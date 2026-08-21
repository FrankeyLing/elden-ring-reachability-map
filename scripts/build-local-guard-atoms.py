#!/usr/bin/env python3
"""Compile conservative guard-atom candidates from EMEVD CFG traces.

This pass translates branch instructions into explicit predicate candidates
without deciding condition-group truth or current save state.  It is the
bridge between a syntactic CFG trace and a future formal guarded edge.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def args_map(instruction: dict[str, Any]) -> dict[str, Any]:
    return {str(arg.get("name")): arg.get("value") for arg in instruction.get("args", [])}


EVENT_FLAG_ARGUMENT_NAMES = {
    "Target Event Flag ID",
    "Base Event Flag ID",
    "ObjAct Event Flag",
}


def event_flag_record(
    flag_id: Any,
    flags: dict[int, dict[str, Any]],
    documented_flags: dict[int, dict[str, Any]],
    local_references: dict[int, list[dict[str, Any]]],
    public_flags: dict[int, dict[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(flag_id, int):
        return None
    references = local_references.get(flag_id, [])
    local_reference_fields = {
        "local_emevd_reference_status": (
            "exact_event_instruction_reference" if references else "not_referenced_in_event"
        ),
        "local_emevd_references": references,
    }
    public_record = public_flags.get(flag_id)
    public_reference_fields: dict[str, Any] = {
        "external_public_event_flag_status": (
            "exact_public_index_reference"
            if public_record is not None
            else "not_found_in_pinned_public_index"
        ),
    }
    if public_record is not None:
        public_reference_fields["external_public_event_flag_record"] = public_record
    row = flags.get(flag_id)
    if row is not None:
        return {
            "id": flag_id,
            "name": row.get("Name"),
            "tags": row.get("Tags", []),
            "status": "local_event_flag_alias_verified",
            "source": "Smithbox EventFlags.json",
            **local_reference_fields,
            **public_reference_fields,
        }
    documented = documented_flags.get(flag_id)
    if documented is not None:
        return {
            "id": flag_id,
            "name": documented.get("description"),
            "tags": documented.get("tags", []),
            "status": "local_event_flag_documentation_verified",
            "source": documented.get("source"),
            "raw_fields": documented.get("raw_fields"),
            **local_reference_fields,
            **public_reference_fields,
        }
    return {
        "id": flag_id,
        "status": "alias_and_documentation_missing",
        **local_reference_fields,
        **public_reference_fields,
    }


def event_local_flag_references(
    instructions: list[dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    references: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for instruction in instructions:
        for argument in instruction.get("args", []):
            if not isinstance(argument, dict):
                continue
            if argument.get("name") not in EVENT_FLAG_ARGUMENT_NAMES:
                continue
            flag_id = argument.get("value")
            if not isinstance(flag_id, int):
                continue
            references[flag_id].append(
                {
                    "source_instruction_index": instruction.get("index"),
                    "instruction_name": instruction.get("instruction_name"),
                    "argument_name": argument.get("name"),
                }
            )
    return dict(references)


def parse_public_event_flag_index(path: Path | None) -> dict[int, dict[str, Any]]:
    if path is None or not path.is_file():
        return {}
    records: dict[int, dict[str, Any]] = {}
    current_section = None
    row_pattern = re.compile(
        r"^\|\s*(-?\d+)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*(.*?)\s*\|\s*$"
    )
    section_pattern = re.compile(r"^##\s+(.+?)\s*$")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        section_match = section_pattern.match(line)
        if section_match:
            current_section = section_match.group(1).strip()
            continue
        row_match = row_pattern.match(line)
        if not row_match:
            continue
        flag_id = int(row_match.group(1))
        records[flag_id] = {
            "id": flag_id,
            "flag_count": row_match.group(2).strip(),
            "usage_type": row_match.group(3).strip(),
            "playlog_category": row_match.group(4).strip(),
            "name": row_match.group(5).strip(),
            "section": current_section,
            "source": str(path),
        }
    return records


def enrich_structure(
    value: Any,
    flags: dict[int, dict[str, Any]],
    documented_flags: dict[int, dict[str, Any]],
    local_references: dict[int, list[dict[str, Any]]],
    public_flags: dict[int, dict[str, Any]],
    seen: set[int],
) -> Any:
    if isinstance(value, list):
        return [
            enrich_structure(
                item,
                flags,
                documented_flags,
                local_references,
                public_flags,
                seen,
            )
            for item in value
        ]
    if not isinstance(value, dict):
        return value
    enriched = {
        key: enrich_structure(
            item,
            flags,
            documented_flags,
            local_references,
            public_flags,
            seen,
        )
        for key, item in value.items()
    }
    flag_ids: set[int] = set()
    if isinstance(enriched.get("flag_id"), int):
        flag_ids.add(enriched["flag_id"])
    for argument in enriched.get("args", []):
        if not isinstance(argument, dict):
            continue
        if argument.get("name") in {"Target Event Flag ID", "Base Event Flag ID", "ObjAct Event Flag"}:
            if isinstance(argument.get("value"), int):
                flag_ids.add(argument["value"])
    if flag_ids:
        for flag_id in flag_ids:
            seen.add(flag_id)
        enriched["event_flag_catalog"] = [
            event_flag_record(
                flag_id,
                flags,
                documented_flags,
                local_references,
                public_flags,
            )
            for flag_id in sorted(flag_ids)
        ]
    return enriched


def direct_predicate(instruction: dict[str, Any]) -> dict[str, Any]:
    args = args_map(instruction)
    name = str(instruction.get("instruction_name") or "")
    if "Event Flag" in name:
        return {
            "kind": "event_flag",
            "instruction_name": name,
            "flag_id": args.get("Target Event Flag ID"),
            "desired_state": args.get("Desired Flag State"),
            "source_instruction_index": instruction.get("instruction_index", instruction.get("index")),
        }
    if "Condition Group State" in name:
        return {
            "kind": "condition_group_state",
            "instruction_name": name,
            "condition_group": args.get("Target Condition Group"),
            "desired_state": args.get("Desired Condition Group State"),
            "source_instruction_index": instruction.get("instruction_index", instruction.get("index")),
        }
    if "World Type" in name:
        return {
            "kind": "world_type",
            "instruction_name": name,
            "world_type": args.get("World Type"),
            "source_instruction_index": instruction.get("instruction_index", instruction.get("index")),
        }
    return {
        "kind": "control_flow_predicate",
        "instruction_name": name,
        "args": instruction.get("args", []),
        "source_instruction_index": instruction.get("instruction_index", instruction.get("index")),
    }


def condition_group_atoms(instructions: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for instruction in instructions:
        name = str(instruction.get("instruction_name") or "")
        if not name.startswith("IF ") or "Condition Group" in name:
            continue
        group = args_map(instruction).get("Result Condition Group")
        if not isinstance(group, int):
            continue
        groups[group].append(
            {
                "source_instruction_index": instruction.get("index"),
                "instruction_name": name,
                "args": instruction.get("args", []),
                "atom": {
                    "kind": "condition_instruction",
                    "result_condition_group": group,
                    "instruction_name": name,
                    "args": instruction.get("args", []),
                    "source_instruction_index": instruction.get("index"),
                },
            }
        )
    return dict(groups)


def path_predicates(path: list[dict[str, Any]], groups: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    predicates = []
    for branch in path:
        name = str(branch.get("instruction_name") or "")
        args = args_map(branch)
        taken = branch.get("taken")
        if taken in {"condition_true", "condition_true_skip"}:
            required = True
        elif taken in {"condition_false", "condition_false_fallthrough"}:
            required = False
        elif taken == "end_if_terminate":
            required = True
        elif taken == "end_if_fallthrough":
            required = False
        else:
            required = None
        predicate = direct_predicate(branch)
        if "Condition Group State" in name:
            group = args.get("Target Condition Group")
            predicate["expanded_group_atoms"] = groups.get(group, [])
        predicates.append(
            {
                "branch_instruction_index": branch.get("instruction_index"),
                "taken": taken,
                "required_truth": required,
                "predicate": predicate,
                "target": branch.get("target"),
            }
        )
    return predicates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--guard-traces", type=Path, required=True)
    parser.add_argument("--event-flags", type=Path, required=True)
    parser.add_argument("--event-flags-dump", type=Path, required=True)
    parser.add_argument("--external-event-flag-index", type=Path, required=False)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    trace_path = args.guard_traces.resolve()
    event_flags_path = args.event_flags.resolve()
    event_flags_dump_path = args.event_flags_dump.resolve()
    external_event_flag_index_path = (
        args.external_event_flag_index.resolve()
        if args.external_event_flag_index
        else None
    )
    traces = json.loads(trace_path.read_text(encoding="utf-8"))
    flags = {
        int(row["ID"]): row
        for row in json.loads(event_flags_path.read_text(encoding="utf-8"))
        if str(row.get("ID", "")).lstrip("-").isdigit()
    }
    documented_flags: dict[int, dict[str, Any]] = {}
    for line in event_flags_dump_path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split(",", 4)
        if len(fields) < 5:
            continue
        try:
            flag_id = int(fields[0].strip())
        except ValueError:
            continue
        documented_flags[flag_id] = {
            "description": fields[4].strip(),
            "tags": [
                "smithbox_event_flag_dump",
                f"category:{fields[1].strip()}",
                f"type:{fields[2].strip()}",
            ],
            "raw_fields": fields[:4],
            "source": str(event_flags_dump_path),
        }
    public_flags = parse_public_event_flag_index(external_event_flag_index_path)
    bindings = []
    atom_count = 0
    path_count = 0
    candidate_flag_ids: set[int] = set()
    local_reference_flag_ids: set[int] = set()
    for event in traces.get("events", []):
        instructions = event.get("instructions", [])
        local_references = event_local_flag_references(instructions)
        local_reference_flag_ids.update(local_references)
        groups = condition_group_atoms(instructions)
        by_target = defaultdict(list)
        for binding in event.get("bindings", []):
            by_target[int(binding["instruction_index"])].append(binding)
        for target in event.get("target_traces", []):
            paths = []
            for raw_path in target.get("paths", []):
                predicates = path_predicates(raw_path.get("branch_trace", []), groups)
                atom_count += len(predicates)
                path_count += 1
                paths.append(
                    {
                        "branch_instruction_indices": raw_path.get("branch_instruction_indices", []),
                        "predicates": predicates,
                    }
                )
            bindings_for_target = by_target.get(int(target["instruction_index"]), [])
            yield_record = {
                "id": f"guard-atoms:{event['map_id']}:{event['event_id']}:{target['instruction_index']}",
                "map_id": event["map_id"],
                "event_id": event["event_id"],
                "target_instruction_index": target["instruction_index"],
                "target_instruction_name": (target.get("instruction") or {}).get("instruction_name"),
                "binding_ids": [binding.get("binding_id") for binding in bindings_for_target],
                "condition_groups": groups,
                "syntactic_path_count_sampled": target.get("syntactic_path_count_sampled", 0),
                "paths": paths,
                "guard_binding_status": "candidate_atoms_only",
                "routeable": False,
                "verification_state": "local_emevd_syntactic_trace",
                "blockers": [
                    "condition_group_runtime_truth_not_solved",
                    "current_save_state_not_bound",
                    "player_space_segment_not_bound",
                ],
            }
            yield_record = enrich_structure(
                yield_record,
                flags,
                documented_flags,
                local_references,
                public_flags,
                candidate_flag_ids,
            )
            bindings.append(yield_record)

    output = {
        "schema": "elden-ring-local-emevd-guard-atoms@1",
        "source": {
            "guard_traces": str(trace_path),
            "guard_traces_sha256": sha256(trace_path),
            "event_flags": str(event_flags_path),
            "event_flags_sha256": sha256(event_flags_path),
            "event_flags_dump": str(event_flags_dump_path),
            "event_flags_dump_sha256": sha256(event_flags_dump_path),
            "external_event_flag_index": (
                str(external_event_flag_index_path)
                if external_event_flag_index_path
                else None
            ),
            "external_event_flag_index_sha256": (
                sha256(external_event_flag_index_path)
                if external_event_flag_index_path
                and external_event_flag_index_path.is_file()
                else None
            ),
        },
        "model": {
            "purpose": "candidate guard predicates for exact transition bindings",
            "condition_semantics": "candidate only; no condition group truth is inferred",
            "routeable": False,
        },
        "status": {
            "guard_atom_records": len(bindings),
            "sampled_path_count": path_count,
            "predicate_candidate_count": atom_count,
            "event_flag_candidate_ids": len(candidate_flag_ids),
            "event_flag_alias_verified": sum(flag_id in flags for flag_id in candidate_flag_ids),
            "event_flag_alias_missing": sum(flag_id not in flags for flag_id in candidate_flag_ids),
            "event_flag_documentation_verified": sum(
                flag_id not in flags and flag_id in documented_flags for flag_id in candidate_flag_ids
            ),
            "event_flag_documentation_missing": sum(
                flag_id not in flags and flag_id not in documented_flags for flag_id in candidate_flag_ids
            ),
            "event_flag_local_reference_verified": sum(
                flag_id in local_reference_flag_ids for flag_id in candidate_flag_ids
            ),
            "event_flag_local_reference_missing": sum(
                flag_id not in local_reference_flag_ids for flag_id in candidate_flag_ids
            ),
            "event_flag_verified_total": sum(
                flag_id in flags or flag_id in documented_flags for flag_id in candidate_flag_ids
            ),
            "event_flag_external_public_verified": sum(
                flag_id in public_flags for flag_id in candidate_flag_ids
            ),
            "event_flag_external_public_missing": sum(
                flag_id not in public_flags for flag_id in candidate_flag_ids
            ),
            "event_flag_any_catalog_verified": sum(
                flag_id in flags or flag_id in documented_flags or flag_id in public_flags
                for flag_id in candidate_flag_ids
            ),
            "routeable_records": 0,
            "all_records_routeable_false": True,
            "all_guard_binding_status_candidate_only": all(
                row["guard_binding_status"] == "candidate_atoms_only" for row in bindings
            ),
        },
        "records": bindings,
        "note": "These predicates are extracted from syntactic branches and condition groups. They are not a current save-state evaluator and do not promote edges.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
