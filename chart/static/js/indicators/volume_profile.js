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
  // Fallback colors if config is unavailable; config.sessions.windows wins.
  const FALLBACK = { Asia: '#3f8ae0', London: '#e0a44e', NY: '#a06ee0' };

  function sessionList(config) {
    const wins = config && config.sessions && config.sessions.windows;
    if (wins) {
      return Object.keys(wins).map((id) => ({ id, color: wins[id].color || FALLBACK[id] || '#888888' }));
    }
    return Object.keys(FALLBACK).map((id) => ({ id, color: FALLBACK[id] }));
  }

  const MAX_WIDTH_PX = 140;   // widest a profile (its POC row) can extend
  // row_size (resolution) is NOT sent from here — the backend reads it from
  // algo_config.yaml, so editing the config recomputes the profile.

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
          const rgb = hexToRgb((this._src._color && this._src._color[prof.session]) || '#888888');
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
    constructor(color, visible) {
      this._profiles = [];
      this._color = color;       // { session: hex } from config
      this._visible = visible;   // { session: bool }
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
    items: (config) => sessionList(config).map((s) => ({ id: s.id, label: s.id, color: s.color })),

    create(ctx) {
      const symbol = ctx.symbol || 'NQ';
      const list = sessionList(ctx.config);
      const color = Object.fromEntries(list.map((s) => [s.id, s.color]));
      const visible = Object.fromEntries(list.map((s) => [s.id, true]));
      const prim = new ProfilePrimitive(color, visible);
      ctx.candleSeries.attachPrimitive(prim);
      let reqId = 0;

      async function update(data, tf) {
        const id = ++reqId;
        if (tf === '1d') { prim.setProfiles([]); return; }
        try {
          const res = await fetch(
            `/api/indicators/volume_profile?symbol=${symbol}&tf=${tf}&limit=10000`,
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
