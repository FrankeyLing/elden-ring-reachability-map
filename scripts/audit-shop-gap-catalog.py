#!/usr/bin/env python3
"""Audit the isolated unresolved-shop evidence catalog."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = ROOT / "data" / "v1" / "entities" / "shop-gap-catalog.json"
DEFAULT_ACQUISITIONS = ROOT / "data" / "v1" / "entities" / "acquisition-registry.json"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--acquisitions", type=Path, default=DEFAULT_ACQUISITIONS)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    acquisitions = json.loads(args.acquisitions.read_text(encoding="utf-8"))

    check(catalog.get("schema") == "elden-ring-shop-gap-catalog@1", "invalid catalog schema")
    relations = {
        relation.get("id"): relation
        for relation in acquisitions.get("relations", [])
        if relation.get("id")
    }
    source_gaps = {
        gap.get("id"): gap
        for gap in acquisitions.get("coverageGaps", [])
        if gap.get("method") == "purchase"
    }
    records = catalog.get("records", [])
    check(len(records) == len(source_gaps), "catalog gap count differs from acquisition registry")
    check(len({record.get("id") for record in records}) == len(records), "catalog gap ids are not unique")
    check(catalog.get("stats", {}).get("gapCount") == len(records), "catalog gap stat mismatch")
    check(catalog.get("stats", {}).get("openCount") == len(records), "catalog open stat mismatch")

    statuses = Counter()
    for record in records:
        gap_id = record.get("id")
        source_gap = source_gaps.get(gap_id)
        check(source_gap is not None, f"catalog record has no source gap: {gap_id}")
        relation = relations.get(record.get("relationId"))
        check(relation is not None, f"catalog record has no relation: {gap_id}")
        check(record.get("method") == "purchase", f"catalog record is not purchase: {gap_id}")
        check(record.get("repairStatus") == "open", f"catalog record is not open: {gap_id}")
        check(record.get("lineupRow") == source_gap.get("lineupRow"), f"lineup row mismatch: {gap_id}")
        check(record.get("shopContext") == relation.get("from"), f"shop context mismatch: {gap_id}")
        check(record.get("relationId") == source_gap.get("relationId"), f"relation mismatch: {gap_id}")
        check(record.get("status") == source_gap.get("status"), f"gap status mismatch: {gap_id}")
        check(relation.get("sellerStatus") != "named", f"named relation leaked into catalog: {gap_id}")
        check(record.get("hasCandidateBinding") == bool(relation.get("merchantShopBinding")), f"candidate flag mismatch: {gap_id}")
        check(record.get("items") == [
            {
                key: item[key]
                for key in ("item", "name", "price", "costType", "mtrlId", "stock", "lineupRow")
                if key in item
            }
            for item in relation.get("items", [])
        ], f"item evidence mismatch: {gap_id}")
        if not record.get("hasCandidateBinding"):
            check(record.get("candidateBinding") is None, f"no-binding row has candidate payload: {gap_id}")
            check(record.get("endpointStatus") == "not_present", f"no-binding row has endpoint status: {gap_id}")
        else:
            check(record.get("candidateBinding") is not None, f"candidate row lost binding: {gap_id}")
        statuses[str(record.get("status"))] += 1

    check(catalog.get("stats", {}).get("statusCounts") == dict(sorted(statuses.items())), "status stat mismatch")
    check(
        catalog.get("stats", {}).get("candidateBindingCount")
        == sum(record.get("hasCandidateBinding") is True for record in records),
        "candidate binding stat mismatch",
    )
    print("SHOP GAP CATALOG AUDIT: PASS")
    print(json.dumps({
        "records": len(records),
        "statuses": dict(sorted(statuses.items())),
        "candidate_bindings": sum(record.get("hasCandidateBinding") is True for record in records),
        "all_open": all(record.get("repairStatus") == "open" for record in records),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
