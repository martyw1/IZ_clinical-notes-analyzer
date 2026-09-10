(() => {
  'use strict';
  function attachChart(canvas, options) {
    let range = null, dragging = null, pinch = null;
    const pointers = new Map(), toAxis = options.logX ? Math.log10 : value => value, fromAxis = options.logX ? value => 10 ** value : value => value;
    canvas.tabIndex = 0; canvas.style.touchAction = 'none';
    const controls = document.createElement('div'); controls.className = 'plot-navigation'; controls.setAttribute('role', 'group'); controls.setAttribute('aria-label', options.label + ' navigation');
    const readout = document.createElement('p'); readout.className = 'plot-readout'; readout.id = canvas.id + '-navigation';
    readout.textContent = 'Drag to pan · wheel or pinch to zoom · arrows and +/− when focused.'; canvas.setAttribute('aria-describedby', readout.id);
    canvas.after(controls, readout);
    function bounds() { const values = options.bounds(); return values && values[1] > values[0] ? values.map(toAxis) : [0, 1]; }
    function axisDomain() { const full = bounds(); return range && range[0] >= full[0] && range[1] <= full[1] ? range : full; }
    function fraction(clientX) { const box = canvas.getBoundingClientRect(); return Math.max(0, Math.min(1, (clientX - box.left - options.left) / Math.max(1, box.width - options.left - 20))); }
    function update(next) {
      const full = bounds(), span = Math.min(full[1] - full[0], Math.max((full[1] - full[0]) / 1e6, next[1] - next[0]));
      const low = Math.max(full[0], Math.min(full[1] - span, next[0])); range = [low, low + span]; options.change();
    }
    function zoom(factor, anchor = .5) { const [lo, hi] = axisDomain(), center = lo + (hi - lo) * anchor, span = (hi - lo) * factor; update([center - span * anchor, center + span * (1 - anchor)]); }
    function pan(fraction) { const [lo, hi] = axisDomain(), shift = (hi - lo) * fraction; update([lo + shift, hi + shift]); }
    function reset(notify = true) { range = null; if (notify) options.change(); }
    for (const [text, name, action] of [['−', 'Zoom out', () => zoom(1.5)], ['+', 'Zoom in', () => zoom(1 / 1.5)], ['←', 'Pan left', () => pan(-.2)], ['→', 'Pan right', () => pan(.2)], ['Reset view', 'Reset view', () => reset()]]) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'small-button'; button.textContent = text; button.setAttribute('aria-label', options.label + ': ' + name); button.addEventListener('click', action); controls.append(button);
    }
    canvas.addEventListener('wheel', event => { if (event.ctrlKey) return; event.preventDefault(); zoom(Math.exp(Math.max(-1, Math.min(1, event.deltaY * .002))), fraction(event.clientX)); }, { passive: false });
    canvas.addEventListener('pointerdown', event => {
      if (event.button !== 0) return; canvas.focus({ preventScroll: true }); canvas.setPointerCapture(event.pointerId); pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      dragging = { x: event.clientX, range: [...axisDomain()] }; pinch = null;
    });
    canvas.addEventListener('pointermove', event => {
      if (pointers.has(event.pointerId)) {
        pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
        if (pointers.size === 2) {
          const [a, b] = [...pointers.values()], distance = Math.hypot(a.x - b.x, a.y - b.y), center = fraction((a.x + b.x) / 2);
          if (pinch && distance > 0) zoom(pinch.distance / distance, center); pinch = { distance }; dragging = null;
        } else if (dragging) { const width = Math.max(1, canvas.getBoundingClientRect().width - options.left - 20), shift = -(event.clientX - dragging.x) / width * (dragging.range[1] - dragging.range[0]); update(dragging.range.map(value => value + shift)); }
      }
      const [lo, hi] = axisDomain(), value = fromAxis(lo + fraction(event.clientX) * (hi - lo)); readout.textContent = options.describe(value);
    });
    const end = event => { pointers.delete(event.pointerId); dragging = null; pinch = null; };
    canvas.addEventListener('pointerup', end); canvas.addEventListener('pointercancel', end); canvas.addEventListener('lostpointercapture', end);
    canvas.addEventListener('keydown', event => {
      const actions = { ArrowLeft: () => pan(-.1), ArrowRight: () => pan(.1), ArrowUp: () => zoom(1 / 1.25), ArrowDown: () => zoom(1.25), '+': () => zoom(1 / 1.25), '=': () => zoom(1 / 1.25), '-': () => zoom(1.25), Home: () => reset() };
      if (actions[event.key]) { event.preventDefault(); actions[event.key](); const [lo, hi] = axisDomain(); readout.textContent = options.describe(fromAxis((lo + hi) / 2)); }
    });
    return { domain: () => axisDomain().map(fromAxis), reset };
  }
  window.HorizonNavigation = { attachChart };
})();
