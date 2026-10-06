using System.IO;
using System.Windows.Threading;
using Bombinha.App.Ui;
using Bombinha.Core.Engine;
using Bombinha.Core.Logging;
using Bombinha.Core.Settings;
using Bombinha.Core.Words;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Microsoft.Win32;

namespace Bombinha.App.ViewModels;

public enum Page
{
    Dashboard,
    Console,
    Setup,
    Humanization,
    Stats,
}

public sealed partial class LetterChip(char letter) : ObservableObject
{
    [ObservableProperty]
    private bool _used;

    public string Letter { get; } = letter.ToString().ToUpperInvariant();
    public char Key { get; } = letter;
}

public sealed record HistoryRow(int Index, string Word, int Uses);

/// <summary>Estado da janela principal: navegação, controle do motor, painel ao vivo e estatísticas.</summary>
internal sealed partial class MainViewModel : ObservableObject
{
    private static readonly Dictionary<Page, (string Title, string Subtitle)> PageTitles = new()
    {
        [Page.Dashboard] = ("Principal", "Escolha o modo e inicie a automação"),
        [Page.Console] = ("Console", "Acompanhe cada decisão do bot em tempo real"),
        [Page.Setup] = ("Setup", "Dicionário, posições de tela, detecção e ritmo"),
        [Page.Humanization] = ("Humanização", "Perfil de digitação e comportamentos humanos"),
        [Page.Stats] = ("Estatísticas", "Desempenho da sessão e histórico de palavras"),
    };

    private readonly AppServices _app;
    private readonly Dispatcher _dispatcher;
    private readonly Logger _log;
    private int _snapshotQueued;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(PageTitle), nameof(PageSubtitle))]
    private Page _currentPage = Page.Dashboard;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(StatusText), nameof(IsRunning))]
    [NotifyCanExecuteChangedFor(nameof(StartCommand), nameof(StopCommand))]
    private EngineStatus _status = EngineStatus.Stopped;

    [ObservableProperty]
    private GameMode _mode;

    [ObservableProperty]
    private bool _alwaysOnTop;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(ReloadDictionaryCommand), nameof(StartCommand))]
    private bool _isLoadingDictionary;

    [ObservableProperty] private string _liveSyllable = "—";
    [ObservableProperty] private string _liveWord = "—";
    [ObservableProperty] private string _liveEvent = "aguardando…";

    [ObservableProperty] private int _sentCount;
    [ObservableProperty] private int _streak;
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(DictionaryCountText))]
    private int _dictionaryCount;
    [ObservableProperty] private int _alphabetsCompleted;
    [ObservableProperty] private int _deliberateFailures;
    [ObservableProperty] private int _rejectedCount;
    [ObservableProperty] private int _learnedCount;
    [ObservableProperty] private int _numbersRemaining;
    [ObservableProperty] private string _acceptanceText = "—";
    [ObservableProperty] private string _alphabetProgress = "0 / 23";
    [ObservableProperty] private IReadOnlyList<HistoryRow> _history = [];
    [ObservableProperty] private string _statusMessage = "Pronto.";
    [ObservableProperty] private string _statusSummary = "";

    public MainViewModel(AppServices app, ScreenPicker picker)
    {
        _app = app;
        _dispatcher = Dispatcher.CurrentDispatcher;
        _log = app.Log.For("App");
        Console = new ConsoleViewModel(_log);
        Setup = new SettingsViewModel(app, picker, ReloadDictionaryAsync);
        Letters = WordSelector.AlphabetLetters.Select(c => new LetterChip(c)).ToArray();

        _mode = app.Settings.Current.Mode;
        _alwaysOnTop = app.Settings.Current.General.AlwaysOnTop;

        app.UiLog.EntriesAdded += Console.Append;
        Console.LineAdded += line => StatusMessage = line.Message.Length > 140 ? line.Message[..140] + "…" : line.Message;
        app.Engine.StatusChanged += s => _dispatcher.BeginInvoke(() => OnEngineStatus(s));
        app.Engine.Live += e => _dispatcher.BeginInvoke(() => OnLive(e));
        app.Engine.StateChanged += QueueSnapshot;
        RefreshSnapshot();
    }

    public ConsoleViewModel Console { get; }
    public SettingsViewModel Setup { get; }
    public IReadOnlyList<LetterChip> Letters { get; }

    public string DictionaryCountText => DictionaryCount.ToString("N0");

    public string PageTitle => PageTitles[CurrentPage].Title;
    public string PageSubtitle => PageTitles[CurrentPage].Subtitle;

    public bool IsRunning => Status is not (EngineStatus.Stopped or EngineStatus.Faulted);

    public string StatusText => Status switch
    {
        EngineStatus.Loading => "Carregando…",
        EngineStatus.WaitingForTurn => "Aguardando a vez",
        EngineStatus.ReadingSyllable => "Lendo a sílaba",
        EngineStatus.Playing => "Digitando",
        EngineStatus.Verifying => "Conferindo",
        EngineStatus.Faulted => "Erro",
        _ => "Parado",
    };

    // ------------------------------------------------------------------ comandos

    private bool CanStart() => !IsRunning && !IsLoadingDictionary;

    [RelayCommand(CanExecute = nameof(CanStart))]
    private void Start()
    {
        // Iniciar aplica e grava o que estiver editado no Setup/Humanização.
        if (!Setup.Save())
            return;
        var settings = _app.Settings.Current;

        try
        {
            _app.Detector.SetTemplate(AppServices.LoadTemplate(settings));
        }
        catch (Exception ex) when (ex is IOException or ArgumentException)
        {
            _log.Error("Template do campo de digitação inválido.", ex);
            Dialogs.Error("Não foi possível iniciar", $"Template do campo de digitação inválido:\n{ex.Message}");
            return;
        }
        if (settings.General.DictionaryPath is { } path && !File.Exists(path))
        {
            Dialogs.Error("Dicionário não encontrado", $"Não encontrei o arquivo:\n{path}");
            return;
        }

        LiveEvent = "procurando o campo de digitação…";
        _app.Engine.Start();
    }

    private bool CanStop() => IsRunning;

    [RelayCommand(CanExecute = nameof(CanStop))]
    private void Stop()
    {
        _app.Engine.Stop();
        LiveEvent = "parando…";
    }

    /// <summary>F8: para tudo, inclusive no meio da digitação.</summary>
    public void KillSwitch()
    {
        if (!IsRunning)
            return;
        _log.Warning("F8 pressionado — automação interrompida.");
        Stop();
    }

    [RelayCommand]
    private void NewMatch() => _app.Engine.NewMatch("manual");

    [RelayCommand]
    private void CycleMode() => Mode = Mode.Next();

    private bool CanReload() => !IsLoadingDictionary;

    [RelayCommand(CanExecute = nameof(CanReload))]
    private async Task ReloadDictionary()
    {
        if (!Setup.Save())
            return;
        await ReloadDictionaryAsync();
    }

    /// <summary>Carrega o dicionário fora da thread da interface (≈245 mil palavras).</summary>
    public async Task ReloadDictionaryAsync()
    {
        IsLoadingDictionary = true;
        var settings = _app.Settings.Current;
        try
        {
            var summary = await Task.Run(() => _app.WordRepository.LoadInto(_app.Words, settings));
            _log.Success($"Dicionário carregado ({summary.Words} palavras, {summary.Source}). " +
                         $"Blacklist: {summary.Blacklisted} | Recusadas pelo jogo: {summary.Rejected}");
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException)
        {
            _log.Error($"Falha ao carregar o dicionário: {ex.Message}", ex);
        }
        finally
        {
            IsLoadingDictionary = false;
            RefreshSnapshot();
        }
    }

    [RelayCommand]
    private void ExportHistory()
    {
        var snapshot = _app.Engine.GetSnapshot();
        if (snapshot.History.Count == 0)
        {
            _log.Info("Nada para exportar: histórico vazio.");
            return;
        }
        var dialog = new SaveFileDialog { FileName = "historico.txt", DefaultExt = ".txt", Filter = "Texto (*.txt)|*.txt" };
        if (dialog.ShowDialog() != true)
            return;
        try
        {
            File.WriteAllLines(dialog.FileName, snapshot.History.Select(h => $"{h.Word}\t{h.Uses}"));
            _log.Success($"Histórico exportado para {dialog.FileName}");
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            _log.Error("Falha ao exportar o histórico.", ex);
            Dialogs.Error("Exportar histórico", ex.Message);
        }
    }

    [RelayCommand]
    private void Save() => Setup.Save();

    // ------------------------------------------------------------------ preferências gravadas na hora

    partial void OnModeChanged(GameMode value)
    {
        PersistQuietly(s => s.Mode = value);
        Setup.SyncFromCurrent(s => s.Mode = value);
        _log.Info($"Modo selecionado: {value.DisplayName()}", LogTag.Accent);
        UpdateSummary();
    }

    partial void OnAlwaysOnTopChanged(bool value)
    {
        PersistQuietly(s => s.General.AlwaysOnTop = value);
        Setup.SyncFromCurrent(s => s.General.AlwaysOnTop = value);
    }

    private void PersistQuietly(Action<AppSettings> change)
    {
        try
        {
            _app.Settings.Update(change);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            _log.Warning("Não foi possível gravar a preferência.", ex);
        }
    }

    // ------------------------------------------------------------------ eventos do motor

    private void OnEngineStatus(EngineStatus status)
    {
        Status = status;
        if (status == EngineStatus.Stopped)
            LiveEvent = "parado";
        else if (status == EngineStatus.Faulted)
            LiveEvent = "erro — veja o console";
        else if (status == EngineStatus.WaitingForTurn && LiveEvent is "procurando o campo de digitação…" or "aceita ✓")
            LiveEvent = "aguardando a sua vez…";
    }

    private void OnLive(LiveEvent e)
    {
        switch (e.Kind)
        {
            case LiveEventKind.Syllable:
                LiveSyllable = e.Text;
                break;
            case LiveEventKind.Word:
                LiveWord = e.Text;
                break;
            default:
                LiveEvent = e.Text;
                break;
        }
    }

    /// <summary>Agrupa várias mudanças seguidas num único retrato (o motor pode notificar de outra thread).</summary>
    private void QueueSnapshot()
    {
        if (Interlocked.Exchange(ref _snapshotQueued, 1) == 0)
            _dispatcher.BeginInvoke(RefreshSnapshot, DispatcherPriority.Background);
    }

    private void RefreshSnapshot()
    {
        Interlocked.Exchange(ref _snapshotQueued, 0);
        var s = _app.Engine.GetSnapshot();
        SentCount = s.History.Count;
        Streak = s.Streak;
        DictionaryCount = s.DictionaryCount;
        AlphabetsCompleted = s.AlphabetsCompleted;
        DeliberateFailures = s.DeliberateFailures;
        RejectedCount = s.Rejected;
        LearnedCount = s.LearnedRejected;
        NumbersRemaining = s.NumbersRemaining;
        AcceptanceText = s.AcceptanceRate is { } rate ? $"{rate:F0}%" : "—";
        foreach (var chip in Letters)
            chip.Used = s.LettersUsed.Contains(chip.Key);
        AlphabetProgress = $"{s.LettersUsed.Count} / {Letters.Count}";
        if (s.History.Count != History.Count)
            History = s.History.Select((h, i) => new HistoryRow(s.History.Count - i, h.Word, h.Uses)).Reverse().ToArray();
        UpdateSummary();
    }

    private void UpdateSummary()
    {
        string summary = $"modo: {Mode.DisplayName()}   ·   dicionário: {DictionaryCountText}   ·   aceitas: {SentCount}";
        if (AcceptanceText != "—")
            summary += $"   ·   aceitação: {AcceptanceText}";
        StatusSummary = summary;
    }
}
