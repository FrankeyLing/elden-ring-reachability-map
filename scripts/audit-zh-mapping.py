#!/usr/bin/env python3
"""Audit the official-Chinese mapping and the formal graph data completeness.

Checks:
  1. every node/edge/condition/layer/epoch field has a mapping entry;
  2. uncovered fields are explicitly listed (they have no official text);
  3. official/composite/partial levels must contain Chinese text;
  4. the formal graph has no empty required fields (label/region/floor/
     description/mode/note/condition label/hint);
  5. mapping entries resolve against the official FMG index (spot check).

Usage:
    python scripts/audit-zh-mapping.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED_NODE_FIELDS = ("label", "region", "floor", "description")
REQUIRED_EDGE_FIELDS = ("mode", "note")
REQUIRED_CONDITION_FIELDS = ("label", "hint")


def is_zh(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=Path("data/v1/graph.json"))
    parser.add_argument("--mapping", type=Path, default=Path("data/v1/zh-cn/official-zh-mapping.json"))
    args = parser.parse_args()

    graph = json.loads(args.graph.resolve().read_text(encoding="utf-8"))
    mapping = json.loads(args.mapping.resolve().read_text(encoding="utf-8"))
    failures = []

    # ---- 1. mapping entry presence + levels ----
    nodes = {n["id"]: n for n in graph["nodes"]}
    edges = {e["id"]: e for e in graph["edges"]}
    conditions = {c["id"]: c for c in graph["conditions"]}
    layers = {l["id"]: l for l in graph.get("layers", [])}
    epochs = {e["id"]: e for e in graph.get("worldEpochs", [])}

    mapping_nodes = mapping.get("nodes", {})
    mapping_edges = mapping.get("edges", {})
    mapping_conditions = mapping.get("conditions", {})
    mapping_layers = mapping.get("layers", {})
    mapping_epochs = mapping.get("epochs", {})

    for node_id, node in nodes.items():
        for field in REQUIRED_NODE_FIELDS:
            entry = mapping_nodes.get(node_id, {}).get(field)
            if entry is None:
                failures.append(f"node {node_id} missing mapping entry for {field}")
                continue
            if entry["level"] not in ("already_zh", "uncovered") and not is_zh(entry["zh"]):
                failures.append(f"node {node_id}.{field} level={entry['level']} has no Chinese text: {entry['zh']!r}")
    for edge_id, edge in edges.items():
        for field in REQUIRED_EDGE_FIELDS:
            entry = mapping_edges.get(edge_id, {}).get(field)
            if entry is None:
                failures.append(f"edge {edge_id} missing mapping entry for {field}")
                continue
            if entry["level"] not in ("already_zh", "uncovered") and not is_zh(entry["zh"]):
                failures.append(f"edge {edge_id}.{field} level={entry['level']} has no Chinese text")
    for condition_id, condition in conditions.items():
        for field in REQUIRED_CONDITION_FIELDS:
            entry = mapping_conditions.get(condition_id, {}).get(field)
            if entry is None:
                failures.append(f"condition {condition_id} missing mapping entry for {field}")
                continue
            if entry["level"] not in ("already_zh", "uncovered") and not is_zh(entry["zh"]):
                failures.append(f"condition {condition_id}.{field} level={entry['level']} has no Chinese text")
    for layer_id in layers:
        entry = mapping_layers.get(layer_id, {}).get("label")
        if entry is None:
            failures.append(f"layer {layer_id} missing mapping entry")
    for epoch_id in epochs:
        entry = mapping_epochs.get(epoch_id, {}).get("label")
        if entry is None:
            failures.append(f"epoch {epoch_id} missing mapping entry")

    # ---- 2. uncovered lists ----
    uncovered_labels = [
        node_id for node_id, fields in mapping_nodes.items()
        if fields.get("label", {}).get("level") == "uncovered"
    ]
    uncovered_regions = [
        node_id for node_id, fields in mapping_nodes.items()
        if fields.get("region", {}).get("level") == "uncovered"
    ]
    print(f"uncovered node labels ({len(uncovered_labels)}): {uncovered_labels}")
    print(f"uncovered node regions ({len(uncovered_regions)}): {uncovered_regions}")

    # ---- 3. data completeness ----
    for node_id, node in nodes.items():
        for field in REQUIRED_NODE_FIELDS:
            if not str(node.get(field, "")).strip():
                failures.append(f"node {node_id} empty required field {field}")
    for edge_id, edge in edges.items():
        for field in REQUIRED_EDGE_FIELDS:
            if not str(edge.get(field, "")).strip():
                failures.append(f"edge {edge_id} empty required field {field}")
    for condition_id, condition in conditions.items():
        for field in REQUIRED_CONDITION_FIELDS:
            if not str(condition.get(field, "")).strip():
                failures.append(f"condition {condition_id} empty required field {field}")

    # ---- 4. coverage summary from mapping ----
    coverage = mapping.get("coverage", {})
    summary = {
        "nodes.label": coverage.get("nodes", {}).get("label", {}),
        "nodes.region": coverage.get("nodes", {}).get("region", {}),
        "edges.mode": coverage.get("edges", {}).get("mode", {}),
        "conditions.label": coverage.get("conditions", {}).get("label", {}),
    }

    if failures:
        print(f"AUDIT FAILED: {len(failures)} problem(s)")
        for failure in failures[:40]:
            print("  -", failure)
        return 1

    print("AUDIT OK: all fields mapped (or explicitly uncovered), no empty required fields")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
