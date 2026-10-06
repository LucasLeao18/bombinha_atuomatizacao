using Bombinha.Core.Common;
using Bombinha.Core.Settings;
using Bombinha.Core.Words;

namespace Bombinha.Core.Engine;

public enum EngineStatus
{
    Stopped,
    Loading,
    WaitingForTurn,
    ReadingSyllable,
    Playing,
    Verifying,
    Faulted,
}

public enum LiveEventKind
{
    Syllable,
    Word,
    Event,
}

/// <summary>Atualização do painel "Rodada atual".</summary>
public sealed record LiveEvent(LiveEventKind Kind, string Text);

public readonly record struct HistoryItem(string Word, int Uses);

/// <summary>Retrato imutável do estado do motor para a interface.</summary>
public sealed record EngineSnapshot(
    EngineStatus Status,
    int Accepted,
    int Rejected,
    int DeliberateFailures,
    int Streak,
    int Matches,
    int NumbersRemaining,
    int AlphabetsCompleted,
    IReadOnlySet<char> LettersUsed,
    int DictionaryCount,
    int LearnedRejected,
    IReadOnlyList<HistoryItem> History)
{
    /// <summary>Percentual de palavras aceitas; null antes da primeira verificação.</summary>
    public double? AcceptanceRate => Accepted + Rejected == 0 ? null : 100.0 * Accepted / (Accepted + Rejected);
}

public sealed record WordLoadSummary(int Words, int Blacklisted, int Rejected, string Source);

/// <summary>Origem das listas de palavras e persistência das recusas aprendidas.</summary>
public interface IWordRepository
{
    /// <exception cref="IOException">Dicionário inexistente ou ilegível.</exception>
    /// <exception cref="InvalidDataException">Dicionário vazio.</exception>
    WordLoadSummary LoadInto(WordList list, AppSettings settings);

    /// <exception cref="IOException">Falha ao gravar.</exception>
    void PersistRejected(string word);
}

/// <summary>Cronometra o turno: o orçamento de tempo desconta o que já passou desde que a vez virou sua.</summary>
public sealed class TurnClock(IClock clock)
{
    private TimeSpan _turnStart;
    private TimeSpan _lastTurnAt = clock.Elapsed;

    public bool InTurn { get; private set; }

    /// <summary>Registra o estado atual; o cronômetro só reinicia na virada "não é minha vez" → "é minha vez".</summary>
    public void Mark(bool myTurn)
    {
        if (myTurn && !InTurn)
        {
            _turnStart = clock.Elapsed;
            _lastTurnAt = _turnStart;
        }
        InTurn = myTurn;
    }

    public TimeSpan ElapsedInTurn => InTurn ? clock.Elapsed - _turnStart : TimeSpan.Zero;

    public TimeSpan Remaining(double limitSeconds)
    {
        var left = TimeSpan.FromSeconds(limitSeconds) - ElapsedInTurn;
        return left > TimeSpan.Zero ? left : TimeSpan.Zero;
    }

    /// <summary>0 = sem tempo, 1 = turno recém-começado.</summary>
    public double Slack(double limitSeconds) =>
        Math.Clamp(Remaining(limitSeconds).TotalSeconds / Math.Max(0.1, limitSeconds), 0.0, 1.0);

    public TimeSpan SinceLastTurn => clock.Elapsed - _lastTurnAt;

    public void ResetIdle() => _lastTurnAt = clock.Elapsed;
}

public static class GameModeText
{
    public static string DisplayName(this GameMode mode) => mode switch
    {
        GameMode.LongWords => "palavras longas",
        GameMode.ShortWords => "palavras curtas",
        GameMode.Alphabet => "alfabeto",
        _ => "qualquer palavra",
    };

    /// <summary>Próximo modo na ordem usada pelo atalho F7.</summary>
    public static GameMode Next(this GameMode mode) => mode switch
    {
        GameMode.LongWords => GameMode.ShortWords,
        GameMode.ShortWords => GameMode.Any,
        GameMode.Any => GameMode.Alphabet,
        _ => GameMode.LongWords,
    };
}
