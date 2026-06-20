# Treatment Plan Checklist Version 1

Source of truth: `config/checklists/treatment-plan-v1.json`

Checklist ID: `treatment-plan-v1`

Version: `1.2.0`

Last updated: `2026-06-20`

## Purpose

This checklist is the canonical Version 1 treatment-plan workflow used by the local Windows app, backend readiness checks, `/api/treatment-plan-checklist`, CSV/JSON workflow-step exports, and the default workflow profile seed.

It is deliberately deterministic. Missing or conflicting admission dates, LOC evidence, treatment-plan dates, signatures, or source documents must produce `Missing Data`, `Needs Review`, `Conflicting Evidence`, or `Unable to Evaluate` instead of guessed compliance.

## Acronym Definitions

| Acronym | Definition | Validation |
|---|---|---|
| API | Application Programming Interface | Standard |
| EMR | Electronic Medical Record | Standard |
| PHI | Protected Health Information | Standard |
| PII | Personally Identifiable Information | Standard |
| OCR | Optical Character Recognition | Standard |
| LLM | Large Language Model | Standard |
| TP | Treatment Plan | Facility review requested |
| SUD | Substance Use Disorder | Facility review requested |
| LOC | Level of Care | Facility review requested |
| PHP | Partial Hospitalization Program | Facility review requested |
| IOP | Intensive Outpatient Program | Facility review requested |
| OP | Outpatient | Facility review requested |
| MRN | Medical Record Number | Facility review requested |
| ASAM | American Society of Addiction Medicine criteria, if used by the facility/workflow | Facility review requested |
| SMART | Specific, Measurable, Achievable, Relevant, Time-bound | Facility review requested |

## Review Statuses

Legacy chart-review statuses remain available for existing records:

- Not Reviewed
- Ready for Review
- In Review
- Needs Human Review
- Passed
- Failed
- Missing Required Data
- Error
- Finalized

Treatment-plan PRD statuses are available for Version 1.2.0 workflow steps:

- Current / Compliant
- Due Soon
- Urgent
- Overdue
- Needs Review
- Missing Data
- Conflicting Evidence
- Unable to Evaluate
- Returned for Correction
- Approved / Finalized

## Source Modes

API mode is a readiness and connectivity harness until official Alleva tenant details, endpoint mapping, scopes, pagination/rate limits, attachment behavior, vendor documentation, and compliance approval exist. Live patient import remains disabled.

Manual upload mode is a point-in-time snapshot of the files selected by the operator. It does not imply automatic weekly monitoring for large chart batches; use the documented monthly compliance-check fallback when API refresh is not available.

## Admin/Manager-Editable Workflow

Admins and office managers can open Workflow profiles, use `Seed draft from 42-step checklist`, edit the generated workflow snapshot and transition rules, and publish a new workflow profile version. The seeded draft includes checklist steps, source modes, status options, reviewer actions, override rules, audit events, and export fields. Draft versions can also be edited in place; published or archived versions can be loaded as a new draft template.

Published workflow history is preserved. Only unused draft-only profiles that were never published can be hard-deleted.

## LOC-Change Blocker

The treatment-plan update window after a level-of-care change is not confirmed by R3/Marleigh. Version 1.4.4 ships a manager-editable 7-calendar-day preset, keeps this setting configurable, marks it unvalidated in the app until R3 confirms the rule, and treats LOC-change timing as `Needs Review`, `Missing Data`, or `Conflicting Evidence` when source evidence is incomplete or inconsistent.

Do not hard-code a final LOC-change update window until `docs/open-blockers.md` is resolved.

## Date Clock and Source Evidence

The timeliness date clock uses the laptop/facility-local current date every time the app starts and while it is running. It calculates the next update date from the admission date when no valid later treatment-plan review/update exists, otherwise from the latest valid treatment-plan review/update date.

Configured PHP levels use 30 calendar days. Other configured treatment levels use 60 calendar days. LOC changes use the separate configurable LOC-change window described above.

Manual-upload evidence should include at least the readable PDF page number when extraction can identify it. API evidence should include source identifiers supplied by approved REST/OpenAPI payloads, such as source document ID, attachment URL, endpoint name, or response field path.

## Checklist Steps

1. Confirm this is the correct client chart
2. Identify whether the review is for a new chart or an existing chart update
3. Confirm the client is active
4. Confirm the admission date
5. Confirm the current LOC
6. Confirm the LOC maps to a Version 1 rule category
7. Capture LOC history when available
8. Classify each source document
9. Confirm each document date
10. Confirm each document's completion status
11. Confirm staff/therapist signature status
12. Confirm client signature status
13. Check for conflicting evidence
14. Check that the Initial Treatment Plan exists
15. Check that the Initial Treatment Plan is dated correctly
16. Check that the Initial Treatment Plan has required signatures
17. Check that the Master Treatment Plan exists
18. Check that the Master Treatment Plan was completed within 30 calendar days of admission
19. Check that the Master Treatment Plan has required signatures
20. Identify the latest valid Treatment Plan Review
21. Calculate the next Treatment Plan Review due date
22. Apply the PHP timing rule
23. Apply the IOP/OP timing rule
24. Mark the treatment plan as current when inside the allowed window
25. Mark the treatment plan as due soon when approaching the deadline
26. Mark the treatment plan as overdue when past the deadline
27. Check PHP individual-session evidence when available
28. Check IOP/OP individual-session evidence when available
29. Identify whether an LOC change occurred
30. Check for an LOC Change Update document when applicable
31. Hold the LOC-change deadline as unresolved until R3 confirms it
32. Flag missing data instead of assuming compliance
33. Allow manual reviewer confirmation
34. Require a reason for manual overrides
35. Produce a final checklist result for the chart
36. Update the status worklist after review
37. Route the chart for manager review
38. Return charts with specific correction comments
39. Approve charts only after checklist issues are resolved or accepted
40. Preserve the review history
41. Continue periodic monitoring when API access is available
42. Use synthetic or approved non-PHI data for validation until production handling is approved

## Step Contract

Every step in `config/checklists/treatment-plan-v1.json` must include:

- `step`
- `key`
- `title`
- `description`
- `source_modes`
- `status_options`
- `reviewer_actions`
- `manual_override`
- `override_reason_required`
- `audit_event`
- `export_fields`

The backend validator requires exactly 42 ordered steps and requires `override_reason_required: true` for each step.
