(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const { createSim, MEMBERS_PER_PAGE } = window.PgHotRowSim;

  function el(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function h(tag, attrs, parent, text) {
    const e = document.createElement(tag);
    for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  function txt(parent, x, y, s, attrs) {
    const t = el('text', Object.assign({ x, y }, attrs || {}), parent);
    t.textContent = s;
    return t;
  }
  const fmt = n => (n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e4 ? Math.round(n / 1e3) + 'k' : n >= 1e3 ? (n / 1e3).toFixed(1) + 'k' : String(Math.round(n)));
  const fmtS = s => (s >= 1 ? s.toFixed(1) + ' s' : Math.round(s * 1000) + ' ms');

  function slider(parent, label, min, max, step, value, onInput, show) {
    const wrap = h('label', { class: 'phr-ctl' }, parent);
    const head = h('span', {}, wrap, label + ' ');
    const out = h('output', {}, head);
    const input = h('input', { type: 'range', min, max, step, value }, wrap);
    const sync = () => { out.textContent = show ? show(+input.value) : input.value; };
    input.addEventListener('input', () => { sync(); onInput(+input.value); });
    sync();
    return { input, set(v) { input.value = v; sync(); } };
  }

  function segmented(parent, label, options, value, onPick) {
    const wrap = h('div', { class: 'phr-ctl' }, parent);
    h('span', {}, wrap, label);
    const seg = h('div', { class: 'phr-seg', role: 'group', 'aria-label': label }, wrap);
    const buttons = options.map(([v, name]) => {
      const b = h('button', { type: 'button', 'aria-pressed': String(v === value) }, seg, name);
      b.addEventListener('click', () => { pick(v); onPick(v); });
      return [v, b];
    });
    function pick(v) { for (const [bv, b] of buttons) b.setAttribute('aria-pressed', String(bv === v)); }
    return { set: pick };
  }

  // ---------------------------------------------------------------
  // Widget 1: every new locker copies the member list
  // ---------------------------------------------------------------

  function multixactWidget(fig) {
    const panel = h('div', { class: 'phr-panel' });
    fig.prepend(panel);
    const controls = h('div', { class: 'phr-controls' }, panel);
    let n = 6, timer = null;

    const svg = el('svg', { viewBox: '0 0 640 250', role: 'img', 'aria-label': 'MultiXacts created as transactions lock the same row' }, panel);
    const stats = h('div', { class: 'phr-stats' }, panel);
    const note = h('p', { class: 'phr-note' }, panel);

    const s = slider(controls, 'Transactions holding KEY SHARE', 1, 40, 1, n, v => { stop(); n = v; draw(); });
    const play = h('button', { type: 'button', class: 'phr-btn' }, controls, 'Play');
    play.addEventListener('click', () => {
      if (timer) return stop();
      if (n >= 40) n = 0;
      play.textContent = 'Stop';
      timer = setInterval(() => {
        n++; s.set(n); draw();
        if (n >= 40) stop();
      }, 350);
    });
    function stop() { clearInterval(timer); timer = null; play.textContent = 'Play'; }

    const g = el('g', {}, svg);
    const tiles = ['MultiXacts created', 'Members written', 'In the newest one'].map(label => {
      const d = h('div', { class: 'phr-stat' }, stats);
      const b = h('b', {}, d, '0');
      h('small', {}, d, label);
      return b;
    });

    function draw() {
      g.replaceChildren();
      const box = el('g', {}, g);
      el('rect', { x: 8, y: 20, width: 160, height: 74, rx: 6, class: 'phr-box' }, box);
      txt(box, 20, 42, 'Parent row', { class: 'phr-t-strong' });
      txt(box, 20, 62, n === 1 ? 'xmax = txn 1' : `xmax = MultiXact #${n}`, { class: 'phr-t' });
      txt(box, 20, 80, `${n} lock holder${n === 1 ? '' : 's'}`, { class: 'phr-t-dim' });

      const x0 = 200, w = 430, top = 20, avail = 205;
      const rowH = Math.min(26, avail / n), cw = Math.min(36, w / n);
      if (n > 1) {
        el('path', { d: `M168 57 C 184 57, 184 ${top + (n - 1) * rowH + rowH / 2}, ${x0 - 4} ${top + (n - 1) * rowH + rowH / 2}`, class: 'phr-arrow', 'marker-end': 'url(#phr-mx-arrow)' }, g);
      }
      for (let i = 1; i <= n; i++) {
        const y = top + (i - 1) * rowH;
        const newest = i === n;
        for (let j = 0; j < i; j++) {
          el('rect', {
            x: x0 + j * cw, y, width: Math.max(cw - 1, 0.6), height: Math.max(rowH - 1, 0.6),
            class: newest ? (j === i - 1 ? 'phr-cell-new' : 'phr-cell-copy') : 'phr-cell-old',
          }, g);
        }
      }
      txt(g, 8, 244, 'Each row is one MultiXact. Each cell is one member transaction ID in pg_multixact.', { class: 'phr-t-dim' });

      const total = (n * (n + 1)) / 2;
      tiles[0].textContent = n === 1 ? '0' : fmt(n);
      tiles[1].textContent = n === 1 ? '0' : fmt(total);
      tiles[2].textContent = n === 1 ? '—' : fmt(n);
      note.innerHTML = n === 1
        ? 'With one locker the row header just holds that transaction ID. The second locker forces a MultiXact.'
        : `The newest MultiXact (bottom row) copies every existing member and adds one. Older rows are no longer in <code>xmax</code> but stay in <code>pg_multixact</code> until no running transaction can need them. At 100 lockers that is <b>5,050</b> members; at 200 it is <b>20,100</b>. The PG15 member cache holds 16 pages × 1,636 = <b>26,176</b> members.`;
    }

    const defs = el('defs', {}, svg);
    const m = el('marker', { id: 'phr-mx-arrow', viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: 'auto' }, defs);
    el('path', { d: 'M0 0 L10 5 L0 10 z', class: 'phr-arrowhead' }, m);
    draw();
  }

  // ---------------------------------------------------------------
  // Widget 2: the simulation
  // ---------------------------------------------------------------

  const STATES = [
    ['cold', 'other rows'],
    ['fk', 'FK lock + MultiXact'],
    ['rowwait', 'waiting on hot row'],
    ['hold', 'holding hot row'],
    ['backoff', 'retry backoff'],
    ['noconn', 'no DB connection'],
    ['idle', 'idle'],
  ];

  const PRESETS = {
    before: { label: 'One queue', p: { concA: 100, concB: 0, hotShare: 0.75, lockTimeoutMs: 0, slruBuffers: 16, apiRate: 250, maxConnections: 1000 }, pin: false },
    after: { label: 'Two queues', p: { concA: 100, concB: 100, hotShare: 0.75, lockTimeoutMs: 0, slruBuffers: 16, apiRate: 250, maxConnections: 1000 }, pin: false },
    incident: { label: 'Two queues + long txn', p: { concA: 100, concB: 100, hotShare: 0.75, lockTimeoutMs: 0, slruBuffers: 16, apiRate: 250, maxConnections: 1000 }, pin: true },
  };

  const HISTORY_S = 90, SAMPLE_S = 0.5, N_SAMPLES = HISTORY_S / SAMPLE_S;

  function simWidget(fig) {
    let sim, history, speed = 2, running = true, visible = false, lastFrame = 0, nextSample = SAMPLE_S, lastWin = null;
    const params = Object.assign({}, PRESETS.before.p);

    const panel = h('div', { class: 'phr-panel' });
    fig.prepend(panel);

    const presetRow = h('div', { class: 'phr-controls' }, panel);
    const preset = segmented(presetRow, 'Start from', Object.entries(PRESETS).map(([k, v]) => [k, v.label]), 'before', k => loadPreset(k));
    const actions = h('div', { class: 'phr-ctl' }, presetRow);
    h('span', {}, actions, 'Actions');
    const actRow = h('div', { class: 'phr-actions' }, actions);
    const pinBtn = h('button', { type: 'button', class: 'phr-btn' }, actRow, 'Open long txn');
    const pauseBtn = h('button', { type: 'button', class: 'phr-btn' }, actRow, 'Pause queues');
    const restartBtn = h('button', { type: 'button', class: 'phr-btn' }, actRow, 'Restart DB');

    const svg = el('svg', { viewBox: '0 0 640 292', role: 'img', 'aria-label': 'Live diagram of queue slots, the hot row, the MultiXact cache and DB connections' }, panel);
    const legend = h('div', { class: 'phr-legend' }, panel);
    for (const [k, name] of STATES) {
      const item = h('span', {}, legend);
      h('i', { class: 'phr-sw-' + k }, item);
      item.appendChild(document.createTextNode(name));
    }

    const stats = h('div', { class: 'phr-stats' }, panel);
    const status = h('p', { class: 'phr-status' }, panel);

    const chartSvg = el('svg', { viewBox: '0 0 640 250', role: 'img', 'aria-label': 'Metrics over the last 90 simulated seconds' }, panel);

    const knobs = h('div', { class: 'phr-controls phr-knobs' }, panel);
    const ctl = {};
    ctl.concA = slider(knobs, 'Queue A concurrency', 0, 100, 5, params.concA, v => apply('concA', v));
    ctl.concB = slider(knobs, 'Queue B concurrency', 0, 100, 5, params.concB, v => apply('concB', v));
    ctl.hotShare = slider(knobs, 'Tasks hitting the hot row', 0, 100, 5, params.hotShare * 100, v => apply('hotShare', v / 100), v => v + '%');
    ctl.apiRate = slider(knobs, 'API requests/s', 0, 600, 25, params.apiRate, v => apply('apiRate', v));
    ctl.maxConnections = slider(knobs, 'max_connections', 300, 3000, 100, params.maxConnections, v => apply('maxConnections', v));
    ctl.lockTimeoutMs = segmented(knobs, 'lock_timeout', [[0, 'off'], [100, '100 ms'], [500, '500 ms'], [2000, '2 s']], params.lockTimeoutMs, v => apply('lockTimeoutMs', v));
    ctl.slruBuffers = segmented(knobs, 'MultiXact member buffers', [[16, '16 (PG15)'], [64, '64'], [256, '256'], [1024, '1024 (PG17)']], params.slruBuffers, v => apply('slruBuffers', v));
    const speedSeg = segmented(knobs, 'Speed', [[0, 'pause'], [1, '1×'], [2, '2×'], [5, '5×']], speed, v => { speed = v; running = v > 0; });

    function apply(k, v) { params[k] = v; sim.set(k, v); }

    function reset(pin) {
      sim = createSim(params);
      history = [];
      nextSample = SAMPLE_S;
      lastWin = null;
      if (pin) sim.pin();
      syncButtons();
    }

    function loadPreset(k) {
      Object.assign(params, PRESETS[k].p);
      ctl.concA.set(params.concA); ctl.concB.set(params.concB);
      ctl.hotShare.set(params.hotShare * 100); ctl.apiRate.set(params.apiRate);
      ctl.maxConnections.set(params.maxConnections);
      ctl.lockTimeoutMs.set(params.lockTimeoutMs); ctl.slruBuffers.set(params.slruBuffers);
      reset(false);
      // Let the steady state settle before the long transaction starts.
      if (PRESETS[k].pin) pendingPin = 10;
    }
    let pendingPin = null;

    pinBtn.addEventListener('click', () => {
      pendingPin = null;
      if (sim.snapshot().pinned) sim.unpin(); else sim.pin();
      syncButtons();
    });
    pauseBtn.addEventListener('click', () => {
      apply('concA', 0); apply('concB', 0);
      ctl.concA.set(0); ctl.concB.set(0);
    });
    restartBtn.addEventListener('click', () => { pendingPin = null; sim.restart(2); syncButtons(); });

    function syncButtons() {
      pinBtn.textContent = sim.snapshot().pinned ? 'End long txn' : 'Open long txn';
    }

    // --- diagram ---

    const defs = el('defs', {}, svg);
    const mk = el('marker', { id: 'phr-arrow', viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: 'auto' }, defs);
    el('path', { d: 'M0 0 L10 5 L0 10 z', class: 'phr-arrowhead' }, mk);

    // Slots: two 10x10 grids.
    const slotRects = [];
    const gridX = [12, 112], gridY = 40, pitch = 9;
    txt(svg, 12, 16, 'Task queue slots', { class: 'phr-t-strong' });
    const qLabel = [txt(svg, 12, 33, '', { class: 'phr-t-dim' }), txt(svg, 112, 33, '', { class: 'phr-t-dim' })];
    for (let q = 0; q < 2; q++) {
      for (let i = 0; i < 100; i++) {
        slotRects.push(el('rect', {
          x: gridX[q] + (i % 10) * pitch, y: gridY + Math.floor(i / 10) * pitch,
          width: pitch - 1.5, height: pitch - 1.5, rx: 1.2, class: 'phr-slot phr-s-off',
        }, svg));
      }
    }
    txt(svg, 12, 148, 'Each square is one concurrent', { class: 'phr-t-dim' });
    txt(svg, 12, 162, 'dispatch. Most tasks hit the', { class: 'phr-t-dim' });
    txt(svg, 12, 176, 'same hot row.', { class: 'phr-t-dim' });

    // Hot row.
    const midX = 232;
    el('rect', { x: midX, y: 8, width: 200, height: 76, rx: 6, class: 'phr-box' }, svg);
    txt(svg, midX + 10, 26, 'Hot row', { class: 'phr-t-strong' });
    const lockIcon = el('circle', { cx: midX + 186, cy: 21, r: 5, class: 'phr-lock' }, svg);
    txt(svg, midX + 10, 44, 'row lock queue (heavyweight)', { class: 'phr-t-dim' });
    el('rect', { x: midX + 10, y: 52, width: 180, height: 10, rx: 2, class: 'phr-track' }, svg);
    const rowBar = el('rect', { x: midX + 10, y: 52, width: 0, height: 10, rx: 2, class: 'phr-fill-rowwait' }, svg);
    const rowText = txt(svg, midX + 10, 77, '', { class: 'phr-t' });

    // Parent row MultiXact.
    el('rect', { x: midX, y: 96, width: 200, height: 70, rx: 6, class: 'phr-box' }, svg);
    txt(svg, midX + 10, 114, 'Parent row: xmax → MultiXact', { class: 'phr-t-strong' });
    txt(svg, midX + 10, 131, 'members (txns holding KEY SHARE)', { class: 'phr-t-dim' });
    el('rect', { x: midX + 10, y: 138, width: 180, height: 10, rx: 2, class: 'phr-track' }, svg);
    const mxBar = el('rect', { x: midX + 10, y: 138, width: 0, height: 10, rx: 2, class: 'phr-fill-fk' }, svg);
    const mxText = txt(svg, midX + 10, 161, '', { class: 'phr-t' });

    // SLRU.
    el('rect', { x: midX, y: 178, width: 200, height: 106, rx: 6, class: 'phr-box' }, svg);
    txt(svg, midX + 10, 196, 'MultiXact member cache (SLRU)', { class: 'phr-t-strong' });
    txt(svg, midX + 10, 213, 'working set vs cache (log scale)', { class: 'phr-t-dim' });
    el('rect', { x: midX + 10, y: 220, width: 180, height: 10, rx: 2, class: 'phr-track' }, svg);
    const wsBar = el('rect', { x: midX + 10, y: 220, width: 0, height: 10, rx: 2, class: 'phr-fill-ws' }, svg);
    const cacheMark = el('line', { x1: 0, x2: 0, y1: 216, y2: 234, class: 'phr-cache-mark' }, svg);
    const wsText = txt(svg, midX + 10, 245, '', { class: 'phr-t' });
    txt(svg, midX + 10, 262, 'LWLock waiters', { class: 'phr-t-dim' });
    const lwDots = [];
    for (let i = 0; i < 20; i++) lwDots.push(el('circle', { cx: midX + 96 + i * 5, cy: 259, r: 1.8, class: 'phr-lwdot' }, svg));
    const lwText = txt(svg, midX + 10, 278, '', { class: 'phr-t' });

    // Arrows.
    el('path', { d: 'M204 70 C 216 70, 216 46, 230 46', class: 'phr-arrow', 'marker-end': 'url(#phr-arrow)' }, svg);
    el('path', { d: 'M204 100 C 216 100, 216 131, 230 131', class: 'phr-arrow', 'marker-end': 'url(#phr-arrow)' }, svg);
    el('path', { d: 'M332 166 L332 176', class: 'phr-arrow', 'marker-end': 'url(#phr-arrow)' }, svg);

    // Connections + API.
    const rX = 458;
    el('rect', { x: rX, y: 8, width: 174, height: 158, rx: 6, class: 'phr-box' }, svg);
    txt(svg, rX + 10, 26, 'DB connections', { class: 'phr-t-strong' });
    const connTrack = el('rect', { x: rX + 10, y: 36, width: 24, height: 120, rx: 3, class: 'phr-track' }, svg);
    const connWorker = el('rect', { x: rX + 10, y: 156, width: 24, height: 0, class: 'phr-fill-hold' }, svg);
    const connApi = el('rect', { x: rX + 10, y: 156, width: 24, height: 0, class: 'phr-fill-api' }, svg);
    const connText = txt(svg, rX + 44, 52, '', { class: 'phr-t-big' });
    const connSub = txt(svg, rX + 44, 70, '', { class: 'phr-t-dim' });
    el('rect', { x: rX + 44, y: 84, width: 9, height: 9, class: 'phr-fill-hold' }, svg);
    const connW = txt(svg, rX + 58, 92, '', { class: 'phr-t-dim' });
    el('rect', { x: rX + 44, y: 100, width: 9, height: 9, class: 'phr-fill-api' }, svg);
    const connA = txt(svg, rX + 58, 108, '', { class: 'phr-t-dim' });
    const pinText = txt(svg, rX + 44, 128, '', { class: 'phr-t-warn' });
    const downText = txt(svg, rX + 44, 146, '', { class: 'phr-t-warn' });
    void connTrack;

    el('rect', { x: rX, y: 178, width: 174, height: 106, rx: 6, class: 'phr-box' }, svg);
    txt(svg, rX + 10, 196, 'API (reads parent row)', { class: 'phr-t-strong' });
    txt(svg, rX + 10, 216, 'p95 latency', { class: 'phr-t-dim' });
    const apiP95 = txt(svg, rX + 10, 238, '', { class: 'phr-t-big' });
    txt(svg, rX + 96, 216, 'errors', { class: 'phr-t-dim' });
    const apiErr = txt(svg, rX + 96, 238, '', { class: 'phr-t-big' });
    txt(svg, rX + 10, 260, 'DB CPU', { class: 'phr-t-dim' });
    const cpuText = txt(svg, rX + 10, 277, '', { class: 'phr-t' });
    const apiRateText = txt(svg, rX + 96, 277, '', { class: 'phr-t-dim' });
    txt(svg, rX + 96, 260, 'client attempts', { class: 'phr-t-dim' });
    el('path', { d: `M${rX} 231 C 446 231, 446 225, 434 225`, class: 'phr-arrow', 'marker-end': 'url(#phr-arrow)' }, svg);

    // --- stat tiles ---
    const tileDefs = [
      ['time', 'simulated time'],
      ['commits', 'task commits/s'],
      ['miss', 'SLRU miss rate'],
      ['aborts', 'lock_timeout aborts/s'],
    ];
    const tiles = {};
    for (const [k, label] of tileDefs) {
      const d = h('div', { class: 'phr-stat' }, stats);
      tiles[k] = h('b', {}, d, '—');
      h('small', {}, d, label);
    }

    // --- charts ---
    const charts = [
      { key: 'commits', title: 'Task commits/s', max: () => 700, fmt: v => fmt(v), cls: 'phr-line-hold' },
      { key: 'ws', title: 'MultiXact working set', log: [1e3, 1e7], fmt: fmt, cls: 'phr-line-ws', ref: 'cache', refLabel: 'cache' },
      { key: 'lw', title: 'LWLock waiters', max: () => 1000, fmt: fmt, cls: 'phr-line-fk' },
      { key: 'conns', title: 'DB connections', max: () => Math.max(params.maxConnections, 300), fmt: fmt, cls: 'phr-line-api', ref: 'maxc', refLabel: 'max' },
      { key: 'p95', title: 'API p95 latency', log: [1e-3, 30], fmt: fmtS, cls: 'phr-line-rowwait' },
      { key: 'err', title: 'API errors %', max: () => 100, fmt: v => Math.round(v) + '%', cls: 'phr-line-noconn' },
    ];
    const cw = 200, ch = 92, cgx = 20, cgy = 30;
    charts.forEach((c, i) => {
      const x = (i % 3) * (cw + cgx), y = Math.floor(i / 3) * (ch + cgy + 4);
      const g = el('g', { transform: `translate(${x},${y})` }, chartSvg);
      txt(g, 0, 12, c.title, { class: 'phr-t-strong' });
      c.val = txt(g, cw, 12, '', { class: 'phr-t', 'text-anchor': 'end' });
      el('rect', { x: 0, y: 20, width: cw, height: ch, class: 'phr-chart-bg' }, g);
      c.refLine = c.ref ? el('line', { x1: 0, x2: cw, class: 'phr-cache-mark' }, g) : null;
      c.refText = c.ref ? txt(g, 3, 0, c.refLabel, { class: 'phr-t-tiny' }) : null;
      c.eventG = el('g', {}, g);
      c.path = el('path', { class: 'phr-line ' + c.cls }, g);
      c.x = x; c.y = y;
    });
    txt(chartSvg, 0, 248, `last ${HISTORY_S} simulated seconds · dashed lines mark the long transaction`, { class: 'phr-t-dim' });

    function yScale(c, v) {
      const top = 20, bottom = 20 + ch;
      if (c.log) {
        const [lo, hi] = c.log;
        const f = (Math.log10(Math.max(v, lo)) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo));
        return bottom - Math.min(1, Math.max(0, f)) * ch;
      }
      return bottom - Math.min(1, Math.max(0, v / c.max())) * ch;
    }

    function drawCharts(snap) {
      const n = history.length;
      for (const c of charts) {
        let d = '';
        for (let i = 0; i < n; i++) {
          const x = ((N_SAMPLES - n + i) / (N_SAMPLES - 1)) * cw;
          d += (i ? 'L' : 'M') + x.toFixed(1) + ' ' + yScale(c, history[i][c.key]).toFixed(1);
        }
        c.path.setAttribute('d', d);
        if (n) c.val.textContent = c.fmt(history[n - 1][c.key]);
        if (c.refLine) {
          const rv = c.ref === 'cache' ? snap.cacheMembers : params.maxConnections;
          const y = yScale(c, rv);
          c.refLine.setAttribute('y1', y); c.refLine.setAttribute('y2', y);
          c.refText.setAttribute('y', y - 3);
        }
        c.eventG.replaceChildren();
        for (let i = 1; i < n; i++) {
          if (history[i].pinned !== history[i - 1].pinned || history[i].restart) {
            const x = ((N_SAMPLES - n + i) / (N_SAMPLES - 1)) * cw;
            el('line', { x1: x, x2: x, y1: 20, y2: 20 + ch, class: history[i].restart ? 'phr-event-restart' : 'phr-event' }, c.eventG);
          }
        }
      }
    }

    // --- render ---

    const logW = v => Math.min(1, Math.max(0, (Math.log10(Math.max(v, 1e3)) - 3) / 4)); // 1k..10M

    function render() {
      const snap = sim.snapshot();
      const w = lastWin || {};

      for (let q = 0; q < 2; q++) {
        const cap = q === 0 ? params.concA : params.concB;
        qLabel[q].textContent = `Queue ${q ? 'B' : 'A'}: ${cap}`;
      }
      const byQ = { A: [], B: [] };
      for (const [q, st] of snap.slots) byQ[q].push(st);
      for (let q = 0; q < 2; q++) {
        const list = byQ[q ? 'B' : 'A'];
        const cap = q === 0 ? params.concA : params.concB;
        for (let i = 0; i < 100; i++) {
          const st = i < list.length ? list[i] : null;
          const cls = st ? 'phr-s-' + st : i < cap ? 'phr-s-idle' : 'phr-s-off';
          const r = slotRects[q * 100 + i];
          if (r.__c !== cls) { r.setAttribute('class', 'phr-slot ' + cls); r.__c = cls; }
        }
      }

      const held = snap.counts.hold > 0;
      lockIcon.setAttribute('class', held ? 'phr-lock phr-lock-held' : 'phr-lock');
      rowBar.setAttribute('width', Math.min(180, (snap.rowQueue / 200) * 180));
      rowText.textContent = `${snap.rowQueue} waiting · one holder at a time`;

      mxBar.setAttribute('width', Math.min(180, (snap.members / 200) * 180));
      mxText.textContent = `${snap.members} members in the newest MultiXact`;

      wsBar.setAttribute('width', logW(snap.workingSet) * 180);
      wsBar.setAttribute('class', snap.workingSet > snap.cacheMembers ? 'phr-fill-noconn' : 'phr-fill-ws');
      const cx = midX + 10 + logW(snap.cacheMembers) * 180;
      cacheMark.setAttribute('x1', cx); cacheMark.setAttribute('x2', cx);
      wsText.textContent = `${fmt(snap.workingSet)} members · cache ${fmt(snap.cacheMembers)}`;
      const lit = Math.min(20, Math.ceil(snap.slruQueue / 50));
      lwDots.forEach((d, i) => d.setAttribute('class', i < lit ? 'phr-lwdot phr-lwdot-on' : 'phr-lwdot'));
      lwText.textContent = `${fmt(snap.slruQueue)} queued on one LWLock`;

      const mc = params.maxConnections;
      const wh = Math.min(120, (snap.workerConns / mc) * 120);
      const ah = Math.min(120 - wh, (snap.apiConns / mc) * 120);
      connWorker.setAttribute('y', 156 - wh); connWorker.setAttribute('height', wh);
      connApi.setAttribute('y', 156 - wh - ah); connApi.setAttribute('height', ah);
      connText.textContent = `${fmt(snap.conns)} / ${fmt(mc)}`;
      connSub.textContent = snap.conns >= mc ? 'limit reached' : 'in use';
      connSub.setAttribute('class', snap.conns >= mc ? 'phr-t-warn' : 'phr-t-dim');
      connW.textContent = `${fmt(Math.max(0, snap.workerConns))} task workers`;
      connA.textContent = `${fmt(snap.apiConns)} API requests`;
      pinText.textContent = snap.pinned ? `long txn open ${Math.round(snap.pinAge)} s` : '';
      downText.textContent = snap.down ? 'DB restarting…' : '';

      apiP95.textContent = w.apiP95 != null ? fmtS(w.apiP95) : '—';
      apiErr.textContent = w.apiErrPct != null ? Math.round(w.apiErrPct) + '%' : '—';
      cpuText.textContent = w.cpuPct != null ? `${w.cpuPct.toFixed(1)}%` : '—';
      apiRateText.textContent = w.apiPerS != null ? `${Math.round(w.apiPerS)}/s` : '';

      tiles.time.textContent = Math.floor(snap.t) + ' s';
      tiles.commits.textContent = w.hotPerS != null ? fmt(w.hotPerS + w.coldPerS) : '—';
      tiles.miss.textContent = w.missPct != null ? Math.round(w.missPct) + '%' : '—';
      tiles.aborts.textContent = w.abortsPerS != null ? fmt(w.abortsPerS) : '—';

      status.innerHTML = describe(snap, w);
      drawCharts(snap);
    }

    function describe(snap, w) {
      if (snap.down) return '<b>Restarting.</b> Every session and lock is gone. Clients get connection errors until the DB is back.';
      if (w.hotPerS == null) return '<b>Warming up…</b>';
      if (snap.conns >= params.maxConnections) {
        return '<b>Collapsed.</b> Connections are exhausted. API requests queue behind the MultiXact LWLock, clients time out and retry, and the server keeps working on the abandoned requests. DB CPU is near zero.' +
          (snap.pinned ? '' : ' Ending the long transaction is not enough to get out of this: pause the queues and restart the DB.');
      }
      if (snap.slruQueue > 100) return '<b>Tipping over.</b> Most MultiXact lookups miss the cache. Every lookup waits on the same LWLock, so the row lock is held longer and the queue grows.';
      if (w.missPct > 5) return `<b>Degraded.</b> The MultiXact working set (${fmt(snap.workingSet)}) no longer fits the cache (${fmt(snap.cacheMembers)}). ${Math.round(w.missPct)}% of lookups go to disk, so every transaction holding the hot row takes longer.`;
      if (snap.rowQueue > 20) return `<b>Convoy, but healthy.</b> ${snap.rowQueue} transactions queue for the hot row, and the MultiXact working set fits the cache.`;
      return '<b>Healthy.</b>';
    }

    function tick(ts) {
      if (visible && running && speed > 0) {
        const dt = Math.min(0.1, (ts - (lastFrame || ts)) / 1000) * speed;
        const target = sim.now + dt;
        while (nextSample <= target) {
          if (pendingPin !== null && nextSample >= pendingPin) { sim.run(pendingPin); sim.pin(); pendingPin = null; syncButtons(); }
          sim.run(nextSample);
          lastWin = sim.closeWindow();
          const snap = sim.snapshot();
          history.push({
            commits: lastWin.hotPerS + lastWin.coldPerS,
            ws: snap.workingSet, cache: snap.cacheMembers, lw: snap.slruQueue, conns: snap.conns,
            p95: lastWin.apiP95, err: lastWin.apiErrPct, pinned: snap.pinned, restart: snap.down && !(history.length && history[history.length - 1].down), down: snap.down,
          });
          if (history.length > N_SAMPLES) history.shift();
          nextSample += SAMPLE_S;
        }
        sim.run(target);
        render();
      }
      lastFrame = ts;
      requestAnimationFrame(tick);
    }

    reset(false);
    render();
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(entries => { visible = entries.some(e => e.isIntersecting); }, { rootMargin: '100px' }).observe(fig);
    } else visible = true;
    void speedSeg; void preset;
    requestAnimationFrame(tick);
  }

  function init() {
    const a = document.getElementById('phr-multixact');
    const b = document.getElementById('phr-sim');
    if (a) multixactWidget(a);
    if (b) simWidget(b);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
