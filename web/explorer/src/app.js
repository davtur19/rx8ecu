/* RX-8 ECU Firmware Explorer — app.js
 * No external dependencies: hand-rolled force-directed callgraph layout on
 * canvas, heatmap/bar-chart on canvas. Works via http.server (fetch data.json)
 * and, as a fallback, directly via file:// (data.js).
 */
"use strict";

/* ============================ BOOT / DATA ============================ */
const DATA = { meta: null, symbols: [], edges: [], tables: [], docs: [], subsystems: [] };
const $ = (id) => document.getElementById(id);
let bootEl, bootMsg;

/* Selected firmware model + lazily loaded per-model values.
 * CUR_MODEL is a key of meta.models (D400, E500, C500, FB00, FC00, B900,
 * E700, 15120, 32000). MODEL_LOAD[key] = {state:'loading'|'ok'|'failed', values}
 * where `values` is an array aligned 1:1 with DATA.tables (baseline entries)
 * carrying the value payload {t?, ax?, scalar?, raw?} extracted from that ROM.
 */
let CUR_MODEL = "D400";
const MODEL_LOAD = {};
let modelRevCache = null;

async function loadData() {
  try {
    const r = await fetch("data.json");
    if (!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json();
    DATA.meta = j.meta; DATA.symbols = j.symbols; DATA.edges = j.edges; DATA.tables = j.tables;
    DATA.docs = j.docs || []; DATA.subsystems = j.subsystems || [];
    DATA.models = j.meta.models || [];
    DATA.addrMap = j.meta.addr_map || {};
    DATA.defaultModel = j.meta.default_model || "D400";
    CUR_MODEL = DATA.defaultModel;
    return;
  } catch (e) {
    if (window.EXPLORER_DATA && window.EXPLORER_DATA.meta) {
      const j = window.EXPLORER_DATA;
      DATA.meta = j.meta; DATA.symbols = j.symbols; DATA.edges = j.edges; DATA.tables = j.tables;
      DATA.docs = j.docs || []; DATA.subsystems = j.subsystems || [];
      DATA.models = j.meta.models || [];
      DATA.addrMap = j.meta.addr_map || {};
      DATA.defaultModel = j.meta.default_model || "D400";
      CUR_MODEL = DATA.defaultModel;
      console.info("explorer: loaded data.js (file:// fallback)");
      return;
    }
    throw e;
  }
}

/* ============================ UTIL ============================ */
const hex = (a) => "0x" + a.toString(16).toUpperCase().padStart(6, "0");
const hex6 = (a) => a.toString(16).toUpperCase().padStart(6, "0");
const fmtNum = (v, d) => {
  if (v === null || v === undefined) return "—";
  if (typeof v !== "number") return String(v);
  if (d === undefined) d = 3;
  if (v === Math.floor(v) && Math.abs(v) < 1e15) return String(v);
  return v.toFixed(d);
};
function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function parseHex(s) {
  s = String(s || "").trim().replace(/^0x/i, "").replace(/_/g, "");
  if (!/^[0-9a-fA-F]+$/.test(s)) return null;
  const v = parseInt(s, 16);
  return isNaN(v) ? null : v;
}

/* ============================ FIRMWARE MODEL SELECTOR ============================ */
/* The user picks one of the 9 stock ROMs. Table addresses are looked up in
 * DATA.addrMap (built from data/table_addr_map_long.csv — per-ROM map, NEVER a
 * global shift), values come from the matching roms/stock/*.bin: the baseline
 * model (D400) values are embedded in DATA.tables, the others are fetched on
 * demand from models/<key>.json. Symbols/functions are NEVER adjusted. */
const METHOD_LABEL = {
  same: "same_addr", match: "content_match", shift: "family_shift",
  hole: "hole", unmatched: "unmatched",
};
const CONF_LABEL = { high: "high", medium: "medium", low: "low" };
const SYMBOL_CONTEXTS = new Set(["60E1D400", "60E0FC00"]);

function modelByKey(key) { return DATA.models.find((m) => m.id === key) || null; }

function modelLabel(key) {
  const m = modelByKey(key);
  if (!m) return key;
  return `${m.cal_id} · ${m.family} (${m.id})`;
}

/* Address-map entry for table row `i` in the CURRENT model:
 * {a: int, m: method-short, c: confidence} or null when not mapped. */
function modelMap(i) {
  const arr = DATA.addrMap[CUR_MODEL];
  const e = arr && arr[i];
  return e ? { a: parseInt(e[0], 16), m: e[1], c: e[2] } : null;
}

/* Lazily loads the per-model value array (aligned with DATA.tables). */
async function loadModelValues(key) {
  if (key === DATA.defaultModel) {
    if (!MODEL_LOAD[key]) {
      MODEL_LOAD[key] = {
        state: "ok",
        values: DATA.tables.map((t) => ({ t: t.t, ax: t.ax, scalar: t.scalar, raw: t.raw })),
      };
    }
    return MODEL_LOAD[key].values;
  }
  if (MODEL_LOAD[key]) return MODEL_LOAD[key].values;
  MODEL_LOAD[key] = { state: "loading", values: null };
  try {
    const r = await fetch("models/" + key + ".json");
    if (!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json();
    MODEL_LOAD[key] = { state: "ok", values: j.values || [] };
  } catch (e) {
    MODEL_LOAD[key] = { state: "failed", values: null };
  }
  return MODEL_LOAD[key].values;
}

/* Value payload ({t?, ax?, scalar?, raw?}) for table row `i` in CURRENT model.
 * The default model's values are embedded in DATA.tables (synchronous); the
 * other models resolve lazily once models/<key>.json has been fetched. */
function modelVal(i) {
  if (CUR_MODEL === DATA.defaultModel) {
    const t = DATA.tables[i];
    return t ? { t: t.t, ax: t.ax, scalar: t.scalar, raw: t.raw } : null;
  }
  const e = MODEL_LOAD[CUR_MODEL];
  return (e && e.values) ? (e.values[i] || null) : null;
}

function modelValHasData(i) {
  const v = modelVal(i);
  if (!v) return false;
  if (v.t && (v.t.vals || v.t.grid)) return true;
  if (v.ax && v.ax.length) return true;
  if (v.scalar !== null && v.scalar !== undefined) return true;
  return false;
}

function confBadge(c) {
  if (!c) return "";
  return `<span class="tag conf-${esc(c)}" title="mapping confidence: ${esc(CONF_LABEL[c] || c)}">${esc(CONF_LABEL[c] || c)}</span>`;
}
function methodBadge(m) {
  if (!m) return "";
  return `<span class="tag" title="mapping method: ${esc(METHOD_LABEL[m] || m)}">${esc(METHOD_LABEL[m] || m)}</span>`;
}

function modelContextSummary() {
  const m = modelByKey(CUR_MODEL);
  if (!m) return "";
  const st = m.stats || {};
  const cf = st.confidence || {};
  const hi = cf.high || 0, me = cf.medium || 0, lo = cf.low || 0;
  let s = `context <b>${esc(m.cal_id)}</b> · ${esc(m.family)} · ${esc(m.role || "")}`
    + ` · ${fmtNum(hi)} <span class="tag conf-high">high</span>`
    + ` ${fmtNum(me)} <span class="tag conf-medium">medium</span>`
    + ` ${fmtNum(lo)} <span class="tag conf-low">low</span>`;
  if (st.unmatched) s += ` · <span class="tag unmapped">${fmtNum(st.unmatched)} not mapped</span>`;
  return s;
}

function updateModelContext() {
  const box = $("model-context");
  if (box) box.innerHTML = modelContextSummary();
}

function updateSymCtxNote() {
  const note = $("sym-ctx-note");
  if (!note) return;
  const m = modelByKey(CUR_MODEL);
  if (!m || SYMBOL_CONTEXTS.has(m.cal_id)) {
    note.classList.add("hidden");
    note.innerHTML = "";
    return;
  }
  note.innerHTML = `<strong>Symbols / functions are not adjusted.</strong> They are only
    reverse-engineered in the <code>60E1D400</code> (baseline) and <code>60E0FC00</code> (Z-line)
    contexts; the selected model <code>${esc(m.cal_id)}</code> has no symbol set, so function
    addresses are shown in their native context and <em>no address adjustment is applied</em>.`;
  note.classList.remove("hidden");
}

function updateTblModelNote() {
  const note = $("tbl-model-note");
  if (!note) return;
  const m = modelByKey(CUR_MODEL);
  if (!m) { note.innerHTML = ""; return; }
  const arr = DATA.addrMap[CUR_MODEL];
  const mapped = arr ? arr.filter((x) => x).length : 0;
  const unmatched = arr ? arr.length - mapped : 0;
  const st = MODEL_LOAD[CUR_MODEL];
  let vnote;
  if (CUR_MODEL === DATA.defaultModel) vnote = "values embedded in <code>data.json</code>";
  else if (!st) vnote = "loading values…";
  else if (st.state === "loading") vnote = "loading values from <code>models/" + esc(CUR_MODEL) + ".json</code>…";
  else if (st.state === "failed") vnote = '<span class="tag unmapped">values unavailable</span> <span class="muted">(could not fetch <code>models/' + esc(CUR_MODEL) + '.json</code> — serve the site over HTTP, e.g. <code>make serve</code>)</span>';
  else vnote = "values from <code>models/" + esc(CUR_MODEL) + ".json</code> (lazy-loaded)";
  note.innerHTML = `Showing <b>${esc(m.cal_id)}</b> <span class="muted">(${esc(m.family)} · ${esc(m.file)})</span>`
    + ` — ${fmtNum(mapped)} mapped, <b>${fmtNum(unmatched)} not mapped</b> in this model · ${vnote}`;
}

/* Reverse map (current model): model addr (int) -> first table row index. */
function modelReverse() {
  if (!modelRevCache) {
    modelRevCache = new Map();
    const arr = DATA.addrMap[CUR_MODEL] || [];
    arr.forEach((e, i) => { if (e) { const k = parseInt(e[0], 16); if (!modelRevCache.has(k)) modelRevCache.set(k, i); } });
  }
  return modelRevCache;
}

async function setModel(key) {
  if (!modelByKey(key) || key === CUR_MODEL) return;
  CUR_MODEL = key;
  modelRevCache = null;
  const sel = $("model-select");
  if (sel) sel.value = key;
  updateModelContext();
  updateSymCtxNote();
  updateTblModelNote();
  const values = await loadModelValues(key);
  if (CUR_MODEL !== key) return; // user switched again meanwhile
  updateTblModelNote();
  TblApply();
  if (Tbl.sel !== null && Tbl.sel >= 0) TblDetail(Tbl.sel);
}

function populateModelSelect() {
  const sel = $("model-select");
  if (!sel || !DATA.models.length) return;
  sel.innerHTML = DATA.models.map((m) =>
    `<option value="${esc(m.id)}">${esc(m.cal_id + " · " + m.family + " (" + m.id + ")")}</option>`).join("");
  sel.value = CUR_MODEL;
  sel.addEventListener("change", () => { setModel(sel.value); });
}

/* ============================ MARKDOWN (minimal renderer) ============================ */
/* No external dependencies: handles # ## ###, lists, `code`, ```fenced blocks```,
 * **bold**, *italic*, markdown tables, > quotes and links. HTML is escaped first,
 * then inline transformations are applied. */
function mdInline(s) {
  s = s.replace(/`([^`]+)`/g, (m, c) => "<code>" + c + "</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return s;
}

function mdToHtml(src, out) {
  if (!src) return "";
  const lines = String(src).split(/\r?\n/);
  let html = "", i = 0, inUl = false, inOl = false, secN = 0;
  const closeList = () => {
    if (inUl) { html += "</ul>"; inUl = false; }
    if (inOl) { html += "</ol>"; inOl = false; }
  };
  const isUl = (t) => /^(\s*)[-*+]\s+/.test(t);
  const isOl = (t) => /^\s*\d+[.)]\s+/.test(t);
  while (i < lines.length) {
    const raw = lines[i];
    const t = raw.trim();
    // fenced code block
    if (/^```/.test(t)) {
      closeList();
      const buf = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i].trim())) { buf.push(lines[i]); i++; }
      i++;
      html += '<pre class="md-code"><code>' + esc(buf.join("\n")) + "</code></pre>";
      continue;
    }
    if (!t) { closeList(); i++; continue; }
    // headings
    const h = /^(#{1,5})\s+(.*)$/.exec(t);
    if (h) {
      closeList();
      const lv = Math.min(6, h[1].length + 1);
      const id = "sec-" + (++secN);
      if (out && out.toc) out.toc.push({ level: lv, text: h[2].replace(/\*\*/g, "").replace(/`/g, "").trim(), id });
      const link = (out && out.toc) ? ` <a class="hlink" href="#${id}" data-sec="${id}" title="Link to this section">§</a>` : "";
      html += `<h${lv} id="${id}" class="md-h">${mdInline(esc(h[2]))}${link}</h${lv}>`;
      i++; continue;
    }
    // separator
    if (/^(-{3,}|\*{3,}|_{3,})\s*$/.test(t)) { closeList(); html += '<hr class="md-hr">'; i++; continue; }
    // quote
    if (/^>\s?/.test(t)) {
      closeList();
      const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) {
        buf.push(lines[i].replace(/^\s*>\s?/, ""));
        i++;
      }
      html += '<blockquote class="md-bq">' + mdInline(esc(buf.join(" "))) + "</blockquote>";
      continue;
    }
    // markdown table (consecutive lines starting with |)
    if (/^\|/.test(t)) {
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) { rows.push(lines[i].trim()); i++; }
      const sepCells = rows[1] ? rows[1].replace(/^\||\|$/g, "").split("|").map((c) => c.trim()) : [];
      const sepOk = rows.length >= 2 &&
        sepCells.every((c) => /^:?-{2,}:?$/.test(c));
      if (sepOk) {
        const cells = (r) => r.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
        const head = cells(rows[0]);
        const body = rows.slice(2).map(cells);
        html += '<div class="md-table-wrap"><table class="md-table"><thead><tr>' +
          head.map((c) => `<th>${mdInline(esc(c))}</th>`).join("") +
          "</tr></thead><tbody>" +
          body.map((r) => "<tr>" + r.map((c) => `<td>${mdInline(esc(c))}</td>`).join("") + "</tr>").join("") +
          "</tbody></table></div>";
        continue;
      }
      html += `<p>${mdInline(esc(rows.join(" ")))}</p>`;
      continue;
    }
    // lists
    if (isUl(t)) {
      if (inOl) { html += "</ol>"; inOl = false; }
      if (!inUl) { html += '<ul class="md-ul">'; inUl = true; }
      html += `<li>${mdInline(esc(t.replace(/^(\s*)[-*+]\s+/, "")))}</li>`;
      i++; continue;
    }
    if (isOl(t)) {
      if (inUl) { html += "</ul>"; inUl = false; }
      if (!inOl) { html += '<ol class="md-ol">'; inOl = true; }
      html += `<li>${mdInline(esc(t.replace(/^\s*\d+[.)]\s+/, "")))}</li>`;
      i++; continue;
    }
    // paragraph
    closeList();
    const buf = [t];
    i++;
    while (i < lines.length) {
      const n = lines[i].trim();
      if (!n || /^(#{1,5})\s/.test(n) || /^```/.test(n) || /^\|/.test(n) ||
          /^>\s?/.test(n) || isUl(n) || isOl(n) || /^(-{3,}|\*{3,}|_{3,})\s*$/.test(n)) break;
      buf.push(n);
      i++;
    }
    html += `<p>${mdInline(esc(buf.join(" ")))}</p>`;
  }
  closeList();
  return html;
}

/* Doc linked to a symbol (by index) */
function docForSym(sym) {
  if (!sym || sym.di === undefined) return null;
  return DATA.docs[sym.di] || null;
}

/* Indexes */
const symIdx = new Map();       // addr -> symbol index
const byAddr = new Map();       // addr -> symbol object
let inEdges = [], outEdges = []; // per-index list of [otherIdx, kind]
let indeg = [], outdeg = [];

function buildIndex() {
  for (let i = 0; i < DATA.symbols.length; i++) {
    symIdx.set(DATA.symbols[i].a, i);
    byAddr.set(DATA.symbols[i].a, DATA.symbols[i]);
  }
  inEdges = DATA.symbols.map(() => []);
  outEdges = DATA.symbols.map(() => []);
  indeg = new Array(DATA.symbols.length).fill(0);
  outdeg = new Array(DATA.symbols.length).fill(0);
  for (const [si, di, k] of DATA.edges) {
    outEdges[si].push([di, k]); indeg[di]++;
    inEdges[di].push([si, k]); outdeg[si]++;
  }
}
const totalDegree = (i) => indeg[i] + outdeg[i];

/* Function containing an address (binary search on start addr, then range) */
function findContainingSymbol(addr) {
  const s = DATA.symbols;
  let lo = 0, hi = s.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (s[mid].a <= addr) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  if (ans >= 0 && addr < s[ans].e) return s[ans];
  return null;
}
function findExactSymbol(addr) { return byAddr.get(addr) || null; }

/* Categories: fixed palette assigned by name */
const CAT_COLORS = {};
function catColor(cat) {
  if (!CAT_COLORS[cat]) {
    const palette = ["#58a6ff", "#7ee787", "#d29922", "#f0883e", "#bc8cff",
                     "#39c5cf", "#f85149", "#79c0ff", "#a5d6ff", "#ffa657",
                     "#3fb950", "#db61a2", "#2f81f7", "#e3b341", "#56d4dd"];
    CAT_COLORS[cat] = palette[Object.keys(CAT_COLORS).length % palette.length];
  }
  return CAT_COLORS[cat];
}
const ROM_LABEL = { 1: "FC00", 2: "FC00-hand", 4: "E1D400-ida", 8: "E1D400" };
function romTags(r) {
  const out = [];
  if (r & 3) out.push("FC00");
  if (r & 12) out.push("E1D400");
  return out.length ? out.join("+") : "cg";
}

/* ============================ GENERIC RENDER ============================ */
function renderSymRow(sym, i) {
  const cs = [fmtNum(indeg[i]), fmtNum(outdeg[i])];
  return `<tr data-i="${i}">
    <td class="addr">${hex(sym.a)}</td>
    <td class="name">${esc(sym.n)}${sym.d ? ' <span class="tag doc">doc</span>' : ""}</td>
    <td class="cat">${esc(sym.c)}</td>
    <td><span class="tag">${romTags(sym.r)}</span></td>
    <td>${sym.d ? '<span class="tag doc">doc</span>' : ""}</td>
    <td>${cs[1]}</td><td>${cs[0]}</td>
  </tr>`;
}

function detailSymbolHtml(i) {
  const sym = DATA.symbols[i];
  if (!sym) return "";
  const callers = inEdges[i].slice().sort((a, b) => a[0] - b[0]);
  const callees = outEdges[i].slice().sort((a, b) => a[0] - b[0]);
  const edgeRow = (o, k) =>
    `<tr><td class="k">${k === "b" ? "bsr" : "ref"}</td><td>${hex(DATA.symbols[o].a)}</td>
     <td class="name">${esc(DATA.symbols[o].n)}</td></tr>`;
  // --- real documentation from the .md ---
  const doc = docForSym(sym);
  let docHtml;
  if (doc) {
    docHtml = `<h4>Documentation</h4>
      <div class="doc-block">
        <div class="doc-title">${esc(doc.t)}${doc.a !== null && doc.a !== undefined ? ` <span class="muted">· ${hex(doc.a)}</span>` : ""}</div>
        <div class="doc-file">docs/functions/${esc(doc.f)}.md</div>
        ${mdToHtml(doc.b)}
      </div>`;
  } else {
    docHtml = `<h4>Documentation</h4>
      <div class="doc-block none">
        <p class="muted">No document in <code>docs/functions/</code> for this function.</p>
      </div>`;
  }
  return `<h4>${esc(sym.n)}</h4>
  <div class="kv-list">
    <div>Address</div><div>${hex(sym.a)}</div>
    <div>Range</div><div>${hex(sym.a)} – ${hex(sym.e)} (${sym.e - sym.a} bytes)</div>
    <div>Category</div><div>${esc(sym.c)}</div>
    <div>Name source</div><div>${esc(sym.s)}</div>
    <div>ROM</div><div>${romTags(sym.r)}</div>
    <div>Documented</div><div>${doc ? `yes (docs/functions/${esc(doc.f)}.md)` : "no"}</div>
    <div>Callers / Callees</div><div>${callers.length} / ${callees.length}</div>
  </div>
  <div class="toolbar"><button data-cg="${i}">Open in callgraph</button></div>
  <h4>Callers</h4>
  <div class="edge-list"><table>${callers.length ? callers.map(([o, k]) => edgeRow(o, k)).join("") : '<tr><td class="muted">none</td></tr>'}</table></div>
  <h4>Callees</h4>
  <div class="edge-list"><table>${callees.length ? callees.map(([o, k]) => edgeRow(o, k)).join("") : '<tr><td class="muted">none</td></tr>'}</table></div>
  ${docHtml}`;
}

/* ============================ TABS ============================ */
function activateTab(name) {
  document.querySelectorAll("#tabs button").forEach((x) => x.classList.remove("active"));
  document.querySelectorAll(".panel").forEach((x) => x.classList.remove("active"));
  const b = document.querySelector(`#tabs button[data-tab="${name}"]`);
  if (b) b.classList.add("active");
  const p = $("panel-" + name);
  if (p) p.classList.add("active");
}
function wireTabs() {
  document.querySelectorAll("#tabs button").forEach((b) => {
    b.addEventListener("click", () => {
      activateTab(b.dataset.tab);
      try { history.pushState(null, "", "#" + b.dataset.tab); } catch (e) { /* file:// ok */ }
    });
  });
}

/* ============================ DASHBOARD ============================ */
function renderDashboard() {
  const c = DATA.meta.counts;
  $("header-stats").innerHTML =
    `<div class="hstat"><b>${fmtNum(c.symbols)}</b><span>symbols</span></div>
     <div class="hstat"><b>${fmtNum(c.edges)}</b><span>edges</span></div>
     <div class="hstat"><b>${fmtNum(c.tables)}</b><span>tables</span></div>
     <div class="hstat"><b>${fmtNum(c.tables_with_values)}</b><span>with values</span></div>
     <div class="hstat"><b>${fmtNum(c.docs_total)}</b><span>function docs</span></div>
     <div class="hstat"><b>${fmtNum(c.subsystems)}</b><span>subsystems</span></div>`;
  $("dash-cards").innerHTML = `
    <div class="card"><div class="num">${fmtNum(c.symbols)}</div><div class="lbl">Symbols / functions</div></div>
    <div class="card"><div class="num">${fmtNum(c.edges)}</div><div class="lbl">Callgraph edges (${fmtNum(c.edges_bsr)} bsr · ${fmtNum(c.edges_ref)} ref)</div></div>
    <div class="card"><div class="num">${fmtNum(c.tables_rows)}</div><div class="lbl">CSV table entries (${fmtNum(c.tables)} tables + ${fmtNum(c.tables_axes)} axes)</div></div>
    <div class="card"><div class="num">${fmtNum(c.tables_with_values)}</div><div class="lbl">Tables with values extracted from 60E1D400.bin</div></div>
    <div class="card"><div class="num">${fmtNum(c.docs_total)}</div><div class="lbl">Function docs (${fmtNum(c.docs_attached)} matched to symbols)</div></div>
    <div class="card"><div class="num">${fmtNum(c.subsystems)}</div><div class="lbl">Subsystem docs in docs/subsystems</div></div>`;

  // symbol categories
  const sc = {};
  for (const s of DATA.symbols) sc[s.c] = (sc[s.c] || 0) + 1;
  barsInto("dash-sym-cats", sc);
  // table categories
  const tc = {};
  for (const t of DATA.tables) tc[t.c] = (tc[t.c] || 0) + 1;
  barsInto("dash-tbl-cats", tc);

  // top functions by degree
  const ranked = DATA.symbols.map((s, i) => ({ i, deg: totalDegree(i) }))
    .sort((a, b) => b.deg - a.deg).slice(0, 14);
  $("dash-top").innerHTML = `<thead><tr><th>Function</th><th>Address</th><th>Degree</th><th>Callers</th><th>Callees</th><th>Category</th></tr></thead><tbody>` +
    ranked.map(({ i, deg }) => {
      const s = DATA.symbols[i];
      return `<tr data-sym-i="${i}"><td class="name">${esc(s.n)}${s.d ? ' <span class="tag doc">doc</span>' : ""}</td>
        <td class="addr">${hex(s.a)}</td><td>${fmtNum(deg)}</td><td>${fmtNum(indeg[i])}</td><td>${fmtNum(outdeg[i])}</td>
        <td class="cat">${esc(s.c)}</td></tr>`;
    }).join("") + "</tbody>";
  $("dash-top").addEventListener("click", (ev) => {
    const tr = ev.target.closest("tr[data-sym-i]");
    if (tr) openCallgraph(parseInt(tr.dataset.symI, 10));
  });
}
function barsInto(id, counts) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 12);
  const max = Math.max(1, ...entries.map((e) => e[1]));
  $(id).innerHTML = entries.map(([k, v]) =>
    `<div class="bar-row"><span>${esc(k)}</span>
       <div class="bar-bg"><div class="bar-fg" style="width:${(v / max * 100).toFixed(1)}%;background:${catColor(k)}"></div></div>
       <span class="bar-num">${fmtNum(v)}</span></div>`).join("") ||
    '<span class="muted">no data</span>';
}

/* ============================ SYMBOLS ============================ */
const SymBrowser = {
  page: 0, perPage: 200, rows: [],
  apply() {
    const q = $("sym-search").value.trim().toLowerCase();
    const cat = $("sym-cat").value, rom = $("sym-rom").value, doc = $("sym-doc").value;
    const qHex = parseHex(q);
    this.rows = DATA.symbols.map((s, i) => ({ s, i })).filter(({ s }) => {
      if (cat && s.c !== cat) return false;
      if (rom === "F" && !(s.r & 3)) return false;
      if (rom === "E" && !(s.r & 12)) return false;
      if (rom === "FE" && !((s.r & 3) && (s.r & 12))) return false;
      if (doc === "1" && !s.d) return false;
      if (!q) return true;
      if (s.n.toLowerCase().includes(q)) return true;
      if (s.a === qHex) return true;
      const hs = hex6(s.a);
      return hs.includes(q) || ("0x" + hs).includes(q) || hs.toLowerCase().includes(q.replace(/^0x/, ""));
    });
    this.page = 0;
    this.render();
  },
  render() {
    const n = this.rows.length;
    const pages = Math.max(1, Math.ceil(n / this.perPage));
    if (this.page >= pages) this.page = pages - 1;
    const slice = this.rows.slice(this.page * this.perPage, (this.page + 1) * this.perPage);
    $("sym-tbody").innerHTML = slice.map(({ s, i }) => renderSymRow(s, i)).join("") ||
      `<tr><td colspan="7" class="muted">No matches</td></tr>`;
    $("sym-count").textContent = `${fmtNum(n)} of ${fmtNum(DATA.symbols.length)} · page ${this.page + 1}/${pages}`;
    $("sym-prev").disabled = this.page <= 0;
    $("sym-next").disabled = this.page >= pages - 1;
  },
  showDetail(i) {
    $("sym-detail").innerHTML = detailSymbolHtml(i);
    $("sym-detail").querySelector("[data-cg]").addEventListener("click", () => openCallgraph(i));
    try { history.pushState(null, "", "#sym-0x" + hex6(DATA.symbols[i].a)); } catch (e) { /* file:// ok */ }
  },
};
function wireSymbols() {
  ["sym-search", "sym-cat", "sym-rom", "sym-doc"].forEach((id) =>
    $(id).addEventListener("input", () => SymBrowser.apply()));
  $("sym-prev").addEventListener("click", () => { SymBrowser.page--; SymBrowser.render(); });
  $("sym-next").addEventListener("click", () => { SymBrowser.page++; SymBrowser.render(); });
  $("sym-tbody").addEventListener("click", (ev) => {
    const tr = ev.target.closest("tr[data-i]");
    if (!tr) return;
    const i = parseInt(tr.dataset.i, 10);
    document.querySelectorAll("#sym-tbody tr.sel").forEach((x) => x.classList.remove("sel"));
    tr.classList.add("sel");
    SymBrowser.showDetail(i);
  });
  // populate category and ROM selects
  const cats = {};
  for (const s of DATA.symbols) cats[s.c] = 1;
  $("sym-cat").innerHTML = `<option value="">All categories</option>` +
    Object.keys(cats).sort().map((c) => `<option>${esc(c)}</option>`).join("");
  $("sym-rom").innerHTML = `<option value="">All ROMs</option>
    <option value="F">60E0FC00 (callgraph)</option>
    <option value="E">60E1D400 (baseline)</option>
    <option value="FE">Present in both</option>`;
  SymBrowser.apply();
}

/* ============================ CALLGRAPH ============================ */
const CG = {
  root: null, nodes: [], edges: [], depth: 1,
  showRef: true, showBsr: true,
  pos: [], vel: [], pinned: new Set(), deg: [],
  role: [], level: [],
  W: 800, H: 620,
  view: { x: 0, y: 0, s: 1 },
  selected: null, hover: null, dragging: null,
  simTimer: null, running: false,
};

function cgEdgeOk(k) {
  return (k === "b" && CG.showBsr) || (k === "r" && CG.showRef);
}
function buildEgo(idx) {
  const depth = CG.depth;
  const ok = cgEdgeOk;
  const inSet = new Map(), outSet = new Map(); // node -> level
  inSet.set(idx, 0); outSet.set(idx, 0);
  // callee (outbound)
  let frontier = [idx], seen = new Set([idx]), lv = 0;
  while (frontier.length && lv < depth) {
    const next = [];
    for (const n of frontier) {
      for (const [o, k] of outEdges[n]) {
        if (!ok(k) || seen.has(o)) continue;
        seen.add(o); outSet.set(o, lv + 1); next.push(o);
      }
    }
    frontier = next; lv++;
  }
  // caller (inbound)
  frontier = [idx]; seen = new Set([idx]); lv = 0;
  while (frontier.length && lv < depth) {
    const next = [];
    for (const n of frontier) {
      for (const [o, k] of inEdges[n]) {
        if (!ok(k) || seen.has(o)) continue;
        seen.add(o); inSet.set(o, lv + 1); next.push(o);
      }
    }
    frontier = next; lv++;
  }
  const nodes = [...new Set([...inSet.keys(), ...outSet.keys()])];
  const cap = 320;
  if (nodes.length > cap) {
    // keep the levels closest to the root
    nodes.sort((a, b) => (Math.min(inSet.get(a) || 9, outSet.get(a) || 9)) - (Math.min(inSet.get(b) || 9, outSet.get(b) || 9)));
    nodes.length = cap;
  }
  const nodeSet = new Set(nodes);
  const edgeSet = new Set();
  const edges = [];
  for (const n of nodes) {
    for (const [o, k] of outEdges[n]) {
      if (nodeSet.has(o) && ok(k)) {
        const key = n + ":" + o;
        if (!edgeSet.has(key)) { edgeSet.add(key); edges.push([n, o, k]); }
      }
    }
  }
  return { nodes, edges, inSet, outSet };
}

function layoutEgo() {
  const { nodes, edges, inSet, outSet } = buildEgo(CG.root);
  CG.nodes = nodes;
  const posOf = new Map();
  nodes.forEach((n, i) => posOf.set(n, i));
  CG.edges = [];
  for (const [n, o, k] of edges) {
    const a = posOf.get(n), b = posOf.get(o);
    if (a !== undefined && b !== undefined) CG.edges.push([a, b, k]);
  }
  const N = nodes.length;
  CG.pos = new Array(N); CG.vel = new Array(N);
  CG.pinned = new Set(); CG.role = new Array(N); CG.level = new Array(N);
  CG.deg = nodes.map((n, i) => totalDegree(n));
  const maxDeg = Math.max(1, ...CG.deg);
  for (let i = 0; i < N; i++) {
    const n = nodes[i];
    const isCallee = outSet.has(n), isCaller = inSet.has(n);
    let lv;
    if (n === CG.root) { lv = 0; CG.role[i] = "root"; }
    else if (isCallee && isCaller) {
      lv = Math.min(outSet.get(n), inSet.get(n));
      CG.role[i] = "mixed";
      // place on the side with the smaller level; ties go right
      const side = outSet.get(n) <= inSet.get(n) ? 1 : -1;
      lv = side * (outSet.get(n) <= inSet.get(n) ? outSet.get(n) : inSet.get(n));
      CG.level[i] = lv;
    } else if (isCallee) { lv = outSet.get(n); CG.role[i] = "callee"; }
    else { lv = -inSet.get(n); CG.role[i] = "caller"; }
    CG.level[i] = lv;
    const x = lv * 170 + (Math.random() - 0.5) * 40;
    const y = (Math.random() - 0.5) * 200 + (i % 2) * 30;
    CG.pos[i] = { x, y };
    CG.vel[i] = { x: 0, y: 0 };
  }
  // start stepped simulation
  CG.simTick = 0;
  runSim();
}
function runSim() {
  CG.running = true;
  if (CG.simTimer) clearTimeout(CG.simTimer);
  const step = () => {
    for (let k = 0; k < 24 && CG.simTick < 380; k++) simStep();
    if (CG.simTick >= 380) { CG.running = false; drawCG(); return; }
    drawCG();
    CG.simTimer = setTimeout(step, 8);
  };
  step();
}
function simStep() {
  const { nodes, edges } = CG;
  const N = nodes.length;
  const pos = CG.pos, vel = CG.vel;
  const krep = 5200, kspring = 0.03, klev = 0.05, kc = 0.002, damping = 0.86;
  const targetX = nodes.map((n, i) => CG.level[i] * 170);
  for (let i = 0; i < N; i++) {
    for (let j = i + 1; j < N; j++) {
      let dx = pos[i].x - pos[j].x, dy = pos[i].y - pos[j].y;
      let d2 = dx * dx + dy * dy + 0.5;
      let f = krep / d2;
      const d = Math.sqrt(d2);
      if (f > 60) f = 60;
      const fx = dx / d * f, fy = dy / d * f;
      vel[i].x += fx; vel[i].y += fy; vel[j].x -= fx; vel[j].y -= fy;
    }
  }
  for (const [a, b] of edges) {
    let dx = pos[a].x - pos[b].x, dy = pos[a].y - pos[b].y;
    const d = Math.sqrt(dx * dx + dy * dy) || 1;
    const rest = 85;
    const f = (d - rest) * kspring;
    const fx = dx / d * f, fy = dy / d * f;
    vel[a].x -= fx; vel[a].y -= fy; vel[b].x += fx; vel[b].y += fy;
  }
  for (let i = 0; i < N; i++) {
    vel[i].x += (targetX[i] - pos[i].x) * klev;
    vel[i].y += (0 - pos[i].y) * klev * 0.3;
    vel[i].x += (0 - pos[i].x) * kc;
    vel[i].y += (0 - pos[i].y) * kc;
    vel[i].x *= damping; vel[i].y *= damping;
    if (CG.pinned.has(i)) continue;
    pos[i].x += vel[i].x;
    pos[i].y += vel[i].y;
    if (Math.abs(pos[i].x) > 2600) pos[i].x = pos[i].x > 0 ? 2600 : -2600;
    if (Math.abs(pos[i].y) > 2200) pos[i].y = pos[i].y > 0 ? 2200 : -2200;
  }
  CG.simTick++;
}
function nodeRadius(i) {
  const r = 3.2 + 4.2 * Math.log10(1 + CG.deg[i]);
  return CG.nodes[i] === CG.root ? r + 4 : r;
}
function nodeColor(role) {
  if (role === "root") return "#d29922";
  if (role === "caller") return "#58a6ff";
  if (role === "callee") return "#7ee787";
  return "#bc8cff";
}
function drawCG() {
  const cv = $("cg-canvas");
  const dpr = window.devicePixelRatio || 1;
  CG.W = cv.clientWidth || 800; CG.H = cv.clientHeight || 620;
  cv.width = CG.W * dpr; cv.height = CG.H * dpr;
  const g = cv.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, CG.W, CG.H);
  const { x: ox, y: oy, s } = CG.view;
  const sx = (p) => p.x * s + ox, sy = (p) => p.y * s + oy;
  // edges
  for (const [a, b, k] of CG.edges) {
    g.beginPath();
    g.moveTo(sx(CG.pos[a]), sy(CG.pos[a]));
    g.lineTo(sx(CG.pos[b]), sy(CG.pos[b]));
    g.strokeStyle = k === "b" ? "rgba(139,148,158,0.45)" : "rgba(139,148,158,0.16)";
    g.lineWidth = k === "b" ? 1.3 : 1;
    if (k === "r") g.setLineDash([3, 4]); else g.setLineDash([]);
    g.stroke();
  }
  g.setLineDash([]);
  // nodes
  const fontBase = 10 / Math.max(s, 0.35);
  for (let i = 0; i < CG.nodes.length; i++) {
    const r = nodeRadius(i);
    const x = sx(CG.pos[i]), y = sy(CG.pos[i]);
    const col = nodeColor(CG.role[i]);
    const grad = g.createRadialGradient(x - r * 0.3, y - r * 0.3, r * 0.2, x, y, r);
    grad.addColorStop(0, col); grad.addColorStop(1, "rgba(13,17,23,0.9)");
    g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2);
    g.fillStyle = grad; g.fill();
    g.lineWidth = 1.5;
    g.strokeStyle = i === CG.selected ? "#ffffff" : (i === CG.hover ? "#f0883e" : col);
    g.stroke();
    if (s > 0.45 && r > 5) {
      const s2 = DATA.symbols[CG.nodes[i]];
      if (s2 && !/^FUN_[0-9a-f]+$/.test(s2.n)) {
        let label = s2.n;
        if (label.length > 16) label = label.slice(0, 15) + "…";
        const mono = getComputedStyle(cv).getPropertyValue("--mono") || "monospace";
        g.font = "10px " + mono;
        g.fillStyle = "rgba(230,237,243,0.85)";
        g.textAlign = "center";
        g.fillText(label, x, y + r + 11);
      }
    }
  }
  if (CG.running) {
    g.fillStyle = "rgba(139,148,158,0.8)";
    g.font = "11px monospace";
    g.textAlign = "left";
    g.fillText("layout in progress… (" + CG.simTick + "/380)", 10, 18);
  }
}
function cgNodeAt(mx, my) {
  let best = -1, bd = 1e9;
  for (let i = 0; i < CG.nodes.length; i++) {
    const x = CG.pos[i].x * CG.view.s + CG.view.x;
    const y = CG.pos[i].y * CG.view.s + CG.view.y;
    const d = Math.hypot(mx - x, my - y);
    if (d < bd) { bd = d; best = i; }
  }
  return bd <= Math.max(14, nodeRadius(best) + 3) ? best : -1;
}
function cgDetail(i) {
  const n = CG.nodes[i];
  if (n === undefined) { $("cg-detail").innerHTML = ""; return; }
  const s = DATA.symbols[n];
  const role = CG.role[i];
  const callers = inEdges[n].filter(([o, k]) => cgEdgeOk(k)).slice(0, 40);
  const callees = outEdges[n].filter(([o, k]) => cgEdgeOk(k)).slice(0, 40);
  const row = (o, k) => `<tr><td class="k">${k === "b" ? "bsr" : "ref"}</td><td>${hex(DATA.symbols[o].a)}</td><td class="name">${esc(DATA.symbols[o].n)}</td></tr>`;
  $("cg-detail").innerHTML = `
    <h4>${esc(s.n)}</h4>
    <div class="kv-list">
      <div>Address</div><div>${hex(s.a)}</div>
      <div>Role</div><div>${role}</div>
      <div>Total degree</div><div>${fmtNum(totalDegree(n))}</div>
      <div>Category</div><div>${esc(s.c)}</div>
    </div>
    <h4>Direct callers (${fmtNum(callers.length)}${inEdges[n].length > callers.length ? "+" : ""})</h4>
    <div class="edge-list"><table>${callers.length ? callers.map(([o, k]) => row(o, k)).join("") : '<tr><td class="muted">none</td></tr>'}</table></div>
    <h4>Direct callees (${fmtNum(callees.length)}${outEdges[n].length > callees.length ? "+" : ""})</h4>
    <div class="edge-list"><table>${callees.length ? callees.map(([o, k]) => row(o, k)).join("") : '<tr><td class="muted">none</td></tr>'}</table></div>`;
}
function openCallgraph(i) {
  document.querySelector("#tabs button[data-tab=callgraph]").click();
  CG.root = i; CG.selected = null;
  $("cg-input").value = DATA.symbols[i].n;
  buildAndLayout();
}
function buildAndLayout() {
  $("cg-info").textContent = "";
  if (CG.root === null) return;
  layoutEgo();
  CG.view = { x: 0, y: 0, s: 1 };
  fitView();
  const { nodes, edges } = { nodes: CG.nodes, edges: CG.edges };
  $("cg-info").textContent = `${fmtNum(nodes.length)} nodes · ${fmtNum(edges.length)} edges (depth ${CG.depth})`;
  cgDetail(-1);
}
function fitView() {
  if (!CG.nodes.length) return;
  let minX = 1e9, maxX = -1e9, minY = 1e9, maxY = -1e9;
  for (let i = 0; i < CG.nodes.length; i++) {
    minX = Math.min(minX, CG.pos[i].x); maxX = Math.max(maxX, CG.pos[i].x);
    minY = Math.min(minY, CG.pos[i].y); maxY = Math.max(maxY, CG.pos[i].y);
  }
  const pad = 60;
  const w = Math.max(1, maxX - minX), h = Math.max(1, maxY - minY);
  CG.view.s = Math.min((CG.W - pad * 2) / w, (CG.H - pad * 2) / h, 1.6);
  CG.view.x = CG.W / 2 - (minX + w / 2) * CG.view.s;
  CG.view.y = CG.H / 2 - (minY + h / 2) * CG.view.s;
}
function wireCallgraph() {
  const cv = $("cg-canvas");
  let pan = null;
  cv.addEventListener("mousedown", (ev) => {
    const rect = cv.getBoundingClientRect();
    const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
    const i = cgNodeAt(mx, my);
    if (i >= 0) {
      CG.dragging = i; CG.pinned.add(i);
      cv.classList.add("dragging");
    } else {
      pan = { x: ev.clientX, y: ev.clientY, vx: CG.view.x, vy: CG.view.y };
      cv.classList.add("dragging");
    }
  });
  window.addEventListener("mousemove", (ev) => {
    const rect = cv.getBoundingClientRect();
    const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
    if (CG.dragging !== null && CG.dragging >= 0) {
      CG.pos[CG.dragging].x = (mx - CG.view.x) / CG.view.s;
      CG.pos[CG.dragging].y = (my - CG.view.y) / CG.view.s;
      drawCG(); return;
    }
    if (pan) {
      CG.view.x = pan.vx + (ev.clientX - pan.x);
      CG.view.y = pan.vy + (ev.clientY - pan.y);
      drawCG(); return;
    }
    const i = cgNodeAt(mx, my);
    if (i !== CG.hover) { CG.hover = i; drawCG(); }
    const tip = $("cg-tip");
    if (i >= 0) {
      const s = DATA.symbols[CG.nodes[i]];
      tip.textContent = `${s.n} · ${hex(s.a)}`;
      tip.style.left = (mx + 12) + "px"; tip.style.top = (my + 12) + "px";
      tip.classList.remove("hidden");
    } else tip.classList.add("hidden");
  });
  window.addEventListener("mouseup", () => {
    pan = null; CG.dragging = null; cv.classList.remove("dragging");
  });
  cv.addEventListener("click", (ev) => {
    const rect = cv.getBoundingClientRect();
    const i = cgNodeAt(ev.clientX - rect.left, ev.clientY - rect.top);
    if (i >= 0) {
      CG.selected = i;
      const n = CG.nodes[i];
      if (n !== CG.root) {
        // re-center the ego-graph on this node
        CG.root = n; CG.selected = null;
        buildAndLayout();
      } else {
        cgDetail(i); drawCG();
      }
    }
  });
  cv.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    const rect = cv.getBoundingClientRect();
    const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
    const f = ev.deltaY < 0 ? 1.12 : 1 / 1.12;
    CG.view.s = Math.min(3, Math.max(0.15, CG.view.s * f));
    CG.view.x = mx - (mx - CG.view.x) * f;
    CG.view.y = my - (my - CG.view.y) * f;
    drawCG();
  }, { passive: false });
  window.addEventListener("resize", () => drawCG());

  // autocomplete
  const inp = $("cg-input"), sug = $("cg-suggest");
  let sel = -1, items = [];
  function pick(i) {
    if (items[i] !== undefined) { CG.root = items[i]; openCallgraph(items[i]); }
  }
  inp.addEventListener("input", () => {
    const q = inp.value.trim().toLowerCase();
    sug.classList.remove("hidden");
    if (!q) { items = []; sug.innerHTML = ""; return; }
    const qHex = parseHex(q);
    items = [];
    for (let i = 0; i < DATA.symbols.length && items.length < 14; i++) {
      const s = DATA.symbols[i];
      if (s.n.toLowerCase().includes(q) || (qHex !== null && (s.a === qHex || hex6(s.a).includes(q.replace(/^0x/, "").toLowerCase())))) {
        items.push(i);
      }
    }
    sel = -1;
    sug.innerHTML = items.map((i, k) =>
      `<div data-k="${k}" class="${k === 0 ? "sel" : ""}"><span class="s-addr">${hex(DATA.symbols[i].a)}</span>${esc(DATA.symbols[i].n)}</div>`).join("") ||
      `<div class="muted">no results</div>`;
  });
  inp.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowDown") { sel = Math.min(items.length - 1, sel + 1); highlight(); ev.preventDefault(); }
    else if (ev.key === "ArrowUp") { sel = Math.max(0, sel - 1); highlight(); ev.preventDefault(); }
    else if (ev.key === "Enter") { if (sel >= 0) pick(sel); else resolveCgInput(); }
    else if (ev.key === "Escape") sug.classList.add("hidden");
  });
  function highlight() {
    sug.querySelectorAll("div[data-k]").forEach((d) => d.classList.toggle("sel", +d.dataset.k === sel));
  }
  sug.addEventListener("mousedown", (ev) => {
    const d = ev.target.closest("div[data-k]");
    if (d) { pick(+d.dataset.k); }
  });
  function resolveCgInput() {
    const q = inp.value.trim();
    const qHex = parseHex(q);
    if (qHex !== null) {
      const s = findExactSymbol(qHex);
      if (s) { CG.root = symIdx.get(qHex); openCallgraph(CG.root); return; }
    }
    const hit = DATA.symbols.find((s) => s.n.toLowerCase() === q.toLowerCase());
    if (hit) { CG.root = symIdx.get(hit.a); openCallgraph(CG.root); }
    else inp.dispatchEvent(new Event("input"));
  }
  $("cg-fit").addEventListener("click", () => { fitView(); drawCG(); });
  $("cg-reset").addEventListener("click", () => {
    if (CG.root !== null) { buildAndLayout(); }
  });
  $("cg-depth").addEventListener("change", () => {
    CG.depth = parseInt($("cg-depth").value, 10);
    if (CG.root !== null) buildAndLayout();
  });
  $("cg-ref").addEventListener("change", () => { CG.showRef = $("cg-ref").checked; if (CG.root !== null) buildAndLayout(); });
  $("cg-bsr").addEventListener("change", () => { CG.showBsr = $("cg-bsr").checked; if (CG.root !== null) buildAndLayout(); });
  // click on rows in the detail lists -> navigate
  $("cg-detail").addEventListener("click", (ev) => {
    const td = ev.target.closest("td.name");
    if (!td) return;
    const i = CG.nodes.findIndex((n) => DATA.symbols[n].n === td.textContent.trim());
    if (i >= 0) { CG.root = CG.nodes[i]; buildAndLayout(); }
  });
}

/* ============================ TABLES ============================ */
const Tbl = { page: 0, perPage: 150, rows: [], sel: null };
/* Type label of a value payload v ({t?, ax?, scalar?}). */
function valTypeLabel(v) {
  if (v && v.t) return v.t.kind === "2D" ? `grid ${v.t.cx}×${v.t.cy} (${v.t.type})` : `vec ${v.t.cx} (${v.t.type})`;
  if (v && v.scalar !== null && v.scalar !== undefined) return "scalar";
  if (v && v.ax) return "f32 axis";
  return "—";
}
/* Classification of a value payload for the "type" filter. */
function valTypeKey(v) {
  if (v && v.t && v.t.grid) return "grid";
  if (v && v.t && v.t.vals) return "vals";
  if (v && v.scalar !== null && v.scalar !== undefined) return "scalar";
  if (v && v.ax) return "axis";
  return "noval";
}
function TblApply() {
  const q = $("tbl-search").value.trim().toLowerCase();
  const cat = $("tbl-cat").value, typ = $("tbl-type").value, role = $("tbl-role").value;
  const qHex = parseHex(q);
  Tbl.rows = DATA.tables.map((t, i) => ({ t, i })).filter(({ t, i }) => {
    if (role === "t" && t.role !== "t") return false;
    if (role === "x" && t.role !== "x") return false;
    if (role === "y" && t.role !== "y") return false;
    if (cat && t.c !== cat) return false;
    // type filter follows the CURRENT model's values (fallback: baseline when
    // the model values are not loaded yet)
    const vk = valTypeKey(modelVal(i));
    if (typ === "grid" && vk !== "grid") return false;
    if (typ === "vals" && vk !== "vals") return false;
    if (typ === "scalar" && vk !== "scalar") return false;
    if (typ === "axis" && vk !== "axis") return false;
    if (typ === "noval" && vk !== "noval") return false;
    if (!q) return true;
    if (t.n.toLowerCase().includes(q)) return true;
    if (t.a === qHex) return true;
    const hs = hex6(t.a);
    if (hs.includes(q) || ("0x" + hs).includes(q)) return true;
    if (t.role !== "t" && t.tbl && t.tbl.toLowerCase().includes(q)) return true;
    return false;
  });
  Tbl.page = 0;
  TblRender();
}
function TblRender() {
  const n = Tbl.rows.length;
  const pages = Math.max(1, Math.ceil(n / Tbl.perPage));
  if (Tbl.page >= pages) Tbl.page = pages - 1;
  const slice = Tbl.rows.slice(Tbl.page * Tbl.perPage, (Tbl.page + 1) * Tbl.perPage);
  $("tbl-tbody").innerHTML = slice.map(({ t, i }) => {
    const roleLabel = { t: "table", x: "X axis", y: "Y axis" }[t.role];
    const mm = modelMap(i);
    const mv = modelVal(i);
    const tv = modelValHasData(i) ? "yes" : "—";
    const modelAddrCell = mm
      ? `<td class="addr">${hex(mm.a)}${mm.a !== t.a ? `<span class="tag addr-delta" title="differs from the baseline (60E1D400) address">Δ</span>` : ""} ${confBadge(mm.c)}</td>`
      : `<td class="addr muted">—</td>`;
    const mapCell = mm
      ? `${methodBadge(mm.m)} ${confBadge(mm.c)}`
      : `<span class="tag unmapped">not mapped</span>`;
    const valCell = mm
      ? (tv === "yes" ? `<span class="tag has-val">values</span>` : `<span class="muted">—</span>`)
      : `<span class="muted">—</span>`;
    return `<tr data-rid="${i}" ${mm ? "" : 'class="row-unmapped"'}>
      ${modelAddrCell}
      <td class="addr-base-cell">${hex(t.a)}</td>
      <td class="name">${esc(t.n)}${t.role !== "t" ? `<span class="muted"> · of ${esc(t.tbl || "?")}</span>` : ""}</td>
      <td>${roleLabel}</td>
      <td>${valTypeLabel(modelVal(i))}</td>
      <td class="cat">${esc(t.c)}</td>
      <td>${mapCell}</td>
      <td>${valCell}</td></tr>`;
  }).join("") || `<tr><td colspan="8" class="muted">No matches</td></tr>`;
  $("tbl-count").textContent = `${fmtNum(n)} entries · page ${Tbl.page + 1}/${pages}`;
  $("tbl-prev").disabled = Tbl.page <= 0;
  $("tbl-next").disabled = Tbl.page >= pages - 1;
}
function TblDetail(rid) {
  const t = DATA.tables[rid];
  if (!t) return;
  Tbl.sel = rid;
  const mm = modelMap(rid);
  const mv = modelVal(rid);
  const m = modelByKey(CUR_MODEL) || { cal_id: CUR_MODEL, file: "" };
  const t0 = mv && mv.t ? mv.t : null;
  let html = `<h4>${esc(t.n)}</h4><div class="kv-list">
    <div>Baseline address</div><div>${hex(t.a)}</div>
    <div>Model address (${esc(m.cal_id)})</div><div>${mm ? `${hex(mm.a)} ${methodBadge(mm.m)} ${confBadge(mm.c)}` : `<span class="tag unmapped">not mapped in this model</span>`}</div>
    <div>Role</div><div>${t.role === "t" ? "table" : t.role === "x" ? "X axis" : "Y axis"}</div>
    <div>Category</div><div>${esc(t.c)}</div>
    <div>Values ROM</div><div>${esc(m.file)} (${esc(m.cal_id)})</div>`;
  if (!mm) {
    html += `</div><div class="model-note">This table has <strong>no mapping</strong> in ${esc(m.cal_id)}
      (${esc(m.family)}): it is outside the mapped cal region or no evidence was found, so no
      address and no values are shown for this model. It is still listed with its baseline
      address (${hex(t.a)}, <code>60E1D400</code>).</div>`;
    html += `<div class="viz-wrap" id="tbl-viz"></div>`;
    $("tbl-detail").innerHTML = html;
    return;
  }
  if (t.role !== "t") {
    html += `<div>Group tables</div><div>${hex(t.tbladdr !== null && t.tbladdr !== undefined ? t.tbladdr : 0)}</div>`;
    if (mv && mv.ax) html += `<div>f32 axis (n=${mv.ax.length})</div><div>${mv.ax.map((v) => fmtNum(v, 2)).join(", ")}</div>`;
    else if (!mv) html += `<div>Axis values</div><div><span class="muted">not extracted for this model${CUR_MODEL !== DATA.defaultModel ? " (load failed?)" : ""}</span></div>`;
    html += `</div>`;
    html += `<div class="viz-wrap" id="tbl-viz"></div>`;
  } else {
    if (t0) {
      html += `<div>Kind</div><div>${t0.kind === "2D" ? "2D map (ThreeDLookup)" : "1D map (TwoDLookup)"}</div>
        <div>Size</div><div>${t0.kind === "2D" ? t0.cx + " × " + t0.cy : t0.cx + " values"}</div>
        <div>Cell type</div><div>${t0.type}</div>`;
      if (t0.scale !== undefined && t0.type !== "f32")
        html += `<div>Scale / Offset</div><div>${fmtNum(t0.scale, 4)} / ${fmtNum(t0.offset, 4)}</div>`;
      html += `<div>Descriptor</div><div>${hex(t0.desc)}</div>`;
    } else {
      if (mv) {
        html += `<div>Extracted values</div><div>no (no map descriptor in ${esc(m.file)})</div>`;
        if (mv.scalar !== null && mv.scalar !== undefined)
          html += `<div>Estimated f32 scalar</div><div>${fmtNum(mv.scalar, 4)}</div>`;
        if (mv.raw) html += `<div>Raw bytes</div><div>${mv.raw}</div>`;
      } else if (CUR_MODEL === DATA.defaultModel) {
        html += `<div>Extracted values</div><div>no (no map descriptor in ${esc(m.file)})</div>`;
      } else {
        html += `<div>Extracted values</div><div><span class="tag unmapped">unavailable</span> <span class="muted">per-model values not loaded (serve over HTTP to fetch <code>models/${esc(CUR_MODEL)}.json</code>)</span></div>`;
      }
    }
    html += `</div>`;
    html += `<div class="viz-wrap" id="tbl-viz"></div>`;
    html += `<div class="viz-wrap" id="tbl-viz-2"></div>`;
  }
  $("tbl-detail").innerHTML = html;
  const viz = $("tbl-viz");
  if (viz) {
    if (t0 && t0.grid) drawHeatmap(viz, t0);
    else if (t0 && t0.vals) draw1D(viz, t0);
    else if (mv && mv.ax) drawAxis(viz, mv.ax, t.n);
  }
  const viz2 = $("tbl-viz-2");
  if (viz2 && t0 && t0.ax) {
    if (!t0.grid && !t0.vals) { viz2.innerHTML = ""; }
    else {
      viz2.innerHTML = `<div class="kv-list"><div>${t0.kind === "2D" ? "X axis" : "Axis"}</div><div>${t0.ax.map((v) => fmtNum(v, 2)).join(", ")}</div></div>`;
      if (t0.kind === "2D")
        viz2.innerHTML += `<div class="kv-list" style="margin-top:6px"><div>Y axis</div><div>${t0.ay.map((v) => fmtNum(v, 2)).join(", ")}</div></div>`;
    }
  }
  try { history.pushState(null, "", "#tbl-0x" + hex6(t.a)); } catch (e) { /* file:// ok */ }
}
function wireTables() {
  ["tbl-search", "tbl-cat", "tbl-type", "tbl-role"].forEach((id) =>
    $(id).addEventListener("input", () => TblApply()));
  $("tbl-prev").addEventListener("click", () => { Tbl.page--; TblRender(); });
  $("tbl-next").addEventListener("click", () => { Tbl.page++; TblRender(); });
  $("tbl-tbody").addEventListener("click", (ev) => {
    const tr = ev.target.closest("tr[data-rid]");
    if (!tr) return;
    document.querySelectorAll("#tbl-tbody tr.sel").forEach((x) => x.classList.remove("sel"));
    tr.classList.add("sel");
    TblDetail(parseInt(tr.dataset.rid, 10));
  });
  const cats = {};
  for (const t of DATA.tables) cats[t.c] = 1;
  $("tbl-cat").innerHTML = `<option value="">All categories</option>` +
    Object.keys(cats).sort().map((c) => `<option>${esc(c)}</option>`).join("");
  TblApply();
}

/* ============================ DOCUMENTATION ============================ */
/* "Documentation" view: subsystems (docs/subsystems/*.md) + function docs
 * (docs/functions/*.md, including those not matched to a symbol). */
const DocView = {
  rows: [],
  cur: -1,
  apply() {
    const q = $("doc-search").value.trim().toLowerCase();
    const grp = $("doc-group").value;
    const symOfDoc = [];
    DATA.symbols.forEach((s, i) => { if (s.di !== undefined && symOfDoc[s.di] === undefined) symOfDoc[s.di] = i; });
    this.rows = [];
    DATA.subsystems.forEach((d, i) => {
      this.rows.push({ type: "sub", t: d.t, f: d.f, b: d.b, symI: -1 });
    });
    DATA.docs.forEach((d, i) => {
      this.rows.push({ type: "fun", t: d.t, f: d.f, b: d.b, a: d.a, symI: symOfDoc[i] !== undefined ? symOfDoc[i] : -1 });
    });
    this.rows = this.rows.filter((r) => {
      if (grp === "fun" && (r.type !== "fun" || r.symI < 0)) return false;
      if (grp === "unatt" && (r.type !== "fun" || r.symI >= 0)) return false;
      if (grp === "sub" && r.type !== "sub") return false;
      if (!q) return true;
      return (r.t + " " + r.f + " " + r.b).toLowerCase().includes(q);
    });
    this.render();
  },
  render() {
    $("doc-count").textContent = `${fmtNum(this.rows.length)} documents`;
    let html = "", lastType = "";
    this.rows.forEach((r, k) => {
      if (r.type !== lastType) {
        html += `<div class="doc-group">${r.type === "sub" ? "Subsystems" : "Functions"}</div>`;
        lastType = r.type;
      }
      const tag = r.type === "sub"
        ? '<span class="tag sub">subsystem</span>'
        : (r.symI >= 0 ? '<span class="tag doc">function</span>'
                        : '<span class="tag">function (unmatched)</span>');
      const addr = (r.a !== null && r.a !== undefined) ? ` ${hex(r.a)}` : "";
      html += `<div class="doc-item" data-k="${k}">
        <div class="doc-item-title">${esc(r.t)}${addr}</div>
        <div class="doc-item-meta">${tag} <span class="muted">${esc(r.f)}.md</span></div>
      </div>`;
    });
    $("doc-list").innerHTML = html || '<div class="muted" style="padding:12px">No documents match.</div>';
  },
  select(k, scrollTop) {
    if (k < 0 || k >= this.rows.length) return;
    this.cur = k;
    document.querySelectorAll("#doc-list .doc-item.sel").forEach((x) => x.classList.remove("sel"));
    const it = Array.from(document.querySelectorAll("#doc-list .doc-item")).find((x) => +x.dataset.k === k);
    if (it) { it.classList.add("sel"); it.scrollIntoView({ block: "nearest" }); }
    this.detail(k, scrollTop === false ? false : true);
  },
  detail(k, scrollTop) {
    const r = this.rows[k];
    if (!r) { $("doc-detail").innerHTML = ""; return; }
    const out = { toc: [] };
    const body = mdToHtml(r.b, out);
    let btn = "";
    if (r.symI >= 0) {
      const s = DATA.symbols[r.symI];
      btn = `<div class="toolbar" style="margin-top:8px"><button data-goto-sym="${r.symI}">Open ${esc(s.n)} in Symbols</button></div>`;
    }
    const tocHtml = out.toc.length >= 2
      ? `<div class="doc-toc"><div class="doc-toc-h">On this page</div><ul>` +
        out.toc.map((t) => `<li class="doc-toc-${t.level}"><a href="#${t.id}" data-sec="${t.id}">${esc(t.text)}</a></li>`).join("") +
        `</ul></div>`
      : "";
    const n = this.rows.length;
    const nav = `<div class="doc-nav">
        <span class="doc-nav-pos">${k + 1} / ${n}</span>
        <button data-nav="prev" ${k > 0 ? "" : "disabled"}>‹ Previous</button>
        <button data-nav="next" ${k < n - 1 ? "" : "disabled"}>Next ›</button>
      </div>`;
    $("doc-detail").innerHTML = `<h4>${esc(r.t)}</h4>
      <div class="kv-list">
        <div>Type</div><div>${r.type === "sub" ? "Subsystem" : "Function"}</div>
        <div>File</div><div>${r.type === "sub" ? "docs/subsystems/" : "docs/functions/"}<code>${esc(r.f)}.md</code></div>
        ${r.symI >= 0 ? `<div>Symbol</div><div>${hex(DATA.symbols[r.symI].a)} · ${esc(DATA.symbols[r.symI].n)}</div>` : ""}
      </div>
      ${btn}
      <div class="doc-block">${tocHtml}${body}</div>
      ${nav}`;
    const g = $("doc-detail").querySelector("[data-goto-sym]");
    if (g) g.addEventListener("click", () => openSymFromDoc(parseInt(g.dataset.gotoSym, 10)));
    $("doc-detail").querySelectorAll("[data-nav]").forEach((b) =>
      b.addEventListener("click", () => DocView.select(k + (b.dataset.nav === "next" ? 1 : -1))));
    try { history.pushState(null, "", "#doc-" + r.f); } catch (e) { /* file:// ok */ }
    if (scrollTop) {
      const el = $("doc-detail");
      if (el) el.scrollIntoView({ block: "start" });
    }
  },
};
function openSymFromDoc(i) {
  document.querySelector("#tabs button[data-tab=symbols]").click();
  document.querySelectorAll("#sym-tbody tr.sel").forEach((x) => x.classList.remove("sel"));
  const tr = Array.from(document.querySelectorAll("#sym-tbody tr[data-i]")).find((t) => +t.dataset.i === i);
  if (tr) { tr.classList.add("sel"); tr.scrollIntoView({ block: "center" }); }
  SymBrowser.showDetail(i);
}
function wireDocs() {
  ["doc-search", "doc-group"].forEach((id) =>
    $(id).addEventListener("input", () => DocView.apply()));
  $("doc-list").addEventListener("click", (ev) => {
    const it = ev.target.closest(".doc-item");
    if (it) DocView.select(parseInt(it.dataset.k, 10));
  });
  $("doc-detail").addEventListener("click", (ev) => {
    const a = ev.target.closest("a[data-sec]");
    if (!a) return;
    ev.preventDefault();
    const sec = a.dataset.sec;
    const el = $("doc-detail").querySelector("#" + sec);
    const r = (DocView.cur >= 0) ? DocView.rows[DocView.cur] : null;
    if (el && r) {
      el.scrollIntoView({ block: "start" });
      try { history.pushState(null, "", "#doc-" + r.f + "#" + sec); } catch (e) { /* file:// ok */ }
    }
  });
  DocView.apply();
}

/* ==================== VISUALIZATIONS (heatmap / 1D) ==================== */
/* "inferno"-like palette: 9 stops */
const INFERNO = [
  [0, 0, 4], [31, 12, 72], [85, 15, 109], [136, 34, 106], [186, 54, 85],
  [227, 89, 51], [249, 140, 10], [252, 201, 75], [252, 255, 164],
];
function heatColor(t) {
  t = Math.max(0, Math.min(1, t)) * (INFERNO.length - 1);
  const i = Math.floor(t), f = t - i, a = INFERNO[i], b = INFERNO[Math.min(i + 1, INFERNO.length - 1)];
  return `rgb(${Math.round(a[0] + (b[0] - a[0]) * f)},${Math.round(a[1] + (b[1] - a[1]) * f)},${Math.round(a[2] + (b[2] - a[2]) * f)})`;
}
function drawHeatmap(host, t0) {
  const cx = t0.cx, cy = t0.cy, grid = t0.grid;
  const vals = grid.filter((v) => v !== null && v !== undefined);
  let min = Math.min(...vals), max = Math.max(...vals);
  if (min === max) { min -= 1; max += 1; }
  const cell = Math.max(10, Math.min(34, Math.floor(880 / cx)));
  const m = { t: 34, l: 56, b: 40, r: 16 };
  const W = m.l + cx * cell + m.r, H = m.t + cy * cell + m.b;
  const cv = document.createElement("canvas");
  cv.width = W; cv.height = H;
  host.appendChild(cv);
  const g = cv.getContext("2d");
  g.fillStyle = "#0d1117"; g.fillRect(0, 0, W, H);
  for (let j = 0; j < cy; j++) {
    for (let i = 0; i < cx; i++) {
      const v = grid[j * cx + i];
      const x = m.l + i * cell, y = m.t + j * cell;
      if (v === null || v === undefined) {
        g.fillStyle = "#161b22";
        g.fillRect(x, y, cell, cell);
        g.strokeStyle = "#30363d"; g.strokeRect(x + 0.5, y + 0.5, cell - 1, cell - 1);
      } else {
        g.fillStyle = heatColor((v - min) / (max - min));
        g.fillRect(x, y, cell, cell);
      }
    }
  }
  // axes
  g.fillStyle = "#8b949e"; g.font = "11px monospace";
  g.textAlign = "right"; g.textBaseline = "middle";
  for (let j = 0; j < cy; j++) {
    const v = t0.ay ? t0.ay[j] : j;
    if (j % Math.ceil(cy / 16) === 0 || j === cy - 1)
      g.fillText(fmtNum(v, 2), m.l - 6, m.t + j * cell + cell / 2);
  }
  g.textAlign = "center"; g.textBaseline = "top";
  const xstep = Math.ceil(cx / 14);
  for (let i = 0; i < cx; i++) {
    if (i % xstep === 0 || i === cx - 1)
      g.fillText(fmtNum(t0.ax[i], 2), m.l + i * cell + cell / 2, m.t + cy * cell + 8);
  }
  g.textAlign = "left"; g.textBaseline = "middle";
  g.fillText("Y", 8, m.t / 2);
  g.fillText("X", m.l + cx * cell / 2, m.t + cy * cell + m.b - 10);
  // legend
  const lg = document.createElement("div");
  lg.className = "heat-legend";
  const grad = document.createElement("div");
  grad.className = "grad";
  grad.style.background = `linear-gradient(90deg, ${INFERNO.map((c) => `rgb(${c})`).join(",")})`;
  lg.innerHTML = `<span>${fmtNum(min, 3)}</span>`;
  lg.appendChild(grad);
  lg.insertAdjacentHTML("beforeend", `<span>${fmtNum(max, 3)}</span><span class="muted">(${t0.type}${t0.scale ? " · phys = raw×" + fmtNum(t0.scale, 4) : ""})</span>`);
  host.appendChild(lg);
  // tooltip
  const tip = document.createElement("div");
  tip.className = "tip hidden"; tip.style.cssText = "position:absolute;pointer-events:none;background:#1c2129;border:1px solid #3d444d;padding:4px 8px;border-radius:5px;font:12px monospace;z-index:10;";
  host.style.position = "relative";
  host.appendChild(tip);
  cv.addEventListener("mousemove", (ev) => {
    const r = cv.getBoundingClientRect();
    const sx = (ev.clientX - r.left) / r.width * W, sy = (ev.clientY - r.top) / r.height * H;
    const i = Math.floor((sx - m.l) / cell), j = Math.floor((sy - m.t) / cell);
    if (i >= 0 && i < cx && j >= 0 && j < cy) {
      const v = grid[j * cx + i];
      const ax = t0.ax[i], ay = t0.ay ? t0.ay[j] : null;
      tip.textContent = `${fmtNum(v, 4)}${ay !== null ? " @ X=" + fmtNum(ax, 2) + " Y=" + fmtNum(ay, 2) : " @ " + fmtNum(ax, 2)}`;
      tip.style.left = Math.min(ev.clientX - r.left + 14, r.width - 180) + "px";
      tip.style.top = (ev.clientY - r.top + 12) + "px";
      tip.classList.remove("hidden");
    } else tip.classList.add("hidden");
  });
  cv.addEventListener("mouseleave", () => tip.classList.add("hidden"));
}
function draw1D(host, t0) {
  const vals = t0.vals, ax = t0.ax;
  const W = Math.max(420, ax.length * 34), H = 220;
  const m = { t: 26, l: 58, b: 34, r: 16 };
  const cv = document.createElement("canvas");
  cv.width = W; cv.height = H;
  host.appendChild(cv);
  const g = cv.getContext("2d");
  g.fillStyle = "#0d1117"; g.fillRect(0, 0, W, H);
  let min = Math.min(...vals.filter((v) => v !== null)), max = Math.max(...vals.filter((v) => v !== null));
  if (min === max) { min -= 1; max += 1; }
  const iw = (W - m.l - m.r) / ax.length;
  vals.forEach((v, i) => {
    if (v === null) return;
    const x = m.l + i * iw, h = (v - min) / (max - min) * (H - m.t - m.b);
    g.fillStyle = heatColor((v - min) / (max - min));
    g.fillRect(x + 1, H - m.b - h, iw - 2, h);
  });
  g.strokeStyle = "#30363d";
  g.beginPath(); g.moveTo(m.l, H - m.b); g.lineTo(W - m.r, H - m.b); g.stroke();
  g.fillStyle = "#8b949e"; g.font = "11px monospace"; g.textAlign = "right"; g.textBaseline = "middle";
  g.fillText(fmtNum(max, 3), m.l - 6, m.t + 2);
  g.fillText(fmtNum(min, 3), m.l - 6, H - m.b - 2);
  g.textAlign = "center"; g.textBaseline = "top";
  const step = Math.max(1, Math.ceil(ax.length / 14));
  for (let i = 0; i < ax.length; i += step)
    g.fillText(fmtNum(ax[i], 2), m.l + i * iw + iw / 2, H - m.b + 8);
  const lg = document.createElement("div");
  lg.className = "heat-legend";
  lg.innerHTML = `<span>min ${fmtNum(min, 3)}</span><span class="muted">·</span><span>max ${fmtNum(max, 3)}</span><span class="muted">(${t0.type}${t0.scale ? " · phys = raw×" + fmtNum(t0.scale, 4) : ""})</span>`;
  host.appendChild(lg);
}
function drawAxis(host, ax, name) {
  const W = Math.max(420, ax.length * 30), H = 120;
  const cv = document.createElement("canvas");
  cv.width = W; cv.height = H;
  host.appendChild(cv);
  const g = cv.getContext("2d");
  g.fillStyle = "#0d1117"; g.fillRect(0, 0, W, H);
  let min = ax[0], max = ax[ax.length - 1];
  const m = { t: 18, l: 58, b: 28, r: 16 };
  const iw = (W - m.l - m.r) / ax.length;
  g.strokeStyle = "#7ee787"; g.lineWidth = 1.5;
  g.beginPath();
  ax.forEach((v, i) => {
    const x = m.l + i * iw + iw / 2;
    const y = m.t + (H - m.t - m.b) * (1 - (v - min) / (max - min));
    if (i === 0) g.moveTo(x, y); else g.lineTo(x, y);
  });
  g.stroke();
  g.fillStyle = "#8b949e"; g.font = "10.5px monospace"; g.textAlign = "center";
  ax.forEach((v, i) => {
    if (i % Math.max(1, Math.ceil(ax.length / 12)) === 0)
      g.fillText(fmtNum(v, 2), m.l + i * iw + iw / 2, H - m.b + 8);
  });
  host.insertAdjacentHTML("beforeend",
    `<div class="heat-legend"><span>f32 axis · ${fmtNum(ax.length)} points · ${fmtNum(min, 3)} → ${fmtNum(max, 3)}</span></div>`);
}

/* ============================ LOOKUP ============================ */
function wireLookup() {
  const run = () => {
    const a = parseHex($("lk-input").value);
    const out = $("lk-result");
    if (a === null || a < 0 || a > 0x7FFFF) {
      out.innerHTML = `<div class="card"><p class="muted">Enter a valid hex address (e.g. <code>0x6cf6c</code>, <code>9fc</code>, <code>0x2000</code>).</p></div>`;
      return;
    }
    let html = `<div class="card"><h3>Results for ${hex(a)}</h3>`;
    const m = modelByKey(CUR_MODEL);
    if (m) html += `<p class="muted">Current firmware model: <b>${esc(m.cal_id)}</b> (${esc(m.family)}); symbols below stay in their native context.</p>`;
    // containing function
    const fs = findContainingSymbol(a);
    if (fs) {
      const i = symIdx.get(fs.a);
      html += `<p><span class="match-good">Function:</span> <b class="name">${esc(fs.n)}</b> ${hex(fs.a)} – ${hex(fs.e)} · ${esc(fs.c)} ·
        <button data-cg="${i}" class="linkish">open callgraph</button></p>`;
    } else {
      html += `<p class="muted">No function contains ${hex(a)} (outside known ranges).</p>`;
    }
    // tables: exact match on the baseline address, or (for non-baseline
    // models) on the address mapped in the current model
    let exact = DATA.tables.filter((t) => t.a === a);
    let matchedViaModel = false;
    if (!exact.length && CUR_MODEL !== DATA.defaultModel) {
      const rid = modelReverse().get(a);
      if (rid !== undefined) {
        exact = [DATA.tables[rid]];
        matchedViaModel = true;
      }
    }
    const tableLine = (t) => {
      const rid = DATA.tables.indexOf(t);
      const mm = modelMap(rid);
      const mctx = mm
        ? ` · model ${modelLabel(CUR_MODEL)}: <span class="addr">${hex(mm.a)}</span> ${methodBadge(mm.m)} ${confBadge(mm.c)}`
        : ` · not mapped in ${modelLabel(CUR_MODEL)}`;
      return `<p><span class="match-good">Exact table:</span> <b class="name">${esc(t.n)}</b> baseline ${hex(t.a)}${matchedViaModel ? " (this address is the one mapped in the current model)" : ""} · role ${t.role} · ${esc(t.c)}${mctx}</p>`;
    };
    if (exact.length) {
      exact.forEach(tableLine);
    } else {
      // nearest
      const near = DATA.tables.slice()
        .map((t) => ({ t, d: Math.abs(t.a - a) }))
        .sort((x, y) => x.d - y.d).slice(0, 5);
      html += `<p class="muted">No table entry at this exact address. Nearest entries:</p><table class="data-table"><thead><tr><th>Distance</th><th>Baseline addr</th><th>Model addr (${esc(m ? m.cal_id : CUR_MODEL)})</th><th>Name</th><th>Role</th><th>Map</th></tr></thead><tbody>` +
        near.map(({ t, d }) => {
          const mm = modelMap(DATA.tables.indexOf(t));
          return `<tr><td class="addr">${hex(t.a)} (Δ${d})</td><td class="addr">${hex(t.a)}</td>` +
            (mm ? `<td class="addr">${hex(mm.a)}</td>` : `<td class="muted">—</td>`) +
            `<td class="name">${esc(t.n)}</td><td>${t.role}</td><td>${mm ? confBadge(mm.c) : `<span class="tag unmapped">not mapped</span>`}</td></tr>`;
        }).join("") + `</tbody></table>`;
    }
    html += `</div>`;
    out.innerHTML = html;
    const btn = out.querySelector("[data-cg]");
    if (btn) btn.addEventListener("click", () => openCallgraph(parseInt(btn.dataset.cg, 10)));
  };
  $("lk-go").addEventListener("click", run);
  $("lk-input").addEventListener("keydown", (ev) => { if (ev.key === "Enter") run(); });
}

/* ============================ DEEP LINKS (anchors) ============================ */
/* Supported anchors: #sym-0xADDR, #tbl-0xADDR, #doc-<filename> */
function jumpToSymbol(addr) {
  const s = findExactSymbol(addr);
  if (!s) return false;
  const i = symIdx.get(addr);
  document.querySelector("#tabs button[data-tab=symbols]").click();
  $("sym-search").value = "0x" + hex6(addr);
  $("sym-cat").value = ""; $("sym-rom").value = ""; $("sym-doc").value = "";
  SymBrowser.apply();
  const tr = Array.from(document.querySelectorAll("#sym-tbody tr[data-i]")).find((x) => +x.dataset.i === i);
  if (tr) { tr.classList.add("sel"); tr.scrollIntoView({ block: "center" }); }
  SymBrowser.showDetail(i);
  return true;
}
function jumpToTable(addr) {
  const t = DATA.tables.find((x) => x.a === addr);
  if (!t) return false;
  document.querySelector("#tabs button[data-tab=tables]").click();
  $("tbl-search").value = "0x" + hex6(addr);
  $("tbl-cat").value = ""; $("tbl-type").value = ""; $("tbl-role").value = "";
  TblApply();
  const rid = DATA.tables.indexOf(t);
  const tr = Array.from(document.querySelectorAll("#tbl-tbody tr[data-rid]")).find((x) => +x.dataset.rid === rid);
  if (tr) { tr.classList.add("sel"); tr.scrollIntoView({ block: "center" }); }
  TblDetail(rid);
  return true;
}
function jumpToDoc(fname, secId) {
  document.querySelector("#tabs button[data-tab=docs]").click();
  $("doc-search").value = ""; $("doc-group").value = "";
  DocView.apply();
  const k = DocView.rows.findIndex((r) => r.f.toLowerCase() === fname.toLowerCase());
  if (k < 0) return false;
  DocView.select(k, !secId);
  if (secId) {
    const el = $("doc-detail").querySelector("#" + secId);
    if (el) {
      el.scrollIntoView({ block: "start" });
      try { history.pushState(null, "", "#doc-" + fname + "#" + secId); } catch (e) { /* file:// ok */ }
    }
  }
  return true;
}
function handleHash() {
  const h = location.hash || "";
  let m;
  if (/^#(dashboard|symbols|callgraph|tables|docs|lookup)$/.test(h)) { activateTab(h.slice(1)); return; }
  if ((m = /^#sym-0x([0-9a-fA-F]{1,8})$/.exec(h))) { jumpToSymbol(parseInt(m[1], 16)); return; }
  if ((m = /^#tbl-0x([0-9a-fA-F]{1,8})$/.exec(h))) { jumpToTable(parseInt(m[1], 16)); return; }
  if ((m = /^#doc-([\w.-]+)(?:#sec-(\d+))?$/.exec(h))) { jumpToDoc(m[1], m[2] ? "sec-" + m[2] : null); return; }
}

/* ============================ INIT ============================ */
async function init() {
  bootEl = $("boot");
  bootMsg = $("boot-msg");
  await loadData();
  buildIndex();
  populateModelSelect();
  wireTabs();
  renderDashboard();
  wireSymbols();
  wireCallgraph();
  wireTables();
  wireDocs();
  wireLookup();
  updateModelContext();
  updateSymCtxNote();
  updateTblModelNote();
  await loadModelValues(CUR_MODEL); // baseline: embedded, resolves immediately
  updateTblModelNote();
  window.addEventListener("popstate", handleHash);
  handleHash();
  bootEl.classList.add("hidden");
}

init().catch((e) => {
  console.error(e);
  $("boot-msg").textContent = "";
  $("boot-err").classList.remove("hidden");
});
