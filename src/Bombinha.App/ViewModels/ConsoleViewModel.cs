using System.Collections.ObjectModel;
using System.Runtime.InteropServices;
using System.Windows;
using Bombinha.Core.Logging;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Bombinha.App.ViewModels;

public enum LogLineKind
{
    Debug,
    Info,
    Success,
    Accent,
    Warning,
    Error,
}

public sealed record LogLine(string Time, string Level, string Component, string Message, LogLineKind Kind);

/// <summary>Console colorido por nível, com limite de linhas para não crescer sem fim.</summary>
internal sealed partial class ConsoleViewModel(Logger log) : ObservableObject
{
    private const int MaxLines = 2000;
    private const int TrimTo = 1600;

    [ObservableProperty]
    private bool _autoScroll = true;

    public ObservableCollection<LogLine> Lines { get; } = [];

    /// <summary>Última mensagem relevante (barra de status).</summary>
    public event Action<LogLine>? LineAdded;

    public void Append(IReadOnlyList<LogEntry> entries)
    {
        foreach (var e in entries)
        {
            string message = e.Exception is null ? e.Message : $"{e.Message} [{e.Exception.GetType().Name}: {e.Exception.Message}]";
            var line = new LogLine(e.Timestamp.ToString("HH:mm:ss"), LevelText(e.Level), e.Component, message, KindOf(e));
            Lines.Add(line);
            LineAdded?.Invoke(line);
        }
        if (Lines.Count > MaxLines)
        {
            while (Lines.Count > TrimTo)
                Lines.RemoveAt(0);
        }
    }

    [RelayCommand]
    private void Clear() => Lines.Clear();

    [RelayCommand]
    private void CopyAll()
    {
        string text = string.Join(Environment.NewLine, Lines.Select(l => $"{l.Time}  {l.Level,-5}  [{l.Component}] {l.Message}"));
        try
        {
            Clipboard.SetText(text);
            log.Success("Console copiado para a área de transferência.");
        }
        catch (ExternalException ex)
        {
            log.Warning("A área de transferência está ocupada por outro programa; tente de novo.", ex);
        }
    }

    private static string LevelText(LogLevel level) => level switch
    {
        LogLevel.Debug => "DEBUG",
        LogLevel.Info => "INFO",
        LogLevel.Warning => "AVISO",
        LogLevel.Error => "ERRO",
        _ => "CRÍT",
    };

    private static LogLineKind KindOf(LogEntry e) => e.Level switch
    {
        LogLevel.Debug => LogLineKind.Debug,
        LogLevel.Warning => LogLineKind.Warning,
        LogLevel.Error or LogLevel.Critical => LogLineKind.Error,
        _ => e.Tag switch
        {
            LogTag.Success => LogLineKind.Success,
            LogTag.Accent => LogLineKind.Accent,
            _ => LogLineKind.Info,
        },
    };
}
