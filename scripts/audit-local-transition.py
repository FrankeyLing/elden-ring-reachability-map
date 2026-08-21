#!/usr/bin/env python3
"""Read-only invariant audit for the local transition evidence artifact."""

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
    endpoint_pairs = payload.get("endpoint_pairs", [])
    scripted_warps = payload.get("scripted_warp_bindings", [])
    scripted_map_warps = payload.get("scripted_map_warp_bindings", [])
    candidates = payload.get("interaction_candidates", [])

    assert payload["schema"] == "elden-ring-local-transition-audit@1"
    assert status["source_map_files"] == status["map_nodes"] == 1347
    assert status["exact_endpoint_pairs"] == len(endpoint_pairs) == 149
    assert status["exact_scripted_warp_bindings"] == len(scripted_warps) == 3
    assert status["exact_scripted_map_warp_bindings"] == len(scripted_map_warps) == 12
    assert status["exact_scripted_map_landing_bindings"] == 12
    assert status["objact_rows"] == len(candidates) == 825
    assert status["objact_exact_sibling_entity_identity_matches"] == 2
    assert status["objact_exact_emevd_objact_param_unique_state_target_matches"] == 2
    assert status["objact_exact_common_event_objact_state_target_matches"] == 1
    assert status["objact_exact_cross_map_entity_part_matches"] == 2
    assert status["objact_exact_global_entity_param_cross_map_matches"] == 2
    assert status["objact_verified_entity_id_minus_2000_support_count"] == 543
    assert status["objact_exact_verified_entity_id_minus_2000_matches"] == 10
    assert status["objact_transition_candidate_target_part_unresolved"] == 33
    assert status["objact_non_transition_target_part_unresolved"] == 21
    assert status["objact_mechanism_pair_count"] == 84
    assert status["objact_mechanism_pair_row_count"] == 168
    assert status["objact_unresolved_transition_global_identity_candidate_records"] == 2
    assert status["objact_unresolved_transition_global_identity_status_counts"] == {
        "cross_map_records_without_unique_named_target_part": 2,
        "invalid_objact_param_or_entity_identity": 17,
        "no_cross_map_same_objact_param_entity": 14,
    }
    assert status["objact_explicit_map_id_records"] == 34
    assert status["objact_explicit_map_id_local_map_records"] == 34
    assert status["objact_explicit_map_id_unresolved_records"] == 0
    assert status["direct_routeable_records"] == 0
    assert status["formal_transition_promotion_ready"] is False
    assert status["all_records_routeable_false"] is True
    assert all(row.get("endpoint_binding_status") == "exact" and row.get("routeable") is False for row in endpoint_pairs)
    assert all(row.get("direction_status", "").startswith("explicit_in_") for row in endpoint_pairs + scripted_warps + scripted_map_warps)
    assert all(row.get("routeable") is False for row in scripted_warps + scripted_map_warps + candidates)
    assert all(
        row.get("target_part_endpoint", {}).get("node_id") in row.get("exact_target_part_node_ids", [])
        for row in candidates
        if row.get("exact_target_part_match")
    )
    global_matches = [
        row for row in candidates
        if row.get("target_binding_basis") == "exact_global_objact_entity_param_to_part_name"
    ]
    assert len(global_matches) == 2
    assert all(
        row.get("cross_map_objact_binding", {}).get("map_id") == row.get("target_part_map_id")
        and row.get("target_part_endpoint", {}).get("map_id") == row.get("target_part_map_id")
        and row.get("cross_map_objact_binding", {}).get("obj_act_id") == row.get("obj_act_id")
        and row.get("cross_map_objact_binding", {}).get("obj_act_entity_id") == row.get("obj_act_entity_id")
        for row in global_matches
    )
    assert all(row.get("to", {}).get("landing_binding_status") == "exact" for row in scripted_map_warps)
    assert all(row.get("emevd_binding", {}).get("routeable") is False for row in candidates)
    paired = [row for row in candidates if row.get("mechanism_pair_id")]
    assert len(paired) == 168
    assert all(
        row.get("mechanism_pair_binding_basis") == "exact_same_map_source_label_opposite_side_pair"
        and row.get("mechanism_pair_routeable") is False
        and row.get("mechanism_side") in {"lower", "upper"}
        and len(row.get("mechanism_peer_candidate_ids", [])) == 1
        for row in paired
    )
    unresolved_transition_rows = [
        row for row in candidates
        if not row.get("exact_target_part_match")
        and row.get("transition_candidate_kind") != "loot_or_non_transition_interaction"
    ]
    assert len(unresolved_transition_rows) == 33
    assert all(
        row.get("global_objact_identity_audit", {}).get("status")
        in {
            "cross_map_records_without_unique_named_target_part",
            "invalid_objact_param_or_entity_identity",
            "no_cross_map_same_objact_param_entity",
        }
        and row.get("global_objact_identity_audit", {}).get("routeable") is False
        for row in unresolved_transition_rows
    )
    assert sum(
        row.get("target_binding_basis") == "exact_emevd_objact_param_unique_state_target"
        and row.get("emevd_state_target_binding", {}).get("status")
        == "exact_unique_objact_param_state_target"
        for row in candidates
    ) == 2
    common_matches = [
        row for row in candidates
        if row.get("target_binding_basis") == "exact_emevd_common_event_objact_state_target"
    ]
    assert len(common_matches) == 1
    assert common_matches[0].get("emevd_common_event_objact_binding", {}).get("binding_status") == "exact_common_event_objact_entity_param_state_target"
    assert common_matches[0].get("emevd_state_target_binding", {}).get("status") == "exact_common_event_objact_state_target"
    assert common_matches[0].get("routeable") is False
    print("LOCAL TRANSITION AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
