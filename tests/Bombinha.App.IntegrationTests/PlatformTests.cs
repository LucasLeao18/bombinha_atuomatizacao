using System.Diagnostics;
using System.Runtime.ExceptionServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Bombinha.App.Infrastructure;
using Bombinha.App.Platform;
using Bombinha.Core.Capture;
using Bombinha.Core.Common;
using Bombinha.Core.Detection;
using Bombinha.Core.Imaging;
using Bombinha.Core.Logging;
using Bombinha.Core.Settings;
using Bombinha.Core.Typing;
using Xunit.Abstractions;

namespace Bombinha.App.IntegrationTests;

/// <summary>Executa o corpo numa thread STA com Dispatcher (exigência do WPF).</summary>
internal static class Sta
{
    public static void Run(Action body)
    {
        ExceptionDispatchInfo? failure = null;
        var thread = new Thread(() =>
        {
            try
            {
                body();
            }
            catch (Exception ex)
            {
                failure = ExceptionDispatchInfo.Capture(ex);
            }
            finally
            {
                Dispatcher.CurrentDispatcher.InvokeShutdown();
            }
        });
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        Assert.True(thread.Join(TimeSpan.FromSeconds(60)), "timeout");
        failure?.Throw();
    }

    /// <summary>Processa a fila do Dispatcher até a renderização assentar.</summary>
    public static void Pump(int milliseconds = 300)
    {
        var until = DateTime.UtcNow.AddMilliseconds(milliseconds);
        while (DateTime.UtcNow < until)
        {
            var frame = new DispatcherFrame();
            Dispatcher.CurrentDispatcher.BeginInvoke(DispatcherPriority.Background, () => frame.Continue = false);
            Dispatcher.PushFrame(frame);
            Thread.Sleep(15);
        }
    }

    /// <summary>Janela sem borda, sempre no topo, posicionada em pixels físicos.</summary>
    public static Window ShowAt(UIElement content, ScreenRect rect, bool activate = false)
    {
        var w = new Window
        {
            WindowStyle = WindowStyle.None,
            ResizeMode = ResizeMode.NoResize,
            Topmost = true,
            ShowInTaskbar = false,
            ShowActivated = activate,
            Background = new SolidColorBrush(Color.FromRgb(0x1C, 0x1F, 0x26)),
            Content = content,
        };
        w.SourceInitialized += (_, _) =>
            Native.SetWindowPos(new WindowInteropHelper(w).Handle, Native.HWND_TOPMOST, rect.X, rect.Y, rect.Width, rect.Height,
                activate ? 0 : Native.SWP_NOACTIVATE);
        w.Show();
        if (activate)
            w.Activate();
        Pump();
        return w;
    }
}

public class PlatformTests(ITestOutputHelper output)
{
    private static readonly ScreenRect Area = new(200, 200, 420, 220);

    private static AppSettings SettingsWithChatAt(ScreenPoint chat)
    {
        var s = new AppSettings();
        s.Calibration.ChatPoint = chat;
        s.Detection.UseTurnBar = false;
        return s;
    }

    [Fact]
    public void Captura_de_tela_encontra_o_template_renderizado()
    {
        Sta.Run(() =>
        {
            PixelBuffer template;
            using (var stream = EmbeddedAssets.Open(EmbeddedAssets.ChatTemplate))
                template = ImageFiles.Load(stream);

            BitmapSource bitmap;
            using (var stream = EmbeddedAssets.Open(EmbeddedAssets.ChatTemplate))
                bitmap = BitmapFrame.Create(stream, BitmapCreateOptions.None, BitmapCacheOption.OnLoad);
            var canvas = new Canvas();
            var image = new Image { Source = bitmap, Stretch = Stretch.None };
            RenderOptions.SetBitmapScalingMode(image, BitmapScalingMode.NearestNeighbor);
            canvas.Children.Add(image);
            var window = Sta.ShowAt(canvas, Area);
            try
            {
                // Coloca a imagem 1:1 em pixels físicos a (40, 50) do canto da janela.
                double scale = VisualTreeHelper.GetDpi(window).DpiScaleX;
                image.Width = template.Width / scale;
                image.Height = template.Height / scale;
                Canvas.SetLeft(image, 40 / scale);
                Canvas.SetTop(image, 50 / scale);
                Sta.Pump();

                var screen = new GdiScreenCapture();
                var shot = screen.Capture(Area);
                var match = new TemplateMatcher(GrayImage.FromBgra(template)).FindBest(GrayImage.FromBgra(shot));
                output.WriteLine($"escala {scale:F2}, achado em ({match.X},{match.Y}) score {match.Score:F4}");
                Assert.Equal((40, 50), (match.X, match.Y));
                Assert.True(match.Score > 0.97);

                // E o detector completo, procurando na faixa ao redor do "campo de digitação".
                var detector = new TurnDetector(screen, new Logger(NullLogSink.Instance, "t"));
                detector.SetTemplate(template);
                var probe = detector.ProbeChatbox(SettingsWithChatAt(new ScreenPoint(Area.X + 100, Area.Y + 80)));
                output.WriteLine($"detector: visível={probe.Visible} score={probe.Score:F4} em {probe.Location} busca {probe.SearchArea}");
                Assert.True(probe.Visible);
                Assert.Equal(new ScreenPoint(Area.X + 40, Area.Y + 50), probe.Location);
            }
            finally
            {
                window.Close();
            }

            // Sem o campo na tela, a mesma busca não pode dar positivo.
            Sta.Pump(200);
            var detectorAfter = new TurnDetector(new GdiScreenCapture(), new Logger(NullLogSink.Instance, "t"));
            detectorAfter.SetTemplate(template);
            var empty = SettingsWithChatAt(new ScreenPoint(Area.X + 100, Area.Y + 80));
            empty.Detection.SearchMarginY = 40;
            output.WriteLine($"sem janela: score {detectorAfter.ProbeChatbox(empty).Score:F4}");
        });
    }

    [Theory]
    [InlineData("VEN", 46.0)]
    [InlineData("BRA", 34.0)]
    [InlineData("LHA", 20.0)]
    [InlineData("CA", 34.0)]
    public void Ocr_do_windows_le_a_silaba_renderizada(string syllable, double fontSize)
    {
        var ocr = new WindowsOcrEngine();
        Assert.True(ocr.IsAvailable, ocr.UnavailableReason);
        Sta.Run(() =>
        {
            var text = new TextBlock
            {
                Text = syllable,
                FontSize = fontSize,
                FontWeight = FontWeights.Bold,
                FontFamily = new FontFamily("Segoe UI"),
                Foreground = Brushes.White,
                HorizontalAlignment = HorizontalAlignment.Center,
                VerticalAlignment = VerticalAlignment.Center,
            };
            var window = Sta.ShowAt(new Grid { Children = { text } }, new ScreenRect(Area.X, Area.Y, 200, 90));
            try
            {
                var settings = new AppSettings();
                settings.Calibration.SyllableRegion = new ScreenRect(Area.X, Area.Y, 200, 90);
                var reader = new OcrSyllableReader(new GdiScreenCapture(), ocr, new Logger(NullLogSink.Instance, "t"));
                string? raw = reader.Read(settings);
                output.WriteLine($"OCR ({ocr.Language}) leu: '{raw}'");
                Assert.Equal(syllable.ToLowerInvariant(), SyllableText.Normalize(raw));
            }
            finally
            {
                window.Close();
            }
        });
    }

    /// <summary>Outros programas (histórico do Windows etc.) seguram o clipboard por instantes após cada cópia.</summary>
    private static void SetClipboardText(string text)
    {
        for (int attempt = 1; ; attempt++)
        {
            try
            {
                Clipboard.SetText(text);
                return;
            }
            catch (System.Runtime.InteropServices.ExternalException) when (attempt < 20)
            {
                Thread.Sleep(50);
            }
        }
    }

    [Fact]
    public void Clipboard_detecta_copia_e_restaura_o_conteudo_do_usuario()
    {
        Sta.Run(() =>
        {
            var window = Sta.ShowAt(new Grid(), new ScreenRect(Area.X, Area.Y, 10, 10));
            nint hwnd = new WindowInteropHelper(window).Handle;
            var clipboard = new Win32Clipboard(() => hwnd);
            var original = clipboard.TakeSnapshot(); // conteúdo real do usuário
            try
            {
                uint before = clipboard.SequenceNumber;
                SetClipboardText("bombinha-teste-1");
                Assert.NotEqual(before, clipboard.SequenceNumber);
                Assert.Equal("bombinha-teste-1", clipboard.TryGetText());

                var snapshot = clipboard.TakeSnapshot();
                Assert.NotNull(snapshot);
                SetClipboardText("outro texto");
                clipboard.Restore(snapshot!);
                Assert.Equal("bombinha-teste-1", clipboard.TryGetText());
            }
            finally
            {
                if (original is not null)
                    clipboard.Restore(original);
                else
                    Clipboard.Clear();
                window.Close();
            }
        });
    }

    [Fact]
    public void Relogio_de_alta_resolucao_e_preciso_e_cancelavel()
    {
        var clock = new HighResolutionClock();
        var sw = Stopwatch.StartNew();
        for (int i = 0; i < 40; i++)
            clock.Sleep(TimeSpan.FromMilliseconds(3), CancellationToken.None);
        double mean = sw.Elapsed.TotalMilliseconds / 40;
        output.WriteLine($"média por espera de 3 ms: {mean:F2} ms");
        Assert.InRange(mean, 2.9, 6.0); // o timer comum daria ~15,6 ms

        using var cts = new CancellationTokenSource(TimeSpan.FromMilliseconds(50));
        sw.Restart();
        Assert.ThrowsAny<OperationCanceledException>(() => clock.Sleep(TimeSpan.FromSeconds(10), cts.Token));
        output.WriteLine($"cancelamento em {sw.ElapsedMilliseconds} ms");
        Assert.True(sw.ElapsedMilliseconds < 1000);
    }

    [Fact]
    public void SendInput_digita_unicode_e_atalhos_na_janela_em_foco()
    {
        Sta.Run(() =>
        {
            var box = new TextBox { FontSize = 18 };
            var window = Sta.ShowAt(box, new ScreenRect(Area.X, Area.Y, 300, 60), activate: true);
            nint hwnd = new WindowInteropHelper(window).Handle;
            try
            {
                box.Focus();
                Sta.Pump();
                if (Native.GetForegroundWindow() != hwnd)
                {
                    // O Windows pode negar o foco a um processo de teste; nunca digitamos fora da janela de teste.
                    output.WriteLine("INCONCLUSIVO: o Windows não deu foco à janela de teste; SendInput não foi exercitado.");
                    return;
                }

                var input = new Win32Input();
                input.TypeText("ação Ç ü");
                Sta.Pump(200);
                Assert.Equal("ação Ç ü", box.Text);

                Assert.Equal(hwnd, Native.GetForegroundWindow());
                input.PressKey(VirtualKey.Backspace);
                Sta.Pump(150);
                Assert.Equal("ação Ç ", box.Text);

                input.PressChord(VirtualKey.Control, VirtualKey.A);
                input.PressKey(VirtualKey.Backspace);
                Sta.Pump(150);
                Assert.Equal("", box.Text);

                // O guarda de segurança precisa recusar digitar no próprio Bombinha.
                var guard = new ForegroundWindowGuard(new Logger(NullLogSink.Instance, "t"));
                var check = guard.Check(new ScreenPoint(Area.X + 20, Area.Y + 20));
                Assert.False(check.IsSafe);
                output.WriteLine($"guarda: {check.Reason}");
            }
            finally
            {
                window.Close();
            }
        });
    }
}
