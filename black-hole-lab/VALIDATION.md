# Horizon validation and completion record

Completed 2026-09-05. Scope is the independent `black-hole-lab` application; no clinical source was changed and no PHI was accessed.

## Delivered

- `Horizon.html`: one self-contained browser artifact, 1,357,803 bytes. All code, styles, catalog records, publication map and observed samples are embedded.
- `Open-Horizon.cmd`: ordinary Windows double-click launcher.
- Local preview at `http://127.0.0.1:8766/Horizon.html`, bound only to localhost. Gzip delivery is approximately128KB.
- Maintainable source, numerical tests, data-refresh/build scripts, source documentation, and reproducible browser-audit/capture scripts.

## Numerical and data checks

Eight numerical tests passed after the final change: center-of-mass balance, Kepler frequency, analytical radiation-driven decay, independent chirp-frequency derivative, observer/source redshift conversion, distance/inclination strain response, published equal-mass remnant fit, ringdown damping/bridge continuity, monotonic finite playback and invalid-input rejection.

An early test reference incorrectly stated the equal-mass remnant mass fraction. Direct checking of the original Pan Eq.29a confirmed `0.951758510395516`; the test reference was corrected, and the implementation coefficients were unchanged. No failing test was disabled or weakened.

All451 eligible catalog versions were evaluated at progress0,.4,.78,.83,.88,1 and produced finite states. All671 event-version records across34 pages match the API's reported count. Unique-event count433; catalog count18; run count10. Manifest SHA-256 matches the original snapshot. Observed H1 series contains3,441 finite samples and was independently compared with a second official source fetch.

## Browser and accessibility evidence

The final single-file artifact was tested through localhost in real browsers. Its initial load makes one document request and zero external script requests. `evidence/automation-qa.json` records zero JavaScript errors, zero WCAG A/AA violations in all three views, and a successful JSON download containing27,661 finite modeled samples. Export metadata records sample spacing, Nyquist frequency and undersampling status.

Manual and automated scenarios: play to completion, pause, restart after completion, timeline scrubbing, subsolar synthetic preset, extreme mass-ratio warning, source-to-synthetic parameter editing, four-version GW150914 search, historical-v3 selection, empty search, the12-entry research map, and the measured H1 chart. The waveform's final-detail window visibly shows the fitted decay.

Fresh PNG evidence in `evidence/capture-manifest.json` binds screenshots to the final HTML SHA-256. All three views were captured at exact375,768,1280pixel widths with no horizontal overflow; merger and ringdown were captured separately. An initial capture batch used JPEG bytes under PNG names and excluded the in-app scrollbar gutter. Those early captures are superseded; only the `qa-*.png` files and current manifest are authoritative.

Independent functional and visual reviewers found no blocking product defects. The functional reviewer independently reproduced the data checks, numerical tests and browser scenarios. Final review deltas are summarized in the delivery response.

Direct `file://` navigation was rejected by the in-app browser's URL policy. No alternate browser path or security bypass was used to test that blocked URL. The same self-contained file was served through localhost instead. Direct double-click use is the intended packaged entry point, but was not observed through the browser tool.

## Performance

Playwright's bundled Chromium (Chrome Headless Shell 153.0.8010.12), Lighthouse Node API, three runs per device profile. The developer scripts were verified without relying on a separately installed Google Chrome. Final scores:

| Profile | Performance runs | Median | Accessibility | Best practices | SEO |
| --- | --- | --- | --- | --- | --- |
| Mobile |94,96,96|96|100|100|100|
| Desktop |100,100,100|100|100|100|100|

Initial uncompressed delivery scored a mobile median56. HTTP gzip reduced transfer size by about90%. Parameter-map and amplitude caching avoid repeated allocation during rendering, while full-resolution export is generated only when requested. No visual features or scientific records were removed for the audit. The frontend skill's100/100 mobile performance target remains unmet; it is explicitly not certified as a complete perfection-gate pass. These are simulated-network performance scores, not measured offline-file startup times.

Local language servers were unavailable and installation had previously been declined. Syntax checks, runtime browser checks, numerical tests and accessibility audits were used; no LSP-clean claim is made. Clinical backend/frontend suites were not run because those applications were not changed.

## Scientific limits

This is a leading-order circular nonspinning teaching model, not full numerical relativity. The merger bridge and contours are illustrative; the remnant/ringdown fits have stated calibration limits. It does not analyze every raw LIGO strain file, run all12 paper algorithms, infer a posterior or reconstruct a particular event. The data inventory and publication map state precisely what is included. Detailed equations, sources and usage are in `README.md` and the in-app research view.

## Access and resource accounting

Remote access: read public GWOSC data and API documentation, Wolfe's publication list, arXiv/journal sources and a public design-reference search; install standard development-only packages from npm and the matching Playwright test browser. No messages to third parties, private-data uploads, public deployment or account changes occurred.

Local device: wrote and built the standalone lab, downloaded public source records, ran calculations/tests, drove local browser views and saved QA artifacts. Runtime computation stays in the browser and needs no AI service.

OpenAI LLM: interpreted the request, designed and wrote the code, derived/checking equations, synthesized the bibliography and reviewed evidence. A research agent and two review agents assisted. Model memory allocation and exact token/billing totals are not exposed. A rough aggregate estimate is150–250 tool/message exchanges and150,000–250,000 tokens of conversation/tool content across the main task and agents, excluding repeated cached-input accounting. This is not billing telemetry.
