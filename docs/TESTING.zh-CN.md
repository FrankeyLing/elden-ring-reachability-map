# 测试与构建

**语言**: [English](../README.md) · [中文](./TESTING.zh-CN.md)

# V1.0 完整性校验（本地数据声明 → 区域可达性闭包；不通过则退出码 1）
python scripts/build-v1-graph.py

# 8 条 E2E 路线回归（真实 HTTP 服务 + framework 引擎）
node scripts/e2e-route-regression.mjs

# 故障隔离测试：零数据/单包/坏节点/悬空边/未知条件/坏行/坏包/缺桥接/重复id/最小阻断
node scripts/test-fault-isolation.mjs

# 获取实体查询回归：铃兰/锻造石搜索、规范化、多获取关系与终点桥接
python scripts/test-player-entity-query.py

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
