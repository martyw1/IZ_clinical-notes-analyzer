# Presenter Verification Steps

This converts Marleigh's walkthrough into a deterministic checklist for the Treatment Plan Timeliness Tracker.

## Full Workflow

| Step | Source timestamp | Presenter action / stated check | Evidence source in Alleva | Analyzer implication |
|---:|---|---|---|---|
| 1 | 00:00-00:06 | Start from the client chart and identify where timeline information lives. | Client Overview header, client demographics, admission date, current level of care. | The app needs a single client-level view that keeps admission date, current LOC, and treatment-plan evidence together. |
| 2 | 00:06-00:16 | Open the Treatment Plan tab and look for an Initial Treatment Plan. | Treatment Plan tab; top plan grid and lower version list. | Import/classify a treatment plan record as `initial` when TP type/version label indicates initial. |
| 3 | 00:16-00:34 | Open the Initial Treatment Plan and scroll to the signature area. Check that it was signed at intake/admission date by staff and by the client. | Initial Treatment Plan modal; client signature; staff signature; signature timestamps; client admission date. | Initial plan is compliant only when required signatures exist and align with admission date. Missing/late/mismatched signatures should be `Needs Review` or noncompliant, not silently accepted. |
| 4 | 00:34-00:53 | Check the Master Treatment Plan. It is due within 30 days of admission. | Treatment Plan grid/version row; created date or document date; Master/Wiley plan row. | Master due date = admission date + 30 calendar days unless policy changes. |
| 5 | 00:53-01:11 | Verify master timeliness by confirming the client and therapist/staff both signed the Master Treatment Plan. | Master Treatment Plan modal; client signature; staff/therapist signature; reviewer signature may also appear. | Master plan must require both client and therapist/staff signature dates within the 30-day window. |
| 6 | 01:11-01:27 | Do not use Treatment Plan version history as the primary source for ongoing treatment-plan updates. | Version history exists in Treatment Plan, but presenter says it does not pull through cleanly enough for reviews. | Use version history as supporting evidence only. Primary ongoing review evidence should come from Treatment Plan Reviews. |
| 7 | 01:27-01:42 | Move to Treatment Plan Reviews after initial and master are verified. | Current Overview panel, Treatment Plan Reviews tab/row. | The tracker needs a distinct `review`/`loc_update` evidence type separate from initial/master. |
| 8 | 01:42-01:58 | Cross-check Level of Care to understand why the review was done. | Level of Care tab in Current Overview. | LOC history is required for review cadence and for explaining due date calculations. |
| 9 | 01:48-02:04 | Identify a stepdown to IOP-5 on 03/30 and a review completed on 04/02. The review reflects the new IOP-5 level of care. | Level of Care rows and Treatment Plan Review row/modal. | Treat level-of-care changes as timeline triggers, but keep the exact post-change window configurable until confirmed. |
| 10 | 02:04-02:12 | While in PHP, treatment plans are due every 30 days within that PHP date range. | LOC history row for PHP with admission and discharge/stepdown dates. | PHP recurrence interval = 30 days. This should be source-configurable in rules. |
| 11 | 02:12-02:21 | In IOP-5, treatment plans are due every 60 days. Active LOC is inferred because the IOP-5 row has no discharge date. | LOC row for IOP-5 with admission/effective date and blank discharge date. | IOP-5 recurrence interval = 60 days. Current LOC = latest LOC row without discharge date. |
| 12 | 02:21-02:31 | Expect a new treatment plan within 60 days of the relevant IOP-5 date. | LOC created/effective date and/or treatment-plan review created/signature date. | Open question: anchor date may be LOC effective date, review created date, staff signature date, or document due field. Do not hard-code without validation. |
| 13 | 02:31-02:45 | Open Treatment Plan Review. For MVP, focus on dates first; other content may be valuable later. | Treatment Plan Review document modal. | Date extraction and explainable evidence should ship before broader content extraction. |
| 14 | 02:45-02:53 | Find the review's displayed next due date: 05/29. | Treatment Plan Review Note section, `Next Review Due` field. | The document-provided due date is useful evidence and may supersede or cross-check calculated due dates. |
| 15 | 02:53-03:05 | Verify when the therapist signed the Treatment Plan Review. The client does not always have to sign reviews. | Staff Signature section in review modal. | For ongoing reviews, therapist/staff signature date is the primary completion evidence. Client signature is optional for this MVP rule. |
| 16 | 03:05-03:25 | Use IOP-5 cadence to prompt the next due date and alert the user. | Review signature date, LOC row, Next Review Due field. | Dashboard should calculate/show due date, days remaining, and alert status for each active client. |
| 17 | 03:25-03:45 | Current manual process: when reviews come for signature, Marleigh checks the date shown in the document and makes sure it generally matches the expected interval. | Treatment Plan Review Note `Next Review Due`, signature section. | Add an evidence comparison: `document_due_date` versus `calculated_due_date`, with conflict handling. |
| 18 | 03:45-04:03 | Current manual process: Marleigh records the next due date in Asana for nearly 60 clients. | Asana is discussed but not shown. | Replace manual cross-app tracking with in-app due-date queue, reminders, exportable task list, or Asana-ready output. |
| 19 | 04:03-04:09 | Trust and accuracy are the key value requirements. | Presenter statement. | Every status should be explainable with source evidence and should surface missing/conflicting data. |

## Minimum Evidence Fields

- Client identifier used by the app.
- Permitted display name or de-identified label.
- Admission date.
- Current level of care.
- Level-of-care history: level, facility if available, effective/admission date, discharge date, source evidence.
- Initial treatment plan: document date, staff signature date, client signature date, source location.
- Master treatment plan: document date, staff signature date, client signature date, source location.
- Treatment plan review: document/created date, staff/therapist signature date, optional client signature date, displayed next-review due date, source location.
- Rule config: LOC recurrence intervals and LOC-change update window.

## Status Handling

- `Compliant`: required dates and signatures exist and satisfy validated timing rules.
- `Due Soon` / `Urgent` / `Overdue`: calculated from next due date and evaluation date.
- `Needs Review`: conflicting evidence, unvalidated LOC-change rule, mismatch between document due date and calculated due date, or policy ambiguity.
- `Missing Data`: required admission date, LOC, signature date, or source evidence is missing.

## Open Questions From The Video

1. The visible `Next Review Due` is 05/29/2026 after an IOP-5 stepdown effective 03/30/2026 and a staff signature on 04/02/2026. That date aligns with 60 days from 03/30, not a straightforward 60 days from 04/02. Confirm the anchor date.
2. Confirm whether PHP and IOP-5 intervals are calendar days or business days.
3. Confirm whether a review created shortly after LOC change satisfies the LOC-change requirement or if another update window applies.
4. Confirm when reviewer signature matters versus staff/therapist signature.
5. Confirm whether the document-provided `Next Review Due` should be treated as authoritative, a cross-check, or user-entered advisory evidence.
