using System.Text;

namespace Bombinha.Core.Words;

/// <summary>Arquivo de lista de palavras (uma por linha) com gravação incremental thread-safe.</summary>
public sealed class WordListFile(string path)
{
    private readonly Lock _gate = new();

    public string Path { get; } = path;

    public List<string> ReadAll()
    {
        if (!File.Exists(Path))
            return [];
        using var reader = new StreamReader(Path, Encoding.UTF8, detectEncodingFromByteOrderMarks: true);
        return WordText.ParseList(reader, allowComments: true);
    }

    /// <exception cref="IOException">Falha de escrita (o chamador decide como reportar).</exception>
    public void Append(string word)
    {
        lock (_gate)
        {
            string? dir = System.IO.Path.GetDirectoryName(Path);
            if (!string.IsNullOrEmpty(dir))
                Directory.CreateDirectory(dir);
            File.AppendAllText(Path, word + Environment.NewLine, new UTF8Encoding(false));
        }
    }

    /// <summary>Acrescenta ao arquivo as palavras que ainda não estão nele. Retorna quantas foram adicionadas.</summary>
    public int Merge(IEnumerable<string> words)
    {
        lock (_gate)
        {
            var existing = new HashSet<string>(ReadAll(), StringComparer.Ordinal);
            var added = words.Select(WordText.Normalize).Where(w => w.Length > 0 && existing.Add(w)).ToList();
            if (added.Count > 0)
            {
                string? dir = System.IO.Path.GetDirectoryName(Path);
                if (!string.IsNullOrEmpty(dir))
                    Directory.CreateDirectory(dir);
                File.AppendAllLines(Path, added, new UTF8Encoding(false));
            }
            return added.Count;
        }
    }
}
