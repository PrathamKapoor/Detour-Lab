"""Search orchestration: one bounded, persisted, replayable optimisation run.

Flow (MASTER_PROMPT §7):

    validate -> baseline (real runs) -> eligibility -> domain plan
    -> per candidate: materialise -> verify (real engine) -> classify
    -> rank -> status -> persist with execution id + semantic hash

Guarantees:

* the source scenario is only ever **read**; a candidate preview exists in
  memory and is never written back by a search;
* every candidate goes through the real pipeline - there is no fast path;
* limits (interventions, candidates, duration) are enforced *and echoed*;
* the persisted payload carries an execution identity (``opt-...``) separate
  from the semantic hash, so replay can be proven across restarts.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from detour_lab import ENGINE_VERSION
from detour_lab.analysis.run import run_analysis
from detour_lab.api.state import rulepack_path
from detour_lab.domain.contracts import CandidateProposal, Intervention, RulePack, Scenario
from detour_lab.domain.enums import SolverStatus
from detour_lab.domain.hashing import semantic_hash
from detour_lab.graph.model import PedestrianGraph
from detour_lab.optimization.generator import assess_eligibility, plan_domain
from detour_lab.optimization.library import InterventionLibrary
from detour_lab.optimization.model import (
    BaselineOD,
    BaselineProfile,
    CandidateCostSummary,
    CandidateEvaluation,
    DomainSummary,
    RankingPolicy,
    SearchConfig,
    SearchOutcome,
    SearchStatus,
)
from detour_lab.optimization.rank import determine_status, rank_candidates
from detour_lab.optimization.verify import (
    CandidateError,
    analysis_comparison_body,
    check_budget,
    materialise_candidate,
    verify_candidate,
)
from detour_lab.persistence.repository import Repository
from detour_lab.rules.engine import load_rulepack
from detour_lab.rules.profiles import DEMO_PROFILES
from detour_lab.scenarios.apply import build_phase_graph

logger = logging.getLogger(__name__)

__all__ = ["SearchInputError", "run_search"]

_DISCLAIMERS = (
    "Modeled checks only. A candidate 'Pass' means every applicable check in the demonstration "
    "rulepack was satisfied by the evidence available; it is not legal compliance, professional "
    "approval, or a statement that anyone can physically travel the route.",
    "Every value in the bundled intervention library and demo dataset is synthetic demonstration "
    "data authored in this repository. No real price, engineering finding or legal threshold is "
    "included.",
    "The search is bounded: limits are user-visible, and a truncated search never claims optimality.",
)


class SearchInputError(ValueError):
    """Invalid search inputs (HTTP 400)."""

    def __init__(self, message: str, *, code: str = "INVALID_INPUT", details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _profile_map() -> dict[str, Any]:
    return {profile.id: profile for profile in DEMO_PROFILES}


def run_search(
    *,
    repository: Repository,
    library: InterventionLibrary,
    scenario_id: str,
    phase_id: str,
    profile_ids: list[str] | None,
    evaluation_instant: datetime,
    config: SearchConfig,
    clock: Callable[[], float] = time.perf_counter,
) -> SearchOutcome:
    started = clock()
    if evaluation_instant.tzinfo is None:
        raise SearchInputError("evaluation_instant must be timezone-aware; results must state their instant")
    instant = evaluation_instant.astimezone(UTC)

    scenario = repository.get_scenario(scenario_id)  # NotFoundError -> 404 at the route
    if scenario.phase_by_id(phase_id) is None:
        raise SearchInputError(
            f"phase {phase_id!r} is not declared by scenario {scenario_id!r}",
            details={"declared_phases": [p.id for p in scenario.ordered_phases()]},
        )
    profiles = _profile_map()
    selected_profiles = list(profile_ids) if profile_ids is not None else list(scenario.profile_ids)
    if not selected_profiles:
        raise SearchInputError("at least one mobility profile must be selected")
    unknown_profiles = [pid for pid in selected_profiles if pid not in profiles]
    if unknown_profiles:
        raise SearchInputError(
            f"unknown profile id(s): {unknown_profiles}",
            details={"known_profiles": sorted(profiles)},
        )
    if len(set(selected_profiles)) != len(selected_profiles):
        raise SearchInputError("profile_ids must not repeat")

    unknown_exclusions = [i for i in config.excluded_intervention_ids if library.by_id(i) is None]
    if unknown_exclusions:
        raise SearchInputError(
            f"excluded_intervention_ids contains unknown id(s): {unknown_exclusions}",
            details={"library_id": library.id, "known_interventions": list(library.ids)},
        )

    rulepack: RulePack = load_rulepack(rulepack_path())
    if scenario.rulepack_id != rulepack.id or scenario.rulepack_hash != rulepack.content_hash:
        raise SearchInputError(
            "scenario references a different rulepack than the bundled one; refusing to search with "
            "a mismatched rulepack hash",
            details={"scenario_rulepack": scenario.rulepack_id, "bundled_rulepack": rulepack.id},
        )
    base_graph: PedestrianGraph = repository.get_graph_version(scenario.base_graph_version_id)

    # -- source baseline (real runs, read-only) -----------------------------
    source_phase_graph = build_phase_graph(base_graph, scenario, phase_id)
    source_results = {
        profile_id: run_analysis(
            base_graph=base_graph,
            scenario=scenario,
            phase_id=phase_id,
            profile_id=profile_id,
            rulepack=rulepack,
            profile=profiles[profile_id],
            as_of=instant,
        )
        for profile_id in selected_profiles
    }
    baseline = [
        BaselineProfile(
            profile_id=profile_id,
            semantic_hash=semantic_hash(analysis_comparison_body(source_results[profile_id])),
            phase_graph_id=source_results[profile_id].phase_graph_id,
            phase_graph_hash=source_results[profile_id].phase_graph_hash,
            od_results=[
                BaselineOD(
                    origin_id=result.origin_id,
                    destination_id=result.destination_id,
                    confirmed_reachable=result.confirmed_reachable,
                    possibly_reachable=result.possibly_reachable,
                    confirmed_distance_m=result.confirmed_distance_m,
                    possible_distance_m=result.possible_distance_m,
                )
                for result in source_results[profile_id].od_results
            ],
        )
        for profile_id in selected_profiles
    ]

    # -- eligibility ---------------------------------------------------------
    eligibility = assess_eligibility(
        library_interventions=library.interventions,
        scenario=scenario,
        base_graph=base_graph,
        phase_graph=source_phase_graph,
        rulepack=rulepack,
        phase_id=phase_id,
        excluded_ids=set(config.excluded_intervention_ids),
        as_of=instant,
    )

    # -- budget currency is never converted ---------------------------------
    if config.budget is not None:
        declared_currencies = sorted(
            {cost.currency for intervention in eligibility.eligible for cost in intervention.costs}
        )
        if declared_currencies and config.budget.currency not in declared_currencies:
            raise SearchInputError(
                f"budget currency {config.budget.currency!r} does not match any declared demo cost "
                f"currency {declared_currencies}; no exchange rate exists",
                code="INVALID_BUDGET_CURRENCY",
                details={"declared_currencies": declared_currencies},
            )

    # -- domain --------------------------------------------------------------
    plan = plan_domain(
        eligibility=eligibility,
        config=config,
        ineligible_reasons=eligibility.ineligible_reasons,
    )

    # -- evaluate candidates -------------------------------------------------
    interventions_by_id: dict[str, Intervention] = {
        intervention.id: intervention for intervention in eligibility.eligible
    }
    evaluations: list[CandidateEvaluation] = []
    duration_limit_s = config.max_duration_ms / 1000.0
    truncated_by_duration = False

    for subset in plan.subsets:
        if clock() - started > duration_limit_s:
            truncated_by_duration = True
            break
        selected = [interventions_by_id[i] for i in subset]
        evaluations.append(
            _evaluate_one(
                subset=subset,
                selected=selected,
                source=scenario,
                base_graph=base_graph,
                rulepack=rulepack,
                profiles=profiles,
                profile_ids=selected_profiles,
                source_results=source_results,
                phase_id=phase_id,
                instant=instant,
                config=config,
            )
        )
        if clock() - started > duration_limit_s:
            truncated_by_duration = True
            break

    evaluation_failures = sum(1 for e in evaluations if e.evaluation_failure is not None)
    exhaustive = plan.enumeration_complete and not truncated_by_duration

    # -- rank & status --------------------------------------------------------
    policy = RankingPolicy()
    ranking = rank_candidates(
        evaluations,
        monetary=config.monetary_objective == "nominal",
        exhaustive=exhaustive,
        policy=policy,
    )
    limits_hit: list[str] = []
    if not plan.enumeration_complete and not truncated_by_duration:
        limits_hit.append("candidate_limit")
    if truncated_by_duration:
        limits_hit.append("duration_limit")
    if plan.side_lists_capped:
        limits_hit.append("side_lists_capped")
    status = determine_status(
        ranked=ranking.ranked,
        exhaustive=exhaustive,
        limits_hit=limits_hit,
        evaluation_failures=evaluation_failures,
        eligible_count=len(eligibility.eligible),
    )

    duration_ms = (clock() - started) * 1000.0
    domain = DomainSummary(
        eligible_intervention_ids=[i.id for i in eligibility.eligible],
        excluded_interventions=list(eligibility.excluded),
        domain_combination_count=plan.domain_combination_count,
        evaluated_count=len(evaluations),
        truncated_by=(
            ["duration_limit"]
            if truncated_by_duration
            else (["candidate_limit"] if not plan.enumeration_complete else [])
        ),
        exhausted=exhaustive,
        dependency_blocked=plan.dependency_blocked,
        mutually_exclusive_blocked=plan.mutually_exclusive_blocked,
        precondition_rejected=list(eligibility.precondition_rejected),
    )

    input_hash = semantic_hash(
        {
            "scenario_id": scenario.id,
            "scenario_revision": scenario.revision,
            "scenario_content_hash": scenario.content_hash,
            "base_graph_hash": base_graph.version.content_hash,
            "rulepack_hash": rulepack.content_hash,
            "phase_id": phase_id,
            "profile_ids": sorted(selected_profiles),
            "evaluation_instant": instant.isoformat(),
            "config": config.model_dump(mode="json"),
            "engine_version": ENGINE_VERSION,
        }
    )

    outcome = SearchOutcome(
        engine_version=ENGINE_VERSION,
        search_id=f"opt-{uuid.uuid4().hex[:12]}",
        created_at=datetime.now(UTC).isoformat(),
        duration_ms=round(duration_ms, 3),
        scenario_id=scenario.id,
        scenario_revision=scenario.revision,
        scenario_content_hash=scenario.content_hash,
        base_graph_version_id=base_graph.version.id,
        base_graph_hash=base_graph.version.content_hash,
        rulepack_id=rulepack.id,
        rulepack_hash=rulepack.content_hash,
        phase_id=phase_id,
        profile_ids=selected_profiles,
        evaluation_instant=instant.isoformat(),
        config=config,
        domain=domain,
        baseline=baseline,
        candidates=ranking.ranked,
        ranking_policy=policy,
        status=SearchStatus(
            solver_status=status.solver_status,
            exhaustive=exhaustive,
            limits_hit=limits_hit,
            best_proposal_id=status.best_proposal_id,
            notes=status.notes,
        ),
        input_hash=input_hash,
        semantic_hash="",
        disclaimers=list(_DISCLAIMERS),
    )
    outcome = outcome.model_copy(update={"semantic_hash": semantic_hash(outcome.semantic_body())})
    repository.store_optimization_run(
        search_id=outcome.search_id,
        scenario_id=outcome.scenario_id,
        scenario_revision=outcome.scenario_revision,
        phase_id=outcome.phase_id,
        engine_version=outcome.engine_version,
        evaluation_instant=outcome.evaluation_instant,
        input_hash=outcome.input_hash,
        semantic_hash=outcome.semantic_hash,
        payload=outcome.model_dump(mode="json"),
        created_at=outcome.created_at,
    )
    return outcome


def _evaluate_one(
    *,
    subset: tuple[str, ...],
    selected: list[Intervention],
    source: Scenario,
    base_graph: PedestrianGraph,
    rulepack: RulePack,
    profiles: dict[str, Any],
    profile_ids: list[str],
    source_results: dict[str, Any],
    phase_id: str,
    instant: datetime,
    config: SearchConfig,
) -> CandidateEvaluation:
    """Verify one subset; convert every failure mode into an explicit outcome."""
    try:
        materialisation = materialise_candidate(source, selected)
    except CandidateError as exc:
        return _rejected_evaluation(
            subset,
            reasons=[f"{exc.code}: {reason}" for reason in exc.reasons],
            failure=None,
        )
    except Exception as exc:  # surfaced to the caller, never swallowed
        logger.exception("unexpected error materialising candidate %s", subset)
        return _rejected_evaluation(
            subset,
            reasons=[f"evaluation error: {type(exc).__name__}: {exc}"],
            failure={"stage": "materialisation", "error_type": type(exc).__name__, "message": str(exc)},
        )

    try:
        outcome = verify_candidate(
            source=source,
            materialisation=materialisation,
            base_graph=base_graph,
            rulepack=rulepack,
            profile_ids=profile_ids,
            profiles=profiles,
            source_results=source_results,
            phase_id=phase_id,
            as_of=instant,
        )
    except CandidateError as exc:
        return _rejected_evaluation(
            subset,
            reasons=[f"{exc.code}: {reason}" for reason in exc.reasons],
            failure=None,
        )
    except Exception as exc:  # surfaced to the caller, never swallowed
        logger.exception("unexpected error verifying candidate %s", subset)
        return _rejected_evaluation(
            subset,
            reasons=[f"evaluation error: {type(exc).__name__}: {exc}"],
            failure={"stage": "verification", "error_type": type(exc).__name__, "message": str(exc)},
        )

    budget_check = check_budget(config.budget, materialisation.cost_summary)
    classification = outcome.classification
    rejection_reasons = list(outcome.proposal.rejection_reasons)
    solver_status = outcome.proposal.solver_status
    if config.budget is not None and budget_check.status != "within":
        classification = "rejected"
        solver_status = SolverStatus.NO_FEASIBLE_IN_ENUMERATED_DOMAIN
        if budget_check.status == "exceeds":
            rejection_reasons.append(f"budget: {budget_check.detail}")
        else:
            rejection_reasons.append(
                "budget: cost cannot be certified (no declared price for every line); "
                "not treated as fitting and not treated as zero"
            )
    proposal = CandidateProposal(
        proposal_id=outcome.proposal.proposal_id,
        intervention_ids=outcome.proposal.intervention_ids,
        eligible=classification != "rejected",
        rejection_reasons=rejection_reasons,
        restored_required_od=outcome.proposal.restored_required_od,
        requires_verification=outcome.proposal.requires_verification,
        passed_profiles=outcome.proposal.passed_profiles,
        failed_profiles=outcome.proposal.failed_profiles,
        cost_nominal=outcome.proposal.cost_nominal,
        cost_max=outcome.proposal.cost_max,
        cost_unknown=outcome.proposal.cost_unknown,
        added_distance_m=outcome.proposal.added_distance_m,
        solver_status=solver_status,
    )
    return CandidateEvaluation(
        proposal=proposal,
        classification=classification,  # type: ignore[arg-type]
        intervention_ids=materialisation.selected_intervention_ids,
        intervention_count=len(materialisation.selected_intervention_ids),
        restored_all_profiles=outcome.restored_all_profiles,
        restored_any_profile=outcome.restored_any_profile,
        regressed_pairs=outcome.regressed_pairs,
        verifications=outcome.verifications,
        assumptions=materialisation.assumptions,
        applied_phase_changes=materialisation.applied_phase_changes,
        introduced_fail_verdict_count=outcome.introduced_fail_verdict_count,
        introduced_unknown_verdict_count=outcome.introduced_unknown_verdict_count,
        cost=materialisation.cost_summary,
        budget=budget_check,
        preview_scenario_hash=materialisation.scenario.content_hash,
        preview_phase_graph_hash=(
            outcome.verifications[0].candidate_phase_graph_hash if outcome.verifications else ""
        ),
    )


def _rejected_evaluation(
    subset: tuple[str, ...],
    *,
    reasons: list[str],
    failure: dict[str, Any] | None,
) -> CandidateEvaluation:
    proposal_id = "cand-" + semantic_hash({"subset": list(subset), "reasons": reasons}).split(":")[-1][:12]
    return CandidateEvaluation(
        proposal=CandidateProposal(
            proposal_id=proposal_id,
            intervention_ids=list(subset),
            eligible=False,
            rejection_reasons=reasons,
            restored_required_od=False,
            requires_verification=False,
            passed_profiles=[],
            failed_profiles=[],
            cost_nominal=None,
            cost_max=None,
            cost_unknown=True,
            added_distance_m=None,
            solver_status=(
                SolverStatus.INCOMPLETE_OR_UNKNOWN if failure is not None else SolverStatus.INVALID_INPUT
            ),
        ),
        classification="rejected",
        intervention_ids=list(subset),
        intervention_count=len(subset),
        restored_all_profiles=[],
        restored_any_profile=[],
        regressed_pairs=[],
        verifications=[],
        assumptions=[],
        applied_phase_changes=[],
        introduced_fail_verdict_count=0,
        introduced_unknown_verdict_count=0,
        cost=CandidateCostSummary(
            currency=None,
            nominal=None,
            maximum=None,
            unknown=True,
            provenance_notes=["Candidate was not evaluated; cost is not estimated."],
        ),
        preview_scenario_hash="",
        preview_phase_graph_hash="",
        evaluation_failure=failure,
    )
