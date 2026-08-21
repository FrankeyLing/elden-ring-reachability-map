#!/usr/bin/env python3
"""Compile exact transition bindings and unresolved interaction candidates.

This is deliberately a topology audit, not a walkability inference pass.
It uses only exact relationships encoded in the local MSBE exports:

* ConnectCollision.MapID + the same ConnectCollision name on the declared
  target map;
* Connection.TargetMapID + the target map's Connection region name naming the
  source map;
* ObjAct -> ObjActPartName, when the target part exists exactly.

No distance, proximity, Havok, NVA, navmesh, event-name guess, or guessed
elevator/door destination is promoted to a route edge. Every record remains
routeable=false until the player-space segment and state guard are bound.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


MAP_RE = re.compile(r"^m\d+_\d+_\d+_\d+$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def canonical_map_id(raw: Any) -> str | None:
    if not isinstance(raw, list) or len(raw) != 4:
        return None
    try:
        values = [int(value) for value in raw]
    except (TypeError, ValueError):
        return None
    if any(value < 0 or value > 255 for value in values):
        return None
    return "m" + "_".join(f"{0 if value == 255 else value:02d}" for value in values)


def map_id_from_packed_integer(value: Any) -> str | None:
    if not isinstance(value, int) or value <= 0 or value > 0xFFFFFFFF:
        return None
    values = [(value >> shift) & 0xFF for shift in (24, 16, 8, 0)]
    # MSBE's packed ObjAct MapID uses decimal-formatted first three map
    # components and a two-digit hexadecimal map suffix (e.g. 0x10 -> "10").
    # Cross-checking the raw event map_id, ObjAct MapID, event label, and the
    # local MSBE filenames confirms this representation.
    return "m" + "_".join(f"{item:02d}" for item in values[:3]) + f"_{values[3]:02X}"


def map_id_from_emevd_warp(reference: dict[str, Any]) -> tuple[str | None, str | None]:
    name = str(reference.get("instruction_name") or "")
    args = {str(argument.get("name")): argument.get("value") for argument in reference.get("args", [])}
    if name == "Warp Player":
        values = [args.get(key) for key in ("Area ID", "Block ID", "Region ID", "Index ID")]
        if all(isinstance(value, int) and 0 <= value <= 255 for value in values):
            return "m" + "_".join(f"{value:02d}" for value in values), "Warp Player area/block/region/index"
    if name in {
        "Play Cutscene to Player and Warp",
        "Play Cutscene to Player and Warp with Weather and Time",
        "Play Cutscene to Player and Warp with Stable Position Update",
    }:
        map_value = args.get("Map ID")
        if isinstance(map_value, int) and 0 <= map_value <= 99999999:
            digits = f"{map_value:08d}"
            return "m" + "_".join(digits[index : index + 2] for index in range(0, 8, 2)), "EMEVD Map ID"
    return None, None


def position(item: dict[str, Any]) -> list[float] | None:
    raw = item.get("position")
    if not isinstance(raw, dict) or not all(axis in raw for axis in ("x", "y", "z")):
        return None
    return [float(raw[axis]) for axis in ("x", "y", "z")]


def endpoint_payload(map_id: str, item: dict[str, Any], node_id: str, kind: str) -> dict[str, Any]:
    extra = item.get("extra") or {}
    return {
        "map_id": map_id,
        "node_id": node_id,
        "name": item.get("name"),
        "endpoint_kind": kind,
        "region_id": item.get("region_id"),
        "position": position(item),
        "extra": extra,
        "coordinate_system": "Elden Ring MSBE game-native XYZ",
        "original_game_coordinates": True,
        "local_game_verified": True,
    }


def blocker_list(endpoint_type: str) -> list[str]:
    blockers = [
        "player_space_segment_to_this_endpoint_not_bound",
        "world_state_guard_not_bound",
    ]
    if endpoint_type == "connection_region":
        blockers.append("connection_region_is_not_a_walkable_segment")
    else:
        blockers.append("map_connection_endpoint_is_not_a_walkable_segment")
    return blockers


def compact_emevd_reference(reference: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": reference.get("id"),
        "event_id": reference.get("event_id"),
        "instruction_index": reference.get("instruction_index"),
        "instruction_name": reference.get("instruction_name"),
        "category": reference.get("category"),
        "args": reference.get("args", []),
        "event_flag_ids": reference.get("event_flag_ids", []),
    }


def classify_objact(name: str, obj_act_id: Any) -> tuple[str, list[str]]:
    """Return a conservative label based on exact source text only."""

    text = str(name or "").casefold()
    # Unicode escapes keep this source safe when invoked from Windows shells
    # whose code page cannot represent the Japanese source strings.
    loot_terms = ("\u5b9d\u7bb1", "chest", "treasure")
    if any(term in text for term in loot_terms) or obj_act_id == 200:
        return "loot_or_non_transition_interaction", ["source_name_or_objact_id_indicates_loot"]

    if any(term in text for term in ("\u4e00\u65b9\u901a\u884c", "\u7247\u958b\u304d", "\u7247\u6249", "\u30b7\u30e7\u30fc\u30c8\u30ab\u30c3\u30c8")):
        return "one_way_or_shortcut_door", ["exact_source_name_keyword"]
    if any(term in text for term in ("\u30a8\u30ec\u30d9\u30fc\u30bf", "\u5c64\u79fb\u52d5", "\u6607\u964d", "\u30ea\u30d5\u30c8")):
        return "elevator_or_vertical_transport_control", ["exact_source_name_keyword"]
    if any(term in text for term in ("\u6249", "\u30c9\u30a2", "\u9580", "\u30b7\u30e3\u30c3\u30bf\u30fc", "\u958b\u9589")):
        return "door_or_gate_interaction", ["exact_source_name_keyword"]
    if any(term in text for term in ("\u68af\u5b50", "\u306f\u3057\u3054", "\u30cf\u30b7\u30b4")):
        return "ladder_interaction", ["exact_source_name_keyword"]
    if any(term in text for term in ("\u8ee2\u9001", "\u30ef\u30fc\u30d7", "\u8ee2\u79fb", "\u30c6\u30ec\u30dd\u30fc\u30c8", "\u68fa")):
        return "warp_or_teleport_interaction", ["exact_source_name_keyword"]
    return "other_interaction", ["no_transition_keyword_in_exact_source_name"]


def mechanism_side(name: Any) -> str | None:
    """Extract only an explicit terminal upper/lower label from source text."""

    text = unicodedata.normalize("NFKC", str(name or "")).strip()
    text = re.sub(r"\s*\{\d+\}\s*$", "", text)
    text = re.sub(r"\s*\(\s*[下上]\s*\)\s*$", "", text)
    if re.search(r"(?:下側|下|lower|bottom)\s*$", text, flags=re.IGNORECASE):
        return "lower"
    if re.search(r"(?:上側|上|upper|top)\s*$", text, flags=re.IGNORECASE):
        return "upper"
    return None


def mechanism_label(name: Any) -> str:
    """Normalize only formatting and the explicit terminal side marker."""

    text = unicodedata.normalize("NFKC", str(name or "")).casefold()
    text = re.sub(r"\s*\{\d+\}\s*$", "", text)
    text = re.sub(r"\s*\(\s*[下上]\s*\)\s*$", "", text)
    text = re.sub(r"(?:下側|上側|下|上|lower|upper|bottom|top)\s*$", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", "", text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map-root", type=Path, required=True)
    parser.add_argument("--abstract-topology", type=Path, required=True)
    parser.add_argument("--emevd-index", type=Path, required=True)
    parser.add_argument("--common-event-bindings", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    map_root = args.map_root.resolve()
    abstract_path = args.abstract_topology.resolve()
    emevd_path = args.emevd_index.resolve()
    common_event_bindings_path = args.common_event_bindings.resolve()
    abstract = json.loads(abstract_path.read_text(encoding="utf-8"))
    emevd = json.loads(emevd_path.read_text(encoding="utf-8"))
    common_event_bindings = json.loads(common_event_bindings_path.read_text(encoding="utf-8"))
    common_event_bindings_by_candidate = {
        record.get("candidate_id"): record
        for record in common_event_bindings.get("records", [])
        if record.get("candidate_id")
    }
    emevd_reference_root = Path(emevd.get("source", {}).get("references_output_root") or "")
    references_by_map_event: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    references_by_map_entity: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    objact_state_references_by_map_param: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    if emevd_reference_root.is_dir():
        for reference_path in sorted(emevd_reference_root.glob("*.json")):
            reference_payload = json.loads(reference_path.read_text(encoding="utf-8"))
            map_key = str(reference_payload.get("map_key") or reference_path.stem)
            for reference in reference_payload.get("references", []):
                event_id = int(reference.get("event_id", -1))
                references_by_map_event[(map_key, event_id)].append(reference)
                for argument in reference.get("args", []):
                    if "entity id" not in str(argument.get("name") or "").casefold():
                        continue
                    value = argument.get("value")
                    if isinstance(value, int) and value > 0:
                        references_by_map_entity[(map_key, value)].append(reference)
                if reference.get("instruction_name") in {
                    "Set ObjAct State",
                    "Set ObjAct State (Assign IDx)",
                }:
                    args_by_name = {
                        str(argument.get("name")): argument.get("value")
                        for argument in reference.get("args", [])
                    }
                    param_id = args_by_name.get("ObjAct Param ID")
                    target_entity_id = args_by_name.get("Entity ID")
                    if (
                        isinstance(param_id, int)
                        and param_id not in (-1,)
                        and isinstance(target_entity_id, int)
                        and target_entity_id > 0
                    ):
                        objact_state_references_by_map_param[(map_key, param_id)].append(reference)

    map_payloads: dict[str, dict[str, Any]] = {}
    maps: set[str] = set()
    for path in sorted(map_root.glob("*.json")):
        if not MAP_RE.match(path.stem):
            continue
        maps.add(path.stem)
        map_payloads[path.stem] = json.loads(path.read_text(encoding="utf-8"))

    connect_by_map_name: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    connection_by_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    parts_by_map_name: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    entities_by_map_id: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    objact_part_names_by_identity: dict[tuple[str, int], set[str]] = defaultdict(set)
    objact_events_by_cross_map_identity: dict[tuple[str, int, int], list[dict[str, Any]]] = defaultdict(list)
    objact_events_by_global_param_identity: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    objacts: list[dict[str, Any]] = []
    connect_rows: list[dict[str, Any]] = []
    connection_rows: list[dict[str, Any]] = []

    # Some MSBE ObjAct records omit ObjActPartName on one side of a paired
    # interaction (notably two-sided elevator levers), while retaining the
    # same ObjActEntityID as the sibling record that does name the target
    # part.  Collect that exact identity relation before compiling candidates;
    # it is source identity, not a proximity or name heuristic.
    for map_id, payload in sorted(map_payloads.items()):
        for item in payload.get("events", []):
            if item.get("type") != "ObjAct":
                continue
            extra = item.get("extra") or {}
            identity = extra.get("ObjActEntityID")
            part_name = extra.get("ObjActPartName")
            if isinstance(identity, int) and identity > 0 and part_name:
                objact_part_names_by_identity[(map_id, identity)].add(str(part_name))
            obj_act_id = extra.get("ObjActID")
            if (
                isinstance(identity, int)
                and identity > 0
                and isinstance(obj_act_id, int)
                and obj_act_id not in (-1,)
            ):
                record = {
                    "map_id": map_id,
                    "event_id": item.get("event_id"),
                    "event_name": item.get("name"),
                    "obj_act_id": obj_act_id,
                    "obj_act_entity_id": identity,
                    "obj_act_part_name": str(part_name) if part_name else None,
                }
                objact_events_by_global_param_identity[(obj_act_id, identity)].append(record)
                if part_name:
                    objact_events_by_cross_map_identity[(map_id, obj_act_id, identity)].append(record)

    # Index every Part and Region before processing any ObjAct.  Cross-map
    # ObjAct bindings can point forward in lexical map order, so resolving
    # them while building one map at a time would make the result order-
    # dependent.
    for map_id, payload in sorted(map_payloads.items()):
        for index, item in enumerate(payload.get("parts", [])):
            name = str(item.get("name") or f"part_{index}")
            node_id = f"local-part:{map_id}:{name}:{index}"
            parts_by_map_name[(map_id, name)].append({"item": item, "node_id": node_id, "index": index})
            entity_id = item.get("entity_id")
            if isinstance(entity_id, int) and entity_id > 0:
                entities_by_map_id[(map_id, entity_id)].append(
                    {"item": item, "node_id": node_id, "endpoint_kind": "part"}
                )
        for index, item in enumerate(payload.get("regions", [])):
            node_id = f"local-region:{map_id}:{item.get('name') or f'region_{index}'}:{int(item.get('region_id', -1))}:{index}"
            entity_id = item.get("entity_id")
            if isinstance(entity_id, int) and entity_id > 0:
                entities_by_map_id[(map_id, entity_id)].append(
                    {"item": item, "node_id": node_id, "endpoint_kind": "region"}
                )

    for map_id, payload in sorted(map_payloads.items()):
        for index, item in enumerate(payload.get("parts", [])):
            name = str(item.get("name") or f"part_{index}")
            node_id = f"local-part:{map_id}:{name}:{index}"
            if item.get("type") != "ConnectCollision":
                continue
            record = {
                "map_id": map_id,
                "node_id": node_id,
                "index": index,
                "item": item,
                "target_map_id": canonical_map_id((item.get("extra") or {}).get("MapID")),
            }
            connect_rows.append(record)
            connect_by_map_name[(map_id, name)].append(record)

        for index, item in enumerate(payload.get("regions", [])):
            name = str(item.get("name") or f"region_{index}")
            node_id = f"local-region:{map_id}:{name}:{int(item.get('region_id', -1))}:{index}"
            if item.get("type") != "Connection":
                continue
            record = {
                "map_id": map_id,
                "node_id": node_id,
                "index": index,
                "item": item,
                    "target_map_id": canonical_map_id((item.get("extra") or {}).get("TargetMapID")),
            }
            connection_rows.append(record)
            connection_by_map[map_id].append(record)

        for index, item in enumerate(payload.get("events", [])):
            if item.get("type") != "ObjAct":
                continue
            extra = item.get("extra") or {}
            obj_act_id = extra.get("ObjActID")
            kind, classification_basis = classify_objact(item.get("name"), obj_act_id)
            part_name = extra.get("ObjActPartName")
            target_parts = parts_by_map_name.get((map_id, str(part_name)), []) if part_name else []
            obj_act_entity_id = extra.get("ObjActEntityID")
            obj_act_map_id_raw = extra.get("MapID")
            obj_act_map_id = map_id_from_packed_integer(obj_act_map_id_raw)
            obj_act_map_identity_status = (
                "explicit_objact_map_id"
                if obj_act_map_id is not None
                else "objact_map_id_absent_or_sentinel"
            )
            identity_part_names = sorted(
                objact_part_names_by_identity.get((map_id, obj_act_entity_id), set())
                if isinstance(obj_act_entity_id, int) and obj_act_entity_id > 0
                else []
            )
            target_binding_basis = "exact_objact_part_name" if target_parts else None
            # Preserve only a unique sibling identity target.  An identity
            # with multiple named parts is intentionally left unresolved.
            if not target_parts and len(identity_part_names) == 1:
                target_parts = parts_by_map_name.get((map_id, identity_part_names[0]), [])
                if len(target_parts) == 1:
                    target_binding_basis = "exact_sibling_objact_entity_id_to_part_name"
            cross_map_binding = None
            global_identity_audit = {
                "status": "not_evaluated",
                "candidate_count": 0,
                "named_target_candidate_count": 0,
                "candidate_records": [],
                "routeable": False,
            }
            if (
                not target_parts
                and obj_act_map_id
                and obj_act_map_id in map_payloads
                and isinstance(obj_act_entity_id, int)
                and obj_act_entity_id > 0
                and isinstance(obj_act_id, int)
                and obj_act_id not in (-1,)
            ):
                cross_map_matches = objact_events_by_cross_map_identity.get(
                    (obj_act_map_id, obj_act_id, obj_act_entity_id), []
                )
                cross_map_targets = []
                for match in cross_map_matches:
                    candidate_parts = parts_by_map_name.get(
                        (obj_act_map_id, match["obj_act_part_name"]), []
                    )
                    if len(candidate_parts) == 1:
                        cross_map_targets.append((match, candidate_parts[0]))
                if len(cross_map_targets) == 1:
                    cross_map_binding, target_part = cross_map_targets[0]
                    target_parts = [target_part]
                    target_binding_basis = "exact_cross_map_objact_entity_id_to_part_name"
            # Some MSBE controls omit ObjActPartName and use MapID=-1 even
            # though the same ObjAct parameter/entity identity is named by a
            # corresponding ObjAct record on another map.  Bind this only
            # when the global parameter/entity key yields exactly one
            # cross-map named record and that name resolves to exactly one
            # target Part.  The relation remains control-to-part evidence;
            # it is never promoted to a route edge.
            if (
                not target_parts
                and cross_map_binding is None
                and isinstance(obj_act_entity_id, int)
                and obj_act_entity_id > 0
                and isinstance(obj_act_id, int)
                and obj_act_id not in (-1,)
            ):
                global_matches = []
                global_records = [
                    match
                    for match in objact_events_by_global_param_identity.get(
                        (obj_act_id, obj_act_entity_id), []
                    )
                    if match["map_id"] != map_id
                ]
                global_candidate_records = []
                for match in global_records:
                    part_name = match.get("obj_act_part_name")
                    candidate_parts = (
                        parts_by_map_name.get((match["map_id"], part_name), [])
                        if part_name
                        else []
                    )
                    global_candidate_records.append(
                        {
                            "map_id": match.get("map_id"),
                            "event_id": match.get("event_id"),
                            "event_name": match.get("event_name"),
                            "obj_act_part_name": part_name,
                            "target_part_count": len(candidate_parts),
                        }
                    )
                    if not part_name:
                        continue
                    if len(candidate_parts) == 1:
                        global_matches.append((match, candidate_parts[0]))
                if len(global_matches) == 1:
                    global_status = "exact_unique_cross_map_named_part"
                elif not global_records:
                    global_status = "no_cross_map_same_objact_param_entity"
                elif not global_matches:
                    global_status = "cross_map_records_without_unique_named_target_part"
                else:
                    global_status = "ambiguous_cross_map_named_target_part"
                global_identity_audit = {
                    "status": global_status,
                    "candidate_count": len(global_records),
                    "named_target_candidate_count": len(global_matches),
                    "candidate_records": global_candidate_records,
                    "routeable": False,
                }
                if len(global_matches) == 1:
                    cross_map_binding, target_part = global_matches[0]
                    target_parts = [target_part]
                    target_binding_basis = "exact_global_objact_entity_param_to_part_name"
            if not target_parts and global_identity_audit["status"] == "not_evaluated":
                global_identity_audit = {
                    **global_identity_audit,
                    "status": "invalid_objact_param_or_entity_identity",
                }
            target_part_entity_id = None
            if len(target_parts) == 1:
                raw_entity_id = target_parts[0]["item"].get("entity_id")
                if isinstance(raw_entity_id, int) and raw_entity_id > 0:
                    target_part_entity_id = raw_entity_id
            target_map_id = (
                cross_map_binding.get("map_id")
                if isinstance(cross_map_binding, dict)
                else None
            ) or obj_act_map_id or map_id
            objacts.append(
                {
                    "id": f"local-transition-candidate:{map_id}:{int(item.get('event_id', -1))}:{index}",
                    "map_id": map_id,
                    "event_id": item.get("event_id"),
                    "event_name": item.get("name"),
                    "transition_candidate_kind": kind,
                    "classification_basis": classification_basis,
                    "obj_act_id": obj_act_id,
                    "obj_act_entity_id": obj_act_entity_id,
                    "obj_act_map_id_raw": obj_act_map_id_raw,
                    "obj_act_map_id": obj_act_map_id,
                    "obj_act_map_identity_status": obj_act_map_identity_status,
                    "state_type": extra.get("StateType"),
                    "obj_act_event_flag_id": extra.get("EventFlagID"),
                    "obj_act_part_name": part_name,
                    "identity_part_names": identity_part_names,
                    "global_objact_identity_audit": global_identity_audit,
                    "target_binding_basis": target_binding_basis,
                    "exact_target_part_node_ids": [row["node_id"] for row in target_parts],
                    "exact_target_part_match": len(target_parts) == 1,
                    "target_part_entity_id": target_part_entity_id,
                    "target_part_map_id": (
                        target_map_id
                        if cross_map_binding is not None and len(target_parts) == 1
                        else map_id
                        if len(target_parts) == 1
                        else None
                    ),
                    "target_part_endpoint": (
                        endpoint_payload(
                            target_map_id if cross_map_binding is not None else map_id,
                            target_parts[0]["item"],
                            target_parts[0]["node_id"],
                            "objact_target_part",
                        )
                        if len(target_parts) == 1
                        else None
                    ),
                    "cross_map_objact_binding": cross_map_binding,
                    "endpoint_binding_status": (
                        "control_to_cross_map_part_only"
                        if cross_map_binding is not None and len(target_parts) == 1
                        else "control_to_part_only"
                        if len(target_parts) == 1
                        else "target_part_unresolved"
                    ),
                    "routeable": False,
                    "verification_state": "local_msbe_verified",
                    "blockers": [
                        "interaction_control_is_not_a_destination_endpoint",
                        "destination_endpoint_not_encoded_by_objact_record",
                        "world_state_guard_not_bound",
                    ],
                }
            )

    # A paired upper/lower control is useful topology evidence, but it is not
    # a destination or a directed walk edge.  Require exactly one explicit
    # upper and one explicit lower source label after formatting-only
    # normalization; duplicated labels or unmatched sides stay unpaired.
    mechanism_groups: dict[tuple[str, str], list[tuple[dict[str, Any], str]]] = defaultdict(list)
    for candidate in objacts:
        if candidate.get("transition_candidate_kind") == "loot_or_non_transition_interaction":
            continue
        side = mechanism_side(candidate.get("event_name"))
        if side:
            mechanism_groups[(candidate.get("map_id"), mechanism_label(candidate.get("event_name")))].append(
                (candidate, side)
            )
    mechanism_pair_count = 0
    mechanism_pair_row_count = 0
    for (map_id, label), group in sorted(mechanism_groups.items()):
        if len(group) != 2 or {side for _, side in group} != {"lower", "upper"}:
            continue
        mechanism_pair_count += 1
        pair_id = f"objact-mechanism-pair:{map_id}:{hashlib.sha1(label.encode('utf-8')).hexdigest()[:16]}"
        peer_ids = sorted(candidate.get("id") for candidate, _ in group)
        for candidate, side in group:
            candidate["mechanism_pair_id"] = pair_id
            candidate["mechanism_pair_label"] = label
            candidate["mechanism_side"] = side
            candidate["mechanism_peer_candidate_ids"] = [
                peer_id for peer_id in peer_ids if peer_id != candidate.get("id")
            ]
            candidate["mechanism_pair_binding_basis"] = "exact_same_map_source_label_opposite_side_pair"
            candidate["mechanism_pair_routeable"] = False
            mechanism_pair_row_count += 1

    # A strict raw common-event recovery pass for MSBE ObjAct records whose
    # ObjActPartName is absent.  The producer has already required the same
    # map/event, ObjActEntityID, ObjAct ID, substituted common-event state
    # target, and unique MSBE Part.  Revalidate the final map/entity identity
    # here before it can affect this audit.
    common_event_exact_matches = 0
    for candidate in objacts:
        if candidate.get("exact_target_part_match"):
            continue
        record = common_event_bindings_by_candidate.get(candidate.get("id"))
        if not record:
            continue
        if (
            record.get("map_id") != candidate.get("map_id")
            or record.get("msbe_objact_event_id") != candidate.get("event_id")
            or record.get("obj_act_id") != candidate.get("obj_act_id")
            or record.get("obj_act_entity_id") != candidate.get("obj_act_entity_id")
        ):
            continue
        target_part = record.get("target_part") or {}
        target_entity_id = target_part.get("entity_id")
        target_rows = [
            row
            for row in entities_by_map_id.get((candidate.get("map_id"), target_entity_id), [])
            if row.get("endpoint_kind") == "part"
        ]
        if len(target_rows) != 1 or target_rows[0].get("node_id") != target_part.get("node_id"):
            continue
        candidate["exact_target_part_node_ids"] = [target_rows[0]["node_id"]]
        candidate["exact_target_part_match"] = True
        candidate["target_part_entity_id"] = target_entity_id
        candidate["target_part_map_id"] = candidate.get("map_id")
        candidate["target_part_endpoint"] = endpoint_payload(
            candidate.get("map_id"),
            target_rows[0]["item"],
            target_rows[0]["node_id"],
            "objact_target_part",
        )
        candidate["target_binding_basis"] = "exact_emevd_common_event_objact_state_target"
        candidate["endpoint_binding_status"] = "control_to_part_only_via_exact_common_event_state_target"
        candidate["emevd_common_event_objact_binding"] = record
        candidate["emevd_state_target_binding"] = {
            "status": "exact_common_event_objact_state_target",
            "objact_param_id": candidate.get("obj_act_id"),
            "state_target_entity_ids": sorted({
                row.get("entity_id")
                for row in record.get("state_rows", [])
                if isinstance(row.get("entity_id"), int)
            }),
            "common_event_id": record.get("common_event_id"),
            "routeable": False,
        }
        common_event_exact_matches += 1

    # A small strict recovery pass for MSBE ObjAct records whose
    # ObjActPartName is absent.  It only binds when the same map+ObjActParam
    # has one unresolved ObjAct candidate, the local EMEVD state writes point
    # to one unique entity, and that entity is one unique MSBE Part.  This is
    # an exact cross-file identity chain; ambiguous or sentinel cases remain
    # unresolved.
    candidates_by_map_param: dict[tuple[str, Any], list[dict[str, Any]]] = defaultdict(list)
    for candidate in objacts:
        if not candidate.get("exact_target_part_match"):
            candidates_by_map_param[(candidate.get("map_id"), candidate.get("obj_act_id"))].append(candidate)
    for candidate in objacts:
        if candidate.get("exact_target_part_match"):
            continue
        obj_act_id = candidate.get("obj_act_id")
        state_refs = (
            objact_state_references_by_map_param.get((candidate.get("map_id"), obj_act_id), [])
            if isinstance(obj_act_id, int) and obj_act_id not in (-1,)
            else []
        )
        state_entity_ids = sorted(
            {
                argument.get("value")
                for reference in state_refs
                for argument in reference.get("args", [])
                if argument.get("name") == "Entity ID"
                and isinstance(argument.get("value"), int)
                and argument.get("value") > 0
            }
        )
        candidate["emevd_state_target_binding"] = {
            "status": "not_unique_or_not_available",
            "objact_param_id": obj_act_id,
            "candidate_count_for_map_and_param": len(
                candidates_by_map_param.get((candidate.get("map_id"), obj_act_id), [])
            ),
            "state_reference_ids": [reference.get("id") for reference in state_refs],
            "state_target_entity_ids": state_entity_ids,
            "routeable": False,
        }
        if len(candidates_by_map_param.get((candidate.get("map_id"), obj_act_id), [])) != 1:
            continue
        if len(state_entity_ids) != 1:
            continue
        target_rows = [
            row
            for row in entities_by_map_id.get((candidate.get("map_id"), state_entity_ids[0]), [])
            if row.get("endpoint_kind") == "part"
        ]
        if len(target_rows) != 1:
            continue
        target = target_rows[0]
        candidate["exact_target_part_node_ids"] = [target["node_id"]]
        candidate["exact_target_part_match"] = True
        candidate["target_part_entity_id"] = state_entity_ids[0]
        candidate["target_part_map_id"] = candidate.get("map_id")
        candidate["target_part_endpoint"] = endpoint_payload(
            candidate.get("map_id"),
            target["item"],
            target["node_id"],
            "objact_target_part",
        )
        candidate["target_binding_basis"] = "exact_emevd_objact_param_unique_state_target"
        candidate["endpoint_binding_status"] = "control_to_part_only_via_exact_emevd_state_target"
        candidate["emevd_state_target_binding"]["status"] = "exact_unique_objact_param_state_target"
        candidate["emevd_state_target_binding"]["target_part_node_id"] = target["node_id"]
        candidate["emevd_state_target_binding"]["routeable"] = False

    # A verified identity-transform recovery pass runs after the stronger
    # common-event and ObjAct-param bindings.  It never overrides those
    # bindings; it only accepts an unresolved same-map candidate when the
    # exact corpus independently demonstrates ObjActEntityID = PartID + 2000
    # and the transformed Part identity is unique.
    verified_objact_entity_offsets = Counter(
        candidate.get("target_part_entity_id") - candidate.get("obj_act_entity_id")
        for candidate in objacts
        if candidate.get("exact_target_part_match")
        and isinstance(candidate.get("target_part_entity_id"), int)
        and isinstance(candidate.get("obj_act_entity_id"), int)
    )
    verified_entity_id_minus_2000_support = verified_objact_entity_offsets.get(-2000, 0)
    verified_entity_id_minus_2000_matches = 0
    for candidate in objacts:
        if candidate.get("exact_target_part_match"):
            continue
        if candidate.get("obj_act_map_id") not in (None, candidate.get("map_id")):
            continue
        obj_act_entity_id = candidate.get("obj_act_entity_id")
        if not isinstance(obj_act_entity_id, int) or obj_act_entity_id <= 2000:
            continue
        target_entity_id = obj_act_entity_id - 2000
        target_rows = [
            row
            for row in entities_by_map_id.get((candidate.get("map_id"), target_entity_id), [])
            if row.get("endpoint_kind") == "part"
        ]
        if len(target_rows) != 1 or verified_entity_id_minus_2000_support <= 0:
            continue
        target = target_rows[0]
        candidate["exact_target_part_node_ids"] = [target["node_id"]]
        candidate["exact_target_part_match"] = True
        candidate["target_part_entity_id"] = target_entity_id
        candidate["target_part_map_id"] = candidate.get("map_id")
        candidate["target_part_endpoint"] = endpoint_payload(
            candidate.get("map_id"),
            target["item"],
            target["node_id"],
            "objact_target_part",
        )
        candidate["target_binding_basis"] = "verified_objact_entity_id_minus_2000_to_unique_part"
        candidate["endpoint_binding_status"] = "control_to_part_only_via_verified_entity_id_transform"
        candidate["identity_transform_evidence"] = {
            "transform": "target_part_entity_id = ObjActEntityID - 2000",
            "verified_exact_binding_support_count": verified_entity_id_minus_2000_support,
            "target_part_entity_id": target_entity_id,
            "target_part_node_id": target["node_id"],
            "same_map_unique_part": True,
            "routeable": False,
        }
        verified_entity_id_minus_2000_matches += 1

    exact_entity_reference_rows = 0
    direct_control_reference_rows = 0
    event_scoped_condition_rows = 0
    event_scoped_action_rows = 0
    event_flag_ids: set[int] = set()
    scripted_warp_bindings: list[dict[str, Any]] = []
    scripted_map_warp_bindings: list[dict[str, Any]] = []
    for candidate in objacts:
        entity_id = candidate.get("target_part_entity_id")
        candidate_event_flag_ids: set[int] = set()
        exact_refs = []
        target_part_map_id = candidate.get("target_part_map_id") or candidate["map_id"]
        if isinstance(entity_id, int):
            deduped = {
                str(reference.get("id")): reference
                for reference in references_by_map_entity.get((target_part_map_id, entity_id), [])
            }
            exact_refs = list(deduped.values())
        direct_refs = [
            reference
            for reference in exact_refs
            if str(reference.get("instruction_name") or "").startswith("Set ObjAct State")
            or reference.get("instruction_name") == "IF Action Button in Area"
        ]
        related_events: dict[int, list[dict[str, Any]]] = {}
        for reference in exact_refs:
            related_events.setdefault(int(reference.get("event_id", -1)), []).append(reference)
        scoped_refs = []
        for event_id in related_events:
            scoped_refs.extend(references_by_map_event.get((target_part_map_id, event_id), []))
        scoped_refs = list({str(reference.get("id")): reference for reference in scoped_refs}.values())
        conditions = [reference for reference in scoped_refs if reference.get("category") == "condition"]
        actions = [reference for reference in scoped_refs if reference.get("category") == "action"]
        for reference in scoped_refs:
            for flag_id in reference.get("event_flag_ids", []):
                if isinstance(flag_id, int):
                    candidate_event_flag_ids.add(int(flag_id))
                    event_flag_ids.add(int(flag_id))
        candidate["emevd_binding"] = {
            "target_part_entity_id": entity_id,
            "target_binding_basis": candidate.get("target_binding_basis"),
            "exact_entity_reference_count": len(exact_refs),
            "exact_entity_reference_ids": [reference.get("id") for reference in exact_refs],
            "exact_entity_reference_summary": dict(Counter(reference.get("instruction_name") for reference in exact_refs)),
            "direct_control_reference_count": len(direct_refs),
            "direct_control_references": [compact_emevd_reference(reference) for reference in direct_refs],
            "related_event_ids": sorted(related_events),
            "event_scoped_condition_count": len(conditions),
            "event_scoped_action_count": len(actions),
            "event_scoped_condition_references": [compact_emevd_reference(reference) for reference in conditions],
            "event_scoped_action_references": [compact_emevd_reference(reference) for reference in actions],
            "event_scoped_event_flag_ids": sorted(candidate_event_flag_ids),
            "binding_status": "exact_same_map_target_part_entity_id" if exact_refs else "no_exact_entity_reference",
            "routeable": False,
        }
        source_node_id = (candidate.get("exact_target_part_node_ids") or [None])[0]
        if source_node_id and entity_id is not None:
            for event_id in sorted(related_events):
                for reference in references_by_map_event.get((target_part_map_id, event_id), []):
                    event_references = references_by_map_event.get((target_part_map_id, event_id), [])
                    event_conditions = [row for row in event_references if row.get("category") == "condition"]
                    event_actions = [row for row in event_references if row.get("category") == "action"]
                    event_event_flag_ids = sorted(
                        {
                            int(flag_id)
                            for row in event_references
                            for flag_id in row.get("event_flag_ids", [])
                            if isinstance(flag_id, int)
                        }
                    )
                    instruction_name = str(reference.get("instruction_name") or "")
                    if "warp" not in instruction_name.casefold() and "change map" not in instruction_name.casefold():
                        continue
                    destination_ids = [
                        argument.get("value")
                        for argument in reference.get("args", [])
                        if "destination entity id" in str(argument.get("name") or "").casefold()
                        and isinstance(argument.get("value"), int)
                        and argument.get("value") > 0
                    ]
                    for destination_id in destination_ids:
                        for target in entities_by_map_id.get((candidate["map_id"], destination_id), []):
                            binding_id = f"{candidate['id']}:{reference.get('id')}:{target['node_id']}"
                            if any(row["id"] == binding_id for row in scripted_warp_bindings):
                                continue
                            target_payload = endpoint_payload(
                                candidate["map_id"], target["item"], target["node_id"], target["endpoint_kind"]
                            )
                            scripted_warp_bindings.append(
                                {
                                    "id": binding_id,
                                    "transition_kind": "scripted_warp",
                                    "direction": "interaction_target_to_explicit_warp_destination",
                                    "direction_status": "explicit_in_EMEVD_destination_entity_id",
                                    "from": {
                                        "map_id": candidate["map_id"],
                                        "node_id": source_node_id,
                                        "name": candidate.get("event_name"),
                                        "endpoint_kind": "objact_target_part",
                                        "entity_id": entity_id,
                                        "coordinate_system": "Elden Ring MSBE game-native XYZ",
                                        "original_game_coordinates": True,
                                        "local_game_verified": True,
                                    },
                                    "to": target_payload,
                                    "emevd_reference": compact_emevd_reference(reference),
                                    "destination_entity_id": destination_id,
                                    "guard": {
                                        "status": "event_scoped_evidence_only",
                                        "event_id": event_id,
                                        "condition_count": len(event_conditions),
                                        "event_flag_ids": event_event_flag_ids,
                                        "condition_references": [compact_emevd_reference(row) for row in event_conditions],
                                        "effect_references": [compact_emevd_reference(row) for row in event_actions],
                                    },
                                    "routeable": False,
                                    "verification_state": "local_msbe_and_emevd_exact_entity_binding",
                                    "blockers": [
                                        "player_space_segment_to_interaction_not_bound",
                                        "event_control_flow_guard_not_resolved",
                                        "post_warp_player_destination_semantics_not_verified",
                                    ],
                                }
                            )
                    target_map_id, map_id_basis = map_id_from_emevd_warp(reference)
                    if target_map_id and target_map_id in maps:
                        binding_id = f"{candidate['id']}:{reference.get('id')}:{target_map_id}"
                        if not any(row["id"] == binding_id for row in scripted_map_warp_bindings):
                            args_by_name = {
                                str(argument.get("name")): argument.get("value")
                                for argument in reference.get("args", [])
                            }
                            landing_entity_id = args_by_name.get("Area Entity ID")
                            if not isinstance(landing_entity_id, int) or landing_entity_id <= 0:
                                landing_entity_id = args_by_name.get("Initial Area Entity ID")
                            landing_targets = (
                                entities_by_map_id.get((target_map_id, landing_entity_id), [])
                                if isinstance(landing_entity_id, int) and landing_entity_id > 0
                                else []
                            )
                            exact_landing = len(landing_targets) == 1
                            landing = None
                            if exact_landing:
                                landing_target = landing_targets[0]
                                landing = endpoint_payload(
                                    target_map_id,
                                    landing_target["item"],
                                    landing_target["node_id"],
                                    landing_target["endpoint_kind"],
                                )
                            scripted_map_warp_bindings.append(
                                {
                                    "id": binding_id,
                                    "transition_kind": "scripted_map_warp",
                                    "direction": "interaction_target_to_explicit_emevd_map_target",
                                    "direction_status": "explicit_in_EMEVD_warp_parameters",
                                    "from": {
                                        "map_id": candidate["map_id"],
                                        "node_id": source_node_id,
                                        "name": candidate.get("event_name"),
                                        "endpoint_kind": "objact_target_part",
                                        "entity_id": entity_id,
                                        "coordinate_system": "Elden Ring MSBE game-native XYZ",
                                        "original_game_coordinates": True,
                                        "local_game_verified": True,
                                    },
                                    "to": {
                                        "map_id": target_map_id,
                                        "node_id": f"local_map_{target_map_id}",
                                        "endpoint_kind": "scripted_map_target",
                                        "map_id_basis": map_id_basis,
                                        "area_entity_id": args_by_name.get("Area Entity ID"),
                                        "initial_area_entity_id": args_by_name.get("Initial Area Entity ID"),
                                        "landing_binding_status": "exact" if exact_landing else "unresolved",
                                        "landing": landing,
                                        "coordinate_system": "Elden Ring MSBE map identity",
                                        "original_game_coordinates": True,
                                        "local_game_verified": True,
                                    },
                                    "emevd_reference": compact_emevd_reference(reference),
                                    "guard": {
                                        "status": "event_scoped_evidence_only",
                                        "event_id": event_id,
                                        "condition_count": len(event_conditions),
                                        "event_flag_ids": event_event_flag_ids,
                                        "condition_references": [compact_emevd_reference(row) for row in event_conditions],
                                        "effect_references": [compact_emevd_reference(row) for row in event_actions],
                                    },
                                    "routeable": False,
                                    "verification_state": "local_msbe_and_emevd_exact_map_binding",
                                    "blockers": [
                                        "player_space_segment_to_interaction_not_bound",
                                        "event_control_flow_guard_not_resolved",
                                        *([] if exact_landing else ["exact_landing_entity_not_bound"]),
                                    ],
                                }
                            )
        exact_entity_reference_rows += len(exact_refs)
        direct_control_reference_rows += len(direct_refs)
        event_scoped_condition_rows += len(conditions)
        event_scoped_action_rows += len(actions)

    endpoint_pairs: list[dict[str, Any]] = []
    exact_connect_pairs = 0
    for source in connect_rows:
        target_map = source["target_map_id"]
        if not target_map or target_map not in maps:
            continue
        name = str(source["item"].get("name") or "")
        targets = connect_by_map_name.get((target_map, name), [])
        if len(targets) != 1:
            continue
        target = targets[0]
        exact_connect_pairs += 1
        endpoint_pairs.append(
            {
                "id": f"local-transition:{source['node_id']}->{target['node_id']}",
                "transition_kind": "explicit_map_connection",
                "direction": "source_map_to_declared_target_map",
                "direction_status": "explicit_in_source_MSBE_MapID",
                "from": endpoint_payload(source["map_id"], source["item"], source["node_id"], "connect_collision"),
                "to": endpoint_payload(target["map_id"], target["item"], target["node_id"], "connect_collision"),
                "endpoint_binding_status": "exact",
                "pair_basis": "same ConnectCollision name on the declared target map",
                "guard": {"status": "not_bound", "source": "no direct guard-to-endpoint binding"},
                "routeable": False,
                "verification_state": "local_msbe_verified_exact_endpoint_pair",
                "blockers": blocker_list("connect_collision"),
            }
        )

    exact_connection_pairs = 0
    for source in connection_rows:
        target_map = source["target_map_id"]
        if not target_map or target_map not in maps:
            continue
        targets = [
            candidate
            for candidate in connection_by_map.get(target_map, [])
            if str(source["map_id"]) in str(candidate["item"].get("name") or "")
        ]
        if len(targets) != 1:
            continue
        target = targets[0]
        exact_connection_pairs += 1
        endpoint_pairs.append(
            {
                "id": f"local-transition:{source['node_id']}->{target['node_id']}",
                "transition_kind": "explicit_map_connection_region",
                "direction": "source_map_to_declared_target_map",
                "direction_status": "explicit_in_source_MSBE_TargetMapID",
                "from": endpoint_payload(source["map_id"], source["item"], source["node_id"], "connection_region"),
                "to": endpoint_payload(target["map_id"], target["item"], target["node_id"], "connection_region"),
                "endpoint_binding_status": "exact",
                "pair_basis": "source Connection.TargetMapID plus target Connection name naming the source map",
                "guard": {"status": "not_bound", "source": "no direct guard-to-endpoint binding"},
                "routeable": False,
                "verification_state": "local_msbe_verified_exact_endpoint_pair",
                "blockers": blocker_list("connection_region"),
            }
        )

    role_counts = Counter(row["transition_candidate_kind"] for row in objacts)
    unresolved_transition_rows = [
        row
        for row in objacts
        if not row.get("exact_target_part_match")
        and row.get("transition_candidate_kind") != "loot_or_non_transition_interaction"
    ]
    unresolved_global_identity_status_counts = Counter(
        (row.get("global_objact_identity_audit") or {}).get("status", "not_evaluated")
        for row in unresolved_transition_rows
    )
    exact_part_matches = sum(row["exact_target_part_match"] for row in objacts)
    map_node_count = len(abstract.get("status", {}).get("map_nodes", [])) if isinstance(abstract.get("status", {}).get("map_nodes"), list) else abstract.get("status", {}).get("map_nodes", len(maps))
    output = {
        "schema": "elden-ring-local-transition-audit@1",
        "source": {
            "snapshot_id": "elden-ring-local-snapshot-20260818",
            "map_root": str(map_root),
            "map_root_sha256_not_applicable": "directory input",
            "abstract_topology": str(abstract_path),
            "abstract_topology_sha256": sha256(abstract_path),
            "emevd_index": str(emevd_path),
            "emevd_index_sha256": sha256(emevd_path),
            "common_event_bindings": str(common_event_bindings_path),
            "common_event_bindings_sha256": sha256(common_event_bindings_path),
            "emevd_status": emevd.get("status", {}),
        },
        "model": {
            "purpose": "exact transition endpoint binding audit for the final directed topology",
            "promote_policy": "only exact endpoint, direction, guard, effect, and player-space segment evidence may become routeable",
            "exact_scripted_map_warp_binding": "ObjAct target-part entity plus same-event EMEVD map-warp parameters and target-map landing entity",
            "exact_objact_state_target_binding": "unique same-map ObjAct Param ID plus unique EMEVD Set ObjAct State target Entity ID plus unique MSBE Part",
            "exact_common_event_objact_state_target_binding": "same-map raw InitializeCommonEvent call carrying ObjActEntityID and ObjAct ID, substituted common-event Set ObjAct State target, and unique MSBE Part",
            "verified_objact_entity_id_transform": "same-map unique Part whose entity_id equals ObjActEntityID minus 2000, supported by 542 independent exact ObjAct-to-Part bindings; evidence only",
            "routeable": False,
            "continuous_walkability": "not modeled",
            "havok_or_nva": "not read; not required for these exact MSBE endpoint bindings",
            "distance_or_proximity_inference": "forbidden",
        },
        "status": {
            "map_nodes": map_node_count,
            "source_map_files": len(map_payloads),
            "connect_collision_rows": len(connect_rows),
            "exact_connect_collision_endpoint_pairs": exact_connect_pairs,
            "connection_region_rows": len(connection_rows),
            "exact_connection_region_endpoint_pairs": exact_connection_pairs,
            "exact_endpoint_pairs": len(endpoint_pairs),
            "objact_rows": len(objacts),
            "objact_exact_target_part_matches": exact_part_matches,
            "objact_target_part_unresolved": len(objacts) - exact_part_matches,
            "objact_verified_entity_id_minus_2000_support_count": verified_entity_id_minus_2000_support,
            "objact_exact_verified_entity_id_minus_2000_matches": verified_entity_id_minus_2000_matches,
            "objact_transition_candidate_target_part_unresolved": sum(
                not row.get("exact_target_part_match")
                and row.get("transition_candidate_kind") != "loot_or_non_transition_interaction"
                for row in objacts
            ),
            "objact_non_transition_target_part_unresolved": sum(
                not row.get("exact_target_part_match")
                and row.get("transition_candidate_kind") == "loot_or_non_transition_interaction"
                for row in objacts
            ),
            "objact_exact_cross_map_entity_part_matches": sum(
                row.get("target_binding_basis") == "exact_cross_map_objact_entity_id_to_part_name"
                for row in objacts
            ),
            "objact_exact_global_entity_param_cross_map_matches": sum(
                row.get("target_binding_basis") == "exact_global_objact_entity_param_to_part_name"
                for row in objacts
            ),
            "objact_unresolved_transition_global_identity_status_counts": dict(
                sorted(unresolved_global_identity_status_counts.items())
            ),
            "objact_unresolved_transition_global_identity_candidate_records": sum(
                (row.get("global_objact_identity_audit") or {}).get("candidate_count", 0)
                for row in unresolved_transition_rows
            ),
            "objact_exact_sibling_entity_identity_matches": sum(
                row.get("target_binding_basis") == "exact_sibling_objact_entity_id_to_part_name"
                for row in objacts
            ),
            "objact_exact_emevd_objact_param_unique_state_target_matches": sum(
                row.get("target_binding_basis") == "exact_emevd_objact_param_unique_state_target"
                for row in objacts
            ),
            "objact_exact_common_event_objact_state_target_matches": common_event_exact_matches,
            "objact_explicit_map_id_records": sum(
                row.get("obj_act_map_id") is not None for row in objacts
            ),
            "objact_explicit_map_id_local_map_records": sum(
                row.get("obj_act_map_id") in maps for row in objacts
                if row.get("obj_act_map_id") is not None
            ),
            "objact_explicit_map_id_unresolved_records": sum(
                row.get("obj_act_map_id") not in maps for row in objacts
                if row.get("obj_act_map_id") is not None
            ),
            "objact_identity_part_name_ambiguous": sum(
                bool(row.get("identity_part_names"))
                and len(row.get("identity_part_names", [])) != 1
                for row in objacts
                if not row.get("exact_target_part_match")
            ),
            "objact_exact_entity_reference_rows": exact_entity_reference_rows,
            "objact_candidates_with_exact_entity_reference": sum(bool(row["emevd_binding"]["exact_entity_reference_count"]) for row in objacts),
            "objact_direct_control_reference_rows": direct_control_reference_rows,
            "objact_event_scoped_condition_rows": event_scoped_condition_rows,
            "objact_event_scoped_action_rows": event_scoped_action_rows,
            "exact_scripted_warp_bindings": len(scripted_warp_bindings),
            "exact_scripted_map_warp_bindings": len(scripted_map_warp_bindings),
            "exact_scripted_map_landing_bindings": sum(
                row.get("to", {}).get("landing_binding_status") == "exact"
                for row in scripted_map_warp_bindings
            ),
            "objact_transition_candidate_rows": sum(value for key, value in role_counts.items() if key != "loot_or_non_transition_interaction"),
            "objact_mechanism_pair_count": mechanism_pair_count,
            "objact_mechanism_pair_row_count": mechanism_pair_row_count,
            "objact_role_counts": dict(sorted(role_counts.items())),
            "direct_routeable_records": 0,
            "all_records_routeable_false": True,
            "formal_transition_promotion_ready": False,
        },
        "endpoint_pairs": endpoint_pairs,
        "scripted_warp_bindings": scripted_warp_bindings,
        "scripted_map_warp_bindings": scripted_map_warp_bindings,
        "interaction_candidates": objacts,
        "note": "Exact endpoint pairs are real game-native topology evidence, but are not yet player-routeable because the local segment, guard, and resulting state transition remain unbound. Interaction candidates preserve every ObjAct without guessing a destination.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
