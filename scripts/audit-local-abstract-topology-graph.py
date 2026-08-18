#!/usr/bin/env python3
"""Audit the merged abstract topology evidence graph."""

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
    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])
    assert payload["schema"] == "elden-ring-local-abstract-topology-graph@1"
    assert status["source_node_count"] == 13584
    assert status["supplemental_transition_endpoint_nodes"] == 9
    assert status["external_declared_map_target_nodes"] == 4
    assert status["external_declared_map_target_online_records"] == 2
    assert status["node_count"] == len(nodes) == 29144
    assert status["native_abstract_node_count"] == 9480
    assert status["native_identity_candidate_node_count"] == 5817
    assert status["native_identity_supplemental_node_count"] == 4709
    assert status["native_layer_index_record_count"] == 1347
    assert status["native_layer_node_count"] == 1347
    assert status["native_layer_partition_relation_count"] == 1347
    assert status["native_layer_membership_relation_count"] == 11034
    assert status["native_layer_distinct_value_count"] == 21
    assert status["native_layer_coverage_map_count"] == 1347
    assert status["native_layer_coverage_maps_with_layer_records"] == 1297
    assert status["native_layer_coverage_maps_without_layer_records"] == 50
    assert status["native_layer_coverage_all_routeable_false"] is True
    assert status["native_layer_all_routeable_false"] is True
    assert status["native_map_declaration_edge_count"] == 1588
    assert status["exact_endpoint_edge_count"] == 149
    assert status["exact_scripted_warp_edge_count"] == 15
    assert status["edge_count"] == len(edges) == 7976
    assert status["native_abstract_connector_edge_count"] == 5884
    assert status["native_abstract_boundary_edges_omitted_count"] == 137358
    assert status["native_identity_relation_count"] == 11646
    assert status["native_identity_layer_relation_count"] == 5817
    assert status["native_identity_relations_all_routeable_false"] is True
    assert status["native_identity_layer_relations_all_routeable_false"] is True
    assert status["semantic_relation_count"] == 16314
    assert status["online_map_key_records"] == 985
    assert status["online_map_key_missing"] == 362
    assert status["online_tile_region_records"] == 765
    assert status["online_tile_region_missing"] == 582
    assert status["native_layer_record_count"] == 1347
    assert status["maps_with_native_layer_evidence"] == 1297
    assert status["native_nva_file_count"] == 997
    assert status["native_nva_parsed_record_count"] == 997
    assert status["native_nva_maps_with_evidence"] == 997
    assert status["native_nva_maps_with_navmesh"] == 846
    assert status["native_nva_total_navmeshes"] == 9480
    assert status["native_nva_total_connectors"] == 5884
    assert status["native_nva_all_routeable_false"] is True
    assert status["native_nva_connectivity_maps_with_evidence"] == 997
    assert status["native_nva_connectivity_exact_connectors"] == 5884
    assert status["native_nva_connectivity_candidate_components"] == 7201
    assert status["native_nva_connectivity_all_routeable_false"] is True
    assert status["native_nva_boundary_pair_maps_with_evidence"] == 997
    assert status["native_nva_boundary_pair_count"] == 137358
    assert status["native_nva_boundary_pair_hkx2_range_validated_count"] == 127534
    assert status["native_nva_boundary_pair_hkx2_range_conflict_count"] == 9824
    assert status["native_nva_boundary_pair_geometry_missing_count"] == 0
    assert status["native_nva_boundary_pair_all_routeable_false"] is True
    assert status["native_nvmhktbnd_maps_with_evidence"] == 997
    assert status["native_nvmhktbnd_parsed_record_count"] == 997
    assert status["native_nvmhktbnd_hkx_entry_count"] == 10880
    assert status["native_nvmhktbnd_all_routeable_false"] is True
    assert status["native_nvmhktbnd_geometry_maps_with_evidence"] == 997
    assert status["native_nvmhktbnd_geometry_navmesh_hkx_entry_count"] == 3390
    assert status["native_nvmhktbnd_geometry_face_count"] == 6888218
    assert status["native_nvmhktbnd_geometry_edge_count"] == 29901878
    assert status["native_nvmhktbnd_geometry_vertex_count"] == 16607263
    assert status["native_nvmhktbnd_geometry_deserialized"] is True
    assert status["native_nvmhktbnd_geometry_all_routeable_false"] is True
    assert status["native_topology_graph_map_count"] == 997
    assert status["native_topology_graph_node_count"] == 9480
    assert status["native_topology_graph_boundary_edge_count"] == 137358
    assert status["native_topology_graph_connector_declaration_edge_count"] == 5884
    assert status["native_topology_graph_connector_declaration_edges_pure_abstract"] is True
    assert status["native_topology_graph_all_routeable_false"] is True
    assert status["native_msbe_model_binding_node_count"] == 9480
    assert status["native_msbe_model_binding_candidate_count"] == 9436
    assert status["native_msbe_model_binding_missing_count"] == 44
    assert status["native_msbe_model_binding_all_routeable_false"] is True
    assert status["native_msbe_model_binding_relation_count"] == 11646
    assert status["native_msbe_connect_collision_binding_count"] == 1125
    assert status["native_msbe_connect_collision_candidate_relation_count"] == 2206
    assert status["native_msbe_connect_collision_ambiguous_count"] == 1103
    assert status["native_msbe_connect_collision_missing_count"] == 22
    assert status["emevd_exact_region_entity_reference_records"] == 824
    assert status["emevd_referenced_region_nodes"] == 598
    assert status["emevd_exact_region_entity_reference_records"] == 824
    assert status["emevd_referenced_region_nodes"] == 598
    assert status["native_map_declaration_target_unresolved"] == 10
    assert status["scripted_warp_edges_with_guard_candidate"] == 15
    assert status["emevd_warp_evidence_edge_count"] == 340
    assert status["emevd_warp_evidence_deduped_existing_count"] == 15
    assert status["warp_evidence_unresolved_count"] == 230
    assert status["supplemental_warp_locator_nodes"] == 11
    assert status["emevd_exact_part_entity_reference_records"] == 2500
    assert status["emevd_referenced_part_nodes"] == 610
    assert status["objact_control_relation_count"] == 771
    assert status["objact_control_relation_unresolved_count"] == 54
    assert status["objact_mechanism_pair_relation_count"] == 84
    assert status["objact_mechanism_pair_relations_all_routeable_false"] is True
    assert status["objact_transition_candidate_target_part_unresolved"] == 33
    assert status["objact_mechanism_pair_count"] == 84
    assert status["objact_mechanism_pair_row_count"] == 168
    assert status["objact_non_transition_target_part_unresolved"] == 21
    assert status["objact_exact_cross_map_entity_part_matches"] == 2
    assert status["objact_exact_global_entity_param_cross_map_matches"] == 2
    assert status["objact_verified_entity_id_minus_2000_support_count"] == 543
    assert status["objact_exact_verified_entity_id_minus_2000_matches"] == 10
    assert status["objact_exact_common_event_objact_state_target_matches"] == 1
    assert status["objact_exact_emevd_objact_param_unique_state_target_matches"] == 2
    assert status["objact_explicit_map_identity_relation_count"] == 34
    assert status["objact_explicit_map_identity_unresolved_count"] == 0
    assert status["objact_param_candidate_id_count"] == 107
    assert status["objact_param_exact_candidate_id_count"] == 105
    assert status["objact_param_missing_candidate_id_count"] == 2
    assert status["objact_param_bound_control_relation_count"] == 637
    assert status["objact_state_evidence_count"] == 695
    assert status["objact_state_condition_evidence_count"] == 317
    assert status["objact_state_action_evidence_count"] == 378
    assert status["objact_state_objact_write_evidence_count"] == 165
    assert status["objact_state_objact_write_exact_param_match_count"] == 130
    assert status["objact_state_unique_emevd_reference_count"] == 652
    assert status["objact_transport_relation_count"] == 18
    assert status["objact_transport_relation_unresolved_count"] == 0
    assert status["routeable_records"] == 0
    assert status["all_edges_routeable_false"] is True
    assert status["all_nodes_routeable_false"] is True
    assert payload["model"]["abstract_topology_is_not_continuous_walkability"] is True
    assert payload["model"]["native_nva_evidence_used"] is True
    assert payload["model"]["havok_nva_navmesh_used_for_continuous_walkability"] is False
    assert payload["model"]["native_topology_graph_joined_by_map_id"] is True
    assert payload["model"]["native_topology_graph_is_abstract_adjacency_only"] is True
    assert payload["model"]["native_msbe_model_identity_bindings_joined"] is True
    assert payload["model"]["native_msbe_model_identity_is_not_player_entrance"] is True
    assert payload["model"]["native_msbe_layer_partition_joined_by_map_id"] is True
    assert payload["model"]["native_msbe_layer_partition_is_not_floor_semantics"] is True
    native_graph = payload["native_topology_graph"]
    assert native_graph["schema"] == "elden-ring-local-native-topology-graph@1"
    assert native_graph["join_key"] == "map_id"
    assert native_graph["routeable"] is False
    assert len(payload.get("warp_evidence_unresolved", [])) == 230
    node_ids = [node.get("id") for node in nodes]
    node_id_set = set(node_ids)
    assert len(node_ids) == len(node_id_set)
    assert all(edge.get("from") in node_id_set and edge.get("to") in node_id_set for edge in edges)
    layer_relations = payload.get("layer_relations", [])
    assert len(layer_relations) == 1347
    assert all(
        relation.get("relation_family") == "native_msbe_layer_partition"
        and relation.get("routeable") is False
        and relation.get("from") in node_id_set
        and relation.get("to") in node_id_set
        for relation in layer_relations
    )
    layer_membership_relations = payload.get("layer_membership_relations", [])
    assert len(layer_membership_relations) == 11034
    assert all(
        relation.get("relation_family") == "native_msbe_layer_membership"
        and relation.get("routeable") is False
        and relation.get("from") in node_id_set
        and relation.get("to") in node_id_set
        and relation.get("entity_node_type") in {"part", "region"}
        for relation in layer_membership_relations
    )
    layer_coverage = payload.get("layer_coverage", [])
    assert len(layer_coverage) == 1347
    assert sum(
        row.get("layer_partition_status") == "exact_raw_layer_partition"
        for row in layer_coverage
    ) == 1297
    assert sum(
        row.get("layer_partition_status") == "source_map_has_no_parts"
        for row in layer_coverage
    ) == 50
    assert all(row.get("routeable") is False for row in layer_coverage)
    warp_edges = [edge for edge in edges if edge.get("edge_family") == "emevd_scripted_warp_evidence"]
    assert len(warp_edges) == 340
    assert all(
        edge.get("destination_resolution_status")
        in {"exact_map_entity_id", "exact_global_entity_id_unique", "exact_map_identity_only"}
        for edge in warp_edges
    )
    assert all(
        edge.get("transport_role")
        in {"player_transport", "character_transport", "asset_transport", "generic_scripted_transport"}
        for edge in warp_edges
    )
    interaction_relations = payload.get("interaction_relations", [])
    assert len(interaction_relations) == 771
    assert len(payload.get("interaction_relation_unresolved", [])) == 54
    assert all(
        relation.get("relation_family") == "objact_control_to_exact_part"
        and relation.get("routeable") is False
        and relation.get("from") in node_id_set
        and relation.get("to") in node_id_set
        for relation in interaction_relations
    )
    assert sum(
        relation.get("objact_param", {}).get("resolution_status") == "exact_local_objact_param_row"
        for relation in interaction_relations
    ) == 637
    mechanism_pair_relations = payload.get("interaction_mechanism_pair_relations", [])
    assert len(mechanism_pair_relations) == 84
    assert all(
        relation.get("relation_family") == "objact_mechanism_pair_identity"
        and relation.get("relation_type") == "same_mechanism_opposite_side_control"
        and relation.get("binding_basis") == "exact_same_map_source_label_opposite_side_pair"
        and relation.get("routeable") is False
        and relation.get("from") in node_id_set
        and relation.get("to") in node_id_set
        for relation in mechanism_pair_relations
    )
    region_reference_relations = [
        relation for relation in payload.get("relations", [])
        if relation.get("relation_type") == "emevd_exact_region_entity_reference"
    ]
    assert len(region_reference_relations) == 824
    assert all(
        relation.get("routeable") is False
        and relation.get("from") in node_id_set
        and relation.get("to") in node_id_set
        and relation.get("argument_value", 0) > 0
        for relation in region_reference_relations
    )
    part_reference_relations = [
        relation for relation in payload.get("relations", [])
        if relation.get("relation_type") == "emevd_exact_part_entity_reference"
    ]
    assert len(part_reference_relations) == 2500
    assert all(
        relation.get("routeable") is False
        and relation.get("from") in node_id_set
        and relation.get("to") in node_id_set
        and relation.get("argument_value", 0) > 0
        for relation in part_reference_relations
    )
    map_identity_relations = payload.get("interaction_map_identity_relations", [])
    assert len(map_identity_relations) == 34
    assert len(payload.get("interaction_map_identity_unresolved", [])) == 0
    assert all(
        relation.get("relation_family") == "objact_explicit_map_identity"
        and relation.get("direction_status") == "map_identity_only_direction_unresolved"
        and relation.get("routeable") is False
        and relation.get("from") in node_id_set
        and relation.get("to") in node_id_set
        for relation in map_identity_relations
    )
    assert all(
        relation.get("state_guard_evidence", {}).get("runtime_condition_truth") == "unevaluated"
        and relation.get("state_guard_evidence", {}).get("current_save_state_bound") is False
        and relation.get("state_guard_evidence", {}).get("routeable") is False
        for relation in interaction_relations
    )
    assert sum(
        relation.get("target_binding_basis") == "exact_emevd_objact_param_unique_state_target"
        and relation.get("emevd_state_target_binding", {}).get("status")
        == "exact_unique_objact_param_state_target"
        for relation in interaction_relations
    ) == 2
    assert sum(
        relation.get("target_binding_basis") == "exact_emevd_common_event_objact_state_target"
        and relation.get("emevd_common_event_objact_binding", {}).get("binding_status")
        == "exact_common_event_objact_entity_param_state_target"
        and relation.get("routeable") is False
        for relation in interaction_relations
    ) == 1
    common_target_relations = [
        relation for relation in payload.get("relations", [])
        if relation.get("relation_type") == "emevd_common_event_objact_target_reference"
    ]
    assert len(common_target_relations) == 1
    assert all(
        relation.get("routeable") is False
        and relation.get("from") in node_id_set
        and relation.get("to") in node_id_set
        for relation in common_target_relations
    )
    interaction_transport_relations = payload.get("interaction_transport_relations", [])
    assert len(interaction_transport_relations) == 18
    assert len(payload.get("interaction_transport_unresolved", [])) == 0
    assert all(
        relation.get("relation_family") == "objact_control_to_scripted_transport"
        and relation.get("routeable") is False
        and relation.get("from") in node_id_set
        and relation.get("to") in node_id_set
        and relation.get("destination_resolution_status")
        in {"exact_map_entity_id", "exact_global_entity_id_unique", "exact_map_identity_only"}
        for relation in interaction_transport_relations
    )
    assert all(
        relation.get("state_guard_evidence", {}).get("runtime_condition_truth") == "unevaluated"
        and relation.get("state_guard_evidence", {}).get("current_save_state_bound") is False
        for relation in interaction_transport_relations
    )
    assert sum(
        relation.get("guard", {}).get("guard_status") == "candidate_expression_linked"
        for relation in interaction_transport_relations
    ) == 15
    assert sum(
        relation.get("guard", {}).get("guard_status") == "not_present_in_guard_trace_index"
        for relation in interaction_transport_relations
    ) == 3
    assert all(edge.get("routeable") is False for edge in edges)
    assert all(node.get("routeable") is False for node in nodes)
    native_identity_nodes = [
        node
        for node in nodes
        if node.get("node_type") == "native_msbe_model_identity_candidate"
    ]
    assert len(native_identity_nodes) == 4709
    assert all(
        node.get("topology_status") == "native_msbe_model_identity_candidate"
        and node.get("routeable") is False
        and node.get("map_studio_layer") is not None
        for node in native_identity_nodes
    )
    native_identity_relations = payload.get("native_identity_relations", [])
    assert len(native_identity_relations) == 11646
    assert all(
        relation.get("relation_family") == "native_nva_to_msbe_collision_model_identity"
        and relation.get("routeable") is False
        and relation.get("from") in node_id_set
        and relation.get("to") in node_id_set
        for relation in native_identity_relations
    )
    native_identity_layer_relations = payload.get("native_identity_layer_relations", [])
    assert len(native_identity_layer_relations) == 5817
    assert all(
        relation.get("relation_family") == "native_msbe_identity_layer_membership"
        and relation.get("routeable") is False
        and relation.get("from") in node_id_set
        and relation.get("to") in node_id_set
        for relation in native_identity_layer_relations
    )
    native_connector_edges = [
        edge for edge in edges if edge.get("edge_family") == "native_nva_connector_declaration"
    ]
    assert len(native_connector_edges) == 5884
    assert all(
        edge.get("edge_layer") == "native_abstract_nva"
        and edge.get("topology_status") == "exact_native_nva_connector_declaration"
        and edge.get("from") in node_id_set
        and edge.get("to") in node_id_set
        and edge.get("routeable") is False
        for edge in native_connector_edges
    )
    state_evidence = payload.get("objact_state_evidence", [])
    assert len(state_evidence) == 695
    assert all(
        evidence.get("routeable") is False
        and evidence.get("truth_evaluated") is False
        and evidence.get("target_part_node_id") in node_id_set
        and evidence.get("evidence_kind") in {"condition", "action"}
        for evidence in state_evidence
    )
    objact_writes = [
        evidence for evidence in state_evidence
        if evidence.get("evidence_class") == "objact_state_write"
    ]
    assert len(objact_writes) == 165
    assert all(
        evidence.get("normalized_state_effect", {}).get("instruction_name")
        in {"Set ObjAct State", "Set ObjAct State (Assign IDx)"}
        for evidence in objact_writes
    )
    assert sum(
        evidence.get("normalized_state_effect", {}).get("objact_param_match_status") == "exact"
        for evidence in objact_writes
    ) == 130
    print("LOCAL ABSTRACT TOPOLOGY GRAPH AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
