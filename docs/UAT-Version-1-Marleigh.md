# UAT Version 1 Marleigh

Use synthetic data only for this script.

Current patch version: `1.4.2` / build `2026.06.18.2`.

Version 1.4.2 keeps the Windows startup reliability fixes, aligns app version metadata, keeps the 42-step PRD workflow, adds treatment-plan date-clock behavior, workflow-step exports, source-evidence page/API traceability, draft workflow editing, clearer Alleva OpenAPI/FHIR setup guidance, separates gated Alleva REST treatment-plan sync from optional FHIR readiness, and fixes manual-upload binder delete-button usability.

1. Install the app with `Install-IZ-Clinical-Notes-Analyzer.cmd`.
2. Launch from the Start Menu shortcut.
3. Confirm the startup window does not report the old false dependency-check failure after preflight succeeds.
4. Sign in with the local admin account.
5. Open the Checklist tab.
6. Confirm the acronym definitions are understandable.
7. Confirm the LOC-change blocker says the timing window is unvalidated.
8. Open Chart audit.
9. Confirm the dashboard shows checklist version `v1.2.0`.
10. Confirm `/api/version` reports app version `1.4.2` after this patch is installed.
11. Confirm the app footer also shows version `1.4.2`.
12. Confirm the Review source section shows EMR/API access and Manual upload.
13. Open Treatment plans.
14. Confirm the updated evidence queue banner is visible and the footer shows `v1.4.2`.
15. Confirm mock/API readiness or synthetic treatment-plan items are visible when live API credentials are not configured.
16. Select a treatment-plan item.
17. Review rule results, evidence, and the source-document/date-clock/LOC-change due-date comparison.
18. Add a manual override comment using synthetic text.
19. Export the treatment-plan report as CSV or JSON and confirm workflow-step statuses are included.
20. Open Manual upload.
21. Upload a synthetic supported file.
22. Confirm the app creates a review case.
23. Select the uploaded binder and hover `Delete uploaded binder`; confirm no Windows busy cursor appears.
24. Click `Delete uploaded binder` before typing the patient ID and confirm the app shows exact patient-ID confirmation guidance.
25. Type the synthetic patient ID exactly and confirm `Delete uploaded binder` remains normal and available; leave the binder in place unless this UAT run is specifically testing cleanup.
26. Open Review queue.
27. Select the generated review.
28. Review findings, evidence, and checklist steps.
29. Add reviewer notes with synthetic text.
30. Export the review report as CSV or JSON and confirm workflow-step statuses are included.
31. Open Help and confirm role permissions, screen/button guidance, workflow, API/EMR, and LLM notes are understandable.
32. Open App settings as admin.
33. Review API settings, FHIR/OAuth discovery controls, stored EMR endpoint profiles, Alleva OpenAPI URL guidance, and optional LLM settings.
34. Open the API connectivity harness from App settings and confirm it uses the existing admin session without a second in-page login.
35. Open Workflow profiles and confirm the profile screen includes `Seed draft from 42-step checklist`.
36. Seed a draft, review the generated snapshot and transition rules, and confirm it can be edited before publish; save a draft edit in place.
37. Run readiness checks.
38. Open Forensic logs.
39. Confirm sign-in, upload, review, override, API test, workflow, and settings actions appear without secrets or uploaded note text.
40. Sign in as an office manager and confirm User management can manage counselor accounts, Workflow profiles is available, and App settings/Forensic logs are not available.
41. Sign in as a counselor and confirm User management, Workflow profiles, App settings, Forensic logs, manager approvals, and treatment-plan overrides are not available.
42. Review `docs\admin-access-reset.md` and confirm the local admin recovery guidance is understandable for an authorized admin.
43. Confirm the Version 1.4.2 local recovery utility exists at `scripts\update-local-admin.ps1`.
44. In App settings, confirm Alleva REST treatment-plan sync has its own base URL/OpenAPI/startup controls and can remain off without requiring a FHIR base URL.
45. Close the browser and app window.
46. Relaunch and confirm prior review status is still present.
47. Use the uninstall shortcut only after confirming no local data needs to be preserved.
