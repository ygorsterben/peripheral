# Peripheral — Gerenciador de Periféricos

**Versão: build beta 1.0** (`1.0.0b1`) · Windows 11 · licença [GPL-3.0](LICENSE)

App leve que configura o teclado **Aula F99 Pro** e o mouse **Fire Phoenix BK-R6X** sem os softwares oficiais.
Os fabricantes não publicam o protocolo: ele foi descoberto gravando pela USB (USBPcap + Wireshark) o que os
softwares oficiais mandam, e reimplementado em Python com hidapi. O protocolo está documentado em [`docs/`](docs/).

## O que faz

**Mouse BK-R6X** (cabo ou receptor 2.4G)
- DPI: até 6 níveis (50 a 18.000), nível ativo e cor do LED de cada nível
- Polling rate, tempo de sono, bateria
- Função de cada botão: clique, ciclo de DPI, tecla/atalho com modificadores, multimídia, atalhos do Windows, desativar

**Teclado F99 Pro** (cabo, receptor 2.4G ou Bluetooth)
- 18 efeitos de luz com brilho, velocidade, cor e modo colorido, com prévia animada
- Luz por tecla (pintar cada tecla)
- Trocar a função das teclas (outra tecla, atalho, multimídia, desativar)
- **Macros gravadas no teclado** (rodam sem o app): sequências com espera, Ctrl/Shift/Alt/Win, repetir N vezes,
  enquanto segurar ou até apertar outra tecla
- Tempo de sono e debounce

O app fica na bandeja, pode iniciar com o Windows e lê os aparelhos sozinho.

## Instalação

Precisa do Python 3.12.

```powershell
py -m pip install -r requirements.txt          # app: hidapi, pywebview, pystray, pillow
py -m pip install -r requirements-dev.txt      # + pyinstaller, para gerar o .exe
```

## App

```powershell
py iniciar.py                 # abre o app (janela + ícone na bandeja); --bandeja = só o ícone
py construir.py               # gera dist\GerenciadorPerifericos.exe (um arquivo, sem console)
```

Fechar a janela deixa o app na bandeja. No menu da bandeja: DPI do mouse, luz do teclado, "Iniciar com o
Windows" e Sair. Abrir o app de novo só traz a janela da instância que já está aberta.
Configurações e registro de erros ficam em `%APPDATA%\GerenciadorPerifericos\`.

As trocas de teclas e as macros do teclado só valem no **modo Windows** do teclado (**Fn + W**).

## Uso pela linha de comando

```powershell
py tools\mouse.py ler                  # estado completo do mouse (cabo ou dongle)
py tools\mouse.py dpi 4                # nível de DPI ativo
py tools\mouse.py cor 4 FFFFFF         # cor do LED do nível 4
py tools\teclado.py ler                # estado do teclado (cabo, dongle ou Bluetooth)
py tools\teclado.py brilho 3
```

Cada comando tem `--help`. Toda gravação relê o aparelho para conferir.
Pelo dongle, o mouse **parado** não responde: mexa o mouse quando o comando pedir.

## Pastas

```
perifericos/            protocolo dos aparelhos (pacote Python usado pelo app e pelas ferramentas)
├── mouse.py            BK-R6X: DPI, cores do LED, polling, sono, botões
├── teclado.py          F99 Pro: efeitos, cores, luz por tecla, teclas, macros, sono, debounce
└── dados/              bloco de cores padrão dos efeitos e tabela de teclas padrão
app/                    o app (pywebview + bandeja) e a interface em app/ui (HTML/CSS/JS, sem bibliotecas)
tools/                  linha de comando e diagnóstico
docs/                   protocolo do mouse e do teclado, funções dos softwares oficiais
design/prototipo/       protótipo da interface
```

As gravações USB (`.pcap`) citadas em `docs/` não são publicadas: elas também registram o que foi digitado
durante cada gravação. Os bytes relevantes de cada comando estão transcritos nos documentos.

## Aviso

Projeto independente, sem ligação com a Aula, a Fire Phoenix ou os fabricantes dos chips. Use por sua conta:
gravar configurações num aparelho sempre tem algum risco. O app nunca escreve no canal de atualização de firmware.

A prévia dos efeitos de luz segue o comportamento das prévias do software oficial descrito no projeto
[open-f75](https://github.com/phantranthienan/open-f75) (só o comportamento; nenhum código foi copiado) e vídeos
do teclado real.
