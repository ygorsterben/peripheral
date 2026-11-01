// Gerenciador de Periféricos — interface (fase 1: só leitura).
// Fala com o Python por window.pywebview.api (estado, atualizar, versao). Sem bibliotecas externas.
"use strict";

const $ = (id) => document.getElementById(id);
const todos = (sel) => document.querySelectorAll(sel);
const NOMES_CONEXAO = { cabo: "Pelo cabo", dongle: "Pelo receptor 2,4 GHz", "bluetooth 5.0": "Pelo Bluetooth", "bluetooth 3.0": "Pelo Bluetooth" };
const EFEITOS_PT = {
  Fixed_on: "Cor fixa", Respire: "Respirar", Rainbow: "Arco-íris", Flash_away: "Clarão", Raindrops: "Gotas de chuva",
  Rainbow_wheel: "Roda de cores", Ripples_shining: "Ondulação", Stars_twinkle: "Estrelas", Shadow_disappear: "Sombra",
  Retro_snake: "Cobrinha", Neon_stream: "Fluxo neon", Reaction: "Reação", Sine_wave: "Onda", "Retinue scanning": "Varredura",
  "Rotating windmill": "Moinho", "Colorful waterfall": "Cascata", Blossoming: "Florescer", "Rotating storm": "Redemoinho",
  "Self-define": "Por tecla", OFF: "Desligada",
};
window.NOMES_CONEXAO = NOMES_CONEXAO;
const milhar = (n) => Number(n).toLocaleString("pt-BR");
const minutos = (m) => (m == null ? "—" : `${String(m).replace(".", ",")} min`);
const hora = (iso) => (iso ? iso.slice(11, 16) : "—");

// ---------- navegação ----------
function mostrarTela() {
  const alvo = (location.hash || "#inicio").slice(1);
  todos(".tela").forEach((t) => t.classList.toggle("ativa", t.id === alvo));
  ajustarTela();
}

// ---------- ajuste automático ao tamanho da janela ----------
// Cada tela é desenhada para BASE_L px de largura. Mede a altura de que a tela atual precisa nessa largura e
// aplica um zoom para caber tudo na janela, sem barra de rolagem (aumenta até ZOOM_MAX em janelas grandes).
const BASE_L = 1120, ZOOM_MAX = 1.3;
let ajusteAgendado = false;
function ajustarTela() {
  // com uma lista (select) aberta, mexer no zoom a fecha: espera o usuário terminar de escolher
  const ativo = document.activeElement;
  if (ativo && ativo.tagName === "SELECT") {
    if (!ativo.dataset.ajustePendente) {
      ativo.dataset.ajustePendente = "1";
      ativo.addEventListener("blur", () => { delete ativo.dataset.ajustePendente; ajustarTela(); }, { once: true });
    }
    return;
  }
  if (ajusteAgendado) return;
  ajusteAgendado = true;
  requestAnimationFrame(() => {
    ajusteAgendado = false;
    const tela = document.querySelector(".tela.ativa");
    if (!tela) return;
    document.body.style.zoom = 1;
    tela.style.width = `${BASE_L}px`;
    tela.style.height = "auto";
    tela.classList.add("medindo");
    const medir = () => Math.max(tela.scrollHeight, ...[...tela.querySelectorAll("main")].map((m) => m.scrollHeight));
    // telas com abas (teclado: Luz, Geral, Teclas) usam a altura da aba mais alta, para o zoom não mudar entre abas
    const abas = [...tela.querySelectorAll(".aba")];
    let precisa = medir();
    if (abas.length) {
      precisa = Math.max(...abas.map((aba) => {
        abas.forEach((x) => { x.style.display = x === aba ? "block" : "none"; });
        return medir();
      }));
      abas.forEach((x) => { x.style.display = ""; });
    }
    tela.classList.remove("medindo");
    const estimativa = Math.min(ZOOM_MAX, window.innerWidth / BASE_L, window.innerHeight / precisa);
    let z = estimativa;
    const aplicar = () => {
      document.body.style.zoom = z;
      tela.style.width = `${window.innerWidth / z}px`;
      tela.style.height = `${window.innerHeight / z}px`;
    };
    // Mesma tela, mesma janela e mesma estimativa: reaplica o zoom já conferido, sem passos intermediários.
    // (O estado chega a cada 2 s; trocar o zoom toda vez fechava listas abertas, como a do modo de repetição.)
    const chave = `${tela.id}|${window.innerWidth}x${window.innerHeight}|${estimativa.toFixed(4)}`;
    if (zoomConferido.chave === chave) {
      z = zoomConferido.z;
      aplicar();
      return;
    }
    aplicar();
    // conferência: a medição acima é uma estimativa (ex.: aba Teclas com a macro aberta e janela baixa ficava cortada).
    // Se algo ainda transborda no tamanho real, diminui o zoom na proporção e confere de novo.
    for (let i = 0; i < 4; i++) {
      const sobra = Math.max(0, ...[...tela.querySelectorAll("main")].map((m) => m.scrollHeight / Math.max(1, m.clientHeight)));
      if (sobra <= 1.005) break;
      z /= sobra;
      aplicar();
    }
    zoomConferido = { chave, z };
  });
}
let zoomConferido = { chave: "", z: 1 };
window.addEventListener("resize", ajustarTela);
new MutationObserver(ajustarTela).observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["hidden"] });
window.addEventListener("hashchange", mostrarTela);
todos("[data-ir]").forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.ir; }));

// ---------- desenho do teclado (miniatura, mesmo layout do protótipo) ----------
// rótulos curtos das teclas (desenho clicável)
const ROTULOS = { esc: "Esc", back: "⌫", del: "Del", scroll: "Scr", calc: "Calc", numlock: "Num", tab: "Tab", caps: "Caps",
  enter: "Enter", shift: "Shift", rshift: "Shift", ctrl: "Ctrl", win: "Win", alt: "Alt", ralt: "Alt", fn: "Fn",
  space: "", home: "Home", pgup: "PgUp", pgdn: "PgDn", up: "↑", down: "↓", left: "←", right: "→",
  "num/": "/", "num*": "*", "num-": "−", "num+": "+", "num.": ".", numenter: "Ent",
  num0: "0", num1: "1", num2: "2", num3: "3", num4: "4", num5: "5", num6: "6", num7: "7", num8: "8", num9: "9" };

function desenharTeclado(alvo, P, clicavel = false) {
  const GAP = 2, PAD = 10, NAV = 15.25, NUM = 16.5, W = 20.5;
  const Y = [0, 1.3, 2.3, 3.3, 4.3, 5.3];
  // layout real do F99 Pro; o nome de cada tecla serve para a prévia dos efeitos (colunas, fileiras, anéis...)
  const L = [];
  const put = (n, x, r, w = 1, h = 1) => L.push({ n, x, r, w, h });
  put("esc", 0, 0);
  ["f1", "f2", "f3", "f4"].forEach((k, i) => put(k, 2 + i, 0));
  ["f5", "f6", "f7", "f8"].forEach((k, i) => put(k, 6.5 + i, 0));
  ["f9", "f10", "f11", "f12"].forEach((k, i) => put(k, 11 + i, 0));
  put("del", NAV, 0); put("scroll", NUM, 0); put("calc", NUM + 1, 0);
  ["`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "="].forEach((k, i) => put(k, i, 1));
  put("back", 13, 1, 2); put("home", NAV, 1); ["numlock", "num/", "num*", "num-"].forEach((k, i) => put(k, NUM + i, 1));
  put("tab", 0, 2, 1.5); ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "[", "]"].forEach((k, i) => put(k, 1.5 + i, 2));
  put("\\", 13.5, 2, 1.5); put("pgup", NAV, 2); ["num7", "num8", "num9"].forEach((k, i) => put(k, NUM + i, 2)); put("num+", NUM + 3, 2, 1, 2);
  put("caps", 0, 3, 1.75); ["a", "s", "d", "f", "g", "h", "j", "k", "l", ";", "'"].forEach((k, i) => put(k, 1.75 + i, 3));
  put("enter", 12.75, 3, 2.25); put("pgdn", NAV, 3); ["num4", "num5", "num6"].forEach((k, i) => put(k, NUM + i, 3));
  put("shift", 0, 4, 2.25); ["z", "x", "c", "v", "b", "n", "m", ",", ".", "/"].forEach((k, i) => put(k, 2.25 + i, 4));
  put("rshift", 12.25, 4, 1.75); put("up", 14.25, 4); ["num1", "num2", "num3"].forEach((k, i) => put(k, NUM + i, 4)); put("numenter", NUM + 3, 4, 1, 2);
  put("ctrl", 0, 5, 1.25); put("win", 1.25, 5, 1.25); put("alt", 2.5, 5, 1.25); put("space", 3.75, 5, 6.25); put("ralt", 10, 5); put("fn", 11, 5, 1.25);
  put("left", 13.25, 5); put("down", 14.25, 5); put("right", NAV, 5); put("num0", NUM, 5, 2); put("num.", NUM + 2, 5);
  const caps = ["#D9DAD3", "#C4C7C2", "#A2A7A5", "#7A8180", "#5A6162", "#454A4D"];
  alvo.style.cssText = `position:relative;width:${PAD * 2 + Math.round(W * P) - GAP}px;height:${PAD * 2 + Math.round(6.3 * P) - GAP}px;` +
    "border-radius:10px;background:linear-gradient(180deg,#24272B,#15171A);box-shadow:inset 0 1px 0 rgba(255,255,255,.08),0 10px 24px rgba(31,35,40,.28)";
  alvo.replaceChildren(...L.map((k) => {
    const s = document.createElement(clicavel ? "button" : "span");
    s.className = "tecla";
    if (clicavel) {
      s.type = "button";
      s.textContent = ROTULOS[k.n] ?? k.n.toUpperCase();
      s.setAttribute("aria-label", `Tecla ${ROTULOS[k.n] || k.n}`);
    }
    s.dataset.x = (k.x + k.w / 2) / W;
    s.dataset.nome = k.n;
    s.dataset.l = k.x; s.dataset.t = Y[k.r]; s.dataset.w = k.w; s.dataset.h = k.h; s.dataset.r = k.r;
    s.dataset.y = (Y[k.r] + k.h / 2) / 6.3;
    s.style.cssText = `position:absolute;left:${PAD + Math.round(k.x * P)}px;top:${PAD + Math.round(Y[k.r] * P)}px;` +
      `width:${Math.round(k.w * P) - GAP}px;height:${Math.round(k.h * P) - GAP}px;border-radius:3px;background:${caps[k.r]};` +
      "box-shadow:inset 0 -2px 0 rgba(0,0,0,.2)" +
      (clicavel ? `;border:0;padding:3px 5px;cursor:pointer;display:flex;align-items:flex-end;justify-content:${k.w > 1.4 ? "flex-start" : "center"};` +
        `font:600 ${Math.round(P / 4)}px/1 var(--fonte);text-transform:uppercase;color:${k.r < 3 ? "#4A4F54" : "#E6E8E6"}` : "");
    return s;
  }));
  const roda = document.createElement("span");
  const kd = Math.round(1.3 * P);
  roda.style.cssText = `position:absolute;left:${PAD + Math.round((NUM + 2.4) * P)}px;top:${PAD - 4}px;width:${kd}px;height:${kd}px;` +
    "border-radius:50%;background:conic-gradient(from 200deg,#F2F3F1,#9DA1A3,#E8E9E6,#8C9093,#F2F3F1);box-shadow:0 2px 5px rgba(0,0,0,.5)";
  alvo.append(roda);
}

function iluminarTeclado(t) {
  // cor do efeito atual; efeitos com várias cores (ou "colorido") viram um arco-íris na miniatura
  const ligado = t.conectado !== false && t.efeito_nome !== "OFF";
  const multi = t.colorido || ["Rainbow", "Rainbow_wheel", "Rotating windmill", "Colorful waterfall", "Blossoming"].includes(t.efeito_nome);
  todos("#mini-teclado .tecla").forEach((s) => {
    if (!ligado || !t.efeito_nome) { s.style.outline = "none"; s.style.filter = "none"; return; }
    const c = multi ? `hsl(${Math.round(s.dataset.x * 300)} 90% 62%)` : `#${t.cor || "9B4DFF"}`;
    s.style.boxShadow = `0 0 0 1px ${c}, 0 2px 6px ${c}, inset 0 -2px 0 rgba(0,0,0,.2)`;
  });
}

// ---------- preencher com o estado ----------
function bateria(prefixo, valor) {
  $(`${prefixo}-bat`).textContent = valor == null ? "—" : `${valor} %`;
  const barra = $(`${prefixo}-bat-barra`);
  barra.style.width = `${valor ?? 0}%`;
  barra.classList.toggle("baixa", valor != null && valor <= 20);
  todos(`.x-${prefixo}-bat`).forEach((e) => { e.textContent = valor == null ? "—" : `${valor} %`; });
}

function conexao(prefixo, e) {
  const txt = e.conectado ? (NOMES_CONEXAO[e.conexao] || e.conexao) : (e.da_copia ? "Desconectado (último conhecido)" : "Desconectado");
  $(`${prefixo}-ponto`).classList.toggle("on", !!e.conectado);
  $(`${prefixo}-conexao`).textContent = txt;
  todos(`.x-${prefixo}-con`).forEach((el) => { el.textContent = txt; });
  $(`${prefixo}-aviso`).textContent = e.aviso || "";
  $(`${prefixo}-aviso2`).textContent = e.aviso || "";
}

async function atualizarTela() {
  try {
    const e = await window.pywebview.api.estado();
    mostrarMouse(e.mouse || {});
    mostrarTeclado(e.teclado || {});
  } catch (err) {
    console.error(err);
  }
}

// ---------- início ----------
// O aviso "pywebview.ready" pode chegar antes deste script; por isso confere se a ponte já existe.
let iniciado = false;
function quandoPronto() {
  if (iniciado || !(window.pywebview && window.pywebview.api && window.pywebview.api.estado)) return;
  iniciado = true;
  iniciar();
}
window.addEventListener("pywebview.ready", quandoPronto);
const espera = setInterval(() => { quandoPronto(); if (iniciado) clearInterval(espera); }, 200);

async function iniciar() {
  const v = await window.pywebview.api.versao();
  const pref = await window.pywebview.api.preferencias();
  corMouse(pref.cor_mouse || "202327");
  $("versao").textContent = `beta ${v.versao}`;
  atualizarTela();
  setInterval(atualizarTela, 2000);
}
desenharTeclado($("mini-teclado"), 21);
mostrarTela();
