# UAT Version 1 Marleigh

Use synthetic data only for this script.

1. Install the app with `Install-IZ-Clinical-Notes-Analyzer.cmd`.
2. Launch from the Start Menu shortcut.
3. Sign in with the local admin account.
4. Open the Checklist tab.
5. Confirm the acronym definitions are understandable.
6. Confirm the LOC-change blocker says the timing window is unvalidated.
7. Open Chart audit.
8. Confirm the dashboard shows checklist version `v1.0.0`.
9. Confirm the Review source section shows EMR/API access and Manual upload.
10. Open Treatment plans.
11. Confirm mock/API readiness or synthetic treatment-plan items are visible when live API credentials are not configured.
12. Select a treatment-plan item.
13. Review rule results and evidence.
14. Add a manual override comment using synthetic text.
15. Export the treatment-plan report as CSV or JSON.
16. Open Manual upload.
17. Upload a synthetic supported file.
18. Confirm the app creates a review case.
19. Open Review queue.
20. Select the generated review.
21. Review findings, evidence, and checklist steps.
22. Add reviewer notes with synthetic text.
23. Export the review report as CSV or JSON.
24. Open Settings as admin.
25. Review API settings and SMART/FHIR discovery controls.
26. Run readiness checks.
27. Open Forensic logs.
28. Confirm sign-in, upload, review, override, and settings actions appear without secrets or uploaded note text.
29. Close the browser and app window.
30. Relaunch and confirm prior review status is still present.
31. Use the uninstall shortcut only after confirming no local data needs to be preserved.
