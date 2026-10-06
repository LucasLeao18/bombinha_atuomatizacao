using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Shapes;
using Bombinha.App.Platform;
using Bombinha.Core.Common;

namespace Bombinha.App.Ui;

/// <summary>
/// Calibração por clique: uma camada quase transparente cobre todas as telas, mostra a instrução
/// e devolve as posições em pixels físicos. Esc ou botão direito cancela.
/// </summary>
internal sealed class ScreenPicker(Window owner)
{
    public async Task<ScreenPoint?> PickPointAsync(string instruction)
    {
        var points = await PickAsync(instruction, 1);
        return points?[0];
    }

    public async Task<ScreenRect?> PickRectAsync(string instruction)
    {
        var points = await PickAsync(instruction + "  (canto superior esquerdo, depois inferior direito)", 2);
        return points is null ? null : ScreenRect.FromCorners(points[0], points[1]);
    }

    private async Task<IReadOnlyList<ScreenPoint>?> PickAsync(string instruction, int count)
    {
        bool wasVisible = owner.IsVisible;
        owner.Hide(); // a janela do app não pode esconder o jogo durante a calibração
        try
        {
            var window = new PickerWindow(instruction, count);
            window.Show();
            window.Activate();
            return await window.Result;
        }
        finally
        {
            if (wasVisible)
            {
                owner.Show();
                owner.Activate();
            }
        }
    }

    private sealed class PickerWindow : Window
    {
        private readonly TaskCompletionSource<IReadOnlyList<ScreenPoint>?> _tcs = new();
        private readonly List<ScreenPoint> _points = [];
        private readonly int _count;
        private readonly Canvas _canvas = new();
        private readonly Rectangle _selection;
        private readonly TextBlock _coords;
        private readonly TextBlock _progress;
        private readonly Border _banner;

        public PickerWindow(string instruction, int count)
        {
            _count = count;
            WindowStyle = WindowStyle.None;
            AllowsTransparency = true;
            ResizeMode = ResizeMode.NoResize;
            ShowInTaskbar = false;
            Topmost = true;
            Cursor = Cursors.Cross;
            // Alfa mínimo: quase invisível, mas recebe os cliques (que não chegam ao jogo).
            Background = new SolidColorBrush(Color.FromArgb(0x28, 0x05, 0x08, 0x10));

            var accent = (Brush)Application.Current.FindResource("Accent");
            _selection = new Rectangle
            {
                Stroke = accent,
                StrokeThickness = 2,
                Fill = new SolidColorBrush(Color.FromArgb(0x30, 0x6C, 0x8C, 0xFF)),
                Visibility = Visibility.Collapsed,
            };
            _coords = new TextBlock
            {
                Foreground = Brushes.White,
                Background = new SolidColorBrush(Color.FromArgb(0xC0, 0x0B, 0x0E, 0x14)),
                Padding = new Thickness(6, 2, 6, 2),
                FontFamily = new FontFamily("Consolas"),
                IsHitTestVisible = false,
            };
            _progress = new TextBlock { Foreground = (Brush)Application.Current.FindResource("TextDim"), Margin = new Thickness(0, 6, 0, 0) };

            var panel = new StackPanel();
            panel.Children.Add(new TextBlock { Text = "MODO CAPTURA", Foreground = accent, FontWeight = FontWeights.Bold, FontSize = 11 });
            panel.Children.Add(new TextBlock
            {
                Text = instruction,
                Foreground = (Brush)Application.Current.FindResource("Text"),
                FontSize = 15,
                FontWeight = FontWeights.SemiBold,
                Margin = new Thickness(0, 4, 0, 0),
                TextWrapping = TextWrapping.Wrap,
                MaxWidth = 560,
            });
            panel.Children.Add(_progress);
            panel.Children.Add(new TextBlock
            {
                Text = "Esc ou botão direito cancela",
                Foreground = (Brush)Application.Current.FindResource("TextMute"),
                FontSize = 11,
                Margin = new Thickness(0, 6, 0, 0),
            });
            _banner = new Border
            {
                Background = (Brush)Application.Current.FindResource("Surface"),
                BorderBrush = accent,
                BorderThickness = new Thickness(2),
                CornerRadius = new CornerRadius(10),
                Padding = new Thickness(20, 14, 20, 14),
                Child = panel,
                IsHitTestVisible = false,
            };

            _canvas.Children.Add(_selection);
            _canvas.Children.Add(_banner);
            _canvas.Children.Add(_coords);
            Content = _canvas;
            UpdateProgress();

            SourceInitialized += (_, _) => CoverVirtualDesktop();
            Loaded += (_, _) => PlaceBanner();
            MouseMove += (_, _) => Track();
            MouseLeftButtonDown += OnLeftClick;
            MouseRightButtonDown += (_, _) => Finish(null);
            KeyDown += (_, e) =>
            {
                if (e.Key == Key.Escape)
                    Finish(null);
            };
            Closed += (_, _) => _tcs.TrySetResult(null);
        }

        public Task<IReadOnlyList<ScreenPoint>?> Result => _tcs.Task;

        private void CoverVirtualDesktop()
        {
            var desktop = GdiScreenCapture.VirtualDesktop();
            nint hwnd = new WindowInteropHelper(this).Handle;
            Native.SetWindowPos(hwnd, Native.HWND_TOPMOST, desktop.X, desktop.Y, desktop.Width, desktop.Height, 0);
        }

        private void PlaceBanner()
        {
            // Centraliza a instrução no topo do monitor onde está o cursor.
            var cursor = CursorPosition();
            var monitor = new GdiScreenCapture().MonitorBoundsAt(cursor);
            var topCenter = PointFromScreen(new Point(monitor.X + (monitor.Width / 2.0), monitor.Y + 40));
            _banner.Measure(new Size(double.PositiveInfinity, double.PositiveInfinity));
            Canvas.SetLeft(_banner, topCenter.X - (_banner.DesiredSize.Width / 2));
            Canvas.SetTop(_banner, topCenter.Y);
            Track();
        }

        private void Track()
        {
            var cursor = CursorPosition();
            _coords.Text = cursor.ToString();
            var local = PointFromScreen(new Point(cursor.X, cursor.Y));
            Canvas.SetLeft(_coords, local.X + 16);
            Canvas.SetTop(_coords, local.Y + 16);

            if (_count == 2 && _points.Count == 1)
            {
                var start = PointFromScreen(new Point(_points[0].X, _points[0].Y));
                Canvas.SetLeft(_selection, Math.Min(start.X, local.X));
                Canvas.SetTop(_selection, Math.Min(start.Y, local.Y));
                _selection.Width = Math.Abs(local.X - start.X);
                _selection.Height = Math.Abs(local.Y - start.Y);
                _selection.Visibility = Visibility.Visible;
            }
        }

        private void OnLeftClick(object sender, MouseButtonEventArgs e)
        {
            _points.Add(CursorPosition());
            if (_points.Count >= _count)
                Finish(_points.ToArray());
            else
                UpdateProgress();
        }

        private void UpdateProgress() =>
            _progress.Text = _count > 1 ? $"Ponto {_points.Count + 1} de {_count}" : "Clique no ponto desejado";

        private void Finish(IReadOnlyList<ScreenPoint>? result)
        {
            _tcs.TrySetResult(result);
            Close();
        }

        private static ScreenPoint CursorPosition() =>
            Native.GetCursorPos(out var p) ? new ScreenPoint(p.X, p.Y) : default;
    }
}

/// <summary>Mensagens modais padronizadas.</summary>
internal static class Dialogs
{
    public static void Error(string title, string message) =>
        MessageBox.Show(Application.Current.MainWindow!, message, title, MessageBoxButton.OK, MessageBoxImage.Error);

    public static void Info(string title, string message) =>
        MessageBox.Show(Application.Current.MainWindow!, message, title, MessageBoxButton.OK, MessageBoxImage.Information);
}
