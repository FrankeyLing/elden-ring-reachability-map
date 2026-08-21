#!/usr/bin/env python3
"""Extract real summon endpoints from the copied local map snapshot.

The source snapshot stays outside the repository.  This script publishes only
the small, player-facing endpoint catalog required by the query projection.
It deliberately records coordinates as coordinate endpoints; it does not
invent a route edge or claim that a summon point is already bound to a formal
topology node.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SNAPSHOT_ROOT = ROOT.parent.parent / "local-snapshots" / "elden-ring-20260818"
DEFAULT_OUT = ROOT / "data" / "v1" / "entities" / "summon-endpoints.json"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def position_of(part: dict[str, Any] | None) -> dict[str, float] | None:
    position = (part or {}).get("position")
    if not isinstance(position, dict):
        return None
    if not all(axis in position for axis in ("x", "y", "z")):
        return None
    return {axis: float(position[axis]) for axis in ("x", "y", "z")}


def map_stem(path: Path) -> str:
    return path.name.removesuffix(".json")


def extract(snapshot_root: Path) -> dict[str, Any]:
    map_root = snapshot_root / "extracted" / "parsed-mapstudio-all-extra2" / "maps"
    files = sorted(map_root.glob("m*.json"))
    if not files:
        raise FileNotFoundError(f"no parsed map files under {map_root}")

    endpoints: list[dict[str, Any]] = []
    for path in files:
        payload = load(path)
        stem = map_stem(path)
        parts = {part.get("name"): part for part in payload.get("parts", []) if part.get("name")}

        for event in payload.get("events", []):
            if event.get("type") != "SignPool":
                continue
            extra = event.get("extra") or {}
            part_name = extra.get("SignPartName")
            part = parts.get(part_name)
            position = position_of(part)
            if position is None:
                raise ValueError(f"SignPool {stem} event {event.get('event_id')} has no referenced part position")
            endpoints.append({
                "id": f"sign_pool_{stem}_event_{event['event_id']}",
                "endpointType": "multiplayer_summon_pool",
                "map": stem,
                "mapFile": path.name,
                "eventId": event.get("event_id"),
                "sourceName": event.get("name"),
                "sourcePart": part_name,
                "signPuddleParamId": extra.get("SignPuddleParamID"),
                "position": position,
                "rotation": part.get("rotation"),
                "coordinateSpace": "game_world_xyz",
                "topologyBinding": {
                    "status": "coordinate_endpoint",
                    "routeNodeIds": [],
                    "semanticNodeIds": [],
                    "reason": "local map SignPool event and referenced asset coordinate; formal topology anchor not proven",
                },
                "sourceEvidence": [
                    "parsed-mapstudio-all-extra2 local map event",
                    f"{path.name} event {event.get('event_id')}",
                    f"SignPartName {part_name}",
                ],
            })

        for region in payload.get("regions", []):
            if region.get("type") != "BuddySummonPoint":
                continue
            position = position_of(region)
            if position is None:
                raise ValueError(f"BuddySummonPoint {stem} region {region.get('region_id')} has no position")
            shape_data = (region.get("extra") or {}).get("shape_data") or {}
            endpoints.append({
                "id": f"buddy_summon_point_{stem}_region_{region['region_id']}",
                "endpointType": "spirit_ash_summon_point",
                "map": stem,
                "mapFile": path.name,
                "regionId": region.get("region_id"),
                "entityId": region.get("entity_id"),
                "sourceName": region.get("name"),
                "shape": region.get("shape"),
                "radius": shape_data.get("Radius"),
                "position": position,
                "rotation": region.get("rotation"),
                "coordinateSpace": "game_world_xyz",
                "topologyBinding": {
                    "status": "coordinate_endpoint",
                    "routeNodeIds": [],
                    "semanticNodeIds": [],
                    "reason": "local map BuddySummonPoint region coordinate; formal topology anchor not proven",
                },
                "sourceEvidence": [
                    "parsed-mapstudio-all-extra2 local map region",
                    f"{path.name} region {region.get('region_id')}",
                ],
            })

    endpoints.sort(key=lambda item: item["id"])
    counts = Counter(item["endpointType"] for item in endpoints)
    return {
        "schema": "elden-ring-summon-endpoints@1",
        "builtAt": "2026-08-21",
        "source": "copied local parsed-mapstudio-all-extra2 map snapshot",
        "stats": {
            "endpointCount": len(endpoints),
            "mapFileCount": len({item["map"] for item in endpoints}),
            "multiplayerSummonPoolCount": counts["multiplayer_summon_pool"],
            "spiritAshSummonPointCount": counts["spirit_ash_summon_point"],
        },
        "endpoints": endpoints,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_SNAPSHOT_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    payload = extract(args.snapshot_root.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
