using Bombinha.Core.Imaging;
using Bombinha.Core.Settings;

namespace Bombinha.Core.Capture;

/// <summary>Conteúdo da área de transferência guardado para ser devolvido depois.</summary>
public interface IClipboardSnapshot;

public interface IClipboard
{
    /// <summary>Muda a cada escrita na área de transferência (ler é barato e não a bloqueia).</summary>
    uint SequenceNumber { get; }

    string? TryGetText();

    /// <summary>Guarda todos os formatos atuais (texto, imagem, arquivos...). Null se estiver vazia.</summary>
    IClipboardSnapshot? TakeSnapshot();

    /// <summary>Devolve o conteúdo guardado sem poluir o histórico (Win+V).</summary>
    void Restore(IClipboardSnapshot snapshot);
}

public interface IOcrEngine
{
    bool IsAvailable { get; }

    /// <summary>Motivo quando <see cref="IsAvailable"/> é false.</summary>
    string? UnavailableReason { get; }

    string Recognize(OcrImage image);
}

/// <summary>Obtém a sílaba do turno já normalizada (minúsculas, só letras). Vazio = falhou.</summary>
public interface ISyllableSource
{
    string Capture(AppSettings settings, CancellationToken ct);
}

public static class SyllableText
{
    /// <summary>As sílabas do Bomb Party têm de 1 a 3 letras; acima disso não é a sílaba.</summary>
    public const int MaxLength = 5;

    /// <summary>Mantém apenas letras latinas (incluindo acentuadas) em minúsculas.</summary>
    public static string Normalize(string? raw)
    {
        if (string.IsNullOrEmpty(raw))
            return "";
        var chars = raw.Where(IsLatinLetter).ToArray();
        return new string(chars).ToLowerInvariant();
    }

    private static bool IsLatinLetter(char c) =>
        c is (>= 'A' and <= 'Z') or (>= 'a' and <= 'z')
            or (>= 'À' and <= 'Ö') or (>= 'Ø' and <= 'ö') or (>= 'ø' and <= 'ÿ');
}
