/* chart/static/js/indicators/sessions.js — Sessions High/Low RENDERER.
 *
 * The math lives in the backend (src/indicators/sessions.py) so the chart and
 * the backtester agree. This module fetches the computed levels from
 * /api/indicators/sessions and draws them with a SINGLE canvas primitive:
 *   - dashed horizontal rays at each session's high/low, and
 *   - dashed vertical lines at each session's start/end,
 * color-coded per session. Each session toggles independently.
 *
 * Perf: everything is one canvas overlay (no per-ray Lightweight-Charts series),
 * so pan/zoom stays smooth and toggling a session is just a repaint.
 *
 * Colors are a frontend (presentation) concern and live here; the session
 * windows/math are the backend's job.
 */
(function () {
  // Fallback colors if config is unavailable; config.sessions.windows wins.
  const FALLBACK = { Asia: '#3f8ae0', London: '#e0a44e', NY: '#a06ee0' };

  function sessionList(config) {
    const wins = config && config.sessions && config.sessions.windows;
    if (wins) {
      return Object.keys(wins).map((id) => ({ id, color: wins[id].color || FALLBACK[id] || '#888888' }));
    }
    return Object.keys(FALLBACK).map((id) => ({ id, color: FALLBACK[id] }));
  }

  // ---- Single canvas primitive: rays (horizontal) + verticals --------------
  class SessionsRenderer {
    constructor(src) { this._src = src; }
    draw(target) {
      const s = this._src;
      const chart = s._chart;
      const series = s._series;
      if (!chart || !series) return;
      const ts = chart.timeScale();
      target.useMediaCoordinateSpace((scope) => {
        const ctx = scope.context;
        const H = scope.mediaSize.height;
        ctx.save();
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);

        // Horizontal H/L rays: from the high/low point to where it was tested.
        for (const r of s._rays) {
          if (!s._visible[r.session]) continue;
          const x1 = ts.timeToCoordinate(r.start);
          const x2 = ts.timeToCoordinate(r.end);
          const y = series.priceToCoordinate(r.price);
          if (x1 === null || x2 === null || y === null) continue;
          const py = Math.round(y) + 0.5;
          ctx.strokeStyle = s._color[r.session] || '#888888';
          ctx.beginPath();
          ctx.moveTo(x1, py);
          ctx.lineTo(x2, py);
          ctx.stroke();
        }

        // Vertical session start/end lines.
        for (const v of s._verticals) {
          if (!s._visible[v.session]) continue;
          const x = ts.timeToCoordinate(v.time);
          if (x === null) continue;
          const px = Math.round(x) + 0.5;
          ctx.strokeStyle = s._color[v.session] || '#888888';
          ctx.beginPath();
          ctx.moveTo(px, 0);
          ctx.lineTo(px, H);
          ctx.stroke();
        }
        ctx.restore();
      });
    }
  }
  class SessionsPaneView {
    constructor(src) { this._renderer = new SessionsRenderer(src); }
    zOrder() { return 'top'; }
    renderer() { return this._renderer; }
  }
  class SessionsPrimitive {
    constructor(color, visible) {
      this._rays = [];
      this._verticals = [];
      this._color = color;       // { session: hex }
      this._visible = visible;   // { session: bool }
      this._chart = null;
      this._series = null;
      this._requestUpdate = null;
      this._views = [new SessionsPaneView(this)];
    }
    attached(p) { this._chart = p.chart; this._series = p.series; this._requestUpdate = p.requestUpdate; }
    detached() { this._chart = null; this._series = null; this._requestUpdate = null; }
    updateAllViews() {}
    paneViews() { return this._views; }
    repaint() { if (this._requestUpdate) this._requestUpdate(); }
    setData(rays, verticals) {
      // Drop degenerate rays (start == end) up front.
      this._rays = (rays || []).filter((r) => r.end > r.start);
      this._verticals = verticals || [];
      this.repaint();
    }
    setVisible(name, on) { this._visible[name] = on; this.repaint(); }
  }

  // ---- Indicator definition (renderer) -------------------------------------
  window.IndicatorRegistry.register({
    id: 'sessions',
    label: 'Sessions H/L',
    description: 'Asia / London / NY session highs & lows with session boundaries',
    enabledByDefault: true,
    items: (config) => sessionList(config).map((s) => ({ id: s.id, label: s.id, color: s.color })),

    create(ctx) {
      const symbol = ctx.symbol || 'NQ';
      const list = sessionList(ctx.config);
      const color = Object.fromEntries(list.map((s) => [s.id, s.color]));
      const visible = Object.fromEntries(list.map((s) => [s.id, true]));
      const prim = new SessionsPrimitive(color, visible);
      ctx.candleSeries.attachPrimitive(prim);
      let reqId = 0;

      async function update(data, tf) {
        const id = ++reqId;
        if (tf === '1d') { prim.setData([], []); return; }
        try {
          const res = await fetch(
            `/api/indicators/sessions?symbol=${symbol}&tf=${tf}&limit=10000`,
            { cache: 'no-store' }
          );
          const payload = res.ok ? await res.json() : null;
          if (id !== reqId) return;
          prim.setData(payload ? payload.rays : [], payload ? payload.verticals : []);
        } catch (_) {
          if (id === reqId) prim.setData([], []);
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
