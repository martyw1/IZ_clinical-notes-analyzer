# Laptop handoff S2 rerun, 2026-09-27

The office-manager login test now compares release channel and stability with
`VERSION.json`, alongside the existing version and build checks. It previously
hard-coded beta identity despite the current stable release metadata. No runtime
behavior or release metadata changed.

## Observed validation

- Full checkout office-manager browser suite, Edge: 33 executed, 33 passed.
- Backend timeliness, workflow-profile, password-recovery and password-reset
  tests: 20 passed; one existing Starlette/httpx deprecation warning.
- Password/recovery browser lifecycle: passed; 24 captures, zero page errors,
  password/session invalidation, one-use recovery and replacement recovery
  checks passed. Its owned runtime stopped and port closed.
- Authenticated synthetic office-manager screenshot inspected: navigation,
  dashboard, stable release footer and unvalidated LOC-change notice visible.
- Retained runtime restarted successfully; health and version responded. Retained
  administrator authentication still reports `password_change_required`.
- Final supported shutdown returned zero; port 8000 had no listener.

Tests used isolated synthetic profiles. Workflow test data was moved intact to
the laptop's approved quarantine instead of deleted. No retained clinical profile
was reset, moved or replaced, and no credentials were saved in this report.

## Station status

Automated rerun passed. S2 remains incomplete pending retained-account password
and recovery setup, authenticated retained-settings checks, persisted workspace
access after restart, and actual CSV/DOCX/PDF/TXT/MD reader/licensing verification.
Association registration alone is not proof of usable reader behavior. The
sender declined a recovery process; recovery-process qualification is not a
passed check. S3 was not started.

Detailed machine-local evidence and the operator report are under the Windows
Documents folder in `Laptop-Handoff-S2`, latest rerun
`rerun-20260927-174952`. The original failed test evidence is retained separately.
