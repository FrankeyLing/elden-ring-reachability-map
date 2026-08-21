#!/usr/bin/env python3
"""Auto-layout the catalog-added grace nodes (x=0,y=0 pile) into their regions.

Each catalog grace is placed on a ring around its region's anchor point (the
centroid of the region's existing laid-out nodes). Ring radius grows with the
number of siblings so nodes never stack.

Usage:
    python scripts/layout-catalog-graces.py --graph data/v1/graph-v1.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=Path("data/v1/graph-v1.json"))
    args = parser.parse_args()

    path = args.graph.resolve()
    graph = json.loads(path.read_text(encoding="utf-8"))
    nodes = graph["nodes"]

    # region centroids from existing (non-catalog) nodes with real coordinates
    region_points = defaultdict(list)
    for node in nodes:
        if node.get("isCatalog"):
            continue
        x, y = node.get("x"), node.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            region_points[node.get("region", "")].append((x, y))

    region_anchor = {}
    for region, points in region_points.items():
        if points:
            region_anchor[region] = (
                sum(p[0] for p in points) / len(points),
                sum(p[1] for p in points) / len(points),
            )

    catalog_by_region = defaultdict(list)
    for node in nodes:
        if node.get("isCatalog"):
            catalog_by_region[node.get("region", "")].append(node)

    placed = 0
    for region, members in catalog_by_region.items():
        anchor = region_anchor.get(region)
        if not anchor:
            continue
        anchor_x, anchor_y = anchor
        for index, node in enumerate(members):
            x, y = node.get("x"), node.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)) and (x != 0 or y != 0):
                continue  # already laid out
            radius = 46 + 17 * (index // 12)
            angle = (index % 12) / 12 * 2 * math.pi + (index // 12) * 0.35
            node["x"] = round(anchor_x + radius * math.cos(angle), 1)
            node["y"] = round(anchor_y + radius * math.sin(angle), 1)
            placed += 1

    path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    print(f"placed {placed} catalog grace nodes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
