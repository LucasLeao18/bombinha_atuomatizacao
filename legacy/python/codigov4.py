import os
import re
import cv2
import json
import time
import random
import string
import datetime
import threading
import numpy as np
import pyperclip
import pyautogui
import keyboard

from PIL import ImageGrab
from enum import Enum
from dataclasses import dataclass, asdict, field, fields
from collections import deque

# UI
import tkinter as tk
from tkinter import ttk, Toplevel, filedialog, messagebox
from pynput import mouse


# ==============================
# Constantes / Enums / Util
# ==============================

APP_NAME = "JKLM.fun – Automação PT-BR"
CONFIG_FILE = "config.json"
POSICOES_FILE = "posicoes.json"
BLACKLIST_FILE = "blacklist.txt"
REJEITADAS_FILE = "rejeitadas.txt"
LOG_FILE = "log.txt"

# Valor gravado no clipboard antes do Ctrl+C: se continuar lá, a cópia falhou
SENTINELA_CLIPBOARD = "\x00__jklm_captura__\x00"

IGNORADAS_ALFABETO = set("ykw")  # Ignorar Y,K,W para completar 23 letras
LETRAS_ALFABETO = [c for c in string.ascii_lowercase if c not in IGNORADAS_ALFABETO]
APENAS_LETRAS_RE = re.compile(r'[^A-Za-zÀ-ÖØ-öø-ÿ]')  # mantém acentos PT-BR

FRASES_ENGRACADAS_DEFAULT = [
    "pera ai 🤔",
    "hmmm acho que é isso...",
    "calma, quase lá",
    "deixa eu pensar rapidinho",
    "ops, escrevi errado",
    "é isso? acho que sim",
]

FRASE_QUANDO_NAO_TEM = "fudeu mlk sei nao mamei"  # pedido do usuário

class Modo(Enum):
    LONGA = 'longa'
    CURTA = 'curta'
    QUALQUER = 'qualquer'
    ALFABETO = 'alfabeto'


class MetodoCaptura(Enum):
    CLIPBOARD = 'clipboard'   # duplo-clique + Ctrl+C (padrão, sem dependências extras)
    OCR = 'ocr'               # leitura da imagem da sílaba (exige pytesseract + tesseract)


class MetodoTurno(Enum):
    PIXEL = 'pixel'           # diferença absoluta em tons de cinza (comportamento original)
    COR = 'cor'               # correlação de histograma HSV
    HIBRIDO = 'hibrido'       # média dos dois

class VelocidadePerfil(Enum):
    NENHUM = 'nenhum'
    RAPIDA = 'rapida'
    ALEATORIA = 'aleatoria'
    GRADUAL = 'gradual'


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def aplicar_dpi_awareness(ativar: bool):
    """Alinha as coordenadas do pyautogui com os pixels reais da tela.

    Precisa ser chamado antes de criar qualquer janela. Fica desligado por padrão
    porque muda o significado das coordenadas já calibradas.
    """
    if not ativar or os.name != "nt":
        return None
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
        return "Ciência de DPI ativada: recalibre as posições se elas foram salvas sem ela."
    except Exception as exc:
        return f"Não foi possível ativar a ciência de DPI: {exc}"


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ==============================
# Configuração persistente
# ==============================

@dataclass
class HumanizarConfig:
    # Probabilidade de cometer um erro e corrigir com backspace por caractere
    chance_erro: float = 0.06
    # Variação aleatória adicional por caractere (0..X s)
    variacao_delay: float = 0.010
    # Inserir números aleatórios (com contador de rodadas)
    inserir_numeros: bool = False
    numeros_rodadas: int = 0  # quantas rodadas ainda usar números
    # Hesitação antes de pressionar Enter (para parecer humano pensando)
    hesitacao_enter_min: float = 0.06
    hesitacao_enter_max: float = 0.18
    # Pequenas pausas a cada n caracteres (respiradas)
    pausa_cada: int = 4
    pausa_min: float = 0.015
    pausa_max: float = 0.06
    # Perfil de velocidade
    perfil: str = VelocidadePerfil.ALEATORIA.value
    # Base de delays (ms) convertidos para s pela UI
    delay_entre_letras_ms: int = 6

    # ======= Recursos de humanização =======
    # Chance (0..1) de enviar uma palavra totalmente errada (falha proposital)
    chance_falha_proposital: float = 0.0
    # Chance (0..1) de digitar UMA LETRA errada, dar ENTER (manda errado) e redigitar certo
    chance_erro_enter: float = 0.0
    # Chance de digitar uma frase engraçada e APAGAR antes da correta
    chance_frase_engracada: float = 0.20
    # Chance de "ensaio" da palavra (digitar algo e apagar) antes da final
    chance_ensaio_palavra: float = 0.25
    # Pensar após 3 primeiras letras (se palavra começar com as 3 do desafio)
    pensar_3letras: bool = True
    pensar_3letras_pausa_ms: int = 500
    # Frases personalizadas
    frases_customizadas: list = field(default_factory=list)

@dataclass
class AppConfig:
    # Delays gerais (ms)
    delay_ciclo_ms: int = 200
    delay_pos_copiar_ms: int = 300
    delay_antes_digitar_ms: int = 200

    # Dicionário
    caminho_dicionario: str = "acento.txt"

    # Chatbox (template para detecção opcional)
    template_chatbox: str = "chatbox.png"
    template_threshold: float = 0.80
    turn_bar_threshold: float = 0.85

    # Modo inicial
    modo: str = Modo.QUALQUER.value

    # ===== Captura da sílaba =====
    metodo_captura: str = MetodoCaptura.CLIPBOARD.value
    # Devolve à área de transferência o que o usuário tinha antes da captura
    preservar_clipboard: bool = True
    # 'duplo' (seleciona a palavra), 'triplo' (seleciona a linha inteira – mais
    # tolerante a errar o glifo) ou 'auto' (duplo e, se falhar, triplo)
    clique_captura: str = 'auto'
    # Quantas vezes repetir o clique+Ctrl+C antes de desistir do ciclo
    tentativas_captura: int = 3

    # ===== Detecção de turno =====
    turn_bar_metodo: str = MetodoTurno.PIXEL.value

    # ===== Verificação de envio / aprendizado =====
    # Confere se a palavra foi aceita: se continuar sendo a sua vez, foi recusada
    verificar_envio: bool = True
    delay_verificacao_ms: int = 350
    max_tentativas_rodada: int = 3
    # Grava em rejeitadas.txt palavras recusadas 2x (o jogo não as conhece)
    aprender_rejeitadas: bool = True

    # Anti-repetição e seleção
    penaliza_repetidas: bool = True
    penalizacao_repetida: float = 0.85     # fator multiplicativo para pontuação
    cooldown_repeticao: int = 5            # não repetir a mesma palavra nas últimas N
    # O JKLM recusa qualquer palavra repetida na mesma partida: exclusão dura
    bloquear_usadas_na_partida: bool = True
    # Preferência por palavras que COMEÇAM com a sílaba (independente da encenação)
    preferir_prefixo: bool = True
    peso_prefixo: float = 1.25
    # Mistura a caça ao alfabeto nos modos normais quando sobra tempo
    alfabeto_hibrido: bool = True
    peso_letras_novas: float = 0.6

    # ===== Partida =====
    # Zera o estado por partida após um período sem turnos
    auto_nova_partida: bool = True
    inatividade_nova_partida_s: float = 60.0

    # ===== Sistema =====
    # Só ative se as coordenadas foram calibradas com o app ciente de DPI
    dpi_aware: bool = False

    # Exibir top opções no terminal
    mostrar_top_n: int = 5

    # Modo teste / debug
    modo_teste: bool = False
    salvar_log: bool = False

    # Limite máximo de tempo estimado por rodada (segundos) para não perder vida
    limite_tempo_round_s: float = 4.5

    # Humanização
    humanizar: HumanizarConfig = field(default_factory=HumanizarConfig)


# ==============================
# Persistência de Config e Posições
# ==============================

class ConfigManager:
    def __init__(self, path=CONFIG_FILE):
        self.path = path
        self.config = AppConfig()

    def load(self):
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Reconstrução segura: ignora chaves desconhecidas (config de outra versão)
        campos_app = {f.name for f in fields(AppConfig)}
        campos_hum = {f.name for f in fields(HumanizarConfig)}

        base = asdict(self.config)
        base.update({k: v for k, v in data.items() if k != "humanizar" and k in campos_app})
        human_data = {k: v for k, v in (data.get("humanizar") or {}).items() if k in campos_hum}
        base["humanizar"] = HumanizarConfig(**human_data)
        self.config = AppConfig(**base)

    def save(self):
        data = asdict(self.config)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


class PosicoesManager:
    def __init__(self, path=POSICOES_FILE):
        self.path = path
        self.pos_letras = (692, 594)
        self.pos_chatbox = (838, 953)
        self.turn_bar_rect = (600, 1010, 240, 32)  # x, y, width, height
        self.letras_rect = None      # x, y, w, h – região da sílaba (modo OCR)
        self.resolucao = None        # resolução em que as posições foram calibradas

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.pos_letras = tuple(data.get("letras", self.pos_letras))
            self.pos_chatbox = tuple(data.get("chatbox", self.pos_chatbox))
            self.turn_bar_rect = tuple(data.get("turn_bar", self.turn_bar_rect))
            lr = data.get("letras_rect")
            self.letras_rect = tuple(lr) if lr else None
            res = data.get("resolucao")
            self.resolucao = tuple(res) if res else None

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({
                "letras": self.pos_letras,
                "chatbox": self.pos_chatbox,
                "turn_bar": self.turn_bar_rect,
                "letras_rect": self.letras_rect,
                "resolucao": self.resolucao,
            }, f, ensure_ascii=False, indent=2)


# ==============================
# Núcleo: Dicionário / Seleção
# ==============================

class Dicionario:
    def __init__(self):
        self.palavras = []
        self.blacklist = set()      # blacklist manual do usuário
        self.rejeitadas = set()     # aprendidas: o JKLM não aceitou

    def carregar(self, caminho):
        self.palavras = []
        if not os.path.exists(caminho):
            return False
        with open(caminho, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip().lower()
                if w:
                    self.palavras.append(w)
        return True

    def carregar_blacklist(self, path=BLACKLIST_FILE):
        self.blacklist = self._ler_lista(path)

    def carregar_rejeitadas(self, path=REJEITADAS_FILE):
        self.rejeitadas = self._ler_lista(path)

    @staticmethod
    def _ler_lista(path):
        itens = set()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    w = line.strip().lower()
                    if w and not w.startswith("#"):
                        itens.add(w)
        return itens

    def registrar_rejeitada(self, palavra, path=REJEITADAS_FILE):
        """Marca uma palavra como desconhecida pelo jogo e persiste em disco."""
        palavra = palavra.lower().strip()
        if not palavra or palavra in self.rejeitadas:
            return False
        self.rejeitadas.add(palavra)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(palavra + "\n")
        except Exception:
            return False
        return True

    def filtrar(self, frag, excluir=None):
        """Palavras que contêm a sílaba, sem blacklist/rejeitadas/já usadas."""
        frag = frag.lower()
        excluir = excluir or frozenset()
        return [w for w in self.palavras
                if frag in w
                and w not in self.blacklist
                and w not in self.rejeitadas
                and w not in excluir]


class Selecionador:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.recentes = deque(maxlen=max(1, cfg.cooldown_repeticao))
        self.frequencia = {}        # contagem de uso por palavra (sessão)
        self.letras_usadas = set()  # progresso rumo à vida extra
        self.alfabeto_completado = 0
        self.usadas_partida = set() # o JKLM recusa repetição na mesma partida

    # ---------- Pontuação ----------
    def _letras_novas(self, palavra):
        letras = set(c for c in palavra if c.isalpha()) - IGNORADAS_ALFABETO
        return len(letras - self.letras_usadas)

    def _score_base(self, palavra, criterio, frag, folga=1.0):
        if criterio == Modo.CURTA.value:
            base = 1.0 / (len(palavra) + 1e-3)
        elif criterio == Modo.LONGA.value:
            base = float(len(palavra))
        else:
            base = 1.0

        if self.cfg.preferir_prefixo and palavra.startswith(frag):
            base *= max(1.0, self.cfg.peso_prefixo)

        # Caça ao alfabeto embutida nos modos normais: só quando sobra tempo.
        # 'folga' vai de 0 (bomba estourando) a 1 (turno acabou de começar).
        if self.cfg.alfabeto_hibrido and folga > 0:
            novas = self._letras_novas(palavra)
            if novas:
                base *= 1.0 + (self.cfg.peso_letras_novas * folga * novas / 5.0)

        if self.cfg.penaliza_repetidas:
            freq = self.frequencia.get(palavra, 0)
            if freq > 0:
                base *= (self.cfg.penalizacao_repetida ** freq)
            if palavra in self.recentes:
                base *= 0.5

        return base

    def _score_alfabeto(self, palavra):
        return self._letras_novas(palavra) + (len(palavra) * 0.05)

    def escolher(self, candidatos, modo: str, frag: str, folga: float = 1.0):
        """Escolhe uma palavra entre as candidatas.

        folga: 1.0 = turno recém-começado, 0.0 = sem tempo (prioriza velocidade).
        """
        if not candidatos:
            return None
        frag = frag.lower()
        folga = clamp(folga, 0.0, 1.0)

        if modo == Modo.ALFABETO.value:
            scored = [(w, self._score_alfabeto(w)) for w in candidatos]
        else:
            scored = [(w, self._score_base(w, modo, frag, folga)) for w in candidatos]

        scored.sort(key=lambda x: x[1], reverse=True)
        top_n = max(1, min(self.cfg.mostrar_top_n if self.cfg.mostrar_top_n > 0 else 1, len(scored)))
        top = scored[:top_n]
        pesos = np.array([max(1e-3, s) for _, s in top], dtype=float)
        pesos = pesos / pesos.sum()
        return random.choices([w for w, _ in top], weights=pesos, k=1)[0]

    # ---------- Estado ----------
    def registrar_uso(self, palavra, modo: str):
        self.frequencia[palavra] = self.frequencia.get(palavra, 0) + 1
        self.recentes.append(palavra)
        self.usadas_partida.add(palavra)

        letras = set(c for c in palavra if c.isalpha()) - IGNORADAS_ALFABETO
        self.letras_usadas.update(letras)
        if len(self.letras_usadas) >= len(LETRAS_ALFABETO):
            self.alfabeto_completado += 1
            self.letras_usadas.clear()

    def bloqueadas(self):
        """Palavras que o jogo recusaria agora por já terem sido usadas."""
        return self.usadas_partida if self.cfg.bloquear_usadas_na_partida else frozenset()

    def nova_partida(self):
        """Zera o que vale por partida (mantém estatísticas da sessão)."""
        self.usadas_partida.clear()
        self.letras_usadas.clear()
        self.recentes.clear()


# ==============================
# Detecção / Captura
# ==============================

class Capturador:
    def __init__(self, posicoes: PosicoesManager, cfg: AppConfig, log_fn):
        self.pos = posicoes
        self.cfg = cfg
        self.contador_falhas = 0
        self.limite_falhas = 5
        self.log = log_fn
        self.turn_bar_reference = None
        self._last_turn_capture = 0.0
        self._warned_turn_rect = False
        self._ocr = None            # None = ainda não testado; False = indisponível
        self._warned_ocr = False

    # ---------- Diagnóstico de tela ----------
    @staticmethod
    def diagnostico_escala():
        """Compara a resolução lógica (pyautogui) com a física (ImageGrab).

        Divergência indica escala do Windows != 100% sem DPI awareness, que é a
        causa mais comum de cliques e capturas caírem no lugar errado.
        """
        try:
            logica = tuple(pyautogui.size())
            fisica = ImageGrab.grab().size
        except Exception:
            return None
        fator = (fisica[0] / logica[0]) if logica[0] else 1.0
        return {"logica": logica, "fisica": fisica, "fator": fator, "ok": abs(fator - 1.0) < 0.01}

    def detectar_chatbox(self, refresh_reference=False):
        # Se não existir template, assume turno
        if not os.path.exists(self.cfg.template_chatbox):
            if refresh_reference:
                self._update_turn_reference()
            return True
        screen = np.array(ImageGrab.grab())
        gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        template = cv2.imread(self.cfg.template_chatbox, 0)
        if template is None:
            if refresh_reference:
                self._update_turn_reference()
            return True
        res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        loc = np.where(res >= float(self.cfg.template_threshold))
        ativa = len(loc[0]) > 0
        if ativa:
            if refresh_reference:
                self._update_turn_reference()
        else:
            self.turn_bar_reference = None
            self._warned_turn_rect = False
        return ativa

    def capturar_barra_turno(self):
        if not self.pos.turn_bar_rect or len(self.pos.turn_bar_rect) != 4:
            return None
        x, y, w, h = self.pos.turn_bar_rect
        if w <= 0 or h <= 0:
            return None
        try:
            shot = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        except Exception as exc:
            self.log(f"Falha ao capturar barra de turno: {exc}")
            return None
        # Mantido em cores: o método 'pixel' converte para cinza na comparação
        # (mesma conta de antes) e o método 'cor' usa os canais.
        return np.array(shot.convert("RGB"))

    def _update_turn_reference(self):
        img = self.capturar_barra_turno()
        if img is not None:
            self.turn_bar_reference = img
            self._last_turn_capture = time.time()
            self._warned_turn_rect = False

    def _similaridade_turno(self, atual):
        if self.turn_bar_reference is None:
            return 1.0
        ref = self.turn_bar_reference
        if atual.shape[:2] != ref.shape[:2]:
            atual = cv2.resize(atual, (ref.shape[1], ref.shape[0]))

        metodo = self.cfg.turn_bar_metodo
        if metodo == MetodoTurno.PIXEL.value:
            return self._score_pixel(ref, atual)
        if metodo == MetodoTurno.COR.value:
            return self._score_cor(ref, atual)
        return (self._score_pixel(ref, atual) + self._score_cor(ref, atual)) / 2.0

    @staticmethod
    def _score_pixel(ref, atual):
        """Diferença média de pixels (sensível a qualquer mudança, inclusive a barra andando)."""
        a = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY) if ref.ndim == 3 else ref
        b = cv2.cvtColor(atual, cv2.COLOR_BGR2GRAY) if atual.ndim == 3 else atual
        return clamp(1.0 - (cv2.absdiff(a, b).mean() / 255.0), 0.0, 1.0)

    @staticmethod
    def _score_cor(ref, atual):
        """Correlação de histograma HSV: tolera a barra encolher, acusa troca de cor/jogador."""
        if ref.ndim != 3 or atual.ndim != 3:
            return Capturador._score_pixel(ref, atual)
        hists = []
        for img in (ref, atual):
            hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
            h = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
            hists.append(cv2.normalize(h, h).flatten())
        return clamp(float(cv2.compareHist(hists[0], hists[1], cv2.HISTCMP_CORREL)), 0.0, 1.0)

    def turno_ativo(self):
        """Checagem leve de 'ainda é a minha vez' (sem mexer o mouse nem a referência).

        Usada para descobrir se a palavra enviada foi aceita: se o turno continua
        sendo seu alguns instantes após o ENTER, o jogo recusou a palavra.
        """
        if not self.detectar_chatbox():
            return False
        atual = self.capturar_barra_turno()
        if atual is None or self.turn_bar_reference is None:
            return False
        return self._similaridade_turno(atual) >= self.cfg.turn_bar_threshold

    def confirmar_turno_para_envio(self):
        original_pos = None
        moved_mouse = False
        safe_target = getattr(self.pos, "pos_letras", None)
        if safe_target and len(safe_target) == 2:
            try:
                original_pos = pyautogui.position()
                pyautogui.moveTo(safe_target[0], safe_target[1], duration=0)
                moved_mouse = True
                time.sleep(0.04)
            except Exception:
                moved_mouse = False

        try:
            if not self.detectar_chatbox():
                self.log("Recheque falhou: barra de turno não ativa.")
                return False
            atual = self.capturar_barra_turno()
            if atual is None:
                if not self._warned_turn_rect:
                    self.log("Retângulo da barra de turno não configurado; envio cancelado.")
                    self._warned_turn_rect = True
                return False
            if self.turn_bar_reference is None:
                self.turn_bar_reference = atual
                self._warned_turn_rect = False
                return True
            score = self._similaridade_turno(atual)
            if score >= self.cfg.turn_bar_threshold:
                self.turn_bar_reference = atual
                self._warned_turn_rect = False
                return True
            self.log(f"Envio cancelado: similaridade da barra {score:.3f} abaixo do threshold {self.cfg.turn_bar_threshold:.3f}.")
            return False
        finally:
            if moved_mouse and original_pos is not None:
                try:
                    pyautogui.moveTo(original_pos[0], original_pos[1], duration=0)
                except Exception:
                    pass

    # ---------- Captura da sílaba ----------
    def capturar_letras(self):
        bruto = None
        if self.cfg.metodo_captura == MetodoCaptura.OCR.value:
            bruto = self._letras_por_ocr()
            if bruto is None:  # OCR indisponível/sem região: cai no método antigo
                bruto = self._letras_por_clipboard()
        else:
            bruto = self._letras_por_clipboard()

        if not bruto:
            self.contador_falhas += 1
            if self.contador_falhas > self.limite_falhas:
                self.log("Falhas repetidas ao capturar. Verifique posições/janela/jogo.")
            return ""

        limpo = APENAS_LETRAS_RE.sub('', bruto).lower().strip()
        if not limpo:
            self.contador_falhas += 1
        else:
            self.contador_falhas = 0
        return limpo

    def _sequencia_de_cliques(self):
        """Quantos cliques dar em cada tentativa da captura.

        O clique duplo seleciona a palavra sob o cursor; se ele errar o glifo por
        alguns pixels (a bomba treme e se move), nada é selecionado e o Ctrl+C não
        copia nada. O clique triplo seleciona a linha inteira e perdoa esse erro.
        """
        modo = self.cfg.clique_captura
        base = {"duplo": [2], "triplo": [3]}.get(modo, [2, 3])
        tentativas = max(1, self.cfg.tentativas_captura)
        seq = []
        while len(seq) < tentativas:
            seq.extend(base)
        return seq[:tentativas]

    def _esperar_clipboard(self, sentinela, timeout_s):
        """Espera o Ctrl+C chegar, em vez de dormir um tempo fixo torcendo para dar certo."""
        fim = time.time() + timeout_s
        while time.time() < fim:
            try:
                atual = pyperclip.paste()
            except Exception:
                atual = sentinela
            if atual and atual != sentinela:
                return atual
            time.sleep(0.015)
        return None

    def _letras_por_clipboard(self):
        """Seleciona a sílaba e copia, com verificação real de sucesso e novas tentativas."""
        anterior = None
        if self.cfg.preservar_clipboard:
            try:
                anterior = pyperclip.paste()
            except Exception:
                anterior = None

        x, y = self.pos.pos_letras
        settle = max(0.03, self.cfg.delay_pos_copiar_ms / 1000.0)
        bruto = None

        try:
            for i, cliques in enumerate(self._sequencia_de_cliques(), start=1):
                # Marca o clipboard: se ele continuar com a sentinela, o Ctrl+C não
                # copiou nada — sem essa marca era impossível distinguir "falhou" de
                # "a sílaba repetiu", e o bot acabava digitando a palavra do turno anterior.
                try:
                    pyperclip.copy(SENTINELA_CLIPBOARD)
                except Exception:
                    pass

                pyautogui.moveTo(x, y, duration=0)
                time.sleep(0.02)  # deixa o navegador registrar a posição antes do clique
                pyautogui.click(x=x, y=y, clicks=cliques, interval=0.03)
                time.sleep(settle)
                pyautogui.hotkey('ctrl', 'c')

                bruto = self._esperar_clipboard(SENTINELA_CLIPBOARD, settle)
                if bruto:
                    if i > 1:
                        self.log(f"Captura recuperada na tentativa {i} ({cliques} cliques).")
                    break
                self.log(f"Nada selecionado com {cliques} cliques (tentativa {i}).")
        finally:
            if anterior is not None:
                try:
                    pyperclip.copy(anterior)
                except Exception:
                    pass

        return bruto or ""

    def _letras_por_ocr(self):
        """Lê a sílaba direto da imagem: sem mouse, sem foco, sem clipboard."""
        if self._ocr is False:
            return None
        if self._ocr is None:
            try:
                import pytesseract  # noqa: F401
                pytesseract.get_tesseract_version()
                self._ocr = pytesseract
            except Exception as exc:
                self._ocr = False
                if not self._warned_ocr:
                    self._warned_ocr = True
                    self.log(f"OCR indisponível ({exc.__class__.__name__}); usando duplo-clique + Ctrl+C. "
                             f"Instale 'pytesseract' e o Tesseract para ativar.")
                return None

        rect = self.pos.letras_rect
        if not rect or len(rect) != 4 or rect[2] <= 0 or rect[3] <= 0:
            if not self._warned_ocr:
                self._warned_ocr = True
                self.log("Região das letras não capturada (Setup > Região da sílaba); usando clipboard.")
            return None

        x, y, w, h = rect
        try:
            img = np.array(ImageGrab.grab(bbox=(x, y, x + w, y + h)).convert("RGB"))
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            # A sílaba costuma ser clara sobre fundo escuro; o Tesseract espera o contrário
            if bw.mean() < 127:
                bw = cv2.bitwise_not(bw)
            texto = self._ocr.image_to_string(
                bw, config="--psm 7 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
            return texto.strip()
        except Exception as exc:
            self.log(f"Falha no OCR: {exc}. Voltando para o clipboard.")
            self._ocr = False
            return None


# ==============================
# Digitação Humanizada + Estimador
# ==============================

class HumanTyper:
    def __init__(self, cfg: AppConfig, log_fn, is_my_turn_fn):
        self.cfg = cfg
        self.log = log_fn
        self.is_my_turn = is_my_turn_fn  # mesma função usada para iniciar a jogada
        self._random = random.Random()
        self.FAST_ERASE_TIME = 0.08     # ~80ms para Ctrl+A + Backspace
        self.KEYPRESS_TIME = 0.0015     # ~1.5ms por tecla
        self.BACKSPACE_KEY_TIME = 0.02  # ~20ms para backspace

    # Sem jitter: clique direto
    def _focus_chat(self, pos):
        pyautogui.click(x=pos[0], y=pos[1])

    def _delay_letra(self, idx, total):
        h = self.cfg.humanizar
        base = clamp(h.delay_entre_letras_ms / 1000.0, 0.0005, 0.2)

        if h.perfil == VelocidadePerfil.GRADUAL.value:
            fator = 0.6 + 0.4 * (idx / max(1, total - 1))
            d = base * fator
        elif h.perfil == VelocidadePerfil.RAPIDA.value:
            d = base * 0.6
        elif h.perfil == VelocidadePerfil.ALEATORIA.value:
            d = base * self._random.uniform(0.65, 1.35)
        else:
            d = base

        d += self._random.uniform(0.0, self.cfg.humanizar.variacao_delay)
        time.sleep(d)

        if (idx + 1) % max(1, self.cfg.humanizar.pausa_cada) == 0 and idx + 1 < total:
            time.sleep(self._random.uniform(self.cfg.humanizar.pausa_min, self.cfg.humanizar.pausa_max))

    # ---------- Modelo de tempo (esperado) ----------
    def _avg_letter_delay_base(self):
        h = self.cfg.humanizar
        base = clamp(h.delay_entre_letras_ms / 1000.0, 0.0005, 0.2)
        if h.perfil == VelocidadePerfil.GRADUAL.value:
            base *= 0.8    # média do fator 0.6..1.0
        elif h.perfil == VelocidadePerfil.RAPIDA.value:
            base *= 0.6
        elif h.perfil == VelocidadePerfil.ALEATORIA.value:
            base *= 1.0    # expectativa de U(0.65,1.35)
        base += self.cfg.humanizar.variacao_delay * 0.5
        return base

    def _pausas_periodicas_time(self, n_chars):
        h = self.cfg.humanizar
        if h.pausa_cada <= 0 or n_chars <= 1:
            return 0.0
        pausas = (n_chars - 1) // h.pausa_cada
        return pausas * ((h.pausa_min + h.pausa_max) / 2.0)

    def _expected_numbers_extra(self, n_chars, include_nums):
        if not include_nums:
            return 0.0
        return 0.12 * n_chars * self.KEYPRESS_TIME

    def _expected_micro_error_extra(self, n_chars, base_letter_delay):
        p = self.cfg.humanizar.chance_erro
        return n_chars * p * (self.KEYPRESS_TIME + base_letter_delay + self.BACKSPACE_KEY_TIME)

    def _enter_hesitation_avg(self):
        h = self.cfg.humanizar
        return (h.hesitacao_enter_min + h.hesitacao_enter_max) / 2.0

    def _typing_block_expected(self, n_chars, envia, include_pensar3=False, think_ms=None, include_nums=False):
        t = 0.0
        # pré-delay por bloco
        t += self.cfg.delay_antes_digitar_ms / 1000.0

        base_d = self._avg_letter_delay_base()

        # digitação base + keypress
        t += n_chars * (base_d + self.KEYPRESS_TIME)

        # pausas periódicas
        t += self._pausas_periodicas_time(n_chars)

        # micro-erro esperado
        t += self._expected_micro_error_extra(n_chars, base_d)

        # números extra
        t += self._expected_numbers_extra(n_chars, include_nums)

        # pensar após 3 letras
        if include_pensar3 and n_chars >= 3:
            val_ms = think_ms if think_ms is not None else self.cfg.humanizar.pensar_3letras_pausa_ms
            t += max(0.0, val_ms / 1000.0)

        # hesitação enter
        if envia:
            t += self._enter_hesitation_avg()

        return t

    # ---------- Execução real
    # Agora: verifica UMA VEZ se ainda é a vez antes de apertar Enter. Se não for, cancela.
    def _try_send_enter_only_if_turn(self) -> bool:
        if not self.is_my_turn():
            self.log("Envio cancelado: não é mais a sua vez no momento do ENTER.")
            return False
        pyautogui.press('enter')
        return True

    def _digitar_texto(self, texto: str, pos_chatbox, enviar=False, override_nums=False):
        if self.cfg.modo_teste:
            self.log(f"[TESTE] {'enviaria' if enviar else 'digitaria'} -> {texto}")
            return True
        self._focus_chat(pos_chatbox)
        time.sleep(self.cfg.delay_antes_digitar_ms / 1000.0)

        h = self.cfg.humanizar
        letras_erradas_pool = string.ascii_lowercase

        for i, ch in enumerate(texto):
            if self._random.random() < h.chance_erro and ch.isalpha():
                errado = self._random.choice(letras_erradas_pool)
                pyautogui.typewrite(errado)
                self._delay_letra(i, len(texto))
                pyautogui.press('backspace')

            pyautogui.typewrite(ch)

            use_nums = (h.inserir_numeros or override_nums)
            if use_nums and self._random.random() < 0.12:
                pyautogui.typewrite(str(self._random.randint(0, 9)))

            self._delay_letra(i, len(texto))

        if enviar:
            time.sleep(self._random.uniform(h.hesitacao_enter_min, h.hesitacao_enter_max))
            return self._try_send_enter_only_if_turn()
        return True

    def _erase_all(self, pos_chatbox):
        if self.cfg.modo_teste:
            self.log("[TESTE] apagaria o campo.")
            return True
        self._focus_chat(pos_chatbox)
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.03)
        pyautogui.press('backspace')
        time.sleep(0.02)
        return True

    def digitar_pensando_3(self, palavra: str, pos_chatbox, think_ms=500, override_nums=False):
        if self.cfg.modo_teste:
            self.log(f"[TESTE] enviaria (pensando 3) -> {palavra}")
            return True
        self._focus_chat(pos_chatbox)
        time.sleep(self.cfg.delay_antes_digitar_ms / 1000.0)

        h = self.cfg.humanizar
        letras_erradas_pool = string.ascii_lowercase
        n = len(palavra)
        pausa_idx = min(2, n - 1)  # após a 3ª letra (índice 2), se possível

        for i, ch in enumerate(palavra):
            if self._random.random() < h.chance_erro and ch.isalpha():
                errado = self._random.choice(letras_erradas_pool)
                pyautogui.typewrite(errado)
                self._delay_letra(i, n)
                pyautogui.press('backspace')

            pyautogui.typewrite(ch)

            use_nums = (h.inserir_numeros or override_nums)
            if use_nums and self._random.random() < 0.12:
                pyautogui.typewrite(str(self._random.randint(0, 9)))

            if i == pausa_idx:
                time.sleep(max(0.0, think_ms / 1000.0))

            self._delay_letra(i, n)

        time.sleep(self._random.uniform(h.hesitacao_enter_min, h.hesitacao_enter_max))
        return self._try_send_enter_only_if_turn()

    def digitar(self, palavra: str, pos_chatbox, override_nums=False):
        return self._digitar_texto(palavra, pos_chatbox, enviar=True, override_nums=override_nums)

    def digitar_quick(self, palavra: str, pos_chatbox):
        if self.cfg.modo_teste:
            self.log(f"[TESTE] enviaria (rápido) -> {palavra}")
            return True
        self._focus_chat(pos_chatbox)
        time.sleep(0.05)  # mínimo para focar
        for ch in palavra:
            pyautogui.typewrite(ch)
            time.sleep(0.001)
        return self._try_send_enter_only_if_turn()

    def frase_engracada_e_apaga(self, pos_chatbox):
        frases = (self.cfg.humanizar.frases_customizadas or []) + FRASES_ENGRACADAS_DEFAULT
        frase = self._random.choice(frases)
        ok = self._digitar_texto(frase, pos_chatbox, enviar=False)
        if not ok:
            return False
        return self._erase_all(pos_chatbox)

    def ensaiar_palavra_e_apagar(self, palavra, pos_chatbox):
        if len(palavra) <= 3:
            rabisco = palavra[:2] + "..."
        else:
            k = self._random.randint(2, min(len(palavra)-1, 5))
            rabisco = palavra[:k] + self._random.choice(["..", "...", "!"])
        ok = self._digitar_texto(rabisco, pos_chatbox, enviar=False)
        if not ok:
            return False
        return self._erase_all(pos_chatbox)

    def falha_proposital(self, palavra_correta, pos_chatbox):
        if len(palavra_correta) > 3:
            i = self._random.randint(0, len(palavra_correta)-1)
            errada = (palavra_correta[:i] +
                      self._random.choice(string.ascii_lowercase.replace(palavra_correta[i], '')) +
                      palavra_correta[i+1:])
        else:
            errada = palavra_correta + self._random.choice(string.ascii_lowercase)
        ok = self._digitar_texto(errada, pos_chatbox, enviar=True)
        return errada if ok else None

    def erro_enter_e_corrige(self, palavra_correta, pos_chatbox):
        # envia UMA errada + ENTER, depois a correta + ENTER
        if len(palavra_correta) > 1:
            i = self._random.randint(0, len(palavra_correta)-1)
            errada = (palavra_correta[:i] +
                      self._random.choice(string.ascii_lowercase.replace(palavra_correta[i], '')) +
                      palavra_correta[i+1:])
        else:
            errada = palavra_correta + self._random.choice(string.ascii_lowercase)

        ok1 = self._digitar_texto(errada, pos_chatbox, enviar=True)
        ok2 = self._digitar_texto(palavra_correta, pos_chatbox, enviar=True) if ok1 else False
        return bool(ok1 and ok2)

    # ---------- Estimativa de tempo ----------
    def estimate_round_time(self, palavra, use_frase, use_ensaio, use_falha, use_erro_enter, use_pensar3, include_nums):
        total = 0.0
        bd = {"frase": 0.0, "ensaio": 0.0, "falha": 0.0, "erro_enter": 0.0, "typing": 0.0}

        h = self.cfg.humanizar

        # frase engraçada
        if use_frase:
            frase = random.choice((h.frases_customizadas or []) + FRASES_ENGRACADAS_DEFAULT)
            part = self._typing_block_expected(len(frase), envia=False, include_pensar3=False, include_nums=False)
            part += self.FAST_ERASE_TIME
            total += part
            bd["frase"] = part

        # ensaio
        if use_ensaio:
            ens_len = 3 if len(palavra) <= 3 else min(5, max(2, len(palavra)//2))
            part = self._typing_block_expected(ens_len, envia=False, include_pensar3=False, include_nums=False)
            part += self.FAST_ERASE_TIME
            total += part
            bd["ensaio"] = part

        n = len(palavra)

        if use_falha:
            # envia uma palavra errada e encerra
            part = self._typing_block_expected(n, envia=True, include_pensar3=False, include_nums=include_nums)
            total += part
            bd["falha"] = part
            return total, bd

        if use_erro_enter:
            # envia errada + envia correta
            part1 = self._typing_block_expected(n, envia=True, include_pensar3=False, include_nums=include_nums)
            part2 = self._typing_block_expected(n, envia=True, include_pensar3=False, include_nums=include_nums)
            total += (part1 + part2)
            bd["erro_enter"] = part1 + part2
            return total, bd

        # caminho normal (pode incluir pensar 3 letras)
        part = self._typing_block_expected(n, envia=True, include_pensar3=use_pensar3, think_ms=h.pensar_3letras_pausa_ms, include_nums=include_nums)
        total += part
        bd["typing"] = part

        return total, bd


# ==============================
# Núcleo do Bot
# ==============================

class BotCore:
    def __init__(self, cfg: AppConfig, pos: PosicoesManager, ui_logger):
        self.cfg = cfg
        self.pos = pos
        self.ui_log = ui_logger

        self.dict = Dicionario()
        self.selector = Selecionador(cfg)
        self.capt = Capturador(pos, cfg, self._log)
        self.typer = HumanTyper(cfg, self._log, self.capt.confirmar_turno_para_envio)

        self.executando = False
        self.modo_atual = cfg.modo
        self.historico = []
        self.lock = threading.Lock()

        # estatísticas humanas
        self.acertos_consecutivos = 0
        self.erros_propositais = 0

        # contador de rodadas com números
        self.numeros_restantes = cfg.humanizar.numeros_rodadas

        # ===== Feedback de envio =====
        self.aceitas = 0
        self.recusadas = 0
        self.strikes = {}            # palavra -> nº de recusas (2 = vai para rejeitadas.txt)
        self.partidas = 0

        # ===== Controle de turno =====
        self._turno_ativo = False
        self._turno_inicio = 0.0
        self._ultimo_turno_em = time.time()

    # ---------- Tempo da rodada ----------
    def _tempo_no_turno(self):
        return (time.time() - self._turno_inicio) if self._turno_ativo else 0.0

    def _orcamento_restante(self):
        """Quanto ainda dá para gastar nesta rodada, descontando o tempo já perdido."""
        return max(0.0, self.cfg.limite_tempo_round_s - self._tempo_no_turno())

    def _folga(self):
        """0.0 = sem tempo, 1.0 = turno recém-começado (usada na escolha da palavra)."""
        limite = max(0.1, self.cfg.limite_tempo_round_s)
        return clamp(self._orcamento_restante() / limite, 0.0, 1.0)

    def _marcar_turno(self, ativo: bool):
        """Detecta a virada 'não é minha vez' -> 'é minha vez' para cronometrar."""
        if ativo and not self._turno_ativo:
            self._turno_inicio = time.time()
            self._ultimo_turno_em = time.time()
        self._turno_ativo = ativo

    # ---------- Partida ----------
    def nova_partida(self, motivo="manual"):
        self.selector.nova_partida()
        self.strikes.clear()
        self.partidas += 1
        self._log(f"Nova partida ({motivo}): palavras usadas e alfabeto zerados.")

    def _checar_inatividade(self):
        if not self.cfg.auto_nova_partida:
            return
        parado_ha = time.time() - self._ultimo_turno_em
        if parado_ha >= self.cfg.inatividade_nova_partida_s and self.selector.usadas_partida:
            self.nova_partida(f"{int(parado_ha)}s sem turnos")
            self._ultimo_turno_em = time.time()

    @property
    def taxa_aceitacao(self):
        total = self.aceitas + self.recusadas
        return (self.aceitas / total * 100.0) if total else 0.0

    def _log(self, msg: str):
        self.ui_log(msg)
        if self.cfg.salvar_log:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{now()} - {msg}\n")

    def carregar_dict_e_blacklist(self):
        ok = self.dict.carregar(self.cfg.caminho_dicionario)
        if not ok:
            self._log(f"Arquivo de dicionário não encontrado: {self.cfg.caminho_dicionario}")
            return False
        self.dict.carregar_blacklist(BLACKLIST_FILE)
        self.dict.carregar_rejeitadas(REJEITADAS_FILE)
        self._log(f"Dicionário carregado ({len(self.dict.palavras)} palavras). "
                  f"Blacklist: {len(self.dict.blacklist)} | Recusadas pelo jogo: {len(self.dict.rejeitadas)}")
        return True

    def set_modo(self, modo: str):
        self.modo_atual = modo
        self._log(f"Modo selecionado: {modo}")

    def iniciar(self):
        with self.lock:
            if self.executando:
                return
            self.executando = True
        threading.Thread(target=self._main_loop, daemon=True).start()

    def parar(self):
        with self.lock:
            self.executando = False

    def _select_triggers(self):
        h = self.cfg.humanizar
        # escolher somente UMA ação de envio errado: falha proposital OU erro_enter
        trigger_falha = random.random() < h.chance_falha_proposital
        trigger_erro_enter = (not trigger_falha) and (random.random() < h.chance_erro_enter)
        # pré-comportamentos podem coexistir
        trigger_frase = random.random() < h.chance_frase_engracada
        trigger_ensaio = random.random() < h.chance_ensaio_palavra
        return trigger_frase, trigger_ensaio, trigger_falha, trigger_erro_enter

    def _main_loop(self):
        self._log(f"Iniciando no modo: {self.modo_atual}")
        if not self.dict.palavras:
            if not self.carregar_dict_e_blacklist():
                self.parar()
                return

        while True:
            with self.lock:
                if not self.executando:
                    self._log("Processo parado.")
                    return

            meu_turno = self.capt.detectar_chatbox(refresh_reference=True)
            self._marcar_turno(meu_turno)

            if meu_turno:
                frag = self.capt.capturar_letras()
                if frag:
                    self._log(f"Letras detectadas: {frag}")
                    try:
                        self._jogar_rodada(frag)
                    except Exception as e:
                        self._log(f"Falha ao jogar a rodada: {e}")
                else:
                    self._log("Captura vazia; tentando novamente.")
            else:
                self._checar_inatividade()

            time.sleep(self.cfg.delay_ciclo_ms / 1000.0)

    # ---------- Rodada ----------
    def _jogar_rodada(self, frag):
        """Tenta palavras até uma ser aceita pelo jogo (ou acabarem as tentativas)."""
        excluidas = set()
        tentativas = max(1, self.cfg.max_tentativas_rodada)

        for tentativa in range(1, tentativas + 1):
            with self.lock:
                if not self.executando:
                    return

            candidatos = self.dict.filtrar(frag, excluir=set(self.selector.bloqueadas()) | excluidas)
            if not candidatos:
                if tentativa == 1:
                    # Regra: quando não achar no dicionário, fala a frase definida
                    self._log("Nenhuma palavra encontrada – enviando frase padrão.")
                    if not self.typer.digitar_quick(FRASE_QUANDO_NAO_TEM, self.pos.pos_chatbox):
                        self._log("Envio da frase padrão cancelado (não era mais a sua vez).")
                else:
                    self._log(f"Sem mais candidatos para '{frag}' nesta rodada.")
                return

            escolha = self.selector.escolher(candidatos, self.modo_atual, frag, folga=self._folga())
            if not escolha:
                return

            if self.cfg.mostrar_top_n > 0 and tentativa == 1:
                top_preview = ", ".join(candidatos[:min(self.cfg.mostrar_top_n, len(candidatos))])
                self._log(f"Top opções ({len(candidatos)} candidatas): {top_preview}")

            sufixo = f"  (tentativa {tentativa}/{tentativas})" if tentativa > 1 else ""
            self._log(f"Escolhida: {escolha}{sufixo}")

            resultado = self._enviar_palavra(escolha, frag, apressado=(tentativa > 1))

            if resultado == "aceita":
                return
            if resultado == "cancelado":
                return
            if resultado == "falha_proposital":
                continue  # erro de propósito: não conta como recusa da palavra
            # recusada
            excluidas.add(escolha)
            self._registrar_recusa(escolha)

        self._log(f"{tentativas} tentativas sem sucesso para '{frag}'.")

    def _enviar_palavra(self, escolha, frag, apressado=False):
        """Envia a palavra com (ou sem) encenação e confere se o jogo aceitou.

        Retorna: 'aceita' | 'recusada' | 'cancelado' | 'falha_proposital'.
        """
        h = self.cfg.humanizar

        if apressado:
            trig_frase = trig_ensaio = trig_falha = trig_erro_enter = False
        else:
            trig_frase, trig_ensaio, trig_falha, trig_erro_enter = self._select_triggers()

        use_nums = h.inserir_numeros and (self.numeros_restantes > 0) and not apressado
        # "Pensar após 3 letras" agora só reage à palavra escolhida – não filtra mais
        # o conjunto de candidatas (isso empobrecia demais a seleção).
        use_pensar3 = (not apressado and h.pensar_3letras
                       and len(frag) >= 3 and escolha.startswith(frag[:3]))

        est, breakdown = self.typer.estimate_round_time(
            escolha,
            use_frase=trig_frase,
            use_ensaio=trig_ensaio,
            use_falha=trig_falha,
            use_erro_enter=trig_erro_enter,
            use_pensar3=use_pensar3,
            include_nums=use_nums,
        )

        flags = [nome for nome, on in (("frase", trig_frase), ("ensaio", trig_ensaio),
                                       ("falha", trig_falha), ("errEnter", trig_erro_enter),
                                       ("pensar3", use_pensar3)) if on]
        bd_txt = " | ".join(f"{k}={v:.2f}s" for k, v in breakdown.items() if v > 0.0) or "typing=0.00s"

        # Orçamento real: desconta o tempo já gasto desde que o turno virou meu
        orcamento = self._orcamento_restante()
        gasto = self._tempo_no_turno()
        self._log(f"Estimativa: ~{est:.2f}s | sobra ~{orcamento:.2f}s (gastos {gasto:.2f}s) | "
                  f"flags: {', '.join(flags) or 'nenhum'} | {bd_txt}")

        fast_path = apressado or est > orcamento
        if fast_path and not apressado:
            self._log(f"FAST PATH: {est:.2f}s > orçamento {orcamento:.2f}s → enviando direto.")
        if fast_path:
            trig_frase = trig_ensaio = trig_falha = trig_erro_enter = False
            use_nums = False
            use_pensar3 = False

        # ----- execução -----
        if trig_falha:
            enviada = self.typer.falha_proposital(escolha, self.pos.pos_chatbox)
            if enviada is None:
                self._log("Falha proposital cancelada (não era a sua vez no ENTER).")
                return "cancelado"
            self._log(f"Falha proposital enviada: {enviada}")
            self.erros_propositais += 1
            self.acertos_consecutivos = 0
            return "falha_proposital"

        if trig_erro_enter:
            self._log("Enviando UMA letra errada + ENTER; depois corrigindo.")
            if not self.typer.erro_enter_e_corrige(escolha, self.pos.pos_chatbox):
                self._log("Fluxo errEnter cancelado (não era sua vez em algum ENTER).")
                return "cancelado"
        else:
            if trig_frase:
                self._log("Frase engraçada & apagar (simulação).")
                self.typer.frase_engracada_e_apaga(self.pos.pos_chatbox)
            if trig_ensaio:
                self._log("Ensaio/rascunho & apagar (simulação).")
                self.typer.ensaiar_palavra_e_apagar(escolha, self.pos.pos_chatbox)

            if fast_path:
                ok_send = self.typer.digitar_quick(escolha, self.pos.pos_chatbox)
            elif use_pensar3 and len(escolha) >= 3:
                self._log(f"Pensar após 3 letras: pausa {h.pensar_3letras_pausa_ms} ms.")
                ok_send = self.typer.digitar_pensando_3(
                    escolha, self.pos.pos_chatbox,
                    think_ms=h.pensar_3letras_pausa_ms, override_nums=use_nums)
            else:
                ok_send = self.typer.digitar(escolha, self.pos.pos_chatbox, override_nums=use_nums)

            if not ok_send:
                self._log("Envio cancelado no ENTER (não era mais a sua vez).")
                return "cancelado"

        # ----- o jogo aceitou? -----
        if not self._verificar_aceite():
            return "recusada"

        self._registrar_aceite(escolha, use_nums)
        return "aceita"

    def _verificar_aceite(self):
        """Se o turno continua sendo meu logo após o ENTER, a palavra foi recusada."""
        if not self.cfg.verificar_envio or self.cfg.modo_teste:
            return True
        time.sleep(max(0.05, self.cfg.delay_verificacao_ms / 1000.0))
        return not self.capt.turno_ativo()

    def _registrar_aceite(self, palavra, use_nums):
        self.aceitas += 1
        self.selector.registrar_uso(palavra, self.modo_atual)
        self.historico.append(palavra)
        self.acertos_consecutivos += 1
        self._marcar_turno(False)  # o turno passou para o próximo jogador

        if use_nums:
            self.numeros_restantes = max(0, self.numeros_restantes - 1)
            if self.numeros_restantes == 0:
                self.cfg.humanizar.inserir_numeros = False
                self._log("Rodadas com números concluídas. Inserção de números desativada.")

    def _registrar_recusa(self, palavra):
        """Duas recusas = o JKLM não conhece a palavra; vai para rejeitadas.txt."""
        self.recusadas += 1
        self.acertos_consecutivos = 0
        n = self.strikes.get(palavra, 0) + 1
        self.strikes[palavra] = n

        if n >= 2 and self.cfg.aprender_rejeitadas:
            if self.dict.registrar_rejeitada(palavra, REJEITADAS_FILE):
                self._log(f"'{palavra}' recusada {n}x → aprendida em {REJEITADAS_FILE}.")
            else:
                self._log(f"'{palavra}' recusada {n}x (já estava na lista).")
        else:
            self._log(f"'{palavra}' recusada pelo jogo; tentando outra.")


# ==============================
# Interface Gráfica – Tema escuro moderno (Tkinter puro)
# ==============================

import queue


class T:
    """Paleta, espaçamentos e tipografia da interface."""
    BG        = "#0b0e14"
    SIDEBAR   = "#0f131c"
    SURFACE   = "#141924"
    SURFACE_2 = "#1b2230"
    HOVER     = "#232c3d"
    BORDER    = "#242c3b"

    TEXT      = "#e7ebf3"
    TEXT_DIM  = "#98a2b6"
    TEXT_MUTE = "#5f6a7d"

    ACCENT    = "#6c8cff"
    ACCENT_D  = "#5878ee"
    SUCCESS   = "#37d399"
    SUCCESS_D = "#2bb886"
    DANGER    = "#ff6b6b"
    DANGER_D  = "#ef5a5a"
    WARN      = "#ffb454"
    PURPLE    = "#b48cff"

    FONT       = ("Segoe UI", 10)
    FONT_SM    = ("Segoe UI", 9)
    FONT_BOLD  = ("Segoe UI Semibold", 10)
    FONT_H1    = ("Segoe UI Semibold", 16)
    FONT_H2    = ("Segoe UI Semibold", 11)
    FONT_BIG   = ("Segoe UI Semibold", 24)
    FONT_MONO  = ("Consolas", 10)


# ------------------------------
# Widgets customizados
# ------------------------------

_BTN_VARIANTS = {
    #          bg           hover        fg          border
    "primary": (T.ACCENT,   T.ACCENT_D,  "#ffffff",  T.ACCENT),
    "success": (T.SUCCESS,  T.SUCCESS_D, "#04211a",  T.SUCCESS),
    "danger":  (T.DANGER,   T.DANGER_D,  "#2b0a0a",  T.DANGER),
    "ghost":   (T.SURFACE_2, T.HOVER,    T.TEXT,     T.BORDER),
    "subtle":  (T.SURFACE,  T.HOVER,     T.TEXT_DIM, T.BORDER),
}


class Btn(tk.Frame):
    """Botão desenhado à mão: hover, variantes de cor e estado desabilitado."""

    def __init__(self, master, text, command=None, variant="ghost",
                 icon="", padx=16, pady=8, font=None, width=None):
        bg, hover, fg, border = _BTN_VARIANTS[variant]
        super().__init__(master, bg=bg, highlightthickness=1,
                         highlightbackground=border, highlightcolor=border, cursor="hand2")
        self._bg, self._hover, self._fg = bg, hover, fg
        self._command = command
        self._enabled = True

        label = f"{icon}  {text}".strip() if icon else text
        self.lbl = tk.Label(self, text=label, bg=bg, fg=fg,
                            font=font or T.FONT_BOLD, padx=padx, pady=pady, cursor="hand2")
        if width:
            self.lbl.configure(width=width)
        self.lbl.pack(fill="both", expand=True)

        for w in (self, self.lbl):
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", self._on_click)

    def _paint(self, bg):
        self.configure(bg=bg)
        self.lbl.configure(bg=bg)

    def _on_enter(self, _=None):
        if self._enabled:
            self._paint(self._hover)

    def _on_leave(self, _=None):
        if self._enabled:
            self._paint(self._bg)

    def _on_click(self, _=None):
        if self._enabled and self._command:
            self._command()

    def set_text(self, text):
        self.lbl.configure(text=text)

    def set_enabled(self, enabled: bool):
        self._enabled = bool(enabled)
        if self._enabled:
            self._paint(self._bg)
            self.lbl.configure(fg=self._fg, cursor="hand2")
            self.configure(cursor="hand2")
        else:
            self._paint(T.SURFACE_2)
            self.lbl.configure(fg=T.TEXT_MUTE, cursor="arrow")
            self.configure(cursor="arrow")


class Toggle(tk.Frame):
    """Switch estilo mobile (on/off) com rótulo opcional."""

    def __init__(self, master, text="", value=False, bg=T.SURFACE, command=None):
        super().__init__(master, bg=bg)
        self._value = bool(value)
        self._command = command
        self.cv = tk.Canvas(self, width=40, height=22, bg=bg, highlightthickness=0, cursor="hand2")
        self.cv.pack(side="left")
        self.cv.bind("<Button-1>", self._toggle)
        if text:
            self.lbl = tk.Label(self, text=text, bg=bg, fg=T.TEXT, font=T.FONT, cursor="hand2")
            self.lbl.pack(side="left", padx=(9, 0))
            self.lbl.bind("<Button-1>", self._toggle)
        self._draw()

    def _draw(self):
        c = T.ACCENT if self._value else "#2c3546"
        self.cv.delete("all")
        self.cv.create_oval(1, 1, 21, 21, fill=c, outline=c)
        self.cv.create_oval(18, 1, 38, 21, fill=c, outline=c)
        self.cv.create_rectangle(11, 1, 28, 21, fill=c, outline=c)
        kx = 27 if self._value else 12
        self.cv.create_oval(kx - 8, 3, kx + 8, 19, fill="#ffffff", outline="")

    def _toggle(self, _=None):
        self._value = not self._value
        self._draw()
        if self._command:
            self._command(self._value)

    def get(self):
        return self._value

    def set(self, value):
        self._value = bool(value)
        self._draw()


class Slider(tk.Frame):
    """Slider desenhado em Canvas: trilha arredondada, parte preenchida e knob."""

    def __init__(self, master, from_=0, to=100, value=0, suffix="", decimals=0,
                 bg=T.SURFACE, length=200, command=None):
        super().__init__(master, bg=bg)
        self.from_, self.to = float(from_), float(to)
        self._value = float(value)
        self.decimals, self.suffix = decimals, suffix
        self._command = command
        self._hot = False

        self.cv = tk.Canvas(self, height=26, width=length, bg=bg, highlightthickness=0, cursor="hand2")
        self.cv.pack(side="left", fill="x", expand=True)
        self.var = tk.StringVar()
        self.lbl = tk.Label(self, textvariable=self.var, bg=bg, fg=T.TEXT,
                            font=T.FONT_MONO, width=9, anchor="e")
        self.lbl.pack(side="left", padx=(10, 0))

        self.cv.bind("<Configure>", lambda e: self._draw())
        self.cv.bind("<Button-1>", self._on_drag)
        self.cv.bind("<B1-Motion>", self._on_drag)
        self.cv.bind("<Enter>", self._on_hot)
        self.cv.bind("<Leave>", self._on_cold)
        self._sync_label()

    def _on_hot(self, _=None):
        self._hot = True
        self._draw()

    def _on_cold(self, _=None):
        self._hot = False
        self._draw()

    def _sync_label(self):
        txt = f"{self._value:.{self.decimals}f}"
        self.var.set(f"{txt} {self.suffix}".strip())

    def _draw(self):
        w = self.cv.winfo_width()
        if w <= 1:
            return
        pad, y = 10, 13
        self.cv.delete("all")
        self.cv.create_line(pad, y, w - pad, y, fill="#2a3346", width=6, capstyle="round")
        span = (self.to - self.from_) or 1.0
        frac = clamp((self._value - self.from_) / span, 0.0, 1.0)
        x = pad + frac * (w - 2 * pad)
        if x > pad:
            self.cv.create_line(pad, y, x, y, fill=T.ACCENT, width=6, capstyle="round")
        r = 9 if self._hot else 7
        self.cv.create_oval(x - r, y - r, x + r, y + r, fill="#ffffff", outline=T.ACCENT, width=2)

    def _on_drag(self, event):
        w = self.cv.winfo_width()
        pad = 10
        frac = clamp((event.x - pad) / max(1, (w - 2 * pad)), 0.0, 1.0)
        self._value = self.from_ + frac * (self.to - self.from_)
        if self.decimals == 0:
            self._value = round(self._value)
        self._sync_label()
        self._draw()
        if self._command:
            self._command(self._value)

    def get(self):
        return self._value

    def set(self, value):
        self._value = clamp(float(value), self.from_, self.to)
        self._sync_label()
        self._draw()


class Stepper(tk.Frame):
    """Campo numérico compacto com botões − / +."""

    def __init__(self, master, from_=0, to=100, value=0, step=1, bg=T.SURFACE, width=4):
        super().__init__(master, bg=bg)
        self.from_, self.to, self.step = int(from_), int(to), int(step)
        self._value = int(clamp(value, from_, to))

        box = tk.Frame(self, bg=T.SURFACE_2, highlightthickness=1, highlightbackground=T.BORDER)
        box.pack(side="left")
        self._mk_btn(box, "−", -1).pack(side="left")
        self.lbl = tk.Label(box, text=str(self._value), bg=T.SURFACE_2, fg=T.TEXT,
                            font=T.FONT_MONO, width=width)
        self.lbl.pack(side="left", pady=5)
        self._mk_btn(box, "+", +1).pack(side="left")

    def _mk_btn(self, parent, text, direction):
        b = tk.Label(parent, text=text, bg=T.SURFACE_2, fg=T.TEXT_DIM,
                     font=T.FONT_BOLD, width=3, pady=4, cursor="hand2")
        b.bind("<Enter>", lambda e: b.configure(bg=T.HOVER, fg=T.TEXT))
        b.bind("<Leave>", lambda e: b.configure(bg=T.SURFACE_2, fg=T.TEXT_DIM))
        b.bind("<Button-1>", lambda e: self._bump(direction))
        return b

    def _bump(self, direction):
        self._value = int(clamp(self._value + direction * self.step, self.from_, self.to))
        self.lbl.configure(text=str(self._value))

    def get(self):
        return self._value

    def set(self, value):
        self._value = int(clamp(value, self.from_, self.to))
        self.lbl.configure(text=str(self._value))


class Segmented(tk.Frame):
    """Grupo de opções mutuamente exclusivas (substitui radiobuttons)."""

    def __init__(self, master, options, value=None, bg=T.SURFACE, command=None):
        super().__init__(master, bg=T.SURFACE_2, highlightthickness=1, highlightbackground=T.BORDER)
        self._command = command
        self._items = {}
        self._value = value if value is not None else options[0][1]
        for text, val in options:
            lbl = tk.Label(self, text=text, bg=T.SURFACE_2, fg=T.TEXT_DIM,
                           font=T.FONT, padx=14, pady=6, cursor="hand2")
            lbl.pack(side="left", padx=2, pady=2)
            lbl.bind("<Button-1>", lambda e, v=val: self.set(v, notify=True))
            lbl.bind("<Enter>", lambda e, v=val, w=lbl: w.configure(fg=T.TEXT) if self._value != v else None)
            lbl.bind("<Leave>", lambda e, v=val, w=lbl: w.configure(fg=T.TEXT_DIM) if self._value != v else None)
            self._items[val] = lbl
        self._paint()

    def _paint(self):
        for val, lbl in self._items.items():
            if val == self._value:
                lbl.configure(bg=T.ACCENT, fg="#ffffff", font=T.FONT_BOLD)
            else:
                lbl.configure(bg=T.SURFACE_2, fg=T.TEXT_DIM, font=T.FONT)

    def get(self):
        return self._value

    def set(self, value, notify=False):
        self._value = value
        self._paint()
        if notify and self._command:
            self._command(value)


class ModeSelector(tk.Frame):
    """Cartões grandes e clicáveis para escolher o modo de jogo."""

    def __init__(self, master, options, value, bg=T.SURFACE, command=None):
        super().__init__(master, bg=bg)
        self._command = command
        self._value = value
        self._cards = {}
        for i, (titulo, desc, val) in enumerate(options):
            card = tk.Frame(self, bg=T.SURFACE_2, highlightthickness=2, highlightbackground=T.BORDER, cursor="hand2")
            card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=5, pady=5)
            dot = tk.Canvas(card, width=14, height=14, bg=T.SURFACE_2, highlightthickness=0)
            dot.grid(row=0, column=0, rowspan=2, padx=(14, 10), pady=14, sticky="n")
            t = tk.Label(card, text=titulo, bg=T.SURFACE_2, fg=T.TEXT, font=T.FONT_H2, anchor="w")
            t.grid(row=0, column=1, sticky="w", pady=(13, 0), padx=(0, 14))
            d = tk.Label(card, text=desc, bg=T.SURFACE_2, fg=T.TEXT_MUTE, font=T.FONT_SM, anchor="w")
            d.grid(row=1, column=1, sticky="w", pady=(1, 13), padx=(0, 14))
            card.columnconfigure(1, weight=1)
            self._cards[val] = (card, dot, t, d)
            for w in (card, dot, t, d):
                w.bind("<Button-1>", lambda e, v=val: self.set(v, notify=True))
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self._paint()

    def _paint(self):
        for val, (card, dot, t, d) in self._cards.items():
            sel = (val == self._value)
            bg = T.HOVER if sel else T.SURFACE_2
            card.configure(highlightbackground=T.ACCENT if sel else T.BORDER, bg=bg)
            for w in (t, d):
                w.configure(bg=bg)
            t.configure(fg=T.TEXT if sel else T.TEXT_DIM)
            dot.configure(bg=bg)
            dot.delete("all")
            dot.create_oval(1, 1, 13, 13, outline=T.ACCENT if sel else "#3a4459", width=2)
            if sel:
                dot.create_oval(4, 4, 10, 10, fill=T.ACCENT, outline="")

    def get(self):
        return self._value

    def set(self, value, notify=False):
        self._value = value
        self._paint()
        if notify and self._command:
            self._command(value)


class StatCard(tk.Frame):
    """Cartão com número grande + legenda."""

    def __init__(self, master, caption, value="0", color=T.ACCENT, bg=T.BG):
        super().__init__(master, bg=T.SURFACE, highlightthickness=1, highlightbackground=T.BORDER)
        tk.Frame(self, bg=color, height=3).pack(fill="x")
        inner = tk.Frame(self, bg=T.SURFACE)
        inner.pack(fill="both", expand=True, padx=16, pady=(12, 14))
        self.val = tk.Label(inner, text=value, bg=T.SURFACE, fg=T.TEXT, font=T.FONT_BIG, anchor="w")
        self.val.pack(anchor="w")
        tk.Label(inner, text=caption.upper(), bg=T.SURFACE, fg=T.TEXT_MUTE,
                 font=("Segoe UI", 8, "bold"), anchor="w").pack(anchor="w", pady=(2, 0))

    def set(self, value):
        self.val.configure(text=str(value))


class AlfabetoGrid(tk.Frame):
    """Progresso rumo à vida extra: as 23 letras úteis acendem conforme são usadas."""

    def __init__(self, master, bg=T.SURFACE, colunas=8):
        super().__init__(master, bg=bg)
        self._chips = {}
        for i, ch in enumerate(LETRAS_ALFABETO):
            lbl = tk.Label(self, text=ch.upper(), bg=T.SURFACE_2, fg=T.TEXT_MUTE,
                           font=("Consolas", 10, "bold"), pady=4)
            lbl.grid(row=i // colunas, column=i % colunas, padx=2, pady=2, sticky="nsew")
            self._chips[ch] = lbl
        for c in range(colunas):
            self.columnconfigure(c, weight=1)

    def atualizar(self, usadas):
        for ch, lbl in self._chips.items():
            if ch in usadas:
                lbl.configure(bg=T.SUCCESS, fg="#04211a")
            else:
                lbl.configure(bg=T.SURFACE_2, fg=T.TEXT_MUTE)


# Perfis prontos: valores no formato dos widgets (ms, %, s)
PRESETS = {
    "Seguro": {
        "descricao": "Parece gente de verdade. Erra, hesita e conversa — mais lento.",
        "perfil": VelocidadePerfil.ALEATORIA.value,
        "delay_letra": 55, "chance_erro": 6, "var_delay": 20,
        "pausa_cada": 4, "pausa_min": 0.030, "pausa_max": 0.120,
        "falha": 3, "err_enter": 6, "frase": 20, "ensaio": 25,
        "pensar3": True, "pensar_ms": 500, "limite": 6.0,
    },
    "Equilibrado": {
        "descricao": "Humanização discreta sem perder rodadas. Bom padrão.",
        "perfil": VelocidadePerfil.ALEATORIA.value,
        "delay_letra": 20, "chance_erro": 3, "var_delay": 12,
        "pausa_cada": 4, "pausa_min": 0.020, "pausa_max": 0.070,
        "falha": 1, "err_enter": 3, "frase": 8, "ensaio": 12,
        "pensar3": True, "pensar_ms": 350, "limite": 4.0,
    },
    "Agressivo": {
        "descricao": "Sem encenação: digita e manda. Para ganhar, não para disfarçar.",
        "perfil": VelocidadePerfil.RAPIDA.value,
        "delay_letra": 5, "chance_erro": 0, "var_delay": 5,
        "pausa_cada": 8, "pausa_min": 0.010, "pausa_max": 0.030,
        "falha": 0, "err_enter": 0, "frase": 0, "ensaio": 0,
        "pensar3": False, "pensar_ms": 200, "limite": 2.0,
    },
}


class ScrollArea(tk.Frame):
    """Área rolável com scroll pelo mouse."""

    def __init__(self, master, bg=T.BG):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview, style="Dark.Vertical.TScrollbar")
        self.body = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")

        self.body.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))

    def _wheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def activate(self):
        """Liga a roda do mouse enquanto esta página estiver visível."""
        self.canvas.bind_all("<MouseWheel>", self._wheel)

    def deactivate(self):
        self.canvas.unbind_all("<MouseWheel>")


def make_card(parent, title=None, subtitle=None, bg=T.BG, pad=16):
    """Cria um cartão com cabeçalho opcional. Retorna (container, corpo)."""
    outer = tk.Frame(parent, bg=T.SURFACE, highlightthickness=1, highlightbackground=T.BORDER)
    if title:
        head = tk.Frame(outer, bg=T.SURFACE)
        head.pack(fill="x", padx=pad, pady=(pad, 0))
        tk.Label(head, text=title, bg=T.SURFACE, fg=T.TEXT, font=T.FONT_H2).pack(anchor="w")
        if subtitle:
            tk.Label(head, text=subtitle, bg=T.SURFACE, fg=T.TEXT_MUTE,
                     font=T.FONT_SM, justify="left").pack(anchor="w", pady=(3, 0))
    body = tk.Frame(outer, bg=T.SURFACE)
    body.pack(fill="both", expand=True, padx=pad, pady=(12 if title else pad, pad))
    return outer, body


def form_row(parent, label, hint=None, bg=T.SURFACE, label_px=280):
    """Linha de formulário: rótulo (+ dica) à esquerda, widget à direita.

    Usa grid com coluna esquerda de largura fixa para que todos os controles
    de um cartão fiquem alinhados verticalmente.
    """
    r = tk.Frame(parent, bg=bg)
    r.pack(fill="x", pady=6)
    left = tk.Frame(r, bg=bg)
    left.grid(row=0, column=0, sticky="w")
    tk.Label(left, text=label, bg=bg, fg=T.TEXT, font=T.FONT,
             anchor="w", justify="left").pack(anchor="w")
    if hint:
        tk.Label(left, text=hint, bg=bg, fg=T.TEXT_MUTE, font=T.FONT_SM, anchor="w",
                 justify="left", wraplength=label_px - 20).pack(anchor="w", pady=(1, 0))
    right = tk.Frame(r, bg=bg)
    right.grid(row=0, column=1, sticky="ew", padx=(14, 0))
    r.columnconfigure(0, minsize=label_px)
    r.columnconfigure(1, weight=1)
    return right


def dark_entry(parent, value="", width=40):
    e = tk.Entry(parent, bg=T.SURFACE_2, fg=T.TEXT, font=T.FONT, width=width,
                 relief="flat", insertbackground=T.ACCENT, highlightthickness=1,
                 highlightbackground=T.BORDER, highlightcolor=T.ACCENT)
    e.insert(0, value)
    e.configure(disabledbackground=T.SURFACE_2)
    return e


# ------------------------------
# Aplicação
# ------------------------------

class AppUI:
    NAV = [
        ("principal", "▶", "Principal"),
        ("console",   "▤", "Console"),
        ("setup",     "⚙", "Setup"),
        ("humano",    "✎", "Humanização"),
        ("stats",     "▦", "Estatísticas"),
    ]

    def __init__(self):
        self.cfg_mgr = ConfigManager()
        self.cfg_mgr.load()
        self.pos_mgr = PosicoesManager()
        self.pos_mgr.load()

        # Precisa acontecer antes de qualquer janela existir
        self._dpi_msg = aplicar_dpi_awareness(self.cfg_mgr.config.dpi_aware)

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.configure(bg=T.BG)
        self.root.minsize(980, 640)
        self._center(1160, 780)
        self.root.attributes("-topmost", True)

        self._init_style()

        # Fila de logs (mantém as chamadas do bot fora da thread da UI)
        self._log_queue = queue.Queue()
        self._capture_listener = None
        self._capture_hint = None

        self.bot = BotCore(self.cfg_mgr.config, self.pos_mgr, self.enqueue_log)

        self._build_layout()
        self._show_page("principal")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Control-s>", lambda e: self._salvar_config())
        self.root.bind("<F8>", lambda e: self._handle_kill_switch())

        threading.Thread(target=self._monitor_f8, daemon=True).start()
        self._drain_logs()
        self._refresh_stats()

        self.enqueue_log("Configurações e posições carregadas.")
        if self._dpi_msg:
            self.enqueue_log(self._dpi_msg)
        self.root.after(400, self._rodar_diagnostico)
        threading.Thread(target=self._preload_dicionario, daemon=True).start()
        self.root.mainloop()

    def _preload_dicionario(self):
        """Carrega o dicionário logo na abertura para já mostrar o total e avisar de erros."""
        try:
            self.bot.carregar_dict_e_blacklist()
        except Exception as e:
            self.enqueue_log(f"Falha ao carregar dicionário: {e}")

    def _center(self, w, h):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w = min(w, sw - 80)
        h = min(h, sh - 120)
        x, y = int((sw - w) / 2), int((sh - h) / 2.4)
        self.root.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

    def _init_style(self):
        self.style = ttk.Style(self.root)
        self.style.theme_use("clam")
        self.style.configure("Dark.Vertical.TScrollbar",
                             background=T.SURFACE_2, troughcolor=T.BG, bordercolor=T.BG,
                             arrowcolor=T.TEXT_MUTE, darkcolor=T.SURFACE_2, lightcolor=T.SURFACE_2,
                             relief="flat", width=10)
        self.style.map("Dark.Vertical.TScrollbar", background=[("active", T.HOVER)])

    # ---------- Layout base ----------
    def _build_layout(self):
        self._build_sidebar()

        main = tk.Frame(self.root, bg=T.BG)
        main.pack(side="left", fill="both", expand=True)

        self._build_topbar(main)
        # a barra de status é empacotada antes do conteúdo para não ser espremida
        self._build_statusbar(main)

        self.content = tk.Frame(main, bg=T.BG)
        self.content.pack(fill="both", expand=True)

        self.pages = {}
        self.pages["principal"] = self._build_page_principal(self.content)
        self.pages["console"] = self._build_page_console(self.content)
        self.pages["setup"] = self._build_page_setup(self.content)
        self.pages["humano"] = self._build_page_humano(self.content)
        self.pages["stats"] = self._build_page_stats(self.content)

    def _build_sidebar(self):
        sb = tk.Frame(self.root, bg=T.SIDEBAR, width=212)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        brand = tk.Frame(sb, bg=T.SIDEBAR)
        brand.pack(fill="x", padx=20, pady=(24, 26))
        logo = tk.Canvas(brand, width=34, height=34, bg=T.SIDEBAR, highlightthickness=0)
        logo.pack(side="left")
        logo.create_oval(1, 1, 33, 33, fill=T.ACCENT, outline="")
        logo.create_text(17, 18, text="B", fill="#ffffff", font=("Segoe UI Semibold", 15))
        txt = tk.Frame(brand, bg=T.SIDEBAR)
        txt.pack(side="left", padx=(10, 0))
        tk.Label(txt, text="Bombinha", bg=T.SIDEBAR, fg=T.TEXT, font=T.FONT_H1).pack(anchor="w")
        tk.Label(txt, text="JKLM.fun PT-BR", bg=T.SIDEBAR, fg=T.TEXT_MUTE, font=T.FONT_SM).pack(anchor="w")

        self.nav_items = {}
        for key, icon, label in self.NAV:
            row = tk.Frame(sb, bg=T.SIDEBAR, cursor="hand2")
            row.pack(fill="x", padx=12, pady=2)
            bar = tk.Frame(row, bg=T.SIDEBAR, width=3)
            bar.pack(side="left", fill="y")
            ic = tk.Label(row, text=icon, bg=T.SIDEBAR, fg=T.TEXT_MUTE, font=("Segoe UI", 11), width=3)
            ic.pack(side="left", pady=9)
            lb = tk.Label(row, text=label, bg=T.SIDEBAR, fg=T.TEXT_DIM, font=T.FONT, anchor="w")
            lb.pack(side="left", fill="x", expand=True)
            for w in (row, ic, lb):
                w.bind("<Button-1>", lambda e, k=key: self._show_page(k))
                w.bind("<Enter>", lambda e, k=key: self._nav_hover(k, True))
                w.bind("<Leave>", lambda e, k=key: self._nav_hover(k, False))
            self.nav_items[key] = (row, bar, ic, lb)

        footer = tk.Frame(sb, bg=T.SIDEBAR)
        footer.pack(side="bottom", fill="x", padx=20, pady=18)
        tk.Frame(footer, bg=T.BORDER, height=1).pack(fill="x", pady=(0, 12))
        for atalho in ("F8  ·  parar tudo", "F7  ·  trocar modo",
                       "F6  ·  nova partida", "Ctrl+S  ·  salvar"):
            tk.Label(footer, text=atalho, bg=T.SIDEBAR, fg=T.TEXT_MUTE, font=T.FONT_SM).pack(anchor="w")
        self.lbl_dev = tk.Label(footer, text="dev @lucasleao18", bg=T.SIDEBAR, fg=T.ACCENT, font=T.FONT_SM)
        self.lbl_dev.pack(anchor="w", pady=(10, 0))

    def _nav_hover(self, key, entering):
        if getattr(self, "_page_atual", None) == key:
            return
        row, bar, ic, lb = self.nav_items[key]
        bg = T.SURFACE if entering else T.SIDEBAR
        for w in (row, ic, lb):
            w.configure(bg=bg)
        bar.configure(bg=bg)
        lb.configure(fg=T.TEXT if entering else T.TEXT_DIM)

    def _build_topbar(self, parent):
        bar = tk.Frame(parent, bg=T.BG)
        bar.pack(fill="x", padx=28, pady=(22, 8))

        left = tk.Frame(bar, bg=T.BG)
        left.pack(side="left")
        self.lbl_page = tk.Label(left, text="Principal", bg=T.BG, fg=T.TEXT, font=T.FONT_H1)
        self.lbl_page.pack(anchor="w")
        self.lbl_page_sub = tk.Label(left, text="Escolha o modo e inicie a automação",
                                     bg=T.BG, fg=T.TEXT_MUTE, font=T.FONT_SM)
        self.lbl_page_sub.pack(anchor="w", pady=(2, 0))

        right = tk.Frame(bar, bg=T.BG)
        right.pack(side="right")

        self.pill = tk.Frame(right, bg=T.SURFACE, highlightthickness=1, highlightbackground=T.BORDER)
        self.pill.pack(side="left", padx=(0, 12))
        self.pill_dot = tk.Canvas(self.pill, width=10, height=10, bg=T.SURFACE, highlightthickness=0)
        self.pill_dot.pack(side="left", padx=(12, 0), pady=9)
        self.pill_txt = tk.Label(self.pill, text="Parado", bg=T.SURFACE, fg=T.DANGER, font=T.FONT_BOLD)
        self.pill_txt.pack(side="left", padx=(8, 14))
        self._paint_pill(False)

        self.tgl_top = Toggle(right, text="Sempre no topo", value=True, bg=T.BG, command=self._toggle_topmost)
        self.tgl_top.pack(side="left")

    def _paint_pill(self, rodando):
        cor = T.SUCCESS if rodando else T.DANGER
        self.pill_txt.configure(text="Rodando" if rodando else "Parado", fg=cor)
        self.pill_dot.delete("all")
        self.pill_dot.create_oval(1, 1, 9, 9, fill=cor, outline="")

    def _build_statusbar(self, parent):
        bar = tk.Frame(parent, bg=T.SIDEBAR, height=30)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.lbl_status_msg = tk.Label(bar, text="Pronto.", bg=T.SIDEBAR, fg=T.TEXT_MUTE, font=T.FONT_SM)
        self.lbl_status_msg.pack(side="left", padx=18)
        self.lbl_status_right = tk.Label(bar, text="", bg=T.SIDEBAR, fg=T.TEXT_MUTE, font=T.FONT_SM)
        self.lbl_status_right.pack(side="right", padx=18)

    def _show_page(self, key):
        for page in self.pages.values():
            if isinstance(page, ScrollArea):
                page.deactivate()
            page.pack_forget()
        alvo = self.pages[key]
        alvo.pack(fill="both", expand=True, padx=28, pady=(10, 18))
        if isinstance(alvo, ScrollArea):
            alvo.activate()
        if key == "stats":
            self._refresh_historico()
        self._page_atual = key

        titulos = {
            "principal": ("Principal", "Escolha o modo e inicie a automação"),
            "console":   ("Console", "Acompanhe cada decisão do bot em tempo real"),
            "setup":     ("Setup", "Dicionário, posições de tela e delays"),
            "humano":    ("Humanização", "Perfil de digitação e comportamentos humanos"),
            "stats":     ("Estatísticas", "Desempenho da sessão e histórico de palavras"),
        }
        self.lbl_page.configure(text=titulos[key][0])
        self.lbl_page_sub.configure(text=titulos[key][1])

        for k, (row, bar, ic, lb) in self.nav_items.items():
            sel = (k == key)
            bg = T.SURFACE if sel else T.SIDEBAR
            for w in (row, ic, lb):
                w.configure(bg=bg)
            bar.configure(bg=T.ACCENT if sel else bg)
            ic.configure(fg=T.ACCENT if sel else T.TEXT_MUTE)
            lb.configure(fg=T.TEXT if sel else T.TEXT_DIM, font=T.FONT_BOLD if sel else T.FONT)

    # ---------- Página: Principal ----------
    def _build_page_principal(self, parent):
        page = ScrollArea(parent, bg=T.BG)

        cols = tk.Frame(page.body, bg=T.BG)
        cols.pack(fill="both", expand=True)
        left = tk.Frame(cols, bg=T.BG)
        right = tk.Frame(cols, bg=T.BG)
        left.grid(row=0, column=0, sticky="nsew")
        right.grid(row=0, column=1, sticky="new", padx=(18, 0))
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(1, minsize=320)

        card, body = make_card(left, "Modo de jogo", "Define como as palavras são escolhidas no dicionário")
        card.pack(fill="x")
        self.modo_sel = ModeSelector(body, [
            ("Palavras Longas", "Prioriza tamanho máximo", Modo.LONGA.value),
            ("Palavras Curtas", "Mais rápido de digitar", Modo.CURTA.value),
            ("Qualquer Palavra", "Equilíbrio entre as opções", Modo.QUALQUER.value),
            ("Modo Alfabeto", "Cobre as 23 letras úteis", Modo.ALFABETO.value),
        ], value=self.cfg_mgr.config.modo, command=self._on_modo)
        self.modo_sel.pack(fill="x")

        ctrl, cbody = make_card(left, "Controle")
        ctrl.pack(fill="x", pady=(18, 0))
        btns = tk.Frame(cbody, bg=T.SURFACE)
        btns.pack(fill="x")
        self.btn_iniciar = Btn(btns, "Iniciar", command=self._iniciar, variant="success", icon="▶", padx=34, pady=11)
        self.btn_iniciar.pack(side="left")
        self.btn_parar = Btn(btns, "Parar  (F8)", command=self._parar, variant="danger", icon="■", padx=30, pady=11)
        self.btn_parar.pack(side="left", padx=10)
        self.btn_parar.set_enabled(False)

        btns2 = tk.Frame(cbody, bg=T.SURFACE)
        btns2.pack(fill="x", pady=(10, 0))
        Btn(btns2, "Nova partida  (F6)", command=self._nova_partida, variant="ghost", icon="⟲",
            padx=16, pady=8).pack(side="left")
        Btn(btns2, "Recarregar dicionário", command=self._recarregar_dicionario, variant="ghost", icon="⟳",
            padx=16, pady=8).pack(side="left", padx=10)

        tk.Label(cbody, text="Deixe a janela do jogo em foco antes de iniciar.   "
                             "F8 para tudo  ·  F7 troca de modo  ·  F6 nova partida.",
                 bg=T.SURFACE, fg=T.TEXT_MUTE, font=T.FONT_SM).pack(anchor="w", pady=(12, 0))

        live, lbody = make_card(left, "Rodada atual")
        live.pack(fill="x", pady=(18, 0))
        self.live_letras = self._live_row(lbody, "Letras detectadas", "—", T.PURPLE)
        self.live_palavra = self._live_row(lbody, "Palavra escolhida", "—", T.ACCENT)
        self.live_evento = self._live_row(lbody, "Último evento", "aguardando…", T.TEXT_DIM)

        # coluna direita – mini estatísticas
        self.card_palavras = StatCard(right, "palavras enviadas", "0", T.ACCENT)
        self.card_palavras.pack(fill="x")
        self.card_sequencia = StatCard(right, "acertos consecutivos", "0", T.SUCCESS)
        self.card_sequencia.pack(fill="x", pady=(14, 0))
        self.card_dict = StatCard(right, "palavras no dicionário", "0", T.PURPLE)
        self.card_dict.pack(fill="x", pady=(14, 0))

        alf, abody = make_card(right, "Vida extra", "Letras já usadas (K, W e Y não contam)")
        alf.pack(fill="x", pady=(14, 0))
        self.grid_alfabeto = AlfabetoGrid(abody)
        self.grid_alfabeto.pack(fill="x")
        self.lbl_alfabeto = tk.Label(abody, text="0 / 23", bg=T.SURFACE, fg=T.TEXT_DIM, font=T.FONT_SM)
        self.lbl_alfabeto.pack(anchor="e", pady=(8, 0))

        tip, tbody = make_card(right, "Dica")
        tip.pack(fill="x", pady=(14, 0))
        tk.Label(tbody, text="Se o bot enviar em turnos alheios, aumente o threshold da barra "
                             "de turno no Setup. Falsos negativos? Reduza um pouco.",
                 bg=T.SURFACE, fg=T.TEXT_DIM, font=T.FONT_SM, wraplength=250, justify="left").pack(anchor="w")
        return page

    def _live_row(self, parent, label, value, color):
        r = tk.Frame(parent, bg=T.SURFACE)
        r.pack(fill="x", pady=6)
        tk.Frame(r, bg=color, width=3, height=34).pack(side="left", padx=(0, 12))
        box = tk.Frame(r, bg=T.SURFACE)
        box.pack(side="left", fill="x", expand=True)
        tk.Label(box, text=label.upper(), bg=T.SURFACE, fg=T.TEXT_MUTE,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        val = tk.Label(box, text=value, bg=T.SURFACE, fg=T.TEXT, font=T.FONT_H2, anchor="w")
        val.pack(anchor="w")
        return val

    # ---------- Página: Console ----------
    def _build_page_console(self, parent):
        page = tk.Frame(parent, bg=T.BG)

        tools = tk.Frame(page, bg=T.BG)
        tools.pack(fill="x", pady=(0, 12))
        Btn(tools, "Limpar", command=self._limpar_terminal, variant="ghost", icon="✕", padx=14, pady=7).pack(side="left")
        Btn(tools, "Copiar tudo", command=self._copiar_terminal, variant="ghost", icon="⧉", padx=14, pady=7).pack(side="left", padx=8)
        self.tgl_autoscroll = Toggle(tools, text="Rolagem automática", value=True, bg=T.BG)
        self.tgl_autoscroll.pack(side="right")

        wrap = tk.Frame(page, bg=T.SURFACE, highlightthickness=1, highlightbackground=T.BORDER)
        wrap.pack(fill="both", expand=True)
        self.terminal = tk.Text(wrap, bg="#0a0d14", fg=T.TEXT, font=T.FONT_MONO, wrap="word",
                                relief="flat", padx=16, pady=12, state=tk.DISABLED,
                                insertbackground=T.ACCENT, selectbackground=T.HOVER, spacing1=1, spacing3=2)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.terminal.yview, style="Dark.Vertical.TScrollbar")
        self.terminal.configure(yscrollcommand=sb.set)
        self.terminal.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.terminal.tag_config("time", foreground=T.TEXT_MUTE)
        self.terminal.tag_config("info", foreground=T.TEXT_DIM)
        self.terminal.tag_config("ok", foreground=T.SUCCESS)
        self.terminal.tag_config("warn", foreground=T.WARN)
        self.terminal.tag_config("err", foreground=T.DANGER)
        self.terminal.tag_config("accent", foreground=T.ACCENT)
        return page

    # ---------- Página: Setup ----------
    def _build_page_setup(self, parent):
        cfg = self.cfg_mgr.config
        page = ScrollArea(parent, bg=T.BG)
        body = page.body

        # --- Dicionário ---
        card, b = make_card(body, "Dicionário e detecção", "Fontes de palavras e reconhecimento de tela")
        card.pack(fill="x")

        r = form_row(b, "Caminho do dicionário", "Arquivo .txt com uma palavra por linha")
        self.ent_dict = dark_entry(r, cfg.caminho_dicionario)
        self.ent_dict.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 8))
        Btn(r, "Abrir", command=self._browse_dict, variant="ghost", padx=14, pady=5).pack(side="left")

        r = form_row(b, "Template da chatbox", "Imagem .png usada para localizar o campo (opcional)")
        self.ent_tpl = dark_entry(r, cfg.template_chatbox)
        self.ent_tpl.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 8))
        Btn(r, "Abrir", command=self._browse_tpl, variant="ghost", padx=14, pady=5).pack(side="left")

        r = form_row(b, "Threshold do template", "Maior = mais rígido para achar a chatbox")
        self.sld_thr = Slider(r, 0.50, 0.99, cfg.template_threshold, decimals=2)
        self.sld_thr.pack(fill="x")

        r = form_row(b, "Threshold da barra de turno", "Maior = evita enviar no turno dos outros")
        self.sld_turn_thr = Slider(r, 0.50, 0.99, cfg.turn_bar_threshold, decimals=2)
        self.sld_turn_thr.pack(fill="x")

        r = form_row(b, "Como comparar a barra de turno",
                     "Pixel = original; Cor = tolera a barra encolher; Híbrido = os dois")
        self.seg_turno = Segmented(r, [("Pixel", MetodoTurno.PIXEL.value),
                                       ("Cor", MetodoTurno.COR.value),
                                       ("Híbrido", MetodoTurno.HIBRIDO.value)],
                                   value=cfg.turn_bar_metodo)
        self.seg_turno.pack(side="left")

        # --- Captura da sílaba ---
        card, b = make_card(body, "Captura da sílaba",
                            "Como o bot lê as letras do desafio a cada turno")
        card.pack(fill="x", pady=(18, 0))

        r = form_row(b, "Método",
                     "OCR dispensa mouse e clipboard, mas exige pytesseract + Tesseract instalados")
        self.seg_captura = Segmented(r, [("Duplo-clique + Ctrl+C", MetodoCaptura.CLIPBOARD.value),
                                         ("OCR da imagem", MetodoCaptura.OCR.value)],
                                     value=cfg.metodo_captura)
        self.seg_captura.pack(side="left")

        r = form_row(b, "Preservar área de transferência",
                     "Devolve o que você tinha copiado depois de ler a sílaba")
        self.tgl_clip = Toggle(r, "Ativar", cfg.preservar_clipboard)
        self.tgl_clip.pack(side="left")

        r = form_row(b, "Tipo de clique para selecionar",
                     "Triplo pega a linha inteira e erra menos; Auto tenta duplo e depois triplo")
        self.seg_clique = Segmented(r, [("Duplo", "duplo"), ("Triplo", "triplo"), ("Auto", "auto")],
                                    value=cfg.clique_captura)
        self.seg_clique.pack(side="left")

        r = form_row(b, "Tentativas de captura",
                     "Repete o clique + Ctrl+C quando nada é selecionado")
        self.stp_tent_captura = Stepper(r, 1, 6, cfg.tentativas_captura)
        self.stp_tent_captura.pack(side="left")

        self.lbl_letras_rect = self._pos_row(b, "Região da sílaba (OCR, 2 cliques)",
                                             self.pos_mgr.letras_rect or "não capturada",
                                             self._capturar_letras_rect)

        # --- Verificação de envio ---
        card, b = make_card(body, "Verificação e aprendizado",
                            "O JKLM recusa palavra repetida ou fora do dicionário dele; "
                            "aqui o bot percebe isso e reage")
        card.pack(fill="x", pady=(18, 0))

        r = form_row(b, "Conferir se a palavra foi aceita",
                     "Se continuar sendo sua vez após o ENTER, foi recusada")
        self.tgl_verificar = Toggle(r, "Ativar", cfg.verificar_envio)
        self.tgl_verificar.pack(side="left")

        r = form_row(b, "Espera antes de conferir")
        self.sld_verif_ms = Slider(r, 120, 1200, cfg.delay_verificacao_ms, suffix="ms")
        self.sld_verif_ms.pack(fill="x")

        r = form_row(b, "Tentativas por rodada", "Quantas palavras tentar antes de desistir do turno")
        self.stp_tentativas = Stepper(r, 1, 6, cfg.max_tentativas_rodada)
        self.stp_tentativas.pack(side="left")

        r = form_row(b, "Aprender palavras recusadas",
                     f"Recusada 2x vai para {REJEITADAS_FILE} e nunca mais é usada")
        self.tgl_aprender = Toggle(r, "Ativar", cfg.aprender_rejeitadas)
        self.tgl_aprender.pack(side="left")

        r = form_row(b, "Nova partida automática",
                     "Zera as palavras usadas após um tempo sem turnos")
        self.tgl_auto_partida = Toggle(r, "Ativar", cfg.auto_nova_partida)
        self.tgl_auto_partida.pack(side="left")

        r = form_row(b, "Tempo de inatividade")
        self.sld_inatividade = Slider(r, 15, 180, cfg.inatividade_nova_partida_s, suffix="s")
        self.sld_inatividade.pack(fill="x")

        # --- Posições ---
        card, b = make_card(body, "Posições na tela",
                            "Clique em «Capturar» e depois no ponto correspondente dentro do jogo")
        card.pack(fill="x", pady=(18, 0))

        self.lbl_pos_letras = self._pos_row(b, "Área das letras", self.pos_mgr.pos_letras, self._capturar_pos_letras)
        self.lbl_pos_chat = self._pos_row(b, "Campo de digitação", self.pos_mgr.pos_chatbox, self._capturar_pos_chat)
        self.lbl_turn_rect = self._pos_row(b, "Barra de turno (2 cliques)", self.pos_mgr.turn_bar_rect, self._capturar_turn_bar)

        Btn(b, "Salvar posições", command=self._salvar_posicoes, variant="ghost", icon="💾",
            padx=16, pady=7).pack(anchor="w", pady=(10, 0))

        # --- Delays ---
        card, b = make_card(body, "Ritmo e limites", "Controla a velocidade geral do ciclo")
        card.pack(fill="x", pady=(18, 0))

        r = form_row(b, "Entre ciclos", "Pausa entre uma verificação e outra")
        self.sld_ciclo = Slider(r, 80, 1000, cfg.delay_ciclo_ms, suffix="ms")
        self.sld_ciclo.pack(fill="x")

        r = form_row(b, "Após copiar as letras")
        self.sld_copiar = Slider(r, 80, 800, cfg.delay_pos_copiar_ms, suffix="ms")
        self.sld_copiar.pack(fill="x")

        r = form_row(b, "Antes de digitar a palavra")
        self.sld_antes = Slider(r, 80, 1000, cfg.delay_antes_digitar_ms, suffix="ms")
        self.sld_antes.pack(fill="x")

        r = form_row(b, "Limite estimado por rodada",
                     "Acima disso o bot corta a encenação e envia direto")
        self.sld_limite = Slider(r, 0.5, 15.0, cfg.limite_tempo_round_s, suffix="s", decimals=1)
        self.sld_limite.pack(fill="x")

        # --- Opções ---
        card, b = make_card(body, "Opções de seleção")
        card.pack(fill="x", pady=(18, 0))

        grid = tk.Frame(b, bg=T.SURFACE)
        grid.pack(fill="x")
        self.tgl_modo_teste = Toggle(grid, "Modo teste (não digita nada)", cfg.modo_teste)
        self.tgl_modo_teste.grid(row=0, column=0, sticky="w", pady=6)
        self.tgl_log = Toggle(grid, "Salvar log em arquivo", cfg.salvar_log)
        self.tgl_log.grid(row=0, column=1, sticky="w", padx=(40, 0), pady=6)
        self.tgl_penaliza = Toggle(grid, "Penalizar palavras repetidas", cfg.penaliza_repetidas)
        self.tgl_penaliza.grid(row=1, column=0, sticky="w", pady=6)
        self.tgl_bloquear_usadas = Toggle(grid, "Nunca repetir na mesma partida", cfg.bloquear_usadas_na_partida)
        self.tgl_bloquear_usadas.grid(row=1, column=1, sticky="w", padx=(40, 0), pady=6)

        r = form_row(b, "Cooldown de repetição", "Não repetir palavra usada nas últimas N rodadas")
        self.stp_cool = Stepper(r, 0, 50, cfg.cooldown_repeticao)
        self.stp_cool.pack(side="left")

        r = form_row(b, "Exibir top N opções", "Quantas alternativas mostrar no console")
        self.stp_top = Stepper(r, 0, 10, cfg.mostrar_top_n)
        self.stp_top.pack(side="left")

        r = form_row(b, "Preferir palavras com a sílaba no início",
                     "Só afeta a pontuação — não descarta as demais candidatas")
        self.tgl_prefixo = Toggle(r, "Ativar", cfg.preferir_prefixo)
        self.tgl_prefixo.pack(side="left")

        r = form_row(b, "Peso do prefixo")
        self.sld_peso_prefixo = Slider(r, 1.0, 3.0, cfg.peso_prefixo, decimals=2)
        self.sld_peso_prefixo.pack(fill="x")

        r = form_row(b, "Caçar letras novas nos modos normais",
                     "Busca a vida extra quando sobra tempo na rodada")
        self.tgl_alf_hibrido = Toggle(r, "Ativar", cfg.alfabeto_hibrido)
        self.tgl_alf_hibrido.pack(side="left")

        r = form_row(b, "Peso das letras novas")
        self.sld_peso_letras = Slider(r, 0.0, 2.0, cfg.peso_letras_novas, decimals=2)
        self.sld_peso_letras.pack(fill="x")

        # --- Sistema ---
        card, b = make_card(body, "Sistema", "Diagnóstico de tela e compatibilidade")
        card.pack(fill="x", pady=(18, 0))

        self.lbl_diag = tk.Label(b, text="Verificando resolução…", bg=T.SURFACE, fg=T.TEXT_DIM,
                                 font=T.FONT_SM, justify="left", wraplength=620, anchor="w")
        self.lbl_diag.pack(anchor="w", pady=(0, 8))

        r = form_row(b, "Ciência de DPI (reinicia o app)",
                     "Só ative se as coordenadas foram calibradas com isto ligado")
        self.tgl_dpi = Toggle(r, "Ativar", cfg.dpi_aware)
        self.tgl_dpi.pack(side="left")

        Btn(b, "Rodar diagnóstico", command=self._rodar_diagnostico, variant="ghost", icon="◍",
            padx=16, pady=7).pack(anchor="w", pady=(10, 0))

        actions = tk.Frame(body, bg=T.BG)
        actions.pack(fill="x", pady=18)
        Btn(actions, "Aplicar e salvar", command=self._salvar_config, variant="primary", icon="✔",
            padx=22, pady=10).pack(side="left")
        return page

    def _pos_row(self, parent, label, value, command):
        r = tk.Frame(parent, bg=T.SURFACE)
        r.pack(fill="x", pady=5)
        tk.Label(r, text=label, bg=T.SURFACE, fg=T.TEXT, font=T.FONT, width=30, anchor="w").pack(side="left")
        Btn(r, "Capturar", command=command, variant="ghost", icon="◎", padx=14, pady=5).pack(side="right")
        val = tk.Label(r, text=str(value), bg=T.SURFACE, fg=T.ACCENT, font=T.FONT_MONO, anchor="w")
        val.pack(side="left", padx=(0, 12))
        return val

    # ---------- Página: Humanização ----------
    def _build_page_humano(self, parent):
        h = self.cfg_mgr.config.humanizar
        page = ScrollArea(parent, bg=T.BG)
        body = page.body

        card, b = make_card(body, "Perfis prontos", "Ajusta todos os controles abaixo de uma vez")
        card.pack(fill="x")
        linha = tk.Frame(b, bg=T.SURFACE)
        linha.pack(fill="x")
        for i, (nome, dados) in enumerate(PRESETS.items()):
            col = tk.Frame(linha, bg=T.SURFACE)
            col.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
            linha.columnconfigure(i, weight=1)
            Btn(col, nome, command=lambda n=nome: self._aplicar_preset(n),
                variant="ghost", padx=16, pady=8).pack(fill="x")
            tk.Label(col, text=dados["descricao"], bg=T.SURFACE, fg=T.TEXT_MUTE, font=T.FONT_SM,
                     wraplength=200, justify="left").pack(anchor="w", pady=(6, 0))

        card, b = make_card(body, "Perfil de digitação", "Como o bot distribui o tempo entre as teclas")
        card.pack(fill="x", pady=(18, 0))

        r = form_row(b, "Perfil de velocidade")
        self.seg_perfil = Segmented(r, [
            ("Rápida", VelocidadePerfil.RAPIDA.value),
            ("Aleatória", VelocidadePerfil.ALEATORIA.value),
            ("Gradual", VelocidadePerfil.GRADUAL.value),
            ("Nenhum", VelocidadePerfil.NENHUM.value),
        ], value=h.perfil)
        self.seg_perfil.pack(side="left")

        r = form_row(b, "Delay entre letras")
        self.sld_delay_letra = Slider(r, 1, 120, h.delay_entre_letras_ms, suffix="ms")
        self.sld_delay_letra.pack(fill="x")

        r = form_row(b, "Erro de digitação por caractere", "Erra e corrige com backspace")
        self.sld_chance_erro = Slider(r, 0, 25, h.chance_erro * 100, suffix="%")
        self.sld_chance_erro.pack(fill="x")

        r = form_row(b, "Variação máxima do delay")
        self.sld_var_delay = Slider(r, 0, 50, h.variacao_delay * 1000, suffix="ms")
        self.sld_var_delay.pack(fill="x")

        r = form_row(b, "Respirar a cada N letras")
        self.stp_pausa_cada = Stepper(r, 2, 8, h.pausa_cada)
        self.stp_pausa_cada.pack(side="left")

        r = form_row(b, "Pausa mínima")
        self.sld_pausa_min = Slider(r, 0.0, 0.30, h.pausa_min, suffix="s", decimals=3)
        self.sld_pausa_min.pack(fill="x")

        r = form_row(b, "Pausa máxima")
        self.sld_pausa_max = Slider(r, 0.0, 0.60, h.pausa_max, suffix="s", decimals=3)
        self.sld_pausa_max.pack(fill="x")

        # --- Comportamentos ---
        card, b = make_card(body, "Comportamentos humanizados",
                            "Cada rodada sorteia estes gatilhos de forma independente")
        card.pack(fill="x", pady=(18, 0))

        r = form_row(b, "Falha proposital", "Envia uma palavra errada de vez em quando")
        self.sld_chance_falha = Slider(r, 0, 50, h.chance_falha_proposital * 100, suffix="%")
        self.sld_chance_falha.pack(fill="x")

        r = form_row(b, "Errar, dar ENTER e corrigir")
        self.sld_chance_errEnter = Slider(r, 0, 60, h.chance_erro_enter * 100, suffix="%")
        self.sld_chance_errEnter.pack(fill="x")

        r = form_row(b, "Frase engraçada antes", "Digita e apaga uma frase da lista abaixo")
        self.sld_chance_frase = Slider(r, 0, 100, h.chance_frase_engracada * 100, suffix="%")
        self.sld_chance_frase.pack(fill="x")

        r = form_row(b, "Ensaio da palavra", "Digita um rascunho e apaga antes da resposta")
        self.sld_chance_ensaio = Slider(r, 0, 100, h.chance_ensaio_palavra * 100, suffix="%")
        self.sld_chance_ensaio.pack(fill="x")

        # --- Extras ---
        card, b = make_card(body, "Extras")
        card.pack(fill="x", pady=(18, 0))

        r = form_row(b, "Pensar após 3 letras", "Quando a palavra começa com as letras do desafio")
        self.tgl_pensar3 = Toggle(r, "Ativar", h.pensar_3letras)
        self.tgl_pensar3.pack(side="left")

        r = form_row(b, "Duração da pausa de «pensar»")
        self.sld_pensar_ms = Slider(r, 100, 2000, h.pensar_3letras_pausa_ms, suffix="ms")
        self.sld_pensar_ms.pack(fill="x")

        r = form_row(b, "Inserir números aleatórios")
        self.tgl_inserir_num = Toggle(r, "Ativar", h.inserir_numeros)
        self.tgl_inserir_num.pack(side="left")

        r = form_row(b, "Rodadas com números")
        self.stp_nums_rounds = Stepper(r, 0, 50, h.numeros_rodadas)
        self.stp_nums_rounds.pack(side="left")

        # --- Frases ---
        card, b = make_card(body, "Frases engraçadas", "Uma por linha. Vazio usa a lista padrão do app.")
        card.pack(fill="x", pady=(18, 0))
        fwrap = tk.Frame(b, bg=T.SURFACE_2, highlightthickness=1, highlightbackground=T.BORDER)
        fwrap.pack(fill="x")
        self.txt_frases = tk.Text(fwrap, height=7, bg=T.SURFACE_2, fg=T.TEXT, font=T.FONT_MONO,
                                  relief="flat", wrap="word", padx=12, pady=10,
                                  insertbackground=T.ACCENT, selectbackground=T.HOVER)
        self.txt_frases.pack(fill="x")
        if h.frases_customizadas:
            self.txt_frases.insert(tk.END, "\n".join(h.frases_customizadas))

        actions = tk.Frame(body, bg=T.BG)
        actions.pack(fill="x", pady=18)
        Btn(actions, "Aplicar e salvar", command=self._salvar_config, variant="primary", icon="✔",
            padx=22, pady=10).pack(side="left")
        return page

    # ---------- Página: Estatísticas ----------
    def _build_page_stats(self, parent):
        page = tk.Frame(parent, bg=T.BG)

        cards = tk.Frame(page, bg=T.BG)
        cards.pack(fill="x")
        self.st_dict = StatCard(cards, "palavras no dicionário", "0", T.PURPLE)
        self.st_enviadas = StatCard(cards, "palavras enviadas", "0", T.ACCENT)
        self.st_alfabeto = StatCard(cards, "alfabetos completos", "0", T.SUCCESS)
        self.st_erros = StatCard(cards, "erros propositais", "0", T.WARN)
        for i, c in enumerate((self.st_dict, self.st_enviadas, self.st_alfabeto, self.st_erros)):
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 12, 0))
            cards.columnconfigure(i, weight=1)

        cards2 = tk.Frame(page, bg=T.BG)
        cards2.pack(fill="x", pady=(14, 0))
        self.st_taxa = StatCard(cards2, "taxa de aceitação", "—", T.ACCENT)
        self.st_recusadas = StatCard(cards2, "recusadas pelo jogo", "0", T.DANGER)
        self.st_aprendidas = StatCard(cards2, "aprendidas (fora do jogo)", "0", T.WARN)
        self.st_seq = StatCard(cards2, "acertos consecutivos", "0", T.SUCCESS)
        self.st_nums = StatCard(cards2, "rodadas c/ números", "0", T.PURPLE)
        for i, c in enumerate((self.st_taxa, self.st_recusadas, self.st_aprendidas,
                               self.st_seq, self.st_nums)):
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 12, 0))
            cards2.columnconfigure(i, weight=1)

        card, b = make_card(page, "Histórico da sessão", "Palavras enviadas e quantas vezes cada uma foi usada")
        card.pack(fill="both", expand=True, pady=(18, 0))

        tools = tk.Frame(b, bg=T.SURFACE)
        tools.pack(fill="x", pady=(0, 10))
        Btn(tools, "Atualizar", command=self._refresh_historico, variant="ghost", icon="⟳",
            padx=14, pady=6).pack(side="left")
        Btn(tools, "Exportar .txt", command=self._exportar_historico, variant="ghost", icon="⇩",
            padx=14, pady=6).pack(side="left", padx=8)

        wrap = tk.Frame(b, bg=T.SURFACE_2, highlightthickness=1, highlightbackground=T.BORDER)
        wrap.pack(fill="both", expand=True)
        self.txt_hist = tk.Text(wrap, bg=T.SURFACE_2, fg=T.TEXT_DIM, font=T.FONT_MONO, relief="flat",
                                padx=14, pady=10, state=tk.DISABLED, wrap="none")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.txt_hist.yview, style="Dark.Vertical.TScrollbar")
        self.txt_hist.configure(yscrollcommand=sb.set)
        self.txt_hist.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return page

    # ---------- Console / logs ----------
    def enqueue_log(self, text: str):
        """Chamado por qualquer thread; a UI consome via _drain_logs."""
        self._log_queue.put(text)

    # mantido por compatibilidade com chamadas diretas
    append_terminal = enqueue_log

    def _drain_logs(self):
        try:
            while True:
                self._write_log(self._log_queue.get_nowait())
        except queue.Empty:
            pass
        self.root.after(90, self._drain_logs)

    @staticmethod
    def _level_of(msg: str) -> str:
        m = msg.lower()
        if any(k in m for k in ("erro", "falha", "não encontrad", "nao encontrad", "cancelad")):
            return "err" if "falha ao" in m or "não encontrad" in m or "nao encontrad" in m else "warn"
        if any(k in m for k in ("escolhida", "carregad", "salv", "concluíd", "concluid")):
            return "ok"
        if any(k in m for k in ("fast path", "kill switch", "parad", "desativad")):
            return "warn"
        if any(k in m for k in ("letras detectadas", "iniciando", "modo selecionado")):
            return "accent"
        return "info"

    def _write_log(self, text: str):
        self.terminal.configure(state=tk.NORMAL)
        self.terminal.insert(tk.END, datetime.datetime.now().strftime("%H:%M:%S  "), "time")
        self.terminal.insert(tk.END, f"{text}\n", self._level_of(text))
        # limita o buffer para não crescer sem fim
        if int(self.terminal.index("end-1c").split(".")[0]) > 1500:
            self.terminal.delete("1.0", "400.0")
        self.terminal.configure(state=tk.DISABLED)
        if self.tgl_autoscroll.get():
            self.terminal.see(tk.END)

        self._update_live(text)
        self.lbl_status_msg.configure(text=text[:120])

    def _update_live(self, text: str):
        if text.startswith("Letras detectadas:"):
            self.live_letras.configure(text=text.split(":", 1)[1].strip().upper())
            self.live_evento.configure(text="analisando dicionário…")
        elif text.startswith("Escolhida:"):
            self.live_palavra.configure(text=text.split(":", 1)[1].strip())
            self.live_evento.configure(text="digitando…")
        elif text.startswith("Estimativa do round"):
            self.live_evento.configure(text=text.split("|")[0].replace("Estimativa do round:", "estimativa:").strip())
        elif "FAST PATH" in text:
            self.live_evento.configure(text="fast path — enviando direto")
        elif "Nenhuma palavra encontrada" in text:
            self.live_palavra.configure(text="—")
            self.live_evento.configure(text="sem candidatos no dicionário")

    def _limpar_terminal(self):
        self.terminal.configure(state=tk.NORMAL)
        self.terminal.delete("1.0", tk.END)
        self.terminal.configure(state=tk.DISABLED)

    def _copiar_terminal(self):
        try:
            pyperclip.copy(self.terminal.get("1.0", tk.END))
            self.enqueue_log("Console copiado para a área de transferência.")
        except Exception as e:
            self.enqueue_log(f"Falha ao copiar console: {e}")

    # ---------- Estatísticas ----------
    def _refresh_stats(self):
        bot = self.bot
        total_dict = len(bot.dict.palavras)
        enviadas = len(bot.historico)
        usadas = bot.selector.letras_usadas

        self.st_dict.set(total_dict)
        self.st_enviadas.set(enviadas)
        self.st_alfabeto.set(bot.selector.alfabeto_completado)
        self.st_erros.set(bot.erros_propositais)
        self.st_seq.set(bot.acertos_consecutivos)
        self.st_nums.set(bot.numeros_restantes)
        self.st_recusadas.set(bot.recusadas)
        self.st_aprendidas.set(len(bot.dict.rejeitadas))
        self.st_taxa.set(f"{bot.taxa_aceitacao:.0f}%" if (bot.aceitas + bot.recusadas) else "—")

        self.card_palavras.set(enviadas)
        self.card_sequencia.set(bot.acertos_consecutivos)
        self.card_dict.set(total_dict)

        self.grid_alfabeto.atualizar(usadas)
        self.lbl_alfabeto.configure(text=f"{len(usadas)} / {len(LETRAS_ALFABETO)}")

        resumo = f"modo: {bot.modo_atual}   ·   dicionário: {total_dict}   ·   enviadas: {enviadas}"
        if bot.aceitas + bot.recusadas:
            resumo += f"   ·   aceitação: {bot.taxa_aceitacao:.0f}%"
        self.lbl_status_right.configure(text=resumo)
        self.root.after(700, self._refresh_stats)

    # ---------- Perfis / partida / diagnóstico ----------
    def _aplicar_preset(self, nome):
        p = PRESETS[nome]
        self.seg_perfil.set(p["perfil"])
        self.sld_delay_letra.set(p["delay_letra"])
        self.sld_chance_erro.set(p["chance_erro"])
        self.sld_var_delay.set(p["var_delay"])
        self.stp_pausa_cada.set(p["pausa_cada"])
        self.sld_pausa_min.set(p["pausa_min"])
        self.sld_pausa_max.set(p["pausa_max"])
        self.sld_chance_falha.set(p["falha"])
        self.sld_chance_errEnter.set(p["err_enter"])
        self.sld_chance_frase.set(p["frase"])
        self.sld_chance_ensaio.set(p["ensaio"])
        self.tgl_pensar3.set(p["pensar3"])
        self.sld_pensar_ms.set(p["pensar_ms"])
        self.sld_limite.set(p["limite"])
        self.enqueue_log(f"Perfil '{nome}' aplicado. Clique em Aplicar e salvar para gravar.")

    def _nova_partida(self):
        self.bot.nova_partida("botão")

    def _rodar_diagnostico(self):
        diag = Capturador.diagnostico_escala()
        if not diag:
            self.lbl_diag.configure(text="Não foi possível ler a resolução da tela.", fg=T.WARN)
            return
        if diag["ok"]:
            txt = (f"Tela: {diag['logica'][0]}x{diag['logica'][1]} lógica = física. "
                   f"Sem problema de escala.")
            cor = T.SUCCESS
        else:
            txt = (f"Atenção: a tela reporta {diag['logica'][0]}x{diag['logica'][1]} mas a captura "
                   f"devolve {diag['fisica'][0]}x{diag['fisica'][1]} (fator {diag['fator']:.2f}). "
                   f"A escala do Windows não é 100%: os cliques e a leitura da tela vão cair no lugar "
                   f"errado. Use 100% de escala ou ative a ciência de DPI e recalibre TODAS as posições.")
            cor = T.DANGER
        if self.pos_mgr.resolucao and tuple(self.pos_mgr.resolucao) != tuple(diag["logica"]):
            txt += (f"  As posições foram calibradas em "
                    f"{self.pos_mgr.resolucao[0]}x{self.pos_mgr.resolucao[1]} — recalibre.")
            cor = T.WARN
        self.lbl_diag.configure(text=txt, fg=cor)
        self.enqueue_log(txt)

    def _refresh_historico(self):
        self.txt_hist.configure(state=tk.NORMAL)
        self.txt_hist.delete("1.0", tk.END)
        if not self.bot.historico:
            self.txt_hist.insert(tk.END, "Nenhuma palavra enviada nesta sessão ainda.")
        else:
            for i, w in enumerate(reversed(self.bot.historico), 1):
                c = self.bot.selector.frequencia.get(w, 0)
                self.txt_hist.insert(tk.END, f"{i:>4}.  {w:<28} usada {c}x\n")
        self.txt_hist.configure(state=tk.DISABLED)

    def _exportar_historico(self):
        if not self.bot.historico:
            self.enqueue_log("Nada para exportar: histórico vazio.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt",
                                            initialfile="historico.txt",
                                            filetypes=[("Texto", "*.txt")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                for w in self.bot.historico:
                    f.write(f"{w}\t{self.bot.selector.frequencia.get(w, 0)}\n")
            self.enqueue_log(f"Histórico exportado para {path}")
        except Exception as e:
            self.enqueue_log(f"Falha ao exportar histórico: {e}")

    # ---------- Eventos principais ----------
    def _on_modo(self, modo):
        self.cfg_mgr.config.modo = modo
        self.bot.set_modo(modo)

    def _iniciar(self):
        self._capturar_config_da_ui()
        cfg = self.cfg_mgr.config
        if not os.path.exists(cfg.caminho_dicionario):
            messagebox.showerror("Dicionário não encontrado",
                                 f"Não encontrei o arquivo:\n{cfg.caminho_dicionario}")
            self.enqueue_log(f"Dicionário não encontrado: {cfg.caminho_dicionario}")
            return
        self.bot.numeros_restantes = cfg.humanizar.numeros_rodadas if cfg.humanizar.inserir_numeros else 0
        self._paint_pill(True)
        self.btn_iniciar.set_enabled(False)
        self.btn_parar.set_enabled(True)
        self.live_evento.configure(text="procurando a chatbox…")
        self.bot.iniciar()

    def _parar(self):
        self.bot.parar()
        self._paint_pill(False)
        self.btn_iniciar.set_enabled(True)
        self.btn_parar.set_enabled(False)
        self.live_evento.configure(text="parado")

    def _handle_kill_switch(self):
        if self.bot.executando:
            self.enqueue_log("F8 pressionado — kill switch acionado.")
        self._parar()

    def _monitor_f8(self):
        """Atalhos globais: F8 para tudo, F7 troca de modo, F6 zera a partida."""
        acoes = {
            'f8': self._handle_kill_switch,
            'f7': self._ciclar_modo,
            'f6': self._nova_partida,
        }
        while True:
            try:
                for tecla, acao in acoes.items():
                    if keyboard.is_pressed(tecla):
                        self.root.after(0, acao)
                        while keyboard.is_pressed(tecla):
                            time.sleep(0.05)
            except Exception:
                time.sleep(0.5)
            time.sleep(0.1)

    def _ciclar_modo(self):
        modos = [m.value for m in Modo]
        atual = self.modo_sel.get()
        proximo = modos[(modos.index(atual) + 1) % len(modos)] if atual in modos else modos[0]
        self.modo_sel.set(proximo, notify=True)

    def _toggle_topmost(self, value):
        self.root.attributes("-topmost", bool(value))

    def _on_close(self):
        try:
            self.bot.parar()
        finally:
            self.root.destroy()

    # ---------- Arquivos ----------
    def _browse_dict(self):
        path = filedialog.askopenfilename(title="Selecionar dicionário (txt)",
                                          filetypes=[("Textos", "*.txt"), ("Todos", "*.*")])
        if path:
            self.ent_dict.delete(0, tk.END)
            self.ent_dict.insert(0, path)

    def _browse_tpl(self):
        path = filedialog.askopenfilename(title="Selecionar template da chatbox (png)",
                                          filetypes=[("Imagens", "*.png"), ("Todos", "*.*")])
        if path:
            self.ent_tpl.delete(0, tk.END)
            self.ent_tpl.insert(0, path)

    # ---------- Captura de posições ----------
    def _capturar_pos_letras(self):
        self._start_capture("Clique onde as LETRAS aparecem no jogo",
                            lambda x, y: self._set_pos('letras', x, y))

    def _capturar_pos_chat(self):
        self._start_capture("Clique no CAMPO DE DIGITAÇÃO do jogo",
                            lambda x, y: self._set_pos('chat', x, y))

    def _capturar_turn_bar(self):
        self._start_capture("Clique no canto SUPERIOR ESQUERDO e depois no INFERIOR DIREITO da barra de turno",
                            self._set_turn_bar, pontos=2)

    def _capturar_letras_rect(self):
        self._start_capture("Região da SÍLABA para OCR: clique no canto superior esquerdo e depois no inferior direito",
                            self._set_letras_rect, pontos=2)

    def _start_capture(self, instrucao, callback, pontos=1):
        self._stop_capture()
        self._show_capture_hint(instrucao)
        coletados = []

        def on_click(x, y, button, pressed):
            if not pressed:
                return
            coletados.append((int(x), int(y)))
            self.enqueue_log(f"Ponto {len(coletados)} registrado: ({int(x)}, {int(y)})")
            if len(coletados) >= pontos:
                args = tuple(coletados) if pontos > 1 else coletados[0]
                self.root.after(0, lambda: (self._stop_capture(), callback(*args)))
                return False

        self._capture_listener = mouse.Listener(on_click=on_click)
        self._capture_listener.start()

    def _show_capture_hint(self, texto):
        hint = Toplevel(self.root)
        hint.overrideredirect(True)
        hint.attributes("-topmost", True)
        hint.configure(bg=T.ACCENT)
        frame = tk.Frame(hint, bg=T.SURFACE, padx=22, pady=14)
        frame.pack(padx=2, pady=2)
        tk.Label(frame, text="MODO CAPTURA", bg=T.SURFACE, fg=T.ACCENT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(frame, text=texto, bg=T.SURFACE, fg=T.TEXT, font=T.FONT_H2).pack(anchor="w", pady=(3, 8))
        Btn(frame, "Cancelar", command=self._stop_capture, variant="ghost", padx=12, pady=4).pack(anchor="w")
        hint.update_idletasks()
        w, h = hint.winfo_width(), hint.winfo_height()
        x = int((self.root.winfo_screenwidth() - w) / 2)
        hint.geometry(f"+{x}+40")
        self._capture_hint = hint

    def _stop_capture(self):
        if self._capture_listener is not None:
            try:
                self._capture_listener.stop()
            except Exception:
                pass
            self._capture_listener = None
        if self._capture_hint is not None:
            try:
                self._capture_hint.destroy()
            except Exception:
                pass
            self._capture_hint = None

    def _set_pos(self, which, x, y):
        self._registrar_resolucao()
        if which == 'letras':
            self.pos_mgr.pos_letras = (x, y)
            self.lbl_pos_letras.configure(text=str(self.pos_mgr.pos_letras))
            self.enqueue_log(f"Posição das letras definida: {self.pos_mgr.pos_letras}")
        else:
            self.pos_mgr.pos_chatbox = (x, y)
            self.lbl_pos_chat.configure(text=str(self.pos_mgr.pos_chatbox))
            self.enqueue_log(f"Posição da chatbox definida: {self.pos_mgr.pos_chatbox}")

    @staticmethod
    def _para_rect(p1, p2):
        x1, y1 = p1
        x2, y2 = p2
        return (int(min(x1, x2)), int(min(y1, y2)),
                int(abs(x2 - x1)) or 1, int(abs(y2 - y1)) or 1)

    def _set_turn_bar(self, p1, p2):
        rect = self._para_rect(p1, p2)
        self.pos_mgr.turn_bar_rect = rect
        self._registrar_resolucao()
        self.lbl_turn_rect.configure(text=str(rect))
        self.enqueue_log(f"Barra de turno definida: {rect}")
        self.bot.capt.turn_bar_reference = None
        self.bot.capt._warned_turn_rect = False

    def _set_letras_rect(self, p1, p2):
        rect = self._para_rect(p1, p2)
        self.pos_mgr.letras_rect = rect
        self._registrar_resolucao()
        self.lbl_letras_rect.configure(text=str(rect))
        self.enqueue_log(f"Região da sílaba (OCR) definida: {rect}")
        self.bot.capt._warned_ocr = False

    def _registrar_resolucao(self):
        """Guarda em que resolução as posições foram calibradas."""
        try:
            self.pos_mgr.resolucao = tuple(pyautogui.size())
        except Exception:
            pass

    # ---------- Config ----------
    def _capturar_config_da_ui(self):
        cfg = self.cfg_mgr.config
        cfg.caminho_dicionario = self.ent_dict.get().strip()
        cfg.template_chatbox = self.ent_tpl.get().strip()
        cfg.template_threshold = round(self.sld_thr.get(), 2)
        cfg.turn_bar_threshold = round(self.sld_turn_thr.get(), 2)

        cfg.delay_ciclo_ms = int(self.sld_ciclo.get())
        cfg.delay_pos_copiar_ms = int(self.sld_copiar.get())
        cfg.delay_antes_digitar_ms = int(self.sld_antes.get())
        cfg.limite_tempo_round_s = round(self.sld_limite.get(), 2)

        cfg.modo = self.modo_sel.get()
        cfg.modo_teste = self.tgl_modo_teste.get()
        cfg.salvar_log = self.tgl_log.get()
        cfg.penaliza_repetidas = self.tgl_penaliza.get()
        cfg.cooldown_repeticao = self.stp_cool.get()
        cfg.mostrar_top_n = self.stp_top.get()

        # captura da sílaba
        cfg.metodo_captura = self.seg_captura.get()
        cfg.preservar_clipboard = self.tgl_clip.get()
        cfg.clique_captura = self.seg_clique.get()
        cfg.tentativas_captura = self.stp_tent_captura.get()
        cfg.turn_bar_metodo = self.seg_turno.get()

        # verificação / aprendizado
        cfg.verificar_envio = self.tgl_verificar.get()
        cfg.delay_verificacao_ms = int(self.sld_verif_ms.get())
        cfg.max_tentativas_rodada = self.stp_tentativas.get()
        cfg.aprender_rejeitadas = self.tgl_aprender.get()
        cfg.auto_nova_partida = self.tgl_auto_partida.get()
        cfg.inatividade_nova_partida_s = round(self.sld_inatividade.get(), 1)

        # seleção
        cfg.bloquear_usadas_na_partida = self.tgl_bloquear_usadas.get()
        cfg.preferir_prefixo = self.tgl_prefixo.get()
        cfg.peso_prefixo = round(self.sld_peso_prefixo.get(), 2)
        cfg.alfabeto_hibrido = self.tgl_alf_hibrido.get()
        cfg.peso_letras_novas = round(self.sld_peso_letras.get(), 2)

        # sistema
        cfg.dpi_aware = self.tgl_dpi.get()

        h = cfg.humanizar
        h.perfil = self.seg_perfil.get()
        h.delay_entre_letras_ms = int(self.sld_delay_letra.get())
        h.chance_erro = self.sld_chance_erro.get() / 100.0
        h.variacao_delay = self.sld_var_delay.get() / 1000.0
        h.pausa_cada = self.stp_pausa_cada.get()
        h.pausa_min = round(self.sld_pausa_min.get(), 3)
        h.pausa_max = round(self.sld_pausa_max.get(), 3)
        if h.pausa_min > h.pausa_max:
            h.pausa_min, h.pausa_max = h.pausa_max, h.pausa_min

        h.inserir_numeros = self.tgl_inserir_num.get()
        h.numeros_rodadas = self.stp_nums_rounds.get()

        h.chance_falha_proposital = self.sld_chance_falha.get() / 100.0
        h.chance_erro_enter = self.sld_chance_errEnter.get() / 100.0
        h.chance_frase_engracada = self.sld_chance_frase.get() / 100.0
        h.chance_ensaio_palavra = self.sld_chance_ensaio.get() / 100.0

        h.pensar_3letras = self.tgl_pensar3.get()
        h.pensar_3letras_pausa_ms = int(self.sld_pensar_ms.get())

        txt = self.txt_frases.get("1.0", tk.END).strip()
        h.frases_customizadas = [ln.strip() for ln in txt.splitlines() if ln.strip()]

    def _salvar_config(self):
        self._capturar_config_da_ui()
        self.cfg_mgr.save()
        self.bot.cfg = self.cfg_mgr.config
        self.bot.capt.cfg = self.cfg_mgr.config
        self.bot.typer.cfg = self.cfg_mgr.config
        self.bot.selector.cfg = self.cfg_mgr.config
        self.enqueue_log("Configurações salvas.")

    def _salvar_posicoes(self):
        self.pos_mgr.save()
        self.enqueue_log("Posições salvas.")

    def _recarregar_dicionario(self):
        self._capturar_config_da_ui()
        if not self.bot.carregar_dict_e_blacklist():
            messagebox.showerror("Erro", f"Falha ao carregar dicionário:\n{self.cfg_mgr.config.caminho_dicionario}")
            return
        self.enqueue_log("Dicionário recarregado.")


# ==============================
# Main
# ==============================

if __name__ == "__main__":
    try:
        AppUI()
    except KeyboardInterrupt:
        pass
