# Clinical Logic Spec From Video

This file translates the Loom walkthrough into implementation requirements. It intentionally preserves the existing project blocker: LOC-change timing is not validated and must remain configurable.

## Core Rule Model

### Initial Treatment Plan

- Trigger: client admission/intake.
- Due date: admission date.
- Required completion evidence:
  - initial treatment plan record exists,
  - client signature date exists,
  - staff signature date exists,
  - both signatures are on the admission date unless R3 defines a grace rule.
- Missing or mismatched evidence: `Needs Review` or `Missing Data`.

### Master Treatment Plan

- Trigger: admission date.
- Due date: admission date + 30 calendar days, pending policy confirmation.
- Required completion evidence:
  - master treatment plan record exists,
  - client signature date exists,
  - therapist/staff signature date exists,
  - signature dates are within the 30-day window.
- Source: Treatment Plan tab and printable Master Treatment Plan modal.

### Ongoing Treatment Plan Review

- Trigger: active LOC cadence and/or previous valid review.
- Required completion evidence:
  - treatment plan review record exists,
  - therapist/staff signature date exists.
- Client signature: not required for MVP review tracking, per presenter.
- Useful cross-check:
  - document `Next Review Due` date,
  - calculated due date from LOC interval,
  - displayed/created date in Treatment Plan Reviews row.

### Level Of Care Cadence

- PHP: treatment plan due every 30 days while the client is in PHP.
- IOP-5: treatment plan due every 60 days while the client is in IOP-5.
- Current LOC: latest LOC row without a discharge date.
- Historical LOC ranges: use effective/admission date through discharge/stepdown date.

### LOC Change

- The video shows a stepdown to IOP-5 on 03/30 and a review on 04/02.
- The visible due date is 05/29.
- 05/29 is consistent with 60 days from 03/30.
- 04/02 + 60 days is 06/01.
- Therefore, the app must not assume the signature date is always the recurring anchor.

Until R3/Marleigh confirms the rule, LOC-change cases should remain `Needs Review` when the anchor/window affects the result.

## Proposed Data Fields

```ts
type TreatmentPlanEvidence = {
  patientId: string
  sourceClientLabel: string
  admissionDate: string | null
  currentLevelOfCare: string | null
  levelOfCareHistory: Array<{
    levelOfCare: string
    facility?: string
    effectiveDate: string | null
    dischargeDate: string | null
    sourceEvidence: string
  }>
  treatmentPlans: Array<{
    planKind: 'initial' | 'master' | 'review' | 'loc_update'
    documentDate: string | null
    createdDate?: string | null
    staffSignatureDate: string | null
    clientSignatureDate: string | null
    reviewerSignatureDate?: string | null
    displayedNextDueDate?: string | null
    sourceEvidence: string
    conflictNote?: string
  }>
}
```

## MVP Evaluation Order

1. Normalize and validate dates.
2. Map level of care aliases to configured rule intervals.
3. Evaluate initial treatment plan against admission date.
4. Evaluate master treatment plan against admission + 30 days.
5. Evaluate current LOC and review recurrence.
6. Compare calculated review due date with displayed `Next Review Due` when present.
7. Add LOC-change rule result as `Needs Review` while unvalidated.
8. Select the most urgent valid due date for queue sorting.
9. Show all rule results and source evidence in detail view.

## Pseudocode

```ts
function evaluateTreatmentPlanTimeliness(client, settings, asOfDate) {
  const results = []
  const admission = parseDate(client.admissionDate)
  const currentLoc = findActiveLevelOfCare(client.levelOfCareHistory)
  const locInterval = getConfiguredInterval(currentLoc.levelOfCare)

  results.push(checkInitialPlan(client.treatmentPlans, admission))
  results.push(checkMasterPlan(client.treatmentPlans, admission, 30))

  const latestReview = findLatestValidReviewWithStaffSignature(client.treatmentPlans)
  const documentDue = latestReview?.displayedNextDueDate
  const signatureAnchorDue = latestReview && locInterval
    ? addDays(latestReview.staffSignatureDate, locInterval)
    : null
  const locAnchorDue = currentLoc?.effectiveDate && locInterval
    ? addDays(currentLoc.effectiveDate, locInterval)
    : null

  results.push(compareReviewDueDates({
    documentDue,
    signatureAnchorDue,
    locAnchorDue,
    locChangeValidated: settings.locChangeWindowValidated,
  }))

  return selectDashboardStatus(results, asOfDate)
}
```

## Test Cases To Add Or Revisit

| Scenario | Synthetic facts | Expected |
|---|---|---|
| Initial plan signed at admission | Admission 2026-02-26; client/staff signatures 2026-02-26 | Initial rule compliant |
| Master signed within 30 days | Admission 2026-02-26; master staff/client signatures 2026-03-03 | Master rule compliant |
| Review in PHP | Current LOC PHP; review staff signature 2026-04-02 | Next due 2026-05-02 if PHP interval remains 30 days |
| Review in IOP-5 by signature anchor | Current LOC IOP-5; review staff signature 2026-04-02 | Next due 2026-06-01 if signature anchor is validated |
| Review in IOP-5 by LOC anchor | IOP-5 effective 2026-03-30; visible next due 2026-05-29 | Needs Review until anchor rule is confirmed |
| Missing client signature on review | Staff signature exists; client signature blank | Review can still count for MVP |
| Missing staff signature on review | Client signature exists or row exists; staff signature missing | Missing Data or Needs Review |
| Document due mismatch | Visible due date differs from calculated due date | Needs Review with both dates shown |

## Current Repo Implication

The existing timeliness tests expect IOP-5 next due date `2026-06-01` from an April 2 staff signature. The video shows a document due date of `2026-05-29`, likely anchored to a March 30 LOC stepdown. This is not a simple bug fix yet; it is a product clarification item. The app should surface both dates and keep the LOC-change anchor/window unvalidated until R3 confirms the rule.
