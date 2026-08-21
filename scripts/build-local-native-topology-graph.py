#!/usr/bin/env python3
"""Build the native NVA boundary-adjacency graph as an abstract topology layer.

The graph is deliberately separate from the semantic MSBE/EMEVD graph.  NVA
Connectors describe native navmesh boundary identity; they do not by
themselves prove a player route, a direction of travel, or a current-state
transition.  Every node and edge therefore remains ``routeable: false``.
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


def native_node(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize one native Navmesh instance without reinterpreting its pose."""
    return {
        "id": record["id"],
        "node_type": "native_navmesh",
        "map_id": record["map_id"],
        "navmesh_index": record["navmesh_index"],
        "name_id": record.get("name_id"),
        "model_id": record.get("model_id"),
        "face_data_index": record.get("face_data_index"),
        "face_count": record.get("face_count"),
        "position": record.get("position"),
        "rotation": record.get("rotation"),
        "scale": record.get("scale"),
        "gate_node_index": record.get("gate_node_index"),
        "gate_node_count": record.get("gate_node_count"),
        "connected_navmeshes": record.get("connected_navmeshes", []),
        "connected_navmeshes_count": record.get("connected_navmeshes_count"),
        "coordinate_system": "Elden Ring NVA native navmesh transform fields; not player-world XYZ",
        "original_game_coordinates": False,
        "local_game_verified": True,
        "player_walkability_validated": False,
        "routeable": False,
        "verification_state": "local_nva_navmesh_instance_exact_native_topology_node",
    }


def native_edge(pair: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": pair["id"],
        "from": pair["from"],
        "to": pair["to"],
        "from_map_id": pair["map_id"],
        "to_map_id": pair["map_id"],
        "edge_family": "native_nva_boundary_adjacency",
        "relation_type": "native_navmesh_boundary_face_edge_pair",
        "topology_status": "exact_native_nva_connector_boundary_pair",
        "connector_index": pair.get("connector_index"),
        "pair_index": pair.get("pair_index"),
        "from_name_id": pair.get("from_name_id"),
        "to_name_id": pair.get("to_name_id"),
        "from_face_index": pair.get("from_face_index"),
        "from_edge_index": pair.get("from_edge_index"),
        "to_face_index": pair.get("to_face_index"),
        "to_edge_index": pair.get("to_edge_index"),
        "from_nva_face_range_valid": pair.get("from_nva_face_range_valid"),
        "to_nva_face_range_valid": pair.get("to_nva_face_range_valid"),
        "from_hkx2_face_range_valid": pair.get("from_hkx2_face_range_valid"),
        "from_hkx2_edge_range_valid": pair.get("from_hkx2_edge_range_valid"),
        "to_hkx2_face_range_valid": pair.get("to_hkx2_face_range_valid"),
        "to_hkx2_edge_range_valid": pair.get("to_hkx2_edge_range_valid"),
        "geometry_index_validation": pair.get("geometry_index_validation"),
        "reverse_native_connector_indices": pair.get("reverse_native_connector_indices", []),
        "direction_status": pair.get("direction_status"),
        "player_walkability_validated": False,
        "routeable": False,
        "verification_state": "local_nva_connector_and_hkx2_boundary_evidence",
    }


def connector_edge(connector: dict[str, Any]) -> dict[str, Any]:
    """Normalize the NVA Connector declaration as a pure abstract edge.

    This edge is deliberately independent of HKX2 face/edge expansion.  It
    records the native NVA name-ID endpoint relation; the reverse connector
    declaration is retained as corroboration, not interpreted as player
    travel direction.
    """
    return {
        "id": connector["id"],
        "from": connector["from"],
        "to": connector["to"],
        "from_map_id": connector["map_id"],
        "to_map_id": connector["map_id"],
        "edge_family": "native_nva_connector_declaration",
        "relation_type": "exact_native_navmesh_connector_endpoint_pair",
        "topology_status": "exact_native_nva_connector_declaration",
        "connector_index": connector.get("connector_index"),
        "from_name_id": connector.get("from_name_id"),
        "to_name_id": connector.get("to_name_id"),
        "from_navmesh_indices": connector.get("from_navmesh_indices", []),
        "to_navmesh_indices": connector.get("to_navmesh_indices", []),
        "navmesh_connection_count": connector.get("navmesh_connection_count"),
        "navmesh_connection_index": connector.get("navmesh_connection_index"),
        "graph_connection_count": connector.get("graph_connection_count"),
        "graph_connection_index": connector.get("graph_connection_index"),
        "reverse_native_connector_indices": connector.get("reverse_native_connector_indices", []),
        "direction_status": connector.get("direction_status"),
        "player_walkability_validated": False,
        "routeable": False,
        "verification_state": "local_nva_connector_declaration_exact",
    }


def model_binding_relations(bindings: dict[str, Any] | None) -> list[dict[str, Any]]:
    relations: list[dict[str, Any]] = []
    if not bindings:
        return relations
    for record in bindings.get("records", []):
        for candidate in record.get("msbe_part_candidates", []):
            relations.append(
                {
                    "id": f"native-msbe-model:{record.get('native_node_id')}:{candidate.get('node_id')}",
                    "from": record.get("native_node_id"),
                    "to": candidate.get("node_id"),
                    "from_map_id": record.get("map_id"),
                    "to_map_id": candidate.get("map_id"),
                    "relation_family": "native_nva_to_msbe_collision_model_identity",
                    "relation_type": "exact_native_model_name_identity",
                    "binding_status": record.get("binding_status"),
                    "native_model_id": record.get("model_id"),
                    "native_name_id": record.get("name_id"),
                    "msbe_part_type": candidate.get("part_type"),
                    "msbe_part_name": candidate.get("name"),
                    "msbe_part_entity_id": candidate.get("entity_id"),
                    "coordinate_system": "native node to MSBE part identity; endpoint coordinates remain source-specific",
                    "routeable": False,
                    "verification_state": "local_native_msbe_exact_model_identity_relation",
                }
            )
    return relations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--connectivity", type=Path, required=True)
    parser.add_argument("--boundary-pairs", type=Path, required=True)
    parser.add_argument("--evidence-chain", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--msbe-model-bindings", type=Path, required=False)
    parser.add_argument("--msbe-native-endpoint-bindings", type=Path, required=False)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    connectivity_path = args.connectivity.resolve()
    boundary_path = args.boundary_pairs.resolve()
    chain_path = args.evidence_chain.resolve()
    coverage_path = args.coverage.resolve()
    msbe_model_bindings_path = (
        args.msbe_model_bindings.resolve() if args.msbe_model_bindings else None
    )
    msbe_native_endpoint_bindings_path = (
        args.msbe_native_endpoint_bindings.resolve()
        if args.msbe_native_endpoint_bindings
        else None
    )
    connectivity = json.loads(connectivity_path.read_text(encoding="utf-8"))
    boundaries = json.loads(boundary_path.read_text(encoding="utf-8"))
    chain = json.loads(chain_path.read_text(encoding="utf-8"))
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    msbe_model_bindings = (
        json.loads(msbe_model_bindings_path.read_text(encoding="utf-8"))
        if msbe_model_bindings_path and msbe_model_bindings_path.is_file()
        else None
    )
    msbe_native_endpoint_bindings = (
        json.loads(msbe_native_endpoint_bindings_path.read_text(encoding="utf-8"))
        if msbe_native_endpoint_bindings_path and msbe_native_endpoint_bindings_path.is_file()
        else None
    )

    boundary_by_map = {
        record.get("map_id"): record
        for record in boundaries.get("maps", [])
        if record.get("map_id")
    }
    chain_by_map = {
        record.get("map_id"): record
        for record in chain.get("maps", [])
        if record.get("map_id")
    }
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    connector_edges: list[dict[str, Any]] = []
    cross_layer_relations = model_binding_relations(msbe_model_bindings)
    maps: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    edge_ids: set[str] = set()

    for map_record in connectivity.get("maps", []):
        map_id = map_record.get("map_id")
        if not map_id:
            continue
        map_nodes = [native_node(row) for row in map_record.get("navmesh_nodes", [])]
        for node in map_nodes:
            if node["id"] in node_ids:
                raise ValueError(f"duplicate native node id: {node['id']}")
            node_ids.add(node["id"])
            nodes.append(node)

        boundary_record = boundary_by_map.get(map_id, {})
        map_edges = [native_edge(row) for row in boundary_record.get("boundary_pairs", [])]
        for edge in map_edges:
            if edge["id"] in edge_ids:
                raise ValueError(f"duplicate native edge id: {edge['id']}")
            if edge["from"] not in node_ids or edge["to"] not in node_ids:
                raise ValueError(f"native edge endpoint missing: {edge['id']}")
            edge_ids.add(edge["id"])
            edges.append(edge)

        for connector in map_record.get("connectors", []):
            declaration_edge = connector_edge(connector)
            connector_edges.append(declaration_edge)

        chain_record = chain_by_map.get(map_id, {})
        maps.append(
            {
                "map_id": map_id,
                "source_file": map_record.get("source_file"),
                "source_sha256": map_record.get("source_sha256"),
                "navmesh_node_count": len(map_nodes),
                "boundary_edge_count": len(map_edges),
                "native_component_count": len(map_record.get("components", [])),
                "connector_count": len(map_record.get("connectors", [])),
                "chain_geometry_present_node_count": chain_record.get("status", {}).get(
                    "hkx2_geometry_present_node_count", 0
                ),
                "chain_geometry_missing_node_count": chain_record.get("status", {}).get(
                    "hkx2_geometry_missing_node_count", 0
                ),
                "player_walkability_validated": False,
                "routeable": False,
                "verification_state": "local_nva_boundary_graph_map_exact",
            }
        )

    status = {
        "map_count": len(maps),
        "node_count": len(nodes),
        "boundary_edge_count": len(edges),
        "connector_declaration_edge_count": len(connector_edges),
        "connector_declaration_unique_directed_node_pair_count": len(
            {(edge["from"], edge["to"]) for edge in connector_edges}
        ),
        "unique_directed_node_pair_count": len({(edge["from"], edge["to"]) for edge in edges}),
        "unique_undirected_node_pair_count": len(
            {
                tuple(sorted((edge["from"], edge["to"])))
                for edge in edges
            }
        ),
        "connector_count": boundaries.get("status", {}).get("connector_count", 0),
        "range_validated_count": boundaries.get("status", {}).get("range_validated_count", 0),
        "range_invalid_count": boundaries.get("status", {}).get("range_invalid_count", 0),
        "geometry_missing_pair_count": boundaries.get("status", {}).get("geometry_missing_pair_count", 0),
        "coverage_msbe_map_count": coverage.get("status", {}).get("msbe_map_count", 0),
        "coverage_nva_map_count": coverage.get("status", {}).get("nva_map_count", 0),
        "coverage_missing_nva_map_count": coverage.get("status", {}).get("msbe_maps_missing_nva", 0),
        "msbe_model_binding_node_count": (msbe_model_bindings or {}).get("status", {}).get(
            "native_navmesh_node_count", 0
        ),
        "msbe_model_binding_candidate_count": (msbe_model_bindings or {}).get("status", {}).get(
            "node_with_msbe_candidate_count", 0
        ),
        "msbe_model_binding_missing_count": (msbe_model_bindings or {}).get("status", {}).get(
            "missing_msbe_model_identity_count", 0
        ),
        "msbe_model_binding_all_routeable_false": (msbe_model_bindings or {}).get("status", {}).get(
            "all_records_routeable_false", False
        ),
        "msbe_model_binding_relation_count": len(cross_layer_relations),
        "msbe_connect_collision_binding_count": (msbe_native_endpoint_bindings or {}).get("status", {}).get(
            "connect_collision_count", 0
        ),
        "msbe_connect_collision_candidate_relation_count": (msbe_native_endpoint_bindings or {}).get("status", {}).get(
            "candidate_relation_count", 0
        ),
        "msbe_connect_collision_ambiguous_count": (msbe_native_endpoint_bindings or {}).get("status", {}).get(
            "ambiguous_candidate_count", 0
        ),
        "msbe_connect_collision_missing_count": (msbe_native_endpoint_bindings or {}).get("status", {}).get(
            "missing_candidate_count", 0
        ),
        "player_walkability_validated": False,
        "routeable_records": 0,
        "all_nodes_routeable_false": all(node.get("routeable") is False for node in nodes),
        "all_edges_routeable_false": all(edge.get("routeable") is False for edge in edges),
    }
    output = {
        "schema": "elden-ring-local-native-topology-graph@1",
        "source": {
            "connectivity": str(connectivity_path),
            "connectivity_sha256": sha256(connectivity_path),
            "boundary_pairs": str(boundary_path),
            "boundary_pairs_sha256": sha256(boundary_path),
            "evidence_chain": str(chain_path),
            "evidence_chain_sha256": sha256(chain_path),
            "coverage": str(coverage_path),
            "coverage_sha256": sha256(coverage_path),
            "msbe_model_bindings": str(msbe_model_bindings_path) if msbe_model_bindings_path else None,
            "msbe_model_bindings_sha256": (
                sha256(msbe_model_bindings_path)
                if msbe_model_bindings_path and msbe_model_bindings_path.is_file()
                else None
            ),
            "msbe_native_endpoint_bindings": (
                str(msbe_native_endpoint_bindings_path)
                if msbe_native_endpoint_bindings_path
                else None
            ),
            "msbe_native_endpoint_bindings_sha256": (
                sha256(msbe_native_endpoint_bindings_path)
                if msbe_native_endpoint_bindings_path
                and msbe_native_endpoint_bindings_path.is_file()
                else None
            ),
        },
        "model": {
            "purpose": "abstract native NVA navmesh boundary topology",
            "connector_declaration_edges_are_pure_abstract_topology": True,
            "connector_declaration_edges_require_no_hkx2_geometry": True,
            "native_connector_is_not_player_transition": True,
            "native_boundary_edge_direction_is_not_player_direction": True,
            "hkx2_geometry_is_supporting_evidence_only": True,
            "havok_runtime_or_game_process_required": False,
            "msbe_model_identity_binding_joined": msbe_model_bindings is not None,
            "msbe_model_identity_is_not_player_entrance": True,
            "continuous_player_walkability_evaluated": False,
            "current_world_state_evaluated": False,
            "routeable": False,
        },
        "status": status,
        "maps": maps,
        "nodes": nodes,
        "edges": edges,
        "connector_edges": connector_edges,
        "cross_layer_relations": cross_layer_relations,
        "msbe_model_bindings": {
            "schema": (msbe_model_bindings or {}).get("schema"),
            "source_file": str(msbe_model_bindings_path) if msbe_model_bindings_path else None,
            "status": (msbe_model_bindings or {}).get("status", {}),
            "join_key": "native_node_id",
            "routeable": False,
            "verification_state": (
                "local_native_to_msbe_model_identity_joined"
                if msbe_model_bindings is not None
                else "local_native_to_msbe_model_identity_not_joined"
            ),
        },
        "msbe_native_endpoint_bindings": {
            "schema": (msbe_native_endpoint_bindings or {}).get("schema"),
            "source_file": (
                str(msbe_native_endpoint_bindings_path)
                if msbe_native_endpoint_bindings_path
                else None
            ),
            "status": (msbe_native_endpoint_bindings or {}).get("status", {}),
            "join_key": "msbe_part.node_id",
            "routeable": False,
            "verification_state": (
                "local_msbe_connect_collision_to_nva_candidates_joined"
                if msbe_native_endpoint_bindings is not None
                else "local_msbe_connect_collision_to_nva_candidates_not_joined"
            ),
        },
        "note": "This is an exact native adjacency layer for the abstract topology. It preserves NVA Connector face/edge identity, HKX2 index validation, and exact native-to-MSBE model identity relations, but never promotes native adjacency to a player route without independent entrance, direction, state, and route-segment evidence.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
