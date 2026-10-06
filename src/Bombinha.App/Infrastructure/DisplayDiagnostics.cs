using Bombinha.App.Platform;
using Bombinha.Core.Common;
using Bombinha.Core.Settings;

namespace Bombinha.App.Infrastructure;

internal enum DiagnosticSeverity
{
    Ok,
    Warning,
    Problem,
}

internal sealed record DiagnosticReport(DiagnosticSeverity Severity, string Text);

/// <summary>Confere se as posições calibradas ainda fazem sentido para a tela atual.</summary>
internal static class DisplayDiagnostics
{
    public static DiagnosticReport Run(AppSettings settings)
    {
        var desktop = GdiScreenCapture.VirtualDesktop();
        var cal = settings.Calibration;
        var lines = new List<string>
        {
            $"Área de trabalho: {desktop.Width}x{desktop.Height} pixels físicos (o app usa sempre pixels reais, em qualquer escala).",
        };
        var severity = DiagnosticSeverity.Ok;

        double scale = GdiScreenCapture.ScaleAt(cal.ChatPoint);
        lines.Add($"Escala do monitor do jogo: {scale * 100:F0}%.");

        foreach (var (name, point) in new[] { ("Área das letras", cal.SyllablePoint), ("Campo de digitação", cal.ChatPoint) })
        {
            if (!Contains(desktop, point))
            {
                lines.Add($"{name} {point} está fora da tela — recalibre.");
                severity = DiagnosticSeverity.Problem;
            }
        }
        if (settings.Detection.UseTurnBar && !Contains(desktop, new ScreenPoint(cal.TurnBar.X, cal.TurnBar.Y)))
        {
            lines.Add("A barra de turno está fora da tela — recalibre.");
            severity = DiagnosticSeverity.Problem;
        }

        if (cal.CalibratedDesktop is { } calibrated && calibrated != new ScreenSize(desktop.Width, desktop.Height))
        {
            lines.Add($"As posições foram calibradas com a tela em {calibrated}; agora ela tem {desktop.Width}x{desktop.Height}. Recalibre.");
            severity = severity == DiagnosticSeverity.Problem ? severity : DiagnosticSeverity.Warning;
        }
        else if (cal.CalibratedDesktop is null)
        {
            lines.Add("Posições ainda não calibradas nesta versão (valores padrão ou importados).");
            severity = severity == DiagnosticSeverity.Problem ? severity : DiagnosticSeverity.Warning;
        }

        return new DiagnosticReport(severity, string.Join(Environment.NewLine, lines));
    }

    private static bool Contains(ScreenRect r, ScreenPoint p) => p.X >= r.X && p.Y >= r.Y && p.X < r.Right && p.Y < r.Bottom;
}
