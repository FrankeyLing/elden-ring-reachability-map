from __future__ import annotations

import argparse
import base64
import json
import os
import re
import zlib
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
ONLINE_QUERY_MAX = 1000
DATA_FILE = ROOT / "data" / "v1" / "graph.json"
PACKAGES_DIR = ROOT / "data" / "v1" / "packages"
PACKAGES_MANIFEST_FILE = PACKAGES_DIR / "manifest.json"
PACKAGE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
CATALOG_FILE = ROOT / "data" / "v1" / "entities" / "sites-of-grace.json"
ACHIEVEMENTS_FILE = ROOT / "data" / "v1" / "entities" / "achievements.json"
ROUTE_LEGS_FILE = ROOT / "data" / "v1" / "entities" / "er-guide-route-legs.json"
ROUTE_TARGET_GROUPS_FILE = ROOT / "data" / "v1" / "entities" / "er-guide-route-target-groups.json"
ROUTE_ASSESSMENTS_FILE = ROOT / "data" / "v1" / "entities" / "er-guide-route-assessments.json"
ROUTE_TARGET_ITEM_SNAPSHOT_FILES = {
    "er-guide-items-caelid-04-20260818": ROOT / "data" / "v1" / "source-snapshots" / "er-guide-items-caelid-04-20260818.json",
    "er-guide-items-caelid-06-20260818": ROOT / "data" / "v1" / "source-snapshots" / "er-guide-items-caelid-06-20260818.json",
    "er-guide-items-dlc-scadu-altus-01-20260818": ROOT / "data" / "v1" / "source-snapshots" / "er-guide-items-dlc-scadu-altus-01-20260818.json",
    "er-guide-items-dlc-scadu-altus-02-20260818": ROOT / "data" / "v1" / "source-snapshots" / "er-guide-items-dlc-scadu-altus-02-20260818.json",
    "er-guide-items-dlc-scadu-altus-04-20260818": ROOT / "data" / "v1" / "source-snapshots" / "er-guide-items-dlc-scadu-altus-04-20260818.json",
    "er-guide-items-dlc-scadu-altus-05-20260818": ROOT / "data" / "v1" / "source-snapshots" / "er-guide-items-dlc-scadu-altus-05-20260818.json",
    "er-guide-items-dlc-scadu-altus-07-20260818": ROOT / "data" / "v1" / "source-snapshots" / "er-guide-items-dlc-scadu-altus-07-20260818.json",
    "er-guide-items-dragonbarrow-02-20260818": ROOT / "data" / "v1" / "source-snapshots" / "er-guide-items-dragonbarrow-02-20260818.json",
}
ROUTE_PROFILES_FILE = ROOT / "data" / "v1" / "route-profiles.json"
ONLINE_GRACE_POSITION_FILE = ROOT / "data" / "v1" / "source-snapshots" / "mapforgoblins-grace-positions-20260818.json"
ONLINE_PROJECTED_GRACE_FILE = ROOT / "data" / "v1" / "source-snapshots" / "elden-ring-map-markers-20260818.json"
ONLINE_PROJECTED_GRACE_FILES = (
    ONLINE_PROJECTED_GRACE_FILE,
    *(ROOT / "data" / "v1" / "source-snapshots" / f"elden-ring-map-markers-supplement-{part:02d}-20260818.json" for part in range(1, 6)),
)
ONLINE_NAMED_GRACE_FILES = tuple(
    ROOT / "data" / "v1" / "source-snapshots" / f"elden-ring-compass-graces-{part:02d}-20260818.json"
    for part in range(1, 6)
)
NAMED_GRACE_IDENTITY_BINDINGS_FILE = ROOT / "data" / "v1" / "entities" / "named-grace-identity-bindings.json"
ONLINE_BOSS_POSITION_FILE = ROOT / "data" / "v1" / "source-snapshots" / "mapforgoblins-boss-positions-20260818.json"
BOSS_IDENTITY_BINDINGS_FILE = ROOT / "data" / "v1" / "entities" / "boss-identity-bindings.json"
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
NAMED_GRACE_IDENTITY_BINDINGS = None
BOSS_IDENTITY_BINDINGS = None
LOCAL_MSBE_INDEX_FILE = ROOT / "data" / "v1" / "entities" / "local-msbe-map-index.json"
LOCAL_MSBE_LAYER_FILE = ROOT / "data" / "v1" / "entities" / "local-msbe-layer-index.json"
LOCAL_TOPOLOGY_FILE = ROOT / "data" / "v1" / "entities" / "local-explicit-topology.json"
LOCAL_ABSTRACT_TOPOLOGY_FILE = ROOT / "data" / "v1" / "entities" / "local-abstract-entity-topology.json"
LOCAL_ABSTRACT_TOPOLOGY_GRAPH_FILE = ROOT / "data" / "v1" / "entities" / "local-abstract-topology-graph.json"
LOCAL_TRANSITION_AUDIT_FILE = ROOT / "data" / "v1" / "entities" / "local-transition-audit.json"
LOCAL_FMG_INDEX_FILE = ROOT / "data" / "v1" / "entities" / "local-fmg-semantic-index.json"
LOCAL_EMEVD_INDEX_FILE = ROOT / "data" / "v1" / "entities" / "local-emevd-semantic-index.json"
LOCAL_EMEVD_GUARD_TRACE_FILE = ROOT / "data" / "v1" / "entities" / "local-emevd-guard-traces.json"
LOCAL_EMEVD_GUARD_ATOM_FILE = ROOT / "data" / "v1" / "entities" / "local-emevd-guard-atoms.json"
LOCAL_EMEVD_GUARD_EXPRESSION_FILE = ROOT / "data" / "v1" / "entities" / "local-emevd-guard-expressions.json"
LOCAL_EMEVD_CONDITION_GROUP_SEMANTICS_FILE = ROOT / "data" / "v1" / "entities" / "local-emevd-condition-group-semantics.json"
LOCAL_GUARDED_TRANSITION_CANDIDATE_FILE = ROOT / "data" / "v1" / "entities" / "local-guarded-transition-candidates.json"
LOCAL_EMEVD_WARP_CANDIDATE_FILE = ROOT / "data" / "v1" / "entities" / "local-emevd-warp-candidates.json"
LOCAL_OBJACT_PARAM_FILE = ROOT / "data" / "v1" / "entities" / "local-objact-param-index.json"
LOCAL_NVA_FILE = ROOT / "data" / "v1" / "entities" / "local-nva-navmesh-index.json"
LOCAL_NVA_CONNECTIVITY_FILE = ROOT / "data" / "v1" / "entities" / "local-nva-connectivity-candidates.json"
LOCAL_NVA_BOUNDARY_PAIR_FILE = ROOT / "data" / "v1" / "entities" / "local-nva-boundary-pair-index.json"
LOCAL_NVA_COVERAGE_FILE = ROOT / "data" / "v1" / "entities" / "local-nva-coverage-audit.json"
LOCAL_MAP_COVERAGE_CLASSIFICATION_FILE = ROOT / "data" / "v1" / "entities" / "local-map-coverage-classification.json"
LOCAL_NVMHKTBND_FILE = ROOT / "data" / "v1" / "entities" / "local-nvmhktbnd-index.json"
LOCAL_NVMHKTBND_GEOMETRY_FILE = ROOT / "data" / "v1" / "entities" / "local-nvmhktbnd-hkx2-geometry-index.json"
LOCAL_NATIVE_TOPOLOGY_EVIDENCE_CHAIN_FILE = ROOT / "data" / "v1" / "entities" / "local-native-topology-evidence-chain.json"
LOCAL_NATIVE_TOPOLOGY_GRAPH_FILE = ROOT / "data" / "v1" / "entities" / "local-native-topology-graph.json"
LOCAL_NATIVE_MSBE_MODEL_BINDINGS_FILE = ROOT / "data" / "v1" / "entities" / "local-native-msbe-model-bindings.json"
LOCAL_MSBE_NATIVE_ENDPOINT_BINDINGS_FILE = ROOT / "data" / "v1" / "entities" / "local-msbe-native-endpoint-bindings.json"
LOCAL_MSBE_SNAPSHOT_ROOT = Path(
    os.environ.get(
        "ELDEN_RING_LOCAL_SNAPSHOT_ROOT",
        str(ROOT.parent.parent / "local-snapshots" / "elden-ring-20260818"),
    )
).resolve()
LOCAL_MSBE_MAP_ROOT = LOCAL_MSBE_SNAPSHOT_ROOT / "extracted" / "parsed-mapstudio-all-extra2" / "maps"
LOCAL_EMEVD_REFERENCE_ROOT = LOCAL_MSBE_SNAPSHOT_ROOT / "extracted" / "parsed-emevd-semantic" / "references"
LOCAL_ABSTRACT_TOPOLOGY_CACHE = None
LOCAL_ABSTRACT_TOPOLOGY_GRAPH_CACHE = None
LOCAL_TRANSITION_AUDIT_CACHE = None
LOCAL_MSBE_LAYER_CACHE = None
LOCAL_NVA_CACHE = None
LOCAL_MAP_COVERAGE_CLASSIFICATION_CACHE = None
LOCAL_NVA_CONNECTIVITY_CACHE = None
LOCAL_NVA_BOUNDARY_PAIR_CACHE = None
LOCAL_NVMHKTBND_CACHE = None
LOCAL_NVMHKTBND_GEOMETRY_CACHE = None
LOCAL_NATIVE_TOPOLOGY_EVIDENCE_CHAIN_CACHE = None
LOCAL_NATIVE_TOPOLOGY_GRAPH_CACHE = None
LOCAL_NATIVE_MSBE_MODEL_BINDINGS_CACHE = None
LOCAL_MSBE_NATIVE_ENDPOINT_BINDINGS_CACHE = None


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


def load_named_grace_identity_bindings():
    global NAMED_GRACE_IDENTITY_BINDINGS
    if NAMED_GRACE_IDENTITY_BINDINGS is None:
        payload = json.loads(NAMED_GRACE_IDENTITY_BINDINGS_FILE.read_bytes())
        NAMED_GRACE_IDENTITY_BINDINGS = {
            int(record["flag_id"]): record
            for record in payload.get("records", [])
        }
    return NAMED_GRACE_IDENTITY_BINDINGS


def enrich_named_grace_record(record, bindings):
    enriched = dict(record)
    binding = bindings.get(int(record["flag_id"]))
    if not binding:
        return enriched
    candidates = list(enriched.get("formal_candidates") or [])
    if binding["formal_id"] not in candidates:
        candidates.append(binding["formal_id"])
    enriched["formal_candidates"] = candidates
    enriched["formal_binding"] = {
        "formal_id": binding["formal_id"],
        "binding_basis": binding["binding_basis"],
        "identity_only": True,
        "routeable": False,
    }
    return enriched


def load_boss_identity_bindings():
    global BOSS_IDENTITY_BINDINGS
    if BOSS_IDENTITY_BINDINGS is None:
        payload = json.loads(BOSS_IDENTITY_BINDINGS_FILE.read_bytes())
        BOSS_IDENTITY_BINDINGS = {
            int(record["source_index"]): record
            for record in payload.get("records", [])
        }
    return BOSS_IDENTITY_BINDINGS


def enrich_boss_record(record, bindings):
    enriched = dict(record)
    binding = bindings.get(int(record["source_index"]))
    if not binding:
        return enriched
    candidates = list(enriched.get("formal_candidates") or [])
    if binding["formal_id"] not in candidates:
        candidates.append(binding["formal_id"])
    enriched["formal_candidates"] = candidates
    enriched["formal_binding"] = {
        "formal_id": binding["formal_id"],
        "binding_basis": binding["binding_basis"],
        "identity_only": True,
        "routeable": False,
    }
    return enriched


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
        if parsed.path == "/api/packages/manifest":
            self.send_json_file(PACKAGES_MANIFEST_FILE)
            return
        if parsed.path.startswith("/api/packages/"):
            package_id = parsed.path[len("/api/packages/"):]
            self.send_package_file(package_id)
            return
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
        if parsed.path == "/api/catalog/route-assessments":
            self.send_json_file(ROUTE_ASSESSMENTS_FILE)
            return
        if parsed.path == "/api/catalog/route-target-items":
            self.send_route_target_items(parse_qs(parsed.query))
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
        if parsed.path == "/api/local-msbe/index":
            self.send_json_file(LOCAL_MSBE_INDEX_FILE)
            return
        if parsed.path == "/api/local-msbe/layers":
            self.send_local_msbe_layers(parse_qs(parsed.query))
            return
        if parsed.path == "/api/local-nva/index":
            self.send_json_file(LOCAL_NVA_FILE)
            return
        if parsed.path == "/api/local-nva/map":
            self.send_local_nva_map(parse_qs(parsed.query))
            return
        if parsed.path == "/api/local-nva/connectivity":
            self.send_json_file(LOCAL_NVA_CONNECTIVITY_FILE)
            return
        if parsed.path == "/api/local-nva/boundary-pairs":
            self.send_json_file(LOCAL_NVA_BOUNDARY_PAIR_FILE)
            return
        if parsed.path == "/api/local-nva/boundary-pairs/map":
            self.send_local_nva_boundary_pairs_map(parse_qs(parsed.query))
            return
        if parsed.path == "/api/local-nva/coverage":
            self.send_json_file(LOCAL_NVA_COVERAGE_FILE)
            return
        if parsed.path == "/api/local-map-coverage/classification":
            self.send_json_file(LOCAL_MAP_COVERAGE_CLASSIFICATION_FILE)
            return
        if parsed.path == "/api/local-map-coverage/classification/map":
            self.send_local_map_coverage_classification_map(parse_qs(parsed.query))
            return
        if parsed.path == "/api/local-nvmhktbnd/index":
            self.send_json_file(LOCAL_NVMHKTBND_FILE)
            return
        if parsed.path == "/api/local-nvmhktbnd/map":
            self.send_local_nvmhktbnd_map(parse_qs(parsed.query))
            return
        if parsed.path == "/api/local-nvmhktbnd/hkx2-geometry":
            self.send_json_file(LOCAL_NVMHKTBND_GEOMETRY_FILE)
            return
        if parsed.path == "/api/local-nvmhktbnd/hkx2-geometry/map":
            self.send_local_nvmhktbnd_geometry_map(parse_qs(parsed.query))
            return
        if parsed.path == "/api/local-native-topology-evidence-chain":
            self.send_json_file(LOCAL_NATIVE_TOPOLOGY_EVIDENCE_CHAIN_FILE)
            return
        if parsed.path == "/api/local-native-topology-evidence-chain/map":
            self.send_local_native_topology_evidence_chain_map(parse_qs(parsed.query))
            return
        if parsed.path == "/api/local-native-topology-graph":
            self.send_json_file(LOCAL_NATIVE_TOPOLOGY_GRAPH_FILE)
            return
        if parsed.path == "/api/local-native-topology-graph/map":
            self.send_local_native_topology_graph_map(parse_qs(parsed.query))
            return
        if parsed.path == "/api/local-native-msbe-model-bindings":
            self.send_json_file(LOCAL_NATIVE_MSBE_MODEL_BINDINGS_FILE)
            return
        if parsed.path == "/api/local-native-msbe-model-bindings/map":
            self.send_local_native_msbe_model_bindings_map(parse_qs(parsed.query))
            return
        if parsed.path == "/api/local-msbe-native-endpoint-bindings":
            self.send_json_file(LOCAL_MSBE_NATIVE_ENDPOINT_BINDINGS_FILE)
            return
        if parsed.path == "/api/local-msbe-native-endpoint-bindings/map":
            self.send_local_msbe_native_endpoint_bindings_map(parse_qs(parsed.query))
            return
        if parsed.path == "/api/local-nva/connectivity/map":
            self.send_local_nva_connectivity_map(parse_qs(parsed.query))
            return
        if parsed.path == "/api/local-topology":
            self.send_json_file(LOCAL_TOPOLOGY_FILE)
            return
        if parsed.path == "/api/local-abstract-topology":
            self.send_json_file(LOCAL_ABSTRACT_TOPOLOGY_FILE)
            return
        if parsed.path == "/api/local-abstract-topology-graph":
            self.send_json_file(LOCAL_ABSTRACT_TOPOLOGY_GRAPH_FILE)
            return
        if parsed.path == "/api/local-abstract-topology-graph/map":
            self.send_local_abstract_topology_graph_map(parse_qs(parsed.query))
            return
        if parsed.path == "/api/local-abstract-topology/map":
            self.send_local_abstract_topology_map(parse_qs(parsed.query))
            return
        if parsed.path == "/api/local-transition-audit":
            self.send_json_file(LOCAL_TRANSITION_AUDIT_FILE)
            return
        if parsed.path == "/api/local-transition-audit/map":
            self.send_local_transition_audit_map(parse_qs(parsed.query))
            return
        if parsed.path == "/api/local-fmg/index":
            self.send_json_file(LOCAL_FMG_INDEX_FILE)
            return
        if parsed.path == "/api/local-msbe/map":
            self.send_local_msbe_map(parse_qs(parsed.query))
            return
        if parsed.path == "/api/local-emevd/index":
            self.send_json_file(LOCAL_EMEVD_INDEX_FILE)
            return
        if parsed.path == "/api/local-emevd/guard-traces":
            self.send_json_file(LOCAL_EMEVD_GUARD_TRACE_FILE)
            return
        if parsed.path == "/api/local-emevd/guard-atoms":
            self.send_json_file(LOCAL_EMEVD_GUARD_ATOM_FILE)
            return
        if parsed.path == "/api/local-emevd/guard-expressions":
            self.send_json_file(LOCAL_EMEVD_GUARD_EXPRESSION_FILE)
            return
        if parsed.path == "/api/local-emevd/condition-group-semantics":
            self.send_json_file(LOCAL_EMEVD_CONDITION_GROUP_SEMANTICS_FILE)
            return
        if parsed.path == "/api/local-emevd/warp-candidates":
            self.send_json_file(LOCAL_EMEVD_WARP_CANDIDATE_FILE)
            return
        if parsed.path == "/api/local-emevd/objact-param":
            self.send_json_file(LOCAL_OBJACT_PARAM_FILE)
            return
        if parsed.path == "/api/local-transition-audit/guarded-candidates":
            self.send_json_file(LOCAL_GUARDED_TRANSITION_CANDIDATE_FILE)
            return
        if parsed.path == "/api/local-emevd/map":
            self.send_local_emevd_map(parse_qs(parsed.query))
            return
        if parsed.path == "/api/catalog/map-points":
            self.send_map_points(parse_qs(parsed.query))
            return
        if parsed.path == "/api/catalog/grace-positions":
            self.send_grace_positions(parse_qs(parsed.query))
            return
        if parsed.path == "/api/catalog/named-grace-positions":
            self.send_named_grace_positions(parse_qs(parsed.query))
            return
        if parsed.path == "/api/catalog/projected-graces":
            self.send_projected_graces(parse_qs(parsed.query))
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

    def send_package_file(self, package_id: str):
        """Serve one JSONL data package. Package ids are strictly validated so
        a request can never escape the packages directory."""
        if not PACKAGE_ID_RE.fullmatch(package_id):
            self.send_json_error(ValueError(f"invalid package id: {package_id!r}"))
            return
        path = PACKAGES_DIR / f"{package_id}.jsonl"
        if not path.is_file():
            self.send_json_error(FileNotFoundError(f"package not found: {package_id}"))
            return
        try:
            payload = path.read_bytes()
        except OSError as exc:
            self.send_json_error(exc)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

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

    def send_local_msbe_map(self, query: dict[str, list[str]]):
        map_id = query.get("map_id", [""])[0].strip()
        if not re.fullmatch(r"m\d+_\d+_\d+_\d+", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid local MSBE map_id"))
            return
        path = LOCAL_MSBE_MAP_ROOT / f"{map_id}.json"
        if not path.is_file():
            self.send_json_error(FileNotFoundError(f"local MSBE map not found: {map_id}"))
            return
        self.send_json_file(path)

    def send_local_msbe_layers(self, query: dict[str, list[str]]):
        global LOCAL_MSBE_LAYER_CACHE
        map_id = query.get("map_id", [""])[0].strip()
        if map_id and not re.fullmatch(r"m\d+_\d+_\d+_\d+", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid local MSBE layer map_id"))
            return
        if LOCAL_MSBE_LAYER_CACHE is None:
            try:
                LOCAL_MSBE_LAYER_CACHE = json.loads(
                    LOCAL_MSBE_LAYER_FILE.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.send_json_error(exc)
                return
        data = LOCAL_MSBE_LAYER_CACHE
        records = [row for row in data.get("records", []) if not map_id or row.get("map_id") == map_id]
        map_coverage = [
            row
            for row in data.get("map_layer_coverage", [])
            if not map_id or row.get("map_id") == map_id
        ]
        self.send_json_payload(
            {
                "schema": "elden-ring-local-msbe-layer-index-query@1",
                "map_id": map_id or None,
                "records": records,
                "map_layer_coverage": map_coverage,
                "record_count": len(records),
                "distinct_layer_values": len({row.get("map_studio_layer") for row in records}),
                "model": data.get("model", {}),
                "routeable": False,
                "verification_state": "local_msbe_verified",
            }
        )

    def send_local_nva_map(self, query: dict[str, list[str]]):
        global LOCAL_NVA_CACHE
        map_id = query.get("map_id", [""])[0].strip()
        if not re.fullmatch(r"m\d+_\d+_\d+_\d+", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid local NVA map_id"))
            return
        if LOCAL_NVA_CACHE is None:
            try:
                LOCAL_NVA_CACHE = json.loads(LOCAL_NVA_FILE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                self.send_json_error(exc)
                return
        record = next(
            (row for row in LOCAL_NVA_CACHE.get("records", []) if row.get("map_id") == map_id),
            None,
        )
        if record is None:
            self.send_json_payload(
                {
                    "schema": "elden-ring-local-nva-navmesh-map@1",
                    "map_id": map_id,
                    "record_present": False,
                    "routeable": False,
                    "verification_state": "local_nva_file_absent",
                }
            )
            return
        self.send_json_payload(
            {
                "schema": "elden-ring-local-nva-navmesh-map@1",
                "map_id": map_id,
                "record_present": True,
                "record": record,
                "model": LOCAL_NVA_CACHE.get("model", {}),
                "routeable": False,
                "verification_state": "local_nva_oodle_decoded_exact",
            }
        )

    def send_local_map_coverage_classification_map(self, query: dict[str, list[str]]):
        global LOCAL_MAP_COVERAGE_CLASSIFICATION_CACHE
        map_id = query.get("map_id", [""])[0].strip()
        if not re.fullmatch(r"m\d+_\d+_\d+_\d+", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid local map coverage map_id"))
            return
        if LOCAL_MAP_COVERAGE_CLASSIFICATION_CACHE is None:
            try:
                LOCAL_MAP_COVERAGE_CLASSIFICATION_CACHE = json.loads(
                    LOCAL_MAP_COVERAGE_CLASSIFICATION_FILE.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.send_json_error(exc)
                return
        data = LOCAL_MAP_COVERAGE_CLASSIFICATION_CACHE
        record = next(
            (row for row in data.get("records", []) if row.get("map_id") == map_id),
            None,
        )
        self.send_json_payload(
            {
                "schema": "elden-ring-local-map-coverage-classification-map@1",
                "map_id": map_id,
                "record_present": record is not None,
                "record": record,
                "model": data.get("model", {}),
                "routeable": False,
                "verification_state": (
                    "local_map_coverage_classification_exact"
                    if record is not None
                    else "local_map_coverage_classification_absent"
                ),
            }
        )

    def send_local_nva_connectivity_map(self, query: dict[str, list[str]]):
        global LOCAL_NVA_CONNECTIVITY_CACHE
        map_id = query.get("map_id", [""])[0].strip()
        if not re.fullmatch(r"m\d+_\d+_\d+_\d+", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid local NVA connectivity map_id"))
            return
        if LOCAL_NVA_CONNECTIVITY_CACHE is None:
            try:
                LOCAL_NVA_CONNECTIVITY_CACHE = json.loads(
                    LOCAL_NVA_CONNECTIVITY_FILE.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.send_json_error(exc)
                return
        record = next(
            (row for row in LOCAL_NVA_CONNECTIVITY_CACHE.get("maps", []) if row.get("map_id") == map_id),
            None,
        )
        if record is None:
            self.send_json_payload(
                {
                    "schema": "elden-ring-local-nva-connectivity-map@1",
                    "map_id": map_id,
                    "record_present": False,
                    "routeable": False,
                    "verification_state": "local_nva_connectivity_candidate_absent",
                }
            )
            return
        self.send_json_payload(
            {
                "schema": "elden-ring-local-nva-connectivity-map@1",
                "map_id": map_id,
                "record_present": True,
                "record": record,
                "model": LOCAL_NVA_CONNECTIVITY_CACHE.get("model", {}),
                "routeable": False,
                "verification_state": "local_nva_connectivity_candidate_exact",
            }
        )

    def send_local_nva_boundary_pairs_map(self, query: dict[str, list[str]]):
        global LOCAL_NVA_BOUNDARY_PAIR_CACHE
        map_id = query.get("map_id", [""])[0].strip()
        if not re.fullmatch(r"m\d+_\d+_\d+_\d+", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid local NVA boundary-pair map_id"))
            return
        if LOCAL_NVA_BOUNDARY_PAIR_CACHE is None:
            try:
                LOCAL_NVA_BOUNDARY_PAIR_CACHE = json.loads(
                    LOCAL_NVA_BOUNDARY_PAIR_FILE.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.send_json_error(exc)
                return
        record = next(
            (
                row
                for row in LOCAL_NVA_BOUNDARY_PAIR_CACHE.get("maps", [])
                if row.get("map_id") == map_id
            ),
            None,
        )
        if record is None:
            self.send_json_payload(
                {
                    "schema": "elden-ring-local-nva-boundary-pair-map@1",
                    "map_id": map_id,
                    "record_present": False,
                    "routeable": False,
                    "verification_state": "local_nva_boundary_pair_map_absent",
                }
            )
            return
        self.send_json_payload(
            {
                "schema": "elden-ring-local-nva-boundary-pair-map@1",
                "map_id": map_id,
                "record_present": True,
                "record": record,
                "model": LOCAL_NVA_BOUNDARY_PAIR_CACHE.get("model", {}),
                "routeable": False,
                "verification_state": "local_nva_boundary_pair_exact_with_hkx2_conflict_audit",
            }
        )

    def send_local_nvmhktbnd_map(self, query: dict[str, list[str]]):
        global LOCAL_NVMHKTBND_CACHE
        map_id = query.get("map_id", [""])[0].strip()
        if not re.fullmatch(r"m\d+_\d+_\d+_\d+", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid local NVMHKT BND4 map_id"))
            return
        if LOCAL_NVMHKTBND_CACHE is None:
            try:
                LOCAL_NVMHKTBND_CACHE = json.loads(
                    LOCAL_NVMHKTBND_FILE.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.send_json_error(exc)
                return
        record = next(
            (row for row in LOCAL_NVMHKTBND_CACHE.get("records", []) if row.get("map_id") == map_id),
            None,
        )
        if record is None:
            self.send_json_payload(
                {
                    "schema": "elden-ring-local-nvmhktbnd-map@1",
                    "map_id": map_id,
                    "record_present": False,
                    "routeable": False,
                    "verification_state": "local_nvmhktbnd_file_absent",
                }
            )
            return
        self.send_json_payload(
            {
                "schema": "elden-ring-local-nvmhktbnd-map@1",
                "map_id": map_id,
                "record_present": True,
                "record": record,
                "model": LOCAL_NVMHKTBND_CACHE.get("model", {}),
                "routeable": False,
                "verification_state": "local_nvmhktbnd_bnd4_tag0_indexed",
            }
        )

    def send_local_nvmhktbnd_geometry_map(self, query: dict[str, list[str]]):
        global LOCAL_NVMHKTBND_GEOMETRY_CACHE
        map_id = query.get("map_id", [""])[0].strip()
        if not re.fullmatch(r"m\d+_\d+_\d+_\d+", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid local NVMHKT HKX2 geometry map_id"))
            return
        if LOCAL_NVMHKTBND_GEOMETRY_CACHE is None:
            try:
                LOCAL_NVMHKTBND_GEOMETRY_CACHE = json.loads(
                    LOCAL_NVMHKTBND_GEOMETRY_FILE.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.send_json_error(exc)
                return
        record = next(
            (
                row
                for row in LOCAL_NVMHKTBND_GEOMETRY_CACHE.get("records", [])
                if row.get("MapId") == map_id
            ),
            None,
        )
        if record is None:
            self.send_json_payload(
                {
                    "schema": "elden-ring-local-nvmhktbnd-hkx2-geometry-map@1",
                    "map_id": map_id,
                    "record_present": False,
                    "routeable": False,
                    "verification_state": "local_nvmhktbnd_geometry_record_absent",
                }
            )
            return
        self.send_json_payload(
            {
                "schema": "elden-ring-local-nvmhktbnd-hkx2-geometry-map@1",
                "map_id": map_id,
                "record_present": True,
                "record": record,
                "model": LOCAL_NVMHKTBND_GEOMETRY_CACHE.get("model", {}),
                "routeable": False,
                "verification_state": "local_nvmhktbnd_hkx2_geometry_deserialized",
            }
        )

    def send_local_native_topology_evidence_chain_map(self, query: dict[str, list[str]]):
        global LOCAL_NATIVE_TOPOLOGY_EVIDENCE_CHAIN_CACHE
        map_id = query.get("map_id", [""])[0].strip()
        if not re.fullmatch(r"m\d+_\d+_\d+_\d+", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid local native topology evidence map_id"))
            return
        if LOCAL_NATIVE_TOPOLOGY_EVIDENCE_CHAIN_CACHE is None:
            try:
                LOCAL_NATIVE_TOPOLOGY_EVIDENCE_CHAIN_CACHE = json.loads(
                    LOCAL_NATIVE_TOPOLOGY_EVIDENCE_CHAIN_FILE.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.send_json_error(exc)
                return
        record = next(
            (
                row
                for row in LOCAL_NATIVE_TOPOLOGY_EVIDENCE_CHAIN_CACHE.get("maps", [])
                if row.get("map_id") == map_id
            ),
            None,
        )
        if record is None:
            self.send_json_payload(
                {
                    "schema": "elden-ring-local-native-topology-evidence-chain-map@1",
                    "map_id": map_id,
                    "record_present": False,
                    "routeable": False,
                    "verification_state": "local_native_topology_evidence_map_absent",
                }
            )
            return
        self.send_json_payload(
            {
                "schema": "elden-ring-local-native-topology-evidence-chain-map@1",
                "map_id": map_id,
                "record_present": True,
                "record": record,
                "model": LOCAL_NATIVE_TOPOLOGY_EVIDENCE_CHAIN_CACHE.get("model", {}),
                "routeable": False,
                "verification_state": "local_native_nva_to_hkx2_evidence_chain_joined",
            }
        )

    def send_local_native_topology_graph_map(self, query: dict[str, list[str]]):
        global LOCAL_NATIVE_TOPOLOGY_GRAPH_CACHE
        map_id = query.get("map_id", [""])[0].strip()
        if not re.fullmatch(r"m\d+_\d+_\d+_\d+", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid local native topology graph map_id"))
            return
        if LOCAL_NATIVE_TOPOLOGY_GRAPH_CACHE is None:
            try:
                LOCAL_NATIVE_TOPOLOGY_GRAPH_CACHE = json.loads(
                    LOCAL_NATIVE_TOPOLOGY_GRAPH_FILE.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.send_json_error(exc)
                return
        data = LOCAL_NATIVE_TOPOLOGY_GRAPH_CACHE
        map_record = next(
            (row for row in data.get("maps", []) if row.get("map_id") == map_id),
            None,
        )
        nodes = [row for row in data.get("nodes", []) if row.get("map_id") == map_id]
        edges = [row for row in data.get("edges", []) if row.get("from_map_id") == map_id]
        connector_edges = [
            row for row in data.get("connector_edges", [])
            if row.get("from_map_id") == map_id
        ]
        cross_layer_relations = [
            row for row in data.get("cross_layer_relations", [])
            if row.get("from_map_id") == map_id
        ]
        if map_record is None:
            self.send_json_payload(
                {
                    "schema": "elden-ring-local-native-topology-graph-map@1",
                    "map_id": map_id,
                    "record_present": False,
                    "nodes": [],
                    "edges": [],
                    "connector_edges": [],
                    "cross_layer_relations": [],
                    "routeable": False,
                    "verification_state": "local_native_topology_graph_map_absent",
                }
            )
            return
        self.send_json_payload(
            {
                "schema": "elden-ring-local-native-topology-graph-map@1",
                "map_id": map_id,
                "record_present": True,
                "map": map_record,
                "nodes": nodes,
                "edges": edges,
                "connector_edges": connector_edges,
                "cross_layer_relations": cross_layer_relations,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "connector_edge_count": len(connector_edges),
                "cross_layer_relation_count": len(cross_layer_relations),
                "model": data.get("model", {}),
                "routeable": False,
                "verification_state": "local_native_nva_boundary_graph_exact",
            }
        )

    def send_local_native_msbe_model_bindings_map(self, query: dict[str, list[str]]):
        global LOCAL_NATIVE_MSBE_MODEL_BINDINGS_CACHE
        map_id = query.get("map_id", [""])[0].strip()
        if not re.fullmatch(r"m\d+_\d+_\d+_\d+", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid local native MSBE model binding map_id"))
            return
        if LOCAL_NATIVE_MSBE_MODEL_BINDINGS_CACHE is None:
            try:
                LOCAL_NATIVE_MSBE_MODEL_BINDINGS_CACHE = json.loads(
                    LOCAL_NATIVE_MSBE_MODEL_BINDINGS_FILE.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.send_json_error(exc)
                return
        data = LOCAL_NATIVE_MSBE_MODEL_BINDINGS_CACHE
        records = [row for row in data.get("records", []) if row.get("map_id") == map_id]
        map_record = next(
            (row for row in data.get("maps", []) if row.get("map_id") == map_id),
            None,
        )
        self.send_json_payload(
            {
                "schema": "elden-ring-local-native-msbe-model-bindings-map@1",
                "map_id": map_id,
                "record_present": map_record is not None,
                "map": map_record,
                "records": records,
                "record_count": len(records),
                "model": data.get("model", {}),
                "routeable": False,
                "verification_state": (
                    "local_native_to_msbe_model_identity_map_exact"
                    if map_record is not None
                    else "local_native_to_msbe_model_identity_map_absent"
                ),
            }
        )

    def send_local_msbe_native_endpoint_bindings_map(self, query: dict[str, list[str]]):
        global LOCAL_MSBE_NATIVE_ENDPOINT_BINDINGS_CACHE
        map_id = query.get("map_id", [""])[0].strip()
        if not re.fullmatch(r"m\d+_\d+_\d+_\d+", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid local MSBE native endpoint binding map_id"))
            return
        if LOCAL_MSBE_NATIVE_ENDPOINT_BINDINGS_CACHE is None:
            try:
                LOCAL_MSBE_NATIVE_ENDPOINT_BINDINGS_CACHE = json.loads(
                    LOCAL_MSBE_NATIVE_ENDPOINT_BINDINGS_FILE.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.send_json_error(exc)
                return
        data = LOCAL_MSBE_NATIVE_ENDPOINT_BINDINGS_CACHE
        records = [row for row in data.get("records", []) if row.get("map_id") == map_id]
        map_record = next(
            (row for row in data.get("maps", []) if row.get("map_id") == map_id),
            None,
        )
        self.send_json_payload(
            {
                "schema": "elden-ring-local-msbe-native-endpoint-bindings-map@1",
                "map_id": map_id,
                "record_present": map_record is not None,
                "map": map_record,
                "records": records,
                "record_count": len(records),
                "model": data.get("model", {}),
                "routeable": False,
                "verification_state": (
                    "local_msbe_connect_collision_to_nva_candidates_map_exact"
                    if map_record is not None
                    else "local_msbe_connect_collision_to_nva_candidates_map_absent"
                ),
            }
        )

    def send_local_emevd_map(self, query: dict[str, list[str]]):
        map_id = query.get("map_id", [""])[0].strip()
        if not re.fullmatch(r"(?:common(?:_func)?|m\d+_\d+_\d+_\d+)", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid local EMEVD map_id"))
            return
        path = LOCAL_EMEVD_REFERENCE_ROOT / f"{map_id}.json"
        if not path.is_file():
            self.send_json_payload(
                {
                    "schema": "elden-ring-local-emevd-semantic-references@1",
                    "map_key": map_id,
                    "reference_count": 0,
                    "references": [],
                    "verification_state": "local_emevd_file_absent",
                }
            )
            return
        self.send_json_file(path)

    def send_local_abstract_topology_map(self, query: dict[str, list[str]]):
        global LOCAL_ABSTRACT_TOPOLOGY_CACHE
        map_id = query.get("map_id", [""])[0].strip()
        if not re.fullmatch(r"m\d+_\d+_\d+_\d+", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid local abstract topology map_id"))
            return
        if LOCAL_ABSTRACT_TOPOLOGY_CACHE is None:
            try:
                LOCAL_ABSTRACT_TOPOLOGY_CACHE = json.loads(
                    LOCAL_ABSTRACT_TOPOLOGY_FILE.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.send_json_error(exc)
                return
        data = LOCAL_ABSTRACT_TOPOLOGY_CACHE
        map_node_id = f"local_map_{map_id}"
        map_node = next((node for node in data.get("nodes", []) if node.get("id") == map_node_id), None)
        if map_node is None:
            self.send_json_error(FileNotFoundError(f"local abstract topology map not found: {map_id}"))
            return
        candidate_nodes = [node for node in data.get("nodes", []) if node.get("map_id") == map_id]
        candidate_ids = {node.get("id") for node in candidate_nodes}
        structural_edges = [
            edge for edge in data.get("structural_edges", []) if edge.get("from") == map_node_id
        ]
        relations = [
            relation
            for relation in data.get("relations", [])
            if relation.get("from") in candidate_ids | {map_node_id}
            or relation.get("to") in candidate_ids | {map_node_id}
        ]
        self.send_json_payload(
            {
                "schema": "elden-ring-local-abstract-entity-topology-map@1",
                "map_id": map_id,
                "map": map_node,
                "candidate_nodes": candidate_nodes,
                "structural_edges": structural_edges,
                "relations": relations,
                "model": data.get("model", {}),
                "verification_state": "local_msbe_verified",
            }
        )

    def send_local_abstract_topology_graph_map(self, query: dict[str, list[str]]):
        global LOCAL_ABSTRACT_TOPOLOGY_GRAPH_CACHE
        map_id = query.get("map_id", [""])[0].strip()
        if not re.fullmatch(r"m\d+_\d+_\d+_\d+", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid local abstract topology graph map_id"))
            return
        if LOCAL_ABSTRACT_TOPOLOGY_GRAPH_CACHE is None:
            try:
                LOCAL_ABSTRACT_TOPOLOGY_GRAPH_CACHE = json.loads(
                    LOCAL_ABSTRACT_TOPOLOGY_GRAPH_FILE.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.send_json_error(exc)
                return
        data = LOCAL_ABSTRACT_TOPOLOGY_GRAPH_CACHE
        map_node_id = f"local_map_{map_id}"
        map_node = next((node for node in data.get("nodes", []) if node.get("id") == map_node_id), None)
        if map_node is None:
            self.send_json_error(FileNotFoundError(f"local abstract topology graph map not found: {map_id}"))
            return
        map_nodes = [node for node in data.get("nodes", []) if node.get("map_id") == map_id]
        node_ids = {node.get("id") for node in map_nodes} | {map_node_id}
        edges = [
            edge
            for edge in data.get("edges", [])
            if edge.get("from_map_id") == map_id
            or edge.get("to_map_id") == map_id
            or edge.get("from") in node_ids
            or edge.get("to") in node_ids
        ]
        referenced_node_ids = {
            node_id
            for edge in edges
            for node_id in (edge.get("from"), edge.get("to"))
            if node_id
        }
        extra_nodes = [
            node
            for node in data.get("nodes", [])
            if node.get("id") in referenced_node_ids and node.get("id") not in node_ids
        ]
        graph_nodes = map_nodes + extra_nodes
        relations = [
            relation
            for relation in data.get("relations", [])
            if relation.get("from") in node_ids or relation.get("to") in node_ids
        ]
        interaction_relations = [
            relation
            for relation in data.get("interaction_relations", [])
            if relation.get("from") in node_ids or relation.get("to") in node_ids
        ]
        interaction_mechanism_pair_relations = [
            relation
            for relation in data.get("interaction_mechanism_pair_relations", [])
            if relation.get("from") in node_ids or relation.get("to") in node_ids
        ]
        interaction_transport_relations = [
            relation
            for relation in data.get("interaction_transport_relations", [])
            if relation.get("from") in node_ids or relation.get("to") in node_ids
        ]
        interaction_relation_unresolved = [
            relation
            for relation in data.get("interaction_relation_unresolved", [])
            if relation.get("map_id") == map_id
        ]
        interaction_transport_unresolved = [
            relation
            for relation in data.get("interaction_transport_unresolved", [])
            if relation.get("map_id") == map_id
        ]
        interaction_map_identity_relations = [
            relation
            for relation in data.get("interaction_map_identity_relations", [])
            if relation.get("from_map_id") == map_id
            or relation.get("to_map_id") == map_id
            or relation.get("from") in node_ids
            or relation.get("to") in node_ids
        ]
        interaction_map_identity_unresolved = [
            relation
            for relation in data.get("interaction_map_identity_unresolved", [])
            if relation.get("map_id") == map_id
        ]
        native_identity_relations = [
            relation
            for relation in data.get("native_identity_relations", [])
            if relation.get("from") in node_ids or relation.get("to") in node_ids
        ]
        native_identity_layer_relations = [
            relation
            for relation in data.get("native_identity_layer_relations", [])
            if relation.get("from") in node_ids or relation.get("to") in node_ids
        ]
        objact_state_evidence = [
            evidence
            for evidence in data.get("objact_state_evidence", [])
            if evidence.get("map_id") == map_id
        ]
        structural_edges = [
            edge for edge in edges if edge.get("edge_family") == "native_msbe_map_declaration"
        ]
        self.send_json_payload(
            {
                "schema": "elden-ring-local-abstract-topology-graph-map@1",
                "map_id": map_id,
                "map": map_node,
                "candidate_nodes": [node for node in map_nodes if node.get("id") != map_node_id],
                "nodes": graph_nodes,
                "edges": edges,
                "structural_edges": structural_edges,
                "relations": relations,
                "layer_relations": [
                    relation
                    for relation in data.get("layer_relations", [])
                    if relation.get("from") in node_ids or relation.get("to") in node_ids
                ],
                "layer_membership_relations": [
                    relation
                    for relation in data.get("layer_membership_relations", [])
                    if relation.get("from") in node_ids or relation.get("to") in node_ids
                ],
                "layer_coverage": [
                    row
                    for row in data.get("layer_coverage", [])
                    if row.get("map_id") == map_id
                ],
                "interaction_relations": interaction_relations,
                "interaction_mechanism_pair_relations": interaction_mechanism_pair_relations,
                "interaction_relation_unresolved": interaction_relation_unresolved,
                "interaction_transport_relations": interaction_transport_relations,
                "interaction_transport_unresolved": interaction_transport_unresolved,
                "interaction_map_identity_relations": interaction_map_identity_relations,
                "interaction_map_identity_unresolved": interaction_map_identity_unresolved,
                "native_identity_relations": native_identity_relations,
                "native_identity_layer_relations": native_identity_layer_relations,
                "objact_state_evidence": objact_state_evidence,
                "status": data.get("status", {}),
                "model": data.get("model", {}),
                "verification_state": "local_msbe_verified_merged_abstract_topology",
            }
        )

    def send_local_transition_audit_map(self, query: dict[str, list[str]]):
        global LOCAL_TRANSITION_AUDIT_CACHE
        map_id = query.get("map_id", [""])[0].strip()
        if not re.fullmatch(r"m\d+_\d+_\d+_\d+", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid local transition audit map_id"))
            return
        if LOCAL_TRANSITION_AUDIT_CACHE is None:
            try:
                LOCAL_TRANSITION_AUDIT_CACHE = json.loads(
                    LOCAL_TRANSITION_AUDIT_FILE.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.send_json_error(exc)
                return
        data = LOCAL_TRANSITION_AUDIT_CACHE
        endpoint_pairs = [
            row
            for row in data.get("endpoint_pairs", [])
            if row.get("from", {}).get("map_id") == map_id
            or row.get("to", {}).get("map_id") == map_id
        ]
        scripted_warp_bindings = [
            row
            for row in data.get("scripted_warp_bindings", [])
            if row.get("from", {}).get("map_id") == map_id
            or row.get("to", {}).get("map_id") == map_id
        ]
        scripted_map_warp_bindings = [
            row
            for row in data.get("scripted_map_warp_bindings", [])
            if row.get("from", {}).get("map_id") == map_id
            or row.get("to", {}).get("map_id") == map_id
        ]
        interaction_candidates = [
            row for row in data.get("interaction_candidates", []) if row.get("map_id") == map_id
        ]
        self.send_json_payload(
            {
                "schema": "elden-ring-local-transition-audit-map@1",
                "map_id": map_id,
                "endpoint_pairs": endpoint_pairs,
                "scripted_warp_bindings": scripted_warp_bindings,
                "scripted_map_warp_bindings": scripted_map_warp_bindings,
                "interaction_candidates": interaction_candidates,
                "model": data.get("model", {}),
                "verification_state": "local_msbe_verified",
            }
        )

    def send_route_target_items(self, query: dict[str, list[str]]):
        snapshot = query.get("snapshot", [""])[0].strip()
        path = ROUTE_TARGET_ITEM_SNAPSHOT_FILES.get(snapshot)
        if path is None:
            self.send_json_error(ValueError("unknown route target item snapshot"))
            return
        self.send_json_file(path)

    def send_map_points(self, query: dict[str, list[str]]):
        search = query.get("q", [""])[0].strip().casefold()
        formal_id = query.get("formal_id", [""])[0].strip()
        try:
            limit = min(max(int(query.get("limit", ["100"])[0]), 1), ONLINE_QUERY_MAX)
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
            limit = min(max(int(query.get("limit", ["100"])[0]), 1), ONLINE_QUERY_MAX)
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
            limit = min(max(int(query.get("limit", ["500"])[0]), 1), ONLINE_QUERY_MAX)
        except ValueError:
            limit = ONLINE_QUERY_MAX

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

    def send_named_grace_positions(self, query: dict[str, list[str]]):
        map_id = query.get("map", [""])[0].strip()
        search = query.get("q", [""])[0].strip().casefold()
        formal_id = query.get("formal_id", [""])[0].strip()
        try:
            limit = min(max(int(query.get("limit", ["500"])[0]), 1), ONLINE_QUERY_MAX)
        except ValueError:
            limit = ONLINE_QUERY_MAX
        try:
            payloads = [json.loads(path.read_bytes()) for path in ONLINE_NAMED_GRACE_FILES]
            bindings = load_named_grace_identity_bindings()
            records = []
            for payload in payloads:
                for source_record in payload["records"]:
                    record = enrich_named_grace_record(source_record, bindings)
                    row_map = str(record.get("map") or "")
                    if map_id and not (row_map == map_id or row_map.startswith(map_id + "_")):
                        continue
                    if formal_id and formal_id not in (record.get("formal_candidates") or []):
                        continue
                    search_text = " / ".join(
                        str(value or "")
                        for value in (record.get("name"), record.get("region"), *(record.get("formal_candidates") or []))
                    )
                    if search and search not in search_text.casefold():
                        continue
                    records.append(record)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.send_json_error(exc)
            return
        self.send_json_payload(
            {
                "schema": "elden-ring-reachability-map/named-grace-position-query@1",
                "query": {"q": search, "map": map_id, "formal_id": formal_id, "limit": limit},
                "record_count": len(records[:limit]),
                "total_matches": len(records),
                "records": records[:limit],
                "routeable": False,
                "source": payloads[0]["source"],
                "snapshots": [payload["snapshot"] for payload in payloads],
                "coordinate_space": payloads[0]["coordinate_space"],
                "identity_binding_snapshot": "named-grace-identity-bindings@1",
                "identity_binding_count": len(bindings),
                "note": "named grace raw map-local entity XYZ evidence; this frame is not interchangeable with MapForGoblins coordinates; formal_candidates and formal_binding are identity links only and never create traversal edges",
            }
        )

    def send_projected_graces(self, query: dict[str, list[str]]):
        master = query.get("master", [""])[0].strip().upper()
        search = query.get("q", [""])[0].strip().casefold()
        formal_id = query.get("formal_id", [""])[0].strip()
        try:
            limit = min(max(int(query.get("limit", ["500"])[0]), 1), ONLINE_QUERY_MAX)
        except ValueError:
            limit = ONLINE_QUERY_MAX
        try:
            payloads = [json.loads(path.read_bytes()) for path in ONLINE_PROJECTED_GRACE_FILES]
            payload = payloads[0]
            records = []
            for source_payload in payloads:
                for record in source_payload["records"]:
                    if master and record.get("master") != master:
                        continue
                    if formal_id and record.get("formal_id") != formal_id:
                        continue
                    search_text = " / ".join(
                        str(value or "")
                        for value in (record.get("name"), record.get("description"), record.get("formal_id"))
                    )
                    if search and search not in search_text.casefold():
                        continue
                    records.append(record)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.send_json_error(exc)
            return
        self.send_json_payload(
            {
                "schema": "elden-ring-reachability-map/projected-grace-query@1",
                "query": {"q": search, "master": master, "formal_id": formal_id, "limit": limit},
                "record_count": len(records[:limit]),
                "total_matches": len(records),
                "records": records[:limit],
                "routeable": False,
                "source": payload["source"],
                "coordinate_space": payload["coordinate_space"],
                "snapshots": [source_payload["snapshot"] for source_payload in payloads],
                "note": "projected online pins only; formal_id is an identity link, not a game-world XYZ coordinate or traversal edge",
            }
        )

    def send_boss_positions(self, query: dict[str, list[str]]):
        map_id = query.get("map", [""])[0].strip()
        search = query.get("q", [""])[0].strip().casefold()
        formal_id = query.get("formal_id", [""])[0].strip()
        try:
            limit = min(max(int(query.get("limit", ["500"])[0]), 1), ONLINE_QUERY_MAX)
        except ValueError:
            limit = ONLINE_QUERY_MAX
        try:
            payload = json.loads(ONLINE_BOSS_POSITION_FILE.read_bytes())
            bindings = load_boss_identity_bindings()
            records = []
            for row in payload["records"]:
                row_map = str(row[2] or "")
                if search and search not in str(row[1] or "").casefold():
                    continue
                if map_id and not (row_map == map_id or row_map.startswith(map_id + "_")):
                    continue
                record = enrich_boss_record(
                    {
                        "source_index": row[0],
                        "name": row[1],
                        "map": row_map,
                        "area_no": row[3],
                        "grid_x": row[4],
                        "grid_z": row[5],
                        "position": [row[6], row[7], row[8]],
                        "model": row[9],
                        "npc_param_id": row[10],
                        "formal_candidates": row[13] or [],
                    },
                    bindings,
                )
                if formal_id and formal_id not in (record.get("formal_candidates") or []):
                    continue
                records.append(record)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.send_json_error(exc)
            return
        self.send_json_payload(
            {
                "schema": "elden-ring-reachability-map/online-boss-position-query@1",
                "query": {"q": search, "map": map_id, "formal_id": formal_id, "limit": limit},
                "record_count": len(records[:limit]),
                "total_matches": len(records),
                "records": records[:limit],
                "routeable": False,
                "identity_binding_snapshot": "boss-identity-bindings@1",
                "identity_binding_count": len(bindings),
                "note": "raw online Boss coordinates; formal candidates and formal_binding are identity evidence only and do not create boss-gated traversal edges",
            }
        )

    def send_map_conversions(self, query: dict[str, list[str]]):
        map_id = query.get("map", [""])[0].strip()
        try:
            limit = min(max(int(query.get("limit", ["500"])[0]), 1), ONLINE_QUERY_MAX)
        except ValueError:
            limit = ONLINE_QUERY_MAX

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
            limit = min(max(int(query.get("limit", ["100"])[0]), 1), ONLINE_QUERY_MAX)
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
            limit = min(max(int(query.get("limit", ["100"])[0]), 1), ONLINE_QUERY_MAX)
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
            limit = min(max(int(query.get("limit", ["100"])[0]), 1), ONLINE_QUERY_MAX)
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
