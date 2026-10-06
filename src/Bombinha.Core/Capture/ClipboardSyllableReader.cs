using Bombinha.Core.Common;
using Bombinha.Core.Logging;
using Bombinha.Core.Settings;
using Bombinha.Core.Typing;

namespace Bombinha.Core.Capture;

/// <summary>
/// Seleciona a sílaba com clique duplo/triplo e copia com Ctrl+C. O sucesso é confirmado pelo número
/// de sequência da área de transferência: se ele não mudou, nada foi copiado — assim o bot nunca
/// confunde "a cópia falhou" com "a sílaba repetiu" e não reaproveita texto velho.
/// O Ctrl+C só é enviado se o clique deu foco à janela do jogo: senão ele copiaria o que estivesse
/// selecionado em outro programa (e leria isso como "sílaba").
/// </summary>
public sealed class ClipboardSyllableReader(
    IInputDriver input, IClipboard clipboard, IClock clock, ITargetWindowGuard targetGuard, Logger log)
{
    private static readonly TimeSpan PollInterval = TimeSpan.FromMilliseconds(10);
    private static readonly TimeSpan ClickInterval = TimeSpan.FromMilliseconds(30);
    private static readonly TimeSpan HoverSettle = TimeSpan.FromMilliseconds(20);

    /// <summary>
    /// Quantos cliques dar em cada tentativa. O duplo seleciona a palavra sob o cursor, mas falha se
    /// errar o glifo por alguns pixels (a bomba treme); o triplo seleciona a linha e perdoa isso.
    /// </summary>
    public static IReadOnlyList<int> ClickSequence(ClickSelection mode, int attempts)
    {
        int[] pattern = mode switch
        {
            ClickSelection.DoubleClick => [2],
            ClickSelection.TripleClick => [3],
            _ => [2, 3],
        };
        int n = Math.Max(1, attempts);
        return Enumerable.Range(0, n).Select(i => pattern[i % pattern.Length]).ToArray();
    }

    public string Read(AppSettings s, CancellationToken ct)
    {
        uint initialSequence = clipboard.SequenceNumber;
        IClipboardSnapshot? snapshot = s.Capture.PreserveClipboard ? TrySnapshot() : null;
        var settle = Ms.Of(Math.Max(30, s.Timing.SettleAfterSelectMs));
        var point = s.Calibration.SyllablePoint;

        try
        {
            var sequence = ClickSequence(s.Capture.ClickSelection, s.Capture.Attempts);
            for (int i = 0; i < sequence.Count; i++)
            {
                int clicks = sequence[i];
                uint before = clipboard.SequenceNumber;

                input.MoveTo(point);
                clock.Sleep(HoverSettle, ct); // deixa o navegador registrar a posição antes do clique
                input.ClickAt(clock, point, clicks, ClickInterval, ct);
                clock.Sleep(settle, ct);

                var target = targetGuard.Check(point);
                if (!target.IsSafe)
                {
                    log.Warning($"Captura cancelada por segurança: {target.Reason}");
                    return "";
                }
                input.PressChord(VirtualKey.Control, VirtualKey.C);

                string? text = WaitForCopy(before, settle, ct);
                if (!string.IsNullOrEmpty(text))
                {
                    if (i > 0)
                        log.Info($"Captura recuperada na tentativa {i + 1} ({clicks} cliques).");
                    return text;
                }
                log.Info($"Nada selecionado com {clicks} cliques (tentativa {i + 1}).");
            }
            return "";
        }
        finally
        {
            // Só devolve se algo realmente foi escrito durante a captura.
            if (snapshot is not null && clipboard.SequenceNumber != initialSequence)
                TryRestore(snapshot);
        }
    }

    /// <summary>Espera o Ctrl+C chegar em vez de dormir um tempo fixo torcendo para dar certo.</summary>
    internal string? WaitForCopy(uint before, TimeSpan timeout, CancellationToken ct)
    {
        var deadline = clock.Elapsed + timeout;
        while (true)
        {
            if (clipboard.SequenceNumber != before)
            {
                string? text = clipboard.TryGetText();
                if (!string.IsNullOrEmpty(text))
                    return text;
            }
            if (clock.Elapsed >= deadline)
                return null;
            clock.Sleep(PollInterval, ct);
        }
    }

    private IClipboardSnapshot? TrySnapshot()
    {
        try
        {
            return clipboard.TakeSnapshot();
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            log.Warning("Não foi possível guardar o conteúdo da área de transferência; ele não será restaurado.", ex);
            return null;
        }
    }

    private void TryRestore(IClipboardSnapshot snapshot)
    {
        try
        {
            clipboard.Restore(snapshot);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            log.Warning("Falha ao restaurar a área de transferência.", ex);
        }
    }
}
