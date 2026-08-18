#!/usr/bin/env python3
"""Audit exact native NVA connectivity candidates."""

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
    maps = payload.get("maps", [])

    assert payload["schema"] == "elden-ring-local-nva-connectivity-candidates@1"
    assert status["map_count"] == len(maps) > 0
    assert status["connector_ambiguous_binding_count"] == 0
    assert status["connector_unresolved_binding_count"] == 0
    assert status["connector_exact_binding_count"] == status["connector_count"]
    assert status["reverse_connector_present_count"] == status["connector_count"]
    assert status["routeable_records"] == 0
    assert status["player_walkability_validated"] is False
    assert status["all_records_routeable_false"] is True
    assert payload["model"]["native_connector_is_not_player_transition"] is True
    assert payload["model"]["component_basis_is_undirected_candidate_only"] is True
    assert payload["model"]["player_walkability_validated"] is False
    assert payload["model"]["routeable"] is False

    total_navmesh = total_connectors = total_gates = total_components = 0
    for map_record in maps:
        navmesh_nodes = map_record["navmesh_nodes"]
        connectors = map_record["connectors"]
        gates = map_record["gate_nodes"]
        components = map_record["components"]
        map_id = map_record["map_id"]
        assert map_record["status"]["connector_exact_binding_count"] == len(connectors)
        assert map_record["status"]["connector_ambiguous_binding_count"] == 0
        assert map_record["status"]["connector_unresolved_binding_count"] == 0
        assert map_record["status"]["routeable_records"] == 0
        node_ids = {node["id"] for node in navmesh_nodes}
        assert len(node_ids) == len(navmesh_nodes)
        assert len({node["name_id"] for node in navmesh_nodes}) == len(navmesh_nodes)
        for node in navmesh_nodes:
            assert node["routeable"] is False
            assert node["verification_state"] == "local_nva_navmesh_instance_exact"
        for connector in connectors:
            assert connector["binding_status"] == "exact_native_name_id_to_navmesh_pair"
            assert connector["routeable"] is False
            assert connector["from"] in node_ids
            assert connector["to"] in node_ids
            assert connector["reverse_native_connector_indices"]
            assert connector["direction_status"] == "native_reverse_connector_present"
        for gate in gates:
            assert gate["routeable"] is False
            assert gate["connected_navmesh_index"] < len(navmesh_nodes)
        for component in components:
            assert component["routeable"] is False
            assert component["player_walkability_validated"] is False
            assert set(component["navmesh_node_ids"]).issubset(node_ids)
        total_navmesh += len(navmesh_nodes)
        total_connectors += len(connectors)
        total_gates += len(gates)
        total_components += len(components)

    assert status["navmesh_node_count"] == total_navmesh
    assert status["connector_count"] == total_connectors
    assert status["gate_node_count"] == total_gates
    assert status["native_component_candidate_count"] == total_components
    print("LOCAL NVA CONNECTIVITY CANDIDATE AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
