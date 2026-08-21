#!/usr/bin/env python3
"""Audit native NVMHKT/BND4 provenance and NVA ModelID bindings."""

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

    assert payload["schema"] == "elden-ring-local-nvmhktbnd-index@1"
    assert status["nva_map_count"] == status["parsed_bnd4_record_count"] == len(records) == 997
    assert status["parse_error_count"] == len(errors) == 0
    assert status["hkx_entry_count"] == status["hkx_tag0_count"] == 10880
    assert status["nva_model_id_exact_unique_count"] == 2974
    assert status["nva_model_id_ambiguous_count"] == 0
    assert status["nva_model_id_missing_count"] == 1739
    assert status["routeable_records"] == 0
    assert status["geometry_deserialized"] is False
    assert status["player_walkability_validated"] is False
    assert status["all_records_routeable_false"] is True
    assert payload["model"]["geometry_deserialized"] is False
    assert payload["model"]["player_walkability_validated"] is False
    assert payload["model"]["routeable"] is False

    total_entries = total_tag0 = total_bindings = total_exact = total_missing = 0
    for record in records:
        files = record["files"]
        bindings = record["model_bindings"]
        assert record["status"]["hkx_entry_count"] == len(files)
        assert record["status"]["hkx_tag0_count"] == sum(file.get("inner_tag") == "TAG0" for file in files)
        assert record["status"]["nva_model_id_count"] == len(bindings)
        assert record["status"]["routeable_records"] == 0
        assert record["status"]["geometry_deserialized"] is False
        assert len({file["entry_index"] for file in files}) == len(files)
        assert all(file.get("inner_tag") == "TAG0" for file in files)
        for binding in bindings:
            assert binding["routeable"] is False
            assert binding["binding_status"] in {
                "exact_unique_hkx_filename_model_id",
                "hkx_filename_model_id_missing",
            }
            if binding["binding_status"] == "exact_unique_hkx_filename_model_id":
                assert len(binding["matching_navmesh_hkx_entry_indices"]) == 1
            else:
                assert not binding["matching_navmesh_hkx_entry_indices"]
        total_entries += len(files)
        total_tag0 += sum(file.get("inner_tag") == "TAG0" for file in files)
        total_bindings += len(bindings)
        total_exact += sum(binding["binding_status"] == "exact_unique_hkx_filename_model_id" for binding in bindings)
        total_missing += sum(binding["binding_status"] == "hkx_filename_model_id_missing" for binding in bindings)

    assert total_entries == status["hkx_entry_count"]
    assert total_tag0 == status["hkx_tag0_count"]
    assert total_bindings == status["nva_model_id_count"]
    assert total_exact == status["nva_model_id_exact_unique_count"]
    assert total_missing == status["nva_model_id_missing_count"]
    print("LOCAL NVMHKT BND4 INDEX AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
