/* chart/static/js/indicators/sessions.js — Sessions High/Low indicator.
 *
 * For each session (Asia / London / NY) on each day:
 *   - draw a DASHED, color-coded horizontal ray from the session's high and low,
 *     extending right until a later candle trades back to the level, then stop;
 *   - draw DASHED vertical lines at the session's start and end, same color.
 *
 * Each session can be toggled independently (see `items` below + the control
 * panel). Session hours are anchored to America/Chicago (exchange tz), DST-aware.
 * Edit SESSIONS to change windows/colors — it's the single source of truth.
 */
(function () {
  // Session windows in Chicago local time, as minutes-from-midnight.
  // A window "wraps" past midnight when end <= start (e.g. Asia 18:00->03:00).
  const SESSIONS = [
    { name: 'Asia',   color: '#3f8ae0', start: 18 * 60, end: 3 * 60 },
    { name: 'London', color: '#e0a44e', start: 3 * 60,  end: 8 * 60 },
    { name: 'NY',     color: '#a06ee0', start: 8 * 60,  end: 17 * 60 },
  ];

  // Cap how many recent session instances we draw, to keep the series count
  // sane on timeframes that span many days.
  const MAX_SESSIONS = 60;

  // ---- Chicago-time helpers (DST-aware via Intl) ----------------------------
  const CHI = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Chicago', hour12: false,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });

  function chicagoParts(unixSec) {
    const o = {};
    for (const p of CHI.formatToParts(new Date(unixSec * 1000))) {
      if (p.type !== 'literal') o[p.type] = p.value;
    }
    return {
      year: +o.year, month: +o.month, day: +o.day,
      hour: (+o.hour) % 24, minute: +o.minute,
    };
  }

  function shiftDay(y, m, d, delta) {
    const dt = new Date(Date.UTC(y, m - 1, d));
    dt.setUTCDate(dt.getUTCDate() + delta);
    return `${dt.getUTCFullYear()}-${dt.getUTCMonth() + 1}-${dt.getUTCDate()}`;
  }

  function sessionFor(localMin) {
    for (const s of SESSIONS) {
      const wraps = s.end <= s.start;
      const inside = wraps
        ? (localMin >= s.start || localMin < s.end)
        : (localMin >= s.start && localMin < s.end);
      if (inside) return s;
    }
    return null;
  }

  // ---- Session computation --------------------------------------------------
  /* Group candles into session instances (one per session per day), tracking
   * each instance's start/end bar and where its high/low occurred. */
  function buildInstances(candles) {
    const byKey = new Map();
    for (let i = 0; i < candles.length; i++) {
      const c = candles[i];
      const p = chicagoParts(c.time);
      const localMin = p.hour * 60 + p.minute;
      const s = sessionFor(localMin);
      if (!s) continue;

      const wraps = s.end <= s.start;
      const dateKey = (wraps && localMin < s.end)
        ? shiftDay(p.year, p.month, p.day, -1)
        : `${p.year}-${p.month}-${p.day}`;
      const key = `${s.name}|${dateKey}`;

      let inst = byKey.get(key);
      if (!inst) {
        inst = {
          name: s.name, color: s.color,
          startIdx: i, endIdx: i,
          hi: -Infinity, hiIdx: i, lo: Infinity, loIdx: i,
        };
        byKey.set(key, inst);
      }
      inst.endIdx = i;
      if (c.high > inst.hi) { inst.hi = c.high; inst.hiIdx = i; }
      if (c.low < inst.lo) { inst.lo = c.low; inst.loIdx = i; }
    }
    return byKey;
  }

  /* First bar after `fromIdx` that trades to `price` (dir +1 = a later high
   * >= price; dir -1 = a later low <= price). Returns that bar's time, or the
   * last bar's time if never tested. */
  function terminate(candles, fromIdx, price, dir) {
    for (let j = fromIdx + 1; j < candles.length; j++) {
      if (dir > 0 ? candles[j].high >= price : candles[j].low <= price) {
        return candles[j].time;
      }
    }
    return candles[candles.length - 1].time;
  }

  /* -> { rays: [{name,color,price,start,end}], verticals: [{name,color,time}] } */
  function computeSessions(candles) {
    const insts = [...buildInstances(candles).values()]
      .sort((a, b) => a.startIdx - b.startIdx)
      .slice(-MAX_SESSIONS);

    const rays = [];
    const verticals = [];
    for (const inst of insts) {
      rays.push({
        name: inst.name, color: inst.color, price: inst.hi,
        start: candles[inst.hiIdx].time,
        end: terminate(candles, inst.hiIdx, inst.hi, +1),
      });
      rays.push({
        name: inst.name, color: inst.color, price: inst.lo,
        start: candles[inst.loIdx].time,
        end: terminate(candles, inst.loIdx, inst.lo, -1),
      });
      verticals.push({ name: inst.name, color: inst.color, time: candles[inst.startIdx].time });
      verticals.push({ name: inst.name, color: inst.color, time: candles[inst.endIdx].time });
    }
    return { rays, verticals };
  }

  // ---- Vertical-line canvas primitive --------------------------------------
  // Lightweight Charts has no native vertical line, so we draw them with a
  // series primitive that paints dashed verticals at given times/colors.
  class VLinesRenderer {
    constructor(src) { this._src = src; }
    draw(target) {
      const chart = this._src._chart;
      if (!chart) return;
      const ts = chart.timeScale();
      target.useMediaCoordinateSpace((scope) => {
        const ctx = scope.context;
        for (const ln of this._src._lines) {
          const x = ts.timeToCoordinate(ln.time);
          if (x === null) continue;
          const px = Math.round(x) + 0.5;
          ctx.save();
          ctx.strokeStyle = ln.color;
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(px, 0);
          ctx.lineTo(px, scope.mediaSize.height);
          ctx.stroke();
          ctx.restore();
        }
      });
    }
  }
  class VLinesPaneView {
    constructor(src) { this._renderer = new VLinesRenderer(src); }
    zOrder() { return 'bottom'; }
    renderer() { return this._renderer; }
  }
  class VLinesPrimitive {
    constructor() {
      this._lines = [];
      this._chart = null;
      this._requestUpdate = null;
      this._views = [new VLinesPaneView(this)];
    }
    attached(p) { this._chart = p.chart; this._requestUpdate = p.requestUpdate; }
    detached() { this._chart = null; this._requestUpdate = null; }
    updateAllViews() {}
    paneViews() { return this._views; }
    setLines(lines) {
      this._lines = lines;
      if (this._requestUpdate) this._requestUpdate();
    }
  }

  // ---- Indicator definition -------------------------------------------------
  window.IndicatorRegistry.register({
    id: 'sessions',
    label: 'Sessions H/L',
    description: 'Asia / London / NY session highs & lows with session boundaries',
    enabledByDefault: true,
    items: SESSIONS.map((s) => ({ id: s.name, label: s.name, color: s.color })),

    create(ctx) {
      const chart = ctx.chart;
      const series = [];
      const visible = { Asia: true, London: true, NY: true };
      let lastData = null;
      let lastTf = null;

      const vlines = new VLinesPrimitive();
      ctx.candleSeries.attachPrimitive(vlines);

      const clearSeries = () => {
        for (const s of series) chart.removeSeries(s);
        series.length = 0;
      };

      function draw() {
        clearSeries();
        const candles = lastData && lastData.candles;
        if (!candles || !candles.length || lastTf === '1d') {
          vlines.setLines([]);
          return;
        }
        const { rays, verticals } = computeSessions(candles);
        for (const r of rays) {
          if (!visible[r.name] || r.end <= r.start) continue;
          const s = chart.addLineSeries({
            color: r.color,
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            lastValueVisible: false,
            priceLineVisible: false,
            crosshairMarkerVisible: false,
          });
          s.setData([
            { time: r.start, value: r.price },
            { time: r.end, value: r.price },
          ]);
          series.push(s);
        }
        vlines.setLines(
          verticals.filter((v) => visible[v.name]).map((v) => ({ time: v.time, color: v.color }))
        );
      }

      return {
        update(data, tf) { lastData = data; lastTf = tf; draw(); },
        setItemVisible(name, vis) { visible[name] = vis; draw(); },
        destroy() { clearSeries(); ctx.candleSeries.detachPrimitive(vlines); },
      };
    },
  });
})();
