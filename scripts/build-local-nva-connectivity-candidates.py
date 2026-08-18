#!/usr/bin/env python3
"""Compile exact native NVA Connector candidates without promoting routes.

An NVA Connector is stronger than a semantic relationship: its two native
Navmesh NameIDs and face/edge boundary records are in the game snapshot.  It
is still not a player Transition.  This compiler therefore emits an isolated
candidate layer and deliberately keeps every node, connector, and component
non-routeable.
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


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def compact_navmesh(node: dict[str, Any], map_id: str) -> dict[str, Any]:
    return {
        "id": f"native_navmesh:{map_id}:{node['navmesh_index']}",
        "map_id": map_id,
        "navmesh_index": node["navmesh_index"],
        "name_id": node["name_id"],
        "model_id": node["model_id"],
        "face_data_index": node["face_data_index"],
        "face_count": node["face_count"],
        "position": node["position"],
        "rotation": node["rotation"],
        "scale": node["scale"],
        "gate_node_index": node["gate_node_index"],
        "gate_node_count": node["gate_node_count"],
        "connected_navmeshes": node["connected_navmeshes"],
        "connected_navmeshes_count": node["connected_navmeshes_count"],
        "connected_navmeshes_inline": node["connected_navmeshes_inline"],
        "routeable": False,
        "verification_state": "local_nva_navmesh_instance_exact",
    }


def compile_map(record: dict[str, Any]) -> dict[str, Any]:
    map_id = record["map_id"]
    nva = record["nva"]
    sections = nva["sections"]
    raw_navmeshes = sections.get("0", {}).get("navmeshes", [])
    raw_connectors = sections.get("4", {}).get("connectors", [])
    raw_gates = sections.get("8", {}).get("gate_nodes", [])
    by_name_id: dict[int, list[int]] = {}
    for node in raw_navmeshes:
        by_name_id.setdefault(node["name_id"], []).append(node["navmesh_index"])

    pair_to_connector_indices: dict[tuple[int, int], list[int]] = {}
    for connector in raw_connectors:
        pair_to_connector_indices.setdefault(
            (connector["main_name_id"], connector["target_name_id"]), []
        ).append(connector["connector_index"])

    union_find = UnionFind(len(raw_navmeshes))
    connectors: list[dict[str, Any]] = []
    exact_count = ambiguous_count = unresolved_count = 0
    for connector in raw_connectors:
        source_indices = by_name_id.get(connector["main_name_id"], [])
        target_indices = by_name_id.get(connector["target_name_id"], [])
        status = "exact_native_name_id_to_navmesh_pair"
        if len(source_indices) != 1 or len(target_indices) != 1:
            if source_indices and target_indices:
                status = "ambiguous_native_name_id_to_navmesh_pair"
                ambiguous_count += 1
            else:
                status = "unresolved_native_name_id_to_navmesh_pair"
                unresolved_count += 1
        else:
            exact_count += 1
            union_find.union(source_indices[0], target_indices[0])
        reverse_indices = pair_to_connector_indices.get(
            (connector["target_name_id"], connector["main_name_id"]), []
        )
        connectors.append(
            {
                "id": f"native_connector:{map_id}:{connector['connector_index']}",
                "map_id": map_id,
                "connector_index": connector["connector_index"],
                "from_name_id": connector["main_name_id"],
                "to_name_id": connector["target_name_id"],
                "from_navmesh_indices": source_indices,
                "to_navmesh_indices": target_indices,
                "from": (
                    f"native_navmesh:{map_id}:{source_indices[0]}" if len(source_indices) == 1 else None
                ),
                "to": (
                    f"native_navmesh:{map_id}:{target_indices[0]}" if len(target_indices) == 1 else None
                ),
                "navmesh_connection_count": connector["navmesh_connection_count"],
                "navmesh_connection_index": connector["navmesh_connection_index"],
                "graph_connection_count": connector["graph_connection_count"],
                "graph_connection_index": connector["graph_connection_index"],
                "reverse_native_connector_indices": reverse_indices,
                "direction_status": (
                    "native_reverse_connector_present" if reverse_indices else "native_reverse_connector_absent"
                ),
                "binding_status": status,
                "routeable": False,
                "verification_state": "local_nva_connector_boundary_exact",
            }
        )

    component_members: dict[int, list[int]] = {}
    for index in range(len(raw_navmeshes)):
        component_members.setdefault(union_find.find(index), []).append(index)
    components = []
    for component_index, members in enumerate(sorted(component_members.values(), key=lambda values: values[0])):
        components.append(
            {
                "id": f"native_navmesh_component:{map_id}:{component_index}",
                "map_id": map_id,
                "navmesh_indices": members,
                "navmesh_node_ids": [f"native_navmesh:{map_id}:{index}" for index in members],
                "basis": "undirected_native_nva_connector_candidate",
                "player_walkability_validated": False,
                "routeable": False,
                "verification_state": "local_nva_component_candidate",
            }
        )

    gates = [
        {
            "id": f"native_gate_node:{map_id}:{gate['gate_node_index']}",
            "map_id": map_id,
            "gate_node_index": gate["gate_node_index"],
            "position": gate["position"],
            "connected_navmesh_index": gate["connected_navmesh_index"],
            "node_sub_id": gate["node_sub_id"],
            "neighbour_gate_node_cost_count": len(gate["neighbour_gate_node_costs"]),
            "routeable": False,
            "verification_state": "local_nva_gate_node_exact",
        }
        for gate in raw_gates
    ]
    return {
        "map_id": map_id,
        "source_file": record["source_file"],
        "source_sha256": record["source_sha256"],
        "navmesh_nodes": [compact_navmesh(node, map_id) for node in raw_navmeshes],
        "connectors": connectors,
        "gate_nodes": gates,
        "components": components,
        "status": {
            "navmesh_node_count": len(raw_navmeshes),
            "connector_count": len(connectors),
            "connector_exact_binding_count": exact_count,
            "connector_ambiguous_binding_count": ambiguous_count,
            "connector_unresolved_binding_count": unresolved_count,
            "reverse_connector_present_count": sum(bool(row["reverse_native_connector_indices"]) for row in connectors),
            "gate_node_count": len(gates),
            "native_component_candidate_count": len(components),
            "routeable_records": 0,
            "player_walkability_validated": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nva-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    nva_path = args.nva_index.resolve()
    source = json.loads(nva_path.read_text(encoding="utf-8"))
    maps = [compile_map(record) for record in source.get("records", []) if record.get("map_id")]
    output = {
        "schema": "elden-ring-local-nva-connectivity-candidates@1",
        "source": {
            "nva_index": str(nva_path),
            "nva_index_sha256": sha256(nva_path),
            "snapshot_id": "elden-ring-local-snapshot-20260818",
        },
        "model": {
            "purpose": "exact native NVA Navmesh/Connector candidate layer",
            "native_connector_is_not_player_transition": True,
            "component_basis_is_undirected_candidate_only": True,
            "player_walkability_validated": False,
            "routeable": False,
        },
        "status": {
            "map_count": len(maps),
            "navmesh_node_count": sum(row["status"]["navmesh_node_count"] for row in maps),
            "connector_count": sum(row["status"]["connector_count"] for row in maps),
            "connector_exact_binding_count": sum(row["status"]["connector_exact_binding_count"] for row in maps),
            "connector_ambiguous_binding_count": sum(row["status"]["connector_ambiguous_binding_count"] for row in maps),
            "connector_unresolved_binding_count": sum(row["status"]["connector_unresolved_binding_count"] for row in maps),
            "reverse_connector_present_count": sum(row["status"]["reverse_connector_present_count"] for row in maps),
            "gate_node_count": sum(row["status"]["gate_node_count"] for row in maps),
            "native_component_candidate_count": sum(row["status"]["native_component_candidate_count"] for row in maps),
            "routeable_records": 0,
            "player_walkability_validated": False,
            "all_records_routeable_false": all(
                row["status"]["routeable_records"] == 0 for row in maps
            ),
        },
        "maps": maps,
        "note": "Native NVA boundary and component candidates are exact snapshot evidence, not proof of a player route, direction, state guard, or collision-safe movement.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
