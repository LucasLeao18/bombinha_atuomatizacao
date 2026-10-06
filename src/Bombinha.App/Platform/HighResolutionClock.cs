using System.Diagnostics;
using System.Runtime.InteropServices;
using Bombinha.Core.Common;
using Microsoft.Win32.SafeHandles;

namespace Bombinha.App.Platform;

/// <summary>
/// Espera precisa e cancelável. O timer padrão do Windows tem resolução de ~15,6 ms, o que
/// distorceria atrasos de digitação de 5 ms; o timer de alta resolução (Windows 10 1803+)
/// acerta em ~1 ms sem alterar a resolução global do sistema (timeBeginPeriod).
/// </summary>
internal sealed class HighResolutionClock : IClock
{
    private readonly long _start = Stopwatch.GetTimestamp();

    public TimeSpan Elapsed => Stopwatch.GetElapsedTime(_start);

    public void Sleep(TimeSpan duration, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (duration <= TimeSpan.Zero)
            return;

        using var timer = CreateTimer();
        if (timer is null)
        {
            // Sem timer de alta resolução: espera comum (menos precisa, ainda cancelável).
            if (cancellationToken.WaitHandle.WaitOne(duration))
                cancellationToken.ThrowIfCancellationRequested();
            return;
        }

        long due = -duration.Ticks; // relativo, em unidades de 100 ns
        if (!Native.SetWaitableTimer(timer.SafeWaitHandle.DangerousGetHandle(), ref due, 0, 0, 0, false))
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "SetWaitableTimer falhou.");

        if (WaitHandle.WaitAny([timer, cancellationToken.WaitHandle]) == 1)
            cancellationToken.ThrowIfCancellationRequested();
    }

    private static TimerHandle? CreateTimer()
    {
        nint handle = Native.CreateWaitableTimerEx(0, null, Native.CREATE_WAITABLE_TIMER_HIGH_RESOLUTION, Native.TIMER_ALL_ACCESS);
        return handle == 0 ? null : new TimerHandle(new SafeWaitHandle(handle, ownsHandle: true));
    }

    private sealed class TimerHandle : WaitHandle
    {
        public TimerHandle(SafeWaitHandle handle) => SafeWaitHandle = handle;
    }
}
