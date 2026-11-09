# Eastern timestamp display — November 6, 2026

## S0 and scope
Preserved the existing work in progress. This station changes frontend rendering only. No database, API timestamp, stored evidence, export or timing-rule write behavior changed. Canonical UTC instants remain intact. Calendar-only dates remain calendar dates, including computed deadlines and evaluation dates.

## Completed change
The shared timestamp formatter uses America/New_York explicitly, independent of the browser or laptop timezone, and renders YYYY-MM-DD HH:mm EST/EDT. Intl selects daylight/standard offsets for the represented instant. Offset-bearing inputs preserve their actual instant. Naive ISO/SQLite UTC timestamps are interpreted as UTC before display. Missing/invalid inputs keep their existing readable fallback. The date-only guard avoids shifting a due date to the preceding day.

Existing formatter consumers cover dashboard refresh time, patient roster/detail synchronization times, saved-version labels, plan timeline and signatures, manager review history, forensic logs, and completed jobs. Review acknowledgements now use this same formatter with the actual EST/EDT abbreviation. Correction return times and timestamp-bearing roster service/initial plan dates use it too. HTML datetime attributes retain source wire values. Raw source evidence remains canonical for inspection. Backup names retain their canonical UTC filename convention.

## Validation
Synthetic formatter tests cover winter/year rollover, summer, both sides of spring-forward and fall-back, offset-bearing timestamps, naive UTC timestamps, date-only preservation, and invalid inputs. UI expectations and the existing Edge display-test expectations were updated to assert Eastern text while retaining original datetime attributes. No backend tests were required because this is a frontend-only display change. All 199 frontend tests passed across 32 files. TypeScript checking and the production frontend build passed. The first run exposed old UTC-label expectations, an incorrect offset test expectation and a transient criterion-selection timing failure; the corrected full rerun passed. The updated Edge display scenarios were not executed during this station. The built frontend is ready for OneDrive sync and browser refresh on the Dell.
