#!/usr/bin/env python3
"""Build the location entity catalog from WorldMapPointParam.

Each WorldMapPointParam row is a game map icon (church, catacomb, cave,
castle, divine tower, mausoleum, ...).  Rows with a resolvable PlaceName
become location entities; the icon id maps to a location type per the
verified icon table below.

Usage:
    python scripts/build-location-catalog.py \
        --param-dir <snapshot>/extracted/param-json \
        --out data/v1/entities/location-catalog.json
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

# iconId -> location type (verified against the base game + SotE icon table)
ICON_TYPES = {
    3: "church", 4: "catacomb", 5: "ruins", 6: "shack", 8: "lookout_tower",
    9: "evergaol", 10: "gate", 11: "bridge", 13: "cave", 14: "tunnel",
    15: "well", 16: "hero_grave", 17: "sorcerer_tower", 18: "fort",
    19: "windmill", 20: "cathedral", 21: "grand_lift", 23: "divine_tower",
    24: "colosseum", 25: "castle", 26: "castle", 27: "castle", 28: "castle",
    29: "castle", 30: "minor_erdtree", 32: "town", 33: "town", 34: "town",
    35: "village", 36: "village", 37: "village", 38: "village", 39: "village",
    40: "village", 45: "mausoleum", 46: "eternal_city", 47: "eternal_city",
    50: "castle", 51: "castle", 52: "belfries", 53: "landmark", 54: "landmark",
    55: "landmark", 56: "landmark", 57: "landmark", 58: "landmark",
    59: "landmark", 60: "capital", 61: "underground", 66: "study_hall",
    87: "landmark", 208: "miquella_cross", 210: "castle", 211: "castle",
    213: "castle", 217: "landmark", 218: "manse", 230: "catacomb",
    231: "gaol", 232: "ruined_forge", 234: "cave", 240: "landmark",
    241: "castle", 242: "fort", 243: "fort", 244: "village", 245: "village",
    246: "village", 247: "church", 248: "cathedral", 249: "landmark",
    250: "ruins", 251: "town", 252: "ruins", 253: "ruins", 254: "ruins",
    255: "ruins", 256: "mausoleum", 257: "landmark", 258: "sorcerer_tower",
    259: "shack", 260: "bridge", 261: "village",
}

_suffix_re = re.compile(r"(_dlc0[12])?\.fmg$")


def load_place_names() -> dict[int, dict[str, str]]:
    names = {}
    with open(FMG_INDEX, encoding="utf-8") as fh:
        recs = json.load(fh)["records"]
    for rec in recs:
        lang = rec["language"]
        if lang not in ("engus", "zhocn"):
            continue
        fmg_name = _suffix_re.sub("", rec["fmg"].replace("\\", "/").split("/")[-1])
        if fmg_name != "PlaceName":
            continue
        entry = names.setdefault(rec["id"], {})
        entry["en" if lang == "engus" else "zh"] = rec["text"]
    return names


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


def param_rows(param_dir: Path, name: str) -> list[dict[str, Any]]:
    path = param_dir / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"param dump missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))["rows"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--param-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "location-catalog.json")
    args = parser.parse_args()

    place_names = load_place_names()
    rows = param_rows(args.param_dir, "WorldMapPointParam")

    entities = []
    skipped = 0
    used_ids: dict[str, int] = {}
    for r in rows:
        c = r["cells"]
        icon = c.get("iconId")
        ltype = ICON_TYPES.get(icon)
        t1 = c.get("textId1")
        entry = place_names.get(t1) if t1 else None
        en = clean_name((entry or {}).get("en"))
        if not en:
            skipped += 1
            continue
        base_id = f"location_{slugify(en)}"
        count = used_ids.get(base_id, 0) + 1
        used_ids[base_id] = count
        lid = base_id if count == 1 else f"{base_id}_{count}"
        entities.append({
            "id": lid,
            "kind": "location",
            "category": ltype or "unknown",
            "class": None,
            "name": {"en": en, "zh": clean_name((entry or {}).get("zh")) or en},
            "signifiers": [{"type": "param", "param": "WorldMapPointParam", "rows": [r["id"]]}],
            "properties": {
                "iconId": icon,
                "eventFlagId": c.get("eventFlagId"),
                "position": {"x": c.get("posX"), "y": c.get("posY"), "z": c.get("posZ")},
                "areaNo": c.get("areaNo"),
            },
            "variant_count": 1,
        })

    from collections import Counter
    print(f"location entities: {len(entities)}, skipped unnamed: {skipped}")
    print("type distribution:", dict(Counter(e["category"] for e in entities)))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "errn-location-catalog@1",
        "built_at": "2026-08-20",
        "built_from": {
            "param": "WorldMapPointParam",
            "policy": "Official PlaceName texts; icon table verified against base game + SotE.",
        },
        "stats": {"locations": len(entities), "unnamed_skipped": skipped},
        "entities": entities,
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
