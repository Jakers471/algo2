/* chart/static/js/indicators/range_hop.js — TEMP session H/L + bias RENDERER.
 *
 * Math lives in src/indicators/range_hop.py. Fetches per-session segments + bias
 * regime from /api/indicators/range_hop and draws:
 *   - HIGH / LOW — connected stepped lines, each step GREEN when the level rose,
 *     RED when it fell.
 *   - BIAS — full-height green (bullish) / red (bearish) background tint from
 *     breaking the previous session's range.
 * Toggle High / Low / Bias independently.
 *
 * EXPERIMENTAL — self-contained drop-in. Delete this file + its <script> tag +
 * the server route to remove. Colors are a frontend concern and live here.
 */
(function () {
  const UP = '#26a37b', DOWN = '#e0685f', NEUTRAL = '#8b97a7';

  function rgba(hex, a) {
    const h = hex.replace('#', '');
    return `rgba(${parseInt(h.slice(0, 2), 16)},${parseInt(h.slice(2, 4), 16)},${parseInt(h.slice(4, 6), 16)},${a})`;
  }
  const dirColor = (d) => (d === 'up' ? UP : d === 'down' ? DOWN : NEUTRAL);

  // --- bias cloud: full-height tint behind price ---
  class CloudRenderer {
    constructor(src) { this._src = src; }
    draw(target) {
      const chart = this._src._chart;
      if (!chart || !this._src._visible.bias) return;
      const ts = chart.timeScale();
      target.useMediaCoordinateSpace((scope) => {
        const ctx = scope.context;
        const H = scope.mediaSize.height, W = scope.mediaSize.width;
        for (const r of this._src._regime) {
          let x0 = ts.timeToCoordinate(r.start);
          let x1 = ts.timeToCoordinate(r.end);
          if (x0 === null) x0 = 0;
          if (x1 === null) x1 = W;
          ctx.fillStyle = rgba(r.bias === 'bull' ? UP : DOWN, 0.08);
          ctx.fillRect(x0, 0, x1 - x0, H);
        }
      });
    }
  }
  class CloudView {
    constructor(src) { this._r = new CloudRenderer(src); }
    zOrder() { return 'bottom'; }   // behind candles
    renderer() { return this._r; }
  }

  // --- connected, direction-colored H/L lines: over price ---
  class LinesRenderer {
    constructor(src) { this._src = src; }
    draw(target) {
      const chart = this._src._chart, series = this._src._series;
      if (!chart || !series) return;
      const ts = chart.timeScale();
      target.useMediaCoordinateSpace((scope) => {
        const ctx = scope.context;
        const vis = this._src._visible, W = scope.mediaSize.width;
        const segs = this._src._segments;
        const drawEdge = (valKey, dirKey) => {
          for (let i = 0; i < segs.length; i++) {
            const s = segs[i];
            const y = series.priceToCoordinate(s[valKey]);
            if (y === null) continue;
            let x0 = ts.timeToCoordinate(s.start);
            let x1 = ts.timeToCoordinate(s.end);
            if (x0 === null) x0 = 0;
            if (x1 === null) x1 = W;
            ctx.strokeStyle = rgba(dirColor(s[dirKey]), s.active ? 1 : 0.85);
            ctx.lineWidth = s.active ? 2 : 1.4;
            ctx.beginPath();
            if (i > 0) {
              const yp = series.priceToCoordinate(segs[i - 1][valKey]);
              if (yp !== null) { ctx.moveTo(x0, yp); ctx.lineTo(x0, y); }
            }
            ctx.moveTo(x0, Math.round(y) + 0.5);
            ctx.lineTo(x1, Math.round(y) + 0.5);
            ctx.stroke();
          }
        };
        if (vis.high) drawEdge('high', 'high_dir');
        if (vis.low) drawEdge('low', 'low_dir');
      });
    }
  }
  class LinesView {
    constructor(src) { this._r = new LinesRenderer(src); }
    zOrder() { return 'top'; }
    renderer() { return this._r; }
  }

  class HopPrimitive {
    constructor(visible) {
      this._segments = []; this._regime = [];
      this._visible = visible;      // { high, low, bias }
      this._chart = null; this._series = null; this._requestUpdate = null;
      this._views = [new CloudView(this), new LinesView(this)];
    }
    attached(p) { this._chart = p.chart; this._series = p.series; this._requestUpdate = p.requestUpdate; }
    detached() { this._chart = null; this._series = null; this._requestUpdate = null; }
    updateAllViews() {}
    paneViews() { return this._views; }
    repaint() { if (this._requestUpdate) this._requestUpdate(); }
    setData(d) { this._segments = d.segments || []; this._regime = d.regime || []; this.repaint(); }
    setVisible(name, on) { this._visible[name] = on; this.repaint(); }
  }

  window.IndicatorRegistry.register({
    id: 'range_hop',
    label: 'Session H/L + bias (TEMP)',
    description: 'Connected session high/low (green up / red down) + bull/bear background from prior-session breaks',
    enabledByDefault: false,
    items: () => [
      { id: 'high', label: 'Session high', color: UP },
      { id: 'low', label: 'Session low', color: DOWN },
      { id: 'bias', label: 'Bias background', color: UP },
    ],

    create(ctx) {
      const symbol = ctx.symbol || 'NQ';
      const prim = new HopPrimitive({ high: true, low: true, bias: false });
      ctx.candleSeries.attachPrimitive(prim);
      let reqId = 0;

      async function update(data, tf, opts) {
        const id = ++reqId;
        if (tf === '1d') { prim.setData({}); return; }
        const asof = opts && opts.asof ? `&asof=${opts.asof}` : '';
        try {
          const res = await fetch(
            `/api/indicators/range_hop?symbol=${symbol}&tf=${tf}&limit=10000${asof}`,
            { cache: 'no-store' }
          );
          const payload = res.ok ? await res.json() : null;
          if (id !== reqId) return;
          prim.setData(payload || {});
        } catch (_) {
          if (id === reqId) prim.setData({});
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
