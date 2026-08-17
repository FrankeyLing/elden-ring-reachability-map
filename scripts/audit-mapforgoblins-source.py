"""Read-only audit for the fixed Map For Goblins JSON snapshot.

This audit reads project snapshot files and, when --source-dir is supplied,
re-hashes the matching fixed Git files. It never starts the game, reads game
process memory, reads a save, reads a game directory, or promotes coordinate
conversions into traversal edges.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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


def audit(source_dir: Path | None = None) -> dict:
    manifest = load(MANIFEST)
    source = manifest["source"]
    artifacts = manifest["artifacts"]
    artifact_counts = {}
    artifact_sources = {}

    for artifact in artifacts:
        path = ROOT / artifact["path"]
        payload = load(path)
        records = payload["records"]
        if len(records) != artifact["records"]:
            raise ValueError(f"record count mismatch: {artifact['path']}")
        if payload["source"]["commit"] != source["commit"]:
            raise ValueError(f"commit mismatch: {artifact['path']}")
        artifact_counts[artifact["path"]] = len(records)
        artifact_sources[artifact["path"]] = payload["source"]

    grace_path = next(path for path in artifact_counts if "grace-positions" in path)
    boss_path = next(path for path in artifact_counts if "boss-positions" in path)
    tile_paths = [path for path in artifact_counts if "tile-regions" in path]
    base_conversion_path = next(path for path in artifact_counts if "conversions-base" in path)
    dlc_conversion_path = next(path for path in artifact_counts if "conversions-dlc" in path)

    grace = load(ROOT / grace_path)
    bosses = load(ROOT / boss_path)
    tile_records = []
    for path in sorted(tile_paths):
        tile_records.extend(load(ROOT / path)["records"])
    base_conversions = load(ROOT / base_conversion_path)["records"]
    dlc_conversions = load(ROOT / dlc_conversion_path)["records"]

    tile_ids = [record[0] for record in tile_records]
    if len(tile_ids) != len(set(tile_ids)):
        raise ValueError("duplicate map IDs across tile-region snapshot parts")

    boss_formal_candidates = [record[-1] for record in bosses["records"]]
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
            "tile_region_records": len(tile_records),
            "legacy_conversion_records": len(base_conversions),
            "dlc_legacy_conversion_records": len(dlc_conversions),
        },
        "promotion": {
            "coordinate_type": "online_game_extract",
            "formal_graph_edges_added": 0,
            "map_conversions_treated_as_routes": False,
            "grace_names_guessed_by_array_order": False,
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
            filename = snapshot_source["file"]
            path = source_dir / filename
            if not path.is_file():
                raise FileNotFoundError(path)
            verified_files[filename] = sha256(path)
            if verified_files[filename] != snapshot_source["sha256"]:
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
