using System.Collections.Concurrent;
using System.Windows.Threading;
using Bombinha.Core.Logging;

namespace Bombinha.App.Infrastructure;

/// <summary>
/// Leva as entradas de log (de qualquer thread) para a thread da interface em lotes,
/// com no máximo um despacho pendente por vez.
/// </summary>
internal sealed class UiLogSink(Dispatcher dispatcher) : ILogSink
{
    private readonly ConcurrentQueue<LogEntry> _pending = new();
    private int _scheduled;

    /// <summary>Disparado na thread da interface.</summary>
    public event Action<IReadOnlyList<LogEntry>>? EntriesAdded;

    public void Write(LogEntry entry)
    {
        _pending.Enqueue(entry);
        if (Interlocked.Exchange(ref _scheduled, 1) == 0)
            dispatcher.BeginInvoke(Flush, DispatcherPriority.Background);
    }

    private void Flush()
    {
        Interlocked.Exchange(ref _scheduled, 0);
        var batch = new List<LogEntry>();
        while (_pending.TryDequeue(out var e))
            batch.Add(e);
        if (batch.Count > 0)
            EntriesAdded?.Invoke(batch);
    }
}
