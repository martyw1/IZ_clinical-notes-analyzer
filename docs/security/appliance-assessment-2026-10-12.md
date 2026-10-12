# Laptop, HIPAA, security and performance assessment

Assessment date: October 12, 2026. Current source candidate: **1.0.1 / build 2026.10.12.1 / stable-local-desktop**. This is a read-only evidence assessment plus the separately documented source fixes, not a vulnerability scan, penetration test, legal opinion or certification. Current source validation belongs in [the release ledger](../validation/current-work-2026-10-12.md); prior test results below retain their scope.

## Decision

The local architecture supports a single-user appliance workflow, but software functionality alone does not establish production HIPAA readiness. R3 must close or formally accept the external control gaps below before claiming a fully qualified regulated deployment. Intended steady state is the app's service/browser and OneDrive plus normal Windows services. ChatGPT is absent from the client workload and is not required by the app. No real patient runtime data, credential values or vendor payloads were needed for this assessment.

## Laptop evidence and limits

The inspected host is a Dell 15 DC15250, Core 3 100U (6 cores/8 threads), 8 GB RAM and healthy approximately 512 GB SSD with roughly 350 GB free. Windows 11 Home reports 26H2 build 26300.9457. Defender reports active normal real-time/behavior/tamper protection and all firewall profiles enabled; McAfee is also registered, so IT should confirm the intended provider without disabling either during handoff. Quick Assist and Edge are available.

The inspected developer account is administrative; PasswordRequired=false and local password length policy zero do not prove a blank password, but do not establish a suitable client sign-in policy. AC screen timeout was about nine hours and AC sleep never; automatic secure lock was not established. Device encryption/BitLocker and Secure Boot queries were denied to the unelevated session. Encryption is **unverified**, not proven off. Recent encryption-key retrieval errors warrant IT confirmation of successful encryption and recovery-key escrow. Windows Time was configured for NTP but stopped; successful recent time synchronization was not established. Date-dependent clinical rules require a reliable Windows clock and facility timezone.

SSD health was healthy; a prior controller event also involved a removable USB device, so no SSD failure was inferred. Old developer automation tasks had expired triggers/old failure outcomes and were left unchanged. No OS policy, account, antivirus, scheduled-task, encryption or time-service configuration was changed by the assessment.

## HIPAA control assessment

The current [HHS Security Rule summary](https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/index.html) requires appropriate administrative, physical and technical safeguards. Proposed rule changes must not be represented as the current rule. Evidence here addresses implementation, not applicability or organizational compliance.

| Control area | Evidence | Gap / required owner action |
| --- | --- | --- |
| Risk analysis and management | Local data flow, source code, host settings and synthetic workflow reviewed | R3 must maintain the organization-wide risk analysis, risk acceptance and remediation owners; include this laptop and OneDrive |
| Assigned security responsibility | Technical boundary and support path documented | Name security/privacy owners and escalation/incident contacts |
| Workforce access and training | App roles, unique accounts, forced initial password change, one-time recovery | Assign minimum necessary office-manager role; documented onboarding/offboarding and periodic access review; train on exports, support and lost-device reporting |
| Workstation/physical security | Localhost architecture; Windows lock instructions | Verify standard-user client account, automatic secure lock, sign-in controls, physical custody, travel and device disposal |
| Access control | Authentication, password epoch revocation, role/facility checks, exact source/plan/version scope | Host administrator and unlocked session remain powerful; validate operating policy and session handling on exact delivered build |
| Audit controls | Structured redacted events and hash-chain verification; privileged Forensic Logs | Define review cadence, access, retention/legal hold and protected independent copies; chain is not immutable against host admin; not every list read is proven audited |
| Integrity | Encrypted envelopes, immutable plan versions, hashes and deterministic source checks | Confirm backup restoration and retained originals; chain verification scope includes legacy limits |
| Authentication | Password policy, reset/recovery and attempt controls | Protect recovery code; no shared app/Windows credentials; approve emergency access procedure |
| Transmission security | App binds loopback; vendor TLS verification present | Use approved HTTPS endpoints; prevent unintended external binding, unapproved remote access and PHI in support/chat |
| Storage confidentiality | Encrypted uploads and API configuration | SQLite identifiers/dates/status metadata remains readable to OS-authorized access; verify whole-device encryption and recovery escrow |
| Contingency plan | Verified encrypted same-account backup tooling | Device/account-loss restore remains unqualified; define RPO/RTO, backup schedule, protected copy and test restoration on replacement hardware |
| Incident/breach handling | Existing privacy incident record remains preserved | Credential rotation, downstream copy inventory and history disposition still open; R3 must evaluate/report incidents under applicable rules |
| Vendor/business associates | Optional LLM disabled; Alleva import gated | Confirm approved vendor scope/contracts and OneDrive business tenant/BAA; personal sync is not an assumed acceptable substitute |
| Privacy/minimum necessary | No note text or secrets intended in logs; CSV omits names/narrative | IDs/dates and exports still may be PHI; approve sharing, disclosure controls, data retention/destruction and support workflow |
| Policies/documentation | Current operator/technical guides and historical evidence index | HIPAA documentation retention and clinical record retention are distinct obligations; legal/records owner defines each |

[HHS cloud guidance](https://www.hhs.gov/hipaa/for-professionals/special-topics/health-information-technology/cloud-computing/index.html) explains that a cloud provider storing ePHI can be a business associate even when it cannot decrypt the data. OneDrive sync therefore needs the correct organizational agreement, tenant controls, restricted sharing and retention; encryption alone does not remove this obligation. If records are subject to 42 CFR Part 2, the [HHS Part 2 guidance](https://www.hhs.gov/hipaa/part-2/index.html) identifies the February 16, 2026 compliance date for the updated rule. R3's legal/privacy owner must determine applicability to its substance-use-disorder records and consent/disclosure workflows.

## Security architecture and residual risks

Source assessment found a loopback service, restricted hosts/CORS, disabled normal API documentation, role-scoped endpoints, bcrypt/PBKDF2 password handling, expiration/password-epoch checks, parameterized database access and encrypted source/configuration storage. Production/local-client configuration rejects unsafe secrets. Uploads use generated names and encrypted envelopes; matching uses exact source/identity/version rather than guessed names. The API harness remains privileged and must not be treated as a general-purpose approved external fetcher.

Confirmed pre-change gaps included missing consistent sensitive-response cache/security headers, memory amplification from applying the per-file read bound without the remaining aggregate budget, and extracting subsequent PDF pages after the text limit was already exceeded, stale branding/version assertions, and documentation mismatches. Their fixes and new validation are recorded in the current release ledger; do not infer remediation from this paragraph alone. Browser session storage, local metadata, privileged host access, dependency maintenance, unsigned distribution, large-data rendering and independent audit protection remain areas for ongoing review. No claim of exhaustive vulnerability discovery or dependency-advisory clearance is made.

The existing [July privacy incident record](privacy-incident-s0-2026-07-10.md) remains active evidence. No historical clinical blobs were fetched and no credential values were printed. Deleting old files or rewriting history would not by itself prove incident containment; owner-authorized rotation and disposition are required.

## Functional and performance evidence before this patch

The source assessment used an isolated synthetic profile and real local browser/backend, never the client's database. Login, mandatory recovery setup, dashboard, patient detail, exact saved plan, 42-step checklist, encrypted binder upload, Help and sign-out worked. Anonymous roster access returned 401; office-manager user administration and audit access returned 403. A synthetic audit chain verified 12 of 12 events. One 347-byte source became a generated-name 555-byte encrypted envelope, not a plaintext archive.

Five requests per route on the tiny fixture measured dashboard approximately 18–41 ms, patient roster 22–37 ms, treatment-plan roster 22–35 ms and current-user 5–6 ms. The service working set was approximately 105 MB plus a small wrapper. Development tools were present during those measurements, so they are smoke observations, not a clean appliance baseline or worst-case capacity claim.

Pre-patch verification found 618 backend tests passed and one reproducible stale-branding assertion failed; 184 frontend tests and TypeScript checks passed. These numbers do not describe post-patch acceptance. [The current ledger](../validation/current-work-2026-10-12.md) records the final tests/build/browser/package scope.

Performance risks are full roster materialization and rendering, bounded but potentially expensive document extraction, multiple active jobs, antivirus/OneDrive competition and 8 GB memory. Normal small-data use appears viable; full operational data volume, largest accepted binders, long-session stability, disk-full recovery, forced power-loss and device-loss restoration need separate realistic synthetic acceptance. Use one large operation at a time and inspect completion/warning counts. Do not disable security services to improve speed.

## Prioritized handoff actions

| Priority | Action / owner | Acceptance evidence |
| --- | --- | --- |
| Before regulated handoff | R3 IT: verify device encryption, key escrow, sign-in, automatic lock and reliable clock | Recorded controls on intended Windows client account |
| Before regulated handoff | R3 security: complete credential incident rotation/copy inventory and risk disposition | Approved incident closure or explicit documented residual acceptance |
| Before regulated handoff | R3 records/IT: same-account backup plus device-loss recovery plan | Successful isolated restore and replacement-device recovery exercise, RPO/RTO |
| Before cloud storage of PHI | R3: confirm OneDrive agreement/tenant/sharing/access/retention | Approved business-associate and tenant configuration evidence |
| Before live vendor pull | R3/Alleva: approved tenant and mapping/read-only/pagination/rate limits | Supervised approved non-PHI end-to-end validation |
| Before clinical policy claim | R3/Marleigh: confirm LOC update rule | Reviewed rule release with clinical tests; no provisional-date compliance shortcut |
| Before distributing new build | Engineering: validate exact prepared package and client path | Tests, build gates, ZIP hash/receipt and synthetic first-use/restart evidence |
| Ongoing | R3: train office manager, review access/audit and patch Windows/browser/dependencies | Scheduled operational records and incident reporting path |

This report records recommendations; no Windows configuration or client-data remediation was performed. Source changes are described separately in the release ledger. Remote activity was official public guidance research only; source/host inspection and synthetic checks were local. LLM analysis interpreted that evidence. No measured token, inference-memory or service-billing telemetry is available from this report.


October 12 patch verification update: source version consistency tests passed (2), frontend tests passed (184), TypeScript and production frontend build passed. Isolated synthetic live office-manager login/recovery, exact patient and saved-plan/42-step checklist, Help and sign-out passed; `/api/version` reported 1.0.1 / 2026.10.12.1 with no-store/nosniff, and the audit chain verified 6/6 events. Full backend and exact prepared-package status remain in the current ledger. Direct offline HTML visual opening was blocked by browser file-protocol policy; static structure/local-link validation is separate evidence, not a visual rendering claim. The numbered desktop guide shortcut was created and its target verified.
