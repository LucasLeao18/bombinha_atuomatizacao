namespace Bombinha.Core.Logging;

public enum LogLevel
{
    Debug,
    Info,
    Warning,
    Error,
    Critical,
}

/// <summary>Destaque visual opcional no console do app (não altera a severidade).</summary>
public enum LogTag
{
    None,
    Success,
    Accent,
}

public sealed record LogEntry(
    DateTimeOffset Timestamp,
    LogLevel Level,
    string Component,
    string Message,
    Exception? Exception = null,
    LogTag Tag = LogTag.None);

public interface ILogSink
{
    /// <summary>Precisa ser thread-safe e não pode lançar exceções.</summary>
    void Write(LogEntry entry);
}
