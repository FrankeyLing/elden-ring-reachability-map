#!/usr/bin/env python3
"""Audit the native HKX2 hkaiNavMesh geometry evidence index."""

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
    errors = payload.get("errors", [])

    assert payload["schema"] == "elden-ring-local-nvmhktbnd-hkx2-geometry-index@1"
    assert status["nvmhktbnd_file_count"] == status["parsed_binder_count"] == len(records) == 997
    assert status["parse_error_count"] == len(errors) == 0
    assert status["navmesh_hkx_entry_count"] == 3390
    assert status["face_count"] == 6888218
    assert status["edge_count"] == 29901878
    assert status["vertex_count"] == 16607263
    assert status["routeable_records"] == 0
    assert status["geometry_deserialized"] is True
    assert status["player_walkability_validated"] is False
    assert status["all_records_routeable_false"] is True
    assert payload["model"]["geometry_deserialized"] is True
    assert payload["model"]["player_walkability_validated"] is False
    assert payload["model"]["routeable"] is False

    total_entries = total_faces = total_edges = total_vertices = 0
    for record in records:
        entries = record["NavmeshEntries"]
        assert record["Bnd4FileCount"] > 0
        assert record["SourceSize"] > 0
        assert record["status"] if "status" in record else True
        for entry in entries:
            assert entry["Faces"] >= 0
            assert entry["Edges"] >= 0
            assert entry["Vertices"] >= 0
            assert entry["BoundaryEdges"] + entry["InternalOppositeEdges"] <= entry["Edges"]
        total_entries += len(entries)
        total_faces += sum(entry["Faces"] for entry in entries)
        total_edges += sum(entry["Edges"] for entry in entries)
        total_vertices += sum(entry["Vertices"] for entry in entries)

    assert total_entries == status["navmesh_hkx_entry_count"]
    assert total_faces == status["face_count"]
    assert total_edges == status["edge_count"]
    assert total_vertices == status["vertex_count"]
    print("LOCAL NVMHKT HKX2 GEOMETRY AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
