# JKLM.fun Automacao PT-BR

Aplicacao desktop em Python para automatizar partidas no jogo JKLM.fun (modo Bomb Party), com interface Tkinter e comportamentos humanizados.

## Recursos
- Interface grafica moderna (tema escuro) com menu lateral, cartoes, sliders e switches.
- Painel "Rodada atual" mostrando letras detectadas, palavra escolhida e evento em tempo real.
- Console colorido por nivel (sucesso, aviso, erro) com rolagem automatica e copiar/limpar.
- Estatisticas em cartoes e historico da sessao exportavel para .txt.
- Captura automatica das letras do turno e selecao inteligente de palavras usando dicionario.

### Jogo
- **Verificacao de envio**: apos o ENTER, se ainda for a sua vez a palavra foi recusada — o bot
  percebe e tenta outra na mesma rodada.
- **Aprendizado**: palavra recusada 2x vai para `rejeitadas.txt` e nunca mais e usada. Com o tempo
  o dicionario converge para o que o JKLM realmente aceita.
- **Nunca repete** palavra na mesma partida (o JKLM sempre recusa repeticao).
- **Orcamento de tempo por turno**: o bot cronometra desde que a vez virou sua e corta a
  encenacao conforme o tempo aperta, em vez de usar um limite fixo.
- **Caca a vida extra**: nos modos normais ele prefere palavras com letras novas quando sobra
  tempo; o grid de 23 letras na tela mostra o progresso.
- **Perfis prontos** (Seguro / Equilibrado / Agressivo) ajustam a humanizacao de uma vez.
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
- `test_logica.py`: testes da logica pura (`python test_logica.py`), nao abre janela.
- `config.json`: configuracoes persistentes (auto-criado/atualizado).
- `posicoes.json`: posicoes de captura (letras, chatbox, retangulos, resolucao da calibracao).
- `acento.txt`: dicionario base de palavras.
- `blacklist.txt`: lista opcional de palavras a ignorar (crie o arquivo se desejar).
- `rejeitadas.txt`: gerado pelo proprio bot com as palavras que o JKLM recusou 2x.

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
| **Setup** | Dicionario, posicoes, captura da silaba, verificacao de envio e delays |
| **Humanizacao** | Perfis prontos, perfil de digitacao, chances de erro e frases engracadas |
| **Estatisticas** | Desempenho, taxa de aceitacao e historico da sessao (exportavel) |

Atalhos: `F8` para tudo, `F7` troca de modo, `F6` nova partida, `Ctrl+S` salva.

## Captura da silaba: clipboard ou OCR
O metodo padrao (duplo-clique + `Ctrl+C`) funciona sem instalar nada, mas mexe o mouse e usa a
area de transferencia — o app devolve o conteudo anterior automaticamente.

Para o metodo OCR (sem mouse e sem clipboard):
1. `pip install pytesseract` e instale o [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki).
2. Em **Setup > Captura da silaba**, escolha "OCR da imagem".
3. Capture a **regiao da silaba** (dois cliques: canto superior esquerdo e inferior direito).

Se o OCR nao estiver disponivel, o bot avisa no console e volta sozinho para o clipboard.

## Escala do Windows (DPI)
Se a escala nao for 100%, as coordenadas dos cliques e a leitura da tela se desalinham. O app roda
um diagnostico ao abrir e mostra o resultado em **Setup > Sistema**. O jeito mais simples e usar
escala 100%. A opcao "Ciencia de DPI" existe, mas **exige recalibrar todas as posicoes** depois de
ativada.

## Dicas de configuracao
- Threshold da barra: aumente se houver falsos negativos; reduza se detectar turnos alheios.
- Ative "Modo Teste" (Setup > Opcoes) para revisar o fluxo sem enviar nenhuma tecla.
- Use a pagina **Humanizacao** para ajustar probabilidades de comportamento humanizado.
- A **verificacao de envio** depende da deteccao de turno estar bem calibrada. Se a taxa de
  aceitacao aparecer muito baixa sem motivo, revise o retangulo da barra e o threshold — ou
  desligue a verificacao em **Setup > Verificacao e aprendizado**.
- Achou que o bot aprendeu errado? Basta apagar (ou editar) o `rejeitadas.txt`.

## Segurança
- Execute o bot em modo janela focada no jogo para evitar digitar em outros aplicativos.
- Mantenha o ponteiro longe da barra de turno; a aplicacao já posiciona o mouse temporariamente para evitar interferencias.

## Solucao de problemas
- "Falhas repetidas ao capturar": recalcule as posicoes ou confira se `acento.txt` esta acessivel.
- "Envio cancelado" frequente: recalcule o retangulo da barra ou revise o threshold.
- Se algum modulo nao for encontrado, reinstale as dependencias listadas acima.

## Licenca
Projeto com fins educacionais. Use com responsabilidade e respeite as regras do jogo JKLM.fun.
