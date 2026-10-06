using Bombinha.Core.Settings;

namespace Bombinha.Core.Words;

public readonly record struct RankedWord(string Word, double Score);

/// <summary>
/// Escolhe a palavra da rodada e guarda o estado da sessão/partida que influencia a escolha
/// (frequência de uso, palavras recentes, letras já usadas rumo à vida extra).
/// Não é thread-safe: o motor serializa o acesso.
/// </summary>
public sealed class WordSelector(Random random)
{
    /// <summary>Letras que o JKLM não exige para a vida extra.</summary>
    public const string IgnoredLetters = "kwy";

    /// <summary>As 23 letras que completam o alfabeto da vida extra.</summary>
    public static IReadOnlyList<char> AlphabetLetters { get; } =
        "abcdefghijklmnopqrstuvwxyz".Where(c => !IgnoredLetters.Contains(c)).ToArray();

    private static readonly HashSet<char> AlphabetSet = [.. AlphabetLetters];

    private readonly LinkedList<string> _recent = new();
    private readonly Dictionary<string, int> _frequency = new(StringComparer.Ordinal);
    private readonly HashSet<char> _lettersUsed = [];
    private readonly HashSet<string> _usedInMatch = new(StringComparer.Ordinal);

    public int AlphabetsCompleted { get; private set; }

    public IReadOnlySet<char> LettersUsed => _lettersUsed;

    public IReadOnlySet<string> UsedInMatch => _usedInMatch;

    public int FrequencyOf(string word) => _frequency.GetValueOrDefault(word);

    /// <summary>Palavras que o jogo recusaria agora por já terem sido usadas na partida.</summary>
    public IReadOnlySet<string> BlockedWords(SelectionSettings s) =>
        s.BlockUsedInMatch ? _usedInMatch : FrozenEmpty;

    private static readonly IReadOnlySet<string> FrozenEmpty = new HashSet<string>();

    /// <summary>
    /// Ordena as candidatas pela pontuação (estável: empates mantêm a ordem do dicionário).
    /// <paramref name="slack"/>: 1 = turno recém-começado, 0 = sem tempo.
    /// </summary>
    public List<RankedWord> Rank(IEnumerable<string> candidates, GameMode mode, string syllable,
        double slack, SelectionSettings s)
    {
        string frag = WordText.Normalize(syllable);
        slack = Math.Clamp(slack, 0.0, 1.0);
        return candidates
            .Select(w => new RankedWord(w, mode == GameMode.Alphabet ? AlphabetScore(w) : BaseScore(w, mode, frag, slack, s)))
            .OrderByDescending(r => r.Score)
            .ToList();
    }

    /// <summary>Sorteia entre as <c>TopN</c> melhores com peso proporcional à pontuação.</summary>
    public string? Choose(IReadOnlyList<RankedWord> ranked, SelectionSettings s)
    {
        if (ranked.Count == 0)
            return null;
        int top = Math.Clamp(s.TopN, 1, ranked.Count);
        double total = 0;
        for (int i = 0; i < top; i++)
            total += Math.Max(1e-3, ranked[i].Score);

        double roll = random.NextDouble() * total;
        for (int i = 0; i < top; i++)
        {
            roll -= Math.Max(1e-3, ranked[i].Score);
            if (roll < 0)
                return ranked[i].Word;
        }
        return ranked[top - 1].Word;
    }

    public void RegisterUse(string word, SelectionSettings s)
    {
        _frequency[word] = _frequency.GetValueOrDefault(word) + 1;
        _usedInMatch.Add(word);

        _recent.AddLast(word);
        while (_recent.Count > s.RepeatCooldown)
            _recent.RemoveFirst();

        _lettersUsed.UnionWith(AlphabetLettersIn(word));
        if (_lettersUsed.Count >= AlphabetLetters.Count)
        {
            AlphabetsCompleted++;
            _lettersUsed.Clear();
        }
    }

    /// <summary>Zera o que vale por partida; frequência e alfabetos completos são da sessão.</summary>
    public void NewMatch()
    {
        _usedInMatch.Clear();
        _lettersUsed.Clear();
        _recent.Clear();
    }

    internal int NewLetters(string word) => AlphabetLettersIn(word).Count(c => !_lettersUsed.Contains(c));

    internal double BaseScore(string word, GameMode mode, string frag, double slack, SelectionSettings s)
    {
        double score = mode switch
        {
            GameMode.ShortWords => 1.0 / (word.Length + 1e-3),
            GameMode.LongWords => word.Length,
            _ => 1.0,
        };

        if (s.PreferPrefix && word.StartsWith(frag, StringComparison.Ordinal))
            score *= Math.Max(1.0, s.PrefixWeight);

        // Caça à vida extra embutida nos modos normais, só quando sobra tempo.
        if (s.HuntNewLetters && slack > 0)
        {
            int fresh = NewLetters(word);
            if (fresh > 0)
                score *= 1.0 + (s.NewLettersWeight * slack * fresh / 5.0);
        }

        if (s.PenalizeRepeats)
        {
            int freq = _frequency.GetValueOrDefault(word);
            if (freq > 0)
                score *= Math.Pow(s.RepeatPenalty, freq);
            if (_recent.Contains(word))
                score *= 0.5;
        }
        return score;
    }

    internal double AlphabetScore(string word) => NewLetters(word) + (word.Length * 0.05);

    // Só as 23 letras contam: acentuadas e K/W/Y não completam o alfabeto do jogo.
    private static HashSet<char> AlphabetLettersIn(string word) => [.. word.Where(AlphabetSet.Contains)];

    // Apenas para testes.
    internal void SetLettersUsed(IEnumerable<char> letters)
    {
        _lettersUsed.Clear();
        _lettersUsed.UnionWith(letters);
    }
}
