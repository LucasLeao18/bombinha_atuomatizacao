import pyperclip
import time

palavras_processadas = []
letras_anteriores = ''

while True:
    # Aguardamos um tempo para a próxima verificação do clipboard
    time.sleep(1)

    # Pegamos o conteúdo do clipboard e transformamos em minúsculas
    letras = pyperclip.paste().strip().lower()

    # Verificamos se o conteúdo é diferente da palavra anteriormente copiada
    if letras != '' and letras != letras_anteriores:
        letras_anteriores = letras

        with open('acento.txt', 'r') as arquivo:
            dicionario = [palavra.strip() for palavra in arquivo if len(palavra.strip()) > 5 and letras in palavra]

        palavras_ordenadas = sorted(dicionario, key=len, reverse=True)
        cinco_palavras_longas = palavras_ordenadas[:5]

        palavra_para_copiar = None

        for palavra in cinco_palavras_longas:
            if palavra not in palavras_processadas:
                palavra_para_copiar = palavra
                break

        if palavra_para_copiar:
            palavras_processadas.append(palavra_para_copiar)
            pyperclip.copy(palavra_para_copiar)
            print('A palavra', palavra_para_copiar, 'foi copiada para a área de transferência.')
        else:
            print('Não foram encontradas palavras que atendam aos critérios.')
