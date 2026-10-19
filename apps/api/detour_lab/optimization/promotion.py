"""Transactional scenario promotion (MASTER_PROMPT §7.9, "Apply to branch").

Promotion is an **explicit user action** that turns one evaluated candidate
into a new, independent scenario branch. The rules enforced here:

* the source scenario is never mutated - only read;
* the new branch is a *clone with edits*: it preserves the full declared plan
  of the source (phases, closures, temporary edges, origins/destinations) and
  the source's own edit list, then appends the candidate's effects. (This is
  the D-025 gap being closed for this path: branch creation must not drop the
  declared plan.)
* creation is one transaction with an optimistic-concurrency check: a stale
  ``expected_source_revision`` or a taken branch id fails with 409 and writes
  nothing;
* the candidate is re-materialised against the *current* source revision and
  its preview hash must match what the search recorded, otherwise the stored
  search is stale (409) - never silently promoted;
* after the commit the branch is re-read and re-analysed per profile; any
  mismatch between preview and persisted state is a surfaced internal defect
  (HTTP 500), not a silent success.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from detour_lab import ENGINE_VERSION
from detour_lab.analysis.run import run_analysis
from detour_lab.api.state import rulepack_path
from detour_lab.domain.contracts import Scenario
from detour_lab.domain.hashing import semantic_hash
from detour_lab.optimization.library import InterventionLibrary
from detour_lab.optimization.model import SearchOutcome
from detour_lab.optimization.verify import analysis_comparison_body, materialise_candidate
from detour_lab.persistence.repository import (
    NotFoundError,
    OptimisticConflictError,
    Repository,
    ScenarioIdExistsError,
)
from detour_lab.rules.engine import load_rulepack
from detour_lab.rules.profiles import DEMO_PROFILES

__all__ = ["PromotionError", "promote_proposal"]


class PromotionError(ValueError):
    """Promotion cannot proceed. Carries the HTTP status and envelope code."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details or {}


def promote_proposal(
    *,
    repository: Repository,
    library: InterventionLibrary,
    search_id: str,
    proposal_id: str,
    new_scenario_id: str,
    new_scenario_name: str,
    expected_source_revision: int,
) -> dict[str, Any]:
    try:
        record = repository.get_optimization_run(search_id)
    except NotFoundError as exc:
        raise PromotionError(
            f"search {search_id!r} does not exist", code="SEARCH_NOT_FOUND", status_code=404
        ) from exc

    outcome = SearchOutcome.model_validate(record.payload)
    source = repository.get_scenario(outcome.scenario_id)
    if source.revision != outcome.scenario_revision:
        raise PromotionError(
            f"the stored search was run against revision {outcome.scenario_revision}, but the "
            f"scenario is now at revision {source.revision}; run a new search",
            code="STALE_SEARCH",
            status_code=409,
            details={
                "searched_revision": outcome.scenario_revision,
                "current_revision": source.revision,
            },
        )
    if source.revision != expected_source_revision:
        raise PromotionError(
            f"the scenario moved from revision {expected_source_revision} (expected) to "
            f"{source.revision}; nothing was written",
            code="STALE_REVISION",
            status_code=409,
            details={"expected_revision": expected_source_revision, "actual_revision": source.revision},
        )

    candidate = next(
        (c for c in outcome.candidates if c.proposal.proposal_id == proposal_id), None
    )
    if candidate is None:
        raise PromotionError(
            f"proposal {proposal_id!r} is not part of search {search_id!r}",
            code="PROPOSAL_NOT_FOUND",
            status_code=404,
            details={"search_id": search_id},
        )
    if candidate.classification == "rejected":
        raise PromotionError(
            "this candidate is rejected and cannot be promoted",
            code="CANDIDATE_REJECTED",
            status_code=409,
            details={"rejection_reasons": candidate.proposal.rejection_reasons},
        )

    selected = []
    for intervention_id in candidate.intervention_ids:
        intervention = library.by_id(intervention_id)
        if intervention is None:
            raise PromotionError(
                f"intervention {intervention_id!r} is no longer in the bundled library; the stored "
                "search cannot be replayed",
                code="LIBRARY_CHANGED",
                status_code=409,
                details={"missing_intervention": intervention_id},
            )
        selected.append(intervention)

    materialisation = materialise_candidate(source, selected)
    if materialisation.scenario.content_hash != candidate.preview_scenario_hash:
        raise PromotionError(
            "re-materialising the candidate from the current source does not reproduce the preview "
            "hash recorded by the search; refusing to promote a stale preview",
            code="STALE_SEARCH",
            status_code=409,
            details={
                "recorded_preview_hash": candidate.preview_scenario_hash,
                "recomputed_preview_hash": materialisation.scenario.content_hash,
            },
        )

    if new_scenario_id == source.id:
        raise PromotionError(
            "the branch id must differ from the source scenario id",
            code="INVALID_INPUT",
            status_code=400,
        )

    payload = materialisation.scenario.model_dump(mode="json")
    payload.update(
        {
            "id": new_scenario_id,
            "name": new_scenario_name,
            "revision": 1,
            "parent_scenario_id": source.id,
            "created_at": datetime.now(UTC).isoformat(),
            "content_hash": "",
            "note": (
                f"Promoted from search {search_id} (proposal {proposal_id}) against "
                f"{source.id!r} revision {source.revision}. Candidate effects are modelled demo "
                "values; nothing here is field-verified."
            ),
        }
    )
    branch = Scenario.model_validate(payload)

    try:
        repository.promote_scenario(
            scenario=branch,
            source_scenario_id=source.id,
            expected_source_revision=expected_source_revision,
        )
    except OptimisticConflictError as exc:
        raise PromotionError(
            str(exc), code="STALE_REVISION", status_code=409,
            details={"expected_revision": exc.expected, "actual_revision": exc.actual},
        ) from exc
    except ScenarioIdExistsError as exc:
        raise PromotionError(
            f"scenario id {new_scenario_id!r} already exists; nothing was written",
            code="SCENARIO_ID_EXISTS",
            status_code=409,
        ) from exc

    # -- persisted-vs-preview verification -----------------------------------
    persisted = repository.get_scenario(new_scenario_id)
    content_hash_match = persisted.content_hash == branch.content_hash

    base_graph = repository.get_graph_version(persisted.base_graph_version_id)
    rulepack = load_rulepack(rulepack_path())
    profiles = {profile.id: profile for profile in DEMO_PROFILES}
    instant = datetime.fromisoformat(outcome.evaluation_instant)
    preview_hashes = {v.profile_id: v.candidate_semantic_hash for v in candidate.verifications}
    per_profile: list[dict[str, Any]] = []
    all_match = True
    for profile_id in outcome.profile_ids:
        result = run_analysis(
            base_graph=base_graph,
            scenario=persisted,
            phase_id=outcome.phase_id,
            profile_id=profile_id,
            rulepack=rulepack,
            profile=profiles[profile_id],
            as_of=instant,
        )
        persisted_hash = semantic_hash(analysis_comparison_body(result))
        expected_hash = preview_hashes.get(profile_id, "")
        match = persisted_hash == expected_hash
        all_match = all_match and match
        per_profile.append(
            {
                "profile_id": profile_id,
                "preview_semantic_hash": expected_hash,
                "persisted_semantic_hash": persisted_hash,
                "match": match,
            }
        )

    source_after = repository.get_scenario(source.id)
    source_unchanged = (
        source_after.revision == source.revision and source_after.content_hash == source.content_hash
    )

    if not content_hash_match or not all_match:
        raise PromotionError(
            "the persisted branch does not reproduce the previewed verification; this is an internal "
            "defect and is reported instead of being silently accepted",
            code="PROMOTION_VERIFICATION_MISMATCH",
            status_code=500,
            details={
                "content_hash_match": content_hash_match,
                "preview_scenario_hash": branch.content_hash,
                "persisted_scenario_hash": persisted.content_hash,
                "per_profile": per_profile,
            },
        )

    return {
        "engine_version": ENGINE_VERSION,
        "search_id": search_id,
        "proposal_id": proposal_id,
        "classification": candidate.classification,
        "source": {
            "scenario_id": source.id,
            "revision": source.revision,
            "content_hash": source.content_hash,
            "unchanged": source_unchanged,
        },
        "branch": {
            "scenario_id": persisted.id,
            "name": persisted.name,
            "revision": persisted.revision,
            "parent_scenario_id": persisted.parent_scenario_id,
            "content_hash": persisted.content_hash,
            "intervention_ids": persisted.intervention_ids,
        },
        "verification": {
            "content_hash_match": content_hash_match,
            "per_profile": per_profile,
            "all_match": all_match,
        },
        "od_summary": {
            "restored_all_profiles": candidate.restored_all_profiles,
            "restored_any_profile": candidate.restored_any_profile,
            "regressed_pairs": candidate.regressed_pairs,
        },
        "disclaimers": [
            "The branch carries modelled demo values from the intervention library; they are not "
            "field-verified and are not legal or engineering approval.",
            "A single-phase improvement is not whole-project continuity.",
        ],
    }
