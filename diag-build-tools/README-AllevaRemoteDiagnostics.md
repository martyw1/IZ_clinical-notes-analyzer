# Standalone Remote Alleva Diagnostics

Copy this folder into:

```text
C:\Users\r3developer\OneDrive - R3 Recovery Services Inc\Development\IZ_clinical-notes-analyzer\diag-build-tools
```

## Purpose

This tool bypasses the IZ Clinical Notes Analyzer app completely.

It does **not** call `localhost`, does **not** log in to the app, and does **not** depend on the app backend being started.

It calls the remote Alleva REST API directly, but it intentionally mirrors the current app's Alleva treatment-plan assumptions:

- OAuth2 `client_credentials` token request.
- Token auth styles: `body`, `basic`, `basic_urlencoded`, `both`, and `all`.
- Patient roster source: `GET /clients`.
- Treatment-plan source: `GET /treatment-plans`.
- Patient-centered production flow: `GET /clients`, then `GET /treatment-plans?ClientId={patient_id}`.
- Active patient logic: `status.id == 1049` or status label `Active`.
- Discharged/non-active logic: `status.id == 1356` or discharged/closed/deceased/inactive-like status labels.

## Files

- `Invoke-AllevaRemoteDiagnostics.ps1` — the actual standalone PowerShell tool.
- `Run-AllevaRemoteDiagnostics.cmd` — double-click launcher.
- `Invoke-AllevaBackendQuickPulls.ps1` — compatibility wrapper that now launches the standalone remote tool.
- `Run-AllevaBackendQuickPulls.cmd` — compatibility wrapper that now launches the standalone remote tool.
- `PACKAGE-MANIFEST-AllevaRemoteDiagnostics.txt` — package manifest with file sizes and SHA-256 hashes.

## First run

Double-click:

```text
Run-AllevaRemoteDiagnostics.cmd
```

Then choose:

```text
19. Edit persistent remote settings
```

Enter the Alleva API base URL, token URL, client ID, client secret, token auth style, API version, page limit, and related settings.

The client secret is saved in a local JSON settings file using Windows DPAPI protection for the current Windows user.

## Version note

Current script version: `2026-07-06-r3-remote-alleva-diagnostics-6`.

This version includes these fixes and additions:

- Fixes the reserved `$PID` variable collision that caused `Cannot overwrite variable PID because it is read-only or constant` when running single-patient options.
- Fixes the treatment-review row creation path that could throw `Argument types do not match` after `GET /treatment-reviews page 1/10`.
- Keeps the Windows PowerShell 5.1 JSON collection-normalization fix from version 3.
- Adds option 15: full raw treatment-plan field export. This calls `GET /treatment-plans` and streams one delimited row per raw field path per treatment plan to disk.
- Adds option 16: one-screen count summary for the report/menu options, including the exact call(s) used to produce the counts.
- Adds per-run call output files: `*-calls.tsv` and `*-calls.json`.
- Adds full call metadata into every `*-summary.txt` and `*-result.json`: method, URI, redacted headers, query values, and request JSON. For `GET` calls, request JSON is `null` because no JSON body is sent.

## Troubleshooting

If you see:

```text
Cannot overwrite variable PID because it is read-only or constant.
```

replace the script with version 4 or newer. That was caused by using `$pid`, which collides with PowerShell's built-in read-only process ID variable.

If you see:

```text
Argument types do not match
```

after `GET /treatment-reviews page 1/10`, replace the script with version 4 or newer. The treatment-review row creation path was hardened.

If you see a failure immediately after `GET /clients page 1/10`, replace the script with version 3 or newer. That symptom usually means the remote response parsed successfully, but PowerShell treated the result as a single object instead of an array while the script was counting returned rows.

## Main menu reports

- Pull all patient records: `GET /clients`
- Pull active patients only: `GET /clients` + active status filter
- Pull inactive/non-active patients: `GET /clients` + non-active status filter
- Pull all treatment plans: `GET /treatment-plans`
- Pull active treatment plans: `GET /treatment-plans` + `isActive` filter
- Pull inactive treatment plans: `GET /treatment-plans` + not `isActive` filter
- Pull single treatment plan, legacy mode: `GET /treatment-plans` + client-reference filter
- Pull all patient-centered treatment plans: `GET /clients` + `GET /treatment-plans?ClientId={patient_id}`
- Pull active-patient treatment plans: patient-centered flow for active patients only
- Pull inactive-patient treatment plans: patient-centered flow for non-active patients only
- Pull single-patient production treatment plans: `GET /clients/{id}` + `GET /treatment-plans?ClientId={id}`
- Patient treatment-plan aggregate dry run: `GET /clients` + `GET /treatment-plans` + optional `GET /treatment-reviews`
- Pull treatment reviews: `GET /treatment-reviews`
- Pull all treatment-plan raw fields: `GET /treatment-plans` + streaming raw field flattening to final output files
- Show counts for every report: `GET /clients` + `GET /treatment-plans` + `GET /treatment-reviews` + optional single-patient calls

## Non-interactive examples

```powershell
.\Invoke-AllevaRemoteDiagnostics.ps1 -Report all_patient_records
.\Invoke-AllevaRemoteDiagnostics.ps1 -Report active_patients
.\Invoke-AllevaRemoteDiagnostics.ps1 -Report active_patient_centered_treatment_plans
.\Invoke-AllevaRemoteDiagnostics.ps1 -Report inactive_patient_centered_treatment_plans
.\Invoke-AllevaRemoteDiagnostics.ps1 -Report single_patient_treatment_plans -PatientId 12345
.\Invoke-AllevaRemoteDiagnostics.ps1 -Report all_treatment_plan_raw_fields
.\Invoke-AllevaRemoteDiagnostics.ps1 -Report counts_summary
.\Invoke-AllevaRemoteDiagnostics.ps1 -Report counts_summary -PatientId 12345
.\Invoke-AllevaRemoteDiagnostics.ps1 -RunRecommendedBatch
```

## Output and logs

Outputs are written under:

```text
diag-build-tools\logs
```

Each run writes:

- `*-summary.txt`
- `*-rows.tsv`
- `*-result.json`
- `*-calls.tsv`
- `*-calls.json`

Optional raw collection JSON can be enabled in settings. Keep in mind that raw output is more likely to contain PHI.

## Security notes

Generated logs, TSV files, and JSON files may contain PHI. Keep them local and access-controlled. Do not commit them to Git. Do not paste them into tickets, chat, or email unless an approved secure workflow says to do so.


## 2026-07-06 r5 fix

`all_treatment_plan_raw_fields` now uses an iterative stack-based JSON flattener instead of recursive flattening. This specifically addresses Windows PowerShell errors such as:

```text
The script failed due to call depth overflow.
```

The raw treatment-plan field export still writes one row per field path, but it avoids PowerShell call-stack overflow on deeply nested Alleva treatment-plan payloads.


## 2026-07-06 r7 clarification/fix

In raw treatment-plan export mode, the TSV is expected to grow much faster than JSONL because it writes one row per field path, while JSONL writes one line per treatment-plan object. Version r7 now flushes the JSONL writer after every plan so the raw-plan file should visibly update during long TSV flattening. If the JSONL still does not visibly change, Windows Explorer may be caching file size display; refresh the folder or check the file with `Get-Item`.

## 2026-07-06 r6 fix

`all_treatment_plan_raw_fields` now streams output directly to final files instead of holding all treatment plans and all flattened field rows in memory.

This addresses the hang / memory growth symptom where the terminal stops around:

```text
GET /treatment-plans page 2/10
```

The raw-field option now writes final output incrementally as pages arrive:

- `*-all_treatment_plan_raw_fields-FULL-raw-fields.tsv` — complete flattened output, one row per treatment-plan field path.
- `*-all_treatment_plan_raw_fields-FULL-raw-plans.jsonl` — complete raw plan objects, one JSON object per line.
- `*-all_treatment_plan_raw_fields-stream-summary.txt` — counts and final file paths.

The menu still shows a small preview in the terminal, but the complete output is the `FULL` files above. This is deliberate so the script can pull all plans and all fields without building a massive in-memory object.

New persistent settings:

- `RawFieldExportPageLimit` — defaults to `25`; lower values use less memory.
- `RawFieldExportMaxPages` — defaults to `0`, which means use `MaxPages`.

To truly pull every treatment plan exposed by Alleva, make sure `RawFieldExportMaxPages` or `MaxPages` is high enough for the number of pages returned. The script stops when a page returns fewer records than the page limit.
