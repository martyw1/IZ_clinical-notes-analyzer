# Direct clinician-only pull — November 6, 2026

## S0 and change
Preserved the existing shared checkout and patient-data boundaries. Added an administrator-only Pull clinicians action directly on Clinicians, with its own asynchronous job, progress/history, approved-connection gate, import concurrency guard, cancellation checks, and sanitized count-only forensic events. It reads /users and /clients relationship context without requesting treatment-plan or treatment-review endpoints, evaluating plans or writing plan versions. It updates staff and explicit primary assignments for already mapped local patients/facilities. Directory refresh runs after completion; existing profile authorization gates remain unchanged.

API routes: POST /api/v2/clinicians/pull, GET /api/v2/clinicians/pull/latest, GET /api/v2/clinicians/pull/jobs/{job_id}. Imported staff remain distinct from app login accounts. Administrators still require the existing approved Alleva connection. The shared import lock prevents overlapping clinician/roster/plan pulls.

## Validation
All five clinician backend tests passed, including denied unauthenticated/blocked-config calls, an actual asynchronous clinician-only job against a synthetic HTTP vendor server, persistent latest-job retrieval, saved directory names, unchanged treatment-plan version count, and proof that no treatment-plan/review endpoint was requested. TypeScript and the frontend production build passed.

## Interactive test limitation
Prepared an isolated OS-local synthetic app/test vendor server; no production patient database or real vendor credentials were used. Windows Computer Use was initialized and Edge was found. Before any test UI interaction, the tool stopped with: "could not determine the current browser URL on Windows with enough confidence to enforce policy." No browser walkthrough was completed, and no live-tenant success is claimed. The isolated test server was stopped. The initial QA attempt correctly rejected the loopback vendor under the restricted local-client environment; the isolated test setup was then configured with the test environment. No application production gate was relaxed.
