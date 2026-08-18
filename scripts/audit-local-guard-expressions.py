#!/usr/bin/env python3
"""Audit the conservative Guard-expression artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    status = payload["status"]
    records = payload.get("records", [])
    expressions = payload.get("expressions", [])
    assert payload["schema"] == "elden-ring-local-emevd-guard-expressions@1"
    assert payload["source"].get("condition_semantics")
    assert payload["source"].get("condition_semantics_sha256")
    assert status["guard_expression_records"] == len(records) == 15
    assert status["sampled_path_count"] == 29
    assert status["unique_expression_count"] == len(expressions)
    assert status["condition_group_reference_count"] > 0
    assert status["condition_group_boolean_operator_verified"] is True
    reasons = status["unresolved_reason_counts"]
    assert "condition_group_boolean_semantics_unresolved" not in reasons
    assert "world_type_semantics_unresolved" not in reasons
    assert "control_flow_predicate_unresolved" not in reasons
    assert "branch_result_semantics_unresolved" not in reasons
    assert status["routeable_records"] == 0
    assert status["all_records_routeable_false"] is True
    assert status["all_guard_binding_status_candidate_only"] is True
    assert all(record.get("routeable") is False for record in records)
    assert all(record.get("guard_binding_status") == "candidate_expression_only" for record in records)
    for record in records:
        for path in record.get("paths", []):
            assert path["expression"]["kind"] == "all_of"
            assert path["expression"]["routeable"] is False
            assert path["expression"]["semantic_status"] == "syntactic_candidate"
    print("LOCAL GUARD EXPRESSION AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
