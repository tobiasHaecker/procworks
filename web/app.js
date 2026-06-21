// SPDX-License-Identifier: BUSL-1.1
"use strict";

/* ProcWorks - schlanker Web-Client (Roadmap-Schritt 13, Abschnitt 8).
 *
 * Die GUI ist ein reiner Client der headless FastAPI: sie sammelt Intentionen
 * und rendert Zustand. Jede Korrektheitsentscheidung (K/D/Z/A/C/H/F/R/M)
 * trifft ausschliesslich der Kern - hier liegt keine Validierungslogik.
 */

// --------------------------------------------------------------------------
// Konfiguration + Zustand
// --------------------------------------------------------------------------

const DEFAULT_API = "http://127.0.0.1:8000";

// Behind the reverse proxy (deploy/Caddyfile) the API is reachable same-origin
// under /api. When the page is served from a real host (not the local file://
// or the :5500 dev static server) default to that proxied path so the deployed
// app — including the Docker stack on http://localhost — works without manual
// configuration. The local dev flow serves the SPA from a static server on
// :5500 (uvicorn separately on :8000) and keeps the 127.0.0.1:8000 default.
function defaultApiBase() {
  try {
    const { protocol, port } = window.location;
    const isFile = protocol === "file:";
    const isDevStatic = port === "5500";
    if (!isFile && !isDevStatic) {
      return window.location.origin + "/api";
    }
  } catch (_e) {
    // window/location unavailable -> fall back to the dev default below.
  }
  return DEFAULT_API;
}

const state = {
  apiBase: localStorage.getItem("apiBase") || defaultApiBase(),
  token: localStorage.getItem("authToken") || "",
  principal: null,
  authMode: "open",
  passwordLogin: false,
  view: localStorage.getItem("view") || "model",
  schemaIds: [],
  schemaNames: {},
  // Version (revision) per schema id, captured alongside the name. Immutable
  // per id (a new revision gets a fresh id), so it is safe to cache.
  schemaVersions: {},
  schemaId: localStorage.getItem("schemaId") || null,
  schema: null,
  validation: null,
  instanceIds: [],
  instanceId: null,
  instance: null,
  worklist: null,
  selectedNode: null,
  // Last seen runtime-event revision (GET /monitoring/revision). Drives the
  // live auto-refresh of the task/monitoring/run views; not persisted.
  revision: 0,
};

const NODE_TYPE = {
  START: "START", END: "END", ACTIVITY: "ACTIVITY",
  AND_SPLIT: "AND_SPLIT", AND_JOIN: "AND_JOIN",
  XOR_SPLIT: "XOR_SPLIT", XOR_JOIN: "XOR_JOIN", SUBPROCESS: "SUBPROCESS",
};
const GATEWAYS = new Set([
  NODE_TYPE.AND_SPLIT, NODE_TYPE.AND_JOIN, NODE_TYPE.XOR_SPLIT, NODE_TYPE.XOR_JOIN,
]);
const DATA_TYPES = ["INTEGER", "FLOAT", "STRING", "DATE", "BOOLEAN", "URI"];
const CONNECTOR_KINDS = ["MS_SQL", "MYSQL", "DYNAMICS_365", "SAP", "CUSTOM"];

// --------------------------------------------------------------------------
// DOM-Helfer
// --------------------------------------------------------------------------

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "html") node.innerHTML = v;
      else if (k.startsWith("on") && typeof v === "function") {
        node.addEventListener(k.slice(2).toLowerCase(), v);
      } else node.setAttribute(k, v);
    }
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    node.appendChild(typeof c === "string" || typeof c === "number"
      ? document.createTextNode(String(c)) : c);
  }
  return node;
}

const SVGNS = "http://www.w3.org/2000/svg";
function svg(tag, attrs, ...children) {
  const node = document.createElementNS(SVGNS, tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k.startsWith("on") && typeof v === "function") {
        node.addEventListener(k.slice(2).toLowerCase(), v);
      } else node.setAttribute(k, v);
    }
  }
  for (const c of children.flat()) {
    if (c == null) continue;
    node.appendChild(c);
  }
  return node;
}

function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
function byId(id) { return document.getElementById(id); }

// --------------------------------------------------------------------------
// Toast + Fehlerbehandlung
// --------------------------------------------------------------------------

function toast(kind, title, lines) {
  const root = byId("toast-root");
  const list = (lines && lines.length)
    ? el("ul", { class: "t-list" }, ...lines.map((l) => el("li", null, l)))
    : null;
  const t = el("div", { class: "toast " + kind },
    el("div", { class: "t-title" }, title), list);
  root.appendChild(t);
  setTimeout(() => t.remove(), kind === "err" ? 7000 : 3500);
}

function describeError(err) {
  // err.detail can be: string, {message}, {findings:[{rule,message,node_id}]}
  const d = err && err.detail;
  if (!d) return { title: err.message || "Fehler", lines: [] };
  if (typeof d === "string") return { title: d, lines: [] };
  if (d.findings) {
    return {
      title: "Vom Kern abgelehnt (Regelverletzung)",
      lines: d.findings.map((f) => `${f.rule}: ${f.message}` + (f.node_id ? ` [${f.node_id}]` : "")),
    };
  }
  if (d.message) return { title: d.message, lines: [] };
  return { title: "Fehler", lines: [] };
}

// --------------------------------------------------------------------------
// Web-Client
// --------------------------------------------------------------------------

async function request(method, path, body) {
  let resp;
  try {
    resp = await fetch(state.apiBase + path, {
      method,
      headers: authHeaders(body !== undefined),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    setConnected(false);
    throw { detail: `Keine Verbindung zur API (${state.apiBase}). Laeuft uvicorn?` };
  }
  setConnected(true);
  const text = await resp.text();
  const data = text ? JSON.parse(text) : null;
  if (!resp.ok) throw { status: resp.status, detail: data && data.detail };
  return data;
}

// Build request headers, attaching the bearer token when the user is logged in.
function authHeaders(hasBody) {
  const headers = {};
  if (hasBody) headers["Content-Type"] = "application/json";
  if (state.token) headers["Authorization"] = "Bearer " + state.token;
  return headers;
}

const api = {
  get: (p) => request("GET", p),
  post: (p, b) => request("POST", p, b === undefined ? {} : b),
  patch: (p, b) => request("PATCH", p, b === undefined ? {} : b),
  del: (p) => request("DELETE", p),
  raw: async (p) => {
    const resp = await fetch(state.apiBase + p, { headers: authHeaders(false) });
    if (!resp.ok) throw { status: resp.status, detail: "Export fehlgeschlagen" };
    return resp.text();
  },
};

function setConnected(ok) {
  const pill = byId("conn-pill");
  pill.textContent = ok ? "verbunden" : "getrennt";
  pill.className = "pill " + (ok ? "pill-green" : "pill-gray");
}

// --------------------------------------------------------------------------
// Modal
// --------------------------------------------------------------------------

function openModal(title, bodyNode, onConfirm, confirmLabel) {
  const root = byId("modal-root");
  clear(root);
  const close = () => clear(root);
  const confirmBtn = el("button", {
    class: "btn primary",
    onClick: async () => {
      const ok = await onConfirm();
      if (ok !== false) close();
    },
  }, confirmLabel || "Anwenden");
  const modal = el("div", { class: "modal-backdrop", onClick: (e) => { if (e.target === e.currentTarget) close(); } },
    el("div", { class: "modal" },
      el("div", { class: "modal-h" }, el("h3", null, title)),
      el("div", { class: "modal-b" }, bodyNode),
      el("div", { class: "modal-f" },
        el("button", { class: "btn ghost", onClick: close }, "Abbrechen"),
        confirmBtn)));
  root.appendChild(modal);
  const firstInput = modal.querySelector("input, select, textarea");
  if (firstInput) firstInput.focus();
}

// --------------------------------------------------------------------------
// Graph-Layout (Longest-Path-Layering, blockstrukturierter DAG)
// --------------------------------------------------------------------------

function layoutSchema(schema) {
  const ids = Object.keys(schema.nodes);
  const inc = {}, out = {};
  ids.forEach((id) => { inc[id] = []; out[id] = []; });
  (schema.edges || []).forEach((e) => {
    if (out[e.source]) out[e.source].push(e);
    if (inc[e.target]) inc[e.target].push(e);
  });
  const depth = {}, visiting = {};
  function d(id) {
    if (depth[id] !== undefined) return depth[id];
    if (visiting[id]) return 0;
    visiting[id] = true;
    let m = 0;
    inc[id].forEach((e) => { m = Math.max(m, d(e.source) + 1); });
    visiting[id] = false;
    return (depth[id] = m);
  }
  ids.forEach(d);
  const cols = {};
  ids.forEach((id) => { (cols[depth[id]] = cols[depth[id]] || []).push(id); });
  const colKeys = Object.keys(cols).map(Number).sort((a, b) => a - b);
  const NW = 144, NH = 56, HGAP = 74, VGAP = 26, PAD = 32;
  const maxRows = Math.max(1, ...colKeys.map((c) => cols[c].length));
  const height = PAD * 2 + maxRows * NH + (maxRows - 1) * VGAP;
  const pos = {};
  colKeys.forEach((c, ci) => {
    const list = cols[c];
    const colHeight = list.length * NH + (list.length - 1) * VGAP;
    const top = PAD + (height - PAD * 2 - colHeight) / 2;
    list.forEach((id, ri) => {
      pos[id] = { x: PAD + ci * (NW + HGAP), y: top + ri * (NH + VGAP), w: NW, h: NH };
    });
  });
  const width = PAD * 2 + colKeys.length * NW + (colKeys.length - 1) * HGAP;
  return { pos, edges: schema.edges || [], width: Math.max(width, 560), height: Math.max(height, 160) };
}

function nodeClass(node, instance) {
  if (instance && instance.node_states && instance.node_states[node.id]) {
    return "gnode s-" + instance.node_states[node.id];
  }
  if (node.type === NODE_TYPE.START || node.type === NODE_TYPE.END) return "gnode nstart";
  if (node.type === NODE_TYPE.SUBPROCESS) return "gnode nsub";
  if (GATEWAYS.has(node.type)) return "gnode ngateway";
  return "gnode ndefault";
}

function nodeCaption(node) {
  if (node.label) return node.label;
  return { START: "Start", END: "Ende", AND_SPLIT: "UND \u25B6", AND_JOIN: "\u25B6 UND",
    XOR_SPLIT: "XOR \u25B6", XOR_JOIN: "\u25B6 XOR", SUBPROCESS: "Teilprozess" }[node.type] || node.type;
}

function renderGraph(schema, opts) {
  opts = opts || {};
  const L = layoutSchema(schema);
  const root = svg("svg", { class: "graph", width: L.width, height: L.height, viewBox: `0 0 ${L.width} ${L.height}` });
  const defs = svg("defs", null,
    svg("marker", { id: "arrow", viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "7", markerHeight: "7", orient: "auto-start-reverse" },
      svg("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#6b7794" })));
  root.appendChild(defs);

  // Kanten
  L.edges.forEach((e) => {
    const a = L.pos[e.source], b = L.pos[e.target];
    if (!a || !b) return;
    const x1 = a.x + a.w, y1 = a.y + a.h / 2, x2 = b.x, y2 = b.y + b.h / 2;
    const mx = (x1 + x2) / 2;
    let cls = "gedge";
    if (opts.instance && opts.instance.edge_states) {
      const st = opts.instance.edge_states[`${e.source}->${e.target}`];
      if (st === "TRUE_SIGNALED") cls += " gedge-true";
      else if (st === "FALSE_SIGNALED") cls += " gedge-false";
    }
    root.appendChild(svg("path", { class: cls, "marker-end": "url(#arrow)",
      d: `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}` }));
    if (e.condition) {
      root.appendChild(svg("text", { class: "gcond", x: mx, y: (y1 + y2) / 2 - 6, "text-anchor": "middle" }, document.createTextNode(e.condition)));
    }
    if (opts.onPlus) {
      const g = svg("g", { class: "gplus-wrap", style: "cursor:pointer", onClick: () => opts.onPlus(e.source) });
      g.appendChild(svg("circle", { class: "gplus", cx: mx, cy: (y1 + y2) / 2 + 10, r: 10 }));
      g.appendChild(svg("text", { class: "gplus-txt", x: mx, y: (y1 + y2) / 2 + 14, "text-anchor": "middle" }, document.createTextNode("+")));
      root.appendChild(g);
    }
  });

  // Knoten
  Object.entries(L.pos).forEach(([id, p]) => {
    const node = schema.nodes[id];
    let cls = nodeClass(node, opts.instance);
    if (opts.selectedId === id) cls += " selected";
    const g = svg("g", { class: cls, style: opts.onSelectNode ? "cursor:pointer" : "",
      onClick: opts.onSelectNode ? () => opts.onSelectNode(id) : null });
    g.appendChild(svg("rect", { x: p.x, y: p.y, width: p.w, height: p.h, rx: 10 }));
    g.appendChild(svg("text", { class: "glabel", x: p.x + p.w / 2, y: p.y + p.h / 2 - 2, "text-anchor": "middle" },
      document.createTextNode(truncate(nodeCaption(node), 18))));
    const sub = opts.instance && opts.instance.node_states ? (opts.instance.node_states[id] || "") : node.type;
    g.appendChild(svg("text", { class: "gstate", x: p.x + p.w / 2, y: p.y + p.h / 2 + 14, "text-anchor": "middle" },
      document.createTextNode(sub)));
    root.appendChild(g);
  });

  return el("div", { class: "canvas-wrap" }, root);
}

function truncate(s, n) { return s.length > n ? s.slice(0, n - 1) + "\u2026" : s; }

// --------------------------------------------------------------------------
// Laden / Auswahl
// --------------------------------------------------------------------------

async function loadSchemas() {
  state.schemaIds = await api.get("/schemas");
  // The list endpoint returns only IDs; fetch each name + version once so the
  // picker can show the human-readable schema name plus its revision (e.g.
  // "Urlaubsantrag (v2)") instead of the raw ID. Revisions share the same name
  // but carry a fresh ID and an incremented version, so the version makes them
  // distinguishable in the selection.
  const unknown = state.schemaIds.filter((id) => !(id in state.schemaNames));
  if (unknown.length) {
    const entries = await Promise.all(unknown.map(async (id) => {
      try { const s = await api.get(`/schemas/${id}`); return [id, s.name, s.version]; }
      catch (_e) { return [id, id, null]; }
    }));
    for (const [id, name, version] of entries) {
      state.schemaNames[id] = name;
      if (version != null) state.schemaVersions[id] = version;
    }
  }
  if (state.schemaIds.length && !state.schemaIds.includes(state.schemaId)) {
    state.schemaId = state.schemaIds[0];
  }
  if (!state.schemaIds.length) state.schemaId = null;
}

async function refreshSchema() {
  if (!state.schemaId) { state.schema = null; state.validation = null; return; }
  state.schema = await api.get(`/schemas/${state.schemaId}`);
  state.validation = await api.get(`/schemas/${state.schemaId}/validation`);
  localStorage.setItem("schemaId", state.schemaId);
}

async function selectSchema(id) {
  state.schemaId = id;
  state.selectedNode = null;
  await refreshSchema();
  render();
}

function activitiesOf(schema) {
  return Object.values(schema.nodes).filter((n) => n.type === NODE_TYPE.ACTIVITY);
}
function isDraft(schema) { return schema && schema.lifecycle_state === "ENTWURF"; }

function lifecyclePill(schema) {
  const s = schema.lifecycle_state;
  const cls = s === "RELEASED" ? "pill-green" : s === "ENTWURF" ? "pill-amber" : "pill-gray";
  return el("span", { class: "pill " + cls }, s);
}

// --------------------------------------------------------------------------
// Topbar / Schema-Picker
// --------------------------------------------------------------------------

// Human-readable schema caption including its revision, e.g. "Urlaubsantrag
// (v2)". Revisions share the same name but get a fresh id and an incremented
// version, so the version is what makes them distinguishable. ``version`` may
// be passed explicitly (e.g. an instance's own schema_version, which is robust
// even when the schema is no longer in the picker); otherwise it falls back to
// the cached version for that id. The id is used as a last resort.
function schemaLabel(id, version) {
  const name = state.schemaNames[id] || id;
  const v = version != null ? version : state.schemaVersions[id];
  return v != null ? `${name} (v${v})` : name;
}

function renderSchemaPicker() {
  const picker = byId("schema-picker");
  clear(picker);
  const select = el("select", { onChange: (e) => selectSchema(e.target.value) },
    ...state.schemaIds.map((id) => {
      const o = el("option", { value: id }, schemaLabel(id));
      if (id === state.schemaId) o.selected = true;
      return o;
    }));
  if (!state.schemaIds.length) {
    select.appendChild(el("option", null, "(kein Schema)"));
    select.disabled = true;
  }
  picker.appendChild(select);
  picker.appendChild(el("button", { class: "btn small", onClick: newSchema }, "+ Neu"));
  picker.appendChild(el("button", { class: "btn small ghost", onClick: importBpmn }, "BPMN-Import"));
}

async function newSchema() {
  const nameInput = el("input", { type: "text", placeholder: "z. B. Urlaubsantrag" });
  openModal("Neues Schema", el("label", { class: "field" }, "Name", nameInput), async () => {
    const name = nameInput.value.trim();
    if (!name) return false;
    try {
      const schema = await api.post("/schemas", { name });
      await loadSchemas();
      await selectSchema(schema.id);
      toast("ok", "Schema angelegt", [schema.name]);
    } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Anlegen");
}

async function importBpmn() {
  const ta = el("textarea", { placeholder: "<bpmn:definitions ...>" });
  const nameInput = el("input", { type: "text", placeholder: "optionaler Name" });
  openModal("BPMN 2.0 importieren", el("div", { class: "row", style: "flex-direction:column;align-items:stretch" },
    el("label", { class: "field" }, "Name (optional)", nameInput),
    el("label", { class: "field" }, "BPMN-XML", ta)), async () => {
    const xml = ta.value.trim();
    if (!xml) return false;
    try {
      const schema = await api.post("/bpmn-import", { xml, name: nameInput.value.trim() || null });
      await loadSchemas();
      await selectSchema(schema.id);
      toast("ok", "BPMN importiert", [schema.name]);
    } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Importieren");
}

// --------------------------------------------------------------------------
// View: Modellieren
// --------------------------------------------------------------------------

function viewModel() {
  const content = byId("content");
  clear(content);
  if (!state.schema) {
    content.appendChild(emptyState("Kein Schema ausgewaehlt. Lege oben rechts ein neues Schema an."));
    return;
  }
  const schema = state.schema;
  const draft = isDraft(schema);

  const header = el("div", { class: "panel" },
    el("div", { class: "panel-h" },
      el("h2", null, schema.name),
      el("span", { class: "sub" }, `v${schema.version}`),
      lifecyclePill(schema),
      validationBadge(),
      el("span", { class: "spacer", style: "flex:1" }),
      el("button", { class: "btn small ghost", onClick: exportBpmn }, "BPMN-Export"),
      draft
        ? el("button", { class: "btn small green", onClick: releaseSchema }, "Freigeben")
        : el("button", { class: "btn small primary", onClick: () => { state.view = "run"; setActiveNav(); render(); } }, "Zur Ausf\u00FChrung")));

  const graph = renderGraph(schema, {
    onPlus: draft ? openInsertModal : null,
    selectedId: state.selectedNode,
    onSelectNode: (id) => { state.selectedNode = id; render(); },
  });

  const hint = el("div", { class: "panel-b muted", style: "font-size:12px" },
    draft
      ? "Gef\u00FChrtes Modellieren: Klicke ein \u201E+\u201C an einer Kante, um nach diesem Schritt seriell, parallel (UND) oder bedingt (XOR) einzuf\u00FCgen. Unzul\u00E4ssiges weist der Kern ab."
      : "Schema ist freigegeben und damit unver\u00E4nderlich. Erzeuge eine Revision \u00FCber die Ausf\u00FChrungs-/Monitoring-Sicht oder starte Instanzen.");

  content.appendChild(header);
  content.appendChild(el("div", { class: "grid-2" },
    el("div", { class: "panel" }, el("div", { class: "panel-h" }, el("h2", null, "Kontrollfluss")), el("div", { class: "panel-b" }, graph), hint),
    el("div", null, nodeInspectorPanel(), findingsPanel(), revisionPanel())));

  // Nach dem (Neu-)Rendern den ausgewaehlten Knoten in die Mitte der scrollbaren
  // Canvas ruecken, statt nach links auf den Start zurueckzuspringen.
  if (state.selectedNode) {
    const pos = layoutSchema(schema).pos[state.selectedNode];
    if (pos) requestAnimationFrame(() => centerCanvasOnNode(graph, pos));
  }
}

function centerCanvasOnNode(wrap, pos) {
  // ``wrap`` ist die scrollbare .canvas-wrap; die Layout-Koordinaten bilden im
  // Ueberlauf-Fall 1:1 auf Pixel ab (SVG-Breite == Layout-Breite).
  const cx = pos.x + pos.w / 2;
  const cy = pos.y + pos.h / 2;
  wrap.scrollLeft = Math.max(0, cx - wrap.clientWidth / 2);
  wrap.scrollTop = Math.max(0, cy - wrap.clientHeight / 2);
}

// --------------------------------------------------------------------------
// Knoten-Inspektor (Aktivitaet umbenennen / Element entfernen)
// --------------------------------------------------------------------------

const SPLIT_TYPES = new Set([NODE_TYPE.AND_SPLIT, NODE_TYPE.XOR_SPLIT]);

function nodeInspectorPanel() {
  const schema = state.schema;
  const draft = isDraft(schema);
  const body = el("div", { class: "panel-b" });
  const node = state.selectedNode ? schema.nodes[state.selectedNode] : null;

  if (!node) {
    body.appendChild(el("div", { class: "muted", style: "font-size:12px" },
      draft
        ? "Klicke einen Knoten an, um ihn umzubenennen oder zu entfernen."
        : "Klicke einen Knoten an, um zu ihm zu scrollen. Bearbeiten ist nur im Entwurf m\u00F6glich."));
    return el("div", { class: "panel" },
      el("div", { class: "panel-h" }, el("h2", null, "Knoten")), body);
  }

  body.appendChild(el("div", { class: "row", style: "gap:8px;align-items:center;margin-bottom:10px" },
    el("span", { class: "pill pill-gray" }, node.type),
    el("strong", null, nodeCaption(node))));

  const renamable = node.type === NODE_TYPE.ACTIVITY || node.type === NODE_TYPE.SUBPROCESS;
  if (!draft) {
    body.appendChild(el("div", { class: "muted", style: "font-size:12px" },
      "Schema ist freigegeben \u2013 Bearbeiten erst in einer neuen Revision m\u00F6glich."));
  } else if (renamable) {
    const input = el("input", { type: "text", value: node.label || "" });
    body.appendChild(el("label", { class: "field" }, "Bezeichnung", input));
    body.appendChild(el("div", { class: "row", style: "gap:8px" },
      el("button", { class: "btn small primary", onClick: () => renameNode(node.id, input.value) }, "Umbenennen"),
      el("button", { class: "btn small danger", onClick: () => deleteNode(node.id) }, "Entfernen")));
  } else if (SPLIT_TYPES.has(node.type)) {
    body.appendChild(el("div", { class: "muted", style: "font-size:12px;margin-bottom:8px" },
      "Verzweigung: Entfernen l\u00F6scht den gesamten Block (Split, Zweige und passenden Join)."));
    body.appendChild(el("button", { class: "btn small danger", onClick: () => deleteNode(node.id) }, "Verzweigung entfernen"));
  } else {
    body.appendChild(el("div", { class: "muted", style: "font-size:12px" },
      node.type === NODE_TYPE.AND_JOIN || node.type === NODE_TYPE.XOR_JOIN
        ? "Join-Knoten werden \u00FCber ihren \u00F6ffnenden Split entfernt."
        : "Start und Ende sind fester Bestandteil des Modells."));
  }
  return el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Knoten"),
      el("span", { class: "spacer", style: "flex:1" }),
      el("button", { class: "btn small ghost", onClick: () => { state.selectedNode = null; render(); } }, "Abw\u00E4hlen")),
    body);
}

async function renameNode(nodeId, label) {
  const name = (label || "").trim();
  if (!name) { toast("err", "Bezeichnung darf nicht leer sein"); return; }
  try {
    await api.patch(`/schemas/${state.schemaId}/nodes/${nodeId}`, { label: name });
    await refreshSchema();
    render();
    toast("ok", "Aktivit\u00E4t umbenannt", [name]);
  } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); }
}

function deleteNode(nodeId) {
  const node = state.schema.nodes[nodeId];
  const isSplit = SPLIT_TYPES.has(node.type);
  const msg = isSplit
    ? "Den gesamten Verzweigungsblock (Split, alle Zweige und den passenden Join) entfernen?"
    : `\u201E${nodeCaption(node)}\u201C aus dem Modell entfernen?`;
  openModal("Element entfernen", el("div", { class: "muted", style: "font-size:13px" }, msg), async () => {
    try {
      await api.del(`/schemas/${state.schemaId}/nodes/${nodeId}`);
      state.selectedNode = null;
      await refreshSchema();
      render();
      toast("ok", "Element entfernt");
    } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Entfernen");
}

function validationBadge() {
  if (!state.validation) return el("span", null, "");
  if (state.validation.correct) return el("span", { class: "pill pill-green" }, "korrekt");
  return el("span", { class: "pill pill-red" }, `${state.validation.findings.length} Befund(e)`);
}

function findingsPanel() {
  const v = state.validation;
  const body = el("div", { class: "panel-b" });
  if (!v || v.correct) {
    body.appendChild(el("div", { class: "ok-banner" }, "\u2713 Strukturell korrekt (K/D/Z/A/C/H/F erf\u00FCllt)."));
  } else {
    v.findings.forEach((f) => body.appendChild(el("div", { class: "finding" },
      el("span", { class: "rule" }, f.rule),
      el("span", null, f.message + (f.node_id ? ` [${f.node_id}]` : "")))));
  }
  return el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Korrektheit"), el("span", { class: "sub" }, "live vom Kern")), body);
}

function revisionPanel() {
  const schema = state.schema;
  if (isDraft(schema)) return el("div");
  return el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Schema-Evolution")),
    el("div", { class: "panel-b row" },
      el("span", { class: "muted", style: "font-size:12px;flex:1" }, "Eine neue Revision erzeugt ein bearbeitbares ENTWURF-Duplikat (IDs bleiben erhalten)."),
      el("button", { class: "btn small", onClick: newRevision }, "Neue Revision")));
}

function openInsertModal(afterNodeId) {
  const node = state.schema.nodes[afterNodeId];
  let active = "serial";
  const serialBody = el("label", { class: "field" }, "Bezeichnung",
    el("input", { type: "text", id: "ins-label", placeholder: "z. B. Antrag pr\u00FCfen" }));
  const parBox = el("div", { class: "row", style: "flex-direction:column;align-items:stretch;gap:8px" });
  const condBox = el("div", { class: "row", style: "flex-direction:column;align-items:stretch;gap:8px" });
  function addParRow(val) {
    parBox.appendChild(el("input", { type: "text", class: "par-branch", placeholder: "Zweig-Bezeichnung", value: val || "" }));
  }
  function addCondRow() {
    condBox.appendChild(el("div", { class: "branch-row" },
      el("input", { type: "text", class: "cond-cond", placeholder: "Bedingung, z. B. betrag > 1000" }),
      el("input", { type: "text", class: "cond-label", placeholder: "Bezeichnung" })));
  }
  addParRow(); addParRow(); addCondRow(); addCondRow();
  const panels = {
    serial: serialBody,
    parallel: el("div", null, parBox, el("button", { class: "btn small ghost", onClick: () => addParRow() }, "+ Zweig")),
    conditional: el("div", null, condBox, el("button", { class: "btn small ghost", onClick: () => addCondRow() }, "+ Zweig")),
  };
  const slot = el("div", null, panels.serial);
  const tabs = el("div", { class: "tabs" },
    tabBtn("Seriell", "serial", true), tabBtn("Parallel (UND)", "parallel"), tabBtn("Bedingt (XOR)", "conditional"));
  function tabBtn(label, key, isActive) {
    return el("button", { class: isActive ? "active" : "", onClick: (e) => {
      active = key;
      [...tabs.children].forEach((c) => c.classList.remove("active"));
      e.target.classList.add("active");
      clear(slot); slot.appendChild(panels[key]);
    } }, label);
  }
  const body = el("div", null,
    el("div", { class: "muted", style: "font-size:12px;margin-bottom:8px" }, `Einf\u00FCgen nach: ${nodeCaption(node)}`),
    tabs, slot);

  openModal("Schritt einf\u00FCgen", body, async () => {
    try {
      if (active === "serial") {
        const label = byId("ins-label").value.trim();
        if (!label) return false;
        await api.post(`/schemas/${state.schemaId}/serial-insert`, { label, after_node_id: afterNodeId });
      } else if (active === "parallel") {
        const labels = [...parBox.querySelectorAll(".par-branch")].map((i) => i.value.trim()).filter(Boolean);
        if (labels.length < 2) { toast("err", "Mindestens zwei Zweige n\u00F6tig"); return false; }
        await api.post(`/schemas/${state.schemaId}/parallel-insert`, { branch_labels: labels, after_node_id: afterNodeId });
      } else {
        const rows = [...condBox.querySelectorAll(".branch-row")].map((r) => ({
          condition: r.querySelector(".cond-cond").value.trim(),
          label: r.querySelector(".cond-label").value.trim(),
        })).filter((b) => b.condition && b.label);
        if (rows.length < 2) { toast("err", "Mindestens zwei Zweige mit Bedingung n\u00F6tig"); return false; }
        await api.post(`/schemas/${state.schemaId}/conditional-insert`, { branches: rows, after_node_id: afterNodeId });
      }
      await refreshSchema();
      render();
      toast("ok", "Schritt eingef\u00FCgt");
    } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Einf\u00FCgen");
}

async function releaseSchema() {
  try {
    await api.post(`/schemas/${state.schemaId}/release`);
    await refreshSchema();
    render();
    toast("ok", "Schema freigegeben", ["Jetzt instanziierbar."]);
  } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); }
}

async function newRevision() {
  try {
    const rev = await api.post(`/schemas/${state.schemaId}/revision`, {});
    await loadSchemas();
    await selectSchema(rev.id);
    toast("ok", "Revision erstellt", [`${rev.id} (v${rev.version})`]);
  } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); }
}

async function exportBpmn() {
  try {
    const xml = await api.raw(`/schemas/${state.schemaId}/bpmn`);
    const blob = new Blob([xml], { type: "application/xml" });
    const a = el("a", { href: URL.createObjectURL(blob), download: `${state.schema.name}.bpmn` });
    document.body.appendChild(a); a.click(); a.remove();
  } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); }
}

// --------------------------------------------------------------------------
// View: Datensicht
// --------------------------------------------------------------------------

function viewData() {
  const content = byId("content");
  clear(content);
  if (!state.schema) { content.appendChild(emptyState("Kein Schema ausgewaehlt.")); return; }
  const schema = state.schema;
  const draft = isDraft(schema);

  // Datenelemente
  const elemRows = Object.values(schema.data_elements);
  const elemTable = elemRows.length
    ? table(["Name", "Typ", "Quelle"], elemRows.map((d) => [d.name, d.data_type, d.source]))
    : emptyState("Noch keine Datenelemente.");

  const addElemBtn = el("button", { class: "btn small", onClick: addDataElement, disabled: !draft }, "+ Datenelement");
  const elemPanel = el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Datenelemente"), el("span", { class: "spacer", style: "flex:1" }), addElemBtn),
    el("div", { class: "panel-b" }, elemTable));

  // Datenzugriffe
  const accRows = (schema.data_accesses || []).map((a) => {
    const node = schema.nodes[a.node_id];
    const elem = schema.data_elements[a.element_id];
    return [node ? nodeCaption(node) : a.node_id, elem ? elem.name : a.element_id, a.mode, a.mandatory ? "Pflicht" : "optional"];
  });
  const accTable = accRows.length ? table(["Schritt", "Element", "Modus", "Bindung"], accRows) : emptyState("Noch keine Datenbindungen.");
  const addAccBtn = el("button", { class: "btn small", onClick: addDataAccess, disabled: !draft || activitiesOf(schema).length === 0 || elemRows.length === 0 }, "+ Datenbindung");
  const accPanel = el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Lese-/Schreibbindungen"), el("span", { class: "sub" }, "D1-D4 live gepr\u00FCft"), el("span", { class: "spacer", style: "flex:1" }), addAccBtn),
    el("div", { class: "panel-b" }, accTable));

  content.appendChild(el("div", { class: "grid-2" }, elemPanel, el("div", null, accPanel, dFindingsPanel())));
}

function dFindingsPanel() {
  const v = state.validation;
  const dz = v && !v.correct ? v.findings.filter((f) => f.rule[0] === "D" || f.rule[0] === "C") : [];
  const body = el("div", { class: "panel-b" });
  if (!dz.length) body.appendChild(el("div", { class: "ok-banner" }, "\u2713 Datenfluss konsistent (D/C)."));
  else dz.forEach((f) => body.appendChild(el("div", { class: "finding" }, el("span", { class: "rule" }, f.rule), el("span", null, f.message + (f.node_id ? ` [${f.node_id}]` : "")))));
  return el("div", { class: "panel" }, el("div", { class: "panel-h" }, el("h2", null, "Datenfluss-Befunde")), body);
}

function addDataElement() {
  const name = el("input", { type: "text", placeholder: "z. B. betrag" });
  const type = el("select", null, ...DATA_TYPES.map((t) => el("option", { value: t }, t)));
  openModal("Datenelement", el("div", { class: "form-grid" },
    el("label", { class: "field" }, "Name", name),
    el("label", { class: "field" }, "Typ", type)), async () => {
    if (!name.value.trim()) return false;
    try {
      await api.post(`/schemas/${state.schemaId}/data-elements`, { name: name.value.trim(), data_type: type.value });
      await refreshSchema(); render(); toast("ok", "Datenelement angelegt");
    } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Anlegen");
}

function addDataAccess() {
  const schema = state.schema;
  const nodeSel = el("select", null, ...activitiesOf(schema).map((n) => el("option", { value: n.id }, nodeCaption(n))));
  const elemSel = el("select", null, ...Object.values(schema.data_elements).map((d) => el("option", { value: d.id }, d.name)));
  const modeSel = el("select", null, ...["READ", "WRITE", "READ_WRITE"].map((m) => el("option", { value: m }, m)));
  openModal("Datenbindung", el("div", { class: "form-grid" },
    el("label", { class: "field" }, "Schritt", nodeSel),
    el("label", { class: "field" }, "Element", elemSel),
    el("label", { class: "field" }, "Modus", modeSel)), async () => {
    try {
      await api.post(`/schemas/${state.schemaId}/data-access`, { node_id: nodeSel.value, element_id: elemSel.value, mode: modeSel.value });
      await refreshSchema(); render(); toast("ok", "Datenbindung gesetzt");
    } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Binden");
}

// --------------------------------------------------------------------------
// View: Ressourcensicht
// --------------------------------------------------------------------------

function viewOrg() {
  const content = byId("content");
  clear(content);
  if (!state.schema) { content.appendChild(emptyState("Kein Schema ausgewaehlt.")); return; }
  const schema = state.schema;
  const draft = isDraft(schema);
  const linked = !!schema.org_model_id;
  // A shared organisation is editable independently of this schema's lifecycle
  // (it is master data used across models); a local org follows the draft gate.
  const orgEditable = draft || linked;
  const org = schema.org_model || { roles: {}, org_units: {}, agents: {} };

  const orgPanel = sharedOrgBanner(schema, draft);

  const roleRows = Object.values(org.roles || {}).map((r) => [r.name, r.id]);
  const rolePanel = listPanel("Rollen", ["Name", "ID"], roleRows, orgEditable ? () => addRole() : null, "+ Rolle");

  const unitPanel = orgUnitPanel(org, orgEditable);
  const agentPanel = agentListPanel(org, orgEditable);

  // BZR-Zuordnung
  const ruleRows = Object.entries(schema.staff_rules || {}).map(([nid, rule]) => {
    const node = schema.nodes[nid];
    return [node ? nodeCaption(node) : nid, describeRule(rule)];
  });
  const ruleTable = ruleRows.length ? table(["Schritt", "Bearbeiterregel"], ruleRows) : emptyState("Noch keine Bearbeiterzuordnung.");
  const addRuleBtn = el("button", { class: "btn small", onClick: addStaffRule,
    disabled: !draft || activitiesOf(schema).length === 0 || (Object.keys(org.roles || {}).length + Object.keys(org.org_units || {}).length) === 0 }, "+ Zuordnung");
  const rulePanel = el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Bearbeiterzuordnung (BZR)"), el("span", { class: "sub" }, "Z1-Z4 live"), el("span", { class: "spacer", style: "flex:1" }), addRuleBtn),
    el("div", { class: "panel-b" }, ruleTable));

  content.appendChild(el("div", { class: "grid-2" },
    el("div", null, orgPanel, rolePanel, unitPanel, agentPanel),
    el("div", null, rulePanel, zFindingsPanel())));
}

// Endpoint base for org-entity edits: the shared org registry when the schema
// is linked, otherwise the schema's embedded org. The same path suffixes
// (/roles, /org-units, /agents, ...) exist under both bases.
function orgApi(suffix) {
  const oid = state.schema && state.schema.org_model_id;
  return oid ? `/org-models/${oid}${suffix}` : `/schemas/${state.schemaId}${suffix}`;
}

function sharedOrgBanner(schema, draft) {
  const linked = !!schema.org_model_id;
  const head = el("div", { class: "panel-h" }, el("h2", null, "Organisation"),
    el("span", { class: "sub" }, linked ? "geteilt (modell\u00FCbergreifend)" : "lokal in diesem Modell"),
    el("span", { class: "spacer", style: "flex:1" }),
    el("button", { class: "btn small", onClick: manageSharedOrg }, linked ? "Verwalten" : "Geteilte Organisation\u2026"));
  const body = el("div", { class: "panel-b" }, el("div", { class: "sub" }, linked
    ? "Diese Organisation wird zentral gepflegt; \u00C4nderungen wirken sofort in allen verkn\u00FCpften Modellen."
    : "Die Organisation geh\u00F6rt nur zu diesem Modell. Verkn\u00FCpfe sie, um dieselbe Organisation in mehreren Modellen zu verwenden."));
  return el("div", { class: "panel" }, head, body);
}

async function manageSharedOrg() {
  const schema = state.schema;
  const draft = isDraft(schema);
  let orgs = [];
  try { orgs = await api.get("/org-models"); } catch (err) { orgs = []; }

  if (schema.org_model_id) {
    const cur = orgs.find((o) => o.id === schema.org_model_id);
    const body = el("div", null,
      el("div", { class: "field" }, "Verkn\u00FCpft mit geteilter Organisation: ",
        el("strong", null, cur ? cur.name : schema.org_model_id)),
      el("p", { class: "sub", style: "margin-top:10px" }, draft
        ? "Beim L\u00F6sen wird die aktuelle Organisation als lokale Kopie ins Modell \u00FCbernommen."
        : "Zum L\u00F6sen der Verkn\u00FCpfung muss das Schema im Entwurf sein."));
    openModal("Geteilte Organisation", body, draft ? async () => {
      try { await api.del(`/schemas/${state.schemaId}/org-model`); await refreshSchema(); render(); toast("ok", "Verkn\u00FCpfung gel\u00F6st"); }
      catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
    } : null, draft ? "Verkn\u00FCpfung l\u00F6sen" : "Schliessen");
    return;
  }

  const sel = el("select", null, el("option", { value: "" }, "\u2013 vorhandene w\u00E4hlen \u2013"),
    ...orgs.map((o) => el("option", { value: o.id }, o.name)));
  const newName = el("input", { type: "text", placeholder: "z. B. Stadtverwaltung" });
  const body = el("div", null,
    el("label", { class: "field" }, "Vorhandene Organisation", sel),
    el("div", { class: "sub", style: "margin:10px 0" }, "\u2013 oder neue anlegen \u2013"),
    el("label", { class: "field" }, "Name", newName),
    draft ? null : el("p", { class: "sub", style: "margin-top:10px" }, "Verkn\u00FCpfen ist nur im Entwurf m\u00F6glich."));
  openModal("Geteilte Organisation verkn\u00FCpfen", body, async () => {
    if (!draft) { toast("err", "Nur im Entwurf m\u00F6glich"); return false; }
    try {
      let orgId = sel.value;
      if (!orgId) {
        if (!newName.value.trim()) return false;
        const created = await api.post("/org-models", { name: newName.value.trim() });
        orgId = created.id;
      }
      await api.post(`/schemas/${state.schemaId}/org-model`, { org_model_id: orgId });
      await refreshSchema(); render(); toast("ok", "Mit geteilter Organisation verkn\u00FCpft");
    } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Verkn\u00FCpfen");
}

function orgUnitPanel(org, draft) {
  const units = Object.values(org.org_units || {});
  const head = el("div", { class: "panel-h" }, el("h2", null, "Abteilungen"),
    el("span", { class: "sub" }, "Hierarchie mit Vorgesetzten"),
    el("span", { class: "spacer", style: "flex:1" }),
    el("button", { class: "btn small", onClick: () => addChildOrgUnit(null), disabled: !draft }, "+ OrgEinheit"));
  const body = el("div", { class: "panel-b" });
  if (!units.length) { body.appendChild(emptyState("Noch keine Abteilung.")); return el("div", { class: "panel" }, head, body); }

  // Kinder je Elternknoten indexieren; verwaiste (unbekannter Parent) auf oberste Ebene.
  const known = org.org_units || {};
  const childrenOf = {};
  units.forEach((u) => {
    const p = u.parent_id && known[u.parent_id] ? u.parent_id : "__root__";
    (childrenOf[p] = childrenOf[p] || []).push(u);
  });
  Object.values(childrenOf).forEach((list) => list.sort((a, b) => a.name.localeCompare(b.name)));

  const tree = el("div", { class: "tree" });
  (childrenOf["__root__"] || []).forEach((u) => tree.appendChild(renderUnitNode(u, org, draft, childrenOf)));
  body.appendChild(tree);
  return el("div", { class: "panel" }, head, body);
}

function renderUnitNode(unit, org, draft, childrenOf) {
  const mgr = unit.manager_id && org.agents[unit.manager_id] ? org.agents[unit.manager_id].name : null;
  const row = el("div", { class: "tree-row" },
    el("span", { class: "tree-name" }, unit.name),
    mgr
      ? el("span", { class: "tree-badge" }, "\u2605 " + mgr)
      : el("span", { class: "tree-badge muted-badge" }, "kein Vorgesetzter"),
    el("span", { class: "spacer", style: "flex:1" }),
    el("button", { class: "btn small", onClick: () => editManager(unit) }, "Vorgesetzter"),
    el("button", { class: "btn small", onClick: () => moveOrgUnit(unit) }, "Umh\u00E4ngen"),
    draft ? el("button", { class: "btn small", onClick: () => addChildOrgUnit(unit.id) }, "+ Unter") : null);
  const node = el("div", { class: "tree-node" }, row);
  const kids = childrenOf[unit.id] || [];
  if (kids.length) {
    const childWrap = el("div", { class: "tree-children" });
    kids.forEach((c) => childWrap.appendChild(renderUnitNode(c, org, draft, childrenOf)));
    node.appendChild(childWrap);
  }
  return node;
}

function agentListPanel(org, draft) {
  const agents = Object.values(org.agents || {});
  const head = el("div", { class: "panel-h" }, el("h2", null, "Agenten"),
    el("span", { class: "spacer", style: "flex:1" }),
    el("button", { class: "btn small", onClick: addAgent, disabled: !draft }, "+ Agent"));
  const body = el("div", { class: "panel-b" });
  if (!agents.length) body.appendChild(emptyState("Noch keine Agenten."));
  else {
    const rows = agents.map((a) => {
      const roles = (a.role_ids || []).map((r) => org.roles[r] ? org.roles[r].name : r).join(", ") || "\u2013";
      const unit = a.org_unit_id && org.org_units[a.org_unit_id] ? org.org_units[a.org_unit_id].name : "\u2013";
      const dep = a.deputy_id && org.agents[a.deputy_id] ? org.agents[a.deputy_id].name : "\u2013";
      const editBtn = el("button", { class: "btn small", onClick: () => editAgent(a), disabled: !draft }, "Bearbeiten");
      const depBtn = el("button", { class: "btn small", onClick: () => editDeputy(a) }, "Vertreter");
      const actions = el("div", { style: "display:flex; gap:6px; justify-content:flex-end" }, editBtn, depBtn);
      // Login provisioning is an admin-only convenience available in password
      // mode; it is independent of the schema lifecycle (works on shared orgs).
      if (state.passwordLogin && hasRole("admin")) {
        actions.appendChild(
          el("button", { class: "btn small", onClick: () => provisionLogin(a) }, "Login"));
      }
      return [a.name, roles, unit, dep, actions];
    });
    body.appendChild(table(["Agent", "Rollen", "Abteilung", "Vertreter", ""], rows));
  }
  return el("div", { class: "panel" }, head, body);
}

function describeRule(rule) {
  if (!rule) return "\u2013";
  if (rule.kind === "ROLE") return `Rolle: ${rule.ref}`;
  if (rule.kind === "ORG_UNIT") return `OrgEinheit: ${rule.ref}${rule.recursive ? " (inkl. Unterbereiche)" : ""}`;
  if (rule.kind === "NODE_PERFORMING_AGENT") return `Bearbeiter von ${rule.ref}`;
  if (rule.operands) return `${rule.kind}(${rule.operands.map(describeRule).join(", ")})`;
  return rule.kind;
}

function zFindingsPanel() {
  const v = state.validation;
  const zs = v && !v.correct ? v.findings.filter((f) => f.rule[0] === "Z" || f.rule[0] === "A") : [];
  const body = el("div", { class: "panel-b" });
  if (!zs.length) body.appendChild(el("div", { class: "ok-banner" }, "\u2713 Ressourcen/Bearbeiter konsistent (Z/A)."));
  else zs.forEach((f) => body.appendChild(el("div", { class: "finding" }, el("span", { class: "rule" }, f.rule), el("span", null, f.message + (f.node_id ? ` [${f.node_id}]` : "")))));
  return el("div", { class: "panel" }, el("div", { class: "panel-h" }, el("h2", null, "Ressourcen-Befunde")), body);
}

function addRole() {
  const name = el("input", { type: "text", placeholder: "z. B. Sachbearbeiter" });
  openModal("Rolle", el("label", { class: "field" }, "Name", name), async () => {
    if (!name.value.trim()) return false;
    try { await api.post(orgApi(`/roles`), { name: name.value.trim() }); await refreshSchema(); render(); toast("ok", "Rolle angelegt"); }
    catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Anlegen");
}

function addAgent() {
  const org = state.schema.org_model;
  const name = el("input", { type: "text", placeholder: "z. B. Erika Muster" });
  const roleSel = el("select", { multiple: "multiple", size: Math.min(5, Math.max(1, Object.keys(org.roles).length)) },
    ...Object.values(org.roles).map((r) => el("option", { value: r.id }, r.name)));
  const unitSel = el("select", null, el("option", { value: "" }, "\u2013 keine \u2013"),
    ...Object.values(org.org_units || {}).map((u) => el("option", { value: u.id }, u.name)));
  const depSel = el("select", null, el("option", { value: "" }, "\u2013 keiner \u2013"),
    ...Object.values(org.agents || {}).map((a) => el("option", { value: a.id }, a.name)));
  openModal("Agent", el("div", null,
    el("label", { class: "field" }, "Name", name),
    el("label", { class: "field", style: "margin-top:10px" }, "Rollen (Mehrfachauswahl)", roleSel),
    el("label", { class: "field", style: "margin-top:10px" }, "Abteilung", unitSel),
    el("label", { class: "field", style: "margin-top:10px" }, "Vertreter", depSel)), async () => {
    if (!name.value.trim()) return false;
    const roleIds = [...roleSel.selectedOptions].map((o) => o.value);
    const payload = { name: name.value.trim(), role_ids: roleIds };
    if (unitSel.value) payload.org_unit_id = unitSel.value;
    if (depSel.value) payload.deputy_id = depSel.value;
    try { await api.post(orgApi(`/agents`), payload); await refreshSchema(); render(); toast("ok", "Agent angelegt"); }
    catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Anlegen");
}

function addChildOrgUnit(parentId) {
  const org = state.schema.org_model;
  const name = el("input", { type: "text", placeholder: "z. B. Einkauf" });
  const mgrSel = el("select", null, el("option", { value: "" }, "\u2013 keiner \u2013"),
    ...Object.values(org.agents || {}).map((a) => el("option", { value: a.id }, a.name)));
  const parentName = parentId && org.org_units[parentId] ? org.org_units[parentId].name : "\u2013 oberste Ebene \u2013";
  const parentField = el("input", { type: "text", value: parentName, disabled: "disabled" });
  openModal("Abteilung", el("div", null,
    el("label", { class: "field" }, "Name", name),
    el("label", { class: "field", style: "margin-top:10px" }, "\u00DCbergeordnet", parentField),
    el("label", { class: "field", style: "margin-top:10px" }, "Vorgesetzter", mgrSel)), async () => {
    if (!name.value.trim()) return false;
    const payload = { name: name.value.trim() };
    if (parentId) payload.parent_id = parentId;
    if (mgrSel.value) payload.manager_id = mgrSel.value;
    try { await api.post(orgApi(`/org-units`), payload); await refreshSchema(); render(); toast("ok", "Abteilung angelegt"); }
    catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Anlegen");
}

function moveOrgUnit(unit) {
  const org = state.schema.org_model;
  // Eigenen Knoten + alle Nachfahren ausschliessen (Zyklus verhindern; Backend prueft zusaetzlich).
  const blocked = new Set([unit.id]);
  let changed = true;
  while (changed) {
    changed = false;
    Object.values(org.org_units).forEach((u) => {
      if (u.parent_id && blocked.has(u.parent_id) && !blocked.has(u.id)) { blocked.add(u.id); changed = true; }
    });
  }
  const sel = el("select", null, el("option", { value: "" }, "\u2013 oberste Ebene \u2013"),
    ...Object.values(org.org_units).filter((u) => !blocked.has(u.id)).map((u) => el("option", { value: u.id }, u.name)));
  if (unit.parent_id) sel.value = unit.parent_id;
  openModal(`Umh\u00E4ngen: ${unit.name}`, el("label", { class: "field" }, "\u00DCbergeordnete Abteilung", sel), async () => {
    try { await api.post(orgApi(`/org-units/${unit.id}/parent`), { parent_id: sel.value || null }); await refreshSchema(); render(); toast("ok", "Abteilung umgeh\u00E4ngt"); }
    catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Speichern");
}

function editManager(unit) {
  const org = state.schema.org_model;
  const sel = el("select", null, el("option", { value: "" }, "\u2013 keiner \u2013"),
    ...Object.values(org.agents || {}).map((a) => el("option", { value: a.id }, a.name)));
  if (unit.manager_id) sel.value = unit.manager_id;
  openModal(`Vorgesetzter: ${unit.name}`, el("label", { class: "field" }, "Vorgesetzter", sel), async () => {
    try { await api.post(orgApi(`/org-units/${unit.id}/manager`), { manager_id: sel.value || null }); await refreshSchema(); render(); toast("ok", "Vorgesetzter gesetzt"); }
    catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Speichern");
}

function editAgent(agent) {
  const org = state.schema.org_model;
  const name = el("input", { type: "text", value: agent.name });
  const roleSel = el("select", { multiple: "multiple", size: Math.min(5, Math.max(1, Object.keys(org.roles).length)) },
    ...Object.values(org.roles).map((r) => {
      const o = el("option", { value: r.id }, r.name);
      if ((agent.role_ids || []).includes(r.id)) o.selected = true;
      return o;
    }));
  const unitSel = el("select", null, el("option", { value: "" }, "\u2013 keine \u2013"),
    ...Object.values(org.org_units || {}).map((u) => el("option", { value: u.id }, u.name)));
  unitSel.value = agent.org_unit_id || "";
  openModal(`Agent bearbeiten: ${agent.name}`, el("div", null,
    el("label", { class: "field" }, "Name", name),
    el("label", { class: "field", style: "margin-top:10px" }, "Rollen (Mehrfachauswahl)", roleSel),
    el("label", { class: "field", style: "margin-top:10px" }, "Abteilung", unitSel)), async () => {
    if (!name.value.trim()) return false;
    const roleIds = [...roleSel.selectedOptions].map((o) => o.value);
    const payload = { name: name.value.trim(), role_ids: roleIds, org_unit_id: unitSel.value || null };
    try { await api.patch(orgApi(`/agents/${agent.id}`), payload); await refreshSchema(); render(); toast("ok", "Agent gespeichert"); }
    catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Speichern");
}

function editDeputy(agent) {
  const org = state.schema.org_model;
  const sel = el("select", null, el("option", { value: "" }, "\u2013 keiner \u2013"),
    ...Object.values(org.agents || {}).filter((a) => a.id !== agent.id).map((a) => el("option", { value: a.id }, a.name)));
  if (agent.deputy_id) sel.value = agent.deputy_id;
  openModal(`Vertreter: ${agent.name}`, el("label", { class: "field" }, "Vertreter", sel), async () => {
    try { await api.post(orgApi(`/agents/${agent.id}/deputy`), { deputy_id: sel.value || null }); await refreshSchema(); render(); toast("ok", "Vertreter gesetzt"); }
    catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Speichern");
}

// Client-side mirror of the server's suggest_login (vorname.nachname). Only used
// to preview the suggestion; the server remains the source of truth.
function suggestLoginClient(name) {
  const map = { "\u00E4": "ae", "\u00F6": "oe", "\u00FC": "ue", "\u00DF": "ss",
    "\u00C4": "ae", "\u00D6": "oe", "\u00DC": "ue" };
  const translit = (name || "").replace(/[\u00E4\u00F6\u00FC\u00DF\u00C4\u00D6\u00DC]/g, (c) => map[c]);
  const ascii = translit.normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
  const parts = ascii.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  return parts.join(".") || "user";
}

// Admin convenience (password mode): provision a login for an agent. The login
// is suggested from the name (server is authoritative); the admin picks the
// coarse RBAC roles. The one-off initial password is shown once afterwards.
function provisionLogin(agent) {
  const roleSel = el("select", { multiple: "multiple", size: 4 },
    ...Object.keys(ROLE_LABELS).map((r) => {
      const o = el("option", { value: r }, ROLE_LABELS[r]);
      if (r === "operator") o.selected = true;
      return o;
    }));
  const loginInput = el("input", { type: "text", placeholder: suggestLoginClient(agent.name) });
  openModal(`Login anlegen: ${agent.name}`, el("div", null,
    el("div", { class: "muted", style: "margin-bottom:10px" },
      "Der Login wird aus dem Namen vorgeschlagen (\u00FCberschreibbar). Es wird ein Initialpasswort erzeugt, das einmalig angezeigt wird; die Person vergibt beim ersten Login ein eigenes Passwort."),
    el("label", { class: "field" }, "Rollen (Mehrfachauswahl)", roleSel),
    el("label", { class: "field", style: "margin-top:10px" }, "Login (optional)", loginInput)), async () => {
    const roles = [...roleSel.selectedOptions].map((o) => o.value);
    if (!roles.length) { toast("err", "Bitte mindestens eine Rolle w\u00E4hlen"); return false; }
    const payload = { agent_id: agent.id, display_name: agent.name, roles };
    if (loginInput.value.trim()) payload.login = loginInput.value.trim();
    try {
      const res = await api.post("/users", payload);
      showLoginCredentials(res);
      toast("ok", "Login angelegt", [`Login: ${res.login}`]);
    } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Anlegen");
}

// Show the freshly provisioned login + one-off initial password (shown once).
function showLoginCredentials(res) {
  const loginField = el("input", { type: "text", value: res.login, readonly: "readonly" });
  const pwField = el("input", { type: "text", value: res.initial_password, readonly: "readonly" });
  openModal("Zugangsdaten", el("div", null,
    el("div", { class: "muted", style: "margin-bottom:10px" },
      "Bitte notieren und der Person sicher mitteilen. Das Initialpasswort wird nur jetzt angezeigt."),
    el("label", { class: "field" }, "Login", loginField),
    el("label", { class: "field", style: "margin-top:10px" }, "Initialpasswort", pwField)),
    async () => true, "Schlie\u00DFen");
}


function addStaffRule() {
  const schema = state.schema;
  const org = schema.org_model;
  const nodeSel = el("select", null, ...activitiesOf(schema).map((n) => el("option", { value: n.id }, nodeCaption(n))));
  const refSel = el("select");
  const kindSel = el("select", null, el("option", { value: "ROLE" }, "Rolle"), el("option", { value: "ORG_UNIT" }, "OrgEinheit"));
  const recBox = el("input", { type: "checkbox" });
  const recField = el("label", { class: "field" }, recBox, " Abteilung und alle Bereiche darunter");
  function syncKind() {
    clear(refSel);
    const src = kindSel.value === "ROLE" ? org.roles : org.org_units;
    Object.values(src || {}).forEach((x) => refSel.appendChild(el("option", { value: x.id }, x.name)));
    recField.style.display = kindSel.value === "ORG_UNIT" ? "" : "none";
  }
  kindSel.addEventListener("change", syncKind); syncKind();
  openModal("Bearbeiterregel", el("div", { class: "form-grid" },
    el("label", { class: "field" }, "Schritt", nodeSel),
    el("label", { class: "field" }, "Art", kindSel),
    el("label", { class: "field" }, "Referenz", refSel),
    recField), async () => {
    if (!refSel.value) { toast("err", "Keine Referenz verf\u00FCgbar"); return false; }
    const rule = { kind: kindSel.value, ref: refSel.value };
    if (kindSel.value === "ORG_UNIT") rule.recursive = recBox.checked;
    try {
      await api.post(`/schemas/${state.schemaId}/staff-rule`, { node_id: nodeSel.value, rule });
      await refreshSchema(); render(); toast("ok", "Zuordnung gesetzt");
    } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Zuordnen");
}

// --------------------------------------------------------------------------
// View: Ausfuehrung
// --------------------------------------------------------------------------

async function viewRun() {
  const content = byId("content");
  clear(content);
  if (!state.schema) { content.appendChild(emptyState("Kein Schema ausgewaehlt.")); return; }
  const schema = state.schema;

  const header = el("div", { class: "panel" },
    el("div", { class: "panel-h" },
      el("h2", null, schema.name), el("span", { class: "sub" }, `v${schema.version}`), lifecyclePill(schema),
      el("span", { class: "spacer", style: "flex:1" }),
      schema.lifecycle_state === "RELEASED"
        ? el("button", { class: "btn small primary", onClick: startInstance }, "\u25B6 Instanz starten")
        : hasRole("modeler", "admin")
          ? el("button", { class: "btn small", onClick: startInstance }, "\u25B6 Test-Instanz starten")
          : el("span", { class: "muted", style: "font-size:12px" }, "Nur freigegebene Schemata sind instanziierbar.")));
  content.appendChild(header);

  if (!state.instance) {
    content.appendChild(emptyState("Keine Instanz geladen. Starte eine Instanz oder w\u00E4hle eine im Monitoring."));
    return;
  }
  await renderInstanceDetail(content, true);
}

async function startInstance() {
  try {
    const inst = await api.post(`/schemas/${state.schemaId}/instances`);
    await loadInstance(inst.id);
    render();
    toast("ok", inst.is_test ? "Test-Instanz gestartet" : "Instanz gestartet", [inst.id]);
  } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); }
}

async function loadInstance(id) {
  state.instanceId = id;
  state.instance = await api.get(`/instances/${id}`);
  state.worklist = await api.get(`/instances/${id}/worklist`);
}

async function renderInstanceDetail(container, withActions) {
  const inst = state.instance;
  const wl = state.worklist;
  // Schema, gegen das die Instanz laeuft (ggf. Ad-hoc-Variante)
  const runSchema = inst.ad_hoc_schema || state.schema;
  const statePill = el("span", { class: "pill " + (inst.state === "COMPLETED" ? "pill-green" : "pill-blue") }, inst.state);

  const graphPanel = el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Live-Prozesslandkarte"), el("span", { class: "sub" }, inst.id), statePill,
      inst.is_test ? el("span", { class: "pill pill-amber", title: "Test-Instanz \u2013 nicht im Monitoring gez\u00E4hlt" }, "TEST") : null),
    el("div", { class: "panel-b" }, renderGraph(runSchema, { instance: inst })));

  // Worklist
  const wlBody = el("div", { class: "panel-b" });
  if (inst.state === "COMPLETED") {
    wlBody.appendChild(el("div", { class: "ok-banner" }, "\u2713 Instanz abgeschlossen \u2013 jeder Knoten COMPLETED oder SKIPPED."));
  } else {
    (wl.ready_activities || []).forEach((nid) => {
      const node = runSchema.nodes[nid];
      wlBody.appendChild(el("div", { class: "worklist-item" },
        el("span", { class: "name" }, node ? nodeCaption(node) : nid),
        el("span", { class: "tag" }, "bereit"),
        withActions ? el("button", { class: "btn small green", onClick: () => completeActivity(nid, node) }, "Abschlie\u00DFen") : null));
    });
    (wl.pending_decisions || []).forEach((nid) => {
      const node = runSchema.nodes[nid];
      wlBody.appendChild(el("div", { class: "worklist-item" },
        el("span", { class: "name" }, (node ? nodeCaption(node) : nid) + " (XOR)"),
        el("span", { class: "tag" }, "Entscheidung"),
        withActions ? el("button", { class: "btn small primary", onClick: () => decideBranch(nid, runSchema) }, "Zweig w\u00E4hlen") : null));
    });
    if (!(wl.ready_activities || []).length && !(wl.pending_decisions || []).length) {
      wlBody.appendChild(el("div", { class: "muted", style: "font-size:13px" }, "Keine bereiten Schritte (l\u00E4uft automatisch weiter oder wartet auf Teilprozess)."));
    }
  }
  const wlPanel = el("div", { class: "panel" }, el("div", { class: "panel-h" }, el("h2", null, "Arbeitsliste")), wlBody);

  // Datenwerte
  const dataRows = Object.entries(inst.data_values || {}).map(([k, v]) => {
    const elem = runSchema.data_elements[k];
    return [elem ? elem.name : k, String(v)];
  });
  const dataPanel = el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Instanzdaten")),
    el("div", { class: "panel-b" }, dataRows.length ? table(["Element", "Wert"], dataRows) : emptyState("Noch keine Werte.")));

  // Audit-Timeline (Schritt 15)
  let events = [];
  try { events = await api.get(`/instances/${inst.id}/audit`); } catch (e) { /* ignore */ }
  const tlBody = el("div", { class: "panel-b" });
  if (!events.length) {
    tlBody.appendChild(emptyState("Noch keine Ereignisse aufgezeichnet."));
  } else {
    const tl = el("div", { class: "timeline" });
    events.forEach((ev) => {
      const meta = [];
      if (ev.label || ev.node_id) meta.push(ev.label || ev.node_id);
      if (ev.agent_id) meta.push("Bearbeiter: " + agentNameOf(ev.agent_id));
      tl.appendChild(el("div", { class: "tl-item" },
        el("span", { class: "tl-time" }, fmtTimestamp(ev.timestamp)),
        el("span", { class: "tl-type" }, eventLabel(ev.event_type)),
        el("span", { class: "tl-meta" }, meta.join(" \u2013 "))));
    });
    tlBody.appendChild(tl);
  }
  const timelinePanel = el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Audit-Verlauf"), el("span", { class: "sub" }, events.length + " Ereignisse")),
    tlBody);

  container.appendChild(el("div", { class: "grid-2" }, graphPanel, el("div", null, wlPanel, dataPanel, timelinePanel)));
}

async function completeActivity(nodeId, node) {
  const schema = state.instance.ad_hoc_schema || state.schema;
  await promptComplete(schema, state.instanceId, nodeId, node ? nodeCaption(node) : nodeId, null,
    async () => { await loadInstance(state.instanceId); render(); });
}

async function promptComplete(schema, instanceId, nodeId, label, agentId, onDone) {
  // Pflicht-Schreibvariablen dieses Schritts abfragen
  const writes = (schema.data_accesses || []).filter((a) => a.node_id === nodeId && (a.mode === "WRITE" || a.mode === "READ_WRITE"));
  const inputs = {};
  const body = el("div", { class: "form-grid" });
  writes.forEach((a) => {
    const elem = schema.data_elements[a.element_id];
    const input = el("input", { type: elem && (elem.data_type === "INTEGER" || elem.data_type === "FLOAT") ? "number" : "text", placeholder: elem ? elem.name : a.element_id });
    inputs[a.element_id] = { input, elem };
    body.appendChild(el("label", { class: "field" }, (elem ? elem.name : a.element_id) + ` (${elem ? elem.data_type : "?"})`, input));
  });
  const doComplete = async () => {
    const data = {};
    for (const [eid, { input, elem }] of Object.entries(inputs)) {
      let val = input.value;
      if (val === "") continue;
      if (elem && elem.data_type === "INTEGER") val = parseInt(val, 10);
      else if (elem && elem.data_type === "FLOAT") val = parseFloat(val);
      else if (elem && elem.data_type === "BOOLEAN") val = val === "true" || val === "1";
      data[eid] = val;
    }
    try {
      const payload = { node_id: nodeId, data };
      if (agentId) payload.agent_id = agentId;
      await api.post(`/instances/${instanceId}/complete`, payload);
      toast("ok", "Schritt abgeschlossen");
      if (onDone) await onDone();
    } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  };
  if (writes.length) openModal(`Abschlie\u00DFen: ${label}`, body, doComplete, "Abschlie\u00DFen");
  else doComplete();
}

function decideBranch(nodeId, schema) {
  const targets = (schema.edges || []).filter((e) => e.source === nodeId);
  const sel = el("select", null, ...targets.map((e) => {
    const tn = schema.nodes[e.target];
    return el("option", { value: e.target }, (tn ? nodeCaption(tn) : e.target) + (e.condition ? ` [${e.condition}]` : ""));
  }));
  openModal("XOR-Zweig w\u00E4hlen", el("label", { class: "field" }, "Zielzweig", sel), async () => {
    try {
      await api.post(`/instances/${state.instanceId}/decide`, { node_id: nodeId, target_node_id: sel.value });
      await loadInstance(state.instanceId); render(); toast("ok", "Zweig gew\u00E4hlt");
    } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "W\u00E4hlen");
}

// --------------------------------------------------------------------------
// View: Monitoring
// --------------------------------------------------------------------------

async function viewMonitor() {
  const content = byId("content");
  clear(content);
  let instances = [];
  try {
    const ids = await api.get("/instances");
    instances = await Promise.all(ids.map((id) => api.get(`/instances/${id}`)));
  } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); }

  const running = instances.filter((i) => i.state === "RUNNING").length;
  const done = instances.filter((i) => i.state === "COMPLETED").length;

  // KPI-Report + Prozesskarte aus dem Audit-Log (Schritt 15)
  let report = null;
  let pmap = null;
  try { report = await api.get("/monitoring/kpis"); } catch (e) { /* ignore */ }
  try { pmap = await api.get("/monitoring/process-map"); } catch (e) { /* ignore */ }

  const kpis = el("div", { class: "kpis" },
    kpi("Instanzen gesamt", instances.length),
    kpi("Laufend", running),
    kpi("Abgeschlossen", done),
    kpi("\u00D8 Durchlaufzeit", report ? fmtDuration(report.avg_cycle_seconds) : "\u2013"));
  content.appendChild(kpis);

  const rows = instances.map((i) => {
    const total = Object.keys(i.node_states || {}).length || 1;
    const completed = Object.values(i.node_states || {}).filter((s) => s === "COMPLETED" || s === "SKIPPED").length;
    const pct = Math.round((completed / total) * 100);
    return { i, cells: [i.id, schemaLabel(i.schema_id, i.schema_version), statePillFor(i.state), `${pct}%`] };
  });

  const tbl = el("table", null,
    el("thead", null, el("tr", null, ...["Instanz", "Schema", "Status", "Fortschritt"].map((h) => el("th", null, h)))),
    el("tbody", null, ...(rows.length ? rows.map((r) =>
      el("tr", { class: "clickable", onClick: () => openInstanceFromMonitor(r.i.id) }, ...r.cells.map((c) => el("td", null, c))))
      : [el("tr", null, el("td", { colspan: 4 }, emptyState("Keine Instanzen. Starte eine in der Ausf\u00FChrungs-Sicht.")))])));

  content.appendChild(el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Aktive Instanzen"), el("span", { class: "sub" }, "Klick \u00F6ffnet Detail")),
    el("div", { class: "panel-b" }, tbl)));

  // Engpass-Analyse (Aktivitaeten nach Haeufigkeit + Dauer)
  const stats = (report && report.activity_stats) || [];
  const statRows = stats.map((s) => [s.label || s.node_id, String(s.completed), fmtDuration(s.avg_duration_seconds)]);
  content.appendChild(el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Engp\u00E4sse \u2013 Aktivit\u00E4ten"), el("span", { class: "sub" }, "H\u00E4ufigkeit & \u00D8 Bearbeitungszeit")),
    el("div", { class: "panel-b" }, statRows.length
      ? table(["Aktivit\u00E4t", "Abschl\u00FCsse", "\u00D8 Dauer"], statRows)
      : emptyState("Noch keine abgeschlossenen Aktivit\u00E4ten erfasst."))));

  // Entdeckte Prozesskarte (Process Mining: directly-follows)
  const edges = (pmap && pmap.edges) || [];
  const nameOfNode = {};
  ((pmap && pmap.nodes) || []).forEach((n) => { nameOfNode[n.node_id] = n.label || n.node_id; });
  const edgeRows = edges.map((e) => [
    nameOfNode[e.source] || e.source,
    nameOfNode[e.target] || e.target,
    String(e.frequency),
  ]);
  content.appendChild(el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Prozesskarte (entdeckt)"), el("span", { class: "sub" }, "Process Mining \u2013 reale Abl\u00E4ufe")),
    el("div", { class: "panel-b" }, edgeRows.length
      ? table(["Von", "Nach", "H\u00E4ufigkeit"], edgeRows)
      : emptyState("Noch keine Abl\u00E4ufe entdeckt. Schlie\u00DFe Aktivit\u00E4ten ab."))));

  // Wartung: nur Administratoren d\u00FCrfen die Daten zur\u00FCcksetzen oder die
  // Beispieldaten laden. Beides l\u00E4uft \u00FCber POST /admin/reset.
  if (hasRole("admin")) {
    content.appendChild(el("div", { class: "panel" },
      el("div", { class: "panel-h" },
        el("h2", null, "Wartung (Administrator)"),
        el("span", { class: "sub" }, "Daten zur\u00FCcksetzen \u00B7 Beispiel laden")),
      el("div", { class: "panel-b" },
        el("p", { class: "muted" },
          "Setzt das gesamte System zur\u00FCck. Die Beispieldaten zeigen alle Funktionen anhand zweier Prozesse, einer Organisation und drei laufenden Instanzen. Dieser Vorgang l\u00F6scht alle vorhandenen Daten unwiderruflich."),
        el("div", { style: "display:flex; gap:10px; margin-top:12px; flex-wrap:wrap;" },
          el("button", { class: "btn primary", onClick: () => confirmReset(true) }, "Beispieldaten laden"),
          el("button", { class: "btn danger", onClick: () => confirmReset(false) }, "Auf Null zur\u00FCcksetzen")))));
  }

  if (state.instance) {
    const detail = el("div");
    // Schema der Instanz laden, damit der Graph passt
    if (state.instance.schema_id !== state.schemaId) {
      try { state.schema = await api.get(`/schemas/${state.instance.schema_id}`); } catch (e) { /* ignore */ }
    }
    await renderInstanceDetail(detail, true);
    content.appendChild(detail);
  }
}

async function openInstanceFromMonitor(id) {
  try {
    await loadInstance(id);
    if (state.instance.schema_id !== state.schemaId) {
      state.schemaId = state.instance.schema_id;
      await refreshSchema();
      renderSchemaPicker();
    }
    render();
  } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); }
}

// Administrator-Wartung: System zur\u00FCcksetzen bzw. Beispieldaten laden.
function confirmReset(loadDemo) {
  const msg = loadDemo
    ? "Alle vorhandenen Daten werden gel\u00F6scht und durch die Beispieldaten ersetzt. M\u00F6chten Sie fortfahren?"
    : "Alle Schemata, Instanzen und Organisationsmodelle werden gel\u00F6scht. Im Login-Betrieb werden zus\u00E4tzlich alle Nutzer au\u00DFer Ihnen und dem Administrator-Konto entfernt. Dieser Schritt kann nicht r\u00FCckg\u00E4ngig gemacht werden.";
  openModal(
    loadDemo ? "Beispieldaten laden" : "Auf Null zur\u00FCcksetzen",
    el("p", { class: "muted" }, msg),
    async () => { await runReset(loadDemo); return true; },
    loadDemo ? "Beispieldaten laden" : "Endg\u00FCltig l\u00F6schen");
}

async function runReset(loadDemo) {
  try {
    const res = await api.post("/admin/reset", { load_demo: !!loadDemo });
    const lines = [
      `Schemata: ${res.schemas}`,
      `Instanzen: ${res.instances}`,
      `Organisationsmodelle: ${res.org_models}`,
    ];
    if (state.passwordLogin) lines.push(`Nutzerkonten: ${res.users}`);
    toast("ok",
      loadDemo ? "Beispieldaten geladen" : "System auf Null zur\u00FCckgesetzt",
      lines);
    // Auswahl zur\u00FCcksetzen, da bisherige Schemata/Instanzen evtl. weg sind.
    state.instance = null;
    state.schema = null;
    state.schemaId = null;
    await boot();
  } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); }
}

function statePillFor(s) {
  return el("span", { class: "pill " + (s === "COMPLETED" ? "pill-green" : "pill-blue") }, s);
}

// Audit-/Monitoring-Hilfen (Schritt 15)
const EVENT_LABELS = {
  INSTANCE_CREATED: "Instanz erstellt",
  ACTIVITY_STARTED: "Aktivit\u00E4t gestartet",
  ACTIVITY_COMPLETED: "Aktivit\u00E4t abgeschlossen",
  BRANCH_DECIDED: "Zweig entschieden",
  ADHOC_INSERTED: "Ad-hoc eingef\u00FCgt",
  ADHOC_DELETED: "Ad-hoc gel\u00F6scht",
  INSTANCE_MIGRATED: "Instanz migriert",
  INSTANCE_COMPLETED: "Instanz abgeschlossen",
};

function eventLabel(t) { return EVENT_LABELS[t] || t; }

function fmtTimestamp(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function fmtDuration(sec) {
  if (sec == null) return "\u2013";
  if (sec < 60) return sec.toFixed(1) + " s";
  if (sec < 3600) return (sec / 60).toFixed(1) + " min";
  return (sec / 3600).toFixed(1) + " h";
}

// --------------------------------------------------------------------------
// View: Meine Aufgaben (Bearbeiter-Aufgabenliste)
// --------------------------------------------------------------------------

function agentNameOf(id) {
  const org = state.schema && state.schema.org_model;
  const a = org && org.agents ? org.agents[id] : null;
  return a ? a.name : id;
}

async function viewTasks() {
  const content = byId("content");
  clear(content);
  if (!state.schema) { content.appendChild(emptyState("Kein Schema ausgew\u00E4hlt.")); return; }
  const org = state.schema.org_model || { agents: {} };
  const agents = Object.values(org.agents || {});
  if (!agents.length) { content.appendChild(emptyState("Keine Agenten im Organisationsmodell. Lege zuerst Agenten in der Ressourcensicht an.")); return; }

  // A bound principal (token login) is tied to one agent: no picker, the
  // worklist comes from /me/tasks. In open dev mode we keep the agent picker.
  const bound = state.principal && state.principal.agent_id;
  let agentId;
  let picker;
  if (bound) {
    agentId = state.principal.agent_id;
    const who = state.principal.display_name || agentNameOf(agentId);
    picker = el("div", { class: "panel" },
      el("div", { class: "panel-h" }, el("h2", null, "Angemeldet"), el("span", { class: "sub" }, "Aufgaben f\u00FCr dich, inkl. Vertretung")),
      el("div", { class: "panel-b" }, el("div", { class: "ok-banner" }, "\u2713 Angemeldet als " + who)));
  } else {
    agentId = localStorage.getItem("agentId");
    if (!agentId || !agents.some((a) => a.id === agentId)) agentId = agents[0].id;
    const sel = el("select", null, ...agents.map((a) => el("option", { value: a.id }, a.name)));
    sel.value = agentId;
    sel.addEventListener("change", () => { localStorage.setItem("agentId", sel.value); render(); });
    picker = el("div", { class: "panel" },
      el("div", { class: "panel-h" }, el("h2", null, "Bearbeiter"), el("span", { class: "sub" }, "Aufgaben f\u00FCr eine Person, inkl. Vertretung")),
      el("div", { class: "panel-b" }, el("label", { class: "field" }, "Angemeldet als", sel)));
  }
  content.appendChild(picker);

  let tasks = [];
  try { tasks = await api.get(bound ? "/me/tasks" : `/agents/${agentId}/tasks`); }
  catch (err) { const d = describeError(err); toast("err", d.title, d.lines); }

  const body = el("div", { class: "panel-b" });
  if (!tasks.length) {
    body.appendChild(el("div", { class: "ok-banner" }, "\u2713 Keine offenen Aufgaben f\u00FCr " + agentNameOf(agentId) + "."));
  } else {
    const rows = tasks.map((t) => {
      const elig = (t.eligible_agents || []).map(agentNameOf).join(", ");
      const btn = el("button", { class: "btn small green", onClick: () => completeTask(t, agentId) }, "Erledigen");
      return [t.label || t.node_id, schemaLabel(t.schema_id, t.schema_version), elig, btn];
    });
    body.appendChild(table(["Aufgabe", "Prozess", "Berechtigte", ""], rows));
  }
  content.appendChild(el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Offene Aufgaben"), el("span", { class: "sub" }, tasks.length + " Eintr\u00E4ge")),
    body));
}

async function completeTask(task, agentId) {
  let schema;
  try {
    const inst = await api.get(`/instances/${task.instance_id}`);
    schema = inst.ad_hoc_schema || await api.get(`/schemas/${task.schema_id}`);
  } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return; }
  await promptComplete(schema, task.instance_id, task.node_id, task.label || task.node_id, agentId, async () => { render(); });
}

// --------------------------------------------------------------------------
// Wiederverwendbare UI-Bausteine
// --------------------------------------------------------------------------

function emptyState(text) { return el("div", { class: "empty" }, text); }
function kpi(label, value) { return el("div", { class: "kpi" }, el("div", { class: "label" }, label), el("div", { class: "value" }, String(value))); }

function table(headers, rows) {
  return el("table", null,
    el("thead", null, el("tr", null, ...headers.map((h) => el("th", null, h)))),
    el("tbody", null, ...rows.map((r) => el("tr", null, ...r.map((c) =>
      el("td", null, c instanceof Node ? c : String(c)))))));
}

function listPanel(title, headers, rows, onAdd, addLabel) {
  const head = el("div", { class: "panel-h" }, el("h2", null, title), el("span", { class: "spacer", style: "flex:1" }),
    onAdd ? el("button", { class: "btn small", onClick: onAdd }, addLabel) : null);
  return el("div", { class: "panel" }, head, el("div", { class: "panel-b" }, rows.length ? table(headers, rows) : emptyState("Noch nichts angelegt.")));
}

// --------------------------------------------------------------------------
// Navigation + Render-Dispatch
// --------------------------------------------------------------------------

const VIEW_META = {
  model: { title: "Modellieren", sub: "Gef\u00FChrte +-Operationen, live-validiert", fn: viewModel },
  data: { title: "Datensicht", sub: "Datenelemente + Lese/Schreib-Bindung (D/C)", fn: viewData },
  org: { title: "Ressourcensicht", sub: "Organisationsmodell + Bearbeiterregeln (Z/A)", fn: viewOrg },
  run: { title: "Ausf\u00FChrung", sub: "Instanzen starten und Arbeitsliste abarbeiten", fn: viewRun },
  tasks: { title: "Meine Aufgaben", sub: "Bearbeiter-Aufgabenliste mit Z-Laufzeitaufl\u00F6sung", fn: viewTasks },
  monitor: { title: "Monitoring", sub: "Live-Status aktiver Instanzen", fn: viewMonitor },
};

function setActiveNav() {
  [...byId("nav").children].forEach((b) => b.classList.toggle("active", b.dataset.view === state.view));
}

// --- Auth / Login (Auth-Konzept Variante C) -------------------------------

// German labels for the coarse RBAC roles (technical ids stay English).
const ROLE_LABELS = { admin: "Administrator", modeler: "Modellierer", operator: "Bearbeiter", viewer: "Leser" };

// Which roles may see each navigation view. In open dev mode the principal
// holds every role, so the full UI stays visible exactly as before.
const VIEW_ROLES = {
  model: ["modeler", "admin"],
  data: ["modeler", "admin"],
  org: ["modeler", "admin"],
  run: ["operator", "modeler", "admin"],
  tasks: ["operator", "modeler", "admin"],
  monitor: ["viewer", "operator", "modeler", "admin"],
};

function currentRoles() {
  return (state.principal && state.principal.roles) || [];
}

function hasRole(...allowed) {
  const roles = currentRoles();
  return allowed.some((r) => roles.includes(r));
}

// Fetch the verified identity from the API (/auth/me). On 401 the token is
// invalid; we drop it and fall back to anonymous so the UI stays usable.
async function loadPrincipal() {
  try {
    state.principal = await api.get("/auth/me");
  } catch (err) {
    state.principal = null;
    if (err && err.status === 401 && state.token) {
      toast("err", "Anmeldung fehlgeschlagen", ["Token ung\u00FCltig \u2013 bitte erneut anmelden."]);
    }
  }
  renderUser();
  applyRoleNav();
}

// Ask the API which login UI to present (open/token/password). In password mode
// the SPA gates the whole app behind a login screen; the manual token field is
// hidden because the server issues session tokens via /auth/login.
async function loadAuthConfig() {
  try {
    const cfg = await api.get("/auth/config");
    state.authMode = cfg.mode || "open";
    state.passwordLogin = !!cfg.password_login;
  } catch (_e) {
    state.authMode = "open";
    state.passwordLogin = false;
  }
  const tokenField = byId("token-field");
  if (tokenField) tokenField.style.display = state.passwordLogin ? "none" : "";
}

function showOverlay(card) {
  const root = byId("auth-overlay");
  clear(root);
  root.appendChild(card);
  root.style.display = "grid";
}

function hideOverlay() {
  const root = byId("auth-overlay");
  clear(root);
  root.style.display = "none";
}

function authBrand(subtitle) {
  return el("div", { class: "auth-brand" },
    el("div", { class: "logo" }, "CbC"),
    el("div", {},
      el("h2", {}, "ProcWorks"),
      el("div", { class: "auth-hint" }, subtitle)));
}

// Full-screen login: exchange username + password for a session token, store it
// and continue booting. A forced password change is handled right after.
function showLoginOverlay() {
  const errBox = el("div", { class: "auth-err" });
  const loginInput = el("input", { type: "text", id: "login-name", autocomplete: "username", placeholder: "vorname.nachname" });
  const pwInput = el("input", { type: "password", id: "login-pw", autocomplete: "current-password", placeholder: "Passwort" });
  const submit = async (e) => {
    if (e) e.preventDefault();
    errBox.textContent = "";
    try {
      const res = await api.post("/auth/login", {
        login: loginInput.value.trim(),
        password: pwInput.value,
      });
      state.token = res.token;
      localStorage.setItem("authToken", state.token);
      if (res.must_change) {
        showChangePasswordOverlay(true);
      } else {
        hideOverlay();
        await boot();
      }
    } catch (err) {
      errBox.textContent = err && err.status === 401
        ? "Login oder Passwort ist falsch."
        : "Anmeldung fehlgeschlagen.";
    }
  };
  const form = el("form", { onSubmit: submit },
    el("label", { class: "field" }, "Login", loginInput),
    el("label", { class: "field" }, "Passwort", pwInput),
    errBox,
    el("button", { class: "btn primary", type: "submit" }, "Anmelden"));
  const card = el("div", { class: "auth-card" },
    authBrand("Bitte melden Sie sich an."), form,
    el("p", { class: "auth-disclaimer" },
      "Nutzung auf eigenes Risiko. ProcWorks wird ohne jede Gewährleistung und ",
      "ohne jede Haftung bereitgestellt – für keinerlei Schäden an Systemen, ",
      "Daten oder Prozessen. ",
      el("a", {
        href: "https://github.com/tobiasHaecker/procworks/blob/main/DISCLAIMER.md",
        target: "_blank", rel: "noopener",
      }, "Haftungsausschluss")));
  showOverlay(card);
  setTimeout(() => loginInput.focus(), 0);
}

// Forced (first login) or self-service password change. On success we have a
// usable session and boot the app.
function showChangePasswordOverlay(forced) {
  const errBox = el("div", { class: "auth-err" });
  const curInput = el("input", { type: "password", autocomplete: "current-password", placeholder: "Aktuelles Passwort" });
  const newInput = el("input", { type: "password", autocomplete: "new-password", placeholder: "Neues Passwort (min. 8 Zeichen)" });
  const repInput = el("input", { type: "password", autocomplete: "new-password", placeholder: "Neues Passwort wiederholen" });
  const submit = async (e) => {
    if (e) e.preventDefault();
    errBox.textContent = "";
    if (newInput.value !== repInput.value) {
      errBox.textContent = "Die Passw\u00F6rter stimmen nicht \u00FCberein.";
      return;
    }
    try {
      await api.post("/auth/change-password", {
        current_password: curInput.value,
        new_password: newInput.value,
      });
      hideOverlay();
      toast("ok", "Passwort ge\u00E4ndert", ["Sie sind jetzt angemeldet."]);
      await boot();
    } catch (err) {
      errBox.textContent = err && err.status === 400
        ? "Passwort zu kurz oder identisch mit dem alten."
        : (err && err.status === 401
          ? "Aktuelles Passwort ist falsch."
          : "\u00C4nderung fehlgeschlagen.");
    }
  };
  const subtitle = forced
    ? "Bitte vergeben Sie ein eigenes Passwort."
    : "Passwort \u00E4ndern.";
  const form = el("form", { onSubmit: submit },
    el("label", { class: "field" }, "Aktuelles Passwort", curInput),
    el("label", { class: "field" }, "Neues Passwort", newInput),
    el("label", { class: "field" }, "Wiederholen", repInput),
    errBox,
    el("button", { class: "btn primary", type: "submit" }, "Speichern"));
  const card = el("div", { class: "auth-card" }, authBrand(subtitle), form);
  showOverlay(card);
  setTimeout(() => curInput.focus(), 0);
}

// End the session server-side, drop the local token and return to the login.
async function logout() {
  try {
    await api.post("/auth/logout");
  } catch (_e) {
    // ignore: the token is dropped locally regardless.
  }
  state.token = "";
  state.principal = null;
  localStorage.removeItem("authToken");
  if (state.passwordLogin) showLoginOverlay();
  else await boot();
}


function renderUser() {
  const pill = byId("user-pill");
  const foot = byId("auth-user");
  const logoutBtn = byId("logout-btn");
  const p = state.principal;
  const bound = p && p.agent_id;
  const roles = (p && p.roles) || [];
  const roleText = roles.map((r) => ROLE_LABELS[r] || r).join(", ");
  const showLogout = state.passwordLogin && !!p;
  if (logoutBtn) logoutBtn.style.display = showLogout ? "" : "none";
  if (!p) {
    pill.textContent = "nicht angemeldet";
    pill.className = "pill pill-gray";
    foot.textContent = "Nicht angemeldet";
    return;
  }
  // Open dev mode: anonymous principal with all roles -> show "offen".
  const open = !bound && roles.length >= 4;
  pill.textContent = open ? "offen" : (p.display_name || p.subject);
  pill.className = "pill " + (open ? "pill-gray" : "pill-green");
  if (showLogout) {
    clear(foot);
    foot.appendChild(el("span", {}, `${p.display_name || p.subject} \u00B7 ${roleText || "ohne Rolle"}`));
    foot.appendChild(document.createTextNode(" \u00B7 "));
    foot.appendChild(el("a", {
      href: "#", onClick: (e) => { e.preventDefault(); showChangePasswordOverlay(false); },
    }, "Passwort \u00E4ndern"));
    return;
  }
  foot.textContent = open
    ? "Modus: offen (kein Login)"
    : `${p.display_name || p.subject} \u00B7 ${roleText || "ohne Rolle"}`;
}

// Hide nav entries the current role may not use and keep the active view valid.
function applyRoleNav() {
  const buttons = [...byId("nav").children];
  buttons.forEach((b) => {
    const allowed = VIEW_ROLES[b.dataset.view] || [];
    const visible = hasRole(...allowed);
    b.style.display = visible ? "" : "none";
  });
  const allowedNow = hasRole(...(VIEW_ROLES[state.view] || []));
  if (!allowedNow) {
    const first = buttons.find((b) => b.style.display !== "none");
    if (first) state.view = first.dataset.view;
  }
}

async function setToken(token) {
  state.token = token.trim();
  if (state.token) localStorage.setItem("authToken", state.token);
  else localStorage.removeItem("authToken");
  await boot();
}

function render() {
  // Guard against a stale/unknown persisted view (e.g. after a rename) so the
  // dispatch below never dereferences an undefined entry.
  if (!VIEW_META[state.view]) state.view = "model";
  // Remember the active view so a page reload restores it instead of always
  // falling back to "Modellieren".
  localStorage.setItem("view", state.view);
  const meta = VIEW_META[state.view];
  byId("view-title").textContent = meta.title;
  byId("view-sub").textContent = meta.sub;
  renderSchemaPicker();
  setActiveNav();
  Promise.resolve(meta.fn()).catch((err) => { const d = describeError(err); toast("err", d.title, d.lines); });
}

// --------------------------------------------------------------------------
// Live-Aktualisierung (Auto-Refresh der Laufzeit-Sichten)
// --------------------------------------------------------------------------

// Views that mirror runtime progress and should refresh automatically when an
// activity/instance advances anywhere (e.g. another user completes a task).
// Modelling views are intentionally excluded so editing is never interrupted.
const LIVE_VIEWS = new Set(["run", "tasks", "monitor"]);
const LIVE_POLL_MS = 4000;
let livePollBusy = false;

// True while the user is actively interacting (a modal/login overlay is open or
// the focus sits in a form field of the content area). Auto-refresh is skipped
// then so it never wipes an open dropdown or a half-filled form.
function userIsBusy() {
  if (byId("modal-root").children.length) return true;
  const overlay = byId("auth-overlay");
  if (overlay && overlay.style.display !== "none") return true;
  const active = document.activeElement;
  if (active && /^(INPUT|SELECT|TEXTAREA)$/.test(active.tagName)) {
    const content = byId("content");
    if (content && content.contains(active)) return true;
  }
  return false;
}

// Poll the cheap runtime-event revision; when it changed, refresh the current
// live view so task lists and monitoring follow progress without a manual
// reload. The "run" view caches the loaded instance, so reload it first.
async function pollLiveUpdates() {
  if (livePollBusy) return;
  if (state.passwordLogin && !state.principal) return;
  livePollBusy = true;
  try {
    const res = await api.get("/monitoring/revision");
    const rev = res && typeof res.revision === "number" ? res.revision : 0;
    if (rev === state.revision) return;
    state.revision = rev;
    if (!LIVE_VIEWS.has(state.view) || userIsBusy()) return;
    if (state.view === "run" && state.instanceId) {
      try { await loadInstance(state.instanceId); } catch (_e) { /* instance gone */ }
    }
    render();
  } catch (_e) {
    // Silent: a transient API hiccup must not spam toasts on a background poll.
  } finally {
    livePollBusy = false;
  }
}

// Start the background poll exactly once (boot may run repeatedly on re-login).
function startLiveUpdates() {
  if (startLiveUpdates._started) return;
  startLiveUpdates._started = true;
  setInterval(pollLiveUpdates, LIVE_POLL_MS);
}

function wireNav() {
  byId("nav").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-view]");
    if (!btn) return;
    state.view = btn.dataset.view;
    render();
  });
  const apiInput = byId("api-base");
  apiInput.value = state.apiBase;
  apiInput.addEventListener("change", async () => {
    state.apiBase = apiInput.value.trim() || defaultApiBase();
    localStorage.setItem("apiBase", state.apiBase);
    await boot();
  });
  const tokenInput = byId("auth-token");
  tokenInput.value = state.token;
  tokenInput.addEventListener("change", () => { setToken(tokenInput.value); });
  const logoutBtn = byId("logout-btn");
  if (logoutBtn) logoutBtn.addEventListener("click", () => { logout(); });
}

async function boot() {
  try {
    await api.get("/health");
    setConnected(true);
    await loadAuthConfig();
    // In password mode an unauthenticated visitor must log in first; the rest
    // of the app stays hidden behind the overlay until /auth/me succeeds.
    if (state.passwordLogin && !state.token) {
      showLoginOverlay();
      return;
    }
    await loadPrincipal();
    if (state.passwordLogin && !state.principal) {
      showLoginOverlay();
      return;
    }
    hideOverlay();
    await loadSchemas();
    await refreshSchema();
    // Baseline the live-update revision to "now" so the first poll only fires on
    // genuinely new progress, then start the background auto-refresh.
    try {
      const res = await api.get("/monitoring/revision");
      state.revision = res && typeof res.revision === "number" ? res.revision : 0;
    } catch (_e) { /* keep current baseline */ }
    startLiveUpdates();
  } catch (err) {
    setConnected(false);
    const d = describeError(err);
    toast("err", d.title, d.lines);
  }
  render();
}

wireNav();
boot();
