using System.Text;
using Bombinha.Core.Capture;
using Bombinha.Core.Common;
using Bombinha.Core.Detection;
using Bombinha.Core.Engine;
using Bombinha.Core.Settings;
using Bombinha.Core.Typing;
using Bombinha.Core.Words;

namespace Bombinha.Core.Tests.Fakes;

/// <summary>Relógio virtual: Sleep avança o tempo na hora, sem esperar de verdade.</summary>
internal sealed class FakeClock : IClock
{
    public TimeSpan Elapsed { get; private set; }

    public Action? OnSleep { get; set; }

    public void Advance(TimeSpan by) => Elapsed += by;

    public void Sleep(TimeSpan duration, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        OnSleep?.Invoke();
        if (duration > TimeSpan.Zero)
            Elapsed += duration;
        cancellationToken.ThrowIfCancellationRequested();
    }
}

/// <summary>Teclado/mouse de mentira que simula um campo de texto e registra os ENTERs.</summary>
internal sealed class FakeInput : IInputDriver
{
    private readonly StringBuilder _field = new();
    private bool _allSelected;

    public List<string> Events { get; } = [];

    /// <summary>Conteúdo do campo em cada ENTER (o que o jogo teria recebido).</summary>
    public List<string> Submitted { get; } = [];

    public ScreenPoint Cursor { get; private set; } = new(5, 5);

    public Action<FakeInput>? OnEvent { get; set; }

    public ScreenPoint GetCursorPosition() => Cursor;

    public void MoveTo(ScreenPoint point)
    {
        Cursor = point;
        Record($"move{point}");
    }

    public void LeftClick() => Record("click");

    public void TypeText(string text)
    {
        if (_allSelected)
        {
            _field.Clear();
            _allSelected = false;
        }
        _field.Append(text);
        Record($"type:{text}");
    }

    public void PressKey(VirtualKey key)
    {
        switch (key)
        {
            case VirtualKey.Backspace when _allSelected:
                _field.Clear();
                _allSelected = false;
                break;
            case VirtualKey.Backspace when _field.Length > 0:
                _field.Length--;
                break;
            case VirtualKey.Enter:
                Submitted.Add(_field.ToString());
                _field.Clear(); // o JKLM limpa o campo ao enviar
                break;
        }
        Record($"key:{key}");
    }

    public void PressChord(VirtualKey modifier, VirtualKey key)
    {
        if (modifier == VirtualKey.Control && key == VirtualKey.A)
            _allSelected = true;
        Record($"chord:{modifier}+{key}");
    }

    /// <summary>Quantos cliques houve desde o último movimento do mouse.</summary>
    public int ClicksSinceLastMove()
    {
        int n = 0;
        for (int i = Events.Count - 1; i >= 0 && !Events[i].StartsWith("move", StringComparison.Ordinal); i--)
        {
            if (Events[i] == "click")
                n++;
        }
        return n;
    }

    private void Record(string e)
    {
        Events.Add(e);
        OnEvent?.Invoke(this);
    }
}

/// <summary>Responde "ainda é minha vez?" com uma sequência pré-programada.</summary>
internal sealed class FakeDetector(params bool[] stillMyTurnAnswers) : ITurnDetector
{
    private readonly Queue<bool> _answers = new(stillMyTurnAnswers);

    public int StillMyTurnQueries { get; private set; }
    public bool ConfirmResult { get; set; } = true;
    public Func<bool> DetectTurnResult { get; set; } = () => false;

    public bool DetectTurn(AppSettings settings) => DetectTurnResult();

    public bool ConfirmForSubmit(AppSettings settings) => ConfirmResult;

    public bool IsStillMyTurn(AppSettings settings)
    {
        StillMyTurnQueries++;
        return _answers.Count > 0 && _answers.Dequeue();
    }

    public void ResetReference() { }
}

internal sealed class SafeTarget : ITargetWindowGuard
{
    public TargetCheck Result { get; set; } = TargetCheck.Safe;
    public TargetCheck Check(ScreenPoint chatPoint) => Result;
}

internal sealed class FakeSyllables(params string[] syllables) : ISyllableSource
{
    private readonly Queue<string> _queue = new(syllables);
    public string Capture(AppSettings settings, CancellationToken ct) => _queue.Count > 0 ? _queue.Dequeue() : "";
}

internal sealed class InMemoryWordRepository(IReadOnlyList<string> words) : IWordRepository
{
    public List<string> Persisted { get; } = [];
    public bool FailWrites { get; set; }

    public WordLoadSummary LoadInto(WordList list, AppSettings settings)
    {
        list.Replace(words, [], Persisted);
        return new WordLoadSummary(words.Count, 0, Persisted.Count, "memória");
    }

    public void PersistRejected(string word)
    {
        if (FailWrites)
            throw new IOException("disco cheio");
        Persisted.Add(word);
    }
}

internal sealed class FakeClipboard : IClipboard
{
    private sealed record Snapshot(string Text) : IClipboardSnapshot;

    public FakeClipboard(string content) => Content = content;

    public string Content { get; private set; }
    public uint SequenceNumber { get; private set; } = 1;
    public int Restores { get; private set; }

    /// <summary>Simula outro programa (o navegador) escrevendo na área de transferência.</summary>
    public void ExternalWrite(string text)
    {
        Content = text;
        SequenceNumber++;
    }

    public string? TryGetText() => Content;

    public IClipboardSnapshot? TakeSnapshot() => new Snapshot(Content);

    public void Restore(IClipboardSnapshot snapshot)
    {
        Restores++;
        ExternalWrite(((Snapshot)snapshot).Text);
    }
}
