# Acquisition Entity Data Model

This document describes the acquisition entity layer: how every item, weapon,
armor piece, spell, enemy, NPC and location instance of Elden Ring is
recorded once (the **signified**), how all references to it are attached
(the **signifiers**), and how "where does X come from" is answered
(the acquisition relations).

**Language**: English · [中文](DATA-MODEL.zh-CN.md)

## 1. Signified / Signifier model

The game data has many different identifiers for the same thing:

- a weapon appears as `EquipParamWeapon` rows (base row + affinity rows +
  upgrade rows), as a `WeaponName` FMG id, as `ItemLotParam` ids in drop
  tables, as `ShopLineupParam` ids in shops;
- a boss appears as several `NpcParam` rows (one per arena state), one or
  more `NpcName` entries (dialogue name and boss-battle name), achievement
  entries, and remembrance items that drop from it;
- a church appears as a `WorldMapPointParam` row, a `PlaceName` FMG id and
  (in the future) MSB map entities.

**Signified** — one canonical entity, recorded exactly once with a stable id:

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

**Signifier** — any reference form that points at the signified.  Every
`signifiers` entry carries its own namespace (`param` row ids, `fmg` name
ids, manual notes), so the same entity is found regardless of which source
the query comes from.

Two special cases the user called out:

1. **Many signifiers → one signified.** All affinity variants
   (`Heavy Dagger`, `Bandit's Keen Curved Sword`, ...) and upgrade rows of a
   weapon collapse into the single `weapon_dagger` entity; all `NpcParam`
   rows of a boss collapse into the single boss entity.
2. **One signifier → many signifieds.** A common item (e.g. `Smithing
   Stone [1]`) is one signified with many acquisition relations: dozens of
   enemies drop it, merchants sell it, it is picked up in several places.

## 2. Data files

Logical paths live under `data/v1/entities/` (`graph-v1.json` lives directly
under `data/v1/`). Generated large JSON is **release-only input**: local builds
may keep a copy, but the Git source repository does not track it. The root
`release-data-manifest.json` injects it into the release staging tree.

| file | content |
|---|---|
| `entity-registry.json` | every signified entity (items, weapons, armor, accessories, ashes of war, spells, enemies, NPCs, shops) with all signifiers |
| `acquisition-registry.json` (release-only) | acquisition relations: drops, pickups, shops, Boss rewards, quest/event evidence, and coordinate endpoints; fixed pickups retain copied MSB location instances |
| `online-map-markers.json` | normalized public interactive-map markers with source provenance; exact-name matches become coordinate-only endpoints |
| `online-guide-items.json` | normalized public item-guide records; exact unique item-name matches become independent coordinate acquisition endpoints |
| `online-item-map-records.json` (release-only) | normalized Map For Goblins item-placement records; exact unique item-name matches become independent game-world coordinate endpoints |
| `online-cookbook-recipes.json` | normalized public recipe-unlock records plus independently sourced material/output quantities; exact product and cookbook matches become `craft` relations |
| `location-catalog.json` | location instances from `WorldMapPointParam` (churches, catacombs, caves, castles, ...) |
| `boss-rewards.json` | boss reward lots decoded from EMEVD `AwardItemLot` instructions |
| `boss-reward-endpoints.json` | independent Boss reward-terminal bindings: formal Boss gate node plus copied local MSB encounter coordinates when available |
| `event-reward-bindings.json` | direct EMEVD item-award evidence with event, item-lot, and referenced event-flag data; quest or NPC identity remains explicitly unclassified |
| `quest-reward-bindings.json` | NPC quest-step bindings split into local-award/event-flag intersections and separately marked external named-reward references |
| `enemy-spawn-bindings.json` (release-only) | exact `Enemy` and `DummyEnemy` instances from the copied MSB map snapshot, keyed by `NpcParam` row and retaining map-local XYZ coordinates |
| `merchant-shop-bindings.json` | copied talk-range shop bindings: each `ShopLineupParam` row, named seller, talk id, map instance and XYZ endpoint, with unresolved seller records retained |
| `merchant-shop-semantic-aliases.json` | separately generated local-map semantic aliases for unnamed shop proxy entities; only exact model, parameter and map-scene evidence may resolve a seller |
| `shop-gap-catalog.json` | independently repairable catalog of every unresolved purchase row, including item, `ShopLineupParam` row, isolated shop context, candidate seller evidence and endpoint status |
| `msb-message-regions.json` | 50 fixed in-game message regions from the copied MSB maps, with map, region id and game-world coordinates |
| `summon-endpoints.json` | 223 multiplayer summon-pool events and 102 spirit-ash summon regions from the copied local map snapshot, with event/region identity and game-world coordinates |
| `graph-v1.json` (release-only) | formal reachability graph + integrated location/item/boss nodes and relations |
| `player-entity-index.json` (release-only) | player query projection: canonical entities, acquisition relations, fixed-message and summon occurrences, endpoint states and topology-anchor states; independent of route packages |
| `abstract-origin-bindings.json` | independent formal-origin-to-abstract-map identity evidence: exact manual origins, retained candidates, ambiguous identities and unbound records |

### 2.1 entity-registry.json

```json
{
  "schema": "errn-entity-registry@1",
  "entities": [ ... as above ... ]
}
```

`kind` values: `weapon`, `armor`, `accessory`, `ash_of_war`, `item`,
`spell`, `enemy`, `npc`, `location`.  The `category` field carries the user
taxonomy:

- locations: `church`, `catacomb`, `cave`, `tunnel`, `castle`, `fort`,
  `divine_tower`, `sorcerer_tower`, `minor_erdtree`, `evergaol`, `gaol`,
  `mausoleum`, `well`, `ruins`, `village`, `town`, `landmark`, ...
- items: `consumable`, `key_item`, `remembrance`, `great_rune`,
  `spirit_ash`, `bell_bearing`, `map_fragment`, `smithing_stone`,
  `grave_glovewort`, `ghost_glovewort`, `golden_rune`, `crystal_tear`, `jar`,
  `multiplayer_item`, ...
- spells: `sorcery`, `incantation`, `sorcery_and_incantation`
- enemies: `boss`, `elite`, `invader`, `furnace_golem`, `merchant`, `npc`

Weapons keep one canonical `weapon` entity identity and expose the local
parameter family in `properties.weaponFamily`: `melee`, `bow`, `crossbow`,
`ballista`, `staff`, `sacred_seal`, `shield`, `torch`, `hand_to_hand`, or
`perfume`. `weaponFamilySet` preserves all families when one canonical name
is shared by parameter variants. The player query projection adds the Chinese
and English family aliases and supports `family=shield`-style filtering; this
does not duplicate entities or alter acquisition relations.

### 2.2 acquisition-registry.json

```json
{
  "id": "drop-20108500-lot300014010",
  "from": "enemy_baleful_shadow",
  "method": "drop",
  "lot": {"param": "ItemLotParam_enemy", "rowId": 300014010},
  "items": [ {"item": "item_smithing_stone_1", "name": {...}, "num": 1} ],
  "sourceNpcParamRows": [20108500],
  "sourceItemLotRows": [300014010],
  "endpointInstances": [
    {"map": "m10_00_00_00.msb.dcx", "part": "c2010_9000",
     "npcParamId": 20108500, "position": {"x": 1.0, "y": 2.0, "z": 3.0},
     "topologyBinding": {
       "status": "coordinate_endpoint",
       "mapBindingStatus": "exact_map_instance",
       "mapNodeIds": ["local_map_m10_00_00_00"],
       "nativeLayerNodeIds": []
     }}
  ],
  "evidence": [...],
  "verification": "local_param_verified"
}
```

`method` values: `drop` (enemy `itemLotId_enemy`), `pickup`
(`ItemLotParam_map`), `purchase` (`ShopLineupParam`), `boss_reward`
(remembrance / great rune mapping), `drops` (inverse direction).
`online_map` is a separate online-coordinate evidence method. It does not
claim local parameter proof and its endpoint remains `coordinate_endpoint`.
`online_guide` is the independent public item-guide coordinate and acquisition
text layer; `online_item_map` is the independent Map For Goblins placement layer
with game-world coordinates. Both methods remain coordinate-only and never
create route edges.

Every endpoint also receives an independent map-evidence binding from the
copied `local-abstract-topology-graph.json`. `mapBindingStatus` can be
`exact_map_instance`, `exact_map_instance_alias`, `candidate_map_instance`,
`external_map_scope`, `unresolved_map_instance`, or `unresolved_map_scope`.
`mapNodeIds` and `nativeLayerNodeIds` identify local map/layer records only;
they are not formal route nodes. An exact native layer is a subset of an exact
map-instance match and preserves the source `mapStudioLayer` identity. A
candidate or unresolved result is retained as evidence and cannot enter route
planning. This layer provides map/layer containment without coordinate-nearest
matching, collision simulation, or fabricated navigation edges.
`spell_acquisition` projects a Goods acquisition fact onto the same-name
official `Magic` entity; it keeps the Goods id in `sourceItemId` and requires
an exact English-name match.
`craft` represents a cookbook event-flag unlock of a recipe product. Its
`from` field is the canonical cookbook item and its `items` field contains the
canonical craft product. This is an acquisition dependency, not a walkable
route edge. When the public cookbook table has an exact product and cookbook
match, `craftRecipe.productQuantity` and `craftRecipe.ingredients` contain the
published output and material quantities. Each ingredient retains its source
name, canonical item id, quantity, and resolution status. A pair that is not
found in the material source remains explicitly missing and never changes the
unlock relation.

Fixed `pickup` relations retain the regulation lot and, when the independent
pickup-location snapshot has a valid MSB placement, one or more
`pickup_endpoint` instances with map, part, game-world coordinates and an
explicit coordinate-only topology status. Their exact local map instance and,
when present, exact native map layer are recorded separately in the map-evidence
binding. Missing coordinates remain an explicit pickup status and do not remove
the acquisition relation.

The lot category table (verified against the local regulation dump) maps
`lotItemCategory` to the item table: 1 = Goods, 2 = Weapon, 3 = Protector,
4 = Accessory, 5 = Gem.

Enemy drop coverage is intentionally split into three independent facts:
`sourceNpcParamRows` identifies the regulation rows that declare the drop.
`sourceItemLotRows` identifies the complete sequential enemy-lot chain used by
that declaration. `NpcParam.itemLotId_enemy` points to the chain root; the
following consecutive `ItemLotParam_enemy` rows are retained as separate item
signifiers instead of being silently discarded. The chain stops before the
next directly referenced root or at the first missing row. This preserves the
actual row-level provenance without turning an unreferenced lot into a guessed
drop source.

`endpointInstances` identifies each exact local map spawn that uses those rows;
`topologyBinding` states whether that endpoint is already attached to a formal
route node. A coordinate endpoint is searchable and displayable, but it is not
silently promoted to a navigable graph edge. Unnamed ordinary enemies are
retained under an explicit unresolved behavior-variation entity rather than
being discarded.

The registry also publishes `coverageGaps` for referenced enemy-lot roots that
cannot produce an item relation. `source_lot_missing`, `source_lot_empty`, and
`item_name_unresolved` are separate statuses. The corresponding counts in
`stats` reconcile the 1,376 referenced roots, 1,210 roots with resolved item
names, 1,215 emitted relations, and 166 isolated source gaps. These gaps are
not treated as successful drops and do not affect unrelated acquisition
relations.

Map pickups use the same sequential-lot rule. A `Treasure` event binds its
position to the chain root; the root pickup relation publishes every
continuation row in `sourceItemLotRows`, so a multi-piece armor set or a
multi-item chest remains one physical endpoint with several independent item
signifiers. Continuation relations remain searchable but are not given a
second guessed position. The sequential-row interpretation is recorded in
the generated provenance as the public ItemLotParam semantics reference:
<https://soulsmodding.wikidot.com/param:itemlotparam>.

Unresolved fixed-pickup locations are also published as independent
`coverageGaps`. `no_external_location_binding` means that the local pickup
relation has no copied Treasure-location binding; `source_record_without_coordinates`
means a Treasure record exists but contains no valid game-world coordinate. These
statuses do not invalidate the item relation and are never filled by copying
an online item marker, because an online marker does not prove the exact
ItemLot-to-Treasure identity.

Shop rows follow the same independent-fact rule. The raw `ShopLineupParam`
row is not treated as a merchant identity: `merchant-shop-bindings.json`
records every known `(row, seller, talk script, map instance)` binding. A
single row can therefore produce several `purchase` relations, one per seller
and physical endpoint. Named endpoints retain the copied MSB part and XYZ
coordinates when the local snapshot matches; blank seller records and rows
not present in the copied source become `unresolved` relations attached to an
isolated `shop_context_<id>` entity. They remain searchable and cannot become
formal route edges. Every unresolved purchase relation is also present in
`coverageGaps`: `seller_unresolved_no_external_binding` means the copied
external source has no seller binding for the row;
`seller_unresolved_candidate_binding` means a seller/map candidate exists but
has no verified seller identity while a named seller relation exists for the
same lineup row. A local semantic alias may resolve a proxy only when its
exact map-scene evidence is published in `merchant-shop-semantic-aliases.json`;
the alias is marked separately from an external seller name. This keeps the
repair queue explicit without converting a candidate into false acquisition
data.

`shop-gap-catalog.json` is a projection of these unresolved purchase relations,
not a second source of truth. It has exactly one open record per purchase
coverage gap and preserves the relation id, item evidence, parameter row,
isolated shop context, candidate binding fields and endpoint status. Repairing
one record can therefore add one seller or endpoint without changing unrelated
shop relations. Rows without evidence remain `open`; they are not assigned to
the nearest named seller.

### 2.3 location-catalog.json

Every `WorldMapPointParam` row with a resolvable `PlaceName` becomes a
location entity; the `iconId` maps to a location type:

```json
{
  "id": "location_stormveil_castle",
  "kind": "location",
  "category": "castle",
  "name": {"en": "Stormveil Castle", "zh": "史东薇尔城"},
  "properties": {"iconId": 50, "position": {...}, "areaNo": ...}
}
```

Multiple instances with the same name (e.g. the three `Minor Erdtree`s)
receive suffixed ids (`location_minor_erdtree_1` ...).

`GestureParam` rows are additional signifiers of the corresponding
`EquipParamGoods` entity. The 54 named gesture entities in this snapshot are
classified as `gesture` and retain their action parameters; 52 also retain
the linked goods parameter, while two are verified `GoodsName`-only actions.
The two remaining gesture parameter rows have no official display name in the
copied name tables and remain excluded from the named player projection.

### 2.4 fixed-message occurrences

`msb-message-regions.json` contains 50 fixed message regions extracted from the
copied local MSB maps. Each row becomes one `message` entity in the player
projection with a stable map/region/entity id and one `fixed_message_endpoint`
occurrence. The source name is retained as an internal map-region name; it is
not asserted to be the full player-visible message text. The occurrence keeps
the map, region id, game-world coordinates and `coordinate_endpoint` status.
It is searchable under `留言` and remains independent of the navigation graph
until a formal topology anchor is proven.

### 2.4a summon-endpoints.json

`summon-endpoints.json` is extracted from the copied local map snapshot. It
publishes two distinct endpoint classes without conflating them:

- 223 `SignPool` events represent multiplayer summon-pool interaction points.
- 102 `BuddySummonPoint` regions represent spirit-ash summon activation areas.

Each endpoint retains its map file, event or region id, source map name,
referenced asset where present, and game-world XYZ coordinates. The player
projection exposes each endpoint as an independent `summon_endpoint` entity
with one occurrence and either `multiplayer_summon_pool` or
`spirit_ash_summon_point` category. Every occurrence is explicitly marked
`coordinate_endpoint`; no route edge, formal navigation anchor, NPC identity,
or destination is fabricated from the summon marker alone. This keeps the
endpoint searchable and useful while isolating the still-unresolved identity
and topology work.

### 2.5 online-map-markers.json

This is a normalized snapshot of the public static marker source used for the
online coordinate layer. It preserves marker id, map master, pixel position,
description, source URL, and retrieval date. The acquisition compiler publishes
only exact English-name matches to the official entity registry. In the current
snapshot, 877 of 1,861 markers are published; the remaining 984 markers are
explicit `coverageGaps` and searchable `external_map_reference` records with
`sourceOnly=true`, rather than guessed entities or route nodes.

The compiler also publishes 683 `spell_acquisition` projections so a spell
detail page exposes local purchase/pickup evidence that is stored in the game's
Goods inventory rows. This is an explicit identity bridge, not a second route
graph and not an inferred spell location.

### 2.6 online-guide-items.json

This is a normalized snapshot of Aether's public item guide. The current
snapshot contains 2,437 unique source items, 1,616 source items with a complete
guide-map coordinate, and 25 source categories. The compiler publishes 1,118
`online_guide` relations after requiring an exact, unique English-name match
against the player entity registry. The remaining 1,319 records stay in the
source layer as explicit `coverageGaps` when they have no map endpoint, an
unmatched name, or an ambiguous name; they are also searchable as
`external_item_reference` records with `sourceOnly=true` and
`formalEntity=false`.

Each published endpoint retains the guide source item id, map layer, marker id,
source coordinate space (`aether_map_lat_lng`), acquisition text, optional quest
and missable notes, and the source wiki URL. It is always marked
`coordinate_endpoint` with empty route-node and semantic-node lists. The guide
coordinate is therefore useful for search and map display, but is not silently
converted to a local game XYZ coordinate, a collision result, or a formal
navigation edge.

The snapshot source is kept outside the repository and copied into this
normalized product layer by `scripts/normalize-aether-guide-items.mjs`.

### 2.7 online-item-map-records.json

This is the normalized item-placement layer from the pinned Map For Goblins
source snapshot. It contains 31,144 source placement records and 40,318 item
occurrences. Exact unique name matches plus unique local parameter-number
matches publish 28,759 independent `online_item_map` relations covering
37,128 item occurrences: 33,289 by exact English name and 3,839 by
`sourceItemId` constrained to the source broad category. A source record can
contain several items at one placement; those items remain one relation and one
endpoint so the physical co-location is not lost.

Each endpoint retains the source record index, map identifier, game-world
coordinate triplet, placement type (`treasure`, `enemy`, or event-related
types), quantity, source item identifier and source commit. Each item records
whether it matched by exact official English name or by a unique local
parameter-number match guarded by the source broad category. The endpoint is
still `coordinate_endpoint` with no route-node or semantic-node binding. The
coordinates are therefore real source coordinate evidence for search and
acquisition display, not a claim that the item can be reached from any chosen
grace without a separately verified topology route. The remaining 3,160
unmatched and 30 ambiguous item occurrences remain outside acquisition
relations and are not silently discarded from the source snapshot. They are
published as 3,190 `coverageGaps`; the 2,334 occurrences with non-empty source
names additionally form 241 `external_item_reference` records in the player
query projection. These records are explicitly `sourceOnly` and
`formalEntity=false`, so they are searchable evidence and repair targets, not
official canonical items or routeable endpoints.

The source is [ERR-MapForGoblins-DLL](https://github.com/Jovial-Nik/ERR-MapForGoblins-DLL)
and the compressed source chunks are copied to an external working snapshot
before normalization by `scripts/normalize-mapforgoblins-item-index.py`.

### 2.8 online-cookbook-recipes.json

This is the normalized recipe layer assembled from two independent sources.
The pinned Smithbox gameplay event-flag documentation supplies the unlock
dependency. The public Eldenpedia cookbook table supplies recipe output and
material quantities only after an exact product-and-cookbook match. The
snapshot contains 127 recipe products across the base-game cookbook groups;
all 127 source products and cookbook names match one canonical player entity,
producing 127 `craft` relations. 124 of those relations have 340 material rows
and output quantities from the public table. Three relations retain an
explicit `source_pair_not_found` status for the material layer.

Each relation points from the cookbook item to the craft product and retains
the source event-flag id, source line, source spellings, canonical ids, and
verification status. `craftRecipe.ingredientSource` records the independent
public source and its snapshot hash. The material layer is nested recipe data,
not a fabricated location or route edge; unresolved or absent material rows do
not remove the product relation.

The source is [Smithbox](https://github.com/vawser/Smithbox), commit
`dceac39472f5cc145d10fd9dfe28d2ea0cceb41a`, and the raw text is copied to an
external working snapshot before normalization by
`scripts/normalize-smithbox-cookbook-recipes.py`.

### 2.9 boss-rewards.json

Decoded from EMEVD `AwardItemLot` / `Award Items (Including Clients)`
instructions across all 589 map event files.  Remembrance lots resolve to
the boss via the official name mapping (`Remembrance of the Grafted` →
`Godrick the Grafted`).

`boss-reward-endpoints.json` is a separate endpoint layer. It binds only the
Boss identities already present in `boss-identity-bindings.json` to formal Boss
gate nodes in `graph-v1.json`; a copied MSB encounter coordinate is retained as
evidence when available. The current snapshot publishes 20 routeable Boss
anchors, 17 with local encounter coordinates. Only 7 of the 25 Boss reward
relations currently have a matching endpoint; the remaining reward relations
stay searchable and explicitly unbound.

`event-reward-bindings.json` records 62 direct local event-award bindings. The
current snapshot retains 231 award instructions, 67 zero-lot instructions, and
62 bindings with event-flag evidence. These records are intentionally exposed
as `event_reward`, not `quest_reward`: the same event system also grants boss,
story, tutorial, and system items, so assigning an NPC quest without a direct
talk or delivery binding would be an unsupported claim.

Event awards use the same sequential `ItemLotParam` rule as enemy drops and map
pickups. `itemLot.rowId` is the award root, `sourceItemLotRows` preserves every
consecutive continuation row, and each published item retains its originating
lot row. This keeps multi-piece event rewards independently searchable while
preserving one event-award fact and its exact local provenance.

`quest-reward-bindings.json` currently publishes 104 bindings. Fourteen retain
the stronger local-award plus event-flag intersection, while 90 are explicitly
marked `external_reference_only`: the external quest step names an exact
official item and uses reward language, but no local award/event-flag join was
proven. The weaker records remain searchable and keep their source description,
NPC resolution status, and quantity-unknown status; they are never presented as
local EMEVD proof. Name-only and flag-only candidates that do not satisfy the
exact quoted-name rule remain omitted from acquisition relations and are still
counted by the builder.

The acquisition projection additionally copies 594 local NPC instances into
these 104 relations as `quest_npc_endpoint` records. They are coordinate
evidence from the local MSB spawn catalog, not formal route nodes: each one is
explicitly `coordinate_endpoint` with empty route and semantic node lists. A
future topology pass may bind an instance to a formal node independently; a
missing or unresolved NPC endpoint must not remove the quest reward relation.

### 2.10 player query and topology bridge

The player page queries `player-entity-index.json` through
`/api/catalog/player-entities`. This projection is independent from route
packages, so an entity remains searchable while its route anchor is missing.
`/api/catalog/player-entity-topology?id=<entity id>` reports each acquisition
endpoint as `routeable_anchor`, `semantic_endpoint`, `coordinate_endpoint`, or
`not_bound`. Only `routeable_anchor` is eligible for route planning; the other
states remain visible data and never become fabricated navigation edges.

The endpoint-to-map evidence layer is separate from that route decision. In
the current snapshot it binds 64,738 of 66,893 acquisition endpoints to an
exact local map instance; 32,231 of those also have an exact native map-layer
record. A further 37 endpoints retain multiple local-map candidates, 1,999
are intentionally limited to an external map scope, and 119 remain locally
unresolved. These counts are audited against `acquisition-registry.json`.
Map-instance or map-layer binding improves floor/plane filtering and gives the
next topology pass a stable anchor, but it does not claim intra-map reachability
or create a route edge.

`acquisition-topology-bridge.json` is the normalized endpoint projection for
this boundary. It contains 71,563 independently auditable endpoint records:
66,893 acquisition-relation endpoints plus 4,670 endpoints retained from
coverage gaps. Each record has an `abstractAnchor` status, an optional exact
map-layer identity, a separately audited `nativeIdentity` attempt, and a
`formalRouteAnchor` field that is always non-routeable in this package. The
bridge uses only exact map/part identity; it never chooses a native partition
by coordinate proximity, geometry, instance order, or name similarity. The
root `mapIndex` and `evidenceCatalog` normalize repeated summaries and
provenance without coupling the acquisition records to the route graph.
For the 3,713 local pickup endpoints, `semanticGraphAnchor` additionally
records an exact `ItemLotParam_map` plus map identity match to a published
pickup node; this is a semantic endpoint anchor, not a routeable node.
For local enemy, dummy-enemy, merchant, quest-NPC, and boss-reward endpoints,
`localPartSemanticAnchor` records an exact match against the copied local
abstract graph only when map id, part name, instance id, entity id, and
map-studio layer all match. The current package has 348 such exact anchors;
unmatched endpoints remain independent searchable records and do not become
routes.
Separately, `localEndpointIdentity` joins 32,231 complete endpoint records to
an exact copied local MSB spawn-instance identity using the same five fields.
This is a local source identity, not an abstract graph part and not a route
node. Therefore the 31,883 records that have this exact local identity but no
matching abstract graph part remain searchable evidence rather than being
silently discarded or promoted to routes; 195 records still lack one or more
identity fields.

The bridge is exposed independently through
`/api/acquisition-topology-bridge`,
`/api/acquisition-topology-bridge/map?map_id=...`, and
`/api/acquisition-topology-bridge/relation?relation_id=...`. The player entity
topology response includes a compact bridge projection, while the full
acquisition endpoint records remain available without requiring a formal route
node. Current bridge audit counts are: 32,231 exact abstract-layer anchors,
32,507 exact abstract-map anchors, 37 candidate map anchors, 1,999 external
map-scope records, and 4,789 unbound or unresolved records. All remain
searchable and none can invalidate another record.

`abstract-topology-route-graph.json` is a separate map/layer topology trace
package. It contains 1,351 map nodes, 1,347 layer nodes, and 2,097 directed
identity-backed abstract connection edges. Its edges are eligible only for
map-level topology evidence queries through `/api/abstract-topology-route`;
the package explicitly remains outside the formal player route graph and does
not claim collision, navigation-mesh, or continuous walkability.

The player-entity topology response also exposes `abstractRouteEvidence`. This
is a bounded incident-edge projection of the same package for the map ids
attached to that entity's acquisition endpoints. It returns matching maps,
layers, map-layer memberships, adjacent map ids, and edge counts; edge details
are capped at 2,000 records and `missingMapIds` preserves requested map ids not
present in the package. A malformed or missing optional route-evidence package
only changes this field to `status=unavailable`; entity search, acquisition
relations, bridge records, and formal route anchors remain usable. Its
`abstractRouteable` flag only means that abstract map evidence exists;
`playerRouteable` and `routeable` remain false.

`/api/catalog/player-entity-abstract-route?id=<entity id>&from_map_id=<map id>`
performs the next independent query step: it searches the abstract map graph
once from the supplied origin map, groups exact acquisition endpoints by
target map, and returns reachable, unreachable, and out-of-graph target-map
statuses. `target_map_id` narrows the result to one target map; `max_paths`
limits returned path details. Candidate, external, unresolved, and unbound
endpoints remain coverage counts and are never converted into exact routes.
Every returned path is abstract topology evidence only and keeps
`playerRouteable=false` and `routeable=false`.

The same endpoint accepts `from_node_id=<formal node id>`. It resolves the
formal origin only through `abstract-origin-bindings.json`: 39 current records
have exact manual formal identity plus exact local grace identity and abstract
map identity; 376 name/map candidates, 2 ambiguous records, and 2 unbound
records remain non-exact. A candidate formal node returns an explicit blocker
instead of silently choosing its map. This is an origin identity projection,
not a new formal route node or edge.

The player projection also exposes an `entityAliases` object at the payload
root. It maps a legacy route-node identity to one canonical searchable entity
when an exact official-name match is unique. In this snapshot
`item_bolt_of_gransax` is an alias of `weapon_bolt_of_gransax`; the former route
node remains queryable, but only the latter is published as the searchable
entity. This prevents duplicate signified objects without renumbering existing
route packages.

## 3. Provenance and verification

- Params come from the local `regulation.bin` snapshot (decrypted with the
  EldenRing key, DCX-decompressed, BND4-parsed, decoded with the Paramdex
  XML definitions).  Every row carries its param table and row id as a
  signifier — nothing is inferred from a third-party dump.
- Names come exclusively from the official bilingual FMG index
  (`official-fmg-bilingual-index.json`); no invented translations.
- Name-id formulas were verified against the local data (e.g. weapon name
  id == row id for the majority, legacy rows use ×100/×1000, a few 90M rows
  use ÷10).
- `scripts/audit-acquisition.py` verifies id uniqueness, name presence,
  signifier validity, relation endpoints and graph relation endpoints.

## 4. Remaining gaps (future increments)

- Shop **topology binding**: 1,816 named purchase relations and 1,817 named
  seller-coordinate endpoints are published from the copied talk-range and
  local-map join. The 157 previously unnamed `c4450` proxy endpoints are now
  explicitly identified as Wandering Mausoleum Corpse through the separately
  published semantic alias evidence. 688 unresolved purchase relations remain
  isolated: 554 rows have no external binding and 134 rows have only a
  candidate sharing a lineup row with a named seller. The coordinates are not
  yet converted into formal route anchors or floor and transition edges.
- Enemy spawn **topology binding**: 1,215 enemy-drop relations and 29,516
  coordinate instances are available, but their map-local coordinates are not
  yet converted into formal route anchors or floor-transition edges. The
  remaining 166 referenced lot roots are retained in `coverageGaps` as
  independently repairable source gaps rather than being counted as drops.

Pickup **location coverage** is partial rather than closed: the copied source
contains 3,552 lot bindings and 3,651 Treasure instances; 3,344 pickup
relations currently have coordinate endpoints, while 1,667 remain isolated
repair gaps (1,655 with no external location binding and 12 without valid
coordinates). Coordinate endpoints remain searchable acquisition evidence and
are not formal route anchors until an abstract topology bridge is proven.
- **Reinforcement**: weapon material sets (normal vs somber) and the
  official level->stone mapping (`reinforce-catalog.json`, 10,070
  relations) plus 52 armor sets grouped by owner prefix.

Closed gaps (2026-08-20): spirit springs (70, icon-83 heuristic, labelled
`icon_heuristic`), caravans (5 MSB patrol routes), puzzles (20 special
ObjAct interactions), hidden passages and teleporters (7 MSB ObjAct) — all
in `gap-catalog.json` and promoted to graph nodes.

## 5. Build pipeline

```bash
python scripts/build-entity-registry.py --param-dir <snapshot>/extracted/param-json
python scripts/build-enemy-spawn-bindings.py --map-root <snapshot>/extracted/parsed-mapstudio-all-extra2/maps
python scripts/build-event-reward-bindings.py --parsed-emevd <snapshot>/extracted/parsed-emevd/files --semantic-references <snapshot>/extracted/parsed-emevd-semantic/references --emedf <tools>/event-defs/er-common.emedf.json --param-dir <snapshot>/extracted/param-json
python scripts/build-quest-reward-bindings.py --quest-source <snapshot>/supporting/oisis-elden-ring-saveforge-quests-v1.6.8.go
python scripts/build-merchant-shop-semantic-aliases.py --msb-dir <snapshot>/extracted/parsed-mapstudio-all-v2/maps --merchant-source <snapshot>/supporting/er-archipelago-merchant-shops.tsv
python scripts/build-merchant-shop-bindings.py --source <snapshot>/supporting/er-archipelago-merchant-shops.tsv
node scripts/normalize-online-map-markers.mjs --source <online-snapshot>/markers.js --out data/v1/entities/online-map-markers.json --source-url <online-source-url> --retrieved-at <YYYY-MM-DD>
node scripts/normalize-aether-guide-items.mjs --source <external-snapshot>/items.json --out data/v1/entities/online-guide-items.json --source-url https://raw.githubusercontent.com/aether-auto/er-guide/main/data/items.json --retrieved-at <YYYY-MM-DD>
python scripts/normalize-mapforgoblins-item-index.py --source-dir <external-mapforgoblins-snapshot> --out data/v1/entities/online-item-map-records.json --retrieved-at 2026-08-18
python scripts/normalize-smithbox-cookbook-recipes.py --source <external-smithbox-snapshot>/Documentation/ER/Info\ -\ Event\ Flags\ -\ Gameplay.txt --out data/v1/entities/online-cookbook-recipes.json --source-url https://github.com/vawser/Smithbox --source-commit dceac39472f5cc145d10fd9dfe28d2ea0cceb41a --retrieved-at 2026-08-21
python scripts/enrich-smithbox-cookbook-ingredients.py --recipes data/v1/entities/online-cookbook-recipes.json --source <external-eldenpedia-snapshot>/cookbook-eldenpedia.md --entity-registry data/v1/entities/entity-registry.json --out data/v1/entities/online-cookbook-recipes.json --source-url https://eldenring.wiki.gg/wiki/Cookbook --retrieval-url https://r.jina.ai/https://eldenring.wiki.gg/wiki/Cookbook --retrieved-at 2026-08-21
python scripts/build-acquisition-registry.py --param-dir <snapshot>/extracted/param-json --enemy-spawns data/v1/entities/enemy-spawn-bindings.json --merchant-shops data/v1/entities/merchant-shop-bindings.json --boss-endpoints data/v1/entities/boss-reward-endpoints.json --event-rewards data/v1/entities/event-reward-bindings.json --quest-rewards data/v1/entities/quest-reward-bindings.json --online-markers data/v1/entities/online-map-markers.json --online-guide-items data/v1/entities/online-guide-items.json --online-item-map data/v1/entities/online-item-map-records.json --online-cookbook-recipes data/v1/entities/online-cookbook-recipes.json --abstract-topology-graph data/v1/entities/local-abstract-topology-graph.json
python scripts/build-abstract-topology-candidates.py --input data/v1/entities/local-abstract-topology-graph.json --output data/v1/entities/abstract-topology-candidates.json
python scripts/audit-abstract-topology-candidates.py --input data/v1/entities/abstract-topology-candidates.json
python scripts/build-abstract-native-topology.py --native-input data/v1/entities/local-native-topology-graph.json --map-input data/v1/entities/local-abstract-topology-graph.json --output data/v1/entities/abstract-native-topology.json
python scripts/audit-abstract-native-topology.py --input data/v1/entities/abstract-native-topology.json
python scripts/build-acquisition-topology-bridge.py
python scripts/audit-acquisition-topology-bridge.py --input data/v1/entities/acquisition-topology-bridge.json --acquisitions data/v1/entities/acquisition-registry.json
python scripts/build-location-catalog.py --param-dir <snapshot>/extracted/param-json
python scripts/build-boss-rewards.py --parsed-emevd ... --emedf ... --param-dir ...
python scripts/build-boss-reward-endpoints.py
python scripts/build-graph-integration.py
python scripts/build-player-entity-index.py
python scripts/audit-acquisition.py
python scripts/build-packages.py --graph data/v1/graph-v1.json
python scripts/audit-packages.py
```
