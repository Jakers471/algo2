/* chart/static/js/indicators/volume_profile.js — Volume Profile RENDERER.
 *
 * Math lives in src/indicators/volume_profile.py. This module fetches the
 * computed per-session profiles from /api/indicators/volume_profile and draws
 * each as a sideways histogram (volume vs price) anchored at the session's
 * start, extending right. Value-area rows are shaded darker; the POC row is
 * highlighted and marked with a line. Each session toggles independently.
 *
 * Colors are a frontend concern and live here (mirrors sessions.js).
 */
(function () {
  const SESSION_META = [
    { id: 'Asia',   color: '#3f8ae0' },
    { id: 'London', color: '#e0a44e' },
    { id: 'NY',     color: '#a06ee0' },
  ];
  const COLOR = Object.fromEntries(SESSION_META.map((s) => [s.id, s.color]));

  const MAX_WIDTH_PX = 140;   // widest a profile (its POC row) can extend
  const BINS = 24;            // resolution requested from the backend

  function hexToRgb(hex) {
    const h = hex.replace('#', '');
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }
  const rgba = (rgb, a) => `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a})`;

  // ---- Histogram canvas primitive ------------------------------------------
  class ProfileRenderer {
    constructor(src) { this._src = src; }
    draw(target) {
      const chart = this._src._chart;
      const series = this._src._series;
      if (!chart || !series) return;
      const ts = chart.timeScale();
      target.useMediaCoordinateSpace((scope) => {
        const ctx = scope.context;
        for (const prof of this._src._profiles) {
          if (!this._src._visible[prof.session]) continue;
          const x0 = ts.timeToCoordinate(prof.start);
          const xEnd = ts.timeToCoordinate(prof.end);
          if (x0 === null) continue;
          const sessW = xEnd === null ? MAX_WIDTH_PX : Math.max(xEnd - x0, 8);
          const maxW = Math.min(sessW * 0.95, MAX_WIDTH_PX);
          const rgb = hexToRgb(COLOR[prof.session] || '#888888');
          const maxVol = prof.max_bin_volume || 1;

          for (const r of prof.rows) {
            if (r.volume <= 0) continue;
            const yTop = series.priceToCoordinate(r.high);
            const yBot = series.priceToCoordinate(r.low);
            if (yTop === null || yBot === null) continue;
            const h = Math.max(1, yBot - yTop);
            const w = maxW * (r.volume / maxVol);
            const alpha = r.poc ? 0.85 : r.in_va ? 0.42 : 0.22;
            ctx.fillStyle = rgba(rgb, alpha);
            ctx.fillRect(x0, yTop, w, Math.max(1, h - 1));
          }

          // POC line across the profile width.
          const yPoc = series.priceToCoordinate(prof.poc);
          if (yPoc !== null) {
            ctx.save();
            ctx.strokeStyle = rgba(rgb, 0.95);
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(x0, Math.round(yPoc) + 0.5);
            ctx.lineTo(x0 + maxW, Math.round(yPoc) + 0.5);
            ctx.stroke();
            ctx.restore();
          }
        }
      });
    }
  }
  class ProfilePaneView {
    constructor(src) { this._renderer = new ProfileRenderer(src); }
    zOrder() { return 'top'; }   // over candles (bars are translucent)
    renderer() { return this._renderer; }
  }
  class ProfilePrimitive {
    constructor() {
      this._profiles = [];
      this._visible = { Asia: true, London: true, NY: true };
      this._chart = null;
      this._series = null;
      this._requestUpdate = null;
      this._views = [new ProfilePaneView(this)];
    }
    attached(p) { this._chart = p.chart; this._series = p.series; this._requestUpdate = p.requestUpdate; }
    detached() { this._chart = null; this._series = null; this._requestUpdate = null; }
    updateAllViews() {}
    paneViews() { return this._views; }
    repaint() { if (this._requestUpdate) this._requestUpdate(); }
    setProfiles(profiles) { this._profiles = profiles; this.repaint(); }
    setVisible(name, on) { this._visible[name] = on; this.repaint(); }
  }

  // ---- Indicator definition (renderer) -------------------------------------
  window.IndicatorRegistry.register({
    id: 'volume_profile',
    label: 'Volume Profile',
    description: 'Per-session volume profile (histogram, POC, value area)',
    enabledByDefault: false,
    items: SESSION_META.map((s) => ({ id: s.id, label: s.id, color: s.color })),

    create(ctx) {
      const symbol = ctx.symbol || 'NQ';
      const prim = new ProfilePrimitive();
      ctx.candleSeries.attachPrimitive(prim);
      let reqId = 0;

      async function update(data, tf) {
        const id = ++reqId;
        if (tf === '1d') { prim.setProfiles([]); return; }
        try {
          const res = await fetch(
            `/api/indicators/volume_profile?symbol=${symbol}&tf=${tf}&limit=10000&bins=${BINS}`,
            { cache: 'no-store' }
          );
          const payload = res.ok ? await res.json() : null;
          if (id !== reqId) return;
          prim.setProfiles(payload ? payload.profiles : []);
        } catch (_) {
          if (id === reqId) prim.setProfiles([]);
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
