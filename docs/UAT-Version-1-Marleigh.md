# UAT Version 1 Marleigh

Use synthetic data only for this script.

Current patch version: `1.0.3` / build `2026.06.09.4`.

Version 1.0.3 keeps the Windows startup reliability fix, aligns app version metadata, adds clear operator guidance for authorized local admin recovery, and makes the updated Treatment Plan Timeliness evidence queue visible in the app.

1. Install the app with `Install-IZ-Clinical-Notes-Analyzer.cmd`.
2. Launch from the Start Menu shortcut.
3. Confirm the startup window does not report the old false dependency-check failure after preflight succeeds.
4. Sign in with the local admin account.
5. Open the Checklist tab.
6. Confirm the acronym definitions are understandable.
7. Confirm the LOC-change blocker says the timing window is unvalidated.
8. Open Chart audit.
9. Confirm the dashboard shows checklist version `v1.0.0`.
10. Confirm `/api/version` reports app version `1.0.3` after this patch is installed.
11. Confirm the app footer also shows version `1.0.3`.
12. Confirm the Review source section shows EMR/API access and Manual upload.
13. Open Treatment plans.
14. Confirm the `Updated evidence queue v1.0.3` banner is visible.
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
30. Run readiness checks.
31. Open Forensic logs.
32. Confirm sign-in, upload, review, override, and settings actions appear without secrets or uploaded note text.
33. Review `docs\admin-access-reset.md` and confirm the local admin recovery guidance is understandable for an authorized admin.
34. Confirm the Version 1.0.3 local recovery utility exists at `scripts\update-local-admin.ps1`.
35. Close the browser and app window.
36. Relaunch and confirm prior review status is still present.
37. Use the uninstall shortcut only after confirming no local data needs to be preserved.
