namespace Bombinha.Core.Common;

/// <summary>Ponto em pixels físicos da área de trabalho virtual.</summary>
public readonly record struct ScreenPoint(int X, int Y)
{
    public override string ToString() => $"({X}, {Y})";
}

/// <summary>Tamanho em pixels físicos.</summary>
public readonly record struct ScreenSize(int Width, int Height)
{
    public override string ToString() => $"{Width}x{Height}";
}

/// <summary>Retângulo em pixels físicos da área de trabalho virtual.</summary>
public readonly record struct ScreenRect(int X, int Y, int Width, int Height)
{
    public bool IsEmpty => Width <= 0 || Height <= 0;
    public int Right => X + Width;
    public int Bottom => Y + Height;

    /// <summary>Retângulo a partir de dois cantos opostos em qualquer ordem (mínimo 1x1).</summary>
    public static ScreenRect FromCorners(ScreenPoint a, ScreenPoint b) =>
        new(Math.Min(a.X, b.X), Math.Min(a.Y, b.Y),
            Math.Max(1, Math.Abs(b.X - a.X)), Math.Max(1, Math.Abs(b.Y - a.Y)));

    public ScreenRect Intersect(ScreenRect other)
    {
        int left = Math.Max(X, other.X);
        int top = Math.Max(Y, other.Y);
        int right = Math.Min(Right, other.Right);
        int bottom = Math.Min(Bottom, other.Bottom);
        return right <= left || bottom <= top ? default : new ScreenRect(left, top, right - left, bottom - top);
    }

    public override string ToString() => $"({X}, {Y}, {Width}x{Height})";
}
