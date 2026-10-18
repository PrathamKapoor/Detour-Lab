# DETOUR LAB — Final Product Requirements Document

**Version:** 1.0 (implementation baseline)  
**Date:** 18 October 2026  
**Decision:** CONDITIONAL GO  
**Product class:** Pre-construction pedestrian detour decision-support and model verification  
**Release targets:** R0 Demonstrable MVP; R1 Differentiated hackathon release; R2 Research pilot  
**Status:** Approved product direction; engineering estimates, standards applicability and validation remain subject to project-specific review.

---

## 1. Executive product evaluation

**Verdict:** Build DETOUR LAB, but not the entire previously proposed municipal platform. A credible win depends on a narrow, complete and falsifiable workflow rather than a long feature count.

| Assessment dimension | Score /10 | Basis |
|---|---:|---|
| Problem relevance | 9 | Construction can disconnect important pedestrian routes, especially for users with access needs. |
| Technical depth | 9 | Directed graphs, evidence-aware rule evaluation, discrete candidate intervention search and reproducibility. |
| Demo potential | 10 | Visible before/after, unexpected failure and ranked fixes in one live sequence. |
| Differentiation | 8 | Prospective construction approval workflow is distinct from routine navigation, but its component methods are prior art. |
| Feasibility — prior full vision | 4 | Computer vision, multi-jurisdiction certification, GIS, field apps and optimizers are too much at once. |
| Feasibility — defined R0/R1 | 8 | Bounded geographical area, enumerated interventions, two profiles and explicit acceptance tests. |
| Research potential | 9 | Testable hypotheses on false-safe decisions, phase omissions and inspection prioritization. |

Scores are editorial estimates, **not** measured outcomes or guarantees of winning.

### 1.1 What has been corrected

1. **Compliance claims:** Outputs say *Pass in modeled checks*, *Fail*, *Unknown* or *Not applicable*. They are not statutory certification, professional approval or proof of physical safety.
2. **Scope:** One small study area, two bounded mobility profiles, one demonstrative ruleset, and candidate interventions from a predefined editable library.
3. **AI boundary:** No generative AI in the authoritative rules, route-feasibility or solver pathway. Image intelligence is advisory and deferred.
4. **Uncertainty:** A missing, conflicting or stale critical measurement cannot silently pass a rule.
5. **Optimization claims:** Only call a result *optimal* when the search domain and algorithm actually establish it. Otherwise say *best candidate found*, *no modeled feasible candidate*, or *search incomplete*.
6. **Field data:** An OSM road centerline never implies a verified pedestrian path. Graph corrections and evidence must be first-class features.

### 1.2 Research and market basis

A 2026 qualitative study documents inconsistent accessibility considerations in sidewalk-detour planning and identifies room for systematic decision-support [S1]. A 2021 systematic work-zone review found little quantitative evaluation of proposed pedestrian accommodations [S2]. Project Sidewalk and AccessMap demonstrate existing accessibility mapping and routing; OpenSidewalks documents explicit pedestrian topology [S3–S5]. The product's defensible differentiation is **prospective, phase-aware, evidence-traceable verification and constrained alternative comparison**—not inventing sidewalk mapping, optimization, or AI.

**Go/no-go condition:** Deliver R0 only if the baseline and scenario graph are correct, every verdict is traceable, unknown attributes remain unknown, and regression tests show no false-safe results on known invalid test fixtures. Otherwise present it as an experimental planning visualization, not a verifier.

## 2. Product definition

**One-line description:** DETOUR LAB helps planners evaluate temporary pedestrian closures before construction, identify modeled accessibility failures and unknowns, compare candidate modifications, and export a reproducible review package.

**Primary problem:** Work-zone designs are often discussed as drawings or checklists. These formats may hide disconnected crossings, profile-specific restrictions, phase-transition failures and unreliable infrastructure data.

**North-star user outcome:** A planner can identify and explain a material detour issue before deployment, compare a feasible modeled alternative with explicit trade-offs, and hand the evidence to a qualified reviewer.

**Product promise:** *Design it. Simulate it. Challenge it. Review it.*

**Primary user:** Planning or traffic/civil engineer preparing a temporary pedestrian management plan.  
**Secondary users:** Accessibility reviewer, municipal reviewer, field surveyor and disability-community representative.  
**Explicitly not the user in R0/R1:** General-public navigation users seeking live route guarantees.

## 3. Goals, non-goals and release boundaries

### 3.1 Product goals

- G1: Represent real or manually corrected pedestrian connectivity, preserving directed edges and explicit curb/crossing interfaces.
- G2: Apply temporary closures and alternate paths across construction phases without mutating the original network.
- G3: Classify modeled constraints as Pass / Fail / Unknown / Not applicable with provenance and readable explanations.
- G4: Compare the before/after impact on selected origin-destination pairs for two mobility profiles.
- G5: Generate, rank and replay a bounded set of candidate fixes without overriding hard constraints.
- G6: Export a reproducible analysis report with model, input, ruleset and evidence references.

### 3.2 Non-goals for R0/R1

- Autonomous legal certification, project permit issuance, or replacement of an accessibility professional.
- Live accessible turn-by-turn public navigation, emergency dispatch, traffic signal engineering, crowd simulation or structural engineering.
- Autonomous geometric design of ramps/roadworks from an unrestricted AI prompt.
- Automatic engineering-grade dimensions inferred from uncalibrated photos.
- All-country compliance coverage, real-time IoT, BIM/CAD round-tripping, crowdsourcing at city scale or persistent multi-tenant municipal ERP.

### 3.3 Release matrix

| Release | Mandatory experience | Deliberately excluded |
|---|---|---|
| R0 — Trustworthy MVP (P0) | Seeded real-area network plus verified/synthetic labels; closure editor; 2 profiles; baseline/changed graph; tri-state rule evaluation plus N/A; exact edge findings; JSON export; deterministic tests | AI, automatic compliance, cost optimization, collaborative approval |
| R1 — Hackathon differentiators (P1) | Phase timeline; Fix This Plan with bounded candidate library and costs; side-by-side comparison; uncertainty/inspection queue; failure injection; reproducible PDF review package | Unconstrained layout generation, live maps for the public, every regulation |
| R2 — Research / pilot (P2) | Field-validated evidence, sensitivity/value-of-information studies, user research, standard-specific rulepacks, optional assisted imagery, roles and integrations | Safety certification unless separately authorized and validated |

## 4. Users and jobs-to-be-done

**Planner:** “Before the sidewalk closes, I need to know which planned path segments become unusable and what modification restores modeled access under my constraints.”  
**Reviewer:** “I need to inspect the exact assumptions and measurements behind a Pass claim and reject unsupported conclusions.”  
**Surveyor:** “I need a prioritized list of the few missing observations that could change the decision.”  
**Disability advocate:** “I need to see how changes affect multiple access profiles and contest unrealistic profile assumptions.”

### 4.1 Critical user journeys

**J1 — Evaluate a planned closure:** Open a project → inspect network provenance → draw closure → select profile/phase → run → see lost destinations and failed/unknown segments → inspect evidence.

**J2 — Repair a failed layout:** Select a failed scenario → open Fix This Plan → review eligible interventions and stated costs → compare valid candidate sets → apply a candidate to a *new* scenario branch → rerun validation.

**J3 — Review and challenge:** Select a result → examine rule/source/measurement → inject a missing curb interface or close another edge → reproduce the changed verdict → export an audit report with caveats.

**J4 — Resolve uncertainty:** Open the unknown queue → inspect why each measurement matters → collect or manually enter a measured value with provenance → rerun and observe the changed classification.

## 5. P0 functional requirements and acceptance criteria

| ID | Requirement | Acceptance / definition of done |
|---|---|---|
| FR-001 | Create/import study area | Load a versioned GeoJSON pedestrian dataset with IDs, CRS, origin and license metadata; reject malformed features with precise errors. |
| FR-002 | Explicit graph topology | Connections require shared validated node IDs or an explicit authorized join; two lines merely crossing do not connect. |
| FR-003 | Graph correction | User can add/split/delete edges, set direction, and assign curb/crossing attributes with edit history. |
| FR-004 | Evidence recording | Every safety-relevant attribute stores value, units, source, observed date and verification state; missing fields are explicitly unknown. |
| FR-005 | Scenario editor | Draw/select edge closure and temporary edge with start/end phases; baseline remains immutable. |
| FR-006 | Mobility profiles | Evaluate 2 documented parameter sets independently; defaults are editable but applicable project rules remain separate. |
| FR-007 | Rule registry | Machine-readable rule ID, wording, scope, operator, threshold, unit, provenance URL, version and required evidence. |
| FR-008 | Verdict engine | Return Pass in modeled checks, Fail, Unknown or N/A per element/rule; any unknown critical constraint prevents an overall verified-in-model status. |
| FR-009 | Feasibility graph | Construct separate known-pass, known-fail and unknown edge sets by profile and phase. |
| FR-010 | Route and reachability | Report confirmed reachability and possible reachability if unknown edges were usable; never report the latter as confirmed. |
| FR-011 | Differential view | Show original vs phase-specific status, lost origin-destination pairs, changed edges and route distance where meaningful. |
| FR-012 | Explainability | Each failed/unknown finding links edge ID, rule ID, inputs, evidence references and remedial information. |
| FR-013 | Deterministic replay | Same graph, scenario, ruleset, profiles and engine version reproduce the same verdicts and report payloads. |
| FR-014 | Accessible UI | Core workflow works with keyboard and has text/table alternatives to color-coded map findings. |
| FR-015 | Offline demo | Ship one local project with seed data, documented synthetic vs verified segments, and no runtime dependence on remote geocoding. |
| FR-016 | Structured export | Export JSON manifest, graph changes, results, all unknowns and source/attribution notices. |

### 5.1 Hard acceptance invariants

- **INV-01:** Unknown is never silently converted to Pass, including on import or after a manual edit.
- **INV-02:** A visual line intersection does not create a graph connection without the prescribed node relationship.
- **INV-03:** A blocked edge is not routed through in an active construction phase.
- **INV-04:** A source measurement in an incompatible unit is rejected or explicitly converted with recorded units.
- **INV-05:** Any rule failure invalidates a proposed route for that profile/phase; route preference weights cannot override hard constraints.
- **INV-06:** Derived reports identify rulepack, profile, baseline graph, scenario and engine versions.
- **INV-07:** The original scenario cannot be overwritten by applying an optimizer proposal without an explicit confirmation and saved revision.
- **INV-08:** A model Pass cannot be displayed as government approval or certification.

## 6. P1 differentiator requirements

| ID | Feature | Acceptance / definition of done |
|---|---|---|
| FR-101 | Construction phase timeline | Recompute each discrete phase; flag a route that works in phase A but not phase B. Represent consistent non-overlapping phase boundaries. |
| FR-102 | Candidate intervention library | User can enable/disable a bounded catalogue (e.g., approved alternate edge, temporary transition, barrier shift, sequence change), each with preconditions. |
| FR-103 | Fix This Plan | Enumerate or solve eligible intervention sets; rerun the authoritative verifier on every proposed output; never fabricate geometry. |
| FR-104 | Cost-aware comparison | Show cost model, currency, quantities, unit prices, setup/removal and uncertainty ranges; indicate estimates are illustrative unless sourced. |
| FR-105 | Multi-objective comparison | Present candidate feasibility first, then cost and added route length; show trade-off frontier, not an unexplained single AI score. |
| FR-106 | Honest solver state | Distinguish optimal, feasible not proven optimal, infeasible over modeled candidates, invalid input and incomplete/unknown. |
| FR-107 | Evidence inspection queue | List unverified critical edges and why each can change project approval; simple criticality ordering before advanced value-of-information. |
| FR-108 | Failure Lab | At least five reproducible fault scenarios change route/evidence states with transparent reason codes. |
| FR-109 | Side-by-side scenario compare | Synchronize two maps plus text summary; compare destinations, phases, interventions, unknowns and assumptions. |
| FR-110 | PDF review package | Export watermarked “Planning analysis — not certified” report with methodology, verdicts, changes, costs, evidence and unresolved actions. |
| FR-111 | Revision and branch history | Save immutable snapshots; compare runs and display changed input/evidence hashes. |

## 7. P2 future requirements (not launch promises)

| ID | Capability | Prerequisite / release gate |
|---|---|---|
| FR-201 | Photo-based barrier suggestions | Consentful dataset, error analysis, privacy safeguards and required human verification. |
| FR-202 | Multi-jurisdiction rulepacks | Legal/domain review, source-controlled clause mapping, versioned tests and exceptions. |
| FR-203 | Risk/sensitivity analysis | Calibrated evidence model and documented variation distributions. |
| FR-204 | Value-of-information planner | Baseline comparison against random and highest-uncertainty selection. |
| FR-205 | Real field survey app | Identity/access control, sync conflict resolution and device privacy review. |
| FR-206 | Role-based review/approvals | Authorized roles, audit log and professional sign-off policy. |
| FR-207 | BIM, CAD and GTFS integrations | Verified data licenses, semantics and schema tests. |
| FR-208 | Public advisory portal | Independent safety, currency, accessibility and governance sign-off. |
| FR-209 | Assisted natural-language explanations | Strict retrieval from structured facts and hallucination/omission evaluation. |
| FR-210 | Cross-city scalable backend | Measured bottleneck on real datasets justifies PostGIS, cache or workers. |

## 8. Domain model and decision semantics

### 8.1 Minimum entities

- **Project:** id, name, study polygon, coordinate reference, jurisdiction descriptor, owner, created_at.
- **BaseGraphVersion:** version, content hash, source license, import timestamp, nodes, directed edges.
- **Node:** id, geometry, junction/curb/crossing type, provenance.
- **Edge:** id, `u`, `v`, geometry, direction, length, width, slope, surface, curb_transition, temporal availability and evidence refs.
- **Evidence:** id, element_id, field, observed value/unit, method, source, timestamp, verifier, quality and status.
- **RulePack:** id, version, basis, geographic scope, disclaimer and rules.
- **Rule:** id, element applicability, expression, units, evidence requirement, source citation and human-readable failure text.
- **Profile:** id, immutable base needs plus configurable preferences; profile thresholds never nullify statutory rules.
- **Phase:** id, logical order, start/end, active closures and temporary constructions.
- **Scenario:** id, parent, graph version, rulepack, interventions, phases and note.
- **CandidateIntervention:** geometry/element edits, dependencies, prerequisites, nominal/range costs and life cycle phases.
- **AnalysisRun:** ids/hashes, evaluated profile/phase, results, solver status, runtime and engine version.
- **Finding:** status, edge/node, rule, evidence IDs, reason code, readable explanation.
- **ReviewArtifact:** linked analysis runs, approval disclaimer and file hashes.

### 8.2 Formal verification behavior

Let `G=(V,E)` be a directed pedestrian graph. For profile `p` and construction phase `t`, each edge `e` is assigned a rule state `s(e,p,t)` in `{PASS, FAIL, UNKNOWN, N_A}`. N/A applies only to individual nonapplicable rules, never as a universal edge clearance. A connected route is **model-confirmed** only when every traversed relevant edge and node satisfies the required checks with adequate evidence. If a requirement is unknown, the route remains unconfirmed. A **potentially traversable** graph may include unknown edges and must be labeled separately.

An analysis returns at least:

`confirmed_reachable(orig, dest, p, t)`, `possibly_reachable(orig, dest, p, t)`, `known_failure_reasons`, `unknown_reason_ids`, `length_if_confirmed`, and `selected_ruleset_version`.

Missing, expired or conflicting evidence yields UNKNOWN according to documented policy; there must be no global AI confidence score that can override that result.

### 8.3 Optimization behavior

For a bounded set of candidate changes `C`, choose subset `S` subject to candidate prerequisites, budget and all hard model constraints. Use **feasibility-first / lexicographic** objectives: (1) satisfy mandatory modeled conditions; (2) maximize retained critical origin-destination connections or user-selected coverage; (3) minimize cost; (4) minimize detour burden. Return non-dominated alternatives where objectives conflict.

In R1, generate a small finite candidate set and enumerate combinations where computationally practical; OR-Tools CP-SAT may replace enumeration when benchmarked complexity warrants it. The reported feasible/optimal/unknown/infeasible states must match solver semantics [S9]. No automatic intervention is declared field-constructible without human confirmation.

### 8.4 Evidence priority

Evidence status is determined through *rule-specific* requirements, not a simplistic rank where all government records automatically outrank recent measurements. In conflicting cases, preserve both claims and mark the attribute UNKNOWN until reviewed. Store the age of evidence; use configurable freshness rules per attribute.

## 9. Interface and interaction specification

| View | Required panels and actions |
|---|---|
| Project home | Open/import study area, active scenario, version/ruleset identification, available source and uncertainty counts. |
| Planning Studio | Base map, accessible feature list, closure/temporary-edge tools, explicit graph connect/disconnect controls, editable measurement drawer, undo/version save. |
| Verification | Phase/profile filters, confirmed vs possible reachability, destination matrix, severity-coded findings with text labels and evidence links. |
| Fix This Plan (R1) | Candidate inputs, budget, ranking table, solver/status banner, cost assumptions, candidate diff, apply-to-branch. |
| Failure Lab (R1) | Fault library, active injected conditions, before/after verdict diff, reset/replay. |
| Evidence & Review (R1) | Critical unknown queue, source records, audit and report export. |

### 9.1 Design requirements

- Never rely on colors alone; use explicit icons, words and accessible table equivalents.
- Keep ruleset version, profile and phase visible in every verdict view.
- Display unknowns alongside failures; do not bury missing evidence in a secondary tab.
- Every displayed cost says whether sourced, manually entered or demonstration-only.
- Every route detail includes a feedback affordance to flag a questionable network connection.
- For critical failures, show both a compact explanation and an inspectable raw rule/evidence trace.

## 10. System architecture and technology rationale

**Frontend:** React + TypeScript + MapLibre GL JS for an editable geospatial canvas and synchronized comparison views [S10].  
**Backend:** Python + FastAPI for typed endpoints, reusable scientific stack and separate authoritative evaluation services.  
**Graph:** NetworkX for explicit directed graph transformations and shortest feasible paths; OSMnx only for ingestion where appropriate. An imported OSM street route is not automatically accepted as a sidewalk graph.  
**Geometry:** Shapely/GeoPandas for validation, clipping and intersection QA; use stable planar/projected units for distance/width computations.  
**Rules:** Small declarative JSON/YAML rules with pure, tested Python evaluators. No free-form dynamic code execution from uploaded rules.  
**Optimizer:** Bounded enumeration first; OR-Tools CP-SAT when discrete decision complexity justifies it [S9].  
**Storage:** SQLite + GeoJSON for seeded/offline demo; upgrade to PostGIS only on measured need.  
**Reporting:** JSON manifest as canonical output; PDF built from structured facts.  
**AI (R2 optional):** Offline or hosted computer-vision suggestions, with human review and no fabricated measurements.

### 10.1 Logical processing chain

`Import + validate → explicit graph version → scenario edits → phase graph → profile/rule evaluation → confirmed/possible reachability → findings → candidate interventions → re-verification → comparable results → immutable report manifest`.

No optimization or explanation module is allowed to bypass re-verification of the final candidate layout.

### 10.2 API outline

| Method + endpoint | Purpose |
|---|---|
| POST `/api/v1/projects` | Create project and metadata. |
| POST `/api/v1/projects/{id}/imports` | Validate and ingest GeoJSON network. |
| GET `/api/v1/projects/{id}/graph` | Retrieve graph version and provenance. |
| POST `/api/v1/projects/{id}/scenarios` | Create scenario branch. |
| PATCH `/api/v1/scenarios/{id}` | Apply validated edits with optimistic version check. |
| POST `/api/v1/scenarios/{id}/evaluate` | Create deterministic analysis run for profile/phase. |
| GET `/api/v1/runs/{id}` | Results, findings and reachability. |
| POST `/api/v1/scenarios/{id}/candidates` | Generate/evaluate candidate intervention sets (R1). |
| POST `/api/v1/scenarios/{id}/fault-tests` | Run declared failure suite (R1). |
| GET `/api/v1/runs/{id}/manifest` | Download machine-readable immutable record. |
| GET `/api/v1/runs/{id}/report` | Download review PDF (R1). |

All errors return stable reason codes and enough context to reproduce the input problem without exposing unnecessary personal data.

## 11. Data, source and standards governance

### 11.1 Mapping data

OSM data is under ODbL and requires attribution; public OSM raster tile servers are not unrestricted infrastructure for an application. Use an appropriate tile provider or bundled offline maps where permitted, and keep attribution visible in the interface and exports [S7]. Store source version and import timestamp.

Use the OpenSidewalks network model as a semantic reference, especially explicit end-to-end connections and curb interfaces [S5]. A project must label data as **measured**, **external source**, **derived**, **assumed** or **synthetic fixture**. Do not blend these categories without provenance.

### 11.2 Standards and legal posture

For Indian pilots, the Harmonised Guidelines for Universal Accessibility in India 2021 are a primary reference listed under relevant national disability-accessibility rules [S6]. Specific applicability, provisions and exceptions must be reviewed before encoding an enforceable India ruleset. For US reference scenarios, the Access Board's PROWAG contains requirements for temporary alternate pedestrian access routes [S8]; it must not be presented as universally applicable in India. The current US MUTCD edition as of this PRD is the 11th Edition with Revision 1 (December 2025) [S11].

**R0 rulepack:** `DEMO-ACCESS-1.0`, a transparent modeling ruleset with individually cited technical inspirations, **not** a legally certified standards implementation. No headline claiming “compliant with Indian/US law.” Maintain `legal_applicability=unverified` until domain review is complete.

## 12. Nonfunctional requirements

| Category | R0/R1 requirement and initial target |
|---|---|
| Performance | Target p95 single-profile rerun under 2 s on reference laptop for a seeded graph ≤1,000 nodes / ≤3,000 directed edges, measured with cold/warm runs distinguished. |
| Optimization | Target bounded 5–10 eligible intervention options with ≤20 chosen candidate layouts compared in under 10 s; report actual timings. |
| Reliability | No unhandled exceptions in the scripted demo and regression fixtures; clearly signal errors rather than returning misleading success. |
| Determinism | Repeat identical non-stochastic runs 20 times with matching canonical payload hashes. |
| Accessibility | Target WCAG 2.2 AA for core UI; map interactions have keyboard and screen-reader-accessible text/table alternatives [S12]. |
| Security | Validate geometry and upload sizes; cap compute time; prevent unsafe rule expression evaluation, path traversal and injected map content. |
| Privacy | Avoid storing identifiable imagery in R0; R2 imagery requires consent, retention and face/license-plate handling. |
| Reproducibility | Commit seed data, fixture schemas and reproducible environment; pin dependencies and record content hashes. |
| Observability | Structured run logs with run ID, timing, engine/ruleset versions, warnings and solver termination status. |
| Transparency | Export includes all model limitations, unknowns and synthetic assumptions. |

All numerical targets above are **acceptance targets to test**, not reported achieved metrics.

## 13. Benchmark and evaluation plan

**Primary research hypothesis H1:** Evidence-aware, phase-specific verification reduces false-safe decisions versus baseline graph routing/checklists on a prespecified benchmark.  
**H2:** Bounded intervention search discovers lower-cost or less-disruptive feasible modeled layouts than an explainable greedy baseline, for scenarios where feasible solutions exist.  
**H3 (R2):** Critical-edge inspection ordering resolves model decisions with fewer inspections than random and highest-uncertainty ordering.

### 13.1 Benchmark construction

- At least **30 controlled fixtures** with known graph/rule truth (10 topology, 8 phase, 6 profile/geometry, 6 data uncertainty) for R0/R1; include failed and impossible cases.
- At least **1 small, real geographic study area** with a manual pedestrian graph audit; show a disclosure identifying all assumed/synthetic values.
- R2 goal: **10+ field-checked critical segments** with documented methodology, if permissions and safe inspection access exist.
- Define gold answers before implementing candidate improvements; include withheld regression cases where possible.
- Never report synthetic-only test performance as observed citywide accessibility accuracy.

### 13.2 Metrics and proposed gates

| Metric | Definition | Proposed R0/R1 gate |
|---|---|---|
| False-safe rate | Known-invalid fixture scenarios marked Pass / all known-invalid fixtures | **0** on benchmark invalid fixtures (not a field safety guarantee). |
| Violation recall | Detected known violations / all labeled known violations | **≥95%** on supported rule fixtures; disclose unsupported conditions. |
| Unknown-state recall | Critical missing/conflicting inputs flagged unknown / such gold cases | **100%** on explicit unknown fixtures. |
| Route correctness | Confirmed reachable origin-destination outputs matching graph ground truth | **100%** on deterministic reference fixtures. |
| Proposal feasibility | Generated candidates that pass independent re-verification / shown as feasible | **100%** for reported modeled-feasible candidates. |
| Solver performance | Runtime, candidate count, feasibility and optimality proof status | Report distribution and worst case, not only mean. |
| Cost comparison | Nominal total, min-max range and sensitivity | Every ranked option has traceable assumptions. |
| Reproducibility | Matching result hashes for identical pinned inputs | **100%** for 20 seeded reruns. |
| Accessibility UX | Keyboard and screen-reader walkthrough of primary flow | No known blocking issue in core flow. |

### 13.3 Baselines

B1: ordinary shortest path without access constraints; B2: profile-aware static graph without construction phases; B3: rule checklist without network connectivity analysis; B4: greedy least-cost candidate selection; B5 (R2): random and highest-uncertainty inspection order. Use the same seeded scenarios and report coverage of each baseline's capabilities fairly.

### 13.4 Mandatory failure fixtures

F01 visual crossing without a shared node; F02 blocked curb transition; F03 prohibited steep directed edge; F04 known narrow path; F05 unknown width; F06 conflicting reports; F07 closure active only in second phase; F08 temporary path removed too early; F09 no feasible candidate within budget; F10 solver timeout/incomplete search; F11 plan meets one profile but not another; F12 missing accessible information/detectable boundary tagged out-of-scope or unknown rather than falsely approved.

## 14. Delivery plan and milestone gates

**M0 — Evidence & design contract:** Select area, acquire permitted map data, write ruleset scope and test fixtures, define user-facing disclaimers and reference profiles. Gate: 10 reviewed fixture truths and no unresolved legal-scope ambiguity in copy.

**M1 — Trusted graph:** Build import, editing, explicit topology, evidence and baseline routing. Gate: topology fixtures pass and source/synthetic provenance visible.

**M2 — Deterministic verifier (R0):** Implement closures, profiles, rule results, confirmed/possible reachability and explanations. Gate: all P0 invariants pass; no known false-safe benchmark fixture; offline demo runs.

**M3 — Phase and alternatives (R1):** Add timeline, bounded candidate library, candidate re-verification, cost comparisons and honest solver states. Gate: phase regression and optimizer tests pass; no invented “optimal” or “compliant” claims.

**M4 — Research-quality demonstration (R1):** Failure Lab, scenario diff, audit manifest/report, benchmarks and usable polished UI. Gate: full demo executed without a developer rescue; metrics report generated by reproducible scripts.

**M5 — Field/R2 decision:** Domain-expert walkthrough and small supervised field validation; decide whether to invest in jurisdiction-specific rules, evidence acquisition or new algorithms. Gate: documented user feedback and prioritized research questions.

Dependencies: M1 → M2 → M3; M4 can improve presentation only after M2 is stable. If under hackathon time pressure, cut M4 polish before weakening M2 correctness.

## 15. Risks and mitigations

| Risk | Severity | Response |
|---|---|---|
| Missing sidewalks or curb geometry in OSM | Critical | Versioned manual corrections; mark unknown; narrow pilot area; no fictitious automatic connectivity. |
| False implication of legal certification | Critical | Required caveat in every screen/report; versioned demo rules; qualified review required. |
| Missing measurement incorrectly passes a route | Critical | Tri-state rule logic, fixture gates, disabled “approve” semantics. |
| Optimizer proposes physically impossible construction | High | Restricted candidate templates with geometry/preconditions and human acceptance; solver re-verification. |
| Overloaded feature scope | High | Locked R0, gated R1, deferred AI/ERP/mobile integrations. |
| Untrusted or stale crowd/photo inputs | High | Provenance ledger; critical conflict = unknown; no image-only numeric measurement. |
| Weak novelty against prior art | Medium | Claim workflow/verified benchmark contribution, not new graph or routing mathematics. |
| Unrealistic cost numbers | High | Explicit cost source/assumptions, range and non-binding estimates. |
| Map/OSM licensing or tile availability | Medium | Attribution, provider policy compliance, offline seeded export. |
| Inaccessible map editor | High | Parallel list and form editor, keyboard focus, accessible findings table. |

## 16. Commercial and research outlook

**Likely first users:** University facilities teams, engineering consultancies and accessibility-focused civic researchers who can supply bounded projects and review scenarios. Municipalities are a later target because procurement, liability and workflow integration require evidence beyond a hackathon demo.

**Potential pricing model (hypothesis only):** Project-based analysis licence or institutional pilot subscription plus optional engineering/field-data services. No revenue forecast until customers validate willingness to pay.

**Research contribution to pursue:** A reproducible benchmark and decision-support methodology for phase-aware pedestrian detour verification under missing and contradictory evidence, with sensitivity of optimization outcomes to unknown field attributes. A system that merely combines established algorithms is a strong engineering contribution but not automatically a novel scientific method.

**External validation required:** At least one practicing engineer or qualified accessibility reviewer, and ideally representatives with lived experience of relevant mobility barriers, should evaluate profiles, interface accessibility and limitations before any real-world use.

## 17. Final release acceptance checklist

- [ ] One bounded real study area plus clear measured/assumed/synthetic labeling.
- [ ] Immutable imported base graph and traceable topology corrections.
- [ ] Two documented profile sets with distinct, independent results.
- [ ] Known Fail and Unknown are visibly different; neither is treated as Pass.
- [ ] Construction editor changes graph connectivity and phase evaluation deterministically.
- [ ] Every result has linked rule/edge/evidence and exact revision identifiers.
- [ ] R1 candidate outputs are independently reverified and costs labeled.
- [ ] Solver status cannot be confused with physical/regulatory approval.
- [ ] At least 30 controlled fixtures, baseline comparisons and generated metric tables.
- [ ] Core workflow accessible without map-only interactions.
- [ ] Local, preloaded and internet-independent hackathon demo mode.
- [ ] JSON manifest and review PDF clearly state limitations and provenance.
- [ ] No fake field performance numbers, unstated thresholds or fabricated engineering sign-off.

**Release decision:** Ship R0 when all R0 gates pass; call it the “DETOUR LAB Preview.” Label R1 the “Hackathon Research Prototype.” Do not claim deployable infrastructure certification without separate legal, safety, accessibility and field-validation review.

## 18. Open decisions and assumptions

| Decision | Baseline choice | Revisit trigger |
|---|---|---|
| Initial geography | One bounded college-adjacent neighbourhood, chosen for data quality rather than brand recognition | No connected sidewalk graph obtainable |
| Jurisdiction | Demo ruleset with annotated source references, no legal-compliance claims | Engaged local professional identifies applicable rules |
| Mobility profiles | Manual wheelchair and limited-mobility walking profile; low-vision wayfinding conditions explicitly unknown/out of scope unless modeled | Co-design yields sufficiently specified third profile |
| Optimization | Predefined interventions + enumeration | Runtime or option count necessitates solver |
| Cost model | Edited illustrative cost ranges | Verified local unit prices become available |
| Data store | SQLite + canonical GeoJSON | Cross-user collaboration or geospatial query load justifies PostGIS |
| AI | None in safety critical path | Demonstrated advisory annotation benefit with evaluation |
| Primary success metric | False-safe rate on deterministic, predeclared fixtures | Field validation supports broader measurement |

## 19. Source register

[S1] Razavi, Montuwy & Mostafavi (2026), *Key Criteria for Accessible Sidewalk Detour Planning* — https://www.mdpi.com/2073-445X/15/9/1538  
[S2] Shaw & Oneyear (2021), *Pedestrian Accommodations in Work Zones: Systematic Literature Review and Research Needs* — https://workzonesafety.org/publication/pedestrian-accommodations-in-work-zones-systematic-literature-review-and-research-needs/  
[S3] Project Sidewalk, source and documentation — https://github.com/ProjectSidewalk/SidewalkWebpage  
[S4] AccessMap, source and routing infrastructure — https://github.com/TaskarCenterAtUW/AccessMap  
[S5] OpenSidewalks Schema — https://github.com/OpenSidewalks/OpenSidewalks-Schema  
[S6] Government of India, Harmonised Guidelines and Standards for Universal Accessibility in India 2021 (notified listing) — https://depwd.gov.in/en/document/harmonised-guidelines-standards-for-universal-accessibility-in-india-2021/  
[S7] OpenStreetMap Foundation, ODbL and attribution FAQs — https://osmfoundation.org/wiki/License/Licence_and_Legal_FAQ  
[S8] U.S. Access Board, Public Right-of-Way Accessibility Guidelines, R204/R303 — https://www.access-board.gov/prowag/complete.html  
[S9] Google OR-Tools, CP-SAT solver status guidance — https://developers.google.com/optimization/cp/cp_solver  
[S10] MapLibre GL JS documentation — https://maplibre.org/maplibre-gl-js/docs/  
[S11] FHWA, MUTCD 11th Edition with Revision 1 — https://mutcd.fhwa.dot.gov/kno_11th_Editionr1.htm  
[S12] W3C, Web Content Accessibility Guidelines 2.2 — https://www.w3.org/WAI/news/2023-10-05/wcag22rec/

---

**Document control:** This is a specification and research-informed planning document. It does not constitute an engineering drawing, accessibility certification, legal opinion, or authority approval. Actual site work requires qualified human review and applicable local permissions.
