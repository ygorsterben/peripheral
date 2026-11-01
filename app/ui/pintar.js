// Gerenciador de Periféricos — luz por tecla: pintar o teclado tecla a tecla e gravar (efeito "Por tecla").
// Usa $, todos, desenharTeclado e atualizarTela de app.js; teclado (estado) de teclado.js.
"use strict";

const PALETA_PINTAR = ["FF0000", "FF8800", "FFFF00", "7CFF00", "00FF00", "00FFB0", "00FFFF", "0080FF", "0000FF", "9B4DFF", "FF00FF", "FFFFFF"];
const DESTAQUE_PINTAR = ["w", "a", "s", "d", "up", "down", "left", "right"];
let desenho = {};          // {tecla: "RRGGBB"} sendo editado
let pincel = "9B4DFF";
let ferramenta = "pintar";
let gravandoP = false;

function pintarTecla(el) {
  const cor = desenho[el.dataset.nome];
  el.style.setProperty("--c", cor ? `#${cor}` : "transparent");
  el.style.setProperty("--a", cor ? "1" : "0");
  el.style.color = cor ? `color-mix(in srgb, #${cor} 75%, ${el.dataset.r < 3 ? "#4A4F54" : "#E6E8E6"})` : "";
}

function redesenharPintura() {
  todos("#teclado-pintar .tecla").forEach(pintarTecla);
  $("p-pincel").style.background = ferramenta === "apagar" ? "repeating-linear-gradient(45deg,#FFF 0 6px,#D6D9D5 6px 12px)" : `#${pincel}`;
  $("p-hex").textContent = ferramenta === "apagar" ? "Apagar" : `#${pincel}`;
  $("p-cor").value = `#${pincel}`;
  todos("#p-ferramenta [data-ferramenta]").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.ferramenta === ferramenta)));
  todos("#p-paleta .amostra").forEach((b) => b.setAttribute("aria-pressed", String(ferramenta === "pintar" && b.dataset.cor === pincel)));
}

function abrirPintura() {
  desenho = { ...((teclado && teclado.por_tecla) || {}) };
  $("p-erro").textContent = "";
  $("p-chip").textContent = "";
  redesenharPintura();
}

desenharTeclado($("teclado-pintar"), 44, true);
todos("#teclado-pintar .tecla").forEach((el) => {
  el.classList.add("luz");
  el.addEventListener("click", () => {
    if (ferramenta === "apagar") delete desenho[el.dataset.nome];
    else desenho[el.dataset.nome] = pincel;
    pintarTecla(el);
  });
});
$("p-paleta").replaceChildren(...PALETA_PINTAR.map((hex) => {
  const b = document.createElement("button");
  b.type = "button"; b.className = "amostra"; b.dataset.cor = hex; b.style.background = `#${hex}`;
  b.setAttribute("aria-label", `Cor #${hex}`);
  b.addEventListener("click", () => { pincel = hex; ferramenta = "pintar"; redesenharPintura(); });
  return b;
}));
$("p-cor").addEventListener("input", () => { pincel = $("p-cor").value.slice(1).toUpperCase(); ferramenta = "pintar"; redesenharPintura(); });
todos("#p-ferramenta [data-ferramenta]").forEach((b) => b.addEventListener("click", () => { ferramenta = b.dataset.ferramenta; redesenharPintura(); }));
$("p-todas").addEventListener("click", () => {
  todos("#teclado-pintar .tecla").forEach((el) => { desenho[el.dataset.nome] = pincel; });
  redesenharPintura();
});
$("p-wasd").addEventListener("click", () => { DESTAQUE_PINTAR.forEach((k) => { desenho[k] = pincel; }); redesenharPintura(); });
$("p-limpar").addEventListener("click", () => { desenho = {}; redesenharPintura(); });
$("p-gravar").addEventListener("click", async () => {
  if (gravandoP) return;
  gravandoP = true;
  $("p-gravar").disabled = true;
  $("p-erro").textContent = "";
  const c = $("p-chip");
  c.textContent = "Gravando no teclado…"; c.className = "chip trabalhando";
  let r;
  try { r = await window.pywebview.api.teclado_por_tecla(desenho); } catch (e) { r = { ok: false, erro: String(e) }; }
  gravandoP = false;
  $("p-gravar").disabled = false;
  if (r && r.ok) {
    c.textContent = "Gravado ✓"; c.className = "chip ok";
    previa = null;  // a aba Luz recomeça do que o teclado confirmou
    await atualizarTela();
  } else {
    c.textContent = "Não gravou"; c.className = "chip falha";
    $("p-erro").textContent = `Não deu para gravar: ${(r && r.erro) || "erro desconhecido"}`;
  }
});
window.addEventListener("hashchange", () => { if (location.hash === "#luz-por-tecla") abrirPintura(); });
redesenharPintura();
