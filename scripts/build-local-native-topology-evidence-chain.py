#!/usr/bin/env python3
"""Join native NVA topology evidence to exact NVMHKT/HKX2 geometry evidence.

This is an evidence-chain artifact, not the final player route graph.  NVA
Navmesh nodes and connectors are joined to the exact ``n*.hkx`` entries that
their ModelIDs name, then to the deserialized HKX2 summary for those entries.
The join deliberately preserves ``routeable=false``: geometry presence does
not by itself prove player walkability, direction, floor identity, a gate
condition, or a valid movement route.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


HKX_MODEL_RE = re.compile(r"(?P<model_id>\d{6})\.hkx$", re.IGNORECASE)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def model_id_from_name(name: str | None) -> int | None:
    if not name:
        return None
    match = HKX_MODEL_RE.search(name.replace("\\", "/").split("/")[-1])
    return int(match.group("model_id")) if match else None


def geometry_summary(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "entry_index": entry["EntryIndex"],
        "name": entry["Name"],
        "variant": entry.get("Variant"),
        "class_name": entry.get("ClassName"),
        "vertices": entry.get("Vertices", 0),
        "faces": entry.get("Faces", 0),
        "edges": entry.get("Edges", 0),
        "boundary_edges": entry.get("BoundaryEdges", 0),
        "internal_opposite_edges": entry.get("InternalOppositeEdges", 0),
        "user_edges": entry.get("UserEdges", 0),
        "min_face_edges": entry.get("MinFaceEdges", 0),
        "max_face_edges": entry.get("MaxFaceEdges", 0),
        "face_data": entry.get("FaceData", 0),
        "edge_data": entry.get("EdgeData", 0),
        "aabb_min": entry.get("AabbMin"),
        "aabb_max": entry.get("AabbMax"),
        "vertex_min": entry.get("VertexMin"),
        "vertex_max": entry.get("VertexMax"),
        "blocked_edges": entry.get("BlockedEdges", 0),
        "edge_flag_counts": entry.get("EdgeFlagCounts", {}),
    }


def build_map(
    nva_record: dict[str, Any],
    connectivity_record: dict[str, Any],
    bnd_record: dict[str, Any],
    geometry_record: dict[str, Any],
) -> dict[str, Any]:
    map_id = nva_record["map_id"]
    if connectivity_record.get("map_id") != map_id:
        raise ValueError(f"connectivity map mismatch for {map_id}")
    if bnd_record.get("map_id") != map_id:
        raise ValueError(f"BND4 map mismatch for {map_id}")
    if geometry_record.get("MapId") != map_id:
        raise ValueError(f"geometry map mismatch for {map_id}")

    bindings_by_model = {
        int(binding["model_id"]): binding
        for binding in bnd_record.get("model_bindings", [])
    }
    geometry_by_entry = {
        int(entry["EntryIndex"]): entry
        for entry in geometry_record.get("NavmeshEntries", [])
    }
    navmesh_nodes = []
    exact_binding_nodes = 0
    geometry_nodes = 0
    missing_geometry_nodes = 0
    for node in connectivity_record.get("navmesh_nodes", []):
        model_id = int(node["model_id"])
        binding = bindings_by_model.get(model_id)
        entry_indices = []
        geometry_entries = []
        binding_status = "nva_model_id_not_indexed"
        if binding is not None:
            binding_status = binding["binding_status"]
            entry_indices = list(binding.get("matching_navmesh_hkx_entry_indices", []))
            geometry_entries = [
                geometry_by_entry[index]
                for index in entry_indices
                if index in geometry_by_entry
            ]
        if binding_status == "exact_unique_hkx_filename_model_id":
            exact_binding_nodes += 1
        if geometry_entries:
            geometry_nodes += 1
        else:
            missing_geometry_nodes += 1
        navmesh_nodes.append(
            {
                "id": node["id"],
                "map_id": map_id,
                "navmesh_index": node["navmesh_index"],
                "name_id": node["name_id"],
                "model_id": model_id,
                "face_data_index": node["face_data_index"],
                "face_count": node["face_count"],
                "position": node["position"],
                "gate_node_index": node["gate_node_index"],
                "gate_node_count": node["gate_node_count"],
                "nvmhktbnd_binding_status": binding_status,
                "nvmhktbnd_hkx_entry_indices": entry_indices,
                "hkx2_geometry": [geometry_summary(entry) for entry in geometry_entries],
                "hkx2_geometry_present": bool(geometry_entries),
                "native_evidence_status": (
                    "exact_nva_model_to_hkx2_geometry"
                    if binding_status == "exact_unique_hkx_filename_model_id" and geometry_entries
                    else "nva_model_binding_without_hkx2_geometry"
                    if binding_status == "exact_unique_hkx_filename_model_id"
                    else "nva_model_binding_unresolved"
                ),
                "player_walkability_validated": False,
                "routeable": False,
            }
        )

    nodes_by_id = {node["id"]: node for node in navmesh_nodes}
    connectors = []
    both_geometry_connectors = 0
    for connector in connectivity_record.get("connectors", []):
        from_node = nodes_by_id.get(connector.get("from"))
        to_node = nodes_by_id.get(connector.get("to"))
        both_geometry = bool(
            from_node
            and to_node
            and from_node["hkx2_geometry_present"]
            and to_node["hkx2_geometry_present"]
        )
        if both_geometry:
            both_geometry_connectors += 1
        connectors.append(
            {
                "id": connector["id"],
                "map_id": map_id,
                "connector_index": connector["connector_index"],
                "from": connector.get("from"),
                "to": connector.get("to"),
                "from_name_id": connector["from_name_id"],
                "to_name_id": connector["to_name_id"],
                "from_navmesh_indices": connector["from_navmesh_indices"],
                "to_navmesh_indices": connector["to_navmesh_indices"],
                "navmesh_connection_count": connector["navmesh_connection_count"],
                "navmesh_connection_index": connector["navmesh_connection_index"],
                "graph_connection_count": connector["graph_connection_count"],
                "graph_connection_index": connector["graph_connection_index"],
                "reverse_native_connector_indices": connector["reverse_native_connector_indices"],
                "direction_status": connector["direction_status"],
                "binding_status": connector["binding_status"],
                "endpoint_hkx2_geometry_status": (
                    "both_native_endpoint_geometry_present"
                    if both_geometry
                    else "one_or_both_native_endpoint_geometry_missing"
                ),
                "geometry_is_boundary_evidence_only": True,
                "player_walkability_validated": False,
                "routeable": False,
            }
        )

    geometry_status = {
        "bnd4_file_count": geometry_record.get("Bnd4FileCount", 0),
        "navmesh_hkx_entry_count": len(geometry_record.get("NavmeshEntries", [])),
        "deserialized_geometry_entry_count": sum(
            entry.get("ClassName") == "hkaiNavMesh"
            for entry in geometry_record.get("NavmeshEntries", [])
        ),
        "vertices": sum(entry.get("Vertices", 0) for entry in geometry_record.get("NavmeshEntries", [])),
        "faces": sum(entry.get("Faces", 0) for entry in geometry_record.get("NavmeshEntries", [])),
        "edges": sum(entry.get("Edges", 0) for entry in geometry_record.get("NavmeshEntries", [])),
        "boundary_edges": sum(
            entry.get("BoundaryEdges", 0) for entry in geometry_record.get("NavmeshEntries", [])
        ),
    }
    return {
        "map_id": map_id,
        "source": {
            "nva_file": nva_record["source_file"],
            "nva_sha256": nva_record["source_sha256"],
            "nvmhktbnd_file": bnd_record["source_file"],
            "nvmhktbnd_sha256": bnd_record["source_sha256"],
            "geometry_source_file": geometry_record["SourceFile"],
            "geometry_source_size": geometry_record["SourceSize"],
        },
        "navmesh_nodes": navmesh_nodes,
        "connectors": connectors,
        "native_components": connectivity_record.get("components", []),
        "gate_nodes": connectivity_record.get("gate_nodes", []),
        "geometry": geometry_status,
        "status": {
            "navmesh_node_count": len(navmesh_nodes),
            "connector_count": len(connectors),
            "exact_nva_to_hkx_binding_node_count": exact_binding_nodes,
            "hkx2_geometry_present_node_count": geometry_nodes,
            "hkx2_geometry_missing_node_count": missing_geometry_nodes,
            "connectors_with_both_endpoint_geometry_count": both_geometry_connectors,
            "routeable_records": 0,
            "player_walkability_validated": False,
            "routeable": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nva-index", type=Path, required=True)
    parser.add_argument("--connectivity", type=Path, required=True)
    parser.add_argument("--nvmhktbnd-index", type=Path, required=True)
    parser.add_argument("--geometry-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    nva = json.loads(args.nva_index.read_text(encoding="utf-8"))
    connectivity = json.loads(args.connectivity.read_text(encoding="utf-8"))
    bnd = json.loads(args.nvmhktbnd_index.read_text(encoding="utf-8"))
    geometry = json.loads(args.geometry_index.read_text(encoding="utf-8"))
    by_connectivity = {row["map_id"]: row for row in connectivity.get("maps", [])}
    by_bnd = {row["map_id"]: row for row in bnd.get("records", [])}
    by_geometry = {row["MapId"]: row for row in geometry.get("records", [])}

    maps = []
    errors = []
    for record in nva.get("records", []):
        map_id = record.get("map_id")
        try:
            maps.append(
                build_map(
                    record,
                    by_connectivity[map_id],
                    by_bnd[map_id],
                    by_geometry[map_id],
                )
            )
        except Exception as exc:
            errors.append({"map_id": map_id, "error": str(exc)})

    output = {
        "schema": "elden-ring-local-native-topology-evidence-chain@1",
        "source": {
            "nva_index": str(args.nva_index.resolve()),
            "nva_index_sha256": sha256(args.nva_index),
            "connectivity_candidates": str(args.connectivity.resolve()),
            "connectivity_candidates_sha256": sha256(args.connectivity),
            "nvmhktbnd_index": str(args.nvmhktbnd_index.resolve()),
            "nvmhktbnd_index_sha256": sha256(args.nvmhktbnd_index),
            "geometry_index": str(args.geometry_index.resolve()),
            "geometry_index_sha256": sha256(args.geometry_index),
            "snapshot_id": "elden-ring-local-snapshot-20260818",
            "read_only_snapshot": True,
        },
        "model": {
            "purpose": "native NVA connector to exact NVMHKT/HKX2 geometry evidence chain",
            "nva_connector_is_not_player_transition": True,
            "geometry_is_not_player_walkability": True,
            "player_walkability_validated": False,
            "routeable": False,
        },
        "status": {
            "map_count": len(maps),
            "parse_error_count": len(errors),
            "navmesh_node_count": sum(row["status"]["navmesh_node_count"] for row in maps),
            "connector_count": sum(row["status"]["connector_count"] for row in maps),
            "exact_nva_to_hkx_binding_node_count": sum(
                row["status"]["exact_nva_to_hkx_binding_node_count"] for row in maps
            ),
            "hkx2_geometry_present_node_count": sum(
                row["status"]["hkx2_geometry_present_node_count"] for row in maps
            ),
            "hkx2_geometry_missing_node_count": sum(
                row["status"]["hkx2_geometry_missing_node_count"] for row in maps
            ),
            "connectors_with_both_endpoint_geometry_count": sum(
                row["status"]["connectors_with_both_endpoint_geometry_count"] for row in maps
            ),
            "hkx2_geometry_entry_count": sum(
                row["geometry"]["navmesh_hkx_entry_count"] for row in maps
            ),
            "hkx2_deserialized_geometry_entry_count": sum(
                row["geometry"]["deserialized_geometry_entry_count"] for row in maps
            ),
            "vertex_count": sum(row["geometry"]["vertices"] for row in maps),
            "face_count": sum(row["geometry"]["faces"] for row in maps),
            "edge_count": sum(row["geometry"]["edges"] for row in maps),
            "boundary_edge_count": sum(row["geometry"]["boundary_edges"] for row in maps),
            "routeable_records": 0,
            "player_walkability_validated": False,
            "all_nodes_routeable_false": all(
                node["routeable"] is False
                for row in maps
                for node in row["navmesh_nodes"]
            ),
            "all_connectors_routeable_false": all(
                connector["routeable"] is False
                for row in maps
                for connector in row["connectors"]
            ),
            "all_records_routeable_false": all(
                row["status"]["routeable_records"] == 0 for row in maps
            ),
        },
        "maps": maps,
        "errors": errors,
        "note": "Every join in this artifact is source-backed, but it remains evidence only. Final RouteNode/Transition promotion still requires exact player-facing endpoint semantics, floor/portal direction, state guards, and route validation.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
