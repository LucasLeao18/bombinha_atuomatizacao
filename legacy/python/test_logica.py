"""Testes da lógica pura (dicionário, seleção e tempo de rodada).

Rode com:  python test_logica.py
Não abre janela nem toca no jogo — só as partes determinísticas.
"""

import os
import sys
import random
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from codigov4 import (AppConfig, Dicionario, Selecionador, Modo,
                      LETRAS_ALFABETO, IGNORADAS_ALFABETO, clamp)


class TestDicionario(unittest.TestCase):
    def setUp(self):
        self.d = Dicionario()
        self.d.palavras = ["casa", "casaco", "bracelete", "abraco", "sol", "brasa"]

    def test_filtra_silaba_em_qualquer_posicao(self):
        # No Bomb Party a sílaba pode estar em qualquer lugar da palavra
        self.assertEqual(sorted(self.d.filtrar("bra")), ["abraco", "bracelete", "brasa"])

    def test_respeita_blacklist_e_rejeitadas(self):
        self.d.blacklist = {"brasa"}
        self.d.rejeitadas = {"abraco"}
        self.assertEqual(self.d.filtrar("bra"), ["bracelete"])

    def test_exclui_palavras_ja_usadas(self):
        self.assertEqual(self.d.filtrar("bra", excluir={"brasa", "abraco"}), ["bracelete"])

    def test_registrar_rejeitada_persiste(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "rej.txt")
            self.assertTrue(self.d.registrar_rejeitada("casa", path))
            self.assertFalse(self.d.registrar_rejeitada("casa", path))  # não duplica

            outro = Dicionario()
            outro.carregar_rejeitadas(path)
            self.assertEqual(outro.rejeitadas, {"casa"})


class TestSelecionador(unittest.TestCase):
    def setUp(self):
        random.seed(1)
        self.cfg = AppConfig()
        self.cfg.mostrar_top_n = 1  # sempre pega o melhor, deixa o teste determinístico
        self.sel = Selecionador(self.cfg)

    def test_modo_curta_prefere_palavra_curta(self):
        escolha = self.sel.escolher(["casa", "casamento", "casario"], Modo.CURTA.value, "cas")
        self.assertEqual(escolha, "casa")

    def test_modo_longa_prefere_palavra_longa(self):
        escolha = self.sel.escolher(["casa", "casamento", "casario"], Modo.LONGA.value, "cas")
        self.assertEqual(escolha, "casamento")

    def test_prefixo_desliga(self):
        self.cfg.alfabeto_hibrido = False
        self.cfg.preferir_prefixo = True
        com = self.sel._score_base("brasa", Modo.QUALQUER.value, "bra")
        sem = self.sel._score_base("abraco", Modo.QUALQUER.value, "bra")
        self.assertGreater(com, sem)

        self.cfg.preferir_prefixo = False
        self.assertAlmostEqual(self.sel._score_base("brasa", Modo.QUALQUER.value, "bra"),
                               self.sel._score_base("abraco", Modo.QUALQUER.value, "bra"))

    def test_alfabeto_hibrido_so_pesa_quando_ha_folga(self):
        self.cfg.alfabeto_hibrido = True
        self.cfg.preferir_prefixo = False
        self.sel.letras_usadas = set("abcdefghij")
        # "muxoxo" traz letras novas; "abaca" não traz nenhuma
        com_folga = self.sel.escolher(["abaca", "muxoxo"], Modo.QUALQUER.value, "a", folga=1.0)
        sem_folga = self.sel.escolher(["abaca", "muxoxo"], Modo.QUALQUER.value, "a", folga=0.0)
        self.assertEqual(com_folga, "muxoxo")
        self.assertEqual(sem_folga, "abaca")  # empate resolvido sem o bônus

    def test_bloqueadas_reflete_usadas_na_partida(self):
        self.sel.registrar_uso("casa", Modo.QUALQUER.value)
        self.assertIn("casa", self.sel.bloqueadas())
        self.cfg.bloquear_usadas_na_partida = False
        self.assertNotIn("casa", self.sel.bloqueadas())

    def test_nova_partida_zera_o_que_e_da_partida(self):
        self.sel.registrar_uso("casa", Modo.QUALQUER.value)
        self.sel.frequencia["casa"] = 3
        self.sel.nova_partida()
        self.assertEqual(self.sel.usadas_partida, set())
        self.assertEqual(self.sel.letras_usadas, set())
        self.assertEqual(self.sel.frequencia["casa"], 3)  # estatística da sessão continua

    def test_alfabeto_completo_conta_vida_extra(self):
        # uma palavra artificial com todas as 23 letras úteis
        self.sel.registrar_uso("".join(LETRAS_ALFABETO), Modo.ALFABETO.value)
        self.assertEqual(self.sel.alfabeto_completado, 1)
        self.assertEqual(self.sel.letras_usadas, set())

    def test_letras_ignoradas_nao_contam(self):
        self.sel.registrar_uso("kiwi", Modo.ALFABETO.value)
        self.assertFalse(self.sel.letras_usadas & IGNORADAS_ALFABETO)

    def test_lista_vazia_devolve_none(self):
        self.assertIsNone(self.sel.escolher([], Modo.CURTA.value, "abc"))


class TyperFalso:
    """Digitador de mentira: registra o que seria enviado, sem tocar no teclado."""

    def __init__(self):
        self.enviadas = []

    def _envia(self, palavra):
        self.enviadas.append(palavra)
        return True

    def digitar(self, palavra, pos, override_nums=False):
        return self._envia(palavra)

    def digitar_quick(self, palavra, pos):
        return self._envia(palavra)

    def digitar_pensando_3(self, palavra, pos, think_ms=500, override_nums=False):
        return self._envia(palavra)

    def estimate_round_time(self, palavra, **kwargs):
        return 0.3, {"typing": 0.3}


class CapturadorFalso:
    """Devolve uma sequência pré-programada de 'ainda é a minha vez?'."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.consultas = 0

    def turno_ativo(self):
        self.consultas += 1
        return self.respostas.pop(0) if self.respostas else False


def montar_bot(palavras, respostas_turno, **cfg_kwargs):
    from codigov4 import BotCore, PosicoesManager
    cfg = AppConfig()
    cfg.delay_verificacao_ms = 1
    cfg.mostrar_top_n = 0
    cfg.humanizar.chance_falha_proposital = 0.0
    cfg.humanizar.chance_erro_enter = 0.0
    cfg.humanizar.chance_frase_engracada = 0.0
    cfg.humanizar.chance_ensaio_palavra = 0.0
    cfg.humanizar.pensar_3letras = False
    for k, v in cfg_kwargs.items():
        setattr(cfg, k, v)

    logs = []
    bot = BotCore(cfg, PosicoesManager(), logs.append)
    bot.dict.palavras = list(palavras)
    bot.typer = TyperFalso()
    bot.capt = CapturadorFalso(respostas_turno)
    bot.executando = True
    bot._marcar_turno(True)
    return bot, logs


class TestCicloDeFeedback(unittest.TestCase):
    """A parte nova mais crítica: descobrir se o JKLM aceitou a palavra."""

    def test_palavra_aceita_e_registrada(self):
        # turno_ativo False = a vez passou = o jogo aceitou
        bot, _ = montar_bot(["brasa", "abraco"], [False])
        bot._jogar_rodada("bra")

        self.assertEqual(len(bot.typer.enviadas), 1)
        self.assertEqual(bot.aceitas, 1)
        self.assertEqual(bot.recusadas, 0)
        self.assertEqual(bot.historico, bot.typer.enviadas)
        self.assertIn(bot.typer.enviadas[0], bot.selector.usadas_partida)

    def test_recusa_tenta_outra_palavra(self):
        # 1ª continua sendo minha vez (recusada), 2ª passa (aceita)
        bot, _ = montar_bot(["brasa", "abraco"], [True, False])
        bot._jogar_rodada("bra")

        self.assertEqual(len(bot.typer.enviadas), 2)
        self.assertNotEqual(bot.typer.enviadas[0], bot.typer.enviadas[1])
        self.assertEqual(bot.recusadas, 1)
        self.assertEqual(bot.aceitas, 1)

    def test_nao_repete_palavra_ja_usada_na_partida(self):
        bot, _ = montar_bot(["brasa", "abraco"], [False, False])
        bot._jogar_rodada("bra")
        primeira = bot.typer.enviadas[0]
        bot._marcar_turno(True)
        bot._jogar_rodada("bra")

        self.assertEqual(len(bot.typer.enviadas), 2)
        self.assertNotEqual(bot.typer.enviadas[1], primeira)

    def test_duas_recusas_aprendem_a_palavra(self):
        with tempfile.TemporaryDirectory() as tmp:
            import codigov4
            original = codigov4.REJEITADAS_FILE
            codigov4.REJEITADAS_FILE = os.path.join(tmp, "rej.txt")
            try:
                bot, _ = montar_bot(["brasa"], [True, True], max_tentativas_rodada=1)
                bot._jogar_rodada("bra")          # 1º strike
                bot._marcar_turno(True)
                bot.selector.nova_partida()       # libera a palavra de novo
                bot._jogar_rodada("bra")          # 2º strike -> aprende

                self.assertEqual(bot.strikes.get("brasa"), 2)
                self.assertIn("brasa", bot.dict.rejeitadas)
                with open(codigov4.REJEITADAS_FILE, encoding="utf-8") as f:
                    self.assertIn("brasa", f.read())
                # e a partir daí ela some das candidatas
                self.assertEqual(bot.dict.filtrar("bra"), [])
            finally:
                codigov4.REJEITADAS_FILE = original

    def test_verificacao_desligada_aceita_tudo(self):
        bot, _ = montar_bot(["brasa"], [True], verificar_envio=False)
        bot._jogar_rodada("bra")
        self.assertEqual(bot.aceitas, 1)
        self.assertEqual(bot.capt.consultas, 0)  # nem chegou a perguntar

    def test_para_quando_acabam_as_tentativas(self):
        bot, logs = montar_bot(["brasa", "abraco"], [True, True, True], max_tentativas_rodada=2)
        bot._jogar_rodada("bra")
        self.assertEqual(len(bot.typer.enviadas), 2)
        self.assertEqual(bot.recusadas, 2)
        self.assertTrue(any("tentativas sem sucesso" in m for m in logs))

    def test_sem_candidatos_manda_frase_padrao(self):
        from codigov4 import FRASE_QUANDO_NAO_TEM
        bot, _ = montar_bot(["casa"], [False])
        bot._jogar_rodada("xyz")
        self.assertEqual(bot.typer.enviadas, [FRASE_QUANDO_NAO_TEM])
        self.assertEqual(bot.aceitas, 0)  # frase de desistência não conta como acerto


class TestOrcamentoDeTempo(unittest.TestCase):
    def test_folga_cai_conforme_o_turno_passa(self):
        bot, _ = montar_bot(["casa"], [False], limite_tempo_round_s=4.0)
        self.assertGreater(bot._folga(), 0.95)          # turno recém-começado

        bot._turno_inicio -= 2.0                        # 2s se passaram
        self.assertAlmostEqual(bot._folga(), 0.5, delta=0.05)
        self.assertAlmostEqual(bot._orcamento_restante(), 2.0, delta=0.05)

        bot._turno_inicio -= 5.0                        # estourou o orçamento
        self.assertEqual(bot._folga(), 0.0)
        self.assertEqual(bot._orcamento_restante(), 0.0)

    def test_turno_so_reinicia_o_cronometro_na_virada(self):
        bot, _ = montar_bot(["casa"], [False])
        inicio = bot._turno_inicio
        bot._marcar_turno(True)                         # continua sendo minha vez
        self.assertEqual(bot._turno_inicio, inicio)

        bot._marcar_turno(False)
        bot._marcar_turno(True)                         # nova virada
        self.assertGreater(bot._turno_inicio, inicio)

    def test_nova_partida_zera_estado(self):
        bot, _ = montar_bot(["brasa"], [False])
        bot._jogar_rodada("bra")
        bot.strikes["x"] = 1
        bot.nova_partida("teste")
        self.assertEqual(bot.selector.usadas_partida, set())
        self.assertEqual(bot.strikes, {})
        self.assertEqual(bot.partidas, 1)


class TestCapturaDaSilaba(unittest.TestCase):
    """Falha do duplo-clique: tem que ser detectada e repetida, nunca ler lixo antigo."""

    def _capturador(self, **cfg_kwargs):
        from codigov4 import Capturador, PosicoesManager
        cfg = AppConfig()
        cfg.delay_pos_copiar_ms = 30
        for k, v in cfg_kwargs.items():
            setattr(cfg, k, v)
        self.logs = []
        return Capturador(PosicoesManager(), cfg, self.logs.append)

    def test_sequencia_auto_alterna_duplo_e_triplo(self):
        c = self._capturador(clique_captura="auto", tentativas_captura=3)
        self.assertEqual(c._sequencia_de_cliques(), [2, 3, 2])

    def test_sequencia_fixa_repete_o_mesmo_clique(self):
        self.assertEqual(self._capturador(clique_captura="triplo",
                                          tentativas_captura=2)._sequencia_de_cliques(), [3, 3])
        self.assertEqual(self._capturador(clique_captura="duplo",
                                          tentativas_captura=1)._sequencia_de_cliques(), [2])

    def test_espera_devolve_assim_que_o_clipboard_muda(self):
        import codigov4
        c = self._capturador()
        chamadas = {"n": 0}

        class ClipFalso:
            @staticmethod
            def paste():
                chamadas["n"] += 1
                # só na 3ª leitura o Ctrl+C "chega"
                return "bra" if chamadas["n"] >= 3 else codigov4.SENTINELA_CLIPBOARD

        original = codigov4.pyperclip
        codigov4.pyperclip = ClipFalso
        try:
            self.assertEqual(c._esperar_clipboard(codigov4.SENTINELA_CLIPBOARD, 1.0), "bra")
        finally:
            codigov4.pyperclip = original

    def test_espera_desiste_no_timeout_quando_nada_e_copiado(self):
        import codigov4
        c = self._capturador()

        class ClipTravado:
            @staticmethod
            def paste():
                return codigov4.SENTINELA_CLIPBOARD

        original = codigov4.pyperclip
        codigov4.pyperclip = ClipTravado
        try:
            # sentinela intacta = Ctrl+C não copiou nada = None (e não texto velho)
            self.assertIsNone(c._esperar_clipboard(codigov4.SENTINELA_CLIPBOARD, 0.08))
        finally:
            codigov4.pyperclip = original

    def test_captura_repete_ate_dar_certo_e_restaura_o_clipboard(self):
        import codigov4
        c = self._capturador(clique_captura="auto", tentativas_captura=3,
                             preservar_clipboard=True)

        estado = {"conteudo": "TEXTO DO USUARIO", "cliques": []}

        class ClipFalso:
            @staticmethod
            def paste():
                return estado["conteudo"]

            @staticmethod
            def copy(v):
                estado["conteudo"] = v

        class AutoGuiFalso:
            @staticmethod
            def moveTo(*a, **k):
                pass

            @staticmethod
            def click(x=None, y=None, clicks=1, interval=0):
                estado["cliques"].append(clicks)

            @staticmethod
            def hotkey(*teclas):
                # o duplo-clique falha; o triplo seleciona e copia
                if estado["cliques"][-1] == 3:
                    estado["conteudo"] = "  VEN  "

        orig_clip, orig_gui = codigov4.pyperclip, codigov4.pyautogui
        codigov4.pyperclip, codigov4.pyautogui = ClipFalso, AutoGuiFalso
        try:
            bruto = c._letras_por_clipboard()
        finally:
            codigov4.pyperclip, codigov4.pyautogui = orig_clip, orig_gui

        self.assertEqual(bruto.strip(), "VEN")
        self.assertEqual(estado["cliques"], [2, 3])           # tentou duplo, recuperou no triplo
        self.assertEqual(estado["conteudo"], "TEXTO DO USUARIO")  # clipboard devolvido
        self.assertTrue(any("Nada selecionado" in m for m in self.logs))

    def test_captura_falhando_sempre_devolve_vazio(self):
        import codigov4
        c = self._capturador(tentativas_captura=2)
        estado = {"conteudo": "SILABA ANTIGA"}

        class ClipFalso:
            @staticmethod
            def paste():
                return estado["conteudo"]

            @staticmethod
            def copy(v):
                estado["conteudo"] = v

        class AutoGuiFalso:
            moveTo = staticmethod(lambda *a, **k: None)
            click = staticmethod(lambda **k: None)
            hotkey = staticmethod(lambda *a: None)   # Ctrl+C nunca funciona

        orig_clip, orig_gui = codigov4.pyperclip, codigov4.pyautogui
        codigov4.pyperclip, codigov4.pyautogui = ClipFalso, AutoGuiFalso
        try:
            bruto = c._letras_por_clipboard()
        finally:
            codigov4.pyperclip, codigov4.pyautogui = orig_clip, orig_gui

        # o essencial: NÃO devolve a sílaba velha, que faria o bot digitar a palavra errada
        self.assertEqual(bruto, "")
        self.assertEqual(estado["conteudo"], "SILABA ANTIGA")


class TestUtilidades(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual(clamp(5, 0, 3), 3)
        self.assertEqual(clamp(-1, 0, 3), 0)
        self.assertEqual(clamp(2, 0, 3), 2)

    def test_alfabeto_tem_23_letras(self):
        self.assertEqual(len(LETRAS_ALFABETO), 23)


if __name__ == "__main__":
    unittest.main(verbosity=2)
