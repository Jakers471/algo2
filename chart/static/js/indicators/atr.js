/* chart/static/js/indicators/atr.js — ATR (Average True Range) RENDERER.
 *
 * The math lives in the backend (src/indicators/atr.py) so the chart and the
 * backtester agree on a bar's volatility. This module fetches the computed
 * per-bar values from /api/indicators/atr and draws them as a single line.
 *
 * ATR is a volatility magnitude in price points, not a price level — so it
 * doesn't belong on the price axis. Lightweight Charts v4 has no separate panes,
 * so (like volume.js) we dock it on its OWN overlay price scale pinned to a lower
 * band of the price pane — the closest thing to a MACD/RSI-style sub-panel here.
 * It shares that lower band with the volume histogram; toggle Volume off (or tune
 * atr.height_pct) if you want the strip to itself.
 *
 * period is a backend/config knob; color + band height are presentation, read
 * from config.atr (with fallbacks here). Experimental — off by default.
 */
(function () {
  // Fallbacks if config is unavailable; config.atr wins.
  const FALLBACK = { period: 14, color: '#eb6834', height_pct: 0.18 };

  function atrCfg(config) {
    const cfg = (config && config.atr) || {};
    return {
      period: typeof cfg.period === 'number' ? cfg.period : FALLBACK.period,
      color: cfg.color || FALLBACK.color,
      height: typeof cfg.height_pct === 'number' ? cfg.height_pct : FALLBACK.height_pct,
    };
  }

  window.IndicatorRegistry.register({
    id: 'atr',
    label: 'ATR',
    description: 'Average True Range (Wilder) — volatility, lower band',
    enabledByDefault: false,

    create(ctx) {
      const symbol = ctx.symbol || 'NQ';
      const cfg = atrCfg(ctx.config);

      // v5 has real sub-panes: give ATR its OWN pane below the price pane (a true
      // MACD/RSI-style panel) instead of sharing the price pane's lower band.
      // addSeries auto-creates the pane when the index doesn't exist yet.
      const ATR_PANE = 1;
      const series = ctx.chart.addSeries(LightweightCharts.LineSeries, {
        color: cfg.color,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: true,
      }, ATR_PANE);
      // Size the ATR pane to ~height_pct of the chart. Panes divide space by
      // stretch factor; the main pane keeps its default (1), so h/(1-h) yields
      // roughly `height` of the total. A little scale padding keeps the line off
      // the pane edges. All cosmetic — never fail the indicator over layout.
      try {
        const panes = ctx.chart.panes();
        if (panes[ATR_PANE]) panes[ATR_PANE].setStretchFactor(cfg.height / (1 - cfg.height));
        series.priceScale().applyOptions({ scaleMargins: { top: 0.15, bottom: 0.1 } });
      } catch (_) { /* cosmetic only */ }

      let reqId = 0;

      async function update(data, tf, opts) {
        const id = ++reqId;
        const asof = opts && opts.asof ? `&asof=${opts.asof}` : '';
        try {
          const res = await fetch(
            `/api/indicators/atr?symbol=${symbol}&tf=${tf}&limit=10000${asof}`,
            { cache: 'no-store' }
          );
          const payload = res.ok ? await res.json() : null;
          if (id !== reqId) return;
          const values = (payload && payload.values) || [];
          series.setData(values);
        } catch (_) {
          if (id === reqId) series.setData([]);
        }
      }

      return {
        update,
        destroy() {
          ctx.chart.removeSeries(series);
          // Remove the now-empty ATR pane so the price pane reclaims the space.
          try {
            const panes = ctx.chart.panes();
            if (panes[ATR_PANE] && panes[ATR_PANE].getSeries().length === 0) {
              ctx.chart.removePane(ATR_PANE);
            }
          } catch (_) { /* pane may already be gone */ }
        },
      };
    },
  });
})();
