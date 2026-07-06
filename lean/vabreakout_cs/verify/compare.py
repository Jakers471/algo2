"""Diff C# output.json against the Python-source expected in input.json."""
import json, os
d = os.path.dirname(os.path.abspath(__file__))
inp = json.load(open(os.path.join(d, "input.json")))
out = json.load(open(os.path.join(d, "output.json")))
assert len(inp) == len(out), (len(inp), len(out))

def close(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) <= tol

cons_ok = cons_bad = g_ok = g_bad = 0
for i, (pi, co) in enumerate(zip(inp, out)):
    # --- consolidation ---
    pc, cc = pi["py_cons"], co["cons"]
    if pc is None and cc is None:
        cons_ok += 1
    elif pc is None or cc is None:
        cons_bad += 1; print(f"[{i}] CONS presence mismatch: py={pc} cs={cc}")
    else:
        if (close(pc["vah"], cc["vah"]) and close(pc["val"], cc["val"]) and close(pc["poc"], cc["poc"])
                and pc["len"] == cc["len"] and pc["ended_ago"] == cc["ago"]):
            cons_ok += 1
        else:
            cons_bad += 1; print(f"[{i}] CONS mismatch:\n   py={pc}\n   cs={cc}")
    # --- grade on last 60 ---
    pg, cg = pi["py_g60"], co["g60"]
    if (pg["state"] == cg["state"] and close(pg["strength"], cg["strength"])
            and close(pg["vah"], cg["vah"]) and close(pg["val"], cg["val"])):
        g_ok += 1
    else:
        g_bad += 1; print(f"[{i}] GRADE mismatch:\n   py={pg}\n   cs={cg}")

print(f"\nconsolidation: {cons_ok}/{cons_ok+cons_bad} match")
print(f"grade(60):     {g_ok}/{g_ok+g_bad} match")
print("ALL MATCH" if cons_bad == 0 and g_bad == 0 else "MISMATCHES FOUND")
