# Documentation and help alignment - 2026-09-08

Current app: `2.0.0-beta.3` / build `2026.09.03.1` / channel `beta-local-desktop-v2`.

## S0 - Scope and source checks

- Confirmed the root version files, frontend package metadata, backend configuration and visible app footer identify beta.3. Checklist content remains independently versioned at `1.2.0`.
- Classified active guidance separately from historical validation, V1 procedures and archived design evidence. Historical test versions remain intact with current-release pointers; they are not new beta.3 validation claims.
- Preserved existing untracked user work. No cleanup, credential access, clinical-data access, API configuration changes or live vendor calls were needed.

## S1 - Documentation and help changes

- Updated active version/build references and added current-release pointers to historical documentation. Obsolete V1 architecture and operator procedures explicitly direct readers to current V2 guidance.
- Updated the offline HTML guide's title, cover, download name, build, contents, Beta 3 changes, source filters, exact-plan selection, saved-version history, filtered exports, manual-processing guidance, session troubleshooting and release gates.
- Retained the guide's existing beta.2 directory so saved links remain valid. Its earlier screenshots are explicitly labeled historical Beta 2 illustrations in the text and captions.
- Expanded in-app Help with the current version/build and corresponding workflow, source-evidence, approval and support guidance using the existing design system.
- No version bump or prepared-installer rebuild is part of this source-checkout update.

## S2 - Verification

- Frontend: 175 tests passed across 26 files; TypeScript check and production build exited 0.
- Real installed Edge, headless: launched the built desktop app with a new isolated synthetic profile; completed first sign-in/password change, navigated to Help, inspected the current version/build and signed out.
- Offline guide: all 10 contents links target existing sections; all 10 screenshot images load. Captured every guide section and in-app Help at 1280, 768 and 390 pixels: 42 fresh captures, no document horizontal overflow and no browser page errors.
- Local browser evidence and a print export are in ignored `.omo/evidence/help-alignment-2026-09-08/`. Browser and owned local app process stopped after QA. The isolated synthetic data directory was not used for a release package.
- Initial independent visual reviews passed all 42 captures. Documentation review then corrected two label mismatches: Patient Roster uses Pull patient roster, and absent names display Name unavailable. The documentation re-review approved these corrections. Frontend tests/typecheck/build and all 42 browser captures were repeated successfully on the corrected source. A fresh final independent visual review inspected all 42 corrected captures and passed with no visual or functional-evidence blockers. All 96 tracked non-credential Markdown documents reference the current release; whitespace validation passed.
- Backend full-suite result is inconclusive: the first tool invocation timed out after two minutes (63 progress dots, no reported failures); the longer invocation failed at the tool boundary before returning a complete result. Both orphaned test process trees were stopped by their verified owned PIDs. No backend source was changed, and no full backend pass is claimed.

## Boundaries

The LOC-change preset remains configurable and unvalidated. Live Alleva authorization, credential remediation, signing and retention/legal-hold decisions remain external gates. Existing historical screenshots and prepared binaries were not recaptured or rebuilt as current release evidence.
