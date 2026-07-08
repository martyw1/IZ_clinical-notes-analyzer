# V2 Test Plan

Automated checks:

- Backend V2 runtime tests verify version metadata, readiness, navigation, 42 criterion aggregate, manager override reason enforcement, redacted API configuration/sample OpenAPI contract, `ClientId` pull-definition flow, and large job lifecycle artifacts.
- Frontend tests verify login, V2 navigation, Treatment Plans status order, patient-ID-only rendering, nested detail sections, override reason enforcement, and large job bounded artifacts.
- Import scans verify active code does not import from `deprecated/v1/`.
- Windows scripts verify preflight, local app stack, API configuration harness, bounded Pull ALL job preview/artifacts, and release package forbidden-file scans.

Manual QA:

- Run the local app at `http://localhost:8000`.
- Sign in as admin.
- Open Treatment Plans and verify the V2 workbench, detail viewer, checklist evidence, Raw Field Explorer, and no patient names.
- Open API Testing Harness and start a synthetic large job.
- Verify the browser remains responsive and no full payload is rendered.
- Use Computer Use or equivalent desktop capture for a real Windows screenshot pass on Dashboard, Treatment Plans, and API Testing Harness before release sign-off.

Current validation evidence is recorded in `validation-report.md`; task-list coverage is recorded in `task-coverage-audit.md`.
