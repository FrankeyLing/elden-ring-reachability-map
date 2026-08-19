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

# ShopLineupParam equipType (verified): 0=Goods, 1=Weapon, 2=Protector, 3=?,
# 4=Accessory, 5=Gem.  Probe-based: map by table hit at build time instead.
SHOP_EQUIP_TABLES = {
    0: "GoodsName",
    1: "WeaponName",
    2: "ProtectorName",
    3: "GoodsName",
    4: "AccessoryName",
    5: "GemName",
}
SHOP_EQUIP_KIND = {
    0: "item", 1: "weapon", 2: "armor", 3: "item", 4: "accessory", 5: "ash_of_war",
}

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


def slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


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
                "evidence": [f"regulation.bin NpcParam row {rid} itemLotId_enemy={lot_id}"],
                "verification": "local_param_verified",
            })
    return relations


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


def build_shops(shop_rows: list[dict], tables) -> tuple[list[dict], list[dict]]:
    """Shop relations: ShopLineupParam rows -> items with prices.

    Returns (relations, shop_entities).
    """
    by_shop: dict[int, list[dict]] = {}
    for r in shop_rows:
        c = r["cells"]
        etype = c.get("equipType")
        eid = c.get("equipId")
        if not eid or eid <= 0:
            continue
        fmg = SHOP_EQUIP_TABLES.get(etype)
        if fmg is None:
            continue
        entry = name_for(tables, eid, [fmg, "GoodsName"])
        en = clean_name((entry or {}).get("en"))
        if not en:
            continue
        shop_id = r["id"] // 1000
        by_shop.setdefault(shop_id, []).append({
            "item": f"{SHOP_EQUIP_KIND.get(etype, 'item')}_{slugify(en)}",
            "name": {"en": en, "zh": clean_name((entry or {}).get("zh")) or en},
            "price": c.get("value"),
            "costType": c.get("costType"),
            "mtrlId": c.get("mtrlId"),
            "stock": c.get("sellQuantity"),
            "lineupRow": r["id"],
        })
    relations = []
    entities = []
    for shop_id in sorted(by_shop):
        entries = by_shop[shop_id]
        relations.append({
            "id": f"shop-{shop_id}",
            "from": f"npc_shop_{shop_id}",
            "method": "purchase",
            "items": entries,
            "evidence": [f"regulation.bin ShopLineupParam shopId={shop_id}"],
            "verification": "local_param_verified",
        })
        entities.append({
            "id": f"npc_shop_{shop_id}",
            "kind": "npc",
            "category": "merchant",
            "class": None,
            "name": {"en": f"Shop {shop_id}", "zh": f"商店 {shop_id}"},
            "signifiers": [{"type": "param", "param": "ShopLineupParam", "rows": [shop_id * 1000]}],
            "properties": {"shopId": shop_id},
            "variant_count": 1,
        })
    return relations, entities


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


def build_boss_reward_relations(entities: list[dict], tables) -> list[dict]:
    """Remembrance / Great Rune entities point to their source boss (and back)."""
    by_name = {e["name"]["en"]: e for e in entities}
    relations = []
    for item_name, boss_name in {**REMEMBRANCE_TO_BOSS, **GREAT_RUNE_TO_BOSS}.items():
        item = by_name.get(item_name)
        boss = by_name.get(boss_name)
        if not item or not boss:
            continue
        relations.append({
            "id": f"boss-reward-{slugify(item_name)}",
            "from": item["id"],
            "method": "boss_reward",
            "items": [{"item": boss["id"], "name": boss["name"], "num": 1}],
            "evidence": ["official boss/remembrance name mapping"],
            "verification": "official_names",
        })
        relations.append({
            "id": f"boss-drops-{slugify(boss_name)}",
            "from": boss["id"],
            "method": "drops",
            "items": [{"item": item["id"], "name": item["name"], "num": 1}],
            "evidence": ["official boss/remembrance name mapping"],
            "verification": "official_names",
        })
    return relations


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
    args = parser.parse_args()

    print("loading FMG name tables ...")
    tables = load_name_tables()

    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    entities = registry["entities"]
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
    shops, shop_entities = build_shops(shop_rows, tables)
    print(f"shop relations: {len(shops)}")

    seen = set()
    deduped = []
    for d in drops:
        key = (d["from"], d["lot"]["rowId"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(d)
    drops = deduped
    print(f"drop relations after dedupe: {len(drops)}")

    boss_rewards = build_boss_reward_relations(entities + enemies, tables)
    print(f"boss reward relations: {len(boss_rewards)}")

    payload = {
        "schema": "errn-acquisition-registry@1",
        "built_at": "2026-08-20",
        "built_from": {
            "param_dir": str(args.param_dir),
            "entity_registry": str(args.registry),
            "policy": "Facts derived from local regulation.bin; every item row is a signifier.",
        },
        "stats": {
            "drop": len(drops), "pickup": len(pickups), "shop": len(shops),
            "boss_reward": len(boss_rewards), "enemy_npc_entities": len(enemies),
        },
        "relations": drops + pickups + shops + boss_rewards,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")

    # merge enemy/npc entities into the entity registry
    # Named entities with no official FMG name (identified by model): the SotE
    # Furnace Golem is a user-category boss with only a community name.
    MANUAL_ENTITIES = [
        {
            "id": "enemy_furnace_golem",
            "kind": "enemy",
            "category": "furnace_golem",
            "class": None,
            "name": {"en": "Furnace Golem", "zh": "燃炉魔像"},
            "signifiers": [{"type": "manual", "note": "no official NpcName; identified by model"}],
            "properties": {},
            "variant_count": 1,
        },
    ]

    registry["entities"] = [e for e in registry["entities"] if e["kind"] not in ("enemy", "npc")]
    registry["entities"].extend(enemies)
    registry["entities"].extend(shop_entities)
    registry["entities"].extend(MANUAL_ENTITIES)
    registry["stats"]["enemy"] = len([e for e in enemies if e["kind"] == "enemy"])
    registry["stats"]["npc"] = len([e for e in enemies if e["kind"] == "npc"])
    registry["built_at"] = "2026-08-20"
    args.registry.write_text(json.dumps(registry, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"updated {args.registry} ({args.registry.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
