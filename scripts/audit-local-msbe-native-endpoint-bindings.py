#!/usr/bin/env python3
"""Audit MSBE ConnectCollision to native Navmesh candidate bindings."""

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
    assert payload["schema"] == "elden-ring-local-msbe-native-endpoint-bindings@1"
    assert status["source_map_count"] == len(payload.get("maps", [])) == 1347
    assert status["connect_collision_count"] == len(records) == 1125
    assert status["candidate_relation_count"] == 2206
    assert status["unique_candidate_count"] == 0
    assert status["ambiguous_candidate_count"] == 1103
    assert status["missing_candidate_count"] == 22
    assert status["strict_identity_unresolvable_ambiguous_count"] == 1103
    assert status["strict_identity_unresolvable_missing_count"] == 22
    assert status["parse_error_count"] == len(payload.get("errors", [])) == 0
    assert status["routeable_records"] == 0
    assert status["all_records_routeable_false"] is True
    assert payload["model"]["candidate_set_is_not_instance_choice"] is True
    assert payload["model"]["strict_cross_layer_instance_key_available"] is False
    assert payload["model"]["repeated_model_instances_are_unresolvable_by_identity_only"] is True
    assert payload["model"]["connect_collision_is_not_player_transition"] is True
    assert all(row.get("routeable") is False for row in records)
    assert all("identity_audit" in row for row in records)
    assert all(row["identity_audit"].get("cross_layer_instance_key") is None for row in records)
    assert all(row["identity_audit"].get("routeable") is False for row in records)
    assert all(
        row["binding_status"]
        in {
            "native_navmesh_candidate_missing",
            "native_navmesh_candidate_unique",
            "native_navmesh_candidate_ambiguous_same_model_instances",
        }
        for row in records
    )
    print("LOCAL MSBE NATIVE ENDPOINT BINDING AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
