# Chart Review Workflow — Build Prompt for ChatGPT 5.3-Codex

Use the following prompt verbatim (or with minor environment-specific edits) to direct ChatGPT 5.3-Codex to architect, build, test, harden, and validate an enterprise-ready clinical chart review application.

---

You are ChatGPT 5.3-Codex acting as a **Chief Architect + Application Architect + Senior Software Engineer + QA Lead + SRE + Security Engineer + Systems Engineer**. Build a production-grade application named **Chart Review Workflow** for a recovery services center.

## 1) Mission and domain context

This app is used by clinicians, counselors, and facility managers to analyze patient clinical notes and chart documentation for compliance risks and remediation needs.

The app must support:
- Non-technical users with clear UX and guided workflows.
- Multi-user secure login and role-based permissions.
- Forensic-level audit logging suitable for regulatory review (Pennsylvania, U.S.).
- Robust workflow management from counselor submission through admin review and return-for-corrections.
- Future integration with Alleva EMR APIs.
- Immediate support for file uploads exported from Alleva (patient clinical notes and related records).

## 2) Non-negotiable requirements

### 2.1 Security, identity, and access
- Implement robust authentication and authorization with RBAC.
- Roles at minimum: `admin`, `counselor`, `manager`.
- Seed initial admin account: username `admin`, password `r3`.
  - On first login, force password reset and require strong password policy.
- Secure session management, CSRF protection, password hashing (Argon2id or bcrypt with strong work factor), account lockout/rate limiting, optional MFA-ready architecture.
- Admin-only screens for user management, rule management, and deep logs.

### 2.2 Database and architecture
- Use PostgreSQL as the primary database.
- Use proper migrations, foreign keys, indexing strategy, transaction safety, and row-level integrity.
- Design for local execution (macOS + Windows 10/11) and future cloud deployment (VPS/Kubernetes-ready).
- Containerize with Docker and provide docker-compose for local reliability.

### 2.3 Forensic logging and observability
- Log all significant events with immutable-style audit records:
  - Login/logout/auth failures
  - User CRUD and role changes
  - File uploads/downloads/deletes
  - Button/action clicks for sensitive operations
  - Rules changes
  - Workflow state transitions
  - Errors/exceptions and stack traces
  - Background jobs and retries
- Every log entry must include:
  - Timestamp (UTC + display local)
  - Actor (user id/username/role)
  - Source IP/user-agent
  - Correlation/request ID
  - Action, target entity, before/after diffs where applicable
  - Outcome status and severity
- Logging should be inspired by CLF/ELF/CEF concepts while normalized into a queryable schema.
- Provide two log views:
  1. **Technical forensic logs** (full fidelity, admin only)
  2. **Human-readable activity stream** (plain-language summaries, admin only)
- Ensure tamper-evident approach (hash chaining or signed log batches) for high-trust auditability.

### 2.4 UI/UX requirements
- Include `r3recoveryservices.com` logo in header.
- Display a persistent top-of-screen status message indicating latest action result.
- Build a simple, highly usable web interface for non-technical staff.
- Implement role-specific dashboards:
  - Counselor dashboard: personal queue, submissions, pending fixes, completion stats.
  - Admin dashboard: facility-wide stats, counselor productivity, compliance trends, queue health.

### 2.5 File ingestion and analysis
- Support multiple file uploads at once.
- Accepted formats configurable (e.g., PDF, DOCX, TXT, CSV export bundles).
- Track upload metadata (who, when, checksum, source).
- Queue and process files reliably with retries and failure dead-letter strategy.
- Log each upload and analysis step.

### 2.6 Rules management engine
- Admin can create/edit/disable/version rules that control analysis logic.
- Rule changes must be versioned and auditable with effective dates.
- Provide simulation mode: run analysis with draft rules before publishing.
- Keep rule execution explainable (which rules triggered, why).

### 2.7 Workflow states and reporting
Implement chart workflow stages with explicit transitions:
- Draft
- Submitted to Admin
- Returned for Update
- In Progress Review
- Completed
- Verified

Requirements:
- Role-gated transitions.
- Mandatory comments on return/rejection.
- Full transition history.
- Exportable reports by status, counselor, date range, and compliance category.

## 3) Clinical chart-audit logic to encode (from existing process)

Model the app’s compliance checks around this checklist-driven workflow:

1. Chart Audit form header
   - Client Name, Level of Care, Discharge Date, Primary Clinician, Other.

2. Client Overview verification
   - Confirm level(s) of care, admission/discharge context, primary clinician assignment.

3. Admission packet checks
   - Intake Packet (Initial) completed at admission.
   - Client Rights in House (Initial) completed at admission.
   - Attendance Policy Consent with explicit Accept/Decline.
   - Assurance of Freedom of Choice with explicit Accept/Decline.

4. Emergency Contact / ROI checks
   - Exists, completed, signatures present, proper disclosures, expiration monitored, annual re-sign logic.

5. Labs / UDS checks
   - Weekly random testing evidence with policy-driven tolerance windows.

6. Medication checks
   - Medication list completeness and proper classification (home meds vs prescribed).
   - If empty, require explicit “no meds documented” evidence reference.

7. Biopsychosocial checks
   - Assessment completed at admission.
   - Instruments present: Columbia Suicide Severity Rating Scale, BARC, ASAM, GAD, PHQ-9.
   - Define policy whether checks are presence-only or require documented follow-up for elevated scores.

8. Medical History & Physical checks
   - H&P within last 12 months OR referral within 30 days (anchor date configurable and explicit).

### Policy ambiguity handling
Some timing and evidence rules are ambiguous. Build a configurable policy layer so admin can define and revise:
- What “at admission” means (same day, 24h, 72h, etc.).
- “Weekly” interpretation and grace period.
- 1-year re-sign anchor date definition.
- Required evidence format standards.

## 4) Technical delivery expectations

Choose a maintainable enterprise stack (example acceptable stack: React + TypeScript frontend, FastAPI or NestJS backend, PostgreSQL, Redis queue, Celery/BullMQ workers).

You must deliver:
1. Full system architecture and ADRs.
2. Data model and ERD.
3. API contracts (OpenAPI).
4. Working implementation with migrations and seed data.
5. Automated tests:
   - Unit
   - Integration
   - API contract tests
   - End-to-end UI tests
   - Security tests (auth/access controls)
6. QA plan with test matrix and defect tracking format.
7. SRE runbook:
   - Health checks
   - Structured logs/metrics/traces
   - Backup/restore procedures
   - Incident response playbooks
8. CI/CD pipeline with linting, tests, vulnerability scanning, and quality gates.
9. Deployment docs for local (macOS/Windows) and VPS target.
10. Hardening checklist (OWASP ASVS aligned where practical).

## 5) Coding and reliability standards

- Defensive coding and comprehensive exception handling.
- No silent failures; every failure path logged with actionable context.
- Idempotent background jobs and retry-safe processing.
- Input validation on all boundaries.
- Pagination/filtering for all large list endpoints.
- Feature flags for risky/in-progress features.
- Backward-compatible schema migration strategy.

## 6) Output format and execution protocol

Work in phases and do not skip validation:

Phase A — Plan
- Provide architecture, risks, assumptions, and implementation plan.

Phase B — Build
- Generate code incrementally with explanations and file tree.

Phase C — Verify
- Run all test suites; fix failures before proceeding.

Phase D — QA + Security
- Perform quality and security checks; fix defects.

Phase E — SRE readiness
- Add monitoring/logging/operational docs and runbook.

Phase F — Final acceptance
- Provide:
  - “What was built” summary
  - Test evidence and coverage summary
  - Known limitations and next steps
  - Explicit statement of production readiness level

## 7) Definition of done

Do not declare completion until:
- All tests pass.
- Critical/high security issues are remediated or explicitly documented with mitigations.
- RBAC and audit log controls are verified.
- Workflow transitions and reporting are verified.
- Seed admin login flow (with forced password change) is verified.
- Local deployment is reproducible from docs.

If any requirement is unclear, propose a default, document it, and proceed without blocking.

---

## Suggested operator note

When running this prompt with ChatGPT 5.3-Codex, ask it to output results as:
1) architecture docs, 2) implementation PR-sized chunks, 3) test evidence after each chunk, and 4) final hardening checklist.

