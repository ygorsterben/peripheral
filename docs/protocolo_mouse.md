# Protocolo — Fire Phoenix BK-R6X (cabo, 248A:5D2E)

Fontes (2026-10-30, software oficial):
- `capturas/dpi_usbpcap2_mouse_cabo.pcap` — nível ativo 2400 → 800 → 1600.
- `capturas/dpi_tabela_1650_12000.pcap` — valor do nível 1: 1600 → 1650 → 12000 → 18000.

## Transporte
- **Interface 2** (usage_page 0x0001, usage 0; relatórios IN/OUT de 33 bytes, sem report ID). Comandos vão por
  **interrupt OUT no endpoint 0x05**, 32 bytes (o 1º byte é o comando). Nenhuma transferência de controle é usada.
  - No hidapi: `write(b"\x00" + pacote)` (report ID 0 + 32 bytes); o eco chega por `read()`.
  - A interface 1 / 0xFFEF (report ID 5, 64 bytes) **não** é o canal: escrever 32 bytes nela dá erro 0x57.
  - Testado com `tools/mouse_dpi.py --enviar` (hoje `tools/mouse.py tabela`): o mouse aceitou e devolveu o eco (2026-10-30).
- O dongle (249A:5C2F, if 2, usage_page 0xFF01) tem o mesmo formato de 33 bytes / report ID 0 — provavelmente o
  mesmo protocolo. Não testado.
- O mouse responde no **interrupt IN 0x84** com um eco idêntico do pacote (~2–10 ms depois).
- Movimento normal: endpoint 0x81, 7 bytes = `botões | X int16 LE | Y int16 LE | roda | ?`.
- Com o mouse no cabo, o software fala só pelo cabo (o dongle no USBPcap1 não recebeu nada).

## Pacote (32 bytes)
| Byte | Significado |
|---|---|
| 0 | comando |
| 1–2 | `00 01` (constante até agora) |
| 3 | `0x25` no cmd 03, `0x12` no cmd 04 — talvez tamanho ou subcomando |
| 4..30 | dados |
| 31 | **checksum = soma(bytes 4..30) & 0xFF** (confere em 8/8 pacotes, cmds 03 e 04) |

## Comando 0x03 — tabela de DPI + nível ativo (confirmado)
```
03 00 01 25 | S | X0 00 Y0 00 | X1 00 Y1 00 | ... | X5 00 Y5 00 | 00 00 | CK
```
- **S (byte 4)**: nibble alto = índice do nível ativo (0-based), nibble baixo = quantidade de níveis (6).
  `0x06` → nível 0, `0x16` → nível 1, `0x26` → nível 2.
  **Contagem de níveis confirmada** (`capturas/contagem_dpi.pcap`): 6 → 4 mandou `0x34`, 4 → 6 mandou `0x36`.
  A tabela vai sempre com os 6 pares, mesmo com contagem menor. Ao reduzir a contagem, o software puxa o nível ativo
  para o último válido (era 4 → virou 3) e não devolve ao voltar para 6.
- **Tabela**: 6 níveis, par X/Y por nível (2 bytes cada; o 2º byte foi sempre 00). Código → DPI observado:

  | Código | DPI | Origem |
  |---|---|---|
  | 0x10 (16) | 800 | gravação 1 |
  | 0x20 (32) | 1600 | gravação 1 |
  | 0x21 (33) | 1650 | gravação 2 |
  | 0xc8 (200) | 10000 | gravação 3 |
  | 0xd2 (210) | 11000 | gravação 3 |
  | 0xdc (220) | 12000 | gravação 2 |
  | 0xdd (221) | 13000 | gravação 3 |
  | 0xe2 (226) | 18000 | gravação 2 (máximo) |

  **Codificação em 3 faixas (confirmada nos 11 valores):**
  ```python
  def codigo_dpi(dpi):
      if dpi <= 10000: return dpi // 50                    # passo 50   → 0x01..0xC8
      if dpi <= 12000: return 200 + (dpi - 10000) // 100   # passo 100  → 0xC9..0xDC
      return 220 + (dpi - 12000) // 1000                   # passo 1000 → 0xDD..0xE2
  ```
  Fonte da gravação 3: `capturas/dpi_alto_10000_11000_13000.pcap`.
- Tabela original do usuário: 0x10/0x20/0x30/0x57/0x60/0xdc → 800 / 1600 / 2400 / 4350 / 4800 / 12000
  (o 0x57 = 4350 assume ×50).
- O software reenvia o estado atual antes de aplicar uma mudança.

## Comando 0x02 — polling rate (confirmado na captura)
```
02 00 01 01 | V | 00 ... 00 | CK          (CK = V)
```
- **V = 1000 / Hz** (intervalo em ms): `08` → 125 Hz, `04` → 250 Hz, `02` → 500 Hz, `01` → 1000 Hz.
- Conferido pelo intervalo dos pacotes de movimento (ep 0x81) depois de cada troca: 8 / 4 / 2 / 1 ms.
- Byte 3 = `01` aqui (cmd 03 = `0x25`, cmd 04 = `0x12`) — reforça a ideia de subcomando, não de tamanho.
- Fonte: `capturas/polling_rate.pcap` (125 → 250 → 500 → 1000 → 1000). Ainda não enviado pelo nosso script.
- Não foi testado se existe valor acima de 1000 Hz pelo cabo.

## Dongle (249A:5C2F, if 2) — testado em 2026-10-31
- **Mesmo protocolo.** Escritas funcionam e o eco vem certo (polling 500 → 1000 testado com hidapi, lido de volta).
  `tools/mouse.py` acha o dongle sozinho (`Mouse.abrir()` em `perifericos/mouse.py` tenta cabo e depois dongle).
- **Leituras: funcionam, mas o dongle pode sair de sincronia.** Normalmente as respostas vêm inteiras e alinhadas
  (`tools/mouse.py ler` 3× seguidas OK, 2026-10-31). Depois que uma resposta se perde (pedidos rápidos demais?), o
  dongle fica **preso** entregando cada pacote IN como
  `[bytes 12..31 da resposta ANTERIOR] [00 00 00 00] [bytes 0..7 da resposta ATUAL]` — parece um buffer circular de
  36 bytes lido a partir do lugar errado; os bytes 8..11 nunca chegam. Aconteceu também com o software oficial
  (`capturas/dongle_abrir.pcap`, USBPcap1 endereço 2). **Só religar o dongle corrige** (o pedido 0x20 não corrige).
  A 0x10 continua alinhada mesmo dessincronizado (é respondida pelo próprio dongle). `mouse.py` detecta e avisa.
- **Investigação da dessincronia (2026-10-31, `tools/sonda_dongle_mouse.py`, `tools/monitor_sincronia.py`):**
  - Forma geral: pacote = `[resposta ANTERIOR a partir do byte d][00 00 00 00][resposta ATUAL bytes 0..d-5]`, ou seja,
    um anel de 36 bytes lido com deslocamento d. Os bytes d-4..d-1 de cada resposta se perdem.
  - **d só vale múltiplos de 6**: visto 12 (30/10), 6, 30 e 24 (31/10). Pedidos rápidos (40 sem pausa) **não** mudam d.
  - d **muda quando o mouse some e volta** (chave OFF → 2.4G): 6 → 30 → (24 ↔ 30). Com o mouse fora, o dongle
    responde `espera` (status 01) **alinhado** (d = 0). Palpite: o rádio entrega a resposta em pedaços de 6 bytes e um
    pedaço perdido desloca o anel em 6.
  - Com d = 30 os bytes perdidos são 26..29 (preenchimento nas leituras curtas) → dados aproveitáveis; com d = 6 perde
    os bytes 2..5 (tamanho e os 2 primeiros dados) → inútil.
  - Ainda sem forma de realinhar por software; religar o dongle continua sendo a única correção conhecida.
  - Depois de religar: **OFF→2.4G (3×) e acordar do sono NÃO dessincronizaram** (d = 0 o tempo todo).
  - **Mouse parado não responde configuração pelo dongle**: o dongle devolve só `1N 01` (espera), e esse pacote só
    sai quando chega o próximo pedido (atrasado em 1). Ao mexer o mouse, tudo responde certo e alinhado em < 0,5 s.
    Era isso que fazia `mouse.py ler` falhar ("leitura 0x11: nenhuma"). `mouse.py` agora repete o pedido por até
    12 s e pede para mexer o mouse. **No app: ao ler/gravar pelo dongle, pedir "mexa o mouse" e repetir.**
  - A dessincronia de verdade (d ≠ 0) não foi reproduzida; **troca BT → 2.4G também não dessincroniza** (testado).
    Suspeita restante: respostas atrasadas misturadas com pedidos repetidos (o `mouse.py` antigo, com mouse parado).
- **Bateria (2026-10-31):** BT (serviço GATT 0x180F, em %) = 100 e byte 9 da info 0x10 pelo dongle = `0x64` = 100 →
  coerentes; escala provavelmente 0–100 %. Falta ver um valor < 100. O software oficial só mostra uma barra (sem
  número); o exe tem `SetDeviceBattery(int,int,int)` (aparelho, valor, carregando?).
- **Byte 1 da resposta = status do dongle:** `00` OK, `01` esperando o mouse (continuar lendo), `02` + `ff` = não
  alcançou o mouse (desligado/dormindo/fora de alcance). Nesse caso a 0x10 vem com o último byte de dados = `00`.
- Pedido **0x20** (o software oficial manda pelo dongle): resposta `20 00 01 02 60 01` (2 bytes). Repetido em
  2026-10-31: igual, e vem na hora mesmo com o mouse parado. **Palpite:** versão do firmware do mouse (`60` é o
  mesmo valor do byte 4 da 0x10 no cabo; pelo dongle esse byte vira `85` = versão do dongle). Não é necessário para
  configurar.
- Info 0x10: byte 8 (dados) = `02` no cabo, `00` no dongle → **tipo de conexão** (o app mostrou "2.4"). Último
  byte (10) = mouse conectado (`01`/`00`). Byte 4 = `60` no cabo, `85` no dongle (?). Bateria continuou `0x64`.

## Leitura do estado — comandos 0x10..0x17 (captura, 2026-10-30)
Ao abrir, o software manda `1N 00 00 ... 00` (32 bytes, só o 1º byte) e o mouse responde no ep 0x84 com o mesmo
formato dos comandos de escrita (byte 3 = subcomando/tamanho, checksum no byte 31). **Leitura = escrita | 0x10.**
Fonte: `capturas/bateria_conexao.pcap` (só abrir o app, sem mudar nada).

| Leitura | Resposta (bytes 0..~22) | Interpretação |
|---|---|---|
| 0x10 | `10 00 01 0b 4d 31 31 30 60 01 11 01 02 64 01` | info: `"M110"` (ASCII, modelo?), ... `0x64` = 100 → **bateria 100 %?** (app mostrou "cheia"). Tipo de conexão provavelmente aqui também. |
| 0x11 | `11 00 01 12 10 01 00 10 02 00 10 04 00 10 08 00 10 10 00 40 01 00` | **botões** (provável cmd 0x01): 6 entradas de 3 bytes. `10 xx 00` = clique do mouse com máscara 01/02/04/08/10 (esq/dir/meio/voltar/avançar), `40 01 00` = botão de DPI? |
| 0x12 | `12 00 01 01 01` | polling rate = 1000 Hz (igual ao cmd 0x02) ✔ |
| 0x13 | `13 00 01 19 46 10 00 10 00 20 00 20 ... dc 00 dc 00` | tabela de DPI (igual ao cmd 0x03): 6 níveis 800/1600/2400/3200/4800/12000, **ativo = nível 4** |
| 0x14 | `14 00 01 12 ff 00 00 00 ff 00 00 00 ff ff 00 ff ff 88 00 00 ff ff` | cores RGB dos 6 níveis de DPI (= cmd 0x04) |
| 0x15 | `15 00 01 01 00` | ? (1 byte = 0) |
| 0x16 | `16 00 01 05 02 00 00 01 00` | ? |
| 0x17 | `17 00 01 05 5a 01 00 08 00` | **sono** = 0x5a × 10 s = 15 min (ver cmd 0x07) |

- **Byte 3 = quantidade de bytes de dados** em todas as leituras (0x10 → 11, 0x11 → 18, 0x12 → 1, 0x13 → 25 =
  1 + 6×4, 0x16/0x17 → 5). Nas escritas: cmd 02 → `01` (confere), mas o cmd 03
  usa `0x25` mesmo com 25 bytes de dados (conferido na captura) — talvez o nibble alto seja uma flag. Não importa
  para enviar: basta copiar o valor que o software usa.
- Para confirmar a bateria: repetir com o mouse sem fio e com a bateria abaixo de 100 %.

## Comando 0x07 — sono (confirmado na captura)
```
07 00 01 04 | T | 01 | 00 | 08 | 00 ... | CK          (leitura 0x17 devolve os mesmos 4 bytes + 1 byte 00)
```
- **T = tempo em unidades de 10 s**: 1/2/5/6/10/15/20/30 min → `06 0c 1e 24 3c 5a 78 b4`.
- Bytes 5 (`01`) e 7 (`08`) não mudaram com o tempo. Suspeita: um deles é o **wake up mode** ("move to wakeup").
- Fonte: `capturas/sono.pcap` (passou pelos 8 tempos em ordem). Original do usuário = 15 min; ficou 30 min.

## Comando 0x09 — funções dos botões (captura `capturas/botoes.pcap`)
```
09 00 01 0f | B1 (3) | B2 (3) | B3 (3) | B4 (3) | B5 (3) | B6 (3) | 00 ... | CK
```
- 6 entradas de 3 bytes `TIPO P1 P2`, na mesma ordem da leitura 0x11. Byte 3 = `0x0f` (15) mesmo com 18 bytes — como
  no cmd 03 (`0x25`), o "tamanho" das escritas não bate; copiar o valor do software.
- O "key 5" do software é a **4ª entrada** (original `10 08 00` = voltar/botão 4).
- Estado padrão: `10 01 00 | 10 02 00 | 10 04 00 | 10 08 00 | 10 10 00 | 40 01 00`.

| TIPO | Categoria do software | P1 P2 observados |
|---|---|---|
| `10` | Mouse features | máscara do botão: 01 esq, 02 dir, 04 meio, 08 voltar, 10 avançar |
| `30` | Fire button | `05 00` (padrão; 05 = vezes ou intervalo? — testar) |
| `40` | Sensitivity | `01 00` no botão 6 (provável ciclo de DPI) — testar |
| `60` | Disable key | `00 00` |
| `70` | Keyboard | `00 04` → P2 = código HID da tecla (0x04 = A); P1 provavelmente modificadores (Ctrl/Shift...) |
| `80` | Multimedia / System shortcut | código *consumer* 16 bits LE: `e9 00` = 0x00E9 Volume + (multimedia), `6f 00` = 0x006F Brilho + (system shortcut) — confirmados pelo usuário |
- Macro key: tipo ainda desconhecido (provável `20` ou `50`).
- "Restaurar padrão" dos botões só reenvia o cmd 0x09 com o estado padrão (nenhum outro comando).
## Comando 0x08 — conteúdo da macro (captura `capturas/macro_abc.pcap`, macro "A, B, C" no key 5)
Ao aplicar, o software manda **0x08 em pedaços** e logo depois o **0x09** com o botão apontando para a macro:
```
08 00 02 1b | 03 30 5e 00 04 b0 29 01 04 30 5d 00 05 b0 6e 00 05 30 4e 00 06 b0 f9 08 06 10 0a | CK   (pedaço 0 de 2)
08 00 12 06 | 00 01 90 0a 00 01 | (resto = lixo do buffer anterior, entra no checksum) | CK         (pedaço 1 de 2)
09 ... key 5 = 90 23 01
```
- Byte 2 = **pedaço/total** (nibble alto = índice, nibble baixo = total): `02` = 0 de 2, `12` = 1 de 2.
  Byte 3 = tamanho dos dados do pedaço. Dados juntos (33 bytes):
  `03 | 30 5e 00 04 | b0 29 01 04 | 30 5d 00 05 | b0 6e 00 05 | 30 4e 00 06 | b0 f9 08 06 | 10 0a 00 01 | 90 0a 00 01`
- **Evento de 4 bytes = `FLAG  ESPERA(16 bits LE, ms)  CÓDIGO`**. FLAG: `30` aperta tecla, `b0` solta tecla
  (bit 0x80 = soltar); `10`/`90` = aperta/solta botão do mouse (`01` = esquerdo — provavelmente o clique em "parar
  gravação" que o editor também gravou). ESPERA = tempo depois do evento.
  Conferido na execução (ep 0x82): A↓ →96 ms→ A↑ →305 ms→ B↓ →96→ B↑ →113→ C↓ →80→ C↑ (macro: 94/297/93/110/78 ms).
- 1º byte `03`: ? (talvez nº de teclas ou modo de repetição). Botão: tipo **`90` = macro**, P1 `0x23` (35 — tamanho?),
  P2 `01` (nº da macro ou repetições?). Uma só macro por enquanto; testar 2 macros para entender o endereço.
- Ao apertar o botão, saiu A várias vezes antes de B e C (e em um trecho B ficou preso com A alternando) — talvez o
  modo de repetição "enquanto segurar". Investigar se for usar macros no hardware.

### Macro de 1 tecla
- `capturas/macro.pcap`: macro de 1 tecla (A) no key 5 virou só `70 00 04` (igual a Keyboard → A); nenhum comando
  de macro foi enviado. Ou o software converte macro de 1 tecla em tecla simples, ou a macro não foi aplicada.
  Ao apertar o botão, o mouse manda teclado pelo **ep 0x82**: `01 00 04 00 00 00 00 00` (report ID 1, modif, 0, tecla).

## Comando 0x04 — cores dos níveis de DPI (resolvido em 2026-10-31)
**É a cor RGB de cada nível de DPI (6 × 3 bytes).** A leitura 0x14 dá `ff0000 00ff00 0000ff ff00ff ff8800 00ffff`,
que são exatamente as cores do `device\mouse_bk-r6x.xml` do software (#FF0000, #00FF00, #0000FF, #FF00FF, #FF8C00,
#00FFFF). **O BK-R6X tem um LED no meio que mostra a cor do nível ativo** (confirmado pelo usuário: as cores
mudam ao apertar o botão de DPI) → o app pode deixar escolher a cor de cada nível.
**Testado (2026-10-31):** `tools/mouse.py cor 4 FFFFFF` gravou, o eco e a releitura 0x14 conferiram, e sem o cabo o
LED ficou **branco** no nível 4 (4800). **No cabo o LED mostra a carga** (vermelho = carregando, verde = cheio), não o DPI. O software manda 0x04 depois de gravar um DPI com
valor novo (`dpi_tabela_1650_12000.pcap`); digitar o mesmo valor não manda (`cmd04_campo_dpi.pcap`).

Histórico:
```
04 00 01 12 ff 00 00 00 00 ff 00 ff 00 00 db 15 ff ff 00 00 ff fe 00 ... 00 e8   (gravação 1)
04 00 01 12 ff 00 00 00 00 ff 04 ff 00 00 db 15 ff ff 00 00 ff fa 00 ... 00 e8   (gravação 2)
```
Entre as gravações, o byte 10 ganhou o bit 0x04 e o byte 21 perdeu o mesmo bit. Segundo o usuário, ele aparece quando
se clica no campo para digitar o valor do DPI. Talvez o software desative/reative algo (atalhos de tecla? botão de
DPI?) enquanto o campo está em edição. Não é necessário para trocar o DPI. Investigar depois.
