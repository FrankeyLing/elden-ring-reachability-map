#!/usr/bin/env python3
"""Bind every MSBE ConnectCollision endpoint to native Navmesh candidates.

The binding uses only same-map model identity.  Repeated native instances of
the same collision model remain an explicit candidate set; no proximity or
floor guess is used to choose one instance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


NATIVE_CANDIDATE_FIELDS = (
    "navmesh_index",
    "name_id",
    "face_data_index",
    "face_count",
    "gate_node_index",
    "gate_node_count",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def model_id_from_name(value: Any) -> int | None:
    text = str(value or "").casefold()
    if not text.startswith("h") or not text[1:].isdigit():
        return None
    return int(text[1:])


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
        "verification_state": "local_msbe_connect_collision_exact",
    }


def normalized_navmesh(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": row.get("id"),
        "map_id": row.get("map_id"),
        "navmesh_index": row.get("navmesh_index"),
        "name_id": row.get("name_id"),
        "model_id": row.get("model_id"),
        "face_data_index": row.get("face_data_index"),
        "face_count": row.get("face_count"),
        "gate_node_index": row.get("gate_node_index"),
        "gate_node_count": row.get("gate_node_count"),
        "routeable": False,
    }


def identity_audit(
    msbe_part: dict[str, Any],
    model_id: int | None,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Record what the copied sources can and cannot identify exactly.

    MSBE ConnectCollision exposes a model identity, while an NVA can contain
    more than one native Navmesh instance with that model ID.  The fields that
    distinguish those NVA instances have no documented MSBE counterpart in
    this snapshot.  Keep that boundary explicit instead of selecting by
    position, geometry, index order, or a name heuristic.
    """
    shared_keys = ["map_id"]
    if model_id is not None:
        shared_keys.append("model_id")
    distinct_candidate_values = {
        field: len({candidate.get(field) for candidate in candidates})
        for field in NATIVE_CANDIDATE_FIELDS
    }
    if not candidates:
        resolution = "unresolved_no_same_map_nva_model_id"
    elif len(candidates) == 1:
        resolution = "unique_same_map_nva_model_id_candidate"
    else:
        resolution = "unresolved_repeated_same_model_without_cross_layer_instance_key"
    return {
        "shared_exact_identity_keys": shared_keys,
        "msbe_instance_key_available": any(
            msbe_part.get(field) not in (None, 0, "")
            for field in ("instance_id", "entity_id", "source_part_index")
        ),
        "native_candidate_distinct_value_counts": distinct_candidate_values,
        "cross_layer_instance_key": None,
        "resolution": resolution,
        "excluded_resolution_methods": [
            "position_or_proximity",
            "hkx2_or_havok_geometry",
            "navmesh_index_order",
            "face_count_or_gate_count_without_an_msbe_counterpart",
            "name_similarity_or_target_map_guess",
        ],
        "routeable": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--msbe-map-index", type=Path, required=True)
    parser.add_argument("--nva-connectivity", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    snapshot_root = args.snapshot_root.resolve()
    map_index_path = args.msbe_map_index.resolve()
    connectivity_path = args.nva_connectivity.resolve()
    map_root = snapshot_root / "extracted" / "parsed-mapstudio-all-extra2" / "maps"
    map_index = json.loads(map_index_path.read_text(encoding="utf-8"))
    connectivity = json.loads(connectivity_path.read_text(encoding="utf-8"))
    native_by_model: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for map_record in connectivity.get("maps", []):
        for row in map_record.get("navmesh_nodes", []):
            model_id = row.get("model_id")
            if isinstance(model_id, int) and model_id >= 0:
                native_by_model[(map_record.get("map_id"), model_id)].append(row)

    records: list[dict[str, Any]] = []
    maps: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    counts = Counter()
    for map_record in map_index.get("maps", []):
        map_id = map_record.get("map_id")
        map_path = map_root / f"{map_id}.json"
        try:
            parsed_map = json.loads(map_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append({"map_id": map_id, "source_file": str(map_path), "error": str(exc)})
            continue
        map_records = []
        map_counts = Counter()
        for source_index, part in enumerate(parsed_map.get("parts", [])):
            if part.get("type") != "ConnectCollision":
                continue
            model_id = model_id_from_name(part.get("model_name"))
            candidates = [
                normalized_navmesh(row)
                for row in native_by_model.get((map_id, model_id), [])
            ] if model_id is not None else []
            if not candidates:
                binding_status = "native_navmesh_candidate_missing"
            elif len(candidates) == 1:
                binding_status = "native_navmesh_candidate_unique"
            else:
                binding_status = "native_navmesh_candidate_ambiguous_same_model_instances"
            counts[binding_status] += 1
            map_counts[binding_status] += 1
            record = {
                "id": f"msbe-native-endpoint:{map_id}:{source_index}",
                "map_id": map_id,
                "msbe_part": normalized_part(map_id, part, source_index),
                "model_id": model_id,
                "model_name_match": "case_insensitive_exact_identifier",
                "binding_status": binding_status,
                "native_navmesh_candidates": candidates,
                "identity_audit": identity_audit(part, model_id, candidates),
                "routeable": False,
                "verification_state": "local_msbe_connect_collision_to_nva_model_identity",
            }
            records.append(record)
            map_records.append(record)
        maps.append(
            {
                "map_id": map_id,
                "source_file": str(map_path),
                "source_sha256": sha256(map_path),
                "connect_collision_count": len(map_records),
                "binding_status_counts": dict(sorted(map_counts.items())),
                "routeable": False,
            }
        )

    status = {
        "source_map_count": len(maps),
        "connect_collision_count": len(records),
        "candidate_relation_count": sum(len(row.get("native_navmesh_candidates", [])) for row in records),
        "unique_candidate_count": counts["native_navmesh_candidate_unique"],
        "ambiguous_candidate_count": counts["native_navmesh_candidate_ambiguous_same_model_instances"],
        "missing_candidate_count": counts["native_navmesh_candidate_missing"],
        "strict_identity_unresolvable_ambiguous_count": sum(
            row["identity_audit"]["resolution"]
            == "unresolved_repeated_same_model_without_cross_layer_instance_key"
            for row in records
        ),
        "strict_identity_unresolvable_missing_count": sum(
            row["identity_audit"]["resolution"]
            == "unresolved_no_same_map_nva_model_id"
            for row in records
        ),
        "parse_error_count": len(errors),
        "routeable_records": 0,
        "all_records_routeable_false": all(row.get("routeable") is False for row in records),
    }
    output = {
        "schema": "elden-ring-local-msbe-native-endpoint-bindings@1",
        "source": {
            "snapshot_root": str(snapshot_root),
            "parsed_msbe_map_root": str(map_root),
            "msbe_map_index": str(map_index_path),
            "msbe_map_index_sha256": sha256(map_index_path),
            "nva_connectivity": str(connectivity_path),
            "nva_connectivity_sha256": sha256(connectivity_path),
        },
        "model": {
            "purpose": "same-map MSBE ConnectCollision model identity to native NVA Navmesh candidate set",
            "candidate_set_is_not_instance_choice": True,
            "strict_cross_layer_instance_key_available": False,
            "repeated_model_instances_are_unresolvable_by_identity_only": True,
            "connect_collision_is_not_player_transition": True,
            "player_walkability_validated": False,
            "routeable": False,
        },
        "status": status,
        "maps": maps,
        "records": records,
        "errors": errors,
        "note": "Repeated native model instances remain ambiguous because the copied MSBE and NVA sources share map/model identity but expose no proven cross-layer instance key. A unique candidate is identity-unique only; it is not automatically a player route or a direction-bearing transition. Position, geometry, index order, and target-map guesses are excluded.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
