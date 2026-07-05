/* chart/static/js/indicators/micro_zones.js — TEMP micro-consolidation RENDERER.
 *
 * Math lives in src/indicators/micro_zones.py. Fetches per-session data from
 * /api/indicators/micro_zones and draws:
 *   - CHANNEL — this timeframe's value-area band (VAH/VAL) across the session.
 *               Amber. The base consolidation, READ (not detected).
 *   - MICRO   — tight runs (30-80 bars of the SAME timeframe) inside the channel.
 *               Cyan boxes.
 * Toggle Channel / Micro independently.
 *
 * EXPERIMENTAL — self-contained drop-in. Delete this file + its <script> tag +
 * the server route to remove. Colors are a frontend concern and live here.
 */
(function () {
  const COL = { channel: '#f2a541', micro: '#4fd0e0' };

  function rgba(hex, a) {
    const h = hex.replace('#', '');
    return `rgba(${parseInt(h.slice(0, 2), 16)},${parseInt(h.slice(2, 4), 16)},${parseInt(h.slice(4, 6), 16)},${a})`;
  }

  class ZonesRenderer {
    constructor(src) { this._src = src; }
    draw(target) {
      const chart = this._src._chart, series = this._src._series;
      if (!chart || !series) return;
      const ts = chart.timeScale();
      target.useMediaCoordinateSpace((scope) => {
        const ctx = scope.context;
        const vis = this._src._visible;

        const rect = (start, end, lo, hi) => {
          // Both edges must land on a real bar, else skip (don't stretch to edge).
          const x0 = ts.timeToCoordinate(start);
          const x1 = ts.timeToCoordinate(end);
          if (x0 === null || x1 === null) return null;
          const yTop = series.priceToCoordinate(hi);
          const yBot = series.priceToCoordinate(lo);
          if (yTop === null || yBot === null) return null;
          return [x0, yTop, Math.max(2, x1 - x0), Math.max(2, yBot - yTop)];
        };

        for (const prof of this._src._profiles) {
          // channel (base value area)
          if (vis.channel) {
            const r = rect(prof.start, prof.end, prof.val, prof.vah);
            if (r) {
              ctx.fillStyle = rgba(COL.channel, 0.07);
              ctx.fillRect(r[0], r[1], r[2], r[3]);
              ctx.strokeStyle = rgba(COL.channel, 0.85);
              ctx.lineWidth = 1;
              ctx.setLineDash([2, 2]);
              ctx.strokeRect(r[0] + 0.5, r[1] + 0.5, r[2] - 1, r[3] - 1);
              ctx.setLineDash([]);
            }
          }
          // micro zones inside the channel
          if (vis.micro) {
            for (const z of prof.zones) {
              const r = rect(z.start, z.end, z.lo, z.hi);
              if (!r) continue;
              ctx.fillStyle = rgba(COL.micro, 0.16);
              ctx.fillRect(r[0], r[1], r[2], r[3]);
              ctx.strokeStyle = rgba(COL.micro, 0.95);
              ctx.lineWidth = 1.3;
              ctx.strokeRect(r[0] + 0.5, r[1] + 0.5, r[2] - 1, r[3] - 1);
            }
          }
        }
      });
    }
  }
  class ZonesPaneView {
    constructor(src) { this._renderer = new ZonesRenderer(src); }
    zOrder() { return 'top'; }
    renderer() { return this._renderer; }
  }
  class ZonesPrimitive {
    constructor(visible) {
      this._profiles = [];
      this._visible = visible;      // { channel, micro }
      this._chart = null; this._series = null; this._requestUpdate = null;
      this._views = [new ZonesPaneView(this)];
    }
    attached(p) { this._chart = p.chart; this._series = p.series; this._requestUpdate = p.requestUpdate; }
    detached() { this._chart = null; this._series = null; this._requestUpdate = null; }
    updateAllViews() {}
    paneViews() { return this._views; }
    repaint() { if (this._requestUpdate) this._requestUpdate(); }
    setProfiles(profiles) { this._profiles = profiles; this.repaint(); }
    setVisible(name, on) { this._visible[name] = on; this.repaint(); }
  }

  window.IndicatorRegistry.register({
    id: 'micro_zones',
    label: 'Micro zones (TEMP)',
    description: "This tf's VAH/VAL channel + tight runs (30-80 bars) inside it — one profile per timeframe",
    enabledByDefault: false,
    items: () => [
      { id: 'channel', label: 'Channel (VAH/VAL)', color: COL.channel },
      { id: 'micro', label: 'Micro zones', color: COL.micro },
    ],

    create(ctx) {
      const symbol = ctx.symbol || 'NQ';
      const prim = new ZonesPrimitive({ channel: true, micro: true });
      ctx.candleSeries.attachPrimitive(prim);
      let reqId = 0;

      async function update(data, tf, opts) {
        const id = ++reqId;
        if (tf === '1d') { prim.setProfiles([]); return; }
        const asof = opts && opts.asof ? `&asof=${opts.asof}` : '';
        try {
          const res = await fetch(
            `/api/indicators/micro_zones?symbol=${symbol}&tf=${tf}&limit=10000${asof}`,
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
