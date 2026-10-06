using System.Numerics;

namespace Bombinha.Core.Imaging;

/// <summary>Melhor posição do template na imagem; X/Y relativos à imagem pesquisada.</summary>
public readonly record struct TemplateMatch(double Score, int X, int Y)
{
    public static TemplateMatch None => new(0, -1, -1);
    public bool Found => X >= 0;
}

/// <summary>
/// Correlação cruzada normalizada com média zero (equivalente ao TM_CCOEFF_NORMED do OpenCV).
/// Usa imagens integrais para média/variância de cada janela, SIMD no produto interno e uma busca
/// grossa (metade da resolução) refinada em resolução cheia ao redor dos melhores candidatos.
/// </summary>
public sealed class TemplateMatcher
{
    private const int MinSizeForPyramid = 16;
    private const int CoarseCandidates = 3;
    private const int RefineRadius = 3;

    private readonly Level _full;
    private readonly Level? _coarse;

    public TemplateMatcher(GrayImage template)
    {
        _full = new Level(template);
        if (template.Width >= MinSizeForPyramid && template.Height >= MinSizeForPyramid)
            _coarse = new Level(template.Downscale2X());
    }

    public int Width => _full.Width;
    public int Height => _full.Height;

    /// <summary>Template de cor uniforme não tem como ser correlacionado.</summary>
    public bool IsDegenerate => _full.Norm <= 1e-6;

    public TemplateMatch FindBest(GrayImage image)
    {
        if (IsDegenerate || image.Width < Width || image.Height < Height)
            return TemplateMatch.None;

        var fullIntegral = new IntegralImage(image);
        if (_coarse is null || image.Width / 2 < _coarse.Width || image.Height / 2 < _coarse.Height || _coarse.Norm <= 1e-6)
            return Exhaustive(_full, image, fullIntegral);

        var small = image.Downscale2X();
        var coarseMap = ScoreMap(_coarse, small, new IntegralImage(small), out int mapW, out int mapH);

        var best = TemplateMatch.None;
        foreach (var (cx, cy) in TopPeaks(coarseMap, mapW, mapH, CoarseCandidates))
        {
            int x0 = Math.Max(0, (2 * cx) - RefineRadius), x1 = Math.Min(image.Width - Width, (2 * cx) + RefineRadius);
            int y0 = Math.Max(0, (2 * cy) - RefineRadius), y1 = Math.Min(image.Height - Height, (2 * cy) + RefineRadius);
            for (int y = y0; y <= y1; y++)
            {
                for (int x = x0; x <= x1; x++)
                {
                    double s = _full.ScoreAt(image, fullIntegral, x, y);
                    if (s > best.Score || !best.Found)
                        best = new TemplateMatch(s, x, y);
                }
            }
        }
        return best;
    }

    /// <summary>Pontuação numa posição específica (diagnóstico e testes).</summary>
    public double ScoreAt(GrayImage image, int x, int y) => _full.ScoreAt(image, new IntegralImage(image), x, y);

    private static TemplateMatch Exhaustive(Level level, GrayImage image, IntegralImage integral)
    {
        var best = TemplateMatch.None;
        for (int y = 0; y <= image.Height - level.Height; y++)
        {
            for (int x = 0; x <= image.Width - level.Width; x++)
            {
                double s = level.ScoreAt(image, integral, x, y);
                if (s > best.Score || !best.Found)
                    best = new TemplateMatch(s, x, y);
            }
        }
        return best;
    }

    private static float[] ScoreMap(Level level, GrayImage image, IntegralImage integral, out int mapW, out int mapH)
    {
        mapW = image.Width - level.Width + 1;
        mapH = image.Height - level.Height + 1;
        var map = new float[mapW * mapH];
        for (int y = 0; y < mapH; y++)
        {
            for (int x = 0; x < mapW; x++)
                map[(y * mapW) + x] = (float)level.ScoreAt(image, integral, x, y);
        }
        return map;
    }

    /// <summary>Melhores picos com supressão de vizinhos, para não refinar o mesmo lugar várias vezes.</summary>
    private static List<(int X, int Y)> TopPeaks(float[] map, int w, int h, int count)
    {
        var peaks = new List<(int, int)>(count);
        for (int k = 0; k < count; k++)
        {
            int bestIndex = -1;
            float bestValue = float.NegativeInfinity;
            for (int i = 0; i < map.Length; i++)
            {
                if (map[i] > bestValue)
                {
                    bestValue = map[i];
                    bestIndex = i;
                }
            }
            if (bestIndex < 0 || float.IsNegativeInfinity(bestValue))
                break;

            int px = bestIndex % w, py = bestIndex / w;
            peaks.Add((px, py));
            for (int y = Math.Max(0, py - RefineRadius); y <= Math.Min(h - 1, py + RefineRadius); y++)
            {
                for (int x = Math.Max(0, px - RefineRadius); x <= Math.Min(w - 1, px + RefineRadius); x++)
                    map[(y * w) + x] = float.NegativeInfinity;
            }
        }
        return peaks;
    }

    private sealed class Level
    {
        private readonly float[] _centered;

        public Level(GrayImage template)
        {
            Width = template.Width;
            Height = template.Height;
            float mean = template.Mean();
            _centered = new float[template.Pixels.Length];
            double sq = 0;
            for (int i = 0; i < _centered.Length; i++)
            {
                _centered[i] = template.Pixels[i] - mean;
                sq += _centered[i] * _centered[i];
            }
            Norm = Math.Sqrt(sq);
        }

        public int Width { get; }
        public int Height { get; }
        public double Norm { get; }

        public double ScoreAt(GrayImage image, IntegralImage integral, int x, int y)
        {
            int n = Width * Height;
            double sum = integral.Sum(x, y, Width, Height);
            double sumSq = integral.SumOfSquares(x, y, Width, Height);
            double variance = sumSq - (sum * sum / n);
            if (variance <= 1e-6 * n)
                return 0; // janela uniforme: correlação indefinida

            double numerator = 0;
            for (int j = 0; j < Height; j++)
            {
                var templateRow = _centered.AsSpan(j * Width, Width);
                var imageRow = image.Pixels.AsSpan(((y + j) * image.Width) + x, Width);
                numerator += Dot(templateRow, imageRow);
            }
            return Math.Clamp(numerator / (Norm * Math.Sqrt(variance)), -1.0, 1.0);
        }
    }

    private static float Dot(ReadOnlySpan<float> a, ReadOnlySpan<float> b)
    {
        int i = 0;
        float sum = 0;
        if (Vector.IsHardwareAccelerated && a.Length >= Vector<float>.Count)
        {
            var acc = Vector<float>.Zero;
            for (; i <= a.Length - Vector<float>.Count; i += Vector<float>.Count)
                acc += new Vector<float>(a[i..]) * new Vector<float>(b[i..]);
            sum = Vector.Sum(acc);
        }
        for (; i < a.Length; i++)
            sum += a[i] * b[i];
        return sum;
    }

    private sealed class IntegralImage
    {
        private readonly double[] _sum;
        private readonly double[] _sumSq;
        private readonly int _stride;

        public IntegralImage(GrayImage image)
        {
            _stride = image.Width + 1;
            _sum = new double[_stride * (image.Height + 1)];
            _sumSq = new double[_sum.Length];
            for (int y = 0; y < image.Height; y++)
            {
                double row = 0, rowSq = 0;
                for (int x = 0; x < image.Width; x++)
                {
                    double v = image.Pixels[(y * image.Width) + x];
                    row += v;
                    rowSq += v * v;
                    int idx = ((y + 1) * _stride) + x + 1;
                    _sum[idx] = _sum[idx - _stride] + row;
                    _sumSq[idx] = _sumSq[idx - _stride] + rowSq;
                }
            }
        }

        public double Sum(int x, int y, int w, int h) => Rect(_sum, x, y, w, h);
        public double SumOfSquares(int x, int y, int w, int h) => Rect(_sumSq, x, y, w, h);

        private double Rect(double[] t, int x, int y, int w, int h) =>
            t[((y + h) * _stride) + x + w] - t[(y * _stride) + x + w] - t[((y + h) * _stride) + x] + t[(y * _stride) + x];
    }
}
