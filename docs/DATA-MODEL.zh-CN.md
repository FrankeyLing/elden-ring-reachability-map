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

逻辑路径均位于 `data/v1/entities/`（正式图 `graph-v1.json` 位于 `data/v1/`）。其中生成型大型 JSON 是**发布专用输入**：本地构建可以保留副本，Git 源代码仓库不追踪；发布时由根目录 `release-data-manifest.json` 注入发布暂存树。

| 文件 | 内容 |
|---|---|
| `entity-registry.json` | 全部所指实体（物品/武器/防具/护符/战灰/法术/敌人/NPC/商店）及其全部能指 |
| `acquisition-registry.json`（发布专用） | 获取关系：掉落、拾取、商店、Boss 奖励、任务/事件证据和坐标终点；固定拾取保留复制的 MSB 位置实例 |
| `online-map-markers.json` | 带来源信息的公开互动地图标记规范化快照；只有精确名称匹配才进入坐标终点层 |
| `online-guide-items.json` | 公开物品指南来源记录的规范化快照；只有物品名称精确且唯一匹配才进入独立坐标获取终点层 |
| `online-item-map-records.json`（发布专用） | Map For Goblins 物品放置记录的规范化快照；只有物品名称精确且唯一匹配才进入独立游戏世界坐标终点层 |
| `online-cookbook-recipes.json` | 公开制作笔记解锁配方记录的规范化快照；只有产物和制作笔记都精确匹配才进入 `craft` 获取关系 |
| `merchant-shop-bindings.json` | 复制的对话脚本商店范围绑定：每个 `ShopLineupParam` 行、具名卖家、对话编号、地图实例和 XYZ 终点；未解析卖家也保留 |
| `shop-gap-catalog.json` | 每条未解析购买行的独立修复目录：物品、`ShopLineupParam` 行、隔离商店上下文、候选卖家证据和终点状态 |
| `location-catalog.json` | 位置实例（来自 `WorldMapPointParam`：教堂、墓地、洞窟、城寨……） |
| `boss-rewards.json` | 从 EMEVD `AwardItemLot` 指令解码出的 Boss 奖励 lot |
| `boss-reward-endpoints.json` | 独立的 Boss 奖励终点绑定：正式 Boss 门节点，以及可用时复制的本地 MSB 战斗坐标 |
| `event-reward-bindings.json` | 直接的 EMEVD 物品发放证据：事件、物品批次和引用的事件标记；任务或 NPC 归属明确保持未分类 |
| `quest-reward-bindings.json` | NPC 任务步骤绑定：区分本地奖励/事件标记交叉证据，以及单独标记的外部明确奖励名称证据 |
| `msb-objact-catalog.json` | MSB 中的 825 个地图机关（宝箱/门/升降机/拉杆/隐藏房间） |
| `msb-message-regions.json` | MSB 中的 50 个游戏内留言区域（含坐标） |
| `summon-endpoints.json` | 223 个多人召唤池事件与 102 个骨灰助战召唤区域，保留地图、事件/区域编号与游戏世界坐标 |
| `graph-v1.json`（发布专用） | 正式可达性图 + 集成的 location/item/boss 节点与关系 |
| `player-entity-index.json`（发布专用） | 玩家查询投影：规范实体、全部获取关系、固定留言与召唤终点、获取终点状态与拓扑锚点状态；独立于路线数据包 |
| `abstract-origin-bindings.json` | 独立的正式起点到抽象地图身份证据：精确人工起点、保留候选、歧义身份和未绑定记录 |

### 2.1 entity-registry.json

`kind` 取值：`weapon`、`armor`、`accessory`、`ash_of_war`、`item`、
`spell`、`enemy`、`npc`、`location`。`category` 字段承载用户 10 大分类。

武器不会因为装备族而复制成多个实体；每个实体仍保持唯一的 `weapon` 身份，
并在 `properties.weaponFamily` 中记录本地参数族：`melee`、`bow`、`crossbow`、
`ballista`、`staff`、`sacred_seal`、`shield`、`torch`、`hand_to_hand` 或 `perfume`。
`weaponFamilySet` 保留同一规范名称对应多个参数变体时的全部族信息。玩家查询投影
提供中英文族别别名，并支持 `family=shield` 过滤；这不会复制实体，也不会改变获取关系。

### 2.2 acquisition-registry.json

`method` 取值：`drop`（敌人 `itemLotId_enemy`）、`pickup`
（`ItemLotParam_map`）、`purchase`（`ShopLineupParam`）、`boss_reward`
（追忆/大卢恩映射）、`drops`（反向）。
`online_map` 表示独立的在线地图坐标证据；它不是本地参数证明，终点始终保持
`coordinate_endpoint`，不会被编译成正式路线节点。
`online_guide` 表示独立的公开物品指南坐标与获取说明层；`online_item_map` 表示
独立的 Map For Goblins 放置层及游戏世界坐标。两者都只发布坐标终点，不会创建
路线边。

每个终点还会从复制到工作目录的 `local-abstract-topology-graph.json` 获得独立的
地图证据绑定。`mapBindingStatus` 可为 `exact_map_instance`、
`exact_map_instance_alias`、`candidate_map_instance`、`external_map_scope`、
`unresolved_map_instance` 或 `unresolved_map_scope`。`mapNodeIds` 与
`nativeLayerNodeIds` 只标识本地地图实例和原生地图层，不是正式路线节点；原生地图层
是精确地图实例的子集，并保留来源 `mapStudioLayer` 身份。候选或未解析结果继续作为
证据保留，但不能进入路线规划。这一层只解决地图/楼层归属，不使用坐标近邻匹配、碰撞
模拟或伪造导航边。
`spell_acquisition` 把同名 Goods 获取事实投影到官方 `Magic` 实体；它保留
`sourceItemId`，并且只有英文名精确相同才会生成。
`craft` 表示“制作笔记事件标志解锁配方产物”的获取依赖：`from` 是规范制作笔记实体，
`items` 是规范制作产物实体。这是获取关系，不是可步行路线边。来源没有提供材料数量和产出数量
时，模型保留明确的未知状态，不根据产物名称臆造材料。

lot 类别表（对照本地 regulation 转储验证）：`lotItemCategory` 1 = 道具
（Goods）、2 = 武器、3 = 防具、4 = 护符、5 = 战灰。

商店行不能直接按 `ShopLineupParam` 的大段编号猜测商人。
`merchant-shop-bindings.json` 逐条记录“商店行—卖家—对话脚本—地图实例”的关系；
同一个行号由多个卖家出售时，`acquisition-registry.json` 会生成多条独立的
`purchase` 关系。具名卖家保留复制的 MSB 部件和 XYZ 坐标；空白卖家或本地参数中
没有对应外部行的数据，进入隔离的 `shop_context_<id>`，可以搜索但不会被冒充成
具名商人或正式路线边。

`shop-gap-catalog.json` 是上述未解析购买关系的投影，不是第二个事实源。
它对每条购买覆盖缺口保留一条仍处于 `open` 状态的记录，并保存关系编号、
物品证据、参数行、隔离商店上下文、候选绑定字段和终点状态。因此后续补证据
时可以只修复一条记录，不会影响其它已经正确的商店关系。没有证据的行保持
`open`，不得分配给相邻的具名商人。

### 2.3 location-catalog.json

每个能解析出 `PlaceName` 的 `WorldMapPointParam` 行成为一个位置实体；
`iconId` 映射到位置类型。同名多实例（如三棵小黄金树）使用带后缀的 id。

### 2.4 online-map-markers.json

这是公开静态互动地图标记的规范化快照，保留标记编号、地图主层、像素坐标、
说明、来源网址和抓取日期。获取编译器只发布与官方实体注册表英文名精确匹配的
标记。本快照共 1,861 个标记，发布其中 877 个；其余 984 个标记进入明确的
`coverageGaps`，并以 `sourceOnly=true` 的 `external_map_reference` 进入玩家查询，
不会被猜测成实体或路线节点。

编译器还发布 683 条 `spell_acquisition` 投影，使法术详情能直接显示游戏
背包 Goods 行中记录的商店/拾取证据。这是明确的实体身份桥接，不是第二张路线图，
也不是推测出来的法术位置。

### 2.5 online-guide-items.json

这是 Aether 公共物品指南的规范化快照。本次快照包含 2,437 条唯一来源物品，
其中 1,616 条拥有完整的指南地图坐标，覆盖 25 个来源分类。只有与玩家实体
注册表进行“英文名称精确且唯一匹配”的记录才会生成 `online_guide` 获取关系，
当前发布 1,118 条。其余 1,319 条没有地图终点、名称无法匹配或名称冲突的记录
会作为明确的 `coverageGaps` 保留，并以 `sourceOnly=true`、`formalEntity=false`
的 `external_item_reference` 进入玩家查询；它们不会被猜测成规范实体或拓扑节点。

每个已发布终点保留指南来源物品编号、地图层、标记编号、来源坐标空间
（`aether_map_lat_lng`）、获取说明、可选任务与错过提示以及来源 Wiki 地址。
它始终标记为 `coordinate_endpoint`，路线节点列表和语义节点列表为空。因此该
坐标可用于搜索和地图展示，但不会被静默转换成本地游戏 XYZ 坐标、碰撞结果或
正式导航边。

来源快照保存在仓库外，通过 `scripts/normalize-aether-guide-items.mjs` 复制为
仓库内的规范化产品数据。

### 2.6 online-item-map-records.json

这是固定版本 Map For Goblins 来源中的物品放置层规范化数据，包含 31,144 条来源
放置记录和 40,318 个物品出现记录。精确且唯一的官方英文名匹配，加上受来源
大类约束且唯一的本地参数编号匹配后，发布 28,759 条独立的 `online_item_map`
获取关系，覆盖 37,128 个物品出现记录：其中 33,289 条通过精确英文名匹配，
3,839 条通过 `sourceItemId` 与来源大类联合匹配。一个来源记录可能在同一个放置
点包含多个物品；这些物品保留为一条关系和一个终点，不丢失实际共点关系。

每个终点保留来源记录编号、地图标识、游戏世界坐标三元组、放置类型
（`treasure`、`enemy` 或事件相关类型）、数量、来源物品编号和来源提交版本。
每个物品还记录自身是通过官方英文名精确匹配，还是通过来源大类约束下的唯一本地
参数编号匹配。终点仍然是 `coordinate_endpoint`，路线节点列表和语义节点列表为空。
因此这些坐标是可用于搜索和获取展示的真实来源证据，不代表从任意赐福到该点已经
存在经过验证的拓扑路线。剩余 3,160 个未匹配和 30 个歧义物品出现记录仍留在来源
快照层，不会被静默丢弃。

这些记录不会被静默丢弃：剩余 3,160 个未匹配和 30 个歧义物品出现记录会作为
3,190 条 `coverageGaps` 发布；其中具有非空来源名称的 2,334 个出现记录进一步
聚合为玩家查询投影中的 241 条 `external_item_reference`。这些记录明确标记为
`sourceOnly` 且 `formalEntity=false`，因此它们是可搜索的来源证据和修复目标，
不是官方规范物品，也不是可参与路线规划的终点。

来源为 [ERR-MapForGoblins-DLL](https://github.com/Jovial-Nik/ERR-MapForGoblins-DLL)，
压缩来源分片先复制到仓库外工作快照，再由
`scripts/normalize-mapforgoblins-item-index.py` 规范化。

### 2.7 online-cookbook-recipes.json

这是由两个彼此独立的来源组成的配方层：固定版本 Smithbox 游戏玩法事件标志文档负责“哪个制作笔记
解锁哪个产物”，公开 Eldenpedia 制作笔记表只负责提供精确匹配后的产物数量和材料数量。本次快照包含
基础游戏制作笔记组的 127 个配方产物；127 个来源产物名和制作笔记名都匹配到规范玩家实体，因此生成
127 条 `craft` 关系。其中 124 条关系得到 340 条材料记录和产物数量；另外 3 条关系的材料层明确标记为
`source_pair_not_found`，但原有解锁关系仍保留。

每条关系从制作笔记指向制作产物，并保留来源事件标志编号、来源行号、来源拼写、规范实体编号以及验证
状态。`craftRecipe.ingredientSource` 记录独立公开来源和快照哈希；材料数据是配方内部数据，不会被伪造
成地点、路线或额外获取关系。无法匹配的材料只保留来源名称和未解析状态，不会影响其它节点和关系。

来源是 [Smithbox](https://github.com/vawser/Smithbox)，提交版本为
`dceac39472f5cc145d10fd9dfe28d2ea0cceb41a`。原始文本先复制到仓库外工作快照，再由
`scripts/normalize-smithbox-cookbook-recipes.py` 和
`scripts/enrich-smithbox-cookbook-ingredients.py` 规范化。材料来源是
[Eldenpedia Cookbook](https://eldenring.wiki.gg/wiki/Cookbook)，其原始文本同样复制到仓库外快照。

### 2.8 boss-rewards.json

从全部 589 个地图事件文件中解码 `AwardItemLot` /
`Award Items (Including Clients)` 指令得出。含追忆的 lot 通过官方名称
映射解析到 Boss（`追忆：接肢` → `葛瑞克`）。

`boss-reward-endpoints.json` 是独立的终点层：只把 `boss-identity-bindings.json`
中已有的 Boss 身份绑定到 `graph-v1.json` 的正式 Boss 门节点；如果复制的 MSB
中有对应战斗实体，则同时保留其地图坐标作为证据。本快照发布 20 个可路由 Boss
锚点，其中 17 个有本地战斗坐标。25 条 Boss 奖励关系中目前有 7 条匹配到终点，
其余关系仍可搜索，但明确标记为未绑定，不会阻断其它实体。

`event-reward-bindings.json` 当前记录 62 条直接事件发放绑定，保留 231 条
发放指令、其中 67 条是空物品批次，并且 62 条绑定具有事件标记证据。它们在
获取关系中使用 `event_reward`，而不是 `quest_reward`：同一事件系统同时处理
Boss、剧情、教程和系统发放；没有直接对话或交付绑定时，不能擅自声明某个 NPC
任务归属。

事件奖励同样遵循敌人掉落和地图拾取使用的连续 `ItemLotParam` 规则。
`itemLot.rowId` 是奖励根行，`sourceItemLotRows` 保留所有连续后继行，
每个发布的物品同时保留其实际来源 lot 行。这样多件套事件奖励可以独立搜索，
同时仍然属于同一个事件发放事实，并保留精确的本地来源链。

`quest-reward-bindings.json` 当前发布 104 条绑定。其中 14 条保留本地奖励
与事件标记交叉验证；另有 90 条明确标记为 `external_reference_only`：外部
任务步骤使用奖励语义并写出精确的官方物品名称，但尚未证明本地奖励指令与
事件标记交叉关系。这些较弱记录仍可搜索，并保留原始任务描述、NPC 解析状态
和数量未知状态；它们不会被冒充为本地 EMEVD 证据。未满足精确引号名称规则
的仅名称候选和仅标记候选仍不会进入获取关系，但会继续由生成器计数。

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

- 商店**拓扑绑定**：目前已发布 1,816 条具名购买关系和 1,817 个具名卖家坐标
  终点；另有 688 条未解析购买关系被独立隔离。坐标尚未转换成正式路线锚点、楼层
  以及升降和转场边。

已取得但尚未完成拓扑闭环的覆盖：
- 拾取**位置**：3,552 个 lot 绑定到 3,651 个 MSB Treasure 实例（地图局部
  坐标，`pickup-location-bindings.json`）；3,344 条获取关系有坐标终点，另有
  1,667 条局部缺口，缺口不会阻断其它关系。
- **强化**：武器材料集（普通/失色）与官方等级→锻造石映射
  （`reinforce-catalog.json`，10,070 条关系），以及按所有者前缀分组的
  52 个防具套装。

### 2.9 玩家查询与拓扑桥接

玩家页面通过 `/api/catalog/player-entities` 查询 `player-entity-index.json`，不依赖路线数据包是否已经为该实体建立正式导航节点。因此，铃兰、锻造石、武器、防具、敌人、地点和固定留言可以先独立搜索，再查看各自的获取关系或出现终点。

`msb-message-regions.json` 中的50条本地地图留言区域会进入玩家投影，成为稳定的 `message` 实体；每个实体保留一个 `fixed_message_endpoint` 出现终点、地图、区域编号和游戏世界坐标。源字段是地图内部区域名称，不声称等于玩家实际看到的完整留言文本。留言终点明确标记为 `coordinate_endpoint`，在正式拓扑锚点得到证明前不会进入路线规划。

`summon-endpoints.json` 来自仓库外的本地地图快照，分开记录两种真实终点：223 个 `SignPool` 多人召唤池事件，以及 102 个 `BuddySummonPoint` 骨灰助战召唤区域。每个终点保留地图文件、事件或区域编号、源名称、关联部件（如有）和游戏世界 XYZ 坐标，并作为独立的 `summon_endpoint` 实体进入玩家查询投影。多人召唤池使用 `multiplayer_summon_pool` 分类，骨灰召唤区域使用 `spirit_ash_summon_point` 分类；它们都明确标记为 `coordinate_endpoint`，不会因为存在坐标就伪造正式导航节点、路线边、友方角色身份或召唤目的地。

`/api/catalog/player-entity-topology?id=<实体 id>` 只返回获取终点到拓扑层的明确绑定状态：`routeable_anchor` 表示可以进入路线规划；`semantic_endpoint` 表示已有语义终点但尚未接入路线；`coordinate_endpoint` 表示已有坐标但尚未绑定抽象锚点；`not_bound` 表示仍缺少具体终点。后面三种状态仍然可搜索、可查看，但不会被伪装成导航边。

地图证据绑定与上述路线资格完全分离。本快照的获取关系终点中，66,893 个终点有
64,738 个绑定到精确本地地图实例，其中 32,231 个进一步绑定到精确原生地图层；
37 个保留多个本地地图候选，1,999 个只有外部地图范围，119 个仍未解析。审计会
把这些数字与 `acquisition-registry.json` 逐项对账。地图实例或地图层绑定只提供位面、
地图和楼层筛选的稳定锚点，不代表地图内部已经可达，也不会自动生成路线边。

`acquisition-topology-bridge.json` 是上述边界的规范化获取终点投影。
它包含 71,563 条可独立审计的终点记录：其中 66,893 条来自获取关系，
4,670 条来自保留的覆盖缺口。每条记录都有 `abstractAnchor` 状态，必要时
携带精确地图层身份，并独立记录 `nativeIdentity` 尝试和始终不可路由的
`formalRouteAnchor`。桥接只使用精确地图身份与部件身份，不会通过坐标邻近、
几何、实例顺序或名称相似度选择原生分区。根级 `mapIndex` 与
`evidenceCatalog` 用于消除重复地图摘要和来源证据，同时保持获取数据与路线图解耦。
其中 3,713 个本地拾取终点还通过精确的 `ItemLotParam_map` 批次编号与地图身份
绑定到已发布的拾取节点，并记录在 `semanticGraphAnchor` 中；这只是语义终点锚点，
不是可路由节点。

对于敌人、伪敌人、商人、任务角色和 Boss 奖励终点，`localPartSemanticAnchor`
只有在地图身份、部件名、实例编号、实体编号和地图层编号五项全部一致时才记录精确绑定。
当前共有 348 个精确部件语义锚点；没有对应本地抽象部件节点的终点仍然独立可搜索，不会被提升为路线。
此外，`localEndpointIdentity` 独立记录获取终点与已复制本地出生实例快照之间的
精确身份连接。当前有 32,231 条终点记录通过同样的五项身份字段连接到本地出生实例。
这只证明本地数据源中的实例身份，不代表抽象图部件，也不代表路线节点。因此其中
31,883 条虽然拥有精确本地实例身份、但尚未对应抽象图部件的记录，仍作为可搜索证据
保留，不会被静默丢弃或提升为路线；另有 195 条仍缺少一个或多个身份字段。

`abstract-topology-route-graph.json` 是独立的地图/楼层抽象拓扑轨迹包，包含 1,351 个地图节点、
1,347 个地图层节点和 2,097 条有向身份支持连接。它只通过
`/api/abstract-topology-route` 提供地图级拓扑证据查询，不进入正式玩家路线图，
也不宣称碰撞、导航网格或连续步行可达性。

玩家实体拓扑响应还提供 `abstractRouteEvidence`。它根据该实体获取端点已经
绑定的地图编号，从同一个独立包投影出关联地图、地图层、地图—地图层包含关系、
相邻地图编号和边计数；边明细最多返回 2,000 条，未进入该包的请求地图会保留在
`missingMapIds` 中。可选的抽象路线证据包缺失或损坏时，只有这个字段变为
`status=unavailable`；实体搜索、获取关系、桥接记录和正式路线锚点仍然可用。
其中 `abstractRouteable` 只表示存在抽象地图证据，`playerRouteable` 和
`routeable` 始终为 `false`。

`/api/catalog/player-entity-abstract-route?id=<实体 id>&from_map_id=<地图编号>`
完成下一步独立查询：从指定起始地图在抽象地图图中执行一次搜索，按目标地图
汇总精确获取终点，并返回可达、不可达以及不在抽象图中的目标地图状态；使用
`target_map_id` 可限定一个目标地图，`max_paths` 可限制返回的路径明细数量。
候选、外部、未解析和未绑定终点仍作为覆盖计数保留，不会被转换成精确路线。
每条返回路径都只是抽象拓扑证据，并始终保持 `playerRouteable=false` 与
`routeable=false`。

同一接口还接受 `from_node_id=<正式节点 id>`。它只通过
`abstract-origin-bindings.json` 解析正式起点：当前有 39 条记录同时具备精确
人工正式身份、精确本地赐福身份和精确抽象地图身份；376 条名称/地图候选、2 条
歧义记录和 2 条未绑定记录仍不是精确身份。候选正式节点会返回明确阻断原因，
不会静默选取其地图。这是起点身份投影，不会新增正式路线节点或路线边。

桥接提供独立接口：`/api/acquisition-topology-bridge`、
`/api/acquisition-topology-bridge/map?map_id=...`、
`/api/acquisition-topology-bridge/relation?relation_id=...`。玩家实体拓扑接口
返回精简桥接投影；完整获取终点记录不要求实体已经存在正式路线节点。当前审计结果为：
32,231 条精确抽象地图层锚点、32,507 条精确抽象地图锚点、37 条候选地图锚点、
1,999 条外部地图范围记录，以及 4,789 条未绑定或未解析记录。它们全部仍可查询，
任何一条记录缺失都不会使其它记录失效。

玩家投影根节点还提供 `entityAliases`。当旧路线节点身份与规范实体的官方名称形成
唯一精确匹配时，别名会把旧路线编号映射到唯一规范实体。本快照中
`item_bolt_of_gransax` 是 `weapon_bolt_of_gransax` 的路线别名；旧路线编号仍可查询，
但搜索结果只发布后者，避免同一所指被重复发布，也不需要改动现有路线包编号。

已关闭缺口（2026-08-20）：灵泉（70 个，icon-83 启发式，标注
`icon_heuristic`）、车队（5 条 MSB 巡逻路线）、谜题（20 个特殊 ObjAct
交互）、暗门与传送机关（7 个 MSB ObjAct）——全部在 `gap-catalog.json`
中并已提升为图节点。

## 5. 构建管道

```bash
python scripts/build-entity-registry.py --param-dir <快照>/extracted/param-json
python scripts/build-merchant-shop-bindings.py --source <快照>/supporting/er-archipelago-merchant-shops.tsv
python scripts/build-event-reward-bindings.py --parsed-emevd <快照>/extracted/parsed-emevd/files --semantic-references <快照>/extracted/parsed-emevd-semantic/references --emedf <工具>/event-defs/er-common.emedf.json --param-dir <快照>/extracted/param-json
python scripts/build-quest-reward-bindings.py --quest-source <快照>/supporting/oisis-elden-ring-saveforge-quests-v1.6.8.go
node scripts/normalize-online-map-markers.mjs --source <在线快照>/markers.js --out data/v1/entities/online-map-markers.json --source-url <在线来源网址> --retrieved-at <YYYY-MM-DD>
node scripts/normalize-aether-guide-items.mjs --source <仓库外快照>/items.json --out data/v1/entities/online-guide-items.json --source-url https://raw.githubusercontent.com/aether-auto/er-guide/main/data/items.json --retrieved-at <YYYY-MM-DD>
python scripts/normalize-mapforgoblins-item-index.py --source-dir <仓库外 Map For Goblins 快照> --out data/v1/entities/online-item-map-records.json --retrieved-at 2026-08-18
python scripts/build-acquisition-registry.py --param-dir <快照>/extracted/param-json --merchant-shops data/v1/entities/merchant-shop-bindings.json --enemy-spawns data/v1/entities/enemy-spawn-bindings.json --boss-endpoints data/v1/entities/boss-reward-endpoints.json --event-rewards data/v1/entities/event-reward-bindings.json --quest-rewards data/v1/entities/quest-reward-bindings.json --online-markers data/v1/entities/online-map-markers.json --online-guide-items data/v1/entities/online-guide-items.json --online-item-map data/v1/entities/online-item-map-records.json --online-cookbook-recipes data/v1/entities/online-cookbook-recipes.json --abstract-topology-graph data/v1/entities/local-abstract-topology-graph.json
python scripts/build-abstract-topology-candidates.py --input data/v1/entities/local-abstract-topology-graph.json --output data/v1/entities/abstract-topology-candidates.json
python scripts/audit-abstract-topology-candidates.py --input data/v1/entities/abstract-topology-candidates.json
python scripts/build-abstract-native-topology.py --native-input data/v1/entities/local-native-topology-graph.json --map-input data/v1/entities/local-abstract-topology-graph.json --output data/v1/entities/abstract-native-topology.json
python scripts/audit-abstract-native-topology.py --input data/v1/entities/abstract-native-topology.json
python scripts/build-acquisition-topology-bridge.py
python scripts/audit-acquisition-topology-bridge.py --input data/v1/entities/acquisition-topology-bridge.json --acquisitions data/v1/entities/acquisition-registry.json
python scripts/build-location-catalog.py --param-dir <快照>/extracted/param-json
python scripts/build-boss-rewards.py --parsed-emevd ... --emedf ... --param-dir ...
python scripts/build-boss-reward-endpoints.py
python scripts/build-graph-integration.py
python scripts/build-player-entity-index.py
python scripts/audit-acquisition.py
python scripts/build-packages.py --graph data/v1/graph-v1.json
python scripts/audit-packages.py
```
