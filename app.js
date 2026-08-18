const SVG_NS = "http://www.w3.org/2000/svg";
const DEFAULT_CONDITIONS = [];
const DEFAULT_ROUTE_PROFILE = "physical_no_fast_travel";

const state = {
 data: null,
  mapMode: "topology",
  coordinateMapId: "m10_00_00",
  coordinateEntityKind: "enemy",
  coordinateBounds: null,
  coordinateFocus: null,
  onlineIndex: null,
  achievementCatalog: null,
 onlineBossByNodeId: new Map(),
 onlineMapPointByNodeId: new Map(),
  onlineMapPointRecords: [],
  onlineTileRecords: [],
  onlineGracePositionRecords: [],
  onlineBossPositionRecords: [],
  onlineMapConversionRecords: [],
  onlineItemRecords: [],
  onlineEntityRecords: [],
  onlineGatheringRecords: [],
  coordinateItemTotal: 0,
  coordinateGracePositionTotal: 0,
  coordinateBossPositionTotal: 0,
  coordinateMapConversionTotal: 0,
  coordinateEntityTotal: 0,
  coordinateGatheringTotal: 0,
 nodes: new Map(),
  layer: "all",
  origin: "grace_avenue_balcony",
  destination: "item_bolt_of_gransax",
  conditions: new Set(DEFAULT_CONDITIONS),
  routeProfiles: null,
  routeProfile: DEFAULT_ROUTE_PROFILE,
  preference: "balanced",
  zoom: 1,
  route: null,
  selectedNode: "gatefront",
};

const els = {
  origin: document.getElementById("origin-select"),
  destination: document.getElementById("destination-select"),
  routeProfile: document.getElementById("route-profile-select"),
  routeProfileHint: document.getElementById("route-profile-hint"),
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
  coordinateMapSelect: document.getElementById("coordinate-map-select"),
  coordinateEntityKind: document.getElementById("coordinate-entity-kind"),
  mapModes: document.querySelectorAll(".map-mode"),
 onlinePoiKind: document.getElementById("online-poi-kind"),
  onlinePoiQuery: document.getElementById("online-poi-query"),
  onlinePoiSearch: document.getElementById("online-poi-search"),
  onlinePoiResults: document.getElementById("online-poi-results"),
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

function onlineNameKey(value) {
  return String(value || "").toLowerCase().replace(/\([^)]*\)/g, "").replace(/[^a-z0-9]+/g, "");
}

function findOnlineMapPointForRouteName(name, regionName) {
  const raw = String(name || "");
  const variants = new Set([raw, raw.replace(/\s*\([^)]*\)\s*$/, "")]);
  const inner = raw.match(/\(([^)]+)\)/);
  if (inner) variants.add(inner[1]);
  const keys = [...variants].map(onlineNameKey).filter(Boolean);
  const matches = state.onlineMapPointRecords.filter((record) =>
    (record.names || []).some((label) => keys.includes(onlineNameKey(label)))
  );
  const regionKey = onlineNameKey(regionName);
  const regional = matches.filter((record) => {
    const tile = state.onlineTileRecords.find((item) => item.mapKey === record.mapKey);
    const tileText = onlineNameKey((tile?.subRegion || "") + " " + (tile?.majorRegion || ""));
    return regionKey && tileText && (tileText.includes(regionKey) || regionKey.includes(tileText));
  });
  const narrowed = regional.length ? regional : matches;
  return narrowed.length === 1 ? narrowed[0] : null;
}

function nodeLabel(id) {
  return state.nodes.get(id)?.label || id;
}

function activeRouteProfile() {
  return state.routeProfiles?.profiles?.find((profile) => profile.id === state.routeProfile)
    || state.routeProfiles?.profiles?.[0]
    || { id: DEFAULT_ROUTE_PROFILE, dynamicFastTravel: false, description: "仅使用正式物理拓扑边。" };
}

function isGraceNode(id) {
  return state.nodes.get(id)?.kind === "grace";
}

function fastTravelEdgesFrom(nodeId) {
  const profile = activeRouteProfile();
  const rule = state.routeProfiles?.fastTravelRule;
  if (!profile.dynamicFastTravel || !rule || !state.conditions.has(rule.id) || !isGraceNode(nodeId)) return [];

  return [...state.nodes.values()]
    .filter((node) => node.kind === "grace" && node.id !== nodeId)
    .map((node) => ({
      id: `dynamic-fast-travel:${nodeId}:${node.id}`,
      from: nodeId,
      to: node.id,
      mode: "地图快速旅行（目标赐福需已发现）",
      cost: 1,
      risk: 0,
      direction: "teleport",
      transitionType: "map_fast_travel",
      requires: [rule.id],
      sourceEvidence: rule.sourceEvidence || [],
      verificationState: "online_cross_checked",
      dynamic: true,
      note: "规划层动态边；不写入 formal graph，不代表玩家已经激活目标赐福。",
      tags: ["fast_travel", "profile_only", "conditional"],
    }));
}

function outgoingEdgesFrom(nodeId) {
  return state.data.edges
    .filter((edge) => edge.from === nodeId)
    .concat(fastTravelEdgesFrom(nodeId));
}

function edgeIsAvailable(edge) {
  if (edge.routeable === false) return false;
  return (edge.requires || []).every((condition) => state.conditions.has(condition));
}

function findBestGraceOrigin(targetId, excludedGraceIds = new Set()) {
  const fastTravelRule = state.routeProfiles?.fastTravelRule;
  if (
    activeRouteProfile().dynamicFastTravel
    && fastTravelRule
    && state.conditions.has(fastTravelRule.id)
    && isGraceNode(state.origin)
    && !excludedGraceIds.has(state.origin)
  ) {
    return state.origin;
  }
  const incoming = new Map();
  state.data.edges.filter((edge) => edgeIsAvailable(edge)).forEach((edge) => {
    if (!incoming.has(edge.to)) incoming.set(edge.to, []);
    incoming.get(edge.to).push(edge);
  });
  const distances = new Map([[targetId, 0]]);
  const unvisited = new Set(state.data.nodes.map((node) => node.id));
  while (unvisited.size) {
    let current = null;
    let currentDistance = Number.POSITIVE_INFINITY;
    for (const id of unvisited) {
      const distance = distances.get(id) ?? Number.POSITIVE_INFINITY;
      if (distance < currentDistance) {
        current = id;
        currentDistance = distance;
      }
    }
    if (!current) break;
    unvisited.delete(current);
    incoming.get(current)?.forEach((edge) => {
      if (!unvisited.has(edge.from)) return;
      const candidate = currentDistance + Number(edge.cost) + Number(edge.risk || 0) * getPreferenceRiskWeight();
      if (candidate < (distances.get(edge.from) ?? Number.POSITIVE_INFINITY)) distances.set(edge.from, candidate);
    });
  }
  return [...state.nodes.values()]
    .filter((node) => node.kind === "grace" && !excludedGraceIds.has(node.id) && distances.has(node.id))
    .sort((a, b) => distances.get(a.id) - distances.get(b.id))[0]?.id || null;
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

    outgoingEdgesFrom(current)
      .filter((edge) => edgeIsAvailable(edge))
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
    [...reachable].forEach((nodeId) => {
      outgoingEdgesFrom(nodeId).forEach((edge) => {
        if (edgeIsAvailable(edge) && !reachable.has(edge.to)) {
          reachable.add(edge.to);
          changed = true;
        }
      });
    });
  }
  const missing = new Set();
  [...state.data.edges, ...(state.data.candidateEdges || [])].forEach((edge) => {
    if (reachable.has(edge.from) && !reachable.has(edge.to)) {
      (edge.requires || []).filter((id) => !state.conditions.has(id)).forEach((id) => missing.add(id));
    }
  });
  if (activeRouteProfile().dynamicFastTravel && !state.conditions.has(state.routeProfiles?.fastTravelRule?.id)) {
    missing.add(state.routeProfiles.fastTravelRule.id);
  }
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

function populateRouteProfiles() {
  const profiles = state.routeProfiles?.profiles || [];
  els.routeProfile.innerHTML = "";
  profiles.forEach((profile) => {
    const option = document.createElement("option");
    option.value = profile.id;
    option.textContent = profile.label;
    els.routeProfile.appendChild(option);
  });
  state.routeProfile = state.routeProfiles?.defaultProfile || DEFAULT_ROUTE_PROFILE;
  els.routeProfile.value = state.routeProfile;
  els.routeProfileHint.textContent = activeRouteProfile().description;
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
  if (state.mapMode === "coordinates") {
    renderCoordinateMap();
    return;
  }
  renderRegions();
  renderEdges();
  renderNodes();
  const coverage = state.onlineIndex?.manifest?.coverage;
 const onlineStats = coverage
    ? ` · 在线 P0 成就 ${state.achievementCatalog?.total_matches || state.achievementCatalog?.record_count || 0} / 坐标 ${coverage.gracePositionNonDummy} 赐福 / ${coverage.bossRecords} Boss / ${coverage.namedMapPointRecords} 地图点 / ${coverage.itemPlacementRecords} 物品 / ${coverage.entityRecords} 实体 / ${coverage.gatheringRecords} 采集节点 / ${coverage.tileRegionRecords} 地图层`
   : "";
  els.graphStats.textContent = `${state.data.nodes.length} 节点 · ${state.data.edges.length} 已证实边 · ${state.data.catalogRecordCount || 0} 赐福 · ${state.data.candidateRouteLegCount || 0} 候选路段${onlineStats} · ${state.data.meta.verificationLabel || "V1"}`;
}

function renderInspector() {
  const node = state.nodes.get(state.selectedNode);
  if (!node) return;
  const allEdges = [...state.data.edges, ...(state.data.candidateEdges || [])];
  const outgoing = allEdges.filter((edge) => edge.from === node.id).slice(0, 4);
  const incoming = allEdges.filter((edge) => edge.to === node.id).slice(0, 3);
  const connections = [...outgoing, ...incoming];
  const onlineBoss = state.onlineBossByNodeId.get(node.id) || state.onlineMapPointByNodeId.get(node.id) || node.onlineCoordinate;
  const onlineBinding = node.onlineCoordinate
    ? `<div class="inspector-online">Coordinate binding: ${node.onlineCoordinate.bindingBasis || "formal_candidate"} / role: ${node.onlineCoordinate.coordinateRole || "formal_node_anchor"}</div>`
    : "";
  const onlineTextLocation = node.onlineTextLocation
    ? `<div class="inspector-online">Online text location: ${node.onlineTextLocation.locationClaim}<br>Coordinate available: false<br>Reason: ${node.onlineTextLocation.reason}</div><button data-focus-location-anchor="${node.onlineTextLocation.anchorNodeId}">Open location anchor</button>`
    : "";
  const onlineCoordinateAction = onlineBoss && Array.isArray(onlineBoss.position)
    ? `<button data-focus-coordinate>定位在线坐标</button>`
    : "";
  const onlineEvidence = onlineBoss
    ? `<div class="inspector-online">在线坐标证据：${onlineBoss.name} · ${onlineBoss.map}<br>游戏坐标 X ${onlineBoss.position[0]} / Y ${onlineBoss.position[1]} / Z ${onlineBoss.position[2]}<br>来源：固定 Git JSON；仅用于定位证据，不改变正式拓扑。</div>`
    : "";
  const candidateTargetGroups = [...new Map(
    connections
      .filter((edge) => edge.targetGroup)
      .map((edge) => [edge.targetGroup.canonical_id, edge.targetGroup]),
  ).values()];
  const targetGroupMarkup = candidateTargetGroups.map((group) => {
    const subroutes = group.subroutes || [];
    const subrouteMarkup = subroutes.length
      ? subroutes.map((subroute) => `<div class="target-group-route"><span>${nodeLabel(subroute.entry_node_id)} → ${nodeLabel(subroute.target_node_id)}</span><span>${subroute.path_edge_ids.length} edges${subroute.requires?.length ? ` · requires ${subroute.requires.join(", ")}` : ""}</span></div>`).join("")
      : `<div class="target-group-route">No formal subroute; scope remains unresolved.</div>`;
    const itemMarkup = group.online_item_snapshot
      ? `<div class="target-group-items"><a href="/api/catalog/route-target-items" target="_blank" rel="noreferrer">Online item snapshot</a> · ${group.online_item_record_count} records · ${group.online_item_coordinate_count} coordinates · routeable=false</div>`
      : "";
    return `<div class="inspector-target-group"><div class="target-group-title">${group.label}</div><div class="target-group-meta">${group.scope} · routeable=false</div>${itemMarkup}${subrouteMarkup}</div>`;
  }).join("");
  els.nodeInspector.innerHTML = `
    <div class="inspector-card">
      <div class="inspector-head">
        <div><div class="inspector-title">${node.label}</div><div class="inspector-type">${node.kind.toUpperCase()} · ${node.layer.toUpperCase()}</div></div>
        <div class="inspector-region">${node.region}</div>
      </div>
      <p class="inspector-description">${node.description}</p>
       ${onlineEvidence}
       ${onlineBinding}
       ${onlineTextLocation}
       ${onlineCoordinateAction}
       ${targetGroupMarkup}
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
  const focusCoordinateButton = els.nodeInspector.querySelector("[data-focus-coordinate]");
  if (focusCoordinateButton) {
    focusCoordinateButton.addEventListener("click", () => {
      focusOnlineCoordinate(onlineBoss, "boss-positions", node.label);
    });
  }
  const focusLocationAnchorButton = els.nodeInspector.querySelector("[data-focus-location-anchor]");
  if (focusLocationAnchorButton) {
    focusLocationAnchorButton.addEventListener("click", () => {
      state.mapMode = "topology";
      els.coordinateMapSelect.hidden = true;
      els.coordinateEntityKind.hidden = true;
      els.mapModes.forEach((mapButton) => mapButton.classList.toggle("active", mapButton.dataset.mapMode === "topology"));
      renderGraph();
      selectNode(focusLocationAnchorButton.dataset.focusLocationAnchor);
    });
  }
}

function routeText(route) {
  const lines = [`RUNE//PATH 路线`, `${nodeLabel(state.origin)} → ${nodeLabel(state.destination)}`, `相对成本 ${route.time} · 风险指数 ${route.risk} · ${route.edges.length} 段`, ""];
  route.nodes.forEach((nodeId, index) => {
    lines.push(`${index + 1}. ${nodeLabel(nodeId)}${route.edges[index] ? ` —[${route.edges[index].mode}]→` : ""}`);
  });
  lines.splice(2, 0, `路线 profile：${activeRouteProfile().label || activeRouteProfile().id}`);
  if (route.edges.some((edge) => edge.dynamic)) lines.splice(3, 0, "注意：包含条件化地图快速旅行边，不代表玩家已激活所有目标赐福。");
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
  if (state.route.edges.some((edge) => edge.dynamic)) {
    els.routeNotice.textContent = "本路线使用了动态地图快速旅行边；它不计入物理拓扑，目标赐福必须已发现，且当前状态允许快速旅行。";
  }
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
  if (state.mapMode === "coordinates" && state.coordinateBounds) {
    const bounds = state.coordinateBounds;
    const centerX = bounds.minX + bounds.width / 2;
    const centerY = bounds.minY + bounds.height / 2;
    els.mapTransform.setAttribute("transform", "translate(" + centerX + " " + centerY + ") scale(" + state.zoom + ") translate(" + (-centerX) + " " + (-centerY) + ")");
    return;
  }
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

function renderOnlinePoiResults(payload, kind) {
  els.onlinePoiResults.innerHTML = "";
  if (!payload.records?.length) {
    els.onlinePoiResults.textContent = "没有匹配的在线记录。";
    return;
  }
  const summary = document.createElement("div");
  summary.className = "online-poi-summary";
  summary.textContent = kind === "achievements"
    ? "匹配 " + payload.total_matches + " 项，显示 " + payload.record_count + " 项；成就目标不会自动变成路线边。"
    : "匹配 " + payload.total_matches + " 条，显示 " + payload.record_count + " 条；仅为坐标证据。";
  els.onlinePoiResults.appendChild(summary);
  payload.records.forEach((record) => {
    const row = document.createElement("div");
    row.className = "online-poi-result";
    const title = document.createElement("strong");
    if (kind === "achievements") {
      title.textContent = record.name || record.canonical_id;
    } else if (kind === "items") {
      title.textContent = (record.items || []).map((item) => item.name || item.id).join(" / ") || "unnamed item";
    } else if (kind === "map-points") {
      title.textContent = (record.names || []).join(" / ") || ("map point " + record.id);
    } else if (kind === "grace-positions") {
      title.textContent = "raw grace position #" + record.source_index + " · " + (record.major_region || record.sub_region || "unknown region");
    } else {
      title.textContent = record.name || record.model || (record.kind ? record.kind + " entity" : "online record");
    }
    const detail = document.createElement("span");
    if (kind === "achievements") {
      const targetIds = [...new Set([...(record.formal_target_ids || []), ...(record.location_target_ids || [])])];
      const targets = targetIds.map((id) => nodeLabel(id)).join(" / ") || "未绑定正式目标节点";
      const requirements = (record.external_requirements || []).join("；");
      const prerequisiteTargets = (record.prerequisite_target_ids || []).map((id) => nodeLabel(id)).join(" / ");
      const itemEvidence = record.online_item_evidence || [];
      const textLocationEvidence = record.online_text_location_evidence || [];
      detail.textContent = record.category + " · " + record.coverage_state + " · " + targets
        + (prerequisiteTargets ? " · 前置节点：" + prerequisiteTargets : "")
        + (itemEvidence.length ? " · 在线物品定位：" + itemEvidence.length + "/" + (record.required_item_names || []).length : "")
        + (textLocationEvidence.length ? " · 文本地点证据：" + textLocationEvidence.length : "")
        + (requirements ? " · 条件：" + requirements : "");
    } else {
      const position = record.position || [];
      detail.textContent = (record.map || (record.current_map || "ID " + (record.id || record.source_index))) + " · X " + position[0] + " / Y " + position[1] + " / Z " + position[2];
    }
    row.append(title, detail);
    if (kind === "achievements") {
      const itemEvidence = record.online_item_evidence || [];
      const textLocationEvidence = record.online_text_location_evidence || [];
      const targetId = [...(record.formal_target_ids || []), ...(record.location_target_ids || [])].find((id) => state.nodes.has(id));
      if (record.category === "collection" && textLocationEvidence.length) {
        const locationList = document.createElement("div");
        locationList.className = "online-text-location-list";
        textLocationEvidence.forEach((evidence) => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "online-text-location-button";
          button.textContent = evidence.item + " → " + nodeLabel(evidence.formal_target_id) + " · 文本地点";
          button.addEventListener("click", (event) => {
            event.stopPropagation();
            const locationTarget = evidence.formal_target_id;
            const originId = findBestGraceOrigin(locationTarget, new Set([locationTarget]));
            if (originId) {
              state.origin = originId;
              state.destination = locationTarget;
              els.origin.value = originId;
              els.destination.value = locationTarget;
            }
            state.selectedNode = locationTarget;
            state.mapMode = "topology";
            els.coordinateMapSelect.hidden = true;
            els.coordinateEntityKind.hidden = true;
            els.mapModes.forEach((mapButton) => mapButton.classList.toggle("active", mapButton.dataset.mapMode === "topology"));
            planAndRender();
            els.mapToast.textContent = record.name + " · " + evidence.item + "：文本地点证据，不声明 XYZ 坐标。";
          });
          locationList.appendChild(button);
        });
        row.appendChild(locationList);
      }
      if (record.category === "collection" && itemEvidence.length) {
        row.classList.add("clickable");
        row.addEventListener("click", () => {
          const evidence = itemEvidence[0];
          state.mapMode = "coordinates";
          state.coordinateMapId = evidence.map;
          state.coordinateEntityKind = "all";
          els.coordinateMapSelect.hidden = false;
          els.coordinateEntityKind.hidden = false;
          els.coordinateEntityKind.value = "all";
          els.mapModes.forEach((button) => button.classList.toggle("active", button.dataset.mapMode === "coordinates"));
          populateCoordinateMapSelect();
          els.coordinateMapSelect.value = state.coordinateMapId;
          loadCoordinateItems();
          els.mapToast.textContent = record.name + " · 已定位在线物品坐标：" + evidence.map + " · " + evidence.matched_requirements.join(" / ");
        });
      } else if (targetId) {
        row.classList.add("clickable");
        row.addEventListener("click", () => {
          const originId = findBestGraceOrigin(targetId, new Set([targetId]));
          if (originId) {
            state.origin = originId;
            state.destination = targetId;
            els.origin.value = originId;
            els.destination.value = targetId;
          }
          state.selectedNode = targetId;
          state.mapMode = "topology";
          els.coordinateMapSelect.hidden = true;
          els.coordinateEntityKind.hidden = true;
          els.mapModes.forEach((button) => button.classList.toggle("active", button.dataset.mapMode === "topology"));
          planAndRender();
          els.mapToast.textContent = record.name + " · 已定位正式目标节点：" + nodeLabel(targetId) + (originId ? " · 起点：" + nodeLabel(originId) : "");
        });
      }
    } else if (["map-points", "items", "boss-positions", "entities", "gathering", "grace-positions"].includes(kind)) {
      row.classList.add("clickable");
      row.addEventListener("click", () => {
        const label = title.textContent || "online coordinate";
        if (!focusOnlineCoordinate(record, kind, label)) {
          els.mapToast.textContent = "该在线记录缺少可定位的地图层或 XYZ。";
        }
      });
    }
    els.onlinePoiResults.appendChild(row);
  });
}

async function searchOnlinePoi() {
  const query = els.onlinePoiQuery.value.trim();
  if (!query) {
    els.onlinePoiResults.textContent = "请输入名称后查询。";
    return;
  }
  const kind = els.onlinePoiKind.value;
  const params = new URLSearchParams({ q: query, limit: "20" });
  els.onlinePoiResults.textContent = "正在读取固定在线快照……";
  try {
    const endpoint = kind === "map-points" ? "map-points" : kind === "items" ? "online-items" : kind;
    const response = await fetch("/api/catalog/" + endpoint + "?" + params, { cache: "no-store" });
    if (!response.ok) throw new Error("HTTP " + response.status);
    renderOnlinePoiResults(await response.json(), kind);
  } catch (error) {
    els.onlinePoiResults.textContent = "在线 POI 查询失败：" + error.message;
  }
}

function wireEvents() {
  els.mapModes.forEach((button) => button.addEventListener("click", () => {
    state.mapMode = button.dataset.mapMode;
    els.mapModes.forEach((item) => item.classList.toggle("active", item === button));
    els.coordinateMapSelect.hidden = state.mapMode !== "coordinates";
    els.coordinateEntityKind.hidden = state.mapMode !== "coordinates";
    if (state.mapMode === "coordinates") {
      populateCoordinateMapSelect();
      renderCoordinateMap();
      loadCoordinateItems();
    } else {
      state.coordinateBounds = null;
      state.coordinateFocus = null;
      applyMapCoordinateSpace();
      renderGraph();
    }
  }));
  els.coordinateMapSelect.addEventListener("change", () => {
    state.coordinateMapId = els.coordinateMapSelect.value;
    state.coordinateFocus = null;
    loadCoordinateItems();
  });
  els.coordinateEntityKind.addEventListener("change", () => {
    state.coordinateEntityKind = els.coordinateEntityKind.value;
    loadCoordinateItems();
  });
 els.origin.addEventListener("change", () => { state.origin = els.origin.value; state.selectedNode = state.origin; planAndRender(); });
  els.destination.addEventListener("change", () => { state.destination = els.destination.value; state.selectedNode = state.destination; planAndRender(); });
  els.routeProfile.addEventListener("change", () => {
    state.routeProfile = els.routeProfile.value;
    els.routeProfileHint.textContent = activeRouteProfile().description;
    planAndRender();
  });
  els.plan.addEventListener("click", planAndRender);
  els.reset.addEventListener("click", () => {
    state.origin = state.data.defaultOrigin || state.data.nodes[0]?.id;
    state.destination = state.data.defaultDestination || state.data.nodes.at(-1)?.id;
    state.conditions = new Set(state.data.defaultConditions || DEFAULT_CONDITIONS);
    state.preference = "balanced";
    state.routeProfile = state.routeProfiles?.defaultProfile || DEFAULT_ROUTE_PROFILE;
    state.layer = "all";
    state.selectedNode = state.origin;
    els.origin.value = state.origin;
    els.destination.value = state.destination;
    els.routeProfile.value = state.routeProfile;
    els.routeProfileHint.textContent = activeRouteProfile().description;
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
  els.onlinePoiSearch.addEventListener("click", searchOnlinePoi);
  els.onlinePoiQuery.addEventListener("keydown", (event) => {
    if (event.key === "Enter") searchOnlinePoi();
  });
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
    const [graphResponse, catalogResponse, achievementResponse, routeLegResponse, routeTargetGroupResponse, routeProfileResponse, onlineIndexResponse, onlineMapKeyResponse, onlineBossResponse, onlineMapPoint1Response, onlineMapPoint2Response, onlineMapPoint3Response, onlineTile1Response, onlineTile2Response] = await Promise.all([
      fetch("/api/graph", { cache: "no-store" }),
      fetch("/api/catalog/sites-of-grace", { cache: "no-store" }),
      fetch("/api/catalog/achievements", { cache: "no-store" }),
      fetch("/api/catalog/route-legs", { cache: "no-store" }),
      fetch("/api/catalog/route-target-groups", { cache: "no-store" }),
      fetch("/api/route-profiles", { cache: "no-store" }),
      fetch("/api/online-index", { cache: "no-store" }),
      fetch("/api/online-map-keys", { cache: "no-store" }),
      fetch("/data/v1/source-snapshots/mapforgoblins-boss-positions-20260818.json", { cache: "no-store" }),
      fetch("/data/v1/source-snapshots/mapforgoblins-map-points-part1-20260818.json", { cache: "no-store" }),
      fetch("/data/v1/source-snapshots/mapforgoblins-map-points-part2-20260818.json", { cache: "no-store" }),
      fetch("/data/v1/source-snapshots/mapforgoblins-map-points-part3-20260818.json", { cache: "no-store" }),
      fetch("/data/v1/source-snapshots/mapforgoblins-tile-regions-part1-20260818.json", { cache: "no-store" }),
      fetch("/data/v1/source-snapshots/mapforgoblins-tile-regions-part2-20260818.json", { cache: "no-store" }),
   ]);
    if (!routeProfileResponse.ok) throw new Error(`route profile HTTP ${routeProfileResponse.status}`);
    if (!graphResponse.ok) throw new Error(`图数据 HTTP ${graphResponse.status}`);
    if (!catalogResponse.ok) throw new Error(`赐福目录 HTTP ${catalogResponse.status}`);
    if (!achievementResponse.ok) throw new Error(`成就目录 HTTP ${achievementResponse.status}`);
    if (!routeLegResponse.ok) throw new Error(`候选路线 HTTP ${routeLegResponse.status}`);
    if (!routeTargetGroupResponse.ok) throw new Error(`route target groups HTTP ${routeTargetGroupResponse.status}`);
    state.data = await graphResponse.json();
    els.datasetVersion.textContent = state.data.meta?.version || "Online Verified V1";
    state.routeProfiles = await routeProfileResponse.json();
    state.achievementCatalog = await achievementResponse.json();
    if (!onlineIndexResponse.ok) throw new Error(`online index HTTP ${onlineIndexResponse.status}`);
    if (!onlineMapKeyResponse.ok) throw new Error(`online map keys HTTP ${onlineMapKeyResponse.status}`);
    if (!onlineBossResponse.ok) throw new Error(`online boss coordinates HTTP ${onlineBossResponse.status}`);
    if (!onlineMapPoint1Response.ok || !onlineMapPoint2Response.ok || !onlineMapPoint3Response.ok) throw new Error("online map point coordinates unavailable");
    if (!onlineTile1Response.ok || !onlineTile2Response.ok) throw new Error("online tile region index unavailable");
    state.onlineIndex = {
      manifest: await onlineIndexResponse.json(),
      mapKeys: await onlineMapKeyResponse.json(),
      bosses: await onlineBossResponse.json(),
      mapPoints: await Promise.all([onlineMapPoint1Response.json(), onlineMapPoint2Response.json(), onlineMapPoint3Response.json()]),
      tiles: await Promise.all([onlineTile1Response.json(), onlineTile2Response.json()]),
    };
    state.onlineBossByNodeId = new Map();
    state.onlineIndex.bosses.records.forEach((record) => {
      const formalCandidates = record[13] || [];
      if (formalCandidates.length === 1) {
        state.onlineBossByNodeId.set(formalCandidates[0], {
          name: record[1],
          map: record[2],
          position: [record[6], record[7], record[8]],
          sourceIndex: record[0],
        });
      }
    });
    state.onlineMapPointByNodeId = new Map();
    state.onlineIndex.mapPoints.forEach((payload) => {
      payload.records.forEach((record) => {
        const formalCandidates = record[10] || [];
        if (formalCandidates.length === 1) {
          state.onlineMapPointByNodeId.set(formalCandidates[0], {
            name: (record[9] || []).join(" / "),
            map: `area ${record[3]} / grid ${record[4]},${record[5]}`,
            position: [record[6], record[7], record[8]],
            sourceIndex: record[0],
          });
        }
      });
    });
    state.onlineMapPointRecords = [];
    state.onlineIndex.mapPoints.forEach((payload) => {
      payload.records.forEach((record) => {
        state.onlineMapPointRecords.push({
          sourceIndex: record[0],
          id: record[1],
          snapshot: `mapforgoblins-map-points-part${payload.part}-20260818`,
          mapKey: mapKeyFromParts(record[3], record[4], record[5]),
          position: [record[6], record[7], record[8]],
          names: record[9] || [],
          formalCandidates: record[10] || [],
        });
      });
    });
    state.onlineTileRecords = state.onlineIndex.tiles.flatMap((payload) => payload.records.map((record) => ({
      mapKey: record[0],
      subRegion: record[3],
      majorRegion: record[4],
      graceCount: record[5],
    })));
    populateCoordinateMapSelect();
    const fastTravelRule = state.routeProfiles.fastTravelRule;
    if (fastTravelRule && !state.data.conditions.some((condition) => condition.id === fastTravelRule.id)) {
      state.data.conditions.push(fastTravelRule);
    }
    applyMapCoordinateSpace();
    const catalog = await catalogResponse.json();
    const routeLegCatalog = await routeLegResponse.json();
    const routeTargetGroupCatalog = await routeTargetGroupResponse.json();
    const routeTargetGroupByLegId = new Map(
      (routeTargetGroupCatalog.records || []).map((group) => [group.route_leg_id, group]),
    );
    const regionSlots = new Map();
    const sourceNameToNodeId = new Map([
      ["Avenue Balcony", "grace_avenue_balcony"],
      ["Lower Capital Church", "grace_leyndell_royal_capital_main_lower_capital_church"],
      ["West Capital Rampart", "grace_leyndell_royal_capital_main_west_capital_rampart"],
      ["Fortified Manor, First Floor", "grace_leyndell_royal_capital_main_fortified_manor_first_floor"],
      ["Divine Bridge", "grace_leyndell_royal_capital_main_divine_bridge"],
      ["Isolated Divine Tower", "grace_caelid_greyoll_s_dragonbarrow_isolated_divine_tower"],
      ["Forbidden Lands", "grace_mountaintops_of_the_giants_forbidden_lands_forbidden_lands"],
      ["Fell Twins", "fell_twins_gate"],
      ["Divine Tower of East Altus: Gate", "grace_mountaintops_of_the_giants_forbidden_lands_divine_tower_of_east_altus_gate"],
      ["Divine Tower of East Altus", "grace_mountaintops_of_the_giants_forbidden_lands_divine_tower_of_east_altus"],
      ["Godfrey, First Elden Lord (golden shade)", "godfrey_royal_capital_gate"],
      ["Erdtree Sanctuary", "grace_erdtree_sanctuary"],
      ["Elden Throne", "grace_elden_throne"],
      ["Siofra River Well Depths", "grace_siofra_well_depths"],
      ["Siofra River Bank", "grace_siofra_river_bank"],
      ["Hallowhorn Grounds (Siofra River)", "hallowhorn_grounds_siofra"],
      ["Ancestor Spirit", "ancestor_spirit_siofra_gate"],
      ["Ancestor Spirit (post-boss return)", "grace_siofra_ancestor_spirit_post_boss"],
      ["Below the Well", "grace_siofra_river_below_the_well"],
      ["Deep Siofra Well lift", "siofra_deep_well_lift"],
      ["Deep Siofra Well", "grace_deep_siofra_well"],
      ["Hidden Arcane Waygate (Siofra)", "siofra_hidden_waygate"],
      ["Dragonkin Soldier (Siofra River)", "dragonkin_soldier_siofra_gate"],
      ["Dragonkin Soldier (Siofra post-boss state)", "siofra_dragonkin_post_boss_state"],
      ["Crumbling Beast Grave", "grace_crumbling_beast_grave"],
      ["Crumbling Beast Grave Depths", "grace_crumbling_beast_grave_depths"],
      ["Tempest-Facing Balcony", "grace_farum_tempest_facing_balcony"],
      ["Dragon Temple", "farum_dragon_temple_approach"],
      ["Dragon Temple Transept", "grace_farum_dragon_temple_transept"],
      ["Beside the Great Bridge", "grace_beside_great_bridge"],
      ["Dragon Temple Altar", "grace_dragon_temple_altar"],
      ["Dragon Temple Lift", "grace_farum_dragon_temple_lift"],
      ["Dragon Temple Rooftop", "grace_farum_dragon_temple_rooftop"],
      ["Dragonlord Placidusax", "dragonlord_placidusax_gate"],
      ["Dragonlord Placidusax (post-boss grace)", "grace_farum_dragonlord_placidusax"],
      ["Maliketh", "maliketh_gate"],
      ["Maliketh, the Black Blade", "grace_maliketh_black_blade"],
      ["Leyndell, Capital of Ash", "grace_leyndell_capital_of_ash"],
      ["Gravesite Plain", "grace_shadow_realm_gravesite_plain"],
      ["Scorched Ruins", "grace_gravesite_plain_main_scorched_ruins"],
      ["Three-Path Cross", "grace_shadow_realm_three_path_cross"],
      ["Greatbridge, North", "grace_gravesite_plain_main_greatbridge_north"],
      ["Belurat Gaol", "grace_shadow_realm_belurat_gaol"],
      ["Fog Rift Catacombs", "grace_shadow_realm_fog_rift_catacombs"],
      ["Rivermouth Cave", "grace_shadow_realm_rivermouth_cave"],
      ["Scorpion River Catacombs", "grace_shadow_realm_scorpion_river_catacombs"],
      ["Ruined Forge Lava Intake", "grace_shadow_realm_ruined_forge_lava_intake"],
      ["Taylew's Ruined Forge", "grace_shadow_realm_taylew_ruined_forge"],
      ["Ruined Forge of Starfall Past", "grace_shadow_realm_ruined_forge_starfall_past"],
      ["Church of Consolation", "landmark_church_of_consolation"],
      ["Main Gate Cross", "grace_shadow_realm_main_gate_cross"],
      ["Belurat, Tower Settlement", "grace_belurat_tower_settlement"],
      ["Small Private Altar", "grace_land_of_the_tower_belurat_tower_settlement_small_private_altar"],
      ["Stagefront", "grace_land_of_the_tower_belurat_tower_settlement_stagefront"],
      ["Divine Beast Dancing Lion", "divine_beast_dancing_lion_gate"],
      ["Theatre of the Divine Beast", "grace_belurat_theatre_divine_beast"],
      ["Pillar Path Cross", "grace_shadow_realm_pillar_path_cross"],
      ["Pillar Path Waypoint", "grace_gravesite_plain_main_pillar_path_waypoint"],
      ["Cliffroad Terminus", "grace_shadow_realm_cliffroad_terminus"],
      ["Highroad Cross", "grace_scadu_altus_highroad_cross"],
      ["Moorth Ruins", "grace_scadu_altus_moorth_ruins"],
      ["Scaduview Cross", "grace_scadu_altus_main_scaduview_cross"],
      ["Moorth Highway, South", "grace_scadu_altus_main_moorth_highway_south"],
      ["Bonny Village", "grace_scadu_altus_bonny_village"],
      ["Bonny Gaol", "grace_scadu_altus_main_bonny_gaol"],
      ["Behind the Fort of Reprimand", "grace_scadu_altus_main_behind_the_fort_of_reprimand"],
      ["Fort of Reprimand", "grace_scadu_altus_main_fort_of_reprimand"],
      ["Scadu Altus, West", "grace_scadu_altus_main_scadu_altus_west"],
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
      ["West Rampart", "grace_shadow_keep_specimen_storehouse_west_rampart"],
      ["Storehouse, Fourth Floor", "grace_shadow_keep_storehouse_fourth_floor"],
      ["Storehouse, Seventh Floor", "grace_shadow_keep_storehouse_seventh_floor"],
      ["Dark Chamber Entrance", "grace_shadow_keep_specimen_storehouse_dark_chamber_entrance"],
      ["Messmer the Impaler", "messmer_gate"],
      ["Messmer's Dark Chamber", "grace_shadow_keep_messmer_dark_chamber"],
      ["Storehouse, Back Section", "grace_shadow_keep_storehouse_back_section"],
      ["Storehouse, Loft", "grace_shadow_keep_storehouse_loft"],
      ["Shadow Keep, Black Gate", "grace_shadow_keep_back_gate"],
      ["Shadow Keep, Back Gate", "grace_shadow_keep_back_gate"],
      ["Scaduview", "grace_shadow_keep_scaduview"],
      ["Commander Gaius", "commander_gaius_gate"],
      ["Scadutree Base", "grace_shadow_keep_scadutree_base"],
      ["Ancient Ruins Base", "grace_rauh_ancient_ruins_base"],
      ["Temple Town Ruins", "grace_land_of_the_tower_rauh_base_temple_town_ruins"],
      ["Ravine North", "grace_land_of_the_tower_rauh_base_ravine_north"],
      ["Viaduct Minor Tower", "grace_rauh_viaduct_minor_tower"],
      ["Rauh Ancient Ruins, East", "grace_rauh_ancient_ruins_east"],
      ["Rauh Ancient Ruins, West", "grace_rauh_ancient_ruins_west"],
      ["Ancient Ruins, Grand Stairway", "grace_land_of_the_tower_ancient_ruins_of_rauh_ancient_ruins_grand_stairway"],
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
      ["Forsaken Graveyard", "grace_scadu_altus_abyssal_woods_forsaken_graveyard"],
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
      ["Finger Birthing Grounds", "grace_scadu_altus_main_finger_birthing_grounds"],
      ["Charo's Hidden Grave", "grace_gravesite_plain_charo_s_hidden_grave_charo_s_hidden_grave"],
      ["Lamenter's Gaol", "grace_gravesite_plain_charo_s_hidden_grave_lamenter_s_gaol"],
      ["Lamenter", "lamenter_gate"],
      ["Lamenter's Gaol Post-Boss", "lamenter_post_state"],
      ["Scadutree Avatar", "scadutree_avatar_gate"],
      ["Agheel Lake South", "grace_limgrave_main_agheel_lake_south"],
      ["Bridge of Sacrifice", "grace_limgrave_weeping_peninsula_bridge_of_sacrifice"],
      ["Castle Morne Rampart", "grace_limgrave_weeping_peninsula_castle_morne_rampart"],
      ["Castle Morne Lift", "grace_limgrave_weeping_peninsula_castle_morne_lift"],
      ["Behind the Castle", "grace_limgrave_weeping_peninsula_behind_the_castle"],
      ["Beside the Rampart Gaol", "grace_limgrave_weeping_peninsula_beside_the_rampart_gaol"],
      ["Morne Tunnel", "grace_limgrave_weeping_peninsula_morne_tunnel"],
      ["Leonine Misbegotten", "leonine_misbegotten_gate"],
      ["Morne Moangrave", "grace_limgrave_weeping_peninsula_morne_moangrave"],
      ["Castleward Tunnel", "grace_limgrave_stormhill_castleward_tunnel"],
      ["Margit, the Fell Omen", "margit_fell_omen_gate"],
      ["Margit, the Fell Omen Grace", "grace_limgrave_stormhill_margit_the_fell_omen"],
      ["Liurnia Lake Shore", "grace_liurnia_of_the_lakes_main_liurnia_lake_shore"],
      ["Laskyar Ruins", "grace_liurnia_of_the_lakes_main_laskyar_ruins"],
      ["Liurnia Highway South", "grace_liurnia_of_the_lakes_main_liurnia_highway_south"],
      ["Liurnia Highway North", "grace_liurnia_of_the_lakes_main_liurnia_highway_north"],
      ["Gate Town Bridge", "grace_liurnia_of_the_lakes_main_gate_town_bridge"],
      ["Fallen Ruins of the Lake", "grace_liurnia_of_the_lakes_main_fallen_ruins_of_the_lake"],
      ["Temple Quarter", "grace_liurnia_of_the_lakes_main_temple_quarter"],
      ["Crystalline Woods", "grace_liurnia_of_the_lakes_main_crystalline_woods"],
      ["Sorcerer's Isle", "grace_liurnia_of_the_lakes_main_sorcerer_s_isle"],
      ["East Gate Bridge Trestle", "grace_liurnia_of_the_lakes_main_east_gate_bridge_trestle"],
      ["Academy Gate Town", "grace_liurnia_of_the_lakes_main_academy_gate_town"],
      ["South Raya Lucaria Gate", "grace_liurnia_of_the_lakes_main_south_raya_lucaria_gate"],
      ["Northern Liurnia Lake Shore", "grace_liurnia_of_the_lakes_main_northern_liurnia_lake_shore"],
      ["Road to the Manor", "grace_liurnia_of_the_lakes_main_road_to_the_manor"],
      ["Main Caria Manor Gate", "grace_liurnia_of_the_lakes_main_main_caria_manor_gate"],
      ["Manor Lower Level", "grace_liurnia_of_the_lakes_main_manor_lower_level"],
      ["Manor Upper Level", "grace_liurnia_of_the_lakes_main_manor_upper_level"],
      ["Royal Knight Loretta", "royal_knight_loretta_caria_gate"],
      ["Royal Moongazing Grounds", "grace_liurnia_of_the_lakes_main_royal_moongazing_grounds"],
      ["Behind Caria Manor", "grace_liurnia_of_the_lakes_main_behind_caria_manor"],
      ["Ranni's Rise", "grace_liurnia_of_the_lakes_main_ranni_s_rise"],
      ["Ranni's Chamber", "grace_liurnia_of_the_lakes_main_ranni_s_chamber"],
      ["Gate Town North", "grace_liurnia_of_the_lakes_main_gate_town_north"],
      ["Eastern Liurnia Lake Shore", "grace_liurnia_of_the_lakes_main_eastern_liurnia_lake_shore"],
      ["Eastern Tableland", "grace_liurnia_of_the_lakes_main_eastern_tableland"],
      ["Study Hall Entrance", "grace_liurnia_of_the_lakes_main_study_hall_entrance"],
      ["Liurnia Tower Bridge", "grace_liurnia_of_the_lakes_main_liurnia_tower_bridge"],
      ["Divine Tower of Liurnia", "grace_liurnia_of_the_lakes_main_divine_tower_of_liurnia"],
      ["East Raya Lucaria Gate", "grace_liurnia_of_the_lakes_bellum_highway_east_raya_lucaria_gate"],
      ["Bellum Church", "grace_liurnia_of_the_lakes_bellum_highway_bellum_church"],
      ["The Ravine", "grace_liurnia_of_the_lakes_main_the_ravine"],
      ["Ravine-Veiled Village", "grace_liurnia_of_the_lakes_main_ravine_veiled_village"],
      ["Ruin-Strewn Precipice", "grace_liurnia_of_the_lakes_ruin_strewn_precipice_ruin_strewn_precipice"],
      ["Ruin-Strewn Precipice Overlook", "grace_liurnia_of_the_lakes_ruin_strewn_precipice_ruin_strewn_precipice_overlook"],
      ["Magma Wyrm Makar", "magma_wyrm_makar_gate"],
      ["Magma Wyrm Makar Grace", "grace_liurnia_of_the_lakes_ruin_strewn_precipice_magma_wyrm_makar"],
      ["Ninth Mt. Gelmir Campsite", "grace_altus_plateau_mt_gelmir_ninth_mt_gelmir_campsite"],
      ["Full-Grown Fallingstar Beast", "full_grown_fallingstar_beast_gate"],
      ["Seethewater River", "grace_altus_plateau_mt_gelmir_seethewater_river"],
      ["Auriza Hero's Grave", "grace_altus_plateau_main_auriza_hero_s_grave"],
      ["Auriza Side Tomb", "grace_altus_plateau_main_auriza_side_tomb"],
      ["Gelmir Hero's Grave", "grace_altus_plateau_main_gelmir_hero_s_grave"],
      ["Wyndham Catacombs", "grace_altus_plateau_main_wyndham_catacombs"],
      ["Seethewater Cave", "grace_altus_plateau_main_seethewater_cave"],
      ["Volcano Cave", "grace_altus_plateau_main_volcano_cave"],
      ["Altus Tunnel", "grace_altus_plateau_main_altus_tunnel"],
      ["Sainted Hero's Grave", "grace_altus_plateau_main_sainted_hero_s_grave"],
      ["Seethewater Terminus", "grace_altus_plateau_mt_gelmir_seethewater_terminus"],
      ["Craftsman's Shack", "grace_altus_plateau_mt_gelmir_craftsman_s_shack"],
      ["Primeval Sorcerer Azur", "grace_altus_plateau_mt_gelmir_primeval_sorcerer_azur"],
      ["Aeonia Swamp Shore", "grace_caelid_swamp_of_aeonia_aeonia_swamp_shore"],
      ["Heart of Aeonia", "grace_caelid_swamp_of_aeonia_heart_of_aeonia"],
      ["Inner Aeonia", "grace_caelid_swamp_of_aeonia_inner_aeonia"],
      ["Commander O'Neil", "commander_o_neil_gate"],
      ["Sellia Under-Stair", "grace_caelid_main_sellia_under_stair"],
      ["Sellia Backstreets", "grace_caelid_main_sellia_backstreets"],
      ["Chair-Crypt of Sellia", "grace_caelid_main_chair_crypt_of_sellia"],
      ["Dragonbarrow West", "grace_caelid_greyoll_s_dragonbarrow_dragonbarrow_west"],
      ["Farum Greatbridge", "grace_caelid_greyoll_s_dragonbarrow_farum_greatbridge"],
      ["Divine Tower of Caelid: Center", "grace_caelid_greyoll_s_dragonbarrow_divine_tower_of_caelid_center"],
      ["Divine Tower of Caelid: Basement", "grace_caelid_greyoll_s_dragonbarrow_divine_tower_of_caelid_basement"],
      ["Godskin Apostle (Divine Tower of Caelid)", "godskin_apostle_caelid_gate"],
      ["Limgrave Tower Bridge", "grace_limgrave_stormhill_limgrave_tower_bridge"],
      ["Divine Tower of Limgrave", "grace_limgrave_stormhill_divine_tower_of_limgrave"],
      ["Underground Roadside", "grace_leyndell_royal_capital_subterranean_shunning_grounds_underground_roadside"],
      ["Forsaken Depths", "grace_leyndell_royal_capital_subterranean_shunning_grounds_forsaken_depths"],
      ["Mohg, the Omen", "mohg_omen_gate"],
      ["Cathedral of the Forsaken", "grace_leyndell_royal_capital_subterranean_shunning_grounds_cathedral_of_the_forsaken"],
      ["Leyndell Catacombs", "grace_leyndell_royal_capital_subterranean_shunning_grounds_leyndell_catacombs"],
      ["Frenzied Flame Proscription", "grace_leyndell_royal_capital_subterranean_shunning_grounds_frenzied_flame_proscription"],
      ["Abandoned Coffin", "grace_altus_plateau_main_abandoned_coffin"],
      ["Erdtree-Gazing Hill", "grace_altus_plateau_main_erdtree_gazing_hill"],
      ["Forest-Spanning Greatbridge", "grace_altus_plateau_main_forest_spanning_greatbridge"],
      ["Windmill Village", "grace_altus_plateau_main_windmill_village"],
      ["Godskin Noble (Windmill Village)", "godskin_noble_altus_gate"],
      ["Windmill Heights", "grace_altus_plateau_main_windmill_heights"],
      ["Bower of Bounty", "grace_altus_plateau_main_bower_of_bounty"],
      ["Road of Iniquity Side Path", "grace_altus_plateau_main_road_of_iniquity_side_path"],
      ["Rampartside Path", "grace_altus_plateau_main_rampartside_path"],
      ["Shaded Castle Ramparts", "grace_altus_plateau_main_shaded_castle_ramparts"],
      ["Shaded Castle Inner Gate", "grace_altus_plateau_main_shaded_castle_inner_gate"],
      ["Elemer of the Briar", "elemer_of_the_briar_gate"],
      ["Castellan's Hall", "grace_altus_plateau_main_castellan_s_hall"],
      ["Bridge of Iniquity", "grace_altus_plateau_mt_gelmir_bridge_of_iniquity"],
      ["First Mt.Gelmir Campsite", "grace_altus_plateau_mt_gelmir_first_mt_gelmir_campsite"],
      ["Road of Iniquity", "grace_altus_plateau_mt_gelmir_road_of_iniquity"],
      ["Audience Pathway", "grace_volcano_manor_main_audience_pathway"],
      ["Rykard, Lord of Blasphemy", "rykard_lord_of_blasphemy_gate"],
      ["Rykard, Lord of Blasphemy Grace", "grace_volcano_manor_main_rykard_lord_of_blasphemy"],
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
      ["Ainsel River Well", "ainsel_well_surface_entrance"],
      ["Ainsel River Well lift", "ainsel_well_lift"],
      ["Ainsel River Well Depths", "grace_ainsel_river_main_ainsel_river_well_depths"],
      ["Ainsel River Sluice Gate", "grace_ainsel_river_main_ainsel_river_sluice_gate"],
      ["Ainsel River Downstream", "grace_ainsel_river_main_ainsel_river_downstream"],
      ["Dragonkin Soldier of Nokstella", "dragonkin_soldier_nokstella_gate"],
      ["Dragonkin Soldier of Nokstella (post-boss grace)", "grace_ainsel_river_main_dragonkin_soldier_of_nokstella"],
      ["Nokstella, Eternal City", "grace_nokstella_eternal_city"],
      ["Nokstella Waterfall Basin", "grace_nokstella_waterfall_basin"],
      ["Lake of Rot Shoreside", "grace_lake_of_rot_shoreside"],
      ["Grand Cloister", "grace_grand_cloister"],
      ["Astel, Naturalborn of the Void", "astel_naturalborn_gate"],
      ["Baleful Shadow", "baleful_shadow_gate"],
      ["Moonlight Altar", "grace_moonlight_altar"],
      ["Altar South", "grace_liurnia_of_the_lakes_moonlight_altar_altar_south"],
      ["Cathedral of Manus Celes", "grace_liurnia_of_the_lakes_moonlight_altar_cathedral_of_manus_celes"],
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
      ["Cave of the Forlorn", "grace_mountaintops_main_cave_of_forlorn"],
      ["Consecrated Snowfield Catacombs", "grace_mountaintops_main_consecrated_snowfield_catacombs"],
      ["Yelough Anix Tunnel", "grace_mountaintops_main_yelough_anix_tunnel"],
      ["Giant-Conquering Hero's Grave", "grace_mountaintops_main_giant_conquering_hero_s_grave"],
      ["Giants' Mountaintop Catacombs", "grace_mountaintops_main_giants_mountaintop_catacombs"],
      ["Spiritcaller's Cave", "grace_mountaintops_main_spiritcallers_cave"],
      ["Spiritcaller Cave", "grace_mountaintops_main_spiritcallers_cave"],
      ["The First Step", "grace_first_step"],
      ["Stranded Graveyard", "grace_limgrave_stranded_graveyard_stranded_graveyard"],
      ["Cave of Knowledge", "grace_limgrave_stranded_graveyard_cave_of_knowledge"],
      ["Foot of the Four Belfries", "grace_liurnia_of_the_lakes_main_foot_of_the_four_belfries"],
      ["The Four Belfries", "grace_liurnia_of_the_lakes_main_the_four_belfries"],
      ["Table of Lost Grace", "grace_roundtable_hold_main_table_of_lost_grace"],
      ["Agheel Lake North", "grace_limgrave_main_agheel_lake_north"],
      ["Seaside Ruins", "grace_limgrave_main_seaside_ruins"],
      ["Church of Dragon Communion", "grace_limgrave_main_church_of_dragon_communion"],
      ["Summonwater Village Outskirts", "grace_limgrave_main_summonwater_village_outskirts"],
      ["Waypoint Ruins Cellar", "grace_limgrave_main_waypoint_ruins_cellar"],
      ["Warmaster's Shack", "grace_limgrave_stormhill_warmasters_shack"],
      ["Ailing Village Outskirts", "grace_limgrave_weeping_peninsula_ailing_village_outskirts"],
      ["Beside the Crater-Pocked Glade", "grace_limgrave_weeping_peninsula_beside_the_crater_pocked_glade"],
      ["Beside the Crater-Pocked  Glade", "grace_limgrave_weeping_peninsula_beside_the_crater_pocked_glade"],
      ["Isolated Merchant's Shack", "grace_limgrave_weeping_peninsula_isolated_merchants_shack"],
      ["Tombsward", "grace_limgrave_weeping_peninsula_tombsward"],
      ["Boilprawn Shack", "grace_liurnia_of_the_lakes_main_boilprawn_shack"],
      ["Folly on the Lake", "grace_liurnia_of_the_lakes_main_folly_on_the_lake"],
      ["Village of the Albinaurics", "grace_liurnia_of_the_lakes_main_village_of_the_albinaurics"],
      ["Jarburg", "grace_liurnia_of_the_lakes_main_jarburg"],
      ["Revenger's Shack", "grace_liurnia_of_the_lakes_main_revengers_shack"],
      ["Slumbering Wolf's Shack", "grace_liurnia_of_the_lakes_main_slumbering_wolfs_shack"],
      ["Frenzied Flame Village Outskirts", "grace_liurnia_of_the_lakes_bellum_highway_frenzied_flame_village_outskirts"],
      ["Church of Inhibition", "grace_liurnia_of_the_lakes_bellum_highway_church_of_inhibition"],
      ["Ancient Snow Valley Ruins", "grace_mountaintops_of_the_giants_ancient_snow_valley_ruins"],
      ["Snow Valley Ruins Overlook", "grace_mountaintops_of_the_giants_snow_valley_ruins_overlook"],
      ["First Church of Marika", "grace_mountaintops_of_the_giants_first_church_of_marika"],
      ["Church of Repose", "grace_mountaintops_of_the_giants_church_of_repose"],
      ["Hidden Path to the Haligtree", "grace_mountaintops_of_the_giants_hidden_path_to_the_haligtree"],
      ["Apostate Derelict", "grace_mountaintops_of_the_giants_apostate_derelict"],
      ["Ordina Liturgical Town", "grace_ordina_liturgical_town"],
      ["Capital Rampart", "grace_altus_plateau_capital_outskirts_capital_rampart"],
      ["Hermit Merchant's Shack", "grace_altus_plateau_capital_outskirts_hermit_merchants_shack"],
      ["Minor Erdtree Church", "grace_altus_plateau_capital_outskirts_minor_erdtree_church"],
      ["Church of Elleh", "grace_church_elleh"],
      ["Gatefront", "grace_gatefront"],
      ["Stormfoot Catacombs", "grace_limgrave_main_stormfoot_catacombs"],
      ["Limgrave Tunnels", "grace_limgrave_main_limgrave_tunnels"],
      ["Groveside Cave", "grace_limgrave_main_groveside_cave"],
      ["Coastal Cave", "grace_limgrave_main_coastal_cave"],
      ["Murkwater Coast", "grace_limgrave_main_murkwater_coast"],
      ["Saintsbridge", "grace_limgrave_stormhill_saintsbridge"],
      ["Murkwater Catacombs", "grace_limgrave_main_murkwater_catacombs"],
      ["Murkwater Cave", "grace_limgrave_main_murkwater_cave"],
      ["Deathtouched Catacombs", "grace_limgrave_stormhill_deathtouched_catacombs"],
      ["Highroad Cave", "grace_limgrave_main_highroad_cave"],
      ["South of the Lookout Tower", "grace_limgrave_weeping_peninsula_south_of_the_lookout_tower"],
      ["Fourth Church of Marika", "grace_limgrave_weeping_peninsula_fourth_church_of_marika"],
      ["Church of Pilgrimage", "grace_limgrave_weeping_peninsula_church_of_pilgrimage"],
      ["Earthbore Cave", "grace_limgrave_weeping_peninsula_earthbore_cave"],
      ["Tombsward Cave", "grace_limgrave_weeping_peninsula_tombsward_cave"],
      ["Tombsward Catacombs", "grace_limgrave_weeping_peninsula_tombsward_catacombs"],
      ["Impaler's Catacombs", "grace_limgrave_weeping_peninsula_impaler_s_catacombs"],
      ["Stillwater Cave", "grace_liurnia_of_the_lakes_main_stillwater_cave"],
      ["Scenic Isle", "grace_liurnia_of_the_lakes_main_scenic_isle"],
      ["Lakeside Crystal Cave", "grace_liurnia_of_the_lakes_main_lakeside_crystal_cave"],
      ["Converted Tower", "grace_liurnia_of_the_lakes_main_converted_tower"],
      ["Road's End Catacombs", "grace_liurnia_of_the_lakes_main_road_s_end_catacombs"],
      ["Cliffbottom Catacombs", "grace_liurnia_of_the_lakes_main_cliffbottom_catacombs"],
      ["Academy Crystal Cave", "grace_liurnia_of_the_lakes_main_academy_crystal_cave"],
      ["Raya Lucaria Crystal Tunnel", "grace_liurnia_of_the_lakes_main_raya_lucaria_crystal_tunnel"],
      ["Church of Vows", "grace_liurnia_of_the_lakes_main_church_of_vows"],
      ["Ruined Labyrinth", "grace_liurnia_of_the_lakes_main_ruined_labyrinth"],
      ["Mausoleum Compound", "grace_liurnia_of_the_lakes_main_mausoleum_compound"],
      ["Black Knife Catacombs", "grace_liurnia_of_the_lakes_main_black_knife_catacombs"],
      ["Old Altus Tunnel", "grace_altus_plateau_main_old_altus_tunnel"],
      ["Perfumer's Grotto", "grace_altus_plateau_main_perfumer_s_grotto"],
      ["Unsightly Catacombs", "grace_altus_plateau_main_unsightly_catacombs"],
      ["Sage's Cave", "grace_altus_plateau_main_sage_s_cave"],
      ["Stormhill Shack", "grace_stormhill_shack"],
      ["Stormveil Main Gate", "grace_stormveil_main_gate"],
      ["Gateside Chamber", "grace_stormveil_castle_main_gateside_chamber"],
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
      ["Sealed Tunnel", "grace_capital_outskirts_sealed_tunnel"],
      ["Onyx Lord (Sealed Tunnel)", "onyx_lord_sealed_tunnel_gate"],
      ["Divine Tower of West Altus: Gate", "grace_divine_tower_west_altus_gate"],
      ["Divine Tower of West Altus", "grace_divine_tower_west_altus"],
      ["Draconic Tree Sentinel", "draconic_tree_sentinel_gate"],
      ["East Capital Rampart", "grace_east_capital_rampart"],
      ["Mistwood Outskirts", "grace_mistwood_outskirts"],
      ["Third Church of Marika", "grace_third_church_of_marika"],
      ["Fort Haight West", "grace_limgrave_main_fort_haight_west"],
      ["Siofra River Well", "siofra_well_surface_entrance"],
      ["Siofra Well descent lift", "siofra_well_lift"],
      ["Worshippers' Woods", "grace_worshippers_woods"],
      ["Ancestral Woods", "grace_ancestral_woods"],
      ["Mimic Tear", "mimic_tear_gate"],
      ["Mimic Tear (post-boss grace)", "grace_nokron_mimic_tear"],
      ["Night's Sacred Ground", "grace_nokron_nights_sacred_ground"],
      ["Regal Ancestor Spirit", "regal_ancestor_spirit_gate"],
      ["Regal Ancestor Spirit (post-boss return)", "grace_nokron_regal_ancestor_post_boss"],
      ["Aqueduct-Facing Cliffs", "grace_aqueduct_facing_cliffs"],
      ["Great Waterfall Basin", "grace_siofra_great_waterfall_basin"],
      ["Caelid Highway South", "grace_caelid_highway_south"],
      ["Rotview Balcony", "grace_rotview_balcony"],
      ["Smoldering Church", "grace_smoldering_church"],
      ["Smoldering Wall", "grace_smoldering_wall"],
      ["Astray from Caelid Highway North", "grace_astray_from_caelid_highway_north"],
      ["Fort Gael North", "grace_fort_gael_north"],
      ["Cathedral of Dragon Communion", "grace_cathedral_dragon_communion"],
      ["Caelem Ruins", "grace_caelem_ruins"],
      ["Impassable Greatbridge", "grace_impassable_greatbridge"],
      ["Redmane Castle Plaza", "grace_redmane_castle_plaza"],
      ["Chamber Outside the Plaza", "grace_chamber_outside_plaza"],
      ["Starscourge Radahn", "grace_starscourge_radahn"],
      ["Southern Aeonia Swamp Bank", "grace_southern_aeonia_swamp_bank"],
      ["Church of the Plague", "grace_church_of_plague"],
      ["Bestial Sanctum", "grace_bestial_sanctum"],
      ["Dragonbarrow Fork", "grace_dragonbarrow_fork"],
      ["Lenne's Rise", "grace_caelid_greyoll_s_dragonbarrow_lennes_rise"],
      ["Isolated Merchant's Shack (Dragonbarrow)", "grace_caelid_greyoll_s_dragonbarrow_isolated_merchant_shack"],
      ["Dragonbarrow Cave", "grace_caelid_dragonbarrow_cave"],
      ["Beastmen of Farum Azula (Dragonbarrow Cave)", "beastmen_dragonbarrow_cave_gate"],
      ["Sellia Hideaway", "grace_caelid_sellia_hideaway"],
      ["Putrid Crystalian Trio (Sellia Hideaway)", "putrid_crystalian_trio_sellia_hideaway_gate"],
      ["Gael Tunnel", "grace_caelid_gael_tunnel"],
      ["Rear Gael Tunnel Entrance", "grace_limgrave_rear_gael_tunnel_entrance"],
      ["Magma Wyrm (Gael Tunnel)", "magma_wyrm_gael_tunnel_gate"],
      ["Abandoned Cave", "grace_caelid_main_abandoned_cave"],
      ["Caelid Catacombs", "grace_caelid_main_caelid_catacombs"],
      ["Gaol Cave", "grace_caelid_main_gaol_cave"],
      ["Minor Erdtree Catacombs", "grace_caelid_main_minor_erdtree_catacombs"],
      ["War-Dead Catacombs", "grace_caelid_main_war_dead_catacombs"],
      ["Sellia Crystal Tunnel", "grace_caelid_main_sellia_crystal_tunnel"],
      ["Fort Faroth", "grace_fort_faroth"],
      ["Dectus Medallion (Right)", "item_dectus_medallion_right"],
      ["Starfall Crater (Mistwood, Limgrave)", "starfall_crater_entrance"],
      ["Nokron, Eternal City", "grace_nokron_eternal_city"],
      ["Siofra Aqueduct (Valiant Gargoyles)", "siofra_aqueduct_valiant_gargoyle_gate"],
      ["Deeproot coffin", "deeproot_coffin"],
      ["Deeproot Depths", "grace_deeproot_depths"],
      ["Great Waterfall Crest", "grace_deeproot_depths_main_great_waterfall_crest"],
      ["The Nameless Eternal City", "grace_deeproot_depths_main_the_nameless_eternal_city"],
      ["Across the Roots", "grace_deeproot_depths_main_across_the_roots"],
      ["Root-Facing Cliffs", "grace_deeproot_depths_main_root_facing_cliffs"],
      ["Deeproot to Ainsel coffin", "deeproot_ainsel_coffin"],
      ["Fia's Champions", "fia_champions_gate"],
      ["Lichdragon Fortissax", "lichdragon_fortissax_gate"],
      ["Lichdragon Fortissax (post-boss state)", "grace_lichdragon_fortissax_post_boss"],
      ["Prince of Death's Throne", "grace_prince_of_deaths_throne"],
      ["Ordina, Liturgical Town (Consecrated Snowfield)", "grace_ordina_liturgical_town"],
      ["Volcano Manor (entrance)", "grace_volcano_manor_entrance"],
      ["Prison Town Church", "grace_prison_town_church"],
      ["Guest Hall", "grace_volcano_manor_main_guest_hall"],
      ["Subterranean Inquisition Chamber", "grace_volcano_manor_main_subterranean_inquisition_chamber"],
      ["Abductor Virgin", "grace_volcano_manor_main_abductor_virgin"],
      ["Academy Abductor Virgin", "abductor_virgin_academy_gate"],
      ["Abductor Virgins", "abductor_virgins_volcano_gate"],
      ["Temple of Eiglay", "grace_temple_of_eiglay"],
      ["Haligtree Canopy", "grace_haligtree_canopy"],
      ["Haligtree Town", "grace_haligtree_town"],
      ["Haligtree Town Plaza", "grace_haligtree_town_plaza"],
      ["Haligtree Promenade", "grace_haligtree_promenade"],
      ["Haligtree Promenade (Loretta)", "grace_haligtree_promenade"],
      ["Prayer Room", "grace_elphael_prayer_room"],
      ["Elphael Inner Wall", "grace_elphael_inner_wall"],
      ["Drainage Channel", "grace_elphael_drainage_channel"],
      ["Haligtree Roots", "grace_elphael_haligtree_roots"],
      ["Malenia, Goddess of Rot", "malenia_haligtree_gate"],
      ["Malenia, Goddess of Rot (post-boss grace)", "grace_malenia_post_boss"],
      ["Ulcerated Tree Spirit (Elphael)", "ulcerated_tree_spirit_elphael_gate"],
    ]);
    const sourceCanonicalIdToNodeId = new Map();
    const sourceRegionNameToNodeId = new Map();
    const catalogNameCounts = new Map();
    catalog.records.forEach((record) => catalogNameCounts.set(record.name, (catalogNameCounts.get(record.name) || 0) + 1));
    const formalNodeIds = new Set(state.data.nodes.map((node) => node.id));
    const layerBase = { surface: 55, underground: 275, legacy: 445 };
    catalog.records.forEach((record) => {
      const regionNameKey = `${record.region}|${record.name}`;
      if (formalNodeIds.has(record.canonical_id)) {
        sourceCanonicalIdToNodeId.set(record.canonical_id, record.canonical_id);
        sourceRegionNameToNodeId.set(regionNameKey, record.canonical_id);
        if (catalogNameCounts.get(record.name) === 1 && !sourceNameToNodeId.has(record.name)) sourceNameToNodeId.set(record.name, record.canonical_id);
        return;
      }
      if (["Abandoned Coffin", "Erdtree-Gazing Hill", "Forest-Spanning Greatbridge", "Windmill Village", "Windmill Heights", "Bower of Bounty", "Road of Iniquity Side Path", "Rampartside Path", "Shaded Castle Ramparts", "Shaded Castle Inner Gate", "Castellan's Hall"].includes(record.name)) return;
      if (["Lower Capital Church", "West Capital Rampart", "Fortified Manor, First Floor", "Divine Bridge", "Isolated Divine Tower", "Forbidden Lands", "Divine Tower of East Altus: Gate", "Divine Tower of East Altus"].includes(record.name)) return;
      if (["Guest Hall", "Subterranean Inquisition Chamber", "Abductor Virgin"].includes(record.name)) return;
      if (["Haligtree Town", "Haligtree Town Plaza", "Haligtree Promenade", "Prayer Room", "Elphael Inner Wall", "Drainage Channel", "Haligtree Roots", "Malenia, Goddess of Rot"].includes(record.name)) return;
      if (["Tempest-Facing Balcony", "Dragon Temple", "Dragon Temple Transept", "Dragon Temple Lift", "Dragon Temple Rooftop", "Dragonlord Placidusax"].includes(record.name)) return;
      if (["Ainsel River Well Depths", "Ainsel River Sluice Gate", "Ainsel River Downstream", "Dragonkin Soldier of Nokstella"].includes(record.name)) return;
      if (["Belurat Gaol", "Fog Rift Catacombs", "Rivermouth Cave", "Scorpion River Catacombs"].includes(record.name)) return;
      if (["Cave of the Forlorn", "Consecrated Snowfield Catacombs", "Yelough Anix Tunnel", "Giant-Conquering Hero's Grave", "Giants' Mountaintop Catacombs", "Spiritcaller's Cave", "Spiritcaller Cave"].includes(record.name)) return;
      if (["Ruined Forge Lava Intake", "Taylew's Ruined Forge", "Ruined Forge of Starfall Past", "Moorth Highway, South", "Bonny Gaol", "Behind the Fort of Reprimand", "Fort of Reprimand", "Scadu Altus, West"].includes(record.name)) return;
      if (["Mimic Tear", "Night's Sacred Ground", "Aqueduct-Facing Cliffs"].includes(record.name)) return;
      if (["Great Waterfall Crest", "The Nameless Eternal City", "Across the Roots", "Root-Facing Cliffs"].includes(record.name)) return;
      if (["Underground Roadside", "Forsaken Depths", "Cathedral of the Forsaken", "Leyndell Catacombs", "Frenzied Flame Proscription"].includes(record.name)) return;
      if (["Limgrave Tower Bridge", "Divine Tower of Limgrave"].includes(record.name)) return;
      if (["Dragonbarrow West", "Farum Greatbridge", "Divine Tower of Caelid: Center", "Divine Tower of Caelid: Basement"].includes(record.name)) return;
      if (["Aeonia Swamp Shore", "Heart of Aeonia", "Inner Aeonia", "Sellia Under-Stair", "Sellia Backstreets", "Chair-Crypt of Sellia"].includes(record.name)) return;
      if (["Ninth Mt. Gelmir Campsite", "Seethewater River", "Seethewater Terminus", "Craftsman's Shack", "Primeval Sorcerer Azur"].includes(record.name)) return;
      if (["The Ravine", "Ravine-Veiled Village", "Ruin-Strewn Precipice", "Ruin-Strewn Precipice Overlook", "Magma Wyrm Makar"].includes(record.name)) return;
      if (["Gate Town North", "Eastern Liurnia Lake Shore", "Study Hall Entrance", "Liurnia Tower Bridge", "Divine Tower of Liurnia", "East Raya Lucaria Gate", "Bellum Church"].includes(record.name)) return;
      if (["Northern Liurnia Lake Shore", "Road to the Manor", "Main Caria Manor Gate", "Manor Lower Level", "Manor Upper Level", "Royal Moongazing Grounds", "Behind Caria Manor", "Ranni's Rise", "Ranni's Chamber"].includes(record.name)) return;
      if (["Crumbling Beast Grave", "Beside the Great Bridge", "Maliketh, the Black Blade", "Leyndell, Capital of Ash", "Gravesite Plain", "Three-Path Cross", "Church of Consolation", "Main Gate Cross", "Belurat, Tower Settlement", "Divine Beast Dancing Lion", "Theatre of the Divine Beast", "Pillar Path Cross", "Cliffroad Terminus", "Highroad Cross", "Moorth Ruins", "Bonny Village", "Bridge Leading to the Village", "Church District Highroad", "Shadow Keep Main Gate", "Main Gate Plaza", "Golden Hippopotamus", "Church District Entrance", "Sunken Chapel", "Tree-Worship Passage", "Tree-Worship Sanctum", "Storehouse, First Floor", "Storehouse, Fourth Floor", "Storehouse, Seventh Floor", "Storehouse, Back Section", "Storehouse, Loft", "Shadow Keep, Back Gate", "Scaduview", "Commander Gaius", "Scadutree Base", "Ancient Ruins Base", "Viaduct Minor Tower", "Rauh Ancient Ruins, East", "Rauh Ancient Ruins, West", "Church of the Bud, Main Entrance", "Romina, Saint of the Bud", "Church of the Bud", "Enir-Ilim: Outer Wall", "First Rise", "Spiral Rise", "Cleansing Chamber Anteroom", "Divine Gate Front Staircase", "Gate of Divinity", "Messmer the Impaler", "Messmer's Dark Chamber", "Queen's Bedchamber", "Sir Gideon Ofnir, the All-Knowing", "Godfrey, First Elden Lord", "Radagon of the Golden Order", "Elden Beast", "Fractured Marika", "Dragon's Pit", "Dragon's Pit Terminus", "Foot of the Jagged Peak", "Grand Altar of Dragon Communion", "Jagged Peak Mountainside", "Jagged Peak Summit", "Rest of the Dread Dragon", "Castle Watering Hole", "Recluses' River Upstream", "Recluses' River Downstream", "Darklight Catacombs", "Abyssal Woods", "Forsaken Graveyard", "Woodland Trail", "Church Ruins", "Divided Falls", "Manse Hall", "Midra's Library", "Second Floor Chamber", "Discussion Chamber", "Ellac River Cave", "Ellac River Downstream", "Cerulean Coast", "Cerulean Coast West", "Cerulean Coast Cross", "Finger Ruins of Rhia", "The Fissure", "Stone Coffin Fissure", "Fissure Cross", "Fissure Waypoint", "Fissure Depths", "Garden of Deep Purple", "Hinterland", "Hinterland Bridge", "Fingerstone Hill", "Cathedral of Manus Metyr", "Charo's Hidden Grave", "Lamenter's Gaol", "Agheel Lake South", "Bridge of Sacrifice", "Castle Morne Rampart", "Castle Morne Lift", "Behind the Castle", "Beside the Rampart Gaol", "Morne Moangrave", "Castleward Tunnel", "Margit, the Fell Omen", "Margit, the Fell Omen Grace", "Liurnia Lake Shore", "Academy Gate Town", "South Raya Lucaria Gate", "Bridge of Iniquity", "First Mt.Gelmir Campsite", "Road of Iniquity", "Audience Pathway", "Rykard, Lord of Blasphemy", "Stranded Graveyard", "Cave of Knowledge", "Foot of the Four Belfries", "The Four Belfries"].includes(record.name)) return;
      if (["Caelid Highway South", "Rotview Balcony", "Smoldering Church", "Caelem Ruins", "Impassable Greatbridge", "Redmane Castle Plaza", "Chamber Outside the Plaza", "Starscourge Radahn", "Southern Aeonia Swamp Bank", "Church of the Plague", "Bestial Sanctum", "Dragonbarrow Fork", "Fort Faroth", "Fort Haight West"].includes(record.name)) return;
      if (["Smoldering Wall", "Astray from Caelid Highway North", "Fort Gael North", "Cathedral of Dragon Communion", "Lenne's Rise", "Isolated Merchant's Shack (Dragonbarrow)", "Dragonbarrow Cave", "Sellia Hideaway", "Gael Tunnel", "Rear Gael Tunnel Entrance", "Abandoned Cave", "Caelid Catacombs", "Gaol Cave", "Minor Erdtree Catacombs", "War-Dead Catacombs", "Sellia Crystal Tunnel"].includes(record.name)) return;
      if (["Stormfoot Catacombs", "Limgrave Tunnels", "Groveside Cave", "Coastal Cave"].includes(record.name)) return;
      if (["Murkwater Coast", "Saintsbridge", "Murkwater Catacombs", "Murkwater Cave", "Deathtouched Catacombs", "Highroad Cave"].includes(record.name)) return;
      if (["South of the Lookout Tower", "Fourth Church of Marika", "Church of Pilgrimage", "Earthbore Cave", "Tombsward Cave", "Tombsward Catacombs", "Impaler's Catacombs", "Morne Tunnel"].includes(record.name)) return;
      if (["Stillwater Cave", "Scenic Isle", "Lakeside Crystal Cave", "Converted Tower", "Road's End Catacombs", "Cliffbottom Catacombs"].includes(record.name)) return;
      if (["Academy Crystal Cave", "Raya Lucaria Crystal Tunnel", "Church of Vows", "Ruined Labyrinth", "Black Knife Catacombs"].includes(record.name)) return;
      if (["Old Altus Tunnel", "Perfumer's Grotto", "Unsightly Catacombs", "Sage's Cave", "Auriza Hero's Grave", "Auriza Side Tomb", "Gelmir Hero's Grave", "Wyndham Catacombs", "Seethewater Cave", "Volcano Cave", "Altus Tunnel", "Sainted Hero's Grave"].includes(record.name)) return;
      if (["Sealed Tunnel", "Divine Tower of West Altus: Gate", "Divine Tower of West Altus"].includes(record.name)) return;
      if (["Laskyar Ruins", "Liurnia Highway South", "Liurnia Highway North", "Gate Town Bridge", "Eastern Tableland"].includes(record.name)) return;
      if (["Small Private Altar", "Stagefront", "Ancient Ruins, Grand Stairway", "Ravine North", "Temple Town Ruins"].includes(record.name)) return;
      if (["Avenue Balcony", "Erdtree Sanctuary", "Elden Throne", "Siofra River Well Depths", "Siofra River Bank", "Worshippers' Woods", "Below the Well", "Deep Siofra Well", "Crumbling Beast Grave Depths", "Dragon Temple Altar", "Castle Front", "Castle Ensis Checkpoint", "Castle-Lord's Chamber", "Ensis Moongazing Grounds", "Ainsel River Main", "Nokstella, Eternal City", "Nokstella Waterfall Basin", "Lake of Rot Shoreside", "Grand Cloister", "Moonlight Altar", "Altar South", "Cathedral of Manus Celes", "Palace Approach Ledge-Road", "Dynasty Mausoleum Entrance", "Dynasty Mausoleum Midpoint", "Cocoon of the Empyrean", "Grand Lift of Rold", "Zamor Ruins", "Whiteridge Road", "Freezing Lake", "Giants' Gravepost", "Foot of the Forge", "Fire Giant", "Forge of the Giants", "Castle Sol Main Gate", "Church of the Eclipse", "Castle Sol Rooftop", "Consecrated Snowfield", "Inner Consecrated Snowfield", "The First Step", "Church of Elleh", "Gatefront", "Stormhill Shack", "Mistwood Outskirts", "Third Church of Marika", "Siofra River Well", "Ancestral Woods", "Aqueduct-Facing Cliffs", "Stormveil Main Gate", "Gateside Chamber", "Stormveil Cliffside", "Rampart Tower", "Liftside Chamber", "Secluded Cell", "Lake-Facing Cliffs", "Main Academy Gate", "Church of the Cuckoo", "Schoolhouse Classroom", "Debate Parlor", "Raya Lucaria Grand Library", "Grand Lift of Dectus", "Altus Plateau", "Altus Highway Junction", "Outer Wall Phantom Tree", "Outer Wall Battleground", "East Capital Rampart", "Nokron, Eternal City", "Deeproot Depths", "Prince of Death's Throne", "Ordina, Liturgical Town", "Volcano Manor", "Prison Town Church", "Temple of Eiglay", "Haligtree Canopy", "Table of Lost Grace", "Agheel Lake North", "Seaside Ruins", "Church of Dragon Communion", "Summonwater Village Outskirts", "Waypoint Ruins Cellar", "Warmaster's Shack", "Ailing Village Outskirts", "Beside the Crater-Pocked Glade", "Beside the Crater-Pocked  Glade", "Isolated Merchant's Shack", "Tombsward", "Boilprawn Shack", "Folly on the Lake", "Village of the Albinaurics", "Jarburg", "Revenger's Shack", "Slumbering Wolf's Shack", "Frenzied Flame Village Outskirts", "Church of Inhibition", "Ancient Snow Valley Ruins", "Snow Valley Ruins Overlook", "First Church of Marika", "Church of Repose", "Hidden Path to the Haligtree", "Apostate Derelict", "Ordina Liturgical Town", "Capital Rampart", "Hermit Merchant's Shack", "Minor Erdtree Church", "Scaduview Cross", "Finger Birthing Grounds", "Shadow Keep, Black Gate", "Dark Chamber Entrance", "West Rampart", "Scorched Ruins", "Greatbridge, North", "Pillar Path Waypoint", "Fallen Ruins of the Lake", "Temple Quarter", "Crystalline Woods", "Sorcerer's Isle", "East Gate Bridge Trestle", "Mausoleum Compound"].includes(record.name)) return;
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
      const resolvedNodeId = catalogNameCounts.get(record.name) > 1 ? record.canonical_id : (sourceNameToNodeId.get(record.name) || record.canonical_id);
      sourceCanonicalIdToNodeId.set(record.canonical_id, resolvedNodeId);
      sourceRegionNameToNodeId.set(regionNameKey, resolvedNodeId);
      if (catalogNameCounts.get(record.name) === 1 && !sourceNameToNodeId.has(record.name)) sourceNameToNodeId.set(record.name, record.canonical_id);
    });
    state.data.catalogRecordCount = catalog.record_count;
    state.data.candidateRouteLegCount = routeLegCatalog.record_count;
    const candidateEndpointByRegionName = new Map();
    const candidateLayer = (regionName) => {
      const match = catalog.records.find((record) => record.region === regionName);
      return match?.layer || "legacy";
    };
    const ensureCandidateEndpoint = (name, regionName) => {
      const regionNameKey = `${regionName}|${name}`;
      if (sourceRegionNameToNodeId.has(regionNameKey)) return sourceRegionNameToNodeId.get(regionNameKey);
      if (name === "Erdtree Sanctuary" && regionName.includes("Ashen")) return "grace_ashen_erdtree_sanctuary";
      if (sourceNameToNodeId.has(name) && catalogNameCounts.get(name) <= 1) return sourceNameToNodeId.get(name);
      if (candidateEndpointByRegionName.has(regionNameKey)) return candidateEndpointByRegionName.get(regionNameKey);
      const layer = candidateLayer(regionName);
      const key = `${layer}|candidate|${regionName}`;
      const slot = regionSlots.get(key) || 0;
      regionSlots.set(key, slot + 1);
      const groupIndex = [...regionSlots.keys()].indexOf(key);
      const id = `candidate_endpoint_${`${regionName} ${name}`.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "")}`;
      const onlinePoint = findOnlineMapPointForRouteName(name, regionName);
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
        coordinateType: onlinePoint ? "online_named_map_point_candidate" : "unplaced_route_candidate",
        verificationState: "online_single",
        sourceEvidence: ["er-guide-main-7f24d64d3631ef4d549f56b42d4c3e3817a269fa"],
        onlineCoordinate: onlinePoint ? {
          source: "map_for_goblins",
          snapshot: onlinePoint.snapshot,
          recordId: onlinePoint.id,
          name: (onlinePoint.names || []).join(" / "),
          map: onlinePoint.mapKey,
          coordinateSpace: "game_world_xyz",
          bindingBasis: "route_name_candidate",
          coordinateRole: "candidate_location_anchor",
          position: onlinePoint.position,
          sourceIndex: onlinePoint.sourceIndex,
        } : null,
        isCatalog: true,
        description: `${regionName} 的在线路线候选端点；尚未获得游戏原始坐标或正式 Transition。`,
      });
      candidateEndpointByRegionName.set(regionNameKey, id);
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
      targetGroup: routeTargetGroupByLegId.get(leg.canonical_id) || null,
      note: `${leg.from} → ${leg.to}；步骤类型：${(leg.step_types || []).join("、")}。需要独立来源核对后才能进入寻路器。`,
      tags: ["candidate", "source_only"],
    }));
    state.nodes = new Map(state.data.nodes.map((node) => [node.id, node]));
    state.conditions = new Set(state.data.defaultConditions || DEFAULT_CONDITIONS);
    state.origin = state.data.defaultOrigin && state.nodes.has(state.data.defaultOrigin) ? state.data.defaultOrigin : state.data.nodes[0].id;
    state.destination = state.data.defaultDestination && state.nodes.has(state.data.defaultDestination) ? state.data.defaultDestination : state.data.nodes.at(-1).id;
    els.datasetVersion.textContent = `v${state.data.meta.version}`;
    populateSelects();
    populateRouteProfiles();
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
