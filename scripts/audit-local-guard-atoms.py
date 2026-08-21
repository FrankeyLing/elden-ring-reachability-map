#!/usr/bin/env python3
"""Audit candidate Guard atoms without evaluating game state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def event_flag_catalogs(value):
    if isinstance(value, dict):
        yield from value.get("event_flag_catalog", [])
        for child in value.values():
            yield from event_flag_catalogs(child)
    elif isinstance(value, list):
        for child in value:
            yield from event_flag_catalogs(child)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    status = payload["status"]
    records = payload.get("records", [])
    assert payload["schema"] == "elden-ring-local-emevd-guard-atoms@1"
    assert status["guard_atom_records"] == len(records) == 15
    assert status["sampled_path_count"] == 29
    assert status["predicate_candidate_count"] == 144
    assert status["event_flag_candidate_ids"] == 25
    assert status["event_flag_alias_verified"] == 3
    assert status["event_flag_alias_missing"] == 22
    assert status["event_flag_documentation_verified"] == 10
    assert status["event_flag_documentation_missing"] == 12
    assert status["event_flag_local_reference_verified"] == 25
    assert status["event_flag_local_reference_missing"] == 0
    assert status["event_flag_external_public_verified"] == 11
    assert status["event_flag_external_public_missing"] == 14
    assert status["event_flag_any_catalog_verified"] == 13
    assert status["event_flag_verified_total"] == 13
    assert status["routeable_records"] == 0
    assert status["all_records_routeable_false"] is True
    assert status["all_guard_binding_status_candidate_only"] is True
    assert all(row.get("guard_binding_status") == "candidate_atoms_only" for row in records)
    assert all(row.get("routeable") is False for row in records)
    catalogs = list(event_flag_catalogs(records))
    assert catalogs
    assert all(
        row.get("local_emevd_reference_status") == "exact_event_instruction_reference"
        for row in catalogs
    )
    assert all(
        row.get("external_public_event_flag_status")
        in {"exact_public_index_reference", "not_found_in_pinned_public_index"}
        for row in catalogs
    )
    print("LOCAL GUARD ATOM AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
