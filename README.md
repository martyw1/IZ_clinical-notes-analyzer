# IZ Clinical Notes Analyzer

Current app version: `2.0.0-beta.2` / build `2026.07.11.1` on the `beta-local-desktop-v2` channel.

Version 2.0 Beta is the active local desktop runtime. The pre-2.0 implementation is preserved under `deprecated/v1/` for historical reference, migration traceability, and regression comparison.

IZ Clinical Notes Analyzer is a local-first clinical chart-review and Treatment Plan Timeliness Tracker app for Windows 10/11 desktop use. It helps R3 staff check clinical-note binders and treatment-plan tracking evidence before office-manager approval. The current app runs as one local FastAPI desktop service with a React/Vite browser interface at `http://localhost:8000`, SQLite under the user's local app-data folder, encrypted local uploaded-file storage, encrypted API configuration storage, role-based access control, deterministic treatment-plan rules, workflow profiles, readiness checks, optional LLM configuration disabled by default, and forensic audit logging.

The normal R3 Windows user path does not require Windows administrator access, Docker, PostgreSQL, cloud hosting, Git, Node.js, command-line work, or a database administrator when a prepared release folder with built frontend assets is used.

## Current Version 2.0 Beta State

Version 2.0 Beta is the current local Windows desktop beta. It includes:

- A focused V2 FastAPI runtime in `backend/app/` with active V2 routes in `backend/app/v2/api/routes.py`.
- A focused V2 React/Vite UI in `frontend/src/v2/` for Status Dashboard, Treatment Plans, Manual Upload, API Testing Harness, Users, Forensic Logs, Settings, and Help.
- Treatment Plan Checklist Version 1 as the canonical source in `config\checklists\treatment-plan-v1.json`; its checklist content version remains separate from the app version.
- A selected-client Treatment Plans Workbench with patient-ID-only labels, deterministic status order, nested clinical-content viewer, 42-step checklist evidence, manager action controls, Evidence Coverage Map, and bounded Raw Field Explorer.
- A V2 API Testing Harness with `ClientId`, Pull ALL Treatment Plans job lifecycle, compact progress, cancel, redacted JSONL/TSV/schema artifacts, and bounded preview.
- Local-first audit/version/readiness services, safe forensic log summaries, encrypted/local app-data boundaries, and frontend footer version metadata.
- Windows preflight, local-stack smoke, API-configuration smoke, release-folder packaging, required-file validation, and forbidden-file scans for a prepared release folder.
- V2 documentation under `docs\v2-beta\`, including validation evidence and task coverage audit.
Version 2.0 Beta still does not include ungated live Alleva patient import or a signed MSI/MSIX. Live Alleva sync remains disabled until R3/Alleva approval and endpoint mapping validation are complete. The level-of-care-change treatment-plan update window remains unvalidated by R3/Marleigh and must stay configurable and visibly marked as unresolved.

`2.0.0-beta.2` is a prerelease release-readiness update, not a production declaration. Before a production release, R3 must complete supervised approved live Alleva validation; rotate the exposed credential and approve downstream/history remediation; and record signing and retention/legal-hold decisions. The final validation procedure uses a clean isolated local-app-data directory and synthetic data only; see `docs/v2-beta/release-readiness-2026-07-11.md`.

## Interactive Architecture Diagram

GitHub renders this Mermaid diagram directly in the README. In GitHub views that support Mermaid click targets, select a node to open the relevant file or folder. If click targets are unavailable in a viewer, use the `Key Files` section below.

```mermaid
flowchart TB
    Staff["R3 staff<br/>Admin / Office manager / Counselor"]

    subgraph Windows["Windows 10/11 local desktop runtime"]
        Launcher["Double-click launcher<br/>scripts/Start-IZ-Clinical-Notes-Analyzer.cmd"]
        Preflight["Preflight and setup<br/>scripts/preflight-windows.ps1"]
        Desktop["FastAPI desktop runtime<br/>backend/app/desktop_main.py<br/>localhost:8000"]
        StaticUI["Built React assets<br/>frontend/dist"]
    end

    subgraph Browser["Browser UI served from localhost:8000"]
        ReactApp["React app<br/>frontend/src/App.tsx"]
        Views["Main screens<br/>Dashboard, Treatment Plans, Manual Upload,<br/>API Testing Harness, Users, Logs,<br/>Settings, Help"]
        DetailUI["Treatment detail and evidence UI<br/>frontend/src/v2/components/TreatmentPlanDetailViewer.tsx"]
        JobUI["Large job progress UI<br/>frontend/src/v2/components/JobProgressCard.tsx"]
        Styles["Responsive styles and status colors<br/>frontend/src/app.css"]
    end

    subgraph Backend["FastAPI backend services"]
        MainAPI["Main API and app factory<br/>backend/app/main.py"]
        Routes["Active V2 routes<br/>backend/app/v2/api/routes.py"]
        Domain["Treatment-plan contracts<br/>backend/app/v2/domain/schemas.py"]
        SampleData["Test-only synthetic fixture<br/>backend/app/v2/services/sample_data.py"]
        Jobs["Large API jobs and artifacts<br/>backend/app/v2/services/jobs.py<br/>backend/app/v2/services/job_artifacts.py"]
        DashboardData["Dashboard data<br/>backend/app/v2/services/dashboard_data.py"]
        Audit["Forensic audit logging<br/>backend/app/services/audit.py"]
        Version["Version and readiness<br/>backend/app/services/version.py<br/>backend/app/v2/api/routes.py"]
    end

    subgraph Config["Repo configuration and product rules"]
        Checklist["Canonical 42-step checklist<br/>config/checklists/treatment-plan-v1.json"]
        RuleYaml["Treatment Plan Tracking rules<br/>config/rules/alleva_treatment_plan_completeness_rules.yaml"]
        VersionFiles["Version metadata<br/>VERSION and VERSION.json"]
    end

    subgraph LocalData["Local app data outside the repo<br/>%LOCALAPPDATA%/IZ Clinical Notes Analyzer"]
        Env[".env<br/>local settings and generated access values"]
        SQLite["SQLite database<br/>clinical-notes-analyzer.sqlite3"]
        EncryptedUploads["Encrypted uploads<br/>clinical source files"]
        Logs["Startup logs and fallback audit logs"]
        Reports["Redacted API reports"]
    end

    subgraph External["External systems and optional integrations"]
        Alleva["Alleva REST / OpenAPI / HL7<br/>readiness and operation tests only"]
        LLM["Optional OpenAI-compatible LLM<br/>disabled by default"]
    end

    subgraph Packaging["Packaging and legacy boundary"]
        Builder["Release-folder builder<br/>scripts/build-windows-installer.ps1"]
        Release["Prepared release folder<br/>dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.2"]
        Legacy["Archived V1 runtime<br/>deprecated/v1"]
    end

    Staff --> Launcher --> Preflight --> Desktop
    Desktop --> StaticUI --> ReactApp
    Staff --> ReactApp
    ReactApp --> Views
    ReactApp --> DetailUI
    ReactApp --> JobUI
    ReactApp --> Styles
    ReactApp --> MainAPI
    Desktop --> MainAPI
    MainAPI --> Routes
    Routes --> Domain
    Routes --> Jobs
    Routes --> DashboardData
    Routes --> Audit
    Routes --> Version
    Domain --> RuleYaml
    Routes --> Checklist
    Version --> VersionFiles
    MainAPI --> SQLite
    MainAPI --> Env
    Audit --> Logs
    Jobs --> Reports
    Jobs -. readiness only, no live patient import .-> Alleva
    MainAPI -. optional and disabled by default .-> LLM
    Builder --> Release
    Legacy -. not ordinary Windows runtime .-> Windows

    click Launcher "scripts/Start-IZ-Clinical-Notes-Analyzer.cmd" "Open Windows launcher"
    click Preflight "scripts/preflight-windows.ps1" "Open Windows preflight"
    click Desktop "backend/app/desktop_main.py" "Open desktop runtime"
    click ReactApp "frontend/src/App.tsx" "Open React app"
    click DetailUI "frontend/src/v2/components/TreatmentPlanDetailViewer.tsx" "Open treatment detail UI"
    click JobUI "frontend/src/v2/components/JobProgressCard.tsx" "Open large job UI"
    click Styles "frontend/src/app.css" "Open app styles"
    click MainAPI "backend/app/main.py" "Open main FastAPI app"
    click Routes "backend/app/v2/api/routes.py" "Open active V2 routes"
    click Domain "backend/app/v2/domain/schemas.py" "Open V2 contracts"
    click SampleData "backend/app/v2/services/sample_data.py" "Open test-only synthetic fixture"
    click Jobs "backend/app/v2/services/jobs.py" "Open large job service"
    click DashboardData "backend/app/v2/services/dashboard_data.py" "Open dashboard data"
    click Audit "backend/app/services/audit.py" "Open audit service"
    click Checklist "config/checklists/treatment-plan-v1.json" "Open canonical checklist"
    click RuleYaml "config/rules/alleva_treatment_plan_completeness_rules.yaml" "Open deterministic rules"
    click VersionFiles "VERSION.json" "Open version metadata"
    click Builder "scripts/build-windows-installer.ps1" "Open release builder"
    click Legacy "deprecated/v1/README.md" "Open V1 archive notes"
```

Diagram boundaries:

- The normal runtime is one local FastAPI desktop service at `http://localhost:8000` serving the React UI and API.
- Runtime data lives under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`, not inside the source checkout.
- Synthetic fixtures are not imported by active V2 routes or production pages; the default queue remains empty until persisted evidence is imported.
- Alleva REST/OpenAPI/HL7 paths are readiness and operation-test paths only; live patient import remains disabled.
- Optional LLM configuration exists but is disabled by default and is not the primary review path.
- Docker/PostgreSQL artifacts are not ordinary Windows desktop requirements.

## Primary Docs

- `docs\release-notes.md`
- `docs\beta-client-test-run-guide.md`
- `docs\Windows-User-Guide-Version-1.md`
- `docs\Windows-Deployment-and-Test-Guide-Version-1.md`
- `docs\UAT-Version-1-Marleigh.md`
- `docs\patient-treatment-plan-handling.md`
- `docs\treatment-plan-checklist-v1.md`
- `docs\open-blockers.md`
- `docs\validation\validation-report-2026-06-16-production-readiness.md`
- `docs\api-configuration-and-connectivity.md`
- `docs\architecture.md`
- `docs\runbook.md`
- `docs\codebase-map.md`
- `docs\admin-access-reset.md`

Historical validation reports keep the original version they validated. Use `docs\release-notes.md`, `VERSION`, and `VERSION.json` for the current release number.

## Quick Start for a Prepared Windows Release Folder

A release folder is created by double-clicking `Build-IZ-Windows-Installer.cmd` from the repo root. The detailed build/install guide is `docs\windows-installer-build-and-install.md`. For Version 2.0 Beta it writes:

- `dist\windows-release\IZ-Clinical-Notes-Analyzer-v2.0.0-beta.1`
- `dist\windows-release\IZ-Clinical-Notes-Analyzer-v2.0.0-beta.1.zip`

To install from a prepared release folder:

1. Open `dist\windows-release\IZ-Clinical-Notes-Analyzer-v2.0.0-beta.1`.
2. Double-click `Install-IZ-Clinical-Notes-Analyzer.cmd`.
3. Wait for preflight to finish.
4. Launch from the Start Menu shortcut named `IZ Clinical Notes Analyzer`.

The per-user install path is `%LOCALAPPDATA%\Programs\IZ Clinical Notes Analyzer`. Local runtime data is preserved under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer` when the normal uninstall removes app files.

The prepared release folder also includes double-click commands for diagnostics, backup, data-preserving uninstall, and complete uninstall:

- `Stop-IZ-Clinical-Notes-Analyzer.cmd`
- `Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd`
- `Backup-IZ-Clinical-Notes-Analyzer.cmd`
- `Uninstall-IZ-Clinical-Notes-Analyzer.cmd`
- `Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd`

Complete uninstall requires typing `REMOVE IZ DATA` and removes the local runtime data folder for the current Windows user. Create a backup first unless R3 intentionally wants the laptop cleared.

## Quick Start for a Source Checkout

Use this path for development, validation, or support work. It is not the preferred non-technical production path.

Requirements:

- Windows 10 or Windows 11.
- Python 3.11 or newer.
- Internet access the first time Python packages are installed.
- Node.js LTS only when the browser UI must be rebuilt because `frontend\dist` is missing or stale.

Use a normal local folder such as:

```text
C:\Users\<your-user>\local-apps\IZ_clinical-notes-analyzer
```

Avoid running the source checkout directly from OneDrive, Dropbox, iCloud Drive, Google Drive, or a network share.

Double-click:

```text
scripts\Start-IZ-Clinical-Notes-Analyzer.cmd
```

The launcher calls `scripts\startup-windows-local.ps1`, which runs preflight, creates local AppData folders and `.env` when missing, checks Python and backend packages, validates rules/checklists, detects missing or stale frontend assets, prompts before installing or rebuilding when needed, starts the local FastAPI desktop app, and opens the browser unless `-NoBrowser` is used.

If Windows says the app is already running, the local port is in use, or a previous console did not close cleanly, double-click:

```text
scripts\Stop-IZ-Clinical-Notes-Analyzer.cmd
```

The cleanup launcher stops only app-specific local launcher/server processes, shows what it is doing in the console, and asks `Do you want to restart the app?`. It does not close browser windows or clear patient data.

The app should open automatically. If it does not, browse to:

```text
http://localhost:8000
```

## Useful Local Pages

| Page | Address |
| --- | --- |
| App home | `http://localhost:8000` |
| Manual upload | `http://localhost:8000/?view=uploads` |
| API configuration | `http://localhost:8000/api-configuration` |
| API health | `http://localhost:8000/api/health` |
| Readiness | `http://localhost:8000/api/readiness` |
| Version | `http://localhost:8000/api/version` |
| API docs | `http://localhost:8000/docs` |

## Supported Upload Files

Supported extensions: `.csv`, `.doc`, `.docx`, `.jpeg`, `.jpg`, `.pdf`, `.png`, `.rtf`, `.txt`, and `.zip`.

Upload limits:

| Limit | Value |
| --- | --- |
| Maximum one file | `50MB` |
| Maximum total binder upload | `250MB` |
| Maximum files in one binder upload | `40` |

## Local Data Locations

The Windows desktop runtime stores data outside the repo:

```text
%LOCALAPPDATA%\IZ Clinical Notes Analyzer
```

Important local files and folders:

| Path | Purpose |
| --- | --- |
| `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\.env` | Local configuration and generated local access material |
| `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\clinical-notes-analyzer.sqlite3` | Local SQLite application database |
| `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\uploads` | Encrypted uploaded clinical files |
| `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\logs` | Startup logs and fallback audit logs |
| `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\api-reports` | Redacted app API harness reports |
| `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\api-connectivity-reports` | Reports from `scripts\test-alleva-api-connectivity.ps1` |
| `%USERPROFILE%\Documents\IZ Clinical Notes Analyzer Backups` | Backup zips created by the backup helper |

The local configuration, database, and uploads must be backed up together. If the local configuration is lost, encrypted uploads and saved API configuration may not be recoverable.

Use `Backup-IZ-Clinical-Notes-Analyzer.cmd` or the Start Menu backup shortcut to create a full local-data backup zip. The backup is not redacted because it is intended for restore; store it encrypted and access-controlled.

## API Configuration and Alleva Readiness

Admins can open `http://localhost:8000/api-configuration` from App settings or directly. When opened from the app, the page reuses the current admin session and does not require a second in-page admin login. App settings is the source of truth for the one active Alleva/API connection; the harness loads and tests those same active values.

The app API harness can:

- save vendor/base URL settings
- use a one-time API key for a test when a vendor uses API-key auth
- save API keys and client secrets in encrypted form
- use OAuth2 client credentials to request a bearer token for a test
- save the OpenAPI URL used by readiness checks and operation tests
- choose body, Basic, URL-encoded Basic, try-both, or try-all token auth styles
- pull OpenAPI/Swagger definitions from a Swagger UI page or direct JSON URL
- test selected OpenAPI operations with generated path/query/header/body fields
- show bounded, redacted, non-secret results

Alleva confirmed that it does not currently support FHIR; the active app does not ask for or require a FHIR endpoint.

For Alleva OAuth, pasting the client ID and client secret supplied by R3/Alleva is expected. The client secret is write-only after save: the browser only receives configured/not-configured flags, and stored secrets are encrypted in the local SQLite database.

Stored API endpoint profiles are optional presets for alternate Alleva or future vendor connection values. Activating a profile copies its REST API base URL, OpenAPI URL, token URL, token auth style, client ID, and encrypted client secret into the active App settings connection. Only the active connection is used by readiness checks, the API harness, periodic checks, and approved REST treatment-plan sync.

Periodic API readiness checks are readiness checks only. They authenticate and test configuration; they do not import live patient charts or treatment plans.

### Standalone Alleva Scripts

Two standalone scripts exist and have different safety profiles:

| Script | Purpose | Secret behavior |
| --- | --- | --- |
| `scripts\test-alleva-api-connectivity.ps1` | Simple Swagger/OpenAPI/API reachability probe and JSON report writer. | Designed for redacted reports; still review output before sharing. |
| `Test-AllevaApi.ps1` | Full diagnostic tester with interactive endpoint selection, local settings, and detailed request/response capture. | Sensitive by default: it prints/saves tokens, secrets, Authorization headers, request bodies, and response bodies unless `-RedactSensitive` is used. |

Keep `.alleva.local.ps1`, generated logs, tokens, secrets, and any real API output out of Git, tickets, screenshots, chat, and email unless an approved secure workflow says otherwise. Do not use real PHI in API tests.

Current 2026-06-17 validation evidence: the public Swagger UI at `https://api.allevasoft.com/swagger/index.html` and OpenAPI definitions at `/swagger/v1/swagger.json` and `/swagger/v2/swagger.json` are reachable. The OpenAPI definitions describe Alleva REST API operations. `https://api.allevasoft.com/advanced-form-elements` is a protected REST operation path and returned `401 Unauthorized` without credentials.

Beta `1.4.6-beta.1` removes active FHIR/SMART-on-FHIR configuration, discovery, import-plan, scopes, UI fields, defaults, and validation requirements from Alleva workflows. The REST sync path uses the active Alleva API base URL (`https://api.allevasoft.com` by default), OpenAPI URL, token URL, client ID, encrypted client secret, token auth style, and validated endpoint mapping to pull active-client, treatment-plan, and treatment-review data into this app. Alleva does not perform the compliance decision; R3's deterministic local Treatment Plan Timeliness rules run after the REST payloads are normalized. Startup sync is disabled by default and requires explicit R3/Alleva live-sync approval plus validated active-client, treatment-plan, treatment-review, pagination, status, and signature/date field mapping before it can run. Patient-name import/display and name-fallback matching are separate App settings controls and both remain off unless explicitly saved.

## Treatment Plan Tracking Rules

The `Treatment plans` tab provides the Treatment Plan Timeliness Tracker work queue. Beta `1.4.6-beta.1` keeps the visible updated-evidence-queue banner, defaults admins and office managers to this work queue when no explicit view is requested, and uses distinct text-labeled statuses for overdue, urgent, due soon, returned, needs review, missing data, conflicting evidence, unable-to-evaluate, approved, and compliant records. The tab includes a normal queue `Refresh` action and an admin-only `Pull / refresh treatment plans` button that runs the gated Alleva REST treatment-plan sync from the tab itself. The tab shows active clients, current level of care, counselor/primary clinician, admission date, last valid treatment-plan review/update date, local current date used by the date clock, next due date, days until due, status, rule used, source evidence summary, evidence completeness, detail records, manual overrides, recent audit history, selected-client 42-step checklist evaluation, manager status/comment notes per criterion, and counselor action export.

The current implementation reference is `docs\patient-treatment-plan-handling.md`. It maps the manual-upload path, gated Alleva REST sync, patient-level aggregate, local treatment-plan tables, deterministic timeliness evaluator, 42-step selected-client checklist output, content-fact privacy boundary, and exact backend/frontend code locations.

For the first client beta run, use `docs\beta-client-test-run-guide.md` as the non-technical day-of-test checklist for install, launch checks, lookup status behavior, treatment-plan review expectations, diagnostics, backup, and maintenance.

The date clock compares the laptop/facility-local current date against either the admission date or the latest valid treatment-plan review/update date. PHP treatment plans use a 30-calendar-day update interval. Other configured treatment levels use a 60-calendar-day update interval. A level-of-care change has a separate manager-editable preset of 7 calendar days, but that LOC-change setting remains visibly marked unvalidated until R3/Marleigh confirms the exact rule.

If an uploaded or API-style pulled plan has no permitted patient name, the app creates a safe fallback display name:

- no name found in source evidence: `no-name-found_YYYY-MM-DD_HHMMSS`

Alleva REST treatment-plan sync stores that redacted fallback by default even when `/clients` contains a name. Admins must turn on `Import and display Alleva patient names` in App settings before imported names are stored or shown. Turning the setting off redacts existing Alleva-sourced treatment-plan client display names again.
- empty or unusable value found: `no-value-found_YYYY-MM-DD_HHMMSS`

Deterministic rules live in:

```text
config\rules\alleva_treatment_plan_completeness_rules.yaml
```

## Workflow Profiles

Admins and office managers can manage versioned workflow profiles from the `Workflow profiles` screen. The Workflow profiles screen includes a `Seed draft from 42-step checklist` action. It loads `config\checklists\treatment-plan-v1.json`, copies the 42 steps, review statuses, override requirements, source modes, audit events, and export fields into a draft workflow snapshot, and gives admins/managers a starting point they can edit before publishing a new workflow version.

Published or archived workflow history must be archived instead of hard-deleted so historical metrics can be interpreted correctly.

## Validation Commands

Backend tests:

```powershell
$env:PYTHONPATH = "$PWD\backend"
.\backend\.venv\Scripts\python.exe -m pytest .\backend\tests -q
```

Frontend tests and build:

```powershell
cd frontend
npm test -- --run
npm run build
cd ..
```

Windows preflight and local smoke:

```powershell
.\scripts\preflight-windows.ps1 -AssumeYes
.\scripts\test-local-app-stack.ps1
.\scripts\test-api-configuration-local.ps1
```

## Legacy Docker/PostgreSQL Status

Docker/PostgreSQL is not the active ordinary Windows desktop path, and the current branch does not have an active root `docker-compose.yml` full-stack deployment file. Do not present Docker, PostgreSQL, nginx, Git, Node.js, or command-line work as ordinary R3 desktop-user requirements. Do not restore the old Docker stack to active paths unless R3 explicitly reintroduces Docker/server deployment and updates the README, Windows docs, CI, tests, and release instructions together.

## Key Files

| File | Purpose |
| --- | --- |
| `VERSION` and `VERSION.json` | Version metadata shown by `/api/version` and the UI footer |
| `frontend\package.json` | Frontend package version metadata |
| `docs\release-notes.md` | Current release notes and version history |
| `docs\beta-client-test-run-guide.md` | Non-technical first beta client test-run guide |
| `scripts\Start-IZ-Clinical-Notes-Analyzer.cmd` | Double-click Windows launcher |
| `scripts\Stop-IZ-Clinical-Notes-Analyzer.cmd` | Double-click Windows cleanup and restart prompt |
| `scripts\Backup-IZ-Clinical-Notes-Analyzer.cmd` | Double-click local-data backup helper |
| `scripts\Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd` | Double-click complete uninstall helper for app files plus local data |
| `scripts\startup-windows-local.ps1` | Main Windows local startup script |
| `scripts\stop-windows-local.ps1` | App-specific Windows process cleanup script |
| `scripts\backup-local-data.ps1` | Backup zip creator for the local AppData folder |
| `scripts\complete-uninstall-local-data.ps1` | Confirmed complete uninstall for installed app and local data |
| `scripts\preflight-windows.ps1` | Windows runtime/readiness preflight |
| `scripts\build-windows-installer.ps1` | Release-folder and zip builder |
| `scripts\update-local-admin.ps1` | Local authorized admin reset utility |
| `backend\app\desktop_main.py` | Desktop FastAPI entrypoint |
| `backend\app\main.py` | Main FastAPI app factory and API endpoints |
| `backend\app\services\secure_storage.py` | Encrypted file and configuration helpers |
| `backend\app\services\patient_notes.py` | Patient-note upload storage and detection helpers |
| `backend\app\services\timeliness.py` | Treatment Plan Timeliness service |
| `backend\app\services\alleva_treatment_plan_sync.py` | Gated Alleva REST treatment-plan sync and current-plan content capture |
| `backend\app\services\alleva_treatment_plan_aggregate.py` | Patient treatment-plan aggregate dry-run builder |
| `backend\app\api\timeliness_routes.py` | Treatment Plan Timeliness dashboard/detail/aggregate/override routes |
| `backend\app\services\rules_engine.py` | Deterministic YAML rules engine |
| `backend\app\api\api_config_routes.py` | API configuration JSON routes |
| `backend\app\api\workflow_routes.py` | Workflow profile CRUD/versioning routes |
| `frontend\src` | React frontend source |
| `frontend\dist` | Built frontend assets after `npm run build` |
| `config\rules\alleva_treatment_plan_completeness_rules.yaml` | Treatment Plan Tracking completeness rules |
| `config\checklists\treatment-plan-v1.json` | Canonical 42-step checklist |
| `docs\patient-treatment-plan-handling.md` | Current treatment-plan handling and code-location reference |
| `docs\sample-clinical-notes` | Synthetic, non-PHI sample clinical notes |

## Version Metadata

The current app version is:

```text
1.4.6-beta.1
```

Checklist content version is separate and remains:

```text
1.2.0
```

Version metadata is stored in `VERSION` and `VERSION.json`. The backend exposes it at:

```text
GET /api/version
```

The UI footer displays the backend-provided beta label, version, environment, and short git commit when available.
