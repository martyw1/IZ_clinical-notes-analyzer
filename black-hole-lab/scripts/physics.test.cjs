const assert = require('node:assert/strict');
const test = require('node:test');
const { model, G, C, MSUN, MPC } = require('../physics.js');
const input = { m1: 36, m2: 29, distance: 410, redshift: .09, start: 24, inclination: 35 };
const near = (a, b, tolerance = 1e-10) => assert.ok(Math.abs(a - b) <= tolerance * Math.max(Math.abs(a), Math.abs(b), 1e-30), `${a} != ${b}`);
test('center of mass, Kepler frequency and exact quadrupole shrinkage', () => {
  const m = model(input), a = m.atTime(0), b = m.atTime(m.inspiralTime / 2);
  near(input.m1 * a.radius1, input.m2 * a.radius2);
  const period = 2 * Math.PI * Math.sqrt(a.separation ** 3 / (G * m.mass * MSUN));
  near(a.frequency, 2 / (period * (1 + input.redshift)));
  near(b.x ** 4, (input.start ** 4 + 6 ** 4) / 2);
  near(m.atTime(m.inspiralTime).x, 6);
  assert.ok(b.frequency > a.frequency && b.amplitude > a.amplitude);
});
test('redshift transforms observer time/frequency and luminosity-distance strain', () => {
  const a = model({ ...input, redshift: 0 }), b = model({ ...input, redshift: 1 });
  near(b.inspiralTime, 2 * a.inspiralTime);
  near(b.atTime(0).frequency, a.atTime(0).frequency / 2);
  near(b.atTime(0).amplitude, a.atTime(0).amplitude * 2);
  near(a.horizon1, b.horizon1);
});
test('chirp derivative matches independent leading-order frequency law', () => {
  const m = model(input), t = m.inspiralTime * .4, dt = 1e-5;
  const f = m.atTime(t).frequency;
  const measured = (m.atTime(t + dt).frequency - m.atTime(t - dt).frequency) / (2 * dt);
  const expected = 96 / 5 * Math.PI ** (8 / 3) * (G * m.chirp * MSUN * 1.09 / C ** 3) ** (5 / 3) * f ** (11 / 3);
  near(measured, expected, 1e-7);
});
test('strain inverse distance and inclination response', () => {
  const face = model({ ...input, inclination: 0 });
  const far = model({ ...input, inclination: 0, distance: 820 });
  near(face.atTime(0).plus, 2 * far.atTime(0).plus);
  const edge = model({ ...input, inclination: 90 });
  near(edge.atTime(0).plus, face.atTime(0).plus / 2);
  assert.ok(Math.abs(edge.atTime(.4).cross) < 1e-35);
  near(face.atTime(0).amplitude, 4 * face.eta * face.rg * 1.09 / (410 * MPC * 24));
});
test('equal-mass published remnant fit and ringdown damping', () => {
  const m = model({ ...input, m1: 30, m2: 30 });
  near(m.spin, .6870254037844386);
  near(m.finalMass / 60, .951758510395516, 1e-12);
  const t = m.inspiralTime + m.bridgeTime;
  near(m.atTime(t + m.damping).amplitude / m.atTime(t).amplitude, 1 / Math.E);
});
test('bridge phase and strain are continuous at both joins', () => {
  const m = model(input);
  for (const t of [m.inspiralTime, m.inspiralTime + m.bridgeTime]) {
    const a = m.atTime(t - 1e-10), b = m.atTime(t + 1e-10);
    near(a.amplitude, b.amplitude, 1e-6);
    near(a.phase, b.phase, 1e-6);
  }
});
test('playback maps monotonically and ends; extreme mass ratio identified', () => {
  for (const masses of [[.1, .1], [300, 3], [30, 30]]) {
    const m = model({ ...input, m1: masses[0], m2: masses[1] });
    let last = -1;
    for (let n = 0; n <= 1000; n++) {
      const state = m.atProgress(n / 1000);
      assert.ok(state.t >= last);
      assert.ok(Object.values(state).every(v => typeof v !== 'number' || Number.isFinite(v)));
      last = state.t;
    }
    near(last, m.totalTime);
  }
  assert.ok(model({ ...input, m1: 300, m2: 3 }).fitExtrapolated);
});
test('nonphysical inputs fail instead of yielding invented states', () => {
  for (const patch of [{ m1: 0 }, { distance: 0 }, { redshift: -1 }, { start: 6 }, { m2: NaN }]) {
    assert.throws(() => model({ ...input, ...patch }), RangeError);
  }
});
