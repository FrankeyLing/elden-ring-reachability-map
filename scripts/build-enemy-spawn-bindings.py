#!/usr/bin/env python3
"""Build exact enemy spawn instances from the copied MSB map snapshot.

This is an endpoint catalog, not a route graph.  Every instance retains its
source map, part identity, raw game coordinates, layer value and NpcParam
identity.  Dummy enemies remain visible but are explicitly distinguished from
ordinary Enemy parts.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAP_ROOT = (
    ROOT.parent.parent
    / "local-snapshots"
    / "elden-ring-20260818"
    / "extracted"
    / "parsed-mapstudio-all-extra2"
    / "maps"
)
DEFAULT_OUT = ROOT / "data" / "v1" / "entities" / "enemy-spawn-bindings.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map-root", type=Path, default=DEFAULT_MAP_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if not args.map_root.is_dir():
        raise FileNotFoundError(f"map snapshot directory missing: {args.map_root}")

    by_npc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    map_count = 0
    enemy_count = 0
    dummy_count = 0
    for path in sorted(args.map_root.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        map_id = data.get("source_entry") or path.name
        map_count += 1
        for part in data.get("parts", []):
            part_type = part.get("type")
            if part_type not in {"Enemy", "DummyEnemy"}:
                continue
            extra = part.get("extra") or {}
            npc_param_id = extra.get("NPCParamID")
            if npc_param_id is None or int(npc_param_id) < 0:
                continue
            if part_type == "Enemy":
                enemy_count += 1
            else:
                dummy_count += 1
            retained_extra = {
                key: extra[key]
                for key in (
                    "ThinkParamID", "CharaInitID", "TalkID", "PlatoonID",
                    "ChrActivateCondParamID", "EntityGroupIDs", "GameEditionDisable",
                )
                if key in extra
            }
            by_npc[str(int(npc_param_id))].append({
                "kind": "enemy_spawn" if part_type == "Enemy" else "dummy_enemy_spawn",
                "spawnKind": part_type,
                "map": map_id,
                "part": part.get("name"),
                "model": part.get("model_name"),
                "instanceId": part.get("instance_id"),
                "entityId": part.get("entity_id"),
                "position": part.get("position"),
                "mapStudioLayer": part.get("map_studio_layer"),
                "npcParamId": int(npc_param_id),
                "topologyBinding": {
                    "status": "coordinate_endpoint",
                    "reason": "本地 MSB 敌人出生实例坐标已记录，尚未绑定正式抽象拓扑锚点",
                },
                "sourceEvidence": [
                    f"local MSB {map_id} part {part.get('name')} NpcParam {int(npc_param_id)}"
                ],
                "extra": retained_extra,
            })

    bindings = [
        {"npcParamId": int(npc_id), "instances": instances}
        for npc_id, instances in sorted(by_npc.items(), key=lambda item: int(item[0]))
    ]
    payload = {
        "schema": "elden-ring-enemy-spawn-bindings@1",
        "built_from": {"map_root": str(args.map_root), "policy": "copied local MSB snapshot only"},
        "stats": {
            "mapCount": map_count,
            "enemyInstanceCount": enemy_count,
            "dummyEnemyInstanceCount": dummy_count,
            "npcParamCount": len(bindings),
            "instanceCount": sum(len(item["instances"]) for item in bindings),
        },
        "bindings": bindings,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2))
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
