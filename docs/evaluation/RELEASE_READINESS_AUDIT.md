# RELEASE_READINESS_AUDIT.md — Gate 7 Release Candidate Audit

**DETOUR LAB** — Pre-construction pedestrian detour decision support and model verification prototype.  
**Release Target:** Gate 7 Release Candidate  
**Audit Date:** 20 October 2026  
**Auditor / Git Identity:** PrathamKapoor (`prathamkapoor027@gmail.com`)  
**Repository Working Tree:** `C:\Pratham\DETOUR-LAB`

---

## 1. Executive Audit Summary

| Category | Total Requirements | Verified | Insufficiently Tested | Blocked by Owner Decision | Deferred by PRD | Blocking Defects |
|---|---|---|---|---|---|---|
| **P0 Functional (FR-001..FR-016)** | 16 | 16 | 0 | 0 | 0 | 0 |
| **P0 Invariants (INV-01..INV-08)** | 8 | 8 | 0 | 0 | 0 | 0 |
| **P1 Differentiators (FR-101..FR-111)** | 11 | 11 | 0 | 0 | 0 | 0 |
| **Mandatory Behaviors (B1..B32)** | 32 | 32 (incl. B30/B31 in G7) | 0 | 0 | 0 | 0 |
| **Gate 5 Optimization (G5-01..G5-12)** | 12 | 12 | 0 | 0 | 0 | 0 |
| **Gate 6 Intelligence & Reporting (G6-01..G6-33)** | 33 | 33 | 0 | 0 | 0 | 0 |
| **Gate 7 Quality & Validation (G7-01..G7-21)** | 21 | 21 | 0 | 0 | 0 | 0 |
| **Evaluation Baselines (B-1..B-5)** | 5 | 5 | 0 | 0 | 0 | 0 |
| **P2 Future Requirements (FR-201..FR-210)** | 10 | 0 | 0 | 0 | 10 | 0 |
| **Owner Decisions (O-1..O-5)** | 5 | 0 | 0 | 5 | 0 | 0 |

**Verdict:** All mandatory R0/R1 functional, safety, invariant, optimization, failure-lab, reporting, and research baseline requirements are implemented, tested, and empirically verified. Zero unmitigated release-blocking defects exist for the local research / hackathon release.

---

## 2. Core Functional Requirements Audit (P0)

| ID | Requirement | User-Visible Behavior | Implementation | API Dependency | Associated Data Contracts | Unit / Integration Tests | Browser E2E Tests | Observed Verification Status | Limitations & Notes |
|---|---|---|---|---|---|---|---|---|---|
| **FR-001** | Create/import study area | Upload/import network GeoJSON with IDs, CRS, origin, licence | `detour_lab.ingestion.schema` | `POST /projects/{id}/imports` | `Project`, `GraphVersion`, `Node`, `Edge` | `test_ingestion.py`, `TestProjectAndImportFlow` | `E2E-01`, `E2E-02` | **VERIFIED** | Synthetic local-planar dataset bundled; real GIS import bounded by O-2. |
| **FR-002** | Explicit topology | Visual crossings without shared nodes are non-connecting | `detour_lab.graph.model` | `GET /projects/{id}/graph` | `GraphSnapshot`, `UnlinkedCrossing` | `test_b01_*`, `TestCrossingIsNotConnectivity` | `E2E-02` | **VERIFIED** | Proximity does not infer connection; shared node ID mandatory. |
| **FR-003** | Graph correction | Add/split/link/direction/attribute edits staged and applied | `detour_lab.scenarios.apply` | `PATCH /scenarios/{id}` | `ScenarioEdit`, `ScenarioRevision` | `TestTypedEdits` (9 cases) | `E2E-09`, `E2E-10`, `E2E-18` | **VERIFIED** | Typed edits validated against schema; optimistic concurrency protected. |
| **FR-004** | Evidence recording | Value, units, source, date, verification status recorded | `detour_lab.evidence.resolver` | `POST /projects/{id}/evidence` | `EvidenceRecord`, `ResolvedAttribute` | `test_evidence_resolution.py` (19 cases) | `E2E-08`, `E2E-G6-03` | **VERIFIED** | Five-state resolution; conflicting measurements kept, never averaged. |
| **FR-005** | Scenario editor | Closures and temporary edges declared per phase | `detour_lab.scenarios.apply` | `PATCH /scenarios/{id}` | `PhaseDeclaration`, `ClosureDeclaration` | `TestClosureAndPhases`, `test_b10_*` | `E2E-09`, `E2E-10`, `E2E-G4-02` | **VERIFIED** | Source baseline remains immutable; phase graph derived on demand. |
| **FR-006** | Two mobility profiles | Manual wheelchair and power/assisted profiles evaluated independently | `detour_lab.rules.profiles` | `POST /scenarios/{id}/evaluate` | `MobilityProfile`, `AnalysisResult` | `TestProfileIndependence`, `test_b13_*` | `E2E-05` | **VERIFIED** | Distinct geometry, grade, and surface thresholds per profile. |
| **FR-007** | Machine-readable rules | Ruleset JSON with metadata, thresholds, citations | `rules/rulepacks/*.json` | `GET /rulepacks/{id}` | `Rule`, `Rulepack` | `TestRuleSafety`, `test_rulepack_hash_is_stable` | `E2E-07` | **VERIFIED** | Demo rulepack `DEMO_RULEPACK_NOT_LEGAL`; legal applicability unverified (O-3). |
| **FR-008** | Verdict engine | Four-valued verdicts: Pass, Fail, Unknown, Not Applicable | `detour_lab.rules.engine` | `POST /scenarios/{id}/evaluate` | `RuleVerdict`, `VerdictStatus` | `TestFourValuedEvaluation` (6 cases) | `E2E-07`, `E2E-08` | **VERIFIED** | Unknown never silently becomes Pass; conservative evaluation enforced. |
| **FR-009** | Feasibility graphs | Dual graphs per profile & phase: confirmed vs possible | `detour_lab.graph.routing` | `POST /scenarios/{id}/evaluate` | `FeasibilityGraphs`, `RoutingGraph` | `TestFeasibilityGraphs` (4 cases) | `E2E-06b` | **VERIFIED** | Confirmed = all rules Pass; Possible = no rule Fail (Pass + Unknown). |
| **FR-010** | Dual reachability | Confirmed vs possible routes never conflated | `detour_lab.graph.routing` | `POST /scenarios/{id}/evaluate` | `ODPairResult` | `test_b11_*`, `test_b12_*` | `E2E-08`, `E2E-G4-06` | **VERIFIED** | Rendered via distinct line styles (solid vs dashed) on SVG canvas. |
| **FR-011** | Differential view | Before/after reachability comparison across runs | `features/analysis/` | `GET /scenarios/{id}/comparison` | `RunComparison`, `ODDelta` | `test_b09_*`, `test_b25_*` | `E2E-11`, `E2E-G4-11` | **VERIFIED** | Computed from two stored authoritative runs, not browser logic. |
| **FR-012** | Explainability | Exact rule, failed/unknown attributes, evidence citations | `detour_lab.rules.engine` | `POST /scenarios/{id}/evaluate` | `Finding`, `EvidenceReference` | `test_explanation_never_claims_certification`, `test_b04_*` | `E2E-07`, `E2E-G6-13` | **VERIFIED** | Every violation cites element ID, rule name, values, and missing evidence. |
| **FR-013** | Deterministic replay | Byte-identical results and identical semantic hashes | `detour_lab.domain.hashing` | `POST /scenarios/{id}/evaluate` | `AnalysisRun.semantic_hash` | `test_b28_*`, 20-run loop | `E2E-17`, `E2E-G6-20` | **VERIFIED** | Float normalisation (6 decimals), canonical sorting, explicit timestamp. |
| **FR-014** | Accessible UI | WCAG 2.2 AA targeting, keyboard operable, entity table | `apps/web/src/**` | Frontend web UI | React UI, ARIA attributes | Vitest component tests (20) | `E2E-04`, `E2E-15`, `E2E-15b`, `E2E-G6-28` | **VERIFIED** | Axe core clean on all primary screens; keyboard tab order verified. |
| **FR-015** | Offline demo | Standalone offline operation with synthetic/verified labels | `data/demo/`, `apps/web/` | `GET /api/v1/health` | Local planar JSON | `TestLocalPlanarDataset` | `E2E-01`, `E2E-13` | **VERIFIED** | Zero third-party cloud tiles, fonts, or external telemetry required. |
| **FR-016** | Structured JSON export | Canonical export manifest with unknowns and disclosures | `detour_lab.reporting.manifest` | `GET /runs/{id}/manifest` | `RunManifest`, `AuditEnvelope` | `TestManifest` (6 cases), `test_b27_*` | `E2E-14`, `E2E-G4-18`, `E2E-G6-25` | **VERIFIED** | Canonical JSON with SHA-256 semantic hash; downloadable verbatim. |

---

## 3. Hard Invariants Audit (INV-01..INV-08)

| ID | Invariant Definition | Enforcement Mechanism | Verification Test | Status |
|---|---|---|---|---|
| **INV-01** | Unknown never silently becomes Pass | Resolver returns `UNKNOWN` on missing/conflicting/unverified evidence; rule engine fails closed | `test_invariants.py::TestInv01UnknownNeverBecomesPass` (4 cases) | **VERIFIED** |
| **INV-02** | Visual intersection ≠ graph connection | Edges only connect at shared node IDs; geometric crossings flagged in topology QA | `test_invariants.py::TestInv02CrossingIsNotConnectivity` (2 cases) | **VERIFIED** |
| **INV-03** | Blocked edge never routed | Active closures exclude edges from routing graph; traversal impossible | `test_invariants.py::TestInv03BlockedEdgeNotRouted` (3 cases) | **VERIFIED** |
| **INV-04** | Incompatible units rejected or converted | Unit conversions explicit (`cm->m`, `in->m`); incompatible dimensions fail validation | `test_invariants.py::TestInv04UnitIncompatibility` (2 cases) | **VERIFIED** |
| **INV-05** | Rule failure invalidates route; weights cannot override | Hard rule Fail excludes edge from confirmed graph regardless of preference penalty | `test_invariants.py::TestInv05PreferenceCannotOverrideHardConstraints` (3 cases) | **VERIFIED** |
| **INV-06** | Results identify versions and disclosures | AnalysisRun, Manifest, and PDF explicitly identify engine, rulepack, profile, dataset | `test_invariants.py::TestInv06ReportIdentifiesVersions` (2 cases) | **VERIFIED** |
| **INV-07** | Candidate promotion preserves source baseline | Promotion is clone-with-edits creating a new branch; source revision and content hash untouched | `test_invariants.py::TestInv07BaselineIsImmutable` (2 cases) | **VERIFIED** |
| **INV-08** | No approval or certification language | Verdicts framed as "Pass in modeled checks"; headers and reports state "Not certified" | `test_invariants.py::TestInv08NoCertificationLanguage` (3 cases) | **VERIFIED** |

---

## 4. Differentiator & Subsystem Audit (P1, Gate 4–6)

### Gate 4: Construction Phase Intelligence (FR-101)
- **Timeline & Phase Ordering:** `Scenario.ordered_phases()` enforces authoritative phase ordering. Verified by `test_phase_reads.py` and `E2E-G4-01`.
- **Authoritative Phase Graphs:** Materialized phase graphs returned by backend; browser never guesses closures. Verified by `E2E-G4-02`.
- **Continuity Matrix:** Evaluates 9 transition pairs; identifies first problematic phase from phase order. Verified by `temporal.test.ts` (32 tests) and `E2E-G4-08`.
- **Scenario Branching:** Branches created with parent link and revision isolation; source scenario unchanged. Verified by `E2E-G4-09` and `E2E-G4-10`.

### Gate 5: Fix This Plan — Bounded Optimization (FR-102..FR-106, G5-01..G5-12)
- **Validated Intervention Library:** `data/demo/interventions.demo.json` loaded with typed effects and preconditions. Verified by `G5-01`, `E2E-G5-01/02`.
- **Bounded Enumeration:** Search constrained by `max_candidates` and `max_duration_ms`; domain truncation echoed honestly. Verified by `G5-03`, `E2E-G5-04/22`.
- **Authoritative Re-verification:** Every candidate re-verified by unmodified analysis pipeline. Verified by `G5-04`, `E2E-G5-08`.
- **Introduced Unknowns Discipline:** Candidates introducing UNKNOWN evidence classified `requires_verification`, never `certified`. Verified by `G5-05`, `E2E-G5-07`.
- **Cost Discipline:** Absent costs rendered as `null` ("Not estimated"); currency conversion refused without FX rate. Verified by `G5-06`, `G5-07`, `E2E-G5-03/12/13`.
- **Lexicographic Ranking & Pareto:** Monetary objective off by default; 3-axis Pareto frontier computed. Verified by `G5-08`, `E2E-G5-23`.
- **Transactional Promotion:** Promotes candidate to new scenario branch, re-verifies post-persist; 409 on stale source revision. Verified by `G5-10`, `E2E-G5-15..20`.

### Gate 6: Evidence Intelligence, Failure Lab, and Review Reporting (FR-107..FR-110, G6-01..G6-33)
- **Derived Evidence Queue:** Derived strictly from resolver outputs; deterministic ordering; no artificial numeric score. Verified by `G6-01..05`, `E2E-G6-01..06`.
- **Stable Issue Identity:** Issue hash remains invariant under scope changes (P-33). Verified by 4 backend tests.
- **Typed Adversarial Faults:** 9 authored suites; no code execution from definitions; per-phase suite readiness (P-34). Verified by `G6-06..10`, `E2E-G6-07..09`.
- **Engineering Observations vs Execution Status:** Software outcomes (`completed`, `invalid_experiment`) separated from physical network reachability. Verified by `G6-12`, `E2E-G6-17`.
- **Robustness Denominators:** Denominators explicitly stated (`pairs_evaluated`); probability claims refused. Verified by `G6-15..16`, `E2E-G6-27`.
- **Audit-Ready Review Packet:** 12-section genuine ReportLab PDF; canonical JSON manifest; SHA-256 digest verified on download; watermarked "Not certified". Verified by `G6-19..27`, `E2E-G6-22..26`.
- **Duplicate Scenario ID Conflict:** Returns HTTP 409 `SCENARIO_ID_EXISTS` with schema-compliant envelope (P-40). Verified by backend & E2E tests.

---

## 5. Gate 7 Deliverables & Release Candidate Status

| ID | Gate 7 Deliverable | Implementation Artifact | Associated Verification | Status |
|---|---|---|---|---|
| **G7-01** | Release Readiness Audit | `docs/RELEASE_READINESS_AUDIT.md` | Codebase & test inventory across all gates | **VERIFIED** |
| **G7-02** | Research Baseline Architecture | `apps/api/detour_lab/benchmarks/baselines.py` | Implementation of Baselines A–E | **VERIFIED** |
| **G7-03** | Benchmark Dataset Design | `apps/api/detour_lab/benchmarks/fixtures.py` | 20 deterministic scenario fixtures | **VERIFIED** |
| **G7-04** | Scientific Evaluation Metrics & Runner | `apps/api/detour_lab/benchmarks/runner.py`, `docs/RESEARCH_EVALUATION.md` | `test_benchmarks.py`, raw JSON output | **VERIFIED** |
| **G7-05** | Performance & Scalability Benchmark | `apps/api/detour_lab/benchmarks/scalability.py` | Workloads from 15 to 1,000 nodes; p50/p95 latency | **VERIFIED** |
| **G7-06** | Security Threat Model | `docs/SECURITY_REVIEW.md` | Practical review of 20 threat questions | **VERIFIED** |
| **G7-07** | Security Hardening & Regression Suite | `apps/api/detour_lab/api/v1/**`, `apps/api/tests/test_security_hardening.py` | Input bounds, path traversal protection, XSS escaping | **VERIFIED** |
| **G7-08** | Accessibility Audit | Automated Axe scans + keyboard review | WCAG 2.2 AA targeting, contrast measured | **VERIFIED** |
| **G7-09** | Visual & UX Polish | Frontend components across 4 viewports | Responsive table scrolling, loading/empty states | **VERIFIED** |
| **G7-10** | System Reliability & Recovery | Error boundaries, concurrency guards, restart replay | 409 conflict, offline resilience, restart persistence | **VERIFIED** |
| **G7-11** | System-Wide Reproducibility Audit | Semantic hashing across all 16 project dimensions | 20-run seeded loops, restart byte-identical verification | **VERIFIED** |
| **G7-12** | Release Candidate Configuration | `scripts/setup.ps1`, `scripts/reset-demo.ps1` | Clean reproducible local configuration | **VERIFIED** |
| **G7-13** | Complete Hackathon Demonstration | `docs/DEMO_WALKTHROUGH.md`, E2E demonstration spec | 9-scene uninterrupted offline user journey | **VERIFIED** |
| **G7-14** | Hackathon Technical Defense | `docs/HACKATHON_TECHNICAL_DEFENSE.md` | Core architecture, trade-offs, limitations | **VERIFIED** |
| **G7-15** | Presentation Artifacts | Summary, architecture diagram, benchmark tables | Clean developer & judge presentation packet | **VERIFIED** |
| **G7-16** | Final Testing Matrix | Unit, property, integration, E2E, performance | All suites green | **VERIFIED** |
| **G7-17** | Quality Gates Enforcement | Release gates (Security, Data Integrity, Verification, A11y) | All release criteria satisfied | **VERIFIED** |
| **G7-18** | Final Verification Pipeline | `scripts/verify.ps1` with benchmark & security steps | Exit code 0 | **VERIFIED** |
| **G7-19** | Release Evidence Manifest | `var/release/manifest.json` | Hash-verified release packet | **VERIFIED** |
| **G7-20** | Manual Product Review | 10 screens inspected in Chromium | Real visual verification evidence | **VERIFIED** |
| **G7-21** | Code Quality & Architecture Audit | Architecture clean, no unmitigated debt | Refactoring & clean code verified | **VERIFIED** |

---

## 6. Open Owner Decisions (O-1..O-5) & Release Boundaries

The following owner decisions remain explicitly open and define the non-claims of the release:
- **O-1 (Remote Push Authorization):** Local release candidate only. Repository has no remote; no code is pushed.
- **O-2 (Real Study Area & GIS Data Rights):** Bundled dataset is explicitly synthetic (`demo-graph-v1`). No real-world pedestrian network accuracy is claimed.
- **O-3 (Jurisdictionally Reviewed Rulepack):** Ruleset is labeled `DEMO_RULEPACK_NOT_LEGAL` with `legal_applicability = unverified`. No legal compliance is expressed or implied.
- **O-4 (Named Domain Reviewers):** No engineering sign-offs, certifications, or professional stamps are fabricated.
- **O-5 (Verified Construction Unit Prices):** Cost figures are labeled `demo_only`. No commercial market pricing is claimed.
