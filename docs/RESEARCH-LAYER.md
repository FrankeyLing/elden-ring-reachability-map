# Research Layer (Local Research Evidence)

**Language**: English · [中文](RESEARCH-LAYER.zh-CN.md)

以下内容描述本地游戏数据考据产物（MSBE/EMEVD/NVA/ObjAct 等证据层）。它们全部 `routeable: false`，不参与玩家路线规划；开发检查入口为 `/research.html`。


## Online Boss identity layer

The current Online Verified V1 API exposes the pinned MapForGoblins Boss coordinates through `/api/catalog/boss-positions`. Twenty records are additionally checked against `sourceIndex`, `mapId`, `npcParamId`, and encounter name in [`data/v1/entities/boss-identity-bindings.json`](../data/v1/entities/boss-identity-bindings.json). These bindings only connect coordinate evidence to an existing formal Boss node; they never create traversal edges, Boss gates, or game-state changes. Ambiguous and source-only Boss records remain explicitly unbound.

## Abstract topology boundary

The merged graph now exposes 5,817 NVA-to-MSBE model identity candidates, 11,646 identity relations, 5,817 raw-layer identity memberships, and 84 exact same-mechanism opposite-side ObjAct pair relations. These remain identity/evidence relations, not selected entrances or routeable edges.

Layer coverage is now explicit for all 1,347 source maps: 1,297 have exact raw `map_studio_layer` partitions and 50 source maps contain no Part records, so they are marked `source_map_has_no_parts` rather than being assigned a fabricated layer.

The local abstract layer remains independent of walkability promotion: [`data/v1/entities/local-abstract-entity-topology.json`](../data/v1/entities/local-abstract-entity-topology.json) contains exact MSBE map connections, topology-support entities, semantic references, and a separate map-level attachment to the native NVA evidence layer; every candidate relation is `routeable: false`. NVA/Navmesh declarations are evidence only and do not claim continuous player walkability or turn event evidence into a transition guard without an exact endpoint binding. The browser can inspect a map subset through `/api/local-abstract-topology/map?map_id=...`.

## Exact transition audit

[`data/v1/entities/local-transition-audit.json`](../data/v1/entities/local-transition-audit.json) is the next formal-topology layer. It binds 17 `ConnectCollision` endpoint pairs and 132 `Connection` region endpoint pairs using only declared target-map fields plus exact target-side identity. It also preserves all 825 local `ObjAct` records, including 535 conservative transition candidates such as elevators, doors, and one-way shortcuts; these remain control-to-part evidence, not guessed destinations.

The audit intentionally reports `direct_routeable_records: 0`. An exact map endpoint pair is not yet a complete player route: its approach segment, state guard, and resulting destination state still need separate evidence-backed binding. The exact endpoint identity pass does not depend on collision geometry; the native NVA/Navmesh layer is now read separately so the eventual physical topology compiler can bind native walkable components without conflating them with semantic relations.

The same audit now joins ObjAct target-part `entity_id` to local EMEVD references without using proximity. 52 ObjAct candidates have 154 exact entity-reference rows, including direct ObjAct-state/action-button operations. Two records whose `ObjActPartName` is absent are resolved through a unique same-map sibling `ObjActEntityID` identity, two through a unique same-map ObjAct-parameter plus EMEVD state-target chain, one through strict raw `InitializeCommonEvent` parameter substitution plus a unique `Set ObjAct State` target Part, two cross-map controls through an exact target-map ObjAct identity plus target event `ObjActPartName`, two more through the stricter global `(ObjActID, ObjActEntityID)` identity plus a unique named target Part on another map, and 10 through the independently verified identity transform `target Part.entity_id = ObjActEntityID - 2000` with a unique same-map Part; 54 records remain unresolved, of which 33 are transition-like controls and 21 are loot/non-transition interactions. All 34 raw ObjAct `MapID` values resolve to local map identities after applying the verified packed-ID format; these remain map-identity evidence only, not destination or route edges without direction proof. Three raw scripted-warp bindings resolve an explicit EMEVD destination entity, and 12 raw scripted map-warp bindings resolve a target map plus an exact landing entity from `Warp Player` or `Play Cutscene to Player and Warp`. Event-scoped conditions and effects are retained as script evidence only; they are not automatically attached as edge guards because event control flow still has to be resolved.

The same transition audit also records 84 exact same-map upper/lower ObjAct mechanism pairs (168 control records) from opposite-side source labels after formatting-only normalization. These are mechanism/control relationships, not destination edges or player-route directions; the six pairs that still lack target parts remain unresolved for routing.

The unresolved transition-like controls now carry a negative identity audit: 14 have no cross-map record with the same `(ObjActID, ObjActEntityID)`, 2 have a cross-map record but no uniquely named target Part, and 17 have an invalid/sentinel ObjAct parameter or entity identity. This is an evidence boundary, not a guessed destination; all remain `routeable: false`.

[`data/v1/entities/local-emevd-guard-traces.json`](../data/v1/entities/local-emevd-guard-traces.json) now provides bounded control-flow traces for all 15 exact scripted Warp targets across 8 EMEVD events. All 15 have a syntactic path and zero decode failures, but every trace remains `syntactic_branch_trace_only`; runtime condition truth and save-state truth are not guessed. The artifact is available from `/api/local-emevd/guard-traces`.

[`data/v1/entities/local-emevd-guard-atoms.json`](../data/v1/entities/local-emevd-guard-atoms.json) converts those traces into 15 Guard records with 29 sampled paths and 144 predicate candidates. They remain `candidate_atoms_only` and `routeable: false` until runtime condition truth, current world state, and the player-space segment are independently bound.

The Guard atom artifact cross-references 25 distinct event-flag IDs against two pinned local Smithbox sources and one pinned public SoulsMods index: 3 have primary alias names/tags, 10 more have exact local Event Flags Dump documentation, 11 occur in the public index, and 14 do not. All 25 nevertheless have an exact instruction-level reference in their local EMEVD event; that fact is recorded separately from semantic naming. The 12 locally unresolved IDs also have no exact row in the public index. Missing names remain missing evidence rather than being inferred from numeric ranges.

[`data/v1/entities/local-emevd-guard-expressions.json`](../data/v1/entities/local-emevd-guard-expressions.json) compiles the Guard atoms into 29 conservative `all_of` candidate expressions across the same 15 targets. Condition-group operators are now verified as positive=AND, negative=OR, and zero=MAIN temporal; world-type values are verified as `0=OwnWorld` and `1=OtherWorld`. Runtime truth, current save state, and player-space segments remain unresolved. The read-only API is `/api/local-emevd/guard-expressions`, and no expression promotes a route edge.

[`data/v1/entities/local-emevd-condition-group-semantics.json`](../data/v1/entities/local-emevd-condition-group-semantics.json) pins the static EMEVD group mapping: 31 possible IDs, with 15 observed in the extracted Guard records; positive IDs are AND, negative IDs are OR, and zero is MAIN. It intentionally does not evaluate event timing, compiled/uncompiled truth, or save state. The read-only API is `/api/local-emevd/condition-group-semantics`.

[`data/v1/entities/local-emevd-warp-candidates.json`](../data/v1/entities/local-emevd-warp-candidates.json) indexes all 585 map-local EMEVD warp instructions found in the local snapshot. It preserves player, character, asset, and generic scripted transport separately; 355 records have an exact local map/entity destination or exact map identity, 14 target an exact runtime player entity, and 216 have no statically resolvable destination. `Warp Asset To Character` now uses its native `Character Entity ID` field rather than incorrectly treating the target as absent. This is script transport evidence, not a player-walk route, so every record remains `routeable: false`; the read-only API is `/api/local-emevd/warp-candidates`.

[`data/v1/entities/local-objact-param-index.json`](../data/v1/entities/local-objact-param-index.json) is a read-only extraction of the local snapshot's `ObjActParam.param`: Regulation `11611000`, `OBJ_ACT_PARAM_ST` data version 3, 96-byte rows, 198 rows. It uses a matching version-3 layout and exposes interaction distance, angle, animation, special-condition, action-button, and timing fields without treating them as destinations. The API is `/api/local-emevd/objact-param`; all records remain `routeable: false`.

[`data/v1/entities/local-guarded-transition-candidates.json`](../data/v1/entities/local-guarded-transition-candidates.json) joins all 15 exact scripted transition bindings (3 entity warps and 12 map warps) to their 29 Guard-expression paths by exact transition binding ID. The read-only API is `/api/local-transition-audit/guarded-candidates`; all 15 remain `routeable: false` and `formal_transition_promotion_ready: false` until the unresolved guard and player-space evidence is solved.

[`data/v1/entities/local-msbe-layer-index.json`](../data/v1/entities/local-msbe-layer-index.json) preserves all 676,631 local MSBE parts across 1,347 source maps using the raw `map_studio_layer` field: 21 distinct layer values, with 2,669 parts on non-default values. The API `/api/local-msbe/layers?map_id=...` exposes the native layer partition to the map UI. No layer value is renamed to a guessed floor, and this layer pass does not require Havok or prove walkability.

The merged abstract graph now joins these 1,347 exact map-layer partitions as `native_map_layer` nodes and `map_contains_native_layer_partition` relations, plus 11,034 exact Part/Region-to-layer membership relations where the referenced layer partition exists. They preserve the original `map_studio_layer` value, part counts, bounds, and sample entities; they deliberately do not claim that a value means ground, underground, roof, or a player-walkable floor.

[`data/v1/entities/local-nva-navmesh-index.json`](../data/v1/entities/local-nva-navmesh-index.json) is the read-only native NVA/Navmesh evidence layer decoded from the copied snapshot with the pinned Oodle library: 997/997 NVA files parse as Elden Ring NVMA v8, covering 997 maps and 9,480 native Navmesh instances, 5,884 Connectors, 137,358 Navmesh connections, and 9,243 GateNodes; every NVA file has its paired NVMHKTBND asset. It records native declarations and exact source hashes but keeps `continuous_player_walkability: false`, `physical_geometry_validated: false`, and `routeable: false`. The full index is available at `/api/local-nva/index`; map-scoped detail is available at `/api/local-nva/map?map_id=...`.

[`data/v1/entities/local-nva-connectivity-candidates.json`](../data/v1/entities/local-nva-connectivity-candidates.json) resolves all 5,884 native Connector endpoint NameIDs uniquely to Navmesh instances and records 7,201 undirected native component candidates; all 5,884 also have an observed reverse native Connector. This is the first native physical-topology candidate layer, not a player route: `player_walkability_validated: false` and `routeable: false` remain mandatory. Its read-only endpoints are `/api/local-nva/connectivity` and `/api/local-nva/connectivity/map?map_id=...`.

[`data/v1/entities/local-nva-boundary-pair-index.json`](../data/v1/entities/local-nva-boundary-pair-index.json) expands the 5,884 native Connectors into 137,358 exact face/edge boundary pairs. HKX2 geometry is present at every pair endpoint; 127,534 pairs have indices valid in the corresponding HKX2 summaries, while 9,824 expose a real NVA Connector-index-space versus HKX2-summary-index-space mismatch and remain unresolved. These records are native adjacency evidence only, never player Transitions; all remain `routeable: false`. The endpoints are `/api/local-nva/boundary-pairs` and `/api/local-nva/boundary-pairs/map?map_id=...`.

[`data/v1/entities/local-native-topology-graph.json`](../data/v1/entities/local-native-topology-graph.json) now promotes that evidence into a dedicated abstract native graph: 9,480 exact native Navmesh nodes, 5,884 exact NVA Connector declaration edges, and 137,358 optional boundary face/edge witness edges across 997 NVA-backed maps. The Connector declaration layer is the pure abstract topology layer and does not require HKX2/Havok geometry; HKX2 remains supporting index evidence only, including the 9,824 index-space conflicts. The 350 MSBE maps without NVA stay explicitly uncovered rather than being marked unplayable. This graph does not require the Havok runtime or a running game, and it does not claim player walkability, travel direction, floor semantics, or current-state passage. The full graph is available at `/api/local-native-topology-graph`; map-scoped data is available at `/api/local-native-topology-graph/map?map_id=...`.

[`data/v1/entities/local-native-msbe-model-bindings.json`](../data/v1/entities/local-native-msbe-model-bindings.json) joins the native nodes to the copied raw MSBE `Collision/ConnectCollision` parts by case-insensitive exact `model_name` identity: 9,436/9,480 Navmesh nodes have at least one exact MSBE model candidate, 7,438 are unique, 1,998 preserve Collision-versus-ConnectCollision role candidates, and 44 zero-model nodes remain unresolved. The native topology graph exposes 11,646 corresponding cross-layer identity relations. This is an identity bridge for the abstract graph, not a guessed entrance or walk edge. The read-only endpoints are `/api/local-native-msbe-model-bindings` and `/api/local-native-msbe-model-bindings/map?map_id=...`; all records remain `routeable: false`.

[`data/v1/entities/local-msbe-native-endpoint-bindings.json`](../data/v1/entities/local-msbe-native-endpoint-bindings.json) applies the same identity rule specifically to all 1,125 MSBE `ConnectCollision` endpoints. It yields 2,206 native candidate relations: 1,103 endpoint records have repeated same-model Navmesh instances and 22 have no NVA candidate. The embedded strict identity audit confirms that all 1,125 are currently unselectable as a single NVA instance from source identity alone: the sources share map/model identity but expose no proven cross-layer instance key. No instance is selected by proximity, geometry, index order, name similarity, or target-map guess. The API is `/api/local-msbe-native-endpoint-bindings` with map-scoped detail at `/api/local-msbe-native-endpoint-bindings/map?map_id=...`.

[`data/v1/entities/local-nva-coverage-audit.json`](../data/v1/entities/local-nva-coverage-audit.json) compares the 997 native NVA-backed maps with all 1,347 parsed MSBE maps. The copied archive was independently re-extracted through Nuxe: 997 actual NVA paths were recovered and matched the primary NVA inventory; the Nuxe hash catalog contains 999 path entries, with only `m60_42_40_10` and `m60_47_42_10` catalog-only entries. The remaining 350 MSBE maps are therefore not an extraction omission in this snapshot, but they are still not labeled playable or unplayable; they remain `unclassified_requires_independent_evidence`, with raw MSBE capability counts preserved. The read-only coverage report is `/api/local-nva/coverage`.

[`data/v1/entities/local-map-coverage-classification.json`](../data/v1/entities/local-map-coverage-classification.json) is the complete 1,347-map evidence inventory: 846 maps have NVA Navmesh declarations, 151 have an NVA file without a Navmesh section, 70 lack NVA but retain MSBE event/region signals, 269 retain only static MSBE signals, and 11 have no MSBE playability signal. These are evidence classes only; every map's playability and floor semantics remain unresolved until independently proven. The map-scoped API is `/api/local-map-coverage/classification/map?map_id=...`.

[`data/v1/entities/local-nvmhktbnd-index.json`](../data/v1/entities/local-nvmhktbnd-index.json) verifies the paired NVMHKT BND4 containers: all 997 parse successfully, exposing 10,880 inner `TAG0` HKX entries. It separates `n...hkx` native Navmesh entries from other same-ModelID assets; 2,974 NVA ModelID bindings are uniquely matched and 1,739 remain explicitly missing because the current filename evidence does not identify a unique Navmesh HKX. This container/provenance artifact intentionally remains `geometry_deserialized: false`, `player_walkability_validated: false`, and `routeable: false`; the decoded geometry is recorded in the separate HKX2 artifact below. The endpoints are `/api/local-nvmhktbnd/index` and `/api/local-nvmhktbnd/map?map_id=...`.

[`data/v1/entities/local-nvmhktbnd-hkx2-geometry-index.json`](../data/v1/entities/local-nvmhktbnd-hkx2-geometry-index.json) deserializes the native `n*.hkx` entries from all 997 copied NVMHKT containers using the source-compiled HKLib 2018 reader and the copied Oodle runtime: 3,390 `hkaiNavMesh` entries, 16,607,263 vertices, 6,888,218 faces, and 29,901,878 edges. Each entry also preserves native AABB/vertex bounds, blocked-edge counts, and edge-flag distributions. This proves native geometry was decoded, not that a player can walk every polygon; `player_walkability_validated: false` and `routeable: false` remain mandatory. The endpoints are `/api/local-nvmhktbnd/hkx2-geometry` and `/api/local-nvmhktbnd/hkx2-geometry/map?map_id=...`.

[`data/v1/entities/local-native-topology-evidence-chain.json`](../data/v1/entities/local-native-topology-evidence-chain.json) joins the NVA Navmesh/Connector declarations to exact NVMHKT `n*.hkx` entries and then to their deserialized HKX2 geometry. It covers 9,480 native Navmesh nodes and 5,884 native Connectors; 5,956 nodes have an exact HKX2 geometry binding and 3,524 remain explicitly unresolved at the filename/model layer. All 5,884 connector pairs have geometry at both native endpoints, but this is boundary evidence only, not a player Transition: all nodes/connectors remain `routeable: false`, and no runtime state, floor direction, gate condition, or player-space route has been inferred. The endpoints are `/api/local-native-topology-evidence-chain` and `/api/local-native-topology-evidence-chain/map?map_id=...`.

[`data/v1/entities/local-abstract-topology-graph.json`](../data/v1/entities/local-abstract-topology-graph.json) is the merged abstract evidence graph: 29,144 nodes and 7,976 topology edges, consisting of 1,588 native MSBE map declarations, 149 exact endpoint pairs, 15 exact scripted warp destinations, 340 additional deduplicated EMEVD transport-evidence edges, and 5,884 exact pure-abstract NVA Connector declaration edges. The NVA nodes/Connector edges are first-class in the merged graph; 137,358 geometry-backed boundary witness edges remain deliberately outside the main abstract edge set. It now also exposes 5,817 exact NVA-to-MSBE model identity candidates, 11,646 identity relations, and 5,817 raw-layer membership relations; 4,709 identity candidate nodes were added where the normalized source Part node used a different identity key. These are cross-layer identity candidates, not selected entrances or walk edges. Its source layer includes 1,347 exact native MSBE layer-partition nodes/relations, 598 MSBE Region nodes exactly referenced by map-local EMEVD entity-ID arguments (824 references), and 610 EMEVD-referenced Part nodes (2,500 references); these are exact event/transport bindings, not guessed walk edges. A separate relation layer adds 771 exact ObjAct-event-to-target-part control relations, including one raw common-event binding, 34 exact ObjAct-to-local-MapID identity relations, 18 exact ObjAct-to-EMEVD-transport bindings, and preserves 54 unresolved ObjAct controls; 33 of the unresolved controls are transition-like and 21 are loot/non-transition interactions. The graph attaches exact version-3 ObjActParam rows to 637 control relations; 105 distinct ObjAct IDs resolve, while two non-sentinel IDs are absent from the local parameter table. It also preserves 695 event-scoped EMEVD state-evidence records (317 conditions and 378 actions), including 165 ObjAct-state writes; 130 of those writes carry an exact matching ObjAct Param ID. Runtime truth remains explicitly unevaluated. Fifteen of those 18 exact ObjAct transport bindings have a linked candidate Guard expression; three remain outside the Guard trace index. The graph preserves 9 supplemental exact ObjAct target-Part nodes and 11 supplemental warp locator nodes plus four external map-target nodes, while retaining 230 unresolved warp records separately instead of dropping or guessing them. It retains exact map-level native NVA evidence for all 997 NVA-backed maps and the dedicated native graph's source hashes and geometry witness layer, while retaining `native_nva_evidence_used: true`, `native_topology_graph_joined_by_map_id: true`, and `havok_nva_navmesh_used_for_continuous_walkability: false`. The full graph is available at `/api/local-abstract-topology-graph`; map-scoped data is available at `/api/local-abstract-topology-graph/map?map_id=...`. Every edge and relation remains `routeable: false`.


《艾尔登法环》可达性图 WebUI 原型。

这个项目把地图建模为有向图：

- 节点：赐福、入口、升降梯端点、传送点、Boss 房、目标物品和关键岔路。
- 边：步行、梯子、升降梯、跳落、传送门、棺材等连接。
- 边属性：方向、层级变化、时间代价、风险、备注和条件。
- 路线：根据当前条件开关，用 Dijkstra 在可通行边上计算路线。

旧的演示 `data/graph.json` 已删除；正式 Online Verified V1 使用独立的 `data/v1` 数据，不得继续按 demo 结构补点冒充正式数据。机器可读来源与调度规则见 [`data/online-source-registry.json`](../data/online-source-registry.json) 和 [`data/execution-policy.json`](../data/execution-policy.json)。

当前正式入口是 [`data/v1/graph.json`](../data/v1/graph.json)、[`data/v1/entities/sites-of-grace.json`](../data/v1/entities/sites-of-grace.json)、[`data/v1/entities/named-grace-identity-bindings.json`](../data/v1/entities/named-grace-identity-bindings.json)、[`data/v1/entities/achievements.json`](../data/v1/entities/achievements.json) 与 [`data/v1/entities/er-guide-route-legs.json`](../data/v1/entities/er-guide-route-legs.json)；赐福目录和路线候选分别由 [`scripts/ingest-sites-of-grace.ps1`](../scripts/ingest-sites-of-grace.ps1) 与 [`scripts/ingest-er-guide-route-legs.ps1`](../scripts/ingest-er-guide-route-legs.ps1) 从固定在线 revision/commit 生成，目录、成就目标、身份绑定和候选路段默认不可路由。当前执行 Phase 1A：在不接触前台游戏的 `GAMING_SAFE + ONLINE_INGEST` 通道中，从有许可、可追溯的在线文本/JSON Source Snapshot 建立 `Online Verified V1`；Phase 1B 才在游戏退出或合格独立快照可用后，从本地游戏文件校准坐标、楼层、状态和 Transition，逐项升级为 `local_game_verified`。

## 当前 Online V1 数据层

当前真实在线坐标视图按地图层读取固定快照，不读取游戏进程、存档、游戏目录或内存：

- 806 个在线底图瓦片层；1037 个可选在线地图层；442 个非 dummy 赐福原始坐标；215 个 Boss 坐标。
- 563 个命名地图点；31,144 个物品/掉落位置；15,099 个实体；21,824 个采集节点。
- 362 条地图坐标转换证据，仅作为跨地图定位参考，全部保持 `routeable: false`。
- 42 项来源固定的成就目标，其中 30 项 Boss 成就已绑定正式 Boss 节点；4 项传奇收集成就保留逐项需求清单，其中骨灰、护符、3 项传奇武器和 3 项传奇法术已补齐正式位置锚点。
- 传奇收集需求与固定物品位置快照逐项审计命中 24/30；其余 6 项已用独立 Eldenpedia 成就路线资料绑定到地点锚点，但仍不冒充精确拾取坐标或自动路线。
- 坐标视图可切换敌人、地图资产和全部实体；在线查询面板可检索各类坐标记录。
- 在线投影视图接入固定 `jw-ofs/elden-ring-map` `markers.js` 快照中的全部 413 个命名赐福锚点，覆盖 M00/M01/M10；375 个与正式赐福节点精确关联，38 个明确保留为未绑定在线标记。投影坐标空间明确为 `master_tile_pixel`，不冒充游戏 XYZ，也不产生路线边。
- “命名源 XYZ”视图接入 Elden Ring Compass 生成的 419 个赐福实体 `mapId + x/y/z` 坐标；它们按 `source_map_local_xyz` 单独显示，不与 MapForGoblins 坐标混叠，417 个记录带有正式节点身份候选，其中 39 个通过独立的名称/区域/mapId 绑定表补齐，2 个仍明确未绑定；全部保持 `routeable: false`。
- 正式图谱当前为 746 个节点、1195 条有向路线边、353 个在线坐标锚点；4 个无法由固定在线快照唯一定位的 Boss 保留文本位置锚点，不伪造 XYZ。
- 在线查询中的成就目标可直接定位到正式目标节点，并在当前条件下选择最近已证实赐福作为路线起点；若状态证据不足仍显示阻断原因。
- 42 项成就中，36 项有正式目标节点、5 项有位置目标、1 项额外声明前置拓扑节点；结局与世界状态记录保留状态条件和外部交互条件，不把成就记录本身伪装成可通行边。
- 当前成就覆盖审计为 40/42 项存在正式赐福到目标的拓扑路径；剩余 2 项是总成就和升级成就，本身没有单一空间目标，保持未绑定状态。
- 集合成就查询会附带固定 MapForGoblins 物品位置证据；缺少 XYZ 的物品另附独立 Eldenpedia 文字地点证据并标记 `coordinate_available: false`，前端可定位到正式地点节点，但不会生成从赐福到物品的假路线。
- 成就目标的自动起点选择会遵循当前路线 Profile；允许快速旅行时只使用规划层动态边，正式图仍不写入全连接的伪 Transition。

正式拓扑当前仍是 Online Verified V1 的已取证切片，不得宣传为完整 1:1 游戏导航图；未有方向、楼层、条件和独立证据的在线点位不会自动成为路线边。

## 启动

需要 Python 3.9+，不需要安装第三方依赖：

```powershell
cd <项目目录>
python server.py
```

然后访问：<http://127.0.0.1:8090>

游戏运行期间可使用项目自带的隐藏后台启动器：

```powershell
.\scripts\start-gaming-safe.ps1
```

它只绑定 `127.0.0.1`，不打开浏览器、不发通知、不访问游戏进程/目录/存档、不安装 Overlay 或输入钩子；停止时使用：

```powershell
.\scripts\stop-gaming-safe.ps1
```

指定监听地址或端口：

```powershell
python server.py --host 0.0.0.0 --port 8090
```

## 已实现

- 地表、地下、遗迹/地牢分层筛选。
- 有向边和不可达边可视化。
- 起点/终点选择、条件开关和三种路线偏好。
- 时间、风险、层级切换和通行方式说明。
- 节点详情、路线步骤和复制路线摘要。
- 零构建依赖，便于后续接入真实地图底图或数据库。
