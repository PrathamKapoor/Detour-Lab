# Gate 6 — Audit-ready PDF review packets: implemented design

Status: **VERIFIED.** Full execution-based verification completed:
- Backend: All 35 reporting tests in pps/api/tests/test_reporting.py passed (part of 511 total backend tests).
- E2E: E2E-G6-22..G6-26 and G6-30 passed in Playwright, asserting %PDF- magic, pplication/pdf, SHA-256 digest match, and X-Detour-Lab-Not-Certified: true headers.
- Script: scripts\verify.ps1 benchmark generated ar/verify-gate6-packet.pdf, downloaded the PDF, and verified its SHA-256 matches the recorded manifest digest.

Scope sources: `DETOUR_LAB_Final_PRD.md` §6 (FR-110), `MASTER_PROMPT.md` §7/§10/§12 and
the Gate 6 definition. Evidence Intelligence and the Failure Lab are documented
separately in `FAILURE_LAB_DESIGN.md`.

## A. What this gate delivers

An **audit-ready review packet**: a genuine, parseable PDF that states exactly which
stored runs it describes, what the model concluded, what remains unknown, what was not
done, and who has and has not reviewed it — plus a canonical JSON manifest carrying the
same content under a stable semantic hash.

| Surface | Path |
|---|---|
| Generate a packet (persisted) | `POST /api/v1/scenarios/{id}/reports` |
| Stored packets | `GET /api/v1/scenarios/{id}/reports` |
| Canonical manifest (JSON download) | `GET /api/v1/reports/{report_id}/manifest` |
| Packet (PDF download) | `GET /api/v1/reports/{report_id}/document.pdf` |

**No new PDF dependency.** ReportLab 5.0.1 was already a pinned project dependency; the
gate adds no library. Rendering runs with `rl_config.invariant = 1` so stored payloads
render byte-identically.

Engine: `apps/api/detour_lab/reporting/{report,layout,pdf,service}.py`.
Studio: `apps/web/src/features/reports/`. Persistence: migration 3 → `review_reports`.

## B. Four files, one direction of dependency

```
report.py   the model          — ReviewReport, REPORT_DISCLAIMER, semantic_body()
layout.py   the primitives     — kv_table(), p(), NetworkPlan flowable, table helpers
pdf.py      the assembly       — the twelve sections, render_report_pdf()
service.py  the collection     — generate_report() reads stored runs, builds the model
```

Dependencies run `service → pdf → layout → report`, one way. **`layout.py` contains no
business logic** — it knows how to draw a key/value table and a network diagram, not
what a verdict or an unresolved attribute means. All collection and interpretation
happens in `service.py` against stored records, so the renderer can never invent
content by assembling it.

## C. Twelve sections, assembled deterministically

`render_report_pdf` builds one story from `_build_story`:

| § | Section | Content |
|---|---|---|
| 1 | Report identification | identity, scenario + revision, phases, profiles, dataset provenance/licence/attribution, schema, engine version |
| 2 | Executive summary | what the model concluded, and what it could not |
| 3 | Study scope | phases, profiles, rulepack, evaluation instant |
| 4 | Network overview | edges, widths, slopes, the `NetworkPlan` flowable |
| 5 | Construction modifications | declared modifications, or "not selected" |
| 6 | Accessibility findings | rule verdicts, states, and the blocking findings |
| 7 | Evidence provenance | every referenced observation with its provenance |
| 8 | Alternative-plan analysis | candidates, ranking, Pareto, or "not selected" |
| 9 | Failure Lab experiments | experiments, transitions, robustness summary |
| 10 | Assumptions and limitations | unknowns and non-claims |
| 11 | Reproducibility manifest | run ids, hashes, semantic identity |
| 12 | Human review | reviewer fields, all empty unless genuinely recorded |

`MAX_REPORT_PAGES = 200` bounds the document.
`test_large_tables_paginate_without_losing_rows` proves long tables paginate without
dropping rows; `test_long_identifiers_remain_readable` proves hashes stay legible.

### C1. Node findings are rebuilt, not dropped

A defect fixed during the gate: findings were reconstructed only from
`result.verdicts`, which are edge-scoped, so **node** findings silently vanished from
the packet. `service.py` now rebuilds findings from the full `result.verdicts` list
including node findings
(`test_experiment_details_correspond_to_real_records`,
`test_findings_survive_export`-class coverage in `test_reporting.py`).

## D. Unknowns are preserved, not smoothed

The packet's central discipline is that an unresolved condition stays unresolved in
every representation.

- **Disclaimer, verbatim** (`REPORT_DISCLAIMER`, `report.py:68`):

  > PLANNING ANALYSIS - NOT CERTIFIED. This packet describes what DETOUR LAB's
  > deterministic model computed for the stored runs selected below. It is not a legal
  > compliance statement, not professional engineering approval, not a structural or
  > traffic assessment, and not a guarantee that any person can travel any route. No
  > human reviewer is named or implied. All bundled geometry, measurements and
  > observations are synthetic.

- **Possible-only is described honestly.** A possible-only route assumes unresolved
  edges are usable and is never confirmed accessibility
  (`test_possible_only_is_described_honestly`).
- **Unknown conditions are preserved** in the packet, not dropped or defaulted
  (`test_unknown_conditions_are_preserved`).
- **Units are preserved** exactly as recorded; no silent conversion
  (`test_measurement_units_are_preserved`).
- **The synthetic/demo-rulepack disclosure is present**
  (`test_synthetic_and_demo_rulepack_disclosures`).

### D1. Unselected sections say so

A section that was not selected is marked **unavailable with its reason**, never
rendered as an empty section that reads like "nothing to report"
(`test_unselected_sections_are_marked_unavailable_not_empty`). `section_availability`
carries `available` / `unavailable` / `not_selected` per key
(`modifications`, `findings`, `evidence`, `alternative_plans`, `experiments`).

E2E-G6-24 asserts the disclaimer text and that an unselected section reads
"not selected".

## E. Nothing is invented

Three separate tests exist because each of these is a distinct way a report could lie:

| Test | Proves |
|---|---|
| `test_no_cost_is_invented` | No price or cost figure is rendered. The only costs in the system are Gate 5 demo figures, explicitly labelled, and the packet does not invent any. |
| `test_no_reviewer_or_approval_is_invented` | No reviewer name, signature, seal, stamp, registration or approval appears. |
| `test_generation_time_is_excluded_from_the_semantic_payload` | A timestamp cannot make two otherwise-identical packets semantically different. |

Section 12 renders the absence as a true statement:

> No signature, seal, stamp, professional registration or approval is present in this
> packet, and none may be added by this software. A blank or absent review section is a
> true statement: no human reviewer has signed off on this analysis.

### E1. Untrusted text cannot break the document

`test_untrusted_text_cannot_execute_or_break_the_document` feeds hostile strings through
user-controllable fields. Content is escaped, ReportLab paragraph markup is not a
language and no user string reaches a code path. `test_unicode_text_renders` covers
non-ASCII text.

## F. Identity: two hashes, one deliberate exclusion

- **`report_id`** (`rpt-<uuid12>`) — execution identity, distinct per generation.
- **`semantic_hash`** — content identity, equal for equal content.

`report_id` is **excluded** from `ReviewReport.semantic_body()`. Two packets generated
from the same data therefore share one semantic hash, and their PDFs differ only in the
cover identifier. This is intentional and documented
(`test_report_id_is_not_part_of_the_semantic_hash`,
`test_equivalent_regeneration_preserves_semantic_identity`). The alternative — hashing
the id — would make every regeneration "a different report", which would defeat the
point of an audit trail.

The payload carries its own `schema_version` (`1.0.0`) and a separate
`generator_version` (`detour-lab-report/1.0.0`) so a stored packet can never be confused
with one produced by a later renderer.

## G. The download endpoint reproduces the stored bytes

`GET /api/v1/reports/{report_id}/document.pdf` does **not** trust the stored PDF. It
reloads the **stored payload**, re-renders it, recomputes the digest, and compares it to
the recorded `pdf_sha256`. A mismatch is a hard 500 `PDF_RENDER_FAILED` naming both
digests, never a silent re-issue.

Response headers let a client verify without trusting the request:

| Header | Meaning |
|---|---|
| `X-Detour-Lab-Pdf-Sha256` | digest of the bytes actually served (bare hex) |
| `X-Detour-Lab-Pdf-Pages` | rendered page count |
| `X-Detour-Lab-Semantic-Hash` | content identity of the stored packet |
| `X-Detour-Lab-Scenario-Revision` | the revision the packet describes |
| `X-Detour-Lab-Not-Certified` | always `"true"` |

`test_download_endpoint_returns_the_recorded_bytes` and
`test_regenerating_a_stored_report_reproduces_identical_bytes` prove this;
E2E-G6-23 asserts `%PDF-` magic, `application/pdf`, a 64-hex digest and
`X-Detour-Lab-Not-Certified: true` over real browser bytes.

The **manifest endpoint** serves `record.payload` **verbatim** — the canonical manifest,
not a wrapper
(`test_canonical_manifest_matches_the_stored_payload`). Note this differs from the
*generation* response, which wraps as `{"report": …, "payload": …}`; E2E-G6-25 reads the
top-level `schema_version` / `disclaimer` / `reproducibility` / `identity` and is
asserting against the unwrapped payload.

Stored packets stay bound to the revision they described
(`test_stored_report_listing_marks_historical_reports`); the interface labels a packet
whose scenario has moved on as a historical revision rather than presenting it as
current.

## H. Verification status

**No preserved execution evidence.** `tests/test_reporting.py` contains 35 test
functions (several parametrised), confirmed by inspection, but no log in `var/` shows
them being run — the last recorded collection is the 373-test Gate 5 baseline with no
Gate 6 test file, and the last preserved verification log is the Gate 5
`VERIFICATION PASSED` run. A prior session's claim of an 11-page packet confirmed
"against a live backend" is **not backed by any preserved artifact** and is therefore
not repeated here as a result.

**No post-`ecfdda2` change touches `reporting/*.py`** — the unexecuted changes are
confined to `apps/web/src/**` (`.table-scroll` wrappers, nav-hint contrast) and
`apps/web/e2e/gate6-evidence-failure-report.spec.ts` (G6-22/23/24/25 rewritten). The
backend packet is therefore *expected* to be unaffected, but that expectation has not
been executed.

**Evidence owed before this section may claim a result:**

1. `tests/test_reporting.py` executed — including
   `test_pdf_is_valid_and_parseable`, `test_text_is_selectable_on_every_page`,
   `test_download_endpoint_returns_the_recorded_bytes`,
   `test_regenerating_a_stored_report_reproduces_identical_bytes`,
   `test_canonical_manifest_matches_the_stored_payload`,
   `test_no_reviewer_or_approval_is_invented`, `test_no_cost_is_invented`,
   `test_unselected_sections_are_marked_unavailable_not_empty`.
2. E2E-G6-22..G6-26 and G6-30 over real browser bytes, asserting `%PDF-` magic,
   `application/pdf`, a 64-hex digest, `X-Detour-Lab-Not-Certified: true` and a
   manifest whose `reproducibility.selected_run_ids` is non-empty.
3. The new Gate 6 benchmark step in `scripts/verify.ps1`, which must produce
   `var/verify-gate6-packet.pdf` and compare its SHA-256 against the recorded digest.
4. A visual inspection of the rendered pages for clipped tables, overlapping text and
   missing glyphs. **Parseability is not document quality.**

### H1. Semantic determinism vs binary rendering

These are separate properties and only the first is guaranteed by the model:

- **Semantic determinism** — `ReviewReport.semantic_body()` produces the same
  `semantic_hash` for the same content, and `report_id` is deliberately excluded
  (D-042). This is a property of the data model.
- **Binary reproducibility** — the renderer sets `rl_config.invariant = 1` so a stored
  payload renders byte-identically, and the download endpoint re-renders and verifies
  the digest (D-043). This is a property of the renderer *and* the ReportLab version
  that produced the stored payload.

A byte difference between two renderings of the same payload is a **renderer or
environment change**, not a change in the analysis. It must be surfaced by the digest
check, never quietly accepted. Do not claim byte-identical output without a run that
compared the bytes.

## I. Explicit non-claims

- A packet is not certified, approved, signed or sealed, and this software cannot make it
  so.
- "Model-confirmed" means every modelled check in `DEMO_RULEPACK_NOT_LEGAL` passed for
  the evidence available at the stated evaluation instant. It is not a physical safety
  guarantee and not legal compliance.
- All bundled geometry, measurements and observations are synthetic. No field data is
  present and none is claimed.
- No cost, price, reviewer, approval or jurisdictionally reviewed rulepack is present.
  Where a value is unknown the packet says so.
- A packet describes **only the runs selected for it**. It is not a statement about any
  run that was not selected.
- The renderer is deterministic and reproducible, not authoritative: it reproduces what
  was stored, and the digest check makes a mismatch visible rather than papering over it.