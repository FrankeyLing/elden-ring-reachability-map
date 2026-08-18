"""Build a compact local-game map/transition index from an external MSBE snapshot.

The input is deliberately outside the repository. Only the compact, derived
index is written to the repository. It preserves the source hashes and the
raw four-byte map IDs so wildcard/unknown targets cannot be mistaken for
ordinary walk edges.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


MAP_FILE_RE = re.compile(r"^(m\d+_\d+_\d+_\d+)\.json$")


def vector_bounds(items: list[dict[str, Any]]) -> dict[str, Any]:
    points = [item["position"] for item in items if item.get("position")]
    if not points:
        return {"count": 0, "nonzero_count": 0, "min": None, "max": None}
    nonzero = [point for point in points if any(abs(float(point[k])) > 1e-6 for k in ("x", "y", "z"))]

    def extrema(key: str) -> dict[str, float]:
        return {axis: min(float(point[axis]) for point in points) for axis in ("x", "y", "z")} if key == "min" else {
            axis: max(float(point[axis]) for point in points) for axis in ("x", "y", "z")
        }

    return {
        "count": len(points),
        "nonzero_count": len(nonzero),
        "min": extrema("min"),
        "max": extrema("max"),
    }


def canonical_map_id(raw: Any) -> tuple[str | None, bool]:
    if not isinstance(raw, list) or len(raw) != 4:
        return None, False
    try:
        values = [int(value) for value in raw]
    except (TypeError, ValueError):
        return None, False
    if any(value < 0 or value > 255 for value in values):
        return None, False
    wildcard = 255 in values
    normalized = [0 if value == 255 else value for value in values]
    return "m" + "_".join(f"{value:02d}" for value in normalized), wildcard


def source_relative(path: Path, input_root: Path) -> str:
    return path.relative_to(input_root).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_root", type=Path)
    parser.add_argument("output_path", type=Path)
    args = parser.parse_args()
    input_root = args.input_root.resolve()
    output_path = args.output_path.resolve()
    map_dir = input_root / "maps"
    manifest_path = input_root / "batch-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_hash_by_path = {Path(row["source"]).name: row["source_sha256"] for row in manifest["successes"]}

    maps: list[dict[str, Any]] = []
    map_ids: set[str] = set()
    transitions: list[dict[str, Any]] = []
    part_totals = Counter()
    region_totals = Counter()
    event_totals = Counter()
    total_models = total_parts = total_regions = total_events = total_routes = 0

    for path in sorted(map_dir.glob("*.json")):
        match = MAP_FILE_RE.match(path.name)
        if not match:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        map_id = "m" + match.group(1).removeprefix("m")
        map_ids.add(map_id)
        parts = payload.get("parts", [])
        regions = payload.get("regions", [])
        events = payload.get("events", [])
        part_counts = Counter(part.get("type", "Unknown") for part in parts)
        region_counts = Counter(region.get("type", "Unknown") for region in regions)
        event_counts = Counter(event.get("type", "Unknown") for event in events)
        part_totals.update(part_counts)
        region_totals.update(region_counts)
        event_totals.update(event_counts)
        total_models += int(payload.get("models", 0))
        total_parts += len(parts)
        total_regions += len(regions)
        total_events += len(events)
        total_routes += int(payload.get("routes", 0))

        for part in parts:
            if part.get("type") != "ConnectCollision":
                continue
            extra = part.get("extra") or {}
            target, wildcard = canonical_map_id(extra.get("MapID"))
            transitions.append(
                {
                    "id": f"local-connect-collision:{map_id}:{part.get('name')}:{len(transitions)}",
                    "from_map_id": map_id,
                    "to_map_id": target,
                    "raw_target_map_id": extra.get("MapID"),
                    "target_has_wildcard_byte": wildcard,
                    "kind": "connect_collision",
                    "collision_name": extra.get("CollisionName"),
                    "part_name": part.get("name"),
                    "model_name": part.get("model_name"),
                    "position": part.get("position"),
                    "source_file": source_relative(path, input_root),
                    "verification_state": "local_msbe_verified",
                }
            )
        for region in regions:
            if region.get("type") != "Connection":
                continue
            extra = region.get("extra") or {}
            target, wildcard = canonical_map_id(extra.get("TargetMapID"))
            transitions.append(
                {
                    "id": f"local-connection-region:{map_id}:{region.get('name')}:{len(transitions)}",
                    "from_map_id": map_id,
                    "to_map_id": target,
                    "raw_target_map_id": extra.get("TargetMapID"),
                    "target_has_wildcard_byte": wildcard,
                    "kind": "connection_region",
                    "region_name": region.get("name"),
                    "shape": region.get("shape"),
                    "position": region.get("position"),
                    "source_file": source_relative(path, input_root),
                    "verification_state": "local_msbe_verified",
                }
            )

        maps.append(
            {
                "id": f"local_map_{map_id}",
                "map_id": map_id,
                "source_entry": payload.get("source_entry"),
                "source_file": source_relative(path, input_root),
                "source_sha256": source_hash_by_path.get(path.name),
                "counts": {
                    "models": int(payload.get("models", 0)),
                    "parts": len(parts),
                    "regions": len(regions),
                    "events": len(events),
                    "routes": int(payload.get("routes", 0)),
                },
                "part_types": dict(sorted(part_counts.items())),
                "region_types": dict(sorted(region_counts.items())),
                "event_types": dict(sorted(event_counts.items())),
                "xyz_bounds": vector_bounds(parts + regions),
                "coordinate_system": "Elden Ring MSBE game-native XYZ",
                "original_game_coordinates": True,
                "local_game_verified": True,
                "verification_state": "local_msbe_verified",
            }
        )

    matched_targets = sum(1 for edge in transitions if edge["to_map_id"] in map_ids)
    output = {
        "schema": "elden-ring-local-msbe-map-index@1",
        "source": {
            "snapshot_id": "elden-ring-local-snapshot-20260818",
            "input_root": str(input_root),
            "batch_manifest": str(manifest_path),
            "parser": {
                "name": "Andre.SoulsFormats / Smithbox",
                "commit": "f076142392679604ff0428a8ae3f48b32b8f6673",
                "assembly_sha256": "860C3ABA7E1E8406A2027AA7929C48ED8DAB437C9F3DDA69F37B96CA45C376F1",
            },
        },
        "status": {
            "source_files": len(maps),
            "map_nodes": len(maps),
            "transition_edges": len(transitions),
            "transition_targets_in_index": matched_targets,
            "transition_targets_unmatched": len(transitions) - matched_targets,
            "total_models": total_models,
            "total_parts": total_parts,
            "total_regions": total_regions,
            "total_events": total_events,
            "total_routes": total_routes,
            "all_msbe_files_parsed": manifest["failure_count"] == 0 and len(maps) == manifest["success_count"],
        },
        "aggregate_part_types": dict(sorted(part_totals.items())),
        "aggregate_region_types": dict(sorted(region_totals.items())),
        "aggregate_event_types": dict(sorted(event_totals.items())),
        "maps": maps,
        "transitions": transitions,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
