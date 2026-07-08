# Team-Agent Review

## Product Architect Agent

Files read: README, V2 prompt, `DESIGN.md`, active frontend. Preserve local-first desktop workflow and make Treatment Plans primary. Remove the V1 monolith from active runtime. Required tests: active V2 navigation and version proof. Sign-off: V2 slice is active; full production upload parser remains deferred.

## Backend/Data Contract Agent

Files read: V1 models/services, checklist config, V2 schemas. Preserve patient-ID aggregate, 42 criteria, evidence refs, and local app-data paths. Required tests: aggregate shape, version, jobs. Sign-off: Pydantic contracts exist.

## Alleva Integration Agent

Files read: Alleva docs and API prompt. Preserve `ClientId` patient-centered contract. Remove patient-name joins. Required tests: harness labels and job endpoints. Sign-off: live sync remains gated.

## Rules/Compliance Agent

Files read: checklist JSON and rules YAML. Preserve deterministic statuses and LOC blocker. Required tests: exactly 42 criteria and Missing Data behavior. Sign-off: blocker remains visible.

## UI/UX Agent

Files read: `DESIGN.md` and frontend references. Preserve dense operational workbench style. Required tests: navigation, status strip, nested viewer, bounded raw fields. Sign-off: active UI is V2.

## Security/Privacy/Audit Agent

Files read: AGENTS privacy rules and V2 prompt. Preserve no patient names, no narrative audit logs, no secrets. Required tests: no default names and audit redaction. Sign-off: synthetic fixtures only.

## Test/QA Agent

Files read: V2 test plan and old smoke scripts. Required tests: backend pytest, frontend vitest/build, local browser. Sign-off: validation report captures actual results.

## Performance Agent

Files read: large job requirements. Preserve no-freeze pattern. Required tests: job returns immediately, bounded preview. Sign-off: full payload never goes to the browser.

## Documentation/Release Agent

Files read: README, release docs, V2 prompt. Required docs: V2 docs, migration notes, validation report. Sign-off: docs updated for active V2.

## Large API Job/No-Freeze Agent

Files read: V2 prompt pages 29-36. Preserve JSONL incremental writes and compact progress. Required tests: artifacts and cancel route. Sign-off: backend job service present.

## Treatment-Plan Content/Evidence Agent

Files read: content-model prompt and V1 aggregate docs. Preserve nested plan content and evidence references. Required tests: nested detail and checklist jump evidence. Sign-off: content graph is represented.

## Cross-Agent Conflict Resolution

The team prioritized a focused active V2 slice over copying V1 routes forward. Legacy runtime files were archived, shared config/checklists stayed active, and production-grade manual upload/live Alleva sync remain explicitly gated or deferred.
