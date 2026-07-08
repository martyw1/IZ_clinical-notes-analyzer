# V1 Deprecation And Migration Plan

V1 contained a FastAPI runtime, a monolithic React `App.tsx`, deterministic rules, treatment-plan timeliness services, manual upload, API configuration/testing, audit logging, users, workflow profiles, Windows scripts, and extensive docs.

Active runtime files moved to `deprecated/v1/`:

- `backend/app/`
- `backend/tests/`
- `frontend/src/`
- `VERSION`
- `VERSION.json`

Reference-only root docs, shared requirements, root scripts, package files, Vite config, checklist config, rules config, and `.gitignore` remain active shared infrastructure.

V2 pulls forward the checklist/rules configuration, patient-ID privacy posture, local app-data paths, Windows launch/build expectations, treatment-plan workbench concepts, Alleva ClientId contract, and forensic logging goals. V2 rewrites active backend routes, schemas, services, frontend pages, job architecture, tests, and version metadata.

Tests prove V2 is active by checking `/api/version`, V2 navigation, V2 Treatment Plans Workbench rendering, and scans for active imports from `deprecated/v1/`.

Git history is preserved with `git mv` for the archived runtime paths.
