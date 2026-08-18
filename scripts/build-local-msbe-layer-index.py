#!/usr/bin/env python3
"""Build an exact MSBE map-studio-layer partition index.

The raw layer value is preserved as-is.  This is a native layer partition,
not a guessed floor name and not a collision/navmesh walkability claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_LAYER = 4294967295


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def update_bounds(bounds: dict[str, float], position: dict[str, Any]) -> None:
    for axis in ("x", "y", "z"):
        value = position.get(axis)
        if not isinstance(value, (int, float)):
            continue
        bounds[f"min_{axis}"] = min(bounds.get(f"min_{axis}", value), value)
        bounds[f"max_{axis}"] = max(bounds.get(f"max_{axis}", value), value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--maps-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    maps_root = args.maps_root.resolve()
    files = sorted(maps_root.glob("*.json"))
    layers: dict[tuple[str, int], dict[str, Any]] = {}
    map_coverage: dict[str, dict[str, Any]] = {}
    missing_layer_parts = 0
    total_parts = 0
    source_sha256 = hashlib.sha256()

    for path in files:
        raw = path.read_bytes()
        source_sha256.update(path.name.encode("utf-8"))
        source_sha256.update(raw)
        payload = json.loads(raw.decode("utf-8"))
        map_id = path.stem
        map_coverage[map_id] = {
            "map_id": map_id,
            "source_file": str(path),
            "part_count": 0,
            "region_count": len(payload.get("regions", [])),
            "event_count": len(payload.get("events", [])),
            "layer_values": set(),
            "parts_missing_layer_value": 0,
            "routeable": False,
        }
        for part in payload.get("parts", []):
            map_coverage[map_id]["part_count"] += 1
            total_parts += 1
            layer = part.get("map_studio_layer")
            if not isinstance(layer, int):
                missing_layer_parts += 1
                map_coverage[map_id]["parts_missing_layer_value"] += 1
                continue
            map_coverage[map_id]["layer_values"].add(layer)
            key = (map_id, layer)
            row = layers.setdefault(
                key,
                {
                    "id": f"local-layer:{map_id}:{layer}",
                    "map_id": map_id,
                    "map_studio_layer": layer,
                    "is_default_layer_value": layer == DEFAULT_LAYER,
                    "part_count": 0,
                    "part_type_counts": Counter(),
                    "coordinate_bounds": {},
                    "sample_parts": [],
                    "coordinate_system": "Elden Ring MSBE game-native XYZ",
                    "original_game_coordinates": True,
                    "local_game_verified": True,
                    "topology_status": "native_layer_partition",
                    "routeable": False,
                },
            )
            row["part_count"] += 1
            row["part_type_counts"][str(part.get("type") or "unknown")] += 1
            update_bounds(row["coordinate_bounds"], part.get("position") or {})
            if len(row["sample_parts"]) < 8:
                row["sample_parts"].append(
                    {
                        "name": part.get("name"),
                        "type": part.get("type"),
                        "instance_id": part.get("instance_id"),
                        "entity_id": part.get("entity_id"),
                        "position": part.get("position"),
                    }
                )

    records = []
    for row in sorted(layers.values(), key=lambda item: (item["map_id"], item["map_studio_layer"])):
        row["part_type_counts"] = dict(sorted(row["part_type_counts"].items()))
        records.append(row)

    map_layer_coverage = []
    for map_id in sorted(map_coverage):
        row = map_coverage[map_id]
        if row["part_count"] == 0:
            coverage_status = "source_map_has_no_parts"
        elif row["parts_missing_layer_value"]:
            coverage_status = "part_layer_value_missing"
        else:
            coverage_status = "exact_raw_layer_partition"
        map_layer_coverage.append(
            {
                **row,
                "layer_values": sorted(row["layer_values"]),
                "layer_partition_status": coverage_status,
            }
        )

    output = {
        "schema": "elden-ring-local-msbe-layer-index@1",
        "source": {
            "maps_root": str(maps_root),
            "source_file_count": len(files),
            "ordered_file_bytes_sha256": source_sha256.hexdigest().upper(),
        },
        "model": {
            "purpose": "exact native MSBE map-studio-layer partition",
            "layer_value_semantics": "raw game field preserved; floor/roof names are not inferred",
            "continuous_walkability_evaluated": False,
            "havok_required_for_this_layer": False,
            "routeable": False,
        },
        "status": {
            "source_files": len(files),
            "layer_records": len(records),
            "map_coverage_records": len(map_layer_coverage),
            "maps_with_layer_records": len({row["map_id"] for row in records}),
            "maps_without_layer_records": len(
                {
                    row["map_id"]
                    for row in map_layer_coverage
                    if row["layer_partition_status"] != "exact_raw_layer_partition"
                }
            ),
            "map_layer_coverage_status_counts": dict(
                sorted(
                    Counter(row["layer_partition_status"] for row in map_layer_coverage).items()
                )
            ),
            "distinct_layer_values": len({row["map_studio_layer"] for row in records}),
            "total_parts": total_parts,
            "parts_with_explicit_layer_value": total_parts - missing_layer_parts,
            "parts_missing_layer_value": missing_layer_parts,
            "default_layer_part_count": sum(
                row["part_count"] for row in records if row["is_default_layer_value"]
            ),
            "nondefault_layer_part_count": sum(
                row["part_count"] for row in records if not row["is_default_layer_value"]
            ),
            "routeable_records": 0,
            "all_records_routeable_false": all(row["routeable"] is False for row in records),
        },
        "records": records,
        "map_layer_coverage": map_layer_coverage,
        "note": "Layer values are exact MSBE metadata. They partition the abstract entity layer but do not prove player walkability or assign human floor names.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
