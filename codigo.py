import cv2
import numpy as np
from PIL import ImageGrab
import pyautogui
import time
import re
import pyperclip  # Para acessar o clipboard
import tkinter as tk
from threading import Thread

# Conjunto de letras ignoradas no Modo Alfabeto
letras_ignoradas = {'y', 'k', 'w'}

# Variáveis globais
modo_selecionado = None
executando = False

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
    pyautogui.doubleClick(x=692, y=594)
    time.sleep(0.5)  # Pequeno delay para garantir que o texto seja selecionado

    # Copia o texto para o clipboard
    pyautogui.hotkey('ctrl', 'c')
    time.sleep(0.5)  # Delay para garantir que o texto seja copiado

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
    with open(caminho_arquivo, 'r') as arquivo:
        return [palavra.strip().lower() for palavra in arquivo if len(palavra.strip()) > 5]

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

# Função para digitar a palavra
def digitar_palavra(palavra):
    for letra in palavra:
        pyautogui.typewrite(letra)
        time.sleep(0.001)  # Atraso reduzido para 0.001 segundos para digitação mais rápida
    pyautogui.press('enter')

# Função principal que une todos os componentes
def main():
    global modo_selecionado, executando
    
    if not modo_selecionado:
        print("Nenhum modo selecionado!")
        return

    print(f"Iniciando no modo: {modo_selecionado}")
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
            print("Chatbox detectada, é a sua vez de jogar!")

            # Captura as letras na tela
            letras_detectadas = capturar_letras_mouse()
            print(f"Letras detectadas: {letras_detectadas}")  # Imprime as letras detectadas

            if letras_detectadas != '':
                palavras_filtradas = filtrar_palavras(palavras_dicionario, letras_detectadas)
                palavra_para_digitar = escolher_palavra(palavras_filtradas, palavras_processadas, modo_selecionado, letras_usadas)

                if palavra_para_digitar:
                    palavras_processadas.append(palavra_para_digitar)
                    print(f"A palavra '{palavra_para_digitar}' foi escolhida para digitação.")

                    # Clica na chatbox antes de digitar
                    pyautogui.click(x=838, y=953)
                    time.sleep(0.3)  # Espera de 0.3 segundos antes de começar a digitar

                    digitar_palavra(palavra_para_digitar)
                    
                    # Atualiza as letras usadas no Modo Alfabeto
                    if modo_selecionado == 'alfabeto':
                        letras_usadas.update(set(palavra_para_digitar) - letras_ignoradas)
                        if len(letras_usadas) >= 23:  # Se o alfabeto completo for usado, considerando 23 letras
                            alfabeto_completado += 1
                            print(f"Alfabeto completado {alfabeto_completado} vez(es)!")
                            letras_usadas.clear()  # Reinicia a contagem das letras usadas

        time.sleep(0.5)

# Função para iniciar o processo
def iniciar():
    global executando
    executando = True
    thread = Thread(target=main)
    thread.start()

# Função para parar o processo
def parar():
    global executando
    executando = False
    print("Processo parado.")

# Função para selecionar o modo
def selecionar_modo(modo):
    global modo_selecionado
    modo_selecionado = modo
    print(f"Modo selecionado: {modo}")

# Interface gráfica com tkinter
root = tk.Tk()
root.title("Automação de Palavras")

# Botões de seleção de modos
tk.Button(root, text="Palavras Longas", command=lambda: selecionar_modo('longa')).pack(pady=5)
tk.Button(root, text="Palavras Curtas", command=lambda: selecionar_modo('curta')).pack(pady=5)
tk.Button(root, text="Qualquer Palavra", command=lambda: selecionar_modo('qualquer')).pack(pady=5)
tk.Button(root, text="Modo Alfabeto", command=lambda: selecionar_modo('alfabeto')).pack(pady=5)

# Botões de controle
tk.Button(root, text="Iniciar", command=iniciar).pack(pady=20)
tk.Button(root, text="Parar", command=parar).pack(pady=5)

# Execução da interface gráfica
root.mainloop()
