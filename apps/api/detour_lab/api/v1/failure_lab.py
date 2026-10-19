"""Failure Lab HTTP surface (Gate 6, G6-05..G6-12).

Routes
------
``GET  /api/v1/scenarios/{id}/failure-lab/catalog``           suite catalogue + readiness
``GET  /api/v1/scenarios/{id}/failure-lab/limits``            enforced bounds
``POST /api/v1/scenarios/{id}/failure-lab/experiments``       run suites and/or ad-hoc faults
``GET  /api/v1/scenarios/{id}/failure-lab/experiments``       stored history
``GET  /api/v1/failure-lab/experiments/{experiment_id}``      one experiment
``POST /api/v1/failure-lab/experiments/{experiment_id}/replay`` re-execute and compare
``GET  /api/v1/failure-lab/experiments/{experiment_id}/graph-differences`` element-level diff

Failure taxonomy in the HTTP layer
----------------------------------
* A fault that cannot be represented safely is ``422`` with a specific code and
  is **never** executed.
* An experiment that was refused after being accepted as a request is stored
  with status ``invalid_experiment`` so a suite cannot look "tested" when it was
  not.
* A software failure during execution is reported as ``execution_failed`` with
  the engine's own message. It is never reported as a modelled network failure.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from detour_lab.api.state import rulepack_path
from detour_lab.api.v1.routers import _error, get_repository
from detour_lab.failure.compare import summarise_robustness
from detour_lab.failure.faults import (
    FAULT_KIND_DESCRIPTIONS,
    FAULT_MUTATION_NOTES,
    FaultValidationError,
    fault_applicability,
)
from detour_lab.failure.model import ExperimentLimits, ExperimentOutcome, FaultDefinition, FaultKind
from detour_lab.failure.service import (
    ExperimentRequestError,
    experiment_history,
    replay_experiment,
    run_experiments,
)
from detour_lab.failure.suite import UNSUPPORTED_SCENARIOS, available_suites
from detour_lab.persistence.repository import NotFoundError, Repository
from detour_lab.rules.engine import load_rulepack

router = APIRouter(prefix="/api/v1", tags=["failure-lab"])


class RunExperimentRequest(BaseModel):
    """Execute bounded experiments against one stored scenario revision.

    ``extra="forbid"`` means a typo is a ``422`` rather than a silently ignored
    field that would change what was actually executed.
    """

    model_config = ConfigDict(extra="forbid")
    phase_ids: list[str] = Field(default_factory=list, max_length=6)
    profile_ids: list[str] = Field(default_factory=list, max_length=2)
    evaluation_instant: str | None = None
    suite_ids: list[str] = Field(default_factory=list, max_length=12)
    faults: list[FaultDefinition] = Field(default_factory=list, max_length=12)
    #: Optional stored runs proven identical to the recomputed baseline.
    baseline_run_ids: list[str] = Field(default_factory=list, max_length=12)


def _instant(value: str | None) -> datetime:
    from detour_lab.api.v1.routers import DEMO_EVALUATION_INSTANT

    if value is None:
        return DEMO_EVALUATION_INSTANT
    from detour_lab.domain.units import parse_timestamp

    try:
        parsed = parse_timestamp(value, field="evaluation_instant")
    except Exception as exc:
        raise _error(
            400,
            "INVALID_INPUT",
            f"evaluation_instant is not a valid ISO 8601 timestamp: {exc}",
            {"field": "evaluation_instant"},
        ) from exc
    if parsed.tzinfo is None:  # pragma: no cover - parse_timestamp always returns aware values
        raise _error(
            400,
            "INVALID_INPUT",
            "evaluation_instant must include a timezone offset",
            {"field": "evaluation_instant"},
        )
    return parsed.astimezone(UTC)


def _outcome_envelope(outcomes: list[ExperimentOutcome]) -> dict:
    summary = summarise_robustness(outcomes=outcomes, available_kinds=list(FaultKind))
    return {
        "experiments": [o.model_dump(mode="json") for o in outcomes],
        "experiment_count": len(outcomes),
        "robustness": summary.model_dump(mode="json"),
        "limits": ExperimentLimits().model_dump(mode="json"),
        "unsupported_scenarios": [dict(entry) for entry in UNSUPPORTED_SCENARIOS],
    }


@router.get("/scenarios/{scenario_id}/failure-lab/catalog")
def failure_lab_catalog(
    scenario_id: str,
    phase_id: str | None = Query(default=None),
    repository: Repository = Depends(get_repository),
) -> dict:
    """Supported fault kinds, suite readiness and the conditions left out."""
    try:
        scenario = repository.get_scenario(scenario_id)
        graph = repository.get_graph_version(scenario.base_graph_version_id)
    except NotFoundError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc
    rulepack = load_rulepack(rulepack_path())
    phases = [phase_id] if phase_id else [p.id for p in scenario.ordered_phases()]
    return {
        "scenario_id": scenario_id,
        "scenario_revision": scenario.revision,
        "scenario_content_hash": scenario.content_hash,
        "declared_phase_ids": [p.id for p in scenario.ordered_phases()],
        "selected_phase_ids": phases,
        "rulepack": {
            "id": rulepack.id,
            "version": rulepack.version,
            "content_hash": rulepack.content_hash,
            "legal_applicability": rulepack.legal_applicability,
        },
        "fault_kinds": [
            {
                "kind": kind.value,
                "description": FAULT_KIND_DESCRIPTIONS[kind.value],
                "mutation_note": FAULT_MUTATION_NOTES.get(kind.value, ""),
            }
            for kind in FaultKind
        ],
        "suites": available_suites(scenario, graph),
        "limits": ExperimentLimits().model_dump(mode="json"),
        "unsupported_scenarios": [dict(entry) for entry in UNSUPPORTED_SCENARIOS],
        "honesty_note": (
            "Every fault below is an explicitly modelled condition evaluated by the authoritative "
            "engine. None of them is a prediction of a real-world failure, and a fault that does not "
            "apply is reported as unavailable rather than as tested."
        ),
    }


@router.get("/scenarios/{scenario_id}/failure-lab/limits")
def failure_lab_limits(scenario_id: str) -> dict:
    """The enforced bounds, so the interface can show them before execution."""
    return {
        "limits": ExperimentLimits().model_dump(mode="json"),
        "security_note": (
            "Fault definitions are typed schemas interpreted by an explicit per-kind match. No "
            "expression, import path or callable is accepted from a request, so a fault definition "
            "cannot be used to execute code."
        ),
    }


@router.post("/scenarios/{scenario_id}/failure-lab/experiments")
def create_experiment(
    scenario_id: str,
    payload: RunExperimentRequest,
    repository: Repository = Depends(get_repository),
) -> dict:
    """Run the requested fault suites and/or ad-hoc fault definitions."""
    if not payload.suite_ids and not payload.faults:
        raise _error(
            400,
            "INVALID_REQUEST",
            "select at least one fault suite or provide at least one fault definition",
            {"known_fault_kinds": [k.value for k in FaultKind]},
        )
    try:
        outcomes = run_experiments(
            repository=repository,
            scenario_id=scenario_id,
            phase_ids=payload.phase_ids,
            profile_ids=payload.profile_ids,
            evaluation_instant=_instant(payload.evaluation_instant),
            suite_ids=payload.suite_ids,
            faults=payload.faults,
            limits=ExperimentLimits(),
            baseline_run_ids=payload.baseline_run_ids,
        )
    except NotFoundError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc
    except ExperimentRequestError as exc:
        raise _error(400, exc.code, str(exc), exc.details) from exc
    except FaultValidationError as exc:
        raise _error(422, exc.code, str(exc), exc.details) from exc
    return _outcome_envelope(outcomes)


@router.get("/scenarios/{scenario_id}/failure-lab/experiments")
def list_experiments(scenario_id: str, repository: Repository = Depends(get_repository)) -> dict:
    """Stored experiment history, oldest first, with both identity hashes."""
    try:
        history = experiment_history(repository, scenario_id)
    except NotFoundError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc
    return {
        "scenario_id": scenario_id,
        "experiments": [h.model_dump(mode="json") for h in history],
        "experiment_count": len(history),
    }


@router.get("/failure-lab/experiments/{experiment_id}")
def get_experiment(experiment_id: str, repository: Repository = Depends(get_repository)) -> dict:
    try:
        stored = repository.get_failure_experiment(experiment_id)
    except NotFoundError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc
    outcome = ExperimentOutcome.model_validate(stored.payload)
    return {
        "experiment": outcome.model_dump(mode="json"),
        "stored": {
            "experiment_id": stored.experiment_id,
            "created_at": stored.created_at,
            "duration_ms": stored.duration_ms,
            "scenario_revision": stored.scenario_revision,
            "input_hash": stored.input_hash,
            "semantic_hash": stored.semantic_hash,
        },
    }


@router.post("/failure-lab/experiments/{experiment_id}/replay")
def replay_experiment_route(
    experiment_id: str, repository: Repository = Depends(get_repository)
) -> dict:
    """Re-execute a stored experiment from its own recorded fault definitions."""
    try:
        replay = replay_experiment(repository=repository, experiment_id=experiment_id)
    except NotFoundError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc
    return {
        "experiment_id": experiment_id,
        "reproduced": replay.reproduced,
        "detail": replay.detail,
        "stored_semantic_hash": replay.stored.semantic_hash,
        "stored_input_hash": replay.stored.input_hash,
        "replayed_semantic_hash": replay.outcome.semantic_hash,
        "replayed_experiment_id": replay.outcome.experiment_id,
        "status": replay.outcome.status.value,
    }


@router.get("/failure-lab/experiments/{experiment_id}/graph-differences")
def experiment_graph_differences(
    experiment_id: str, repository: Repository = Depends(get_repository)
) -> dict:
    """Element-level before/after for one experiment, in a nonvisual form."""
    try:
        stored = repository.get_failure_experiment(experiment_id)
    except NotFoundError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc
    outcome = ExperimentOutcome.model_validate(stored.payload)
    before = {row.phase_id + "|" + row.profile_id: row for row in outcome.baseline}
    after = {row.phase_id + "|" + row.profile_id: row for row in outcome.faulted}
    return {
        "experiment_id": experiment_id,
        "status": outcome.status.value,
        "source": outcome.source.model_dump(mode="json"),
        "isolated": {
            "scenario_hash": outcome.isolated_scenario_hash,
            "graph_hash": outcome.isolated_graph_hash,
            "graph_version_id": outcome.isolated_graph_version_id,
            "evaluation_instant": outcome.faulted_evaluation_instant,
        },
        "phase_graph_identities": [
            {
                "phase_id": key.split("|")[0],
                "profile_id": key.split("|")[1],
                "baseline_phase_graph_hash": before[key].phase_graph_hash if key in before else None,
                "faulted_phase_graph_hash": after[key].phase_graph_hash if key in after else None,
                "changed": (before[key].phase_graph_hash if key in before else None)
                != (after[key].phase_graph_hash if key in after else None),
            }
            for key in sorted(set(before) | set(after))
        ],
        "element_changes": [c.model_dump(mode="json") for c in outcome.element_changes],
        "evidence_change_log": list(outcome.evidence_change_log),
        "applicability": fault_applicability(
            graph=repository.get_graph_version(outcome.source.base_graph_version_id),
            scenario=repository.get_scenario(outcome.source.scenario_id),
            faults=outcome.faults,
            default_phases=outcome.source.phase_ids,
        ),
    }