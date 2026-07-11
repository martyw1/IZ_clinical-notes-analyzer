# V2 Rules Contract

The canonical checklist remains `config/checklists/treatment-plan-v1.json`, with exactly 42 ordered criteria.

The completeness engine must evaluate the full treatment-plan content graph where available, including diagnoses, behavioral definitions, goals, objectives, interventions, evidence-based flags, Wiley/template flags, signature metadata, reason for admission, initial client needs, family education needs, observed field inventory, and source field paths.

Required statuses remain: Overdue, Urgent, Due Soon, Returned, Needs Review, Missing Data, Conflicting Evidence, Unable to Evaluate, Compliant, Approved, and Not Applicable.

PHP cadence is 30 calendar days. IOP, IOP-5, IOP-19, IOP-3, OP, Outpatient, and configured non-PHP levels use 60 calendar days. The LOC-change update window remains unvalidated, configurable, and visibly blocked.

The beta.2 release-readiness update does not change the checklist or rules versions and does not turn an unresolved LOC-change case into a compliance decision.
