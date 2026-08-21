function mapKeyFromParts(area, gridX, gridZ) {
  const pad = (value) => String(value ?? 0).padStart(2, "0");
  return "m" + pad(area) + "_" + pad(gridX) + "_" + pad(gridZ);
}

function normalizeCoordinateMapKey(value) {
  const text = String(value ?? "").trim();
  const match = text.match(/^(m\d+_\d+_\d+)(?:_\d+)+$/i);
  return match ? match[1] : text;
}

function coordinateMapKeyForRecord(record, kind) {
  if (record && record.mapKey) return normalizeCoordinateMapKey(record.mapKey);
  if (kind === "map-points") return mapKeyFromParts(record.area_no, record.grid_x, record.grid_z);
  const rawMap = String(record.map || record.current_map || "").trim();
  const areaGrid = rawMap.match(/^area\s+(\d+)\s*\/\s*grid\s+(\d+)\s*,\s*(\d+)$/i);
  return areaGrid ? mapKeyFromParts(areaGrid[1], areaGrid[2], areaGrid[3]) : normalizeCoordinateMapKey(rawMap);
}

function localTopologyLayout(nodes) {
  const grouped = new Map();
  nodes.forEach((node) => {
    const match = String(node.map_id || "").match(/^m(\d+)/i);
    const area = match ? `m${match[1]}` : "other";
    if (!grouped.has(area)) grouped.set(area, []);
    grouped.get(area).push(node);
  });
  const areas = [...grouped.keys()].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  const positions = new Map();
  const groupAnchors = [];
  const groupColumns = 6;
  const groupWidth = 160;
  const groupHeight = 150;
  areas.forEach((area, areaIndex) => {
    const column = areaIndex % groupColumns;
    const row = Math.floor(areaIndex / groupColumns);
    const groupNodes = grouped.get(area).sort((a, b) => a.map_id.localeCompare(b.map_id));
    const originX = 34 + column * groupWidth;
    const originY = 44 + row * groupHeight;
    groupAnchors.push({ area, x: originX, y: originY });
    groupNodes.forEach((node, index) => {
      positions.set(node.map_id, {
        x: originX + (index % 10) * 12,
        y: originY + 16 + Math.floor(index / 10) * 12,
      });
    });
  });
  return {
    positions,
    groupAnchors,
    width: groupColumns * groupWidth + 40,
    height: Math.max(600, Math.ceil(areas.length / groupColumns) * groupHeight + 40),
  };
}

async function loadLocalTopology() {
  if (state.localTopology) {
    renderLocalTopology();
    return;
  }
  try {
    const response = await fetch("/api/local-topology", { cache: "no-store" });
    if (!response.ok) throw new Error("local topology HTTP " + response.status);
    state.localTopology = await response.json();
    renderLocalTopology();
  } catch (error) {
    els.mapToast.textContent = "local topology load failed: " + error.message;
    renderLocalTopology();
  }
}

function renderLocalTopologyInspector(node) {
  if (!node) return;
  const safe = (value) => String(value ?? "").replace(/[&<>\"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[character]));
  const edges = state.localTopology?.edges || [];
  const outgoing = edges.filter((edge) => edge.from_map_id === node.map_id);
  const incoming = edges.filter((edge) => edge.to_map_id === node.map_id);
  const event = node.emevd_evidence || {};
  els.nodeInspector.innerHTML = `<div class="inspector-card"><div class="inspector-head"><div><div class="inspector-title">${safe(node.map_id)}</div><div class="inspector-type">LOCAL EXPLICIT TOPOLOGY · ROUTABLE=false</div></div><div class="inspector-region">MSB MAP NODE</div></div><p class="inspector-description">这是一个原生 MSB 地图节点。边只来自游戏文件显式记录的 ConnectCollision 或 Connection；连续空间步行能力和未绑定脚本条件不会被自动猜测。</p><div class="inspector-online">Parts ${safe(node.counts?.parts)} · Regions ${safe(node.counts?.regions)} · Events ${safe(node.counts?.events)}<br>Outgoing ${safe(outgoing.length)} · Incoming ${safe(incoming.length)}<br>EMEVD conditions ${safe(event.condition_count)} · actions ${safe(event.action_count)} · flags ${safe(event.event_flag_ids?.length || 0)}</div><div class="inspector-actions"><button data-open-local-xyz>Open native MSBE XYZ</button></div><div class="connection-list"><div class="connection-list-title">Explicit connections / ${outgoing.length + incoming.length}</div>${outgoing.slice(0, 10).map((edge) => `<div class="connection-item"><span>→ ${safe(edge.to_map_id)}</span><span class="connection-mode">${safe(edge.edge_kind)} · ${safe(edge.condition_status)}</span></div>`).join("")}${incoming.slice(0, 6).map((edge) => `<div class="connection-item"><span>← ${safe(edge.from_map_id)}</span><span class="connection-mode">${safe(edge.edge_kind)}</span></div>`).join("") || `<div class="connection-item"><span>暂无显式连接</span></div>`}</div></div>`;
  els.nodeInspector.querySelector("[data-open-local-xyz]").addEventListener("click", () => {
    state.localMsbeMapId = node.map_id;
    state.localMsbeMap = null;
    state.localEmevdMap = null;
    state.mapMode = "local-msbe";
    els.mapModes.forEach((button) => button.classList.toggle("active", button.dataset.mapMode === "local-msbe"));
    els.localMsbeMapSelect.hidden = false;
    els.localMsbeKind.hidden = false;
    els.coordinateMapSelect.hidden = true;
    els.coordinateEntityKind.hidden = true;
    els.projectedMasterSelect.hidden = true;
    populateLocalMsbeMapSelect();
    els.localMsbeMapSelect.value = state.localMsbeMapId;
    loadLocalMsbeMap();
  });
  const abstractButton = document.createElement("button");
  abstractButton.textContent = "Load abstract entities";
  abstractButton.type = "button";
  const abstractSummary = document.createElement("div");
  abstractSummary.className = "layer-meta-note";
  abstractSummary.textContent = "Abstract entity candidates load on demand; all remain routeable=false.";
  els.nodeInspector.querySelector(".inspector-actions")?.appendChild(abstractButton);
  els.nodeInspector.querySelector(".inspector-card")?.appendChild(abstractSummary);
  abstractButton.addEventListener("click", async () => {
    abstractButton.disabled = true;
    abstractButton.textContent = "Loading abstract entities...";
    try {
      const response = await fetch("/api/local-abstract-topology/map?map_id=" + encodeURIComponent(node.map_id), { cache: "no-store" });
      if (!response.ok) throw new Error("abstract topology HTTP " + response.status);
      const payload = await response.json();
      const roleCounts = {};
      (payload.candidate_nodes || []).forEach((candidate) => {
        const role = candidate.candidate_role || "unknown";
        roleCounts[role] = (roleCounts[role] || 0) + 1;
      });
      const roleText = Object.entries(roleCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 8)
        .map(([role, count]) => `${safe(role)} ${count}`)
        .join(" · ");
      abstractSummary.innerHTML = `Abstract candidates ${safe(payload.candidate_nodes?.length || 0)} · structural edges ${safe(payload.structural_edges?.length || 0)} · semantic references ${safe(payload.relations?.length || 0)}<br>${roleText || "No typed candidates"}<br>All records routeable=false; no Havok/NVA inference.`;
      abstractButton.textContent = "Reload abstract entities";
      abstractButton.disabled = false;
    } catch (error) {
      abstractSummary.textContent = "Abstract entity load failed: " + error.message;
      abstractButton.textContent = "Load abstract entities";
      abstractButton.disabled = false;
    }
  });
}

function renderLocalTopology() {
  els.edgeLayer.innerHTML = "";
  els.regionLabels.innerHTML = "";
  els.nodeLayer.innerHTML = "";
  if (!state.localTopology) {
    els.coordinateLayerMeta.hidden = true;
    els.graphStats.textContent = "local explicit topology loading...";
    return;
  }
  const nodes = state.localTopology.nodes || [];
  const edges = state.localTopology.edges || [];
  const layout = localTopologyLayout(nodes);
  state.coordinateBounds = { minX: 0, minY: 0, width: layout.width, height: layout.height };
  const map = document.getElementById("topology-map");
  map.setAttribute("viewBox", `0 0 ${layout.width} ${layout.height}`);
  const grid = document.querySelector(".map-grid");
  if (grid) {
    grid.setAttribute("x", "0");
    grid.setAttribute("y", "0");
    grid.setAttribute("width", String(layout.width));
    grid.setAttribute("height", String(layout.height));
  }
  setZoom(state.zoom);
  layout.groupAnchors.forEach((group) => {
    const label = svg("text", { x: group.x, y: group.y - 8, class: "coordinate-axis" });
    label.textContent = group.area;
    els.regionLabels.appendChild(label);
  });
  edges.forEach((edge) => {
    const from = layout.positions.get(edge.from_map_id);
    const to = layout.positions.get(edge.to_map_id);
    if (!from || !to) return;
    const line = svg("line", {
      x1: from.x, y1: from.y, x2: to.x, y2: to.y,
      class: "local-topology-edge",
      "marker-end": "url(#arrow-default)",
    });
    if (edge.from_map_id === state.localMsbeMapId || edge.to_map_id === state.localMsbeMapId) line.classList.add("selected");
    const title = svg("title");
    title.textContent = `${edge.from_map_id} → ${edge.to_map_id} · ${edge.edge_kind} · condition=${edge.condition_status}`;
    line.appendChild(title);
    els.edgeLayer.appendChild(line);
  });
  nodes.forEach((node) => {
    const point = layout.positions.get(node.map_id);
    if (!point) return;
    const group = svg("g", { class: "local-topology-node", transform: `translate(${point.x} ${point.y})` });
    const hit = svg("circle", { r: 9, class: "node-hit" });
    const core = svg("circle", { r: node.map_id === state.localMsbeMapId ? 5 : 2.5, class: "node-core local-topology-core" });
    const title = svg("title");
    title.textContent = `${node.map_id} · parts ${node.counts?.parts || 0} · regions ${node.counts?.regions || 0}`;
    group.append(hit, core, title);
    if (node.map_id === state.localMsbeMapId) {
      const label = svg("text", { x: 8, y: 3, class: "coordinate-poi-label" });
      label.textContent = node.map_id;
      group.appendChild(label);
    }
    group.addEventListener("click", () => {
      state.localMsbeMapId = node.map_id;
      renderLocalTopologyInspector(node);
      renderLocalTopology();
    });
    els.nodeLayer.appendChild(group);
  });
  const meta = state.localTopology.status || {};
  els.coordinateLayerMeta.innerHTML = `<strong>LOCAL EXPLICIT TOPOLOGY</strong><br>${meta.node_count || 0} MSB map nodes · ${meta.edge_count || 0} explicit directed edges · ConnectCollision ${meta.connect_collision_edges || 0} · Connection ${meta.connection_region_edges || 0}<div class="layer-meta-note">条件只在地图级 EMEVD 证据中展示；当前没有把条件自动绑定到边。连续空间 walkability 不在此模型内；routeable=false。</div>`;
  els.coordinateLayerMeta.hidden = false;
  els.graphStats.textContent = `${meta.node_count || nodes.length} map nodes · ${meta.edge_count || edges.length} explicit directed edges · ${meta.target_nodes_missing || 0} unmatched targets · routeable=false`;
  const selected = nodes.find((node) => node.map_id === state.localMsbeMapId);
  if (selected) renderLocalTopologyInspector(selected);
}

function localMsbePosition(record) {
  const position = record?.position;
  if (!position || !Number.isFinite(Number(position.x)) || !Number.isFinite(Number(position.z))) return null;
  return [Number(position.x), Number(position.y || 0), Number(position.z)];
}

function localMsbePartPosition(partsByName, name) {
  if (!name) return null;
  const part = partsByName.get(String(name));
  return localMsbePosition(part);
}

function localMsbeEventPosition(event, partsByName) {
  const extra = event?.extra || {};
  const candidateKeys = [
    "TreasurePartName", "ObjActPartName", "GeneratorPartName", "ActivationPartName",
    "PartName", "CollisionPartName", "SpawnerPartName", "TargetPartName",
  ];
  for (const key of candidateKeys) {
    const position = localMsbePartPosition(partsByName, extra[key]);
    if (position) return position;
  }
  return null;
}

function localMsbeKindClass(type) {
  return String(type || "other").toLowerCase().replace(/[^a-z0-9_-]+/g, "-");
}

function populateLocalMsbeMapSelect() {
  if (!els.localMsbeMapSelect || !state.localMsbeIndex) return;
  const maps = [...(state.localMsbeIndex.maps || [])].sort((a, b) => String(a.map_id).localeCompare(String(b.map_id)));
  els.localMsbeMapSelect.innerHTML = "";
  maps.forEach((record) => {
    const option = document.createElement("option");
    option.value = record.map_id;
    option.textContent = `${record.map_id} · parts ${record.counts?.parts || 0} · regions ${record.counts?.regions || 0}`;
    els.localMsbeMapSelect.appendChild(option);
  });
  if (!maps.some((record) => record.map_id === state.localMsbeMapId)) state.localMsbeMapId = maps[0]?.map_id || "m10_00_00_00";
  els.localMsbeMapSelect.value = state.localMsbeMapId;
}

function populateLocalMsbeLayerSelect() {
  if (!els.localMsbeLayerSelect) return;
  const records = [...(state.localMsbeLayers?.records || [])].sort(
    (a, b) => Number(a.map_studio_layer) - Number(b.map_studio_layer),
  );
  els.localMsbeLayerSelect.innerHTML = "";
  const allOption = document.createElement("option");
  allOption.value = "all";
  allOption.textContent = "All raw MSBE layers";
  els.localMsbeLayerSelect.appendChild(allOption);
  records.forEach((record) => {
    const option = document.createElement("option");
    option.value = String(record.map_studio_layer);
    option.textContent = `${record.is_default_layer_value ? "default" : "raw layer"} ${record.map_studio_layer} · parts ${record.part_count}`;
    els.localMsbeLayerSelect.appendChild(option);
  });
  if (!["all", ...records.map((record) => String(record.map_studio_layer))].includes(String(state.localMsbeLayer))) {
    state.localMsbeLayer = "all";
  }
  els.localMsbeLayerSelect.value = String(state.localMsbeLayer);
}

function localMsbeLayerMatches(record) {
  if (String(state.localMsbeLayer) === "all") return true;
  if (record?.map_studio_layer === undefined || record?.map_studio_layer === null) return true;
  return String(record.map_studio_layer) === String(state.localMsbeLayer);
}

async function loadLocalMsbeMap() {
  if (!state.localMsbeIndex) return;
  try {
    const response = await fetch("/api/local-msbe/map?map_id=" + encodeURIComponent(state.localMsbeMapId), { cache: "no-store" });
    if (!response.ok) throw new Error("local MSBE map HTTP " + response.status);
    state.localMsbeMap = await response.json();
    const layerResponse = await fetch("/api/local-msbe/layers?map_id=" + encodeURIComponent(state.localMsbeMapId), { cache: "no-store" });
    if (!layerResponse.ok) throw new Error("local MSBE layers HTTP " + layerResponse.status);
    state.localMsbeLayers = await layerResponse.json();
    populateLocalMsbeLayerSelect();
    await loadLocalEmevdMap();
    renderLocalMsbeMap();
  } catch (error) {
    state.localMsbeMap = null;
    els.mapToast.textContent = "local MSBE map load failed: " + error.message;
    renderLocalMsbeMap();
  }
}

async function loadLocalAbstractMap() {
  if (!state.localMsbeIndex) return;
  try {
    const mapQuery = encodeURIComponent(state.localMsbeMapId);
    const [abstractResponse, auditResponse, layerResponse] = await Promise.all([
      fetch("/api/local-abstract-topology-graph/map?map_id=" + mapQuery, { cache: "no-store" }),
      fetch("/api/local-transition-audit/map?map_id=" + mapQuery, { cache: "no-store" }),
      fetch("/api/local-msbe/layers?map_id=" + mapQuery, { cache: "no-store" }),
    ]);
    const [guardResponse, expressionResponse] = await Promise.all([
      fetch("/api/local-emevd/guard-traces", { cache: "no-store" }),
      fetch("/api/local-emevd/guard-expressions", { cache: "no-store" }),
    ]);
    if (!abstractResponse.ok) throw new Error("local abstract topology graph HTTP " + abstractResponse.status);
    if (!auditResponse.ok) throw new Error("local transition audit HTTP " + auditResponse.status);
    if (!layerResponse.ok) throw new Error("local MSBE layers HTTP " + layerResponse.status);
    if (!guardResponse.ok) throw new Error("local EMEVD guard traces HTTP " + guardResponse.status);
    if (!expressionResponse.ok) throw new Error("local EMEVD guard expressions HTTP " + expressionResponse.status);
    state.localAbstractMap = await abstractResponse.json();
    state.localTransitionAuditMap = await auditResponse.json();
    state.localMsbeLayers = await layerResponse.json();
    populateLocalMsbeLayerSelect();
    state.localEmevdGuardTraces = await guardResponse.json();
    state.localEmevdGuardExpressions = await expressionResponse.json();
    renderLocalAbstractMap();
  } catch (error) {
    state.localAbstractMap = null;
    state.localTransitionAuditMap = null;
    state.localMsbeLayers = null;
    state.localEmevdGuardTraces = null;
    state.localEmevdGuardExpressions = null;
    els.mapToast.textContent = "local abstract topology load failed: " + error.message;
    renderLocalAbstractMap();
  }
}

async function loadLocalNativeTopologyMap() {
  if (!state.localMsbeIndex) return;
  try {
    const mapQuery = encodeURIComponent(state.localMsbeMapId);
    const [nativeResponse, modelResponse, endpointResponse] = await Promise.all([
      fetch("/api/local-native-topology-graph/map?map_id=" + mapQuery, { cache: "no-store" }),
      fetch("/api/local-native-msbe-model-bindings/map?map_id=" + mapQuery, { cache: "no-store" }),
      fetch("/api/local-msbe-native-endpoint-bindings/map?map_id=" + mapQuery, { cache: "no-store" }),
    ]);
    if (!nativeResponse.ok) throw new Error("local native topology HTTP " + nativeResponse.status);
    if (!modelResponse.ok) throw new Error("native MSBE model bindings HTTP " + modelResponse.status);
    if (!endpointResponse.ok) throw new Error("MSBE native endpoint bindings HTTP " + endpointResponse.status);
    state.localNativeTopologyMap = await nativeResponse.json();
    state.localNativeModelBindingsMap = await modelResponse.json();
    state.localNativeEndpointBindingsMap = await endpointResponse.json();
    renderLocalNativeTopologyMap();
  } catch (error) {
    state.localNativeTopologyMap = null;
    state.localNativeModelBindingsMap = null;
    state.localNativeEndpointBindingsMap = null;
    els.mapToast.textContent = "local native topology load failed: " + error.message;
    renderLocalNativeTopologyMap();
  }
}

function renderLocalNativeTopologyInspector(node) {
  if (!node) return;
  const safe = (value) => String(value ?? "").replace(/[&<>\"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[character]));
  const modelRecords = (state.localNativeModelBindingsMap?.records || [])
    .filter((record) => record.native_node_id === node.id);
  const modelCandidates = modelRecords.flatMap((record) => record.msbe_part_candidates || []);
  const endpointRecords = (state.localNativeEndpointBindingsMap?.records || [])
    .filter((record) => (record.native_navmesh_candidates || []).some((candidate) => candidate.node_id === node.id));
  els.nodeInspector.innerHTML = `<div class="inspector-card"><div class="inspector-head"><div><div class="inspector-title">${safe(node.id)}</div><div class="inspector-type">LOCAL NATIVE NAVMESH · ROUTABLE=false</div></div><div class="inspector-region">${safe(node.map_id)}</div></div><p class="inspector-description">这是本地 NVA 原生 Navmesh 节点。它与 MSBE 部件的关系来自精确 model identity；这里不把重复模型实例选择、碰撞边界或原生连接自动解释成玩家可走路线。</p><div class="inspector-online">Navmesh index ${safe(node.navmesh_index)} · model ${safe(node.model_id)} · name ${safe(node.name_id)}<br>face data ${safe(node.face_data_index)} · faces ${safe(node.face_count)} · gate nodes ${safe(node.gate_node_count)}<br>MSBE model candidates ${safe(modelCandidates.length)} · ConnectCollision endpoint candidates ${safe(endpointRecords.length)}<br>native position is transform metadata, not player-world XYZ · routeable=false</div>${modelCandidates.length ? `<div class="connection-list"><div class="connection-list-title">Exact MSBE model candidates</div>${modelCandidates.slice(0, 10).map((candidate) => `<div class="connection-item"><span>${safe(candidate.part_type)} · ${safe(candidate.name)}</span><span class="connection-mode">${safe(candidate.node_id)}</span></div>`).join("")}</div>` : ""}${endpointRecords.length ? `<div class="connection-list"><div class="connection-list-title">ConnectCollision endpoint candidates</div>${endpointRecords.slice(0, 10).map((record) => `<div class="connection-item"><span>${safe(record.msbe_part?.name)}</span><span class="connection-mode">${safe(record.binding_status)}</span></div>`).join("")}</div>` : ""}<details class="coordinate-inspector-details"><summary>Raw native node record</summary><pre>${safe(JSON.stringify(node, null, 2))}</pre></details></div>`;
}

function renderLocalNativeTopologyMap() {
  els.edgeLayer.innerHTML = "";
  els.regionLabels.innerHTML = "";
  els.nodeLayer.innerHTML = "";
  if (!state.localNativeTopologyMap) {
    els.coordinateLayerMeta.hidden = true;
    els.graphStats.textContent = "local native topology loading...";
    return;
  }
  const payload = state.localNativeTopologyMap;
  const nodes = payload.nodes || [];
  if (!payload.record_present) {
    state.coordinateBounds = { minX: 0, minY: 0, width: 900, height: 600 };
    const map = document.getElementById("topology-map");
    map.setAttribute("viewBox", "0 0 900 600");
    els.coordinateLayerMeta.innerHTML = `<strong>${state.localMsbeMapId} · LOCAL NATIVE TOPOLOGY</strong><br>没有对应 NVA 文件；该地图保持 native coverage unresolved，不代表不可玩或空地图。<div class="layer-meta-note">MSBE/EMEVD 抽象证据仍可从其他视图查看；routeable=false。</div>`;
    els.coordinateLayerMeta.hidden = false;
    els.graphStats.textContent = `${state.localMsbeMapId} · NVA coverage unresolved · routeable=false`;
    return;
  }
  const boundaryPairCounts = new Map();
  (payload.edges || []).forEach((edge) => {
    const key = `${edge.from}|${edge.to}`;
    boundaryPairCounts.set(key, (boundaryPairCounts.get(key) || 0) + 1);
  });
  const connectorEdges = payload.connector_edges || [];
  const uniqueEdges = new Map();
  (connectorEdges.length ? connectorEdges : payload.edges || []).forEach((edge) => {
    const key = `${edge.from}|${edge.to}`;
    if (!uniqueEdges.has(key)) uniqueEdges.set(key, { ...edge, boundary_pair_count: boundaryPairCounts.get(key) || 0 });
  });
  const columns = Math.max(8, Math.ceil(Math.sqrt(Math.max(nodes.length, 1))));
  const cellWidth = 44;
  const cellHeight = 36;
  const width = Math.max(900, columns * cellWidth + 80);
  const height = Math.max(600, Math.ceil(nodes.length / columns) * cellHeight + 90);
  const positions = new Map();
  nodes.forEach((node, index) => positions.set(node.id, {
    x: 40 + (index % columns) * cellWidth,
    y: 50 + Math.floor(index / columns) * cellHeight,
  }));
  state.coordinateBounds = { minX: 0, minY: 0, width, height };
  const map = document.getElementById("topology-map");
  map.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const grid = document.querySelector(".map-grid");
  if (grid) {
    grid.setAttribute("x", "0");
    grid.setAttribute("y", "0");
    grid.setAttribute("width", String(width));
    grid.setAttribute("height", String(height));
  }
  setZoom(state.zoom);
  const axis = svg("text", { x: 16, y: 22, class: "coordinate-axis" });
  axis.textContent = `${state.localMsbeMapId} · NVA abstract node layout · not player-world XYZ`;
  els.regionLabels.appendChild(axis);
  uniqueEdges.forEach((edge) => {
    const from = positions.get(edge.from);
    const to = positions.get(edge.to);
    if (!from || !to) return;
    const line = svg("line", {
      x1: from.x, y1: from.y, x2: to.x, y2: to.y,
      class: "local-native-edge",
      "marker-end": "url(#arrow-default)",
    });
    const title = svg("title");
    title.textContent = `${edge.from} → ${edge.to} · exact Connector declaration · ${edge.boundary_pair_count} boundary pairs · routeable=false`;
    line.appendChild(title);
    els.edgeLayer.appendChild(line);
  });
  const modelRecords = state.localNativeModelBindingsMap?.records || [];
  nodes.forEach((node) => {
    const point = positions.get(node.id);
    if (!point) return;
    const group = svg("g", { class: "local-native-node", transform: `translate(${point.x} ${point.y})` });
    const hit = svg("circle", { r: 12, class: "node-hit" });
    const core = svg("circle", { r: 5, class: "node-core local-native-core" });
    const title = svg("title");
    const modelRecord = modelRecords.find((record) => record.native_node_id === node.id);
    title.textContent = `${node.id} · model ${node.model_id} · MSBE candidates ${modelRecord?.msbe_part_candidates?.length || 0}`;
    group.append(hit, core, title);
    group.addEventListener("click", () => renderLocalNativeTopologyInspector(node));
    els.nodeLayer.appendChild(group);
  });
  const status = payload.map || {};
  const graphStatus = payload.model || {};
  const endpointCount = state.localNativeEndpointBindingsMap?.record_count || 0;
  const modelCount = modelRecords.reduce((count, record) => count + (record.msbe_part_candidates || []).length, 0);
  els.coordinateLayerMeta.innerHTML = `<strong>${state.localMsbeMapId} · LOCAL NATIVE TOPOLOGY</strong><br>${nodes.length} Navmesh nodes · ${connectorEdges.length} exact Connector declarations · ${(payload.edges || []).length} optional boundary pairs · ${uniqueEdges.size} native directed pairs<br>MSBE model candidates ${modelCount} · ConnectCollision endpoints ${endpointCount}<div class="layer-meta-note">图中节点按原生索引排列，布局不是游戏 XYZ；线来自 NVA Connector declaration abstract topology，HKX2 face/edge evidence 只作边界索引佐证。重复模型实例保持候选集，不自动选入口、楼层或方向；全部 routeable=false。${graphStatus.routeable === false ? "" : ""}</div>`;
  els.coordinateLayerMeta.hidden = false;
  els.graphStats.textContent = `${state.localMsbeMapId} · ${nodes.length} NVA nodes · ${uniqueEdges.size} Connector pairs · ${endpointCount} ConnectCollision endpoints · routeable=false`;
  if (nodes.length) renderLocalNativeTopologyInspector(nodes[0]);
}

async function loadLocalEmevdMap() {
  state.localEmevdMap = null;
  try {
    const response = await fetch("/api/local-emevd/map?map_id=" + encodeURIComponent(state.localMsbeMapId), { cache: "no-store" });
    if (!response.ok) throw new Error("local EMEVD map HTTP " + response.status);
    state.localEmevdMap = await response.json();
  } catch (error) {
    els.mapToast.textContent = "local EMEVD evidence load failed: " + error.message;
  }
}

function renderLocalMsbeLayerMeta(mapRecord, plottedCount, totalCount) {
  const panel = els.coordinateLayerMeta;
  if (!panel) return;
  const safe = (value) => String(value ?? "").replace(/[&<>\"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[character]));
  const status = state.localMsbeIndex?.status || {};
  const source = state.localMsbeIndex?.source || {};
  const eventSummary = (state.localEmevdIndex?.maps || []).find((record) => record.map_key === state.localMsbeMapId) || {};
  const bounds = mapRecord?.xyz_bounds || {};
  panel.innerHTML = `<strong>${safe(state.localMsbeMapId)}</strong> · native MSBE XYZ<br>显示 ${plottedCount}/${totalCount} 条 ${safe(state.localMsbeKind)} 记录 · maps ${status.map_nodes || 0} · transitions ${status.transition_edges || 0}<br>EMEVD 条件 ${eventSummary.condition_count || 0} · 动作 ${eventSummary.action_count || 0} · 旗帜 ${eventSummary.event_flag_ids?.length || 0}<div class="layer-meta-note">原始游戏坐标来自本地副本；解析器 ${safe(source.parser?.name)} @ ${safe(source.parser?.commit?.slice(0, 12))}。这是实体/区域/事件和脚本条件证据层，不等同完整 walkable navmesh；当前 routeable=false。范围 X ${safe(bounds.min?.x)}..${safe(bounds.max?.x)} · Y ${safe(bounds.min?.y)}..${safe(bounds.max?.y)} · Z ${safe(bounds.min?.z)}..${safe(bounds.max?.z)}</div>`;
  panel.hidden = false;
}

function renderLocalMsbeInspector(record, kind, label, position) {
  if (!record) return;
  const safe = (value) => String(value ?? "").replace(/[&<>\"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[character]));
  const xyz = position || localMsbePosition(record);
  const title = label || record.name || record.map_id || "local MSBE record";
  const semanticSummary = (state.localEmevdIndex?.maps || []).find((item) => item.map_key === state.localMsbeMapId) || {};
  const semanticRefs = state.localEmevdMap?.reference_count || 0;
  els.nodeInspector.innerHTML = `<div class="inspector-card"><div class="inspector-head"><div><div class="inspector-title">${safe(title)}</div><div class="inspector-type">LOCAL MSBE ${safe(kind).toUpperCase()} · ROUTEABLE=false</div></div><div class="inspector-region">${safe(state.localMsbeMapId)}</div></div><p class="inspector-description">原生 MSBE 记录，坐标来自工作目录中的游戏数据副本。它证明实体、区域、事件或跨地图连接存在；脚本条件作为独立证据展示，不单独证明角色可步行到达。</p><div class="inspector-online">${xyz ? `X ${safe(xyz[0])} / Y ${safe(xyz[1])} / Z ${safe(xyz[2])}` : "无可绘制 XYZ 坐标"}<br>source: ${safe(state.localMsbeMap?.source_entry || "local snapshot")}<br>EMEVD references: ${safe(semanticRefs)} · conditions: ${safe(semanticSummary.condition_count || 0)} · actions: ${safe(semanticSummary.action_count || 0)}</div><details class="coordinate-inspector-details"><summary>Raw local MSBE record</summary><pre>${safe(JSON.stringify(record, null, 2))}</pre></details></div>`;
}

function abstractRoleColor(role) {
  const value = String(role || "");
  if (value === "map_connection_endpoint") return "#73b9c9";
  if (value === "interaction_event") return "#e9c979";
  if (value.includes("vertical") || value.includes("fall")) return "#d993c4";
  if (value.includes("airflow")) return "#8bd4b5";
  if (value.includes("warp") || value.includes("retry")) return "#a8a2e8";
  if (value.includes("event_target")) return "#b1a99a";
  return "#9ba8b5";
}

function localAbstractPosition(record) {
  return localMsbePosition(record) || (record?.anchor_position ? localMsbePosition({ position: record.anchor_position }) : null);
}

function renderLocalAbstractInspector(record) {
  if (!record) return;
  const safe = (value) => String(value ?? "").replace(/[&<>\"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[character]));
  const position = localAbstractPosition(record);
  const evidence = record.local_fmg_evidence || [];
  els.nodeInspector.innerHTML = `<div class="inspector-card"><div class="inspector-head"><div><div class="inspector-title">${safe(record.name || record.id)}</div><div class="inspector-type">LOCAL ABSTRACT ENTITY · ROUTABLE=false</div></div><div class="inspector-region">${safe(record.map_id)}</div></div><p class="inspector-description">该节点来自本地 MSBE 的明确实体或拓扑候选类型。它用于表达连接、交互、区域和事件关系；没有把碰撞、Navmesh 或距离推断成可通行路线。</p><div class="inspector-online">role: ${safe(record.candidate_role)} · type: ${safe(record.part_type || record.region_type || record.event_type || record.node_type)}<br>${position ? `X ${safe(position[0])} / Y ${safe(position[1])} / Z ${safe(position[2])}` : "无可绘制 XYZ 坐标"}<br>FMG evidence: ${safe(evidence.length)} · routeable=false</div>${evidence.length ? `<div class="connection-list"><div class="connection-list-title">Local FMG text evidence</div>${evidence.slice(0, 8).map((item) => `<div class="connection-item"><span>${safe(item.language)} · ${safe(item.fmg)}:${safe(item.id)}</span><span class="connection-mode">${safe(item.text)}</span></div>`).join("")}</div>` : ""}<details class="coordinate-inspector-details"><summary>Raw abstract entity record</summary><pre>${safe(JSON.stringify(record, null, 2))}</pre></details></div>`;
}

function renderLocalAbstractAudit(record) {
  if (!record || !state.localTransitionAuditMap) return;
  const safe = (value) => String(value ?? "").replace(/[&<>\"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[character]));
  const pairs = (state.localTransitionAuditMap.endpoint_pairs || []).filter((pair) => pair.from?.node_id === record.id || pair.to?.node_id === record.id);
  const warps = (state.localTransitionAuditMap.scripted_warp_bindings || []).filter((binding) => binding.from?.node_id === record.id || binding.to?.node_id === record.id);
  const mapWarps = (state.localTransitionAuditMap.scripted_map_warp_bindings || []).filter((binding) => binding.from?.node_id === record.id || binding.to?.node_id === record.id);
  const controls = (state.localTransitionAuditMap.interaction_candidates || []).filter((candidate) => (candidate.exact_target_part_node_ids || []).includes(record.id));
  if (!pairs.length && !warps.length && !mapWarps.length && !controls.length) return;
  const card = els.nodeInspector.querySelector(".inspector-card");
  if (!card) return;
  const markup = `<div class="connection-list"><div class="connection-list-title">Exact transition audit</div>${pairs.slice(0, 8).map((pair) => `<div class="connection-item"><span>${safe(pair.transition_kind)} · ${safe(pair.from?.map_id)} -> ${safe(pair.to?.map_id)}</span><span class="connection-mode">endpoint exact · routeable=false</span></div>`).join("")}${warps.slice(0, 8).map((binding) => `<div class="connection-item"><span>scripted warp · ${safe(binding.from?.name)} -> ${safe(binding.to?.name)}</span><span class="connection-mode">EMEVD exact · routeable=false</span></div>`).join("")}${mapWarps.slice(0, 8).map((binding) => `<div class="connection-item"><span>scripted map warp · ${safe(binding.from?.name)} -> ${safe(binding.to?.landing?.name || binding.to?.map_id)}</span><span class="connection-mode">map + landing exact · guard trace only</span></div>`).join("")}${controls.slice(0, 8).map((candidate) => `<div class="connection-item"><span>${safe(candidate.transition_candidate_kind)} · ObjAct ${safe(candidate.obj_act_id)}</span><span class="connection-mode">control-to-part only</span></div>`).join("")}</div>`;
  card.insertAdjacentHTML("beforeend", markup);
}

function renderLocalAbstractMap() {
  els.edgeLayer.innerHTML = "";
  els.regionLabels.innerHTML = "";
  els.nodeLayer.innerHTML = "";
  if (!state.localAbstractMap) {
    els.coordinateLayerMeta.hidden = true;
    els.graphStats.textContent = "local abstract entities loading...";
    return;
  }
  const candidateNodes = state.localAbstractMap.candidate_nodes || [];
  const graphEndpointNodes = (state.localAbstractMap.nodes || []).filter((record) =>
    record.map_id === state.localMsbeMapId
    && ["transition_endpoint", "warp_evidence_endpoint"].includes(record.node_type)
    && !candidateNodes.some((candidate) => candidate.id === record.id)
  );
  const candidates = candidateNodes.concat(graphEndpointNodes).filter(localMsbeLayerMatches);
  const plotted = candidates.map((record) => ({ record, position: localAbstractPosition(record) })).filter((item) => item.position);
  const positionsById = new Map(plotted.map((item) => [item.record.id, item.position]));
  const xs = plotted.map((item) => item.position[0]);
  const zs = plotted.map((item) => item.position[2]);
  const rawMinX = xs.length ? Math.min(...xs) : -500;
  const rawMaxX = xs.length ? Math.max(...xs) : 500;
  const rawMinY = zs.length ? Math.min(...zs) : -500;
  const rawMaxY = zs.length ? Math.max(...zs) : 500;
  const rawWidth = Math.max(100, rawMaxX - rawMinX);
  const rawHeight = Math.max(100, rawMaxY - rawMinY);
  const margin = Math.max(30, Math.max(rawWidth, rawHeight) * 0.08);
  const minX = rawMinX - margin;
  const minY = rawMinY - margin;
  const width = rawWidth + margin * 2;
  const height = rawHeight + margin * 2;
  state.coordinateBounds = { minX, minY, width, height };
  const map = document.getElementById("topology-map");
  map.setAttribute("viewBox", [minX, minY, width, height].join(" "));
  const grid = document.querySelector(".map-grid");
  if (grid) {
    grid.setAttribute("x", String(minX));
    grid.setAttribute("y", String(minY));
    grid.setAttribute("width", String(width));
    grid.setAttribute("height", String(height));
  }
  setZoom(state.zoom);
  const axis = svg("text", { x: minX + 10, y: minY + 16, class: "coordinate-axis" });
  axis.textContent = `${state.localMsbeMapId} · abstract MSBE entities · native X/Z · Y is height`;
  els.regionLabels.appendChild(axis);

  (state.localAbstractMap.relations || []).forEach((relation) => {
    const from = positionsById.get(relation.from);
    const to = positionsById.get(relation.to);
    if (!from || !to) return;
    const line = svg("line", { x1: from[0], y1: from[2], x2: to[0], y2: to[2], class: "local-abstract-relation" });
    const title = svg("title");
    title.textContent = `${relation.relation_type} · routeable=false`;
    line.appendChild(title);
    els.edgeLayer.appendChild(line);
  });

  (state.localAbstractMap.interaction_relations || []).forEach((relation) => {
    const from = positionsById.get(relation.from);
    const to = positionsById.get(relation.to);
    if (!from || !to) return;
    const line = svg("line", { x1: from[0], y1: from[2], x2: to[0], y2: to[2], class: "local-abstract-interaction" });
    const title = svg("title");
    title.textContent = `${relation.relation_type} · ObjAct ${relation.obj_act_id} · routeable=false`;
    line.appendChild(title);
    els.edgeLayer.appendChild(line);
  });

  (state.localAbstractMap.interaction_transport_relations || []).forEach((relation) => {
    const from = positionsById.get(relation.from);
    const to = positionsById.get(relation.to);
    if (!from || !to) return;
    const line = svg("line", { x1: from[0], y1: from[2], x2: to[0], y2: to[2], class: "local-abstract-interaction-transport" });
    const title = svg("title");
    title.textContent = `${relation.relation_type} · ${relation.instruction_name} · routeable=false`;
    line.appendChild(title);
    els.edgeLayer.appendChild(line);
  });

  (state.localAbstractMap.edges || [])
    .filter((edge) => edge.edge_family !== "native_msbe_map_declaration")
    .forEach((edge) => {
    const from = positionsById.get(edge.from);
    const to = positionsById.get(edge.to);
    if (!from || !to) return;
    const lineClass = edge.edge_family === "exact_scripted_warp"
      ? "local-abstract-scripted-warp"
      : edge.edge_family === "emevd_scripted_warp_evidence"
        ? "local-abstract-emevd-warp-evidence"
        : "local-abstract-exact-endpoint";
    const line = svg("line", { x1: from[0], y1: from[2], x2: to[0], y2: to[2], class: lineClass });
    const title = svg("title");
    title.textContent = `${edge.edge_family} · ${edge.from} -> ${edge.to} · routeable=false`;
    line.appendChild(title);
    els.edgeLayer.appendChild(line);
  });

  const labelBudget = plotted.length <= 160 ? plotted.length : 60;
  plotted.forEach((item, index) => {
    const record = item.record;
    const [x, yHeight, z] = item.position;
    const role = String(record.candidate_role || "unknown");
    const roleClass = localMsbeKindClass(role);
    const radius = record.node_type === "warp_evidence_endpoint" ? 5 : role === "map_connection_endpoint" ? 8 : role === "interaction_event" ? 6 : role.includes("vertical") || role.includes("fall") ? 5 : 3.5;
    const group = svg("g", { class: `coordinate-poi local-abstract ${roleClass}`, transform: `translate(${x} ${z})` });
    const hit = svg("circle", { r: Math.max(10, radius * 2.5), class: "node-hit" });
    const core = svg("circle", { r: radius, class: "node-core local-abstract-core", fill: abstractRoleColor(role) });
    const title = svg("title");
    title.textContent = `${record.name || record.id} · ${role} · X ${x} / Y ${yHeight} / Z ${z} · routeable=false`;
    group.append(hit, core, title);
    if (index < labelBudget && ["map_connection_endpoint", "interaction_event"].includes(role)) {
      const label = svg("text", { x: radius + 5, y: 3, class: "coordinate-poi-label" });
      label.textContent = record.name || role;
      group.appendChild(label);
    }
    group.addEventListener("click", () => {
      renderLocalAbstractInspector(record);
      renderLocalAbstractAudit(record);
    });
    els.nodeLayer.appendChild(group);
  });
  const mapRecord = state.localAbstractMap.map || {};
  const onlineRegion = mapRecord.online_tile_region_evidence?.record || {};
  const counts = candidates.reduce((result, record) => {
    const role = record.candidate_role || "unknown";
    result[role] = (result[role] || 0) + 1;
    return result;
  }, {});
  const topRoles = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([role, count]) => `${role} ${count}`).join(" · ");
  els.coordinateLayerMeta.innerHTML = `<strong>${state.localMsbeMapId} · LOCAL ABSTRACT ENTITIES</strong><br>${plotted.length}/${candidates.length} candidates plotted · structural edges ${(state.localAbstractMap.structural_edges || []).length} · relations ${(state.localAbstractMap.relations || []).length}<br>online region: ${onlineRegion.subRegion || "unknown"} · ${onlineRegion.majorRegion || "unknown"}<div class="layer-meta-note">${topRoles || "No typed candidates"}<br>Exact MSBE entity evidence only. No Havok/NVA inference; all records routeable=false.</div>`;
  els.coordinateLayerMeta.hidden = false;
  const auditPairs = state.localTransitionAuditMap?.endpoint_pairs || [];
  const scriptedWarps = state.localTransitionAuditMap?.scripted_warp_bindings || [];
  const scriptedMapWarps = state.localTransitionAuditMap?.scripted_map_warp_bindings || [];
  const auditCandidates = state.localTransitionAuditMap?.interaction_candidates || [];
  const guardStatus = state.localEmevdGuardTraces?.status || {};
  const expressionStatus = state.localEmevdGuardExpressions?.status || {};
  const layerStatus = state.localMsbeLayers || {};
  const graphEdges = state.localAbstractMap.edges || [];
  const exactGraphEdges = graphEdges.filter((edge) => edge.edge_family !== "native_msbe_map_declaration");
  const warpGraphEdges = graphEdges.filter((edge) => edge.edge_family === "emevd_scripted_warp_evidence");
  const interactionRelations = state.localAbstractMap.interaction_relations || [];
  const interactionUnresolved = state.localAbstractMap.interaction_relation_unresolved || [];
  const interactionTransportRelations = state.localAbstractMap.interaction_transport_relations || [];
  const interactionTransportUnresolved = state.localAbstractMap.interaction_transport_unresolved || [];
  const objactStateEvidence = state.localAbstractMap.objact_state_evidence || [];
  els.coordinateLayerMeta.insertAdjacentHTML("beforeend", `<br>EMEVD transport evidence edges: ${warpGraphEdges.length}`);
  els.coordinateLayerMeta.insertAdjacentHTML("beforeend", `<br>ObjAct exact control relations: ${interactionRelations.length} · unresolved controls: ${interactionUnresolved.length}`);
  els.coordinateLayerMeta.insertAdjacentHTML("beforeend", `<br>ObjAct exact transport bindings: ${interactionTransportRelations.length} · unresolved transport bindings: ${interactionTransportUnresolved.length}`);
  els.coordinateLayerMeta.insertAdjacentHTML("beforeend", `<br>ObjAct EMEVD state evidence: ${objactStateEvidence.length} · runtime truth unevaluated`);
  els.coordinateLayerMeta.insertAdjacentHTML("beforeend", `<br>merged graph edges: ${graphEdges.length} · exact endpoint/warp edges: ${exactGraphEdges.length}`);
  els.coordinateLayerMeta.insertAdjacentHTML("beforeend", `<br>native MSBE layer partitions: ${layerStatus.record_count || 0} · raw layer values: ${layerStatus.distinct_layer_values || 0}<br>exact endpoint pairs touching map: ${auditPairs.length} · scripted entity warps: ${scriptedWarps.length} · scripted map warps: ${scriptedMapWarps.length} · ObjAct candidates: ${auditCandidates.length}<br>EMEVD guard traces: ${guardStatus.targets_with_syntactic_path || 0} syntactic paths · guard expressions: ${expressionStatus.unique_expression_count || 0} candidates · semantics unresolved`);
  els.graphStats.textContent = `${state.localMsbeMapId} · ${plotted.length}/${candidates.length} abstract candidates · endpoint pairs ${auditPairs.length} · map warps ${scriptedMapWarps.length} · guard expressions ${expressionStatus.unique_expression_count || 0} · routeable=false`;
  if (plotted.length) {
    renderLocalAbstractInspector(plotted[0].record);
    renderLocalAbstractAudit(plotted[0].record);
  }
}

function renderLocalMsbeMap() {
  els.edgeLayer.innerHTML = "";
  els.regionLabels.innerHTML = "";
  els.nodeLayer.innerHTML = "";
  if (!state.localMsbeMap) {
    els.coordinateLayerMeta.hidden = true;
    els.graphStats.textContent = "local MSBE map loading...";
    return;
  }
  const mapRecord = (state.localMsbeIndex?.maps || []).find((record) => record.map_id === state.localMsbeMapId) || {};
  const parts = state.localMsbeMap.parts || [];
  const regions = state.localMsbeMap.regions || [];
  const events = state.localMsbeMap.events || [];
  const partsByName = new Map(parts.map((part) => [String(part.name), part]));
  const transitions = (state.localMsbeIndex?.transitions || []).filter((edge) => edge.from_map_id === state.localMsbeMapId);
  const transitionRecords = transitions.map((edge) => ({
    ...edge,
    type: "Transition",
    name: `${edge.kind} → ${edge.to_map_id}`,
    position: edge.position && (edge.position.x || edge.position.y || edge.position.z)
      ? edge.position
      : (localMsbePartPosition(partsByName, edge.part_name) ? { x: localMsbePartPosition(partsByName, edge.part_name)[0], y: localMsbePartPosition(partsByName, edge.part_name)[1], z: localMsbePartPosition(partsByName, edge.part_name)[2] } : edge.position),
  }));
  let records;
  let totalCount;
  if (state.localMsbeKind === "parts") {
    const filteredParts = parts.filter(localMsbeLayerMatches);
    records = filteredParts.map((record) => ({ record, type: record.type, position: localMsbePosition(record), label: record.name }));
    totalCount = filteredParts.length;
  } else if (state.localMsbeKind === "regions") {
    records = regions.map((record) => ({ record, type: record.type, position: localMsbePosition(record), label: record.name }));
    totalCount = regions.length;
  } else if (state.localMsbeKind === "events") {
    records = events.map((record) => ({ record, type: record.type, position: localMsbeEventPosition(record, partsByName), label: record.name }));
    totalCount = events.length;
  } else if (state.localMsbeKind === "transitions") {
    records = transitionRecords.map((record) => ({ record, type: record.type, position: localMsbePosition(record), label: record.name }));
    totalCount = transitions.length;
  } else {
    records = parts.filter(localMsbeLayerMatches).map((record) => ({ record, type: record.type, position: localMsbePosition(record), label: record.name }))
      .concat(regions.map((record) => ({ record, type: record.type, position: localMsbePosition(record), label: record.name })))
      .concat(events.map((record) => ({ record, type: record.type, position: localMsbeEventPosition(record, partsByName), label: record.name })))
      .concat(transitionRecords.map((record) => ({ record, type: record.type, position: localMsbePosition(record), label: record.name })));
    totalCount = parts.filter(localMsbeLayerMatches).length + regions.length + events.length + transitions.length;
  }
  const plotted = records.filter((record) => record.position);
  const xs = plotted.map((record) => record.position[0]);
  const ys = plotted.map((record) => record.position[2]);
  const rawMinX = xs.length ? Math.min(...xs) : -500;
  const rawMaxX = xs.length ? Math.max(...xs) : 500;
  const rawMinY = ys.length ? Math.min(...ys) : -500;
  const rawMaxY = ys.length ? Math.max(...ys) : 500;
  const rawWidth = Math.max(100, rawMaxX - rawMinX);
  const rawHeight = Math.max(100, rawMaxY - rawMinY);
  const margin = Math.max(30, Math.max(rawWidth, rawHeight) * 0.08);
  const minX = rawMinX - margin;
  const minY = rawMinY - margin;
  const width = rawWidth + margin * 2;
  const height = rawHeight + margin * 2;
  state.coordinateBounds = { minX, minY, width, height };
  const map = document.getElementById("topology-map");
  map.setAttribute("viewBox", [minX, minY, width, height].join(" "));
  const grid = document.querySelector(".map-grid");
  if (grid) {
    grid.setAttribute("x", String(minX));
    grid.setAttribute("y", String(minY));
    grid.setAttribute("width", String(width));
    grid.setAttribute("height", String(height));
  }
  setZoom(state.zoom);
  const axis = svg("text", { x: minX + 10, y: minY + 16, class: "coordinate-axis" });
  axis.textContent = `${state.localMsbeMapId} · MSBE native X/Z · Y is height · ${state.localMsbeKind}`;
  els.regionLabels.appendChild(axis);
  const labelBudget = plotted.length <= 120 ? plotted.length : 45;
  plotted.forEach((item, index) => {
    const [x, yHeight, z] = item.position;
    const typeClass = localMsbeKindClass(item.type);
    const group = svg("g", { class: "coordinate-poi local-msbe " + typeClass, transform: `translate(${x} ${z})` });
    const radius = item.type === "ConnectCollision" || item.type === "Transition" ? 10 : item.type === "Collision" ? 6 : item.type === "Enemy" ? 4 : 2.5;
    const hit = svg("circle", { r: Math.max(9, radius * 2.5), class: "node-hit" });
    const core = svg("circle", { r: radius, class: "node-core local-msbe-core " + typeClass });
    const title = svg("title");
    title.textContent = `${item.label || item.type} · X ${x} / Y ${yHeight} / Z ${z}`;
    group.append(hit, core, title);
    if (index < labelBudget && (item.type === "Collision" || item.type === "ConnectCollision" || item.type === "Transition")) {
      const label = svg("text", { x: radius + 5, y: 3, class: "coordinate-poi-label" });
      label.textContent = item.label || item.type;
      group.appendChild(label);
    }
    group.addEventListener("click", () => renderLocalMsbeInspector(item.record, item.type, item.label, item.position));
    els.nodeLayer.appendChild(group);
  });
  renderLocalMsbeLayerMeta(mapRecord, plotted.length, totalCount);
  const noPosition = totalCount - plotted.length;
  els.graphStats.textContent = `${state.localMsbeMapId} · ${plotted.length}/${totalCount} plotted · parts ${parts.length} · regions ${regions.length} · events ${events.length} · transitions ${transitions.length} · native XYZ · routeable=false${noPosition ? ` · ${noPosition} no position` : ""}`;
}

function renderCoordinateLayerMeta() {
  const panel = els.coordinateLayerMeta;
  if (!panel) return;
  if (!["coordinates", "named-coordinates", "projected"].includes(state.mapMode)) {
    panel.hidden = true;
    return;
  }
  const escape = (value) => String(value ?? "").replace(/[&<>"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[character]));
  if (state.mapMode === "projected") {
    const total = state.projectedGraceTotal || state.onlineProjectedGraceRecords.length;
    panel.innerHTML = `<strong>${escape(state.projectedMaster)}</strong> · 命名赐福投影<br>显示：${state.onlineProjectedGraceRecords.length}/${total} 个赐福锚点<div class="layer-meta-note">坐标空间：master_tile_pixel，px/py 为 10496×10496 主图像素；仅用于在线地图定位，routeable=false，不是游戏 XYZ。</div>`;
    panel.hidden = false;
    return;
  }
  if (state.mapMode === "named-coordinates") {
    const total = state.coordinateNamedGraceTotal || state.onlineNamedGracePositionRecords.length;
    panel.innerHTML = `<strong>${escape(state.coordinateMapId)}</strong> · 命名赐福源坐标<br>显示：${state.onlineNamedGracePositionRecords.length}/${total} 个赐福锚点<div class="layer-meta-note">坐标空间：source_map_local_xyz；来自 Elden Ring Compass 的 mapId 实体坐标。它与 MapForGoblins XYZ 不是同一坐标框架，单独显示，routeable=false。</div>`;
    panel.hidden = false;
    return;
  }
  const tile = state.onlineTileRecords.find((record) => record.mapKey === state.coordinateMapId) || {};
  const indexRecord = (state.onlineIndex?.mapKeys?.records || []).find((record) => normalizeCoordinateMapKey(record.mapKey) === state.coordinateMapId) || {};
  const source = state.onlineIndex?.manifest?.source || {};
  const sourceKinds = (indexRecord.sourceKinds || []).join(", ") || "raw coordinate snapshots";
  const region = tile.subRegion || indexRecord.subRegion || "unclassified online layer";
  const majorRegion = tile.majorRegion || indexRecord.majorRegion || "—";
  const recordCount = indexRecord.recordCount ?? "—";
  const graceCount = tile.graceCount ?? "—";
  const dominance = tile.dominance == null ? "—" : tile.dominance;
  panel.innerHTML = `<strong>${escape(state.coordinateMapId)}</strong> · ${escape(region)}<br>位面/父区：${escape(majorRegion)} · 赐福索引：${escape(graceCount)} · 原始记录：${escape(recordCount)}<br>来源层：${escape(sourceKinds)}<div class="layer-meta-note">XYZ 点云覆盖，不加载图片/瓦片；坐标仅作在线证据，routeable=false。MapForGoblins ${escape(source.commit || "pinned snapshot")} · dominance=${escape(dominance)}</div>`;
  panel.hidden = false;
}

function focusOnlineCoordinate(record, kind, label) {
  if (kind === "named-grace-positions") return focusNamedGraceCoordinate(record, label);
  const mapKey = coordinateMapKeyForRecord(record, kind);
  const position = Array.isArray(record.position) ? record.position : [];
  if (!mapKey || position.length !== 3 || position.some((value) => !Number.isFinite(Number(value)))) return false;
  state.mapMode = "coordinates";
  state.coordinateMapId = mapKey;
  state.coordinateFocus = { mapKey, position: position.map(Number), label: String(label || "online coordinate"), kind };
  els.coordinateMapSelect.hidden = false;
  els.coordinateEntityKind.hidden = false;
  els.projectedMasterSelect.hidden = true;
  els.mapModes.forEach((button) => button.classList.toggle("active", button.dataset.mapMode === "coordinates"));
  populateCoordinateMapSelect();
  els.coordinateMapSelect.value = state.coordinateMapId;
  loadCoordinateItems();
  els.mapToast.textContent = state.coordinateFocus.label + " · located on " + mapKey + " · X " + position[0] + " / Y " + position[1] + " / Z " + position[2];
  return true;
}

function populateProjectedMasterSelect() {
  els.projectedMasterSelect.value = state.projectedMaster;
}

async function loadProjectedGraces() {
  /* projected-pixel view removed: its snapshot came from an unlicensed
   * repository (jw-ofs/elden-ring-map markers.js); use the self-datamined
   * game-local grace positions instead */
  state.onlineProjectedGraceRecords = [];
  state.projectedGraceTotal = 0;
  renderProjectedMap();
}

function focusProjectedCoordinate(record, label) {
  els.mapToast.textContent = "在线投影视图已移除（原数据源无许可证）；请使用命名源 XYZ（本地自产坐标）。";
  return false;
  const position = Array.isArray(record?.position) ? record.position : [];
  if (!record?.master || position.length !== 2 || position.some((value) => !Number.isFinite(Number(value)))) return false;
  state.mapMode = "projected";
  state.projectedMaster = record.master;
  state.projectedFocus = { master: record.master, position: position.map(Number), label: String(label || record.name || "projected grace") };
  state.coordinateBounds = null;
  els.coordinateMapSelect.hidden = true;
  els.coordinateEntityKind.hidden = true;
  els.projectedMasterSelect.hidden = false;
  els.mapModes.forEach((button) => button.classList.toggle("active", button.dataset.mapMode === "projected"));
  populateProjectedMasterSelect();
  loadProjectedGraces();
  els.mapToast.textContent = state.projectedFocus.label + " · " + record.master + " · px " + position[0] + " / py " + position[1];
  return true;
}

function renderProjectedMap() {
  els.edgeLayer.innerHTML = "";
  els.regionLabels.innerHTML = "";
  els.nodeLayer.innerHTML = "";
  const notice = svg("text", { x: 60, y: 80, class: "coordinate-axis" });
  notice.textContent = "在线投影视图已移除：原数据源（jw-ofs/elden-ring-map markers.js）无许可证；请改用命名源 XYZ（本地 MSBE 自产坐标）。";
  els.regionLabels.appendChild(notice);
  renderCoordinateLayerMeta();
  const records = state.onlineProjectedGraceRecords.filter((record) => record.master === state.projectedMaster);
  const width = 10496;
  const height = 10496;
  state.coordinateBounds = { minX: 0, minY: 0, width, height };
  const map = document.getElementById("topology-map");
  map.setAttribute("viewBox", "0 0 " + width + " " + height);
  const grid = document.querySelector(".map-grid");
  if (grid) {
    grid.setAttribute("x", "0");
    grid.setAttribute("y", "0");
    grid.setAttribute("width", String(width));
    grid.setAttribute("height", String(height));
  }
  setZoom(state.zoom);
  const axis = svg("text", { x: 160, y: 220, class: "coordinate-axis" });
  axis.textContent = state.projectedMaster + " · master tile pixels (px/py) · named grace anchors";
  els.regionLabels.appendChild(axis);
  records.forEach((record) => {
    const x = Number(record.position?.[0]);
    const y = Number(record.position?.[1]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    const group = svg("g", { class: "coordinate-poi projected-grace", transform: "translate(" + x + " " + y + ")" });
    const circle = svg("circle", { r: 42, class: "node-hit" });
    const core = svg("circle", { r: 22, class: "node-core projected-grace" });
    const title = svg("title");
    title.textContent = record.name + " · " + record.master + " · px " + x + " / py " + y;
    group.append(circle, core, title);
    if (records.length <= 90 || record.formal_id) {
      const label = svg("text", { x: 55, y: 5, class: "coordinate-poi-label" });
      label.textContent = record.name;
      group.appendChild(label);
    }
    group.addEventListener("click", () => renderProjectedAnchorInspector(record, record.name));
    els.nodeLayer.appendChild(group);
  });
  const focus = state.projectedFocus;
  if (focus && focus.master === state.projectedMaster) {
    const x = Number(focus.position[0]);
    const y = Number(focus.position[1]);
    if (Number.isFinite(x) && Number.isFinite(y)) {
      const focusGroup = svg("g", { class: "coordinate-focus", transform: "translate(" + x + " " + y + ")" });
      focusGroup.append(svg("circle", { r: 100, class: "coordinate-focus-ring" }), svg("circle", { r: 10, class: "coordinate-focus-core" }));
      els.nodeLayer.appendChild(focusGroup);
    }
  }
  els.graphStats.textContent = state.projectedMaster + " · " + records.length + "/" + (state.projectedGraceTotal || records.length) + " named grace projected anchors · master_tile_pixel · routeable=false";
}

function populateCoordinateMapSelect() {
  const options = new Map();
  state.onlineTileRecords.forEach((record) => options.set(record.mapKey, record));
  state.onlineMapPointRecords.forEach((record) => {
    if (!options.has(record.mapKey)) options.set(record.mapKey, { mapKey: record.mapKey });
  });
  state.onlineNamedGracePositionRecords.forEach((record) => {
    const mapKey = coordinateMapKeyForRecord(record, "named-grace-positions");
    if (mapKey && !options.has(mapKey)) options.set(mapKey, { mapKey });
  });
  (state.onlineIndex?.bosses?.records || []).forEach((record) => {
    const mapKey = normalizeCoordinateMapKey(record.map || record[2]);
    if (mapKey && !options.has(mapKey)) options.set(mapKey, { mapKey });
  });
  (state.onlineIndex?.mapKeys?.records || []).forEach((record) => {
    const mapKey = normalizeCoordinateMapKey(record.mapKey);
    if (mapKey && !options.has(mapKey)) options.set(mapKey, record);
  });
  els.coordinateMapSelect.innerHTML = "";
  [...options.values()].sort((a, b) => a.mapKey.localeCompare(b.mapKey)).forEach((record) => {
    const option = document.createElement("option");
    option.value = record.mapKey;
    option.textContent = record.mapKey + (record.subRegion || record.majorRegion ? " · " + (record.subRegion || record.majorRegion) : "");
    els.coordinateMapSelect.appendChild(option);
  });
  if (!options.has(state.coordinateMapId)) state.coordinateMapId = options.keys().next().value || "m10_00_00";
  els.coordinateMapSelect.value = state.coordinateMapId;
}

async function loadCoordinateItems() {
  state.onlineItemRecords = [];
  state.onlineGracePositionRecords = [];
  state.onlineBossPositionRecords = [];
  state.onlineMapConversionRecords = [];
  state.onlineEntityRecords = [];
  state.onlineGatheringRecords = [];
  try {
    const map = encodeURIComponent(state.coordinateMapId);
    const [graceResponse, bossResponse, conversionResponse, itemResponse, entityResponse, gatheringResponse] = await Promise.all([
      fetch("/api/catalog/grace-positions?map=" + map + "&limit=1000", { cache: "no-store" }),
      fetch("/api/catalog/boss-positions?map=" + map + "&limit=1000", { cache: "no-store" }),
      fetch("/api/catalog/map-conversions?map=" + map + "&limit=1000", { cache: "no-store" }),
      fetch("/api/catalog/online-items?map=" + map + "&limit=1000", { cache: "no-store" }),
      fetch("/api/catalog/entities?map=" + map + "&kind=" + encodeURIComponent(state.coordinateEntityKind === "all" ? "" : state.coordinateEntityKind) + "&limit=1000", { cache: "no-store" }),
      fetch("/api/catalog/gathering?map=" + map + "&limit=1000", { cache: "no-store" }),
    ]);
    if (!graceResponse.ok || !bossResponse.ok || !conversionResponse.ok || !itemResponse.ok || !entityResponse.ok || !gatheringResponse.ok) {
      throw new Error("online layer HTTP " + [graceResponse.status, bossResponse.status, conversionResponse.status, itemResponse.status, entityResponse.status, gatheringResponse.status].join("/"));
    }
    const [gracePayload, bossPayload, conversionPayload, itemPayload, entityPayload, gatheringPayload] = await Promise.all([
      graceResponse.json(), bossResponse.json(), conversionResponse.json(), itemResponse.json(), entityResponse.json(), gatheringResponse.json(),
    ]);
    state.onlineGracePositionRecords = gracePayload.records || [];
    state.coordinateGracePositionTotal = gracePayload.total_matches || state.onlineGracePositionRecords.length;
    state.onlineBossPositionRecords = bossPayload.records || [];
    state.coordinateBossPositionTotal = bossPayload.total_matches || state.onlineBossPositionRecords.length;
    state.onlineMapConversionRecords = conversionPayload.records || [];
    state.coordinateMapConversionTotal = conversionPayload.total_matches || state.onlineMapConversionRecords.length;
    state.onlineItemRecords = itemPayload.records || [];
    state.coordinateItemTotal = itemPayload.total_matches || state.onlineItemRecords.length;
    state.onlineEntityRecords = entityPayload.records || [];
    state.coordinateEntityTotal = entityPayload.total_matches || state.onlineEntityRecords.length;
    state.onlineGatheringRecords = gatheringPayload.records || [];
    state.coordinateGatheringTotal = gatheringPayload.total_matches || state.onlineGatheringRecords.length;
  } catch (error) {
    state.coordinateItemTotal = 0;
    state.coordinateGracePositionTotal = 0;
    state.coordinateBossPositionTotal = 0;
    state.coordinateMapConversionTotal = 0;
    state.coordinateEntityTotal = 0;
    state.coordinateGatheringTotal = 0;
    els.mapToast.textContent = "online POI layer load failed: " + error.message;
  }
  renderCoordinateMap();
}

async function loadNamedCoordinateLayer() {
  state.onlineNamedGracePositionRecords = [];
  state.coordinateNamedGraceTotal = 0;
  try {
    const map = encodeURIComponent(state.coordinateMapId);
    const response = await fetch("/api/catalog/named-grace-positions?map=" + map + "&limit=1000", { cache: "no-store" });
    if (!response.ok) throw new Error("named grace XYZ layer HTTP " + response.status);
    const payload = await response.json();
    state.onlineNamedGracePositionRecords = payload.records || [];
    state.coordinateNamedGraceTotal = payload.total_matches || state.onlineNamedGracePositionRecords.length;
  } catch (error) {
    els.mapToast.textContent = "命名赐福源坐标层加载失败：" + error.message;
  }
  renderNamedCoordinateMap();
}

function focusNamedGraceCoordinate(record, label) {
  const mapKey = coordinateMapKeyForRecord(record, "named-grace-positions");
  const position = Array.isArray(record?.position) ? record.position : [];
  if (!mapKey || position.length !== 3 || position.some((value) => !Number.isFinite(Number(value)))) return false;
  state.mapMode = "named-coordinates";
  state.coordinateMapId = mapKey;
  state.coordinateFocus = { mapKey, position: position.map(Number), label: String(label || record.name || "named grace"), kind: "named-grace-positions" };
  state.projectedFocus = null;
  els.coordinateMapSelect.hidden = false;
  els.coordinateEntityKind.hidden = true;
  els.projectedMasterSelect.hidden = true;
  els.mapModes.forEach((button) => button.classList.toggle("active", button.dataset.mapMode === "named-coordinates"));
  populateCoordinateMapSelect();
  els.coordinateMapSelect.value = state.coordinateMapId;
  loadNamedCoordinateLayer();
  els.mapToast.textContent = state.coordinateFocus.label + " · source map " + record.map + " · X " + position[0] + " / Y " + position[1] + " / Z " + position[2];
  return true;
}

function renderNamedCoordinateMap() {
  els.edgeLayer.innerHTML = "";
  els.regionLabels.innerHTML = "";
  els.nodeLayer.innerHTML = "";
  renderCoordinateLayerMeta();
  const records = state.onlineNamedGracePositionRecords;
  const plotRecords = records.map((record) => ({ raw: record, sourceKind: "named-grace-positions", position: record.position, label: record.name, kind: "named-grace-position" }));
  const xs = plotRecords.map((record) => Number(record.position?.[0])).filter(Number.isFinite);
  const ys = plotRecords.map((record) => Number(record.position?.[2])).filter(Number.isFinite);
  const rawMinX = xs.length ? Math.min(...xs) : -500;
  const rawMaxX = xs.length ? Math.max(...xs) : 500;
  const rawMinY = ys.length ? Math.min(...ys) : -500;
  const rawMaxY = ys.length ? Math.max(...ys) : 500;
  const rawWidth = Math.max(100, rawMaxX - rawMinX);
  const rawHeight = Math.max(100, rawMaxY - rawMinY);
  const margin = Math.max(30, Math.max(rawWidth, rawHeight) * 0.08);
  const minX = rawMinX - margin;
  const minY = rawMinY - margin;
  const width = rawWidth + margin * 2;
  const height = rawHeight + margin * 2;
  state.coordinateBounds = { minX, minY, width, height };
  const map = document.getElementById("topology-map");
  map.setAttribute("viewBox", [minX, minY, width, height].join(" "));
  const grid = document.querySelector(".map-grid");
  if (grid) {
    grid.setAttribute("x", String(minX));
    grid.setAttribute("y", String(minY));
    grid.setAttribute("width", String(width));
    grid.setAttribute("height", String(height));
  }
  setZoom(state.zoom);
  const axis = svg("text", { x: minX + 10, y: minY + 16, class: "coordinate-axis" });
  axis.textContent = state.coordinateMapId + " · source map entity X/Z · Y is height";
  els.regionLabels.appendChild(axis);
  plotRecords.forEach((record, index) => {
    const x = Number(record.position[0]);
    const y = Number(record.position[2]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    const group = svg("g", { class: "coordinate-poi named-grace-position", transform: "translate(" + x + " " + y + ")" });
    const circle = svg("circle", { r: 9, class: "node-hit" });
    const core = svg("circle", { r: 5, class: "node-core named-grace-position" });
    const title = svg("title");
    title.textContent = record.label + " · " + record.raw.map + " · X " + record.position[0] + " / Y " + record.position[1] + " / Z " + record.position[2];
    group.append(circle, core, title);
    if (records.length <= 90 || index < 60) {
      const label = svg("text", { x: 12, y: 3, class: "coordinate-poi-label" });
      label.textContent = record.label;
      group.appendChild(label);
    }
    group.addEventListener("click", () => renderOnlineCoordinateInspector(record.raw, record.sourceKind, record.label));
    els.nodeLayer.appendChild(group);
  });
  const focus = state.coordinateFocus;
  if (focus && focus.mapKey === state.coordinateMapId && Array.isArray(focus.position)) {
    const x = Number(focus.position[0]);
    const y = Number(focus.position[2]);
    if (Number.isFinite(x) && Number.isFinite(y)) {
      const focusGroup = svg("g", { class: "coordinate-focus", transform: "translate(" + x + " " + y + ")" });
      focusGroup.append(svg("circle", { r: Math.max(20, Math.min(width, height) * 0.035), class: "coordinate-focus-ring" }), svg("circle", { r: 3, class: "coordinate-focus-core" }));
      els.nodeLayer.appendChild(focusGroup);
    }
  }
  els.graphStats.textContent = state.coordinateMapId + " · " + records.length + "/" + (state.coordinateNamedGraceTotal || records.length) + " named grace source XYZ · routeable=false · frame=source_map_local_xyz";
}

function renderCoordinateMap() {
  els.edgeLayer.innerHTML = "";
  els.regionLabels.innerHTML = "";
  els.nodeLayer.innerHTML = "";
  renderCoordinateLayerMeta();
  const points = state.onlineMapPointRecords.filter((record) => record.mapKey === state.coordinateMapId);
  const gracePositions = state.onlineGracePositionRecords;
  const bosses = state.onlineBossPositionRecords;
  const conversions = state.onlineMapConversionRecords;
  const items = state.onlineItemRecords;
  const entities = state.onlineEntityRecords;
  const gathering = state.onlineGatheringRecords;
  const plotRecords = gracePositions.map((record) => ({ position: record.position, label: "raw grace position #" + record.source_index + " · " + (record.major_region || record.sub_region || "unknown region"), kind: "grace-position" }))
    .concat(bosses.map((record) => ({ position: record.position, label: record.name || "Boss", kind: "boss" })))
    .concat(conversions.map((record) => ({ position: record.position, label: "map conversion · " + record.source_map + " → " + record.destination_map, kind: "conversion" })))
    .concat(points.map((record) => ({ position: record.position, label: (record.names || []).join(" / "), kind: "point" })))
    .concat(items.map((record) => ({ position: record.position, label: (record.items || []).map((item) => item.name || item.id).join(" / "), kind: "item" })))
    .concat(entities.map((record) => ({ position: record.position, label: record.name || record.model || record.entity_id, kind: "entity" })))
    .concat(gathering.map((record) => ({ position: record.position, label: record.name || record.model, kind: "gathering" })));
  const coordinateSourceRecords = [
    ...gracePositions.map((record) => ({ raw: record, sourceKind: "grace-positions" })),
    ...bosses.map((record) => ({ raw: record, sourceKind: "boss-positions" })),
    ...conversions.map((record) => ({ raw: record, sourceKind: "map-conversions" })),
    ...points.map((record) => ({ raw: record, sourceKind: "map-points" })),
    ...items.map((record) => ({ raw: record, sourceKind: "items" })),
    ...entities.map((record) => ({ raw: record, sourceKind: "entities" })),
    ...gathering.map((record) => ({ raw: record, sourceKind: "gathering" })),
  ];
  plotRecords.forEach((record, index) => Object.assign(record, coordinateSourceRecords[index]));
  const xs = plotRecords.map((record) => Number(record.position[0])).filter(Number.isFinite);
  const ys = plotRecords.map((record) => Number(record.position[2])).filter(Number.isFinite);
  const rawMinX = xs.length ? Math.min(...xs) : -500;
  const rawMaxX = xs.length ? Math.max(...xs) : 500;
  const rawMinY = ys.length ? Math.min(...ys) : -500;
  const rawMaxY = ys.length ? Math.max(...ys) : 500;
  const rawWidth = Math.max(100, rawMaxX - rawMinX);
  const rawHeight = Math.max(100, rawMaxY - rawMinY);
  const margin = Math.max(30, Math.max(rawWidth, rawHeight) * 0.08);
  const minX = rawMinX - margin;
  const minY = rawMinY - margin;
  const width = rawWidth + margin * 2;
  const height = rawHeight + margin * 2;
  state.coordinateBounds = { minX, minY, width, height };
  const map = document.getElementById("topology-map");
  map.setAttribute("viewBox", [minX, minY, width, height].join(" "));
  const grid = document.querySelector(".map-grid");
  if (grid) {
    grid.setAttribute("x", String(minX));
    grid.setAttribute("y", String(minY));
    grid.setAttribute("width", String(width));
    grid.setAttribute("height", String(height));
  }
  setZoom(state.zoom);
  const axis = svg("text", { x: minX + 10, y: minY + 16, class: "coordinate-axis" });
  axis.textContent = state.coordinateMapId + " · X/Z online game coordinates · Y is height";
  els.regionLabels.appendChild(axis);
  plotRecords.forEach((record, index) => {
    const x = Number(record.position[0]);
    const y = Number(record.position[2]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    const group = svg("g", { class: "coordinate-poi " + record.kind, transform: "translate(" + x + " " + y + ")" });
    const circle = svg("circle", { r: record.kind === "point" ? 7 : record.kind === "boss" ? 5 : 3, class: "node-hit" });
    const core = svg("circle", { r: record.kind === "point" ? 4 : record.kind === "boss" ? 3 : 2, class: "node-core " + record.kind });
    const title = svg("title");
    title.textContent = record.label + " · X " + record.position[0] + " / Y " + record.position[1] + " / Z " + record.position[2];
    group.append(circle, core, title);
    if (record.kind === "point" && (points.length <= 90 || index < 60)) {
      const label = svg("text", { x: 10, y: 3, class: "coordinate-poi-label" });
      label.textContent = record.label || "map point";
      group.appendChild(label);
    }
    group.addEventListener("click", () => {
      els.mapToast.textContent = record.label + " · X " + record.position[0] + " / Y " + record.position[1] + " / Z " + record.position[2];
    });
    group.addEventListener("click", () => renderOnlineCoordinateInspector(record.raw, record.sourceKind, record.label));
    els.nodeLayer.appendChild(group);
  });
  const focus = state.coordinateFocus;
  if (focus && focus.mapKey === state.coordinateMapId && Array.isArray(focus.position)) {
    const x = Number(focus.position[0]);
    const y = Number(focus.position[2]);
    if (Number.isFinite(x) && Number.isFinite(y)) {
      const radius = Math.max(10, Math.min(width, height) * 0.035);
      const focusGroup = svg("g", { class: "coordinate-focus", transform: "translate(" + x + " " + y + ")" });
      const ring = svg("circle", { r: radius, class: "coordinate-focus-ring" });
      const core = svg("circle", { r: 3, class: "coordinate-focus-core" });
      const title = svg("title");
      title.textContent = focus.label + " · X " + focus.position[0] + " / Y " + focus.position[1] + " / Z " + focus.position[2];
      focusGroup.append(ring, core, title);
      els.nodeLayer.appendChild(focusGroup);
    }
  }
  const coverage = state.onlineIndex?.manifest?.coverage || {};
  els.graphStats.textContent = state.coordinateMapId + " · " + gracePositions.length + "/" + (state.coordinateGracePositionTotal || gracePositions.length) + " raw grace positions · " + bosses.length + "/" + (state.coordinateBossPositionTotal || bosses.length) + " bosses · " + conversions.length + "/" + (state.coordinateMapConversionTotal || conversions.length) + " map conversions · " + points.length + " named points · " + items.length + "/" + (state.coordinateItemTotal || items.length) + " items · " + entities.length + "/" + (state.coordinateEntityTotal || entities.length) + " " + state.coordinateEntityKind + " entities · " + gathering.length + "/" + (state.coordinateGatheringTotal || gathering.length) + " gathering nodes · " + (coverage.tileRegionRecords || 0) + " map layers";
}
