namespace Bombinha.Core.Words;

/// <summary>
/// Dicionário em memória + blacklist do usuário + palavras que o jogo recusou.
/// Thread-safe: a UI pode recarregar enquanto o motor consulta.
/// </summary>
public sealed class WordList
{
    private readonly Lock _gate = new();
    private string[] _words = [];
    private HashSet<string> _blacklist = new(StringComparer.Ordinal);
    private HashSet<string> _rejected = new(StringComparer.Ordinal);

    public int Count
    {
        get
        {
            lock (_gate)
                return _words.Length;
        }
    }

    public int RejectedCount
    {
        get
        {
            lock (_gate)
                return _rejected.Count;
        }
    }

    public void Replace(IReadOnlyList<string> words, IEnumerable<string> blacklist, IEnumerable<string> rejected)
    {
        var data = words.ToArray();
        var black = new HashSet<string>(blacklist, StringComparer.Ordinal);
        var rej = new HashSet<string>(rejected, StringComparer.Ordinal);
        lock (_gate)
        {
            _words = data;
            _blacklist = black;
            _rejected = rej;
        }
    }

    /// <summary>Palavras que contêm a sílaba em qualquer posição, sem blacklist, rejeitadas e excluídas.</summary>
    public List<string> Filter(string syllable, IReadOnlySet<string>? exclude = null)
    {
        string frag = WordText.Normalize(syllable);
        var result = new List<string>();
        if (frag.Length == 0)
            return result;

        lock (_gate)
        {
            foreach (string w in _words)
            {
                if (w.Contains(frag, StringComparison.Ordinal)
                    && !_blacklist.Contains(w)
                    && !_rejected.Contains(w)
                    && (exclude is null || !exclude.Contains(w)))
                    result.Add(w);
            }
        }
        return result;
    }

    /// <summary>Marca a palavra como desconhecida pelo jogo. Retorna false se já estava marcada.</summary>
    public bool AddRejected(string word)
    {
        string w = WordText.Normalize(word);
        if (w.Length == 0)
            return false;
        lock (_gate)
            return _rejected.Add(w);
    }

    internal bool IsRejected(string word)
    {
        lock (_gate)
            return _rejected.Contains(WordText.Normalize(word));
    }
}

public static class WordText
{
    public static string Normalize(string word) => word.Trim().ToLowerInvariant();

    /// <summary>
    /// Uma palavra por linha; ignora vazias e comentários (#), normaliza para minúsculas e remove
    /// duplicatas mantendo a ordem original (o dicionário PT-BR tem várias, ex.: "Aarao"/"aarao").
    /// </summary>
    public static List<string> ParseList(TextReader reader, bool allowComments)
    {
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var result = new List<string>();
        while (reader.ReadLine() is { } line)
        {
            string w = Normalize(line);
            if (w.Length == 0 || (allowComments && w.StartsWith('#')))
                continue;
            if (seen.Add(w))
                result.Add(w);
        }
        return result;
    }
}
