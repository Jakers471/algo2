# GRADE spec — one measurement, every scale (design doc, not yet code)

Purpose: kill the drift. Right now each experiment computes a *different subset* of
metrics and represents the volume profile *differently*. The fractal thesis forbids
that: if patterns repeat at every scale, the **same measurement must describe every
scale**. So we pin **one** function, `grade()`, and call it identically on every anchor.

Two concepts only (see LAYERS_NOTES → "two-things model"):
- **ANCHOR** — a contiguous run of bars with a high/low (a container).
- **GRADE** — the fixed metric set computed on an anchor.

---

## 1. The contract

```
grade(bars) -> Grade
```

`bars` = a sequence of OHLCV rows (raw candles OR lower-layer meta-candles — see §4).
`Grade` = the struct below. **Every field is computed for every anchor, always.**
No layer computes a subset; that is the anti-drift rule.

## 2. The metric set (ONE definition each — names are distinct on purpose)

Let `O,C` = open of first / close of last bar; `H,L` = max high / min low;
`range = H - L`; `net = C - O`; `travel = Σ |close_i - close_{i-1}|`.

| field | definition | meaning | notes |
|---|---|---|---|
| `direction` | sign(`net`) | bull / bear / flat | |
| `strength` | `net / range` (−1..+1) | how much of the range was net-directional | this is Layer-1's "net %" |
| `efficiency` | `\|net\| / travel` (0..1) | how *direct* the path was (progress axis) | choppy→0, clean→1 |
| `acceptance` | `1 − va_frac` (0..1) | did volume pile at a POC | `va_frac` = value-area rows ÷ total rows |
| `size` | `range` (pts) | raw extent | |
| `scale` | `range / ATR` | extent normalized to volatility | comparable across time |
| `profile` | `{poc, vah, val}` | the volume profile levels | via `range_hop`/`_profile_for` + `_value_area` |
| `poc_loc` | `(poc − L) / range` | *where* value formed (0 low, 1 high) | |
| `swings` | intrabar direction changes | choppiness | |
| `wicks` | `up_wick`, `low_wick` (÷range) | rejection | |
| `delta` | signed volume (up − down) | pressure | |
| `state` | see §3 | the regime verdict | derived from the above |
| `meta` | `{O,H,L,C, Σvolume}` | the anchor collapsed to ONE candle | enables §4 recursion |

**strength vs efficiency are DIFFERENT and both kept** — a move can end far up
(`strength` high) via a choppy path (`efficiency` low). Never conflate them again.
(Kill the old `range/travel` "path_eff" — `efficiency` = `net/travel` is canonical.)

## 3. State = progress × acceptance (× direction)

Thresholds `E` (efficiency) and `A` (acceptance), config knobs.

|              | acceptance < A (spread) | acceptance ≥ A (fat POC) |
|--------------|-------------------------|--------------------------|
| efficiency ≥ E | **IMPULSE** (dir)      | **GRIND / accumulation** (dir) |
| efficiency < E | **WHIPSAW**            | **CONSOLIDATION** |

Progress states carry `direction`. A fifth honest value — **UNCLEAR** — when the
anchor is too small / near the thresholds (the "not always there" case).

## 4. The recursion (why it's ONE design, not layers of cousins)

Every anchor collapses to one OHLCV `meta` candle (§2). So `grade()` always eats "a
sequence of OHLCV," whether those are raw candles or lower grades' meta-candles.

- **zoom OUT**: grade the sequence of a layer's `meta` candles → the layer above.
- **zoom IN**: inside an anchor, the `state == IMPULSE` runs are the sub-anchors; grade
  each (finer TF) → the layer below.

## 5. Anchors per layer (the ONLY things that change: anchor + timeframe)

| layer | anchor | input | comes from |
|---|---|---|---|
| L1 | the **session** | 5m bars | **clock-given** (session windows) |
| L2 | an **impulse** inside a session | 1m bars | **structure-detected** (L1 grade's IMPULSE runs) |
| L2b | a **consolidation** inside an impulse | 1m bars | its `profile` POC/VAH/VAL |
| L3 | a **multi-session** block | session `meta` candles | zoom-out of L1 grades |

Clock-given at the top, structure-detected below — that is the whole difference
between layers. **Timeframe = input resolution only, NOT a layer.**

## 6. Anti-drift rules (the point of this doc)
1. One formula per metric, one name. No re-defining "efficiency" per script.
2. `grade()` returns the FULL struct every time — no layer computes a subset.
3. The volume profile is always the same object (`{poc,vah,val}` + `va_frac`); shown or
   not is a *view* choice, never a *computation* difference.
4. `range_hop.py` stays the H/L primitive underneath; do not touch it.

## 7. Not in scope yet
Turning grades into trades (score/decide) — that's the pipeline downstream. This doc is
the **fact layer** only: measure structure identically at every scale, first.
