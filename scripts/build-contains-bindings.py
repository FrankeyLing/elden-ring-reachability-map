#!/usr/bin/env python3
"""Build the containment isolation layer: exact abstract anchors -> formal regions.

The contract (5.5) allows a fourth topology-binding state: "已包含绑定" —
an endpoint inside a verified room, region, or local connected component.
This script adds that state for bridge records whose map/layer identity is
already proven (exact_abstract_map_anchor / exact_abstract_layer_anchor).

The endpoint map id is resolved to a formal region through exactly the same
authoritative chain that assigned the formal graph node regions
(build-v1-graph.region_for_map): MSBE MapNameOverride -> PlaceName -> formal
region, tile major/sub, then the one-hop-vote prefix fallback.  A region
containment never promotes an exact anchor: routeable stays False, the
containment level is recorded, and unresolved maps stay explicit gaps.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "v1"
ENTITIES = DATA / "entities"
DEFAULT_BRIDGE = ENTITIES / "acquisition-topology-bridge.json"
DEFAULT_GRAPH = DATA / "graph-v1.json"
DEFAULT_MAP_NAMES = ENTITIES / "local-msbe-map-names.json"
DEFAULT_SNAPSHOTS = DATA / "source-snapshots"
DEFAULT_ZH_MAPPING = DATA / "zh-cn" / "official-zh-mapping.json"
DEFAULT_OUTPUT = ENTITIES / "acquisition-contains-bindings.json"
MAP_ID_RE = re.compile(r"^m\d+_\d+_\d+_\d+$", re.IGNORECASE)
KIND_PRIORITY = {
    "grace": 0,
    "entrance": 1,
    "junction": 2,
    "checkpoint": 3,
    "landmark": 4,
    "exit": 5,
    "lift": 6,
    "teleport": 7,
    "transition": 8,
    "state": 9,
    "boss": 10,
    "reward": 11,
    "target": 12,
    "item": 13,
    "world_state": 14,
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_map_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    for suffix in (".msb.dcx", ".msb"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text if MAP_ID_RE.fullmatch(text) else None


def load_region_chain() -> tuple[Any, list[dict], dict[str, dict]]:
    """Import the authoritative region resolution used by the formal graph."""
    spec = importlib.util.spec_from_file_location(
        "build_v1_graph", str(ROOT / "scripts" / "build-v1-graph.py")
    )
    bvg = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(bvg)
    tiles = bvg.load_tiles()
    tile_by_key = {tile["mapKey"]: tile for tile in tiles}
    return bvg, tiles, tile_by_key


def resolve_region_with_evidence(
    map_id: str,
    msbe_regions: dict[str, str],
    tiles: list[dict],
    tile_by_key: dict[str, dict],
    bvg: Any,
) -> tuple[str | None, list[str]]:
    """Resolve a map id exactly like the formal graph and record the branch.

    The branch order mirrors region_for_map; the final result is checked
    against region_for_map itself so a divergence fails the build loudly.
    """
    base = map_id
    evidence: list[str] = []
    if msbe_regions and base in msbe_regions:
        region = msbe_regions[base]
        evidence.append(
            f"MSBE MapNameOverride -> official place name -> formal region {region!r} ({map_id})"
        )
    else:
        region = None
        for candidate in (base, "_".join(base.split("_")[:3]), "_".join(base.split("_")[:2])):
            tile = tile_by_key.get(candidate)
            if tile:
                if tile["major"]:
                    region = tile["major"]
                    evidence.append(
                        f"tile major region {region!r} via map key {candidate}"
                    )
                elif tile["sub"]:
                    region = bvg.SUBRESION_TO_FORMAL.get(tile["sub"], tile["sub"])
                    evidence.append(
                        f"tile sub region {tile['sub']!r} -> {region!r} via map key {candidate}"
                    )
                break
        if region is None:
            for prefix, prefix_region in sorted(
                bvg.MAP_PREFIX_REGION.items(), key=lambda item: -len(item[0])
            ):
                if base.startswith(prefix):
                    region = prefix_region
                    evidence.append(
                        f"one-hop-vote map prefix {prefix} -> formal region {prefix_region!r}"
                    )
                    break
    authoritative = bvg.region_for_map(map_id, tiles, tile_by_key, msbe_regions)
    if region != authoritative:
        raise RuntimeError(
            f"containment region resolution diverged from build-v1-graph for {map_id}: "
            f"{region!r} != {authoritative!r}"
        )
    if region is None:
        evidence.append(f"no verified region mapping exists for {map_id}")
    return region, evidence


def build_region_classes(
    formal_by_region: dict[str, list[dict]], zh_nodes: dict[str, Any]
) -> tuple[dict[str, str], dict[str, list[dict]], dict[str, dict[str, Any]]]:
    """Merge zh/en region strings into canonical official-zh region classes.

    The formal graph labels the same region with official English and Chinese
    strings depending on the source of each node; a containment must treat
    them as one verified region.  The official zh mapping gives every formal
    node's canonical Chinese region, so the equivalence class key is the
    canonical zh name.
    """
    region_zh: dict[str, str] = {}
    zh_unknown: list[str] = []
    for region, region_nodes in formal_by_region.items():
        zh = None
        for node in region_nodes:
            mapped = (zh_nodes.get(str(node.get("id"))) or {}).get("region", {}).get("zh")
            if mapped:
                zh = mapped
                break
        if zh is None:
            zh_unknown.append(region)
            zh = region
        region_zh[region] = zh
    classes: dict[str, dict[str, Any]] = {}
    for region, region_nodes in formal_by_region.items():
        canonical = region_zh[region]
        bucket = classes.setdefault(
            canonical,
            {"canonicalZh": canonical, "regionStrings": [], "nodes": []},
        )
        bucket["regionStrings"].append(region)
        bucket["nodes"].extend(region_nodes)
    return region_zh, classes, zh_unknown


def representative_node(
    region: str, region_zh: dict[str, str], classes: dict[str, dict[str, Any]]
) -> tuple[str | None, str]:
    """Pick a deterministic representative inside the canonical region class.

    Within the class, nodes of the same region string (the resolved evidence
    branch) are preferred over the translated sibling strings, then kind
    priority, then node id.
    """
    canonical = region_zh.get(region) or region
    bucket = classes.get(canonical)
    if not bucket:
        return None, canonical
    group_nodes = [node for node in bucket["nodes"] if node.get("region") == region]
    ranked = sorted(
        group_nodes or bucket["nodes"],
        key=lambda node: (KIND_PRIORITY.get(node.get("kind"), 100), node.get("id", "")),
    )
    return (ranked[0]["id"] if ranked else None), canonical


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge", type=Path, default=DEFAULT_BRIDGE)
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--map-names", type=Path, default=DEFAULT_MAP_NAMES)
    parser.add_argument("--zh-mapping", type=Path, default=DEFAULT_ZH_MAPPING)
    parser.add_argument("--snapshots", type=Path, default=DEFAULT_SNAPSHOTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    bvg, tiles, tile_by_key = load_region_chain()
    msbe_regions = bvg.load_msbe_map_regions() if args.map_names.is_file() else {}
    graph = load(args.graph)
    bridge = load(args.bridge)
    map_names_payload = load(args.map_names) if args.map_names.is_file() else {}
    zh_mapping = load(args.zh_mapping)
    zh_nodes = zh_mapping.get("nodes", {})

    incident = {
        endpoint
        for edge in graph.get("edges", [])
        for endpoint in (edge.get("from"), edge.get("to"))
        if endpoint
    }
    formal_by_region: dict[str, list[dict]] = {}
    for node in graph.get("nodes", []):
        if node.get("id") in incident and node.get("region"):
            formal_by_region.setdefault(node["region"], []).append(node)
    region_zh, region_classes, zh_unknown = build_region_classes(formal_by_region, zh_nodes)
    if zh_unknown:
        raise RuntimeError(f"formal regions without official zh identity: {zh_unknown}")

    aggregate_stamp = json.dumps(
        {
            "snapshot": {
                "bridge": bridge.get("schema"),
                "graphNodes": len(graph.get("nodes", [])),
                "graphEdges": len(graph.get("edges", [])),
                "graphNodeSha256": hashlib.sha256(
                    json.dumps(
                        sorted(node.get("id", "") for node in graph.get("nodes", [])),
                        ensure_ascii=False,
                    ).encode("utf-8")
                ).hexdigest(),
            }
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    layer_sha = hashlib.sha256(aggregate_stamp).hexdigest()[:40]

    bindings: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    region_counts: Counter[str] = Counter()
    unresolved_maps: dict[str, int] = {}
    no_formal_nodes: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for record in bridge.get("records", []):
        record_id = record.get("id")
        if not record_id:
            raise RuntimeError("bridge record without id")
        if record_id in seen_ids:
            raise RuntimeError(f"duplicate bridge record id {record_id}")
        seen_ids.add(record_id)
        anchor = record.get("abstractAnchor") or {}
        status = anchor.get("status")
        endpoint = record.get("endpoint") or {}
        map_id = normalize_map_id(endpoint.get("map"))
        base: dict[str, Any] = {
            "id": f"contains:{record_id}",
            "bridgeRecordId": record_id,
            "sourceClass": record.get("sourceClass"),
            "method": record.get("method"),
            "endpointKind": record.get("endpointKind"),
            "itemIds": record.get("itemIds", []),
            "endpoint": {
                key: endpoint.get(key)
                for key in ("map", "mapStudioLayer", "part", "position")
                if endpoint.get(key) is not None
            },
        }

        if status not in ("exact_abstract_map_anchor", "exact_abstract_layer_anchor"):
            status_counts["not_applicable:" + str(status)] += 1
            bindings.append(
                {**base, "containsStatus": "not_applicable", "reason": "anchor_status_" + str(status)}
            )
            continue
        # The abstraction anchor carries the proven map identities; the
        # endpoint map field alone can miss bindings without a map at row level.
        map_candidates: list[str] = []
        for candidate in [map_id] + list(anchor.get("mapIds") or []):
            normalized = normalize_map_id(candidate)
            if normalized is not None and normalized not in map_candidates:
                map_candidates.append(normalized)
        if not map_candidates:
            status_counts["missing_map_id"] += 1
            bindings.append(
                {**base, "containsStatus": "region_unresolved", "reason": "missing_normalized_map_id"}
            )
            continue

        resolved: str | None = None
        evidence: list[str] = []
        used_map = map_candidates[0]
        for candidate in map_candidates:
            region, candidate_evidence = resolve_region_with_evidence(
                candidate, msbe_regions, tiles, tile_by_key, bvg
            )
            if region is not None:
                resolved = region
                evidence = candidate_evidence
                used_map = candidate
                break
        region = resolved
        if region is None:
            status_counts["region_unresolved"] += 1
            for candidate in map_candidates:
                unresolved_maps[candidate] = unresolved_maps.get(candidate, 0) + 1
            bindings.append(
                {
                    **base,
                    "containsStatus": "region_unresolved",
                    "mapId": map_candidates[0],
                    "reason": "no_verified_region_mapping",
                    "evidence": ["no verified region mapping exists for " + candidate for candidate in map_candidates],
                }
            )
            continue
        representative, canonical_zh = representative_node(region, region_zh, region_classes)
        if representative is None:
            status_counts["region_without_formal_nodes"] += 1
            no_formal_nodes.append(
                {**base, "containsStatus": "region_without_formal_nodes", "region": region}
            )
            bindings.append({**base, "containsStatus": "region_without_formal_nodes", "region": region})
            continue
        status_counts["region_containment"] += 1
        region_counts[canonical_zh] += 1
        bindings.append(
            {
                **base,
                "containsStatus": "region_containment",
                "containmentLevel": "region",
                "region": region,
                "canonicalZhRegion": canonical_zh,
                "mapId": used_map,
                "layerAnchor": status == "exact_abstract_layer_anchor",
                "routeNodeIds": [representative],
                "regionFormalNodeCount": len(region_classes.get(canonical_zh, {}).get("nodes", [])),
                "routeable": False,
                "evidence": evidence,
            }
        )

    payload = {
        "schema": "elden-ring-reachability-map/acquisition-contains-bindings@1",
        "contract": "5.5 已包含绑定 endpoints inside a verified formal region",
        "source": {
            "bridge": str(args.bridge),
            "graph": str(args.graph),
            "mapNames": str(args.map_names),
            "chain": "build-v1-graph region_for_map (MapNameOverride -> PlaceName; tile major/sub; one-hop-vote prefix)",
        },
        "builtFromDigest": layer_sha,
        "stats": {
            "bridgeRecordCount": len(bridge.get("records", [])),
            "bindingRecordCount": len(bindings),
            "containmentStatusCounts": dict(sorted(status_counts.items())),
            "regionContainmentCount": status_counts["region_containment"],
            "regionCount": len(region_counts),
            "unresolvedMapCount": len(unresolved_maps),
            "allRouteableFalse": True,
        },
        "regionCounts": dict(
            sorted(region_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "unresolvedMaps": sorted(unresolved_maps.items()),
        "regionWithoutFormalNodes": no_formal_nodes,
        "bindings": bindings,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2))
    print(f"wrote {len(bindings)} containment bindings to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
