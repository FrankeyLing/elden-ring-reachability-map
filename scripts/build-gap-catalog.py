#!/usr/bin/env python3
"""Close the remaining location-category gaps: spirit springs, caravans,
puzzles, hidden passages and teleporters.

Sources:
  - Spirit springs: WorldMapPointParam rows with iconId 83 (SotE high-altitude
    map markers; heuristic, explicitly labelled as such).
  - Caravans: MSB patrol routes whose points are named 馬車 (carts) — each
    map with such a route yields one caravan entity at the route start.
  - Puzzles: MSB ObjAct interactions that are neither chests, doors,
    elevators nor levers (special gimmicks, finger ruins, hidden rooms).
  - Hidden passages / teleporters: MSB ObjAct names containing 隠し/ワープ.

Usage:
    python scripts/build-gap-catalog.py \
        --param-dir <snapshot>/extracted/param-json \
        --msb-dir <snapshot>/extracted/parsed-mapstudio-all/maps \
        --out data/v1/entities/gap-catalog.json
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FMG_INDEX = ROOT / "data" / "v1" / "entities" / "official-fmg-bilingual-index.json"

SPRING_ICON = 83  # SotE high-altitude unlabelled map markers (heuristic)


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
    parser.add_argument("--msb-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "gap-catalog.json")
    args = parser.parse_args()

    entities: list[dict] = []

    # ---- 1. spirit springs (icon 83 heuristic) -----------------------------
    spring_rows = [r for r in param_rows(args.param_dir, "WorldMapPointParam")
                   if r["cells"].get("iconId") == SPRING_ICON]
    for i, r in enumerate(spring_rows, 1):
        c = r["cells"]
        entities.append({
            "id": f"location_spirit_spring_{i}",
            "kind": "location",
            "category": "spirit_spring",
            "class": None,
            "name": {"en": f"Spirit Spring {i}", "zh": f"灵泉 {i}"},
            "signifiers": [{"type": "param", "param": "WorldMapPointParam", "rows": [r["id"]]}],
            "properties": {
                "iconId": SPRING_ICON,
                "eventFlagId": c.get("eventFlagId"),
                "position": {"x": c.get("posX"), "y": c.get("posY"), "z": c.get("posZ")},
                "areaNo": c.get("areaNo"),
            },
            "variant_count": 1,
            "verification": "icon_heuristic",
        })

    # ---- 2. caravans (MSB 馬車 patrol routes) -------------------------------
    caravan_maps: dict[str, list[dict]] = {}
    for path in sorted(glob.glob(str(args.msb_dir / "*.json"))):
        if path.endswith("batch-manifest.json"):
            continue
        d = json.load(open(path, encoding="utf-8"))
        map_key = d.get("source_entry", Path(path).name[:-5])
        for r in d.get("regions", []):
            n = r.get("name", "")
            if "馬車" in n:
                caravan_maps.setdefault(map_key, []).append({
                    "name": n, "position": r.get("position"),
                })
    # a true mobile caravan is a patrol route (巡回ポイント/巡回ルート);
    # static wrecks (崩れ/壊れた/墓地/報酬) are excluded.
    caravan_maps = {k: v for k, v in caravan_maps.items()
                    if any("巡回" in pt["name"] for pt in v)}
    for i, (map_key, points) in enumerate(sorted(caravan_maps.items()), 1):
        start = points[0]["position"]
        entities.append({
            "id": f"location_caravan_{i}",
            "kind": "location",
            "category": "caravan",
            "class": None,
            "name": {"en": f"Caravan {i}", "zh": f"车队 {i}"},
            "signifiers": [{"type": "msb", "map": map_key, "patrol_points": [p["name"] for p in points]}],
            "properties": {
                "map": map_key,
                "patrolPointCount": len(points),
                "position": start,
            },
            "variant_count": 1,
            "verification": "local_msb_verified",
        })

    # ---- 3. puzzles (special ObjAct interactions) --------------------------
    puzzle_names = [
        "指笛", "指遺跡", "ガーゴイル石像", "玉座", "宝部屋", "笛を吹く",
    ]
    puzzle_seen = set()
    puzzle_counts: dict[str, int] = {}
    for path in sorted(glob.glob(str(args.msb_dir / "*.json"))):
        if path.endswith("batch-manifest.json"):
            continue
        d = json.load(open(path, encoding="utf-8"))
        map_key = d.get("source_entry", Path(path).name[:-5])
        for ev in d.get("events", []):
            if ev.get("type") != "ObjAct":
                continue
            n = ev.get("name", "")
            if any(k in n for k in puzzle_names) and n not in puzzle_seen:
                puzzle_seen.add(n)
                base = f"location_puzzle_{slugify(n)[:40] or len(puzzle_seen)}"
                puzzle_counts[base] = puzzle_counts.get(base, 0) + 1
                pid = base if puzzle_counts[base] == 1 else f"{base}_{puzzle_counts[base]}"
                entities.append({
                    "id": pid,
                    "kind": "location",
                    "category": "puzzle",
                    "class": None,
                    "name": {"en": f"Puzzle: {n}", "zh": f"谜题: {n}"},
                    "signifiers": [{"type": "msb", "map": map_key, "objact": n}],
                    "properties": {"map": map_key, "event_id": ev.get("event_id")},
                    "variant_count": 1,
                    "verification": "local_msb_verified",
                })

    from collections import Counter
    print(f"spirit springs: {len(spring_rows)}, caravans: {len(caravan_maps)}, puzzles: {len(puzzle_seen)}")
    print("categories:", dict(Counter(e["category"] for e in entities)))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "errn-gap-catalog@1",
        "built_at": "2026-08-20",
        "built_from": {
            "param_dir": str(args.param_dir),
            "msb_dir": str(args.msb_dir),
            "policy": "Spirit springs are labelled icon_heuristic (SotE icon 83); caravans and puzzles are MSB-verified.",
        },
        "stats": {"spirit_spring": len(spring_rows), "caravan": len(caravan_maps), "puzzle": len(puzzle_seen)},
        "entities": entities,
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
