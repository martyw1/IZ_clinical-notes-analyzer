# Open Blockers

Date: 2026-06-04

## LOC-Change Treatment-Plan Update Window

Status: unvalidated.

The required treatment-plan update window after a level-of-care change is not confirmed by R3/Marleigh. The v0.5.0 implementation must keep this value configurable and must visibly mark it as unvalidated in admin/settings UI and operator documentation.

Current implementation state: the setting exists in the database and admin Settings UI, and the timeliness dashboard/detail output marks LOC-change cases as `Needs Review` while this blocker remains unresolved.

Until R3 confirms the rule, do not hard-code a final number of days and do not silently treat a LOC-change case as compliant. If source evidence is incomplete or conflicting, return `Needs Review` or `Missing Data` according to the deterministic rules.

Required resolution evidence:

- R3/Marleigh confirms the exact update window after LOC change.
- R3 confirms whether the window is calendar days or business days.
- R3 confirms whether the trigger date is the LOC-change date, signed review date, admission date, or another source evidence date.
- R3 confirms the user-visible label and default status for overdue LOC-change updates.
