# V2 rules contract

Current source 1.0.2 / build 2026.10.16.1 / stable-local-desktop. V2 is the internal architecture name, not the app release number.

The canonical `config/checklists/treatment-plan-v1.json` retains 42 ordered criteria; checklist content version is separate from app version. Active evaluation is in `backend/app/v2/services/deterministic_evaluator.py`. Available plan content covers diagnoses, goals, objectives, interventions, evidence-based/template flags, typed signature/date evidence, needs and source field inventory. Missing content does not become a passing criterion.

Initial signatures are checked on admission Day 1. A signed master plan is due within 30 calendar days of admission. Recurring PHP reviews use 30 calendar days; IOP variants and OP/Outpatient use 60 calendar days. The recurring anchor is the selected treatment plan last updated date; admission, creation, import and signed-review dates do not substitute for it. Dashboard counts select the most recently updated plan per authorized patient record. Calculated due dates are compared with source Next Review Due. A late master signature contributes to the overall status.

Overdue means an established deadline has passed. Due Soon includes today through ten Monday-Friday business days after today, with no holiday exclusions; there is no Urgent dashboard count. Compliant timing does not establish that every completeness criterion passes. Missing Data, Needs Review, Conflicting Evidence and Unable to Evaluate must remain deterministic unresolved results. Review actions such as Approved/Returned record authorized workflow decisions.

Settings displays clinical intervals read-only from the versioned rule package. The LOC-change seven-calendar-day date is an unvalidated display candidate. It remains Needs Review pending R3/Marleigh confirmation of duration, calendar/business basis and clock start. A saved local validated flag does not clear this policy gate. Clinical changes require reviewed versioned rules, tests and release validation; manager overrides cannot establish that policy.

See [operator help](../operator-help-current.md), [open blockers](../open-blockers.md) and [current validation](../validation/current-work-2026-10-16.md).

Prior-version comments are displayed separately from current-version actions for the same patient/source/plan identity. Earlier approvals and overrides do not apply to updated content. Checklist and rule package revision: 1.2.1.
