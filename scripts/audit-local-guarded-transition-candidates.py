#!/usr/bin/env python3
"""Audit exact scripted transition to Guard-expression joins."""

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
    assert payload["schema"] == "elden-ring-local-guarded-transition-candidates@1"
    assert status["candidate_count"] == len(records) == 15
    assert status["scripted_entity_warp_count"] == 3
    assert status["scripted_map_warp_count"] == 12
    assert status["guard_expression_linked_count"] == 15
    assert status["guard_expression_missing_count"] == 0
    assert status["guard_path_count"] == 29
    assert status["routeable_records"] == 0
    assert status["all_records_routeable_false"] is True
    assert status["formal_transition_promotion_ready"] is False
    assert all(row.get("guard_status") == "candidate_expression_linked" for row in records)
    assert all(row.get("routeable") is False for row in records)
    print("LOCAL GUARDED TRANSITION CANDIDATE AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
