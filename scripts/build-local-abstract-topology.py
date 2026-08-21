#!/usr/bin/env python3
"""Compile an entity-level abstract topology index from parsed Elden Ring MSBE.

This compiler reads a separately audited native NVA/Navmesh evidence index but
does not infer continuous walkability from it.  It preserves exact MSBE
entities which can explain topology (map connections, interaction events,
warp/retry events, vertical and airflow regions, and exact event references)
as structural candidates.
Only explicit ConnectCollision/Connection map links are structural map edges;
all candidate relations remain non-routeable until a separate, evidence-backed
Transition compiler binds direction, guard, effect, and endpoints.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


MAP_FILE_RE = re.compile(r"^(m\d+_\d+_\d+_\d+)\.json$")

EVENT_CANDIDATE_TYPES = {
    "ObjAct": "interaction_event",
    "RetryPoint": "retry_event",
    "PseudoMultiplayer": "warp_event",
    "OnlinePseudoMultiplayer": "warp_event",
    "Mount": "mount_event",
}

REGION_CANDIDATE_TYPES = {
    "Connection": "map_connection_endpoint",
    "PlayArea": "play_area",
    "MapPoint": "map_point",
    "MapPointDiscoveryOverride": "map_point_discovery_override",
    "FastTravelRestriction": "fast_travel_restriction",
    "GroupDefeatReward": "group_defeat_reward",
    "WindSFX": "airflow_region",
    "WindArea": "airflow_region",
    "MountJump": "vertical_jump_region",
    "MountJumpFall": "vertical_fall_region",
    "LockedMountJump": "locked_vertical_jump_region",
    "LockedMountJumpFall": "locked_vertical_fall_region",
    "FallPreventionRemoval": "fall_prevention_region",
    "SpawnPoint": "spawn_point",
    "BuddySummonPoint": "summon_point",
    "InvasionPoint": "invasion_point",
    "Message": "message_region",
    "MapNameOverride": "map_name_override",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def canonical_map_id(raw: Any) -> tuple[str | None, bool]:
    if not isinstance(raw, list) or len(raw) != 4:
        return None, False
    try:
        values = [int(value) for value in raw]
    except (TypeError, ValueError):
        return None, False
    if any(value < 0 or value > 255 for value in values):
        return None, False
    wildcard = 255 in values
    normalized = [0 if value == 255 else value for value in values]
    return "m" + "_".join(f"{value:02d}" for value in normalized), wildcard


def source_relative(path: Path, input_root: Path) -> str:
    return path.relative_to(input_root).as_posix()


def online_map_key(map_id: str) -> str:
    parts = map_id.split("_")
    return "_".join(parts[:3]) if len(parts) >= 3 else map_id


def position_payload(item: dict[str, Any]) -> dict[str, float] | None:
    position = item.get("position")
    if not isinstance(position, dict):
        return None
    if not all(axis in position for axis in ("x", "y", "z")):
        return None
    return {axis: float(position[axis]) for axis in ("x", "y", "z")}


def local_fmg_evidence(item: dict[str, Any], fmg_by_key: dict[tuple[str, int], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    extra = item.get("extra") or {}
    field_to_fmgs = {
        "TextID": ("PlaceName.fmg", "EventTextForMap.fmg"),
        "LocationTextID": ("PlaceName.fmg",),
        "EventTextForMapID": ("EventTextForMap.fmg",),
        "ActionButtonID": ("ActionButtonText.fmg",),
    }
    evidence: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for field, fmg_names in field_to_fmgs.items():
        value = extra.get(field)
        try:
            entry_id = int(value)
        except (TypeError, ValueError):
            continue
        if entry_id <= 0:
            continue
        for fmg_name in fmg_names:
            for record in fmg_by_key.get((fmg_name, entry_id), []):
                text = str(record.get("text") or "")
                key = (fmg_name, entry_id, str(record.get("language")))
                if not text.strip() or key in seen:
                    continue
                seen.add(key)
                evidence.append(
                    {
                        "field": field,
                        "fmg": fmg_name,
                        "id": entry_id,
                        "language": record.get("language"),
                        "text": text,
                        "source_file": record.get("source_file"),
                        "verification_state": "local_fmg_verified",
                    }
                )
    return evidence


def compact_nva_evidence(record: dict[str, Any] | None) -> dict[str, Any]:
    if record is None:
        return {
            "record_present": False,
            "verification_state": "local_nva_file_absent",
            "continuous_player_walkability": False,
            "physical_geometry_validated": False,
            "routeable": False,
        }
    nva = record.get("nva") or {}
    return {
        "record_present": True,
        "source_file": record.get("source_file"),
        "source_sha256": record.get("source_sha256"),
        "source_size": record.get("source_size"),
        "paired_nvmhktbnd": record.get("paired_nvmhktbnd"),
        "version": nva.get("version"),
        "section_count": nva.get("section_count"),
        "section_counts": nva.get("section_counts", {}),
        "summary": nva.get("summary", {}),
        "verification_state": record.get("verification_state"),
        "continuous_player_walkability": False,
        "physical_geometry_validated": False,
        "routeable": False,
    }


def compact_nva_connectivity_evidence(record: dict[str, Any] | None) -> dict[str, Any]:
    if record is None:
        return {
            "record_present": False,
            "verification_state": "local_nva_connectivity_candidate_absent",
            "player_walkability_validated": False,
            "routeable": False,
        }
    return {
        "record_present": True,
        "source_file": record.get("source_file"),
        "source_sha256": record.get("source_sha256"),
        "navmesh_node_count": record.get("status", {}).get("navmesh_node_count", 0),
        "connector_count": record.get("status", {}).get("connector_count", 0),
        "connector_exact_binding_count": record.get("status", {}).get("connector_exact_binding_count", 0),
        "connector_ambiguous_binding_count": record.get("status", {}).get("connector_ambiguous_binding_count", 0),
        "connector_unresolved_binding_count": record.get("status", {}).get("connector_unresolved_binding_count", 0),
        "reverse_connector_present_count": record.get("status", {}).get("reverse_connector_present_count", 0),
        "gate_node_count": record.get("status", {}).get("gate_node_count", 0),
        "native_component_candidate_count": record.get("status", {}).get("native_component_candidate_count", 0),
        "verification_state": "local_nva_connectivity_candidate_exact",
        "player_walkability_validated": False,
        "routeable": False,
    }


def compact_nva_boundary_pair_evidence(record: dict[str, Any] | None) -> dict[str, Any]:
    if record is None:
        return {
            "record_present": False,
            "verification_state": "local_nva_boundary_pair_index_absent",
            "player_walkability_validated": False,
            "routeable": False,
        }
    status = record.get("status", {})
    return {
        "record_present": True,
        "source_file": record.get("source_file"),
        "source_sha256": record.get("source_sha256"),
        "connector_count": status.get("connector_count", 0),
        "boundary_pair_count": status.get("boundary_pair_count", 0),
        "hkx2_range_validated_count": status.get("range_validated_count", 0),
        "hkx2_range_conflict_count": status.get("range_invalid_count", 0),
        "geometry_missing_pair_count": status.get("geometry_missing_pair_count", 0),
        "verification_state": "local_nva_boundary_pairs_exact_with_hkx2_index_audit",
        "player_walkability_validated": False,
        "routeable": False,
    }


def compact_nvmhktbnd_evidence(record: dict[str, Any] | None) -> dict[str, Any]:
    if record is None:
        return {
            "record_present": False,
            "verification_state": "local_nvmhktbnd_file_absent",
            "geometry_deserialized": False,
            "routeable": False,
        }
    status = record.get("status", {})
    return {
        "record_present": True,
        "source_file": record.get("source_file"),
        "source_sha256": record.get("source_sha256"),
        "source_size": record.get("source_size"),
        "hkx_entry_count": status.get("hkx_entry_count", 0),
        "hkx_tag0_count": status.get("hkx_tag0_count", 0),
        "nva_model_id_count": status.get("nva_model_id_count", 0),
        "nva_model_id_exact_unique_count": status.get("nva_model_id_exact_unique_count", 0),
        "nva_model_id_ambiguous_count": status.get("nva_model_id_ambiguous_count", 0),
        "nva_model_id_missing_count": status.get("nva_model_id_missing_count", 0),
        "verification_state": "local_nvmhktbnd_bnd4_tag0_indexed",
        "geometry_deserialized": False,
        "routeable": False,
    }


def compact_nvmhktbnd_geometry_evidence(record: dict[str, Any] | None) -> dict[str, Any]:
    if record is None:
        return {
            "record_present": False,
            "verification_state": "local_nvmhktbnd_hkx2_geometry_absent",
            "geometry_deserialized": False,
            "player_walkability_validated": False,
            "routeable": False,
        }
    entries = record.get("NavmeshEntries", [])
    return {
        "record_present": True,
        "source_file": record.get("SourceFile"),
        "source_size": record.get("SourceSize"),
        "bnd4_file_count": record.get("Bnd4FileCount", 0),
        "navmesh_hkx_entry_count": len(entries),
        "face_count": sum(entry.get("Faces", 0) for entry in entries),
        "edge_count": sum(entry.get("Edges", 0) for entry in entries),
        "vertex_count": sum(entry.get("Vertices", 0) for entry in entries),
        "verification_state": "local_nvmhktbnd_hkx2_geometry_deserialized",
        "geometry_deserialized": True,
        "player_walkability_validated": False,
        "routeable": False,
    }


def compact_part(item: dict[str, Any], map_id: str, node_id: str, role: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "node_type": "part",
        "candidate_role": role,
        "map_id": map_id,
        "name": item.get("name"),
        "part_type": item.get("type"),
        "model_name": item.get("model_name"),
        "instance_id": item.get("instance_id"),
        "entity_id": item.get("entity_id"),
        "position": position_payload(item),
        "rotation": item.get("rotation"),
        "scale": item.get("scale"),
        "map_studio_layer": item.get("map_studio_layer"),
        "extra": item.get("extra") or {},
        "coordinate_system": "Elden Ring MSBE game-native XYZ",
        "original_game_coordinates": True,
        "local_game_verified": True,
        "routeable": False,
        "verification_state": "local_msbe_verified",
    }


def compact_region(item: dict[str, Any], map_id: str, node_id: str, role: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "node_type": "region",
        "candidate_role": role,
        "map_id": map_id,
        "name": item.get("name"),
        "region_type": item.get("type"),
        "region_id": item.get("region_id"),
        "entity_id": item.get("entity_id"),
        "map_id_field": item.get("map_id"),
        "shape": item.get("shape"),
        "position": position_payload(item),
        "rotation": item.get("rotation"),
        "map_studio_layer": item.get("map_studio_layer"),
        "extra": item.get("extra") or {},
        "coordinate_system": "Elden Ring MSBE game-native XYZ",
        "original_game_coordinates": True,
        "local_game_verified": True,
        "routeable": False,
        "verification_state": "local_msbe_verified",
    }


def compact_event(item: dict[str, Any], map_id: str, node_id: str, role: str) -> dict[str, Any]:
    extra = item.get("extra") or {}
    return {
        "id": node_id,
        "node_type": "event",
        "candidate_role": role,
        "map_id": map_id,
        "name": item.get("name"),
        "event_type": item.get("type"),
        "event_id": item.get("event_id"),
        "entity_id": item.get("entity_id"),
        "part_name": item.get("part_name"),
        "region_name": item.get("region_name"),
        "position": position_payload(item),
        "extra": extra,
        "event_flag_id": extra.get("EventFlagID"),
        "obj_act_id": extra.get("ObjActID"),
        "obj_act_part_name": extra.get("ObjActPartName"),
        "obj_act_entity_id": extra.get("ObjActEntityID"),
        "state_type": extra.get("StateType"),
        "coordinate_system": "Elden Ring MSBE game-native XYZ",
        "original_game_coordinates": True,
        "local_game_verified": True,
        "routeable": False,
        "verification_state": "local_msbe_verified",
    }


def compact_emevd_entity_reference(
    reference: dict[str, Any], argument: dict[str, Any], source_file: str
) -> dict[str, Any]:
    return {
        "reference_id": reference.get("id"),
        "source_file": source_file,
        "event_id": reference.get("event_id"),
        "instruction_index": reference.get("instruction_index"),
        "instruction_name": reference.get("instruction_name"),
        "category": reference.get("category"),
        "argument_index": argument.get("index"),
        "argument_name": argument.get("name"),
        "argument_value": argument.get("value"),
        "event_flag_ids": reference.get("event_flag_ids", []),
        "verification_state": "local_emevd_verified_exact_entity_reference",
        "routeable": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map-root", type=Path, required=True)
    parser.add_argument("--msbe-index", type=Path, required=True)
    parser.add_argument("--emevd-index", type=Path, required=True)
    parser.add_argument("--common-event-bindings", type=Path, required=True)
    parser.add_argument("--layer-index", type=Path, required=True)
    parser.add_argument("--nva-index", type=Path, required=True)
    parser.add_argument("--nva-connectivity-candidates", type=Path, required=True)
    parser.add_argument("--nva-boundary-pairs", type=Path, required=True)
    parser.add_argument("--nvmhktbnd-index", type=Path, required=True)
    parser.add_argument("--nvmhktbnd-geometry-index", type=Path, required=True)
    parser.add_argument("--online-map-index", type=Path, required=True)
    parser.add_argument("--tile-region-index", type=Path, action="append", required=True)
    parser.add_argument("--fmg-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    map_root = args.map_root.resolve()
    msbe_path = args.msbe_index.resolve()
    emevd_path = args.emevd_index.resolve()
    common_event_bindings_path = args.common_event_bindings.resolve()
    layer_index_path = args.layer_index.resolve()
    nva_index_path = args.nva_index.resolve()
    nva_connectivity_path = args.nva_connectivity_candidates.resolve()
    nva_boundary_pairs_path = args.nva_boundary_pairs.resolve()
    nvmhktbnd_path = args.nvmhktbnd_index.resolve()
    nvmhktbnd_geometry_path = args.nvmhktbnd_geometry_index.resolve()
    online_path = args.online_map_index.resolve()
    tile_paths = [path.resolve() for path in args.tile_region_index]
    fmg_path = args.fmg_index.resolve()
    msbe = json.loads(msbe_path.read_text(encoding="utf-8"))
    emevd = json.loads(emevd_path.read_text(encoding="utf-8"))
    common_event_bindings = json.loads(common_event_bindings_path.read_text(encoding="utf-8"))
    layer_index = json.loads(layer_index_path.read_text(encoding="utf-8"))
    nva_index = json.loads(nva_index_path.read_text(encoding="utf-8"))
    nva_connectivity = json.loads(nva_connectivity_path.read_text(encoding="utf-8"))
    nva_boundary_pairs = json.loads(nva_boundary_pairs_path.read_text(encoding="utf-8"))
    nvmhktbnd = json.loads(nvmhktbnd_path.read_text(encoding="utf-8"))
    nvmhktbnd_geometry = json.loads(nvmhktbnd_geometry_path.read_text(encoding="utf-8"))
    online = json.loads(online_path.read_text(encoding="utf-8"))
    fmg = json.loads(fmg_path.read_text(encoding="utf-8"))
    msbe_maps = {record["map_id"]: record for record in msbe["maps"]}
    emevd_maps = {record["map_key"]: record for record in emevd["maps"]}
    emevd_entity_reference_root = Path(emevd.get("source", {}).get("references_output_root") or "")
    emevd_entity_references_by_map_entity: dict[tuple[str, int], list[dict[str, Any]]] = {}
    if emevd_entity_reference_root.is_dir():
        for reference_path in sorted(emevd_entity_reference_root.glob("*.json")):
            reference_payload = json.loads(reference_path.read_text(encoding="utf-8"))
            map_key = str(reference_payload.get("map_key") or reference_path.stem)
            if map_key not in msbe_maps:
                continue
            for reference in reference_payload.get("references", []):
                for argument in reference.get("args", []):
                    if "entity id" not in str(argument.get("name") or "").casefold():
                        continue
                    value = argument.get("value")
                    if not isinstance(value, int) or value <= 0:
                        continue
                    emevd_entity_references_by_map_entity.setdefault((map_key, value), []).append(
                        compact_emevd_entity_reference(reference, argument, reference_path.name)
                    )
    common_event_bindings_by_map_entity: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for binding in common_event_bindings.get("records", []):
        target_part = binding.get("target_part") or {}
        map_id = binding.get("map_id")
        entity_id = target_part.get("entity_id")
        if isinstance(map_id, str) and isinstance(entity_id, int) and entity_id > 0:
            common_event_bindings_by_map_entity.setdefault((map_id, entity_id), []).append(binding)
    layers_by_map: dict[str, list[dict[str, Any]]] = {}
    for layer_record in layer_index.get("records", []):
        map_id = layer_record.get("map_id")
        if isinstance(map_id, str):
            layers_by_map.setdefault(map_id, []).append(layer_record)
    nva_by_map: dict[str, dict[str, Any]] = {}
    for nva_record in nva_index.get("records", []):
        map_id = nva_record.get("map_id")
        if isinstance(map_id, str):
            if map_id in nva_by_map:
                raise ValueError(f"duplicate NVA map record: {map_id}")
            nva_by_map[map_id] = nva_record
    nva_connectivity_by_map: dict[str, dict[str, Any]] = {}
    for connectivity_record in nva_connectivity.get("maps", []):
        map_id = connectivity_record.get("map_id")
        if isinstance(map_id, str):
            if map_id in nva_connectivity_by_map:
                raise ValueError(f"duplicate NVA connectivity map record: {map_id}")
            nva_connectivity_by_map[map_id] = connectivity_record
    nva_boundary_pairs_by_map: dict[str, dict[str, Any]] = {}
    for boundary_record in nva_boundary_pairs.get("maps", []):
        map_id = boundary_record.get("map_id")
        if isinstance(map_id, str):
            if map_id in nva_boundary_pairs_by_map:
                raise ValueError(f"duplicate NVA boundary-pair map record: {map_id}")
            nva_boundary_pairs_by_map[map_id] = boundary_record
    nvmhktbnd_by_map: dict[str, dict[str, Any]] = {}
    for nvmhktbnd_record in nvmhktbnd.get("records", []):
        map_id = nvmhktbnd_record.get("map_id")
        if isinstance(map_id, str):
            if map_id in nvmhktbnd_by_map:
                raise ValueError(f"duplicate NVMHKT BND4 map record: {map_id}")
            nvmhktbnd_by_map[map_id] = nvmhktbnd_record
    nvmhktbnd_geometry_by_map: dict[str, dict[str, Any]] = {}
    for geometry_record in nvmhktbnd_geometry.get("records", []):
        map_id = geometry_record.get("MapId")
        if isinstance(map_id, str):
            if map_id in nvmhktbnd_geometry_by_map:
                raise ValueError(f"duplicate NVMHKT HKX2 geometry map record: {map_id}")
            nvmhktbnd_geometry_by_map[map_id] = geometry_record
    online_maps = {record["mapKey"]: record for record in online.get("records", [])}
    tile_regions: dict[str, dict[str, Any]] = {}
    tile_sources: list[dict[str, Any]] = []
    for tile_path in tile_paths:
        tile_payload = json.loads(tile_path.read_text(encoding="utf-8"))
        fields = tile_payload.get("fields", [])
        for raw_record in tile_payload.get("records", []):
            if not isinstance(raw_record, list) or len(raw_record) != len(fields):
                continue
            record = dict(zip(fields, raw_record))
            tile_regions[str(record.get("mapId"))] = record
        tile_sources.append(
            {
                "path": str(tile_path),
                "sha256": sha256(tile_path),
                "source": tile_payload.get("source", {}),
            }
        )
    fmg_by_key: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for record in fmg.get("records", []):
        try:
            entry_id = int(record.get("id"))
        except (TypeError, ValueError):
            continue
        fmg_by_key.setdefault((str(record.get("fmg")), entry_id), []).append(record)
    map_ids = set(msbe_maps)

    nodes: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    structural_edges: list[dict[str, Any]] = []
    node_by_part: dict[tuple[str, str], str] = {}
    node_by_region: dict[tuple[str, str, int], str] = {}
    node_by_event: dict[tuple[str, int, int], str] = {}
    candidate_role_counts = Counter()
    exact_part_refs = exact_part_matches = 0
    exact_region_refs = exact_region_matches = 0
    objact_connector_exact_matches = 0
    objact_connection_region_exact_matches = 0
    source_files = 0

    for map_id, record in sorted(msbe_maps.items()):
        event_record = emevd_maps.get(map_id)
        map_key = online_map_key(map_id)
        online_record = online_maps.get(map_key)
        tile_record = tile_regions.get(map_key)
        native_layers = layers_by_map.get(map_id, [])
        native_nva = compact_nva_evidence(nva_by_map.get(map_id))
        native_nva_connectivity = compact_nva_connectivity_evidence(nva_connectivity_by_map.get(map_id))
        native_nva_boundary_pairs = compact_nva_boundary_pair_evidence(
            nva_boundary_pairs_by_map.get(map_id)
        )
        native_nvmhktbnd = compact_nvmhktbnd_evidence(nvmhktbnd_by_map.get(map_id))
        native_nvmhktbnd_geometry = compact_nvmhktbnd_geometry_evidence(
            nvmhktbnd_geometry_by_map.get(map_id)
        )
        nodes.append(
            {
                "id": record["id"],
                "node_type": "map",
                "candidate_role": "map",
                "map_id": map_id,
                "source_file": record["source_file"],
                "counts": record["counts"],
                "part_types": record["part_types"],
                "region_types": record["region_types"],
                "event_types": record["event_types"],
                "xyz_bounds": record["xyz_bounds"],
                "native_layer_evidence": native_layers,
                "native_layer_count": len(native_layers),
                "native_nva_evidence": native_nva,
                "native_nva_connectivity_evidence": native_nva_connectivity,
                "native_nva_boundary_pair_evidence": native_nva_boundary_pairs,
                "native_nvmhktbnd_evidence": native_nvmhktbnd,
                "native_nvmhktbnd_geometry_evidence": native_nvmhktbnd_geometry,
                "coordinate_system": record["coordinate_system"],
                "original_game_coordinates": record["original_game_coordinates"],
                "local_game_verified": record["local_game_verified"],
                "emevd_evidence": {
                    "file_present": event_record is not None,
                    "event_count": event_record.get("event_count", 0) if event_record else 0,
                    "condition_count": event_record.get("condition_count", 0) if event_record else 0,
                    "action_count": event_record.get("action_count", 0) if event_record else 0,
                    "event_flag_ids": event_record.get("event_flag_ids", []) if event_record else [],
                    "reference_count": event_record.get("reference_count", 0) if event_record else 0,
                    "verification_state": "local_emevd_verified" if event_record else "local_emevd_file_absent",
                },
                "online_source_evidence": {
                    "map_key": map_key,
                    "record_present": online_record is not None,
                    "record_count": online_record.get("recordCount", 0) if online_record else 0,
                    "sources": online_record.get("sources", {}) if online_record else {},
                    "source_kinds": online_record.get("sourceKinds", []) if online_record else [],
                    "verification_state": "online_map_key_index_verified" if online_record else "online_map_key_absent",
                },
                "online_tile_region_evidence": {
                    "map_key": map_key,
                    "record_present": tile_record is not None,
                    "record": tile_record,
                    "verification_state": "online_tile_region_verified" if tile_record else "online_tile_region_absent",
                },
                "routeable": False,
                "verification_state": "local_msbe_verified",
            }
        )

    for path in sorted(map_root.glob("*.json")):
        match = MAP_FILE_RE.match(path.name)
        if not match:
            continue
        map_id = "m" + match.group(1).removeprefix("m")
        if map_id not in map_ids:
            continue
        source_files += 1
        payload = json.loads(path.read_text(encoding="utf-8"))
        parts = payload.get("parts", [])
        regions = payload.get("regions", [])
        events = payload.get("events", [])
        referenced_part_names = {
            str((event.get("extra") or {}).get("ObjActPartName"))
            for event in events
            if event.get("type") == "ObjAct" and (event.get("extra") or {}).get("ObjActPartName")
        }
        referenced_region_names = {
            str(event.get("region_name"))
            for event in events
            if event.get("region_name")
        }
        local_part_nodes: dict[str, str] = {}
        local_part_positions: dict[str, dict[str, float] | None] = {}
        local_region_nodes: dict[tuple[str, int], str] = {}
        local_event_nodes: dict[int, str] = {}
        local_connect_names: set[str] = set()
        local_connection_region_names: set[str] = set()

        def add_part(item: dict[str, Any], role: str, index: int) -> str:
            name = str(item.get("name") or f"part_{index}")
            node_id = f"local-part:{map_id}:{name}:{index}"
            node = compact_part(item, map_id, node_id, role)
            node["local_fmg_evidence"] = local_fmg_evidence(item, fmg_by_key)
            nodes.append(node)
            candidate_role_counts[role] += 1
            local_part_nodes.setdefault(name, node_id)
            local_part_positions.setdefault(name, position_payload(item))
            node_by_part.setdefault((map_id, name), node_id)
            relations.append(
                {
                    "id": f"contains:{map_id}:{node_id}",
                    "from": f"local_map_{map_id}",
                    "to": node_id,
                    "relation_type": "map_contains_candidate",
                    "routeable": False,
                    "verification_state": "local_msbe_verified",
                }
            )
            return node_id

        def add_region(item: dict[str, Any], role: str, index: int) -> str:
            name = str(item.get("name") or f"region_{index}")
            region_id = int(item.get("region_id", -1))
            node_id = f"local-region:{map_id}:{name}:{region_id}:{index}"
            node = compact_region(item, map_id, node_id, role)
            node["local_fmg_evidence"] = local_fmg_evidence(item, fmg_by_key)
            nodes.append(node)
            candidate_role_counts[role] += 1
            local_region_nodes.setdefault((name, region_id), node_id)
            node_by_region.setdefault((map_id, name, region_id), node_id)
            relations.append(
                {
                    "id": f"contains:{map_id}:{node_id}",
                    "from": f"local_map_{map_id}",
                    "to": node_id,
                    "relation_type": "map_contains_candidate",
                    "routeable": False,
                    "verification_state": "local_msbe_verified",
                }
            )
            return node_id

        def add_event(item: dict[str, Any], role: str, index: int) -> str:
            event_id = int(item.get("event_id", -1))
            node_id = f"local-event:{map_id}:{item.get('type', 'Unknown')}:{event_id}:{index}"
            node = compact_event(item, map_id, node_id, role)
            node["local_fmg_evidence"] = local_fmg_evidence(item, fmg_by_key)
            event_part_name = (item.get("extra") or {}).get("ObjActPartName")
            anchor_position = local_part_positions.get(str(event_part_name)) if event_part_name else None
            if anchor_position:
                node["anchor_position"] = anchor_position
                node["anchor_source"] = "exact_objact_part_reference"
            nodes.append(node)
            candidate_role_counts[role] += 1
            local_event_nodes.setdefault(event_id, node_id)
            node_by_event.setdefault((map_id, event_id, index), node_id)
            relations.append(
                {
                    "id": f"contains:{map_id}:{node_id}",
                    "from": f"local_map_{map_id}",
                    "to": node_id,
                    "relation_type": "map_contains_candidate",
                    "routeable": False,
                    "verification_state": "local_msbe_verified",
                }
            )
            return node_id

        # Explicit connector endpoints are always retained.
        for index, item in enumerate(parts):
            part_name = str(item.get("name") or "")
            part_entity_id = item.get("entity_id")
            emevd_part_references = (
                emevd_entity_references_by_map_entity.get((map_id, part_entity_id), [])
                if isinstance(part_entity_id, int) and part_entity_id > 0
                else []
            )
            common_event_target_bindings = (
                common_event_bindings_by_map_entity.get((map_id, part_entity_id), [])
                if isinstance(part_entity_id, int) and part_entity_id > 0
                else []
            )
            if item.get("type") == "ConnectCollision" or part_name in referenced_part_names or emevd_part_references or common_event_target_bindings:
                role = (
                    "map_connection_endpoint"
                    if item.get("type") == "ConnectCollision"
                    else "event_target_part"
                    if part_name in referenced_part_names
                    else "emevd_common_event_target_part"
                    if common_event_target_bindings
                    else "emevd_referenced_part"
                )
                connector_id = add_part(item, role, index)
                if common_event_target_bindings:
                    nodes[-1]["emevd_common_event_objact_binding_evidence"] = common_event_target_bindings
                    for binding in common_event_target_bindings:
                        relations.append(
                            {
                                "id": f"emevd-common-objact-target:{binding.get('id')}:{connector_id}",
                                "from": f"local_map_{map_id}",
                                "to": connector_id,
                                "relation_type": "emevd_common_event_objact_target_reference",
                                "binding_id": binding.get("id"),
                                "candidate_id": binding.get("candidate_id"),
                                "common_event_id": binding.get("common_event_id"),
                                "msbe_objact_event_id": binding.get("msbe_objact_event_id"),
                                "obj_act_id": binding.get("obj_act_id"),
                                "obj_act_entity_id": binding.get("obj_act_entity_id"),
                                "target_entity_id": part_entity_id,
                                "routeable": False,
                                "verification_state": "local_msbe_and_raw_emevd_common_event_exact_part_reference",
                            }
                        )
                if emevd_part_references:
                    nodes[-1]["emevd_part_reference_evidence"] = emevd_part_references
                    for evidence in emevd_part_references:
                        relations.append(
                            {
                                "id": f"emevd-part-ref:{connector_id}:{evidence.get('reference_id')}:{evidence.get('argument_index')}",
                                "from": f"local_map_{map_id}",
                                "to": connector_id,
                                "relation_type": "emevd_exact_part_entity_reference",
                                "reference_id": evidence.get("reference_id"),
                                "instruction_name": evidence.get("instruction_name"),
                                "event_id": evidence.get("event_id"),
                                "instruction_index": evidence.get("instruction_index"),
                                "argument_name": evidence.get("argument_name"),
                                "argument_value": evidence.get("argument_value"),
                                "routeable": False,
                                "verification_state": "local_msbe_and_emevd_exact_part_entity_reference",
                            }
                        )
                if item.get("type") != "ConnectCollision":
                    continue
                local_connect_names.add(part_name)
                extra = item.get("extra") or {}
                target, wildcard = canonical_map_id(extra.get("MapID"))
                structural_edges.append(
                    {
                        "id": f"structural:{connector_id}",
                        "from": f"local_map_{map_id}",
                        "to": f"local_map_{target}" if target in map_ids else None,
                        "anchor": connector_id,
                        "to_map_id": target,
                        "raw_target_map_id": extra.get("MapID"),
                        "target_has_wildcard_byte": wildcard,
                        "edge_kind": "explicit_connect_collision",
                        "target_exists": target in map_ids,
                        "requires": [],
                        "condition_status": "not_directly_bound",
                        "routeable": False,
                        "verification_state": "local_msbe_verified",
                    }
                )

        # Connection regions and typed topology-support regions.
        for index, item in enumerate(regions):
            region_name = str(item.get("name") or "")
            is_typed_candidate = item.get("type") in REGION_CANDIDATE_TYPES
            is_event_target = region_name in referenced_region_names
            region_entity_id = item.get("entity_id")
            emevd_region_references = (
                emevd_entity_references_by_map_entity.get((map_id, region_entity_id), [])
                if isinstance(region_entity_id, int) and region_entity_id > 0
                else []
            )
            is_emevd_target = bool(emevd_region_references)
            if not is_typed_candidate and not is_event_target and not is_emevd_target:
                continue
            role = REGION_CANDIDATE_TYPES.get(
                item.get("type"),
                "event_target_region" if is_event_target else "emevd_referenced_region",
            )
            region_node_id = add_region(item, role, index)
            if is_emevd_target:
                nodes[-1]["emevd_region_reference_evidence"] = emevd_region_references
                for evidence in emevd_region_references:
                    relations.append(
                        {
                            "id": f"emevd-region-ref:{region_node_id}:{evidence.get('reference_id')}:{evidence.get('argument_index')}",
                            "from": f"local_map_{map_id}",
                            "to": region_node_id,
                            "relation_type": "emevd_exact_region_entity_reference",
                            "reference_id": evidence.get("reference_id"),
                            "instruction_name": evidence.get("instruction_name"),
                            "event_id": evidence.get("event_id"),
                            "instruction_index": evidence.get("instruction_index"),
                            "argument_name": evidence.get("argument_name"),
                            "argument_value": evidence.get("argument_value"),
                            "routeable": False,
                            "verification_state": "local_msbe_and_emevd_exact_region_entity_reference",
                        }
                    )
            if not is_typed_candidate:
                continue
            if item.get("type") == "Connection":
                local_connection_region_names.add(region_name)
                extra = item.get("extra") or {}
                target, wildcard = canonical_map_id(extra.get("TargetMapID"))
                structural_edges.append(
                    {
                        "id": f"structural:{region_node_id}",
                        "from": f"local_map_{map_id}",
                        "to": f"local_map_{target}" if target in map_ids else None,
                        "anchor": region_node_id,
                        "to_map_id": target,
                        "raw_target_map_id": extra.get("TargetMapID"),
                        "target_has_wildcard_byte": wildcard,
                        "edge_kind": "explicit_connection_region",
                        "target_exists": target in map_ids,
                        "requires": [],
                        "condition_status": "not_directly_bound",
                        "routeable": False,
                        "verification_state": "local_msbe_verified",
                    }
                )

        # Events are retained only when their exact type is a topology candidate.
        for index, item in enumerate(events):
            role = EVENT_CANDIDATE_TYPES.get(item.get("type"))
            if role is not None:
                add_event(item, role, index)

        # Keep exact ObjAct part/region references as semantic relations only.
        for index, item in enumerate(events):
            if item.get("type") != "ObjAct":
                continue
            event_node_id = f"local-event:{map_id}:ObjAct:{int(item.get('event_id', -1))}:{index}"
            extra = item.get("extra") or {}
            part_name = extra.get("ObjActPartName")
            if part_name:
                exact_part_refs += 1
                target_id = local_part_nodes.get(str(part_name))
                if target_id:
                    exact_part_matches += 1
                if str(part_name) in local_connect_names:
                    objact_connector_exact_matches += 1
                relations.append(
                    {
                        "id": f"event-part:{event_node_id}:{part_name}",
                        "from": event_node_id,
                        "to": target_id,
                        "target_name": part_name,
                        "relation_type": "event_exact_part_reference",
                        "target_exists": target_id is not None,
                        "routeable": False,
                        "verification_state": "local_msbe_verified",
                    }
                )
            region_name = item.get("region_name")
            if region_name:
                exact_region_refs += 1
                target_id = next(
                    (candidate_id for (name, _region_id), candidate_id in local_region_nodes.items() if name == region_name),
                    None,
                )
                if target_id:
                    exact_region_matches += 1
                if str(region_name) in local_connection_region_names:
                    objact_connection_region_exact_matches += 1
                relations.append(
                    {
                        "id": f"event-region:{event_node_id}:{region_name}",
                        "from": event_node_id,
                        "to": target_id,
                        "target_name": region_name,
                        "relation_type": "event_exact_region_reference",
                        "target_exists": target_id is not None,
                        "routeable": False,
                        "verification_state": "local_msbe_verified",
                    }
                )

    target_missing = sum(not edge["target_exists"] for edge in structural_edges)
    direct_routeable = sum(bool(edge.get("routeable")) for edge in structural_edges + relations)
    map_nodes_payload = [node for node in nodes if node.get("node_type") == "map"]
    output = {
        "schema": "elden-ring-local-abstract-entity-topology@1",
        "source": {
            "snapshot_id": "elden-ring-local-snapshot-20260818",
            "map_root": str(map_root),
            "map_root_file_count": source_files,
            "msbe_index": str(msbe_path),
            "msbe_index_sha256": sha256(msbe_path),
            "emevd_index": str(emevd_path),
            "emevd_index_sha256": sha256(emevd_path),
            "common_event_bindings": str(common_event_bindings_path),
            "common_event_bindings_sha256": sha256(common_event_bindings_path),
            "layer_index": str(layer_index_path),
            "layer_index_sha256": sha256(layer_index_path),
            "nva_index": str(nva_index_path),
            "nva_index_sha256": sha256(nva_index_path),
            "nva_connectivity_candidates": str(nva_connectivity_path),
            "nva_connectivity_candidates_sha256": sha256(nva_connectivity_path),
            "nva_boundary_pairs": str(nva_boundary_pairs_path),
            "nva_boundary_pairs_sha256": sha256(nva_boundary_pairs_path),
            "nvmhktbnd_index": str(nvmhktbnd_path),
            "nvmhktbnd_index_sha256": sha256(nvmhktbnd_path),
            "nvmhktbnd_geometry_index": str(nvmhktbnd_geometry_path),
            "nvmhktbnd_geometry_index_sha256": sha256(nvmhktbnd_geometry_path),
            "online_map_index": str(online_path),
            "online_map_index_sha256": sha256(online_path),
            "online_source": online.get("source", {}),
            "tile_region_indexes": tile_sources,
            "fmg_index": str(fmg_path),
            "fmg_index_sha256": sha256(fmg_path),
        },
        "model": {
            "node_definition": "maps plus exact MSBE topology-support candidates",
            "candidate_types": {
                "ConnectCollision": "explicit map connection endpoint",
                "Connection": "explicit map connection region",
                "ObjAct": "exact interaction event and optional flag evidence",
                "RetryPoint/PseudoMultiplayer/Mount": "explicit event candidates",
                "typed_regions": "exact MSBE vertical, airflow, area, warp and checkpoint candidates",
                "emevd_referenced_region": "MSBE Region exactly identified by a map-local EMEVD entity-ID argument",
                "emevd_referenced_part": "MSBE Part exactly identified by a map-local EMEVD entity-ID argument",
                "emevd_common_event_target_part": "MSBE Part exactly identified by raw same-map InitializeCommonEvent ObjAct parameter substitution and Set ObjAct State target",
            },
            "relation_definition": "map containment, exact MSBE references, exact map-local EMEVD region-entity references, exact raw common-event ObjAct target references, and explicit map links",
            "continuous_walkability": "not modeled",
            "native_nva": "exact native Navmesh evidence is attached at map level; it is not a player route",
            "havok_or_nva": "NVA was read as evidence only; continuous walkability and collision validity are not claimed",
            "condition_binding": "event evidence is not promoted to a transition guard without a direct endpoint binding",
            "routeable": False,
        },
        "status": {
            "source_map_files": source_files,
            "map_nodes": len(msbe_maps),
            "online_map_key_records": sum(bool(node.get("online_source_evidence", {}).get("record_present")) for node in map_nodes_payload),
            "online_map_key_missing": sum(not node.get("online_source_evidence", {}).get("record_present") for node in map_nodes_payload),
            "online_tile_region_records": sum(bool(node.get("online_tile_region_evidence", {}).get("record_present")) for node in map_nodes_payload),
            "online_tile_region_missing": sum(not node.get("online_tile_region_evidence", {}).get("record_present") for node in map_nodes_payload),
            "candidate_nodes": len(nodes) - len(msbe_maps),
            "total_nodes": len(nodes),
            "structural_edges": len(structural_edges),
            "semantic_relations": len(relations),
            "explicit_connect_collision_edges": sum(edge["edge_kind"] == "explicit_connect_collision" for edge in structural_edges),
            "explicit_connection_region_edges": sum(edge["edge_kind"] == "explicit_connection_region" for edge in structural_edges),
            "structural_target_missing": target_missing,
            "exact_objact_part_references": exact_part_refs,
            "exact_objact_part_matches": exact_part_matches,
            "objact_connector_exact_matches": objact_connector_exact_matches,
            "objact_connection_region_exact_matches": objact_connection_region_exact_matches,
            "exact_event_region_references": exact_region_refs,
            "exact_event_region_matches": exact_region_matches,
            "emevd_exact_region_entity_reference_records": sum(
                len(node.get("emevd_region_reference_evidence", []))
                for node in nodes
                if node.get("node_type") == "region"
            ),
            "emevd_referenced_region_nodes": sum(
                node.get("candidate_role") == "emevd_referenced_region" for node in nodes
            ),
            "emevd_exact_part_entity_reference_records": sum(
                len(node.get("emevd_part_reference_evidence", []))
                for node in nodes
                if node.get("node_type") == "part"
            ),
            "emevd_referenced_part_nodes": sum(
                node.get("candidate_role") == "emevd_referenced_part" for node in nodes
            ),
            "emevd_common_event_objact_binding_records": len(common_event_bindings.get("records", [])),
            "emevd_common_event_target_part_nodes": sum(
                bool(node.get("emevd_common_event_objact_binding_evidence"))
                for node in nodes
                if node.get("node_type") == "part"
            ),
            "native_layer_record_count": sum(len(layers_by_map.get(map_id, [])) for map_id in map_ids),
            "maps_with_native_layer_evidence": sum(bool(layers_by_map.get(map_id)) for map_id in map_ids),
            "native_nva_file_count": nva_index.get("status", {}).get("nva_file_count", 0),
            "native_nva_parsed_record_count": nva_index.get("status", {}).get("parsed_record_count", 0),
            "native_nva_maps_with_evidence": sum(bool(nva_by_map.get(map_id)) for map_id in map_ids),
            "native_nva_maps_with_navmesh": sum(
                (nva_by_map.get(map_id, {}).get("nva", {}).get("summary", {}).get("navmesh_count", 0) > 0)
                for map_id in map_ids
            ),
            "native_nva_total_navmeshes": nva_index.get("status", {}).get("total_navmesh_count", 0),
            "native_nva_total_connectors": nva_index.get("status", {}).get("total_connector_count", 0),
            "native_nva_all_routeable_false": nva_index.get("status", {}).get("all_records_routeable_false", False),
            "native_nva_connectivity_maps_with_evidence": sum(
                bool(nva_connectivity_by_map.get(map_id)) for map_id in map_ids
            ),
            "native_nva_connectivity_exact_connectors": nva_connectivity.get("status", {}).get(
                "connector_exact_binding_count", 0
            ),
            "native_nva_connectivity_candidate_components": nva_connectivity.get("status", {}).get(
                "native_component_candidate_count", 0
            ),
            "native_nva_connectivity_all_routeable_false": nva_connectivity.get("status", {}).get(
                "all_records_routeable_false", False
            ),
            "native_nva_boundary_pair_maps_with_evidence": sum(
                bool(nva_boundary_pairs_by_map.get(map_id)) for map_id in map_ids
            ),
            "native_nva_boundary_pair_count": nva_boundary_pairs.get("status", {}).get(
                "boundary_pair_count", 0
            ),
            "native_nva_boundary_pair_hkx2_range_validated_count": nva_boundary_pairs.get(
                "status", {}
            ).get("range_validated_count", 0),
            "native_nva_boundary_pair_hkx2_range_conflict_count": nva_boundary_pairs.get(
                "status", {}
            ).get("range_invalid_count", 0),
            "native_nva_boundary_pair_geometry_missing_count": nva_boundary_pairs.get(
                "status", {}
            ).get("geometry_missing_pair_count", 0),
            "native_nva_boundary_pair_all_routeable_false": nva_boundary_pairs.get("status", {}).get(
                "all_pairs_routeable_false", False
            ),
            "native_nvmhktbnd_maps_with_evidence": sum(
                bool(nvmhktbnd_by_map.get(map_id)) for map_id in map_ids
            ),
            "native_nvmhktbnd_parsed_record_count": nvmhktbnd.get("status", {}).get(
                "parsed_bnd4_record_count", 0
            ),
            "native_nvmhktbnd_hkx_entry_count": nvmhktbnd.get("status", {}).get(
                "hkx_entry_count", 0
            ),
            "native_nvmhktbnd_geometry_deserialized": nvmhktbnd.get("status", {}).get(
                "geometry_deserialized", False
            ),
            "native_nvmhktbnd_all_routeable_false": nvmhktbnd.get("status", {}).get(
                "all_records_routeable_false", False
            ),
            "native_nvmhktbnd_geometry_maps_with_evidence": len(nvmhktbnd_geometry_by_map),
            "native_nvmhktbnd_geometry_navmesh_hkx_entry_count": nvmhktbnd_geometry.get("status", {}).get(
                "navmesh_hkx_entry_count", 0
            ),
            "native_nvmhktbnd_geometry_face_count": nvmhktbnd_geometry.get("status", {}).get(
                "face_count", 0
            ),
            "native_nvmhktbnd_geometry_edge_count": nvmhktbnd_geometry.get("status", {}).get(
                "edge_count", 0
            ),
            "native_nvmhktbnd_geometry_vertex_count": nvmhktbnd_geometry.get("status", {}).get(
                "vertex_count", 0
            ),
            "native_nvmhktbnd_geometry_deserialized": nvmhktbnd_geometry.get("status", {}).get(
                "geometry_deserialized", False
            ),
            "native_nvmhktbnd_geometry_all_routeable_false": nvmhktbnd_geometry.get("status", {}).get(
                "all_records_routeable_false", False
            ),
            "direct_routeable_records": direct_routeable,
            "all_records_routeable_false": direct_routeable == 0,
            "all_coordinates_game_native": all(node.get("original_game_coordinates") for node in nodes),
            "nodes_with_local_fmg_evidence": sum(bool(node.get("local_fmg_evidence")) for node in nodes),
            "local_fmg_evidence_records": sum(len(node.get("local_fmg_evidence", [])) for node in nodes),
        },
        "candidate_role_counts": dict(sorted(candidate_role_counts.items())),
        "nodes": nodes,
        "structural_edges": structural_edges,
        "relations": relations,
        "note": "Abstract entity topology plus exact native NVA evidence. Structural, semantic, and native Navmesh evidence remain separate; no collision, continuous player walkability, or route is inferred.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
