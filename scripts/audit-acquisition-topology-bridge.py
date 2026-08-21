#!/usr/bin/env python3
"""Audit the isolated acquisition-endpoint to topology bridge."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--acquisitions", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    acquisitions = json.loads(args.acquisitions.read_text(encoding="utf-8"))

    assert payload["schema"] == "elden-ring-acquisition-topology-bridge@1"
    assert payload["status"] == "acquisition_endpoint_bridge_evidence_only"
    assert payload["model"]["continuousPhysics"] is False
    assert payload["model"]["coordinateNeighbourMatching"] is False
    assert payload["model"]["allRouteable"] is False
    records = payload["records"]
    relation_count = sum(len(row.get("endpointInstances", [])) for row in acquisitions.get("relations", []))
    gap_count = sum(len(row.get("endpointInstances", [])) for row in acquisitions.get("coverageGaps", []))
    assert len(records) == relation_count + gap_count
    assert payload["stats"]["recordCount"] == len(records)
    assert payload["stats"]["acquisitionRelationEndpointCount"] == relation_count
    assert payload["stats"]["coverageGapEndpointCount"] == gap_count
    assert payload["stats"]["sourceClassCounts"] == {
        "acquisition_relation": relation_count,
        "coverage_gap": gap_count,
    }
    assert len({row["id"] for row in records}) == len(records)
    assert all(row["routeable"] is False for row in records)
    assert all(row["abstractAnchor"]["routeable"] is False for row in records)
    assert all(row["semanticGraphAnchor"]["routeable"] is False for row in records)
    assert all(row["localPartSemanticAnchor"]["routeable"] is False for row in records)
    assert all(row["localEndpointIdentity"]["routeable"] is False for row in records)
    assert all(row["nativeIdentity"]["routeable"] is False for row in records)
    assert all(row["formalRouteAnchor"]["routeable"] is False for row in records)
    assert all(
        row["abstractAnchor"]["status"] in {
            "exact_abstract_layer_anchor",
            "exact_abstract_map_anchor",
            "candidate_abstract_map_anchor",
            "external_map_scope",
            "unbound_map_identity",
            "unbound",
        }
        for row in records
    )
    map_index = payload["mapIndex"]
    assert all(row.get("routeable") is False for row in map_index.values())
    for row in records:
        for map_id in row["abstractAnchor"]["mapIds"]:
            assert map_id in map_index
        for native_id in row["nativeIdentity"]["nativeNodeIds"]:
            assert native_id.startswith("native_navmesh:")
    assert payload["stats"]["mapIndexCount"] == len(map_index)
    assert payload["stats"]["formalRouteAnchorEndpointCount"] == sum(
        bool(row["formalRouteAnchor"]["routeNodeIds"]) for row in records
    )
    semantic_statuses = Counter(row["semanticGraphAnchor"]["status"] for row in records)
    assert payload["stats"]["semanticGraphAnchorStatusCounts"] == dict(semantic_statuses)
    assert semantic_statuses["exact_semantic_graph_anchor"] == sum(
        row["endpointKind"] == "pickup_endpoint" for row in records
    )
    local_part_statuses = Counter(row["localPartSemanticAnchor"]["status"] for row in records)
    assert payload["stats"]["localPartSemanticAnchorStatusCounts"] == dict(local_part_statuses)
    assert payload["stats"]["localPartSemanticAnchorExactCount"] == local_part_statuses[
        "exact_local_part_semantic_anchor"
    ]
    assert all(
        row["localPartSemanticAnchor"]["status"]
        not in {"exact_local_part_semantic_anchor", "candidate_local_part_semantic_anchor"}
        or row["localPartSemanticAnchor"]["nodeIds"]
        for row in records
    )
    assert all(
        row["localPartSemanticAnchor"]["status"] != "exact_local_part_semantic_anchor"
        or len(row["localPartSemanticAnchor"]["nodeIds"]) == 1
        for row in records
    )
    local_endpoint_statuses = Counter(row["localEndpointIdentity"]["status"] for row in records)
    assert payload["stats"]["localEndpointIdentityStatusCounts"] == dict(local_endpoint_statuses)
    assert payload["stats"]["localEndpointIdentityExactCount"] == local_endpoint_statuses[
        "exact_local_endpoint_identity"
    ]
    assert all(
        row["localEndpointIdentity"]["status"]
        not in {"exact_local_endpoint_identity", "candidate_local_endpoint_identity"}
        or row["localEndpointIdentity"]["identityIds"]
        for row in records
    )
    assert all(
        row["localEndpointIdentity"]["status"] != "exact_local_endpoint_identity"
        or len(row["localEndpointIdentity"]["identityIds"]) == 1
        for row in records
    )
    assert all(
        row["localEndpointIdentity"]["status"] != "exact_local_endpoint_identity"
        or row["localEndpointIdentity"].get("sourceFile") == payload["source"]["spawnBindingsArtifact"]
        for row in records
    )
    print("ACQUISITION TOPOLOGY BRIDGE AUDIT: PASS")
    print(json.dumps({
        "records": len(records),
        "relation_endpoints": relation_count,
        "coverage_gap_endpoints": gap_count,
        "maps": len(map_index),
        "abstract_anchor_statuses": Counter(
            row["abstractAnchor"]["status"] for row in records
        ),
        "native_identity_statuses": Counter(
            row["nativeIdentity"]["status"] for row in records
        ),
        "semantic_graph_anchor_statuses": semantic_statuses,
        "local_part_semantic_anchor_statuses": local_part_statuses,
        "local_endpoint_identity_statuses": local_endpoint_statuses,
        "local_endpoint_identity_exact": payload["stats"]["localEndpointIdentityExactCount"],
        "formal_route_anchor_endpoints": payload["stats"]["formalRouteAnchorEndpointCount"],
        "all_routeable_false": True,
    }, ensure_ascii=False, default=dict, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
