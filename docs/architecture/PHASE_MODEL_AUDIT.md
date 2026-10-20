# Phase model audit (Gate 4, task 1)

Audit of the **existing** implementation, completed before any new phase behaviour was written.
Every answer below is taken from code, a running API or an existing test — never assumed.

## 1. Phase semantics as actually implemented

**Phases are independent graph snapshots, not cumulative transformations.**

`build_phase_graph()` (`apps/api/detour_lab/scenarios/apply.py:471`) rebuilds each phase from the
**base graph every time**:

```
phase_graph = apply_edits(base_graph, [edits that are not close_edge / activate_temporary_edge])
closed      = set(phase.closed_edge_ids)  ∪ {close_edge edits scoped to this phase}
active_tmp  = set(phase.temporary_edge_ids) ∪ {activate_temporary_edge edits scoped to this phase}
```

There is no "previous phase" input anywhere in that function.

### Answers to the audit questions

| # | Question | Answer, with evidence |
|---|---|---|
| 1 | Independent snapshots or cumulative? | **Independent.** `build_phase_graph` takes `(base_graph, scenario, phase_id)` — no prior phase. Verified on the seed: phase 2 re-declares `E_ME` because each phase states its own closure set. |
| 2 | Edits applied to base or previous phase? | **Base graph.** Line 495 applies the scenario's structural edits to `base_graph`. |
| 3 | How is reopening represented? | **There is no reopen operation.** Closures live in `Phase.closed_edge_ids`, which only a new scenario can change. Reopening is expressed as a branch scenario whose phase omits the edge (`DECISIONS.md` D-018). |
| 4 | Can a closure in one phase affect a later phase? | **Yes, but only by explicit construction.** A `close_edge` edit carrying no `phases` filter applies to *every* phase; carrying a `phases` list applies only to those. A closure declared on a phase object affects only that phase. |
| 5 | How are added edges identified across phases? | By `TemporaryEdge.id`. The edge is materialised once into the working graph and is *active* only in phases that list it (or whose edits activate it). |
| 6 | What happens when phase order changes? | Phase order is validated for uniqueness and the scenario's canonical body **sorts phases by `order`**, so a changed order changes the scenario `content_hash`. No structural edit is implied. |
| 7 | Does phase order affect graph identity? | **It changes scenario identity, not phase-graph identity.** `phase_graph_id` is `{base}~scenario:{id}~phase:{phase_id}` and the graph hash is computed over the materialised graph, which does not contain `order`. |
| 8 | Authoritative phase identifier | **`Phase.id`**, unique per scenario (enforced by `Scenario._validated`). |
| 9 | Does the API allow phase creation/editing? | **No — this is the gap.** Phases arrive only inside `ScenarioRequest` on `POST /projects/{id}/scenarios`; `PATCH` appends edits and cannot restructure phases. |
| 10 | Can every phase be evaluated independently? | **Yes**, already: `POST /scenarios/{id}/evaluate` takes an explicit `phase_id`. |
| 11 | Can results be retrieved by phase? | **Yes**, via `GET /scenarios/{id}/runs`, which returns `phase_id` and `scenario_revision` per run. |
| 12 | Can two branches be evaluated without shared state? | **Yes.** Branches are separate scenario rows with separate ids; evaluation reads one scenario. Covered by the Gate 3 branch tests. |
| 13 | How are revisions associated with runs? | `analysis_runs.scenario_revision` is written at evaluation time; every manifest carries it. |
| 14 | Can historical results be replayed? | **Yes.** `GET /runs/{id}` returns the stored payload; editing a scenario does not touch stored runs. |
| 15 | How are invalid phase references rejected? | `build_phase_graph` raises `GraphEditError(code="INVALID_INPUT")`, surfaced as HTTP 422. |

## 2. Ordering: `Phase.order` is the temporal authority

`Phase.order: int = Field(ge=0)`, unique within a scenario, and the scenario's canonical body sorts by
it. The seed uses logical ordinals (`phase-1` → order 1, `phase-2` → order 2) with
`boundary_convention = "logical_ordinal"`.

**No calendar exists in the domain.** There are no start/end dates; `start_ordinal`/`end_ordinal` are
optional logical markers. Gate 4 therefore implements an **ordered sequence**, never a Gantt chart,
and never invents construction dates.

Orders need not be contiguous, so ordering code must never assume `order == index` and must never
sort by phase id or label.

## 3. Observed phase behaviour on the seeded scenario

Profile A (`DEMO_PROFILE_MANUAL_WHEELCHAIR`), `evaluation_instant=2026-03-01T00:00:00Z`, revision 1:

| Phase | order | closed | temporary | phase-graph hash | W→Gate | W→Lib | E→Gate | E→Lib |
|---|---|---|---|---|---|---|---|---|
| phase-1 | 1 | E_ME | — | `sha256:380225338a98` | confirmed 58.0 m | confirmed 98.0 m | no route | possible only |
| phase-2 | 2 | E_ME, E_ES1 | TMP-EAST-BYPASS | `sha256:8ff379f928ef` | confirmed 58.0 m | confirmed 98.0 m | no route | possible only |

Two facts fall out of this that the UI must report rather than hide:

- the two phases have **different phase-graph hashes**, so phase state is content-addressed;
- phase 2 opens the temporary bypass, yet **E→Lib stays possible-only** — the bypass does not resolve
  the unresolved curb evidence at `N_EK`. A temporary connection is not automatically an improvement.

## 4. Gaps found (the only backend work Gate 4 needs)

1. **No authoritative read of a phase graph.** The frontend currently receives the *base* graph and
   toggles closures client-side from `Phase.closed_edge_ids`. Gate 4 forbids reconstructing graph
   state in the browser, so the materialised phase graph must be served by the backend.
2. **No timeline read.** Phase identity, order, label, declared closures and temporary connections are
   available only by loading the whole scenario, and "has this phase been analysed?" needs the run
   list. Without a timeline read the explorer must fan out N+1 requests.

Both are pure reads of already-authoritative state; neither introduces new domain behaviour.