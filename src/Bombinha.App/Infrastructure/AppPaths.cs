using System.IO;

namespace Bombinha.App.Infrastructure;

/// <summary>
/// Onde o app guarda seus arquivos. Nada depende do diretório de trabalho: a versão antiga lia
/// config.json/acento.txt relativos à pasta de onde fosse executada e quebrava fora dela.
/// </summary>
internal sealed class AppPaths
{
    public AppPaths()
        : this(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Bombinha"),
               Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Bombinha", "logs"))
    {
    }

    public AppPaths(string dataDirectory, string logDirectory)
    {
        DataDirectory = dataDirectory;
        LogDirectory = logDirectory;
    }

    /// <summary>%APPDATA%\Bombinha — configurações e listas aprendidas (acompanham o perfil).</summary>
    public string DataDirectory { get; }

    /// <summary>%LOCALAPPDATA%\Bombinha\logs — logs técnicos (ficam na máquina).</summary>
    public string LogDirectory { get; }

    public string SettingsFile => Path.Combine(DataDirectory, "settings.json");
    public string RejectedFile => Path.Combine(DataDirectory, "rejeitadas.txt");
    public string BlacklistFile => Path.Combine(DataDirectory, "blacklist.txt");
    public string CapturedTemplateFile => Path.Combine(DataDirectory, "campo-digitacao.png");

    public void EnsureCreated()
    {
        Directory.CreateDirectory(DataDirectory);
        Directory.CreateDirectory(LogDirectory);
    }
}
