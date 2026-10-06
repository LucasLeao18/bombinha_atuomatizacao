namespace Bombinha.Core.Settings;

/// <summary>Perfis prontos que ajustam a humanização (e o orçamento por turno) de uma vez.</summary>
public sealed record HumanizationPreset(
    string Name,
    string Description,
    TypingSpeedProfile Profile,
    int LetterDelayMs,
    double TypoChance,
    double DelayJitterSeconds,
    int PauseEvery,
    double PauseMinSeconds,
    double PauseMaxSeconds,
    double DeliberateFailChance,
    double WrongEnterChance,
    double JokePhraseChance,
    double RehearsalChance,
    bool ThinkAfterThree,
    int ThinkAfterThreeMs,
    double RoundTimeLimitSeconds)
{
    public static IReadOnlyList<HumanizationPreset> All { get; } =
    [
        new("Seguro", "Parece gente de verdade. Erra, hesita e conversa — mais lento.",
            TypingSpeedProfile.Random, 55, 0.06, 0.020, 4, 0.030, 0.120,
            0.03, 0.06, 0.20, 0.25, true, 500, 6.0),
        new("Equilibrado", "Humanização discreta sem perder rodadas. Bom padrão.",
            TypingSpeedProfile.Random, 20, 0.03, 0.012, 4, 0.020, 0.070,
            0.01, 0.03, 0.08, 0.12, true, 350, 4.0),
        new("Agressivo", "Sem encenação: digita e manda. Para ganhar, não para disfarçar.",
            TypingSpeedProfile.Fast, 5, 0.0, 0.005, 8, 0.010, 0.030,
            0.0, 0.0, 0.0, 0.0, false, 200, 2.0),
    ];

    public void ApplyTo(AppSettings settings)
    {
        var h = settings.Humanization;
        h.Profile = Profile;
        h.LetterDelayMs = LetterDelayMs;
        h.TypoChance = TypoChance;
        h.DelayJitterSeconds = DelayJitterSeconds;
        h.PauseEvery = PauseEvery;
        h.PauseMinSeconds = PauseMinSeconds;
        h.PauseMaxSeconds = PauseMaxSeconds;
        h.DeliberateFailChance = DeliberateFailChance;
        h.WrongEnterChance = WrongEnterChance;
        h.JokePhraseChance = JokePhraseChance;
        h.RehearsalChance = RehearsalChance;
        h.ThinkAfterThree = ThinkAfterThree;
        h.ThinkAfterThreeMs = ThinkAfterThreeMs;
        settings.Timing.RoundTimeLimitSeconds = RoundTimeLimitSeconds;
    }
}
