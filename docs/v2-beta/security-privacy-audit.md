# Security, privacy and audit contract

Current source 1.0.1 / build 2026.10.12.1 / stable-local-desktop. This is an implementation contract, not certification. See the [current assessment](../security/appliance-assessment-2026-10-12.md).

Runtime data remains under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`, outside the repository. Uploaded sources and saved API configuration use encrypted envelopes. SQLite identity/date/status metadata is not fully encrypted by application storage; disk encryption, Windows access controls and approved backups remain necessary safeguards.

Identity joins use MRN plus exact source/facility/plan/version scope, never name alone. Authorized patient-name display may be derived from encrypted patient source snapshots when enabled; names are not valid join keys and must not enter diagnostics or audit details. Browser clinical views can contain sensitive information, so a localhost boundary does not remove authentication, workstation or privacy requirements.

Primary V2 audit records are in SQLite with safe structured details and a SHA-256 linked chain. The common wrapper supports JSONL fallback on logging failure. Events include actor/action/target/outcome/time and safe metadata. Audit verification reports current-format versus legacy scope. This is tamper evidence, not immutable independent storage against a host administrator. Redaction patterns are a backstop; event callers must omit clinical narrative, original filenames, raw vendor payloads, names, secrets/tokens/Authorization, passwords, recovery codes and signature images/base64.

Keep detailed authentication/recovery, review, settings, import/upload, export and error metadata without increasing PHI exposure. Do not claim every request is fully audited. Audit retention remains `local_policy_required`; R3 must define access review, retention, legal hold, protected off-device evidence and incident response. Current backup uses an encrypted `.izcnabackup` bound to the same Windows account/computer through CurrentUser DPAPI; device-loss recovery is an open operational requirement.

Optional LLM stays disabled by default. Live Alleva import remains gated; configuration tests do not authorize production PHI. Credential incident containment/rotation and downstream history disposition remain owner gates in [open blockers](../open-blockers.md). Do not modify historical incident evidence or upload it to ordinary support channels.
