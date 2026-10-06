using Bombinha.Core.Settings;

namespace Bombinha.App.Infrastructure;

/// <summary>
/// Dono da configuração vigente. Cada gravação publica um clone novo, que ninguém mais altera:
/// o motor lê <see cref="Current"/> a cada ciclo sem precisar de lock e sem ver edições pela metade.
/// </summary>
internal sealed class SettingsService(SettingsStore store)
{
    private AppSettings _current = new();

    /// <summary>Disparado na thread que salvou (sempre a da interface).</summary>
    public event Action<AppSettings>? Changed;

    /// <summary>Somente leitura por convenção: altere via <see cref="Save"/> ou <see cref="Update"/>.</summary>
    public AppSettings Current => Volatile.Read(ref _current);

    public string FilePath => store.Path;

    public SettingsLoadResult Load()
    {
        var result = store.Load();
        Volatile.Write(ref _current, result.Settings);
        return result;
    }

    /// <exception cref="System.IO.IOException">Falha ao gravar o arquivo.</exception>
    public void Save(AppSettings settings)
    {
        var copy = settings.Clone();
        store.Save(copy);
        Volatile.Write(ref _current, copy);
        Changed?.Invoke(copy);
    }

    /// <summary>Altera um ou mais campos e grava.</summary>
    public void Update(Action<AppSettings> change)
    {
        var copy = Current.Clone();
        change(copy);
        Save(copy.Normalize());
    }
}
