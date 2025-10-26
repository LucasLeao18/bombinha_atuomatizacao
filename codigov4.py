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
from dataclasses import dataclass, asdict, field
from collections import deque

# UI
import tkinter as tk
from tkinter import ttk, Toplevel, Menu, scrolledtext, filedialog, messagebox
from pynput import mouse


# ==============================
# Constantes / Enums / Util
# ==============================

APP_NAME = "JKLM.fun – Automação PT-BR"
CONFIG_FILE = "config.json"
POSICOES_FILE = "posicoes.json"
BLACKLIST_FILE = "blacklist.txt"
LOG_FILE = "log.txt"

IGNORADAS_ALFABETO = set("ykw")  # Ignorar Y,K,W para completar 23 letras
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

class VelocidadePerfil(Enum):
    NENHUM = 'nenhum'
    RAPIDA = 'rapida'
    ALEATORIA = 'aleatoria'
    GRADUAL = 'gradual'


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


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

    # Anti-repetição e seleção
    penaliza_repetidas: bool = True
    penalizacao_repetida: float = 0.85     # fator multiplicativo para pontuação
    cooldown_repeticao: int = 5            # não repetir a mesma palavra nas últimas N

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

        # Reconstrução segura para evitar múltiplos 'humanizar'
        base = asdict(self.config)
        base.update({k: v for k, v in data.items() if k != "humanizar"})
        human_data = data.get("humanizar", {})
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

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.pos_letras = tuple(data.get("letras", self.pos_letras))
            self.pos_chatbox = tuple(data.get("chatbox", self.pos_chatbox))
            self.turn_bar_rect = tuple(data.get("turn_bar", self.turn_bar_rect))

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({
                "letras": self.pos_letras,
                "chatbox": self.pos_chatbox,
                "turn_bar": self.turn_bar_rect
            }, f, ensure_ascii=False, indent=2)


# ==============================
# Núcleo: Dicionário / Seleção
# ==============================

class Dicionario:
    def __init__(self):
        self.palavras = []
        self.blacklist = set()

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
        self.blacklist = set()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    w = line.strip().lower()
                    if w:
                        self.blacklist.add(w)

    def filtrar(self, frag):
        frag = frag.lower()
        return [w for w in self.palavras if frag in w and w not in self.blacklist]


class Selecionador:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.recentes = deque(maxlen=cfg.cooldown_repeticao)
        self.frequencia = {}  # contagem de uso por palavra
        self.letras_usadas = set()
        self.alfabeto_completado = 0

    def _score_base(self, palavra, criterio, frag):
        if criterio == Modo.CURTA.value:
            base = 1.0 / (len(palavra) + 1e-3)
        elif criterio == Modo.LONGA.value:
            base = float(len(palavra))
        else:
            base = 1.0

        if palavra.startswith(frag):
            base *= 1.25

        if self.cfg.penaliza_repetidas:
            freq = self.frequencia.get(palavra, 0)
            if freq > 0:
                base *= (self.cfg.penalizacao_repetida ** freq)
            if palavra in self.recentes:
                base *= 0.5

        return base

    def _score_alfabeto(self, palavra):
        letras = set([c for c in palavra if c.isalpha()]) - IGNORADAS_ALFABETO
        novas = len([c for c in letras if c not in self.letras_usadas])
        return novas + (len(palavra) * 0.05)

    def escolher(self, candidatos, modo: str, frag: str):
        if not candidatos:
            return None
        frag = frag.lower()
        scored = []
        if modo == Modo.ALFABETO.value:
            for w in candidatos:
                scored.append((w, self._score_alfabeto(w)))
        else:
            for w in candidatos:
                scored.append((w, self._score_base(w, modo, frag)))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_n = max(1, min(self.cfg.mostrar_top_n if self.cfg.mostrar_top_n > 0 else 1, len(scored)))
        top = scored[:top_n]
        pesos = np.array([max(1e-3, s) for _, s in top], dtype=float)
        pesos = pesos / pesos.sum()
        escolha = random.choices([w for w, _ in top], weights=pesos, k=1)[0]
        return escolha

    def registrar_uso(self, palavra, modo: str):
        self.frequencia[palavra] = self.frequencia.get(palavra, 0) + 1
        self.recentes.append(palavra)
        if modo == Modo.ALFABETO.value:
            letras = set([c for c in palavra if c.isalpha()]) - IGNORADAS_ALFABETO
            self.letras_usadas.update(letras)
            if len(self.letras_usadas) >= 23:
                self.alfabeto_completado += 1
                self.letras_usadas.clear()


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
        return cv2.cvtColor(np.array(shot), cv2.COLOR_BGR2GRAY)

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
        if atual.shape != ref.shape:
            atual = cv2.resize(atual, (ref.shape[1], ref.shape[0]))
        diff = cv2.absdiff(ref, atual)
        score = 1.0 - (diff.mean() / 255.0)
        return max(0.0, min(1.0, score))

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

    def capturar_letras(self):
        x, y = self.pos.pos_letras
        pyautogui.doubleClick(x=x, y=y)
        time.sleep(self.cfg.delay_pos_copiar_ms / 1000.0)
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(self.cfg.delay_pos_copiar_ms / 1000.0)

        bruto = pyperclip.paste()
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
        self._focus_chat(pos_chatbox)
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.03)
        pyautogui.press('backspace')
        time.sleep(0.02)
        return True

    def digitar_pensando_3(self, palavra: str, pos_chatbox, think_ms=500, override_nums=False):
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
        if self.cfg.modo_teste:
            self.log(f"[TESTE] -> {palavra}")
            return True
        return self._digitar_texto(palavra, pos_chatbox, enviar=True, override_nums=override_nums)

    def digitar_quick(self, palavra: str, pos_chatbox):
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
        self._log(f"Dicionário carregado ({len(self.dict.palavras)} palavras). Blacklist: {len(self.dict.blacklist)}")
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

            if self.capt.detectar_chatbox(refresh_reference=True):
                frag = self.capt.capturar_letras()
                if frag:
                    self._log(f"Letras detectadas: {frag}")
                    candidatos = self.dict.filtrar(frag)
                    if not candidatos:
                        # Regra: quando não achar no dicionário, fala a frase definida
                        self._log("Nenhuma palavra encontrada – enviando frase padrão.")
                        ok_send = self.typer.digitar_quick(FRASE_QUANDO_NAO_TEM, self.pos.pos_chatbox)
                        if not ok_send:
                            self._log("Envio da frase padrão cancelado (não era mais a sua vez).")
                    else:
                        # preferir palavras que comecem com as 3 primeiras letras do frag
                        use_pensar3 = False
                        if len(frag) >= 3 and self.cfg.humanizar.pensar_3letras:
                            prefix = frag[:3]
                            candidatos_prefix = [w for w in candidatos if w.startswith(prefix)]
                            if candidatos_prefix:
                                candidatos = candidatos_prefix
                                use_pensar3 = True

                        escolha = self.selector.escolher(candidatos, self.modo_atual, frag)
                        if not escolha:
                            time.sleep(self.cfg.delay_ciclo_ms / 1000.0)
                            continue

                        if self.cfg.mostrar_top_n > 0:
                            top_preview = ", ".join(candidatos[:min(self.cfg.mostrar_top_n, len(candidatos))])
                            self._log(f"Top opções: {top_preview}")
                        self._log(f"Escolhida: {escolha}")

                        # triggers da rodada
                        trig_frase, trig_ensaio, trig_falha, trig_erro_enter = self._select_triggers()

                        # Números: válidos nesta rodada?
                        use_nums_this_round = self.cfg.humanizar.inserir_numeros and (self.numeros_restantes > 0)

                        # estimativa de tempo (inclui TUDO da humanização)
                        est, breakdown = self.typer.estimate_round_time(
                            escolha,
                            use_frase=trig_frase,
                            use_ensaio=trig_ensaio,
                            use_falha=trig_falha,
                            use_erro_enter=trig_erro_enter,
                            use_pensar3=use_pensar3,
                            include_nums=use_nums_this_round
                        )
                        flags_txt = []
                        if trig_frase: flags_txt.append("frase")
                        if trig_ensaio: flags_txt.append("ensaio")
                        if trig_falha: flags_txt.append("falha")
                        if trig_erro_enter: flags_txt.append("errEnter")
                        if use_pensar3: flags_txt.append("pensar3")
                        flags_str = ", ".join(flags_txt) if flags_txt else "nenhum"

                        bd_txt = " | ".join([f"{k}={v:.2f}s" for k, v in breakdown.items() if v > 0.0]) or "typing=0.00s"
                        self._log(f"Estimativa do round: ~{est:.2f}s | flags: {flags_str} | breakdown: {bd_txt}")

                        fast_path = est > self.cfg.limite_tempo_round_s
                        if fast_path:
                            self._log(f"FAST PATH: {est:.2f}s > limite {self.cfg.limite_tempo_round_s:.2f}s → enviar direto a correta.")
                            trig_frase = trig_ensaio = trig_falha = trig_erro_enter = False
                            use_nums_this_round = False  # sem números para acelerar
                            use_pensar3 = False

                        # executa
                        try:
                            if trig_falha:
                                enviada = self.typer.falha_proposital(escolha, self.pos.pos_chatbox)
                                if enviada is None:
                                    self._log("Falha proposital cancelada (não era a sua vez no ENTER).")
                                else:
                                    self._log(f"Falha proposital enviada: {enviada}")
                                    self.erros_propositais += 1
                                    self.acertos_consecutivos = 0

                            elif trig_erro_enter:
                                self._log("Enviando UMA letra errada + ENTER; depois corrigindo.")
                                ok = self.typer.erro_enter_e_corrige(escolha, self.pos.pos_chatbox)
                                if ok:
                                    self.selector.registrar_uso(escolha, self.modo_atual)
                                    self.historico.append(escolha)
                                    self.acertos_consecutivos += 1
                                    if use_nums_this_round:
                                        self.numeros_restantes = max(0, self.numeros_restantes - 1)
                                        if self.numeros_restantes == 0:
                                            self.cfg.humanizar.inserir_numeros = False
                                            self._log("Rodadas com números concluídas. Inserção de números desativada.")
                                else:
                                    self._log("Fluxo errEnter cancelado (não era sua vez em algum ENTER).")

                            else:
                                if trig_frase:
                                    self._log("Frase engraçada & apagar (simulação).")
                                    self.typer.frase_engracada_e_apaga(self.pos.pos_chatbox)

                                if trig_ensaio:
                                    self._log("Ensaio/rascunho & apagar (simulação).")
                                    self.typer.ensaiar_palavra_e_apagar(escolha, self.pos.pos_chatbox)

                                if fast_path:
                                    ok_send = self.typer.digitar_quick(escolha, self.pos.pos_chatbox)
                                else:
                                    if use_pensar3 and len(escolha) >= 3:
                                        self._log(f"Pensar após 3 letras: pausa {self.cfg.humanizar.pensar_3letras_pausa_ms} ms.")
                                        ok_send = self.typer.digitar_pensando_3(
                                            escolha,
                                            self.pos.pos_chatbox,
                                            think_ms=self.cfg.humanizar.pensar_3letras_pausa_ms,
                                            override_nums=use_nums_this_round
                                        )
                                    else:
                                        ok_send = self.typer.digitar(escolha, self.pos.pos_chatbox, override_nums=use_nums_this_round)

                                if ok_send:
                                    self.selector.registrar_uso(escolha, self.modo_atual)
                                    self.historico.append(escolha)
                                    self.acertos_consecutivos += 1
                                    if use_nums_this_round:
                                        self.numeros_restantes = max(0, self.numeros_restantes - 1)
                                        if self.numeros_restantes == 0:
                                            self.cfg.humanizar.inserir_numeros = False
                                            self._log("Rodadas com números concluídas. Inserção de números desativada.")
                                else:
                                    self._log("Envio cancelado no ENTER (não era mais a sua vez).")

                        except Exception as e:
                            self._log(f"Falha ao digitar: {e}")

                else:
                    self._log("Captura vazia; tentando novamente.")

            time.sleep(self.cfg.delay_ciclo_ms / 1000.0)


# ==============================
# Interface Gráfica (Tkinter + ttk)
# ==============================

class AppUI:
    def __init__(self):
        self.cfg_mgr = ConfigManager()
        self.cfg_mgr.load()

        self.pos_mgr = PosicoesManager()
        self.pos_mgr.load()

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("980x960")
        self.root.attributes("-topmost", True)

        # Estilo
        self.style = ttk.Style(self.root)
        if "vista" in self.style.theme_names():
            self.style.theme_use("vista")

        # Bot
        self.bot = BotCore(self.cfg_mgr.config, self.pos_mgr, self.append_terminal)

        # Menus / Tabs
        self._build_menubar()
        self._build_tabs()

        # F8 -> Parar (kill switch global)
        threading.Thread(target=self._monitor_f8, daemon=True).start()

        # Labels arco-íris (estéticas)
        self._apply_dev_label(self.tabs['Principal'])
        self._apply_dev_label(self.tabs['Terminal'])
        self._apply_dev_label(self.tabs['Setup'])
        self._apply_dev_label(self.tabs['Estatísticas'])
        self._apply_dev_label(self.tabs['Erros/Humano'])

        self.append_terminal("Posições e configurações carregadas.")

        self.root.mainloop()

    # ---------- Menus ----------
    def _build_menubar(self):
        menubar = Menu(self.root)
        self.root.config(menu=menubar)

        m_arquivo = Menu(menubar, tearoff=0)
        m_arquivo.add_command(label="Salvar Configurações", command=self._salvar_config)
        m_arquivo.add_command(label="Recarregar Dicionário", command=self._recarregar_dicionario)
        m_arquivo.add_command(label="Salvar Posições", command=self._salvar_posicoes)
        m_arquivo.add_separator()
        m_arquivo.add_command(label="Sair", command=self.root.destroy)

        m_ver = Menu(menubar, tearoff=0)
        self.var_topmost = tk.BooleanVar(value=True)
        m_ver.add_checkbutton(label="Sempre no topo", onvalue=True, offvalue=False, variable=self.var_topmost, command=self._toggle_topmost)

        menubar.add_cascade(label="Arquivo", menu=m_arquivo)
        menubar.add_cascade(label="Janela", menu=m_ver)

    # ---------- Tabs ----------
    def _build_tabs(self):
        self.tabs = {}
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(expand=1, fill='both', padx=6, pady=6)

        self.tabs['Principal'] = ttk.Frame(self.nb); self.nb.add(self.tabs['Principal'], text="Principal")
        self._build_tab_principal(self.tabs['Principal'])

        self.tabs['Terminal'] = ttk.Frame(self.nb); self.nb.add(self.tabs['Terminal'], text="Terminal")
        self._build_tab_terminal(self.tabs['Terminal'])

        self.tabs['Setup'] = ttk.Frame(self.nb); self.nb.add(self.tabs['Setup'], text="Setup")
        self._build_tab_setup(self.tabs['Setup'])

        self.tabs['Estatísticas'] = ttk.Frame(self.nb); self.nb.add(self.tabs['Estatísticas'], text="Estatísticas")
        self._build_tab_stats(self.tabs['Estatísticas'])

        self.tabs['Erros/Humano'] = ttk.Frame(self.nb); self.nb.add(self.tabs['Erros/Humano'], text="Erros/Humano")
        self._build_tab_human(self.tabs['Erros/Humano'])

    def _build_tab_principal(self, parent):
        f = ttk.Frame(parent)
        f.pack(pady=10)

        ttk.Label(f, text="Modo de Jogo:", font=('Arial', 14, 'bold')).grid(row=0, column=0, columnspan=4, pady=6)
        self.modo_var = tk.StringVar(value=self.cfg_mgr.config.modo)
        for i, (texto, val) in enumerate([("Palavras Longas", Modo.LONGA.value),
                                          ("Palavras Curtas", Modo.CURTA.value),
                                          ("Qualquer Palavra", Modo.QUALQUER.value),
                                          ("Modo Alfabeto (23 letras)", Modo.ALFABETO.value)]):
            ttk.Radiobutton(f, text=texto, variable=self.modo_var, value=val, command=self._on_modo).grid(row=1 + i // 2, column=i % 2, padx=8, pady=4, sticky="w")

        g = ttk.Frame(parent); g.pack(pady=10)
        self.btn_iniciar = ttk.Button(g, text="Iniciar", command=self._iniciar, width=30)
        self.btn_parar = ttk.Button(g, text="Parar (F8)", command=self._parar, width=30)
        self.btn_iniciar.grid(row=0, column=0, padx=6, pady=6)
        self.btn_parar.grid(row=0, column=1, padx=6, pady=6)

        s = ttk.Frame(parent); s.pack(pady=6, fill='x')
        self.lbl_status = ttk.Label(s, text="Status: Parado", foreground="red", font=('Arial', 12, 'bold'))
        self.lbl_status.pack(side='left', padx=6)

    def _build_tab_terminal(self, parent):
        self.terminal = scrolledtext.ScrolledText(parent, state=tk.DISABLED, wrap=tk.WORD)
        self.terminal.pack(expand=1, fill='both', padx=6, pady=6)

    def _build_tab_setup(self, parent):
        cfg = self.cfg_mgr.config

        frm = ttk.Frame(parent); frm.pack(padx=8, pady=8, fill='x')

        ttk.Label(frm, text="Caminho do Dicionário:").grid(row=0, column=0, sticky='w')
        self.ent_dict = ttk.Entry(frm, width=60); self.ent_dict.insert(0, cfg.caminho_dicionario)
        self.ent_dict.grid(row=0, column=1, padx=6)
        ttk.Button(frm, text="Abrir…", command=self._browse_dict).grid(row=0, column=2, padx=4)

        ttk.Label(frm, text="Template Chatbox (opcional):").grid(row=1, column=0, sticky='w', pady=4)
        self.ent_tpl = ttk.Entry(frm, width=60); self.ent_tpl.insert(0, cfg.template_chatbox)
        self.ent_tpl.grid(row=1, column=1, padx=6)
        ttk.Button(frm, text="Abrir…", command=self._browse_tpl).grid(row=1, column=2, padx=4)

        ttk.Label(frm, text="Threshold Template (0-1):").grid(row=2, column=0, sticky='w')
        self.spn_thr = ttk.Spinbox(frm, from_=0.5, to=0.99, increment=0.01, width=6)
        self.spn_thr.delete(0, tk.END); self.spn_thr.insert(0, str(cfg.template_threshold))
        self.spn_thr.grid(row=2, column=1, sticky='w')

        ttk.Label(frm, text="Threshold Barra de Turno (0-1):").grid(row=3, column=0, sticky='w')
        self.spn_turn_thr = ttk.Spinbox(frm, from_=0.5, to=0.99, increment=0.01, width=6)
        self.spn_turn_thr.delete(0, tk.END); self.spn_turn_thr.insert(0, str(cfg.turn_bar_threshold))
        self.spn_turn_thr.grid(row=3, column=1, sticky='w')

        ttk.Separator(parent, orient='horizontal').pack(fill='x', padx=8, pady=8)

        posf = ttk.Frame(parent); posf.pack(padx=8, pady=8, fill='x')
        ttk.Label(posf, text=f"Posição Letras: {self.pos_mgr.pos_letras}").grid(row=0, column=0, sticky='w', padx=4)
        ttk.Button(posf, text="Atualizar (clique na tela)", command=self._capturar_pos_letras).grid(row=0, column=1, padx=6)
        ttk.Label(posf, text=f"Posição Chatbox: {self.pos_mgr.pos_chatbox}").grid(row=1, column=0, sticky='w', padx=4)
        ttk.Button(posf, text="Atualizar (clique na tela)", command=self._capturar_pos_chat).grid(row=1, column=1, padx=6)
        self.lbl_turn_rect = ttk.Label(posf, text=f"Retângulo Barra Turno: {self.pos_mgr.turn_bar_rect}")
        self.lbl_turn_rect.grid(row=2, column=0, sticky='w', padx=4)
        ttk.Button(posf, text="Atualizar retângulo", command=self._capturar_turn_bar).grid(row=2, column=1, padx=6)

        ttk.Separator(parent, orient='horizontal').pack(fill='x', padx=8, pady=8)

        delf = ttk.LabelFrame(parent, text="Delays (ms)")
        delf.pack(padx=8, pady=8, fill='x')

        self.sld_ciclo   = ttk.Scale(delf, from_=80,  to=1000, value=cfg.delay_ciclo_ms,        command=lambda e: None)
        self.sld_copiar  = ttk.Scale(delf, from_=80,  to=800,  value=cfg.delay_pos_copiar_ms,   command=lambda e: None)
        self.sld_antes   = ttk.Scale(delf, from_=80,  to=1000, value=cfg.delay_antes_digitar_ms, command=lambda e: None)

        ttk.Label(delf, text="Entre ciclos:").grid(row=0, column=0, sticky='w')
        ttk.Label(delf, textvariable=self._bind_val(self.sld_ciclo)).grid(row=0, column=2, sticky='w', padx=6)
        self.sld_ciclo.grid(row=0, column=1, sticky='we', padx=6, pady=4)

        ttk.Label(delf, text="Após copiar letras:").grid(row=1, column=0, sticky='w')
        ttk.Label(delf, textvariable=self._bind_val(self.sld_copiar)).grid(row=1, column=2, sticky='w', padx=6)
        self.sld_copiar.grid(row=1, column=1, sticky='we', padx=6, pady=4)

        ttk.Label(delf, text="Antes de digitar palavra:").grid(row=2, column=0, sticky='w')
        ttk.Label(delf, textvariable=self._bind_val(self.sld_antes)).grid(row=2, column=2, sticky='w', padx=6)
        self.sld_antes.grid(row=2, column=1, sticky='we', padx=6, pady=4)

        # Aviso do limite por rodada
        limf = ttk.LabelFrame(parent, text="Limite estimado por rodada")
        limf.pack(padx=8, pady=8, fill='x')
        ttk.Label(limf, text=f"Atual: {cfg.limite_tempo_round_s:.2f} s (configure na seção abaixo)").grid(row=0, column=0, sticky='w')

        tog = ttk.LabelFrame(parent, text="Opções")
        tog.pack(padx=8, pady=8, fill='x')

        self.var_modo_teste = tk.BooleanVar(value=self.cfg_mgr.config.modo_teste)
        self.var_log = tk.BooleanVar(value=self.cfg_mgr.config.salvar_log)
        ttk.Checkbutton(tog, text="Modo Teste (não digita)", variable=self.var_modo_teste).grid(row=0, column=0, sticky='w')
        ttk.Checkbutton(tog, text="Salvar log em arquivo", variable=self.var_log).grid(row=0, column=1, sticky='w')

        self.var_penaliza = tk.BooleanVar(value=self.cfg_mgr.config.penaliza_repetidas)
        ttk.Checkbutton(tog, text="Penalizar repetição/frequência", variable=self.var_penaliza).grid(row=1, column=0, sticky='w')

        ttk.Label(tog, text="Cooldown de repetição (N últimas):").grid(row=1, column=1, sticky='e')
        self.spn_cool = ttk.Spinbox(tog, from_=0, to=50, width=5)
        self.spn_cool.delete(0, tk.END); self.spn_cool.insert(0, str(self.cfg_mgr.config.cooldown_repeticao))
        self.spn_cool.grid(row=1, column=2, sticky='w', padx=4)

        ttk.Label(tog, text="Exibir top N opções:").grid(row=2, column=1, sticky='e')
        self.spn_top = ttk.Spinbox(tog, from_=0, to=10, width=5)
        self.spn_top.delete(0, tk.END); self.spn_top.insert(0, str(self.cfg_mgr.config.mostrar_top_n))
        self.spn_top.grid(row=2, column=2, sticky='w', padx=4)

        # bloco para setar limite por rodada
        setf = ttk.LabelFrame(parent, text="Ajustes rápidos")
        setf.pack(padx=8, pady=8, fill='x')
        ttk.Label(setf, text="Limite estimado por rodada (s):").grid(row=0, column=0, sticky='w')
        self.ent_limiteS = ttk.Entry(setf, width=10)
        self.ent_limiteS.insert(0, f"{cfg.limite_tempo_round_s:.2f}")
        self.ent_limiteS.grid(row=0, column=1, sticky='w', padx=6)

        ttk.Button(parent, text="Aplicar / Salvar", command=self._salvar_config).pack(pady=8)

    def _build_tab_stats(self, parent):
        self.lbl_total_dict = ttk.Label(parent, text="Total no dicionário: 0"); self.lbl_total_dict.pack(anchor='w', padx=8, pady=4)
        self.lbl_hist = ttk.Label(parent, text="Total digitadas: 0 | Alfabetos completos: 0"); self.lbl_hist.pack(anchor='w', padx=8, pady=4)
        self.lbl_humano = ttk.Label(parent, text="Acertos consecutivos: 0 | Erros propositais: 0"); self.lbl_humano.pack(anchor='w', padx=8, pady=4)
        self.lbl_nums = ttk.Label(parent, text="Rodadas com números restantes: 0"); self.lbl_nums.pack(anchor='w', padx=8, pady=4)

        ttk.Button(parent, text="Ver histórico completo", command=self._ver_historico).pack(pady=6)

        def refresh():
            self.lbl_total_dict.config(text=f"Total no dicionário: {len(self.bot.dict.palavras)}")
            self.lbl_hist.config(text=f"Total digitadas: {len(self.bot.historico)} | Alfabetos completos: {self.bot.selector.alfabeto_completado}")
            self.lbl_humano.config(text=f"Acertos consecutivos: {self.bot.acertos_consecutivos} | Erros propositais: {self.bot.erros_propositais}")
            self.lbl_nums.config(text=f"Rodadas com números restantes: {self.bot.numeros_restantes}")
            parent.after(800, refresh)
        refresh()

    def _build_tab_human(self, parent):
        h = self.cfg_mgr.config.humanizar

        frm = ttk.Frame(parent); frm.pack(padx=8, pady=8, fill='x')

        ttk.Label(frm, text="Perfil de Velocidade:").grid(row=0, column=0, sticky='w')
        self.perfil_var = tk.StringVar(value=h.perfil)
        for i, val in enumerate([VelocidadePerfil.RAPIDA.value,
                                 VelocidadePerfil.ALEATORIA.value,
                                 VelocidadePerfil.GRADUAL.value,
                                 VelocidadePerfil.NENHUM.value]):
            ttk.Radiobutton(frm, text=val.capitalize(), variable=self.perfil_var, value=val).grid(row=0, column=i+1, padx=4)

        ttk.Label(frm, text="Delay entre letras (ms):").grid(row=1, column=0, sticky='w', pady=4)
        self.sld_delay_letra = ttk.Scale(frm, from_=1, to=120, value=h.delay_entre_letras_ms, command=lambda e: None)
        ttk.Label(frm, textvariable=self._bind_val(self.sld_delay_letra)).grid(row=1, column=2, sticky='w', padx=6)
        self.sld_delay_letra.grid(row=1, column=1, sticky='we', padx=6)

        ttk.Label(frm, text="Chance de erro por caractere (%):").grid(row=2, column=0, sticky='w', pady=4)
        self.sld_chance_erro = ttk.Scale(frm, from_=0, to=25, value=h.chance_erro * 100, command=lambda e: None)
        ttk.Label(frm, textvariable=self._bind_val(self.sld_chance_erro, suffix="%")).grid(row=2, column=2, sticky='w', padx=6)
        self.sld_chance_erro.grid(row=2, column=1, sticky='we', padx=6)

        ttk.Label(frm, text="Variação delay máx (ms):").grid(row=3, column=0, sticky='w', pady=4)
        self.sld_var_delay = ttk.Scale(frm, from_=0, to=50, value=h.variacao_delay * 1000, command=lambda e: None)
        ttk.Label(frm, textvariable=self._bind_val(self.sld_var_delay)).grid(row=3, column=2, sticky='w', padx=6)
        self.sld_var_delay.grid(row=3, column=1, sticky='we', padx=6)

        ttk.Label(frm, text="Pausa a cada N letras:").grid(row=4, column=0, sticky='w', pady=4)
        self.spn_pausa_cada = ttk.Spinbox(frm, from_=2, to=8, width=5)
        self.spn_pausa_cada.delete(0, tk.END); self.spn_pausa_cada.insert(0, str(h.pausa_cada))
        self.spn_pausa_cada.grid(row=4, column=1, sticky='w')

        ttk.Label(frm, text="Pausa min (s):").grid(row=4, column=2, sticky='e')
        self.ent_pausa_min = ttk.Entry(frm, width=6); self.ent_pausa_min.insert(0, f"{h.pausa_min:.3f}")
        self.ent_pausa_min.grid(row=4, column=3, sticky='w', padx=4)

        ttk.Label(frm, text="Pausa max (s):").grid(row=4, column=4, sticky='e')
        self.ent_pausa_max = ttk.Entry(frm, width=6); self.ent_pausa_max.insert(0, f"{h.pausa_max:.3f}")
        self.ent_pausa_max.grid(row=4, column=5, sticky='w', padx=4)

        ttk.Separator(parent, orient='horizontal').pack(fill='x', padx=8, pady=8)

        nums = ttk.LabelFrame(parent, text="Inserir números aleatórios")
        nums.pack(fill='x', padx=8, pady=8)
        self.var_inserir_num = tk.BooleanVar(value=h.inserir_numeros)
        ttk.Checkbutton(nums, text="Ativar", variable=self.var_inserir_num).grid(row=0, column=0, sticky='w')
        ttk.Label(nums, text="Rodadas com números:").grid(row=0, column=1, sticky='e')
        self.spn_nums_rounds = ttk.Spinbox(nums, from_=0, to=50, width=5)
        self.spn_nums_rounds.delete(0, tk.END); self.spn_nums_rounds.insert(0, str(h.numeros_rodadas))
        self.spn_nums_rounds.grid(row=0, column=2, sticky='w', padx=4)

        errgrp = ttk.LabelFrame(parent, text="Comportamentos Humanizados")
        errgrp.pack(fill='x', padx=8, pady=8)

        ttk.Label(errgrp, text="Chance de falha proposital (%):").grid(row=0, column=0, sticky='w')
        self.sld_chance_falha = ttk.Scale(errgrp, from_=0, to=50, value=h.chance_falha_proposital * 100, command=lambda e: None)
        ttk.Label(errgrp, textvariable=self._bind_val(self.sld_chance_falha, suffix="%")).grid(row=0, column=2, sticky='w', padx=6)
        self.sld_chance_falha.grid(row=0, column=1, sticky='we', padx=6)

        ttk.Label(errgrp, text="Chance de enviar errado (+ENTER) e corrigir (%):").grid(row=1, column=0, sticky='w')
        self.sld_chance_errEnter = ttk.Scale(errgrp, from_=0, to=60, value=h.chance_erro_enter * 100, command=lambda e: None)
        ttk.Label(errgrp, textvariable=self._bind_val(self.sld_chance_errEnter, suffix="%")).grid(row=1, column=2, sticky='w', padx=6)
        self.sld_chance_errEnter.grid(row=1, column=1, sticky='we', padx=6)

        ttk.Label(errgrp, text="Chance de frase engraçada antes (%):").grid(row=2, column=0, sticky='w')
        self.sld_chance_frase = ttk.Scale(errgrp, from_=0, to=100, value=h.chance_frase_engracada * 100, command=lambda e: None)
        ttk.Label(errgrp, textvariable=self._bind_val(self.sld_chance_frase, suffix="%")).grid(row=2, column=2, sticky='w', padx=6)
        self.sld_chance_frase.grid(row=2, column=1, sticky='we', padx=6)

        ttk.Label(errgrp, text="Chance de 'ensaio' da palavra antes (%):").grid(row=3, column=0, sticky='w')
        self.sld_chance_ensaio = ttk.Scale(errgrp, from_=0, to=100, value=h.chance_ensaio_palavra * 100, command=lambda e: None)
        ttk.Label(errgrp, textvariable=self._bind_val(self.sld_chance_ensaio, suffix="%")).grid(row=3, column=2, sticky='w', padx=6)
        self.sld_chance_ensaio.grid(row=3, column=1, sticky='we', padx=6)

        # --- Pensar após 3 letras ---
        pensarf = ttk.LabelFrame(parent, text="Pensar após 3 letras (se a palavra começar com as 3 do desafio)")
        pensarf.pack(fill='x', padx=8, pady=8)
        self.var_pensar3 = tk.BooleanVar(value=h.pensar_3letras)
        ttk.Checkbutton(pensarf, text="Ativar", variable=self.var_pensar3).grid(row=0, column=0, sticky='w')
        ttk.Label(pensarf, text="Pausa (ms):").grid(row=0, column=1, sticky='e')
        self.spn_pensar_ms = ttk.Spinbox(pensarf, from_=100, to=2000, increment=50, width=7)
        self.spn_pensar_ms.delete(0, tk.END); self.spn_pensar_ms.insert(0, str(h.pensar_3letras_pausa_ms))
        self.spn_pensar_ms.grid(row=0, column=2, sticky='w', padx=4)

        ttk.Label(parent, text="Frases engraçadas (uma por linha):").pack(anchor='w', padx=8)
        self.txt_frases = scrolledtext.ScrolledText(parent, height=6, wrap=tk.WORD)
        if h.frases_customizadas:
            self.txt_frases.insert(tk.END, "\n".join(h.frases_customizadas))
        self.txt_frases.pack(fill='x', padx=8, pady=4)

        ttk.Button(parent, text="Aplicar / Salvar", command=self._salvar_config).pack(pady=8)

    # ---------- Helpers ----------
    def _bind_val(self, scale: ttk.Scale, suffix="ms"):
        var = tk.StringVar(value=f"{int(scale.get())} {suffix}")
        def upd(_evt=None):
            if suffix == "%":
                var.set(f"{int(scale.get())}{suffix}")
            else:
                try:
                    val = float(scale.get())
                    var.set(f"{val:.0f} {suffix}" if suffix != "s" else f"{val:.1f} {suffix}")
                except:
                    var.set(f"{int(scale.get())} {suffix}")
        scale.configure(command=lambda e: upd())
        return var

    def _apply_dev_label(self, parent):
        lbl = tk.Label(parent, text="Desenvolvedor: @lucasleao18", font=('Arial', 9))
        lbl.place(relx=1.0, rely=1.0, anchor='se')
        def rainbow():
            r = lambda: random.randint(0, 255)
            lbl.config(fg=f"#{r():02x}{r():02x}{r():02x}")
            parent.after(500, rainbow)
        rainbow()

    # ---------- Terminal ----------
    def append_terminal(self, text: str):
        self.terminal.config(state=tk.NORMAL)
        self.terminal.insert(tk.END, f"{now()} - {text}\n")
        self.terminal.config(state=tk.DISABLED)
        self.terminal.yview(tk.END)

    # ---------- Eventos ----------
    def _on_modo(self):
        modo = self.modo_var.get()
        self.cfg_mgr.config.modo = modo
        self.bot.set_modo(modo)

    def _iniciar(self):
        self._capturar_config_da_ui()
        if not os.path.exists(self.cfg_mgr.config.caminho_dicionario):
            messagebox.showerror("Erro", f" Dicionário não encontrado: {self.cfg_mgr.config.caminho_dicionario}")
            return
        # ressincroniza contador de rodadas com números
        self.bot.numeros_restantes = self.cfg_mgr.config.humanizar.numeros_rodadas if self.cfg_mgr.config.humanizar.inserir_numeros else 0
        self.lbl_status.config(text="Status: Rodando", foreground="green")
        self.bot.iniciar()

    def _parar(self):
        self.bot.parar()
        self.lbl_status.config(text="Status: Parado", foreground="red")

    def _handle_kill_switch(self):
        if self.bot.executando:
            self.append_terminal("F8 pressionado - kill switch acionado.")
        self._parar()

    def _monitor_f8(self):
        while True:
            try:
                if keyboard.is_pressed('f8'):
                    self.root.after(0, self._handle_kill_switch)
                    while keyboard.is_pressed('f8'):
                        time.sleep(0.05)
            except Exception:
                time.sleep(0.5)
            time.sleep(0.1)

    # ---------- Navegação arquivos ----------
    def _browse_dict(self):
        path = filedialog.askopenfilename(title="Selecionar dicionário (txt)", filetypes=[("Textos", "*.txt"), ("Todos", "*.*")])
        if path:
            self.ent_dict.delete(0, tk.END)
            self.ent_dict.insert(0, path)

    def _browse_tpl(self):
        path = filedialog.askopenfilename(title="Selecionar template da chatbox (png)", filetypes=[("Imagens", "*.png"), ("Todos", "*.*")])
        if path:
            self.ent_tpl.delete(0, tk.END)
            self.ent_tpl.insert(0, path)

    # ---------- Posições ----------
    def _capturar_pos_letras(self):
        self.append_terminal("Clique no jogo onde as letras aparecem (duplo clique para selecionar).")
        self._capturar_posicao(lambda x, y: self._set_pos('letras', x, y))

    def _capturar_pos_chat(self):
        self.append_terminal("Clique na chatbox do jogo (onde digita as palavras).")
        self._capturar_posicao(lambda x, y: self._set_pos('chat', x, y))

    def _capturar_turn_bar(self):
        self.append_terminal("Clique no canto superior esquerdo da barra de turno e depois no canto inferior direito.")
        self._capturar_retangulo(self._set_turn_bar)

    def _capturar_posicao(self, callback):
        def on_click(x, y, button, pressed):
            if pressed:
                callback(x, y)
                return False
        threading.Thread(target=lambda: mouse.Listener(on_click=on_click).start(), daemon=True).start()

    def _capturar_retangulo(self, callback):
        pontos = []

        def on_click(x, y, button, pressed):
            if pressed:
                pontos.append((x, y))
                self.append_terminal(f"Ponto {len(pontos)} registrado: ({x}, {y})")
                if len(pontos) >= 2:
                    callback(pontos[0], pontos[1])
                    return False
        threading.Thread(target=lambda: mouse.Listener(on_click=on_click).start(), daemon=True).start()

    def _set_pos(self, which, x, y):
        if which == 'letras':
            self.pos_mgr.pos_letras = (x, y)
            self.append_terminal(f"Posição Letras -> {self.pos_mgr.pos_letras}")
        else:
            self.pos_mgr.pos_chatbox = (x, y)
            self.append_terminal(f"Posição Chatbox -> {self.pos_mgr.pos_chatbox}")

    def _set_turn_bar(self, p1, p2):
        x1, y1 = p1
        x2, y2 = p2
        left = int(min(x1, x2))
        top = int(min(y1, y2))
        width = int(abs(x2 - x1)) or 1
        height = int(abs(y2 - y1)) or 1
        self.pos_mgr.turn_bar_rect = (left, top, width, height)
        if hasattr(self, 'lbl_turn_rect'):
            self.lbl_turn_rect.config(text=f"Retângulo Barra Turno: {self.pos_mgr.turn_bar_rect}")
        self.append_terminal(f"Barra de turno definida: {self.pos_mgr.turn_bar_rect}")
        self.bot.capt.turn_bar_reference = None
        self.bot.capt._warned_turn_rect = False

    # ---------- Salvar/Aplicar ----------
    def _capturar_config_da_ui(self):
        cfg = self.cfg_mgr.config
        cfg.caminho_dicionario = self.ent_dict.get().strip()
        cfg.template_chatbox = self.ent_tpl.get().strip()
        try: cfg.template_threshold = float(self.spn_thr.get())
        except: pass
        try: cfg.turn_bar_threshold = float(self.spn_turn_thr.get())
        except: pass

        cfg.delay_ciclo_ms = int(float(self.sld_ciclo.get()))
        cfg.delay_pos_copiar_ms = int(float(self.sld_copiar.get()))
        cfg.delay_antes_digitar_ms = int(float(self.sld_antes.get()))

        # limite via input
        try:
            cfg.limite_tempo_round_s = float(self.ent_limiteS.get().replace(',', '.'))
        except: pass

        cfg.modo_teste = self.var_modo_teste.get()
        cfg.salvar_log = self.var_log.get()
        cfg.penaliza_repetidas = self.var_penaliza.get()
        try: cfg.cooldown_repeticao = int(self.spn_cool.get())
        except: pass
        try: cfg.mostrar_top_n = int(self.spn_top.get())
        except: pass

        h = cfg.humanizar
        h.perfil = self.perfil_var.get()
        h.delay_entre_letras_ms = int(float(self.sld_delay_letra.get()))
        h.chance_erro = float(self.sld_chance_erro.get()) / 100.0
        h.variacao_delay = float(self.sld_var_delay.get()) / 1000.0
        try: h.pausa_cada = int(self.spn_pausa_cada.get())
        except: pass
        try:
            h.pausa_min = float(self.ent_pausa_min.get())
            h.pausa_max = float(self.ent_pausa_max.get())
            if h.pausa_min > h.pausa_max:
                h.pausa_min, h.pausa_max = h.pausa_max, h.pausa_min
        except: pass

        # números + rodadas
        h.inserir_numeros = self.var_inserir_num.get()
        try: h.numeros_rodadas = int(self.spn_nums_rounds.get())
        except: h.numeros_rodadas = 0

        # chances novas
        h.chance_falha_proposital = float(self.sld_chance_falha.get()) / 100.0
        h.chance_erro_enter = float(self.sld_chance_errEnter.get()) / 100.0
        h.chance_frase_engracada = float(self.sld_chance_frase.get()) / 100.0
        h.chance_ensaio_palavra = float(self.sld_chance_ensaio.get()) / 100.0

        # pensar após 3 letras
        h.pensar_3letras = self.var_pensar3.get()
        try: h.pensar_3letras_pausa_ms = int(self.spn_pensar_ms.get())
        except: pass

        # frases custom
        txt = self.txt_frases.get("1.0", tk.END).strip()
        h.frases_customizadas = [ln.strip() for ln in txt.splitlines() if ln.strip()]

    def _salvar_config(self):
        self._capturar_config_da_ui()
        self.cfg_mgr.save()
        self.append_terminal("Configurações salvas.")
        self.bot.cfg = self.cfg_mgr.config  # atualiza bot
        self.bot.capt.cfg = self.cfg_mgr.config
        self.bot.typer.cfg = self.cfg_mgr.config

    def _salvar_posicoes(self):
        self.pos_mgr.save()
        self.append_terminal("Posições salvas.")

    def _recarregar_dicionario(self):
        self._capturar_config_da_ui()
        if not self.bot.carregar_dict_e_blacklist():
            messagebox.showerror("Erro", f"Falha ao carregar dicionário: {self.cfg_mgr.config.caminho_dicionario}")
            return
        self.append_terminal("Dicionário recarregado.")

    def _toggle_topmost(self):
        self.root.attributes("-topmost", bool(self.var_topmost.get()))

    def _ver_historico(self):
        win = Toplevel(self.root)
        win.title("Histórico Completo")
        txt = scrolledtext.ScrolledText(win, wrap=tk.WORD, width=80, height=30)
        txt.pack(expand=1, fill='both')
        for w in self.bot.historico:
            c = self.bot.selector.frequencia.get(w, 0)
            txt.insert(tk.END, f"{now()} - {w} (usada {c}x)\n")


# ==============================
# Main
# ==============================

if __name__ == "__main__":
    try:
        AppUI()
    except KeyboardInterrupt:
        pass
