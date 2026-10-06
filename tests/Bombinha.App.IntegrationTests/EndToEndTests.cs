using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Bombinha.App.Infrastructure;
using Bombinha.App.Platform;
using Bombinha.Core.Capture;
using Bombinha.Core.Common;
using Bombinha.Core.Detection;
using Bombinha.Core.Engine;
using Bombinha.Core.Logging;
using Bombinha.Core.Settings;
using Bombinha.Core.Typing;
using Bombinha.Core.Words;
using Xunit.Abstractions;

namespace Bombinha.App.IntegrationTests;

/// <summary>Só roda com BOMBINHA_E2E=1: move o mouse real e digita por alguns segundos.</summary>
public sealed class E2EFactAttribute : FactAttribute
{
    public E2EFactAttribute()
    {
        if (Environment.GetEnvironmentVariable("BOMBINHA_E2E") != "1")
            Skip = "Defina BOMBINHA_E2E=1 para rodar (usa o mouse e o teclado reais).";
    }
}

/// <summary>Versão parametrizada de <see cref="E2EFactAttribute"/>.</summary>
public sealed class E2ETheoryAttribute : TheoryAttribute
{
    public E2ETheoryAttribute()
    {
        if (Environment.GetEnvironmentVariable("BOMBINHA_E2E") != "1")
            Skip = "Defina BOMBINHA_E2E=1 para rodar (usa o mouse e o teclado reais).";
    }
}

public class EndToEndTests(ITestOutputHelper output)
{
    private sealed class OnlyWindowGuard(nint hwnd) : ITargetWindowGuard
    {
        public TargetCheck Check(ScreenPoint chatPoint) =>
            Native.GetForegroundWindow() == hwnd ? TargetCheck.Safe : TargetCheck.Unsafe("foco fora do jogo simulado");
    }

    private sealed class FixedWords(IReadOnlyList<string> words) : IWordRepository
    {
        public WordLoadSummary LoadInto(WordList list, AppSettings settings)
        {
            list.Replace(words, [], []);
            return new WordLoadSummary(words.Count, 0, 0, "teste");
        }

        public void PersistRejected(string word) { }
    }

    private sealed class OutputSink(ITestOutputHelper output) : ILogSink
    {
        public void Write(LogEntry entry)
        {
            try
            {
                output.WriteLine($"{entry.Timestamp:HH:mm:ss.fff} [{entry.Level}] [{entry.Component}] {entry.Message}");
            }
            catch (InvalidOperationException)
            {
                // teste já terminou
            }
        }
    }

    /// <summary>
    /// Jogo de mentira: mostra a sílaba (selecionável), o "campo de digitação" (template) e a caixa de texto.
    /// ENTER com palavra válida passa a vez; inválida é recusada e a vez continua.
    /// </summary>
    private sealed class FakeGame
    {
        private static readonly string[] Syllables = ["BRA", "SOL", "CA"];
        private static readonly HashSet<string> GameDictionary = ["brasa", "cobra", "solar", "girassol", "casa", "caco"];

        private readonly TextBox _syllable;
        private readonly Image _chatbox;
        private readonly TextBox _input;
        private int _round;

        public FakeGame(ScreenRect area)
        {
            Area = area;
            var canvas = new Canvas();
            _syllable = new TextBox
            {
                Text = Syllables[0], IsReadOnly = true, FontSize = 34, FontWeight = FontWeights.Bold, Width = 120,
                Background = Brushes.Transparent, Foreground = Brushes.White, BorderThickness = new Thickness(0),
            };
            Canvas.SetLeft(_syllable, 40);
            Canvas.SetTop(_syllable, 30);

            using (var stream = EmbeddedAssets.Open(EmbeddedAssets.ChatTemplate))
                _chatbox = new Image { Source = BitmapFrame.Create(stream, BitmapCreateOptions.None, BitmapCacheOption.OnLoad), Stretch = Stretch.None };
            Canvas.SetLeft(_chatbox, 40);
            Canvas.SetTop(_chatbox, 150);

            _input = new TextBox { Width = 300, FontSize = 18 };
            Canvas.SetLeft(_input, 110);
            Canvas.SetTop(_input, 170);
            _input.PreviewKeyDown += OnKey;

            var bar = new Border { Width = 140, Height = 20, Background = Brushes.Orange };
            Canvas.SetLeft(bar, 420);
            Canvas.SetTop(bar, 30);

            canvas.Children.Add(_syllable);
            canvas.Children.Add(_chatbox);
            canvas.Children.Add(_input);
            canvas.Children.Add(bar);
            Window = Sta.ShowAt(canvas, area, activate: true);
        }

        public ScreenRect Area { get; }
        public Window Window { get; }
        public List<string> Accepted { get; } = [];
        public List<string> Rejected { get; } = [];

        public ScreenPoint SyllablePoint => new(Area.X + 70, Area.Y + 55);
        public ScreenPoint ChatPoint => new(Area.X + 260, Area.Y + 185);
        public ScreenRect TurnBar => new(Area.X + 420, Area.Y + 30, 140, 20);
        public ScreenRect SyllableRegion => new(Area.X + 40, Area.Y + 30, 120, 50);

        private void OnKey(object sender, KeyEventArgs e)
        {
            if (e.Key != Key.Enter)
                return;
            e.Handled = true;
            string word = _input.Text.Trim().ToLowerInvariant();
            _input.Clear(); // o JKLM limpa o campo a cada envio
            string syllable = Syllables[_round % Syllables.Length].ToLowerInvariant();
            if (!word.Contains(syllable, StringComparison.Ordinal) || !GameDictionary.Contains(word) || Accepted.Contains(word))
            {
                Rejected.Add(word);
                return;
            }
            Accepted.Add(word);
            _round++;
            _chatbox.Visibility = Visibility.Hidden; // a vez passou
            var next = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(700) };
            next.Tick += (_, _) =>
            {
                next.Stop();
                _syllable.Text = Syllables[_round % Syllables.Length];
                _chatbox.Visibility = Visibility.Visible; // sua vez de novo
            };
            next.Start();
        }
    }

    [E2ETheory]
    [InlineData(SyllableCaptureMethod.Clipboard)]
    [InlineData(SyllableCaptureMethod.Ocr)]
    public void Motor_completo_joga_tres_rodadas_contra_um_jogo_simulado(SyllableCaptureMethod method)
    {
        Sta.Run(() =>
        {
            var game = new FakeGame(new ScreenRect(300, 200, 600, 260));
            nint hwnd = new WindowInteropHelper(game.Window).Handle;
            var settings = new AppSettings();
            settings.Calibration.SyllablePoint = game.SyllablePoint;
            settings.Calibration.ChatPoint = game.ChatPoint;
            settings.Calibration.TurnBar = game.TurnBar;
            settings.Mode = GameMode.ShortWords;
            settings.Selection.TopN = 1;
            settings.Timing.CycleDelayMs = 100;
            settings.Capture.ClickSelection = ClickSelection.DoubleClick;
            settings.Capture.Method = method;
            settings.Calibration.SyllableRegion = game.SyllableRegion;
            settings.Humanization.LetterDelayMs = 20;

            var screen = new GdiScreenCapture();
            var clock = new HighResolutionClock();
            var input = new Win32Input();
            var log = new Logger(new OutputSink(output), "E2E");
            var detector = new TurnDetector(screen, log.For("Detecção"));
            using (var stream = EmbeddedAssets.Open(EmbeddedAssets.ChatTemplate))
                detector.SetTemplate(ImageFiles.Load(stream));
            var clipboard = new Win32Clipboard(() => hwnd);
            var syllables = new SyllableCapture(
                new ClipboardSyllableReader(input, clipboard, clock, new OnlyWindowGuard(hwnd), log.For("Captura")),
                new OcrSyllableReader(screen, new WindowsOcrEngine(), log.For("Captura")), log.For("Captura"));

            // "solx" está no dicionário do bot mas não no do jogo: deve ser recusada e trocada.
            var words = new WordList();
            using var engine = new BotEngine(new EngineServices(detector, syllables, input, new OnlyWindowGuard(hwnd), clock,
                new Random(42), words, new FixedWords(["brasa", "cobra", "solx", "solar", "girassol", "casa", "caco"]),
                () => settings, log.For("Motor")));

            if (method == SyllableCaptureMethod.Ocr)
            {
                var crop = screen.Capture(game.SyllableRegion);
                string file = Path.Combine(Path.GetTempPath(), "bombinha-e2e-ocr.png");
                ImageFiles.SavePng(crop, file);
                var prepared = Bombinha.Core.Imaging.OcrPreprocessor.Prepare(crop, 2);
                output.WriteLine($"OCR antes de iniciar: '{new WindowsOcrEngine().Recognize(prepared)}' (recorte salvo em {file})");
            }

            var userCursor = input.GetCursorPosition();
            engine.Start();
            var deadline = DateTime.UtcNow.AddSeconds(45);
            // Espera o próprio motor confirmar a 3ª aceitação (ele confere a vez ~350 ms após o ENTER).
            while (engine.GetSnapshot().Accepted < 3 && DateTime.UtcNow < deadline && engine.IsRunning)
                Sta.Pump(100);
            engine.Stop();
            Assert.True(engine.WaitForExit(TimeSpan.FromSeconds(3)), "o motor não parou");
            Sta.Pump(200);
            game.Window.Close();
            input.MoveTo(userCursor);

            var snap = engine.GetSnapshot();
            output.WriteLine($"aceitas: {string.Join(", ", game.Accepted)} | recusadas: {string.Join(", ", game.Rejected)}");
            output.WriteLine($"motor: {snap.Accepted} aceitas, {snap.Rejected} recusadas, status {engine.Status}");
            Assert.Equal(3, game.Accepted.Count);
            Assert.Contains("bra", game.Accepted[0], StringComparison.Ordinal);
            Assert.Contains("sol", game.Accepted[1], StringComparison.Ordinal);
            Assert.Contains("ca", game.Accepted[2], StringComparison.Ordinal);
            Assert.Contains("solx", game.Rejected);
            Assert.Equal(3, snap.Accepted);
            Assert.True(snap.Rejected >= 1);
            Assert.Equal(EngineStatus.Stopped, engine.Status);
        });
    }
}
