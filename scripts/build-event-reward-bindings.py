#!/usr/bin/env python3
"""Build an independent event-reward evidence catalog.

This catalog records direct EMEVD item-award instructions and the local item
lot rows they reference.  It deliberately does not guess an NPC or quest
identity: an event can be a boss reward, a story reward, a system grant, or a
quest step.  Event flags are retained as evidence for a later classification
pass.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FMG_INDEX = ROOT / "data" / "v1" / "entities" / "official-fmg-bilingual-index.json"
DEFAULT_FLAGS = ROOT.parent.parent / "local-snapshots" / "elden-ring-20260818" / "supporting" / "smithbox-er-event-flags.json"
_suffix_re = re.compile(r"(_dlc0[12])?\.fmg$")

LOT_CATEGORY_TABLES = {
    1: "GoodsName",
    2: "WeaponName",
    3: "ProtectorName",
    4: "AccessoryName",
    5: "GemName",
}
LOT_CATEGORY_KIND = {
    1: "item",
    2: "weapon",
    3: "armor",
    4: "accessory",
    5: "ash_of_war",
}
FMG_TO_PARAM = {
    "GoodsName": "EquipParamGoods",
    "WeaponName": "EquipParamWeapon",
    "ProtectorName": "EquipParamProtector",
    "AccessoryName": "EquipParamAccessory",
    "GemName": "EquipParamGem",
}
LOT_CHAIN_REFERENCE = "https://soulsmodding.wikidot.com/param:itemlotparam"
TYPE_SIZE = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 8}


def load_name_tables() -> dict[str, dict[int, dict[str, str]]]:
    records = json.loads(FMG_INDEX.read_text(encoding="utf-8"))["records"]
    tables: dict[str, dict[int, dict[str, str]]] = {}
    for record in records:
        if record["language"] not in ("engus", "zhocn"):
            continue
        fmg = _suffix_re.sub("", record["fmg"].replace("\\", "/").split("/")[-1])
        entry = tables.setdefault(fmg, {}).setdefault(int(record["id"]), {})
        entry["en" if record["language"] == "engus" else "zh"] = record["text"]
    return tables


def clean_name(value: str | None) -> str | None:
    if not value or value in ("[ERROR]", ""):
        return None
    return value.removeprefix("[ERROR]").strip() or None


def decode_args(raw: bytes, definition: dict[str, Any]) -> list[int | None]:
    values: list[int | None] = []
    offset = 0
    for argument in definition.get("args", []):
        size = TYPE_SIZE[int(argument["type"])]
        offset = (offset + size - 1) & ~(size - 1)
        chunk = raw[offset:offset + size]
        if len(chunk) != size:
            raise ValueError("truncated instruction arguments")
        kind = int(argument["type"])
        if kind == 6:
            values.append(None)
        else:
            values.append(int.from_bytes(chunk, "little", signed=kind in (1, 3, 5)))
        offset += size
    return values


def decode_direct_item_args(raw: bytes) -> tuple[int, int, int, int]:
    """Decode 2003:43 using its verified 16-byte on-disk layout.

    The EMEDF semantic type codes do not by themselves describe the padding
    and 32-bit storage used by the final two arguments. The parsed instruction
    bytes and Smithbox decoder both agree on B3x/i/I/I.
    """
    if len(raw) < 16:
        raise ValueError("truncated direct item arguments")
    return struct.unpack_from("<B3xiII", raw, 0)


def load_rows(param_dir: Path, table: str) -> dict[int, dict[str, Any]]:
    rows = json.loads((param_dir / f"{table}.json").read_text(encoding="utf-8"))["rows"]
    return {int(row["id"]): row["cells"] for row in rows}


def load_flag_names(path: Path) -> dict[int, dict[str, Any]]:
    if not path.is_file():
        return {}
    return {int(row["ID"]): row for row in json.loads(path.read_text(encoding="utf-8"))}


def event_flags(reference_path: Path, event_id: int, flag_names: dict[int, dict[str, Any]]) -> dict[str, Any]:
    if not reference_path.is_file():
        return {"eventFlagIds": [], "eventFlags": [], "evidenceStatus": "no_semantic_reference"}
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    ids: set[int] = set()
    for reference in payload.get("references", []):
        if reference.get("event_id") != event_id:
            continue
        for value in reference.get("event_flag_ids", []):
            if isinstance(value, (int, float)):
                ids.add(int(value))
    return {
        "eventFlagIds": sorted(ids),
        "eventFlags": [
            {"id": flag_id, "name": flag_names[flag_id].get("Name"), "tags": flag_names[flag_id].get("Tags", [])}
            for flag_id in sorted(ids) if flag_id in flag_names
        ],
        "evidenceStatus": "semantic_event_flags_verified",
    }


def expand_lot_chain(
    root_lot_id: int,
    lot_by_id: dict[int, dict],
    referenced_lot_ids: set[int],
) -> list[int]:
    """Expand consecutive ItemLotParam rows for one event-award root."""
    chain: list[int] = []
    lot_id = root_lot_id
    while lot_id in lot_by_id:
        if lot_id != root_lot_id and lot_id in referenced_lot_ids:
            break
        chain.append(lot_id)
        lot_id += 1
    return chain


def initialize_event_call_sites(
    files: dict[str, dict[str, Any]],
    template_file: str,
    event_id: int,
) -> list[dict[str, Any]]:
    """Resolve exact parameter buffers supplied to one event template.

    Common-function events may be called from every map through Initialize
    Common Event. Ordinary events are file-local and use Initialize Event.
    Keeping those scopes separate prevents same-number events in other maps
    from being joined accidentally.
    """
    scopes = files.items() if template_file == "common_func" else [
        (template_file, files[template_file])
    ]
    expected_opcode = (2000, 6) if template_file == "common_func" else (2000, 0)
    calls = []
    for caller_file, payload in scopes:
        for caller_event in payload.get("events", []):
            for instruction in caller_event.get("instructions", []):
                if (instruction.get("bank"), instruction.get("id")) != expected_opcode:
                    continue
                raw = bytes.fromhex(str(instruction.get("args_hex") or ""))
                if len(raw) < 8 or struct.unpack_from("<I", raw, 4)[0] != event_id:
                    continue
                calls.append({
                    "callerFile": caller_file,
                    "callerEventId": int(caller_event["id"]),
                    "callerInstructionIndex": int(instruction["index"]),
                    "parameterBuffer": raw[8:],
                })
    return calls


def build(parsed_dir: Path, semantic_dir: Path, emedf_path: Path, param_dir: Path, flags_path: Path) -> dict[str, Any]:
    emedf = json.loads(emedf_path.read_text(encoding="utf-8"))
    definitions: dict[tuple[int, int], dict[str, Any]] = {}
    direct_item_definition: dict[str, Any] | None = None
    for group in emedf["main_classes"]:
        for instruction in group.get("instrs", []):
            if instruction.get("name") in {"Award Item Lot", "Award Items (Including Clients)"}:
                definitions[(int(group["index"]), int(instruction["index"]))] = instruction
            elif instruction.get("name") == "Directly Give Player Item":
                direct_item_definition = instruction
    if not definitions:
        raise SystemExit("award instruction definitions not found")
    if direct_item_definition is None:
        raise SystemExit("direct item instruction definition not found")

    tables = load_name_tables()
    flag_names = load_flag_names(flags_path)
    lots_by_table: dict[str, dict[int, dict]] = {}
    for table in ("ItemLotParam_map", "ItemLotParam_enemy"):
        lots_by_table[table] = load_rows(param_dir, table)
    custom_weapons = load_rows(param_dir, "EquipParamCustomWeapon")

    records: list[dict[str, Any]] = []
    raw_awards = 0
    zero_lots = 0
    decoded_awards: list[dict[str, Any]] = []
    unresolved_parameterized_awards: list[dict[str, Any]] = []
    literal_awards = 0
    substituted_awards = 0
    raw_direct_item_instructions = 0
    literal_direct_item_bindings = 0
    substituted_direct_item_bindings = 0
    unresolved_direct_item_instructions: list[dict[str, Any]] = []
    event_files = {
        file_path.stem: json.loads(file_path.read_text(encoding="utf-8"))
        for file_path in sorted(parsed_dir.glob("*.json"))
        if file_path.name != "batch-manifest.json"
    }
    for source_file, file_data in sorted(event_files.items()):
        file_path = parsed_dir / f"{source_file}.json"
        map_key = Path(file_data.get("source_file", file_path.name)).name.removesuffix(".emevd.dcx")
        ref_path = semantic_dir / file_path.name
        for event in file_data.get("events", []):
            mappings_by_instruction: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for mapping in event.get("parameters", []):
                mappings_by_instruction[int(mapping.get("instruction_index", -1))].append(mapping)
            for instruction in event.get("instructions", []):
                opcode = (int(instruction.get("bank", -1)), int(instruction.get("id", -1)))
                definition = definitions.get(opcode)
                if definition is None:
                    continue
                raw_awards += 1
                raw = bytes.fromhex(str(instruction.get("args_hex") or ""))
                instruction_index = int(instruction["index"])
                mappings = [
                    mapping for mapping in mappings_by_instruction.get(instruction_index, [])
                    if int(mapping.get("target_start_byte", -1)) == 0
                    and int(mapping.get("byte_count", 0)) == 4
                ]
                resolved_sources: list[dict[str, Any]] = []
                if not mappings:
                    try:
                        decoded = decode_args(raw, definition)
                    except (ValueError, IndexError):
                        continue
                    lot_id = int(decoded[0]) if decoded and decoded[0] is not None else 0
                    if lot_id <= 0:
                        zero_lots += 1
                        continue
                    literal_awards += 1
                    resolved_sources.append({
                        "lotId": lot_id,
                        "map": map_key,
                        "eventId": int(event["id"]),
                        "instructionIndex": instruction_index,
                        "resolution": "literal_instruction_argument",
                    })
                else:
                    calls = initialize_event_call_sites(
                        event_files, source_file, int(event["id"])
                    )
                    for mapping in mappings:
                        offset = int(mapping["source_start_byte"])
                        for call in calls:
                            buffer = call["parameterBuffer"]
                            if offset < 0 or offset + 4 > len(buffer):
                                continue
                            lot_id = struct.unpack_from("<i", buffer, offset)[0]
                            if lot_id <= 0:
                                continue
                            resolved_sources.append({
                                "lotId": lot_id,
                                "map": call["callerFile"],
                                "eventId": call["callerEventId"],
                                "instructionIndex": call["callerInstructionIndex"],
                                "templateMap": map_key,
                                "templateEventId": int(event["id"]),
                                "templateInstructionIndex": instruction_index,
                                "parameterSourceByte": offset,
                                "resolution": "initialize_event_parameter_substitution",
                            })
                    if not resolved_sources:
                        unresolved_parameterized_awards.append({
                            "file": source_file,
                            "eventId": int(event["id"]),
                            "instructionIndex": instruction_index,
                            "reason": "parameterized_template_has_no_verified_call_site",
                        })
                for source in resolved_sources:
                    lot_id = int(source["lotId"])
                    lot_table = next(
                        (
                            table for table in ("ItemLotParam_map", "ItemLotParam_enemy")
                            if lot_id in lots_by_table[table]
                        ),
                        None,
                    )
                    if lot_table is None:
                        continue
                    if source["resolution"] == "initialize_event_parameter_substitution":
                        substituted_awards += 1
                    decoded_awards.append({
                        "file_path": file_path,
                        "map_key": source["map"],
                        "ref_path": ref_path,
                        "event": event,
                        "instruction": instruction,
                        "source": source,
                        "lot_id": lot_id,
                        "lot_table": lot_table,
                    })

    # Direct item grants do not reference ItemLotParam. Expand every template
    # whose item id or backing event-flag range is parameterized at its exact
    # Initialize Event call sites. This keeps the item fact while avoiding an
    # invented quest/NPC identity or endpoint.
    for source_file, file_data in sorted(event_files.items()):
        file_path = parsed_dir / f"{source_file}.json"
        map_key = Path(file_data.get("source_file", file_path.name)).name.removesuffix(".emevd.dcx")
        ref_path = semantic_dir / file_path.name
        for event in file_data.get("events", []):
            mappings_by_instruction: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for mapping in event.get("parameters", []):
                mappings_by_instruction[int(mapping.get("instruction_index", -1))].append(mapping)
            for instruction in event.get("instructions", []):
                if (int(instruction.get("bank", -1)), int(instruction.get("id", -1))) != (2003, 43):
                    continue
                raw_direct_item_instructions += 1
                instruction_index = int(instruction["index"])
                raw = bytes.fromhex(str(instruction.get("args_hex") or ""))
                relevant_mappings = [
                    mapping
                    for mapping in mappings_by_instruction.get(instruction_index, [])
                    if int(mapping.get("target_start_byte", -1)) in (4, 8)
                    and int(mapping.get("byte_count", 0)) == 4
                ]
                resolved_sources: list[tuple[bytes, dict[str, Any]]] = []
                if not relevant_mappings:
                    resolved_sources.append((raw, {
                        "map": map_key,
                        "eventId": int(event["id"]),
                        "instructionIndex": instruction_index,
                        "resolution": "direct_literal_instruction_arguments",
                    }))
                else:
                    calls = initialize_event_call_sites(event_files, source_file, int(event["id"]))
                    for call in calls:
                        resolved_raw = bytearray(raw)
                        complete = True
                        for mapping in relevant_mappings:
                            source_offset = int(mapping["source_start_byte"])
                            target_offset = int(mapping["target_start_byte"])
                            buffer = call["parameterBuffer"]
                            if source_offset < 0 or source_offset + 4 > len(buffer):
                                complete = False
                                break
                            resolved_raw[target_offset:target_offset + 4] = buffer[source_offset:source_offset + 4]
                        if not complete:
                            continue
                        resolved_sources.append((bytes(resolved_raw), {
                            "map": call["callerFile"],
                            "eventId": call["callerEventId"],
                            "instructionIndex": call["callerInstructionIndex"],
                            "templateMap": map_key,
                            "templateEventId": int(event["id"]),
                            "templateInstructionIndex": instruction_index,
                            "resolution": "initialize_event_parameter_substitution",
                            "parameterMappings": [
                                {
                                    "targetByte": int(mapping["target_start_byte"]),
                                    "sourceByte": int(mapping["source_start_byte"]),
                                    "byteCount": 4,
                                }
                                for mapping in relevant_mappings
                            ],
                        }))
                    if not resolved_sources:
                        item_id_is_parameterized = any(
                            int(mapping["target_start_byte"]) == 4
                            for mapping in relevant_mappings
                        )
                        if not item_id_is_parameterized:
                            resolved_sources.append((raw, {
                                "map": map_key,
                                "eventId": int(event["id"]),
                                "instructionIndex": instruction_index,
                                "resolution": "direct_literal_item_parameterized_flag",
                                "baseEventFlagStatus": "parameterized_call_site_unresolved",
                            }))
                        else:
                            unresolved_direct_item_instructions.append({
                                "file": source_file,
                                "eventId": int(event["id"]),
                                "instructionIndex": instruction_index,
                                "reason": "parameterized_direct_item_template_has_no_verified_call_site",
                            })
                for resolved_raw, source in resolved_sources:
                    try:
                        decoded = decode_direct_item_args(resolved_raw)
                    except (ValueError, IndexError, struct.error):
                        continue
                    item_type = int(decoded[0]) if decoded[0] is not None else -1
                    item_id = int(decoded[1]) if decoded[1] is not None else -1
                    base_flag = int(decoded[2]) if decoded[2] is not None else -1
                    used_flag_bits = int(decoded[3]) if decoded[3] is not None else -1
                    if source["resolution"] == "direct_literal_item_parameterized_flag":
                        base_flag = -1
                    name_entry = tables.get("GoodsName", {}).get(item_id, {})
                    english = clean_name(name_entry.get("en"))
                    if item_type != 3 or item_id <= 0 or not english:
                        unresolved_direct_item_instructions.append({
                            "file": source_file,
                            "eventId": int(event["id"]),
                            "instructionIndex": instruction_index,
                            "itemType": item_type,
                            "itemId": item_id,
                            "reason": "direct_item_type_or_official_name_unresolved",
                        })
                        continue
                    source.update({
                        "itemType": item_type,
                        "itemId": item_id,
                        "baseEventFlagId": base_flag,
                        "usedEventFlagBits": used_flag_bits,
                    })
                    if source["resolution"] in {
                        "direct_literal_instruction_arguments",
                        "direct_literal_item_parameterized_flag",
                    }:
                        literal_direct_item_bindings += 1
                        binding_id = f"event-reward-direct-{map_key}-{source['eventId']}-{source['instructionIndex']}"
                    else:
                        substituted_direct_item_bindings += 1
                        binding_id = (
                            f"event-reward-direct-{source['map']}-{source['eventId']}-{source['instructionIndex']}"
                            f"-via-{source['templateMap']}-{source['templateEventId']}-{source['templateInstructionIndex']}"
                        )
                    flags = event_flags(ref_path, int(event["id"]), flag_names)
                    records.append({
                        "id": binding_id,
                        "method": "event_reward",
                        "map": source["map"],
                        "eventId": int(source["eventId"]),
                        "instructionIndex": int(source["instructionIndex"]),
                        "awardSource": source,
                        "directGrant": {
                            "instruction": "Directly Give Player Item",
                            "itemType": item_type,
                            "itemId": item_id,
                            "baseEventFlagId": base_flag,
                            "usedEventFlagBits": used_flag_bits,
                        },
                        "items": [{
                            "item": f"item_{re.sub(r'[^a-z0-9]+', '_', english.lower()).strip('_')}",
                            "name": {
                                "en": english,
                                "zh": clean_name(name_entry.get("zh")) or english,
                            },
                            "sourceParam": "EquipParamGoods",
                            "sourceParamId": item_id,
                            "directItemType": item_type,
                            "num": None,
                            "quantityStatus": "not_encoded_as_literal_quantity",
                        }],
                        "sourceItemLotRows": [],
                        "eventFlags": flags["eventFlags"],
                        "eventFlagIds": sorted(set(flags["eventFlagIds"] + ([base_flag] if base_flag >= 0 else []))),
                        "taskStatus": "unclassified",
                        "evidence": [
                            f"local EMEVD {map_key} event {event['id']} direct item instruction {instruction_index}",
                            source["resolution"],
                            f"official EquipParamGoods/GoodsName row {item_id}",
                            flags["evidenceStatus"],
                        ],
                        "verification": "local_emevd_direct_goods_verified",
                    })

    roots_by_table: dict[str, set[int]] = {
        table: {
            award["lot_id"] for award in decoded_awards
            if award["lot_table"] == table
        }
        for table in lots_by_table
    }
    for award in decoded_awards:
        lot_id = award["lot_id"]
        lot_table = award["lot_table"]
        lot_by_id = lots_by_table[lot_table]
        chain_ids = expand_lot_chain(lot_id, lot_by_id, roots_by_table[lot_table])
        items = []
        for chain_lot_id in chain_ids:
            lot = lot_by_id[chain_lot_id]
            for slot in range(1, 9):
                item_id = lot.get(f"lotItemId{slot:02d}")
                category = lot.get(f"lotItemCategory{slot:02d}")
                if not item_id or item_id <= 0:
                    continue
                custom = custom_weapons.get(item_id) if category == 6 else None
                if custom:
                    resolved_item_id = int(custom.get("baseWepId", -1))
                    table = "WeaponName"
                    kind = "weapon"
                else:
                    resolved_item_id = item_id
                    table = LOT_CATEGORY_TABLES.get(category)
                    kind = LOT_CATEGORY_KIND.get(category)
                name_entry = tables.get(table, {}).get(resolved_item_id, {}) if table else {}
                english = clean_name(name_entry.get("en"))
                if not english or not table or not kind:
                    continue
                item = {
                    "item": f"{kind}_{re.sub(r'[^a-z0-9]+', '_', english.lower()).strip('_')}",
                    "name": {"en": english, "zh": clean_name(name_entry.get("zh")) or english},
                    "sourceParam": FMG_TO_PARAM[table],
                    "sourceParamId": resolved_item_id,
                    "category": category,
                    "lot": chain_lot_id,
                    "slot": slot,
                    "num": lot.get(f"lotItemNum{slot:02d}"),
                }
                if custom:
                    item.update({
                        "sourceCustomWeaponId": item_id,
                        "reinforcementLevel": int(custom.get("reinforceLv", 0)),
                        "attachedGemId": int(custom.get("gemId", -1)),
                    })
                items.append(item)
        if not items:
            continue
        flags = event_flags(award["ref_path"], int(award["event"]["id"]), flag_names)
        source = award["source"]
        if source["resolution"] == "literal_instruction_argument":
            binding_id = (
                f"event-reward-{award['map_key']}-{source['eventId']}-"
                f"{source['instructionIndex']}"
            )
        else:
            binding_id = (
                f"event-reward-{award['map_key']}-{source['eventId']}-"
                f"{source['instructionIndex']}-via-{source['templateMap']}-"
                f"{source['templateEventId']}-{source['templateInstructionIndex']}"
            )
        records.append({
            "id": binding_id,
            "method": "event_reward",
            "map": award["map_key"],
            "eventId": int(source["eventId"]),
            "instructionIndex": int(source["instructionIndex"]),
            "awardSource": source,
            "itemLot": {"param": lot_table, "rowId": lot_id},
            "items": items,
            "sourceItemLotRows": chain_ids,
            "eventFlags": flags["eventFlags"],
            "eventFlagIds": flags["eventFlagIds"],
            "taskStatus": "unclassified",
            "evidence": [
                (
                    f"local EMEVD {award['map_key']} event {source['eventId']} "
                    f"award call {source['instructionIndex']}"
                ),
                source["resolution"],
                f"local {lot_table} row {lot_id}",
                "sequential " + lot_table + " continuation rows "
                + ",".join(str(value) for value in chain_ids),
                flags["evidenceStatus"],
            ],
            "verification": (
                "local_emevd_and_param_verified_sequential_lot_chain"
                if len(chain_ids) > 1 else "local_emevd_and_param_verified"
            ),
        })

    return {
        "schema": "elden-ring-event-reward-bindings@1",
        "builtFrom": {
            "parsedEmevd": str(parsed_dir),
            "semanticReferences": str(semantic_dir),
            "emedf": str(emedf_path),
            "paramDir": str(param_dir),
            "eventFlags": str(flags_path),
            "itemLotChainReference": LOT_CHAIN_REFERENCE,
            "policy": "event award is factual; quest or NPC identity is never inferred from an event alone",
        },
        "stats": {
            "rawAwardInstructions": raw_awards,
            "zeroLotInstructions": zero_lots,
            "literalAwardBindings": literal_awards,
            "substitutedAwardBindings": substituted_awards,
            "unresolvedParameterizedAwards": len(unresolved_parameterized_awards),
            "rawDirectItemInstructions": raw_direct_item_instructions,
            "literalDirectItemBindings": literal_direct_item_bindings,
            "substitutedDirectItemBindings": substituted_direct_item_bindings,
            "unresolvedDirectItemInstructions": len(unresolved_direct_item_instructions),
            "bindings": len(records),
            "withEventFlags": sum(bool(record["eventFlagIds"]) for record in records),
            "taskUnclassified": len(records),
        },
        "bindings": records,
        "unresolvedParameterizedAwards": unresolved_parameterized_awards,
        "unresolvedDirectItemInstructions": unresolved_direct_item_instructions,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parsed-emevd", type=Path, required=True)
    parser.add_argument("--semantic-references", type=Path, required=True)
    parser.add_argument("--emedf", type=Path, required=True)
    parser.add_argument("--param-dir", type=Path, required=True)
    parser.add_argument("--event-flags", type=Path, default=DEFAULT_FLAGS)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "v1" / "entities" / "event-reward-bindings.json")
    args = parser.parse_args()
    payload = build(args.parsed_emevd, args.semantic_references, args.emedf, args.param_dir, args.event_flags)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2))
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
