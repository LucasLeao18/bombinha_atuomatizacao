namespace Bombinha.Core.Imaging;

/// <summary>Imagem em tons de cinza (0..255) em ponto flutuante, pronta para cálculos.</summary>
public sealed class GrayImage
{
    public GrayImage(int width, int height, float[] pixels)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(width);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(height);
        if (pixels.Length != width * height)
            throw new ArgumentException("Tamanho do buffer não confere.", nameof(pixels));
        Width = width;
        Height = height;
        Pixels = pixels;
    }

    public int Width { get; }
    public int Height { get; }
    public float[] Pixels { get; }

    public float this[int x, int y] => Pixels[(y * Width) + x];

    public ReadOnlySpan<float> Row(int y) => Pixels.AsSpan(y * Width, Width);

    /// <summary>Luminância BT.601 (mesmos pesos do OpenCV), ignorando o canal alfa.</summary>
    public static GrayImage FromBgra(PixelBuffer image)
    {
        var px = new float[image.Width * image.Height];
        var d = image.Data;
        for (int i = 0, j = 0; i < px.Length; i++, j += 4)
            px[i] = (0.114f * d[j]) + (0.587f * d[j + 1]) + (0.299f * d[j + 2]);
        return new GrayImage(image.Width, image.Height, px);
    }

    /// <summary>Reduz à metade com média 2x2 (base da busca grossa).</summary>
    public GrayImage Downscale2X()
    {
        int w = Width / 2, h = Height / 2;
        var px = new float[w * h];
        for (int y = 0; y < h; y++)
        {
            int r0 = 2 * y * Width, r1 = r0 + Width;
            for (int x = 0; x < w; x++)
            {
                int c = 2 * x;
                px[(y * w) + x] = (Pixels[r0 + c] + Pixels[r0 + c + 1] + Pixels[r1 + c] + Pixels[r1 + c + 1]) * 0.25f;
            }
        }
        return new GrayImage(w, h, px);
    }

    /// <summary>Amplia por interpolação bilinear (melhora o OCR de textos pequenos).</summary>
    public GrayImage UpscaleBilinear(int factor)
    {
        int w = Width * factor, h = Height * factor;
        var px = new float[w * h];
        for (int y = 0; y < h; y++)
        {
            float sy = Math.Clamp(((y + 0.5f) / factor) - 0.5f, 0, Height - 1);
            int y0 = (int)sy, y1 = Math.Min(y0 + 1, Height - 1);
            float fy = sy - y0;
            for (int x = 0; x < w; x++)
            {
                float sx = Math.Clamp(((x + 0.5f) / factor) - 0.5f, 0, Width - 1);
                int x0 = (int)sx, x1 = Math.Min(x0 + 1, Width - 1);
                float fx = sx - x0;
                float top = this[x0, y0] + ((this[x1, y0] - this[x0, y0]) * fx);
                float bottom = this[x0, y1] + ((this[x1, y1] - this[x0, y1]) * fx);
                px[(y * w) + x] = top + ((bottom - top) * fy);
            }
        }
        return new GrayImage(w, h, px);
    }

    public float Mean()
    {
        double sum = 0;
        foreach (float p in Pixels)
            sum += p;
        return (float)(sum / Pixels.Length);
    }
}
