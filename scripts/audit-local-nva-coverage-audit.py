#!/usr/bin/env python3
"""Audit native NVA coverage without classifying missing maps as unplayable."""

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
    missing = payload.get("missing_maps", [])
    assert payload["schema"] == "elden-ring-local-nva-coverage-audit@1"
    assert status["msbe_map_count"] == 1347
    assert status["nva_map_count"] == 997
    assert status["msbe_maps_with_nva"] == 997
    assert status["msbe_maps_missing_nva"] == len(missing) == 350
    assert status["nva_maps_without_msbe"] == len(payload.get("extra_nva_map_ids", [])) == 0
    assert abs(status["coverage_fraction"] - (997 / 1347)) < 1e-12
    assert status["archive_hash_nva_path_count"] == 999
    assert status["archive_hash_nva_map_count"] == 999
    assert status["archive_reextract_nva_path_count"] == 997
    assert status["archive_reextract_nva_map_count"] == 997
    assert status["archive_hash_catalog_only_map_count"] == 2
    assert status["archive_reextract_matches_primary_nva_index"] is True
    assert status["routeable_records"] == 0
    assert status["all_records_routeable_false"] is True
    assert payload["model"]["missing_nva_does_not_mean_unplayable"] is True
    assert payload["model"]["playability_classification_is_unresolved"] is True
    assert payload["model"]["archive_inventory_checked"] is True
    archive = payload["source"]["archive_hash_inventory"]
    assert sorted(archive["hash_catalog_only_map_ids"]) == ["m60_42_40_10", "m60_47_42_10"]
    assert archive["reextract_matches_hash_catalog_actual_ids"] is True
    assert archive["reextract_matches_primary_nva_index_ids"] is True
    assert all(
        row["native_nva_status"] == "missing_from_snapshot_nva_inventory"
        and row["playability_classification"] == "unclassified_requires_independent_evidence"
        and row["routeable"] is False
        for row in missing
    )
    print("LOCAL NVA COVERAGE AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
