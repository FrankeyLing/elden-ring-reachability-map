#!/usr/bin/env python3
"""Build the player-facing entity and acquisition query projection.

This is deliberately separate from the route packages. Entity records remain
searchable even when they have no formal route node or topology anchor yet.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "v1"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def copy_name(name: dict[str, Any] | None) -> dict[str, str]:
    name = name or {}
    return {key: str(value) for key, value in name.items() if value}


def summary_node(node: dict[str, Any], *, routeable: bool = False) -> dict[str, Any]:
    return {
        "id": node["id"],
        "label": node.get("label") or node["id"],
        "kind": node.get("kind") or "other",
        "entityType": node.get("entityType"),
        "region": node.get("region"),
        "layer": node.get("layer"),
        "floor": node.get("floor"),
        "map": node.get("map"),
        "position": node.get("position"),
        "x": node.get("x"),
        "y": node.get("y"),
        "verificationState": node.get("verificationState"),
        "routeable": routeable,
    }


def compact_acquisition(
    relation: dict[str, Any],
    endpoints: list[dict[str, Any]],
    topology_binding: dict[str, Any],
) -> dict[str, Any]:
    keep = {
        key: relation[key]
        for key in (
            "id", "from", "method", "lot", "evidence", "verification",
            "items", "price", "costType", "stock", "lineupRow",
            "sourceNpcParamRows", "sellerStatus", "merchantShopBinding",
            "eventRewardBinding",
            "questRewardBinding",
        )
        if key in relation
    }
    if endpoints:
        keep["endpointInstances"] = endpoints
    keep["topologyBinding"] = topology_binding
    return keep


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path,
                        default=DATA / "entities" / "player-entity-index.json")
    args = parser.parse_args()

    registry = load(DATA / "entities" / "entity-registry.json")
    locations = load(DATA / "entities" / "location-catalog.json")
    gaps = load(DATA / "entities" / "gap-catalog.json")
    acquisitions = load(DATA / "entities" / "acquisition-registry.json")
    pickups = load(DATA / "entities" / "pickup-location-bindings.json")
    reinforce = load(DATA / "entities" / "reinforce-catalog.json")
    graph = load(DATA / "graph-v1.json")

    records: dict[str, dict[str, Any]] = {}

    def ensure(
        entity_id: str,
        *,
        kind: str = "unknown",
        category: str | None = None,
        name: dict[str, Any] | None = None,
        source: str,
        aliases: list[str] | None = None,
        properties: dict[str, Any] | None = None,
        verification: str | None = None,
    ) -> dict[str, Any]:
        record = records.get(entity_id)
        if record is None:
            record = {
                "id": entity_id,
                "kind": kind,
                "category": category or kind,
                "name": copy_name(name) or {"en": entity_id},
                "aliases": [],
                "sources": [],
                "properties": properties or {},
                "topology": {
                    "status": "not_bound",
                    "graphNodes": [],
                    "relations": [],
                },
                "acquisitions": [],
                "reinforcementOutgoing": [],
                "reinforcementIncoming": [],
                "setMembership": [],
            }
            records[entity_id] = record
        if kind != "unknown" and record["kind"] == "unknown":
            record["kind"] = kind
        if category and record["category"] in (None, "unknown"):
            record["category"] = category
        if name:
            for key, value in copy_name(name).items():
                record["name"].setdefault(key, value)
        if properties:
            for key, value in properties.items():
                if value is not None:
                    record["properties"].setdefault(key, value)
        if aliases:
            record["aliases"].extend(value for value in aliases if value)
        if source not in record["sources"]:
            record["sources"].append(source)
        if verification:
            record.setdefault("verificationStates", []).append(verification)
        return record

    for entity in registry["entities"]:
        aliases = []
        for signifier in entity.get("signifiers", []):
            aliases.extend(value for value in signifier.values() if isinstance(value, str))
        ensure(
            entity["id"],
            kind=entity.get("kind", "unknown"),
            category=entity.get("category"),
            name=entity.get("name"),
            source="entity-registry",
            aliases=aliases,
            properties=entity.get("properties"),
        )

    for source_name, catalog in (("location-catalog", locations), ("gap-catalog", gaps)):
        for entity in catalog.get("entities", []):
            ensure(
                entity["id"],
                kind=entity.get("kind", "location"),
                category=entity.get("category", "location"),
                name=entity.get("name"),
                source=source_name,
                aliases=[
                    value for signifier in entity.get("signifiers", [])
                    for value in signifier.values() if isinstance(value, str)
                ],
                properties=entity.get("properties"),
                verification=entity.get("verification"),
            )

    graph_nodes = {node["id"]: node for node in graph["nodes"]}
    incident_edges: Counter[str] = Counter()
    for edge in graph.get("edges", []):
        incident_edges[edge["from"]] += 1
        incident_edges[edge["to"]] += 1

    graph_relations_by_lot: dict[str, list[dict[str, Any]]] = defaultdict(list)
    graph_relations_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in graph.get("relations", []):
        lot = relation.get("lot", {}).get("rowId") if isinstance(relation.get("lot"), dict) else None
        if lot is not None:
            graph_relations_by_lot[str(lot)].append(relation)
        if relation.get("from"):
            graph_relations_by_source[str(relation["from"])].append(relation)

    for node in graph["nodes"]:
        record = ensure(
            node["id"],
            kind=node.get("kind", "other"),
            category=node.get("entityType") or node.get("kind", "other"),
            name={"en": node.get("label") or node["id"]},
            source="graph-v1",
            aliases=[node.get("label"), node.get("region"), node.get("floor")],
        )
        node_summary = summary_node(node, routeable=bool(incident_edges[node["id"]]))
        record["topology"]["graphNodes"].append(node_summary)
        if incident_edges[node["id"]]:
            record["topology"]["status"] = "routeable_anchor"
        elif record["topology"]["status"] == "not_bound":
            record["topology"]["status"] = "semantic_graph_node"

    pickup_by_lot: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for binding in pickups.get("bindings", []):
        lot = str(binding["lot"])
        for position in binding.get("positions", []):
            if not position.get("position"):
                continue
            pickup_by_lot[lot].append({
                "kind": "fixed_pickup",
                "lot": binding["lot"],
                "map": position.get("map"),
                "part": position.get("part"),
                "position": position.get("position"),
                "inChest": position.get("inChest"),
                "treasureName": position.get("treasureName"),
            })

    for relation in acquisitions.get("relations", []):
        lot_id = str((relation.get("lot") or {}).get("rowId"))
        endpoints = []
        endpoint_keys = set()
        explicit_semantic_node_ids = set()
        for endpoint in relation.get("endpointInstances", []):
            key = (
                endpoint.get("kind"), endpoint.get("map"), endpoint.get("part"),
                endpoint.get("npcParamId"), tuple(endpoint.get("position") or []),
            )
            if key not in endpoint_keys:
                endpoint_keys.add(key)
                endpoints.append(endpoint)
            binding = endpoint.get("topologyBinding") or {}
            for node_id in binding.get("routeNodeIds", []):
                if node_id in graph_nodes:
                    explicit_semantic_node_ids.add(node_id)
            for node_id in binding.get("semanticNodeIds", []):
                if node_id in graph_nodes:
                    explicit_semantic_node_ids.add(node_id)
        for endpoint in pickup_by_lot.get(lot_id, []):
            key = (
                endpoint.get("kind"), endpoint.get("map"), endpoint.get("part"),
                endpoint.get("npcParamId"), tuple(endpoint.get("position") or []),
            )
            if key not in endpoint_keys:
                endpoint_keys.add(key)
                endpoints.append(endpoint)
        semantic_node_ids = set(explicit_semantic_node_ids)
        candidate_relations = list(graph_relations_by_lot.get(lot_id, []))
        source_id = relation.get("from")
        if source_id:
            candidate_relations.extend(graph_relations_by_source.get(str(source_id), []))
        for graph_relation in candidate_relations:
            target_id = graph_relation.get("to")
            if target_id in graph_nodes:
                semantic_node_ids.add(target_id)
        route_node_ids = sorted(
            node_id for node_id in semantic_node_ids if incident_edges[node_id]
        )
        semantic_node_ids = sorted(semantic_node_ids)
        if route_node_ids:
            binding_status = "routeable_anchor"
            binding_reason = "获取终点已绑定正式导航节点"
        elif semantic_node_ids:
            binding_status = "semantic_endpoint"
            binding_reason = "获取终点已有语义节点，但尚未绑定正式导航边"
        elif endpoints:
            binding_status = "coordinate_endpoint"
            binding_reason = "已有本地坐标终点，但尚未绑定抽象导航节点"
        else:
            binding_status = "not_bound"
            binding_reason = "已有获取关系，但尚未解析出具体终点"
        topology_binding = {
            "status": binding_status,
            "routeNodeIds": route_node_ids,
            "semanticNodeIds": semantic_node_ids,
            "endpointInstanceCount": len(endpoints),
            "reason": binding_reason,
        }
        compact = compact_acquisition(relation, endpoints, topology_binding)
        for item in relation.get("items", []):
            item_id = item.get("item")
            if not item_id:
                continue
            target = ensure(
                item_id,
                kind="unknown",
                name=item.get("name"),
                source="acquisition-registry",
            )
            target["acquisitions"].append(compact)
            if relation.get("from"):
                source = ensure(relation["from"], source="acquisition-registry")
                source.setdefault("acquisitionTargets", []).append({
                    "relationId": relation["id"],
                    "method": relation.get("method"),
                    "target": item_id,
                })
                if relation.get("method") == "purchase":
                    source.setdefault("shopSales", []).append(compact)

    for relation in reinforce.get("reinforcements", []):
        source = ensure(relation["from"], source="reinforce-catalog")
        target = ensure(relation["to"], source="reinforce-catalog")
        compact = {
            key: relation[key]
            for key in ("id", "method", "to", "from", "level", "maxLevel", "class", "verification", "evidence")
            if key in relation
        }
        source["reinforcementOutgoing"].append(compact)
        target["reinforcementIncoming"].append(compact)

    for armor_set in reinforce.get("armor_sets", []):
        set_record = ensure(
            armor_set["id"],
            kind="armor_set",
            category="armor_set",
            name=armor_set.get("name"),
            source="reinforce-catalog",
        )
        set_record["members"] = armor_set.get("members", [])
        for member in armor_set.get("members", []):
            member_record = ensure(member["item"], source="reinforce-catalog")
            membership = {"set": armor_set["id"], "name": armor_set.get("name")}
            member_record["setMembership"].append(membership)

    for relation in graph.get("relations", []):
        if relation.get("type") not in {"pickup_at", "boss_located_at", "located_in", "set_member"}:
            continue
        from_id = relation.get("from")
        to_id = relation.get("to")
        if from_id not in records or to_id not in records:
            continue
        attached = {
            "id": relation.get("id"),
            "type": relation.get("type"),
            "to" if from_id in records else "from": to_id if from_id in records else from_id,
            "evidence": relation.get("sourceEvidence", []),
        }
        records[from_id]["topology"]["relations"].append(attached)

    for record in records.values():
        record["aliases"] = sorted({alias for alias in record["aliases"] if alias and alias not in record["name"].values()})
        record["sources"] = sorted(set(record["sources"]))
        if record.get("verificationStates"):
            record["verificationStates"] = sorted(set(record["verificationStates"]))
        else:
            record.pop("verificationStates", None)
        record["searchText"] = " ".join(
            [record["id"], *record["name"].values(), *record["aliases"], record.get("category") or ""]
        ).casefold()
        record["counts"] = {
            "acquisitions": len(record["acquisitions"]),
            "shopSales": len(record.get("shopSales", [])),
            "reinforcementOutgoing": len(record["reinforcementOutgoing"]),
            "reinforcementIncoming": len(record["reinforcementIncoming"]),
            "topologyRelations": len(record["topology"]["relations"]),
        }
        record.pop("searchText", None)

    stats = {
        "entityCount": len(records),
        "sourceEntityCount": len(registry["entities"]),
        "locationCount": len(locations.get("entities", [])) + len(gaps.get("entities", [])),
        "acquisitionRelationCount": len(acquisitions.get("relations", [])),
        "reinforcementRelationCount": len(reinforce.get("reinforcements", [])),
        "routeableAnchorCount": sum(record["topology"]["status"] == "routeable_anchor" for record in records.values()),
        "semanticOnlyCount": sum(record["topology"]["status"] == "semantic_graph_node" for record in records.values()),
        "unboundCount": sum(record["topology"]["status"] == "not_bound" for record in records.values()),
        "kindCounts": dict(Counter(record["kind"] for record in records.values())),
        "categoryCounts": dict(Counter(record["category"] for record in records.values())),
    }
    payload = {
        "schema": "elden-ring-player-entity-index@1",
        "builtFrom": [
            "entity-registry", "location-catalog", "gap-catalog",
            "acquisition-registry", "pickup-location-bindings",
            "reinforce-catalog", "graph-v1",
        ],
        "stats": stats,
        "entities": sorted(records.values(), key=lambda record: (record["name"].get("zh", ""), record["id"])),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
