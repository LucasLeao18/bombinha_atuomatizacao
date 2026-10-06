using System.IO;
using System.Windows.Threading;
using Bombinha.App.Infrastructure;
using Bombinha.App.Platform;
using Bombinha.Core.Capture;
using Bombinha.Core.Detection;
using Bombinha.Core.Engine;
using Bombinha.Core.Imaging;
using Bombinha.Core.Logging;
using Bombinha.Core.Settings;
using Bombinha.Core.Words;

namespace Bombinha.App;

/// <summary>Raiz de composição: cria e liga todos os serviços uma única vez.</summary>
internal sealed class AppServices : IDisposable
{
    private nint _mainWindowHandle;

    private AppServices(Dispatcher dispatcher)
    {
        Paths = new AppPaths();
        Paths.EnsureCreated();

        FileLog = new FileLogSink(Paths.LogDirectory);
        UiLog = new UiLogSink(dispatcher);
        Settings = new SettingsService(new SettingsStore(Paths.SettingsFile));
        var sink = new CompositeLogSink();
        sink.Add(FileLog, MinimumLevel);
        sink.Add(UiLog, MinimumLevel);
        Log = new Logger(sink, "App");

        WordRepository = new WordRepository(Paths);
        Migration = new LegacyMigration(Settings, WordRepository, Log.For("Migração"));
        Screen = new GdiScreenCapture();
        Input = new Win32Input();
        Clock = new HighResolutionClock();
        Ocr = new WindowsOcrEngine();
        Detector = new TurnDetector(Screen, Log.For("Detecção"));

        var captureLog = Log.For("Captura");
        var guard = new ForegroundWindowGuard(Log.For("Segurança"));
        var clipboard = new Win32Clipboard(() => Volatile.Read(ref _mainWindowHandle));
        var ocrReader = new OcrSyllableReader(Screen, Ocr, captureLog);
        var syllables = new SyllableCapture(new ClipboardSyllableReader(Input, clipboard, Clock, guard, captureLog), ocrReader, captureLog);

        Engine = new BotEngine(new EngineServices(
            Detector, syllables, Input, guard, Clock,
            new Random(), Words, WordRepository, () => Settings.Current, Log.For("Motor")));
    }

    public AppPaths Paths { get; }
    public FileLogSink FileLog { get; }
    public UiLogSink UiLog { get; }
    public Logger Log { get; }
    public SettingsService Settings { get; }
    public WordRepository WordRepository { get; }
    public WordList Words { get; } = new();
    public LegacyMigration Migration { get; }
    public GdiScreenCapture Screen { get; }
    public Win32Input Input { get; }
    public HighResolutionClock Clock { get; }
    public WindowsOcrEngine Ocr { get; }
    public TurnDetector Detector { get; }
    public BotEngine Engine { get; }

    public static AppServices Create(Dispatcher dispatcher) => new(dispatcher);

    /// <summary>Janela dona da área de transferência quando o app devolve o conteúdo do usuário.</summary>
    public void SetMainWindowHandle(nint hwnd) => Volatile.Write(ref _mainWindowHandle, hwnd);

    /// <summary>Template do campo de digitação: arquivo do usuário ou o embutido.</summary>
    /// <exception cref="IOException">Arquivo ausente ou imagem inválida.</exception>
    public static PixelBuffer LoadTemplate(AppSettings settings)
    {
        string? path = settings.Detection.TemplatePath;
        if (path is null)
        {
            using var stream = EmbeddedAssets.Open(EmbeddedAssets.ChatTemplate);
            return ImageFiles.Load(stream);
        }
        if (!File.Exists(path))
            throw new FileNotFoundException($"Template do campo de digitação não encontrado: {path}", path);
        return ImageFiles.Load(path);
    }

    private LogLevel MinimumLevel() => Settings.Current.General.VerboseLog ? LogLevel.Debug : LogLevel.Info;

    public void Dispose()
    {
        Engine.Dispose();
        FileLog.Dispose();
    }
}
