#!/usr/bin/env python3
"""Audit the native MSBE layer partition index."""

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
    map_coverage = payload.get("map_layer_coverage", [])
    assert payload["schema"] == "elden-ring-local-msbe-layer-index@1"
    assert status["source_files"] == 1347
    assert status["layer_records"] == len(records)
    assert status["map_coverage_records"] == len(map_coverage) == 1347
    assert status["maps_with_layer_records"] == 1297
    assert status["maps_without_layer_records"] == 50
    assert status["map_layer_coverage_status_counts"] == {
        "exact_raw_layer_partition": 1297,
        "source_map_has_no_parts": 50,
    }
    assert status["distinct_layer_values"] == 21
    assert status["total_parts"] == 676631
    assert status["parts_with_explicit_layer_value"] == status["total_parts"]
    assert status["parts_missing_layer_value"] == 0
    assert status["routeable_records"] == 0
    assert status["all_records_routeable_false"] is True
    assert payload["model"]["continuous_walkability_evaluated"] is False
    assert payload["model"]["havok_required_for_this_layer"] is False
    assert all(row["routeable"] is False for row in records)
    assert all(row["routeable"] is False for row in map_coverage)
    assert all(
        row["layer_partition_status"] in {
            "exact_raw_layer_partition",
            "source_map_has_no_parts",
        }
        for row in map_coverage
    )
    print("LOCAL MSBE LAYER INDEX AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
