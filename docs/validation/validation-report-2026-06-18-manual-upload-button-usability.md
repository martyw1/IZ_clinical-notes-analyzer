# Validation Report - 2026-06-18 Manual Upload Button Usability

Version under test: `1.4.2` / build `2026.06.18.2`

Scope: verify the Manual upload `Delete uploaded binder` hover/click problem, run the automated suites, run all example treatment-plan files, and sweep live UI buttons on a disposable local desktop server with synthetic data only.

## Results

| Check | Result |
| --- | --- |
| Backend pytest | Pass: `96 passed, 2 skipped` |
| Frontend Vitest | Pass: `16 passed` |
| Frontend production build | Pass |
| Example treatment-plan upload/timeliness smoke | Pass: 4 files uploaded and appeared in the timeliness dashboard |
| Computer Use availability | Pass: Windows app/session list was readable |
| Live browser Manual upload delete hover | Pass: `cursor: pointer`, `disabled: false`, `pointerEvents: auto` |
| Delete guidance click before confirmation | Pass: modal showed exact patient-ID confirmation guidance and no delete occurred |
| Confirmed synthetic binder delete | Pass: linked binder/review were removed from the disposable server |
| Main-screen button cursor sweep | Pass: zero wait/progress cursor issues across scanned active screens |

## Live UI Coverage

The live sweep used a temp SQLite database, temp uploads/logs, and a synthetic binder `SYNTH-BUTTON-001`.

Screens scanned:

- Manual upload initial: 18 buttons, 0 cursor issues
- Review queue: 60 buttons, 0 cursor issues
- Treatment plans: 33 buttons, 0 cursor issues
- Chart audit: 29 buttons, 0 cursor issues
- Checklist: 14 buttons, 0 cursor issues
- My account: 13 buttons, 0 cursor issues
- Help: 13 buttons, 0 cursor issues
- User management: 16 buttons, 0 cursor issues
- Workflow profiles: 21 buttons, 0 cursor issues
- Forensic logs: 14 buttons, 0 cursor issues
- App settings: 35 buttons, 0 cursor issues
- Manual upload confirmed delete: 18 buttons, 0 cursor issues
- Manual upload after delete: 14 buttons, 0 cursor issues

Safe live clicks included Review Queue `Export CSV`/`Export JSON`, Treatment Plans `Copy task list`, `Export task list`, selected-client `Export CSV`/`Export JSON`, timeliness status filters, all main navigation tabs, unconfirmed delete guidance, and confirmed delete of the synthetic binder.

## Notes

- The disposable server ran on `http://127.0.0.1:8772`, reported `/api/version` as `1.4.2` / build `2026.06.18.2`, and was stopped after validation.
- Temporary synthetic app-data folders were removed after validation.
- An unrelated existing desktop server on port `8000` was left running.
