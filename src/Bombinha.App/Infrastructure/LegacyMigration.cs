using System.IO;
using Bombinha.Core.Logging;
using Bombinha.Core.Settings;
using Bombinha.Core.Words;

namespace Bombinha.App.Infrastructure;

/// <summary>Traz config.json, posicoes.json, rejeitadas.txt e blacklist.txt da versão em Python.</summary>
internal sealed class LegacyMigration(SettingsService settings, WordRepository words, Logger log)
{
    /// <summary>Na primeira execução, procura a versão antiga ao lado do executável ou na pasta atual.</summary>
    public bool TryAutoImport()
    {
        var candidates = new[] { AppContext.BaseDirectory, Environment.CurrentDirectory }
            .Select(Path.GetFullPath)
            .Distinct(StringComparer.OrdinalIgnoreCase);
        foreach (string folder in candidates)
        {
            if (LegacyImporter.LooksLikeLegacyFolder(folder))
            {
                Import(folder);
                return true;
            }
        }
        return false;
    }

    /// <exception cref="IOException">Falha de leitura/gravação.</exception>
    public LegacyImportResult Import(string folder)
    {
        var result = LegacyImporter.ImportFolder(folder);
        if (result.ImportedConfig || result.ImportedPositions)
            settings.Save(result.Settings);

        int rejected = MergeList(Path.Combine(folder, LegacyImporter.RejectedFileName), words.Rejected);
        int blacklist = MergeList(Path.Combine(folder, LegacyImporter.BlacklistFileName), words.Blacklist);

        log.Success($"Importado da versão antiga ({folder}): configuração {(result.ImportedConfig ? "sim" : "não")}, " +
                    $"posições {(result.ImportedPositions ? "sim" : "não")}, +{rejected} rejeitadas, +{blacklist} na blacklist.");
        foreach (string note in result.Notes)
            log.Warning($"Importação: {note}");
        return result;
    }

    private static int MergeList(string source, WordListFile target) =>
        File.Exists(source) ? target.Merge(new WordListFile(source).ReadAll()) : 0;
}
