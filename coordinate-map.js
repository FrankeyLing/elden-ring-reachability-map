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
  if (state.mapMode !== "coordinates") {
    panel.hidden = true;
    return;
  }
  const escape = (value) => String(value ?? "").replace(/[&<>"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[character]));
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
  const mapKey = coordinateMapKeyForRecord(record, kind);
  const position = Array.isArray(record.position) ? record.position : [];
  if (!mapKey || position.length !== 3 || position.some((value) => !Number.isFinite(Number(value)))) return false;
  state.mapMode = "coordinates";
  state.coordinateMapId = mapKey;
  state.coordinateFocus = { mapKey, position: position.map(Number), label: String(label || "online coordinate"), kind };
  els.coordinateMapSelect.hidden = false;
  els.coordinateEntityKind.hidden = false;
  els.mapModes.forEach((button) => button.classList.toggle("active", button.dataset.mapMode === "coordinates"));
  populateCoordinateMapSelect();
  els.coordinateMapSelect.value = state.coordinateMapId;
  loadCoordinateItems();
  els.mapToast.textContent = state.coordinateFocus.label + " · located on " + mapKey + " · X " + position[0] + " / Y " + position[1] + " / Z " + position[2];
  return true;
}

function populateCoordinateMapSelect() {
  const options = new Map();
  state.onlineTileRecords.forEach((record) => options.set(record.mapKey, record));
  state.onlineMapPointRecords.forEach((record) => {
    if (!options.has(record.mapKey)) options.set(record.mapKey, { mapKey: record.mapKey });
  });
  (state.onlineIndex?.bosses?.records || []).forEach((record) => {
    const mapKey = normalizeCoordinateMapKey(record[2]);
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
