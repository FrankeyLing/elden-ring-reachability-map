from __future__ import annotations

import argparse
import base64
import json
import zlib
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "v1" / "graph.json"
CATALOG_FILE = ROOT / "data" / "v1" / "entities" / "sites-of-grace.json"
ROUTE_LEGS_FILE = ROOT / "data" / "v1" / "entities" / "er-guide-route-legs.json"
ROUTE_PROFILES_FILE = ROOT / "data" / "v1" / "route-profiles.json"
ONLINE_INDEX_MANIFEST_FILE = (
    ROOT / "data" / "v1" / "source-snapshots" / "mapforgoblins-online-index-20260818.json"
)
ONLINE_MAP_POINT_FILES = tuple(
    ROOT / "data" / "v1" / "source-snapshots" / f"mapforgoblins-map-points-part{part}-20260818.json"
    for part in (1, 2, 3)
)
ONLINE_ITEM_FILES = tuple(
    ROOT / "data" / "v1" / "source-snapshots" / f"mapforgoblins-item-index-part{part}-20260818.json"
    for part in range(1, 31)
)
ONLINE_ITEM_CACHE = None


class AppHandler(SimpleHTTPRequestHandler):
    """Small dependency-free server for the Online Verified V1 UI and data."""

    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".css": "text/css; charset=utf-8",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        if parsed.path == "/api/graph":
            self.send_json_file(DATA_FILE)
            return
        if parsed.path == "/api/catalog/sites-of-grace":
            self.send_json_file(CATALOG_FILE)
            return
        if parsed.path == "/api/catalog/route-legs":
            self.send_json_file(ROUTE_LEGS_FILE)
            return
        if parsed.path == "/api/route-profiles":
            self.send_json_file(ROUTE_PROFILES_FILE)
            return
        if parsed.path == "/api/online-index":
            self.send_json_file(ONLINE_INDEX_MANIFEST_FILE)
            return
        if parsed.path == "/api/catalog/map-points":
            self.send_map_points(parse_qs(parsed.query))
            return
        if parsed.path == "/api/catalog/online-items":
            self.send_online_items(parse_qs(parsed.query))
            return
        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def send_json_file(self, path: Path):
        try:
            payload = path.read_bytes()
            json.loads(payload)
        except (OSError, json.JSONDecodeError) as exc:
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_map_points(self, query: dict[str, list[str]]):
        search = query.get("q", [""])[0].strip().casefold()
        formal_id = query.get("formal_id", [""])[0].strip()
        try:
            limit = min(max(int(query.get("limit", ["100"])[0]), 1), 500)
        except ValueError:
            limit = 100

        records = []
        try:
            for path in ONLINE_MAP_POINT_FILES:
                payload = json.loads(path.read_bytes())
                for row in payload["records"]:
                    names = row[9] or []
                    candidates = row[10] or []
                    if search and search not in " / ".join(names).casefold():
                        continue
                    if formal_id and formal_id not in candidates:
                        continue
                    records.append(
                        {
                            "source_index": row[0],
                            "id": row[1],
                            "icon_id": row[2],
                            "area_no": row[3],
                            "grid_x": row[4],
                            "grid_z": row[5],
                            "position": [row[6], row[7], row[8]],
                            "names": names,
                            "formal_candidates": candidates,
                        }
                    )
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        response = {
            "schema": "elden-ring-reachability-map/online-map-points-query@1",
            "query": {"q": search, "formal_id": formal_id, "limit": limit},
            "record_count": len(records[:limit]),
            "total_matches": len(records),
            "records": records[:limit],
            "routeable": False,
            "note": "在线地图点坐标证据；不代表存在正式可通行边。",
        }
        body = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_online_items(self, query: dict[str, list[str]]):
        global ONLINE_ITEM_CACHE
        search = query.get("q", [""])[0].strip().casefold()
        category = query.get("category", [""])[0].strip().casefold()
        map_id = query.get("map", [""])[0].strip()
        source = query.get("source", [""])[0].strip().casefold()
        try:
            limit = min(max(int(query.get("limit", ["100"])[0]), 1), 500)
        except ValueError:
            limit = 100

        try:
            if ONLINE_ITEM_CACHE is None:
                chunks = []
                for path in ONLINE_ITEM_FILES:
                    chunks.append(json.loads(path.read_bytes()))
                chunks.sort(key=lambda payload: payload["part"])
                encoded = "".join(payload["chunk"] for payload in chunks)
                ONLINE_ITEM_CACHE = json.loads(
                    zlib.decompress(base64.b64decode(encoded)).decode("utf-8")
                )
            records = []
            for index, row in enumerate(ONLINE_ITEM_CACHE):
                item_text = json.dumps(row[4], ensure_ascii=False).casefold()
                if search and search not in item_text:
                    continue
                if category and str(row[5] or "").casefold() != category:
                    continue
                if map_id and not (
                    str(row[0] or "") == map_id
                    or str(row[0] or "").startswith(map_id + "_")
                ):
                    continue
                if source and str(row[6] or "").casefold() != source:
                    continue
                records.append(
                    {
                        "source_index": index,
                        "map": row[0],
                        "position": [row[1], row[2], row[3]],
                        "items": row[4],
                        "category": row[5],
                        "source": row[6],
                        "guaranteed": row[7],
                    }
                )
        except (OSError, KeyError, TypeError, ValueError, zlib.error, json.JSONDecodeError) as exc:
            body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        response = {
            "schema": "elden-ring-reachability-map/online-item-query@1",
            "query": {"q": search, "category": category, "map": map_id, "source": source, "limit": limit},
            "record_count": len(records[:limit]),
            "total_matches": len(records),
            "records": records[:limit],
            "routeable": False,
            "note": "在线物品/掉落坐标证据；不代表已建立从任意赐福到物品的正式可通行路线。",
        }
        body = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")


def main():
    parser = argparse.ArgumentParser(description="Run the RUNE//PATH WebUI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"RUNE//PATH running at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
