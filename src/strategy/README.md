# src/strategy — the trading pipeline

One direction, top to bottom. Each stage does one job and talks to the next only
through a stable contract (never reaching into the previous stage's internals).
Full rules: CLAUDE.md convention #7.

> The filesystem lists these folders alphabetically — **this file is the
> read-it-in-order view.** Folder = pluggable (holds swappable versions);
> file = one fixed thing.

## Execution order (top → bottom)

```
        bars (OHLCV DataFrame)
          │
─ 1 ─  src/indicators/*        RAW math (POC, MAs, volume). SHARED — also feeds
          │                    the chart, so it lives OUTSIDE strategy.        ✅
          ▼
─ 2 ─  readings/               raw indicators → the FACTS we need
          │                    ("price +38 above POC", "MAs stacked up").
          │                    Objective. No opinions. One module per concern.  ✅
          ▼
─ 3 ─  snapshot.py             assemble every reading → ONE Snapshot = THE
          │                    CONTRACT. Monitor + strategy both read this.      ✅
          ▼
─ 4 ─  score/                  facts → weighted signals (0..1) + conviction.
          │                    OPINIONS.   base.py + v1.py                        🟡
          ▼
─ 5 ─  decide/                 scores → a trade Intent (dir/entry/stop/target).
          │                    base.py + v1.py                                    🟡
          ▼
─ 6 ─  manage/                 intent → lifecycle Actions (arm/activate/trail/
          │                    exit/kill). base.py + fixed.py + trailing.py       🟡
          ▼
─ 7 ─  pipeline.py             reads config, wires the chosen versions, runs it.  ✅
          │
          ▼  Action
─ 8 ─  src/brokers/*           execution translates Actions → Broker interface;
                               per-broker adapters. (future)                      ⬜
```

`✅ live · 🟡 seam-only stub (no logic yet) · ⬜ not built`

## How swapping works

`score/`, `decide/`, `manage/` are folders: `base.py` is the seam (interface +
registry); each version is a file beside it that self-registers. The active
version per stage is chosen in `algo_config.yaml`:

```yaml
strategy:
  use:
    scorer:  v1
    decider: v1
    manager: fixed      # ← change one word to swap that stage; nothing else moves
```

Add `score/v2.py`, flip `scorer: v2` — v1 stays untouched next to it (instant A/B).

## Contracts (the stable seams)

`Snapshot` (facts) → `Scores` (opinions) → `Intent` (trade plan) → `Action`
(lifecycle verb). Adding a Snapshot field is additive and safe; renaming/removing
is the only breaking change.

## Run it

```python
from src.strategy import pipeline
import pandas as pd
df = pd.read_parquet("data/NQ/NQ_5m.parquet").tail(2000)
pipeline.run(df, "NQ", "5m")   # -> {snapshot, scores, intent, action}
```

## Watch it — the replay monitor

`tools/replay_monitor.py` runs alongside `chart/server.py` and renders the live
`pipeline.run()` result each replay bar. Pick a layout with `--view`:

```
python tools/replay_monitor.py                    # horizontal (default): bucketed
                                                  #   grid, one boxed column-group
                                                  #   per phase, one row per bar
python tools/replay_monitor.py --view vertical    # funnel block per bar
python tools/replay_monitor.py --view snapshot    # just the SNAPSHOT facts table
```

Phase palette (consistent across views): **SNAPSHOT=cyan · SCORE=yellow ·
DECIDE=magenta · MANAGE=blue**. The SCORE/DECIDE/MANAGE cells show `—` until those
phases have logic — **the layout is already wired; a bucket lights up the moment
its phase returns data** (no monitor change needed).

## State & memory — stateless facts vs. remembered state

Two different kinds of "looking back", in two different places:

- **Facts are stateless** — `readings`/`snapshot`/`score` are recomputed from the
  bars every bar. "Has vexp been rising?" / "near VAH?" are functions of recent bars
  (like rvol's 20-bar lookback), so they need no memory — the bars *are* the memory.
  This is why replay == backtest == live: same inputs → same output, no hidden state.

- **Positions/decisions are remembered** — an armed setup, an open position, a
  trailed stop, a decision that stays ON until invalidated: these exist because of a
  past **decision**, not the bars, so they **cannot be recomputed**. They persist
  across bars as a **`book`** (open positions + armed intents + running log), owned
  by **`manage`** (the stateful stage; `decide` reads it to avoid double-entry).

Status: today `pipeline.run(df, symbol, tf)` is stateless per bar (fine for the
facts base). When `manage` is built, the pipeline gains a driver that threads one
`book` **across** bars — the same object in replay/backtest/live. That driver is
the "brain's memory". (Not built yet — `manage` is a stub.)

## Build order (how the buckets light up)

Build down the pipe; each step surfaces in the monitor as soon as it returns data:

1. **readings/** — design how facts are measured (e.g. price vs POC/VAH/VAL) → add
   modules + Snapshot fields. (SNAPSHOT bucket grows.)
2. **score/v1** — weights turning facts into signals + conviction. (SCORE lights up.)
3. **decide/v1** — rules turning scores into an Intent. (DECIDE lights up.)
4. **manage/** — `fixed`/`trailing` lifecycle turning intent into Actions. (MANAGE lights up.)
5. **execution + brokers/** — translate Actions → the `Broker` interface (tier 8).

Adding a new indicator? Follow the onboarding questions in CLAUDE.md #7.
