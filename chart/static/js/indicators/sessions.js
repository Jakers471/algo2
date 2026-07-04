/* chart/static/js/indicators/sessions.js — Sessions High/Low RENDERER.
 *
 * The math lives in the backend (src/indicators/sessions.py) so the chart and
 * the backtester agree. This module only fetches the computed levels from
 * /api/indicators/sessions and draws them:
 *   - dashed horizontal rays at each session's high/low, and
 *   - dashed vertical lines at each session's start/end,
 * color-coded per session. Each session toggles independently.
 *
 * Colors are a frontend (presentation) concern and live here; the session
 * windows/math are the backend's job.
 */
(function () {
  const SESSION_META = [
    { id: 'Asia',   color: '#3f8ae0' },
    { id: 'London', color: '#e0a44e' },
    { id: 'NY',     color: '#a06ee0' },
  ];
  const COLOR = Object.fromEntries(SESSION_META.map((s) => [s.id, s.color]));

  // ---- Vertical-line canvas primitive --------------------------------------
  // Lightweight Charts has no native vertical line, so we draw them with a
  // series primitive that paints dashed verticals at given times/colors.
  class VLinesRenderer {
    constructor(src) { this._src = src; }
    draw(target) {
      const chart = this._src._chart;
      if (!chart) return;
      const ts = chart.timeScale();
      target.useMediaCoordinateSpace((scope) => {
        const ctx = scope.context;
        for (const ln of this._src._lines) {
          const x = ts.timeToCoordinate(ln.time);
          if (x === null) continue;
          const px = Math.round(x) + 0.5;
          ctx.save();
          ctx.strokeStyle = ln.color;
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(px, 0);
          ctx.lineTo(px, scope.mediaSize.height);
          ctx.stroke();
          ctx.restore();
        }
      });
    }
  }
  class VLinesPaneView {
    constructor(src) { this._renderer = new VLinesRenderer(src); }
    zOrder() { return 'bottom'; }
    renderer() { return this._renderer; }
  }
  class VLinesPrimitive {
    constructor() {
      this._lines = [];
      this._chart = null;
      this._requestUpdate = null;
      this._views = [new VLinesPaneView(this)];
    }
    attached(p) { this._chart = p.chart; this._requestUpdate = p.requestUpdate; }
    detached() { this._chart = null; this._requestUpdate = null; }
    updateAllViews() {}
    paneViews() { return this._views; }
    setLines(lines) {
      this._lines = lines;
      if (this._requestUpdate) this._requestUpdate();
    }
  }

  // ---- Indicator definition (renderer) -------------------------------------
  window.IndicatorRegistry.register({
    id: 'sessions',
    label: 'Sessions H/L',
    description: 'Asia / London / NY session highs & lows with session boundaries',
    enabledByDefault: true,
    items: SESSION_META.map((s) => ({ id: s.id, label: s.id, color: s.color })),

    create(ctx) {
      const chart = ctx.chart;
      const symbol = ctx.symbol || 'NQ';
      const series = [];
      const visible = { Asia: true, London: true, NY: true };
      let result = null;   // last payload from the API
      let reqId = 0;       // guards against out-of-order async responses

      const vlines = new VLinesPrimitive();
      ctx.candleSeries.attachPrimitive(vlines);

      const clearSeries = () => {
        for (const s of series) chart.removeSeries(s);
        series.length = 0;
      };

      function draw() {
        clearSeries();
        if (!result) { vlines.setLines([]); return; }
        for (const r of result.rays) {
          if (!visible[r.session] || r.end <= r.start) continue;
          const s = chart.addLineSeries({
            color: COLOR[r.session],
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            lastValueVisible: false,
            priceLineVisible: false,
            crosshairMarkerVisible: false,
          });
          s.setData([
            { time: r.start, value: r.price },
            { time: r.end, value: r.price },
          ]);
          series.push(s);
        }
        vlines.setLines(
          result.verticals
            .filter((v) => visible[v.session])
            .map((v) => ({ time: v.time, color: COLOR[v.session] }))
        );
      }

      async function update(data, tf) {
        const id = ++reqId;
        if (tf === '1d') { result = null; draw(); return; }
        try {
          const res = await fetch(
            `/api/indicators/sessions?symbol=${symbol}&tf=${tf}&limit=10000`,
            { cache: 'no-store' }
          );
          const payload = res.ok ? await res.json() : null;
          if (id !== reqId) return; // a newer request superseded this one
          result = payload;
        } catch (_) {
          if (id !== reqId) return;
          result = null;
        }
        draw();
      }

      return {
        update,
        setItemVisible(name, vis) { visible[name] = vis; draw(); },
        destroy() { clearSeries(); ctx.candleSeries.detachPrimitive(vlines); },
      };
    },
  });
})();
