#!/usr/bin/env python3
"""Build a compact semantic evidence index from locally parsed Elden Ring EMEVD.

This intentionally does not create traversal edges. It decodes the fixed
Elden Ring EMEDF argument layout and records condition/action references so a
later topology compiler can attach conditions to explicit MSB connections.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


TYPE_INFO = {
    0: (1, "byte"),
    1: (2, "uint16"),
    2: (4, "uint32"),
    3: (1, "sbyte"),
    4: (2, "int16"),
    5: (4, "int32"),
    6: (4, "single"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def align(offset: int, size: int) -> int:
    return (offset + size - 1) & ~(size - 1)


def decode_value(raw: bytes, offset: int, type_id: int) -> tuple[Any, int]:
    size, type_name = TYPE_INFO[type_id]
    offset = align(offset, size)
    if offset + size > len(raw):
        raise ValueError(f"argument exceeds buffer at {offset} for type {type_id}")
    chunk = raw[offset : offset + size]
    if type_id == 0:
        value: Any = chunk[0]
    elif type_id == 1:
        value = int.from_bytes(chunk, "little", signed=False)
    elif type_id == 2:
        value = int.from_bytes(chunk, "little", signed=False)
    elif type_id == 3:
        value = int.from_bytes(chunk, "little", signed=True)
    elif type_id == 4:
        value = int.from_bytes(chunk, "little", signed=True)
    elif type_id == 5:
        value = int.from_bytes(chunk, "little", signed=True)
    else:
        value = struct.unpack("<f", chunk)[0]
    return value, offset + size


def decode_args(instruction: dict[str, Any], definition: dict[str, Any]) -> list[dict[str, Any]]:
    raw = bytes.fromhex(instruction.get("args_hex", ""))
    decoded: list[dict[str, Any]] = []
    offset = 0
    for index, argument in enumerate(definition.get("args", [])):
        type_id = argument.get("type")
        if type_id not in TYPE_INFO:
            raise ValueError(f"unsupported EMEDF type {type_id}")
        value, end = decode_value(raw, offset, type_id)
        decoded.append(
            {
                "index": index,
                "name": argument.get("name"),
                "type": TYPE_INFO[type_id][1],
                "enum_name": argument.get("enum_name"),
                "value": value,
                "raw_offset": align(offset, TYPE_INFO[type_id][0]),
                "raw_size": TYPE_INFO[type_id][0],
            }
        )
        offset = end
    if offset > len(raw):
        raise ValueError("decoded argument buffer overflow")
    return decoded


def classify(class_name: str, instruction_name: str) -> str | None:
    lower = f"{class_name} {instruction_name}".casefold()
    if class_name.casefold().startswith("condition"):
        return "condition"
    keywords = (
        "event flag",
        "eventflag",
        "initialize event",
        "run event",
        "enable asset",
        "disable asset",
        "enable character",
        "disable character",
        "warp",
        "change map",
        "objact",
        "open map",
        "map loading",
        "cutscene",
        "move map",
    )
    if any(keyword in lower for keyword in keywords):
        return "action"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parsed-root", type=Path, required=True)
    parser.add_argument("--emedf", type=Path, required=True)
    parser.add_argument("--event-flags", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--references-output-root", type=Path)
    args = parser.parse_args()

    manifest = json.loads((args.parsed_root / "batch-manifest.json").read_text(encoding="utf-8"))
    emedf = json.loads(args.emedf.read_text(encoding="utf-8"))
    flag_rows = json.loads(args.event_flags.read_text(encoding="utf-8"))
    flag_names = {int(row["ID"]): {"name": row.get("Name"), "tags": row.get("Tags", [])} for row in flag_rows}
    definitions = {
        (int(group["index"]), int(instruction["index"])): instruction
        for group in emedf["main_classes"]
        for instruction in group.get("instrs", [])
    }

    references: list[dict[str, Any]] = []
    references_by_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    map_summaries: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "file_count": 0,
            "event_count": 0,
            "condition_count": 0,
            "action_count": 0,
            "event_flag_ids": set(),
            "instruction_names": Counter(),
        }
    )
    decode_failures: list[dict[str, str]] = []
    total_instructions = 0
    total_decoded = 0

    for file_path in sorted((args.parsed_root / "files").glob("*.json")):
        if file_path.name in {"batch-manifest.json"}:
            continue
        file_data = json.loads(file_path.read_text(encoding="utf-8"))
        source_file = str(file_data["source_file"])
        map_key = Path(source_file).name.removesuffix(".emevd.dcx")
        summary = map_summaries[map_key]
        summary["file_count"] += 1
        summary["event_count"] += len(file_data.get("events", []))
        for event in file_data.get("events", []):
            for instruction in event.get("instructions", []):
                total_instructions += 1
                key = (int(instruction["bank"]), int(instruction["id"]))
                definition = definitions.get(key)
                if definition is None:
                    continue
                category = classify(
                    next((group["name"] for group in emedf["main_classes"] if int(group["index"]) == key[0]), ""),
                    definition.get("name", ""),
                )
                if category is None:
                    continue
                try:
                    decoded = decode_args(instruction, definition)
                except (ValueError, struct.error) as exc:
                    decode_failures.append(
                        {
                            "source_file": source_file,
                            "event_id": str(event["id"]),
                            "instruction_index": str(instruction["index"]),
                            "opcode": f"{key[0]}:{key[1]}",
                            "error": str(exc),
                        }
                    )
                    continue
                total_decoded += 1
                summary[f"{category}_count"] += 1
                summary["instruction_names"][definition.get("name", "unknown")] += 1
                flag_ids: list[int] = []
                for argument in decoded:
                    name = str(argument.get("name") or "")
                    if "flag" in name.casefold() and "id" in name.casefold() and isinstance(argument.get("value"), int):
                        flag_id = int(argument["value"])
                        flag_ids.append(flag_id)
                        summary["event_flag_ids"].add(flag_id)
                reference = {
                        "id": f"local-emevd:{map_key}:{event['id']}:{instruction['index']}",
                        "source_file": source_file,
                        "event_id": event["id"],
                        "instruction_index": instruction["index"],
                        "bank": key[0],
                        "opcode": key[1],
                        "category": category,
                        "instruction_name": definition.get("name"),
                        "args": decoded,
                        "event_flag_ids": flag_ids,
                        "verification_state": "local_emevd_verified",
                    }
                references.append(reference)
                references_by_map[map_key].append(reference)

    maps = []
    for map_key, summary in sorted(map_summaries.items()):
        maps.append(
            {
                "map_key": map_key,
                "file_count": summary["file_count"],
                "event_count": summary["event_count"],
                "condition_count": summary["condition_count"],
                "action_count": summary["action_count"],
                "reference_count": summary["condition_count"] + summary["action_count"],
                "event_flag_ids": [
                    {"id": flag_id, **flag_names.get(flag_id, {})}
                    for flag_id in sorted(summary["event_flag_ids"])
                ],
                "instruction_names": dict(summary["instruction_names"].most_common()),
                "verification_state": "local_emevd_verified",
            }
        )

    reference_files: dict[str, str] = {}
    if args.references_output_root:
        args.references_output_root.mkdir(parents=True, exist_ok=True)
        for map_key, map_references in sorted(references_by_map.items()):
            reference_file = args.references_output_root / f"{map_key}.json"
            reference_file.write_text(
                json.dumps(
                    {
                        "schema": "elden-ring-local-emevd-semantic-references@1",
                        "map_key": map_key,
                        "reference_count": len(map_references),
                        "references": map_references,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            reference_files[map_key] = str(reference_file.resolve())

    output = {
        "schema": "elden-ring-local-emevd-semantic-index@1",
        "source": {
            "parsed_root": str(args.parsed_root.resolve()),
            "batch_manifest": str((args.parsed_root / "batch-manifest.json").resolve()),
            "emedf": str(args.emedf.resolve()),
            "emedf_sha256": sha256(args.emedf),
            "event_flags": str(args.event_flags.resolve()),
            "event_flags_sha256": sha256(args.event_flags),
            "references_output_root": str(args.references_output_root.resolve()) if args.references_output_root else None,
        },
        "status": {
            "parsed_files": manifest.get("success_count", 0),
            "parsed_events": manifest.get("event_count", 0),
            "parsed_instructions": total_instructions,
            "decoded_references": total_decoded,
            "decode_failures": len(decode_failures),
            "routeable": False,
        },
        "maps": maps,
        "reference_files": reference_files,
        "decode_failures": decode_failures,
        "note": "EMEVD semantic evidence only; this artifact does not create or prove physical traversal edges.",
    }
    if not args.references_output_root:
        output["references"] = references
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False))
    print(args.output)
    return 0 if not decode_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
