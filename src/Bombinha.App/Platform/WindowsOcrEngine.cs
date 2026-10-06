using System.Runtime.InteropServices;
using System.Runtime.InteropServices.WindowsRuntime;
using Bombinha.Core.Capture;
using Bombinha.Core.Imaging;
using Windows.Globalization;
using Windows.Graphics.Imaging;
using Windows.Media.Ocr;

namespace Bombinha.App.Platform;

/// <summary>
/// OCR nativo do Windows 10/11 (Windows.Media.Ocr): roda no processo, sem instalar Tesseract e
/// sem criar um subprocesso por leitura como o pytesseract fazia.
/// </summary>
internal sealed class WindowsOcrEngine : IOcrEngine
{
    private readonly OcrEngine? _engine;

    public WindowsOcrEngine()
    {
        try
        {
            _engine = OcrEngine.TryCreateFromUserProfileLanguages()
                      ?? OcrEngine.TryCreateFromLanguage(new Language("pt-BR"))
                      ?? OcrEngine.TryCreateFromLanguage(new Language("en-US"));
            UnavailableReason = _engine is null
                ? "nenhum pacote de idioma com OCR instalado (Configurações › Hora e idioma › Idioma)"
                : null;
        }
        catch (Exception ex) when (ex is COMException or UnauthorizedAccessException or TypeLoadException)
        {
            UnavailableReason = $"OCR do Windows indisponível: {ex.Message}";
        }
    }

    public bool IsAvailable => _engine is not null;

    public string? UnavailableReason { get; }

    public string Language => _engine?.RecognizerLanguage.DisplayName ?? "—";

    public string Recognize(OcrImage image)
    {
        var engine = _engine ?? throw new InvalidOperationException(UnavailableReason);
        using var gray = SoftwareBitmap.CreateCopyFromBuffer(image.Pixels.AsBuffer(), BitmapPixelFormat.Gray8, image.Width, image.Height);
        using var bgra = SoftwareBitmap.Convert(gray, BitmapPixelFormat.Bgra8);
        var result = engine.RecognizeAsync(bgra).AsTask().GetAwaiter().GetResult();
        return result.Text ?? "";
    }
}
