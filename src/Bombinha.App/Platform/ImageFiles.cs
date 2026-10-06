using System.IO;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Bombinha.Core.Imaging;

namespace Bombinha.App.Platform;

/// <summary>Leitura e gravação de PNG usando o codec do próprio Windows (WIC).</summary>
internal static class ImageFiles
{
    /// <exception cref="IOException">Arquivo inexistente ou imagem inválida.</exception>
    public static PixelBuffer Load(Stream stream)
    {
        try
        {
            var decoder = BitmapDecoder.Create(stream, BitmapCreateOptions.PreservePixelFormat, BitmapCacheOption.OnLoad);
            var frame = new FormatConvertedBitmap(decoder.Frames[0], PixelFormats.Bgra32, null, 0);
            int w = frame.PixelWidth, h = frame.PixelHeight;
            var data = new byte[w * h * 4];
            frame.CopyPixels(data, w * 4, 0);
            return new PixelBuffer(w, h, data);
        }
        catch (Exception ex) when (ex is NotSupportedException or FileFormatException or ArgumentException)
        {
            throw new IOException($"Imagem inválida: {ex.Message}", ex);
        }
    }

    public static PixelBuffer Load(string path)
    {
        using var stream = File.OpenRead(path);
        return Load(stream);
    }

    public static void SavePng(PixelBuffer image, string path)
    {
        var source = BitmapSource.Create(image.Width, image.Height, 96, 96, PixelFormats.Bgra32, null, image.Data, image.Width * 4);
        var encoder = new PngBitmapEncoder();
        encoder.Frames.Add(BitmapFrame.Create(source));
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        string temp = path + ".tmp";
        using (var stream = File.Create(temp))
            encoder.Save(stream);
        File.Move(temp, path, overwrite: true);
    }
}
