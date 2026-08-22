#!/usr/bin/env python3
"""Build the independent native abstract-connectivity package.

The package preserves exact native navigation-partition identities and
connector declarations. It intentionally does not copy boundary geometry or
run collision, movement, or continuous walkability simulation.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_NATIVE_INPUT = Path("data/v1/entities/local-native-topology-graph.json")
DEFAULT_MAP_INPUT = Path("data/v1/entities/local-abstract-topology-graph.json")
DEFAULT_COVERAGE_INPUT = Path("data/v1/entities/local-map-coverage-classification.json")
DEFAULT_OUTPUT = Path("data/v1/entities/abstract-native-topology.json")


def compact_native_node(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": node.get("id"),
        "mapId": node.get("map_id"),
        "navmeshIndex": node.get("navmesh_index"),
        "nameId": node.get("name_id"),
        "modelId": node.get("model_id"),
        "faceDataIndex": node.get("face_data_index"),
        "faceCount": node.get("face_count"),
        "gateNodeIndex": node.get("gate_node_index"),
        "gateNodeCount": node.get("gate_node_count"),
        "coordinateSystem": node.get("coordinate_system"),
        "originalGameCoordinates": node.get("original_game_coordinates") is True,
        "localGameVerified": node.get("local_game_verified") is True,
        "routeable": False,
        "playerRouteable": False,
        "abstractNodeStatus": "native_partition_identity",
        "verificationState": node.get("verification_state"),
    }


def compact_connector(edge: dict[str, Any]) -> dict[str, Any]:
    reverse = edge.get("reverse_native_connector_indices") or []
    return {
        "id": edge.get("id"),
        "from": edge.get("from"),
        "to": edge.get("to"),
        "fromMapId": edge.get("from_map_id"),
        "toMapId": edge.get("to_map_id"),
        "connectorIndex": edge.get("connector_index"),
        "fromNameId": edge.get("from_name_id"),
        "toNameId": edge.get("to_name_id"),
        "navmeshConnectionCount": edge.get("navmesh_connection_count"),
        "navmeshConnectionIndex": edge.get("navmesh_connection_index"),
        "directionStatus": edge.get("direction_status"),
        "reverseConnectorIndices": reverse,
        "routeable": False,
        "playerRouteable": False,
        "abstractConnected": True,
        "abstractConnectionStatus": "exact_native_connector_declaration",
        "verificationState": edge.get("verification_state"),
    }


def compact_binding(relation: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": relation.get("id"),
        "from": relation.get("from"),
        "to": relation.get("to"),
        "fromMapId": relation.get("from_map_id"),
        "toMapId": relation.get("to_map_id"),
        "relationType": relation.get("relation_type"),
        "bindingStatus": relation.get("binding_status"),
        "nativeModelId": relation.get("native_model_id"),
        "nativeNameId": relation.get("native_name_id"),
        "msbePartType": relation.get("msbe_part_type"),
        "msbePartName": relation.get("msbe_part_name"),
        "msbePartEntityId": relation.get("msbe_part_entity_id"),
        "routeable": False,
        "playerRouteable": False,
        "abstractBinding": "native_model_to_map_part_identity",
        "verificationState": relation.get("verification_state"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-input", type=Path, default=DEFAULT_NATIVE_INPUT)
    parser.add_argument("--map-input", type=Path, default=DEFAULT_MAP_INPUT)
    parser.add_argument("--coverage-input", type=Path, default=DEFAULT_COVERAGE_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    native = json.loads(args.native_input.read_text(encoding="utf-8"))
    map_graph = json.loads(args.map_input.read_text(encoding="utf-8")) if args.map_input.is_file() else {}
    coverage = json.loads(args.coverage_input.read_text(encoding="utf-8"))
    coverage_by_map = {
        row["map_id"]: row for row in coverage.get("records", []) if row.get("map_id")
    }
    native_nodes = [compact_native_node(row) for row in native.get("nodes", [])]
    connectors = [compact_connector(row) for row in native.get("connector_edges", [])]
    bindings = [compact_binding(row) for row in native.get("cross_layer_relations", [])]
    native_node_map_ids = {row.get("mapId") for row in native_nodes if row.get("mapId")}
    native_file_map_ids = {
        row.get("map_id") for row in native.get("maps", []) if row.get("map_id")
    }
    all_map_ids = {
        row.get("map_id")
        for row in map_graph.get("nodes", [])
        if row.get("node_type") == "map" and row.get("map_id")
    }
    missing_map_ids = sorted(all_map_ids - native_file_map_ids)

    map_summary: dict[str, dict[str, Any]] = {}
    for row in native.get("maps", []):
        map_id = row.get("map_id")
        if not map_id:
            continue
        map_summary[map_id] = {
            "mapId": map_id,
            "nativeFile": row.get("source_file"),
            "nativeNodeCount": row.get("navmesh_node_count", 0),
            "connectorCount": row.get("connector_count", 0),
            "boundaryEvidenceCount": row.get("boundary_edge_count", 0),
            "nativeComponentCount": row.get("native_component_count", 0),
            "verificationState": row.get("verification_state"),
            "playerWalkabilityValidated": False,
            "routeable": False,
            "coverageStatus": "native_partition_present",
        }
    for map_id in missing_map_ids:
        coverage_record = coverage_by_map.get(map_id, {})
        inherited = (
            coverage_record.get("navigation_topology_coverage")
            == "covered_by_native_child_tiles"
        )
        map_summary[map_id] = {
            "mapId": map_id,
            "nativeFile": None,
            "nativeNodeCount": 0,
            "connectorCount": 0,
            "boundaryEvidenceCount": 0,
            "nativeComponentCount": 0,
            "verificationState": (
                "native_child_tile_coverage_verified"
                if inherited else "native_partition_missing"
            ),
            "playerWalkabilityValidated": False,
            "routeable": False,
            "coverageStatus": (
                "hierarchical_parent_covered_by_native_children"
                if inherited else "native_partition_missing"
            ),
            "nativeChildMapIds": (
                (coverage_record.get("native_child_tile_coverage") or {}).get(
                    "nativeChildMapIds", []
                )
            ),
        }

    unresolved_missing_map_ids = [
        map_id for map_id in missing_map_ids
        if map_summary[map_id]["coverageStatus"] == "native_partition_missing"
    ]

    node_ids = {row["id"] for row in native_nodes}
    assert all(row["from"] in node_ids and row["to"] in node_ids for row in connectors)
    assert all(row["routeable"] is False and row["playerRouteable"] is False for row in native_nodes + connectors + bindings)
    payload = {
        "schema": "elden-ring-abstract-native-topology@1",
        "status": "abstract_native_identity_evidence",
        "model": {
            "nodeMeaning": "native navigation partition identity, not a player position",
            "edgeMeaning": "exact native connector declaration between partition identities",
            "bindingMeaning": "native partition to map-part identity relation, not a walkable endpoint",
            "boundaryGeometryCopied": False,
            "continuousPhysics": False,
            "playerWalkabilityValidated": False,
            "allRouteable": False,
        },
        "source": {
            "nativeArtifact": str(args.native_input).replace("\\", "/"),
            "mapArtifact": str(args.map_input).replace("\\", "/"),
            "coverageArtifact": str(args.coverage_input).replace("\\", "/"),
            "nativeSchema": native.get("schema"),
        },
        "mapCoverage": [map_summary[map_id] for map_id in sorted(map_summary)],
        "nodes": native_nodes,
        "edges": connectors,
        "bindings": bindings,
        "stats": {
            "mapCoverageCount": len(map_summary),
            "nativeMapCount": len(native_file_map_ids),
            "nativeNodeMapCount": len(native_node_map_ids),
            "rawMissingNativeMapCount": len(missing_map_ids),
            "hierarchicalParentCoveredMapCount": len(missing_map_ids) - len(unresolved_missing_map_ids),
            "missingNativeMapCount": len(unresolved_missing_map_ids),
            "nativeNodeCount": len(native_nodes),
            "connectorEdgeCount": len(connectors),
            "bindingCount": len(bindings),
            "abstractConnectedEdgeCount": len(connectors),
            "allRouteableFalse": True,
            "bindingStatusCounts": dict(Counter(row["bindingStatus"] for row in bindings)),
        },
        "notes": [
            "This package is an abstract identity/connectivity layer and does not run physical simulation.",
            "The native boundary graph remains source evidence; it is not promoted to player walkability.",
            "Maps without native files remain explicit coverage records and do not invalidate other maps.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
