"""Build the selectable map-layer index from pinned online snapshots only."""

from __future__ import annotations

import argparse
import base64
import json
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ROOT = ROOT / "data" / "v1" / "source-snapshots"


def load(name: str):
    return json.loads((SNAPSHOT_ROOT / name).read_text(encoding="utf-8"))


def decode_chunks(prefix: str, count: int) -> list:
    chunks = [load(f"mapforgoblins-{prefix}-part{part}-20260818.json") for part in range(1, count + 1)]
    chunks.sort(key=lambda payload: payload["part"])
    expected_parts = chunks[0]["parts"] if chunks else 0
    if expected_parts != len(chunks) or [chunk["part"] for chunk in chunks] != list(range(1, expected_parts + 1)):
        raise ValueError(f"online {prefix} snapshot chunks are incomplete or out of order")
    encoded = "".join(chunk["chunk"] for chunk in chunks)
    return json.loads(zlib.decompress(base64.b64decode(encoded)).decode("utf-8"))


def map_key(value) -> str:
    text = str(value or "").strip()
    parts = text.split("_")
    if len(parts) >= 4 and parts[0].lower().startswith("m"):
        return "_".join(parts[:3])
    return text


def grid_map_key(area, grid_x, grid_z):
    if area is None or grid_x is None or grid_z is None:
        return ""
    return f"m{int(area):02d}_{int(grid_x):02d}_{int(grid_z):02d}"


def build() -> dict:
    records_by_map = {}

    def add(raw_map, source):
        normalized = map_key(raw_map)
        if not normalized:
            return
        record = records_by_map.setdefault(normalized, {"mapKey": normalized, "sources": {}, "recordCount": 0})
        record["sources"][source] = record["sources"].get(source, 0) + 1
        record["recordCount"] += 1

    for part in (1, 2):
        for row in load(f"mapforgoblins-tile-regions-part{part}-20260818.json")["records"]:
            add(row[0], "tile-regions")
    for part in (1, 2, 3):
        for row in load(f"mapforgoblins-map-points-part{part}-20260818.json")["records"]:
            add(grid_map_key(row[3], row[4], row[5]), "map-points")
    for row in load("mapforgoblins-grace-positions-20260818.json")["records"]:
        add(grid_map_key(row[1], row[2], row[3]), "grace-positions")
    for row in load("mapforgoblins-boss-positions-20260818.json")["records"]:
        add(row[2], "boss-positions")
    for name in ("mapforgoblins-map-conversions-base-20260818.json", "mapforgoblins-map-conversions-dlc-20260818.json"):
        for row in load(name)["records"]:
            add(grid_map_key(row[1], row[2], row[3]), "map-conversions")
            add(grid_map_key(row[7], row[8], row[9]), "map-conversions")
    for row in decode_chunks("item-index", 30):
        add(row[0], "items")
    for row in decode_chunks("entity-index", 22):
        add(row[1], "entities")
    for row in decode_chunks("gathering-index", 32):
        add(row[2], "gathering")

    records = sorted(records_by_map.values(), key=lambda record: record["mapKey"])
    for record in records:
        record["sourceKinds"] = sorted(record["sources"])
    return {
        "schema": "elden-ring-reachability-map/online-map-key-index@1",
        "capturedAt": "2026-08-18",
        "source": {
            "id": "map_for_goblins",
            "commit": "324a895ba51d6091534578c2ce194d0c6720edc2",
        },
        "records": records,
        "record_count": len(records),
        "source_categories": sorted({source for record in records for source in record["sources"]}),
        "routeable": False,
        "safetyBoundary": {
            "readOnly": True,
            "gameProcessAccessed": False,
            "gameFilesAccessed": False,
            "runtimeInjection": False,
            "overlay": False,
            "saveAccess": False,
            "gameDirectoryAccess": False,
        },
        "note": "map-layer selector evidence aggregated from pinned online snapshots; it does not create traversal edges",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(SNAPSHOT_ROOT / "mapforgoblins-map-key-index-20260818.json"),
    )
    args = parser.parse_args()
    output = Path(args.output)
    output.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output} with {len(json.loads(output.read_text(encoding='utf-8'))['records'])} map layers")


if __name__ == "__main__":
    main()
