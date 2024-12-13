Automação de Palavras para Jogos Online
Este projeto é uma ferramenta de automação para digitação de palavras em jogos online, simulando um comportamento humano. O software captura letras exibidas na tela, escolhe uma palavra adequada de um dicionário e digita no chat do jogo, podendo simular erros de digitação e variação de velocidade.

Funcionalidades
Modos de Seleção de Palavras:

Palavras Longas
Palavras Curtas
Qualquer Palavra
Modo Alfabeto (foco em completar o alfabeto)
Modo Alfabético (ordem A-Z)
Modos de Velocidade de Digitação:

Velocidade Rápida: Digita com o menor delay possível.
Velocidade Aleatória: Aplica um delay aleatório entre cada palavra.
Velocidade Gradual: A cada palavra digitada, a velocidade aumenta (diminui o delay entre letras).
Simulação de Erros e Variação de Tempo (opcional):

Pode digitar letras erradas ocasionalmente e depois corrigi-las, simulando um humano cometendo erros.
Ajuste da porcentagem de erro, variação de delay entre letras e quais letras podem ser digitadas incorretamente.
Inserção Opcional de Números:

Pode inserir dígitos aleatórios entre as letras, tornando a digitação ainda menos "robótica".
Detecção Automática da Chatbox:

O programa busca a área do chat na tela e aguarda sua vez de jogar.
Interface Gráfica Completa (Tkinter):

Aba Principal: Seleção de modo, velocidade, inserção de erros, iniciar/parar.
Aba Terminal: Visualizar logs e mensagens do programa.
Aba Setup: Configurar caminhos, delays, posição do mouse, modo teste, modo debug.
Aba Estatísticas: Exibir informações sobre número de palavras digitadas, usos por modo, últimas palavras, quantas foram ignoradas pela blacklist.
Aba Config Erros: Ajustar chance de erro, variação de delay, letras erradas possíveis.
Blacklist de Palavras:

Arquivo blacklist.txt com palavras que não devem ser usadas pelo programa.
Registro de Log em Arquivo (opcional):

Pode ativar modo debug para logar ações em log.txt.
Suporte a Parar a Execução Com Tecla F8:

Permite interromper a automação rapidamente.
Requisitos
Python 3.x
Bibliotecas Python: cv2 (OpenCV), numpy, PIL, pyautogui, pyperclip, keyboard, pynput, tkinter (geralmente incluso por padrão), json, random, re, time, threading.
Dicionário de palavras (arquivo texto), ex: acento.txt.
Opcional: blacklist.txt para palavras a serem ignoradas.
Instalação
Clone ou baixe este repositório.
Instale as dependências, por exemplo:
bash
Copiar código
pip install opencv-python numpy pyautogui pyperclip keyboard pynput Pillow
Certifique-se que o arquivo acento.txt (ou outro dicionário) esteja no mesmo diretório do script principal.
Uso
Execute o script principal:

bash
Copiar código
python automacao.py
A janela principal será exibida. Selecione o modo de palavras desejado na aba Principal.

Ajuste as configurações de velocidade (Rápida, Aleatória, Gradual), insira números aleatórios (opcional), ative/desative erros e variações.

Clique em "Iniciar" para começar a automação.

O programa detectará a chatbox na tela (use a opção "Atualizar Posição da Chatbox" no Setup se necessário) e aguardará sua vez de jogar.

Quando as letras forem exibidas no jogo, o script capturará, escolherá uma palavra do dicionário e digitará automaticamente.

Para parar a execução, pressione o botão "Parar (F8)" ou use a tecla F8 do teclado.

Ajustes e Personalizações
Use a aba "Setup" para ajustar delays e caminhos do dicionário.
Use a aba "Config Erros" para detalhar o comportamento de erros de digitação.
Edite blacklist.txt para adicionar palavras que não devem ser usadas.
Dicas
Mantenha a janela do jogo em primeiro plano.
Ajuste as posições do mouse para captura de letras e clique na chatbox se o padrão não funcionar.
Teste primeiro com o "Modo Teste" ativado, para garantir que a configuração está correta antes de digitar no jogo real.
Contribuição
Sinta-se livre para contribuir com melhorias, correções de bugs ou novas funcionalidades por meio de pull requests.

Licença
Este projeto é fornecido "como está", sem garantias. Verifique a licença associada ao repositório (se fornecida).

Esse README oferece uma visão geral do projeto, descrevendo como ele funciona, como usá-lo, e quais opções estão disponíveis. Ajuste conforme necessário para o seu contexto.