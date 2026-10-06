namespace Bombinha.Core.Common;

internal static class Ms
{
    public static TimeSpan Of(double milliseconds) => TimeSpan.FromMilliseconds(Math.Max(0, milliseconds));

    public static TimeSpan Seconds(double seconds) => TimeSpan.FromSeconds(Math.Max(0, seconds));

    /// <summary>Amostra uniforme em [min, max) — equivalente ao random.uniform do Python.</summary>
    public static double Uniform(this Random rng, double min, double max) => min + rng.NextDouble() * (max - min);
}
