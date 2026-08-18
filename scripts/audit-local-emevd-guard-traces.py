#!/usr/bin/env python3
"""Audit the conservative EMEVD guard-trace artifact."""

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
    targets = [target for event in payload.get("events", []) for target in event.get("target_traces", [])]
    assert payload["schema"] == "elden-ring-local-emevd-guard-traces@1"
    assert status["transition_binding_count"] == 15
    assert status["event_trace_count"] == status["decoded_event_count"] == 8
    assert status["decode_failures"] == 0
    assert status["targets_with_syntactic_path"] == len(targets) == 15
    assert status["targets_without_syntactic_path"] == 0
    assert status["routeable_records"] == 0
    assert status["all_records_routeable_false"] is True
    assert all(target["guard_resolution_status"] == "syntactic_branch_trace_only" for target in targets)
    print("LOCAL EMEVD GUARD TRACE AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
