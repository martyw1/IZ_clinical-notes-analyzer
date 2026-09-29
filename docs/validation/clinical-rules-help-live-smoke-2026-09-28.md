# Clinical timing, operator Help, and live import validation — 2026-09-28

Scope: current source candidate `1.0.0` / build `2026.09.21.2` on `stable-local-desktop`. This validates the source checkout on this Windows laptop. The previously published installer and ZIP were not rebuilt or requalified.

## Source behavior

- A signed master plan later than admission plus 30 calendar days makes the overall evaluation `Overdue` when required evidence is resolved; the 42-step master-plan criterion remains independently visible.
- Settings displays effective master/PHP/IOP-OP values of 30/30/60 days. Clinical-rule edits through `PATCH /api/settings` return 409. Previously stored local clinical-setting values and an LOC validation flag do not override the versioned source rules or clear the readiness warning.
- The seven-day LOC-change date remains a display-only, unvalidated candidate. A changed-LOC case stays `Needs Review` unless higher-priority missing or conflicting evidence applies. R3/Marleigh has not confirmed the policy.
- Help now covers sign-in, exact record/version selection, status meanings, review actions, manual and Alleva imports, account recovery, troubleshooting, and safe support reporting. The treatment-plan roster restores its last saved job outcome after reopening.

## Live calls through the retained local app

The authorized administrator used the app's patient-roster and treatment-plan controls against its saved Alleva connection. These were read-only vendor pulls that wrote results to the retained local clinical database. No credentials, patient identifiers, names, or record payloads are recorded here.

| Job | Outcome | Seen | Updated | Failed records | Warnings | Errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Patient roster | Completed | 403 | 403 | 0 | 0 | 0 |
| Treatment plans | Completed | 598 | 5 | 0 | 0 | 0 |

The Treatment Plans Roster visibly displayed the saved completed job after the frontend was rebuilt and reopened: 100%, 598 seen, 5 updated, and zero failed records, warnings, or errors. Its roster loaded 657 current filtered results at the time of this check. A completed import does not itself prove the correctness of each clinical record or establish vendor contract approval.

## Verification

- Backend full suite, first run: 618 passed; one Help release-text consistency failure. Restored the required version and qualification text; that file then passed both cases.
- Backend full suite, second run: 618 passed; one unrelated packaged-launcher test exceeded its fixed 90-second subprocess timeout while concurrent app/browser/build work was active. The exact test passed alone in 20.79 seconds. All 619 backend cases have passed, though no single full-suite run finished without a timing or then-corrected Help failure.
- Frontend: 184 tests across 28 files passed; TypeScript check and production Vite build passed.
- Isolated Windows Edge office-manager smoke: three scenarios passed, with synthetic data and a separate runtime.
- Manual local UI checks: admin sign-in, Help navigation/content, read-only Settings values, live patient and plan pulls, and restoration of the completed plan job card after reopening.
- `git diff --check` was clean. Existing untracked `tmp/`, local databases, credentials, uploads, and generated smoke evidence were excluded from the source commit.

Remaining boundaries: the client Windows 10 environment and a new packaged installer were not tested in this run; the LOC-change window remains unvalidated. This report is source and laptop validation, not a new release or clinical sign-off.
