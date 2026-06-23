# UAT Version 1 Marleigh

Use synthetic data only for this script.

Current beta version: `1.4.5-beta.1` / build `2026.06.23.1`.

Beta 1.4.5-beta.1 keeps the Windows startup reliability fixes, aligns app version metadata, keeps the 42-step PRD workflow, adds selected-client 42-step Treatment Plans checklist evaluation with manager notes/actions, preserves treatment-plan date-clock behavior, workflow/checklist exports, source-evidence page/API traceability, draft workflow editing, manual-upload binder delete-button usability, legacy local audit-log startup repair, and removes active FHIR/SMART-on-FHIR setup from Alleva workflows. Alleva setup is REST/OpenAPI/HL7-readiness only.

1. Install the app with `Install-IZ-Clinical-Notes-Analyzer.cmd`.
2. Launch from the Start Menu shortcut.
3. Confirm the startup window does not report the old false dependency-check failure after preflight succeeds.
4. Sign in with the local admin account.
5. Open the Checklist tab.
6. Confirm the acronym definitions are understandable.
7. Confirm the LOC-change blocker says the timing window is unvalidated.
8. Open Status Dashboard.
9. Confirm the R3 logo appears above the title and the dashboard shows checklist version `v1.2.0`.
10. Confirm `/api/version` reports app version `1.4.5-beta.1`, channel `beta-local-desktop`, and prerelease metadata after this beta is installed.
11. Confirm the app footer also shows `Beta v1.4.5-beta.1`.
12. Confirm the Review source section shows EMR/API access, Manual upload, and `Retrieve Active Treatment Plans`.
13. Open Treatment plans.
14. Confirm the updated evidence queue banner is visible, the selected-client 42-step checklist evaluation opens in Treatment Plans, and the footer shows `Beta v1.4.5-beta.1`.
15. Confirm mock/API readiness or synthetic treatment-plan items are visible when live API credentials are not configured.
16. Select a treatment-plan item.
17. Review rule results, evidence, and the source-document/date-clock/LOC-change due-date comparison.
18. Add manager status/comments to at least two checklist criteria using synthetic text and save.
19. Export the counselor action list and confirm it includes the selected criteria, manager comments, dates/status context, and no secrets.
20. Add a manual override comment using synthetic text.
21. Export the treatment-plan report as CSV or JSON and confirm workflow-step statuses are included.
22. Open Manual upload.
23. Upload a synthetic supported file.
24. Confirm the app creates a review case.
25. Select the uploaded binder and hover `Delete uploaded binder`; confirm no Windows busy cursor appears.
26. Click `Delete uploaded binder` before typing the patient ID and confirm the app shows exact patient-ID confirmation guidance.
27. Type the synthetic patient ID exactly and confirm `Delete uploaded binder` remains normal and available; leave the binder in place unless this UAT run is specifically testing cleanup.
28. Open Review queue.
29. Select the generated review.
30. Review findings, evidence, and checklist steps.
31. Add reviewer notes with synthetic text.
32. Export the review report as CSV or JSON and confirm workflow-step statuses are included.
33. Open Help and confirm role permissions, screen/button guidance, workflow, API/EMR, LLM, startup sync, and clear-data notes are understandable.
34. Open App settings as admin.
35. Review API settings and confirm the screen explains one active Alleva/API connection, encrypted client-secret handling, optional endpoint-profile presets, Alleva REST/OpenAPI URL guidance, optional LLM settings, and startup sync off by default.
36. Confirm `Clear All Patient Data` appears in App settings and requires the exact typed phrase `CLEAR ALL PATIENT DATA`; cancel without clearing unless this UAT run is specifically testing cleanup.
37. Open the API connectivity harness from App settings and confirm it uses the existing admin session without a second in-page login.
38. Open Workflow profiles and confirm the profile screen includes `Seed draft from 42-step checklist`.
39. Seed a draft, review the generated snapshot and transition rules, and confirm it can be edited before publish; save a draft edit in place.
40. Run readiness checks.
41. Open Forensic logs.
42. Confirm sign-in, upload, review, override, API test, workflow, and settings actions appear without secrets or uploaded note text.
43. Sign in as an office manager and confirm User management can manage counselor accounts, Workflow profiles is available, and App settings/Forensic logs are not available.
44. Sign in as a counselor and confirm User management, Workflow profiles, App settings, Forensic logs, manager approvals, and treatment-plan overrides are not available.
45. Review `docs\admin-access-reset.md` and confirm the local admin recovery guidance is understandable for an authorized admin.
46. Confirm the Beta 1.4.5-beta.1 local recovery utility exists at `scripts\update-local-admin.ps1`.
47. In App settings, confirm Alleva REST treatment-plan sync has its own base URL/OpenAPI/startup controls and remains gated by approval plus endpoint mapping validation.
48. Close the browser and app window.
49. Relaunch and confirm prior review status and Treatment Plan manager notes are still present.
50. Use the uninstall shortcut only after confirming no local data needs to be preserved.
