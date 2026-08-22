#!/usr/bin/env python3
"""Chapter-4 category vocabulary reachable through the live player search.

Contract 4.x page search: the category words themselves (地标/精英/联机/
祷告/漫步灵庙/...) must return real entities from the running server, not
only the offline index.  Run against the live server:

    python scripts/test-player-search-runtime.py --base http://127.0.0.1:8127
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request

# (query, minimum hits) - every chapter-4 vocabulary word must return at
# least one published entity from the runtime projection.
RUNTIME_QUERIES = [
    ("地标", 1), ("精英", 1), ("入侵者", 1), ("联机", 1), ("祷告", 1),
    ("魔法", 1), ("战灰", 1), ("护符", 1), ("铃珠", 1), ("制作笔记", 1),
    ("绘画", 1), ("表情动作", 1), ("追忆", 1), ("大卢恩", 1), ("骨灰", 1),
    ("地图残片", 1), ("石剑钥匙", 1), ("漫步灵庙", 1), ("神授塔", 1),
    ("灵泉", 1), ("传送机关", 1), ("暗门", 1), ("谜题", 1), ("固定留言", 1),
    ("锻造石", 1), ("铃兰", 1), ("墓地铃兰", 1), ("灵依墓地铃兰", 1),
    ("大朵墓地铃兰", 1), ("大朵灵依墓地铃兰", 1), ("圣杯露滴", 1),
    ("星光碎片", 1), ("死根", 1), ("龙心脏", 1), ("黄金种子", 1),
    ("记忆石", 1), ("泪滴幼体", 1), ("卢恩弯弧", 1), ("黄金卢恩", 1),
    ("英雄卢恩", 1), ("大龟裂壶", 1), ("炉像", 1), ("燃炉魔像", 1),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8127")
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()
    failures = []
    for query, floor in RUNTIME_QUERIES:
        params = urllib.parse.urlencode({"q": query, "limit": args.limit})
        try:
            with urllib.request.urlopen(
                f"{args.base}/api/catalog/player-entities?{params}", timeout=20
            ) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - report and fail
            failures.append(f"{query}: request failed ({exc})")
            continue
        total = int(data.get("total_matches") or 0)
        if total >= floor:
            print(f"  PASS {query} -> {total} matches")
        else:
            failures.append(f"{query}: {total} matches (floor {floor})")
    print(f"\nPLAYER SEARCH RUNTIME: {len(RUNTIME_QUERIES) - len(failures)}/{len(RUNTIME_QUERIES)} passed")
    for failure in failures:
        print(f"  - {failure}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
