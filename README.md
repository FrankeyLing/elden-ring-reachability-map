# RUNE//PATH

《艾尔登法环》可达性图 WebUI 原型。

这个项目把地图建模为有向图：

- 节点：赐福、入口、升降梯端点、传送点、Boss 房、目标物品和关键岔路。
- 边：步行、梯子、升降梯、跳落、传送门、棺材等连接。
- 边属性：方向、层级变化、时间代价、风险、备注和条件。
- 路线：根据当前条件开关，用 Dijkstra 在可通行边上计算路线。

当前内置的是一套隔离的演示拓扑数据，不是完整的全世界数据集，也不得继续按同一结构补点冒充正式数据。真实项目执行规格见 [`ELDEN_RING_FULL_MAP_EXECUTION_SPEC.md`](./ELDEN_RING_FULL_MAP_EXECUTION_SPEC.md)，在线真实 V1 方案见 [`ONLINE_FIRST_V1_PLAN.md`](./ONLINE_FIRST_V1_PLAN.md)，游戏并行边界见 [`CONCURRENT_EXECUTION_PLAN.md`](./CONCURRENT_EXECUTION_PLAN.md)，Phase 0 环境基线见 [`PHASE0_ENVIRONMENT_BASELINE.md`](./PHASE0_ENVIRONMENT_BASELINE.md)。机器可读来源与调度规则分别见 [`data/online-source-registry.json`](./data/online-source-registry.json) 和 [`data/execution-policy.json`](./data/execution-policy.json)，当前真实安装 manifest 见 [`data/source-manifest.json`](./data/source-manifest.json)。

`data/graph.json` 只用于验证界面交互和算法单测，正式构建必须对它保持零引用。当前正式入口是 [`data/v1/graph.json`](./data/v1/graph.json)、[`data/v1/entities/sites-of-grace.json`](./data/v1/entities/sites-of-grace.json) 与 [`data/v1/entities/er-guide-route-legs.json`](./data/v1/entities/er-guide-route-legs.json)；赐福目录和路线候选分别由 [`scripts/ingest-sites-of-grace.ps1`](./scripts/ingest-sites-of-grace.ps1) 与 [`scripts/ingest-er-guide-route-legs.ps1`](./scripts/ingest-er-guide-route-legs.ps1) 从固定在线 revision/commit 生成，目录与候选路段默认不可路由。当前执行 Phase 1A：在不接触前台游戏的 `GAMING_SAFE + ONLINE_INGEST` 通道中，从有许可、可追溯的在线文本/JSON Source Snapshot 建立 `Online Verified V1`；Phase 1B 才在游戏退出或合格独立快照可用后，从本地游戏文件校准坐标、楼层、状态和 Transition，逐项升级为 `local_game_verified`。

## 当前 Online V1 数据层

当前真实在线坐标视图按地图层读取固定快照，不读取游戏进程、存档、游戏目录或内存：

- 806 个地图层；442 个非 dummy 赐福原始坐标；215 个 Boss 坐标。
- 563 个命名地图点；31,144 个物品/掉落位置；15,099 个实体；21,824 个采集节点。
- 362 条地图坐标转换证据，仅作为跨地图定位参考，全部保持 `routeable: false`。
- 坐标视图可切换敌人、地图资产和全部实体；在线查询面板可检索各类坐标记录。

正式拓扑当前仍是 Online Verified V1 的已取证切片，不得宣传为完整 1:1 游戏导航图；未有方向、楼层、条件和独立证据的在线点位不会自动成为路线边。

## 启动

需要 Python 3.9+，不需要安装第三方依赖：

```powershell
cd C:\Users\Frankey\ZCodeProject\repos\elden-ring-reachability-map
python server.py
```

然后访问：<http://127.0.0.1:8090>

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
