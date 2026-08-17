function mapKeyFromParts(area, gridX, gridZ) {
  const pad = (value) => String(value ?? 0).padStart(2, "0");
  return "m" + pad(area) + "_" + pad(gridX) + "_" + pad(gridZ);
}

function populateCoordinateMapSelect() {
  const options = new Map();
  state.onlineTileRecords.forEach((record) => options.set(record.mapKey, record));
  state.onlineMapPointRecords.forEach((record) => {
    if (!options.has(record.mapKey)) options.set(record.mapKey, { mapKey: record.mapKey });
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
  state.onlineEntityRecords = [];
  state.onlineGatheringRecords = [];
  try {
    const map = encodeURIComponent(state.coordinateMapId);
    const [graceResponse, bossResponse, itemResponse, entityResponse, gatheringResponse] = await Promise.all([
      fetch("/api/catalog/grace-positions?map=" + map + "&limit=500", { cache: "no-store" }),
      fetch("/api/catalog/boss-positions?map=" + map + "&limit=500", { cache: "no-store" }),
      fetch("/api/catalog/online-items?map=" + map + "&limit=500", { cache: "no-store" }),
      fetch("/api/catalog/entities?map=" + map + "&kind=enemy&limit=500", { cache: "no-store" }),
      fetch("/api/catalog/gathering?map=" + map + "&limit=500", { cache: "no-store" }),
    ]);
    if (!graceResponse.ok || !bossResponse.ok || !itemResponse.ok || !entityResponse.ok || !gatheringResponse.ok) {
      throw new Error("online layer HTTP " + [graceResponse.status, bossResponse.status, itemResponse.status, entityResponse.status, gatheringResponse.status].join("/"));
    }
    const [gracePayload, bossPayload, itemPayload, entityPayload, gatheringPayload] = await Promise.all([
      graceResponse.json(), bossResponse.json(), itemResponse.json(), entityResponse.json(), gatheringResponse.json(),
    ]);
    state.onlineGracePositionRecords = gracePayload.records || [];
    state.coordinateGracePositionTotal = gracePayload.total_matches || state.onlineGracePositionRecords.length;
    state.onlineBossPositionRecords = bossPayload.records || [];
    state.coordinateBossPositionTotal = bossPayload.total_matches || state.onlineBossPositionRecords.length;
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
  const points = state.onlineMapPointRecords.filter((record) => record.mapKey === state.coordinateMapId);
  const gracePositions = state.onlineGracePositionRecords;
  const bosses = state.onlineBossPositionRecords;
  const items = state.onlineItemRecords;
  const entities = state.onlineEntityRecords;
  const gathering = state.onlineGatheringRecords;
  const plotRecords = gracePositions.map((record) => ({ position: record.position, label: "raw grace position #" + record.source_index + " · " + (record.major_region || record.sub_region || "unknown region"), kind: "grace-position" }))
    .concat(bosses.map((record) => ({ position: record.position, label: record.name || "Boss", kind: "boss" })))
    .concat(points.map((record) => ({ position: record.position, label: (record.names || []).join(" / "), kind: "point" })))
    .concat(items.map((record) => ({ position: record.position, label: (record.items || []).map((item) => item.name || item.id).join(" / "), kind: "item" })))
    .concat(entities.map((record) => ({ position: record.position, label: record.name || record.model || record.entity_id, kind: "entity" })))
    .concat(gathering.map((record) => ({ position: record.position, label: record.name || record.model, kind: "gathering" })));
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
    els.nodeLayer.appendChild(group);
  });
  const coverage = state.onlineIndex?.manifest?.coverage || {};
  els.graphStats.textContent = state.coordinateMapId + " · " + gracePositions.length + "/" + (state.coordinateGracePositionTotal || gracePositions.length) + " raw grace positions · " + bosses.length + "/" + (state.coordinateBossPositionTotal || bosses.length) + " bosses · " + points.length + " named points · " + items.length + "/" + (state.coordinateItemTotal || items.length) + " items · " + entities.length + "/" + (state.coordinateEntityTotal || entities.length) + " enemies · " + gathering.length + "/" + (state.coordinateGatheringTotal || gathering.length) + " gathering nodes · " + (coverage.tileRegionRecords || 0) + " map layers";
}
