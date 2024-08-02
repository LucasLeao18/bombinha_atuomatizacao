import pyperclip
import time
import pyautogui

# Carregar o dicionário de palavras
def carregar_dicionario(caminho_arquivo):
    with open(caminho_arquivo, 'r') as arquivo:
        return [palavra.strip().lower() for palavra in arquivo if len(palavra.strip()) > 5]

# Filtrar palavras que contêm uma sequência específica de letras
def filtrar_palavras(palavras, letras):
    return [palavra for palavra in palavras if letras in palavra]

# Escolher a palavra mais longa que ainda não foi processada
def escolher_palavra(palavras, palavras_processadas):
    for palavra in palavras:
        if palavra not in palavras_processadas:
            return palavra
    return None

# Função para digitar a palavra
def digitar_palavra(palavra):
    for letra in palavra:
        pyautogui.typewrite(letra)
        time.sleep(0.001)  # Atraso reduzido para 0.01 segundos para digitação mais rápida
    pyautogui.press('enter')

# Função principal
def main():
    # Pausa de 2 segundos no início
    print("Iniciando em 2 segundos...")
    time.sleep(2)
    
    caminho_dicionario = 'acento.txt'
    palavras_dicionario = carregar_dicionario(caminho_dicionario)
    palavras_processadas = []
    letras_anteriores = ''

    while True:
        time.sleep(1)
        
        # Pegamos o conteúdo do clipboard e transformamos em minúsculas
        letras = pyperclip.paste().strip().lower()

        # Verificamos se o conteúdo é diferente da palavra anteriormente copiada
        if letras != '' and letras != letras_anteriores:
            letras_anteriores = letras
            palavras_filtradas = filtrar_palavras(palavras_dicionario, letras)
            palavras_ordenadas = sorted(palavras_filtradas, key=len, reverse=True)
            palavra_para_copiar = escolher_palavra(palavras_ordenadas, palavras_processadas)

            if palavra_para_copiar:
                palavras_processadas.append(palavra_para_copiar)
                pyperclip.copy(palavra_para_copiar)
                print('A palavra', palavra_para_copiar, 'foi copiada para a área de transferência.')
                time.sleep(1)  # Espera de 1 segundo antes de começar a digitar
                digitar_palavra(palavra_para_copiar)
            else:
                print('Não foram encontradas palavras que atendam aos critérios.')

if __name__ == '__main__':
    main()