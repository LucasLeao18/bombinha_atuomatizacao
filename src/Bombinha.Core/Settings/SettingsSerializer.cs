using System.Text.Json;
using System.Text.Json.Serialization;

namespace Bombinha.Core.Settings;

[JsonSourceGenerationOptions(
    WriteIndented = true,
    PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase,
    UseStringEnumConverter = true,
    ReadCommentHandling = JsonCommentHandling.Skip,
    AllowTrailingCommas = true)]
[JsonSerializable(typeof(AppSettings))]
internal sealed partial class SettingsJsonContext : JsonSerializerContext;

public static class SettingsSerializer
{
    public static string Serialize(AppSettings settings) =>
        JsonSerializer.Serialize(settings, SettingsJsonContext.Default.AppSettings);

    /// <exception cref="JsonException">JSON inválido.</exception>
    public static AppSettings Deserialize(string json) =>
        (JsonSerializer.Deserialize(json, SettingsJsonContext.Default.AppSettings) ?? new AppSettings()).Normalize();

    public static AppSettings Clone(AppSettings settings) => Deserialize(Serialize(settings));
}
