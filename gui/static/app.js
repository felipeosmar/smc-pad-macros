"use strict";

// ordem física dos pads (topo -> base), como no controlador
const LAYOUT = [48, 49, 50, 51, 44, 45, 46, 47, 40, 41, 42, 43, 36, 37, 38, 39];
const COLORS = { key: "#22d3ee", exec: "#f04dc4", media: "#fbbf24", text: "#a3e635", empty: "#39404f" };
const CAT_NAMES = { key: "Tecla", exec: "Comando", media: "Mídia/Volume", text: "Texto", empty: "Vazio" };

let config = { device: "SMC-PAD Pocket", pads: {} };
let selected = null;
let dirty = false;

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

// ---------- categoria/cor de uma ação ----------
function categoryOf(a) {
  if (!a || !a.type) return "empty";
  if (a.type === "key") return "key";
  if (a.type === "type") return "text";
  if (a.type === "exec") {
    return /^\s*(playerctl|wpctl|pactl|amixer|pamixer)\b/.test(a.cmd || "") ? "media" : "exec";
  }
  return "empty";
}

// ---------- toast ----------
let toastTimer;
function toast(msg, kind = "") {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show " + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = "toast " + kind), 2600);
}

// ---------- render do grid ----------
function renderGrid(boot = false) {
  const grid = $("#grid");
  grid.innerHTML = "";
  if (boot) grid.classList.add("booting");
  LAYOUT.forEach((note, i) => {
    const a = config.pads[note];
    const cat = categoryOf(a);
    const pad = document.createElement("button");
    pad.className = "pad" + (selected === note ? " selected" : "");
    pad.style.setProperty("--c", COLORS[cat]);
    pad.style.animationDelay = boot ? i * 45 + "ms" : "0ms";
    pad.dataset.note = note;
    const label = a && a.label ? a.label : "vazio";
    pad.innerHTML =
      `<span class="pad-label${a && a.label ? "" : " is-empty"}">${escapeHtml(label)}</span>` +
      `<span class="pad-note">${note}</span>`;
    pad.addEventListener("click", () => selectPad(note));
    grid.appendChild(pad);
  });
  if (boot) setTimeout(() => grid.classList.remove("booting"), LAYOUT.length * 45 + 400);
}

function renderLegend() {
  const el = $("#legend");
  el.innerHTML = "";
  Object.entries(CAT_NAMES).forEach(([k, name]) => {
    const lg = document.createElement("span");
    lg.className = "lg";
    lg.innerHTML = `<span class="dot" style="color:${COLORS[k]};background:${COLORS[k]}"></span>${name}`;
    el.appendChild(lg);
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// ---------- editor ----------
function selectPad(note) {
  selected = note;
  $$(".pad").forEach(p => p.classList.toggle("selected", +p.dataset.note === note));
  const a = config.pads[note] || { type: "" };
  $("#editorEmpty").hidden = true;
  $("#editorForm").hidden = false;
  $("#edNote").textContent = note;
  $("#edLabel").value = a.label || "";
  $("#edKeys").value = a.type === "key" ? (Array.isArray(a.keys) ? a.keys.join(" ") : a.keys || "") : "";
  $("#edCmd").value = a.type === "exec" ? a.cmd || "" : "";
  $("#edText").value = a.type === "type" ? a.text || "" : "";
  setType(a.type || "");
}

function setType(type) {
  $$("#edType button").forEach(b => b.classList.toggle("active", b.dataset.type === type));
  $$(".pane").forEach(p => (p.hidden = p.dataset.pane !== type));
  $("#testWarn").hidden = type !== "key";
  $("#editorForm").dataset.type = type;
}

// monta a ação a partir dos campos do editor
function buildAction() {
  const type = $("#editorForm").dataset.type || "";
  const label = $("#edLabel").value.trim();
  if (!type) return label ? { type: "", label } : null;
  if (type === "key") {
    const keys = $("#edKeys").value.trim();
    return { type: "key", keys, label };
  }
  if (type === "exec") return { type: "exec", cmd: $("#edCmd").value.trim(), label };
  if (type === "type") return { type: "type", text: $("#edText").value, label };
  return null;
}

function applyPad() {
  if (selected == null) return;
  const a = buildAction();
  if (!a || !a.type) delete config.pads[selected];
  else config.pads[selected] = a;
  markDirty();
  renderGrid();
  toast(`Pad ${selected} atualizado — lembre de salvar`, "");
}

function markDirty() {
  dirty = true;
  $("#saveAll").disabled = false;
}

// ---------- captura de atalho ----------
let capturing = false;
const MODS = ["Control", "Alt", "Shift", "Meta"];
function keyName(e) {
  const k = e.key;
  if (MODS.includes(k)) return null;
  const map = {
    " ": "space", Enter: "enter", Tab: "Tab", Escape: "esc", Backspace: "Backspace",
    Delete: "delete", ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right",
    Home: "home", End: "end", PageUp: "pageup", PageDown: "pagedown",
  };
  if (map[k]) return map[k];
  if (/^F\d{1,2}$/.test(k)) return k;
  return k.length === 1 ? k.toLowerCase() : k.toLowerCase();
}
function modList(e) {
  const m = [];
  if (e.ctrlKey) m.push("ctrl");
  if (e.altKey) m.push("alt");
  if (e.shiftKey) m.push("shift");
  if (e.metaKey) m.push("super");
  return m;
}
function startCapture() {
  capturing = true;
  const box = $('[data-pane="key"]');
  box.classList.add("capturing");
  $("#captureHint").textContent = "Aperte a combinação agora…";
  $("#edCapture").textContent = "…";

  const onDown = e => {
    e.preventDefault();
    const main = keyName(e);
    const mods = modList(e);
    if (main) {
      $("#edKeys").value = [...mods, main].join("+");
      finish();
    } else {
      $("#edKeys").value = mods.join("+") || "";
    }
  };
  const onUp = e => {
    // combinação só de modificador (ex.: super sozinho)
    if (!capturing) return;
    const mods = modList(e);
    if (mods.length && !$("#edKeys").value.includes("+") &&
        ["Control", "Alt", "Shift", "Meta"].includes(e.key)) {
      $("#edKeys").value = { Control: "ctrl", Alt: "alt", Shift: "shift", Meta: "super" }[e.key];
      finish();
    }
  };
  function finish() {
    capturing = false;
    box.classList.remove("capturing");
    $("#captureHint").textContent = "Clique em “Gravar” e aperte a combinação no teclado.";
    $("#edCapture").textContent = "Gravar";
    window.removeEventListener("keydown", onDown, true);
    window.removeEventListener("keyup", onUp, true);
  }
  window.addEventListener("keydown", onDown, true);
  window.addEventListener("keyup", onUp, true);
}

// ---------- rede ----------
async function loadConfig() {
  const r = await fetch("/api/config");
  config = await r.json();
  if (!config.pads) config.pads = {};
}
async function saveAll() {
  const r = await fetch("/api/config", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (r.ok) { dirty = false; $("#saveAll").disabled = true; toast("Configuração salva ✓", "ok"); }
  else toast("Falha ao salvar", "err");
}
async function testAction() {
  const a = buildAction();
  if (!a || !a.type) return toast("Nada para testar neste pad", "err");
  const r = await fetch("/api/test", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: a }),
  });
  if (r.ok) return toast("Ação disparada ▶", "ok");
  const motivo = await r.json().then(j => j.error).catch(() => null);
  toast(motivo ? `Falha: ${motivo}` : "Falha ao testar", "err");
}
async function svc(action) {
  const r = await fetch("/api/service", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
  toast(r.ok ? `Serviço: ${action} ✓` : `Falha: ${action}`, r.ok ? "ok" : "err");
  setTimeout(pollService, 400);
}
async function pollService() {
  try {
    const s = await (await fetch("/api/service")).json();
    const led = $("#svcLed"), lbl = $("#svcLabel");
    const on = s.active === "active";
    led.className = "led " + (on ? "on" : "off");
    lbl.textContent = on ? "ativo" : (s.active || "inativo");
  } catch (_) {}
}

// ---------- ciclo de vida ----------
function heartbeat() { fetch("/api/heartbeat", { method: "POST" }).catch(() => {}); }

function init() {
  renderLegend();
  loadConfig().then(() => renderGrid(true));
  pollService();

  $("#edType").addEventListener("click", e => {
    const b = e.target.closest("button[data-type]");
    if (b) setType(b.dataset.type);
  });
  $("#edCapture").addEventListener("click", startCapture);
  $("#edTest").addEventListener("click", testAction);
  $("#editorForm").addEventListener("submit", e => { e.preventDefault(); applyPad(); });
  $("#saveAll").addEventListener("click", saveAll);
  $$("[data-svc]").forEach(b => b.addEventListener("click", () => svc(b.dataset.svc)));

  window.addEventListener("beforeunload", () => navigator.sendBeacon("/api/quit"));
  setInterval(heartbeat, 5000);
  setInterval(pollService, 3000);
  heartbeat();
}

document.addEventListener("DOMContentLoaded", init);
