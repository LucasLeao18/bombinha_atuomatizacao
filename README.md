# Automação de Palavras com Interface Gráfica JKLM

Este projeto é uma aplicação em Python que automatiza a digitação de palavras com base em letras capturadas de uma tela. A aplicação permite escolher entre diferentes modos de operação, adicionar números aleatórios durante a digitação, e controlar a execução através de uma interface gráfica.

## Funcionalidades

- **Captura de Letras:** O programa captura as letras na tela usando uma automação de mouse e copia para o clipboard para processar as palavras.
- **Modos de Operação:**
  - **Palavras Longas:** O programa seleciona as palavras mais longas possíveis.
  - **Palavras Curtas:** O programa seleciona as palavras mais curtas possíveis.
  - **Qualquer Palavra:** O programa seleciona qualquer palavra disponível.
  - **Modo Alfabeto:** O programa tenta completar o alfabeto com as palavras selecionadas, ignorando as letras Y, K, e W.
- **Inserção de Números Aleatórios:** Quando ativado, o programa insere números aleatórios entre as letras durante a digitação.
- **Interface Gráfica:** A aplicação possui uma interface gráfica com botões para selecionar o modo de operação, iniciar, parar e fechar o programa.
- **Indicador de Status:** A interface mostra o status atual do programa (Rodando ou Parado).
- **Atalho F8:** O programa pode ser parado pressionando a tecla F8.

## Requisitos

- Python 3.x
- Bibliotecas Python:
  - `cv2` (OpenCV)
  - `numpy`
  - `PIL` (Pillow)
  - `pyautogui`
  - `pyperclip`
  - `tkinter` (incluído no Python)

## Instalação

1. Clone este repositório para sua máquina local.
2. Instale as dependências necessárias utilizando pip:
    ```bash
    pip install opencv-python-headless numpy pillow pyautogui pyperclip
    ```
3. Execute o script Python:
    ```bash
    python nome_do_seu_script.py
    ```

## Como Usar

1. **Interface Gráfica:**
   - Selecione um dos modos de operação clicando em um dos botões: "Palavras Longas", "Palavras Curtas", "Qualquer Palavra" ou "Modo Alfabeto".
   - (Opcional) Marque a opção "Inserir números aleatórios" se desejar adicionar números aleatórios durante a digitação.
   - Clique em "Iniciar" para começar o processo de automação.
   - O status do programa será mostrado na interface (Rodando ou Parado).
   - Pressione "Parar (F8)" ou a tecla F8 no teclado para interromper o processo.
   - Clique em "Fechar" para sair do programa.

2. **Processo de Automação:**
   - O programa irá detectar a presença de uma chatbox na tela.
   - Em seguida, capturará as letras visíveis na tela, processará e digitará a palavra correspondente.
   - Durante o modo "Alfabeto", o programa tentará formar palavras que utilizem o máximo de letras diferentes do alfabeto, exceto Y, K, e W.
   - Números aleatórios serão inseridos entre as letras durante a digitação se a opção estiver ativada.



## Créditos

Este projeto foi desenvolvido por Lucas Leão.
Github: @lucasleao18
