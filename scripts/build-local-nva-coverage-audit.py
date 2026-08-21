#!/usr/bin/env python3
"""Audit MSBE map coverage against the copied native NVA inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


NVA_PATH_RE = re.compile(r"^/map/m\d+/(m\d+_\d+_\d+_\d+)/\1\.nva\.dcx$", re.IGNORECASE)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def archive_hash_inventory(hash_root: Path | None) -> dict[str, Any] | None:
    if hash_root is None or not hash_root.is_dir():
        return None
    rows: list[dict[str, str]] = []
    for path in sorted(hash_root.glob("*.txt")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            value = line.strip()
            if NVA_PATH_RE.match(value):
                rows.append({"manifest_file": path.name, "path": value})
    map_ids = sorted({NVA_PATH_RE.match(row["path"]).group(1).lower() for row in rows})
    return {
        "hash_root": str(hash_root),
        "hash_files": [
            {"name": path.name, "sha256": sha256(path), "size": path.stat().st_size}
            for path in sorted(hash_root.glob("*.txt"))
            if any(row["manifest_file"] == path.name for row in rows)
        ],
        "nva_path_count": len(rows),
        "nva_map_count": len(map_ids),
        "nva_map_ids": map_ids,
        "paths": rows,
    }


def extracted_nva_inventory(root: Path | None) -> dict[str, Any] | None:
    if root is None or not root.is_dir():
        return None
    paths = sorted(root.rglob("*.nva.dcx"))
    map_ids = sorted({path.name.removesuffix(".nva.dcx").lower() for path in paths})
    return {
        "root": str(root),
        "nva_path_count": len(paths),
        "nva_map_count": len(map_ids),
        "nva_map_ids": map_ids,
        "file_sha256_by_name": {path.name: sha256(path) for path in paths},
    }


def map_capabilities(record: dict[str, Any]) -> dict[str, Any]:
    part_types = record.get("part_types", {})
    region_types = record.get("region_types", {})
    event_types = record.get("event_types", {})
    counts = record.get("counts", {})
    return {
        "models": counts.get("models", 0),
        "parts": counts.get("parts", 0),
        "regions": counts.get("regions", 0),
        "events": counts.get("events", 0),
        "collision_parts": part_types.get("Collision", 0),
        "connect_collision_parts": part_types.get("ConnectCollision", 0),
        "map_piece_parts": part_types.get("MapPiece", 0),
        "player_parts": part_types.get("Player", 0),
        "enemy_parts": part_types.get("Enemy", 0),
        "play_area_regions": region_types.get("PlayArea", 0),
        "connection_regions": region_types.get("Connection", 0),
        "wind_regions": region_types.get("WindSFX", 0) + region_types.get("WindArea", 0),
        "objact_events": event_types.get("ObjAct", 0),
        "mount_events": event_types.get("Mount", 0),
        "transport_events": event_types.get("PseudoMultiplayer", 0)
        + event_types.get("OnlinePseudoMultiplayer", 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--msbe-index", type=Path, required=True)
    parser.add_argument("--nva-index", type=Path, required=True)
    parser.add_argument("--archive-hash-root", type=Path)
    parser.add_argument("--nva-reextract-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    msbe_path = args.msbe_index.resolve()
    nva_path = args.nva_index.resolve()
    msbe = json.loads(msbe_path.read_text(encoding="utf-8"))
    nva = json.loads(nva_path.read_text(encoding="utf-8"))
    msbe_by_map = {record["map_id"]: record for record in msbe.get("maps", [])}
    nva_by_map = {record["map_id"]: record for record in nva.get("records", []) if record.get("map_id")}
    archive_hash = archive_hash_inventory(
        args.archive_hash_root.resolve() if args.archive_hash_root else None
    )
    reextract = extracted_nva_inventory(
        args.nva_reextract_root.resolve() if args.nva_reextract_root else None
    )
    if archive_hash is not None and reextract is not None:
        hash_ids = set(archive_hash["nva_map_ids"])
        reextract_ids = set(reextract["nva_map_ids"])
        archive_hash["hash_catalog_only_map_ids"] = sorted(hash_ids - reextract_ids)
        archive_hash["reextract_not_in_hash_catalog_map_ids"] = sorted(reextract_ids - hash_ids)
        archive_hash["reextract_matches_hash_catalog_actual_ids"] = reextract_ids <= hash_ids
        archive_hash["reextract_matches_primary_nva_index_ids"] = reextract_ids == set(nva_by_map)
    missing_ids = sorted(set(msbe_by_map) - set(nva_by_map))
    extra_ids = sorted(set(nva_by_map) - set(msbe_by_map))
    missing = []
    for map_id in missing_ids:
        record = msbe_by_map[map_id]
        missing.append(
            {
                "map_id": map_id,
                "source_file": record.get("source_file"),
                "source_entry": record.get("source_entry"),
                "capabilities": map_capabilities(record),
                "native_nva_status": "missing_from_snapshot_nva_inventory",
                "playability_classification": "unclassified_requires_independent_evidence",
                "routeable": False,
            }
        )
    prefix_counts = Counter(map_id.split("_")[0] for map_id in missing_ids)
    output = {
        "schema": "elden-ring-local-nva-coverage-audit@1",
        "source": {
            "msbe_index": str(msbe_path),
            "nva_index": str(nva_path),
            "msbe_snapshot_id": msbe.get("source", {}).get("snapshot_id"),
            "nva_snapshot_id": "elden-ring-local-snapshot-20260818",
            "archive_hash_inventory": archive_hash,
            "nva_reextract_inventory": reextract,
        },
        "model": {
            "purpose": "coverage audit, not a playable-map classifier",
            "missing_nva_does_not_mean_unplayable": True,
            "playability_classification_is_unresolved": True,
            "archive_inventory_checked": archive_hash is not None and reextract is not None,
            "routeable": False,
        },
        "status": {
            "msbe_map_count": len(msbe_by_map),
            "nva_map_count": len(nva_by_map),
            "msbe_maps_with_nva": len(set(msbe_by_map) & set(nva_by_map)),
            "msbe_maps_missing_nva": len(missing),
            "nva_maps_without_msbe": len(extra_ids),
            "coverage_fraction": (len(set(msbe_by_map) & set(nva_by_map)) / len(msbe_by_map)) if msbe_by_map else 0.0,
            "routeable_records": 0,
            "all_records_routeable_false": True,
            "missing_map_prefix_counts": dict(sorted(prefix_counts.items())),
            "archive_hash_nva_path_count": archive_hash.get("nva_path_count") if archive_hash else None,
            "archive_hash_nva_map_count": archive_hash.get("nva_map_count") if archive_hash else None,
            "archive_reextract_nva_path_count": reextract.get("nva_path_count") if reextract else None,
            "archive_reextract_nva_map_count": reextract.get("nva_map_count") if reextract else None,
            "archive_hash_catalog_only_map_count": (
                len(archive_hash.get("hash_catalog_only_map_ids", [])) if archive_hash else None
            ),
            "archive_reextract_matches_primary_nva_index": (
                archive_hash.get("reextract_matches_primary_nva_index_ids") if archive_hash else None
            ),
        },
        "missing_maps": missing,
        "extra_nva_map_ids": extra_ids,
        "note": "This report prevents missing NVA files from being silently treated as absent game space. When supplied, the copied archive hash catalog and independent Nuxe re-extraction are recorded; every MSBE map without an actual NVA record remains a separately unresolved coverage item.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
