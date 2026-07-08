/* chart/static/js/session_detail.js — click a session to draw its profile levels.
 *
 * Click anywhere inside a session's time span to overlay that session's
 * H / VAH / POC / VAL / L at TWO resolutions:
 *   - 5m (session color, labels on the right)  — the 5-minute session profile
 *   - 1m (teal, labels on the left)            — the 1-minute mirror (finer bars)
 * Click the same session again, or empty space, to clear.
 *
 * Now a control-panel indicator ("Session Levels (click)") with 5m / 1m sub-toggles,
 * so each resolution turns on/off from the panel like every other overlay. Both
 * resolutions reuse the SAME per-session volume-profile math (src/indicators/
 * volume_profile.py) — the 1m one is just /api/indicators/volume_profile?tf=1m.
 */
(function () {
  const FALLBACK = { Asia: '#3f8ae0', London: '#e0a44e', NY: '#a06ee0' };
  const TEAL = '#26c6da';                 // 1m levels (matches the 1m Volume Profile overlay)
  function colorFor(config, name) {
    const wins = config && config.sessions && config.sessions.windows;
    return (wins && wins[name] && wins[name].color) || FALLBACK[name] || '#888888';
  }
  function hexA(hex, a) {
    let h = hex.replace('#', '');
    if (h.length === 3) h = h.split('').map((c) => c + c).join('');
    const n = parseInt(h, 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }
  const fmtPrice = (p) => String(Math.round(p * 4) / 4);

  const LEVELS = [
    { key: 'high', label: 'H',   dash: false, weight: 1, alpha: 0.55 },
    { key: 'vah',  label: 'VAH', dash: true,  weight: 1, alpha: 0.9 },
    { key: 'poc',  label: 'POC', dash: false, weight: 2, alpha: 1.0 },
    { key: 'val',  label: 'VAL', dash: true,  weight: 1, alpha: 0.9 },
    { key: 'low',  label: 'L',   dash: false, weight: 1, alpha: 0.55 },
  ];

  class DetailRenderer {
    constructor(src) { this._src = src; }
    draw(target) {
      const s = this._src;
      const chart = s._chart, series = s._series;
      if (!chart || !series) return;
      const ts = chart.timeScale();

      target.useMediaCoordinateSpace((scope) => {
        const ctx = scope.context;
        const H = scope.mediaSize.height;

        const drawOne = (prof, color, side) => {
          if (!prof) return;
          const x1 = ts.timeToCoordinate(prof.start);
          const x2 = ts.timeToCoordinate(prof.end);
          if (x1 === null || x2 === null) return;
          const xL = Math.min(x1, x2), xR = Math.max(x1, x2);

          // Faint session-span highlight (once per resolution, very light).
          ctx.save();
          ctx.fillStyle = hexA(color, 0.04);
          ctx.fillRect(xL, 0, xR - xL, H);
          ctx.restore();

          ctx.save();
          ctx.font = '11px system-ui, -apple-system, sans-serif';
          ctx.textBaseline = 'middle';
          for (const lv of LEVELS) {
            const y = series.priceToCoordinate(prof[lv.key]);
            if (y === null) continue;
            const py = Math.round(y) + 0.5;
            ctx.strokeStyle = hexA(color, lv.alpha);
            ctx.lineWidth = lv.weight;
            ctx.setLineDash(lv.dash ? [4, 4] : []);
            ctx.beginPath(); ctx.moveTo(xL, py); ctx.lineTo(xR, py); ctx.stroke();

            const text = `${lv.label} ${fmtPrice(prof[lv.key])}`;
            ctx.setLineDash([]);
            const tw = ctx.measureText(text).width;
            const tx = side === 'right' ? xR + 5 : xL - tw - 5;   // 5m right, 1m left
            ctx.fillStyle = 'rgba(13,13,13,0.72)';
            ctx.fillRect(tx - 3, py - 7.5, tw + 6, 15);
            ctx.fillStyle = hexA(color, 1);
            ctx.fillText(text, tx, py);
          }
          ctx.restore();
        };

        if (s._visible['5m']) drawOne(s._prof5, s._colorFor(s._session), 'right');
        if (s._visible['1m']) drawOne(s._prof1, TEAL, 'left');
      });
    }
  }
  class DetailPaneView {
    constructor(src) { this._renderer = new DetailRenderer(src); }
    zOrder() { return 'top'; }
    renderer() { return this._renderer; }
  }
  class DetailPrimitive {
    constructor(visible) {
      this._prof5 = null; this._prof1 = null; this._session = null;
      this._visible = visible;               // { '5m': bool, '1m': bool }
      this._chart = null; this._series = null; this._requestUpdate = null;
      this._colorFor = () => '#888888';
      this._views = [new DetailPaneView(this)];
    }
    attached(p) { this._chart = p.chart; this._series = p.series; this._requestUpdate = p.requestUpdate; }
    detached() { this._chart = null; this._series = null; this._requestUpdate = null; }
    updateAllViews() {}
    paneViews() { return this._views; }
    repaint() { if (this._requestUpdate) this._requestUpdate(); }
    setSelected(prof5, prof1, session) { this._prof5 = prof5; this._prof1 = prof1; this._session = session; this.repaint(); }
    setVisible(id, on) { this._visible[id] = on; this.repaint(); }
  }

  window.IndicatorRegistry.register({
    id: 'session_detail',
    label: 'Session Levels (click)',
    description: 'Click a session to draw its H/VAH/POC/VAL/L — 5m and/or 1m',
    enabledByDefault: true,
    items: () => [
      { id: '5m', label: '5m', color: '#c3c2b7' },
      { id: '1m', label: '1m', color: TEAL },
    ],

    create(ctx) {
      const chart = ctx.chart;
      const symbol = ctx.symbol || 'NQ';
      const visible = { '5m': true, '1m': true };
      const prim = new DetailPrimitive(visible);
      prim._colorFor = (name) => colorFor(ctx.config, name);
      ctx.candleSeries.attachPrimitive(prim);

      let profiles5 = [], profiles1 = [];
      let reqId = 0;
      let lastTf = null;
      let selT = null;                        // clicked time (inside the session span)

      const findAt = (profs, t) => profs.find((p) => t >= p.start && t <= p.end) || null;

      function resolve() {
        if (selT == null) { prim.setSelected(null, null, null); return; }
        const p5 = findAt(profiles5, selT);
        const p1 = findAt(profiles1, selT);
        prim.setSelected(p5, p1, (p5 || p1 || {}).session || null);
      }

      async function fetchProfiles(tf, asof) {
        try {
          const res = await fetch(
            `/api/indicators/volume_profile?symbol=${symbol}&tf=${tf}&limit=10000${asof}`,
            { cache: 'no-store' });
          const j = res.ok ? await res.json() : null;
          return j ? j.profiles : [];
        } catch (_) { return []; }
      }

      async function update(data, tf, opts) {
        const id = ++reqId;
        if (tf !== lastTf) { selT = null; }   // real dataset change drops the selection
        lastTf = tf;
        if (tf === '1d') { profiles5 = []; profiles1 = []; selT = null; prim.setSelected(null, null, null); return; }
        const asof = opts && opts.asof ? `&asof=${opts.asof}` : '';
        // Both resolutions, independent of the displayed tf (5m + 1m session profiles).
        const [p5, p1] = await Promise.all([fetchProfiles('5m', asof), fetchProfiles('1m', asof)]);
        if (id !== reqId) return;
        profiles5 = p5; profiles1 = p1;
        resolve();
      }

      function onClick(param) {
        if (!param || !param.point) return;
        const t = chart.timeScale().coordinateToTime(param.point.x);
        if (t == null) { selT = null; resolve(); return; }
        const hit = findAt(profiles5, t) || findAt(profiles1, t);
        // toggle off if clicking the already-selected session (or empty)
        const cur = selT != null ? (findAt(profiles5, selT) || findAt(profiles1, selT)) : null;
        const same = hit && cur && hit.session === cur.session && hit.start === cur.start;
        selT = (hit && !same) ? t : null;
        resolve();
      }
      chart.subscribeClick(onClick);

      return {
        update,
        setItemVisible(id, vis) { prim.setVisible(id, vis); },
        destroy() { chart.unsubscribeClick(onClick); ctx.candleSeries.detachPrimitive(prim); },
      };
    },
  });
})();
