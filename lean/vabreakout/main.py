"""lean/vabreakout/main.py — VA-breakout on QuantConnect LEAN (NQ E-mini).

The SAME strategy as src/strategy, ported to LEAN: L1 = 5m session bias (grade().strength),
L2 = a 1m CONSOLIDATION; enter on the break of its value area in the session's direction,
stop = opposite edge, target 2R. Entries decided on 5m; exits checked on 1m (intrabar).

Data: continuous NQ future (minute base, 5m via consolidator). Sessions use the ALGORITHM
clock (set to Chicago) so they match algo_config.yaml. Math is in grade_lib.py.

v2: session timing off the algo clock (not the bar's tz), flatten on contract rollover,
robust bar access, and diagnostic logging. Short debug range — expand once it looks right.
"""
from AlgorithmImports import *
import numpy as np

from grade_lib import (grade, state_of, find_consolidation, decide,
                       MIN_BARS, STATE_WINDOW, MIN_LEN)

CHI_WINDOWS = [("Asia", 18 * 60, 3 * 60), ("London", 3 * 60, 8 * 60), ("NY", 8 * 60, 17 * 60)]


def _session_of(dt):
    """Chicago-local datetime -> 'Asia'|'London'|'NY'|None (matches algo_config sessions)."""
    m = dt.hour * 60 + dt.minute
    for name, s, e in CHI_WINDOWS:
        if (s <= e and s <= m < e) or (s > e and (m >= s or m < e)):   # Asia wraps midnight
            return name
    return None


class VaBreakout(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2022, 1, 1)           # 3-year validation sample (~8 min on cloud)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100_000)
        self.set_time_zone(TimeZones.CHICAGO)     # so self.time matches the session windows

        self._future = self.add_future(
            Futures.Indices.NASDAQ_100_E_MINI, resolution=Resolution.MINUTE,
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
            data_mapping_mode=DataMappingMode.LAST_TRADING_DAY, contract_depth_offset=0)
        self._future.set_filter(0, 182)
        self._sym = self._future.symbol

        cons = TradeBarConsolidator(timedelta(minutes=5))
        cons.data_consolidated += self._on_5m
        self.subscription_manager.add_consolidator(self._sym, cons)

        self._b1, self._st1, self._b5 = [], [], []   # 1m bars, 1m states (aligned), 5m session bars
        self._session = None
        self._traded = set()
        self._pos = None
        self._diag = {"got_bar": False, "trades": 0}     # one-time diagnostics

        self.set_warm_up(timedelta(days=3))

    # ---- 1m stream: buffer + intrabar exit ----
    def on_data(self, slice):
        for _ in slice.symbol_changed_events.values():        # contract rollover -> go flat
            if self._pos is not None:
                self.liquidate(); self._pos = None
                self.log(f"{self.time} ROLLOVER flat")

        bar = slice.bars.get(self._sym) or slice.bars.get(self._future.mapped)
        if bar is None:
            return
        if not self._diag["got_bar"]:
            self._diag["got_bar"] = True
            self.log(f"{self.time} data flowing on {bar.symbol}")
        self._b1.append([bar.open, bar.high, bar.low, bar.close, bar.volume])
        # compute THIS bar's state once (grade of the trailing window) and keep it —
        # so find_consolidation never re-grades the whole window (the perf fix).
        if len(self._b1) >= STATE_WINDOW + 1:     # rolling_states grades bars[i-25:i+1] = 26 bars
            w = np.array(self._b1[-(STATE_WINDOW + 1):], float)
            self._st1.append(state_of(w[:, 0], w[:, 1], w[:, 2], w[:, 3], w[:, 4]))
        else:
            self._st1.append(None)
        if len(self._b1) > 400:
            self._b1 = self._b1[-400:]; self._st1 = self._st1[-400:]
        if self._pos is not None:
            self._check_exit(bar)

    def _check_exit(self, bar):
        p = self._pos
        long = p["direction"] == "long"
        hit_stop = bar.low <= p["stop"] if long else bar.high >= p["stop"]
        hit_tgt = bar.high >= p["target"] if long else bar.low <= p["target"]
        if hit_stop or hit_tgt:
            self.liquidate(self._future.mapped)
            self.log(f"{self.time} EXIT {'stop' if hit_stop else 'target'} {p['direction']}")
            self._pos = None

    # ---- 5m stream: session bias + decide + entry ----
    def _on_5m(self, sender, bar):
        sess = _session_of(self.time)                         # algo clock (Chicago)
        if sess != self._session:
            if self._pos is not None:
                self.liquidate(self._future.mapped)           # flat at session close (intraday)
                self.log(f"{self.time} SESSION-FLAT {self._pos['direction']}")
                self._pos = None
            self.log(f"{self.time} -> session {sess}  (5m={len(self._b5)} 1m={len(self._b1)})")
            self._session, self._b5, self._traded = sess, [], set()
        if sess is None:
            return
        self._b5.append([bar.open, bar.high, bar.low, bar.close, bar.volume])

        if self.is_warming_up or self._pos is not None:
            return
        if len(self._b5) < MIN_BARS or len(self._b1) < STATE_WINDOW + MIN_LEN:
            return

        s5 = np.array(self._b5, float)
        strength = grade(s5[:, 0], s5[:, 1], s5[:, 2], s5[:, 3], s5[:, 4]).strength
        b1 = np.array(self._b1, float)
        cons = find_consolidation(self._st1, b1[:, 0], b1[:, 1], b1[:, 2], b1[:, 3], b1[:, 4])
        intent = decide(strength, cons, bar.close)
        if intent is None:
            return
        sig = (round(intent["entry"], 1), round(intent["stop"], 1))
        if sig in self._traded:
            return
        self._traded.add(sig)
        self._enter(intent)

    def _enter(self, intent):
        qty = 1 if intent["direction"] == "long" else -1
        self.market_order(self._future.mapped, qty)
        self._pos = dict(intent)
        self._diag["trades"] += 1
        self.log(f"{self.time} ENTER {intent['direction']} @{intent['entry']:.1f} "
                 f"stop {intent['stop']:.1f} tgt {intent['target']:.1f}")

    def on_end_of_algorithm(self):
        self.log(f"DONE — entries fired: {self._diag['trades']}, ever got a bar: {self._diag['got_bar']}")
