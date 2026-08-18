#!/usr/bin/env python3
"""Join exact scripted transition bindings to conservative Guard expressions.

The join is by the exact transition binding ID emitted by the local transition
audit.  It never uses proximity, names, or guessed event ordering, and it
never promotes a candidate to a routeable edge.
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transition-audit", type=Path, required=True)
    parser.add_argument("--guard-expressions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    transition_path = args.transition_audit.resolve()
    expression_path = args.guard_expressions.resolve()
    transitions = json.loads(transition_path.read_text(encoding="utf-8"))
    expressions = json.loads(expression_path.read_text(encoding="utf-8"))

    by_binding_id: dict[str, dict[str, Any]] = {}
    for record in expressions.get("records", []):
        for binding_id in record.get("binding_ids", []):
            by_binding_id[str(binding_id)] = record

    candidates = []
    linked_count = 0
    missing_count = 0
    for collection_name, transition_kind in (
        ("scripted_warp_bindings", "scripted_warp"),
        ("scripted_map_warp_bindings", "scripted_map_warp"),
    ):
        for transition in transitions.get(collection_name, []):
            transition_id = str(transition.get("id"))
            guard_record = by_binding_id.get(transition_id)
            if guard_record is None:
                missing_count += 1
                guard_status = "exact_transition_without_guard_expression_binding"
                expression_refs = []
                unresolved_reasons = ["guard_expression_binding_missing"]
            else:
                linked_count += 1
                guard_status = "candidate_expression_linked"
                expression_refs = [
                    {
                        "record_id": guard_record.get("id"),
                        "map_id": guard_record.get("map_id"),
                        "event_id": guard_record.get("event_id"),
                        "target_instruction_index": guard_record.get("target_instruction_index"),
                        "target_instruction_name": guard_record.get("target_instruction_name"),
                        "paths": [
                            {
                                "path_index": path.get("path_index"),
                                "expression_id": path.get("expression_id"),
                                "expression": path.get("expression"),
                            }
                            for path in guard_record.get("paths", [])
                        ],
                    }
                ]
                unresolved_reasons = sorted(
                    {
                        reason
                        for path in guard_record.get("paths", [])
                        for reason in path.get("expression", {}).get("unresolved_reasons", [])
                    }
                )
            candidates.append(
                {
                    "id": f"guarded-transition:{transition_id}",
                    "transition_kind": transition_kind,
                    "transition_binding_id": transition_id,
                    "from": transition.get("from"),
                    "to": transition.get("to"),
                    "emevd_reference": transition.get("emevd_reference"),
                    "guard_status": guard_status,
                    "guard_expression_refs": expression_refs,
                    "unresolved_reasons": unresolved_reasons,
                    "routeable": False,
                    "verification_state": "exact_local_transition_plus_syntactic_guard_candidate",
                }
            )

    output = {
        "schema": "elden-ring-local-guarded-transition-candidates@1",
        "source": {
            "transition_audit": str(transition_path),
            "transition_audit_sha256": sha256(transition_path),
            "guard_expressions": str(expression_path),
            "guard_expressions_sha256": sha256(expression_path),
        },
        "model": {
            "purpose": "exact scripted transition evidence joined to conservative guard candidates",
            "join_key": "transition_binding_id == guard_expression.binding_ids[]",
            "routeable": False,
        },
        "status": {
            "candidate_count": len(candidates),
            "scripted_entity_warp_count": sum(row["transition_kind"] == "scripted_warp" for row in candidates),
            "scripted_map_warp_count": sum(row["transition_kind"] == "scripted_map_warp" for row in candidates),
            "guard_expression_linked_count": linked_count,
            "guard_expression_missing_count": missing_count,
            "guard_path_count": sum(
                len(ref.get("paths", []))
                for row in candidates
                for ref in row.get("guard_expression_refs", [])
            ),
            "routeable_records": 0,
            "all_records_routeable_false": all(row["routeable"] is False for row in candidates),
            "formal_transition_promotion_ready": False,
        },
        "records": candidates,
        "note": "These are exact local scripted transition bindings with syntactic guard candidates. They are not a current-save-state evaluator, continuous player route, or promoted navigable edge.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
