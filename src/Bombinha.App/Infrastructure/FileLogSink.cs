using System.IO;
using System.Text;
using System.Threading.Channels;
using Bombinha.Core.Logging;

namespace Bombinha.App.Infrastructure;

/// <summary>
/// Log técnico em arquivo diário (bombinha-AAAAMMDD.log). A escrita acontece numa tarefa de fundo,
/// então registrar nunca bloqueia o motor nem a interface. Mantém os últimos <see cref="RetentionDays"/> dias.
/// </summary>
internal sealed class FileLogSink : ILogSink, IDisposable
{
    public const int RetentionDays = 14;

    private readonly string _directory;
    private readonly Channel<LogEntry> _channel =
        Channel.CreateUnbounded<LogEntry>(new UnboundedChannelOptions { SingleReader = true });
    private readonly Task _writer;

    public FileLogSink(string directory)
    {
        _directory = directory;
        Directory.CreateDirectory(directory);
        DeleteOldFiles();
        _writer = Task.Run(WriteLoopAsync);
    }

    public void Write(LogEntry entry) => _channel.Writer.TryWrite(entry);

    public void Dispose()
    {
        _channel.Writer.TryComplete();
        _writer.Wait(TimeSpan.FromSeconds(2));
    }

    private async Task WriteLoopAsync()
    {
        var sb = new StringBuilder();
        while (await _channel.Reader.WaitToReadAsync().ConfigureAwait(false))
        {
            sb.Clear();
            string? file = null;
            while (_channel.Reader.TryRead(out var e))
            {
                file ??= Path.Combine(_directory, $"bombinha-{e.Timestamp:yyyyMMdd}.log");
                sb.Append(e.Timestamp.ToString("yyyy-MM-dd HH:mm:ss.fff"))
                  .Append(" [").Append(LevelName(e.Level)).Append("] [")
                  .Append(e.Component).Append("] ")
                  .AppendLine(e.Message);
                if (e.Exception is not null)
                    sb.AppendLine(e.Exception.ToString());
            }
            if (file is null)
                continue;
            try
            {
                await File.AppendAllTextAsync(file, sb.ToString(), Encoding.UTF8).ConfigureAwait(false);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                // Disco cheio/arquivo travado: perder um lote de log é preferível a derrubar o app.
                System.Diagnostics.Debug.WriteLine($"Falha ao gravar log: {ex.Message}");
            }
        }
    }

    private static string LevelName(LogLevel level) => level switch
    {
        LogLevel.Debug => "DEBUG",
        LogLevel.Info => "INFO ",
        LogLevel.Warning => "WARN ",
        LogLevel.Error => "ERROR",
        _ => "CRIT ",
    };

    private void DeleteOldFiles()
    {
        var limit = DateTime.Now.AddDays(-RetentionDays);
        foreach (var file in new DirectoryInfo(_directory).EnumerateFiles("bombinha-*.log"))
        {
            if (file.LastWriteTime >= limit)
                continue;
            try
            {
                file.Delete();
            }
            catch (IOException ex)
            {
                // Arquivo em uso: tenta de novo na próxima abertura.
                System.Diagnostics.Debug.WriteLine($"Log antigo não removido: {ex.Message}");
            }
        }
    }
}
