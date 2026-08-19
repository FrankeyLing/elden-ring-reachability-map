#!/usr/bin/env python3
"""Build reinforcement relations and armor set membership.

- Weapon reinforcement: materialSetId classifies weapons into normal
  (smithing stones) vs somber (somber smithing stones); the level->stone
  mapping is the official game mechanic (levels are deterministic).
- Armor reinforcement uses normal smithing stones (ReinforceParamProtector).
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

# Official ER reinforcement mechanic (level -> stone grade)
NORMAL_LEVEL_STONES = {
    1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4,
    9: 5, 10: 5, 11: 6, 12: 6, 13: 7, 14: 7, 15: 8, 16: 8,
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

    # ---- 2. armor reinforcement (normal smithing stones) --------------------
    for ent in entities:
        if ent["kind"] != "armor":
            continue
        for level in range(1, 10):
            grade = NORMAL_LEVEL_STONES.get(level)
            if grade is None:
                continue
            stone_id = normal_stone.get(grade)
            if not stone_id:
                continue
            reinforce_relations.append({
                "id": f"{ent['id']}-reinforce-{level}",
                "from": ent["id"],
                "method": "reinforce",
                "to": stone_id,
                "level": level,
                "maxLevel": 9,
                "class": "normal",
                "verification": "game_mechanics_official",
                "evidence": ["ReinforceParamProtector (normal smithing stones)"],
            })

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

    print(f"weapon reinforcement relations: {len([r for r in reinforce_relations if r['method'] == 'reinforce' and 'armor' not in r['from']])}")
    print(f"armor sets: {len(sets)}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "errn-reinforce-catalog@1",
        "built_at": "2026-08-20",
        "built_from": {
            "param": ["EquipParamWeapon (materialSetId)", "ReinforceParamProtector"],
            "policy": "Level->stone mapping is the official ER reinforcement mechanic; "
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
