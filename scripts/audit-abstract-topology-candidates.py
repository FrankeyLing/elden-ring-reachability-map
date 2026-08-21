#!/usr/bin/env python3
"""Audit the independent abstract-topology candidate artifact."""

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

    assert payload["schema"] == "elden-ring-abstract-topology-candidates@2"
    assert payload["status"] == "candidate_evidence_only"
    assert payload["model"]["allRouteable"] is False
    nodes = payload["nodes"]
    layers = payload["layers"]
    layer_relations = payload["layerRelations"]
    edges = payload["edges"]
    transports = payload["transportRelations"]
    map_ids = {node["mapId"] for node in nodes}
    assert len(nodes) == payload["stats"]["mapNodeCount"]
    assert payload["stats"]["sourceMapNodeCount"] == 1347
    assert payload["stats"]["externalMapNodeCount"] == len(nodes) - 1347
    assert all(node["routeable"] is False for node in nodes)
    assert len(layers) == payload["stats"]["layerNodeCount"] == 1347
    assert len(layer_relations) == payload["stats"]["layerRelationCount"] == 1347
    layer_ids = {layer["id"] for layer in layers}
    assert all(layer["routeable"] is False for layer in layers)
    assert all(relation["routeable"] is False for relation in layer_relations)
    assert all(relation["layerId"] in layer_ids for relation in layer_relations)
    assert payload["stats"]["mapsWithLayerEvidence"] == 1297
    assert payload["stats"]["mapsWithoutLayerEvidence"] == 54
    assert payload["stats"]["sourceMapsWithoutLayerEvidence"] == 50
    assert all(edge["routeable"] is False for edge in edges)
    assert all(edge["playerRouteable"] is False for edge in edges)
    assert all(transport["routeable"] is False for transport in transports)
    assert all(transport["playerRouteable"] is False for transport in transports)
    assert all(edge["fromMapId"] in map_ids and edge["toMapId"] in map_ids for edge in edges)
    all_ids = {edge["id"] for edge in edges} | {row["id"] for row in transports}
    abstract_ids = {
        row["id"] for row in edges + transports if row["abstractConnected"]
    }
    assert all(
        value["routeable"] is False
        and set(value["outgoingEdgeIds"]).issubset(all_ids)
        and set(value["incomingEdgeIds"]).issubset(all_ids)
        and set(value["abstractOutgoingEdgeIds"]).issubset(abstract_ids)
        and set(value["abstractIncomingEdgeIds"]).issubset(abstract_ids)
        for value in payload["adjacency"].values()
    )
    families = Counter(edge["evidence"]["edgeFamily"] for edge in edges)
    assert families["native_msbe_map_declaration"] == 1588
    assert families["exact_msbe_endpoint_pair"] == 149
    assert families["exact_scripted_warp"] == 15
    assert families["emevd_scripted_warp_evidence"] == 340
    assert len(transports) == 18
    assert payload["stats"]["abstractConnectedEdgeCount"] == 2079
    assert payload["stats"]["abstractUnresolvedEdgeCount"] == 13
    assert payload["stats"]["abstractConnectedTransportCount"] == 18
    assert payload["stats"]["skippedEvidence"] == {}
    assert all(edge["fromMapId"] and edge["toMapId"] for edge in edges)
    assert payload["stats"]["edgeCount"] == len(edges)
    assert payload["stats"]["transportRelationCount"] == len(transports)
    print("ABSTRACT TOPOLOGY CANDIDATE AUDIT: PASS")
    print(json.dumps({
        "map_nodes": len(nodes),
        "edges": len(edges),
        "transports": len(transports),
        "layers": len(layers),
        "layer_relations": len(layer_relations),
        "families": families,
        "all_routeable_false": True,
    }, ensure_ascii=False, default=dict, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
