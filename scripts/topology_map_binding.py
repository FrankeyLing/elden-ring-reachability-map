"""Resolve endpoint map identifiers to copied local topology map records.

This module deliberately stops at exact map-instance and, when the endpoint
contains it, exact native map-layer evidence.  It never turns a coordinate,
map instance, or native layer into a formal route node or navigation edge.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


_MAP_TOKEN_RE = re.compile(r"^(m\d+(?:_\d+){2,3})$", re.IGNORECASE)


def _clean_map_token(value: Any) -> str | None:
    if value is None:
        return None
    token = str(value).strip()
    if not token:
        return None
    token = re.sub(r"\.msb(?:\.dcx)?$", "", token, flags=re.IGNORECASE)
    token = re.sub(r"_msb(?:_dcx)?$", "", token, flags=re.IGNORECASE)
    match = _MAP_TOKEN_RE.fullmatch(token)
    return match.group(1).lower() if match else None


def load_map_index(path: Path) -> dict[str, Any]:
    """Load only map and native-layer identity records from the topology file."""
    if not path.is_file():
        return {
            "available": False,
            "maps": {},
            "layers": {},
            "map_ids": [],
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    maps: dict[str, dict[str, Any]] = {}
    layers: dict[tuple[str, str], dict[str, Any]] = {}
    for node in payload.get("nodes", []):
        if node.get("node_type") != "map" or not node.get("map_id"):
            continue
        map_id = str(node["map_id"]).lower()
        maps[map_id] = {
            "id": node.get("id"),
            "map_id": map_id,
            "source_file": node.get("source_file"),
            "local_game_verified": node.get("local_game_verified"),
            "original_game_coordinates": node.get("original_game_coordinates"),
            "native_layer_evidence": node.get("native_layer_evidence") or [],
        }
        for layer in node.get("native_layer_evidence") or []:
            if layer.get("id") is None or layer.get("map_studio_layer") is None:
                continue
            layers[(map_id, str(layer["map_studio_layer"]))] = {
                "id": layer["id"],
                "map_id": map_id,
                "map_studio_layer": layer["map_studio_layer"],
                "verification_state": layer.get("verification_state"),
                "local_game_verified": layer.get("local_game_verified"),
            }
    return {
        "available": True,
        "maps": maps,
        "layers": layers,
        "map_ids": sorted(maps),
    }


def _map_candidates(token: str, index: dict[str, Any]) -> list[str]:
    maps = index.get("maps", {})
    if token in maps:
        return [token]
    prefixed = [map_id for map_id in index.get("map_ids", []) if map_id.startswith(token + "_")]
    return sorted(prefixed)


def enrich_endpoint(endpoint: dict[str, Any], index: dict[str, Any]) -> dict[str, Any]:
    """Add exact map/layer evidence to one endpoint without changing route fields."""
    binding = dict(endpoint.get("topologyBinding") or {})
    raw_map = endpoint.get("map")
    token = _clean_map_token(raw_map)
    map_ids: list[str] = []
    candidate_ids: list[str] = []
    map_status: str
    evidence: list[str] = []

    if not index.get("available"):
        map_status = "map_index_unavailable"
    elif token is not None:
        candidates = _map_candidates(token, index)
        if len(candidates) == 1:
            map_ids = candidates
            if candidates[0] == token:
                map_status = "exact_map_instance"
            else:
                map_status = "exact_map_instance_alias"
            evidence.append(f"local-abstract-topology-graph exact map identity {candidates[0]}")
        elif len(candidates) > 1:
            candidate_ids = candidates
            map_status = "candidate_map_instance"
            evidence.append(
                f"local-abstract-topology-graph map prefix {token} has {len(candidates)} candidates"
            )
        else:
            map_status = "unresolved_map_instance"
            evidence.append(f"local-abstract-topology-graph has no map identity for {token}")
    elif raw_map or endpoint.get("mapCode") or endpoint.get("mapMaster"):
        map_status = "external_map_scope"
        evidence.append("endpoint uses an external map scope, not a local MSB map identity")
    else:
        map_status = "unresolved_map_scope"

    layer_ids: list[str] = []
    layer_status = "not_applicable"
    layer_value = endpoint.get("mapStudioLayer")
    if map_ids:
        if layer_value is None:
            layer_status = "exact_map_instance_only"
        else:
            layer_key = (map_ids[0], str(layer_value))
            layer = index.get("layers", {}).get(layer_key)
            if layer:
                layer_ids = [layer["id"]]
                layer_status = "exact_map_layer"
                evidence.append(
                    f"local-abstract-topology-graph exact native map layer {layer['id']}"
                )
            else:
                layer_status = "unresolved_map_layer"
                evidence.append(
                    f"local-abstract-topology-graph has no native layer {layer_value} for {map_ids[0]}"
                )
    elif candidate_ids:
        layer_status = "candidate_map_instance_only"
    elif map_status == "external_map_scope":
        layer_status = "external_map_scope"
    elif map_status == "unresolved_map_instance":
        layer_status = "unresolved_map_instance"
    elif map_status == "map_index_unavailable":
        layer_status = "map_index_unavailable"

    binding.update({
        "mapBindingStatus": map_status,
        "mapNodeIds": [f"local_map_{map_id}" for map_id in map_ids],
        "mapIds": map_ids,
        "mapCandidateNodeIds": [f"local_map_{map_id}" for map_id in candidate_ids],
        "mapCandidateIds": candidate_ids,
        "nativeLayerNodeIds": layer_ids,
        "mapLayerBindingStatus": layer_status,
    })
    if evidence:
        binding["mapBindingEvidence"] = evidence
    endpoint["topologyBinding"] = binding
    return endpoint


def summarize_endpoint_map_bindings(endpoints: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize endpoint map evidence for a relation-level topology binding."""
    bindings = [endpoint.get("topologyBinding") or {} for endpoint in endpoints]
    exact = [b for b in bindings if b.get("mapIds")]
    candidates = [b for b in bindings if b.get("mapCandidateIds")]
    external = [b for b in bindings if b.get("mapBindingStatus") == "external_map_scope"]
    unresolved = [
        b for b in bindings
        if b.get("mapBindingStatus") in {
            "unresolved_map_instance", "unresolved_map_scope", "map_index_unavailable",
        }
    ]
    map_ids = sorted({map_id for binding in bindings for map_id in binding.get("mapIds", [])})
    map_node_ids = sorted({node_id for binding in bindings for node_id in binding.get("mapNodeIds", [])})
    candidate_ids = sorted({map_id for binding in bindings for map_id in binding.get("mapCandidateIds", [])})
    candidate_node_ids = sorted({node_id for binding in bindings for node_id in binding.get("mapCandidateNodeIds", [])})
    layer_ids = sorted({node_id for binding in bindings for node_id in binding.get("nativeLayerNodeIds", [])})

    if not endpoints:
        status = "no_endpoint"
    elif len(exact) == len(endpoints):
        status = "exact_map_instance" if len(map_ids) == 1 else "multiple_exact_map_instances"
    elif exact:
        status = "partial_exact_map_instances"
    elif candidates:
        status = "candidate_map_instance"
    elif external and len(external) == len(endpoints):
        status = "external_map_scope"
    elif unresolved:
        status = "unresolved_map_scope"
    else:
        status = "map_binding_unclassified"

    return {
        "mapBindingStatus": status,
        "mapNodeIds": map_node_ids,
        "mapIds": map_ids,
        "mapCandidateNodeIds": candidate_node_ids,
        "mapCandidateIds": candidate_ids,
        "nativeLayerNodeIds": layer_ids,
        "mapEndpointCount": len(endpoints),
        "exactMapEndpointCount": len(exact),
        "candidateMapEndpointCount": len(candidates),
        "externalMapEndpointCount": len(external),
        "unresolvedMapEndpointCount": len(unresolved),
    }


def enrich_relations(relations: list[dict[str, Any]], index: dict[str, Any]) -> dict[str, Any]:
    """Enrich every acquisition endpoint and return auditable aggregate counts."""
    counts = Counter()
    layer_count = 0
    for relation in relations:
        for endpoint in relation.get("endpointInstances", []):
            enrich_endpoint(endpoint, index)
            status = endpoint.get("topologyBinding", {}).get("mapBindingStatus", "unclassified")
            counts[status] += 1
            if endpoint.get("topologyBinding", {}).get("nativeLayerNodeIds"):
                layer_count += 1
    return {
        "endpointCount": sum(counts.values()),
        "statusCounts": dict(sorted(counts.items())),
        "exactMapInstanceEndpointCount": sum(
            counts.get(status, 0)
            for status in ("exact_map_instance", "exact_map_instance_alias")
        ),
        "exactMapLayerEndpointCount": layer_count,
        "candidateMapEndpointCount": counts.get("candidate_map_instance", 0),
        "externalMapEndpointCount": counts.get("external_map_scope", 0),
        "unresolvedMapEndpointCount": sum(
            counts.get(status, 0)
            for status in ("unresolved_map_instance", "unresolved_map_scope", "map_index_unavailable")
        ),
    }
