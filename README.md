# JKLM.fun Automacao PT-BR

Aplicacao desktop em Python para automatizar partidas no jogo JKLM.fun (modo Bomb Party), com interface Tkinter e comportamentos humanizados.

## Recursos
- Interface grafica completa para configuracoes e monitoramento em tempo real.
- Captura automatica das letras do turno e selecao inteligente de palavras usando dicionario.
- Modo alfabeto com rastreio de letras usadas, cooldown de repeticao e blacklist personalizada.
- Perfil de digitacao humanizado: erros simulados, pausas, ensaio, frases aleatorias e insercao de numeros.
- Verificacao visual da vez (barra de turno) antes do envio da palavra.
- Logs em arquivo opcionais e historico das palavras enviadas.

## Dependencias
- Python 3.10+
- Bibliotecas: `numpy`, `opencv-python`, `pyautogui`, `pynput`, `pyperclip`, `keyboard`, `Pillow`

Instale-as com:
```powershell
python -m pip install -r requirements.txt
```
(ou instale manualmente caso nao utilize arquivo de requisitos.)

## Arquivos principais
- `codigov4.py`: aplicacao principal com a GUI e logica do bot.
- `config.json`: configuracoes persistentes (auto-criado/atualizado).
- `posicoes.json`: posicoes de captura (letras, chatbox, retangulo da barra).
- `acento.txt`: dicionario base de palavras.
- `blacklist.txt`: lista opcional de palavras a ignorar (crie o arquivo se desejar).

## Como usar
1. Certifique-se de que a resolucao/escala do Windows corresponde a utilizada quando as coordenadas foram salvas.
2. Execute `python codigov4.py`.
3. Na aba **Setup**:
   - Aponte para o dicionario (`acento.txt`).
   - Ajuste as posicoes de letras e chatbox.
   - Capture o retangulo da barra de turno (clique canto superior esquerdo, depois inferior direito).
   - Ajuste thresholds, delays e demais opcoes conforme necessario.
4. Na aba **Principal**, escolha o modo de jogo e clique **Iniciar**.
5. Use `F8` como kill-switch rapido.

## Dicas de configuracao
- Threshold da barra: aumente se houver falsos negativos; reduza se detectar turnos alheios.
- Ative "Modo Teste" para revisar o fluxo sem enviar teclas.
- Utilize a aba **Erros/Humano** para ajustar probabilidades de comportamento humanizado.

## Segurança
- Execute o bot em modo janela focada no jogo para evitar digitar em outros aplicativos.
- Mantenha o ponteiro longe da barra de turno; a aplicacao já posiciona o mouse temporariamente para evitar interferencias.

## Solucao de problemas
- "Falhas repetidas ao capturar": recalcule as posicoes ou confira se `acento.txt` esta acessivel.
- "Envio cancelado" frequente: recalcule o retangulo da barra ou revise o threshold.
- Se algum modulo nao for encontrado, reinstale as dependencias listadas acima.

## Licenca
Projeto com fins educacionais. Use com responsabilidade e respeite as regras do jogo JKLM.fun.
