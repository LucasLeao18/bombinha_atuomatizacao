using System.ComponentModel;
using System.Runtime.InteropServices;
using Bombinha.Core.Common;
using Bombinha.Core.Typing;

namespace Bombinha.App.Platform;

/// <summary>
/// Teclado e mouse via SendInput. Cada operação vai num único lote, então não se mistura com
/// teclas que o usuário esteja apertando. O texto é enviado como caracteres Unicode: independe do
/// layout (ABNT2, US...) e digita acentos — o pyautogui antigo simplesmente pulava "ç", "é" etc.
/// </summary>
internal sealed class Win32Input : IInputDriver
{
    public ScreenPoint GetCursorPosition() =>
        Native.GetCursorPos(out var p) ? new ScreenPoint(p.X, p.Y) : throw new Win32Exception(Marshal.GetLastWin32Error());

    public void MoveTo(ScreenPoint point)
    {
        if (!Native.SetCursorPos(point.X, point.Y))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Não foi possível mover o cursor.");
    }

    public void LeftClick() =>
        Send([Mouse(Native.MOUSEEVENTF_LEFTDOWN), Mouse(Native.MOUSEEVENTF_LEFTUP)]);

    public void TypeText(string text)
    {
        if (text.Length == 0)
            return;
        var inputs = new Native.INPUT[text.Length * 2];
        for (int i = 0; i < text.Length; i++)
        {
            inputs[2 * i] = Unicode(text[i], keyUp: false);
            inputs[(2 * i) + 1] = Unicode(text[i], keyUp: true);
        }
        Send(inputs);
    }

    public void PressKey(VirtualKey key) => Send([Key(key, false), Key(key, true)]);

    public void PressChord(VirtualKey modifier, VirtualKey key) =>
        Send([Key(modifier, false), Key(key, false), Key(key, true), Key(modifier, true)]);

    private static unsafe void Send(Native.INPUT[] inputs)
    {
        uint sent;
        fixed (Native.INPUT* ptr = inputs)
            sent = Native.SendInput((uint)inputs.Length, ptr, sizeof(Native.INPUT));
        if (sent != inputs.Length)
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(),
                "O Windows bloqueou a entrada simulada (tela bloqueada, UAC aberto ou janela do jogo rodando como administrador).");
        }
    }

    private static Native.INPUT Mouse(uint flags) => new()
    {
        type = Native.INPUT_MOUSE,
        U = new Native.InputUnion { mi = new Native.MOUSEINPUT { dwFlags = flags } },
    };

    private static Native.INPUT Key(VirtualKey key, bool keyUp) => new()
    {
        type = Native.INPUT_KEYBOARD,
        U = new Native.InputUnion
        {
            ki = new Native.KEYBDINPUT { wVk = (ushort)key, dwFlags = keyUp ? Native.KEYEVENTF_KEYUP : 0 },
        },
    };

    private static Native.INPUT Unicode(char c, bool keyUp) => new()
    {
        type = Native.INPUT_KEYBOARD,
        U = new Native.InputUnion
        {
            ki = new Native.KEYBDINPUT
            {
                wScan = c,
                dwFlags = Native.KEYEVENTF_UNICODE | (keyUp ? Native.KEYEVENTF_KEYUP : 0),
            },
        },
    };
}
