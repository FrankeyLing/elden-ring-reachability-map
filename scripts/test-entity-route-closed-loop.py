#!/usr/bin/env python3
"""Player entity -> acquisition -> formal anchor -> route regression.

The fixture deliberately uses Bolt of Gransax because it is backed by a
verified acquisition endpoint that is part of the formal player route graph.
Map-only evidence paths and semantic pickup nodes must never satisfy this gate.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
PORT = 8128
BASE = f"http://127.0.0.1:{PORT}"


def get(path: str) -> dict:
    if "?" in path:
        prefix, query = path.split("?", 1)
        path = prefix + "?" + quote(query, safe="=&")
    request = Request(BASE + path, headers={"Accept": "application/json"})
    with urlopen(request, timeout=10) as response:
        assert response.status == 200, response.status
        return json.loads(response.read().decode("utf-8"))


def boot() -> subprocess.Popen:
    process = subprocess.Popen(
        [sys.executable, "server.py", "--port", str(PORT)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        try:
            if urlopen(BASE + "/api/packages/manifest", timeout=1).status == 200:
                return process
        except OSError:
            time.sleep(0.3)
    process.kill()
    raise RuntimeError("server did not start in time")


def main() -> int:
    server = boot()
    try:
        search = get("/api/catalog/player-entities?q=古兰桑克斯的雷电&limit=10")
        assert search["total_matches"] == 1, search
        assert search["records"][0]["id"] == "weapon_bolt_of_gransax", search

        detail = get("/api/catalog/player-entities?id=weapon_bolt_of_gransax")
        assert detail["found"] is True, detail
        acquisitions = detail["entity"].get("acquisitions", [])
        assert acquisitions, detail
        assert any(
            relation.get("topologyBinding", {}).get("status") == "routeable_anchor"
            and "item_bolt_of_gransax" in relation.get("topologyBinding", {}).get("routeNodeIds", [])
            for relation in acquisitions
        ), "Bolt acquisition is not bound to its formal route endpoint"

        topology = get("/api/catalog/player-entity-topology?id=weapon_bolt_of_gransax")
        assert topology["routeReady"] is True, topology
        assert topology["routeNodeIds"] == ["item_bolt_of_gransax"], topology
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    # scripts/e2e-route-regression.mjs independently exercises the same
    # framework store and HTTP packages used by the page. Its case 1 asserts
    # the exact five executable steps from the grace to this endpoint.
    print("PASS stage6 entity -> acquisition relation -> formal route anchor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
