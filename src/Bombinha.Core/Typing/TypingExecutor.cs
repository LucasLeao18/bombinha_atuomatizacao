using Bombinha.Core.Common;
using Bombinha.Core.Logging;

namespace Bombinha.Core.Typing;

public enum PlanOutcome
{
    Completed,
    /// <summary>Na hora do ENTER já não era a vez do jogador: nada foi enviado.</summary>
    TurnLost,
    /// <summary>O foco não está no jogo (ex.: outra janela por cima do campo): nada foi digitado.</summary>
    UnsafeTarget,
}

/// <summary>Confere, imediatamente antes do ENTER, se ainda é a vez do jogador.</summary>
public interface ISubmitGuard
{
    bool ConfirmTurnForSubmit(CancellationToken ct);
}

public readonly record struct TargetCheck(bool IsSafe, string? Reason)
{
    public static TargetCheck Safe => new(true, null);
    public static TargetCheck Unsafe(string reason) => new(false, reason);
}

/// <summary>Garante que as teclas vão para o jogo e não para outra janela.</summary>
public interface ITargetWindowGuard
{
    TargetCheck Check(ScreenPoint chatPoint);
}

/// <summary>Executa roteiros de digitação, verificando cancelamento antes de cada passo.</summary>
public sealed class TypingExecutor(
    IInputDriver input,
    IClock clock,
    ISubmitGuard submitGuard,
    ITargetWindowGuard targetGuard,
    Logger log)
{
    private static readonly TimeSpan ClickInterval = TimeSpan.FromMilliseconds(30);

    public PlanOutcome Execute(TypingPlan plan, ScreenPoint chatPoint, bool testMode, CancellationToken ct)
    {
        if (testMode)
        {
            string action = plan.Submits ? "enviaria" : "digitaria e apagaria";
            log.Info($"[TESTE] {plan.Label}: {action} → {plan.VisibleText()}");
            return PlanOutcome.Completed;
        }

        foreach (var step in plan.Steps)
        {
            ct.ThrowIfCancellationRequested();
            switch (step)
            {
                case TypingStep.Focus:
                    if (!Focus(chatPoint, ct))
                        return PlanOutcome.UnsafeTarget;
                    break;
                case TypingStep.TypeText t:
                    input.TypeText(t.Text);
                    break;
                case TypingStep.Backspace:
                    input.PressKey(VirtualKey.Backspace);
                    break;
                case TypingStep.Wait w:
                    clock.Sleep(w.Duration, ct);
                    break;
                case TypingStep.ClearField:
                    if (!Focus(chatPoint, ct))
                        return PlanOutcome.UnsafeTarget;
                    input.PressChord(VirtualKey.Control, VirtualKey.A);
                    clock.Sleep(TimeSpan.FromMilliseconds(30), ct);
                    input.PressKey(VirtualKey.Backspace);
                    clock.Sleep(TimeSpan.FromMilliseconds(20), ct);
                    break;
                case TypingStep.Submit:
                    if (!submitGuard.ConfirmTurnForSubmit(ct))
                    {
                        log.Warning("Envio cancelado: não era mais a sua vez no momento do ENTER.");
                        return PlanOutcome.TurnLost;
                    }
                    input.PressKey(VirtualKey.Enter);
                    break;
                default:
                    throw new InvalidOperationException($"Passo de digitação desconhecido: {step}");
            }
        }
        return PlanOutcome.Completed;
    }

    private bool Focus(ScreenPoint chatPoint, CancellationToken ct)
    {
        input.ClickAt(clock, chatPoint, 1, ClickInterval, ct);
        var check = targetGuard.Check(chatPoint);
        if (check.IsSafe)
            return true;
        log.Warning($"Digitação bloqueada por segurança: {check.Reason}");
        return false;
    }
}
