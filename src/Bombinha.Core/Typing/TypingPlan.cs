using System.Text;

namespace Bombinha.Core.Typing;

/// <summary>Um passo de um roteiro de digitação.</summary>
public abstract record TypingStep
{
    private TypingStep() { }

    /// <summary>Clica no campo de digitação do jogo.</summary>
    public sealed record Focus : TypingStep;

    public sealed record TypeText(string Text) : TypingStep;

    public sealed record Backspace : TypingStep;

    public sealed record Wait(TimeSpan Duration) : TypingStep;

    /// <summary>Foca o campo e apaga tudo (Ctrl+A, Backspace).</summary>
    public sealed record ClearField : TypingStep;

    /// <summary>ENTER, só se ainda for a vez do jogador.</summary>
    public sealed record Submit : TypingStep;
}

/// <summary>Roteiro determinístico: o sorteio da humanização já aconteceu ao montá-lo.</summary>
public sealed record TypingPlan(string Label, IReadOnlyList<TypingStep> Steps)
{
    // Custos médios fora das esperas explícitas (mesma ordem de grandeza do modelo antigo).
    public static readonly TimeSpan KeyCost = TimeSpan.FromMilliseconds(1.5);
    public static readonly TimeSpan FocusCost = TimeSpan.FromMilliseconds(10);
    public static readonly TimeSpan ClearFieldCost = TimeSpan.FromMilliseconds(80);
    public static readonly TimeSpan SubmitCost = TimeSpan.FromMilliseconds(60);

    /// <summary>Texto que fica no campo no momento do ENTER (null se o roteiro não envia).</summary>
    public string? SubmittedText => Submits ? VisibleText() : null;

    public bool Submits => Steps.Any(s => s is TypingStep.Submit);

    public TimeSpan EstimatedDuration
    {
        get
        {
            var total = TimeSpan.Zero;
            foreach (var step in Steps)
            {
                total += step switch
                {
                    TypingStep.Wait w => w.Duration,
                    TypingStep.TypeText t => KeyCost * t.Text.Length,
                    TypingStep.Backspace => KeyCost,
                    TypingStep.Focus => FocusCost,
                    TypingStep.ClearField => ClearFieldCost,
                    TypingStep.Submit => SubmitCost,
                    _ => TimeSpan.Zero,
                };
            }
            return total;
        }
    }

    /// <summary>Simula o campo de texto até o ENTER ou até ele ser apagado.</summary>
    public string VisibleText()
    {
        var sb = new StringBuilder();
        foreach (var step in Steps)
        {
            switch (step)
            {
                case TypingStep.TypeText t:
                    sb.Append(t.Text);
                    break;
                case TypingStep.Backspace when sb.Length > 0:
                    sb.Length--;
                    break;
                case TypingStep.ClearField:
                case TypingStep.Submit:
                    return sb.ToString();
            }
        }
        return sb.ToString();
    }
}

public enum RoundStyle
{
    /// <summary>Frase/ensaio opcionais e a palavra.</summary>
    Normal,
    /// <summary>Envia uma palavra errada de propósito.</summary>
    DeliberateFailure,
    /// <summary>Envia com uma letra errada e depois a palavra correta.</summary>
    WrongThenCorrect,
    /// <summary>Sem encenação (tempo apertado ou nova tentativa).</summary>
    Quick,
}

/// <summary>Sequência de roteiros executada numa jogada.</summary>
public sealed record RoundScript(RoundStyle Style, IReadOnlyList<TypingPlan> Plans, IReadOnlyList<string> Flags)
{
    public TimeSpan EstimatedDuration => Plans.Aggregate(TimeSpan.Zero, (acc, p) => acc + p.EstimatedDuration);
}

public readonly record struct RoundTriggers(bool JokePhrase, bool Rehearsal, bool DeliberateFailure, bool WrongEnter)
{
    public static RoundTriggers None => default;
}
