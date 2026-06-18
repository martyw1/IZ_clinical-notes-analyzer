# Treatment Plan Timeliness UI/UX Update

Date: 2026-06-17
Current app patch: `1.4.2` / build `2026.06.18.2`

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

- visible updated evidence queue and footer version `1.4.2` so operators can confirm the refreshed UI is being served
- video-reference color alignment using dark teal navigation, coral primary actions, restrained gray work surfaces, green compliant states, purple review states, and teal focus/evidence accents
- queue metrics for active clients, task rows, overdue, urgent, needs review, and missing data
- quick filters for `Overdue`, `Urgent`, `Due Soon`, `Needs Review`, `Missing Data`, and `Compliant`
- selected-client summary with admission date, current LOC, primary clinician/counselor, next due date, status, and evidence completeness
- evidence comparison panel showing source-document `Next Review Due`, date-clock anchor, date-clock due date, LOC-change due date, and final status
- visible `Unvalidated LOC-change rule` warning in the queue and selected-client evidence panel
- LOC history table with facility, effective date, discharge/stepdown date, cadence, current/ended state, and evidence preview
- treatment-plan evidence table with visually distinct Initial, Master, Review, and LOC-update evidence
- evidence preview modal for dates, signatures, source labels, and source-document IDs without displaying raw clinical text
- `Copy task list` and `Export task list` actions for manual Asana/task entry
- CSV/JSON exports that include both checklist/domain rows and active 42-step workflow status rows

## Supporting API/Model Changes

The backend timeliness payload now exposes optional evidence fields needed by the UI:

- LOC history: `facility`, `discharge_date`, derived `interval_days`, and `is_current`
- treatment-plan records: `displayed_next_due_date`, `reviewer_signature_date`, and `source_section`
- selected-client detail: `current_date`, `evidence_comparison`, `date_clock_anchor_date`, `date_clock_due_date`, `loc_change_due_date`, `evidence_completeness_percent`, and `missing_evidence_fields`

The deterministic rule path remains local and non-LLM. Missing/conflicting source evidence is still surfaced as `Missing Data` or `Needs Review`; the app does not silently convert ambiguous evidence into compliance.

The dashboard source cards now distinguish API readiness from manual upload: API access can show daily-monitoring readiness labels, while manual upload is labeled as an upload-time snapshot with monthly compliance-check fallback language.

## Windows Build Visibility

The desktop runtime serves `frontend\dist` when present. Version `1.4.2` keeps the Windows preflight stale-build guard so source-checkout launches rebuild the frontend when npm is available and the React source is newer than `frontend\dist`; otherwise preflight warns that the served browser UI may be stale.

## LOC-Change Ambiguity

The original video showed a practical ambiguity:

- source-document `Next Review Due`: `2026-05-29`
- staff signature plus 60 days: `2026-06-01`
- older LOC-effective plus 60-day comparison: `2026-05-29`

Version 1.4.2 uses the latest valid treatment-plan review/update date, or admission date when no later valid update exists, as the recurring date-clock anchor. PHP uses 30 calendar days and other configured treatment levels use 60 calendar days. LOC changes use a separate manager-editable 7-calendar-day preset, but that setting remains visibly unvalidated and affected records stay `Needs Review` until R3/Marleigh confirms the final rule.

## Alleva REST Sync UI

App settings now separates Alleva REST treatment-plan sync from FHIR discovery. The REST sync fields use the Alleva API base URL, OpenAPI URL, API version, record limit, startup toggle, approval checkbox, and endpoint-mapping validation checkbox. The FHIR base URL remains only for a future SMART/FHIR root endpoint if Alleva supplies one for R3's tenant.

## Remaining R3/Marleigh Questions

- Is the ongoing review due date anchored to the LOC effective date, staff signature date, document-created date, or source-document `Next Review Due`?
- Should source-document `Next Review Due` be authoritative or only a cross-check?
- Are PHP/IOP recurrence intervals calendar days or business days?
- What exact update window applies after a level-of-care change?
- When, if ever, should reviewer signature date affect compliance?
