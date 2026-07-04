/* volume_profile_algo — chart bootstrap
 * TradingView Lightweight Charts v4, dark theme.
 * Candlesticks + volume histogram (overlaid on a scaled bottom band).
 *
 * Data: loadData() tries the Flask API (/api/candles); if that isn't
 * available (e.g. opened directly as a file), it falls back to generated
 * sample data so the chart always renders.
 */

const COLORS = {
  background: '#0e1117',
  text: '#d1d4dc',
  grid: '#1c2230',
  border: '#2a3140',
  up: '#26a69a',
  down: '#ef5350',
  volUp: 'rgba(38, 166, 154, 0.5)',
  volDown: 'rgba(239, 83, 80, 0.5)',
};

function createChart() {
  const el = document.getElementById('chart');
  const chart = LightweightCharts.createChart(el, {
    layout: {
      background: { type: 'solid', color: COLORS.background },
      textColor: COLORS.text,
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    },
    grid: {
      vertLines: { color: COLORS.grid },
      horzLines: { color: COLORS.grid },
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: COLORS.border, labelBackgroundColor: '#2a3140' },
      horzLine: { color: COLORS.border, labelBackgroundColor: '#2a3140' },
    },
    rightPriceScale: {
      borderColor: COLORS.border,
      scaleMargins: { top: 0.08, bottom: 0.25 },
    },
    timeScale: {
      borderColor: COLORS.border,
      timeVisible: true,
      secondsVisible: false,
    },
    autoSize: true,
  });

  const candleSeries = chart.addCandlestickSeries({
    upColor: COLORS.up,
    downColor: COLORS.down,
    borderVisible: false,
    wickUpColor: COLORS.up,
    wickDownColor: COLORS.down,
  });

  const volumeSeries = chart.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: 'vol',
  });
  // Pin volume to the bottom ~20% of the pane.
  chart.priceScale('vol').applyOptions({
    scaleMargins: { top: 0.8, bottom: 0 },
  });

  return { chart, candleSeries, volumeSeries };
}

async function loadData() {
  try {
    const res = await fetch('/api/candles', { cache: 'no-store' });
    if (res.ok) return await res.json();
  } catch (_) {
    /* no backend — fall through to sample data */
  }
  return generateSampleData(400);
}

/* Random-walk OHLCV so the chart looks alive before real data is wired in. */
function generateSampleData(bars) {
  const candles = [];
  const volumes = [];
  let price = 100;
  // Start `bars` days ago, one candle per day.
  const startMs = Date.now() - bars * 86400 * 1000;
  for (let i = 0; i < bars; i++) {
    const time = Math.floor((startMs + i * 86400 * 1000) / 1000);
    const drift = (Math.random() - 0.5) * 2;
    const open = price;
    const close = Math.max(1, open + drift + (Math.random() - 0.5) * 2);
    const high = Math.max(open, close) + Math.random() * 1.5;
    const low = Math.min(open, close) - Math.random() * 1.5;
    candles.push({ time, open, high, low, close });
    volumes.push({
      time,
      value: Math.round(500 + Math.random() * 2000),
      color: close >= open ? COLORS.volUp : COLORS.volDown,
    });
    price = close;
  }
  return { candles, volumes };
}

async function main() {
  const { chart, candleSeries, volumeSeries } = createChart();
  const data = await loadData();

  candleSeries.setData(data.candles);

  // If the backend didn't supply per-bar volume colors, tint them here.
  const volumes = (data.volumes || []).map((v, i) => {
    if (v.color) return v;
    const c = data.candles[i];
    return { ...v, color: c && c.close >= c.open ? COLORS.volUp : COLORS.volDown };
  });
  volumeSeries.setData(volumes);

  chart.timeScale().fitContent();
}

document.addEventListener('DOMContentLoaded', main);
