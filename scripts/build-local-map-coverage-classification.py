#!/usr/bin/env python3
"""Build a conservative evidence index for every local MSBE map.

This is a coverage/classification artifact, not a playability classifier.  It
keeps maps without NVA in the final inventory and describes exactly which
static MSBE/NVA signals are present.  No suffix, map-id pattern, or absence of
NVA is interpreted as playable, cutscene, unused, or duplicate.
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


EVENT_SIGNAL_FIELDS = (
    "regions",
    "events",
    "objact_events",
    "transport_events",
    "connection_regions",
    "play_area_regions",
)


def section_count(section_counts: dict[str, Any], key: str) -> int:
    value = section_counts.get(key, 0)
    if isinstance(value, dict):
        value = value.get("count", 0)
    return int(value or 0)


def classify(capabilities: dict[str, Any], nva_record: dict[str, Any] | None) -> tuple[str, str]:
    if nva_record is not None:
        section_counts = nva_record.get("nva", {}).get("section_counts", {})
        navmesh_count = section_count(section_counts, "0")
        if navmesh_count > 0:
            return "native_nva_navmesh_backed", "exact_nva_navmesh_present"
        return "native_nva_present_without_navmesh", "exact_nva_present_navmesh_section_empty"

    if any(int(capabilities.get(field, 0) or 0) > 0 for field in EVENT_SIGNAL_FIELDS):
        return "nva_missing_msbe_event_or_region_signal", "msbe_signal_without_nva"

    static_signal = sum(
        int(capabilities.get(field, 0) or 0)
        for field in ("models", "parts", "collision_parts", "map_piece_parts")
    )
    if static_signal > 0:
        return "nva_missing_msbe_static_signal_only", "msbe_static_signal_without_nva"
    return "nva_missing_no_msbe_playability_signal", "no_nva_or_msbe_playability_signal"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--nva", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    coverage_path = args.coverage.resolve()
    nva_path = args.nva.resolve()
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    nva = json.loads(nva_path.read_text(encoding="utf-8"))
    nva_by_map = {record.get("map_id"): record for record in nva.get("records", [])}

    records: list[dict[str, Any]] = []
    for coverage_record in sorted(coverage.get("missing_maps", []) + [
        {
            "map_id": record.get("map_id"),
            "source_file": record.get("source_file"),
            "source_entry": record.get("source_entry"),
            "capabilities": {},
            "native_nva_status": "present_in_nva_inventory",
        }
        for record in nva.get("records", [])
        if record.get("map_id") not in {item.get("map_id") for item in coverage.get("missing_maps", [])}
    ], key=lambda row: str(row.get("map_id") or "")):
        map_id = coverage_record.get("map_id")
        nva_record = nva_by_map.get(map_id)
        capabilities = dict(coverage_record.get("capabilities") or {})
        if nva_record is not None:
            section_counts = nva_record.get("nva", {}).get("section_counts", {})
            capabilities = {
                **capabilities,
                "nva_navmesh_count": section_count(section_counts, "0"),
                "nva_connector_count": section_count(section_counts, "4"),
                "nva_navmesh_connection_count": section_count(section_counts, "5"),
                "nva_gate_node_count": section_count(section_counts, "8"),
            }
        classification, basis = classify(capabilities, nva_record)
        records.append(
            {
                "map_id": map_id,
                "source_file": coverage_record.get("source_file")
                or f"maps/{map_id}.json",
                "source_entry": coverage_record.get("source_entry"),
                "capabilities": capabilities,
                "native_nva_present": nva_record is not None,
                "native_nva_source_file": nva_record.get("source_file") if nva_record else None,
                "native_nva_source_sha256": nva_record.get("source_sha256") if nva_record else None,
                "evidence_classification": classification,
                "classification_basis": basis,
                "playability_classification": "requires_independent_evidence",
                "floor_semantics": "unresolved",
                "routeable": False,
            }
        )

    classifications: dict[str, int] = {}
    for record in records:
        key = record["evidence_classification"]
        classifications[key] = classifications.get(key, 0) + 1
    status = {
        "map_count": len(records),
        "nva_present_map_count": sum(record["native_nva_present"] for record in records),
        "nva_missing_map_count": sum(not record["native_nva_present"] for record in records),
        "classification_counts": dict(sorted(classifications.items())),
        "all_playability_unresolved": all(
            record["playability_classification"] == "requires_independent_evidence"
            for record in records
        ),
        "all_floor_semantics_unresolved": all(
            record["floor_semantics"] == "unresolved" for record in records
        ),
        "routeable_records": 0,
        "all_records_routeable_false": all(record["routeable"] is False for record in records),
    }
    output = {
        "schema": "elden-ring-local-map-coverage-classification@1",
        "source": {
            "coverage": str(coverage_path),
            "coverage_sha256": sha256(coverage_path),
            "nva": str(nva_path),
            "nva_sha256": sha256(nva_path),
        },
        "model": {
            "purpose": "complete local MSBE map inventory with conservative native coverage evidence",
            "not_a_playability_classifier": True,
            "not_a_floor_semantics_classifier": True,
            "missing_nva_is_not_interpreted": True,
            "routeable": False,
        },
        "status": status,
        "records": records,
        "note": "Every map remains in the inventory. A map without NVA is not marked playable, cutscene, unused, duplicate, or empty; those meanings require independent evidence.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
