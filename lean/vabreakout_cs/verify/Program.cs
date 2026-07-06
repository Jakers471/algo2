using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Json;

// ================= Vab: copied VERBATIM from lean/vabreakout_cs/Main.cs =================
public static class Vab
{
    public const int NRows = 24, StateWindow = 25, MinLen = 15, MaxAge = 40, DetWindow = 120, MinBars = 8;
    public const double ECut = 0.38, ACut = 0.55, BiasStr = 0.3, TargetR = 2.0;

    public struct GResult { public string State, Direction; public double Strength, Vah, Val, Poc; }
    public struct Cons { public bool Valid; public double Vah, Val, Poc; public int Len, EndedAgo; }
    public struct Intent { public bool Valid; public string Direction; public double Entry, Stop, Target; }

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

    public static Cons FindConsolidation(List<string> states, ReadOnlySpan<double> o, ReadOnlySpan<double> h,
                                         ReadOnlySpan<double> l, ReadOnlySpan<double> c, ReadOnlySpan<double> v)
    {
        int n = states.Count;
        if (n < StateWindow + MinLen) return default;
        for (int i = 0; i < Math.Min(StateWindow, n); i++) states[i] = null;
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
}

// ================= test harness: replicate main.py's per-bar state build + calls =================
public class Case { public double[] o { get; set; } public double[] h { get; set; } public double[] l { get; set; } public double[] c { get; set; } public double[] v { get; set; } }

public static class Program
{
    public static int Main()
    {
        string dir = AppContext.BaseDirectory;
        // walk up to the project dir (bin/Debug/netX -> project)
        string inPath = FindUp(dir, "input.json");
        var cases = JsonSerializer.Deserialize<List<Case>>(File.ReadAllText(inPath));
        var sb = new StringBuilder("[");
        for (int k = 0; k < cases.Count; k++)
        {
            var cc = cases[k];
            int n = cc.c.Length;
            // build 1m states like main.py: state[i] = Grade(bars[i-25:i+1]) once i>=25
            var st = new List<string>(n);
            for (int i = 0; i < n; i++)
            {
                if (i + 1 >= Vab.StateWindow + 1)
                {
                    int s = i + 1 - (Vab.StateWindow + 1), len = Vab.StateWindow + 1;
                    st.Add(Vab.Grade(cc.o.AsSpan(s, len), cc.h.AsSpan(s, len), cc.l.AsSpan(s, len),
                                     cc.c.AsSpan(s, len), cc.v.AsSpan(s, len)).State);
                }
                else st.Add(null);
            }
            int lo = Math.Max(0, n - Vab.DetWindow), cnt = n - lo;
            var cons = Vab.FindConsolidation(st.GetRange(lo, cnt),
                cc.o.AsSpan(lo, cnt), cc.h.AsSpan(lo, cnt), cc.l.AsSpan(lo, cnt), cc.c.AsSpan(lo, cnt), cc.v.AsSpan(lo, cnt));
            var g = Vab.Grade(cc.o.AsSpan(n - 60, 60), cc.h.AsSpan(n - 60, 60), cc.l.AsSpan(n - 60, 60),
                              cc.c.AsSpan(n - 60, 60), cc.v.AsSpan(n - 60, 60));
            if (k > 0) sb.Append(',');
            sb.Append("{\"cons\":");
            sb.Append(cons.Valid
                ? $"{{\"vah\":{R(cons.Vah)},\"val\":{R(cons.Val)},\"poc\":{R(cons.Poc)},\"len\":{cons.Len},\"ago\":{cons.EndedAgo}}}"
                : "null");
            sb.Append($",\"g60\":{{\"state\":\"{g.State}\",\"strength\":{R(g.Strength)},\"vah\":{R(g.Vah)},\"val\":{R(g.Val)}}}}}");
        }
        sb.Append(']');
        string outPath = Path.Combine(Path.GetDirectoryName(inPath), "output.json");
        File.WriteAllText(outPath, sb.ToString());
        Console.WriteLine($"wrote {cases.Count} results -> {outPath}");
        return 0;
    }

    static string R(double d) => d.ToString("R", System.Globalization.CultureInfo.InvariantCulture);
    static string FindUp(string start, string file)
    {
        var d = new DirectoryInfo(start);
        while (d != null) { var p = Path.Combine(d.FullName, file); if (File.Exists(p)) return p; d = d.Parent; }
        throw new FileNotFoundException(file);
    }
}
