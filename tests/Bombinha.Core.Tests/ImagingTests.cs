using System.Diagnostics;
using Bombinha.Core.Imaging;
using Bombinha.Core.Settings;
using Xunit.Abstractions;

namespace Bombinha.Core.Tests;

public class TemplateMatcherTests(ITestOutputHelper output)
{
    private static GrayImage Noise(int w, int h, int seed)
    {
        var rng = new Random(seed);
        var px = new float[w * h];
        for (int i = 0; i < px.Length; i++)
            px[i] = rng.Next(256);
        return new GrayImage(w, h, px);
    }

    private static GrayImage Crop(GrayImage img, int x, int y, int w, int h)
    {
        var px = new float[w * h];
        for (int j = 0; j < h; j++)
            img.Pixels.AsSpan(((y + j) * img.Width) + x, w).CopyTo(px.AsSpan(j * w, w));
        return new GrayImage(w, h, px);
    }

    /// <summary>Formas grandes e suaves, como a borda arredondada do campo de digitação.</summary>
    private static GrayImage Smooth(int w, int h, int seed)
    {
        var rng = new Random(seed);
        var blobs = Enumerable.Range(0, Math.Max(40, w * h / 500)).Select(_ => (X: rng.Next(w), Y: rng.Next(h), R: rng.Next(8, 30), V: rng.Next(40, 220))).ToArray();
        var px = new float[w * h];
        for (int y = 0; y < h; y++)
        {
            for (int x = 0; x < w; x++)
            {
                float v = 30;
                foreach (var b in blobs)
                {
                    if (((x - b.X) * (x - b.X)) + ((y - b.Y) * (y - b.Y)) < b.R * b.R)
                        v = b.V;
                }
                px[(y * w) + x] = v;
            }
        }
        return new GrayImage(w, h, px);
    }

    [Theory]
    [InlineData(137, 41)]
    [InlineData(0, 0)]
    [InlineData(244, 48)]
    public void Encontra_o_template_na_posicao_exata(int x, int y)
    {
        var image = Smooth(300, 120, 1);
        var matcher = new TemplateMatcher(Crop(image, x, y, 56, 72));
        var match = matcher.FindBest(image);
        Assert.Equal((x, y), (match.X, match.Y));
        Assert.True(match.Score > 0.999, $"score {match.Score}");
    }

    [Fact]
    public void Busca_grossa_nao_perde_padroes_de_alta_frequencia()
    {
        var image = Noise(200, 100, 3);
        var match = new TemplateMatcher(Crop(image, 77, 13, 40, 40)).FindBest(image);
        Assert.Equal((77, 13), (match.X, match.Y));
    }

    [Fact]
    public void Correlacao_normalizada_tolera_brilho_e_contraste()
    {
        var image = Smooth(300, 120, 2);
        var template = Crop(image, 100, 30, 56, 72);
        var brighter = new GrayImage(image.Width, image.Height, image.Pixels.Select(p => (p * 0.7f) + 40).ToArray());
        var match = new TemplateMatcher(template).FindBest(brighter);
        Assert.Equal((100, 30), (match.X, match.Y));
        Assert.True(match.Score > 0.99);
    }

    [Fact]
    public void Imagem_sem_o_template_fica_abaixo_do_limite()
    {
        var template = Crop(Smooth(300, 120, 4), 50, 20, 56, 72);
        var match = new TemplateMatcher(template).FindBest(Noise(300, 120, 5));
        Assert.True(match.Score < 0.5, $"score {match.Score}");
    }

    [Fact]
    public void Template_uniforme_e_degenerado()
    {
        var flat = new GrayImage(20, 20, Enumerable.Repeat(128f, 400).ToArray());
        var matcher = new TemplateMatcher(flat);
        Assert.True(matcher.IsDegenerate);
        Assert.False(matcher.FindBest(Noise(50, 50, 1)).Found);
    }

    [Fact]
    public void Imagem_menor_que_o_template_nao_encontra()
    {
        var matcher = new TemplateMatcher(Noise(56, 72, 1));
        Assert.False(matcher.FindBest(Noise(40, 40, 2)).Found);
    }

    [Fact]
    public void Busca_numa_faixa_full_hd_e_rapida()
    {
        var band = Smooth(1920, 300, 6);
        var matcher = new TemplateMatcher(Crop(band, 1500, 200, 56, 72));
        matcher.FindBest(band); // aquecimento (JIT)
        var sw = Stopwatch.StartNew();
        var match = matcher.FindBest(band);
        sw.Stop();
        output.WriteLine($"Faixa 1920x300: {sw.ElapsedMilliseconds} ms");
        Assert.Equal((1500, 200), (match.X, match.Y));
        Assert.True(sw.ElapsedMilliseconds < 1000, $"{sw.ElapsedMilliseconds} ms");
    }
}

public class TurnBarSimilarityTests
{
    private static PixelBuffer Bar(int filled, byte r, byte g, byte b)
    {
        var img = PixelBuffer.Solid(100, 10, 20, 20, 20);
        for (int y = 0; y < 10; y++)
        {
            for (int x = 0; x < filled; x++)
            {
                int i = ((y * 100) + x) * 4;
                img.Data[i] = b;
                img.Data[i + 1] = g;
                img.Data[i + 2] = r;
            }
        }
        return img;
    }

    [Theory]
    [InlineData(TurnBarMethod.Pixel)]
    [InlineData(TurnBarMethod.Color)]
    [InlineData(TurnBarMethod.Hybrid)]
    public void Imagens_iguais_tem_similaridade_maxima(TurnBarMethod method) =>
        Assert.Equal(1.0, TurnBarSimilarity.Compute(Bar(60, 200, 50, 50), Bar(60, 200, 50, 50), method), 6);

    [Fact]
    public void Pixel_preto_contra_branco_e_zero() =>
        Assert.Equal(0.0, TurnBarSimilarity.Pixel(PixelBuffer.Solid(10, 10, 0, 0, 0), PixelBuffer.Solid(10, 10, 255, 255, 255)), 6);

    [Fact]
    public void Cor_tolera_a_barra_encolher_mas_acusa_troca_de_cor()
    {
        var reference = Bar(80, 200, 50, 50);
        double shrunk = TurnBarSimilarity.Color(reference, Bar(70, 200, 50, 50));
        double otherColor = TurnBarSimilarity.Color(reference, Bar(80, 50, 50, 200));
        Assert.True(shrunk > 0.9, $"encolhida {shrunk}");
        Assert.True(otherColor < shrunk, $"outra cor {otherColor}");
    }

    [Fact]
    public void Tamanhos_diferentes_sao_alinhados()
    {
        var a = PixelBuffer.Solid(100, 10, 90, 90, 90);
        var b = PixelBuffer.Solid(50, 5, 90, 90, 90);
        Assert.Equal(1.0, TurnBarSimilarity.Compute(a, b, TurnBarMethod.Pixel), 6);
    }
}

public class OcrPreprocessorTests
{
    private static PixelBuffer LightTextOnDark()
    {
        var crop = PixelBuffer.Solid(10, 10, 10, 10, 10);
        for (int i = 0; i < 4 * 30; i += 4)
        {
            crop.Data[i] = 250;
            crop.Data[i + 1] = 250;
            crop.Data[i + 2] = 250;
        }
        return crop;
    }

    [Theory]
    [InlineData(1)]
    [InlineData(3)]
    public void Texto_claro_em_fundo_escuro_vira_texto_escuro_em_fundo_claro_com_margem(int scale)
    {
        var img = OcrPreprocessor.Prepare(LightTextOnDark(), scale);
        int m = OcrPreprocessor.Margin;
        Assert.Equal((10 * scale) + (2 * m), img.Width);
        Assert.Equal((10 * scale) + (2 * m), img.Height);
        Assert.Equal(255, img.Pixels[0]);                       // margem clara
        Assert.True(img.Pixels[(m * img.Width) + m] < 20);     // "texto" escuro
        Assert.True(img.Pixels[((m + (9 * scale)) * img.Width) + m] > 230); // fundo claro
    }

    [Fact]
    public void Texto_escuro_em_fundo_claro_nao_e_invertido()
    {
        var crop = PixelBuffer.Solid(10, 10, 240, 240, 240);
        crop.Data[0] = crop.Data[1] = crop.Data[2] = 5;
        var img = OcrPreprocessor.Prepare(crop, 1);
        int m = OcrPreprocessor.Margin;
        Assert.True(img.Pixels[(m * img.Width) + m] < 20);
    }

    [Fact]
    public void Escalas_tentadas_comecam_pelas_que_funcionam_melhor() =>
        Assert.Equal([2, 3, 4, 1], OcrPreprocessor.Scales);
}
