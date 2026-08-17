"""Read-only audit for the fixed Map For Goblins JSON snapshot.

This audit reads project snapshot files and, when --source-dir is supplied,
re-hashes the matching fixed Git files. It never starts the game, reads game
process memory, reads a save, reads a game directory, or promotes coordinate
conversions into traversal edges.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ROOT = ROOT / "data" / "v1" / "source-snapshots"
MANIFEST = SNAPSHOT_ROOT / "mapforgoblins-online-index-20260818.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode_chunks(paths: list[str], label: str) -> tuple[list[dict], list]:
    payloads = sorted(
        (load(ROOT / path) for path in paths),
        key=lambda payload: payload["part"],
    )
    expected_parts = payloads[0]["parts"] if payloads else 0
    parts = [payload["part"] for payload in payloads]
    if not payloads or expected_parts != len(payloads) or parts != list(range(1, expected_parts + 1)):
        raise ValueError(f"{label} chunks are incomplete or out of order")
    records = json.loads(
        zlib.decompress(
            base64.b64decode("".join(payload["chunk"] for payload in payloads))
        ).decode("utf-8")
    )
    return payloads, records


def audit(source_dir: Path | None = None) -> dict:
    manifest = load(MANIFEST)
    source = manifest["source"]
    artifacts = manifest["artifacts"]
    artifact_counts = {}
    artifact_sources = {}

    for artifact in artifacts:
        path = ROOT / artifact["path"]
        payload = load(path)
        if payload.get("encoding") == "zlib+base64":
            if not payload.get("chunk") or payload.get("part") != artifact["chunk"]:
                raise ValueError(f"compressed chunk metadata mismatch: {artifact['path']}")
        else:
            records = payload["records"]
            if len(records) != artifact["records"]:
                raise ValueError(f"record count mismatch: {artifact['path']}")
        if payload["source"]["commit"] != source["commit"]:
            raise ValueError(f"commit mismatch: {artifact['path']}")
        artifact_counts[artifact["path"]] = artifact["records"]
        artifact_sources[artifact["path"]] = payload["source"]

    grace_path = next(path for path in artifact_counts if "grace-positions" in path)
    boss_path = next(path for path in artifact_counts if "boss-positions" in path)
    tile_paths = [path for path in artifact_counts if "tile-regions" in path]
    base_conversion_path = next(path for path in artifact_counts if "conversions-base" in path)
    dlc_conversion_path = next(path for path in artifact_counts if "conversions-dlc" in path)
    map_point_paths = [path for path in artifact_counts if "map-points-part" in path]
    item_paths = [path for path in artifact_counts if "item-index-part" in path]
    entity_paths = [path for path in artifact_counts if "entity-index-part" in path]
    gathering_paths = [path for path in artifact_counts if "gathering-index-part" in path]

    grace = load(ROOT / grace_path)
    bosses = load(ROOT / boss_path)
    tile_records = []
    for path in sorted(tile_paths):
        tile_records.extend(load(ROOT / path)["records"])
    base_conversions = load(ROOT / base_conversion_path)["records"]
    dlc_conversions = load(ROOT / dlc_conversion_path)["records"]
    map_point_records = []
    for path in sorted(map_point_paths):
        map_point_records.extend(load(ROOT / path)["records"])
    item_payloads, item_records = decode_chunks(item_paths, "item index")
    entity_payloads, entity_records = decode_chunks(entity_paths, "entity index")
    gathering_payloads, gathering_records = decode_chunks(gathering_paths, "gathering index")
    if len(item_records) != 31144:
        raise ValueError(f"unexpected item placement count: {len(item_records)}")
    if len(entity_records) != 15099:
        raise ValueError(f"unexpected entity count: {len(entity_records)}")
    if len(gathering_records) != 21824:
        raise ValueError(f"unexpected gathering count: {len(gathering_records)}")

    tile_ids = [record[0] for record in tile_records]
    if len(tile_ids) != len(set(tile_ids)):
        raise ValueError("duplicate map IDs across tile-region snapshot parts")
    map_point_ids = [record[1] for record in map_point_records]
    if len(map_point_ids) != len(set(map_point_ids)):
        raise ValueError("duplicate WorldMapPointParam IDs across map-point snapshot parts")

    boss_formal_candidates = [record[-1] for record in bosses["records"]]
    map_point_formal_candidates = [record[-1] for record in map_point_records]
    result = {
        "manifest": str(MANIFEST.relative_to(ROOT)),
        "source": {
            "id": source["id"],
            "commit": source["commit"],
            "license": source["license"],
        },
        "snapshot": {
            "grace_position_records": len(grace["records"]),
            "grace_position_non_dummy": sum(not record[-1] for record in grace["records"]),
            "boss_records": len(bosses["records"]),
            "boss_unique_formal_candidates": sum(len(candidates) == 1 for candidates in boss_formal_candidates),
            "boss_ambiguous_formal_candidates": sum(len(candidates) > 1 for candidates in boss_formal_candidates),
            "boss_without_formal_candidate": sum(not candidates for candidates in boss_formal_candidates),
            "named_map_point_records": len(map_point_records),
            "named_map_point_unique_formal_candidates": sum(
                len(candidates) == 1 for candidates in map_point_formal_candidates
            ),
            "named_map_point_ambiguous_formal_candidates": sum(
                len(candidates) > 1 for candidates in map_point_formal_candidates
            ),
            "named_map_point_without_formal_candidate": sum(
                not candidates for candidates in map_point_formal_candidates
            ),
            "item_placement_records": len(item_records),
            "item_index_chunks": len(item_payloads),
            "entity_records": len(entity_records),
            "entity_index_chunks": len(entity_payloads),
            "gathering_records": len(gathering_records),
            "gathering_index_chunks": len(gathering_payloads),
            "tile_region_records": len(tile_records),
            "legacy_conversion_records": len(base_conversions),
            "dlc_legacy_conversion_records": len(dlc_conversions),
        },
        "promotion": {
            "coordinate_type": "online_game_extract",
            "formal_graph_edges_added": 0,
            "map_conversions_treated_as_routes": False,
            "grace_names_guessed_by_array_order": False,
            "map_point_names_promoted_to_routes": False,
        },
        "safety": {
            "game_process_accessed": False,
            "game_files_accessed": False,
            "save_access": False,
            "runtime_injection": False,
            "overlay": False,
            "writes_performed": False,
        },
    }

    if source_dir is not None:
        source_dir = source_dir.resolve()
        verified_files = {}
        for snapshot_source in artifact_sources.values():
            files = snapshot_source.get("files")
            if files is None:
                files = {snapshot_source["file"]: snapshot_source["sha256"]}
            for filename, expected_hash in files.items():
                path = source_dir / filename
                if not path.is_file():
                    raise FileNotFoundError(path)
                verified_files[filename] = sha256(path)
                if verified_files[filename] != expected_hash:
                    raise ValueError(f"source hash mismatch: {filename}")
        result["source_reverification"] = {
            "source_dir": str(source_dir),
            "verified_files": verified_files,
        }
    else:
        result["source_reverification"] = {
            "status": "not_requested",
            "hint": "pass --source-dir to re-hash the fixed Git JSON files",
        }

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.source_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
