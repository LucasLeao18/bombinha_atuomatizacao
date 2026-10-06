namespace Bombinha.Core.Imaging;

/// <summary>Imagem em tons de cinza de 8 bits, texto escuro sobre fundo claro, pronta para o OCR.</summary>
public sealed record OcrImage(int Width, int Height, byte[] Pixels);

/// <summary>
/// Prepara o recorte da sílaba para o OCR do Windows. Medido contra o motor real:
/// <list type="bullet">
/// <item>tons de cinza funcionam bem melhor que binarizar (o antisserrilhado ajuda);</item>
/// <item>texto encostado na borda não é reconhecido, então há uma margem clara;</item>
/// <item>palavras curtas dependem da escala, então o leitor tenta várias (<see cref="Scales"/>).</item>
/// </list>
/// </summary>
public static class OcrPreprocessor
{
    public const int Margin = 40;

    /// <summary>Escalas tentadas em ordem até uma leitura plausível.</summary>
    public static IReadOnlyList<int> Scales { get; } = [2, 3, 4, 1];

    public static OcrImage Prepare(PixelBuffer crop, int scale)
    {
        var gray = GrayImage.FromBgra(crop);
        if (scale > 1)
            gray = gray.UpscaleBilinear(scale);

        // O fundo domina a área: se ele é escuro, o texto é claro e precisa ser invertido.
        bool invert = gray.Mean() < 127;
        int w = gray.Width + (2 * Margin), h = gray.Height + (2 * Margin);
        var pixels = new byte[w * h];
        Array.Fill(pixels, (byte)255);
        for (int y = 0; y < gray.Height; y++)
        {
            int row = ((y + Margin) * w) + Margin;
            for (int x = 0; x < gray.Width; x++)
            {
                int v = Math.Clamp((int)MathF.Round(gray.Pixels[(y * gray.Width) + x]), 0, 255);
                pixels[row + x] = (byte)(invert ? 255 - v : v);
            }
        }
        return new OcrImage(w, h, pixels);
    }
}
