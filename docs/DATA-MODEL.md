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

All files live under `data/v1/entities/`:

| file | content |
|---|---|
| `entity-registry.json` | every signified entity (items, weapons, armor, accessories, ashes of war, spells, enemies, NPCs, shops) with all signifiers |
| `acquisition-registry.json` | acquisition relations: drops, pickups, shops, boss rewards |
| `location-catalog.json` | location instances from `WorldMapPointParam` (churches, catacombs, caves, castles, ...) |
| `boss-rewards.json` | boss reward lots decoded from EMEVD `AwardItemLot` instructions |
| `boss-reward-endpoints.json` | independent Boss reward-terminal bindings: formal Boss gate node plus copied local MSB encounter coordinates when available |
| `event-reward-bindings.json` | direct EMEVD item-award evidence with event, item-lot, and referenced event-flag data; quest or NPC identity remains explicitly unclassified |
| `enemy-spawn-bindings.json` | exact `Enemy` and `DummyEnemy` instances from the copied MSB map snapshot, keyed by `NpcParam` row and retaining map-local XYZ coordinates |
| `merchant-shop-bindings.json` | copied talk-range shop bindings: each `ShopLineupParam` row, named seller, talk id, map instance and XYZ endpoint, with unresolved seller records retained |
| `graph-v1.json` | formal reachability graph + integrated location/item/boss nodes and relations |
| `player-entity-index.json` | player query projection: canonical entities, acquisition relations, endpoint states and topology-anchor states; independent of route packages |

### 2.1 entity-registry.json

```json
{
  "schema": "errn-entity-registry@1",
  "entities": [ ... as above ... ]
}
```

`kind` values: `weapon`, `armor`, `accessory`, `ash_of_war`, `item`,
`spell`, `enemy`, `npc`, `location`.  The `category` field carries the user
taxonomy (10 categories):

- locations: `church`, `catacomb`, `cave`, `tunnel`, `castle`, `fort`,
  `divine_tower`, `sorcerer_tower`, `minor_erdtree`, `evergaol`, `gaol`,
  `mausoleum`, `well`, `ruins`, `village`, `town`, `landmark`, ...
- items: `consumable`, `key_item`, `remembrance`, `great_rune`,
  `spirit_ash`, `bell_bearing`, `map_fragment`, `smithing_stone`,
  `grave_glovewort`, `golden_rune`, `crystal_tear`, `jar`, `multiplayer_item`, ...
- spells: `sorcery`, `incantation`, `sorcery_and_incantation`
- enemies: `boss`, `elite`, `invader`, `furnace_golem`, `merchant`, `npc`

### 2.2 acquisition-registry.json

```json
{
  "id": "drop-20108500-lot300014010",
  "from": "enemy_baleful_shadow",
  "method": "drop",
  "lot": {"param": "ItemLotParam_enemy", "rowId": 300014010},
  "items": [ {"item": "item_smithing_stone_1", "name": {...}, "num": 1} ],
  "sourceNpcParamRows": [20108500],
  "endpointInstances": [
    {"map": "m10_00_00_00.msb.dcx", "part": "c2010_9000",
     "npcParamId": 20108500, "position": {"x": 1.0, "y": 2.0, "z": 3.0},
     "topologyBinding": {"status": "coordinate_endpoint"}}
  ],
  "evidence": [...],
  "verification": "local_param_verified"
}
```

`method` values: `drop` (enemy `itemLotId_enemy`), `pickup`
(`ItemLotParam_map`), `purchase` (`ShopLineupParam`), `boss_reward`
(remembrance / great rune mapping), `drops` (inverse direction).

The lot category table (verified against the local regulation dump) maps
`lotItemCategory` to the item table: 1 = Goods, 2 = Weapon, 3 = Protector,
4 = Accessory, 5 = Gem.

Enemy drop coverage is intentionally split into three independent facts:
`sourceNpcParamRows` identifies the regulation rows that declare the drop;
`endpointInstances` identifies each exact local map spawn that uses those rows;
`topologyBinding` states whether that endpoint is already attached to a formal
route node. A coordinate endpoint is searchable and displayable, but it is not
silently promoted to a navigable graph edge. Unnamed ordinary enemies are
retained under an explicit unresolved behavior-variation entity rather than

Shop rows follow the same independent-fact rule. The raw `ShopLineupParam`
row is not treated as a merchant identity: `merchant-shop-bindings.json`
records every known `(row, seller, talk script, map instance)` binding. A
single row can therefore produce several `purchase` relations, one per seller
and physical endpoint. Named endpoints retain the copied MSB part and XYZ
coordinates when the local snapshot matches; blank seller records and rows
not present in the copied source become `unresolved` relations attached to an
isolated `shop_context_<id>` entity. They remain searchable and cannot become
formal route edges.

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

### 2.4 boss-rewards.json

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

### 2.5 player query and topology bridge

The player page queries `player-entity-index.json` through
`/api/catalog/player-entities`. This projection is independent from route
packages, so an entity remains searchable while its route anchor is missing.
`/api/catalog/player-entity-topology?id=<entity id>` reports each acquisition
endpoint as `routeable_anchor`, `semantic_endpoint`, `coordinate_endpoint`, or
`not_bound`. Only `routeable_anchor` is eligible for route planning; the other
states remain visible data and never become fabricated navigation edges.

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

- Shop **topology binding**: 1,659 named purchase relations and 1,660 named
  seller-coordinate endpoints are published from the copied talk-range/MSB
  join; 845 unresolved purchase relations remain explicitly isolated. The
  coordinates are not yet converted into formal route anchors or floor and
  transition edges.
- Enemy spawn **topology binding**: 1,215 enemy-drop relations and 29,516
  coordinate instances are available, but their map-local coordinates are not
  yet converted into formal route anchors or floor-transition edges.

Closed gaps (2026-08-20):
- Pickup **locations**: 3,552 lots bound to 3,894 MSB Treasure instances
  with map-local coordinates (`pickup-location-bindings.json`); each pickup
  became a graph node (`pickup_<lot>_<map>`) with `pickup_at` relations to
  the item node.
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
python scripts/build-acquisition-registry.py --param-dir <snapshot>/extracted/param-json --enemy-spawns data/v1/entities/enemy-spawn-bindings.json --merchant-shops data/v1/entities/merchant-shop-bindings.json --boss-endpoints data/v1/entities/boss-reward-endpoints.json --event-rewards data/v1/entities/event-reward-bindings.json
python scripts/build-location-catalog.py --param-dir <snapshot>/extracted/param-json
python scripts/build-boss-rewards.py --parsed-emevd ... --emedf ... --param-dir ...
python scripts/build-boss-reward-endpoints.py
python scripts/build-graph-integration.py
python scripts/build-player-entity-index.py
python scripts/audit-acquisition.py
python scripts/build-packages.py --graph data/v1/graph-v1.json
python scripts/audit-packages.py
```
