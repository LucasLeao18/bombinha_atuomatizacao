# Implementação original (Python) — somente referência

Esta é a versão 1 do Bombinha (`codigov4.py`, Tkinter + pyautogui + OpenCV), mantida como **referência
funcional** da reescrita em C#/.NET (raiz do repositório). Ela não recebe mais correções; os problemas
encontrados nela estão listados em [`docs/ARQUITETURA.md`](../../docs/ARQUITETURA.md).

Para rodá-la mesmo assim:

```powershell
cd legacy\python
python -m pip install -r requirements.txt
python codigov4.py        # precisa ser executado DESTA pasta (caminhos relativos)
python test_logica.py     # testes da lógica
```

O `config.json` daqui aponta para `../../assets/acento.txt` e `../../assets/chatbox.png`, que foram movidos para
`assets/` na raiz. Para levar estas configurações para a versão nova: **Setup › Sistema › Importar da versão
antiga…** e selecione esta pasta.

`Zignore.txt` (lista acentuada de 320 mil linhas), `chatboxantiga.png` e `22.png` não eram usados pelo código.
