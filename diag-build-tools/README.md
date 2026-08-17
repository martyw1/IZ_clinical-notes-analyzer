# Alleva Diagnostic and Complete Export Tool

`Invoke-AllevaEndUserTools.ps1` and `Run-AllevaEndUserTools.cmd` are the supported diagnostic-tool pair. Keep the two files together in this folder.

This folder is a standalone, local-first Windows CLI utility for inspecting Alleva patient and treatment-plan data and producing reviewable exports. It calls Alleva directly; it does not start or connect to the IZ Clinical Notes Analyzer application.

## Current folder contents

| Path | Purpose |
|---|---|
| `Run-AllevaEndUserTools.cmd` | Recommended Windows launcher. It locates Windows PowerShell 5.1, starts the script with a process-only execution-policy bypass, forwards arguments, preserves the PowerShell exit code, and pauses after double-click runs. |
| `Invoke-AllevaEndUserTools.ps1` | The complete CLI implementation: menu, encrypted settings, OAuth, HTTP requests, collection handling, patient-to-plan mapping, CSV/JSON output, dependency-free XLSX generation, structured logs, and synthetic self-test. Current script version: `2026-07-15-r3-alleva-complete-export-6`. |
| `README.md` | Operator and maintainer documentation for this directory. |
| `alleva-remote-diagnostics.local.json` | Local runtime settings. Created or updated by menu option 6 and encrypted for the current Windows user. Never commit or share it. |
| `logs/` | Runtime-created session directories containing privacy-filtered `events.ndjson` logs. |
| `exports/` | Runtime-created XLSX, CSV, JSON companion, and self-test output files. These files may contain PHI. |

Only the CMD launcher, PowerShell script, and README are distributable source files. The local settings, logs, and exports are machine-specific runtime data.

## Requirements

- Windows 10 or 11.
- Windows PowerShell 5.1 or PowerShell 7 or newer.
- Network access to the configured Alleva OAuth and REST endpoints for live actions.
- Approved Alleva tenant credentials for live use.
- Write access to the configured log and export directories.

Administrator access, Excel, Git, Node.js, Python, Docker, ImportExcel, and third-party PowerShell modules are not required.

## Run it

For ordinary guided use on Windows, double-click `Run-AllevaEndUserTools.cmd`. The launcher opens the menu and pauses before closing so the operator can read the result.

Recommended first-run sequence:

1. Keep `Run-AllevaEndUserTools.cmd` and `Invoke-AllevaEndUserTools.ps1` together.
2. Double-click `Run-AllevaEndUserTools.cmd`.
3. Select option 8 and confirm preflight passes.
4. Select option 6 and enter the Alleva API, OAuth, version, and paging settings supplied for the tenant.
5. Select option 7 to confirm the required values show as configured. Values remain masked.
6. Start with option 2 or 3 to validate connectivity and returned data.
7. Use option 1 when a complete patient-and-treatment-plan XLSX is required.

Command Prompt examples:

```bat
Run-AllevaEndUserTools.cmd
Run-AllevaEndUserTools.cmd -Action ExportAll -NoPause
Run-AllevaEndUserTools.cmd -Action SelfTest -NoPause
```

PowerShell examples:

```powershell
.\Invoke-AllevaEndUserTools.ps1
.\Invoke-AllevaEndUserTools.ps1 -Action ExportAll -NoPause
.\Invoke-AllevaEndUserTools.ps1 -Action SelfTest -NoPause
```

The actions are:

- `Menu`: guided patient-roster, treatment-plan, patient-detail, and export workflows.
- `ExportAll`: retrieves the complete patient roster and every treatment-plan list/detail field, then writes one XLSX workbook.
- `SelfTest`: uses synthetic patient, plan, and detail providers and never calls Alleva. It still exercises the normal settings-loading and export paths, then writes a synthetic validation workbook and PASS result. An unreadable local settings file may produce a warning, but no saved connection is used for the synthetic requests.

`-NoPause` is intended for automation and CI. It prevents a noninteractive run from waiting for a key press. Any argument-bearing CMD run also skips the launcher pause and returns the exact PowerShell exit code.

Useful PowerShell path overrides are also available:

```powershell
.\Invoke-AllevaEndUserTools.ps1 `
  -Action ExportAll `
  -SettingsPath 'C:\secure\alleva-settings.json' `
  -LogDirectory 'C:\secure\alleva-logs' `
  -ExportDirectory 'C:\secure\alleva-exports' `
  -NoPause
```

`-WorksheetRowLimit`, `-NoRun`, and the provider/failure-hook parameters are test seams for maintainers. They are not needed for normal operation.

## Guided menu

| Option | Operation |
|---:|---|
| 1 | Pull the complete patient roster and treatment-plan collection, request every available treatment-plan detail record, map plans to patients, and publish one XLSX. |
| 2 | Pull all client records, filter the active roster locally using the configured active-status mapping, display a preview, and optionally export flattened CSV/JSON. |
| 3 | Refresh the active roster when requested, pull treatment plans, map patient identifiers and `/clients/{id}` references to roster records, display the mapping, and optionally export index and raw-list CSV/JSON files. |
| 4 | Select an active patient, list only plans associated with that patient's known IDs, retrieve full detail for one or all selected plans, display every flattened field, and optionally export CSV/JSON. |
| 5 | Select an active patient, display every flattened patient-record field, and optionally export CSV/JSON. |
| 6 | Configure API URLs, client credentials, optional scope, token authentication style, API version, paging limits, treatment-plan start date, timeout, console preview limit, and raw JSON companion behavior. |
| 7 | Show script paths, version, configured-state flags, paging bounds, timeout, and output settings without printing credentials or connection values. |
| 8 | Check PowerShell version, required built-in commands, and log/export directory writability. |
| 9 | Show the current run's log directory and export directory, and optionally open the export directory in File Explorer. |
| 0 | Exit the menu. |

Menu workflows catch errors, display the reason, and return to the menu. Noninteractive `ExportAll` returns exit code `0` only for a COMPLETE export; an INCOMPLETE export is preserved but returns a nonzero exit code.

## Architecture

```text
Run-AllevaEndUserTools.cmd
        |
        v
Invoke-AllevaEndUserTools.ps1
        |
        +-- action router: Menu | ExportAll | SelfTest
        +-- encrypted settings and privacy-filtered session logging
        +-- OAuth token acquisition and authenticated Alleva GET requests
        +-- collection normalizer, completeness checks, deduplication, and safety cap
        +-- patient identity index and treatment-plan relationship mapping
        +-- interactive tables and focused CSV/JSON exporters
        +-- encrypted row spools and streaming OOXML workbook writer/validator
```

The script is intentionally a single-file Windows utility. It uses built-in PowerShell and .NET APIs for TLS, OAuth, JSON, DPAPI protection, encrypted temporary records, ZIP packaging, XML writing, and CSV output.

The complete-export pipeline works as follows:

1. Load and decrypt settings for the current Windows user.
2. Acquire and cache an Alleva OAuth access token for the process.
3. Retrieve the complete client collection and build a canonical patient index using primary IDs plus safe `clientId` and `patientId` aliases.
4. Retrieve the treatment-plan list collection and extract direct patient IDs or `/clients/{id}` foreign-key references.
5. Request each treatment plan's detail endpoint serially, retrying only eligible transient failures.
6. Flatten every returned patient, plan-list, and plan-detail field without maintaining a fixed vendor-field allowlist.
7. Stream encrypted intermediate rows, create and validate the XLSX package, then atomically publish the final workbook.
8. Remove encrypted spools and the temporary patient identity index in a `finally` cleanup path.

The encrypted patient identity index is created under the current user's Windows temporary directory, not under a OneDrive-backed export folder. Final exports and atomic workbook staging files remain in the configured export directory. No database or long-running service is used.

Collection responses may be bare arrays or common JSON envelopes. The collector recognizes explicit terminal metadata, validates continuation values and totals, deduplicates overlapping pages, detects repeated pages or contradictory metadata, and enforces the configured safety cap. Complete exports request a large snapshot from cursor zero because the current Alleva tenant returns unpaged bare arrays and ignores common page/cursor variants.

## Complete XLSX export

The dependency-free writer uses built-in .NET ZIP and XML APIs. It does not require Excel, ImportExcel, or another third-party module to create the workbook.

The workbook contains:

- `Summary`: overall COMPLETE/INCOMPLETE status, pagination/detail/mapping counts, and workbook reconciliation counts.
- `Patient Roster`: one row per patient with the exact patient ID and untruncated full, legal first/middle/last, and preferred names plus core status/date fields.
- `Patient Fields`: every scalar field returned for every patient, including nested and previously unknown fields.
- `Treatment Plans`: one row per treatment plan, mapped to the roster identity when available.
- `Treatment Plan Fields 1`, `Treatment Plan Fields 2`, and so on: every list and detail scalar field, kept in separate `list` and `detail` source scopes.

Every sheet freezes the header row and enables filters. Very large sheets split at Excel's row limit, and long values are stored in ordered chunks of at most 32,000 UTF-16 characters so the data remains navigable and recoverable. Identifiers and formula-like text are written as text.

The export is COMPLETE only when pagination reaches a valid terminal condition, required IDs exist, every plan-detail request succeeds, and every treatment plan maps to the roster. `ExportAll` always begins both independent collections at cursor `0`; the saved interactive cursor is not used for complete exports. The configured `MaxPages` value is a hard safety cap (1 through 10,000). Reaching it before a proven terminal response produces an INCOMPLETE workbook. A partial pagination result, missing ID, detail failure, identity conflict, or unmapped patient likewise produces an INCOMPLETE workbook and a nonzero process exit while preserving successfully retrieved rows for review. It never labels partial data COMPLETE.

Patient identity from a treatment-plan list response and identity from its detail response are evaluated independently. A missing identity may be supplied by the other response, but conflicting patient or plan IDs are not guessed: the ambiguous summary association is blank, source fields remain available in their original `list` or `detail` scope, and the export is marked `IDENTITY_CONFLICT` / INCOMPLETE.

The two wide data sheets contain one column for every flattened field path observed during that run:

- Patient fields use a `patient.` prefix.
- Treatment-plan list fields use a `list.` prefix.
- Treatment-plan detail fields use a `detail.` prefix.
- Relationship columns retain the treatment-plan ID, canonical patient ID, raw list patient reference, detail patient reference, and mapping status.

This means column counts can change when Alleva adds fields or returns a field only for certain records. For smaller exports, the long-form field sheets are retained as an audit-friendly duplicate representation. When those sheets would exceed 25,000 rows, they are omitted to prevent a long, apparently stalled workbook build; every retrieved field remains available in the wide patient and treatment-plan columns, and the Summary sheet reports whether long-form sheets were included and how many duplicate rows were omitted.

Treatment-plan detail requests run serially. Timeout, HTTP 429, and HTTP 500 through 599 responses may use at most four total attempts. A single retry delay is capped at 60 seconds and cumulative retry delay at 180 seconds. Other HTTP status codes are not retried. Treatment-plan IDs are URI-escaped before request paths are built.

Workbook publication is atomic: the tool writes and validates a temporary package before replacing the final XLSX. A failed write, close, or validation does not publish a new final workbook.

Option 1 can take substantially longer than options 2 or 3 because it makes one detail request per treatment plan and writes every returned scalar field. Repeated `GET /treatment-plans/{id}` progress messages are expected. Do not close the window while the export is retrieving details or building the workbook.

## Outputs and filenames

- Complete workbooks: `alleva-complete-export-<timestamp>-<nonce>-COMPLETE.xlsx` or `...-INCOMPLETE.xlsx`.
- Focused exports: collision-resistant `alleva-focused-csv-...csv` names with an optional adjacent JSON companion.
- Self-test result: `alleva-end-user-self-test-<nonce>.json` plus its synthetic validation workbook.
- Session log: `logs/end-user-session-<timestamp>/events.ndjson`.

Console tables obey `ConsoleRowLimit`; a shortened console preview does not mean the export was shortened. CSV and XLSX output include all retrieved rows for that workflow.

## Settings reference

| Setting | Meaning |
|---|---|
| `AllevaApiBaseUrl` | Base URL for Alleva REST requests. |
| `AllevaTokenUrl` | OAuth token endpoint. |
| `ClientId` / client secret | Tenant credentials. The saved settings envelope is protected with Windows DPAPI for the current user. |
| `Scope` | Optional OAuth scope; it may legitimately be blank for a tenant. |
| `TokenAuthStyle` | `body`, `basic`, `basic_urlencoded`, `both`, or `all`. Multiple styles are attempted only when selected. |
| `ApiVersion` | Sent as the Alleva API version/header value. |
| `Limit` / `Cursor` | Interactive collection request size and starting cursor. Complete exports override these with their completeness-oriented query. |
| `StartDate` | Treatment-plan lower-bound date sent when applicable. |
| `MaxPages` | Hard collection safety cap from 1 through 10,000. |
| `TimeoutSeconds` | HTTP timeout from 1 through 300 seconds. |
| `ConsoleRowLimit` | Maximum displayed preview rows from 10 through 2,000. |
| `WriteRawJsonCompanion` | Whether focused CSV exports also save the original records as JSON. |

Settings encrypted by one Windows user normally cannot be decrypted by another user or on another machine. Re-enter credentials through option 6 after moving the tool to a different Windows account or computer.

## Privacy and local files

XLSX exports contain PHI, including patient names. Keep `exports` local and access-controlled; do not place its contents in Git, tickets, email, or chat. The tool's structured logs contain only allowlisted event names, endpoint labels, status, durations, and aggregate counts. They do not contain payloads, names, patient identifiers, URLs, credentials, usernames, machine names, or local paths.

The default local settings file is `alleva-remote-diagnostics.local.json`. Its entire connection payload is protected at rest with Windows DPAPI for the current Windows user; a recognized legacy plaintext file is migrated on the next successful load using an atomic, no-backup replacement. Unknown or malformed envelope formats fail closed and are not rewritten. Settings display reports configured-state flags and bounds without printing connection values. Settings, logs, and exports are ignored by Git and must remain local. Never commit vendor credentials, tokens, runtime output, or patient data.

Focused CSV/JSON exports use generic collision-resistant filenames that do not include patient-supplied identifiers. CSV values and remote-derived header/property names beginning with `=`, `+`, `-`, or `@` are prefixed as text to prevent spreadsheet formula execution.

## Live API gate

`SelfTest` is safe to run without Alleva access. Live menu and `ExportAll` requests call Alleva directly and remain operationally gated. Do not use live import/export until R3 and Alleva have approved the tenant credentials, endpoint mapping, authentication requirements, pagination, rate limits, attachment behavior, vendor documentation, and compliance handling for the environment. The tool does not make that approval decision and must not be treated as approval for production import.

If a live run cannot prove completeness, treat the workbook as INCOMPLETE and review the Summary sheet and privacy-safe event counts before any operational use.

## Troubleshooting

- **Preflight fails:** run from Windows PowerShell 5.1+ or PowerShell 7+, and confirm the selected settings, log, and export locations are writable.
- **Credentials cannot be decrypted:** the settings were probably created by another Windows user or machine. Reconfigure with option 6.
- **OAuth fails:** verify token URL, client ID/secret, token authentication style, and whether the tenant requires a scope.
- **Export is INCOMPLETE:** open the Summary sheet and review pagination termination, missing IDs, detail failures/retries, mapping misses, and identity conflicts.
- **A plan is UNMAPPED:** its returned client reference did not match a primary or alias ID in the retrieved roster. The raw reference remains in the workbook; the script does not guess by patient name.
- **The window appears busy during option 1:** detail calls are serial and full-field workbook generation is CPU- and disk-intensive. Check for continuing GET messages and allow it to finish.
- **Need a safe functional check:** run `Run-AllevaEndUserTools.cmd -Action SelfTest -NoPause`. SelfTest uses synthetic data and makes no Alleva request, although it still loads the local settings path as part of the normal export pipeline.
