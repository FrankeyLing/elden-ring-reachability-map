#!/usr/bin/env python3
"""Build the merged, non-Havok abstract topology evidence graph.

This graph separates four evidence families:

* native MSBE map declarations (ConnectCollision/Connection),
* exact endpoint pairs recovered from both sides of those declarations, and
* exact scripted warp destinations with conservative Guard-expression refs, and
* the wider map-local EMEVD warp evidence set, including character/asset
  transport and player transport records whose exact map/entity target can be
  resolved without proximity guessing.

It is an abstract topology graph, not a continuous walkability graph.  Every
node and edge remains routeable=false until a separate state-aware route layer
is proven.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def online_map_key(map_id: str) -> str:
    parts = str(map_id).split("_")
    return "_".join(parts[:3]) if len(parts) >= 3 else str(map_id)


def supplemental_endpoint_node(endpoint: dict[str, Any]) -> dict[str, Any]:
    node_id = endpoint.get("node_id")
    return {
        "id": node_id,
        "node_type": "transition_endpoint",
        "candidate_role": "transition_evidence_endpoint",
        "map_id": endpoint.get("map_id"),
        "name": endpoint.get("name"),
        "endpoint_kind": endpoint.get("endpoint_kind"),
        "region_id": endpoint.get("region_id"),
        "entity_id": endpoint.get("entity_id"),
        "position": (
            {
                "x": endpoint["position"][0],
                "y": endpoint["position"][1],
                "z": endpoint["position"][2],
            }
            if isinstance(endpoint.get("position"), list) and len(endpoint["position"]) == 3
            else None
        ),
        "extra": endpoint.get("extra") or {},
        "map_studio_layer": None,
        "layer_status": "not_present_in_candidate_node_index",
        "coordinate_system": endpoint.get("coordinate_system", "Elden Ring MSBE game-native XYZ"),
        "original_game_coordinates": endpoint.get("original_game_coordinates", True),
        "local_game_verified": endpoint.get("local_game_verified", True),
        "routeable": False,
        "verification_state": "local_transition_audit_verified_supplemental_node",
    }


def supplemental_warp_locator_node(locator: dict[str, Any]) -> dict[str, Any]:
    """Preserve an exact MSBE entity used by a warp instruction."""
    return {
        "id": locator.get("node_id"),
        "node_type": "warp_evidence_endpoint",
        "candidate_role": "scripted_warp_entity",
        "map_id": locator.get("map_id"),
        "name": locator.get("name"),
        "entity_kind": locator.get("kind"),
        "entity_type": locator.get("type"),
        "entity_id": locator.get("entity_id"),
        "region_id": locator.get("region_id"),
        "position": locator.get("position"),
        "source_file": locator.get("source_file"),
        "source_index": locator.get("source_index"),
        "map_studio_layer": None,
        "layer_status": "not_present_in_candidate_node_index",
        "coordinate_system": "Elden Ring MSBE game-native XYZ",
        "original_game_coordinates": True,
        "local_game_verified": True,
        "routeable": False,
        "verification_state": "local_emevd_warp_exact_msbe_entity",
    }


def native_layer_node(record: dict[str, Any]) -> dict[str, Any]:
    """Expose the exact MSBE layer partition as a graph node.

    The raw layer value is intentionally preserved.  This node is a native
    partition/evidence node, not a guessed "ground floor", "underground", or
    rooftop label and not a walkability claim.
    """

    return {
        "id": record.get("id"),
        "node_type": "native_map_layer",
        "candidate_role": "native_msbe_layer_partition",
        "map_id": record.get("map_id"),
        "map_studio_layer": record.get("map_studio_layer"),
        "is_default_layer_value": record.get("is_default_layer_value"),
        "part_count": record.get("part_count", 0),
        "part_type_counts": record.get("part_type_counts", {}),
        "coordinate_bounds": record.get("coordinate_bounds", {}),
        "sample_parts": record.get("sample_parts", []),
        "coordinate_system": record.get("coordinate_system", "Elden Ring MSBE game-native XYZ"),
        "original_game_coordinates": record.get("original_game_coordinates", True),
        "local_game_verified": record.get("local_game_verified", True),
        "topology_status": "native_layer_partition",
        "floor_semantics_status": "raw_layer_value_only",
        "continuous_walkability_evaluated": False,
        "routeable": False,
        "verification_state": "local_msbe_native_layer_index_verified",
    }


def native_msbe_identity_candidate_node(candidate: dict[str, Any]) -> dict[str, Any]:
    """Expose an exact NVA-to-MSBE model candidate without selecting a role."""

    return {
        "id": candidate.get("node_id"),
        "node_type": "native_msbe_model_identity_candidate",
        "candidate_role": "native_nva_to_msbe_collision_model_identity",
        "map_id": candidate.get("map_id"),
        "source_part_index": candidate.get("source_part_index"),
        "part_type": candidate.get("part_type"),
        "name": candidate.get("name"),
        "model_name": candidate.get("model_name"),
        "instance_id": candidate.get("instance_id"),
        "entity_id": candidate.get("entity_id"),
        "position": candidate.get("position"),
        "rotation": candidate.get("rotation"),
        "scale": candidate.get("scale"),
        "map_studio_layer": candidate.get("map_studio_layer"),
        "extra": candidate.get("extra") or {},
        "coordinate_system": candidate.get(
            "coordinate_system", "Elden Ring MSBE game-native XYZ"
        ),
        "original_game_coordinates": candidate.get("original_game_coordinates", True),
        "local_game_verified": candidate.get("local_game_verified", True),
        "topology_status": "native_msbe_model_identity_candidate",
        "continuous_walkability_evaluated": False,
        "routeable": False,
        "verification_state": "local_native_msbe_exact_model_identity_candidate",
    }


def compact_guard_ref(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "guard_status": candidate.get("guard_status"),
        "record_id": (candidate.get("guard_expression_refs") or [{}])[0].get("record_id"),
        "expression_ids": [
            path.get("expression_id")
            for ref in candidate.get("guard_expression_refs", [])
            for path in ref.get("paths", [])
        ],
        "path_count": sum(
            len(ref.get("paths", [])) for ref in candidate.get("guard_expression_refs", [])
        ),
        "unresolved_reasons": candidate.get("unresolved_reasons", []),
    }


OBJACT_PARAM_FIELDS = (
    "actionEnableMsgId",
    "actionFailedMsgId",
    "spQualifiedPassEventFlag",
    "playerAnimId",
    "chrAnimId",
    "validDist",
    "spQualifiedId",
    "spQualifiedId2",
    "objDummyId",
    "isEventKickSync",
    "objAnimId",
    "validPlayerAngle",
    "spQualifiedType",
    "spQualifiedType2",
    "validObjAngle",
    "chrSorbType",
    "eventKickTiming",
    "actionButtonParamId",
    "enableTreasureDelaySec",
    "preActionSfxDmypolyId",
    "preActionSfxId",
)


def objact_param_evidence(candidate: dict[str, Any], rows_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    obj_act_id = candidate.get("obj_act_id")
    row = rows_by_id.get(str(obj_act_id))
    if row is None:
        return {
            "param_id": obj_act_id,
            "resolution_status": "objact_param_id_missing" if obj_act_id in (None, -1) else "objact_param_row_not_found",
            "routeable": False,
        }
    values = row.get("values") or {}
    return {
        "param_id": row.get("id"),
        "param_row_name": row.get("name"),
        "resolution_status": "exact_local_objact_param_row",
        "values": {field: values.get(field) for field in OBJACT_PARAM_FIELDS},
        "routeable": False,
    }


def classify_objact_state_evidence(kind: str, instruction_name: str) -> str:
    name = instruction_name.casefold()
    if kind == "condition":
        return "condition_predicate"
    if "set objact state" in name:
        return "objact_state_write"
    if "event flag" in name:
        return "event_flag_write_or_control_flow"
    if "warp" in name or "cutscene" in name:
        return "transport_or_cutscene_action"
    if "goto" in name or "skip" in name or "end if" in name:
        return "control_flow_action"
    return "event_action"


def objact_state_guard_evidence(candidate: dict[str, Any], rows_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    binding = candidate.get("emevd_binding") or {}
    condition_refs = binding.get("event_scoped_condition_references", [])
    action_refs = binding.get("event_scoped_action_references", [])

    def reference_flag_ids(references: list[dict[str, Any]]) -> list[int]:
        return sorted(
            {
                int(flag_id)
                for reference in references
                for flag_id in reference.get("event_flag_ids", [])
                if isinstance(flag_id, int)
            }
        )

    param = objact_param_evidence(candidate, rows_by_id)
    param_values = param.get("values") or {}
    return {
        "msbe_objact_event_flag_id": candidate.get("obj_act_event_flag_id"),
        "objact_param_sp_qualified_pass_event_flag": param_values.get("spQualifiedPassEventFlag"),
        "objact_param_special_condition_ids": [
            value for value in (param_values.get("spQualifiedId"), param_values.get("spQualifiedId2"))
            if value not in (None, 0)
        ],
        "objact_param_special_condition_types": [
            value for value in (param_values.get("spQualifiedType"), param_values.get("spQualifiedType2"))
            if value not in (None, 0)
        ],
        "condition_reference_flag_ids": reference_flag_ids(condition_refs),
        "action_reference_flag_ids": reference_flag_ids(action_refs),
        "event_scoped_event_flag_ids": binding.get("event_scoped_event_flag_ids", []),
        "condition_reference_count": len(condition_refs),
        "action_reference_count": len(action_refs),
        "runtime_condition_truth": "unevaluated",
        "current_save_state_bound": False,
        "routeable": False,
    }


def normalized_state_effect(candidate: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    args = {
        str(argument.get("name")): argument.get("value")
        for argument in reference.get("args", [])
    }
    instruction_name = str(reference.get("instruction_name") or "")
    objact_param_id = args.get("ObjAct Param ID")
    event_flag_id = next(
        (
            args.get(name)
            for name in ("Target Event Flag ID", "Event Flag ID", "ObjAct Event Flag")
            if isinstance(args.get(name), int)
        ),
        None,
    )
    desired_state = next(
        (
            args.get(name)
            for name in ("State", "Desired Flag State", "Desired State")
            if args.get(name) is not None
        ),
        None,
    )
    return {
        "objact_param_id": objact_param_id,
        "candidate_objact_param_id": candidate.get("obj_act_id"),
        "objact_param_match_status": (
            "exact"
            if objact_param_id == candidate.get("obj_act_id")
            else "reference_missing_objact_param_id"
            if objact_param_id is None
            else "reference_objact_param_id_differs"
        ),
        "effect_entity_id": args.get("Entity ID"),
        "relative_target_index": args.get("Relative Target IDx"),
        "state_value": args.get("State"),
        "event_flag_id": event_flag_id,
        "desired_state": desired_state,
        "instruction_name": instruction_name,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--abstract-topology", type=Path, required=True)
    parser.add_argument("--transition-audit", type=Path, required=True)
    parser.add_argument("--guarded-transitions", type=Path, required=True)
    parser.add_argument("--warp-candidates", type=Path, required=True)
    parser.add_argument("--objact-param-index", type=Path, required=True)
    parser.add_argument("--online-map-key-index", type=Path, required=True)
    parser.add_argument("--layer-index", type=Path, required=False)
    parser.add_argument("--native-topology-graph", type=Path, required=False)
    parser.add_argument("--native-msbe-model-bindings", type=Path, required=False)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    abstract_path = args.abstract_topology.resolve()
    audit_path = args.transition_audit.resolve()
    guarded_path = args.guarded_transitions.resolve()
    warp_path = args.warp_candidates.resolve()
    objact_param_path = args.objact_param_index.resolve()
    online_map_key_path = args.online_map_key_index.resolve()
    layer_index_path = args.layer_index.resolve() if args.layer_index else None
    native_topology_graph_path = (
        args.native_topology_graph.resolve() if args.native_topology_graph else None
    )
    native_msbe_model_bindings_path = (
        args.native_msbe_model_bindings.resolve()
        if args.native_msbe_model_bindings
        else None
    )
    abstract = json.loads(abstract_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    guarded = json.loads(guarded_path.read_text(encoding="utf-8"))
    warp_candidates = json.loads(warp_path.read_text(encoding="utf-8"))
    objact_param_index = json.loads(objact_param_path.read_text(encoding="utf-8"))
    online_map_key_index = json.loads(online_map_key_path.read_text(encoding="utf-8"))
    layer_index = (
        json.loads(layer_index_path.read_text(encoding="utf-8"))
        if layer_index_path and layer_index_path.is_file()
        else None
    )
    layer_coverage = (layer_index or {}).get("map_layer_coverage", [])
    native_topology_graph = (
        json.loads(native_topology_graph_path.read_text(encoding="utf-8"))
        if native_topology_graph_path and native_topology_graph_path.is_file()
        else None
    )
    native_msbe_model_bindings = (
        json.loads(native_msbe_model_bindings_path.read_text(encoding="utf-8"))
        if native_msbe_model_bindings_path and native_msbe_model_bindings_path.is_file()
        else None
    )
    objact_param_rows = {
        str(row.get("id")): row for row in objact_param_index.get("rows", [])
    }
    online_map_records = {
        record.get("mapKey"): record
        for record in online_map_key_index.get("records", [])
        if record.get("mapKey")
    }

    nodes = list(abstract.get("nodes", []))
    node_ids = {node.get("id") for node in nodes}
    supplemental_nodes = []
    native_abstract_nodes: list[dict[str, Any]] = []
    native_connector_edges: list[dict[str, Any]] = []
    native_identity_candidates: dict[str, dict[str, Any]] = {}
    native_identity_candidate_native_nodes: dict[str, set[str]] = {}
    native_identity_supplemental_nodes: list[dict[str, Any]] = []
    native_identity_relations: list[dict[str, Any]] = []
    native_identity_layer_relations: list[dict[str, Any]] = []
    if native_topology_graph is not None:
        for native_node in native_topology_graph.get("nodes", []):
            native_node_id = native_node.get("id")
            if not native_node_id or native_node_id in node_ids:
                continue
            if native_node.get("routeable") is not False:
                raise ValueError(f"native abstract node is unexpectedly routeable: {native_node_id}")
            nodes.append(native_node)
            node_ids.add(native_node_id)
            native_abstract_nodes.append(native_node)
        for connector in native_topology_graph.get("connector_edges", []):
            if connector.get("routeable") is not False:
                raise ValueError(f"native connector is unexpectedly routeable: {connector.get('id')}")
            if connector.get("from") not in node_ids or connector.get("to") not in node_ids:
                raise ValueError(f"native connector endpoint missing: {connector.get('id')}")
            native_connector_edges.append(
                {
                    **connector,
                    "edge_layer": "native_abstract_nva",
                    "verification_state": "local_native_nva_connector_declaration_exact",
                }
            )
        for binding in (native_msbe_model_bindings or {}).get("records", []):
            native_node_id = binding.get("native_node_id")
            for candidate in binding.get("msbe_part_candidates", []):
                candidate_id = candidate.get("node_id")
                if not candidate_id:
                    continue
                native_identity_candidates.setdefault(candidate_id, candidate)
                native_identity_candidate_native_nodes.setdefault(candidate_id, set()).add(
                    str(native_node_id)
                )
        for candidate_id, candidate in native_identity_candidates.items():
            if candidate_id in node_ids:
                continue
            node = native_msbe_identity_candidate_node(candidate)
            node["native_navmesh_candidate_count"] = len(
                native_identity_candidate_native_nodes.get(candidate_id, set())
            )
            nodes.append(node)
            node_ids.add(candidate_id)
            native_identity_supplemental_nodes.append(node)
        for relation in native_topology_graph.get("cross_layer_relations", []):
            if relation.get("from") not in node_ids or relation.get("to") not in node_ids:
                raise ValueError(f"native identity relation endpoint missing: {relation.get('id')}")
            native_identity_relations.append(
                {
                    **relation,
                    "relation_layer": "native_abstract_identity_bridge",
                    "routeable": False,
                    "verification_state": "local_native_msbe_exact_model_identity_relation",
                }
            )
    layer_relations: list[dict[str, Any]] = []
    layer_membership_relations: list[dict[str, Any]] = []
    local_map_ids = {
        node.get("map_id")
        for node in nodes
        if node.get("id", "").startswith("local_map_") and node.get("map_id")
    }
    if layer_index is not None:
        for record in layer_index.get("records", []):
            layer_node = native_layer_node(record)
            layer_id = layer_node.get("id")
            map_id = layer_node.get("map_id")
            if not layer_id or layer_id in node_ids or map_id not in local_map_ids:
                continue
            nodes.append(layer_node)
            node_ids.add(layer_id)
            map_node_id = f"local_map_{map_id}"
            if map_node_id in node_ids:
                layer_relations.append(
                    {
                        "id": f"map-layer:{map_node_id}:{layer_id}",
                        "from": map_node_id,
                        "to": layer_id,
                        "from_map_id": map_id,
                        "to_map_id": map_id,
                        "relation_family": "native_msbe_layer_partition",
                        "relation_type": "map_contains_native_layer_partition",
                        "map_studio_layer": layer_node.get("map_studio_layer"),
                        "routeable": False,
                        "verification_state": "local_msbe_native_layer_index_verified",
                    }
                )
        for node in list(nodes):
            if node.get("node_type") not in {"part", "region"}:
                continue
            map_id = node.get("map_id")
            layer = node.get("map_studio_layer")
            if not map_id or not isinstance(layer, int):
                continue
            layer_id = f"local-layer:{map_id}:{layer}"
            if layer_id not in node_ids:
                continue
            layer_membership_relations.append(
                {
                    "id": f"layer-member:{node.get('id')}:{layer_id}",
                    "from": node.get("id"),
                    "to": layer_id,
                    "from_map_id": map_id,
                    "to_map_id": map_id,
                    "relation_family": "native_msbe_layer_membership",
                    "relation_type": "entity_belongs_to_native_layer_partition",
                    "map_studio_layer": layer,
                    "entity_node_type": node.get("node_type"),
                    "routeable": False,
                    "verification_state": "local_msbe_native_layer_index_verified",
                }
            )
    for candidate_id, candidate in native_identity_candidates.items():
        map_id = candidate.get("map_id")
        layer = candidate.get("map_studio_layer")
        layer_id = f"local-layer:{map_id}:{layer}"
        if candidate_id not in node_ids or layer_id not in node_ids:
            continue
        native_identity_layer_relations.append(
            {
                "id": f"native-identity-layer:{candidate_id}:{layer_id}",
                "from": candidate_id,
                "to": layer_id,
                "from_map_id": map_id,
                "to_map_id": map_id,
                "relation_family": "native_msbe_identity_layer_membership",
                "relation_type": "identity_candidate_belongs_to_native_layer_partition",
                "map_studio_layer": layer,
                "entity_node_type": "native_msbe_model_identity_candidate",
                "routeable": False,
                "verification_state": "local_native_msbe_identity_and_layer_exact",
            }
        )
    exact_warp_statuses = {
        "exact_map_entity_id",
        "exact_global_entity_id_unique",
        "exact_map_identity_only",
    }
    external_target_map_ids = {
        edge.get("to_map_id")
        for edge in abstract.get("structural_edges", [])
        if not edge.get("target_exists", True) and edge.get("to_map_id")
    }
    external_target_map_ids.update(
        row.get("destination", {}).get("map_id")
        for row in warp_candidates.get("records", [])
        if row.get("destination", {}).get("resolution_status") in exact_warp_statuses
        and row.get("destination", {}).get("map_id")
        and row.get("destination", {}).get("map_id") not in local_map_ids
    )
    external_target_map_ids = sorted(external_target_map_ids)
    external_target_nodes = []
    for map_id in external_target_map_ids:
        node = {
            "id": f"local_external_map_target_{map_id}",
            "node_type": "external_map_target",
            "candidate_role": "declared_map_target_without_local_source_file",
            "map_id": map_id,
            "coordinate_system": "Elden Ring MSBE map identity",
            "coordinate_available": False,
            "original_game_coordinates": False,
            "local_game_verified": False,
            "routeable": False,
            "verification_state": "local_msbe_target_unresolved",
        }
        online_key = online_map_key(map_id)
        online_record = online_map_records.get(online_key)
        node["online_source_evidence"] = {
            "map_key": online_key,
            "record_present": online_record is not None,
            "record": online_record,
            "verification_state": "online_map_key_index_verified" if online_record else "online_map_key_index_absent",
        }
        nodes.append(node)
        node_ids.add(node["id"])
        external_target_nodes.append(node)

    supplemental_warp_nodes = []

    def ensure_endpoint(endpoint: dict[str, Any] | None) -> str | None:
        if not endpoint:
            return None
        node_id = endpoint.get("node_id")
        if not node_id:
            return None
        if node_id not in node_ids:
            node = supplemental_endpoint_node(endpoint)
            nodes.append(node)
            node_ids.add(node_id)
            supplemental_nodes.append(node)
        return node_id

    def ensure_warp_locator(locator: dict[str, Any] | None) -> str | None:
        if not locator:
            return None
        node_id = locator.get("node_id")
        if not node_id:
            return None
        if node_id not in node_ids:
            nodes.append(supplemental_warp_locator_node(locator))
            node_ids.add(node_id)
            supplemental_warp_nodes.append(nodes[-1])
        return node_id

    def map_node_or_external(map_id: str | None) -> str | None:
        if not map_id:
            return None
        if map_id in local_map_ids:
            return f"local_map_{map_id}"
        external_id = f"local_external_map_target_{map_id}"
        if external_id in node_ids:
            return external_id
        return None

    structural_edges = []
    for edge in abstract.get("structural_edges", []):
        target_exists = bool(edge.get("target_exists", True))
        to_node = (
            f"local_map_{edge.get('to_map_id')}"
            if target_exists and edge.get("to_map_id")
            else f"local_external_map_target_{edge.get('to_map_id')}"
            if edge.get("to_map_id")
            else None
        )
        structural_edges.append(
            {
                "id": edge.get("id"),
                "edge_family": "native_msbe_map_declaration",
                "topology_status": "abstract_declared_map_relation" if target_exists else "abstract_declared_target_unresolved",
                "from": edge.get("from"),
                "to": to_node,
                "from_map_id": str(edge.get("from", "")).removeprefix("local_map_"),
                "to_map_id": edge.get("to_map_id"),
                "anchor": edge.get("anchor"),
                "edge_kind": edge.get("edge_kind"),
                "raw_target_map_id": edge.get("raw_target_map_id"),
                "target_has_wildcard_byte": edge.get("target_has_wildcard_byte"),
                "target_exists": target_exists,
                "requires": edge.get("requires", []),
                "condition_status": edge.get("condition_status"),
                "routeable": False,
                "verification_state": edge.get("verification_state", "local_msbe_verified"),
            }
        )

    endpoint_edges = []
    for pair in audit.get("endpoint_pairs", []):
        from_id = ensure_endpoint(pair.get("from"))
        to_id = ensure_endpoint(pair.get("to"))
        endpoint_edges.append(
            {
                "id": pair.get("id"),
                "edge_family": "exact_msbe_endpoint_pair",
                "topology_status": "abstract_exact_endpoint_pair",
                "from": from_id,
                "to": to_id,
                "from_map_id": pair.get("from", {}).get("map_id"),
                "to_map_id": pair.get("to", {}).get("map_id"),
                "transition_kind": pair.get("transition_kind"),
                "direction": pair.get("direction"),
                "endpoint_binding_status": pair.get("endpoint_binding_status"),
                "pair_basis": pair.get("pair_basis"),
                "guard": pair.get("guard"),
                "blockers": pair.get("blockers", []),
                "routeable": False,
                "verification_state": pair.get("verification_state"),
            }
        )

    guarded_by_binding = {
        str(row.get("transition_binding_id")): row for row in guarded.get("records", [])
    }
    scripted_edges = []
    existing_scripted_reference_keys = set()
    for collection_name in ("scripted_warp_bindings", "scripted_map_warp_bindings"):
        for binding in audit.get(collection_name, []):
            from_id = ensure_endpoint(binding.get("from"))
            destination = binding.get("to", {})
            landing = destination.get("landing") or {}
            landing_id = ensure_endpoint(landing) if landing else None
            destination_id = ensure_endpoint(destination) if not landing_id else None
            to_id = landing_id or destination_id or destination.get("node_id")
            guard_candidate = guarded_by_binding.get(str(binding.get("id")), {})
            reference = binding.get("emevd_reference") or {}
            existing_scripted_reference_keys.add(
                (
                    binding.get("from", {}).get("map_id"),
                    reference.get("event_id"),
                    reference.get("instruction_index"),
                )
            )
            scripted_edges.append(
                {
                    "id": f"abstract-scripted:{binding.get('id')}",
                    "edge_family": "exact_scripted_warp",
                    "topology_status": "abstract_exact_scripted_destination",
                    "from": from_id,
                    "to": to_id,
                    "from_map_id": binding.get("from", {}).get("map_id"),
                    "to_map_id": destination.get("map_id"),
                    "transition_kind": binding.get("transition_kind"),
                    "direction": binding.get("direction"),
                    "destination_map_identity": destination.get("map_id_basis"),
                    "landing_binding_status": destination.get("landing_binding_status"),
                    "landing_node_id": landing_id,
                    "emevd_reference": binding.get("emevd_reference"),
                    "guard": compact_guard_ref(guard_candidate),
                    "routeable": False,
                    "verification_state": "local_exact_scripted_destination_guard_candidate",
                }
            )

    warp_evidence_edges = []
    warp_evidence_unresolved = []
    deduped_warp_evidence_count = 0
    for record in warp_candidates.get("records", []):
        source = record.get("source") or {}
        destination = record.get("destination") or {}
        reference = record.get("emevd_reference") or {}
        reference_key = (
            record.get("map_id"),
            reference.get("event_id", record.get("event_id")),
            reference.get("instruction_index", record.get("instruction_index")),
        )
        if reference_key in existing_scripted_reference_keys:
            deduped_warp_evidence_count += 1
            continue
        destination_status = destination.get("resolution_status")
        if destination_status not in exact_warp_statuses:
            warp_evidence_unresolved.append(
                {
                    "id": record.get("id"),
                    "map_id": record.get("map_id"),
                    "event_id": record.get("event_id"),
                    "instruction_index": record.get("instruction_index"),
                    "instruction_name": record.get("instruction_name"),
                    "transport_role": record.get("transport_role"),
                    "source_resolution_status": source.get("resolution_status"),
                    "destination_resolution_status": destination_status,
                    "destination_map_id": destination.get("map_id"),
                    "destination_entity_id": destination.get("entity_id"),
                    "routeable": False,
                }
            )
            continue

        source_id = ensure_warp_locator(source.get("locator"))
        source_binding_status = source.get("resolution_status")
        if source_id is None:
            source_id = map_node_or_external(record.get("map_id"))
            source_binding_status = source_binding_status or "source_map_identity"
        destination_id = ensure_warp_locator(destination.get("locator"))
        if destination_id is None:
            destination_id = map_node_or_external(destination.get("map_id"))
        if not source_id or not destination_id:
            warp_evidence_unresolved.append(
                {
                    "id": record.get("id"),
                    "map_id": record.get("map_id"),
                    "event_id": record.get("event_id"),
                    "instruction_index": record.get("instruction_index"),
                    "instruction_name": record.get("instruction_name"),
                    "transport_role": record.get("transport_role"),
                    "source_resolution_status": source.get("resolution_status"),
                    "destination_resolution_status": destination_status,
                    "destination_map_id": destination.get("map_id"),
                    "destination_entity_id": destination.get("entity_id"),
                    "binding_failure": "source_or_destination_node_unavailable",
                    "routeable": False,
                }
            )
            continue
        warp_evidence_edges.append(
            {
                "id": f"abstract-emevd-warp-evidence:{record.get('id')}",
                "edge_family": "emevd_scripted_warp_evidence",
                "topology_status": "abstract_scripted_transport_evidence",
                "from": source_id,
                "to": destination_id,
                "from_map_id": record.get("map_id"),
                "to_map_id": destination.get("map_id"),
                "transport_role": record.get("transport_role"),
                "instruction_name": record.get("instruction_name"),
                "event_id": record.get("event_id"),
                "instruction_index": record.get("instruction_index"),
                "source_entity_id": source.get("entity_id"),
                "destination_entity_id": destination.get("entity_id"),
                "source_binding_status": source_binding_status,
                "destination_resolution_status": destination_status,
                "destination_map_identity_basis": destination.get("map_identity_basis"),
                "emevd_reference": reference,
                "guard_status": "not_joined_in_warp_evidence_layer",
                "routeable": False,
                "verification_state": "local_emevd_warp_exact_destination_evidence",
            }
        )

    event_nodes_by_key: dict[tuple[Any, Any, Any], list[str]] = {}
    for node in nodes:
        if node.get("node_type") != "event":
            continue
        event_nodes_by_key.setdefault(
            (node.get("map_id"), node.get("event_id"), node.get("obj_act_id")), []
        ).append(node.get("id"))
    interaction_relations = []
    interaction_relation_unresolved = []
    interaction_mechanism_pair_relations: list[dict[str, Any]] = []
    interaction_mechanism_pair_seen: set[tuple[str, str]] = set()
    candidates_by_id = {
        str(candidate.get("id")): candidate
        for candidate in audit.get("interaction_candidates", [])
        if candidate.get("id")
    }
    for candidate in audit.get("interaction_candidates", []):
        candidate_id = str(candidate.get("id"))
        for peer_id_raw in candidate.get("mechanism_peer_candidate_ids", []):
            peer_id = str(peer_id_raw)
            pair_key = tuple(sorted((candidate_id, peer_id)))
            if pair_key in interaction_mechanism_pair_seen:
                continue
            peer = candidates_by_id.get(peer_id)
            if peer is None:
                continue
            left_events = event_nodes_by_key.get(
                (candidate.get("map_id"), candidate.get("event_id"), candidate.get("obj_act_id")),
                [],
            )
            right_events = event_nodes_by_key.get(
                (peer.get("map_id"), peer.get("event_id"), peer.get("obj_act_id")),
                [],
            )
            if len(left_events) != 1 or len(right_events) != 1:
                continue
            interaction_mechanism_pair_seen.add(pair_key)
            interaction_mechanism_pair_relations.append(
                {
                    "id": f"objact-mechanism-pair:{candidate.get('mechanism_pair_id')}:{pair_key[0]}:{pair_key[1]}",
                    "from": left_events[0],
                    "to": right_events[0],
                    "from_map_id": candidate.get("map_id"),
                    "to_map_id": peer.get("map_id"),
                    "relation_family": "objact_mechanism_pair_identity",
                    "relation_type": "same_mechanism_opposite_side_control",
                    "mechanism_pair_id": candidate.get("mechanism_pair_id"),
                    "mechanism_pair_label": candidate.get("mechanism_pair_label"),
                    "left_candidate_id": candidate_id,
                    "right_candidate_id": peer_id,
                    "left_obj_act_id": candidate.get("obj_act_id"),
                    "right_obj_act_id": peer.get("obj_act_id"),
                    "left_obj_act_entity_id": candidate.get("obj_act_entity_id"),
                    "right_obj_act_entity_id": peer.get("obj_act_entity_id"),
                    "left_mechanism_side": candidate.get("mechanism_side"),
                    "right_mechanism_side": peer.get("mechanism_side"),
                    "left_target_part_node_ids": candidate.get("exact_target_part_node_ids", []),
                    "right_target_part_node_ids": peer.get("exact_target_part_node_ids", []),
                    "left_objact_param": objact_param_evidence(candidate, objact_param_rows),
                    "right_objact_param": objact_param_evidence(peer, objact_param_rows),
                    "left_state_guard_evidence": objact_state_guard_evidence(
                        candidate, objact_param_rows
                    ),
                    "right_state_guard_evidence": objact_state_guard_evidence(
                        peer, objact_param_rows
                    ),
                    "binding_basis": candidate.get("mechanism_pair_binding_basis"),
                    "routeable": False,
                    "verification_state": "local_msbe_exact_objact_mechanism_pair_identity",
                }
            )
    for candidate in audit.get("interaction_candidates", []):
        target_ids = candidate.get("exact_target_part_node_ids") or []
        target_endpoint = candidate.get("target_part_endpoint")
        if target_endpoint:
            ensure_endpoint(target_endpoint)
        event_ids = event_nodes_by_key.get(
            (candidate.get("map_id"), candidate.get("event_id"), candidate.get("obj_act_id")), []
        )
        for target_id in target_ids:
            for event_id in event_ids:
                if target_id not in node_ids:
                    continue
                binding = candidate.get("emevd_binding") or {}
                interaction_relations.append(
                    {
                        "id": f"objact-control:{candidate.get('id')}:{target_id}",
                        "from": event_id,
                        "to": target_id,
                        "from_map_id": candidate.get("map_id"),
                        "to_map_id": candidate.get("map_id"),
                        "relation_family": "objact_control_to_exact_part",
                        "relation_type": "interaction_control_target",
                        "obj_act_id": candidate.get("obj_act_id"),
                        "obj_act_entity_id": candidate.get("obj_act_entity_id"),
                        "target_binding_basis": candidate.get("target_binding_basis"),
                        "emevd_state_target_binding": candidate.get("emevd_state_target_binding"),
                        "emevd_common_event_objact_binding": candidate.get("emevd_common_event_objact_binding"),
                        "event_id": candidate.get("event_id"),
                        "transition_candidate_kind": candidate.get("transition_candidate_kind"),
                        "mechanism_pair_id": candidate.get("mechanism_pair_id"),
                        "mechanism_pair_label": candidate.get("mechanism_pair_label"),
                        "mechanism_side": candidate.get("mechanism_side"),
                        "mechanism_peer_candidate_ids": candidate.get("mechanism_peer_candidate_ids", []),
                        "mechanism_pair_binding_basis": candidate.get("mechanism_pair_binding_basis"),
                        "state_type": candidate.get("state_type"),
                        "obj_act_event_flag_id": candidate.get("obj_act_event_flag_id"),
                        "emevd_binding_status": binding.get("binding_status"),
                        "exact_entity_reference_count": binding.get("exact_entity_reference_count", 0),
                        "direct_control_reference_count": binding.get("direct_control_reference_count", 0),
                        "event_scoped_condition_count": binding.get("event_scoped_condition_count", 0),
                        "event_scoped_action_count": binding.get("event_scoped_action_count", 0),
                        "event_scoped_event_flag_ids": binding.get("event_scoped_event_flag_ids", []),
                        "blockers": candidate.get("blockers", []),
                        "objact_param": objact_param_evidence(candidate, objact_param_rows),
                        "state_guard_evidence": objact_state_guard_evidence(candidate, objact_param_rows),
                        "routeable": False,
                        "verification_state": "local_msbe_verified_objact_exact_target_relation",
                    }
                )
        if target_ids and not event_ids:
            interaction_relation_unresolved.append(
                {
                    "id": candidate.get("id"),
                    "map_id": candidate.get("map_id"),
                    "event_id": candidate.get("event_id"),
                    "obj_act_id": candidate.get("obj_act_id"),
                    "obj_act_entity_id": candidate.get("obj_act_entity_id"),
                    "target_binding_basis": candidate.get("target_binding_basis"),
                    "emevd_state_target_binding": candidate.get("emevd_state_target_binding"),
                    "emevd_common_event_objact_binding": candidate.get("emevd_common_event_objact_binding"),
                    "reason": "exact_target_part_without_matching_event_node",
                    "routeable": False,
                }
            )
        if not candidate.get("exact_target_part_match"):
            interaction_relation_unresolved.append(
                {
                    "id": candidate.get("id"),
                    "map_id": candidate.get("map_id"),
                    "event_id": candidate.get("event_id"),
                    "obj_act_id": candidate.get("obj_act_id"),
                    "obj_act_entity_id": candidate.get("obj_act_entity_id"),
                    "target_binding_basis": candidate.get("target_binding_basis"),
                    "emevd_state_target_binding": candidate.get("emevd_state_target_binding"),
                    "transition_candidate_kind": candidate.get("transition_candidate_kind"),
                    "mechanism_pair_id": candidate.get("mechanism_pair_id"),
                    "mechanism_pair_label": candidate.get("mechanism_pair_label"),
                    "mechanism_side": candidate.get("mechanism_side"),
                    "mechanism_peer_candidate_ids": candidate.get("mechanism_peer_candidate_ids", []),
                    "mechanism_pair_binding_basis": candidate.get("mechanism_pair_binding_basis"),
                    "obj_act_part_name": candidate.get("obj_act_part_name"),
                    "global_objact_identity_audit": candidate.get("global_objact_identity_audit"),
                    "reason": "objact_target_part_unresolved",
                    "blockers": candidate.get("blockers", []),
                    "objact_param": objact_param_evidence(candidate, objact_param_rows),
                    "state_guard_evidence": objact_state_guard_evidence(candidate, objact_param_rows),
                    "routeable": False,
                }
            )
    interaction_relation_unresolved_count = len(interaction_relation_unresolved)

    interaction_map_identity_relations = []
    interaction_map_identity_unresolved = []
    for candidate in audit.get("interaction_candidates", []):
        target_map_id = candidate.get("obj_act_map_id")
        if not target_map_id:
            continue
        event_ids = event_nodes_by_key.get(
            (candidate.get("map_id"), candidate.get("event_id"), candidate.get("obj_act_id")), []
        )
        target_node_id = map_node_or_external(target_map_id)
        if target_node_id and event_ids:
            for event_node_id in event_ids:
                interaction_map_identity_relations.append(
                    {
                        "id": f"objact-map-identity:{candidate.get('id')}:{event_node_id}:{target_node_id}",
                        "from": event_node_id,
                        "to": target_node_id,
                        "from_map_id": candidate.get("map_id"),
                        "to_map_id": target_map_id,
                        "relation_family": "objact_explicit_map_identity",
                        "relation_type": "objact_explicit_map_id_evidence",
                        "obj_act_id": candidate.get("obj_act_id"),
                        "obj_act_entity_id": candidate.get("obj_act_entity_id"),
                        "obj_act_map_id_raw": candidate.get("obj_act_map_id_raw"),
                        "obj_act_map_id": target_map_id,
                        "direction_status": "map_identity_only_direction_unresolved",
                        "routeable": False,
                        "verification_state": "local_msbe_explicit_objact_map_id",
                    }
                )
        else:
            interaction_map_identity_unresolved.append(
                {
                    "id": f"objact-map-identity-unresolved:{candidate.get('id')}",
                    "candidate_id": candidate.get("id"),
                    "map_id": candidate.get("map_id"),
                    "event_id": candidate.get("event_id"),
                    "obj_act_id": candidate.get("obj_act_id"),
                    "obj_act_map_id_raw": candidate.get("obj_act_map_id_raw"),
                    "obj_act_map_id": target_map_id,
                    "reason": "explicit_objact_map_id_target_map_or_event_node_unresolved",
                    "routeable": False,
                }
            )

    objact_state_evidence = []
    for candidate in audit.get("interaction_candidates", []):
        if not candidate.get("exact_target_part_match"):
            continue
        binding = candidate.get("emevd_binding") or {}
        for kind, reference_key in (
            ("condition", "event_scoped_condition_references"),
            ("action", "event_scoped_action_references"),
        ):
            for reference in binding.get(reference_key, []):
                for target_id in candidate.get("exact_target_part_node_ids") or []:
                    objact_state_evidence.append(
                        {
                            "id": f"objact-state:{candidate.get('id')}:{kind}:{reference.get('id')}:{target_id}",
                            "map_id": candidate.get("map_id"),
                            "candidate_id": candidate.get("id"),
                            "obj_act_id": candidate.get("obj_act_id"),
                            "obj_act_entity_id": candidate.get("obj_act_entity_id"),
                            "target_binding_basis": candidate.get("target_binding_basis"),
                            "obj_act_event_id": candidate.get("event_id"),
                            "target_part_node_id": target_id,
                            "evidence_kind": kind,
                            "evidence_class": classify_objact_state_evidence(
                                kind, str(reference.get("instruction_name") or "")
                            ),
                            "instruction_name": reference.get("instruction_name"),
                            "event_id": reference.get("event_id"),
                            "instruction_index": reference.get("instruction_index"),
                            "event_flag_ids": reference.get("event_flag_ids", []),
                            "emevd_reference": reference,
                            "normalized_state_effect": normalized_state_effect(candidate, reference),
                            "truth_evaluated": False,
                            "routeable": False,
                            "verification_state": "local_emevd_objact_event_scoped_state_evidence",
                        }
                    )

    warp_records_by_key = {
        (
            record.get("map_id"),
            record.get("event_id"),
            record.get("instruction_index"),
        ): record
        for record in warp_candidates.get("records", [])
    }
    guarded_by_warp_key = {}
    for guarded_record in guarded.get("records", []):
        guarded_reference = guarded_record.get("emevd_reference") or {}
        guarded_map_id = (guarded_record.get("from") or {}).get("map_id")
        guarded_by_warp_key[
            (
                guarded_map_id,
                guarded_reference.get("event_id"),
                guarded_reference.get("instruction_index"),
            )
        ] = guarded_record
    interaction_transport_relations = []
    interaction_transport_unresolved = []
    for candidate in audit.get("interaction_candidates", []):
        binding = candidate.get("emevd_binding") or {}
        action_refs = list(binding.get("event_scoped_action_references", []))
        action_refs.extend(binding.get("direct_control_references", []))
        seen_warp_keys = set()
        event_ids = event_nodes_by_key.get(
            (candidate.get("map_id"), candidate.get("event_id"), candidate.get("obj_act_id")), []
        )
        for ref in action_refs:
            warp_key = (
                candidate.get("map_id"),
                ref.get("event_id"),
                ref.get("instruction_index"),
            )
            if warp_key in seen_warp_keys:
                continue
            seen_warp_keys.add(warp_key)
            warp_record = warp_records_by_key.get(warp_key)
            if not warp_record:
                continue
            destination = warp_record.get("destination") or {}
            destination_status = destination.get("resolution_status")
            destination_node_id = None
            if destination.get("locator"):
                destination_node_id = destination["locator"].get("node_id")
            if destination_node_id is None:
                destination_node_id = map_node_or_external(destination.get("map_id"))
            if (
                destination_status in exact_warp_statuses
                and destination_node_id in node_ids
                and event_ids
            ):
                guard_candidate = guarded_by_warp_key.get(warp_key)
                for event_node_id in event_ids:
                    interaction_transport_relations.append(
                        {
                            "id": f"objact-transport:{candidate.get('id')}:{warp_record.get('id')}:{event_node_id}",
                            "from": event_node_id,
                            "to": destination_node_id,
                            "from_map_id": candidate.get("map_id"),
                            "to_map_id": destination.get("map_id"),
                            "relation_family": "objact_control_to_scripted_transport",
                            "relation_type": "objact_exact_warp_action",
                            "obj_act_id": candidate.get("obj_act_id"),
                            "event_id": candidate.get("event_id"),
                            "transition_candidate_kind": candidate.get("transition_candidate_kind"),
                            "warp_record_id": warp_record.get("id"),
                            "transport_role": warp_record.get("transport_role"),
                            "instruction_name": warp_record.get("instruction_name"),
                            "instruction_index": warp_record.get("instruction_index"),
                            "destination_resolution_status": destination_status,
                            "destination_entity_id": destination.get("entity_id"),
                            "destination_map_id": destination.get("map_id"),
                            "objact_param": objact_param_evidence(candidate, objact_param_rows),
                            "state_guard_evidence": objact_state_guard_evidence(candidate, objact_param_rows),
                            "guard": compact_guard_ref(guard_candidate) if guard_candidate else {
                                "guard_status": "not_present_in_guard_trace_index",
                                "routeable": False,
                            },
                            "routeable": False,
                            "verification_state": "local_objact_exact_emevd_transport_binding",
                        }
                    )
            else:
                interaction_transport_unresolved.append(
                    {
                        "id": f"objact-transport-unresolved:{candidate.get('id')}:{warp_record.get('id')}",
                        "candidate_id": candidate.get("id"),
                        "map_id": candidate.get("map_id"),
                        "event_id": candidate.get("event_id"),
                        "obj_act_id": candidate.get("obj_act_id"),
                        "warp_record_id": warp_record.get("id"),
                        "instruction_name": warp_record.get("instruction_name"),
                        "destination_resolution_status": destination_status,
                        "reason": "objact_warp_action_destination_or_event_binding_unresolved",
                        "routeable": False,
                    }
                )

    edges = (
        structural_edges
        + endpoint_edges
        + scripted_edges
        + warp_evidence_edges
        + native_connector_edges
    )
    output = {
        "schema": "elden-ring-local-abstract-topology-graph@1",
        "source": {
            "abstract_topology": str(abstract_path),
            "abstract_topology_sha256": sha256(abstract_path),
            "transition_audit": str(audit_path),
            "transition_audit_sha256": sha256(audit_path),
            "guarded_transitions": str(guarded_path),
            "guarded_transitions_sha256": sha256(guarded_path),
            "warp_candidates": str(warp_path),
            "warp_candidates_sha256": sha256(warp_path),
            "objact_param_index": str(objact_param_path),
            "objact_param_index_sha256": sha256(objact_param_path),
            "online_map_key_index": str(online_map_key_path),
            "online_map_key_index_sha256": sha256(online_map_key_path),
            "native_topology_graph": str(native_topology_graph_path) if native_topology_graph_path else None,
            "native_topology_graph_sha256": (
                sha256(native_topology_graph_path)
                if native_topology_graph_path and native_topology_graph_path.is_file()
                else None
            ),
            "native_msbe_model_bindings": (
                str(native_msbe_model_bindings_path)
                if native_msbe_model_bindings_path
                else None
            ),
            "native_msbe_model_bindings_sha256": (
                sha256(native_msbe_model_bindings_path)
                if native_msbe_model_bindings_path
                and native_msbe_model_bindings_path.is_file()
                else None
            ),
            "layer_index": str(layer_index_path) if layer_index_path else None,
            "layer_index_sha256": (
                sha256(layer_index_path)
                if layer_index_path and layer_index_path.is_file()
                else None
            ),
        },
        "model": {
            "purpose": "merged abstract topology and native Navmesh evidence graph for exact map/entity/warp relations",
            "abstract_topology_is_not_continuous_walkability": True,
            "native_nva_evidence_used": True,
            "havok_nva_navmesh_used_for_continuous_walkability": False,
            "native_topology_graph_joined_by_map_id": native_topology_graph is not None,
            "native_topology_graph_is_abstract_adjacency_only": True,
            "native_msbe_model_identity_bindings_joined": native_msbe_model_bindings is not None,
            "native_msbe_model_identity_is_not_player_entrance": True,
            "native_msbe_layer_partition_joined_by_map_id": layer_index is not None,
            "native_msbe_layer_partition_is_not_floor_semantics": True,
            "routeable": False,
            "edge_families": {
                "native_msbe_map_declaration": "raw ConnectCollision/Connection map relation",
                "exact_msbe_endpoint_pair": "same-name/region endpoint identity on both maps",
                "exact_scripted_warp": "EMEVD destination and exact landing identity",
                "emevd_scripted_warp_evidence": "map-local EMEVD warp instruction with exact map/entity resolution; transport role is preserved and not promoted to player route",
                "native_nva_connector_declaration": "exact NVA Connector endpoint declaration; pure abstract topology only, not a player transition",
                "native_msbe_model_identity": "exact native NVA model to MSBE Collision/ConnectCollision identity candidate; not an entrance or route edge",
                "objact_mechanism_pair_identity": "exact same-map source-label/opposite-side ObjAct mechanism pairing; not a player route edge",
                "objact_control_to_exact_part": "exact ObjAct event-to-target-part control relation; it is not a destination or walkable transition edge",
                "emevd_common_event_objact_target_reference": "raw same-map InitializeCommonEvent parameter substitution to a unique MSBE Part target; it is exact identity evidence, not a route edge",
                "objact_control_to_scripted_transport": "exact ObjAct event-to-EMEVD transport action relation; destination identity is preserved but routeability is not inferred",
            },
        },
        "status": {
            "node_count": len(nodes),
            "source_node_count": len(abstract.get("nodes", [])),
            "native_abstract_node_count": len(native_abstract_nodes),
            "native_identity_candidate_node_count": len(native_identity_candidates),
            "native_identity_supplemental_node_count": len(native_identity_supplemental_nodes),
            "supplemental_transition_endpoint_nodes": len(supplemental_nodes),
            "native_layer_index_record_count": (layer_index or {}).get("status", {}).get(
                "layer_records", 0
            ),
            "native_layer_node_count": len(layer_relations),
            "native_layer_partition_relation_count": len(layer_relations),
            "native_layer_membership_relation_count": len(layer_membership_relations),
            "native_layer_distinct_value_count": (layer_index or {}).get("status", {}).get(
                "distinct_layer_values", 0
            ),
            "native_layer_coverage_map_count": len(layer_coverage),
            "native_layer_coverage_maps_with_layer_records": (layer_index or {}).get(
                "status", {}
            ).get("maps_with_layer_records", 0),
            "native_layer_coverage_maps_without_layer_records": (layer_index or {}).get(
                "status", {}
            ).get("maps_without_layer_records", 0),
            "native_layer_coverage_all_routeable_false": all(
                row.get("routeable") is False for row in layer_coverage
            ),
            "native_layer_all_routeable_false": all(
                node.get("routeable") is False
                for node in nodes
                if node.get("node_type") == "native_map_layer"
            ),
            "external_declared_map_target_nodes": len(external_target_nodes),
            "external_declared_map_target_online_records": sum(
                node.get("online_source_evidence", {}).get("record_present")
                for node in external_target_nodes
            ),
            "edge_count": len(edges),
            "native_abstract_connector_edge_count": len(native_connector_edges),
            "native_abstract_boundary_edges_omitted_count": (native_topology_graph or {}).get("status", {}).get(
                "boundary_edge_count", 0
            ),
            "native_identity_relation_count": len(native_identity_relations),
            "native_identity_layer_relation_count": len(native_identity_layer_relations),
            "native_identity_relations_all_routeable_false": all(
                relation.get("routeable") is False for relation in native_identity_relations
            ),
            "native_identity_layer_relations_all_routeable_false": all(
                relation.get("routeable") is False
                for relation in native_identity_layer_relations
            ),
            "native_map_declaration_edge_count": len(structural_edges),
            "exact_endpoint_edge_count": len(endpoint_edges),
            "exact_scripted_warp_edge_count": len(scripted_edges),
            "emevd_warp_evidence_edge_count": len(warp_evidence_edges),
            "emevd_warp_evidence_deduped_existing_count": deduped_warp_evidence_count,
            "warp_evidence_unresolved_count": len(warp_evidence_unresolved),
            "supplemental_warp_locator_nodes": sum(
                node.get("node_type") == "warp_evidence_endpoint" for node in supplemental_warp_nodes
            ),
            "objact_param_candidate_id_count": len({
                candidate.get("obj_act_id")
                for candidate in audit.get("interaction_candidates", [])
                if candidate.get("obj_act_id") not in (None, -1)
            }),
            "objact_param_exact_candidate_id_count": len({
                candidate.get("obj_act_id")
                for candidate in audit.get("interaction_candidates", [])
                if candidate.get("obj_act_id") not in (None, -1)
                and str(candidate.get("obj_act_id")) in objact_param_rows
            }),
            "objact_param_missing_candidate_id_count": len({
                candidate.get("obj_act_id")
                for candidate in audit.get("interaction_candidates", [])
                if candidate.get("obj_act_id") not in (None, -1)
                and str(candidate.get("obj_act_id")) not in objact_param_rows
            }),
            "objact_param_bound_control_relation_count": sum(
                relation.get("objact_param", {}).get("resolution_status") == "exact_local_objact_param_row"
                for relation in interaction_relations
            ),
            "objact_state_evidence_count": len(objact_state_evidence),
            "objact_state_condition_evidence_count": sum(
                evidence.get("evidence_kind") == "condition" for evidence in objact_state_evidence
            ),
            "objact_state_action_evidence_count": sum(
                evidence.get("evidence_kind") == "action" for evidence in objact_state_evidence
            ),
            "objact_state_objact_write_evidence_count": sum(
                evidence.get("evidence_class") == "objact_state_write" for evidence in objact_state_evidence
            ),
            "objact_state_objact_write_exact_param_match_count": sum(
                evidence.get("normalized_state_effect", {}).get("objact_param_match_status") == "exact"
                for evidence in objact_state_evidence
                if evidence.get("evidence_class") == "objact_state_write"
            ),
            "objact_state_unique_emevd_reference_count": len({
                evidence.get("emevd_reference", {}).get("id")
                for evidence in objact_state_evidence
            }),
            "objact_control_relation_count": len(interaction_relations),
            "objact_control_relation_unresolved_count": interaction_relation_unresolved_count,
            "objact_mechanism_pair_relation_count": len(interaction_mechanism_pair_relations),
            "objact_mechanism_pair_relations_all_routeable_false": all(
                relation.get("routeable") is False
                for relation in interaction_mechanism_pair_relations
            ),
            "objact_transition_candidate_target_part_unresolved": audit.get("status", {}).get(
                "objact_transition_candidate_target_part_unresolved", 0
            ),
            "objact_mechanism_pair_count": audit.get("status", {}).get(
                "objact_mechanism_pair_count", 0
            ),
            "objact_mechanism_pair_row_count": audit.get("status", {}).get(
                "objact_mechanism_pair_row_count", 0
            ),
            "objact_non_transition_target_part_unresolved": audit.get("status", {}).get(
                "objact_non_transition_target_part_unresolved", 0
            ),
            "objact_exact_cross_map_entity_part_matches": audit.get("status", {}).get(
                "objact_exact_cross_map_entity_part_matches", 0
            ),
            "objact_exact_global_entity_param_cross_map_matches": audit.get("status", {}).get(
                "objact_exact_global_entity_param_cross_map_matches", 0
            ),
            "objact_verified_entity_id_minus_2000_support_count": audit.get("status", {}).get(
                "objact_verified_entity_id_minus_2000_support_count", 0
            ),
            "objact_exact_verified_entity_id_minus_2000_matches": audit.get("status", {}).get(
                "objact_exact_verified_entity_id_minus_2000_matches", 0
            ),
            "objact_exact_emevd_objact_param_unique_state_target_matches": sum(
                candidate.get("target_binding_basis") == "exact_emevd_objact_param_unique_state_target"
                for candidate in audit.get("interaction_candidates", [])
            ),
            "objact_exact_common_event_objact_state_target_matches": sum(
                candidate.get("target_binding_basis") == "exact_emevd_common_event_objact_state_target"
                for candidate in audit.get("interaction_candidates", [])
            ),
            "objact_transport_relation_count": len(interaction_transport_relations),
            "objact_transport_relation_unresolved_count": len(interaction_transport_unresolved),
            "objact_explicit_map_identity_relation_count": len(interaction_map_identity_relations),
            "objact_explicit_map_identity_unresolved_count": len(interaction_map_identity_unresolved),
            "semantic_relation_count": len(abstract.get("relations", [])),
            "online_map_key_records": abstract.get("status", {}).get("online_map_key_records", 0),
            "online_map_key_missing": abstract.get("status", {}).get("online_map_key_missing", 0),
            "online_tile_region_records": abstract.get("status", {}).get("online_tile_region_records", 0),
            "online_tile_region_missing": abstract.get("status", {}).get("online_tile_region_missing", 0),
            "native_layer_record_count": abstract.get("status", {}).get("native_layer_record_count", 0),
            "maps_with_native_layer_evidence": abstract.get("status", {}).get("maps_with_native_layer_evidence", 0),
            "native_nva_file_count": abstract.get("status", {}).get("native_nva_file_count", 0),
            "native_nva_parsed_record_count": abstract.get("status", {}).get("native_nva_parsed_record_count", 0),
            "native_nva_maps_with_evidence": abstract.get("status", {}).get("native_nva_maps_with_evidence", 0),
            "native_nva_maps_with_navmesh": abstract.get("status", {}).get("native_nva_maps_with_navmesh", 0),
            "native_nva_total_navmeshes": abstract.get("status", {}).get("native_nva_total_navmeshes", 0),
            "native_nva_total_connectors": abstract.get("status", {}).get("native_nva_total_connectors", 0),
            "native_nva_all_routeable_false": abstract.get("status", {}).get("native_nva_all_routeable_false", False),
            "native_nva_connectivity_maps_with_evidence": abstract.get("status", {}).get(
                "native_nva_connectivity_maps_with_evidence", 0
            ),
            "native_nva_connectivity_exact_connectors": abstract.get("status", {}).get(
                "native_nva_connectivity_exact_connectors", 0
            ),
            "native_nva_connectivity_candidate_components": abstract.get("status", {}).get(
                "native_nva_connectivity_candidate_components", 0
            ),
            "native_nva_connectivity_all_routeable_false": abstract.get("status", {}).get(
                "native_nva_connectivity_all_routeable_false", False
            ),
            "native_nva_boundary_pair_maps_with_evidence": abstract.get("status", {}).get(
                "native_nva_boundary_pair_maps_with_evidence", 0
            ),
            "native_nva_boundary_pair_count": abstract.get("status", {}).get(
                "native_nva_boundary_pair_count", 0
            ),
            "native_nva_boundary_pair_hkx2_range_validated_count": abstract.get("status", {}).get(
                "native_nva_boundary_pair_hkx2_range_validated_count", 0
            ),
            "native_nva_boundary_pair_hkx2_range_conflict_count": abstract.get("status", {}).get(
                "native_nva_boundary_pair_hkx2_range_conflict_count", 0
            ),
            "native_nva_boundary_pair_geometry_missing_count": abstract.get("status", {}).get(
                "native_nva_boundary_pair_geometry_missing_count", 0
            ),
            "native_nva_boundary_pair_all_routeable_false": abstract.get("status", {}).get(
                "native_nva_boundary_pair_all_routeable_false", False
            ),
            "native_nvmhktbnd_maps_with_evidence": abstract.get("status", {}).get(
                "native_nvmhktbnd_maps_with_evidence", 0
            ),
            "native_nvmhktbnd_parsed_record_count": abstract.get("status", {}).get(
                "native_nvmhktbnd_parsed_record_count", 0
            ),
            "native_nvmhktbnd_hkx_entry_count": abstract.get("status", {}).get(
                "native_nvmhktbnd_hkx_entry_count", 0
            ),
            "native_nvmhktbnd_geometry_deserialized": abstract.get("status", {}).get(
                "native_nvmhktbnd_geometry_deserialized", False
            ),
            "native_nvmhktbnd_all_routeable_false": abstract.get("status", {}).get(
                "native_nvmhktbnd_all_routeable_false", False
            ),
            "native_nvmhktbnd_geometry_maps_with_evidence": abstract.get("status", {}).get(
                "native_nvmhktbnd_geometry_maps_with_evidence", 0
            ),
            "native_nvmhktbnd_geometry_navmesh_hkx_entry_count": abstract.get("status", {}).get(
                "native_nvmhktbnd_geometry_navmesh_hkx_entry_count", 0
            ),
            "native_nvmhktbnd_geometry_face_count": abstract.get("status", {}).get(
                "native_nvmhktbnd_geometry_face_count", 0
            ),
            "native_nvmhktbnd_geometry_edge_count": abstract.get("status", {}).get(
                "native_nvmhktbnd_geometry_edge_count", 0
            ),
            "native_nvmhktbnd_geometry_vertex_count": abstract.get("status", {}).get(
                "native_nvmhktbnd_geometry_vertex_count", 0
            ),
            "native_nvmhktbnd_geometry_deserialized": abstract.get("status", {}).get(
                "native_nvmhktbnd_geometry_deserialized", False
            ),
            "native_nvmhktbnd_geometry_all_routeable_false": abstract.get("status", {}).get(
                "native_nvmhktbnd_geometry_all_routeable_false", False
            ),
            "native_topology_graph_map_count": (native_topology_graph or {}).get("status", {}).get(
                "map_count", 0
            ),
            "native_topology_graph_node_count": (native_topology_graph or {}).get("status", {}).get(
                "node_count", 0
            ),
            "native_topology_graph_boundary_edge_count": (native_topology_graph or {}).get("status", {}).get(
                "boundary_edge_count", 0
            ),
            "native_topology_graph_connector_declaration_edge_count": (native_topology_graph or {}).get("status", {}).get(
                "connector_declaration_edge_count", 0
            ),
            "native_topology_graph_connector_declaration_edges_pure_abstract": (native_topology_graph or {}).get("model", {}).get(
                "connector_declaration_edges_are_pure_abstract_topology", False
            ),
            "native_topology_graph_all_routeable_false": (native_topology_graph or {}).get("status", {}).get(
                "all_nodes_routeable_false", False
            ) and (native_topology_graph or {}).get("status", {}).get("all_edges_routeable_false", False),
            "native_msbe_model_binding_node_count": (native_topology_graph or {}).get("status", {}).get(
                "msbe_model_binding_node_count", 0
            ),
            "native_msbe_model_binding_candidate_count": (native_topology_graph or {}).get("status", {}).get(
                "msbe_model_binding_candidate_count", 0
            ),
            "native_msbe_model_binding_missing_count": (native_topology_graph or {}).get("status", {}).get(
                "msbe_model_binding_missing_count", 0
            ),
            "native_msbe_model_binding_all_routeable_false": (native_topology_graph or {}).get("status", {}).get(
                "msbe_model_binding_all_routeable_false", False
            ),
            "native_msbe_model_binding_relation_count": (native_topology_graph or {}).get("status", {}).get(
                "msbe_model_binding_relation_count", 0
            ),
            "native_msbe_connect_collision_binding_count": (native_topology_graph or {}).get("status", {}).get(
                "msbe_connect_collision_binding_count", 0
            ),
            "native_msbe_connect_collision_candidate_relation_count": (native_topology_graph or {}).get("status", {}).get(
                "msbe_connect_collision_candidate_relation_count", 0
            ),
            "native_msbe_connect_collision_ambiguous_count": (native_topology_graph or {}).get("status", {}).get(
                "msbe_connect_collision_ambiguous_count", 0
            ),
            "native_msbe_connect_collision_missing_count": (native_topology_graph or {}).get("status", {}).get(
                "msbe_connect_collision_missing_count", 0
            ),
            "emevd_exact_region_entity_reference_records": abstract.get("status", {}).get(
                "emevd_exact_region_entity_reference_records", 0
            ),
            "emevd_referenced_region_nodes": abstract.get("status", {}).get(
                "emevd_referenced_region_nodes", 0
            ),
            "emevd_exact_part_entity_reference_records": abstract.get("status", {}).get(
                "emevd_exact_part_entity_reference_records", 0
            ),
            "emevd_referenced_part_nodes": abstract.get("status", {}).get(
                "emevd_referenced_part_nodes", 0
            ),
            "native_map_declaration_target_unresolved": sum(not edge["target_exists"] for edge in structural_edges),
            "scripted_warp_edges_with_guard_candidate": sum(
                row.get("guard", {}).get("guard_status") == "candidate_expression_linked"
                for row in scripted_edges
            ),
            "routeable_records": 0,
            "all_edges_routeable_false": all(edge["routeable"] is False for edge in edges),
            "all_nodes_routeable_false": all(node.get("routeable") is False for node in nodes),
        },
        "nodes": nodes,
        "edges": edges,
        "relations": abstract.get("relations", []),
        "layer_relations": layer_relations,
        "layer_membership_relations": layer_membership_relations,
        "layer_coverage": layer_coverage,
        "native_identity_relations": native_identity_relations,
        "native_identity_layer_relations": native_identity_layer_relations,
        "interaction_relations": interaction_relations,
        "interaction_mechanism_pair_relations": interaction_mechanism_pair_relations,
        "interaction_relation_unresolved": interaction_relation_unresolved,
        "interaction_transport_relations": interaction_transport_relations,
        "interaction_transport_unresolved": interaction_transport_unresolved,
        "interaction_map_identity_relations": interaction_map_identity_relations,
        "interaction_map_identity_unresolved": interaction_map_identity_unresolved,
        "objact_state_evidence": objact_state_evidence,
        "native_topology_graph": {
            "schema": (native_topology_graph or {}).get("schema"),
            "source_file": str(native_topology_graph_path) if native_topology_graph_path else None,
            "join_key": "map_id",
            "status": (native_topology_graph or {}).get("status", {}),
            "routeable": False,
            "verification_state": (
                "local_native_topology_graph_joined_by_map_id"
                if native_topology_graph is not None
                else "local_native_topology_graph_not_joined"
            ),
        },
        "warp_evidence_unresolved": warp_evidence_unresolved,
        "note": "This graph is the exact abstract evidence layer. It does not infer walkability, solve current save state, or convert endpoint identity/scripted transport into a traversable route.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
