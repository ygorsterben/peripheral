# Protocolo — Aula F99 Pro (o que já se sabe antes de gravar)

Pesquisa de 2026-10-31. **Nada disto foi testado ainda no teclado do usuário** — confirmar por captura antes de enviar.

## Interfaces (HidP_GetCaps, lido no PC do usuário)
| Modo | Coleção | In | Out | Feature | Uso provável |
|---|---|---|---|---|---|
| Cabo 258A:010C | if 1, 0xFF00 u1 | 8 | – | **520** | cores tecla a tecla (report ID 6, ver abaixo) |
| Cabo | if 1, 0xFF00 u1 | – | – | **6** | comandos curtos (efeito/brilho/…?) — a confirmar |
| Cabo | if 1, 0xFF00 u1 | 4 | – | – | ? |
| Dongle 3554:FA09 | if 1, **0xFF02** u2 | 20 | **20** | – | protocolo sem fio de 20 bytes (abaixo) |
| Dongle | if 1, 0xFF04 u2 | – | – | 8 | ? |

## Cabo — cores diretas (OpenRGB, MR !3062, rascunho não incorporado)
- `SinowealthKeyboard10cController::SetLEDsDirect`: buffer de **520 bytes** enviado com `hid_send_feature_report`:
  `buf[0]=0x06 (report ID)`, `buf[1]=0x08`, `buf[4]=0x01`, `buf[6]=0x7A`, `buf[7]=0x01`, depois **RGB por LED a partir
  do byte 8** (`8 + i*3`). Sem checksum. Pausa de 1 ms depois.
- O modo direto precisa de **reenvio contínuo** (o OpenRGB reenvia se passar 1 s sem atualização).
- Mapa tecla → índice de LED: `aula_f99_layout` em `SinowealthKeyboard10cDevices.cpp` (não copiado ainda).
- **ID do modelo: 0xA4 = F99** (0xCD = F75) — igual no cabo e no sem fio.
- Aviso do OpenRGB: o PID 010C é reutilizado por vários teclados com firmwares diferentes, e detectores SinoWealth
  já **brickaram** teclados Redragon → só mandar comandos confirmados por captura do nosso teclado.

## Dongle — protocolo de 20 bytes (OpenRGB issue #5166, capturas do autor)
```
13 | CMD | TOTAL | ÍNDICE | MODO/TAM | 14 bytes de dados | CK = soma(bytes 0..18) & 0xFF
```
- CMD: `0x05` pede o ID do modelo (resposta: 10º byte = 0xA4), `0x07` mandado primeiro pelo software (?),
  `0x88` cores. TOTAL/ÍNDICE = pacotes da mensagem.
- MODO/TAM: nibble alto `0x10` = cor por tecla, `0x20` = cor única; nibble baixo = nº de bytes de dados.
  Cor única: `R G B`; por tecla: `R G B N códigos...`.
- Exemplo (tudo vermelho): `13 88 01 00 23 ff 00 00 ... be`.

## Captura: abrir o software pelo cabo (`capturas/teclado_abrir.pcap`, USBPcap2 endereço 6, 2026-10-31)
- Só **feature reports pela if 1** (SET_REPORT `wValue 0x0306` = feature, report ID 6; GET_REPORT igual), 3 vezes:
  envia `06 82 01 00 01 00 06 00...` (520 bytes) → lê de volta 14 bytes:
  `06 82 01 00 01 00 06 00 03 00 00 00 01 58`. O software mostra **firmware V3.0.0 (USB)** → `03 00 00` = versão;
  `01 58` = ?
- Estado do usuário (print): efeito **Neon_stream**, brilho 4, velocidade 4 (máx.), "Colourful" marcado; perfil
  "Profile1"; luz com música desligada. Abas Global: Device Info, Language, Startup, Exit, Tap, Sleep, Debounce, Reset.
- O software **não lê efeito/teclas ao abrir** (diferente do mouse) — deve guardar o estado no PC.

## Captura: trocar efeito de luz (`capturas/teclado_efeito.pcap`) — Fixed_on → Respire → Neon_stream
Tudo por **feature report ID 6, 520 bytes** (SET_REPORT/GET_REPORT `wValue 0x0306`, if 1). Cabeçalho de 8 bytes:
`06 CMD 00 00 01 00 TAM_LO TAM_HI`? (`80 00` = 128, `00 02` = 512). A cada "salvar" o software faz:
1. SET `06 84 00 00 01 00 80 00` + GET → teclado devolve o **bloco de configuração de 128 bytes** (após o cabeçalho).
2. SET `06 04 00 00 01 00 80 00` + o bloco alterado (**ler → alterar → gravar**).
3. SET `06 0a 00 00 01 00 00 02` + 512 bytes (cores — paleta dos efeitos? `fe e1 00 ff 00 00 00 ff ff ff 00 ...`).

Bloco de 128 bytes (como gravado com Neon_stream):
```
idx: 0  1  2  3  4  5  6  7  8  9  10 11 12 ...
     00 03 03 01 00 00 04 04 07 00 0b 20 01 00 00 00 00 00 01 00 02 01 00 ff 0a 00 00 00 03 06 01 01 ...
     ... ff ff 04 40 04 40 04 47 ... 04 04 04 04 | 5a a5   (últimos 2 bytes = marca 5a a5)
```
- **idx 10 = efeito** = número `hw` do `LedOptN` do KB.ini: Fixed_on `01`, Respire `02`, Neon_stream `0b`.
- **Brilho/velocidade são por efeito** (`capturas/teclado_brilho_vel.pcap`, uma mudança por salvamento): par de 2
  bytes por efeito em **idx 56 + 2×hw** (Neon_stream hw 11 → idx 78/79):
  - 1º byte = **brilho 0..4** (2 → `02`, 4 → `04`);
  - 2º byte, nibble alto = **velocidade 0..4** (2 → `20`, 4 → `40`); nibble baixo = **"Colourful"**: `7` =
    colorido, `0` = cor única (`capturas/teclado_cor.pcap`: Fixed_on `40` → `47` ao marcar Colourful).
- **Cor única de cada efeito** fica no bloco de 512 bytes do cmd `0x0a`: 3 bytes RGB por efeito; Fixed_on (hw 1)
  nos bytes 21..23 do bloco (vermelho `ff 00 00` → azul `00 00 ff`) → provável **offset 18 + 3×hw**. O software
  reenvia o 0x0a inteiro a cada salvar.
- **Nibble baixo do 2º byte do par do efeito = modo de cor (corrigido em 2026-10-31):** `0` = cor escolhida,
  `1..6` = uma das 6 cores da paleta do efeito (1 = verde), **`7` = colorido (aleatório)**. O código antigo gravava
  `1` para "colorido" e o teclado ficava verde (Respire e Neon_stream).
- **Formato do bloco 0x0a decifrado (2026-10-31):** **21 bytes por efeito a partir do byte `21 × hw`** = 7 cores RGB:
  a 1ª é a cor escolhida, as outras 6 são a paleta do software (00ff00, 0000ff, ffff00, ff00ff, 00ffff, ffffff).
  Bytes 506/507 = `5a a5`. Conferido: as cores tiradas do perfil do software batem byte a byte com o bloco capturado,
  exceto a Fixed_on, que o usuário trocou depois (`0000ff` → `ff00ff`).
- **Perfil do software oficial:** `%LOCALAPPDATA%\BYCOMBO4\AULA F99 Pro\profile.dct` (13312 bytes). A partir do byte
  **12172**, um registro de 36 bytes por efeito (hw 1, 2, ...): `brilho velocidade colorido 00` + 8 × `R G B 00`
  (7 cores + zeros). Começo do arquivo: tabela de teclas (16 bytes por tecla). → O app pode **importar as cores do
  software oficial** e restaurar exatamente o que o usuário tinha.
- **Trocar de efeito sem mandar o 0x0a deixa a luz apagada** (Neon_stream, testado com `tools/teclado.py`); mandando
  0x84 → 0x04 → 0x0a como o software, funciona. Brilho sozinho funcionou sem o 0x0a. Não há leitura conhecida do
  bloco 0x0a — o app precisa guardar uma cópia (hoje: `perifericos/dados/teclado_cores.bin`).
  - (idx 6/7 = `04 04` não mudaram — não são brilho/velocidade.)
- **idx 3 = debounce** = estágio − 1 (2 Stage `01`, 4 Stage `03`) — `capturas/teclado_sono_debounce.pcap`.
- **idx 24 = sono** em unidades de 30 s (5 min `0a`, 10 min `14`). A tela Global aplica na hora (sem disquete),
  com o mesmo ler 0x84 → gravar 0x04. O liga/desliga do sono e o Tap ainda não foram capturados.
- Sem checksum aparente.

## Efeitos novos — o que é possível (análise 2026-10-31)
- **Efeitos do firmware são fixos** (18 + Self-define + OFF). Flags do `KB.ini` `LedOptN = hw, nome, velocidade, brilho,
  direção, aleatório, cor`: sem cor/aleatório = hw 3 (Rainbow), 15 (Windmill), 16 (Waterfall), 17 (Blossoming);
  sem velocidade = hw 1 (Fixed on). Criar efeito novo *no firmware* exigiria alterar o firmware → **não fazer**.
- **Desenho fixo por tecla** (Self-define, cmd 0x06, já capturado): qualquer combinação estática, gravada no teclado,
  funciona sem o app e em qualquer conexão. Não usar 0x06 para animar (provavelmente grava na flash a cada envio).
- **Efeitos animados pelo app** (música, temperatura, mapa de digitação, avisos…): precisam do **modo de cor direta**
  (OpenRGB: feature report 520 bytes, `buf[1]=0x08`, reenvio contínuo) — só no cabo, só com o app aberto.
  **Ainda não testado no nosso teclado** e não aparece nas capturas do software oficial → testar com cuidado, um
  quadro só, antes de prometer. Pelo dongle existe o `0x88` de 20 bytes (cor por tecla), mas seria lento (~27
  pacotes por quadro).

## Captura: luz por tecla — Self-define (`capturas/teclado_selfdefine.pcap`)
- Ao salvar o Self-define: 0x84 → 0x04 com **efeito idx 10 = `0x15`** (21 = `LedOpt19` do KB.ini) e **idx 9 = `01`**
  (volta a `00` ao sair do Self-define) → **cmd `0x06`**: `06 06 00 00 01 00 80 01` + 384 bytes = **cores por tecla
  em 3 planos de 126**: R = byte `idx`, G = byte `126 + idx`, B = byte `252 + idx` (idx = índice de matriz do KB.ini).
  Confirmado: F1 (idx 12) verde → byte 138; F2 (idx 18) azul → byte 270 (`capturas/teclado_selfdefine2.pcap`).
- Vermelho em Esc(0), A(9), W(14), S(15), D(21), ←(83), ↑(88), ↓(89), →(95) = preset "Gaoshou" do KB.ini
  (`GaoshouKey1`, `clrGaoshou=255,0,0`), que o Self-define já traz.
- Saindo para Neon_stream: 0x04 (idx 9 → 00, idx 10 → 0b) e 0x0a (cores dos efeitos), sem 0x06.

## Luz por tecla pelo receptor (`capturas/teclado_selfdefine_dongle.pcap`, 2026-10-31) — TESTADO
- Sequência: `0x44` (ler bloco) → `0x04` (bloco com idx 9 = `01` e idx 10 = `0x15`; idx 11 = `0x20`) →
  **`0x02`, TOTAL `0x1c` = 28 pacotes** (27 × 14 + 6 = 384 bytes) = os mesmos 3 planos R/G/B de 126 do cabo (0x06).
  Conferido: F1 (idx 12) verde só no plano G; QWER/ASDF e setas brancas = o desenho que já estava no teclado.
- `perifericos.teclado.aplicar_por_tecla()` regravou esse desenho pelo receptor: aceito e ecoado (0,5 s).
- Índices: `INDICE_TECLA` em `perifericos/teclado.py` (tirado do KB.ini; a roda = 108).

## Captura: remapear tecla (`capturas/teclado_remap.pcap`) — Scroll Lock → A → restaurar
- **cmd `0x03` = tabela de teclas**: `06 03 PÁG 00 01 00 00 02` + 512 bytes = **128 teclas × 4 bytes**, na ordem do
  índice de matriz do KB.ini (último número de cada `Kn`: Esc 0, ` 1, Tab 2, Caps 3, LShift 4, LCtrl 5, F1 12, ...,
  Scroll 90).
- Entrada de 4 bytes: `TIPO MODIF 00 CÓDIGO_HID` (tecla comum: `00 00 00 hid`; modificador: `00 bits 00 00`, ex.
  LShift `00 02 00 00`, LCtrl `00 01 00 00`).
- Scroll: `00 00 00 47` → `00 00 00 04` (A) → `00 00 00 47`. Só a página 0 foi reenviada; na 1ª tentativa o
  software mandou PÁG 0..3 (provável: Default, FN1, FN2, Tap — confirmar).
- Outros tipos (mouse, multimídia, macro, comandos): ver `[FN1]` do KB.ini (`0x09,0x01,valor`) — a capturar.

## Trocar tecla pelo receptor (`capturas/teclado_remap_dongle.pcap`, 2026-10-31) — TESTADO
- **cmd `0x01`, TOTAL `0x25` = 37 pacotes = 512 bytes** = a mesma tabela de 128 × 4 do cabo (0x03 página 0).
  O software NÃO lê a tabela: manda a tabela inteira a cada mudança (Scroll → A: só a entrada 90 muda,
  `00 00 00 47` → `00 00 00 04`). Tabela padrão salva em `perifericos/dados/teclado_teclas_padrao.bin`.
- Tipos vistos na tabela padrão: `00 MOD 00 HID` tecla, `02 00 HH LL` multimídia (Calc = `02 00 01 92`, código
  consumer em big-endian), `0d 00 00 00` Fn, `07 00 00 1d` roda; `00 00 00 00` = sem função (posições vazias).
- `gravar_teclas(montar_tabela_teclas({}))` pelo receptor: aceito e ecoado (0,4 s). Fn e roda travadas no app.
- **A tabela vale só no modo Windows (Fn+W).** Com o teclado no modo Mac (Fn+Q) a gravação é aceita e ecoada, mas a
  tecla não muda (2026-10-31: Scroll = A só funcionou depois de Fn+W). O app avisa isso na aba Teclas.

## Captura: macro "teste1" = A, B, C no Scroll (`capturas/teclado_macro.pcap`)
- Tecla → macro na tabela 0x03: Scroll = **`03 01 01 00`** (tipo `03` = macro; `01` = nº da macro?; `01` = repetição?).
- **cmd `0x05` = conteúdo da macro**: `06 05 00 00 01 00 TAM 00` + dados:
  `04 00 | 25 00 (tamanho do resto) | 0c (tam. do nome) | "teste1" em UTF-16LE | eventos de 4 bytes`
  Eventos: `ESPERA(2 bytes, big-endian?, ms) TECLA_HID FLAG(80 aperta / 00 solta)`:
  `00 7d 04 80` A↓, `05 ad 04 00` A↑, `00 5d 05 80` B↓, `00 5e 05 00` B↑, `00 5e 06 80` C↓, `00 00 06 00` C↑.
  (o 1º envio veio vazio — só o nome, TAM 0x11 — e o 2º com os eventos, TAM 0x29.) `04 00` no início = ? (slot?).
- Ainda a confirmar: significado de `04 00`, ordem/unidade da espera, como ficam várias macros.
- Teste do usuário: apertar Scroll digitou **só "a"** (não "abc"). Suspeita: modo de repetição "enquanto segurar"
  (o 3º byte `01` da tecla?) + espera de ~1,45 s depois do A↑ → soltar a tecla interrompeu. Investigar se for usar
  macro no hardware (ou fazer macros pelo app no PC).

## Dongle 3554:FA09 — captura (`capturas/teclado_dongle.pcap`, USBPcap1 endereço 3, 2026-10-31)
**Mesmo conteúdo do cabo, em pacotes de 20 bytes** (SET_REPORT de saída pelo ep 0, coleção 0xFF02; o dongle ecoa
cada pacote e responde pelo **ep 0x82**):
```
13 | CMD | TOTAL | ÍNDICE | TAM | 14 bytes de dados | CK = soma(bytes 0..18) & 0xFF
```
| Cabo (feature 520) | Dongle (20 bytes) | Conteúdo |
|---|---|---|
| `82` firmware | `05` → resposta TAM 0x0a: `03 00 00 00 01 58 01 ...` | V3.0.0 (mesmos bytes) |
| `84` ler bloco | `44` → 10 pacotes (9×14 + 2 bytes = 128) | **mesmo bloco de 128 bytes** |
| `04` gravar bloco | `04`, TOTAL 0x0a, 10 pacotes | idem (brilho 2 → `02 47` no par do Neon) |
| `0a` cores (512) | `09`, TOTAL 0x25 = 37 pacotes | mesmas cores |
| — | `07` → `01 01` | mandado primeiro pelo software (?) |
- **Avisos espontâneos do dongle** (ep 0x82, CMD `0a`, TAM 4): `02 01 00 00`, `07 00 00 00`, **`05 64 01 00`** →
  provável **bateria = 0x64 = 100 %**. O software não mostra bateria (`ShowPower=0` no KB.ini), mas ela chega.
- Ainda não visto pelo dongle: 0x03 (teclas), 0x05 (macro), 0x06 (luz por tecla) — devem seguir o mesmo envelope.

## Bluetooth — "AULA-F99Pro 5.0", 3554:FA07 (BLE), testado em 2026-10-31
- Expõe a **mesma coleção 0xFF02 de 20 bytes do dongle** → mesmo protocolo (`13 CMD TOTAL IDX TAM ... CK`).
  `tools/teclado.py` leu o bloco e mudou o brilho (1 → 4) pelo Bluetooth; o usuário viu a luz mudar.
- O pedido **0x07 não tem resposta** no BT (é do dongle; o dongle responde 0x07 mesmo sem o teclado ligado nele).
  Para saber se o teclado está num caminho, usar o **0x05** (firmware).
- **O Windows perde pacotes de resposta** quando chegam vários juntos (ex.: de 10 do bloco 0x44 chegam ~6, outros
  a cada vez; 4 e 8 raramente). Solução: repetir o pedido e juntar as partes — ler levou ~16 s, gravar ~20 s.
  Ideia para melhorar: o app guardar uma cópia do bloco e só ler quando necessário.
- Aviso de bateria também chega no BT: `13 0a 01 00 04 05 64 01 ...` (0x64 = 100 %).
- **Bluetooth clássico "AULA-F99Pro 3.0" = 3554:FA08**: também tem a coleção 0xFF02 de 20 bytes e responde ao
  firmware (0x05), mas perde **ainda mais** pacotes do bloco (o pacote 3 não veio em 5 tentativas; a leitura não
  completou em 20). Como a perda acontece nos dois Bluetooth, deve ser do lado do teclado. **Preferir dongle/cabo;
  no BT, o app deve gravar a partir de uma cópia guardada em vez de ler.**
- **idx 14 do bloco = modo de conexão**: `00` cabo, `01` dongle, `02` Bluetooth (idx 15 = `01` no BT, canal?).

## Fontes
- https://gitlab.com/CalcProgrammer1/OpenRGB/-/issues/5166
- https://gitlab.com/CalcProgrammer1/OpenRGB/-/merge_requests/3062 (cabo) e !3026/!3027 (sem fio)

## Macro pelo receptor (`capturas/teclado_macro_dongle.pcap`, USBPcap1 endereço 1, 2026-10-31) — FUNCIONA
- Modo Windows (Fn+W): macro `m1` no Scroll **digitou "abc"** (o "só a" do cabo era do modo Mac). Receptor: tecla = `03 01 01 00`
  na tabela 0x01 (37 pacotes); conteúdo da macro = **cmd `0x03`** (no cabo é 0x05), 2 pacotes de 20 bytes.
- Macro montada no software: A, B, C só com "aperta" (sem soltar), esperas 1, 2 e 3 ms. Dados (21 bytes):
  `04 00 | 11 00 | 04 | 6d 00 31 00 ("m1") | 00 00 01 04 | 00 00 02 05 | 00 00 03 06`.
  As esperas 1, 2, 3 aparecem logo antes de cada tecla (04, 05, 06) → o formato de evento deste envio NÃO é igual ao
  do cabo (`espera(2) tecla flag`); falta uma gravação com soltar/atrasos maiores para decifrar.

### Formato do conteúdo da macro no receptor — DECIFRADO (`capturas/teclado_macro_dongle2.pcap`, 2026-10-31)
- Macro `m2`: A↓100, A↑200, B↓300, B↑400, C↓500, C↑600 → cmd `0x03`, TOTAL 3 pacotes (TOTAL = ceil(bytes/14)):
  `04 00 | 1d 00 | 04 | 6d 00 32 00 ("m2") | 00 00 64 04 | 80 00 c8 04 | 00 01 2c 05 | 80 01 90 05 | 00 01 f4 06 | 80 02 58 06`
- Cabeçalho: `04 00` (fixo nas duas macros), tamanho do resto (2 bytes LE) = 1 + tam. do nome + 4 × eventos, tam. do
  nome em bytes, nome em UTF-16LE.
- **Evento de 4 bytes = `FLAG ESPERA(2, big-endian, ms) TECLA_HID`**, FLAG `00` = apertar, `80` = soltar.
  Isso explica `m1` (só apertar, esperas 1, 2, 3): `00 00 01 04 | 00 00 02 05 | 00 00 03 06`.
  (A leitura antiga do cabo, `espera tecla flag`, era a mesma sequência de bytes deslocada em 1.)
- Falta: nº da macro na tecla (`03 01 01 00`: o 2º byte é o nº? o 3º é repetição?), várias macros, repetição, mouse (0x08).
- Teste do usuário com `m2`: saiu `aabbbbbcccccc` (aprox.) = repetição automática do Windows enquanto a tecla fica apertada.
  A espera é o tempo ANTES do evento, então A fica apertado 200 ms, B 400 ms, C 600 ms. Para digitar sem repetir,
  usar esperas curtas (ex.: 10–20 ms) entre apertar e soltar.

### Duas macros (`capturas/teclado_macro_dongle3.pcap`, 2026-11-01): m3 no Scroll, m4 no Pause
- **Entrada da tecla = `03 01 01 IDX`**, IDX = nº da macro na lista enviada (0-based): Pause (m4) = `03 01 01 00`, Scroll
  (m3) = `03 01 01 01`. Os dois `01` do meio ainda sem significado (repetição?).
- Macro única (1º envio, 1 macro): `04 00 | TAM(2) | corpo`, corpo = `tam_nome nome eventos`.
- Com 2 macros (2º envio, 34 bytes): `08 00 0d 00 15 00 | 0d 00 04 "m4" 00000a05 80000a05 | 04 "m3" 00000a04 80000a04`
  (m4 = corpo de 13 bytes com prefixo `0d 00`; m3 = 13 bytes). O cabeçalho `08 00 0d 00 15 00` NÃO está decifrado
  (0x0d = 13 = tamanho de uma macro; 0x15 = 21 = tamanho da m3 antiga com A e B; talvez lista de tamanhos/slots).

### Cabeçalho da lista de macros — DECIFRADO (`capturas/teclado_macro_dongle4.pcap`, 2026-11-01: m7, m6, m5)
- Blob da macro (receptor, cmd `0x03`, TOTAL = ceil(bytes/14)) = **tabela + corpos**:
  **tabela = N × (DESLOCAMENTO u16 LE, TAMANHO u16 LE)**, o deslocamento é contado desde o início do blob (o da 1ª
  macro = 4 × N, tamanho da tabela); **corpos colados** logo depois, cada um = `tam_nome(1) nome(UTF-16LE) eventos`.
  Evento = `FLAG(00 aperta/80 solta) ESPERA(2, big-endian, ms) TECLA_HID`.
- Prova: 1 macro `04 00 15 00`; 2 macros `08 00 0d 00 | 15 00 0d 00`; 3 macros (m7 29 bytes, m6 13, m5 13):
  `0c 00 1d 00 | 29 00 0d 00 | 36 00 0d 00` (12, 29 | 41, 13 | 54, 13). Os corpos vieram na ordem m7, m6, m5.
- Teclas: `03 01 01 IDX` com IDX = posição do corpo no blob (0, 1, 2). Os dois `01` do meio ainda sem significado.

### Repetição (`capturas/teclado_macro_repeticao.pcap`, 2026-11-01)
- Macro "abc" no Scroll com **repetir 3x**: a tecla passou de `03 01 01 00` para **`03 01 03 00`** → entrada da tecla =
  **`03 MODO VEZES IDX`**, modo `01` = repetir VEZES vezes. Outros modos (enquanto segurar?) ainda não gravados.
  O conteúdo da macro (cmd 0x03) não muda com a repetição.

### Modo Windows / Mac = byte 27 do bloco de configuração (2026-11-01)
- Lido pelo receptor: Fn+W → `bloco[27] = 00`, Fn+Q → `bloco[27] = 01` (única diferença no bloco de 128 bytes).
- O app só grava o bloco depois de lê-lo (alterar/aplicar_por_tecla), então preserva o modo. Nas gravações antigas do
  software oficial pelo cabo, os blocos enviados tinham byte 27 = 00.
- As trocas de tecla e as macros só valem com 00 (Windows).

### Trava da tecla Win (Fn + Win) = byte 15 do bloco (2026-11-01)
- Lido pelo receptor no modo Windows: Win funcionando → `bloco[15] = 00`; depois de Fn+Win (Win travada) → `01`.
- Só tem efeito no modo Windows (no Mac a Win vira Cmd). Era a causa de "a Win só funciona com Fn+Q".

### Modificadores na macro (`capturas/teclado_macro_shift.pcap`, 2026-11-01) — saiu "A" maiúsculo
- m8 = Shift↓ A↓ A↑ Shift↑: eventos `10 03 1d e1 | 00 00 4e 04 | 80 02 80 04 | 90 00 00 e1`.
- **FLAG = bits: `0x80` = solta, `0x10` = modificador** (código HID E0–E7 no 4º byte). Com flag 00/80 no Shift, o
  teclado ignora o modificador (teste do app: saiu "a" minúsculo).

### Modos de repetição (2026-11-01, confirmados pelo usuário com o software oficial)
- Tecla = `03 MODO VEZES IDX`: **`01` = repetir VEZES vezes**, **`02` = até apertar outra tecla**
  (`capturas/teclado_macro_segurar.pcap`, apesar do nome do arquivo), **`04` = enquanto segurar**
  (`capturas/teclado_macro_modo3.pcap`). Nos modos 02/04 o software manda VEZES = 01.

### Macro pelo cabo (`capturas/teclado_macro_cabo.pcap`, USBPcap2 endereço 8, 2026-11-01)
- **Mesmo bloco do receptor**, num feature report só: `06 05 00 00 01 00 TAM(2, little-endian) + bloco` (máx. 512).
  Tecla na tabela do cabo (0x03) = a mesma entrada `03 MODO VEZES IDX`. Ordem do software: tabela (0x03) → macros (0x05).

### Ler o bloco de cores = cmd `0x8a` (cabo) — FUNCIONA (2026-11-01)
- Pedido `06 8a 00 00 01 00 00 02` (feature report) → resposta `06 8a 00 00 01 00 00 02` + 512 bytes = o mesmo bloco
  que o `0x0a` grava (21 bytes por efeito em 21 × hw). Lido no teclado real: 9 bytes diferentes da cópia do app
  (cores mudadas depois pelo software oficial) → a cópia do app pode ficar desatualizada; melhor ler do teclado.
- Receptor/Bluetooth: provável `0x49` (padrão leitura = escrita + 0x40, como 0x44/0x04) — testar.

### Cor ao vivo = cmd `0x88` (receptor) — `capturas/teclado_musica_dongle.pcap` (Luz com música, 2026-11-01)
- Envelope `13 88 TOTAL IDX TIPO dados[14] CK`; **TIPO = 0x10 + tamanho** nos pacotes com dados (0x1e = 14 bytes);
  nos quadros de silêncio `13 88 01 00 23 00 00 00 ...` (0x20 + 3?). ~60 pacotes/s; quadros de 1 a 14 pacotes.
- Dados do quadro (pedaços juntados por IDX) = lista de grupos **`R G B N idx1..idxN`** (idx = mesmo índice da luz por
  tecla / INDICE_TECLA). Ex.: `c8 00 00 02 2e 34`, `00 ff 00 02 52 53`, `00 00 5f 01 35`.
- Não houve comando para "entrar" no modo; ao sair o software leu (0x44) e regravou (0x04) o bloco de configuração.
- **TESTADO pelo app (2026-11-01, receptor): quadro `ff0000 1 esc | 0000ff 4 w a s d` reenviado por 6 s acendeu as
  teclas certas; regravar o bloco (0x04) voltou ao efeito normal.** A testar: teclas fora da lista apagam? precisa reenviar sempre (tempo limite)? limite de grupos; cabo (0x88 também?).

### Cor ao vivo pelo CABO = cmd `0x08` — `capturas/teclado_musica_cabo.pcap` (2026-11-01) — TESTADO
- Feature report `06 08 00 00 01 00 7a 01` + **378 bytes = 126 teclas × (R G B)** na ordem de INDICE_TECLA (quadro
  completo, diferente da lista esparsa do receptor). Software: ~1 quadro a cada 47 ms.
- Teste pelo app: W A S D azul + Esc vermelho por 6 s acendeu certo; regravar o bloco (0x04) voltou ao efeito normal.
