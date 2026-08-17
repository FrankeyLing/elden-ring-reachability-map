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
  if (edge.routeable === false) return false;
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
  [...state.data.edges, ...(state.data.candidateEdges || [])].forEach((edge) => {
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
      class: `edge ${available ? "available" : "blocked"} ${(edge.requires || []).length ? "conditional" : ""} ${edge.candidate ? "candidate" : ""} ${isRoute ? "route" : ""}`,
      "data-edge-id": edge.id,
    });
    line.addEventListener("mouseenter", () => {
       els.mapToast.textContent = `${from.label} → ${to.label} · ${edge.mode}${edge.candidate ? " · 候选，尚未晋升" : available ? "" : " · 条件未满足"}`;
    });
    line.addEventListener("mouseleave", () => { els.mapToast.textContent = "点击节点查看详情"; });
    els.edgeLayer.appendChild(line);

    if (!edge.candidate && ((edge.requires || []).length || isRoute)) {
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
    const showCatalogLabel = !node.isCatalog || node.id === state.selectedNode || routeNodeIds.has(node.id);
    const label = svg("text", { x: 12, y: 4, class: `node-label${showCatalogLabel ? "" : " node-label-hidden"}` });
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
  els.graphStats.textContent = `${state.data.nodes.length} 节点 · ${state.data.edges.length} 已证实边 · ${state.data.catalogRecordCount || 0} 赐福 · ${state.data.candidateRouteLegCount || 0} 候选路段 · ${state.data.meta.verificationLabel || "V1"}`;
}

function renderInspector() {
  const node = state.nodes.get(state.selectedNode);
  if (!node) return;
  const allEdges = [...state.data.edges, ...(state.data.candidateEdges || [])];
  const outgoing = allEdges.filter((edge) => edge.from === node.id).slice(0, 4);
  const incoming = allEdges.filter((edge) => edge.to === node.id).slice(0, 3);
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
           return `<div class="connection-item"><span>${target}</span><span class="connection-mode">${edge.candidate ? "候选未晋升" : edge.mode}${lock}</span></div>`;
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
  const width = state.data?.meta?.coordinateSpace?.width || 1000;
  const height = state.data?.meta?.coordinateSpace?.height || 600;
  els.mapTransform.setAttribute("transform", `translate(${width / 2} ${height / 2}) scale(${state.zoom}) translate(${-width / 2} ${-height / 2})`);
}

function applyMapCoordinateSpace() {
  const width = state.data?.meta?.coordinateSpace?.width || 1000;
  const height = state.data?.meta?.coordinateSpace?.height || 600;
  const map = document.getElementById("topology-map");
  map.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const grid = document.querySelector(".map-grid");
  if (grid) {
    grid.setAttribute("width", String(width));
    grid.setAttribute("height", String(height));
  }
  setZoom(state.zoom);
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
    const [graphResponse, catalogResponse, routeLegResponse] = await Promise.all([
      fetch("/api/graph", { cache: "no-store" }),
      fetch("/api/catalog/sites-of-grace", { cache: "no-store" }),
      fetch("/api/catalog/route-legs", { cache: "no-store" }),
    ]);
    if (!graphResponse.ok) throw new Error(`图数据 HTTP ${graphResponse.status}`);
    if (!catalogResponse.ok) throw new Error(`赐福目录 HTTP ${catalogResponse.status}`);
    if (!routeLegResponse.ok) throw new Error(`候选路线 HTTP ${routeLegResponse.status}`);
    state.data = await graphResponse.json();
    applyMapCoordinateSpace();
    const catalog = await catalogResponse.json();
    const routeLegCatalog = await routeLegResponse.json();
    const regionSlots = new Map();
    const sourceNameToNodeId = new Map([
      ["Avenue Balcony", "grace_avenue_balcony"],
      ["Erdtree Sanctuary", "grace_erdtree_sanctuary"],
      ["Elden Throne", "grace_elden_throne"],
      ["Siofra River Well Depths", "grace_siofra_well_depths"],
      ["Siofra River Bank", "grace_siofra_river_bank"],
      ["Crumbling Beast Grave", "grace_crumbling_beast_grave"],
      ["Crumbling Beast Grave Depths", "grace_crumbling_beast_grave_depths"],
      ["Beside the Great Bridge", "grace_beside_great_bridge"],
      ["Dragon Temple Altar", "grace_dragon_temple_altar"],
      ["Maliketh", "maliketh_gate"],
      ["Maliketh, the Black Blade", "grace_maliketh_black_blade"],
      ["Leyndell, Capital of Ash", "grace_leyndell_capital_of_ash"],
      ["Gravesite Plain", "grace_shadow_realm_gravesite_plain"],
      ["Three-Path Cross", "grace_shadow_realm_three_path_cross"],
      ["Church of Consolation", "landmark_church_of_consolation"],
      ["Main Gate Cross", "grace_shadow_realm_main_gate_cross"],
      ["Belurat, Tower Settlement", "grace_belurat_tower_settlement"],
      ["Divine Beast Dancing Lion", "divine_beast_dancing_lion_gate"],
      ["Theatre of the Divine Beast", "grace_belurat_theatre_divine_beast"],
      ["Pillar Path Cross", "grace_shadow_realm_pillar_path_cross"],
      ["Cliffroad Terminus", "grace_shadow_realm_cliffroad_terminus"],
      ["Highroad Cross", "grace_scadu_altus_highroad_cross"],
      ["Moorth Ruins", "grace_scadu_altus_moorth_ruins"],
      ["Bonny Village", "grace_scadu_altus_bonny_village"],
      ["Bridge Leading to the Village", "grace_scadu_altus_bridge_leading_to_village"],
      ["Church District Highroad", "grace_scadu_altus_church_district_highroad"],
      ["Shadow Keep Main Gate", "grace_shadow_keep_main_gate"],
      ["Main Gate Plaza", "grace_shadow_keep_main_gate_plaza"],
      ["Golden Hippopotamus", "golden_hippopotamus_gate"],
      ["Church District Entrance", "grace_shadow_keep_church_district_entrance"],
      ["Sunken Chapel", "grace_shadow_keep_sunken_chapel"],
      ["Tree-Worship Passage", "grace_shadow_keep_tree_worship_passage"],
      ["Tree-Worship Sanctum", "grace_shadow_keep_tree_worship_sanctum"],
      ["Storehouse, First Floor", "grace_shadow_keep_storehouse_first_floor"],
      ["Storehouse, Fourth Floor", "grace_shadow_keep_storehouse_fourth_floor"],
      ["Storehouse, Seventh Floor", "grace_shadow_keep_storehouse_seventh_floor"],
      ["Messmer the Impaler", "messmer_gate"],
      ["Messmer's Dark Chamber", "grace_shadow_keep_messmer_dark_chamber"],
      ["Storehouse, Back Section", "grace_shadow_keep_storehouse_back_section"],
      ["Storehouse, Loft", "grace_shadow_keep_storehouse_loft"],
      ["Shadow Keep, Back Gate", "grace_shadow_keep_back_gate"],
      ["Scaduview", "grace_shadow_keep_scaduview"],
      ["Commander Gaius", "commander_gaius_gate"],
      ["Scadutree Base", "grace_shadow_keep_scadutree_base"],
      ["Ancient Ruins Base", "grace_rauh_ancient_ruins_base"],
      ["Viaduct Minor Tower", "grace_rauh_viaduct_minor_tower"],
      ["Rauh Ancient Ruins, East", "grace_rauh_ancient_ruins_east"],
      ["Rauh Ancient Ruins, West", "grace_rauh_ancient_ruins_west"],
      ["Church of the Bud, Main Entrance", "grace_church_of_bud_main_entrance"],
      ["Romina, Saint of the Bud", "romina_gate"],
      ["Church of the Bud", "grace_church_of_bud"],
      ["Enir-Ilim: Outer Wall", "grace_enir_ilim_outer_wall"],
      ["First Rise", "grace_enir_ilim_first_rise"],
      ["Spiral Rise", "grace_enir_ilim_spiral_rise"],
      ["Cleansing Chamber Anteroom", "grace_enir_ilim_cleansing_chamber"],
      ["Leda and Allies", "leda_allies_gate"],
      ["Divine Gate Front Staircase", "grace_enir_ilim_divine_gate_front_staircase"],
      ["Promised Consort Radahn", "promised_consort_radahn_gate"],
      ["Gate of Divinity", "grace_enir_ilim_gate_of_divinity"],
      ["Dragon's Pit", "grace_gravesite_plain_main_dragon_s_pit"],
      ["Ancient Dragon-Man", "ancient_dragon_man_gate"],
      ["Dragon's Pit Terminus", "grace_gravesite_plain_main_dragon_s_pit_terminus"],
      ["Foot of the Jagged Peak", "grace_gravesite_plain_foot_of_the_jagged_peak_foot_of_the_jagged_peak"],
      ["Grand Altar of Dragon Communion", "grace_gravesite_plain_foot_of_the_jagged_peak_grand_altar_of_dragon_communion"],
      ["Ancient Dragon Senessax", "ancient_dragon_senessax_gate"],
      ["Jagged Peak Mountainside", "grace_gravesite_plain_jagged_peak_jagged_peak_mountainside"],
      ["Jagged Peak Summit", "grace_gravesite_plain_jagged_peak_jagged_peak_summit"],
      ["Bayle the Dread", "bayle_gate"],
      ["Jagged Peak Summit (Bayle the Dread)", "bayle_gate"],
      ["Rest of the Dread Dragon", "grace_gravesite_plain_jagged_peak_rest_of_the_dread_dragon"],
      ["Castle Watering Hole", "grace_scadu_altus_main_castle_watering_hole"],
      ["Recluses' River Upstream", "grace_scadu_altus_main_recluses_river_upstream"],
      ["Recluses' River Downstream", "grace_scadu_altus_main_recluses_river_downstream"],
      ["Darklight Catacombs", "grace_scadu_altus_main_darklight_catacombs"],
      ["Jori, Elder Inquisitor", "jori_gate"],
      ["Abyssal Woods", "grace_scadu_altus_abyssal_woods_abyssal_woods"],
      ["Abyssal Woods (Midra's Manse)", "grace_scadu_altus_abyssal_woods_abyssal_woods"],
      ["Woodland Trail", "grace_scadu_altus_abyssal_woods_woodland_trail"],
      ["Church Ruins", "grace_scadu_altus_abyssal_woods_church_ruins"],
      ["Divided Falls", "grace_scadu_altus_abyssal_woods_divided_falls"],
      ["Manse Hall", "grace_scadu_altus_midra_s_manse_manse_hall"],
      ["Midra's Library", "grace_scadu_altus_midra_s_manse_midra_s_library"],
      ["Second Floor Chamber", "grace_scadu_altus_midra_s_manse_second_floor_chamber"],
      ["Midra, Lord of Frenzied Flame", "midra_gate"],
      ["Discussion Chamber", "grace_scadu_altus_midra_s_manse_discussion_chamber"],
      ["Ellac River Cave", "grace_gravesite_plain_main_ellac_river_cave"],
      ["Ellac River Downstream", "grace_gravesite_plain_main_ellac_river_downstream"],
      ["Cerulean Coast", "grace_gravesite_plain_cerulean_coast_cerulean_coast"],
      ["Cerulean Coast West", "grace_gravesite_plain_cerulean_coast_cerulean_coast_west"],
      ["Cerulean Coast Cross", "grace_gravesite_plain_cerulean_coast_cerulean_coast_cross"],
      ["Finger Ruins of Rhia", "grace_gravesite_plain_cerulean_coast_finger_ruins_of_rhia"],
      ["The Fissure", "grace_gravesite_plain_cerulean_coast_the_fissure"],
      ["Stone Coffin Fissure", "grace_gravesite_plain_stone_coffin_fissure_stone_coffin_fissure"],
      ["Fissure Cross", "grace_gravesite_plain_stone_coffin_fissure_fissure_cross"],
      ["Fissure Waypoint", "grace_gravesite_plain_stone_coffin_fissure_fissure_waypoint"],
      ["Fissure Depths", "grace_gravesite_plain_stone_coffin_fissure_fissure_depths"],
      ["Putrescent Knight", "putrescent_knight_gate"],
      ["Garden of Deep Purple", "grace_gravesite_plain_stone_coffin_fissure_garden_of_deep_purple"],
      ["O Mother Statue Passage", "o_mother_statue_gate"],
      ["Hinterland", "grace_shadow_keep_scaduview_hinterland"],
      ["Hinterland Bridge", "grace_shadow_keep_scaduview_hinterland_bridge"],
      ["Fingerstone Hill", "grace_shadow_keep_scaduview_fingerstone_hill"],
      ["Finger Ruins of Dheo", "finger_ruins_dheo"],
      ["Finger Ruins of Rhia Bell", "finger_rhia_bell"],
      ["Finger Ruins of Dheo Bell", "finger_dheo_bell"],
      ["Cathedral of Manus Metyr", "grace_scadu_altus_main_cathedral_of_manus_metyr"],
      ["Count Ymir's Throne", "ymir_throne_gate"],
      ["Finger Ruins of Miyr", "finger_ruins_miyr"],
      ["Metyr, Mother of Fingers", "metyr_gate"],
      ["Queen's Bedchamber", "grace_queens_bedchamber"],
      ["Sir Gideon Ofnir, the All-Knowing", "gideon_ashen_gate"],
      ["Godfrey, First Elden Lord", "godfrey_ashen_gate"],
      ["Radagon of the Golden Order", "radagon_elden_beast_gate"],
      ["Elden Beast", "radagon_elden_beast_gate"],
      ["Fractured Marika", "grace_fractured_marika"],
      ["Castle Front", "grace_castle_front"],
      ["Castle Ensis Checkpoint", "grace_castle_ensis_checkpoint"],
      ["Castle-Lord's Chamber", "grace_castle_lord_chamber"],
      ["Ensis Moongazing Grounds", "grace_ensis_moongazing_grounds"],
      ["Renna's Rise (sending gate)", "renna_rise_waygate"],
      ["Ainsel River Main", "grace_ainsel_river_main"],
      ["Nokstella, Eternal City", "grace_nokstella_eternal_city"],
      ["Nokstella Waterfall Basin", "grace_nokstella_waterfall_basin"],
      ["Lake of Rot Shoreside", "grace_lake_of_rot_shoreside"],
      ["Grand Cloister", "grace_grand_cloister"],
      ["Astel, Naturalborn of the Void", "astel_naturalborn_gate"],
      ["Moonlight Altar", "grace_moonlight_altar"],
      ["Mohgwyn sending gate", "mohgwyn_sending_gate"],
      ["Pureblood Knight's Medal", "pureblood_knight_medal_gate"],
      ["Palace Approach Ledge-Road", "grace_palace_approach_ledge_road"],
      ["Dynasty Mausoleum Entrance", "grace_dynasty_mausoleum_entrance"],
      ["Dynasty Mausoleum Midpoint", "grace_dynasty_mausoleum_midpoint"],
      ["Cocoon of the Empyrean", "grace_cocoon_of_empyrean"],
      ["Grand Lift of Rold", "grace_grand_lift_of_rold"],
      ["Zamor Ruins", "grace_zamor_ruins"],
      ["Whiteridge Road", "grace_whiteridge_road"],
      ["Freezing Lake", "grace_freezing_lake"],
      ["Giants' Gravepost", "grace_giants_gravepost"],
      ["Foot of the Forge", "grace_foot_of_forge"],
      ["Fire Giant", "fire_giant_gate"],
      ["Forge of the Giants", "grace_forge_of_giants"],
      ["Castle Sol Main Gate", "grace_castle_sol_main_gate"],
      ["Church of the Eclipse", "grace_church_of_eclipse"],
      ["Commander Niall", "commander_niall_gate"],
      ["Castle Sol Rooftop", "grace_castle_sol_rooftop"],
      ["Consecrated Snowfield", "grace_consecrated_snowfield"],
      ["Inner Consecrated Snowfield", "grace_inner_consecrated_snowfield"],
      ["The First Step", "grace_first_step"],
      ["Church of Elleh", "grace_church_elleh"],
      ["Gatefront", "grace_gatefront"],
      ["Stormhill Shack", "grace_stormhill_shack"],
      ["Stormveil Main Gate", "grace_stormveil_main_gate"],
      ["Stormveil Cliffside", "grace_stormveil_cliffside"],
      ["Rampart Tower", "grace_stormveil_rampart_tower"],
      ["Liftside Chamber", "grace_stormveil_liftside_chamber"],
      ["Secluded Cell", "grace_stormveil_secluded_cell"],
      ["Godrick the Grafted", "godrick_gate"],
      ["Lake-Facing Cliffs", "grace_lake_facing_cliffs"],
      ["Main Academy Gate", "grace_main_academy_gate"],
      ["Church of the Cuckoo", "grace_church_of_cuckoo"],
      ["Schoolhouse Classroom", "grace_schoolhouse_classroom"],
      ["Red Wolf of Radagon", "red_wolf_gate"],
      ["Debate Parlor", "grace_debate_parlor"],
      ["Rennala, Queen of the Full Moon", "rennala_gate"],
      ["Raya Lucaria Grand Library", "grace_raya_lucaria_grand_library"],
      ["Grand Lift of Dectus", "grace_grand_lift_dectus"],
      ["Altus Plateau", "grace_altus_plateau"],
      ["Altus Highway Junction", "grace_altus_highway_junction"],
      ["Outer Wall Phantom Tree", "grace_outer_wall_phantom_tree"],
      ["Outer Wall Battleground", "grace_outer_wall_battleground"],
      ["Draconic Tree Sentinel", "draconic_tree_sentinel_gate"],
      ["East Capital Rampart", "grace_east_capital_rampart"],
      ["Mistwood Outskirts", "grace_mistwood_outskirts"],
      ["Third Church of Marika", "grace_third_church_of_marika"],
      ["Siofra River Well", "siofra_well_surface_entrance"],
      ["Siofra Well descent lift", "siofra_well_lift"],
      ["Worshippers' Woods", "grace_worshippers_woods"],
      ["Ancestral Woods", "grace_ancestral_woods"],
      ["Aqueduct-Facing Cliffs", "grace_aqueduct_facing_cliffs"],
      ["Caelid Highway South", "grace_caelid_highway_south"],
      ["Rotview Balcony", "grace_rotview_balcony"],
      ["Smoldering Church", "grace_smoldering_church"],
      ["Caelem Ruins", "grace_caelem_ruins"],
      ["Impassable Greatbridge", "grace_impassable_greatbridge"],
      ["Redmane Castle Plaza", "grace_redmane_castle_plaza"],
      ["Chamber Outside the Plaza", "grace_chamber_outside_plaza"],
      ["Starscourge Radahn", "grace_starscourge_radahn"],
      ["Southern Aeonia Swamp Bank", "grace_southern_aeonia_swamp_bank"],
      ["Church of the Plague", "grace_church_of_plague"],
      ["Bestial Sanctum", "grace_bestial_sanctum"],
      ["Dragonbarrow Fork", "grace_dragonbarrow_fork"],
      ["Fort Faroth", "grace_fort_faroth"],
      ["Dectus Medallion (Right)", "item_dectus_medallion_right"],
      ["Starfall Crater (Mistwood, Limgrave)", "starfall_crater_entrance"],
      ["Nokron, Eternal City", "grace_nokron_eternal_city"],
      ["Siofra Aqueduct (Valiant Gargoyles)", "siofra_aqueduct_valiant_gargoyle_gate"],
      ["Deeproot coffin", "deeproot_coffin"],
      ["Deeproot Depths", "grace_deeproot_depths"],
      ["Prince of Death's Throne", "grace_prince_of_deaths_throne"],
      ["Ordina, Liturgical Town (Consecrated Snowfield)", "grace_ordina_liturgical_town"],
      ["Volcano Manor (entrance)", "grace_volcano_manor_entrance"],
      ["Prison Town Church", "grace_prison_town_church"],
      ["Temple of Eiglay", "grace_temple_of_eiglay"],
      ["Haligtree Canopy", "grace_haligtree_canopy"],
      ["Haligtree Promenade (Loretta)", "grace_haligtree_promenade"],
    ]);
    const layerBase = { surface: 55, underground: 275, legacy: 445 };
    catalog.records.forEach((record) => {
      if (["Crumbling Beast Grave", "Beside the Great Bridge", "Maliketh, the Black Blade", "Leyndell, Capital of Ash", "Gravesite Plain", "Three-Path Cross", "Church of Consolation", "Main Gate Cross", "Belurat, Tower Settlement", "Divine Beast Dancing Lion", "Theatre of the Divine Beast", "Pillar Path Cross", "Cliffroad Terminus", "Highroad Cross", "Moorth Ruins", "Bonny Village", "Bridge Leading to the Village", "Church District Highroad", "Shadow Keep Main Gate", "Main Gate Plaza", "Golden Hippopotamus", "Church District Entrance", "Sunken Chapel", "Tree-Worship Passage", "Tree-Worship Sanctum", "Storehouse, First Floor", "Storehouse, Fourth Floor", "Storehouse, Seventh Floor", "Storehouse, Back Section", "Storehouse, Loft", "Shadow Keep, Back Gate", "Scaduview", "Commander Gaius", "Scadutree Base", "Ancient Ruins Base", "Viaduct Minor Tower", "Rauh Ancient Ruins, East", "Rauh Ancient Ruins, West", "Church of the Bud, Main Entrance", "Romina, Saint of the Bud", "Church of the Bud", "Enir-Ilim: Outer Wall", "First Rise", "Spiral Rise", "Cleansing Chamber Anteroom", "Divine Gate Front Staircase", "Gate of Divinity", "Messmer the Impaler", "Messmer's Dark Chamber", "Queen's Bedchamber", "Sir Gideon Ofnir, the All-Knowing", "Godfrey, First Elden Lord", "Radagon of the Golden Order", "Elden Beast", "Fractured Marika", "Dragon's Pit", "Dragon's Pit Terminus", "Foot of the Jagged Peak", "Grand Altar of Dragon Communion", "Jagged Peak Mountainside", "Jagged Peak Summit", "Rest of the Dread Dragon", "Castle Watering Hole", "Recluses' River Upstream", "Recluses' River Downstream", "Darklight Catacombs", "Abyssal Woods", "Woodland Trail", "Church Ruins", "Divided Falls", "Manse Hall", "Midra's Library", "Second Floor Chamber", "Discussion Chamber", "Ellac River Cave", "Ellac River Downstream", "Cerulean Coast", "Cerulean Coast West", "Cerulean Coast Cross", "Finger Ruins of Rhia", "The Fissure", "Stone Coffin Fissure", "Fissure Cross", "Fissure Waypoint", "Fissure Depths", "Garden of Deep Purple", "Hinterland", "Hinterland Bridge", "Fingerstone Hill", "Cathedral of Manus Metyr"].includes(record.name)) return;
      if (["Caelid Highway South", "Rotview Balcony", "Smoldering Church", "Caelem Ruins", "Impassable Greatbridge", "Redmane Castle Plaza", "Chamber Outside the Plaza", "Starscourge Radahn", "Southern Aeonia Swamp Bank", "Church of the Plague", "Bestial Sanctum", "Dragonbarrow Fork", "Fort Faroth"].includes(record.name)) return;
      if (["Avenue Balcony", "Erdtree Sanctuary", "Elden Throne", "Siofra River Well Depths", "Siofra River Bank", "Worshippers' Woods", "Crumbling Beast Grave Depths", "Dragon Temple Altar", "Castle Front", "Castle Ensis Checkpoint", "Castle-Lord's Chamber", "Ensis Moongazing Grounds", "Ainsel River Main", "Nokstella, Eternal City", "Nokstella Waterfall Basin", "Lake of Rot Shoreside", "Grand Cloister", "Moonlight Altar", "Palace Approach Ledge-Road", "Dynasty Mausoleum Entrance", "Dynasty Mausoleum Midpoint", "Cocoon of the Empyrean", "Grand Lift of Rold", "Zamor Ruins", "Whiteridge Road", "Freezing Lake", "Giants' Gravepost", "Foot of the Forge", "Fire Giant", "Forge of the Giants", "Castle Sol Main Gate", "Church of the Eclipse", "Castle Sol Rooftop", "Consecrated Snowfield", "Inner Consecrated Snowfield", "The First Step", "Church of Elleh", "Gatefront", "Stormhill Shack", "Mistwood Outskirts", "Third Church of Marika", "Siofra River Well", "Ancestral Woods", "Aqueduct-Facing Cliffs", "Stormveil Main Gate", "Stormveil Cliffside", "Rampart Tower", "Liftside Chamber", "Secluded Cell", "Lake-Facing Cliffs", "Main Academy Gate", "Church of the Cuckoo", "Schoolhouse Classroom", "Debate Parlor", "Raya Lucaria Grand Library", "Grand Lift of Dectus", "Altus Plateau", "Altus Highway Junction", "Outer Wall Phantom Tree", "Outer Wall Battleground", "East Capital Rampart", "Nokron, Eternal City", "Deeproot Depths", "Prince of Death's Throne", "Ordina, Liturgical Town", "Volcano Manor", "Prison Town Church", "Temple of Eiglay", "Haligtree Canopy"].includes(record.name)) return;
      const groupKey = `${record.layer}|${record.region}`;
      const slot = regionSlots.get(groupKey) || 0;
      regionSlots.set(groupKey, slot + 1);
      const groupIndex = [...regionSlots.keys()].indexOf(groupKey);
      state.data.nodes.push({
        id: record.canonical_id,
        label: record.name,
        kind: "grace",
        layer: record.layer,
        region: record.region,
        floor: record.subgroup || record.region,
        worldEpoch: record.region.includes("Ash") || record.subgroup.includes("Ash") ? "ashen_capital_post_maliketh" : "unknown",
        x: 45 + (groupIndex % 5) * 190 + (slot % 7) * 20,
        y: layerBase[record.layer] + Math.floor(slot / 7) * 18 + (groupIndex % 3) * 7,
        coordinateType: record.coordinate_type,
        verificationState: record.verification_state,
        sourceEvidence: [record.source_evidence],
        isCatalog: true,
        description: `${record.region}${record.subgroup ? ` · ${record.subgroup}` : ""}。在线赐福目录实体；尚未获得游戏原始坐标或可通行边。`,
      });
      if (!sourceNameToNodeId.has(record.name)) sourceNameToNodeId.set(record.name, record.canonical_id);
    });
    state.data.catalogRecordCount = catalog.record_count;
    state.data.candidateRouteLegCount = routeLegCatalog.record_count;
    const candidateEndpointByName = new Map();
    const candidateLayer = (regionName) => {
      const match = catalog.records.find((record) => record.region === regionName);
      return match?.layer || "legacy";
    };
    const ensureCandidateEndpoint = (name, regionName) => {
      if (sourceNameToNodeId.has(name)) return sourceNameToNodeId.get(name);
      if (candidateEndpointByName.has(name)) return candidateEndpointByName.get(name);
      const layer = candidateLayer(regionName);
      const key = `${layer}|candidate|${regionName}`;
      const slot = regionSlots.get(key) || 0;
      regionSlots.set(key, slot + 1);
      const groupIndex = [...regionSlots.keys()].indexOf(key);
      const id = `candidate_endpoint_${name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "")}`;
      state.data.nodes.push({
        id,
        label: name,
        kind: "junction",
        layer,
        region: regionName,
        floor: regionName,
        worldEpoch: "unknown",
        x: 45 + (groupIndex % 5) * 190 + (slot % 7) * 20,
        y: layerBase[layer] + Math.floor(slot / 7) * 18 + (groupIndex % 3) * 7,
        coordinateType: "unplaced_route_candidate",
        verificationState: "online_single",
        sourceEvidence: ["er-guide-main-7f24d64d3631ef4d549f56b42d4c3e3817a269fa"],
        isCatalog: true,
        description: `${regionName} 的在线路线候选端点；尚未获得游戏原始坐标或正式 Transition。`,
      });
      candidateEndpointByName.set(name, id);
      return id;
    };
    state.data.candidateEdges = routeLegCatalog.records.map((leg) => ({
      id: leg.canonical_id,
      from: ensureCandidateEndpoint(leg.from, leg.region_name),
      to: ensureCandidateEndpoint(leg.to, leg.region_name),
      mode: "候选赐福路段",
      cost: 0,
      risk: 0,
      candidate: true,
      routeable: false,
      sourceEvidence: [leg.source_evidence],
      note: `${leg.from} → ${leg.to}；步骤类型：${(leg.step_types || []).join("、")}。需要独立来源核对后才能进入寻路器。`,
      tags: ["candidate", "source_only"],
    }));
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
