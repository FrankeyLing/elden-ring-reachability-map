#!/usr/bin/env python3
"""Normalize the pinned Map For Goblins item-placement index.

The compressed source chunks are copied to an external working snapshot. This
normalizer publishes the source record index, placement coordinates, quantity,
placement type and item signifiers without inventing a route node or changing
the source coordinate system.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import zlib
from collections import Counter
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode(source_dir: Path) -> tuple[dict, list[list], list[dict]]:
    manifest = load(source_dir / "manifest.json")
    files = sorted(
        source_dir.glob("mapforgoblins-item-index-part*.json"),
        key=lambda path: load(path)["part"],
    )
    expected_parts = load(files[0])["parts"] if files else 0
    part_numbers = [load(path)["part"] for path in files]
    if not files or expected_parts != len(files) or part_numbers != list(range(1, expected_parts + 1)):
        raise ValueError("Map For Goblins item-index chunks are incomplete or out of order")
    encoded = "".join(load(path)["chunk"] for path in files)
    rows = json.loads(zlib.decompress(base64.b64decode(encoded)).decode("utf-8"))
    expected_records = next(
        (
            artifact["records"]
            for artifact in manifest.get("artifacts", [])
            if "item-index-part1" in artifact.get("path", "")
        ),
        None,
    )
    if expected_records is not None and len(rows) != expected_records:
        raise ValueError(
            f"Map For Goblins item-index count mismatch: {len(rows)} != {expected_records}"
        )
    return manifest, rows, files


def normalize(source_dir: Path, retrieved_at: str) -> dict:
    manifest, rows, files = decode(source_dir)
    records = []
    placement_types = Counter()
    broad_categories = Counter()
    map_counts = Counter()
    blank_names = 0
    item_occurrences = 0
    for source_index, row in enumerate(rows):
        if len(row) != 8:
            raise ValueError(f"item record {source_index} does not have 8 fields")
        map_name, x, y, z, raw_items, broad, placement_type, is_static = row
        if not isinstance(map_name, str) or not map_name:
            raise ValueError(f"item record {source_index} has no map name")
        if not all(isinstance(value, (int, float)) for value in (x, y, z)):
            raise ValueError(f"item record {source_index} has invalid coordinates")
        if not isinstance(raw_items, list) or not raw_items:
            raise ValueError(f"item record {source_index} has no item signifier")
        items = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                raise ValueError(f"item record {source_index} has an invalid item signifier")
            name = str(raw_item.get("name") or "")
            if not name:
                blank_names += 1
            item_occurrences += 1
            items.append({
                "sourceItemId": raw_item.get("id"),
                "name": name,
                "category": raw_item.get("category"),
                "quantity": raw_item.get("num"),
                "broadCategory": raw_item.get("broad_category"),
                "subCategory": raw_item.get("sub_category"),
            })
            if raw_item.get("broad_category"):
                broad_categories[raw_item["broad_category"]] += 1
        records.append({
            "sourceIndex": source_index,
            "sourceRecordId": f"mapforgoblins-item-{source_index}",
            "map": map_name,
            "coordinateSpace": "game_world_xyz",
            "position": {"x": x, "y": y, "z": z},
            "items": items,
            "broadCategory": broad,
            "placementType": placement_type,
            "isStatic": is_static,
        })
        placement_types[str(placement_type)] += 1
        map_counts[map_name] += 1

    source = manifest.get("source", {})
    return {
        "schema": "errn-mapforgoblins-item-index@1",
        "built_at": retrieved_at,
        "source": {
            "id": source.get("id", "map_for_goblins"),
            "name": source.get("name"),
            "url": source.get("url"),
            "commit": source.get("commit"),
            "license": source.get("license"),
            "licenseFile": source.get("licenseFile"),
            "snapshotDir": str(source_dir),
            "sourceFiles": {
                path.name: sha256(path)
                for path in [source_dir / "manifest.json", *files]
            },
            "policy": "Only exact unique English-name matches to player itemlike entities are promoted to coordinate acquisition relations; source records remain independently auditable.",
        },
        "stats": {
            "recordCount": len(records),
            "itemOccurrenceCount": item_occurrences,
            "blankNameOccurrences": blank_names,
            "placementTypeCounts": dict(sorted(placement_types.items())),
            "broadCategoryCounts": dict(sorted(broad_categories.items())),
            "mapCount": len(map_counts),
        },
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--retrieved-at", default="2026-08-18")
    args = parser.parse_args()
    payload = normalize(args.source_dir, args.retrieved_at)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(payload["stats"], ensure_ascii=False))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
