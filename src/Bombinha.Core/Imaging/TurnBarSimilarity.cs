using Bombinha.Core.Settings;

namespace Bombinha.Core.Imaging;

/// <summary>Quão parecida a barra de turno está da referência tirada no início do turno (0..1).</summary>
public static class TurnBarSimilarity
{
    private const int HueBins = 30;
    private const int SaturationBins = 32;

    public static double Compute(PixelBuffer reference, PixelBuffer current, TurnBarMethod method)
    {
        if (current.Width != reference.Width || current.Height != reference.Height)
            current = current.ResizeNearest(reference.Width, reference.Height);

        return method switch
        {
            TurnBarMethod.Pixel => Pixel(reference, current),
            TurnBarMethod.Color => Color(reference, current),
            _ => (Pixel(reference, current) + Color(reference, current)) / 2.0,
        };
    }

    /// <summary>1 − diferença média absoluta em tons de cinza (sensível a qualquer mudança).</summary>
    public static double Pixel(PixelBuffer a, PixelBuffer b)
    {
        var ga = GrayImage.FromBgra(a).Pixels;
        var gb = GrayImage.FromBgra(b).Pixels;
        double diff = 0;
        for (int i = 0; i < ga.Length; i++)
            diff += Math.Abs(ga[i] - gb[i]);
        return Math.Clamp(1.0 - (diff / ga.Length / 255.0), 0.0, 1.0);
    }

    /// <summary>Correlação de histogramas H×S: tolera a barra encolher, acusa troca de cor/jogador.</summary>
    public static double Color(PixelBuffer a, PixelBuffer b)
    {
        var ha = HueSaturationHistogram(a);
        var hb = HueSaturationHistogram(b);
        double ma = ha.Average(), mb = hb.Average();
        double num = 0, da = 0, db = 0;
        for (int i = 0; i < ha.Length; i++)
        {
            double x = ha[i] - ma, y = hb[i] - mb;
            num += x * y;
            da += x * x;
            db += y * y;
        }
        if (da <= 0 || db <= 0)
            return ha.AsSpan().SequenceEqual(hb) ? 1.0 : 0.0;
        return Math.Clamp(num / Math.Sqrt(da * db), 0.0, 1.0);
    }

    /// <summary>Histograma 2D com a mesma convenção do OpenCV para HSV de 8 bits (H em 0..180).</summary>
    internal static double[] HueSaturationHistogram(PixelBuffer image)
    {
        var hist = new double[HueBins * SaturationBins];
        var d = image.Data;
        for (int i = 0; i < d.Length; i += 4)
        {
            int bl = d[i], g = d[i + 1], r = d[i + 2];
            int max = Math.Max(r, Math.Max(g, bl));
            int min = Math.Min(r, Math.Min(g, bl));
            int delta = max - min;
            double s = max == 0 ? 0 : 255.0 * delta / max;
            double h = 0;
            if (delta > 0)
            {
                if (max == r)
                    h = 60.0 * (g - bl) / delta;
                else if (max == g)
                    h = 120.0 + (60.0 * (bl - r) / delta);
                else
                    h = 240.0 + (60.0 * (r - g) / delta);
                if (h < 0)
                    h += 360.0;
            }
            int hBin = Math.Min(HueBins - 1, (int)(h / 2.0 * HueBins / 180.0));
            int sBin = Math.Min(SaturationBins - 1, (int)(s * SaturationBins / 256.0));
            hist[(hBin * SaturationBins) + sBin]++;
        }
        return hist;
    }
}
