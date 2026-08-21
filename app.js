/* Elden Ring Reachability Map Beta — player-first route planner.
 *
 * Depends on framework.js (RouteFramework). The page loads ONLY the package
 * manifest and the data packages; no research indexes, no online coordinate
 * catalogs, no local MSBE/EMEVD files are fetched on startup. Every package
 * failure is isolated and reported in the coverage panel.
 */
"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
const DEFAULT_ROUTE_PROFILE = "physical_no_fast_travel";

const KIND_LABELS = {
  grace: "赐福",
  boss: "Boss",
  target: "物品 / 目标",
  entrance: "入口",
  lift: "升降梯",
  teleport: "传送点",
  junction: "岔路 / 枢纽",
  state: "世界状态",
  transition: "过渡",
  other: "其他",
};

const ENTITY_KIND_LABELS = {
  accessory: "护符 / 饰品",
  armor: "防具",
  armor_set: "防具套装",
  ash_of_war: "战灰",
  boss: "Boss",
  enemy: "敌人",
  grace: "赐福",
  item: "道具",
  location: "地点",
  npc: "友方角色",
  weapon: "武器",
  spell: "法术",
  unknown: "待分类",
};

const ENTITY_METHOD_LABELS = {
  pickup: "固定拾取",
  drop: "敌人掉落",
  drops: "Boss掉落",
  boss_reward: "Boss奖励",
  purchase: "商店购买",
  quest_reward: "任务奖励",
  exchange: "交换",
  craft: "制作",
};

const ENTITY_BINDING_LABELS = {
  routeable_anchor: "已绑定正式导航锚点",
  semantic_endpoint: "已有语义终点，尚未接入路线",
  coordinate_endpoint: "已有坐标终点，尚未绑定拓扑锚点",
  not_bound: "尚未解析具体终点",
};

const DIRECTION_LABELS = {
  forward: "正向",
  one_way: "单向",
  one_way_drop: "单向跳落",
  teleport: "传送",
  return: "返回",
};

const PREFERENCE_HINTS = {
  balanced: "综合时间与风险，适合首次探索。",
  fast: "优先较短时间，允许承担更高落差和战斗风险。",
  safe: "显著回避高风险跳落，可能增加路线长度。",
};

/* 中文搜索别名（产品数据：让玩家用常用中文名找到英文命名的拓扑节点）。
 * 键是中文搜索词，值是该词在节点 id/label/region/floor 中可能出现的英文关键词。 */
const SEARCH_ALIASES = {
  "玛莲妮亚": ["malenia"],
  "葛瑞克": ["godrick"],
  "接肢": ["godrick", "grafted"],
  "拉卡德": ["rykard"],
  "玛利喀斯": ["maliketh"],
  "黑剑": ["maliketh"],
  "拉塔恩": ["radahn"],
  "碎星": ["radahn", "starscourge"],
  "蒙葛特": ["morgott"],
  "蒙格": ["mohg"],
  "神皮": ["godskin"],
  "罗蕾塔": ["loretta"],
  "龙人士兵": ["dragonkin"],
  "双月": ["rellana", "moon"],
  "蕾拉娜": ["rellana"],
  "梅瑟莫": ["messmer"],
  "梅斯梅尔": ["messmer"],
  "古兰桑克斯": ["gransax"],
  "雷电": ["bolt of gransax"],
  "黄金树大教堂": ["erdtree sanctuary"],
  "史东薇尔": ["stormveil"],
  "法姆亚兹拉": ["farum"],
  "圣树": ["haligtree"],
  "艾布雷菲尔": ["elphael"],
  "希芙拉": ["siofra"],
  "安瑟尔": ["ainsel"],
  "诺克隆": ["nokron"],
  "诺克史黛拉": ["nokstella"],
  "深根": ["deeproot"],
  "腐败湖": ["lake of rot"],
  "蒙格温": ["mohgwyn"],
  "亚坛": ["altus"],
  "格密尔": ["gelmir"],
  "火山官邸": ["volcano manor"],
  "盖利德": ["caelid"],
  "宁姆格福": ["limgrave"],
  "利耶尼亚": ["liurnia"],
  "化圣雪原": ["snowfield"],
  "巨人山顶": ["mountaintops"],
  "幽影之地": ["shadow realm"],
  "影之塔": ["shadow keep"],
  "恩希斯": ["ensis"],
  "米德拉": ["midra"],
  "劳赫": ["rauh"],
  "拉乌": ["rauh"],
  "龙教堂": ["dragon temple"],
  "王城": ["leyndell", "royal capital"],
  "罗德尔": ["leyndell"],
  "灰烬王城": ["ashen capital", "capital of ash"],
  "学院": ["raya lucaria", "academy"],
  "卡利亚": ["caria"],
  "神皮双人组": ["godskin duo"],
  "双人组": ["godskin duo"],
  "化圣": ["snowfield"],
  "仪典镇": ["ordina"],
  "索尔城": ["castle sol"],
  "红狮子城": ["redmane"],
  "血王": ["mohg"],
  "女武神": ["malenia"],
  "米凯拉": ["miquella"],
  "拉达冈": ["radagon"],
  "艾尔登之兽": ["elden beast"],
  "葛孚雷": ["godfrey"],
  "初代艾尔登之王": ["godfrey"],
  "荷莱露": ["hoarah loux"],
  "百智": ["gideon"],
  "维克": ["vyke"],
  "火焰巨人": ["fire giant"],
  "恶兆": ["omen", "margit"],
  "大树守卫": ["tree sentinel"],
  "双树守卫": ["tree sentinel"],
  "罗尔塔": ["loretta"],
  "神皮贵族": ["godskin noble"],
  "神皮使徒": ["godskin apostle"],
  "祖灵": ["ancestor spirit"],
  "仿身泪滴": ["mimic tear"],
  "黑刀": ["black knife"],
  "石像鬼": ["gargoyle"],
  "黄金河马": ["hippopotamus"],
  "墓穴": ["catacombs"],
  "监牢": ["gaol"],
  "洞窟": ["cave", "grotto"],
  "隧道": ["tunnel"],
  "英雄墓地": ["hero's grave"],
  "井": ["well"],
  "升降梯": ["lift", "elevator"],
  "电梯": ["lift", "elevator"],
  "传送门": ["waygate", "sending gate"],
  "赐福": ["grace"],
};

const state = {
  store: window.RouteFramework.createStore(),
  zhMap: null,          // official Chinese mapping (data/v1/zh-cn/official-zh-mapping.json)
  origin: null,
  destination: null,
  conditions: new Set(),
  routeProfiles: null,
  routeProfile: DEFAULT_ROUTE_PROFILE,
  preference: "balanced",
  layer: "surface",
  mapView: "regions",      // "regions" (aggregate overview) | "detail" (one region)
  detailRegion: null,
  regionLayoutCache: null,
  zoom: 1,
  route: null,
  selectedNode: null,
  loaded: false,
  entitySearchRequest: 0,
};

/* ---- official Chinese display helpers ---- */

/* Returns the official-Chinese display text for a mapping entry.
 * official / composite / partial levels display Chinese (partial keeps the
 * English remainder); already_zh and uncovered fall back to the raw value. */
function zhText(entry, fallback) {
  if (!entry) return fallback;
  if (entry.level === "official" || entry.level === "official_bracket_main"
    || entry.level === "official_slash_parts" || entry.level === "official_comma_parts"
    || entry.level === "official_to_parts" || entry.level === "official_patch"
    || entry.level === "composite" || entry.level === "partial") {
    return entry.zh;
  }
  return fallback;
}

function nodeLabelZh(id) {
  const raw = state.store.node(id)?.label || id;
  return zhText(state.zhMap?.nodes?.[id]?.label, raw);
}

function regionZh(id) {
  const raw = state.store.node(id)?.region || "";
  return zhText(state.zhMap?.nodes?.[id]?.region, raw);
}

function floorZh(id) {
  const raw = state.store.node(id)?.floor || "";
  return zhText(state.zhMap?.nodes?.[id]?.floor, raw);
}

function descriptionZh(id) {
  const raw = state.store.node(id)?.description || "";
  return zhText(state.zhMap?.nodes?.[id]?.description, raw);
}

function modeZh(edge) {
  const raw = edge.mode || edge.transitionType || "";
  return zhText(state.zhMap?.edges?.[edge.id]?.mode, raw);
}

function noteZh(edge) {
  const raw = edge.note || "";
  return zhText(state.zhMap?.edges?.[edge.id]?.note, raw);
}

function conditionLabelZh(id) {
  const raw = state.store.condition(id)?.label || id;
  return zhText(state.zhMap?.conditions?.[id]?.label, raw);
}

function conditionHintZh(id) {
  const raw = state.store.condition(id)?.hint || "";
  return zhText(state.zhMap?.conditions?.[id]?.hint, raw);
}

/* Registers the official Chinese names as search aliases so players can type
 * 中文 directly (alias: zh name -> the node's English label/id keywords). */
function registerZhSearchAliases() {
  const aliases = {};
  if (!state.zhMap) return;
  for (const [nodeId, fields] of Object.entries(state.zhMap.nodes || {})) {
    const entry = fields?.label;
    if (!entry || entry.level === "already_zh" || entry.level === "uncovered") continue;
    const node = state.store.node(nodeId);
    if (!node) continue;
    aliases[entry.zh] = [node.label, nodeId];
  }
  state.store.registerAliases(aliases);
}

const els = {
  datasetVersion: document.getElementById("dataset-version"),
  packageStatusChip: document.getElementById("package-status-chip"),
  originSearch: document.getElementById("origin-search"),
  destinationSearch: document.getElementById("destination-search"),
  swapRoute: document.getElementById("swap-route"),
  routeProfile: document.getElementById("route-profile-select"),
  routeProfileHint: document.getElementById("route-profile-hint"),
  conditions: document.getElementById("conditions"),
  conditionsAll: document.getElementById("conditions-all"),
  conditionsNone: document.getElementById("conditions-none"),
  plan: document.getElementById("plan-route"),
  reset: document.getElementById("reset-route"),
  preferenceHint: document.getElementById("preference-hint"),
  graphStats: document.getElementById("graph-stats"),
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
  routeEmptyHint: document.getElementById("route-empty-hint"),
  nodeInspector: document.getElementById("node-inspector"),
  mapToast: document.getElementById("map-toast"),
  mapBack: document.getElementById("map-back"),
  mapTransform: document.getElementById("map-transform"),
  copyRoute: document.getElementById("copy-route"),
  coveragePanel: document.getElementById("coverage-panel"),
  entitySearch: document.getElementById("entity-search"),
  entityResults: document.getElementById("entity-results"),
  entityDetail: document.getElementById("entity-detail"),
  coverageNote: document.getElementById("coverage-note"),
  engineStatus: document.getElementById("engine-status"),
  footerCoverage: document.getElementById("footer-coverage"),
  loadingState: document.getElementById("loading-state"),
  topologyMap: document.getElementById("topology-map"),
  mapStage: document.querySelector(".map-stage"),
};

/* ---------------- combobox ---------------- */

function comboboxGroup(results) {
  const groups = new Map();
  for (const result of results) {
    const key = result.kind || "other";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(result);
  }
  return groups;
}

function attachCombobox(input, onSelect) {
  const root = input.closest(".combobox");
  const list = root.querySelector(".combobox-list");
  let items = [];
  let activeIndex = -1;

  function close() {
    list.hidden = true;
    activeIndex = -1;
  }

  function render(query) {
    const results = state.store.search(query, 120);
    items = results;
    const groups = comboboxGroup(results);
    if (!results.length) {
      list.innerHTML = `<div class="combobox-empty">无匹配节点${state.store.hasData() ? "" : "（尚未加载数据包）"}</div>`;
      list.hidden = false;
      return;
    }
    let html = "";
    for (const [kind, members] of groups) {
      html += `<div class="combobox-group">${KIND_LABELS[kind] || kind} · ${members.length}</div>`;
      for (const item of members) {
        const layers = item.layer ? ` · ${layerZh(item.layer)}` : "";
        html += `<div class="combobox-item" data-id="${escapeHtml(item.id)}">
          <span class="combobox-item-label">${escapeHtml(nodeLabelZh(item.id))}</span>
          <span class="combobox-item-meta">${escapeHtml(regionZh(item.id))}${layers}</span>
        </div>`;
      }
    }
    list.innerHTML = html;
    list.hidden = false;
    list.querySelectorAll(".combobox-item").forEach((element) => {
      element.addEventListener("mousedown", (event) => {
        event.preventDefault();
        const id = event.currentTarget.dataset.id;
        const index = items.findIndex((item) => item.id === id);
        if (index >= 0) pick(index);
      });
      element.addEventListener("mouseenter", () => {
        const id = element.dataset.id;
        const index = items.findIndex((item) => item.id === id);
        if (index >= 0) setActive(index);
      });
    });
  }

  function setActive(index) {
    activeIndex = index;
    list.querySelectorAll(".combobox-item").forEach((element, i) => {
      element.classList.toggle("active", i === index);
    });
    const active = list.querySelector(".combobox-item.active");
    if (active) active.scrollIntoView({ block: "nearest" });
  }

  function pick(index) {
    const item = items[index];
    if (!item) return;
    input.value = `${item.label}（${item.region || item.layer || ""}）`;
    input.dataset.nodeId = item.id;
    onSelect(item);
    close();
  }

  input.addEventListener("input", () => {
    delete input.dataset.nodeId;
    render(input.value);
  });
  input.addEventListener("focus", () => {
    render(input.value);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (list.hidden) { render(input.value); return; }
      setActive(Math.min(activeIndex + 1, items.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive(Math.max(activeIndex - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (activeIndex >= 0) pick(activeIndex);
      else if (items.length) pick(0);
    } else if (event.key === "Escape") {
      close();
    }
  });
  document.addEventListener("click", (event) => {
    if (!root.contains(event.target)) close();
  });
  return { close };
}

/* ---------------- escaping ---------------- */

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[character]));
}

function entityName(entity) {
  return entity?.name?.zh || entity?.name?.en || entity?.id || "未命名实体";
}

function entityKindLabel(entity) {
  return ENTITY_KIND_LABELS[entity?.kind] || entity?.category || entity?.kind || "其他";
}

function entityTopologyLabel(status) {
  return {
    routeable_anchor: "已有正式导航锚点",
    semantic_graph_node: "已有语义节点，尚未成为正式路线终点",
    not_bound: "尚未绑定拓扑锚点",
  }[status] || "拓扑状态未知";
}

function renderEntityResults(payload) {
  const records = payload?.records || [];
  if (!records.length) {
    els.entityResults.innerHTML = `<div class="entity-placeholder">没有匹配实体。</div>`;
    return;
  }
  els.entityResults.innerHTML = records.map((entity) => {
    const name = entity.name?.zh || entity.name?.en || entity.id;
    const secondary = entity.name?.en && entity.name?.zh && entity.name.en !== entity.name.zh
      ? ` · ${entity.name.en}` : "";
    const counts = entity.counts || {};
    const acquisition = Number(counts.acquisitions || 0);
    return `<button class="entity-result" type="button" data-entity-id="${escapeHtml(entity.id)}">
      <span class="entity-result-copy"><strong>${escapeHtml(name)}</strong><small>${escapeHtml(entityKindLabel(entity))}${escapeHtml(secondary)}</small></span>
      <span class="entity-result-meta">${acquisition ? `${acquisition}种获取` : escapeHtml(entityTopologyLabel(entity.topologyStatus))}</span>
    </button>`;
  }).join("");
  els.entityResults.querySelectorAll("[data-entity-id]").forEach((button) => {
    button.addEventListener("click", () => loadEntityDetail(button.dataset.entityId));
  });
}

function renderEntityDetail(payload) {
  const entity = payload?.entity;
  if (!payload?.found || !entity) {
    els.entityDetail.classList.add("hidden");
    return;
  }
  const name = entityName(entity);
  const topology = entity.topology || {};
  const acquisitions = entity.acquisitions || [];
  const shopSales = entity.shopSales || [];
  const reinforcement = entity.reinforcementIncoming || [];
  const outgoing = entity.reinforcementOutgoing || [];
  const sources = (entity.sources || []).join("、") || "未记录";
  const endpointCount = acquisitions.reduce((sum, relation) => sum + (relation.endpointInstances?.length || 0), 0);
  const routeAnchorNodes = (topology.graphNodes || []).filter((node) => node.routeable && state.store.node(node.id));
  const renderEndpoint = (endpoint) => {
    const position = endpoint.position || {};
    const xyz = ["x", "y", "z"].every((axis) => Number.isFinite(Number(position[axis])))
      ? `XYZ ${Number(position.x).toFixed(3)}, ${Number(position.y).toFixed(3)}, ${Number(position.z).toFixed(3)}`
      : "XYZ 未解析";
    const kind = endpoint.spawnKind || endpoint.kind || "endpoint";
    const identity = endpoint.npcParamId != null ? `NpcParam ${endpoint.npcParamId}` : "固定拾取点";
    const seller = endpoint.merchantName ? ` · ${endpoint.merchantName}` : "";
    const row = endpoint.rowId != null ? ` · ShopLineupParam ${endpoint.rowId}` : "";
    return `<div class="entity-endpoint"><strong>${escapeHtml(endpoint.map || "未知地图")}</strong><span>${escapeHtml(endpoint.part || "未知部件")} · ${escapeHtml(identity)} · ${escapeHtml(kind)}${escapeHtml(seller)}${escapeHtml(row)}</span><small>${escapeHtml(xyz)}</small></div>`;
  };
  const acquisitionHtml = acquisitions.length
    ? acquisitions.slice(0, 40).map((relation) => {
      const method = ENTITY_METHOD_LABELS[relation.method] || relation.method || "其他关系";
      const endpoints = relation.endpointInstances?.length ? ` · ${relation.endpointInstances.length}个具体终点` : "";
      const evidence = relation.verification || "证据状态未标记";
      const binding = relation.topologyBinding || {};
      const bindingLabel = ENTITY_BINDING_LABELS[binding.status] || "拓扑终点状态未知";
      const merchant = relation.merchantShopBinding?.merchantName
        || (relation.sellerStatus === "unresolved" ? "卖家身份未解析" : "");
      const lineup = relation.lineupRow != null ? ` · ShopLineupParam ${relation.lineupRow}` : "";
      const sourceLabel = merchant || lineup ? `<small class="entity-acquisition-source">${escapeHtml(merchant)}${escapeHtml(lineup)}</small>` : "";
      const endpointList = relation.endpointInstances?.length
        ? `<details class="entity-endpoint-details"><summary>查看具体终点（前 ${Math.min(relation.endpointInstances.length, 8)} 个，共 ${relation.endpointInstances.length} 个）</summary><div class="entity-endpoint-list">${relation.endpointInstances.slice(0, 8).map(renderEndpoint).join("")}${relation.endpointInstances.length > 8 ? `<small class="entity-endpoint-more">其余 ${relation.endpointInstances.length - 8} 个终点保留在数据接口中。</small>` : ""}</div></details>`
        : "";
      return `<div class="entity-detail-row"><div class="entity-detail-row-head"><strong>${escapeHtml(method)}</strong><span>${escapeHtml(bindingLabel)} · ${escapeHtml(evidence)}${escapeHtml(endpoints)}</span></div>${sourceLabel}${endpointList}</div>`;
    }).join("")
    : `<div class="entity-placeholder">当前没有已登记获取关系。</div>`;
  const shopSalesHtml = shopSales.length
    ? `<div class="entity-detail-section"><div class="entity-detail-section-title">商店库存 · ${shopSales.length} 条行记录</div>${shopSales.slice(0, 80).map((sale) => {
      const item = sale.items?.[0]?.name?.zh || sale.items?.[0]?.name?.en || sale.items?.[0]?.item || "未命名物品";
      const row = sale.lineupRow != null ? `ShopLineupParam ${sale.lineupRow}` : "商店行未知";
      const endpoint = sale.endpointInstances?.[0];
      const location = endpoint?.map ? ` · ${endpoint.map}` : " · 卖家位置未绑定";
      return `<div class="entity-detail-row"><div class="entity-detail-row-head"><strong>${escapeHtml(item)}</strong><span>${escapeHtml(row)}${escapeHtml(location)}</span></div></div>`;
    }).join("")}${shopSales.length > 80 ? `<small class="entity-endpoint-more">其余 ${shopSales.length - 80} 条库存记录保留在数据接口中。</small>` : ""}</div>`
    : "";
  const reinforcementHtml = reinforcement.length || outgoing.length
    ? `<div class="entity-detail-note">强化关系：作为材料被使用 ${reinforcement.length} 条；自身强化 ${outgoing.length} 条。</div>`
    : "";
  const graphNode = topology.graphNodes?.[0];
  const topologyMeta = graphNode
    ? `${graphNode.region || "未分区"}${graphNode.floor ? ` · ${graphNode.floor}` : ""}`
    : "暂无正式图节点";
  const routeActionHtml = routeAnchorNodes.length
    ? `<div class="entity-detail-route-actions">${routeAnchorNodes.map((node) => `<button type="button" class="entity-route-button" data-route-node-id="${escapeHtml(node.id)}">以“${escapeHtml(node.label || node.id)}”作为终点规划路线</button>`).join("")}</div>`
    : `<div class="entity-detail-route-note">获取终点尚未绑定正式导航锚点；这里不会把坐标或语义关系伪装成可规划路线。</div>`;
  els.entityDetail.innerHTML = `<div class="entity-detail-card">
    <div class="entity-detail-head"><div><h3>${escapeHtml(name)}</h3><span>${escapeHtml(entityKindLabel(entity))} · ${escapeHtml(entity.category || "")}</span></div><button type="button" class="entity-detail-close" aria-label="关闭">×</button></div>
    <div class="entity-detail-en">${escapeHtml(entity.name?.en || "")}</div>
    <div class="entity-detail-status"><strong>${escapeHtml(entityTopologyLabel(topology.status))}</strong><span>${escapeHtml(topologyMeta)}</span></div>
    ${routeActionHtml}
    <div class="entity-detail-section"><div class="entity-detail-section-title">获取方式 · ${acquisitions.length}条关系 · ${endpointCount}个已定位终点</div>${acquisitionHtml}</div>
    ${shopSalesHtml}
    ${reinforcementHtml}
    <div class="entity-detail-source">来源层：${escapeHtml(sources)}</div>
  </div>`;
  els.entityDetail.classList.remove("hidden");
  els.entityDetail.querySelector(".entity-detail-close")?.addEventListener("click", () => {
    els.entityDetail.classList.add("hidden");
  });
  els.entityDetail.querySelectorAll("[data-route-node-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const nodeId = button.dataset.routeNodeId;
      if (!state.store.node(nodeId)) return;
      state.destination = nodeId;
      state.selectedNode = nodeId;
      els.destinationSearch.value = nodeLabel(nodeId);
      els.destinationSearch.dataset.nodeId = nodeId;
      planAndRender();
    });
  });
}

async function loadEntityDetail(entityId) {
  try {
    const response = await fetch(`/api/catalog/player-entities?id=${encodeURIComponent(entityId)}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderEntityDetail(await response.json());
  } catch (error) {
    els.entityDetail.innerHTML = `<div class="entity-placeholder">实体详情加载失败：${escapeHtml(error.message)}</div>`;
    els.entityDetail.classList.remove("hidden");
  }
}

async function searchPlayerEntities(query) {
  const requestId = ++state.entitySearchRequest;
  if (!query.trim()) {
    els.entityResults.innerHTML = `<div class="entity-placeholder">输入名称开始查询。</div>`;
    els.entityDetail.classList.add("hidden");
    return;
  }
  els.entityResults.innerHTML = `<div class="entity-placeholder">查询中…</div>`;
  try {
    const response = await fetch(`/api/catalog/player-entities?q=${encodeURIComponent(query)}&limit=80`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    if (requestId !== state.entitySearchRequest) return;
    renderEntityResults(payload);
  } catch (error) {
    if (requestId !== state.entitySearchRequest) return;
    els.entityResults.innerHTML = `<div class="entity-placeholder">查询失败：${escapeHtml(error.message)}</div>`;
  }
}

function text(value) {
  return value == null ? "" : String(value);
}

/* ---------------- graph store helpers ---------------- */

function nodeLabel(id) {
  return nodeLabelZh(id);
}

function layerZh(layer) {
  const raw = layer || "";
  const entry = state.zhMap?.layers?.[raw]?.label;
  return entry && entry.level !== "already_zh" && entry.level !== "uncovered" ? entry.zh : raw;
}

function activeRouteProfile() {
  return state.routeProfiles?.profiles?.find((profile) => profile.id === state.routeProfile)
    || state.routeProfiles?.profiles?.[0]
    || { id: DEFAULT_ROUTE_PROFILE, dynamicFastTravel: false, description: "仅使用正式物理拓扑边。" };
}

function riskWeight() {
  if (state.preference === "fast") return 0.35;
  if (state.preference === "safe") return 5.5;
  return 2.0;
}

function routeOptions() {
  const profile = activeRouteProfile();
  return {
    dynamicFastTravel: Boolean(profile.dynamicFastTravel),
    fastTravelRuleId: state.routeProfiles?.fastTravelRule?.id,
    riskWeight: riskWeight(),
  };
}

function isGraceNode(node) {
  return Boolean(node) && (node.kind === "grace" || node.isGraceAnchor === true);
}

/* ---------------- conditions ---------------- */

function renderConditions() {
  els.conditions.innerHTML = "";
  const conditions = [...state.store.conditions.values()].sort((a, b) => a.label.localeCompare(b.label, "zh-CN"));
  if (!conditions.length) {
    els.conditions.innerHTML = `<div class="condition-empty">没有可用的世界状态条件。</div>`;
    return;
  }
  for (const condition of conditions) {
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
    copy.innerHTML = `<span class="condition-label">${escapeHtml(conditionLabelZh(condition.id))}</span><span class="condition-hint">${escapeHtml(conditionHintZh(condition.id))}</span>`;
    label.append(input, copy);
    els.conditions.appendChild(label);
  }
}

/* ---------------- route profiles ---------------- */

function renderRouteProfiles() {
  const profiles = state.routeProfiles?.profiles || [];
  els.routeProfile.innerHTML = "";
  for (const profile of profiles) {
    const option = document.createElement("option");
    option.value = profile.id;
    option.textContent = profile.label;
    els.routeProfile.appendChild(option);
  }
  state.routeProfile = state.routeProfiles?.defaultProfile || DEFAULT_ROUTE_PROFILE;
  els.routeProfile.value = state.routeProfile;
  els.routeProfileHint.textContent = activeRouteProfile().description;
}

/* ---------------- planning ---------------- */

function planAndRender() {
  if (!state.store.hasData()) return;
  if (!state.origin || !state.destination) {
    showEmptyRoute("请先选择起点与终点。");
    return;
  }
  const route = state.store.route(state.origin, state.destination, [...state.conditions], routeOptions());
  if (route) {
    state.route = route;
    renderRouteCard(route);
    renderGraph();
    return;
  }
  const blocked = state.store.explainBlocked(state.origin, state.destination, [...state.conditions], routeOptions());
  state.route = null;
  renderBlockedCard(blocked);
  renderGraph();
}

function showEmptyRoute(message) {
  state.route = null;
  els.routeContent.classList.add("hidden");
  els.routeSummary.classList.remove("empty");
  els.routeSummary.classList.add("empty");
  els.routeEmptyHint.textContent = message || "设定起点和终点后，规划器会按照当前世界状态计算可达路径。";
  renderGraph();
}

function renderRouteCard(route) {
  els.routeSummary.classList.add("hidden");
  els.routeContent.classList.remove("hidden");
  const originNode = state.store.node(route.nodes[0]);
  const destinationNode = state.store.node(route.nodes[route.nodes.length - 1]);
  els.routeTitle.textContent = `${nodeLabelZh(route.nodes[0])} → ${nodeLabelZh(route.nodes.at(-1))}`;
  els.routeTime.textContent = route.time;
  els.routeRisk.textContent = route.risk;
  els.routeHops.textContent = route.edges.length;

  let html = "";
  route.edges.forEach((edge, index) => {
    const fromNode = state.store.node(edge.from);
    const toNode = state.store.node(edge.to);
    const oneWay = edge.direction === "one_way" || edge.direction === "one_way_drop" || (edge.tags || []).includes("one_way");
    const directionLabel = oneWay ? "单向" : DIRECTION_LABELS[edge.direction] || "双向";
    const provLabel = oneWay
      ? edge.transitionType === "one_way_drop" ? "单向跳落" : directionLabel
      : `双向 · ${directionLabel}`;
    const layerChange = fromNode?.layer !== toNode?.layer
      ? ` · ${fromNode?.layer || "?"} → ${toNode?.layer || "?"}`
      : "";
    const requires = (edge.requires || [])
      .map((id) => conditionLabelZh(id))
      .filter(Boolean);
    const requiresText = requires.length ? `要求：${requires.join("；")}` : "无条件";
    const packageMeta = edge.packageId === "dynamic"
      ? { id: "dynamic", version: "规划层" }
      : state.store.packages.get(edge.packageId) || {};
    const evidence = edge.verificationState || "未声明";
    html += `<div class="route-step">
      <div class="route-step-index">${index + 1}</div>
      <div class="route-step-body">
        <div class="route-step-title">${escapeHtml(nodeLabelZh(edge.from))} <span class="route-step-arrow">→</span> ${escapeHtml(nodeLabelZh(edge.to))}</div>
        <div class="route-step-meta">${escapeHtml(modeZh(edge))}${layerChange}</div>
        <div class="route-step-detail">${escapeHtml(requiresText)}</div>
        <div class="route-step-provenance">
          <span class="prov-chip ${oneWay ? "prov-oneway" : ""}">${escapeHtml(provLabel)}</span>
          <span class="prov-chip">包 ${escapeHtml(packageMeta.id || "?")}@${escapeHtml(packageMeta.version || "?")}</span>
          <span class="prov-chip">证据 ${escapeHtml(evidence)}</span>
        </div>
      </div>
    </div>`;
  });
  els.pathTrack.innerHTML = html;
  const noticeParts = [];
  noticeParts.push(`路线使用 ${route.edges.length} 条有向边，按当前勾选的世界状态计算。`);
  const dynamicCount = route.edges.filter((edge) => edge.packageId === "dynamic").length;
  if (dynamicCount) noticeParts.push(`其中 ${dynamicCount} 段为地图快速旅行（需已发现目标赐福）。`);
  els.routeNotice.textContent = noticeParts.join(" ");
}

function renderBlockedCard(blocked) {
  els.routeSummary.classList.add("hidden");
  els.routeContent.classList.remove("hidden");
  els.routeTitle.textContent = `${nodeLabel(state.origin)} → ${nodeLabel(state.destination)}`;
  els.routeTime.textContent = "—";
  els.routeRisk.textContent = "—";
  els.routeHops.textContent = "—";
  els.pathTrack.innerHTML = `<div class="blocked-card">
    <div class="blocked-title">「${escapeHtml(nodeLabelZh(state.origin))}」到「${escapeHtml(nodeLabelZh(state.destination))}」当前无法规划路线。</div>
    ${blocked.missingConditions?.length ? `
      <div class="blocked-conditions-title">满足以下条件后可达：</div>
      <div class="blocked-conditions">${blocked.missingConditions.map((condition) => `
        <div class="blocked-condition">
          <div class="blocked-condition-label">${escapeHtml(conditionLabelZh(condition.id))}</div>
          <div class="blocked-condition-hint">${escapeHtml(conditionHintZh(condition.id))}</div>
        </div>`).join("")}
      </div>
      <div class="blocked-tip">勾选以上条件后重新规划；未列出的其他区域条件与这条路线无关。</div>` : ""}
    ${blocked.category === "cross-component" ? `<div class="blocked-tip">${escapeHtml(blocked.message || "")}</div>` : ""}
  </div>`;
  els.routeNotice.textContent = "本次查询在满足上述条件前不可达；这是数据状态，不是系统错误。";
}

/* ---------------- map rendering ---------------- */

function visibleNode(node) {
  return state.layer === "all" || node.layer === state.layer || Boolean(state.route?.nodes.includes(node.id));
}

function edgeAvailable(edge) {
  if (edge.routeable === false) return false;
  if (edge.conditionUnknown?.length) return false;
  return (edge.requires || []).every((id) => state.conditions.has(id));
}

/* Focus mode: with a planned route, the focus set is the route plus its
 * one-hop neighbourhood; without a route but with a chosen origin, the focus
 * is the unconditionally reachable set. Everything else recedes (dim). */
function focusNodeIds() {
  if (state.route) {
    const focus = new Set(state.route.nodes);
    for (const edge of state.store.activeEdgeList()) {
      if (focus.has(edge.from)) focus.add(edge.to);
      if (focus.has(edge.to)) focus.add(edge.from);
    }
    return focus;
  }
  if (state.origin && state.store.hasData()) {
    const focus = new Set([state.origin]);
    const queue = [state.origin];
    while (queue.length) {
      const current = queue.pop();
      for (const edge of state.store.activeEdgeList()) {
        if (edge.from === current && edgeAvailable(edge) && !focus.has(edge.to)) {
          focus.add(edge.to);
          queue.push(edge.to);
        }
      }
    }
    return focus;
  }
  return null;
}

function renderRegions() {
  els.regionLabels.innerHTML = "";
  const groups = new Map();
  for (const node of state.store.activeNodeList()) {
    const region = regionZh(node.id) || node.region || "";
    if (!groups.has(region)) groups.set(region, []);
    groups.get(region).push(node);
  }
  [...groups.entries()].forEach(([region, nodes], index) => {
    const x = Math.min(...nodes.map((node) => node.x)) - 16;
    const y = Math.max(28, Math.min(...nodes.map((node) => node.y)) - 35 - (index % 2) * 10);
    const label = svg("text", { x, y, class: "region-label" });
    label.textContent = region;
    const rule = svg("line", { x1: x, y1: y + 7, x2: x + 58, y2: y + 7, class: "region-rule" });
    els.regionLabels.append(rule, label);
  });
}

function renderEdges() {
  els.edgeLayer.innerHTML = "";
  const routeEdgeIds = new Set(state.route?.edges.map((edge) => edge.id) || []);
  const focus = focusNodeIds();
  for (const edge of state.store.activeEdgeList()) {
    const from = state.store.node(edge.from);
    const to = state.store.node(edge.to);
    if (!from || !to) continue;
    if (!visibleNode(from) || !visibleNode(to)) continue;
    const available = edgeAvailable(edge);
    const isRoute = routeEdgeIds.has(edge.id);
    const unknown = Boolean(edge.conditionUnknown?.length);
    const isLocalDeclared = (edge.tags || []).includes("local_declared") || (edge.tags || []).includes("known_connection");
    const isCatalogGrace = (edge.tags || []).includes("catalog_grace");
    const dimEdge = Boolean(focus) && !focus.has(edge.from) && !focus.has(edge.to) && !isRoute;
    const classes = [
      "edge",
      available ? "available" : "blocked",
      (edge.requires || []).length ? "conditional" : "",
      unknown ? "unknown" : "",
      isRoute ? "route" : "",
      isLocalDeclared ? "local-declared" : "",
      isCatalogGrace ? "catalog-grace" : "",
      dimEdge ? "dim-edge" : "",
    ];
    const line = svg("line", {
      x1: from.x,
      y1: from.y,
      x2: to.x,
      y2: to.y,
      class: classes.join(" "),
      "data-edge-id": edge.id,
    });
    line.addEventListener("mouseenter", () => {
      els.mapToast.textContent = `${nodeLabelZh(edge.from)} → ${nodeLabelZh(edge.to)} · ${modeZh(edge)}${unknown ? " · 条件未知" : available ? "" : " · 条件未满足"}`;
    });
    line.addEventListener("mouseleave", () => { els.mapToast.textContent = "点击节点查看详情"; });
    els.edgeLayer.appendChild(line);
    if ((edge.requires || []).length || isRoute) {
      const labelX = (from.x + to.x) / 2;
      const labelY = (from.y + to.y) / 2 - 5;
      const label = svg("text", { x: labelX, y: labelY, class: `edge-label ${isRoute ? "route-label" : ""}` });
      label.textContent = available ? modeZh(edge) : unknown ? `未知 · ${modeZh(edge)}` : `锁定 · ${modeZh(edge)}`;
      els.edgeLayer.appendChild(label);
    }
  }
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
  /* renderGraph, not renderNodes: in region-detail view, renderNodes would
   * repaint every node globally and yank the user out of the region. */
  renderGraph();
  renderInspector();
}

function renderNodes() {
  els.nodeLayer.innerHTML = "";
  const routeNodeIds = new Set(state.route?.nodes || []);
  for (const node of state.store.activeNodeList()) {
    if (!visibleNode(node)) continue;
    const group = svg("g", {
      class: `node-group kind-${node.kind} ${state.selectedNode === node.id ? "selected" : ""} ${routeNodeIds.has(node.id) ? "route-node" : ""} ${node.id === state.origin ? "origin" : ""} ${node.id === state.destination ? "destination" : ""}`,
      transform: `translate(${node.x} ${node.y})`,
    });
    const focus = focusNodeIds();
    const dimNode = Boolean(focus) && !focus.has(node.id) && !routeNodeIds.has(node.id);
    if (dimNode) group.classList.add("dim-hard");
    else if (state.route && !routeNodeIds.has(node.id) && state.layer === "all") group.classList.add("dim");
    const hit = svg("circle", { r: 14, class: "node-hit" });
    const ring = svg("circle", { r: node.kind === "target" ? 9 : 7, class: "node-ring" });
    const core = svg("circle", { r: node.kind === "target" ? 4 : 3, class: "node-core", fill: nodeCoreColor(node.kind) });
    const label = svg("text", { x: 12, y: 4, class: "node-label" });
    label.textContent = nodeLabelZh(node.id);
    const region = svg("text", { x: 12, y: 15, class: "node-region" });
    region.textContent = `${layerZh(node.layer).toUpperCase()} · ${regionZh(node.id)}`;
    group.append(hit, ring, core, label, region);
    if (node.id === state.origin || node.id === state.destination) {
      const marker = svg("text", { x: -4, y: -13, class: "node-status" });
      marker.textContent = node.id === state.origin ? "FROM" : "TO";
      group.appendChild(marker);
    }
    group.addEventListener("click", () => selectNode(node.id));
    group.addEventListener("mouseenter", () => { els.mapToast.textContent = `${nodeLabelZh(node.id)} · ${regionZh(node.id)}`; });
    group.addEventListener("mouseleave", () => { els.mapToast.textContent = "点击节点查看详情"; });
    els.nodeLayer.appendChild(group);
  }
}

function renderInspector() {
  const node = state.store.node(state.selectedNode);
  if (!node) {
    els.nodeInspector.innerHTML = `<div class="inspector-placeholder">选择地图上的节点<br />查看它的层级、类型和可用连接。</div>`;
    return;
  }
  const outgoing = state.store.activeEdgeList().filter((edge) => edge.from === node.id);
  const incoming = state.store.activeEdgeList().filter((edge) => edge.to === node.id);
  const outgoingHtml = outgoing.length ? outgoing.map((edge) => {
    const available = edgeAvailable(edge);
    return `<div class="inspector-edge ${available ? "" : "inspector-edge-blocked"}">
      <span>→ ${escapeHtml(nodeLabelZh(edge.to))}</span>
      <span class="inspector-edge-mode">${escapeHtml(modeZh(edge))}${available ? "" : " · 锁定"}</span>
    </div>`;
  }).join("") : `<div class="inspector-edge">（无可通行出边）</div>`;
  const incomingHtml = incoming.length ? incoming.map((edge) => {
    return `<div class="inspector-edge"><span>← ${escapeHtml(nodeLabelZh(edge.from))}</span><span class="inspector-edge-mode">${escapeHtml(modeZh(edge))}</span></div>`;
  }).join("") : "";
  els.nodeInspector.innerHTML = `<div class="inspector-card">
    <div class="inspector-head">
      <div>
        <div class="inspector-title">${escapeHtml(nodeLabelZh(node.id))}</div>
        <div class="inspector-type">${escapeHtml(KIND_LABELS[node.kind] || node.kind)} · ${escapeHtml(layerZh(node.layer))} · 包 ${escapeHtml(node.packageId || "?")}</div>
      </div>
      <div class="inspector-region">${escapeHtml(regionZh(node.id))}${floorZh(node.id) ? ` · ${escapeHtml(floorZh(node.id))}` : ""}</div>
    </div>
    <p class="inspector-description">${escapeHtml(descriptionZh(node.id))}</p>
    <div class="inspector-section-title">出边（${outgoing.length}）</div>
    ${outgoingHtml}
    ${incomingHtml ? `<div class="inspector-section-title">入边（${incoming.length}）</div>${incomingHtml}` : ""}
  </div>`;
}

/* ---------------- region overview (方案六) ---------------- */

/* Group key: the displayed (official-Chinese) region name, so synonym regions
 * like 王城罗德尔 / Leyndell, Royal Capital merge into one aggregate node. */
function regionKey(node) {
  return regionZh(node.id) || node.region || "?";
}

function buildRegionGroups() {
  const groups = new Map();
  for (const node of state.store.activeNodeList()) {
    const key = regionKey(node);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(node);
  }
  return groups;
}

function regionRadius(nodeCount) {
  return 30 + Math.min(nodeCount, 120) * 0.5;
}

/* Half-width of a region's name label in local (region-node) units. The label
 * is drawn at 15px and, crucially, sits in the same local coordinate space as
 * the circle (the group carries only a translate; the spaceScale is applied
 * uniformly to both in the parent transform). A Chinese name can be wider than
 * a small circle's diameter, so repulsion must account for it or labels stack. */
function regionLabelSpan(key) {
  return ([...key].length * 15) / 2;
}

/* Force-directed anti-overlap layout for the aggregate region nodes: starts
 * from each region's centroid, then repels overlapping pairs until stable.
 * The circle radius drives the drawn node, but repulsion uses the wider of the
 * circle radius and the label half-width so text never stacks on text.
 * Result is cached per group signature (deterministic, ~100ms for 122). */
function computeRegionLayout(groups) {
  const keys = [...groups.keys()];
  const pos = new Map();
  const radius = new Map();
  const collision = new Map();
  for (const key of keys) {
    const nodes = groups.get(key);
    pos.set(key, {
      x: nodes.reduce((sum, node) => sum + node.x, 0) / nodes.length,
      y: nodes.reduce((sum, node) => sum + node.y, 0) / nodes.length,
    });
    radius.set(key, regionRadius(nodes.length));
    collision.set(key, Math.max(radius.get(key), regionLabelSpan(key)));
  }
  for (let iteration = 0; iteration < 90; iteration += 1) {
    let moved = 0;
    for (let i = 0; i < keys.length; i += 1) {
      for (let j = i + 1; j < keys.length; j += 1) {
        const a = pos.get(keys[i]);
        const b = pos.get(keys[j]);
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let dist = Math.hypot(dx, dy);
        const minDist = collision.get(keys[i]) + collision.get(keys[j]) + 12;
        if (dist >= minDist) continue;
        if (dist === 0) {
          dx = 1;
          dy = 0.3;
          dist = Math.hypot(dx, dy);
        }
        const push = (minDist - dist) / 2;
        const ux = dx / dist;
        const uy = dy / dist;
        a.x -= ux * push;
        a.y -= uy * push;
        b.x += ux * push;
        b.y += uy * push;
        moved += 1;
      }
    }
    for (const key of keys) {
      pos.get(key).x = Math.max(50, Math.min(COORDINATE_SPACE.width - 50, pos.get(key).x));
      pos.get(key).y = Math.max(50, Math.min(COORDINATE_SPACE.height - 50, pos.get(key).y));
    }
    if (moved === 0) break;
  }
  return { pos, radius };
}

function renderRegionOverview() {
  els.regionLabels.innerHTML = "";
  els.edgeLayer.innerHTML = "";
  els.nodeLayer.innerHTML = "";
  const groups = buildRegionGroups();
  const signature = [...groups.keys()].sort().join("|") + ":" + [...groups.values()].map((nodes) => nodes.length).join(",");
  if (!state.regionLayoutCache || state.regionLayoutCache.signature !== signature) {
    state.regionLayoutCache = { signature, ...computeRegionLayout(groups) };
  }
  const { pos, radius } = state.regionLayoutCache;
  const meta = new Map();
  for (const [key, nodes] of groups) {
    const position = pos.get(key);
    meta.set(key, {
      cx: position.x,
      cy: position.y,
      radius: radius.get(key),
      nodes: nodes.length,
      graces: nodes.filter((node) => node.kind === "grace").length,
    });
  }

  /* aggregate inter-region edges: one dashed link per region pair */
  const drawnPairs = new Set();
  for (const edge of state.store.activeEdgeList()) {
    const from = state.store.node(edge.from);
    const to = state.store.node(edge.to);
    if (!from || !to) continue;
    const fromKey = regionKey(from);
    const toKey = regionKey(to);
    if (fromKey === toKey) continue;
    const a = meta.get(fromKey);
    const b = meta.get(toKey);
    if (!a || !b) continue;
    const pair = fromKey < toKey ? `${fromKey}|${toKey}` : `${toKey}|${fromKey}`;
    if (drawnPairs.has(pair)) continue;
    drawnPairs.add(pair);
    const line = svg("line", { x1: a.cx, y1: a.cy, x2: b.cx, y2: b.cy, class: "region-edge" });
    els.edgeLayer.appendChild(line);
  }

  for (const [key, regionMeta] of meta) {
    const group = svg("g", {
      class: "region-node",
      transform: `translate(${regionMeta.cx} ${regionMeta.cy})`,
    });
    const circle = svg("circle", { r: regionMeta.radius, class: "region-node-core" });
    /* transparent hit circle extends the clickable area beyond the visual ring */
    const hit = svg("circle", { r: regionMeta.radius + 16, class: "region-node-hit" });
    const label = svg("text", { y: -regionMeta.radius - 9, class: "region-node-label" });
    label.textContent = key;
    const sub = svg("text", { y: 5, class: "region-node-sub" });
    sub.textContent = `${regionMeta.nodes} 节点 · ${regionMeta.graces} 赐福`;
    group.append(hit, circle, label, sub);
    group.addEventListener("click", () => {
      state.mapView = "detail";
      state.detailRegion = key;
      state.selectedNode = null;
      fitCameraToRegion(key);
      els.mapBack.hidden = false;
      renderGraph();
    });
    group.addEventListener("mouseenter", () => {
      els.mapToast.textContent = `${key} · ${regionMeta.nodes} 节点 · ${regionMeta.graces} 赐福（点击进入）`;
    });
    group.addEventListener("mouseleave", () => { els.mapToast.textContent = "点击区域查看内部拓扑"; });
    els.nodeLayer.appendChild(group);
  }
  els.graphStats.textContent = `${groups.size} 个区域 · ${state.store.nodes.size} 节点 · ${state.store.edges.size} 条边（点击区域下钻）`;
}

/* ---- node label layout (collision avoidance + leader lines) ---- */

let labelMeasureCtx = null;
function measureTextWidth(text, fontSize) {
  if (!labelMeasureCtx) {
    labelMeasureCtx = document.createElement("canvas").getContext("2d");
  }
  labelMeasureCtx.font = `${fontSize}px "Segoe UI", "Microsoft YaHei", sans-serif`;
  return labelMeasureCtx.measureText(text).width;
}

function labelRectCollides(rect, placed, nodeObstacles, selfId) {
  for (const p of placed) {
    if (rect.x < p.x + p.w && rect.x + rect.w > p.x && rect.y < p.y + p.h && rect.y + rect.h > p.y) return true;
  }
  for (const [id, o] of nodeObstacles) {
    if (id === selfId) continue;
    const nx = Math.max(rect.x, Math.min(o.x, rect.x + rect.w));
    const ny = Math.max(rect.y, Math.min(o.y, rect.y + rect.h));
    const dx = o.x - nx;
    const dy = o.y - ny;
    if (dx * dx + dy * dy < o.r * o.r) return true;
  }
  return false;
}

/* Greedy anti-overlap label placement for a region's member nodes. Nodes stay
 * at their fixed geographic positions (moving them would distort the map), so
 * only the labels move: each label tries right / left / below / above the node
 * in that order and takes the first spot that neither overlaps a previously
 * placed label nor sits on another node. A leader line ties a label back to
 * its node when it lands anywhere but the default (right) slot. */
function layoutNodeLabels(nodes) {
  const FONT = 10;          // matches .node-label font-size
  const GAP = 7;            // gap between node ring and label edge
  const NODE_R = 15;        // obstacle radius (ring + margin)
  const ordered = [...nodes].sort((a, b) => a.y - b.y || a.x - b.x);
  const nodeObstacles = new Map();
  for (const n of nodes) nodeObstacles.set(n.id, { x: n.x, y: n.y, r: NODE_R });
  const placed = [];
  const placements = new Map();
  for (const n of ordered) {
    const w = measureTextWidth(n.label, FONT);
    const h = FONT;
    /* Multiple standoff distances per direction: labels hug the node first,
     * and when the local cluster is too dense (real geographic coordinates can
     * put several nodes within a few tens of units) they step outward until a
     * slot clears, tied back by a leader line. */
    const standoffs = [GAP, GAP + 14, GAP + 28];
    const candidates = [];
    for (const s of standoffs) {
      candidates.push(
        { tx: n.x + s + 5, ty: n.y + FONT * 0.8, anchor: "start",  side: "right",        rect: { x: n.x + s + 5, y: n.y - h / 2, w, h } },
        { tx: n.x - s - 5, ty: n.y + FONT * 0.8, anchor: "end",    side: "left",         rect: { x: n.x - s - 5 - w, y: n.y - h / 2, w, h } },
        { tx: n.x, ty: n.y + s + FONT, anchor: "middle",           side: "below",        rect: { x: n.x - w / 2, y: n.y + s, w, h } },
        { tx: n.x, ty: n.y - s, anchor: "middle",                  side: "above",        rect: { x: n.x - w / 2, y: n.y - s - h, w, h } },
        { tx: n.x + s, ty: n.y - s, anchor: "start",               side: "top-right",    rect: { x: n.x + s, y: n.y - s - h, w, h } },
        { tx: n.x - s, ty: n.y - s, anchor: "end",                 side: "top-left",     rect: { x: n.x - s - w, y: n.y - s - h, w, h } },
        { tx: n.x + s, ty: n.y + s + FONT, anchor: "start",        side: "bottom-right", rect: { x: n.x + s, y: n.y + s, w, h } },
        { tx: n.x - s, ty: n.y + s + FONT, anchor: "end",          side: "bottom-left",  rect: { x: n.x - s - w, y: n.y + s, w, h } },
      );
    }
    let chosen = candidates[0];
    for (const cand of candidates) {
      if (labelRectCollides(cand.rect, placed, nodeObstacles, n.id)) continue;
      chosen = cand;
      break;
    }
    placements.set(n.id, { tx: chosen.tx, ty: chosen.ty, anchor: chosen.anchor, side: chosen.side, rect: chosen.rect });
    placed.push({ x: chosen.rect.x, y: chosen.rect.y, w, h });
  }
  return placements;
}

/* Point on the label rect edge closest to the node centre, in absolute
 * coordinate-space units — used to draw the leader line from the node ring to
 * a relocated label. */
function leaderEndPoint(nodeX, nodeY, placement) {
  const r = placement.rect;
  const px = Math.max(r.x, Math.min(nodeX, r.x + r.w));
  const py = Math.max(r.y, Math.min(nodeY, r.y + r.h));
  return { x: px, y: py };
}

function renderRegionDetail() {
  const region = state.detailRegion;
  const memberIds = new Set();
  for (const node of state.store.activeNodeList()) {
    if (regionKey(node) === region) memberIds.add(node.id);
  }

  els.regionLabels.innerHTML = "";
  els.edgeLayer.innerHTML = "";
  els.nodeLayer.innerHTML = "";

  const routeEdgeIds = new Set(state.route?.edges.map((edge) => edge.id) || []);
  /* Region detail shows the full intra-region topology; the global focus dim
   * (which fades + disables nodes outside the current route/origin reach) must
   * not apply here or most nodes render ghosted and un-tappable. */
  const focus = null;
  let internalEdges = 0;
  let externalEdges = 0;
  for (const edge of state.store.activeEdgeList()) {
    const inFrom = memberIds.has(edge.from);
    const inTo = memberIds.has(edge.to);
    if (!inFrom && !inTo) continue;
    if (!inFrom || !inTo) {
      externalEdges += 1;
      continue;
    }
    internalEdges += 1;
    const from = state.store.node(edge.from);
    const to = state.store.node(edge.to);
    const available = edgeAvailable(edge);
    const isRoute = routeEdgeIds.has(edge.id);
    const unknown = Boolean(edge.conditionUnknown?.length);
    const isLocalDeclared = (edge.tags || []).includes("local_declared") || (edge.tags || []).includes("known_connection");
    const isCatalogGrace = (edge.tags || []).includes("catalog_grace");
    const dimEdge = Boolean(focus) && !focus.has(edge.from) && !focus.has(edge.to) && !isRoute;
    const classes = [
      "edge", available ? "available" : "blocked",
      (edge.requires || []).length ? "conditional" : "",
      unknown ? "unknown" : "",
      isRoute ? "route" : "",
      isLocalDeclared ? "local-declared" : "",
      isCatalogGrace ? "catalog-grace" : "",
      dimEdge ? "dim-edge" : "",
    ];
    const line = svg("line", {
      x1: from.x, y1: from.y, x2: to.x, y2: to.y,
      class: classes.join(" "),
      "data-edge-id": edge.id,
    });
    line.addEventListener("mouseenter", () => {
      els.mapToast.textContent = `${nodeLabelZh(edge.from)} → ${nodeLabelZh(edge.to)} · ${modeZh(edge)}`;
    });
    line.addEventListener("mouseleave", () => { els.mapToast.textContent = "点击节点查看详情"; });
    els.edgeLayer.appendChild(line);
  }

  const routeNodeIds = new Set(state.route?.nodes || []);
  const memberNodes = [];
  for (const node of state.store.activeNodeList()) {
    if (memberIds.has(node.id)) {
      memberNodes.push({ id: node.id, x: node.x, y: node.y, label: nodeLabelZh(node.id) });
    }
  }
  const labelLayout = layoutNodeLabels(memberNodes);

  for (const node of state.store.activeNodeList()) {
    if (!memberIds.has(node.id)) continue;
    const group = svg("g", {
      class: `node-group kind-${node.kind} ${state.selectedNode === node.id ? "selected" : ""} ${routeNodeIds.has(node.id) ? "route-node" : ""} ${node.id === state.origin ? "origin" : ""} ${node.id === state.destination ? "destination" : ""}`,
      transform: `translate(${node.x} ${node.y})`,
    });
    const dimNode = Boolean(focus) && !focus.has(node.id) && !routeNodeIds.has(node.id);
    if (dimNode) group.classList.add("dim-hard");
    const hit = svg("circle", { r: 14, class: "node-hit" });
    const ring = svg("circle", { r: node.kind === "target" ? 9 : 7, class: "node-ring" });
    const core = svg("circle", { r: node.kind === "target" ? 4 : 3, class: "node-core", fill: nodeCoreColor(node.kind) });

    const placement = labelLayout.get(node.id);
    const localX = placement.tx - node.x;
    const localY = placement.ty - node.y;
    const label = svg("text", { x: localX, y: localY, "text-anchor": placement.anchor, class: "node-label" });
    label.textContent = nodeLabelZh(node.id);
    const region = svg("text", { x: localX, y: localY + 11, "text-anchor": placement.anchor, class: "node-region" });
    region.textContent = `${layerZh(node.layer).toUpperCase()} · ${regionZh(node.id)}`;
    group.append(hit, ring, core);

    /* leader line ties a relocated (non-right) label back to its node */
    if (placement.side !== "right") {
      const end = leaderEndPoint(node.x, node.y, placement);
      const ringEdge = node.kind === "target" ? 9 : 7;
      const dx = end.x - node.x;
      const dy = end.y - node.y;
      const len = Math.hypot(dx, dy) || 1;
      const lead = svg("line", {
        x1: (dx / len) * ringEdge,
        y1: (dy / len) * ringEdge,
        x2: end.x - node.x,
        y2: end.y - node.y,
        class: "node-leader",
      });
      group.appendChild(lead);
    }

    group.append(label, region);
    if (node.id === state.origin || node.id === state.destination) {
      const marker = svg("text", { x: -4, y: -13, class: "node-status" });
      marker.textContent = node.id === state.origin ? "FROM" : "TO";
      group.appendChild(marker);
    }
    group.addEventListener("click", () => selectNode(node.id));
    group.addEventListener("mouseenter", () => { els.mapToast.textContent = `${nodeLabelZh(node.id)} · ${regionZh(node.id)}`; });
    group.addEventListener("mouseleave", () => { els.mapToast.textContent = "点击节点查看详情"; });
    els.nodeLayer.appendChild(group);
  }
  els.graphStats.textContent = `${region} · ${memberIds.size} 节点 · ${internalEdges} 内部边 · ${externalEdges} 条跨区边`;
}

function renderGraph() {
  if (state.mapView === "regions") {
    renderRegionOverview();
    return;
  }
  if (state.mapView === "detail") {
    renderRegionDetail();
    return;
  }
  renderRegions();
  renderEdges();
  renderNodes();
  const store = state.store;
  els.graphStats.textContent = store.hasData()
    ? `${store.nodes.size} 节点 · ${store.edges.size} 条已证实边 · ${store.connectedComponents().length} 个连通分量`
    : "当前没有已加载地图数据";
}

function svg(tag, attrs = {}) {
  const element = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, String(value)));
  return element;
}

const VIEWBOX_WIDTH = 1000;
const VIEWBOX_HEIGHT = 600;
const COORDINATE_SPACE = { width: 2500, height: 1100 };
const ZOOM_MIN = 0.3;
const ZOOM_MAX = 8;
const CAMERA_MIN_X = -1200;
const CAMERA_MAX_X = 2200;
const CAMERA_MIN_Y = -900;
const CAMERA_MAX_Y = 1500;

function clampCamera(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

/* Camera model: (camX, camY) is the viewport centre in the 1000x600 canvas
 * coordinates, zoom scales around it. The transform chain is
 *   translate(cx,cy) scale(zoom) translate(-camX,-camY) translate(0,oy) scale(ss)
 * so the world point under the cursor stays fixed while zooming (zoomAt) and
 * dragging moves the camera by the inverse of the pointer delta. */
function applyCamera() {
  const spaceScale = VIEWBOX_WIDTH / COORDINATE_SPACE.width;
  const spaceOffsetY = (VIEWBOX_HEIGHT - COORDINATE_SPACE.height * spaceScale) / 2;
  const centerX = VIEWBOX_WIDTH / 2;
  const centerY = VIEWBOX_HEIGHT / 2;
  const { x: camX, y: camY, zoom } = state.camera;
  els.mapTransform.setAttribute(
    "transform",
    `translate(${centerX} ${centerY}) scale(${zoom}) translate(${-camX} ${-camY}) translate(0 ${spaceOffsetY}) scale(${spaceScale})`
  );
  const zoomLevel = zoom < 0.9 ? "far" : zoom < 1.5 ? "mid" : "near";
  els.mapStage.dataset.zoomLevel = zoomLevel;
}

function resetCamera() {
  state.camera = { x: VIEWBOX_WIDTH / 2, y: VIEWBOX_HEIGHT / 2, zoom: 1 };
  applyCamera();
}

/* Fit the camera to a region's member nodes so the region fills the viewport.
 * Region-detail nodes keep their raw coordinate-space positions, so without
 * this the camera sits at the whole-map default and the region collapses into
 * a dense, unreadable, un-tappable cluster. */
function fitCameraToRegion(region) {
  const spaceScale = VIEWBOX_WIDTH / COORDINATE_SPACE.width;
  const spaceOffsetY = (VIEWBOX_HEIGHT - COORDINATE_SPACE.height * spaceScale) / 2;
  let minWx = Infinity;
  let minWy = Infinity;
  let maxWx = -Infinity;
  let maxWy = -Infinity;
  for (const node of state.store.activeNodeList()) {
    if (regionKey(node) !== region) continue;
    const wx = node.x * spaceScale;
    const wy = node.y * spaceScale + spaceOffsetY;
    if (wx < minWx) minWx = wx;
    if (wx > maxWx) maxWx = wx;
    if (wy < minWy) minWy = wy;
    if (wy > maxWy) maxWy = wy;
  }
  if (maxWx === -Infinity) {
    resetCamera();
    return;
  }
  const bboxW = Math.max(1, maxWx - minWx);
  const bboxH = Math.max(1, maxWy - minWy);
  const pad = 70;
  const zoom = Math.max(
    ZOOM_MIN,
    Math.min(ZOOM_MAX, Math.min((VIEWBOX_WIDTH - pad * 2) / bboxW, (VIEWBOX_HEIGHT - pad * 2) / bboxH))
  );
  state.camera = { x: (minWx + maxWx) / 2, y: (minWy + maxWy) / 2, zoom };
  applyCamera();
}

/* Convert a client-space point to viewBox coordinates (handles the SVG
 * preserveAspectRatio mapping exactly). */
function toSvgPoint(clientX, clientY) {
  const point = els.topologyMap.createSVGPoint();
  point.x = clientX;
  point.y = clientY;
  const ctm = els.topologyMap.getScreenCTM();
  if (!ctm) return { x: clientX, y: clientY };
  const mapped = point.matrixTransform(ctm.inverse());
  return { x: mapped.x, y: mapped.y };
}

/* Zoom keeping the world point under svgPoint fixed on screen. */
function zoomAt(svgPoint, factor) {
  const spaceScale = VIEWBOX_WIDTH / COORDINATE_SPACE.width;
  const spaceOffsetY = (VIEWBOX_HEIGHT - COORDINATE_SPACE.height * spaceScale) / 2;
  const centerX = VIEWBOX_WIDTH / 2;
  const centerY = VIEWBOX_HEIGHT / 2;
  const zoomNew = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, state.camera.zoom * factor));
  if (zoomNew === state.camera.zoom) return;
  /* world point under the cursor */
  const qx = (svgPoint.x - centerX) / state.camera.zoom + state.camera.x;
  const qy = (svgPoint.y - centerY) / state.camera.zoom + state.camera.y;
  const px = qx / spaceScale;
  const py = (qy - spaceOffsetY) / spaceScale;
  /* keep that world point under the cursor at the new zoom */
  state.camera.zoom = zoomNew;
  state.camera.x = clampCamera(spaceScale * px - (svgPoint.x - centerX) / zoomNew, CAMERA_MIN_X, CAMERA_MAX_X);
  state.camera.y = clampCamera(spaceScale * py + spaceOffsetY - (svgPoint.y - centerY) / zoomNew, CAMERA_MIN_Y, CAMERA_MAX_Y);
  applyCamera();
}

/* Pan so the world point under fromSvg ends up under toSvg. The pointer delta
 * is in viewBox (screen) space, but the camera coordinate lives in the
 * pre-scale space, so the delta must be divided by zoom before it is applied
 * — otherwise pan speed decouples from the zoom factor. */
function panCameraBySvgDelta(camStart, fromSvg, toSvg, zoom) {
  return {
    x: clampCamera(camStart.x + (fromSvg.x - toSvg.x) / zoom, CAMERA_MIN_X, CAMERA_MAX_X),
    y: clampCamera(camStart.y + (fromSvg.y - toSvg.y) / zoom, CAMERA_MIN_Y, CAMERA_MAX_Y),
  };
}

/* ---------------- coverage panel ---------------- */

function renderCoverage() {
  const diagnostics = state.store.diagnostics();
  const packages = diagnostics.packages;
  const loaded = packages.filter((p) => p.status === "loaded");
  const failed = packages.filter((p) => p.status === "failed");
  const pending = packages.filter((p) => p.status === "pending");
  els.packageStatusChip.textContent = diagnostics.hasData
    ? `${loaded.length}/${packages.length} 数据包已加载`
    : "零数据状态";
  els.datasetVersion.textContent = `v${diagnostics.manifestVersion || "?"} · ${diagnostics.hasData ? "Beta 数据包" : "无数据"}`;

  const statement = diagnostics.coverage?.statement || "Beta 仅以已加载数据包的范围提供路线。";
  els.coverageNote.textContent = statement;
  els.footerCoverage.textContent = statement;
  els.engineStatus.textContent = diagnostics.hasData ? "GRAPH ENGINE READY" : "NO DATA LOADED";

  let html = `<div class="coverage-statement">${escapeHtml(statement)}</div>`;
  html += `<div class="coverage-table">
    <div class="coverage-row coverage-row-head">
      <span>数据包</span><span>状态</span><span>节点</span><span>边</span><span>隔离</span>
    </div>`;
  for (const pkg of packages) {
    const statusLabel = pkg.status === "loaded" ? "已加载" : pkg.status === "failed" ? "失败" : "未加载";
    const statusClass = pkg.status === "loaded" ? "status-ok" : pkg.status === "failed" ? "status-fail" : "status-pending";
    html += `<div class="coverage-row">
      <span title="${escapeHtml(pkg.title)}">${escapeHtml(pkg.id)}</span>
      <span class="${statusClass}">${statusLabel}</span>
      <span>${pkg.nodeCount}</span><span>${pkg.edgeCount}</span><span>${pkg.quarantinedCount}</span>
    </div>`;
  }
  html += `</div>`;

  if (diagnostics.quarantineTotal) {
    html += `<details class="coverage-details"><summary>隔离记录（${diagnostics.quarantineTotal}）</summary>`;
    for (const [packageId, items] of Object.entries(diagnostics.quarantineByPackage)) {
      html += `<div class="quarantine-package">${escapeHtml(packageId)}</div>`;
      for (const item of items) {
        const id = item.record?.id || item.line || "";
        html += `<div class="quarantine-item">${escapeHtml(item.kind)}${id ? ` ${escapeHtml(String(id))}` : ""} — ${escapeHtml(item.reason)}</div>`;
      }
    }
    html += `</details>`;
  }

  html += `<div class="coverage-components">连通分量 ${diagnostics.components.length} 个：`;
  html += diagnostics.components.slice(0, 8).map((component) =>
    `${escapeHtml(component.id)}（${component.nodeCount} 节点 · ${component.graceCount} 赐福）`
  ).join("，");
  if (diagnostics.components.length > 8) html += `…`;
  html += `</div>`;

  if (failed.length) {
    html += `<div class="coverage-warning">以下数据包未能加载（不影响其他区域）：${failed.map((p) => escapeHtml(p.id)).join("、")}</div>`;
  }
  els.coveragePanel.innerHTML = html;
}

/* ---------------- zero data ---------------- */

function showZeroData(reason) {
  state.loaded = false;
  els.loadingState.classList.add("hidden");
  els.datasetVersion.textContent = "v? · 零数据";
  els.packageStatusChip.textContent = "零数据状态";
  els.coverageNote.textContent = reason || "当前没有已加载地图数据。";
  els.footerCoverage.textContent = "当前没有已加载地图数据；请确认 data/v1/packages 已构建且服务端可访问。";
  els.engineStatus.textContent = "NO DATA LOADED";
  els.routeEmptyHint.textContent = "当前没有已加载地图数据，无法规划路线。";
  renderCoverage();
  renderGraph();
}

/* ---------------- boot ---------------- */

async function loadPackages() {
  const manifestResponse = await fetch("/api/packages/manifest", { cache: "no-store" });
  if (!manifestResponse.ok) {
    throw new Error(`数据包清单不可用（HTTP ${manifestResponse.status}）`);
  }
  const manifestPayload = await manifestResponse.json();
  const manifestResult = state.store.loadManifest(manifestPayload);
  if (!manifestResult.ok) {
    throw new Error(`数据包清单不受支持：${state.store.manifestError}`);
  }

  const profilesResponse = await fetch("/api/route-profiles", { cache: "no-store" });
  if (profilesResponse.ok) {
    state.routeProfiles = await profilesResponse.json();
    if (state.routeProfiles?.fastTravelRule) {
      state.store.registerCondition(state.routeProfiles.fastTravelRule);
    }
  }

  let loadedAny = false;
  for (const entry of manifestPayload.packages || []) {
    try {
      const response = await fetch(`/api/packages/${encodeURIComponent(entry.id)}`, { cache: "no-store" });
      if (!response.ok) {
        state.store.markPackageFailed(entry.id, `HTTP ${response.status}`);
        continue;
      }
      const rawText = await response.text();
      const result = state.store.loadPackage({ schema: "elden-ring-package@1", package: { id: entry.id }, rawText });
      if (!result.ok) {
        state.store.markPackageFailed(entry.id, result.error || "package load failed");
        continue;
      }
      if (result.validNodes > 0) loadedAny = true;
    } catch (error) {
      state.store.markPackageFailed(entry.id, `fetch failed: ${error.message}`);
    }
  }
  state.store.finalizeDanglingEdges();

  if (!loadedAny) {
    throw new Error("没有任何数据包成功加载；页面保持可用，但无法规划路线。");
  }
  return manifestPayload;
}

async function loadZhMapping() {
  /* Official Chinese display mapping; failure only degrades to English, it
   * never blocks the route planner. */
  try {
    const response = await fetch("/data/v1/zh-cn/official-zh-mapping.json", { cache: "no-store" });
    if (!response.ok) return null;
    const payload = await response.json();
    if (payload?.schema !== "elden-ring-official-zh-mapping@2") return null;
    return payload;
  } catch {
    return null;
  }
}

async function init() {
  wireEvents();
  /* collapsible settings/coverage: auto-expanded on desktop, collapsed on mobile */
  const advancedDetails = document.querySelectorAll(".advanced-settings");
  const syncDetailState = () => {
    const desktop = window.innerWidth >= 901;
    advancedDetails.forEach((details) => { details.open = desktop; });
  };
  syncDetailState();
  window.addEventListener("resize", syncDetailState);
  try {
    const manifestPayload = await loadPackages();
    state.loaded = true;
    els.loadingState.classList.add("hidden");
    state.store.registerAliases(SEARCH_ALIASES);
    state.zhMap = await loadZhMapping();
    if (state.zhMap) registerZhSearchAliases();

    const defaults = state.store.defaults;
    state.origin = defaults.origin || state.store.activeNodeList()[0]?.id;
    state.destination = defaults.destination || state.store.activeNodeList().at(-1)?.id;
    state.conditions = new Set(defaults.conditions || []);

    renderRouteProfiles();
    renderConditions();
    applyMapCoordinateSpace();
    renderCoverage();

    els.originSearch.value = nodeLabel(state.origin);
    els.originSearch.dataset.nodeId = state.origin;
    els.destinationSearch.value = nodeLabel(state.destination);
    els.destinationSearch.dataset.nodeId = state.destination;

    if (manifestPayload.packages) {
      els.loadingState.textContent = "";
    }
    planAndRender();
  } catch (error) {
    console.warn("Elden Ring Reachability Map init:", error);
    showZeroData(error.message);
  }
}

function applyMapCoordinateSpace() {
  els.topologyMap.setAttribute("viewBox", `0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`);
  resetCamera();
}

/* ---------------- events ---------------- */

function wireEvents() {
  /* ---- camera interactions: wheel zoom at cursor, left-drag pan, touch ---- */
  let panState = null;
  let suppressNextClick = false;
  let isTouching = false;

  els.mapStage.addEventListener("wheel", (event) => {
    event.preventDefault();
    const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15;
    zoomAt(toSvgPoint(event.clientX, event.clientY), factor);
  }, { passive: false });

  els.mapStage.addEventListener("mousedown", (event) => {
    if (event.button !== 0) return;
    if (isTouching) return; /* synthesized mouse events are handled by touch code */
    panState = {
      startSvg: toSvgPoint(event.clientX, event.clientY),
      camStart: { x: state.camera.x, y: state.camera.y, zoom: state.camera.zoom },
      moved: false,
    };
    els.mapStage.classList.add("panning");
  });

  window.addEventListener("mousemove", (event) => {
    if (!panState || isTouching) return;
    const current = toSvgPoint(event.clientX, event.clientY);
    const deltaX = current.x - panState.startSvg.x;
    const deltaY = current.y - panState.startSvg.y;
    if (Math.hypot(deltaX, deltaY) > 3) panState.moved = true;
    /* dragging the pointer by d moves the camera by -d / zoom */
    const next = panCameraBySvgDelta(panState.camStart, panState.startSvg, current, panState.camStart.zoom);
    state.camera.x = next.x;
    state.camera.y = next.y;
    applyCamera();
  });

  window.addEventListener("mouseup", () => {
    if (!panState || isTouching) return;
    if (panState.moved) {
      suppressNextClick = true;
      setTimeout(() => { suppressNextClick = false; }, 0);
    }
    panState = null;
    els.mapStage.classList.remove("panning");
  });

  /* ---- touch: single-finger pan, two-finger pinch zoom (camera model) ---- */
  const activeTouches = new Map();
  let pinchState = null;
  let touchPanState = null;

  els.mapStage.addEventListener("touchstart", (event) => {
    isTouching = true;
    for (const touch of event.changedTouches) {
      activeTouches.set(touch.identifier, { x: touch.clientX, y: touch.clientY });
    }
    if (activeTouches.size === 2) {
      const [a, b] = [...activeTouches.values()];
      const midX = (a.x + b.x) / 2;
      const midY = (a.y + b.y) / 2;
      pinchState = {
        startDist: Math.hypot(b.x - a.x, b.y - a.y),
        startZoom: state.camera.zoom,
        startCam: { x: state.camera.x, y: state.camera.y },
        startMidSvg: toSvgPoint(midX, midY),
      };
      touchPanState = null;
      els.mapStage.classList.add("panning");
    } else if (activeTouches.size === 1) {
      const [touch] = [...activeTouches.values()];
      touchPanState = {
        startSvg: toSvgPoint(touch.x, touch.y),
        camStart: { x: state.camera.x, y: state.camera.y, zoom: state.camera.zoom },
        moved: false,
      };
      pinchState = null;
    }
  }, { passive: true });

  els.mapStage.addEventListener("touchmove", (event) => {
    event.preventDefault(); /* pan started: suppress the synthesized click */
    for (const touch of event.changedTouches) {
      if (activeTouches.has(touch.identifier)) {
        activeTouches.set(touch.identifier, { x: touch.clientX, y: touch.clientY });
      }
    }
    if (activeTouches.size === 2 && pinchState) {
      const [a, b] = [...activeTouches.values()];
      const dist = Math.hypot(b.x - a.x, b.y - a.y);
      const midSvg = toSvgPoint((a.x + b.x) / 2, (a.y + b.y) / 2);
      /* restore the pinch start (zoom too, so the ratio is absolute), pan by
       * the mid-point delta, then zoom at the current mid-point so the world
       * under the fingers stays put */
      state.camera.zoom = pinchState.startZoom;
      const next = panCameraBySvgDelta(pinchState.startCam, pinchState.startMidSvg, midSvg, pinchState.startZoom);
      state.camera.x = next.x;
      state.camera.y = next.y;
      zoomAt(midSvg, dist / pinchState.startDist);
    } else if (activeTouches.size === 1 && touchPanState) {
      const [touch] = [...activeTouches.values()];
      const current = toSvgPoint(touch.x, touch.y);
      const deltaX = current.x - touchPanState.startSvg.x;
      const deltaY = current.y - touchPanState.startSvg.y;
      if (Math.hypot(deltaX, deltaY) > 3) touchPanState.moved = true;
      const next = panCameraBySvgDelta(touchPanState.camStart, touchPanState.startSvg, current, touchPanState.camStart.zoom);
      state.camera.x = next.x;
      state.camera.y = next.y;
      applyCamera();
    }
  }, { passive: false });

  function endTouch(event) {
    for (const touch of event.changedTouches) activeTouches.delete(touch.identifier);
    if (activeTouches.size < 2) pinchState = null;
    if (activeTouches.size === 0) {
      touchPanState = null;
      isTouching = false;
      els.mapStage.classList.remove("panning");
    }
  }
  els.mapStage.addEventListener("touchend", endTouch);
  els.mapStage.addEventListener("touchcancel", endTouch);

  /* a click right after a drag must not select nodes under the pointer */
  document.addEventListener("click", (event) => {
    if (suppressNextClick) {
      event.stopPropagation();
      event.preventDefault();
      suppressNextClick = false;
    }
  }, true);

  attachCombobox(els.originSearch, (item) => {
    state.origin = item.id;
    state.selectedNode = item.id;
    planAndRender();
  });
  attachCombobox(els.destinationSearch, (item) => {
    state.destination = item.id;
    state.selectedNode = item.id;
    planAndRender();
  });
  let entitySearchTimer = null;
  els.entitySearch.addEventListener("input", () => {
    clearTimeout(entitySearchTimer);
    entitySearchTimer = setTimeout(() => searchPlayerEntities(els.entitySearch.value), 180);
  });
  els.entitySearch.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      els.entitySearch.value = "";
      searchPlayerEntities("");
    }
  });
  els.swapRoute.addEventListener("click", () => {
    const tmp = state.origin;    state.origin = state.destination;
    state.destination = tmp;
    els.originSearch.value = nodeLabel(state.origin);
    els.originSearch.dataset.nodeId = state.origin;
    els.destinationSearch.value = nodeLabel(state.destination);
    els.destinationSearch.dataset.nodeId = state.destination;
    planAndRender();
  });
  els.routeProfile.addEventListener("change", () => {
    state.routeProfile = els.routeProfile.value;
    els.routeProfileHint.textContent = activeRouteProfile().description;
    planAndRender();
  });
  els.plan.addEventListener("click", planAndRender);
  els.reset.addEventListener("click", () => {
    const defaults = state.store.defaults;
    state.origin = defaults.origin || state.origin;
    state.destination = defaults.destination || state.destination;
    state.conditions = new Set(defaults.conditions || []);
    state.preference = "balanced";
    state.routeProfile = state.routeProfiles?.defaultProfile || DEFAULT_ROUTE_PROFILE;
    state.layer = "all";
    state.selectedNode = state.origin;
    els.originSearch.value = nodeLabel(state.origin);
    els.originSearch.dataset.nodeId = state.origin;
    els.destinationSearch.value = nodeLabel(state.destination);
    els.destinationSearch.dataset.nodeId = state.destination;
    els.routeProfile.value = state.routeProfile;
    els.routeProfileHint.textContent = activeRouteProfile().description;
    document.querySelectorAll(".condition-item input").forEach((input) => { input.checked = state.conditions.has(input.dataset.conditionId); });
    document.querySelectorAll(".segment").forEach((button) => button.classList.toggle("active", button.dataset.preference === state.preference));
    document.querySelectorAll(".layer-tab").forEach((button) => button.classList.toggle("active", button.dataset.layer === state.layer));
    els.preferenceHint.textContent = PREFERENCE_HINTS[state.preference];
    planAndRender();
  });
  els.conditionsAll.addEventListener("click", () => {
    for (const condition of state.store.conditions.values()) state.conditions.add(condition.id);
    document.querySelectorAll(".condition-item input").forEach((input) => { input.checked = true; });
    planAndRender();
  });
  els.conditionsNone.addEventListener("click", () => {
    state.conditions.clear();
    document.querySelectorAll(".condition-item input").forEach((input) => { input.checked = false; });
    planAndRender();
  });
  document.querySelectorAll(".segment").forEach((button) => button.addEventListener("click", () => {
    state.preference = button.dataset.preference;
    document.querySelectorAll(".segment").forEach((item) => item.classList.toggle("active", item === button));
    els.preferenceHint.textContent = PREFERENCE_HINTS[state.preference];
    planAndRender();
  }));
  document.querySelectorAll(".layer-tab").forEach((button) => button.addEventListener("click", () => {
    state.layer = button.dataset.layer;
    document.querySelectorAll(".layer-tab").forEach((item) => item.classList.toggle("active", item === button));
    renderGraph();
  }));
  document.getElementById("zoom-in").addEventListener("click", () => zoomAt({ x: VIEWBOX_WIDTH / 2, y: VIEWBOX_HEIGHT / 2 }, 1.2));
  document.getElementById("zoom-out").addEventListener("click", () => zoomAt({ x: VIEWBOX_WIDTH / 2, y: VIEWBOX_HEIGHT / 2 }, 1 / 1.2));
  document.getElementById("zoom-reset").addEventListener("click", resetCamera);
  els.mapBack.addEventListener("click", () => {
    state.mapView = "regions";
    state.detailRegion = null;
    state.selectedNode = null;
    els.mapBack.hidden = true;
    resetCamera();
    renderGraph();
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

function routeText(route) {
  const lines = route.edges.map((edge, index) => {
    const from = nodeLabel(edge.from);
    const to = nodeLabel(edge.to);
    const direction = edge.direction === "one_way" || edge.direction === "one_way_drop" ? "（单向）" : "";
    return `${index + 1}. ${from} → ${to}${direction} · ${modeZh(edge)}`;
  });
  return `艾尔登法环可达性地图 路线（${route.edges.length} 段）\n${lines.join("\n")}`;
}

document.addEventListener("DOMContentLoaded", init);
