/* chart/static/js/indicators/moving_average.js — Moving Averages RENDERER.
 *
 * The math lives in the backend (src/indicators/moving_average.py) so the chart
 * and the backtester agree. This module fetches the computed per-bar values from
 * /api/indicators/moving_average and draws one Lightweight-Charts line series per
 * configured period (20 / 50 / 200 by default), on the price scale.
 *
 * Periods live in the backend/config; colors are a frontend (presentation)
 * concern read from config.moving_averages (with a fallback here). Each line
 * toggles independently via the control panel.
 */
(function () {
  // Fallback lines if config is unavailable; config.moving_averages.lines wins.
  const FALLBACK = [
    { type: 'ema', period: 20, color: '#4fc3f7' },
    { type: 'ema', period: 50, color: '#ffb74d' },
    { type: 'ema', period: 200, color: '#ba68c8' },
  ];

  // Stable key per line so SMA20 and EMA20 never collide.
  const lineKey = (type, period) => `${type}${period}`;

  function maList(config) {
    const cfg = config && config.moving_averages;
    const lines = (cfg && cfg.lines && cfg.lines.length) ? cfg.lines : FALLBACK;
    return lines.map((l) => {
      const type = (l.type || 'sma').toLowerCase();
      return {
        id: lineKey(type, l.period),
        type,
        period: l.period,
        color: l.color || '#888888',
        label: (type === 'ema' ? 'EMA ' : 'MA ') + l.period,
      };
    });
  }

  window.IndicatorRegistry.register({
    id: 'moving_average',
    label: 'Moving Averages',
    description: 'Simple moving averages of price (20 / 50 / 200)',
    enabledByDefault: true,
    items: (config) => maList(config).map((m) => ({ id: m.id, label: m.label, color: m.color })),

    create(ctx) {
      const symbol = ctx.symbol || 'NQ';
      const list = maList(ctx.config);

      // One line series per MA. Kept lean: no price line, no last-value label, no
      // crosshair marker — these are context lines, not the primary series.
      const series = {};
      for (const m of list) {
        series[m.id] = ctx.chart.addSeries(LightweightCharts.LineSeries, {
          color: m.color,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
          priceScaleId: 'right',
        });
      }

      let reqId = 0;

      async function update(data, tf, opts) {
        const id = ++reqId;
        const asof = opts && opts.asof ? `&asof=${opts.asof}` : '';
        try {
          const res = await fetch(
            `/api/indicators/moving_average?symbol=${symbol}&tf=${tf}&limit=10000${asof}`,
            { cache: 'no-store' }
          );
          const payload = res.ok ? await res.json() : null;
          if (id !== reqId) return;
          const byKey = {};
          if (payload && payload.lines) {
            for (const ln of payload.lines) byKey[lineKey(ln.type, ln.period)] = ln.values || [];
          }
          for (const m of list) series[m.id].setData(byKey[m.id] || []);
        } catch (_) {
          if (id === reqId) for (const m of list) series[m.id].setData([]);
        }
      }

      return {
        update,
        // Toggle visibility without dropping data (keeps the last computed line).
        setItemVisible(itemId, vis) {
          if (series[itemId]) series[itemId].applyOptions({ visible: vis });
        },
        destroy() {
          for (const m of list) ctx.chart.removeSeries(series[m.id]);
        },
      };
    },
  });
})();
