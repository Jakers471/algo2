# verify — C# ↔ Python equivalence check for the C# port

Proves `lean/vabreakout_cs/Main.cs`'s math (`Vab.Grade`, `Vab.FindConsolidation`) is byte-identical
to the frozen Python **source of truth** (`experiments/engine/grade.py`, `src/strategy/readings/consolidation.py`).
Needs `dotnet` (any recent SDK) + the project's Python env.

**Rule (do this before shipping any change to the C# math):** run all three steps and confirm `ALL MATCH`.
Don't optimize or edit `Vab` without re-passing this.

```bash
python lean/vabreakout_cs/verify/export.py        # 1. dump 52 windows + Python-source expected -> input.json
cd lean/vabreakout_cs/verify && dotnet run -c Release   # 2. compile Vab + run it -> output.json  (also = the compile check)
python lean/vabreakout_cs/verify/compare.py       # 3. diff -> "consolidation 52/52 · grade 52/52 · ALL MATCH"
```

## What it does
- `export.py` — 52 NQ 1m windows across 2024; for each, the Python source's `read_consolidation` +
  `grade(last 60)` as the expected answer.
- `Program.cs` — the `Vab` class **copied verbatim** from `Main.cs`, plus a harness that rebuilds the
  per-bar states exactly like `main.py` and calls `FindConsolidation`/`Grade`. `dotnet run` compiles it
  (so this doubles as the local compile check for the math) and writes `output.json`.
- `compare.py` — diffs C# vs Python (state exact; prices/strength within 1e-6; len/ago exact).

## Scope
This verifies the **math** (the risky part of the port). The LEAN wiring in `Main.cs` (OnData,
consolidators, orders) can't be compiled without LEAN's assemblies — QC's cloud compiler is that check.

`input.json` / `output.json` / `bin/` / `obj/` are generated — gitignored.
