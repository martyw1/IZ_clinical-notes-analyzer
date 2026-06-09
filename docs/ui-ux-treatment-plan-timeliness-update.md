# Treatment Plan Timeliness UI/UX Update

Date: 2026-06-09

## Source Artifacts

This update translated the synthetic, written artifacts in `video-extract (2026-06-05)` into the production React/FastAPI app. The raw Loom video, frame captures, transcript JSON, and any PHI-like visual material remain local-only and were not copied into tests, docs, fixtures, or UI assets.

Primary inputs:

- `visual-style-guide.md`
- `ui-flow-storyboard.md`
- `verification-steps.md`
- `clinical-logic-spec.md`
- `source-evidence-matrix.md`
- `frontend-reference/TreatmentPlanTimelinessVideoMockup.tsx`
- `frontend-reference/treatment-plan-timeliness-video.css`
- `frontend-reference/mockup-data.json`

## Production UI Changes

The `Treatment plans` tab is now an evidence-first work queue instead of a passive dashboard. It keeps the existing upload-first chart-review app structure, but presents treatment-plan timeliness as a compact operational workflow:

- queue metrics for active clients, task rows, overdue, urgent, needs review, and missing data
- quick filters for `Overdue`, `Urgent`, `Due Soon`, `Needs Review`, `Missing Data`, and `Compliant`
- selected-client summary with admission date, current LOC, primary clinician/counselor, next due date, status, and evidence completeness
- evidence comparison panel showing source-document `Next Review Due`, staff-signature cadence due date, LOC-effective cadence due date, and final status
- visible `Unvalidated LOC-change rule` warning in the queue and selected-client evidence panel
- LOC history table with facility, effective date, discharge/stepdown date, cadence, current/ended state, and evidence preview
- treatment-plan evidence table with visually distinct Initial, Master, Review, and LOC-update evidence
- evidence preview modal for dates, signatures, source labels, and source-document IDs without displaying raw clinical text
- `Copy task list` and `Export task list` actions for manual Asana/task entry

## Supporting API/Model Changes

The backend timeliness payload now exposes optional evidence fields needed by the UI:

- LOC history: `facility`, `discharge_date`, derived `interval_days`, and `is_current`
- treatment-plan records: `displayed_next_due_date`, `reviewer_signature_date`, and `source_section`
- selected-client detail: `evidence_comparison`, `evidence_completeness_percent`, and `missing_evidence_fields`

The deterministic rule path remains local and non-LLM. Missing/conflicting source evidence is still surfaced as `Missing Data` or `Needs Review`; the app does not silently convert ambiguous evidence into compliance.

## LOC-Change Ambiguity

The video shows a practical ambiguity:

- source-document `Next Review Due`: `2026-05-29`
- staff signature plus 60 days: `2026-06-01`
- LOC effective date plus 60 days: `2026-05-29`

Until R3/Marleigh validates the anchor/window rule, conflicts between these anchors stay visible and the affected record is marked `Needs Review`.

## Remaining R3/Marleigh Questions

- Is the ongoing review due date anchored to the LOC effective date, staff signature date, document-created date, or source-document `Next Review Due`?
- Should source-document `Next Review Due` be authoritative or only a cross-check?
- Are PHP/IOP recurrence intervals calendar days or business days?
- What exact update window applies after a level-of-care change?
- When, if ever, should reviewer signature date affect compliance?
