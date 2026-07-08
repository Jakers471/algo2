/* chart/static/js/indicators/session_structure.js — Session Structure RENDERER.
 *
 * The math lives in the backend (src/indicators/session_structure.py) so the chart,
 * the strategy Snapshot and the backtester agree. This fetches the computed levels
 * from /api/indicators/session_structure and draws, per session, on ONE canvas:
 *   - RAW high/low   solid lines across the session span (the extreme wicks), and
 *   - SWING high/low dashed lines (last CONFIRMED swing = BOS levels) + pivot dots.
 * It honors `asof`, so it recomputes live during replay (same as the other overlays).
 *
 * Distinct from the Sessions H/L indicator: that draws retest-terminated rays; this
 * draws the structural read (raw span + swing/BOS levels). Each session toggles
 * independently. Colors are a frontend concern and come from config (session color).
 */
(function () {
  const FALLBACK = { Asia: '#3f8ae0', London: '#e0a44e', NY: '#a06ee0' };

  function sessionList(config) {
    const wins = config && config.sessions && config.sessions.windows;
    if (wins) {
      return Object.keys(wins).map((id) => ({ id, color: wins[id].color || FALLBACK[id] || '#888888' }));
    }
    return Object.keys(FALLBACK).map((id) => ({ id, color: FALLBACK[id] }));
  }

  class StructRenderer {
    constructor(src) { this._src = src; }
    draw(target) {
      const s = this._src;
      const chart = s._chart;
      const series = s._series;
      if (!chart || !series) return;
      const ts = chart.timeScale();
      target.useMediaCoordinateSpace((scope) => {
        const ctx = scope.context;
        ctx.save();
        ctx.font = '10px -apple-system, system-ui, sans-serif';
        ctx.textBaseline = 'middle';

        const hline = (t0, t1, price, color, dashed, label) => {
          if (price == null) return;
          const x0 = ts.timeToCoordinate(t0);
          const x1 = ts.timeToCoordinate(t1);
          const y = series.priceToCoordinate(price);
          if (x0 === null || x1 === null || y === null) return;
          const py = Math.round(y) + 0.5;
          ctx.strokeStyle = color;
          ctx.lineWidth = dashed ? 1.5 : 1;
          ctx.setLineDash(dashed ? [5, 3] : []);
          ctx.beginPath();
          ctx.moveTo(x0, py);
          ctx.lineTo(x1, py);
          ctx.stroke();
          if (label) {
            ctx.setLineDash([]);
            ctx.fillStyle = color;
            ctx.fillText(label, x1 + 4, py);
          }
        };
        const dot = (t, price, color) => {
          if (price == null) return;
          const x = ts.timeToCoordinate(t);
          const y = series.priceToCoordinate(price);
          if (x === null || y === null) return;
          ctx.setLineDash([]);
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(x, y, 2.5, 0, Math.PI * 2);
          ctx.fill();
        };

        for (const st of s._structures) {
          if (!s._visible[st.session]) continue;
          const color = s._color[st.session] || '#888888';
          // Raw extremes: solid lines across the whole session span.
          hline(st.start, st.end, st.high, color, false, 'H');
          hline(st.start, st.end, st.low, color, false, 'L');
          // Swing (BOS) levels: dashed, from the pivot forward to the session end.
          hline(st.swing_high_time, st.end, st.swing_high, color, true, 'SH');
          hline(st.swing_low_time, st.end, st.swing_low, color, true, 'SL');
          // Every confirmed swing pivot as a dot.
          for (const p of st.pivots || []) dot(p.time, p.price, color);
        }
        ctx.restore();
      });
    }
  }
  class StructPaneView {
    constructor(src) { this._renderer = new StructRenderer(src); }
    zOrder() { return 'top'; }
    renderer() { return this._renderer; }
  }
  class StructPrimitive {
    constructor(color, visible) {
      this._structures = [];
      this._color = color;
      this._visible = visible;
      this._chart = null;
      this._series = null;
      this._requestUpdate = null;
      this._views = [new StructPaneView(this)];
    }
    attached(p) { this._chart = p.chart; this._series = p.series; this._requestUpdate = p.requestUpdate; }
    detached() { this._chart = null; this._series = null; this._requestUpdate = null; }
    updateAllViews() {}
    paneViews() { return this._views; }
    repaint() { if (this._requestUpdate) this._requestUpdate(); }
    setData(structures) { this._structures = structures || []; this.repaint(); }
    setVisible(name, on) { this._visible[name] = on; this.repaint(); }
  }

  window.IndicatorRegistry.register({
    id: 'session_structure',
    label: 'Session Structure',
    description: 'Per-session raw high/low + swing (BOS) structural levels',
    enabledByDefault: false,
    items: (config) => sessionList(config).map((s) => ({ id: s.id, label: s.id, color: s.color })),

    create(ctx) {
      const symbol = ctx.symbol || 'NQ';
      const list = sessionList(ctx.config);
      const color = Object.fromEntries(list.map((s) => [s.id, s.color]));
      const visible = Object.fromEntries(list.map((s) => [s.id, true]));
      const prim = new StructPrimitive(color, visible);
      ctx.candleSeries.attachPrimitive(prim);
      let reqId = 0;

      async function update(data, tf, opts) {
        const id = ++reqId;
        if (tf === '1d') { prim.setData([]); return; }
        const asof = opts && opts.asof ? `&asof=${opts.asof}` : '';
        try {
          const res = await fetch(
            `/api/indicators/session_structure?symbol=${symbol}&tf=${tf}&limit=10000${asof}`,
            { cache: 'no-store' }
          );
          const payload = res.ok ? await res.json() : null;
          if (id !== reqId) return;
          prim.setData(payload ? payload.structures : []);
        } catch (_) {
          if (id === reqId) prim.setData([]);
        }
      }

      return {
        update,
        setItemVisible(name, vis) { prim.setVisible(name, vis); },
        destroy() { ctx.candleSeries.detachPrimitive(prim); },
      };
    },
  });
})();
