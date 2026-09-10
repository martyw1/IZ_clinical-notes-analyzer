(() => {
  'use strict';
  const $ = id => document.getElementById(id), S = window.HorizonScience, publications = window.LIGO_PUBLICATIONS;
  const fmt = (value, digits = 3) => Number.isFinite(value) ? value.toLocaleString('en-US', { maximumFractionDigits: digits }) : '—';
  let result = null, libraryLimit = 25, activeView = 'simulation', checkResult = null;
  const numericNames = ['m1', 'm2', 'distance', 'redshift', 'inclination', 'fmin', 'fmax', 'df', 'fref', 'phase', 'time', 'theta', 'phi', 'psi', 'asd', 'order'];
  function node(tag, className, text) { const item = document.createElement(tag); if (className) item.className = className; if (text !== undefined) item.textContent = text; return item; }
  function sourceLink(label, url) {
    const parsed = new URL(url); if (parsed.protocol === 'http:') parsed.protocol = 'https:';
    if (parsed.protocol !== 'https:') return node('span', '', label);
    const item = node('a', '', label); item.href = parsed.href; item.target = '_blank'; item.rel = 'noreferrer'; return item;
  }
  function download(name, contents, type) {
    const url = URL.createObjectURL(new Blob([contents], { type })), anchor = node('a');
    anchor.href = url; anchor.download = name; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function readInputs() {
    const entries = Object.fromEntries(new FormData($('science-form')));
    for (const name of numericNames) entries[name] = entries[name] === '' ? NaN : Number(entries[name]);
    return entries;
  }
  function calculate() {
    try {
      result = S.frequencyModel(readInputs());
      $('science-error').hidden = true;
      $('science-chirp').textContent = fmt(result.chirp, 6); $('science-isco').textContent = fmt(result.isco, 3);
      $('science-count').textContent = fmt(result.count, 0); $('science-snr').textContent = fmt(result.snr, 4);
      $('science-summary').textContent = `TaylorF2 ${result.input.order / 2}PN · ${fmt(result.actualMin, 6)}–${fmt(result.actualMax, 6)} Hz · Δf ${fmt(result.input.df, 6)} Hz. ${result.cutoffApplied ? 'Requested upper band truncated at the stated ISCO reference.' : 'Entire requested band is below the ISCO reference.'} Restricted amplitude; zero spin and tides.`;
      $('science-comparison').textContent = `Compared with 0PN using identical phase, reference frequency, and time. Phase-maximized overlap: ${result.phaseMaximizedOverlap === null ? 'undefined (zero detector response)' : result.phaseMaximizedOverlap.toFixed(6)}. Not maximized over time or intrinsic parameters. White-noise weighting; no detection claim. F+ = ${fmt(result.response.plus, 6)}, F× = ${fmt(result.response.cross, 6)}.`;
      $('science-export').disabled = false; $('science-config').disabled = false;
      drawPlots();
    } catch (error) {
      result = null; $('science-error').hidden = false; $('science-error').textContent = error.message;
      $('science-summary').textContent = 'No current waveform: correct the inputs and calculate again.';
      for (const id of ['science-chirp', 'science-isco', 'science-count', 'science-snr']) $(id).textContent = '—';
      $('science-comparison').textContent = 'No comparison available for these inputs.';
      $('science-export').disabled = true; $('science-config').disabled = true;
      drawPlots();
    }
  }
  function chart(canvas) {
    const width = canvas.clientWidth || 640, height = canvas.clientHeight || 264, ratio = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
    const ctx = canvas.getContext('2d'); ctx.scale(ratio, ratio);
    const style = getComputedStyle(document.documentElement), colors = Object.fromEntries(['text', 'muted', 'border', 'accent', 'cyan'].map(key => [key, style.getPropertyValue(`--${key}`).trim()]));
    ctx.font = '12px Consolas, monospace'; return { ctx, width, height, colors };
  }
  function plot(canvas, series, options) {
    const { ctx, width, height, colors } = chart(canvas), left = 68, right = width - 20, top = 40, bottom = height - 40;
    if (!result) { ctx.fillStyle = colors.muted; ctx.fillText('No current waveform', left, top); return; }
    const xmin = options.logX ? Math.log10(result.actualMin) : result.actualMin, xmax = options.logX ? Math.log10(result.actualMax) : result.actualMax;
    const ys = series.flatMap(line => line.values).filter(value => Number.isFinite(value) && (!options.logY || value > 0)).map(value => options.logY ? Math.log10(value) : value);
    let ymin = ys.reduce((minimum, value) => Math.min(minimum, value), Infinity), ymax = ys.reduce((maximum, value) => Math.max(maximum, value), -Infinity); if (!ys.length) { ymin = -24; ymax = -20; }
    const padding = Math.max((ymax - ymin) * .12, options.logY ? .1 : .5); ymin -= padding; ymax += padding;
    const x = f => left + ((options.logX ? Math.log10(f) : f) - xmin) / (xmax - xmin) * (right - left);
    const y = value => bottom - ((options.logY ? Math.log10(value) : value) - ymin) / (ymax - ymin) * (bottom - top);
    ctx.fillStyle = colors.muted; ctx.fillText(options.label, 0, 16); ctx.lineWidth = .7;
    for (let i = 0; i <= 3; i++) {
      const yy = top + (bottom - top) * i / 3, value = ymax - (ymax - ymin) * i / 3;
      ctx.strokeStyle = colors.border; ctx.beginPath(); ctx.moveTo(left, yy); ctx.lineTo(right, yy); ctx.stroke();
      ctx.fillStyle = colors.muted; ctx.fillText(options.logY ? (10 ** value).toExponential(1) : fmt(value, 1), 0, yy + 4);
    }
    for (let i = 0; i <= (width < 450 ? 2 : 4); i++) {
      const n = width < 450 ? 2 : 4, f = options.logX ? 10 ** (xmin + (xmax - xmin) * i / n) : xmin + (xmax - xmin) * i / n;
      const xx = x(f); ctx.strokeStyle = colors.border; ctx.beginPath(); ctx.moveTo(xx, top); ctx.lineTo(xx, bottom); ctx.stroke();
      ctx.fillStyle = colors.muted; ctx.fillText(fmt(f, 1), Math.min(right - 32, Math.max(left - 8, xx - 16)), bottom + 20);
    }
    ctx.fillText('Frequency (Hz)', Math.max(left, (width - 110) / 2), height - 2);
    series.forEach((line, index) => {
      ctx.strokeStyle = index ? colors.cyan : colors.accent; ctx.lineWidth = 1.6; ctx.beginPath(); let started = false;
      for (let i = 0; i < line.values.length; i++) { const value = line.values[i]; if (!Number.isFinite(value) || (options.logY && value <= 0)) { started = false; continue; } const xx = x(result.samples[i].frequency), yy = y(value); if (!started) ctx.moveTo(xx, yy); else ctx.lineTo(xx, yy); started = true; } ctx.stroke();
      ctx.fillStyle = index ? colors.cyan : colors.accent; ctx.fillText(line.label, left + index * (width < 450 ? 120 : 180), 32);
    });
  }
  function drawPlots() {
    if (activeView !== 'scientist') return;
    plot($('science-spectrum'), result ? [{ label: '2f |h̃det|', values: result.samples.map(s => 2 * s.frequency * Math.hypot(s.detectorRe, s.detectorIm)) }, { label: '√(f Sₙ)', values: result.samples.map(s => Math.sqrt(s.frequency) * result.input.asd) }] : [], { logX: true, logY: true, label: 'Characteristic strain (dimensionless)' });
    plot($('science-phase-plot'), result ? [{ label: 'Selected − 0PN', values: result.deltas }] : [], { logX: true, logY: false, label: 'Unwrapped phase difference (rad)' });
  }
  function renderLibrary() {
    const query = $('library-search').value.trim().toLowerCase(), topic = $('library-topic').value, year = $('library-year').value;
    const rows = publications.records.filter(record => (!query || `${record.title} ${record.byline} ${record.sourceKeywords.join(' ')} ${record.arxivLinks.map(x => x.label).join(' ')} ${record.publicReportLinks.map(x => x.label).join(' ')}`.toLowerCase().includes(query)) && (!topic || record.sourceKeywords.includes(topic)) && (!year || record.releaseDate?.startsWith(year)));
    $('library-count').textContent = `${rows.length} of ${publications.recordCount} records`;
    const fragment = document.createDocumentFragment();
    for (const record of rows.slice(0, libraryLimit)) {
      const row = node('article', 'library-row'), date = node('time', '', record.releaseDate || record.releaseDateSource || 'Undated'); if (record.releaseDate) date.dateTime = record.releaseDate;
      const body = node('div'); body.append(node('h2', '', record.title), node('p', '', `${record.byline} · ${record.journalCitation || 'See source record'}`));
      const keywords = node('div', 'source-keywords'); keywords.append(node('span', '', 'INDEXED · NOT IMPLEMENTED')); for (const keyword of record.sourceKeywords) keywords.append(node('span', '', keyword)); body.append(keywords);
      const links = node('div', 'library-links');
      for (const [type, entries] of [['arXiv', record.arxivLinks], ['Journal', record.journalLinks], ['Public report', record.publicReportLinks], ['Science summary', record.scienceSummaryLinks]]) for (const entry of entries) links.append(sourceLink(`${type}${type === 'arXiv' ? ` ${entry.label}` : ''}`, entry.url));
      if (!links.children.length) links.append(sourceLink('Source record', record.source));
      body.append(links); row.append(date, body); fragment.append(row);
    }
    if (!rows.length) fragment.append(node('p', 'empty-state', 'No publications match these filters. Clear the search or choose another topic.'));
    $('library-list').replaceChildren(fragment); $('library-more').hidden = rows.length <= libraryLimit;
  }
  function manifest() {
    return { schemaVersion: 2, softwareVersion: '2.0.0', generatedAt: new Date().toISOString(), model: `TaylorF2 ${result.input.order / 2}PN phase, restricted Newtonian amplitude, circular nonspinning point particles`, source: { commit: S.SOURCE_SHA, coefficients: S.SOURCE_URL },
      inputs: result.input, constants: { G: S.G, c: S.C, solarMassKg: S.MSUN, mpcMeters: S.MPC, solarMassTimeSeconds: S.MTSUN },
      conventions: { transform: 'h(f)=A(f) exp[-i(phase(f)-pi/4)] with negative real base A; hcross=-i cos(inclination) hbase', phaseReference: 'Orbital radians; finite fref subtracts intrinsic phase at fref', timeShift: 'Positive time adds +2pi f t to phase inside negative exponential', units: 'Frequency Hz; htilde complex polarizations seconds (strain/Hz); distances luminosity Mpc; input angles degrees except orbital phase radians', detector: 'Ideal 90-degree local-frame interferometer, not a celestial RA/declination or an actual detector timestamp', noise: 'Constant one-sided PSD = ASD squared; not measured instrument noise', innerProduct: '4 deltaF sum over selected positive-frequency bins; overlap maximized only over constant phase' },
      derived: { detectorMass1: result.detectorMass1, detectorMass2: result.detectorMass2, sourceMass1: result.sourceMass1, sourceMass2: result.sourceMass2, detectorChirpMass: result.chirp, iscoHz: result.isco, actualMinHz: result.actualMin, actualMaxHz: result.actualMax, bins: result.count, antenna: result.response, idealNoiseSNR: result.snr, phaseMaximizedOverlapWith0PN: result.phaseMaximizedOverlap },
      verification: checkResult, limitations: ['Inspiral only; ISCO is a test-particle reference, not a validated comparable-mass merger boundary.', 'Zero component spin, precession, eccentricity, matter and tides.', 'PN expansion and restricted amplitude are not a precision full-merger waveform.', 'No calibration, real PSD, likelihood, posterior sampling or detection claim.'] };
  }
  $('science-form').addEventListener('submit', event => { event.preventDefault(); calculate(); });
  $('science-form').addEventListener('input', () => { $('science-summary').textContent = 'Inputs changed. Calculate again to update the waveform and enable export.'; $('science-export').disabled = true; $('science-config').disabled = true; });
  $('science-reset').addEventListener('click', () => { $('science-form').reset(); calculate(); });
  $('science-copy').addEventListener('click', () => { const input = window.HorizonLab.getSettings(); for (const name of ['m1', 'm2', 'distance', 'redshift', 'inclination']) $('science-form').elements.namedItem(name).value = input[name]; $('science-frame').value = 'source'; calculate(); });
  $('science-export').addEventListener('click', () => { if (!result) return; const columns = ['frequency', 'plusRe', 'plusIm', 'crossRe', 'crossIm', 'detectorRe', 'detectorIm', 'phase']; download('horizon-taylorf2.csv', ['frequency_Hz,hplus_real_s,hplus_imag_s,hcross_real_s,hcross_imag_s,hdet_real_s,hdet_imag_s,phase_rad', ...result.samples.map(sample => columns.map(key => sample[key].toPrecision(16)).join(','))].join('\n') + '\n', 'text/csv'); });
  $('science-config').addEventListener('click', () => { if (result) download('horizon-reproducibility.json', JSON.stringify(manifest(), null, 2), 'application/json'); });
  $('library-summary').textContent = `${publications.recordCount} public index records · ${publications.records.at(-1).releaseDate?.slice(0, 4)}–${publications.records[0].releaseDate?.slice(0, 4)} · retrieved ${publications.retrievedOn}.`;
  for (const topic of [...new Set(publications.records.flatMap(record => record.sourceKeywords))].sort()) $('library-topic').append(new Option(topic, topic));
  for (const year of [...new Set(publications.records.map(record => record.releaseDate?.slice(0, 4)).filter(Boolean))].sort().reverse()) $('library-year').append(new Option(year, year));
  for (const id of ['library-search', 'library-topic', 'library-year']) $(id).addEventListener(id === 'library-search' ? 'input' : 'change', () => { libraryLimit = 25; renderLibrary(); });
  $('library-more').addEventListener('click', () => { libraryLimit += 25; renderLibrary(); });
  $('library-export').addEventListener('click', () => download('horizon-lvk-publications.json', JSON.stringify(publications, null, 2), 'application/json'));
  window.addEventListener('horizon:view', event => { activeView = event.detail; if (activeView === 'scientist') { if (!result) calculate(); else drawPlots(); } if (activeView === 'library') renderLibrary(); });
  new ResizeObserver(drawPlots).observe($('scientist-view'));
  const validation = $('science-validation'); validation.append(node('p', '', 'Source coefficients: LALSuite commit ' + S.SOURCE_SHA.slice(0, 12) + '. Independent regression references retain their provenance and model limitations.'));
  const runCheck = node('button', 'button secondary', 'Run numerical self-check'); runCheck.id = 'science-check'; validation.append(runCheck);
  const receipt = node('p', 'help', 'Self-check has not run in this browser session.'); receipt.id = 'science-check-result'; receipt.setAttribute('role', 'status'); validation.append(receipt);
  runCheck.addEventListener('click', () => { runCheck.disabled = true; receipt.textContent = 'Checking coefficients, integrated trajectories, and independent waveform values…'; setTimeout(() => { try { checkResult = S.verifyReferences(window.HORIZON_REFERENCE); receipt.textContent = `${checkResult.pass ? 'PASS' : 'FAIL'} · ${checkResult.waveformBins} independent waveform bins: max complex relative error ${checkResult.waveformRelativeError.toExponential(2)}. ${checkResult.trajectoryCases} integrated trajectories: max relative error ${checkResult.trajectoryRelativeError.toExponential(2)}. Fixture is transformed from an official stored LALSuite vector, not a fresh LAL run.`; } catch (error) { receipt.textContent = 'Verification could not complete: ' + error.message; } finally { runCheck.disabled = false; } }, 0); });
})();
