using Bombinha.Core.Common;
using Bombinha.Core.Settings;

namespace Bombinha.Core.Typing;

/// <summary>
/// Monta roteiros de digitação humanizada. Puro: todo o acaso vem do <see cref="Random"/> injetado,
/// então o mesmo seed gera exatamente o mesmo roteiro.
/// </summary>
public sealed class TypingPlanner(Random random)
{
    public static IReadOnlyList<string> DefaultJokePhrases { get; } =
    [
        "pera ai 🤔",
        "hmmm acho que é isso...",
        "calma, quase lá",
        "deixa eu pensar rapidinho",
        "ops, escrevi errado",
        "é isso? acho que sim",
    ];

    private const string Letters = "abcdefghijklmnopqrstuvwxyz";
    private const double NumberChancePerChar = 0.12;
    private static readonly string[] RehearsalEndings = ["..", "...", "!"];

    public RoundTriggers SampleTriggers(HumanizationSettings h)
    {
        // No máximo UM envio errado por rodada: falha proposital OU erro+ENTER.
        bool fail = random.NextDouble() < h.DeliberateFailChance;
        bool wrongEnter = !fail && random.NextDouble() < h.WrongEnterChance;
        bool joke = random.NextDouble() < h.JokePhraseChance;
        bool rehearsal = random.NextDouble() < h.RehearsalChance;
        return new RoundTriggers(joke, rehearsal, fail, wrongEnter);
    }

    /// <summary>Roteiro completo da jogada com a encenação sorteada.</summary>
    public RoundScript BuildRound(string word, RoundTriggers triggers, bool thinkAfterThree, bool insertNumbers,
        HumanizationSettings h, TimingSettings t)
    {
        if (triggers.DeliberateFailure)
            return new RoundScript(RoundStyle.DeliberateFailure,
                [Word(Typo(word, minLengthToReplace: 3), h, t, think: false, numbers: false, label: "falha proposital")],
                ["falha"]);

        if (triggers.WrongEnter)
            return new RoundScript(RoundStyle.WrongThenCorrect,
            [
                Word(Typo(word, minLengthToReplace: 1), h, t, think: false, numbers: false, label: "erro + ENTER"),
                Word(word, h, t, think: false, numbers: insertNumbers, label: "correção"),
            ], ["errEnter"]);

        var plans = new List<TypingPlan>();
        var flags = new List<string>();
        if (triggers.JokePhrase)
        {
            plans.Add(Scratch(JokePhrase(h), h, t, "frase engraçada"));
            flags.Add("frase");
        }
        if (triggers.Rehearsal)
        {
            plans.Add(Scratch(Rehearsal(word), h, t, "ensaio"));
            flags.Add("ensaio");
        }
        bool think = thinkAfterThree && word.Length >= 3;
        if (think)
            flags.Add("pensar3");
        if (insertNumbers)
            flags.Add("números");
        plans.Add(Word(word, h, t, think, insertNumbers, "palavra"));
        return new RoundScript(RoundStyle.Normal, plans, flags);
    }

    public static RoundScript QuickRound(string text, TimingSettings t) =>
        new(RoundStyle.Quick, [Quick(text, t)], []);

    /// <summary>Digita a palavra com o perfil humanizado e envia.</summary>
    public TypingPlan Word(string word, HumanizationSettings h, TimingSettings t, bool think, bool numbers,
        string label = "palavra")
    {
        // Começa limpando o campo: sobra de um envio anterior nunca pode virar prefixo da palavra.
        var steps = new List<TypingStep>();
        Key(steps, new TypingStep.ClearField(), t);
        steps.Add(Wait(t.BeforeTypingMs));
        int thinkIndex = Math.Min(2, word.Length - 1);
        for (int i = 0; i < word.Length; i++)
        {
            char ch = word[i];
            if (random.NextDouble() < h.TypoChance && char.IsLetter(ch))
            {
                Key(steps, new TypingStep.TypeText(RandomLetter().ToString()), t);
                AddLetterDelay(steps, i, word.Length, h);
                Key(steps, new TypingStep.Backspace(), t);
            }

            Key(steps, new TypingStep.TypeText(ch.ToString()), t);

            if (numbers && random.NextDouble() < NumberChancePerChar)
                Key(steps, new TypingStep.TypeText(random.Next(0, 10).ToString()), t);

            if (think && i == thinkIndex)
                steps.Add(Wait(h.ThinkAfterThreeMs));

            AddLetterDelay(steps, i, word.Length, h);
        }
        steps.Add(new TypingStep.Wait(Ms.Seconds(random.Uniform(h.EnterHesitationMinSeconds, h.EnterHesitationMaxSeconds))));
        Key(steps, new TypingStep.Submit(), t);
        return new TypingPlan(label, steps);
    }

    /// <summary>Digita um texto que não é enviado e depois apaga o campo.</summary>
    public TypingPlan Scratch(string text, HumanizationSettings h, TimingSettings t, string label)
    {
        var steps = new List<TypingStep>();
        Key(steps, new TypingStep.Focus(), t);
        steps.Add(Wait(t.BeforeTypingMs));
        for (int i = 0; i < text.Length; i++)
        {
            if (random.NextDouble() < h.TypoChance && char.IsLetter(text[i]))
            {
                Key(steps, new TypingStep.TypeText(RandomLetter().ToString()), t);
                AddLetterDelay(steps, i, text.Length, h);
                Key(steps, new TypingStep.Backspace(), t);
            }
            Key(steps, new TypingStep.TypeText(text[i].ToString()), t);
            AddLetterDelay(steps, i, text.Length, h);
        }
        Key(steps, new TypingStep.ClearField(), t);
        return new TypingPlan(label, steps);
    }

    /// <summary>Envio direto, sem encenação: usado quando o tempo aperta.</summary>
    public static TypingPlan Quick(string text, TimingSettings t)
    {
        var steps = new List<TypingStep>();
        Key(steps, new TypingStep.ClearField(), t);
        steps.Add(Wait(50));
        foreach (char ch in text)
        {
            Key(steps, new TypingStep.TypeText(ch.ToString()), t);
            steps.Add(Wait(1));
        }
        Key(steps, new TypingStep.Submit(), t);
        return new TypingPlan("envio rápido", steps);
    }

    /// <summary>
    /// Toda ação de teclado/mouse é seguida do intervalo mínimo configurado. O navegador e o jogo
    /// processam as teclas de forma assíncrona; sem esse respiro o ENTER chega antes das letras e a
    /// palavra seguinte começa antes de o campo ser limpo. (A versão em Python tinha esse intervalo
    /// sem perceber: o pyautogui espera 100 ms depois de cada chamada por padrão.)
    /// </summary>
    private static void Key(List<TypingStep> steps, TypingStep step, TimingSettings t)
    {
        steps.Add(step);
        if (t.KeyIntervalMs > 0)
            steps.Add(Wait(t.KeyIntervalMs));
    }

    /// <summary>Troca uma letra (palavras com mais de N letras) ou acrescenta uma letra no fim.</summary>
    public string Typo(string word, int minLengthToReplace)
    {
        if (word.Length > minLengthToReplace)
        {
            int i = random.Next(word.Length);
            string pool = Letters.Replace(word[i].ToString(), "", StringComparison.Ordinal);
            return string.Concat(word.AsSpan(0, i), pool[random.Next(pool.Length)].ToString(), word.AsSpan(i + 1));
        }
        return word + RandomLetter();
    }

    public string Rehearsal(string word)
    {
        if (word.Length <= 3)
            return word[..Math.Min(2, word.Length)] + "...";
        int k = random.Next(2, Math.Min(word.Length - 1, 5) + 1);
        return word[..k] + RehearsalEndings[random.Next(RehearsalEndings.Length)];
    }

    public string JokePhrase(HumanizationSettings h)
    {
        var pool = h.CustomPhrases.Concat(DefaultJokePhrases).ToList();
        return pool[random.Next(pool.Count)];
    }

    private void AddLetterDelay(List<TypingStep> steps, int index, int total, HumanizationSettings h)
    {
        double baseDelay = Math.Clamp(h.LetterDelayMs / 1000.0, 0.0005, 0.2);
        double d = h.Profile switch
        {
            TypingSpeedProfile.Gradual => baseDelay * (0.6 + (0.4 * index / Math.Max(1, total - 1))),
            TypingSpeedProfile.Fast => baseDelay * 0.6,
            TypingSpeedProfile.Random => baseDelay * random.Uniform(0.65, 1.35),
            _ => baseDelay,
        };
        d += random.Uniform(0.0, h.DelayJitterSeconds);
        steps.Add(new TypingStep.Wait(Ms.Seconds(d)));

        // "Respiro" periódico, exceto depois da última letra.
        if ((index + 1) % Math.Max(1, h.PauseEvery) == 0 && index + 1 < total)
            steps.Add(new TypingStep.Wait(Ms.Seconds(random.Uniform(h.PauseMinSeconds, h.PauseMaxSeconds))));
    }

    private char RandomLetter() => Letters[random.Next(Letters.Length)];

    private static TypingStep.Wait Wait(double milliseconds) => new(Ms.Of(milliseconds));
}
