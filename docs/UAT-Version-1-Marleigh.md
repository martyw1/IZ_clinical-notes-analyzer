# UAT Version 1 Marleigh

Use synthetic data only for this script.

Current patch version: `1.0.1` / build `2026.06.09.2`.

Version 1.0.1 adds a Windows startup reliability fix: the local launcher runs preflight once, validates the full Windows runtime dependency set, and should not show the old false dependency-check failure after packages were already installed.

1. Install the app with `Install-IZ-Clinical-Notes-Analyzer.cmd`.
2. Launch from the Start Menu shortcut.
3. Confirm the startup window does not report the old false dependency-check failure after preflight succeeds.
4. Sign in with the local admin account.
5. Open the Checklist tab.
6. Confirm the acronym definitions are understandable.
7. Confirm the LOC-change blocker says the timing window is unvalidated.
8. Open Chart audit.
9. Confirm the dashboard shows checklist version `v1.0.0`.
10. Confirm `/api/version` reports app version `1.0.1` after this patch is installed.
11. Confirm the Review source section shows EMR/API access and Manual upload.
12. Open Treatment plans.
13. Confirm mock/API readiness or synthetic treatment-plan items are visible when live API credentials are not configured.
14. Select a treatment-plan item.
15. Review rule results and evidence.
16. Add a manual override comment using synthetic text.
17. Export the treatment-plan report as CSV or JSON.
18. Open Manual upload.
19. Upload a synthetic supported file.
20. Confirm the app creates a review case.
21. Open Review queue.
22. Select the generated review.
23. Review findings, evidence, and checklist steps.
24. Add reviewer notes with synthetic text.
25. Export the review report as CSV or JSON.
26. Open Settings as admin.
27. Review API settings and SMART/FHIR discovery controls.
28. Run readiness checks.
29. Open Forensic logs.
30. Confirm sign-in, upload, review, override, and settings actions appear without secrets or uploaded note text.
31. Review `docs\admin-access-reset.md` and confirm the local admin recovery guidance is understandable for an authorized admin.
32. Close the browser and app window.
33. Relaunch and confirm prior review status is still present.
34. Use the uninstall shortcut only after confirming no local data needs to be preserved.
