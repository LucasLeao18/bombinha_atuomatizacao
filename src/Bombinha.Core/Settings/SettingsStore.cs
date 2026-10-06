using System.Text.Json;

namespace Bombinha.Core.Settings;

public enum SettingsLoadStatus
{
    Loaded,
    Missing,
    /// <summary>Arquivo ilegível: foi renomeado para backup e os padrões foram usados.</summary>
    Corrupt,
}

public sealed record SettingsLoadResult(AppSettings Settings, SettingsLoadStatus Status, string? Detail = null);

/// <summary>Lê e grava o settings.json com escrita atômica (nunca deixa um arquivo pela metade).</summary>
public sealed class SettingsStore(string path)
{
    public string Path { get; } = path;

    public SettingsLoadResult Load()
    {
        if (!File.Exists(Path))
            return new(new AppSettings(), SettingsLoadStatus.Missing);

        try
        {
            string json = File.ReadAllText(Path);
            if (string.IsNullOrWhiteSpace(json))
                throw new JsonException("arquivo vazio");
            return new(SettingsSerializer.Deserialize(json), SettingsLoadStatus.Loaded);
        }
        catch (JsonException ex)
        {
            string backup = $"{Path}.corrompido-{DateTime.Now:yyyyMMdd-HHmmss}";
            File.Move(Path, backup, overwrite: true);
            return new(new AppSettings(), SettingsLoadStatus.Corrupt,
                $"{ex.Message} (cópia preservada em {backup})");
        }
    }

    public void Save(AppSettings settings)
    {
        string? dir = System.IO.Path.GetDirectoryName(Path);
        if (!string.IsNullOrEmpty(dir))
            Directory.CreateDirectory(dir);

        string temp = Path + ".tmp";
        File.WriteAllText(temp, SettingsSerializer.Serialize(settings));
        File.Move(temp, Path, overwrite: true);
    }
}
