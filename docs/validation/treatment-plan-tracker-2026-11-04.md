# Treatment Plan Tracker maintenance, November 4, 2026

The dashboard and plan evaluator share the 10-calendar-day warning rule. The
warning includes today and day ten. This station leaves the clinical deadline
calculation and the unvalidated level-of-care change window in place.

## Evidence still needed

The live Alleva gate remains closed. Verify patient-level lifecycle and LOC,
primary counselor identity and scope, and plan version and completion evidence
before enabling any new production mappings. Historical attribution and
coverage must be established before backfilling counselor performance.

## Weekly digest feasibility

The dashboard already evaluates saved plans locally. A future digest can use
the same eligibility and deadlines as the worklists once those views share a
permission-scoped data model and counselors have verified recipient mappings.
The Windows desktop runtime has no existing mail sender or scheduler. Delivery
while the app is closed needs a separately configured runner on an available
machine or an approved external service. Recipient verification, permissible
report content, approved transport, and retry deduplication are prerequisites.
No digest delivery was enabled.

## Validation scope

The frontend production build and five synthetic deadline boundary checks
passed. Those checks cover yesterday, today, day ten, day eleven, and a missing
deadline. This station does not qualify a release or a full user acceptance
test.

## Follow-up station

Patient Roster status and level-of-care filters run together with search and
source before pagination. Changing any filter resets the page in the same
update. The roster prefers the saved patient snapshot's level of care when
available, consistent with Patient Record Detail, and falls back to the saved
plan when the snapshot has no LOC.

Both synthetic roster pagination tests passed, including the Patient Roster
filter reset and Case Management lookup. The frontend production build passed.
The primary counselor filter and current workload eligibility remain pending.
C10 remains deferred, and no live Alleva sync was run.

## Dashboard and worklist station

The dashboard opens the Overdue or Due Soon roster mode and shows a count of
eligible active patient records. Both views use the existing authorized
patient scope, facility date, and latest-plan selection. Inactive, discharged,
deleted and unlinked records and saved patient snapshots with Case Management
are outside the current worklists. The All Plans roster retains saved records.

The synthetic API workflow imported two plans, reconciled the dashboard to
one due-soon roster row, opened its exact version, and verified that discharge
removed it from current counts while retaining both rows. Twelve targeted
backend tests passed. The frontend production build passed. The prior full
backend run passed 655 tests, with three Windows PowerShell policy failures.
This evidence covers the worklist path. Counselor mapping, review
acknowledgement, historical outcomes, and full user acceptance remain open.

## Overdue review station

An office manager or administrator can acknowledge a current overdue version.
The write stores the exact version, reviewer and UTC timestamp and audits the
first acknowledgement. Plan Detail renders Eastern time. The overdue roster
can reveal reviewed rows without removing them from the dashboard count.
The roster and detail use a common deadline indicator.

The synthetic API checks passed for unauthorized writes, repeated requests,
repeated imports, version isolation and the audit event. A process-only
RemoteSigned retry passed the Windows local recovery test. Two desktop
maintenance tests timed out at 15 seconds during that retry.

Counselor grouping, filtering and caseloads still require a verified
patient-to-primary-staff relationship and a stable staff identifier scope.
Historical performance requires verified completion evidence tied to a specific
deadline and historical counselor assignment. Do not infer these from display
names, latest plan dates, or app user accounts. The live Alleva gate and the
deferred digest remain in place.

The isolated Edge tracker workflow passed. It exercised sign-in, dashboard
drill-down, selection of the exact overdue plan, acknowledgement, and the
collapsed reviewed roster. The dashboard count stayed the same after review.
The expanded synthetic API workflow also passed for Case Management with an
older plan and an active client without a plan. All 192 frontend unit tests
passed and the frontend production build succeeded.

The broader isolated office-manager run passed 26 of 34 browser scenarios.
One checklist display scenario timed out. The other seven failures were in
the harness guard, two identity scenarios, metadata reuse, two legacy
dashboard metric scenarios, and dashboard recovery. The dashboard recovery
test was updated to assert the current three-tile contract. The metric
scenarios still assume removed dashboard counters and explanatory text.

## Counselor directory station

The counselor directory keys staff by explicit source scope and stable staff
ID. It records scoped patient observations so a counselor remains visible
after reassignment if the viewer can still read an observed patient. The
latest timestamped primary assignment drives roster filtering, the overdue
counselor index, and active caseloads. Conflicting assignments at the same
timestamp are unresolved. The UI exposes unassigned clients and retains
eligible clients who have no plan.

The built-in Alleva mapping still needs PHI-free confirmation of the primary
relationship, stable staff ID and identity scope. The importer only accepts
counselor evidence if all three counselor field paths are explicitly mapped
and the patient record supplies a timezone-aware source update timestamp.
No live calls were made. Historical outcome reporting requires verified
completion and attribution evidence linked to the original obligation.

The three focused synthetic API tests passed, including same-name counselor
separation, replay, retained directory entries after an unresolved update,
Case Management and discharge, and version-specific review. Both tracker
scenarios passed in isolated Edge, including exact version selection from a
counselor caseload. The full frontend suite passed all 192 tests, and the
production build passed.
