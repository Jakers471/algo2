# Layers — design notes (fractal regime structure)

Running log of the "grade price structure by scale" idea. Jake's messages quoted
**verbatim** (typos and all — his exact words matter); responses summarized. Newest
at the bottom. This is the thinking record behind `experiments/layer1/` and beyond.

---

## The idea in one line

Price is fractal — it goes up / down / sideways at every timeframe, only the
duration changes. So there is **one engine** ("take a leg, decide if it trended or
cancelled itself out" = a directional move + its retracement, i.e. `range_hop` +
retracement thresholds), run at different **zoom levels**:

- **Layer 1** — the engine on a **session as one unit** → is this session bull / bear
  / chop? (net % of range, POC, path efficiency, swings, …). ✅ built.
- **Layer 2** — **zoom IN**: decompose one session into its **sequence of legs**
  (bull impulse → range → break → bear → range …). Same engine, smaller scale.
- **Layer 3** — **zoom OUT**: **stitch sessions** into a larger move. Same engine,
  bigger scale.

Key realization: **consolidation is not the absence of trend — it's trends that
cancel.** Chop at scale N = a sequence of trends + consolidations at scale N−1. The
volume-profile POC/VAH/VAL is where a sub-leg *paused* (a range node between impulses).

Honest constraint: **it's not always cleanly there.** The engine must return however
many legs it actually finds (1 = clean trend, N = structured); never a forced count.
That count is itself a feature (few legs = trending, many = choppy).

`range_hop.py` (session H/L) is the solid foundation — do not touch it.

---

## Log

**1 — Break sequence.** Jake: *"count in sequence whats happening upon each break,
so every break is bullish or bearish yes. theres a hidden sequence… bull > bull >
bear > bull > bear > bear… show me like % chance 1 bull turn to two bull to three…
find the most bull/bear runs, then show me the chances of them happening. give me the
command to run"* (run from Nov 27, within the 10k chart bars).
→ Built `break_sequence.py`: per-session bull/bear (close beyond prior session range),
run-length + continuation odds.

**2–4 — Make it readable.** Jake found the table jargon (`len / #runs>=k / B/E`)
unintuitive: *"idk what ur abbreviatiosn shit mean its not clicking."*
→ Rewrote output as plain-English sentences.

**5 — More data.** Jake: *"we only rna this on like a couplle motnhs… whats the last
data we have, what day for nq?"* → Last NQ bar **2025-01-10**; data back to 2005
(~20y). Full-history run: the couple-months "edge" (86% at 2→3) was small-sample
noise; over 20y bull continuation is a steady ~58%, bears mean-revert.

**6 — Regimes + magnitude.** Jake: *"remebr we are trying to find regimes… esentially
bull/bear and ocnsoldiation… find the maginitude of eahc move relative to previous
moves… 3 bullish breaks then one bearish break takes out all 3 previous bull sesison
lows… 2 bullish moves up and one down, thats… re accumulation before the next
continuation… dont code yet."*
→ Framed: direction says WHAT, magnitude says WHETHER IT MATTERS. Magnitude =
structural depth / retracement (how much of the opposing run it takes back).

**7 — Retracement zones.** Jake: *"if 2 buls move 100 points combind, then the next
bar only retraces 30% … thats just a reaccoumulton… still bull, just bear on smaller
scale… when trend retraces say 50%, thats when direction gets fuzzy… reversal around
70-100%… consoldiation if 3 or 4 breaks flipping or they dont move much… just build
the script im curious to see."*
→ Built `regime.py`: leg tracker with retrace zones (<50% pullback / 50-70% fuzzy /
≥70% reversal) + consolidation. First cut flipped every 2 sessions (leg origin
trailed too tight); fixed to trail only to confirmed higher-lows.

**8 — Visual check.** Jake: *"letme make sur eyou have this design corretc… show me a
png of some of the regimes it found with candlesticks on."*
→ `regime_plot.py`: bull/bear trends matched price; **consolidation never fired** — the
boxed-range test was knife-edge (1.5x → 2%, 2.5x → 72%). Diagnosis: consolidation
needs a proper basis (efficiency ratio), not range-vs-range.

**9 — Build from the atom.** Jake: *"this needs ot be built out proprotiannly… the
range_hop is solid as fuck. neevr mess wit it. the regime now needs to think in
smallest units first… show me all the info we can derive form a single session, png…
ny sesisons oonly. hw many dimensions can we extrarct?"*
→ `session_anatomy.py`: ~15 atomic dimensions per session. **`net % of range`** is the
master trend/chop grade (±89% strong trend vs ±3% chop) — and the chop sessions had
*bigger* ranges than the bull, proving "small range" was never the signal;
"big range but net ≈ 0" is chop.

**10 — Foldering.** Jake: *"archive regime plot, regime.py… layer 1 (smallest) folder…
session anatomy."* → `experiments/archive/` (micro_zones + regime attempt),
`experiments/layer1/` (session_anatomy).

**11 — Commit.** *"commit eveyrhitng too. call commit layer one."*

**12 — Volume profile.** Jake: *"add volume range profile. with poc line… draws form
sesison low/high… just more ifo for session anaomty in ayer 1 … on the sam epng."*
→ Added per-session volume histogram + POC (17th dimension: *where* the session found
value, independent of how far it moved).

**13 — Fractal realization.** Jake: *"were almost creeping into layer 2 here with
volume profile… the songest bull and bear carry consolidatory periods… chop 2 kind of
has 2 ocnsoldiaiton periods within it… it needs to be tracked in sequence… price is
fratcal… bullish > consodiaiton > bullish > consoldiaiton > bullish… on a sesisons
perspective, chop #2 is indeed chop because the move retraced itself… layer 3 will
maybe be stitching a sesison to a sesison… its not always there."*
→ Response: it's **one engine at three zoom levels** (L1 session-as-unit, L2 zoom-in
to leg sequence, L3 zoom-out to stitch sessions). Consolidation = trends that cancel.
Engine must return however many legs it finds (count = a feature). Proposed next step:
decompose ONE session (chop #2) on 1m into its leg sequence, visualize, falsify before
generalizing.

**14 — Layer 2 built (`experiments/layer2/session_legs.py`).** Ran the engine (threshold
zigzag, reversal = `swing_frac` × session range) on each session's **1-min** bars.
**Fractal confirmed:** strong bull = few legs, one-sided, stepping (bull→pullback→bull);
chop = many legs that cancel (chop#1 = 31 legs, 16 up / 15 down; chop#2 = 19 legs).
Chop #2 matched Jake's verbal read (open range → rip up +188 → top → −131 down → drift →
range). Jake: *"leg count isnt a sperateor"* (agreed — bear 15 vs chop#2 19 too close),
and the crude local-range **blue boxes were bad → removed.**

**Anchor realization (Jake):** *"the sessions/range hop/volume profile… it was bult off
the sessions. in my head, no matter what timeframe we are looking at we do the same thing,
but it needs anchors. obviously ltf is more noisy… chop 1 has a slower grind up, chop 2 a
faster intial grind up, so its cleaner to build volume profile around that to capture the
big legs to the smaller consolidatory legs."*
→ The anchor should shift from the **session** (a clock container) to the **leg** (a
structure container): hang the volume profile / H/L / retracement off each LEG, same ops.
And the **volume-profile SHAPE** is the real impulse-vs-consolidation detector — thin/
spread = impulse (price ran through), fat POC = consolidation (price accepted) — which
also replaces the removed range boxes.

---

## Open questions / to decide
- Layer 2 unit: legs from the retracement engine on a lower TF (1m) *inside* a session. ✅
- **Anchor = the LEG, not the session** (structure-based, not clock-based). Build volume
  profile per leg.
- **Consolidation via volume-profile SHAPE** (POC concentration / fat vs thin), not leg
  count and not crude range boxes.
- Chop grade: net% (L1) + up-vs-down leg *size* balance (L2) — two independent reads.
- Where the fractal "isn't always there" (ambiguous sessions) — represent "unclear" as a
  first-class state, not a forced label.
