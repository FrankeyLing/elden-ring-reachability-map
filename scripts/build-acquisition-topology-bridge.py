#!/usr/bin/env python3
"""Build an isolated acquisition-endpoint to abstract-topology bridge.

This artifact joins acquisition evidence to the weakest topology anchor that
is actually proven by the copied data. It deliberately does not perform
coordinate-neighbour matching, native navmesh guessing, route promotion, or
continuous physics simulation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "v1" / "entities"
DEFAULT_ACQUISITIONS = DATA / "acquisition-registry.json"
DEFAULT_GRAPH = ROOT / "data" / "v1" / "graph-v1.json"
DEFAULT_LOCAL_GRAPH = DATA / "local-abstract-topology-graph.json"
DEFAULT_CANDIDATES = DATA / "abstract-topology-candidates.json"
DEFAULT_NATIVE = DATA / "abstract-native-topology.json"
DEFAULT_SPAWN_BINDINGS = DATA / "enemy-spawn-bindings.json"
DEFAULT_OUTPUT = DATA / "acquisition-topology-bridge.json"
MAP_ID_RE = re.compile(r"^m\d+_\d+_\d+_\d+$", re.IGNORECASE)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_map_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    for suffix in (".msb.dcx", ".msb"):
        if text.lower().endswith(suffix):
            text = text[: -len(suffix)]
    return text if MAP_ID_RE.fullmatch(text) else None


def source_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix().replace("\\", "/")


def endpoint_maps(endpoint: dict[str, Any], binding: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(binding.get("mapIds") or [])
    values.extend(binding.get("mapCandidateIds") or [])
    values.extend(normalize_map_id(value) for value in [endpoint.get("map")])
    return sorted({value for value in values if value and MAP_ID_RE.fullmatch(str(value))})


def abstract_anchor(endpoint: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
    map_ids = endpoint_maps(endpoint, binding)
    map_node_ids = sorted(set(binding.get("mapNodeIds") or []))
    candidate_node_ids = sorted(set(binding.get("mapCandidateNodeIds") or []))
    layer_ids = sorted(set(binding.get("nativeLayerNodeIds") or []))
    binding_status = binding.get("mapBindingStatus") or binding.get("status")

    if layer_ids and binding_status == "exact_map_instance":
        status = "exact_abstract_layer_anchor"
    elif map_node_ids and binding_status in {"exact_map_instance", "exact_map_instance_alias"}:
        status = "exact_abstract_map_anchor"
    elif candidate_node_ids or binding.get("mapCandidateIds"):
        status = "candidate_abstract_map_anchor"
    elif binding_status == "external_map_scope":
        status = "external_map_scope"
    elif binding_status in {"unresolved_map_instance", "unresolved"}:
        status = "unbound_map_identity"
    else:
        status = "unbound"

    return {
        "status": status,
        "mapBindingStatus": binding_status,
        "mapIds": map_ids,
        "mapNodeIds": map_node_ids,
        "candidateMapIds": sorted(set(binding.get("mapCandidateIds") or [])),
        "candidateMapNodeIds": candidate_node_ids,
        "layerIds": layer_ids,
        "evidence": list(binding.get("mapBindingEvidence") or []),
        "routeable": False,
    }


def semantic_graph_anchor(
    endpoint: dict[str, Any],
    abstract: dict[str, Any],
    pickup_nodes: dict[tuple[int, str], set[str]],
) -> dict[str, Any]:
    """Bind a pickup to a published semantic pickup node by exact identity.

    The key is the local ItemLotParam_map row plus normalized MSB map id. A
    graph node's coordinate is not consulted and cannot break a tie.
    """
    if endpoint.get("kind") != "pickup_endpoint":
        return {
            "status": "not_applicable",
            "nodeIds": [],
            "routeable": False,
        }
    lot = endpoint.get("sourceLotRow")
    if lot is None:
        lot = (endpoint.get("lot") or {}).get("rowId")
    map_ids = abstract.get("mapIds") or []
    if lot is None or not map_ids:
        return {
            "status": "unbound_missing_pickup_identity",
            "nodeIds": [],
            "routeable": False,
        }
    node_ids = sorted({
        node_id
        for map_id in map_ids
        for node_id in pickup_nodes.get((int(lot), map_id), set())
    })
    if len(node_ids) == 1:
        status = "exact_semantic_graph_anchor"
    elif node_ids:
        status = "candidate_semantic_graph_anchor"
    else:
        status = "unbound_semantic_graph_anchor"
    return {
        "status": status,
        "nodeIds": node_ids,
        "identityKey": {
            "param": "ItemLotParam_map",
            "rowId": int(lot),
            "mapIds": list(map_ids),
        },
        "routeable": False,
    }


LOCAL_PART_ENDPOINT_KINDS = {
    "enemy_spawn",
    "dummy_enemy_spawn",
    "merchant_shop_endpoint",
    "quest_npc_endpoint",
    "boss_reward_endpoint",
}

LOCAL_ENDPOINT_IDENTITY_KINDS = {
    "enemy_spawn",
    "dummy_enemy_spawn",
    "merchant_shop_endpoint",
    "quest_npc_endpoint",
    "boss_reward_endpoint",
}


def integer_identity(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def local_part_semantic_anchor(
    endpoint: dict[str, Any],
    abstract: dict[str, Any],
    local_parts: dict[tuple[str, str, int, int, int], list[str]],
) -> dict[str, Any]:
    """Bind a local endpoint to an abstract part node by exact identity only.

    The local abstract graph contains part nodes extracted from copied native
    event evidence. This intentionally requires every identity component that
    distinguishes a map part: normalized map id, exact part name, instance id,
    entity id, and map-studio layer. Coordinates and model names are not used.
    """
    if endpoint.get("kind") not in LOCAL_PART_ENDPOINT_KINDS:
        return {
            "status": "not_applicable",
            "nodeIds": [],
            "routeable": False,
        }
    map_ids = abstract.get("mapIds") or []
    part = str(endpoint.get("part") or "").strip()
    instance_id = integer_identity(endpoint.get("instanceId"))
    entity_id = integer_identity(endpoint.get("entityId"))
    map_studio_layer = integer_identity(endpoint.get("mapStudioLayer"))
    identity = {
        "mapIds": list(map_ids),
        "part": part or None,
        "instanceId": instance_id,
        "entityId": entity_id,
        "mapStudioLayer": map_studio_layer,
    }
    if not map_ids or not part or instance_id is None or entity_id is None or map_studio_layer is None:
        return {
            "status": "unbound_missing_local_part_identity",
            "nodeIds": [],
            "identityKey": identity,
            "routeable": False,
            "matchingPolicy": "exact_map_part_instance_entity_layer_identity",
        }
    node_ids = sorted({
        node_id
        for map_id in map_ids
        for node_id in local_parts.get(
            (map_id, part, instance_id, entity_id, map_studio_layer), []
        )
    })
    if len(node_ids) == 1:
        status = "exact_local_part_semantic_anchor"
    elif node_ids:
        status = "candidate_local_part_semantic_anchor"
    else:
        status = "unbound_local_part_semantic_anchor"
    return {
        "status": status,
        "nodeIds": node_ids,
        "identityKey": identity,
        "routeable": False,
        "matchingPolicy": "exact_map_part_instance_entity_layer_identity",
    }


def local_endpoint_identity(
    endpoint: dict[str, Any],
    local_endpoints: dict[tuple[str, str, int, int, int], list[dict[str, Any]]],
) -> dict[str, Any]:
    """Bind an acquisition endpoint to a copied local instance identity.

    This is deliberately separate from ``localPartSemanticAnchor``. A copied
    MSB spawn instance proves which local instance the acquisition source names,
    but it is not itself an abstract movement node and does not create a route.
    The join is exact on normalized map id, part name, instance id, entity id,
    and map-studio layer. Coordinates are never consulted.
    """
    if endpoint.get("kind") not in LOCAL_ENDPOINT_IDENTITY_KINDS:
        return {
            "status": "not_applicable",
            "identityIds": [],
            "routeable": False,
        }
    map_id = normalize_map_id(endpoint.get("map"))
    part = str(endpoint.get("part") or "").strip()
    instance_id = integer_identity(endpoint.get("instanceId"))
    entity_id = integer_identity(endpoint.get("entityId"))
    map_studio_layer = integer_identity(endpoint.get("mapStudioLayer"))
    identity = {
        "mapId": map_id,
        "part": part or None,
        "instanceId": instance_id,
        "entityId": entity_id,
        "mapStudioLayer": map_studio_layer,
    }
    if not map_id or not part or instance_id is None or entity_id is None or map_studio_layer is None:
        return {
            "status": "unbound_missing_local_endpoint_identity",
            "identityIds": [],
            "identityKey": identity,
            "routeable": False,
            "matchingPolicy": "exact_map_part_instance_entity_layer_identity",
        }
    matches = local_endpoints.get(
        (map_id, part, instance_id, entity_id, map_studio_layer), []
    )
    identity_ids = sorted({str(row["identityId"]) for row in matches})
    if len(identity_ids) == 1:
        status = "exact_local_endpoint_identity"
    elif identity_ids:
        status = "candidate_local_endpoint_identity"
    else:
        status = "unbound_local_endpoint_identity"
    result: dict[str, Any] = {
        "status": status,
        "identityIds": identity_ids,
        "identityKey": identity,
        "routeable": False,
        "matchingPolicy": "exact_map_part_instance_entity_layer_identity",
    }
    if len(identity_ids) == 1:
        match = next(row for row in matches if row["identityId"] == identity_ids[0])
        result.update({
            "sourceFile": match["sourceFile"],
            "sourceNpcParamId": match.get("npcParamId"),
            "sourceInstanceKind": match.get("kind"),
            "sourceSpawnKind": match.get("spawnKind"),
        })
    return result


def native_identity(
    endpoint: dict[str, Any],
    anchor: dict[str, Any],
    native_by_part: dict[tuple[str, str], list[dict[str, Any]]],
) -> dict[str, Any]:
    names = sorted({
        str(endpoint.get(key)).strip()
        for key in ("part", "sourcePart", "collisionName")
        if endpoint.get(key)
    })
    matches: list[dict[str, Any]] = []
    for map_id in anchor["mapIds"]:
        for name in names:
            matches.extend(native_by_part.get((map_id, name.casefold()), []))
    unique = {row["id"]: row for row in matches}
    if len(unique) == 1:
        status = "exact_native_part_identity"
    elif len(unique) > 1:
        status = "candidate_native_part_identity"
    else:
        status = "not_proven_no_native_part_identity"
    return {
        "status": status,
        "endpointPartNames": names,
        "nativeBindingIds": sorted(unique),
        "nativeNodeIds": sorted({row["from"] for row in unique.values()}),
        "routeable": False,
        "matchingPolicy": "exact_map_and_part_name_only",
    }


def compact_endpoint(
    source_class: str,
    source: dict[str, Any],
    row_index: int,
    index: int,
    pickup_nodes: dict[tuple[int, str], set[str]],
    candidate_maps: dict[str, dict[str, Any]],
    native_maps: dict[str, dict[str, Any]],
    native_by_part: dict[tuple[str, str], list[dict[str, Any]]],
    local_parts: dict[tuple[str, str, int, int, int], list[str]],
    local_endpoints: dict[tuple[str, str, int, int, int], list[dict[str, Any]]],
) -> dict[str, Any]:
    source_id = str(source.get("id") or source.get("relationId") or f"row-{index}")
    binding = source.get("topologyBinding") or {}
    anchor = abstract_anchor(source, binding)

    item_ids = sorted({
        str(item.get("item"))
        for item in source.get("items", [])
        if item.get("item") is not None
    })
    source_entity_ids = source.get("sourceEntityIds") or []
    if not source_entity_ids and source.get("from"):
        source_entity_ids = [source["from"]]
    route_node_ids = sorted({
        str(value)
        for value in (
            [source.get("formalNodeId")] + list(source.get("routeNodeIds") or [])
            + list(binding.get("routeNodeIds") or [])
        )
        if value
    })
    native = native_identity(source, anchor, native_by_part)
    semantic = semantic_graph_anchor(source, anchor, pickup_nodes)
    local_part = local_part_semantic_anchor(source, anchor, local_parts)
    local_endpoint = local_endpoint_identity(source, local_endpoints)
    bridge_identity = json.dumps(
        {
            "sourceClass": source_class,
            "sourceRecordId": source_id,
            "sourceRowIndex": row_index,
            "method": source.get("method"),
            "itemIds": item_ids,
            "endpointIndex": index,
            "endpoint": {
                key: source.get(key)
                for key in ("map", "part", "sourcePart", "model", "instanceId", "entityId", "position")
                if source.get(key) is not None
            },
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    bridge_id = hashlib.sha256(bridge_identity.encode("utf-8")).hexdigest()[:20]
    return {
        "id": f"acquisition-bridge:{source_class}:{bridge_id}",
        "sourceClass": source_class,
        "sourceRecordId": source_id,
        "sourceRowIndex": row_index,
        "relationId": source.get("relationId") or (source_id if source_class == "coverage_gap" else source.get("id")),
        "method": source.get("method"),
        "sourceEntityIds": sorted({str(value) for value in source_entity_ids if value}),
        "itemIds": item_ids,
        "endpointIndex": index,
        "endpointKind": source.get("kind"),
        "endpoint": {
            key: source.get(key)
            for key in (
                "map", "part", "sourcePart", "model", "instanceId", "entityId",
                "npcParamId", "eventId", "regionId", "position", "mapStudioLayer",
                "coordinateSpace", "sourceStatus", "externalSourceId",
            )
            if source.get(key) is not None
        },
        "abstractAnchor": anchor,
        "semanticGraphAnchor": semantic,
        "localPartSemanticAnchor": local_part,
        "localEndpointIdentity": local_endpoint,
        "nativeIdentity": native,
        "formalRouteAnchor": {
            "status": "formal_route_anchor_present" if route_node_ids else "not_a_formal_route_anchor",
            "routeNodeIds": route_node_ids,
            "routeable": False,
        },
        "verification": source.get("verification"),
        "evidence": list(source.get("evidence") or source.get("sourceEvidence") or []),
        "routeable": False,
    }


def build_map_indexes(
    candidates: dict[str, Any], native: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    candidate_maps: dict[str, dict[str, Any]] = {}
    for node in candidates.get("nodes", []):
        map_id = node.get("mapId")
        if not map_id:
            continue
        adjacency = candidates.get("adjacency", {}).get(map_id, {})
        candidate_maps[map_id] = {
            "mapNodeIds": [node.get("id")],
            "layerIds": list(node.get("layerIds") or []),
            "abstractOutgoingEdgeCount": len(adjacency.get("abstractOutgoingEdgeIds") or []),
            "abstractIncomingEdgeCount": len(adjacency.get("abstractIncomingEdgeIds") or []),
            "abstractUnresolvedOutgoingEdgeCount": len(adjacency.get("outgoingEdgeIds") or []) - len(adjacency.get("abstractOutgoingEdgeIds") or []),
            "abstractUnresolvedIncomingEdgeCount": len(adjacency.get("incomingEdgeIds") or []) - len(adjacency.get("abstractIncomingEdgeIds") or []),
        }
    native_maps = {
        row["mapId"]: {
            "coverageStatus": row.get("coverageStatus"),
            "nativeNodeCount": row.get("nativeNodeCount", 0),
            "connectorCount": row.get("connectorCount", 0),
        }
        for row in native.get("mapCoverage", [])
        if row.get("mapId")
    }
    return candidate_maps, native_maps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisitions", type=Path, default=DEFAULT_ACQUISITIONS)
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--local-graph", type=Path, default=DEFAULT_LOCAL_GRAPH)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--native", type=Path, default=DEFAULT_NATIVE)
    parser.add_argument("--spawn-bindings", type=Path, default=DEFAULT_SPAWN_BINDINGS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    acquisitions = load(args.acquisitions)
    graph = load(args.graph)
    local_graph = load(args.local_graph)
    candidates = load(args.candidates)
    native = load(args.native)
    spawn_bindings = load(args.spawn_bindings)
    candidate_maps, native_maps = build_map_indexes(candidates, native)

    graph_nodes = {row.get("id"): row for row in graph.get("nodes", []) if row.get("id")}
    pickup_nodes: dict[tuple[int, str], set[str]] = defaultdict(set)
    for relation in graph.get("relations", []):
        if relation.get("type") != "pickup_at":
            continue
        node = graph_nodes.get(relation.get("to"))
        lot = (relation.get("lot") or {}).get("rowId")
        map_id = normalize_map_id(node.get("map")) if node else None
        if node and lot is not None and map_id:
            pickup_nodes[(int(lot), map_id)].add(node["id"])

    native_by_part: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for binding in native.get("bindings", []):
        map_id = binding.get("fromMapId")
        part_name = binding.get("msbePartName")
        if map_id and part_name:
            native_by_part[(map_id, str(part_name).casefold())].append(binding)

    local_parts: dict[tuple[str, str, int, int, int], list[str]] = defaultdict(list)
    for node in local_graph.get("nodes", []):
        if node.get("node_type") != "part" or not node.get("id"):
            continue
        map_id = normalize_map_id(node.get("map_id"))
        part_name = str(node.get("name") or "").strip()
        instance_id = integer_identity(node.get("instance_id"))
        entity_id = integer_identity(node.get("entity_id"))
        map_studio_layer = integer_identity(node.get("map_studio_layer"))
        if not map_id or not part_name or instance_id is None or entity_id is None or map_studio_layer is None:
            continue
        local_parts[(map_id, part_name, instance_id, entity_id, map_studio_layer)].append(node["id"])

    local_endpoints: dict[tuple[str, str, int, int, int], list[dict[str, Any]]] = defaultdict(list)
    spawn_source_file = source_path(args.spawn_bindings)
    for binding in spawn_bindings.get("bindings", []):
        for instance in binding.get("instances", []):
            map_id = normalize_map_id(instance.get("map"))
            part_name = str(instance.get("part") or "").strip()
            instance_id = integer_identity(instance.get("instanceId"))
            entity_id = integer_identity(instance.get("entityId"))
            map_studio_layer = integer_identity(instance.get("mapStudioLayer"))
            if not map_id or not part_name or instance_id is None or entity_id is None or map_studio_layer is None:
                continue
            identity_id = (
                f"local-spawn:{map_id}:{part_name}:{instance_id}:"
                f"{entity_id}:{map_studio_layer}"
            )
            local_endpoints[(map_id, part_name, instance_id, entity_id, map_studio_layer)].append({
                "identityId": identity_id,
                "sourceFile": spawn_source_file,
                "npcParamId": instance.get("npcParamId", binding.get("npcParamId")),
                "kind": instance.get("kind"),
                "spawnKind": instance.get("spawnKind"),
            })

    records: list[dict[str, Any]] = []
    evidence_catalog: list[str] = []
    evidence_ids: dict[str, int] = {}

    def intern_evidence(values: list[Any]) -> list[int]:
        ids = []
        for value in values:
            text = str(value)
            if text not in evidence_ids:
                evidence_ids[text] = len(evidence_catalog)
                evidence_catalog.append(text)
            ids.append(evidence_ids[text])
        return ids

    for source_class, rows in (("acquisition_relation", acquisitions.get("relations", [])), ("coverage_gap", acquisitions.get("coverageGaps", []))):
        for row_index, row in enumerate(rows):
            for index, endpoint in enumerate(row.get("endpointInstances", [])):
                record = compact_endpoint(
                    source_class,
                    {**row, **endpoint},
                    row_index,
                    index,
                    pickup_nodes,
                    candidate_maps,
                    native_maps,
                    native_by_part,
                    local_parts,
                    local_endpoints,
                )
                record["evidenceIds"] = intern_evidence(record.pop("evidence", []))
                anchor_evidence = record["abstractAnchor"].pop("evidence", [])
                record["abstractAnchor"]["evidenceIds"] = intern_evidence(anchor_evidence)
                records.append(record)

    map_ids = sorted({map_id for record in records for map_id in record["abstractAnchor"]["mapIds"]})
    map_index = {}
    for map_id in map_ids:
        candidate = candidate_maps.get(map_id, {})
        native_row = native_maps.get(map_id, {})
        map_index[map_id] = {
            "mapId": map_id,
            "candidateMapNodeIds": candidate.get("mapNodeIds", []),
            "layerIds": candidate.get("layerIds", []),
            "abstractOutgoingEdgeCount": candidate.get("abstractOutgoingEdgeCount", 0),
            "abstractIncomingEdgeCount": candidate.get("abstractIncomingEdgeCount", 0),
            "abstractUnresolvedOutgoingEdgeCount": candidate.get("abstractUnresolvedOutgoingEdgeCount", 0),
            "abstractUnresolvedIncomingEdgeCount": candidate.get("abstractUnresolvedIncomingEdgeCount", 0),
            "nativeCoverageStatus": native_row.get("coverageStatus", "not_in_native_coverage_index"),
            "nativeNodeCount": native_row.get("nativeNodeCount", 0),
            "nativeConnectorCount": native_row.get("connectorCount", 0),
            "routeable": False,
        }

    anchor_statuses = Counter(row["abstractAnchor"]["status"] for row in records)
    native_statuses = Counter(row["nativeIdentity"]["status"] for row in records)
    semantic_statuses = Counter(row["semanticGraphAnchor"]["status"] for row in records)
    local_part_statuses = Counter(row["localPartSemanticAnchor"]["status"] for row in records)
    local_endpoint_statuses = Counter(row["localEndpointIdentity"]["status"] for row in records)
    method_counts = Counter(row.get("method") or "unknown" for row in records)
    source_class_counts = Counter(row["sourceClass"] for row in records)
    formal_count = sum(bool(row["formalRouteAnchor"]["routeNodeIds"]) for row in records)
    payload = {
        "schema": "elden-ring-acquisition-topology-bridge@1",
        "status": "acquisition_endpoint_bridge_evidence_only",
        "model": {
            "recordMeaning": "one acquisition evidence endpoint, independently searchable from route data",
            "abstractAnchorMeaning": "map or native-layer identity proven by copied local data; not a player position",
            "nativeIdentityMeaning": "exact part-name identity attempt only; no coordinate or geometry inference",
            "routeMeaning": "no bridge record creates or promotes a formal navigation edge",
            "continuousPhysics": False,
            "coordinateNeighbourMatching": False,
            "allRouteable": False,
        },
        "source": {
            "acquisitionArtifact": source_path(args.acquisitions),
            "candidateArtifact": source_path(args.candidates),
            "nativeArtifact": source_path(args.native),
            "graphArtifact": source_path(args.graph),
            "localGraphArtifact": source_path(args.local_graph),
            "spawnBindingsArtifact": spawn_source_file,
            "acquisitionSchema": acquisitions.get("schema"),
            "candidateSchema": candidates.get("schema"),
            "nativeSchema": native.get("schema"),
            "graphSchema": graph.get("meta", {}).get("schema") or "graph-v1",
            "localGraphSchema": local_graph.get("schema") or local_graph.get("meta", {}).get("schema"),
            "spawnBindingsSchema": spawn_bindings.get("schema"),
        },
        "mapIndex": map_index,
        "evidenceCatalog": evidence_catalog,
        "records": records,
        "stats": {
            "recordCount": len(records),
            "acquisitionRelationEndpointCount": source_class_counts["acquisition_relation"],
            "coverageGapEndpointCount": source_class_counts["coverage_gap"],
            "sourceClassCounts": {
                "acquisition_relation": source_class_counts.get("acquisition_relation", 0),
                "coverage_gap": source_class_counts.get("coverage_gap", 0),
            },
            "methodCounts": dict(method_counts),
            "abstractAnchorStatusCounts": dict(anchor_statuses),
            "nativeIdentityStatusCounts": dict(native_statuses),
            "semanticGraphAnchorStatusCounts": dict(semantic_statuses),
            "semanticGraphPickupNodeKeyCount": len(pickup_nodes),
            "localPartSemanticAnchorStatusCounts": dict(local_part_statuses),
            "localPartSemanticAnchorExactCount": local_part_statuses["exact_local_part_semantic_anchor"],
            "localPartIdentityKeyCount": len(local_parts),
            "localEndpointIdentityStatusCounts": dict(local_endpoint_statuses),
            "localEndpointIdentityExactCount": local_endpoint_statuses["exact_local_endpoint_identity"],
            "localEndpointIdentityKeyCount": len(local_endpoints),
            "formalRouteAnchorEndpointCount": formal_count,
            "mapIndexCount": len(map_index),
            "candidateMapIndexCount": sum(map_id in candidate_maps for map_id in map_index),
            "nativeMapIndexCount": sum(map_id in native_maps for map_id in map_index),
            "unboundEndpointCount": sum(
                row["abstractAnchor"]["status"] in {"unbound", "unbound_map_identity"}
                for row in records
            ),
            "allRouteableFalse": True,
        },
        "notes": [
            "Acquisition relations and coverage gaps remain valid records even when their topology anchor is absent.",
            "Exact map and layer identity is exposed separately from native navmesh partition identity.",
            "Local part semantic anchors require exact map, part, instance, entity, and map-studio-layer identity; missing matches remain searchable evidence.",
            "Local endpoint identities join acquisition endpoints to copied MSB spawn instances by exact map, part, instance, entity, and map-studio-layer identity; they are evidence identities, not abstract movement nodes.",
            "Native navmesh nodes are never selected by coordinate proximity, geometry, instance order, or name similarity.",
            "Formal player navigation remains an independent package and is not implied by this bridge.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
