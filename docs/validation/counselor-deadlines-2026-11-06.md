# Counselor and deadline maintenance — November 6, 2026

## S0
Existing working changes were present across the tracker and counselor implementation. No cleanup or production data changes were performed.

## Findings and changes
PHP-5 was absent from the PHP aliases despite being used by the roster. Added PHP-5, PHP 5 and PHP5 to the configured 30-calendar-day rule. IOP/OP retain 60 calendar days from plan last updated; the warning remains 10 calendar days. Unknown LOC and missing evidence remain unresolved. The LOC-change window remains configurable and unvalidated.

The counselor page waited for both complete rosters before displaying the directory. It now displays directory results independently, bounds the loading indicator to 30 seconds, and reports failed or slow loading. It also derives directory entries from explicit roster assignments and explains missing mappings. Added alphabetical counselor groups containing overdue plans sorted by descending days overdue, with exact-version links.

Source counselor evidence still requires explicitly mapped identity scope, stable staff ID, display name and a timezone-aware source timestamp. Existing records lacking this evidence cannot be attributed safely. No production mapping was inferred or live sync performed. The screenshot alone does not establish whether the installed app is waiting on slow roster evaluation or lacks mapped evidence.

## Validation
14 targeted backend tests passed. The new synthetic counselor UI test passed and the frontend production build passed. The full existing frontend suite passed 192 tests; the new counselor test passed separately. The existing backend virtual environment references another user's Python installation; checks used the available Python with the existing dependency directory. No installer was created or deployment performed.
