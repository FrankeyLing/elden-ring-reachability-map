#!/usr/bin/env python3
"""Regression checks for entity-record fault isolation."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "data" / "v1" / "entities" / "player-entity-index.json"
sys.path.insert(0, str(ROOT))

from server import sanitize_player_entity_payload


def main() -> int:
    payload = json.loads(INDEX.read_text(encoding="utf-8"))
    original_count = len(payload["entities"])
    original_ids = {entity["id"] for entity in payload["entities"]}

    injected = copy.deepcopy(payload)
    injected["entities"].append({"id": "broken_record", "name": "not-a-name-map"})
    sanitized = sanitize_player_entity_payload(injected)
    assert len(sanitized["entities"]) == original_count
    assert sanitized["stats"]["quarantinedEntityCount"] == 1
    assert {entity["id"] for entity in sanitized["entities"]} == original_ids

    removed_one = copy.deepcopy(payload)
    removed_one["entities"] = [
        entity for entity in removed_one["entities"] if entity["id"] != "item_grave_glovewort_1"
    ]
    still_usable = sanitize_player_entity_payload(removed_one)
    remaining_ids = {entity["id"] for entity in still_usable["entities"]}
    assert "item_grave_glovewort_1" not in remaining_ids
    assert "item_smithing_stone_1" in remaining_ids
    assert still_usable["stats"]["quarantinedEntityCount"] == 0

    print("PASS entity layer isolation")
    print(f"  clean_entities={original_count}")
    print("  malformed_record_quarantined=1")
    print("  unrelated_smithing_stone_survives_missing_glovewort=True")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
