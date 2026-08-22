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


def normalize_raw_items_database(
    raw_path: Path,
    retrieved_at: str,
    source_profile: str,
    local_game_snapshot: str | None,
    gathering_nodes_path: Path | None = None,
    gathering_mappings_paths: list[Path] | None = None,
) -> dict:
    """Normalize MapForGoblins' profile-scoped extracted item database.

    The public compressed chunks are not profile-labelled and the pinned
    repository defaults to the Elden Ring Reforged profile.  A raw database
    produced by the vanilla profile is therefore accepted only when the
    caller labels it explicitly.  Native part names are retained as
    endpoint-local evidence; they do not create navigation edges.
    """
    if source_profile != "vanilla":
        raise ValueError("raw item database requires --source-profile vanilla")
    raw = load(raw_path)
    if not isinstance(raw, list):
        raise ValueError("raw item database must be a JSON array")

    records = []
    placement_types = Counter()
    broad_categories = Counter()
    map_counts = Counter()
    item_occurrences = 0
    blank_names = 0
    for source_index, row in enumerate(raw):
        if not isinstance(row, dict):
            raise ValueError(f"raw item record {source_index} is not an object")
        map_name = row.get("map")
        position = {key: row.get(key) for key in ("x", "y", "z")}
        if not isinstance(map_name, str) or not map_name:
            raise ValueError(f"raw item record {source_index} has no map name")
        if any(not isinstance(value, (int, float)) for value in position.values()):
            raise ValueError(f"raw item record {source_index} has invalid coordinates")
        raw_items = row.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise ValueError(f"raw item record {source_index} has no item signifier")
        items = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                raise ValueError(f"raw item occurrence {source_index} is not an object")
            name = str(raw_item.get("name") or "")
            blank_names += not bool(name)
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
        record = {
            "sourceIndex": source_index,
            "sourceRecordId": f"mapforgoblins-item-{source_index}",
            "map": map_name,
            "coordinateSpace": "game_world_xyz",
            "position": position,
            "part": row.get("partName"),
            "items": items,
            "broadCategory": row.get("primary_category"),
            "placementType": row.get("source"),
            "isStatic": row.get("guaranteed"),
            "itemLotId": row.get("itemLotId"),
            "eventFlag": row.get("eventFlag"),
            "enemyModel": row.get("enemyModel"),
            "npcParamId": row.get("npcParamId"),
            "defeatFlag": row.get("defeatFlag"),
            "emevdEventId": row.get("emevdEventId"),
            "partBucket": row.get("partBucket"),
        }
        records.append(record)
        placement_types[str(row.get("source"))] += 1
        map_counts[map_name] += 1

    # MapForGoblins' item database contains treasure, enemy, shop, and event
    # placements, but gathering nodes are published by the same pinned source
    # as separate mapping artifacts.  Join those artifacts by the native
    # model name.  This is still an acquisition endpoint only: it does not
    # infer a route edge or a collision relationship.
    gathering_source = {}
    if gathering_nodes_path or gathering_mappings_paths:
        if not gathering_nodes_path or not gathering_mappings_paths:
            raise ValueError(
                "--gathering-nodes and --gathering-mappings must be supplied together"
            )
        mappings = {}
        for mapping_path in gathering_mappings_paths:
            mapping_rows = load(mapping_path)
            if not isinstance(mapping_rows, list):
                raise ValueError(f"gathering mapping must be a JSON array: {mapping_path}")
            for mapping in mapping_rows:
                model = mapping.get("model")
                if not model:
                    continue
                if model in mappings:
                    raise ValueError(f"duplicate gathering model mapping: {model}")
                mappings[model] = mapping
        nodes = load(gathering_nodes_path)
        if not isinstance(nodes, list):
            raise ValueError("gathering nodes must be a JSON array")
        gathering_count = 0
        for node_index, node in enumerate(nodes):
            if not isinstance(node, dict):
                raise ValueError(f"gathering node {node_index} is not an object")
            mapping = mappings.get(node.get("model"))
            if not mapping:
                continue
            mapped_items = [
                item for item in mapping.get("items", [])
                if isinstance(item, dict) and item.get("name") not in (None, "", "???")
            ]
            if not mapped_items:
                continue
            map_name = node.get("map")
            position = {key: node.get(key) for key in ("x", "y", "z")}
            if not isinstance(map_name, str) or not map_name:
                raise ValueError(f"gathering node {node_index} has no map name")
            if any(not isinstance(value, (int, float)) for value in position.values()):
                raise ValueError(f"gathering node {node_index} has invalid coordinates")
            items = []
            for mapped_item in mapped_items:
                item_name = str(mapped_item.get("name") or "")
                item_occurrences += 1
                items.append({
                    "sourceItemId": mapped_item.get("goodsId"),
                    "name": item_name,
                    "category": mapped_item.get("category"),
                    "quantity": mapped_item.get("num"),
                    "broadCategory": "crafting_material",
                    "subCategory": "gathering_material",
                })
                broad_categories["crafting_material"] += 1
            source_index = 1_000_000 + node_index
            records.append({
                "sourceIndex": source_index,
                "sourceRecordId": f"mapforgoblins-gathering-{node_index}",
                "map": map_name,
                "coordinateSpace": "game_world_xyz",
                "position": position,
                "part": node.get("name"),
                "items": items,
                "broadCategory": "crafting_material",
                "placementType": "gathering_node",
                "isStatic": True,
                "itemLotId": mapping.get("pickUpItemLotParamId"),
                "gatheringModel": node.get("model"),
                "gatheringInstanceId": node.get("instance_id", node.get("instanceId")),
                "gatheringArea": node.get("area"),
                "sourceKind": "gathering_node",
            })
            placement_types["gathering_node"] += 1
            map_counts[map_name] += 1
            gathering_count += 1
        gathering_source = {
            "nodes": str(gathering_nodes_path),
            "nodesSha256": sha256(gathering_nodes_path),
            "mappings": [str(path) for path in gathering_mappings_paths],
            "mappingSha256": [sha256(path) for path in gathering_mappings_paths],
            "recordCount": gathering_count,
        }

    source = {
        "id": "map_for_goblins",
        "name": "ERR-MapForGoblins-DLL vanilla profile",
        "url": "https://github.com/Jovial-Nik/ERR-MapForGoblins-DLL",
        "commit": "324a895ba51d6091534578c2ce194d0c6720edc2",
        "profile": source_profile,
        "rawDatabase": str(raw_path),
        "rawDatabaseSha256": sha256(raw_path),
        "localGameSnapshot": local_game_snapshot,
        "gathering": gathering_source,
        "policy": (
            "Only records generated by the explicitly labelled vanilla profile "
            "are eligible; native part names remain endpoint-local evidence and "
            "never create navigation edges."
        ),
    }
    return {
        "schema": "errn-mapforgoblins-item-index@1",
        "built_at": retrieved_at,
        "source": source,
        "stats": {
            "recordCount": len(records),
            "itemOccurrenceCount": item_occurrences,
            "blankNameOccurrences": blank_names,
            "placementTypeCounts": dict(sorted(placement_types.items())),
            "broadCategoryCounts": dict(sorted(broad_categories.items())),
            "mapCount": len(map_counts),
            "sourceProfile": source_profile,
            "nativePartRecordCount": sum(bool(record.get("part")) for record in records),
        },
        "records": records,
    }


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
    parser.add_argument("--raw-items-database", type=Path)
    parser.add_argument("--source-profile", choices=["vanilla"])
    parser.add_argument("--local-game-snapshot")
    parser.add_argument("--gathering-nodes", type=Path)
    parser.add_argument("--gathering-mappings", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--retrieved-at", default="2026-08-18")
    args = parser.parse_args()
    if args.raw_items_database:
        if not args.source_profile:
            parser.error("--raw-items-database requires --source-profile vanilla")
        payload = normalize_raw_items_database(
            args.raw_items_database,
            args.retrieved_at,
            args.source_profile,
            args.local_game_snapshot,
            args.gathering_nodes,
            args.gathering_mappings,
        )
    else:
        payload = normalize(args.source_dir, args.retrieved_at)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(payload["stats"], ensure_ascii=False))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
