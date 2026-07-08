/* chart/static/js/indicators/ltf_volume_profile.js — 1-minute (L2) Volume Profile RENDERER.
 *
 * Math lives in src/indicators/ltf_volume_profile.py (computed the same way grade()
 * profiles, so it matches the monitor's "1min volume profile" box). This fetches the
 * one profile from /api/indicators/ltf_volume_profile and draws it as a sideways
 * histogram over ITS RANGE: bars anchored at the window start extending right (width
 * ~ volume), value-area rows shaded, POC highlighted, with POC/VAH/VAL lines spanning
 * the window. Honors `asof`, so it tracks replay.
 *
 * Single distinct color (teal) so it reads apart from the per-session 5m Volume Profile.
 * Colors are a frontend concern and live here.
 */
(function () {
  const COLOR = '#26c6da';       // teal — distinct from the session-colored 5m profile
  const MAX_WIDTH_PX = 160;      // widest the POC row can extend

  function hexToRgb(hex) {
    const h = hex.replace('#', '');
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }
  const rgba = (rgb, a) => `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a})`;

  class LtfRenderer {
    constructor(src) { this._src = src; }
    draw(target) {
      const s = this._src;
      const chart = s._chart, series = s._series;
      if (!chart || !series || !s._prof) return;
      const p = s._prof;
      const ts = chart.timeScale();
      const rgb = hexToRgb(COLOR);
      target.useMediaCoordinateSpace((scope) => {
        const ctx = scope.context;
        const x0 = ts.timeToCoordinate(p.start);
        const xEnd = ts.timeToCoordinate(p.end);
        if (x0 === null) return;
        const rangeW = xEnd === null ? MAX_WIDTH_PX : Math.max(xEnd - x0, 10);
        const maxW = Math.min(rangeW * 0.95, MAX_WIDTH_PX);
        const maxVol = p.max_bin_volume || 1;

        for (const r of p.rows) {
          if (r.volume <= 0) continue;
          const yTop = series.priceToCoordinate(r.high);
          const yBot = series.priceToCoordinate(r.low);
          if (yTop === null || yBot === null) continue;
          const h = Math.max(1, yBot - yTop);
          const w = maxW * (r.volume / maxVol);
          const alpha = r.poc ? 0.80 : r.in_va ? 0.40 : 0.20;
          ctx.fillStyle = rgba(rgb, alpha);
          ctx.fillRect(x0, yTop, w, Math.max(1, h - 1));
        }

        // POC / VAH / VAL lines across the window range.
        const xRight = xEnd === null ? x0 + maxW : xEnd;
        const line = (price, a, dash) => {
          const y = series.priceToCoordinate(price);
          if (y === null) return;
          ctx.save();
          ctx.strokeStyle = rgba(rgb, a);
          ctx.lineWidth = 1;
          ctx.setLineDash(dash || []);
          ctx.beginPath();
          ctx.moveTo(x0, Math.round(y) + 0.5);
          ctx.lineTo(xRight, Math.round(y) + 0.5);
          ctx.stroke();
          ctx.restore();
        };
        line(p.poc, 0.95, null);      // POC solid
        line(p.vah, 0.6, [4, 3]);     // value-area edges dashed
        line(p.val, 0.6, [4, 3]);
      });
    }
  }
  class LtfPaneView {
    constructor(src) { this._renderer = new LtfRenderer(src); }
    zOrder() { return 'top'; }
    renderer() { return this._renderer; }
  }
  class LtfPrimitive {
    constructor() {
      this._prof = null;
      this._chart = null; this._series = null; this._requestUpdate = null;
      this._views = [new LtfPaneView(this)];
    }
    attached(p) { this._chart = p.chart; this._series = p.series; this._requestUpdate = p.requestUpdate; }
    detached() { this._chart = null; this._series = null; this._requestUpdate = null; }
    updateAllViews() {}
    paneViews() { return this._views; }
    repaint() { if (this._requestUpdate) this._requestUpdate(); }
    setProfile(prof) { this._prof = prof; this.repaint(); }
  }

  window.IndicatorRegistry.register({
    id: 'ltf_volume_profile',
    label: '1m Volume Profile',
    description: 'The 1-minute (L2) volume profile drawn over its recent window',
    enabledByDefault: false,
    items: () => [{ id: 'ltf', label: '1m VP', color: COLOR }],

    create(ctx) {
      const symbol = ctx.symbol || 'NQ';
      const prim = new LtfPrimitive();
      ctx.candleSeries.attachPrimitive(prim);
      let reqId = 0;

      async function update(data, tf, opts) {
        const id = ++reqId;
        const asof = opts && opts.asof ? `&asof=${opts.asof}` : '';
        try {
          const res = await fetch(
            `/api/indicators/ltf_volume_profile?symbol=${symbol}&tf=${tf}&limit=10000${asof}`,
            { cache: 'no-store' }
          );
          const payload = res.ok ? await res.json() : null;
          if (id !== reqId) return;
          prim.setProfile(payload ? payload.profile : null);
        } catch (_) {
          if (id === reqId) prim.setProfile(null);
        }
      }

      return {
        update,
        setItemVisible() { /* single overlay; master toggle handles it */ },
        destroy() { ctx.candleSeries.detachPrimitive(prim); },
      };
    },
  });
})();
