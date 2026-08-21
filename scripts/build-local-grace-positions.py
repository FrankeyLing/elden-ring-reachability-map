#!/usr/bin/env python3
"""Datamine grace (Site of Grace) positions directly from the local MSBE copy.

Grace is the fixed model `AEG099_060` placed as an Asset/DummyAsset part in
the parsed MSBE maps. Extracting position/entity from the game files removes
the dependency on third-party community coordinate snapshots (which carry no
license). The output is pure game-data facts: map id, entity id, instance id,
part type, XYZ position and raw studio layer.

Verification (development only): the extracted positions are cross-checked
against the previously used community snapshot coordinates; the snapshot is
NOT a dependency of this script or of the produced file.

Usage:
    python scripts/build-local-grace-positions.py
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
GRACE_MODEL = "AEG099_060"


def main() -> int:
    records = []
    failures = []
    for path in sorted(MSBE_MAPS.glob("m*.json")):
        map_id = path.stem
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            failures.append({"map_id": map_id, "error": str(exc)})
            continue
        for part in payload.get("parts", []):
            if part.get("model_name") != GRACE_MODEL:
                continue
            position = part.get("position") or {}
            records.append(
                {
                    "map_id": map_id,
                    "entity_id": part.get("entity_id"),
                    "instance_id": part.get("instance_id"),
                    "part_type": part.get("type"),
                    "position": [
                        position.get("x"),
                        position.get("y"),
                        position.get("z"),
                    ],
                    "map_studio_layer": part.get("map_studio_layer"),
                }
            )

    records.sort(key=lambda r: (r["map_id"], r["entity_id"] or 0))
    output = {
        "schema": "elden-ring-local-grace-positions@1",
        "source": {
            "msbe_maps": str(MSBE_MAPS),
            "grace_model": GRACE_MODEL,
            "method": "Datamined from the local MSBE copy (Asset/DummyAsset parts with model AEG099_060). "
            "No third-party coordinate snapshot is used.",
            "coordinate_space": "game_local_xyz",
        },
        "record_count": len(records),
        "records": records,
        "failures": failures,
    }
    (DATA / "entities" / "local-grace-positions.json").write_text(
        json.dumps(output, ensure_ascii=False), encoding="utf-8"
    )
    print(f"grace records extracted: {len(records)}, failures: {len(failures)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
