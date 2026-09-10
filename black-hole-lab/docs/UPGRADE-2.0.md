# Horizon 2.0: scientific workspace and Sites edition

The expanded application retains the GWOSC event snapshot, observed GW150914 Hanford series, and twelve-paper Noah E. Wolfe map. It adds every one of the 310 records in the official public LVK publication table as retrieved September 5, 2026, a higher-order animated inspiral, an independent frequency-domain scientist workspace, and private Sites hosting.

## Research coverage

[Official publication table](https://pnp.ligo.org/ppcomm/Papers.html) and [BibTeX](https://pnp.ligo.org/ppcomm/LVC_Papers.bib) each contain 310 records. Dates span 2003-08-14 through 2026-08-24. There are 306 distinct BibTeX keys; repeated revisions and companion records are retained. These are index records, not 310 unique experiments. `data/publications.json` preserves all table rows, titles, bylines, source keywords, release dates, journal strings and primary links. Original topic tags overlap and are incomplete; search titles to find topics such as populations and cosmology that often carry only a CBC tag.

This is complete coverage of that public table, not all restricted DCC material, unpublished studies, every independently authored LIGO-related paper, or a claim that every indexed paper has been fully read or implemented. The library explicitly says indexed-only. The mathematical source notes identify the narrower set of implemented equations.

The new Wolfe figure is Figure 2 of [arXiv:2305.19907v2](https://arxiv.org/html/2305.19907v2#S3.F2), CC BY 4.0, credited to Noah E. Wolfe, Salvatore Vitale and Colm Talbot (2023). The original PDF was rendered to PNG without altering scientific content. Its caption identifies simulated O4-design-sensitivity forecasts and explicitly distinguishes them from detections and current simulator output. The original LIGO site informs subject organization and source-focused presentation; no official logo or affiliation is claimed.

## Implemented physics

- Animated inspiral: selectable nonspinning TaylorT4 through 3.5PN, or original Newtonian/quadrupole radiation reaction. A cumulative composite-Simpson integral with 4,096 intervals calculates time and orbital phase as functions of velocity. Cubic Hermite interpolation inverts the monotonic time grid. Source masses set physical horizon radii; detector mass-time includes redshift.
- The displayed orbit uses `r_proxy = GM/(c²v²)`, a frequency-derived Newtonian-equivalent separation. It is not a PN coordinate separation or relativistic proper distance.
- The same explicitly illustrative merger bridge and calibrated nonspinning remnant/ringdown fits remain separate. No scientific Fourier export includes that bridge.
- Scientist waveform: nonspinning TaylorF2 phase at 0, 1, 1.5, 2, 2.5, 3 or 3.5PN, restricted leading-order amplitude and a test-particle Schwarzschild ISCO reference cutoff. This cutoff is a convention, not a proven accuracy boundary for comparable masses.
- Ideal detector: long-wavelength right-angle antenna factors in a declared local frame. No real Hanford/Livingston geographic tensor, celestial coordinates, sidereal time, calibration or arrival-time triangulation is implied.
- Noise: an explicitly synthetic constant one-sided PSD, equal to the entered ASD squared. SNR uses `sqrt(4 Δf Σ |hdet|² / PSD)` on the selected positive-frequency grid. Overlap against the 0PN reference maximizes over a constant phase only, not arrival time or intrinsic parameters.

Coefficients and conventions are pinned to LALSuite commit `c54be3dd1be3c9effedc83f0dda55a0d9fa1f34c`. Full equations, source links, fixture transformation and limitations are in `docs/physics-reference.md`.

## Scientist controls and outputs

Numeric fields expose mass frame, both masses, independent redshift and luminosity distance, inclination, PN phase order, lower/upper frequency, frequency spacing, reference frequency, orbital reference phase, time shift, detector-local angles and white-noise ASD. Spins, precession, eccentricity and tides remain explicitly zero/absent rather than appearing as ineffective controls.

Frequency bins are exact multiples of Δf, starting at `ceil(fmin/Δf)` and ending at `floor(min(fmax,fISCO)/Δf)`. Fewer than two or more than 65,536 bins produces an error; no hidden resampling occurs. Edits disable export until the waveform is recalculated. Invalid input clears current results and keeps exports disabled.

CSV exports include frequency, real/imaginary h+/h×, projected detector strain and the unwrapped phase argument. Fourier strain units are seconds (strain/Hz), not ASD or time-domain strain. The companion JSON records all inputs, actual band, source/detector masses, constants, Fourier sign, polarization convention, reference-phase convention, noise assumption, source commit, software version and the current self-check receipt. Save both files for a reproducible experiment.

## Validation meaning

Sixteen numerical tests cover the original equations and the new approximants, physical scalings, mass-frame equivalence, detector nulls, frequency grid/cutoff, invalid input and extreme-parameter behavior.

Independent reference comparisons use 12 source-extracted coefficient points, 12 trajectories integrated independently with 16,384 intervals and convergence checks, and 477 nonzero complex waveform bins derived from an official stored LALSuite test vector. Both polarizations agree to approximately 4.83e-11 maximum complex relative error; trajectory relative error is approximately 1.36e-13. The in-browser self-check repeats these comparisons with explicit tolerances.

The original stored waveform includes known tidal phase and older solar-mass constants. The regression fixture removes exactly that tidal phase and translates masses to preserve SI mass-times. It is clearly marked as a transformed stored regression fixture, not fresh native LALSuite execution. The original untransformed subset and provenance are retained in `data/references/`. This verifies implementation agreement within the approximation; it does not establish full-GR physical accuracy, parameter-estimation quality, or merger fidelity.

## Packaging and access

`npm test` runs numerical checks. `npm run build` prepares both the self-contained `Horizon.html` and an explicit static allowlist in `dist/`. Only that static output is deployed. Developer dependencies, tests, local evidence, source credentials and the clinical repository are excluded from the deployment archive.

The Site is published privately to its owner. Open the final hosted link in a browser and use the same account that owns this Codex/Sites project if a sign-in screen appears. No local server is needed for the hosted Site. The packaged standalone HTML retains an offline option; hosted access itself requires internet and the Site's access policy.
