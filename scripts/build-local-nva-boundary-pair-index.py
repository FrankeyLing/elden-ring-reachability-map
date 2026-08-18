#!/usr/bin/env python3
"""Compile exact NVA Connector face/edge boundary pairs.

The NVA Connector records contain the two endpoint Navmesh identities and the
face/edge pairs that meet across the native boundary.  This compiler joins
those pairs to the HKX2 geometry summary where an exact ModelID binding
exists.  It still does not claim player walkability or promote a Transition.
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


def compile_map(
    nva_record: dict[str, Any],
    connectivity_record: dict[str, Any],
    chain_record: dict[str, Any],
) -> dict[str, Any]:
    map_id = nva_record["map_id"]
    nodes = {node["navmesh_index"]: node for node in chain_record.get("navmesh_nodes", [])}
    connectors = {
        row["connector_index"]: row
        for row in connectivity_record.get("connectors", [])
    }
    pairs = []
    range_validated_count = 0
    range_invalid_count = 0
    geometry_missing_count = 0
    for raw in nva_record["nva"]["sections"].get("4", {}).get("connectors", []):
        connector_index = raw["connector_index"]
        connector = connectors.get(connector_index)
        if connector is None:
            raise ValueError(f"missing connectivity connector {map_id}:{connector_index}")
        from_index = (connector.get("from_navmesh_indices") or [None])[0]
        to_index = (connector.get("to_navmesh_indices") or [None])[0]
        from_node = nodes.get(from_index)
        to_node = nodes.get(to_index)
        for pair_index, boundary in enumerate(raw.get("navmesh_connections", [])):
            from_face = int(boundary["face_index"])
            to_face = int(boundary["opposite_face_index"])
            from_edge = int(boundary["edge_index"])
            to_edge = int(boundary["opposite_edge_index"])
            from_geometry = (from_node or {}).get("hkx2_geometry", [])
            to_geometry = (to_node or {}).get("hkx2_geometry", [])
            from_mesh = from_geometry[0] if len(from_geometry) == 1 else None
            to_mesh = to_geometry[0] if len(to_geometry) == 1 else None
            if from_mesh is None or to_mesh is None:
                geometry_missing_count += 1
            from_nva_face_valid = bool(
                from_node
                and from_face < from_node.get("face_count", 0)
            )
            to_nva_face_valid = bool(
                to_node
                and to_face < to_node.get("face_count", 0)
            )
            from_hkx2_face_valid = bool(from_mesh and 0 <= from_face < from_mesh.get("faces", 0))
            from_hkx2_edge_valid = bool(from_mesh and 0 <= from_edge < from_mesh.get("edges", 0))
            to_hkx2_face_valid = bool(to_mesh and 0 <= to_face < to_mesh.get("faces", 0))
            to_hkx2_edge_valid = bool(to_mesh and 0 <= to_edge < to_mesh.get("edges", 0))
            hkx2_range_valid = (
                from_hkx2_face_valid
                and from_hkx2_edge_valid
                and to_hkx2_face_valid
                and to_hkx2_edge_valid
            )
            if hkx2_range_valid:
                range_validated_count += 1
            else:
                range_invalid_count += 1
            pairs.append(
                {
                    "id": f"native_boundary_pair:{map_id}:{connector_index}:{pair_index}",
                    "map_id": map_id,
                    "connector_index": connector_index,
                    "pair_index": pair_index,
                    "from": connector.get("from"),
                    "to": connector.get("to"),
                    "from_name_id": connector["from_name_id"],
                    "to_name_id": connector["to_name_id"],
                    "from_face_index": from_face,
                    "from_edge_index": from_edge,
                    "to_face_index": to_face,
                    "to_edge_index": to_edge,
                    "from_nva_face_range_valid": from_nva_face_valid,
                    "to_nva_face_range_valid": to_nva_face_valid,
                    "from_hkx2_face_range_valid": from_hkx2_face_valid,
                    "from_hkx2_edge_range_valid": from_hkx2_edge_valid,
                    "to_hkx2_face_range_valid": to_hkx2_face_valid,
                    "to_hkx2_edge_range_valid": to_hkx2_edge_valid,
                    "geometry_index_validation": (
                        "exact_endpoint_hkx2_face_edge_ranges"
                        if hkx2_range_valid
                        else "nva_connector_index_space_not_equal_to_hkx2_summary_index_space"
                        if from_mesh is not None and to_mesh is not None
                        else "endpoint_hkx2_geometry_missing"
                    ),
                    "reverse_native_connector_indices": connector.get("reverse_native_connector_indices", []),
                    "direction_status": connector.get("direction_status"),
                    "native_adjacency_status": "exact_nva_connector_face_edge_pair",
                    "player_walkability_validated": False,
                    "routeable": False,
                }
            )
    return {
        "map_id": map_id,
        "source_file": nva_record["source_file"],
        "source_sha256": nva_record["source_sha256"],
        "boundary_pairs": pairs,
        "status": {
            "connector_count": len(nva_record["nva"]["sections"].get("4", {}).get("connectors", [])),
            "boundary_pair_count": len(pairs),
            "range_validated_count": range_validated_count,
            "range_invalid_count": range_invalid_count,
            "geometry_missing_pair_count": geometry_missing_count,
            "routeable_records": 0,
            "player_walkability_validated": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nva-index", type=Path, required=True)
    parser.add_argument("--connectivity", type=Path, required=True)
    parser.add_argument("--native-chain", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    nva = json.loads(args.nva_index.read_text(encoding="utf-8"))
    connectivity = json.loads(args.connectivity.read_text(encoding="utf-8"))
    chain = json.loads(args.native_chain.read_text(encoding="utf-8"))
    by_connectivity = {row["map_id"]: row for row in connectivity.get("maps", [])}
    by_chain = {row["map_id"]: row for row in chain.get("maps", [])}
    maps = []
    errors = []
    for record in nva.get("records", []):
        map_id = record.get("map_id")
        try:
            maps.append(compile_map(record, by_connectivity[map_id], by_chain[map_id]))
        except Exception as exc:
            errors.append({"map_id": map_id, "error": str(exc)})
    output = {
        "schema": "elden-ring-local-nva-boundary-pair-index@1",
        "source": {
            "nva_index": str(args.nva_index.resolve()),
            "nva_index_sha256": sha256(args.nva_index),
            "connectivity_candidates": str(args.connectivity.resolve()),
            "connectivity_candidates_sha256": sha256(args.connectivity),
            "native_topology_evidence_chain": str(args.native_chain.resolve()),
            "native_topology_evidence_chain_sha256": sha256(args.native_chain),
            "snapshot_id": "elden-ring-local-snapshot-20260818",
            "read_only_snapshot": True,
        },
        "model": {
            "purpose": "exact NVA Connector face/edge boundary pair evidence",
            "native_boundary_pair_is_not_player_transition": True,
            "geometry_range_validation_is_not_walkability": True,
            "player_walkability_validated": False,
            "routeable": False,
        },
        "status": {
            "map_count": len(maps),
            "parse_error_count": len(errors),
            "connector_count": sum(row["status"]["connector_count"] for row in maps),
            "boundary_pair_count": sum(row["status"]["boundary_pair_count"] for row in maps),
            "range_validated_count": sum(row["status"]["range_validated_count"] for row in maps),
            "range_invalid_count": sum(row["status"]["range_invalid_count"] for row in maps),
            "geometry_missing_pair_count": sum(row["status"]["geometry_missing_pair_count"] for row in maps),
            "routeable_records": 0,
            "player_walkability_validated": False,
            "all_pairs_routeable_false": all(
                pair["routeable"] is False
                for row in maps
                for pair in row["boundary_pairs"]
            ),
            "all_records_routeable_false": all(
                row["status"]["routeable_records"] == 0 for row in maps
            ),
        },
        "maps": maps,
        "errors": errors,
        "note": "Boundary face/edge pairs are exact native adjacency evidence and their index ranges are checked against endpoint HKX2 geometry where available. They do not establish player walkability, one-way direction, gate state, floor semantics, or a final Transition.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
