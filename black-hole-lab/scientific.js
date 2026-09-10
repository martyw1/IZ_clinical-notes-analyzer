(function (global) {
  'use strict';
  const C = 299792458, G = 6.67430e-11, MSUN = 1.988409870698051e30, MPC = 3.085677581491367e22;
  const MTSUN = G * MSUN / C ** 3, GAMMA = 0.5772156649015329;
  const SOURCE_SHA = 'c54be3dd1be3c9effedc83f0dda55a0d9fa1f34c';
  const SOURCE_URL = `https://git.ligo.org/lscsoft/lalsuite/-/blob/${SOURCE_SHA}/lalsimulation/lib/LALSimInspiralPNCoefficients.c`;
  function t4Correction(v, eta) {
    const a2 = -743 / 336 - 11 * eta / 4;
    const a3 = 4 * Math.PI;
    const a4 = 34103 / 18144 + 13661 * eta / 2016 + 59 * eta ** 2 / 18;
    const a5 = -Math.PI * (4159 / 672 + 189 * eta / 8);
    const a6 = 16447322263 / 139708800 - 1712 * GAMMA / 105 - 56198689 * eta / 217728
      + Math.PI ** 2 * (16 / 3 + 451 * eta / 48) + 541 * eta ** 2 / 896 - 5605 * eta ** 3 / 2592
      - 856 * Math.log(16 * v ** 2) / 105;
    const a7 = Math.PI * (-13245 + 717350 * eta + 731960 * eta ** 2) / 12096;
    return 1 + a2 * v ** 2 + a3 * v ** 3 + a4 * v ** 4 + a5 * v ** 5 + a6 * v ** 6 + a7 * v ** 7;
  }
  function t4Trajectory({ eta, massSeconds, start, steps = 4096 }) {
    if (!(eta > 0 && eta <= .25 && massSeconds > 0 && start > 6 && Number.isInteger(steps) && steps >= 32 && steps <= 65536)) throw new RangeError('Invalid TaylorT4 trajectory domain');
    const v0 = 1 / Math.sqrt(start), v1 = 1 / Math.sqrt(6), dv = (v1 - v0) / steps;
    const times = new Float64Array(steps + 1), phases = new Float64Array(steps + 1), speeds = new Float64Array(steps + 1);
    const speed = v => 32 * eta / (5 * massSeconds) * v ** 9 * t4Correction(v, eta);
    const integrands = v => { const inverse = 1 / speed(v); if (!(inverse > 0 && Number.isFinite(inverse))) throw new RangeError('TaylorT4 frequency evolution is not monotonic'); return [inverse, inverse * v ** 3 / massSeconds]; };
    for (let i = 0; i <= steps; i++) speeds[i] = speed(v0 + i * dv);
    for (let i = 1; i <= steps; i++) {
      const va = v0 + (i - 1) * dv, vc = v0 + i * dv;
      const a = [1 / speeds[i - 1], va ** 3 / (massSeconds * speeds[i - 1])], b = integrands(v0 + (i - .5) * dv), c = [1 / speeds[i], vc ** 3 / (massSeconds * speeds[i])];
      times[i] = times[i - 1] + dv / 6 * (a[0] + 4 * b[0] + c[0]);
      phases[i] = phases[i - 1] + dv / 6 * (a[1] + 4 * b[1] + c[1]);
    }
    const hermite = (a, b, da, db, u, dt) => (2 * u ** 3 - 3 * u ** 2 + 1) * a + (u ** 3 - 2 * u ** 2 + u) * dt * da + (-2 * u ** 3 + 3 * u ** 2) * b + (u ** 3 - u ** 2) * dt * db;
    function atTime(t) {
      if (!Number.isFinite(t)) throw new RangeError('Time must be finite');
      const clamped = Math.min(times[steps], Math.max(0, t));
      let low = 0, high = steps;
      while (high - low > 1) { const mid = (low + high) >> 1; if (times[mid] <= clamped) low = mid; else high = mid; }
      const dt = times[high] - times[low], u = (clamped - times[low]) / dt;
      const va = v0 + low * dv, vb = v0 + high * dv;
      const v = hermite(va, vb, speeds[low], speeds[high], u, dt);
      return { v, x: 1 / v ** 2, phase: hermite(phases[low], phases[high], va ** 3 / massSeconds, vb ** 3 / massSeconds, u, dt), frequency: v ** 3 / (Math.PI * massSeconds) };
    }
    return { duration: times[steps], phase: phases[steps], steps, atTime };
  }
  function phaseSeries(v, eta, order = 7) {
    const coefficients = [1, 0, 3715 / 756 + 55 * eta / 9, -16 * Math.PI,
      15293365 / 508032 + 27145 * eta / 504 + 3085 * eta ** 2 / 72,
      Math.PI * (38645 / 756 - 65 * eta / 9) * (1 + 3 * Math.log(v)),
      11583231236531 / 4694215680 - 640 * Math.PI ** 2 / 3 - 6848 * GAMMA / 21
        + (-15737765635 / 3048192 + 2255 * Math.PI ** 2 / 12) * eta + 76055 * eta ** 2 / 1728 - 127825 * eta ** 3 / 1296 - 6848 * Math.log(4 * v) / 21,
      Math.PI * (77096675 / 254016 + 378515 * eta / 1512 - 74045 * eta ** 2 / 756)];
    return 3 / (128 * eta * v ** 5) * coefficients.reduce((sum, coefficient, power) => sum + (power <= order ? coefficient * v ** power : 0), 0);
  }
  function antenna(theta, phi, psi) {
    const d = Math.PI / 180, ct = Math.cos(theta * d), c2p = Math.cos(2 * phi * d), s2p = Math.sin(2 * phi * d);
    const c2s = Math.cos(2 * psi * d), s2s = Math.sin(2 * psi * d);
    const plus = .5 * (1 + ct ** 2) * c2p * c2s - ct * s2p * s2s;
    const cross = .5 * (1 + ct ** 2) * c2p * s2s + ct * s2p * c2s;
    return { plus: Math.abs(plus) < 1e-15 ? 0 : plus, cross: Math.abs(cross) < 1e-15 ? 0 : cross };
  }
  function validate(input) {
    const ranges = { m1: [.1, 1000], m2: [.1, 1000], distance: [.001, 1e6], redshift: [0, 10], inclination: [0, 180], fmin: [1, 20000], fmax: [1, 20000], df: [.0001, 100], fref: [0, 20000], phase: [-1000, 1000], time: [-10000, 10000], theta: [0, 180], phi: [-360, 360], psi: [-180, 180], asd: [1e-30, 1e-15] };
    for (const [key, [low, high]] of Object.entries(ranges)) if (!Number.isFinite(input[key]) || input[key] < low || input[key] > high) throw new RangeError(`${key} must be finite and between ${low} and ${high}.`);
    if (!['source', 'detector'].includes(input.frame) || ![0, 2, 3, 4, 5, 6, 7].includes(input.order)) throw new RangeError('Unsupported mass frame or PN phase order.');
    if (input.fmin >= input.fmax) throw new RangeError('Upper frequency must exceed lower frequency.');
  }
  function frequencyModel(input) {
    validate(input);
    const detectorFactor = input.frame === 'source' ? 1 + input.redshift : 1;
    const m1 = input.m1 * detectorFactor, m2 = input.m2 * detectorFactor, mass = m1 + m2, eta = m1 * m2 / mass ** 2;
    const massSeconds = mass * MTSUN, chirp = mass * eta ** (3 / 5), isco = 1 / (6 ** 1.5 * Math.PI * massSeconds);
    const end = Math.min(input.fmax, isco), firstIndex = Math.ceil(input.fmin / input.df), lastIndex = Math.floor(end / input.df), count = lastIndex - firstIndex + 1;
    if (count < 2) throw new RangeError('Fewer than two frequency bins below ISCO. Lower the frequency band or decrease Δf.');
    if (count > 65536) throw new RangeError('More than 65,536 bins. Increase Δf or narrow the frequency band; no silent undersampling is applied.');
    if (input.fref > isco) throw new RangeError('Reference frequency exceeds this model’s ISCO cutoff.');
    const response = antenna(input.theta, input.phi, input.psi), ci = Math.cos(input.inclination * Math.PI / 180);
    const plusFactor = (1 + ci ** 2) / 2, crossFactor = ci;
    const amplitude = -Math.sqrt(5 / 24) * (chirp * MTSUN) ** (5 / 6) / (Math.PI ** (2 / 3) * (input.distance * MPC / C));
    const refV = input.fref > 0 ? Math.cbrt(Math.PI * massSeconds * input.fref) : 0;
    function atFrequency(frequency, order = input.order) {
      if (!Number.isFinite(frequency) || frequency <= 0) throw new RangeError('Frequency must be positive and finite.');
      const v = Math.cbrt(Math.PI * massSeconds * frequency);
      const phase = phaseSeries(v, eta, order) - (refV ? phaseSeries(refV, eta, order) : 0) - 2 * input.phase + 2 * Math.PI * frequency * input.time;
      const amp = amplitude * frequency ** (-7 / 6), angle = phase - Math.PI / 4;
      const re = amp * Math.cos(angle), im = -amp * Math.sin(angle);
      const plusRe = plusFactor * re, plusIm = plusFactor * im;
      const crossRe = crossFactor * im, crossIm = -crossFactor * re;
      return { frequency, phase, amplitude: Math.abs(amp), plusRe, plusIm, crossRe, crossIm,
        detectorRe: response.plus * plusRe + response.cross * crossRe, detectorIm: response.plus * plusIm + response.cross * crossIm };
    }
    const samples = Array.from({ length: count }, (_, index) => atFrequency((firstIndex + index) * input.df));
    let norm = 0, norm0 = 0, innerRe = 0, innerIm = 0;
    const deltas = [];
    for (const sample of samples) {
      const base = atFrequency(sample.frequency, 0), weight = 4 * input.df / input.asd ** 2;
      norm += weight * (sample.detectorRe ** 2 + sample.detectorIm ** 2);
      norm0 += weight * (base.detectorRe ** 2 + base.detectorIm ** 2);
      innerRe += weight * (sample.detectorRe * base.detectorRe + sample.detectorIm * base.detectorIm);
      innerIm += weight * (sample.detectorIm * base.detectorRe - sample.detectorRe * base.detectorIm);
      deltas.push(sample.phase - base.phase);
    }
    return { input: { ...input }, detectorMass1: m1, detectorMass2: m2, sourceMass1: m1 / (1 + input.redshift), sourceMass2: m2 / (1 + input.redshift), massSeconds, eta, chirp, isco,
      actualMin: samples[0].frequency, actualMax: samples.at(-1).frequency, count, samples, deltas, response, snr: Math.sqrt(norm),
      phaseMaximizedOverlap: norm > 0 && norm0 > 0 ? Math.min(1, Math.hypot(innerRe, innerIm) / Math.sqrt(norm * norm0)) : null,
      atFrequency, cutoffApplied: input.fmax > isco };
  }
  function verifyReferences(reference) {
    if (!reference?.pn?.pointwise?.length || !reference?.pn?.integrals?.length || !reference?.waveform?.samples?.length) throw new Error('Independent reference data is unavailable.');
    let phaseAbsoluteError = 0, correctionAbsoluteError = 0, trajectoryRelativeError = 0, waveformRelativeError = 0, waveformBins = 0;
    for (const point of reference.pn.pointwise) {
      phaseAbsoluteError = Math.max(phaseAbsoluteError, Math.abs(phaseSeries(point.v, point.eta) - point.F2_intrinsic_phase));
      correctionAbsoluteError = Math.max(correctionAbsoluteError, Math.abs(t4Correction(point.v, point.eta) - point.B));
    }
    for (const expected of reference.pn.integrals) {
      const trajectory = t4Trajectory({ eta: expected.eta, massSeconds: 1, start: expected.startSeparationProxy });
      trajectoryRelativeError = Math.max(trajectoryRelativeError, Math.abs(trajectory.duration / expected.durationOverM - 1), Math.abs(trajectory.phase / expected.orbitalPhaseRadians - 1));
    }
    const p = reference.waveform.parameters;
    const model = frequencyModel({ m1: p.mass1DetectorSolar, m2: p.mass2DetectorSolar, frame: 'detector', distance: p.luminosityDistanceMpc, redshift: 0, inclination: p.inclinationRad * 180 / Math.PI, fmin: p.minFrequencyHz, fmax: p.maxFrequencyHz, df: p.deltaFrequencyHz, fref: p.referenceFrequencyHz, phase: p.orbitalPhaseReferenceRad, time: p.coalescenceTimeSeconds, theta: 0, phi: 0, psi: 0, asd: 1e-23, order: 7 });
    for (const expected of reference.waveform.samples) {
      if (expected.frequencyHz < p.minFrequencyHz) continue;
      const actual = model.atFrequency(expected.frequencyHz);
      for (const polarization of ['plus', 'cross']) {
        const norm = Math.hypot(expected[polarization + 'Real'], expected[polarization + 'Imag']);
        waveformRelativeError = Math.max(waveformRelativeError, Math.hypot(actual[polarization + 'Re'] - expected[polarization + 'Real'], actual[polarization + 'Im'] - expected[polarization + 'Imag']) / norm);
      }
      waveformBins++;
    }
    const pass = waveformBins > 0 && [phaseAbsoluteError, correctionAbsoluteError, trajectoryRelativeError, waveformRelativeError].every(Number.isFinite)
      && phaseAbsoluteError < 1e-8 && correctionAbsoluteError < 1e-12 && trajectoryRelativeError < 1e-9 && waveformRelativeError < 1e-8;
    return { pass, sourceCommit: SOURCE_SHA, coefficientPoints: reference.pn.pointwise.length, trajectoryCases: reference.pn.integrals.length, waveformBins, phaseAbsoluteError, correctionAbsoluteError, trajectoryRelativeError, waveformRelativeError,
      referenceProvenance: reference.waveform.provenance, thresholds: { phaseAbsoluteRadians: 1e-8, correctionAbsolute: 1e-12, trajectoryRelative: 1e-9, waveformComplexRelative: 1e-8 } };
  }
  const API = { G, C, MSUN, MPC, MTSUN, SOURCE_SHA, SOURCE_URL, t4Correction, t4Trajectory, phaseSeries, antenna, frequencyModel, verifyReferences };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  else global.HorizonScience = API;
})(typeof window !== 'undefined' ? window : globalThis);
