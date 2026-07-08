/* chart/static/js/indicators/strategy.js — STRATEGY overlay RENDERER.
 *
 * Math lives in src/strategy/* (the pipeline). This module fetches the pipeline's
 * result over the loaded range from /api/strategy and draws it ON the chart:
 *   - BASES  : the consolidation base each trade broke out of (VAH..VAL box over its span).
 *   - TRADES : entry ▲/▼ + exit ●, connected by a line tinted by outcome (win green /
 *              loss red), with the R printed at the exit; the stop shown as a faint line.
 *
 * This is the tune-and-see loop: edit a strategy knob in algo_config.yaml (regime /
 * consolidation / decide), refresh, and the overlay recomputes — the backend keys its
 * cache on the config file's mtime, so a config edit re-runs the pipeline. Colors are a
 * frontend concern and live here (mirrors the other indicators).
 */
(function () {
  const LONG = '#199e70', SHORT = '#e66767';
  const WIN = '#199e70', LOSS = '#e66767';
  const BASE = '#c9a227';                 // consolidation base (amber, like POC)
  const STOP = 'rgba(230,103,103,0.55)';
  const TEXT = '#c3c2b7';

  function rgba(hex, a) {
    const h = hex.replace('#', '');
    return `rgba(${parseInt(h.slice(0, 2), 16)},${parseInt(h.slice(2, 4), 16)},${parseInt(h.slice(4, 6), 16)},${a})`;
  }

  // ---- canvas primitive ----------------------------------------------------
  class StrategyRenderer {
    constructor(src) { this._src = src; }
    draw(target) {
      const chart = this._src._chart, series = this._src._series;
      if (!chart || !series) return;
      const ts = chart.timeScale();
      const vis = this._src._visible;
      target.useMediaCoordinateSpace((scope) => {
        const ctx = scope.context;
        if (this._src._loading) {         // recompute in progress (the pipeline is slow)
          ctx.save();
          ctx.fillStyle = rgba(BASE, 0.9);
          ctx.font = '12px -apple-system, system-ui, sans-serif';
          ctx.textBaseline = 'top';
          ctx.fillText('computing strategy…', 12, 10);
          ctx.restore();
        }
        for (const tr of this._src._trades) {
          const xe = ts.timeToCoordinate(tr.entry_time);
          const xx = ts.timeToCoordinate(tr.exit_time);
          const ye = series.priceToCoordinate(tr.entry);
          const yx = series.priceToCoordinate(tr.exit);
          const long = tr.direction === 'long';

          // --- base box (VAH..VAL over the base's span) ---
          if (vis.bases && tr.base_vah != null && tr.base_start != null) {
            const x0 = ts.timeToCoordinate(tr.base_start);
            const x1 = ts.timeToCoordinate(tr.base_end);
            const yTop = series.priceToCoordinate(tr.base_vah);
            const yBot = series.priceToCoordinate(tr.base_val);
            if (x0 !== null && x1 !== null && yTop !== null && yBot !== null) {
              ctx.fillStyle = rgba(BASE, 0.10);
              ctx.fillRect(x0, yTop, Math.max(x1 - x0, 1), Math.max(yBot - yTop, 1));
              ctx.strokeStyle = rgba(BASE, 0.75);
              ctx.lineWidth = 1;
              ctx.strokeRect(x0 + 0.5, yTop + 0.5, Math.max(x1 - x0, 1), Math.max(yBot - yTop, 1));
            }
          }

          if (!vis.trades || xe === null || ye === null) continue;

          // --- stop line (faint) ---
          if (xx !== null) {
            const ys = series.priceToCoordinate(tr.stop);
            if (ys !== null) {
              ctx.save();
              ctx.strokeStyle = STOP; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
              ctx.beginPath(); ctx.moveTo(xe, ys); ctx.lineTo(xx, ys); ctx.stroke();
              ctx.restore();
            }
          }

          // --- entry -> exit connector, tinted by outcome ---
          if (xx !== null && yx !== null) {
            ctx.save();
            ctx.strokeStyle = rgba(tr.R > 0 ? WIN : LOSS, 0.9);
            ctx.lineWidth = 1.5;
            ctx.beginPath(); ctx.moveTo(xe, ye); ctx.lineTo(xx, yx); ctx.stroke();
            ctx.restore();
          }

          // --- entry marker (triangle: up for long, down for short) ---
          const dcol = long ? LONG : SHORT;
          ctx.fillStyle = dcol;
          ctx.beginPath();
          const s = 5;
          if (long) { ctx.moveTo(xe, ye - s); ctx.lineTo(xe - s, ye + s); ctx.lineTo(xe + s, ye + s); }
          else { ctx.moveTo(xe, ye + s); ctx.lineTo(xe - s, ye - s); ctx.lineTo(xe + s, ye - s); }
          ctx.closePath(); ctx.fill();

          // --- exit marker + R label ---
          if (xx !== null && yx !== null) {
            ctx.fillStyle = rgba(tr.R > 0 ? WIN : LOSS, 0.95);
            ctx.beginPath(); ctx.arc(xx, yx, 3.5, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = TEXT;
            ctx.font = '10px -apple-system, system-ui, sans-serif';
            ctx.textBaseline = 'middle';
            ctx.fillText(`${tr.R > 0 ? '+' : ''}${tr.R.toFixed(1)}R`, xx + 6, yx);
          }
        }
      });
    }
  }
  class StrategyPaneView {
    constructor(src) { this._renderer = new StrategyRenderer(src); }
    zOrder() { return 'top'; }
    renderer() { return this._renderer; }
  }
  class StrategyPrimitive {
    constructor(visible) {
      this._trades = [];
      this._loading = false;
      this._visible = visible;         // { trades: bool, bases: bool }
      this._chart = null; this._series = null; this._requestUpdate = null;
      this._views = [new StrategyPaneView(this)];
    }
    attached(p) { this._chart = p.chart; this._series = p.series; this._requestUpdate = p.requestUpdate; }
    detached() { this._chart = null; this._series = null; this._requestUpdate = null; }
    updateAllViews() {}
    paneViews() { return this._views; }
    repaint() { if (this._requestUpdate) this._requestUpdate(); }
    setTrades(t) { this._trades = t; this._loading = false; this.repaint(); }
    setLoading(on) { this._loading = on; this.repaint(); }
    setVisible(id, on) { this._visible[id] = on; this.repaint(); }
  }

  // ---- indicator definition ------------------------------------------------
  // The strategy runs across the range once (heavier than a raw indicator), so we ask
  // for a bounded recent slice, not the full 10k the chart loads.
  const STRATEGY_LIMIT = 2500;

  window.IndicatorRegistry.register({
    id: 'strategy',
    label: 'Strategy (VA breakout)',
    description: 'The pipeline drawn on the chart: consolidation bases + trades (edit strategy knobs in algo_config.yaml, refresh)',
    enabledByDefault: false,
    items: [
      { id: 'trades', label: 'Trades', color: LONG },
      { id: 'bases', label: 'Bases', color: BASE },
    ],

    create(ctx) {
      const symbol = ctx.symbol || 'NQ';
      const prim = new StrategyPrimitive({ trades: true, bases: true });
      ctx.candleSeries.attachPrimitive(prim);
      let reqId = 0;

      async function update(data, tf, opts) {
        const id = ++reqId;
        // Replay drives its own per-bar view; the batch overlay is for the static chart.
        if (opts && opts.asof) { prim.setTrades([]); return; }
        prim.setLoading(true);
        try {
          const res = await fetch(
            `/api/strategy?symbol=${symbol}&tf=${tf}&limit=${STRATEGY_LIMIT}`,
            { cache: 'no-store' }
          );
          const payload = res.ok ? await res.json() : null;
          if (id !== reqId) return;
          prim.setTrades(payload && payload.trades ? payload.trades : []);
        } catch (_) {
          if (id === reqId) prim.setTrades([]);
        }
      }

      return {
        update,
        setItemVisible(itemId, vis) { prim.setVisible(itemId, vis); },
        destroy() { ctx.candleSeries.detachPrimitive(prim); },
      };
    },
  });
})();
