using System.Diagnostics.CodeAnalysis;
using System.Windows;
using Bombinha.App.Ui;
using Bombinha.App.ViewModels;
using Bombinha.App.Views;
using Bombinha.Core.Settings;

namespace Bombinha.App;

[SuppressMessage("Design", "CA1001", Justification = "Recursos liberados em OnExit, o fim do ciclo de vida do Application.")]
public partial class App : Application
{
    // Uma instância por sessão de usuário: duas cópias brigariam pelo teclado e pelos atalhos globais.
    private const string SingleInstanceName = @"Local\Bombinha.App.SingleInstance";

    private Mutex? _singleInstance;
    private AppServices? _services;
    private DateTime _lastErrorDialog = DateTime.MinValue;
    private bool _showingErrorDialog;

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        _singleInstance = new Mutex(initiallyOwned: true, SingleInstanceName, out bool createdNew);
        if (!createdNew)
        {
            MessageBox.Show("O Bombinha já está aberto.", "Bombinha", MessageBoxButton.OK, MessageBoxImage.Information);
            _singleInstance.Dispose();
            _singleInstance = null;
            Shutdown();
            return;
        }

        _services = AppServices.Create(Dispatcher);
        InstallExceptionHandlers(_services);
        _services.Log.Info($"Bombinha {typeof(App).Assembly.GetName().Version?.ToString(3)} iniciado. Dados em {_services.Paths.DataDirectory}");
        LoadSettings(_services);

        var window = new MainWindow(_services);
        MainWindow = window;
        var viewModel = new MainViewModel(_services, new ScreenPicker(window));
        window.Attach(viewModel);
        window.Show();

        _ = viewModel.ReloadDictionaryAsync();
        viewModel.Setup.RunDiagnosticsCommand.Execute(null);
    }

    protected override void OnExit(ExitEventArgs e)
    {
        _services?.Log.Info("Encerrando.");
        _services?.Dispose();
        if (_singleInstance is not null)
        {
            _singleInstance.ReleaseMutex();
            _singleInstance.Dispose();
        }
        base.OnExit(e);
    }

    private static void LoadSettings(AppServices services)
    {
        var result = services.Settings.Load();
        switch (result.Status)
        {
            case SettingsLoadStatus.Missing:
                if (!services.Migration.TryAutoImport())
                    services.Log.Info("Primeira execução: usando configurações padrão. Use Setup › Importar da versão antiga se tiver uma.");
                break;
            case SettingsLoadStatus.Corrupt:
                services.Log.Warning($"settings.json estava corrompido e foi substituído pelos padrões: {result.Detail}");
                break;
        }
    }

    private void InstallExceptionHandlers(AppServices services)
    {
        DispatcherUnhandledException += (_, args) =>
        {
            args.Handled = true;
            services.Log.Critical("Erro não tratado na interface.", args.Exception);
            // Uma caixa de diálogo por vez e no máximo uma a cada 10 s: um erro que se repete
            // (por exemplo, ao exibir o próprio log) não pode empilhar janelas modais.
            if (_showingErrorDialog || DateTime.UtcNow - _lastErrorDialog < TimeSpan.FromSeconds(10))
                return;
            _showingErrorDialog = true;
            try
            {
                MessageBox.Show($"Ocorreu um erro inesperado:\n\n{args.Exception.Message}\n\nDetalhes no log em {services.Paths.LogDirectory}.",
                    "Bombinha", MessageBoxButton.OK, MessageBoxImage.Error);
            }
            finally
            {
                _showingErrorDialog = false;
                _lastErrorDialog = DateTime.UtcNow;
            }
        };
        AppDomain.CurrentDomain.UnhandledException += (_, args) =>
            services.Log.Critical("Erro fatal não tratado.", args.ExceptionObject as Exception);
        TaskScheduler.UnobservedTaskException += (_, args) =>
        {
            services.Log.Error("Erro em tarefa de fundo não observada.", args.Exception);
            args.SetObserved();
        };
    }
}
