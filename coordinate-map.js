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
  state.onlineProjectedGraceRecords = [];
  state.projectedGraceTotal = 0;
  try {
    const master = encodeURIComponent(state.projectedMaster);
    const response = await fetch("/api/catalog/projected-graces?master=" + master + "&limit=1000", { cache: "no-store" });
    if (!response.ok) throw new Error("projected grace layer HTTP " + response.status);
    const payload = await response.json();
    state.onlineProjectedGraceRecords = payload.records || [];
    state.projectedGraceTotal = payload.total_matches || state.onlineProjectedGraceRecords.length;
  } catch (error) {
    els.mapToast.textContent = "在线投影层加载失败：" + error.message;
  }
  renderProjectedMap();
}

function focusProjectedCoordinate(record, label) {
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
