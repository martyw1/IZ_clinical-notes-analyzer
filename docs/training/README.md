# Short introduction and help video

Open **R3-Treatment-Plan-Audit-Quick-Start.mp4** in a video player. It runs 6 minutes 13 seconds and uses the new product name, actual app screenshots with synthetic example records, highlighted controls, conversational Microsoft Ava narration, and visible English captions. **R3-Treatment-Plan-Audit-Quick-Start-selectable-captions.mp4** contains the same revised narration and visuals with selectable subtitles instead. The adjacent `.srt` and transcript provide accessible alternatives.

The guide assumes no technical knowledge and full application administrator access. It explains every administrator tab and when to use it: Status Dashboard, Patient Roster, Patient Record Detail, Treatment Plans Roster, Treatment Plan Detail, Manual Upload, Users, Settings, API Testing Harness, Forensic Logs, and Help, plus Account at the top right. It includes checklist review actions, upload warnings, approved connection/pull boundaries, password recovery, and ordinary troubleshooting. Screenshot changes follow the spoken steps. The 19 screenshots are captured from the actual built app and local backend with synthetic records. No real patient records, passwords, recovery codes, or connection credentials are shown.

The desktop tools retain their existing names:

- **(1) Start IZ Clinical Notes Analyzer** opens the app so you can sign in.
- **(2) Stop IZ Clinical Notes Analyzer** stops the app and offers a restart prompt; signing out alone does not stop it.
- **(3) Collect IZ Diagnostics** creates a support report to send through R3's approved support channel when requested.
- **(4) Quick Assist - R3 Support** opens Windows assisted support; review access requests with a trusted R3 support person.

Content was checked against `docs/operator-help-current.md`, the current Help page, Manual Upload page, and Treatment Plan Detail page on October 3, 2026. Actions and navigation vary by role. Live imports remain conditional on approval and configuration; LOC-change policy remains unresolved.

For support staff regenerating media: run `capture-training-screens.ps1` after a frontend build, then `build-quick-start-video.ps1 -Ffmpeg <full path to ffmpeg.exe>`. Capture uses the existing synthetic seed and an isolated backend on port 8767, and stops its own server afterward. Rendering requires Python with `edge-tts`, FFmpeg with subtitle support, and Windows System.Drawing. Only the generic script is sent to the online speech service; screenshots stay on the device. Narration is reused when its script and voice settings match. Intermediate media and historical video drafts are ignored by Git. The approved captioned video is committed under `docs/help/R3-Treatment-Plan-Audit-Quick-Start.mp4`.

The current browser-facing name is R3 Treatment Plan Audit Application. Existing installed shortcuts and local storage identifiers keep their legacy names; a new installer has not been built. The tutorial names each of the four actual numbered desktop shortcuts and explains its purpose. Earlier videos remain as historical drafts. This work does not qualify a release or change clinical rules.

The repository help entry is [docs/help](../help/README.md); the desktop shortcut **(5) Short Intro Video** points to that committed MP4.
