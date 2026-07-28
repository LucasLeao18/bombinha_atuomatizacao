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
from tkinter import ttk, Toplevel, filedialog, messagebox
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
        tk.Label(footer, text="F8  ·  parar tudo", bg=T.SIDEBAR, fg=T.TEXT_MUTE, font=T.FONT_SM).pack(anchor="w")
        tk.Label(footer, text="Ctrl+S  ·  salvar", bg=T.SIDEBAR, fg=T.TEXT_MUTE, font=T.FONT_SM).pack(anchor="w")
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
        Btn(btns, "Recarregar dicionário", command=self._recarregar_dicionario, variant="ghost", icon="⟳",
            padx=18, pady=11).pack(side="left")

        tk.Label(cbody, text="Deixe a janela do jogo em foco antes de iniciar. F8 interrompe de qualquer lugar.",
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

        r = form_row(b, "Cooldown de repetição", "Não repetir palavra usada nas últimas N rodadas")
        self.stp_cool = Stepper(r, 0, 50, cfg.cooldown_repeticao)
        self.stp_cool.pack(side="left")

        r = form_row(b, "Exibir top N opções", "Quantas alternativas mostrar no console")
        self.stp_top = Stepper(r, 0, 10, cfg.mostrar_top_n)
        self.stp_top.pack(side="left")

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

        card, b = make_card(body, "Perfil de digitação", "Como o bot distribui o tempo entre as teclas")
        card.pack(fill="x")

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
        self.st_seq = StatCard(cards2, "acertos consecutivos", "0", T.SUCCESS)
        self.st_nums = StatCard(cards2, "rodadas c/ números restantes", "0", T.PURPLE)
        for i, c in enumerate((self.st_seq, self.st_nums)):
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
        total_dict = len(self.bot.dict.palavras)
        enviadas = len(self.bot.historico)
        self.st_dict.set(total_dict)
        self.st_enviadas.set(enviadas)
        self.st_alfabeto.set(self.bot.selector.alfabeto_completado)
        self.st_erros.set(self.bot.erros_propositais)
        self.st_seq.set(self.bot.acertos_consecutivos)
        self.st_nums.set(self.bot.numeros_restantes)
        self.card_palavras.set(enviadas)
        self.card_sequencia.set(self.bot.acertos_consecutivos)
        self.card_dict.set(total_dict)
        self.lbl_status_right.configure(
            text=f"modo: {self.bot.modo_atual}   ·   dicionário: {total_dict}   ·   enviadas: {enviadas}")
        self.root.after(700, self._refresh_stats)

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
        while True:
            try:
                if keyboard.is_pressed('f8'):
                    self.root.after(0, self._handle_kill_switch)
                    while keyboard.is_pressed('f8'):
                        time.sleep(0.05)
            except Exception:
                time.sleep(0.5)
            time.sleep(0.1)

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
        if which == 'letras':
            self.pos_mgr.pos_letras = (x, y)
            self.lbl_pos_letras.configure(text=str(self.pos_mgr.pos_letras))
            self.enqueue_log(f"Posição das letras definida: {self.pos_mgr.pos_letras}")
        else:
            self.pos_mgr.pos_chatbox = (x, y)
            self.lbl_pos_chat.configure(text=str(self.pos_mgr.pos_chatbox))
            self.enqueue_log(f"Posição da chatbox definida: {self.pos_mgr.pos_chatbox}")

    def _set_turn_bar(self, p1, p2):
        x1, y1 = p1
        x2, y2 = p2
        rect = (int(min(x1, x2)), int(min(y1, y2)), int(abs(x2 - x1)) or 1, int(abs(y2 - y1)) or 1)
        self.pos_mgr.turn_bar_rect = rect
        self.lbl_turn_rect.configure(text=str(rect))
        self.enqueue_log(f"Barra de turno definida: {rect}")
        self.bot.capt.turn_bar_reference = None
        self.bot.capt._warned_turn_rect = False

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
