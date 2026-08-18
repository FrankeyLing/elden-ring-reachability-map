#!/usr/bin/env python3
"""Bind native NVA Navmesh model identities to copied MSBE collision parts.

This is an identity layer only.  A matching ``model_name`` proves that the
native Navmesh and MSBE part refer to the same native model identity; it does
not prove that the MSBE part is a player entrance or that the node is
walkable in the current world state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


PART_TYPES = {"Collision", "ConnectCollision"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def part_node_id(map_id: str, part: dict[str, Any], source_index: int) -> str:
    return f"local-part:{map_id}:{part.get('name')}:{source_index}"


def normalized_part(map_id: str, part: dict[str, Any], source_index: int) -> dict[str, Any]:
    return {
        "node_id": part_node_id(map_id, part, source_index),
        "map_id": map_id,
        "source_part_index": source_index,
        "part_type": part.get("type"),
        "name": part.get("name"),
        "model_name": part.get("model_name"),
        "instance_id": part.get("instance_id"),
        "entity_id": part.get("entity_id"),
        "position": part.get("position"),
        "rotation": part.get("rotation"),
        "scale": part.get("scale"),
        "map_studio_layer": part.get("map_studio_layer"),
        "extra": part.get("extra") or {},
        "coordinate_system": "Elden Ring MSBE game-native XYZ",
        "original_game_coordinates": True,
        "local_game_verified": True,
        "routeable": False,
        "verification_state": "local_msbe_raw_part_exact_model_identity",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--nva-connectivity", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    snapshot_root = args.snapshot_root.resolve()
    connectivity_path = args.nva_connectivity.resolve()
    map_root = snapshot_root / "extracted" / "parsed-mapstudio-all-extra2" / "maps"
    connectivity = json.loads(connectivity_path.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    map_summaries: list[dict[str, Any]] = []
    status_counts = Counter()
    parse_errors: list[dict[str, Any]] = []

    for map_record in connectivity.get("maps", []):
        map_id = map_record.get("map_id")
        map_path = map_root / f"{map_id}.json"
        try:
            parsed_map = json.loads(map_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parse_errors.append({"map_id": map_id, "source_file": str(map_path), "error": str(exc)})
            continue

        by_model: dict[str, list[dict[str, Any]]] = {}
        for source_index, part in enumerate(parsed_map.get("parts", [])):
            if part.get("type") not in PART_TYPES:
                continue
            model_name = str(part.get("model_name") or "")
            by_model.setdefault(model_name.casefold(), []).append(
                {"part": part, "source_index": source_index}
            )

        map_records: list[dict[str, Any]] = []
        map_counts = Counter()
        for navmesh in map_record.get("navmesh_nodes", []):
            model_id = navmesh.get("model_id")
            expected_model_name = f"h{model_id:06d}" if isinstance(model_id, int) and model_id >= 0 else None
            candidates = [
                normalized_part(map_id, row["part"], row["source_index"])
                for row in by_model.get(expected_model_name, [])
            ] if expected_model_name else []
            if not candidates:
                binding_status = "missing_msbe_collision_model_identity"
            elif len(candidates) == 1:
                binding_status = "exact_msbe_collision_model_identity_unique"
            else:
                binding_status = "exact_msbe_collision_model_identity_role_candidates"
            status_counts[binding_status] += 1
            map_counts[binding_status] += 1
            map_records.append(
                {
                    "native_node_id": navmesh.get("id"),
                    "map_id": map_id,
                    "navmesh_index": navmesh.get("navmesh_index"),
                    "name_id": navmesh.get("name_id"),
                    "model_id": model_id,
                    "expected_msbe_model_name": expected_model_name,
                    "binding_status": binding_status,
                    "model_name_match": "case_insensitive_exact_identifier",
                    "msbe_part_candidates": candidates,
                    "player_walkability_validated": False,
                    "routeable": False,
                    "verification_state": "local_nva_to_msbe_model_identity_audit",
                }
            )
            records.append(map_records[-1])
        map_summaries.append(
            {
                "map_id": map_id,
                "source_file": str(map_path),
                "source_sha256": sha256(map_path),
                "native_navmesh_node_count": len(map_records),
                "binding_status_counts": dict(sorted(map_counts.items())),
                "player_walkability_validated": False,
                "routeable": False,
            }
        )

    status = {
        "map_count": len(map_summaries),
        "native_navmesh_node_count": len(records),
        "node_with_msbe_candidate_count": sum(
            status_counts[k]
            for k in (
                "exact_msbe_collision_model_identity_unique",
                "exact_msbe_collision_model_identity_role_candidates",
            )
        ),
        "unique_msbe_part_binding_count": status_counts[
            "exact_msbe_collision_model_identity_unique"
        ],
        "role_candidate_binding_count": status_counts[
            "exact_msbe_collision_model_identity_role_candidates"
        ],
        "missing_msbe_model_identity_count": status_counts[
            "missing_msbe_collision_model_identity"
        ],
        "parse_error_count": len(parse_errors),
        "routeable_records": 0,
        "player_walkability_validated": False,
        "all_records_routeable_false": all(row.get("routeable") is False for row in records),
    }
    output = {
        "schema": "elden-ring-local-native-msbe-model-bindings@1",
        "source": {
            "snapshot_root": str(snapshot_root),
            "parsed_msbe_map_root": str(map_root),
            "nva_connectivity": str(connectivity_path),
            "nva_connectivity_sha256": sha256(connectivity_path),
        },
        "model": {
            "purpose": "exact native NVA model identity to copied MSBE Collision/ConnectCollision part identity",
            "model_name_match_is_not_player_entrance": True,
            "model_name_comparison": "case_insensitive_exact_identifier",
            "collision_part_is_not_player_route": True,
            "continuous_player_walkability_evaluated": False,
            "routeable": False,
        },
        "status": status,
        "maps": map_summaries,
        "records": records,
        "errors": parse_errors,
        "note": "A role-candidate binding preserves both exact Collision and ConnectCollision identities when the same model name is present in both forms. No candidate is promoted to a player route.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
