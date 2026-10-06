using System.Runtime.InteropServices;
using System.Windows.Interop;

namespace Bombinha.App.Platform;

/// <summary>
/// Atalhos globais via RegisterHotKey: o Windows avisa por mensagem, sem hook de teclado e sem a
/// thread que a versão antiga mantinha consultando o teclado a cada 100 ms.
/// </summary>
internal sealed class GlobalHotkeys : IDisposable
{
    private readonly HwndSource _source;
    private readonly Dictionary<int, Action> _actions = [];
    private int _nextId = 0xB000;

    public GlobalHotkeys(HwndSource source)
    {
        _source = source;
        _source.AddHook(WndProc);
    }

    /// <summary>Registra a tecla sem modificadores. Retorna o erro do Windows, ou null se deu certo.</summary>
    public string? Register(uint virtualKey, Action action)
    {
        int id = _nextId++;
        if (!Native.RegisterHotKey(_source.Handle, id, Native.MOD_NOREPEAT, virtualKey))
            return new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error()).Message;
        _actions[id] = action;
        return null;
    }

    public void Dispose()
    {
        foreach (int id in _actions.Keys)
            Native.UnregisterHotKey(_source.Handle, id);
        _actions.Clear();
        _source.RemoveHook(WndProc);
    }

    private nint WndProc(nint hwnd, int msg, nint wParam, nint lParam, ref bool handled)
    {
        if (msg == Native.WM_HOTKEY && _actions.TryGetValue((int)wParam, out var action))
        {
            action();
            handled = true;
        }
        return 0;
    }
}
