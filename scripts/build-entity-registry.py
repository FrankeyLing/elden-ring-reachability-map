#!/usr/bin/env python3
"""Build the acquisition entity registry (signified/signifier model).

Every signified (one canonical entity: a weapon, armor piece, item, spell,
enemy, npc or location instance) is recorded once with all of its signifiers
(param row ids, FMG name ids, source references).  Acquisitions map entities
to places/actors they come from.

Sources (all local game data):
  - data/v1/entities/official-fmg-bilingual-index.json  (official en/zh names)
  - <snapshot>/extracted/param-json/*.json              (regulation params)

Usage:
    python scripts/build-entity-registry.py \
        --param-dir <snapshot>/extracted/param-json \
        --out data/v1/entities/entity-registry.json
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

NAME_FMGS = [
    "GoodsName", "WeaponName", "ProtectorName", "AccessoryName",
    "GemName", "MagicName", "NpcName", "PlaceName", "ArtsName",
]

_suffix_re = re.compile(r"(_dlc0[12])?\.fmg$")

# Weapon affinity prefixes (official ER affinities) that precede the base name
AFFIX_PREFIXES = [
    "Flame Art", "Lightning", "Sacred", "Magic", "Cold", "Poison",
    "Blood", "Occult", "Quality", "Heavy", "Keen", "Fire", "Standard",
]


def load_name_tables() -> dict[str, dict[int, dict[str, str]]]:
    tables: dict[str, dict[int, dict[str, str]]] = {f: {} for f in NAME_FMGS}
    with open(FMG_INDEX, encoding="utf-8") as fh:
        recs = json.load(fh)["records"]
    for rec in recs:
        lang = rec["language"]
        if lang not in ("engus", "zhocn"):
            continue
        fmg_name = _suffix_re.sub("", rec["fmg"].replace("\\", "/").split("/")[-1])
        if fmg_name not in tables:
            continue
        entry = tables[fmg_name].setdefault(rec["id"], {})
        entry["en" if lang == "engus" else "zh"] = rec["text"]
    return tables


def clean_name(text: str | None) -> str | None:
    if not text or text in ("[ERROR]", ""):
        return None
    if text.startswith("[ERROR]"):
        text = text[len("[ERROR]"):].strip()
    return text or None


def fmg_lookup(tables, fmg: str, fmg_id: int) -> dict[str, str] | None:
    entry = tables.get(fmg, {}).get(fmg_id)
    if entry and (clean_name(entry.get("en")) or clean_name(entry.get("zh"))):
        return entry
    return None


def param_rows(param_dir: Path, name: str) -> list[dict[str, Any]]:
    path = param_dir / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"param dump missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))["rows"]


def slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def strip_affix(en_name: str) -> str:
    for prefix in AFFIX_PREFIXES:
        if en_name.startswith(prefix + " "):
            rest = en_name[len(prefix) + 1:]
            if rest:
                return rest
    return en_name


# Ammunition weapon types (arrows / bolts / ballista bolts) are not weapons
AMMO_WEPTYPES = {42, 43, 44, 45, 46, 47, 48, 49}


def build_weapons(rows: list[dict], tables) -> list[dict]:
    """EquipParamWeapon rows -> base weapon entities (affix variants merged).

    Name id rules seen in the ER merged param: row id == name id (majority),
    legacy rows use row*10 / row*100 / row*1000, a few 90M rows use row/10.
    Affix variants ("Heavy Dagger", "Bandit's Keen Curved Sword") are merged
    into the base weapon in a second pass when the stripped name exists.
    """
    entities: dict[str, dict] = {}
    for r in rows:
        rid = r["id"]
        if rid <= 0 or rid > 99999999:
            continue
        nm = None
        for v in (rid, rid * 10, rid * 100, rid * 1000):
            nm = fmg_lookup(tables, "WeaponName", v)
            if nm:
                break
        if not nm and rid % 10 == 0:
            nm = fmg_lookup(tables, "WeaponName", rid // 10)
        if not nm:
            continue
        en = clean_name(nm.get("en"))
        if not en or "dummy" in en.lower():
            continue
        wep_type = r["cells"].get("wepType")
        if wep_type in AMMO_WEPTYPES:
            continue
        eid = f"weapon_{slugify(en)}"
        ent = entities.setdefault(eid, {
            "id": eid,
            "kind": "weapon",
            "category": "weapon",
            "class": None,
            "name": {"en": en, "zh": None},
            "signifiers": [{"type": "param", "param": "EquipParamWeapon", "rows": []}],
            "properties": {"wepType": wep_type},
            "variant_count": 0,
        })
        if ent["name"]["zh"] is None and nm.get("zh"):
            ent["name"]["zh"] = clean_name(nm["zh"])
        ent["signifiers"][0]["rows"].append(rid)
        ent["variant_count"] += 1

    # second pass: merge affix variants into base weapons when the stripped
    # name already exists as an entity (e.g. Bandit's Keen Curved Sword)
    by_name = {e["name"]["en"]: e for e in entities.values()}
    merged_out: dict[str, dict] = {}
    for ent in entities.values():
        en = ent["name"]["en"]
        base = en
        for affix in AFFIX_PREFIXES:
            token = affix + " "
            idx = en.find(token)
            if idx >= 0:
                candidate = en[:idx] + en[idx + len(token):]
                if candidate in by_name and candidate != en:
                    base = candidate
                    break
        if base != en:
            target = by_name[base]
            target["signifiers"][0]["rows"].extend(ent["signifiers"][0]["rows"])
            target["variant_count"] += ent["variant_count"]
        else:
            merged_out[en] = ent
    for ent in merged_out.values():
        ent["name"]["zh"] = ent["name"]["zh"] or ent["name"]["en"]
    return sorted(merged_out.values(), key=lambda e: e["id"])


def build_armor(rows: list[dict], tables) -> list[dict]:
    """EquipParamProtector rows -> base armor entities (upgrade rows merged).

    ProtectorName id rules: row id (new rows) or row*100 (legacy rows);
    upgrade rows share the base row name.
    """
    entities: dict[str, dict] = {}
    for r in rows:
        rid = r["id"]
        nm = None
        for v in (rid, rid * 100, rid * 1000):
            nm = fmg_lookup(tables, "ProtectorName", v)
            if nm:
                break
        if not nm:
            continue
        en = clean_name(nm.get("en"))
        if not en or "dummy" in en.lower():
            continue
        base_en = en.replace(" (Altered)", "")
        eid = f"armor_{slugify(base_en)}"
        ent = entities.setdefault(eid, {
            "id": eid,
            "kind": "armor",
            "category": "armor",
            "class": None,
            "name": {"en": base_en, "zh": clean_name(nm.get("zh")) or en},
            "signifiers": [{"type": "param", "param": "EquipParamProtector", "rows": []}],
            "properties": {"protectorCategory": r["cells"].get("protectorCategory")},
            "variant_count": 0,
        })
        ent["signifiers"][0]["rows"].append(rid)
        ent["variant_count"] += 1
    return sorted(entities.values(), key=lambda e: e["id"])


def build_direct(rows: list[dict], tables, fmg: str, kind: str, category: str,
                 param_name: str, mults=(1,)) -> list[dict]:
    entities = []
    for r in rows:
        rid = r["id"]
        nm = None
        for mult in mults:
            nm = fmg_lookup(tables, fmg, rid * mult)
            if nm:
                break
        if not nm:
            continue
        en = clean_name(nm.get("en"))
        if not en or "dummy" in en.lower():
            continue
        entities.append({
            "id": f"{kind}_{slugify(en)}",
            "kind": kind,
            "category": category,
            "class": None,
            "name": {"en": en, "zh": clean_name(nm.get("zh")) or en},
            "signifiers": [{"type": "param", "param": param_name, "rows": [rid]}],
            "properties": {},
            "variant_count": 1,
        })
    return sorted(entities, key=lambda e: e["id"])


def build_spells(magic_rows: list[dict], goods_names, goods_rows: dict[int, dict]) -> list[dict]:
    """Magic param rows -> sorcery/incantation entities named from GoodsName.

    Magic row id == GoodsName id.  Classification: Int requirement => sorcery,
    Faith requirement => incantation (both => both).
    """
    entities = []
    for r in magic_rows:
        rid = r["id"]
        cells = r["cells"]
        nm = goods_names.get(rid)
        if not nm:
            continue
        en = clean_name(nm.get("en"))
        if not en:
            continue
        req_int = cells.get("requirementIntellect") or 0
        req_fai = cells.get("requirementFaith") or 0
        if req_int > 0 and req_fai > 0:
            category = "sorcery_and_incantation"
        elif req_int > 0:
            category = "sorcery"
        elif req_fai > 0:
            category = "incantation"
        else:
            category = "spell"
        entities.append({
            "id": f"spell_{slugify(en)}",
            "kind": "spell",
            "category": category,
            "class": None,
            "name": {"en": en, "zh": clean_name(nm.get("zh")) or en},
            "signifiers": [{"type": "param", "param": "Magic", "rows": [rid]}],
            "properties": {"requirementIntellect": req_int, "requirementFaith": req_fai},
            "variant_count": 1,
        })
    return sorted(entities, key=lambda e: e["id"])


# ---------------------------------------------------------------------------
# Goods classification (user categories)
# ---------------------------------------------------------------------------

GOODS_RULES = [
    ("smithing_stone", re.compile(r"Smithing Stone", re.I), re.compile(r"锻造石", re.I)),
    ("grave_glovewort", re.compile(r"Glovewort", re.I), re.compile(r"铃兰", re.I)),
    ("golden_rune", re.compile(r"Golden Rune", re.I), re.compile(r"黄金卢恩", re.I)),
    ("hero_rune", re.compile(r"Hero's Rune|Hero Rune", re.I), re.compile(r"英雄卢恩", re.I)),
    ("stone_sword_key", re.compile(r"Stone Sword Key", re.I), re.compile(r"石剑钥匙", re.I)),
    ("remembrance", re.compile(r"Remembrance", re.I), re.compile(r"追忆", re.I)),
    ("great_rune", re.compile(r"Great Rune", re.I), re.compile(r"大卢恩", re.I)),
    ("spirit_ash", re.compile(r"Ashes?$", re.I), re.compile(r"骨灰$", re.I)),
    ("map_fragment", re.compile(r"^Map:", re.I), re.compile(r"^地图", re.I)),
    ("scroll", re.compile(r"Scroll", re.I), re.compile(r"卷轴", re.I)),
    ("prayerbook", re.compile(r"Prayerbook", re.I), re.compile(r"祷书", re.I)),
    ("bell_bearing", re.compile(r"Bell Bearing", re.I), re.compile(r"铃珠", re.I)),
    ("cookbook", re.compile(r"Cookbook", re.I), re.compile(r"制作笔记", re.I)),
    ("painting", re.compile(r"Painting", re.I), re.compile(r"绘画", re.I)),
    ("crystal_tear", re.compile(r"Crystal Tear", re.I), re.compile(r"露滴", re.I)),
    ("sacred_tear", re.compile(r"Sacred Tear", re.I), re.compile(r"圣杯露滴", re.I)),
    ("larval_tear", re.compile(r"Larval Tear", re.I), re.compile(r"泪滴幼体", re.I)),
    ("rune_arc", re.compile(r"Rune Arc", re.I), re.compile(r"卢恩弯弧", re.I)),
    ("dragon_heart", re.compile(r"Dragon Heart", re.I), re.compile(r"龙心脏", re.I)),
    ("golden_seed", re.compile(r"Golden Seed", re.I), re.compile(r"黄金种子", re.I)),
    ("memory_stone", re.compile(r"Memory Stone", re.I), re.compile(r"记忆石", re.I)),
    ("deathroot", re.compile(r"Deathroot", re.I), re.compile(r"死根", re.I)),
    ("starlight_shard", re.compile(r"Starlight Shard", re.I), re.compile(r"星光碎片", re.I)),
    ("perfume_bottle", re.compile(r"Perfume Bottle", re.I), re.compile(r"调香瓶", re.I)),
    ("jar", re.compile(r"Pot$|Pot \(|Jar", re.I), re.compile(r"(龟裂|仪式)?壶", re.I)),
    ("tool", re.compile(r"Tool$|Tools", re.I), re.compile(r"工具", re.I)),
    ("multiplayer_item", re.compile(r"Finger|Effigy|Tarnished's|Duelist|Cipher|Tongue|Furled", re.I),
     re.compile(r"手指|傀儡|褪色者|决斗者|密文|舌头|勾指", re.I)),
    ("key_item", re.compile(r"Key$|Key Item", re.I), re.compile(r"钥匙", re.I)),
]


def classify_goods(name_en: str, name_zh: str | None, goods_type: int | None) -> str:
    for category, re_en, re_zh in GOODS_RULES:
        if re_en.search(name_en) or (name_zh and re_zh.search(name_zh)):
            return category
    if goods_type == 1:
        return "key_item"
    return "consumable"


def build_goods(rows: list[dict], tables) -> list[dict]:
    entities = []
    for r in rows:
        rid = r["id"]
        nm = fmg_lookup(tables, "GoodsName", rid)
        if not nm:
            continue
        en = clean_name(nm.get("en"))
        if not en or "dummy" in en.lower() or en.startswith("Ash of War:"):
            continue
        cells = r["cells"]
        category = classify_goods(en, clean_name(nm.get("zh")), cells.get("goodsType"))
        entities.append({
            "id": f"item_{slugify(en)}",
            "kind": "item",
            "category": category,
            "class": None,
            "name": {"en": en, "zh": clean_name(nm.get("zh")) or en},
            "signifiers": [{"type": "param", "param": "EquipParamGoods", "rows": [rid]}],
            "properties": {"goodsType": cells.get("goodsType"), "basicPrice": cells.get("basicPrice"),
                           "sortId": cells.get("sortId")},
            "variant_count": 1,
        })
    return sorted(entities, key=lambda e: e["id"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--param-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "v1" / "entities" / "entity-registry.json")
    args = parser.parse_args()

    print("loading FMG name tables ...")
    tables = load_name_tables()
    print("  tables:", {k: len(v) for k, v in tables.items()})

    weapons = build_weapons(param_rows(args.param_dir, "EquipParamWeapon"), tables)
    print(f"weapons: {len(weapons)}")
    armors = build_armor(param_rows(args.param_dir, "EquipParamProtector"), tables)
    print(f"armors: {len(armors)}")
    accessories = build_direct(param_rows(args.param_dir, "EquipParamAccessory"), tables,
                               "AccessoryName", "accessory", "accessory", "EquipParamAccessory")
    print(f"accessories: {len(accessories)}")
    gems = build_direct(param_rows(args.param_dir, "EquipParamGem"), tables,
                        "GemName", "ash_of_war", "ash_of_war", "EquipParamGem", mults=(1, 100, 1000))
    print(f"ash_of_war: {len(gems)}")
    goods = build_goods(param_rows(args.param_dir, "EquipParamGoods"), tables)
    print(f"items: {len(goods)}")
    spells = build_spells(param_rows(args.param_dir, "Magic"), tables["GoodsName"], None)
    print(f"spells: {len(spells)}")

    entities = weapons + armors + accessories + gems + goods + spells
    # merge duplicates (e.g. two Gem rows resolving to the same name id)
    by_id: dict[str, dict] = {}
    for ent in entities:
        existing = by_id.get(ent["id"])
        if existing is None:
            by_id[ent["id"]] = ent
            continue
        existing["signifiers"][0]["rows"].extend(ent["signifiers"][0]["rows"])
        existing["variant_count"] += ent["variant_count"]
    entities = sorted(by_id.values(), key=lambda e: e["id"])
    from collections import Counter
    cats = Counter(e["category"] for e in entities)
    print("category distribution:", dict(cats))
    print(f"total entities: {len(entities)}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "errn-entity-registry@1",
        "built_at": "2026-08-20",
        "built_from": {
            "fmg_index": str(FMG_INDEX),
            "param_dir": str(args.param_dir),
            "policy": "Only FromSoftware official names; every row is a signifier of one signified entity.",
        },
        "stats": {
            "weapon": len(weapons), "armor": len(armors), "accessory": len(accessories),
            "ash_of_war": len(gems), "spell": len(spells), "item": len(goods),
        },
        "entities": entities,
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
