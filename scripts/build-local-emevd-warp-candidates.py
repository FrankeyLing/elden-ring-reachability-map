#!/usr/bin/env python3
"""Index every map-local EMEVD warp action and resolve exact destinations.

This is evidence for scripted transport/topology.  It includes character and
asset warps, not only player travel, and therefore never promotes a record to
routeable.  Destination identity is resolved only by map/entity IDs in the
local MSBE snapshot; no proximity or name guessing is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


MAP_RE = re.compile(r"^m\d+_\d+_\d+_\d+$")
WARP_TOKEN_RE = re.compile(r"warp", re.IGNORECASE)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def args_map(ref: dict[str, Any]) -> dict[str, Any]:
    return {str(arg.get("name")): arg.get("value") for arg in ref.get("args", [])}


def map_id_from_integer(value: Any) -> str | None:
    if not isinstance(value, int) or value <= 0:
        return None
    digits = str(value)
    if len(digits) != 8:
        return None
    map_id = f"m{digits[0:2]}_{digits[2:4]}_{digits[4:6]}_{digits[6:8]}"
    return map_id if MAP_RE.fullmatch(map_id) else None


def node_id(map_id: str, kind: str, item: dict[str, Any], index: int) -> str:
    if kind == "part":
        return f"local-part:{map_id}:{item.get('name')}:{index}"
    if kind == "region":
        return f"local-region:{map_id}:{item.get('name')}:{item.get('region_id', -1)}:{index}"
    return f"local-event:{map_id}:{item.get('type', 'Unknown')}:{item.get('event_id', -1)}:{index}"


def build_entity_index(maps_root: Path) -> tuple[dict[tuple[str, int], list[dict[str, Any]]], dict[int, list[dict[str, Any]]], int]:
    by_map_entity: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    by_entity: dict[int, list[dict[str, Any]]] = defaultdict(list)
    source_files = 0
    for path in sorted(maps_root.glob("*.json")):
        source_files += 1
        map_id = path.stem
        payload = json.loads(path.read_text(encoding="utf-8"))
        for kind in ("part", "region", "event"):
            section = "parts" if kind == "part" else f"{kind}s"
            for index, item in enumerate(payload.get(section, [])):
                entity_id = item.get("entity_id")
                if not isinstance(entity_id, int) or entity_id == 0:
                    continue
                locator = {
                    "node_id": node_id(map_id, kind, item, index),
                    "map_id": map_id,
                    "kind": kind,
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "entity_id": entity_id,
                    "region_id": item.get("region_id"),
                    "position": item.get("position"),
                    "source_file": path.name,
                    "source_index": index,
                }
                by_map_entity[(map_id, entity_id)].append(locator)
                by_entity[entity_id].append(locator)
    return dict(by_map_entity), dict(by_entity), source_files


def resolve_entity(
    map_id: str | None,
    entity_id: Any,
    by_map_entity: dict[tuple[str, int], list[dict[str, Any]]],
    by_entity: dict[int, list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(entity_id, int) or entity_id == 0:
        return None, "entity_id_absent_or_zero"
    if map_id:
        rows = by_map_entity.get((map_id, entity_id), [])
        if len(rows) == 1:
            return rows[0], "exact_map_entity_id"
        if len(rows) > 1:
            return None, "ambiguous_map_entity_id"
    rows = by_entity.get(entity_id, [])
    if len(rows) == 1:
        return rows[0], "exact_global_entity_id_unique"
    if len(rows) > 1:
        return None, "ambiguous_global_entity_id"
    return None, "entity_id_not_found"


def compact_reference(ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": ref.get("event_id"),
        "instruction_index": ref.get("instruction_index"),
        "instruction_name": ref.get("instruction_name"),
        "category": ref.get("category"),
        "args": ref.get("args", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--emevd-root", type=Path, required=True)
    parser.add_argument("--maps-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    emevd_root = args.emevd_root.resolve()
    maps_root = args.maps_root.resolve()
    by_map_entity, by_entity, source_map_files = build_entity_index(maps_root)
    records = []
    instruction_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    total_refs = 0

    for path in sorted(emevd_root.glob("m*.json")):
        map_id = path.stem
        if not MAP_RE.fullmatch(map_id):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for ref in payload.get("references", []):
            name = str(ref.get("instruction_name") or "")
            if not WARP_TOKEN_RE.search(name):
                continue
            total_refs += 1
            instruction_counts[name] += 1
            args_by_name = args_map(ref)
            lower_name = name.lower()
            if "player" in lower_name:
                role = "player_transport"
            elif "character" in lower_name:
                role = "character_transport"
            elif "asset" in lower_name:
                role = "asset_transport"
            else:
                role = "generic_scripted_transport"
            role_counts[role] += 1

            destination_map_id = None
            destination_entity_id = None
            destination_basis = None
            if "Map ID" in args_by_name:
                destination_map_id = map_id_from_integer(args_by_name.get("Map ID"))
                destination_basis = "EMEVD Map ID"
            elif "Area ID" in args_by_name:
                values = [
                    args_by_name.get("Area ID"),
                    args_by_name.get("Block ID"),
                    args_by_name.get("Region ID"),
                    args_by_name.get("Index ID"),
                ]
                if all(isinstance(value, int) for value in values):
                    destination_map_id = "m" + "_".join(f"{value:02d}" for value in values)
                destination_basis = "EMEVD Area/Block/Region/Index"
            if "Warp Destination Entity ID" in args_by_name:
                destination_entity_id = args_by_name.get("Warp Destination Entity ID")
                destination_basis = destination_basis or "EMEVD destination entity ID"
            elif "Initial Area Entity ID" in args_by_name:
                destination_entity_id = args_by_name.get("Initial Area Entity ID")
                destination_basis = destination_basis or "EMEVD initial area entity ID"
            elif "Area Entity ID" in args_by_name:
                destination_entity_id = args_by_name.get("Area Entity ID")
                destination_basis = destination_basis or "EMEVD area entity ID"
            elif name == "Warp Asset To Character" and "Character Entity ID" in args_by_name:
                # This instruction has no Warp Destination Entity ID.  Its
                # Character Entity ID is the exact target of the asset-to-
                # character operation; using it avoids treating a statically
                # named MSBE character as an unresolved destination.
                destination_entity_id = args_by_name.get("Character Entity ID")
                destination_basis = destination_basis or "EMEVD character entity ID"

            if destination_entity_id == 10000:
                destination_locator = {
                    "node_id": "runtime:player-entity:10000",
                    "map_id": None,
                    "kind": "runtime_entity",
                    "name": "Player entity 10000",
                    "type": "runtime_player",
                    "entity_id": 10000,
                    "region_id": None,
                    "position": None,
                    "source_file": None,
                    "source_index": None,
                }
                destination_status = "exact_runtime_entity_id"
            else:
                destination_locator, destination_status = resolve_entity(
                    destination_map_id or map_id,
                    destination_entity_id,
                    by_map_entity,
                    by_entity,
                )
            if destination_map_id and destination_status in {"entity_id_absent_or_zero", "entity_id_not_found"}:
                destination_status = "exact_map_identity_only"
            status_counts[destination_status] += 1

            source_entity_id = args_by_name.get("Entity ID")
            source_locator, source_status = resolve_entity(
                map_id, source_entity_id, by_map_entity, by_entity
            )
            if source_entity_id == 10000:
                source_status = "player_entity_10000"
            records.append(
                {
                    "id": f"local-emevd-warp:{map_id}:{ref.get('event_id')}:{ref.get('instruction_index')}",
                    "map_id": map_id,
                    "event_id": ref.get("event_id"),
                    "instruction_index": ref.get("instruction_index"),
                    "instruction_name": name,
                    "transport_role": role,
                    "source": {
                        "entity_id": source_entity_id,
                        "resolution_status": source_status,
                        "locator": source_locator,
                    },
                    "destination": {
                        "map_id": destination_map_id,
                        "map_identity_basis": destination_basis,
                        "entity_id": destination_entity_id,
                        "resolution_status": destination_status,
                        "locator": destination_locator,
                    },
                    "emevd_reference": compact_reference(ref),
                    "routeable": False,
                    "verification_state": "local_emevd_warp_evidence",
                }
            )

    output = {
        "schema": "elden-ring-local-emevd-warp-candidates@1",
        "source": {
            "emevd_root": str(emevd_root),
            "maps_root": str(maps_root),
            "emevd_source_file_count": len(list(emevd_root.glob("m*.json"))),
            "map_source_file_count": source_map_files,
        },
        "model": {
            "purpose": "full map-local EMEVD warp evidence with exact entity/map resolution where possible",
            "uses_proximity": False,
            "uses_havok_nva_navmesh": False,
            "routeable": False,
        },
        "status": {
            "warp_reference_count": total_refs,
            "record_count": len(records),
            "instruction_name_count": len(instruction_counts),
            "instruction_counts": dict(sorted(instruction_counts.items())),
            "transport_role_counts": dict(sorted(role_counts.items())),
            "destination_resolution_counts": dict(sorted(status_counts.items())),
            "exact_destination_entity_count": sum(
                row["destination"]["resolution_status"]
                in {"exact_map_entity_id", "exact_global_entity_id_unique"}
                for row in records
            ),
            "exact_runtime_entity_count": sum(
                row["destination"]["resolution_status"] == "exact_runtime_entity_id"
                for row in records
            ),
            "exact_map_identity_only_count": sum(
                row["destination"]["resolution_status"] == "exact_map_identity_only" for row in records
            ),
            "unresolved_destination_count": sum(
                row["destination"]["resolution_status"]
                not in {
                    "exact_map_entity_id",
                    "exact_global_entity_id_unique",
                    "exact_map_identity_only",
                    "exact_runtime_entity_id",
                }
                for row in records
            ),
            "routeable_records": 0,
            "all_records_routeable_false": all(row["routeable"] is False for row in records),
        },
        "records": records,
        "note": "Warp instructions are broader than player traversal. These records preserve exact script evidence but do not infer interaction availability, conditions, or a walkable route.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
