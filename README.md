# R3 Treatment Plan Audit Application

Current source: **1.0.1 / build 2026.10.12.1 / installer revision 1 / stable-local-desktop**. Existing IZ Clinical Notes Analyzer package, shortcut and AppData names remain intentional for compatibility. Internal V2 architecture and schema/checklist versions are separate from the app version.

The app is a local-first Windows clinical-evidence and treatment-plan review tool for R3. One localhost FastAPI service serves a built React interface, uses local SQLite, encrypts source uploads and saved API settings, restricts access by role/facility and retains exact saved-plan/evaluation context. Clinical timing and the 42-step checklist are deterministic. Optional LLM configuration stays disabled by default and is unnecessary for decisions.

The intended client workload is the app with its localhost browser and OneDrive plus normal Windows services. ChatGPT will not run and is not required. Passing software checks does not close R3 policy, security, vendor or recovery obligations.

## Start here

- Office manager: [current illustrated offline HTML guide](docs/guides/current/Marleigh-Setup-Install-and-User-Guide.html), [written operator help](docs/operator-help-current.md).
- Support: [operations runbook](docs/runbook.md), [account recovery](docs/admin-access-reset.md), [password management](docs/password-management-beta4.md).
- Shipping box: [one-page Getting Started Guide](docs/guides/current/Getting-Started-Guide.pdf). Desktop links: `scripts/create-source-desktop-shortcuts.ps1`.
- Handoff: [client checklist](docs/client-handoff-checklist.md), [Windows build/install](docs/windows-installer-build-and-install.md), [maintenance contract](docs/windows-cmd-maintenance.md).
- Current evidence: [October 12 verification](docs/validation/current-work-2026-10-12.md), [package index](docs/client-release-packages.md), [release notes](docs/release-notes.md).
- Boundaries: [open blockers](docs/open-blockers.md), [laptop/HIPAA/security/performance assessment](docs/security/appliance-assessment-2026-10-12.md).
- Technical map: [architecture](docs/architecture.md), [patient treatment-plan handling](docs/patient-treatment-plan-handling.md), [current V2 contracts](docs/v2-beta/README.md).
- [Documentation index](docs/current-documentation-state.md) and [complete inventory](docs/documentation-inventory.md) distinguish current instructions from dated beta/Version 1/PRD evidence.

## Prepared Windows client package

Use the exact approved ZIP and its receipt/hash from the package index. October 12 source updates do not change the immutable September 21 ZIP. Extract All, run `Install-IZ-Clinical-Notes-Analyzer.cmd`, wait for success, then use the installed shortcut or package-root `Launch-IZ-Clinical-Notes-Analyzer.cmd`. Launch delegates to the installed current-user runtime; without an install it tells the user to run Install first. Normal upgrade/reinstall preserves initialized passwords and local data. Complete uninstall is a separate destructive purge, never an upgrade step.

A prepared runtime includes built assets and does not require Windows administrator rights, Python, Git, Node.js, Docker, PostgreSQL or command-line work. The source checkout is an engineering path, not the default client handoff. First use includes temporary-password replacement when needed and mandatory recovery-code setup/save acknowledgment. Use assigned individual accounts. Office-manager screens/actions differ from administrator Settings, API harness, Users and Forensic Logs.

Normal application root is `%LOCALAPPDATA%\Programs\IZ Clinical Notes Analyzer`; data stays under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`, outside the repository/OneDrive source tree. Check the running footer and `/api/version` against the delivered package. Browser product name is R3 Treatment Plan Audit Application; legacy Windows identifiers do not imply an old build.

## Daily workflow and clinical boundary

Start at Dashboard/Patient Roster. Open Patient Record Detail, then select the exact saved plan or use Treatment Plans Roster. Both Manual and Alleva saved plans are browsable. Confirm source/facility, MRN, patient-record ID, plan ID and saved-version ID. Names can be displayed from encrypted authorized patient snapshots, but are never identity join keys. A successor import does not silently replace an already selected version. Inspect the source, signatures, warnings and criterion evidence before recording a manager decision.

Initial signatures are checked on admission Day 1, master signatures within 30 calendar days after admission, recurring PHP reviews every 30 calendar days and IOP/OP every 60. The recurring anchor is latest valid signed review, or admission without one. Settings clinical intervals are read-only. The LOC-change seven-calendar-day date is an unvalidated candidate; cases remain Needs Review pending R3/Marleigh policy and a tested versioned-rule update. Missing Data, Conflicting Evidence and Unable to Evaluate cannot silently become compliance. [Rules contract](docs/v2-beta/rules-contract.md).

Manual uploads are point-in-time evidence. Bounded parsing and encrypted archival are different outcomes: opaque files may be safely stored without clinical extraction. Live Alleva import remains off by default and requires approved tenant credentials, read-only authorization, endpoint/mapping and pagination/rate-limit validation and compliance approval. Startup import remains disabled. A connection test or diagnostic preview is not a complete import. [API configuration](docs/api-configuration-and-connectivity.md).

## Logging, backups and support

Structured V2 audit events retain actor/action/target/outcome/time and privacy-safe detail in SQLite with a linked SHA-256 chain. The common audit wrapper supports JSONL fallback on persistence failure. Forensic, startup and job evidence serve distinct purposes. Do not add names, note text, raw vendor payloads, original filenames, passwords, recovery codes or access/encryption material to logs. Hash-chain verification proves covered-record consistency, not immutable independent storage against a host administrator. [Audit/security contract](docs/v2-beta/security-privacy-audit.md).

Stop the app before supported backup/restore. Backup produces a verified encrypted `.izcnabackup` containing related data/configuration; CurrentUser DPAPI binds key recovery to the same Windows account/computer. Use the supplied Restore command, never unzip or copy only a database/configuration file. R3 must separately test device-loss restoration, backup schedule, RPO/RTO and approved protected storage. OneDrive synchronization is not itself a tested recovery plan or HIPAA control; business agreement, tenant sharing/access and retention require owner approval. SQLite clinical identifiers/dates still need disk/Windows protection despite encrypted source envelopes.

Desktop handoff convention: **(1) Start IZ Clinical Notes Analyzer**, **(2) Stop IZ Clinical Notes Analyzer**, **(3) Collect IZ Diagnostics**, **(4) Quick Assist - R3 Support**, **(5) Short Intro Video**, **(6) IZ Clinical Notes Analyzer User Guide**. Shortcuts are machine-specific and verified during handoff. Closing a browser/signing out does not stop the service; lock Windows when unattended. The October 3 MP4 is dated administrator training with synthetic records; current written guide governs version-specific instructions.

## Source development and validation

Use the task-oriented [scripts guide](scripts/README.md). Windows source launcher: `scripts/Start-IZ-Clinical-Notes-Analyzer.cmd`. macOS source launcher: `scripts/Start-IZ-Clinical-Notes-Analyzer.command`. Only engineering/source maintenance requires development dependencies.

Backend, using the prepared local environment in PowerShell:

```powershell
$env:PYTHONPATH = "$PWD\backend"
.\backend\.venv\Scripts\python.exe -m pytest .\backend\tests -q
```

Frontend, from `frontend`:

```text
npm run test -- --run
npx tsc --noEmit
npm run build
```

Windows release build: double-click `scripts/Build-IZ-Windows-Installer.cmd`. The builder must run backend/frontend tests and frontend build, validate assets, prepare runtime/package, and apply required-file/forbidden-file gates to folder and ZIP. Expected source identity is 1.0.1 / build 2026.10.12.1; actual output paths, hash and results belong to its receipt. Never rename an old archive or transfer historical passing counts to new source. Use only isolated synthetic profiles for tests and screenshots; never a client's live database, credentials, uploads or API reports.

## Key source locations

| Responsibility | Active location |
| --- | --- |
| Desktop service/app construction | `backend/app/desktop_main.py`, `backend/app/main.py` |
| Active API composition | `backend/app/v2/api/routes.py` |
| Authorization and identity resolution | `backend/app/v2/authorization.py`, `backend/app/v2/api/deps.py` |
| V2 models, schemas and structural migrations | `backend/app/v2/models.py`, `backend/app/v2/domain/schemas.py`, `backend/app/v2/migrations/` |
| Plan storage/read model/evaluation | `backend/app/v2/services/treatment_plan_store.py`, `treatment_plan_read_model.py`, `deterministic_evaluator.py`, `evaluation_store.py` |
| Encrypted source/patient snapshots | `backend/app/v2/services/clinical_snapshot_codec.py`, `manual_source_batch.py`, `patient_snapshot_store.py` |
| Alleva source jobs | `backend/app/v2/services/alleva_sync.py`, `alleva_roster.py`, `jobs.py` |
| Structured audit | `backend/app/v2/services/audit_store.py`, `backend/app/services/audit.py` |
| UI/session and pages | `frontend/src/v2/AppV2.tsx`, `frontend/src/v2/pages/` |
| Canonical checklist and rules | `config/checklists/treatment-plan-v1.json`, `config/rules/` |
| Release metadata | `VERSION`, `VERSION.json`, `frontend/package.json`, `frontend/package-lock.json` |

Do not commit/package PHI, runtime `.env`, databases, uploads, exports, raw reports/logs, credentials, virtual environments, dependency directories or caches. Preserve existing user changes and immutable historical evidence. Before release, reconcile source/API/footer identity, test/build results, detailed logging/privacy boundaries, exact ZIP receipts and unresolved owner gates. [Current validation](docs/validation/current-work-2026-10-12.md) records what was actually observed.
