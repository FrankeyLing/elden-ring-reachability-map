#!/usr/bin/env python3
"""Audit the native NVA/Navmesh evidence index."""

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
    records = payload.get("records", [])
    errors = payload.get("errors", [])

    assert payload["schema"] == "elden-ring-local-nva-navmesh-index@1"
    assert status["nva_file_count"] == status["parsed_record_count"] + status["parse_error_count"]
    assert status["parse_error_count"] == len(errors) == 0
    assert status["parsed_record_count"] == len(records) > 0
    assert status["routeable_records"] == 0
    assert status["all_records_routeable_false"] is True
    assert status["continuous_player_walkability"] is False
    assert status["physical_geometry_validated"] is False
    assert payload["model"]["abstract_relations_are_not_walk_edges"] is True
    assert payload["model"]["continuous_player_walkability_is_not_claimed"] is True
    assert payload["model"]["routeable"] is False

    seen_files = set()
    for record in records:
        source_file = record["source_file"]
        assert source_file not in seen_files
        seen_files.add(source_file)
        assert record["verification_state"] == "local_nva_oodle_decoded_exact"
        assert record["routeable"] is False
        assert record["continuous_player_walkability"] is False
        assert record["physical_geometry_validated"] is False
        nva = record["nva"]
        assert nva["version"] == 8
        assert nva["declared_size"] > 0
        assert nva["section_count"] == len(nva["section_counts"])
        assert nva["summary"]["navmesh_count"] == len(nva["sections"].get("0", {}).get("navmeshes", []))
        assert nva["summary"]["connector_count"] == len(nva["sections"].get("4", {}).get("connectors", []))
        assert nva["summary"]["navmesh_connection_count"] == len(
            nva["sections"].get("5", {}).get("navmesh_connections", [])
        )
        assert nva["summary"]["graph_connection_count"] == len(
            nva["sections"].get("6", {}).get("graph_connections", [])
        )
        assert nva["summary"]["level_connector_count"] == len(
            nva["sections"].get("7", {}).get("level_connectors", [])
        )
        assert nva["summary"]["gate_node_count"] == len(
            nva["sections"].get("8", {}).get("gate_nodes", [])
        )
        for navmesh in nva["sections"].get("0", {}).get("navmeshes", []):
            assert len(navmesh["position"]) == 4
            assert len(navmesh["rotation"]) == 4
            assert len(navmesh["scale"]) == 4
            assert navmesh["navmesh_index"] >= 0
        for connector in nva["sections"].get("4", {}).get("connectors", []):
            assert len(connector["navmesh_connections"]) == connector["navmesh_connection_count"]
            assert len(connector["graph_connections"]) == connector["graph_connection_count"]

    print("LOCAL NVA NAVMESH AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
