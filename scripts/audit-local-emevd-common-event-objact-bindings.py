#!/usr/bin/env python3
"""Audit strict raw CommonEvent-to-ObjAct target bindings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    status = payload["status"]

    assert payload["schema"] == "elden-ring-local-emevd-common-event-objact-bindings@1"
    assert status["record_count"] == len(records) == 1
    assert status["missing_part_name_candidate_count"] == 46
    assert status["initialize_common_event_call_count"] > 0
    assert status["same_call_objact_identity_match_count"] > 0
    assert status["matching_objact_param_state_row_count"] > 0
    assert status["routeable_records"] == 0
    assert status["all_records_routeable_false"] is True
    assert all(record.get("routeable") is False for record in records)
    assert all(
        record.get("binding_status") == "exact_common_event_objact_entity_param_state_target"
        and record.get("verification_state")
        == "local_raw_emevd_parameter_substitution_and_msbe_exact_part"
        and len(record.get("state_rows", [])) > 0
        and record.get("target_part", {}).get("entity_id", 0) > 0
        for record in records
    )
    assert all(
        record.get("obj_act_part_name") is None
        for record in records
    )
    print("LOCAL EMEVD COMMON-EVENT OBJACT BINDINGS: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
