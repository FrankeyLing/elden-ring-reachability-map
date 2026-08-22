#!/usr/bin/env python3
"""Audit the independent formal-origin to abstract-map evidence package."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "v1" / "entities" / "abstract-origin-bindings.json"
DEFAULT_FORMAL_GRAPH = ROOT / "data" / "v1" / "graph-v1.json"
MAP_PATTERN = re.compile(r"m\d+_\d+_\d+_\d+", re.IGNORECASE)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--formal-graph", type=Path, default=DEFAULT_FORMAL_GRAPH)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    graph = json.loads(args.formal_graph.read_text(encoding="utf-8"))
    formal_ids = {row.get("id") for row in graph.get("nodes", []) if row.get("id")}
    records = payload.get("records", [])
    assert payload.get("schema") == "elden-ring-reachability-map/abstract-origin-bindings@1"
    assert len({row.get("id") for row in records}) == len(records)
    assert records
    for row in records:
        assert MAP_PATTERN.fullmatch(row["originMapId"]), row
        assert row["originMapNodeId"] == f"abstract-map:{row['originMapId']}", row
        assert row["playerRouteable"] is False and row["routeable"] is False, row
        assert row["localIdentity"]["status"] == "exact_local_grace_identity", row
        status = row["binding"]["status"]
        if status in {
            "exact_manual_formal_identity",
            "exact_unique_formal_grace_name_identity",
            "exact_name_and_map_grid_identity",
        }:
            assert row["formalNodeId"] in formal_ids, row
            assert row["abstractOriginRouteable"] is True, row
        else:
            assert row["abstractOriginRouteable"] is False, row
            if row.get("formalNodeId"):
                assert row["formalNodeId"] in row["formalCandidateIds"], row
    stats = payload["stats"]
    counts = Counter(row["binding"]["status"] for row in records)
    assert dict(sorted(counts.items())) == stats["bindingStatusCounts"]
    assert stats["exactAbstractOriginCount"] == sum(
        row["abstractOriginRouteable"] for row in records
    )
    assert stats["exactAbstractOriginCount"] == stats["recordCount"] == 419
    assert counts == Counter({
        "exact_unique_formal_grace_name_identity": 378,
        "exact_manual_formal_identity": 39,
        "exact_name_and_map_grid_identity": 2,
    })
    assert stats["allPlayerRouteableFalse"] is True
    assert stats["allRouteableFalse"] is True
    print("ABSTRACT ORIGIN BINDINGS AUDIT: PASS")
    print(json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
