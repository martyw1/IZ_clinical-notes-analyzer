# Implementation Backlog From Video

Use this as a build queue after the extraction artifacts are reviewed.

## S0: Preserve Safety And Evidence

- Keep raw video/capture files ignored.
- Use synthetic fixtures for tests, screenshots, docs, and demos.
- Do not copy patient identifiers from the video into production fixtures.
- Add explicit source-evidence strings to every derived result.
- Keep LOC-change timing visibly unvalidated until R3 confirms it.

## S1: Data Model And Import Mapping

- Add or verify fields for `displayed_next_due_date`, `reviewer_signature_date`, and `source_section`.
- Distinguish plan kinds: `initial`, `master`, `review`, `loc_update`.
- Store LOC history with effective date and discharge date.
- Normalize LOC aliases: PHP, PHP-5, IOP 5, IOP-5, IOPF if confirmed.
- Mark review client signature as optional for MVP.

## S2: Rule Engine Updates

- Compare three dates for reviews:
  - document displayed due date,
  - latest staff signature + current LOC interval,
  - current/changed LOC effective date + interval.
- If dates conflict, return `Needs Review` with all dates visible.
- Keep existing deterministic `Missing Data` behavior for absent admission, LOC, signatures, or document evidence.
- Add explicit tests for the 05/29 versus 06/01 ambiguity using synthetic data.

## S3: UI Changes

- Add an evidence comparison panel to the Timeliness detail view.
- Add quick filters for `Overdue`, `Urgent`, `Due Soon`, `Needs Review`, and `Missing Data`.
- Add a source-jump/evidence drawer pattern inspired by the Alleva document modal.
- Show the `Next Review Due` date from source documents when present.
- Add an export/copy queue action for Asana-style manual tracking.

## S4: Validation With R3

- Ask Marleigh to confirm the due-date anchor for LOC-change reviews.
- Ask whether PHP/IOP intervals are calendar or business days.
- Ask whether the document `Next Review Due` field should be authoritative.
- Ask whether reviewer signatures should ever affect compliance.
- Ask whether a stepdown review must be completed within a separate LOC-change update window.

## Suggested Acceptance Checks

- The dashboard can explain why a client is `Needs Review`.
- Detail view shows document due date and calculated due date side by side.
- Initial and master plan checks require the right signatures.
- Ongoing review check does not require a client signature.
- Missing/conflicting evidence never displays as compliant.
- No raw video frame, transcript, or PHI-like fixture is staged.
