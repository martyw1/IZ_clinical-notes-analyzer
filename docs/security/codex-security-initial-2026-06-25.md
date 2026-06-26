# Security Review: IZ_clinical-notes-analyzer

## Scope

Repository-wide standard scan of runtime backend, frontend, Windows scripts, rules/checklists, migrations, and selected source/reference artifacts.

- Scan mode: repository
- Target kind: git_revision
- Target ID: target_sha256_e338d162e14f8ece5d7ebb07f27793dbeb7d09d7d0585dd8dc49ddcfdbb920bb
- Revision: 123feab324a8406c401f5dc4e93c686b28419efb
- Inventory strategy: repository
- Included paths: .
- Excluded paths: none
- Runtime or test status: Static review with targeted worker reproductions; no real PHI used.
- Artifacts reviewed: AGENTS.md threat model, 73-file deep-review worklist, worker discovery receipts and candidate ledgers
- Scan context: HIPAA-adjacent local Windows FastAPI/React app with strict Patient-ID-only privacy target.

Limitations and exclusions:
- Dependency advisory research was not exhaustive.
- No live Alleva or real patient data was used.

### Scan Summary

| Field | Value |
| --- | --- |
| Reportable findings | 17 |
| Severity mix | high: 3, medium: 9, low: 5 |
| Confidence mix | high: 5, medium: 11, low: 1 |
| Coverage | complete |
| Validation mode | Static source trace plus existing tests and bounded reproductions where proportionate. |

Canonical artifacts: `scan-manifest.json`, `findings.json`, and `coverage.json`. This report is a deterministic projection of those files.

## Threat Model

AGENTS.md is authoritative: local-first Windows clinical notes and treatment-plan tracker with encrypted local data, RBAC, audit logs, vendor API readiness gates, redacted diagnostics, Windows packaging, and strict Patient-ID-only privacy.

### Assets

- SQLite database
- encrypted uploads
- API credentials
- audit logs
- diagnostics
- installer artifacts
- patient IDs and treatment-plan evidence

### Trust Boundaries

- browser to localhost API
- manual uploads to extraction/storage
- external API payloads to reports/UI
- Windows launcher/installer to AppData
- counselor/manager/admin RBAC

### Attacker Capabilities

- authenticated counselor
- admin using hostile API/OpenAPI
- local user or support recipient with logs/artifacts

### Security Objectives

- Patient ID is the only patient identifier
- no patient names or addresses in storage/display/logs/exports
- credentials and diagnostics are redacted
- RBAC is enforced on patient-linked workflows

## Findings

| Finding | Severity | Confidence |
| --- | --- | --- |
| [Counselors can enumerate and read arbitrary timeliness clients](#finding-1) | high | high |
| [Default bootstrap admin credential and reset behavior remain unsafe](#finding-2) | high | medium |
| [OpenAPI metadata can execute script in the admin API harness](#finding-3) | high | medium |
| [Patient names, labels, and raw filenames persist into storage UI exports and downloads](#finding-4) | medium | high |
| [Windows launcher batch files allow install-path command injection](#finding-5) | medium | medium |
| [API readiness harness can return live PHI and raw operation responses](#finding-6) | medium | high |
| [OAuth client credentials can be sent to cleartext HTTP token URLs](#finding-7) | medium | medium |
| [Rules evaluation response echoes PHI-capable source chart fields](#finding-8) | medium | medium |
| [Raw request query strings are persisted in forensic audit logs](#finding-9) | medium | high |
| [CSV and clipboard exports allow spreadsheet formula injection](#finding-10) | medium | medium |
| [Tracked Loom metadata may expose preview URLs for identifiable chart recording](#finding-11) | medium | low |
| [Settings and audit paths expose vendor connection material](#finding-12) | medium | medium |
| [Admin reset utility duplicates secret env files into backups](#finding-13) | low | medium |
| [Login access intelligence trusts spoofable forwarding headers](#finding-14) | low | medium |
| [Startup transcript can persist URL identifiers from access logs](#finding-15) | low | medium |
| [Smoke script prints reset admin password](#finding-16) | low | medium |
| [Unauthenticated readiness diagnostics expose local paths](#finding-17) | low | high |

### Confidence Scale

| Label | Meaning |
| --- | --- |
| high | Direct evidence supports the finding with no material unresolved blocker. |
| medium | Evidence supports a plausible issue, but material runtime or reachability proof remains. |
| low | Evidence is incomplete and the item is retained only for explicit follow-up. |

<a id="finding-1"></a>

### [1] Counselors can enumerate and read arbitrary timeliness clients

| Field | Value |
| --- | --- |
| Severity | high |
| Confidence | high |
| Confidence rationale | Supported by worker source review, existing tests, or targeted reproduction recorded in scan artifacts. |
| Category | Authorization bypass / IDOR |
| CWE | CWE-639, CWE-862 |
| Affected lines | backend/app/api/timeliness_routes.py:79, backend/app/api/timeliness_routes.py:173, backend/app/services/review_source_discovery.py:125 |

#### Summary

Counselor-allowed timeliness and review-source APIs query clients without ownership scoping.

#### Root Cause

Counselor-allowed timeliness and review-source APIs query clients without ownership scoping.

#### Validation

Counselor-allowed timeliness and review-source APIs query clients without ownership scoping.

Validation method: static source trace plus targeted worker validation

#### Dataflow

See affected locations and discovery artifacts.

#### Reachability

Reachability calibrated for localhost Windows desktop app and authenticated role boundaries.

#### Severity

**High** — Counselor-allowed timeliness and review-source APIs query clients without ownership scoping.

Severity changes if reachability or data sensitivity differs from the scanned local Windows HIPAA-adjacent workflow.

#### Remediation

Filter counselor reads to owned patients/charts or restrict routes to manager/admin and add negative access tests.

Tests:
- Add regression tests for this dataflow and privacy/security invariant.

Preventive controls:
- Run Codex Security and privacy canary scans before release.

<a id="finding-2"></a>

### [2] Default bootstrap admin credential and reset behavior remain unsafe

| Field | Value |
| --- | --- |
| Severity | high |
| Confidence | medium |
| Confidence rationale | Supported by worker source review, existing tests, or targeted reproduction recorded in scan artifacts. |
| Category | Default credential |
| CWE | CWE-798, CWE-259 |
| Affected lines | backend/app/core/config.py:79, backend/app/main.py:58 |

#### Summary

Static bootstrap admin defaults can create full admin access if a source/install flow misses randomization.

#### Root Cause

Static bootstrap admin defaults can create full admin access if a source/install flow misses randomization.

#### Validation

Static bootstrap admin defaults can create full admin access if a source/install flow misses randomization.

Validation method: static source trace plus targeted worker validation

#### Dataflow

See affected locations and discovery artifacts.

#### Reachability

Reachability calibrated for localhost Windows desktop app and authenticated role boundaries.

#### Severity

**High** — Static bootstrap admin defaults can create full admin access if a source/install flow misses randomization.

Severity changes if reachability or data sensitivity differs from the scanned local Windows HIPAA-adjacent workflow.

#### Remediation

Fail readiness/startup for unsafe bootstrap defaults and disable reset-by-default for installed builds.

Tests:
- Add regression tests for this dataflow and privacy/security invariant.

Preventive controls:
- Run Codex Security and privacy canary scans before release.

<a id="finding-3"></a>

### [3] OpenAPI metadata can execute script in the admin API harness

| Field | Value |
| --- | --- |
| Severity | high |
| Confidence | medium |
| Confidence rationale | Supported by worker source review, existing tests, or targeted reproduction recorded in scan artifacts. |
| Category | Cross-site scripting |
| CWE | CWE-79 |
| Affected lines | backend/app/api/api_config_ui_routes.py:483, backend/app/api/api_config_ui_routes.py:510 |

#### Summary

OpenAPI metadata is interpolated into HTML and assigned to innerHTML in the admin API harness.

#### Root Cause

OpenAPI metadata is interpolated into HTML and assigned to innerHTML in the admin API harness.

#### Validation

OpenAPI metadata is interpolated into HTML and assigned to innerHTML in the admin API harness.

Validation method: static source trace plus targeted worker validation

#### Dataflow

See affected locations and discovery artifacts.

#### Reachability

Reachability calibrated for localhost Windows desktop app and authenticated role boundaries.

#### Severity

**High** — OpenAPI metadata is interpolated into HTML and assigned to innerHTML in the admin API harness.

Severity changes if reachability or data sensitivity differs from the scanned local Windows HIPAA-adjacent workflow.

#### Remediation

Build the form with DOM/text APIs or strict escaping and add an XSS regression test.

Tests:
- Add regression tests for this dataflow and privacy/security invariant.

Preventive controls:
- Run Codex Security and privacy canary scans before release.

<a id="finding-4"></a>

### [4] Patient names, labels, and raw filenames persist into storage UI exports and downloads

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | Supported by worker source review, existing tests, or targeted reproduction recorded in scan artifacts. |
| Category | PHI minimization failure |
| CWE | CWE-359, CWE-200 |
| Affected lines | backend/app/models/models.py:191, backend/app/models/models.py:247, backend/app/api/routes.py:1761, frontend/src/App.tsx:4205 |

#### Summary

Patient display names and raw filenames can be accepted, persisted, returned, displayed, exported, and used as download names.

#### Root Cause

Patient display names and raw filenames can be accepted, persisted, returned, displayed, exported, and used as download names.

#### Validation

Patient display names and raw filenames can be accepted, persisted, returned, displayed, exported, and used as download names.

Validation method: static source trace plus targeted worker validation

#### Dataflow

See affected locations and discovery artifacts.

#### Reachability

Reachability calibrated for localhost Windows desktop app and authenticated role boundaries.

#### Severity

**Medium** — Patient display names and raw filenames can be accepted, persisted, returned, displayed, exported, and used as download names.

Severity changes if reachability or data sensitivity differs from the scanned local Windows HIPAA-adjacent workflow.

#### Remediation

Reject patient names, replace raw filenames with opaque document labels, use patient_id in UI/exports, and add canary privacy scans.

Tests:
- Add regression tests for this dataflow and privacy/security invariant.

Preventive controls:
- Run Codex Security and privacy canary scans before release.

<a id="finding-5"></a>

### [5] Windows launcher batch files allow install-path command injection

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | medium |
| Confidence rationale | Supported by worker source review, existing tests, or targeted reproduction recorded in scan artifacts. |
| Category | Command injection |
| CWE | CWE-78, CWE-88 |
| Affected lines | scripts/Start-IZ-Clinical-Notes-Analyzer.cmd:9, scripts/build-windows-installer.ps1:93 |

#### Summary

Unquoted batch set assignments let metacharacters in install paths execute as the launching user.

#### Root Cause

Unquoted batch set assignments let metacharacters in install paths execute as the launching user.

#### Validation

Unquoted batch set assignments let metacharacters in install paths execute as the launching user.

Validation method: static source trace plus targeted worker validation

#### Dataflow

See affected locations and discovery artifacts.

#### Reachability

Reachability calibrated for localhost Windows desktop app and authenticated role boundaries.

#### Severity

**Medium** — Unquoted batch set assignments let metacharacters in install paths execute as the launching user.

Severity changes if reachability or data sensitivity differs from the scanned local Windows HIPAA-adjacent workflow.

#### Remediation

Use quoted set syntax or replace batch launchers with a safer app launcher.

Tests:
- Add regression tests for this dataflow and privacy/security invariant.

Preventive controls:
- Run Codex Security and privacy canary scans before release.

<a id="finding-6"></a>

### [6] API readiness harness can return live PHI and raw operation responses

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | Supported by worker source review, existing tests, or targeted reproduction recorded in scan artifacts. |
| Category | Sensitive data exposure |
| CWE | CWE-359, CWE-200 |
| Affected lines | backend/app/api/api_config_routes.py:433, backend/app/api/api_config_routes.py:979, backend/app/services/api_connectivity.py:790 |

#### Summary

API quick-pull and operation-test paths can return names, TSV rows, raw JSON, or body previews from external patient APIs.

#### Root Cause

API quick-pull and operation-test paths can return names, TSV rows, raw JSON, or body previews from external patient APIs.

#### Validation

API quick-pull and operation-test paths can return names, TSV rows, raw JSON, or body previews from external patient APIs.

Validation method: static source trace plus targeted worker validation

#### Dataflow

See affected locations and discovery artifacts.

#### Reachability

Reachability calibrated for localhost Windows desktop app and authenticated role boundaries.

#### Severity

**Medium** — API quick-pull and operation-test paths can return names, TSV rows, raw JSON, or body previews from external patient APIs.

Severity changes if reachability or data sensitivity differs from the scanned local Windows HIPAA-adjacent workflow.

#### Remediation

Apply direct-identifier minimization to API payloads and remove raw response/body persistence.

Tests:
- Add regression tests for this dataflow and privacy/security invariant.

Preventive controls:
- Run Codex Security and privacy canary scans before release.

<a id="finding-7"></a>

### [7] OAuth client credentials can be sent to cleartext HTTP token URLs

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | medium |
| Confidence rationale | Supported by worker source review, existing tests, or targeted reproduction recorded in scan artifacts. |
| Category | Cleartext credential transmission |
| CWE | CWE-319 |
| Affected lines | backend/app/services/api_connectivity.py:83, backend/app/services/api_connectivity.py:263 |

#### Summary

The OAuth client-credentials helper accepts HTTP token URLs and can post secrets over cleartext transport.

#### Root Cause

The OAuth client-credentials helper accepts HTTP token URLs and can post secrets over cleartext transport.

#### Validation

The OAuth client-credentials helper accepts HTTP token URLs and can post secrets over cleartext transport.

Validation method: static source trace plus targeted worker validation

#### Dataflow

See affected locations and discovery artifacts.

#### Reachability

Reachability calibrated for localhost Windows desktop app and authenticated role boundaries.

#### Severity

**Medium** — The OAuth client-credentials helper accepts HTTP token URLs and can post secrets over cleartext transport.

Severity changes if reachability or data sensitivity differs from the scanned local Windows HIPAA-adjacent workflow.

#### Remediation

Require HTTPS for token URLs except tightly controlled local synthetic tests.

Tests:
- Add regression tests for this dataflow and privacy/security invariant.

Preventive controls:
- Run Codex Security and privacy canary scans before release.

<a id="finding-8"></a>

### [8] Rules evaluation response echoes PHI-capable source chart fields

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | medium |
| Confidence rationale | Supported by worker source review, existing tests, or targeted reproduction recorded in scan artifacts. |
| Category | Sensitive data echo |
| CWE | CWE-359, CWE-200 |
| Affected lines | backend/app/api/rules_routes.py:63, backend/app/services/rules_engine.py:453 |

#### Summary

Rules responses include full source_fields from PHI-capable chart input.

#### Root Cause

Rules responses include full source_fields from PHI-capable chart input.

#### Validation

Rules responses include full source_fields from PHI-capable chart input.

Validation method: static source trace plus targeted worker validation

#### Dataflow

See affected locations and discovery artifacts.

#### Reachability

Reachability calibrated for localhost Windows desktop app and authenticated role boundaries.

#### Severity

**Medium** — Rules responses include full source_fields from PHI-capable chart input.

Severity changes if reachability or data sensitivity differs from the scanned local Windows HIPAA-adjacent workflow.

#### Remediation

Omit or sanitize source_fields before returning rule results.

Tests:
- Add regression tests for this dataflow and privacy/security invariant.

Preventive controls:
- Run Codex Security and privacy canary scans before release.

<a id="finding-9"></a>

### [9] Raw request query strings are persisted in forensic audit logs

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | Supported by worker source review, existing tests, or targeted reproduction recorded in scan artifacts. |
| Category | Sensitive data logging |
| CWE | CWE-532 |
| Affected lines | backend/app/services/audit.py:162, backend/app/services/audit.py:416 |

#### Summary

Audit rows store request query strings verbatim, so PHI or secrets in query params become durable logs.

#### Root Cause

Audit rows store request query strings verbatim, so PHI or secrets in query params become durable logs.

#### Validation

Audit rows store request query strings verbatim, so PHI or secrets in query params become durable logs.

Validation method: static source trace plus targeted worker validation

#### Dataflow

See affected locations and discovery artifacts.

#### Reachability

Reachability calibrated for localhost Windows desktop app and authenticated role boundaries.

#### Severity

**Medium** — Audit rows store request query strings verbatim, so PHI or secrets in query params become durable logs.

Severity changes if reachability or data sensitivity differs from the scanned local Windows HIPAA-adjacent workflow.

#### Remediation

Redact or allowlist query strings before audit persistence.

Tests:
- Add regression tests for this dataflow and privacy/security invariant.

Preventive controls:
- Run Codex Security and privacy canary scans before release.

<a id="finding-10"></a>

### [10] CSV and clipboard exports allow spreadsheet formula injection

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | medium |
| Confidence rationale | Supported by worker source review, existing tests, or targeted reproduction recorded in scan artifacts. |
| Category | CSV formula injection |
| CWE | CWE-1236 |
| Affected lines | frontend/src/App.tsx:1247 |

#### Summary

CSV cells are quoted but formula-leading values are not neutralized before export/clipboard.

#### Root Cause

CSV cells are quoted but formula-leading values are not neutralized before export/clipboard.

#### Validation

CSV cells are quoted but formula-leading values are not neutralized before export/clipboard.

Validation method: static source trace plus targeted worker validation

#### Dataflow

See affected locations and discovery artifacts.

#### Reachability

Reachability calibrated for localhost Windows desktop app and authenticated role boundaries.

#### Severity

**Medium** — CSV cells are quoted but formula-leading values are not neutralized before export/clipboard.

Severity changes if reachability or data sensitivity differs from the scanned local Windows HIPAA-adjacent workflow.

#### Remediation

Prefix formula-leading cells and add export tests.

Tests:
- Add regression tests for this dataflow and privacy/security invariant.

Preventive controls:
- Run Codex Security and privacy canary scans before release.

<a id="finding-11"></a>

### [11] Tracked Loom metadata may expose preview URLs for identifiable chart recording

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | low |
| Confidence rationale | Supported by worker source review, existing tests, or targeted reproduction recorded in scan artifacts. |
| Category | Potential PHI artifact exposure |
| CWE | CWE-200, CWE-359 |
| Affected lines | video-extract (2026-06-05)/reference-assets/loom-apollo-metadata.json:14 |

#### Summary

Tracked reference metadata contains preview URLs for a recording described as containing identifiable chart content.

#### Root Cause

Tracked reference metadata contains preview URLs for a recording described as containing identifiable chart content.

#### Validation

Tracked reference metadata contains preview URLs for a recording described as containing identifiable chart content.

Validation method: static source trace plus targeted worker validation

#### Dataflow

See affected locations and discovery artifacts.

#### Reachability

Reachability calibrated for localhost Windows desktop app and authenticated role boundaries.

#### Severity

**Medium** — Tracked reference metadata contains preview URLs for a recording described as containing identifiable chart content.

Severity changes if reachability or data sensitivity differs from the scanned local Windows HIPAA-adjacent workflow.

#### Remediation

Remove/redact external media URLs and scan release/source artifacts.

Tests:
- Add regression tests for this dataflow and privacy/security invariant.

Preventive controls:
- Run Codex Security and privacy canary scans before release.

<a id="finding-12"></a>

### [12] Settings and audit paths expose vendor connection material

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | medium |
| Confidence rationale | Supported by worker source review, existing tests, or targeted reproduction recorded in scan artifacts. |
| Category | Sensitive configuration exposure |
| CWE | CWE-200 |
| Affected lines | backend/app/services/app_settings.py:50, backend/app/services/audit.py:425 |

#### Summary

Settings/audit payloads can expose API client IDs, endpoint URLs, token URLs, and vendor connection metadata.

#### Root Cause

Settings/audit payloads can expose API client IDs, endpoint URLs, token URLs, and vendor connection metadata.

#### Validation

Settings/audit payloads can expose API client IDs, endpoint URLs, token URLs, and vendor connection metadata.

Validation method: static source trace plus targeted worker validation

#### Dataflow

See affected locations and discovery artifacts.

#### Reachability

Reachability calibrated for localhost Windows desktop app and authenticated role boundaries.

#### Severity

**Medium** — Settings/audit payloads can expose API client IDs, endpoint URLs, token URLs, and vendor connection metadata.

Severity changes if reachability or data sensitivity differs from the scanned local Windows HIPAA-adjacent workflow.

#### Remediation

Expose configured-state flags and redact connection material before audit/diagnostic output.

Tests:
- Add regression tests for this dataflow and privacy/security invariant.

Preventive controls:
- Run Codex Security and privacy canary scans before release.

<a id="finding-13"></a>

### [13] Admin reset utility duplicates secret env files into backups

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | Supported by worker source review, existing tests, or targeted reproduction recorded in scan artifacts. |
| Category | Secret sprawl |
| CWE | CWE-312, CWE-522 |
| Affected lines | scripts/update-local-admin.ps1:47 |

#### Summary

Admin reset copies the full secret .env to plaintext backups.

#### Root Cause

Admin reset copies the full secret .env to plaintext backups.

#### Validation

Admin reset copies the full secret .env to plaintext backups.

Validation method: static source trace plus targeted worker validation

#### Dataflow

See affected locations and discovery artifacts.

#### Reachability

Reachability calibrated for localhost Windows desktop app and authenticated role boundaries.

#### Severity

**Low** — Admin reset copies the full secret .env to plaintext backups.

Severity changes if reachability or data sensitivity differs from the scanned local Windows HIPAA-adjacent workflow.

#### Remediation

Avoid full .env backups or redact/exclude backup secrets.

Tests:
- Add regression tests for this dataflow and privacy/security invariant.

Preventive controls:
- Run Codex Security and privacy canary scans before release.

<a id="finding-14"></a>

### [14] Login access intelligence trusts spoofable forwarding headers

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | Supported by worker source review, existing tests, or targeted reproduction recorded in scan artifacts. |
| Category | Trusting untrusted forwarding headers |
| CWE | CWE-807 |
| Affected lines | backend/app/api/auth_user_routes.py:131, backend/app/services/access_intel.py:41 |

#### Summary

Login audit/access intelligence can treat caller-supplied forwarding headers as source IP.

#### Root Cause

Login audit/access intelligence can treat caller-supplied forwarding headers as source IP.

#### Validation

Login audit/access intelligence can treat caller-supplied forwarding headers as source IP.

Validation method: static source trace plus targeted worker validation

#### Dataflow

See affected locations and discovery artifacts.

#### Reachability

Reachability calibrated for localhost Windows desktop app and authenticated role boundaries.

#### Severity

**Low** — Login audit/access intelligence can treat caller-supplied forwarding headers as source IP.

Severity changes if reachability or data sensitivity differs from the scanned local Windows HIPAA-adjacent workflow.

#### Remediation

Ignore forwarding headers unless behind a configured trusted proxy.

Tests:
- Add regression tests for this dataflow and privacy/security invariant.

Preventive controls:
- Run Codex Security and privacy canary scans before release.

<a id="finding-15"></a>

### [15] Startup transcript can persist URL identifiers from access logs

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | Supported by worker source review, existing tests, or targeted reproduction recorded in scan artifacts. |
| Category | Sensitive data logging |
| CWE | CWE-532 |
| Affected lines | scripts/startup-windows-local.ps1:77, scripts/startup-windows-local.ps1:106 |

#### Summary

Startup transcript can capture Uvicorn access logs containing request paths/query strings.

#### Root Cause

Startup transcript can capture Uvicorn access logs containing request paths/query strings.

#### Validation

Startup transcript can capture Uvicorn access logs containing request paths/query strings.

Validation method: static source trace plus targeted worker validation

#### Dataflow

See affected locations and discovery artifacts.

#### Reachability

Reachability calibrated for localhost Windows desktop app and authenticated role boundaries.

#### Severity

**Low** — Startup transcript can capture Uvicorn access logs containing request paths/query strings.

Severity changes if reachability or data sensitivity differs from the scanned local Windows HIPAA-adjacent workflow.

#### Remediation

Disable access logs or redact diagnostic bundles.

Tests:
- Add regression tests for this dataflow and privacy/security invariant.

Preventive controls:
- Run Codex Security and privacy canary scans before release.

<a id="finding-16"></a>

### [16] Smoke script prints reset admin password

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | Supported by worker source review, existing tests, or targeted reproduction recorded in scan artifacts. |
| Category | Secret exposure in logs |
| CWE | CWE-532 |
| Affected lines | scripts/smoke.sh:91 |

#### Summary

Smoke reset mode prints the chosen admin password to stdout.

#### Root Cause

Smoke reset mode prints the chosen admin password to stdout.

#### Validation

Smoke reset mode prints the chosen admin password to stdout.

Validation method: static source trace plus targeted worker validation

#### Dataflow

See affected locations and discovery artifacts.

#### Reachability

Reachability calibrated for localhost Windows desktop app and authenticated role boundaries.

#### Severity

**Low** — Smoke reset mode prints the chosen admin password to stdout.

Severity changes if reachability or data sensitivity differs from the scanned local Windows HIPAA-adjacent workflow.

#### Remediation

Do not print password values; print only reset status.

Tests:
- Add regression tests for this dataflow and privacy/security invariant.

Preventive controls:
- Run Codex Security and privacy canary scans before release.

<a id="finding-17"></a>

### [17] Unauthenticated readiness diagnostics expose local paths

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | high |
| Confidence rationale | Supported by worker source review, existing tests, or targeted reproduction recorded in scan artifacts. |
| Category | Information disclosure |
| CWE | CWE-200 |
| Affected lines | backend/app/services/runtime_checks.py:52, backend/app/main.py:240 |

#### Summary

Public readiness details can include local database/upload/log paths.

#### Root Cause

Public readiness details can include local database/upload/log paths.

#### Validation

Public readiness details can include local database/upload/log paths.

Validation method: static source trace plus targeted worker validation

#### Dataflow

See affected locations and discovery artifacts.

#### Reachability

Reachability calibrated for localhost Windows desktop app and authenticated role boundaries.

#### Severity

**Low** — Public readiness details can include local database/upload/log paths.

Severity changes if reachability or data sensitivity differs from the scanned local Windows HIPAA-adjacent workflow.

#### Remediation

Redact public readiness or require auth for detailed diagnostics.

Tests:
- Add regression tests for this dataflow and privacy/security invariant.

Preventive controls:
- Run Codex Security and privacy canary scans before release.

## Reviewed Surfaces

| Surface | Risk Area | Outcome | Notes |
| --- | --- | --- | --- |
| Counselors can enumerate and read arbitrary timeliness clients | Authorization bypass / IDOR | Reported | Counselor-allowed timeliness and review-source APIs query clients without ownership scoping. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| Default bootstrap admin credential and reset behavior remain unsafe | Default credential | Reported | Static bootstrap admin defaults can create full admin access if a source/install flow misses randomization. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| OpenAPI metadata can execute script in the admin API harness | Cross-site scripting | Reported | OpenAPI metadata is interpolated into HTML and assigned to innerHTML in the admin API harness. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| API readiness harness can return live PHI and raw operation responses | Sensitive data exposure | Reported | API quick-pull and operation-test paths can return names, TSV rows, raw JSON, or body previews from external patient APIs. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| CSV and clipboard exports allow spreadsheet formula injection | CSV formula injection | Reported | CSV cells are quoted but formula-leading values are not neutralized before export/clipboard. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| OAuth client credentials can be sent to cleartext HTTP token URLs | Cleartext credential transmission | Reported | The OAuth client-credentials helper accepts HTTP token URLs and can post secrets over cleartext transport. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| Patient names, labels, and raw filenames persist into storage UI exports and downloads | PHI minimization failure | Reported | Patient display names and raw filenames can be accepted, persisted, returned, displayed, exported, and used as download names. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| Raw request query strings are persisted in forensic audit logs | Sensitive data logging | Reported | Audit rows store request query strings verbatim, so PHI or secrets in query params become durable logs. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| Rules evaluation response echoes PHI-capable source chart fields | Sensitive data echo | Reported | Rules responses include full source_fields from PHI-capable chart input. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| Settings and audit paths expose vendor connection material | Sensitive configuration exposure | Reported | Settings/audit payloads can expose API client IDs, endpoint URLs, token URLs, and vendor connection metadata. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| Tracked Loom metadata may expose preview URLs for identifiable chart recording | Potential PHI artifact exposure | Reported | Tracked reference metadata contains preview URLs for a recording described as containing identifiable chart content. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| Windows launcher batch files allow install-path command injection | Command injection | Reported | Unquoted batch set assignments let metacharacters in install paths execute as the launching user. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| Admin reset utility duplicates secret env files into backups | Secret sprawl | Reported | Admin reset copies the full secret .env to plaintext backups. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| Login access intelligence trusts spoofable forwarding headers | Trusting untrusted forwarding headers | Reported | Login audit/access intelligence can treat caller-supplied forwarding headers as source IP. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| Smoke script prints reset admin password | Secret exposure in logs | Reported | Smoke reset mode prints the chosen admin password to stdout. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| Startup transcript can persist URL identifiers from access logs | Sensitive data logging | Reported | Startup transcript can capture Uvicorn access logs containing request paths/query strings. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| Unauthenticated readiness diagnostics expose local paths | Information disclosure | Reported | Public readiness details can include local database/upload/log paths. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| JWT/RBAC core helpers | Authentication | No issue found | Reviewed; no separate surviving candidate beyond reported findings. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| Encrypted upload/secret storage | Storage | No issue found | Reviewed; no separate surviving candidate beyond reported findings. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| Rules and checklist | Deterministic workflow | No issue found | Reviewed; no separate surviving candidate beyond reported findings. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| Frontend static/CSS | Frontend | No issue found | Reviewed; no separate surviving candidate beyond reported findings. Evidence: artifacts/02_discovery/work_ledger.jsonl |
| Windows preflight/test scripts | Windows scripts | No issue found | Reviewed; no separate surviving candidate beyond reported findings. Evidence: artifacts/02_discovery/work_ledger.jsonl |

## Open Questions And Follow Up

- Dependency advisory research was not exhaustive in this privacy-focused initial scan.
  - Follow-up prompt: Run a focused backend/frontend dependency advisory scan after privacy implementation.
