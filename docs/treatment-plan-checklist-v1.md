# Treatment Plan Checklist Version 1

Source of truth: `config/checklists/treatment-plan-v1.json`

Checklist ID: `treatment-plan-v1`

Version: `1.0.0`

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
| ASAM | American Society of Addiction Medicine criteria, if used by the facility/workflow | Facility review requested |
| SMART | Specific, Measurable, Achievable, Relevant, Time-bound | Facility review requested |

## Review Statuses

- Not Reviewed
- Ready for Review
- In Review
- Needs Human Review
- Passed
- Failed
- Missing Required Data
- Error
- Finalized

## LOC-Change Blocker

The treatment-plan update window after a level-of-care change is not confirmed by R3/Marleigh. Version 1 keeps this setting configurable, marks it unvalidated in the app, and treats LOC-change timing as Needs Human Review until the blocker is resolved.

## Checklist Steps

1. Select review source
   The reviewer chooses EMR/API access or manual upload before evaluation.

2. API source discovery
   API mode uses the readiness/mock discovery boundary to surface available treatment plans and notes by review status. Live Alleva import remains disabled until official approval exists.

3. Upload source intake
   Upload mode validates supported files, size, patient identifier, and encrypted storage, then creates the same review workflow used by API-sourced items.

4. Review item status classification
   Each item receives a clear status and cannot silently pass when data is missing or conflicting.

5. Required metadata capture
   Capture or extract client identifier, document type, provider/staff, service date, plan date, review period, program/location, and source system/file.

6. Required document set check
   Verify expected treatment plans, progress notes, assessments, signatures, reviews, and supporting documents.

7. Treatment plan structure check
   Confirm problem areas, diagnoses/clinical needs, goals, objectives, interventions, target dates, review dates, staff responsibilities, client participation, and signatures.

8. Timeliness check
   Check creation, review, update, and signature timeframes and flag expired, late, missing, future-dated, or unvalidated LOC-change items.

9. Completeness check
   Flag missing sections, blank fields, placeholders, missing signatures, missing credentials, missing dates, generic language, and incomplete goals/objectives/interventions.

10. Goal/objective quality check
    Evaluate whether goals and objectives are individualized and SMART enough for clinical review.

11. Medical necessity / clinical rationale check
    Check whether diagnosis, symptoms, LOC, risks, needs, and planned services are logically connected.

12. Progress note alignment check
    Check whether notes and services connect back to active plan goals, objectives, interventions, frequency, duration, and modality.

13. Consistency check
    Flag contradictions across dates, providers, diagnosis, LOC, service frequency, client identifiers, and plan version.

14. High-risk issue detection
    Specifically flag missing plan, expired plan, unsigned plan, notes before plan creation, service not tied to plan, no measurable objective, no progress update, and unsupported frequency.

15. Evidence capture
    Store a plain-English finding, severity, checklist step, source document, date, and safe short evidence excerpt when available.

16. Human review and override
    Authorized reviewers can mark findings confirmed, dismissed, needs follow-up, or corrected with comments and audit logging.

17. Output and export
    Provide a clear report summary, severity/finding details, remediation suggestions, and CSV/JSON exports where practical.

18. Status persistence
    Save review status so the same item does not return as unreviewed unless it changes, expires, or is manually reopened.

19. Periodic monitoring
    API mode can refresh mock/API-derived status and surface new, changed, overdue, failed, or needs-review items.

20. Audit and traceability
    Record review creation, actor, source type, checklist version, app version, rules/model version where applicable, and final disposition.
