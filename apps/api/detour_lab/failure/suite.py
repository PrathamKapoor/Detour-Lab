"""Explicitly defined, deterministic fault suites (G6-10).

A suite is **authored data**, not a generator: each entry names a fault kind and
the element ids it acts on, and the rationale for including it is written down.
Nothing here inspects the graph to invent a hazard, and nothing is chosen at
runtime by looking for "interesting" edges.

Why these conditions and not others
------------------------------------
The bundled demonstration graph has 12 edges, two construction phases, one
declared temporary connection, two demonstration mobility profiles and exactly
three unresolved attributes. The suites therefore target the conditions that
the seeded fixture was actually built to exercise:

``critical_closure``   closes an edge that carries a model-confirmed route
                       (the crossing segment ``E_K2``).
``incidental_closure`` closes an edge that carries no selected outcome, to show
                       a fault that changes nothing is reported honestly as
                       ``no_relevant_modelled_change`` rather than as success.
``evidence``           masks and contradicts one of the three genuinely
                       unresolved attributes.
``expiration``         moves the evaluation instant so the rulepack's own
                       freshness policy (declared for ``crossing_type``) is
                       actually exercised.
``connection_loss``    deactivates the declared temporary connection.
``unrepresentable``    is deliberately absent: see ``UNSUPPORTED_SCENARIOS``.

All referenced ids are validated against the live source state before execution.
A suite naming an id that does not exist in the selected scenario revision is
reported as an invalid experiment, never silently skipped and never presented
as successfully tested.
"""

from __future__ import annotations

from collections.abc import Sequence

from detour_lab.domain.contracts import Scenario
from detour_lab.failure.faults import FaultValidationError
from detour_lab.failure.model import FaultDefinition, FaultKind

__all__ = [
    "SUITES",
    "UNSUPPORTED_SCENARIOS",
    "available_suites",
    "build_suite",
]

#: Conditions deliberately NOT modelled, with the reason. A missing fault type is
#: never quietly presented as "tested and passed".
UNSUPPORTED_SCENARIOS: tuple[dict[str, str], ...] = (
    {
        "name": "Physical obstruction geometry or severity",
        "reason": (
            "The domain models edge availability only. There is no representation for an "
            "obstruction's footprint, clearance or severity, so only the availability change is "
            "modelled (fault kind path_obstruction)."
        ),
    },
    {
        "name": "Structural loading, hydrology, weather or material performance",
        "reason": (
            "These are civil-engineering simulations. DETOUR LAB performs no physical simulation of "
            "any kind and asserting otherwise would be a fabricated capability."
        ),
    },
    {
        "name": "Probability of real-world failure",
        "reason": (
            "The faults are deliberately authored stress conditions, not a sample from any "
            "population of hazards. No probability of field failure is computed or implied."
        ),
    },
)


def _f(
    kind: FaultKind,
    *,
    label: str,
    target_ids: Sequence[str] = (),
    phase_ids: Sequence[str] = (),
    observation=None,
    evaluation_instant: str | None = None,
    note: str = "",
) -> FaultDefinition:
    return FaultDefinition(
        kind=kind,
        label=label,
        target_ids=list(target_ids),
        phase_ids=list(phase_ids),
        observation=observation,
        evaluation_instant=evaluation_instant,
        note=note,
    )


def _observation(field: str, value, unit: str | None, note: str):
    from detour_lab.failure.model import FaultObservation

    return FaultObservation(field=field, value=value, unit=unit, note=note)


#: ``suite_id -> (title, description, factory)``. The factories read only their
#: declared arguments, so a suite is fully reproducible from its id and scenario.
SUITES: dict[str, tuple[str, str, object]] = {
    "critical_closure": (
        "Critical edge closure",
        "Closes one modelled edge that carries a model-confirmed origin-destination route, to test "
        "whether a confirmed conclusion survives an explicitly modelled loss of that segment.",
        lambda scenario, phase_id: [
            _f(
                FaultKind.EDGE_CLOSURE,
                label="Close the north crossing segment E_K2",
                target_ids=["E_K2"],
                phase_ids=[phase_id],
                note="E_K2 carries the only model-confirmed route from OD-W to OD-GATE in phase-1.",
            )
        ],
    ),
    "incidental_closure": (
        "Incidental edge closure",
        "Closes an edge that carries no selected origin-destination outcome, so a fault that changes "
        "nothing can be observed and reported honestly instead of being counted as resilience.",
        lambda scenario, phase_id: [
            _f(
                FaultKind.EDGE_CLOSURE,
                label="Close the rear link E_LINK",
                target_ids=["E_LINK"],
                phase_ids=[phase_id],
                note="E_LINK is not on any confirmed or possible route for a selected pair.",
            )
        ],
    ),
    "modelled_obstruction": (
        "Modelled obstruction on the crossing approach",
        "Applies the path_obstruction kind to the crossing approach edge, exercising the same domain "
        "operation as a closure while carrying an explicit obstruction label and its limitation.",
        lambda scenario, phase_id: [
            _f(
                FaultKind.PATH_OBSTRUCTION,
                label="Model an obstruction on crossing approach E_K1",
                target_ids=["E_K1"],
                phase_ids=[phase_id],
                note=(
                    "The domain models edge availability only. No obstruction geometry, footprint or "
                    "severity is simulated."
                ),
            )
        ],
    ),
    "evidence_gap": (
        "Missing critical observation",
        "Masks an existing width observation on an edge that carries a model-confirmed route, to "
        "observe whether a confirmed conclusion becomes unresolved rather than passing.",
        lambda scenario, phase_id: [
            _f(
                FaultKind.EVIDENCE_REMOVAL,
                label="Mask the recorded width of E_K1",
                target_ids=["E_K1"],
                phase_ids=[phase_id],
                observation=_observation(
                    "width_mm",
                    None,
                    None,
                    "The recorded width observation is masked inside the experiment's isolated "
                    "evidence context only.",
                ),
                note="The source evidence store is not modified.",
            )
        ],
    ),
    "conflicting_measurement": (
        "Conflicting measurements",
        "Introduces an explicitly synthetic, contradictory width observation so the real resolver "
        "decides the resulting condition.",
        lambda scenario, phase_id: [
            _f(
                FaultKind.CONFLICTING_OBSERVATION,
                label="Add a contradictory width record for E_K2",
                target_ids=["E_K2"],
                phase_ids=[phase_id],
                observation=_observation(
                    "width_mm",
                    1500,
                    "mm",
                    "Synthetic contradiction of the recorded 1100 mm width. No value is preferred.",
                ),
            )
        ],
    ),
    "unsupported_unit": (
        "Unsupported measurement unit",
        "Introduces an explicitly synthetic observation whose unit the rulepack does not accept, so "
        "the real unit-conversion layer rejects it.",
        lambda scenario, phase_id: [
            _f(
                FaultKind.UNSUPPORTED_UNIT_OBSERVATION,
                label="Add a width record for E_K1 in an undeclared unit",
                target_ids=["E_K1"],
                phase_ids=[phase_id],
                observation=_observation(
                    "width_mm",
                    1.1,
                    "handspan",
                    "Synthetic observation in a unit the rulepack does not declare for width_mm.",
                ),
            )
        ],
    ),
    "expired_evidence": (
        "Stale observation under its freshness policy",
        "Moves the evaluation instant past the rulepack's declared freshness policy for "
        "``crossing_type`` so the real expiration path runs. Timestamps are not rewritten.",
        lambda scenario, phase_id: [
            _f(
                FaultKind.EVIDENCE_EXPIRATION,
                label="Evaluate the crossing-type evidence five years after observation",
                target_ids=["N_K"],
                phase_ids=[phase_id],
                evaluation_instant="2032-01-05T09:00:00Z",
                note=(
                    "The seeded crossing_type observation is dated 2026-01-05 and the rulepack "
                    "declares a 1825-day freshness policy for that attribute. Only the evaluation "
                    "instant moves; the recorded timestamp is untouched."
                ),
            )
        ],
    ),
    "connection_loss": (
        "Temporary connection loss",
        "Deactivates the scenario's declared temporary connection in its phase, which is a genuine "
        "graph change rather than a rendering change.",
        lambda scenario, phase_id: [
            _f(
                FaultKind.TEMPORARY_CONNECTION_LOSS,
                label="Disable the modelled east bypass TMP-EAST-BYPASS",
                target_ids=["TMP-EAST-BYPASS"],
                phase_ids=[phase_id],
            )
        ],
    ),
    "multi_phase_isolation": (
        "Multi-phase closure (scope isolation)",
        "Closes an edge in phase-1 only, so the consequence for phase continuity can be observed "
        "while phase-2 remains an independent snapshot.",
        lambda scenario, phase_id: [
            _f(
                FaultKind.EDGE_CLOSURE,
                label="Close E_K2 in phase-1 only",
                target_ids=["E_K2"],
                phase_ids=["phase-1"],
                note="Applies to one phase only; other phases are evaluated unchanged.",
            )
        ],
    ),
}


#: Element ids each suite acts on, used for a purely structural readiness check
#: against the real graph. Listed separately so readiness never has to parse a
#: rendered label.
TARGETS_BY_SUITE: dict[str, tuple[str, ...]] = {
    "critical_closure": ("E_K2",),
    "incidental_closure": ("E_LINK",),
    "modelled_obstruction": ("E_K1",),
    "evidence_gap": ("E_K1",),
    "conflicting_measurement": ("E_K2",),
    "unsupported_unit": ("E_K1",),
    "expired_evidence": ("N_K",),
    "connection_loss": ("TMP-EAST-BYPASS",),
    "multi_phase_isolation": ("E_K2",),
}


def available_suites(scenario: Scenario, graph=None, phase_ids: Sequence[str] | None = None) -> list[dict]:
    """Suite catalogue with a per-scenario, per-phase readiness flag.

    Readiness is computed structurally against the live source graph so the
    interface can show which suites apply *to the phase the reviewer selected*.
    A suite that does not apply there is reported as unavailable - never as
    "passed", and never silently skipped.

    ``phase_ids`` restricts the evaluation to the selected phases. When it is
    omitted every declared phase is considered, because a suite that applies
    somewhere in the plan is not inapplicable to the plan as a whole.
    """
    from detour_lab.graph.model import PedestrianGraph

    graph = graph if isinstance(graph, PedestrianGraph) else None
    known_elements: set[str] = set()
    if graph is not None:
        known_elements = {e.id for e in graph.edges} | {n.id for n in graph.nodes}
    declared_temporary = {t.id for t in scenario.temporary_edges}

    declared = [p.id for p in scenario.ordered_phases()]
    evaluated = [p for p in (phase_ids or declared) if p is not None]

    catalog: list[dict] = []
    for suite_id, (title, description, _factory) in sorted(SUITES.items()):
        applicable_phases = [
            p for p in evaluated if _suite_applies(suite_id, scenario, p, known_elements)
        ]
        missing = [
            t
            for t in TARGETS_BY_SUITE.get(suite_id, ())
            if known_elements and t not in known_elements and t not in declared_temporary
        ]
        catalog.append(
            {
                "suite_id": suite_id,
                "title": title,
                "description": description,
                "target_element_ids": list(TARGETS_BY_SUITE.get(suite_id, ())),
                "evaluated_phase_ids": evaluated,
                "applicable_phase_ids": applicable_phases,
                "applicable": bool(applicable_phases),
                "unavailable_reason": (
                    ""
                    if applicable_phases
                    else (
                        f"Target element(s) {missing} are absent from this scenario's graph."
                        if missing
                        else (
                            "No phase in this selection satisfies the suite's precondition; "
                            f"the suite applies in {declared}."
                            if declared
                            else "The scenario declares no phases."
                        )
                    )
                ),
            }
        )
    return catalog


def build_suite(*, suite_id: str, scenario: Scenario, phase_id: str) -> list[FaultDefinition]:
    """Build one suite's fault list for a phase, or refuse to."""
    entry = SUITES.get(suite_id)
    if entry is None:
        raise FaultValidationError(
            f"unknown fault suite {suite_id!r}",
            code="UNKNOWN_SUITE",
            details={"known_suite_ids": sorted(SUITES)},
        )
    if scenario.phase_by_id(phase_id) is None:
        raise FaultValidationError(
            f"phase {phase_id!r} is not declared in scenario {scenario.id!r}",
            code="INVALID_PHASE",
            details={"declared_phase_ids": phases_of(scenario)},
        )
    faults = list(entry[2](scenario, phase_id))  # type: ignore[operator]
    if not faults:
        raise FaultValidationError(
            f"fault suite {suite_id!r} produced no applicable faults for phase {phase_id!r}",
            code="INVALID_SUITE",
            details={"suite_id": suite_id, "phase_id": phase_id},
        )
    return faults


def phases_of(scenario: Scenario) -> list[str]:
    return [p.id for p in scenario.ordered_phases()]


def _suite_applies(
    suite_id: str, scenario: Scenario, phase_id: str, known_elements: set[str] | None
) -> bool:
    """Whether a suite's targets exist in this phase's own graph.

    Structural only: it checks that the referenced edges, nodes and declared
    temporary connections exist. It never predicts an outcome and never inspects
    rule verdicts, so it cannot become a hidden second engine.
    """
    if suite_id == "multi_phase_isolation":
        # The isolation case is meaningful only when another declared phase
        # exists that the fault deliberately does not touch.
        return phase_id == "phase-1" and len(phases_of(scenario)) > 1
    if suite_id == "connection_loss":
        phase = scenario.phase_by_id(phase_id)
        return bool(phase and phase.temporary_edge_ids)
    targets = TARGETS_BY_SUITE.get(suite_id, ())
    if not targets:
        return True
    declared_temporary = {t.id for t in scenario.temporary_edges}
    for target in targets:
        if known_elements and target not in known_elements and target not in declared_temporary:
            return False
    return True