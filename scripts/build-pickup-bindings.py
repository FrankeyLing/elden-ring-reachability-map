#!/usr/bin/env python3
"""Bind pickup lots to MSB treasure positions.

For every Treasure event in the (re-extracted) MSB maps:
  - ItemLotID -> ItemLotParam_map row -> items (with official names)
  - TreasurePartName -> part position (map-local MSB coordinates)

Outputs data/v1/entities/pickup-location-bindings.json with one entry per
lot carrying all pickup positions.

Usage:
    python scripts/build-pickup-bindings.py \
        --msb-dir <snapshot>/extracted/parsed-mapstudio-all-v2/maps \
        --param-dir <snapshot>/extracted/param-json \
        --out data/v1/entities/pickup-location-bindings.json
"""

from __future__ import annotations

import argparse
import copy
import glob
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FMG_INDEX = ROOT / "data" / "v1" / "entities" / "official-fmg-bilingual-index.json"

LOT_CATEGORY_TABLES = {1: "GoodsName", 2: "WeaponName", 3: "ProtectorName",
                       4: "AccessoryName", 5: "GemName"}
LOT_CATEGORY_KIND = {1: "item", 2: "weapon", 3: "armor", 4: "accessory", 5: "ash_of_war"}
LOT_CHAIN_REFERENCE = "https://soulsmodding.wikidot.com/param:itemlotparam"

_suffix_re = re.compile(r"(_dlc0[12])?\.fmg$")


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


def slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def expand_lot_chain(
    root_lot_id: int,
    lot_by_id: dict[int, dict],
    referenced_lot_ids: set[int],
) -> list[int]:
    """Return the sequential map-lot rows belonging to one Treasure root."""
    chain: list[int] = []
    lot_id = root_lot_id
    while lot_id in lot_by_id:
        if lot_id != root_lot_id and lot_id in referenced_lot_ids:
            break
        chain.append(lot_id)
        lot_id += 1
    return chain


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--msb-dir", type=Path, required=True)
    parser.add_argument("--param-dir", type=Path, required=True)
    parser.add_argument("--acquisition", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "acquisition-registry.json")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "pickup-location-bindings.json")
    args = parser.parse_args()

    tables = load_name_tables()
    lot_rows = json.loads((args.param_dir / "ItemLotParam_map.json").read_text(encoding="utf-8"))["rows"]
    lot_by_id = {r["id"]: r["cells"] for r in lot_rows}
    acquisition = json.loads(args.acquisition.read_text(encoding="utf-8"))
    canonical_items_by_lot = {
        relation["lot"]["rowId"]: relation.get("items", [])
        for relation in acquisition.get("relations", [])
        if relation.get("method") == "pickup" and relation.get("lot", {}).get("rowId") is not None
    }

    bindings: dict[int, dict] = {}
    source_exclusions: list[dict[str, Any]] = []
    for path in sorted(glob.glob(str(args.msb_dir / "*.json"))):
        if path.endswith("batch-manifest.json"):
            continue
        d = json.load(open(path, encoding="utf-8"))
        map_key = d.get("source_entry", Path(path).name[:-5])
        parts = {p["name"]: p for p in d.get("parts", [])}
        for ev in d.get("events", []):
            if ev.get("type") != "Treasure":
                continue
            extra = ev.get("extra", {})
            lot = extra.get("ItemLotID")
            if not lot:
                continue
            part_name = extra.get("TreasurePartName")
            position = None
            if part_name and part_name in parts:
                position = parts[part_name].get("position")
            if not part_name or part_name not in parts or not isinstance(position, dict):
                source_exclusions.append({
                    "id": f"orphan-treasure:{map_key}:{ev.get('event_id')}:{lot}",
                    "status": "orphan_treasure_event_without_part",
                    "lot": lot,
                    "map": map_key,
                    "eventId": ev.get("event_id"),
                    "treasureName": ev.get("name"),
                    "treasurePartName": part_name,
                    "inChest": extra.get("InChest"),
                    "evidence": [
                        f"local MSBE Treasure event {ev.get('event_id')} in {map_key}",
                        f"ItemLotParam_map row {lot}",
                        "TreasurePartName is null or does not resolve to a positioned MSBE Part",
                    ],
                    "verification": "local_msbe_uninstantiated_treasure",
                })
                continue
            entry = bindings.setdefault(lot, {
                "lot": lot,
                "items": [],
                "positions": [],
                "count": 0,
            })
            entry["positions"].append({
                "map": map_key,
                "part": part_name,
                "position": position,
                "inChest": extra.get("InChest"),
                "treasureName": ev.get("name"),
            })
            entry["count"] += 1

    referenced_lot_ids = set(bindings)

    # resolve items per lot
    for lot, entry in bindings.items():
        chain_ids = expand_lot_chain(lot, lot_by_id, referenced_lot_ids)
        if not chain_ids:
            continue
        entry["sourceItemLotRows"] = chain_ids

        root_relation_items = canonical_items_by_lot.get(lot, [])
        root_relation_has_chain = any(
            relation.get("lot", {}).get("rowId") == lot
            and len(relation.get("sourceItemLotRows", [])) > 1
            for relation in acquisition.get("relations", [])
            if relation.get("method") == "pickup"
        )
        if root_relation_has_chain:
            entry["items"] = copy.deepcopy(root_relation_items)
            continue

        for chain_lot_id in chain_ids:
            if chain_lot_id in canonical_items_by_lot:
                entry["items"].extend(copy.deepcopy(canonical_items_by_lot[chain_lot_id]))
                continue
            cells = lot_by_id.get(chain_lot_id)
            if not cells:
                continue
            for k in range(1, 9):
                iid = cells.get(f"lotItemId{k:02d}")
                cat = cells.get(f"lotItemCategory{k:02d}")
                if not iid or iid <= 0:
                    continue
                fmg = LOT_CATEGORY_TABLES.get(cat, "GoodsName")
                nm = tables.get(fmg, {}).get(iid)
                en = clean_name((nm or {}).get("en"))
                if not en:
                    continue
                entry["items"].append({
                    "item": f"{LOT_CATEGORY_KIND.get(cat, 'item')}_{slugify(en)}",
                    "name": {"en": en, "zh": clean_name((nm or {}).get("zh")) or en},
                    "lot": chain_lot_id,
                    "slot": k,
                    "num": cells.get(f"lotItemNum{k:02d}"),
                })

        # Acquisition normalization is the single source of truth for the
        # canonical target id.  It folds affinity/altered signifiers and
        # preserves their source ids, so the topology binding cannot recreate
        # a second searchable entity for the same item.
        if lot in canonical_items_by_lot and not entry["items"]:
            entry["items"] = canonical_items_by_lot[lot]

    with_position = sum(1 for b in bindings.values() if any(p["position"] for p in b["positions"]))
    print(f"bound lots: {len(bindings)}, with positions: {with_position}, "
          f"pickup instances: {sum(b['count'] for b in bindings.values())}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "errn-pickup-location-bindings@1",
        "built_at": "2026-08-20",
        "built_from": {
            "msb_dir": str(args.msb_dir),
            "param": "ItemLotParam_map",
            "item_lot_chain_reference": LOT_CHAIN_REFERENCE,
            "policy": "Positions are map-local MSB coordinates from TreasurePartName parts.",
        },
        "stats": {"lots": len(bindings), "with_positions": with_position,
                  "instances": sum(b["count"] for b in bindings.values()),
                  "sourceExclusionCount": len(source_exclusions)},
        "sourceExclusions": source_exclusions,
        "bindings": [b for b in bindings.values() if b["positions"]],
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
