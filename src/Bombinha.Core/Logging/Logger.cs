namespace Bombinha.Core.Logging;

/// <summary>Fachada leve de log com o nome do componente embutido em cada entrada.</summary>
public sealed class Logger
{
    private readonly ILogSink _sink;
    private readonly TimeProvider _time;

    public Logger(ILogSink sink, string component, TimeProvider? time = null)
    {
        _sink = sink;
        Component = component;
        _time = time ?? TimeProvider.System;
    }

    public string Component { get; }

    public Logger For(string component) => new(_sink, component, _time);

    public void Debug(string message) => Write(LogLevel.Debug, message);
    public void Info(string message, LogTag tag = LogTag.None) => Write(LogLevel.Info, message, null, tag);
    public void Success(string message) => Write(LogLevel.Info, message, null, LogTag.Success);
    public void Warning(string message, Exception? exception = null) => Write(LogLevel.Warning, message, exception);
    public void Error(string message, Exception? exception = null) => Write(LogLevel.Error, message, exception);
    public void Critical(string message, Exception? exception = null) => Write(LogLevel.Critical, message, exception);

    public void Write(LogLevel level, string message, Exception? exception = null, LogTag tag = LogTag.None) =>
        _sink.Write(new LogEntry(_time.GetLocalNow(), level, Component, message, exception, tag));
}

/// <summary>Distribui cada entrada para vários destinos, cada um com seu nível mínimo.</summary>
public sealed class CompositeLogSink : ILogSink
{
    private readonly List<(ILogSink Sink, Func<LogLevel> MinLevel)> _sinks = [];
    private readonly Lock _gate = new();

    public void Add(ILogSink sink, Func<LogLevel> minLevel)
    {
        lock (_gate)
            _sinks.Add((sink, minLevel));
    }

    public void Write(LogEntry entry)
    {
        (ILogSink Sink, Func<LogLevel> MinLevel)[] sinks;
        lock (_gate)
            sinks = [.. _sinks];
        foreach (var (sink, minLevel) in sinks)
        {
            if (entry.Level >= minLevel())
                sink.Write(entry);
        }
    }
}

/// <summary>Descarta tudo (padrão para testes e componentes sem log).</summary>
public sealed class NullLogSink : ILogSink
{
    public static readonly NullLogSink Instance = new();
    public void Write(LogEntry entry) { }
}

/// <summary>Guarda as entradas em memória (útil em testes e diagnósticos).</summary>
public sealed class MemoryLogSink : ILogSink
{
    private readonly List<LogEntry> _entries = [];
    private readonly Lock _gate = new();

    public IReadOnlyList<LogEntry> Entries
    {
        get
        {
            lock (_gate)
                return [.. _entries];
        }
    }

    public void Write(LogEntry entry)
    {
        lock (_gate)
            _entries.Add(entry);
    }
}
