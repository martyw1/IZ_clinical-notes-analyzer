# Loom Video Extraction: Treatment Plan Timelines

Source: `https://www.loom.com/share/bb01b72bdebf4585bed02e456c43b0e7`

Presenter: Marleigh Johnson.

Video title: `Treatment plan timelines`

Duration: 255.466 seconds.

Extraction date: 2026-06-05.

## Safety Note

The screen recording shows identifiable client chart content inside Alleva. Raw captures and the downloaded source video are kept locally for review only and are ignored by `video-extract/.gitignore`. Do not commit raw frames, the MP4, captions, or transcript JSON unless the data is redacted and approved.

The written artifacts below use synthetic labels and avoid reproducing client identifiers.

## What Was Extracted

- Full Loom transcript/captions from the video metadata.
- Full HLS source video downloaded locally for frame review.
- Timestamped still frames at every transcript phrase boundary.
- A 15-second contact sheet for visual flow review.
- Visual style notes for the Alleva-inspired operational UI.
- The verification process Marleigh demonstrates and discusses.
- Logic artifacts for the Treatment Plan Timeliness Tracker.
- React/CSS reference code using synthetic data only, now quarantined under `depricated/` because it is historical reference code and not active app source.

## Artifact Index

- `transcript-timestamped.md`: full timestamped caption phrases.
- `verification-steps.md`: presenter workflow converted to a verification checklist.
- `clinical-logic-spec.md`: rules, data fields, open questions, and implementation notes.
- `visual-style-guide.md`: UI style and interaction details observed from the video.
- `ui-flow-storyboard.md`: timestamp-to-screen storyboard with capture references.
- `extraction-log.md`: source acquisition log and known limitations.
- `../depricated/video-extract (2026-06-05)/frontend-reference/TreatmentPlanTimelinessVideoMockup.tsx`: deprecated React reference component.
- `../depricated/video-extract (2026-06-05)/frontend-reference/treatment-plan-timeliness-video.css`: deprecated CSS reference styling.
- `../depricated/video-extract (2026-06-05)/frontend-reference/mockup-data.json`: deprecated synthetic sample payload for the mockup.

## Raw Local Assets

Ignored local-only assets were created under:

- `reference-assets/source-video.mp4`
- `reference-assets/transcript.json`
- `reference-assets/captions.vtt`
- `reference-assets/loom-apollo-metadata.json`
- `captures/contact-sheet-15s.jpg`
- `captures/phrase-*.png`
- `captures/time-*.png`

These files are useful for local reinspection, but the app logic should be built from the written artifacts and synthetic fixtures.
