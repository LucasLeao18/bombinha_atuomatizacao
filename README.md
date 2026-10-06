# Bombinha — automação do Bomb Party (JKLM.fun) em PT-BR

Aplicativo para Windows 10/11 que joga o modo **Bomb Party** do [JKLM.fun](https://jklm.fun): percebe quando é a
sua vez, lê a sílaba, escolhe uma palavra do dicionário e digita com comportamento humanizado — conferindo se o
jogo aceitou e aprendendo as palavras que ele recusa.

> Versão 2 (C#/.NET 10, WPF). A versão original em Python continua em [`legacy/python/`](legacy/python/) como
> referência. Os motivos da reescrita e a análise completa estão em [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md).

## Instalação

Baixe/gere `Bombinha-<versão>-win-x64.zip`, extraia e rode **`Bombinha.exe`**. É um executável único: não precisa
instalar Python, .NET, Tesseract nem nenhuma outra dependência, e funciona de qualquer pasta.

- Windows 10 (1809+) ou Windows 11, x64.
- Não pede administrador. Se o navegador do jogo estiver rodando como administrador, o app avisa (o Windows
  bloqueia teclas simuladas vindas de um programa comum).
- O primeiro arranque leva ~2 s (o executável extrai suas bibliotecas nativas uma vez); os seguintes, menos de 1 s.

## Primeiros passos

1. Abra o jogo no navegador e deixe-o visível, sem janelas por cima do campo de digitação.
2. **Setup › Posições na tela**: clique em *Capturar* e depois no ponto dentro do jogo:
   - **Área das letras** — sobre a sílaba da bomba;
   - **Campo de digitação** — dentro do campo onde você digita;
   - **Barra de turno** — dois cliques (cantos do retângulo).
   Durante a captura o app se esconde e uma camada transparente recebe o clique (ele não chega ao jogo).
   As posições são gravadas na hora.
3. Na sua vez, clique em **Testar detecção**: o app mostra se enxerga o campo de digitação e com que similaridade.
   Se não reconhecer, use *Imagem do campo de digitação › Capturar da tela* e selecione a borda esquerda do campo.
4. Em **Principal**, escolha o modo e clique **Iniciar**. **F8** para tudo na hora — inclusive no meio de uma
   palavra.

Veio da versão em Python? **Setup › Sistema › Importar da versão antiga…** e selecione a pasta que tem o
`config.json`/`posicoes.json` antigos (neste repositório, `legacy/python`). Configurações, posições,
`rejeitadas.txt` e `blacklist.txt` são trazidos. Se a escala do Windows não era 100%, recalibre as posições.

## Atalhos

| Tecla | Ação |
| --- | --- |
| **F8** | Para a automação imediatamente (global) |
| **F7** | Troca o modo de jogo (global) |
| **F6** | Nova partida: zera palavras usadas e alfabeto (global) |
| **Ctrl+S** | Aplica e salva as configurações |

Os atalhos globais são registrados no Windows (`RegisterHotKey`); se outro programa já usar uma dessas teclas,
o console avisa.

## Recursos

**Jogo**
- Modos: palavras longas, curtas, qualquer palavra e alfabeto (caça às 23 letras da vida extra).
- Nunca repete palavra na mesma partida; penaliza repetições na sessão.
- **Verificação de envio**: se ainda for a sua vez depois do ENTER, a palavra foi recusada — o bot tenta outra
  na mesma rodada. Recusada 2× vai para `rejeitadas.txt` e não é mais usada.
- **Orçamento de tempo por turno**: cronometra desde que a vez virou sua e corta a encenação quando o tempo aperta.
- Nova partida automática após um período sem turnos.

**Leitura da sílaba**
- *Clique + Ctrl+C* (padrão): seleciona a sílaba e copia, confirmando a cópia pelo número de sequência da área de
  transferência e devolvendo depois tudo o que você tinha copiado (texto, imagens, arquivos), sem poluir o
  histórico do Win+V.
- *OCR do Windows*: lê a sílaba da imagem, sem mexer no mouse nem no clipboard (usa o OCR nativo do Windows, sem
  instalar nada). Se o OCR não reconhecer a sílaba num ciclo, o bot usa clique + Ctrl+C naquele ciclo.

**Humanização**
- Perfis prontos (Seguro, Equilibrado, Agressivo), perfil de velocidade, erros corrigidos com backspace, pausas,
  hesitação antes do ENTER, "pensar" após 3 letras, frase engraçada / ensaio digitados e apagados, falha
  proposital, erro + ENTER + correção, números aleatórios por algumas rodadas.

**Segurança**
- Antes de digitar ou copiar, o app confere se o foco está na janela do jogo (e não no próprio Bombinha ou em
  outro programa). Se não estiver, a jogada é cancelada com um aviso no console.
- Modo teste: roda o fluxo inteiro sem enviar teclas.

## Onde ficam os arquivos

| O quê | Onde |
| --- | --- |
| Configurações e posições | `%APPDATA%\Bombinha\settings.json` |
| Palavras recusadas pelo jogo | `%APPDATA%\Bombinha\rejeitadas.txt` (pode editar/apagar) |
| Blacklist pessoal (opcional) | `%APPDATA%\Bombinha\blacklist.txt` (uma palavra por linha, `#` comenta) |
| Template capturado da tela | `%APPDATA%\Bombinha\campo-digitacao.png` |
| Logs técnicos (14 dias) | `%LOCALAPPDATA%\Bombinha\logs\` |

O dicionário PT-BR (~245 mil palavras) e o template padrão ficam embutidos no executável; **Setup** permite usar
arquivos próprios. Os botões *Abrir pasta de dados* e *Abrir pasta de logs* levam até essas pastas.

## Solução de problemas

- **"Campo de digitação não encontrado"** no *Testar detecção* durante a sua vez: capture o template da tela
  (Setup) ou reduza um pouco o limite do template. Fora da sua vez, "não encontrado" é o esperado.
- **Envia em turnos alheios**: aumente o limite do template/da barra de turno.
- **"Digitação bloqueada por segurança"**: alguma janela (inclusive o Bombinha "sempre no topo") está por cima
  do campo de digitação, ou o foco foi para outro programa.
- **ENTER antes da palavra terminar / palavra digitada em cima de outra**: aumente *Setup › Ritmo e limites ›
  Intervalo mínimo entre teclas* (padrão 100 ms, o mesmo ritmo da versão antiga). Valores baixos são mais rápidos,
  mas o navegador pode não registrar as teclas a tempo. Com intervalos maiores, aumente também o *Orçamento por
  turno*, senão a encenação é cortada com frequência.
- **Captura falhando seguidamente**: confira a posição da área das letras e o zoom do navegador; experimente o
  clique triplo ou o OCR.
- Achou que o bot aprendeu errado? Edite ou apague `rejeitadas.txt`.

## Desenvolvimento

Requer o SDK do .NET 10.

```powershell
.\build.ps1            # build Release, testes unitários e de integração, executável e .zip em artifacts\
.\build.ps1 -E2E       # inclui os testes ponta a ponta (movem o mouse e digitam por ~30 s)
dotnet run --project src\Bombinha.App
```

| Pasta | Conteúdo |
| --- | --- |
| `src/Bombinha.Core` | Regras do bot, sem dependência de Windows: seleção de palavras, planejamento da digitação, detecção por imagem, motor, configuração |
| `src/Bombinha.App` | WPF + integração com o Windows (SendInput, captura de tela, clipboard, OCR, atalhos) |
| `tests/Bombinha.Core.Tests` | Testes unitários (inclui o porte de todos os testes da versão Python) |
| `tests/Bombinha.App.IntegrationTests` | Testes contra as APIs reais do Windows e um jogo simulado |
| `assets/` | Dicionário e template padrão (embutidos no executável) |
| `legacy/python/` | Implementação original, mantida como referência |

## Licença

Projeto com fins educacionais. Use com responsabilidade e respeite as regras do JKLM.fun.
