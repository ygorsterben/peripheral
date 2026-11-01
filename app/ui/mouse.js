// Gerenciador de Periféricos — tela do mouse (fase 2: grava de verdade).
// Usa $, todos, milhar, minutos, hora, conexao e bateria de app.js.
"use strict";

const API = () => window.pywebview.api;
let mouse = {};          // último estado recebido do Python
let botaoSel = 5;        // botão selecionado no mapa (numeração do software: 1..6)
let gravando = false;

const POLLINGS = [125, 250, 500, 1000];
const SONOS = [1, 2, 5, 6, 10, 15, 20, 30];
const PADRAO_DPI = [800, 1600, 2400, 3200, 4800, 12000];
const PADRAO_CORES = ["FF0000", "00FF00", "0000FF", "FF00FF", "FF8800", "00FFFF"];
// Botão N do software → posição na tabela do mouse (o 4 e o 5 são trocados; ver perifericos/mouse.py)
const INDICE = { 1: 0, 2: 1, 3: 2, 4: 4, 5: 3, 6: 5 };
const ONDE = { 1: "botão esquerdo", 2: "botão direito", 3: "clique da roda", 4: "lateral da frente", 5: "lateral de trás", 6: "embaixo do mouse" };

const NOMES = {
  clique: { esquerdo: "Clique esquerdo", direito: "Clique direito", meio: "Clique do meio", voltar: "Voltar", avancar: "Avançar" },
  midia: { volume_mais: "Volume +", volume_menos: "Volume −", mudo: "Mudo", player: "Abrir o player", tocar_pausar: "Tocar / pausar",
    anterior: "Faixa anterior", proxima: "Próxima faixa", parar: "Parar" },
  atalho: { brilho_mais: "Brilho da tela +", brilho_menos: "Brilho da tela −", calculadora: "Calculadora",
    meu_computador: "Meu computador", email: "E-mail", navegador: "Navegador" },
};

// ---------- teclas (KeyboardEvent.code → código HID) ----------
const HID = {};
"ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").forEach((l, i) => { HID[`Key${l}`] = [0x04 + i, l]; });
"1234567890".split("").forEach((n, i) => { HID[`Digit${n}`] = [0x1E + i, n]; });
for (let i = 1; i <= 12; i++) HID[`F${i}`] = [0x39 + i, `F${i}`];
Object.assign(HID, {
  Enter: [0x28, "Enter"], Escape: [0x29, "Esc"], Backspace: [0x2A, "Backspace"], Tab: [0x2B, "Tab"], Space: [0x2C, "Espaço"],
  Minus: [0x2D, "-"], Equal: [0x2E, "="], BracketLeft: [0x2F, "["], BracketRight: [0x30, "]"], Backslash: [0x31, "\\"],
  Semicolon: [0x33, ";"], Quote: [0x34, "'"], Backquote: [0x35, "`"], Comma: [0x36, ","], Period: [0x37, "."], Slash: [0x38, "/"],
  CapsLock: [0x39, "Caps Lock"], PrintScreen: [0x46, "Print Screen"], ScrollLock: [0x47, "Scroll Lock"], Pause: [0x48, "Pause"],
  Insert: [0x49, "Insert"], Home: [0x4A, "Home"], PageUp: [0x4B, "Page Up"], Delete: [0x4C, "Delete"], End: [0x4D, "End"],
  PageDown: [0x4E, "Page Down"], ArrowRight: [0x4F, "→"], ArrowLeft: [0x50, "←"], ArrowDown: [0x51, "↓"], ArrowUp: [0x52, "↑"],
  NumpadDivide: [0x54, "Num /"], NumpadMultiply: [0x55, "Num *"], NumpadSubtract: [0x56, "Num −"], NumpadAdd: [0x57, "Num +"],
  NumpadEnter: [0x58, "Num Enter"], NumpadDecimal: [0x63, "Num ."], ContextMenu: [0x65, "Menu"],
});
for (let i = 1; i <= 9; i++) HID[`Numpad${i}`] = [0x58 + i, `Num ${i}`];
HID.Numpad0 = [0x62, "Num 0"];
const NOME_HID = Object.fromEntries(Object.values(HID).map(([c, n]) => [c, n]));
const MODS = [["Ctrl", 0x01], ["Shift", 0x02], ["Alt", 0x04], ["Win", 0x08]];

function nomeTecla(codigo, mods) {
  const partes = MODS.filter(([, bit]) => mods & bit).map(([n]) => n);
  partes.push(NOME_HID[codigo] || `tecla 0x${Number(codigo).toString(16)}`);
  return partes.join(" + ");
}

function descrever(f) {
  if (!f) return "—";
  if (NOMES[f.tipo]) return NOMES[f.tipo][f.valor] || "Outra função";
  if (f.tipo === "tecla") return nomeTecla(f.valor, f.modificadores);
  return { dpi: "Ciclo de DPI", desativar: "Desativado", macro: "Macro", disparo: "Disparo rápido" }[f.tipo] || "Outra função";
}

// ---------- gravação comum ----------
function chip(texto, tipo) {
  const c = $("m-chip");
  c.textContent = texto;
  c.className = "chip" + (tipo ? ` ${tipo}` : "");
}

async function gravar(chamada, erroEm) {
  if (gravando) return false;
  gravando = true;
  chip("Gravando no mouse…", "trabalhando");
  let r;
  try { r = await chamada(); } catch (e) { r = { ok: false, erro: String(e) }; }
  gravando = false;
  if (r && r.ok) {
    chip("Gravado ✓", "ok");
    await atualizarTela();
    return true;
  }
  chip("Não gravou", "falha");
  const msg = r && r.erro ? r.erro : "erro desconhecido";
  if (erroEm) erroEm.textContent = `Não deu para gravar: ${msg}`;
  else $("m-aviso2").textContent = `Não deu para gravar: ${msg}`;
  return false;
}

// ---------- preencher a tela ----------
function mostrarMouse(m) {
  mouse = m;
  conexao("m", m);
  bateria("m", m.bateria);
  const ativo = m.dpi ? m.dpi[m.ativo] : null;
  $("m-resumo").textContent = ativo ? `${milhar(ativo)} DPI · ${m.polling} Hz` : "—";
  $("m-sub").textContent = (NOMES_CONEXAO[m.conexao] || "Desconectado") +
    (m.conectado ? ". As mudanças são gravadas no mouse na hora." : " — mostrando o último estado lido.");
  $("m-mexa").hidden = !m.esperando_mouse;
  if (!gravando && !$("m-chip").textContent && m.lido_em) chip(`Lido às ${hora(m.lido_em)}`);
  desenharEscada(m);
  desenharPolling(m);
  desenharSono(m);
  desenharMapa(m);
}

function desenharEscada(m) {
  const escada = $("escada");
  if (!m.dpi) return;
  const log = (d) => Math.log(d / 400) / Math.log(18000 / 400);
  escada.replaceChildren(...m.dpi.map((d, i) => {
    const b = document.createElement("button");
    const fora = i >= m.niveis;
    b.className = "degrau" + (i === m.ativo ? " ativo" : "") + (fora ? " fora" : "");
    b.disabled = fora;
    b.setAttribute("aria-label", `Usar ${milhar(d)} DPI`);
    b.innerHTML = `<span class="num"><span class="led" style="background:#${m.cores?.[i] || "FFFFFF"}"></span>${milhar(d)}</span>` +
      `<span class="barra" style="height:${Math.round(20 + 76 * log(d))}px"></span>`;
    b.addEventListener("click", () => { if (i !== m.ativo) gravar(() => API().mouse_dpi_ativo(i)); });
    return b;
  }));
}

function desenharPolling(m) {
  $("m-polling").replaceChildren(...POLLINGS.map((hz) => {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(hz === m.polling));
    b.textContent = `${hz} Hz`;
    b.addEventListener("click", () => { if (hz !== m.polling) gravar(() => API().mouse_polling(hz)); });
    return b;
  }));
}

function desenharSono(m) {
  const sel = $("m-sono");
  if (!sel.options.length) {
    SONOS.forEach((n) => sel.add(new Option(n === 1 ? "1 minuto" : `${n} minutos`, n)));
    sel.addEventListener("change", () => gravar(() => API().mouse_sono(Number(sel.value))));
  }
  if (document.activeElement !== sel && m.sono_min) sel.value = String(Math.round(m.sono_min));
}

// ---------- mapa dos botões ----------
// pontos no desenho (unidades do viewBox 140×235) e posição da etiqueta; tirado do protótipo aprovado
const MAPA = {
  1: [38, 28.5, "E", 23], 2: [98, 28.5, "D", 23], 3: [71, 49, "D", 74],
  4: [14, 91, "E", 90], 5: [14, 115, "E", 142], 6: [95.5, 111, "D", 132],
};
const O = { x: 141, y: 15, s: 250 / 235 }, LW = 132, LH = 44, CW = 432;  // etiquetas iguais, sem invadir o desenho (141–290)

function desenharMapa(m) {
  const linhas = $("mapa-linhas"), rotulos = $("mapa-rotulos");
  const svg = [];
  rotulos.replaceChildren();
  for (const n of [1, 2, 3, 4, 5, 6]) {
    const [vx, vy, lado, topo] = MAPA[n];
    const ax = Math.round(O.x + vx * O.s), ay = Math.round(O.y + vy * O.s);
    const sel = n === botaoSel, embaixo = n === 6;
    const x1 = lado === "E" ? LW : CW - LW;
    svg.push(`<line x1="${x1}" y1="${topo + LH / 2}" x2="${ax}" y2="${ay}" stroke="${sel ? "#2647C9" : "#8A9096"}" stroke-width="1.4"${embaixo ? ' stroke-dasharray="4 3"' : ""}/>`,
      `<circle cx="${ax}" cy="${ay}" r="3.5" fill="${sel ? "#2647C9" : "#FFFFFF"}" stroke="${sel ? "#FFFFFF" : "#5B6168"}" stroke-width="1.4"/>`);
    const b = document.createElement("button");
    b.type = "button";
    b.className = "rotulo-botao" + (sel ? " sel" : "");
    b.style.cssText = `left:${lado === "E" ? 0 : CW - LW}px;top:${topo}px;width:${LW}px;height:${LH}px`;
    const f = m.botoes ? m.botoes[INDICE[n]] : null;
    b.innerHTML = `<span class="pequeno">Botão ${n}${n === 1 ? " · travado" : ""}</span><b>${descrever(f)}</b>`;
    b.title = `Botão ${n}: ${descrever(f)}`;  // texto inteiro, caso a etiqueta corte com "…"
    b.setAttribute("aria-label", `Botão ${n}, ${ONDE[n]}: ${descrever(f)}`);
    b.addEventListener("click", () => selecionarBotao(n));
    rotulos.append(b);
  }
  linhas.innerHTML = svg.join("");
  todos("#mapa-botoes .zona").forEach((z) => z.classList.toggle("sel", Number(z.dataset.botao) === botaoSel));
  const trocar = $("m-trocar");
  trocar.disabled = botaoSel === 1;
  trocar.textContent = botaoSel === 1 ? "Botão 1 travado: é o clique esquerdo" : `Trocar função do Botão ${botaoSel}`;
}

function selecionarBotao(n) {
  botaoSel = n;
  desenharMapa(mouse);
}
todos("#mapa-botoes .zona").forEach((z) => z.addEventListener("click", () => selecionarBotao(Number(z.dataset.botao))));

// ---------- diálogo: editar DPI ----------
let edicao = null;
const passo = (v) => (v <= 10000 ? 50 : v <= 12000 ? 100 : 1000);
const arredondar = (v) => { v = Math.max(50, Math.min(18000, Math.round(Number(v) || 50))); const p = passo(v); return Math.round(v / p) * p; };

function abrirDpi() {
  if (!mouse.dpi) return;
  edicao = { dpi: [...mouse.dpi], cores: [...mouse.cores], niveis: mouse.niveis, ativo: mouse.ativo };
  $("dpi-erro").textContent = "";
  desenharDpi();
  $("dlg-dpi").showModal();
}

function desenharDpi() {
  $("dpi-niveis").replaceChildren(...[1, 2, 3, 4, 5, 6].map((n) => {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = n; b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(n === edicao.niveis));
    b.addEventListener("click", () => { edicao.niveis = n; edicao.ativo = Math.min(edicao.ativo, n - 1); desenharDpi(); });
    return b;
  }));
  $("dpi-linhas").replaceChildren(...edicao.dpi.flatMap((d, i) => {
    const fora = i >= edicao.niveis;
    const nivel = document.createElement("b"); nivel.textContent = i + 1; nivel.className = fora ? "fora" : "";
    const num = document.createElement("input");
    Object.assign(num, { type: "number", min: 50, max: 18000, step: passo(d), value: d, disabled: fora });
    num.setAttribute("aria-label", `DPI do nível ${i + 1}`);
    num.addEventListener("change", () => { edicao.dpi[i] = arredondar(num.value); num.value = edicao.dpi[i]; num.step = passo(edicao.dpi[i]); });
    const cor = document.createElement("input");
    Object.assign(cor, { type: "color", value: `#${edicao.cores[i]}`, disabled: fora });
    cor.setAttribute("aria-label", `Cor do LED do nível ${i + 1}`);
    cor.addEventListener("input", () => { edicao.cores[i] = cor.value.slice(1).toUpperCase(); });
    const radio = document.createElement("input");
    Object.assign(radio, { type: "radio", name: "dpi-ativo", checked: i === edicao.ativo, disabled: fora });
    radio.setAttribute("aria-label", `Usar o nível ${i + 1} agora`);
    radio.addEventListener("change", () => { edicao.ativo = i; });
    const r = document.createElement("span"); r.className = "radio-celula"; r.append(radio);
    return [nivel, num, cor, r];
  }));
}

$("m-editar-dpi").addEventListener("click", abrirDpi);
$("dlg-dpi").addEventListener("keydown", (ev) => { if (ev.key === "Enter" && ev.target.tagName === "INPUT") { ev.preventDefault(); ev.target.blur(); } });
$("dpi-padrao").addEventListener("click", () => {
  edicao = { dpi: [...PADRAO_DPI], cores: [...PADRAO_CORES], niveis: 6, ativo: 4 };
  desenharDpi();
});
$("dpi-gravar").addEventListener("click", async () => {
  $("dpi-erro").textContent = "";
  todos("#dpi-linhas input[type=number]").forEach((inp, i) => { edicao.dpi[i] = arredondar(inp.value); });
  const ok = await gravar(() => API().mouse_tabela(edicao.dpi, edicao.niveis, edicao.ativo, edicao.cores), $("dpi-erro"));
  if (ok) $("dlg-dpi").close();
});

// ---------- diálogo: trocar função ----------
const CATEGORIAS = [
  ["clique", "Mouse", "Funções de clique e o ciclo de DPI."],
  ["tecla", "Tecla ou atalho", "O botão digita uma tecla, sozinha ou com Ctrl, Shift, Alt e Win."],
  ["midia", "Multimídia", "Controle de som e do player."],
  ["atalho", "Atalho do Windows", "Abre programas ou ajusta o brilho da tela."],
  ["desativar", "Desativar", "O botão para de fazer qualquer coisa. Útil para um botão que você aperta sem querer."],
  ["embreve", "Em breve", "Ainda falta decifrar como o mouse guarda estas funções: duplo clique, rolagem, disparo rápido e macro."],
];
let escolha = null, categoria = "clique", tecla = { codigo: null, mods: 0 }, capturando = false;

function abrirFuncao() {
  if (botaoSel === 1 || !mouse.botoes) return;
  const atual = mouse.botoes[INDICE[botaoSel]];
  escolha = { ...atual };
  categoria = ["clique", "dpi"].includes(atual.tipo) ? "clique" : CATEGORIAS.some(([c]) => c === atual.tipo) ? atual.tipo : "clique";
  tecla = atual.tipo === "tecla" ? { codigo: atual.valor, mods: atual.modificadores } : { codigo: null, mods: 0 };
  $("fn-qual").textContent = `Botão ${botaoSel} · ${ONDE[botaoSel]}`;
  $("fn-agora").textContent = descrever(atual);
  $("fn-erro").textContent = "";
  desenharFuncao();
  $("dlg-funcao").showModal();
}

function opcao(rotulo, f, desativada) {
  const b = document.createElement("button");
  b.type = "button"; b.className = "opcao"; b.textContent = rotulo; b.disabled = !!desativada;
  const igual = escolha && f && escolha.tipo === f.tipo && escolha.valor === f.valor;
  b.setAttribute("aria-pressed", String(!!igual));
  if (f) b.addEventListener("click", () => { escolha = f; desenharFuncao(); });
  return b;
}

function desenharFuncao() {
  $("fn-categorias").replaceChildren(...CATEGORIAS.map(([id, rotulo]) => {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = rotulo;
    b.className = "categoria" + (id === categoria ? " atual" : "");
    b.addEventListener("click", () => {
      categoria = id;
      if (id === "desativar") escolha = { tipo: "desativar" };
      if (id === "tecla" && tecla.codigo) escolha = { tipo: "tecla", valor: tecla.codigo, modificadores: tecla.mods };
      desenharFuncao();
    });
    return b;
  }));
  $("fn-dica").textContent = CATEGORIAS.find(([c]) => c === categoria)[2];
  const ops = $("fn-opcoes");
  ops.replaceChildren();
  $("fn-tecla").hidden = categoria !== "tecla";
  if (categoria === "clique") {
    Object.entries(NOMES.clique).forEach(([v, n]) => ops.append(opcao(n, { tipo: "clique", valor: v })));
    ops.append(opcao("Ciclo de DPI", { tipo: "dpi" }));
  } else if (categoria === "midia" || categoria === "atalho") {
    Object.entries(NOMES[categoria]).forEach(([v, n]) => ops.append(opcao(n, { tipo: categoria, valor: v })));
  } else if (categoria === "desativar") {
    ops.append(opcao("Desativar o botão", { tipo: "desativar" }));
  } else if (categoria === "embreve") {
    ["Duplo clique", "Rolar para cima", "Rolar para baixo", "Disparo rápido", "Macro"].forEach((n) => ops.append(opcao(n, null, true)));
  }
  $("fn-mods").replaceChildren(...MODS.map(([n, bit]) => {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = n; b.setAttribute("aria-pressed", String(!!(tecla.mods & bit)));
    b.addEventListener("click", () => { tecla.mods ^= bit; if (tecla.codigo) escolha = { tipo: "tecla", valor: tecla.codigo, modificadores: tecla.mods }; desenharFuncao(); });
    return b;
  }));
  $("fn-combo").textContent = tecla.codigo ? nomeTecla(tecla.codigo, tecla.mods) : "—";
  $("fn-capturar").textContent = capturando ? "Aperte a tecla agora…" : "Clique aqui e aperte a tecla";
  $("fn-capturar").classList.toggle("ouvindo", capturando);
  $("fn-gravar").disabled = !escolha || ["outro", "macro", "disparo"].includes(escolha.tipo);
}

$("fn-capturar").addEventListener("click", () => { capturando = true; desenharFuncao(); });
$("dlg-funcao").addEventListener("keydown", (ev) => {
  if (!capturando) return;
  if (["ControlLeft", "ControlRight", "ShiftLeft", "ShiftRight", "AltLeft", "AltRight", "MetaLeft", "MetaRight"].includes(ev.code)) return;
  ev.preventDefault();
  const h = HID[ev.code];
  if (!h) { $("fn-erro").textContent = "Essa tecla ainda não é suportada."; return; }
  const mods = (ev.ctrlKey ? 1 : 0) | (ev.shiftKey ? 2 : 0) | (ev.altKey ? 4 : 0) | (ev.metaKey ? 8 : 0);
  tecla = { codigo: h[0], mods: mods || tecla.mods };
  escolha = { tipo: "tecla", valor: tecla.codigo, modificadores: tecla.mods };
  capturando = false;
  $("fn-erro").textContent = "";
  desenharFuncao();
});
$("m-trocar").addEventListener("click", abrirFuncao);
$("dlg-funcao").addEventListener("close", () => { capturando = false; });
$("fn-padrao").addEventListener("click", async () => {
  const ok = await gravar(() => API().mouse_botao(INDICE[botaoSel], { tipo: "padrao" }), $("fn-erro"));
  if (ok) $("dlg-funcao").close();
});
$("fn-gravar").addEventListener("click", async () => {
  const ok = await gravar(() => API().mouse_botao(INDICE[botaoSel], escolha), $("fn-erro"));
  if (ok) $("dlg-funcao").close();
});

// ---------- cor do desenho do mouse (salva no PC) ----------
function corMouse(hex) {
  const c = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const mix = (alvo, f) => `rgb(${c.map((v, i) => Math.round(v + (alvo[i] - v) * f)).join(" ")})`;
  const raiz = document.documentElement.style;
  raiz.setProperty("--mouse-claro", mix([255, 255, 255], 0.14));
  raiz.setProperty("--mouse-meio", `#${hex}`);
  raiz.setProperty("--mouse-escuro", mix([0, 0, 0], 0.45));
  $("cor-mouse").value = `#${hex}`;
  todos("[data-cor-mouse]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.corMouse === hex)));
}
function escolherCorMouse(hex) {
  corMouse(hex);
  window.pywebview.api.salvar_preferencia("cor_mouse", hex);
}
todos("[data-cor-mouse]").forEach((b) => b.addEventListener("click", () => escolherCorMouse(b.dataset.corMouse)));
$("cor-mouse").addEventListener("change", () => escolherCorMouse($("cor-mouse").value.slice(1).toUpperCase()));
