#!/usr/bin/env python3
"""experiments/har_vol/plot_demo.py — render the HAR walk-forward as SVG charts,
using ONLY the standard library (no numpy/pandas/matplotlib).

Purpose: preview what har_rv.py's output looks like in an environment that can't
install the scientific stack or hold the (gitignored) NQ parquets. It drives the
SAME verified walk-forward logic from verify_logic.py, but on SYNTHETIC
clustered-volatility data, and draws:

  Panel 1  actual vs HAR-predicted realized vol over the out-of-sample window
  Panel 2  predicted-vs-actual scatter with a y=x reference + OOS R² vs RW

The shapes are exactly what har_rv.py --plot produces on real NQ; only the input
series differs (synthetic here, NQ parquets there). Clearly labelled as such.

Run:  python experiments/har_vol/plot_demo.py   ->   out/demo_har_synthetic.svg
"""
import math
import os

from verify_logic import LCG, persistent_vol, har_matrix, walk_forward, ols, sse

HERE = os.path.dirname(os.path.abspath(__file__))


# ---- minimal SVG helpers -------------------------------------------------
def _sx(v, lo, hi, x0, w):
    return x0 + (v - lo) / (hi - lo) * w if hi > lo else x0


def _sy(v, lo, hi, y0, h):
    return y0 + h - (v - lo) / (hi - lo) * h if hi > lo else y0 + h


def _poly(pts, color, wid, opacity=1.0):
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="{wid}" opacity="{opacity}"/>'


def _txt(x, y, s, size=13, color="#333", anchor="start", weight="normal"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="ui-sans-serif,Arial" '
            f'font-size="{size}" fill="{color}" text-anchor="{anchor}" '
            f'font-weight="{weight}">{s}</text>')


def _axes(x0, y0, w, h):
    return (f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="#fafafa" stroke="#ccc"/>')


# ---- build the run -------------------------------------------------------
def run():
    rng = LCG(1)
    v = persistent_vol(2600, rng)          # clustered vol, like NQ realized vol
    y, X, _ = har_matrix(v)
    min_train = 500
    pred, act = walk_forward(y, X, min_train)
    rw = [X[min_train + i][1] for i in range(len(act))]   # random-walk baseline
    r2 = 1.0 - sse(act, pred) / sse(act, rw)
    mp = sum(pred) / len(pred)
    ma = sum(act) / len(act)
    cov = sum((p - mp) * (a - ma) for p, a in zip(pred, act))
    sp = math.sqrt(sum((p - mp) ** 2 for p in pred))
    sa = math.sqrt(sum((a - ma) ** 2 for a in act))
    corr = cov / (sp * sa) if sp > 0 and sa > 0 else float("nan")
    return act, pred, r2, corr


# ---- draw ----------------------------------------------------------------
def svg(act, pred, r2, corr):
    W, H = 1040, 780
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}">',
           f'<rect width="{W}" height="{H}" fill="#ffffff"/>']
    out.append(_txt(28, 34, "HAR-RV walk-forward — predicted vs actual volatility",
                    size=20, weight="bold"))
    out.append(_txt(28, 56,
                    "SYNTHETIC clustered-vol demo (real NQ needs data/NQ/*.parquet + pandas locally). "
                    "Same verified walk-forward as har_rv.py.", size=13, color="#777"))

    # ---- Panel 1: time series ----
    x0, y0, w, h = 60, 90, W - 100, 300
    out.append(_axes(x0, y0, w, h))
    out.append(_txt(x0, y0 - 8, "Panel 1  realized volatility over the out-of-sample window",
                    size=14, weight="bold"))
    n = len(act)
    lo = min(min(act), min(pred))
    hi = max(max(act), max(pred))
    xs = lambda i: _sx(i, 0, n - 1, x0, w)
    ys = lambda val: _sy(val, lo, hi, y0, h)
    out.append(_poly([(xs(i), ys(act[i])) for i in range(n)], "#555555", 0.7, 0.9))
    out.append(_poly([(xs(i), ys(pred[i])) for i in range(n)], "#e8823a", 0.7, 0.9))
    # legend
    out.append(f'<line x1="{x0+w-190}" y1="{y0+16}" x2="{x0+w-160}" y2="{y0+16}" stroke="#555555" stroke-width="2"/>')
    out.append(_txt(x0 + w - 154, y0 + 20, "actual", size=12, color="#555"))
    out.append(f'<line x1="{x0+w-190}" y1="{y0+34}" x2="{x0+w-160}" y2="{y0+34}" stroke="#e8823a" stroke-width="2"/>')
    out.append(_txt(x0 + w - 154, y0 + 38, "HAR predicted", size=12, color="#e8823a"))
    out.append(_txt(x0, y0 + h + 18, f"OOS day 0", size=11, color="#999"))
    out.append(_txt(x0 + w, y0 + h + 18, f"{n}", size=11, color="#999", anchor="end"))

    # ---- Panel 2: scatter pred vs actual ----
    px0, py0, pw, ph = 60, 460, 300, 280
    out.append(_axes(px0, py0, pw, ph))
    out.append(_txt(px0, py0 - 8, "Panel 2  predicted vs actual (y=x is perfect)",
                    size=14, weight="bold"))
    slo, shi = lo, hi
    sxf = lambda val: _sx(val, slo, shi, px0, pw)
    syf = lambda val: _sy(val, slo, shi, py0, ph)
    out.append(f'<line x1="{sxf(slo):.1f}" y1="{syf(slo):.1f}" x2="{sxf(shi):.1f}" y2="{syf(shi):.1f}" '
               f'stroke="#3a7de8" stroke-width="1" stroke-dasharray="4 3"/>')
    step = max(1, n // 1200)                # thin the cloud for file size
    dots = "".join(f'<circle cx="{sxf(act[i]):.1f}" cy="{syf(pred[i]):.1f}" r="1.4" '
                   f'fill="#e8823a" opacity="0.4"/>' for i in range(0, n, step))
    out.append(dots)
    out.append(_txt(px0 + pw / 2, py0 + ph + 20, "actual", size=12, anchor="middle", color="#666"))
    out.append(_txt(px0 - 40, py0 + ph / 2, "pred", size=12, anchor="middle", color="#666"))

    # ---- metrics card ----
    mx, my = 420, 470
    out.append(f'<rect x="{mx}" y="{my}" width="560" height="260" rx="8" fill="#f5f7fa" stroke="#dde3ea"/>')
    out.append(_txt(mx + 22, my + 34, "Out-of-sample result", size=16, weight="bold"))
    lines = [
        (f"OOS R² vs random-walk", f"{r2:+.3f}", "#1a7f3c" if r2 > 0 else "#b23"),
        (f"correlation(pred, actual)", f"{corr:.3f}", "#333"),
        (f"walk-forward test days", f"{len(act):,}", "#333"),
    ]
    yy = my + 74
    for label, val, col in lines:
        out.append(_txt(mx + 22, yy, label, size=14, color="#555"))
        out.append(_txt(mx + 538, yy, val, size=15, color=col, anchor="end", weight="bold"))
        yy += 34
    out.append(_txt(mx + 22, yy + 6,
                    "R² > 0  =>  HAR beats \"tomorrow ≈ today\".", size=13, color="#777"))
    out.append(_txt(mx + 22, yy + 28,
                    "On real NQ this is typically larger (vol is more", size=13, color="#777"))
    out.append(_txt(mx + 22, yy + 48,
                    "persistent than this toy series).", size=13, color="#777"))
    out.append("</svg>")
    return "\n".join(out)


def main():
    act, pred, r2, corr = run()
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    path = os.path.join(HERE, "out", "demo_har_synthetic.svg")
    with open(path, "w") as f:
        f.write(svg(act, pred, r2, corr))
    print(f"OOS R² vs RW = {r2:+.3f}  corr = {corr:.3f}  days = {len(act):,}")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
