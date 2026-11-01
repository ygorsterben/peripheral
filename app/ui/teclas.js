// Gerenciador de Periféricos — aba Teclas: trocar o que cada tecla do teclado faz (tabela 0x03 / 0x01).
// Usa de app.js: $, todos, desenharTeclado, ROTULOS, atualizarTela; de mouse.js: HID, MODS, nomeTecla, NOMES;
// de teclado.js: teclado (estado).
"use strict";

const TRAVADAS = ["fn", "roda"];
let trocasSalvas = {};   // o que está gravado (cópia do app)
let trocas = {};         // em edição
let teclaSel = null;
let tipoSel = "padrao";
let ouvindoTecla = false;
let gravandoK = false;
let macrosSalvas = []; // macros gravadas: [{nome, eventos: [[solta, ms, tecla], ...]}]; a posição é o número da macro
let macros = [];       // em edição
let editando = null;   // {indice (-1 = nova), nome, eventos} enquanto o editor está aberto
let ouvindoSeq = false;
const MAX_EVENTOS = 30;

const nomeVisivel = (n) => (n === "space" ? "Espaço" : ROTULOS[n] || n.toUpperCase());
const iguais = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function descreverTroca(f) {
  if (!f) return "Padrão";
  if (f.tipo === "tecla") return nomeTecla(f.valor, f.modificadores || 0);
  if (f.tipo === "midia" || f.tipo === "atalho") return (NOMES[f.tipo] || {})[f.valor] || f.valor;
  if (f.tipo === "desativar") return "Desativada";
  if (f.tipo === "macro") {
    const extra = f.modo === "segurar" ? " (enquanto segurar)" : f.modo === "ate_outra" ? " (até outra tecla)"
      : (f.vezes || 1) > 1 ? ` ×${f.vezes}` : "";
    return `Macro ${macros[f.valor] ? macros[f.valor].nome : "?"}${extra}`;
  }
  return "?";
}

function desenharMacro() {
  const f = teclaSel ? trocas[teclaSel] : null;
  const lista = $("k-lista-macro");
  lista.replaceChildren(...macros.map((m, i) => new Option(m.nome, String(i))));
  if (f && f.tipo === "macro") lista.value = String(f.valor);
  lista.hidden = !macros.length;
  $("m-editar").hidden = $("m-excluir").hidden = $("m-rotulo-vezes").hidden = !macros.length;
  $("m-vezes").value = f && f.tipo === "macro" ? f.vezes || 1 : 1;
  $("m-modo").value = f && f.tipo === "macro" ? f.modo || "vezes" : "vezes";
  $("m-rotulo-num").hidden = $("m-modo").value !== "vezes";
  if (!editando) return;
  $("m-gravar-seq").textContent = ouvindoSeq ? "Aperte as teclas… (clique aqui para parar)" : "Clique aqui e aperte as teclas da macro";
  $("m-gravar-seq").classList.toggle("ouvindo", ouvindoSeq);
  $("m-eventos").replaceChildren(...editando.eventos.map((e, i) => {
    const li = document.createElement("li");
    li.append(`${nomeEvento(e[2])} ${e[0] ? "solta" : "aperta"} · espera `);
    const campo = document.createElement("input");
    campo.type = "number"; campo.min = 0; campo.max = 65535; campo.value = e[1];
    campo.setAttribute("aria-label", "Espera em milissegundos");
    campo.addEventListener("change", () => { e[1] = Math.max(0, Math.min(65535, parseInt(campo.value, 10) || 0)); });
    li.append(campo, " ms ");
    const x = document.createElement("button");
    x.type = "button"; x.className = "fechar pequeno-x"; x.textContent = "✕"; x.setAttribute("aria-label", "Tirar este evento");
    x.addEventListener("click", () => { editando.eventos.splice(i, 1); redesenharTeclas(); });
    li.append(x);
    return li;
  }));
  $("m-info").textContent = `${editando.eventos.length} de ${MAX_EVENTOS} eventos. Grava o apertar e o soltar na ordem real ` +
    "(Ctrl + C = Ctrl↓ C↓ C↑ Ctrl↑); esperas curtas (10 ms) evitam letras repetidas.";
}

function abrirEditor(indice) {
  editando = indice >= 0 ? JSON.parse(JSON.stringify(macros[indice]))
    : { nome: `Macro ${macros.length + 1}`, eventos: [] };
  editando.indice = indice;
  $("m-nome").value = editando.nome;
  ouvindoSeq = false;
  $("m-erro").textContent = "";
  $("dlg-macro-titulo").textContent = indice >= 0 ? `Editar macro ${macros[indice].nome}` : "Nova macro";
  redesenharTeclas();
  $("dlg-macro").showModal();
}

function redesenharTeclas() {
  todos("#teclado-teclas .tecla").forEach((el) => {
    const n = el.dataset.nome;
    el.classList.toggle("trocada", !!trocas[n]);
    el.classList.toggle("selecionada", n === teclaSel);
    el.disabled = TRAVADAS.includes(n);
    el.title = trocas[n] ? `${nomeVisivel(n)} → ${descreverTroca(trocas[n])}` : "";
  });
  const f = teclaSel ? trocas[teclaSel] : null;
  $("k-titulo").textContent = teclaSel ? `Tecla ${nomeVisivel(teclaSel)}` : "Escolha uma tecla no desenho";
  $("k-agora").textContent = teclaSel ? `Agora: ${descreverTroca(f)}` : "As trocas valem no modo Windows do teclado (Fn + W). A Fn é travada.";
  todos("#k-tipos [data-tipo]").forEach((b) => {
    b.setAttribute("aria-checked", String(b.dataset.tipo === tipoSel));
    b.disabled = !teclaSel;
  });
  $("k-tecla").hidden = tipoSel !== "tecla" || !teclaSel;
  $("k-midia").hidden = tipoSel !== "midia" || !teclaSel;
  $("k-macro").hidden = tipoSel !== "macro" || !teclaSel;
  if (tipoSel === "macro" && teclaSel) desenharMacro();
  if (tipoSel === "tecla") {
    const mods = f && f.tipo === "tecla" ? f.modificadores || 0 : 0;
    $("k-mods").replaceChildren(...MODS.map(([nome, bit]) => {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = nome; b.setAttribute("aria-pressed", String(!!(mods & bit)));
      b.addEventListener("click", () => {
        const atual = trocas[teclaSel];
        if (atual && atual.tipo === "tecla") { atual.modificadores = (atual.modificadores || 0) ^ bit; redesenharTeclas(); }
      });
      return b;
    }));
    $("k-combo").textContent = f && f.tipo === "tecla" ? nomeTecla(f.valor, f.modificadores || 0) : "—";
    $("k-capturar").textContent = ouvindoTecla ? "Aperte a tecla agora…" : "Clique aqui e aperte a tecla";
    $("k-capturar").classList.toggle("ouvindo", ouvindoTecla);
  }
  if (tipoSel === "midia" && f && (f.tipo === "midia" || f.tipo === "atalho")) $("k-lista-midia").value = `${f.tipo}:${f.valor}`;
  const lista = Object.entries(trocas);
  $("k-conta").textContent = lista.length ? `${lista.length} tecla(s)` : "nenhuma";
  $("k-lista").replaceChildren(...lista.map(([n, fn]) => {
    const li = document.createElement("li");
    li.innerHTML = `<button type="button" class="link-tecla"><b>${nomeVisivel(n)}</b> → ${descreverTroca(fn)}</button>`;
    li.querySelector("button").addEventListener("click", () => selecionarTecla(n));
    const x = document.createElement("button");
    x.type = "button"; x.className = "fechar pequeno-x"; x.textContent = "✕"; x.setAttribute("aria-label", `Voltar ${nomeVisivel(n)} ao padrão`);
    x.addEventListener("click", () => { delete trocas[n]; redesenharTeclas(); });
    li.append(x);
    return li;
  }));
  $("k-gravar").disabled = gravandoK || !!editando || (iguais(trocas, trocasSalvas) && iguais(macros, macrosSalvas));
}

function selecionarTecla(n) {
  teclaSel = n;
  const f = trocas[n];
  tipoSel = !f ? "padrao" : f.tipo === "atalho" ? "midia" : f.tipo;
  ouvindoTecla = false;
  editando = null; ouvindoSeq = false;
  $("k-erro").textContent = "";
  redesenharTeclas();
}

function abrirTeclas() {
  trocasSalvas = JSON.parse(JSON.stringify((teclado && teclado.teclas) || {}));
  trocas = JSON.parse(JSON.stringify(trocasSalvas));
  macrosSalvas = JSON.parse(JSON.stringify((teclado && teclado.macros) || []));
  macros = JSON.parse(JSON.stringify(macrosSalvas));
  editando = null; ouvindoSeq = false;
  redesenharTeclas();
}

// ---------- montar ----------
desenharTeclado($("teclado-teclas"), 37, true);
todos("#teclado-teclas .tecla").forEach((el) => el.addEventListener("click", () => selecionarTecla(el.dataset.nome)));
$("k-lista-midia").replaceChildren(...["midia", "atalho"].flatMap((g) =>
  Object.entries(NOMES[g]).map(([v, n]) => new Option(n, `${g}:${v}`))));
todos("#k-tipos [data-tipo]").forEach((b) => b.addEventListener("click", () => {
  if (!teclaSel) return;
  tipoSel = b.dataset.tipo;
  editando = null; ouvindoSeq = false;
  if (tipoSel === "padrao") delete trocas[teclaSel];
  if (tipoSel === "desativar") trocas[teclaSel] = { tipo: "desativar" };
  if (tipoSel === "midia") { const [g, v] = $("k-lista-midia").value.split(":"); trocas[teclaSel] = { tipo: g, valor: v }; }
  if (tipoSel === "tecla" && !(trocas[teclaSel] && trocas[teclaSel].tipo === "tecla")) delete trocas[teclaSel];
  if (tipoSel === "macro") {
    if (macros.length) trocas[teclaSel] = { tipo: "macro", valor: (trocas[teclaSel] && trocas[teclaSel].valor) || 0 };
    else { delete trocas[teclaSel]; abrirEditor(-1); return; }
  }
  redesenharTeclas();
}));
$("k-lista-macro").addEventListener("change", () => {
  if (teclaSel) { trocas[teclaSel] = { tipo: "macro", valor: Number($("k-lista-macro").value) }; redesenharTeclas(); }
});
$("m-modo").addEventListener("change", () => {
  const f = teclaSel && trocas[teclaSel];
  if (!f || f.tipo !== "macro") return;
  const modo = $("m-modo").value;
  if (modo === "vezes") delete f.modo; else { f.modo = modo; delete f.vezes; }  // sem "modo" = vezes (trocas antigas)
  redesenharTeclas();
});
$("m-vezes").addEventListener("change", () => {
  const f = teclaSel && trocas[teclaSel];
  if (!f || f.tipo !== "macro") return;
  const v = Math.max(1, Math.min(99, parseInt($("m-vezes").value, 10) || 1));
  if (v > 1) f.vezes = v; else delete f.vezes;  // sem "vezes" = 1, como as trocas antigas
  redesenharTeclas();
});
$("m-nova").addEventListener("click", () => abrirEditor(-1));
$("m-editar").addEventListener("click", () => abrirEditor(Number($("k-lista-macro").value)));
$("m-excluir").addEventListener("click", () => {
  const i = Number($("k-lista-macro").value);
  macros.splice(i, 1);
  for (const [n, f] of Object.entries(trocas)) {  // as teclas que apontavam para ela voltam ao padrão; as seguintes descem uma posição
    if (f.tipo !== "macro") continue;
    if (f.valor === i) delete trocas[n]; else if (f.valor > i) f.valor -= 1;
  }
  if (!trocas[teclaSel]) tipoSel = "padrao";
  redesenharTeclas();
});
function fecharApertadas() {  // tecla sem "solta" ficaria presa no teclado depois da macro
  for (const h of apertadas) if (editando && editando.eventos.length < MAX_EVENTOS) editando.eventos.push([true, 10, h]);
  apertadas.clear();
}
$("m-gravar-seq").addEventListener("click", () => {
  ouvindoSeq = !ouvindoSeq;
  if (ouvindoSeq) apertadas.clear(); else fecharApertadas();
  redesenharTeclas();
});
$("dlg-macro").addEventListener("close", () => {  // Cancelar, ✕, Esc ou depois de salvar
  editando = null; ouvindoSeq = false; apertadas.clear();
  if (!trocas[teclaSel]) tipoSel = "padrao";
  redesenharTeclas();
});
$("m-salvar").addEventListener("click", () => {
  if (ouvindoSeq) { ouvindoSeq = false; fecharApertadas(); }
  const nome = $("m-nome").value.trim();
  const erro = (t) => { $("m-erro").textContent = t; redesenharTeclas(); };
  if (!nome) return erro("Dê um nome à macro.");
  if (!editando.eventos.length) return erro("A macro está vazia: aperte as teclas dela.");
  if (macros.some((m, i) => i !== editando.indice && m.nome === nome)) return erro("Já existe uma macro com esse nome.");
  const i = editando.indice >= 0 ? editando.indice : macros.length;
  macros[i] = { nome, eventos: editando.eventos };
  if (teclaSel) trocas[teclaSel] = { tipo: "macro", valor: i };
  $("k-erro").textContent = "";
  $("dlg-macro").close();
});
// Na macro os modificadores são teclas comuns (HID E0–E7), com "aperta" e "solta" na ordem real: Ctrl↓ C↓ C↑ Ctrl↑.
const MOD_HID = { ControlLeft: 0xE0, ShiftLeft: 0xE1, AltLeft: 0xE2, MetaLeft: 0xE3,
                  ControlRight: 0xE4, ShiftRight: 0xE5, AltRight: 0xE6, MetaRight: 0xE7 };
const NOME_MOD = { 0xE0: "Ctrl", 0xE1: "Shift", 0xE2: "Alt", 0xE3: "Win", 0xE4: "Ctrl dir.", 0xE5: "Shift dir.", 0xE6: "Alt Gr", 0xE7: "Win dir." };
const nomeEvento = (h) => NOME_MOD[h] || nomeTecla(h, 0);
const apertadas = new Set();  // teclas que já tiveram "aperta" nesta gravação (para não gravar um "solta" órfão)

function eventoDaMacro(ev, solta) {
  if (!ouvindoSeq || !editando || ev.repeat) return;
  if (ev.target && ev.target.tagName === "INPUT") return;  // digitando o nome ou a espera: não é tecla da macro
  ev.preventDefault();
  const h = MOD_HID[ev.code] || (HID[ev.code] && HID[ev.code][0]);
  if (!h) { if (!solta) $("m-erro").textContent = "Essa tecla ainda não é suportada."; return; }
  if (solta && !apertadas.delete(h)) return;
  if (!solta && apertadas.has(h)) return;
  // um "aperta" só entra se ainda couberem os "solta" de tudo que está apertado (nada fica preso no teclado)
  if (!solta && editando.eventos.length + apertadas.size + 2 > MAX_EVENTOS) {
    $("m-erro").textContent = `No máximo ${MAX_EVENTOS} eventos.`;
    return;
  }
  if (!solta) apertadas.add(h);
  $("m-erro").textContent = "";
  editando.eventos.push([solta, 10, h]);
  redesenharTeclas();
}
document.addEventListener("keydown", (ev) => eventoDaMacro(ev, false), true);
document.addEventListener("keyup", (ev) => eventoDaMacro(ev, true), true);
$("k-lista-midia").addEventListener("change", () => {
  const [g, v] = $("k-lista-midia").value.split(":");
  if (teclaSel) { trocas[teclaSel] = { tipo: g, valor: v }; redesenharTeclas(); }
});
$("k-capturar").addEventListener("click", () => { ouvindoTecla = true; redesenharTeclas(); });
document.addEventListener("keydown", (ev) => {
  if (!ouvindoTecla || !teclaSel) return;
  if (["ControlLeft", "ControlRight", "ShiftLeft", "ShiftRight", "AltLeft", "AltRight", "MetaLeft", "MetaRight"].includes(ev.code)) return;
  ev.preventDefault();
  const h = HID[ev.code];
  if (!h) { $("k-erro").textContent = "Essa tecla ainda não é suportada."; return; }
  const mods = (ev.ctrlKey ? 1 : 0) | (ev.shiftKey ? 2 : 0) | (ev.altKey ? 4 : 0) | (ev.metaKey ? 8 : 0);
  trocas[teclaSel] = { tipo: "tecla", valor: h[0], modificadores: mods };
  ouvindoTecla = false;
  $("k-erro").textContent = "";
  redesenharTeclas();
}, true);
$("k-tudo-padrao").addEventListener("click", () => { trocas = {}; macros = []; editando = null; tipoSel = "padrao"; redesenharTeclas(); });
$("k-gravar").addEventListener("click", async () => {
  if (gravandoK) return;
  gravandoK = true;
  $("k-erro").textContent = "";
  chipT("Gravando no teclado…", "trabalhando");
  redesenharTeclas();
  let r;
  try { r = await window.pywebview.api.teclado_teclas(trocas, macros); } catch (e) { r = { ok: false, erro: String(e) }; }
  gravandoK = false;
  if (r && r.ok) {
    chipT("Gravado ✓", "ok");
    trocasSalvas = JSON.parse(JSON.stringify(trocas));
    macrosSalvas = JSON.parse(JSON.stringify(macros));
    await atualizarTela();
  } else {
    chipT("Não gravou", "falha");
    $("k-erro").textContent = `Não deu para gravar: ${(r && r.erro) || "erro desconhecido"}`;
  }
  redesenharTeclas();
});
todos("#t-abas [data-aba]").forEach((b) => b.addEventListener("click", () => {
  $("teclado").dataset.aba = b.dataset.aba;
  if (b.dataset.aba === "teclas") abrirTeclas();
}));
