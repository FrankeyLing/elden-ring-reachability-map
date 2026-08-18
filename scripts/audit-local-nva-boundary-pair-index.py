#!/usr/bin/env python3
"""Audit exact NVA Connector face/edge boundary pairs."""

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
    assert payload["schema"] == "elden-ring-local-nva-boundary-pair-index@1"
    assert status["map_count"] == len(payload.get("maps", [])) == 997
    assert status["parse_error_count"] == len(payload.get("errors", [])) == 0
    assert status["connector_count"] == 5884
    assert status["boundary_pair_count"] == 137358
    assert status["range_validated_count"] == 127534
    assert status["range_invalid_count"] == 9824
    assert status["geometry_missing_pair_count"] == 0
    assert status["routeable_records"] == 0
    assert status["player_walkability_validated"] is False
    assert status["all_pairs_routeable_false"] is True
    assert status["all_records_routeable_false"] is True
    assert payload["model"]["native_boundary_pair_is_not_player_transition"] is True
    for row in payload.get("maps", []):
        for pair in row.get("boundary_pairs", []):
            assert pair["routeable"] is False
            assert pair["player_walkability_validated"] is False
            assert pair["native_adjacency_status"] == "exact_nva_connector_face_edge_pair"
            assert pair["from_nva_face_range_valid"] is True
            assert pair["to_nva_face_range_valid"] is True
            assert pair["geometry_index_validation"] in {
                "exact_endpoint_hkx2_face_edge_ranges",
                "nva_connector_index_space_not_equal_to_hkx2_summary_index_space",
            }
            if pair["geometry_index_validation"] == "exact_endpoint_hkx2_face_edge_ranges":
                assert all(
                    pair[key] is True
                    for key in (
                        "from_hkx2_face_range_valid",
                        "from_hkx2_edge_range_valid",
                        "to_hkx2_face_range_valid",
                        "to_hkx2_edge_range_valid",
                    )
                )
            else:
                assert any(
                    pair[key] is False
                    for key in (
                        "from_hkx2_face_range_valid",
                        "from_hkx2_edge_range_valid",
                        "to_hkx2_face_range_valid",
                        "to_hkx2_edge_range_valid",
                    )
                )
    print("LOCAL NVA BOUNDARY PAIR AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
