#!/usr/bin/env python3
"""Build weapon reinforcement relations and armor set membership.

- Weapon reinforcement: materialSetId classifies weapons into normal
  (smithing stones) vs somber (somber smithing stones); the level->stone
  mapping is the official game mechanic (levels are deterministic).
- Elden Ring armor is not upgradeable; no armor reinforcement relations are
  generated.
- Armor sets: armor entities sharing an owner prefix ("Alberich's ...")
  form one set with head/chest/arms/legs members.

Usage:
    python scripts/build-reinforce-catalog.py \
        --param-dir <snapshot>/extracted/param-json \
        --registry data/v1/entities/entity-registry.json \
        --out data/v1/entities/reinforce-catalog.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# Official Elden Ring normal weapon mechanic (level -> stone grade).
# Normal stones cover three consecutive levels each; +25 uses an ancient
# dragon stone. Somber weapons cover one level per somber stone grade.
NORMAL_LEVEL_STONES = {
    1: 1, 2: 1, 3: 1, 4: 2, 5: 2, 6: 2, 7: 3, 8: 3, 9: 3,
    10: 4, 11: 4, 12: 4, 13: 5, 14: 5, 15: 5,
    16: 6, 17: 6, 18: 6, 19: 7, 20: 7, 21: 7,
    22: 8, 23: 8, 24: 8,
    25: "ancient_dragon",
}
SOMBER_LEVEL_STONES = {
    1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9,
    10: "ancient_dragon_somber",
}
NORMAL_MAX = 25
SOMBER_MAX = 10


def slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def param_rows(param_dir: Path, name: str) -> list[dict[str, Any]]:
    path = param_dir / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"param dump missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))["rows"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--param-dir", type=Path, required=True)
    parser.add_argument("--registry", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "entity-registry.json")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "reinforce-catalog.json")
    args = parser.parse_args()

    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    entities = registry["entities"]
    by_id = {e["id"]: e for e in entities}

    # ---- 1. weapon reinforcement class -------------------------------------
    weapon_rows = param_rows(args.param_dir, "EquipParamWeapon")
    goods_rows = param_rows(args.param_dir, "EquipParamGoods")
    goods_by_id = {row["id"]: row for row in goods_rows}
    stone_entities = {e["id"]: e for e in entities
                      if e["category"] == "smithing_stone"}
    print("smithing stone entities:", {k: v["name"]["en"] for k, v in list(stone_entities.items())[:5]})

    weapon_class: dict[int, str] = {}
    for r in weapon_rows:
        ms = r["cells"].get("materialSetId")
        if ms == 2200:
            weapon_class[r["id"]] = "somber"
        elif ms == 0:
            weapon_class[r["id"]] = "normal"

    reinforce_relations = []
    normal_stone = {g: f"item_{slugify(f'Smithing Stone [{g}]')}" for g in range(1, 9)}
    somber_stone = {g: f"item_{slugify(f'Somber Smithing Stone [{g}]')}" for g in range(1, 10)}
    ancient = "item_ancient_dragon_smithing_stone"
    ancient_somber = "item_ancient_dragon_somber_smithing_stone"
    grave_glovewort = {g: f"item_grave_glovewort_{g}" for g in range(1, 10)}
    ghost_glovewort = {g: f"item_ghost_glovewort_{g}" for g in range(1, 10)}
    great_grave_glovewort = "item_great_grave_glovewort"
    great_ghost_glovewort = "item_great_ghost_glovewort"

    # resolve actual entity ids from the registry names
    for eid, ent in stone_entities.items():
        en = ent["name"]["en"]
        if en.startswith("Somber Smithing Stone"):
            somber_stone[int(en[en.index("[") + 1:en.index("]")])] = eid
        elif "Somber Ancient Dragon" in en or "Ancient Dragon Somber" in en:
            ancient_somber = eid
        elif en.startswith("Smithing Stone"):
            normal_stone[int(en[en.index("[") + 1:en.index("]")])] = eid
        elif "Ancient Dragon Smithing Stone" in en:
            ancient = eid

    glovewort_entities = {
        ent["name"]["en"]: ent["id"]
        for ent in entities
        if ent.get("category") == "grave_glovewort"
    }
    for level in range(1, 10):
        grave_glovewort[level] = glovewort_entities.get(
            f"Grave Glovewort [{level}]", grave_glovewort[level]
        )
        ghost_glovewort[level] = glovewort_entities.get(
            f"Ghost Glovewort [{level}]", ghost_glovewort[level]
        )
    great_grave_glovewort = glovewort_entities.get(
        "Great Grave Glovewort", great_grave_glovewort
    )
    great_ghost_glovewort = glovewort_entities.get(
        "Great Ghost Glovewort", great_ghost_glovewort
    )

    # weapon entity -> material class via signifier rows
    for ent in entities:
        if ent["kind"] != "weapon":
            continue
        rows = ent["signifiers"][0]["rows"]
        cls = None
        for rid in rows:
            cls = weapon_class.get(rid)
            if cls:
                break
        if cls is None:
            continue
        stones = somber_stone if cls == "somber" else normal_stone
        mapping = SOMBER_LEVEL_STONES if cls == "somber" else NORMAL_LEVEL_STONES
        max_lv = SOMBER_MAX if cls == "somber" else NORMAL_MAX
        for level, grade in mapping.items():
            if grade == "ancient_dragon":
                stone_id = ancient
            elif grade == "ancient_dragon_somber":
                stone_id = ancient_somber
            else:
                stone_id = stones.get(grade)
            if not stone_id:
                continue
            reinforce_relations.append({
                "id": f"{ent['id']}-reinforce-{level}",
                "from": ent["id"],
                "method": "reinforce",
                "to": stone_id,
                "level": level,
                "maxLevel": max_lv,
                "class": cls,
                "verification": "game_mechanics_official",
                "evidence": [f"materialSetId={next((weapon_class.get(r) for r in rows if weapon_class.get(r)), '')} "
                             f"(EquipParamWeapon)"],
            })

    # ---- 2. spirit ash reinforcement --------------------------------------
    # EquipParamGoods sortGroupId 10 is ordinary spirit ash; 20/30 are
    # renowned/special spirit ash. Both use ten reinforcement levels, but the
    # material family differs. Rows without a reinforcement chain are not
    # upgradeable ashes and are intentionally skipped.
    spirit_reinforcement_count = 0
    for ent in entities:
        if ent.get("kind") != "item" or ent.get("category") != "spirit_ash":
            continue
        rows = ent.get("signifiers", [{}])[0].get("rows", [])
        goods = goods_by_id.get(rows[0]) if rows else None
        cells = goods.get("cells", {}) if goods else {}
        if cells.get("reinforceGoodsId", -1) == -1:
            continue
        sort_group = cells.get("sortGroupId")
        if sort_group == 10:
            materials = grave_glovewort
            great_material = great_grave_glovewort
            ash_class = "grave_glovewort"
        elif sort_group in (20, 30):
            materials = ghost_glovewort
            great_material = great_ghost_glovewort
            ash_class = "ghost_glovewort"
        else:
            continue
        for level in range(1, 11):
            material = great_material if level == 10 else materials.get(level)
            if not material:
                continue
            reinforce_relations.append({
                "id": f"{ent['id']}-reinforce-{level}",
                "from": ent["id"],
                "method": "reinforce",
                "to": material,
                "level": level,
                "maxLevel": 10,
                "class": ash_class,
                "verification": "game_mechanics_official",
                "evidence": [
                    f"EquipParamGoods row {rows[0]} sortGroupId={sort_group} "
                    "reinforceMaterialId chain"
                ],
            })
            spirit_reinforcement_count += 1

    # ---- 3. armor sets -------------------------------------------------------
    armor_entities = [e for e in entities if e["kind"] == "armor"]
    sets: dict[str, dict] = {}
    for ent in armor_entities:
        en = ent["name"]["en"]
        m = re.match(r"^(.*?'s) ", en)
        if not m:
            continue
        prefix = m.group(1)
        entry = sets.setdefault(prefix, {
            "id": f"armor_set_{slugify(prefix)}",
            "kind": "armor_set",
            "category": "armor_set",
            "name": {"en": prefix, "zh": None},
            "members": [],
        })
        entry["members"].append({
            "item": ent["id"],
            "name": en,
            "zh": ent["name"].get("zh"),
        })

    for prefix, entry in sets.items():
        zh_candidates = [m["zh"] for m in entry["members"] if m["zh"]]
        if zh_candidates:
            # set zh name: strip the slot word from the first member zh name
            zh = zh_candidates[0]
            for slot in ("头盔", "铠甲", "臂甲", "腿甲", "帽子", "长袍", "裤子", "护腕", "头罩", "臂套", "靴子"):
                idx = zh.find(slot)
                if idx > 0:
                    zh = zh[:idx]
                    break
            entry["name"]["zh"] = zh or zh_candidates[0]
        else:
            entry["name"]["zh"] = entry["name"]["en"]

    print(f"weapon reinforcement relations: {len(reinforce_relations)}")
    print(f"spirit ash reinforcement relations: {spirit_reinforcement_count}")
    print("armor reinforcement relations: 0 (armor is not upgradeable in Elden Ring)")
    print(f"armor sets: {len(sets)}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "errn-reinforce-catalog@1",
        "built_at": "2026-08-20",
        "built_from": {
            "param": ["EquipParamWeapon (materialSetId)", "EquipParamGoods (spirit ash reinforcement chain)"],
            "policy": "Level->stone mapping is the official ER reinforcement mechanic; "
                      "armor reinforcement is excluded because Elden Ring armor is not upgradeable; "
                      "no quantities recorded (not present in the params).",
        },
        "stats": {
            "reinforce_relations": len(reinforce_relations),
            "armor_sets": len(sets),
            "armor_set_members": sum(len(s["members"]) for s in sets.values()),
        },
        "reinforcements": reinforce_relations,
        "armor_sets": sorted(sets.values(), key=lambda s: s["id"]),
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
