#!/usr/bin/env python3
"""Audit the static EMEVD condition-group semantics table."""

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
    records = payload["records"]
    assert payload["schema"] == "elden-ring-local-emevd-condition-group-semantics@1"
    assert status["record_count"] == len(records) == 31
    assert status["observed_group_id_count"] == 15
    assert status["observed_condition_group_reference_count"] == 35
    assert status["all_group_ids_mapped"] is True
    assert status["routeable_records"] == 0
    assert payload["model"]["current_event_truth_evaluated"] is False
    assert payload["model"]["current_save_state_evaluated"] is False
    assert records[0]["alias"] == "OR_15"
    assert records[15]["alias"] == "MAIN"
    assert records[16]["alias"] == "AND_01"
    print("LOCAL EMEVD CONDITION GROUP SEMANTICS AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
