import cv2
import numpy as np
import pytesseract
from PIL import ImageGrab, Image
import pyautogui
import time
import re

# Configuração do Tesseract OCR
pytesseract.pytesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'  # Caminho padrão para o executável do Tesseract

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

# Função para capturar letras na tela usando OCR sem pré-processamento e ignorar tudo exceto letras
def capturar_letras_ocr(bbox=(658, 558, 728, 618)):
    screen = np.array(ImageGrab.grab(bbox=bbox))
    screen_pil = Image.fromarray(screen)

    # Executando OCR diretamente na imagem capturada
    letras = pytesseract.image_to_string(screen_pil, config='--psm 7')  # Modo de página único texto horizontal

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

# Função para escolher a palavra de acordo com o critério escolhido (longa, curta ou qualquer)
def escolher_palavra(palavras, palavras_processadas, criterio='longa'):
    if criterio == 'curta':
        palavras_ordenadas = sorted(palavras, key=len)  # Ordena da mais curta para a mais longa
    else:
        palavras_ordenadas = sorted(palavras, key=len, reverse=True)  # Ordena da mais longa para a mais curta, ou não aplica filtro de tamanho
    
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
    print("Selecione uma opção:")
    print("1. Programa com palavras longas")
    print("2. Programa com palavras curtas")
    print("3. Programa com qualquer palavra")
    opcao = input("Digite o número da opção desejada: ")

    if opcao == '1':
        criterio = 'longa'
        print("Modo: Palavras Longas")
    elif opcao == '2':
        criterio = 'curta'
        print("Modo: Palavras Curtas")
    elif opcao == '3':
        criterio = 'qualquer'
        print("Modo: Qualquer Palavra")
    else:
        print("Opção inválida!")
        return

    print("Iniciando em 2 segundos...")
    time.sleep(2)

    caminho_dicionario = 'acento.txt'
    palavras_dicionario = carregar_dicionario(caminho_dicionario)
    palavras_processadas = []
    letras_anteriores = ''
    letras_detectadas = ''  # Variável para armazenar as letras detectadas

    while True:
        chatbox_position = detectar_chatbox('chatbox.png')  # Usando o nome da imagem 'chatbox.png'
        if chatbox_position:
            print("Chatbox detectada, é a sua vez de jogar!")

            # Clique na posição da chatbox onde a palavra será digitada
            pyautogui.click(x=838, y=953)
            time.sleep(0.5)  # Pequeno delay para garantir que a chatbox esteja ativa

            letras_detectadas = capturar_letras_ocr(bbox=(658, 558, 728, 618))
            print(f"Letras detectadas: {letras_detectadas}")  # Imprime as letras detectadas

            if letras_detectadas != '' and letras_detectadas != letras_anteriores:
                letras_anteriores = letras_detectadas
                palavras_filtradas = filtrar_palavras(palavras_dicionario, letras_detectadas)
                palavra_para_digitar = escolher_palavra(palavras_filtradas, palavras_processadas, criterio)

                if palavra_para_digitar:
                    palavras_processadas.append(palavra_para_digitar)
                    print(f"A palavra '{palavra_para_digitar}' foi escolhida para digitação.")
                    time.sleep(0.3)  # Espera de 0.3 segundos antes de começar a digitar
                    digitar_palavra(palavra_para_digitar)
                else:
                    print('Não foram encontradas palavras que atendam aos critérios.')

        time.sleep(0.5)

if __name__ == '__main__':
    main()
