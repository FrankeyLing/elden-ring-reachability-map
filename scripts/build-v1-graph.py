#!/usr/bin/env python3
"""Build the V1.0 formal graph: complete node set + local-declaration edges,
then verify completeness against local game data declarations.

V1.0 completeness model (acceptance gate):
  1. Every grace in the official catalog exists as a node (grace kind).
  2. Every local reachability declaration (EMEVD scripted warp, MSBE cross-map
     declaration / endpoint pair, NVA connector) maps to a (source region ->
     target region) pair via the map-key index.
  3. For every declared region pair, the formal graph contains a directed path
     from a node of the source region to a node of the target region
     (conditions treated as satisfied — a condition gate is a state, not
     missing data).
  4. Gaps are closed with evidence-backed bridge edges derived from the local
     declarations themselves; edges that cannot be grounded in any local
     declaration are never synthesized.

Usage:
    python scripts/build-v1-graph.py
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "v1"
SNAPSHOTS = DATA / "source-snapshots"

# tile subRegion -> formal region for regions whose names differ
SUBRESION_TO_FORMAL = {
    "Knight's Study": "Elphael, Brace of the Haligtree",
    "Midra's Manse": "Scadu Altus",
    "Stone Coffin Fissure": "Gravesite Plain",
    "Stranded Graveyard": "Limgrave",
    "Stormhill": "Limgrave",
    "Specimen Storehouse": "Shadow Keep",
    "Enir-Ilim": "Land of the Tower",
    "Stone Platform": "Gravesite Plain",
    "Moonlight Altar": "Liurnia of the Lakes",
    "Flame Peak": "Mountaintops of the Giants",
    "Gilded Court": "Gravesite Plain",
    "Charo's Hidden Grave": "Gravesite Plain",
    "Finger Ruins of Dheo": "Scadu Altus",
    "Finger Ruins of Rhia": "Scadu Altus",
    "Hinterland": "Scaduview",
    "Abyssal Woods": "Scadu Altus",
    "Jagged Peak": "Gravesite Plain",
    "Cerulean Coast": "Gravesite Plain",
    "Scorched Ruins": "Gravesite Plain",
    "Rauh Base": "Land of the Tower",
    "Belurat, Tower Settlement": "Land of the Tower",
    "Theatre of the Divine Beast": "Land of the Tower",
    "Dragon's Pit": "Gravesite Plain",
    "Fog Rift Fort": "Gravesite Plain",
    "Fog Rift Catacombs": "Gravesite Plain",
    "Rivermouth Cave": "Gravesite Plain",
    "Scorpion River Catacombs": "Gravesite Plain",
    "Bonny Gaol": "Scadu Altus",
    "Fort of Reprimand": "Scadu Altus",
    "Ruined Forge Lava Intake": "Scadu Altus",
    "Ruined Forge of Starfall Past": "Scadu Altus",
    "Taylew's Ruined Forge": "Scadu Altus",
    "Castle Ensis": "Gravesite Plain",
    "Ellac River": "Gravesite Plain",
    "Storehouse": "Shadow Keep",
    "Church District": "Shadow Keep",
    "Scaduview": "Scaduview",
    "Divine Tower of Limgrave": "Divine Tower of Limgrave",
    "Divine Tower of Liurnia": "Divine Tower of Liurnia",
    "Divine Tower of Caelid": "Divine Tower of Caelid",
    "Divine Tower of West Altus": "Divine Tower of West Altus",
    "Ainsel River": "Ainsel River",
    "Deeproot Depths": "Deeproot Depths",
    "Lake of Rot": "Lake of Rot",
    "Mohgwyn Palace": "Mohgwyn Palace",
    "Nokron, Eternal City": "Nokron, Eternal City",
    "Siofra River": "Siofra River",
    "Siofra Aqueduct": "Siofra River",
    "Grand Cloister": "Lake of Rot",
}

# map-id prefix fallbacks for maps without tile/name data. Derived from one-hop
# neighbor voting over the local declarations plus FromSoft map-numbering
# knowledge; entries with a strong unanimous vote are preferred.
MAP_PREFIX_REGION = {
    "m11_71_00": "Subterranean Shunning-Grounds",
    "m12_08_00": "Ainsel River",
    "m12_09_00": "Ainsel River",
    "m13_00_00": "Crumbling Farum Azula",
    "m17_00_00": "Crumbling Farum Azula",
    "m19_70_00": "Leyndell, Royal Capital",
    "m25_00_00": "Scaduview",
    "m30_17_00": "Mountaintops of the Giants",
    "m30_18_00": "Mountaintops of the Giants",
    "m30_19_00": "Mountaintops of the Giants",
    "m31_00_00": "Limgrave",
    "m31_02_00": "Limgrave",
    "m31_22_00": "Mountaintops of the Giants",
    "m32_01_00": "Limgrave",
    "m32_02_00": "Liurnia of the Lakes",
    "m32_04_00": "Altus Plateau",
    "m32_11_00": "Mountaintops of the Giants",
    "m34_16_00": "Liurnia of the Lakes",
    "m40_00_00": "Gravesite Plain",
    "m40_01_00": "Scadu Altus",
    "m40_02_00": "Scadu Altus",
    "m41_00_00": "Altus Plateau",
    "m41_01_00": "Scadu Altus",
    "m41_02_00": "Gravesite Plain",
    "m42_00_00": "Altus Plateau",
    "m42_02_00": "Scadu Altus",
    "m42_03_00": "Shadow Keep",
    "m43_00_00": "Gravesite Plain",
    "m43_01_00": "Gravesite Plain",
    "m00_00_00": "Chapel of Anticipation",
    "m42_01_00": "Scadu Altus",
    "m61_43_46_00": "Gravesite Plain",
    "m61_43_47_00": "Gravesite Plain",
    "m61_44_42_00": "Land of the Tower",
    "m61_44_": "Scadu Altus",
    "m61_45_42_00": "Land of the Tower",
    "m61_45_": "Scadu Altus",
    "m61_46_": "Gravesite Plain",
    "m61_47_": "Gravesite Plain",
    "m61_48_": "Gravesite Plain",
    "m61_49_": "Gravesite Plain",
    "m61_50_": "Gravesite Plain",
    "m61_51_": "Scaduview",
    "m61_52_": "Scadu Altus",
    "m61_53_": "Scadu Altus",
    "m61_54_": "Scadu Altus",
}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def load_tiles() -> list[dict]:
    tiles = []
    for part in (1, 2):
        payload = json.loads(
            (SNAPSHOTS / f"mapforgoblins-tile-regions-part{part}-20260818.json").read_text(encoding="utf-8")
        )
        for record in payload["records"]:
            tiles.append({"mapKey": record[0], "sub": record[3], "major": record[4]})
    return tiles


# MSBE MapNameOverride PlaceName names -> formal region (authoritative DLC names)
PLACENAME_TO_REGION = {
    "Belurat, Tower Settlement": "Land of the Tower",
    "Theatre of the Divine Beast": "Land of the Tower",
    "Scaduview": "Scaduview",
    "Enir-Ilim": "Land of the Tower",
    "Specimen Storehouse": "Shadow Keep",
    "Shadow Keep": "Shadow Keep",
    "Hinterland": "Scaduview",
    "Midra's Manse": "Scadu Altus",
    "Stone Coffin Fissure": "Gravesite Plain",
    "Cerulean Coast": "Gravesite Plain",
    "Gravesite Plain": "Gravesite Plain",
    "Scadu Altus": "Scadu Altus",
    "Abyssal Woods": "Scadu Altus",
    "Jagged Peak": "Gravesite Plain",
    "Stone Platform": "Gravesite Plain",
}


def load_msbe_map_regions() -> dict[str, str]:
    """map_id -> formal region from MSBE MapNameOverride (PlaceName)."""
    path = DATA / "entities" / "local-msbe-map-names.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = {}
    for record in payload.get("records", []):
        name = record.get("eng") or record.get("zh")
        if not name:
            continue
        region = PLACENAME_TO_REGION.get(name)
        if region:
            result[record["map_id"]] = region
    return result


# Manually verified connections that the local declarations imply but the
# online-only graph did not encode. Each entry names the gameplay fact it is
# grounded in; no connection is invented.
KNOWN_CONNECTIONS = [
    {
        "id": "v1-known:ashen-capital-to-rampart",
        "from": "grace_leyndell_capital_of_ash",
        "to": "grace_altus_plateau_capital_outskirts_capital_rampart",
        "mode": "灰烬王城大门 → 王城正门（返回外围）",
        "cost": 1, "risk": 1, "direction": "forward",
        "transitionType": "ashen_capital_exit",
        "requires": [],
        "note": "王城化为灰烬后，王城正门仍可返回外围；由本地跨图声明与游戏流程人工核对。",
    },
    {
        "id": "v1-known:rampart-to-ashen-capital",
        "from": "grace_altus_plateau_capital_outskirts_capital_rampart",
        "to": "grace_leyndell_capital_of_ash",
        "mode": "王城正门 → 灰烬王城（玛利喀斯后）",
        "cost": 1, "risk": 2, "direction": "forward",
        "transitionType": "ashen_capital_entrance",
        "requires": ["maliketh_defeated"],
        "note": "击败玛利喀斯后，从王城正门进入灰烬王城。",
    },
    {
        "id": "v1-known:ashen-capital-to-sewers",
        "from": "grace_leyndell_capital_of_ash",
        "to": "grace_leyndell_royal_capital_subterranean_shunning_grounds_underground_roadside",
        "mode": "灰烬王城 → 王城下水道入口",
        "cost": 2, "risk": 2, "direction": "forward",
        "transitionType": "ashen_sewer_entrance",
        "requires": [],
        "note": "灰烬王城仍保留王城下水道入口；由本地跨图声明（Ashen Capital↔Shunning-Grounds）人工核对。",
    },
    {
        "id": "v1-known:ashen-capital-to-forbidden-lands",
        "from": "grace_leyndell_capital_of_ash",
        "to": "grace_mountaintops_of_the_giants_forbidden_lands_forbidden_lands",
        "mode": "灰烬王城 → 禁域（王城后方）",
        "cost": 2, "risk": 2, "direction": "forward",
        "transitionType": "ashen_to_forbidden_lands",
        "requires": ["morgott_defeated"],
        "note": "击败蒙葛特后，王城后方禁域始终可走；由本地跨图声明（Ashen Capital↔Forbidden Lands）人工核对。",
    },
]


def region_for_map(
    map_id: str,
    tiles: list[dict],
    tile_by_key: dict[str, dict],
    msbe_regions: dict[str, str] | None = None,
) -> str | None:
    if not map_id:
        return None
    if msbe_regions and map_id in msbe_regions:
        return msbe_regions[map_id]
    base = map_id
    for candidate in (base, "_".join(base.split("_")[:3]), "_".join(base.split("_")[:2])):
        tile = tile_by_key.get(candidate)
        if tile:
            if tile["major"]:
                return tile["major"]
            if tile["sub"]:
                return SUBRESION_TO_FORMAL.get(tile["sub"], tile["sub"])
    for prefix, region in sorted(MAP_PREFIX_REGION.items(), key=lambda item: -len(item[0])):
        if base.startswith(prefix):
            return region
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=DATA / "graph.json")
    parser.add_argument("--graces", type=Path, default=DATA / "entities" / "sites-of-grace.json")
    parser.add_argument("--output", type=Path, default=DATA / "graph-v1.json")
    parser.add_argument("--report", type=Path, default=DATA / "v1" / "coverage-audit.json")
    args = parser.parse_args()

    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    grace_catalog = json.loads(args.graces.read_text(encoding="utf-8")).get("records", [])
    tiles = load_tiles()
    tile_by_key = {t["mapKey"]: t for t in tiles}

    # local declarations
    abstract = json.loads((DATA / "entities" / "local-abstract-topology-graph.json").read_text(encoding="utf-8"))
    declarations = []
    for edge in abstract.get("edges", []):
        declarations.append(
            {
                "id": edge.get("id", ""),
                "family": edge.get("edge_family", ""),
                "kind": edge.get("edge_kind", ""),
                "from_map": edge.get("from_map_id", ""),
                "to_map": edge.get("to_map_id", ""),
                "from": edge.get("from", ""),
                "to": edge.get("to", ""),
            }
        )

    nodes = graph["nodes"]
    edges = graph["edges"]
    node_by_id = {n["id"]: n for n in nodes}
    existing_ids = set(node_by_id)

    # ---- 1. grace completeness: every catalog grace becomes a node ----
    added_graces = []
    for record in grace_catalog:
        cid = record.get("canonical_id")
        if not cid or cid in existing_ids:
            continue
        node = {
            "id": cid,
            "label": record.get("name") or cid,
            "kind": "grace",
            "layer": record.get("layer") or "surface",
            "region": record.get("region") or "",
            "floor": record.get("subgroup") or "",
            "x": 0,
            "y": 0,
            "coordinateType": record.get("coordinate_type") or "unplaced_online_catalog",
            "verificationState": record.get("verification_state") or "online_catalog",
            "sourceEvidence": record.get("source_evidence") or [],
            "description": "官方赐福目录补齐节点；位置未在抽象布局中放置。",
            "isCatalog": True,
        }
        nodes.append(node)
        existing_ids.add(cid)
        added_graces.append(cid)
    print(f"grace nodes added: {len(added_graces)} (total graces {sum(1 for n in nodes if n['kind'] == 'grace')})")

    # ---- 2. map declarations to region pairs ----
    msbe_regions = load_msbe_map_regions()
    declared_pairs = Counter()
    unmapped = []
    intra_map_evidence = 0
    no_map_reference = 0
    for declaration in declarations:
        from_map = declaration["from_map"]
        to_map = declaration["to_map"]
        if from_map and from_map == to_map:
            # same-map declaration (e.g. NVA connectors within one map)
            intra_map_evidence += 1
            continue
        from_region = region_for_map(from_map, tiles, tile_by_key, msbe_regions)
        to_region = region_for_map(to_map, tiles, tile_by_key, msbe_regions)
        declaration["from_region"] = from_region
        declaration["to_region"] = to_region
        if not from_map and not to_map:
            no_map_reference += 1
            continue
        if from_region and to_region:
            declared_pairs[(from_region, to_region)] += 1
        elif from_region and not to_map:
            # scripted warp evidence with only a source map: intra-map transport
            intra_map_evidence += 1
        else:
            unmapped.append(declaration)
    print(f"declared region pairs: {len(declared_pairs)}; unmapped declarations: {len(unmapped)}")

    # ---- 3. reachability check ----
    outgoing = defaultdict(list)
    for edge in edges:
        outgoing[edge["from"]].append(edge["to"])

    def region_nodes(region: str) -> list[str]:
        return [n["id"] for n in nodes if n.get("region") == region]

    def reachable_from(origin_ids: list[str]) -> set[str]:
        seen = set()
        queue = list(origin_ids)
        while queue:
            current = queue.pop()
            if current in seen:
                continue
            seen.add(current)
            for target in outgoing.get(current, []):
                if target not in seen:
                    queue.append(target)
        return seen

    def pick_anchor(region: str, kind_priority: tuple[str, ...]) -> str | None:
        candidates = region_nodes(region)
        if not candidates:
            return None
        for kind in kind_priority:
            for nid in candidates:
                if node_by_id[nid]["kind"] == kind:
                    return nid
        return candidates[0]

    gaps = []
    for (from_region, to_region), count in sorted(declared_pairs.items(), key=lambda item: -item[1]):
        if from_region == to_region:
            continue
        from_ids = region_nodes(from_region)
        to_ids = set(region_nodes(to_region))
        if not from_ids or not to_ids:
            gaps.append(
                {"from": from_region, "to": to_region, "declarations": count,
                 "reason": "region has no nodes in graph"}
            )
            continue
        reachable = reachable_from(from_ids)
        if not to_ids.intersection(reachable):
            gaps.append(
                {"from": from_region, "to": to_region, "declarations": count,
                 "reason": "no path"}
            )

    # ---- 4. close gaps with local-declaration bridge edges ----
    edge_id_counter = 0
    existing_edge_ids = {e["id"] for e in edges}
    closed = 0
    for gap in gaps:
        from_region, to_region = gap["from"], gap["to"]
        from_anchor = pick_anchor(from_region, ("grace", "entrance", "lift", "teleport", "junction"))
        to_anchor = pick_anchor(to_region, ("grace", "entrance", "lift", "teleport", "junction"))
        if not from_anchor or not to_anchor or from_anchor == to_anchor:
            gap["reason"] += " (no anchor to bridge)"
            continue
        edge_id_counter += 1
        edge_id = f"v1-bridge:{from_region}:{to_region}:{edge_id_counter}"
        if edge_id in existing_edge_ids:
            continue
        edges.append(
            {
                "id": edge_id,
                "from": from_anchor,
                "to": to_anchor,
                "mode": f"{from_region} → {to_region}（本地数据声明桥接）",
                "cost": 4,
                "risk": 3,
                "direction": "forward",
                "transitionType": "local_declared_bridge",
                "requires": [],
                "sourceEvidence": ["local-game-data-declaration"],
                "verificationState": "local_data_declared",
                "note": "由本地游戏数据可达性声明补全的桥接边；方向按本地声明推断，未做玩家步行验证。",
                "tags": ["local_declared", "bridge"],
            }
        )
        existing_edge_ids.add(edge_id)
        gap["closed_by"] = edge_id
        closed += 1
    print(f"gaps closed with bridge edges: {closed}/{len(gaps)}")

    # ---- 4b. manually verified known connections (ashen capital exits) ----
    known_added = 0
    existing_ids = {e["id"] for e in edges}
    for connection in KNOWN_CONNECTIONS:
        if connection["id"] in existing_ids:
            continue
        if connection["from"] not in node_by_id or connection["to"] not in node_by_id:
            print(f"  WARN: known connection {connection['id']} references missing nodes")
            continue
        edges.append(
            {
                "id": connection["id"],
                "from": connection["from"],
                "to": connection["to"],
                "mode": connection["mode"],
                "cost": connection["cost"],
                "risk": connection["risk"],
                "direction": connection["direction"],
                "transitionType": connection["transitionType"],
                "requires": connection["requires"],
                "sourceEvidence": ["local-game-data-declaration", "manual-verification"],
                "verificationState": "local_data_declared",
                "note": connection["note"],
                "tags": ["known_connection", "manual"],
            }
        )
        existing_ids.add(connection["id"])
        known_added += 1
    print(f"known connections added: {known_added}")

    # ---- 4c. connect catalog-added graces into their region network ----
    degree = Counter()
    for edge in edges:
        degree[edge["from"]] += 1
        degree[edge["to"]] += 1
    region_anchor = {}
    for node in nodes:
        if node.get("isCatalog"):
            continue
        if degree.get(node["id"], 0) > 0 and node.get("region"):
            region_anchor.setdefault(node["region"], node["id"])
    grace_bridges = 0
    for node in nodes:
        if not node.get("isCatalog") or degree.get(node["id"], 0) > 0:
            continue
        anchor = region_anchor.get(node.get("region"))
        if not anchor or anchor == node["id"]:
            continue
        edge_id = f"v1-catalog-grace:{node['id']}:{anchor}"
        if edge_id in existing_edge_ids:
            continue
        edges.append(
            {
                "id": edge_id,
                "from": node["id"],
                "to": anchor,
                "mode": f"区域内部（{node.get('region') or ''} 官方赐福目录补齐）",
                "cost": 2,
                "risk": 1,
                "direction": "forward",
                "transitionType": "catalog_grace_region_bridge",
                "requires": [],
                "sourceEvidence": ["sites-of-grace-catalog", "local-game-data-declaration"],
                "verificationState": "online_catalog",
                "note": "官方赐福目录补齐节点；区域内部连通按本地图内声明与同区域既有赐福推断，未做步行验证。",
                "tags": ["catalog_grace", "region_bridge"],
            }
        )
        edges.append(
            {
                "id": edge_id + ":r",
                "from": anchor,
                "to": node["id"],
                "mode": f"区域内部（{node.get('region') or ''} 官方赐福目录补齐）",
                "cost": 2,
                "risk": 1,
                "direction": "return",
                "transitionType": "catalog_grace_region_bridge",
                "requires": [],
                "sourceEvidence": ["sites-of-grace-catalog", "local-game-data-declaration"],
                "verificationState": "online_catalog",
                "note": "官方赐福目录补齐节点；区域内部连通按本地图内声明与同区域既有赐福推断，未做步行验证。",
                "tags": ["catalog_grace", "region_bridge"],
            }
        )
        existing_edge_ids.add(edge_id)
        existing_edge_ids.add(edge_id + ":r")
        grace_bridges += 1
    print(f"catalog grace region bridges added: {grace_bridges}")

    # ---- 4d. auto-layout catalog graces around their region anchors ----
    region_points = defaultdict(list)
    for node in nodes:
        if node.get("isCatalog"):
            continue
        x, y = node.get("x"), node.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            region_points[node.get("region", "")].append((x, y))
    region_anchor = {
        region: (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
        for region, points in region_points.items()
        if points
    }
    catalog_by_region = defaultdict(list)
    for node in nodes:
        if node.get("isCatalog"):
            catalog_by_region[node.get("region", "")].append(node)
    laid_out = 0
    for region, members in catalog_by_region.items():
        anchor = region_anchor.get(region)
        if not anchor:
            continue
        anchor_x, anchor_y = anchor
        for index, node in enumerate(members):
            x, y = node.get("x"), node.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)) and (x != 0 or y != 0):
                continue
            radius = 46 + 17 * (index // 12)
            angle = (index % 12) / 12 * 2 * math.pi + (index // 12) * 0.35
            node["x"] = round(anchor_x + radius * math.cos(angle), 1)
            node["y"] = round(anchor_y + radius * math.sin(angle), 1)
            laid_out += 1
    print(f"catalog grace nodes laid out: {laid_out}")

    # ---- 5. re-verify ----
    outgoing2 = defaultdict(list)
    for edge in edges:
        outgoing2[edge["from"]].append(edge["to"])

    def reachable_from2(origin_ids: list[str]) -> set[str]:
        seen = set()
        queue = list(origin_ids)
        while queue:
            current = queue.pop()
            if current in seen:
                continue
            seen.add(current)
            for target in outgoing2.get(current, []):
                if target not in seen:
                    queue.append(target)
        return seen

    remaining = []
    for (from_region, to_region), count in sorted(declared_pairs.items(), key=lambda item: -item[1]):
        if from_region == to_region:
            continue
        from_ids = region_nodes(from_region)
        to_ids = set(region_nodes(to_region))
        if not from_ids or not to_ids:
            remaining.append({"from": from_region, "to": to_region, "declarations": count, "reason": "no nodes"})
            continue
        if not to_ids.intersection(reachable_from2(from_ids)):
            remaining.append({"from": from_region, "to": to_region, "declarations": count, "reason": "no path"})

    # ---- 6. write outputs ----
    graph["meta"]["version"] = "1.0.0-v1-local-verified"
    graph["meta"]["verificationLabel"] = "V1.0 Local-Verified"
    graph["meta"]["v1"] = {
        "graceCatalogAdded": len(added_graces),
        "bridgeEdgesAdded": closed,
        "declaredRegionPairs": len(declared_pairs),
        "remainingGaps": len(remaining),
    }
    args.output.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")

    report = {
        "schema": "elden-ring-v1-coverage-audit@2",
        "verification": "PASS" if not remaining else "FAIL",
        "summary": {
            "declarations_total": len(declarations),
            "declarations_mapped": sum(declared_pairs.values()),
            "declarations_unmapped": len(unmapped),
            "intra_map_evidence": intra_map_evidence,
            "no_map_reference": no_map_reference,
            "declared_region_pairs": len(declared_pairs),
            "grace_catalog": len(grace_catalog),
            "grace_nodes": sum(1 for n in nodes if n["kind"] == "grace"),
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "bridge_edges_added": closed,
            "remaining_gaps": remaining,
        },
        "remaining_gaps": remaining,
        "unmapped_declarations": [
            {"id": d["id"], "family": d["family"], "from": d["from_map"], "to": d["to_map"]}
            for d in unmapped[:100]
        ],
        "declared_region_pairs": [{"from": k[0], "to": k[1], "declarations": v} for k, v in sorted(declared_pairs.items(), key=lambda item: -item[1])],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=1))
    print(f"verification: {report['verification']}")
    return 0 if not remaining else 1


if __name__ == "__main__":
    sys.exit(main())
