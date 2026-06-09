# UAT Version 1 Marleigh

Use synthetic data only for this script.

Current patch version: `1.0.2` / build `2026.06.09.3`.

Version 1.0.2 keeps the Windows startup reliability fix, aligns app version metadata, and adds clear operator guidance for authorized local admin recovery.

1. Install the app with `Install-IZ-Clinical-Notes-Analyzer.cmd`.
2. Launch from the Start Menu shortcut.
3. Confirm the startup window does not report the old false dependency-check failure after preflight succeeds.
4. Sign in with the local admin account.
5. Open the Checklist tab.
6. Confirm the acronym definitions are understandable.
7. Confirm the LOC-change blocker says the timing window is unvalidated.
8. Open Chart audit.
9. Confirm the dashboard shows checklist version `v1.0.0`.
10. Confirm `/api/version` reports app version `1.0.2` after this patch is installed.
11. Confirm the app footer also shows version `1.0.2`.
12. Confirm the Review source section shows EMR/API access and Manual upload.
13. Open Treatment plans.
14. Confirm mock/API readiness or synthetic treatment-plan items are visible when live API credentials are not configured.
15. Select a treatment-plan item.
16. Review rule results and evidence.
17. Add a manual override comment using synthetic text.
18. Export the treatment-plan report as CSV or JSON.
19. Open Manual upload.
20. Upload a synthetic supported file.
21. Confirm the app creates a review case.
22. Open Review queue.
23. Select the generated review.
24. Review findings, evidence, and checklist steps.
25. Add reviewer notes with synthetic text.
26. Export the review report as CSV or JSON.
27. Open Settings as admin.
28. Review API settings and SMART/FHIR discovery controls.
29. Run readiness checks.
30. Open Forensic logs.
31. Confirm sign-in, upload, review, override, and settings actions appear without secrets or uploaded note text.
32. Review `docs\admin-access-reset.md` and confirm the local admin recovery guidance is understandable for an authorized admin.
33. Confirm the Version 1.0.2 local recovery utility exists at `scripts\update-local-admin.ps1`.
34. Close the browser and app window.
35. Relaunch and confirm prior review status is still present.
36. Use the uninstall shortcut only after confirming no local data needs to be preserved.
