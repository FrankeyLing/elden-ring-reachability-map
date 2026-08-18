#!/usr/bin/env python3
"""Audit the native NVA boundary-adjacency graph invariants."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    status = payload["status"]
    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])
    connector_edges = payload.get("connector_edges", [])
    cross_layer_relations = payload.get("cross_layer_relations", [])
    assert payload["schema"] == "elden-ring-local-native-topology-graph@1"
    assert status["map_count"] == len(payload.get("maps", [])) == 997
    assert status["node_count"] == len(nodes) == 9480
    assert status["boundary_edge_count"] == len(edges) == 137358
    assert status["connector_declaration_edge_count"] == len(connector_edges) == 5884
    assert status["connector_declaration_unique_directed_node_pair_count"] == len(
        {(edge["from"], edge["to"]) for edge in connector_edges}
    ) == 5884
    assert status["connector_count"] == 5884
    assert status["range_validated_count"] == 127534
    assert status["range_invalid_count"] == 9824
    assert status["geometry_missing_pair_count"] == 0
    assert status["coverage_msbe_map_count"] == 1347
    assert status["coverage_nva_map_count"] == 997
    assert status["coverage_missing_nva_map_count"] == 350
    assert status["msbe_model_binding_node_count"] == 9480
    assert status["msbe_model_binding_candidate_count"] == 9436
    assert status["msbe_model_binding_missing_count"] == 44
    assert status["msbe_model_binding_all_routeable_false"] is True
    assert status["msbe_model_binding_relation_count"] == len(cross_layer_relations) == 11646
    assert status["msbe_connect_collision_binding_count"] == 1125
    assert status["msbe_connect_collision_candidate_relation_count"] == 2206
    assert status["msbe_connect_collision_ambiguous_count"] == 1103
    assert status["msbe_connect_collision_missing_count"] == 22
    assert status["player_walkability_validated"] is False
    assert status["routeable_records"] == 0
    assert status["all_nodes_routeable_false"] is True
    assert status["all_edges_routeable_false"] is True
    assert payload["model"]["native_connector_is_not_player_transition"] is True
    assert payload["model"]["connector_declaration_edges_are_pure_abstract_topology"] is True
    assert payload["model"]["connector_declaration_edges_require_no_hkx2_geometry"] is True
    assert payload["model"]["havok_runtime_or_game_process_required"] is False
    assert payload["model"]["msbe_model_identity_binding_joined"] is True
    assert payload["model"]["msbe_model_identity_is_not_player_entrance"] is True
    assert payload["msbe_model_bindings"]["schema"] == "elden-ring-local-native-msbe-model-bindings@1"
    assert payload["msbe_model_bindings"]["join_key"] == "native_node_id"
    assert payload["msbe_model_bindings"]["routeable"] is False
    assert payload["msbe_native_endpoint_bindings"]["schema"] == "elden-ring-local-msbe-native-endpoint-bindings@1"
    assert payload["msbe_native_endpoint_bindings"]["join_key"] == "msbe_part.node_id"
    assert payload["msbe_native_endpoint_bindings"]["routeable"] is False
    node_ids = {node["id"] for node in nodes}
    assert len(node_ids) == len(nodes)
    assert all(node["node_type"] == "native_navmesh" for node in nodes)
    assert all(edge["from"] in node_ids and edge["to"] in node_ids for edge in edges)
    assert all(edge["routeable"] is False for edge in edges)
    assert all(edge["from"] in node_ids and edge["to"] in node_ids for edge in connector_edges)
    assert all(edge["routeable"] is False for edge in connector_edges)
    assert all(node["routeable"] is False for node in nodes)
    assert all(
        relation["from"] in node_ids
        and relation["routeable"] is False
        and relation["relation_family"] == "native_nva_to_msbe_collision_model_identity"
        for relation in cross_layer_relations
    )
    print("LOCAL NATIVE TOPOLOGY GRAPH AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
