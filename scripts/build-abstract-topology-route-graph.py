#!/usr/bin/env python3
"""Build an independent map/layer abstract-topology route evidence graph.

This graph is deliberately separate from the player route graph. It promotes
only candidate records whose source data already proves the source map,
destination map, direction, and abstract connection identity. It does not
claim continuous walkability, collision validity, or a currently executable
player route.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "data" / "v1" / "entities" / "abstract-topology-candidates.json"
DEFAULT_OUTPUT = ROOT / "data" / "v1" / "entities" / "abstract-topology-route-graph.json"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def source_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix().replace("\\", "/")


def map_node_id(map_id: str) -> str:
    return f"abstract-map:{map_id}"


def route_class(edge: dict[str, Any]) -> str:
    family = (edge.get("evidence") or {}).get("edgeFamily")
    if family == "native_msbe_map_declaration":
        return "explicit_map_connection"
    if family in {"exact_msbe_endpoint_pair", "exact_scripted_warp"}:
        return "exact_endpoint_connection"
    if family == "emevd_scripted_warp_evidence":
        return "scripted_transport_evidence"
    return "abstract_connection_evidence"


def build(payload: dict[str, Any], input_path: Path) -> dict[str, Any]:
    source_nodes = {
        row.get("mapId"): row
        for row in payload.get("nodes", [])
        if row.get("mapId")
    }
    nodes: list[dict[str, Any]] = []
    for map_id, row in sorted(source_nodes.items()):
        nodes.append({
            "id": map_node_id(map_id),
            "nodeType": "abstract_map",
            "mapId": map_id,
            "region": row.get("region"),
            "subRegion": row.get("subRegion"),
            "layerIds": list(row.get("layerIds") or []),
            "sourceNodeId": row.get("id"),
            "verificationState": row.get("topologyStatus"),
            "abstractRouteable": True,
            "playerRouteable": False,
            "routeable": False,
        })

    layer_ids = set()
    layers_by_id = {
        row.get("id"): row
        for row in payload.get("layers", [])
        if row.get("id")
    }
    for row in nodes:
        layer_ids.update(row.get("layerIds") or [])
    for layer_id in sorted(layer_ids):
        layer = layers_by_id.get(layer_id, {})
        nodes.append({
            "id": layer_id,
            "nodeType": "abstract_layer",
            "mapId": layer.get("mapId"),
            "mapStudioLayer": layer.get("mapStudioLayer"),
            "floorLabel": layer.get("floorLabel"),
            "floorSemanticsStatus": layer.get("floorSemanticsStatus"),
            "sourceNodeId": layer_id,
            "verificationState": layer.get("verificationState"),
            "abstractRouteable": True,
            "playerRouteable": False,
            "routeable": False,
        })

    candidate_edges = [
        row for row in payload.get("edges", []) + payload.get("transportRelations", [])
        if row.get("abstractConnected")
        and row.get("fromMapId") in source_nodes
        and row.get("toMapId") in source_nodes
    ]
    edges: list[dict[str, Any]] = []
    adjacency: dict[str, list[str]] = defaultdict(list)
    for candidate in candidate_edges:
        source_id = candidate.get("id")
        if not source_id:
            continue
        edge_id = f"abstract-route:{source_id}"
        evidence = candidate.get("evidence") or {}
        edge = {
            "id": edge_id,
            "edgeType": "abstract_topology_route_evidence",
            "from": map_node_id(candidate["fromMapId"]),
            "to": map_node_id(candidate["toMapId"]),
            "fromMapId": candidate["fromMapId"],
            "toMapId": candidate["toMapId"],
            "direction": candidate.get("direction"),
            "routeClass": route_class(candidate),
            "candidateClass": candidate.get("candidateClass"),
            "requires": list(candidate.get("requires") or []),
            "conditionStatus": (
                candidate.get("conditionStatus")
                or evidence.get("conditionStatus")
                or "not_evaluated"
            ),
            "abstractConnectionStatus": candidate.get("abstractConnectionStatus"),
            "verificationState": candidate.get("verificationState") or evidence.get("verificationState"),
            "sourceCandidateEdgeId": source_id,
            "sourceEvidence": candidate.get("evidence"),
            "abstractRouteable": True,
            "playerRouteable": False,
            "routeable": False,
        }
        edges.append(edge)
        adjacency[candidate["fromMapId"]].append(edge_id)

    membership = []
    for map_id, row in sorted(source_nodes.items()):
        for layer_id in row.get("layerIds") or []:
            membership.append({
                "id": f"abstract-membership:{map_id}:{layer_id}",
                "from": map_node_id(map_id),
                "to": layer_id,
                "mapId": map_id,
                "layerId": layer_id,
                "relationType": "map_contains_abstract_layer",
                "abstractRouteable": False,
                "playerRouteable": False,
                "routeable": False,
            })

    edge_class_counts = Counter(edge["routeClass"] for edge in edges)
    unresolved_candidate_count = sum(
        not row.get("abstractConnected")
        or row.get("toMapId") not in source_nodes
        or row.get("fromMapId") not in source_nodes
        for row in payload.get("edges", []) + payload.get("transportRelations", [])
    )
    return {
        "schema": "elden-ring-abstract-topology-route-graph@1",
        "status": "abstract_topology_route_evidence_only",
        "model": {
            "nodeMeaning": "map and native layer identity used as abstract topology route endpoints",
            "edgeMeaning": "directed identity-backed abstract connection copied from candidate evidence",
            "routeMeaning": "map/layer topology trace only; not a continuous player walk route",
            "abstractRouteableMeaning": "eligible for abstract topology trace when endpoint maps are known",
            "playerRouteable": False,
            "continuousPhysics": False,
            "collisionWalkability": False,
            "navmeshWalkability": False,
            "formalPlayerRouteGraph": False,
        },
        "source": {
            "artifact": source_path(input_path),
            "schema": payload.get("schema"),
            "status": payload.get("status"),
        },
        "nodes": nodes,
        "edges": edges,
        "layerMembership": membership,
        "adjacency": {
            map_id: sorted(edge_ids)
            for map_id, edge_ids in sorted(adjacency.items())
        },
        "stats": {
            "mapNodeCount": len(source_nodes),
            "layerNodeCount": len(layer_ids),
            "layerMembershipCount": len(membership),
            "edgeCount": len(edges),
            "candidateConnectedEdgeCount": len(edges),
            "candidateUnresolvedOrUnboundEdgeCount": unresolved_candidate_count,
            "edgeClassCounts": dict(edge_class_counts),
            "abstractRouteableEdgeCount": sum(edge["abstractRouteable"] for edge in edges),
            "allPlayerRouteableFalse": True,
            "allRouteableFalse": True,
        },
        "notes": [
            "This package is independent from graph-v1 and does not alter formal player route behavior.",
            "Map containment is metadata, not a movement edge; layer membership cannot create a cross-layer route by itself.",
            "Unknown runtime guards remain on the edge as condition evidence and are reported by the route query.",
            "No coordinate proximity, collision simulation, navmesh walkability, or game-process state is used.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build(load(args.input), args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
