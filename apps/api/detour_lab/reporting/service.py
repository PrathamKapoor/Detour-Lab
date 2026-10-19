"""Report assembly: authoritative collection, validation and delivery (Gate 6).

The service is the only place that reads stored artefacts and turns them into a
report. It performs no accessibility calculation of its own - every value in the
packet comes from a stored run, a stored optimisation search or a stored Failure
Lab experiment.

Selection rules enforced here
-----------------------------
* At least one stored analysis run is required. A packet with no analysed run
  would present invented results.
* Every selected run must belong to the requested scenario. Selecting a run from
  another scenario is refused rather than silently included.
* Phases are read from the runs; a phase that is declared but unanalysed is
  reported as ``NOT ANALYSED`` in the packet, never as a result.
* Optional sections (alternatives, experiments) are emitted as ``unavailable``
  with a reason when they were not selected. They never appear as an empty table
  that reads as "nothing to report".
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any

from detour_lab.analysis.run import run_analysis
from detour_lab.domain.contracts import MobilityProfile, RulePack, Scenario
from detour_lab.evidence.queue import derive_evidence_queue
from detour_lab.failure.compare import RobustnessSummary, summarise_robustness
from detour_lab.failure.model import ExperimentOutcome, ExperimentStatus, FaultKind
from detour_lab.graph.model import PedestrianGraph
from detour_lab.persistence.db import utc_now_iso
from detour_lab.persistence.repository import Repository, RunRecord, StoredOptimizationRun
from detour_lab.reporting.pdf import MAX_REPORT_PAGES, pdf_sha256, render_report_pdf, rendered_page_count
from detour_lab.reporting.report import (
    NetworkEdge,
    NetworkNode,
    ReportAlternativePlan,
    ReportCandidate,
    ReportDataError,
    ReportEvidenceIssue,
    ReportEvidenceRow,
    ReportExperiment,
    ReportFinding,
    ReportIdentity,
    ReportLimitations,
    ReportModification,
    ReportNetwork,
    ReportODRow,
    ReportScope,
    ReportSection12,
    SectionAvailability,
    build_review_report,
    validate_report_sources,
)
from detour_lab.rules.engine import load_rulepack
from detour_lab.scenarios.apply import build_phase_graph

__all__ = ["GeneratedReport", "generate_report"]


class GeneratedReport:
    """A generated packet plus the identities a caller needs to verify it."""

    __slots__ = ("page_count", "payload", "pdf_bytes", "pdf_digest", "record_id", "semantic_hash")

    def __init__(
        self,
        payload,
        pdf_bytes: bytes,
        page_count: int,
        pdf_digest: str,
        record_id: str,
    ) -> None:
        self.payload = payload
        self.pdf_bytes = pdf_bytes
        self.page_count = page_count
        self.pdf_digest = pdf_digest
        self.record_id = record_id
        self.semantic_hash = payload.semantic_hash()

    def runtime_block(self) -> dict[str, Any]:
        """Volatile metadata, kept out of the semantic payload."""
        return {
            "report_id": self.record_id,
            "pdf_sha256": self.pdf_digest,
            "pdf_bytes": len(self.pdf_bytes),
            "pdf_page_count": self.page_count,
            "generated_at": utc_now_iso(),
        }


def generate_report(
    *,
    repository: Repository,
    scenario_id: str,
    run_ids: list[str],
    search_ids: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    report_id: str | None = None,
    include_evidence_queue: bool = True,
    queue_phase_ids: list[str] | None = None,
    clock: Any = time.perf_counter,
) -> GeneratedReport:
    """Build, render and persist one review packet."""
    started = clock()
    search_ids = list(search_ids or [])
    experiment_ids = list(experiment_ids or [])

    validate_report_sources(
        scenario_id=scenario_id,
        run_ids=run_ids,
        search_ids=search_ids,
        experiment_ids=experiment_ids,
    )

    scenario = repository.get_scenario(scenario_id)
    project = repository.get_project(repository.project_id_for_scenario(scenario_id))
    graph: PedestrianGraph = repository.get_graph_version(scenario.base_graph_version_id)
    rulepack = load_rulepack_from_scenario(scenario)
    profiles = _profile_map()

    runs = [repository.get_run(run_id) for run_id in run_ids]
    for run in runs:
        if run.scenario_id != scenario_id:
            raise ReportDataError(
                f"run {run.run_id!r} belongs to scenario {run.scenario_id!r}, not {scenario_id!r}",
                code="RUN_SCENARIO_MISMATCH",
                details={"run_id": run.run_id, "run_scenario_id": run.scenario_id},
            )

    searches = [repository.get_optimization_run(search_id) for search_id in search_ids]
    for search in searches:
        if search.scenario_id != scenario_id:
            raise ReportDataError(
                f"optimisation search {search.search_id!r} belongs to scenario "
                f"{search.scenario_id!r}, not {scenario_id!r}",
                code="SEARCH_SCENARIO_MISMATCH",
                details={"search_id": search.search_id},
            )

    stored_experiments = [repository.get_failure_experiment(eid) for eid in experiment_ids]
    for experiment in stored_experiments:
        if experiment.scenario_id != scenario_id:
            raise ReportDataError(
                f"failure experiment {experiment.experiment_id!r} belongs to scenario "
                f"{experiment.scenario_id!r}, not {scenario_id!r}",
                code="EXPERIMENT_SCENARIO_MISMATCH",
                details={"experiment_id": experiment.experiment_id},
            )

    record_id = report_id or f"rpt-{uuid.uuid4().hex[:12]}"
    analysed_phases = sorted({run.phase_id for run in runs})
    analysed_profiles = sorted({run.profile_id for run in runs})

    identity = _identity(project_id=project.id, project=project, scenario=scenario, graph=graph, report_id=record_id)
    scope = _scope(
        scenario=scenario,
        graph=graph,
        rulepack=rulepack,
        profiles=profiles,
        runs=runs,
        analysed_phases=analysed_phases,
    )
    network = _network(
        graph=graph,
        scenario=scenario,
        phase_id=analysed_phases[0],
        profile_id=analysed_profiles[0],
        runs=runs,
    )
    modifications = _modifications(scenario=scenario, phases=analysed_phases)
    od_rows, findings, verdict_totals = _findings_and_od(runs=runs)
    executive_summary = _executive_summary(
        runs=runs,
        verdict_totals=verdict_totals,
        experiments=stored_experiments,
        evidence_issue_count=0,
    )
    evidence_rows = _evidence_rows(graph=graph, scope_phases=analysed_phases, scenario=scenario)
    evidence_issues, queue_count = _evidence_issues(
        repository=repository,
        graph=graph,
        scenario=scenario,
        rulepack=rulepack,
        profiles=profiles,
        phase_ids=queue_phase_ids or analysed_phases,
        include=include_evidence_queue,
    )
    executive_summary["evidence_issue_count"] = queue_count

    alternative_plans = [_alternative_plan(s) for s in searches]
    experiments = [_experiment(e) for e in stored_experiments]
    robustness = _robustness(experiments=[ExperimentOutcome.model_validate(e.payload) for e in stored_experiments])
    limitations = _limitations(scenario=scenario, analysed_phases=analysed_phases)

    availability = {
        "modifications": SectionAvailability(
            status="available" if modifications else "not_selected",
            reason="" if modifications else "No construction modification is declared for the reported phases.",
        ),
        "findings": SectionAvailability(status="available", reason=""),
        "evidence": SectionAvailability(status="available", reason=""),
        "alternative_plans": SectionAvailability(
            status="available" if alternative_plans else "not_selected",
            reason="" if alternative_plans else "No optimisation search was selected for this packet.",
        ),
        "experiments": SectionAvailability(
            status="available" if experiments else "not_selected",
            reason="" if experiments else "No Failure Lab experiment was selected for this packet.",
        ),
    }

    payload = build_review_report(
        report_id=record_id,
        identity=identity,
        scope=scope,
        network=network,
        modifications=modifications,
        executive_summary=executive_summary,
        od_rows=od_rows,
        findings=findings,
        evidence_rows=evidence_rows,
        evidence_issues=evidence_issues,
        alternative_plans=alternative_plans,
        experiments=experiments,
        robustness=robustness,
        limitations=limitations,
        human_review=ReportSection12(),
        section_availability=availability,
        selected_run_ids=[run.run_id for run in runs],
        selected_run_semantic_hashes=[run.semantic_hash for run in runs],
        selected_run_input_hashes=[run.input_hash for run in runs],
        selected_search_ids=[s.search_id for s in searches],
        selected_search_semantic_hashes=[s.semantic_hash for s in searches],
        selected_experiment_ids=[e.experiment_id for e in stored_experiments],
        selected_experiment_semantic_hashes=[e.semantic_hash for e in stored_experiments],
        selected_experiment_input_hashes=[e.input_hash for e in stored_experiments],
    )

    pdf = render_report_pdf(payload)
    page_count = rendered_page_count(pdf)
    if page_count > MAX_REPORT_PAGES:
        raise ReportDataError(
            f"the rendered packet has {page_count} pages, above the {MAX_REPORT_PAGES}-page bound. "
            "Narrow the selection instead of producing an unbounded document.",
            code="REPORT_TOO_LARGE",
            details={"page_count": page_count, "max_pages": MAX_REPORT_PAGES},
        )
    digest = pdf_sha256(pdf)

    repository.store_review_report(
        report_id=record_id,
        scenario_id=scenario_id,
        scenario_revision=scenario.revision,
        schema_version=payload.schema_version,
        generator_version=payload.generator_version,
        semantic_hash=payload.semantic_hash(),
        pdf_sha256=digest,
        pdf_bytes=len(pdf),
        pdf_page_count=page_count,
        selected_run_ids=[run.run_id for run in runs],
        selected_search_ids=[s.search_id for s in searches],
        selected_experiment_ids=[e.experiment_id for e in stored_experiments],
        payload=payload.model_dump(mode="json"),
        created_at=utc_now_iso(),
    )
    _ = started
    return GeneratedReport(payload=payload, pdf_bytes=pdf, page_count=page_count, pdf_digest=digest, record_id=record_id)


# --------------------------------------------------------------------------- helpers


def load_rulepack_from_scenario(scenario: Scenario) -> RulePack:
    """Load the bundled rulepack and refuse to report against a different one."""
    from detour_lab.api.state import rulepack_path

    rulepack = load_rulepack(rulepack_path())
    if scenario.rulepack_id != rulepack.id or scenario.rulepack_hash != rulepack.content_hash:
        raise ReportDataError(
            "the selected scenario references a different rulepack than the bundled one, so a packet "
            "would describe checks that are not the ones in force",
            code="RULEPACK_MISMATCH",
            details={
                "scenario_rulepack_id": scenario.rulepack_id,
                "scenario_rulepack_hash": scenario.rulepack_hash,
                "bundled_rulepack_id": rulepack.id,
                "bundled_rulepack_hash": rulepack.content_hash,
            },
        )
    return rulepack


def _profile_map() -> dict[str, MobilityProfile]:
    from detour_lab.rules.profiles import DEMO_PROFILES

    return {profile.id: profile for profile in DEMO_PROFILES}


def _identity(*, project_id, project, scenario: Scenario, graph: PedestrianGraph, report_id: str) -> ReportIdentity:
    source = graph.version.source
    return ReportIdentity(
        report_id=report_id,
        project_id=project_id,
        project_name=project.name,
        project_jurisdiction=project.jurisdiction,
        project_owner=project.owner,
        project_study_area=project.study_area_description,
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        scenario_revision=scenario.revision,
        scenario_content_hash=scenario.content_hash,
        parent_scenario_id=scenario.parent_scenario_id,
        dataset_notice=source.description,
        dataset_license=source.license,
        dataset_attribution=source.attribution,
        dataset_provenance_class=source.provenance_class.value,
    )


def _scope(
    *,
    scenario: Scenario,
    graph: PedestrianGraph,
    rulepack: RulePack,
    profiles: dict[str, MobilityProfile],
    runs: list[RunRecord],
    analysed_phases: list[str],
) -> ReportScope:
    synthetic = graph.version.source.provenance_class.value in {"synthetic", "synthetic_fixture"}
    return ReportScope(
        synthetic_dataset=synthetic,
        synthetic_dataset_reason=(
            f"Dataset provenance class is {graph.version.source.provenance_class.value!r}. Every "
            "geometry and measurement below is an authored demonstration value, not a field "
            "observation."
            if synthetic
            else f"Dataset provenance class is {graph.version.source.provenance_class.value!r}."
        ),
        coordinate_basis_kind=graph.version.basis.kind,
        coordinate_basis_note=graph.version.basis.crs_note,
        local_origin_label=graph.version.basis.local_origin_label,
        graph_version_id=graph.version.id,
        graph_content_hash=graph.version.content_hash,
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
        evidence_record_count=len(graph.evidence_registry.all_records()),
        rulepack_id=rulepack.id,
        rulepack_version=rulepack.version,
        rulepack_hash=rulepack.content_hash,
        rulepack_legal_applicability=rulepack.legal_applicability,
        rulepack_disclaimer=rulepack.disclaimer,
        rule_count=len(rulepack.rules),
        profiles=[
            {
                "profile_id": profile.id,
                "name": profile.name,
                "description": profile.description,
                "is_demo_profile": profile.is_demo_profile,
                "preference_weights": dict(profile.preference_weights),
                "notes": profile.notes,
            }
            for run in runs
            if (profile := profiles.get(run.profile_id)) is not None
        ],
        phases_analysed=[
            {
                "phase_id": run.phase_id,
                "order": next((p.order for p in scenario.ordered_phases() if p.id == run.phase_id), 0),
                "label": next((p.label for p in scenario.ordered_phases() if p.id == run.phase_id), ""),
                "closed_edge_ids": list(
                    scenario.phase_by_id(run.phase_id).closed_edge_ids if scenario.phase_by_id(run.phase_id) else []
                ),
                "temporary_edge_ids": list(
                    scenario.phase_by_id(run.phase_id).temporary_edge_ids if scenario.phase_by_id(run.phase_id) else []
                ),
            }
            for run in sorted(runs, key=lambda r: (r.phase_id, r.profile_id))
        ],
        phases_declared=[
            {
                "phase_id": p.id,
                "order": p.order,
                "label": p.label,
                "closed_edge_ids": list(p.closed_edge_ids),
                "temporary_edge_ids": list(p.temporary_edge_ids),
            }
            for p in scenario.ordered_phases()
        ],
        origin_destination_requirements=[od.model_dump(mode="json") for od in scenario.origins_destinations],
        evaluation_instants=sorted({run.evaluation_instant for run in runs}),
    )


def _network(
    *,
    graph: PedestrianGraph,
    scenario: Scenario,
    phase_id: str,
    profile_id: str,
    runs: list[RunRecord],
) -> ReportNetwork:
    phase_graph = build_phase_graph(graph, scenario, phase_id).graph
    matching = [r for r in runs if r.phase_id == phase_id and r.profile_id == profile_id]
    states: dict[str, str] = {}
    reasons: dict[str, list[str]] = {}
    for run in matching:
        for evaluation in run.result.edge_evaluations:
            states.setdefault(evaluation.edge_id, evaluation.state.value)
            reasons.setdefault(evaluation.edge_id, [rc.value for rc in evaluation.reason_codes])
    xs = [n.x for n in phase_graph.nodes] or [0.0]
    ys = [n.y for n in phase_graph.nodes] or [0.0]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    pad = 4.0
    return ReportNetwork(
        phase_id=phase_id,
        profile_id=profile_id,
        phase_graph_id=matching[0].result.phase_graph_id if matching else phase_graph.version.id,
        phase_graph_hash=matching[0].result.phase_graph_hash if matching else phase_graph.version.content_hash,
        nodes=[
            NetworkNode(id=n.id, x=n.x, y=n.y, node_type=n.node_type.value, name=n.name)
            for n in phase_graph.nodes
        ],
        edges=[
            NetworkEdge(
                id=e.id,
                u=e.u,
                v=e.v,
                length_m=e.length_m,
                edge_type=e.edge_type.value,
                closed_in_phase=e.id in phase_graph.closed_edge_ids,
                temporary=e.id.startswith("TMP::"),
                state=states.get(e.id),
                reason_codes=sorted(reasons.get(e.id, [])),
            )
            for e in phase_graph.edges
        ],
        unlinked_crossings=[
            c for c in phase_graph.unlinked_crossings() if not c["connected_via_shared_node"]
        ],
        bound_x=min_x - pad,
        bound_y=min_y - pad,
        bound_width=max(max_x - min_x + 2 * pad, 1.0),
        bound_height=max(max_y - min_y + 2 * pad, 1.0),
    )


def _modifications(*, scenario: Scenario, phases: list[str]) -> list[ReportModification]:
    out: list[ReportModification] = []
    for phase in scenario.ordered_phases():
        out.append(
            ReportModification(
                phase_id=phase.id,
                order=phase.order,
                label=phase.label,
                closed_edge_ids=list(phase.closed_edge_ids),
                temporary_edge_ids=list(phase.temporary_edge_ids),
                notes=phase.notes,
            )
        )
    return out


def _findings_and_od(runs: list[RunRecord]) -> tuple[list[ReportODRow], list[ReportFinding], dict[str, int]]:
    od_rows: list[ReportODRow] = []
    findings: list[ReportFinding] = []
    totals = {"PASS": 0, "FAIL": 0, "UNKNOWN": 0, "NOT_APPLICABLE": 0}
    for run in sorted(runs, key=lambda r: (r.phase_id, r.profile_id, r.run_id)):
        result = run.result
        for od in result.od_results:
            od_rows.append(
                ReportODRow(
                    profile_id=run.profile_id,
                    phase_id=run.phase_id,
                    pair_id=f"{od.origin_id}->{od.destination_id}",
                    origin_id=od.origin_id,
                    destination_id=od.destination_id,
                    confirmed_reachable=od.confirmed_reachable,
                    possibly_reachable=od.possibly_reachable,
                    confirmed_distance_m=od.confirmed_distance_m,
                    possible_distance_m=od.possible_distance_m,
                    confirmed_route_cost=od.confirmed_route_cost,
                    confirmed_path_edge_ids=list(od.confirmed_path_edge_ids),
                    possible_path_edge_ids=list(od.possible_path_edge_ids),
                    blocking_finding_ids=list(od.blocking_finding_ids),
                    relevant_finding_ids=list(od.relevant_finding_ids),
                    reason_codes=[rc.value for rc in od.reason_codes],
                )
            )
        for verdict in result.verdicts:
            totals[verdict.state.value] = totals.get(verdict.state.value, 0) + 1
        for edge_evaluation in result.edge_evaluations:
            for finding in edge_evaluation.findings:
                findings.append(
                    ReportFinding(
                        finding_id=finding.id,
                        element_id=finding.element_id,
                        element_kind=finding.element_kind,
                        state=finding.state.value,
                        severity=finding.severity,
                        reason_code=finding.reason_code.value,
                        rule_id=finding.rule_id,
                        rule_version=next(
                            (
                                v.rule_version
                                for v in result.verdicts
                                if v.rule_id == finding.rule_id and v.element_id == finding.element_id
                            ),
                            None,
                        ),
                        rulepack_version=result.rulepack_version,
                        profile_id=run.profile_id,
                        phase_id=run.phase_id,
                        explanation=finding.explanation,
                        evidence_ids=list(finding.evidence_ids),
                        attributes=[a.model_dump(mode="json") for a in finding.attributes],
                    )
                )
    findings.sort(key=lambda f: (f.phase_id, f.profile_id, f.element_id, f.finding_id))
    return od_rows, findings, totals


def _executive_summary(
    *,
    runs: list[RunRecord],
    verdict_totals: dict[str, int],
    experiments,
    evidence_issue_count: int,
) -> dict[str, Any]:
    latest_by_key: dict[tuple[str, str], RunRecord] = {}
    for run in runs:
        latest_by_key[(run.phase_id, run.profile_id)] = run
    pairs: dict[tuple[str, str, str], object] = {}
    for run in latest_by_key.values():
        for od in run.result.od_results:
            pairs[(run.phase_id, run.profile_id, f"{od.origin_id}->{od.destination_id}")] = od
    confirmed = sum(1 for od in pairs.values() if od.confirmed_reachable)
    possible_only = sum(1 for od in pairs.values() if od.possibly_reachable and not od.confirmed_reachable)
    unreachable = sum(1 for od in pairs.values() if not od.possibly_reachable)
    return {
        "run_count": len(runs),
        "pair_count": len(pairs),
        "confirmed_pairs": confirmed,
        "possible_only_pairs": possible_only,
        "unreachable_pairs": unreachable,
        "fail_verdicts": verdict_totals.get("FAIL", 0),
        "unknown_verdicts": verdict_totals.get("UNKNOWN", 0),
        "not_applicable_verdicts": verdict_totals.get("NOT_APPLICABLE", 0),
        "pass_verdicts": verdict_totals.get("PASS", 0),
        "evidence_issue_count": evidence_issue_count,
        "experiment_count": len(experiments),
        "headline": [
            f"{confirmed} of {len(pairs)} reported origin-destination pairs are model-confirmed.",
            f"{possible_only} pair(s) have a hypothetical route that assumes unresolved edges are "
            "usable. These are not confirmed accessibility.",
            f"{unreachable} pair(s) have no route in either graph.",
            f"{verdict_totals.get('UNKNOWN', 0)} rule evaluation(s) are UNKNOWN because evidence is "
            "unresolved. An unresolved condition is not a failure and is not a pass.",
            f"{verdict_totals.get('FAIL', 0)} rule evaluation(s) are known modelled failures.",
        ],
    }


def _evidence_rows(*, graph: PedestrianGraph, scope_phases: list[str], scenario: Scenario) -> list[ReportEvidenceRow]:
    records = {r.id: r for r in graph.evidence_registry.all_records()}
    for phase_id in scope_phases:
        phase_graph = build_phase_graph(graph, scenario, phase_id).graph
        for record in phase_graph.evidence_registry.all_records():
            records.setdefault(record.id, record)
    return [
        ReportEvidenceRow(
            evidence_id=record.id,
            element_id=record.element_id,
            field=record.field,
            value=record.value,
            unit=record.unit,
            method=record.method,
            source=record.source,
            observed_at=record.observed_at.isoformat() if record.observed_at else None,
            verification_status=record.verification_status.value,
            provenance_class=record.provenance_class.value,
            synthetic=record.synthetic,
            note=record.note,
        )
        for record in sorted(records.values(), key=lambda r: r.id)
    ]


def _evidence_issues(
    *,
    repository: Repository,
    graph: PedestrianGraph,
    scenario: Scenario,
    rulepack: RulePack,
    profiles: dict[str, MobilityProfile],
    phase_ids: list[str],
    include: bool,
) -> tuple[list[ReportEvidenceIssue], int]:
    if not include or not phase_ids:
        return [], 0
    instant = datetime.fromisoformat(_queue_instant(repository, scenario))
    results = {}
    for phase_id in phase_ids:
        for profile_id, profile in sorted(profiles.items()):
            results[(phase_id, profile_id)] = run_analysis(
                base_graph=graph,
                scenario=scenario,
                phase_id=phase_id,
                profile_id=profile_id,
                rulepack=rulepack,
                profile=profile,
                as_of=instant,
            )
    queue = derive_evidence_queue(
        graph=graph,
        scenario=scenario,
        rulepack=rulepack,
        results_by_phase_profile=results,
        phase_ids=phase_ids,
        profile_ids=sorted(profiles),
        as_of=instant,
        project_id=repository.project_id_for_scenario(scenario.id),
        dataset_notice=graph.version.source.description,
    )
    return (
        [
            ReportEvidenceIssue(
                issue_id=issue.issue_id,
                element_id=issue.element_id,
                attribute=issue.attribute,
                resolution_status=issue.resolution_status.value,
                status_label=issue.status_label,
                criticality=issue.criticality.value,
                rationale=list(issue.criticality_rationale),
                evidence_record_ids=list(issue.evidence_record_ids),
                investigation_target=issue.investigation_target,
            )
            for issue in queue.issues
        ],
        len(queue.issues),
    )


def _queue_instant(repository: Repository, scenario: Scenario) -> str:
    """Reuse the newest stored run's instant so freshness judgement is consistent."""
    runs = repository.list_runs(scenario.id)
    if runs:
        return max(r.evaluation_instant for r in runs)
    from detour_lab.api.v1.routers import DEMO_EVALUATION_INSTANT

    return DEMO_EVALUATION_INSTANT.isoformat()


def _alternative_plan(search: StoredOptimizationRun) -> ReportAlternativePlan:
    payload = search.payload
    domain = payload.get("domain", {})
    status = payload.get("status", {})
    from detour_lab.api.state import interventions_path
    from detour_lab.optimization.library import load_intervention_library

    library = load_intervention_library(interventions_path())
    return ReportAlternativePlan(
        search_id=search.search_id,
        scenario_revision=search.scenario_revision,
        phase_id=search.phase_id,
        profile_ids=list(payload.get("profile_ids", [])),
        evaluation_instant=search.evaluation_instant,
        solver_status=status.get("solver_status", "unknown"),
        exhaustive=bool(status.get("exhaustive", False)),
        limits_hit=list(status.get("limits_hit", [])),
        best_proposal_id=status.get("best_proposal_id"),
        domain_eligible_intervention_ids=list(domain.get("eligible_intervention_ids", [])),
        domain_evaluated_count=int(domain.get("evaluated_count", 0)),
        domain_combination_count=int(domain.get("domain_combination_count", 0)),
        truncated_by=list(domain.get("truncated_by", [])),
        scope_note=status.get("scope_note", ""),
        permitted_interventions=[
            {
                "id": i.id,
                "name": i.name,
                "allowed_ops": list(i.allowed_ops),
                "target_element_ids": list(i.target_element_ids),
                "constructible_in_field": i.constructible_in_field,
            }
            for i in library.interventions
        ],
        selected_candidates=[
            ReportCandidate(
                proposal_id=candidate["proposal"]["proposal_id"],
                classification=candidate["classification"],
                intervention_ids=list(candidate["intervention_ids"]),
                restored_all_profiles=list(candidate.get("restored_all_profiles", [])),
                requires_verification=bool(candidate["proposal"].get("requires_verification")),
                introduced_unknown_verdict_count=int(
                    candidate.get("introduced_unknown_verdict_count", 0)
                ),
                introduced_fail_verdict_count=int(candidate.get("introduced_fail_verdict_count", 0)),
                cost_currency=(candidate.get("cost") or {}).get("currency"),
                cost_nominal=(candidate.get("cost") or {}).get("nominal"),
                cost_maximum=(candidate.get("cost") or {}).get("maximum"),
                cost_unknown=bool((candidate.get("cost") or {}).get("unknown", True)),
                cost_note=" | ".join((candidate.get("cost") or {}).get("provenance_notes", []))
                or "Declared demonstration values only; no market source was consulted.",
                preview_scenario_hash=candidate.get("preview_scenario_hash", ""),
            )
            for candidate in payload.get("candidates", [])
        ],
    )


def _experiment(stored) -> ReportExperiment:
    outcome = ExperimentOutcome.model_validate(stored.payload)
    return ReportExperiment(
        experiment_id=outcome.experiment_id,
        status=outcome.status.value,
        scenario_revision=outcome.source.scenario_revision,
        phase_ids=list(outcome.source.phase_ids),
        profile_ids=list(outcome.source.profile_ids),
        evaluation_instant=outcome.source.evaluation_instant,
        faulted_evaluation_instant=outcome.faulted_evaluation_instant,
        fault_kinds=[f.kind.value for f in outcome.faults],
        fault_labels=[f.label or f.kind.value for f in outcome.faults],
        fault_semantic_hashes=[f.semantic_hash for f in outcome.faults],
        fault_targets=sorted({t for f in outcome.faults for t in f.target_ids}),
        observations=[o.value for o in outcome.observations],
        transitions=[
            {
                "profile_id": t.profile_id,
                "phase_id": t.phase_id,
                "pair_id": t.pair_id,
                "before_confirmed": t.before_confirmed,
                "before_possible": t.before_possible,
                "after_confirmed": t.after_confirmed,
                "after_possible": t.after_possible,
                "before_distance_m": t.before_distance_m,
                "after_distance_m": t.after_distance_m,
                "distance_delta_m": t.distance_delta_m,
                "observation": t.observation.value,
            }
            for t in outcome.transitions
        ],
        element_changes=[c.model_dump(mode="json") for c in outcome.element_changes],
        evidence_change_log=list(outcome.evidence_change_log),
        error=outcome.error.model_dump(mode="json") if outcome.error else None,
        semantic_hash=outcome.semantic_hash,
        input_hash=outcome.input_hash,
    )


def _robustness(experiments: list[ExperimentOutcome]) -> RobustnessSummary | None:
    completed = [e for e in experiments if e.status is ExperimentStatus.COMPLETED]
    if not completed:
        return None
    return summarise_robustness(outcomes=experiments, available_kinds=list(FaultKind))


def _limitations(*, scenario: Scenario, analysed_phases: list[str]) -> ReportLimitations:
    not_analysed = [p.id for p in scenario.ordered_phases() if p.id not in analysed_phases]
    return ReportLimitations(
        statements=[
            "This packet reports modelled checks from DEMO_RULEPACK_NOT_LEGAL. The rulepack has not "
            "been reviewed by an accessibility professional and is not a legal standard in any "
            "jurisdiction.",
            "Every geometry, measurement and observation in the bundled dataset is synthetic. None is "
            "a field measurement, and none has been independently verified.",
            "A model-confirmed route means every modelled check passed for the evidence available at "
            "the recorded evaluation instant. It does not guarantee physical safety.",
            "A possible-only route assumes unresolved edges are usable. It is not confirmed "
            "accessibility and must not be reported as such.",
            "No structural loading, hydrology, weather, material-performance or traffic simulation was "
            "performed. This software performs no physical simulation of any kind.",
            "Evidence freshness was judged at the recorded evaluation instant and changes with it.",
            "Failure Lab experiments report how the model behaved under explicitly modelled synthetic "
            "conditions. A surviving experiment is not evidence of real-world safety, and a ratio of "
            "passing experiments is not a probability of field failure.",
            "Demonstration costs are illustrative values authored in this repository. No market "
            "source was consulted and no currency conversion is performed.",
            "Results are specific to the selected phases, profiles and evaluation instants. They do "
            "not describe any other phase, profile or instant.",
        ],
        phases_not_analysed=not_analysed,
    )