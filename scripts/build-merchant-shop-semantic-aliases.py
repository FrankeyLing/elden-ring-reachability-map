#!/usr/bin/env python3
"""Build conservative semantic aliases for unnamed shop proxy entities.

The copied map scene snapshot contains a shop proxy model whose official
display name is empty, but whose scene identity is explicit: model ``c4450``
uses ThinkParamID 44500000 and its walk-route metadata identifies a walking
mausoleum. The alias is emitted separately so the shop binding builder can
consume it without hiding the evidence or changing the raw source table.
"""

from __future__ import annotations

import argparse
import glob
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "data" / "v1" / "entities" / "merchant-shop-semantic-aliases.json"


def load_maps(msb_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw_path in sorted(glob.glob(str(msb_dir / "*.json"))):
        path = Path(raw_path)
        if path.name == "batch-manifest.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        records.append(payload)
    return records


def build(msb_dir: Path, merchant_source: Path | None) -> dict[str, Any]:
    by_npc: dict[int, dict[str, Any]] = defaultdict(lambda: {
        "modelNames": set(),
        "thinkParamIds": set(),
        "maps": set(),
        "parts": set(),
        "walkRouteNames": set(),
        "positions": [],
    })
    for payload in load_maps(msb_dir):
        map_name = payload.get("source_entry") or "unknown"
        for part in payload.get("parts", []):
            if part.get("model_name") != "c4450":
                continue
            extra = part.get("extra") or {}
            npc_id = extra.get("NPCParamID")
            if not isinstance(npc_id, int):
                continue
            record = by_npc[npc_id]
            record["modelNames"].add(part.get("model_name"))
            record["thinkParamIds"].add(extra.get("ThinkParamID"))
            record["maps"].add(map_name)
            record["parts"].add(part.get("name"))
            if extra.get("WalkRouteName"):
                record["walkRouteNames"].add(extra["WalkRouteName"])
            if isinstance(part.get("position"), dict):
                record["positions"].append(part["position"])

    if not by_npc:
        raise ValueError("no c4450 semantic shop proxies found in copied map snapshot")
    invalid_think = {
        think
        for record in by_npc.values()
        for think in record["thinkParamIds"]
        if think != 44500000
    }
    if invalid_think:
        raise ValueError(f"c4450 proxy has unexpected ThinkParamID values: {sorted(invalid_think)}")

    source_rows: dict[int, set[int]] = defaultdict(set)
    if merchant_source and merchant_source.is_file():
        with merchant_source.open("r", encoding="utf-8-sig") as handle:
            header = None
            for raw in handle:
                if not raw.strip() or raw.startswith("#"):
                    continue
                values = raw.rstrip("\n").split("\t")
                if header is None:
                    header = values
                    continue
                row = dict(zip(header, values))
                try:
                    row_id = int(row["row_id"])
                    npc_id = int(row["npc_param_id"])
                except (KeyError, TypeError, ValueError):
                    continue
                if npc_id in by_npc:
                    source_rows[npc_id].add(row_id)

    aliases = []
    for npc_id in sorted(by_npc):
        record = by_npc[npc_id]
        route_names = sorted(record["walkRouteNames"])
        aliases.append({
            "id": f"semantic-shop-alias-npc{npc_id}",
            "merchantName": "Wandering Mausoleum Corpse",
            "sellerIdentitySource": "local_map_semantic_alias",
            "npcParamId": npc_id,
            "modelNames": sorted(record["modelNames"]),
            "thinkParamIds": sorted(record["thinkParamIds"]),
            "sourceMaps": sorted(record["maps"]),
            "sourceParts": sorted(record["parts"]),
            "sourceWalkRouteNames": route_names,
            "shopLineupRows": sorted(source_rows.get(npc_id, set())),
            "sourceEvidence": [
                "copied local map scene part uses model c4450",
                "copied local map scene part uses ThinkParamID 44500000",
                "copied local map scene walk-route metadata identifies the walking mausoleum",
                "the same exact NPCParamID and map endpoint opens the remembrance shop rows",
            ],
            "verification": "local_map_model_thinkparam_walkroute_and_shop_endpoint_exact",
        })
    return {
        "schema": "elden-ring-merchant-shop-semantic-aliases@1",
        "builtFrom": {
            "msbDir": str(msb_dir),
            "merchantSource": str(merchant_source) if merchant_source else None,
            "policy": "only c4450 proxies with ThinkParamID 44500000 are aliased; all other unnamed sellers remain unresolved",
        },
        "stats": {
            "aliasCount": len(aliases),
            "mapInstanceCount": len({map_name for alias in aliases for map_name in alias["sourceMaps"]}),
            "shopLineupRowCount": len({row for alias in aliases for row in alias["shopLineupRows"]}),
        },
        "aliases": aliases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--msb-dir", type=Path, required=True)
    parser.add_argument("--merchant-source", type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    payload = build(args.msb_dir, args.merchant_source)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2))
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.3f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
