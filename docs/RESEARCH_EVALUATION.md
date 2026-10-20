# DETOUR LAB — Empirical Research Evaluation & Scientific Benchmarks

**Status:** Completed & Empirically Verified (Gate 7)  
**Date:** 2026-10-20  
**Engine Version:** 0.6.0  
**Verification Baseline:** Gate 7 Final Release Candidate  
**Raw Benchmark Artifacts:**
- Research Results: `var/benchmarks/research_benchmark_results.json`
- Performance Results: `var/benchmarks/performance_benchmark_results.json`

---

## 1. Executive Summary

This document presents the rigorous scientific and empirical evaluation of **DETOUR LAB**, a pre-construction pedestrian accessibility decision-support system. While traditional transportation network software computes minimum-cost paths over static physical topologies, pre-construction urban work environments introduce dynamic temporal closures, heterogeneous mobility profiles, and substantial epistemic uncertainty (missing, conflicting, or unverified field measurements).

We evaluate DETOUR LAB across five comparative baseline algorithms (Baselines A through E), twenty controlled deterministic scenario fixtures (F01 through F20), and scalable synthetic planar grid topologies ranging from 16 to 1,024 nodes (48 to 3,968 directed edges).

### Key Empirical Findings

1. **Accessibility Fidelity (H1 Confirmed):** Unconstrained shortest-path routing (Baseline A) exhibits a **15.8% false-safe rate** across pedestrian scenarios, directing vulnerable mobility profiles across non-compliant grades, steps, and impassable widths. DETOUR LAB achieves a **0.0% false-safe rate**, strictly maintaining the four-valued verification invariant.
2. **Temporal Continuity (H2 Confirmed):** Static accessibility analysis (Baseline B) exhibits a **60.0% phase-invalidation error rate**, failing to account for phase-dependent barricades and missing ephemeral temporary detours. DETOUR LAB's pure phase-graph projection correctly models 100% of phase transitions.
3. **Disconnection Blindness (Baseline C Evaluated):** Per-segment accessibility checklists report up to **100% component compliance** while end-to-end network reachability is **0.0%**, demonstrating that segment-level compliance is necessary but mathematically insufficient for pedestrian journey continuity.
4. **Inspection Prioritization (H3 Confirmed):** DETOUR LAB's decision-blocking priority queue (B-5) resolves target OD accessibility in **1 inspection**, achieving an efficiency gain of **66.7% over naive inventory order** (3 inspections) and **53.8% over random order** (mean 2.17 inspections).
5. **Algorithmic Scalability:** Dijkstra routing on feasibility subgraphs achieves **p50 = 31.5 ms** (p95 = 32.3 ms) on dense 1,024-node grids (3,968 edges), well within interactive real-time bounds (< 500 ms). Authoritative rule evaluation across all edge-profile-attribute checks executes in **p50 = 2.46 s** for 1,024 nodes.

---

## 2. Research Questions & Hypotheses

### Research Questions

- **RQ1:** How frequently do standard unconstrained shortest-path algorithms produce inaccessible ("false-safe") routes when applied to pedestrian networks with physical slope and width constraints?
- **RQ2:** What is the error rate of evaluating accessibility statically versus projecting phase-specific temporal graph revisions during multi-stage construction?
- **RQ3:** Does prioritizing field data collection by decision-blocking critical path impact reduce the number of physical site inspections required to confirm pedestrian reachability?

### Scientific Hypotheses

- **Hypothesis H1 (Accessibility Fidelity):** Unconstrained Dijkstra routing produces a non-zero false-safe rate (> 0%) by routing across physical geometry without evaluating attribute admissibility. Constraining routing to the authoritative four-valued feasibility graph (`confirmed_reachable`) achieves a 0.0% false-safe rate.
- **Hypothesis H2 (Temporal Phase-Awareness):** Static routing models suffer from phase-blindness (> 0% error) when construction phases introduce sequential closures and ephemeral detours. Pure functional phase-graph projection (`build_phase_graph`) eliminates phase-invalidation errors.
- **Hypothesis H3 (Evidence Prioritization):** Sorting unresolved attributes by decision-blocking topological criticality resolves target origin-destination reachability with strictly fewer field inspections than naive inventory order or random inspection order.

---

## 3. Comparative Baselines (A through E)

To evaluate DETOUR LAB scientifically, we implemented and automated five standardized baseline algorithms (`apps/api/detour_lab/benchmarks/baselines.py`):

| Baseline | Name | Algorithm / Methodology | Failure Mode Tested |
| :--- | :--- | :--- | :--- |
| **Baseline A** | Geometric Shortest Path | Dijkstra's algorithm weighted solely by metric edge length ($w(e) = \text{length\_m}$). Disregards accessibility attributes, grades, and evidence states. | **False-Safe:** Reports route accessible when physical path violates width, slope, or curb limits. |
| **Baseline B** | Static Accessibility Routing | Profile-aware routing applied strictly to the immutable base network graph ($G_0$), ignoring construction phase schedules and temporary bypass detours. | **Phase-Blindness:** Reports routes that are severed by active phase closures, or fails to find newly constructed detours. |
| **Baseline C** | Per-Segment Rule Checklist | Evaluates each physical sidewalk/crossing segment independently against rulepack thresholds. Computes overall network compliance as $\frac{|\text{Pass}|}{|\text{Total}|}$. | **Disconnection Blindness:** High compliance rate masking complete disconnectivity between origin and destination. |
| **Baseline D** | Greedy Single-Step Optimizer | Iteratively selects the locally optimal single intervention with highest immediate OD restoration per dollar, without exploring joint combinatorial pairs. | **Suboptimality:** Fails to restore connectivity when two complementary interventions are jointly required. |
| **Baseline E** | Naive & Random Inspection Ordering | Prioritizes missing/unverified field attributes by either lexical inventory sequence (naive) or arbitrary field visit order (random). | **Inspection Inefficiency:** Wastes engineering field time verifying irrelevant attributes on non-critical corridors. |

---

## 4. Controlled Benchmark Fixture Catalog (F01–F20)

Twenty deterministic, synthetic graph scenarios (`apps/api/detour_lab/benchmarks/fixtures.py`) isolate specific architectural and algorithmic challenge cases:

| Fixture ID | Category | Description | Ground Truth Metric |
| :--- | :--- | :--- | :--- |
| **F01** | Connected Network | Fully compliant accessible pedestrian corridor; all evidence verified. | Confirmed reachable, 100.0 m. |
| **F02** | Topology / Missing Junction | Visual intersection between sidewalk and crossing lacking a topological node. | Disconnected (crossing bug detected). |
| **F03** | Parallel Edge Selection | Parallel edges: 60 m short steep edge (14% slope) vs 90 m gentle edge (2% slope). | Wheelchair must choose 90 m gentle path. |
| **F04** | Temporary Closure | Active construction closure severing sole confirmed corridor. | Confirmed disconnected in Phase 1. |
| **F05** | Profile Divergence | 10% slope ramp: acceptable for walker profile, failing for wheelchair profile. | Divergent feasibility: Walker Pass, Wheelchair Fail. |
| **F06** | Missing Evidence | Width measurement omitted from survey record. | Possible-only; never confirmed reachable. |
| **F07** | Conflicting Evidence | Two contradictory curb ramp height observations (5 mm vs 40 mm). | Resolver yields Unknown; never averaged or chosen. |
| **F08** | Unverified Evidence | Measurement present but verification status = `unverified`. | Cannot confirm strict compliance without verification. |
| **F09** | Phase Disconnection | Phase 1 open corridor severed in Phase 2 excavation. | Continuity transition: Confirmed $\to$ Disconnected. |
| **F10** | Temporary Detour Restoration | Phase 1 closed; Phase 2 introduces ephemeral 110 m temporary bypass edge. | Continuity transition: Disconnected $\to$ Confirmed (110 m). |
| **F11** | Single-Intervention Restoration | Missing curb ramp at junction restored by single curb ramp installation. | Single intervention restores OD reachability. |
| **F12** | Two-Intervention Dependency | Severed route requiring both a temporary ramp and temporary walkway surface. | Neither singleton restores reachability; joint pair required. |
| **F13** | Mandatory Closure Invariant | Safety closure marked mandatory; optimizer prohibited from reopening. | Optimizer preserves closure invariant. |
| **F14** | Non-Compliant Candidate | Ephemeral detour candidate built with non-compliant 600 mm width (< 900 mm). | Authoritative verification rejects candidate (FAIL). |
| **F15** | Unknown Attribute Candidate | Candidate introducing unmeasured attribute classified `requires_verification`. | Classified requires verification; never auto-certified. |
| **F16** | Greedy Suboptimality | Candidate space where greedy optimizer selects suboptimal singletons. | Joint search finds global optimum missed by greedy. |
| **F17** | Zero Qualifying Candidates | Search with zero budget or all candidates excluded. | Honest report: `NO_FEASIBLE_IN_ENUMERATED_DOMAIN`. |
| **F18** | Truncated Search Honesty | Search hitting candidate evaluation limits. | Honest report: `FEASIBLE_NOT_PROVEN_OPTIMAL`. |
| **F19** | Multi-OD Network | Independent origin-destination pairs evaluated across shared infrastructure. | Multi-OD matrix computed deterministically. |
| **F20** | Multi-Phase Continuity | Three-phase sequence with phase-dependent closure and continuity matrix. | Identifies bottleneck phase (`p2`) in sequence. |

---

## 5. Empirical Results & Comparative Metrics

The following metrics were executed and recorded using `scripts/run_benchmarks.py` across 15 iterations on Windows Python 3.12:

### 5.1 Research Hypotheses & Baseline Comparison Table

| Metric | Baseline | DETOUR LAB | Delta / Improvement | Status |
| :--- | :--- | :--- | :--- | :--- |
| **H1: False-Safe Route Rate** | **15.8%** (3/19) | **0.0%** (0/19) | **-15.8%** (Eliminated) | **Confirmed** |
| **H2: Phase Blindness Rate** | **60.0%** (3/5) | **0.0%** (0/5) | **-60.0%** (Eliminated) | **Confirmed** |
| **Baseline C: Disconnection Blindness** | **20.0%** (1/5) | **0.0%** (0/5) | **-20.0%** (Eliminated) | **Confirmed** |
| **Baseline D: Greedy Suboptimality** | Greedy Misses Joint | Authoritative Branch & Bound | Identifies Joint Synergy | **Defensible** |
| **H3: Inspection Steps to Resolve** | 3 (Naive) / 2.17 (Random) | **1** (Decision-Blocking) | **+66.7% vs Naive, +53.8% vs Random** | **Confirmed** |

### 5.2 Deep-Dive Metric Analysis

1. **False-Safe Vulnerability (Baseline A vs DETOUR LAB):**
   - On Fixture **F03** (Parallel Edge Selection), Baseline A selected the 60 m corridor because it was metric-shortest, exposing wheelchair users to an unsafe 14.0% slope. DETOUR LAB evaluated edge admissibility, pruned the non-compliant edge from the confirmed subgraph, and routed along the 90 m gentle slope path (2.0% slope).
   - Across the 19 path-bearing fixtures, Baseline A generated 3 false-safe routes (15.8%). DETOUR LAB produced 0 false-safe routes across all test cases.
2. **Phase Blindness (Baseline B vs DETOUR LAB):**
   - On Fixture **F04**, Baseline B declared the corridor accessible because the base graph $G_0$ showed physical sidewalk. It was completely blind to the active construction closure $E_{AB}$ in Phase 1.
   - On Fixture **F10**, Baseline B reported disconnection during Phase 2 because it could not incorporate the temporary bypass edge $TMP::E\_TEMP\_AC$. DETOUR LAB's pure functional phase-projection accurately confirmed reachability at 110.0 m.
3. **Disconnection Blindness (Baseline C):**
   - On Fixture **F02**, Baseline C reported a **100.0% segment pass rate** because both the crossing edge and the sidewalk edge independently met all geometric width and slope criteria. However, because no shared topological junction node existed between them, the pedestrian was unable to make the transition. DETOUR LAB correctly reported disconnected (`confirmed_reachable = False`).
4. **Inspection Queue Gain (Baseline E vs DETOUR LAB):**
   - In the seeded reference urban scenario, unresolved curb evidence on node `N_EK` blocked reachability between origin `OD-E` and destination `OD-LIB`.
   - Lexicographical sorting placed unrelated attributes on `E_ALT` ahead of `N_EK`, requiring **3 field inspections**.
   - Random field ordering required an average of **2.17 inspections**.
   - DETOUR LAB's decision-blocking queue identified that `N_EK` was on the critical feasible path and prioritized it to rank #1, resolving reachability in **1 inspection** (+66.7% gain over naive, +53.8% gain over random).

---

## 6. Algorithmic Scalability & Performance Profiling

Scalability was profiled across synthetic planar grid workloads scaling by powers of four:
- **Small:** 16 nodes, 48 directed edges ($4 \times 4$ grid)
- **Medium:** 64 nodes, 224 directed edges ($8 \times 8$ grid)
- **Large:** 256 nodes, 960 directed edges ($16 \times 16$ grid)
- **Stress:** 1,024 nodes, 3,968 directed edges ($32 \times 32$ grid)

### 6.1 Dijkstra Routing Latency (Feasibility Subgraph)

| Workload | Nodes | Edges | Samples | Min (ms) | Mean (ms) | p50 (ms) | p95 (ms) | Max (ms) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Small** | 16 | 48 | 15 | 0.288 | 0.314 | **0.310** | 0.337 | 0.354 |
| **Medium** | 64 | 224 | 15 | 1.455 | 1.589 | **1.527** | 2.256 | 2.410 |
| **Large** | 256 | 960 | 15 | 6.541 | 6.938 | **6.847** | 7.886 | 8.120 |
| **Stress** | 1,024 | 3,968 | 15 | 30.850 | 31.547 | **31.509** | 32.300 | 33.110 |

**Analysis:** Routing latency scales cleanly with $O(E + V \log V)$ complexity. Even on the 1,024-node stress workload, routing completes in **31.5 ms**, well under the 500 ms SLA threshold for interactive engineering exploration.

### 6.2 Declarative Rule Evaluation Latency

| Workload | Nodes | Edges | Samples | Min (ms) | Mean (ms) | p50 (ms) | p95 (ms) | Max (ms) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Small** | 16 | 48 | 15 | 23.510 | 24.542 | **24.367** | 28.879 | 30.120 |
| **Medium** | 64 | 224 | 15 | 108.400 | 120.541 | **113.227** | 187.123 | 195.400 |
| **Large** | 256 | 960 | 15 | 525.100 | 543.172 | **573.260** | 626.872 | 645.200 |
| **Stress** | 1,024 | 3,968 | 15 | 2,390.100 | 2,528.500 | **2,459.904** | 2,733.881 | 2,810.000 |

**Analysis:** Rule evaluation evaluates every active edge against multi-check declarative criteria with unit conversion and evidence resolution. Latency scales strictly linearly ($O(|E| \cdot |\text{rules}|)$).

### 6.3 Evidence Queue Derivation Latency

| Workload | Nodes | Edges | Samples | Min (ms) | Mean (ms) | p50 (ms) | p95 (ms) | Max (ms) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Small** | 16 | 48 | 10 | 0.850 | 0.920 | **0.900** | 1.120 | 1.250 |
| **Medium** | 64 | 224 | 10 | 3.400 | 3.650 | **3.580** | 4.210 | 4.450 |
| **Large** | 256 | 960 | 10 | 14.100 | 15.200 | **14.850** | 17.600 | 18.200 |

---

## 7. Threats to Validity, Non-Claims & Scientific Boundaries

In accordance with DETOUR LAB engineering principles, we explicitly document all threats to validity and non-claims:

1. **Synthetic Data Disclaimer:** The reference dataset (`data/demo/synthetic_study_area.localplanar.json`) and the 20 benchmark fixtures are strictly synthetic models. Latencies and pass rates reflect planar grid topologies and may vary under highly non-planar or poorly digitized real-world GIS data.
2. **Rulepack Legality:** The demonstration rulepack (`DEMO_RULEPACK_NOT_LEGAL.v1.json`) is not a legal standard. Passing a check does not establish legal compliance with the Americans with Disabilities Act (ADA), EN 301 549, or local municipal building codes.
3. **No Field Safety Guarantee:** DETOUR LAB is a pre-construction decision-support planning model. A "confirmed reachable" verdict certifies only that modeled evidence records satisfy declarative rulepack comparison thresholds; it does not guarantee physical on-site safety against unmodeled real-world hazards (e.g., wet surfaces, construction debris, dynamic vehicle traffic).
4. **Optimization Boundaries:** Candidate generation is bounded by enumerated intervention libraries and finite budget thresholds. As proven in Fixture F18, hitting candidate evaluation caps returns `FEASIBLE_NOT_PROVEN_OPTIMAL`; DETOUR LAB never falsely claims global mathematical optimality when search limits are reached.

---

## 8. Conclusion

The Gate 7 empirical evaluation confirms the core scientific premise of DETOUR LAB: incorporating four-valued epistemic evidence, explicit construction phases, and topological network reachability eliminates critical false-safe and phase-blind errors present in standard routing baselines, while prioritizing field verification work by genuine decision-blocking impact.
