# Selected non-runtime folders archived — 2026-09-23

At the user's request, these working-tree folders were relocated to the local `not-required-for-deployment/selected-folders-2026-09-23/repo` archive:

- `video-extract (2026-06-05)` — historical design reference.
- `walkthroughs (2026-03-04)` — historical walkthrough material.
- `deprecated/v1` — inactive V1 source and tests.
- `depricated` — inactive legacy launchers and UI reference.
- `example-treatment-plans` — historical example documents excluded from deployment.
- `black-hole-lab` — separate astronomy teaching application, unrelated to the clinical runtime.
- `output/pdf` — reference PDFs and quick-start documentation; not a runtime dependency.

The specifically selected external QA directories `C:/Users/Public/IZ-CNA-QA-20260915` and `C:/iz-cna-final-a8262b5` were included in the same local archive under `external`.

S0 evidence: reference searches found no active backend, frontend, test or CI dependency on the selected repository folders. The Windows release builder explicitly excludes these folders and `output`. Current source and the production release ZIP remain in place. Historical documentation references describe the former locations; the files remain in the local archive and tracked historical versions remain in Git history.

The local archive contains `PLAN.json`, `S0-PREFLIGHT.json`, `FILE-MANIFEST.jsonl`, and `RESULTS.json`, with absolute original/destination paths. Readable files are verified using SHA-256 after relocation. Access-denied files are explicitly recorded and checked using available metadata; their content integrity cannot be independently confirmed. Application tests were not repeated because no active application code changed.
