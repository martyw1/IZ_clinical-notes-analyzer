(function (global) {
  'use strict';
  const G = 6.67430e-11;
  const C = 299792458;
  const MSUN = 1.988409870698051e30;
  const MPC = 3.085677581491367e22;
  const Science = typeof module !== 'undefined' && module.exports ? require('./scientific.js') : global.HorizonScience;
  const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

  function model(input) {
    for (const key of ['m1', 'm2', 'distance', 'start', 'inclination', 'redshift']) {
      if (!Number.isFinite(input[key])) throw new RangeError(`${key} must be finite`);
    }
    if (input.m1 <= 0 || input.m2 <= 0 || input.distance <= 0 || input.start <= 6 || input.redshift < 0 || input.inclination < 0 || input.inclination > 90) {
      throw new RangeError('Mass, distance, separation, redshift or inclination is outside the physical model domain');
    }
    const mass = input.m1 + input.m2;
    const eta = input.m1 * input.m2 / mass ** 2;
    const rg = G * mass * MSUN / C ** 2;
    const timeUnit = rg / C * (1 + input.redshift);
    const chirp = mass * eta ** (3 / 5);
    const fittedFinalMass = mass * (1 + (Math.sqrt(8 / 9) - 1) * eta - .4333 * eta ** 2 - .4392 * eta ** 3);
    const spin = Math.sqrt(12) * eta - 3.871 * eta ** 2 + 4.028 * eta ** 3;
    const hasFinalMass = Number.isFinite(input.finalMass) && input.finalMass > Math.max(input.m1, input.m2) && input.finalMass < mass;
    const finalMass = hasFinalMass ? input.finalMass : fittedFinalMass;
    const finalTime = G * finalMass * MSUN / C ** 3 * (1 + input.redshift);
    const ringFrequency = (1.5251 - 1.1568 * (1 - spin) ** .1292) / (2 * Math.PI * finalTime);
    const quality = .7000 + 1.4187 * (1 - spin) ** (-.4990);
    const damping = quality / (Math.PI * ringFrequency);
    const trajectory = input.approximant === 'TaylorT4' ? Science.t4Trajectory({ eta, massSeconds: timeUnit, start: input.start }) : null;
    const inspiralTime = trajectory ? trajectory.duration : 5 * timeUnit / (256 * eta) * (input.start ** 4 - 6 ** 4);
    const bridgeTime = 30 * timeUnit;
    const ringTime = 10 * damping;
    const totalTime = inspiralTime + bridgeTime + ringTime;
    const cutoffPhase = trajectory ? trajectory.phase : (input.start ** 2.5 - 6 ** 2.5) / (32 * eta);
    const cutoffFrequency = 1 / (Math.PI * timeUnit * 6 ** 1.5);
    const cosI = Math.cos(input.inclination * Math.PI / 180);
    const amplitudeAt = radius => 4 * eta * rg * (1 + input.redshift) / (input.distance * MPC * radius);

    function atTime(seconds) {
      const t = clamp(seconds, 0, totalTime);
      let phase, frequency, amplitude, x, stage, blend = 0;
      if (t <= inspiralTime) {
        const motion = trajectory ? trajectory.atTime(t) : null;
        x = motion ? motion.x : Math.max(6, (input.start ** 4 - 256 * eta * t / (5 * timeUnit)) ** .25);
        phase = motion ? motion.phase : (input.start ** 2.5 - x ** 2.5) / (32 * eta);
        frequency = motion ? motion.frequency : 1 / (Math.PI * timeUnit * x ** 1.5);
        amplitude = amplitudeAt(x);
        stage = 'Inspiral';
      } else if (t < inspiralTime + bridgeTime) {
        const dt = t - inspiralTime;
        blend = dt / bridgeTime;
        x = 6 * (1 - blend);
        frequency = cutoffFrequency + (ringFrequency - cutoffFrequency) * blend;
        phase = cutoffPhase + Math.PI * (cutoffFrequency * dt + (ringFrequency - cutoffFrequency) * dt ** 2 / (2 * bridgeTime));
        amplitude = amplitudeAt(6) * (1 + .5 * Math.sin(Math.PI * blend / 2));
        stage = 'Merger illustration';
      } else {
        const dt = t - inspiralTime - bridgeTime;
        x = 0;
        blend = 1;
        frequency = ringFrequency;
        phase = cutoffPhase + Math.PI * (cutoffFrequency + ringFrequency) * bridgeTime / 2 + Math.PI * ringFrequency * dt;
        amplitude = 1.5 * amplitudeAt(6) * Math.exp(-dt / damping);
        stage = 'Fitted ringdown';
      }
      const separation = x * rg;
      return { t, x, stage, blend, phase, frequency, amplitude, separation,
        plus: amplitude * (1 + cosI ** 2) / 2 * Math.cos(2 * phase),
        cross: amplitude * cosI * Math.sin(2 * phase),
        radius1: separation * input.m2 / mass, radius2: separation * input.m1 / mass,
        sourceTime: t / (1 + input.redshift),
        luminosity: stage === 'Inspiral' ? 32 / 5 * C ** 5 / G * eta ** 2 / x ** 5 : null,
      };
    }
    function timeAtProgress(progress) {
      const p = clamp(progress, 0, 1);
      if (p <= .78) return inspiralTime * (1 - (1 - p / .78) ** 3);
      if (p <= .88) return inspiralTime + bridgeTime * (p - .78) / .1;
      return inspiralTime + bridgeTime + ringTime * (p - .88) / .12;
    }
    return { ...input, mass, eta, rg, timeUnit, chirp, finalMass, spin, ringFrequency, damping,
      hasFinalMass, inspiralTime, bridgeTime, ringTime, totalTime, cutoffFrequency, trajectory,
      horizon1: 2 * rg * input.m1 / mass, horizon2: 2 * rg * input.m2 / mass,
      radiatedMass: mass - finalMass, fitExtrapolated: Math.max(input.m1, input.m2) / Math.min(input.m1, input.m2) > 6,
      atTime, timeAtProgress, atProgress: p => atTime(timeAtProgress(p)),
    };
  }
  const API = { G, C, MSUN, MPC, clamp, model };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  else global.BlackHolePhysics = API;
})(typeof window !== 'undefined' ? window : globalThis);
