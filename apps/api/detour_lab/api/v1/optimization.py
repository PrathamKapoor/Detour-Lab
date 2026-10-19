"""Fix This Plan routes (MASTER_PROMPT §10).

Four read/write endpoints, all with the flat error envelope:

* ``GET  /scenarios/{id}/optimization/interventions`` - the bundled library as
  applicable to one phase, with per-intervention eligibility reasons;
* ``POST /scenarios/{id}/optimization/search`` - one bounded, persisted search;
* ``GET  /scenarios/{id}/optimization/searches`` - search history for replay;
* ``GET  /optimization/searches/{search_id}`` - one stored search payload;
* ``POST /optimization/promote`` - explicit, transactional apply-to-branch.

Nothing here computes verdicts: the heavy lifting lives in
``detour_lab.optimization`` and every candidate is verified through the real
analysis pipeline before it is reported.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from detour_lab.api.state import interventions_path, rulepack_path
from detour_lab.api.v1.routers import DEMO_EVALUATION_INSTANT, _error, get_repository
from detour_lab.optimization import (
    LibraryError,
    PromotionError,
    SearchConfig,
    SearchInputError,
    load_intervention_library,
    promote_proposal,
    run_search,
)
from detour_lab.optimization.generator import assess_eligibility
from detour_lab.optimization.model import SearchOutcome
from detour_lab.persistence.repository import NotFoundError, Repository, StoredOptimizationRun
from detour_lab.rules.engine import load_rulepack
from detour_lab.scenarios.apply import GraphEditError, build_phase_graph

router = APIRouter(prefix="/api/v1", tags=["optimization"])


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase_id: str = Field(min_length=1)
    profile_ids: list[str] | None = None
    #: ISO-8601. Defaults to the fixed demo instant so demo replay is stable.
    evaluation_instant: str | None = None
    config: SearchConfig = Field(default_factory=SearchConfig)


class PromoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    new_scenario_id: str = Field(min_length=1)
    new_scenario_name: str = Field(min_length=1)
    expected_source_revision: int = Field(ge=1)


def _parse_instant(value: str | None) -> datetime:
    if value is None:
        return DEMO_EVALUATION_INSTANT
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _error(
            400, "INVALID_INPUT", f"evaluation_instant {value!r} is not a valid ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise _error(
            400,
            "INVALID_INPUT",
            "evaluation_instant must include a timezone offset; results must state their instant",
        )
    return parsed


def _scenario_or_404(repository: Repository, scenario_id: str):
    try:
        return repository.get_scenario(scenario_id)
    except NotFoundError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc


def _library():
    try:
        return load_intervention_library(interventions_path())
    except LibraryError as exc:
        # A broken bundled library is a server-side defect, surfaced loudly.
        raise _error(500, exc.code, str(exc), exc.detail) from exc


def _search_summary(record: StoredOptimizationRun) -> dict:
    status = record.payload.get("status", {})
    candidates = record.payload.get("candidates", [])
    return {
        "search_id": record.search_id,
        "scenario_id": record.scenario_id,
        "scenario_revision": record.scenario_revision,
        "phase_id": record.phase_id,
        "evaluation_instant": record.evaluation_instant,
        "engine_version": record.engine_version,
        "semantic_hash": record.semantic_hash,
        "input_hash": record.input_hash,
        "created_at": record.created_at,
        "solver_status": status.get("solver_status"),
        "exhaustive": status.get("exhaustive"),
        "best_proposal_id": status.get("best_proposal_id"),
        "candidate_count": len(candidates),
    }


@router.get("/scenarios/{scenario_id}/optimization/interventions")
def list_interventions(
    scenario_id: str,
    phase_id: str | None = Query(default=None),
    repository: Repository = Depends(get_repository),
) -> dict:
    """The bundled intervention library as applicable to the selected phase."""
    scenario = _scenario_or_404(repository, scenario_id)
    declared = [phase.id for phase in scenario.ordered_phases()]
    selected_phase = phase_id or (declared[0] if declared else None)
    if selected_phase is None or scenario.phase_by_id(selected_phase) is None:
        raise _error(
            400,
            "INVALID_INPUT",
            f"phase {selected_phase!r} is not declared by scenario {scenario_id!r}",
            {"declared_phases": declared},
        )

    library = _library()
    rulepack = load_rulepack(rulepack_path())
    base_graph = repository.get_graph_version(scenario.base_graph_version_id)
    try:
        phase_graph = build_phase_graph(base_graph, scenario, selected_phase)
    except GraphEditError as exc:
        raise _error(500, exc.code, str(exc)) from exc

    eligibility = assess_eligibility(
        library_interventions=library.interventions,
        scenario=scenario,
        base_graph=base_graph,
        phase_graph=phase_graph,
        rulepack=rulepack,
        phase_id=selected_phase,
        excluded_ids=set(),
        as_of=DEMO_EVALUATION_INSTANT,
    )
    eligible_ids = {intervention.id for intervention in eligibility.eligible}
    items: list[dict] = []
    for intervention in library.interventions:
        item = intervention.model_dump(mode="json")
        item["applicable"] = intervention.id in eligible_ids
        item["eligibility_reasons"] = list(eligibility.ineligible_reasons.get(intervention.id, []))
        items.append(item)

    return {
        "library": {
            "id": library.id,
            "version": library.version,
            "notice": library.notice,
            "source": str(interventions_path()),
        },
        "scenario_id": scenario.id,
        "scenario_revision": scenario.revision,
        "phase_id": selected_phase,
        "declared_phases": declared,
        "evaluated_as_of": DEMO_EVALUATION_INSTANT.isoformat(),
        "interventions": items,
        "eligible_intervention_ids": sorted(eligible_ids),
        "excluded": [entry.model_dump(mode="json") for entry in eligibility.excluded],
        "precondition_rejected": list(eligibility.precondition_rejected),
    }


@router.post("/scenarios/{scenario_id}/optimization/search", status_code=200)
def start_search(
    scenario_id: str,
    payload: SearchRequest,
    repository: Repository = Depends(get_repository),
) -> dict:
    """Run one bounded search. Persisted; the response is the stored payload."""
    try:
        outcome = run_search(
            repository=repository,
            library=_library(),
            scenario_id=scenario_id,
            phase_id=payload.phase_id,
            profile_ids=payload.profile_ids,
            evaluation_instant=_parse_instant(payload.evaluation_instant),
            config=payload.config,
        )
    except NotFoundError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc
    except SearchInputError as exc:
        raise _error(400, exc.code, str(exc), exc.details) from exc
    except GraphEditError as exc:
        raise _error(500, exc.code, str(exc)) from exc
    return outcome.model_dump(mode="json")


@router.get("/scenarios/{scenario_id}/optimization/searches")
def list_searches(
    scenario_id: str,
    repository: Repository = Depends(get_repository),
) -> dict:
    """Search history for this scenario, oldest first, for replay comparisons."""
    _scenario_or_404(repository, scenario_id)
    records = repository.list_optimization_runs(scenario_id)
    return {"scenario_id": scenario_id, "searches": [_search_summary(record) for record in records]}


@router.get("/optimization/searches/{search_id}")
def get_search(
    search_id: str,
    repository: Repository = Depends(get_repository),
) -> dict:
    """The full stored payload of one search (the replay source)."""
    try:
        record = repository.get_optimization_run(search_id)
    except NotFoundError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc
    # Validate against the contract before serving: a stored payload that no
    # longer parses is a surfaced defect, not a silent best-effort response.
    return SearchOutcome.model_validate(record.payload).model_dump(mode="json")


@router.post("/optimization/promote", status_code=201)
def promote(
    payload: PromoteRequest,
    repository: Repository = Depends(get_repository),
) -> dict:
    """Apply one candidate to a **new** scenario branch, then re-verify it."""
    try:
        result = promote_proposal(
            repository=repository,
            library=_library(),
            search_id=payload.search_id,
            proposal_id=payload.proposal_id,
            new_scenario_id=payload.new_scenario_id,
            new_scenario_name=payload.new_scenario_name,
            expected_source_revision=payload.expected_source_revision,
        )
    except PromotionError as exc:
        raise _error(exc.status_code, exc.code, str(exc), exc.details) from exc
    except NotFoundError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc
    return result
