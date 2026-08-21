#!/usr/bin/env python3
"""Reproduce exact-equivalence evidence for selected parsed MapStudio pairs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "data" / "v1" / "entities" / "equivalent-map-instances.json"
GROUPS = {
    "m60_45_39": ("m60_45_39_00", "m60_45_39_10"),
    "m60_44_52": ("m60_44_52_00", "m60_44_52_10"),
    "m61_47_46": ("m61_47_46_00", "m61_47_46_10"),
}
VOLATILE_KEYS = {"source_file", "source_entry", "map_id", "mapId"}


def normalize(value: Any, member_ids: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        return {
            key: normalize(item, member_ids)
            for key, item in sorted(value.items())
            if key not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [normalize(item, member_ids) for item in value]
    if isinstance(value, str):
        result = value
        for member_id in member_ids:
            result = result.replace(member_id, "<MAP>")
        return result
    return value


def digest(path: Path, member_ids: tuple[str, ...]) -> str:
    normalized = normalize(json.loads(path.read_text(encoding="utf-8")), member_ids)
    encoded = json.dumps(
        normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--maps-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    rows = []
    for coarse_id, member_ids in GROUPS.items():
        paths = [args.maps_dir / f"{member_id}.json" for member_id in member_ids]
        missing = [str(path) for path in paths if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"missing parsed maps for {coarse_id}: {missing}")
        digests = [digest(path, member_ids) for path in paths]
        if len(set(digests)) != 1:
            raise ValueError(f"parsed maps are not content-equivalent: {coarse_id} {digests}")
        rows.append({
            "coarseMapId": coarse_id,
            "mapIds": list(member_ids),
            "normalizedParsedSha256": digests[0],
        })

    payload = {
        "schema": "elden-ring-reachability-map/equivalent-map-instances@1",
        "sourceSnapshot": "elden-ring-local-snapshot-20260818",
        "algorithm": (
            "SHA-256 over parsed MapStudio JSON after recursively removing "
            "source_file/source_entry/map_id/mapId and replacing the pair member ids with <MAP>"
        ),
        "groups": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(rows)} exact-equivalence groups to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
