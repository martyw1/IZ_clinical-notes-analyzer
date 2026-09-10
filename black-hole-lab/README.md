# Horizon: black-hole observatory

Open **Horizon.html** in a current browser, or double-click **Open-Horizon.cmd** on Windows. The 1.36 MB HTML file contains every runtime asset and needs no installation, server, login, API key, or internet connection. External source links require internet. The separate source files are provided for development.

## Using the lab

1. Choose an observed event. The default is the latest model-ready GW150914 version in the snapshot.
2. Press **Play merger**. Replay deliberately stretches the short final stages; the physical observer-time counter is separate.
3. Pause or scrub the timeline. Select **Merger detail** under Signal window to inspect the brief final waveform on a uniform physical time axis.
4. Change mass, distance or redshift to create a clearly labeled synthetic system. Inclination is an assumed viewing angle, including for observed presets. Camera rotation changes the view without changing the waveform's polarization convention.
5. Open **Event catalog** to inspect every retained version, uncertainties through each source record, SNR, FAR limits and catalog provenance. Entries without required parameters or with a component median below 3 solar masses remain searchable but are not offered as black-hole demonstration presets.
6. Open **Physics & research** for the equations, limitations, an observed GW150914 Hanford plot, and all 12 works on Noah E. Wolfe's public publication list with relevance notes.
7. **Export model data** downloads a JSON file of input parameters, selected source record, source/observer times, modeled plus/cross strain, frequency and stage. Separation is null after the analytical inspiral; the illustrated plunge is not exported as a measured orbit. Exports include sample spacing, Nyquist frequency and an undersampling flag for extreme scenarios that hit the browser-memory sample cap.

## Included data and reproducibility

Snapshot retrieved **2026-09-05 UTC** (September 4 in US Eastern time):

- 671 GWOSC event-version records, representing 433 named events, across all 34 API pages.
- 18 catalog indexes and 10 observing-run indexes.
- 451 versions satisfy this application's explicitly heuristic model-ready filter; the event selector favors the latest eligible version for each name. Versions are not duplicate detections.
- Original GWOSC parameter names, values, uncertainty bounds, units and limit flags are preserved in `data/gwosc-snapshot.json`. `data/manifest.json` records endpoints, counts, timestamp and SHA-256.
- 3,441 observed H1 samples from the official GW150914 Figure 1 dataset, at 16,384 Hz, including detector noise and the publisher's filtering. No local filtering/resampling was applied. `data/observed-gw150914.json` records source URL, units, processing and checksum.
- A researched inventory of the 12 works listed at https://noahewolfe.github.io/ . This is the scope of the publication review, not a guarantee of all collaboration contributions or unpublished research.

This does **not** contain or analyze all raw LIGO strain, all posterior samples, every data product, or execute all algorithms described in the papers. Catalog and run links provide entry points to the larger archive. Missing scientific parameters are not imputed to force an event into the model.

## Physics

The inspiral assumes circular point-mass Newtonian motion plus the leading quadrupole radiation flux. It is an educational approximation, not a precision event reconstruction or a numerical-relativity solver.

Define M=m1+m2, eta=m1*m2/M^2, x=r*c^2/(G*M). In source-frame geometric time T=t*c^3/(G*M):

```
x(T)^4 = x0^4 - (256/5)*eta*T
phi(x) - phi0 = (x0^(5/2) - x^(5/2)) / (32*eta)
Omega^2 = G*M/r^3
f_GW = Omega/pi
P_GW = (32/5)*(c^5/G)*eta^2/x^5
```

These are derived from Kepler's law, the quadrupole flux and energy balance; see [LVK, The basic physics of the binary black hole merger GW150914](https://arxiv.org/abs/1608.01940). Analytical evaluation makes orbital position independent of render rate.

Source-frame masses set horizon sizes and separation. Observer time is multiplied by 1+z, frequency is divided by 1+z, and luminosity-distance strain uses detector-frame masses. The modeled waveform is source h+/hx polarization, without a detector antenna pattern, noise, sky localization or observed coalescence phase. Catalog medians are separate marginal summaries, not a joint posterior sample. Distance and redshift are independent laboratory controls; no cosmological distance relation is enforced.

At x=6, the weak-field model switches to a continuous **illustrative** 30 GM/c^3 bridge. The cutoff is a test-particle Schwarzschild reference, not the true merger separation of a comparable-mass binary. Bridge separation, duration, amplitude and visual coalescence are not calibrated numerical-relativity predictions.

Remnant mass uses a physically consistent catalog final-mass median if provided; otherwise mass and spin use [Pan et al. (2011), Eq.29](https://arxiv.org/html/1106.1021). For equal masses, Mf/M=0.951758510395516 and chi_f=0.6870254037844386. The fit's numerical calibration covers mass ratios1,2,3,4,6; larger ratios are explicitly marked extrapolated. The total fitted radiated mass corresponds to inspiral from infinity, not just the displayed segment. Individual progenitor spins are fixed to zero; catalog chi_eff is displayed but is not applied to the motion or remnant spin.

Single-mode ringdown follows the Kerr220 fit in [Berti, Cardoso and Will, TableVIII](https://arxiv.org/abs/gr-qc/0512160): f220=[1.5251−1.1568(1−chi_f)^0.1292]/(2*pi*G*Mf_det/c^3), Q=.7000+1.4187(1−chi_f)^−.4990, tau=Q/(pi*f220). Mode excitation is illustrative. No higher modes or overtones are included.

The canvas is a schematic with relative physical horizon radii, projected coordinates, false-color halos and illustrative grid/ripple contours. It is not geodesic ray tracing or an exact spacetime embedding. The remnant circle uses a Kerr coordinate-radius proxy, not a ray-traced shadow diameter. No luminous matter or accretion disk is assumed.

## Development

Node.js is only needed to develop, refresh data or rebuild, not to use the packaged HTML.

```
npm test
npm run build
npm start
npm run refresh-data
```

For optional automated browser checks, install the locked development dependencies with `npm ci` and the matching test browser with `npx playwright install chromium`, then run `node scripts/audit.cjs` or `node scripts/capture.cjs` while the local server is running. They use Playwright's bundled Chromium and do not require a separate Chrome installation. They do not test blocked file URLs or change browser security settings.

The development server binds only to `127.0.0.1:8766`. Refresh retrieves the complete currently public event-version, catalog and run indexes, validates counts, then rewrites the snapshot. Run the build afterward. The measured H1 series and publication map are independently reviewed artifacts and are not automatically refreshed by this command.

Validation evidence lives in `evidence/`; see `VALIDATION.md`. No clinical application source or patient data was used or modified. No application runtime analytics, cookies, remote scripts or outbound background requests are included.

## Data attribution

This project uses data and services of the [Gravitational Wave Open Science Center](https://gwosc.org/), a service of LIGO Laboratory, the LIGO Scientific Collaboration, the Virgo Collaboration, and KAGRA. GWOSC data are released under [CC BY4.0](https://creativecommons.org/licenses/by/4.0/); follow [GWOSC acknowledgement guidance](https://gwosc.org/acknowledgement/). The measured GW150914 data are linked from [the official event page](https://gwosc.org/events/GW150914/), associated with [Abbott et al., Physical Review Letters116,061102](https://doi.org/10.1103/PhysRevLett.116.061102).

This independent educational application is not endorsed by MIT, Noah E. Wolfe, or the LVK collaborations.
