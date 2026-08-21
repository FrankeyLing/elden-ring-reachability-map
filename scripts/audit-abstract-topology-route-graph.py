#!/usr/bin/env python3
"""Audit the independent abstract-topology route evidence graph."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    assert payload["schema"] == "elden-ring-abstract-topology-route-graph@1"
    assert payload["status"] == "abstract_topology_route_evidence_only"
    assert payload["model"]["playerRouteable"] is False
    assert payload["model"]["continuousPhysics"] is False
    assert payload["model"]["collisionWalkability"] is False
    assert payload["model"]["navmeshWalkability"] is False
    assert payload["model"]["formalPlayerRouteGraph"] is False
    nodes = payload["nodes"]
    edges = payload["edges"]
    memberships = payload["layerMembership"]
    node_ids = {node["id"] for node in nodes}
    assert len(node_ids) == len(nodes)
    assert all(node["routeable"] is False for node in nodes)
    assert all(node["playerRouteable"] is False for node in nodes)
    assert all(edge["routeable"] is False for edge in edges)
    assert all(edge["playerRouteable"] is False for edge in edges)
    assert all(edge["abstractRouteable"] is True for edge in edges)
    assert all(edge["from"] in node_ids and edge["to"] in node_ids for edge in edges)
    assert all(row["routeable"] is False for row in memberships)
    assert all(row["playerRouteable"] is False for row in memberships)
    assert len({edge["id"] for edge in edges}) == len(edges)
    edge_ids = {edge["id"] for edge in edges}
    assert all(
        edge_id in edge_ids
        for outgoing in payload["adjacency"].values()
        for edge_id in outgoing
    )
    assert payload["stats"]["mapNodeCount"] == sum(
        node["nodeType"] == "abstract_map" for node in nodes
    )
    assert payload["stats"]["layerNodeCount"] == sum(
        node["nodeType"] == "abstract_layer" for node in nodes
    )
    assert payload["stats"]["edgeCount"] == len(edges)
    assert payload["stats"]["edgeClassCounts"] == dict(
        Counter(edge["routeClass"] for edge in edges)
    )
    assert payload["stats"]["abstractRouteableEdgeCount"] == len(edges)
    print("ABSTRACT TOPOLOGY ROUTE GRAPH AUDIT: PASS")
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
