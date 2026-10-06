using System.Diagnostics;
using System.IO;
using System.Text;
using Bombinha.App.Infrastructure;
using Bombinha.App.Platform;
using Bombinha.App.Ui;
using Bombinha.Core.Capture;
using Bombinha.Core.Common;
using Bombinha.Core.Detection;
using Bombinha.Core.Imaging;
using Bombinha.Core.Logging;
using Bombinha.Core.Settings;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Microsoft.Win32;

namespace Bombinha.App.ViewModels;

/// <summary>
/// Edição das configurações. A tela trabalha sobre uma cópia (<see cref="Editing"/>); nada chega
/// ao motor até "Aplicar e salvar" (ou Iniciar). Calibrações são gravadas na hora.
/// </summary>
internal sealed partial class SettingsViewModel : ObservableObject
{
    private readonly AppServices _app;
    private readonly ScreenPicker _picker;
    private readonly Func<Task> _reloadDictionary;
    private readonly Logger _log;

    [ObservableProperty]
    private AppSettings _editing;

    [ObservableProperty]
    private string _detectionResult = "Use \"Testar detecção\" com o jogo aberto para ver o que o bot enxerga.";

    [ObservableProperty]
    private string _diagnosticText = "";

    [ObservableProperty]
    private DiagnosticSeverity _diagnosticSeverity;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(TestDetectionCommand))]
    private bool _isTestingDetection;

    public SettingsViewModel(AppServices app, ScreenPicker picker, Func<Task> reloadDictionary)
    {
        _app = app;
        _picker = picker;
        _reloadDictionary = reloadDictionary;
        _log = app.Log.For("Setup");
        _editing = app.Settings.Current.Clone();
    }

    public string OcrStatus => _app.Ocr.IsAvailable
        ? $"OCR do Windows disponível ({_app.Ocr.Language})."
        : $"OCR indisponível: {_app.Ocr.UnavailableReason}.";

    public string SyllablePointText => Editing.Calibration.SyllablePoint.ToString();
    public string ChatPointText => Editing.Calibration.ChatPoint.ToString();
    public string TurnBarText => Editing.Calibration.TurnBar.ToString();
    public string SyllableRegionText => Editing.Calibration.SyllableRegion?.ToString() ?? "não calibrada";
    public string DataFolder => _app.Paths.DataDirectory;

    partial void OnEditingChanged(AppSettings value) => RaiseCalibrationTexts();

    /// <summary>Valida e grava a edição atual. Retorna false (já avisando o usuário) se falhar.</summary>
    public bool Save()
    {
        try
        {
            var settings = Editing.Clone().Normalize();
            _app.Settings.Save(settings);
            Editing = settings.Clone();
            _log.Success("Configurações salvas.");
            return true;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            _log.Error($"Falha ao salvar as configurações em {_app.Settings.FilePath}.", ex);
            Dialogs.Error("Não foi possível salvar", ex.Message);
            return false;
        }
    }

    /// <summary>Reflete alterações feitas fora desta tela (modo pelo F7, calibração).</summary>
    public void SyncFromCurrent(Action<AppSettings> apply)
    {
        var copy = Editing.Clone();
        apply(copy);
        Editing = copy;
    }

    [RelayCommand]
    private void ApplyAndSave() => Save();

    [RelayCommand]
    private void Revert()
    {
        Editing = _app.Settings.Current.Clone();
        _log.Info("Alterações não salvas descartadas.");
    }

    [RelayCommand]
    private void ApplyPreset(HumanizationPreset preset)
    {
        var copy = Editing.Clone();
        preset.ApplyTo(copy);
        Editing = copy;
        _log.Info($"Perfil '{preset.Name}' aplicado. Clique em Aplicar e salvar para gravar.");
    }

    // ------------------------------------------------------------------ arquivos

    [RelayCommand]
    private void BrowseDictionary()
    {
        var dialog = new OpenFileDialog { Title = "Selecionar dicionário", Filter = "Texto (*.txt)|*.txt|Todos (*.*)|*.*" };
        if (dialog.ShowDialog() == true)
            SyncFromCurrent(s => s.General.DictionaryPath = dialog.FileName);
    }

    [RelayCommand]
    private void UseEmbeddedDictionary() => SyncFromCurrent(s => s.General.DictionaryPath = null);

    [RelayCommand]
    private void BrowseTemplate()
    {
        var dialog = new OpenFileDialog { Title = "Selecionar imagem do campo de digitação", Filter = "Imagens (*.png)|*.png|Todos (*.*)|*.*" };
        if (dialog.ShowDialog() == true)
            SyncFromCurrent(s => s.Detection.TemplatePath = dialog.FileName);
    }

    [RelayCommand]
    private void UseEmbeddedTemplate() => SyncFromCurrent(s => s.Detection.TemplatePath = null);

    [RelayCommand]
    private async Task CaptureTemplate()
    {
        var rect = await _picker.PickRectAsync("Na SUA vez, selecione a borda esquerda do campo de digitação do jogo");
        if (rect is not { } r)
            return;
        await Task.Delay(150); // espera a camada de captura sumir da tela
        try
        {
            var image = _app.Screen.Capture(r);
            new TurnDetector(_app.Screen, _log).SetTemplate(image); // rejeita imagem uniforme
            ImageFiles.SavePng(image, _app.Paths.CapturedTemplateFile);
            SyncFromCurrent(s => s.Detection.TemplatePath = _app.Paths.CapturedTemplateFile);
            _log.Success($"Template capturado ({r.Width}x{r.Height}). Clique em Aplicar e salvar para usá-lo.");
        }
        catch (Exception ex) when (ex is IOException or ArgumentException or ScreenCaptureException)
        {
            _log.Error("Não foi possível capturar o template.", ex);
            Dialogs.Error("Captura do template", ex.Message);
        }
    }

    // ------------------------------------------------------------------ calibração

    [RelayCommand]
    private async Task CaptureSyllablePoint()
    {
        if (await _picker.PickPointAsync("Clique onde as LETRAS da bomba aparecem") is { } p)
            SaveCalibration(c => c.SyllablePoint = p, $"Posição das letras definida: {p}");
    }

    [RelayCommand]
    private async Task CaptureChatPoint()
    {
        if (await _picker.PickPointAsync("Clique dentro do CAMPO DE DIGITAÇÃO do jogo") is { } p)
            SaveCalibration(c => c.ChatPoint = p, $"Campo de digitação definido: {p}");
    }

    [RelayCommand]
    private async Task CaptureTurnBar()
    {
        if (await _picker.PickRectAsync("Selecione a BARRA DE TURNO") is { } r)
        {
            SaveCalibration(c => c.TurnBar = r, $"Barra de turno definida: {r}");
            _app.Detector.ResetReference();
        }
    }

    [RelayCommand]
    private async Task CaptureSyllableRegion()
    {
        if (await _picker.PickRectAsync("Selecione a região da SÍLABA (para o OCR)") is { } r)
            SaveCalibration(c => c.SyllableRegion = r, $"Região da sílaba (OCR) definida: {r}");
    }

    private void SaveCalibration(Action<Calibration> change, string message)
    {
        var desktop = GdiScreenCapture.VirtualDesktop();
        void Apply(AppSettings s)
        {
            change(s.Calibration);
            s.Calibration.CalibratedDesktop = new ScreenSize(desktop.Width, desktop.Height);
        }

        try
        {
            _app.Settings.Update(Apply);
            SyncFromCurrent(Apply);
            _log.Success(message);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            _log.Error("Falha ao gravar a calibração.", ex);
            Dialogs.Error("Não foi possível salvar", ex.Message);
        }
    }

    private void RaiseCalibrationTexts()
    {
        OnPropertyChanged(nameof(SyllablePointText));
        OnPropertyChanged(nameof(ChatPointText));
        OnPropertyChanged(nameof(TurnBarText));
        OnPropertyChanged(nameof(SyllableRegionText));
    }

    // ------------------------------------------------------------------ diagnóstico

    private bool CanTestDetection() => !IsTestingDetection;

    /// <summary>Roda uma detecção completa (sem clicar nem digitar) e mostra o que o bot enxerga.</summary>
    [RelayCommand(CanExecute = nameof(CanTestDetection))]
    private async Task TestDetection()
    {
        IsTestingDetection = true;
        var settings = Editing.Clone().Normalize();
        try
        {
            DetectionResult = await Task.Run(() => RunDetectionTest(settings));
            _log.Info("Teste de detecção:" + Environment.NewLine + DetectionResult);
        }
        catch (Exception ex) when (ex is IOException or ArgumentException or ScreenCaptureException or InvalidOperationException)
        {
            DetectionResult = $"Falhou: {ex.Message}";
            _log.Error("Teste de detecção falhou.", ex);
        }
        finally
        {
            IsTestingDetection = false;
        }
    }

    private string RunDetectionTest(AppSettings s)
    {
        var sb = new StringBuilder();
        var detector = new TurnDetector(_app.Screen, _log);
        detector.SetTemplate(AppServices.LoadTemplate(s));

        var sw = Stopwatch.StartNew();
        var probe = detector.ProbeChatbox(s);
        sw.Stop();
        sb.AppendLine(probe.Visible
            ? $"✔ Campo de digitação VISÍVEL em {probe.Location} — similaridade {probe.Score:F3} (limite {s.Detection.TemplateThreshold:F2})."
            : $"✘ Campo de digitação não encontrado — melhor similaridade {probe.Score:F3} (limite {s.Detection.TemplateThreshold:F2}). " +
              "Normal se não for a sua vez.");
        sb.AppendLine($"   Busca em {probe.SearchArea} levou {sw.ElapsedMilliseconds} ms.");

        if (s.Detection.UseTurnBar)
        {
            var bar = detector.CaptureTurnBar(s.Calibration);
            sb.AppendLine(bar is null ? "✘ Barra de turno não calibrada." : $"✔ Barra de turno capturada ({bar.Width}x{bar.Height}).");
        }

        if (s.Capture.Method == SyllableCaptureMethod.Ocr)
        {
            string? raw = new OcrSyllableReader(_app.Screen, _app.Ocr, _log).Read(s);
            sb.AppendLine(raw is null
                ? "✘ OCR não pôde ser usado (veja o console)."
                : $"OCR leu \"{raw.Trim()}\" → sílaba \"{SyllableText.Normalize(raw)}\".");
        }
        else
        {
            sb.AppendLine("A leitura por clique + Ctrl+C não é testada aqui (ela clicaria no jogo).");
        }
        return sb.ToString().TrimEnd();
    }

    [RelayCommand]
    private void RunDiagnostics()
    {
        var report = DisplayDiagnostics.Run(_app.Settings.Current);
        DiagnosticText = report.Text;
        DiagnosticSeverity = report.Severity;
        var level = report.Severity == DiagnosticSeverity.Ok ? LogLevel.Info : LogLevel.Warning;
        _log.Write(level, "Diagnóstico de tela: " + report.Text.Replace(Environment.NewLine, " ", StringComparison.Ordinal));
    }

    // ------------------------------------------------------------------ dados

    [RelayCommand]
    private async Task ImportLegacy()
    {
        var dialog = new OpenFolderDialog { Title = "Pasta da versão antiga (com config.json / posicoes.json)" };
        if (dialog.ShowDialog() != true)
            return;
        if (!LegacyImporter.LooksLikeLegacyFolder(dialog.FolderName))
        {
            Dialogs.Error("Importar versão antiga", "Não encontrei config.json ou posicoes.json da versão antiga nessa pasta.");
            return;
        }
        try
        {
            _app.Migration.Import(dialog.FolderName);
            Editing = _app.Settings.Current.Clone();
            await _reloadDictionary();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            _log.Error("Falha ao importar a versão antiga.", ex);
            Dialogs.Error("Importar versão antiga", ex.Message);
        }
    }

    [RelayCommand]
    private void OpenDataFolder() => OpenFolder(_app.Paths.DataDirectory);

    [RelayCommand]
    private void OpenLogFolder() => OpenFolder(_app.Paths.LogDirectory);

    private void OpenFolder(string path)
    {
        try
        {
            // Caminho controlado pelo app (AppData); abre no Explorer sem passar por shell de comando.
            Process.Start(new ProcessStartInfo { FileName = path, UseShellExecute = true })?.Dispose();
        }
        catch (System.ComponentModel.Win32Exception ex)
        {
            _log.Warning($"Não foi possível abrir {path}.", ex);
        }
    }
}
