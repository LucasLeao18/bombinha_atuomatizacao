using Bombinha.Core.Common;
using Bombinha.Core.Settings;
using Bombinha.Core.Typing;

namespace Bombinha.Core.Detection;

/// <summary>
/// Antes do ENTER, tira o mouse de cima da barra de turno (o hover muda a aparência dela),
/// confere a vez e devolve o cursor para onde estava.
/// </summary>
public sealed class TurnGuard(ITurnDetector detector, IInputDriver input, IClock clock, AppSettings settings) : ISubmitGuard
{
    private static readonly TimeSpan SettleAfterMove = TimeSpan.FromMilliseconds(40);

    public bool ConfirmTurnForSubmit(CancellationToken ct)
    {
        var original = input.GetCursorPosition();
        try
        {
            input.MoveTo(settings.Calibration.SyllablePoint);
            clock.Sleep(SettleAfterMove, ct);
            return detector.ConfirmForSubmit(settings);
        }
        finally
        {
            input.MoveTo(original);
        }
    }
}
