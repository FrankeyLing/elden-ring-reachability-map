#!/usr/bin/env python3
"""Audit the native NVA -> NVMHKT -> HKX2 evidence-chain artifact."""

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
    assert payload["schema"] == "elden-ring-local-native-topology-evidence-chain@1"
    assert status["map_count"] == len(maps) == 997
    assert status["parse_error_count"] == len(payload.get("errors", [])) == 0
    assert status["navmesh_node_count"] == 9480
    assert status["connector_count"] == 5884
    assert status["exact_nva_to_hkx_binding_node_count"] == 5956
    assert status["hkx2_geometry_present_node_count"] == 5956
    assert status["hkx2_geometry_missing_node_count"] == 3524
    assert status["connectors_with_both_endpoint_geometry_count"] == 5884
    assert status["hkx2_geometry_entry_count"] == 3390
    assert status["hkx2_deserialized_geometry_entry_count"] == 3390
    assert status["vertex_count"] == 16607263
    assert status["face_count"] == 6888218
    assert status["edge_count"] == 29901878
    assert status["routeable_records"] == 0
    assert status["player_walkability_validated"] is False
    assert status["all_nodes_routeable_false"] is True
    assert status["all_connectors_routeable_false"] is True
    assert status["all_records_routeable_false"] is True
    assert payload["model"]["geometry_is_not_player_walkability"] is True
    assert payload["model"]["routeable"] is False

    node_count = connector_count = 0
    for row in maps:
        assert row["status"]["routeable_records"] == 0
        for node in row["navmesh_nodes"]:
            node_count += 1
            assert node["routeable"] is False
            assert node["player_walkability_validated"] is False
            if node["hkx2_geometry_present"]:
                assert node["nvmhktbnd_binding_status"] == "exact_unique_hkx_filename_model_id"
                assert node["native_evidence_status"] == "exact_nva_model_to_hkx2_geometry"
                assert len(node["hkx2_geometry"]) == 1
                assert node["hkx2_geometry"][0]["class_name"] == "hkaiNavMesh"
            else:
                assert node["nvmhktbnd_binding_status"] in {
                    "hkx_filename_model_id_missing",
                    "nva_model_id_not_indexed",
                }
                assert node["native_evidence_status"] == "nva_model_binding_unresolved"
                assert not node["hkx2_geometry"]
        for connector in row["connectors"]:
            connector_count += 1
            assert connector["routeable"] is False
            assert connector["player_walkability_validated"] is False
            assert connector["binding_status"] == "exact_native_name_id_to_navmesh_pair"
            assert connector["endpoint_hkx2_geometry_status"] == "both_native_endpoint_geometry_present"
            assert connector["geometry_is_boundary_evidence_only"] is True
            assert connector["from"] and connector["to"]
    assert node_count == status["navmesh_node_count"]
    assert connector_count == status["connector_count"]
    print("LOCAL NATIVE TOPOLOGY EVIDENCE CHAIN AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
