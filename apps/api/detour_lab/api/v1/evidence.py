"""Evidence-intelligence HTTP surface (Gate 6, G6-01..G6-04).

Conventions followed (identical to the existing v1 routers):

* prefix ``/api/v1``;
* the flat error envelope ``{code, message, details, request_id}``;
* a missing entity is ``404 NOT_FOUND``, an unusable request is ``400`` or
  ``422``, and a broken internal invariant is ``500`` with a stable code;
* request models forbid unknown fields, so a typo is rejected rather than
  silently ignored.

Every endpoint here reads authoritative state only. None of them computes a
verdict, and none of them writes evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from detour_lab.analysis.run import run_analysis
from detour_lab.api.state import rulepack_path
from detour_lab.api.v1.routers import _error, get_repository
from detour_lab.domain.enums import ReasonCode
from detour_lab.evidence.queue import derive_evidence_queue, explain_attribute, filter_issues
from detour_lab.persistence.repository import NotFoundError, Repository
from detour_lab.rules.engine import load_rulepack
from detour_lab.rules.profiles import DEMO_PROFILES

router = APIRouter(prefix="/api/v1", tags=["evidence"])

#: Bounded work: the queue recomputes analyses for the selection, so the number
#: of phases and profiles a single request may ask for is capped.
MAX_QUEUE_PHASES = 6
MAX_QUEUE_PROFILES = 2


class EvidenceExplainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(min_length=1, max_length=120)
    element_id: str = Field(min_length=1, max_length=160)
    field: str = Field(min_length=1, max_length=80)
    evaluation_instant: str | None = None


def _parse_instant(value: str | None) -> datetime:
    if value is None:
        from detour_lab.api.v1.routers import DEMO_EVALUATION_INSTANT

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
    if parsed.tzinfo is None:
        raise _error(
            400,
            "INVALID_INPUT",
            "evaluation_instant must include a timezone offset",
            {"field": "evaluation_instant"},
        )
    return parsed.astimezone(UTC)


def _selected(
    repository: Repository, scenario_id: str, phase_ids: list[str], profile_ids: list[str]
) -> tuple:
    scenario = repository.get_scenario(scenario_id)
    declared = [p.id for p in scenario.ordered_phases()]
    phases = phase_ids or declared
    unknown_phases = [p for p in phases if p not in declared]
    if unknown_phases:
        raise _error(
            400,
            "INVALID_PHASE",
            f"phase(s) {unknown_phases} are not declared in scenario {scenario_id!r}",
            {"unknown_phase_ids": unknown_phases, "declared_phase_ids": declared},
        )
    if len(phases) > MAX_QUEUE_PHASES:
        raise _error(
            400,
            "LIMIT_EXCEEDED",
            f"{len(phases)} phases requested but at most {MAX_QUEUE_PHASES} are accepted",
            {"requested": len(phases), "max_queue_phases": MAX_QUEUE_PHASES},
        )
    known_profiles = {p.id for p in DEMO_PROFILES}
    profiles = profile_ids or list(scenario.profile_ids)
    unknown_profiles = [p for p in profiles if p not in known_profiles]
    if unknown_profiles:
        raise _error(
            404,
            "PROFILE_NOT_FOUND",
            f"unknown mobility profile(s) {unknown_profiles}",
            {"unknown_profile_ids": unknown_profiles, "known_profile_ids": sorted(known_profiles)},
        )
    if len(profiles) > MAX_QUEUE_PROFILES:
        raise _error(
            400,
            "LIMIT_EXCEEDED",
            f"{len(profiles)} profiles requested but at most {MAX_QUEUE_PROFILES} are accepted",
            {"requested": len(profiles), "max_queue_profiles": MAX_QUEUE_PROFILES},
        )
    return scenario, sorted(phases), sorted(profiles)


def _csplit(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@router.get("/scenarios/{scenario_id}/evidence/queue")
def evidence_queue(
    scenario_id: str,
    phase_ids: str | None = Query(
        default=None,
        description="Comma-separated phase ids. Defaults to every declared phase.",
    ),
    profile_ids: str | None = Query(
        default=None, description="Comma-separated mobility profile ids. Defaults to the scenario's."
    ),
    statuses: str | None = Query(
        default=None,
        description=(
            "Comma-separated resolver status codes to keep, for example "
            "NO_EVIDENCE,CONFLICTING_EVIDENCE,UNSUPPORTED_UNIT,EVIDENCE_EXPIRED,"
            "EVIDENCE_NOT_VERIFIED."
        ),
    ),
    criticalities: str | None = Query(default=None, description="decision_blocking|decision_relevant|supporting"),
    element_id: str | None = Query(default=None, description="Restrict to one graph element."),
    field: str | None = Query(default=None, description="Restrict to one observation attribute."),
    repository: Repository = Depends(get_repository),
) -> dict:
    """Derive the deterministic evidence-verification queue for a selection."""
    try:
        scenario, phases, profiles = _selected(repository, scenario_id, _csplit(phase_ids), _csplit(profile_ids))
    except NotFoundError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc

    requested_statuses = _csplit(statuses)
    for status in requested_statuses:
        try:
            ReasonCode(status.upper())
        except ValueError as exc:
            raise _error(
                400,
                "INVALID_INPUT",
                f"{status!r} is not a known evidence resolution status code",
                {"known_statuses": sorted(r.value for r in ReasonCode)},
            ) from exc
    requested_criticalities = _csplit(criticalities)
    valid_criticalities = {"decision_blocking", "decision_relevant", "supporting"}
    unknown_criticalities = [c for c in requested_criticalities if c not in valid_criticalities]
    if unknown_criticalities:
        raise _error(
            400,
            "INVALID_INPUT",
            f"unknown criticality value(s) {unknown_criticalities}",
            {"known_criticalities": sorted(valid_criticalities)},
        )

    graph = repository.get_graph_version(scenario.base_graph_version_id)
    rulepack = load_rulepack(rulepack_path())
    if scenario.rulepack_id != rulepack.id or scenario.rulepack_hash != rulepack.content_hash:
        raise _error(
            409,
            "RULEPACK_MISMATCH",
            "this scenario references a different rulepack than the bundled one",
            {"scenario_rulepack_hash": scenario.rulepack_hash, "bundled": rulepack.content_hash},
        )
    profile_map = {p.id: p for p in DEMO_PROFILES}
    instant = _parse_instant(None)

    results = {}
    for phase_id in phases:
        for profile_id in profiles:
            try:
                results[(phase_id, profile_id)] = run_analysis(
                    base_graph=graph,
                    scenario=scenario,
                    phase_id=phase_id,
                    profile_id=profile_id,
                    rulepack=rulepack,
                    profile=profile_map[profile_id],
                    as_of=instant,
                )
            except Exception as exc:
                raise _error(
                    500,
                    "ANALYSIS_FAILED",
                    f"the authoritative engine could not evaluate phase {phase_id!r} for profile "
                    f"{profile_id!r}: {type(exc).__name__}: {exc}",
                    {"phase_id": phase_id, "profile_id": profile_id},
                ) from exc

    queue = derive_evidence_queue(
        graph=graph,
        scenario=scenario,
        rulepack=rulepack,
        results_by_phase_profile=results,
        phase_ids=phases,
        profile_ids=profiles,
        as_of=instant,
        project_id=repository.project_id_for_scenario(scenario_id),
        dataset_notice=graph.version.source.description,
        additional_phases=[p.id for p in scenario.ordered_phases()],
    )

    issues = filter_issues(
        queue.issues,
        statuses=requested_statuses or None,
        profile_ids=_csplit(profile_ids) or None,
        phase_ids=_csplit(phase_ids) or None,
        criticalities=requested_criticalities or None,
    )
    if element_id:
        issues = [i for i in issues if i.element_id == element_id]
    if field:
        issues = [i for i in issues if i.attribute == field]

    filtered_counts_status: dict[str, int] = {}
    filtered_counts_criticality: dict[str, int] = {}
    for issue in issues:
        filtered_counts_status[issue.resolution_status.value] = (
            filtered_counts_status.get(issue.resolution_status.value, 0) + 1
        )
        filtered_counts_criticality[issue.criticality] = (
            filtered_counts_criticality.get(issue.criticality, 0) + 1
        )

    return {
        **queue.model_dump(mode="json"),
        "issues": [issue.model_dump(mode="json") for issue in issues],
        "counts_by_status": dict(sorted(filtered_counts_status.items())),
        "counts_by_criticality": dict(sorted(filtered_counts_criticality.items())),
        "returned_issues": len(issues),
        "filters_applied": {
            "statuses": requested_statuses,
            "criticalities": requested_criticalities,
            "element_id": element_id or "",
            "field": field or "",
        },
    }


@router.get("/scenarios/{scenario_id}/evidence/issues/{issue_id}")
def evidence_issue(
    scenario_id: str,
    issue_id: str,
    phase_ids: str | None = Query(default=None),
    profile_ids: str | None = Query(default=None),
    repository: Repository = Depends(get_repository),
) -> dict:
    """One queue entry, including the resolver's own explanation."""
    try:
        scenario, phases, profiles = _selected(repository, scenario_id, _csplit(phase_ids), _csplit(profile_ids))
    except NotFoundError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc

    graph = repository.get_graph_version(scenario.base_graph_version_id)
    rulepack = load_rulepack(rulepack_path())
    profile_map = {p.id: p for p in DEMO_PROFILES}
    instant = _parse_instant(None)
    results = {
        (phase_id, profile_id): run_analysis(
            base_graph=graph,
            scenario=scenario,
            phase_id=phase_id,
            profile_id=profile_id,
            rulepack=rulepack,
            profile=profile_map[profile_id],
            as_of=instant,
        )
        for phase_id in phases
        for profile_id in profiles
    }
    queue = derive_evidence_queue(
        graph=graph,
        scenario=scenario,
        rulepack=rulepack,
        results_by_phase_profile=results,
        phase_ids=phases,
        profile_ids=profiles,
        as_of=instant,
        project_id=repository.project_id_for_scenario(scenario_id),
        dataset_notice=graph.version.source.description,
        additional_phases=[p.id for p in scenario.ordered_phases()],
    )
    match = next((i for i in queue.issues if i.issue_id == issue_id), None)
    if match is None:
        raise _error(
            404,
            "ISSUE_NOT_FOUND",
            f"evidence issue {issue_id!r} is not in the queue for this selection",
            {
                "issue_id": issue_id,
                "available_issue_ids": [i.issue_id for i in queue.issues],
                "note": (
                    "The queue is derived, so an issue only exists while the resolver still reports "
                    "the attribute unresolved for the selected phases and profiles."
                ),
            },
        )
    explanation = explain_attribute(
        graph=graph,
        rulepack=rulepack,
        element_id=match.element_id,
        field=match.attribute,
        as_of=instant,
    )
    return {
        "issue": match.model_dump(mode="json"),
        "resolver_explanation": explanation.model_dump(mode="json"),
    }


@router.post("/scenarios/{scenario_id}/evidence/attributes/explain")
@router.post("/projects/{project_id}/evidence/attributes/explain")
def explain_project_attribute(
    project_id: str,
    payload: EvidenceExplainRequest,
    repository: Repository = Depends(get_repository),
) -> dict:
    """Explain why one attribute is unresolved, using a project's latest graph.

    No value is selected, no claim is preferred and nothing is averaged: the
    response reports what the authoritative resolver decided and why.
    """
    try:
        graph = repository.get_latest_graph_version(project_id)
    except NotFoundError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc
    rulepack = load_rulepack(rulepack_path())
    try:
        report = explain_attribute(
            graph=graph,
            rulepack=rulepack,
            element_id=payload.element_id,
            field=payload.field,
            as_of=_parse_instant(payload.evaluation_instant),
        )
    except KeyError as exc:
        raise _error(
            400,
            "UNKNOWN_ATTRIBUTE",
            f"the rulepack {rulepack.id!r} does not declare attribute {payload.field!r}",
            {"field": payload.field, "known_attributes": sorted(rulepack.attributes)},
        ) from exc
    return report.model_dump(mode="json")