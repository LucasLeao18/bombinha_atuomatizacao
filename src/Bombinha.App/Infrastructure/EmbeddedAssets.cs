using System.IO;
using System.Reflection;

namespace Bombinha.App.Infrastructure;

/// <summary>Dicionário e template padrão embutidos no executável.</summary>
internal static class EmbeddedAssets
{
    public const string Dictionary = "Bombinha.Assets.acento.txt";
    public const string ChatTemplate = "Bombinha.Assets.chatbox.png";

    public static Stream Open(string name) =>
        Assembly.GetExecutingAssembly().GetManifestResourceStream(name)
        ?? throw new FileNotFoundException($"Recurso embutido ausente: {name}");
}
