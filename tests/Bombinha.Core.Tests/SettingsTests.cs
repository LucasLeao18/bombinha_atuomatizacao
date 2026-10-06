using Bombinha.Core.Common;
using Bombinha.Core.Settings;

namespace Bombinha.Core.Tests;

public sealed class TempDir : IDisposable
{
    public string Path { get; } = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "bombinha-tests-" + Guid.NewGuid().ToString("N"));

    public TempDir() => Directory.CreateDirectory(Path);

    public string File(string name) => System.IO.Path.Combine(Path, name);

    public void Dispose() => Directory.Delete(Path, recursive: true);
}

public class SettingsTests
{
    [Fact]
    public void Padroes_sobrevivem_a_ida_e_volta_em_json()
    {
        var original = new AppSettings();
        original.Humanization.CustomPhrases = ["oi"];
        original.Calibration.SyllableRegion = new ScreenRect(1, 2, 3, 4);
        string json = SettingsSerializer.Serialize(original);
        Assert.Equal(json, SettingsSerializer.Serialize(SettingsSerializer.Deserialize(json)));
        Assert.Contains("\"mode\": \"Any\"", json, StringComparison.Ordinal); // enums legíveis
    }

    [Fact]
    public void Clone_e_independente()
    {
        var a = new AppSettings();
        var b = a.Clone();
        b.Humanization.CustomPhrases.Add("x");
        b.Timing.CycleDelayMs = 999;
        Assert.Empty(a.Humanization.CustomPhrases);
        Assert.Equal(200, a.Timing.CycleDelayMs);
    }

    [Fact]
    public void Normalizacao_corrige_valores_fora_de_faixa()
    {
        var s = SettingsSerializer.Deserialize("""
            {
              "mode": "alphabet",
              "timing": { "cycleDelayMs": 1, "roundTimeLimitSeconds": 99 },
              "humanization": { "pauseMinSeconds": 0.5, "pauseMaxSeconds": 0.1, "typoChance": 7, "customPhrases": [" a ", "", "  "] },
              "selection": { "topN": 0 },
              "general": { "dictionaryPath": "   " }
            }
            """);
        Assert.Equal(GameMode.Alphabet, s.Mode);
        Assert.Equal(50, s.Timing.CycleDelayMs);
        Assert.Equal(15.0, s.Timing.RoundTimeLimitSeconds);
        Assert.Equal((0.1, 0.5), (s.Humanization.PauseMinSeconds, s.Humanization.PauseMaxSeconds));
        Assert.Equal(0.5, s.Humanization.TypoChance);
        Assert.Equal(["a"], s.Humanization.CustomPhrases);
        Assert.Equal(1, s.Selection.TopN);
        Assert.Null(s.General.DictionaryPath);
    }

    [Fact]
    public void Json_com_secoes_nulas_vira_padrao() =>
        Assert.NotNull(SettingsSerializer.Deserialize("""{ "timing": null, "humanization": null }""").Timing);

    [Fact]
    public void Store_salva_e_carrega()
    {
        using var dir = new TempDir();
        var store = new SettingsStore(dir.File("settings.json"));
        Assert.Equal(SettingsLoadStatus.Missing, store.Load().Status);

        var s = new AppSettings { Mode = GameMode.ShortWords };
        store.Save(s);
        var loaded = store.Load();
        Assert.Equal(SettingsLoadStatus.Loaded, loaded.Status);
        Assert.Equal(GameMode.ShortWords, loaded.Settings.Mode);
        Assert.False(File.Exists(dir.File("settings.json.tmp")));
    }

    [Theory]
    [InlineData("")]
    [InlineData("{ isso não é json")]
    public void Arquivo_corrompido_vira_backup_e_usa_padroes(string content)
    {
        using var dir = new TempDir();
        File.WriteAllText(dir.File("settings.json"), content);
        var result = new SettingsStore(dir.File("settings.json")).Load();
        Assert.Equal(SettingsLoadStatus.Corrupt, result.Status);
        Assert.False(File.Exists(dir.File("settings.json")));
        Assert.Single(Directory.GetFiles(dir.Path, "settings.json.corrompido-*"));
    }

    [Fact]
    public void Presets_ajustam_humanizacao_e_orcamento()
    {
        var s = new AppSettings();
        HumanizationPreset.All.Single(p => p.Name == "Agressivo").ApplyTo(s);
        Assert.Equal(TypingSpeedProfile.Fast, s.Humanization.Profile);
        Assert.Equal(0, s.Humanization.JokePhraseChance);
        Assert.Equal(2.0, s.Timing.RoundTimeLimitSeconds);
    }

    [Fact]
    public void Geometria_retangulo_a_partir_de_cantos()
    {
        Assert.Equal(new ScreenRect(10, 20, 30, 40), ScreenRect.FromCorners(new(40, 60), new(10, 20)));
        Assert.Equal(new ScreenRect(5, 5, 1, 1), ScreenRect.FromCorners(new(5, 5), new(5, 5)));
        Assert.True(new ScreenRect(0, 0, 10, 10).Intersect(new ScreenRect(20, 20, 5, 5)).IsEmpty);
    }
}

public class LegacyImporterTests
{
    private static string RepoFile(params string[] parts)
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !File.Exists(Path.Combine(dir.FullName, "Bombinha.slnx")))
            dir = dir.Parent;
        Assert.NotNull(dir);
        return Path.Combine([dir.FullName, .. parts]);
    }

    [Fact]
    public void Importa_o_config_real_da_versao_python()
    {
        string folder = Path.GetDirectoryName(RepoFile("legacy", "python", "config.json"))!;
        var result = LegacyImporter.ImportFolder(folder);
        var s = result.Settings;

        Assert.True(result.ImportedConfig);
        Assert.Equal(GameMode.ShortWords, s.Mode);                 // "curta"
        Assert.Equal(200, s.Timing.CycleDelayMs);
        Assert.Equal(300, s.Timing.SettleAfterSelectMs);
        Assert.Equal(2.0, s.Timing.RoundTimeLimitSeconds);
        Assert.Equal(0.85, s.Detection.TurnBarThreshold);
        Assert.Null(s.General.DictionaryPath);                    // acento.txt → dicionário embutido
        Assert.Null(s.Detection.TemplatePath);                    // chatbox.png → template embutido
        Assert.Equal(5, s.Selection.TopN);
        Assert.True(s.Selection.ShowTopInConsole);
        Assert.Equal(TypingSpeedProfile.Random, s.Humanization.Profile);
        Assert.Equal(0.014534883720930232, s.Humanization.TypoChance, 12);
        Assert.Equal(5, s.Humanization.LetterDelayMs);
        Assert.Equal(5, s.Humanization.CustomPhrases.Count);
        Assert.True(s.Humanization.ThinkAfterThree);

        // posicoes.json antigo só tem letras e chatbox; o resto fica com o padrão.
        Assert.True(result.ImportedPositions);
        Assert.Equal(new ScreenPoint(784, 574), s.Calibration.SyllablePoint);
        Assert.Equal(new ScreenPoint(791, 997), s.Calibration.ChatPoint);
        Assert.Equal(new AppSettings().Calibration.TurnBar, s.Calibration.TurnBar);
        Assert.Empty(result.Notes);
    }

    [Theory]
    [InlineData("")]
    [InlineData("{ quebrado")]
    public void Posicoes_vazias_ou_corrompidas_viram_nota(string content)
    {
        var result = LegacyImporter.Import(null, content, ".");
        Assert.False(result.ImportedPositions);
        Assert.Single(result.Notes);
        Assert.Equal(new AppSettings().Calibration.ChatPoint, result.Settings.Calibration.ChatPoint);
    }

    [Fact]
    public void Importa_posicoes()
    {
        var result = LegacyImporter.Import(null, """
            {"letras": [10, 20], "chatbox": [30, 40], "turn_bar": [1, 2, 3, 4], "letras_rect": null, "resolucao": [1920, 1080]}
            """, ".");
        var c = result.Settings.Calibration;
        Assert.True(result.ImportedPositions);
        Assert.Equal(new ScreenPoint(10, 20), c.SyllablePoint);
        Assert.Equal(new ScreenPoint(30, 40), c.ChatPoint);
        Assert.Equal(new ScreenRect(1, 2, 3, 4), c.TurnBar);
        Assert.Null(c.SyllableRegion);
        Assert.Equal(new ScreenSize(1920, 1080), c.CalibratedDesktop);
    }

    [Fact]
    public void Valores_invalidos_viram_notas_e_mantem_padrao()
    {
        var result = LegacyImporter.Import("""
            {"modo": "turbo", "delay_ciclo_ms": "rapido", "mostrar_top_n": 0, "humanizar": {"perfil": "gradual"}}
            """, null, ".");
        Assert.Equal(GameMode.Any, result.Settings.Mode);
        Assert.Equal(200, result.Settings.Timing.CycleDelayMs);
        Assert.False(result.Settings.Selection.ShowTopInConsole);
        Assert.Equal(1, result.Settings.Selection.TopN);
        Assert.Equal(TypingSpeedProfile.Gradual, result.Settings.Humanization.Profile);
        Assert.Equal(2, result.Notes.Count);
    }

    [Fact]
    public void Caminho_personalizado_relativo_e_resolvido_contra_a_pasta_antiga()
    {
        var result = LegacyImporter.Import("""{"caminho_dicionario": "meu_dic.txt"}""", null, @"C:\jogo");
        Assert.Equal(@"C:\jogo\meu_dic.txt", result.Settings.General.DictionaryPath);
    }

    [Fact]
    public void Reconhece_pasta_da_versao_antiga()
    {
        Assert.True(LegacyImporter.LooksLikeLegacyFolder(Path.GetDirectoryName(RepoFile("legacy", "python", "config.json"))!));
        using var dir = new TempDir();
        Assert.False(LegacyImporter.LooksLikeLegacyFolder(dir.Path));
        File.WriteAllText(dir.File("config.json"), """{"outro": "app"}""");
        Assert.False(LegacyImporter.LooksLikeLegacyFolder(dir.Path));
    }
}
