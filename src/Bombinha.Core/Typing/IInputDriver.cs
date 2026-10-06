using Bombinha.Core.Common;

namespace Bombinha.Core.Typing;

public enum VirtualKey : ushort
{
    Backspace = 0x08,
    Enter = 0x0D,
    Control = 0x11,
    A = 0x41,
    C = 0x43,
}

/// <summary>Injeção de teclado/mouse. Cada chamada é atômica (não intercala com a entrada do usuário).</summary>
public interface IInputDriver
{
    ScreenPoint GetCursorPosition();

    void MoveTo(ScreenPoint point);

    /// <summary>Um clique esquerdo na posição atual do cursor.</summary>
    void LeftClick();

    /// <summary>Digita texto como caracteres Unicode (independe do layout do teclado).</summary>
    void TypeText(string text);

    void PressKey(VirtualKey key);

    void PressChord(VirtualKey modifier, VirtualKey key);
}

public static class InputDriverExtensions
{
    /// <summary>Move o cursor e dá <paramref name="count"/> cliques (duplo/triplo selecionam texto).</summary>
    public static void ClickAt(this IInputDriver input, IClock clock, ScreenPoint point, int count,
        TimeSpan interval, CancellationToken ct)
    {
        input.MoveTo(point);
        for (int i = 0; i < count; i++)
        {
            if (i > 0)
                clock.Sleep(interval, ct);
            input.LeftClick();
        }
    }
}
