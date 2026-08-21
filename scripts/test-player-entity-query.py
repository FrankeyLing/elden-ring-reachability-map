#!/usr/bin/env python3
"""End-to-end checks for the player entity/acquisition query projection."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent.parent
PORT = 8127
BASE = f"http://127.0.0.1:{PORT}"


def get(path: str) -> dict:
    with urlopen(BASE + path, timeout=5) as response:
        assert response.status == 200, response.status
        return json.loads(response.read().decode("utf-8"))


def query(**params: object) -> dict:
    return get("/api/catalog/player-entities?" + urlencode(params, doseq=True))


def topology_query(entity_id: str) -> dict:
    return get("/api/catalog/player-entity-topology?" + urlencode({"id": entity_id}))


def main() -> int:
    process = subprocess.Popen(
        [sys.executable, "server.py", "--port", str(PORT)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(40):
            try:
                get("/api/catalog/player-entities?q=%E9%93%83%E5%85%B0&limit=1")
                break
            except Exception:
                time.sleep(0.15)
        else:
            raise AssertionError("server did not start")

        glovewort = query(q="铃兰", limit=100)
        smithing = query(q="锻造石", limit=100)
        assert glovewort["total_matches"] > 0, glovewort
        assert smithing["total_matches"] > 0, smithing
        assert any(row["id"] == "item_grave_glovewort_1" for row in glovewort["records"])
        assert any(row["id"] == "item_smithing_stone_1" for row in smithing["records"])
        assert len({row["id"] for row in glovewort["records"]}) == len(glovewort["records"])
        assert not any(row["id"].startswith("accessory_") for row in glovewort["records"])

        common_drop = query(id="item_smithing_stone_1")
        assert common_drop["found"] is True
        drop_relations = [
            relation for relation in common_drop["entity"]["acquisitions"]
            if relation.get("method") == "drop"
        ]
        assert drop_relations, common_drop
        assert any(relation.get("endpointInstances") for relation in drop_relations), common_drop
        for relation in drop_relations:
            for endpoint in relation.get("endpointInstances", []):
                assert endpoint.get("map"), endpoint
                assert endpoint.get("part"), endpoint
                assert isinstance(endpoint.get("position"), dict), endpoint
                assert all(axis in endpoint["position"] for axis in ("x", "y", "z")), endpoint
                assert endpoint.get("npcParamId") is not None, endpoint

        detail = query(id="item_grave_glovewort_1")
        assert detail["found"] is True
        assert detail["entity"]["name"]["zh"] == "墓地铃兰【１】"
        assert detail["entity"]["counts"]["reinforcementIncoming"] > 0
        assert detail["entity"]["counts"]["acquisitions"] > 0
        assert detail["entity"]["topology"]["graphNodes"]
        glovewort_topology = topology_query("item_grave_glovewort_1")
        assert glovewort_topology["found"] is True
        assert glovewort_topology["bindings"]
        assert glovewort_topology["routeReady"] is False
        assert any(
            binding["binding"]["status"] in {"semantic_endpoint", "coordinate_endpoint"}
            for binding in glovewort_topology["bindings"]
        )

        routeable_entity_topology = topology_query("item_bolt_of_gransax")
        assert routeable_entity_topology["found"] is True
        assert routeable_entity_topology["routeReady"] is True
        assert "item_bolt_of_gransax" in routeable_entity_topology["routeNodeIds"]

        weapon = query(id="weapon_longsword")
        assert weapon["found"] is True
        assert any(
            item.get("variant") == "Fire"
            for acq in weapon["entity"]["acquisitions"]
            for item in acq.get("items", [])
        )

        shop_item = query(id="item_stonesword_key")
        assert shop_item["found"] is True
        purchases = [
            relation for relation in shop_item["entity"]["acquisitions"]
            if relation.get("method") == "purchase"
        ]
        assert purchases, shop_item
        assert any(
            relation.get("merchantShopBinding", {}).get("merchantName") == "Nomadic Merchant"
            and relation.get("endpointInstances")
            and relation["endpointInstances"][0].get("position")
            for relation in purchases
        ), purchases[:3]

        kale = query(q="咖列", limit=20)
        assert any(row["id"] == "npc_merchant_kal" for row in kale["records"]), kale
        kale_detail = query(id="npc_merchant_kal")
        assert kale_detail["found"] is True
        assert kale_detail["entity"]["counts"]["shopSales"] > 0, kale_detail

        missing = query(id="definitely_missing_entity")
        assert missing["found"] is False
        missing_topology = topology_query("definitely_missing_entity")
        assert missing_topology["found"] is False

        index = get("/api/catalog/player-entities?limit=1")
        assert index["stats"]["entityCount"] >= 9000
        print("PASS player entity query")
        print(f"  glovewort_matches={glovewort['total_matches']}")
        print(f"  smithing_matches={smithing['total_matches']}")
        print(f"  published_entities={index['stats']['entityCount']}")
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
