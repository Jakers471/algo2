# NOTES

Running log of vision, decisions, and what we learned. Newest first. Entries are
dated + timed and terse (≤50 lines). Split into `notes/` when this gets large.

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
