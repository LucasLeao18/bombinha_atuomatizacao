import cv2
import numpy as np
from PIL import ImageGrab
import pyautogui
import time
import re
import pyperclip
import tkinter as tk
from tkinter import ttk, scrolledtext, Toplevel, Menu
from threading import Thread
import random
import keyboard
from pynput import mouse
import json
import datetime

# -----------------------------------------------------------
# Variáveis Globais
# -----------------------------------------------------------
modo_selecionado = None
executando = False
inserir_numeros = False
posicao_mouse_letras = (692, 594)
posicao_mouse_chatbox = (838, 953)

letras_ignoradas = {'y', 'k', 'w'}

palavras_dicionario = []
palavras_processadas = []
letras_usadas = set()
alfabeto_completado = 0
caminho_dicionario = 'acento.txt'
modo_teste = False
modo_debug_log = False

# Delays ajustáveis
delay_entre_ciclos = 0.2
delay_captura_letras = 0.3
delay_entre_letras = 0.001
delay_antes_digitar = 0.2

blacklist = set()
mostrar_top_5 = True
freq_usage = {}
contador_falhas_captura = 0
limite_falhas_captura = 5
modo_alfabetico = False
usos_por_modo = {"longa":0, "curta":0, "qualquer":0, "alfabeto":0, "alfabetico":0}
contador_blacklist = 0

erro_variacao_ativo = False

# Config Erros
chance_erro_val = 0.1
delay_variacao_val = 0.002
letras_erradas_val = "abcdefghijklmnopqrstuvwxyz"

# Modos de velocidade:
# 0 = Nenhum selecionado
# 1 = Velocidade Rápida
# 2 = Velocidade Aleatória
# 3 = Velocidade Gradual
modo_velocidade = 0

def append_terminal(text: str):
    terminal_textbox.config(state=tk.NORMAL)
    terminal_textbox.insert(tk.END, text + "\n")
    terminal_textbox.config(state=tk.DISABLED)
    terminal_textbox.yview(tk.END)
    if modo_debug_log:
        escrever_log(text)

def escrever_log(text: str):
    with open('log.txt', 'a', encoding='utf-8') as f:
        f.write(f"{datetime.datetime.now()} - {text}\n")

def carregar_posicoes():
    global posicao_mouse_letras, posicao_mouse_chatbox
    try:
        with open('posicoes.json', 'r') as file:
            posicoes = json.load(file)
            posicao_mouse_letras = tuple(posicoes.get('letras', posicao_mouse_letras))
            posicao_mouse_chatbox = tuple(posicoes.get('chatbox', posicao_mouse_chatbox))
            append_terminal("Posições carregadas com sucesso.")
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        append_terminal("Nenhuma posição salva encontrada ou arquivo corrompido, usando valores padrão.")

def salvar_posicoes():
    posicoes = {
        'letras': posicao_mouse_letras,
        'chatbox': posicao_mouse_chatbox
    }
    with open('posicoes.json', 'w') as file:
        json.dump(posicoes, file)
    append_terminal("Posições salvas com sucesso.")

def detectar_chatbox(image_path='chatbox.png', threshold=0.8):
    screen = np.array(ImageGrab.grab())
    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)

    template = cv2.imread(image_path, 0)
    if template is None:
        append_terminal("Imagem da chatbox não encontrada ou inválida.")
        return None

    w, h = template.shape[::-1]
    res = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
    loc = np.where(res >= threshold)

    if len(loc[0]) > 0:
        for pt in zip(*loc[::-1]):
            return pt
    return None

def capturar_letras_mouse():
    global contador_falhas_captura
    pyautogui.doubleClick(x=posicao_mouse_letras[0], y=posicao_mouse_letras[1])
    time.sleep(delay_captura_letras)
    pyautogui.hotkey('ctrl', 'c')
    time.sleep(delay_captura_letras)

    letras = pyperclip.paste()
    letras_somente = re.sub(r'[^A-Za-z]', '', letras)
    letras_minusculas = letras_somente.lower().strip()

    if not letras_minusculas:
        contador_falhas_captura += 1
        if contador_falhas_captura > limite_falhas_captura:
            append_terminal("Falhas repetidas ao capturar letras! Verifique as posições ou o jogo.")
    else:
        contador_falhas_captura = 0

    return letras_minusculas

def carregar_dicionario_func(caminho_arquivo: str):
    try:
        with open(caminho_arquivo, 'r', encoding='utf-8') as arquivo:
            return [palavra.strip().lower() for palavra in arquivo if palavra.strip()]
    except FileNotFoundError:
        append_terminal(f"Arquivo {caminho_arquivo} não encontrado.")
        return []

def carregar_blacklist():
    global blacklist
    blacklist.clear()
    try:
        with open('blacklist.txt', 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    blacklist.add(line.strip().lower())
        append_terminal("Blacklist carregada com sucesso.")
    except FileNotFoundError:
        append_terminal("Nenhuma blacklist encontrada. Crie um arquivo 'blacklist.txt' se desejar.")

def filtrar_palavras(palavras, letras: str):
    return [palavra for palavra in palavras if letras in palavra]

def escolher_palavra(palavras, criterio='longa'):
    global letras_usadas, alfabeto_completado, contador_blacklist

    # Remove palavras da blacklist
    palavras = [p for p in palavras if p not in blacklist]

    # Exibir top 5
    if mostrar_top_5 and palavras:
        top5 = palavras[:5]
        append_terminal(f"Top 5 opções: {', '.join(top5)}")

    if criterio == 'curta':
        palavras_ordenadas = sorted(palavras, key=len)
    elif criterio == 'alfabeto':
        palavras_ordenadas = sorted(
            [p for p in palavras if not any(l in letras_ignoradas for l in p)],
            key=lambda p: len(set(p) - letras_ignoradas - letras_usadas),
            reverse=True
        )
    elif criterio == 'alfabetico':
        palavras_ordenadas = sorted(palavras)
    else:
        palavras_ordenadas = sorted(palavras, key=len, reverse=True)

    for palavra in palavras_ordenadas:
        if palavra not in palavras_processadas:
            return palavra
    return None

def aplicar_modo_velocidade():
    """
    Aplica ajustes de velocidade com base no modo selecionado:
    1 = Velocidade Rápida: delays mínimos
    2 = Velocidade Aleatória: delay aleatório entre palavras
    3 = Velocidade Gradual: a cada palavra digitada, delay_entre_letras diminui
    """
    global modo_velocidade, delay_entre_letras

    if modo_velocidade == 1:
        # Velocidade Rápida: definir delay_entre_letras muito baixo
        delay_entre_letras = 0.0005
    elif modo_velocidade == 2:
        # Velocidade Aleatória: antes de digitar cada palavra, introduz um delay aleatório
        time.sleep(random.uniform(0.1, 0.5))
    elif modo_velocidade == 3:
        # Velocidade Gradual será aplicada após a digitação da palavra, no digitar_palavra
        pass

def digitar_palavra(palavra: str):
    global inserir_numeros, modo_teste, freq_usage, delay_entre_letras, modo_velocidade
    global chance_erro_val, delay_variacao_val, letras_erradas_val, erro_variacao_ativo

    if erro_variacao_ativo:
        chance_erro = chance_erro_val
        letras_erradas_possiveis = list(letras_erradas_val)
        delay_variacao = delay_variacao_val
    else:
        chance_erro = 0.0
        delay_variacao = 0.0
        letras_erradas_possiveis = []

    if modo_teste:
        append_terminal(f"[TESTE] Digitando: {palavra}")
    else:
        for letra in palavra:
            if erro_variacao_ativo and random.random() < chance_erro:
                if letras_erradas_possiveis:
                    letra_errada = random.choice(letras_erradas_possiveis)
                else:
                    letra_errada = letra
                pyautogui.typewrite(letra_errada)
                time.sleep(delay_entre_letras + random.uniform(0, delay_variacao))
                pyautogui.press('backspace')
                time.sleep(delay_entre_letras + random.uniform(0, delay_variacao))
                pyautogui.typewrite(letra)
            else:
                pyautogui.typewrite(letra)

            if inserir_numeros and random.choice([True, False]):
                numero_aleatorio = str(random.randint(0, 9))
                pyautogui.typewrite(numero_aleatorio)

            time.sleep(delay_entre_letras + (random.uniform(0, delay_variacao) if erro_variacao_ativo else 0))

        pyautogui.press('enter')

    freq_usage[palavra] = freq_usage.get(palavra, 0) + 1

    # Se modo_velocidade == 3 (Velocidade Gradual), diminuir delay a cada palavra
    if modo_velocidade == 3:
        delay_entre_letras = max(0.0005, delay_entre_letras - 0.0001)

def main():
    global modo_selecionado, executando, palavras_dicionario, palavras_processadas, letras_usadas, alfabeto_completado
    global usos_por_modo, contador_blacklist

    if not modo_selecionado:
        append_terminal("Nenhum modo selecionado!")
        executando = False
        return

    append_terminal(f"Iniciando no modo: {modo_selecionado}")
    usos_por_modo[modo_selecionado] = usos_por_modo.get(modo_selecionado, 0) + 1

    if not palavras_dicionario:
        append_terminal("Carregando dicionário...")
        dicionario = carregar_dicionario_func(caminho_dicionario)
        if not dicionario:
            append_terminal("Nenhuma palavra disponível no dicionário. Verifique o arquivo.")
            executando = False
            return
        palavras_dicionario.extend(dicionario)
        append_terminal("Dicionário carregado com sucesso.")

    carregar_blacklist()

    if modo_selecionado == 'alfabeto':
        letras_usadas.clear()
        alfabeto_completado = 0

    while executando:
        chatbox_position = detectar_chatbox('chatbox.png')
        if chatbox_position:
            append_terminal("Chatbox detectada, é a sua vez de jogar!")
            letras_detectadas = capturar_letras_mouse()
            append_terminal(f"Letras detectadas: {letras_detectadas}")

            if letras_detectadas:
                criterio = modo_selecionado if not modo_alfabetico else 'alfabetico'
                palavras_filtradas = filtrar_palavras(palavras_dicionario, letras_detectadas)

                if not palavras_filtradas:
                    append_terminal("Nenhuma palavra encontrada para essas letras. (Sem digitar)")
                    time.sleep(delay_entre_ciclos)
                    continue

                palavra_para_digitar = escolher_palavra(palavras_filtradas, criterio)

                if palavra_para_digitar:
                    if palavra_para_digitar in blacklist:
                        contador_blacklist += 1

                    palavras_processadas.append(palavra_para_digitar)
                    append_terminal(f"A palavra '{palavra_para_digitar}' foi escolhida para digitação.")
                    atualizar_estatisticas_ui(ultima_palavra=palavra_para_digitar)

                    pyautogui.click(x=posicao_mouse_chatbox[0], y=posicao_mouse_chatbox[1])
                    time.sleep(delay_antes_digitar)

                    # Aplicar o modo de velocidade antes de digitar a palavra
                    aplicar_modo_velocidade()

                    digitar_palavra(palavra_para_digitar)

                    if modo_selecionado == 'alfabeto':
                        letras_usadas.update(set(palavra_para_digitar) - letras_ignoradas)
                        if len(letras_usadas) >= 23:
                            alfabeto_completado += 1
                            append_terminal(f"Alfabeto completado {alfabeto_completado} vez(es)!")
                            letras_usadas.clear()
                            atualizar_estatisticas_ui()
        time.sleep(delay_entre_ciclos)

def iniciar():
    global executando
    executando = True
    status_label.config(text="Status: Rodando", fg="green")
    thread = Thread(target=main)
    thread.start()

def parar():
    global executando
    executando = False
    status_label.config(text="Status: Parado", fg="red")
    append_terminal("Processo parado.")

def selecionar_modo(modo: str):
    global modo_selecionado, modo_alfabetico
    modo_selecionado = modo
    modo_alfabetico = (modo == 'alfabetico')
    modo_label.config(text=f"Modo Selecionado: {modo.capitalize()}")
    append_terminal(f"Modo selecionado: {modo}")

def alternar_inserir_numeros():
    global inserir_numeros
    inserir_numeros = not inserir_numeros
    estado = "ligado" if inserir_numeros else "desligado"
    append_terminal(f"Inserir números aleatórios: {estado}")

def fechar_programa():
    root.destroy()

def monitorar_tecla_f8():
    while True:
        if keyboard.is_pressed('F8'):
            parar()
            break
        time.sleep(0.1)

def capturar_posicao_mouse(callback):
    def on_click(x, y, button, pressed):
        if pressed:
            callback(x, y)
            return False
    listener_thread = Thread(target=lambda: mouse.Listener(on_click=on_click).start())
    listener_thread.start()

def atualizar_posicao_letras():
    append_terminal("Clique para definir a nova posição para copiar as letras...")
    capturar_posicao_mouse(atualizar_posicao_letras_callback)

def atualizar_posicao_letras_callback(x, y):
    global posicao_mouse_letras
    posicao_mouse_letras = (x, y)
    append_terminal(f"Posição do mouse para copiar letras atualizada para: {posicao_mouse_letras}")

def atualizar_posicao_chatbox():
    append_terminal("Clique para definir a nova posição da chatbox...")
    capturar_posicao_mouse(atualizar_posicao_chatbox_callback)

def atualizar_posicao_chatbox_callback(x, y):
    global posicao_mouse_chatbox
    posicao_mouse_chatbox = (x, y)
    append_terminal(f"Posição do mouse para clicar na chatbox atualizada para: {posicao_mouse_chatbox}")

def aplicar_texto_desenvolvedor(parent):
    label_texto = tk.Label(parent, text="Desenvolvedor: @lucasleao18", font=('Arial', 10))
    label_texto.place(relx=1.0, rely=1.0, anchor='se')

    def mudar_cor():
        r = lambda: random.randint(0, 255)
        cor = f'#{r():02x}{r():02x}{r():02x}'
        label_texto.config(fg=cor)
        parent.after(500, mudar_cor)
    mudar_cor()

def alterar_caminho_dicionario():
    global caminho_dicionario
    caminho_dicionario = dicionario_entry.get().strip()
    append_terminal(f"Caminho do dicionário atualizado: {caminho_dicionario}")

def recarregar_dicionario():
    global palavras_dicionario, palavras_processadas
    palavras_dicionario.clear()
    palavras_processadas.clear()
    dicionario = carregar_dicionario_func(caminho_dicionario)
    if dicionario:
        palavras_dicionario.extend(dicionario)
        append_terminal("Dicionário recarregado com sucesso.")
    else:
        append_terminal("Falha ao recarregar dicionário. Verifique o caminho.")
    atualizar_estatisticas_ui()

def limpar_historico():
    global palavras_processadas
    palavras_processadas.clear()
    append_terminal("Histórico de palavras processadas limpo.")
    atualizar_estatisticas_ui()

def alternar_modo_teste():
    global modo_teste
    modo_teste = not modo_teste
    estado = "ativado" if modo_teste else "desativado"
    append_terminal(f"Modo teste {estado}.")

def alternar_modo_debug():
    global modo_debug_log
    modo_debug_log = not modo_debug_log
    estado = "ativado" if modo_debug_log else "desativado"
    append_terminal(f"Modo debug (log em arquivo) {estado}.")

def atualizar_delays():
    global delay_entre_ciclos, delay_captura_letras, delay_entre_letras, delay_antes_digitar
    delay_entre_ciclos = slider_delay_ciclos.get() / 1000.0
    delay_captura_letras = slider_delay_captura.get() / 1000.0
    delay_entre_letras = slider_delay_dig_letras.get() / 1000.0
    delay_antes_digitar = slider_delay_antes_digitar.get() / 1000.0
    append_terminal("Delays atualizados.")

def atualizar_estatisticas_ui(ultima_palavra=None):
    count_palavras = len(palavras_processadas)
    stat_palavras_label.config(text=f"Total de Palavras Digitadas: {count_palavras}")
    stat_alfabeto_label.config(text=f"Alfabetos Completos (modo alfabeto): {alfabeto_completado}")
    if ultima_palavra is not None:
        stat_ultima_palavra_label.config(text=f"Última Palavra: {ultima_palavra}")
    total_dict = len(palavras_dicionario)
    stat_total_dict_label.config(text=f"Total de Palavras no Dicionário: {total_dict}")
    stat_blacklist_label.config(text=f"Palavras Ignoradas pela Blacklist: {contador_blacklist}")
    stat_modos_label.config(text=f"Usos por modo: {usos_por_modo}")

def mostrar_historico_completo():
    hist_window = Toplevel(root)
    hist_window.title("Histórico Completo de Palavras Digitadas")

    texto = scrolledtext.ScrolledText(hist_window, wrap=tk.WORD)
    texto.pack(expand=1, fill='both')
    for p in palavras_processadas:
        t = freq_usage.get(p, 0)
        texto.insert(tk.END, f"{datetime.datetime.now()} - {p} (usada {t}x)\n")

def alternar_erro_variacao():
    global erro_variacao_ativo
    erro_variacao_ativo = not erro_variacao_ativo
    estado = "ativado" if erro_variacao_ativo else "desativado"
    append_terminal(f"Erros e Variação de Delay {estado}.")

def atualizar_erros_config():
    global chance_erro_val, delay_variacao_val, letras_erradas_val
    chance_erro_val = slider_chance_erro.get() / 100.0
    delay_variacao_val = slider_delay_var.get() / 1000.0
    letras_erradas_val = entry_letras_erradas.get().strip()
    append_terminal("Configurações de erros atualizadas.")

def definir_velocidade():
    global modo_velocidade
    modo_velocidade = var_velocidade.get()
    # Atualiza label ao lado de cada opção
    lbl_rapida.config(text="Selecionado" if modo_velocidade == 1 else "")
    lbl_aleatoria.config(text="Selecionado" if modo_velocidade == 2 else "")
    lbl_gradual.config(text="Selecionado" if modo_velocidade == 3 else "")
    append_terminal(f"Modo de velocidade definido: {('Rápida' if modo_velocidade==1 else 'Aleatória' if modo_velocidade==2 else 'Gradual' if modo_velocidade==3 else 'Nenhum')}")

# -----------------------------------------------------------
# Interface Gráfica
# -----------------------------------------------------------
root = tk.Tk()
root.title("Automação de Palavras")
root.geometry("900x850")
root.attributes('-topmost', True)

menubar = Menu(root)
root.config(menu=menubar)

filemenu = Menu(menubar, tearoff=0)
filemenu.add_command(label="Salvar Posições", command=salvar_posicoes)
filemenu.add_command(label="Recarregar Dicionário", command=recarregar_dicionario)
filemenu.add_command(label="Limpar Histórico", command=limpar_historico)
filemenu.add_separator()
filemenu.add_command(label="Fechar", command=fechar_programa)
menubar.add_cascade(label="Ações", menu=filemenu)

tab_control = ttk.Notebook(root)
tab_control.pack(expand=1, fill='both')

tab1 = ttk.Frame(tab_control)  # Principal
tab2 = ttk.Frame(tab_control)  # Terminal
tab3 = ttk.Frame(tab_control)  # Setup
tab4 = ttk.Frame(tab_control)  # Estatísticas
tab5 = ttk.Frame(tab_control)  # Config Erros

tab_control.add(tab1, text='Principal')
tab_control.add(tab2, text='Terminal')
tab_control.add(tab3, text='Setup')
tab_control.add(tab4, text='Estatísticas')
tab_control.add(tab5, text='Config Erros')

button_font = ('Arial', 14)
button_width = 25

# Aba Principal
tk.Button(tab1, text="Palavras Longas", font=button_font, width=button_width, command=lambda: selecionar_modo('longa')).pack(pady=5)
tk.Button(tab1, text="Palavras Curtas", font=button_font, width=button_width, command=lambda: selecionar_modo('curta')).pack(pady=5)
tk.Button(tab1, text="Qualquer Palavra", font=button_font, width=button_width, command=lambda: selecionar_modo('qualquer')).pack(pady=5)
tk.Button(tab1, text="Modo Alfabeto", font=button_font, width=button_width, command=lambda: selecionar_modo('alfabeto')).pack(pady=5)
tk.Button(tab1, text="Modo Alfabético (A-Z)", font=button_font, width=button_width, command=lambda: selecionar_modo('alfabetico')).pack(pady=5)

checkbox_var = tk.IntVar()
tk.Checkbutton(tab1, text="Inserir números aleatórios", font=button_font, variable=checkbox_var, command=alternar_inserir_numeros).pack(pady=5)

checkbox_erro_var = tk.IntVar()
tk.Checkbutton(tab1, text="Ativar Erros e Variação de Delay", font=button_font, variable=checkbox_erro_var, command=alternar_erro_variacao).pack(pady=5)

# Radiobuttons para modos de velocidade
frame_velocidade = tk.Frame(tab1)
frame_velocidade.pack(pady=10)

var_velocidade = tk.IntVar(value=0)

tk.Radiobutton(frame_velocidade, text="Velocidade Rápida", font=button_font, variable=var_velocidade, value=1, command=definir_velocidade).grid(row=0, column=0, padx=5)
lbl_rapida = tk.Label(frame_velocidade, text="", font=button_font, fg="blue")
lbl_rapida.grid(row=0, column=1, padx=5)

tk.Radiobutton(frame_velocidade, text="Velocidade Aleatória", font=button_font, variable=var_velocidade, value=2, command=definir_velocidade).grid(row=1, column=0, padx=5)
lbl_aleatoria = tk.Label(frame_velocidade, text="", font=button_font, fg="blue")
lbl_aleatoria.grid(row=1, column=1, padx=5)

tk.Radiobutton(frame_velocidade, text="Velocidade Gradual", font=button_font, variable=var_velocidade, value=3, command=definir_velocidade).grid(row=2, column=0, padx=5)
lbl_gradual = tk.Label(frame_velocidade, text="", font=button_font, fg="blue")
lbl_gradual.grid(row=2, column=1, padx=5)

tk.Button(tab1, text="Iniciar", font=button_font, width=button_width, bg='green', fg='white', command=iniciar).pack(pady=10)
tk.Button(tab1, text="Parar (F8)", font=button_font, width=button_width, bg='red', fg='white', command=parar).pack(pady=10)

status_label = tk.Label(tab1, text="Status: Parado", font=button_font, fg="red")
status_label.pack(pady=5)

modo_label = tk.Label(tab1, text="Modo Selecionado: Nenhum", font=button_font)
modo_label.pack(pady=5)

tk.Button(tab1, text="Fechar", font=('Arial', 12), width=10, command=fechar_programa).pack(pady=5)

# Aba Terminal
terminal_textbox = scrolledtext.ScrolledText(tab2, state=tk.DISABLED, wrap=tk.WORD)
terminal_textbox.pack(expand=1, fill='both')

# Aba Setup
setup_font = ('Arial', 12)

tk.Label(tab3, text="Caminho do Dicionário:", font=setup_font).pack(pady=5)
dicionario_entry = tk.Entry(tab3, font=setup_font, width=50)
dicionario_entry.insert(0, caminho_dicionario)
dicionario_entry.pack(pady=5)
tk.Button(tab3, text="Alterar Caminho", font=setup_font, command=alterar_caminho_dicionario).pack(pady=5)
tk.Button(tab3, text="Recarregar Dicionário", font=setup_font, command=recarregar_dicionario).pack(pady=5)
tk.Button(tab3, text="Limpar Histórico", font=setup_font, command=limpar_historico).pack(pady=5)

tk.Button(tab3, text="Alternar Modo Teste", font=setup_font, command=alternar_modo_teste).pack(pady=5)
tk.Button(tab3, text="Alternar Modo Debug", font=setup_font, command=alternar_modo_debug).pack(pady=5)

tk.Button(tab3, text="Atualizar Posição para Copiar Letras", font=setup_font, command=atualizar_posicao_letras).pack(pady=5)
tk.Button(tab3, text="Atualizar Posição da Chatbox", font=setup_font, command=atualizar_posicao_chatbox).pack(pady=5)
tk.Button(tab3, text="Salvar Posições", font=setup_font, command=salvar_posicoes).pack(pady=5)

tk.Label(tab3, text="Delay entre ciclos (ms):", font=setup_font).pack(pady=2)
slider_delay_ciclos = tk.Scale(tab3, from_=100, to=1000, orient='horizontal')
slider_delay_ciclos.set(int(delay_entre_ciclos*1000))
slider_delay_ciclos.pack(pady=2)

tk.Label(tab3, text="Delay após capturar letras (ms):", font=setup_font).pack(pady=2)
slider_delay_captura = tk.Scale(tab3, from_=100, to=1000, orient='horizontal')
slider_delay_captura.set(int(delay_captura_letras*1000))
slider_delay_captura.pack(pady=2)

tk.Label(tab3, text="Delay entre letras digitadas (ms):", font=setup_font).pack(pady=2)
slider_delay_dig_letras = tk.Scale(tab3, from_=1, to=100, orient='horizontal')
slider_delay_dig_letras.set(int(delay_entre_letras*1000))
slider_delay_dig_letras.pack(pady=2)

tk.Label(tab3, text="Delay antes de digitar a palavra (ms):", font=setup_font).pack(pady=2)
slider_delay_antes_digitar = tk.Scale(tab3, from_=100, to=1000, orient='horizontal')
slider_delay_antes_digitar.set(int(delay_antes_digitar*1000))
slider_delay_antes_digitar.pack(pady=2)

tk.Button(tab3, text="Atualizar Delays", font=setup_font, command=atualizar_delays).pack(pady=10)

# Aba Estatísticas
stat_palavras_label = tk.Label(tab4, text="Total de Palavras Digitadas: 0", font=setup_font)
stat_palavras_label.pack(pady=5)

stat_alfabeto_label = tk.Label(tab4, text="Alfabetos Completos (modo alfabeto): 0", font=setup_font)
stat_alfabeto_label.pack(pady=5)

stat_ultima_palavra_label = tk.Label(tab4, text="Última Palavra: Nenhuma", font=setup_font)
stat_ultima_palavra_label.pack(pady=5)

stat_total_dict_label = tk.Label(tab4, text="Total de Palavras no Dicionário: 0", font=setup_font)
stat_total_dict_label.pack(pady=5)

stat_blacklist_label = tk.Label(tab4, text="Palavras Ignoradas pela Blacklist: 0", font=setup_font)
stat_blacklist_label.pack(pady=5)

stat_modos_label = tk.Label(tab4, text="Usos por modo: {}", font=setup_font)
stat_modos_label.pack(pady=5)

tk.Button(tab4, text="Mostrar Histórico Completo", font=setup_font, command=mostrar_historico_completo).pack(pady=5)

# Aba Config Erros
tk.Label(tab5, text="Chance de Erro (%):", font=setup_font).pack(pady=5)
slider_chance_erro = tk.Scale(tab5, from_=0, to=100, orient='horizontal')
slider_chance_erro.set(int(chance_erro_val*100))
slider_chance_erro.pack(pady=5)

tk.Label(tab5, text="Variação de Delay (ms):", font=setup_font).pack(pady=5)
slider_delay_var = tk.Scale(tab5, from_=0, to=50, orient='horizontal')
slider_delay_var.set(int(delay_variacao_val*1000))
slider_delay_var.pack(pady=5)

tk.Label(tab5, text="Letras Erradas Possíveis:", font=setup_font).pack(pady=5)
entry_letras_erradas = tk.Entry(tab5, font=setup_font, width=50)
entry_letras_erradas.insert(0, letras_erradas_val)
entry_letras_erradas.pack(pady=5)

tk.Button(tab5, text="Atualizar Config Erros", font=setup_font, command=atualizar_erros_config).pack(pady=10)

aplicar_texto_desenvolvedor(tab1)
aplicar_texto_desenvolvedor(tab2)
aplicar_texto_desenvolvedor(tab3)
aplicar_texto_desenvolvedor(tab4)
aplicar_texto_desenvolvedor(tab5)

Thread(target=monitorar_tecla_f8, daemon=True).start()
carregar_posicoes()

root.mainloop()
