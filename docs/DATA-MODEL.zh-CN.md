# 获取实体数据模型

本文档描述获取实体层：如何把《艾尔登法环》中的每一件物品、武器、防具、
法术、敌人、NPC 与地点实例**只记录一次**（**所指**），如何挂接对它的
全部引用（**能指**），以及如何回答「X 从哪里来」（获取关系）。

**语言**：[English](DATA-MODEL.md) · 中文

## 1. 能指 / 所指模型

游戏数据里同一个事物有大量不同的标识符：

- 一把武器同时出现在 `EquipParamWeapon` 的多行（基础行 + 派生行 + 强化行）、
  `WeaponName` FMG 的 id、掉落表 `ItemLotParam` 的 id、商店 `ShopLineupParam` 的 id 中；
- 一个 Boss 对应多个 `NpcParam` 行（每个战斗场地状态一行）、一个或多个
  `NpcName` 条目（对话名与 Boss 战名）、成就条目，以及从它身上掉落的追忆；
- 一座教堂同时是 `WorldMapPointParam` 的一行、`PlaceName` FMG 的一个 id，
  以及（未来）MSB 地图实体。

**所指（Signified）**——一个规范实体，只记录一次，拥有稳定 id：

```json
{
  "id": "weapon_dagger",
  "kind": "weapon",
  "category": "weapon",
  "name": {"en": "Dagger", "zh": "短剑"},
  "signifiers": [
    {"type": "param", "param": "EquipParamWeapon", "rows": [1000000, 1000001, ...]},
    {"type": "fmg", "fmg": "WeaponName", "ids": [1000000]}
  ],
  "properties": {"wepType": 1},
  "variant_count": 26
}
```

**能指（Signifier）**——指向该所指的任何引用形式。每条 `signifiers` 记录
自带命名空间（param 行 id、FMG 名 id、人工说明），无论查询来自哪个来源，
都能定位到同一个实体。

两个用户特别点出的情形：

1. **多能指 → 单所指。** 一把武器的全部派生形态（`Heavy Dagger`、
   `Bandit's Keen Curved Sword`……）与强化行都坍缩到唯一的
   `weapon_dagger` 实体；一个 Boss 的全部 `NpcParam` 行坍缩到唯一的
   Boss 实体。
2. **单能指 → 多所指。** 常见物品（如 `锻造石[1]`）是一个所指，但拥有
   大量获取关系：几十个敌人掉落它、商人出售它、多处拾取它。

## 2. 数据文件

全部位于 `data/v1/entities/`：

| 文件 | 内容 |
|---|---|
| `entity-registry.json` | 全部所指实体（物品/武器/防具/护符/战灰/法术/敌人/NPC/商店）及其全部能指 |
| `acquisition-registry.json` | 获取关系：掉落、拾取、商店、Boss 奖励 |
| `merchant-shop-bindings.json` | 复制的对话脚本商店范围绑定：每个 `ShopLineupParam` 行、具名卖家、对话编号、地图实例和 XYZ 终点；未解析卖家也保留 |
| `location-catalog.json` | 位置实例（来自 `WorldMapPointParam`：教堂、墓地、洞窟、城寨……） |
| `boss-rewards.json` | 从 EMEVD `AwardItemLot` 指令解码出的 Boss 奖励 lot |
| `boss-reward-endpoints.json` | 独立的 Boss 奖励终点绑定：正式 Boss 门节点，以及可用时复制的本地 MSB 战斗坐标 |
| `msb-objact-catalog.json` | MSB 中的 825 个地图机关（宝箱/门/升降机/拉杆/隐藏房间） |
| `msb-message-regions.json` | MSB 中的 50 个游戏内留言区域（含坐标） |
| `graph-v1.json` | 正式可达性图 + 集成的 location/item/boss 节点与关系 |
| `player-entity-index.json` | 玩家查询投影：规范实体、全部获取关系、获取终点状态与拓扑锚点状态；独立于路线数据包 |

### 2.1 entity-registry.json

`kind` 取值：`weapon`、`armor`、`accessory`、`ash_of_war`、`item`、
`spell`、`enemy`、`npc`、`location`。`category` 字段承载用户 10 大分类。

### 2.2 acquisition-registry.json

`method` 取值：`drop`（敌人 `itemLotId_enemy`）、`pickup`
（`ItemLotParam_map`）、`purchase`（`ShopLineupParam`）、`boss_reward`
（追忆/大卢恩映射）、`drops`（反向）。

lot 类别表（对照本地 regulation 转储验证）：`lotItemCategory` 1 = 道具
（Goods）、2 = 武器、3 = 防具、4 = 护符、5 = 战灰。

商店行不能直接按 `ShopLineupParam` 的大段编号猜测商人。
`merchant-shop-bindings.json` 逐条记录“商店行—卖家—对话脚本—地图实例”的关系；
同一个行号由多个卖家出售时，`acquisition-registry.json` 会生成多条独立的
`purchase` 关系。具名卖家保留复制的 MSB 部件和 XYZ 坐标；空白卖家或本地参数中
没有对应外部行的数据，进入隔离的 `shop_context_<id>`，可以搜索但不会被冒充成
具名商人或正式路线边。

### 2.3 location-catalog.json

每个能解析出 `PlaceName` 的 `WorldMapPointParam` 行成为一个位置实体；
`iconId` 映射到位置类型。同名多实例（如三棵小黄金树）使用带后缀的 id。

### 2.4 boss-rewards.json

从全部 589 个地图事件文件中解码 `AwardItemLot` /
`Award Items (Including Clients)` 指令得出。含追忆的 lot 通过官方名称
映射解析到 Boss（`追忆：接肢` → `葛瑞克`）。

`boss-reward-endpoints.json` 是独立的终点层：只把 `boss-identity-bindings.json`
中已有的 Boss 身份绑定到 `graph-v1.json` 的正式 Boss 门节点；如果复制的 MSB
中有对应战斗实体，则同时保留其地图坐标作为证据。本快照发布 20 个可路由 Boss
锚点，其中 17 个有本地战斗坐标。25 条 Boss 奖励关系中目前有 7 条匹配到终点，
其余关系仍可搜索，但明确标记为未绑定，不会阻断其它实体。

## 3. 来源与验证

- 参数来自本地 `regulation.bin` 快照（用 EldenRing 密钥解密、DCX 解压、
  BND4 解析、按 Paramdex XML 定义解码）。每一行都带 param 表名与行号
  作为能指——没有任何来自第三方转储的推断。
- 名称全部来自官方双语 FMG 索引（`official-fmg-bilingual-index.json`），
  无自译。
- 名称 id 公式均对照本地数据验证（如武器名 id 大多数与行 id 相同，
  遗留行用 ×100/×1000，少量 9000 万行用 ÷10）。
- `scripts/audit-acquisition.py` 验证 id 唯一性、名称存在性、能指有效性、
  关系端点与图关系端点。

## 4. 剩余缺口（后续增量）

- 商店**拓扑绑定**：目前已发布 1,659 条具名购买关系和 1,660 个具名卖家坐标
  终点；另有 845 条未解析购买关系被独立隔离。坐标尚未转换成正式路线锚点、楼层
  以及升降和转场边。

已关闭缺口（2026-08-20）：
- 拾取**位置**：3,552 个 lot 绑定到 3,894 个 MSB Treasure 实例（地图局部
  坐标，`pickup-location-bindings.json`）；每个拾取点成为图节点
  （`pickup_<lot>_<map>`），与物品节点建立 `pickup_at` 关系。
- **强化**：武器材料集（普通/失色）与官方等级→锻造石映射
  （`reinforce-catalog.json`，10,070 条关系），以及按所有者前缀分组的
  52 个防具套装。

### 2.5 玩家查询与拓扑桥接

玩家页面通过 `/api/catalog/player-entities` 查询 `player-entity-index.json`，不依赖路线数据包是否已经为该实体建立正式导航节点。因此，铃兰、锻造石、武器、防具、敌人和地点可以先独立搜索，再查看各自的获取关系。

`/api/catalog/player-entity-topology?id=<实体 id>` 只返回获取终点到拓扑层的明确绑定状态：`routeable_anchor` 表示可以进入路线规划；`semantic_endpoint` 表示已有语义终点但尚未接入路线；`coordinate_endpoint` 表示已有坐标但尚未绑定抽象锚点；`not_bound` 表示仍缺少具体终点。后面三种状态仍然可搜索、可查看，但不会被伪装成导航边。

已关闭缺口（2026-08-20）：灵泉（70 个，icon-83 启发式，标注
`icon_heuristic`）、车队（5 条 MSB 巡逻路线）、谜题（20 个特殊 ObjAct
交互）、暗门与传送机关（7 个 MSB ObjAct）——全部在 `gap-catalog.json`
中并已提升为图节点。

## 5. 构建管道

```bash
python scripts/build-entity-registry.py --param-dir <快照>/extracted/param-json
python scripts/build-merchant-shop-bindings.py --source <快照>/supporting/er-archipelago-merchant-shops.tsv
python scripts/build-acquisition-registry.py --param-dir <快照>/extracted/param-json --merchant-shops data/v1/entities/merchant-shop-bindings.json --enemy-spawns data/v1/entities/enemy-spawn-bindings.json --boss-endpoints data/v1/entities/boss-reward-endpoints.json
python scripts/build-location-catalog.py --param-dir <快照>/extracted/param-json
python scripts/build-boss-rewards.py --parsed-emevd ... --emedf ... --param-dir ...
python scripts/build-boss-reward-endpoints.py
python scripts/build-graph-integration.py
python scripts/build-player-entity-index.py
python scripts/audit-acquisition.py
python scripts/build-packages.py --graph data/v1/graph-v1.json
python scripts/audit-packages.py
```
