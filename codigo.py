import cv2
import numpy as np
from PIL import ImageGrab
import pyautogui
import time
import re
import pyperclip  # Para acessar o clipboard
import tkinter as tk
from tkinter import ttk, scrolledtext
from threading import Thread
import random
import keyboard  # Biblioteca para capturar eventos de teclado globalmente
from pynput import mouse  # Para capturar cliques do mouse
import json  # Para salvar e carregar as posições do mouse

# Conjunto de letras ignoradas no Modo Alfabeto
letras_ignoradas = {'y', 'k', 'w'}

# Variáveis globais
modo_selecionado = None
executando = False
inserir_numeros = False  # Variável para controle da inserção de números aleatórios
posicao_mouse_letras = (692, 594)  # Posição inicial do mouse para copiar as letras
posicao_mouse_chatbox = (838, 953)  # Posição inicial do clique na chatbox

# Função para carregar as posições do mouse de um arquivo
def carregar_posicoes():
    global posicao_mouse_letras, posicao_mouse_chatbox
    try:
        with open('posicoes.json', 'r') as file:
            posicoes = json.load(file)
            posicao_mouse_letras = tuple(posicoes['letras'])
            posicao_mouse_chatbox = tuple(posicoes['chatbox'])
            append_terminal("Posições carregadas com sucesso.")
    except (FileNotFoundError, KeyError):
        append_terminal("Nenhuma posição salva encontrada, usando valores padrão.")

# Função para salvar as posições do mouse em um arquivo
def salvar_posicoes():
    posicoes = {
        'letras': posicao_mouse_letras,
        'chatbox': posicao_mouse_chatbox
    }
    with open('posicoes.json', 'w') as file:
        json.dump(posicoes, file)
    append_terminal("Posições salvas com sucesso.")

# Função para detectar a chatbox na tela
def detectar_chatbox(image_path='chatbox.png', threshold=0.8):
    screen = np.array(ImageGrab.grab())
    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)

    template = cv2.imread(image_path, 0)
    w, h = template.shape[::-1]

    res = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
    loc = np.where(res >= threshold)

    if len(loc[0]) > 0:
        for pt in zip(*loc[::-1]):
            return pt  # Retorna a posição da chatbox encontrada
    return None

# Função para capturar letras usando automação do mouse e clipboard
def capturar_letras_mouse():
    # Realiza o duplo clique na posição especificada
    pyautogui.doubleClick(x=posicao_mouse_letras[0], y=posicao_mouse_letras[1])
    time.sleep(0.3)  # Reduzindo o delay para garantir que o texto seja selecionado

    # Copia o texto para o clipboard
    pyautogui.hotkey('ctrl', 'c')
    time.sleep(0.3)  # Reduzindo o delay para garantir que o texto seja copiado

    # Obtém o texto do clipboard
    letras = pyperclip.paste()

    # Filtrar a string para manter apenas letras (A-Z, a-z)
    letras_somente = re.sub(r'[^A-Za-z]', '', letras)
    
    # Converter para minúsculas
    letras_minusculas = letras_somente.lower()
    
    return letras_minusculas.strip()

# Função para processar a palavra com base nas letras capturadas
def processar_palavra(letras):
    return letras  # Simplesmente retornando as letras capturadas como exemplo

# Função para carregar o dicionário de palavras
def carregar_dicionario(caminho_arquivo):
    with open(caminho_arquivo, 'r', encoding='utf-8') as arquivo:
        return [palavra.strip().lower() for palavra in arquivo if len(palavra.strip()) > 0]

# Função para filtrar palavras que contêm uma sequência específica de letras
def filtrar_palavras(palavras, letras):
    return [palavra for palavra in palavras if letras in palavra]

# Função para escolher a palavra de acordo com o critério escolhido (longa, curta, qualquer, ou alfabeto)
def escolher_palavra(palavras, palavras_processadas, criterio='longa', letras_usadas=set()):
    if criterio == 'curta':
        palavras_ordenadas = sorted(palavras, key=len)  # Ordena da mais curta para a mais longa
    elif criterio == 'alfabeto':
        palavras_ordenadas = sorted(
            [palavra for palavra in palavras if not any(letra in letras_ignoradas for letra in palavra)],
            key=lambda palavra: len(set(palavra) - letras_usadas),
            reverse=True
        )  # Maximiza letras únicas sem usar Y, K, W
    else:
        palavras_ordenadas = sorted(palavras, key=len, reverse=True)  # Ordena da mais longa para a mais curta
    
    for palavra in palavras_ordenadas:
        if palavra not in palavras_processadas:
            return palavra
    return None

# Função para digitar a palavra, possivelmente com números aleatórios
def digitar_palavra(palavra):
    global inserir_numeros
    for letra in palavra:
        pyautogui.typewrite(letra)
        if inserir_numeros and random.choice([True, False]):
            numero_aleatorio = str(random.randint(0, 9))
            pyautogui.typewrite(numero_aleatorio)
        time.sleep(0.001)  # Atraso reduzido para 0.001 segundos para digitação mais rápida
    pyautogui.press('enter')

# Função principal que une todos os componentes
def main():
    global modo_selecionado, executando
    
    if not modo_selecionado:
        append_terminal("Nenhum modo selecionado!")
        return

    append_terminal(f"Iniciando no modo: {modo_selecionado}")
    caminho_dicionario = 'acento.txt'
    palavras_dicionario = carregar_dicionario(caminho_dicionario)
    palavras_processadas = []
    letras_anteriores = ''
    letras_detectadas = ''  # Variável para armazenar as letras detectadas
    letras_usadas = set() if modo_selecionado == 'alfabeto' else None
    alfabeto_completado = 0

    while executando:
        chatbox_position = detectar_chatbox('chatbox.png')  # Usando o nome da imagem 'chatbox.png'
        if chatbox_position:
            append_terminal("Chatbox detectada, é a sua vez de jogar!")

            # Captura as letras na tela
            letras_detectadas = capturar_letras_mouse()
            append_terminal(f"Letras detectadas: {letras_detectadas}")  # Imprime as letras detectadas

            if letras_detectadas != '':
                palavras_filtradas = filtrar_palavras(palavras_dicionario, letras_detectadas)
                palavra_para_digitar = escolher_palavra(palavras_filtradas, palavras_processadas, modo_selecionado, letras_usadas)

                if palavra_para_digitar:
                    palavras_processadas.append(palavra_para_digitar)
                    append_terminal(f"A palavra '{palavra_para_digitar}' foi escolhida para digitação.")

                    # Clica na chatbox antes de digitar
                    pyautogui.click(x=posicao_mouse_chatbox[0], y=posicao_mouse_chatbox[1])
                    time.sleep(0.3)  # Reduzindo o tempo de espera antes de digitar

                    digitar_palavra(palavra_para_digitar)
                    
                    # Atualiza as letras usadas no Modo Alfabeto
                    if modo_selecionado == 'alfabeto':
                        letras_usadas.update(set(palavra_para_digitar) - letras_ignoradas)
                        if len(letras_usadas) >= 23:  # Se o alfabeto completo for usado, considerando 23 letras
                            alfabeto_completado += 1
                            append_terminal(f"Alfabeto completado {alfabeto_completado} vez(es)!")
                            letras_usadas.clear()  # Reinicia a contagem das letras usadas

        time.sleep(0.2)  # Reduzindo o tempo de espera entre as execuções do loop

# Função para iniciar o processo
def iniciar():
    global executando
    executando = True
    status_label.config(text="Status: Rodando", fg="green")
    thread = Thread(target=main)
    thread.start()

# Função para parar o processo
def parar():
    global executando
    executando = False
    status_label.config(text="Status: Parado", fg="red")
    append_terminal("Processo parado.")

# Função para selecionar o modo
def selecionar_modo(modo):
    global modo_selecionado
    modo_selecionado = modo
    modo_label.config(text=f"Modo Selecionado: {modo.capitalize()}")
    append_terminal(f"Modo selecionado: {modo}")

# Função para alternar a inserção de números
def alternar_inserir_numeros():
    global inserir_numeros
    inserir_numeros = not inserir_numeros
    estado = "ligado" if inserir_numeros else "desligado"
    append_terminal(f"Inserir números aleatórios: {estado}")

# Função para fechar o programa
def fechar_programa():
    root.destroy()

# Função para parar o programa ao pressionar F8 (mesmo em segundo plano)
def monitorar_tecla_f8():
    while True:
        if keyboard.is_pressed('F8'):
            parar()
            break
        time.sleep(0.1)

# Função para adicionar texto ao terminal na interface
def append_terminal(text):
    terminal_textbox.config(state=tk.NORMAL)
    terminal_textbox.insert(tk.END, text + "\n")
    terminal_textbox.config(state=tk.DISABLED)
    terminal_textbox.yview(tk.END)

# Função para capturar a posição do mouse
def capturar_posicao_mouse(callback):
    def on_click(x, y, button, pressed):
        if pressed:
            callback(x, y)
            return False  # Para o listener após o primeiro clique

    listener_thread = Thread(target=lambda: mouse.Listener(on_click=on_click).start())
    listener_thread.start()

# Função para atualizar a posição do mouse para copiar as letras
def atualizar_posicao_letras():
    append_terminal("Clique para definir a nova posição para copiar as letras...")
    capturar_posicao_mouse(atualizar_posicao_letras_callback)

def atualizar_posicao_letras_callback(x, y):
    global posicao_mouse_letras
    posicao_mouse_letras = (x, y)
    append_terminal(f"Posição do mouse para copiar letras atualizada para: {posicao_mouse_letras}")

# Função para atualizar a posição do mouse para clicar na chatbox
def atualizar_posicao_chatbox():
    append_terminal("Clique para definir a nova posição da chatbox...")
    capturar_posicao_mouse(atualizar_posicao_chatbox_callback)

def atualizar_posicao_chatbox_callback(x, y):
    global posicao_mouse_chatbox
    posicao_mouse_chatbox = (x, y)
    append_terminal(f"Posição do mouse para clicar na chatbox atualizada para: {posicao_mouse_chatbox}")

# Interface gráfica com tkinter
root = tk.Tk()
root.title("Automação de Palavras")
root.geometry("600x650")  # Definindo o tamanho da janela
root.attributes('-topmost', True)  # Mantém a janela sempre no topo

# Adicionando abas
tab_control = ttk.Notebook(root)
tab_control.pack(expand=1, fill='both')

# Aba principal
tab1 = ttk.Frame(tab_control)
tab_control.add(tab1, text='Principal')

# Aba do terminal
tab2 = ttk.Frame(tab_control)
tab_control.add(tab2, text='Terminal')

# Aba de setup
tab3 = ttk.Frame(tab_control)
tab_control.add(tab3, text='Setup')

# Configuração da aba principal
# Botões de seleção de modos
button_font = ('Arial', 14)  # Definindo uma fonte maior para os botões
button_width = 25  # Largura dos botões

tk.Button(tab1, text="Palavras Longas", font=button_font, width=button_width, command=lambda: selecionar_modo('longa')).pack(pady=5)
tk.Button(tab1, text="Palavras Curtas", font=button_font, width=button_width, command=lambda: selecionar_modo('curta')).pack(pady=5)
tk.Button(tab1, text="Qualquer Palavra", font=button_font, width=button_width, command=lambda: selecionar_modo('qualquer')).pack(pady=5)
tk.Button(tab1, text="Modo Alfabeto", font=button_font, width=button_width, command=lambda: selecionar_modo('alfabeto')).pack(pady=5)

# Checkbox para inserir números aleatórios
checkbox_var = tk.IntVar()
tk.Checkbutton(tab1, text="Inserir números aleatórios", font=button_font, variable=checkbox_var, command=alternar_inserir_numeros).pack(pady=5)

# Botões de controle
tk.Button(tab1, text="Iniciar", font=button_font, width=button_width, bg='green', fg='white', command=iniciar).pack(pady=10)
tk.Button(tab1, text="Parar (F8)", font=button_font, width=button_width, bg='red', fg='white', command=parar).pack(pady=10)

# Indicador de status
status_label = tk.Label(tab1, text="Status: Parado", font=button_font, fg="red")
status_label.pack(pady=5)

# Indicador do modo selecionado
modo_label = tk.Label(tab1, text="Modo Selecionado: Nenhum", font=button_font)
modo_label.pack(pady=5)

# Botão para fechar o programa
tk.Button(tab1, text="Fechar", font=('Arial', 12), width=10, command=fechar_programa).pack(pady=5)

# Configuração da aba do terminal
terminal_textbox = scrolledtext.ScrolledText(tab2, state=tk.DISABLED, wrap=tk.WORD)
terminal_textbox.pack(expand=1, fill='both')

# Configuração da aba de setup
tk.Button(tab3, text="Atualizar Posição para Copiar Letras", font=button_font, command=atualizar_posicao_letras).pack(pady=10)
tk.Button(tab3, text="Atualizar Posição da Chatbox", font=button_font, command=atualizar_posicao_chatbox).pack(pady=10)
tk.Button(tab3, text="Salvar Posições", font=button_font, command=salvar_posicoes).pack(pady=10)

# Função para criar o texto de desenvolvedor com cores RGB rainbow
def aplicar_texto_desenvolvedor(parent):
    label_texto = tk.Label(parent, text="Desenvolvedor: @lucasleao18", font=('Arial', 10))
    label_texto.place(relx=1.0, rely=1.0, anchor='se')

    def mudar_cor():
        r = lambda: random.randint(0, 255)
        cor = f'#{r():02x}{r():02x}{r():02x}'
        label_texto.config(fg=cor)
        parent.after(500, mudar_cor)

    mudar_cor()

# Aplicando o texto de desenvolvedor em todas as abas
aplicar_texto_desenvolvedor(tab1)
aplicar_texto_desenvolvedor(tab2)
aplicar_texto_desenvolvedor(tab3)

# Inicia a thread para monitorar a tecla F8 em segundo plano
Thread(target=monitorar_tecla_f8, daemon=True).start()

# Carrega as posições do mouse
carregar_posicoes()

# Execução da interface gráfica
root.mainloop()
