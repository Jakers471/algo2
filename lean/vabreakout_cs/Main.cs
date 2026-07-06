/*
 * lean/vabreakout_cs/Main.cs — VA-breakout on QuantConnect LEAN (NQ E-mini), in C#.
 *
 * Byte-for-byte port of lean/vabreakout (Python) / src/strategy: L1 = 5m session bias
 * (Grade().Strength), L2 = a 1m CONSOLIDATION; enter on the break of its value area in the
 * session's direction, stop = opposite edge, target 2R. Entries decided on 5m; exits on 1m.
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
using System.Runtime.InteropServices;
using Newtonsoft.Json;
using QuantConnect.Data;
using QuantConnect.Data.Consolidators;
using QuantConnect.Data.Market;
using QuantConnect.Securities.Future;

namespace QuantConnect.Algorithm.CSharp
{
    public class VaBreakout : QCAlgorithm
    {
        private Future _future;
        private Symbol _sym;
        private readonly List<double> _o1 = new(), _h1 = new(), _l1 = new(), _c1 = new(), _v1 = new();
        private readonly List<string> _st1 = new();
        private readonly List<double> _o5 = new(), _h5 = new(), _l5 = new(), _c5 = new(), _v5 = new();
        private string _session = null;
        private HashSet<(double, double)> _traded = new();
        private Vab.Intent _pos;
        private bool _inPos = false;
        private readonly List<Vab.TradeRec> _trades = new();
        private bool _gotBar = false;
        private int _entries = 0;

        public override void Initialize()
        {
            SetStartDate(2022, 1, 1);
            SetEndDate(2025, 1, 1);
            SetCash(100000);
            SetTimeZone(TimeZones.Chicago);

            _future = AddFuture(Futures.Indices.NASDAQ100EMini, Resolution.Minute,
                dataNormalizationMode: DataNormalizationMode.BackwardsRatio,
                dataMappingMode: DataMappingMode.LastTradingDay, contractDepthOffset: 0);
            _future.SetFilter(0, 182);
            _sym = _future.Symbol;

            var cons = new TradeBarConsolidator(TimeSpan.FromMinutes(5));
            cons.DataConsolidated += On5m;
            SubscriptionManager.AddConsolidator(_sym, cons);

            SetWarmUp(TimeSpan.FromDays(3));
        }

        // ---- 1m stream: buffer + intrabar exit ----
        public override void OnData(Slice slice)
        {
            foreach (var _ in slice.SymbolChangedEvents.Values)
                if (_inPos) { Liquidate(); Record(_pos.Entry, "rollover"); _inPos = false; }

            if (!slice.Bars.TryGetValue(_sym, out var bar) &&
                !slice.Bars.TryGetValue(_future.Mapped, out bar))
                return;

            if (!_gotBar) { _gotBar = true; Log($"{Time} data flowing on {bar.Symbol}"); }

            _o1.Add((double)bar.Open); _h1.Add((double)bar.High); _l1.Add((double)bar.Low);
            _c1.Add((double)bar.Close); _v1.Add((double)bar.Volume);

            int n = _c1.Count;
            if (n >= Vab.StateWindow + 1)   // grade the trailing 26-bar window once (zero-copy span)
            {
                int s = n - (Vab.StateWindow + 1), len = Vab.StateWindow + 1;
                _st1.Add(Vab.Grade(
                    CollectionsMarshal.AsSpan(_o1).Slice(s, len), CollectionsMarshal.AsSpan(_h1).Slice(s, len),
                    CollectionsMarshal.AsSpan(_l1).Slice(s, len), CollectionsMarshal.AsSpan(_c1).Slice(s, len),
                    CollectionsMarshal.AsSpan(_v1).Slice(s, len)).State);
            }
            else _st1.Add(null);

            if (_c1.Count > 800) TrimHead();

            if (_inPos) CheckExit(bar);
        }

        private void CheckExit(TradeBar bar)
        {
            bool lng = _pos.Direction == "long";
            double hi = (double)bar.High, lo = (double)bar.Low;
            bool hitStop = lng ? lo <= _pos.Stop : hi >= _pos.Stop;
            bool hitTgt = lng ? hi >= _pos.Target : lo <= _pos.Target;
            if (hitStop || hitTgt)
            {
                Liquidate(_future.Mapped);
                Record(hitStop ? _pos.Stop : _pos.Target, hitStop ? "stop" : "target");
                _inPos = false;
            }
        }

        // ---- 5m stream: session bias + decide + entry ----
        private void On5m(object sender, TradeBar bar)
        {
            var sess = SessionOf(Time);
            if (sess != _session)
            {
                if (_inPos) { Liquidate(_future.Mapped); Record((double)bar.Close, "session_close"); _inPos = false; }
                _session = sess;
                _o5.Clear(); _h5.Clear(); _l5.Clear(); _c5.Clear(); _v5.Clear();
                _traded = new HashSet<(double, double)>();
            }
            if (sess == null) return;

            _o5.Add((double)bar.Open); _h5.Add((double)bar.High); _l5.Add((double)bar.Low);
            _c5.Add((double)bar.Close); _v5.Add((double)bar.Volume);

            if (IsWarmingUp || _inPos) return;
            if (_o5.Count < Vab.MinBars || _c1.Count < Vab.StateWindow + Vab.MinLen) return;

            double strength = Vab.Grade(
                CollectionsMarshal.AsSpan(_o5), CollectionsMarshal.AsSpan(_h5), CollectionsMarshal.AsSpan(_l5),
                CollectionsMarshal.AsSpan(_c5), CollectionsMarshal.AsSpan(_v5)).Strength;              // L1 bias

            int m = _c1.Count, lo = Math.Max(0, m - Vab.DetWindow), cnt = m - lo;                      // last 120 (L2)
            var cons = Vab.FindConsolidation(_st1.GetRange(lo, cnt),
                CollectionsMarshal.AsSpan(_o1).Slice(lo, cnt), CollectionsMarshal.AsSpan(_h1).Slice(lo, cnt),
                CollectionsMarshal.AsSpan(_l1).Slice(lo, cnt), CollectionsMarshal.AsSpan(_c1).Slice(lo, cnt),
                CollectionsMarshal.AsSpan(_v1).Slice(lo, cnt));

            var intent = Vab.Decide(strength, cons, (double)bar.Close);
            if (!intent.Valid) return;
            var sig = (Math.Round(intent.Entry, 1), Math.Round(intent.Stop, 1));
            if (_traded.Contains(sig)) return;
            _traded.Add(sig);
            Enter(intent);
        }

        private void Enter(Vab.Intent intent)
        {
            MarketOrder(_future.Mapped, intent.Direction == "long" ? 1 : -1);
            _pos = intent; _inPos = true; _entries++;
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
    }
}
