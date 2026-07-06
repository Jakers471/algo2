"""lean/vabreakout/main.py — VA-breakout on QuantConnect LEAN (NQ E-mini).

The SAME strategy as src/strategy, ported to LEAN: L1 = 5m session bias (grade().strength),
L2 = a 1m CONSOLIDATION; enter on the break of its value area in the session's direction,
stop = opposite edge, target 2R. Entries decided on 5m; exits checked on 1m (intrabar).

Data: continuous NQ future (minute base, 5m via consolidator). Timezone set to Chicago so
the session windows match algo_config.yaml. All math is in grade_lib.py (a self-contained
copy of the project's brain).

STATUS: v1, written from the LEAN Python examples but NOT run locally here (no Docker/QC auth
in this environment). Run `lean backtest vabreakout` and we iterate on any API mismatch.
"""
from AlgorithmImports import *
import numpy as np

from grade_lib import (grade, read_consolidation, decide,
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
        self.set_start_date(2024, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100_000)
        self.set_time_zone(TimeZones.CHICAGO)                 # session windows are Chicago-local

        self._future = self.add_future(
            Futures.Indices.NASDAQ_100_E_MINI, resolution=Resolution.MINUTE,
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
            data_mapping_mode=DataMappingMode.LAST_TRADING_DAY, contract_depth_offset=0)
        self._future.set_filter(0, 182)
        self._sym = self._future.symbol                       # continuous symbol (data arrives here)

        cons = TradeBarConsolidator(timedelta(minutes=5))     # 1m -> 5m
        cons.data_consolidated += self._on_5m
        self.subscription_manager.add_consolidator(self._sym, cons)

        self._b1 = []            # recent 1m bars [o,h,l,c,v]  (for the L2 consolidation)
        self._b5 = []            # this session's 5m bars       (for the L1 bias)
        self._session = None
        self._traded = set()     # (entry,stop) fingerprints taken this session (one/base)
        self._pos = None         # open position dict {dir,entry,stop,target}

        self.set_warm_up(timedelta(days=3))                   # fill buffers before trading

    # ---- 1m stream: buffer + intrabar exit management ----
    def on_data(self, slice):
        bar = slice.bars.get(self._sym)
        if bar is None:
            return
        self._b1.append([bar.open, bar.high, bar.low, bar.close, bar.volume])
        if len(self._b1) > 400:
            self._b1 = self._b1[-400:]
        if self._pos is not None:                             # manage on the 1m bar (intrabar)
            self._check_exit(bar)

    def _check_exit(self, bar):
        p = self._pos
        long = p["direction"] == "long"
        hit_stop = bar.low <= p["stop"] if long else bar.high >= p["stop"]
        hit_tgt = bar.high >= p["target"] if long else bar.low <= p["target"]
        if hit_stop or hit_tgt:                               # stop checked first (conservative)
            self.liquidate(self._future.mapped)
            self._pos = None

    # ---- 5m stream: session bias + decide + entry ----
    def _on_5m(self, sender, bar):
        sess = _session_of(bar.end_time)
        if sess != self._session:                            # session boundary (intraday reset)
            if self._pos is not None:
                self.liquidate(self._future.mapped)          # flat at session close
                self._pos = None
            self._session, self._b5, self._traded = sess, [], set()
        if sess is None:
            return
        self._b5.append([bar.open, bar.high, bar.low, bar.close, bar.volume])

        if self.is_warming_up or self._pos is not None:
            return
        if len(self._b5) < MIN_BARS or len(self._b1) < STATE_WINDOW + MIN_LEN:
            return

        s5 = np.array(self._b5, float)
        strength = grade(s5[:, 0], s5[:, 1], s5[:, 2], s5[:, 3], s5[:, 4]).strength   # L1 bias
        b1 = np.array(self._b1, float)
        cons = read_consolidation(b1[:, 0], b1[:, 1], b1[:, 2], b1[:, 3], b1[:, 4])   # L2 base
        intent = decide(strength, cons, bar.close)
        if intent is None:
            return
        sig = (round(intent["entry"], 1), round(intent["stop"], 1))
        if sig in self._traded:                              # already took this base's break
            return
        self._traded.add(sig)
        self._enter(intent)

    def _enter(self, intent):
        qty = 1 if intent["direction"] == "long" else -1
        self.market_order(self._future.mapped, qty)
        self._pos = dict(intent)
        self.log(f"{self.time} ENTER {intent['direction']} @{intent['entry']:.1f} "
                 f"stop {intent['stop']:.1f} tgt {intent['target']:.1f}")

    def on_order_event(self, order_event):
        if order_event.status == OrderStatus.FILLED:
            self.debug(f"{self.time} fill {order_event.symbol} {order_event.fill_quantity} "
                       f"@ {order_event.fill_price}")
