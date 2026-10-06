namespace Bombinha.Core.Imaging;

/// <summary>Imagem BGRA 32 bits, linhas contíguas (stride = largura × 4).</summary>
public sealed class PixelBuffer
{
    public PixelBuffer(int width, int height, byte[] bgra)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(width);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(height);
        if (bgra.Length != width * height * 4)
            throw new ArgumentException($"Esperados {width * height * 4} bytes, recebidos {bgra.Length}.", nameof(bgra));
        Width = width;
        Height = height;
        Data = bgra;
    }

    public int Width { get; }
    public int Height { get; }

    /// <summary>B, G, R, A por pixel.</summary>
    public byte[] Data { get; }

    internal static PixelBuffer Solid(int width, int height, byte r, byte g, byte b)
    {
        var data = new byte[width * height * 4];
        for (int i = 0; i < data.Length; i += 4)
        {
            data[i] = b;
            data[i + 1] = g;
            data[i + 2] = r;
            data[i + 3] = 255;
        }
        return new PixelBuffer(width, height, data);
    }

    /// <summary>Redimensiona por vizinho mais próximo (só para alinhar tamanhos em comparações).</summary>
    public PixelBuffer ResizeNearest(int width, int height)
    {
        if (width == Width && height == Height)
            return this;
        var data = new byte[width * height * 4];
        for (int y = 0; y < height; y++)
        {
            int sy = y * Height / height;
            for (int x = 0; x < width; x++)
            {
                int sx = x * Width / width;
                Buffer.BlockCopy(Data, ((sy * Width) + sx) * 4, data, ((y * width) + x) * 4, 4);
            }
        }
        return new PixelBuffer(width, height, data);
    }
}
