using Bombinha.Core.Logging;
using Bombinha.Core.Settings;

namespace Bombinha.Core.Capture;

/// <summary>Escolhe o método de leitura configurado, normaliza o resultado e acompanha falhas seguidas.</summary>
public sealed class SyllableCapture(ClipboardSyllableReader clipboard, OcrSyllableReader ocr, Logger log) : ISyllableSource
{
    private const int FailureWarningThreshold = 5;
    private int _consecutiveFailures;

    public string Capture(AppSettings settings, CancellationToken ct)
    {
        string? raw = settings.Capture.Method == SyllableCaptureMethod.Ocr ? ocr.Read(settings) : null;
        raw ??= clipboard.Read(settings, ct);

        string syllable = SyllableText.Normalize(raw);
        if (syllable.Length > SyllableText.MaxLength)
        {
            // Nunca registra o texto inteiro: pode ser conteúdo do usuário vindo de outra janela.
            log.Warning($"Texto capturado não parece uma sílaba ({syllable.Length} letras); ignorado.");
            syllable = "";
            raw = null;
        }
        if (syllable.Length > 0)
        {
            _consecutiveFailures = 0;
            return syllable;
        }

        _consecutiveFailures++;
        if (_consecutiveFailures == FailureWarningThreshold + 1 || _consecutiveFailures % 20 == 0)
            log.Warning($"{_consecutiveFailures} falhas seguidas ao capturar a sílaba. Verifique as posições, a janela do jogo e o zoom do navegador.");
        if (!string.IsNullOrWhiteSpace(raw))
            log.Debug($"Captura sem letras válidas: \"{Truncate(raw, 20)}\"");
        return "";
    }

    private static string Truncate(string text, int max) => text.Length <= max ? text : text[..max] + "…";
}
