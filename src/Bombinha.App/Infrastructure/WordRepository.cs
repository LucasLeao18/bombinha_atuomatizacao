using System.IO;
using System.Text;
using Bombinha.Core.Engine;
using Bombinha.Core.Settings;
using Bombinha.Core.Words;

namespace Bombinha.App.Infrastructure;

/// <summary>Dicionário (embutido ou do usuário) + blacklist + rejeitadas aprendidas, em %APPDATA%.</summary>
internal sealed class WordRepository(AppPaths paths) : IWordRepository
{
    public WordListFile Rejected { get; } = new(paths.RejectedFile);
    public WordListFile Blacklist { get; } = new(paths.BlacklistFile);

    public WordLoadSummary LoadInto(WordList list, AppSettings settings)
    {
        List<string> words;
        string source;
        string? path = settings.General.DictionaryPath;
        if (path is null)
        {
            using var reader = new StreamReader(EmbeddedAssets.Open(EmbeddedAssets.Dictionary), Encoding.UTF8);
            words = WordText.ParseList(reader, allowComments: false);
            source = "dicionário PT-BR embutido";
        }
        else
        {
            if (!File.Exists(path))
                throw new FileNotFoundException($"Dicionário não encontrado: {path}", path);
            using var reader = new StreamReader(path, Encoding.UTF8, detectEncodingFromByteOrderMarks: true);
            words = WordText.ParseList(reader, allowComments: false);
            source = Path.GetFileName(path);
        }
        if (words.Count == 0)
            throw new InvalidDataException($"O dicionário ({source}) está vazio.");

        var blacklist = Blacklist.ReadAll();
        var rejected = Rejected.ReadAll();
        list.Replace(words, blacklist, rejected);
        return new WordLoadSummary(words.Count, blacklist.Count, rejected.Count, source);
    }

    public void PersistRejected(string word) => Rejected.Append(word);
}
