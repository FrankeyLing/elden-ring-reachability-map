#!/usr/bin/env python3
"""Build a compact, independent abstract-topology candidate index.

This artifact is deliberately separate from the formal route graph. It keeps
map declarations, exact endpoint pairs, and scripted transport evidence as
searchable directed candidates while preserving every unresolved condition.
No candidate emitted here is routeable.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("data/v1/entities/local-abstract-topology-graph.json")
DEFAULT_OUTPUT = Path("data/v1/entities/abstract-topology-candidates.json")

MAP_EDGE_FAMILIES = {
    "native_msbe_map_declaration",
    "exact_msbe_endpoint_pair",
    "emevd_scripted_warp_evidence",
    "exact_scripted_warp",
}


def abstract_edge_connection(edge: dict[str, Any]) -> tuple[bool, str]:
    family = edge.get("edge_family")
    if family == "native_msbe_map_declaration":
        return (
            edge.get("target_exists") is True,
            "declared_target_map_exists" if edge.get("target_exists") is True else "declared_target_map_missing",
        )
    if family == "exact_msbe_endpoint_pair":
        return (
            edge.get("endpoint_binding_status") == "exact",
            "exact_endpoint_pair" if edge.get("endpoint_binding_status") == "exact" else "endpoint_binding_unresolved",
        )
    if family == "emevd_scripted_warp_evidence":
        return (
            edge.get("destination_resolution_status")
            in {"exact_map_entity_id", "exact_map_identity_only", "exact_global_entity_id_unique"},
            "exact_scripted_destination" if edge.get("destination_resolution_status") in {
                "exact_map_entity_id", "exact_map_identity_only", "exact_global_entity_id_unique"
            } else "scripted_destination_unresolved",
        )
    if family == "exact_scripted_warp":
        return (
            edge.get("landing_binding_status") == "exact",
            "exact_landing_binding" if edge.get("landing_binding_status") == "exact" else "landing_binding_unresolved",
        )
    return False, "unsupported_candidate_family"


def compact_guard(guard: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(guard, dict):
        return None
    result: dict[str, Any] = {}
    for key in ("guard_status", "status", "record_id", "expression_ids", "path_count", "unresolved_reasons"):
        if key in guard:
            result[key] = guard[key]
    return result or None


def compact_edge(
    edge: dict[str, Any],
    layer_by_node_id: dict[str, str],
    map_by_node_id: dict[str, str],
) -> dict[str, Any]:
    family = edge.get("edge_family") or "unknown"
    abstract_connected, abstract_reason = abstract_edge_connection(edge)
    candidate_class = {
        "native_msbe_map_declaration": "map_declaration",
        "exact_msbe_endpoint_pair": "exact_endpoint_pair",
        "emevd_scripted_warp_evidence": "scripted_transport_evidence",
        "exact_scripted_warp": "exact_scripted_transport",
    }.get(family, "abstract_candidate")
    from_map_id = edge.get("from_map_id") or map_by_node_id.get(edge.get("from"))
    to_map_id = edge.get("to_map_id") or map_by_node_id.get(edge.get("to"))
    evidence: dict[str, Any] = {
        "sourceEdgeId": edge.get("id"),
        "edgeFamily": family,
        "verificationState": edge.get("verification_state"),
        "mapIdentityBasis": (
            "explicit_edge_map_ids"
            if edge.get("from_map_id") and edge.get("to_map_id")
            else "endpoint_node_map_identity"
        ),
    }
    for source_key, target_key in (
        ("anchor", "anchor"),
        ("edge_kind", "edgeKind"),
        ("transition_kind", "transitionKind"),
        ("pair_basis", "pairBasis"),
        ("endpoint_binding_status", "endpointBindingStatus"),
        ("instruction_name", "instructionName"),
        ("event_id", "eventId"),
        ("instruction_index", "instructionIndex"),
        ("transport_role", "transportRole"),
        ("destination_resolution_status", "destinationResolutionStatus"),
    ):
        if source_key in edge:
            evidence[target_key] = edge[source_key]
    if edge.get("guard"):
        evidence["guard"] = compact_guard(edge["guard"])
    if edge.get("blockers"):
        evidence["blockers"] = edge["blockers"]
    if edge.get("condition_status"):
        evidence["conditionStatus"] = edge["condition_status"]

    direction = (
        edge.get("direction")
        or edge.get("direction_status")
        or "source_to_declared_target"
    )
    result = {
        "id": edge.get("id"),
        "from": edge.get("from"),
        "to": edge.get("to"),
        "fromMapId": from_map_id,
        "toMapId": to_map_id,
        "candidateClass": candidate_class,
        "topologyStatus": edge.get("topology_status"),
        "direction": direction,
        "requires": edge.get("requires", []),
        "routeable": False,
        "playerRouteable": False,
        "abstractConnected": abstract_connected,
        "abstractConnectionStatus": abstract_reason,
        "availability": "candidate_evidence",
        "evidence": evidence,
    }
    from_layer_id = layer_by_node_id.get(edge.get("from"))
    to_layer_id = layer_by_node_id.get(edge.get("to"))
    if from_layer_id:
        result["fromLayerId"] = from_layer_id
    if to_layer_id:
        result["toLayerId"] = to_layer_id
    return result


def compact_transport(
    relation: dict[str, Any],
    layer_by_node_id: dict[str, str],
    map_by_node_id: dict[str, str],
) -> dict[str, Any]:
    from_map_id = relation.get("from_map_id") or map_by_node_id.get(relation.get("from"))
    to_map_id = relation.get("to_map_id") or map_by_node_id.get(relation.get("to"))
    result = {
        "id": relation.get("id"),
        "from": relation.get("from"),
        "to": relation.get("to"),
        "fromMapId": from_map_id,
        "toMapId": to_map_id,
        "relationType": relation.get("relation_type"),
        "transportRole": relation.get("transport_role"),
        "candidateKind": relation.get("transition_candidate_kind"),
        "destinationResolutionStatus": relation.get("destination_resolution_status"),
        "direction": "interaction_control_to_scripted_destination",
        "routeable": False,
        "playerRouteable": False,
        "abstractConnected": bool(to_map_id)
        and relation.get("destination_resolution_status")
        in {"exact_map_entity_id", "exact_map_identity_only", "exact_global_entity_id_unique"},
        "abstractConnectionStatus": (
            "exact_scripted_destination"
            if relation.get("destination_resolution_status")
            in {"exact_map_entity_id", "exact_map_identity_only", "exact_global_entity_id_unique"}
            and to_map_id
            else "destination_map_identity_unresolved"
        ),
        "availability": "candidate_evidence",
        "evidence": {
            "verificationState": relation.get("verification_state"),
            "mapIdentityBasis": (
                "explicit_relation_map_ids"
                if relation.get("from_map_id") and relation.get("to_map_id")
                else "endpoint_node_map_identity"
            ),
            "warpRecordId": relation.get("warp_record_id"),
            "eventId": relation.get("event_id"),
            "instructionIndex": relation.get("instruction_index"),
            "guard": compact_guard(relation.get("guard")),
            "stateGuardEvidence": relation.get("state_guard_evidence"),
        },
    }
    from_layer_id = layer_by_node_id.get(relation.get("from"))
    to_layer_id = layer_by_node_id.get(relation.get("to"))
    if from_layer_id:
        result["fromLayerId"] = from_layer_id
    if to_layer_id:
        result["toLayerId"] = to_layer_id
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    source = json.loads(args.input.read_text(encoding="utf-8"))
    source_nodes = source.get("nodes", [])
    map_by_node_id = {
        node["id"]: node["map_id"]
        for node in source_nodes
        if node.get("id") and node.get("map_id")
    }
    map_nodes = [node for node in source_nodes if node.get("node_type") == "map" and node.get("map_id")]
    layer_source_nodes = [
        node for node in source_nodes
        if node.get("node_type") == "native_map_layer" and node.get("map_id")
    ]
    layers = [
        {
            "id": node["id"],
            "mapId": node["map_id"],
            "mapStudioLayer": node.get("map_studio_layer"),
            "floorSemanticsStatus": node.get("floor_semantics_status") or "raw_layer_value_only",
            "floorLabel": None,
            "partCount": node.get("part_count", 0),
            "coordinateBounds": node.get("coordinate_bounds"),
            "originalGameCoordinates": node.get("original_game_coordinates") is True,
            "localGameVerified": node.get("local_game_verified") is True,
            "routeable": False,
            "topologyStatus": "abstract_native_layer_partition",
            "verificationState": node.get("verification_state"),
        }
        for node in layer_source_nodes
    ]
    layer_ids_by_map_id: dict[str, list[str]] = defaultdict(list)
    for layer in layers:
        layer_ids_by_map_id[layer["mapId"]].append(layer["id"])
    layer_id_by_map_value = {
        (node["map_id"], node.get("map_studio_layer")): node["id"]
        for node in layer_source_nodes
    }
    layer_by_node_id = {}
    for node in source_nodes:
        layer_id = layer_id_by_map_value.get((node.get("map_id"), node.get("map_studio_layer")))
        if layer_id:
            layer_by_node_id[node.get("id")] = layer_id
    map_ids = {node["map_id"] for node in map_nodes}

    nodes = []
    for node in map_nodes:
        online_tile = node.get("online_tile_region_evidence", {}).get("record") or {}
        nodes.append(
            {
                "id": node["id"],
                "mapId": node["map_id"],
                "region": online_tile.get("majorRegion") or online_tile.get("subRegion"),
                "subRegion": online_tile.get("subRegion"),
                "nativeLayerCount": node.get("native_layer_count", 0),
                "layerIds": sorted(layer_ids_by_map_id.get(node["map_id"], [])),
                "layerCoverageStatus": (
                    "present" if layer_ids_by_map_id.get(node["map_id"]) else "missing"
                ),
                "originalGameCoordinates": node.get("original_game_coordinates") is True,
                "localGameVerified": node.get("local_game_verified") is True,
                "routeable": False,
                "topologyStatus": "abstract_map_node",
            }
        )

    edges = []
    skipped = Counter()
    external_map_ids: set[str] = set()
    for edge in source.get("edges", []):
        family = edge.get("edge_family")
        if family not in MAP_EDGE_FAMILIES:
            continue
        from_map = edge.get("from_map_id") or map_by_node_id.get(edge.get("from"))
        to_map = edge.get("to_map_id") or map_by_node_id.get(edge.get("to"))
        if not from_map or not to_map:
            skipped[f"{family}:missing_map_endpoint"] += 1
            continue
        external_map_ids.update({map_id for map_id in (from_map, to_map) if map_id not in map_ids})
        edges.append(compact_edge(edge, layer_by_node_id, map_by_node_id))

    for map_id in sorted(external_map_ids):
        nodes.append(
            {
                "id": f"local_map_{map_id}",
                "mapId": map_id,
                "region": None,
                "subRegion": None,
                "nativeLayerCount": 0,
                "layerIds": [],
                "layerCoverageStatus": "external_map_unknown",
                "originalGameCoordinates": False,
                "localGameVerified": False,
                "routeable": False,
                "topologyStatus": "external_declared_map_target",
            }
        )
    map_ids.update(external_map_ids)

    transports = []
    for relation in source.get("interaction_transport_relations", []):
        transports.append(compact_transport(relation, layer_by_node_id, map_by_node_id))

    layer_relations = [
        {
            "id": relation.get("id"),
            "fromMapId": relation.get("from_map_id"),
            "layerId": relation.get("to"),
            "mapStudioLayer": relation.get("map_studio_layer"),
            "relationType": relation.get("relation_type"),
            "routeable": False,
            "availability": "native_layer_evidence",
            "verificationState": relation.get("verification_state"),
        }
        for relation in source.get("layer_relations", [])
    ]

    outgoing: dict[str, list[str]] = defaultdict(list)
    incoming: dict[str, list[str]] = defaultdict(list)
    abstract_outgoing: dict[str, list[str]] = defaultdict(list)
    abstract_incoming: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        outgoing[edge["fromMapId"]].append(edge["id"])
        incoming[edge["toMapId"]].append(edge["id"])
        if edge["abstractConnected"]:
            abstract_outgoing[edge["fromMapId"]].append(edge["id"])
            abstract_incoming[edge["toMapId"]].append(edge["id"])
    for transport in transports:
        if transport.get("fromMapId") in map_ids:
            outgoing[transport["fromMapId"]].append(transport["id"])
            if transport["abstractConnected"]:
                abstract_outgoing[transport["fromMapId"]].append(transport["id"])
        if transport.get("toMapId") in map_ids:
            incoming[transport["toMapId"]].append(transport["id"])
            if transport["abstractConnected"]:
                abstract_incoming[transport["toMapId"]].append(transport["id"])

    adjacency = {
        map_id: {
            "outgoingEdgeIds": sorted(outgoing.get(map_id, [])),
            "incomingEdgeIds": sorted(incoming.get(map_id, [])),
            "abstractOutgoingEdgeIds": sorted(abstract_outgoing.get(map_id, [])),
            "abstractIncomingEdgeIds": sorted(abstract_incoming.get(map_id, [])),
            "routeable": False,
        }
        for map_id in sorted(map_ids)
    }

    payload = {
        "schema": "elden-ring-abstract-topology-candidates@2",
        "status": "candidate_evidence_only",
        "model": {
            "nodeMeaning": "local MSBE map identity, not a player position",
            "layerMeaning": "native map partition identity; raw layer values are not guessed floor names",
            "edgeMeaning": "directed declaration or scripted transport evidence between abstract endpoints",
            "routeMeaning": "not a formal player route until direction, state and endpoint semantics are independently resolved",
            "abstractConnectionMeaning": "a local identity-backed topological relation; it may still have unknown runtime conditions",
            "continuousPhysics": False,
            "allRouteable": False,
        },
        "source": {
            "artifact": str(args.input).replace("\\", "/"),
            "sourceSchema": source.get("schema"),
            "sourceStatus": source.get("status"),
        },
        "nodes": nodes,
        "layers": layers,
        "layerRelations": layer_relations,
        "edges": edges,
        "transportRelations": transports,
        "adjacency": adjacency,
        "stats": {
            "mapNodeCount": len(nodes),
            "sourceMapNodeCount": len(map_nodes),
            "externalMapNodeCount": len(external_map_ids),
            "layerNodeCount": len(layers),
            "layerRelationCount": len(layer_relations),
            "mapsWithLayerEvidence": len(layer_ids_by_map_id),
            "mapsWithoutLayerEvidence": len(map_ids - set(layer_ids_by_map_id)),
            "sourceMapsWithoutLayerEvidence": len(
                {node["map_id"] for node in map_nodes} - set(layer_ids_by_map_id)
            ),
            "edgeCount": len(edges),
            "abstractConnectedEdgeCount": sum(edge["abstractConnected"] for edge in edges),
            "abstractUnresolvedEdgeCount": sum(not edge["abstractConnected"] for edge in edges),
            "transportRelationCount": len(transports),
            "abstractConnectedTransportCount": sum(row["abstractConnected"] for row in transports),
            "edgeFamilies": dict(Counter(edge["evidence"]["edgeFamily"] for edge in edges)),
            "candidateClassCounts": dict(Counter(edge["candidateClass"] for edge in edges)),
            "edgeMapIdentityBasisCounts": dict(
                Counter(edge["evidence"]["mapIdentityBasis"] for edge in edges)
            ),
            "mapsWithOutgoingEvidence": sum(bool(value["outgoingEdgeIds"]) for value in adjacency.values()),
            "mapsWithIncomingEvidence": sum(bool(value["incomingEdgeIds"]) for value in adjacency.values()),
            "skippedEvidence": dict(skipped),
        },
        "notes": [
            "This layer is searchable topology evidence and is not a route graph.",
            "A missing or incorrect candidate edge must not invalidate unrelated maps or entities.",
            "Candidate edges retain blockers and unresolved state evidence instead of silently becoming reachable.",
            "Native collision and navigation-mesh connectivity are intentionally excluded from this map-level candidate layer.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
