#!/usr/bin/env python3
"""Compile explicit MSB map connections into an abstract topology index.

This is deliberately not a navmesh or continuous walkability compiler. Only
connections explicitly represented by MSB ConnectCollision/Connection records
become edges. EMEVD data is attached as map-scoped condition evidence; it is
never guessed as an edge requirement without a direct binding.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--msbe-index", type=Path, required=True)
    parser.add_argument("--emevd-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    msbe = json.loads(args.msbe_index.read_text(encoding="utf-8"))
    emevd = json.loads(args.emevd_index.read_text(encoding="utf-8"))
    msbe_maps = {record["map_id"]: record for record in msbe["maps"]}
    emevd_maps = {record["map_key"]: record for record in emevd["maps"]}

    nodes: list[dict[str, Any]] = []
    for map_id, record in sorted(msbe_maps.items()):
        event_record = emevd_maps.get(map_id)
        nodes.append(
            {
                "id": record["id"],
                "map_id": map_id,
                "source_file": record["source_file"],
                "coordinate_system": record["coordinate_system"],
                "original_game_coordinates": record["original_game_coordinates"],
                "local_game_verified": record["local_game_verified"],
                "counts": record["counts"],
                "part_types": record["part_types"],
                "region_types": record["region_types"],
                "xyz_bounds": record["xyz_bounds"],
                "emevd_evidence": {
                    "file_present": event_record is not None,
                    "event_count": event_record.get("event_count", 0) if event_record else 0,
                    "condition_count": event_record.get("condition_count", 0) if event_record else 0,
                    "action_count": event_record.get("action_count", 0) if event_record else 0,
                    "event_flag_ids": event_record.get("event_flag_ids", []) if event_record else [],
                    "reference_count": event_record.get("reference_count", 0) if event_record else 0,
                    "verification_state": "local_emevd_verified" if event_record else "local_emevd_file_absent",
                },
                "verification_state": "local_msbe_verified",
            }
        )

    edges: list[dict[str, Any]] = []
    for transition in msbe["transitions"]:
        target = msbe_maps.get(transition["to_map_id"])
        edge_kind = "explicit_map_connection" if transition["kind"] == "connect_collision" else "explicit_connection_region"
        edges.append(
            {
                "id": transition["id"],
                "from_map_id": transition["from_map_id"],
                "to_map_id": transition["to_map_id"],
                "kind": transition["kind"],
                "edge_kind": edge_kind,
                "part_name": transition.get("part_name"),
                "collision_name": transition.get("collision_name"),
                "model_name": transition.get("model_name"),
                "position": transition.get("position"),
                "raw_target_map_id": transition.get("raw_target_map_id"),
                "target_has_wildcard_byte": transition.get("target_has_wildcard_byte", False),
                "target_exists_in_msbe_index": target is not None,
                "source_file": transition["source_file"],
                "requires": [],
                "condition_status": "not_directly_bound",
                "condition_evidence_scope": "map_level_only",
                "routeable": False,
                "verification_state": transition["verification_state"],
            }
        )

    output = {
        "schema": "elden-ring-local-explicit-topology@1",
        "source": {
            "msbe_index": str(args.msbe_index.resolve()),
            "msbe_index_sha256": sha256(args.msbe_index),
            "emevd_index": str(args.emevd_index.resolve()),
            "emevd_index_sha256": sha256(args.emevd_index),
        },
        "model": {
            "node_definition": "one node per locally parsed MSB map",
            "edge_definition": "only explicit MSB ConnectCollision or Connection records",
            "condition_binding": "never inferred from map-level EMEVD evidence",
            "continuous_walkability": "not modeled",
            "routeable": False,
        },
        "status": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "connect_collision_edges": sum(edge["kind"] == "connect_collision" for edge in edges),
            "connection_region_edges": sum(edge["kind"] == "connection_region" for edge in edges),
            "target_nodes_missing": sum(not edge["target_exists_in_msbe_index"] for edge in edges),
            "edges_with_direct_conditions": 0,
            "all_edges_routeable_false": True,
        },
        "nodes": nodes,
        "edges": edges,
        "note": "抽象拓扑和条件证据层；不声称玩家可在连续空间中步行到达，也不自动把地图级脚本条件绑定到某条边。",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
