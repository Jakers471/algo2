/* volume_profile_algo — chart bootstrap
 * TradingView Lightweight Charts v4, dark theme.
 * Candlesticks only here; volume and everything else are pluggable indicator
 * modules (see indicators/) — the chart just hosts them.
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
  background: '#1a1a19',
  text: '#c3c2b7',
  grid: '#1a1a19',
  border: 'rgba(255, 255, 255, 0.10)',
  crosshair: '#898781',
  up: '#199e70',
  down: '#e66767',
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
      vertLine: { color: COLORS.crosshair, labelBackgroundColor: '#2a2a28' },
      horzLine: { color: COLORS.crosshair, labelBackgroundColor: '#2a2a28' },
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

  const candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
    upColor: COLORS.up,
    downColor: COLORS.down,
    borderVisible: false,
    wickUpColor: COLORS.up,
    wickDownColor: COLORS.down,
  });

  return { chart, candleSeries };
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

/* Random-walk OHLC so the chart looks alive before real data is wired in.
 * (Volume is an API-driven indicator now, so sample mode shows candles only.) */
function generateSampleData(bars) {
  const candles = [];
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
    price = close;
  }
  return { candles };
}

function render(candleSeries, data) {
  candleSeries.setData(data.candles);
  // Note: no fitContent() here — the caller decides the visible range so we can
  // restore the saved view (see select() / persisted view state).
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

/* Fire-and-forget: report the replay cursor to the backend so a separate
 * terminal monitor (tools/replay_monitor.py) can read it. NEVER awaited — this
 * must add zero latency to the replay loop. */
function reportReplay(state) {
  try {
    const body = JSON.stringify(state);
    if (navigator.sendBeacon) {
      navigator.sendBeacon('/api/replay/state', new Blob([body], { type: 'application/json' }));
    } else {
      fetch('/api/replay/state', {
        method: 'POST', body, keepalive: true,
        headers: { 'Content-Type': 'application/json' },
      }).catch(() => {});
    }
  } catch (_) { /* telemetry must never break replay */ }
}

/* Indicator manager — reads the global registry, renders a floating control
 * panel (master toggle + per-item toggles with color swatches), and keeps
 * enabled indicators in sync with the current data/tf. Indicators are
 * self-contained modules; this is the only thing that drives them
 * (see indicators/registry.js). */
function createIndicatorManager(chart, candleSeries, symbol, config, opts) {
  const defs = window.IndicatorRegistry ? window.IndicatorRegistry.list() : [];
  const active = new Map();      // id -> instance
  const itemState = new Map();   // id -> { itemId: visible }
  const initialState = (opts && opts.initialState) || {};
  const onChange = (opts && opts.onChange) || (() => {});
  let lastData = null;
  let lastTf = null;
  let lastOpts = null;

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
    if (lastData) inst.update(lastData, lastTf, lastOpts);
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

  // Re-run every enabled indicator against new data (e.g. timeframe switch or a
  // replay frame). `opts` may carry { asof } so indicators recompute on the
  // revealed slice.
  function onData(data, tf, opts) {
    lastData = data;
    lastTf = tf;
    lastOpts = opts || null;
    for (const inst of active.values()) inst.update(data, tf, opts);
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
      const saved = initialState[def.id];
      const on = saved ? !!saved.on : !!def.enabledByDefault;

      // Seed per-item visibility from saved state (defaults to all-on).
      const state = itemsFor(def);
      if (saved && saved.items) {
        for (const k in saved.items) if (k in state) state[k] = !!saved.items[k];
      }

      const group = document.createElement('div');
      group.className = 'panel-group';

      const subs = document.createElement('div');
      subs.className = 'panel-subs';

      // Master row.
      const master = makeRow('panel-master', on, def.label, (checked) => {
        checked ? enable(def) : disable(def);
        subs.style.display = checked ? '' : 'none';
        onChange();
      });
      if (def.description) master.title = def.description;
      group.appendChild(master);

      // Per-item sub-rows with color swatches.
      for (const it of resolveItems(def)) {
        const swatch = `<i class="swatch" style="background:${it.color}"></i>${it.label}`;
        const row = makeRow('panel-item', state[it.id] !== false, swatch, (checked) => {
          itemsFor(def)[it.id] = checked;
          const inst = active.get(def.id);
          if (inst && inst.setItemVisible) inst.setItemVisible(it.id, checked);
          onChange();
        });
        subs.appendChild(row);
      }
      group.appendChild(subs);
      subs.style.display = on ? '' : 'none';

      container.appendChild(group);
      if (on) enable(def);
    }
  }

  // Snapshot of what's on and each indicator's per-item visibility (persisted).
  function getState() {
    const s = {};
    for (const def of defs) {
      s[def.id] = { on: active.has(def.id), items: { ...itemsFor(def) } };
    }
    return s;
  }

  return { buildUI, onData, getState };
}

// Persisted view state (timeframe, visible range, indicator toggles) so a page
// refresh restores exactly what you were looking at instead of resetting.
const VIEW_KEY = 'vpa.viewstate.v1';
function loadViewState() {
  try { return JSON.parse(localStorage.getItem(VIEW_KEY)) || {}; } catch (_) { return {}; }
}

async function main() {
  const { chart, candleSeries } = createChart();

  // Load config first — it drives symbol, default timeframe, and indicator knobs.
  CONFIG = await fetchConfig();
  if (CONFIG.chart && CONFIG.chart.symbol) SYMBOL = CONFIG.chart.symbol;
  const defaultTf = (CONFIG.chart && CONFIG.chart.timeframe) || '5m';

  let timeframes = await fetchTimeframes();
  const hasBackend = timeframes.length > 0;
  if (!hasBackend) timeframes = ['sample'];

  // Restore saved view (only for the same instrument).
  const savedView = loadViewState();
  const sameSymbol = savedView.symbol === SYMBOL;
  let current = (sameSymbol && savedView.tf && timeframes.includes(savedView.tf))
    ? savedView.tf
    : (timeframes.includes(defaultTf) ? defaultTf : timeframes[0]);
  let buttons = {};

  function saveViewState() {
    try {
      localStorage.setItem(VIEW_KEY, JSON.stringify({
        symbol: SYMBOL,
        tf: current,
        range: chart.timeScale().getVisibleRange(),
        indicators: indicators.getState(),
      }));
    } catch (_) { /* storage unavailable */ }
  }
  let saveTimer = null;
  const scheduleSave = () => { clearTimeout(saveTimer); saveTimer = setTimeout(saveViewState, 300); };

  const indicators = createIndicatorManager(chart, candleSeries, SYMBOL, CONFIG, {
    initialState: sameSymbol ? (savedView.indicators || {}) : {},
    onChange: saveViewState,
  });
  indicators.buildUI(document.getElementById('panel'));

  // Click a session's span to overlay its H/VAH/POC/VAL/L levels (no module).
  const sessionDetail = window.SessionDetail
    ? window.SessionDetail.create({ chart, candleSeries, symbol: SYMBOL, config: CONFIG })
    : null;

  let firstLoad = true;
  let fullData = { candles: [] };
  async function select(tf) {
    if (replay && replay.isActive()) replay.stop(); // leave replay on tf switch
    current = tf;
    for (const [k, b] of Object.entries(buttons)) b.classList.toggle('active', k === tf);
    setStatus(`${SYMBOL} · ${tf} · loading…`);

    const prevRange = chart.timeScale().getVisibleRange();
    const data = await loadData(tf);
    fullData = data;
    render(candleSeries, data);
    indicators.onData(data, tf);
    if (sessionDetail) sessionDetail.update(tf);

    // Restore the saved window on first load; keep the same window across a
    // timeframe switch; otherwise fit everything.
    const range = (firstLoad && sameSymbol && savedView.range) ? savedView.range
      : (!firstLoad && prevRange) ? prevRange
      : null;
    try {
      if (range) chart.timeScale().setVisibleRange(range);
      else chart.timeScale().fitContent();
    } catch (_) {
      chart.timeScale().fitContent();
    }
    firstLoad = false;

    const n = (data.candles || []).length;
    setStatus(hasBackend ? `${SYMBOL} · ${tf} · ${n.toLocaleString()} bars` : 'sample data (no backend)');
    saveViewState();
  }

  // ---- Replay ---------------------------------------------------------------
  // Reveal bars forward from a start point while indicators recompute as-of each
  // bar (backend computes on bars <= asof — same math as live). A log line shows
  // the current forming session's values.
  const fmtLevel = (p) => String(Math.round(p * 4) / 4);
  const shortVol = (v) => (v >= 1e6 ? (v / 1e6).toFixed(2) + 'm' : v >= 1e3 ? Math.round(v / 1e3) + 'k' : String(Math.round(v)));

  async function replayLog(asof) {
    try {
      const res = await fetch(
        `/api/indicators/volume_profile?symbol=${SYMBOL}&tf=${current}&limit=10000&asof=${asof}`,
        { cache: 'no-store' }
      );
      if (!res.ok) return `${fmtDate(asof)} ${fmt12h(asof)}`;
      const d = await res.json();
      const profs = d.profiles || [];
      const cur = profs.find((p) => asof >= p.start && asof <= p.end) || profs[profs.length - 1];
      const when = `${fmtDate(asof)} ${fmt12h(asof)}`;
      if (!cur) return when;
      return `${when} · ${cur.session} · POC ${fmtLevel(cur.poc)} · VAH ${fmtLevel(cur.vah)} · VAL ${fmtLevel(cur.val)} · vol ${shortVol(cur.total_volume)}`;
    } catch (_) { return ''; }
  }

  let replayWindow = 120;
  let lastRenderIdx = -1;   // high-water mark of the last candle drawn (for O(1) stepping)
  async function replayFrame(i) {
    const candles = fullData.candles || [];
    if (!candles.length) return '';
    // Candle rendering: stepping forward one bar APPENDS that single bar (O(1)); only a
    // jump/scrub re-loads the slice. Re-setData(all revealed bars) every frame was O(n)
    // per frame -> O(n^2) as bars accumulate — the "slow once candles pile up" bug.
    if (i === lastRenderIdx + 1) {
      candleSeries.update(candles[i]);
    } else {
      candleSeries.setData(candles.slice(0, i + 1));
    }
    lastRenderIdx = i;
    const slice = { candles: candles.slice(0, i + 1) };
    const asof = candles[i].time;
    reportReplay({ active: true, symbol: SYMBOL, tf: current, asof });
    indicators.onData(slice, current, { asof });
    if (sessionDetail) sessionDetail.update(current, { asof });
    try {
      chart.timeScale().setVisibleLogicalRange({
        from: i - replayWindow,
        to: i + Math.round(replayWindow * 0.08),
      });
    } catch (_) { /* ignore */ }
    return replayLog(asof);
  }

  const replay = window.Replay
    ? window.Replay.create({
        mount: document.getElementById('replay'),
        onFrame: replayFrame,
        onExit: () => {
          reportReplay({ active: false });
          lastRenderIdx = -1;                 // next replay re-seeds with a full setData
          // Restore the full, live view.
          render(candleSeries, fullData);
          indicators.onData(fullData, current);
          if (sessionDetail) sessionDetail.update(current);
          try { chart.timeScale().fitContent(); } catch (_) { /* ignore */ }
          const rb = document.getElementById('replayBtn');
          if (rb) rb.classList.remove('active');
        },
      })
    : null;

  function enterReplay() {
    if (!replay || !hasBackend) return;
    const n = (fullData.candles || []).length;
    if (!n) return;
    const range = chart.timeScale().getVisibleLogicalRange();
    replayWindow = range ? Math.max(40, Math.min(Math.round(range.to - range.from), 400)) : 120;
    const startIdx = range ? Math.max(0, Math.min(Math.floor(range.from), n - 1)) : 0;
    const rb = document.getElementById('replayBtn');
    if (rb) rb.classList.add('active');
    lastRenderIdx = -1;                        // first frame does a full setData, then O(1) steps
    reportReplay({ active: true, symbol: SYMBOL, tf: current, asof: null });
    replay.start(startIdx, n);
  }

  const replayBtn = document.getElementById('replayBtn');
  if (replayBtn) {
    replayBtn.addEventListener('click', () => {
      if (replay && replay.isActive()) replay.stop();
      else enterReplay();
    });
  }

  buttons = buildTimeframeBar(timeframes, current, select);
  chart.timeScale().subscribeVisibleTimeRangeChange(scheduleSave);
  await select(current);
}

document.addEventListener('DOMContentLoaded', main);
