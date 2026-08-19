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
| `location-catalog.json` | 位置实例（来自 `WorldMapPointParam`：教堂、墓地、洞窟、城寨……） |
| `boss-rewards.json` | 从 EMEVD `AwardItemLot` 指令解码出的 Boss 奖励 lot |
| `msb-objact-catalog.json` | MSB 中的 825 个地图机关（宝箱/门/升降机/拉杆/隐藏房间） |
| `msb-message-regions.json` | MSB 中的 50 个游戏内留言区域（含坐标） |
| `graph-v1.json` | 正式可达性图 + 集成的 location/item/boss 节点与关系 |

### 2.1 entity-registry.json

`kind` 取值：`weapon`、`armor`、`accessory`、`ash_of_war`、`item`、
`spell`、`enemy`、`npc`、`location`。`category` 字段承载用户 10 大分类。

### 2.2 acquisition-registry.json

`method` 取值：`drop`（敌人 `itemLotId_enemy`）、`pickup`
（`ItemLotParam_map`）、`purchase`（`ShopLineupParam`）、`boss_reward`
（追忆/大卢恩映射）、`drops`（反向）。

lot 类别表（对照本地 regulation 转储验证）：`lotItemCategory` 1 = 道具
（Goods）、2 = 武器、3 = 防具、4 = 护符、5 = 战灰。

### 2.3 location-catalog.json

每个能解析出 `PlaceName` 的 `WorldMapPointParam` 行成为一个位置实体；
`iconId` 映射到位置类型。同名多实例（如三棵小黄金树）使用带后缀的 id。

### 2.4 boss-rewards.json

从全部 589 个地图事件文件中解码 `AwardItemLot` /
`Award Items (Including Clients)` 指令得出。含追忆的 lot 通过官方名称
映射解析到 Boss（`追忆：接肢` → `葛瑞克`）。

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

- 商店**商人绑定**：商店关系绑定到 `shop-<id>` 实体，尚未绑定到具名
  商人 NPC。

已关闭缺口（2026-08-20）：
- 拾取**位置**：3,552 个 lot 绑定到 3,894 个 MSB Treasure 实例（地图局部
  坐标，`pickup-location-bindings.json`）；每个拾取点成为图节点
  （`pickup_<lot>_<map>`），与物品节点建立 `pickup_at` 关系。
- **强化**：武器材料集（普通/失色）与官方等级→锻造石映射
  （`reinforce-catalog.json`，13,015 条关系），以及按所有者前缀分组的
  52 个防具套装。

已关闭缺口（2026-08-20）：灵泉（70 个，icon-83 启发式，标注
`icon_heuristic`）、车队（5 条 MSB 巡逻路线）、谜题（20 个特殊 ObjAct
交互）、暗门与传送机关（7 个 MSB ObjAct）——全部在 `gap-catalog.json`
中并已提升为图节点。

## 5. 构建管道

```bash
python scripts/build-entity-registry.py --param-dir <快照>/extracted/param-json
python scripts/build-acquisition-registry.py --param-dir <快照>/extracted/param-json
python scripts/build-location-catalog.py --param-dir <快照>/extracted/param-json
python scripts/build-boss-rewards.py --parsed-emevd ... --emedf ... --param-dir ...
python scripts/build-graph-integration.py
python scripts/audit-acquisition.py
python scripts/build-packages.py --graph data/v1/graph-v1.json
python scripts/audit-packages.py
```
