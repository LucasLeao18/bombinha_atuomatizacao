using System.Collections.Specialized;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;
using Bombinha.App.ViewModels;

namespace Bombinha.App.Views;

public partial class ConsoleView : UserControl
{
    private ConsoleViewModel? _console;
    private bool _scrollQueued;

    public ConsoleView()
    {
        InitializeComponent();
        Lines.DataContextChanged += OnConsoleChanged;
    }

    private void OnConsoleChanged(object sender, DependencyPropertyChangedEventArgs e)
    {
        if (_console is not null)
            _console.Lines.CollectionChanged -= OnLinesChanged;
        _console = e.NewValue as ConsoleViewModel;
        if (_console is not null)
            _console.Lines.CollectionChanged += OnLinesChanged;
    }

    private void OnLinesChanged(object? sender, NotifyCollectionChangedEventArgs e)
    {
        // Rolar dentro do próprio evento força um layout antes de o ListBox processar o item novo
        // ("ItemsControl inconsistente"). Adia para depois, uma vez por lote de linhas.
        if (e.Action != NotifyCollectionChangedAction.Add || _console is not { AutoScroll: true } || _scrollQueued)
            return;
        _scrollQueued = true;
        Dispatcher.BeginInvoke(DispatcherPriority.Background, () =>
        {
            _scrollQueued = false;
            if (Lines.Items.Count > 0)
                Lines.ScrollIntoView(Lines.Items[^1]);
        });
    }
}
