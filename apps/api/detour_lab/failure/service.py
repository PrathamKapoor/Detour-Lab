"""Failure Lab orchestration, persistence and replay (Gate 6, G6-11).

What this service guarantees
---------------------------
* **Persistence is append-only.** Re-running an experiment inserts a new row
  with a new ``experiment_id``. No stored experiment is ever updated, so a
  historical experiment always describes the revision it was run against.
* **Replay is deterministic.** :func:`replay_experiment` re-executes the stored
  fault definitions against the stored source revision and compares the semantic
  hash. A mismatch is reported as a defect, never smoothed over.
* **Revision binding is explicit.** Every experiment records the scenario
  revision and content hash it tested. If the scenario has since moved on, the
  stored experiment still refers to its own revision and replay says so rather
  than silently re-analysing a newer plan.
* **A failed experiment is not a failed plan.** Persisting an execution failure
  is how the system stays honest about its own limits.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from detour_lab.domain.hashing import semantic_hash
from detour_lab.failure.compare import RobustnessSummary, summarise_robustness
from detour_lab.failure.engine import execute_experiment
from detour_lab.failure.faults import FaultValidationError
from detour_lab.failure.model import (
    ExperimentLimits,
    ExperimentOutcome,
    ExperimentStatus,
    ExperimentSummary,
    FaultDefinition,
    FaultKind,
)
from detour_lab.failure.suite import build_suite
from detour_lab.persistence.db import utc_now_iso
from detour_lab.persistence.repository import Repository

__all__ = [
    "ExperimentRequestError",
    "ReplayResult",
    "experiment_history",
    "experiment_summary",
    "replay_experiment",
    "run_experiments",
]


class ExperimentRequestError(ValueError):
    """The request itself is unusable (bad suite, bad phase, unknown scenario)."""

    def __init__(self, message: str, *, code: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def run_experiments(
    *,
    repository: Repository,
    scenario_id: str,
    phase_ids: Sequence[str],
    profile_ids: Sequence[str],
    evaluation_instant: datetime,
    suite_ids: Sequence[str] = (),
    faults: Sequence[FaultDefinition] = (),
    limits: ExperimentLimits | None = None,
    baseline_run_ids: Sequence[str] = (),
    persist: bool = True,
    clock: Any = time.perf_counter,
) -> list[ExperimentOutcome]:
    """Execute one experiment per suite (and/or one ad-hoc fault set).

    A suite is an explicitly defined set of fault definitions; each becomes its
    own experiment so its outcome can be read individually. Suites that do not
    apply to the selected phase are refused by the validator, not skipped.
    """
    from detour_lab.api.state import rulepack_path
    from detour_lab.rules.engine import load_rulepack
    from detour_lab.rules.profiles import DEMO_PROFILES

    limits = limits or ExperimentLimits()
    scenario = repository.get_scenario(scenario_id)
    project_id = repository.project_id_for_scenario(scenario_id)
    graph = repository.get_graph_version(scenario.base_graph_version_id)
    rulepack = load_rulepack(rulepack_path())
    if scenario.rulepack_id != rulepack.id or scenario.rulepack_hash != rulepack.content_hash:
        raise ExperimentRequestError(
            "scenario references a different rulepack than the bundled one; refusing to run an "
            "experiment against a mismatched ruleset",
            code="RULEPACK_MISMATCH",
            details={"scenario_rulepack_hash": scenario.rulepack_hash, "bundled": rulepack.content_hash},
        )

    profiles = {profile.id: profile for profile in DEMO_PROFILES}
    selected_profiles = sorted(set(profile_ids) or scenario.profile_ids)
    unknown_profiles = [p for p in selected_profiles if p not in profiles]
    if unknown_profiles:
        raise ExperimentRequestError(
            f"unknown mobility profile(s) {unknown_profiles}",
            code="PROFILE_NOT_FOUND",
            details={"unknown_profile_ids": unknown_profiles, "known_profile_ids": sorted(profiles)},
        )
    declared_phases = [p.id for p in scenario.ordered_phases()]
    unknown_phases = [p for p in phase_ids if p not in declared_phases]
    if unknown_phases:
        raise ExperimentRequestError(
            f"phase(s) {unknown_phases} are not declared in scenario {scenario_id!r}",
            code="INVALID_PHASE",
            details={"unknown_phase_ids": unknown_phases, "declared_phase_ids": declared_phases},
        )
    if not phase_ids:
        phase_ids = declared_phases

    runs = [repository.get_run(rid) for rid in baseline_run_ids] if baseline_run_ids else []

    batches: list[tuple[str | None, list[FaultDefinition]]] = []
    for suite_id in suite_ids:
        for phase_id in sorted(set(phase_ids) & set(declared_phases)):
            batches.append((suite_id, build_suite(suite_id=suite_id, scenario=scenario, phase_id=phase_id)))
    if faults:
        batches.append((None, list(faults)))

    total = len(batches)
    if total > limits.max_experiments_per_suite:
        raise ExperimentRequestError(
            f"{total} experiments requested but at most {limits.max_experiments_per_suite} are accepted "
            "per request",
            code="FAULT_LIMIT_EXCEEDED",
            details={"requested": total, "max_experiments_per_suite": limits.max_experiments_per_suite},
        )
    if not batches:
        raise ExperimentRequestError(
            "at least one fault suite or fault definition must be selected",
            code="INVALID_REQUEST",
            details={"known_suite_ids": None},
        )

    outcomes: list[ExperimentOutcome] = []
    for index, (suite_id, fault_set) in enumerate(batches):
        try:
            outcome = execute_experiment(
                project_id=project_id,
                graph=graph,
                scenario=scenario,
                rulepack=rulepack,
                profiles=profiles,
                faults=fault_set,
                phase_ids=list(phase_ids),
                profile_ids=selected_profiles,
                evaluation_instant=evaluation_instant,
                limits=limits,
                baseline_run_records=runs,
                suite_id=suite_id,
                clock=clock,
            )
        except FaultValidationError as exc:
            # An unrepresentable fault is recorded as an invalid experiment with
            # its reason, so a suite can never look "tested" when it was refused.
            # It is persisted like any other outcome: a refusal that disappeared
            # would be indistinguishable from a suite that was never requested.
            outcome = _invalid_outcome(
                faults=fault_set,
                suite_id=suite_id,
                error_stage="validation",
                code=exc.code,
                message=str(exc),
                details=exc.details,
                scenario=scenario,
                graph=graph,
                project_id=project_id,
                phase_ids=list(phase_ids),
                profile_ids=selected_profiles,
                evaluation_instant=evaluation_instant,
            )
        else:
            if outcome.suite_id != suite_id:
                outcome = outcome.model_copy(update={"suite_id": suite_id})
                outcome = outcome.model_copy(
                    update={"semantic_hash": semantic_hash(outcome.semantic_body())}
                )
        outcomes.append(outcome)

        if persist:
            repository.store_failure_experiment(
                experiment_id=outcome.experiment_id,
                scenario_id=scenario_id,
                scenario_revision=scenario.revision,
                phase_id=",".join(outcome.source.phase_ids),
                profile_id=",".join(outcome.source.profile_ids),
                engine_version=outcome.engine_version,
                status=outcome.status.value,
                input_hash=outcome.input_hash,
                semantic_hash=outcome.semantic_hash,
                duration_ms=outcome.duration_ms,
                payload=outcome.model_dump(mode="json"),
                created_at=outcome.created_at,
            )
        del index

    return outcomes


def _invalid_outcome(
    *,
    faults: list[FaultDefinition],
    suite_id: str | None,
    error_stage: str,
    code: str,
    message: str,
    details: dict[str, Any],
    scenario,
    graph,
    project_id: str,
    phase_ids: list[str],
    profile_ids: list[str],
    evaluation_instant: datetime,
) -> ExperimentOutcome:
    from detour_lab import ENGINE_VERSION
    from detour_lab.failure.model import ExecutionError, ExperimentLimits, ExperimentSource

    outcome = ExperimentOutcome(
        engine_version=ENGINE_VERSION,
        # A refused experiment still gets its own execution identity, so several
        # refusals in one request cannot collide on the primary key and two
        # different refusals are never conflated in history.
        experiment_id=f"fxp-{uuid.uuid4().hex[:12]}",
        created_at=utc_now_iso(),
        duration_ms=0.0,
        limits=ExperimentLimits(),
        status=ExperimentStatus.INVALID_EXPERIMENT,
        source=ExperimentSource(
            project_id=project_id,
            scenario_id=scenario.id,
            scenario_revision=scenario.revision,
            scenario_content_hash=scenario.content_hash,
            base_graph_version_id=graph.version.id,
            base_graph_hash=graph.version.content_hash,
            rulepack_id=scenario.rulepack_id,
            rulepack_version="",
            rulepack_hash=scenario.rulepack_hash,
            phase_ids=list(phase_ids),
            profile_ids=list(profile_ids),
            evaluation_instant=evaluation_instant.isoformat(),
        ),
        faults=faults,
        error=ExecutionError(stage=error_stage, code=code, message=message, details=details),
        suite_id=suite_id,
    )
    return outcome.model_copy(
        update={"semantic_hash": semantic_hash(outcome.semantic_body()), "input_hash": ""}
    )


# --------------------------------------------------------------------------- replay


class ReplayResult:
    """Outcome of re-executing a stored experiment from its own definition."""

    __slots__ = ("detail", "outcome", "reproduced", "stored")

    def __init__(self, stored, outcome: ExperimentOutcome, reproduced: bool, detail: str) -> None:
        self.stored = stored
        self.outcome = outcome
        self.reproduced = reproduced
        self.detail = detail


def replay_experiment(*, repository: Repository, experiment_id: str) -> ReplayResult:
    """Re-execute a stored experiment and compare semantic identities."""
    stored = repository.get_failure_experiment(experiment_id)
    recorded = ExperimentOutcome.model_validate(stored.payload)

    scenario = repository.get_scenario(stored.scenario_id)
    if scenario.revision != stored.scenario_revision:
        return ReplayResult(
            stored,
            recorded,
            False,
            (
                f"The scenario has since moved from revision {stored.scenario_revision} to "
                f"{scenario.revision}. This experiment stays bound to revision "
                f"{stored.scenario_revision} and is not re-analysed against the newer plan. Replay it "
                "against that historical revision to reproduce it."
            ),
        )
    if scenario.content_hash != recorded.source.scenario_content_hash:
        return ReplayResult(
            stored,
            recorded,
            False,
            (
                f"Scenario {scenario.id!r} content hash {scenario.content_hash} no longer matches the "
                f"hash recorded by this experiment ({recorded.source.scenario_content_hash}). The "
                "source revision is not the one that was tested."
            ),
        )

    from detour_lab.api.state import rulepack_path
    from detour_lab.rules.engine import load_rulepack
    from detour_lab.rules.profiles import DEMO_PROFILES

    rulepack = load_rulepack(rulepack_path())
    profiles = {profile.id: profile for profile in DEMO_PROFILES}
    graph = repository.get_graph_version(scenario.base_graph_version_id)
    instant = datetime.fromisoformat(recorded.source.evaluation_instant)

    try:
        replayed = execute_experiment(
            project_id=stored.project_id,
            graph=graph,
            scenario=scenario,
            rulepack=rulepack,
            profiles=profiles,
            faults=recorded.faults,
            phase_ids=recorded.source.phase_ids,
            profile_ids=recorded.source.profile_ids,
            evaluation_instant=instant,
            limits=recorded.limits,
        )
    except FaultValidationError as exc:
        return ReplayResult(
            stored,
            recorded,
            False,
            f"The stored fault definition no longer validates: {exc.code}: {exc}",
        )

    if replayed.semantic_hash != recorded.semantic_hash:
        return ReplayResult(
            stored,
            replayed,
            False,
            (
                f"Re-execution produced semantic hash {replayed.semantic_hash} but the stored record "
                f"holds {recorded.semantic_hash}. This is a reproducibility defect, not a modelling "
                "difference."
            ),
        )
    return ReplayResult(
        stored,
        replayed,
        True,
        (
            f"Re-executed from the stored fault definitions; the semantic hash reproduced exactly "
            f"({replayed.semantic_hash}). The replay has its own execution id "
            f"{replayed.experiment_id}."
        ),
    )


# --------------------------------------------------------------------------- history


def experiment_summary(outcome: ExperimentOutcome) -> ExperimentSummary:
    return ExperimentSummary(
        experiment_id=outcome.experiment_id,
        scenario_id=outcome.source.scenario_id,
        scenario_revision=outcome.source.scenario_revision,
        phase_ids=list(outcome.source.phase_ids),
        profile_ids=list(outcome.source.profile_ids),
        fault_kinds=[f.kind for f in outcome.faults],
        fault_labels=[f.label or f.kind.value for f in outcome.faults],
        status=outcome.status,
        observations=list(outcome.observations),
        input_hash=outcome.input_hash,
        semantic_hash=outcome.semantic_hash,
        created_at=outcome.created_at,
        suite_id=outcome.suite_id,
        error_code=outcome.error.code if outcome.error else None,
    )


def experiment_history(repository: Repository, scenario_id: str) -> list[ExperimentSummary]:
    return [
        experiment_summary(ExperimentOutcome.model_validate(stored.payload))
        for stored in repository.list_failure_experiments(scenario_id)
    ]


def summarise(experiments: Sequence[ExperimentOutcome]) -> RobustnessSummary:
    return summarise_robustness(outcomes=list(experiments), available_kinds=list(FaultKind))