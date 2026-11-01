// Gerenciador de Periféricos — tela do teclado (fase 3: luz, sono e debounce gravam de verdade).
// Usa $, todos, minutos, hora, conexao, bateria, desenharTeclado, iluminarTeclado e EFEITOS_PT de app.js.
"use strict";

// Efeitos do firmware. Flags do KB.ini (LedOptN): velocidade, aleatório (colorido), cor. anim = só para a prévia.
// [hw, grupo, nome original, vel, aleatório, cor, anim, descrição]
const FX = [
  [1, "fixos", "Fixed_on", 0, 1, 1, "fixo", "Todas as teclas acesas numa cor, sem movimento."],
  [21, "fixos", "Self-define", 0, 0, 0, "portecla", "Cada tecla com a cor que você pintar. Fica gravado no teclado."],
  [2, "fixos", "Respire", 1, 1, 1, "respirar", "A luz acende e apaga devagar, como respiração."],
  [3, "ondas", "Rainbow", 1, 0, 0, "onda", "Faixas de todas as cores passando pelo teclado."],
  [6, "ondas", "Rainbow_wheel", 1, 1, 1, "radial", "Um arco-íris em volta do centro do teclado, girando devagar."],
  [11, "ondas", "Neon_stream", 1, 1, 1, "onda", "Uma onda de cor corre de um lado ao outro."],
  [13, "ondas", "Sine_wave", 1, 1, 1, "onda", "Ondas suaves de luz atravessando as fileiras."],
  [14, "ondas", "Retinue scanning", 1, 1, 1, "onda", "Uma faixa de luz varre o teclado e volta."],
  [15, "ondas", "Rotating windmill", 1, 0, 0, "radial", "Pás de cor girando a partir do centro."],
  [16, "ondas", "Colorful waterfall", 1, 0, 0, "onda", "Cores descendo como uma cachoeira."],
  [18, "ondas", "Rotating storm", 1, 1, 1, "radial", "Um redemoinho de cor girando rápido."],
  [12, "toque", "Reaction", 1, 1, 1, "toque", "Só acende a tecla que você aperta."],
  [7, "toque", "Ripples_shining", 1, 1, 1, "toque", "Cada toque solta uma onda em volta da tecla."],
  [5, "toque", "Raindrops", 1, 1, 1, "estrelas", "Pontos de luz caindo pelas colunas."],
  [4, "toque", "Flash_away", 1, 1, 1, "toque", "A tecla tocada pisca forte e some."],
  [9, "toque", "Shadow_disappear", 1, 1, 1, "toque", "Tudo aceso; a tecla tocada apaga e volta aos poucos."],
  [17, "toque", "Blossoming", 1, 0, 0, "radial", "Cores se abrindo a partir das teclas."],
  [8, "toque", "Stars_twinkle", 1, 1, 1, "estrelas", "Teclas aleatórias piscando como estrelas."],
  [10, "toque", "Retro_snake", 1, 1, 1, "onda", "Uma linha de luz andando pelo teclado, como o jogo da cobrinha."],
];
const EM_BREVE = [
  ["fixos", "Desligada", "em teste"],
  ["meus", "Mapa de digitação", "do app · em breve"], ["meus", "Aviso", "do app · em breve"],
];
// efeitos do app (cor ao vivo, app/efeitos.py): [id, nome, descrição, tira, modos [[id, nome]]]
const FX_APP = [
  ["musica", "Música", "As teclas seguem o som que sai do PC. Só funciona com o app aberto (a bandeja conta).",
    "linear-gradient(0deg,#2DFF6A 0 35%,#FFD400 35% 65%,#FF2A2A 65%)", [["barras", "Barras"], ["pulso", "Pulso"]]],
];
const fxApp = (id) => FX_APP.find((f) => f[0] === id);
let appSel = null;                                                  // efeito do app aberto no painel
let appOpcoes = { modo: "barras", sensibilidade: 3, cor: null };    // null = colorido
const GRUPOS = [["fixos", "Fixos"], ["ondas", "Ondas e cores"], ["toque", "Ao toque"], ["meus", "Criados por você"]];
const PALETA = ["FF0000", "FF8800", "FFFF00", "00FF00", "00FFFF", "0000FF", "9B4DFF", "FF00FF", "FFFFFF"];
const SONOS_T = [1, 1.5, 2, 3, 4, 5, 10, 15, 20];
const STRIP = {
  portecla: "linear-gradient(90deg,#9B4DFF 0 55%,#FFFFFF 55% 70%,#00FF00 70% 80%,#9B4DFF 80%)",
  fixo: "#9B4DFF", respirar: "linear-gradient(90deg,#2A1650,#9B4DFF,#2A1650)",
  onda: "linear-gradient(90deg,#FF2A2A,#FFD400,#2DFF6A,#2AD4FF,#6A4BFF,#FF2AD4)",
  radial: "conic-gradient(from 90deg,#FF2A2A,#FFD400,#2DFF6A,#2AD4FF,#6A4BFF,#FF2A2A)",
  toque: "linear-gradient(90deg,#2A1650 0 40%,#9B4DFF 40% 52%,#2A1650 52%)",
  estrelas: "radial-gradient(circle at 20% 50%,#FFF 0 2px,transparent 3px),radial-gradient(circle at 70% 40%,#C9B8FF 0 2px,transparent 3px),#2A1650",
};

let teclado = {};      // último estado lido
let previa = null;     // o que está na tela (pode ainda não estar gravado)
let grupo = null;
let gravandoT = false;

const fxDe = (hw) => FX.find((f) => f[0] === hw);
const mesmo = (a, b) => a && b && a.efeito === b.efeito && a.brilho === b.brilho && a.velocidade === b.velocidade &&
  a.colorido === b.colorido && a.cor === b.cor;

function chipT(texto, tipo) { const c = $("t-chip"); c.textContent = texto; c.className = "chip" + (tipo ? ` ${tipo}` : ""); }

function doTeclado(t) {
  return { efeito: t.efeito, brilho: t.brilho, velocidade: t.velocidade, colorido: !!t.colorido, cor: t.cor };
}

// ---------- abas ----------
todos("#t-abas [data-aba]").forEach((b) => b.addEventListener("click", () => {
  todos("#t-abas [data-aba]").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
  todos("#teclado .aba").forEach((a) => { a.hidden = a.dataset.aba !== b.dataset.aba; });
  pintarPrevia();
}));

// ---------- prévia no desenho ----------
// Motor da prévia. Segue o comportamento das prévias do software oficial da AULA (OemDrv.exe), descrito em
// https://github.com/phantranthienan/open-f75 (docs/reverse-engineering/previews): unidades de teclas (colunas,
// fileiras, setores, anéis), paletas, tempos de cada efeito e o desvanecer das teclas. Código próprio deste projeto.
// Sombra, Varredura e Redemoinho não estão documentados (o F75 os esconde): ali a animação é nossa.
const RGB = {
  vermelho: [255, 0, 0], verde: [0, 255, 0], azul: [0, 0, 255], magenta: [255, 0, 255], amarelo: [255, 255, 0],
  ciano: [0, 255, 255], laranja: [255, 128, 0], branco: [255, 255, 255],
};
const SORTEIO6 = [RGB.vermelho, RGB.ciano, RGB.verde, RGB.amarelo, RGB.azul, RGB.magenta];
const hexRgb = (h) => [0, 2, 4].map((i) => parseInt((h || "9B4DFF").slice(i, i + 2), 16));
const mistura = (a, b, f) => a.map((v, i) => Math.trunc(v + (b[i] - v) * f));
const escurece = (c, f) => c.map((v) => Math.trunc(v * f));
const matiz = (h) => [0, 8, 4].map((n) => { const k = (n + h * 12) % 12; return Math.round(255 * (1 - Math.max(0, Math.min(k - 3, 9 - k, 1)))); }); // arco-íris (HSL, s=1, l=.5)
const sorteio = (lista, evitar) => { let c; do { c = lista[Math.floor(Math.random() * lista.length)]; } while (lista.length > 1 && c === evitar); return c; };

let cena = null;      // teclas e unidades montadas uma vez
let anima = null;     // estado do efeito em andamento
let ultimoToqueReal = 0;

function montarCena() {
  const teclas = [...document.querySelectorAll("#teclado-grande .tecla")].map((el, i) => {
    const d = el.dataset;
    const k = { el, i, nome: d.nome, l: +d.l, t: +d.t, w: +d.w, h: +d.h, r: +d.r };
    k.cx = k.l + k.w / 2; k.cy = k.t + k.h / 2;
    return k;
  });
  const porNome = Object.fromEntries(teclas.map((k) => [k.nome, k]));
  const W = 20.5, H = 6.3, centro = { x: W / 2, y: H / 2 };
  const agrupar = (n, chave) => { const u = Array.from({ length: n }, () => []); teclas.forEach((k) => u[Math.max(0, Math.min(n - 1, chave(k)))].push(k)); return u.filter((g) => g.length); };
  const anguloHorario = (k) => { // 0 no canto de cima à esquerda, crescendo no sentido horário
    const a = Math.atan2((k.cy - centro.y) * 2.2, k.cx - centro.x);
    return ((a + Math.PI - 0.35 + 4 * Math.PI) % (2 * Math.PI)) / (2 * Math.PI);
  };
  const o = porNome.o;
  const distO = (k) => Math.hypot(k.cx - o.cx, (k.cy - o.cy) * 1.25);
  const maxO = Math.max(...teclas.map(distO));
  const fileiras = agrupar(6, (k) => k.r).map((f) => f.sort((a, b) => a.l - b.l));
  cena = {
    teclas, porNome, W, H, fileiras,
    colunas: agrupar(21, (k) => Math.floor(k.cx)).map((c) => c.sort((a, b) => a.t - b.t)),
    setores19: agrupar(19, (k) => Math.floor(anguloHorario(k) * 19)),
    setores13: agrupar(13, (k) => Math.floor(anguloHorario(k) * 13)),
    aneis11: agrupar(11, (k) => Math.floor(distO(k) / maxO * 10.999)),
    aneis10: agrupar(10, (k) => Math.floor(distO(k) / maxO * 9.999)),
    colunas14: agrupar(14, (k) => Math.floor(k.cx / W * 14)),
    // caminho da cobrinha: fileiras de cima para baixo alternando o sentido, depois de volta para cima
    serpente: (() => {
      const ida = fileiras.map((f, n) => (n % 2 ? [...f].reverse() : f));
      const volta = ida.slice(1, -1).reverse().map((f, n) => ((fileiras.length - 2 - n) % 2 ? f : [...f].reverse()));
      return [...ida, ...volta].flat();
    })(),
  };
}

// --- ciclo de paleta por unidade (Neon, Roda, Moinho, Cascata, Florescer, Arco-íris) ---
function cicloDe(unidades, paleta, segurar, fade, espalhar, direcao) {
  const n = paleta.length, volta = (segurar + fade) * n;
  const passo = Math.trunc((segurar + fade) * espalhar / unidades.length);
  const fases = unidades.map((_, u) => (direcao ? u * passo : (unidades.length - u) * passo) % volta);
  return { tipo: "ciclo", unidades, paleta, segurar, fade, volta, fases };
}
function corDoCiclo(a, u, ms) {
  const ph = (((a.fases[u] + ms) % a.volta) + a.volta) % a.volta, bloco = a.segurar + a.fade;
  const idx = Math.floor(ph / bloco), resto = ph - idx * bloco - a.segurar;
  const de = a.paleta[idx], para = a.paleta[(idx + 1) % a.paleta.length];
  return resto < 0 ? de : mistura(de, para, resto / a.fade);
}

function prepararEfeito(f, p) {
  const c = hexRgb(p.cor);
  const multi = !!(f[4] && p.colorido);
  const base = { nome: f[2], c, multi, alfa: new Float32Array(cena.teclas.length), cor: cena.teclas.map(() => c), acc: 0, ms: 0 };
  const P4 = [RGB.verde, RGB.azul, RGB.magenta, RGB.amarelo];
  switch (f[2]) {
    case "Rainbow": return { ...base, ...cicloDe([cena.teclas], [RGB.vermelho, RGB.verde, RGB.azul, RGB.magenta, RGB.laranja], 70, 1400, 1, 0) };
    case "Neon_stream": return { ...base, ...cicloDe(cena.colunas, multi ? P4 : [c, escurece(c, 0.3), c, escurece(c, 0.3)], 120, 240, 2.5, 0) };
    case "Rainbow_wheel": { // medido no vídeo do teclado real (2026-11-01): arco-íris contínuo em volta de um ponto
      // (~50 % da largura, ~55 % da altura), cores crescendo no sentido horário, girando 1 volta a cada ~6,1 s
      const cx = cena.W * 0.5, cy = cena.H * 0.55;
      const ang = cena.teclas.map((k) => (Math.atan2(k.cy - cy, k.cx - cx) / (2 * Math.PI) + 1) % 1);
      return { ...base, tipo: "roda", ang };
    }
    case "Rotating windmill": return { ...base, ...cicloDe(cena.setores13, P4, 60, 180, 4, 0) };
    case "Colorful waterfall": return { ...base, ...cicloDe(cena.fileiras, P4, 400, 800, 3, 0) };
    case "Blossoming": return { ...base, ...cicloDe(cena.aneis11, [RGB.vermelho, RGB.amarelo, RGB.verde, RGB.azul, RGB.ciano, RGB.magenta], 120, 300, 1.8, 0) };
    case "Self-define": { // as cores pintadas, paradas (cópia guardada no PC)
      const por = teclado.por_tecla || {};
      const al = new Float32Array(cena.teclas.length);
      const cor = cena.teclas.map((k, i) => { const h = por[k.nome]; al[i] = h ? 200 : 0; return hexRgb(h || "000000"); });
      return { ...base, cor, alfa: al };
    }
    case "Rotating storm": return { ...base, ...cicloDe(cena.setores19, multi ? [RGB.vermelho, RGB.magenta, RGB.azul, RGB.ciano, RGB.verde, RGB.amarelo]
      : [c, escurece(c, 0.15)], 0, 200, 2, 1), redemoinho: true };
    default: return base;
  }
}

// --- um passo dos efeitos que andam em "ticks" (tempo do software oficial em ms) ---
const PERIODO = { Fixed_on: 300, Respire: 50, Sine_wave: 30, Raindrops: 40, Stars_twinkle: 80, Retro_snake: 15.6,
  Reaction: 50, Flash_away: 30, Ripples_shining: 15, Shadow_disappear: 50, "Retinue scanning": 40 };

function passoEfeito(a) {
  const T = cena.teclas, al = a.alfa;
  switch (a.nome) {
    case "Fixed_on":
      T.forEach((k, i) => { al[i] = 200; a.cor[i] = a.multi ? a.gradiente[i] : a.c; });
      break;
    case "Respire": {
      a.dir ??= -1; a.v ??= 180;
      a.v += 6 * a.dir;
      if (a.v <= 5) { a.v = 5; a.dir = 1; } else if (a.v >= 180) { a.v = 180; a.dir = -1; }
      T.forEach((k, i) => { al[i] = a.v; a.cor[i] = a.multi ? a.gradiente[i] : a.c; });
      break;
    }
    case "Sine_wave": {
      for (let i = 0; i < T.length; i++) al[i] = Math.max(0, al[i] - 50);
      a.fase ??= 360;
      const amp = cena.H / 2 - 0.3;
      for (let t = 0; t <= 360; t += 8) {
        const x = 0.15 + t / 360 * (cena.W - 0.3), y = cena.H / 2 + Math.sin((a.fase + t) * Math.PI / 180) * amp;
        const k = T.find((q) => x >= q.l && x < q.l + q.w && y >= q.t && y < q.t + q.h);
        if (k && al[k.i] <= 0) { al[k.i] = 200; a.cor[k.i] = a.multi ? sorteio(SORTEIO6) : a.c; }
      }
      a.fase -= 20; if (a.fase < 0) a.fase = 360;
      break;
    }
    case "Raindrops": {
      a.gotas ??= cena.colunas.map(() => -1);
      const ociosas = [];
      cena.colunas.forEach((col, u) => {
        const pos = a.gotas[u];
        if (pos < 0) { ociosas.push(u); return; }
        if (pos >= col.length) { al[col[col.length - 1].i] = 0; a.gotas[u] = -1; return; }
        const k = col[pos];
        al[k.i] = 200; a.cor[k.i] = a.multi ? (a.ultima = sorteio(SORTEIO6.slice(0, 4), a.ultima)) : a.c;
        if (pos > 0) al[col[pos - 1].i] = 0;
        a.gotas[u] = pos + 1;
      });
      for (let n = 0; n < ociosas.length - 2; n++) a.gotas[ociosas[Math.floor(Math.random() * ociosas.length)]] = 0;
      break;
    }
    case "Stars_twinkle": {
      for (let i = 0; i < T.length; i++) al[i] = Math.max(0, al[i] - 20);
      for (let n = 0; n < 7; n++) {
        const i = Math.floor(Math.random() * (T.length * 1.2)); // ~1 em 6 sorteios cai fora, como no original
        if (i < T.length) { al[i] = 180; a.cor[i] = a.multi ? sorteio([RGB.vermelho, RGB.verde, RGB.azul, RGB.magenta, RGB.ciano]) : a.c; }
      }
      break;
    }
    case "Retro_snake": {
      for (let i = 0; i < T.length; i++) al[i] = Math.max(0, al[i] - 8);
      a.pos ??= 0;
      const k = cena.serpente[a.pos];
      al[k.i] = 200; a.cor[k.i] = a.multi ? (a.ultima = sorteio(SORTEIO6.slice(0, 4), a.ultima)) : a.c;
      a.pos = (a.pos + 1) % cena.serpente.length;
      break;
    }
    case "Reaction":
      for (let i = 0; i < T.length; i++) al[i] = Math.max(0, al[i] - 40);
      break;
    case "Shadow_disappear": // nossa: tudo aceso; a tecla tocada apaga e volta aos poucos
      for (let i = 0; i < T.length; i++) { al[i] = Math.min(200, al[i] + 8); a.cor[i] = a.multi ? a.gradiente[i] : a.c; }
      break;
    case "Retinue scanning": { // nossa: uma faixa de colunas vai e volta, com rastro
      for (let i = 0; i < T.length; i++) al[i] = Math.max(0, al[i] - 25);
      a.col ??= 0; a.sentido ??= 1;
      for (const k of cena.colunas[a.col]) { al[k.i] = 200; a.cor[k.i] = a.multi ? a.gradiente[k.i] : a.c; }
      a.col += a.sentido;
      if (a.col <= 0 || a.col >= cena.colunas.length - 1) a.sentido *= -1;
      break;
    }
    case "Flash_away": {
      for (let i = 0; i < T.length; i++) al[i] = Math.max(0, al[i] - 45);
      a.ondas = (a.ondas || []).filter((o) => o.esq >= 0 || o.dir < o.fila.length);
      for (const o of a.ondas) {
        for (const j of [o.esq, o.dir]) if (j >= 0 && j < o.fila.length) { al[o.fila[j].i] = 220; a.cor[o.fila[j].i] = o.cor; }
        o.esq--; o.dir++;
      }
      break;
    }
    case "Ripples_shining": {
      if (!a.losango) { for (let i = 0; i < T.length; i++) al[i] = 0; break; }
      const L = a.losango;
      L.raio += 0.65;
      const dentro = (x, y) => Math.abs(x - L.x) + Math.abs(y - L.y) * 2 <= L.raio;
      const cantos = (k) => [[k.l, k.t], [k.l + k.w, k.t], [k.l, k.t + k.h], [k.l + k.w, k.t + k.h]].filter(([x, y]) => dentro(x, y)).length;
      if ([[0, 0], [cena.W, 0], [0, cena.H], [cena.W, cena.H]].every(([x, y]) => dentro(x, y))) { a.losango = null; break; }
      T.forEach((k, i) => {
        const n = cantos(k);
        if (n > 0 && n < 4) { al[i] = 200; a.cor[i] = a.multi ? (a.ultima = sorteio(SORTEIO6, a.ultima)) : a.c; } else al[i] = 0;
      });
      break;
    }
  }
}

// --- teclas apertadas (de verdade, com a tela aberta, ou simuladas quando ninguém digita) ---
function apertar(k) {
  if (!anima || !k) return;
  const a = anima, al = a.alfa;
  const cor = a.multi ? sorteio(SORTEIO6) : a.c;
  if (a.nome === "Reaction") { al[k.i] = 220; a.cor[k.i] = cor; }
  if (a.nome === "Shadow_disappear") al[k.i] = 0;
  if (a.nome === "Ripples_shining") { a.losango = { x: k.cx, y: k.cy, raio: 0 }; al[k.i] = 200; a.cor[k.i] = cor; }
  if (a.nome === "Flash_away") {
    const fila = cena.fileiras.find((f) => f.includes(k));
    if (fila && (a.ondas || []).length < 10) (a.ondas ||= []).push({ fila, esq: fila.indexOf(k), dir: fila.indexOf(k), cor });
  }
}

const NOME_DO_CODIGO = {
  Escape: "esc", Backquote: "`", Minus: "-", Equal: "=", Backspace: "back", Tab: "tab", BracketLeft: "[", BracketRight: "]",
  Backslash: "\\", CapsLock: "caps", Semicolon: ";", Quote: "'", Enter: "enter", ShiftLeft: "shift", ShiftRight: "rshift",
  Comma: ",", Period: ".", Slash: "/", ControlLeft: "ctrl", ControlRight: "fn", MetaLeft: "win", AltLeft: "alt", AltRight: "ralt",
  Space: "space", ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down", Delete: "del", Home: "home",
  PageUp: "pgup", PageDown: "pgdn", ScrollLock: "scroll", NumLock: "numlock", NumpadDivide: "num/", NumpadMultiply: "num*",
  NumpadSubtract: "num-", NumpadAdd: "num+", NumpadEnter: "numenter", NumpadDecimal: "num.",
};
document.addEventListener("keydown", (ev) => {
  if (!cena || !$("teclado").classList.contains("ativa") || ev.repeat || document.querySelector("dialog[open]")) return;
  const c = ev.code;
  const nome = NOME_DO_CODIGO[c] || (/^Key[A-Z]$/.test(c) && c[3].toLowerCase()) || (/^Digit\d$/.test(c) && c[5]) ||
    (/^F\d+$/.test(c) && c.toLowerCase()) || (/^Numpad\d$/.test(c) && `num${c[6]}`);
  if (nome && cena.porNome[nome]) { ultimoToqueReal = performance.now(); apertar(cena.porNome[nome]); }
});

// --- liga a prévia ao que está escolhido ---
function pintarPrevia() {
  if (!cena) montarCena();
  if (mostraApp()) { anima = null; return; }  // a prévia vem do app (quadros pedidos abaixo)
  const naLuz = !$("teclado").querySelector('.aba[data-aba="luz"]').hidden;
  const p = naLuz && previa ? previa : (teclado.efeito ? doTeclado(teclado) : null);
  const f = p ? fxDe(p.efeito) : null;
  if (!cena) montarCena();
  if (!f) { anima = null; return; }
  const chave = `${p.efeito}|${p.colorido}|${p.cor}`;
  if (!anima || anima.chave !== chave) {
    anima = prepararEfeito(f, p);
    anima.chave = chave;
    // gradientes usados no "colorido" de Cor fixa / Respirar / Sombra (anéis em volta do O e colunas)
    const anel = cena.aneis10, col = cena.colunas14;
    anima.gradiente = cena.teclas.map((k) => {
      const ia = anel.findIndex((g) => g.includes(k)), ic = col.findIndex((g) => g.includes(k));
      return f[2] === "Respire" ? (ic < 7 ? mistura(RGB.azul, RGB.verde, ic / 7) : mistura(RGB.verde, RGB.laranja, (ic - 7) / 6))
        : (ia < 5 ? mistura(RGB.vermelho, RGB.verde, ia / 5) : mistura(RGB.verde, RGB.azul, (ia - 5) / 4));
    });
    if (f[2] === "Shadow_disappear") anima.alfa.fill(200);
  }
  anima.velocidade = p.velocidade ?? 2;
  anima.brilho = p.brilho ?? 4;
}

let antes = 0, proxSimulado = 0;
function quadro(agora) {
  requestAnimationFrame(quadro);
  const dt = Math.max(0, Math.min(250, agora - (antes || agora))); // nunca negativo nem gigante (aba escondida)
  antes = agora;
  if (!anima || document.hidden || !$("teclado").classList.contains("ativa")) return;
  const a = anima, T = cena.teclas;
  const parado = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  // velocidade 4 = ritmo da prévia do software oficial (que ignora a velocidade); as menores vão ficando mais lentas
  const fator = 2 ** ((4 - a.velocidade) / 2.5);
  if (!parado) {
    a.ms += dt / fator;
    if (PERIODO[a.nome]) {
      a.acc += dt / fator;
      let n = 0;
      while (a.acc >= PERIODO[a.nome] && n++ < 40) { passoEfeito(a); a.acc -= PERIODO[a.nome]; }
    }
    // ninguém digitando há 2 s: aperta teclas sozinho, como a prévia oficial
    if (["Reaction", "Flash_away", "Ripples_shining", "Shadow_disappear"].includes(a.nome) && agora - ultimoToqueReal > 2000 && agora > proxSimulado) {
      apertar(T[Math.floor(Math.random() * T.length)]);
      proxSimulado = agora + (a.nome === "Ripples_shining" ? 1300 : 220 + Math.random() * 380);
    }
  } else if (!a.parado) { for (let n = 0; n < 40; n++) passoEfeito(a); a.parado = true; }
  const luz = a.brilho === 0 ? 0 : 0.35 + a.brilho * 0.1625;
  T.forEach((k, i) => {
    let cor, alfa;
    if (a.tipo === "ciclo") {
      const u = a.unidades.findIndex((g) => g.includes(k));
      cor = u < 0 ? [0, 0, 0] : corDoCiclo(a, u, a.ms * (a.redemoinho ? 1 + 0.4 * Math.sin(a.ms / 900) : 1));
      alfa = u < 0 ? 0 : 200;
    } else if (a.tipo === "roda") {
      const giro = (((a.ang[i] - a.ms / 6100) % 1) + 1) % 1;  // num ponto fixo a cor "volta" (vermelho → magenta → azul…)
      cor = a.multi ? matiz(giro) : mistura(escurece(a.c, 0.12), a.c, 0.5 + 0.5 * Math.cos(giro * 2 * Math.PI));
      alfa = 200;
    } else { cor = a.cor[i]; alfa = a.alfa[i]; }
    k.el.style.setProperty("--c", `rgb(${cor[0]} ${cor[1]} ${cor[2]})`);
    k.el.style.setProperty("--a", (Math.min(1, alfa / 200) * luz).toFixed(3));
  });
}
requestAnimationFrame(quadro);

// ---------- aba Luz ----------
function desenharLuz() {
  if (!previa) return;
  const atual = fxDe(previa.efeito);
  if (!grupo) grupo = atual ? atual[1] : "fixos";
  $("t-grupos").replaceChildren(...GRUPOS.map(([id, nome]) => {
    const b = document.createElement("button");
    b.setAttribute("role", "tab"); b.textContent = nome;
    b.setAttribute("aria-selected", String(id === grupo));
    b.addEventListener("click", () => { grupo = id; if (id !== "meus") appSel = null; desenharLuz(); pintarPrevia(); });
    return b;
  }));
  const cartoes = FX.filter((f) => f[1] === grupo).map((f) => {
    const b = document.createElement("button");
    b.className = "cartao-efeito"; b.setAttribute("aria-pressed", String(f[0] === previa.efeito));
    b.innerHTML = `<span class="tira" style="background:${STRIP[f[6]]}"></span><b>${EFEITOS_PT[f[2]] || f[2]}</b><span class="pequeno">${f[2].replace(/_/g, " ")}</span>`;
    b.addEventListener("click", () => escolherEfeito(f[0]));
    return b;
  });
  if (grupo === "meus") FX_APP.forEach(([id, nome, , tira]) => {
    const b = document.createElement("button");
    const ligado = teclado.efeito_app && teclado.efeito_app.nome === id;
    b.className = "cartao-efeito"; b.setAttribute("aria-pressed", String(appSel === id));
    b.innerHTML = `<span class="tira" style="background:${tira}"></span><b>${nome}</b>` +
      (ligado ? '<span class="ligado">● ligado no teclado</span>' : '<span class="pequeno">efeito do app</span>');
    b.addEventListener("click", () => abrirApp(id));
    cartoes.push(b);
  });
  EM_BREVE.filter(([g]) => g === grupo).forEach(([, nome, nota]) => {
    const b = document.createElement("button");
    b.className = "cartao-efeito"; b.disabled = true;
    b.innerHTML = `<span class="tira" style="background:#C6CAC6"></span><b>${nome}</b><span class="pequeno">${nota}</span>`;
    cartoes.push(b);
  });
  $("t-efeitos").replaceChildren(...cartoes);

  $("t-ef-nome").textContent = atual ? (EFEITOS_PT[atual[2]] || atual[2]) : "—";
  $("t-ef-orig").textContent = atual ? atual[2].replace(/_/g, " ") : "";
  $("t-ef-desc").textContent = atual ? atual[7] : "";
  const passos = (alvo, chave, rotulo) => $(alvo).replaceChildren(...[0, 1, 2, 3, 4].map((v) => {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = v; b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(previa[chave] === v)); b.setAttribute("aria-label", `${rotulo} ${v}`);
    b.addEventListener("click", () => { previa[chave] = v; atualizarLuz(); });
    return b;
  }));
  passos("t-brilho", "brilho", "Brilho");
  passos("t-vel", "velocidade", "Velocidade");
  // controles que o efeito não aceita ficam invisíveis mas ocupam o espaço: a tela não muda de tamanho
  const mostrar = (id, sim) => { const e = $(id); e.classList.toggle("oculto", !sim); e.inert = !sim; };
  mostrar("t-c-brilho", atual && atual[0] !== 21);
  $("t-pintar").classList.toggle("oculto", !(atual && atual[0] === 21));
  mostrar("t-c-vel", atual && atual[3]);
  mostrar("t-c-cor", atual && atual[5]);
  mostrar("t-c-colorido", atual && atual[4]);
  $("t-colorido").checked = previa.colorido;
  $("t-paleta").replaceChildren(...PALETA.map((hex) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "amostra"; b.style.background = `#${hex}`; b.setAttribute("aria-label", `Cor #${hex}`);
    b.setAttribute("aria-pressed", String(!previa.colorido && previa.cor === hex));
    b.addEventListener("click", () => { previa.cor = hex; previa.colorido = false; atualizarLuz(); });
    return b;
  }), (() => {
    const inp = document.createElement("input");
    inp.type = "color"; inp.value = `#${previa.cor || "FFFFFF"}`; inp.setAttribute("aria-label", "Outra cor");
    inp.addEventListener("input", () => { previa.cor = inp.value.slice(1).toUpperCase(); previa.colorido = false; atualizarLuz(false); });
    return inp;
  })());
  const mudou = !mesmo(previa, doTeclado(teclado));
  // com um efeito do app ligado, "Gravar" também serve para voltar a um efeito do próprio teclado
  $("t-gravar").disabled = (!mudou && !teclado.efeito_app) || gravandoT;
  $("t-desfazer").disabled = !mudou || gravandoT;
  desenharApp();
}

// a prévia mostra o efeito do app quando ele está aberto no painel, ou ligado e nada diferente foi escolhido
function mostraApp() {
  return !!(appSel || (teclado.efeito_app && previa && mesmo(previa, doTeclado(teclado))));
}

// ---------- efeitos do app (cor ao vivo) ----------
function abrirApp(id) {
  appSel = id;
  const e = teclado.efeito_app;
  if (e && e.nome === id) appOpcoes = { ...appOpcoes, ...e.opcoes };
  $("a-erro").textContent = "";
  desenharLuz();
  pintarPrevia();
}

function desenharApp() {
  const f = appSel && fxApp(appSel);
  $("t-app").hidden = !f;
  $("t-app").inert = !f;
  if (!f) return;
  const e = teclado.efeito_app, ligado = e && e.nome === appSel;
  $("a-nome").textContent = f[1];
  $("a-desc").textContent = f[2];
  const seg = (alvo, itens, chave) => $(alvo).replaceChildren(...itens.map(([v, rot]) => {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = rot; b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(appOpcoes[chave] === v));
    b.addEventListener("click", () => { appOpcoes[chave] = v; desenharApp(); });
    return b;
  }));
  seg("a-modo", f[4], "modo");
  seg("a-sens", [1, 2, 3, 4, 5].map((n) => [n, String(n)]), "sensibilidade");
  $("a-colorido").checked = !appOpcoes.cor;
  $("a-paleta").replaceChildren(...PALETA.map((hex) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "amostra"; b.style.background = `#${hex}`; b.setAttribute("aria-label", `Cor #${hex}`);
    b.setAttribute("aria-pressed", String(appOpcoes.cor === hex));
    b.addEventListener("click", () => { appOpcoes.cor = hex; desenharApp(); });
    return b;
  }));
  const mudou = !ligado || JSON.stringify(e.opcoes) !== JSON.stringify(appOpcoes);
  $("a-situacao").textContent = !ligado ? "Desligado. Escolha e clique em Ligar; a prévia acima já segue o som."
    : e.situacao === "ligado" ? "Ligado no teclado." : `Esperando o teclado${e.erro ? `: ${e.erro}` : "…"}`;
  $("a-ligar").textContent = ligado ? "Aplicar mudanças" : "Ligar no teclado";
  $("a-ligar").disabled = !mudou;
  $("a-desligar").disabled = !ligado;
}

$("a-colorido").addEventListener("change", () => {
  appOpcoes.cor = $("a-colorido").checked ? null : (PALETA[0]);
  desenharApp();
});
$("a-ligar").addEventListener("click", async () => {
  $("a-erro").textContent = "";
  let r;
  try { r = await window.pywebview.api.efeito_app_ligar(appSel, { ...appOpcoes }); } catch (err) { r = { ok: false, erro: String(err) }; }
  if (!r || !r.ok) { $("a-erro").textContent = `Não ligou: ${(r && r.erro) || "erro desconhecido"}`; return; }
  chipT("Efeito do app ligado ✓", "ok");
  await atualizarTela();
  desenharLuz();
});
$("a-desligar").addEventListener("click", async () => {
  $("a-erro").textContent = "";
  chipT("Voltando ao efeito do teclado…", "trabalhando");
  let r;
  try { r = await window.pywebview.api.efeito_app_desligar(); } catch (err) { r = { ok: false, erro: String(err) }; }
  chipT(r && r.ok ? "Efeito do app desligado ✓" : "Não desligou", r && r.ok ? "ok" : "falha");
  if (!r || !r.ok) $("a-erro").textContent = (r && r.erro) || "erro desconhecido";
  await atualizarTela();
  desenharLuz();
});

// prévia dos efeitos do app: o quadro de verdade (o que vai ou iria para o teclado), ~10 vezes por segundo
let pedindoPrevia = 0, ultimoApp = "null";
setInterval(async () => {
  const nome = appSel || (teclado.efeito_app && teclado.efeito_app.nome);
  if (!nome || !mostraApp() || !cena || !$("teclado").classList.contains("ativa") || document.hidden) return;
  if (pedindoPrevia && performance.now() - pedindoPrevia < 3000) return;  // pedido anterior ainda em andamento
  pedindoPrevia = performance.now();
  try {
    const opcoes = appSel ? appOpcoes : teclado.efeito_app.opcoes;
    const acesas = await window.pywebview.api.efeito_app_previa(nome, { ...opcoes });
    cena.teclas.forEach((k) => {
      const h = acesas[k.nome];
      const [r, g, b] = h ? hexRgb(h) : [0, 0, 0];
      k.el.style.setProperty("--c", `rgb(${r} ${g} ${b})`);
      k.el.style.setProperty("--a", h ? "1" : "0");
    });
  } catch (err) { /* a ponte ainda não está pronta */ }
  pedindoPrevia = 0;
}, 100);

function atualizarLuz(redesenhar = true) {
  if (redesenhar) desenharLuz();
  else {
    const mudou = !mesmo(previa, doTeclado(teclado));
    $("t-gravar").disabled = (!mudou && !teclado.efeito_app) || gravandoT;  // mesma regra de desenharLuz
    $("t-desfazer").disabled = !mudou || gravandoT;
  }
  pintarPrevia();
}

function escolherEfeito(hw) {
  appSel = null;  // saiu do painel do efeito do app (o efeito continua ligado até gravar outro ou desligar)
  // ao trocar de efeito, cada efeito traz o próprio brilho/velocidade/cor guardados no teclado
  const e = (teclado.efeitos || {})[hw] || {};
  previa = { efeito: hw, brilho: e.brilho ?? previa.brilho, velocidade: e.velocidade ?? previa.velocidade,
    colorido: !!e.colorido, cor: e.cor || previa.cor };
  atualizarLuz();
}

$("t-colorido").addEventListener("change", () => { previa.colorido = $("t-colorido").checked; atualizarLuz(); });
$("t-desfazer").addEventListener("click", () => { previa = doTeclado(teclado); grupo = null; atualizarLuz(); });
$("t-gravar").addEventListener("click", async () => {
  $("t-erro").textContent = "";
  const p = { ...previa };
  const r = await gravarT(() => (p.efeito === 21 ? window.pywebview.api.teclado_por_tecla(null)
    : window.pywebview.api.teclado_luz(p.efeito, p.brilho, p.velocidade, p.colorido, p.cor)));
  if (r) previa = null; // recomeça do que o teclado confirmou
});

async function gravarT(chamada) {
  if (gravandoT) return false;
  gravandoT = true;
  chipT("Gravando no teclado…", "trabalhando");
  $("t-gravar").disabled = true;
  let r;
  try { r = await chamada(); } catch (e) { r = { ok: false, erro: String(e) }; }
  gravandoT = false;
  if (r && r.ok) { chipT("Gravado ✓", "ok"); await atualizarTela(); return true; }
  chipT("Não gravou", "falha");
  $("t-erro").textContent = `Não deu para gravar: ${(r && r.erro) || "erro desconhecido"}`;
  $("t-aviso2").textContent = $("t-erro").textContent;
  atualizarLuz();
  return false;
}

// ---------- aba Geral ----------
function desenharGeral(t) {
  const sel = $("t-sono");
  if (!sel.options.length) {
    SONOS_T.forEach((n) => sel.add(new Option(n === 1 ? "1 minuto" : `${String(n).replace(".", ",")} minutos`, n)));
    sel.addEventListener("change", () => gravarT(() => window.pywebview.api.teclado_sono(Number(sel.value))));
  }
  if (document.activeElement !== sel && t.sono_min) sel.value = String(t.sono_min);
  $("t-debounce").replaceChildren(...[1, 2, 3, 4].map((n) => {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = n; b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(t.debounce === n));
    b.addEventListener("click", () => { if (n !== t.debounce) gravarT(() => window.pywebview.api.teclado_debounce(n)); });
    return b;
  }));
  $("t-fw").textContent = t.firmware ? `V${t.firmware}` : "—";
  $("t-lido").textContent = hora(t.lido_em);
}

// ---------- estado ----------
function mostrarTeclado(t) {
  teclado = t;
  conexao("t", t);
  bateria("t", t.bateria);
  const nome = EFEITOS_PT[t.efeito_nome] || t.efeito_nome || "—";
  $("t-resumo").textContent = t.efeito_nome ? `${nome} · brilho ${t.brilho}` : "—";
  $("t-sub").textContent = (NOMES_CONEXAO[t.conexao] || "Desconectado") +
    (t.conectado ? `. Firmware ${t.firmware}.` : " — mostrando o último estado lido.");
  if (!gravandoT && !$("t-chip").textContent && t.lido_em) chipT(`Lido às ${hora(t.lido_em)}`);
  iluminarTeclado(t);
  if (t.efeito && fxDe(t.efeito)) {
    if (!previa) {
      previa = doTeclado(t); grupo = null;
      if (t.efeito_app) { grupo = "meus"; appSel = t.efeito_app.nome; appOpcoes = { ...appOpcoes, ...t.efeito_app.opcoes }; }
      desenharLuz(); pintarPrevia();
    }
    else atualizarLuz(false); // não redesenha a cada 2 s (fecharia o seletor de cor aberto)
  }
  const app = JSON.stringify(t.efeito_app || null);  // efeito do app ligou/desligou/mudou de situação
  if (app !== ultimoApp) { ultimoApp = app; if (previa) desenharLuz(); pintarPrevia(); }
  desenharGeral(t);
}

desenharTeclado($("teclado-grande"), 37);
todos("#teclado-grande .tecla").forEach((s) => s.classList.add("luz"));
