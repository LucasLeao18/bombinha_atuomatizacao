# JKLM.fun Automacao PT-BR

Aplicacao desktop em Python para automatizar partidas no jogo JKLM.fun (modo Bomb Party), com interface Tkinter e comportamentos humanizados.

## Recursos
- Interface grafica moderna (tema escuro) com menu lateral, cartoes, sliders e switches.
- Painel "Rodada atual" mostrando letras detectadas, palavra escolhida e evento em tempo real.
- Console colorido por nivel (sucesso, aviso, erro) com rolagem automatica e copiar/limpar.
- Estatisticas em cartoes e historico da sessao exportavel para .txt.
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
3. Na pagina **Setup**:
   - Aponte para o dicionario (`acento.txt`).
   - Clique em **Capturar** e depois no ponto correspondente dentro do jogo (letras e campo de digitacao).
   - Para a barra de turno sao dois cliques: canto superior esquerdo e inferior direito.
   - Ajuste thresholds, delays e demais opcoes conforme necessario e clique **Aplicar e salvar**.
4. Na pagina **Principal**, escolha o modo de jogo e clique **Iniciar**.
5. Use `F8` como kill-switch rapido.

## Navegacao da interface
| Pagina | Para que serve |
| --- | --- |
| **Principal** | Modo de jogo, botoes Iniciar/Parar e acompanhamento da rodada atual |
| **Console** | Log colorido de tudo que o bot decide, com copiar/limpar |
| **Setup** | Dicionario, posicoes de tela, delays e opcoes de selecao |
| **Humanizacao** | Perfil de digitacao, chances de erro e frases engracadas |
| **Estatisticas** | Cartoes de desempenho e historico da sessao (exportavel) |

Atalhos: `F8` para parar tudo, `Ctrl+S` para salvar as configuracoes.

## Dicas de configuracao
- Threshold da barra: aumente se houver falsos negativos; reduza se detectar turnos alheios.
- Ative "Modo Teste" (Setup > Opcoes) para revisar o fluxo sem enviar nenhuma tecla.
- Use a pagina **Humanizacao** para ajustar probabilidades de comportamento humanizado.

## Segurança
- Execute o bot em modo janela focada no jogo para evitar digitar em outros aplicativos.
- Mantenha o ponteiro longe da barra de turno; a aplicacao já posiciona o mouse temporariamente para evitar interferencias.

## Solucao de problemas
- "Falhas repetidas ao capturar": recalcule as posicoes ou confira se `acento.txt` esta acessivel.
- "Envio cancelado" frequente: recalcule o retangulo da barra ou revise o threshold.
- Se algum modulo nao for encontrado, reinstale as dependencias listadas acima.

## Licenca
Projeto com fins educacionais. Use com responsabilidade e respeite as regras do jogo JKLM.fun.
