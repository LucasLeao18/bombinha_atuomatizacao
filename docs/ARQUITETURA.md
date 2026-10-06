# Arquitetura do Bombinha 2

Este documento registra a análise da versão original (Python), a escolha de tecnologia da reescrita, a
arquitetura resultante e como ela foi validada.

## 1. O que o aplicativo faz

Joga o modo Bomb Party do JKLM.fun no navegador, observando a tela e simulando teclado/mouse:

1. **Detecta a vez** procurando na tela a imagem do campo de digitação (template) e, opcionalmente, comparando a
   "barra de turno" com uma referência.
2. **Lê a sílaba**: duplo/triplo clique sobre ela + Ctrl+C (com várias tentativas) ou OCR de uma região.
3. **Escolhe a palavra** no dicionário PT-BR (sílaba em qualquer posição), pontuando por modo (longa, curta,
   qualquer, alfabeto), prefixo, letras novas para a vida extra (quando sobra tempo) e repetição.
4. **Digita humanizado**: atraso por letra conforme perfil, erros corrigidos, pausas, hesitação, "pensar" após
   3 letras, frase engraçada/ensaio apagados, falha proposital, erro + ENTER + correção, dígitos aleatórios.
   Antes de cada ENTER confere de novo se ainda é a vez.
5. **Confere o aceite**: se a vez continua do jogador após o ENTER, a palavra foi recusada → tenta outra na mesma
   rodada; 2 recusas → aprendida em `rejeitadas.txt`.
6. **Gerencia o tempo**: orçamento por turno a partir da virada da vez; se a encenação não cabe, envia direto.
7. Interface com Principal, Console, Setup, Humanização e Estatísticas; atalhos F6/F7/F8; calibração por clique.

## 2. Análise da versão original (`legacy/python/codigov4.py`)

Um único arquivo de ~3000 linhas (lógica, captura, digitação, UI Tkinter e persistência), com dependências
numpy, opencv-python, pyautogui, pynput, pyperclip, keyboard, Pillow e, opcionalmente, pytesseract + Tesseract.
Não usa registro, serviços, rede nem privilégios administrativos; o único subprocesso é o `tesseract.exe`
iniciado pelo pytesseract a cada leitura OCR.

### Defeitos e riscos encontrados

| # | Área | Problema | Consequência |
|---|---|---|---|
| 1 | Segurança | Ctrl+C da captura e toda a digitação vão para **qualquer janela em foco**; nada confere o alvo. | Digitar em outro programa; **copiar texto de outro programa e tratá-lo como sílaba** (reproduzido nos testes ponta a ponta). |
| 2 | Segurança | Sem o arquivo de template, `detectar_chatbox` retorna "é a sua vez" sempre. | O bot digita continuamente na janela em foco. |
| 3 | Segurança | A janela do bot fica "sempre no topo" por padrão e pode cobrir o campo do jogo. | Cliques e teclas caem na própria UI. |
| 4 | Concorrência | A UI altera o objeto de configuração enquanto a thread do bot o lê; `historico`, `frequencia` e `usadas_partida` são lidos/limpos pela UI (F6, estatísticas) enquanto o bot os altera. | Configuração pela metade; `RuntimeError: ... changed size during iteration`. |
| 5 | Robustez | Exceções fora de `_jogar_rodada` (captura, OpenCV, `FailSafeException` do pyautogui) **matam a thread do bot em silêncio**. | UI continua mostrando "Rodando". |
| 6 | Robustez | F8/Parar só é verificado entre ciclos e tentativas. | O bot continua digitando por segundos após o kill switch. |
| 7 | Robustez | `config.json`/`posicoes.json` carregados sem tratamento de erro. | Arquivo vazio/corrompido derruba o app na inicialização. |
| 8 | Robustez | Todos os caminhos (config, dicionário, template, logs, listas) são relativos ao diretório de trabalho. | Executar de outra pasta quebra tudo. |
| 9 | Correção | `pyautogui.typewrite` só envia teclas do seu mapa e usa códigos de tecla virtuais. | Letras acentuadas são **puladas**; resultado depende do layout do teclado. |
| 10 | Correção | Dígitos inseridos pela humanização tornam a palavra inválida, mas a recusa conta como *strike* da palavra. | Palavras válidas acabam "aprendidas" como rejeitadas. Além disso, `inserir_numeros` ignora o contador de rodadas. |
| 11 | Correção | Área de transferência: grava um texto sentinela no clipboard do usuário e só preserva texto. | Histórico do Win+V poluído; **imagens/arquivos copiados são perdidos**. |
| 12 | Correção | Captura de tela em RGB convertida com `COLOR_BGR2GRAY`, template lido em BGR. | Pesos de canal trocados entre tela e template. |
| 13 | Correção | "Top opções" mostra as N primeiras do dicionário, não as melhores; o mesmo número controla o sorteio. | Log enganoso; ajuste acoplado. |
| 14 | Correção | O *cooldown* de repetição é fixado na criação (`deque(maxlen=...)`). | Mudar a configuração não tem efeito até reiniciar. |
| 15 | Correção | Falha ao gravar `rejeitadas.txt` é engolida e registrada como "já estava na lista". | Erro de disco invisível. |
| 16 | Correção | Letras acentuadas contam para as 23 letras da vida extra (`isalpha`). | Progresso do alfabeto incorreto com dicionários acentuados. |
| 17 | Desempenho | Captura da tela inteira + `matchTemplate` a cada 200 ms, antes de cada ENTER e após cada envio. | ~54 ms por verificação nesta máquina (3840×1080) e risco de achar o template em outra janela. |
| 18 | Desempenho | OCR via pytesseract cria um processo por leitura e exige instalar o Tesseract (resolvido pelo PATH). | Lento; dependência externa; risco de binário errado no PATH. |
| 19 | UI | Recarregar o dicionário (245 mil linhas) e o diagnóstico rodam na thread da UI. | Interface congela. |
| 20 | UI | Atalhos por *polling* (`keyboard.is_pressed` a cada 100 ms) numa thread eterna que engole exceções. | Pode perder toques; hook global de teclado. |
| 21 | DPI | Processo sem ciência de DPI por padrão; a opção exige reiniciar e recalibrar. | Com escala ≠ 100%, cliques e capturas caem no lugar errado. |
| 22 | Logs | Nível do log adivinhado por palavras-chave; painel "ao vivo" interpreta o texto do log (um dos ramos nunca casa); arquivo aberto/fechado a cada linha. | Cores erradas, painel frágil. |

**Código morto/duplicado**: `Zignore.txt`, `chatboxantiga.png` e `22.png` não são referenciados;
`_last_turn_capture`, o alias `append_terminal` e o ramo `"Estimativa do round"` não têm efeito; numpy é usado
só para normalizar pesos. `_digitar_texto` e `digitar_pensando_3` são o mesmo laço duplicado; a geração de
palavra errada aparece duas vezes; o modelo de tempo estimado reimplementa a digitação. O dicionário tem 247
entradas duplicadas.

### Comportamentos preservados

**Ritmo implícito do pyautogui.** O código antigo nunca altera `pyautogui.PAUSE`, que vale 0,1 s: depois de
*cada* letra, tecla, clique e ENTER havia 100 ms de espera, mesmo com "atraso entre letras" de 5 ms. A primeira
versão da reescrita não reproduzia isso e digitava rápido demais para o jogo (ENTER antes das letras serem
registradas, palavra nova começando antes de o campo ser limpo). Agora o intervalo é uma configuração explícita
(`timing.keyIntervalMs`, padrão 100 ms, ajustável em Setup) aplicada depois de toda ação de entrada, e cada
palavra começa limpando o campo.

Todos os recursos visíveis foram mantidos: modos e pontuação (mesmas fórmulas, testadas), verificação de envio
e aprendizado, orçamento por turno, nova partida automática, captura por clique (duplo/triplo/auto, tentativas)
e por OCR, comparação da barra de turno (pixel/cor/híbrido), toda a humanização e os três perfis, frase de
desistência, estatísticas e exportação do histórico, atalhos F6/F7/F8, calibração por clique, modo teste.

## 3. Escolha da tecnologia

O app é quase só integração com o Windows (injeção de entrada, leitura de tela, clipboard, atalhos globais, DPI,
OCR) mais uma lógica pequena e uma GUI de configuração. Critérios e avaliação:

| Critério | Python (atual) | **C# / .NET 10 + WPF** | Rust | C++ | Go |
|---|---|---|---|---|---|
| APIs Win32/WinRT | via ctypes/libs de terceiros | P/Invoke gerado em compilação; WinRT nativo (OCR) | `windows-rs`, bom | nativo | fraco |
| GUI | Tkinter desenhado à mão | WPF maduro, MVVM, DPI per-monitor | egui/Slint, imaturo para desktop | Win32/Qt, custoso | fraco |
| OCR sem dependência | não (Tesseract) | **sim** (`Windows.Media.Ocr`) | sim, via WinRT | sim, via WinRT | difícil |
| Distribuição | PyInstaller ~100 MB, falsos positivos de antivírus comuns | executável único self-contained | binário pequeno | binário pequeno | binário pequeno |
| Concorrência/cancelamento | GIL, threads sem cancelamento | `CancellationToken`, threads, `Channel` | excelente | manual | excelente |
| Produtividade/manutenção | alta, mas sem tipos | alta, tipada, analisadores | média | baixa | média |

**Decisão: C#/.NET 10 (LTS) com WPF, sem arquitetura híbrida.** O gargalo do app é o jogo, não a CPU, então o
ganho de Rust/C++ em tamanho de binário não compensa a GUI e o custo de desenvolvimento piores. .NET dá acesso
direto a tudo que o app precisa, inclusive o OCR nativo que elimina o Tesseract, e publica um executável que
não exige nada instalado.

## 4. Arquitetura

```
src/Bombinha.Core (net10.0, sem Windows)      src/Bombinha.App (WPF, net10.0-windows)
├─ Engine/     BotEngine, TurnClock           ├─ Platform/   Win32Input (SendInput), GdiScreenCapture,
├─ Words/      WordList, WordSelector         │              Win32Clipboard, WindowsOcrEngine,
├─ Typing/     TypingPlanner, TypingPlan,     │              HighResolutionClock, ForegroundWindowGuard,
│              TypingExecutor                 │              GlobalHotkeys, ImageFiles, Native
├─ Detection/  TurnDetector, TurnGuard        ├─ Infrastructure/ AppPaths, SettingsService, WordRepository,
├─ Capture/    ClipboardSyllableReader,       │              FileLogSink, UiLogSink, LegacyMigration,
│              OcrSyllableReader, ...         │              DisplayDiagnostics
├─ Imaging/    TemplateMatcher, ...           ├─ ViewModels/ Main, Settings, Console
├─ Settings/   AppSettings, SettingsStore,    ├─ Views/      MainWindow + 5 páginas
│              LegacyImporter, Presets        ├─ Ui/         tema, controles, ScreenPicker
└─ Logging/    Logger, sinks                  └─ AppServices.cs (raiz de composição)
```

- **Core não conhece o Windows**: depende de interfaces (`IInputDriver`, `IScreenCapture`, `IClipboard`,
  `IOcrEngine`, `IClock`, `ITurnDetector`, `ITargetWindowGuard`). Por isso o motor inteiro é testável com fakes.
- **Digitação em duas etapas**: `TypingPlanner` (puro) gera um roteiro de passos já sorteado; o
  `TypingExecutor` o executa. A duração do roteiro é conhecida antes de começar (substitui o "modelo de tempo
  estimado" duplicado) e o cancelamento é verificado antes de cada passo.
- **Motor numa thread dedicada** com `CancellationToken`: todas as esperas são canceláveis (F8 interrompe no
  meio da palavra). As esperas usam um *waitable timer* de alta resolução — o timer padrão do Windows (~15,6 ms)
  distorceria atrasos de 5 ms. Erros por ciclo são registrados com exceção completa; 5 seguidos param o motor
  com estado "Erro" visível.
- **Estado compartilhado** do motor fica sob um único lock e sai para a UI como `EngineSnapshot` imutável;
  eventos são levados à thread da UI pelo `Dispatcher`. A configuração vigente é um objeto imutável por
  convenção, trocado atomicamente a cada gravação; a tela edita uma cópia.
- **Detecção** procura o template só numa faixa (±150 px, configurável) do monitor do campo calibrado, com
  correlação normalizada (mesma métrica do `TM_CCOEFF_NORMED`) usando imagens integrais, SIMD e busca
  grossa→fina; a barra de turno usa pixel, histograma HSV ou ambos, como antes.
- **Captura da sílaba**: o sucesso do Ctrl+C é medido pelo `GetClipboardSequenceNumber` (sem sentinela); o
  clipboard do usuário é restaurado com todos os formatos e marcado para não entrar no histórico; texto com mais
  de 5 letras é descartado (e nunca registrado por inteiro). OCR: tons de cinza + margem + várias escalas
  (medido contra o motor real: binarizar ou deixar o texto encostado na borda faz o OCR do Windows falhar).
- **Segurança de alvo**: antes de digitar e antes do Ctrl+C, `ForegroundWindowGuard` exige que a janela em foco
  seja a que está sob o ponto calibrado, que não seja o próprio Bombinha e que não esteja elevada (UIPI).
- **Configuração**: um `settings.json` em `%APPDATA%\Bombinha`, gravado de forma atômica, normalizado ao
  carregar; arquivo corrompido vira backup e o app segue com os padrões. Importador da versão antiga.
- **Logs**: níveis DEBUG→CRITICAL com componente; arquivo diário em `%LOCALAPPDATA%\Bombinha\logs` gravado em
  segundo plano (retenção de 14 dias) e console colorido por nível. O conteúdo do clipboard do usuário não é
  registrado.
- **DPI**: manifesto PerMonitorV2; todas as coordenadas são pixels físicos em qualquer escala.

## 5. Validação

| Verificação | Resultado |
|---|---|
| Build Release (`TreatWarningsAsErrors`, analisadores `latest-recommended`) | 0 avisos, 0 erros |
| Testes unitários (`Bombinha.Core.Tests`) — inclui o porte dos 31 testes Python | 109 aprovados |
| Integração com o Windows real: SendInput (Unicode, atalhos), captura + template, OCR (VEN/BRA/LHA/CA), clipboard, timer, guarda de segurança | 8 aprovados (estável em execuções repetidas) |
| Ponta a ponta: motor real contra um jogo simulado, por clique e por OCR (3 rodadas, uma recusa trocada) | 2 aprovados (`BOMBINHA_E2E=1`) |
| App real via UI Automation: abrir, Iniciar → "Aguardando a vez", F8 → "Parado", F7 troca de modo, fechar | OK, código de saída 0 |
| Executável publicado sem .NET instalado, de outra pasta | abre em ~0,6–0,8 s (1ª vez ~2,5 s), ~123 MB de memória privada, 153 MB no disco, 60 MB zipado |

Problemas encontrados *durante* a validação e corrigidos: Ctrl+C da captura indo para outra janela (a primeira
versão do guarda de janela cobria só a digitação), OCR do Windows falhando com texto binarizado/encostado na
borda, rolagem automática do console disparando exceção de layout e um laço de realimentação no handler global
de erros, e contenção do clipboard por outros processos.

## 6. Limitações conhecidas

- A detecção depende de imagem: zoom do navegador, tema ou mudanças visuais do JKLM exigem recapturar o template
  e recalibrar. Uma alternativa mais robusta seria ler o estado do jogo pelo DOM (extensão do navegador ou Chrome
  DevTools Protocol), mas isso muda o modo de uso e não foi adotado.
- Com o template embutido, a melhor similaridade encontrada numa região sem o campo (o próprio editor desta
  máquina) foi 0,79 — logo abaixo do limite padrão de 0,80. Capturar o template do seu jogo e/ou subir o limite
  dá mais margem; a barra de turno e o guarda de janela reduzem o impacto de um falso positivo.
- O OCR do Windows ainda falha com sílabas de **uma** letra; nesses ciclos o bot recorre a clique + Ctrl+C.
- Sem assinatura de código: o SmartScreen pode alertar na primeira execução.
