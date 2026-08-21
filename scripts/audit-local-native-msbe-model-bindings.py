#!/usr/bin/env python3
"""Audit native NVA to raw MSBE model-identity bindings."""

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
    assert payload["schema"] == "elden-ring-local-native-msbe-model-bindings@1"
    assert status["map_count"] == len(payload.get("maps", [])) == 997
    assert status["native_navmesh_node_count"] == len(records) == 9480
    assert status["node_with_msbe_candidate_count"] == 9436
    assert status["unique_msbe_part_binding_count"] == 7438
    assert status["role_candidate_binding_count"] == 1998
    assert status["missing_msbe_model_identity_count"] == 44
    assert status["parse_error_count"] == len(payload.get("errors", [])) == 0
    assert status["routeable_records"] == 0
    assert status["player_walkability_validated"] is False
    assert status["all_records_routeable_false"] is True
    assert payload["model"]["model_name_match_is_not_player_entrance"] is True
    assert payload["model"]["model_name_comparison"] == "case_insensitive_exact_identifier"
    assert payload["model"]["collision_part_is_not_player_route"] is True
    statuses = {
        "exact_msbe_collision_model_identity_unique",
        "exact_msbe_collision_model_identity_role_candidates",
        "missing_msbe_collision_model_identity",
    }
    assert all(row["binding_status"] in statuses for row in records)
    assert all(row["routeable"] is False for row in records)
    assert all(
        row["binding_status"] == "missing_msbe_collision_model_identity"
        or len(row.get("msbe_part_candidates", [])) > 0
        for row in records
    )
    print("LOCAL NATIVE MSBE MODEL BINDING AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
