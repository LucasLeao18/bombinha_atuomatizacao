using Bombinha.Core.Capture;
using Bombinha.Core.Common;
using Bombinha.Core.Detection;
using Bombinha.Core.Logging;
using Bombinha.Core.Settings;
using Bombinha.Core.Typing;
using Bombinha.Core.Words;

namespace Bombinha.Core.Engine;

public sealed record EngineServices(
    ITurnDetector Detector,
    ISyllableSource Syllables,
    IInputDriver Input,
    ITargetWindowGuard TargetGuard,
    IClock Clock,
    Random Random,
    WordList Words,
    IWordRepository WordRepository,
    Func<AppSettings> Settings,
    Logger Log);

/// <summary>
/// Loop principal do bot: detecta a vez, lê a sílaba, escolhe a palavra, digita e confere se o jogo aceitou.
/// Roda numa thread dedicada; todas as esperas são canceláveis, então Parar/F8 interrompe na hora,
/// inclusive no meio da digitação. Estado compartilhado com a UI é protegido por um único lock.
/// </summary>
public sealed class BotEngine : IDisposable
{
    private const int MaxConsecutiveErrors = 5;

    private readonly EngineServices _s;
    private readonly Logger _log;
    private readonly WordSelector _selector;
    private readonly TypingPlanner _planner;
    private readonly TurnClock _turnClock;
    private readonly Lock _gate = new();

    private readonly List<string> _history = [];
    private readonly Dictionary<string, int> _strikes = new(StringComparer.Ordinal);
    private int _accepted, _rejected, _deliberateFailures, _streak, _matches, _numbersRemaining;

    private Thread? _thread;
    private CancellationTokenSource? _cts;
    private volatile EngineStatus _status = EngineStatus.Stopped;

    public BotEngine(EngineServices services)
    {
        _s = services;
        _log = services.Log;
        _selector = new WordSelector(services.Random);
        _planner = new TypingPlanner(services.Random);
        _turnClock = new TurnClock(services.Clock);
    }

    /// <summary>Disparado na thread do motor.</summary>
    public event Action<EngineStatus>? StatusChanged;

    /// <summary>Disparado na thread do motor.</summary>
    public event Action<LiveEvent>? Live;

    /// <summary>Estatísticas/estado mudaram (thread de origem variável).</summary>
    public event Action? StateChanged;

    public EngineStatus Status => _status;

    public bool IsRunning => _thread is { IsAlive: true };

    public bool Start()
    {
        lock (_gate)
        {
            if (IsRunning)
                return false;
            InitializeSession(_s.Settings());
            _cts?.Dispose();
            _cts = new CancellationTokenSource();
            var token = _cts.Token;
            _thread = new Thread(() => Run(token)) { IsBackground = true, Name = "Bombinha.Engine" };
            _thread.Start();
            return true;
        }
    }

    /// <summary>Estado que vale por execução (chamado sob o lock).</summary>
    internal void InitializeSession(AppSettings settings) =>
        _numbersRemaining = settings.Humanization.InsertNumbers ? settings.Humanization.NumberRounds : 0;

    public void Stop()
    {
        lock (_gate)
            _cts?.Cancel();
    }

    /// <summary>Espera a thread terminar (usado ao fechar o app).</summary>
    public bool WaitForExit(TimeSpan timeout) => _thread?.Join(timeout) ?? true;

    public void NewMatch(string reason)
    {
        lock (_gate)
        {
            _selector.NewMatch();
            _strikes.Clear();
            _matches++;
        }
        _log.Info($"Nova partida ({reason}): palavras usadas e alfabeto zerados.");
        StateChanged?.Invoke();
    }

    public EngineSnapshot GetSnapshot()
    {
        lock (_gate)
        {
            var history = _history.Select(w => new HistoryItem(w, _selector.FrequencyOf(w))).ToArray();
            return new EngineSnapshot(_status, _accepted, _rejected, _deliberateFailures, _streak, _matches,
                _numbersRemaining, _selector.AlphabetsCompleted, new HashSet<char>(_selector.LettersUsed),
                _s.Words.Count, _s.Words.RejectedCount, history);
        }
    }

    public void Dispose()
    {
        Stop();
        WaitForExit(TimeSpan.FromSeconds(2));
        _cts?.Dispose();
    }

    // ---------------------------------------------------------------- loop

    private void Run(CancellationToken ct)
    {
        try
        {
            SetStatus(EngineStatus.Loading);
            var settings = _s.Settings();
            _log.Info($"Iniciando no modo: {settings.Mode.DisplayName()}", LogTag.Accent);
            if (_s.Words.Count == 0 && !TryLoadWords(settings))
            {
                SetStatus(EngineStatus.Faulted);
                return;
            }

            int consecutiveErrors = 0;
            while (!ct.IsCancellationRequested)
            {
                settings = _s.Settings();
                try
                {
                    RunCycle(settings, ct);
                    consecutiveErrors = 0;
                }
                catch (OperationCanceledException) when (ct.IsCancellationRequested)
                {
                    break;
                }
                catch (Exception ex)
                {
                    consecutiveErrors++;
                    _log.Error($"Erro no ciclo ({consecutiveErrors}/{MaxConsecutiveErrors}): {ex.Message}", ex);
                    if (consecutiveErrors >= MaxConsecutiveErrors)
                    {
                        _log.Critical("Muitos erros seguidos; automação interrompida. Veja o log para detalhes.");
                        SetStatus(EngineStatus.Faulted);
                        return;
                    }
                }
                _s.Clock.Sleep(Ms.Of(settings.Timing.CycleDelayMs), ct);
            }
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            // Parada solicitada.
        }
        catch (Exception ex)
        {
            _log.Critical("Falha inesperada no motor do bot.", ex);
            SetStatus(EngineStatus.Faulted);
            return;
        }

        _log.Info("Automação parada.");
        SetStatus(EngineStatus.Stopped);
    }

    private bool TryLoadWords(AppSettings settings)
    {
        try
        {
            var summary = _s.WordRepository.LoadInto(_s.Words, settings);
            _log.Success($"Dicionário carregado ({summary.Words} palavras, {summary.Source}). " +
                         $"Blacklist: {summary.Blacklisted} | Recusadas pelo jogo: {summary.Rejected}");
            StateChanged?.Invoke();
            return true;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException)
        {
            _log.Error($"Não foi possível carregar o dicionário: {ex.Message}", ex);
            return false;
        }
    }

    internal void RunCycle(AppSettings s, CancellationToken ct)
    {
        SetStatus(EngineStatus.WaitingForTurn);
        bool myTurn = _s.Detector.DetectTurn(s);
        lock (_gate)
            _turnClock.Mark(myTurn);

        if (!myTurn)
        {
            CheckInactivity(s);
            return;
        }

        SetStatus(EngineStatus.ReadingSyllable);
        string syllable = _s.Syllables.Capture(s, ct);
        if (syllable.Length == 0)
        {
            _log.Info("Captura vazia; tentando novamente.");
            return;
        }

        _log.Info($"Letras detectadas: {syllable.ToUpperInvariant()}", LogTag.Accent);
        Live?.Invoke(new LiveEvent(LiveEventKind.Syllable, syllable.ToUpperInvariant()));
        Live?.Invoke(new LiveEvent(LiveEventKind.Event, "analisando dicionário…"));
        PlayRound(syllable, s, ct);
    }

    // ---------------------------------------------------------------- rodada

    internal enum WordOutcome
    {
        Accepted,
        Rejected,
        Cancelled,
        /// <summary>Envio errado de propósito (ou com dígitos inseridos): não conta contra a palavra.</summary>
        NotCounted,
    }

    /// <summary>Tenta palavras até uma ser aceita pelo jogo (ou acabarem as tentativas).</summary>
    internal void PlayRound(string syllable, AppSettings s, CancellationToken ct)
    {
        var excluded = new HashSet<string>(StringComparer.Ordinal);
        int attempts = Math.Max(1, s.Verification.MaxAttemptsPerRound);

        for (int attempt = 1; attempt <= attempts; attempt++)
        {
            ct.ThrowIfCancellationRequested();

            HashSet<string> blocked;
            lock (_gate)
                blocked = new HashSet<string>(_selector.BlockedWords(s.Selection), StringComparer.Ordinal);
            blocked.UnionWith(excluded);

            var candidates = _s.Words.Filter(syllable, blocked);
            if (candidates.Count == 0)
            {
                if (attempt == 1)
                    SendGiveUpPhrase(s, ct);
                else
                    _log.Info($"Sem mais candidatas para '{syllable}' nesta rodada.");
                return;
            }

            string? choice;
            List<RankedWord> ranked;
            lock (_gate)
            {
                ranked = _selector.Rank(candidates, s.Mode, syllable, _turnClock.Slack(s.Timing.RoundTimeLimitSeconds), s.Selection);
                choice = _selector.Choose(ranked, s.Selection);
            }
            if (choice is null)
                return;

            if (attempt == 1 && s.Selection.ShowTopInConsole)
            {
                string top = string.Join(", ", ranked.Take(s.Selection.TopN).Select(r => r.Word));
                _log.Info($"Top opções ({candidates.Count} candidatas): {top}");
            }
            string suffix = attempt > 1 ? $"  (tentativa {attempt}/{attempts})" : "";
            _log.Success($"Escolhida: {choice}{suffix}");
            Live?.Invoke(new LiveEvent(LiveEventKind.Word, choice));

            switch (SendWord(choice, syllable, hurried: attempt > 1, s, ct))
            {
                case WordOutcome.Accepted:
                case WordOutcome.Cancelled:
                    return;
                case WordOutcome.NotCounted:
                    continue;
                case WordOutcome.Rejected:
                    excluded.Add(choice);
                    RegisterRejection(choice, s);
                    break;
            }
        }
        _log.Warning($"{attempts} tentativas sem sucesso para '{syllable}'.");
    }

    private void SendGiveUpPhrase(AppSettings s, CancellationToken ct)
    {
        Live?.Invoke(new LiveEvent(LiveEventKind.Word, "—"));
        Live?.Invoke(new LiveEvent(LiveEventKind.Event, "sem candidatas no dicionário"));
        string phrase = s.General.GiveUpPhrase;
        if (phrase.Length == 0)
        {
            _log.Warning("Nenhuma palavra encontrada (frase de desistência desativada).");
            return;
        }
        _log.Warning("Nenhuma palavra encontrada – enviando a frase de desistência.");
        SetStatus(EngineStatus.Playing);
        if (CreateExecutor(s).Execute(TypingPlanner.Quick(phrase), s.Calibration.ChatPoint, s.General.TestMode, ct) != PlanOutcome.Completed)
            _log.Info("Envio da frase de desistência cancelado.");
    }

    /// <summary>Envia a palavra com (ou sem) encenação e confere se o jogo aceitou.</summary>
    internal WordOutcome SendWord(string choice, string syllable, bool hurried, AppSettings s, CancellationToken ct)
    {
        var h = s.Humanization;
        var triggers = hurried ? RoundTriggers.None : _planner.SampleTriggers(h);
        bool useNumbers;
        lock (_gate)
            useNumbers = !hurried && h.InsertNumbers && _numbersRemaining > 0;
        // "Pensar após 3 letras" só reage à palavra escolhida; não filtra as candidatas.
        bool think = !hurried && h.ThinkAfterThree && syllable.Length >= 3
                     && choice.StartsWith(syllable[..3], StringComparison.Ordinal);

        var script = _planner.BuildRound(choice, triggers, think, useNumbers, h, s.Timing);
        TimeSpan budget, spent;
        lock (_gate)
        {
            budget = _turnClock.Remaining(s.Timing.RoundTimeLimitSeconds);
            spent = _turnClock.ElapsedInTurn;
        }
        string flags = script.Flags.Count > 0 ? string.Join(", ", script.Flags) : "nenhuma";
        _log.Info($"Estimativa: ~{script.EstimatedDuration.TotalSeconds:F2}s | sobra ~{budget.TotalSeconds:F2}s " +
                  $"(gastos {spent.TotalSeconds:F2}s) | encenação: {flags}");

        if (!hurried && script.EstimatedDuration > budget)
        {
            _log.Warning($"Tempo curto: {script.EstimatedDuration.TotalSeconds:F2}s > orçamento {budget.TotalSeconds:F2}s → enviando direto.");
            Live?.Invoke(new LiveEvent(LiveEventKind.Event, "tempo curto — enviando direto"));
        }
        if (hurried || script.EstimatedDuration > budget)
        {
            script = TypingPlanner.QuickRound(choice);
            useNumbers = false;
        }

        SetStatus(EngineStatus.Playing);
        Live?.Invoke(new LiveEvent(LiveEventKind.Event, "digitando…"));
        var executor = CreateExecutor(s);
        string? submitted = null;
        foreach (var plan in script.Plans)
        {
            var outcome = executor.Execute(plan, s.Calibration.ChatPoint, s.General.TestMode, ct);
            if (outcome != PlanOutcome.Completed)
            {
                _log.Info($"Jogada cancelada ({plan.Label}).");
                Live?.Invoke(new LiveEvent(LiveEventKind.Event, "jogada cancelada"));
                return WordOutcome.Cancelled;
            }
            if (plan.Submits)
                submitted = plan.SubmittedText;
        }

        if (script.Style == RoundStyle.DeliberateFailure)
        {
            _log.Info($"Falha proposital enviada: {submitted}");
            lock (_gate)
            {
                _deliberateFailures++;
                _streak = 0;
            }
            StateChanged?.Invoke();
            return WordOutcome.NotCounted;
        }

        SetStatus(EngineStatus.Verifying);
        if (!WasAccepted(s, ct))
        {
            if (!string.Equals(submitted, choice, StringComparison.Ordinal))
            {
                // Dígitos inseridos tornam a palavra inválida; isso não diz nada sobre a palavra em si.
                _log.Info($"Recusada com dígitos inseridos ('{submitted}'); não conta contra '{choice}'.");
                return WordOutcome.NotCounted;
            }
            return WordOutcome.Rejected;
        }

        RegisterAccept(choice, useNumbers, s);
        Live?.Invoke(new LiveEvent(LiveEventKind.Event, "aceita ✓"));
        return WordOutcome.Accepted;
    }

    private TypingExecutor CreateExecutor(AppSettings s) =>
        new(_s.Input, _s.Clock, new TurnGuard(_s.Detector, _s.Input, _s.Clock, s), _s.TargetGuard, _log);

    /// <summary>Se a vez continua sendo do jogador logo após o ENTER, a palavra foi recusada.</summary>
    private bool WasAccepted(AppSettings s, CancellationToken ct)
    {
        if (!s.Verification.VerifySubmission || s.General.TestMode)
            return true;
        _s.Clock.Sleep(Ms.Of(Math.Max(50, s.Verification.VerificationDelayMs)), ct);
        return !_s.Detector.IsStillMyTurn(s);
    }

    private void RegisterAccept(string word, bool usedNumbers, AppSettings s)
    {
        bool numbersFinished = false;
        lock (_gate)
        {
            _accepted++;
            _streak++;
            _history.Add(word);
            _selector.RegisterUse(word, s.Selection);
            _turnClock.Mark(false); // a vez passou para o próximo jogador
            if (usedNumbers && _numbersRemaining > 0)
            {
                _numbersRemaining--;
                numbersFinished = _numbersRemaining == 0;
            }
        }
        if (numbersFinished)
            _log.Info("Rodadas com números concluídas.");
        StateChanged?.Invoke();
    }

    /// <summary>Duas recusas = o JKLM não conhece a palavra; ela é aprendida como rejeitada.</summary>
    private void RegisterRejection(string word, AppSettings s)
    {
        int strikes;
        lock (_gate)
        {
            _rejected++;
            _streak = 0;
            strikes = _strikes.GetValueOrDefault(word) + 1;
            _strikes[word] = strikes;
        }

        if (strikes >= 2 && s.Verification.LearnRejected)
        {
            if (_s.Words.AddRejected(word))
            {
                try
                {
                    _s.WordRepository.PersistRejected(word);
                    _log.Warning($"'{word}' recusada {strikes}x → aprendida como rejeitada.");
                }
                catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
                {
                    _log.Error($"'{word}' recusada {strikes}x, mas não foi possível gravar a lista de rejeitadas: {ex.Message}", ex);
                }
            }
            else
            {
                _log.Info($"'{word}' recusada {strikes}x (já estava na lista).");
            }
        }
        else
        {
            _log.Info($"'{word}' recusada pelo jogo; tentando outra.");
        }
        StateChanged?.Invoke();
    }

    private void CheckInactivity(AppSettings s)
    {
        if (!s.Verification.AutoNewMatch)
            return;
        TimeSpan idle;
        bool hasUsedWords;
        lock (_gate)
        {
            idle = _turnClock.SinceLastTurn;
            hasUsedWords = _selector.UsedInMatch.Count > 0;
        }
        if (hasUsedWords && idle.TotalSeconds >= s.Verification.InactivityNewMatchSeconds)
        {
            NewMatch($"{idle.TotalSeconds:F0}s sem turnos");
            lock (_gate)
                _turnClock.ResetIdle();
        }
    }

    private void SetStatus(EngineStatus status)
    {
        if (_status == status)
            return;
        _status = status;
        StatusChanged?.Invoke(status);
    }

    // ---------------------------------------------------------------- apoio a testes

    internal void MarkTurnForTest(bool myTurn)
    {
        lock (_gate)
            _turnClock.Mark(myTurn);
    }

    internal TurnClock TurnClockForTest => _turnClock;

    internal WordSelector SelectorForTest => _selector;

    internal int StrikesFor(string word)
    {
        lock (_gate)
            return _strikes.GetValueOrDefault(word);
    }
}
