#!/usr/bin/env python3
"""Build independent Boss reward-terminal endpoint bindings.

The boss identity table already binds selected encounter identities to formal
Boss gate nodes.  This builder joins those records to copied MSB enemy
instances, retaining a local body coordinate when available.  The formal gate
is the abstract reward-trigger anchor; the local body is evidence for the same
encounter, not a new navigation edge.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IDENTITY = ROOT / "data" / "v1" / "entities" / "boss-identity-bindings.json"
DEFAULT_SPAWNS = ROOT / "data" / "v1" / "entities" / "enemy-spawn-bindings.json"
DEFAULT_GRAPH = ROOT / "data" / "v1" / "graph-v1.json"
DEFAULT_OUT = ROOT / "data" / "v1" / "entities" / "boss-reward-endpoints.json"


def map_matches(source_map: str | None, local_map: str | None) -> bool:
    if not source_map or not local_map:
        return False
    local_name = Path(local_map).name
    return local_name == source_map or local_name.startswith(f"{source_map}.") or local_name.startswith(f"{source_map}_")


def load_spawns(path: Path) -> dict[str, list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(binding["npcParamId"]): binding.get("instances", [])
        for binding in payload.get("bindings", [])
    }


def build(identity_path: Path, spawn_path: Path, graph_path: Path) -> dict[str, Any]:
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    spawns = load_spawns(spawn_path)
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph_nodes = {node["id"]: node for node in graph.get("nodes", [])}
    endpoints = []
    for record in identity.get("records", []):
        formal_id = record.get("formal_id")
        graph_node = graph_nodes.get(formal_id)
        candidates = [
            instance for instance in spawns.get(str(record.get("npc_param_id")), [])
            if map_matches(record.get("map"), instance.get("map"))
        ]
        local = candidates[0] if candidates else None
        endpoint = {
            "id": f"boss-reward-endpoint-{formal_id}",
            "kind": "boss_reward_endpoint",
            "role": "boss_arena_reward_trigger",
            "bossName": record.get("name"),
            "formalNodeId": formal_id,
            "npcParamId": record.get("npc_param_id"),
            "sourceMap": record.get("map"),
            "endpointStatus": "routeable_anchor" if graph_node else ("coordinate_endpoint" if local else "unbound"),
            "topologyBinding": {
                "status": "routeable_anchor" if graph_node else ("coordinate_endpoint" if local else "not_bound"),
                "routeNodeIds": [formal_id] if graph_node else [],
                "semanticNodeIds": [formal_id] if graph_node else [],
                "reason": "Boss 身份绑定与正式 Boss 门节点共同证明奖励结算锚点"
                if graph_node else "Boss 身份有坐标证据，但尚未找到正式图节点",
            },
            "sourceEvidence": [
                "boss-identity-bindings.json encounter identity record",
                "formal graph Boss gate node" if graph_node else "no formal graph Boss gate node",
            ],
        }
        if local:
            endpoint.update({
                "map": local.get("map"),
                "part": local.get("part"),
                "instanceId": local.get("instanceId"),
                "entityId": local.get("entityId"),
                "position": local.get("position"),
                "mapStudioLayer": local.get("mapStudioLayer"),
            })
            endpoint["sourceEvidence"].append("copied local MSB Boss instance catalog")
        elif graph_node and graph_node.get("onlineCoordinate"):
            online = graph_node["onlineCoordinate"]
            endpoint["map"] = online.get("map")
            endpoint["onlineCoordinate"] = online
        endpoints.append(endpoint)

    payload = {
        "schema": "elden-ring-boss-reward-endpoints@1",
        "builtFrom": {
            "bossIdentityBindings": str(identity_path),
            "enemySpawnBindings": str(spawn_path),
            "graph": str(graph_path),
            "policy": "formal Boss gate is the reward anchor; local Boss body is coordinate evidence",
        },
        "stats": {
            "identityRecords": len(identity.get("records", [])),
            "endpoints": len(endpoints),
            "routeableAnchors": sum(e["endpointStatus"] == "routeable_anchor" for e in endpoints),
            "localSpawnMatches": sum("part" in e for e in endpoints),
            "unbound": sum(e["endpointStatus"] == "unbound" for e in endpoints),
        },
        "endpoints": endpoints,
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity", type=Path, default=DEFAULT_IDENTITY)
    parser.add_argument("--enemy-spawns", type=Path, default=DEFAULT_SPAWNS)
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    payload = build(args.identity, args.enemy_spawns, args.graph)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2))
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
