#!/usr/bin/env python3
"""Audit the independent native abstract-connectivity package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    assert payload["schema"] == "elden-ring-abstract-native-topology@1"
    assert payload["status"] == "abstract_native_identity_evidence"
    assert payload["model"]["continuousPhysics"] is False
    assert payload["model"]["playerWalkabilityValidated"] is False
    assert payload["model"]["allRouteable"] is False
    maps = payload["mapCoverage"]
    nodes = payload["nodes"]
    edges = payload["edges"]
    bindings = payload["bindings"]
    assert len(maps) == payload["stats"]["mapCoverageCount"] == 1347
    assert payload["stats"]["nativeMapCount"] == 997
    assert payload["stats"]["nativeNodeMapCount"] == 846
    assert payload["stats"]["rawMissingNativeMapCount"] == 350
    assert payload["stats"]["hierarchicalParentCoveredMapCount"] == 318
    assert payload["stats"]["nonNavigationContentLayerCount"] == 32
    assert payload["stats"]["missingNativeMapCount"] == 0
    assert len(nodes) == payload["stats"]["nativeNodeCount"] == 9480
    assert len(edges) == payload["stats"]["connectorEdgeCount"] == 5884
    assert len(bindings) == payload["stats"]["bindingCount"] == 11646
    node_ids = {row["id"] for row in nodes}
    assert all(row["routeable"] is False for row in maps + nodes + edges + bindings)
    assert all(row["playerRouteable"] is False for row in nodes + edges + bindings)
    assert all(row["from"] in node_ids and row["to"] in node_ids for row in edges)
    assert all(row["abstractConnected"] is True for row in edges)
    assert payload["stats"]["abstractConnectedEdgeCount"] == len(edges)
    print("ABSTRACT NATIVE TOPOLOGY AUDIT: PASS")
    print(json.dumps({
        "maps": len(maps),
        "native_maps": payload["stats"]["nativeMapCount"],
        "native_node_maps": payload["stats"]["nativeNodeMapCount"],
        "missing_native_maps": payload["stats"]["missingNativeMapCount"],
        "nodes": len(nodes),
        "edges": len(edges),
        "bindings": len(bindings),
        "all_routeable_false": True,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
