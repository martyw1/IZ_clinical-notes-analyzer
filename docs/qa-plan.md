# QA Plan & Matrix

> Current source reference: `1.0.2` / build `2026.10.16.1` (`stable-local-desktop`). Dated examples and beta test results retain their original scope. See the [current documentation index](current-documentation-state.md).

## Coverage targets
- Unit/API tests for auth, health, role checks.
- Integration tests for workflow transitions and audit logging.
- E2E smoke test for login + dashboard rendering.

## Defect template
- ID
- Severity
- Steps to reproduce
- Expected vs actual
- Root cause
- Fix reference commit


For current operational behavior and release acceptance use [operator help](operator-help-current.md), [rules contract](v2-beta/rules-contract.md), [runbook](runbook.md) and [current validation](validation/current-work-2026-10-12.md). Live vendor approval remains external and all test records must be synthetic.
