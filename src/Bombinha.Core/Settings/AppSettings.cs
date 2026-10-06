using Bombinha.Core.Common;

namespace Bombinha.Core.Settings;

public enum GameMode
{
    /// <summary>Prioriza palavras longas.</summary>
    LongWords,
    /// <summary>Prioriza palavras curtas (mais rápidas de digitar).</summary>
    ShortWords,
    /// <summary>Sem preferência de tamanho.</summary>
    Any,
    /// <summary>Caça as 23 letras úteis para ganhar vida extra.</summary>
    Alphabet,
}

public enum SyllableCaptureMethod
{
    /// <summary>Seleciona a sílaba com clique duplo/triplo e copia com Ctrl+C.</summary>
    Clipboard,
    /// <summary>Lê a sílaba da imagem com o OCR nativo do Windows (sem mouse e sem clipboard).</summary>
    Ocr,
}

public enum ClickSelection
{
    DoubleClick,
    TripleClick,
    /// <summary>Alterna duplo e triplo entre as tentativas.</summary>
    Auto,
}

public enum TurnBarMethod
{
    /// <summary>Diferença média de pixels em tons de cinza.</summary>
    Pixel,
    /// <summary>Correlação de histograma HSV (tolera a barra encolher).</summary>
    Color,
    /// <summary>Média dos dois métodos.</summary>
    Hybrid,
}

public enum TypingSpeedProfile
{
    None,
    Fast,
    Random,
    Gradual,
}

/// <summary>
/// Configuração completa do app. Classes mutáveis para permitir binding direto na UI;
/// o motor sempre recebe um clone, então nunca observa uma edição pela metade.
/// </summary>
public sealed class AppSettings
{
    public const int CurrentVersion = 1;

    public int Version { get; set; } = CurrentVersion;
    public GameMode Mode { get; set; } = GameMode.Any;
    public GeneralSettings General { get; set; } = new();
    public DetectionSettings Detection { get; set; } = new();
    public CaptureSettings Capture { get; set; } = new();
    public VerificationSettings Verification { get; set; } = new();
    public SelectionSettings Selection { get; set; } = new();
    public TimingSettings Timing { get; set; } = new();
    public HumanizationSettings Humanization { get; set; } = new();
    public Calibration Calibration { get; set; } = new();

    public AppSettings Clone() => SettingsSerializer.Clone(this);

    /// <summary>Corrige valores fora de faixa (arquivo editado à mão ou de outra versão).</summary>
    public AppSettings Normalize()
    {
        General ??= new();
        Detection ??= new();
        Capture ??= new();
        Verification ??= new();
        Selection ??= new();
        Timing ??= new();
        Humanization ??= new();
        Calibration ??= new();

        if (!Enum.IsDefined(Mode))
            Mode = GameMode.Any;

        General.Normalize();
        Detection.Normalize();
        Capture.Normalize();
        Verification.Normalize();
        Selection.Normalize();
        Timing.Normalize();
        Humanization.Normalize();
        Version = CurrentVersion;
        return this;
    }

    internal static T ValidEnum<T>(T value, T fallback) where T : struct, Enum =>
        Enum.IsDefined(value) ? value : fallback;
}

public sealed class GeneralSettings
{
    /// <summary>Caminho de um dicionário próprio; vazio usa o dicionário PT-BR embutido.</summary>
    public string? DictionaryPath { get; set; }

    /// <summary>Executa todo o fluxo sem enviar teclas para o jogo.</summary>
    public bool TestMode { get; set; }

    /// <summary>Inclui mensagens DEBUG no console e no arquivo de log.</summary>
    public bool VerboseLog { get; set; }

    public bool AlwaysOnTop { get; set; } = true;

    /// <summary>Enviada quando nenhuma palavra do dicionário contém a sílaba.</summary>
    public string GiveUpPhrase { get; set; } = "fudeu mlk sei nao mamei";

    internal void Normalize()
    {
        DictionaryPath = string.IsNullOrWhiteSpace(DictionaryPath) ? null : DictionaryPath.Trim();
        GiveUpPhrase = (GiveUpPhrase ?? "").Trim();
    }
}

public sealed class DetectionSettings
{
    /// <summary>Imagem do campo de digitação do jogo; vazio usa o template embutido.</summary>
    public string? TemplatePath { get; set; }

    /// <summary>Similaridade mínima (0..1) para considerar o campo de digitação visível.</summary>
    public double TemplateThreshold { get; set; } = 0.80;

    /// <summary>Faixa vertical (px, para cima e para baixo do campo calibrado) onde o template é procurado.</summary>
    public int SearchMarginY { get; set; } = 150;

    /// <summary>Confirma também pela barra de turno antes de cada ENTER e na verificação de aceite.</summary>
    public bool UseTurnBar { get; set; } = true;

    public double TurnBarThreshold { get; set; } = 0.85;

    public TurnBarMethod TurnBarMethod { get; set; } = TurnBarMethod.Pixel;

    internal void Normalize()
    {
        TemplatePath = string.IsNullOrWhiteSpace(TemplatePath) ? null : TemplatePath.Trim();
        TemplateThreshold = Math.Clamp(TemplateThreshold, 0.50, 0.99);
        SearchMarginY = Math.Clamp(SearchMarginY, 40, 600);
        TurnBarThreshold = Math.Clamp(TurnBarThreshold, 0.50, 0.99);
        TurnBarMethod = AppSettings.ValidEnum(TurnBarMethod, TurnBarMethod.Pixel);
    }
}

public sealed class CaptureSettings
{
    public SyllableCaptureMethod Method { get; set; } = SyllableCaptureMethod.Clipboard;

    /// <summary>Devolve à área de transferência o que havia antes da captura.</summary>
    public bool PreserveClipboard { get; set; } = true;

    public ClickSelection ClickSelection { get; set; } = ClickSelection.Auto;

    /// <summary>Quantas vezes repetir clique + Ctrl+C antes de desistir do ciclo.</summary>
    public int Attempts { get; set; } = 3;

    internal void Normalize()
    {
        Method = AppSettings.ValidEnum(Method, SyllableCaptureMethod.Clipboard);
        ClickSelection = AppSettings.ValidEnum(ClickSelection, ClickSelection.Auto);
        Attempts = Math.Clamp(Attempts, 1, 6);
    }
}

public sealed class VerificationSettings
{
    /// <summary>Se ainda for a sua vez depois do ENTER, a palavra foi recusada.</summary>
    public bool VerifySubmission { get; set; } = true;

    public int VerificationDelayMs { get; set; } = 350;

    public int MaxAttemptsPerRound { get; set; } = 3;

    /// <summary>Palavra recusada 2x vai para a lista de rejeitadas e nunca mais é usada.</summary>
    public bool LearnRejected { get; set; } = true;

    /// <summary>Zera o estado da partida após um período sem turnos.</summary>
    public bool AutoNewMatch { get; set; } = true;

    public double InactivityNewMatchSeconds { get; set; } = 60;

    internal void Normalize()
    {
        VerificationDelayMs = Math.Clamp(VerificationDelayMs, 50, 2000);
        MaxAttemptsPerRound = Math.Clamp(MaxAttemptsPerRound, 1, 6);
        InactivityNewMatchSeconds = Math.Clamp(InactivityNewMatchSeconds, 15, 600);
    }
}

public sealed class SelectionSettings
{
    /// <summary>Sorteia (com peso pela pontuação) entre as N melhores candidatas.</summary>
    public int TopN { get; set; } = 5;

    public bool ShowTopInConsole { get; set; } = true;

    public bool PenalizeRepeats { get; set; } = true;

    /// <summary>Fator multiplicativo por uso anterior na sessão.</summary>
    public double RepeatPenalty { get; set; } = 0.85;

    /// <summary>Palavras usadas nas últimas N jogadas têm a pontuação reduzida à metade.</summary>
    public int RepeatCooldown { get; set; } = 5;

    /// <summary>O JKLM recusa qualquer palavra repetida na mesma partida.</summary>
    public bool BlockUsedInMatch { get; set; } = true;

    public bool PreferPrefix { get; set; } = true;

    public double PrefixWeight { get; set; } = 1.25;

    /// <summary>Nos modos normais, favorece letras novas (vida extra) quando sobra tempo.</summary>
    public bool HuntNewLetters { get; set; } = true;

    public double NewLettersWeight { get; set; } = 0.6;

    internal void Normalize()
    {
        TopN = Math.Clamp(TopN, 1, 10);
        RepeatPenalty = Math.Clamp(RepeatPenalty, 0.05, 1.0);
        RepeatCooldown = Math.Clamp(RepeatCooldown, 0, 50);
        PrefixWeight = Math.Clamp(PrefixWeight, 1.0, 3.0);
        NewLettersWeight = Math.Clamp(NewLettersWeight, 0.0, 2.0);
    }
}

public sealed class TimingSettings
{
    /// <summary>Pausa entre uma verificação de turno e a próxima.</summary>
    public int CycleDelayMs { get; set; } = 200;

    /// <summary>Espera após selecionar a sílaba (e prazo máximo para o Ctrl+C chegar).</summary>
    public int SettleAfterSelectMs { get; set; } = 300;

    /// <summary>Espera entre focar o campo de digitação e começar a digitar.</summary>
    public int BeforeTypingMs { get; set; } = 200;

    /// <summary>Orçamento de tempo por turno; acima dele a encenação é cortada.</summary>
    public double RoundTimeLimitSeconds { get; set; } = 4.5;

    /// <summary>
    /// Espera mínima depois de cada tecla, clique ou ENTER, para o navegador/jogo processar a entrada.
    /// 100 ms reproduz o ritmo real da versão em Python (pausa padrão do pyautogui).
    /// </summary>
    public int KeyIntervalMs { get; set; } = 100;

    internal void Normalize()
    {
        CycleDelayMs = Math.Clamp(CycleDelayMs, 50, 2000);
        SettleAfterSelectMs = Math.Clamp(SettleAfterSelectMs, 30, 1500);
        BeforeTypingMs = Math.Clamp(BeforeTypingMs, 0, 2000);
        RoundTimeLimitSeconds = Math.Clamp(RoundTimeLimitSeconds, 0.5, 15.0);
        KeyIntervalMs = Math.Clamp(KeyIntervalMs, 0, 300);
    }
}

public sealed class HumanizationSettings
{
    public TypingSpeedProfile Profile { get; set; } = TypingSpeedProfile.Random;

    public int LetterDelayMs { get; set; } = 6;

    /// <summary>Variação aleatória adicional por caractere, em segundos.</summary>
    public double DelayJitterSeconds { get; set; } = 0.010;

    /// <summary>Probabilidade por caractere de errar uma letra e corrigir com backspace.</summary>
    public double TypoChance { get; set; } = 0.06;

    /// <summary>"Respira" a cada N letras.</summary>
    public int PauseEvery { get; set; } = 4;

    public double PauseMinSeconds { get; set; } = 0.015;
    public double PauseMaxSeconds { get; set; } = 0.06;

    public double EnterHesitationMinSeconds { get; set; } = 0.06;
    public double EnterHesitationMaxSeconds { get; set; } = 0.18;

    /// <summary>Chance de enviar uma palavra errada de propósito.</summary>
    public double DeliberateFailChance { get; set; }

    /// <summary>Chance de enviar com UMA letra errada e em seguida a correta.</summary>
    public double WrongEnterChance { get; set; }

    /// <summary>Chance de digitar uma frase engraçada e apagar antes da resposta.</summary>
    public double JokePhraseChance { get; set; } = 0.20;

    /// <summary>Chance de digitar um rascunho da palavra e apagar antes da resposta.</summary>
    public double RehearsalChance { get; set; } = 0.25;

    /// <summary>Pausa depois das 3 primeiras letras quando a palavra começa com a sílaba.</summary>
    public bool ThinkAfterThree { get; set; } = true;

    public int ThinkAfterThreeMs { get; set; } = 500;

    /// <summary>Insere dígitos aleatórios durante a digitação por algumas rodadas.</summary>
    public bool InsertNumbers { get; set; }

    public int NumberRounds { get; set; }

    /// <summary>Somadas às frases padrão do app.</summary>
    public List<string> CustomPhrases { get; set; } = [];

    internal void Normalize()
    {
        Profile = AppSettings.ValidEnum(Profile, TypingSpeedProfile.Random);
        LetterDelayMs = Math.Clamp(LetterDelayMs, 1, 200);
        DelayJitterSeconds = Math.Clamp(DelayJitterSeconds, 0, 0.2);
        TypoChance = Math.Clamp(TypoChance, 0, 0.5);
        PauseEvery = Math.Clamp(PauseEvery, 1, 20);
        PauseMinSeconds = Math.Clamp(PauseMinSeconds, 0, 1);
        PauseMaxSeconds = Math.Clamp(PauseMaxSeconds, 0, 1);
        if (PauseMinSeconds > PauseMaxSeconds)
            (PauseMinSeconds, PauseMaxSeconds) = (PauseMaxSeconds, PauseMinSeconds);
        EnterHesitationMinSeconds = Math.Clamp(EnterHesitationMinSeconds, 0, 2);
        EnterHesitationMaxSeconds = Math.Clamp(EnterHesitationMaxSeconds, 0, 2);
        if (EnterHesitationMinSeconds > EnterHesitationMaxSeconds)
            (EnterHesitationMinSeconds, EnterHesitationMaxSeconds) = (EnterHesitationMaxSeconds, EnterHesitationMinSeconds);
        DeliberateFailChance = Math.Clamp(DeliberateFailChance, 0, 1);
        WrongEnterChance = Math.Clamp(WrongEnterChance, 0, 1);
        JokePhraseChance = Math.Clamp(JokePhraseChance, 0, 1);
        RehearsalChance = Math.Clamp(RehearsalChance, 0, 1);
        ThinkAfterThreeMs = Math.Clamp(ThinkAfterThreeMs, 0, 5000);
        NumberRounds = Math.Clamp(NumberRounds, 0, 1000);
        CustomPhrases = (CustomPhrases ?? [])
            .Select(p => p?.Trim() ?? "")
            .Where(p => p.Length > 0)
            .ToList();
    }
}

/// <summary>Posições calibradas na tela (pixels físicos).</summary>
public sealed class Calibration
{
    /// <summary>Ponto sobre a sílaba (clique para selecionar; também é onde o mouse "estaciona").</summary>
    public ScreenPoint SyllablePoint { get; set; } = new(692, 594);

    /// <summary>Ponto dentro do campo de digitação do jogo.</summary>
    public ScreenPoint ChatPoint { get; set; } = new(838, 953);

    public ScreenRect TurnBar { get; set; } = new(600, 1010, 240, 32);

    /// <summary>Região da sílaba para OCR.</summary>
    public ScreenRect? SyllableRegion { get; set; }

    /// <summary>Tamanho da área de trabalho virtual quando as posições foram calibradas.</summary>
    public ScreenSize? CalibratedDesktop { get; set; }
}
