# Aula F99 Pro — o que o software oficial faz (lido da pasta de instalação)

Fonte: `C:\Program Files (x86)\AULA\F99\` (2026-10-31). Programa `OemDrv.exe` — driver genérico BY Tech/SinoWealth
(`Appdir=BYCOMBO4` no `Cfg.ini`). Config do modelo em `Dev\kb\F99Pro\KB.ini`; textos em `Text\en\text.xml`.

## KB.ini (F99Pro)
- `VID=0x258a PID=0x010C` (cabo), `VID_Wireless=0x3554 PID_Wireless=0xfa09` (dongle). `Fw=24`, `CRC=1`,
  `MatrixLen=128`, `ChannelMask=3`, `ShowDebounce=0x04000101`.
- **Sono**: `SleepUI=60,90,120,180,240,300,600,900,1200` (s) ↔ `SleepHW=2,3,4,6,8,10,20,30,40` → **unidades de 30 s**.
- **Efeitos de luz** `LedOptN = hw, efeito, velocidade, brilho, direção, aleatório, cor` (1 = permite ajustar):
  N=1..18 com códigos de efeito 1,3,2,19,15,13,20,16,18,5,7,17,12,8,28,30,14,29 (nomes em `tc_kb_led1..18`);
  `Light=0..4` e `Speed=0..4` (5 níveis cada). `DefLedIndex=10`.
- **[KEY]**: `Kn = x1,y1,x2,y2 (desenho), tipo, código VK do Windows, ?, ÍNDICE NA MATRIZ` — o último número é a
  posição da tecla no protocolo (Esc=0, `=1, Tab=2, Caps=3, LShift=4, LCtrl=5, F1=12...; 113 teclas, MatrixLen=128).
- **[FN1]**: funções de fábrica das combinações FN (`0x09,0x01,valor` — ex.: FN+F10..F12 = consumer 0xE2/0xEA/0xE9
  = mudo/vol−/vol+; FN+Q/W/E/R = 0x070000xx, provavelmente modos/canais).

## Funções do software (Text/en/text.xml)
- **Luz**: 18 efeitos (Fixed_on, Respire, Rainbow, Flash_away, Raindrops, Rainbow_wheel, Ripples_shining,
  Stars_twinkle, Shadow_disappear, Retro_snake, Neon_stream, Reaction, Sine_wave, Retinue scanning, Rotating windmill,
  Colorful waterfall, Blossoming, Rotating storm) + Self-define (por tecla) + OFF; brilho, velocidade, cor,
  colorido, direção.
- **Luz com música**: 10 modos, ganho, suavidade — feito pelo software no PC (o app pode fazer igual).
- **Teclas**: camadas Default / FN1 / FN2 / Tap; destinos: tecla, mouse (esq/dir/meio/avançar/voltar/rolagem/duplo
  clique), multimídia, comandos (fechar janela, bloquear PC, Executar, mostrar desktop, zoom, gerenciador de tarefas,
  desfazer, salvar, travar Win, travar teclado), combinação, macro, desativar.
- **Macros**: gravar/editar, atraso, repetição (N vezes / enquanto segurar / até outra tecla).
- **Global**: debounce (ms), sono (sem fio), perfis (importar/exportar/copiar), bateria, versão de firmware,
  restaurar fábrica, atualização de firmware ("conecte pelo USB primeiro").
- Aviso do software: o teclado precisa estar em **modo Windows (FN+W)**.
- **FN+Q = modo Mac** (confirmado pelo usuário em 2026-10-31: a tecla Win passou a agir como outra tecla). FN+W volta
  ao modo Windows. Cuidado ao usar FN+E/R/T (canais Bluetooth), que ficam ao lado.
