const SVG_NS = "http://www.w3.org/2000/svg";
const DEFAULT_CONDITIONS = [];

const state = {
  data: null,
  nodes: new Map(),
  layer: "all",
  origin: "grace_avenue_balcony",
  destination: "item_bolt_of_gransax",
  conditions: new Set(DEFAULT_CONDITIONS),
  preference: "balanced",
  zoom: 1,
  route: null,
  selectedNode: "gatefront",
};

const els = {
  origin: document.getElementById("origin-select"),
  destination: document.getElementById("destination-select"),
  conditions: document.getElementById("conditions"),
  plan: document.getElementById("plan-route"),
  reset: document.getElementById("reset-route"),
  preferenceHint: document.getElementById("preference-hint"),
  graphStats: document.getElementById("graph-stats"),
  datasetVersion: document.getElementById("dataset-version"),
  loading: document.getElementById("loading-state"),
  edgeLayer: document.getElementById("edge-layer"),
  nodeLayer: document.getElementById("node-layer"),
  regionLabels: document.getElementById("region-labels"),
  routeSummary: document.getElementById("route-summary"),
  routeContent: document.getElementById("route-content"),
  routeTitle: document.getElementById("route-title"),
  routeTime: document.getElementById("route-time"),
  routeRisk: document.getElementById("route-risk"),
  routeHops: document.getElementById("route-hops"),
  pathTrack: document.getElementById("path-track"),
  routeNotice: document.getElementById("route-notice"),
  nodeInspector: document.getElementById("node-inspector"),
  mapToast: document.getElementById("map-toast"),
  mapTransform: document.getElementById("map-transform"),
  copyRoute: document.getElementById("copy-route"),
};

const preferenceHints = {
  balanced: "综合时间与风险，适合首次探索。",
  fast: "优先较短时间，允许承担更高落差和战斗风险。",
  safe: "显著回避高风险跳落，可能增加路线长度。",
};

function svg(tag, attrs = {}) {
  const element = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, String(value)));
  return element;
}

function text(value) {
  return value == null ? "" : String(value);
}

function nodeLabel(id) {
  return state.nodes.get(id)?.label || id;
}

function edgeIsAvailable(edge) {
  return (edge.requires || []).every((condition) => state.conditions.has(condition));
}

function getPreferenceRiskWeight() {
  if (state.preference === "fast") return 0.35;
  if (state.preference === "safe") return 5.5;
  return 2.0;
}

function calculateRoute() {
  if (!state.data) return null;
  if (state.origin === state.destination) {
    return { nodes: [state.origin], edges: [], time: 0, risk: 0, score: 0 };
  }

  const distances = new Map();
  const previous = new Map();
  const unvisited = new Set(state.data.nodes.map((node) => node.id));
  state.data.nodes.forEach((node) => distances.set(node.id, Number.POSITIVE_INFINITY));
  distances.set(state.origin, 0);

  while (unvisited.size) {
    let current = null;
    let currentDistance = Number.POSITIVE_INFINITY;
    for (const id of unvisited) {
      const distance = distances.get(id);
      if (distance < currentDistance) {
        current = id;
        currentDistance = distance;
      }
    }
    if (!current || current === state.destination) break;
    unvisited.delete(current);

    state.data.edges
      .filter((edge) => edge.from === current && edgeIsAvailable(edge))
      .forEach((edge) => {
        if (!unvisited.has(edge.to)) return;
        const edgeScore = Number(edge.cost) + Number(edge.risk || 0) * getPreferenceRiskWeight();
        const candidate = currentDistance + edgeScore;
        if (candidate < distances.get(edge.to)) {
          distances.set(edge.to, candidate);
          previous.set(edge.to, { nodeId: current, edge });
        }
      });
  }

  if (!previous.has(state.destination)) return null;

  const nodes = [];
  const edges = [];
  let cursor = state.destination;
  while (cursor !== state.origin) {
    nodes.unshift(cursor);
    const step = previous.get(cursor);
    if (!step) return null;
    edges.unshift(step.edge);
    cursor = step.nodeId;
  }
  nodes.unshift(state.origin);

  return {
    nodes,
    edges,
    time: edges.reduce((sum, edge) => sum + Number(edge.cost || 0), 0),
    risk: edges.reduce((sum, edge) => sum + Number(edge.risk || 0), 0),
    score: distances.get(state.destination),
  };
}

function findBlockedRequirements() {
  const reachable = new Set([state.origin]);
  let changed = true;
  while (changed) {
    changed = false;
    state.data.edges.forEach((edge) => {
      if (reachable.has(edge.from) && edgeIsAvailable(edge) && !reachable.has(edge.to)) {
        reachable.add(edge.to);
        changed = true;
      }
    });
  }
  const missing = new Set();
  state.data.edges.forEach((edge) => {
    if (reachable.has(edge.from) && !reachable.has(edge.to)) {
      (edge.requires || []).filter((id) => !state.conditions.has(id)).forEach((id) => missing.add(id));
    }
  });
  return [...missing].map((id) => state.data.conditions.find((condition) => condition.id === id)?.label || id);
}

function populateSelects() {
  const nodes = [...state.data.nodes].sort((a, b) => a.label.localeCompare(b.label, "zh-CN"));
  [els.origin, els.destination].forEach((select) => {
    select.innerHTML = "";
    nodes.forEach((node) => {
      const option = document.createElement("option");
      option.value = node.id;
      option.textContent = `${node.label} · ${node.region}`;
      select.appendChild(option);
    });
  });
  els.origin.value = state.origin;
  els.destination.value = state.destination;
}

function renderConditions() {
  els.conditions.innerHTML = "";
  state.data.conditions.forEach((condition) => {
    const label = document.createElement("label");
    label.className = "condition-item";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.dataset.conditionId = condition.id;
    input.checked = state.conditions.has(condition.id);
    input.addEventListener("change", () => {
      if (input.checked) state.conditions.add(condition.id);
      else state.conditions.delete(condition.id);
      planAndRender();
    });
    const copy = document.createElement("span");
    copy.className = "condition-copy";
    copy.innerHTML = `<span class="condition-label">${condition.label}</span><span class="condition-hint">${condition.hint}</span>`;
    label.append(input, copy);
    els.conditions.appendChild(label);
  });
}

function renderRegions() {
  els.regionLabels.innerHTML = "";
  const groups = new Map();
  state.data.nodes.forEach((node) => {
    if (!groups.has(node.region)) groups.set(node.region, []);
    groups.get(node.region).push(node);
  });
  [...groups.entries()].forEach(([region, nodes], index) => {
    const x = Math.min(...nodes.map((node) => node.x)) - 16;
    const y = Math.max(28, Math.min(...nodes.map((node) => node.y)) - 35 - (index % 2) * 10);
    const label = svg("text", { x, y, class: "region-label" });
    label.textContent = region;
    const rule = svg("line", { x1: x, y1: y + 7, x2: x + 58, y2: y + 7, class: "region-rule" });
    els.regionLabels.append(rule, label);
  });
}

function visibleNode(node) {
  return state.layer === "all" || node.layer === state.layer || Boolean(state.route?.nodes.includes(node.id));
}

function renderEdges() {
  els.edgeLayer.innerHTML = "";
  const routeEdgeIds = new Set(state.route?.edges.map((edge) => edge.id) || []);
  const routeNodeIds = new Set(state.route?.nodes || []);

  state.data.edges.forEach((edge) => {
    const from = state.nodes.get(edge.from);
    const to = state.nodes.get(edge.to);
    if (!from || !to) return;
    const edgeVisible = visibleNode(from) && visibleNode(to);
    if (!edgeVisible) return;
    const available = edgeIsAvailable(edge);
    const isRoute = routeEdgeIds.has(edge.id);
    const line = svg("line", {
      x1: from.x,
      y1: from.y,
      x2: to.x,
      y2: to.y,
      class: `edge ${available ? "available" : "blocked"} ${(edge.requires || []).length ? "conditional" : ""} ${isRoute ? "route" : ""}`,
      "data-edge-id": edge.id,
    });
    line.addEventListener("mouseenter", () => {
      els.mapToast.textContent = `${from.label} → ${to.label} · ${edge.mode}${available ? "" : " · 条件未满足"}`;
    });
    line.addEventListener("mouseleave", () => { els.mapToast.textContent = "点击节点查看详情"; });
    els.edgeLayer.appendChild(line);

    if ((edge.requires || []).length || isRoute) {
      const labelX = (from.x + to.x) / 2;
      const labelY = (from.y + to.y) / 2 - 5;
      const label = svg("text", { x: labelX, y: labelY, class: `edge-label ${isRoute ? "route-label" : ""}` });
      label.textContent = available ? edge.mode : `锁定 · ${edge.mode}`;
      els.edgeLayer.appendChild(label);
    }
  });
}

function nodeCoreColor(kind) {
  if (kind === "target") return "#d5b862";
  if (kind === "boss") return "#c36e66";
  if (kind === "teleport") return "#9b8fc4";
  if (kind === "lift") return "#82b0b9";
  if (kind === "entrance") return "#9b9b8a";
  return "#74796f";
}

function selectNode(id) {
  state.selectedNode = id;
  renderNodes();
  renderInspector();
}

function renderNodes() {
  els.nodeLayer.innerHTML = "";
  const routeNodeIds = new Set(state.route?.nodes || []);
  state.data.nodes.forEach((node) => {
    if (!visibleNode(node)) return;
    const group = svg("g", {
      class: `node-group kind-${node.kind} ${state.selectedNode === node.id ? "selected" : ""} ${routeNodeIds.has(node.id) ? "route-node" : ""} ${node.id === state.origin ? "origin" : ""} ${node.id === state.destination ? "destination" : ""}`,
      transform: `translate(${node.x} ${node.y})`,
    });
    if (state.route && !routeNodeIds.has(node.id) && state.layer === "all") group.classList.add("dim");
    const hit = svg("circle", { r: 14, class: "node-hit" });
    const ring = svg("circle", { r: node.kind === "target" ? 9 : 7, class: "node-ring" });
    const core = svg("circle", { r: node.kind === "target" ? 4 : 3, class: "node-core", fill: nodeCoreColor(node.kind) });
    const label = svg("text", { x: 12, y: 4, class: "node-label" });
    label.textContent = node.label;
    const region = svg("text", { x: 12, y: 15, class: "node-region" });
    region.textContent = `${node.layer.toUpperCase()} · ${node.region}`;
    group.append(hit, ring, core, label, region);
    if (node.id === state.origin || node.id === state.destination) {
      const marker = svg("text", { x: -4, y: -13, class: "node-status" });
      marker.textContent = node.id === state.origin ? "FROM" : "TO";
      group.appendChild(marker);
    }
    group.addEventListener("click", () => selectNode(node.id));
    group.addEventListener("mouseenter", () => { els.mapToast.textContent = `${node.label} · ${node.region}`; });
    group.addEventListener("mouseleave", () => { els.mapToast.textContent = "点击节点查看详情"; });
    els.nodeLayer.appendChild(group);
  });
}

function renderGraph() {
  renderRegions();
  renderEdges();
  renderNodes();
  els.graphStats.textContent = `${state.data.nodes.length} 节点 · ${state.data.edges.length} 有向边 · ${state.data.meta.verificationLabel || "V1"}`;
}

function renderInspector() {
  const node = state.nodes.get(state.selectedNode);
  if (!node) return;
  const outgoing = state.data.edges.filter((edge) => edge.from === node.id).slice(0, 4);
  const incoming = state.data.edges.filter((edge) => edge.to === node.id).slice(0, 3);
  const connections = [...outgoing, ...incoming];
  els.nodeInspector.innerHTML = `
    <div class="inspector-card">
      <div class="inspector-head">
        <div><div class="inspector-title">${node.label}</div><div class="inspector-type">${node.kind.toUpperCase()} · ${node.layer.toUpperCase()}</div></div>
        <div class="inspector-region">${node.region}</div>
      </div>
       <p class="inspector-description">${node.description}</p>
       <div class="inspector-source">验证：${node.verificationState || "unknown"} · 坐标：${node.coordinateType || "unknown"}<br>来源：${(node.sourceEvidence || []).map((id) => state.data.sourceEvidence?.find((item) => item.id === id)?.label || id).join("；") || "未登记"}</div>
      <div class="inspector-actions"><button data-set-origin="${node.id}">设为起点</button><button data-set-destination="${node.id}">设为终点</button></div>
      <div class="connection-list"><div class="connection-list-title">附近连接 / ${connections.length}</div>
        ${connections.map((edge) => {
          const target = edge.from === node.id ? nodeLabel(edge.to) : `← ${nodeLabel(edge.from)}`;
          const lock = edgeIsAvailable(edge) ? "" : " · 锁定";
          return `<div class="connection-item"><span>${target}</span><span class="connection-mode">${edge.mode}${lock}</span></div>`;
        }).join("") || '<div class="connection-item"><span>暂无连接</span></div>'}
      </div>
    </div>`;
  els.nodeInspector.querySelector("[data-set-origin]").addEventListener("click", () => {
    state.origin = node.id;
    els.origin.value = node.id;
    planAndRender();
  });
  els.nodeInspector.querySelector("[data-set-destination]").addEventListener("click", () => {
    state.destination = node.id;
    els.destination.value = node.id;
    planAndRender();
  });
}

function routeText(route) {
  const lines = [`RUNE//PATH 路线`, `${nodeLabel(state.origin)} → ${nodeLabel(state.destination)}`, `相对成本 ${route.time} · 风险指数 ${route.risk} · ${route.edges.length} 段`, ""];
  route.nodes.forEach((nodeId, index) => {
    lines.push(`${index + 1}. ${nodeLabel(nodeId)}${route.edges[index] ? ` —[${route.edges[index].mode}]→` : ""}`);
  });
  return lines.join("\n");
}

function renderRoute() {
  if (!state.route) {
    els.routeSummary.classList.remove("hidden");
    els.routeContent.classList.add("hidden");
    const missing = findBlockedRequirements();
    els.routeSummary.innerHTML = `<div class="summary-icon">∅</div><h2>此刻不可达</h2><p>${nodeLabel(state.origin)} 到 ${nodeLabel(state.destination)} 没有满足当前条件的有向路径。</p>${missing.length ? `<div class="route-notice warning">可能需要：${missing.join("、")}</div>` : ""}`;
    return;
  }
  els.routeSummary.classList.add("hidden");
  els.routeContent.classList.remove("hidden");
  els.routeTitle.textContent = `${nodeLabel(state.origin)} → ${nodeLabel(state.destination)}`;
  els.routeTime.textContent = state.route.time;
  els.routeRisk.textContent = state.route.risk;
  els.routeHops.textContent = state.route.edges.length;
  els.pathTrack.innerHTML = state.route.nodes.map((nodeId, index) => {
    const edge = state.route.edges[index];
    const node = state.nodes.get(nodeId);
    return `<div class="path-step"><div class="step-dot">${index + 1}</div><div class="step-copy"><div class="step-node">${node.label}</div>${edge ? `<div class="step-edge">${edge.mode} → ${nodeLabel(edge.to)}</div><div class="step-meta">成本 ${edge.cost} · 风险 ${edge.risk}${edge.requires?.length ? ` · ${edge.requires.map((id) => state.data.conditions.find((condition) => condition.id === id)?.label || id).join("、")}` : ""}</div>` : "<div class=\"step-meta\">目标节点</div>"}</div></div>`;
  }).join("");
  els.routeNotice.textContent = state.preference === "safe" && state.route.risk > 3
    ? "当前没有完全低风险的连通方案；这条路线已经是在现有图中风险最低的可达路径。"
    : "路线按有向连接计算；标记为单向的跳落、传送和棺材边不会自动反向。";
  els.routeNotice.classList.toggle("warning", state.preference === "safe" && state.route.risk > 3);
}

function planAndRender() {
  state.route = calculateRoute();
  renderGraph();
  renderRoute();
  renderInspector();
}

function setZoom(nextZoom) {
  state.zoom = Math.max(0.7, Math.min(1.7, nextZoom));
  els.mapTransform.setAttribute("transform", `translate(500 300) scale(${state.zoom}) translate(-500 -300)`);
}

function wireEvents() {
  els.origin.addEventListener("change", () => { state.origin = els.origin.value; state.selectedNode = state.origin; planAndRender(); });
  els.destination.addEventListener("change", () => { state.destination = els.destination.value; state.selectedNode = state.destination; planAndRender(); });
  els.plan.addEventListener("click", planAndRender);
  els.reset.addEventListener("click", () => {
    state.origin = state.data.defaultOrigin || state.data.nodes[0]?.id;
    state.destination = state.data.defaultDestination || state.data.nodes.at(-1)?.id;
    state.conditions = new Set(state.data.defaultConditions || DEFAULT_CONDITIONS);
    state.preference = "balanced";
    state.layer = "all";
    state.selectedNode = state.origin;
    els.origin.value = state.origin;
    els.destination.value = state.destination;
    document.querySelectorAll(".condition-item input").forEach((input) => { input.checked = state.conditions.has(input.dataset.conditionId); });
    document.querySelectorAll(".segment").forEach((button) => button.classList.toggle("active", button.dataset.preference === state.preference));
    document.querySelectorAll(".layer-tab").forEach((button) => button.classList.toggle("active", button.dataset.layer === state.layer));
    els.preferenceHint.textContent = preferenceHints[state.preference];
    planAndRender();
  });
  document.querySelectorAll(".segment").forEach((button) => button.addEventListener("click", () => {
    state.preference = button.dataset.preference;
    document.querySelectorAll(".segment").forEach((item) => item.classList.toggle("active", item === button));
    els.preferenceHint.textContent = preferenceHints[state.preference];
    planAndRender();
  }));
  document.querySelectorAll(".layer-tab").forEach((button) => button.addEventListener("click", () => {
    state.layer = button.dataset.layer;
    document.querySelectorAll(".layer-tab").forEach((item) => item.classList.toggle("active", item === button));
    renderGraph();
  }));
  document.getElementById("zoom-in").addEventListener("click", () => setZoom(state.zoom + 0.1));
  document.getElementById("zoom-out").addEventListener("click", () => setZoom(state.zoom - 0.1));
  document.getElementById("zoom-reset").addEventListener("click", () => setZoom(1));
  els.copyRoute.addEventListener("click", async () => {
    if (!state.route) return;
    try {
      await navigator.clipboard.writeText(routeText(state.route));
      els.mapToast.textContent = "路线摘要已复制";
      setTimeout(() => { els.mapToast.textContent = "点击节点查看详情"; }, 1800);
    } catch {
      els.mapToast.textContent = "浏览器阻止了剪贴板访问";
    }
  });
}

async function init() {
  wireEvents();
  try {
    const response = await fetch("/api/graph", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    state.nodes = new Map(state.data.nodes.map((node) => [node.id, node]));
    state.conditions = new Set(state.data.defaultConditions || DEFAULT_CONDITIONS);
    state.origin = state.data.defaultOrigin && state.nodes.has(state.data.defaultOrigin) ? state.data.defaultOrigin : state.data.nodes[0].id;
    state.destination = state.data.defaultDestination && state.nodes.has(state.data.defaultDestination) ? state.data.defaultDestination : state.data.nodes.at(-1).id;
    els.datasetVersion.textContent = `v${state.data.meta.version}`;
    populateSelects();
    renderConditions();
    els.preferenceHint.textContent = preferenceHints[state.preference];
    els.loading.classList.add("hidden");
    planAndRender();
  } catch (error) {
    els.loading.textContent = `拓扑数据载入失败：${error.message}`;
    els.loading.style.color = "#d47d71";
  }
}

init();
