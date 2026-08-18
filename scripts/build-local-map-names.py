#!/usr/bin/env python3
"""Extract the authoritative map display names from parsed MSBE files.

Every map's MapNameOverride regions carry a TextID into PlaceName.fmg; the
bilingual FMG index then yields the official English and Simplified-Chinese
display names for that map. This is the ground truth the V1.0 completeness
verification uses to resolve local map ids to semantic regions.

Output: data/v1/entities/local-msbe-map-names.json

Usage:
    python scripts/build-local-map-names.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "v1"
MSBE_MAPS = Path(
    "C:/Users/Frankey/ZCodeProject/local-snapshots/elden-ring-20260818/extracted/parsed-mapstudio-all-extra2/maps"
)


def fmg_base(name: str) -> str:
    return name.replace("\\", "/").split("/")[-1]


def main() -> int:
    # bilingual FMG dictionary: (fmg, id) -> {eng, zh}; DLC map names live in
    # PlaceName_dlc01/02.fmg with the same id space as PlaceName.fmg
    fmg = json.loads((DATA / "entities" / "official-fmg-bilingual-index.json").read_text(encoding="utf-8"))
    place_names: dict[int, dict[str, str]] = {}
    for record in fmg.get("records", []):
        if not fmg_base(record["fmg"]).startswith("PlaceName"):
            continue
        entry = place_names.setdefault(record["id"], {})
        if record["language"] not in entry or not entry[record["language"]]:
            entry[record["language"]] = record["text"]

    # scan all parsed maps for MapNameOverride TextID
    map_names = []
    failures = []
    for path in sorted(MSBE_MAPS.glob("m*.json")):
        map_id = path.stem
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            failures.append({"map_id": map_id, "error": str(exc)})
            continue
        text_ids = set()
        for region in payload.get("regions", []):
            if region.get("type") != "MapNameOverride":
                continue
            text_id = (region.get("extra") or {}).get("TextID")
            if isinstance(text_id, int) and text_id > 0:
                text_ids.add(text_id)
        for text_id in sorted(text_ids):
            names = place_names.get(text_id, {})
            map_names.append(
                {
                    "map_id": map_id,
                    "text_id": text_id,
                    "eng": names.get("engus", ""),
                    "zh": names.get("zhocn", ""),
                }
            )

    output = {
        "schema": "elden-ring-local-msbe-map-names@1",
        "source": {"msbe_maps": str(MSBE_MAPS), "fmg": "PlaceName.fmg (bilingual)"},
        "map_count": len({m["map_id"] for m in map_names}),
        "records": map_names,
        "failures": failures,
    }
    (DATA / "entities" / "local-msbe-map-names.json").write_text(
        json.dumps(output, ensure_ascii=False), encoding="utf-8"
    )
    print(f"maps with names: {output['map_count']}, records: {len(map_names)}, failures: {len(failures)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
