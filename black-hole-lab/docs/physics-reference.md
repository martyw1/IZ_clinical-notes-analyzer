# TaylorF2 and TaylorT4 scientific verification

Research date: 2026-09-05. Project and Site checkout were read-only for this task. All artifacts are in this research directory.

## Verified implementation outcome

Read-only evaluation of `black-hole-lab/scientific.js` (SHA256 DE72703D445A07E0386D4290A75F2B4923AFFE6E47808C577B554B1A2FB153BA):

- 477 nonzero transformed official-reference bins: maximum relative complex error 4.83056e-11 for plus and 4.83056e-11 for cross.
- 12 source-extracted coefficient points: maximum F2 intrinsic-phase absolute error 1.14e-13 rad; maximum T4 correction absolute error 4.44e-16.
- 12 trajectory integrations (eta=.25,.16,10/121 and start proxy=12,20,30,50 to 6): maximum relative duration error 1.36e-13 and orbital-phase error 2.76e-14 versus source-extracted coefficients with independent composite Simpson16384 quadrature.
- F2 negative restricted amplitude, complex-exponent sign, factor2 on orbital reference phase, and cross=-i cos(inclination)*base waveform are correct.
- All F2 and T4 nonspinning coefficients in scientific.js match the pinned source.

These establish implementation/regression agreement, not physical accuracy against numerical relativity.

## Exact nonspinning TaylorF2 equations

Use detector-frame masses, M=m1+m2, eta=m1*m2/M^2, Mc=M*eta^(3/5), M_sec=M*MTSUN, and v=(pi*M_sec*f)^(1/3). The frequency is the dominant quadrupole GW frequency, twice orbital frequency. f is positive and measured in Hz. Logarithms below are natural.

Define the intrinsic phase Q(v)=3/(128*eta*v^5)*[1+a2*v^2+a3*v^3+a4*v^4+a5(v)*v^5+a6(v)*v^6+a7*v^7].

- a2 = 3715/756 + 55*eta/9
- a3 = -16*pi
- a4 = 15293365/508032 + 27145*eta/504 + 3085*eta^2/72
- a5(v) = pi*(38645/756 - 65*eta/9)*(1+3*ln(v))
- a6(v) = 11583231236531/4694215680 - 640*pi^2/3 - 6848*gamma_E/21 + (-15737765635/3048192 + 2255*pi^2/12)*eta + 76055*eta^2/1728 - 127825*eta^3/1296 - 6848*ln(4*v)/21
- a7 = pi*(77096675/254016 + 378515*eta/1512 - 74045*eta^2/756)
- gamma_E = 0.577215664901532860606512090082402431

For order selection retain powers through n=0,2,3,4,5,6,7 for Newtonian,1PN,1.5PN,2PN,2.5PN,3PN,3.5PN respectively. A coefficient named `6PNCoeff` in this LAL source denotes the power of v; it is 3PN, not 6PN physical order.

The positive restricted amplitude is A(f)=sqrt(5/24)*pi^(-2/3)*(Mc*MTSUN)^(5/6)/(dL/c)*f^(-7/6). Units are strain*seconds (strain/Hz), not time-domain strain or amplitude spectral density.

To match LAL conventions exactly, the base waveform is H(f)=-A(f)*exp{-i[Q(v)-Q_ref-2*phi_ref+2*pi*f*t_c-pi/4]}. phi_ref is an ORBITAL phase in radians. Set Q_ref=0 if f_ref=0; otherwise Q_ref=Q((pi*M_sec*f_ref)^(1/3)). The f_ref=0 choice is the LAL coalescence convention. Do not literally evaluate the truncated logarithmic series at f=infinity.

Polarizations: h_plus=(1+cos(iota)^2)/2*H and h_cross=-i*cos(iota)*H. This sign is confirmed against BOTH original stored complex polarizations. Detector strain is F_plus*h_plus+F_cross*h_cross. Fourier convention is integral h(t)*exp(-2*pi*i*f*t) dt, so a positive physical time delay multiplies the Fourier strain by exp(-2*pi*i*f*delay).

LAL's uniform array starts at f0=0, length floor(f_end/df)+1, and fills from ceil(f_min/df). Its epoch is -1/df, with a corresponding linear phase; for exact grid frequencies that phase is an integer multiple of2pi, apart from GPS nanosecond rounding. A browser may export only the nonzero band if metadata records f0 and df explicitly.

Source: [LAL F2 core](https://git.ligo.org/lscsoft/lalsuite/-/blob/c54be3dd1be3c9effedc83f0dda55a0d9fa1f34c/lalsimulation/lib/LALSimInspiralTaylorF2.c#L148-482), especially340,344-384,475-482. [Coefficient expressions](https://git.ligo.org/lscsoft/lalsuite/-/blob/c54be3dd1be3c9effedc83f0dda55a0d9fa1f34c/lalsimulation/lib/LALSimInspiralPNCoefficients.c#L688-748), normalization970-983. [Polarization construction](https://git.ligo.org/lscsoft/lalsuite/-/blob/c54be3dd1be3c9effedc83f0dda55a0d9fa1f34c/lalsimulation/lib/LALSimInspiral.c#L6320-6343). Primary equation derivation: [Buonanno et al 2009, Eq3.18](https://arxiv.org/abs/0907.0700).

## Exact nonspinning TaylorT4 equations

Let tau=t/M_sec. dv/dtau=(32*eta/5)*v^9*B(v), and dphi_orb/dtau=v^3.

B(v)=1+b2*v^2+b3*v^3+b4*v^4+b5*v^5+b6(v)*v^6+b7*v^7, with:

- b2 = -743/336 - 11*eta/4
- b3 = 4*pi
- b4 = 34103/18144 + 13661*eta/2016 + 59*eta^2/18
- b5 = -pi*(4159/672 + 189*eta/8)
- b6(v) = 16447322263/139708800 - 1712*gamma_E/105 - 56198689*eta/217728 + pi^2*(16/3+451*eta/48) + 541*eta^2/896 - 5605*eta^3/2592 - 856*ln(16*v^2)/105
- b7 = pi*(-13245+717350*eta+731960*eta^2)/12096

Equivalent split logarithm: b6_constant includes -856*ln(16)/105 and the coefficient of ln(v) is -1712/105. LAL's leading `wdot` helper returns96*eta/5; divide by3*M_sec for dv/dt.

Integrate dt/dv=5*M_sec/(32*eta*v^9*B(v)) and dphi_orb/dv=5/(32*eta*v^6*B(v)) from v0=1/sqrt(start_proxy) to1/sqrt6. Positive B permits monotonic time inversion. GW phase is2*phi_orb. `x=1/v^2` should be labeled a frequency-derived Newtonian separation proxy, not the PN coordinate separation.

Independent source-derived test: eta=.25,v=.3 gives B=1.1137311997919825 and dv/dtau=3.507451392880894e-5. eta=.25,start_proxy20 to6 gives duration/M_sec=11937.310066261301 and orbital phase199.61718321548008rad. Full12points and12integrals are `pn-source-fixtures.json`; `verify-pn-source.ps1` extracts authoritative C expressions, converts only syntax for the .NET compiler, and runs an independent quadrature. It does not call the application under test or require a scientific server.

Sources: [coefficient definitions](https://git.ligo.org/lscsoft/lalsuite/-/blob/c54be3dd1be3c9effedc83f0dda55a0d9fa1f34c/lalsimulation/lib/LALSimInspiralPNCoefficients.c#L1802-2129), and [TaylorT4 evaluator](https://git.ligo.org/lscsoft/lalsuite/-/blob/c54be3dd1be3c9effedc83f0dda55a0d9fa1f34c/lalsimulation/lib/LALSimInspiralTaylorT4.c#L251-349). Physical formula is Eq3.6 of Buonanno et al. The helper section has an UNREVIEWED comment covering that collection including spin terms; this report verifies the nonspin equations against the paper/source and computations rather than implying all helpers have a formal review status.

## Regression fixture provenance

- `reviewed_waveforms-full.asc`: unmodified official file, SHA256 f5da128fa6baa82a90320f58b0628f074b14cfa9d8537f1d2f40109620a987ac, [download](https://git.ligo.org/lscsoft/lalsuite/-/raw/c54be3dd1be3c9effedc83f0dda55a0d9fa1f34c/lalsimulation/test/reviewed_waveforms.asc).
- `taylorf2-reviewed-nonspin-tidal.ini`: complete ORIGINAL481-bin nonspinning tidal block, unchanged numerical arrays.
- `taylorf2-original-reference-subset.json`: UNTRANSFORMED7-frequency subset with original parameters, historical constants, exact raw complex plus/cross, and provenance.
- `taylorf2-nonspin-independent-reference.json`: TRANSFORMED REGRESSION FIXTURE, not a fresh native LAL execution.477nonzero points plus4zero bins. Known tidal phase removed analytically; modern masses adjusted to preserve physical mass-times. Reproduce with `export-nonspin-reference.ps1`.

Original vector: masses1.4+1.4solar, distance50Mpc, inclination.3rad, orbital phase0, f_ref0, f_min10Hz,f_max1200Hz,df2.5Hz, spins0, lambda1=90.5,lambda2=112. The block's generator SHA says `to be inserted`; do not invent it. Historical MTSUN=4.925491025543575903411922162094833998e-6 is verified at [archive constants](https://github.com/lscsoft/lalsuite-archive/blob/af88bb786eb62dcf73e4c926c1391cdbc3aef7c4/lal/src/std/LALConstants.h#L449-513). The currently used MTSUN=4.925490947641266978197229498498379006e-6 is [current constants](https://git.ligo.org/lscsoft/lalsuite/-/blob/c54be3dd1be3c9effedc83f0dda55a0d9fa1f34c/lal/lib/std/LALConstants.h#L589-605). Using modern constants with the unadjusted historical masses causes a real~0.001rad low-frequency mismatch.

The original vector matches nonspin3.5PN plus5PN/6PN tidal phase with maximum relative complex error4.828947378008616e-11 across477nonzero bins. This is recorded by `compare-reviewed-vector.ps1` and `reviewed-vector-comparison.json`; orders absent from raw metadata are inferred from this successful comparison.

Q_tidal=3/(128*eta)*sum_i lambda_i*[C10(X_i)*v^5+C12(X_i)*v^7], X_i=m_i/M, C10=(-288+264X)*X^4, C12=(-15895/28+4595X/28+5715X^2/14-325X^3/7)*X^4. Transform h_nonspin=h_original*exp(+i*Q_tidal). Current-constant equivalent component masses each1.4000000221426114solar. Both polarizations preserve their original independent values through the same phase rotation. Those tide terms exist only in the validation transform; no tide physics needs to be added to the browser's scientific model.

## Detector convention and limits

The current scientific.js local antenna formula is internally usable for an ideal90degree long-wavelength interferometer. It is not directly LAL RA/declination input. Algebraically it maps to PyCBC `overhead_antenna_pattern` with RA=phi+pi/2, dec=pi/2-theta, polarization=-psi. This mapping is an inference from exact formulas in [PyCBC primary source](https://pycbc.org/pycbc/latest/html/_modules/pycbc/detector/ground.html#overhead_antenna_pattern). For real named detectors, use documented geographic tensors, sidereal time, sky coordinates, time delays, and consistent polarization basis as in [LAL DetResponse](https://git.ligo.org/lscsoft/lalsuite/-/blob/c54be3dd1be3c9effedc83f0dda55a0d9fa1f34c/lal/lib/tools/DetResponse.c#L31-99).

TaylorF2 and TaylorT4 are separate PN approximants; their differences start beyond the retained PN truncation and need not coincide near the cutoff. Neither is a merger/ringdown or numerical-relativity simulation. Both here assume nonspinning, quasicircular point masses, leading quadrupole amplitude, no tides, eccentricity, higher harmonics, precession, or lensing. The f_ISCO=1/(6^(3/2)*pi*M_sec) cutoff is a Schwarzschild test-particle convention, not a guaranteed accuracy boundary for comparable-mass binaries. A user may choose an earlier cutoff; never call below-ISCO automatically trustworthy to a quantified physical accuracy. Do not stitch illustrative merger into scientific Fourier exports.

## Useful controls and export metadata

Use numeric component masses and explicit source/detector frame, redshift, luminosity distance, inclination, orbital phase reference, time reference, f_ref,f_min,f_max,df and PN order. Source masses map to detector masses by1+z; observed GW frequency/time use detector masses. Keep user-provided redshift and luminosity distance independent unless a named cosmology is explicitly applied. Expose actual sampled limits, cutoff, bins, intrinsic phase, complex polarizations, detector strain, and source provenance.

For detector-weighted comparisons use positive one-sided PSD S_n in strain^2/Hz; square ASD exactly once. Define (a|b)=4 Re integral a* b/S_n df, rho=sqrt((h|h)); phase-maximized overlap=abs(4integral a* b/S_n df)/sqrt((a|a)(b|b)). A phase-maximized result at fixed time is not maximized over arrival time or intrinsic parameters. A flat synthetic ASD must be named synthetic; its SNR is not an observing-run sensitivity claim. Real PSD file import should explicitly validate units, positive values, frequency coverage and interpolation. Comparisons require a common frequency grid and band. CSV/JSON should export complex values plus all conventions, units, constants, model/cutoff, mass frame, PSD provenance, and software version. Optional inverseFFT needs Hermitian extension, correct normalization, df anddt relation, windowing/taper metadata, and protection from cyclic wrap; a sampled FD graph alone should not imply an accurately reconstructed merger.

## Access and resource accounting

Remote calls downloaded public LALSuite source, reference arrays, constants and primary documentation. Local calls read scientific.js, compiled source-derived coefficient expressions with .NET, calculated fixtures, and evaluated scientific.js with Node. LLM reasoning assembled formulas, mapped conventions and bounded validity claims. No remote simulation server, project modifications or native LALSuite execution occurred. This subtask used approximately45tool invocations,35remoteHTTPrequests,~20k output/reasoning tokens; these are estimates, not API-billed measurements. Downloaded research source/data~13MB; transient process memory and LLM server memory were not instrumented and cannot be accurately reported.
