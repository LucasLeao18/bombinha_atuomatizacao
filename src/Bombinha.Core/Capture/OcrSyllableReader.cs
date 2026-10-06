using Bombinha.Core.Detection;
using Bombinha.Core.Imaging;
using Bombinha.Core.Logging;
using Bombinha.Core.Settings;

namespace Bombinha.Core.Capture;

/// <summary>Lê a sílaba direto da imagem: sem mouse, sem foco e sem área de transferência.</summary>
public sealed class OcrSyllableReader(IScreenCapture screen, IOcrEngine ocr, Logger log)
{
    private bool _warnedUnavailable;
    private bool _warnedNoRegion;
    private int _misses;

    /// <summary>
    /// Texto reconhecido, ou null quando o OCR não pode ser usado agora ou não reconheceu nada
    /// plausível — nesse caso o chamador usa clique + Ctrl+C neste ciclo, em vez de perder o turno.
    /// </summary>
    public string? Read(AppSettings s)
    {
        if (!ocr.IsAvailable)
        {
            if (!_warnedUnavailable)
            {
                log.Warning($"OCR indisponível ({ocr.UnavailableReason}); usando clique + Ctrl+C.");
                _warnedUnavailable = true;
            }
            return null;
        }

        if (s.Calibration.SyllableRegion is not { IsEmpty: false } region)
        {
            if (!_warnedNoRegion)
            {
                log.Warning("Região da sílaba não calibrada (Setup › Captura da sílaba); usando clique + Ctrl+C.");
                _warnedNoRegion = true;
            }
            return null;
        }
        _warnedNoRegion = false;

        try
        {
            var crop = screen.Capture(region);
            foreach (int scale in OcrPreprocessor.Scales)
            {
                string raw = ocr.Recognize(OcrPreprocessor.Prepare(crop, scale));
                int letters = SyllableText.Normalize(raw).Length;
                if (letters is > 0 and <= SyllableText.MaxLength)
                {
                    _misses = 0;
                    return raw;
                }
            }
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            log.Error("Falha no OCR; usando clique + Ctrl+C neste ciclo.", ex);
            return null;
        }

        _misses++;
        if (_misses == 1 || _misses % 20 == 0)
            log.Warning($"O OCR não reconheceu a sílaba ({_misses}x seguidas); usando clique + Ctrl+C neste ciclo. Confira a região da sílaba.");
        return null;
    }
}
