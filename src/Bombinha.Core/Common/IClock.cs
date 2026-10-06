namespace Bombinha.Core.Common;

/// <summary>
/// Tempo monotônico e espera cancelável. O motor roda numa thread dedicada e depende de
/// esperas curtas e precisas (atrasos de digitação de poucos ms), por isso a espera é
/// síncrona; a implementação de produção usa um timer de alta resolução do Windows.
/// </summary>
public interface IClock
{
    /// <summary>Tempo decorrido desde um ponto arbitrário (monotônico).</summary>
    TimeSpan Elapsed { get; }

    /// <summary>Espera <paramref name="duration"/>; lança <see cref="OperationCanceledException"/> se cancelado.</summary>
    void Sleep(TimeSpan duration, CancellationToken cancellationToken);
}

/// <summary>Relógio portátil (resolução do timer padrão do SO). Usado fora do Windows e em ferramentas.</summary>
public sealed class StopwatchClock : IClock
{
    private readonly long _start = System.Diagnostics.Stopwatch.GetTimestamp();

    public TimeSpan Elapsed => System.Diagnostics.Stopwatch.GetElapsedTime(_start);

    public void Sleep(TimeSpan duration, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (duration <= TimeSpan.Zero)
            return;
        if (cancellationToken.WaitHandle.WaitOne(duration))
            cancellationToken.ThrowIfCancellationRequested();
    }
}
