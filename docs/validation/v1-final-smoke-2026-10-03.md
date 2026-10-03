# V1 final source smoke — 2026-10-03

Scope: `1.0.0` / build `2026.09.21.2`, `stable-local-desktop`, on this Windows laptop and OneDrive source checkout. Before testing, local `main`, `origin/main`, and GitHub's live `refs/heads/main` all matched `21636e777833109c820daad7d4214170f2694116`. No initial merge or push was needed.

## Results

- Frontend production build and `npx tsc --noEmit`: exit 0.
- Frontend unit suite: 184 tests across 28 files passed.
- Focused backend release consistency, readiness, auth/RBAC, and timeliness suite: 21 passed in 58.38 seconds; one dependency deprecation warning.
- Full isolated Edge office-manager smoke: all 33 discovered scenarios executed and passed, zero reporter errors, runner exit 0.
- Node syntax check of the updated smoke spec and `git diff --check`: passed.

The browser suite exercised real localhost UI/backend login, four roles, version/footer consistency, roster and saved-version selection, source/facility isolation, denied exports and assignments, history/actions/corrections, filtered CSV downloads, manual JSON/binder uploads, expired and delayed sessions, dashboard recovery, saved sync-status rendering, Help, and responsive layouts. Vendor fixtures and sync-status cases were synthetic; this run made no live Alleva import calls.

## Smoke assertion repair

Two runs reproduced a stale Help assertion: 32 of 33 scenarios passed, with the roster edge scenario failing at `roster.spec.mjs:146` in its Help phase. The test expected “a new import never silently replaces your selection”; current Help says “A new import does not silently replace your selection.” Updated both desktop and narrow-screen assertions to the current sentence. All isolation and access-denial assertions remain intact. No application behavior or clinical rule changed.

The first command wrapper reached its 120-second limit; its harness subsequently wrote a complete failed result and successful cleanup receipt. The extended-budget reproduction and final fixed run completed normally. Final local evidence: `.omo/evidence/v1-final-smoke-2026-10-03-fixed/all-all-msedge-5004e3d2-4583-43c2-a2fe-de0f6a465348/`, including `playwright-results.json`, screenshots, and `teardown.json`. Final cleanup confirms runtime stopped, all owned processes stopped, synthetic data removed, and no personal processes targeted.

## Boundaries and hygiene

This is source smoke validation, not a rebuilt installer, Windows 10 client qualification, full backend-suite rerun, live vendor validation, or clinical sign-off. The LOC-change window remains unvalidated by R3/Marleigh. The prior 619-test full backend result is documented in `clinical-rules-help-live-smoke-2026-09-28.md`.

Only the smoke assertion correction and documentation belong in this commit. Existing untracked `tmp/` PDF-review scratch files remain untouched; runtime data, configuration, credentials, screenshots, and generated frontend assets are excluded. Fetch succeeded despite permission warnings from Git's attempted cleanup of old worktree metadata; no destructive worktree cleanup was performed.
