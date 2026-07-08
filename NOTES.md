# NOTES

Running log of vision, decisions, and what we learned. Newest first. Entries are
dated + timed and terse (≤50 lines). Split into `notes/` when this gets large.

---

## 2026-07-07 18:xx — Strategy knobs → config (step 1 of the tune-and-see loop)

**Context:** Jake's real goal for the strategy is a tight *tune-and-see* loop — nudge a
knob, see it play out on the chart, fast. Talked through it: the right shape is **not**
fast replay (that's for watching mechanism) but **overlay + repaint** — compute the
strategy over the whole visible range once and draw regime bands / consolidation boxes /
trade markers; change a knob → refresh → the chart recolors. Two gaps block it: (1) the
tunable knobs were hardcoded in the frozen engine, (2) the strategy output isn't on the
chart yet (only in the terminal monitor).

**Did (step 1):** graduated every hardcoded strategy knob into `algo_config.yaml` —
`strategy.regime` (grade cutoffs), `strategy.consolidation` (base detector),
`strategy.decide` (bias/target). Kept `grade()` **pure**: cutoffs became parameters
(defaults = old constants), and `build_snapshot`/the decider resolve from config + pass
in. So config → live readings/regime/trades, no restart.

**Caching decision (Jake's concern "I don't want cached shit"):** caches are fine *when
keyed by everything the result depends on*. Bars are static (cache freely); regime state
depends on (bars + cutoffs) → keyed the consolidation state cache by the regime knobs, so
a knob change invalidates cleanly. Verified: knob change flips the reading
(CONSOL→GRIND→WHIPSAW), cache holds both configs (95→190), default==explicit grade.

**Regime knobs live now:** `e_cut` (efficiency → trend vs chop), `a_cut` (acceptance →
fat vs thin POC), `n_rows`, `min_bars`. These drive BOTH scales + the base detector — the
biggest lever. See [[strategy-pipeline-architecture]], [[va-breakout-graduation]].

**Next (steps 2-3):** `/api/strategy` endpoint (pipeline across the range → drawable
regime/consol/trades) + a chart overlay renderer → the loop exists. Perf follow-up: cache
`config.load()` by file mtime (avoid a YAML read per bar); make the 120k 1m slice
positional (kill the per-bar mask).

## 2026-07-07 22:xx — Strategy overlay on the chart (tune-and-see loop, steps 2+3)

**Goal reached (first version):** the strategy is now DRAWN on the chart, not just the terminal.
`/api/strategy` runs the pipeline across the range (fresh Driver, same brain) → trades + the base
each broke out of. `chart/static/js/indicators/strategy.js` = a canvas primitive (like
volume_profile.js): entry ▲/▼ → exit ● connector (win green / loss red) + R label + faint stop +
VAH–VAL base box. Toggleable, sub-toggles Trades/Bases.

**The loop:** edit a strategy knob in algo_config.yaml → refresh → overlay recomputes. Backend caches
the batch keyed by the config file's **mtime**, so a config edit invalidates it; unchanged config is
instant (0ms). `config.load()` also mtime-cached now (was re-parsing YAML ~2×/bar).

**Perf:** full-slice batch was ~35ms/bar (O(range²), 108s for 2500 bars — unusable). Fixed with
bounded trailing windows (W5=300 5m, W1=900 1m — both exceed the longest session so snapshots are
identical) + positional searchsorted 1m slicing → O(range). Now ~25-33s for 2500 bars (verified
identical trades). Still slow-ish → "computing strategy…" indicator shows while it runs. Deeper
per-bar speedups (grade/volume-profile caching) = follow-up. See [[va-breakout-graduation]].

**Still owed:** full historical re-backtest of the leg-based anchor (only bounded smoke so far).

## 2026-07-07 21:xx — L2 base made truly fractal (leg-based) + engine dir restore

**Trigger:** Jake looked at `experiments/archive/layer2/leg_profiles.png` and called out that
the 1m base didn't feel like a real fractal reading — `det_window/state_window/min_len/max_age`
are detection tuning, not structure. Correct: L1 grades the SESSION (a natural anchor); the old
L2 used a *third* method (rolling-window CONSOLIDATION-run detector, mirroring
`backtest_equity.collect()`), not legs. So it was "same measurement, different anchoring."

**Decision — Option A (the picture Jake always wanted):** L2 = grade() each **swing leg** within
the session, exactly like the archived `leg_profiles`. Legs = threshold zigzag; threshold =
`swing_frac × session range` (Jake's pick — scale-invariant, couples L2 to its L1 container).
Base judged by a **config-selectable** method (Jake wanted to A/B both): `grade_state`
(`grade(leg).state==CONSOLIDATION`, reuses regime cutoffs — one regime def everywhere) vs
`va_frac` (archived value-area rule + `va_thr`). Levels always from `grade(leg)`.

**Did:** new `experiments/engine/legs.py` (ported zigzag, pure). Rewrote `readings/consolidation.py`
(leg scan, method switch, leg-grade cache keyed by regime knobs). `build_snapshot` slices the
session's 1m bars as the leg window. New `strategy.consolidation` knobs in config + README; kept
the `snapshot.consolidation` field name (no contract break). Bounded Driver smoke: both methods
fire (grade_state strict = few bases; va_frac loose = many) — mechanism validated, **full
re-backtest still owed** (anchor changed → different entries). See [[va-breakout-graduation]],
[[strategy-pipeline-architecture]].

**⚠️ Incident:** mid-session, `experiments/engine/` was wiped from the working tree by something
external (~21:25; all files showed ` D`). My grade.py regime edits were already committed
(`fa7e898`), so `git checkout -- experiments/engine/` restored everything intact. Flag if it
recurs — an editor/sync/cleanup tool is the likely culprit.

## 2026-07-05 15:xx — ATR wired in as an indicator (experimental)

**Context:** explored NQ volatility via a run of throwaway artifacts (time-of-day
volume/vol profile, ATR-over-year, consolidation-vs-impulse fingerprint, Dec 27 2024
by session, points→ATR ruler, session-scoped ATR w/ high-ATR boxes). Jake then asked
to wire ATR into the *actual chart* the same way the other indicators are — flagged
as "most likely temp/experimental."

**Built (standard continuous Wilder ATR, not the session-scoped experiment):** both
halves per CLAUDE.md #5 — `src/indicators/atr.py` (pure; TR = max(H-L, |H-pc|,
|L-pc|), Wilder EMA α=1/period, drop `period-1` warm-up) + renderer
`atr.js`; `atr` config block (`period`/`color`/`height_pct`) + `atr_config()`;
route `/api/indicators/atr`; README + CHANGELOG. Verified: module == manual Wilder
(397.431 on NQ 1d), endpoint 200.

**Key constraint / decision:** vendored Lightweight Charts is **v4.2.0 — no real
sub-panes** (that's v5). So ATR can't be a true MACD/RSI pane; it's docked as an
overlay line on its own auto-scaled price scale pinned to a lower band (the same
trick `volume.js` uses), which means it **shares the lower band with volume**. Left
it **off by default**. If we want a clean dedicated pane later, the move is upgrading
LWC to v5 (`addPane`). ATR-derived overlays (Keltner/ATR-stop/SuperTrend) would be
*separate* price-pane modules, not this one.

---

## 2026-07-05 — Sub-consolidation hunt: two experiments, both shelved

**Goal:** find the *smaller* consolidations inside a session's volume profile
(we already have session H/L, POC, VAH/VAL). Two temp experiments on the chart;
neither kept. Both were self-contained drop-in indicators (math + renderer + route).

**Experiment 1 — `volume_nodes` (detect sub-nodes from the histogram).** Two ways
to pull HVN/LVN out of the profile: **A "peeling"** (reuse POC+value-area, peel the
leftover — eager) vs **B "prominence"** (scipy peak/valley w/ prominence — strict).
Then made 2D (time+price), then a **"budgeted"** version (1 base + ≤2 micro, scale
floor → ≤3 boxes). *Jake: too noisy / "not what I'm looking for."* **Learning that
stuck:** a volume profile *squashes time onto the price axis* — so any sub-node is a
price BAND the full session wide; adding time back by "tightening" just fragments it.
Detect-then-filter is inherently noisy. Deleted.

**Insight kept (→ memory [[mtf-time-scaling]]):** a profile's quality = bars/window.
Session = the natural **5m MTF base** (~60–108 bars); **60m can't bind to a session**
(5–9 bars — its home is a week); window length ∝ timeframe (geometric ladder);
nesting is HTF(60m/week) ⊃ MTF(5m/session=base) ⊃ LTF(1m/~1.5h).

**Experiment 2 — `micro_zones` (VAH/VAL-anchored).** Base = the VAH/VAL channel
(read, not detected); micros = tight-range runs (30–80 bars) *inside* the channel.
v1 mixed 5m-channel + 1m-micros → rendering bug (1m box edges have no 5m bar →
stretched full-width; fixed by snapping to 5m grid). Rebuilt **per-timeframe /
self-contained** (profile + VAH/VAL + micros all on the viewed tf) per Jake's
correction. Then *Jake shelved it.* **Why it doesn't work well:** the micro is a
**price-action** thing (tight range) bolted onto a **volume** thing (value area) —
no shared basis, so zones don't track volume structure; the "every bar inside
VAH/VAL" rule is brittle to wicks; and going single-timeframe dropped the very
LTF-in-MTF-in-HTF nesting that motivated it. **Archived** (not deleted) →
`experiments/micro_zones/` (+ README to re-wire).

**Where it stands:** sub-structure detection is still open. The clean idea hasn't
landed yet; volume + time + scale haven't been unified into one basis.

---

## 2026-07-04 — First reading added: time-based Volume (base-building begins)

Jake's plan: build the FULL fact-base (all readings into the Snapshot) and watch
them in replay BEFORE scoring. First run of the onboarding recipe (CLAUDE #7):
raw indicator → reading → Snapshot field → build_snapshot → monitor column.

Added `readings/volume.py` deriving 3 facts from the per-bar volume indicator:
`bar` (this bar), `rvol` (vs last 20-bar avg — spike >1), `delta` (net signed vol
last 20 bars — buying vs selling). New `volume` field on Snapshot; shown in the
monitor SNAPSHOT bucket beside the profile's session-cumulative `vol` (a distinct
fact). Window=20 hardcoded (TODO: config knob). Verified live: bar 700 / rvol 0.2 /
Δ -11k on the last NQ 5m bar. Next: keep adding readings, then score.

---

## 2026-07-04 — Replay monitor wired to the pipeline; two views

**Decision:** the terminal monitor gets two pipeline layouts + the facts table,
selectable via `--view` (Jake may use either; both maintained):
- `horizontal` (default) — bucketed grid, one boxed column-group per phase, one row
  per bar (the snapshot table extended rightward through the pipeline).
- `vertical` — a funnel block per bar, phases stacked top→bottom.
- `snapshot` — just the SNAPSHOT facts (today's table).

**Consistent phase palette across views:** SNAPSHOT=cyan · SCORE=yellow ·
DECIDE=magenta · MANAGE=blue (tints borders/gutters/labels). Values are semantic
(POC yellow, VAH green/VAL red, conv green ≥0.60, dir/setup green-long/red-short,
stop red/target green). No meters/animation — flat + professional per Jake.

**Wired to the live pipeline:** `/api/replay/state` now returns
`strategy.pipeline.run()` = `{snapshot, scores, intent, action}` (was snapshot
only). Monitor renders whichever view. score/decide/manage are stubs → their cells
show `—`; **the layout is already in place and lights up automatically** as each
phase gets logic (no monitor changes needed). Verified all 3 views on live NQ data.

**Build roadmap (down the pipe, Jake's timeline):** (1) design how VP facts are
measured → fill `readings/` + more Snapshot fields; (2) `score/v1` weights (facts→
signals→conviction); (3) `decide/v1` rules (scores→intent); (4) `manage/`
fixed/trailing lifecycle (intent→actions); (5) execution layer + broker adapter
(actions→Broker). Each step surfaces in the monitor the moment it returns data.

---

## 2026-07-04 — Strategy pipeline scaffold (skeleton only; decisions deferred)

**Locked the mental model** with Jake: `indicators (raw) → readings (facts) →
snapshot (contract) → score (opinions) → decide (intent) → manage (actions) →
pipeline`. readings=facts vs score=opinions kept separate. Stages talk only through
stable contracts (Snapshot/Scores/Intent/Action); adding a Snapshot field is
additive/safe. score/decide/manage are per-stage swappable via a name→version
registry, chosen in `algo_config.yaml → strategy.use`. Documented as CLAUDE.md #7.

**Built the skeleton, NOT the logic (deliberate).** Jake wants to rehearse how he
measures VP numbers / defines weights before any of that is coded. So: `readings/
volume_profile.py` + `snapshot.py` are LIVE but only carry the *same* numbers the
replay reader already showed (session/POC/VAH/VAL/vol + price) — zero new
derivations, zero opinions. `score`/`decide`/`manage` are empty seam stubs;
`pipeline.run()` returns the live snapshot with empty scores/intent/action. Config
has only the `use:` selectors — no weights/thresholds yet.

**Repointed the replay monitor to the TRUE Snapshot:** `/api/replay/state` now
calls `build_snapshot` (the exact object the strategy will consume), monitor reads
`snapshot.*`. Same line on screen, real state underneath.

**Next (Jake's timeline):** design conversation on what facts to derive from VP and
how to measure price relative to them — then fill readings + score. Use the
indicator-onboarding questions each time.

---

## 2026-07-04 — Volume made a first-class indicator module

**Goal (user):** "do with volume as volume profile is" — the time-based volume
histogram was hardcoded into `chart.js` (series built in `createChart`, drawn in
`render`, sliced in replay). Make it modular like every other indicator (conv #5).

**Change:** new two-halves module. Math `src/indicators/volume.py`
`compute_volume(df)` → `{bars:[{time,value,up}]}` (pure; `up=close>=open` so the
frontend can tint direction). Endpoint `/api/indicators/volume` (asof-aware, so
replay recomputes on the revealed slice — parity with the rest). Renderer
`chart/static/js/indicators/volume.js` adds its own `vol` overlay histogram
pinned to the bottom band, fetches + colors per bar, master toggle on by default.

**Why config:** volume math has no numeric knobs, but colors + band height are
tunables → `volume` section in `algo_config.yaml` + `volume_config()`, read by the
renderer via `/api/config` (colors stay config-driven, mirrors sessions).

**Chart core slimmed:** `createChart()` → `{chart, candleSeries}`;
`render(candleSeries, data)`; sample-data mode is candles-only (volume is
API-driven now, so it won't show without a backend — same as the other
indicators). Verified: endpoint + asof slicing return correct bars; JS syntax OK.

---

## 2026-07-04 — Replay readout → separate terminal monitor

**Goal (user):** peel the on-chart replay readout into its own terminal script
that runs alongside — knows when replay starts, then streams the readings — as the
seed of the strategy/backtest consumer. Hard constraint: **replay must stay
snappy** — the monitor must never slow it.

**Design (chart drives, terminal reads, nothing blocks):** the chart
fire-and-forgets its cursor via `navigator.sendBeacon` (never awaited → zero added
latency) to `POST /api/replay/state` (in-memory `{active,symbol,tf,asof}`). The
monitor `tools/replay_monitor.py` polls `GET /api/replay/state` ~10Hz; the server
computes the readout lazily on that poll via `compute_volume_profile` (single
source of truth), cached per-`asof`. So all compute is off the browser loop, on
the monitor's poll. Beacons on enter (`active:true`), each frame (`asof`), exit
(`active:false`) → monitor prints `replay initialised` / line per bar / `ended`.

**Verified** end-to-end via Flask test client: POST→GET returns the live NY
readout (POC/VAH/VAL/vol), exit clears asof, monitor formats the line. stdout
forced to UTF-8 for the `·`/`──` glyphs on Windows. **Format is v1 — tidy next.**

**Note:** poll (not push) to the terminal means fast playback samples frames
(prints latest asof per poll), not every bar — fine for a live readout; raise
`--hz` or revisit if a complete per-bar log is needed for the backtest.

---

## 2026-07-04 — Moving Averages indicator (SMA/EMA, 20 / 50 / 200)

**Added the MA indicator** as a clean two-halves module, following the sessions/
volume-profile pattern so nothing drifts. Math: `src/indicators/moving_average.py`
— per-line `type` sma (rolling mean) or ema (`ewm` span=period, adjust=False) on a
config-selectable `source` (close/open/high/low/hl2/hlc3/ohlc4); one line per
config entry; first `period-1` bars omitted. Config: new `moving_averages` block
in `algo_config.yaml` (`source` + `lines: [{type,period,color}]`) read via
`config.moving_averages_config()`. Server: `/api/indicators/moving_average`
(honors the same `asof` slice → recomputes per replay frame). Renderer:
`moving_average.js` — one LWC line series per line keyed by `type+period` (so
SMA20/EMA20 never collide), colors from config, per-line toggle via
`applyOptions({visible})`; on by default.

**"MAs don't look right" — chased it down:** proved the math is exact (code MA20
== plain mean of last 20 closes to machine precision; data clean: 1.36M rows,
sorted, unique, no NaN, steady 5m spacing). So the numbers are right — the look
was SMA lag on 5m (MA200 ≈ 16h behind). Added EMA to hug price; **user tried both
and prefers SMA**, so defaults are back to `type: sma` (EMA stays a config flip
away per line). Verified endpoint + math after the switch.

**Note:** reverted `main` back to `f9249f7` earlier this session; the session-
character/regime + ML work is parked on branch `character-regime-ml`.

---

## 2026-07-03 21:01 CDT — Replay v1 (the loop that becomes the backtest)

**Built minimal replay.** Backend: added `asof` param to the sessions +
volume_profile endpoints — computes on `df[df.index <= asof]` (same functions, a
growing slice). Frontend: `replay.js` (Play/Pause, 1x/2x/4x, step, scrubber, log
line) + a `replay` button. Each frame reveals bars 0..i, recomputes indicators
as-of `candles[i].time`, tracks the view window, and logs
`session · POC/VAH/VAL · vol`. Enter = from the left of the current view; exit =
restore live.

**Verified:** backend asof grows the NY profile correctly (vol 66k→227k→357k→
470k→562k; POC/VAH/VAL evolve; 100% == full-compute exactly). Controller: start/
step/seek/speed/play(4x ≈140ms/bar)/pause/exit all pass.

**Why this matters (mental model):** replay IS the backtest loop. `for i: frame =
df.iloc[:i]; levels = compute_*(frame)`. Backtest = same loop + a strategy reading
each frame emitting trades; replay-with-trades = draw those on the same frames.
So the strategy/backtest work slots straight onto this.

**v1 shortcuts to revisit:** per-frame API calls (sessions + vp overlay + vp log
+ session_detail) — several redundant volume_profile fetches per frame; fine on
localhost, share one fetch later; view tracks a fixed window; no trade markers
yet (come with the strategy).

**Follow-up (same session):** clicked-session levels now **persist through
replay** — session_detail keeps the selection by identity ({session,start}) and
re-resolves it each as-of frame so its POC/VAH/VAL update live; hidden if the
session hasn't formed yet at the current bar; cleared only on tf change. Verified
headlessly.

---

## 2026-07-03 20:49 CDT — Click-a-session levels + REPLAY vision

**Built (Jake's pick — on-chart, no module):** click a session's span →
`session_detail.js` overlays its H/VAH/POC/VAL/L labeled lines + faint span/VA
shade. Own canvas primitive, fetches its own volume_profile (works whether or not
the VP overlay is on). Click again / empty = clear; tf change clears. Verified
headlessly: hit-test, toggle, draw (5 lines + 5 labels), destroy/unsubscribe.

**Jake's REPLAY vision (next big thing, noted for planning):**
- A **replay tool**: step bars forward (1x/2x/4x), watching POC/VAH/VAL + volume
  profile **recompute live** as bars are revealed. Scrub to any point, cut off,
  play forward.
- Purpose: Jake builds the strategy by *watching* this; then we wire the strategy,
  **backtest bar-by-bar on NQ 5m**, then replay again **with trades drawn**
  (entry/exit/stop, resting positions).
- Also wants **backend logs / script output** of what's happening during replay.
- Mental model to build toward: replay = feed the SAME src/ indicator functions a
  growing slice of bars (df.iloc[:i]) frame by frame; the chart just renders each
  frame. Same math as live/backtest → nothing diverges. Backtest = replay with a
  strategy consuming each frame and emitting trades.
- **Scope now:** just the replay capability (+ maybe a backend log stream). Trades
  come after the strategy/backtest work.

---

## 2026-07-03 20:40 CDT — Persist chart view across refresh

**Jake:** refresh reset the chart to default layout; wanted the exact window
(same zoom + position) + selections restored on reload.

**Done (frontend only):** save `{symbol, tf, visible range, indicator states}` to
`localStorage` (`vpa.viewstate.v1`) on pan/zoom (debounced) + on any toggle, and
restore on load. Removed `fitContent()` from render — `select()` now restores the
saved window on first load, keeps the current window across a timeframe switch,
and only fits when there's nothing saved. Guarded by symbol (won't restore a
different instrument's view). Uses LWC `getVisibleRange`/`setVisibleRange`/
`subscribeVisibleTimeRangeChange` (confirmed in the v4.2 bundle).

**Verified:** indicator state roundtrip (toggle → getState → rebuild from it) is
an exact match; page/assets serve. Range restore relies on the LWC APIs above.

---

## 2026-07-03 20:32 CDT — Perf: rays → canvas primitive; new palette

**Jake compared to a reference chart** (…/algo/algoproj/simplicity, port 8765) —
liked its colors + felt it was snappier/smoother, including the indicator modal.
Read its files directly: it draws overlays as SVG (addLineSeries count = 1).

**Root cause found:** our sessions H/L drew **~120 individual LWC line series**
(60 sessions × high+low). LWC re-projects every series each frame → laggy
pan/zoom; and each panel toggle **tore down + rebuilt** all series → laggy modal.

**Fix:** rewrote `sessions.js` so rays + verticals are ONE canvas primitive
(same technique as the vertical lines / volume profile). Verified headlessly:
**0 addLineSeries calls** (was ~120), 240 canvas strokes, toggling = pure
repaint (no series churn), 1d clears, destroy detaches.

**Palette:** adopted the reference theme — bg #0d0d0d/#1a1a19, text #c3c2b7,
up #199e70, down #e66767, accent #3987e5, borders rgba(255,255,255,.10). Grid
already off.

**Still TODO / noticed:** reference also draws the volume profile as an SVG
overlay and has a richer sidebar (backtest run panel, per-session stat modules,
chat log). Ours' VP is already a single primitive (fine). Their sidebar hints at
the backtest UI we'll build next.

---

## 2026-07-03 20:24 CDT — algo_config.yaml (all knobs) + uniform bins fix

**`algo_config.yaml`** is now the single source of truth for every knob (session
windows+colors, VP row_size + value_area_pct, chart defaults). `src/config.py`
reads it **live** per request — verified: edited row_size 5.0→2.5, `/api/config`
and the computed profile both changed with **no restart**. Backend defaults,
endpoints, and the frontend all resolve knobs through it; `/api/config` feeds the
chart (colors, symbol/tf, params). Indicators refactored to read config; session
windows/tz/cap no longer hardcoded. **This config will also drive the strategy +
backtester.**

**Fixed "bins look different sizes" (Jake):** each session was dividing its own
range into a fixed *count* (24), so wide sessions got taller rows. Switched VP to
a fixed **`row_size`** (price per row) on an **absolute price grid** → every row
is the same height and rows line up across sessions. Verified: all rows exactly
row_size tall, edges on grid, volume conserved, VA≥70%.

**Roadmap (Jake set order):** next = **backtesting framework + wiring up the
strategy** (before more chart features). The config + `src/` split were built to
sit under that. brokers/ has a Broker interface stub; strategy/ + backtest/ are
placeholders ready to fill.

**Verified**: /api/config serves knobs; VP uses config row_size (uniform rows);
query override + live YAML edit both work; renderers pull colors from config
(swatches match), draw, toggle, detach.

---

## 2026-07-03 20:13 CDT — Volume Profile indicator + params discussion

**Built per-session Volume Profile** (`src/indicators/volume_profile.py`): for
each session's high→low range, bin the price, distribute each bar's volume
**overlap-weighted** across the rows it spans (conserves total volume — verified),
then derive **POC** and **value area (VAL/VAH)**. Reuses `session_instances()`.
Served at `/api/indicators/volume_profile`; JS renders a sideways histogram
(value area shaded, POC highlighted + line), per-session toggle, off by default.

**Params clarified with Jake (important design call):**
- `bins`/row-size and `value_area_pct` are **computation parameters in the
  backend**, NOT frontend visual filters. Changing bins → recompute (refetch),
  so the chart and strategy always agree. Verified live: POC moved
  21940→21933→21930 as bins went 12→24→48.
- **POC is an OUTPUT** ("the truth"), not a knob — but its value depends on bin
  resolution. **`value_area_pct` (70%) does NOT move POC**; it only sets how wide
  VAL/VAH sit around it. Session H/L = pure facts.
- For strategy: session H/L + POC are computed signals; the 70% gate (→ VAL/VAH)
  is the tunable hyperparameter if entering off the value edges. All come from
  one `compute_volume_profile(df, bins, value_area_pct)` call.

**Verified**: volume conserved, VAL≤POC≤VAH, VA≥70%, one POC row; API 60
profiles; renderer draws 1440 rects + 60 POC lines, toggles, skips 1d, detaches.

---

## 2026-07-03 20:03 CDT — Backend/frontend split (src/) 

**Decision (Jake):** indicator *logic* belongs in Python, not JS — the algo will
backtest + make entry/exit decisions on the same math the chart shows, so it must
live once. Split the repo into **backend (`src/`)** and **frontend (`chart/`)**.

- **`src/`** = the brain: `indicators/` (pure OHLCV→values math), `strategy/`,
  `brokers/` (Broker interface skeleton), `backtest/`. Placeholders for the last
  three; only sessions math is real so far.
- **`src/indicators/sessions.py`** — ported the session H/L math from JS. Pure,
  DataFrame in / rays+verticals out. Verified it produces **identical** results
  to the old JS (48 rays on 2000 5m bars, same prices/times).
- **`chart/server.py`** = the seam: added `/api/indicators/sessions`, imports
  `src/`. The JS sessions module is now a **thin renderer** (fetch + draw).
- **Rule (now in CLAUDE.md):** anything numeric lives in `src/`, computed once;
  frontend only renders. Colors/styling = frontend; windows/params = backend.

**Verified** full pipeline headlessly: Python compute == JS baseline; API returns
120 rays at 10k/5m (cap 60 instances); slimmed renderer draws + toggles + skips
1d + detaches on destroy. Canvas draw still needs a visual eyeball.

**Gotcha:** hit two stale Flask servers bound to :5000 masking the new route —
kill all python before restarting when testing the server.

---

## 2026-07-03 19:51 CDT — Sessions control panel + vertical boundaries

- **Floating control panel** (chart upper-left): per-indicator master toggle +
  per-item sub-toggles with color swatches. Framework generalized: indicators can
  declare `items` and expose `setItemVisible(id, on)`; `create` now receives
  `{ chart, candleSeries }`. Replaces the old header toggle bar.
- **Sessions H/L**: each session (Asia/London/NY) toggles independently; added
  **dashed vertical lines at session start/end**, same color as the session.
- **Vertical lines** use a Lightweight Charts **series primitive** (no native
  vertical line exists) — one canvas pass draws all boundaries via
  `timeToCoordinate` + `useMediaCoordinateSpace`. Verified the API exists in the
  vendored v4.2 build before relying on it.
- **Verified** headlessly on real 5m NQ data: all-on = 48 rays / 48 verticals;
  toggling Asia off drops both to 32; re-enable restores; 1d clears; destroy
  detaches the primitive. (Canvas rendering itself not machine-checkable — needs
  a visual eyeball.)

---

## 2026-07-03 19:43 CDT — Indicator framework + Sessions H/L

**Built the indicator system** (first of the pluggable chart modules):
- `indicators/registry.js` — global registry; each indicator self-registers.
  The chart renders a toggle button per indicator and drives enable/disable +
  data updates. Indicators never reference each other.
- `indicators/sessions.js` — **Sessions H/L**. Per session (Asia/London/NY) per
  day, find high & low; draw a **dashed, color-coded ray** from that point
  extending right until a later candle trades back to the level, then stop.
  Colors: Asia blue, London amber, NY purple. On by default; skipped on 1d.

**Decisions / assumptions:**
- Session hours anchored to **America/Chicago** (exchange tz), DST-aware via
  `Intl`. Using the "Full sessions" preset hours *as Chicago local time*:
  Asia 18:00–03:00, London 03:00–08:00, NY 08:00–17:00. Single config block at
  top of `sessions.js` — easy to retune. (Note: preset was labeled ET; treated
  literally in CT per the tz choice. Flag if you meant ET clock → convert −1h.)
- One line series per ray (LWC can't put overlapping-time levels in one series).
  Capped at the 60 most-recent session instances (`MAX_SESSIONS`) so high TFs
  spanning many days don't spawn thousands of series.

**Verified** headlessly against real 5m NQ data: rays horizontal, dashed,
well-formed; session assignment matches Chicago windows; 1d draws nothing.

**Deferred:** vertical session-boundary markers (earlier idea) — sticking to the
"just show H/L rays" version for now.

---

## 2026-07-03 19:32 CDT — Project vision & scaffolding

**What this is:** an algorithmic trading strategy project. Core = a volume
profile indicator (plus supporting indicators) driving a strategy, with a
reusable chart UI for visualization.

**Architecture decisions:**
- **Broker abstraction layer.** Strategy logic stays fully decoupled from broker
  code. One standard interface the strategy calls; per-broker adapters translate
  to each API. Swapping/adding a broker must not touch the strategy backend.
- **Indicators = pluggable chart modules.** Each indicator is a self-contained
  module that attaches to the chart and can be toggled on/off individually at
  runtime. Add one by dropping in a module, not editing existing code.

**Indicators planned:**
1. **Volume profile** — the core indicator.
2. **Sessions H/L** — maps each session's high→low: Asia, London, NY
   (separately). Toggleable like the rest.
3. A few more TBD.

**Chart UI (this session):**
- Wired the NQ parquets to the chart via `chart/server.py` (Flask). API returns
  the last 10k bars per timeframe; selector for 1m/5m/15m/60m/1d.
- Requested tweaks: horizontal (time) axis in 12-hour format; remove the chart
  grid.

**Docs process (now enforced via CLAUDE.md):** keep `CHANGELOG.md`, `NOTES.md`,
and `requirements.txt` current as part of every change.

**Roadmap (rough order):** broker abstraction layer → volume profile indicator →
sessions H/L indicator → wire strategy on top.
