#!/usr/bin/env python3
"""Build conservative EMEVD control-flow traces for exact transition bindings.

The result is intentionally not a boolean guard solver. It follows the
syntactic branches and labels surrounding exact Warp instructions, preserving
the decoded conditions and actions that can reach each instruction.  A trace
is only promoted to ``syntactically_reachable``; the actual game-state
semantics of condition groups remain explicitly unresolved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from collections import defaultdict
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
REFERENCE_ID_RE = re.compile(r"^local-emevd:(?P<map>.+):(?P<event>\d+):(?P<instruction>\d+)$")


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
    decoded = []
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
            }
        )
        offset = end
    return decoded


def decoded_instruction(raw: dict[str, Any], definitions: dict[tuple[int, int], dict[str, Any]]) -> dict[str, Any]:
    bank = int(raw["bank"])
    opcode = int(raw["id"])
    definition = definitions.get((bank, opcode))
    payload = {
        "index": int(raw["index"]),
        "bank": bank,
        "opcode": opcode,
        "instruction_name": definition.get("name") if definition else None,
        "args": [],
        "decode_status": "decoded" if definition else "definition_missing",
    }
    if definition:
        try:
            payload["args"] = decode_args(raw, definition)
        except (ValueError, struct.error) as exc:
            payload["decode_status"] = f"decode_failed:{exc}"
    return payload


def arg_map(instruction: dict[str, Any]) -> dict[str, Any]:
    return {str(argument.get("name")): argument.get("value") for argument in instruction.get("args", [])}


def label_targets(instructions: list[dict[str, Any]]) -> dict[int, int]:
    targets = {}
    for instruction in instructions:
        if not str(instruction.get("instruction_name") or "").startswith("Label"):
            continue
        # The numeric label is an argument of the raw definition in all
        # current Elden Ring EMEVD label records; tolerate absent labels.
        args = arg_map(instruction)
        label = args.get("Label")
        if not isinstance(label, int):
            match = re.search(r"Label\s+(-?\d+)$", str(instruction.get("instruction_name") or ""))
            if match:
                label = int(match.group(1))
        if isinstance(label, int):
            targets[label] = instruction["index"]
    return targets


def successors(
    instruction: dict[str, Any],
    label_map: dict[int, int],
    max_index: int,
) -> list[tuple[int | None, dict[str, Any] | None]]:
    index = int(instruction["index"])
    name = str(instruction.get("instruction_name") or "")
    args = arg_map(instruction)
    next_index = index + 1 if index + 1 <= max_index else None
    if name == "GOTO Unconditionally":
        target = label_map.get(args.get("Label"))
        return [(target, {"taken": "label", "target": target})] if target is not None else [(None, {"taken": "unknown_label"})]
    if name.startswith("GOTO IF"):
        target = label_map.get(args.get("Label"))
        branches = []
        if target is not None:
            branches.append((target, {"taken": "condition_true", "target": target}))
        if next_index is not None:
            branches.append((next_index, {"taken": "condition_false", "target": next_index}))
        return branches or [(None, {"taken": "unknown_branch"})]
    if name.startswith("SKIP IF"):
        count = args.get("Number Of Skipped Lines")
        skip_target = index + int(count) + 1 if isinstance(count, int) else None
        branches = []
        if skip_target is not None and skip_target <= max_index:
            branches.append((skip_target, {"taken": "condition_true_skip", "target": skip_target}))
        if next_index is not None:
            branches.append((next_index, {"taken": "condition_false_fallthrough", "target": next_index}))
        return branches or [(None, {"taken": "unknown_skip"})]
    if name.startswith("END") and name != "END IF Condition Group State (Compiled)":
        # END IF Event Flag/World/Condition Group has a terminating branch;
        # preserve both possibilities instead of asserting one semantic.
        if name.startswith("END IF") and next_index is not None:
            return [(next_index, {"taken": "end_if_fallthrough", "target": next_index}), (None, {"taken": "end_if_terminate"})]
        return [(None, {"taken": "end"})]
    if name == "END IF Condition Group State (Compiled)":
        if next_index is not None:
            return [(next_index, {"taken": "end_if_fallthrough", "target": next_index}), (None, {"taken": "end_if_terminate"})]
        return [(None, {"taken": "end_if_terminate"})]
    if name.startswith("SKIP") and not name.startswith("SKIP IF"):
        count = args.get("Number Of Skipped Lines")
        target = index + int(count) + 1 if isinstance(count, int) else None
        return [(target, {"taken": "unconditional_skip", "target": target})] if target is not None else [(None, {"taken": "unknown_skip"})]
    return ([(next_index, None)] if next_index is not None else [(None, None)])


def find_paths(
    instructions: list[dict[str, Any]],
    target_index: int,
    labels: dict[int, int],
    max_paths: int = 32,
    max_steps: int = 512,
) -> tuple[list[list[dict[str, Any]]], bool]:
    by_index = {int(instruction["index"]): instruction for instruction in instructions}
    max_index = max(by_index) if by_index else -1
    paths: list[list[dict[str, Any]]] = []
    truncated = False
    stack: list[tuple[int, list[dict[str, Any]], set[int]]] = [(0, [], set())]
    while stack:
        index, branch_trace, visited = stack.pop()
        if index == target_index:
            paths.append(branch_trace)
            if len(paths) >= max_paths:
                truncated = bool(stack)
                break
            continue
        if index not in by_index or len(branch_trace) > max_steps:
            truncated = True
            continue
        if index in visited:
            truncated = True
            continue
        instruction = by_index[index]
        next_visited = visited | {index}
        branches = successors(instruction, labels, max_index)
        for target, decision in reversed(branches):
            if target is None:
                continue
            new_trace = branch_trace
            if decision is not None:
                new_trace = branch_trace + [
                    {
                        "instruction_index": index,
                        "instruction_name": instruction.get("instruction_name"),
                        "args": instruction.get("args", []),
                        **decision,
                    }
                ]
            stack.append((target, new_trace, next_visited))
    return paths, truncated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transition-audit", type=Path, required=True)
    parser.add_argument("--parsed-root", type=Path, required=True)
    parser.add_argument("--emedf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    audit_path = args.transition_audit.resolve()
    parsed_root = args.parsed_root.resolve()
    emedf_path = args.emedf.resolve()
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    emedf = json.loads(emedf_path.read_text(encoding="utf-8"))
    definitions = {
        (int(group["index"]), int(instruction["index"])): instruction
        for group in emedf["main_classes"]
        for instruction in group.get("instrs", [])
    }

    references: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    transition_refs: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    all_bindings = [
        *audit.get("scripted_warp_bindings", []),
        *audit.get("scripted_map_warp_bindings", []),
    ]
    for binding in all_bindings:
        reference = binding.get("emevd_reference") or {}
        map_id = binding.get("from", {}).get("map_id")
        event_id = reference.get("event_id")
        instruction_index = reference.get("instruction_index")
        if not isinstance(map_id, str) or not isinstance(event_id, int) or not isinstance(instruction_index, int):
            continue
        transition_refs[(map_id, event_id)].append(
            {
                "binding_id": binding.get("id"),
                "instruction_index": instruction_index,
                "transition_kind": binding.get("transition_kind"),
            }
        )

    trace_records = []
    decode_failures = 0
    for (map_id, event_id), binding_refs in sorted(transition_refs.items()):
        path = parsed_root / "files" / f"{map_id}.json"
        if not path.is_file():
            trace_records.append(
                {
                    "map_id": map_id,
                    "event_id": event_id,
                    "status": "source_event_file_missing",
                    "bindings": binding_refs,
                }
            )
            continue
        file_payload = json.loads(path.read_text(encoding="utf-8"))
        event = next((row for row in file_payload.get("events", []) if int(row.get("id", -1)) == event_id), None)
        if event is None:
            trace_records.append(
                {
                    "map_id": map_id,
                    "event_id": event_id,
                    "status": "source_event_missing",
                    "bindings": binding_refs,
                }
            )
            continue
        instructions = [decoded_instruction(raw, definitions) for raw in event.get("instructions", [])]
        decode_failures += sum(row["decode_status"] != "decoded" for row in instructions)
        labels = label_targets(instructions)
        targets = sorted({int(row["instruction_index"]) for row in binding_refs})
        target_traces = []
        for target_index in targets:
            paths, truncated = find_paths(instructions, target_index, labels)
            branch_sets = [
                {int(item["instruction_index"]) for item in branch_path}
                for branch_path in paths
            ]
            common_branches = sorted(set.intersection(*branch_sets)) if branch_sets else []
            target_traces.append(
                {
                    "instruction_index": target_index,
                    "instruction": next((row for row in instructions if row["index"] == target_index), None),
                    "syntactic_path_count_sampled": len(paths),
                    "path_search_truncated": truncated,
                    "common_branch_instruction_indices": common_branches,
                    "guard_resolution_status": "syntactic_branch_trace_only" if paths else "no_syntactic_path_found",
                    "paths": [
                        {
                            "branch_trace": branch_path,
                            "branch_instruction_indices": [item["instruction_index"] for item in branch_path],
                        }
                        for branch_path in paths
                    ],
                }
            )
        trace_records.append(
            {
                "map_id": map_id,
                "event_id": event_id,
                "status": "source_event_decoded",
                "instruction_count": len(instructions),
                "label_count": len(labels),
                "bindings": binding_refs,
                "target_traces": target_traces,
                "instructions": instructions,
            }
        )

    output = {
        "schema": "elden-ring-local-emevd-guard-traces@1",
        "source": {
            "transition_audit": str(audit_path),
            "transition_audit_sha256": sha256(audit_path),
            "parsed_root": str(parsed_root),
            "emedf": str(emedf_path),
            "emedf_sha256": sha256(emedf_path),
        },
        "model": {
            "purpose": "syntactic control-flow evidence for exact transition bindings",
            "condition_semantics": "not solved; condition groups and game-state meaning remain unresolved",
            "path_semantics": "bounded CFG paths, not proof that every branch is enabled in a player save",
            "routeable": False,
        },
        "status": {
            "transition_binding_count": len(all_bindings),
            "event_trace_count": len(trace_records),
            "decoded_event_count": sum(row.get("status") == "source_event_decoded" for row in trace_records),
            "decode_failures": decode_failures,
            "targets_with_syntactic_path": sum(
                bool(target.get("syntactic_path_count_sampled"))
                for row in trace_records
                for target in row.get("target_traces", [])
            ),
            "targets_without_syntactic_path": sum(
                not bool(target.get("syntactic_path_count_sampled"))
                for row in trace_records
                for target in row.get("target_traces", [])
            ),
            "routeable_records": 0,
            "all_records_routeable_false": True,
        },
        "events": trace_records,
        "note": "A syntactic path to a Warp instruction is preserved as evidence only. It is not a resolved guard and does not promote a transition to a routeable edge.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0 if decode_failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
