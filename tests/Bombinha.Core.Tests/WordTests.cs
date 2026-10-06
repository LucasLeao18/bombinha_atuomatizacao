using Bombinha.Core.Settings;
using Bombinha.Core.Words;

namespace Bombinha.Core.Tests;

public class WordListTests
{
    private static WordList Make(IEnumerable<string>? blacklist = null, IEnumerable<string>? rejected = null)
    {
        var list = new WordList();
        list.Replace(["casa", "casaco", "bracelete", "abraco", "sol", "brasa"], blacklist ?? [], rejected ?? []);
        return list;
    }

    [Fact]
    public void Filtra_silaba_em_qualquer_posicao()
    {
        // No Bomb Party a sílaba pode estar em qualquer lugar da palavra.
        Assert.Equal(["abraco", "bracelete", "brasa"], Make().Filter("bra").Order());
    }

    [Fact]
    public void Respeita_blacklist_e_rejeitadas()
    {
        Assert.Equal(["bracelete"], Make(blacklist: ["brasa"], rejected: ["abraco"]).Filter("bra"));
    }

    [Fact]
    public void Exclui_palavras_ja_usadas()
    {
        Assert.Equal(["bracelete"], Make().Filter("bra", new HashSet<string> { "brasa", "abraco" }));
    }

    [Fact]
    public void Silaba_e_normalizada()
    {
        Assert.Equal(3, Make().Filter("  BRA ").Count);
        Assert.Empty(Make().Filter(""));
    }

    [Fact]
    public void Rejeitada_nao_duplica()
    {
        var list = Make();
        Assert.True(list.AddRejected("casa"));
        Assert.False(list.AddRejected("CASA"));
        Assert.True(list.IsRejected("casa"));
        Assert.Equal(1, list.RejectedCount);
    }

    [Fact]
    public void ParseList_normaliza_ignora_comentarios_e_remove_duplicatas()
    {
        var parsed = WordText.ParseList(new StringReader("Aarao\n\n# comentário\naarao\n CASA \ncasa\n"), allowComments: true);
        Assert.Equal(["aarao", "casa"], parsed);
    }

    [Fact]
    public void Arquivo_de_rejeitadas_persiste_e_relê()
    {
        string dir = Path.Combine(Path.GetTempPath(), "bombinha-tests-" + Guid.NewGuid().ToString("N"));
        try
        {
            var file = new WordListFile(Path.Combine(dir, "sub", "rejeitadas.txt"));
            file.Append("casa");
            Assert.Equal(1, file.Merge(["casa", "Brasa", ""]));
            Assert.Equal(["casa", "brasa"], file.ReadAll());
        }
        finally
        {
            if (Directory.Exists(dir))
                Directory.Delete(dir, recursive: true);
        }
    }
}

public class WordSelectorTests
{
    private readonly SelectionSettings _s = new() { TopN = 1 }; // sempre a melhor: determinístico
    private readonly WordSelector _sel = new(new Random(1));

    private string? Choose(IEnumerable<string> words, GameMode mode, string frag, double slack = 1.0) =>
        _sel.Choose(_sel.Rank(words, mode, frag, slack, _s), _s);

    [Fact]
    public void Modo_curta_prefere_palavra_curta() =>
        Assert.Equal("casa", Choose(["casa", "casamento", "casario"], GameMode.ShortWords, "cas"));

    [Fact]
    public void Modo_longa_prefere_palavra_longa() =>
        Assert.Equal("casamento", Choose(["casa", "casamento", "casario"], GameMode.LongWords, "cas"));

    [Fact]
    public void Prefixo_pesa_e_pode_ser_desligado()
    {
        _s.HuntNewLetters = false;
        _s.PreferPrefix = true;
        Assert.True(_sel.BaseScore("brasa", GameMode.Any, "bra", 1, _s) > _sel.BaseScore("abraco", GameMode.Any, "bra", 1, _s));

        _s.PreferPrefix = false;
        Assert.Equal(_sel.BaseScore("brasa", GameMode.Any, "bra", 1, _s), _sel.BaseScore("abraco", GameMode.Any, "bra", 1, _s), 9);
    }

    [Fact]
    public void Alfabeto_hibrido_so_pesa_quando_ha_folga()
    {
        _s.HuntNewLetters = true;
        _s.PreferPrefix = false;
        _sel.SetLettersUsed("abcdefghij");
        // "muxoxo" traz letras novas; "abaca" não traz nenhuma.
        Assert.Equal("muxoxo", Choose(["abaca", "muxoxo"], GameMode.Any, "a", slack: 1.0));
        Assert.Equal("abaca", Choose(["abaca", "muxoxo"], GameMode.Any, "a", slack: 0.0)); // empate: ordem do dicionário
    }

    [Fact]
    public void Bloqueadas_refletem_usadas_na_partida()
    {
        _sel.RegisterUse("casa", _s);
        Assert.Contains("casa", _sel.BlockedWords(_s));
        _s.BlockUsedInMatch = false;
        Assert.DoesNotContain("casa", _sel.BlockedWords(_s));
    }

    [Fact]
    public void Nova_partida_zera_so_o_que_e_da_partida()
    {
        _sel.RegisterUse("casa", _s);
        _sel.RegisterUse("casa", _s);
        _sel.NewMatch();
        Assert.Empty(_sel.UsedInMatch);
        Assert.Empty(_sel.LettersUsed);
        Assert.Equal(2, _sel.FrequencyOf("casa")); // estatística da sessão continua
    }

    [Fact]
    public void Alfabeto_completo_conta_vida_extra()
    {
        _sel.RegisterUse(string.Concat(WordSelector.AlphabetLetters), _s);
        Assert.Equal(1, _sel.AlphabetsCompleted);
        Assert.Empty(_sel.LettersUsed);
    }

    [Fact]
    public void Letras_ignoradas_e_acentuadas_nao_contam()
    {
        _sel.RegisterUse("kiwi", _s);
        _sel.RegisterUse("açaí", _s);
        Assert.DoesNotContain('k', _sel.LettersUsed);
        Assert.DoesNotContain('w', _sel.LettersUsed);
        Assert.DoesNotContain('ç', _sel.LettersUsed);
        Assert.Equal(["a", "i"], _sel.LettersUsed.Select(c => c.ToString()).Order());
    }

    [Fact]
    public void Alfabeto_tem_23_letras() => Assert.Equal(23, WordSelector.AlphabetLetters.Count);

    [Fact]
    public void Lista_vazia_devolve_null() => Assert.Null(Choose([], GameMode.ShortWords, "abc"));

    [Fact]
    public void Repeticao_penaliza_e_cooldown_respeita_configuracao_atual()
    {
        _s.HuntNewLetters = false;
        _s.PreferPrefix = false;
        _s.RepeatPenalty = 0.5;
        _s.RepeatCooldown = 1;
        _sel.RegisterUse("casa", _s);
        // 0.5 (frequência 1) × 0.5 (recente)
        Assert.Equal(0.25, _sel.BaseScore("casa", GameMode.Any, "ca", 1, _s), 9);

        _sel.RegisterUse("sol", _s); // cooldown 1: "casa" sai das recentes
        Assert.Equal(0.5, _sel.BaseScore("casa", GameMode.Any, "ca", 1, _s), 9);
    }

    [Fact]
    public void Sorteio_fica_entre_as_top_n()
    {
        _s.TopN = 2;
        var ranked = _sel.Rank(["a", "bb", "ccc", "dddd"], GameMode.LongWords, "x", 0, _s);
        for (int i = 0; i < 200; i++)
            Assert.Contains(_sel.Choose(ranked, _s), new[] { "dddd", "ccc" });
    }

    [Fact]
    public void Modo_alfabeto_prioriza_letras_novas()
    {
        _sel.SetLettersUsed("abc");
        Assert.Equal("fumego", Choose(["abaca", "fumego"], GameMode.Alphabet, "a"));
    }
}
