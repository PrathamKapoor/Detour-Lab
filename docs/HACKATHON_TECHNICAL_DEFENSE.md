# DETOUR LAB — Hackathon Technical Defense & Architectural FAQ

**Target Audience:** Expert Judges, Technical Evaluators, Civil Engineers, AppSec Auditors  
**Version:** Gate 7 Final Release Candidate  
**Date:** 2026-10-20  

---

## 1. Core Architectural & Modeling Defenses

### Q1.1: Why build an explicit pedestrian graph instead of consuming OpenStreetMap (OSM) or Google Maps APIs directly?

**Defense:**
Standard road network graphs are vehicle-centric and collapse pedestrian infrastructure into street centerline abstractions. Even OSM's pedestrian tags (`highway=footway`) suffer from three fundamental defects for accessibility decision-support:
1. **Geometric Granularity:** Wheelchair navigation depends on micro-topological features: curb ramp slopes, cross-slopes, transition lips (vertical offsets $> 6$ mm), and clear sidewalk width. Road centerlines omit these entirely.
2. **Epistemic Incompleteness:** Public GIS datasets frequently omit whether a curb cut exists or when it was last inspected. Mainstream routing algorithms treat missing data as passable (the "open-world assumption"), creating dangerous false-safe routes.
3. **Temporal Construction Dynamics:** Municipal road closures rarely reflect temporary pedestrian barricades, scaffolding corridors, or gravel detour surfaces. DETOUR LAB's explicit planar pedestrian network models physical pedestrian paths with four-valued epistemic evidence bound directly to edges and nodes.

### Q1.2: Why four-valued logic (Pass / Fail / Unknown / Not Applicable) instead of a continuous accessibility score (e.g., "85% accessible")?

**Defense:**
A probabilistic or percentage score is physically meaningless and safety-critical for individuals with mobility impairments:
- If a 1-kilometre corridor is 99% flat asphalt with a 1.8-metre width, but has a **single 150 mm unramped step** or a **25% construction slope**, a manual wheelchair user cannot traverse it. A composite score of "99% accessible" is a lethal falsehood.
- In DETOUR LAB, reachability is topological: an Origin-Destination pair is `Confirmed Reachable` if and only if there exists a contiguous path where **every constituent segment evaluates to PASS**.
- If a single segment has unmeasured width, the route evaluates to `Possible-Only (Unknown)`. If any required segment has an observed slope exceeding the threshold, it evaluates to `Fail`. We never average or blur physical barriers into misleading composite percentages.

### Q1.3: Why pure functional phase projection (`build_phase_graph`) instead of updating a mutable graph in SQLite?

**Defense:**
Construction sequencing is fundamentally multi-temporal. Projecting phase graphs as a pure function:
$$\text{PhaseGraph} = f(\text{BaseGraph}, \text{ScenarioRevision}, \text{PhaseID})$$
provides three crucial guarantees:
1. **Zero Phase Bleed:** Temporary barricades or bypasses in Phase 2 can never leak into Phase 1 or Phase 3.
2. **Concurrency & Thread Safety:** Because the base graph and scenario revisions are immutable, multiple threads or worker processes can evaluate different phases in parallel without database locks or dirty reads.
3. **Deterministic Replay:** Any past construction state can be reconstructed bit-for-bit from its revision ID and phase identifier.

---

## 2. Algorithmic Rigor, Complexity & Optimization

### Q2.1: Is candidate intervention optimization NP-hard? How does DETOUR LAB prevent combinatorial explosion?

**Defense:**
Selecting an optimal subset of interventions under budget and multi-profile constraints is a formulation of the **0/1 Knapsack Problem / Constrained Shortest Path**, which is NP-hard. We prevent combinatorial explosion through strict, explicit engineering bounds:
1. **Finite Candidate Space:** Interventions are selected from an enumerated domain ($\le 60$ candidates by default, capped at 500).
2. **Bounded Intervention Combinations:** Combinations are bounded by `max_interventions` ($\le 4$, default 2).
3. **Branch-and-Bound Pruning:** Subsets exceeding the user's budget or failing structural applicability rules are pruned before expensive graph evaluations.
4. **Honest Search Termination:** If search duration hits `max_duration_ms` or the candidate cap, the solver returns `FEASIBLE_NOT_PROVEN_OPTIMAL` rather than falsely claiming global optimality.

### Q2.2: Why use authoritative backend re-verification instead of letting an LLM or heuristic select the best detour?

**Defense:**
Heuristics and LLMs hallucinate compliance:
- An LLM or greedy heuristic might propose a modular ramp that solves connectivity but violates the minimum width rule ($600\text{ mm} < 900\text{ mm}$), or introduce an unverified surface attribute.
- In DETOUR LAB, the candidate generator is strictly a *proposer*. **Every single candidate combination must survive authoritative verification through the real rules and routing engine.** Non-compliant candidates are rejected by hard checks (as verified in Fixture F14). The frontend is an interface, never an authority.

### Q2.3: How do you guarantee Dijkstra routing terminates efficiently on large networks without infinite loops?

**Defense:**
- All edge metric lengths are validated to be strictly non-negative ($w(e) \ge 0$).
- Routing runs on indexed adjacency lists with binary min-heaps, guaranteeing $O(E + V \log V)$ execution time.
- As demonstrated in our Gate 7 scalability benchmarks, routing on a 1,024-node grid (3,968 edges) executes in **p50 = 31.5 ms**, well under our 500 ms SLA.

---

## 3. Scientific Integrity, Evidence Resolution & Epistemic Boundaries

### Q3.1: What happens when two field inspectors record contradictory measurements for the same curb cut?

**Defense:**
Standard systems either average the values (e.g., $\frac{5 + 40}{2} = 22.5\text{ mm}$) or take the latest timestamp. DETOUR LAB rejects both assumptions:
- If Inspector A records a compliant $5\text{ mm}$ lip, but Inspector B records a non-compliant $40\text{ mm}$ lip, the attribute status is marked `CONFLICTING_EVIDENCE`.
- The resolver refuses to pick a winner. The attribute state becomes `UNKNOWN`, and the route downgrades from Confirmed to Possible-Only.
- The conflict is automatically routed to the **Evidence Queue** with highest criticality so an engineer can physically re-inspect the location.

### Q3.2: Does DETOUR LAB certify legal ADA compliance or guarantee physical pedestrian safety?

**Defense:**
**EMPHATICALLY NO, and the system explicitly says so.**
- DETOUR LAB is a pre-construction decision-support prototype.
- Passing a declarative check against `DEMO_RULEPACK_NOT_LEGAL.v1.json` certifies only that the modeled mathematical representation satisfies the specified thresholds.
- It does not establish legal compliance with ADA Title II/III, PROWAG, or EN 301 549, nor does it guarantee physical safety against unmodeled real-world hazards (weather, construction vehicle crossings, moving equipment). This disclaimer is embedded on every screen, in every API error envelope, and on all 9 pages of the generated review PDF.

---

## 4. Security, Non-Repudiation & Cryptographic Reproducibility

### Q4.1: How can a city council or regulatory auditor verify that an exported engineering PDF report hasn't been modified?

**Defense:**
Every generated review packet is cryptographically anchored:
1. The report metadata and raw analytical payload are serialized into canonical JSON and stored in SQLite.
2. A SHA-256 digest is computed over the deterministic PDF byte stream and recorded in the database manifest.
3. Every page of the generated PDF displays this exact SHA-256 digest alongside the engine version and rulepack hash.
4. When a user or auditor requests the PDF, the server re-renders the document from the stored payload and verifies that the resulting digest matches the recorded manifest. If a single byte differs, the server refuses to serve the document (`PDF_REGENERATION_MISMATCH`).

### Q4.2: How does the system handle concurrent edits from multiple municipal engineers?

**Defense:**
DETOUR LAB implements **Optimistic Concurrency Control (OCC)**:
- Scenarios carry an integer `revision` counter.
- When an engineer submits an edit, the client sends `expected_revision`.
- The database executes an atomic `UPDATE ... WHERE id = ? AND revision = ?`.
- If another engineer committed a change first, the revision check fails, and the API returns **HTTP 409 `REVISION_CONFLICT`** with details on the actual revision. The system never permits silent overwrite or lost updates.

---

## 5. Summary Matrix: DETOUR LAB vs Traditional GIS

| Feature | Standard GIS / Pedestrian Routing | DETOUR LAB |
| :--- | :--- | :--- |
| **Logic Model** | Binary (Open / Closed) | Four-Valued (Pass / Fail / Unknown / N/A) |
| **Missing Evidence** | Assumed Pass (False-Safe Risk: 15.8%) | Possible-Only (False-Safe Rate: 0.0%) |
| **Conflicting Observations** | Averaged or Overwritten | Explicit Conflict Flagged for Re-inspection |
| **Construction Sequencing** | Static Snapshot (Phase Blindness: 60%) | Pure Functional Phase Projection (0% Blindness) |
| **Detour Optimization** | Manual Trial-and-Error | Authoritative Bounded Branch & Bound |
| **Inspection Guidance** | Unsorted Attribute Dump | Decision-Blocking Critical Path Queue (+66.7% Gain) |
| **Audit Defense** | Ephemeral Screenshots | Cryptographic Digest-Verified Engineering PDF |
| **Operational Boundary** | Cloud API / SaaS Dependent | 100% Offline, Local-First, Zero Third-Party Leaks |
