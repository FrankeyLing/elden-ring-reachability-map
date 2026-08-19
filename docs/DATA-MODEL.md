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
| `graph-v1.json` | formal reachability graph + integrated location/item/boss nodes and relations |

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

## 4. Known gaps (future increments)

- Pickup **locations**: the 5,011 pickup lots are not yet bound to MSB
  treasure instances (3,894 `Treasure` events found); the EMEVD treasure
  event chain still needs decoding.
- Shop **merchant binding**: shop relations are bound to `shop-<id>`
  entities, not yet to named NPC merchants.
- Spirit springs / caravans / puzzles: no WorldMapPointParam or MSB
  category has been mapped for these yet.
- Illusory walls and teleporters exist inside `msb-objact-catalog.json`
  (hidden rooms, warp traps) but are not yet promoted to graph nodes.

## 5. Build pipeline

```bash
python scripts/build-entity-registry.py --param-dir <snapshot>/extracted/param-json
python scripts/build-acquisition-registry.py --param-dir <snapshot>/extracted/param-json
python scripts/build-location-catalog.py --param-dir <snapshot>/extracted/param-json
python scripts/build-boss-rewards.py --parsed-emevd ... --emedf ... --param-dir ...
python scripts/build-graph-integration.py
python scripts/audit-acquisition.py
python scripts/build-packages.py --graph data/v1/graph-v1.json
python scripts/audit-packages.py
```
