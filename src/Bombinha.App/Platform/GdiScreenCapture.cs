using System.Runtime.InteropServices;
using Bombinha.Core.Common;
using Bombinha.Core.Detection;
using Bombinha.Core.Imaging;

namespace Bombinha.App.Platform;

/// <summary>
/// Copia regiões da tela com GDI (BitBlt). Lê só o retângulo pedido — a versão antiga capturava a
/// tela inteira várias vezes por segundo. Coordenadas em pixels físicos (o app é PerMonitorV2).
/// </summary>
internal sealed class GdiScreenCapture : IScreenCapture
{
    public PixelBuffer Capture(ScreenRect rect)
    {
        if (rect.IsEmpty)
            throw new ArgumentException("Retângulo vazio.", nameof(rect));

        nint screenDc = Native.GetDC(0);
        if (screenDc == 0)
            throw new ScreenCaptureException("Não foi possível acessar a tela (GetDC).");
        nint memDc = 0, bitmap = 0, previous = 0;
        try
        {
            memDc = Native.CreateCompatibleDC(screenDc);
            var info = new Native.BITMAPINFO
            {
                bmiHeader = new Native.BITMAPINFOHEADER
                {
                    biSize = (uint)Marshal.SizeOf<Native.BITMAPINFOHEADER>(),
                    biWidth = rect.Width,
                    biHeight = -rect.Height, // de cima para baixo
                    biPlanes = 1,
                    biBitCount = 32,
                },
            };
            bitmap = Native.CreateDIBSection(memDc, ref info, Native.DIB_RGB_COLORS, out nint bits, 0, 0);
            if (memDc == 0 || bitmap == 0)
                throw new ScreenCaptureException($"Falha ao alocar a captura de {rect.Width}x{rect.Height} (erro {Marshal.GetLastWin32Error()}).");

            previous = Native.SelectObject(memDc, bitmap);
            if (!Native.BitBlt(memDc, 0, 0, rect.Width, rect.Height, screenDc, rect.X, rect.Y, Native.SRCCOPY))
                throw new ScreenCaptureException($"Falha ao ler a tela (erro {Marshal.GetLastWin32Error()}). A tela pode estar bloqueada ou numa janela segura (UAC).");

            var data = new byte[rect.Width * rect.Height * 4];
            Marshal.Copy(bits, data, 0, data.Length);
            for (int i = 3; i < data.Length; i += 4)
                data[i] = 255;
            return new PixelBuffer(rect.Width, rect.Height, data);
        }
        finally
        {
            if (previous != 0)
                Native.SelectObject(memDc, previous);
            if (bitmap != 0)
                Native.DeleteObject(bitmap);
            if (memDc != 0)
                Native.DeleteDC(memDc);
            _ = Native.ReleaseDC(0, screenDc);
        }
    }

    public ScreenRect MonitorBoundsAt(ScreenPoint point)
    {
        nint monitor = Native.MonitorFromPoint(new Native.POINT { X = point.X, Y = point.Y }, Native.MONITOR_DEFAULTTONEAREST);
        var info = new Native.MONITORINFO { cbSize = (uint)Marshal.SizeOf<Native.MONITORINFO>() };
        if (monitor == 0 || !Native.GetMonitorInfo(monitor, ref info))
            return VirtualDesktop();
        var r = info.rcMonitor;
        return new ScreenRect(r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top);
    }

    public static ScreenRect VirtualDesktop() => new(
        Native.GetSystemMetrics(Native.SM_XVIRTUALSCREEN),
        Native.GetSystemMetrics(Native.SM_YVIRTUALSCREEN),
        Native.GetSystemMetrics(Native.SM_CXVIRTUALSCREEN),
        Native.GetSystemMetrics(Native.SM_CYVIRTUALSCREEN));

    /// <summary>Escala do Windows (1.0 = 100%) do monitor que contém o ponto.</summary>
    public static double ScaleAt(ScreenPoint point)
    {
        nint monitor = Native.MonitorFromPoint(new Native.POINT { X = point.X, Y = point.Y }, Native.MONITOR_DEFAULTTONEAREST);
        return Native.GetDpiForMonitor(monitor, Native.MDT_EFFECTIVE_DPI, out uint dpi, out _) == 0 ? dpi / 96.0 : 1.0;
    }
}
