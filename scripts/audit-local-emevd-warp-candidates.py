#!/usr/bin/env python3
"""Audit map-local EMEVD warp evidence coverage."""

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
    assert payload["schema"] == "elden-ring-local-emevd-warp-candidates@1"
    assert status["warp_reference_count"] == len(records) == 585
    assert status["exact_destination_entity_count"] > 0
    assert status["exact_map_identity_only_count"] > 0
    assert status["exact_destination_entity_count"] == 337
    assert status["exact_runtime_entity_count"] == 14
    assert status["unresolved_destination_count"] == 216
    assert (
        status["exact_destination_entity_count"]
        + status["exact_map_identity_only_count"]
        + status["exact_runtime_entity_count"]
        + status["unresolved_destination_count"]
        == status["record_count"]
    )
    assert status["unresolved_destination_count"] > 0
    assert status["routeable_records"] == 0
    assert status["all_records_routeable_false"] is True
    assert all(row.get("routeable") is False for row in records)
    print("LOCAL EMEVD WARP CANDIDATE AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
