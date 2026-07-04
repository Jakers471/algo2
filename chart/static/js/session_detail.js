/* chart/static/js/session_detail.js — click a session to draw its levels.
 *
 * Click anywhere inside a session's time span on the main chart to overlay that
 * session's H / VAH / POC / VAL / L (computed by the backend from the config's
 * row_size / value_area_pct). Click the same session again, or an empty area, to
 * clear. Drawn as one canvas primitive — no extra series, no popup module.
 *
 * Self-contained: fetches its own /api/indicators/volume_profile so it works
 * regardless of whether the Volume Profile overlay is toggled on.
 */
(function () {
  const FALLBACK = { Asia: '#3f8ae0', London: '#e0a44e', NY: '#a06ee0' };
  function colorFor(config, name) {
    const wins = config && config.sessions && config.sessions.windows;
    return (wins && wins[name] && wins[name].color) || FALLBACK[name] || '#888888';
  }
  function hexA(hex, a) {
    let h = hex.replace('#', '');
    if (h.length === 3) h = h.split('').map((c) => c + c).join('');
    const n = parseInt(h, 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }
  function fmtPrice(p) {
    const r = Math.round(p * 4) / 4; // nearest 0.25
    return Number.isInteger(r) ? String(r) : String(r);
  }

  // Levels drawn per selected session (label, profile key, style).
  const LEVELS = [
    { key: 'high', label: 'H',   dash: false, weight: 1, alpha: 0.55 },
    { key: 'vah',  label: 'VAH', dash: true,  weight: 1, alpha: 0.9 },
    { key: 'poc',  label: 'POC', dash: false, weight: 2, alpha: 1.0 },
    { key: 'val',  label: 'VAL', dash: true,  weight: 1, alpha: 0.9 },
    { key: 'low',  label: 'L',   dash: false, weight: 1, alpha: 0.55 },
  ];

  class DetailRenderer {
    constructor(src) { this._src = src; }
    draw(target) {
      const s = this._src;
      const prof = s._selected;
      const chart = s._chart, series = s._series;
      if (!prof || !chart || !series) return;
      const ts = chart.timeScale();
      const x1 = ts.timeToCoordinate(prof.start);
      const x2 = ts.timeToCoordinate(prof.end);
      if (x1 === null || x2 === null) return;
      const color = s._colorFor(prof.session);
      const xL = Math.min(x1, x2), xR = Math.max(x1, x2);

      target.useMediaCoordinateSpace((scope) => {
        const ctx = scope.context;
        const H = scope.mediaSize.height;

        // Faint session-span highlight + value-area band.
        ctx.save();
        ctx.fillStyle = hexA(color, 0.05);
        ctx.fillRect(xL, 0, xR - xL, H);
        const yVah = series.priceToCoordinate(prof.vah);
        const yVal = series.priceToCoordinate(prof.val);
        if (yVah !== null && yVal !== null) {
          ctx.fillStyle = hexA(color, 0.09);
          ctx.fillRect(xL, Math.min(yVah, yVal), xR - xL, Math.abs(yVal - yVah));
        }
        ctx.restore();

        // Level lines + right-edge labels.
        ctx.save();
        ctx.font = '11px system-ui, -apple-system, sans-serif';
        ctx.textBaseline = 'middle';
        for (const lv of LEVELS) {
          const y = series.priceToCoordinate(prof[lv.key]);
          if (y === null) continue;
          const py = Math.round(y) + 0.5;
          ctx.strokeStyle = hexA(color, lv.alpha);
          ctx.lineWidth = lv.weight;
          ctx.setLineDash(lv.dash ? [4, 4] : []);
          ctx.beginPath(); ctx.moveTo(xL, py); ctx.lineTo(xR, py); ctx.stroke();

          const text = `${lv.label} ${fmtPrice(prof[lv.key])}`;
          ctx.setLineDash([]);
          const tw = ctx.measureText(text).width;
          const tx = xR + 5;
          ctx.fillStyle = 'rgba(13,13,13,0.72)';
          ctx.fillRect(tx - 3, py - 7.5, tw + 6, 15);
          ctx.fillStyle = hexA(color, 1);
          ctx.fillText(text, tx, py);
        }
        ctx.restore();
      });
    }
  }
  class DetailPaneView {
    constructor(src) { this._renderer = new DetailRenderer(src); }
    zOrder() { return 'top'; }
    renderer() { return this._renderer; }
  }
  class DetailPrimitive {
    constructor() {
      this._selected = null;
      this._chart = null;
      this._series = null;
      this._requestUpdate = null;
      this._colorFor = () => '#888888';
      this._views = [new DetailPaneView(this)];
    }
    attached(p) { this._chart = p.chart; this._series = p.series; this._requestUpdate = p.requestUpdate; }
    detached() { this._chart = null; this._series = null; this._requestUpdate = null; }
    updateAllViews() {}
    paneViews() { return this._views; }
    repaint() { if (this._requestUpdate) this._requestUpdate(); }
    setSelected(p) { this._selected = p; this.repaint(); }
  }

  function create(ctx) {
    const chart = ctx.chart;
    const symbol = ctx.symbol || 'NQ';
    const prim = new DetailPrimitive();
    prim._colorFor = (name) => colorFor(ctx.config, name);
    ctx.candleSeries.attachPrimitive(prim);

    let profiles = [];
    let reqId = 0;
    let lastTf = null;
    let selKey = null; // { session, start } — the selected session's identity

    async function update(tf, opts) {
      const id = ++reqId;
      // A real dataset change (timeframe switch) drops the selection; a replay
      // frame (same tf, new asof) keeps it and re-resolves it below.
      if (tf !== lastTf) { selKey = null; prim.setSelected(null); }
      lastTf = tf;
      if (tf === '1d') { profiles = []; selKey = null; prim.setSelected(null); return; }

      const asof = opts && opts.asof ? `&asof=${opts.asof}` : '';
      try {
        const res = await fetch(
          `/api/indicators/volume_profile?symbol=${symbol}&tf=${tf}&limit=10000${asof}`,
          { cache: 'no-store' }
        );
        const payload = res.ok ? await res.json() : null;
        if (id !== reqId) return;
        profiles = payload ? payload.profiles : [];
      } catch (_) {
        if (id === reqId) profiles = [];
      }
      if (id !== reqId) return;

      // Re-resolve the selected session against the (possibly as-of) profiles so
      // its levels update live during replay; hide it if it hasn't formed yet.
      if (selKey) {
        const m = profiles.find((p) => p.session === selKey.session && p.start === selKey.start);
        prim.setSelected(m || null);
      }
    }

    function onClick(param) {
      if (!param || !param.point) { return; }
      const t = chart.timeScale().coordinateToTime(param.point.x);
      if (t == null) { selKey = null; prim.setSelected(null); return; }
      const hit = profiles.find((p) => t >= p.start && t <= p.end);
      const same = hit && selKey && selKey.session === hit.session && selKey.start === hit.start;
      if (hit && !same) {
        selKey = { session: hit.session, start: hit.start };
        prim.setSelected(hit);
      } else {
        selKey = null;
        prim.setSelected(null);
      }
    }
    chart.subscribeClick(onClick);

    return {
      update,
      destroy() { chart.unsubscribeClick(onClick); ctx.candleSeries.detachPrimitive(prim); },
    };
  }

  window.SessionDetail = { create };
})();
