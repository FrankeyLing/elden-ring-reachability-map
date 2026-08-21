#!/usr/bin/env python3
"""Compile conservative logical-expression candidates from Guard atoms.

This pass makes the syntactic branch evidence queryable as an expression tree.
It deliberately does not solve EMEVD condition-group boolean semantics, save
state, or player-space reachability.  A generated expression is therefore a
candidate guard, never a promoted route edge.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def integer_key(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_group_atom(atom_row: dict[str, Any]) -> dict[str, Any]:
    atom = atom_row.get("atom", atom_row)
    return {
        "kind": "condition_instruction",
        "instruction_name": atom.get("instruction_name"),
        "result_condition_group": atom.get("result_condition_group"),
        "source_instruction_index": atom.get("source_instruction_index"),
        "args": atom.get("args", []),
        "event_flag_catalog": atom_row.get("event_flag_catalog", []),
    }


def condition_group_semantics(group_id: Any, semantic_by_id: dict[int, dict[str, Any]] | None = None) -> dict[str, Any]:
    try:
        numeric_id = int(group_id)
    except (TypeError, ValueError):
        return {
            "group_type": "unknown",
            "group_alias": None,
            "boolean_operator": "unresolved",
            "semantic_status": "condition_group_id_not_numeric",
        }
    if semantic_by_id and numeric_id in semantic_by_id:
        row = semantic_by_id[numeric_id]
        return {
            "group_type": row.get("group_type"),
            "group_alias": row.get("alias"),
            "boolean_operator": row.get("boolean_operator"),
            "semantic_status": row.get("semantic_status"),
        }
    if numeric_id == 0:
        return {
            "group_type": "main",
            "group_alias": "MAIN",
            "boolean_operator": "temporal_wait_group",
            "semantic_status": "main_group_operator_is_temporal",
        }
    if numeric_id > 0:
        return {
            "group_type": "and",
            "group_alias": f"AND_{numeric_id:02d}",
            "boolean_operator": "all_of",
            "semantic_status": "boolean_operator_verified_from_emedf",
        }
    return {
        "group_type": "or",
        "group_alias": f"OR_{abs(numeric_id):02d}",
        "boolean_operator": "any_of",
        "semantic_status": "boolean_operator_verified_from_emedf",
    }


def group_reference(
    group_id: Any,
    group_rows: list[dict[str, Any]],
    semantic_by_id: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    semantics = condition_group_semantics(group_id, semantic_by_id)
    return {
        "kind": "condition_group_reference",
        "group_id": group_id,
        **semantics,
        "atoms": [normalize_group_atom(row) for row in group_rows],
        "runtime_truth_status": "unresolved_current_event_state",
    }


def branch_test(
    predicate: dict[str, Any],
    semantic_by_id: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    kind = predicate.get("kind")
    if kind == "event_flag":
        return {
            "kind": "event_flag_test",
            "instruction_name": predicate.get("instruction_name"),
            "flag_id": predicate.get("flag_id"),
            "desired_state": predicate.get("desired_state"),
            "event_flag_catalog": predicate.get("event_flag_catalog", []),
            "source_instruction_index": predicate.get("source_instruction_index"),
        }
    if kind == "condition_group_state":
        return {
            "kind": "condition_group_test",
            "instruction_name": predicate.get("instruction_name"),
            "condition_group": predicate.get("condition_group"),
            "desired_state": predicate.get("desired_state"),
            "group": group_reference(
                predicate.get("condition_group"),
                predicate.get("expanded_group_atoms", []),
                semantic_by_id,
            ),
            "source_instruction_index": predicate.get("source_instruction_index"),
        }
    if kind == "world_type":
        world_type = predicate.get("world_type")
        return {
            "kind": "world_type_test",
            "instruction_name": predicate.get("instruction_name"),
            "world_type": world_type,
            "world_type_alias": {0: "OwnWorld", 1: "OtherWorld"}.get(world_type),
            "source_instruction_index": predicate.get("source_instruction_index"),
            "semantic_status": "world_type_value_mapping_verified_from_emedf",
            "runtime_status": "current_multiplayer_world_state_unresolved",
        }
    return {
        "kind": "unresolved_control_flow_test",
        "instruction_name": predicate.get("instruction_name"),
        "args": predicate.get("args", []),
        "source_instruction_index": predicate.get("source_instruction_index"),
        "semantic_status": "control_flow_predicate_unresolved",
    }


def compile_branch(
    branch: dict[str, Any],
    semantic_by_id: dict[int, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], set[str]]:
    predicate = branch.get("predicate", {})
    required_truth = branch.get("required_truth")
    reasons: set[str] = set()
    if predicate.get("kind") == "condition_group_state":
        reasons.add("condition_group_runtime_state_unresolved")
    if predicate.get("kind") == "world_type":
        reasons.add("world_type_runtime_state_unresolved")
    if predicate.get("kind") == "control_flow_predicate":
        if branch.get("taken") in {"unconditional_skip", "label"}:
            requirement_status = "deterministic_cfg_edge"
        else:
            reasons.add("control_flow_predicate_unresolved")
            requirement_status = "candidate_only"
    else:
        requirement_status = "candidate_only"
    if required_truth is None and requirement_status != "deterministic_cfg_edge":
        reasons.add("branch_result_semantics_unresolved")
    test = branch_test(predicate, semantic_by_id)
    if requirement_status == "deterministic_cfg_edge":
        test = {
            "kind": "deterministic_cfg_edge",
            "instruction_name": predicate.get("instruction_name"),
            "branch_outcome": branch.get("taken"),
            "source_instruction_index": predicate.get("source_instruction_index"),
            "semantic_status": "deterministic_cfg_edge",
        }
    return (
        {
            "kind": "branch_requirement",
            "branch_instruction_index": branch.get("branch_instruction_index"),
            "instruction_name": predicate.get("instruction_name"),
            "branch_outcome": branch.get("taken"),
            "required_truth": required_truth,
            "test": test,
            "target": branch.get("target"),
            "semantic_status": requirement_status,
        },
        reasons,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--guard-atoms", type=Path, required=True)
    parser.add_argument("--condition-semantics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = args.guard_atoms.resolve()
    semantics_source = args.condition_semantics.resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    semantics_payload = json.loads(semantics_source.read_text(encoding="utf-8"))
    semantic_by_id = {
        int(row["group_id"]): row for row in semantics_payload.get("records", [])
    }
    records = []
    unique_expressions: dict[str, dict[str, Any]] = {}
    sampled_path_count = 0
    group_reference_count = 0
    unresolved_reason_counts: dict[str, int] = {}

    for record in payload.get("records", []):
        group_definitions = []
        for group_key, group_rows in record.get("condition_groups", {}).items():
            group_id = integer_key(group_key)
            if group_id is None:
                group_id = group_key
            group_definitions.append(
                {
                    "group_id": group_id,
                    "atom_count": len(group_rows),
                    "expression": group_reference(group_id, group_rows, semantic_by_id),
                }
            )

        paths = []
        for path_index, path in enumerate(record.get("paths", [])):
            sampled_path_count += 1
            requirements = []
            reasons = {"syntactic_cfg_path_only"}
            for branch in path.get("predicates", []):
                requirement, branch_reasons = compile_branch(branch, semantic_by_id)
                requirements.append(requirement)
                reasons.update(branch_reasons)
                if requirement["test"]["kind"] == "condition_group_test":
                    group_reference_count += 1
            reasons.update({"current_save_state_unbound", "player_space_segment_unbound"})
            for reason in reasons:
                unresolved_reason_counts[reason] = unresolved_reason_counts.get(reason, 0) + 1
            expression = {
                "kind": "all_of",
                "requirements": requirements,
                "semantic_status": "syntactic_candidate",
                "unresolved_reasons": sorted(reasons),
                "routeable": False,
            }
            expression_key = canonical(expression)
            expression_id = "guard-expression:" + hashlib.sha256(expression_key.encode("utf-8")).hexdigest()[:16]
            unique_expressions.setdefault(
                expression_id,
                {
                    "expression_id": expression_id,
                    "expression": expression,
                    "occurrence_count": 0,
                },
            )
            unique_expressions[expression_id]["occurrence_count"] += 1
            paths.append(
                {
                    "path_index": path_index,
                    "branch_instruction_indices": path.get("branch_instruction_indices", []),
                    "expression_id": expression_id,
                    "expression": expression,
                }
            )

        records.append(
            {
                "id": record.get("id"),
                "map_id": record.get("map_id"),
                "event_id": record.get("event_id"),
                "target_instruction_index": record.get("target_instruction_index"),
                "target_instruction_name": record.get("target_instruction_name"),
                "binding_ids": record.get("binding_ids", []),
                "condition_group_definitions": group_definitions,
                "paths": paths,
                "guard_binding_status": "candidate_expression_only",
                "routeable": False,
                "verification_state": "local_emevd_syntactic_trace",
            }
        )

    output = {
        "schema": "elden-ring-local-emevd-guard-expressions@1",
        "source": {
            "guard_atoms": str(source),
            "guard_atoms_sha256": sha256(source),
            "condition_semantics": str(semantics_source),
            "condition_semantics_sha256": sha256(semantics_source),
        },
        "model": {
            "purpose": "conservative candidate expressions for exact transition guards",
            "path_operator": "ordered_all_of_of_syntactic_branch_requirements",
            "condition_group_operator": "verified: positive=AND, negative=OR, zero=MAIN temporal group",
            "condition_group_runtime_truth": "unresolved",
            "world_type_value_mapping": {"0": "OwnWorld", "1": "OtherWorld"},
            "routeable": False,
            "semantic_references": [
                {
                    "url": "https://soulsmods.github.io/emedf/er-emedf.html",
                    "claim": "ConditionGroup numeric aliases: OR=-1..-15, MAIN=0, AND=1..15",
                },
                {
                    "url": "https://www.soulsmodding.com/doku.php?id=tutorial:learning-how-to-use-emevd",
                    "claim": "AND requires every check, OR requires any check, and uncompiled groups can be checked outside MAIN",
                },
                {
                    "url": "https://soulsmods.github.io/emedf/er-emedf.html",
                    "claim": "WorldType.OwnWorld=0 and WorldType.OtherWorld=1",
                },
            ],
        },
        "status": {
            "guard_expression_records": len(records),
            "sampled_path_count": sampled_path_count,
            "unique_expression_count": len(unique_expressions),
            "condition_group_reference_count": group_reference_count,
            "condition_group_boolean_operator_verified": all(
                group.get("expression", {}).get("semantic_status")
                in {"boolean_operator_verified_from_emedf", "main_group_temporal_semantics_verified"}
                for record in records
                for group in record.get("condition_group_definitions", [])
            ),
            "unresolved_reason_counts": dict(sorted(unresolved_reason_counts.items())),
            "routeable_records": 0,
            "all_records_routeable_false": all(record["routeable"] is False for record in records),
            "all_guard_binding_status_candidate_only": all(
                record["guard_binding_status"] == "candidate_expression_only" for record in records
            ),
        },
        "expressions": list(unique_expressions.values()),
        "records": records,
        "note": "Expressions preserve branch and condition-group evidence but do not evaluate boolean semantics, save state, player-space segments, or routeability.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
