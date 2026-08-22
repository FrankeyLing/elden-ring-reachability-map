#!/usr/bin/env python3
"""Build the acquisition registry: enemy/npc/location entities plus
acquisition relations (drops, pickups, shops, remembrance exchanges).

Reads the entity registry produced by build-entity-registry.py, adds
enemy/npc entities from NpcParam (nameId -> NpcName), location entities from
WorldMapPointParam, and acquisition relations from:
  - NpcParam.itemLotId_enemy  -> ItemLotParam_enemy   (enemy drops)
  - ItemLotParam_map                                  (map pickups)
  - ShopLineupParam                                   (shops)
  - achievements.json                                 (boss identification)

Usage:
    python scripts/build-acquisition-registry.py \
        --param-dir <snapshot>/extracted/param-json \
        --registry data/v1/entities/entity-registry.json \
        --out data/v1/entities/acquisition-registry.json
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from topology_map_binding import enrich_relations, load_map_index

ROOT = Path(__file__).resolve().parent.parent
FMG_INDEX = ROOT / "data" / "v1" / "entities" / "official-fmg-bilingual-index.json"
ACHIEVEMENTS = ROOT / "data" / "v1" / "entities" / "achievements.json"
DEFAULT_ENEMY_SPAWNS = ROOT / "data" / "v1" / "entities" / "enemy-spawn-bindings.json"
DEFAULT_MERCHANT_SHOPS = ROOT / "data" / "v1" / "entities" / "merchant-shop-bindings.json"
DEFAULT_BOSS_ENDPOINTS = ROOT / "data" / "v1" / "entities" / "boss-reward-endpoints.json"
DEFAULT_EVENT_REWARDS = ROOT / "data" / "v1" / "entities" / "event-reward-bindings.json"
DEFAULT_TALK_ITEM_LOTS = ROOT / "data" / "v1" / "entities" / "talk-item-lot-bindings.json"
DEFAULT_QUEST_REWARDS = ROOT / "data" / "v1" / "entities" / "quest-reward-bindings.json"
DEFAULT_GESTURE_ACQUISITIONS = ROOT / "data" / "v1" / "entities" / "gesture-acquisition-bindings.json"
DEFAULT_TUTORIAL_UNLOCKS = ROOT / "data" / "v1" / "entities" / "tutorial-unlock-bindings.json"
DEFAULT_ONLINE_MARKERS = ROOT / "data" / "v1" / "entities" / "online-map-markers.json"
DEFAULT_ONLINE_GUIDE_ITEMS = ROOT / "data" / "v1" / "entities" / "online-guide-items.json"
DEFAULT_ONLINE_ITEM_MAP = ROOT / "data" / "v1" / "entities" / "online-item-map-records.json"
DEFAULT_ONLINE_COOKBOOK_RECIPES = ROOT / "data" / "v1" / "entities" / "online-cookbook-recipes.json"
DEFAULT_PICKUP_BINDINGS = ROOT / "data" / "v1" / "entities" / "pickup-location-bindings.json"
DEFAULT_ABSTRACT_TOPOLOGY_GRAPH = ROOT / "data" / "v1" / "entities" / "local-abstract-topology-graph.json"
LOT_CHAIN_REFERENCE = "https://soulsmodding.wikidot.com/param:itemlotparam"

_suffix_re = re.compile(r"(_dlc0[12])?\.fmg$")

# ITEMLOT_ITEMCATEGORY (verified against the local regulation dump):
# 1=Goods, 2=Weapon, 3=Protector, 4=Accessory, 5=Gem
LOT_CATEGORY_TABLES = {
    1: "GoodsName",
    2: "WeaponName",
    3: "ProtectorName",
    4: "AccessoryName",
    5: "GemName",
}
LOT_CATEGORY_KIND = {
    1: "item", 2: "weapon", 3: "armor", 4: "accessory", 5: "ash_of_war",
}
FMG_TO_PARAM = {
    "GoodsName": "EquipParamGoods",
    "WeaponName": "EquipParamWeapon",
    "ProtectorName": "EquipParamProtector",
    "AccessoryName": "EquipParamAccessory",
    "GemName": "EquipParamGem",
}

# ShopLineupParam equipType (verified against the local regulation dump and the
# corresponding EquipParam tables): 0=Weapon, 1=Protector, 2=Accessory,
# 3=Goods, 4=Gem, 5=EquipParamCustomWeapon.  A custom-weapon row is a concrete
# preset (base weapon + reinforcement level + attached gem); it must resolve
# back to the canonical base weapon instead of masquerading as a Gem item.
SHOP_EQUIP_TABLES = {
    0: "WeaponName",
    1: "ProtectorName",
    2: "AccessoryName",
    3: "GoodsName",
    4: "GemName",
}
SHOP_EQUIP_KIND = {
    0: "weapon", 1: "armor", 2: "accessory", 3: "item", 4: "ash_of_war",
}

# Map For Goblins carries a source item number, but its normalized record does
# not carry the original EquipParam table name.  The broad category is the
# available type guard.  A source number is accepted only when it resolves to
# one canonical entity after this guard; unknown categories never use a raw
# number because EquipParam row ids are not globally unique across tables.
ONLINE_ITEM_MAP_EXPECTED_KINDS = {
    "consumable": {"item"},
    "crafting_material": {"item"},
    "key_item": {"item"},
    "tool": {"item"},
    "armament": {"weapon"},
    "ranged_weapon": {"weapon"},
    "magic_catalyst": {"weapon"},
    "shield": {"weapon"},
    "armour": {"armor"},
    "talisman": {"accessory"},
    "ash_of_war": {"ash_of_war"},
    "spirit_ash": {"item"},
    "incantation": {"spell"},
    "sorcery": {"spell"},
}

# Weapon affinity names are separate FMG signifiers but the entity registry
# intentionally stores the underlying weapon once.  Acquisition rows retain
# the original name as ``sourceName`` and point at that canonical weapon.
WEAPON_AFFIXES = (
    "Flame Art", "Lightning", "Sacred", "Magic", "Cold", "Poison",
    "Blood", "Occult", "Quality", "Heavy", "Keen", "Fire", "Standard",
)


def slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def canonicalize_acquisition_items(relations: list[dict], entities: list[dict]) -> list[dict]:
    """Resolve acquisition signifiers to canonical entity ids.

    Loot and shop parameters may name an affinity variant, an altered armor
    variant, or an official goods name that has no EquipParam row in this
    snapshot.  The player must see one signified entity, while the raw
    signifier remains auditable.  Unbound official names therefore become
    explicit supplemental entities instead of anonymous search records.
    """
    entity_by_id = {e["id"]: e for e in entities}
    by_kind_name: dict[tuple[str, str], list[str]] = {}
    by_param_row: dict[tuple[str, int], list[str]] = {}
    for entity in entities:
        name = entity.get("name", {}).get("en")
        if name:
            by_kind_name.setdefault((entity.get("kind"), name.casefold()), []).append(entity["id"])
        for signifier in entity.get("signifiers", []):
            param = signifier.get("param")
            if not param:
                continue
            for row_id in signifier.get("rows", []):
                by_param_row.setdefault((str(param), int(row_id)), []).append(entity["id"])

    kind_by_prefix = {
        "weapon": "weapon", "armor": "armor", "accessory": "accessory",
        "ash": "ash_of_war", "ash_of_war": "ash_of_war", "item": "item",
    }
    supplemental: dict[str, dict] = {}

    def candidates(name: str, kind: str | None) -> list[str]:
        if not kind:
            return []
        return by_kind_name.get((kind, name.casefold()), [])

    def resolve(item: dict) -> tuple[str, str | None, str | None]:
        raw_id = item["item"]
        name = (item.get("name") or {}).get("en") or ""
        source_param = item.get("sourceParam")
        source_param_id = item.get("sourceParamId")
        if source_param and isinstance(source_param_id, int):
            param_candidates = by_param_row.get((str(source_param), source_param_id), [])
            if len(param_candidates) == 1:
                target_id = param_candidates[0]
                target = entity_by_id[target_id]
                target_name = (target.get("name") or {}).get("en") or ""
                if target.get("kind") == "weapon":
                    for affix in WEAPON_AFFIXES:
                        if name == f"{affix} {target_name}":
                            return target_id, affix, None
                if target.get("kind") == "armor" and name == f"{target_name} (Altered)":
                    return target_id, "altered", None
                level_match = re.fullmatch(rf"{re.escape(target_name)} \+(\d+)", name)
                if level_match:
                    return target_id, f"reinforcement_level_{level_match.group(1)}", None
                return target_id, None, None
        if raw_id in entity_by_id:
            return raw_id, None, None
        prefix = raw_id.split("_", 1)[0]
        kind = kind_by_prefix.get(prefix)

        # The game has one typo in the local bilingual source.  Resolve it to
        # the official entity while retaining the source spelling below.
        aliases = {"Glinstone Scrap": "Glintstone Scrap"}
        normalized_name = aliases.get(name, name)

        direct = candidates(normalized_name, kind)
        if len(direct) == 1:
            return direct[0], None, normalized_name if normalized_name != name else None

        # Reinforcement levels are variants of one canonical goods entity.
        # Some external acquisition snapshots expose a level suffix even
        # though the player-facing catalog intentionally stores the base
        # Spirit Ash only once.
        level_match = re.match(r"^(.*?) \+(\d+)$", normalized_name)
        if level_match:
            base_name = level_match.group(1)
            direct = candidates(base_name, kind or "item")
            if len(direct) == 1:
                return direct[0], f"reinforcement_level_{level_match.group(2)}", None

        if kind == "armor" and normalized_name.endswith(" (Altered)"):
            base_name = normalized_name[: -len(" (Altered)")]
            direct = candidates(base_name, "armor")
            if len(direct) == 1:
                return direct[0], "altered", None

        if kind == "weapon":
            for affix in WEAPON_AFFIXES:
                token = affix + " "
                if normalized_name.startswith(token):
                    base_name = normalized_name[len(token):]
                    direct = candidates(base_name, "weapon")
                    if len(direct) == 1:
                        return direct[0], affix, None

        # A category collision can make the raw prefix wrong (old shop rows
        # are the common case).  Prefer an exact official name in the
        # canonical item/equipment categories before creating a supplemental
        # entity.
        for fallback_kind in ("item", "weapon", "armor", "accessory", "ash_of_war", "spell"):
            direct = candidates(normalized_name, fallback_kind)
            if len(direct) == 1:
                return direct[0], None, normalized_name if normalized_name != name else None

        # Some arrows and bolts are affinity-like names whose base is present
        # as a weapon even when the source prefix says otherwise.
        if kind == "weapon":
            for affix in WEAPON_AFFIXES:
                token = affix + " "
                if normalized_name.startswith(token):
                    base_name = normalized_name[len(token):]
                    for fallback_kind in ("weapon", "item"):
                        direct = candidates(base_name, fallback_kind)
                        if len(direct) == 1:
                            return direct[0], affix, None

        return raw_id, None, normalized_name if normalized_name != name else None

    for relation in relations:
        for item in relation.get("items", []):
            raw_id = item.get("item")
            name = (item.get("name") or {}).get("en")
            if not raw_id or not name:
                continue
            resolved, variant, corrected_name = resolve(item)
            if resolved != raw_id:
                item["sourceItemId"] = raw_id
                item["sourceName"] = name
                item["item"] = resolved
                if variant:
                    item["variant"] = variant
                if corrected_name:
                    item["name"] = {**item["name"], "en": corrected_name}
                continue

            if raw_id in entity_by_id:
                continue
            # Keep an unresolved official acquisition target searchable as a
            # first-class data record.  It is explicitly marked unbound so a
            # later source can enrich it without changing the framework.
            supplemental.setdefault(raw_id, {
                "id": raw_id,
                "kind": kind_by_prefix.get(raw_id.split("_", 1)[0], "item"),
                "category": "consumable" if raw_id.startswith("item_") else "unbound",
                "class": None,
                "name": item["name"],
                "signifiers": [{
                    "type": "acquisition_name",
                    "relation": relation["id"],
                    "rawItemId": raw_id,
                }],
                "properties": {"topologyStatus": "not_bound"},
                "variant_count": 1,
            })

    entities.extend(supplemental.values())
    return relations

# Boss names from the official achievement list (category == "boss")
BOSS_ACHIEVEMENT_NAMES = [
    "Ancestor Spirit", "Astel, Naturalborn of the Void", "Commander Niall",
    "Dragonkin Soldier of Nokstella", "Dragonlord Placidusax", "Elemer of the Briar",
    "Fire Giant", "Godfrey, First Elden Lord", "Godrick the Grafted",
    "Hoarah Loux, Warrior", "Lichdragon Fortissax", "Malenia, Blade of Miquella",
    "Maliketh, the Black Blade", "Margit, the Fell Omen", "Mimic Tear",
    "Mohg, Lord of Blood", "Morgott, the Omen King", "Radagon of the Golden Order",
    "Radahn, Starscourge", "Regal Ancestor Spirit", "Rennala, Queen of the Full Moon",
    "Rykard, Lord of Blasphemy", "Sir Gideon Ofnir, the All-Knowing",
    "Starscourge Radahn", "Godskin Duo", "Mohg, the Omen", "Elden Beast",
    "God-Devouring Serpent", "Leonine Misbegotten", "Bell Bearing Hunter",
    "Soldier of Godrick", "Night's Cavalry", "Erdtree Burial Watchdog",
    "Grave Warden Duelist", "Mad Pumpkin Head", "Magma Wyrm Makar",
    "Miranda the Blighted Bloom", "Onyx Lord", "Red Wolf of Radagon",
    "Stonedigger Troll", "Tibia Mariner", "Fallingstar Beast",
]


def load_name_tables() -> dict[str, dict[int, dict[str, str]]]:
    tables: dict[str, dict[int, dict[str, str]]] = {}
    with open(FMG_INDEX, encoding="utf-8") as fh:
        recs = json.load(fh)["records"]
    for rec in recs:
        lang = rec["language"]
        if lang not in ("engus", "zhocn"):
            continue
        fmg_name = _suffix_re.sub("", rec["fmg"].replace("\\", "/").split("/")[-1])
        entry = tables.setdefault(fmg_name, {}).setdefault(rec["id"], {})
        entry["en" if lang == "engus" else "zh"] = rec["text"]
    return tables


def clean_name(text: str | None) -> str | None:
    if not text or text in ("[ERROR]", ""):
        return None
    if text.startswith("[ERROR]"):
        text = text[len("[ERROR]"):].strip()
    return text or None


def name_for(tables, fmg_id: int, candidates) -> dict | None:
    for fmg in candidates:
        entry = tables.get(fmg, {}).get(fmg_id)
        if entry and clean_name(entry.get("en")):
            return entry
    return None


def param_rows(param_dir: Path, name: str) -> list[dict[str, Any]]:
    path = param_dir / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"param dump missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))["rows"]


# ---------------------------------------------------------------------------
# Enemy / NPC entities
# ---------------------------------------------------------------------------

NPC_FRIENDLY_HINTS = [
    "melina", "ranni", "renna", "blaidd", "gurranq", "tanith", "latenna",
    "enia", "sellen", "hewg", "roderika", "fia", "rogier", "thops", "miriel",
    "patches", "alexander", "boc", "millicent", "gowry", "seluvis", "iji",
    "dung eater", "goldmask", "corhyn", "d,", "diallos", "jarburg", "nepheli",
    "kenneth", "gostoc", "hyetta", "irina", "edgar", "yura", "shabriri",
    "rodrika", "knight jerren", "sorceress sellen", "finger reader", "finger maiden",
    "the two fingers", "smith", "merchant", "kale", "boc the seamster",
    "millicent", "gowry", "diallos", "nepheli", "kenneth", "gostoc", "hyetta",
    "irina", "edgar", "yura", "shabriri", "corhyn", "goldmask", "varre",
    "white-faced varre", "fia", "d,", "roderika", "hunter of the dead",
]

ENEMY_CLASS_RULES = [
    ("furnace_golem", re.compile(r"Furnace Golem", re.I)),
    ("invader", re.compile(r"Invader|Bloody Finger|Recusant", re.I)),
    ("merchant", re.compile(r"Merchant|Nomadic Merchant", re.I)),
    ("boss", re.compile(r"^(?:" + "|".join(re.escape(n) for n in BOSS_ACHIEVEMENT_NAMES) + r")$", re.I)),
    ("elite", re.compile(r"Knight$|^Knight |Soldier|Warrior|Guardian|Golem|Dragon|Giant|Troll|Omen|Misbegotten", re.I)),
]


def build_enemies_npcs(npc_rows: list[dict], tables) -> tuple[list[dict], dict[int, str]]:
    """Named enemy/npc entities from the full NpcName table.

    NpcParam rows carry a small nameId (dialogue names); boss-battle names
    exist only in the large-id NpcName entries.  Both are signifiers of one
    entity keyed by the official English name.  Returns
    (entities, {npc_param_row: entity_id}).
    """
    entities: dict[str, dict] = {}
    row_to_entity: dict[int, str] = {}

    def ensure(en: str, zh: str | None, nid: int | None, r: dict | None) -> dict:
        eid = None
        ent = entities.get(en)
        if ent is None:
            low = en.lower()
            kind = "npc" if any(h in low for h in NPC_FRIENDLY_HINTS) else "enemy"
            category = None
            for cat, pattern in ENEMY_CLASS_RULES:
                if pattern.search(en):
                    category = cat
                    break
            if kind == "npc" and category is None:
                category = "npc"
            ent = {
                "id": f"{kind}_{slugify(en)}",
                "kind": kind,
                "category": category or ("npc" if kind == "npc" else "enemy"),
                "class": None,
                "name": {"en": en, "zh": zh or en},
                "signifiers": [
                    {"type": "param", "param": "NpcParam", "rows": []},
                    {"type": "fmg", "fmg": "NpcName", "ids": []},
                ],
                "properties": {},
                "variant_count": 0,
            }
            entities[en] = ent
        if nid is not None and nid not in ent["signifiers"][1]["ids"]:
            ent["signifiers"][1]["ids"].append(nid)
        if r is not None:
            ent["signifiers"][0]["rows"].append(r["id"])
            ent["variant_count"] += 1
            ent["properties"].setdefault("npcType", r["cells"].get("npcType"))
            ent["properties"].setdefault("dropItemLotEnemy", r["cells"].get("itemLotId_enemy"))
            ent["properties"].setdefault("dropItemLotMap", r["cells"].get("itemLotId_map"))
        return ent

    # pass 1: NpcParam rows via nameId
    for r in npc_rows:
        nid = r["cells"].get("nameId")
        if not nid or nid <= 0:
            continue
        entry = tables.get("NpcName", {}).get(nid)
        en = clean_name((entry or {}).get("en"))
        if not en:
            continue
        ent = ensure(en, clean_name((entry or {}).get("zh")), nid, r)
        row_to_entity[r["id"]] = ent["id"]

    # pass 2: every other NpcName entry (boss-battle names, etc.)
    for nid, entry in tables.get("NpcName", {}).items():
        en = clean_name(entry.get("en"))
        if not en:
            continue
        ensure(en, clean_name(entry.get("zh")), nid, None)

    # pass 3: unnamed NpcParam rows that still carry a real enemy drop lot.
    # Ordinary enemies do not necessarily have an NpcName FMG entry.  Group
    # them by the stable behavior-variation identity so their drop sources are
    # retained without pretending that a guessed English name is authoritative.
    fallback_by_behavior: dict[int, dict] = {}
    for r in npc_rows:
        cells = r["cells"]
        lot_id = cells.get("itemLotId_enemy", -1)
        if lot_id is None or lot_id <= 0 or r["id"] in row_to_entity:
            continue
        behavior_id = cells.get("behaviorVariationId") or 0
        fallback_key = behavior_id if behavior_id > 0 else r["id"]
        ent = fallback_by_behavior.get(fallback_key)
        if ent is None:
            label = (
                f"Enemy behavior variation {fallback_key}"
                if behavior_id > 0
                else f"Enemy parameter {r['id']}"
            )
            ent = {
                "id": f"enemy_unresolved_{fallback_key}",
                "kind": "enemy",
                "category": "enemy",
                "class": None,
                "name": {"en": label, "zh": f"未命名敌人参数 {fallback_key}"},
                "signifiers": [{
                    "type": "param",
                    "param": "NpcParam",
                    "rows": [],
                    "identityStatus": "unresolved",
                }],
                "properties": {
                    "identityStatus": "unresolved",
                    "behaviorVariationId": behavior_id if behavior_id > 0 else None,
                },
                "variant_count": 0,
            }
            fallback_by_behavior[fallback_key] = ent
            entities[ent["name"]["en"]] = ent
        ent["signifiers"][0]["rows"].append(r["id"])
        ent["variant_count"] += 1
        ent["properties"].setdefault("dropItemLotEnemy", lot_id)
        row_to_entity[r["id"]] = ent["id"]

    return sorted(entities.values(), key=lambda e: e["id"]), row_to_entity


# ---------------------------------------------------------------------------
# Acquisitions
# ---------------------------------------------------------------------------

def expand_enemy_lot_chain(
    root_lot_id: int,
    lot_by_id: dict[int, dict],
    referenced_lot_ids: set[int],
) -> list[int]:
    """Expand the sequential ItemLotParam_enemy rows for one NpcParam root.

    In this parameter family the NpcParam row points at the first row of an
    enemy loot chain.  Consecutive rows after that root are additional loot
    records and are not separately referenced by NpcParam.  A new directly
    referenced row starts the next chain, so it is a hard boundary even when
    the numeric ids are consecutive.
    """
    chain: list[int] = []
    lot_id = root_lot_id
    while lot_id in lot_by_id:
        if lot_id != root_lot_id and lot_id in referenced_lot_ids:
            break
        chain.append(lot_id)
        lot_id += 1
    return chain


def build_drops(npc_rows: list[dict], row_to_entity: dict[int, str],
                lot_rows: list[dict], tables) -> list[dict]:
    """Enemy drops: NpcParam root -> sequential ItemLotParam_enemy rows."""
    lot_by_id = {r["id"]: r["cells"] for r in lot_rows}
    referenced_lot_ids = {
        r["cells"].get("itemLotId_enemy")
        for r in npc_rows
        if isinstance(r["cells"].get("itemLotId_enemy"), int)
        and r["cells"].get("itemLotId_enemy") > 0
    }
    relations = []
    for r in npc_rows:
        rid = r["id"]
        eid = row_to_entity.get(rid)
        if not eid:
            continue
        lot_id = r["cells"].get("itemLotId_enemy")
        if not lot_id:
            continue
        chain_ids = expand_enemy_lot_chain(
            lot_id, lot_by_id, referenced_lot_ids
        )
        if not chain_ids:
            continue
        items = []
        for chain_lot_id in chain_ids:
            lot = lot_by_id[chain_lot_id]
            for k in range(1, 9):
                iid = lot.get(f"lotItemId{k:02d}")
                cat = lot.get(f"lotItemCategory{k:02d}")
                if not iid or iid <= 0:
                    continue
                fmg = LOT_CATEGORY_TABLES.get(cat, "GoodsName")
                entry = tables.get(fmg, {}).get(iid)
                en = clean_name((entry or {}).get("en"))
                if not en:
                    continue
                items.append({
                    "item": f"{LOT_CATEGORY_KIND.get(cat, 'item')}_{slugify(en)}",
                    "name": {"en": en, "zh": clean_name((entry or {}).get("zh")) or en},
                    "lot": chain_lot_id,
                    "slot": k,
                    "num": lot.get(f"lotItemNum{k:02d}"),
                    "rate": lot.get(f"lotItemBasePoint{k:02d}"),
                    "sourceParam": FMG_TO_PARAM[fmg],
                    "sourceParamId": iid,
                    "sourceItemCategory": cat,
                })
        if items:
            relations.append({
                "id": f"drop-{rid}-lot{lot_id}",
                "from": eid,
                "method": "drop",
                "lot": {"param": "ItemLotParam_enemy", "rowId": lot_id},
                "items": items,
                "sourceNpcParamRows": [rid],
                "sourceItemLotRows": chain_ids,
                "evidence": [
                    f"regulation.bin NpcParam row {rid} itemLotId_enemy={lot_id}",
                    "sequential ItemLotParam_enemy continuation rows "
                    + ",".join(str(value) for value in chain_ids),
                ],
                "verification": (
                    "local_param_verified_sequential_lot_chain"
                    if len(chain_ids) > 1 else "local_param_verified"
                ),
            })
    return relations


def summarize_enemy_drop_coverage(
    npc_rows: list[dict],
    lot_rows: list[dict],
    tables,
    row_to_entity: dict[int, str],
) -> tuple[dict[str, int], list[dict]]:
    """Report every referenced enemy-lot root, including non-item gaps.

    A missing or empty ItemLotParam row is not an acquisition relation because
    it does not identify an item. It is still a real source fact and must stay
    visible as a local, independently repairable coverage gap.
    """

    lot_by_id = {row["id"]: row["cells"] for row in lot_rows}
    referenced_lot_ids = {
        row["cells"].get("itemLotId_enemy")
        for row in npc_rows
        if isinstance(row["cells"].get("itemLotId_enemy"), int)
        and row["cells"].get("itemLotId_enemy") > 0
    }
    source_rows_by_root: dict[int, list[int]] = {}
    for row in npc_rows:
        root = row["cells"].get("itemLotId_enemy")
        if isinstance(root, int) and root > 0:
            source_rows_by_root.setdefault(root, []).append(row["id"])

    gaps: list[dict] = []
    roots_with_resolved_items = 0
    roots_with_partial_name_resolution = 0
    roots_with_raw_items = 0
    roots_with_unresolved_names_only = 0
    missing_roots = 0
    empty_roots = 0
    unresolved_name_slots = 0
    raw_item_slots = 0
    resolved_item_slots = 0

    for root in sorted(referenced_lot_ids):
        chain_ids = expand_enemy_lot_chain(root, lot_by_id, referenced_lot_ids)
        source_rows = sorted(source_rows_by_root.get(root, []))
        source_entities = sorted({
            row_to_entity[row_id]
            for row_id in source_rows
            if row_id in row_to_entity
        })
        if not chain_ids:
            missing_roots += 1
            gaps.append({
                "id": f"enemy-drop-gap-lot{root}",
                "method": "drop",
                "status": "source_lot_missing",
                "sourceItemLotRoot": root,
                "sourceNpcParamRows": source_rows,
                "sourceEntityIds": source_entities,
                "evidence": [
                    f"NpcParam itemLotId_enemy references missing ItemLotParam_enemy row {root}",
                ],
                "verification": "local_param_gap",
            })
            continue

        raw_slots = 0
        resolved_slots = 0
        unresolved_slots = 0
        for chain_id in chain_ids:
            cells = lot_by_id[chain_id]
            for slot in range(1, 9):
                item_id = cells.get(f"lotItemId{slot:02d}")
                if not isinstance(item_id, int) or item_id <= 0:
                    continue
                raw_slots += 1
                category = cells.get(f"lotItemCategory{slot:02d}")
                fmg = LOT_CATEGORY_TABLES.get(category, "GoodsName")
                entry = tables.get(fmg, {}).get(item_id)
                if clean_name((entry or {}).get("en")):
                    resolved_slots += 1
                else:
                    unresolved_slots += 1

        raw_item_slots += raw_slots
        resolved_item_slots += resolved_slots
        unresolved_name_slots += unresolved_slots
        if raw_slots:
            roots_with_raw_items += 1
        if resolved_slots:
            roots_with_resolved_items += 1
        if unresolved_slots and resolved_slots:
            roots_with_partial_name_resolution += 1
        if raw_slots and not resolved_slots:
            roots_with_unresolved_names_only += 1
            gaps.append({
                "id": f"enemy-drop-gap-lot{root}",
                "method": "drop",
                "status": "item_name_unresolved",
                "sourceItemLotRoot": root,
                "sourceItemLotRows": chain_ids,
                "sourceNpcParamRows": source_rows,
                "sourceEntityIds": source_entities,
                "rawItemSlotCount": raw_slots,
                "unresolvedItemSlotCount": unresolved_slots,
                "evidence": [
                    f"ItemLotParam_enemy chain {','.join(str(value) for value in chain_ids)} contains item ids",
                    "no corresponding official FMG name was resolved",
                ],
                "verification": "local_param_gap",
            })
        elif not raw_slots:
            empty_roots += 1
            gaps.append({
                "id": f"enemy-drop-gap-lot{root}",
                "method": "drop",
                "status": "source_lot_empty",
                "sourceItemLotRoot": root,
                "sourceItemLotRows": chain_ids,
                "sourceNpcParamRows": source_rows,
                "sourceEntityIds": source_entities,
                "evidence": [
                    f"ItemLotParam_enemy chain {','.join(str(value) for value in chain_ids)} has no item slot",
                ],
                "verification": "local_param_gap",
            })

    stats = {
        "dropSourceNpcRowCount": len(source_rows_by_root),
        "dropSourceNpcRowsWithDropLot": sum(len(rows) for rows in source_rows_by_root.values()),
        "dropRootCount": len(referenced_lot_ids),
        "dropRootWithResolvedItems": roots_with_resolved_items,
        "dropRootWithRawItems": roots_with_raw_items,
        "dropRootWithPartialNameResolution": roots_with_partial_name_resolution,
        "dropRootWithUnresolvedNamesOnly": roots_with_unresolved_names_only,
        "dropRootMissingLotRowCount": missing_roots,
        "dropRootEmptyLotCount": empty_roots,
        "dropRawItemSlotCount": raw_item_slots,
        "dropResolvedItemSlotCount": resolved_item_slots,
        "dropUnresolvedItemSlotCount": unresolved_name_slots,
        "dropGapCount": len(gaps),
    }
    return stats, gaps


def attach_enemy_spawn_endpoints(relations: list[dict], spawn_path: Path) -> int:
    """Attach exact MSB enemy instances to their regulation drop relations."""
    if not spawn_path.is_file():
        return 0
    payload = json.loads(spawn_path.read_text(encoding="utf-8"))
    by_npc = {
        str(binding["npcParamId"]): binding.get("instances", [])
        for binding in payload.get("bindings", [])
    }
    endpoint_count = 0
    for relation in relations:
        instances: list[dict] = []
        seen = set()
        for row_id in relation.get("sourceNpcParamRows", []):
            for instance in by_npc.get(str(row_id), []):
                key = (instance.get("map"), instance.get("part"), instance.get("npcParamId"))
                if key in seen:
                    continue
                seen.add(key)
                instances.append(instance)
        if instances:
            relation["endpointInstances"] = instances
            endpoint_count += len(instances)
    return endpoint_count


def build_pickups(
    lot_rows: list[dict],
    tables,
    chain_root_ids: set[int] | None = None,
) -> list[dict]:
    """Map pickups: ItemLotParam_map rows -> items.

    Treasure events point at the first row of the same sequential-lot chain
    used for multi-item chests and corpses.  The root relation therefore keeps
    every continuation item.  When ``chain_root_ids`` is supplied, only roots
    proven by the copied MSB treasure binding snapshot are published as fixed
    pickups; unrelated ItemLotParam_map rows are not pickup evidence.
    """
    lot_by_id = {r["id"]: r["cells"] for r in lot_rows}
    referenced_lot_ids = set(chain_root_ids or ())
    relations = []
    for r in lot_rows:
        root_lot_id = r["id"]
        if chain_root_ids is not None and root_lot_id not in referenced_lot_ids:
            continue
        chain_ids = (
            expand_enemy_lot_chain(root_lot_id, lot_by_id, referenced_lot_ids)
            if root_lot_id in referenced_lot_ids else [root_lot_id]
        )
        items = []
        for chain_lot_id in chain_ids:
            lot = lot_by_id[chain_lot_id]
            for k in range(1, 9):
                iid = lot.get(f"lotItemId{k:02d}")
                cat = lot.get(f"lotItemCategory{k:02d}")
                if not iid or iid <= 0:
                    continue
                fmg = LOT_CATEGORY_TABLES.get(cat, "GoodsName")
                entry = tables.get(fmg, {}).get(iid)
                en = clean_name((entry or {}).get("en"))
                if not en:
                    continue
                items.append({
                    "item": f"{LOT_CATEGORY_KIND.get(cat, 'item')}_{slugify(en)}",
                    "name": {"en": en, "zh": clean_name((entry or {}).get("zh")) or en},
                    "lot": chain_lot_id,
                    "slot": k,
                    "num": lot.get(f"lotItemNum{k:02d}"),
                    "rate": lot.get(f"lotItemBasePoint{k:02d}"),
                    "sourceParam": FMG_TO_PARAM[fmg],
                    "sourceParamId": iid,
                    "sourceItemCategory": cat,
                })
        if items:
            relations.append({
                "id": f"pickup-lot{root_lot_id}",
                "from": None,
                "method": "pickup",
                "lot": {"param": "ItemLotParam_map", "rowId": root_lot_id},
                "items": items,
                "sourceItemLotRows": chain_ids,
                "evidence": [
                    f"regulation.bin ItemLotParam_map row {root_lot_id}",
                    "sequential ItemLotParam_map continuation rows "
                    + ",".join(str(value) for value in chain_ids),
                ],
                "verification": (
                    "local_param_verified_sequential_lot_chain"
                    if len(chain_ids) > 1 else "local_param_verified"
                ),
            })
    return relations


def build_shops(
    shop_rows: list[dict],
    tables,
    custom_weapon_rows: list[dict] | None = None,
    material_rows: list[dict] | None = None,
    merchant_bindings_path: Path | None = None,
    known_entities: list[dict] | None = None,
) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Build one purchase relation per item row and known seller instance.

    A ShopLineupParam block is not a merchant identity.  The copied merchant
    binding table comes from talk-script shop ranges joined to physical map
    instances, so a row sold by several merchants becomes several independent
    relations.  Rows without a named seller stay attached to an explicit
    unresolved shop context and remain searchable without becoming a route.

    Returns ``(relations, newly_created_entities, stats)``.
    """
    known_by_name = {
        entity.get("name", {}).get("en"): entity
        for entity in (known_entities or [])
        if entity.get("name", {}).get("en")
    }
    known_by_param_row: dict[tuple[str, int], list[str]] = defaultdict(list)
    for entity in known_entities or []:
        for signifier in entity.get("signifiers", []):
            param = signifier.get("param")
            if not param:
                continue
            for row_id in signifier.get("rows", []):
                known_by_param_row[(str(param), int(row_id))].append(entity["id"])
    merchant_bindings: dict[int, list[dict]] = {}
    if merchant_bindings_path and merchant_bindings_path.is_file():
        payload = json.loads(merchant_bindings_path.read_text(encoding="utf-8"))
        for binding in payload.get("bindings", []):
            row_id = binding.get("rowId")
            if row_id is not None:
                merchant_bindings.setdefault(int(row_id), []).append(binding)

    custom_weapons = {
        int(row["id"]): row["cells"] for row in (custom_weapon_rows or [])
    }
    material_sets = {
        int(row["id"]): row["cells"] for row in (material_rows or [])
    }

    def material_cost(material_set_id: int) -> list[dict]:
        cells = material_sets.get(material_set_id)
        if not cells:
            return []
        category_param = {1: "EquipParamWeapon", 4: "EquipParamGoods"}
        category_fmg = {1: "WeaponName", 4: "GoodsName"}
        result = []
        for index in range(1, 7):
            suffix = f"{index:02d}"
            item_id = int(cells.get(f"materialId{suffix}", -1))
            quantity = int(cells.get(f"itemNum{suffix}", -1))
            category = int(cells.get(f"materialCate{suffix}", -1))
            param = category_param.get(category)
            fmg = category_fmg.get(category)
            if item_id < 0 or quantity < 0 or not param or not fmg:
                continue
            entry = name_for(tables, item_id, [fmg])
            english = clean_name((entry or {}).get("en"))
            if not english:
                continue
            candidates = known_by_param_row.get((param, item_id), [])
            result.append({
                "item": candidates[0] if len(candidates) == 1 else None,
                "name": {
                    "en": english,
                    "zh": clean_name((entry or {}).get("zh")) or english,
                },
                "quantity": quantity,
                "sourceParam": param,
                "sourceParamId": item_id,
                "sourceMaterialCategory": category,
                "canonicalStatus": (
                    "exact" if len(candidates) == 1
                    else "ambiguous" if candidates else "unresolved"
                ),
                "candidateEntityIds": candidates,
            })
        return result
    custom_weapon_row_count = 0
    unresolved_custom_weapon_row_count = 0
    row_items: dict[int, dict] = {}
    for r in shop_rows:
        c = r["cells"]
        etype = c.get("equipType")
        eid = c.get("equipId")
        if not eid or eid <= 0:
            continue
        source_custom_weapon_id = None
        custom_weapon = None
        if etype == 5:
            custom_weapon = custom_weapons.get(int(eid))
            if not custom_weapon:
                unresolved_custom_weapon_row_count += 1
                continue
            source_custom_weapon_id = int(eid)
            eid = int(custom_weapon.get("baseWepId", -1))
            fmg = "WeaponName"
            if eid <= 0:
                unresolved_custom_weapon_row_count += 1
                continue
            custom_weapon_row_count += 1
        else:
            fmg = SHOP_EQUIP_TABLES.get(etype)
            if fmg is None:
                continue
        # The category is carried by equipType.  Falling back to GoodsName
        # when the selected FMG has no row turns stale/invalid ShopLineupParam
        # entries into false purchases (for example an ash or a consumable
        # masquerading as armor).  Keep only rows whose category-specific
        # official name resolves.
        entry = name_for(tables, eid, [fmg])
        en = clean_name((entry or {}).get("en"))
        if not en:
            continue
        item = {
            "item": f"{'weapon' if etype == 5 else SHOP_EQUIP_KIND.get(etype, 'item')}_{slugify(en)}",
            "name": {"en": en, "zh": clean_name((entry or {}).get("zh")) or en},
            "price": c.get("value"),
            "costType": c.get("costType"),
            "mtrlId": c.get("mtrlId"),
            "stock": c.get("sellQuantity"),
            "lineupRow": r["id"],
            "sourceParam": FMG_TO_PARAM[fmg],
            "sourceParamId": eid,
            "sourceEquipType": etype,
        }
        if source_custom_weapon_id is not None and custom_weapon is not None:
            item.update({
                "sourceEquipId": source_custom_weapon_id,
                "sourceCustomWeaponId": source_custom_weapon_id,
                "reinforcementLevel": int(custom_weapon.get("reinforceLv", 0)),
                "attachedGemId": int(custom_weapon.get("gemId", -1)),
            })
        material_set_id = int(c.get("mtrlId", -1))
        costs = material_cost(material_set_id) if material_set_id >= 0 else []
        if costs:
            item["materialCost"] = costs
        row_items[r["id"]] = item
    relations = []
    entities = []
    context_entities: dict[int, dict] = {}

    def unresolved_context(shop_id: int) -> dict:
        entity = context_entities.get(shop_id)
        if entity:
            return entity
        entity = {
            "id": f"shop_context_{shop_id}",
            "kind": "shop_context",
            "category": "unresolved_shop",
            "class": None,
            "name": {
                "en": f"Unresolved Shop Context {shop_id}",
                "zh": f"未解析商店上下文 {shop_id}",
            },
            "signifiers": [{
                "type": "param_block",
                "param": "ShopLineupParam",
                "rows": [shop_id * 1000],
            }],
            "properties": {
                "shopId": shop_id,
                "identityStatus": "unresolved",
                "topologyStatus": "not_bound",
            },
            "variant_count": 1,
        }
        context_entities[shop_id] = entity
        entities.append(entity)
        return entity

    def seller_entity(binding: dict) -> dict:
        name = binding.get("merchantName")
        if name in known_by_name:
            entity = known_by_name[name]
            entity.setdefault("properties", {})["shopVendor"] = True
            return entity
        seller_id = f"shop_vendor_{slugify(name or 'unresolved_seller')}"
        entity = {
            "id": seller_id,
            "kind": "npc",
            "category": "merchant",
            "class": None,
            "name": {"en": name or "Unresolved seller", "zh": name or "未解析卖家"},
            "signifiers": [{
                "type": "external_shop_source",
                "merchantName": name,
                "npcParamRows": [binding["npcParamId"]] if binding.get("npcParamId") is not None else [],
            }],
            "properties": {
                "identityStatus": "external_name_verified" if name else "unresolved",
                "shopVendor": True,
            },
            "variant_count": 1,
        }
        known_by_name[name] = entity
        entities.append(entity)
        return entity

    def endpoint_for(binding: dict) -> dict | None:
        if not binding.get("position") or not binding.get("map"):
            return None
        endpoint = dict(binding)
        endpoint["kind"] = "merchant_shop_endpoint"
        endpoint["topologyBinding"] = {
            "status": "coordinate_endpoint",
            "routeNodeIds": [],
            "semanticNodeIds": [],
            "reason": "商店行号已绑定到卖家地图坐标，但尚未绑定正式抽象导航锚点",
        }
        return endpoint

    mapped_rows = set()
    named_relation_count = 0
    unresolved_relation_count = 0
    for row_id, item in sorted(row_items.items()):
        bindings = merchant_bindings.get(row_id, [])
        if not bindings:
            context = unresolved_context(row_id // 1000)
            relations.append({
                "id": f"purchase-unresolved-row{row_id}",
                "from": context["id"],
                "method": "purchase",
                "items": [item],
                "lineupRow": row_id,
                "sellerStatus": "unresolved",
                **({"materialCost": item["materialCost"]} if item.get("materialCost") else {}),
                "evidence": [
                    f"regulation.bin ShopLineupParam row {row_id}",
                    "no seller binding in copied talk-range shop source",
                ],
                "verification": "local_param_verified_seller_unresolved",
            })
            unresolved_relation_count += 1
            continue

        mapped_rows.add(row_id)
        for binding in bindings:
            endpoint = endpoint_for(binding)
            named = binding.get("sellerStatus") == "named" and binding.get("merchantName")
            if named:
                seller = seller_entity(binding)
                seller_id = seller["id"]
                seller_slug = slugify(binding["merchantName"])
                relation_id = (
                    f"purchase-row{row_id}-{seller_slug}-"
                    f"{binding.get('npcParamId') or 'unknown'}-{slugify(binding.get('map') or 'unknown')}"
                )
                evidence = [
                    f"regulation.bin ShopLineupParam row {row_id}",
                    (
                        "copied local map semantic alias named the seller and exact map endpoint"
                        if binding.get("sellerIdentitySource") == "local_map_semantic_alias"
                        else "copied talk-range shop source named the seller and map endpoint"
                    ),
                ]
                verification = (
                    "local_param_and_local_map_semantic_shop_endpoint_verified"
                    if binding.get("sellerIdentitySource") == "local_map_semantic_alias"
                    else "local_param_and_external_shop_endpoint_verified"
                )
            else:
                context = unresolved_context(row_id // 1000)
                seller_id = context["id"]
                relation_id = (
                    f"purchase-row{row_id}-unresolved-"
                    f"{binding.get('talkId') or 'unknown'}-{slugify(binding.get('map') or 'unknown')}"
                )
                evidence = [
                    f"regulation.bin ShopLineupParam row {row_id}",
                    "copied talk-range source contains a seller/map candidate without a resolved seller identity",
                ]
                verification = "local_param_verified_seller_unresolved"
                unresolved_relation_count += 1

            relation = {
                "id": relation_id,
                "from": seller_id,
                "method": "purchase",
                "items": [item],
                "lineupRow": row_id,
                "sellerStatus": "named" if named else "unresolved",
                "merchantShopBinding": binding,
                **({"materialCost": item["materialCost"]} if item.get("materialCost") else {}),
                "evidence": evidence,
                "verification": verification,
            }
            if endpoint:
                relation["endpointInstances"] = [endpoint]
            relations.append(relation)
            if named:
                named_relation_count += 1

    # The copied source may intentionally omit a parameter row that exists in
    # this local regulation snapshot.  Preserve that row independently instead
    # of dropping it or assigning it to a guessed merchant.
    source_only_rows = set(merchant_bindings) - set(row_items)
    stats = {
        "purchaseRows": len(row_items),
        "sellerMappedRows": len(mapped_rows),
        "sellerUnresolvedRows": len(row_items) - len(mapped_rows),
        "namedPurchaseRelations": named_relation_count,
        "unresolvedPurchaseRelations": unresolved_relation_count,
        "unresolvedShopContexts": len(context_entities),
        "sourceOnlyRows": len(source_only_rows),
        "customWeaponPurchaseRows": custom_weapon_row_count,
        "unresolvedCustomWeaponPurchaseRows": unresolved_custom_weapon_row_count,
    }
    return relations, entities, stats


def summarize_shop_coverage_gaps(
    purchase_relations: list[dict],
) -> tuple[list[dict], dict[str, int]]:
    """Publish every unresolved purchase relation as an isolated repair gap.

    A missing seller identity is a data-coverage problem, not permission to
    invent a merchant.  The copied source has two materially different forms
    of unresolved evidence: a ShopLineupParam row with no external binding at
    all, or a binding with a map/talk candidate but no verified seller name.
    A candidate that shares its lineup row with a named seller is called out
    separately because it may be a duplicate context, but it is still not
    promoted to that named seller.
    """
    named_rows = {
        relation.get("lineupRow")
        for relation in purchase_relations
        if relation.get("sellerStatus") == "named"
    }
    gaps: list[dict] = []
    status_counts = Counter()
    named_sibling_count = 0
    for relation in purchase_relations:
        if relation.get("sellerStatus") == "named":
            continue
        binding = relation.get("merchantShopBinding") or {}
        lineup_row = relation.get("lineupRow")
        has_named_sibling = bool(binding) and lineup_row in named_rows
        if not binding:
            status = "seller_unresolved_no_external_binding"
        elif has_named_sibling:
            status = "seller_unresolved_candidate_binding"
            named_sibling_count += 1
        else:
            status = "seller_unresolved_binding"
        status_counts[status] += 1
        gaps.append({
            "id": f"purchase-gap-{relation['id']}",
            "method": "purchase",
            "status": status,
            "relationId": relation["id"],
            "lineupRow": lineup_row,
            "shopContext": relation.get("from"),
            "sellerStatus": relation.get("sellerStatus"),
            "hasCandidateBinding": bool(binding),
            "hasNamedSibling": has_named_sibling,
            "evidence": list(relation.get("evidence", [])),
            "verification": "local_param_gap",
        })
    return gaps, {
        "coverageGapCount": len(gaps),
        "coverageGapSellerUnresolvedNoExternalBindingCount": status_counts[
            "seller_unresolved_no_external_binding"
        ],
        "coverageGapSellerUnresolvedBindingCount": status_counts[
            "seller_unresolved_binding"
        ],
        "coverageGapSellerUnresolvedCandidateBindingCount": status_counts[
            "seller_unresolved_candidate_binding"
        ],
        "coverageGapCandidateWithNamedSiblingCount": named_sibling_count,
        "coverageGapCandidateWithoutNamedSiblingCount": status_counts[
            "seller_unresolved_binding"
        ],
    }


def summarize_pickup_coverage_gaps(
    pickup_relations: list[dict],
) -> tuple[list[dict], dict[str, int]]:
    """Publish unresolved fixed-pickup location evidence as isolated gaps.

    The acquisition relation remains valid when its location endpoint is
    missing. A missing external binding and a source record without valid
    coordinates are separate repair states; neither is filled from an online
    item marker because that would lose the exact ItemLot-to-Treasure identity.
    """
    gaps: list[dict] = []
    status_counts = Counter()
    for relation in pickup_relations:
        status = relation.get("pickupEndpointStatus")
        if status == "coordinate_endpoint":
            continue
        if status not in {
            "no_external_location_binding",
            "source_record_without_coordinates",
        }:
            raise ValueError(
                f"unexpected pickup endpoint status while publishing gaps: {status}"
            )
        binding = relation.get("pickupLocationBinding") or {}
        status_counts[status] += 1
        gaps.append({
            "id": f"pickup-gap-{relation['id']}",
            "method": "pickup",
            "status": status,
            "relationId": relation["id"],
            "sourceItemLotRoot": (relation.get("lot") or {}).get("rowId"),
            "sourceItemLotRows": relation.get("sourceItemLotRows", []),
            "itemCount": len(relation.get("items", [])),
            "hasLocationBinding": bool(binding),
            "positionCount": binding.get("positionCount", 0),
            "validPositionCount": binding.get("validPositionCount", 0),
            "evidence": list(relation.get("evidence", [])) + [
                "fixed pickup endpoint remains unresolved; no online marker promoted",
            ],
            "verification": "local_param_gap",
        })
    return gaps, {
        "coverageGapCount": len(gaps),
        "coverageGapNoExternalLocationBindingCount": status_counts[
            "no_external_location_binding"
        ],
        "coverageGapSourceRecordWithoutCoordinatesCount": status_counts[
            "source_record_without_coordinates"
        ],
    }


# ---------------------------------------------------------------------------
# Boss reward relations (remembrance / great rune -> boss)
# ---------------------------------------------------------------------------

# Official Remembrance goods name -> boss NpcName
REMEMBRANCE_TO_BOSS = {
    "Remembrance of the Grafted": "Godrick the Grafted",
    "Remembrance of the Starscourge": "Starscourge Radahn",
    "Remembrance of the Omen King": "Morgott, the Omen King",
    "Remembrance of the Blasphemous": "Rykard, Lord of Blasphemy",
    "Remembrance of the Rot Goddess": "Malenia, Blade of Miquella",
    "Remembrance of the Blood Lord": "Mohg, Lord of Blood",
    "Remembrance of the Full Moon Queen": "Rennala, Queen of the Full Moon",
    "Remembrance of the Naturalborn": "Astel, Naturalborn of the Void",
    "Remembrance of the Dragonlord": "Dragonlord Placidusax",
    "Remembrance of the Regal Ancestor": "Regal Ancestor Spirit",
    "Remembrance of the Fire Giant": "Fire Giant",
    "Remembrance of the Black Blade": "Maliketh, the Black Blade",
    "Remembrance of Hoarah Loux": "Hoarah Loux, Warrior",
    "Remembrance of the Elden Beast": "Elden Beast",
    "Remembrance of the Lord of Frenzied Flame": "Lord of Frenzied Flame",
    "Remembrance of the Wild Dancer": "Divine Beast Dancing Lion",
    "Remembrance of the Mother of Fingers": "Metyr, Mother of Fingers",
    "Remembrance of the Impaler": "Messmer the Impaler",
    "Remembrance of the Saint of the Bud": "Romina, Saint of the Bud",
    "Remembrance of the Dread": "Midra, Lord of Frenzied Flame",
    "Remembrance of the Twin Moon Knight": "Rellana, Twin Moon Knight",
    "Remembrance of the Shadow Sunflower": "Scadutree Avatar",
}

GREAT_RUNE_TO_BOSS = {
    "Godrick's Great Rune": "Godrick the Grafted",
    "Great Rune of the Unborn": "Rennala, Queen of the Full Moon",
    "Radahn's Great Rune": "Starscourge Radahn",
    "Morgott's Great Rune": "Morgott, the Omen King",
    "Rykard's Great Rune": "Rykard, Lord of Blasphemy",
    "Mohg's Great Rune": "Mohg, Lord of Blood",
    "Malenia's Great Rune": "Malenia, Blade of Miquella",
}


def build_boss_reward_relations(
    entities: list[dict], tables, boss_endpoints_path: Path | None = None
) -> list[dict]:
    """Remembrance / Great Rune entities point to their source boss (and back)."""
    by_name = {e["name"]["en"]: e for e in entities}
    endpoint_by_name: dict[str, dict] = {}
    if boss_endpoints_path and boss_endpoints_path.is_file():
        endpoint_payload = json.loads(boss_endpoints_path.read_text(encoding="utf-8"))
        endpoint_by_name = {
            str(endpoint["bossName"]).casefold(): endpoint
            for endpoint in endpoint_payload.get("endpoints", [])
            if endpoint.get("bossName")
        }
    relations = []
    for item_name, boss_name in {**REMEMBRANCE_TO_BOSS, **GREAT_RUNE_TO_BOSS}.items():
        item = by_name.get(item_name)
        boss = by_name.get(boss_name)
        if not item or not boss:
            continue
        endpoint = endpoint_by_name.get(boss_name.casefold())
        evidence = ["official boss/remembrance name mapping"]
        verification = "official_names"
        if endpoint:
            evidence.append("independent Boss reward endpoint binding")
            verification = "official_names_and_boss_endpoint_binding"
        reward_relation = {
            "id": f"boss-reward-{slugify(item_name)}",
            "from": item["id"],
            "method": "boss_reward",
            "items": [{"item": boss["id"], "name": boss["name"], "num": 1}],
            "evidence": evidence,
            "verification": verification,
        }
        if endpoint:
            reward_relation["endpointInstances"] = [endpoint]
        relations.append(reward_relation)
        drops_relation = {
            "id": f"boss-drops-{slugify(boss_name)}",
            "from": boss["id"],
            "method": "drops",
            "items": [{"item": item["id"], "name": item["name"], "num": 1}],
            "evidence": evidence,
            "verification": verification,
        }
        if endpoint:
            drops_relation["endpointInstances"] = [endpoint]
        relations.append(drops_relation)
    return relations


def attach_pickup_endpoints(
    relations: list[dict],
    pickup_bindings_path: Path | None,
) -> dict[str, int]:
    """Attach copied MSB treasure/corpse coordinates to pickup relations.

    The regulation lot identifies the reward contents; the separate pickup
    binding snapshot identifies where that lot is instantiated. These are
    joined only by the exact root lot id. A coordinate endpoint is useful
    acquisition evidence, but it is deliberately not promoted to a route node.
    """

    empty = {
        "bindings": 0,
        "endpoint_relations": 0,
        "endpoint_instances": 0,
        "source_without_coordinates": 0,
        "missing_bindings": 0,
    }
    if not pickup_bindings_path or not pickup_bindings_path.is_file():
        return empty
    payload = json.loads(pickup_bindings_path.read_text(encoding="utf-8"))
    bindings = {
        int(binding["lot"]): binding
        for binding in payload.get("bindings", [])
        if binding.get("lot") is not None
    }
    stats = dict(empty)
    stats["bindings"] = len(bindings)
    for relation in relations:
        root_lot = (relation.get("lot") or {}).get("rowId")
        binding = bindings.get(root_lot)
        if binding is None:
            relation["pickupEndpointStatus"] = "no_external_location_binding"
            stats["missing_bindings"] += 1
            continue

        positions = binding.get("positions", [])
        valid_positions = [
            position for position in positions
            if position.get("map") and isinstance(position.get("position"), dict)
            and all(isinstance(position["position"].get(axis), (int, float))
                    for axis in ("x", "y", "z"))
        ]
        relation["pickupLocationBinding"] = {
            "lot": root_lot,
            "sourceItemLotRows": binding.get("sourceItemLotRows", []),
            "positionCount": len(positions),
            "validPositionCount": len(valid_positions),
            "count": binding.get("count"),
        }
        if not valid_positions:
            relation["pickupEndpointStatus"] = "source_record_without_coordinates"
            stats["source_without_coordinates"] += 1
            continue

        endpoints = []
        for index, position in enumerate(valid_positions, 1):
            endpoints.append({
                "kind": "pickup_endpoint",
                "sourceLotRow": root_lot,
                "sourcePositionIndex": index,
                "map": position["map"],
                "part": position.get("part"),
                "position": position["position"],
                "coordinateSpace": "game_world_xyz",
                "inChest": position.get("inChest"),
                "treasureName": position.get("treasureName"),
                "topologyBinding": {
                    "status": "coordinate_endpoint",
                    "routeNodeIds": [],
                    "semanticNodeIds": [],
                    "reason": (
                        "local MSB pickup coordinate; no formal abstract "
                        "topology anchor has been proven"
                    ),
                },
                "sourceEvidence": [
                    "pickup-location-bindings.json exact root ItemLotParam_map row",
                    f"source lot row {root_lot} position {index}",
                ],
            })
        relation["endpointInstances"] = endpoints
        relation["pickupEndpointStatus"] = "coordinate_endpoint"
        relation.setdefault("evidence", []).append(
            "copied local MSB pickup location endpoint catalog"
        )
        stats["endpoint_relations"] += 1
        stats["endpoint_instances"] += len(endpoints)
    return stats


def build_event_reward_relations(event_rewards_path: Path | None = None) -> list[dict]:
    """Expose direct EMEVD item-award facts without guessing quest identity."""
    if not event_rewards_path or not event_rewards_path.is_file():
        return []
    payload = json.loads(event_rewards_path.read_text(encoding="utf-8"))
    relations = []
    for binding in payload.get("bindings", []):
        items = [
            {
                "item": item["item"],
                "name": item["name"],
                "num": item.get("num"),
                **{
                    key: item[key]
                    for key in ("lot", "slot", "category", "quantityStatus")
                    if key in item
                },
            }
            for item in binding.get("items", [])
            if item.get("item") and item.get("name", {}).get("en")
        ]
        if not items:
            continue
        relations.append({
            "id": binding["id"],
            "from": None,
            "method": "event_reward",
            "items": items,
            "eventRewardBinding": binding,
            "evidence": binding.get("evidence", []),
            "verification": binding.get("verification", "local_emevd_and_param_verified"),
        })
    return relations


def build_talk_reward_relations(talk_rewards_path: Path | None = None) -> list[dict]:
    """Expose exact Talk ESD awards without inventing an NPC or endpoint."""
    if not talk_rewards_path or not talk_rewards_path.is_file():
        return []
    payload = json.loads(talk_rewards_path.read_text(encoding="utf-8"))
    relations = []
    for binding in payload.get("bindings", []):
        items = [
            {
                key: item[key]
                for key in (
                    "item", "name", "num", "lot", "slot", "category",
                    "sourceParam", "sourceParamId", "quantityStatus",
                )
                if key in item
            }
            for item in binding.get("items", [])
            if item.get("item") and item.get("name", {}).get("en")
        ]
        if not items:
            continue
        relations.append({
            "id": binding["id"],
            "from": None,
            "method": "talk_reward",
            "items": items,
            "talkItemLotBinding": binding,
            "evidence": binding.get("evidence", []),
            "verification": binding.get(
                "verification", "local_talk_esd_and_param_verified"
            ),
        })
    return relations


def build_gesture_acquisition_relations(
    gesture_acquisitions_path: Path | None = None,
) -> list[dict]:
    """Expose local starting-loadout, EMEVD, and Talk ESD gesture facts."""
    if not gesture_acquisitions_path or not gesture_acquisitions_path.is_file():
        return []
    payload = json.loads(gesture_acquisitions_path.read_text(encoding="utf-8"))
    relations = []
    for binding in payload.get("bindings", []):
        items = [
            {
                key: item[key]
                for key in ("item", "name", "sourceParam", "sourceParamId")
                if key in item
            }
            for item in binding.get("items", [])
            if item.get("item") and item.get("name", {}).get("en")
        ]
        if not items:
            continue
        relations.append({
            "id": binding["id"],
            "from": None,
            "method": binding["method"],
            "items": items,
            "gestureAcquisitionBinding": binding,
            "evidence": binding.get("evidence", []),
            "verification": binding.get("verification"),
        })
    return relations


def build_tutorial_unlock_relations(
    tutorial_unlocks_path: Path | None = None,
) -> list[dict]:
    """Expose exact local tutorial/info unlock events as independent facts."""
    if not tutorial_unlocks_path or not tutorial_unlocks_path.is_file():
        return []
    payload = json.loads(tutorial_unlocks_path.read_text(encoding="utf-8"))
    relations = []
    for binding in payload.get("bindings", []):
        items = [
            {
                key: item[key]
                for key in ("item", "name", "sourceParam", "sourceParamId")
                if key in item
            }
            for item in binding.get("items", [])
            if item.get("item") and item.get("name", {}).get("en")
        ]
        if not items:
            continue
        relations.append({
            "id": binding["id"],
            "from": None,
            "method": "tutorial_unlock",
            "items": items,
            "tutorialUnlockBinding": binding,
            "evidence": binding.get("evidence", []),
            "verification": binding.get("verification"),
        })
    return relations


ONLINE_CATEGORY_FILTERS = {
    "spell": lambda entity: entity.get("kind") == "spell",
    "weapon": lambda entity: entity.get("kind") == "weapon",
    "armor": lambda entity: entity.get("kind") == "armor",
    "talisman": lambda entity: entity.get("kind") == "accessory",
    "spirit": lambda entity: entity.get("category") == "spirit_ash",
    "ash": lambda entity: entity.get("category") == "ash_of_war",
    "golden": lambda entity: entity.get("category") == "golden_seed",
    "crystal": lambda entity: entity.get("category") == "crystal_tear",
    "tear": lambda entity: entity.get("category") == "crystal_tear",
    "greatrune": lambda entity: entity.get("category") == "great_rune",
    "larval": lambda entity: entity.get("category") == "larval_tear",
    "memory": lambda entity: entity.get("category") == "memory_stone",
    "whetblade": lambda entity: entity.get("category") == "key_item",
}


def build_online_map_relations(
    online_markers_path: Path | None,
    entities: list[dict],
) -> tuple[list[dict], dict[str, int], list[dict]]:
    """Publish exact-name online map markers as coordinate-only endpoints.

    The online map is a second, independent evidence source. It may add a
    concrete map endpoint, but it never invents a formal route node or
    replaces a local regulation/MSB fact.
    """
    if not online_markers_path or not online_markers_path.is_file():
        return [], {
            "markers": 0, "matched": 0, "unmatched": 0, "ambiguous": 0,
            "coverage_gap_count": 0, "source_only_name_count": 0,
        }, []
    payload = json.loads(online_markers_path.read_text(encoding="utf-8"))
    source = payload.get("source", {})
    by_name: dict[str, list[dict]] = {}
    for entity in entities:
        name = entity.get("name", {}).get("en")
        if name:
            by_name.setdefault(name.casefold(), []).append(entity)

    relations = []
    stats = {
        "markers": len(payload.get("markers", [])),
        "matched": 0,
        "unmatched": 0,
        "ambiguous": 0,
        "coverage_gap_count": 0,
        "source_only_name_count": 0,
    }
    coverage_gaps = []
    for marker in payload.get("markers", []):
        predicate = ONLINE_CATEGORY_FILTERS.get(marker.get("category"))
        candidates = [
            entity
            for entity in by_name.get(str(marker.get("name", "")).casefold(), [])
            if predicate and predicate(entity)
        ]
        if len(candidates) != 1:
            status = "source_marker_unmatched" if not candidates else "source_marker_ambiguous"
            stats["unmatched" if not candidates else "ambiguous"] += 1
            endpoint = {
                "kind": "online_map_marker",
                "source": source.get("url") or "online_map_snapshot",
                "markerId": marker["id"],
                "mapMaster": marker["master"],
                "pixelPosition": marker["pixel"],
                "description": marker.get("description"),
                "topologyBinding": {
                    "status": "coordinate_endpoint",
                    "routeNodeIds": [],
                    "semanticNodeIds": [],
                    "reason": "online map marker; canonical identity unresolved",
                },
                "sourceEvidence": [
                    f"online map marker {marker['id']} has {status}",
                    f"online map source {source.get('url') or 'snapshot'}",
                ],
            }
            coverage_gaps.append({
                "id": f"online-map-gap-{marker['id']}",
                "method": "online_map",
                "status": status,
                "externalSourceId": marker.get("id"),
                "externalSourceName": str(marker.get("name") or ""),
                "onlineMapCategory": marker.get("category"),
                "onlineMapDescription": marker.get("description"),
                "onlineMapMaster": marker.get("master"),
                "onlineMapPixelPosition": marker.get("pixel"),
                "candidateEntityIds": [candidate["id"] for candidate in candidates],
                "endpointInstances": [endpoint],
                "sourceMarker": marker,
                "evidence": endpoint["sourceEvidence"],
                "verification": "online_map_source_record_unresolved",
            })
            continue
        entity = candidates[0]
        marker_id = marker["id"]
        endpoint = {
            "kind": "online_map_marker",
            "source": source.get("url") or "online_map_snapshot",
            "markerId": marker_id,
            "mapMaster": marker["master"],
            "pixelPosition": marker["pixel"],
            "description": marker.get("description"),
            "topologyBinding": {
                "status": "coordinate_endpoint",
                "routeNodeIds": [],
                "semanticNodeIds": [],
                "reason": "在线地图像素终点；尚未绑定正式抽象导航锚点",
            },
            "sourceEvidence": [
                f"online map marker {marker_id} exact English-name match",
                f"online map source {source.get('url') or 'snapshot'}",
            ],
        }
        relations.append({
            "id": f"online-map-{marker_id}",
            "from": None,
            "method": "online_map",
            "items": [{
                "item": entity["id"],
                "name": entity["name"],
                "num": 1,
                "onlineMapCategory": marker["category"],
                "onlineMapDescription": marker.get("description"),
            }],
            "endpointInstances": [endpoint],
            "onlineMapMarker": marker,
            "evidence": endpoint["sourceEvidence"],
            "verification": "online_map_exact_official_name_match",
        })
        stats["matched"] += 1
    stats["coverage_gap_count"] = len(coverage_gaps)
    stats["source_only_name_count"] = len({
        (gap.get("externalSourceId"), gap.get("externalSourceName"), gap.get("onlineMapCategory"))
        for gap in coverage_gaps
        if gap.get("externalSourceName")
    })
    return relations, stats, coverage_gaps


def build_online_guide_item_relations(
    guide_items_path: Path | None,
    entities: list[dict],
) -> tuple[list[dict], dict[str, int], list[dict]]:
    """Publish exact-name public guide item locations independently.

    The guide supplies an item name, an acquisition description and a
    source-specific map coordinate.  It is deliberately not treated as a
    local game coordinate, a route node, or a physical walkability proof.
    Ambiguous names and records without a complete map endpoint are retained
    as explicit source-layer gaps and are not promoted to canonical entities.
    """
    if not guide_items_path or not guide_items_path.is_file():
        return [], {
            "items": 0, "map_items": 0, "matched": 0, "unmatched": 0,
            "ambiguous": 0, "invalid_map": 0, "no_map": 0,
            "coverage_gap_count": 0, "source_only_name_count": 0,
        }, []
    payload = json.loads(guide_items_path.read_text(encoding="utf-8"))
    source = payload.get("source", {})
    by_name: dict[str, list[dict]] = {}
    allowed_kinds = {"item", "weapon", "armor", "accessory", "ash_of_war", "spell"}
    for entity in entities:
        if entity.get("kind") not in allowed_kinds:
            continue
        name = entity.get("name", {}).get("en")
        if name:
            by_name.setdefault(name.casefold(), []).append(entity)

    source_items = payload.get("items", [])
    relations = []
    stats = {
        "items": len(source_items),
        "map_items": 0,
        "matched": 0,
        "unmatched": 0,
        "ambiguous": 0,
        "invalid_map": 0,
        "no_map": 0,
        "coverage_gap_count": 0,
        "source_only_name_count": 0,
    }
    coverage_gaps = []
    for item in source_items:
        source_id = str(item.get("sourceId") or "")
        map_data = item.get("map")
        if not map_data:
            stats["no_map"] += 1
            coverage_gaps.append({
                "id": f"online-guide-gap-{source_id}",
                "method": "online_guide",
                "status": "source_item_no_map",
                "externalSourceId": source_id,
                "externalSourceName": str(item.get("name") or ""),
                "onlineGuideCategory": item.get("category"),
                "onlineGuideDescription": item.get("acquisition"),
                "onlineGuideMissable": item.get("missable"),
                "onlineGuideQuest": item.get("quest"),
                "onlineGuideWikiUrl": item.get("wikiUrl"),
                "sourceItem": item,
                "endpointInstances": [],
                "evidence": [
                    f"Aether guide item {source_id} has no map endpoint",
                    f"Aether guide source {source.get('url') or 'snapshot'}",
                ],
                "verification": "online_guide_source_record_unresolved",
            })
            continue
        stats["map_items"] += 1
        if (
            not map_data.get("markerId")
            or not isinstance(map_data.get("code"), str)
            or not isinstance(map_data.get("lat"), (int, float))
            or not isinstance(map_data.get("lng"), (int, float))
        ):
            stats["invalid_map"] += 1
            coverage_gaps.append({
                "id": f"online-guide-gap-{source_id}",
                "method": "online_guide",
                "status": "source_map_invalid",
                "externalSourceId": source_id,
                "externalSourceName": str(item.get("name") or ""),
                "onlineGuideCategory": item.get("category"),
                "onlineGuideDescription": item.get("acquisition"),
                "onlineGuideMissable": item.get("missable"),
                "onlineGuideQuest": item.get("quest"),
                "onlineGuideWikiUrl": item.get("wikiUrl"),
                "sourceItem": item,
                "endpointInstances": [],
                "evidence": [
                    f"Aether guide item {source_id} has an invalid map endpoint",
                    f"Aether guide source {source.get('url') or 'snapshot'}",
                ],
                "verification": "online_guide_source_record_unresolved",
            })
            continue
        candidates = by_name.get(str(item.get("name", "")).casefold(), [])
        if len(candidates) != 1:
            status = "source_item_unmatched" if not candidates else "source_item_ambiguous"
            stats["unmatched" if not candidates else "ambiguous"] += 1
            endpoint = {
                "kind": "online_guide_marker",
                "source": source.get("url") or "aether_guide_snapshot",
                "sourceItemId": source_id,
                "markerId": map_data["markerId"],
                "mapCode": map_data["code"],
                "coordinateSpace": "aether_map_lat_lng",
                "position": {"lat": map_data["lat"], "lng": map_data["lng"]},
                "acquisition": item.get("acquisition"),
                "missable": item.get("missable"),
                "quest": item.get("quest"),
                "wikiUrl": item.get("wikiUrl"),
                "topologyBinding": {
                    "status": "coordinate_endpoint",
                    "routeNodeIds": [],
                    "semanticNodeIds": [],
                    "reason": "public guide coordinate; canonical identity unresolved",
                },
                "sourceEvidence": [
                    f"Aether guide item {source_id} has {status}",
                    f"Aether guide map marker {map_data['markerId']} on {map_data['code']}",
                ],
            }
            coverage_gaps.append({
                "id": f"online-guide-gap-{source_id}",
                "method": "online_guide",
                "status": status,
                "externalSourceId": source_id,
                "externalSourceName": str(item.get("name") or ""),
                "onlineGuideCategory": item.get("category"),
                "onlineGuideDescription": item.get("acquisition"),
                "onlineGuideMissable": item.get("missable"),
                "onlineGuideQuest": item.get("quest"),
                "onlineGuideWikiUrl": item.get("wikiUrl"),
                "candidateEntityIds": [candidate["id"] for candidate in candidates],
                "sourceItem": item,
                "endpointInstances": [endpoint],
                "evidence": endpoint["sourceEvidence"],
                "verification": "online_guide_source_record_unresolved",
            })
            continue
        entity = candidates[0]
        endpoint = {
            "kind": "online_guide_marker",
            "source": source.get("url") or "aether_guide_snapshot",
            "sourceItemId": source_id,
            "markerId": map_data["markerId"],
            "mapCode": map_data["code"],
            "coordinateSpace": "aether_map_lat_lng",
            "position": {
                "lat": map_data["lat"],
                "lng": map_data["lng"],
            },
            "acquisition": item.get("acquisition"),
            "missable": item.get("missable"),
            "quest": item.get("quest"),
            "wikiUrl": item.get("wikiUrl"),
            "topologyBinding": {
                "status": "coordinate_endpoint",
                "routeNodeIds": [],
                "semanticNodeIds": [],
                "reason": "public guide map coordinate; no formal route-node binding",
            },
            "sourceEvidence": [
                f"Aether guide item {source_id} exact unique English-name match",
                f"Aether guide map marker {map_data['markerId']} on {map_data['code']}",
            ],
        }
        relations.append({
            "id": f"online-guide-{source_id}",
            "from": None,
            "method": "online_guide",
            "items": [{
                "item": entity["id"],
                "name": entity["name"],
                "num": 1,
                "onlineGuideCategory": item.get("category"),
                "onlineGuideDescription": item.get("acquisition"),
                "externalSourceId": source_id,
                "externalSourceName": item.get("name"),
            }],
            "endpointInstances": [endpoint],
            "onlineGuideItem": item,
            "evidence": endpoint["sourceEvidence"],
            "verification": "online_guide_exact_unique_official_name_match",
        })
        stats["matched"] += 1
    stats["coverage_gap_count"] = len(coverage_gaps)
    stats["source_only_name_count"] = len({
        (
            gap.get("externalSourceId"),
            gap.get("externalSourceName"),
            gap.get("onlineGuideCategory"),
        )
        for gap in coverage_gaps
        if gap.get("externalSourceName")
    })
    return relations, stats, coverage_gaps


def build_online_item_map_relations(
    item_map_path: Path | None,
    entities: list[dict],
) -> tuple[list[dict], dict[str, int], list[dict]]:
    """Publish exact-name Map For Goblins item placements.

    This source is a coordinate catalog, not a topology source. A single
    source record can contain several items at one physical placement, so one
    relation is retained with multiple item signifiers rather than duplicating
    the endpoint. Unmatched and ambiguous names are retained as explicit
    source-layer gaps; they are not promoted to canonical entities or
    topology relations.
    """
    empty_stats = {
        "records": 0,
        "item_occurrences": 0,
        "matched_records": 0,
        "matched_item_occurrences": 0,
        "matched_by_exact_name_item_occurrences": 0,
        "matched_by_source_param_id_item_occurrences": 0,
        "unmatched_records": 0,
        "unmatched_item_occurrences": 0,
        "ambiguous_item_occurrences": 0,
        "source_param_id_ambiguous_item_occurrences": 0,
        "partial_records": 0,
        "mixed_match_records": 0,
        "matched_entities": 0,
        "coverage_gap_count": 0,
        "source_only_name_count": 0,
    }
    if not item_map_path or not item_map_path.is_file():
        return [], empty_stats, []
    payload = json.loads(item_map_path.read_text(encoding="utf-8"))
    source = payload.get("source", {})
    by_name: dict[str, list[dict]] = {}
    by_param_row: dict[str, list[dict]] = {}
    allowed_kinds = {"item", "weapon", "armor", "accessory", "ash_of_war", "spell"}
    for entity in entities:
        if entity.get("kind") not in allowed_kinds:
            continue
        name = entity.get("name", {}).get("en")
        if name:
            by_name.setdefault(name.casefold(), []).append(entity)
        for signifier in entity.get("signifiers", []):
            if signifier.get("type") != "param":
                continue
            for row in signifier.get("rows", []):
                by_param_row.setdefault(str(row), []).append(entity)

    records = payload.get("records", [])
    stats = dict(empty_stats)
    stats["records"] = len(records)
    relations = []
    coverage_gaps = []
    matched_entity_ids: set[str] = set()
    for record in records:
        source_items = record.get("items", [])
        stats["item_occurrences"] += len(source_items)
        resolved_items = []
        unresolved_count = 0
        ambiguous_count = 0
        record_match_methods: set[str] = set()
        unresolved_items = []
        for source_item_index, source_item in enumerate(source_items):
            name = str(source_item.get("name") or "")
            candidates = by_name.get(name.casefold(), []) if name else []
            match_method = None
            if len(candidates) != 1:
                expected_kinds = ONLINE_ITEM_MAP_EXPECTED_KINDS.get(
                    str(source_item.get("broadCategory") or "").casefold()
                )
                all_param_candidates = by_param_row.get(
                    str(source_item.get("sourceItemId")), []
                )
                param_candidates = (
                    all_param_candidates
                    if len(all_param_candidates) == 1
                    else [
                        candidate
                        for candidate in all_param_candidates
                        if expected_kinds and candidate.get("kind") in expected_kinds
                    ]
                )
                if len(param_candidates) == 1:
                    candidates = param_candidates
                    match_method = "source_param_id"
                    stats["matched_by_source_param_id_item_occurrences"] += 1
                else:
                    unresolved_count += 1
                    if candidates or len(param_candidates) > 1:
                        ambiguous_count += 1
                        if len(param_candidates) > 1:
                            stats["source_param_id_ambiguous_item_occurrences"] += 1
                    unresolved_items.append({
                        "sourceItemIndex": source_item_index,
                        "sourceItem": source_item,
                        "status": (
                            "source_item_ambiguous"
                            if candidates or len(param_candidates) > 1
                            else "source_item_unmatched"
                        ),
                        "candidateEntityIds": sorted({
                            candidate["id"]
                            for candidate in [*candidates, *param_candidates]
                        }),
                    })
                    continue
            if match_method is None:
                match_method = "exact_name"
                stats["matched_by_exact_name_item_occurrences"] += 1
            entity = candidates[0]
            matched_entity_ids.add(entity["id"])
            record_match_methods.add(match_method)
            quantity = source_item.get("quantity")
            resolved_items.append({
                "item": entity["id"],
                "name": entity["name"],
                "num": quantity,
                "quantityStatus": "stated" if quantity is not None else "not_stated",
                "onlineItemMapCategory": source_item.get("category"),
                "onlineItemMapBroadCategory": source_item.get("broadCategory"),
                "onlineItemMapSubCategory": source_item.get("subCategory"),
                "externalSourceId": source_item.get("sourceItemId"),
                "externalSourceName": name,
                "onlineItemMapMatchMethod": match_method,
            })
        stats["matched_item_occurrences"] += len(resolved_items)
        stats["unmatched_item_occurrences"] += unresolved_count - ambiguous_count
        stats["ambiguous_item_occurrences"] += ambiguous_count
        if not resolved_items:
            stats["unmatched_records"] += 1
        else:
            stats["matched_records"] += 1
            if unresolved_count:
                stats["partial_records"] += 1
            if len(record_match_methods) > 1:
                stats["mixed_match_records"] += 1
        verification_by_method = {
            "exact_name": "online_item_map_exact_unique_official_name_match",
            "source_param_id": "online_item_map_source_param_id_unique_kind_match",
        }
        verification = (
            verification_by_method[next(iter(record_match_methods))]
            if len(record_match_methods) == 1
            else (
                "online_item_map_exact_name_or_source_param_id_unique_match"
                if record_match_methods
                else "online_item_map_source_record_unresolved"
            )
        )
        endpoint = {
            "kind": "online_item_map_endpoint",
            "source": source.get("url") or "map_for_goblins_snapshot",
            "sourceCommit": source.get("commit"),
            "sourceRecordId": record.get("sourceRecordId"),
            "sourceIndex": record.get("sourceIndex"),
            "map": record.get("map"),
            "coordinateSpace": record.get("coordinateSpace", "game_world_xyz"),
            "position": record.get("position"),
            "placementType": record.get("placementType"),
            "broadCategory": record.get("broadCategory"),
            "isStatic": record.get("isStatic"),
            "topologyBinding": {
                "status": "coordinate_endpoint",
                "routeNodeIds": [],
                "semanticNodeIds": [],
                "reason": "public item-placement coordinate; no formal route-node binding",
            },
            "sourceEvidence": [
                f"Map For Goblins item record {record.get('sourceIndex')} resolved by {verification}",
                f"Map For Goblins source commit {source.get('commit') or 'snapshot'}",
            ],
        }
        if resolved_items:
            relations.append({
                "id": f"online-item-map-{record['sourceIndex']}",
                "from": None,
                "method": "online_item_map",
                "items": resolved_items,
                "endpointInstances": [endpoint],
                "onlineItemMapRecord": {
                    "sourceIndex": record.get("sourceIndex"),
                    "sourceRecordId": record.get("sourceRecordId"),
                    "map": record.get("map"),
                    "position": record.get("position"),
                    "coordinateSpace": record.get("coordinateSpace"),
                    "placementType": record.get("placementType"),
                    "broadCategory": record.get("broadCategory"),
                    "isStatic": record.get("isStatic"),
                    "sourceItemCount": len(source_items),
                    "unresolvedItemCount": unresolved_count,
                    "matchMethods": sorted(record_match_methods),
                },
                "evidence": endpoint["sourceEvidence"],
                "verification": verification,
            })
        for unresolved in unresolved_items:
            source_item = unresolved["sourceItem"]
            gap_id = (
                f"online-item-map-gap-{record['sourceIndex']}-"
                f"{unresolved['sourceItemIndex']}"
            )
            coverage_gaps.append({
                "id": gap_id,
                "method": "online_item_map",
                "status": unresolved["status"],
                "sourceIndex": record.get("sourceIndex"),
                "sourceRecordId": record.get("sourceRecordId"),
                "sourceItemIndex": unresolved["sourceItemIndex"],
                "externalSourceId": source_item.get("sourceItemId"),
                "externalSourceName": str(source_item.get("name") or ""),
                "onlineItemMapCategory": source_item.get("category"),
                "onlineItemMapBroadCategory": source_item.get("broadCategory"),
                "onlineItemMapSubCategory": source_item.get("subCategory"),
                "candidateEntityIds": unresolved["candidateEntityIds"],
                "map": record.get("map"),
                "coordinateSpace": record.get("coordinateSpace", "game_world_xyz"),
                "position": record.get("position"),
                "placementType": record.get("placementType"),
                "isStatic": record.get("isStatic"),
                "endpointInstances": [copy.deepcopy(endpoint)],
                "evidence": [
                    f"Map For Goblins item occurrence {record.get('sourceIndex')}:{unresolved['sourceItemIndex']} has no canonical unique match",
                    f"Map For Goblins source commit {source.get('commit') or 'snapshot'}",
                ],
                "verification": "online_item_map_source_record_unresolved",
            })
    stats["matched_entities"] = len(matched_entity_ids)
    stats["coverage_gap_count"] = len(coverage_gaps)
    stats["source_only_name_count"] = len({
        (
            gap.get("externalSourceId"),
            gap.get("externalSourceName"),
            gap.get("onlineItemMapBroadCategory"),
        )
        for gap in coverage_gaps
        if gap.get("externalSourceName")
    })
    return relations, stats, coverage_gaps


def build_online_cookbook_recipe_relations(
    recipes_path: Path | None,
    entities: list[dict],
) -> tuple[list[dict], dict[str, int]]:
    """Publish cookbook-to-product recipe unlock relations.

    Smithbox's public event-flag index identifies which cookbook unlocks each
    recipe product.  A separate public cookbook table may enrich the same
    relation with material quantities; the two sources remain independently
    recorded in the relation provenance.
    Cookbook spelling variants in the official name dump, such as square
    brackets versus parentheses, are resolved only for the canonical entity
    id while the source spelling remains in ``craftRecipe``.
    """
    empty_stats = {
        "recipes": 0,
        "matched": 0,
        "unmatched_products": 0,
        "ambiguous_products": 0,
        "unmatched_cookbooks": 0,
        "ambiguous_cookbooks": 0,
        "matched_products": 0,
        "matched_cookbooks": 0,
        "ingredients_present": 0,
        "ingredient_source_exact_matches": 0,
        "ingredient_source_pair_mismatches": 0,
        "ingredient_count": 0,
        "resolved_ingredient_count": 0,
        "unresolved_ingredient_count": 0,
    }
    if not recipes_path or not recipes_path.is_file():
        return [], empty_stats
    payload = json.loads(recipes_path.read_text(encoding="utf-8"))
    recipes = payload.get("recipes", [])
    stats = dict(empty_stats)
    stats["recipes"] = len(recipes)
    payload_stats = payload.get("stats") or {}
    stats["ingredient_source_exact_matches"] = int(
        payload_stats.get("ingredientSourceExactMatchCount", 0)
    )
    stats["ingredient_source_pair_mismatches"] = int(
        payload_stats.get("ingredientSourcePairMismatchCount", 0)
    )
    stats["ingredient_count"] = int(payload_stats.get("ingredientCount", 0))
    stats["resolved_ingredient_count"] = int(
        payload_stats.get("resolvedIngredientCount", 0)
    )
    stats["unresolved_ingredient_count"] = int(
        payload_stats.get("unresolvedIngredientCount", 0)
    )

    def index_by_name(kind_filter: set[str] | None = None) -> dict[str, list[dict]]:
        result: dict[str, list[dict]] = {}
        for entity in entities:
            if kind_filter and entity.get("kind") not in kind_filter:
                continue
            name = entity.get("name", {}).get("en")
            if name:
                result.setdefault(name.casefold(), []).append(entity)
        return result

    product_by_name = index_by_name({"item", "weapon", "armor", "accessory", "ash_of_war", "spell"})
    cookbook_by_name = index_by_name({"item"})
    entity_by_id = {entity["id"]: entity for entity in entities}
    relations = []
    source = payload.get("source", {})

    def cookbook_candidates(source_name: str) -> list[dict]:
        candidates = cookbook_by_name.get(source_name.casefold(), [])
        if candidates:
            return candidates
        # The local official dump uses parentheses for a few cookbook names,
        # while the public event-flag source uses square brackets.
        alternate = re.sub(r"\s+\[(\d+)\]$", r" (\1)", source_name)
        return cookbook_by_name.get(alternate.casefold(), [])

    for recipe in recipes:
        product_name = str(recipe.get("productName") or "")
        cookbook_name = str(recipe.get("cookbookName") or "")
        product_candidates = product_by_name.get(product_name.casefold(), [])
        resolved_product_id = recipe.get("resolvedProductItemId")
        if resolved_product_id:
            resolved_product = entity_by_id.get(resolved_product_id)
            product_candidates = (
                [resolved_product]
                if resolved_product
                and (resolved_product.get("name", {}).get("en") or "").casefold()
                == product_name.casefold()
                else []
            )
        elif len(product_candidates) > 1:
            # Crafting creates an inventory Goods record.  If a localized name
            # is shared with a Magic row (for example Golden Vow), the single
            # Goods entity is the only valid product in this context.
            goods_candidates = [
                candidate for candidate in product_candidates
                if candidate.get("kind") == "item"
            ]
            if len(goods_candidates) == 1:
                product_candidates = goods_candidates
        cookbook_candidates_for_recipe = cookbook_candidates(cookbook_name)
        resolved_cookbook_id = recipe.get("resolvedCookbookItemId")
        if resolved_cookbook_id:
            resolved_cookbook = entity_by_id.get(resolved_cookbook_id)
            cookbook_candidates_for_recipe = (
                [resolved_cookbook]
                if resolved_cookbook
                and resolved_cookbook.get("kind") == "item"
                and (resolved_cookbook.get("name", {}).get("en") or "").casefold()
                == cookbook_name.casefold()
                else []
            )
        if len(product_candidates) != 1:
            stats["ambiguous_products" if product_candidates else "unmatched_products"] += 1
            continue
        if len(cookbook_candidates_for_recipe) != 1:
            stats["ambiguous_cookbooks" if cookbook_candidates_for_recipe else "unmatched_cookbooks"] += 1
            continue
        product = product_candidates[0]
        cookbook = cookbook_candidates_for_recipe[0]
        stats["matched_products"] += 1
        stats["matched_cookbooks"] += 1
        if recipe.get("ingredients"):
            stats["ingredients_present"] += 1
        source_recipe_id = recipe.get("sourceRecipeId")
        unlock_source = recipe.get("unlockSource") or {}
        if unlock_source:
            source_label = unlock_source.get("id") or "online cookbook dataset"
            evidence = [
                f"{source_label} recipe {source_recipe_id} exact product-name match",
                f"{source_label} cookbook unlock {cookbook_name} -> {product_name}",
                f"{source_label} source commit {unlock_source.get('commit') or 'snapshot'}",
            ]
            verification = unlock_source.get("verification") or (
                "online_dataset_cookbook_product_exact_unique_official_name_match"
            )
        else:
            evidence = [
                f"Smithbox cookbook recipe {source_recipe_id} exact product-name match",
                f"Smithbox cookbook unlock {cookbook_name} -> {product_name}",
                f"Smithbox source commit {source.get('commit') or 'snapshot'}",
            ]
            verification = "online_cookbook_product_exact_unique_official_name_match"
        ingredient_source = payload.get("ingredientSource")
        if recipe.get("ingredients") and ingredient_source:
            evidence.append(
                "Public cookbook material table exact product/cookbook match"
            )
        relations.append({
            "id": f"craft-recipe-{source_recipe_id}",
            "from": cookbook["id"],
            "method": "craft",
            "items": [{
                "item": product["id"],
                "name": product["name"],
                "num": recipe.get("productQuantity"),
                "quantityStatus": recipe.get("productQuantityStatus", "not_stated_in_source"),
                "craftProduct": True,
            }],
            "craftRecipe": {
                "sourceRecipeId": source_recipe_id,
                "sourceLine": recipe.get("sourceLine"),
                "sourceProductName": product_name,
                "sourceCookbookName": cookbook_name,
                "cookbookItemId": cookbook["id"],
                "canonicalCookbookName": cookbook["name"],
                "productItemId": product["id"],
                "canonicalProductName": product["name"],
                "productQuantity": recipe.get("productQuantity"),
                "productQuantityStatus": recipe.get("productQuantityStatus", "not_stated_in_source"),
                "ingredients": recipe.get("ingredients", []),
                "ingredientsStatus": recipe.get("ingredientsStatus", "not_present_in_source"),
                "ingredientSourceLine": recipe.get("ingredientSourceLine"),
                "ingredientSource": ingredient_source,
                "unlockSource": unlock_source or None,
            },
            "evidence": evidence,
            "verification": verification,
        })
    stats["matched"] = len(relations)
    return relations, stats


DEFAULT_CRAFT_RECIPE_IDS = {30000, 30100, 30200, 30600, 30700}


def attach_local_craft_recipes(
    recipe_rows: list[dict],
    material_rows: list[dict],
    entities: list[dict],
    online_relations: list[dict],
) -> tuple[list[dict], dict[str, int], list[dict]]:
    """Attach exact local recipe products and materials to craft relations.

    ``ShopLineupParam_Recipe`` is the game's recipe table.  Cookbook unlock
    identity is deliberately kept separate: the local table proves product,
    output quantity and material set, while the pinned event-flag catalog
    proves cookbook ownership.  The five rows labelled ``Default`` by that
    catalog are available from the Crafting Kit and receive independent local
    relations.  Any disagreement remains a local coverage gap and cannot
    invalidate unrelated recipes.
    """
    by_param_row: dict[tuple[str, int], list[dict]] = {}
    entity_by_id = {entity["id"]: entity for entity in entities}
    for entity in entities:
        for signifier in entity.get("signifiers", []):
            if signifier.get("type") != "param":
                continue
            for row_id in signifier.get("rows", []):
                by_param_row.setdefault(
                    (str(signifier.get("param")), int(row_id)), []
                ).append(entity)

    material_by_id = {int(row["id"]): row["cells"] for row in material_rows}
    online_by_source_id = {
        relation.get("craftRecipe", {}).get("sourceRecipeId"): relation
        for relation in online_relations
    }
    online_by_product: dict[str, list[dict]] = {}
    for relation in online_relations:
        product_id = relation.get("craftRecipe", {}).get("productItemId")
        if product_id:
            online_by_product.setdefault(product_id, []).append(relation)

    stats = {
        "local_rows": len(recipe_rows),
        "usable_rows": 0,
        "online_enriched": 0,
        "default_relations": 0,
        "unresolved_products": 0,
        "unresolved_materials": 0,
        "unbound_unlocks": 0,
    }
    default_relations: list[dict] = []
    gaps: list[dict] = []

    for row in recipe_rows:
        recipe_id = int(row["id"])
        cells = row["cells"]
        material_set_id = int(cells.get("mtrlId", -1))
        # Row 1 is a carried-over non-recipe record and has no material set.
        if material_set_id < 0:
            continue
        stats["usable_rows"] += 1
        equip_type = int(cells["equipType"])
        fmg_table = SHOP_EQUIP_TABLES.get(equip_type)
        param_table = FMG_TO_PARAM.get(fmg_table or "")
        product_candidates = by_param_row.get(
            (param_table or "", int(cells["equipId"])), []
        )
        if len(product_candidates) != 1:
            stats["unresolved_products"] += 1
            gaps.append({
                "id": f"local-craft-product-{recipe_id}",
                "method": "craft",
                "status": "local_recipe_product_unresolved",
                "sourceRecipeId": recipe_id,
                "sourceParam": "ShopLineupParam_Recipe",
                "sourceEquipType": equip_type,
                "sourceEquipId": cells["equipId"],
                "candidateEntityIds": [candidate["id"] for candidate in product_candidates],
                "verification": "local_param_unresolved",
            })
            continue
        product = product_candidates[0]

        material_cells = material_by_id.get(material_set_id)
        ingredients = []
        unresolved_ingredients = []
        if material_cells is None:
            unresolved_ingredients.append({"materialSetId": material_set_id})
        else:
            material_param = {1: "EquipParamWeapon", 4: "EquipParamGoods"}
            for index in range(1, 7):
                suffix = f"{index:02d}"
                material_id = int(material_cells.get(f"materialId{suffix}", -1))
                quantity = int(material_cells.get(f"itemNum{suffix}", -1))
                if material_id < 0 or quantity < 0:
                    continue
                category = int(material_cells.get(f"materialCate{suffix}", -1))
                candidates = by_param_row.get(
                    (material_param.get(category, ""), material_id), []
                )
                if len(candidates) == 1:
                    ingredient = candidates[0]
                    ingredients.append({
                        "itemId": ingredient["id"],
                        "canonicalName": ingredient["name"],
                        "sourceParamId": material_id,
                        "sourceMaterialCategory": category,
                        "quantity": quantity,
                        "quantityStatus": "local_param_exact",
                    })
                else:
                    unresolved_ingredients.append({
                        "sourceParamId": material_id,
                        "sourceMaterialCategory": category,
                        "quantity": quantity,
                        "candidateEntityIds": [candidate["id"] for candidate in candidates],
                    })
        if unresolved_ingredients:
            stats["unresolved_materials"] += len(unresolved_ingredients)

        local_recipe = {
            "sourceParam": "ShopLineupParam_Recipe",
            "sourceRecipeId": recipe_id,
            "sourceProductParam": param_table,
            "sourceProductParamId": int(cells["equipId"]),
            "productItemId": product["id"],
            "productQuantity": int(cells.get("setNum", 1)),
            "materialSetParam": "EquipMtrlSetParam",
            "materialSetId": material_set_id,
            "ingredients": ingredients,
            "unresolvedIngredients": unresolved_ingredients,
            "verification": (
                "local_param_exact"
                if not unresolved_ingredients else "local_param_partial"
            ),
        }

        relation = online_by_source_id.get(recipe_id)
        if relation is None:
            product_relations = online_by_product.get(product["id"], [])
            if len(product_relations) == 1:
                relation = product_relations[0]
        if relation is not None:
            relation["localRecipe"] = local_recipe
            relation["evidence"].extend([
                f"regulation.bin ShopLineupParam_Recipe row {recipe_id}",
                f"regulation.bin EquipMtrlSetParam row {material_set_id}",
            ])
            stats["online_enriched"] += 1
            continue

        if recipe_id in DEFAULT_CRAFT_RECIPE_IDS:
            crafting_kit = entity_by_id["item_crafting_kit"]
            default_relations.append({
                "id": f"craft-default-{recipe_id}",
                "from": crafting_kit["id"],
                "method": "craft",
                "items": [{
                    "item": product["id"],
                    "name": product["name"],
                    "num": int(cells.get("setNum", 1)),
                    "quantityStatus": "local_param_exact",
                    "craftProduct": True,
                }],
                "craftRecipe": {
                    "sourceRecipeId": recipe_id,
                    "unlockType": "default",
                    "unlockItemId": crafting_kit["id"],
                    "productItemId": product["id"],
                    "canonicalProductName": product["name"],
                },
                "localRecipe": local_recipe,
                "evidence": [
                    f"regulation.bin ShopLineupParam_Recipe row {recipe_id}",
                    f"regulation.bin EquipMtrlSetParam row {material_set_id}",
                    f"pinned Smithbox event-flag catalog recipe {recipe_id} labelled Default",
                ],
                "verification": "local_recipe_and_pinned_default_unlock_exact",
            })
            stats["default_relations"] += 1
            continue

        stats["unbound_unlocks"] += 1
        gaps.append({
            "id": f"local-craft-unlock-{recipe_id}",
            "method": "craft",
            "status": "local_recipe_unlock_unbound",
            "sourceRecipeId": recipe_id,
            "productItemId": product["id"],
            "localRecipe": local_recipe,
            "verification": "local_product_and_materials_without_unlock_identity",
        })

    return default_relations, stats, gaps


def build_initial_loadout_relations(
    base_class_rows: list[dict],
    chara_init_rows: list[dict],
    char_make_top_rows: list[dict],
    char_make_list_rows: list[dict],
    entities: list[dict],
) -> tuple[list[dict], dict[str, int], list[dict]]:
    """Build player class and selectable-gift acquisitions from local params.

    Only player-selectable rows are followed: ``BaseChrSelectMenuParam`` gives
    the ten concrete class loadouts, and character-creation command 24 gives
    the selectable gift table.  Arbitrary ``CharaInitParam`` rows used by
    non-player characters are never treated as player acquisitions.
    """
    by_param_row: dict[tuple[str, int], list[dict]] = {}
    for entity in entities:
        for signifier in entity.get("signifiers", []):
            if signifier.get("type") != "param":
                continue
            for row_id in signifier.get("rows", []):
                by_param_row.setdefault(
                    (str(signifier.get("param")), int(row_id)), []
                ).append(entity)

    chara_by_id = {int(row["id"]): row["cells"] for row in chara_init_rows}
    class_rows = [
        row for row in base_class_rows if 2000 <= int(row["id"]) <= 2009
    ]
    slot_specs = [
        ("equip_Wep_Right", "EquipParamWeapon", None),
        ("equip_Subwep_Right", "EquipParamWeapon", None),
        ("equip_Wep_Left", "EquipParamWeapon", None),
        ("equip_Subwep_Left", "EquipParamWeapon", None),
        ("equip_Arrow", "EquipParamWeapon", None),
        ("equip_Bolt", "EquipParamWeapon", None),
        ("equip_SubArrow", "EquipParamWeapon", None),
        ("equip_SubBolt", "EquipParamWeapon", None),
        ("equip_Helm", "EquipParamProtector", None),
        ("equip_Armer", "EquipParamProtector", None),
        ("equip_Gaunt", "EquipParamProtector", None),
        ("equip_Leg", "EquipParamProtector", None),
        ("equip_Accessory01", "EquipParamAccessory", None),
        ("equip_Accessory02", "EquipParamAccessory", None),
        ("equip_Accessory03", "EquipParamAccessory", None),
        ("equip_Accessory04", "EquipParamAccessory", None),
    ]
    slot_specs.extend(
        (f"equip_Spell_{index:02d}", "Magic", None) for index in range(1, 8)
    )
    slot_specs.extend(
        (f"item_{index:02d}", "EquipParamGoods", f"itemNum_{index:02d}")
        for index in range(1, 11)
    )
    slot_specs.extend(
        (
            f"secondaryItem_{index:02d}",
            "EquipParamGoods",
            f"secondaryItemNum_{index:02d}",
        )
        for index in range(1, 7)
    )

    stats = {
        "selectable_class_count": len(class_rows),
        "class_relation_count": 0,
        "gift_option_count": 0,
        "gift_relation_count": 0,
        "unresolved_slot_count": 0,
    }
    gaps: list[dict] = []
    grouped: dict[str, dict] = {}

    def add_slots(cells: dict, source: dict) -> None:
        for slot, param, quantity_slot in slot_specs:
            value = int(cells.get(slot, -1))
            if value < 0:
                continue
            candidates = by_param_row.get((param, value), [])
            if len(candidates) != 1:
                stats["unresolved_slot_count"] += 1
                gaps.append({
                    "id": f"initial-loadout-slot-{source['sourceRowId']}-{slot}",
                    "method": "initial_loadout",
                    "status": "initial_loadout_slot_unresolved",
                    "source": source,
                    "sourceSlot": slot,
                    "sourceParam": param,
                    "sourceParamId": value,
                    "candidateEntityIds": [candidate["id"] for candidate in candidates],
                    "verification": "local_param_unresolved",
                })
                continue
            entity = candidates[0]
            quantity = int(cells.get(quantity_slot, 1)) if quantity_slot else 1
            if quantity < 1:
                quantity = 1
            record = grouped.setdefault(entity["id"], {
                "entity": entity,
                "sources": [],
                "quantity": quantity,
            })
            record["quantity"] = max(record["quantity"], quantity)
            record["sources"].append({**source, "slot": slot, "quantity": quantity})

    for row in class_rows:
        cells = row["cells"]
        loadout_id = int(cells["chrInitParam"])
        loadout = chara_by_id.get(loadout_id)
        if loadout is None:
            gaps.append({
                "id": f"initial-loadout-class-{row['id']}",
                "method": "initial_loadout",
                "status": "selectable_class_loadout_missing",
                "baseChrSelectMenuRow": row["id"],
                "charaInitParamRow": loadout_id,
                "verification": "local_param_missing_reference",
            })
            continue
        add_slots(loadout, {
            "sourceType": "selectable_starting_class",
            "sourceRowId": loadout_id,
            "baseChrSelectMenuRow": int(row["id"]),
            "originCharaInitRow": int(cells["originChrInitParam"]),
        })

    relations: list[dict] = []
    for entity_id, record in sorted(grouped.items()):
        entity = record["entity"]
        relations.append({
            "id": f"initial-loadout-class-{entity_id}",
            "from": None,
            "method": "initial_loadout",
            "items": [{
                "item": entity_id,
                "name": entity["name"],
                "num": record["quantity"],
                "quantityStatus": "local_param_exact",
            }],
            "initialLoadoutBinding": {
                "sourceType": "selectable_starting_class",
                "sources": record["sources"],
            },
            "evidence": [
                "local BaseChrSelectMenuParam selectable class reference",
                "local CharaInitParam concrete loadout slots",
            ],
            "verification": "local_selectable_class_loadout_exact",
        })
    stats["class_relation_count"] = len(relations)

    gift_top_rows = [
        row for row in char_make_top_rows
        if int(row["cells"].get("commandType", -1)) == 24
    ]
    if len(gift_top_rows) == 1:
        gift_table_id = int(gift_top_rows[0]["cells"]["tableId"])
        gift_options = [
            row for row in char_make_list_rows
            if gift_table_id <= int(row["id"]) < gift_table_id + 100
        ]
        stats["gift_option_count"] = len(gift_options)
        for option in gift_options:
            value = int(option["cells"]["value"])
            gift_row_id = 2400 + value
            gift_cells = chara_by_id.get(gift_row_id)
            if gift_cells is None:
                gaps.append({
                    "id": f"initial-gift-{option['id']}",
                    "method": "initial_loadout",
                    "status": "selectable_gift_loadout_missing",
                    "charMakeMenuListItemRow": option["id"],
                    "charaInitParamRow": gift_row_id,
                    "verification": "local_param_missing_reference",
                })
                continue
            gift_grouped: dict[str, dict] = {}
            old_grouped = grouped
            grouped = gift_grouped
            add_slots(gift_cells, {
                "sourceType": "selectable_starting_gift",
                "sourceRowId": gift_row_id,
                "charMakeMenuTopRow": int(gift_top_rows[0]["id"]),
                "charMakeMenuListItemRow": int(option["id"]),
                "selectionValue": value,
            })
            grouped = old_grouped
            for entity_id, record in sorted(gift_grouped.items()):
                entity = record["entity"]
                relations.append({
                    "id": f"initial-loadout-gift-{option['id']}-{entity_id}",
                    "from": None,
                    "method": "initial_loadout",
                    "items": [{
                        "item": entity_id,
                        "name": entity["name"],
                        "num": record["quantity"],
                        "quantityStatus": "local_param_exact",
                    }],
                    "initialLoadoutBinding": {
                        "sourceType": "selectable_starting_gift",
                        "sources": record["sources"],
                    },
                    "evidence": [
                        "local CharMakeMenuTopParam gift-selection command",
                        "local CharMakeMenuListItemParam selection value",
                        "local CharaInitParam gift loadout slots",
                    ],
                    "verification": "local_selectable_starting_gift_exact",
                })
                stats["gift_relation_count"] += 1
    else:
        gaps.append({
            "id": "initial-gift-table",
            "method": "initial_loadout",
            "status": "gift_selection_table_ambiguous",
            "candidateTopRows": [row["id"] for row in gift_top_rows],
            "verification": "local_param_unresolved",
        })

    return relations, stats, gaps


def attach_quest_npc_endpoints(
    relations: list[dict],
    entities: list[dict],
    spawn_path: Path | None,
) -> int:
    """Attach copied local NPC MSB instances without inventing route nodes.

    Quest rewards identify a source character, but the quest binding itself is
    not a route graph.  The local enemy/NPC spawn catalog still gives us useful
    independent coordinate evidence for every known NpcParam row.  Publish
    those instances as coordinate endpoints and keep the formal topology
    binding empty until a real route-node correspondence is proven.
    """
    if not spawn_path or not spawn_path.is_file():
        return 0
    payload = json.loads(spawn_path.read_text(encoding="utf-8"))
    by_npc = {
        str(binding["npcParamId"]): binding.get("instances", [])
        for binding in payload.get("bindings", [])
    }
    rows_by_entity: dict[str, list[int]] = {}
    for entity in entities:
        rows = next(
            (
                signifier.get("rows", [])
                for signifier in entity.get("signifiers", [])
                if signifier.get("type") == "param"
                and signifier.get("param") == "NpcParam"
            ),
            [],
        )
        if rows:
            rows_by_entity[entity["id"]] = [int(row) for row in rows]

    endpoint_count = 0
    for relation in relations:
        source_id = relation.get("from")
        instances: list[dict] = []
        seen: set[tuple] = set()
        for row_id in rows_by_entity.get(source_id, []):
            for source_instance in by_npc.get(str(row_id), []):
                key = (
                    source_instance.get("map"),
                    source_instance.get("part"),
                    source_instance.get("npcParamId"),
                )
                if key in seen:
                    continue
                seen.add(key)
                instance = dict(source_instance)
                instance["kind"] = "quest_npc_endpoint"
                instance["questRewardRole"] = "npc_delivery_or_quest_actor"
                instance["topologyBinding"] = {
                    "status": "coordinate_endpoint",
                    "routeNodeIds": [],
                    "semanticNodeIds": [],
                    "reason": "local MSB NPC coordinate; no formal quest NPC route node",
                }
                instance["sourceEvidence"] = [
                    *source_instance.get("sourceEvidence", []),
                    "quest reward source character resolved through local NpcParam",
                ]
                instances.append(instance)
        if instances:
            relation["endpointInstances"] = instances
            relation.setdefault("evidence", []).append(
                "copied local MSB NPC endpoint catalog"
            )
            endpoint_count += len(instances)
    return endpoint_count


def build_quest_reward_relations(
    quest_rewards_path: Path | None = None,
    entities: list[dict] | None = None,
    spawn_path: Path | None = None,
) -> tuple[list[dict], int]:
    """Expose conservative NPC quest-step/local award intersections."""
    if not quest_rewards_path or not quest_rewards_path.is_file():
        return [], 0
    payload = json.loads(quest_rewards_path.read_text(encoding="utf-8"))
    relations = []
    for binding in payload.get("bindings", []):
        items = [
            {
                "item": item["item"],
                "name": item["name"],
                "num": item.get("num"),
                **{
                    key: item[key]
                    for key in ("quantityStatus",)
                    if key in item
                },
            }
            for item in binding.get("items", [])
            if item.get("item") and item.get("name", {}).get("en")
        ]
        if not items:
            continue
        relations.append({
            "id": binding["id"],
            "from": binding.get("from"),
            "method": "quest_reward",
            "items": items,
            "questRewardBinding": binding,
            "evidence": binding.get("evidence", []),
            "verification": binding.get("verification", "local_award_external_quest_name_and_flag_overlap"),
        })
    endpoint_count = attach_quest_npc_endpoints(
        relations, entities or [], spawn_path
    )
    return relations, endpoint_count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--param-dir", type=Path, required=True)
    parser.add_argument("--registry", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "entity-registry.json")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "acquisition-registry.json")
    parser.add_argument("--enemy-spawns", type=Path, default=DEFAULT_ENEMY_SPAWNS)
    parser.add_argument("--merchant-shops", type=Path, default=DEFAULT_MERCHANT_SHOPS)
    parser.add_argument("--boss-endpoints", type=Path, default=DEFAULT_BOSS_ENDPOINTS)
    parser.add_argument("--event-rewards", type=Path, default=DEFAULT_EVENT_REWARDS)
    parser.add_argument("--talk-item-lots", type=Path, default=DEFAULT_TALK_ITEM_LOTS)
    parser.add_argument("--quest-rewards", type=Path, default=DEFAULT_QUEST_REWARDS)
    parser.add_argument("--gesture-acquisitions", type=Path, default=DEFAULT_GESTURE_ACQUISITIONS)
    parser.add_argument("--tutorial-unlocks", type=Path, default=DEFAULT_TUTORIAL_UNLOCKS)
    parser.add_argument("--online-markers", type=Path, default=DEFAULT_ONLINE_MARKERS)
    parser.add_argument("--online-guide-items", type=Path, default=DEFAULT_ONLINE_GUIDE_ITEMS)
    parser.add_argument("--online-item-map", type=Path, default=DEFAULT_ONLINE_ITEM_MAP)
    parser.add_argument("--online-cookbook-recipes", type=Path, default=DEFAULT_ONLINE_COOKBOOK_RECIPES)
    parser.add_argument("--pickup-bindings", type=Path, default=DEFAULT_PICKUP_BINDINGS)
    parser.add_argument("--abstract-topology-graph", type=Path,
                        default=DEFAULT_ABSTRACT_TOPOLOGY_GRAPH)
    args = parser.parse_args()

    print("loading FMG name tables ...")
    tables = load_name_tables()

    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    # Make repeated builds idempotent.  The previous run may already have
    # merged generated enemy/shop/supplemental records into the registry; the
    # canonical source pass must start from the equipment/goods entities only.
    entities = [
        entity for entity in registry["entities"]
        if entity.get("kind") not in ("enemy", "npc")
        and not entity.get("id", "").startswith(("npc_shop_", "shop_context_", "shop_vendor_"))
        and not any(s.get("type") == "acquisition_name" for s in entity.get("signifiers", []))
    ]
    print(f"registry entities: {len(entities)}")

    npc_rows = param_rows(args.param_dir, "NpcParam")
    enemies, row_to_entity = build_enemies_npcs(npc_rows, tables)
    print(f"named enemy/npc entities: {len(enemies)}")

    lot_enemy = param_rows(args.param_dir, "ItemLotParam_enemy")
    drops = build_drops(npc_rows, row_to_entity, lot_enemy, tables)
    drop_coverage, drop_gaps = summarize_enemy_drop_coverage(
        npc_rows, lot_enemy, tables, row_to_entity
    )
    print(f"drop relations: {len(drops)}")
    print(
        "drop coverage: "
        f"roots={drop_coverage['dropRootCount']}; "
        f"resolved={drop_coverage['dropRootWithResolvedItems']}; "
        f"gaps={drop_coverage['dropGapCount']} "
        f"(missing={drop_coverage['dropRootMissingLotRowCount']}, "
        f"empty={drop_coverage['dropRootEmptyLotCount']}, "
        f"unresolved-names={drop_coverage['dropRootWithUnresolvedNamesOnly']})"
    )

    lot_map = param_rows(args.param_dir, "ItemLotParam_map")
    boss_lots = set()
    import glob as _glob
    for bp in _glob.glob(str(ROOT / "data" / "v1" / "entities" / "boss-rewards.json")):
        for br in json.loads(Path(bp).read_text(encoding="utf-8"))["rewards"]:
            boss_lots.add(br["lot"]["rowId"])
    pickup_root_ids: set[int] = set()
    orphan_treasure_exclusions_by_lot: dict[int, list[dict]] = defaultdict(list)
    if args.pickup_bindings.is_file():
        pickup_payload = json.loads(args.pickup_bindings.read_text(encoding="utf-8"))
        pickup_root_ids = {
            int(binding["lot"])
            for binding in pickup_payload.get("bindings", [])
            if binding.get("lot") is not None
        }
        for exclusion in pickup_payload.get("sourceExclusions", []):
            if isinstance(exclusion.get("lot"), int):
                orphan_treasure_exclusions_by_lot[exclusion["lot"]].append(exclusion)
    all_map_lot_relations = build_pickups(lot_map, tables)
    pickups = [
        x for x in build_pickups(lot_map, tables, pickup_root_ids)
        if x["lot"]["rowId"] not in boss_lots
    ]
    published_pickup_rows = {
        int(row_id)
        for relation in pickups
        for row_id in relation.get("sourceItemLotRows", [])
    }
    event_reward_payload = (
        json.loads(args.event_rewards.read_text(encoding="utf-8"))
        if args.event_rewards.is_file() else {"bindings": []}
    )
    event_bindings_by_lot: dict[int, list[str]] = defaultdict(list)
    event_reward_rows: set[int] = set()
    for binding in event_reward_payload.get("bindings", []):
        row_id = (binding.get("itemLot") or {}).get("rowId")
        if isinstance(row_id, int):
            event_bindings_by_lot[row_id].append(binding.get("id"))
        for value in binding.get("sourceItemLotRows", []):
            if not isinstance(value, int):
                continue
            event_reward_rows.add(value)
            if binding.get("id") not in event_bindings_by_lot[value]:
                event_bindings_by_lot[value].append(binding.get("id"))
    talk_reward_payload = (
        json.loads(args.talk_item_lots.read_text(encoding="utf-8"))
        if args.talk_item_lots.is_file() else {"bindings": []}
    )
    talk_bindings_by_lot: dict[int, list[str]] = defaultdict(list)
    talk_reward_rows: set[int] = set()
    for binding in talk_reward_payload.get("bindings", []):
        for value in binding.get("sourceItemLotRows", []):
            if not isinstance(value, int):
                continue
            talk_reward_rows.add(value)
            if binding.get("id") not in talk_bindings_by_lot[value]:
                talk_bindings_by_lot[value].append(binding.get("id"))
    non_pickup_param_relations = [
        relation for relation in all_map_lot_relations
        if relation["lot"]["rowId"] not in published_pickup_rows
        and relation["lot"]["rowId"] not in boss_lots
    ]
    pickup_source_exclusions = []
    orphan_treasure_exclusion_count = 0
    event_reward_exclusion_count = 0
    talk_reward_exclusion_count = 0
    unclassified_map_lot_gaps = []
    for relation in non_pickup_param_relations:
        row_id = relation["lot"]["rowId"]
        if row_id in orphan_treasure_exclusions_by_lot:
            orphan_treasure_exclusion_count += 1
            orphan_records = orphan_treasure_exclusions_by_lot[row_id]
            pickup_source_exclusions.append({
                "id": f"item-lot-map-exclusion-orphan-treasure-{row_id}",
                "method": "pickup",
                "status": "orphan_treasure_event_without_part",
                "sourceItemLotRoot": row_id,
                "sourceItemLotRows": relation.get("sourceItemLotRows", []),
                "sourceTreasureEventIds": [row.get("id") for row in orphan_records],
                "evidence": [
                    f"regulation.bin ItemLotParam_map row {row_id}",
                    *[
                        evidence
                        for row in orphan_records
                        for evidence in row.get("evidence", [])
                    ],
                    "not published as a fixed pickup because no positioned MSBE Part exists",
                ],
                "verification": "local_msbe_uninstantiated_treasure",
            })
        elif row_id in event_reward_rows:
            event_reward_exclusion_count += 1
            pickup_source_exclusions.append({
                "id": f"item-lot-map-exclusion-{row_id}",
                "method": "event_reward",
                "status": "classified_event_award_not_fixed_pickup",
                "sourceItemLotRoot": row_id,
                "sourceItemLotRows": relation.get("sourceItemLotRows", []),
                "eventRewardBindingIds": event_bindings_by_lot.get(row_id, []),
                "evidence": [
                    f"regulation.bin ItemLotParam_map row {row_id}",
                    "local EMEVD AwardItemLot reference; published through event/quest reward relations",
                    "no copied MSB Treasure reference for this lot root",
                ],
                "verification": "local_param_and_emevd_classified",
            })
        elif row_id in talk_reward_rows:
            talk_reward_exclusion_count += 1
            pickup_source_exclusions.append({
                "id": f"item-lot-map-exclusion-talk-{row_id}",
                "method": "talk_reward",
                "status": "classified_talk_award_not_fixed_pickup",
                "sourceItemLotRoot": row_id,
                "sourceItemLotRows": relation.get("sourceItemLotRows", []),
                "talkItemLotBindingIds": talk_bindings_by_lot.get(row_id, []),
                "evidence": [
                    f"regulation.bin ItemLotParam_map row {row_id}",
                    "local Talk ESD AwardItemLot reference; published as a talk reward",
                    "no copied MSB Treasure reference for this lot root",
                ],
                "verification": "local_param_and_talk_esd_classified",
            })
        else:
            unclassified_map_lot_gaps.append({
                "id": f"item-lot-map-unclassified-{row_id}",
                "method": "unclassified_param",
                "status": "unreferenced_item_lot_param_map",
                "sourceItemLotRoot": row_id,
                "sourceItemLotRows": relation.get("sourceItemLotRows", []),
                "itemCount": len(relation.get("items", [])),
                "evidence": [
                    f"regulation.bin ItemLotParam_map row {row_id}",
                    "no copied MSB Treasure, EMEVD reward, or Boss reward root reference",
                    "not published as a fixed pickup until a real acquisition mechanism is proven",
                ],
                "verification": "local_param_unclassified",
            })
    pickup_endpoint_stats = attach_pickup_endpoints(pickups, args.pickup_bindings)
    pickup_gaps, pickup_gap_stats = summarize_pickup_coverage_gaps(pickups)
    print(f"pickup relations: {len(pickups)} (excluding {len(boss_lots)} boss reward lots)")
    print(
        "non-pickup map lots: "
        f"event-classified={event_reward_exclusion_count}; "
        f"talk-classified={talk_reward_exclusion_count}; "
        f"orphan-treasure={orphan_treasure_exclusion_count}; "
        f"unclassified={len(unclassified_map_lot_gaps)}"
    )
    print(
        "pickup endpoints: "
        f"relations={pickup_endpoint_stats['endpoint_relations']}; "
        f"instances={pickup_endpoint_stats['endpoint_instances']}; "
        f"without-coordinates={pickup_endpoint_stats['source_without_coordinates']}; "
        f"missing-bindings={pickup_endpoint_stats['missing_bindings']}; "
        f"coverage-gaps={pickup_gap_stats['coverageGapCount']}"
    )

    shop_rows = param_rows(args.param_dir, "ShopLineupParam")
    shops, shop_entities, shop_stats = build_shops(
        shop_rows,
        tables,
        param_rows(args.param_dir, "EquipParamCustomWeapon"),
        param_rows(args.param_dir, "EquipMtrlSetParam"),
        args.merchant_shops,
        entities + enemies,
    )
    shop_gaps, shop_gap_stats = summarize_shop_coverage_gaps(shops)
    shop_stats.update(shop_gap_stats)
    print(f"shop relations: {len(shops)}; details={shop_stats}")

    seen = set()
    deduped_by_key = {}
    deduped = []
    for d in drops:
        key = (d["from"], d["lot"]["rowId"])
        if key in seen:
            existing = deduped_by_key[key]
            existing.setdefault("sourceNpcParamRows", []).extend(d.get("sourceNpcParamRows", []))
            existing.setdefault("sourceItemLotRows", []).extend(d.get("sourceItemLotRows", []))
            continue
        seen.add(key)
        deduped_by_key[key] = d
        deduped.append(d)
    for d in deduped:
        d["sourceNpcParamRows"] = sorted(set(d.get("sourceNpcParamRows", [])))
        d["sourceItemLotRows"] = sorted(set(d.get("sourceItemLotRows", [])))
    drops = deduped
    print(f"drop relations after dedupe: {len(drops)}")
    drop_coverage["dropRelationRootCount"] = len({
        relation["lot"]["rowId"] for relation in drops
    })
    drop_coverage["dropRelationCount"] = len(drops)
    drop_coverage["dropRelationSourceNpcRowCount"] = len({
        row_id
        for relation in drops
        for row_id in relation.get("sourceNpcParamRows", [])
    })
    drop_endpoint_count = attach_enemy_spawn_endpoints(drops, args.enemy_spawns)
    print(f"enemy spawn endpoints attached: {drop_endpoint_count}")

    boss_rewards = build_boss_reward_relations(entities + enemies, tables, args.boss_endpoints)
    print(f"boss reward relations: {len(boss_rewards)}")
    event_rewards = build_event_reward_relations(args.event_rewards)
    print(f"event reward relations: {len(event_rewards)}")
    talk_rewards = build_talk_reward_relations(args.talk_item_lots)
    print(f"talk reward relations: {len(talk_rewards)}")
    gesture_acquisitions = build_gesture_acquisition_relations(args.gesture_acquisitions)
    print(f"gesture acquisition relations: {len(gesture_acquisitions)}")
    tutorial_unlocks = build_tutorial_unlock_relations(args.tutorial_unlocks)
    print(f"tutorial unlock relations: {len(tutorial_unlocks)}")
    quest_rewards, quest_endpoint_count = build_quest_reward_relations(
        args.quest_rewards, entities + enemies, args.enemy_spawns
    )
    print(
        f"quest reward relations: {len(quest_rewards)}; "
        f"NPC endpoints={quest_endpoint_count}"
    )

    online_map_relations, online_map_stats, online_map_gaps = build_online_map_relations(
        args.online_markers, entities + enemies
    )
    print(
        "online map markers: "
        f"{online_map_stats['matched']} matched / "
        f"{online_map_stats['markers']} total; "
        f"unmatched={online_map_stats['unmatched']}; "
        f"ambiguous={online_map_stats['ambiguous']}; "
        f"gaps={len(online_map_gaps)}"
    )

    online_guide_relations, online_guide_stats, online_guide_gaps = build_online_guide_item_relations(
        args.online_guide_items, entities + enemies
    )
    print(
        "online guide items: "
        f"{online_guide_stats['matched']} matched / "
        f"{online_guide_stats['map_items']} with map / "
        f"{online_guide_stats['items']} total; "
        f"unmatched={online_guide_stats['unmatched']}; "
        f"ambiguous={online_guide_stats['ambiguous']}; "
        f"no-map={online_guide_stats['no_map']}; "
        f"gaps={len(online_guide_gaps)}"
    )

    online_item_map_relations, online_item_map_stats, online_item_map_gaps = build_online_item_map_relations(
        args.online_item_map, entities + enemies
    )
    print(
        "online item map records: "
        f"{online_item_map_stats['matched_records']} matched / "
        f"{online_item_map_stats['records']} total; "
        f"items={online_item_map_stats['matched_item_occurrences']}; "
        f"unmatched={online_item_map_stats['unmatched_item_occurrences']}; "
        f"ambiguous={online_item_map_stats['ambiguous_item_occurrences']}; "
        f"gaps={len(online_item_map_gaps)}"
    )

    online_cookbook_relations, online_cookbook_stats = build_online_cookbook_recipe_relations(
        args.online_cookbook_recipes, entities + enemies
    )
    print(
        "online cookbook recipes: "
        f"{online_cookbook_stats['matched']} matched / "
        f"{online_cookbook_stats['recipes']} total; "
        f"unmatched products={online_cookbook_stats['unmatched_products']}; "
        f"unmatched cookbooks={online_cookbook_stats['unmatched_cookbooks']}"
    )
    local_default_craft_relations, local_recipe_stats, local_recipe_gaps = attach_local_craft_recipes(
        param_rows(args.param_dir, "ShopLineupParam_Recipe"),
        param_rows(args.param_dir, "EquipMtrlSetParam"),
        entities + enemies,
        online_cookbook_relations,
    )
    print(
        "local craft recipes: "
        f"usable={local_recipe_stats['usable_rows']}; "
        f"online-enriched={local_recipe_stats['online_enriched']}; "
        f"defaults={local_recipe_stats['default_relations']}; "
        f"unbound={local_recipe_stats['unbound_unlocks']}; "
        f"unresolved-products={local_recipe_stats['unresolved_products']}; "
        f"unresolved-materials={local_recipe_stats['unresolved_materials']}"
    )
    initial_loadout_relations, initial_loadout_stats, initial_loadout_gaps = build_initial_loadout_relations(
        param_rows(args.param_dir, "BaseChrSelectMenuParam"),
        param_rows(args.param_dir, "CharaInitParam"),
        param_rows(args.param_dir, "CharMakeMenuTopParam"),
        param_rows(args.param_dir, "CharMakeMenuListItemParam"),
        entities + enemies,
    )
    print(f"initial loadouts: {initial_loadout_stats}")

    # Spell Goods rows are now signifiers on the canonical spell entity.
    # Parameter-row resolution below binds each source relation directly to
    # that entity, so name-only duplicate projections are intentionally zero.
    spell_acquisition_projections: list[dict] = []
    print("spell acquisition projections: 0 (canonical signifier merge)")

    # Named entities with no official FMG name (identified by model): the SotE
    # Furnace Golem is a user-category boss with only a community name.
    manual_entities = [{
        "id": "enemy_furnace_golem",
        "kind": "enemy",
        "category": "furnace_golem",
        "class": None,
        "name": {"en": "Furnace Golem", "zh": "鐕冪倝榄斿儚"},
        "signifiers": [{"type": "manual", "note": "no official NpcName; identified by model"}],
        "properties": {},
        "variant_count": 1,
    }]
    all_entities = entities + enemies + shop_entities + manual_entities
    relations = (
        drops + pickups + shops + boss_rewards + event_rewards + talk_rewards
        + gesture_acquisitions
        + tutorial_unlocks
        + quest_rewards + online_map_relations + online_guide_relations
        + online_item_map_relations + online_cookbook_relations
        + local_default_craft_relations
        + initial_loadout_relations
        + spell_acquisition_projections
    )
    topology_map_index = load_map_index(args.abstract_topology_graph)
    topology_map_stats = enrich_relations(relations, topology_map_index)
    print(
        "endpoint map bindings: "
        f"total={topology_map_stats['endpointCount']}; "
        f"exact-map={topology_map_stats['exactMapInstanceEndpointCount']}; "
        f"exact-layer={topology_map_stats['exactMapLayerEndpointCount']}; "
        f"candidate={topology_map_stats['candidateMapEndpointCount']}; "
        f"external={topology_map_stats['externalMapEndpointCount']}; "
        f"unresolved={topology_map_stats['unresolvedMapEndpointCount']}"
    )
    canonicalize_acquisition_items(relations, all_entities)
    print(f"canonical entities after acquisition enrichment: {len(all_entities)}")

    payload = {
        "schema": "errn-acquisition-registry@1",
        "built_at": date.today().isoformat(),
        "built_from": {
            "param_dir": str(args.param_dir),
            "entity_registry": str(args.registry),
            "enemy_spawn_bindings": str(args.enemy_spawns),
            "merchant_shop_bindings": str(args.merchant_shops),
            "boss_reward_endpoints": str(args.boss_endpoints),
            "event_reward_bindings": str(args.event_rewards),
            "talk_item_lot_bindings": str(args.talk_item_lots),
            "quest_reward_bindings": str(args.quest_rewards),
            "gesture_acquisition_bindings": str(args.gesture_acquisitions),
            "tutorial_unlock_bindings": str(args.tutorial_unlocks),
            "online_map_markers": str(args.online_markers),
            "online_guide_items": str(args.online_guide_items),
            "online_item_map": str(args.online_item_map),
            "online_cookbook_recipes": str(args.online_cookbook_recipes),
            "pickup_bindings": str(args.pickup_bindings),
            "abstract_topology_graph": str(args.abstract_topology_graph),
            "item_lot_chain_reference": LOT_CHAIN_REFERENCE,
            "online_map_source": (
                json.loads(args.online_markers.read_text(encoding="utf-8")).get("source", {})
                if args.online_markers.is_file() else {}
            ),
            "online_guide_source": (
                json.loads(args.online_guide_items.read_text(encoding="utf-8")).get("source", {})
                if args.online_guide_items.is_file() else {}
            ),
            "online_item_map_source": (
                json.loads(args.online_item_map.read_text(encoding="utf-8")).get("source", {})
                if args.online_item_map.is_file() else {}
            ),
            "online_cookbook_source": (
                json.loads(args.online_cookbook_recipes.read_text(encoding="utf-8")).get("source", {})
                if args.online_cookbook_recipes.is_file() else {}
            ),
            "online_cookbook_dlc_source": (
                json.loads(args.online_cookbook_recipes.read_text(encoding="utf-8")).get("dlcUnlockSource", {})
                if args.online_cookbook_recipes.is_file() else {}
            ),
            "policy": "Local parameter facts and independently sourced online coordinate endpoints remain separate evidence layers; every item row is a signifier.",
        },
        "stats": {
            "drop": len(drops), "pickup": len(pickups), "shop": len(shops),
            **drop_coverage,
            "pickupBindingCount": pickup_endpoint_stats["bindings"],
            "pickupEndpointRelationCount": pickup_endpoint_stats["endpoint_relations"],
            "pickupEndpointInstanceCount": pickup_endpoint_stats["endpoint_instances"],
            "pickupSourceWithoutCoordinatesCount": pickup_endpoint_stats[
                "source_without_coordinates"
            ],
            "pickupMissingBindingRelationCount": pickup_endpoint_stats["missing_bindings"],
            "pickupEventRewardExclusionCount": event_reward_exclusion_count,
            "pickupTalkRewardExclusionCount": talk_reward_exclusion_count,
            "pickupOrphanTreasureExclusionCount": orphan_treasure_exclusion_count,
            "unclassifiedItemLotParamMapCount": len(unclassified_map_lot_gaps),
            **{f"pickup_{key}": value for key, value in pickup_gap_stats.items()},
            "boss_reward": len(boss_rewards), "enemy_npc_entities": len(enemies),
            "event_reward": len(event_rewards),
            "talk_reward": len(talk_rewards),
            "quest_reward": len(quest_rewards),
            "gesture_acquisition": len(gesture_acquisitions),
            "tutorial_unlock": len(tutorial_unlocks),
            "online_map": len(online_map_relations),
            "onlineMapMarkerCount": online_map_stats["markers"],
            "onlineMapUnmatched": online_map_stats["unmatched"],
            "onlineMapAmbiguous": online_map_stats["ambiguous"],
            "onlineMapCoverageGapCount": online_map_stats["coverage_gap_count"],
            "onlineMapSourceOnlyNameCount": online_map_stats["source_only_name_count"],
            "online_guide": len(online_guide_relations),
            "onlineGuideItemCount": online_guide_stats["items"],
            "onlineGuideMapItemCount": online_guide_stats["map_items"],
            "onlineGuideUnmatched": online_guide_stats["unmatched"],
            "onlineGuideAmbiguous": online_guide_stats["ambiguous"],
            "onlineGuideInvalidMap": online_guide_stats["invalid_map"],
            "onlineGuideNoMap": online_guide_stats["no_map"],
            "onlineGuideCoverageGapCount": online_guide_stats["coverage_gap_count"],
            "onlineGuideSourceOnlyNameCount": online_guide_stats["source_only_name_count"],
            "online_item_map": len(online_item_map_relations),
            "onlineItemMapRecordCount": online_item_map_stats["records"],
            "onlineItemMapItemOccurrenceCount": online_item_map_stats["item_occurrences"],
            "onlineItemMapMatchedItemOccurrenceCount": online_item_map_stats["matched_item_occurrences"],
            "onlineItemMapMatchedByExactNameItemOccurrenceCount": online_item_map_stats[
                "matched_by_exact_name_item_occurrences"
            ],
            "onlineItemMapMatchedBySourceParamIdItemOccurrenceCount": online_item_map_stats[
                "matched_by_source_param_id_item_occurrences"
            ],
            "onlineItemMapUnmatchedItemOccurrenceCount": online_item_map_stats["unmatched_item_occurrences"],
            "onlineItemMapAmbiguousItemOccurrenceCount": online_item_map_stats["ambiguous_item_occurrences"],
            "onlineItemMapSourceParamIdAmbiguousItemOccurrenceCount": online_item_map_stats[
                "source_param_id_ambiguous_item_occurrences"
            ],
            "onlineItemMapPartialRecordCount": online_item_map_stats["partial_records"],
            "onlineItemMapMixedMatchRecordCount": online_item_map_stats["mixed_match_records"],
            "onlineItemMapCoverageGapCount": online_item_map_stats["coverage_gap_count"],
            "onlineItemMapSourceOnlyNameCount": online_item_map_stats["source_only_name_count"],
            "onlineItemMapMatchedEntityCount": online_item_map_stats["matched_entities"],
            "craft": len(online_cookbook_relations) + len(local_default_craft_relations),
            "craftRecipeCount": online_cookbook_stats["recipes"],
            "craftMatchedProductCount": online_cookbook_stats["matched_products"],
            "craftMatchedCookbookCount": online_cookbook_stats["matched_cookbooks"],
            "craftUnmatchedProductCount": online_cookbook_stats["unmatched_products"],
            "craftAmbiguousProductCount": online_cookbook_stats["ambiguous_products"],
            "craftUnmatchedCookbookCount": online_cookbook_stats["unmatched_cookbooks"],
            "craftAmbiguousCookbookCount": online_cookbook_stats["ambiguous_cookbooks"],
            "craftIngredientsPresentCount": online_cookbook_stats["ingredients_present"],
            "craftIngredientSourceExactMatchCount": online_cookbook_stats[
                "ingredient_source_exact_matches"
            ],
            "craftIngredientSourcePairMismatchCount": online_cookbook_stats[
                "ingredient_source_pair_mismatches"
            ],
            "craftIngredientCount": online_cookbook_stats["ingredient_count"],
            "craftResolvedIngredientCount": online_cookbook_stats[
                "resolved_ingredient_count"
            ],
            "craftUnresolvedIngredientCount": online_cookbook_stats[
                "unresolved_ingredient_count"
            ],
            "localCraftRecipeRowCount": local_recipe_stats["local_rows"],
            "localCraftUsableRecipeCount": local_recipe_stats["usable_rows"],
            "localCraftOnlineEnrichedCount": local_recipe_stats["online_enriched"],
            "localCraftDefaultRelationCount": local_recipe_stats["default_relations"],
            "localCraftUnboundUnlockCount": local_recipe_stats["unbound_unlocks"],
            "localCraftUnresolvedProductCount": local_recipe_stats["unresolved_products"],
            "localCraftUnresolvedMaterialCount": local_recipe_stats["unresolved_materials"],
            "initialLoadoutRelationCount": len(initial_loadout_relations),
            **{
                f"initialLoadout_{key}": value
                for key, value in initial_loadout_stats.items()
            },
            "spell_acquisition": len(spell_acquisition_projections),
            "dropEndpointInstances": drop_endpoint_count,
            "questNpcEndpointInstances": quest_endpoint_count,
            "bossRewardEndpointInstances": sum(
                len(relation.get("endpointInstances", [])) for relation in boss_rewards
            ),
            "topologyMapEndpointCount": topology_map_stats["endpointCount"],
            "topologyMapExactMapInstanceEndpointCount": topology_map_stats[
                "exactMapInstanceEndpointCount"
            ],
            "topologyMapExactLayerEndpointCount": topology_map_stats[
                "exactMapLayerEndpointCount"
            ],
            "topologyMapCandidateEndpointCount": topology_map_stats[
                "candidateMapEndpointCount"
            ],
            "topologyMapExternalScopeEndpointCount": topology_map_stats[
                "externalMapEndpointCount"
            ],
            "topologyMapUnresolvedEndpointCount": topology_map_stats[
                "unresolvedMapEndpointCount"
            ],
            "topologyMapBindingStatusCounts": topology_map_stats["statusCounts"],
            **{f"shop_{key}": value for key, value in shop_stats.items()},
        },
        "coverageGaps": (
            drop_gaps + pickup_gaps + shop_gaps + online_map_gaps + online_guide_gaps
            + online_item_map_gaps + local_recipe_gaps + initial_loadout_gaps
            + unclassified_map_lot_gaps
        ),
        "sourceExclusions": pickup_source_exclusions,
        "relations": relations,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")

    # Merge enemy/npc, shop, and supplemental acquisition entities into the
    # canonical registry.  This is data enrichment; the query framework does
    # not require every entity to have a route node.
    registry["entities"] = all_entities
    registry["stats"]["enemy"] = len([e for e in enemies if e["kind"] == "enemy"])
    registry["stats"]["npc"] = len([e for e in enemies if e["kind"] == "npc"])
    registry["built_at"] = date.today().isoformat()
    args.registry.write_text(json.dumps(registry, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"updated {args.registry} ({args.registry.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
