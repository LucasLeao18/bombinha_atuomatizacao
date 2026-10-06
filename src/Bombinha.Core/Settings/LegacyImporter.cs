using System.Text.Json;
using Bombinha.Core.Common;

namespace Bombinha.Core.Settings;

public sealed record LegacyImportResult(AppSettings Settings, IReadOnlyList<string> Notes, bool ImportedConfig, bool ImportedPositions);

/// <summary>
/// Converte config.json + posicoes.json da versão em Python para o formato atual.
/// Chaves ausentes ficam com o padrão; valores inválidos são ignorados com uma nota.
/// </summary>
public static class LegacyImporter
{
    public const string ConfigFileName = "config.json";
    public const string PositionsFileName = "posicoes.json";
    public const string RejectedFileName = "rejeitadas.txt";
    public const string BlacklistFileName = "blacklist.txt";

    /// <summary>Indica se a pasta parece conter dados da versão antiga.</summary>
    public static bool LooksLikeLegacyFolder(string folder)
    {
        string config = Path.Combine(folder, ConfigFileName);
        if (!File.Exists(config))
            return File.Exists(Path.Combine(folder, PositionsFileName));
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(config));
            return doc.RootElement.ValueKind == JsonValueKind.Object
                   && doc.RootElement.TryGetProperty("humanizar", out _);
        }
        catch (JsonException)
        {
            return false;
        }
    }

    public static LegacyImportResult ImportFolder(string folder)
    {
        string configPath = Path.Combine(folder, ConfigFileName);
        string positionsPath = Path.Combine(folder, PositionsFileName);
        return Import(
            File.Exists(configPath) ? File.ReadAllText(configPath) : null,
            File.Exists(positionsPath) ? File.ReadAllText(positionsPath) : null,
            folder);
    }

    public static LegacyImportResult Import(string? configJson, string? positionsJson, string legacyFolder)
    {
        var settings = new AppSettings();
        var notes = new List<string>();
        bool importedConfig = TryParse(configJson, ConfigFileName, notes) is { } config
                              && ApplyConfig(config, settings, legacyFolder, notes);
        bool importedPositions = TryParse(positionsJson, PositionsFileName, notes) is { } positions
                                 && ApplyPositions(positions, settings.Calibration, notes);
        settings.Normalize();
        return new(settings, notes, importedConfig, importedPositions);
    }

    private static JsonElement? TryParse(string? json, string name, List<string> notes)
    {
        if (json is null)
            return null;
        if (string.IsNullOrWhiteSpace(json))
        {
            notes.Add($"{name} está vazio; ignorado.");
            return null;
        }
        try
        {
            using var doc = JsonDocument.Parse(json, new JsonDocumentOptions { AllowTrailingCommas = true });
            if (doc.RootElement.ValueKind != JsonValueKind.Object)
            {
                notes.Add($"{name} não contém um objeto JSON; ignorado.");
                return null;
            }
            return doc.RootElement.Clone();
        }
        catch (JsonException ex)
        {
            notes.Add($"{name} é inválido ({ex.Message}); ignorado.");
            return null;
        }
    }

    private static bool ApplyConfig(JsonElement c, AppSettings s, string folder, List<string> notes)
    {
        var r = new Reader(c, notes);

        r.Int("delay_ciclo_ms", v => s.Timing.CycleDelayMs = v);
        r.Int("delay_pos_copiar_ms", v => s.Timing.SettleAfterSelectMs = v);
        r.Int("delay_antes_digitar_ms", v => s.Timing.BeforeTypingMs = v);
        r.Double("limite_tempo_round_s", v => s.Timing.RoundTimeLimitSeconds = v);

        r.String("caminho_dicionario", v => s.General.DictionaryPath = ResolveAsset(v, "acento.txt", folder));
        r.Bool("modo_teste", v => s.General.TestMode = v);

        r.String("template_chatbox", v => s.Detection.TemplatePath = ResolveAsset(v, "chatbox.png", folder));
        r.Double("template_threshold", v => s.Detection.TemplateThreshold = v);
        r.Double("turn_bar_threshold", v => s.Detection.TurnBarThreshold = v);
        r.Enum("turn_bar_metodo", v => s.Detection.TurnBarMethod = v,
            ("pixel", TurnBarMethod.Pixel), ("cor", TurnBarMethod.Color), ("hibrido", TurnBarMethod.Hybrid));

        r.Enum("modo", v => s.Mode = v,
            ("longa", GameMode.LongWords), ("curta", GameMode.ShortWords), ("qualquer", GameMode.Any), ("alfabeto", GameMode.Alphabet));

        r.Enum("metodo_captura", v => s.Capture.Method = v,
            ("clipboard", SyllableCaptureMethod.Clipboard), ("ocr", SyllableCaptureMethod.Ocr));
        r.Bool("preservar_clipboard", v => s.Capture.PreserveClipboard = v);
        r.Enum("clique_captura", v => s.Capture.ClickSelection = v,
            ("duplo", ClickSelection.DoubleClick), ("triplo", ClickSelection.TripleClick), ("auto", ClickSelection.Auto));
        r.Int("tentativas_captura", v => s.Capture.Attempts = v);

        r.Bool("verificar_envio", v => s.Verification.VerifySubmission = v);
        r.Int("delay_verificacao_ms", v => s.Verification.VerificationDelayMs = v);
        r.Int("max_tentativas_rodada", v => s.Verification.MaxAttemptsPerRound = v);
        r.Bool("aprender_rejeitadas", v => s.Verification.LearnRejected = v);
        r.Bool("auto_nova_partida", v => s.Verification.AutoNewMatch = v);
        r.Double("inatividade_nova_partida_s", v => s.Verification.InactivityNewMatchSeconds = v);

        r.Int("mostrar_top_n", v =>
        {
            s.Selection.TopN = Math.Max(1, v);
            s.Selection.ShowTopInConsole = v > 0;
        });
        r.Bool("penaliza_repetidas", v => s.Selection.PenalizeRepeats = v);
        r.Double("penalizacao_repetida", v => s.Selection.RepeatPenalty = v);
        r.Int("cooldown_repeticao", v => s.Selection.RepeatCooldown = v);
        r.Bool("bloquear_usadas_na_partida", v => s.Selection.BlockUsedInMatch = v);
        r.Bool("preferir_prefixo", v => s.Selection.PreferPrefix = v);
        r.Double("peso_prefixo", v => s.Selection.PrefixWeight = v);
        r.Bool("alfabeto_hibrido", v => s.Selection.HuntNewLetters = v);
        r.Double("peso_letras_novas", v => s.Selection.NewLettersWeight = v);

        r.Bool("dpi_aware", v =>
        {
            if (!v)
                notes.Add("A versão nova é sempre ciente de DPI. Se a escala do Windows não for 100%, recalibre as posições.");
        });
        r.Bool("salvar_log", _ => { });

        if (c.TryGetProperty("humanizar", out var hum) && hum.ValueKind == JsonValueKind.Object)
            ApplyHumanization(new Reader(hum, notes), s.Humanization);

        return true;
    }

    private static void ApplyHumanization(Reader r, HumanizationSettings h)
    {
        r.Double("chance_erro", v => h.TypoChance = v);
        r.Double("variacao_delay", v => h.DelayJitterSeconds = v);
        r.Bool("inserir_numeros", v => h.InsertNumbers = v);
        r.Int("numeros_rodadas", v => h.NumberRounds = v);
        r.Double("hesitacao_enter_min", v => h.EnterHesitationMinSeconds = v);
        r.Double("hesitacao_enter_max", v => h.EnterHesitationMaxSeconds = v);
        r.Int("pausa_cada", v => h.PauseEvery = v);
        r.Double("pausa_min", v => h.PauseMinSeconds = v);
        r.Double("pausa_max", v => h.PauseMaxSeconds = v);
        r.Enum("perfil", v => h.Profile = v,
            ("nenhum", TypingSpeedProfile.None), ("rapida", TypingSpeedProfile.Fast),
            ("aleatoria", TypingSpeedProfile.Random), ("gradual", TypingSpeedProfile.Gradual));
        r.Int("delay_entre_letras_ms", v => h.LetterDelayMs = v);
        r.Double("chance_falha_proposital", v => h.DeliberateFailChance = v);
        r.Double("chance_erro_enter", v => h.WrongEnterChance = v);
        r.Double("chance_frase_engracada", v => h.JokePhraseChance = v);
        r.Double("chance_ensaio_palavra", v => h.RehearsalChance = v);
        r.Bool("pensar_3letras", v => h.ThinkAfterThree = v);
        r.Int("pensar_3letras_pausa_ms", v => h.ThinkAfterThreeMs = v);
        r.StringList("frases_customizadas", v => h.CustomPhrases = v);
    }

    private static bool ApplyPositions(JsonElement p, Calibration cal, List<string> notes)
    {
        var r = new Reader(p, notes);
        r.Ints("letras", 2, v => cal.SyllablePoint = new ScreenPoint(v[0], v[1]));
        r.Ints("chatbox", 2, v => cal.ChatPoint = new ScreenPoint(v[0], v[1]));
        r.Ints("turn_bar", 4, v => cal.TurnBar = new ScreenRect(v[0], v[1], v[2], v[3]));
        r.Ints("letras_rect", 4, v => cal.SyllableRegion = new ScreenRect(v[0], v[1], v[2], v[3]));
        r.Ints("resolucao", 2, v => cal.CalibratedDesktop = new ScreenSize(v[0], v[1]));
        return true;
    }

    /// <summary>
    /// O padrão antigo ("acento.txt"/"chatbox.png" relativo) vira o recurso embutido; outros caminhos
    /// relativos são resolvidos contra a pasta antiga, já que dependiam do diretório de execução.
    /// </summary>
    private static string? ResolveAsset(string value, string defaultFileName, string folder)
    {
        if (string.IsNullOrWhiteSpace(value))
            return null;
        if (!Path.IsPathRooted(value)
            && string.Equals(Path.GetFileName(value), defaultFileName, StringComparison.OrdinalIgnoreCase))
            return null;
        return Path.IsPathRooted(value) ? value : Path.GetFullPath(Path.Combine(folder, value));
    }

    private readonly struct Reader(JsonElement obj, List<string> notes)
    {
        private bool TryGet(string key, JsonValueKind kind, out JsonElement value)
        {
            if (!obj.TryGetProperty(key, out value) || value.ValueKind == JsonValueKind.Null)
                return false;
            if (value.ValueKind == kind
                || (kind == JsonValueKind.True && value.ValueKind == JsonValueKind.False))
                return true;
            notes.Add($"'{key}' tem um tipo inesperado ({value.ValueKind}); mantido o padrão.");
            return false;
        }

        public void Int(string key, Action<int> set)
        {
            if (TryGet(key, JsonValueKind.Number, out var v))
                set((int)Math.Round(v.GetDouble()));
        }

        public void Double(string key, Action<double> set)
        {
            if (TryGet(key, JsonValueKind.Number, out var v))
                set(v.GetDouble());
        }

        public void Bool(string key, Action<bool> set)
        {
            if (TryGet(key, JsonValueKind.True, out var v))
                set(v.GetBoolean());
        }

        public void String(string key, Action<string> set)
        {
            if (TryGet(key, JsonValueKind.String, out var v))
                set(v.GetString() ?? "");
        }

        public void Enum<T>(string key, Action<T> set, params (string Legacy, T Value)[] map)
        {
            if (!TryGet(key, JsonValueKind.String, out var v))
                return;
            string raw = v.GetString() ?? "";
            foreach (var (legacy, value) in map)
            {
                if (string.Equals(raw, legacy, StringComparison.OrdinalIgnoreCase))
                {
                    set(value);
                    return;
                }
            }
            notes.Add($"'{key}' = '{raw}' não é reconhecido; mantido o padrão.");
        }

        public void StringList(string key, Action<List<string>> set)
        {
            if (TryGet(key, JsonValueKind.Array, out var v))
                set(v.EnumerateArray().Where(e => e.ValueKind == JsonValueKind.String).Select(e => e.GetString()!).ToList());
        }

        public void Ints(string key, int count, Action<int[]> set)
        {
            if (!TryGet(key, JsonValueKind.Array, out var v))
                return;
            var values = v.EnumerateArray().Where(e => e.ValueKind == JsonValueKind.Number)
                .Select(e => (int)Math.Round(e.GetDouble())).ToArray();
            if (values.Length == count)
                set(values);
            else
                notes.Add($"'{key}' deveria ter {count} números; ignorado.");
        }
    }
}
