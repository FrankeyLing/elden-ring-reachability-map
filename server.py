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
ACHIEVEMENTS_FILE = ROOT / "data" / "v1" / "entities" / "achievements.json"
ROUTE_LEGS_FILE = ROOT / "data" / "v1" / "entities" / "er-guide-route-legs.json"
ROUTE_TARGET_GROUPS_FILE = ROOT / "data" / "v1" / "entities" / "er-guide-route-target-groups.json"
ROUTE_PROFILES_FILE = ROOT / "data" / "v1" / "route-profiles.json"
ONLINE_GRACE_POSITION_FILE = ROOT / "data" / "v1" / "source-snapshots" / "mapforgoblins-grace-positions-20260818.json"
ONLINE_BOSS_POSITION_FILE = ROOT / "data" / "v1" / "source-snapshots" / "mapforgoblins-boss-positions-20260818.json"
ONLINE_MAP_CONVERSION_FILES = (
    ROOT / "data" / "v1" / "source-snapshots" / "mapforgoblins-map-conversions-base-20260818.json",
    ROOT / "data" / "v1" / "source-snapshots" / "mapforgoblins-map-conversions-dlc-20260818.json",
)
ONLINE_INDEX_MANIFEST_FILE = (
    ROOT / "data" / "v1" / "source-snapshots" / "mapforgoblins-online-index-20260818.json"
)
ONLINE_MAP_KEY_INDEX_FILE = (
    ROOT / "data" / "v1" / "source-snapshots" / "mapforgoblins-map-key-index-20260818.json"
)
ONLINE_MAP_POINT_FILES = tuple(
    ROOT / "data" / "v1" / "source-snapshots" / f"mapforgoblins-map-points-part{part}-20260818.json"
    for part in (1, 2, 3)
)
ONLINE_ITEM_FILES = tuple(
    ROOT / "data" / "v1" / "source-snapshots" / f"mapforgoblins-item-index-part{part}-20260818.json"
    for part in range(1, 31)
)
ONLINE_ENTITY_FILES = tuple(
    ROOT / "data" / "v1" / "source-snapshots" / f"mapforgoblins-entity-index-part{part}-20260818.json"
    for part in range(1, 23)
)
ONLINE_GATHERING_FILES = tuple(
    ROOT / "data" / "v1" / "source-snapshots" / f"mapforgoblins-gathering-index-part{part}-20260818.json"
    for part in range(1, 33)
)
ONLINE_ITEM_CACHE = None
ONLINE_ENTITY_CACHE = None
ONLINE_GATHERING_CACHE = None


def collection_item_evidence(record):
    """Return fixed online item positions for a collection record without creating route edges."""
    global ONLINE_ITEM_CACHE
    if record.get("category") != "collection":
        return []
    if ONLINE_ITEM_CACHE is None:
        ONLINE_ITEM_CACHE = decode_online_chunks(ONLINE_ITEM_FILES)
    aliases = record.get("online_name_aliases", {})
    name_to_requirement = {}
    for required_name in record.get("required_item_names", []):
        for candidate in [required_name, *aliases.get(required_name, [])]:
            name_to_requirement[str(candidate).casefold()] = required_name
    evidence = []
    for index, row in enumerate(ONLINE_ITEM_CACHE):
        matched_requirements = sorted(
            {
                name_to_requirement[str(item.get("name")).casefold()]
                for item in row[4]
                if item.get("name") and str(item.get("name")).casefold() in name_to_requirement
            }
        )
        if not matched_requirements:
            continue
        evidence.append(
            {
                "source_index": index,
                "map": row[0],
                "position": [row[1], row[2], row[3]],
                "items": row[4],
                "matched_requirements": matched_requirements,
                "category": row[5],
                "source": row[6],
                "guaranteed": row[7],
            }
        )
    return evidence


def decode_online_chunks(paths):
    chunks = [json.loads(path.read_bytes()) for path in paths]
    chunks.sort(key=lambda payload: payload["part"])
    expected_parts = chunks[0]["parts"] if chunks else 0
    if not chunks or expected_parts != len(chunks) or [chunk["part"] for chunk in chunks] != list(range(1, expected_parts + 1)):
        raise ValueError("online snapshot chunks are incomplete or out of order")
    encoded = "".join(chunk["chunk"] for chunk in chunks)
    return json.loads(zlib.decompress(base64.b64decode(encoded)).decode("utf-8"))


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
        if parsed.path == "/api/catalog/achievements":
            self.send_achievements(parse_qs(parsed.query))
            return
        if parsed.path == "/api/catalog/route-legs":
            self.send_json_file(ROUTE_LEGS_FILE)
            return
        if parsed.path == "/api/catalog/route-target-groups":
            self.send_json_file(ROUTE_TARGET_GROUPS_FILE)
            return
        if parsed.path == "/api/route-profiles":
            self.send_json_file(ROUTE_PROFILES_FILE)
            return
        if parsed.path == "/api/online-index":
            self.send_json_file(ONLINE_INDEX_MANIFEST_FILE)
            return
        if parsed.path == "/api/online-map-keys":
            self.send_json_file(ONLINE_MAP_KEY_INDEX_FILE)
            return
        if parsed.path == "/api/catalog/map-points":
            self.send_map_points(parse_qs(parsed.query))
            return
        if parsed.path == "/api/catalog/grace-positions":
            self.send_grace_positions(parse_qs(parsed.query))
            return
        if parsed.path == "/api/catalog/boss-positions":
            self.send_boss_positions(parse_qs(parsed.query))
            return
        if parsed.path == "/api/catalog/map-conversions":
            self.send_map_conversions(parse_qs(parsed.query))
            return
        if parsed.path == "/api/catalog/online-items":
            self.send_online_items(parse_qs(parsed.query))
            return
        if parsed.path == "/api/catalog/entities":
            self.send_entities(parse_qs(parsed.query))
            return
        if parsed.path == "/api/catalog/gathering":
            self.send_gathering(parse_qs(parsed.query))
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

    def send_achievements(self, query: dict[str, list[str]]):
        search = query.get("q", [""])[0].strip().casefold()
        category = query.get("category", [""])[0].strip().casefold()
        coverage_state = query.get("coverage", [""])[0].strip().casefold()
        try:
            limit = min(max(int(query.get("limit", ["100"])[0]), 1), 500)
        except ValueError:
            limit = 100
        try:
            payload = json.loads(ACHIEVEMENTS_FILE.read_bytes())
            records = []
            for record in payload["records"]:
                search_text = " / ".join(
                    str(value or "")
                    for value in (
                        record.get("canonical_id"),
                        record.get("name"),
                        record.get("description"),
                        *record.get("required_item_names", []),
                    )
                )
                if search and search not in search_text.casefold():
                    continue
                if category and str(record.get("category", "")).casefold() != category:
                    continue
                if coverage_state and str(record.get("coverage_state", "")).casefold() != coverage_state:
                    continue
                records.append(record)
            enriched_records = []
            text_location_evidence = payload.get("online_text_location_evidence", {})
            for record in records:
                enriched = dict(record)
                enriched["online_text_location_evidence"] = list(
                    text_location_evidence.get(enriched.get("canonical_id"), [])
                )
                if enriched.get("category") == "collection":
                    enriched["online_item_evidence"] = collection_item_evidence(enriched)
                enriched_records.append(enriched)
            records = enriched_records
        except (OSError, KeyError, TypeError, ValueError, zlib.error, json.JSONDecodeError) as exc:
            self.send_json_error(exc)
            return
        self.send_json_payload(
            {
                "schema": "elden-ring-reachability-map/achievement-query@1",
                "query": {"q": search, "category": category, "coverage": coverage_state, "limit": limit},
                "record_count": len(records[:limit]),
                "total_matches": len(records),
                "records": records[:limit],
                "routeable": False,
                "source": payload["source"],
                "online_item_evidence_source": {
                    "source_id": "map_for_goblins",
                    "commit": "324a895ba51d6091534578c2ce194d0c6720edc2",
                    "captured_on": "2026-08-18",
                },
                "note": "achievement targets are checklist evidence; they never become traversal edges automatically",
            }
        )

    def send_grace_positions(self, query: dict[str, list[str]]):
        map_id = query.get("map", [""])[0].strip()
        search = query.get("q", [""])[0].strip().casefold()
        include_dummy = query.get("include_dummy", ["0"])[0].strip().casefold() in {"1", "true", "yes"}
        try:
            limit = min(max(int(query.get("limit", ["500"])[0]), 1), 500)
        except ValueError:
            limit = 500

        def map_key(row):
            return f"m{int(row[1]):02d}_{int(row[2]):02d}_{int(row[3]):02d}"

        try:
            payload = json.loads(ONLINE_GRACE_POSITION_FILE.read_bytes())
            records = []
            for row in payload["records"]:
                row_map = map_key(row)
                region_text = " / ".join(str(value or "") for value in (row[8], row[10]))
                if row[11] and not include_dummy:
                    continue
                if map_id and not (row_map == map_id or row_map.startswith(map_id + "_")):
                    continue
                if search and search not in region_text.casefold():
                    continue
                records.append(
                    {
                        "source_index": row[0],
                        "map": row_map,
                        "area_no": row[1],
                        "grid_x": row[2],
                        "grid_z": row[3],
                        "position": [row[4], row[5], row[6]],
                        "sub_region": row[8],
                        "major_region": row[10],
                        "dummy": row[11],
                    }
                )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.send_json_error(exc)
            return
        self.send_json_payload(
            {
                "schema": "elden-ring-reachability-map/online-grace-position-query@1",
                "query": {"q": search, "map": map_id, "include_dummy": include_dummy, "limit": limit},
                "record_count": len(records[:limit]),
                "total_matches": len(records),
                "records": records[:limit],
                "routeable": False,
                "note": "raw online grace positions; the source index has no reliable grace names, so names are intentionally not guessed",
            }
        )

    def send_boss_positions(self, query: dict[str, list[str]]):
        map_id = query.get("map", [""])[0].strip()
        search = query.get("q", [""])[0].strip().casefold()
        try:
            limit = min(max(int(query.get("limit", ["500"])[0]), 1), 500)
        except ValueError:
            limit = 500
        try:
            payload = json.loads(ONLINE_BOSS_POSITION_FILE.read_bytes())
            records = []
            for row in payload["records"]:
                row_map = str(row[2] or "")
                if search and search not in str(row[1] or "").casefold():
                    continue
                if map_id and not (row_map == map_id or row_map.startswith(map_id + "_")):
                    continue
                records.append(
                    {
                        "source_index": row[0],
                        "name": row[1],
                        "map": row_map,
                        "area_no": row[3],
                        "grid_x": row[4],
                        "grid_z": row[5],
                        "position": [row[6], row[7], row[8]],
                        "model": row[9],
                        "formal_candidates": row[13] or [],
                    }
                )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.send_json_error(exc)
            return
        self.send_json_payload(
            {
                "schema": "elden-ring-reachability-map/online-boss-position-query@1",
                "query": {"q": search, "map": map_id, "limit": limit},
                "record_count": len(records[:limit]),
                "total_matches": len(records),
                "records": records[:limit],
                "routeable": False,
                "note": "raw online Boss coordinates; formal candidates are identity hints and do not create boss-gated traversal edges",
            }
        )

    def send_map_conversions(self, query: dict[str, list[str]]):
        map_id = query.get("map", [""])[0].strip()
        try:
            limit = min(max(int(query.get("limit", ["500"])[0]), 1), 500)
        except ValueError:
            limit = 500

        def map_key(area, grid_x, grid_z):
            if area is None or grid_x is None or grid_z is None:
                return None
            return f"m{int(area):02d}_{int(grid_x):02d}_{int(grid_z):02d}"

        try:
            records = []
            for path in ONLINE_MAP_CONVERSION_FILES:
                payload = json.loads(path.read_bytes())
                source_kind = "dlc" if "dlc" in path.name else "base"
                for row in payload["records"]:
                    source_map = map_key(row[1], row[2], row[3])
                    destination_map = map_key(row[7], row[8], row[9])
                    source_match = bool(source_map) and (not map_id or source_map == map_id or source_map.startswith(map_id + "_"))
                    destination_match = bool(destination_map) and (not map_id or destination_map == map_id or destination_map.startswith(map_id + "_"))
                    if not (source_match or destination_match):
                        continue
                    side = "source" if source_match else "destination"
                    position = [row[4], row[5], row[6]] if side == "source" else [row[10], row[11], row[12]]
                    records.append(
                        {
                            "source_index": row[0],
                            "dataset": source_kind,
                            "source_map": source_map,
                            "source_position": [row[4], row[5], row[6]],
                            "destination_map": destination_map,
                            "destination_position": [row[10], row[11], row[12]],
                            "current_map": map_id,
                            "current_side": side,
                            "position": position,
                            "is_base_point": bool(row[13]),
                        }
                    )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.send_json_error(exc)
            return
        self.send_json_payload(
            {
                "schema": "elden-ring-reachability-map/online-map-conversion-query@1",
                "query": {"map": map_id, "limit": limit},
                "record_count": len(records[:limit]),
                "total_matches": len(records),
                "records": records[:limit],
                "routeable": False,
                "note": "raw coordinate-conversion evidence only; it does not prove a walkable, one-way, elevator, coffin, portal, or boss-gated transition",
            }
        )

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
                ONLINE_ITEM_CACHE = decode_online_chunks(ONLINE_ITEM_FILES)
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

    def send_entities(self, query: dict[str, list[str]]):
        global ONLINE_ENTITY_CACHE
        search = query.get("q", [""])[0].strip().casefold()
        map_id = query.get("map", [""])[0].strip()
        kind = query.get("kind", [""])[0].strip().casefold()
        try:
            limit = min(max(int(query.get("limit", ["100"])[0]), 1), 500)
        except ValueError:
            limit = 100
        try:
            if ONLINE_ENTITY_CACHE is None:
                ONLINE_ENTITY_CACHE = decode_online_chunks(ONLINE_ENTITY_FILES)
            records = []
            for index, row in enumerate(ONLINE_ENTITY_CACHE):
                row_map = str(row[1] or "")
                row_kind = str(row[6] or "").casefold()
                search_text = " / ".join(str(value or "") for value in (row[0], row[5], row[7]))
                if search and search not in search_text.casefold():
                    continue
                if kind and row_kind != kind:
                    continue
                if map_id and not (row_map == map_id or row_map.startswith(map_id + "_")):
                    continue
                records.append(
                    {
                        "source_index": index,
                        "entity_id": row[0],
                        "map": row[1],
                        "position": [row[2], row[3], row[4]],
                        "model": row[5],
                        "kind": row[6],
                        "name": row[7],
                    }
                )
        except (OSError, KeyError, TypeError, ValueError, zlib.error, json.JSONDecodeError) as exc:
            self.send_json_error(exc)
            return
        self.send_json_payload(
            {
                "schema": "elden-ring-reachability-map/online-entity-query@1",
                "query": {"q": search, "map": map_id, "kind": kind, "limit": limit},
                "record_count": len(records[:limit]),
                "total_matches": len(records),
                "records": records[:limit],
                "routeable": False,
                "note": "online MSB entity coordinates; not a proof of a walkable route or enemy encounter state",
            }
        )

    def send_gathering(self, query: dict[str, list[str]]):
        global ONLINE_GATHERING_CACHE
        search = query.get("q", [""])[0].strip().casefold()
        map_id = query.get("map", [""])[0].strip()
        try:
            limit = min(max(int(query.get("limit", ["100"])[0]), 1), 500)
        except ValueError:
            limit = 100
        try:
            if ONLINE_GATHERING_CACHE is None:
                ONLINE_GATHERING_CACHE = decode_online_chunks(ONLINE_GATHERING_FILES)
            records = []
            for index, row in enumerate(ONLINE_GATHERING_CACHE):
                row_map = str(row[2] or "")
                search_text = " / ".join(str(value or "") for value in (row[0], row[1], row[10], row[11]))
                if search and search not in search_text.casefold():
                    continue
                if map_id and not (row_map == map_id or row_map.startswith(map_id + "_")):
                    continue
                records.append(
                    {
                        "source_index": index,
                        "model": row[0],
                        "name": row[1],
                        "map": row[2],
                        "area": row[3],
                        "position": [row[7], row[8], row[9]],
                        "entity_id": row[10],
                        "instance_id": row[11],
                    }
                )
        except (OSError, KeyError, TypeError, ValueError, zlib.error, json.JSONDecodeError) as exc:
            self.send_json_error(exc)
            return
        self.send_json_payload(
            {
                "schema": "elden-ring-reachability-map/online-gathering-query@1",
                "query": {"q": search, "map": map_id, "limit": limit},
                "record_count": len(records[:limit]),
                "total_matches": len(records),
                "records": records[:limit],
                "routeable": False,
                "note": "online gathering-node coordinates; not a proof of a walkable route or pickup availability state",
            }
        )

    def send_json_error(self, exc):
        body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json_payload(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
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
