/* volume_profile_algo — chart bootstrap
 * TradingView Lightweight Charts v4, dark theme.
 * Candlesticks + volume histogram (overlaid on a scaled bottom band).
 *
 * Data: served by chart/server.py from the NQ parquets — the API returns the
 * last ~10k bars for the selected timeframe. A timeframe bar in the header
 * switches between 1m/5m/15m/60m/1d. If no backend is reachable (page opened
 * as a bare file), it falls back to generated sample data so it still renders.
 */

// Set from /api/config at startup (algo_config.yaml is the source of truth).
let SYMBOL = 'NQ';
let CONFIG = {};

/* 12-hour time formatting. Our API sends Unix-second UTC timestamps, so we
 * format in UTC to stay consistent with the data (sessions get proper tz
 * handling once the sessions indicator lands). */
function fmt12h(unixSec) {
  const d = new Date(unixSec * 1000);
  let h = d.getUTCHours();
  const ampm = h >= 12 ? 'PM' : 'AM';
  h = h % 12 || 12;
  return `${h}:${String(d.getUTCMinutes()).padStart(2, '0')} ${ampm}`;
}
function fmtDate(unixSec) {
  const d = new Date(unixSec * 1000);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

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
      vertLines: { visible: false },
      horzLines: { visible: false },
    },
    localization: {
      // Crosshair time label: date + 12-hour time.
      timeFormatter: (t) => `${fmtDate(t)} ${fmt12h(t)}`,
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
      // Axis ticks: 12-hour time for intraday ticks, date for day/month ticks.
      tickMarkFormatter: (time, tickMarkType) =>
        tickMarkType >= 3 ? fmt12h(time) : fmtDate(time),
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

async function fetchConfig() {
  try {
    const res = await fetch('/api/config', { cache: 'no-store' });
    if (res.ok) return await res.json();
  } catch (_) { /* no backend */ }
  return {};
}

async function fetchTimeframes() {
  try {
    const res = await fetch(`/api/timeframes?symbol=${SYMBOL}`, { cache: 'no-store' });
    if (res.ok) {
      const j = await res.json();
      if (j.timeframes && j.timeframes.length) return j.timeframes;
    }
  } catch (_) { /* no backend */ }
  return [];
}

async function loadData(tf) {
  try {
    const res = await fetch(
      `/api/candles?symbol=${SYMBOL}&tf=${tf}&limit=10000`,
      { cache: 'no-store' }
    );
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

function render(chart, candleSeries, volumeSeries, data) {
  candleSeries.setData(data.candles);

  // Tint each volume bar by its candle's direction.
  const volumes = (data.volumes || []).map((v, i) => {
    if (v.color) return v;
    const c = data.candles[i];
    return { ...v, color: c && c.close >= c.open ? COLORS.volUp : COLORS.volDown };
  });
  volumeSeries.setData(volumes);

  chart.timeScale().fitContent();
}

function buildTimeframeBar(timeframes, active, onSelect) {
  const bar = document.getElementById('tf-bar');
  bar.innerHTML = '';
  const buttons = {};
  for (const tf of timeframes) {
    const b = document.createElement('button');
    b.textContent = tf;
    b.classList.toggle('active', tf === active);
    b.addEventListener('click', () => onSelect(tf));
    bar.appendChild(b);
    buttons[tf] = b;
  }
  return buttons;
}

function setStatus(text) {
  const el = document.getElementById('status');
  if (el) el.textContent = text;
}

/* Indicator manager — reads the global registry, renders a floating control
 * panel (master toggle + per-item toggles with color swatches), and keeps
 * enabled indicators in sync with the current data/tf. Indicators are
 * self-contained modules; this is the only thing that drives them
 * (see indicators/registry.js). */
function createIndicatorManager(chart, candleSeries, symbol, config) {
  const defs = window.IndicatorRegistry ? window.IndicatorRegistry.list() : [];
  const active = new Map();      // id -> instance
  const itemState = new Map();   // id -> { itemId: visible }
  let lastData = null;
  let lastTf = null;

  // `items` may be a static array or a function of config (so swatch colors /
  // sub-toggles come from algo_config.yaml).
  function resolveItems(def) {
    return typeof def.items === 'function' ? def.items(config) : (def.items || []);
  }

  function itemsFor(def) {
    if (!itemState.has(def.id)) {
      const s = {};
      for (const it of resolveItems(def)) s[it.id] = true;
      itemState.set(def.id, s);
    }
    return itemState.get(def.id);
  }

  function enable(def) {
    const inst = def.create({ chart, candleSeries, symbol, config });
    active.set(def.id, inst);
    if (lastData) inst.update(lastData, lastTf);
    // Apply any remembered per-item visibility.
    const state = itemsFor(def);
    if (inst.setItemVisible) {
      for (const it of resolveItems(def)) {
        if (!state[it.id]) inst.setItemVisible(it.id, false);
      }
    }
  }

  function disable(def) {
    active.get(def.id).destroy();
    active.delete(def.id);
  }

  // Re-run every enabled indicator against new data (e.g. timeframe switch).
  function onData(data, tf) {
    lastData = data;
    lastTf = tf;
    for (const inst of active.values()) inst.update(data, tf);
  }

  function makeRow(cls, checked, labelHTML, onToggle) {
    const row = document.createElement('label');
    row.className = cls;
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = checked;
    cb.addEventListener('change', () => onToggle(cb.checked));
    const span = document.createElement('span');
    span.innerHTML = labelHTML;
    row.append(cb, span);
    return row;
  }

  function buildUI(container) {
    if (!container) return;
    container.innerHTML = '';
    for (const def of defs) {
      const group = document.createElement('div');
      group.className = 'panel-group';

      const subs = document.createElement('div');
      subs.className = 'panel-subs';

      // Master row.
      const master = makeRow('panel-master', !!def.enabledByDefault, def.label, (on) => {
        on ? enable(def) : disable(def);
        subs.style.display = on ? '' : 'none';
      });
      if (def.description) master.title = def.description;
      group.appendChild(master);

      // Per-item sub-rows with color swatches.
      for (const it of resolveItems(def)) {
        const swatch = `<i class="swatch" style="background:${it.color}"></i>${it.label}`;
        const row = makeRow('panel-item', true, swatch, (on) => {
          itemsFor(def)[it.id] = on;
          const inst = active.get(def.id);
          if (inst && inst.setItemVisible) inst.setItemVisible(it.id, on);
        });
        subs.appendChild(row);
      }
      group.appendChild(subs);
      subs.style.display = def.enabledByDefault ? '' : 'none';

      container.appendChild(group);
      if (def.enabledByDefault) enable(def);
    }
  }

  return { buildUI, onData };
}

async function main() {
  const { chart, candleSeries, volumeSeries } = createChart();

  // Load config first — it drives symbol, default timeframe, and indicator knobs.
  CONFIG = await fetchConfig();
  if (CONFIG.chart && CONFIG.chart.symbol) SYMBOL = CONFIG.chart.symbol;
  const defaultTf = (CONFIG.chart && CONFIG.chart.timeframe) || '5m';

  let timeframes = await fetchTimeframes();
  const hasBackend = timeframes.length > 0;
  if (!hasBackend) timeframes = ['sample'];

  let current = timeframes.includes(defaultTf) ? defaultTf : timeframes[0];
  let buttons = {};

  const indicators = createIndicatorManager(chart, candleSeries, SYMBOL, CONFIG);
  indicators.buildUI(document.getElementById('panel'));

  async function select(tf) {
    current = tf;
    for (const [k, b] of Object.entries(buttons)) b.classList.toggle('active', k === tf);
    setStatus(`${SYMBOL} · ${tf} · loading…`);
    const data = await loadData(tf);
    render(chart, candleSeries, volumeSeries, data);
    indicators.onData(data, tf);
    const n = (data.candles || []).length;
    setStatus(hasBackend ? `${SYMBOL} · ${tf} · ${n.toLocaleString()} bars` : 'sample data (no backend)');
  }

  buttons = buildTimeframeBar(timeframes, current, select);
  await select(current);
}

document.addEventListener('DOMContentLoaded', main);
