using System.ComponentModel;
using System.Diagnostics.CodeAnalysis;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using Bombinha.App.Platform;
using Bombinha.App.ViewModels;
using Bombinha.Core.Engine;

namespace Bombinha.App.Views;

[SuppressMessage("Design", "CA1001", Justification = "Os atalhos são liberados no Closing da janela.")]
internal sealed partial class MainWindow : Window
{
    private const uint VkF6 = 0x75;
    private const uint VkF7 = 0x76;
    private const uint VkF8 = 0x77;

    private readonly AppServices _services;
    private MainViewModel? _viewModel;
    private GlobalHotkeys? _hotkeys;

    public MainWindow(AppServices services)
    {
        _services = services;
        InitializeComponent();
        SourceInitialized += OnSourceInitialized;
        Closing += OnClosing;
    }

    public void Attach(MainViewModel viewModel)
    {
        _viewModel = viewModel;
        DataContext = viewModel;
        viewModel.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(MainViewModel.Status))
                PaintStatus(viewModel.Status);
        };
        PaintStatus(viewModel.Status);
    }

    private void OnSourceInitialized(object? sender, EventArgs e)
    {
        var source = (HwndSource)PresentationSource.FromVisual(this);
        _services.SetMainWindowHandle(source.Handle);
        _hotkeys = new GlobalHotkeys(source);
        RegisterHotkey(VkF8, "F8", () => _viewModel?.KillSwitch());
        RegisterHotkey(VkF7, "F7", () => _viewModel?.CycleModeCommand.Execute(null));
        RegisterHotkey(VkF6, "F6", () => _viewModel?.NewMatchCommand.Execute(null));
    }

    private void RegisterHotkey(uint vk, string name, Action action)
    {
        if (_hotkeys!.Register(vk, action) is { } error)
            _services.Log.Warning($"Atalho global {name} indisponível (outro programa já o usa): {error}");
    }

    private void OnClosing(object? sender, CancelEventArgs e)
    {
        if (_services.Engine.IsRunning)
        {
            _services.Engine.Stop();
            if (!_services.Engine.WaitForExit(TimeSpan.FromSeconds(2)))
                _services.Log.Warning("O motor demorou para parar; encerrando assim mesmo.");
        }
        _hotkeys?.Dispose();
    }

    private void PaintStatus(EngineStatus status)
    {
        var brush = (Brush)FindResource(status switch
        {
            EngineStatus.Stopped => "Danger",
            EngineStatus.Faulted => "Warn",
            EngineStatus.Loading => "TextDim",
            _ => "Success",
        });
        StatusDot.Fill = brush;
        StatusLabel.Foreground = brush;
    }
}
