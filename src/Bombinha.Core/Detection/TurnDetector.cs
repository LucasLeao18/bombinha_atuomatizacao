using Bombinha.Core.Common;
using Bombinha.Core.Imaging;
using Bombinha.Core.Logging;
using Bombinha.Core.Settings;

namespace Bombinha.Core.Detection;

public readonly record struct ChatboxProbe(bool Visible, double Score, ScreenPoint? Location, ScreenRect SearchArea);

/// <summary>
/// Detecta a vez do jogador procurando o campo de digitação (template) numa faixa ao redor da posição
/// calibrada — e não na tela inteira, o que era lento e podia achar o template em outra janela —
/// e, opcionalmente, comparando a barra de turno com a referência do início do turno.
/// </summary>
public sealed class TurnDetector(IScreenCapture screen, Logger log) : ITurnDetector
{
    // volatile: a interface pode trocar o template ou zerar a referência com o motor rodando.
    private volatile TemplateMatcher? _matcher;
    private volatile PixelBuffer? _barReference;
    private bool _warnedMissingBar;

    /// <exception cref="ArgumentException">Template de cor uniforme (não serve para localizar nada).</exception>
    public void SetTemplate(PixelBuffer template)
    {
        var matcher = new TemplateMatcher(GrayImage.FromBgra(template));
        if (matcher.IsDegenerate)
            throw new ArgumentException("O template do campo de digitação é uma imagem de cor uniforme.", nameof(template));
        _matcher = matcher;
    }

    public ScreenRect SearchArea(AppSettings settings)
    {
        var chat = settings.Calibration.ChatPoint;
        var monitor = screen.MonitorBoundsAt(chat);
        int margin = Math.Max(settings.Detection.SearchMarginY, (_matcher?.Height ?? 0) + 4);
        var band = new ScreenRect(monitor.X, chat.Y - margin, monitor.Width, 2 * margin).Intersect(monitor);
        return band.IsEmpty ? monitor : band;
    }

    public ChatboxProbe ProbeChatbox(AppSettings settings)
    {
        var matcher = _matcher ?? throw new InvalidOperationException("Template do campo de digitação não carregado.");
        var area = SearchArea(settings);
        var image = GrayImage.FromBgra(screen.Capture(area));
        var match = matcher.FindBest(image);
        if (!match.Found)
            return new ChatboxProbe(false, 0, null, area);
        return new ChatboxProbe(match.Score >= settings.Detection.TemplateThreshold, match.Score,
            new ScreenPoint(area.X + match.X, area.Y + match.Y), area);
    }

    public bool DetectTurn(AppSettings settings)
    {
        if (ProbeChatbox(settings).Visible)
        {
            if (settings.Detection.UseTurnBar && CaptureTurnBar(settings.Calibration) is { } bar)
            {
                _barReference = bar;
                _warnedMissingBar = false;
            }
            return true;
        }
        ResetReference();
        return false;
    }

    public bool IsStillMyTurn(AppSettings settings)
    {
        if (!ProbeChatbox(settings).Visible)
            return false;
        if (!settings.Detection.UseTurnBar)
            return true;
        var current = CaptureTurnBar(settings.Calibration);
        if (current is null || _barReference is null)
            return false;
        return TurnBarSimilarity.Compute(_barReference, current, settings.Detection.TurnBarMethod)
               >= settings.Detection.TurnBarThreshold;
    }

    public bool ConfirmForSubmit(AppSettings settings)
    {
        if (!ProbeChatbox(settings).Visible)
        {
            log.Info("Recheque antes do ENTER: o campo de digitação não está mais visível.");
            return false;
        }
        if (!settings.Detection.UseTurnBar)
            return true;

        var current = CaptureTurnBar(settings.Calibration);
        if (current is null)
        {
            if (!_warnedMissingBar)
            {
                log.Warning("Retângulo da barra de turno não configurado; envio cancelado. Calibre-o no Setup ou desative a barra de turno.");
                _warnedMissingBar = true;
            }
            return false;
        }
        if (_barReference is null)
        {
            _barReference = current;
            return true;
        }

        double score = TurnBarSimilarity.Compute(_barReference, current, settings.Detection.TurnBarMethod);
        if (score >= settings.Detection.TurnBarThreshold)
        {
            _barReference = current;
            return true;
        }
        log.Info($"Envio cancelado: similaridade da barra {score:F3} abaixo do limite {settings.Detection.TurnBarThreshold:F3}.");
        return false;
    }

    public void ResetReference()
    {
        _barReference = null;
        _warnedMissingBar = false;
    }

    public PixelBuffer? CaptureTurnBar(Calibration calibration) =>
        calibration.TurnBar.IsEmpty ? null : screen.Capture(calibration.TurnBar);
}
