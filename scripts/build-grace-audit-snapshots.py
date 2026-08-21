"""Build the ignored grace-coordinate snapshots used by the online audit.

The product repository keeps source snapshots outside version control.  This
builder turns two pinned, read-only public inputs into the small audit inputs:

* the 413 grace markers already normalized in ``online-map-markers.json``;
* the generated Compass marker source, deduplicated by its game entity ID.

The output is deliberately not a route graph.  It is coordinate evidence with
explicit source identity, candidate formal-node bindings, and unbound records.
Run this before ``audit-online-coverage.py`` when a fresh workspace has no
ignored source snapshots.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ONLINE_MARKERS = ROOT / "data" / "v1" / "entities" / "online-map-markers.json"
DEFAULT_GRAPH = ROOT / "data" / "v1" / "graph.json"
DEFAULT_BINDINGS = ROOT / "data" / "v1" / "entities" / "named-grace-identity-bindings.json"
DEFAULT_COMPASS_SOURCE = (
    ROOT.parent.parent
    / "local-snapshots"
    / "online-elden-ring-compass-20260818-markers.ts"
)
DEFAULT_OUTPUT = ROOT / "data" / "v1" / "source-snapshots"

PROJECTED_SOURCE_URL = "https://raw.githubusercontent.com/jw-ofs/elden-ring-map/main/markers.js"
COMPASS_SOURCE_URL = (
    "https://raw.githubusercontent.com/EthanShoeDev/elden-ring-compass/main/"
    "packages/data/src/generated/markers.ts"
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_compass_markers(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    marker_start = text.find("export const MAP_MARKERS")
    if marker_start < 0:
        raise ValueError(f"Compass source has no MAP_MARKERS export: {path}")
    body = text[marker_start:]
    body = body[body.find("=") + 1 :].strip().rstrip(";").rstrip()
    body = re.sub(r",\s*]$", "]", body)
    rows = json.loads(body)
    if not isinstance(rows, list):
        raise ValueError(f"Compass MAP_MARKERS is not an array: {path}")
    grace_rows = [row for row in rows if row.get("category") == "grace"]
    by_entity_id: dict[int, dict] = {}
    for row in grace_rows:
        entity_id = int(row["entityId"])
        by_entity_id.setdefault(entity_id, row)
    return list(by_entity_id.values())


def master_for_map(map_id: str) -> str:
    prefix = map_id[:3]
    if prefix == "m12":
        return "M01"
    if prefix in {"m20", "m21", "m22", "m25", "m28", "m40", "m41", "m42", "m43", "m61"}:
        return "M10"
    return "M00"


def write_snapshot(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def split_records(records: list[dict], sizes: list[int]) -> list[list[dict]]:
    if sum(sizes) != len(records):
        raise ValueError(f"split sizes {sizes} do not sum to {len(records)} records")
    parts: list[list[dict]] = []
    cursor = 0
    for size in sizes:
        parts.append(records[cursor : cursor + size])
        cursor += size
    return parts


def build_projected_snapshots(online_markers: dict, graph: dict, output: Path) -> dict:
    formal_by_label = {
        node.get("label"): node["id"]
        for node in graph.get("nodes", [])
        if node.get("kind") == "grace" and node.get("label")
    }
    grace_markers = [marker for marker in online_markers.get("markers", []) if marker.get("category") == "grace"]
    records = [
        {
            "source_id": marker["id"],
            "name": marker["name"],
            "master": marker["master"],
            "position": [marker["pixel"]["x"], marker["pixel"]["y"]],
            "formal_id": formal_by_label.get(marker["name"]),
        }
        for marker in grace_markers
    ]
    parts = split_records(records, [111, 75, 75, 75, 75, 2])
    snapshots = ["elden-ring-map-markers-20260818"] + [
        f"elden-ring-map-markers-supplement-{part:02d}-20260818" for part in range(1, 6)
    ]
    for snapshot, part_records in zip(snapshots, parts):
        write_snapshot(
            output / f"{snapshot}.json",
            {
                "schema": "elden-ring-reachability-map/projected-anchor-snapshot@1",
                "snapshot": snapshot,
                "source": {
                    "url": PROJECTED_SOURCE_URL,
                    "retrieved_at": "2026-08-18",
                    "input_snapshot": "data/v1/entities/online-map-markers.json",
                    "policy": "Coordinate-only projection; it never creates traversal edges.",
                },
                "coordinate_space": {
                    "id": "master_tile_pixel",
                    "width": 10496,
                    "height": 10496,
                    "origin": "top_left",
                },
                "records": part_records,
            },
        )
    return {
        "record_count": len(records),
        "part_record_counts": [len(part) for part in parts],
        "exact_formal_bindings": sum(bool(record["formal_id"]) for record in records),
        "unbound_source_markers": sum(not record["formal_id"] for record in records),
    }


def build_named_snapshots(
    compass_rows: list[dict],
    online_markers: dict,
    graph: dict,
    bindings: dict,
    output: Path,
) -> dict:
    formal_by_label: dict[str, list[str]] = {}
    for node in graph.get("nodes", []):
        if node.get("kind") == "grace" and node.get("label"):
            formal_by_label.setdefault(node["label"], []).append(node["id"])

    online_graces = [marker for marker in online_markers.get("markers", []) if marker.get("category") == "grace"]
    marker_by_name_master = {
        (marker["name"], marker["master"]): marker
        for marker in online_graces
    }
    binding_records = bindings.get("records", [])
    binding_by_name_map = {(record["name"], record["map"]): record for record in binding_records}
    used_flag_ids: set[int] = set()
    records: list[dict] = []

    for row in compass_rows:
        name = row["displayName"]
        map_id = row["mapId"]
        binding = binding_by_name_map.get((name, map_id))
        marker = marker_by_name_master.get((name, master_for_map(map_id)))
        if binding:
            flag_id = int(binding["flag_id"])
            region = binding["region"]
        elif marker and int(marker["id"][1:]) not in used_flag_ids:
            flag_id = int(marker["id"][1:])
            region = marker.get("description") or ""
        else:
            # The public sources do not expose a stable flag ID for every
            # duplicate/alias record.  Keep an explicit deterministic source
            # identity instead of collapsing the coordinate record.
            flag_id = 900000000 + int(row["entityId"])
            region = marker.get("description") if marker else ""
        while flag_id in used_flag_ids:
            flag_id += 1
        used_flag_ids.add(flag_id)
        candidates = list(formal_by_label.get(name, []))
        records.append(
            {
                "flag_id": flag_id,
                "name": name,
                "region": region,
                "map": map_id,
                "position": [row["x"], row["y"], row["z"]],
                "bonfire_entity_id": int(row["entityId"]),
                "formal_candidates": candidates,
                "source_identity": {
                    "map_id": map_id,
                    "entity_id": int(row["entityId"]),
                    "instance_kind": row.get("kind"),
                },
            }
        )

    parts = split_records(records, [84, 84, 84, 84, 83])
    for part, part_records in enumerate(parts, start=1):
        snapshot = f"elden-ring-compass-graces-{part:02d}-20260818"
        write_snapshot(
            output / f"{snapshot}.json",
            {
                "schema": "elden-ring-reachability-map/named-grace-coordinate-snapshot@1",
                "snapshot": snapshot,
                "source": {
                    "url": COMPASS_SOURCE_URL,
                    "retrieved_at": "2026-08-18",
                    "input_snapshot": str(DEFAULT_COMPASS_SOURCE),
                    "policy": "Game-local XYZ coordinate evidence; it never creates traversal edges.",
                },
                "coordinate_space": {"id": "source_map_local_xyz"},
                "records": part_records,
            },
        )
    return {
        "record_count": len(records),
        "part_record_counts": [len(part) for part in parts],
        "raw_formal_candidate_count": sum(bool(record["formal_candidates"]) for record in records),
        "identity_binding_count": len(binding_records),
        "formal_candidate_count_after_audit_bindings": sum(
            bool(record["formal_candidates"])
            or (record["name"], record["map"]) in binding_by_name_map
            for record in records
        ),
        "unbound_source_records_before_audit_bindings": sum(
            not record["formal_candidates"] for record in records
        ),
        "unbound_source_records_after_audit_bindings": sum(
            not record["formal_candidates"]
            and (record["name"], record["map"]) not in binding_by_name_map
            for record in records
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--online-markers", type=Path, default=DEFAULT_ONLINE_MARKERS)
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--bindings", type=Path, default=DEFAULT_BINDINGS)
    parser.add_argument("--compass-source", type=Path, default=DEFAULT_COMPASS_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    online_markers = read_json(args.online_markers)
    graph = read_json(args.graph)
    bindings = read_json(args.bindings)
    compass_rows = parse_compass_markers(args.compass_source)
    projected = build_projected_snapshots(online_markers, graph, args.output)
    named = build_named_snapshots(compass_rows, online_markers, graph, bindings, args.output)
    print(json.dumps({"projected": projected, "named": named}, ensure_ascii=False))


if __name__ == "__main__":
    main()
