using Bombinha.Core.Common;
using Bombinha.Core.Imaging;

namespace Bombinha.Core.Detection;

public interface IScreenCapture
{
    /// <summary>Copia um retângulo da área de trabalho virtual (pixels físicos).</summary>
    /// <exception cref="ScreenCaptureException">A tela não pôde ser lida (ex.: tela bloqueada/UAC).</exception>
    PixelBuffer Capture(ScreenRect rect);

    /// <summary>Limites do monitor que contém o ponto (ou o mais próximo dele).</summary>
    ScreenRect MonitorBoundsAt(ScreenPoint point);
}

public sealed class ScreenCaptureException : Exception
{
    public ScreenCaptureException() { }
    public ScreenCaptureException(string message) : base(message) { }
    public ScreenCaptureException(string message, Exception inner) : base(message, inner) { }
}
