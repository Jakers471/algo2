/*
 * lean/vabreakout_cs/Main.cs — VA-breakout on QuantConnect LEAN (NQ E-mini), in C#.
 *
 * A byte-for-byte port of lean/vabreakout (Python), which itself mirrors src/strategy:
 *   L1 = 5m session bias (Grade().Strength), L2 = a 1m CONSOLIDATION; enter on the break of
 *   its value area in the session's direction, stop = opposite edge, target 2R. Entries decided
 *   on 5m; exits checked on 1m (intrabar). Sessions off the algo clock (Chicago).
 *
 * Why C#: compiled + no Python GIL -> dramatically faster than the Python algo (no numpy tricks
 * needed; plain loops are fast). Same logic and constants, so it should reproduce the Python
 * trades (modulo QC's continuous-contract data). NOTE: written from the LEAN C# API but not
 * compiled in this environment — run `lean cloud backtest` and we iterate on any compile errors.
 */
using System;
using System.Collections.Generic;
using System.Linq;
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
        // 1m buffers (parallel arrays) + per-bar states; 5m session buffers
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
            SetTimeZone(TimeZones.Chicago);   // so Time matches the Chicago session windows

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
            foreach (var _ in slice.SymbolChangedEvents.Values)   // contract rollover -> go flat
                if (_inPos) { Liquidate(); Record(_pos.Entry, "rollover"); _inPos = false; }

            if (!slice.Bars.TryGetValue(_sym, out var bar) &&
                !slice.Bars.TryGetValue(_future.Mapped, out bar))
                return;

            if (!_gotBar) { _gotBar = true; Log($"{Time} data flowing on {bar.Symbol}"); }

            _o1.Add((double)bar.Open); _h1.Add((double)bar.High); _l1.Add((double)bar.Low);
            _c1.Add((double)bar.Close); _v1.Add((double)bar.Volume);

            int n = _c1.Count;
            if (n >= Vab.StateWindow + 1)   // grade the trailing 26-bar window (bars[i-25:i+1]) once
            {
                int s = n - (Vab.StateWindow + 1), len = Vab.StateWindow + 1;
                _st1.Add(Vab.Grade(Sub(_o1, s, len), Sub(_h1, s, len), Sub(_l1, s, len),
                                   Sub(_c1, s, len), Sub(_v1, s, len)).State);
            }
            else _st1.Add(null);

            if (_c1.Count > 800) TrimHead();   // amortized trim: every ~400 bars, not every bar

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
            var sess = SessionOf(Time);   // algo clock (Chicago)
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

            double strength = Vab.Grade(_o5.ToArray(), _h5.ToArray(), _l5.ToArray(),
                                        _c5.ToArray(), _v5.ToArray()).Strength;          // L1 bias

            int m = _c1.Count, lo = Math.Max(0, m - Vab.DetWindow), cnt = m - lo;         // last 120 (L2)
            var cons = Vab.FindConsolidation(_st1.GetRange(lo, cnt),
                Sub(_o1, lo, cnt), Sub(_h1, lo, cnt), Sub(_l1, lo, cnt), Sub(_c1, lo, cnt), Sub(_v1, lo, cnt));

            var intent = Vab.Decide(strength, cons, (double)bar.Close);
            if (!intent.Valid) return;
            var sig = (Math.Round(intent.Entry, 1), Math.Round(intent.Stop, 1));
            if (_traded.Contains(sig)) return;   // one trade per base
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
            int wins = _trades.Count(t => t.R > 0);
            double total = Math.Round(_trades.Sum(t => t.R), 2);
            Log($"{Time} running: {n} trades, {wins}/{Math.Max(n, 1)} win, {total}R");
            ObjectStore.Save("vabreakout_trades.json", JsonConvert.SerializeObject(_trades));
        }

        public override void OnEndOfAlgorithm()
        {
            if (_trades.Count > 0) Checkpoint(true);
            int n = _trades.Count, wins = _trades.Count(t => t.R > 0);
            double total = Math.Round(_trades.Sum(t => t.R), 2);
            Log($"DONE — {n} trades, {(n > 0 ? 100.0 * wins / n : 0):0}% win, {total}R total " +
                $"(entries {_entries}, gotBar {_gotBar})");
        }

        // ---- helpers ----
        private static double[] Sub(List<double> buf, int start, int count) => buf.GetRange(start, count).ToArray();

        private void TrimHead()
        {
            int drop = _c1.Count - 400;
            foreach (var b in new[] { _o1, _h1, _l1, _c1, _v1 }) b.RemoveRange(0, drop);
            _st1.RemoveRange(0, drop);
        }

        private static string SessionOf(DateTime dt)
        {
            int m = dt.Hour * 60 + dt.Minute;
            if (m >= 18 * 60 || m < 3 * 60) return "Asia";       // wraps midnight
            if (m >= 3 * 60 && m < 8 * 60) return "London";
            if (m >= 8 * 60 && m < 17 * 60) return "NY";
            return null;
        }
    }

    // ================= the strategy math (mirrors grade_lib.py) =================
    public static class Vab
    {
        public const int NRows = 24, StateWindow = 25, MinLen = 15, MaxAge = 40, DetWindow = 120, MinBars = 8;
        public const double ECut = 0.38, ACut = 0.55, BiasStr = 0.3, TargetR = 2.0;

        public struct GResult { public string State, Direction; public double Strength, Vah, Val, Poc; }
        public struct Cons { public bool Valid; public double Vah, Val, Poc; public int Len, EndedAgo; }
        public struct Intent { public bool Valid; public string Direction; public double Entry, Stop, Target; }
        public class TradeRec { public string time, direction, reason; public double entry, stop, target, exit, R; }

        private static int ArgMax(double[] a) { int m = 0; for (int i = 1; i < a.Length; i++) if (a[i] > a[m]) m = i; return m; }

        private static (int, int) ValueArea(double[] vol, int poc, double pct)
        {
            double target = vol.Sum() * pct, acc = vol[poc];
            int lo = poc, hi = poc, n = vol.Length;
            while (acc < target && (lo > 0 || hi < n - 1))
            {
                double below = lo > 0 ? vol[lo - 1] : -1.0, above = hi < n - 1 ? vol[hi + 1] : -1.0;
                if (above >= below) { hi++; acc += vol[hi]; } else { lo--; acc += vol[lo]; }
            }
            return (lo, hi);
        }

        private static double[] ProfileFor(double[] h, double[] l, double[] v, double bas, double rs, int nRows)
        {
            var bin = new double[nRows];
            for (int p = 0; p < h.Length; p++)
            {
                double bl = l[p], bh = h[p], vol = v[p];
                if (bh <= bl) { bin[Math.Min(Math.Max((int)((bl - bas) / rs), 0), nRows - 1)] += vol; continue; }
                int loI = Math.Min(Math.Max((int)((bl - bas) / rs), 0), nRows - 1);
                int hiI = Math.Min(Math.Max((int)((bh - bas) / rs), 0), nRows - 1);
                double span = bh - bl;
                for (int bi = loI; bi <= hiI; bi++)
                {
                    double bBot = bas + bi * rs, overlap = Math.Min(bh, bBot + rs) - Math.Max(bl, bBot);
                    if (overlap > 0) bin[bi] += vol * (overlap / span);
                }
            }
            return bin;
        }

        public static GResult Grade(double[] o, double[] h, double[] l, double[] c, double[] v)
        {
            int n = c.Length;
            double O = o[0], C = c[n - 1], H = h.Max(), L = l.Min();
            double rng = (H - L); if (rng == 0) rng = 1e-9;
            double net = C - O;
            double travel = 0; for (int i = 1; i < n; i++) travel += Math.Abs(c[i] - c[i - 1]);
            if (travel == 0) travel = 1e-9;

            double rs = rng / NRows;
            var bin = ProfileFor(h, l, v, L, rs, NRows);
            int pocI; int vaLo, vaHi;
            if (bin.Sum() <= 0) { pocI = 0; vaLo = 0; vaHi = NRows - 1; }
            else { pocI = ArgMax(bin); (vaLo, vaHi) = ValueArea(bin, pocI, 0.70); }

            double acceptance = 1.0 - (double)(vaHi - vaLo + 1) / NRows;
            double efficiency = Math.Abs(net) / travel;
            string direction = net > 0 ? "bull" : net < 0 ? "bear" : "flat";
            string state;
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

        private static List<(int, int)> ConsRuns(IList<string> states, int minLen)
        {
            var outp = new List<(int, int)>();
            int i = 0, n = states.Count;
            while (i < n)
            {
                int j = i;
                while (j < n && states[j] == states[i]) j++;
                if (states[i] == "CONSOLIDATION" && j - i >= minLen) outp.Add((i, j - 1));
                i = j;
            }
            return outp;
        }

        public static Cons FindConsolidation(List<string> states, double[] o, double[] h, double[] l, double[] c, double[] v)
        {
            int n = states.Count;
            if (n < StateWindow + MinLen) return new Cons { Valid = false };
            int lo = Math.Max(0, n - DetWindow);
            var st = states.GetRange(lo, n - lo);
            for (int i = 0; i < Math.Min(StateWindow, st.Count); i++) st[i] = null;   // tail-window warm-up
            var runs = ConsRuns(st, MinLen);
            if (runs.Count == 0) return new Cons { Valid = false };
            var (a, b) = runs[runs.Count - 1];
            int endedAgo = (n - lo) - 1 - b;
            if (endedAgo > MaxAge) return new Cons { Valid = false };
            int A = lo + a, B = lo + b, len = B - A + 1;
            var g = Grade(o[A..(B + 1)], h[A..(B + 1)], l[A..(B + 1)], c[A..(B + 1)], v[A..(B + 1)]);
            if (g.Vah <= g.Val) return new Cons { Valid = false };
            return new Cons { Valid = true, Vah = g.Vah, Val = g.Val, Poc = g.Poc, Len = len, EndedAgo = endedAgo };
        }

        public static Intent Decide(double strength, Cons cons, double price)
        {
            if (!cons.Valid || cons.Vah <= cons.Val) return new Intent { Valid = false };
            double risk = cons.Vah - cons.Val;
            if (strength >= BiasStr && price > cons.Vah)
                return new Intent { Valid = true, Direction = "long", Entry = cons.Vah, Stop = cons.Val, Target = cons.Vah + TargetR * risk };
            if (strength <= -BiasStr && price < cons.Val)
                return new Intent { Valid = true, Direction = "short", Entry = cons.Val, Stop = cons.Vah, Target = cons.Val - TargetR * risk };
            return new Intent { Valid = false };
        }
    }
}
