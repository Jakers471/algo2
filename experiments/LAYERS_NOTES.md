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

## The two-things model (crystallized 2026-07-05)

The whole system is only **two things**:

1. **ANCHOR** — a high/low container. A *session* is an anchor; an *impulse* is an
   anchor; a *consolidation* is an anchor.
2. **GRADE** — the fixed metric set computed on an anchor: direction, efficiency
   (net ÷ travel), acceptance (volume concentration), size, and the volume profile
   (POC / VAH / VAL).

"Layers" = **the same GRADE on smaller and smaller ANCHORS.** The loop:
grade an anchor → its grade reveals the **impulses** inside → **each impulse becomes a
new anchor** → grade those → recurse (zoom out = anchors merge).

- Layer 1's anchor (the **session**) is **clock-given** — arbitrary but convenient.
- Every deeper anchor is **structure-detected** (an **impulse**). That is the only real
  difference between layers: clock-given at the top, structure-detected below.

**No drift.** The fractal thesis *forbids* metric drift: if patterns reproduce at every
scale, the SAME measurement must describe every scale, or you can't compare across them.
Our current drift (each script computed a different subset — anatomy = full grade static;
leg_states = 2 axes hiding the profile as `va_frac`; leg_profiles = the drawn profile per
leg) is an accident of separate scripts, not a design choice. Fix = compute ONE full grade
on EVERY anchor. Timeframe = input resolution only (finer anchor → finer TF); NOT a layer.

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

**15 — Volume profile per leg (`experiments/layer2/leg_profiles.py`).** Hung a volume
profile off each zigzag leg, graded by value-area concentration (`va_frac` = fraction of
the leg's rows holding 70% of its volume). **Confirmed:** hanging the profile off a LEG
(not the session) is the right anchor, and the profiles visibly show fat POCs on sideways
stretches vs spread on fast moves. **But** a single binary RANGE-vs-impulse label is too
crude — the strongest-bull's main up-leg got labeled "RANGE va 46%" because a *slow grind*
builds acceptance even while trending.
→ **The real lesson: concentration and direction are two DIFFERENT axes.** Cross them:

|                | low acceptance (spread) | high acceptance (fat POC) |
|----------------|-------------------------|---------------------------|
| **net progress**   | clean **impulse**        | **grind / accumulation** (slow trend) |
| **no progress**    | fast **whipsaw chop**    | **consolidation** (the real range)    |

A 4-state regime map that reuses Layer 1's `net %` (progress) + the per-leg profile
concentration (acceptance). Neither axis alone works; together they do. This is likely
the core of the whole thing. Next: label each leg by both axes into one of the 4 states.

**16 — 2-axis regime map (`experiments/layer2/leg_states.py`).** Rolling per-bar classifier:
PROGRESS (efficiency = net ÷ travel) × ACCEPTANCE (1 − va_frac) → IMPULSE / GRIND /
CONSOLIDATION / WHIPSAW (progress states tinted up/down). **Chop #2 came out beautiful** —
clean IMPULSE UP (open rip) → chop → IMPULSE DN (drop) → consolidation. Jake (discretionary
trader): *"beautiful up and down impulses… correct versions of what i constitute as an
impulse."* Strong bull = mostly WHIPSAW/weak grind → Jake: *"the strongest bull is in fact
a weaker climb."* Insight: **Layer 1 net% = magnitude ("ended way up"); Layer 2 2-axis =
quality ("got there weakly")** — complementary, not contradictory. GRIND barely appears
because a slow trend is choppy at a fine window — trend is a LARGER-scale pattern (fractal
again). Volume profile IS used here, but only as one hidden number (`va_frac`), not drawn.

**17 — "Make sense of the layers" (the coherence audit).** Jake: *"i cant make sense of
these layers easily… we started at layer 1, talked about repeating in layer 2, same
premise… we need new anchors if we scale (what do we define those anchors as)… found
inconsistency with volume range profile… leg states captures something beautiful, regimes
well detected, as a discretionary trader i agree… but the 5min doesnt have this regime
detection, does it need it? can we get this same regime design on the 5min or is that just
the 1min overlaid?… once impulse is detected, that becomes the core high/low for the volume
profile to see smaller consolidations within the 5min base… session anatomy has all these
numbers i love but i dont see this data captured for leg states… wheres the drift, do we
want a drift, does there have to be one?… is volume profile even used in leg states?… do we
want it mapped like leg profiles (POC/VAH/VAL)?… this isnt weakness, im gathering it all."*
→ Response = **the two-things model** (see top): everything is an **ANCHOR** (a high/low
container) + a **GRADE** (fixed metric set on it). Layers = same grade on smaller anchors;
the loop grades an anchor, its impulses become new anchors, recurse. Layer 1 anchor =
clock-given (session); deeper anchors = structure-detected (impulses) — Jake's "impulse
becomes the core high/low for the profile" IS the recursion. **Drift is bad** — fractal
forbids it; our drift is accidental (separate scripts, different subsets). Answers: volume
profile IS in leg_states but hidden as `va_frac` (leg_profiles draws it — want both
everywhere); 5m doesn't lack regime detection, the engine is timeframe-blind (5m = coarse,
1m = fine, they nest); leg_states missing the anatomy numbers = the drift, unify to fix.
Next: write the canonical `grade(anchor) → {metrics + profile}` + anchor-recursion spec as
a design doc before any more views.

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
