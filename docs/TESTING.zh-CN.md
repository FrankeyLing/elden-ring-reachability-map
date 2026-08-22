# 测试与构建

**语言**: [English](../README.md) · [中文](./TESTING.zh-CN.md)

# V1.0 完整性校验（本地数据声明 → 区域可达性闭包；不通过则退出码 1）
python scripts/build-v1-graph.py

# 2026-08-21 真实需求合同静态门槛。Beta 与最终 V1 分开报告；
# V1 存在任何覆盖、获取、终点或拓扑缺口时必须退出码 1。
python scripts/audit-real-requirements.py --milestone beta
python scripts/audit-real-requirements.py --milestone v1

# 从同一固定快照连续完整构建两次，稳定实体/关系/数据包投影必须一致。
python scripts/test-reproducible-build.py

# 8 条 E2E 路线回归（真实 HTTP 服务 + framework 引擎）
node scripts/e2e-route-regression.mjs

# 故障隔离测试：零数据/单包/坏节点/悬空边/未知条件/坏行/坏包/缺桥接/重复id/最小阻断
node scripts/test-fault-isolation.mjs

# 获取实体查询回归：铃兰/锻造石搜索、规范化、多获取关系与终点桥接
python scripts/test-player-entity-query.py

# 发布追踪策略：源代码不追踪生成型大型 JSON；发布时由清单注入数据
python release.py --check
python release.py

# 独立商店修复队列：每条未解析购买缺口一条证据记录；不得混入具名卖家或猜测终点
python scripts/build-shop-gap-catalog.py
python scripts/audit-shop-gap-catalog.py

# 同一回归还覆盖实体到地图的抽象拓扑查询：精确目标路径、多目标汇总和无路线隔离。

# 获取终点桥接：逐条隔离获取关系与保留缺口，审计地图/层锚点，禁止桥接记录进入路线
python scripts/build-acquisition-topology-bridge.py
python scripts/audit-acquisition-topology-bridge.py --input data/v1/entities/acquisition-topology-bridge.json --acquisitions data/v1/entities/acquisition-registry.json

# 区域包含绑定：只有已证明的精确地图身份可以包含到正式区域；
# 候选、外部范围和未解析终点不得升级为正式绑定
python scripts/build-contains-bindings.py

# 独立抽象地图/楼层拓扑轨迹包；不进入正式玩家路线，也不执行碰撞或物理检查
python scripts/build-abstract-topology-route-graph.py
python scripts/audit-abstract-topology-route-graph.py --input data/v1/entities/abstract-topology-route-graph.json

# 正式起点到抽象地图身份证据；候选起点保持阻断，不会成为正式路线起点。
python scripts/build-abstract-origin-bindings.py
python scripts/audit-abstract-origin-bindings.py

# 获取桥接审计同时检查部件语义锚点；任何桥接记录都不得进入正式路线

# 获取实体层故障隔离：单条坏实体记录隔离后，其余实体仍可查询
python scripts/test-entity-layer-isolation.py

# 数据包完整性审计（拆包不丢边、不悬空、不重复）
python scripts/audit-packages.py --graph data/v1/graph-v1.json

# 从 V1.0 图重建数据包（机械拆分，可重复）
python scripts/build-packages.py --graph data/v1/graph-v1.json --out data/v1/packages

# 官方中文映射审计（uncovered 清单 + 字段完整性）
python scripts/audit-zh-mapping.py --graph data/v1/graph-v1.json

# 重建官方中文映射（需先重建 274MB 双语 FMG 索引）
python scripts/build-official-fmg-index.py --msg-root <快照>/extracted/msg-all --oodle-dll <快照>/runtime/oo2core_6_win64.dll --output data/v1/entities/official-fmg-bilingual-index.json
python scripts/build-official-zh-mapping.py --graph data/v1/graph-v1.json

# 重建本地地图权威名表（地图文件地名标识 → 官方文本）
python scripts/build-local-map-names.py

# 从本地 MSBE 副本自产赐福坐标（模型 AEG099_060）
python scripts/build-local-grace-positions.py

# 重建规范装备族与玩家查询投影
python scripts/build-entity-registry.py --param-dir <snapshot>/extracted/param-json
python scripts/build-acquisition-registry.py --param-dir <snapshot>/extracted/param-json
python scripts/build-player-entity-index.py
python scripts/test-player-entity-query.py
