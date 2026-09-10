const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const S = require('../scientific.js');
const P = require('../physics.js');
const defaults = { m1: 30, m2: 20, frame: 'source', distance: 470, redshift: .1, inclination: 35, fmin: 20, fmax: 512, df: .25, fref: 20, phase: 0, time: 0, theta: 0, phi: 0, psi: 0, asd: 1e-23, order: 7 };
const near = (actual, expected, relative = 1e-11) => assert.ok(Math.abs(actual - expected) <= Math.max(1e-40, Math.abs(expected) * relative), `${actual} != ${expected}`);
test('independent LAL waveform regression and source-extracted PN trajectories', () => {
  const root = path.resolve(__dirname, '..');
  const reference = { pn: require('../data/references/pn-source-fixtures.json'), waveform: require('../data/references/taylorf2-independent.json') };
  const result = S.verifyReferences(reference);
  assert.equal(result.waveformBins, 477); assert.equal(result.trajectoryCases, 12); assert.equal(result.coefficientPoints, 12);
  assert.equal(result.pass, true); assert.ok(result.waveformRelativeError < 1e-8); assert.ok(result.trajectoryRelativeError < 1e-9);
  fs.mkdirSync(path.join(root, 'evidence'), { recursive: true });
  fs.writeFileSync(path.join(root, 'evidence/scientific-validation.json'), JSON.stringify(result, null, 2));
});
test('source/detector mass conversion preserves frequency waveform', () => {
  const a = S.frequencyModel(defaults), b = S.frequencyModel({ ...defaults, frame: 'detector', m1: 33, m2: 22 });
  near(a.isco, b.isco); near(a.snr, b.snr); near(a.samples[20].plusRe, b.samples[20].plusRe, 1e-9);
  near(b.sourceMass1, 30); near(b.sourceMass2, 20);
});
test('distance, white ASD, phase and arrival time have the physical scaling', () => {
  const a = S.frequencyModel(defaults), farther = S.frequencyModel({ ...defaults, distance: 940 }), noisier = S.frequencyModel({ ...defaults, asd: 2e-23 });
  near(farther.snr, a.snr / 2); near(noisier.snr, a.snr / 2);
  const f = 30, base = a.atFrequency(f), moved = S.frequencyModel({ ...defaults, time: .025 }).atFrequency(f);
  const rotation = -2 * Math.PI * f * .025;
  near(moved.plusRe, base.plusRe * Math.cos(rotation) - base.plusIm * Math.sin(rotation), 1e-10);
  const phased = S.frequencyModel({ ...defaults, phase: Math.PI / 2 }).atFrequency(f);
  near(phased.plusRe, -base.plusRe, 1e-10); near(phased.plusIm, -base.plusIm, 1e-10);
});
test('inclination and ideal detector nulls preserve polarization conventions', () => {
  assert.deepEqual(S.antenna(0, 0, 0), { plus: 1, cross: 0 });
  assert.deepEqual(S.antenna(90, 45, 0), { plus: 0, cross: 0 });
  const nullSignal = S.frequencyModel({ ...defaults, theta: 90, phi: 45 }); assert.equal(nullSignal.snr, 0); assert.equal(nullSignal.phaseMaximizedOverlap, null);
  const face = S.frequencyModel({ ...defaults, inclination: 0 }).samples[0], edge = S.frequencyModel({ ...defaults, inclination: 90 }).samples[0];
  near(edge.plusRe, face.plusRe / 2); assert.ok(Math.hypot(edge.crossRe, edge.crossIm) < Math.hypot(face.crossRe, face.crossIm) * 1e-15);
  near(face.crossRe, face.plusIm); near(face.crossIm, -face.plusRe);
});
test('frequency grid is uniform, origin-aligned, and bounded by explicit ISCO', () => {
  const m = S.frequencyModel({ ...defaults, fmin: 20.1, df: .25 });
  assert.equal(m.actualMin, 20.25); assert.ok(m.actualMax <= m.isco && m.isco - m.actualMax < .25);
  for (let i = 1; i < m.samples.length; i++) near(m.samples[i].frequency - m.samples[i - 1].frequency, .25);
  assert.equal(S.frequencyModel({ ...defaults, order: 0 }).phaseMaximizedOverlap, 1);
});
test('invalid bands, nonfinite values and excessive grids are rejected without silently changing sampling', () => {
  for (const override of [{ m1: NaN }, { m2: 0 }, { redshift: -1 }, { frame: 'unknown' }, { order: 1 }, { fmin: 512 }, { fref: 500 }, { df: .0001 }, { distance: Infinity }]) assert.throws(() => S.frequencyModel({ ...defaults, ...override }), RangeError);
});
test('TaylorT4 animation agrees with quadrature and remains continuous into illustrative bridge', () => {
  const input = { m1: 30, m2: 30, distance: 400, start: 20, inclination: 35, redshift: .1, approximant: 'TaylorT4' }, m = P.model(input);
  near(m.inspiralTime / m.timeUnit, 11937.310066261301, 1e-10);
  const endpoint = m.atTime(m.inspiralTime), right = m.atTime(m.inspiralTime + m.timeUnit * 1e-7);
  near(endpoint.x, 6); near(endpoint.frequency, m.cutoffFrequency); near(right.plus, endpoint.plus, 1e-6);
  const fine = S.t4Trajectory({ eta: .25, massSeconds: m.timeUnit, start: 20, steps: 8192 });
  for (let i = 0; i <= 100; i++) { const a = m.atTime(m.inspiralTime * i / 100), b = fine.atTime(m.inspiralTime * i / 100); near(a.frequency, b.frequency, 1e-8); assert.ok(Math.abs(a.phase - b.phase) < 1e-7); }
});
test('TaylorT4 high-mass-ratio and subsolar trajectories remain finite across playback', () => {
  for (const [m1, m2] of [[.5, .3], [300, .1], [30, 30]]) {
    const m = P.model({ m1, m2, distance: 10, start: 60, inclination: 90, redshift: 0, approximant: 'TaylorT4' });
    let last = -1;
    for (let i = 0; i <= 100; i++) { const state = m.atProgress(i / 100); assert.ok([state.t, state.frequency, state.plus, state.cross].every(Number.isFinite)); assert.ok(state.t > last); last = state.t; }
  }
});
