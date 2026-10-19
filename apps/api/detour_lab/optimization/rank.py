"""Ranking, Pareto set and honest solver status (MASTER_PROMPT §7.5-7.6).

The ordering is **lexicographic over measured, model-confirmed quantities**,
documented in :class:`~detour_lab.optimization.model.RankingPolicy` and
mirrored here. There is no weighted sum anywhere: a hidden weight would make
the result unauditable, and a weighted sum must never be presented as a
Pareto frontier.

Status honesty:

* ``OPTIMAL_IN_ENUMERATED_DOMAIN`` is claimed **only** when the eligible
  domain was enumerated completely and a certified candidate exists;
* a truncated search (candidate budget or time budget) can never claim
  optimality;
* a search that found nothing but was truncated is ``INCOMPLETE_OR_UNKNOWN``,
  never "no feasible option exists";
* ``NO_FEASIBLE_IN_ENUMERATED_DOMAIN`` is claimed only after a complete
  enumeration with no certified candidate and no evaluation failures.
"""

from __future__ import annotations

from dataclasses import dataclass

from detour_lab.domain.enums import SolverStatus
from detour_lab.optimization.model import CandidateEvaluation, RankingPolicy

__all__ = ["RankingResult", "determine_status", "rank_candidates"]

_CLASSIFICATION_GROUP = {
    "certified": 0,
    "requires_verification": 1,
    "no_improvement": 2,
    "rejected": 3,
}


@dataclass(slots=True)
class RankingResult:
    ranked: list[CandidateEvaluation]
    pareto_frontier: list[str]


def _rank_key(evaluation: CandidateEvaluation, *, monetary: bool) -> tuple:
    cost = evaluation.cost
    if monetary:
        cost_key: tuple = (0, cost.nominal) if cost.nominal is not None else (1, 0.0)
    else:
        cost_key = (0, 0.0)
    distance = evaluation.proposal.added_distance_m
    distance_key: tuple = (0, distance) if distance is not None else (1, 0.0)
    return (
        _CLASSIFICATION_GROUP[evaluation.classification],
        -len(evaluation.restored_all_profiles),
        -len(evaluation.restored_any_profile),
        evaluation.introduced_fail_verdict_count,
        evaluation.introduced_unknown_verdict_count,
        len(evaluation.regressed_pairs),
        evaluation.intervention_count,
        cost_key,
        distance_key,
        evaluation.proposal.proposal_id,
    )


def _dominates(a: CandidateEvaluation, b: CandidateEvaluation) -> bool:
    """Pareto domination over (restoration, intervention count, distance).

    Distance is compared only when both sides have one; a missing route is
    never treated as 0 m. ``None`` is worst (it cannot dominate).
    """

    def ge(x: float | None, y: float | None) -> bool:
        if x is None:
            return y is None
        return y is None or x <= y

    def strict(x: float | None, y: float | None) -> bool:
        if x is None:
            return False
        return y is None or x < y

    axes_ge = [
        len(a.restored_all_profiles) >= len(b.restored_all_profiles),
        len(a.restored_any_profile) >= len(b.restored_any_profile),
        a.intervention_count <= b.intervention_count,
        ge(a.proposal.added_distance_m, b.proposal.added_distance_m),
    ]
    if not all(axes_ge):
        return False
    axes_strict = [
        len(a.restored_all_profiles) > len(b.restored_all_profiles),
        len(a.restored_any_profile) > len(b.restored_any_profile),
        a.intervention_count < b.intervention_count,
        strict(a.proposal.added_distance_m, b.proposal.added_distance_m),
    ]
    return any(axes_strict)


def rank_candidates(
    evaluations: list[CandidateEvaluation],
    *,
    monetary: bool,
    exhaustive: bool,
    policy: RankingPolicy | None = None,
) -> RankingResult:
    """Assign ranks, tie groups, Pareto flags and candidate solver statuses."""
    del policy  # kept for signature stability; ordering constants live here
    ordered = sorted(evaluations, key=lambda e: _rank_key(e, monetary=monetary))

    previous_meaningful: tuple | None = None
    tie_group = 0
    for index, evaluation in enumerate(ordered, start=1):
        key = _rank_key(evaluation, monetary=monetary)
        # The proposal id is the final deterministic order, not a measured
        # difference: candidates equal on every measured axis share a tie group
        # even though their ids still give the ranking a total order.
        meaningful = key[:-1]
        if previous_meaningful is not None and meaningful != previous_meaningful:
            tie_group += 1
        evaluation.rank = index
        evaluation.tie_group = tie_group
        previous_meaningful = meaningful

    certified = [e for e in ordered if e.classification == "certified"]
    pareto_ids: list[str] = []
    for candidate in certified:
        dominated = any(
            other is not candidate and _dominates(other, candidate) for other in certified
        )
        candidate.pareto_optimal = not dominated
        if candidate.pareto_optimal:
            pareto_ids.append(candidate.proposal.proposal_id)

    if exhaustive and ordered and ordered[0].classification == "certified":
        ordered[0].proposal.solver_status = SolverStatus.OPTIMAL_IN_ENUMERATED_DOMAIN

    return RankingResult(ranked=ordered, pareto_frontier=pareto_ids)


@dataclass(slots=True)
class StatusResult:
    solver_status: SolverStatus
    best_proposal_id: str | None
    notes: list[str]


def determine_status(
    *,
    ranked: list[CandidateEvaluation],
    exhaustive: bool,
    limits_hit: list[str],
    evaluation_failures: int,
    eligible_count: int,
) -> StatusResult:
    """Map the search's actual coverage to one of the five SolverStatus values."""
    notes: list[str] = []
    certified = [e for e in ranked if e.classification == "certified"]
    requires_verification = [e for e in ranked if e.classification == "requires_verification"]

    best: CandidateEvaluation | None = None
    if ranked and ranked[0].classification in {"certified", "requires_verification"}:
        best = ranked[0]

    if eligible_count == 0:
        notes.append(
            "No intervention was eligible for this search; the candidate domain is empty. "
            "Read the exclusion and precondition reasons before concluding anything about the plan."
        )
        return StatusResult(
            solver_status=SolverStatus.NO_FEASIBLE_IN_ENUMERATED_DOMAIN,
            best_proposal_id=None,
            notes=notes,
        )

    if certified:
        if exhaustive:
            return StatusResult(
                solver_status=SolverStatus.OPTIMAL_IN_ENUMERATED_DOMAIN,
                best_proposal_id=best.proposal.proposal_id if best else None,
                notes=notes,
            )
        notes.append(
            "A model-confirmed candidate exists, but the search was truncated, so it is not proven "
            "optimal over the eligible domain."
        )
        return StatusResult(
            solver_status=SolverStatus.FEASIBLE_NOT_PROVEN_OPTIMAL,
            best_proposal_id=best.proposal.proposal_id if best else None,
            notes=notes,
        )

    if requires_verification:
        notes.append(
            f"{len(requires_verification)} candidate(s) improve only the possible graph (unresolved "
            "evidence) and remain in the requires-verification bucket; none is model-confirmed."
        )

    if exhaustive and evaluation_failures == 0:
        notes.append(
            "The eligible domain was enumerated completely and contains no model-confirmed candidate."
        )
        return StatusResult(
            solver_status=SolverStatus.NO_FEASIBLE_IN_ENUMERATED_DOMAIN,
            best_proposal_id=None,
            notes=notes,
        )

    if evaluation_failures:
        notes.append(
            f"{evaluation_failures} candidate(s) could not be evaluated; the domain is not fully verified."
        )
    if limits_hit:
        notes.append(f"Search limits were reached: {sorted(set(limits_hit))}.")
    return StatusResult(
        solver_status=SolverStatus.INCOMPLETE_OR_UNKNOWN,
        best_proposal_id=None,
        notes=notes,
    )
