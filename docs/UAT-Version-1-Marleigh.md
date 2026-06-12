# UAT Version 1 Marleigh

Use synthetic data only for this script.

Current patch version: `1.1.1` / build `2026.06.12.1`.

Version 1.1.1 keeps the Windows startup reliability fix, aligns app version metadata, keeps the 42-step PRD workflow, and adds deployment-readiness hardening for redacted uploads, timezone-aware logs, button-event logging, safe daily source checks, and API client-credentials testing.

1. Install the app with `Install-IZ-Clinical-Notes-Analyzer.cmd`.
2. Launch from the Start Menu shortcut.
3. Confirm the startup window does not report the old false dependency-check failure after preflight succeeds.
4. Sign in with the local admin account.
5. Open the Checklist tab.
6. Confirm the acronym definitions are understandable.
7. Confirm the LOC-change blocker says the timing window is unvalidated.
8. Open Chart audit.
9. Confirm the dashboard shows checklist version `v1.1.0`.
10. Confirm `/api/version` reports app version `1.1.1` after this patch is installed.
11. Confirm the app footer also shows version `1.1.1`.
12. Confirm the Review source section shows EMR/API access and Manual upload.
13. Open Treatment plans.
14. Confirm the `Updated evidence queue v1.1.1` banner is visible.
15. Confirm mock/API readiness or synthetic treatment-plan items are visible when live API credentials are not configured.
16. Select a treatment-plan item.
17. Review rule results, evidence, and the source/staff/LOC due-date comparison.
18. Add a manual override comment using synthetic text.
19. Export the treatment-plan report as CSV or JSON.
20. Open Manual upload.
21. Upload a synthetic supported file.
22. Confirm the app creates a review case.
23. Open Review queue.
24. Select the generated review.
25. Review findings, evidence, and checklist steps.
26. Add reviewer notes with synthetic text.
27. Export the review report as CSV or JSON.
28. Open Settings as admin.
29. Review API settings and SMART/FHIR discovery controls.
30. Confirm the workflow profile panel includes `Seed draft from 42-step checklist`.
31. Seed a draft, review the generated snapshot and transition rules, and confirm it can be edited before publish.
32. Run readiness checks.
33. Open Forensic logs.
34. Confirm sign-in, upload, review, override, API test, and settings actions appear without secrets or uploaded note text.
35. Review `docs\admin-access-reset.md` and confirm the local admin recovery guidance is understandable for an authorized admin.
36. Confirm the Version 1.1.1 local recovery utility exists at `scripts\update-local-admin.ps1`.
37. Close the browser and app window.
38. Relaunch and confirm prior review status is still present.
39. Use the uninstall shortcut only after confirming no local data needs to be preserved.
