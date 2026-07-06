//
// AddOns/Reporting/TradeExporter.cs — reusable backtest run capture (trades.csv + meta.json).
//
// Infrastructure, NOT strategy logic. Writes a run into  <repo>/backtests/runs/<run_id>/  per the
// project EXPORT CONTRACT: trades.csv (one row per round-trip, R-scored) + meta.json (the label).
// SystemPerformance.AllTrades carries no stop/target, so the strategy passes parallel stop/target
// lists (aligned to AllTrades order) and this computes R.
//
// Lives under Custom\AddOns\ (NinjaTrader only compiles beneath Custom\). Kept out of AddOns\quant\
// which is an excluded Python project.
//
#region Using declarations
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using NinjaTrader.Cbi;
#endregion

namespace NinjaTrader.NinjaScript.AddOns
{
    public static class TradeExporter
    {
        private static readonly CultureInfo CI = CultureInfo.InvariantCulture;

        // <repo>/backtests/runs/  (created on demand)
        public static string RunsDir(string repoDir)
        {
            string dir = Path.Combine(Path.Combine(repoDir, "backtests"), "runs");
            Directory.CreateDirectory(dir);
            return dir;
        }

        // One row per completed round-trip trade, with Stop/Target/R. stops/targets are parallel to
        // AllTrades (index i == trade i). count set (0 -> returns "").
        public static string BuildCsv(SystemPerformance perf, string inst,
                                      IList<double> stops, IList<double> targets, out int count)
        {
            TradeCollection trades = perf != null ? perf.AllTrades : null;
            count = trades != null ? trades.Count : 0;
            if (count == 0) return "";

            StringBuilder sb = new StringBuilder();
            sb.AppendLine("TradeNumber,Instrument,Direction,Quantity,EntryTime,EntryPrice,EntryName," +
                "ExitTime,ExitPrice,ExitName,ProfitPoints,ProfitTicks,ProfitCurrency,Commission," +
                "CumProfitCurrency,MaePoints,MfePoints,Stop,Target,R");
            double cum = 0;
            for (int i = 0; i < count; i++)
            {
                Trade t = trades[i];
                cum += t.ProfitCurrency;
                bool isLong = t.Entry.MarketPosition == MarketPosition.Long;
                double entry = t.Entry.Price, exit = t.Exit.Price;
                double stop   = (stops   != null && i < stops.Count)   ? stops[i]   : double.NaN;
                double target = (targets != null && i < targets.Count) ? targets[i] : double.NaN;
                double risk = double.IsNaN(stop) ? 0.0 : Math.Abs(entry - stop);
                double r = risk > 1e-9 ? (exit - entry) / risk * (isLong ? 1.0 : -1.0) : 0.0;

                sb.AppendLine(string.Join(",",
                    t.TradeNumber.ToString(CI), inst, isLong ? "Long" : "Short", t.Quantity.ToString(CI),
                    t.Entry.Time.ToString("yyyy-MM-dd HH:mm:ss", CI), entry.ToString(CI), Esc(t.Entry.Name),
                    t.Exit.Time.ToString("yyyy-MM-dd HH:mm:ss", CI), exit.ToString(CI), Esc(t.Exit.Name),
                    t.ProfitPoints.ToString(CI), t.ProfitTicks.ToString(CI), t.ProfitCurrency.ToString(CI),
                    t.Commission.ToString(CI), cum.ToString(CI), t.MaePoints.ToString(CI), t.MfePoints.ToString(CI),
                    double.IsNaN(stop) ? "" : stop.ToString(CI), double.IsNaN(target) ? "" : target.ToString(CI),
                    r.ToString("F4", CI)));
            }
            return sb.ToString();
        }

        // Partial checkpoint -> runs/_inprogress_nt/trades.csv (overwritten). Swallows all errors.
        public static void WriteCheckpoint(SystemPerformance perf, string inst,
                                           IList<double> stops, IList<double> targets, string repoDir)
        {
            try
            {
                int count; string csv = BuildCsv(perf, inst, stops, targets, out count);
                if (count == 0) return;
                string dir = Path.Combine(RunsDir(repoDir), "_inprogress_nt");
                Directory.CreateDirectory(dir);
                File.WriteAllText(Path.Combine(dir, "trades.csv"), csv);
            }
            catch { /* never let a checkpoint failure break the backtest */ }
        }

        // Final run -> runs/<runId>/{trades.csv, meta.json}. Drops the checkpoint. Returns folder (null if 0).
        public static string WriteRun(SystemPerformance perf, string inst, IList<double> stops, IList<double> targets,
                                      string repoDir, string runId, string metaJson, out int count)
        {
            string csv = BuildCsv(perf, inst, stops, targets, out count);
            if (count == 0) return null;

            string dir = Path.Combine(RunsDir(repoDir), runId);
            if (Directory.Exists(dir)) dir += "_" + DateTime.Now.ToString("HHmmssfff", CI); // collision-safe
            Directory.CreateDirectory(dir);
            File.WriteAllText(Path.Combine(dir, "trades.csv"), csv);
            File.WriteAllText(Path.Combine(dir, "meta.json"), metaJson);

            try { string cp = Path.Combine(RunsDir(repoDir), "_inprogress_nt");
                  if (Directory.Exists(cp)) Directory.Delete(cp, true); } catch { }
            return dir;
        }

        // minimal CSV field escaping (quote if it contains a comma or a quote)
        private static string Esc(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            return (s.IndexOf(',') >= 0 || s.IndexOf('"') >= 0)
                ? "\"" + s.Replace("\"", "\"\"") + "\"" : s;
        }
    }
}
