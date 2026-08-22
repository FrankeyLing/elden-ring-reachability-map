#!/usr/bin/env python3
"""Build the player-facing entity and acquisition query projection.

This is deliberately separate from the route packages. Entity records remain
searchable even when they have no formal route node or topology anchor yet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from topology_map_binding import enrich_endpoint, load_map_index, summarize_endpoint_map_bindings

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "v1"
MESSAGE_REGIONS_FILE = DATA / "entities" / "msb-message-regions.json"
SUMMON_ENDPOINTS_FILE = DATA / "entities" / "summon-endpoints.json"

# Category aliases are search vocabulary, not extra entities.  They keep a
# category query complete when an official display name omits the category
# word, as happens for unique Spirit Ash names such as Lhutel the Headless.
CATEGORY_SEARCH_ALIASES = {
    "spirit_ash": ["骨灰", "Spirit Ash", "Spirit Ashes"],
    "grave_glovewort": ["铃兰", "墓地铃兰", "Grave Glovewort"],
    "ghost_glovewort": ["铃兰", "灵依墓地铃兰", "Ghost Glovewort"],
}

WEAPON_FAMILY_SEARCH_ALIASES = {
    "melee": ["近战", "近戰", "Melee"],
    "bow": ["弓", "弓箭", "Bow"],
    "crossbow": ["弩", "弩箭", "Crossbow"],
    "ballista": ["弩炮", "大弩", "Ballista"],
    "staff": ["法杖", "Staff"],
    "sacred_seal": ["圣印记", "聖印記", "Sacred Seal"],
    "shield": ["盾牌", "盾", "Shield"],
    "torch": ["火把", "Torch"],
    "hand_to_hand": ["徒手", "拳脚", "Hand-to-Hand"],
    "perfume": ["调香瓶武器", "調香瓶武器", "Perfume"],
}


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
            "items", "price", "costType", "stock", "lineupRow", "materialCost",
            "sourceNpcParamRows", "sellerStatus", "merchantShopBinding",
            "sourceItemLotRows", "eventRewardBinding", "talkItemLotBinding",
            "questRewardBinding", "onlineMapMarker", "craftRecipe", "localRecipe",
            "pickupLocationBinding", "pickupEndpointStatus", "initialLoadoutBinding",
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
    messages = load(MESSAGE_REGIONS_FILE)
    summon_endpoints = load(SUMMON_ENDPOINTS_FILE)
    topology_map_index = load_map_index(
        DATA / "entities" / "local-abstract-topology-graph.json"
    )

    records: dict[str, dict[str, Any]] = {}
    entity_aliases: dict[str, str] = dict(registry.get("entityAliases", {}))

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
        aliases.extend(CATEGORY_SEARCH_ALIASES.get(entity.get("category"), []))
        weapon_family = entity.get("properties", {}).get("weaponFamily")
        aliases.extend(WEAPON_FAMILY_SEARCH_ALIASES.get(weapon_family, []))
        if entity.get("category") == "map_fragment":
            aliases.extend(["地图碎片", "地图残片", "Map Fragment"])
        ensure(
            entity["id"],
            kind=entity.get("kind", "unknown"),
            category=entity.get("category"),
            name=entity.get("name"),
            source="entity-registry",
            aliases=aliases,
            properties=entity.get("properties"),
        )

    # Route packages may use a stable semantic target id that predates the
    # canonical parameter-table identity.  Merge only an unambiguous exact
    # official-name match into the canonical entity; keep the route id as an
    # alias so existing route queries remain valid without publishing a second
    # searchable entity.
    canonical_name_ids: dict[str, set[str]] = defaultdict(set)
    for entity in registry["entities"]:
        for value in (entity.get("name") or {}).values():
            if value:
                canonical_name_ids[str(value).casefold()].add(entity["id"])
    graph_entity_ids = {node["id"] for node in graph.get("nodes", [])}
    for node in graph.get("nodes", []):
        if node.get("id") in graph_entity_ids and node.get("kind") not in {"item", "target"}:
            continue
        if node.get("id") in records or node.get("kind") not in {"item", "target"}:
            continue
        candidates = canonical_name_ids.get(str(node.get("label") or "").casefold(), set())
        if len(candidates) == 1:
            canonical_id = next(iter(candidates))
            if canonical_id != node["id"]:
                entity_aliases[node["id"]] = canonical_id

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

    for message in messages.get("messages", []):
        map_name = str(message.get("map") or "unknown_map")
        map_stem = map_name.removesuffix(".msb.dcx")
        region_id = message.get("region_id")
        entity_id = message.get("entity_id")
        message_id = f"message_{map_stem}_region_{region_id}_entity_{entity_id}"
        source_name = str(message.get("name") or "unnamed fixed message")
        record = ensure(
            message_id,
            kind="message",
            category="fixed_message",
            name={
                "en": f"Fixed message · {source_name}",
                "zh": f"固定留言 · {source_name}",
            },
            source="msb-message-regions",
            aliases=[
                "留言",
                "固定留言",
                source_name,
                map_stem,
                f"region {region_id}",
            ],
            properties={
                "messageKind": "fixed_map_message",
                "sourceName": source_name,
                "map": map_name,
                "regionId": region_id,
                "entityId": entity_id,
                "coordinateSpace": "game_world_xyz",
            },
            verification="local_msb_message_region_verified",
        )
        record.setdefault("occurrences", []).append({
            "kind": "fixed_message_endpoint",
            "map": map_name,
            "regionId": region_id,
            "entityId": entity_id,
            "messageName": source_name,
            "position": message.get("position"),
            "coordinateSpace": "game_world_xyz",
            "topologyBinding": {
                "status": "coordinate_endpoint",
                "routeNodeIds": [],
                "semanticNodeIds": [],
                "reason": "local MSB message region coordinate; formal topology anchor not proven",
            },
            "sourceEvidence": [
                "msb-message-regions.json local MSB message region",
                f"map {map_name} region {region_id}",
            ],
        })

    for endpoint in summon_endpoints.get("endpoints", []):
        endpoint_type = str(endpoint.get("endpointType") or "summon_endpoint")
        source_name = str(endpoint.get("sourceName") or endpoint["id"])
        if endpoint_type == "multiplayer_summon_pool":
            zh_name = f"助战召唤池 · {source_name}"
            en_name = f"Multiplayer summon pool · {source_name}"
            aliases = ["助战召唤符", "召唤符", "召唤池", "多人召唤", "SignPool"]
        else:
            zh_name = f"骨灰助战召唤点 · {source_name}"
            en_name = f"Spirit ash summon point · {source_name}"
            aliases = ["助战召唤符", "召唤符", "骨灰召唤", "骨灰召唤点", "BuddySummonPoint"]
        aliases.extend([source_name, endpoint.get("map")])
        record = ensure(
            endpoint["id"],
            kind="summon_endpoint",
            category=endpoint_type,
            name={"en": en_name, "zh": zh_name},
            source="summon-endpoints",
            aliases=[str(value) for value in aliases if value],
            properties={
                "summonEndpointType": endpoint_type,
                "sourceName": source_name,
                "map": endpoint.get("map"),
                "eventId": endpoint.get("eventId"),
                "regionId": endpoint.get("regionId"),
                "signPuddleParamId": endpoint.get("signPuddleParamId"),
                "coordinateSpace": endpoint.get("coordinateSpace"),
            },
            verification="local_mapstudio_summon_endpoint_verified",
        )
        record.setdefault("occurrences", []).append({
            "kind": endpoint_type,
            "map": endpoint.get("map"),
            "mapFile": endpoint.get("mapFile"),
            "eventId": endpoint.get("eventId"),
            "regionId": endpoint.get("regionId"),
            "entityId": endpoint.get("entityId"),
            "summonName": source_name,
            "sourcePart": endpoint.get("sourcePart"),
            "signPuddleParamId": endpoint.get("signPuddleParamId"),
            "shape": endpoint.get("shape"),
            "radius": endpoint.get("radius"),
            "position": endpoint.get("position"),
            "rotation": endpoint.get("rotation"),
            "coordinateSpace": endpoint.get("coordinateSpace"),
            "topologyBinding": endpoint.get("topologyBinding", {
                "status": "coordinate_endpoint",
                "routeNodeIds": [],
                "semanticNodeIds": [],
                "reason": "local summon endpoint coordinate; formal topology anchor not proven",
            }),
            "sourceEvidence": endpoint.get("sourceEvidence", []),
        })

    def source_only_id(gap: dict[str, Any]) -> str:
        method = str(gap.get("method") or "source")
        category = str(
            gap.get("onlineItemMapBroadCategory")
            or gap.get("onlineGuideCategory")
            or gap.get("onlineMapCategory")
            or ""
        ).casefold()
        identity_parts = [
            str(gap.get("externalSourceId") or ""),
            str(gap.get("externalSourceName") or "").casefold(),
            category,
        ]
        if method != "online_item_map":
            identity_parts.insert(0, method)
        identity = "|".join(identity_parts)
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        prefix = (
            "source_only_online_item_map"
            if method == "online_item_map"
            else f"source_only_{method}"
        )
        return f"{prefix}_{digest}"

    source_only_entity_ids: set[str] = set()
    source_only_entity_ids_by_method: dict[str, set[str]] = defaultdict(set)
    for gap in (acquisitions.get("coverageGaps", []) + acquisitions.get("onlineSourceGaps", [])):
        method = str(gap.get("method") or "")
        if method not in {"online_item_map", "online_guide", "online_map"}:
            continue
        source_name = str(gap.get("externalSourceName") or "").strip()
        if not source_name:
            # Empty source names remain in coverageGaps, but cannot produce a
            # useful search record.  This is intentionally not a guessed name.
            continue
        status = str(gap.get("status") or "source_item_unmatched")
        entity_id = source_only_id(gap)
        source_only_entity_ids.add(entity_id)
        source_only_entity_ids_by_method[method].add(entity_id)
        broad_category = str(
            gap.get("onlineItemMapBroadCategory")
            or gap.get("onlineGuideCategory")
            or gap.get("onlineMapCategory")
            or ""
        )
        if method == "online_item_map":
            entity_kind = "external_item_reference"
            entity_category = "online_item_map_source_only"
            verification = "online_item_map_source_only_unresolved"
        elif method == "online_guide":
            entity_kind = "external_item_reference"
            entity_category = "online_guide_source_only"
            verification = "online_guide_source_only_unresolved"
        else:
            entity_kind = "external_map_reference"
            entity_category = "online_map_source_only"
            verification = "online_map_source_only_unresolved"
        record = ensure(
            entity_id,
            kind=entity_kind,
            category=entity_category,
            name={"en": source_name},
            source="acquisition-registry",
            aliases=[
                str(gap.get("externalSourceId"))
                if gap.get("externalSourceId") is not None else None,
                broad_category,
            ],
            properties={
                "formalEntity": False,
                "sourceOnly": True,
                "sourceStatus": status,
                "sourceMethod": method,
                "sourceItemId": gap.get("externalSourceId"),
                "sourceCategory": broad_category,
            },
            verification=verification,
        )
        record["properties"]["sourceOccurrenceCount"] = (
            record["properties"].get("sourceOccurrenceCount", 0) + 1
        )
        endpoint_instances = gap.get("endpointInstances", [])
        topology_status = "coordinate_endpoint" if endpoint_instances else "not_bound"
        if method == "online_item_map":
            source_item = {
                "name": {"en": source_name},
                "externalSourceId": gap.get("externalSourceId"),
                "externalSourceName": source_name,
                "sourceOnly": True,
                "sourceStatus": status,
                "onlineItemMapCategory": gap.get("onlineItemMapCategory"),
                "onlineItemMapBroadCategory": gap.get("onlineItemMapBroadCategory"),
                "onlineItemMapSubCategory": gap.get("onlineItemMapSubCategory"),
            }
        elif method == "online_guide":
            source_item = {
                "name": {"en": source_name},
                "externalSourceId": gap.get("externalSourceId"),
                "externalSourceName": source_name,
                "sourceOnly": True,
                "sourceStatus": status,
                "onlineGuideCategory": gap.get("onlineGuideCategory"),
                "onlineGuideDescription": gap.get("onlineGuideDescription"),
                "onlineGuideMissable": gap.get("onlineGuideMissable"),
                "onlineGuideQuest": gap.get("onlineGuideQuest"),
                "onlineGuideWikiUrl": gap.get("onlineGuideWikiUrl"),
            }
        else:
            source_item = {
                "name": {"en": source_name},
                "externalSourceId": gap.get("externalSourceId"),
                "externalSourceName": source_name,
                "sourceOnly": True,
                "sourceStatus": status,
                "onlineMapCategory": gap.get("onlineMapCategory"),
                "onlineMapDescription": gap.get("onlineMapDescription"),
                "onlineMapMaster": gap.get("onlineMapMaster"),
            }
        source_evidence = {
            "id": gap["id"],
            "from": None,
            "method": method,
            "items": [source_item],
            "endpointInstances": endpoint_instances,
            "topologyBinding": {
                "status": topology_status,
                "routeNodeIds": [],
                "semanticNodeIds": [],
                "endpointInstanceCount": len(endpoint_instances),
                "reason": (
                    "source-only coordinate evidence; canonical identity unresolved"
                    if endpoint_instances
                    else "source-only acquisition text; source map endpoint absent or invalid"
                ),
            },
            "sourceGapStatus": status,
            "sourceCoverageGapId": gap["id"],
            "evidence": gap.get("evidence", []),
            "verification": verification,
        }
        if method == "online_map":
            record.setdefault("occurrences", []).append({
                "kind": "online_map_marker",
                "sourceOnly": True,
                "sourceStatus": status,
                "sourceCoverageGapId": gap["id"],
                "markerId": gap.get("externalSourceId"),
                "category": gap.get("onlineMapCategory"),
                "description": gap.get("onlineMapDescription"),
                "mapMaster": gap.get("onlineMapMaster"),
                "pixelPosition": gap.get("onlineMapPixelPosition"),
                "endpointInstances": endpoint_instances,
                "evidence": gap.get("evidence", []),
            })
        else:
            record["acquisitions"].append(source_evidence)

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
            source_id = entity_aliases.get(str(relation["from"]), str(relation["from"]))
            graph_relations_by_source[source_id].append(relation)

    for node in graph["nodes"]:
        record_id = entity_aliases.get(node["id"], node["id"])
        record = ensure(
            record_id,
            kind=node.get("kind", "other"),
            category=node.get("entityType") or node.get("kind", "other"),
            name={"en": node.get("label") or node["id"]},
            source="graph-v1",
            aliases=[node.get("label"), node.get("region"), node.get("floor")],
        )
        node_summary = summary_node(node, routeable=bool(incident_edges[node["id"]]))
        record["topology"]["graphNodes"].append(node_summary)
        if record_id != node["id"]:
            record["aliases"].append(node["id"])
            record.setdefault("properties", {}).setdefault("graphNodeAliases", []).append(node["id"])
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
        for endpoint in endpoints:
            enrich_endpoint(endpoint, topology_map_index)
        topology_binding.update(summarize_endpoint_map_bindings(endpoints))
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
        record_from_id = entity_aliases.get(from_id, from_id)
        if record_from_id not in records or to_id not in records:
            continue
        attached = {
            "id": relation.get("id"),
            "type": relation.get("type"),
            "to" if from_id in records else "from": to_id if from_id in records else from_id,
            "evidence": relation.get("sourceEvidence", []),
        }
        records[record_from_id]["topology"]["relations"].append(attached)

    # Enrich occurrences and source-only endpoints as well as acquisition
    # endpoints.  Pickup bindings that are joined from the independent pickup
    # snapshot enter here, so they receive the same exact map/layer evidence
    # without becoming route edges.
    for record in records.values():
        for occurrence in record.get("occurrences", []):
            enrich_endpoint(occurrence, topology_map_index)
            for endpoint in occurrence.get("endpointInstances", []):
                enrich_endpoint(endpoint, topology_map_index)
        for acquisition in record.get("acquisitions", []):
            endpoints = acquisition.get("endpointInstances", [])
            for endpoint in endpoints:
                enrich_endpoint(endpoint, topology_map_index)
            acquisition.setdefault("topologyBinding", {}).update(
                summarize_endpoint_map_bindings(endpoints)
            )
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
            "occurrences": len(record.get("occurrences", [])),
            "reinforcementOutgoing": len(record["reinforcementOutgoing"]),
            "reinforcementIncoming": len(record["reinforcementIncoming"]),
            "topologyRelations": len(record["topology"]["relations"]),
        }
        record.pop("searchText", None)

    stats = {
        "entityCount": len(records),
        "sourceEntityCount": len(registry["entities"]),
        "entityAliasCount": len(entity_aliases),
        "sourceOnlyEntityCount": len(source_only_entity_ids),
        "sourceOnlyAcquisitionCount": sum(
            len(records[entity_id]["acquisitions"])
            for entity_id in source_only_entity_ids
        ),
        "sourceOnlyEntityCounts": {
            method: len(entity_ids)
            for method, entity_ids in sorted(source_only_entity_ids_by_method.items())
        },
        "sourceOnlyAcquisitionCounts": {
            method: sum(
                len(records[entity_id]["acquisitions"])
                for entity_id in entity_ids
            )
            for method, entity_ids in sorted(source_only_entity_ids_by_method.items())
        },
        "sourceOnlyOccurrenceCounts": {
            method: sum(
                len(records[entity_id].get("occurrences", []))
                for entity_id in entity_ids
            )
            for method, entity_ids in sorted(source_only_entity_ids_by_method.items())
        },
        "locationCount": len(locations.get("entities", [])) + len(gaps.get("entities", [])),
        "acquisitionRelationCount": len(acquisitions.get("relations", [])),
        "reinforcementRelationCount": len(reinforce.get("reinforcements", [])),
        "routeableAnchorCount": sum(record["topology"]["status"] == "routeable_anchor" for record in records.values()),
        "semanticOnlyCount": sum(record["topology"]["status"] == "semantic_graph_node" for record in records.values()),
        "unboundCount": sum(record["topology"]["status"] == "not_bound" for record in records.values()),
        "kindCounts": dict(Counter(record["kind"] for record in records.values())),
        "categoryCounts": dict(Counter(record["category"] for record in records.values())),
        "weaponFamilyCounts": dict(Counter(
            record.get("properties", {}).get("weaponFamily")
            for record in records.values()
            if record.get("properties", {}).get("weaponFamily")
        )),
        "messageOccurrenceCount": sum(
            len(record.get("occurrences", []))
            for record in records.values()
            if record.get("kind") == "message"
        ),
        "summonEndpointOccurrenceCount": sum(
            len(record.get("occurrences", []))
            for record in records.values()
            if record.get("kind") == "summon_endpoint"
        ),
        "multiplayerSummonPoolCount": sum(
            1 for endpoint in summon_endpoints.get("endpoints", [])
            if endpoint.get("endpointType") == "multiplayer_summon_pool"
        ),
        "spiritAshSummonPointCount": sum(
            1 for endpoint in summon_endpoints.get("endpoints", [])
            if endpoint.get("endpointType") == "spirit_ash_summon_point"
        ),
    }
    acquisition_stats = acquisitions.get("stats", {})
    stats["acquisitionCoverage"] = {
        "drop": {
            key: value for key, value in acquisition_stats.items()
            if key.startswith("drop")
        },
        "pickup": {
            key: value for key, value in acquisition_stats.items()
            if key.startswith("pickup")
        },
        "shop": {
            key: value for key, value in acquisition_stats.items()
            if key.startswith("shop")
        },
        "coverageGapCount": len(acquisitions.get("coverageGaps", [])),
        "sourceExclusionCount": len(acquisitions.get("sourceExclusions", [])),
    }
    stats["topologyMapBinding"] = {
        key: value
        for key, value in acquisition_stats.items()
        if key.startswith("topologyMap")
    }
    payload = {
        "schema": "elden-ring-player-entity-index@1",
        "builtFrom": [
            "entity-registry", "location-catalog", "gap-catalog",
            "acquisition-registry", "pickup-location-bindings",
            "reinforce-catalog", "graph-v1",
            "msb-message-regions",
        "summon-endpoints",
            "local-abstract-topology-graph",
        ],
        "entityAliases": entity_aliases,
        "stats": stats,
        "coverageGaps": acquisitions.get("coverageGaps", []),
        "onlineSourceGaps": acquisitions.get("onlineSourceGaps", []),
        "verifiedNoDropFacts": acquisitions.get("verifiedNoDropFacts", []),
        "verifiedUnusedMapLotFacts": acquisitions.get("verifiedUnusedMapLotFacts", []),
        "sellerUnresolvedRecords": acquisitions.get("sellerUnresolvedRecords", []),
        "serviceMenuRecords": acquisitions.get("serviceMenuRecords", []),
        "testShopRowRecords": acquisitions.get("testShopRowRecords", []),
        "sourceExclusions": acquisitions.get("sourceExclusions", []),
        "entities": sorted(records.values(), key=lambda record: (record["name"].get("zh", ""), record["id"])),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
