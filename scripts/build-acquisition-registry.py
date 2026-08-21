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
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FMG_INDEX = ROOT / "data" / "v1" / "entities" / "official-fmg-bilingual-index.json"
ACHIEVEMENTS = ROOT / "data" / "v1" / "entities" / "achievements.json"
DEFAULT_ENEMY_SPAWNS = ROOT / "data" / "v1" / "entities" / "enemy-spawn-bindings.json"
DEFAULT_MERCHANT_SHOPS = ROOT / "data" / "v1" / "entities" / "merchant-shop-bindings.json"
DEFAULT_BOSS_ENDPOINTS = ROOT / "data" / "v1" / "entities" / "boss-reward-endpoints.json"
DEFAULT_EVENT_REWARDS = ROOT / "data" / "v1" / "entities" / "event-reward-bindings.json"
DEFAULT_QUEST_REWARDS = ROOT / "data" / "v1" / "entities" / "quest-reward-bindings.json"

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

# ShopLineupParam equipType (verified against the local regulation dump and the
# corresponding EquipParam tables): 0=Weapon, 1=Protector, 2=Accessory,
# 3=Goods, 4=Gem.  Type 5 is reserved/unknown in this snapshot and is skipped
# when no official name can be resolved.
SHOP_EQUIP_TABLES = {
    0: "WeaponName",
    1: "ProtectorName",
    2: "AccessoryName",
    3: "GoodsName",
    4: "GemName",
    5: "GemName",
}
SHOP_EQUIP_KIND = {
    0: "weapon", 1: "armor", 2: "accessory", 3: "item", 4: "ash_of_war", 5: "ash_of_war",
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
    for entity in entities:
        name = entity.get("name", {}).get("en")
        if name:
            by_kind_name.setdefault((entity.get("kind"), name.casefold()), []).append(entity["id"])

    kind_by_prefix = {
        "weapon": "weapon", "armor": "armor", "accessory": "accessory",
        "ash": "ash_of_war", "ash_of_war": "ash_of_war", "item": "item",
    }
    supplemental: dict[str, dict] = {}

    def candidates(name: str, kind: str | None) -> list[str]:
        if not kind:
            return []
        return by_kind_name.get((kind, name.casefold()), [])

    def resolve(raw_id: str, name: str) -> tuple[str, str | None, str | None]:
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
        for fallback_kind in ("item", "weapon", "armor", "accessory", "ash_of_war"):
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
            resolved, variant, corrected_name = resolve(raw_id, name)
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

def build_drops(npc_rows: list[dict], row_to_entity: dict[int, str],
                lot_rows: list[dict], tables) -> list[dict]:
    """Enemy drop relations: NpcParam.itemLotId_enemy -> ItemLotParam_enemy -> items."""
    lot_by_id = {r["id"]: r["cells"] for r in lot_rows}
    relations = []
    for r in npc_rows:
        rid = r["id"]
        eid = row_to_entity.get(rid)
        if not eid:
            continue
        lot_id = r["cells"].get("itemLotId_enemy")
        if not lot_id:
            continue
        lot = lot_by_id.get(lot_id)
        if not lot:
            continue
        items = []
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
                "lot": lot_id,
                "slot": k,
                "num": lot.get(f"lotItemNum{k:02d}"),
                "rate": lot.get(f"lotItemBasePoint{k:02d}"),
            })
        if items:
            relations.append({
                "id": f"drop-{rid}-lot{lot_id}",
                "from": eid,
                "method": "drop",
                "lot": {"param": "ItemLotParam_enemy", "rowId": lot_id},
                "items": items,
                "sourceNpcParamRows": [rid],
                "evidence": [f"regulation.bin NpcParam row {rid} itemLotId_enemy={lot_id}"],
                "verification": "local_param_verified",
            })
    return relations


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


def build_pickups(lot_rows: list[dict], tables) -> list[dict]:
    """Map pickups: ItemLotParam_map rows -> items (location binding later)."""
    relations = []
    for r in lot_rows:
        lot = r["cells"]
        items = []
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
                "lot": r["id"],
                "slot": k,
                "num": lot.get(f"lotItemNum{k:02d}"),
                "rate": lot.get(f"lotItemBasePoint{k:02d}"),
            })
        if items:
            relations.append({
                "id": f"pickup-lot{r['id']}",
                "from": None,
                "method": "pickup",
                "lot": {"param": "ItemLotParam_map", "rowId": r["id"]},
                "items": items,
                "evidence": [f"regulation.bin ItemLotParam_map row {r['id']}"],
                "verification": "local_param_verified",
            })
    return relations


def build_shops(
    shop_rows: list[dict],
    tables,
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
    merchant_bindings: dict[int, list[dict]] = {}
    if merchant_bindings_path and merchant_bindings_path.is_file():
        payload = json.loads(merchant_bindings_path.read_text(encoding="utf-8"))
        for binding in payload.get("bindings", []):
            row_id = binding.get("rowId")
            if row_id is not None:
                merchant_bindings.setdefault(int(row_id), []).append(binding)

    row_items: dict[int, dict] = {}
    for r in shop_rows:
        c = r["cells"]
        etype = c.get("equipType")
        eid = c.get("equipId")
        if not eid or eid <= 0:
            continue
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
        row_items[r["id"]] = {
            "item": f"{SHOP_EQUIP_KIND.get(etype, 'item')}_{slugify(en)}",
            "name": {"en": en, "zh": clean_name((entry or {}).get("zh")) or en},
            "price": c.get("value"),
            "costType": c.get("costType"),
            "mtrlId": c.get("mtrlId"),
            "stock": c.get("sellQuantity"),
            "lineupRow": r["id"],
        }
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
                    "copied talk-range shop source named the seller and map endpoint",
                ]
                verification = "local_param_and_external_shop_endpoint_verified"
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
    }
    return relations, entities, stats


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
    parser.add_argument("--quest-rewards", type=Path, default=DEFAULT_QUEST_REWARDS)
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
    print(f"drop relations: {len(drops)}")

    lot_map = param_rows(args.param_dir, "ItemLotParam_map")
    boss_lots = set()
    import glob as _glob
    for bp in _glob.glob(str(ROOT / "data" / "v1" / "entities" / "boss-rewards.json")):
        for br in json.loads(Path(bp).read_text(encoding="utf-8"))["rewards"]:
            boss_lots.add(br["lot"]["rowId"])
    pickups = [x for x in build_pickups(lot_map, tables) if x["lot"]["rowId"] not in boss_lots]
    print(f"pickup relations: {len(pickups)} (excluding {len(boss_lots)} boss reward lots)")

    shop_rows = param_rows(args.param_dir, "ShopLineupParam")
    shops, shop_entities, shop_stats = build_shops(
        shop_rows, tables, args.merchant_shops, entities + enemies
    )
    print(f"shop relations: {len(shops)}; details={shop_stats}")

    seen = set()
    deduped_by_key = {}
    deduped = []
    for d in drops:
        key = (d["from"], d["lot"]["rowId"])
        if key in seen:
            existing = deduped_by_key[key]
            existing.setdefault("sourceNpcParamRows", []).extend(d.get("sourceNpcParamRows", []))
            continue
        seen.add(key)
        deduped_by_key[key] = d
        deduped.append(d)
    for d in deduped:
        d["sourceNpcParamRows"] = sorted(set(d.get("sourceNpcParamRows", [])))
    drops = deduped
    print(f"drop relations after dedupe: {len(drops)}")
    drop_endpoint_count = attach_enemy_spawn_endpoints(drops, args.enemy_spawns)
    print(f"enemy spawn endpoints attached: {drop_endpoint_count}")

    boss_rewards = build_boss_reward_relations(entities + enemies, tables, args.boss_endpoints)
    print(f"boss reward relations: {len(boss_rewards)}")
    event_rewards = build_event_reward_relations(args.event_rewards)
    print(f"event reward relations: {len(event_rewards)}")
    quest_rewards, quest_endpoint_count = build_quest_reward_relations(
        args.quest_rewards, entities + enemies, args.enemy_spawns
    )
    print(
        f"quest reward relations: {len(quest_rewards)}; "
        f"NPC endpoints={quest_endpoint_count}"
    )

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
    relations = drops + pickups + shops + boss_rewards + event_rewards + quest_rewards
    canonicalize_acquisition_items(relations, all_entities)
    print(f"canonical entities after acquisition enrichment: {len(all_entities)}")

    payload = {
        "schema": "errn-acquisition-registry@1",
        "built_at": "2026-08-20",
        "built_from": {
            "param_dir": str(args.param_dir),
            "entity_registry": str(args.registry),
            "enemy_spawn_bindings": str(args.enemy_spawns),
            "merchant_shop_bindings": str(args.merchant_shops),
            "boss_reward_endpoints": str(args.boss_endpoints),
            "event_reward_bindings": str(args.event_rewards),
            "quest_reward_bindings": str(args.quest_rewards),
            "policy": "Facts derived from local regulation.bin; every item row is a signifier.",
        },
        "stats": {
            "drop": len(drops), "pickup": len(pickups), "shop": len(shops),
            "boss_reward": len(boss_rewards), "enemy_npc_entities": len(enemies),
            "event_reward": len(event_rewards),
            "quest_reward": len(quest_rewards),
            "dropEndpointInstances": drop_endpoint_count,
            "questNpcEndpointInstances": quest_endpoint_count,
            "bossRewardEndpointInstances": sum(
                len(relation.get("endpointInstances", [])) for relation in boss_rewards
            ),
            **{f"shop_{key}": value for key, value in shop_stats.items()},
        },
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
    registry["built_at"] = "2026-08-20"
    args.registry.write_text(json.dumps(registry, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"updated {args.registry} ({args.registry.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
