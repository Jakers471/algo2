// ninjatrader/VABreakout.cs — VA-breakout ported to NinjaTrader 8 (NinjaScript).
//
// Logic mirrors lean/vabreakout_cs/Main.cs and src/strategy: L1 = 5m session bias
// (Grade().Strength), L2 = a 1m CONSOLIDATION; ARM a resting stop at the value-area edge in
// the session's direction so we fill AT the level on the break (not chase it). Stop = opposite
// VA edge, target 2R. Entries decided on 5m; the resting order + bracket handle 1m/intrabar.
//
// DIFFERENCES vs the LEAN port (on purpose):
//  - No Span/stackalloc — NT8 runs .NET Framework and may lack System.Memory. Grade takes
//    (List, start, len) instead and uses a reusable _bin scratch array (zero per-bar alloc).
//  - Exits are REAL orders via SetStopLoss/SetProfitTarget, not a manual bar-OHLC check. Under
//    Strategy Analyzer *Tick Replay* these fill honestly (this is the fix for the "fill mirage").
//
// SETUP IN NT8:
//  - Run the Strategy Analyzer with the PRIMARY series = NQ, 1 MINUTE. The 5m series is added
//    below in State.Configure. (Primary MUST be 1m or the buffers are wrong.)
//  - Turn ON Tick Replay for realistic fills, else win% is optimistic.
//  - TIMEZONE CAVEAT: SessionOf() thresholds below assume the bar clock is Chicago/CT (as LEAN
//    ran). NinjaTrader shows bar times in your configured timezone (often ET = CT+1h). If yours
//    is ET, shift each hour boundary by +1 (18->19, 3->4, 8->9, 17->18). See SessionOf().

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Text;
using System.Globalization;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.SuperDom;
using NinjaTrader.Gui.Tools;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.AddOns;   // TradeExporter (reusable persistence module)
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.NinjaScript.Indicators;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

// Strategies MUST be in the NinjaTrader.NinjaScript.Strategies namespace. A trailing segment
// (e.g. ".NinjaTrader") creates a nested NinjaTrader namespace that shadows the root one and
// breaks name resolution across the ENTIRE Custom assembly (DEMA.cs, Gui, etc.). Do not add one.
namespace NinjaTrader.NinjaScript.Strategies
{
    public class VABreakout : Strategy
    {
        // ---- strategy knobs (mirror Vab in Main.cs) ----
        private const int NRows = 24, StateWindow = 25, MinLen = 15, MaxAge = 40, DetWindow = 120, MinBars = 8;
        private const double ECut = 0.38, ACut = 0.55, BiasStr = 0.3, TargetR = 2.0;

        // ---- 1m + 5m buffers (chronological: [0] = oldest, like the LEAN lists) ----
        private readonly List<double> _o1 = new List<double>(), _h1 = new List<double>(),
            _l1 = new List<double>(), _c1 = new List<double>(), _v1 = new List<double>();
        private readonly List<string> _st1 = new List<string>();
        private readonly List<double> _o5 = new List<double>(), _h5 = new List<double>(),
            _l5 = new List<double>(), _c5 = new List<double>(), _v5 = new List<double>();

        private readonly double[] _bin = new double[NRows];   // reusable profile scratch (no per-call alloc)

        private string _session = null;
        private DateTime _lastBar = DateTime.MinValue;        // gap detection (breaks a merged session)
        private HashSet<string> _traded = new HashSet<string>();
        private Intent _pos, _arm;
        private bool _inPos = false;
        private Order _entryOrder = null;                     // resting stop entry
        private int _entries = 0;
        private int _nextPct = 0;                             // next backtest-progress milestone to print
        private const int ProgressStep = 10;                  // print progress + checkpoint-save every N%

        // per-trade stop/target, aligned to SystemPerformance.AllTrades order (for R scoring on export)
        private readonly List<double> _recStop = new List<double>(), _recTarget = new List<double>();
        private DateTime _runStart = DateTime.MinValue, _runEnd;   // requested (data) range for meta.json

        // EXPORT CONTRACT: capture runs into the repo (not Desktop). Cost figures match Python/QC.
        private const string RepoDir = @"C:\Users\jakers\Desktop\volume_profile_algo";
        private const double CommissionRt = 4.0;              // $/round-turn (set via Commission template in UI)
        private const int SlippageTicks = 1;                  // enforced in code below (Slippage = 1)

        private struct GResult { public string State, Direction; public double Strength, Vah, Val, Poc; }
        private struct Cons { public bool Valid; public double Vah, Val, Poc; public int Len, EndedAgo; }
        private struct Intent { public bool Valid; public string Direction; public double Entry, Stop, Target; }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "VA-breakout: 5m session bias + 1m consolidation break, stop opposite edge, 2R.";
                Name = "VABreakout";
                Calculate = Calculate.OnBarClose;
                EntriesPerDirection = 1;
                EntryHandling = EntryHandling.AllEntries;
                IsExitOnSessionCloseStrategy = true;          // EOD safety net; custom sessions flatten below
                ExitOnSessionCloseSeconds = 30;
                IsFillLimitOnTouch = false;
                MaximumBarsLookBack = MaximumBarsLookBack.TwoHundredFiftySix;
                OrderFillResolution = OrderFillResolution.Standard;
                Slippage = SlippageTicks;                     // COST CONTRACT: 1 tick per fill (NQ tick = $5)
                StartBehavior = StartBehavior.WaitUntilFlat;
                TimeInForce = TimeInForce.Gtc;
                TraceOrders = false;
                RealtimeErrorHandling = RealtimeErrorHandling.StopCancelClose;
                StopTargetHandling = StopTargetHandling.PerEntryExecution;
                BarsRequiredToTrade = 20;
                IsInstantiatedOnEachOptimizationIteration = true;
                ExportTrades = true;                          // write trades.csv + meta.json into the repo at run end
                SampleType   = "full";                        // NOT hardcoded in meta — a per-run label (default full)
                Notes        = "";
            }
            else if (State == State.Configure)
            {
                // FAIL FAST: every bar-count window (StateWindow, DetWindow, ...) counts 1-MINUTE bars.
                // A tick/other primary silently corrupts the timescale — refuse to run.
                if (BarsPeriod.BarsPeriodType != BarsPeriodType.Minute || BarsPeriod.Value != 1)
                    throw new Exception(string.Format(
                        "VABreakout requires a 1-Minute primary series, got {0}/{1}",
                        BarsPeriod.BarsPeriodType, BarsPeriod.Value));

                // add the 5m series of the SAME primary instrument (index 1). Primary (index 0) = 1m.
                AddDataSeries(Data.BarsPeriodType.Minute, 5);
            }
            else if (State == State.Terminated)
            {
                if (ExportTrades) WriteTrades();
            }
        }

        [NinjaScriptProperty]
        [Display(Name = "Export run (trades.csv + meta.json)", GroupName = "Reporting", Order = 0)]
        public bool ExportTrades { get; set; }

        // Experiment labels — a property of the RUN, not the code, so set per-run in the Analyzer.
        [NinjaScriptProperty]
        [Display(Name = "Sample type (full / out_of_sample / in_sample)", GroupName = "Reporting", Order = 1)]
        public string SampleType { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Run notes", GroupName = "Reporting", Order = 2)]
        public string Notes { get; set; }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress == 0) On1m();
            else if (BarsInProgress == 1) On5m();
        }

        // ---- 1m stream: buffer + per-bar state grade ----
        private void On1m()
        {
            if (CurrentBars[0] < 0) return;
            if (_runStart == DateTime.MinValue) _runStart = Times[0][0];   // requested-range start (first 1m bar)
            _runEnd = Times[0][0];                                         // ... end (last 1m bar seen)
            _o1.Add(Open[0]); _h1.Add(High[0]); _l1.Add(Low[0]); _c1.Add(Close[0]); _v1.Add(Volume[0]);

            int n = _c1.Count;
            if (n >= StateWindow + 1)
                _st1.Add(Grade(_o1, _h1, _l1, _c1, _v1, n - (StateWindow + 1), StateWindow + 1).State);
            else
                _st1.Add(null);

            if (_c1.Count > 800) TrimHead();
            // exits are resting bracket orders (SetStopLoss/SetProfitTarget) — no manual exit check.

            ReportProgress();   // % complete + periodic partial save (primary/1m stream drives this)
        }

        // ---- 5m stream: session bias + decide + arm resting entry ----
        private void On5m()
        {
            if (CurrentBars[1] < 0) return;
            DateTime now = Times[1][0];
            bool gap = _lastBar != DateTime.MinValue && (now - _lastBar).TotalMinutes > 30;
            _lastBar = now;

            string sess = SessionOf(now);
            if (sess != _session || gap)
            {
                CancelEntry();
                if (_inPos) FlattenAll();
                _session = sess;
                _o5.Clear(); _h5.Clear(); _l5.Clear(); _c5.Clear(); _v5.Clear();
                _traded.Clear();
            }
            if (sess == null) return;

            _o5.Add(Opens[1][0]); _h5.Add(Highs[1][0]); _l5.Add(Lows[1][0]);
            _c5.Add(Closes[1][0]); _v5.Add(Volumes[1][0]);

            if (_inPos) return;
            if (_o5.Count < MinBars || _c1.Count < StateWindow + MinLen) return;

            // L1 bias (session, unbounded window — grade the full session buffer)
            double strength = Grade(_o5, _h5, _l5, _c5, _v5, 0, _c5.Count).Strength;

            // L2 base: find the 1m CONSOLIDATION in the last DetWindow bars
            int m = _c1.Count, lo = Math.Max(0, m - DetWindow), cnt = m - lo;
            Cons cons = FindConsolidation(lo, cnt);

            double price = Closes[1][0];
            Intent arm = DecideArm(strength, cons, price);
            if (!arm.Valid) { CancelEntry(); return; }

            string sig = Math.Round(arm.Entry, 1).ToString("F1") + "|" + Math.Round(arm.Stop, 1).ToString("F1");
            if (_traded.Contains(sig)) { CancelEntry(); return; }

            // NinjaTrader IGNORES a stop-entry whose price sits within the primary (1m) bar's range
            // ("invalid based on the price range of the bar") and then disables the whole strategy.
            // Only arm when the breakout level is still strictly beyond price on the correct side —
            // i.e. the break hasn't happened yet. If price already reached it, skip (missed break).
            double pHigh = Highs[0][0], pLow = Lows[0][0];
            bool sideOk = arm.Direction == "long" ? arm.Entry > pHigh : arm.Entry < pLow;
            if (!sideOk) { CancelEntry(); return; }

            // (re)arm a resting stop at the breakout level with an attached bracket
            if (_entryOrder == null || _arm.Direction != arm.Direction || Math.Abs(_arm.Entry - arm.Entry) > 1e-9)
            {
                CancelEntry();
                _arm = arm;
                SetStopLoss("VAB", CalculationMode.Price, arm.Stop, false);
                SetProfitTarget("VAB", CalculationMode.Price, arm.Target);
                if (arm.Direction == "long")
                    _entryOrder = EnterLongStopMarket(0, true, 1, arm.Entry, "VAB");
                else
                    _entryOrder = EnterShortStopMarket(0, true, 1, arm.Entry, "VAB");
            }
        }

        private void CancelEntry()
        {
            if (_entryOrder != null)
            {
                if (_entryOrder.OrderState == OrderState.Working || _entryOrder.OrderState == OrderState.Accepted)
                    CancelOrder(_entryOrder);
                _entryOrder = null;
            }
        }

        private void FlattenAll()
        {
            if (Position.MarketPosition == MarketPosition.Long) ExitLong();
            else if (Position.MarketPosition == MarketPosition.Short) ExitShort();
        }

        protected override void OnExecutionUpdate(Execution execution, string executionId, double price,
            int quantity, MarketPosition marketPosition, string orderId, DateTime time)
        {
            if (execution.Order == null) return;
            if (execution.Order.Name == "VAB" && execution.Order.OrderState == OrderState.Filled)
            {
                _pos = _arm; _pos.Entry = price;    // honest fill price for reference
                _inPos = true; _entries++;
                _recStop.Add(_arm.Stop); _recTarget.Add(_arm.Target);   // for R scoring (aligned to AllTrades)
                _traded.Add(Math.Round(_arm.Entry, 1).ToString("F1") + "|" + Math.Round(_arm.Stop, 1).ToString("F1"));
                _entryOrder = null;
            }
        }

        protected override void OnPositionUpdate(Position position, double averagePrice,
            int quantity, MarketPosition marketPosition)
        {
            if (marketPosition == MarketPosition.Flat) _inPos = false;   // stop/target/session closed us
        }

        private void TrimHead()
        {
            int drop = _c1.Count - 400;
            _o1.RemoveRange(0, drop); _h1.RemoveRange(0, drop); _l1.RemoveRange(0, drop);
            _c1.RemoveRange(0, drop); _v1.RemoveRange(0, drop); _st1.RemoveRange(0, drop);
        }

        // thresholds in CT (see file header). ET users: +1h on each boundary.
        private static string SessionOf(DateTime dt)
        {
            int m = dt.Hour * 60 + dt.Minute;
            if (m >= 18 * 60 || m < 3 * 60) return "Asia";
            if (m >= 3 * 60 && m < 8 * 60) return "London";
            if (m >= 8 * 60 && m < 17 * 60) return "NY";
            return null;
        }

        // ================= the strategy math (mirrors Vab / grade_lib.py) =================
        // List + (start, len) window instead of Span; reuses _bin scratch. Same numbers as Main.cs.
        private GResult Grade(List<double> o, List<double> h, List<double> l, List<double> c, List<double> v,
                              int s, int n)
        {
            double O = o[s], C = c[s + n - 1], H = h[s], L = l[s], travel = 0;
            for (int i = 0; i < n; i++) { if (h[s + i] > H) H = h[s + i]; if (l[s + i] < L) L = l[s + i]; }
            for (int i = 1; i < n; i++) { double d = c[s + i] - c[s + i - 1]; travel += d < 0 ? -d : d; }
            double rng = H - L; if (rng == 0) rng = 1e-9;
            if (travel == 0) travel = 1e-9;
            double net = C - O, rs = rng / NRows;

            for (int i = 0; i < NRows; i++) _bin[i] = 0;
            for (int p = 0; p < n; p++)
            {
                double bl = l[s + p], bh = h[s + p], vol = v[s + p];
                if (bh <= bl) { _bin[Clamp((int)((bl - L) / rs))] += vol; continue; }
                int loI = Clamp((int)((bl - L) / rs)), hiI = Clamp((int)((bh - L) / rs));
                double span = bh - bl;
                for (int bi = loI; bi <= hiI; bi++)
                {
                    double bBot = L + bi * rs, ov = Math.Min(bh, bBot + rs) - Math.Max(bl, bBot);
                    if (ov > 0) _bin[bi] += vol * (ov / span);
                }
            }
            double binSum = 0; for (int i = 0; i < NRows; i++) binSum += _bin[i];
            int pocI = 0, vaLo, vaHi;
            if (binSum <= 0) { vaLo = 0; vaHi = NRows - 1; }
            else
            {
                for (int i = 1; i < NRows; i++) if (_bin[i] > _bin[pocI]) pocI = i;
                ValueArea(pocI, 0.70, binSum, out vaLo, out vaHi);
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
            GResult g;
            g.State = state; g.Direction = direction; g.Strength = net / rng;
            g.Vah = L + (vaHi + 1) * rs; g.Val = L + vaLo * rs; g.Poc = L + (pocI + 0.5) * rs;
            return g;
        }

        private static int Clamp(int i) { return i < 0 ? 0 : (i >= NRows ? NRows - 1 : i); }

        private void ValueArea(int poc, double pct, double sum, out int lo, out int hi)
        {
            double target = sum * pct, acc = _bin[poc];
            lo = poc; hi = poc;
            while (acc < target && (lo > 0 || hi < NRows - 1))
            {
                double below = lo > 0 ? _bin[lo - 1] : -1.0, above = hi < NRows - 1 ? _bin[hi + 1] : -1.0;
                if (above >= below) { hi++; acc += _bin[hi]; } else { lo--; acc += _bin[lo]; }
            }
        }

        // window = _st1[start .. start+len) aligned to _o1..[start..]. Copies the state window so the
        // warm-up head can be nulled without touching the real buffer.
        private Cons FindConsolidation(int start, int len)
        {
            Cons none = default(Cons);
            if (len < StateWindow + MinLen) return none;
            List<string> st = _st1.GetRange(start, len);
            for (int i = 0; i < Math.Min(StateWindow, len); i++) st[i] = null;

            int bestA = -1, bestB = -1, i2 = 0;
            while (i2 < len)
            {
                int j = i2; while (j < len && st[j] == st[i2]) j++;
                if (st[i2] == "CONSOLIDATION" && j - i2 >= MinLen) { bestA = i2; bestB = j - 1; }
                i2 = j;
            }
            if (bestA < 0) return none;
            int endedAgo = len - 1 - bestB;
            if (endedAgo > MaxAge) return none;
            int clen = bestB - bestA + 1;
            GResult g = Grade(_o1, _h1, _l1, _c1, _v1, start + bestA, clen);
            if (g.Vah <= g.Val) return none;
            Cons cc;
            cc.Valid = true; cc.Vah = g.Vah; cc.Val = g.Val; cc.Poc = g.Poc; cc.Len = clen; cc.EndedAgo = endedAgo;
            return cc;
        }

        // arm for resting stops: fire when directional + a base exists AND price HASN'T broken yet,
        // so the parked stop fills ON the break (matches DecideArm in Main.cs).
        private Intent DecideArm(double strength, Cons cons, double price)
        {
            Intent none = default(Intent);
            if (!cons.Valid || cons.Vah <= cons.Val) return none;
            double risk = cons.Vah - cons.Val;
            if (strength >= BiasStr && price < cons.Vah)
            {
                Intent it; it.Valid = true; it.Direction = "long";
                it.Entry = cons.Vah; it.Stop = cons.Val; it.Target = cons.Vah + TargetR * risk; return it;
            }
            if (strength <= -BiasStr && price > cons.Val)
            {
                Intent it; it.Valid = true; it.Direction = "short";
                it.Entry = cons.Val; it.Stop = cons.Vah; it.Target = cons.Val - TargetR * risk; return it;
            }
            return none;
        }

        // ================= backtest progress + run capture (thin shim) =================
        // The strategy decides WHEN + supplies its data (trades, stops/targets, meta). All CSV/JSON
        // formatting and file I/O live in AddOns\Reporting\TradeExporter so any strategy can reuse it.
        private string InstName() { return Instrument != null ? Instrument.MasterInstrument.Name : "NA"; }

        // % complete (primary/1m bars are fully loaded in a backtest) + a periodic partial checkpoint save.
        private void ReportProgress()
        {
            int total = BarsArray[0].Count;
            if (total <= 1) return;
            int pct = (int)(100.0 * CurrentBars[0] / (total - 1));
            if (pct < _nextPct) return;

            int done = SystemPerformance != null && SystemPerformance.AllTrades != null
                ? SystemPerformance.AllTrades.Count : 0;
            Print(string.Format("VABreakout: {0,3}% complete | bar {1} | trades so far: {2}",
                _nextPct, Times[0][0].ToString("yyyy-MM-dd"), done));
            if (ExportTrades) TradeExporter.WriteCheckpoint(SystemPerformance, InstName(), _recStop, _recTarget, RepoDir);

            _nextPct += ProgressStep;
            while (_nextPct <= pct) _nextPct += ProgressStep; // don't re-fire if a bar jumped a whole step
        }

        // run_id = YYYY-MM-DD_nt_<fill>_NQ_<startYear>-<endYear>  (fill auto-detected from Tick Replay)
        private string RunId(string fill)
        {
            int y0 = _runStart == DateTime.MinValue ? _runEnd.Year : _runStart.Year;
            return string.Format("{0}_nt_{1}_{2}_{3}-{4}",
                DateTime.Now.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture), fill, InstName(), y0, _runEnd.Year);
        }

        // meta.json — the label that makes a run comparable (§4). Hand-built (no JSON dependency).
        private string BuildMeta(string runId, string fill)
        {
            CultureInfo ci = CultureInfo.InvariantCulture;
            string a = _runStart == DateTime.MinValue ? "" : _runStart.ToString("yyyy-MM-dd", ci);
            string b = _runEnd.ToString("yyyy-MM-dd", ci);
            StringBuilder m = new StringBuilder();
            m.AppendLine("{");
            m.AppendLine("  \"run_id\": \"" + runId + "\",");
            m.AppendLine("  \"created_utc\": \"" + DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ", ci) + "\",");
            m.AppendLine("  \"platform\": \"ninjatrader\",");
            m.AppendLine("  \"strategy\": \"VABreakout\",");
            m.AppendLine("  \"instrument\": \"" + InstName() + "\",");
            m.AppendLine("  \"bar_type\": \"Minute/1\",");
            m.AppendLine("  \"tick_replay\": " + (IsTickReplay ? "true" : "false") + ",");
            m.AppendLine("  \"fill_resolution\": \"" + fill + "\",");
            m.AppendLine("  \"commission_per_rt\": " + CommissionRt.ToString(ci) + ",");
            m.AppendLine("  \"slippage_ticks\": " + SlippageTicks.ToString(ci) + ",");
            m.AppendLine("  \"requested_range\": [\"" + a + "\", \"" + b + "\"],");
            m.AppendLine("  \"params\": {\"NRows\":24,\"StateWindow\":25,\"MinLen\":15,\"MaxAge\":40," +
                "\"DetWindow\":120,\"MinBars\":8,\"ECut\":0.38,\"ACut\":0.55,\"BiasStr\":0.3,\"TargetR\":2.0},");
            m.AppendLine("  \"sample_type\": \"" + J(SampleType) + "\",");
            m.AppendLine("  \"notes\": \"" + J(Notes) + "\"");
            m.Append("}");
            return m.ToString();
        }

        // minimal JSON string escaping for free-text meta fields
        private static string J(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", " ").Replace("\n", " ");
        }

        // final capture on State.Terminated — writes <repo>/backtests/runs/<run_id>/{trades.csv, meta.json}
        private void WriteTrades()
        {
            try
            {
                string fill = IsTickReplay ? "tick" : "bar";
                string runId = RunId(fill);
                int count;
                string dir = TradeExporter.WriteRun(SystemPerformance, InstName(), _recStop, _recTarget,
                    RepoDir, runId, BuildMeta(runId, fill), out count);
                if (count == 0) { Print("VABreakout: 0 trades — no run written."); return; }
                Print("VABreakout: wrote " + count + " trades + meta -> " + dir);
            }
            catch (Exception ex)
            {
                Print("VABreakout: trade export failed: " + ex.Message);
            }
        }
    }
}
