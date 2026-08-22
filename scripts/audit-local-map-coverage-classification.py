#!/usr/bin/env python3
"""Audit the complete conservative local map inventory."""

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
    assert payload["schema"] == "elden-ring-local-map-coverage-classification@1"
    assert status["map_count"] == len(records) == 1347
    assert status["nva_present_map_count"] == 997
    assert status["nva_missing_map_count"] == 350
    assert status["hierarchical_parent_covered_map_count"] == 318
    assert status["non_navigation_content_layer_count"] == 32
    assert status["native_topology_requirement_unresolved_map_count"] == 0
    assert status["classification_counts"] == {
        "native_nva_navmesh_backed": 846,
        "native_nva_present_without_navmesh": 151,
        "nva_missing_msbe_event_or_region_signal": 70,
        "nva_missing_msbe_static_signal_only": 269,
        "nva_missing_no_msbe_playability_signal": 11,
    }
    assert status["all_playability_unresolved"] is True
    assert status["all_floor_semantics_unresolved"] is True
    assert status["routeable_records"] == 0
    assert status["all_records_routeable_false"] is True
    inherited = [
        record for record in records
        if record["navigation_topology_coverage"] == "covered_by_native_child_tiles"
    ]
    assert len(inherited) == 318
    assert all(
        row["native_child_tile_coverage"]["allInventoryChildrenNative"] is True
        and row["native_child_tile_coverage"]["inventoryChildMapIds"]
        and not row["native_child_tile_coverage"]["missingNativeChildMapIds"]
        for row in inherited
    )
    content_layers = [
        record for record in records
        if record["navigation_topology_coverage"]
        == "not_an_independent_navigation_carrier"
    ]
    assert len(content_layers) == 32
    assert all(
        row["non_navigation_content_evidence"]["onlyNonNavigationContentRecords"]
        and not row["non_navigation_content_evidence"]["eventTypeCounts"]
        and row["non_navigation_content_evidence"]["routeCount"] == 0
        for row in content_layers
    )
    assert len({record["map_id"] for record in records}) == len(records)
    assert all(record["routeable"] is False for record in records)
    print("LOCAL MAP COVERAGE CLASSIFICATION AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
