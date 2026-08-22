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

# EquipParamWeapon.wepType is the game's stable equipment-family identity.
# Keep the canonical entity category as ``weapon`` so a shield or staff is
# still one weapon entity, while exposing the real family as a property for
# filtering and display.  Values are taken from the local parameter snapshot
# and are intentionally kept separate from reinforcement or acquisition data.
WEAPON_FAMILY_BY_TYPE = {
    50: "bow",
    51: "bow",
    53: "bow",
    55: "crossbow",
    56: "ballista",
    57: "staff",
    61: "sacred_seal",
    65: "shield",
    67: "shield",
    69: "shield",
    87: "torch",
    88: "hand_to_hand",
    89: "perfume",
    90: "shield",
}


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
        family = WEAPON_FAMILY_BY_TYPE.get(wep_type, "melee")
        ent["properties"].setdefault("weaponFamilies", set()).add(family)

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
        families = ent.get("properties", {}).pop("weaponFamilies", set())
        if not isinstance(families, set):
            families = set(families or [])
        non_melee_families = sorted(families - {"melee"})
        if len(non_melee_families) == 1:
            family = non_melee_families[0]
        elif not non_melee_families:
            family = "melee"
        else:
            family = "mixed"
        ent["properties"]["weaponFamily"] = family
        ent["properties"]["weaponFamilySet"] = sorted(families)
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
        # Some internal Magic rows reuse a GoodsName id belonging to a real
        # inventory item.  A key-item row such as Stonesword Key is not a
        # spell and must not create a second canonical entity.
        goods_row = goods_rows.get(rid)
        if goods_row and goods_row.get("cells", {}).get("goodsType") == 1:
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


def merge_spell_goods_signifiers(
    goods: list[dict], spells: list[dict], goods_rows_by_id: dict[int, dict]
) -> tuple[list[dict], dict[str, str], int]:
    """Merge the Goods learning row into its one canonical spell entity.

    A learnable spell has a Magic row and a same-id Goods row.  They are two
    engine signifiers for one player-facing spell, not two obtainable things.
    A same-name Goods row with another id remains independent; Golden Vow is
    the concrete case where the DLC consumable must not be merged into the
    base-game incantation.
    """
    goods_by_name: dict[str, list[tuple[int, dict]]] = {}
    for index, entity in enumerate(goods):
        name = (entity.get("name", {}).get("en") or "").casefold()
        if name:
            goods_by_name.setdefault(name, []).append((index, entity))
    aliases: dict[str, str] = {}
    merged_signifiers = 0
    consumed_goods_indexes: set[int] = set()

    for spell in spells:
        name_key = (spell.get("name", {}).get("en") or "").casefold()
        magic_rows = {
            int(row_id)
            for signifier in spell.get("signifiers", [])
            if signifier.get("param") == "Magic"
            for row_id in signifier.get("rows", [])
        }
        candidate = None
        for goods_index, goods_entity in goods_by_name.get(name_key, []):
            goods_signifier = next(
                (
                    signifier
                    for signifier in goods_entity.get("signifiers", [])
                    if signifier.get("param") == "EquipParamGoods"
                ),
                None,
            )
            if goods_signifier and magic_rows & {
                int(row_id) for row_id in goods_signifier.get("rows", [])
            }:
                candidate = (goods_index, goods_entity, goods_signifier)
                break
        if not candidate:
            continue
        goods_index, goods_entity, goods_signifier = candidate
        goods_rows = {int(row_id) for row_id in goods_signifier.get("rows", [])}
        linked_rows = sorted(goods_rows & magic_rows)
        if not linked_rows:
            continue

        spell.setdefault("signifiers", []).append({
            "type": "param",
            "param": "EquipParamGoods",
            "rows": linked_rows,
            "role": "spell_learning_inventory_signifier",
        })
        spell.setdefault("properties", {})["goodsLearningRowIds"] = linked_rows
        spell["properties"]["canonicalEntityRole"] = "learnable_spell"
        merged_signifiers += 1

        remaining_rows = sorted(goods_rows - set(linked_rows))
        if remaining_rows:
            # The same display name denotes a separate inventory product too.
            # Retain only its non-spell Goods rows on the item entity.
            goods_signifier["rows"] = remaining_rows
            goods_entity["variant_count"] = len(remaining_rows)
            remaining_cells = goods_rows_by_id[remaining_rows[0]]["cells"]
            goods_entity["properties"] = {
                "goodsType": remaining_cells.get("goodsType"),
                "basicPrice": remaining_cells.get("basicPrice"),
                "sortId": remaining_cells.get("sortId"),
            }
            goods_entity.setdefault("properties", {})["sameNameSpellEntityId"] = spell["id"]
            spell["properties"]["sameNameInventoryEntityId"] = goods_entity["id"]
        else:
            consumed_goods_indexes.add(goods_index)
            spell.setdefault("properties", {})["legacyGoodsEntityId"] = goods_entity["id"]

    retained_goods = [
        entity for index, entity in enumerate(goods)
        if index not in consumed_goods_indexes
    ]
    retained_ids = {entity["id"] for entity in retained_goods}
    for index in consumed_goods_indexes:
        source_id = goods[index]["id"]
        if source_id not in retained_ids:
            spell_id = f"spell_{slugify(goods[index]['name']['en'])}"
            aliases[source_id] = spell_id
        else:
            spell_id = f"spell_{slugify(goods[index]['name']['en'])}"
            spell = next(entity for entity in spells if entity["id"] == spell_id)
            spell.get("properties", {}).pop("legacyGoodsEntityId", None)
    return retained_goods, dict(sorted(aliases.items())), merged_signifiers


# ---------------------------------------------------------------------------
# Goods classification (user categories)
# ---------------------------------------------------------------------------

SPIRIT_ASH_REINFORCEMENT_MATERIALS = {
    10000: "grave_glovewort",
    10100: "ghost_glovewort",
}
NON_SPIRIT_ASH_NAMES = {"About Combat with Spirit Ashes"}


GOODS_RULES = [
    ("smithing_stone", re.compile(r"Smithing Stone", re.I), re.compile(r"锻造石", re.I)),
    # More specific goods must precede the broad Glovewort rule. Otherwise
    # Glovewort Picker's Bell Bearings and Glovewort Crystal Tear are falsely
    # published as reinforcement materials.
    ("bell_bearing", re.compile(r"Bell Bearing", re.I), re.compile(r"铃珠", re.I)),
    ("crystal_tear", re.compile(r"Crystal Tear", re.I), re.compile(r"露滴", re.I)),
    ("ghost_glovewort", re.compile(r"Ghost Glovewort", re.I), re.compile(r"灵依墓地铃兰", re.I)),
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
    ("cookbook", re.compile(r"Cookbook", re.I), re.compile(r"制作笔记", re.I)),
    ("painting", re.compile(r"Painting", re.I), re.compile(r"绘画", re.I)),
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


FLASK_REINFORCEMENT_RE = re.compile(
    r"^(Flask of (?:Crimson|Cerulean) Tears)(?: \+\d+)?$",
    re.IGNORECASE,
)


def classify_goods(
    name_en: str,
    name_zh: str | None,
    goods_type: int | None,
    cells: dict | None = None,
) -> str:
    # The official goods parameters are authoritative for Spirit Ashes.  A
    # number of unique ashes (for example Lhutel the Headless and the
    # summonable puppets) do not contain the word "Ashes" in their display
    # name and were previously misclassified by the name-only rules.
    cells = cells or {}
    if (
        cells.get("reinforceGoodsId", -1) != -1
        and cells.get("reinforceMaterialId") in SPIRIT_ASH_REINFORCEMENT_MATERIALS
    ):
        return "spirit_ash"
    for category, re_en, re_zh in GOODS_RULES:
        if category == "spirit_ash" and name_en in NON_SPIRIT_ASH_NAMES:
            continue
        if re_en.search(name_en) or (name_zh and re_zh.search(name_zh)):
            return category
    if goods_type == 1:
        return "key_item"
    return "consumable"


def build_goods(rows: list[dict], tables) -> list[dict]:
    entities = []
    rows_by_id = {row["id"]: row for row in rows}
    predecessor_by_next: dict[int, int] = {}
    for row in rows:
        next_id = row["cells"].get("reinforceGoodsId", -1)
        if next_id != -1 and next_id in rows_by_id:
            predecessor_by_next[next_id] = row["id"]

    def reinforcement_root(row_id: int) -> int:
        current = row_id
        seen: set[int] = set()
        while current in predecessor_by_next and current not in seen:
            seen.add(current)
            current = predecessor_by_next[current]
        return current

    chain_rows: dict[int, list[dict]] = {}
    for row in rows:
        root_id = reinforcement_root(row["id"])
        root = rows_by_id[root_id]
        root_cells = root["cells"]
        if (
            root_cells.get("reinforceGoodsId", -1) != -1
            and root_cells.get("reinforceMaterialId")
            in SPIRIT_ASH_REINFORCEMENT_MATERIALS
        ):
            chain_rows.setdefault(root_id, []).append(row)

    emitted_chain_roots: set[int] = set()
    chain_row_ids = {row["id"] for chain in chain_rows.values() for row in chain}
    for r in rows:
        if r["id"] in chain_row_ids:
            root_id = reinforcement_root(r["id"])
            if root_id in emitted_chain_roots:
                continue
            r = rows_by_id[root_id]
            chain = sorted(chain_rows[root_id], key=lambda row: row["id"])
            emitted_chain_roots.add(root_id)
        else:
            chain = [r]
        rid = r["id"]
        nm = fmg_lookup(tables, "GoodsName", rid)
        if not nm:
            continue
        en = clean_name(nm.get("en"))
        if not en or "dummy" in en.lower() or en.startswith("Ash of War:"):
            continue
        cells = r["cells"]
        flask_match = FLASK_REINFORCEMENT_RE.fullmatch(en)
        canonical_en = flask_match.group(1) if flask_match else en
        category = (
            "consumable"
            if flask_match
            else classify_goods(
                en,
                clean_name(nm.get("zh")),
                cells.get("goodsType"),
                cells,
            )
        )
        entities.append({
            "id": f"item_{slugify(canonical_en)}",
            "kind": "item",
            "category": category,
            "class": None,
            "name": {
                "en": canonical_en,
                "zh": (
                    clean_name(nm.get("zh")).split("+")[0].strip()
                    if flask_match and clean_name(nm.get("zh"))
                    else clean_name(nm.get("zh")) or canonical_en
                ),
            },
            "signifiers": [{
                "type": "param",
                "param": "EquipParamGoods",
                "rows": [row["id"] for row in chain],
            }],
            "properties": {"goodsType": cells.get("goodsType"), "basicPrice": cells.get("basicPrice"),
                           "sortId": cells.get("sortId"),
                           **({
                               "reinforcementMaterialId": cells.get("reinforceMaterialId"),
                               "reinforcementClass": SPIRIT_ASH_REINFORCEMENT_MATERIALS[
                                   cells.get("reinforceMaterialId")
                               ],
                           } if len(chain) > 1 else {}),
                           **({
                               "variantKind": "reinforcement_state",
                           } if flask_match else {})},
            "variant_count": len(chain),
        })
    return sorted(entities, key=lambda e: e["id"])


def apply_gesture_signifiers(
    entities: list[dict], gesture_rows: list[dict], tables
) -> int:
    """Promote goods referenced by GestureParam to the gesture category.

    Gesture names are stored in the ordinary GoodsName table and their item
    ids overlap the goods registry.  The GestureParam rows are therefore an
    additional signifier of the same canonical item, not a second entity.
    """
    rows_by_item: dict[int, list[dict]] = {}
    for row in gesture_rows:
        item_id = row.get("cells", {}).get("itemId")
        if isinstance(item_id, int) and item_id > 0:
            rows_by_item.setdefault(item_id, []).append(row)

    promoted = 0
    for entity in entities:
        goods_signifier = next(
            (
                signifier
                for signifier in entity.get("signifiers", [])
                if signifier.get("type") == "param"
                and signifier.get("param") == "EquipParamGoods"
            ),
            None,
        )
        if not goods_signifier:
            continue
        matches = [
            row
            for goods_id in goods_signifier.get("rows", [])
            for row in rows_by_item.get(goods_id, [])
        ]
        if not matches:
            continue

        entity["category"] = "gesture"
        entity.setdefault("properties", {})["gestureItemIds"] = sorted({
            row["cells"]["itemId"] for row in matches
        })
        entity["properties"]["gestureCannotUseRiding"] = sorted({
            row["cells"].get("cannotUseRiding")
            for row in matches
            if row["cells"].get("cannotUseRiding") is not None
        })
        gesture_signifier = next(
            (
                signifier
                for signifier in entity.setdefault("signifiers", [])
                if signifier.get("type") == "param"
                and signifier.get("param") == "GestureParam"
            ),
            None,
        )
        if gesture_signifier is None:
            gesture_signifier = {
                "type": "param",
                "param": "GestureParam",
                "rows": [],
            }
            entity["signifiers"].append(gesture_signifier)
        gesture_signifier["rows"] = sorted({row["id"] for row in matches})
        if not any(
            signifier.get("type") == "category_alias"
            for signifier in entity["signifiers"]
        ):
            entity["signifiers"].append({
                "type": "category_alias",
                "en": "gesture",
                "zh": "表情动作",
            })
        promoted += 1

    # A small number of named gestures are referenced by GestureParam and
    # GoodsName but have no EquipParamGoods row in this snapshot.  They are
    # still real named actions, so publish them as GestureParam-only entities
    # instead of losing them or inventing an ordinary consumable.
    existing_gesture_item_ids = {
        item_id
        for entity in entities
        if entity.get("category") == "gesture"
        for item_id in entity.get("properties", {}).get("gestureItemIds", [])
    }
    for row in gesture_rows:
        item_id = row.get("cells", {}).get("itemId")
        if item_id in existing_gesture_item_ids:
            continue
        name = fmg_lookup(tables, "GoodsName", item_id)
        en = clean_name((name or {}).get("en"))
        if not en:
            continue
        entity = {
            "id": f"gesture_{slugify(en)}",
            "kind": "item",
            "category": "gesture",
            "class": None,
            "name": {"en": en, "zh": clean_name((name or {}).get("zh")) or en},
            "signifiers": [
                {"type": "param", "param": "GestureParam", "rows": [row["id"]]},
                {"type": "category_alias", "en": "gesture", "zh": "表情动作"},
            ],
            "properties": {
                "gestureItemIds": [item_id],
                "gestureCannotUseRiding": [row["cells"].get("cannotUseRiding")]
                if row["cells"].get("cannotUseRiding") is not None else [],
                "goodsNameOnly": True,
            },
            "variant_count": 1,
        }
        entities.append(entity)
        existing_gesture_item_ids.add(item_id)
        promoted += 1
    return promoted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# These rows are present in the copied parameter snapshot but are disabled
# internal test or discarded records, not player-obtainable Ashes of War.
# Keep the exclusion explicit and auditable instead of publishing them as
# searchable game content.
EXCLUDED_INTERNAL_GEM_ROWS = {
    20: "EquipParamGem internal test gem row; disabled and has no player item name",
    30: "EquipParamGem internal test gem row; disabled and has no player item name",
    121: "EquipParamGem discarded internal Wicked Stance row; no official localized item name",
    117: "EquipParamGem internal Torch Attack row; disabled, non-droppable, and uses the internal sort sentinel",
}

EXCLUDED_INTERNAL_WEAPON_ROWS = {
    100600: "discarded Abundance and Decay Twinblade row; non-droppable and uses the internal sort sentinel",
    100700: "discarded Abundance Twinblade row; non-droppable and uses the internal sort sentinel",
    1100: "unarmed equipment placeholder; cannot be discarded, dropped, or deposited",
    11000: "unarmed equipment placeholder; non-droppable and uses the internal sort sentinel",
    110000: "unarmed equipment placeholder; uses the internal sort sentinel and has no acquisition reference",
}

EXCLUDED_INTERNAL_ARMOR_ROWS = {
    10000: "head-slot equipment placeholder; cannot be discarded, dropped, or deposited",
    10100: "body-slot equipment placeholder; cannot be discarded, dropped, or deposited",
    10200: "arms-slot equipment placeholder; cannot be discarded, dropped, or deposited",
    10300: "legs-slot equipment placeholder; cannot be discarded, dropped, or deposited",
    610000: "discarded Ragged Hat row; non-droppable and uses the internal sort sentinel",
    610100: "discarded Ragged Armor row; non-droppable and uses the internal sort sentinel",
    610200: "discarded Ragged Gloves row; non-droppable and uses the internal sort sentinel",
    610300: "discarded Ragged Loincloth row; non-droppable and uses the internal sort sentinel",
    611000: "discarded alternate Ragged Hat row; non-droppable and uses the internal sort sentinel",
    611100: "discarded alternate Ragged Armor row; non-droppable and uses the internal sort sentinel",
    700000: "discarded Brave's Cord Circlet row; non-droppable and uses the internal sort sentinel",
    920000: "discarded Grass Hair Ornament row; non-droppable and uses the internal sort sentinel",
    1950100: "discarded Millicent's Robe row; non-droppable and uses the internal sort sentinel",
    1950200: "discarded Millicent's Gloves row; non-droppable and uses the internal sort sentinel",
    1950300: "discarded Millicent's Boots row; non-droppable and uses the internal sort sentinel",
    1970100: "discarded Millicent's Tunic row; non-droppable and uses the internal sort sentinel",
    1970200: "discarded Golden Prosthetic row; non-droppable and uses the internal sort sentinel",
}

EXCLUDED_INTERNAL_ACCESSORY_ROWS = {
    6100: "discarded Entwining Umbilical Cord row; non-droppable and uses the internal sort sentinel",
}


def explicit_param_exclusions(
    rows: list[dict], param: str, kind: str, excluded: dict[int, str]
) -> list[dict]:
    rows_by_id = {row["id"]: row for row in rows}
    records = []
    for row_id, reason in excluded.items():
        cells = rows_by_id[row_id]["cells"]
        records.append({
            "kind": kind,
            "param": param,
            "row": row_id,
            "reason": reason,
            "evidence": [
                f"disableParam_NT={cells.get('disableParam_NT')}",
                f"isDiscard={cells.get('isDiscard')}",
                f"isDrop={cells.get('isDrop')}",
                f"isDeposit={cells.get('isDeposit')}",
                f"sortId={cells.get('sortId')}",
            ],
        })
    return records

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--param-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "v1" / "entities" / "entity-registry.json")
    args = parser.parse_args()

    print("loading FMG name tables ...")
    tables = load_name_tables()
    print("  tables:", {k: len(v) for k, v in tables.items()})

    weapon_rows = param_rows(args.param_dir, "EquipParamWeapon")
    excluded_weapons = explicit_param_exclusions(
        weapon_rows, "EquipParamWeapon", "weapon", EXCLUDED_INTERNAL_WEAPON_ROWS
    )
    weapons = build_weapons([
        row for row in weapon_rows if row["id"] not in EXCLUDED_INTERNAL_WEAPON_ROWS
    ], tables)
    print(f"weapons: {len(weapons)} (excluded internal rows: {len(excluded_weapons)})")
    armor_rows = param_rows(args.param_dir, "EquipParamProtector")
    appearance_rows = [
        row for row in armor_rows
        if row.get("cells", {}).get("protectorCategory") == 4
    ]
    excluded_appearance_armor = [
        {
            "kind": "armor",
            "param": "EquipParamProtector",
            "row": row["id"],
            "reason": (
                "Protector category 4 is a character-appearance/body-type record, "
                "not a player-obtainable head/body/arms/legs armor item"
            ),
            "evidence": [
                "protectorCategory=4",
                f"headEquip={row['cells'].get('headEquip')}",
                f"bodyEquip={row['cells'].get('bodyEquip')}",
                f"armEquip={row['cells'].get('armEquip')}",
                f"legEquip={row['cells'].get('legEquip')}",
                f"isDeposit={row['cells'].get('isDeposit')}",
            ],
        }
        for row in appearance_rows
    ]
    excluded_internal_armor = explicit_param_exclusions(
        armor_rows, "EquipParamProtector", "armor", EXCLUDED_INTERNAL_ARMOR_ROWS
    )
    armors = build_armor([
        row for row in armor_rows
        if row.get("cells", {}).get("protectorCategory") != 4
        and row["id"] not in EXCLUDED_INTERNAL_ARMOR_ROWS
    ], tables)
    print(
        f"armors: {len(armors)} "
        f"(excluded appearance/body-type rows: {len(excluded_appearance_armor)}; "
        f"internal rows: {len(excluded_internal_armor)})"
    )
    accessory_rows = param_rows(args.param_dir, "EquipParamAccessory")
    excluded_accessories = explicit_param_exclusions(
        accessory_rows, "EquipParamAccessory", "accessory",
        EXCLUDED_INTERNAL_ACCESSORY_ROWS,
    )
    accessories = build_direct([
        row for row in accessory_rows if row["id"] not in EXCLUDED_INTERNAL_ACCESSORY_ROWS
    ], tables,
                               "AccessoryName", "accessory", "accessory", "EquipParamAccessory")
    print(f"accessories: {len(accessories)}")
    gem_rows = param_rows(args.param_dir, "EquipParamGem")
    gem_rows_by_id = {row["id"]: row for row in gem_rows}
    excluded_gems = [
        {
            "kind": "ash_of_war",
            "param": "EquipParamGem",
            "row": row_id,
            "reason": reason,
            "evidence": [
                f"disableParam_NT={gem_rows_by_id[row_id]['cells'].get('disableParam_NT')}",
                f"isDiscard={gem_rows_by_id[row_id]['cells'].get('isDiscard')}",
                f"sortId={gem_rows_by_id[row_id]['cells'].get('sortId')}",
            ],
        }
        for row_id, reason in EXCLUDED_INTERNAL_GEM_ROWS.items()
    ]
    gems = build_direct(
        [row for row in gem_rows if row["id"] not in EXCLUDED_INTERNAL_GEM_ROWS],
        tables,
        "GemName", "ash_of_war", "ash_of_war", "EquipParamGem", mults=(1, 100, 1000),
    )
    print(f"ash_of_war: {len(gems)} (excluded internal rows: {len(excluded_gems)})")
    goods_rows = param_rows(args.param_dir, "EquipParamGoods")
    goods = build_goods(goods_rows, tables)
    gestures = param_rows(args.param_dir, "GestureParam")
    spells = build_spells(
        param_rows(args.param_dir, "Magic"),
        tables["GoodsName"],
        {row["id"]: row for row in goods_rows},
    )
    goods, entity_aliases, merged_spell_goods = merge_spell_goods_signifiers(
        goods, spells, {row["id"]: row for row in goods_rows}
    )
    print(
        f"items: {len(goods)}; spells: {len(spells)}; "
        f"merged spell Goods signifiers: {merged_spell_goods}; "
        f"compatibility aliases: {len(entity_aliases)}"
    )

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
    gesture_count = apply_gesture_signifiers(entities, gestures, tables)
    print(f"gestures: {gesture_count} named canonical entities from {len(gestures)} GestureParam rows")
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
            "ash_of_war": sum(entity["category"] == "ash_of_war" for entity in entities),
            "ash_of_war_source_rows": len(gems),
            "spell": sum(entity["kind"] == "spell" for entity in entities),
            "item": sum(entity["kind"] == "item" for entity in entities),
            "gesture": gesture_count,
            "spell_goods_signifiers_merged": merged_spell_goods,
            "entity_aliases": len(entity_aliases),
            "excluded_ash_of_war": len(excluded_gems),
            "excluded_armor_appearance_rows": len(excluded_appearance_armor),
            "excluded_internal_weapon_rows": len(excluded_weapons),
            "excluded_internal_armor_rows": len(excluded_internal_armor),
            "excluded_internal_accessory_rows": len(excluded_accessories),
        },
        "exclusions": (
            excluded_gems + excluded_appearance_armor + excluded_weapons
            + excluded_internal_armor + excluded_accessories
        ),
        "entityAliases": entity_aliases,
        "entities": entities,
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
