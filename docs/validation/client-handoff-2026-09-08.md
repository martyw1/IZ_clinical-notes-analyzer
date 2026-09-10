# Client handoff and one-page guide validation - 2026-09-08

Current app: `2.0.0-beta.3` / build `2026.09.03.1` / `beta-local-desktop-v2`.

## S0 - Discovery

Reviewed the source and prepared-release entry points, preflight, generated installer, runtime entry point, stop/restart, diagnostics, backup/restore and admin recovery. No client install, upgrade, uninstall, clinical-data access, credential access or dependency download was performed.

An independent read-only audit confirmed that packaged ordinary install/launch uses the bundled runtime. Source double-click startup passes `-AssumeYes` and can install user-scoped Python and repo-local dependencies. No machine-wide firewall/service/registry change was found in the inspected packaged scripts. Third-party installer effects are not covered by that statement.

## S1 - Deliverables

- `docs/client-handoff-checklist.md`: exact prepared-package root files, wrapper dependencies, source-copy allowlist, optional trimming proposal, omissions, startup checks and limitations.
- `output/pdf/IZ-Clinical-Notes-Analyzer-Quick-Start.pdf`: one US Letter page, restrained green/white styling, four launch steps, preparation, three troubleshooting rows and closeout advice. It covers the prepared-release path and correctly instructs the user to open the browser.
- Existing application code, dependencies, version metadata and release binaries were not changed by this handoff task. The existing candidate predates September 8 Help changes; a newly current package must be rebuilt and validated separately.

## S2 - Checks completed

| Check | Result |
| --- | --- |
| Source-copy core file/directory inventory | 21 paths exist; no missing paths |
| Existing prepared-package core/wrapper inventory | 26 paths exist; no missing paths |
| Bundled EXE PE machine header | x64; ARM/32-bit operation not certified |
| Current release-folder filename/category scan | PASS |
| Current release-ZIP filename/category scan | PASS |
| Packaged initialization in a fresh isolated temporary LocalAppData | Exit 0; local configuration generated, zero reported failures |
| Repeat isolated initialization | Exit 0; generated configuration hash unchanged |
| Initialization checks executed | Only repo, appdata and local_env checks; developer setup branches skipped |
| PowerShell syntax parsing | 10 relevant scripts parsed; zero syntax errors |
| PDF page count / text | One page; current app version/build and localhost URL present |
| PDF rendering | Rendered with Poppler; visually checked for readable text, no clipping/overlap and quiet layout |

Evidence is under ignored `.omo/evidence/client-handoff-2026-09-08/`; the synthetic generated configuration stays in its temporary local profile and is not distribution material. The temporary environment override was restored after the probe. No existing processes were stopped and no destructive cleanup was required.

Independent final review: APPROVE / PASS, no criterion-linked blockers. The reviewer verified the file lists, wrapper dependencies, package scans, metadata scope and one-page PDF render. The whole illustrated-guide directory is retained, including its 11 PNGs; the HTML references 10 of them.

## Limits that remain visible to the sender

- Stop's Yes-to-restart action uses source startup; guide says N, then packaged shortcut.
- Bootstrap password is generated locally, so R3 must arrange first login. The current recovery script requires a source virtual environment.
- Source preflight checks Python minimum and module availability, not all version compatibility; it does not enforce Node's engine range.
- Installer mirrors its own app directory; unmanaged files there may be removed on upgrade. Complete Uninstall deletes runtime data. Backups use Windows CurrentUser protection.
- No freshly rebuilt/trimmed package, target-client laptop, SmartScreen/antivirus behavior, admin recovery without Python, full lifecycle or cross-user backup migration was certified here.
- This is a dependency/setup review, not a new backend/frontend regression run or a dependency vulnerability scan. LOC-change and live Alleva approval gates remain unchanged.
