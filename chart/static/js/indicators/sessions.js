/* chart/static/js/indicators/sessions.js — Sessions High/Low indicator.
 *
 * For each session (Asia / London / NY) on each day, find that session's high
 * and low, then draw a DASHED, color-coded horizontal ray from the high/low
 * point extending RIGHT until a later candle trades back to that level, then
 * stop. Same color per session for its high and its low.
 *
 * Session hours are anchored to America/Chicago (the data's exchange tz),
 * DST-aware. Edit SESSIONS below to change windows/colors — it's the single
 * source of truth. (Hours picked from the "Full sessions" preset.)
 */
(function () {
  // Session windows in Chicago local time, as minutes-from-midnight.
  // A window "wraps" past midnight when end <= start (e.g. Asia 18:00->03:00).
  const SESSIONS = [
    { name: 'Asia',   color: '#3f8ae0', start: 18 * 60, end: 3 * 60 },
    { name: 'London', color: '#e0a44e', start: 3 * 60,  end: 8 * 60 },
    { name: 'NY',     color: '#a06ee0', start: 8 * 60,  end: 17 * 60 },
  ];

  // Cap how many recent session instances we draw, to keep series count sane
  // on timeframes that span many days (each instance = up to 2 ray series).
  const MAX_SESSIONS = 60;

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

  /* Group candles into session instances (one per session per day), tracking
   * each instance's high/low and the bar index where each occurred. */
  function buildInstances(candles) {
    const byKey = new Map();
    for (let i = 0; i < candles.length; i++) {
      const c = candles[i];
      const p = chicagoParts(c.time);
      const localMin = p.hour * 60 + p.minute;
      const s = sessionFor(localMin);
      if (!s) continue;

      const wraps = s.end <= s.start;
      // Anchor after-midnight bars of a wrapping session to the day it started.
      const dateKey = (wraps && localMin < s.end)
        ? shiftDay(p.year, p.month, p.day, -1)
        : `${p.year}-${p.month}-${p.day}`;
      const key = `${s.name}|${dateKey}`;

      let inst = byKey.get(key);
      if (!inst) {
        inst = { color: s.color, hi: -Infinity, hiIdx: i, lo: Infinity, loIdx: i };
        byKey.set(key, inst);
      }
      if (c.high > inst.hi) { inst.hi = c.high; inst.hiIdx = i; }
      if (c.low < inst.lo) { inst.lo = c.low; inst.loIdx = i; }
    }
    return byKey;
  }

  /* First bar after `fromIdx` that trades to `price` (dir +1 = high tested when
   * a later high >= price; dir -1 = low tested when a later low <= price).
   * Returns that bar's time, or the last bar's time if never tested. */
  function terminate(candles, fromIdx, price, dir) {
    for (let j = fromIdx + 1; j < candles.length; j++) {
      if (dir > 0 ? candles[j].high >= price : candles[j].low <= price) {
        return candles[j].time;
      }
    }
    return candles[candles.length - 1].time;
  }

  function computeRays(candles) {
    const insts = [...buildInstances(candles).values()]
      // Keep the most recent MAX_SESSIONS instances (by when their high formed).
      .sort((a, b) => a.hiIdx - b.hiIdx)
      .slice(-MAX_SESSIONS);

    const rays = [];
    for (const inst of insts) {
      rays.push({
        color: inst.color, price: inst.hi,
        start: candles[inst.hiIdx].time,
        end: terminate(candles, inst.hiIdx, inst.hi, +1),
      });
      rays.push({
        color: inst.color, price: inst.lo,
        start: candles[inst.loIdx].time,
        end: terminate(candles, inst.loIdx, inst.lo, -1),
      });
    }
    return rays;
  }

  window.IndicatorRegistry.register({
    id: 'sessions',
    label: 'Sessions H/L',
    description: 'Asia / London / NY session highs & lows — dashed rays until tested',
    enabledByDefault: true,
    create(chart) {
      const series = [];
      const clear = () => { for (const s of series) chart.removeSeries(s); series.length = 0; };

      function update(data, tf) {
        clear();
        const candles = data && data.candles;
        if (!candles || !candles.length) return;
        if (tf === '1d') return; // sessions are an intraday concept

        for (const r of computeRays(candles)) {
          if (r.end <= r.start) continue; // degenerate (formed on the last bar)
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
      }

      return { update, destroy: clear };
    },
  });
})();
