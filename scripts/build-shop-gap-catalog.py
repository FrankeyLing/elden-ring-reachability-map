#!/usr/bin/env python3
"""Publish unresolved shop rows as an independently repairable evidence catalog.

The acquisition registry already keeps unresolved purchases searchable.  This
artifact gives each unresolved row a compact repair record so later data work
can fill one seller or one endpoint without rebuilding or invalidating other
shop relations.  No seller is inferred from neighboring rows, item ids, or
shop context numbers.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ACQUISITIONS = ROOT / "data" / "v1" / "entities" / "acquisition-registry.json"
DEFAULT_OUTPUT = ROOT / "data" / "v1" / "entities" / "shop-gap-catalog.json"


def source_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def endpoint_status(binding: dict[str, Any] | None) -> str:
    if not binding:
        return "not_present"
    if binding.get("position") and binding.get("map"):
        return "candidate_coordinate_endpoint"
    return str(binding.get("endpointStatus") or "unbound")


def compact_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item[key]
        for key in ("item", "name", "price", "costType", "mtrlId", "stock", "lineupRow")
        if key in item
    }


def compact_binding(binding: dict[str, Any] | None) -> dict[str, Any] | None:
    if not binding:
        return None
    result: dict[str, Any] = {
        key: binding[key]
        for key in (
            "id",
            "talkId",
            "npcParamId",
            "merchantName",
            "map",
            "mapSource",
            "npcNameId",
            "position",
            "part",
            "instanceId",
            "entityId",
            "mapStudioLayer",
            "endpointStatus",
            "sellerStatus",
            "sellerIdentitySource",
            "localSpawnMatch",
            "semanticAliasId",
        )
        if key in binding
    }
    result["endpointStatus"] = endpoint_status(binding)
    return result


def build(acquisitions: dict[str, Any], input_path: Path) -> dict[str, Any]:
    relations = {
        relation.get("id"): relation
        for relation in acquisitions.get("relations", [])
        if relation.get("id")
    }
    gaps = [
        gap for gap in acquisitions.get("coverageGaps", [])
        if gap.get("method") == "purchase"
    ]
    records: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    context_counts: Counter[str] = Counter()
    for gap in sorted(gaps, key=lambda row: (row.get("lineupRow") or -1, row.get("id") or "")):
        relation = relations.get(gap.get("relationId"))
        if relation is None:
            raise ValueError(f"shop gap references missing relation: {gap.get('id')}")
        binding = relation.get("merchantShopBinding") or None
        context = relation.get("from")
        status = gap.get("status")
        status_counts[str(status)] += 1
        context_counts[str(context)] += 1
        records.append({
            "id": gap["id"],
            "method": "purchase",
            "status": status,
            "repairStatus": "open",
            "lineupRow": gap.get("lineupRow"),
            "shopContext": context,
            "items": [compact_item(item) for item in relation.get("items", [])],
            "seller": {
                "status": relation.get("sellerStatus"),
                "merchantName": (binding or {}).get("merchantName"),
                "talkId": (binding or {}).get("talkId"),
                "npcParamId": (binding or {}).get("npcParamId"),
            },
            "candidateBinding": compact_binding(binding),
            "endpointStatus": endpoint_status(binding),
            "hasCandidateBinding": bool(binding),
            "hasNamedSibling": bool(gap.get("hasNamedSibling")),
            "source": {
                "parameter": "ShopLineupParam",
                "rowId": gap.get("lineupRow"),
                "verification": gap.get("verification"),
                "evidence": list(gap.get("evidence", [])),
            },
            "relationId": relation["id"],
        })

    return {
        "schema": "elden-ring-shop-gap-catalog@1",
        "builtFrom": {
            "acquisitionRegistry": source_path(input_path),
            "acquisitionSchema": acquisitions.get("schema"),
            "policy": (
                "retain every unresolved purchase relation independently; "
                "never infer a seller from neighboring rows, item ids, or shop context numbers"
            ),
        },
        "stats": {
            "gapCount": len(records),
            "statusCounts": dict(sorted(status_counts.items())),
            "shopContextCount": len(context_counts),
            "shopContextCounts": dict(sorted(context_counts.items())),
            "candidateBindingCount": sum(record["hasCandidateBinding"] for record in records),
            "candidateEndpointCount": sum(
                record["endpointStatus"] == "candidate_coordinate_endpoint"
                for record in records
            ),
            "namedSiblingCandidateCount": sum(record["hasNamedSibling"] for record in records),
            "openCount": len(records),
        },
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acquisitions", type=Path, default=DEFAULT_ACQUISITIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    acquisitions = json.loads(args.acquisitions.read_text(encoding="utf-8"))
    payload = build(acquisitions, args.acquisitions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2))
    print(f"wrote {args.output} ({args.output.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
