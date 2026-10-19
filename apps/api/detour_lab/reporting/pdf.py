"""PDF document assembly for the review packet (Gate 6, G6-13/G6-14).

This module turns a fully populated
:class:`~detour_lab.reporting.report.ReviewReport` into a multi-page document
using :mod:`detour_lab.reporting.layout` primitives. It contains **no**
accessibility, routing or evidence logic - only the order in which an already
computed result is presented.

Section order follows the Gate 6 specification exactly: identification,
executive summary, scope, network, modifications, findings, evidence provenance,
alternatives, failure experiments, limitations, reproducibility, human review.
"""

from __future__ import annotations

import hashlib
import io
import re

from reportlab import rl_config

#: Must be set before the first canvas is created. Fixes the PDF document id and
#: the creation date, so identical payloads render to byte-identical files.
rl_config.invariant = 1

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)

from detour_lab.reporting.layout import (  # noqa: E402
    NetworkPlan,
    build_styles,
    ensure_fonts,
    font_note,
    kv_table,
    p,
    table,
)
from detour_lab.reporting.report import ReviewReport  # noqa: E402

__all__ = ["MAX_REPORT_PAGES", "pdf_sha256", "render_report_pdf", "rendered_page_count"]

#: A packet that would exceed this is refused rather than rendered into an
#: unreadable or unbounded document.
MAX_REPORT_PAGES = 200

_FULL_WIDTH = A4[0] - 32 * mm


def render_report_pdf(report: ReviewReport) -> bytes:
    """Render the deterministic PDF for one report model."""
    ensure_fonts()
    styles = build_styles()

    buffer = io.BytesIO()
    document = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title="DETOUR LAB review packet - planning analysis, not certified",
        author="DETOUR LAB",
        subject="Modelled pedestrian detour planning analysis",
        creator=report.generator_version,
    )
    document.addPageTemplates(
        [
            PageTemplate(
                id="packet",
                frames=[
                    Frame(
                        document.leftMargin,
                        document.bottomMargin,
                        document.width,
                        document.height,
                        id="body",
                        leftPadding=0,
                        rightPadding=0,
                        topPadding=0,
                        bottomPadding=0,
                    )
                ],
                onPage=_decorate(report),
            )
        ]
    )
    document.build(_build_story(report, styles))
    return buffer.getvalue()


def _decorate(report: ReviewReport):
    def draw(canvas, doc) -> None:
        canvas.saveState()
        styles = build_styles()
        canvas.setFont(styles["small"].fontName, 7.2)
        canvas.setFillColor(colors.HexColor("#55636f"))
        canvas.drawString(16 * mm, 10 * mm, "DETOUR LAB - planning analysis, not certified")
        canvas.drawRightString(
            A4[0] - 16 * mm,
            10 * mm,
            f"{report.identity.scenario_id} rev {report.identity.scenario_revision} | page {doc.page}",
        )
        canvas.setStrokeColor(colors.HexColor("#c3ced9"))
        canvas.setLineWidth(0.4)
        canvas.line(16 * mm, 13 * mm, A4[0] - 16 * mm, 13 * mm)
        canvas.restoreState()

    return draw


def rendered_page_count(pdf_bytes: bytes) -> int:
    """Page count read from the page tree; no second PDF library required."""
    counts = [int(m) for m in re.findall(rb"/Type\s*/Pages[^>]*?/Count\s+(\d+)", pdf_bytes)]
    if counts:
        return max(counts)
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf_bytes)) or 1


def pdf_sha256(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


# --------------------------------------------------------------------------- sections


def _availability_note(report: ReviewReport, key: str, styles) -> Paragraph | None:
    entry = report.section_availability.get(key)
    if entry is None or entry.status == "available":
        return None
    label = {
        "unavailable": "Section unavailable",
        "not_selected": "Section not selected",
    }.get(entry.status, entry.status)
    return p(f"{label}: {entry.reason}", styles["note"])


def _build_story(report: ReviewReport, styles: dict) -> list:
    story: list = []

    # -- 1. Cover and identification -----------------------------------------
    story.append(p("DETOUR LAB", styles["title"]))
    story.append(p("Pedestrian detour planning and model verification", styles["subtitle"]))
    story.append(Spacer(1, 5))
    story.append(p(report.disclaimer, styles["warn"]))
    story.append(Spacer(1, 9))

    identity = report.identity
    story.append(p("1. Report identification", styles["h1"]))
    story.append(
        kv_table(
            [
                ("Report identifier", report.identity.report_id or "(assigned at generation)"),
                ("Report type", "Engineering review packet - modelled analysis"),
                ("Project", f"{identity.project_name} [{identity.project_id}]"),
                ("Jurisdiction", identity.project_jurisdiction),
                ("Owner", identity.project_owner),
                ("Study area", identity.project_study_area or "(not described)"),
                ("Scenario", f"{identity.scenario_id} (revision {identity.scenario_revision})"),
                ("Scenario content hash", identity.scenario_content_hash),
                ("Parent scenario", identity.parent_scenario_id or "(none - root revision)"),
                (
                    "Analysed phases",
                    ", ".join(ph["phase_id"] for ph in report.scope.phases_analysed) or "(none selected)",
                ),
                (
                    "Analysed profiles",
                    ", ".join(pr["profile_id"] for pr in report.scope.profiles) or "(none selected)",
                ),
                ("Dataset provenance", identity.dataset_provenance_class),
                ("Dataset licence", identity.dataset_license),
                ("Dataset attribution", identity.dataset_attribution or "(none recorded)"),
                ("Report schema", f"{report.schema_version} (generator {report.generator_version})"),
                ("Engine version", report.engine_version),
            ],
            styles,
        )
    )
    story.append(Spacer(1, 5))
    story.append(p(identity.dataset_notice, styles["note"]))
    if font_note():
        story.append(p(f"Font note: {font_note()}", styles["small"]))
    story.append(PageBreak())

    # -- 2. Executive summary -------------------------------------------------
    story.append(p("2. Executive summary", styles["h1"]))
    story.extend(_executive_summary(report, styles))

    # -- 3. Study scope -------------------------------------------------------
    story.append(p("3. Study scope", styles["h1"]))
    story.extend(_scope(report, styles))

    # -- 4. Network overview --------------------------------------------------
    story.append(p("4. Network overview", styles["h1"]))
    story.extend(_network(report, styles))

    # -- 5. Construction modifications ---------------------------------------
    story.append(p("5. Construction modifications", styles["h1"]))
    story.extend(_modifications(report, styles))

    # -- 6. Accessibility findings -------------------------------------------
    story.append(p("6. Accessibility findings", styles["h1"]))
    story.extend(_findings(report, styles))

    # -- 7. Evidence provenance ----------------------------------------------
    story.append(p("7. Evidence provenance", styles["h1"]))
    story.extend(_evidence(report, styles))

    # -- 8. Alternative-plan analysis ----------------------------------------
    story.append(p("8. Alternative-plan analysis", styles["h1"]))
    story.extend(_alternatives(report, styles))

    # -- 9. Failure Lab experiments ------------------------------------------
    story.append(p("9. Failure Lab experiments", styles["h1"]))
    story.extend(_experiments(report, styles))

    # -- 10. Assumptions and limitations -------------------------------------
    story.append(p("10. Assumptions and limitations", styles["h1"]))
    story.extend(_limitations(report, styles))

    # -- 11. Reproducibility manifest ----------------------------------------
    story.append(p("11. Reproducibility manifest", styles["h1"]))
    story.extend(_reproducibility(report, styles))

    # -- 12. Human review -----------------------------------------------------
    story.append(p("12. Human review", styles["h1"]))
    story.extend(_human_review(report, styles))

    return story


def _executive_summary(report: ReviewReport, styles) -> list:
    summary = report.executive_summary
    story = [
        p(report.not_certified_note, styles["note"]),
        kv_table(
            [
                ("Runs included in this packet", summary.get("run_count", 0)),
                ("Origin-destination pairs reported", summary.get("pair_count", 0)),
                ("Pairs model-confirmed", summary.get("confirmed_pairs", 0)),
                ("Pairs possible-only (hypothetical)", summary.get("possible_only_pairs", 0)),
                ("Pairs with no route at all", summary.get("unreachable_pairs", 0)),
                ("Known modelled violations", summary.get("fail_verdicts", 0)),
                ("Unresolved conditions (UNKNOWN)", summary.get("unknown_verdicts", 0)),
                ("Not-applicable rules", summary.get("not_applicable_verdicts", 0)),
                ("Unresolved attributes in the evidence queue", summary.get("evidence_issue_count", 0)),
                ("Failure Lab experiments included", summary.get("experiment_count", 0)),
            ],
            styles,
        ),
    ]
    for line in summary.get("headline", []):
        story.append(Spacer(1, 3))
        story.append(p(f"- {line}", styles["body"]))
    story.append(Spacer(1, 4))
    story.append(
        p(
            "Scope limitation: this packet reports only the phases, profiles and runs selected for "
            "it. Any phase not listed in section 3 was not analysed here and no result is claimed "
            "for it.",
            styles["note"],
        )
    )
    return story


def _scope(report: ReviewReport, styles) -> list:
    scope = report.scope
    story = [
        kv_table(
            [
                ("Dataset is synthetic", "YES" if scope.synthetic_dataset else "NO"),
                ("Synthetic-data basis", scope.synthetic_dataset_reason),
                ("Coordinate basis", scope.coordinate_basis_kind),
                ("Local origin label", scope.local_origin_label or "(not applicable)"),
                ("Coordinate note", scope.coordinate_basis_note),
                ("Graph version", scope.graph_version_id),
                ("Graph content hash", scope.graph_content_hash),
                ("Network size", f"{scope.node_count} nodes, {scope.edge_count} edges"),
                ("Evidence records", scope.evidence_record_count),
                ("Ruleset", f"{scope.rulepack_id} v{scope.rulepack_version}"),
                ("Ruleset content hash", scope.rulepack_hash),
                ("Ruleset legal applicability", scope.rulepack_legal_applicability),
                ("Rule count", scope.rule_count),
            ],
            styles,
        ),
        Spacer(1, 5),
        p(scope.rulepack_disclaimer, styles["note"]),
    ]

    story.append(p("Evaluated mobility profiles", styles["h2"]))
    story.append(
        table(
            [
                [p(h, styles["small"]) for h in ("Profile ID", "Name", "Demonstration only", "Preference weights")]
                + [
                    [
                        p(pr.get("profile_id", ""), styles["small"]),
                        p(pr.get("name", ""), styles["small"]),
                        p("yes" if pr.get("is_demo_profile") else "no", styles["small"]),
                        p(
                            ", ".join(f"{k}={v}" for k, v in sorted(pr.get("preference_weights", {}).items()))
                            or "none declared",
                            styles["small"],
                        ),
                    ]
                    for pr in scope.profiles
                ],
            ],
            [42 * mm, 50 * mm, 32 * mm, 42 * mm],
        )
    )

    story.append(p("Phases analysed and declared", styles["h2"]))
    rows = [[p(h, styles["small"]) for h in ("Phase", "Order", "Analysed", "Closed edges", "Temporary connections")]]
    declared = {ph["phase_id"]: ph for ph in scope.phases_declared}
    for phase in scope.phases_analysed:
        source = declared.get(phase["phase_id"], phase)
        rows.append(
            [
                p(phase["phase_id"], styles["small"]),
                p(phase.get("order", ""), styles["small"]),
                p("yes", styles["small"]),
                p(", ".join(phase.get("closed_edge_ids", [])) or "none", styles["small"]),
                p(", ".join(phase.get("temporary_edge_ids", [])) or "none", styles["small"]),
            ]
        )
    for phase_id in sorted(set(declared) - {ph["phase_id"] for ph in scope.phases_analysed}):
        source = declared[phase_id]
        rows.append(
            [
                p(phase_id, styles["small"]),
                p(source.get("order", ""), styles["small"]),
                p("NOT ANALYSED", styles["small"]),
                p(", ".join(source.get("closed_edge_ids", [])) or "none", styles["small"]),
                p(", ".join(source.get("temporary_edge_ids", [])) or "none", styles["small"]),
            ]
        )
    story.append(table(rows, [28 * mm, 14 * mm, 26 * mm, 50 * mm, 48 * mm]))

    story.append(p("Origin and destination requirements", styles["h2"]))
    story.append(
        table(
            [[p(h, styles["small"]) for h in ("ID", "Label", "Node", "Kind", "Essential", "Priority", "Weight source")]]
            + [
                [
                    p(od.get("id", ""), styles["small"]),
                    p(od.get("label", ""), styles["small"]),
                    p(od.get("node_id", ""), styles["small"]),
                    p(od.get("kind", ""), styles["small"]),
                    p("yes" if od.get("essential") else "no", styles["small"]),
                    p(od.get("priority", ""), styles["small"]),
                    p(od.get("weight_source", ""), styles["small"]),
                ]
                for od in scope.origin_destination_requirements
            ],
            [24 * mm, 38 * mm, 20 * mm, 20 * mm, 18 * mm, 16 * mm, 30 * mm],
        )
    )
    story.append(Spacer(1, 3))
    story.append(
        p(
            "An origin or destination is bound to a graph node identifier. A coordinate near a footway "
            "is never treated as a connection.",
            styles["small"],
        )
    )
    return story


def _network(report: ReviewReport, styles) -> list:
    network = report.network
    story = [
        p(
            f"Reported state: phase {network.phase_id}, profile {network.profile_id}, phase graph "
            f"{network.phase_graph_id} (content hash {network.phase_graph_hash}).",
            styles["body"],
        ),
        NetworkPlan(network),
        Spacer(1, 3),
        p(
            "Plan key: solid heavy line = model-confirmed edge; solid medium = unresolved (UNKNOWN); "
            "dashed = closed in this phase (X) or temporary connection (T). Edge identifiers are "
            "printed on the plan and repeated in the table below, so the figure is never the only "
            "source of the information.",
            styles["small"],
        ),
        Spacer(1, 5),
    ]
    story.append(
        table(
            [
                [
                    p(h, styles["small"])
                    for h in ("Edge", "From", "To", "Type", "Length (m)", "State", "Closed", "Temporary")
                ]
            ]
            + [
                [
                    p(e.id, styles["small"]),
                    p(e.u, styles["small"]),
                    p(e.v, styles["small"]),
                    p(e.edge_type, styles["small"]),
                    p(f"{e.length_m:g}", styles["small"]),
                    p(e.state or "not evaluated", styles["small"]),
                    p("yes" if e.closed_in_phase else "no", styles["small"]),
                    p("yes" if e.temporary else "no", styles["small"]),
                ]
                for e in network.edges
            ],
            [34 * mm, 20 * mm, 20 * mm, 26 * mm, 20 * mm, 26 * mm, 16 * mm, 18 * mm],
        )
    )
    if network.unlinked_crossings:
        story.append(p("Geometric crossings that are not graph connections", styles["h2"]))
        story.append(
            table(
                [[p(h, styles["small"]) for h in ("Edges", "Point (x, y)", "Connected via shared node")]]
                + [
                    [
                        p(" / ".join(c.get("edge_ids", [])), styles["small"]),
                        p(f"({c['point'][0]:g}, {c['point'][1]:g})", styles["small"]),
                        p("yes" if c.get("connected_via_shared_node") else "NO - not connected", styles["small"]),
                    ]
                    for c in network.unlinked_crossings
                ],
                [56 * mm, 44 * mm, 66 * mm],
            )
        )
        story.append(Spacer(1, 3))
        story.append(
            p(
                "A crossing in space is not a connection. Connectivity exists only through a shared "
                "node identifier.",
                styles["small"],
            )
        )
    return story


def _modifications(report: ReviewReport, styles) -> list:
    note = _availability_note(report, "modifications", styles)
    story = [note] if note else []
    if not report.modifications:
        if not story:
            story.append(p("No construction modification is declared for the reported phases.", styles["body"]))
        return story
    rows = [[p(h, styles["small"]) for h in ("Phase", "Order", "Label", "Closed edges", "Temporary connections", "Notes")]]
    for modification in report.modifications:
        rows.append(
            [
                p(modification.phase_id, styles["small"]),
                p(modification.order, styles["small"]),
                p(modification.label, styles["small"]),
                p(", ".join(modification.closed_edge_ids) or "none", styles["small"]),
                p(", ".join(modification.temporary_edge_ids) or "none", styles["small"]),
                p(modification.notes, styles["small"]),
            ]
        )
    story.append(table(rows, [22 * mm, 12 * mm, 36 * mm, 32 * mm, 32 * mm, 32 * mm]))
    story.append(Spacer(1, 3))
    story.append(
        p(
            "A modelled temporary connection is a modelled path only. Field constructibility has not "
            "been confirmed by any engineer, and no such confirmation is implied here.",
            styles["note"],
        )
    )
    return story


def _findings(report: ReviewReport, styles) -> list:
    note = _availability_note(report, "findings", styles)
    story = [note] if note else []
    if not report.od_rows and not report.findings:
        if not story:
            story.append(p("No analysis run was selected, so no findings are reported.", styles["note"]))
        return story

    story.append(p("Origin-destination outcomes", styles["h2"]))
    rows = [
        [
            p(h, styles["small"])
            for h in ("Profile", "Phase", "Pair", "Confirmed", "Possible only", "Confirmed distance (m)", "Reason codes")
        ]
    ]
    for row in report.od_rows:
        rows.append(
            [
                p(row.profile_id, styles["small"]),
                p(row.phase_id, styles["small"]),
                p(row.pair_id, styles["small"]),
                p("YES" if row.confirmed_reachable else "no", styles["small"]),
                p("hypothetical" if row.possibly_reachable and not row.confirmed_reachable else ("yes" if row.possibly_reachable else "no"), styles["small"]),
                p(f"{row.confirmed_distance_m:g}" if row.confirmed_distance_m is not None else "not established", styles["small"]),
                p(", ".join(row.reason_codes), styles["small"]),
            ]
        )
    story.append(table(rows, [38 * mm, 18 * mm, 26 * mm, 18 * mm, 22 * mm, 28 * mm, 16 * mm]))
    story.append(Spacer(1, 3))
    story.append(p(report.od_rows[0].distance_note, styles["small"]))

    unknown_rows = [r for r in report.od_rows if r.possibly_reachable and not r.confirmed_reachable]
    if unknown_rows:
        story.append(Spacer(1, 4))
        story.append(
            p(
                f"{len(unknown_rows)} pair(s) are possible-only. A possible-only route assumes "
                "unresolved edges are usable. It is NOT confirmed accessibility and must not be "
                "reported to anyone as such.",
                styles["note"],
            )
        )

    story.append(p("Rule evaluations producing a finding", styles["h2"]))
    finding_rows = [
        [
            p(h, styles["small"])
            for h in ("Element", "Kind", "State", "Severity", "Reason", "Rule", "Profile", "Explanation")
        ]
    ]
    for finding in report.findings:
        finding_rows.append(
            [
                p(finding.element_id, styles["small"]),
                p(finding.element_kind, styles["small"]),
                p(finding.state, styles["small"]),
                p(finding.severity, styles["small"]),
                p(finding.reason_code, styles["small"]),
                p(finding.rule_id or "(phase closure)", styles["small"]),
                p(finding.profile_id, styles["small"]),
                p(finding.explanation, styles["small"]),
            ]
        )
    story.append(table(finding_rows, [26 * mm, 14 * mm, 20 * mm, 18 * mm, 32 * mm, 34 * mm, 38 * mm, 60 * mm]))

    detail = [f for f in report.findings if f.evidence_ids]
    if detail:
        story.append(p("Evidence referenced by findings", styles["h2"]))
        story.append(
            table(
                [[p(h, styles["small"]) for h in ("Element", "Rule", "State", "Reason code", "Evidence record IDs")]]
                + [
                    [
                        p(f.element_id, styles["small"]),
                        p(f.rule_id or "-", styles["small"]),
                        p(f.state, styles["small"]),
                        p(f.reason_code, styles["small"]),
                        p(", ".join(f.evidence_ids), styles["small"]),
                    ]
                    for f in detail
                ],
                [30 * mm, 38 * mm, 22 * mm, 36 * mm, 40 * mm],
            )
        )
    return story


def _evidence(report: ReviewReport, styles) -> list:
    note = _availability_note(report, "evidence", styles)
    story = [note] if note else []
    story.append(p("Recorded observations", styles["h2"]))
    if not report.evidence_rows:
        story.append(p("No observation is recorded for the reported elements.", styles["body"]))
    else:
        story.append(
            table(
                [
                    [
                        p(h, styles["small"])
                        for h in ("Record", "Element", "Field", "Value", "Unit", "Observed", "Verification", "Provenance", "Synthetic")
                    ]
                ]
                + [
                    [
                        p(r.evidence_id, styles["small"]),
                        p(r.element_id, styles["small"]),
                        p(r.field, styles["small"]),
                        p(r.value if r.value is not None else "(none)", styles["small"]),
                        p(r.unit or "(none)", styles["small"]),
                        p(r.observed_at or "(no timestamp)", styles["small"]),
                        p(r.verification_status, styles["small"]),
                        p(r.provenance_class, styles["small"]),
                        p("yes" if r.synthetic else "no", styles["small"]),
                    ]
                    for r in report.evidence_rows
                ],
                [34 * mm, 22 * mm, 24 * mm, 20 * mm, 14 * mm, 30 * mm, 22 * mm, 22 * mm, 14 * mm],
            )
        )
        story.append(Spacer(1, 3))
        story.append(
            p(
                "Values and units are reproduced exactly as the source reported them. Where a unit "
                "conversion was applied, the original value and unit remain visible above; the "
                "conversion is recorded in the canonical manifest, not by overwriting the record.",
                styles["small"],
            )
        )

    story.append(p("Unresolved attributes (verification queue)", styles["h2"]))
    if not report.evidence_issues:
        story.append(
            p(
                "No unresolved attribute was derived for the selected phases and profiles, or no "
                "queue was requested for this packet.",
                styles["body"],
            )
        )
    else:
        rows = [[p(h, styles["small"]) for h in ("Issue", "Element", "Attribute", "Status", "Decision relevance", "What to check")]]
        for issue in report.evidence_issues:
            rows.append(
                [
                    p(issue.issue_id, styles["small"]),
                    p(issue.element_id, styles["small"]),
                    p(issue.attribute, styles["small"]),
                    p(issue.resolution_status, styles["small"]),
                    p(issue.criticality, styles["small"]),
                    p(issue.investigation_target, styles["small"]),
                ]
            )
        story.append(table(rows, [26 * mm, 24 * mm, 24 * mm, 30 * mm, 30 * mm, 32 * mm]))
        for issue in report.evidence_issues:
            if issue.rationale:
                story.append(Spacer(1, 2))
                story.append(p(f"{issue.issue_id}: {issue.status_label}", styles["small"]))
                for line in issue.rationale:
                    story.append(p(f"- {line}", styles["small"]))
    story.append(Spacer(1, 4))
    story.append(
        p(
            "An unresolved attribute means the model cannot determine the condition. It is not a "
            "physical defect and it is not proof that the element is unusable. No observation was "
            "verified, re-measured or resolved in producing this packet.",
            styles["note"],
        )
    )
    return story


def _alternatives(report: ReviewReport, styles) -> list:
    note = _availability_note(report, "alternative_plans", styles)
    story = [note] if note else []
    if not report.alternative_plans:
        if not story:
            story.append(
                p(
                    "No optimisation search was selected for this packet. No alternative plan is "
                    "described, and no cost appears anywhere in it.",
                    styles["note"],
                )
            )
        return story

    for plan in report.alternative_plans:
        story.append(p(f"Search {plan.search_id}", styles["h2"]))
        story.append(
            kv_table(
                [
                    ("Source scenario revision", plan.scenario_revision),
                    ("Phase", plan.phase_id),
                    ("Profiles", ", ".join(plan.profile_ids)),
                    ("Evaluation instant", plan.evaluation_instant),
                    ("Solver status", plan.solver_status),
                    ("Search exhaustive over the enumerated domain", "yes" if plan.exhaustive else "NO"),
                    ("Limits hit", ", ".join(plan.limits_hit) or "none"),
                    ("Truncated by", ", ".join(plan.truncated_by) or "nothing"),
                    ("Subsets evaluated", f"{plan.domain_evaluated_count} of {plan.domain_combination_count}"),
                    ("Eligible interventions", ", ".join(plan.domain_eligible_intervention_ids) or "none"),
                    ("Best proposal", plan.best_proposal_id or "none"),
                    ("Search semantic hash", plan.semantic_hash),
                ],
                styles,
            )
        )
        story.append(Spacer(1, 3))
        story.append(p(plan.scope_note, styles["small"]))
        story.append(p(plan.budget_note, styles["small"]))

        if plan.permitted_interventions:
            story.append(p("Permitted interventions considered", styles["h2"]))
            story.append(
                table(
                    [[p(h, styles["small"]) for h in ("Intervention", "Name", "Operations", "Targets", "Field constructible")]]
                    + [
                        [
                            p(i.get("id", ""), styles["small"]),
                            p(i.get("name", ""), styles["small"]),
                            p(", ".join(i.get("allowed_ops", [])), styles["small"]),
                            p(", ".join(i.get("target_element_ids", [])), styles["small"]),
                            p("confirmed" if i.get("constructible_in_field") else "NOT confirmed", styles["small"]),
                        ]
                        for i in plan.permitted_interventions
                    ],
                    [40 * mm, 44 * mm, 34 * mm, 28 * mm, 20 * mm],
                )
            )

        story.append(p("Selected candidates", styles["h2"]))
        if not plan.selected_candidates:
            story.append(p("No candidate from this search is included in this packet.", styles["body"]))
        else:
            story.append(
                table(
                    [
                        [
                            p(h, styles["small"])
                            for h in (
                                "Proposal",
                                "Classification",
                                "Interventions",
                                "Restored (all profiles)",
                                "New unknowns",
                                "New violations",
                                "Nominal cost",
                                "Maximum cost",
                                "Cost unknown",
                            )
                        ]
                    ]
                    + [
                        [
                            p(c.proposal_id, styles["small"]),
                            p(c.classification, styles["small"]),
                            p(", ".join(c.intervention_ids), styles["small"]),
                            p(", ".join(c.restored_all_profiles) or "none", styles["small"]),
                            p(c.introduced_unknown_verdict_count, styles["small"]),
                            p(c.introduced_fail_verdict_count, styles["small"]),
                            p(f"{c.cost_nominal:g} {c.cost_currency}" if c.cost_nominal is not None else "NOT ESTIMATED", styles["small"]),
                            p(f"{c.cost_maximum:g} {c.cost_currency}" if c.cost_maximum is not None else "NOT ESTIMATED", styles["small"]),
                            p("yes" if c.cost_unknown else "no", styles["small"]),
                        ]
                        for c in plan.selected_candidates
                    ],
                    [30 * mm, 30 * mm, 34 * mm, 40 * mm, 16 * mm, 18 * mm, 24 * mm, 24 * mm, 16 * mm],
                )
            )
        story.append(Spacer(1, 3))
        story.append(
            p(
                "A candidate classified as requiring verification is NOT a certified solution. An "
                "absent cost is reported as not estimated and is never treated as zero.",
                styles["note"],
            )
        )
    return story


def _experiments(report: ReviewReport, styles) -> list:
    note = _availability_note(report, "experiments", styles)
    story = [note] if note else []
    if not report.experiments:
        if not story:
            story.append(
                p(
                    "No Failure Lab experiment was selected for this packet. No adversarial testing "
                    "result appears anywhere in it.",
                    styles["note"],
                )
            )
        return story

    for experiment in report.experiments:
        story.append(
            KeepTogether(
                [
                    p(f"Experiment {experiment.experiment_id}", styles["h2"]),
                    kv_table(
                        [
                            ("Execution status", experiment.status),
                            ("Source scenario revision", experiment.scenario_revision),
                            ("Phases evaluated", ", ".join(experiment.phase_ids)),
                            ("Profiles evaluated", ", ".join(experiment.profile_ids)),
                            ("Baseline evaluation instant", experiment.evaluation_instant),
                            ("Faulted evaluation instant", experiment.faulted_evaluation_instant),
                            ("Fault kinds", ", ".join(experiment.fault_kinds)),
                            ("Fault targets", ", ".join(experiment.fault_targets) or "none named"),
                            ("Input hash", experiment.input_hash),
                            ("Semantic hash", experiment.semantic_hash),
                        ],
                        styles,
                    ),
                ]
            )
        )
        story.append(Spacer(1, 3))
        for label in experiment.fault_labels:
            story.append(p(f"Fault: {label}", styles["body"]))
        if experiment.evidence_change_log:
            story.append(p("Evidence changes applied inside the isolated context", styles["h2"]))
            story.append(
                table(
                    [[p(h, styles["small"]) for h in ("Fault", "Action", "Element(s)", "Detail")]]
                    + [
                        [
                            p(change.get("fault_id", ""), styles["small"]),
                            p(change.get("action", ""), styles["small"]),
                            p(", ".join(change.get("element_ids", [])) or change.get("field", ""), styles["small"]),
                            p(
                                ", ".join(
                                    f"{k}={v}" for k, v in change.items() if k in ("masked_evidence_ids", "injected_evidence_id", "value", "unit", "from", "to")
                                ),
                                styles["small"],
                            ),
                        ]
                        for change in experiment.evidence_change_log
                    ],
                    [34 * mm, 30 * mm, 36 * mm, 66 * mm],
                )
            )

        story.append(p("Changed accessibility outcomes", styles["h2"]))
        rows = [
            [
                p(h, styles["small"])
                for h in ("Profile", "Phase", "Pair", "Before", "After", "Observed consequence", "Distance before", "Distance after")
            ]
        ]
        for transition in experiment.transitions:
            rows.append(
                [
                    p(transition.get("profile_id", ""), styles["small"]),
                    p(transition.get("phase_id", ""), styles["small"]),
                    p(transition.get("pair_id", ""), styles["small"]),
                    p(_reach(transition.get("before_confirmed"), transition.get("before_possible")), styles["small"]),
                    p(_reach(transition.get("after_confirmed"), transition.get("after_possible")), styles["small"]),
                    p(transition.get("observation", ""), styles["small"]),
                    p(_distance(transition.get("before_distance_m")), styles["small"]),
                    p(_distance(transition.get("after_distance_m")), styles["small"]),
                ]
            )
        story.append(table(rows, [34 * mm, 16 * mm, 24 * mm, 18 * mm, 18 * mm, 40 * mm, 20 * mm, 20 * mm]))

        if experiment.element_changes:
            story.append(p("Graph elements that changed", styles["h2"]))
            story.append(
                table(
                    [[p(h, styles["small"]) for h in ("Element", "Change", "Before", "After", "Explanation")]]
                    + [
                        [
                            p(change.get("element_id", ""), styles["small"]),
                            p(change.get("change", ""), styles["small"]),
                            p(change.get("before_state") or "-", styles["small"]),
                            p(change.get("after_state") or "-", styles["small"]),
                            p(change.get("detail", ""), styles["small"]),
                        ]
                        for change in experiment.element_changes
                    ],
                    [30 * mm, 26 * mm, 22 * mm, 22 * mm, 66 * mm],
                )
            )
        if experiment.error:
            story.append(p("Execution problem (software outcome, not a modelled failure)", styles["h2"]))
            story.append(
                kv_table(
                    [
                        ("Stage", experiment.error.get("stage", "")),
                        ("Code", experiment.error.get("code", "")),
                        ("Message", experiment.error.get("message", "")),
                    ],
                    styles,
                )
            )
            story.append(Spacer(1, 3))
            story.append(
                p(
                    "An experiment that could not be executed is evidence about this software, not "
                    "about the proposed construction plan. No modelled network failure is claimed.",
                    styles["note"],
                )
            )

    robustness = report.robustness
    if robustness:
        story.append(p("Robustness summary across the selected experiments", styles["h2"]))
        story.append(
            kv_table(
                [
                    ("Experiments requested", robustness.get("experiments_requested", 0)),
                    ("Completed", robustness.get("experiments_completed", 0)),
                    ("Partially completed", robustness.get("experiments_partially_completed", 0)),
                    ("Invalid", robustness.get("experiments_invalid", 0)),
                    ("Execution failed", robustness.get("experiments_failed", 0)),
                    ("Fault kinds tested", ", ".join(robustness.get("fault_kinds_tested", []))),
                    ("Fault kinds NOT tested", ", ".join(robustness.get("fault_kinds_untested", [])) or "none"),
                    ("Origin-destination comparisons", robustness.get("pairs_evaluated", 0)),
                    ("Retained model-confirmed connectivity", robustness.get("pairs_retaining_confirmed", 0)),
                    ("Lost model-confirmed connectivity", robustness.get("pairs_losing_confirmed", 0)),
                    ("Became possible-only", robustness.get("pairs_becoming_possible_only", 0)),
                    ("Became disconnected", robustness.get("pairs_becoming_disconnected", 0)),
                    ("New known violations", robustness.get("pairs_with_new_known_violation", 0)),
                    ("New unresolved conditions", robustness.get("pairs_with_new_unknown_condition", 0)),
                ],
                styles,
            )
        )
        story.append(Spacer(1, 4))
        story.append(p(robustness.get("denominator_note", ""), styles["note"]))
        story.append(p(robustness.get("interpretation_note", ""), styles["note"]))
    return story


def _reach(confirmed, possible) -> str:
    if confirmed:
        return "confirmed"
    if possible:
        return "possible-only"
    return "no route"


def _distance(value) -> str:
    if value is None:
        return "not established"
    try:
        return f"{float(value):g} m"
    except (TypeError, ValueError):  # pragma: no cover - stored values are numeric
        return "not established"


def _limitations(report: ReviewReport, styles) -> list:
    limitations = report.limitations
    story = [
        table(
            [
                [p(h, styles["small"]) for h in ("Question", "Answer")],
                [p("Is the dataset synthetic?", styles["small"]), p("YES", styles["small"])],
                [
                    p("Are the rules a legally reviewed standard?", styles["small"]),
                    p("NO - DEMO_RULEPACK_NOT_LEGAL, applicability unverified", styles["small"]),
                ],
                [
                    p("Were field measurements independently verified?", styles["small"]),
                    p("NO", styles["small"]),
                ],
                [p("Was legal applicability reviewed?", styles["small"]), p("NO", styles["small"])],
                [
                    p("Was physical safety established?", styles["small"]),
                    p("NO. No physical simulation of any kind was performed.", styles["small"]),
                ],
                [
                    p("Did a manual accessibility review take place?", styles["small"]),
                    p("NO", styles["small"]),
                ],
                [
                    p("Are construction costs available?", styles["small"]),
                    p("NO - demonstration values only; absent costs are not estimated", styles["small"]),
                ],
            ],
            [78 * mm, 88 * mm],
        ),
        Spacer(1, 5),
        p("Limitations that apply to every statement in this packet", styles["h2"]),
    ]
    for statement in limitations.statements:
        story.append(p(f"- {statement}", styles["body"]))
    if limitations.phases_not_analysed:
        story.append(Spacer(1, 3))
        story.append(
            p(
                "Phases declared in this scenario but not analysed here: "
                + ", ".join(limitations.phases_not_analysed)
                + ". No result is claimed for them in this packet.",
                styles["note"],
            )
        )
    return story


def _reproducibility(report: ReviewReport, styles) -> list:
    repro = report.reproducibility
    story = [
        kv_table(
            [
                ("Report schema version", repro.report_schema_version),
                ("Report generator version", repro.report_generator_version),
                ("Engine version", repro.engine_version),
                ("Scenario", f"{repro.scenario_id} revision {repro.scenario_revision}"),
                ("Scenario content hash", repro.scenario_content_hash),
                ("Base graph version", repro.base_graph_version_id),
                ("Base graph content hash", repro.base_graph_hash),
                ("Ruleset", f"{repro.rulepack_id} v{repro.rulepack_version}"),
                ("Ruleset content hash", repro.rulepack_hash),
                ("Canonical report JSON size (bytes)", repro.canonical_json_bytes),
            ],
            styles,
        ),
        Spacer(1, 4),
        p("Selected source runs", styles["h2"]),
        p("Run IDs: " + (", ".join(repro.selected_run_ids) or "none"), styles["small"]),
        p("Run semantic hashes: " + (", ".join(repro.selected_run_semantic_hashes) or "none"), styles["small"]),
        p("Run input hashes: " + (", ".join(repro.selected_run_input_hashes) or "none"), styles["small"]),
    ]
    if repro.selected_search_ids:
        story.append(Spacer(1, 3))
        story.append(p("Selected optimisation searches", styles["h2"]))
        p("Search IDs: " + ", ".join(repro.selected_search_ids), styles["small"])
        p("Search semantic hashes: " + ", ".join(repro.selected_search_semantic_hashes), styles["small"])
    if repro.selected_experiment_ids:
        story.append(Spacer(1, 3))
        story.append(p("Selected Failure Lab experiments", styles["h2"]))
        p("Experiment IDs: " + ", ".join(repro.selected_experiment_ids), styles["small"])
        p("Experiment semantic hashes: " + ", ".join(repro.selected_experiment_semantic_hashes), styles["small"])
        p("Experiment input hashes: " + ", ".join(repro.selected_experiment_input_hashes), styles["small"])

    story.append(Spacer(1, 4))
    story.append(p("Steps to reproduce these conclusions", styles["h2"]))
    for index, step in enumerate(repro.reproduction_steps, start=1):
        story.append(p(f"{index}. {step}", styles["body"]))
    return story


def _human_review(report: ReviewReport, styles) -> list:
    review = report.human_review
    story = [
        p(review.note, styles["note"]),
        kv_table(
            [
                ("Review recorded", "yes" if review.review_recorded else "NO"),
                ("Reviewer", review.reviewer or "(none)"),
                ("Reviewer role", review.reviewer_role or "(none)"),
                ("Reviewed at", review.reviewed_at or "(none)"),
                ("Approval status", review.approval_status),
            ],
            styles,
        ),
        Spacer(1, 4),
        p(
            "No signature, seal, stamp, professional registration or approval is present in this "
            "packet, and none may be added by this software. A blank or absent review section is a "
            "true statement: no human reviewer has signed off on this analysis.",
            styles["note"],
        ),
    ]
    return story