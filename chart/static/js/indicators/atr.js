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

      const series = ctx.chart.addLineSeries({
        color: cfg.color,
        lineWidth: 2,
        priceScaleId: 'atr',
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: true,
      });
      // Dock the ATR line in the lower `height` fraction of the pane, on its own
      // auto-scaled price scale (so it fills the band regardless of price level).
      ctx.chart.priceScale('atr').applyOptions({
        scaleMargins: { top: 1 - cfg.height, bottom: 0 },
      });

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
        destroy() { ctx.chart.removeSeries(series); },
      };
    },
  });
})();
