#!/usr/bin/env python3
"""Build physical shop endpoint bindings from a copied merchant-shop table.

The ShopLineupParam table only describes an item row.  A talk script opens a
range of those rows, and the same row can be opened by several sellers.  This
builder keeps that relationship one row at a time and joins each named seller
to the copied MSB enemy/NPC instance catalog when possible.

The external table is deliberately an input, not a runtime dependency.  The
caller must copy it into the local snapshot directory and pass it with
``--source``.  Blank seller records are retained as unresolved evidence and
are never promoted to a named merchant or a route anchor.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPAWNS = ROOT / "data" / "v1" / "entities" / "enemy-spawn-bindings.json"
DEFAULT_OUT = ROOT / "data" / "v1" / "entities" / "merchant-shop-bindings.json"
DEFAULT_SEMANTIC_ALIASES = ROOT / "data" / "v1" / "entities" / "merchant-shop-semantic-aliases.json"


def as_int(value: str | None) -> int | None:
    value = (value or "").strip()
    return int(value) if value else None


def as_float(value: str | None) -> float | None:
    value = (value or "").strip()
    return float(value) if value else None


def map_matches(source_map: str | None, local_map: str | None) -> bool:
    if not source_map or not local_map:
        return False
    stem = Path(local_map).name
    return stem == source_map or stem.startswith(f"{source_map}_")


def close_position(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    if not a or not b:
        return False
    return all(abs(float(a[axis]) - float(b[axis])) <= 0.02 for axis in ("x", "y", "z"))


def load_spawns(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(binding["npcParamId"]): binding.get("instances", [])
        for binding in payload.get("bindings", [])
    }


def local_endpoint(
    row: dict[str, Any],
    spawns: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    npc_id = row.get("npcParamId")
    if npc_id is None:
        return None
    candidates = [
        instance for instance in spawns.get(str(npc_id), [])
        if map_matches(row.get("mapId"), instance.get("map"))
    ]
    position = row.get("position")
    exact = next((instance for instance in candidates if close_position(position, instance.get("position"))), None)
    return exact or (candidates[0] if len(candidates) == 1 else None)


def read_source(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        lines = (line for line in handle if line.strip() and not line.startswith("#"))
        for raw in csv.DictReader(lines, delimiter="\t"):
            position_values = {
                axis: as_float(raw.get(f"pos_{axis}")) for axis in ("x", "y", "z")
            }
            position = position_values if all(value is not None for value in position_values.values()) else None
            rows.append({
                "rowId": as_int(raw.get("row_id")),
                "talkId": as_int(raw.get("talk_id")),
                "npcParamId": as_int(raw.get("npc_param_id")),
                "merchantName": (raw.get("merchant_name") or "").strip() or None,
                "mapId": (raw.get("map_id") or "").strip() or None,
                "mapSource": (raw.get("map_source") or "").strip() or None,
                "npcNameId": as_int(raw.get("npc_name_id")),
                "position": position,
            })
    return [row for row in rows if row["rowId"] is not None]


def load_semantic_aliases(path: Path | None) -> dict[int, dict[str, Any]]:
    if not path or not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    aliases: dict[int, dict[str, Any]] = {}
    for alias in payload.get("aliases", []):
        npc_id = alias.get("npcParamId")
        if npc_id is None or not alias.get("merchantName"):
            continue
        if int(npc_id) in aliases:
            raise ValueError(f"duplicate semantic merchant alias for NpcParam {npc_id}")
        aliases[int(npc_id)] = alias
    return aliases


def build(
    source: Path,
    spawn_path: Path,
    source_url: str | None,
    source_commit: str | None,
    semantic_aliases_path: Path | None = None,
) -> dict[str, Any]:
    source_rows = read_source(source)
    spawns = load_spawns(spawn_path)
    semantic_aliases = load_semantic_aliases(semantic_aliases_path)
    bindings: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in source_rows:
        local = local_endpoint(row, spawns)
        semantic_alias = (
            semantic_aliases.get(row.get("npcParamId"))
            if not row.get("merchantName") else None
        )
        merchant_name = row.get("merchantName") or (
            semantic_alias.get("merchantName") if semantic_alias else None
        )
        named = bool(merchant_name)
        endpoint = {
            "id": (
                f"merchant-shop-endpoint-{row['rowId']}-"
                f"{row.get('talkId') or 'unknown'}-{row.get('npcParamId') or 'unknown'}-"
                f"{row.get('mapId') or 'unknown'}"
            ),
            "rowId": row["rowId"],
            "talkId": row.get("talkId"),
            "npcParamId": row.get("npcParamId"),
            "merchantName": merchant_name,
            "map": row.get("mapId"),
            "mapSource": row.get("mapSource"),
            "npcNameId": row.get("npcNameId"),
            "position": row.get("position"),
            "endpointStatus": "named_coordinate_endpoint" if named and row.get("position") else "unbound",
            "sellerStatus": "named" if named else "unresolved",
            "sellerIdentitySource": (
                "external_shop_source" if row.get("merchantName")
                else semantic_alias.get("sellerIdentitySource") if semantic_alias
                else "unresolved"
            ),
            "sourceEvidence": [
                "external merchant-shop table: talk range joined to physical map instance"
            ],
        }
        if semantic_alias:
            endpoint["semanticAliasId"] = semantic_alias.get("id")
            endpoint["sourceEvidence"].extend(semantic_alias.get("sourceEvidence", []))
        if local:
            endpoint["map"] = local.get("map") or endpoint["map"]
            endpoint["part"] = local.get("part")
            endpoint["instanceId"] = local.get("instanceId")
            endpoint["entityId"] = local.get("entityId")
            endpoint["mapStudioLayer"] = local.get("mapStudioLayer")
            endpoint["position"] = local.get("position") or endpoint["position"]
            endpoint["endpointStatus"] = "named_coordinate_endpoint" if named else "candidate_coordinate_endpoint"
            endpoint["localSpawnMatch"] = True
            endpoint["sourceEvidence"].append("copied local MSB enemy/NPC instance catalog")
        else:
            endpoint["localSpawnMatch"] = False
        key = (
            endpoint["rowId"], endpoint["talkId"], endpoint["npcParamId"],
            endpoint["merchantName"], endpoint["map"],
            tuple((endpoint.get("position") or {}).get(axis) for axis in ("x", "y", "z")),
        )
        if key in seen:
            continue
        seen.add(key)
        bindings.append(endpoint)

    named = [binding for binding in bindings if binding["sellerStatus"] == "named"]
    unresolved = [binding for binding in bindings if binding["sellerStatus"] == "unresolved"]
    named_endpoints = [binding for binding in named if binding["endpointStatus"] == "named_coordinate_endpoint"]
    payload = {
        "schema": "elden-ring-merchant-shop-bindings@1",
        "builtFrom": {
            "source": str(source),
            "sourceUrl": source_url,
            "sourceCommit": source_commit,
            "enemySpawnBindings": str(spawn_path),
            "semanticAliases": str(semantic_aliases_path) if semantic_aliases_path else None,
            "policy": "retain every talk-row seller binding; only explicit semantic aliases may resolve an unnamed seller",
        },
        "stats": {
            "sourceRows": len(source_rows),
            "bindings": len(bindings),
            "uniqueShopRows": len({binding["rowId"] for binding in bindings}),
            "namedBindings": len(named),
            "namedCoordinateEndpoints": len(named_endpoints),
            "unresolvedSellerBindings": len(unresolved),
            "semanticAliasBindings": sum(
                binding.get("sellerIdentitySource") == "local_map_semantic_alias"
                for binding in bindings
            ),
            "localSpawnMatches": sum(bool(binding.get("localSpawnMatch")) for binding in bindings),
            "merchantNames": len({binding["merchantName"] for binding in named}),
        },
        "bindings": sorted(
            bindings,
            key=lambda binding: (
                binding["rowId"], binding.get("merchantName") or "", binding.get("map") or "",
                binding.get("npcParamId") or -1,
            ),
        ),
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--enemy-spawns", type=Path, default=DEFAULT_SPAWNS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--semantic-aliases", type=Path, default=DEFAULT_SEMANTIC_ALIASES)
    parser.add_argument("--source-url")
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    if not args.source.is_file():
        raise FileNotFoundError(f"merchant source missing: {args.source}")
    payload = build(
        args.source,
        args.enemy_spawns,
        args.source_url,
        args.source_commit,
        args.semantic_aliases,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2))
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
