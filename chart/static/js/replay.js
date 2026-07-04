/* chart/static/js/replay.js — replay clock + control bar.
 *
 * Generic stepper: reveals bars from a start point forward at 1x/2x/4x while the
 * host redraws each frame. This module owns only the CONTROLS + cursor + timer;
 * the host provides onFrame(i) (reveal bars 0..i, recompute indicators as-of
 * that bar, return a short log string) and onExit() (restore the live view).
 *
 * Same idea as the backtest loop: step an index forward and recompute on the
 * revealed slice — the math (src/indicators) is identical to live.
 */
(function () {
  const SPEEDS = [1, 2, 4];
  const BASE_MS = 600; // 1x delay per bar; /speed for faster.

  function el(tag, cls, txt) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt != null) e.textContent = txt;
    return e;
  }

  function create({ mount, onFrame, onExit }) {
    let total = 0, i = 0, speed = 1;
    let playing = false, timer = null, active = false;

    mount.innerHTML = '';
    const exitB = el('button', 'rp-btn', '✕'); exitB.title = 'exit replay';
    const stepBk = el('button', 'rp-btn', '◀|');
    const playBtn = el('button', 'rp-btn', '▶');
    const stepFw = el('button', 'rp-btn', '|▶');
    const speedBtns = SPEEDS.map((s) => { const b = el('button', 'rp-btn', s + 'x'); b.dataset.s = s; return b; });
    const slider = el('input', 'rp-slider'); slider.type = 'range'; slider.min = 0; slider.value = 0;
    const counter = el('span', 'rp-count', '0 / 0');
    const log = el('span', 'rp-log', '');

    const nav = el('div', 'rp-grp'); nav.append(stepBk, playBtn, stepFw);
    const sp = el('div', 'rp-grp'); sp.append(...speedBtns);
    mount.append(exitB, nav, sp, slider, counter, log);

    const setSpeedUI = () => speedBtns.forEach((b) => b.classList.toggle('on', +b.dataset.s === speed));
    const setPlayUI = () => { playBtn.textContent = playing ? '❚❚' : '▶'; };
    const ui = () => { counter.textContent = `${i + 1} / ${total}`; slider.value = i; };

    async function frameTo(idx) {
      i = Math.max(0, Math.min(idx, total - 1));
      ui();
      const s = await onFrame(i);
      if (s != null) log.textContent = s;
    }
    const interval = () => Math.round(BASE_MS / speed);

    async function loop() {
      if (!playing) return;
      if (i >= total - 1) { pause(); return; }
      await frameTo(i + 1);
      if (playing) timer = setTimeout(loop, interval());
    }
    function play() {
      if (playing || total === 0) return;
      if (i >= total - 1) i = 0;
      playing = true; setPlayUI(); loop();
    }
    function pause() {
      playing = false; setPlayUI();
      if (timer) { clearTimeout(timer); timer = null; }
    }

    playBtn.onclick = () => (playing ? pause() : play());
    stepFw.onclick = () => { pause(); frameTo(i + 1); };
    stepBk.onclick = () => { pause(); frameTo(i - 1); };
    speedBtns.forEach((b) => { b.onclick = () => { speed = +b.dataset.s; setSpeedUI(); }; });
    slider.oninput = () => { pause(); frameTo(+slider.value); };
    exitB.onclick = () => stop();

    function start(fromIndex, totalBars) {
      active = true; total = totalBars; slider.max = Math.max(0, total - 1);
      speed = 1; setSpeedUI(); setPlayUI();
      mount.style.display = 'flex';
      frameTo(fromIndex || 0);
    }
    function stop() {
      if (!active) return;
      pause(); active = false; mount.style.display = 'none';
      if (onExit) onExit();
    }

    mount.style.display = 'none';
    return { start, stop, isActive: () => active };
  }

  window.Replay = { create };
})();
