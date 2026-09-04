# Isolated office-manager smoke interface

Run from the repository root with existing installed dependencies:

```powershell
powershell -NoProfile -File scripts/test-office-manager-smoke.ps1 -Scenario harness -Case all -BrowserChannel msedge -EvidenceDir .omo/evidence/office-manager-production-fixes
```

Use `chrome` for the installed Google Chrome executable. `-Scenario all` discovers every `frontend/e2e/office-manager/*.spec.mjs`; otherwise the scenario selects its matching filename. Tests use `@happy` or `@edge` in their titles. `-Case all` runs both. Zero discovered tests, failures, skipped tests, timeouts, and teardown failures make the invocation fail.

Each invocation makes a unique child of `-EvidenceDir`; it never overwrites an earlier run. The runner does not build the frontend. Build the current UI in a coordinated source slot before claiming a changed UI is verified. Each receipt records the actual served frontend index hash and runtime `/api/version`.

## Discovery isolation

Ordinary `npm --prefix frontend run test:e2e` keeps its existing workflow-profiles and treatment-plan-pull suites. Its default config excludes this entire office-manager directory, including Node guard self-tests. Only the dedicated `playwright.office-manager.config.mjs` discovers the isolated scenarios; use the PowerShell runner above for actual execution.

The discovery-only regression starts no application server or browser and requires no credentials or synthetic data:

```powershell
node --test frontend/e2e/office-manager/support/discovery-check.mjs
```

It verifies that the ordinary config lists all seven existing tests and that the dedicated config lists every office-manager scenario file. A temporary synthetic metadata-only contract supports module-scope fixture references; it seeds no runtime and is removed afterward. No scenario body runs and its placeholder IDs/files are not runtime fixtures. The check intentionally uses a filename without `.test` or `.spec` so a future exclusion regression cannot recursively discover the check itself.

## Feature-owned specs

```javascript
import { test, expect, login, apiFor, fixtureContract, capture, writeEvidence } from './support/fixtures.mjs'

test('selected behavior works @happy', async ({ page }) => {
  const selected = fixtureContract().plans.primaryV1
  await login(page) // office_manager by default
  const api = await apiFor('office_manager')
  try {
    const response = await api.get(`/api/v2/treatment-plans/${selected.patient_id}`, {
      params: { plan_version_id: selected.plan_version_id, patient_record_id: selected.patient_record_id },
    })
    expect(response.status()).toBe(200)
    await capture(page, 'task-N-selected.png')
    writeEvidence('task-N-selected.json', { status: response.status(), selectedVersionId: selected.plan_version_id })
  } finally { await api.dispose() }
})
```

`credentials(role)` is also exported for controlled reauthentication scenarios. Its random password exists only in process memory; never log, attach, or write it. Do not persist request bodies/headers, tokens, cookies, storage state, raw server exceptions, traces, or video. `capture` masks all inputs and checks for known secrets in visible text. `writeEvidence` rejects known generated secrets. Record boolean/count/immutable-ID assertions, not whole responses. The reporter intentionally omits exception bodies; use safe assertion receipts to locate failures. Browser page/console events are recorded as counts only. Unhandled page errors fail the scenario. The default browser context blocks non-runner origins. Specs may intercept specific localhost failure paths for adverse-transition tests, but must identify simulated failures as such.

## Failure-artifact privacy boundary

`failurePrivacy.mjs` exports a privacy-only `test` and `expect`, with no office-manager runtime/contract requirement. The smoke fixtures extend that `test`. Its public `failurePrivacy` automatic fixture synchronously replaces public error detail fields during teardown while retaining the errors, their count and failed/timed-out status. Credential-using custom test fixtures must depend on `failurePrivacy`; the guard itself must not depend on page/context/request fixtures. Its separate five-second teardown budget also applies after ordinary test timeout.

The runner removes inherited Playwright/debug/inspector/capture environment overrides and sets `PLAYWRIGHT_NO_COPY_PROMPT=1` to prevent the separately cached page snapshot. Trace/video/automatic screenshots are off and the reporter omits raw error details. Error sanitation alone cannot remove a page snapshot captured earlier. The snapshot environment switch is installed Playwright behavior, pinned by regression rather than a promised stable public API.

This is **not** a universal credential-persistence guarantee: beforeAll/afterAll, worker/pre-fixture/post-guard failures and independently written attachments are excluded. Do not put credentials in those lifecycle paths. Original-spec adapters must import the privacy-only test and use an explicitly safe capture configuration; CLI trace-off alone cannot install the guard or disable default screenshots. No private fixture override or status weakening is used. Receipts distinguish the intended harness write policy from a per-run artifact scan, which is not performed by an ordinary smoke run.

Standalone verification uses only noncredential sentinels, retains deliberate failure files, confirms nonzero exit/error counts, and records unsupported all-hook cases separately:

```powershell
node --test frontend/e2e/office-manager/support/failurePrivacy.test.mjs
```

It includes installed headless Edge/Chrome about:blank probes, no clinical runtime. Each invocation retains a fresh `failure-privacy-<uuid>` evidence child and removes only its marker-owned temporary directory after all owned processes stop. Do not treat a clean final scan or later deletion as proof that earlier raw writes never happened.

## Fixture contract

`fixtureContract()` reads a per-run sanitized contract. Seeding finishes before discovery, so it is safe at module scope.

| Field | Meaning |
| --- | --- |
| `users.{admin,office_manager,counselor,viewer}` | `{id,username}`; no password/token |
| `facilities.{primary,secondary}` | Actual generated facility IDs |
| `patients.{primary,secondary,sourceCollision,facilityCollision}` | Actual `patients.id`, not MRN |
| `plans.{primaryV1,primaryV2,secondaryPlan,patientTwo,sourceCollision,facilityCollision}` | Actual immutable version selectors |
| `files.{aggregate,binder}` | Synthetic upload paths resolved by Python to the physical OS-local directory; usable only while this run is alive |
| `physical_data_dir` | Python-resolved directory; may differ from the logical path because Windows packaged-app redirection is active |

Every plan selector contains `patient_id` (synthetic MRN), `patient_record_id`, `plan_id` (source record ID), `source_mode`, `plan_version_id`, and `version_ordinal`.

Primary MRN is `TEST-PATIENT-001`; second MRN is `TEST-PATIENT-002`. Primary MRN has `smoke-primary` v1/v2 and sibling `smoke-secondary`. Both main patients are in the primary facility and visible to the office manager/viewer. The counselor is assigned only the first main patient. Admin has both facilities; other accounts have primary only. Source collision is an offline synthetic Alleva-source record for the same MRN/plan ID; live import remains disabled. Facility collision is a genuinely separate patient/version in the second facility, not a renamed ID. Setup is offline real store/SQLite fixture work, not UI account creation/import coverage.

## Safety and lifecycle

Runtime data is a new direct child of `%LOCALAPPDATA%/IZ-CNA-OfficeManager-Smoke`, with a random `run-<uuid>` name and matching owner marker. Existing paths, outside paths, symlinked ancestors, missing runtime executables, and external URLs are refused before runtime/evidence creation. Even a supplied loopback `-BaseUrl` is refused: this harness cannot attach to another service. `-LocalAppDataDir` exists for safety tests, not for data reuse.

The environment explicitly disables inherited app configuration by clearing `IZ_CNA_*` and supplying new secrets, app-data path, database path, allowed hosts and frontend origin. Backend binds to `127.0.0.1` on a newly allocated port under restricted `local-client` configuration. No user installation, vendor configuration, old runtime, or personal browser profile is opened. All process launches are recorded; `finally` closes Playwright-owned browsers/contexts and terminates only still-live child-process handles and their descendants. The owned synthetic directory is removed after process and port teardown. Forced OS termination of the supervising runner is not a graceful shutdown mechanism; allow it to finish normally.

`task-1-harness.json`, `playwright-results.json`, `browser-*.json`, `surface-*.json`, and `teardown.json` are the per-run receipts. Runtime termination normally records nonzero exit because Windows `taskkill` ends the owned server process; `treeTerminationExitCode: 0`, `runtimeStopped: true`, and all owned-process stop flags are the teardown observables, not the server's forced exit code.

## Bounded hands-on runtime

```powershell
powershell -NoProfile -File scripts/test-office-manager-smoke.ps1 -Scenario harness -Case happy -BrowserChannel chrome -InteractiveSeconds 300 -InteractiveRole admin -EvidenceDir .omo/evidence/office-manager-production-fixes
```

After automated checks, this opens a separate headed installed browser, signs in to the chosen synthetic role, writes `interactive-ready.json` with exact URL/window title/executable/PIDs, and holds that owned runtime for at most 900 seconds. The file is the readiness signal; stdout announces dispatch before browser login settles. Record actual hands-on actions separately. `handsOnActionsClaimed` is always false in the harness receipt. The deadline closes this context and runtime automatically. `-Headed` only changes automated test visibility and does not hold a context open.

### In-memory native signout/relogin credentials

Only a native controller that must type the password again after real signout should add `-InteractiveCredentialsFromEnvironment`. It must also specify `-InteractiveSeconds` from 1 to 900 and generate a fresh password in its own memory using `Qa1!` followed by 48 lowercase random hexadecimal characters (`randomBytes(24).toString('hex')`). Supply that value only as `IZ_OM_INTERACTIVE_PASSWORD` in the spawned PowerShell child's environment, never in command arguments or a shell assignment recorded in a transcript. Retain the value in the native controller's memory for the later approved native typing action; discard that reference when the bounded session finishes.

Without this explicit switch, inherited input is ignored and the existing fresh random-password generator is unchanged. With the switch, absent/empty input, malformed synthetic shape, or a missing positive bound is refused with a fixed code before runtime/evidence setup. The runner removes the reserved input from downstream inherited environments; only its existing `IZ_OM_PASSWORD` and bootstrap-password variables carry the selected run password. Existing screenshot/evidence secret guards therefore recognize the actual selected value. Do not print, persist, attach, copy to the clipboard, or send this value through files/IPC. This is not a mechanism for reading real browser credentials or another process's memory.

Focused credential guard and in-memory handoff checks, with no application runtime:

```powershell
node --test frontend/e2e/office-manager/support/native-credentials.test.mjs
```

Those checks report only scalar equality/redaction/refusal outcomes. They do not claim native login/signout/relogin coverage; record that later in the actual native controller's QA evidence.

## Prepared runtime

Use `-RuntimeMode prepared -PreparedExecutable <verified-new-release-exe>` to start the exact packaged executable directly, with the same fresh synthetic data and `IZ_CNA_PORT`; never install it over the user's app. Seed code uses the checked-out backend, so only test a package built from the same source/version. A missing executable is covered by the refusal tests. Successful newly built package validation belongs to the release task and is not implied by checkout-mode passes.
