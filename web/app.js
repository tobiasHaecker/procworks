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
  // When a data/worker badge on a control-flow node is clicked, the target view
  // (data / resource) highlights and scrolls to that node's bindings. Mutually
  // exclusive; cleared on a manual nav click. Not persisted.
  dataFocusNode: null,
  staffFocusNode: null,
  // Resource view: clicking an org unit (in the org chart or the Abteilungen
  // tree) highlights that unit plus the agents that belong to it -- including
  // the unit's supervisor -- in the Agenten table. orgFocusUnit is the selected
  // unit id; orgFocusAgents lists the agent ids to emphasise. Not persisted.
  orgFocusUnit: null,
  orgFocusAgents: [],
  // Last seen runtime-event revision (GET /monitoring/revision). Drives the
  // live auto-refresh of the task/monitoring/run views; not persisted.
  revision: 0,
  // Last connection-test outcome per connector id (ok/err/unknown), shown as a
  // status badge in the integration view. Purely a UI hint; not persisted.
  connectorStatus: {},
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
// Domain events a webhook may subscribe to (mirrors outbox.WEBHOOK_EVENTS). The
// server validates the selection; this list only drives the checkbox picker.
const WEBHOOK_EVENT_TYPES = [
  "instance.started", "instance.completed", "task.ready", "task.completed", "task.incident",
];

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
    renderNodeBadges(root, schema, node, p, opts);
  });

  const wrap = el("div", { class: "canvas-wrap" }, root,
    el("div", { class: "canvas-hint" }, "Mausrad: Zoom \u00B7 Ziehen: Verschieben"));
  attachPanZoom(wrap, root);
  return wrap;
}

// Draw small "chips" straddling the bottom edge of an activity node that show
// whether it has data bindings and/or a worker (BZR) assignment. In the
// modelling control-flow view the chips are clickable and jump to the data /
// resource view with that node's bindings highlighted (opts.onOpenData /
// opts.onOpenStaff); elsewhere (e.g. the live process map) they are static
// indicators. Purely visual -- never touches the model or backend.
function renderNodeBadges(root, schema, node, p, opts) {
  if (node.type !== NODE_TYPE.ACTIVITY && node.type !== NODE_TYPE.SUBPROCESS) return;
  const accesses = (schema.data_accesses || []).filter((a) => a.node_id === node.id);
  const rule = (schema.staff_rules || {})[node.id];
  const chips = [];
  if (accesses.length) {
    const detail = accesses.map((a) => {
      const e = schema.data_elements[a.element_id];
      return (e ? e.name : a.element_id) + " (" + a.mode + ")";
    }).join(", ");
    chips.push({
      kind: "data",
      label: "Daten " + accesses.length,
      title: "Datenbindungen: " + detail + (opts.onOpenData ? "\u2002\u2013 klicken \u00F6ffnet die Datensicht" : ""),
      onClick: opts.onOpenData ? () => opts.onOpenData(node.id) : null,
    });
  }
  if (rule) {
    chips.push({
      kind: "staff",
      label: "Bearbeiter",
      title: describeRule(rule) + (opts.onOpenStaff ? "\u2002\u2013 klicken \u00F6ffnet die Bearbeiterzuordnung" : ""),
      onClick: opts.onOpenStaff ? () => opts.onOpenStaff(node.id) : null,
    });
  }
  if (!chips.length) return;
  const PADX = 7, GAP = 6, CH = 6;
  const widths = chips.map((c) => Math.round(c.label.length * CH) + PADX * 2);
  const total = widths.reduce((s, w) => s + w, 0) + GAP * (chips.length - 1);
  let cx = p.x + (p.w - total) / 2;
  const y = p.y + p.h - 8;
  chips.forEach((chip, i) => {
    const w = widths[i];
    const g = svg("g", {
      class: "gchip gchip-" + chip.kind + (chip.onClick ? " gchip-link" : ""),
      onClick: chip.onClick ? (e) => { e.stopPropagation(); chip.onClick(); } : null,
    });
    g.appendChild(svg("title", null, document.createTextNode(chip.title)));
    g.appendChild(svg("rect", { class: "gchip-bg", x: cx, y, width: w, height: 16, rx: 8 }));
    g.appendChild(svg("text", { class: "gchip-txt", x: cx + w / 2, y: y + 11, "text-anchor": "middle" },
      document.createTextNode(chip.label)));
    root.appendChild(g);
    cx += w + GAP;
  });
}

// Jump from a control-flow badge into the data / resource view with that node's
// bindings highlighted (and scrolled into view). The focus is mutually
// exclusive between the two views.
function focusBindingView(view, nodeId) {
  state.dataFocusNode = view === "data" ? nodeId : null;
  state.staffFocusNode = view === "org" ? nodeId : null;
  state.view = view;
  setActiveNav();
  render();
}

// Smoothly bring the first highlighted (.hl-row) table row of the current view
// into the centre of the viewport after a render.
function scrollHighlightIntoView() {
  requestAnimationFrame(() => {
    const row = byId("content").querySelector(".hl-row");
    if (row) row.scrollIntoView({ block: "center", behavior: "smooth" });
  });
}

// Dismissible banner shown above a highlighted binding table to explain why a
// row is emphasised and let the user clear the emphasis.
function focusBanner(text, onClear) {
  return el("div", { class: "focus-banner" },
    el("span", null, text),
    el("button", { class: "btn small ghost", onClick: onClear }, "Hervorhebung l\u00F6schen"));
}

// Highlight an organisational unit (in the Abteilungen tree and the org chart)
// together with every agent that belongs to it -- including the unit's
// supervisor (manager) -- in the Agenten table. Selecting a unit is a fresh
// resource-focus intent, so it clears any staff-rule highlight. Not persisted.
function focusOrgUnit(unitId) {
  const org = (state.schema && state.schema.org_model) || { agents: {}, org_units: {} };
  const unit = (org.org_units || {})[unitId];
  if (!unit) return;
  const ids = Object.values(org.agents || {})
    .filter((a) => a.org_unit_id === unitId)
    .map((a) => a.id);
  if (unit.manager_id && (org.agents || {})[unit.manager_id] && !ids.includes(unit.manager_id)) {
    ids.push(unit.manager_id);
  }
  state.orgFocusUnit = unitId;
  state.orgFocusAgents = ids;
  state.staffFocusNode = null;
  render();
}

// Highlight a single agent (a unit's supervisor) in the Agenten table -- used
// when the supervisor badge in the Abteilungen tree is clicked.
function focusOrgAgent(agentId, unitId) {
  const org = (state.schema && state.schema.org_model) || { agents: {} };
  if (!agentId || !(org.agents || {})[agentId]) return;
  state.orgFocusUnit = unitId || null;
  state.orgFocusAgents = [agentId];
  state.staffFocusNode = null;
  render();
}

// Make a rendered graph canvas pannable (drag in any direction) and zoomable
// (mouse wheel, anchored to the pointer position). Pan/zoom is purely visual
// (a CSS transform on the SVG) and resets on the next render -- it never
// touches the model or any backend state. The controller is exposed on
// ``wrap._panzoom`` so ``centerCanvasOnNode`` can re-centre the selected node.
function attachPanZoom(wrap, svgEl) {
  const MIN = 0.2, MAX = 4;
  let scale = 1, tx = 0, ty = 0;

  function apply() {
    svgEl.style.transformOrigin = "0 0";
    svgEl.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
  }
  apply();

  // Wheel = zoom towards / away from the pointer: keep the model point under
  // the cursor fixed while the scale changes.
  wrap.addEventListener("wheel", (e) => {
    e.preventDefault();
    const rect = wrap.getBoundingClientRect();
    const px = e.clientX - rect.left, py = e.clientY - rect.top;
    const cx = (px - tx) / scale, cy = (py - ty) / scale;
    const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
    const next = Math.min(MAX, Math.max(MIN, scale * factor));
    if (next === scale) return;
    scale = next;
    tx = px - cx * scale;
    ty = py - cy * scale;
    apply();
  }, { passive: false });

  // Drag = pan. Only capture the pointer once movement passes a small
  // threshold so a plain click still selects a node / hits a "+" handle.
  let down = false, dragging = false, sx = 0, sy = 0, lastX = 0, lastY = 0;
  wrap.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    down = true; dragging = false;
    sx = lastX = e.clientX; sy = lastY = e.clientY;
  });
  wrap.addEventListener("pointermove", (e) => {
    if (!down) return;
    if (!dragging && Math.abs(e.clientX - sx) + Math.abs(e.clientY - sy) < 4) return;
    if (!dragging) {
      dragging = true;
      wrap.classList.add("grabbing");
      try { wrap.setPointerCapture(e.pointerId); } catch (_e) { /* ignore */ }
    }
    tx += e.clientX - lastX; ty += e.clientY - lastY;
    lastX = e.clientX; lastY = e.clientY;
    apply();
  });
  function endDrag(e) {
    if (!down) return;
    down = false;
    if (dragging) {
      wrap.classList.remove("grabbing");
      try { wrap.releasePointerCapture(e.pointerId); } catch (_e) { /* ignore */ }
    }
  }
  wrap.addEventListener("pointerup", endDrag);
  wrap.addEventListener("pointercancel", endDrag);
  // Swallow the click that trails a real drag so panning never selects a node.
  wrap.addEventListener("click", (e) => {
    if (dragging) { e.stopPropagation(); e.preventDefault(); }
    dragging = false;
  }, true);

  wrap._panzoom = {
    centerOn(pos) {
      const cx = pos.x + pos.w / 2, cy = pos.y + pos.h / 2;
      tx = wrap.clientWidth / 2 - cx * scale;
      ty = wrap.clientHeight / 2 - cy * scale;
      apply();
    },
  };
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
    onOpenData: (id) => focusBindingView("data", id),
    onOpenStaff: (id) => focusBindingView("org", id),
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
  // ``wrap`` ist die .canvas-wrap; der Pan/Zoom-Controller verschiebt den
  // Knoten ueber eine CSS-Transformation in die Mitte des Viewports (statt
  // ueber nativen Scroll, der durch overflow:hidden entfaellt).
  if (wrap && wrap._panzoom) wrap._panzoom.centerOn(pos);
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
  function addParRow(val) {
    parBox.appendChild(el("input", { type: "text", class: "par-branch", placeholder: "Zweig-Bezeichnung", value: val || "" }));
  }
  // --- XOR partition builder (K7): a typed discriminator drives the branches.
  const partitionable = Object.values(state.schema.data_elements).filter(
    (d) => d.source === "INSTANCE" && ["INTEGER", "FLOAT", "BOOLEAN", "STRING"].includes(d.data_type));
  const condDisc = el("select", { class: "cond-disc" },
    ...partitionable.map((d) => el("option", { value: d.id }, `${d.name} (${d.data_type})`)));
  const condRows = el("div", { class: "row", style: "flex-direction:column;align-items:stretch;gap:8px" });
  function discKind() {
    const elem = state.schema.data_elements[condDisc.value];
    if (!elem) return null;
    if (elem.data_type === "INTEGER" || elem.data_type === "FLOAT") return "THRESHOLD";
    if (elem.data_type === "BOOLEAN") return "BOOLEAN";
    if (elem.data_type === "STRING") return "ENUM";
    return null;
  }
  function addThresholdRow(last) {
    condRows.appendChild(el("div", { class: "branch-row threshold-row" },
      el("input", { type: "text", class: "cond-label", placeholder: "Bezeichnung" }),
      el("input", { type: "number", class: "cond-upper", placeholder: last ? "Obergrenze leer = bis +\u221E" : "unter \u2026" })));
  }
  function addEnumRow() {
    condRows.appendChild(el("div", { class: "branch-row enum-row" },
      el("input", { type: "text", class: "cond-label", placeholder: "Bezeichnung" }),
      el("input", { type: "text", class: "cond-values", placeholder: "Werte, kommagetrennt" })));
  }
  function rebuildCondRows() {
    clear(condRows);
    const kind = discKind();
    if (kind === "THRESHOLD") { addThresholdRow(false); addThresholdRow(true); }
    else if (kind === "BOOLEAN") {
      condRows.appendChild(el("div", { class: "branch-row bool-row" },
        el("span", { class: "muted" }, "wahr (true)"),
        el("input", { type: "text", class: "cond-label", "data-bool": "true", placeholder: "Bezeichnung" })));
      condRows.appendChild(el("div", { class: "branch-row bool-row" },
        el("span", { class: "muted" }, "falsch (false)"),
        el("input", { type: "text", class: "cond-label", "data-bool": "false", placeholder: "Bezeichnung" })));
    } else if (kind === "ENUM") {
      addEnumRow(); addEnumRow();
      condRows.appendChild(el("div", { class: "branch-row else-row" },
        el("span", { class: "muted" }, "Sonst (otherwise)"),
        el("input", { type: "text", class: "cond-label", "data-else": "1", placeholder: "Bezeichnung" })));
    }
  }
  function addCondRow() {
    const kind = discKind();
    if (kind === "THRESHOLD") {
      const rows = condRows.querySelectorAll(".threshold-row");
      addThresholdRow(false);
      if (rows.length) condRows.insertBefore(condRows.lastChild, rows[rows.length - 1]);
    } else if (kind === "ENUM") {
      const elseRow = condRows.querySelector(".else-row");
      addEnumRow();
      if (elseRow) condRows.insertBefore(condRows.lastChild, elseRow);
    }
  }
  condDisc.addEventListener("change", rebuildCondRows);
  addParRow(); addParRow(); rebuildCondRows();
  const condPanel = partitionable.length
    ? el("div", null,
        el("label", { class: "field" }, "Diskriminator (Datenelement)", condDisc),
        el("div", { class: "muted", style: "font-size:12px;margin:4px 0" }, "Die Engine w\u00E4hlt den Zweig automatisch anhand des Werts \u2013 vollst\u00E4ndig und \u00FCberschneidungsfrei (K7)."),
        condRows, el("button", { class: "btn small ghost", onClick: () => addCondRow() }, "+ Zweig"))
    : el("div", { class: "muted", style: "font-size:13px" }, "Legen Sie zuerst ein Datenelement (INTEGER/FLOAT/BOOLEAN/STRING) an und lassen Sie es vor dieser Stelle schreiben.");
  const panels = {
    serial: serialBody,
    parallel: el("div", null, parBox, el("button", { class: "btn small ghost", onClick: () => addParRow() }, "+ Zweig")),
    conditional: condPanel,
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
        const kind = discKind();
        if (!kind) { toast("err", "Kein g\u00FCltiger Diskriminator gew\u00E4hlt"); return false; }
        let branches = [];
        if (kind === "THRESHOLD") {
          const rows = [...condRows.querySelectorAll(".threshold-row")].map((r) => ({
            label: r.querySelector(".cond-label").value.trim(),
            upperRaw: r.querySelector(".cond-upper").value.trim(),
          })).filter((b) => b.label);
          if (rows.length < 2) { toast("err", "Mindestens zwei Stufen n\u00F6tig"); return false; }
          const unbounded = rows.filter((b) => b.upperRaw === "");
          if (unbounded.length !== 1) { toast("err", "Genau eine Stufe muss ohne Obergrenze (bis +\u221E) sein"); return false; }
          const bounded = rows.filter((b) => b.upperRaw !== "")
            .map((b) => ({ label: b.label, upper: Number(b.upperRaw) }))
            .sort((a, b) => a.upper - b.upper);
          branches = [...bounded, { label: unbounded[0].label }];
        } else if (kind === "BOOLEAN") {
          branches = [...condRows.querySelectorAll(".cond-label")]
            .map((i) => ({ label: i.value.trim(), bool_value: i.dataset.bool === "true" }))
            .filter((b) => b.label);
          if (branches.length !== 2) { toast("err", "Beide F\u00E4lle (wahr/falsch) ben\u00F6tigen eine Bezeichnung"); return false; }
        } else {
          branches = [...condRows.children].map((r) => {
            const labelEl = r.querySelector(".cond-label");
            const valuesEl = r.querySelector(".cond-values");
            if (!labelEl || !labelEl.value.trim()) return null;
            if (labelEl.dataset.else) return { label: labelEl.value.trim(), is_else: true };
            const values = (valuesEl ? valuesEl.value : "").split(",").map((v) => v.trim()).filter(Boolean);
            if (!values.length) return null;
            return { label: labelEl.value.trim(), values };
          }).filter(Boolean);
          if (branches.length < 2) { toast("err", "Mindestens ein Wertzweig plus Sonst-Zweig n\u00F6tig"); return false; }
        }
        await api.post(`/schemas/${state.schemaId}/conditional-insert`, { after_node_id: afterNodeId, discriminator: condDisc.value, branches });
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
  const accList = schema.data_accesses || [];
  const accRows = accList.map((a) => {
    const node = schema.nodes[a.node_id];
    const elem = schema.data_elements[a.element_id];
    return [node ? nodeCaption(node) : a.node_id, elem ? elem.name : a.element_id, a.mode, a.mandatory ? "Pflicht" : "optional"];
  });
  const accTable = accRows.length
    ? table(["Schritt", "Element", "Modus", "Bindung"], accRows,
        (i) => accList[i].node_id === state.dataFocusNode ? "hl-row" : "")
    : emptyState("Noch keine Datenbindungen.");
  const addAccBtn = el("button", { class: "btn small", onClick: addDataAccess, disabled: !draft || activitiesOf(schema).length === 0 || elemRows.length === 0 }, "+ Datenbindung");
  const accPanel = el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Lese-/Schreibbindungen"), el("span", { class: "sub" }, "D1-D4 live gepr\u00FCft"), el("span", { class: "spacer", style: "flex:1" }), addAccBtn),
    el("div", { class: "panel-b" }, accTable));

  const dataFocus = state.dataFocusNode && schema.nodes[state.dataFocusNode];
  const rightCol = el("div", null,
    dataFocus
      ? focusBanner("Hervorgehoben: Bindungen von \u201E" + nodeCaption(dataFocus) + "\u201C",
          () => { state.dataFocusNode = null; render(); })
      : null,
    accPanel, dFindingsPanel());

  content.appendChild(el("div", { class: "grid-2" }, elemPanel, rightCol));
  scrollHighlightIntoView();
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
  const ruleEntries = Object.entries(schema.staff_rules || {});
  const ruleRows = ruleEntries.map(([nid, rule]) => {
    const node = schema.nodes[nid];
    return [node ? nodeCaption(node) : nid, describeRule(rule)];
  });
  const ruleTable = ruleRows.length
    ? table(["Schritt", "Bearbeiterregel"], ruleRows,
        (i) => ruleEntries[i][0] === state.staffFocusNode ? "hl-row" : "")
    : emptyState("Noch keine Bearbeiterzuordnung.");
  const addRuleBtn = el("button", { class: "btn small", onClick: addStaffRule,
    disabled: !draft || activitiesOf(schema).length === 0 || (Object.keys(org.roles || {}).length + Object.keys(org.org_units || {}).length) === 0 }, "+ Zuordnung");
  const rulePanel = el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Bearbeiterzuordnung (BZR)"), el("span", { class: "sub" }, "Z1-Z4 live"), el("span", { class: "spacer", style: "flex:1" }), addRuleBtn),
    el("div", { class: "panel-b" }, ruleTable));

  const staffFocus = state.staffFocusNode && schema.nodes[state.staffFocusNode];
  const orgFocusUnit = state.orgFocusUnit && (org.org_units || {})[state.orgFocusUnit];
  content.appendChild(el("div", { class: "grid-2" },
    el("div", null, orgPanel, rolePanel, unitPanel, agentPanel),
    el("div", null,
      staffFocus
        ? focusBanner("Hervorgehoben: Zuordnung von \u201E" + nodeCaption(staffFocus) + "\u201C",
            () => { state.staffFocusNode = null; render(); })
        : null,
      rulePanel, zFindingsPanel(),
      orgFocusUnit
        ? focusBanner("Hervorgehoben: Abteilung \u201E" + orgFocusUnit.name + "\u201C inkl. zugeh\u00F6riger Agenten",
            () => { state.orgFocusUnit = null; state.orgFocusAgents = []; render(); })
        : null,
      orgChartPanel(org))));
  scrollHighlightIntoView();
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
  const rowCls = "tree-row" + (unit.id === state.orgFocusUnit ? " tree-row-hl" : "");
  const row = el("div", { class: rowCls },
    el("span", { class: "tree-name" }, unit.name),
    mgr
      ? el("span", { class: "tree-badge tree-badge-link", title: "Vorgesetzten in der Agentenliste hervorheben",
          onClick: () => focusOrgAgent(unit.manager_id, unit.id) }, "\u2605 " + mgr)
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
    body.appendChild(table(["Agent", "Rollen", "Abteilung", "Vertreter", ""], rows,
      (i) => (state.orgFocusAgents || []).includes(agents[i].id) ? "hl-row" : ""));
  }
  return el("div", { class: "panel" }, head, body);
}

// Organigramm: the org-unit hierarchy rendered as a classic top-down org chart
// (HTML/CSS, no SVG). Clicking a box highlights that unit (in the chart and the
// Abteilungen tree) and every agent that belongs to it -- including the unit's
// supervisor -- in the Agenten table.
function orgChartPanel(org) {
  const units = Object.values(org.org_units || {});
  const head = el("div", { class: "panel-h" }, el("h2", null, "Organigramm"),
    el("span", { class: "sub" }, "Klick hebt Abteilung + Agenten hervor"));
  const body = el("div", { class: "panel-b" });
  if (!units.length) {
    body.appendChild(emptyState("Noch keine Abteilung modelliert."));
    return el("div", { class: "panel" }, head, body);
  }
  // Kinder je Elternknoten indexieren; verwaiste (unbekannter Parent) als Wurzel.
  const known = org.org_units || {};
  const childrenOf = {};
  units.forEach((u) => {
    const p = u.parent_id && known[u.parent_id] ? u.parent_id : "__root__";
    (childrenOf[p] = childrenOf[p] || []).push(u);
  });
  Object.values(childrenOf).forEach((list) => list.sort((a, b) => a.name.localeCompare(b.name)));
  const roots = childrenOf["__root__"] || [];
  body.appendChild(el("div", { class: "orgchart" },
    el("ul", null, ...roots.map((u) => orgChartNode(u, org, childrenOf)))));
  return el("div", { class: "panel" }, head, body);
}

function orgChartNode(unit, org, childrenOf) {
  const mgr = unit.manager_id && (org.agents || {})[unit.manager_id] ? org.agents[unit.manager_id].name : null;
  const memberCount = Object.values(org.agents || {}).filter((a) => a.org_unit_id === unit.id).length;
  const cls = "oc-node" + (unit.id === state.orgFocusUnit ? " selected" : "");
  const box = el("div", { class: cls, title: "Abteilung + zugeh\u00F6rige Agenten hervorheben",
    onClick: () => focusOrgUnit(unit.id) },
    el("div", { class: "oc-name" }, unit.name),
    mgr ? el("div", { class: "oc-mgr" }, "\u2605 " + mgr) : el("div", { class: "oc-mgr oc-muted" }, "kein Vorgesetzter"),
    el("div", { class: "oc-count" }, memberCount + (memberCount === 1 ? " Agent" : " Agenten")));
  const li = el("li", null, box);
  const kids = childrenOf[unit.id] || [];
  if (kids.length) li.appendChild(el("ul", null, ...kids.map((c) => orgChartNode(c, org, childrenOf))));
  return li;
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
    if (!(wl.ready_activities || []).length) {
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
    // Spaltenkopf: der Bearbeiter (Akteur) steht in einer eigenen Spalte.
    tl.appendChild(el("div", { class: "tl-item tl-head" },
      el("span", { class: "tl-time" }, "Zeit"),
      el("span", { class: "tl-type" }, "Ereignis"),
      el("span", { class: "tl-actor" }, "Bearbeiter"),
      el("span", { class: "tl-meta" }, "Detail")));
    events.forEach((ev) => {
      tl.appendChild(el("div", { class: "tl-item" },
        el("span", { class: "tl-time" }, fmtTimestamp(ev.timestamp)),
        el("span", { class: "tl-type" }, eventLabel(ev.event_type)),
        el("span", { class: "tl-actor" }, ev.agent_id ? agentNameOf(ev.agent_id) : "System"),
        el("span", { class: "tl-meta" }, ev.label || ev.node_id || "\u2013")));
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
      el("tr", { class: r.i.id === state.instanceId ? "clickable selected" : "clickable", onClick: () => openInstanceFromMonitor(r.i.id) }, ...r.cells.map((c) => el("td", null, c))))
      : [el("tr", null, el("td", { colspan: 4 }, emptyState("Keine Instanzen. Starte eine in der Ausf\u00FChrungs-Sicht.")))])));

  content.appendChild(el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Aktive Instanzen"), el("span", { class: "sub" }, "Klick \u00F6ffnet Detail")),
    el("div", { class: "panel-b" }, tbl)));

  // Detail der ausgewaehlten Instanz inkl. Live-Prozesslandkarte -- direkt unter
  // der Liste der aktiven Instanzen, damit der Bezug sofort sichtbar ist.
  if (state.instance) {
    const detail = el("div");
    // Schema der Instanz laden, damit der Graph passt
    if (state.instance.schema_id !== state.schemaId) {
      try { state.schema = await api.get(`/schemas/${state.instance.schema_id}`); } catch (e) { /* ignore */ }
    }
    await renderInstanceDetail(detail, true);
    content.appendChild(detail);
  }

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

  // Inzidente externer Aufgaben (Integrations-Konzept 11.5). Sichtbar fuer alle
  // Monitoring-Leser; "Erneut versuchen" (Aufloesen + Wiedereinreihen) ist nur
  // fuer Bearbeiter/Administratoren freigeschaltet (tasks:complete).
  let incidents = [];
  try { incidents = await api.get("/v1/incidents?unresolved_only=true"); }
  catch (e) { /* ignore: integration runtime may be disabled */ }
  const canResolve = hasRole("operator", "admin");
  const incBody = el("div", { class: "panel-b" });
  if (!incidents.length) {
    incBody.appendChild(el("div", { class: "ok-banner" }, "\u2713 Keine offenen Inzidente externer Aufgaben."));
  } else {
    const incRows = incidents.map((inc) => {
      const action = canResolve
        ? el("button", { class: "btn small green", onClick: () => resolveIncident(inc) }, "Erneut versuchen")
        : el("span", { class: "muted" }, "\u2013");
      return [inc.node_id, inc.message, fmtTimestamp(new Date(inc.created_at * 1000).toISOString()), action];
    });
    incBody.appendChild(table(["Schritt", "Fehler", "Zeit", ""], incRows));
  }
  content.appendChild(el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Inzidente (externe Aufgaben)"),
      el("span", { class: "sub" }, "Topic-Fehler \u00B7 Aufl\u00F6sen reiht die Aufgabe erneut ein")),
    incBody));

  // Wartung (Administrator): ganz unten, da selten benoetigt und destruktiv.
  // Nur Administratoren duerfen zuruecksetzen oder Beispieldaten laden
  // (POST /admin/reset).
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

// Inzident eines externen Tasks aufloesen (Aufgabe wird erneut eingereiht).
async function resolveIncident(inc) {
  try {
    await api.post(`/v1/incidents/${inc.id}/resolve`);
    render();
    toast("ok", "Inzident aufgel\u00F6st", ["Aufgabe erneut eingereiht."]);
  } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); }
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
// View: Integration (Integrations-Konzept Abschnitt 11 / Roadmap P5)
// --------------------------------------------------------------------------
//
// Wie der ganze Client traegt diese Sicht KEINE Korrektheitslogik: sie ruft
// nur gepruefte Endpunkte (Connectoren, Datenanbindung, Automatik, Webhooks).
// Validitaet ist eine Eigenschaft des Serverzustands; ungueltige Eingaben
// weist der Kern mit 422 ab und wir zeigen den Befund als Toast.

async function viewIntegration() {
  const content = byId("content");
  clear(content);
  // Connectoren + Webhooks parallel laden (unabhaengige Endpunkte).
  const [connPanel, hookPanel] = await Promise.all([
    connectorRegistryPanel(),
    webhookPanel(),
  ]);
  content.appendChild(connPanel);          // 11.1
  content.appendChild(dataBindingPanel()); // 11.2
  content.appendChild(automationPanel());  // 11.3
  content.appendChild(hookPanel);          // 11.4
}

// --- 11.1 Connector-Registry ----------------------------------------------

async function connectorRegistryPanel() {
  let connectors = [];
  try { connectors = await api.get("/v1/connectors"); }
  catch (err) { const d = describeError(err); toast("err", d.title, d.lines); }
  const rows = connectors.map((c) => {
    const st = state.connectorStatus[c.connector_id] || "unknown";
    const pill = el("span", { class: "pill " + (st === "ok" ? "pill-green" : st === "err" ? "pill-red" : "pill-gray") },
      st === "ok" ? "verbunden" : st === "err" ? "Fehler" : "ungepr\u00FCft");
    const testBtn = el("button", { class: "btn small", onClick: () => testConnector(c.connector_id) }, "Verbindung testen");
    const readBtn = el("button", { class: "btn small ghost", onClick: () => sampleReadConnector(c.connector_id) }, "Testlesen");
    return [c.connector_id, el("span", { class: "pill pill-blue" }, c.kind), pill,
      el("div", { class: "row-actions" }, testBtn, readBtn)];
  });
  const body = el("div", { class: "panel-b" },
    connectors.length
      ? table(["Connector", "Typ", "Status", ""], rows)
      : emptyState("Keine Connectoren konfiguriert. Connectoren werden serverseitig (admin-only) eingerichtet \u2013 Zugangsdaten bleiben dort, niemals im Modell."),
    el("p", { class: "muted", style: "margin-top:10px" },
      "Zugangsdaten werden nie angezeigt oder abgefragt. Die Modellierung referenziert nur eine serverseitig aufgel\u00F6ste Secret-Referenz."));
  return el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Connector-Registry"), el("span", { class: "sub" }, "Externe Datensysteme \u00B7 nur Metadaten")),
    body);
}

async function testConnector(id) {
  try {
    const res = await api.post(`/v1/connectors/${id}/test`);
    state.connectorStatus[id] = res.ok ? "ok" : "err";
    toast(res.ok ? "ok" : "err", res.ok ? "Verbindung ok" : "Verbindung fehlgeschlagen", [id]);
  } catch (err) {
    state.connectorStatus[id] = "err";
    const d = describeError(err); toast("err", d.title, d.lines);
  }
  render();
}

function sampleReadConnector(id) {
  const entity = el("input", { type: "text", placeholder: "z. B. Kunde" });
  const limit = el("input", { type: "number", value: "1", min: "1", max: "100" });
  openModal("Testlesen \u2013 " + id, el("div", { class: "form-grid" },
    el("label", { class: "field" }, "Entit\u00E4t/Tabelle", entity),
    el("label", { class: "field" }, "Anzahl", limit)), async () => {
    if (!entity.value.trim()) return false;
    try {
      const rows = await api.post(`/v1/connectors/${id}/sample-read`,
        { entity: entity.value.trim(), limit: Number(limit.value) || 1 });
      showSampleRecords(entity.value.trim(), rows);
    } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Lesen");
}

function showSampleRecords(entity, rows) {
  const pre = el("pre", { class: "code-block" }, JSON.stringify(rows, null, 2));
  openModal(`Beispieldatensatz: ${entity} (${rows.length})`, pre, async () => true, "Schlie\u00DFen");
}

// --- 11.2 Datenanbindungs-Assistent ---------------------------------------

function elemName(schema, id) {
  const e = schema.data_elements[id];
  return e ? e.name : id;
}

function dataBindingPanel() {
  const head = el("div", { class: "panel-h" },
    el("h2", null, "Datenanbindung (extern)"),
    el("span", { class: "sub" }, "Datenelemente an Connectoren binden (C1\u2013C3)"));
  if (!state.schema) {
    return el("div", { class: "panel" }, head,
      el("div", { class: "panel-b" }, emptyState("Kein Schema ausgew\u00E4hlt \u2013 oben ein Schema w\u00E4hlen.")));
  }
  const schema = state.schema;
  const draft = isDraft(schema);

  // Modell-Connectoren (Metadaten im Schema, getrennt von der Laufzeit-Registry).
  const connRows = Object.values(schema.connectors || {}).map((c) =>
    [c.name, el("span", { class: "pill pill-blue" }, c.kind), c.id]);
  const addConnBtn = el("button", { class: "btn small", onClick: registerSchemaConnector, disabled: !draft }, "+ Connector");
  const connBlock = el("div", null,
    el("div", { class: "sub-h" }, el("h3", null, "Modell-Connectoren"), el("span", { class: "spacer", style: "flex:1" }), addConnBtn),
    connRows.length ? table(["Name", "Typ", "ID"], connRows)
      : emptyState("Noch keine Connectoren im Modell registriert."));

  // Datenelemente + externe Bindung.
  const hasConn = Object.keys(schema.connectors || {}).length > 0;
  const elemRows = Object.values(schema.data_elements).map((d) => {
    const src = d.source === "EXTERNAL"
      ? el("span", { class: "pill pill-amber" }, "EXTERN")
      : el("span", { class: "pill pill-gray" }, "Instanz");
    const detail = d.external
      ? `${d.external.connector_id} \u00B7 ${d.external.entity} \u00B7 Schl\u00FCssel ${elemName(schema, d.external.key_element_id)}`
      : "\u2013";
    const bindBtn = el("button", { class: "btn small ghost", onClick: () => bindExternalElement(d), disabled: !draft || !hasConn }, "Extern anbinden");
    return [d.name, d.data_type, src, detail, bindBtn];
  });
  const elemBlock = el("div", null,
    el("div", { class: "sub-h" }, el("h3", null, "Datenelemente")),
    elemRows.length ? table(["Element", "Typ", "Quelle", "Abbildung", ""], elemRows)
      : emptyState("Noch keine Datenelemente. Lege sie in der Datensicht an."));

  return el("div", { class: "panel" }, head,
    el("div", { class: "panel-b" }, connBlock, el("div", { style: "height:14px" }), elemBlock,
      el("p", { class: "muted", style: "margin-top:10px" },
        "Lese-/Schreib-Richtung (D/C) wird \u00FCber die Bindungen in der Datensicht festgelegt.")));
}

function registerSchemaConnector() {
  const name = el("input", { type: "text", placeholder: "z. B. ERP-Kunden" });
  const kind = el("select", null, ...CONNECTOR_KINDS.map((k) => el("option", { value: k }, k)));
  const cid = el("input", { type: "text", placeholder: "optionale ID, z. B. erp" });
  openModal("Connector registrieren", el("div", { class: "form-grid" },
    el("label", { class: "field" }, "Name", name),
    el("label", { class: "field" }, "Typ", kind),
    el("label", { class: "field" }, "ID (optional)", cid)), async () => {
    if (!name.value.trim()) return false;
    try {
      await api.post(`/schemas/${state.schemaId}/connectors`,
        { name: name.value.trim(), kind: kind.value, connector_id: cid.value.trim() || null });
      await refreshSchema(); render(); toast("ok", "Connector registriert");
    } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Registrieren");
}

function bindExternalElement(element) {
  const schema = state.schema;
  const conn = el("select", null, ...Object.values(schema.connectors || {}).map((c) =>
    el("option", { value: c.id }, `${c.name} (${c.id})`)));
  const entity = el("input", { type: "text", placeholder: "z. B. Kunde" });
  const keyElems = Object.values(schema.data_elements).filter((d) => d.source !== "EXTERNAL" && d.id !== element.id);
  const key = el("select", null, ...keyElems.map((d) => el("option", { value: d.id }, d.name)));
  const body = el("div", { class: "form-grid" },
    el("label", { class: "field" }, "Connector", conn),
    el("label", { class: "field" }, "Entit\u00E4t/Tabelle", entity),
    el("label", { class: "field" }, "Schl\u00FCssel-Datenelement", keyElems.length
      ? key
      : el("span", { class: "muted" }, "Erst ein Instanz-Datenelement anlegen.")));
  openModal(`Extern anbinden \u2013 ${element.name}`, body, async () => {
    if (!entity.value.trim() || !conn.value || !keyElems.length) return false;
    try {
      await api.post(`/schemas/${state.schemaId}/data-elements/${element.id}/external`,
        { connector_id: conn.value, entity: entity.value.trim(), key_element_id: key.value });
      await refreshSchema(); render(); toast("ok", "Datenelement extern angebunden");
    } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Anbinden");
}

// --- 11.3 Automatik-Schritt-Binding ---------------------------------------

function automationPanel() {
  const head = el("div", { class: "panel-h" },
    el("h2", null, "Automatik-Schritte"),
    el("span", { class: "sub" }, "Person / Automatisch (External-Task \u00B7 HTTP-Push)"));
  if (!state.schema) {
    return el("div", { class: "panel" }, head,
      el("div", { class: "panel-b" }, emptyState("Kein Schema ausgew\u00E4hlt.")));
  }
  const schema = state.schema;
  const draft = isDraft(schema);
  const acts = activitiesOf(schema);
  const rows = acts.map((n) => {
    const sb = (schema.service_bindings || {})[n.id];
    const auto = sb ? sb.automation : "MANUAL_NONE";
    const detail = auto === "EXTERNAL_TASK" ? `External-Task \u00B7 Topic ${sb.topic || "?"}`
      : auto === "HTTP_PUSH" ? `HTTP-Push \u00B7 ${sb.endpoint_ref || "?"}`
      : "Person / manuell";
    const pill = el("span", { class: "pill " + (auto === "MANUAL_NONE" ? "pill-gray" : "pill-green") },
      auto === "MANUAL_NONE" ? "manuell" : "automatisch");
    const btn = sb
      ? el("button", { class: "btn small", onClick: () => editAutomation(n, sb), disabled: !draft }, "Bearbeitung w\u00E4hlen")
      : el("span", { class: "muted" }, "erst Dienst zuweisen");
    return [nodeCaption(n), pill, detail, btn];
  });
  const body = el("div", { class: "panel-b" },
    acts.length ? table(["Aktivit\u00E4t", "Modus", "Anbindung", ""], rows)
      : emptyState("Keine Aktivit\u00E4ten im Schema."));
  return el("div", { class: "panel" }, head, body);
}

function editAutomation(node, sb) {
  const kindSel = el("select", null,
    el("option", { value: "MANUAL_NONE" }, "Person / manuell"),
    el("option", { value: "EXTERNAL_TASK" }, "Automatisch \u00B7 External-Task (Topic)"),
    el("option", { value: "HTTP_PUSH" }, "Automatisch \u00B7 HTTP-Push (Ziel)"));
  kindSel.value = sb.automation || "MANUAL_NONE";
  const topic = el("input", { type: "text", placeholder: "z. B. invoice-check", value: sb.topic || "" });
  const endpoint = el("input", { type: "text", placeholder: "z. B. webhook_1", value: sb.endpoint_ref || "" });
  const retryMax = el("input", { type: "number", min: "0", value: String(sb.retry_max != null ? sb.retry_max : 5) });
  const backoff = el("input", { type: "number", min: "0", value: String(sb.retry_backoff_ms != null ? sb.retry_backoff_ms : 2000) });
  const timeout = el("input", { type: "number", min: "0", value: String(sb.request_timeout_ms != null ? sb.request_timeout_ms : 30000) });
  const topicField = el("label", { class: "field" }, "Topic", topic);
  const endpointField = el("label", { class: "field" }, "Endpunkt-Referenz", endpoint);
  const advanced = el("details", { class: "adv-block" }, el("summary", null, "Erweitert (Robustheit)"),
    el("div", { class: "form-grid" },
      el("label", { class: "field" }, "Max. Versuche", retryMax),
      el("label", { class: "field" }, "Backoff (ms)", backoff),
      el("label", { class: "field" }, "Timeout (ms)", timeout)));
  const syncFields = () => {
    const k = kindSel.value;
    topicField.style.display = k === "EXTERNAL_TASK" ? "" : "none";
    endpointField.style.display = k === "HTTP_PUSH" ? "" : "none";
    advanced.style.display = k === "MANUAL_NONE" ? "none" : "";
  };
  kindSel.addEventListener("change", syncFields);
  const body = el("div", { class: "form-grid" },
    el("label", { class: "field" }, "Bearbeitung", kindSel), topicField, endpointField, advanced);
  syncFields();
  openModal(`Automatik \u2013 ${nodeCaption(node)}`, body, async () => {
    const k = kindSel.value;
    const req = { node_id: node.id, automation: k };
    if (k === "EXTERNAL_TASK") { if (!topic.value.trim()) return false; req.topic = topic.value.trim(); }
    if (k === "HTTP_PUSH") { if (!endpoint.value.trim()) return false; req.endpoint_ref = endpoint.value.trim(); }
    if (k !== "MANUAL_NONE") {
      req.retry_max = Number(retryMax.value);
      req.retry_backoff_ms = Number(backoff.value);
      req.request_timeout_ms = Number(timeout.value);
    }
    try {
      await api.post(`/schemas/${state.schemaId}/automation`, req);
      await refreshSchema(); render(); toast("ok", "Automatik gesetzt");
    } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "\u00DCbernehmen");
}

// --- 11.4 Webhook-/Ereignis-Panel -----------------------------------------

async function webhookPanel() {
  let subs = [];
  try { subs = await api.get("/v1/webhooks"); }
  catch (err) { const d = describeError(err); toast("err", d.title, d.lines); }
  const rows = subs.map((s) => {
    const events = (s.events || []).join(", ");
    const test = el("button", { class: "btn small", onClick: () => testWebhook(s.id) }, "Testzustellung");
    const log = el("button", { class: "btn small ghost", onClick: () => showDeliveries(s.id) }, "Protokoll");
    const del = el("button", { class: "btn small danger", onClick: () => deleteWebhook(s) }, "L\u00F6schen");
    return [s.url, events, s.secret_ref || "\u2013", el("div", { class: "row-actions" }, test, log, del)];
  });
  const addBtn = el("button", { class: "btn small", onClick: addWebhook }, "+ Abonnement");
  const body = el("div", { class: "panel-b" },
    subs.length ? table(["Ziel-URL", "Ereignisse", "Secret-Ref", ""], rows)
      : emptyState("Noch keine Webhook-Abonnements."));
  return el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Webhooks / Ereignisse"), el("span", { class: "spacer", style: "flex:1" }), addBtn),
    body);
}

function addWebhook() {
  const url = el("input", { type: "url", placeholder: "https://hooks.example.com/procworks" });
  const secret = el("input", { type: "text", placeholder: "z. B. WEBHOOK_SECRET (optional)" });
  const checks = WEBHOOK_EVENT_TYPES.map((ev) => {
    const cb = el("input", { type: "checkbox", value: ev });
    return { cb, row: el("label", { class: "check-row" }, cb, " " + ev) };
  });
  const body = el("div", { class: "form-grid" },
    el("label", { class: "field" }, "Ziel-URL", url),
    el("label", { class: "field" }, "Secret-Referenz (Servername, optional)", secret),
    el("div", { class: "field" }, el("span", null, "Ereignisse"),
      el("div", { class: "check-list" }, ...checks.map((c) => c.row))));
  openModal("Webhook-Abonnement", body, async () => {
    const events = checks.filter((c) => c.cb.checked).map((c) => c.cb.value);
    if (!url.value.trim() || !events.length) return false;
    try {
      await api.post("/v1/webhooks", { url: url.value.trim(), events, secret_ref: secret.value.trim() });
      render(); toast("ok", "Webhook angelegt");
    } catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "Anlegen");
}

async function testWebhook(id) {
  try {
    const d = await api.post(`/v1/webhooks/${id}/test`);
    const detail = d.status_code != null ? "HTTP " + d.status_code : (d.error || "");
    toast(d.ok ? "ok" : "err", d.ok ? "Testzustellung erfolgreich" : "Testzustellung fehlgeschlagen", detail ? [detail] : []);
  } catch (err) { const e = describeError(err); toast("err", e.title, e.lines); }
}

async function showDeliveries(id) {
  let deliveries = [];
  try { deliveries = await api.get(`/v1/webhooks/${id}/deliveries`); }
  catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return; }
  const rows = deliveries.map((d) => [
    fmtTimestamp(new Date(d.at * 1000).toISOString()),
    d.event_type, String(d.attempt),
    d.ok ? el("span", { class: "pill pill-green" }, "ok") : el("span", { class: "pill pill-red" }, "Fehler"),
    d.status_code != null ? "HTTP " + d.status_code : (d.error || "\u2013"),
  ]);
  const body = rows.length ? table(["Zeit", "Ereignis", "Versuch", "Status", "Detail"], rows)
    : emptyState("Noch keine Zustellungen.");
  openModal("Zustellprotokoll", body, async () => true, "Schlie\u00DFen");
}

function deleteWebhook(sub) {
  openModal("Webhook l\u00F6schen", el("p", { class: "muted" }, `Abonnement f\u00FCr ${sub.url} entfernen?`), async () => {
    try { await api.del(`/v1/webhooks/${sub.id}`); render(); toast("ok", "Webhook gel\u00F6scht"); }
    catch (err) { const d = describeError(err); toast("err", d.title, d.lines); return false; }
  }, "L\u00F6schen");
}

// --------------------------------------------------------------------------
// Wiederverwendbare UI-Bausteine
// --------------------------------------------------------------------------

function emptyState(text) { return el("div", { class: "empty" }, text); }
function kpi(label, value) { return el("div", { class: "kpi" }, el("div", { class: "label" }, label), el("div", { class: "value" }, String(value))); }

function table(headers, rows, rowClassFn) {
  return el("table", null,
    el("thead", null, el("tr", null, ...headers.map((h) => el("th", null, h)))),
    el("tbody", null, ...rows.map((r, i) => el("tr", rowClassFn ? { class: rowClassFn(i) || null } : null, ...r.map((c) =>
      el("td", null, c instanceof Node ? c : String(c)))))));
}

function listPanel(title, headers, rows, onAdd, addLabel) {
  const head = el("div", { class: "panel-h" }, el("h2", null, title), el("span", { class: "spacer", style: "flex:1" }),
    onAdd ? el("button", { class: "btn small", onClick: onAdd }, addLabel) : null);
  return el("div", { class: "panel" }, head, el("div", { class: "panel-b" }, rows.length ? table(headers, rows) : emptyState("Noch nichts angelegt.")));
}

// --------------------------------------------------------------------------
// View: Hilfe (kontextsensitive In-App-Hilfe + Glossar der Regel-Codes)
// --------------------------------------------------------------------------

// Documentation lives in the repository; link to the GitHub blobs so the help
// works even when served as a static client without local file access.
const DOCS_BASE = "https://github.com/tobiasHaecker/procworks/blob/main/docs/";

// Short purpose of each navigation view (mirrors VIEW_META plus a one-liner of
// what the user actually does there).
const HELP_VIEWS = [
  ["\u25A3 Modellieren", "Schritte \u00FCber \u201E+\u201C einf\u00FCgen (seriell / parallel / bedingt), umbenennen, entfernen, Befunde pr\u00FCfen, freigeben."],
  ["\u2630 Datensicht", "Datenelemente anlegen und je Aktivit\u00E4t Lesen/Schreiben verbinden (Datenfluss D)."],
  ["\u265F Ressourcensicht", "Organisation (Rollen, Einheiten, Agenten) und Bearbeiterregeln je Schritt (Z/A)."],
  ["\u25B6 Ausf\u00FChrung", "Instanzen starten, Arbeitsliste abarbeiten, XOR-Zweige w\u00E4hlen. Modellierer starten Entw\u00FCrfe als Test-Instanz."],
  ["\u2630 Meine Aufgaben", "Pers\u00F6nliche Arbeitsliste \u2013 Aufgaben mit \u201EErledigen\u201C abschlie\u00DFen."],
  ["\u2609 Monitoring", "Live-Status aktiver Instanzen, Prozesslandkarte, Inzidente, Wartung (Administrator)."],
  ["\u21C4 Integration", "Connectoren, externe Datenbindung, Automatik (External-Task / HTTP-Push), Webhooks."],
];

// Role-oriented quick starts: each entry points at the matching how-to doc.
const HELP_QUICKSTART = [
  ["Modellierer", "Prozess erstellen, Daten/Bearbeiter verdrahten, testen, freigeben.", "Modellierer-Anleitung.md"],
  ["Sachbearbeiter", "Anmelden, eigene Aufgaben sehen und erledigen.", "Mitarbeiter-Anleitung.md"],
  ["Administrator", "Installation, Logins, Betrieb (Update/Backup), Beispieldaten.", "Windows-Server-Setup.md"],
  ["Integrator", "Fremdsysteme \u00FCber die offene /v1-Schnittstelle anbinden.", "Integrations-Leitfaden.md"],
];

// Glossary of the correctness rule codes that surface in the findings list and
// error toasts. Grouped by family so a user can look up exactly what e.g. "D1"
// or "B2" means. Kept in sync with validator.py and Architektur-Konzept §3.
const HELP_RULES = [
  ["Struktur & Kontrollfluss (K)", [
    ["K1", "Blockstruktur: jeder Split hat genau einen passenden Join desselben Typs."],
    ["K2", "Genau ein START und ein END; jede Aktivit\u00E4t hat genau eine Ein- und Ausgangskante."],
    ["K3", "Erreichbarkeit: kein isolierter Knoten, keine Sackgasse \u2013 alles liegt auf START\u2192END."],
    ["K4", "Sync-Kanten nur zwischen Aktivit\u00E4ten verschiedener UND-Zweige."],
    ["K5", "Soundness: jeder Zustand kann ordentlich zum Ende gelangen."],
    ["K6", "Strukturierte Schleifen (REPEAT-UNTIL mit definierter Abbruchbedingung)."],
    ["K7", "XOR-Pr\u00E4dikate decken den Wertebereich vollst\u00E4ndig und \u00FCberlappungsfrei ab."],
  ]],
  ["Datenfluss (D)", [
    ["D1", "Pflicht-Eingaben sind auf ALLEN Pfaden vor dem Lesen geschrieben."],
    ["D2", "Keine konkurrierenden Schreibzugriffe paralleler Zweige auf dasselbe Element."],
    ["D3", "Typkonformit\u00E4t von Quelle und Senke."],
    ["D4", "Optionale Eingaben d\u00FCrfen unversorgt bleiben; Join-Knoten tragen keine Daten."],
    ["D5", "Datenfluss wird live gepr\u00FCft und muss vor Freigabe sauber sein."],
  ]],
  ["Externe Datenbindung (C)", [
    ["C1", "EXTERNE Elemente brauchen eine g\u00FCltige Connector-Bindung; INSTANCE-Elemente keine."],
    ["C2", "Das Schl\u00FCsselelement der Bindung ist ein existierendes INSTANCE-Element (nicht es selbst)."],
    ["C3", "Der gebundene Entit\u00E4tsname ist nicht leer."],
  ]],
  ["Bearbeiter / Ressourcen (Z, A)", [
    ["Z1", "Bearbeiterregel ist syntaktisch g\u00FCltig und referenziert existierende Rollen/Einheiten."],
    ["Z2", "Die Regel ist erf\u00FCllbar \u2013 sie liefert mindestens einen Agenten."],
    ["Z3", "NodePerformingAgent(\u2026) verweist nur auf garantiert vorher laufende Schritte."],
    ["Z4", "Interaktive Schritte brauchen eine Bearbeiterregel; automatische nicht."],
    ["A1\u2013A3", "Zugeordneter Dienst (Template) ist vorhanden und typkonform an die Daten gebunden."],
  ]],
  ["Integration / Automatik (I)", [
    ["I1", "Automatik wohlgeformt: External-Task braucht Topic, HTTP-Push eine Endpunkt-Referenz."],
    ["I2", "Genau ein Automatik-Muster; automatisierte Bindung ist als automatisch markiert."],
    ["I3", "Parameter-Mapping zeigt auf existierende Datenelemente."],
    ["I4", "Topic/Endpunkt enthalten keine Inline-URL oder Zugangsdaten."],
  ]],
  ["Komposition (H, F)", [
    ["H1\u2013H4", "Sub-Prozesse: nur freigegebene, gepinnte Version; typkonforme Schnittstelle; zyklenfrei."],
    ["F1\u2013F3", "Folgeprozesse: Ziel existiert freigegeben; typkonformes Handover; lose Kopplung bei ASYNC."],
  ]],
  ["Zeit & Release (T, B)", [
    ["T1\u2013T2", "Fristen/Dauern wohldefiniert und entlang der Blockstruktur widerspruchsfrei."],
    ["B1", "Release-Reife: jeder Schritt hat einen ausf\u00FChrbaren Dienst."],
    ["B2", "Release-Reife: jeder interaktive Schritt hat eine Bearbeiterzuordnung."],
    ["B3", "Release-Reife: alle Pflichtdaten sind gebunden, alle Pr\u00E4dikate spezifiziert."],
  ]],
  ["Laufzeit & Migration (R, M)", [
    ["R0", "Nur Entw\u00FCrfe sind editierbar; freigegebene Schemata sind unver\u00E4nderlich."],
    ["R1\u2013R2", "Ad-hoc-\u00C4nderungen nur zustandsvertr\u00E4glich und unter Erhalt aller K/D-Regeln."],
    ["M1\u2013M5", "Migration nur, wenn Ziel korrekt ist und der bisherige Verlauf vertr\u00E4glich bleibt."],
  ]],
  ["Modellhinweise (G, 7PMG)", [
    ["G1", "Hinweis: sehr gro\u00DFes Modell (>50 Knoten) \u2013 ggf. in Sub-Prozesse zerlegen."],
    ["G2", "Hinweis: hoher Gateway-Grad \u2013 Verzweigung vereinfachen."],
    ["G6", "Hinweis: hohe Verschachtelungstiefe (>5)."],
    ["G7", "Hinweis: Aktivit\u00E4t ohne sprechenden Namen."],
  ]],
];

function viewHelp() {
  const content = byId("content");
  clear(content);

  // Intro / principle.
  content.appendChild(el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "ProcWorks \u2013 Hilfe")),
    el("div", { class: "panel-b" },
      el("p", { class: "muted" },
        "ProcWorks h\u00E4lt jedes Modell \u201Ekorrekt per Konstruktion\u201C: Das Werkzeug ",
        "bietet nur Operationen an, die das Modell g\u00FCltig halten. Einen ",
        "\u201EValidieren\u201C-Knopf gibt es bewusst nicht \u2013 was noch zur Ausf\u00FChrbarkeit ",
        "fehlt, zeigt die Befunde-Liste laufend an."))));

  // The seven views.
  content.appendChild(el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Die Sichten im \u00DCberblick")),
    el("div", { class: "panel-b" },
      table(["Sicht", "Wof\u00FCr"], HELP_VIEWS.map(([n, d]) => [n, d])))));

  // Role-oriented quick starts with deep links to the how-to docs.
  content.appendChild(el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Schnellstart je Rolle")),
    el("div", { class: "panel-b" },
      table(["Rolle", "Ziel", "Anleitung"], HELP_QUICKSTART.map(([role, goal, doc]) => [
        role, goal,
        el("a", { href: DOCS_BASE + doc, target: "_blank", rel: "noopener" }, doc),
      ])))));

  // Glossary of rule codes, grouped by family.
  const glossary = el("div", { class: "panel-b" });
  for (const [group, rules] of HELP_RULES) {
    glossary.appendChild(el("div", { class: "sub-h" }, el("h3", null, group)));
    glossary.appendChild(table(["Code", "Bedeutung"], rules.map(([c, m]) => [
      el("span", { class: "pill pill-gray" }, c), m,
    ])));
  }
  content.appendChild(el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Glossar der Regel-Codes"),
      el("span", { class: "spacer", style: "flex:1" }),
      el("span", { class: "muted", style: "font-size:12px" }, "erscheinen in Befunden & Fehlermeldungen")),
    glossary));

  // Further reading.
  content.appendChild(el("div", { class: "panel" },
    el("div", { class: "panel-h" }, el("h2", null, "Weiterf\u00FChrend")),
    el("div", { class: "panel-b" },
      el("ul", { style: "margin:4px 0;padding-left:18px;line-height:1.7" },
        el("li", null, el("a", { href: DOCS_BASE + "README.md", target: "_blank", rel: "noopener" }, "Dokumentations-\u00DCbersicht (nach Rolle)")),
        el("li", null, el("a", { href: DOCS_BASE + "Architektur-Konzept-Prozessmodellierung.md", target: "_blank", rel: "noopener" }, "Architektur-Konzept (Korrektheitskriterien, \u00A73)")),
        el("li", null, el("a", { href: "https://github.com/tobiasHaecker/procworks/blob/main/DISCLAIMER.md", target: "_blank", rel: "noopener" }, "Haftungsausschluss"))))));
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
  integration: { title: "Integration", sub: "Connectoren, Datenanbindung, Automatik & Webhooks", fn: viewIntegration },
  help: { title: "Hilfe", sub: "Sichten, Schnellstart je Rolle & Glossar der Regel-Codes", fn: viewHelp },
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
  integration: ["modeler", "admin"],
  help: ["viewer", "operator", "modeler", "admin"],
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
    // A direct nav click is a fresh intent -- drop any badge-driven highlight.
    state.dataFocusNode = null;
    state.staffFocusNode = null;
    state.orgFocusUnit = null;
    state.orgFocusAgents = [];
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
