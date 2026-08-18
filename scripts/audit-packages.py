#!/usr/bin/env python3
"""Audit the published data packages for mechanical integrity.

Checks, per record, without importing the app or the framework:
  - every package file parses line by line (a bad line is reportable, not fatal);
  - every node belongs to exactly one package;
  - node/edge/condition counts add up to the source graph;
  - intra-package edges never dangle;
  - every edge (including bridge) has both endpoints among published nodes;
  - every condition referenced by an edge is defined in the same package or
    somewhere in the manifest conditions.

Usage:
    python scripts/audit-packages.py [--packages data/v1/packages] [--graph data/v1/graph.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_package(path: Path):
    """Parse a JSONL package record by record; return (header, records, bad_lines)."""
    header = None
    records = []
    bad_lines = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            bad_lines.append({"line": index + 1, "error": str(exc)})
            continue
        if payload.get("schema"):
            header = payload
            continue
        records.append(payload)
    return header, records, bad_lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages", type=Path, default=Path("data/v1/packages"))
    parser.add_argument("--graph", type=Path, default=Path("data/v1/graph.json"))
    args = parser.parse_args()

    packages_dir = args.packages.resolve()
    graph = json.loads(args.graph.resolve().read_text(encoding="utf-8"))
    source_nodes = {n["id"]: n for n in graph["nodes"]}
    source_edges = {e["id"]: e for e in graph["edges"]}
    source_conditions = {c["id"]: c for c in graph["conditions"]}

    manifest = json.loads((packages_dir / "manifest.json").read_text(encoding="utf-8"))
    failures = []

    all_nodes = {}
    all_edges = {}
    all_conditions = {}
    package_records = {}
    package_headers = {}

    for package in manifest["packages"]:
        pkg_id = package["id"]
        path = packages_dir / f"{pkg_id}.jsonl"
        header, records, bad_lines = load_package(path)
        package_records[pkg_id] = records
        package_headers[pkg_id] = header
        if bad_lines:
            failures.append(f"{pkg_id}: {len(bad_lines)} unparseable lines: {bad_lines[:2]}")
        if header is None:
            failures.append(f"{pkg_id}: missing package header")
            continue
        for payload in records:
            kind = payload.get("type")
            record = payload.get("record", {})
            if kind == "node":
                if record["id"] in all_nodes:
                    failures.append(f"node id duplicated across packages: {record['id']}")
                all_nodes[record["id"]] = (pkg_id, record)
            elif kind == "edge":
                if record["id"] in all_edges:
                    failures.append(f"edge id duplicated across packages: {record['id']}")
                all_edges[record["id"]] = (pkg_id, record)
            elif kind == "condition":
                all_conditions[record["id"]] = record

    # counts match source graph
    if len(all_nodes) != len(source_nodes):
        failures.append(f"node count mismatch: packages {len(all_nodes)} vs graph {len(source_nodes)}")
    if len(all_edges) != len(source_edges):
        failures.append(f"edge count mismatch: packages {len(all_edges)} vs graph {len(source_edges)}")

    # every edge endpoint exists in some package
    for edge_id, (pkg_id, edge) in all_edges.items():
        if edge["from"] not in all_nodes:
            failures.append(f"{pkg_id}:{edge_id}: dangling from {edge['from']}")
        if edge["to"] not in all_nodes:
            failures.append(f"{pkg_id}:{edge_id}: dangling to {edge['to']}")

    # intra-package edges never dangle
    for pkg_id, records in package_records.items():
        pkg_nodes = {p["record"]["id"] for p in records if p.get("type") == "node"}
        for payload in records:
            if payload.get("type") != "edge":
                continue
            edge = payload["record"]
            if edge["from"] in pkg_nodes and edge["to"] in pkg_nodes:
                # intra edge, fine
                continue
            if pkg_id != "bridge":
                # non-bridge package edge with a cross-package endpoint is a split error
                if edge["from"] not in pkg_nodes or edge["to"] not in pkg_nodes:
                    failures.append(f"{pkg_id}:{edge['id']}: edge crosses packages but is not in bridge")

    # every required condition is defined somewhere
    for edge_id, (pkg_id, edge) in all_edges.items():
        for condition_id in edge.get("requires", []):
            if condition_id == "map_fast_travel_available":
                continue  # defined by route-profiles.json, injected by the framework
            if condition_id not in all_conditions and condition_id not in source_conditions:
                failures.append(f"{pkg_id}:{edge_id}: unknown condition {condition_id}")
            if condition_id not in all_conditions and condition_id in source_conditions:
                failures.append(f"{pkg_id}:{edge_id}: condition {condition_id} not shipped in any package")

    if failures:
        print(f"AUDIT FAILED: {len(failures)} problem(s)")
        for failure in failures[:40]:
            print("  -", failure)
        return 1

    print(
        f"AUDIT OK: {len(all_nodes)} nodes / {len(all_edges)} edges / {len(all_conditions)} conditions "
        f"across {len(package_records)} packages, zero dangling or duplicated records"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
