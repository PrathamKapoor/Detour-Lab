# RESEARCH_AND_SOURCES.md

Purpose: an auditable ledger of (a) the authoritative specification, (b) technical references whose
exact APIs are relied upon, (c) third-party licences actually used, and (d) standards deliberately
**not** encoded.

---

## 1. Authoritative project specification

| Ref | Document | Status |
|---|---|---|
| SPEC-PRD | `DETOUR_LAB_Final_PRD.md` v1.0, 18 Oct 2026 | Read in full; source of all FR/INV rows |
| SPEC-MP | `MASTER_PROMPT.md` (execution contract) | Read in full; source of gates, tests and quality rules |
| SPEC-PACK | `EXECUTION_PACK_README.md`, `prompts/00_BOOTSTRAP.md`, `prompts/01_GATE_0.md`, `prompts/02_GATE_1.md`, `prompts/03_GATE_2.md`, `prompts/09_RESUME_AND_AUDIT.md` | Read in full |
| SPEC-OWNER | Owner decisions in this session: repository path `C:\Pratham\DETOUR-LAB`; Apache-2.0 licence | Recorded in `DECISIONS.md` D-001/D-002 |

Prompt pack source directory (not copied wholesale, referenced files were placed in repo root):
`C:\Users\mlepn\Downloads\DETOUR_LAB_Flash_Prompt_Pack\DETOUR_LAB_Flash_Prompt_Pack\`.

## 2. Technical references consulted

| Topic | Reference | Used for |
|---|---|---|
| GeoJSON format | https://www.rfc-editor.org/info/rfc7946/ | Import validation rules; why the seeded demo is *not* claimed as RFC 7946 |
| Directed/weighted shortest paths | https://networkx.org/documentation/stable/reference/algorithms/shortest_paths/index.html | Routing implementation; documented multigraph + weight pitfalls |
| FastAPI response models | https://fastapi.tiangolo.com/tutorial/response-model/ | Typed API contracts |
| OR-Tools CP-SAT statuses | https://developers.google.com/optimization/cp/cp_solver | Status vocabulary for `FEASIBLE_NOT_PROVEN_OPTIMAL` etc. (DEFERRED to Gate 5) |
| WCAG 2.2 | https://www.w3.org/TR/WCAG22/ | Accessibility targets (target AA, not claimed conformance) |
| OSM attribution/licensing | https://osmfoundation.org/wiki/Licence/Attribution_Guidelines | Attribution requirements if OSM data is ever introduced |

**Retrieval status note:** these URLs are listed as the authoritative starting points required by
MASTER_PROMPT §4. Where a specific library API is used in code, the installed version's own
signature/docstring is the binding reference and is exercised by tests rather than recalled.

## 3. Third-party dependencies actually installed and their licences

Backend (`.venv`, resolved 18 Oct 2026 — versions from a real `pip install` run):

| Package | Version | Licence | Note |
|---|---|---|---|
| fastapi | 0.143.3 | MIT | |
| starlette | 1.8.0 | BSD-3-Clause | FastAPI transport |
| uvicorn | 0.54.0 | BSD-3-Clause | ASGI server |
| pydantic | 2.14.1 | MIT | validation contracts |
| pydantic-core | 2.50.1 | MIT | |
| networkx | 3.7 | BSD-3-Clause | directed multigraph algorithms |
| shapely | 2.2.0 | BSD-3-Clause | geometry validity/intersection QA |
| reportlab | 5.0.1 | BSD-3-Clause | PDF review packet (major version; import surface verified by test, not assumed) |
| numpy | 2.5.4 | BSD-3-Clause | transitive (reportlab/shapely) |
| pillow | 13.0.0 | HPND | transitive (reportlab) |
| pytest | 9.1.1 | MIT | |
| hypothesis | 6.170.1 | MPL-2.0 | property-based tests |
| httpx | 0.28.1 | BSD-3-Clause | TestClient transport |
| ruff | 0.17.1 | MIT | lint/format |
| PyYAML | 6.0.3 | MIT | rulepack authoring convenience |

Frontend dependencies are added in Gate 3 and recorded here at the same level of detail
(pin + licence + role) once installed — **no licence claim is made for anything not yet installed.**

No dependency was added without an actual successful install on this machine.

## 4. Standards referenced but deliberately NOT encoded as rules

| Standard | Why referenced | Status |
|---|---|---|
| Harmonised Guidelines and Standards for Universal Accessibility in India 2021 (DEPwD) | PRD §11.2 primary reference for an Indian pilot | Cited as inspiration only; `legal_applicability = unverified` |
| US Access Board PROWAG (R204/R303, temporary alternate pedestrian accessible routes) | PRD §11.2 reference for US scenarios | Cited as inspiration only; never presented as applicable in India |
| MUTCD 11th Edition Rev. 1 (Dec 2025) | PRD §11.2 | Referenced for phase/temporary-traffic-control context only |

Encoding any of these as an enforceable ruleset requires named professional review (see
`docs/ASSUMPTIONS_AND_LIMITATIONS.md` §4). Until then the shipped pack is
`DEMO_RULEPACK_NOT_LEGAL` and every verdict is labelled "Pass in modeled checks" / "Fail" /
"Unknown" / "Not applicable" — never "compliant".

## 5. Data sources

| Dataset | Source | Rights status |
|---|---|---|
| `data/demo/` seeded study area | Authored for this project | **100% synthetic.** No real place, no OSM extraction, no field survey |
| `data/fixtures/` regression fixtures | Authored for this project | **100% synthetic**, deterministic, no randomness in fixtures |

No OpenStreetMap data is bundled in this repository at the current checkpoint. If it is introduced
later, ODbL attribution must be visible in the interface and in every export (PRD §11.1), and the
derivation recorded here.