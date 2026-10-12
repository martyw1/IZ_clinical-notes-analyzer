# Current local desktop architecture

Source **1.0.1 / build 2026.10.12.1 / stable-local-desktop**, October 12, 2026. The browser product is **R3 Treatment Plan Audit Application**; legacy IZ storage/shortcut/package identifiers remain stable. V2 names internal modules, not the app release version.

## Runtime and data flow

The Windows launcher starts one FastAPI desktop service bound to localhost, ordinarily port 8000. `backend/app/desktop_main.py` mounts built React/Vite assets and desktop-only readiness/API pages. `backend/app/main.py` constructs the shared application. Normal prepared-package users need no build tools, administrator privileges, Docker, PostgreSQL, Git, Python or Node installation.

The React entry renders `frontend/src/v2/AppV2.tsx`. Role-scoped pages include Dashboard, Patient Roster/detail, Treatment Plans Roster/detail, Manual Upload and Help; administrators also have Users, Settings, API Testing Harness and Forensic Logs. Account provides password and recovery workflows. Current clinical/identity behavior is described in [operator help](operator-help-current.md), [UI contract](v2-beta/ui-workflows.md) and [patient handling](patient-treatment-plan-handling.md).

Active API routes are composed under `backend/app/v2/api/`. Auth validates active accounts, role/facility scope, session expiration and password epoch. Initial temporary-password change and recovery-code setup protect entry to the workspace. Password recovery is one-time and does not reactivate a disabled user. Do not assume browser sign-out substitutes for Windows locking.

Default runtime paths resolve through `Settings.local_app_data_dir` to `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`, outside repository/OneDrive. SQLite stores accounts, local patient/plan/version/evaluation metadata and forensic records. Generated-name source uploads and saved API configuration use encrypted storage. Immutable saved versions keep exact source/facility/identity associations; ambiguous or missing relationships are not guessed. Clinical identifiers and dates in SQLite still need OS/disk protection.

## Deterministic evaluation

The canonical 42-step checklist and versioned rules feed `backend/app/v2/services/deterministic_evaluator.py`. Initial signatures are checked on admission Day 1, master signatures within 30 calendar days, recurring PHP reviews at 30 calendar days and IOP/OP at 60. The recurring anchor is latest valid signed review or admission; source Next Review Due is compared with calculated dates. Settings shows clinical intervals read-only. The seven-calendar-day LOC date remains an unvalidated candidate and Needs Review. Optional LLM configuration is disabled by default and unnecessary for timing/completeness decisions.

## Import and readiness boundary

Manual upload parses supported text/document formats within file/aggregate/extraction bounds and archives source material encrypted. Some legacy/image/archive formats remain opaque; storage success is not extraction or clinical acceptance. Authorized Alleva operations use approved tenant/read-only credentials and canonical mapping with pagination/rate ceilings, checkpoints and bounded detail workers. Patient roster and treatment-plan pulls are distinct jobs. Startup import stays disabled. API configuration, OAuth/connectivity tests and bounded OpenAPI/operation previews do not establish live import approval.

## Logging, backup and packaging

V2 audits use safe structured metadata in SQLite with a SHA-256 linked chain; the common audit wrapper supports local JSONL fallback on persistence failure. Startup logs, redacted diagnostics and job artifacts serve separate support purposes. Preserve detailed events without note text, raw vendor payloads, names, original filenames or secret values. Chain verification is consistency evidence, not independent immutable storage against a host administrator. Retention/legal hold remains an R3 policy requirement.

Backup tooling produces semantically verified encrypted `.izcnabackup` archives containing related data and configuration. AES/HMAC and CurrentUser DPAPI bind key recovery to the same Windows account/computer. Replacement-device recovery requires separate testing. Prepared Windows packaging bundles runtime/assets and applies required-file and forbidden-file gates; exact receipts/hashes belong to the actual ZIP, never a renamed historical release.

See [runbook](runbook.md), [assessment](security/appliance-assessment-2026-10-12.md), [open blockers](open-blockers.md) and [current validation](validation/current-work-2026-10-12.md). The supported appliance workload is app/browser plus OneDrive and Windows services; ChatGPT is excluded. Whole-device encryption, secure Windows account/locking, approved OneDrive business controls, incident disposition and tested disaster recovery remain deployment controls outside source-code correctness.
