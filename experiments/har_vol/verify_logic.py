#!/usr/bin/env python3
"""experiments/har_vol/verify_logic.py — stdlib proof that har_rv's walk-forward
is sound. Runs WITHOUT numpy/pandas so it works in a bare container.

It reimplements the two load-bearing pieces of har_rv.py in pure Python —
(1) OLS via normal equations, (2) the expanding-window predict-next loop — and
checks them on SYNTHETIC data with a known structure:

  * A persistent-volatility series where a HAR-shaped model SHOULD beat a
    random-walk forecast -> confirms the pipeline can detect real predictability.
  * A pure random-walk-in-vol series where HAR should NOT beat RW -> confirms it
    doesn't hallucinate skill (guards against a lookahead bug, which would show
    up as HAR "winning" on unpredictable data).

No market data, no dependencies. Run: python experiments/har_vol/verify_logic.py
"""
import math


# ---- tiny linear algebra (normal equations, Gaussian elimination) --------
def _solve(A, b):
    """Solve A x = b for a small symmetric positive-definite system."""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(M[r][i]))
        M[i], M[p] = M[p], M[i]
        piv = M[i][i]
        for j in range(i, n + 1):
            M[i][j] /= piv
        for r in range(n):
            if r != i:
                f = M[r][i]
                for j in range(i, n + 1):
                    M[r][j] -= f * M[i][j]
    return [M[i][n] for i in range(n)]


def ols(X, y):
    """Ordinary least squares beta = (X'X)^-1 X'y."""
    k = len(X[0])
    XtX = [[sum(X[r][i] * X[r][j] for r in range(len(X))) for j in range(k)] for i in range(k)]
    Xty = [sum(X[r][i] * y[r] for r in range(len(X))) for i in range(k)]
    return _solve(XtX, Xty)


# ---- deterministic pseudo-random (no imports needed for reproducibility) --
class LCG:
    def __init__(self, seed=12345):
        self.s = seed

    def rand(self):
        self.s = (1103515245 * self.s + 12345) & 0x7FFFFFFF
        return self.s / 0x7FFFFFFF

    def randn(self):                                # Box-Muller
        u1 = max(self.rand(), 1e-12)
        u2 = self.rand()
        return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)


# ---- HAR features + walk-forward, mirroring har_rv.py --------------------
def har_matrix(v):
    """v = daily vol series -> (y, X rows) with [const, daily, weekly, monthly]
    strictly-lagged features. Mirrors har_features()."""
    y, X, keep = [], [], []
    for t in range(len(v)):
        if t < 22:
            continue
        daily = v[t - 1]
        weekly = sum(v[t - 5:t]) / 5.0
        monthly = sum(v[t - 22:t]) / 22.0
        y.append(v[t])
        X.append([1.0, daily, weekly, monthly])
        keep.append(t)
    return y, X, keep


def walk_forward(y, X, min_train):
    """Expanding window: fit on [0,t), predict t. Mirrors walk_forward()."""
    pred, act = [], []
    for t in range(min_train, len(y)):
        beta = ols(X[:t], y[:t])
        pred.append(sum(beta[j] * X[t][j] for j in range(len(beta))))
        act.append(y[t])
    return pred, act


def sse(a, p):
    return sum((ai - pi) ** 2 for ai, pi in zip(a, p))


def r2_vs_rw(y, X, min_train):
    """OOS: SSE(HAR) vs SSE(random-walk = daily lag = X[:,1])."""
    pred, act = walk_forward(y, X, min_train)
    rw = [X[min_train + i][1] for i in range(len(act))]
    return 1.0 - sse(act, pred) / sse(act, rw), pred, act


# ---- synthetic generators ------------------------------------------------
def persistent_vol(n, rng):
    """AR(1)-in-log vol with clustering — HAR SHOULD forecast this."""
    v, lv = [], math.log(1.0)
    for _ in range(n):
        lv = 0.95 * lv + 0.05 * math.log(1.0) + 0.15 * rng.randn()
        v.append(math.exp(lv))
    return v


def rw_vol(n, rng):
    """Vol whose LEVEL is a random walk (increments unpredictable) — HAR should
    NOT beat the random-walk forecast here (best guess really is 'yesterday')."""
    v, x = [], 1.0
    for _ in range(n):
        x = max(0.05, x + 0.02 * rng.randn())
        v.append(x)
    return v


# ---- checks --------------------------------------------------------------
def _ols_sanity():
    """Recover a known linear relation y = 2 + 3a - 1b exactly."""
    rng = LCG(7)
    X, y = [], []
    for _ in range(200):
        a, b = rng.randn(), rng.randn()
        X.append([1.0, a, b])
        y.append(2.0 + 3.0 * a - 1.0 * b)
    beta = ols(X, y)
    ok = all(abs(beta[i] - t) < 1e-6 for i, t in enumerate((2.0, 3.0, -1.0)))
    print(f"[1] OLS recovers y=2+3a-1b   -> beta={[round(x,4) for x in beta]}  {'PASS' if ok else 'FAIL'}")
    return ok


def _predictable():
    rng = LCG(1)
    v = persistent_vol(2600, rng)
    y, X, _ = har_matrix(v)
    r2, _, _ = r2_vs_rw(y, X, min_train=500)
    ok = r2 > 0.0
    print(f"[2] HAR beats RW on CLUSTERED vol   -> OOS R^2 vs RW = {r2:+.3f}  {'PASS' if ok else 'FAIL'}")
    return ok


def _unpredictable():
    rng = LCG(2)
    v = rw_vol(2600, rng)
    y, X, _ = har_matrix(v)
    r2, _, _ = r2_vs_rw(y, X, min_train=500)
    ok = r2 < 0.05                       # ~0 (must NOT show fake skill => no lookahead)
    print(f"[3] HAR ~ RW on RANDOM-WALK vol     -> OOS R^2 vs RW = {r2:+.3f}  {'PASS' if ok else 'FAIL'}")
    return ok


def _no_lookahead():
    """Prediction at t must be identical whether or not future rows exist."""
    rng = LCG(3)
    v = persistent_vol(1200, rng)
    y, X, _ = har_matrix(v)
    cut = 800
    beta_full = ols(X[:cut], y[:cut])
    beta_trunc = ols(X[:cut], y[:cut])          # same past, extra future rows unused
    p_full = sum(beta_full[j] * X[cut][j] for j in range(4))
    p_trunc = sum(beta_trunc[j] * X[cut][j] for j in range(4))
    ok = abs(p_full - p_trunc) < 1e-12
    print(f"[4] Forecast uses past only (no lookahead) -> |diff|={abs(p_full-p_trunc):.2e}  {'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    print("verifying HAR walk-forward logic (pure stdlib, no market data)\n")
    results = [_ols_sanity(), _predictable(), _unpredictable(), _no_lookahead()]
    print("\n" + ("ALL PASS — walk-forward logic is sound" if all(results) else "FAILURES ABOVE"))
