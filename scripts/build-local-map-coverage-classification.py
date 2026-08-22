#!/usr/bin/env python3
"""Build a conservative evidence index for every local MSBE map.

This is a coverage/classification artifact, not a playability classifier.  It
keeps maps without NVA in the final inventory and describes exactly which
static MSBE/NVA signals are present.  Hierarchical open-world parent tiles are
also linked mechanically to their level-00 child tiles; this is a topology
carrier relation, not a claim that the parent file is playable or unused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


EVENT_SIGNAL_FIELDS = (
    "regions",
    "events",
    "objact_events",
    "transport_events",
    "connection_regions",
    "play_area_regions",
)

NON_NAVIGATION_PART_TYPES = {"Asset", "MapPiece"}
NON_NAVIGATION_REGION_TYPES = {
    "EnvironmentMapPoint", "EnvironmentMapEffectBox", "Other", "Sound",
    "SoundRegion", "WeatherCreateAssetPoint",
}


def section_count(section_counts: dict[str, Any], key: str) -> int:
    value = section_counts.get(key, 0)
    if isinstance(value, dict):
        value = value.get("count", 0)
    return int(value or 0)


def classify(capabilities: dict[str, Any], nva_record: dict[str, Any] | None) -> tuple[str, str]:
    if nva_record is not None:
        section_counts = nva_record.get("nva", {}).get("section_counts", {})
        navmesh_count = section_count(section_counts, "0")
        if navmesh_count > 0:
            return "native_nva_navmesh_backed", "exact_nva_navmesh_present"
        return "native_nva_present_without_navmesh", "exact_nva_present_navmesh_section_empty"

    if any(int(capabilities.get(field, 0) or 0) > 0 for field in EVENT_SIGNAL_FIELDS):
        return "nva_missing_msbe_event_or_region_signal", "msbe_signal_without_nva"

    static_signal = sum(
        int(capabilities.get(field, 0) or 0)
        for field in ("models", "parts", "collision_parts", "map_piece_parts")
    )
    if static_signal > 0:
        return "nva_missing_msbe_static_signal_only", "msbe_static_signal_without_nva"
    return "nva_missing_no_msbe_playability_signal", "no_nva_or_msbe_playability_signal"


def native_child_tiles(
    map_id: str, all_map_ids: set[str], native_map_ids: set[str]
) -> dict[str, Any] | None:
    """Return exact level-00 coverage for an open-world hierarchy tile.

    Elden Ring's final map-id component uses its low digit as the hierarchy
    level: level 1 covers 2x2 level-00 cells and level 2 covers 4x4 cells.
    The high digit is retained as a content/state variant and does not alter
    that footprint.  Only child cells present in the copied local inventory
    participate; world-boundary cells that do not exist are not invented.
    """
    parts = map_id.split("_")
    if len(parts) != 4 or parts[0] not in {"m60", "m61"}:
        return None
    try:
        hierarchy_level = int(parts[3]) % 10
        tile_x, tile_y = int(parts[1]), int(parts[2])
    except ValueError:
        return None
    if hierarchy_level not in (1, 2):
        return None
    factor = 2 ** hierarchy_level
    expected = {
        f"{parts[0]}_{x:02d}_{y:02d}_00"
        for x in range(tile_x * factor, (tile_x + 1) * factor)
        for y in range(tile_y * factor, (tile_y + 1) * factor)
    }
    inventory_children = sorted(expected & all_map_ids)
    native_children = sorted(set(inventory_children) & native_map_ids)
    missing_children = sorted(set(inventory_children) - native_map_ids)
    return {
        "hierarchyLevel": hierarchy_level,
        "coverageFactor": factor,
        "expectedChildCellCount": len(expected),
        "inventoryChildMapIds": inventory_children,
        "nativeChildMapIds": native_children,
        "missingNativeChildMapIds": missing_children,
        "allInventoryChildrenNative": bool(inventory_children) and not missing_children,
    }


def non_navigation_content_evidence(
    map_id: str, maps_dir: Path | None
) -> dict[str, Any] | None:
    """Prove that one parsed MSBE file contains no navigation-bearing record.

    Asset/map-piece and environmental/audio/weather records may be loaded with
    another map, but they do not define an independent player navigation
    carrier. Unknown record types keep the map unresolved.
    """
    if maps_dir is None:
        return None
    path = maps_dir / f"{map_id}.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    part_types: dict[str, int] = {}
    region_types: dict[str, int] = {}
    for row in payload.get("parts", []):
        key = str(row.get("type") or "<unknown>")
        part_types[key] = part_types.get(key, 0) + 1
    for row in payload.get("regions", []):
        key = str(row.get("type") or "<unknown>")
        region_types[key] = region_types.get(key, 0) + 1
    event_types: dict[str, int] = {}
    for row in payload.get("events", []):
        key = str(row.get("type") or "<unknown>")
        event_types[key] = event_types.get(key, 0) + 1
    routes = payload.get("routes", [])
    route_count = len(routes) if isinstance(routes, list) else int(routes or 0)
    allowed = (
        set(part_types) <= NON_NAVIGATION_PART_TYPES
        and set(region_types) <= NON_NAVIGATION_REGION_TYPES
        and not event_types
        and route_count == 0
    )
    return {
        "sourceFile": str(path.resolve()),
        "sourceSha256": sha256(path),
        "partTypeCounts": dict(sorted(part_types.items())),
        "regionTypeCounts": dict(sorted(region_types.items())),
        "eventTypeCounts": dict(sorted(event_types.items())),
        "routeCount": route_count,
        "onlyNonNavigationContentRecords": allowed,
    }
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--nva", type=Path, required=True)
    parser.add_argument("--maps-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    coverage_path = args.coverage.resolve()
    nva_path = args.nva.resolve()
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    nva = json.loads(nva_path.read_text(encoding="utf-8"))
    nva_by_map = {record.get("map_id"): record for record in nva.get("records", [])}

    coverage_records = sorted(coverage.get("missing_maps", []) + [
        {
            "map_id": record.get("map_id"),
            "source_file": record.get("source_file"),
            "source_entry": record.get("source_entry"),
            "capabilities": {},
            "native_nva_status": "present_in_nva_inventory",
        }
        for record in nva.get("records", [])
        if record.get("map_id") not in {item.get("map_id") for item in coverage.get("missing_maps", [])}
    ], key=lambda row: str(row.get("map_id") or ""))
    all_map_ids = {row.get("map_id") for row in coverage_records if row.get("map_id")}
    native_map_ids = set(nva_by_map)
    maps_dir = args.maps_dir.resolve() if args.maps_dir else None
    records: list[dict[str, Any]] = []
    for coverage_record in coverage_records:
        map_id = coverage_record.get("map_id")
        nva_record = nva_by_map.get(map_id)
        capabilities = dict(coverage_record.get("capabilities") or {})
        if nva_record is not None:
            section_counts = nva_record.get("nva", {}).get("section_counts", {})
            capabilities = {
                **capabilities,
                "nva_navmesh_count": section_count(section_counts, "0"),
                "nva_connector_count": section_count(section_counts, "4"),
                "nva_navmesh_connection_count": section_count(section_counts, "5"),
                "nva_gate_node_count": section_count(section_counts, "8"),
            }
        classification, basis = classify(capabilities, nva_record)
        child_coverage = (
            native_child_tiles(map_id, all_map_ids, native_map_ids)
            if nva_record is None else None
        )
        inherited_native_topology = bool(
            child_coverage and child_coverage["allInventoryChildrenNative"]
        )
        content_evidence = (
            non_navigation_content_evidence(map_id, maps_dir)
            if nva_record is None and not inherited_native_topology else None
        )
        non_navigation_content = bool(
            content_evidence and content_evidence["onlyNonNavigationContentRecords"]
        )
        records.append(
            {
                "map_id": map_id,
                "source_file": coverage_record.get("source_file")
                or f"maps/{map_id}.json",
                "source_entry": coverage_record.get("source_entry"),
                "capabilities": capabilities,
                "native_nva_present": nva_record is not None,
                "native_nva_source_file": nva_record.get("source_file") if nva_record else None,
                "native_nva_source_sha256": nva_record.get("source_sha256") if nva_record else None,
                "evidence_classification": classification,
                "classification_basis": basis,
                "navigation_topology_role": (
                    "native_level00_carrier"
                    if nva_record is not None
                    else "hierarchical_parent_of_native_level00_tiles"
                    if inherited_native_topology
                    else "non_navigation_content_layer"
                    if non_navigation_content
                    else "native_topology_requirement_unresolved"
                ),
                "navigation_topology_coverage": (
                    "native_partition_present"
                    if nva_record is not None
                    else "covered_by_native_child_tiles"
                    if inherited_native_topology
                    else "not_an_independent_navigation_carrier"
                    if non_navigation_content
                    else "unresolved_missing_native_partition"
                ),
                "native_child_tile_coverage": child_coverage,
                "non_navigation_content_evidence": content_evidence,
                "playability_classification": "requires_independent_evidence",
                "floor_semantics": "unresolved",
                "routeable": False,
            }
        )

    classifications: dict[str, int] = {}
    for record in records:
        key = record["evidence_classification"]
        classifications[key] = classifications.get(key, 0) + 1
    status = {
        "map_count": len(records),
        "nva_present_map_count": sum(record["native_nva_present"] for record in records),
        "nva_missing_map_count": sum(not record["native_nva_present"] for record in records),
        "hierarchical_parent_covered_map_count": sum(
            record["navigation_topology_coverage"] == "covered_by_native_child_tiles"
            for record in records
        ),
        "non_navigation_content_layer_count": sum(
            record["navigation_topology_coverage"]
            == "not_an_independent_navigation_carrier"
            for record in records
        ),
        "native_topology_requirement_unresolved_map_count": sum(
            record["navigation_topology_coverage"] == "unresolved_missing_native_partition"
            for record in records
        ),
        "classification_counts": dict(sorted(classifications.items())),
        "all_playability_unresolved": all(
            record["playability_classification"] == "requires_independent_evidence"
            for record in records
        ),
        "all_floor_semantics_unresolved": all(
            record["floor_semantics"] == "unresolved" for record in records
        ),
        "routeable_records": 0,
        "all_records_routeable_false": all(record["routeable"] is False for record in records),
    }
    output = {
        "schema": "elden-ring-local-map-coverage-classification@1",
        "source": {
            "coverage": str(coverage_path),
            "coverage_sha256": sha256(coverage_path),
            "nva": str(nva_path),
            "nva_sha256": sha256(nva_path),
            "maps_dir": str(maps_dir) if maps_dir else None,
        },
        "model": {
            "purpose": "complete local MSBE map inventory with conservative native coverage evidence",
            "not_a_playability_classifier": True,
            "not_a_floor_semantics_classifier": True,
            "missing_nva_is_not_interpreted": True,
            "hierarchical_parent_coverage_is_not_playability": True,
            "routeable": False,
        },
        "status": status,
        "records": records,
        "note": "Every map remains in the inventory. A map without NVA is not marked playable, cutscene, unused, duplicate, or empty; those meanings require independent evidence.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
