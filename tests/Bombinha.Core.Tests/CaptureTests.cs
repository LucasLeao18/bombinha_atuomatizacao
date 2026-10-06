using Bombinha.Core.Capture;
using Bombinha.Core.Logging;
using Bombinha.Core.Settings;
using Bombinha.Core.Tests.Fakes;
using Bombinha.Core.Typing;

namespace Bombinha.Core.Tests;

public class ClipboardSyllableReaderTests
{
    private readonly FakeClock _clock = new();
    private readonly FakeInput _input = new();
    private readonly MemoryLogSink _log = new();
    private readonly AppSettings _settings = new();

    private readonly SafeTarget _target = new();

    private ClipboardSyllableReader Reader(FakeClipboard clipboard) =>
        new(_input, clipboard, _clock, _target, new Logger(_log, "captura"));

    [Fact]
    public void Sequencia_auto_alterna_duplo_e_triplo() =>
        Assert.Equal([2, 3, 2], ClipboardSyllableReader.ClickSequence(ClickSelection.Auto, 3));

    [Fact]
    public void Sequencia_fixa_repete_o_mesmo_clique()
    {
        Assert.Equal([3, 3], ClipboardSyllableReader.ClickSequence(ClickSelection.TripleClick, 2));
        Assert.Equal([2], ClipboardSyllableReader.ClickSequence(ClickSelection.DoubleClick, 1));
    }

    [Fact]
    public void Espera_devolve_assim_que_o_clipboard_muda()
    {
        var clipboard = new FakeClipboard("velho");
        uint before = clipboard.SequenceNumber;
        int polls = 0;
        _clock.OnSleep = () =>
        {
            if (++polls == 3)
                clipboard.ExternalWrite("bra"); // só na 3ª espera o Ctrl+C "chega"
        };
        Assert.Equal("bra", Reader(clipboard).WaitForCopy(before, TimeSpan.FromSeconds(1), CancellationToken.None));
    }

    [Fact]
    public void Espera_desiste_no_timeout_quando_nada_e_copiado()
    {
        var clipboard = new FakeClipboard("SILABA ANTIGA");
        // Sequência intacta = Ctrl+C não copiou nada = null (e não o texto velho).
        Assert.Null(Reader(clipboard).WaitForCopy(clipboard.SequenceNumber, TimeSpan.FromMilliseconds(80), CancellationToken.None));
        Assert.True(_clock.Elapsed >= TimeSpan.FromMilliseconds(80));
    }

    [Fact]
    public void Captura_repete_ate_dar_certo_e_restaura_o_clipboard()
    {
        _settings.Capture.ClickSelection = ClickSelection.Auto;
        _settings.Capture.Attempts = 3;
        _settings.Capture.PreserveClipboard = true;
        var clipboard = new FakeClipboard("TEXTO DO USUARIO");
        var clicks = new List<int>();
        _input.OnEvent = input =>
        {
            if (input.Events[^1] != "chord:Control+C")
                return;
            int n = input.ClicksSinceLastMove();
            clicks.Add(n);
            if (n == 3)
                clipboard.ExternalWrite("  VEN  "); // o duplo-clique falha; o triplo seleciona e copia
        };

        string raw = Reader(clipboard).Read(_settings, CancellationToken.None);

        Assert.Equal("VEN", raw.Trim());
        Assert.Equal([2, 3], clicks);                       // tentou duplo, recuperou no triplo
        Assert.Equal("TEXTO DO USUARIO", clipboard.Content); // clipboard devolvido
        Assert.Contains(_log.Entries, e => e.Message.Contains("Nada selecionado", StringComparison.Ordinal));
    }

    [Fact]
    public void Captura_falhando_sempre_devolve_vazio_sem_mexer_no_clipboard()
    {
        _settings.Capture.Attempts = 2;
        var clipboard = new FakeClipboard("SILABA ANTIGA"); // Ctrl+C nunca funciona

        string raw = Reader(clipboard).Read(_settings, CancellationToken.None);

        // O essencial: NÃO devolve a sílaba velha, que faria o bot digitar a palavra errada.
        Assert.Equal("", raw);
        Assert.Equal("SILABA ANTIGA", clipboard.Content);
        Assert.Equal(0, clipboard.Restores); // nada mudou, então nada a restaurar
    }

    [Fact]
    public void Sem_preservar_nao_restaura()
    {
        _settings.Capture.PreserveClipboard = false;
        var clipboard = new FakeClipboard("meu texto");
        _input.OnEvent = input =>
        {
            if (input.Events[^1] == "chord:Control+C")
                clipboard.ExternalWrite("bra");
        };
        Assert.Equal("bra", Reader(clipboard).Read(_settings, CancellationToken.None));
        Assert.Equal(0, clipboard.Restores);
    }

    [Fact]
    public void Nao_copia_se_o_clique_nao_deu_foco_ao_jogo()
    {
        var clipboard = new FakeClipboard("texto do usuário em outro programa");
        _target.Result = TargetCheck.Unsafe("foco em outra janela");
        _input.OnEvent = input =>
        {
            if (input.Events[^1] == "chord:Control+C")
                clipboard.ExternalWrite("algo copiado de outro programa");
        };

        Assert.Equal("", Reader(clipboard).Read(_settings, CancellationToken.None));
        Assert.DoesNotContain("chord:Control+C", _input.Events);
        Assert.Contains(_log.Entries, e => e.Message.Contains("foco em outra janela", StringComparison.Ordinal));
    }

    private sealed class NoScreen : Bombinha.Core.Detection.IScreenCapture
    {
        public Bombinha.Core.Imaging.PixelBuffer Capture(Bombinha.Core.Common.ScreenRect rect) => throw new InvalidOperationException();
        public Bombinha.Core.Common.ScreenRect MonitorBoundsAt(Bombinha.Core.Common.ScreenPoint point) => default;
    }

    private sealed class NoOcr : IOcrEngine
    {
        public bool IsAvailable => false;
        public string? UnavailableReason => "teste";
        public string Recognize(Bombinha.Core.Imaging.OcrImage image) => "";
    }

    [Fact]
    public void Texto_longo_nao_e_aceito_como_silaba_nem_vai_inteiro_para_o_log()
    {
        const string secret = "senha super secreta do usuario copiada de outro programa";
        var clipboard = new FakeClipboard("");
        _input.OnEvent = input =>
        {
            if (input.Events[^1] == "chord:Control+C")
                clipboard.ExternalWrite(secret);
        };
        var logger = new Logger(_log, "captura");
        var capture = new SyllableCapture(Reader(clipboard), new OcrSyllableReader(new NoScreen(), new NoOcr(), logger), logger);

        Assert.Equal("", capture.Capture(_settings, CancellationToken.None));
        Assert.Contains(_log.Entries, e => e.Message.Contains("não parece uma sílaba", StringComparison.Ordinal));
        Assert.DoesNotContain(_log.Entries, e => e.Message.Contains("secreta", StringComparison.Ordinal));
    }

    [Theory]
    [InlineData("  VEN  ", "ven")]
    [InlineData("Ção!", "ção")]
    [InlineData("a1b2", "ab")]
    [InlineData(null, "")]
    [InlineData("🙂", "")]
    public void Normalizacao_mantem_so_letras(string? raw, string expected) =>
        Assert.Equal(expected, SyllableText.Normalize(raw));
}

public class TypingPlannerTests
{
    private static readonly TimingSettings Timing = new() { BeforeTypingMs = 200 };

    private static HumanizationSettings Calm() => new()
    {
        TypoChance = 0,
        JokePhraseChance = 0,
        RehearsalChance = 0,
        DeliberateFailChance = 0,
        WrongEnterChance = 0,
    };

    [Fact]
    public void Palavra_sem_humanizacao_digita_exatamente_a_palavra()
    {
        var plan = new TypingPlanner(new Random(1)).Word("bracelete", Calm(), Timing, think: false, numbers: false);
        Assert.IsType<TypingStep.ClearField>(plan.Steps[0]); // limpa sobras antes de digitar
        Assert.IsType<TypingStep.Submit>(plan.Steps.Last(s => s is not TypingStep.Wait));
        Assert.Equal("bracelete", plan.SubmittedText);
    }

    [Fact]
    public void Erros_de_digitacao_sempre_sao_corrigidos()
    {
        var h = Calm();
        h.TypoChance = 1.0;
        var plan = new TypingPlanner(new Random(3)).Word("casa", h, Timing, false, false);
        Assert.Equal("casa", plan.SubmittedText);
        Assert.Equal(4, plan.Steps.Count(s => s is TypingStep.Backspace));
    }

    [Fact]
    public void Numeros_inseridos_aparecem_no_texto_enviado()
    {
        var plans = Enumerable.Range(0, 30)
            .Select(seed => new TypingPlanner(new Random(seed)).Word("bracelete", Calm(), Timing, false, numbers: true))
            .ToList();
        Assert.Contains(plans, p => p.SubmittedText!.Any(char.IsDigit));
        Assert.All(plans, p => Assert.Equal("bracelete", new string(p.SubmittedText!.Where(char.IsLetter).ToArray())));
    }

    [Fact]
    public void Pensar_pausa_depois_da_terceira_letra()
    {
        var h = Calm();
        h.ThinkAfterThreeMs = 700;
        var steps = new TypingPlanner(new Random(1)).Word("brasa", h, Timing, think: true, numbers: false).Steps;
        int third = steps.Select((s, i) => (s, i)).Where(x => x.s is TypingStep.TypeText).ElementAt(2).i;
        // depois da 3ª letra: intervalo entre teclas e, em seguida, a pausa de "pensar"
        Assert.Equal(new TypingStep.Wait(TimeSpan.FromMilliseconds(Timing.KeyIntervalMs)), steps[third + 1]);
        Assert.Equal(new TypingStep.Wait(TimeSpan.FromMilliseconds(700)), steps[third + 2]);
    }

    [Fact]
    public void Mesmo_seed_gera_mesmo_roteiro()
    {
        var h = new HumanizationSettings { JokePhraseChance = 0.5, RehearsalChance = 0.5 };
        string Describe(int seed)
        {
            var planner = new TypingPlanner(new Random(seed));
            var script = planner.BuildRound("bracelete", planner.SampleTriggers(h), true, false, h, Timing);
            return string.Join("|", script.Plans.SelectMany(p => p.Steps));
        }
        Assert.Equal(Describe(42), Describe(42));
    }

    [Fact]
    public void Typo_troca_exatamente_uma_letra_em_palavras_longas()
    {
        var planner = new TypingPlanner(new Random(5));
        for (int i = 0; i < 100; i++)
        {
            string typo = planner.Typo("bracelete", 3);
            Assert.Equal(9, typo.Length);
            Assert.Equal(1, typo.Zip("bracelete").Count(p => p.First != p.Second));
        }
        Assert.Equal(4, planner.Typo("sol", 3).Length); // curtas ganham uma letra a mais
        Assert.StartsWith("sol", planner.Typo("sol", 3), StringComparison.Ordinal);
    }

    [Fact]
    public void Ensaio_e_um_pedaco_da_palavra()
    {
        var planner = new TypingPlanner(new Random(2));
        Assert.Equal("so...", planner.Rehearsal("sol"));
        for (int i = 0; i < 50; i++)
        {
            string r = planner.Rehearsal("bracelete");
            string prefix = r.TrimEnd('.', '!');
            Assert.InRange(prefix.Length, 2, 5);
            Assert.StartsWith(prefix, "bracelete", StringComparison.Ordinal);
        }
    }

    [Fact]
    public void Rodada_com_falha_proposital_envia_palavra_errada()
    {
        var planner = new TypingPlanner(new Random(1));
        var script = planner.BuildRound("bracelete", new RoundTriggers(false, false, true, false), false, false, Calm(), Timing);
        Assert.Equal(RoundStyle.DeliberateFailure, script.Style);
        Assert.Single(script.Plans);
        Assert.NotEqual("bracelete", script.Plans[0].SubmittedText);
    }

    [Fact]
    public void Rodada_normal_com_frase_e_ensaio_apaga_antes_da_resposta()
    {
        var planner = new TypingPlanner(new Random(1));
        var script = planner.BuildRound("bracelete", new RoundTriggers(true, true, false, false), false, false, Calm(), Timing);
        Assert.Equal(3, script.Plans.Count);
        Assert.False(script.Plans[0].Submits);
        Assert.IsType<TypingStep.ClearField>(script.Plans[0].Steps.Last(s => s is not TypingStep.Wait));
        Assert.False(script.Plans[1].Submits);
        Assert.Equal("bracelete", script.Plans[2].SubmittedText);
        Assert.Equal(["frase", "ensaio"], script.Flags);
    }

    [Fact]
    public void Duracao_estimada_soma_esperas_e_custos()
    {
        var t = new TimingSettings { KeyIntervalMs = 0 };
        var plan = TypingPlanner.Quick("abc", t);
        var expected = TypingPlan.ClearFieldCost + TimeSpan.FromMilliseconds(50)
                       + (3 * (TypingPlan.KeyCost + TimeSpan.FromMilliseconds(1))) + TypingPlan.SubmitCost;
        Assert.Equal(expected, plan.EstimatedDuration);
    }

    [Fact]
    public void Cada_tecla_e_seguida_do_intervalo_minimo()
    {
        var t = new TimingSettings { KeyIntervalMs = 100 };
        var steps = TypingPlanner.Quick("abc", t).Steps;
        var interval = new TypingStep.Wait(TimeSpan.FromMilliseconds(100));
        for (int i = 0; i < steps.Count; i++)
        {
            if (steps[i] is TypingStep.TypeText or TypingStep.Submit or TypingStep.ClearField)
                Assert.Equal(interval, steps[i + 1]);
        }
        Assert.Equal(interval, steps[^1]); // inclusive depois do ENTER
        Assert.True(TypingPlanner.Quick("abc", t).EstimatedDuration >= TimeSpan.FromMilliseconds(500));
    }

    [Fact]
    public void Texto_visivel_ignora_a_limpeza_inicial()
    {
        var plan = TypingPlanner.Quick("casa", new TimingSettings());
        Assert.Equal("casa", plan.SubmittedText);
        var scratch = new TypingPlanner(new Random(1)).Scratch("oi", Calm(), Timing, "frase");
        Assert.Equal("oi", scratch.VisibleText());
    }

    [Fact]
    public void Frases_customizadas_somam_as_padrao()
    {
        var h = Calm();
        h.CustomPhrases = ["minha frase"];
        var planner = new TypingPlanner(new Random(1));
        var seen = Enumerable.Range(0, 300).Select(_ => planner.JokePhrase(h)).ToHashSet();
        Assert.Contains("minha frase", seen);
        Assert.Contains(TypingPlanner.DefaultJokePhrases[0], seen);
    }
}

public class TypingExecutorTests
{
    private readonly FakeInput _input = new();
    private readonly FakeClock _clock = new();
    private readonly MemoryLogSink _log = new();

    private sealed class Guard(bool result) : ISubmitGuard
    {
        public int Calls { get; private set; }
        public bool ConfirmTurnForSubmit(CancellationToken ct)
        {
            Calls++;
            return result;
        }
    }

    private TypingExecutor Executor(bool turnOk = true, TargetCheck? target = null) =>
        new(_input, _clock, new Guard(turnOk), new SafeTarget { Result = target ?? TargetCheck.Safe }, new Logger(_log, "digitação"));

    [Fact]
    public void Executa_o_roteiro_e_envia()
    {
        var outcome = Executor().Execute(TypingPlanner.Quick("casa", new TimingSettings()), new(10, 20), testMode: false, CancellationToken.None);
        Assert.Equal(PlanOutcome.Completed, outcome);
        Assert.Equal(["casa"], _input.Submitted);
        Assert.Equal("move(10, 20)", _input.Events[0]);
    }

    [Fact]
    public void Turno_perdido_nao_aperta_enter()
    {
        var outcome = Executor(turnOk: false).Execute(TypingPlanner.Quick("casa", new TimingSettings()), new(1, 1), false, CancellationToken.None);
        Assert.Equal(PlanOutcome.TurnLost, outcome);
        Assert.DoesNotContain("key:Enter", _input.Events);
    }

    [Fact]
    public void Alvo_inseguro_nao_digita_nada()
    {
        var outcome = Executor(target: TargetCheck.Unsafe("Bombinha está por cima do jogo"))
            .Execute(TypingPlanner.Quick("casa", new TimingSettings()), new(1, 1), false, CancellationToken.None);
        Assert.Equal(PlanOutcome.UnsafeTarget, outcome);
        Assert.DoesNotContain(_input.Events, e => e.StartsWith("type:", StringComparison.Ordinal));
    }

    [Fact]
    public void Modo_teste_so_registra()
    {
        var outcome = Executor().Execute(TypingPlanner.Quick("casa", new TimingSettings()), new(1, 1), testMode: true, CancellationToken.None);
        Assert.Equal(PlanOutcome.Completed, outcome);
        Assert.Empty(_input.Events);
        Assert.Contains(_log.Entries, e => e.Message.Contains("[TESTE]", StringComparison.Ordinal) && e.Message.Contains("casa", StringComparison.Ordinal));
    }

    [Fact]
    public void Cancelamento_interrompe_no_meio_da_palavra()
    {
        using var cts = new CancellationTokenSource();
        _input.OnEvent = input =>
        {
            if (input.Events.Count(e => e.StartsWith("type:", StringComparison.Ordinal)) == 2)
                cts.Cancel(); // F8 apertado depois de 2 letras
        };
        Assert.Throws<OperationCanceledException>(() =>
            Executor().Execute(TypingPlanner.Quick("bracelete", new TimingSettings()), new(1, 1), false, cts.Token));
        Assert.Equal(2, _input.Events.Count(e => e.StartsWith("type:", StringComparison.Ordinal)));
        Assert.DoesNotContain("key:Enter", _input.Events);
    }
}
