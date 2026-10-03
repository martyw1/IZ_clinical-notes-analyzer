# Quick-start video completion record

## Full-administrator revision

- Verified all four numbered shortcut names and targets on the actual desktop without running tools against the user's normal app. Explained each tool within the startup, troubleshooting, and closing narrative.
- Captured 19 actual screen states with a synthetic administrator account in a separate marker-owned runtime. Covered all eleven administrator navigation tabs plus Account, with no invented administrator Corrections tab. No live vendor import was performed. The capture server was stopped afterward.
- Delivered a 6 minute 13 second administrator walkthrough with conversational Ava narration, actual screenshot crops, visible captions, selectable-caption alternative, SRT and transcript. Screenshot transitions are aligned to speech caption cues, with section breathing pauses.
- Complete video/audio decoding passed: no black interval of at least 0.5 seconds, audio average -19.9 dB and peak -1.8 dB. Inspected encoded frames for caption legibility and actual administrator controls. Naturalness remains a listener judgment.
- This revision changes training media and capture/render scripts only. Earlier frontend validation remains applicable; application tests were not repeated. Generic narration alone went to the speech service; screenshots and encoding stayed local.

## R3 name and actual-screen revision

- Updated browser sign-in, header, Help heading, recovery text, and tab title to **R3 Treatment Plan Audit Application**. Legacy storage identifiers and installed shortcut names remain stable; no installer or release metadata was changed.
- Captured 14 actual built-app screen states through Edge/Playwright against a separate marker-owned SQLite runtime with synthetic test records. The final capture uses an office-manager account, manual-source records, a real binder upload, selected patient TEST-PATIENT-001, real checklist evidence and permitted controls. Each owned server was stopped after capture. Capture guards reject an occupied port and wait for loading states to finish. Screenshot assets remain local.
- Rewrote narration for a completely nontechnical viewer: explained roster and MRN, removed setup/API/format discussion, described specific clicks and results, added simple empty-list, password and launch troubleshooting, retained conversational Ava delivery, and added a one-second breathing pause between sections.
- Delivered `R3-Treatment-Plan-Audit-Quick-Start.mp4`: 3 minutes 35 seconds, actual-screen crops and control highlights, 1280 x 720 at 30 fps, visible English captions. Also generated selectable-caption version, SRT, and revised transcript. Previous drafts remain available.
- Frontend build, all 184 unit tests, TypeScript checking, screenshot script syntax, and tracked diff whitespace check passed. Actual browser sign-in, roster navigation, upload, detail/checklist viewing, Help, sign-out, and password-help navigation were exercised. No backend code or clinical rule was changed; backend tests were not rerun for browser copy/media work.
- Final video/audio decode passed. No black interval of at least 0.5 seconds detected. Audio average -19.6 dB, peak -1.5 dB. Inspected actual encoded captioned frame and all nine section layouts. Perceived voice naturalness remains a listener judgment.

## Conversational revision

- Replaced the script with a friendly guided first-pass story, plain-language explanations, and light humor about technology. Preserved practical screen/button labels and review boundaries.
- Delivered `IZ-Quick-Start-Friendly.mp4`: 3 minutes 42 seconds, 1280 x 720, 30 fps, conversational Microsoft Ava neural narration, cream/teal/peach illustrated panels, progressive highlights, fades, and visible speech-timed captions. The selectable-subtitle MP4 and transcript were also regenerated.
- Inspected final encoded captioned frame and the longest list text for clipping; corrected the step font size. Complete final audio/video decoding succeeded. Audio measured -19.5 dB average and -1.6 dB peak, without clipping. Full-video black-frame detection found no black interval lasting 0.5 seconds or longer. Voice quality was not independently assessed by a human listener.
- Fixed a rendering issue: fading sparse still-image input before creating the constant frame rate held black frames or truncated short segments. A four-second reproduction produced 0.03 seconds without the `fps=30` prefilter and the full four seconds with it. Final encoded frame inspection confirms visible panels and captions. Intermediate reproduction files are retained in the ignored output folder as QA evidence.
- Only the generic non-patient script was sent to Microsoft's online speech service. Rendering, encoding, frame inspection, and file checks ran locally. The prior MP4 remains in the ignored output folder.

## Original version

- Delivered a 3 minute 54 second, 1280 x 720 MP4 with eight instructional cards, Microsoft Zira Desktop narration, embedded English subtitles, external SRT, transcript, and reproducible Windows build script.
- Verified wording against current operator help and V2 source labels. Avoided historical navigation, patient information, credentials, unsupported live-import claims, and final LOC-change deadline claims.
- Full encoded video/audio decode completed without errors. Inspected rendered upload card and overview of all cards for legibility and clipping. Subtitles use estimated sentence timing rather than word-level alignment.
- This is an introduction and narrated step-card guide, not a live screen recording. No live patient workflow was executed. Application code and release metadata were not changed; application tests were not run for this media-only addition.
- Media rendering and speech ran on the local Windows device. A public encoder dependency (`imageio-ffmpeg`) was downloaded from the package index; project content was not uploaded to a media service.

## Repository and desktop delivery

- Added the approved captioned MP4 under `docs/help`, with links from written operator help and the training README. Verified the committed copy matches the rendered original by SHA-256.
- Created `(5) Short Intro Video.lnk` on the current desktop, verified its target exists, and launched it through Windows file association. Windows Media Player started. The machine-specific shortcut is not tracked.
- Preserved unrelated `tmp/` files. Remote publication targets `origin/main`; no installer was rebuilt.
