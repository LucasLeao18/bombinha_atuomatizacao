using System.Diagnostics;
using Bombinha.Core.Common;
using Bombinha.Core.Logging;
using Bombinha.Core.Typing;

namespace Bombinha.App.Platform;

/// <summary>
/// Antes de digitar, garante que o clique no campo de digitação realmente deu foco ao jogo.
/// A versão antiga digitava em qualquer janela que estivesse em foco — inclusive na própria
/// interface do bot, que fica "sempre no topo" e pode cobrir o jogo.
/// </summary>
internal sealed class ForegroundWindowGuard(Logger log) : ITargetWindowGuard
{
    private readonly int _ownProcessId = Environment.ProcessId;
    private readonly bool _weAreElevated = Environment.IsPrivilegedProcess;
    private uint _lastTargetPid;
    private bool? _lastTargetElevated;

    public TargetCheck Check(ScreenPoint chatPoint)
    {
        nint foreground = Native.GetForegroundWindow();
        if (foreground == 0)
            return TargetCheck.Unsafe("nenhuma janela em primeiro plano.");

        Native.GetWindowThreadProcessId(foreground, out uint pid);
        if (pid == _ownProcessId)
            return TargetCheck.Unsafe("a janela do Bombinha está em foco ou por cima do campo de digitação. " +
                                      "Afaste-a do jogo ou desative \"Sempre no topo\".");

        nint underPoint = Native.GetAncestor(Native.WindowFromPoint(new Native.POINT { X = chatPoint.X, Y = chatPoint.Y }), Native.GA_ROOT);
        if (underPoint != foreground)
            return TargetCheck.Unsafe($"o campo de digitação está coberto por outra janela ({ProcessName(underPoint)}); " +
                                      $"o foco ficou em {ProcessName(foreground)}.");

        if (pid != _lastTargetPid)
        {
            _lastTargetPid = pid;
            _lastTargetElevated = _weAreElevated ? false : IsElevated(pid);
            log.Info($"Digitando na janela de {ProcessName(foreground)} (PID {pid}).");
        }
        if (_lastTargetElevated == true)
            return TargetCheck.Unsafe("o navegador do jogo está rodando como administrador e o Windows bloqueia teclas " +
                                      "vindas de um programa comum. Abra o navegador normalmente ou execute o Bombinha como administrador.");
        return TargetCheck.Safe;
    }

    private static string ProcessName(nint hwnd)
    {
        if (hwnd == 0)
            return "desconhecida";
        Native.GetWindowThreadProcessId(hwnd, out uint pid);
        try
        {
            using var p = Process.GetProcessById((int)pid);
            return p.ProcessName + ".exe";
        }
        catch (ArgumentException)
        {
            return $"PID {pid}";
        }
    }

    /// <summary>True/false quando dá para saber; null se o token não pôde ser lido.</summary>
    private static bool? IsElevated(uint pid)
    {
        nint process = Native.OpenProcess(Native.PROCESS_QUERY_LIMITED_INFORMATION, false, pid);
        if (process == 0)
            return null;
        try
        {
            if (!Native.OpenProcessToken(process, Native.TOKEN_QUERY, out nint token))
                return null;
            try
            {
                return Native.GetTokenInformation(token, Native.TokenElevation, out uint elevated, sizeof(uint), out _)
                    ? elevated != 0
                    : null;
            }
            finally
            {
                Native.CloseHandle(token);
            }
        }
        finally
        {
            Native.CloseHandle(process);
        }
    }
}
