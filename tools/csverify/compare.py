"""Diff C# output.json against the Python-source expected in input.json.

Now verifies TWO C# targets against the one Python source of truth:
  - LEAN  (lean/vabreakout_cs/Main.cs)      -> keys "cons" / "g60"
  - NinjaTrader (ninjatrader/VABreakout.cs) -> keys "cons_nt" / "g60_nt"
Python == LEAN == NT means all three implementations compute identical signals.
"""
import json, os
d = os.path.dirname(os.path.abspath(__file__))
inp = json.load(open(os.path.join(d, "input.json")))
out = json.load(open(os.path.join(d, "output.json")))
assert len(inp) == len(out), (len(inp), len(out))


def close(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) <= tol


def cons_match(pc, cc):
    if pc is None and cc is None:
        return True
    if pc is None or cc is None:
        return False
    return (close(pc["vah"], cc["vah"]) and close(pc["val"], cc["val"]) and close(pc["poc"], cc["poc"])
            and pc["len"] == cc["len"] and pc["ended_ago"] == cc["ago"])


def grade_match(pg, cg):
    return (pg["state"] == cg["state"] and close(pg["strength"], cg["strength"])
            and close(pg["vah"], cg["vah"]) and close(pg["val"], cg["val"]))


def run(label, cons_key, g_key):
    cons_ok = cons_bad = g_ok = g_bad = 0
    for i, (pi, co) in enumerate(zip(inp, out)):
        if cons_match(pi["py_cons"], co[cons_key]):
            cons_ok += 1
        else:
            cons_bad += 1; print(f"[{label} {i}] CONS mismatch:\n   py={pi['py_cons']}\n   cs={co[cons_key]}")
        if grade_match(pi["py_g60"], co[g_key]):
            g_ok += 1
        else:
            g_bad += 1; print(f"[{label} {i}] GRADE mismatch:\n   py={pi['py_g60']}\n   cs={co[g_key]}")
    n = len(inp)
    print(f"{label:<5} consolidation {cons_ok}/{n} | grade {g_ok}/{n}")
    return cons_bad == 0 and g_bad == 0


ok_lean = run("LEAN", "cons", "g60")
ok_nt = run("NT", "cons_nt", "g60_nt") if "cons_nt" in out[0] else True
print("\nALL MATCH" if ok_lean and ok_nt else "MISMATCHES FOUND")
