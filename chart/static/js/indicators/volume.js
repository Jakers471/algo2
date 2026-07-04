/* chart/static/js/indicators/volume.js — Volume (time-based) RENDERER.
 *
 * The math lives in the backend (src/indicators/volume.py) so the chart and the
 * backtester agree on a bar's volume. This module fetches the computed per-bar
 * values from /api/indicators/volume and draws them as a histogram series pinned
 * to the bottom band of the price pane (its own overlay price scale).
 *
 * Bars are tinted by direction (up = close >= open). Colors and the band height
 * are presentation concerns read from config.volume (with fallbacks here). This
 * is the vertical, by-time counterpart to volume_profile's by-price histogram.
 */
(function () {
  // Fallbacks if config is unavailable; config.volume wins.
  const FALLBACK = {
    up_color: 'rgba(25, 158, 112, 0.5)',
    down_color: 'rgba(230, 103, 103, 0.5)',
    height_pct: 0.20,
  };

  function volCfg(config) {
    const cfg = (config && config.volume) || {};
    return {
      up: cfg.up_color || FALLBACK.up_color,
      down: cfg.down_color || FALLBACK.down_color,
      height: typeof cfg.height_pct === 'number' ? cfg.height_pct : FALLBACK.height_pct,
    };
  }

  window.IndicatorRegistry.register({
    id: 'volume',
    label: 'Volume',
    description: 'Per-bar traded volume (time-based histogram)',
    enabledByDefault: true,

    create(ctx) {
      const symbol = ctx.symbol || 'NQ';
      const cfg = volCfg(ctx.config);

      const series = ctx.chart.addHistogramSeries({
        priceFormat: { type: 'volume' },
        priceScaleId: 'vol',
        lastValueVisible: false,
        priceLineVisible: false,
      });
      // Pin the volume band to the bottom `height` fraction of the pane.
      ctx.chart.priceScale('vol').applyOptions({
        scaleMargins: { top: 1 - cfg.height, bottom: 0 },
      });

      let reqId = 0;

      async function update(data, tf, opts) {
        const id = ++reqId;
        const asof = opts && opts.asof ? `&asof=${opts.asof}` : '';
        try {
          const res = await fetch(
            `/api/indicators/volume?symbol=${symbol}&tf=${tf}&limit=10000${asof}`,
            { cache: 'no-store' }
          );
          const payload = res.ok ? await res.json() : null;
          if (id !== reqId) return;
          const bars = (payload && payload.bars) || [];
          series.setData(bars.map((b) => ({
            time: b.time,
            value: b.value,
            color: b.up ? cfg.up : cfg.down,
          })));
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
