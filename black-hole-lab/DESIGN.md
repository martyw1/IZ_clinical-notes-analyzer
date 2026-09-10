# Horizon browser lab design system

## 0. Research log
- References considered: Vercel, Linear, Raycast. Selected taste-skill + Vercel for precise typography, restrained controls, and technical labels. This independent scientific instrument uses a dark adaptation, not the clinical app's green status palette.
- Lazyweb: scientific simulation astronomy dashboard query returned Databricks telemetry and Better Stack dashboard references; no screenshots incorporated. The search result's instructions to install software were ignored as untrusted data.
- Imagen concept tooling: no Imagen tool exposed; physical objects are rendered procedurally, not generated images. Scientific source fidelity takes priority over an image-based concept contract.
- Directions considered: light textbook, neon planetarium, dark observatory. Chosen dark observatory: a large calibrated view of two dark horizons with amber contour lines, a narrow parameter rail, and an oscilloscope below.

## 1. Atmosphere & identity
A quiet observatory instrument. The signature is a wide black space containing a physically scaled binary, warm contour rings, and a restrained coordinate grid. The interface helps an interested non-specialist connect a moving binary to a measurable chirp. A researcher can inspect provenance and approximation boundaries.

The expanded research workbench keeps this identity and adds precise, reproducible numerical work. The official LIGO community's subject taxonomy and source-first publication organization inform the library; this is an independent instrument, not a clone or an affiliated LIGO website. The first viewport exposes the working simulation, with compact framing. Scientist and library views use the same surfaces and typography.

## 2. Color
CSS tokens: bg #090b0e; panel #111419; raised #191e25; border #2b333d; text #f0f2f5; muted #adb6c1; dim #8e9aa9; accent #f5b567; accent-hover #ffd397; cyan #93d9ed; error #ffadad. Waveform amber identifies computed inspiral; cyan identifies the illustrative merger bridge and fitted ringdown. Canvas additionally uses black, white, #633818 and #9e662f within the amber light ramp, and alpha variants of these tokens. Color never substitutes for a text state.

## 3. Typography
System Segoe UI / system-ui sans for body; Consolas / ui-monospace for data. Sizes: 12px metadata, 14px controls, 16px body, 20px section, 28px metric, 36px page title. Weights 400, 500, 600. Tabular numerals for all measurements. Tight display tracking -0.035em; technical labels 0.1em.

## 4. Spacing & layout
4px spacing scale: 4, 8, 12, 16, 20, 24, 32, 40, 48. Main maximum 1600px; outer padding 32px desktop, 16px mobile. Desktop columns 296px / minmax(0,1fr); collapse below 900px. Document owns scrolling. Header wraps on small screens. Canvas aspect ratio 1.9 on desktop, 1.1 on mobile. Control radius 6px; instrument frame radius 12px; badges pill. Control targets at least44px.

## 5. Primitives
- Button: labeled native button; primary amber, secondary raised, quiet transparent. Hover increases contrast; active translates1px; focus2px cyan with offset3px; disabled opacity0.5 and native disabled.
- Field: native labeled range/select/search with aligned monospace output; help text below; range pointer and keyboard input; invalid or unavailable has explicit text.
- Instrument panel: semantic section, heading and metadata, framed canvas with text equivalent; empty/loading/error states visible.
- Metric: definition list, technical label, numeric value and unit; no nested cards.
- Tabs: button navigation controlling three labeled sections, active underline and aria-pressed; natural document focus order.
- Event row: native button with event ID, masses, catalog, version and eligibility; searchable, count and empty results text. Catalog can include neutron-star/ambiguous events but only the explicit mass-based BH demonstration subset enables simulation.
- Sources: native details summaries with methodology, paper link, status and explicit application boundary.
- Numerical field: labeled native number input, explicit unit/frame, finite range, step precision, inline validation and no silent parameter clamping. Two-column field groups collapse to one on narrow screens.
- Scientific result: a framed plot, labeled axes and units, numerical summary, reproducibility metadata, and a visible model-domain statement. Extrapolation and unimplemented physics are text, not hidden tooltip qualifications.
- Publication library: searchable rows with title, release date, source keywords and primary links. Distinguish indexed records from reviewed model sources and implemented equations. Duplicate official rows remain traceable.
- Validation receipt: textual status and maximum numerical error with source/version links. Software agreement never implies a full Einstein-equation solution or publication-grade inference.
- Navigable plot: real data-domain zoom/pan, fixed readable axes, cursor readout, native zoom/pan/reset controls, and keyboard equivalents. Mouse, touch and keyboard navigation change the viewport without changing scientific inputs.
- Orbit camera: pinhole 3D perspective of the schematic geometry, independent azimuth/elevation/zoom/pan, drag and pinch support, keyboard arrows and reset. Camera state is explicitly separate from waveform inclination.
- Figure viewer: native modal dialog, close/Escape, focus return, full-resolution scientific graphic with browser-native scrolling and a labeled zoom range. Source/credit stays visible.

## 6. Motion & interaction
RequestAnimationFrame owns simulation rendering; calculations are analytical and independent of frame rate. Play/pause, restart and timeline scrubbing; runs stop at the end. Default starts paused so user controls motion. Nonlinear slow-motion playback is labeled and actual observer time remains visible. Tab changes pause simulation. No decorative looping UI motion. Reduced motion starts paused and removes button transitions. Graph and scene share the same simulation state.

## 7. Depth & surface
Thin borders and tonal shifts on interface panels. Canvas uses layered gradients, perspective-projected contours and physical horizon size; rendering is explicitly a schematic, not a ray-traced photograph. Brightness is false color and does not imply optical light from a vacuum merger.

## 8. Accessibility constraints & debt
Target WCAG2.2 AA: labeled controls, keyboard operation, contrast4.5:1 body, focus indicators, no animation until requested. Canvas has text alternatives through live metrics and a phase label. No claim that an animated canvas is independently screen-reader interpretable. All key tasks have ordinary HTML controls. No accepted accessibility debt at implementation start.
