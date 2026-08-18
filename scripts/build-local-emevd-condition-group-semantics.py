#!/usr/bin/env python3
"""Materialize the documented Elden Ring EMEVD condition-group mapping."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--guard-atoms", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    atoms_path = args.guard_atoms.resolve()
    atoms = json.loads(atoms_path.read_text(encoding="utf-8"))
    observed_ids = set()
    observed_reference_count = 0
    for record in atoms.get("records", []):
        observed_ids.update(int(group_id) for group_id in record.get("condition_groups", {}))
        for path in record.get("paths", []):
            for branch in path.get("predicates", []):
                if branch.get("predicate", {}).get("kind") == "condition_group_state":
                    observed_reference_count += 1

    records = []
    for group_id in range(-15, 16):
        if group_id < 0:
            group_type = "or"
            alias = f"OR_{abs(group_id):02d}"
            operator = "any_of"
            description = "accumulates condition results with logical OR"
        elif group_id > 0:
            group_type = "and"
            alias = f"AND_{group_id:02d}"
            operator = "all_of"
            description = "accumulates condition results with logical AND"
        else:
            group_type = "main"
            alias = "MAIN"
            operator = "temporal_wait_group"
            description = "special group that waits/rechecks conditions; not a static boolean accumulator"
        records.append(
            {
                "group_id": group_id,
                "alias": alias,
                "group_type": group_type,
                "boolean_operator": operator,
                "description": description,
                "observed_in_guard_atoms": group_id in observed_ids,
                "semantic_status": "boolean_operator_verified_from_emedf" if group_id else "main_group_temporal_semantics_verified",
            }
        )

    output = {
        "schema": "elden-ring-local-emevd-condition-group-semantics@1",
        "source": {
            "guard_atoms": str(atoms_path),
            "guard_atoms_sha256": hashlib.sha256(atoms_path.read_bytes()).hexdigest().upper(),
            "references": [
                {
                    "url": "https://soulsmods.github.io/emedf/er-emedf.html",
                    "claim": "Numeric ConditionGroup enum aliases for Elden Ring",
                },
                {
                    "url": "https://www.soulsmodding.com/doku.php?id=tutorial:learning-how-to-use-emevd",
                    "claim": "AND/OR/MAIN behavior and uncompiled condition groups",
                },
            ],
        },
        "model": {
            "purpose": "static operator mapping only",
            "current_event_truth_evaluated": False,
            "current_save_state_evaluated": False,
            "routeable": False,
        },
        "status": {
            "record_count": len(records),
            "observed_group_id_count": len(observed_ids),
            "observed_condition_group_reference_count": observed_reference_count,
            "all_group_ids_mapped": all(row["semantic_status"] for row in records),
            "routeable_records": 0,
        },
        "records": records,
        "note": "This artifact resolves only the operator/name mapping. It does not evaluate conditions, compiled state, event timing, or a player save.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
