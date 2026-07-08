/*
 * lean/vabreakout_cs/Main.cs — VA-breakout on QuantConnect LEAN (NQ E-mini), in C#.
 *
 * Byte-for-byte port of lean/vabreakout (Python) / src/strategy: L1 = 5m session bias
 * (Grade().Strength), L2 = a 1m CONSOLIDATION; enter on the break of its value area in the
 * session's direction, stop = opposite edge, target 2R. Entries decided on 5m; exits are REAL
 * stop/limit bracket orders (placed once the entry fills) so the entry's own bar can't stop us out.
 *
 * PERFORMANCE: the per-bar hot path (Grade) is written TIGHT — no LINQ, no per-bar allocations.
 * It slices the buffers with zero-copy Span<double> (CollectionsMarshal.AsSpan) and uses a
 * stackalloc for the profile bins. Manual min/max/sum loops. This is what makes C# actually fast;
 * naive LINQ/GetRange().ToArray() in a million-call loop is slower than optimized Python.
 *
 * Written from the LEAN C# API but not compiled in this env — first cloud run may surface C#
 * errors to iterate on.
 */
using System;
using System.Collections.Generic;
using Newtonsoft.Json;
using QuantConnect;
using QuantConnect.Data;
using QuantConnect.Data.Consolidators;
using QuantConnect.Data.Market;
using QuantConnect.Orders;             // OrderTicket / OrderEvent / StopMarketOrder
using QuantConnect.Securities;         // Futures.Indices.NASDAQ100EMini lives here
using QuantConnect.Securities.Future;  // the Future type

namespace QuantConnect.Algorithm.CSharp
{
    public class VaBreakout : QCAlgorithm
    {
        private Future _future;
        private Symbol _sym;
        private readonly List<double> _o1 = new(), _h1 = new(), _l1 = new(), _c1 = new(), _v1 = new();
        private readonly List<string> _st1 = new();
        private readonly List<double> _o5 = new(), _h5 = new(), _l5 = new(), _c5 = new(), _v5 = new();
        // reusable scratch arrays: copy a window in, pass a SAFE array-span to Vab (no CollectionsMarshal,
        // no per-bar allocation). Sized past the max window (detection 120, session <=110).
        private readonly double[] _so = new double[512], _sh = new double[512], _sl = new double[512],
                                  _sc = new double[512], _sv = new double[512];
        private string _session = null;
        private bool _rolled = false;   // set on a contract roll (Raw data jumps) -> reset the session
        private DateTime _lastBar = DateTime.MinValue;   // to detect data gaps that break a session
        private HashSet<(double, double)> _traded = new();
        private Vab.Intent _pos;
        private bool _inPos = false;
        private OrderTicket _entryTicket;   // resting stop-order for the pending entry (fill AT the level)
        private OrderTicket _stopTicket, _tgtTicket;   // REAL bracket exit legs (manual OCO), placed once entry fills
        private Vab.Intent _arm;            // the setup behind the resting order
        private readonly List<Vab.TradeRec> _trades = new();
        private bool _gotBar = false;
        private int _entries = 0;
        // DIAGNOSTIC (direction bug): where do longs vanish? Count the session-bias sign at every
        // decision bar, the stop-orders actually placed, and the fills — each split long/short.
        private int _biasBull = 0, _biasBear = 0, _biasFlat = 0;
        private int _placeLong = 0, _placeShort = 0, _fillLong = 0, _fillShort = 0;

        public override void Initialize()
        {
            // Honest 11yr baseline: Second-resolution fills, 2015-2026 (2R target, no BE — best config).
            SetStartDate(2015, 1, 1);
            SetEndDate(2026, 7, 1);
            SetCash(100000);
            SetTimeZone(TimeZones.Chicago);

            // RAW (not BackwardsRatio): the strategy computes order prices (Vah/Val) from this data and
            // submits them on _future.Mapped (the raw contract). BackwardsRatio-adjusted prices are on a
            // DIFFERENT scale than the raw contract (the adjustment grows back in time), so buy-stops
            // landed far above the raw market (never filled) and sell-stops triggered instantly at garbage
            // -> 4/1041 long fills, ~0% win, and R(adjusted) disagreeing with P&L(raw). Raw aligns the two.
            // Within a session (no roll) Raw and BackwardsRatio have identical shape, so signals are
            // unchanged; rolls are handled by breaking the session on SymbolChanged (see OnData).
            // SECOND resolution: the resting entry + bracket orders fill on 1-second bars (honest intrabar
            // sequencing), removing the 1-minute over-stopping that made minute fills pessimistic. The
            // strategy's 1m/5m buffers are rebuilt by consolidators below — OnData no longer builds them.
            _future = AddFuture(Futures.Indices.NASDAQ100EMini, Resolution.Second,
                dataNormalizationMode: DataNormalizationMode.Raw,
                dataMappingMode: DataMappingMode.LastTradingDay, contractDepthOffset: 0);
            _future.SetFilter(0, 182);
            _sym = _future.Symbol;

            // 1m consolidator registered BEFORE the 5m one so On1m updates the buffers before On5m reads them.
            var c1 = new TradeBarConsolidator(TimeSpan.FromMinutes(1));
            c1.DataConsolidated += On1m;
            SubscriptionManager.AddConsolidator(_sym, c1);
            var c5 = new TradeBarConsolidator(TimeSpan.FromMinutes(5));
            c5.DataConsolidated += On5m;
            SubscriptionManager.AddConsolidator(_sym, c5);

            // HARD EOD flatten: fires at 15:55 CT every day REGARDLESS of data (the session-flatten in
            // On5m only runs when a 5m bar arrives, so a position open into a weekend/data-gap could ride
            // for days — up to 89h observed). This guarantees the strategy is genuinely intraday: no
            // position survives the CME daily close (16:00 CT halt), so no overnight/weekend gap exposure.
            Schedule.On(DateRules.EveryDay(_sym), TimeRules.At(15, 55), FlattenEod);

            SetWarmUp(TimeSpan.FromDays(3));
        }

        // ---- second stream: only rollover handling; buffers + fills happen elsewhere ----
        // At Second resolution OnData fires every second. The 1m/5m strategy buffers are built by the
        // consolidators (On1m/On5m); the resting entry + bracket orders fill automatically on the 1s data
        // (honest intrabar sequencing). So OnData just watches for contract rolls.
        public override void OnData(Slice slice)
        {
            foreach (var _ in slice.SymbolChangedEvents.Values)
            {
                CancelEntry();
                if (_inPos) FlattenPosition(_pos.Entry, "rollover");
                // With Raw data the price jumps at a roll. Clear the 1m buffers so the L2 consolidation
                // window can't span the discontinuity, and flag the 5m stream to reset its session (L1).
                _o1.Clear(); _h1.Clear(); _l1.Clear(); _c1.Clear(); _v1.Clear(); _st1.Clear();
                _rolled = true;
            }
        }

        // ---- 1m stream (consolidated from 1s): buffer + per-bar state grade ----
        private void On1m(object sender, TradeBar bar)
        {
            if (!_gotBar) { _gotBar = true; Log($"{Time} data flowing on {bar.Symbol}"); }

            _o1.Add((double)bar.Open); _h1.Add((double)bar.High); _l1.Add((double)bar.Low);
            _c1.Add((double)bar.Close); _v1.Add((double)bar.Volume);

            int n = _c1.Count;
            if (n >= Vab.StateWindow + 1)   // grade the trailing 26-bar window once (safe scratch span)
            {
                int s = n - (Vab.StateWindow + 1), len = Vab.StateWindow + 1;
                _o1.CopyTo(s, _so, 0, len); _h1.CopyTo(s, _sh, 0, len); _l1.CopyTo(s, _sl, 0, len);
                _c1.CopyTo(s, _sc, 0, len); _v1.CopyTo(s, _sv, 0, len);
                _st1.Add(Vab.Grade(_so.AsSpan(0, len), _sh.AsSpan(0, len), _sl.AsSpan(0, len),
                                   _sc.AsSpan(0, len), _sv.AsSpan(0, len)).State);
            }
            else _st1.Add(null);

            if (_c1.Count > 800) TrimHead();
            // Exits are REAL bracket orders (placed in OnOrderEvent once the entry fills) — no manual OHLC
            // check. At Second resolution the stop/target legs only trigger on subsequent 1s bars, so the
            // entry's own bar can't stop it out and a 1m bar can't over-count a stop-out.
        }

        // ---- 5m stream: session bias + decide + entry ----
        private void On5m(object sender, TradeBar bar)
        {
            // A >30-min gap between bars (weekend / missing overnight) breaks the session, so
            // "NY day1..NY day2" doesn't merge into one (which collapses the bias -> no trades).
            bool gap = _lastBar != DateTime.MinValue && (Time - _lastBar).TotalMinutes > 30;
            _lastBar = Time;
            var sess = SessionOf(Time);
            if (sess != _session || gap || _rolled)
            {
                CancelEntry();                                    // drop any resting entry at the boundary
                if (_inPos) FlattenPosition((double)bar.Close, "session_close");
                _session = sess;
                _rolled = false;
                _o5.Clear(); _h5.Clear(); _l5.Clear(); _c5.Clear(); _v5.Clear();
                _traded = new HashSet<(double, double)>();
            }
            if (sess == null) return;

            _o5.Add((double)bar.Open); _h5.Add((double)bar.High); _l5.Add((double)bar.Low);
            _c5.Add((double)bar.Close); _v5.Add((double)bar.Volume);

            if (IsWarmingUp || _inPos) return;
            if (_o5.Count < Vab.MinBars || _c1.Count < Vab.StateWindow + Vab.MinLen) return;

            // L1 bias (session). The session buffer is UNBOUNDED — a data gap can merge sessions
            // (missing overnight bars => "NY day1..NY day2" reads as one), so use fresh arrays here
            // (per-5m, negligible) rather than the fixed scratch. Matches the Python (dynamic lists).
            double strength = Vab.Grade(_o5.ToArray(), _h5.ToArray(), _l5.ToArray(),
                                        _c5.ToArray(), _v5.ToArray()).Strength;
            if (strength >= Vab.BiasStr) _biasBull++;          // DIAGNOSTIC: session-bias sign this bar
            else if (strength <= -Vab.BiasStr) _biasBear++;
            else _biasFlat++;

            int m = _c1.Count, lo = Math.Max(0, m - Vab.DetWindow), cnt = m - lo;                      // last 120 (L2)
            _o1.CopyTo(lo, _so, 0, cnt); _h1.CopyTo(lo, _sh, 0, cnt); _l1.CopyTo(lo, _sl, 0, cnt);
            _c1.CopyTo(lo, _sc, 0, cnt); _v1.CopyTo(lo, _sv, 0, cnt);
            var cons = Vab.FindConsolidation(_st1.GetRange(lo, cnt),
                _so.AsSpan(0, cnt), _sh.AsSpan(0, cnt), _sl.AsSpan(0, cnt), _sc.AsSpan(0, cnt), _sv.AsSpan(0, cnt));

            // ARM a resting stop at the breakout level, so we fill AT the level when price crosses it
            // (not chasing it with a market order after the 5m close). arm = directional + a base +
            // price hasn't broken yet.
            var arm = Vab.DecideArm(strength, cons, (double)bar.Close);
            if (!arm.Valid) { CancelEntry(); return; }
            var sig = (Math.Round(arm.Entry, 1), Math.Round(arm.Stop, 1));
            if (_traded.Contains(sig)) { CancelEntry(); return; }   // already took this base
            if (_future.Mapped == null) return;
            if (_entryTicket == null || _arm.Direction != arm.Direction || Math.Abs(_arm.Entry - arm.Entry) > 1e-9)
            {
                CancelEntry();
                _arm = arm;
                if (arm.Direction == "long") _placeLong++; else _placeShort++;   // DIAGNOSTIC
                _entryTicket = StopMarketOrder(_future.Mapped, arm.Direction == "long" ? 1 : -1, (decimal)arm.Entry);
            }
        }

        private void CancelEntry()
        {
            if (_entryTicket != null) { _entryTicket.Cancel(); _entryTicket = null; }
        }

        private void CancelBracket()
        {
            if (_stopTicket != null) { _stopTicket.Cancel(); _stopTicket = null; }
            if (_tgtTicket != null) { _tgtTicket.Cancel(); _tgtTicket = null; }
        }

        // flatten NOW (rollover / session boundary): drop the bracket, market-out, record once.
        private void FlattenPosition(double exitPx, string reason)
        {
            CancelBracket();
            Liquidate(_future.Mapped);
            Record(exitPx, reason);
            _inPos = false;
        }

        // scheduled hard EOD flatten (data-independent) — drop any resting entry + flatten at market.
        private void FlattenEod(string name, DateTime time)
        {
            CancelEntry();
            if (_inPos)
            {
                double px = (_future.Mapped != null && Securities.ContainsKey(_future.Mapped))
                    ? (double)Securities[_future.Mapped].Price : _pos.Entry;
                FlattenPosition(px, "eod");
            }
        }

        public override void OnOrderEvent(OrderEvent orderEvent)
        {
            if (orderEvent.Status != OrderStatus.Filled) return;
            int id = orderEvent.OrderId;

            // (1) entry stop filled -> record the position + place the REAL protective bracket. Child
            //     orders placed here are evaluated from the NEXT bar on, so the entry's own bar can't
            //     stop us out (the bug that made every QC trade exit at -1R -> 0% win).
            if (_entryTicket != null && id == _entryTicket.OrderId)
            {
                _pos = _arm;
                _pos.Entry = (double)orderEvent.FillPrice;       // actual fill (~the level) for honest R
                _inPos = true; _entries++;
                if (_arm.Direction == "long") _fillLong++; else _fillShort++;   // DIAGNOSTIC
                _traded.Add((Math.Round(_arm.Entry, 1), Math.Round(_arm.Stop, 1)));
                _entryTicket = null;

                int exitQty = _arm.Direction == "long" ? -1 : 1;   // close = opposite side of the entry
                // tag as a NAMED arg: LEAN's 4th positional param is `bool asynchronous`, not the tag.
                _stopTicket = StopMarketOrder(_future.Mapped, exitQty, (decimal)_pos.Stop, tag: "stop");
                _tgtTicket = LimitOrder(_future.Mapped, exitQty, (decimal)_pos.Target, tag: "target");
                return;
            }

            // (2) a bracket leg filled -> record at the honest fill price, cancel the sibling (manual OCO).
            if (_stopTicket != null && id == _stopTicket.OrderId)
            {
                _stopTicket = null;
                if (_tgtTicket != null) { _tgtTicket.Cancel(); _tgtTicket = null; }
                Record((double)orderEvent.FillPrice, "stop"); _inPos = false;
                return;
            }
            if (_tgtTicket != null && id == _tgtTicket.OrderId)
            {
                _tgtTicket = null;
                if (_stopTicket != null) { _stopTicket.Cancel(); _stopTicket = null; }
                Record((double)orderEvent.FillPrice, "target"); _inPos = false;
            }
        }

        // ---- checkpointing (throttled: logging every bar trips QC's rate limit) ----
        private void Record(double exitPx, string reason)
        {
            double risk = Math.Abs(_pos.Entry - _pos.Stop); if (risk == 0) risk = 1e-9;
            double R = Math.Round((exitPx - _pos.Entry) / risk * (_pos.Direction == "long" ? 1 : -1), 3);
            _trades.Add(new Vab.TradeRec {
                time = Time.ToString("o"), direction = _pos.Direction, entry = _pos.Entry,
                stop = _pos.Stop, target = _pos.Target, exit = exitPx, reason = reason, R = R });
            Checkpoint(false);
        }

        private void Checkpoint(bool force)
        {
            int n = _trades.Count;
            if (!force && n % 25 != 0) return;
            int wins = 0; double total = 0;
            foreach (var t in _trades) { if (t.R > 0) wins++; total += t.R; }
            Log($"{Time} running: {n} trades, {wins}/{Math.Max(n, 1)} win, {Math.Round(total, 2)}R");
            ObjectStore.Save("vabreakout_trades.json", JsonConvert.SerializeObject(_trades));
        }

        public override void OnEndOfAlgorithm()
        {
            if (_trades.Count > 0) Checkpoint(true);
            int n = _trades.Count, wins = 0; double total = 0;
            foreach (var t in _trades) { if (t.R > 0) wins++; total += t.R; }
            Log($"DONE — {n} trades, {(n > 0 ? 100 * wins / n : 0)}% win, {Math.Round(total, 2)}R total " +
                $"(entries {_entries}, gotBar {_gotBar})");
            // DIAGNOSTIC: trace where longs vanish. bias(bull/bear/flat) -> placed(L/S) -> filled(L/S).
            Log($"DIAG bias  bull={_biasBull} bear={_biasBear} flat={_biasFlat}");
            Log($"DIAG place long={_placeLong} short={_placeShort}   |   fill long={_fillLong} short={_fillShort}");
        }

        // ---- helpers ----
        private void TrimHead()
        {
            int drop = _c1.Count - 400;
            _o1.RemoveRange(0, drop); _h1.RemoveRange(0, drop); _l1.RemoveRange(0, drop);
            _c1.RemoveRange(0, drop); _v1.RemoveRange(0, drop); _st1.RemoveRange(0, drop);
        }

        private static string SessionOf(DateTime dt)
        {
            int m = dt.Hour * 60 + dt.Minute;
            if (m >= 18 * 60 || m < 3 * 60) return "Asia";
            if (m >= 3 * 60 && m < 8 * 60) return "London";
            if (m >= 8 * 60 && m < 17 * 60) return "NY";
            return null;
        }
    }

    // ================= the strategy math (mirrors grade_lib.py) — allocation-free, no LINQ =========
    public static class Vab
    {
        public const int NRows = 24, StateWindow = 25, MinLen = 15, MaxAge = 40, DetWindow = 120, MinBars = 8;
        public const double ECut = 0.38, ACut = 0.55, BiasStr = 0.3, TargetR = 2.0;

        public struct GResult { public string State, Direction; public double Strength, Vah, Val, Poc; }
        public struct Cons { public bool Valid; public double Vah, Val, Poc; public int Len, EndedAgo; }
        public struct Intent { public bool Valid; public string Direction; public double Entry, Stop, Target; }
        public class TradeRec { public string time, direction, reason; public double entry, stop, target, exit, R; }

        public static GResult Grade(ReadOnlySpan<double> o, ReadOnlySpan<double> h, ReadOnlySpan<double> l,
                                    ReadOnlySpan<double> c, ReadOnlySpan<double> v)
        {
            int n = c.Length;
            double O = o[0], C = c[n - 1], H = h[0], L = l[0], travel = 0;
            for (int i = 0; i < n; i++) { if (h[i] > H) H = h[i]; if (l[i] < L) L = l[i]; }
            for (int i = 1; i < n; i++) { double d = c[i] - c[i - 1]; travel += d < 0 ? -d : d; }
            double rng = H - L; if (rng == 0) rng = 1e-9;
            if (travel == 0) travel = 1e-9;
            double net = C - O, rs = rng / NRows;

            Span<double> bin = stackalloc double[NRows];
            for (int p = 0; p < n; p++)
            {
                double bl = l[p], bh = h[p], vol = v[p];
                if (bh <= bl) { bin[Clamp((int)((bl - L) / rs))] += vol; continue; }
                int loI = Clamp((int)((bl - L) / rs)), hiI = Clamp((int)((bh - L) / rs));
                double span = bh - bl;
                for (int bi = loI; bi <= hiI; bi++)
                {
                    double bBot = L + bi * rs, ov = Math.Min(bh, bBot + rs) - Math.Max(bl, bBot);
                    if (ov > 0) bin[bi] += vol * (ov / span);
                }
            }
            double binSum = 0; for (int i = 0; i < NRows; i++) binSum += bin[i];
            int pocI = 0, vaLo, vaHi;
            if (binSum <= 0) { vaLo = 0; vaHi = NRows - 1; }
            else
            {
                for (int i = 1; i < NRows; i++) if (bin[i] > bin[pocI]) pocI = i;
                (vaLo, vaHi) = ValueArea(bin, pocI, 0.70, binSum);
            }
            double acceptance = 1.0 - (double)(vaHi - vaLo + 1) / NRows, efficiency = Math.Abs(net) / travel;
            string direction = net > 0 ? "bull" : net < 0 ? "bear" : "flat", state;
            if (n < MinBars) state = "UNCLEAR";
            else
            {
                string d = direction == "bull" ? "UP" : "DN";
                if (efficiency >= ECut) state = (acceptance >= ACut ? "GRIND " : "IMPULSE ") + d;
                else state = acceptance >= ACut ? "CONSOLIDATION" : "WHIPSAW";
            }
            return new GResult {
                State = state, Direction = direction, Strength = net / rng,
                Vah = L + (vaHi + 1) * rs, Val = L + vaLo * rs, Poc = L + (pocI + 0.5) * rs };
        }

        private static int Clamp(int i) => i < 0 ? 0 : (i >= NRows ? NRows - 1 : i);

        private static (int, int) ValueArea(ReadOnlySpan<double> vol, int poc, double pct, double sum)
        {
            double target = sum * pct, acc = vol[poc];
            int lo = poc, hi = poc, n = vol.Length;
            while (acc < target && (lo > 0 || hi < n - 1))
            {
                double below = lo > 0 ? vol[lo - 1] : -1.0, above = hi < n - 1 ? vol[hi + 1] : -1.0;
                if (above >= below) { hi++; acc += vol[hi]; } else { lo--; acc += vol[lo]; }
            }
            return (lo, hi);
        }

        // states: the last <=DetWindow per-bar states (a fresh copy — modified here); o..v aligned spans.
        public static Cons FindConsolidation(List<string> states, ReadOnlySpan<double> o, ReadOnlySpan<double> h,
                                             ReadOnlySpan<double> l, ReadOnlySpan<double> c, ReadOnlySpan<double> v)
        {
            int n = states.Count;
            if (n < StateWindow + MinLen) return default;
            for (int i = 0; i < Math.Min(StateWindow, n); i++) states[i] = null;   // tail-window warm-up
            int bestA = -1, bestB = -1, i2 = 0;
            while (i2 < n)
            {
                int j = i2; while (j < n && states[j] == states[i2]) j++;
                if (states[i2] == "CONSOLIDATION" && j - i2 >= MinLen) { bestA = i2; bestB = j - 1; }
                i2 = j;
            }
            if (bestA < 0) return default;
            int endedAgo = n - 1 - bestB;
            if (endedAgo > MaxAge) return default;
            int len = bestB - bestA + 1;
            var g = Grade(o.Slice(bestA, len), h.Slice(bestA, len), l.Slice(bestA, len),
                          c.Slice(bestA, len), v.Slice(bestA, len));
            if (g.Vah <= g.Val) return default;
            return new Cons { Valid = true, Vah = g.Vah, Val = g.Val, Poc = g.Poc, Len = len, EndedAgo = endedAgo };
        }

        public static Intent Decide(double strength, Cons cons, double price)
        {
            if (!cons.Valid || cons.Vah <= cons.Val) return default;
            double risk = cons.Vah - cons.Val;
            if (strength >= BiasStr && price > cons.Vah)
                return new Intent { Valid = true, Direction = "long", Entry = cons.Vah, Stop = cons.Val, Target = cons.Vah + TargetR * risk };
            if (strength <= -BiasStr && price < cons.Val)
                return new Intent { Valid = true, Direction = "short", Entry = cons.Val, Stop = cons.Vah, Target = cons.Val - TargetR * risk };
            return default;
        }

        // Arm version for resting stop-orders: fire when directional + a base exists AND price HASN'T
        // broken yet (price < VAH for long / > VAL for short), so a stop parked at the level fills ON
        // the break rather than chasing it after the 5m close.
        public static Intent DecideArm(double strength, Cons cons, double price)
        {
            if (!cons.Valid || cons.Vah <= cons.Val) return default;
            double risk = cons.Vah - cons.Val;
            if (strength >= BiasStr && price < cons.Vah)
                return new Intent { Valid = true, Direction = "long", Entry = cons.Vah, Stop = cons.Val, Target = cons.Vah + TargetR * risk };
            if (strength <= -BiasStr && price > cons.Val)
                return new Intent { Valid = true, Direction = "short", Entry = cons.Val, Stop = cons.Vah, Target = cons.Val - TargetR * risk };
            return default;
        }
    }
}
