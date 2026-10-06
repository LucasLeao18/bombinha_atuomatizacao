using Bombinha.Core.Common;
using Bombinha.Core.Engine;
using Bombinha.Core.Logging;
using Bombinha.Core.Settings;
using Bombinha.Core.Tests.Fakes;
using Bombinha.Core.Typing;
using Bombinha.Core.Words;

namespace Bombinha.Core.Tests;

/// <summary>Monta um motor completo com fakes; digitação e planejador são os reais.</summary>
internal sealed class EngineHarness
{
    public EngineHarness(IReadOnlyList<string> words, bool[] stillMyTurn, Action<AppSettings>? configure = null, int seed = 7)
    {
        Settings = new AppSettings();
        Settings.Verification.VerificationDelayMs = 50;
        Settings.Selection.TopN = 1;
        Settings.Selection.ShowTopInConsole = false;
        var h = Settings.Humanization;
        h.DeliberateFailChance = 0;
        h.WrongEnterChance = 0;
        h.JokePhraseChance = 0;
        h.RehearsalChance = 0;
        h.ThinkAfterThree = false;
        configure?.Invoke(Settings);

        Detector = new FakeDetector(stillMyTurn);
        Repo = new InMemoryWordRepository(words);
        Repo.LoadInto(Words, Settings);
        Engine = new BotEngine(new EngineServices(Detector, new FakeSyllables(), Input, Target, Clock,
            new Random(seed), Words, Repo, () => Settings, new Logger(Log, "teste")));
        Engine.InitializeSession(Settings);
        Engine.MarkTurnForTest(true);
    }

    public AppSettings Settings { get; }
    public FakeDetector Detector { get; }
    public FakeInput Input { get; } = new();
    public SafeTarget Target { get; } = new();
    public FakeClock Clock { get; } = new();
    public WordList Words { get; } = new();
    public InMemoryWordRepository Repo { get; }
    public MemoryLogSink Log { get; } = new();
    public BotEngine Engine { get; }

    public void Play(string syllable) => Engine.PlayRound(syllable, Settings, CancellationToken.None);

    public bool Logged(string fragment) => Log.Entries.Any(e => e.Message.Contains(fragment, StringComparison.Ordinal));
}

public class EngineFeedbackTests
{
    [Fact]
    public void Palavra_aceita_e_registrada()
    {
        // Depois do ENTER a vez passou = o jogo aceitou.
        var t = new EngineHarness(["brasa", "abraco"], [false]);
        t.Play("bra");

        var snap = t.Engine.GetSnapshot();
        Assert.Single(t.Input.Submitted);
        Assert.Equal(1, snap.Accepted);
        Assert.Equal(0, snap.Rejected);
        Assert.Equal(t.Input.Submitted, snap.History.Select(x => x.Word));
        Assert.Contains(t.Input.Submitted[0], t.Engine.SelectorForTest.UsedInMatch);
    }

    [Fact]
    public void Erros_de_digitacao_sao_corrigidos_antes_do_enter()
    {
        var t = new EngineHarness(["bracelete"], [false], s => s.Humanization.TypoChance = 1.0);
        t.Play("bra");
        Assert.Equal(["bracelete"], t.Input.Submitted);
        Assert.Contains("key:Backspace", t.Input.Events);
    }

    [Fact]
    public void Recusa_tenta_outra_palavra()
    {
        // 1ª continua sendo minha vez (recusada), 2ª passa (aceita).
        var t = new EngineHarness(["brasa", "abraco"], [true, false]);
        t.Play("bra");

        Assert.Equal(2, t.Input.Submitted.Count);
        Assert.NotEqual(t.Input.Submitted[0], t.Input.Submitted[1]);
        Assert.Equal(1, t.Engine.GetSnapshot().Rejected);
        Assert.Equal(1, t.Engine.GetSnapshot().Accepted);
    }

    [Fact]
    public void Nao_repete_palavra_ja_usada_na_partida()
    {
        var t = new EngineHarness(["brasa", "abraco"], [false, false]);
        t.Play("bra");
        t.Engine.MarkTurnForTest(true);
        t.Play("bra");

        Assert.Equal(2, t.Input.Submitted.Count);
        Assert.NotEqual(t.Input.Submitted[0], t.Input.Submitted[1]);
    }

    [Fact]
    public void Duas_recusas_aprendem_a_palavra()
    {
        var t = new EngineHarness(["brasa"], [true, true], s => s.Verification.MaxAttemptsPerRound = 1);
        t.Play("bra");                          // 1º strike
        t.Engine.MarkTurnForTest(true);
        t.Engine.SelectorForTest.NewMatch();    // libera a palavra de novo
        t.Play("bra");                          // 2º strike → aprende

        Assert.Equal(2, t.Engine.StrikesFor("brasa"));
        Assert.True(t.Words.IsRejected("brasa"));
        Assert.Equal(["brasa"], t.Repo.Persisted);
        Assert.Empty(t.Words.Filter("bra")); // e a partir daí ela some das candidatas
    }

    [Fact]
    public void Falha_ao_gravar_rejeitada_e_reportada_como_erro()
    {
        var t = new EngineHarness(["brasa"], [true, true], s => s.Verification.MaxAttemptsPerRound = 1);
        t.Repo.FailWrites = true;
        t.Play("bra");
        t.Engine.MarkTurnForTest(true);
        t.Engine.SelectorForTest.NewMatch();
        t.Play("bra");

        Assert.Contains(t.Log.Entries, e => e.Level == LogLevel.Error && e.Message.Contains("não foi possível gravar", StringComparison.Ordinal));
    }

    [Fact]
    public void Verificacao_desligada_aceita_tudo()
    {
        var t = new EngineHarness(["brasa"], [true], s => s.Verification.VerifySubmission = false);
        t.Play("bra");
        Assert.Equal(1, t.Engine.GetSnapshot().Accepted);
        Assert.Equal(0, t.Detector.StillMyTurnQueries); // nem chegou a perguntar
    }

    [Fact]
    public void Para_quando_acabam_as_tentativas()
    {
        var t = new EngineHarness(["brasa", "abraco"], [true, true, true], s => s.Verification.MaxAttemptsPerRound = 2);
        t.Play("bra");
        Assert.Equal(2, t.Input.Submitted.Count);
        Assert.Equal(2, t.Engine.GetSnapshot().Rejected);
        Assert.True(t.Logged("tentativas sem sucesso"));
    }

    [Fact]
    public void Sem_candidatas_manda_frase_de_desistencia()
    {
        var t = new EngineHarness(["casa"], [false]);
        t.Play("xyz");
        Assert.Equal([t.Settings.General.GiveUpPhrase], t.Input.Submitted);
        Assert.Equal(0, t.Engine.GetSnapshot().Accepted); // desistência não conta como acerto
    }

    [Fact]
    public void Frase_de_desistencia_vazia_nao_envia_nada()
    {
        var t = new EngineHarness(["casa"], [false], s => s.General.GiveUpPhrase = "");
        t.Play("xyz");
        Assert.Empty(t.Input.Submitted);
    }

    [Fact]
    public void Turno_perdido_no_enter_cancela_sem_enviar()
    {
        var t = new EngineHarness(["brasa"], [false]);
        t.Detector.ConfirmResult = false;
        t.Play("bra");
        Assert.Empty(t.Input.Submitted);
        Assert.DoesNotContain("key:Enter", t.Input.Events);
        Assert.Equal(0, t.Engine.GetSnapshot().Accepted);
    }

    [Fact]
    public void Janela_errada_em_foco_bloqueia_a_digitacao()
    {
        var t = new EngineHarness(["brasa"], [false]);
        t.Target.Result = Bombinha.Core.Typing.TargetCheck.Unsafe("outra janela");
        t.Play("bra");
        Assert.DoesNotContain(t.Input.Events, e => e.StartsWith("type:", StringComparison.Ordinal));
        Assert.True(t.Logged("outra janela"));
    }

    [Fact]
    public void Modo_teste_nao_envia_teclas()
    {
        var t = new EngineHarness(["brasa"], [true], s => s.General.TestMode = true);
        t.Play("bra");
        Assert.Empty(t.Input.Events);
        Assert.Equal(1, t.Engine.GetSnapshot().Accepted);
        Assert.True(t.Logged("[TESTE]"));
    }

    [Fact]
    public void Falha_proposital_nao_conta_contra_a_palavra_e_depois_envia_a_certa()
    {
        var t = new EngineHarness(["bracelete"], [false], s => s.Humanization.DeliberateFailChance = 1.0);
        t.Play("bra");

        Assert.Equal(2, t.Input.Submitted.Count);
        Assert.NotEqual("bracelete", t.Input.Submitted[0]);
        Assert.Equal("bracelete", t.Input.Submitted[1]); // 2ª tentativa é "apressada": sem encenação
        var snap = t.Engine.GetSnapshot();
        Assert.Equal(1, snap.DeliberateFailures);
        Assert.Equal(0, snap.Rejected);
        Assert.Equal(1, snap.Accepted);
    }

    [Fact]
    public void Erro_e_enter_envia_errada_e_depois_correta()
    {
        var t = new EngineHarness(["bracelete"], [false], s => s.Humanization.WrongEnterChance = 1.0);
        t.Play("bra");
        Assert.Equal(2, t.Input.Submitted.Count);
        Assert.NotEqual("bracelete", t.Input.Submitted[0]);
        Assert.Equal("bracelete", t.Input.Submitted[1]);
        Assert.Equal(1, t.Engine.GetSnapshot().Accepted);
    }

    [Fact]
    public void Recusa_com_digitos_inseridos_nao_gera_strike()
    {
        // Procura (deterministicamente) um seed cujo sorteio insira dígitos na primeira digitação.
        for (int seed = 1; seed <= 50; seed++)
        {
            var t = new EngineHarness(["bracelete"], [true, false], s =>
            {
                s.Humanization.InsertNumbers = true;
                s.Humanization.NumberRounds = 5;
            }, seed);
            t.Play("bra");
            if (t.Input.Submitted[0].All(char.IsLetter))
                continue;

            Assert.Equal(0, t.Engine.StrikesFor("bracelete"));
            Assert.Equal(0, t.Engine.GetSnapshot().Rejected);
            Assert.Equal("bracelete", t.Input.Submitted[1]); // nova tentativa sem dígitos
            Assert.Equal(1, t.Engine.GetSnapshot().Accepted);
            return;
        }
        Assert.Fail("Nenhum seed inseriu dígitos.");
    }

    [Fact]
    public void Nova_partida_zera_estado_da_partida()
    {
        var t = new EngineHarness(["brasa"], [false]);
        t.Play("bra");
        t.Engine.NewMatch("teste");
        Assert.Empty(t.Engine.SelectorForTest.UsedInMatch);
        Assert.Equal(1, t.Engine.GetSnapshot().Matches);
        Assert.Single(t.Engine.GetSnapshot().History); // histórico é da sessão
    }

    [Fact]
    public void Inatividade_inicia_nova_partida_automaticamente()
    {
        var t = new EngineHarness(["brasa"], [false], s => s.Verification.InactivityNewMatchSeconds = 30);
        t.Play("bra");
        t.Clock.Advance(TimeSpan.FromSeconds(31));
        t.Engine.RunCycle(t.Settings, CancellationToken.None); // detector: não é minha vez
        Assert.Empty(t.Engine.SelectorForTest.UsedInMatch);
        Assert.True(t.Logged("sem turnos"));
    }

    [Fact]
    public void Tempo_curto_corta_a_encenacao()
    {
        var t = new EngineHarness(["bracelete"], [false], s =>
        {
            s.Humanization.JokePhraseChance = 1.0;
            s.Humanization.LetterDelayMs = 150;
            s.Timing.RoundTimeLimitSeconds = 0.5;
        });
        t.Play("bra");
        Assert.Equal(["bracelete"], t.Input.Submitted);
        // frase engraçada não foi digitada: só as 9 letras da palavra
        Assert.Equal(9, t.Input.Events.Count(e => e.StartsWith("type:", StringComparison.Ordinal)));
        Assert.True(t.Logged("Tempo curto"));
    }
}

public class TurnClockTests
{
    [Fact]
    public void Folga_cai_conforme_o_turno_passa()
    {
        var clock = new FakeClock();
        var turn = new TurnClock(clock);
        turn.Mark(true);
        Assert.Equal(1.0, turn.Slack(4.0), 3);

        clock.Advance(TimeSpan.FromSeconds(2));
        Assert.Equal(0.5, turn.Slack(4.0), 3);
        Assert.Equal(2.0, turn.Remaining(4.0).TotalSeconds, 3);

        clock.Advance(TimeSpan.FromSeconds(5)); // estourou o orçamento
        Assert.Equal(0.0, turn.Slack(4.0));
        Assert.Equal(TimeSpan.Zero, turn.Remaining(4.0));
    }

    [Fact]
    public void Cronometro_so_reinicia_na_virada()
    {
        var clock = new FakeClock();
        var turn = new TurnClock(clock);
        turn.Mark(true);
        clock.Advance(TimeSpan.FromSeconds(1));
        turn.Mark(true); // continua sendo minha vez
        Assert.Equal(1.0, turn.ElapsedInTurn.TotalSeconds, 3);

        turn.Mark(false);
        turn.Mark(true); // nova virada
        Assert.Equal(TimeSpan.Zero, turn.ElapsedInTurn);
    }

    [Fact]
    public void Fora_do_turno_nao_ha_tempo_gasto()
    {
        var turn = new TurnClock(new FakeClock());
        Assert.Equal(TimeSpan.Zero, turn.ElapsedInTurn);
    }
}

public class EngineLifecycleTests
{
    private static (BotEngine Engine, MemoryLogSink Log) Build(FakeDetector detector)
    {
        var settings = new AppSettings();
        settings.Timing.CycleDelayMs = 50;
        var log = new MemoryLogSink();
        var words = new WordList();
        var engine = new BotEngine(new EngineServices(detector, new FakeSyllables(), new FakeInput(), new SafeTarget(),
            new StopwatchClock(), new Random(1), words, new InMemoryWordRepository(["casa"]), () => settings,
            new Logger(log, "teste")));
        return (engine, log);
    }

    private static void WaitUntil(Func<bool> condition)
    {
        var deadline = DateTime.UtcNow.AddSeconds(5);
        while (!condition() && DateTime.UtcNow < deadline)
            Thread.Sleep(10);
        Assert.True(condition());
    }

    [Fact]
    public void Inicia_aguarda_turno_e_para_rapidamente()
    {
        var (engine, log) = Build(new FakeDetector());
        using (engine)
        {
            Assert.True(engine.Start());
            Assert.False(engine.Start()); // já está rodando
            WaitUntil(() => engine.Status == EngineStatus.WaitingForTurn);
            Assert.Equal(1, engine.GetSnapshot().DictionaryCount); // carregou o dicionário ao iniciar

            engine.Stop();
            Assert.True(engine.WaitForExit(TimeSpan.FromSeconds(2)));
            Assert.Equal(EngineStatus.Stopped, engine.Status);
            Assert.Contains(log.Entries, e => e.Message.Contains("parada", StringComparison.Ordinal));
        }
    }

    [Fact]
    public void Erros_seguidos_interrompem_com_status_de_falha()
    {
        var detector = new FakeDetector { DetectTurnResult = () => throw new InvalidOperationException("tela indisponível") };
        var (engine, log) = Build(detector);
        using (engine)
        {
            engine.Start();
            Assert.True(engine.WaitForExit(TimeSpan.FromSeconds(5)));
            Assert.Equal(EngineStatus.Faulted, engine.Status);
            Assert.Equal(5, log.Entries.Count(e => e.Level == LogLevel.Error));
            Assert.Contains(log.Entries, e => e.Level == LogLevel.Critical);
            Assert.All(log.Entries.Where(e => e.Level == LogLevel.Error), e => Assert.NotNull(e.Exception));
        }
    }
}
