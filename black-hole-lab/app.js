(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const P = window.BlackHolePhysics;
  const data = window.GWOSC_DATA;
  const fmt = (n, places = 1) => Number.isFinite(n) ? n.toLocaleString('en-US', { maximumFractionDigits: places }) : '—';
  const time = n => n < .01 ? n.toFixed(6) : n.toFixed(3);
  const parameterCache = new WeakMap();
  const parameters = event => {
    if (!parameterCache.has(event)) parameterCache.set(event, Object.fromEntries((event.default_parameters || []).map(p => [p.name, p])));
    return parameterCache.get(event);
  };
  const value = (event, name) => parameters(event)[name]?.best;
  const key = event => `${event.catalog}|${event.shortName}`;
  const usable = event => ['mass_1_source', 'mass_2_source', 'luminosity_distance', 'redshift'].every(name => Number.isFinite(value(event, name)))
    && value(event, 'mass_1_source') >= 3 && value(event, 'mass_2_source') >= 3 && value(event, 'luminosity_distance') > 0 && value(event, 'redshift') >= 0;
  const events = data.events;
  const ready = events.filter(usable);
  const newest = new Map();
  for (const event of ready) if (!newest.has(event.name) || newest.get(event.name).version < event.version) newest.set(event.name, event);
  let selection = newest.get('GW150914') || ready[0];
  let current, progress = 0, playing = false, lastFrame = 0, animation = 0, renderedAt = 0;
  let showGrid = true, showLabels = true, zoom = 1, activeView = 'simulation', catalogLimit = 40;
  let waveform = [];
  let amplitudeScale = 1;
  const colors = { bg: '#090b0e', text: '#f0f2f5', muted: '#adb6c1', grid: '#2b333d', amber: '#f5b567', cyan: '#93d9ed' };
  const controls = { mass1: 'm1', mass2: 'm2', distance: 'distance', inclination: 'inclination', redshift: 'redshift', separation: 'start' };
  const settings = { m1: 36, m2: 29, distance: 410, inclination: 35, redshift: .09, start: 24, approximant: 'TaylorT4' };

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function link(label, url) {
    const node = element('a', '', label);
    const target = new URL(url);
    if (target.protocol !== 'https:') throw Error('Source URL must use HTTPS');
    node.href = target.href; node.target = '_blank'; node.rel = 'noreferrer';
    return node;
  }
  function fillEvents() {
    const select = $('event-select'); select.replaceChildren();
    select.append(new Option('Custom binary / synthetic', 'custom'));
    const popular = ['GW150914', 'GW151226', 'GW170104', 'GW190412', 'GW190521'];
    const sorted = [...newest.values()].sort((a, b) => {
      const pa = popular.includes(a.name) ? popular.indexOf(a.name) : 99;
      const pb = popular.includes(b.name) ? popular.indexOf(b.name) : 99;
      return pa - pb || a.name.localeCompare(b.name);
    });
    for (const event of sorted) select.append(new Option(`${event.name} · ${fmt(value(event, 'mass_1_source'))} + ${fmt(value(event, 'mass_2_source'))} M☉`, key(event)));
  }
  function pause() {
    playing = false; cancelAnimationFrame(animation); $('play').textContent = progress >= 1 ? 'Replay merger' : 'Play merger';
    $('play-state').textContent = progress >= 1 ? 'Complete' : 'Paused';
  }
  function applyEvent(event) {
    if (!event || !usable(event)) return;
    selection = event;
    if (![...$('event-select').options].some(option => option.value === key(event))) $('event-select').append(new Option(`${event.name} · v${event.version} · ${event.catalog}`, key(event)));
    $('event-select').value = key(event);
    settings.m1 = value(event, 'mass_1_source'); settings.m2 = value(event, 'mass_2_source');
    settings.distance = value(event, 'luminosity_distance'); settings.redshift = value(event, 'redshift');
    rebuild();
  }
  function rebuild() {
    progress = 0; pause();
    current = P.model({ ...settings, finalMass: selection ? value(selection, 'final_mass_source') : null });
    for (const [id, name] of Object.entries(controls)) {
      const control = $(id);
      control.max = Math.max(Number(control.max), settings[name]);
      control.value = settings[name];
    }
    updateOutputs();
    $('model-boundary').textContent = `${settings.approximant === 'TaylorT4' ? 'TaylorT4 3.5PN' : 'Leading-order'} circular, nonspinning inspiral. Merger is illustrative; ringdown uses published fits.`;
    $('source-kind').textContent = selection ? 'CATALOG' : 'SYNTHETIC';
    $('event-title').textContent = selection ? `${selection.name} / v${selection.version}` : settings.m1 < 1 && settings.m2 < 1 ? 'Subsolar thought experiment' : 'Custom binary';
    $('remnant-kind').textContent = current.hasFinalMass ? 'catalog' : 'fit';
    $('chirp-mass').textContent = fmt(current.chirp, 2); $('remnant-mass').textContent = fmt(current.finalMass, 2);
    $('total-time').textContent = `${time(current.totalTime)} s`;
    if (selection) {
      const chi = value(selection, 'chi_eff');
      $('event-help').textContent = `${selection.catalog} · v${selection.version}. Catalog χeff = ${fmt(chi, 2)}; component spin dynamics are not modeled.`;
      const p = parameters(selection);
      const uncertainty = name => p[name] && Number.isFinite(p[name].lower_error) && Number.isFinite(p[name].upper_error)
        ? `${fmt(p[name].best)} (${fmt(p[name].lower_error)} / +${fmt(p[name].upper_error)}) M☉` : `${fmt(p[name]?.best)} M☉ (interval unavailable)`;
      $('selection-note').textContent = `Published mass summaries: ${uncertainty('mass_1_source')} and ${uncertainty('mass_2_source')}. Separate medians are not a joint posterior draw. Inclination ${settings.inclination}° is assumed. ${/marginal|auxiliary/i.test(selection.catalog) ? 'This record is a marginal/auxiliary candidate, not a confirmed detection. ' : ''}${current.fitExtrapolated ? 'Mass ratio exceeds 6: remnant fits are extrapolated.' : 'Nonspinning remnant spin fit: ' + fmt(current.spin, 3) + '.'}`;
    } else {
      $('event-help').textContent = 'Synthetic parameters. This system is not claimed to be an observed event.';
      $('selection-note').textContent = `Synthetic binary. Component spins fixed to zero; inclination is assumed. Distance and redshift are independent controls, with no cosmology enforced. ${current.fitExtrapolated ? 'Mass ratio exceeds 6: the remnant fit is extrapolated beyond its numerical calibration.' : 'Remnant mass and spin use the published nonspinning fit.'}`;
    }
    const samples = Math.min(65536, Math.max(2048, Math.ceil(current.totalTime * current.ringFrequency * 2.5)));
    waveform = Array.from({ length: samples + 1 }, (_, i) => current.atTime(current.totalTime * i / samples));
    amplitudeScale = waveform.reduce((max, sample) => Math.max(max, sample.amplitude), 0) * 1.08;
    $('timeline').value = '0'; render();
  }
  function updateOutputs() {
    $('mass1-value').textContent = `${fmt(settings.m1)} M☉`; $('mass2-value').textContent = `${fmt(settings.m2)} M☉`;
    $('distance-value').textContent = `${fmt(settings.distance)} Mpc`; $('inclination-value').textContent = `${fmt(settings.inclination)}°`;
    $('redshift-value').textContent = fmt(settings.redshift, 3); $('separation-value').textContent = `${fmt(settings.start)} GM/c²`;
    $('replay-value').textContent = `${$('replay').value} s`; $('azimuth-value').textContent = `${$('azimuth').value}°`;
  }
  function frame(now) {
    if (!playing) return;
    const delta = lastFrame ? Math.min((now - lastFrame) / 1000, .1) : 0; lastFrame = now;
    progress = Math.min(1, progress + delta / Number($('replay').value));
    if (now - renderedAt >= 30 || progress >= 1) { render(); renderedAt = now; }
    if (progress >= 1) pause(); else animation = requestAnimationFrame(frame);
  }
  function render() {
    if (!current || activeView !== 'simulation') return;
    const state = current.atProgress(progress);
    $('stage').textContent = state.stage.toUpperCase();
    $('stage-detail').textContent = state.stage === 'Inspiral' ? 'Orbital energy radiates away as gravitational waves.' : state.stage === 'Merger illustration' ? 'Strong-field coalescence: an illustrative bridge.' : 'A single remnant settles through a damped oscillation.';
    $('frequency').textContent = fmt(state.frequency, 1);
    $('separation-km').textContent = state.stage === 'Inspiral' ? fmt(state.separation / 1000, 0) : '—';
    $('physical-time').textContent = `${time(state.t)} s`;
    $('timeline').value = String(Math.round(progress * 1000));
    drawSpace(state); drawWave(state);
  }
  function context(canvas) {
    const rect = canvas.getBoundingClientRect();
    const ratio = Math.min(devicePixelRatio || 1, 2);
    const w = Math.max(1, Math.round(rect.width)), h = Math.max(1, Math.round(rect.height));
    if (canvas.width !== Math.round(w * ratio) || canvas.height !== Math.round(h * ratio)) { canvas.width = Math.round(w * ratio); canvas.height = Math.round(h * ratio); }
    const ctx = canvas.getContext('2d'); ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, w, h);
    return { ctx, w, h };
  }
  let seed = 3021;
  const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
  const stars = Array.from({ length: 260 }, () => [random(), random(), random(), random()]);
  function drawSpace(state) {
    const { ctx, w, h } = context($('space'));
    ctx.fillStyle = colors.bg; ctx.fillRect(0, 0, w, h);
    const cx = w * .5, cy = h * .56;
    const scale = Math.min(w * .69, h * 1.12) / current.start * zoom;
    const tilt = Math.cos(settings.inclination * Math.PI / 180), yaw = Number($('azimuth').value) * Math.PI / 180 + .35;
    const project = (x, y, z = 0) => [cx + (x * Math.cos(yaw) - y * Math.sin(yaw)) * scale, cy + (x * Math.sin(yaw) + y * Math.cos(yaw)) * scale * tilt + z * scale * Math.sin(settings.inclination * Math.PI / 180)];
    const atmosphere = ctx.createRadialGradient(cx, cy, 0, cx, cy, w * .6);
    atmosphere.addColorStop(0, '#f5b56708'); atmosphere.addColorStop(.5, '#9e662f05'); atmosphere.addColorStop(1, '#090b0e00');
    ctx.fillStyle = atmosphere; ctx.fillRect(0, 0, w, h);
    for (const [x, y, size, bright] of stars) { ctx.fillStyle = `rgba(173,182,193,${.12 + bright * .45})`; ctx.fillRect(x * w, y * h, .5 + size, .5 + size); }
    const angle = state.phase;
    const b1 = [Math.cos(angle) * state.x * current.m2 / current.mass, Math.sin(angle) * state.x * current.m2 / current.mass];
    const b2 = [-Math.cos(angle) * state.x * current.m1 / current.mass, -Math.sin(angle) * state.x * current.m1 / current.mass];
    if (showGrid) {
      ctx.lineWidth = .6;
      const extent = current.start * 1.1;
      const well = (x, y) => 1.1 * (current.m1 / current.mass / Math.sqrt((x - b1[0]) ** 2 + (y - b1[1]) ** 2 + .45) + current.m2 / current.mass / Math.sqrt((x - b2[0]) ** 2 + (y - b2[1]) ** 2 + .45));
      for (let axis = 0; axis < 2; axis++) for (let i = -15; i <= 15; i++) {
        ctx.beginPath(); ctx.strokeStyle = i === 0 ? '#f5b56730' : '#adb6c11c';
        for (let j = 0; j <= 65; j++) {
          const a = i / 15 * extent, b = (j / 65 * 2 - 1) * extent;
          const x = axis ? a : b, y = axis ? b : a;
          const [px, py] = project(x, y, well(x, y) * 6);
          j ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
        }
        ctx.stroke();
      }
    }
    ctx.strokeStyle = '#f5b56726'; ctx.setLineDash([3, 6]); ctx.lineWidth = 1;
    if (state.stage === 'Inspiral') for (const orbit of [state.x * current.m2 / current.mass, state.x * current.m1 / current.mass]) {
      ctx.beginPath();
      for (let i = 0; i <= 100; i++) { const a = i / 100 * Math.PI * 2; const p = project(Math.cos(a) * orbit, Math.sin(a) * orbit); i ? ctx.lineTo(...p) : ctx.moveTo(...p); }
      ctx.stroke();
    }
    ctx.setLineDash([]);
    for (let ring = 0; ring < 7; ring++) {
      const r = (ring * 3.1 + state.phase * .26 % 3.1 + 3) * scale;
      const opacity = .09 * (1 - ring / 8) * (state.stage === 'Fitted ringdown' ? Math.exp(-(state.t - current.inspiralTime - current.bridgeTime) / (4 * current.damping)) : 1);
      ctx.strokeStyle = `rgba(245,181,103,${opacity})`; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.ellipse(cx, cy, r, Math.max(2, r * .55), 0, 0, Math.PI * 2); ctx.stroke();
    }
    const remnantBlend = state.blend > .45 ? (state.blend - .45) / .55 : 0;
    const holes = [
      { p: project(...b1), radius: current.horizon1 / current.rg * scale, name: 'PRIMARY', mass: current.m1 },
      { p: project(...b2), radius: current.horizon2 / current.rg * scale, name: 'SECONDARY', mass: current.m2 },
    ].sort((a, b) => a.p[1] - b.p[1]);
    for (const hole of holes) if (remnantBlend < 1) drawHole(ctx, hole.p[0], hole.p[1], hole.radius, 1 - remnantBlend, state.phase);
    if (remnantBlend > 0) {
      const radius = (1 + Math.sqrt(1 - current.spin ** 2)) * current.finalMass / current.mass * scale;
      drawHole(ctx, cx, cy, radius, remnantBlend, state.phase);
      if (showLabels && remnantBlend > .85) label(ctx, cx + radius * 2, cy - radius * 2, 'REMNANT', `${fmt(current.finalMass, 1)} M☉ · χfit ${fmt(current.spin, 3)}`, w);
    } else if (showLabels) {
      for (const hole of holes) label(ctx, hole.p[0] + hole.radius * 1.8, hole.p[1] - hole.radius * 2.2, hole.name, `${fmt(hole.mass)} M☉`, w);
      ctx.strokeStyle = '#adb6c177'; ctx.beginPath();ctx.moveTo(cx - 5, cy);ctx.lineTo(cx + 5, cy);ctx.moveTo(cx, cy - 5);ctx.lineTo(cx, cy + 5);ctx.stroke();
    }
    const barPixels = Math.min(100, w * .2), barKm = barPixels / scale * current.rg / 1000;
    ctx.strokeStyle = colors.muted; ctx.lineWidth = 1; ctx.beginPath();ctx.moveTo(w - 20 - barPixels,h - 40);ctx.lineTo(w - 20,h - 40);ctx.stroke();
    $('scale-caption').textContent = `${fmt(barKm, barKm < 10 ? 2 : 0)} km · source frame`;
  }
  function drawHole(ctx, x, y, radius, alpha, phase) {
    const r = Math.max(.45, radius);
    ctx.save(); ctx.globalAlpha = alpha;
    const halo = ctx.createRadialGradient(x, y, r * .9, x, y, r * 6);
    halo.addColorStop(0, '#ffd397e0'); halo.addColorStop(.08, '#f5b56790');halo.addColorStop(.18, '#9e662f55');halo.addColorStop(.5, '#63381816');halo.addColorStop(1, '#63381800');
    ctx.fillStyle = halo; ctx.fillRect(x - r * 6, y - r * 6, r * 12, r * 12);
    for (let ring = 12; ring >= 1; ring--) {
      ctx.strokeStyle = `rgba(245,181,103,${.025 + .22 * (1 - ring / 13)})`;ctx.lineWidth = ring === 1 ? 1.8 : .6;
      ctx.beginPath();ctx.ellipse(x,y,r*(1+.12*ring),r*(1+.10*ring),-.18,0,Math.PI*2);ctx.stroke();
    }
    ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fillStyle='#000000';ctx.fill();
    const rim = ctx.createLinearGradient(x-r,y-r,x+r,y+r);rim.addColorStop(0,'#ffd397');rim.addColorStop(.45,'#f5b567');rim.addColorStop(1,'#633818');
    ctx.strokeStyle=rim;ctx.lineWidth=Math.max(1,r*.045);ctx.stroke();
    ctx.strokeStyle='#ffd397';ctx.globalAlpha=alpha*.6;ctx.lineWidth=.7;ctx.beginPath();ctx.arc(x,y,r*1.13,phase*.02,phase*.02+Math.PI*.7);ctx.stroke();
    ctx.restore();
  }
  function label(ctx,x,y,title,detail,w){
    x=Math.max(12,Math.min(w-150,x));y=Math.max(86,y);
    ctx.fillStyle=colors.muted;ctx.font='10px Consolas,monospace';ctx.fillText(title,x,y);
    ctx.fillStyle=colors.text;ctx.font='13px Consolas,monospace';ctx.fillText(detail,x,y+19);
  }
  function drawWave(state) {
    const {ctx,w,h}=context($('wave'));const left=48,right=w-12,top=24,bottom=h-28,mid=(top+bottom)/2;
    const start=$('wave-window').value==='end'?Math.max(0,current.inspiralTime-150*current.timeUnit):0;
    const duration=current.totalTime-start;
    const max=amplitudeScale;
    ctx.font='11px Consolas,monospace';ctx.lineWidth=.7;
    const divisions=w<450?2:4;
    for(let i=0;i<=divisions;i++){const x=left+(right-left)*i/divisions;ctx.strokeStyle=colors.grid;ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,bottom);ctx.stroke();ctx.fillStyle=colors.muted;ctx.fillText(time(start+duration*i/divisions),Math.min(right-48,x-12),h-5);}
    ctx.strokeStyle=colors.grid;ctx.beginPath();ctx.moveTo(left,mid);ctx.lineTo(right,mid);ctx.stroke();
    ctx.fillStyle=colors.muted;ctx.fillText('h+ (×10⁻²¹)',0,12);ctx.fillText((max*1e21).toPrecision(2),0,top+4);ctx.fillText('0',18,mid+4);ctx.fillText('−'+(max*1e21).toPrecision(2),0,bottom);
    const boundary=left+(right-left)*(current.inspiralTime-start)/duration;
    ctx.fillStyle='#93d9ed0d';ctx.fillRect(boundary,top,right-boundary,bottom-top);
    for(const stage of [0,1]){
      ctx.beginPath();ctx.strokeStyle=stage?colors.cyan:colors.amber;ctx.lineWidth=1.15;let first=true;
      const plotSamples=$('wave-window').value==='end'?Array.from({length:2001},(_,i)=>current.atTime(start+duration*i/2000)):waveform;
      for(const sample of plotSamples){if(sample.t<start||(sample.t>current.inspiralTime)!==Boolean(stage))continue;
        const x=left+(sample.t-start)/duration*(right-left),y=mid-sample.plus/max*(bottom-top)/2;
        first?ctx.moveTo(x,y):ctx.lineTo(x,y);first=false;
      }ctx.stroke();
    }
    if(state.t>=start){const x=left+(state.t-start)/duration*(right-left);ctx.strokeStyle='#f0f2f599';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,bottom);ctx.stroke();}
    $('strain-caption').textContent=`Modeled h+ · current ${state.plus.toExponential(2)}`;
  }
  function drawObserved(){
    const observed=window.GW150914_OBSERVED;if(!observed){$('observed-caption').textContent='Observed series unavailable in this copy. Open the official source below.';return;}
    const {ctx,w,h}=context($('observed'));const left=36,right=w-12,top=20,bottom=h-32,mid=(top+bottom)/2;
    const samples=observed.samples;const start=samples[0][0],end=samples.at(-1)[0];
    ctx.font='11px Consolas,monospace';ctx.fillStyle=colors.muted;ctx.fillText('h × 10²¹',0,12);
    for(let i=-1;i<=1;i++){const y=mid-i*(bottom-top)/3;ctx.strokeStyle=colors.grid;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();ctx.fillText(String(i),12,y+4);}
    ctx.beginPath();ctx.lineWidth=1.2;ctx.strokeStyle=colors.cyan;
    samples.forEach(([t,strain],i)=>{const x=left+(t-start)/(end-start)*(right-left),y=mid-strain*(bottom-top)/3;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.stroke();
    for(let i=0;i<=3;i++)ctx.fillText((start+(end-start)*i/3).toFixed(2)+' s',left+(right-left)*i/3-12,h-8);
    $('observed-caption').textContent=`${samples.length.toLocaleString()} measured samples, including detector noise. Published 35–350 Hz bandpass and instrumental-line rejection. Time since 2015-09-14 09:50:45 UTC. This is separate from the model.`;
  }
  function setView(view){
    pause();activeView=view;
    for(const name of ['simulation','scientist','catalog','library','research'])$(name+'-view').hidden=name!==view;
    document.querySelectorAll('[data-view]').forEach(button=>{const active=button.dataset.view===view;button.classList.toggle('selected',active);button.setAttribute('aria-pressed',String(active));});
    if(view==='simulation')render();if(view==='catalog')renderCatalog();if(view==='research')drawObserved();
    window.dispatchEvent(new CustomEvent('horizon:view',{detail:view}));
  }
  function renderCatalog(){
    const query=$('catalog-search').value.trim().toLowerCase(),filter=$('catalog-filter').value,only=$('eligible-only').checked;
    const rows=events.filter(e=>(!query||`${e.name} ${e.catalog} ${e.shortName}`.toLowerCase().includes(query))&&(!filter||e.catalog===filter)&&(!only||usable(e)));
    $('catalog-count').textContent=`${rows.length.toLocaleString()} records`;
    const fragment=document.createDocumentFragment();
    for(const event of rows.slice(0,catalogLimit)){
      const row=element('article','event-row');const title=element('div');title.append(element('h3','',event.name),element('small','',`${event.catalog} · v${event.version}`));
      const masses=element('div');masses.append(element('p','mass-pair',`${fmt(value(event,'mass_1_source'))} + ${fmt(value(event,'mass_2_source'))}`),element('small','','Source-frame solar masses'));
      const evidence=element('div');const far=parameters(event).far;
      const farText=far?.best==null?'unavailable':`${far.is_upper_limit?'≤ ':far.is_lower_limit?'≥ ':''}${far.best.toExponential(1)} yr⁻¹`;
      evidence.append(element('p','',`SNR ${fmt(value(event,'network_matched_filter_snr'))} · ${fmt(value(event,'luminosity_distance'))} Mpc`),element('small','',`FAR ${farText} · χeff ${fmt(value(event,'chi_eff'),2)}`));
      const actions=element('div','event-actions');const simulate=element('button','button secondary',usable(event)?'Simulate':'Unavailable');simulate.disabled=!usable(event);simulate.setAttribute('aria-label',`Simulate ${event.shortName} from ${event.catalog}`);simulate.addEventListener('click',()=>{applyEvent(event);setView('simulation');$('simulation-title').scrollIntoView({block:'start'});});
      actions.append(simulate,link('Source',event.detail_url));row.append(title,masses,evidence,actions);fragment.append(row);
    }
    if(!rows.length)fragment.append(element('p','empty-state','No records match. Clear the search or choose another catalog.'));
    $('catalog-list').replaceChildren(fragment);$('more-events').hidden=rows.length<=catalogLimit;
  }
  function research(){
    const count=data.counts;
    $('catalog-summary').textContent=`${count.versions} event versions · ${count.events} named events · ${count.catalogs} catalogs · ${ready.length} model-ready versions. Snapshot ${data.retrievedAt.slice(0,10)}.`;
    $('coverage-detail').textContent=`The offline snapshot includes all ${count.versions} event-version default-parameter records returned by GWOSC across ${count.pages} verified pages at ${data.retrievedAt}, representing ${count.events} named events. It also includes ${count.catalogs} catalog indexes, ${count.runs} observing-run indexes, and the 3,441 published GW150914 Hanford figure-data samples. Missing parameters remain missing; older versions and marginal candidates are retained.`;
    const uniqueCatalogs=[...new Set(events.map(e=>e.catalog))].sort();for(const name of uniqueCatalogs)$('catalog-filter').append(new Option(name,name));
    for(const source of [...data.catalogs,...data.runs])$('source-index').append(link(source.name,source.detail_url));
    for(const pub of window.WOLFE_RESEARCH||[]){
      const details=element('details','publication');const summary=element('summary');const title=element('div');title.append(element('strong','',pub.title),element('span','pub-status',pub.status));summary.append(element('span','pub-year',String(pub.year)),title);
      const body=element('div','pub-body');body.append(element('p','',pub.relevance),element('p','',pub.limit),link('Read the paper',pub.url));if(pub.journalUrl)body.append(document.createTextNode(' · '),link('Journal publication',pub.journalUrl));details.append(summary,body);$('publication-list').append(details);
    }
  }
  fillEvents();research();$('snapshot-date').textContent=data.retrievedAt.slice(0,10);
  for(const [id,name] of Object.entries(controls))$(id).addEventListener('input',()=>{
    settings[name]=Number($(id).value);
    if(['m1','m2','distance','redshift'].includes(name)){selection=null;$('event-select').value='custom';}
    rebuild();
  });
  $('event-select').addEventListener('change',()=>{if($('event-select').value==='custom'){selection=null;rebuild();}else applyEvent(events.find(e=>key(e)===$('event-select').value));});
  $('first-event').addEventListener('click',()=>applyEvent(newest.get('GW150914')));
  $('subsolar').addEventListener('click',()=>{selection=null;Object.assign(settings,{m1:.5,m2:.3,distance:10,redshift:0});$('event-select').value='custom';rebuild();});
  $('play').addEventListener('click',()=>{if(playing){pause();return;}if(progress>=1)progress=0;playing=true;lastFrame=0;$('play').textContent='Pause';$('play-state').textContent='Playing';animation=requestAnimationFrame(frame);});
  $('reset').addEventListener('click',()=>{progress=0;pause();render();});
  $('timeline').addEventListener('input',()=>{progress=Number($('timeline').value)/1000;pause();render();});
  $('wave-window').addEventListener('change',render);
  $('radiation-model').addEventListener('change',()=>{settings.approximant=$('radiation-model').value;rebuild();});
  $('replay').addEventListener('input',updateOutputs);$('azimuth').addEventListener('input',()=>{updateOutputs();render();});
  $('grid-toggle').addEventListener('click',()=>{showGrid=!showGrid;$('grid-toggle').setAttribute('aria-pressed',String(showGrid));render();});
  $('labels-toggle').addEventListener('click',()=>{showLabels=!showLabels;$('labels-toggle').setAttribute('aria-pressed',String(showLabels));render();});
  $('zoom-in').addEventListener('click',()=>{zoom=P.clamp(zoom*1.2,.5,2);render();});$('zoom-out').addEventListener('click',()=>{zoom=P.clamp(zoom/1.2,.5,2);render();});
  document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>setView(button.dataset.view)));
  document.querySelectorAll('[data-go]').forEach(button=>button.addEventListener('click',()=>{setView(button.dataset.go);$('research-title').scrollIntoView({block:'start'});}));
  for(const id of ['catalog-search','catalog-filter','eligible-only'])$(id).addEventListener(id==='catalog-search'?'input':'change',()=>{catalogLimit=40;renderCatalog();});
  $('more-events').addEventListener('click',()=>{catalogLimit+=40;renderCatalog();});
  $('export').addEventListener('click',()=>{
    const sampleCount=Math.min(65536,Math.max(4096,Math.ceil(current.totalTime*current.ringFrequency*12)));
    const exportedSamples=Array.from({length:sampleCount+1},(_,i)=>current.atTime(current.totalTime*i/sampleCount));
    const payload={model:`${settings.approximant === 'TaylorT4' ? 'TaylorT4 3.5PN' : 'Newtonian/quadrupole'} circular nonspinning inspiral; illustrative merger bridge; Pan nonspinning remnant fit and Berti220 ringdown`,limitations:'Not numerical relativity or observed strain. Nonuniform visual replay; exported time uniformly sampled in observer seconds. Sampling is capped for browser memory; inspect sampling metadata before waveform analysis. TaylorT4 separation is a Newtonian-equivalent frequency coordinate, not a relativistic proper distance.',sampling:{samples:sampleCount+1,observerStepSeconds:current.totalTime/sampleCount,nyquistHz:sampleCount/(2*current.totalTime),maximumModeledFrequencyHz:current.ringFrequency,undersampled:sampleCount/(2*current.totalTime)<current.ringFrequency},parameters:{...settings},event:selection,snapshot:data.retrievedAt,remnant:{mass:current.finalMass,spin:current.spin,massSource:current.hasFinalMass?'catalog':'fit',fitExtrapolated:current.fitExtrapolated},samples:exportedSamples.map(s=>({observerSeconds:s.t,sourceSeconds:s.sourceTime,hPlus:s.plus,hCross:s.cross,frequencyHz:s.frequency,separationM:s.stage==='Inspiral'?s.separation:null,stage:s.stage}))};
    const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));const anchor=element('a');anchor.href=url;anchor.download='horizon-model.json';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();});
  new ResizeObserver(()=>{if(activeView==='research')drawObserved();else render();}).observe($('main'));
  applyEvent(selection);
  window.HorizonLab = { getSettings: () => ({ ...settings }), getEvent: () => selection, setView };
})();
