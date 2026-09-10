# Security, Privacy, And Audit

> Release reference: the current app is `2.0.0-beta.3` / build `2026.09.03.1` (`beta-local-desktop-v2`). See the [current documentation index](../current-documentation-state.md).

V2 is local-first and keeps runtime data under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer`.

Patient names are excluded by default and are never used for matching. Browser payloads use patient display labels such as `Patient ID 307`. Audit logs capture safe summaries only and must not include names, secrets, tokens, Authorization headers, raw upstream payloads, full uploaded files, clinical narrative text, or signature image/base64 data.

The V2 audit service writes hash-chained JSONL events with action, actor, entity reference, outcome, safe details, previous hash, and event hash.

Release/incident evidence retains only redacted metadata. Retention, legal-hold, signing, and downstream credential/history-remediation decisions remain R3 owner approvals; beta.2 does not imply that any of those decisions is complete.
