#!/usr/bin/env python3
"""Recover strict ObjAct targets from raw InitializeCommonEvent calls.

Some MSBE ObjAct records omit ObjActPartName.  The raw EMEVD still carries
the ObjActEntityID and ObjActParam ID in an InitializeCommonEvent call.  This
pass substitutes the call's parameter buffer into the common event's raw
parameter mappings and accepts a target only when all of these are exact:

* same map and same MSBE ObjAct event ID,
* ObjActEntityID and ObjActParam ID both occur in the same raw call,
* the substituted Set ObjAct State instruction uses that ObjActParam ID,
* the resulting Entity ID resolves to exactly one MSBE Part on that map.

No name, distance, or map-layout inference is used.  The result is evidence
only and remains routeable=false.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def decode_value(buffer: bytes, argument: dict[str, Any]) -> Any:
    offset = int(argument.get("raw_offset", 0))
    size = int(argument.get("raw_size", 0))
    if offset < 0 or offset + size > len(buffer):
        return None
    raw = buffer[offset : offset + size]
    kind = argument.get("type")
    try:
        if kind == "uint32" and size == 4:
            return struct.unpack_from("<I", raw)[0]
        if kind == "int32" and size == 4:
            return struct.unpack_from("<i", raw)[0]
        if kind == "byte" and size == 1:
            return raw[0]
        if kind == "float" and size == 4:
            return struct.unpack_from("<f", raw)[0]
    except struct.error:
        return None
    return argument.get("value")


def expanded_common_event_references(
    event: dict[str, Any],
    semantic_references: list[dict[str, Any]],
    call_values: list[int],
) -> list[dict[str, Any]]:
    raw_by_index = {
        int(instruction.get("index")): instruction
        for instruction in event.get("instructions", [])
    }
    parameter_buffer = b"".join(struct.pack("<I", value) for value in call_values[2:])
    expanded = []
    for reference in semantic_references:
        instruction_index = int(reference.get("instruction_index", -1))
        raw_instruction = raw_by_index.get(instruction_index)
        if raw_instruction is None:
            continue
        try:
            buffer = bytearray(bytes.fromhex(str(raw_instruction.get("args_hex") or "")))
        except ValueError:
            continue
        for mapping in event.get("parameters", []):
            if int(mapping.get("instruction_index", -1)) != instruction_index:
                continue
            source = int(mapping.get("source_start_byte", 0))
            target = int(mapping.get("target_start_byte", 0))
            count = int(mapping.get("byte_count", 0))
            if source + count <= len(parameter_buffer) and target + count <= len(buffer):
                buffer[target : target + count] = parameter_buffer[source : source + count]
        args = []
        for argument in reference.get("args", []):
            item = dict(argument)
            item["value_after_substitution"] = decode_value(buffer, argument)
            args.append(item)
        expanded.append(
            {
                "reference": reference,
                "args": args,
                "raw_instruction": raw_instruction,
            }
        )
    return expanded


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map-root", type=Path, required=True)
    parser.add_argument("--parsed-emevd-root", type=Path, required=True)
    parser.add_argument("--semantic-common-references", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    map_root = args.map_root.resolve()
    parsed_root = args.parsed_emevd_root.resolve()
    semantic_path = args.semantic_common_references.resolve()
    raw_root = parsed_root / "files"
    common_raw_path = raw_root / "common_func.json"
    common_raw = json.loads(common_raw_path.read_text(encoding="utf-8"))
    common_events = {
        int(event.get("id")): event for event in common_raw.get("events", [])
    }
    semantic_payload = json.loads(semantic_path.read_text(encoding="utf-8"))
    semantic_by_event: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for reference in semantic_payload.get("references", []):
        semantic_by_event[int(reference.get("event_id", -1))].append(reference)

    parts_by_map_entity: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    objact_candidates: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    map_payloads: dict[str, dict[str, Any]] = {}
    for map_path in sorted(map_root.glob("m*.json")):
        map_id = map_path.stem
        payload = json.loads(map_path.read_text(encoding="utf-8"))
        map_payloads[map_id] = payload
        for index, part in enumerate(payload.get("parts", [])):
            entity_id = part.get("entity_id")
            if isinstance(entity_id, int) and entity_id > 0:
                parts_by_map_entity[(map_id, entity_id)].append(
                    {
                        "node_id": f"local-part:{map_id}:{part.get('name')}:{index}",
                        "map_id": map_id,
                        "entity_id": entity_id,
                        "name": part.get("name"),
                        "part_type": part.get("type"),
                        "model_name": part.get("model_name"),
                        "instance_id": part.get("instance_id"),
                        "position": part.get("position"),
                        "rotation": part.get("rotation"),
                        "scale": part.get("scale"),
                        "map_studio_layer": part.get("map_studio_layer"),
                        "extra": part.get("extra") or {},
                        "source_index": index,
                    }
                )
        for index, item in enumerate(payload.get("events", [])):
            if item.get("type") != "ObjAct":
                continue
            extra = item.get("extra") or {}
            entity_id = extra.get("ObjActEntityID")
            objact_id = extra.get("ObjActID")
            if not isinstance(entity_id, int) or entity_id <= 0:
                continue
            objact_candidates[(map_id, int(item.get("event_id", -1)))].append(
                {
                    "candidate_id": f"local-transition-candidate:{map_id}:{int(item.get('event_id', -1))}:{index}",
                    "map_id": map_id,
                    "event_id": int(item.get("event_id", -1)),
                    "event_index": index,
                    "event_name": item.get("name"),
                    "obj_act_id": objact_id,
                    "obj_act_entity_id": entity_id,
                    "obj_act_part_name": extra.get("ObjActPartName"),
                }
            )

    records = []
    missing_part_name_candidate_count = sum(
        1
        for candidates in objact_candidates.values()
        for candidate in candidates
        if not candidate.get("obj_act_part_name")
    )
    initialize_common_event_call_count = 0
    same_call_objact_identity_match_count = 0
    matching_objact_param_state_row_count = 0
    for map_path in sorted(raw_root.glob("m*.json")):
        map_id = map_path.stem
        if map_id not in map_payloads:
            continue
        raw_payload = json.loads(map_path.read_text(encoding="utf-8"))
        for raw_event in raw_payload.get("events", []):
            event_id = int(raw_event.get("id", -1))
            for instruction in raw_event.get("instructions", []):
                if instruction.get("bank") != 2000 or instruction.get("id") != 6:
                    continue
                initialize_common_event_call_count += 1
                try:
                    raw_args = bytes.fromhex(str(instruction.get("args_hex") or ""))
                    call_values = [
                        struct.unpack_from("<I", raw_args, offset)[0]
                        for offset in range(0, len(raw_args) - 3, 4)
                    ]
                except (ValueError, struct.error):
                    continue
                if len(call_values) < 3:
                    continue
                common_event_id = call_values[1]
                common_event = common_events.get(common_event_id)
                if common_event is None:
                    continue
                for candidate in objact_candidates.get((map_id, event_id), []):
                    # This pass exists only for the MSBE records whose direct
                    # ObjActPartName binding is absent.  Named records already
                    # have a stronger direct MSBE binding and must not be
                    # counted again as common-event recoveries.
                    if candidate["obj_act_part_name"]:
                        continue
                    if candidate["obj_act_id"] in (None, -1, 0, 200):
                        continue
                    if candidate["obj_act_entity_id"] not in call_values:
                        continue
                    if candidate["obj_act_id"] not in call_values:
                        continue
                    same_call_objact_identity_match_count += 1
                    expanded = expanded_common_event_references(
                        common_event,
                        semantic_by_event.get(common_event_id, []),
                        call_values,
                    )
                    state_rows = []
                    for expanded_row in expanded:
                        name = str(
                            expanded_row["reference"].get("instruction_name") or ""
                        )
                        if "Set ObjAct State" not in name:
                            continue
                        values = {
                            arg.get("name"): arg.get("value_after_substitution")
                            for arg in expanded_row["args"]
                        }
                        if values.get("ObjAct Param ID") == candidate["obj_act_id"]:
                            matching_objact_param_state_row_count += 1
                            state_rows.append(
                                {
                                    "instruction_name": name,
                                    "instruction_index": expanded_row["reference"].get(
                                        "instruction_index"
                                    ),
                                    "reference_id": expanded_row["reference"].get("id"),
                                    "entity_id": values.get("Entity ID"),
                                    "objact_param_id": values.get("ObjAct Param ID"),
                                    "relative_target_index": values.get("Relative Target IDx"),
                                    "state": values.get("State"),
                                }
                            )
                    target_entity_ids = sorted(
                        {
                            row.get("entity_id")
                            for row in state_rows
                            if isinstance(row.get("entity_id"), int)
                            and row.get("entity_id") > 0
                        }
                    )
                    target_parts = [
                        row
                        for entity_id in target_entity_ids
                        for row in parts_by_map_entity.get((map_id, entity_id), [])
                    ]
                    if len(target_entity_ids) != 1 or len(target_parts) != 1:
                        continue
                    records.append(
                        {
                            "id": f"local-emevd-common-objact:{map_id}:{event_id}:{instruction.get('index')}:{candidate['candidate_id']}",
                            "candidate_id": candidate["candidate_id"],
                            "map_id": map_id,
                            "msbe_objact_event_id": candidate["event_id"],
                            "msbe_objact_event_name": candidate["event_name"],
                            "obj_act_id": candidate["obj_act_id"],
                            "obj_act_entity_id": candidate["obj_act_entity_id"],
                            "emevd_source_event_id": event_id,
                            "emevd_initialize_common_event_instruction_index": instruction.get("index"),
                            "common_event_id": common_event_id,
                            "call_values": call_values,
                            "state_rows": state_rows,
                            "target_part": target_parts[0],
                            "binding_status": "exact_common_event_objact_entity_param_state_target",
                            "routeable": False,
                            "verification_state": "local_raw_emevd_parameter_substitution_and_msbe_exact_part",
                        }
                    )

    output = {
        "schema": "elden-ring-local-emevd-common-event-objact-bindings@1",
        "source": {
            "map_root": str(map_root),
            "parsed_emevd_root": str(parsed_root),
            "semantic_common_references": str(semantic_path),
            "common_func_raw": str(common_raw_path),
            "common_func_raw_sha256": sha256(common_raw_path),
            "semantic_common_references_sha256": sha256(semantic_path),
        },
        "model": {
            "purpose": "strict raw InitializeCommonEvent parameter-substitution bindings for ObjAct records missing ObjActPartName",
            "uses_name_guessing": False,
            "uses_proximity": False,
            "routeable": False,
        },
        "status": {
            "record_count": len(records),
            "missing_part_name_candidate_count": missing_part_name_candidate_count,
            "initialize_common_event_call_count": initialize_common_event_call_count,
            "same_call_objact_identity_match_count": same_call_objact_identity_match_count,
            "matching_objact_param_state_row_count": matching_objact_param_state_row_count,
            "routeable_records": 0,
            "all_records_routeable_false": all(row["routeable"] is False for row in records),
        },
        "records": records,
        "note": "Only same-map calls with matching ObjActEntityID and ObjActParam ID and one exact MSBE Part target are retained.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
