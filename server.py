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
ONLINE_PROJECTED_GRACE_FILE = None
ONLINE_PROJECTED_GRACE_FILES = ()
ONLINE_NAMED_GRACE_FILES = tuple(
    ROOT / "data" / "v1" / "source-snapshots" / f"elden-ring-compass-graces-{part:02d}-20260818.json"
    for part in range(1, 6)
)
LOCAL_GRACE_POSITIONS_FILE = ROOT / "data" / "v1" / "entities" / "local-grace-positions.json"
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
ABSTRACT_TOPOLOGY_CANDIDATES_FILE = ROOT / "data" / "v1" / "entities" / "abstract-topology-candidates.json"
ABSTRACT_TOPOLOGY_ROUTE_GRAPH_FILE = ROOT / "data" / "v1" / "entities" / "abstract-topology-route-graph.json"
ABSTRACT_TOPOLOGY_ENTITY_EDGE_LIMIT = 2000
ABSTRACT_ORIGIN_BINDINGS_FILE = ROOT / "data" / "v1" / "entities" / "abstract-origin-bindings.json"
ABSTRACT_NATIVE_TOPOLOGY_FILE = ROOT / "data" / "v1" / "entities" / "abstract-native-topology.json"
ACQUISITION_TOPOLOGY_BRIDGE_FILE = ROOT / "data" / "v1" / "entities" / "acquisition-topology-bridge.json"
PLAYER_ENTITY_INDEX_FILE = ROOT / "data" / "v1" / "entities" / "player-entity-index.json"
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
ABSTRACT_TOPOLOGY_CANDIDATES_CACHE = None
ABSTRACT_TOPOLOGY_ROUTE_GRAPH_CACHE = None
ABSTRACT_ORIGIN_BINDINGS_CACHE = None
ABSTRACT_NATIVE_TOPOLOGY_CACHE = None
ACQUISITION_TOPOLOGY_BRIDGE_CACHE = None
PLAYER_ENTITY_INDEX_CACHE = None
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


def sanitize_player_entity_payload(payload):
    """Keep valid entity records available when one record is malformed.

    A broken projection record is quarantined at the entity layer. A broken
    projection file remains a package-level failure, which is reported by the
    endpoint instead of being confused with a valid empty result.
    """
    entities = []
    quarantined = []
    for index, entity in enumerate(payload.get("entities", [])):
        valid = (
            isinstance(entity, dict)
            and isinstance(entity.get("id"), str)
            and bool(entity.get("id"))
            and isinstance(entity.get("name"), dict)
            and isinstance(entity.get("aliases", []), list)
            and isinstance(entity.get("topology", {}), dict)
            and isinstance(entity.get("acquisitions", []), list)
            and isinstance(entity.get("occurrences", []), list)
            and isinstance(entity.get("reinforcementIncoming", []), list)
            and isinstance(entity.get("reinforcementOutgoing", []), list)
        )
        if valid:
            entities.append(entity)
        else:
            quarantined.append({"index": index, "reason": "invalid_entity_record"})
    sanitized = dict(payload)
    sanitized["entities"] = entities
    sanitized["quarantine"] = quarantined
    stats = dict(payload.get("stats", {}))
    stats["quarantinedEntityCount"] = len(quarantined)
    stats["publishedEntityCount"] = len(entities)
    sanitized["stats"] = stats
    return sanitized


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
        if parsed.path == "/api/abstract-topology-candidates":
            self.send_json_file(ABSTRACT_TOPOLOGY_CANDIDATES_FILE)
            return
        if parsed.path == "/api/acquisition-topology-bridge/map":
            self.send_acquisition_topology_bridge_map(parse_qs(parsed.query))
            return
        if parsed.path == "/api/acquisition-topology-bridge/relation":
            self.send_acquisition_topology_bridge_relation(parse_qs(parsed.query))
            return
        if parsed.path == "/api/acquisition-topology-bridge":
            self.send_json_file(ACQUISITION_TOPOLOGY_BRIDGE_FILE)
            return
        if parsed.path == "/api/abstract-topology-candidates/path":
            self.send_abstract_topology_candidates_path(parse_qs(parsed.query))
            return
        if parsed.path == "/api/abstract-topology-route":
            self.send_abstract_topology_route(parse_qs(parsed.query))
            return
        if parsed.path == "/api/abstract-native-topology/map":
            self.send_abstract_native_topology_map(parse_qs(parsed.query))
            return
        if parsed.path == "/api/abstract-native-topology":
            self.send_json_file(ABSTRACT_NATIVE_TOPOLOGY_FILE)
            return
        if parsed.path == "/api/abstract-topology-candidates/map":
            self.send_abstract_topology_candidates_map(parse_qs(parsed.query))
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
        if parsed.path == "/api/catalog/player-entities":
            self.send_player_entities(parse_qs(parsed.query))
            return
        if parsed.path == "/api/catalog/player-entity-topology":
            self.send_player_entity_topology(parse_qs(parsed.query))
            return
        if parsed.path == "/api/catalog/player-entity-abstract-route":
            self.send_player_entity_abstract_route(parse_qs(parsed.query))
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

    def send_abstract_topology_candidates_map(self, query: dict[str, list[str]]):
        """Return one map's isolated candidate adjacency view.

        This endpoint exposes abstract connections for inspection and search.
        It never promotes a candidate to a formal route edge.
        """
        global ABSTRACT_TOPOLOGY_CANDIDATES_CACHE
        map_id = query.get("map_id", [""])[0].strip()
        if not re.fullmatch(r"m\d+_\d+_\d+_\d+", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid abstract topology candidate map_id"))
            return
        if ABSTRACT_TOPOLOGY_CANDIDATES_CACHE is None:
            try:
                ABSTRACT_TOPOLOGY_CANDIDATES_CACHE = json.loads(
                    ABSTRACT_TOPOLOGY_CANDIDATES_FILE.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.send_json_error(exc)
                return
        data = ABSTRACT_TOPOLOGY_CANDIDATES_CACHE
        node = next((row for row in data.get("nodes", []) if row.get("mapId") == map_id), None)
        if node is None:
            self.send_json_error(FileNotFoundError(f"abstract topology candidate map not found: {map_id}"))
            return
        adjacency = data.get("adjacency", {}).get(map_id, {})
        edge_ids = set(adjacency.get("outgoingEdgeIds", [])) | set(adjacency.get("incomingEdgeIds", []))
        edges = [edge for edge in data.get("edges", []) if edge.get("id") in edge_ids]
        transports = [row for row in data.get("transportRelations", []) if row.get("id") in edge_ids]
        layer_ids = set(node.get("layerIds", []))
        layers = [row for row in data.get("layers", []) if row.get("id") in layer_ids]
        layer_relations = [
            row for row in data.get("layerRelations", [])
            if row.get("fromMapId") == map_id or row.get("layerId") in layer_ids
        ]
        self.send_json_payload(
            {
                "schema": "elden-ring-abstract-topology-candidates-map@2",
                "mapId": map_id,
                "node": node,
                "layers": layers,
                "layerRelations": layer_relations,
                "adjacency": adjacency,
                "edges": edges,
                "transportRelations": transports,
                "routeable": False,
                "status": data.get("status"),
                "note": "候选连接仅用于抽象拓扑检索；未解析的方向、条件或端点不会被当作正式路线。",
            }
        )

    def send_abstract_topology_candidates_path(self, query: dict[str, list[str]]):
        """Trace a map-level abstract path without claiming a player route.

        Only identity-backed abstract connections are traversed. Runtime
        guards and player-space semantics remain warnings in the response.
        """
        global ABSTRACT_TOPOLOGY_CANDIDATES_CACHE
        from_map_id = query.get("from_map_id", [""])[0].strip()
        to_map_id = query.get("to_map_id", [""])[0].strip()
        map_pattern = r"m\d+_\d+_\d+_\d+"
        if not re.fullmatch(map_pattern, from_map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid abstract topology path from_map_id"))
            return
        if not re.fullmatch(map_pattern, to_map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid abstract topology path to_map_id"))
            return
        if ABSTRACT_TOPOLOGY_CANDIDATES_CACHE is None:
            try:
                ABSTRACT_TOPOLOGY_CANDIDATES_CACHE = json.loads(
                    ABSTRACT_TOPOLOGY_CANDIDATES_FILE.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.send_json_error(exc)
                return
        data = ABSTRACT_TOPOLOGY_CANDIDATES_CACHE
        maps = {row.get("mapId"): row for row in data.get("nodes", [])}
        if from_map_id not in maps or to_map_id not in maps:
            self.send_json_payload(
                {
                    "schema": "elden-ring-abstract-topology-candidates-path@1",
                    "found": False,
                    "fromMapId": from_map_id,
                    "toMapId": to_map_id,
                    "reason": "map_not_in_candidate_index",
                    "routeable": False,
                }
            )
            return
        edge_by_id = {
            row.get("id"): row
            for row in data.get("edges", []) + data.get("transportRelations", [])
        }
        adjacency = data.get("adjacency", {})
        predecessor: dict[str, tuple[str, str]] = {}
        queue = [from_map_id]
        visited = {from_map_id}
        while queue and to_map_id not in visited:
            current = queue.pop(0)
            for edge_id in adjacency.get(current, {}).get("abstractOutgoingEdgeIds", []):
                edge = edge_by_id.get(edge_id)
                target = edge.get("toMapId") if edge else None
                if not target or target in visited:
                    continue
                visited.add(target)
                predecessor[target] = (current, edge_id)
                queue.append(target)
                if target == to_map_id:
                    break
        if to_map_id not in visited:
            self.send_json_payload(
                {
                    "schema": "elden-ring-abstract-topology-candidates-path@1",
                    "found": False,
                    "fromMapId": from_map_id,
                    "toMapId": to_map_id,
                    "reason": "no_abstract_identity_backed_path",
                    "visitedMapCount": len(visited),
                    "routeable": False,
                    "note": "候选边和未解析条件不会被强行加入抽象路径。",
                }
            )
            return
        path_edge_ids = []
        path_map_ids = [to_map_id]
        current = to_map_id
        while current != from_map_id:
            previous, edge_id = predecessor[current]
            path_edge_ids.append(edge_id)
            path_map_ids.append(previous)
            current = previous
        path_edge_ids.reverse()
        path_map_ids.reverse()
        path_edges = [edge_by_id[edge_id] for edge_id in path_edge_ids]
        warnings = []
        for edge in path_edges:
            evidence = edge.get("evidence", {})
            blockers = evidence.get("blockers") or []
            guard = evidence.get("guard") or {}
            unresolved = guard.get("unresolved_reasons") or []
            if blockers or unresolved or evidence.get("conditionStatus") not in {None, ""}:
                warnings.append(
                    {
                        "edgeId": edge.get("id"),
                        "blockers": blockers,
                        "guardUnresolvedReasons": unresolved,
                        "conditionStatus": evidence.get("conditionStatus"),
                    }
                )
        self.send_json_payload(
            {
                "schema": "elden-ring-abstract-topology-candidates-path@1",
                "found": True,
                "fromMapId": from_map_id,
                "toMapId": to_map_id,
                "mapIds": path_map_ids,
                "maps": [maps[map_id] for map_id in path_map_ids],
                "edges": path_edges,
                "warnings": warnings,
                "routeable": False,
                "mode": "abstract_topology_evidence_trace",
                "note": "此路径表示抽象身份连接，不等于已验证的玩家可执行路线；正式路线仍只使用 routeNodeIds 和正式导航边。",
            }
        )

    def send_abstract_topology_route(self, query: dict[str, list[str]]):
        """Return a map-level abstract topology trace.

        This endpoint is intentionally separate from the formal player route
        engine. It can traverse identity-backed map connections, but it never
        claims continuous walkability or promotes an edge into graph-v1.
        """
        global ABSTRACT_TOPOLOGY_ROUTE_GRAPH_CACHE
        from_map_id = query.get("from_map_id", [""])[0].strip()
        to_map_id = query.get("to_map_id", [""])[0].strip()
        map_pattern = r"m\d+_\d+_\d+_\d+"
        if not re.fullmatch(map_pattern, from_map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid abstract topology route from_map_id"))
            return
        if not re.fullmatch(map_pattern, to_map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid abstract topology route to_map_id"))
            return
        try:
            max_hops = min(max(int(query.get("max_hops", ["2000"])[0]), 1), 5000)
        except ValueError:
            max_hops = 2000
        if ABSTRACT_TOPOLOGY_ROUTE_GRAPH_CACHE is None:
            try:
                ABSTRACT_TOPOLOGY_ROUTE_GRAPH_CACHE = json.loads(
                    ABSTRACT_TOPOLOGY_ROUTE_GRAPH_FILE.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.send_json_error(exc)
                return
        data = ABSTRACT_TOPOLOGY_ROUTE_GRAPH_CACHE
        map_nodes = {
            row.get("mapId"): row
            for row in data.get("nodes", [])
            if row.get("nodeType") == "abstract_map" and row.get("mapId")
        }
        if from_map_id not in map_nodes or to_map_id not in map_nodes:
            self.send_json_payload(
                {
                    "schema": "elden-ring-abstract-topology-route@1",
                    "found": False,
                    "fromMapId": from_map_id,
                    "toMapId": to_map_id,
                    "reason": "map_not_in_abstract_route_graph",
                    "abstractRouteable": False,
                    "routeable": False,
                }
            )
            return
        edge_by_id = {row.get("id"): row for row in data.get("edges", [])}
        adjacency = data.get("adjacency", {})
        predecessor: dict[str, tuple[str, str]] = {}
        queue = [from_map_id]
        visited = {from_map_id}
        while queue and to_map_id not in visited and len(visited) <= max_hops:
            current = queue.pop(0)
            for edge_id in adjacency.get(current, []):
                edge = edge_by_id.get(edge_id)
                target = edge.get("toMapId") if edge else None
                if not target or target in visited:
                    continue
                visited.add(target)
                predecessor[target] = (current, edge_id)
                queue.append(target)
                if target == to_map_id:
                    break
        base = {
            "schema": "elden-ring-abstract-topology-route@1",
            "fromMapId": from_map_id,
            "toMapId": to_map_id,
            "mode": "abstract_topology_route_evidence",
            "abstractRouteable": False,
            "playerRouteable": False,
            "routeable": False,
            "visitedMapCount": len(visited),
            "maxHops": max_hops,
        }
        if to_map_id not in visited:
            self.send_json_payload({
                **base,
                "found": False,
                "reason": "no_identity_backed_abstract_topology_path",
                "note": "未找到地图身份支持的抽象路径；这不等于连续物理不可达。",
            })
            return
        edge_ids = []
        map_ids = [to_map_id]
        current = to_map_id
        while current != from_map_id:
            previous, edge_id = predecessor[current]
            edge_ids.append(edge_id)
            map_ids.append(previous)
            current = previous
        edge_ids.reverse()
        map_ids.reverse()
        edges = [edge_by_id[edge_id] for edge_id in edge_ids]
        warnings = []
        for edge in edges:
            condition = edge.get("conditionStatus")
            evidence = edge.get("sourceEvidence") or {}
            blockers = evidence.get("blockers") or [] if isinstance(evidence, dict) else []
            if condition not in {None, "", "not_evaluated"} or blockers:
                warnings.append({
                    "edgeId": edge.get("id"),
                    "conditionStatus": condition,
                    "blockers": blockers,
                    "requires": edge.get("requires") or [],
                })
        self.send_json_payload({
            **base,
            "found": True,
            "mapIds": map_ids,
            "maps": [map_nodes[map_id] for map_id in map_ids],
            "edges": edges,
            "warnings": warnings,
            "abstractRouteable": True,
            "note": "这是地图/楼层身份拓扑轨迹，不是连续步行路线，也不会改变正式玩家路线图。",
        })

    def send_player_entity_abstract_route(self, query: dict[str, list[str]]):
        """Find abstract map paths to one entity's exact acquisition maps.

        The result is deliberately separate from the formal player route graph.
        It reports map-level topology evidence and keeps candidate, external,
        unresolved, and unbound endpoint coverage visible instead of silently
        converting those records into routes.
        """
        global ABSTRACT_TOPOLOGY_ROUTE_GRAPH_CACHE
        global ABSTRACT_ORIGIN_BINDINGS_CACHE
        entity_id = query.get("id", [""])[0].strip()
        from_map_id = query.get("from_map_id", [""])[0].strip()
        from_node_id = query.get("from_node_id", [""])[0].strip()
        target_map_id = query.get("target_map_id", [""])[0].strip()
        map_pattern = r"m\d+_\d+_\d+_\d+"
        if not entity_id:
            self.send_json_error(ValueError("player entity abstract route requires id"))
            return
        if not from_map_id and not from_node_id:
            self.send_json_error(ValueError("invalid player entity abstract route from_map_id"))
            return
        if target_map_id and not re.fullmatch(map_pattern, target_map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid player entity abstract route target_map_id"))
            return
        try:
            max_hops = min(max(int(query.get("max_hops", ["2000"])[0]), 1), 5000)
        except ValueError:
            max_hops = 2000
        try:
            max_paths = min(max(int(query.get("max_paths", ["20"])[0]), 1), 100)
        except ValueError:
            max_paths = 20
        try:
            payload = self.load_player_entity_index()
            canonical_entity_id = payload.get("entityAliases", {}).get(entity_id, entity_id)
            entity = next(
                (row for row in payload["entities"] if row.get("id") == canonical_entity_id),
                None,
            )
            schema = "elden-ring-reachability-map/player-entity-abstract-route@1"
            if entity is None:
                self.send_json_payload({
                    "schema": schema,
                    "found": False,
                    "entityId": entity_id,
                    "canonicalEntityId": None,
                    "reason": "entity_not_found",
                    "abstractRouteable": False,
                    "playerRouteable": False,
                    "routeable": False,
                })
                return
            origin_resolution = {
                "status": "explicit_map_id" if from_map_id else "unresolved",
                "formalNodeId": from_node_id or None,
                "mapId": from_map_id or None,
            }
            if from_node_id:
                if ABSTRACT_ORIGIN_BINDINGS_CACHE is None:
                    try:
                        ABSTRACT_ORIGIN_BINDINGS_CACHE = json.loads(
                            ABSTRACT_ORIGIN_BINDINGS_FILE.read_text(encoding="utf-8")
                        )
                    except (OSError, TypeError, ValueError, json.JSONDecodeError):
                        self.send_json_payload({
                            "schema": "elden-ring-reachability-map/player-entity-abstract-route@1",
                            "found": True,
                            "entityId": entity_id,
                            "canonicalEntityId": canonical_entity_id,
                            "fromNodeId": from_node_id,
                            "fromMapId": from_map_id or None,
                            "pathFound": False,
                            "reason": "origin_binding_package_unavailable",
                            "originResolution": {
                                "status": "origin_binding_package_unavailable",
                                "formalNodeId": from_node_id,
                            },
                            "abstractRouteable": False,
                            "playerRouteable": False,
                            "routeable": False,
                            "paths": [],
                        })
                        return
                origin_records = [
                    row for row in ABSTRACT_ORIGIN_BINDINGS_CACHE.get("records", [])
                    if row.get("formalNodeId") == from_node_id
                ]
                exact_origin_records = [
                    row for row in origin_records
                    if row.get("abstractOriginRouteable") is True
                ]
                exact_origin_map_ids = sorted({row.get("originMapId") for row in exact_origin_records})
                if len(exact_origin_map_ids) != 1:
                    candidate_rows = [
                        {
                            "id": row.get("id"),
                            "name": row.get("name"),
                            "originMapId": row.get("originMapId"),
                            "status": row.get("binding", {}).get("status"),
                            "abstractOriginRouteable": row.get("abstractOriginRouteable") is True,
                        }
                        for row in origin_records
                    ]
                    self.send_json_payload({
                        "schema": "elden-ring-reachability-map/player-entity-abstract-route@1",
                        "found": True,
                        "entityId": entity_id,
                        "canonicalEntityId": canonical_entity_id,
                        "fromNodeId": from_node_id,
                        "fromMapId": from_map_id or None,
                        "pathFound": False,
                        "reason": "origin_node_not_exactly_bound_to_one_abstract_map",
                        "originResolution": {
                            "status": (
                                "candidate_origin_identity"
                                if candidate_rows
                                else "unbound_origin_identity"
                            ),
                            "formalNodeId": from_node_id,
                            "candidateRecords": candidate_rows,
                        },
                        "abstractRouteable": False,
                        "playerRouteable": False,
                        "routeable": False,
                        "paths": [],
                    })
                    return
                resolved_map_id = exact_origin_map_ids[0]
                if from_map_id and from_map_id != resolved_map_id:
                    self.send_json_error(ValueError("from_node_id and from_map_id identify different abstract maps"))
                    return
                from_map_id = resolved_map_id
                origin_resolution = {
                    "status": "exact_formal_node_to_abstract_map",
                    "formalNodeId": from_node_id,
                    "mapId": from_map_id,
                    "bindingRecordIds": [row.get("id") for row in exact_origin_records],
                }
            if not re.fullmatch(map_pattern, from_map_id, flags=re.IGNORECASE):
                self.send_json_error(ValueError("invalid player entity abstract route from_map_id"))
                return
            if ABSTRACT_TOPOLOGY_ROUTE_GRAPH_CACHE is None:
                ABSTRACT_TOPOLOGY_ROUTE_GRAPH_CACHE = json.loads(
                    ABSTRACT_TOPOLOGY_ROUTE_GRAPH_FILE.read_text(encoding="utf-8")
                )
            route_data = ABSTRACT_TOPOLOGY_ROUTE_GRAPH_CACHE
            map_nodes = {
                row.get("mapId"): row
                for row in route_data.get("nodes", [])
                if row.get("nodeType") == "abstract_map" and row.get("mapId")
            }
            base = {
                "schema": schema,
                "found": True,
                "entityId": entity_id,
                "canonicalEntityId": canonical_entity_id,
                "fromNodeId": from_node_id or None,
                "fromMapId": from_map_id,
                "targetMapId": target_map_id or None,
                "originResolution": origin_resolution,
                "maxHops": max_hops,
                "maxPaths": max_paths,
                "abstractRouteable": False,
                "playerRouteable": False,
                "routeable": False,
            }
            if from_map_id not in map_nodes:
                self.send_json_payload({
                    **base,
                    "pathFound": False,
                    "reason": "origin_map_not_in_abstract_route_graph",
                    "targetMapCount": 0,
                    "paths": [],
                })
                return

            endpoint_groups: dict[str, list[dict[str, object]]] = {}
            endpoint_count = 0
            unbound_endpoint_count = 0
            candidate_endpoint_count = 0
            external_endpoint_count = 0
            unresolved_endpoint_count = 0

            def add_endpoint_reference(
                relation: dict[str, object],
                endpoint: dict[str, object] | None,
                endpoint_index: int | None,
                binding: dict[str, object],
            ) -> None:
                nonlocal endpoint_count
                nonlocal unbound_endpoint_count
                nonlocal candidate_endpoint_count
                nonlocal external_endpoint_count
                nonlocal unresolved_endpoint_count
                map_status = binding.get("mapBindingStatus")
                exact_map_ids = [
                    map_id for map_id in binding.get("mapIds", [])
                    if re.fullmatch(map_pattern, str(map_id), flags=re.IGNORECASE)
                ]
                candidate_map_ids = [
                    map_id for map_id in binding.get("mapCandidateIds", [])
                    if re.fullmatch(map_pattern, str(map_id), flags=re.IGNORECASE)
                ]
                if endpoint is not None or endpoint_index is not None:
                    endpoint_count += 1
                if exact_map_ids:
                    for map_id in exact_map_ids:
                        endpoint_groups.setdefault(map_id, []).append(
                            {
                                "relationId": relation.get("id"),
                                "method": relation.get("method"),
                                "endpointIndex": endpoint_index,
                                "endpointKind": (endpoint or {}).get("kind") or (endpoint or {}).get("spawnKind"),
                                "mapBindingStatus": map_status,
                            }
                        )
                    return
                if map_status == "candidate_map_instance" or candidate_map_ids:
                    candidate_endpoint_count += 1
                elif map_status in {"external_map_scope", "unresolved_map_scope"}:
                    external_endpoint_count += 1
                elif map_status in {"unresolved_map_instance", "map_index_unavailable"}:
                    unresolved_endpoint_count += 1
                else:
                    unbound_endpoint_count += 1

            for relation in entity.get("acquisitions", []):
                endpoints = relation.get("endpointInstances", [])
                if endpoints:
                    for endpoint_index, endpoint in enumerate(endpoints):
                        binding = endpoint.get("topologyBinding") or relation.get("topologyBinding") or {}
                        add_endpoint_reference(relation, endpoint, endpoint_index, binding)
                else:
                    binding = relation.get("topologyBinding") or {}
                    if binding.get("mapIds") or binding.get("mapCandidateIds"):
                        add_endpoint_reference(relation, None, None, binding)

            if target_map_id:
                endpoint_groups = {
                    target_map_id: endpoint_groups.get(target_map_id, [])
                }

            edge_by_id = {row.get("id"): row for row in route_data.get("edges", [])}
            adjacency = route_data.get("adjacency", {})
            predecessor: dict[str, tuple[str, str]] = {}
            queue = [from_map_id]
            visited = {from_map_id}
            queue_index = 0
            while queue_index < len(queue) and len(visited) <= max_hops:
                current = queue[queue_index]
                queue_index += 1
                for edge_id in adjacency.get(current, []):
                    edge = edge_by_id.get(edge_id)
                    target = edge.get("toMapId") if edge else None
                    if not target or target in visited:
                        continue
                    visited.add(target)
                    predecessor[target] = (current, edge_id)
                    queue.append(target)

            def build_path(target: str) -> tuple[list[str], list[dict[str, object]]]:
                edge_ids: list[str] = []
                map_ids = [target]
                current = target
                while current != from_map_id:
                    previous, edge_id = predecessor[current]
                    edge_ids.append(edge_id)
                    map_ids.append(previous)
                    current = previous
                edge_ids.reverse()
                map_ids.reverse()
                return map_ids, [edge_by_id[edge_id] for edge_id in edge_ids]

            target_statuses = []
            paths = []
            for map_id in sorted(endpoint_groups):
                references = endpoint_groups[map_id]
                reachable = map_id in visited
                in_graph = map_id in map_nodes
                status = {
                    "mapId": map_id,
                    "endpointCount": len(references),
                    "relationIds": sorted({row.get("relationId") for row in references if row.get("relationId")}),
                    "inAbstractRouteGraph": in_graph,
                    "reachable": reachable,
                    "abstractRouteable": reachable,
                    "playerRouteable": False,
                    "routeable": False,
                }
                if reachable:
                    map_ids, edges = build_path(map_id)
                    status["pathEdgeCount"] = len(edges)
                    if len(paths) < max_paths:
                        warnings = [
                            {
                                "edgeId": edge.get("id"),
                                "conditionStatus": edge.get("conditionStatus"),
                                "requires": edge.get("requires") or [],
                            }
                            for edge in edges
                            if edge.get("conditionStatus") not in {None, "", "not_evaluated"}
                            or edge.get("requires")
                        ]
                        paths.append(
                            {
                                "targetMapId": map_id,
                                "endpointCount": len(references),
                                "endpointReferenceCount": len(references),
                                "endpointReferences": references[:100],
                                "mapIds": map_ids,
                                "maps": [map_nodes[row] for row in map_ids],
                                "edges": edges,
                                "warnings": warnings,
                                "abstractRouteable": True,
                                "playerRouteable": False,
                                "routeable": False,
                            }
                        )
                elif not in_graph:
                    status["reason"] = "target_map_not_in_abstract_route_graph"
                else:
                    status["reason"] = "no_identity_backed_abstract_topology_path"
                target_statuses.append(status)

            reachable_target_count = sum(row["reachable"] for row in target_statuses)
            self.send_json_payload({
                **base,
                "pathFound": bool(paths),
                "visitedMapCount": len(visited),
                "targetMapCount": len(target_statuses),
                "reachableTargetMapCount": reachable_target_count,
                "unreachableTargetMapCount": len(target_statuses) - reachable_target_count,
                "endpointCount": endpoint_count,
                "unboundEndpointCount": unbound_endpoint_count,
                "candidateEndpointCount": candidate_endpoint_count,
                "externalEndpointCount": external_endpoint_count,
                "unresolvedEndpointCount": unresolved_endpoint_count,
                "targetMapStatuses": target_statuses,
                "paths": paths,
                "abstractRouteable": bool(paths),
                "playerRouteable": False,
                "routeable": False,
                "note": "这是从指定起始地图到实体精确获取地图端点的抽象拓扑证据路径；它不表示连续步行，也不会进入正式玩家路线图。",
            })
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.send_json_error(exc)

    def load_acquisition_topology_bridge(self):
        global ACQUISITION_TOPOLOGY_BRIDGE_CACHE
        if ACQUISITION_TOPOLOGY_BRIDGE_CACHE is None:
            ACQUISITION_TOPOLOGY_BRIDGE_CACHE = json.loads(
                ACQUISITION_TOPOLOGY_BRIDGE_FILE.read_text(encoding="utf-8")
            )
        return ACQUISITION_TOPOLOGY_BRIDGE_CACHE

    def send_acquisition_topology_bridge_map(self, query: dict[str, list[str]]):
        """Return acquisition endpoints scoped to one abstract map identity.

        This is a projection query only. It does not turn an acquisition
        endpoint into a player route node or infer an intra-map connection.
        """
        map_id = query.get("map_id", [""])[0].strip()
        if not re.fullmatch(r"m\d+_\d+_\d+_\d+", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid acquisition bridge map_id"))
            return
        try:
            limit = min(max(int(query.get("limit", ["1000"])[0]), 1), ONLINE_QUERY_MAX)
        except ValueError:
            limit = 1000
        method = query.get("method", [""])[0].strip()
        try:
            data = self.load_acquisition_topology_bridge()
            records = [
                row for row in data.get("records", [])
                if map_id in (row.get("abstractAnchor", {}).get("mapIds") or [])
                and (not method or row.get("method") == method)
            ]
            self.send_json_payload(
                {
                    "schema": "elden-ring-acquisition-topology-bridge-map@1",
                    "found": map_id in data.get("mapIndex", {}),
                    "mapId": map_id,
                    "map": data.get("mapIndex", {}).get(map_id),
                    "query": {"mapId": map_id, "method": method or None, "limit": limit},
                    "totalMatches": len(records),
                    "records": records[:limit],
                    "routeable": False,
                    "note": "获取终点到地图/层的证据投影；不等于地图内部可达路线。",
                }
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.send_json_error(exc)

    def send_acquisition_topology_bridge_relation(self, query: dict[str, list[str]]):
        """Return all bridge endpoints belonging to one acquisition relation."""
        relation_id = query.get("relation_id", [""])[0].strip()
        if not relation_id:
            self.send_json_error(ValueError("acquisition bridge relation_id is required"))
            return
        try:
            limit = min(max(int(query.get("limit", ["1000"])[0]), 1), ONLINE_QUERY_MAX)
        except ValueError:
            limit = 1000
        try:
            data = self.load_acquisition_topology_bridge()
            records = [
                row for row in data.get("records", [])
                if row.get("relationId") == relation_id
                or row.get("sourceRecordId") == relation_id
            ]
            self.send_json_payload(
                {
                    "schema": "elden-ring-acquisition-topology-bridge-relation@1",
                    "found": bool(records),
                    "relationId": relation_id,
                    "totalMatches": len(records),
                    "records": records[:limit],
                    "routeable": False,
                    "note": "关系终点桥接证据；正式路线资格仍由独立路线图决定。",
                }
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.send_json_error(exc)

    def send_abstract_native_topology_map(self, query: dict[str, list[str]]):
        """Return one map's native abstract partitions and identity bindings."""
        global ABSTRACT_NATIVE_TOPOLOGY_CACHE
        map_id = query.get("map_id", [""])[0].strip()
        if not re.fullmatch(r"m\d+_\d+_\d+_\d+", map_id, flags=re.IGNORECASE):
            self.send_json_error(ValueError("invalid abstract native topology map_id"))
            return
        if ABSTRACT_NATIVE_TOPOLOGY_CACHE is None:
            try:
                ABSTRACT_NATIVE_TOPOLOGY_CACHE = json.loads(
                    ABSTRACT_NATIVE_TOPOLOGY_FILE.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.send_json_error(exc)
                return
        data = ABSTRACT_NATIVE_TOPOLOGY_CACHE
        coverage = next(
            (row for row in data.get("mapCoverage", []) if row.get("mapId") == map_id),
            None,
        )
        if coverage is None:
            self.send_json_payload(
                {
                    "schema": "elden-ring-abstract-native-topology-map@1",
                    "found": False,
                    "mapId": map_id,
                    "reason": "map_not_in_native_coverage_index",
                    "routeable": False,
                }
            )
            return
        nodes = [row for row in data.get("nodes", []) if row.get("mapId") == map_id]
        node_ids = {row.get("id") for row in nodes}
        edges = [
            row for row in data.get("edges", [])
            if row.get("from") in node_ids or row.get("to") in node_ids
        ]
        bindings = [
            row for row in data.get("bindings", [])
            if row.get("fromMapId") == map_id or row.get("toMapId") == map_id
        ]
        self.send_json_payload(
            {
                "schema": "elden-ring-abstract-native-topology-map@1",
                "found": True,
                "mapId": map_id,
                "coverage": coverage,
                "nodes": nodes,
                "edges": edges,
                "bindings": bindings,
                "routeable": False,
                "note": "原生分区和身份映射是抽象拓扑证据，不是连续物理或已验证玩家步行路线。",
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
        """Grace positions datamined from the local MSBE copy (model AEG099_060).

        No third-party coordinate snapshot is involved; names are intentionally
        not guessed (the game files carry no grace display names)."""
        map_id = query.get("map", [""])[0].strip()
        search = query.get("q", [""])[0].strip().casefold()
        try:
            limit = min(max(int(query.get("limit", ["500"])[0]), 1), ONLINE_QUERY_MAX)
        except ValueError:
            limit = ONLINE_QUERY_MAX
        try:
            payload = json.loads(LOCAL_GRACE_POSITIONS_FILE.read_bytes())
            records = []
            for record in payload["records"]:
                row_map = str(record.get("map_id") or "")
                if map_id and not (row_map == map_id or row_map.startswith(map_id + "_")):
                    continue
                if search:
                    search_text = f"{row_map} {record.get('entity_id') or ''}".casefold()
                    if search not in search_text:
                        continue
                records.append(record)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.send_json_error(exc)
            return
        self.send_json_payload(
            {
                "schema": "elden-ring-reachability-map/local-grace-position-query@1",
                "query": {"q": search, "map": map_id, "limit": limit},
                "record_count": len(records[:limit]),
                "total_matches": len(records),
                "records": records[:limit],
                "routeable": False,
                "source": payload.get("source"),
                "coordinate_space": payload.get("source", {}).get("coordinate_space", "game_local_xyz"),
                "note": "grace positions datamined from the local MSBE copy (AEG099_060); game-local XYZ frame, no community snapshot involved; names are not guessed",
            }
        )

    def send_projected_graces(self, query: dict[str, list[str]]):
        """Removed: the projected-pixel snapshot came from an unlicensed
        third-party repository (jw-ofs/elden-ring-map) and was dropped when the
        project switched to self-datamined grace positions."""
        self.send_json_payload(
            {
                "schema": "elden-ring-reachability-map/projected-grace-query@1",
                "removed": True,
                "record_count": 0,
                "records": [],
                "note": "projected grace view removed: source markers.js had no license; use local-grace-positions (game-local XYZ) instead",
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

    def load_player_entity_index(self):
        global PLAYER_ENTITY_INDEX_CACHE
        if PLAYER_ENTITY_INDEX_CACHE is None:
            PLAYER_ENTITY_INDEX_CACHE = sanitize_player_entity_payload(
                json.loads(PLAYER_ENTITY_INDEX_FILE.read_bytes())
            )
        return PLAYER_ENTITY_INDEX_CACHE

    def send_player_entities(self, query: dict[str, list[str]]):
        """Serve the player-facing entity/acquisition projection.

        This endpoint is intentionally independent from route packages. An
        entity can be returned with a semantic-only or unbound topology state;
        that state is data shown to the player, not a reason to drop the entity
        from search.
        """
        search = query.get("q", [""])[0].strip().casefold()
        entity_id = query.get("id", [""])[0].strip()
        kind = query.get("kind", [""])[0].strip().casefold()
        category = query.get("category", [""])[0].strip().casefold()
        family = query.get("family", [""])[0].strip().casefold()
        try:
            limit = min(max(int(query.get("limit", ["100"])[0]), 1), ONLINE_QUERY_MAX)
        except ValueError:
            limit = 100

        try:
            payload = self.load_player_entity_index()
            entities = payload["entities"]
            if entity_id:
                canonical_entity_id = payload.get("entityAliases", {}).get(entity_id, entity_id)
                record = next((entity for entity in entities if entity.get("id") == canonical_entity_id), None)
                self.send_json_payload(
                    {
                        "schema": "elden-ring-reachability-map/player-entity-detail@1",
                        "found": record is not None,
                        "entity": record,
                        "requestedId": entity_id,
                        "canonicalEntityId": canonical_entity_id if record is not None else None,
                    }
                )
                return

            matches = []
            for entity in entities:
                if kind and str(entity.get("kind", "")).casefold() != kind:
                    continue
                if category and str(entity.get("category", "")).casefold() != category:
                    continue
                if family and str(entity.get("properties", {}).get("weaponFamily", "")).casefold() != family:
                    continue
                search_text = " ".join(
                    [
                        str(entity.get("id", "")),
                        *[str(value) for value in entity.get("name", {}).values()],
                        *[str(value) for value in entity.get("aliases", [])],
                        str(entity.get("category", "")),
                        str(entity.get("kind", "")),
                    ]
                ).casefold()
                if search and search not in search_text:
                    continue
                score = 0
                names = [str(value).casefold() for value in entity.get("name", {}).values()]
                if search and any(name == search for name in names):
                    score += 10
                if search and any(name.startswith(search) for name in names):
                    score += 5
                matches.append((score, entity))
            matches.sort(key=lambda item: (-item[0], item[1].get("name", {}).get("zh", ""), item[1]["id"]))

            records = []
            for _, entity in matches[:limit]:
                records.append(
                    {
                        "id": entity["id"],
                        "kind": entity.get("kind"),
                        "category": entity.get("category"),
                        "weaponFamily": entity.get("properties", {}).get("weaponFamily"),
                        "properties": {
                            "officialEnName": entity.get("properties", {}).get("officialEnName"),
                            "officialZhName": entity.get("properties", {}).get("officialZhName"),
                        },
                        "name": entity.get("name"),
                        "aliases": entity.get("aliases", [])[:8],
                        "sourceOnly": bool(entity.get("properties", {}).get("sourceOnly")),
                        "sourceStatus": entity.get("properties", {}).get("sourceStatus"),
                        "topologyStatus": entity.get("topology", {}).get("status", "not_bound"),
                        "counts": entity.get("counts", {}),
                    }
                )
            self.send_json_payload(
                {
                    "schema": "elden-ring-reachability-map/player-entity-query@1",
                    "query": {"q": search, "id": entity_id, "kind": kind, "category": category, "family": family, "limit": limit},
                    "record_count": len(records),
                    "total_matches": len(matches),
                    "records": records,
                    "stats": payload.get("stats", {}),
                    "coverageGaps": payload.get("coverageGaps", []),
                    "onlineSourceGaps": payload.get("onlineSourceGaps", []),
                    "verifiedNoDropFacts": payload.get("verifiedNoDropFacts", []),
                    "verifiedUnusedMapLotFacts": payload.get("verifiedUnusedMapLotFacts", []),
                    "sellerUnresolvedRecords": payload.get("sellerUnresolvedRecords", []),
                    "serviceMenuRecords": payload.get("serviceMenuRecords", []),
                    "testShopRowRecords": payload.get("testShopRowRecords", []),
                }
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.send_json_error(exc)

    def send_player_entity_topology(self, query: dict[str, list[str]]):
        """Expose the acquisition-to-topology bridge without fabricating edges.

        Acquisition records and route records remain independently usable. The
        response reports whether each acquisition endpoint is a formal route
        anchor, a semantic graph endpoint, a coordinate-only endpoint, or not
        bound. Only formal route anchors are eligible for route planning.
        """
        global ABSTRACT_TOPOLOGY_CANDIDATES_CACHE
        global ABSTRACT_TOPOLOGY_ROUTE_GRAPH_CACHE
        global ACQUISITION_TOPOLOGY_BRIDGE_CACHE
        entity_id = query.get("id", [""])[0].strip()
        try:
            if not entity_id:
                raise ValueError("player entity topology requires id")
            payload = self.load_player_entity_index()
            canonical_entity_id = payload.get("entityAliases", {}).get(entity_id, entity_id)
            entity = next((row for row in payload["entities"] if row.get("id") == canonical_entity_id), None)
            if entity is None:
                self.send_json_payload(
                    {
                        "schema": "elden-ring-reachability-map/player-entity-topology@1",
                        "found": False,
                        "entityId": entity_id,
                        "canonicalEntityId": None,
                        "bindings": [],
                        "routeNodeIds": [],
                    }
                )
                return
            bindings = []
            route_node_ids = {
                node.get("id")
                for node in entity.get("topology", {}).get("graphNodes", [])
                if node.get("routeable") and node.get("id")
            }
            for acquisition in entity.get("acquisitions", []):
                binding = acquisition.get("topologyBinding") or {
                    "status": "not_bound",
                    "routeNodeIds": [],
                    "semanticNodeIds": [],
                    "endpointInstanceCount": len(acquisition.get("endpointInstances", [])),
                    "reason": "该获取关系尚未生成拓扑绑定状态",
                }
                route_node_ids.update(binding.get("routeNodeIds", []))
                bindings.append(
                    {
                        "relationId": acquisition.get("id"),
                        "method": acquisition.get("method"),
                        "binding": binding,
                        "endpointInstances": acquisition.get("endpointInstances", []),
                    }
                )
            bridge_projection = {
                "status": "unavailable",
                "records": [],
                "statusCounts": {},
                "routeable": False,
            }
            try:
                if ACQUISITION_TOPOLOGY_BRIDGE_CACHE is None:
                    ACQUISITION_TOPOLOGY_BRIDGE_CACHE = json.loads(
                        ACQUISITION_TOPOLOGY_BRIDGE_FILE.read_text(encoding="utf-8")
                    )
                relation_ids = {
                    row.get("relationId")
                    for row in bindings
                    if row.get("relationId")
                }
                bridge_records = [
                    row for row in ACQUISITION_TOPOLOGY_BRIDGE_CACHE.get("records", [])
                    if row.get("relationId") in relation_ids
                ]
                status_counts = {}
                for row in bridge_records:
                    status = row.get("abstractAnchor", {}).get("status", "unbound")
                    status_counts[status] = status_counts.get(status, 0) + 1
                bridge_projection = {
                    "status": "acquisition_endpoint_bridge_evidence_only",
                    "records": [
                        {
                            "id": row.get("id"),
                            "relationId": row.get("relationId"),
                            "method": row.get("method"),
                            "endpointKind": row.get("endpointKind"),
                            "abstractAnchor": row.get("abstractAnchor"),
                            "semanticGraphAnchor": row.get("semanticGraphAnchor"),
                            "localPartSemanticAnchor": row.get("localPartSemanticAnchor"),
                            "localEndpointIdentity": row.get("localEndpointIdentity"),
                            "nativeIdentity": row.get("nativeIdentity"),
                            "formalRouteAnchor": row.get("formalRouteAnchor"),
                            "routeable": False,
                        }
                        for row in bridge_records
                    ],
                    "statusCounts": status_counts,
                    "routeable": False,
                }
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                # The player entity projection remains usable if this optional
                # bridge package is missing or malformed.
                pass
            candidate_map_ids = set()
            for acquisition in entity.get("acquisitions", []):
                binding = acquisition.get("topologyBinding") or {}
                candidate_map_ids.update(binding.get("mapIds", []))
                candidate_map_ids.update(binding.get("mapCandidateIds", []))
                for endpoint in acquisition.get("endpointInstances", []):
                    endpoint_binding = endpoint.get("topologyBinding") or {}
                    candidate_map_ids.update(endpoint_binding.get("mapIds", []))
                    candidate_map_ids.update(endpoint_binding.get("mapCandidateIds", []))
            candidate_topology = {
                "status": "unavailable",
                "mapIds": sorted(
                    map_id
                    for map_id in candidate_map_ids
                    if re.fullmatch(r"m\d+_\d+_\d+_\d+", str(map_id), flags=re.IGNORECASE)
                ),
                "maps": [],
                "layers": [],
                "layerRelations": [],
                "edges": [],
                "transportRelations": [],
                "abstractConnectedEdgeCount": 0,
                "abstractUnresolvedEdgeCount": 0,
                "routeable": False,
            }
            try:
                if ABSTRACT_TOPOLOGY_CANDIDATES_CACHE is None:
                    ABSTRACT_TOPOLOGY_CANDIDATES_CACHE = json.loads(
                        ABSTRACT_TOPOLOGY_CANDIDATES_FILE.read_text(encoding="utf-8")
                    )
                candidate_data = ABSTRACT_TOPOLOGY_CANDIDATES_CACHE
                selected_maps = [
                    row for row in candidate_data.get("nodes", [])
                    if row.get("mapId") in candidate_topology["mapIds"]
                ]
                selected_layer_ids = {
                    layer_id
                    for row in selected_maps
                    for layer_id in row.get("layerIds", [])
                }
                selected_edge_ids = set()
                for map_id in candidate_topology["mapIds"]:
                    selected_edge_ids.update(
                        candidate_data.get("adjacency", {}).get(map_id, {}).get("outgoingEdgeIds", [])
                    )
                    selected_edge_ids.update(
                        candidate_data.get("adjacency", {}).get(map_id, {}).get("incomingEdgeIds", [])
                    )
                candidate_topology.update(
                    {
                        "status": "candidate_evidence_only",
                        "maps": selected_maps,
                        "layers": [
                            row for row in candidate_data.get("layers", [])
                            if row.get("id") in selected_layer_ids
                        ],
                        "layerRelations": [
                            row for row in candidate_data.get("layerRelations", [])
                            if row.get("fromMapId") in candidate_topology["mapIds"]
                            or row.get("layerId") in selected_layer_ids
                        ],
                        "edges": [
                            row for row in candidate_data.get("edges", [])
                            if row.get("id") in selected_edge_ids
                        ],
                        "transportRelations": [
                            row for row in candidate_data.get("transportRelations", [])
                            if row.get("id") in selected_edge_ids
                        ],
                        "abstractConnectedEdgeCount": sum(
                            row.get("abstractConnected") is True
                            for row in candidate_data.get("edges", [])
                            if row.get("id") in selected_edge_ids
                        ),
                        "abstractUnresolvedEdgeCount": sum(
                            row.get("abstractConnected") is not True
                            for row in candidate_data.get("edges", [])
                            if row.get("id") in selected_edge_ids
                        ),
                    }
                )
            except (OSError, json.JSONDecodeError, TypeError):
                # The player entity projection remains usable if this optional
                # candidate package is missing or malformed.
                pass
            abstract_route_evidence = {
                "status": "unavailable",
                "requestedMapIds": candidate_topology["mapIds"],
                "mapIds": [],
                "missingMapIds": candidate_topology["mapIds"],
                "maps": [],
                "layers": [],
                "layerMembership": [],
                "edges": [],
                "adjacentMapIds": [],
                "edgeCounts": {"incident": 0, "outgoing": 0, "incoming": 0},
                "truncated": False,
                "abstractRouteable": False,
                "playerRouteable": False,
                "routeable": False,
            }
            try:
                if ABSTRACT_TOPOLOGY_ROUTE_GRAPH_CACHE is None:
                    ABSTRACT_TOPOLOGY_ROUTE_GRAPH_CACHE = json.loads(
                        ABSTRACT_TOPOLOGY_ROUTE_GRAPH_FILE.read_text(encoding="utf-8")
                    )
                route_data = ABSTRACT_TOPOLOGY_ROUTE_GRAPH_CACHE
                requested_map_ids = set(candidate_topology["mapIds"])
                route_map_ids = {
                    row.get("mapId")
                    for row in route_data.get("nodes", [])
                    if row.get("nodeType") == "abstract_map"
                    and row.get("mapId") in requested_map_ids
                }
                route_maps = [
                    row for row in route_data.get("nodes", [])
                    if row.get("nodeType") == "abstract_map"
                    and row.get("mapId") in route_map_ids
                ]
                route_layers = [
                    row for row in route_data.get("nodes", [])
                    if row.get("nodeType") == "abstract_layer"
                    and row.get("mapId") in route_map_ids
                ]
                route_memberships = [
                    row for row in route_data.get("layerMembership", [])
                    if row.get("mapId") in route_map_ids
                ]
                incident_edges = [
                    row for row in route_data.get("edges", [])
                    if row.get("fromMapId") in route_map_ids
                    or row.get("toMapId") in route_map_ids
                ]
                outgoing_edges = [
                    row for row in incident_edges
                    if row.get("fromMapId") in route_map_ids
                ]
                incoming_edges = [
                    row for row in incident_edges
                    if row.get("toMapId") in route_map_ids
                ]
                adjacent_map_ids = {
                    map_id
                    for row in incident_edges
                    for map_id in (row.get("fromMapId"), row.get("toMapId"))
                    if map_id and map_id not in route_map_ids
                }
                abstract_route_evidence.update(
                    {
                        "status": "abstract_topology_route_evidence" if route_map_ids else "no_abstract_map_match",
                        "mapIds": sorted(route_map_ids),
                        "missingMapIds": sorted(requested_map_ids - route_map_ids),
                        "maps": route_maps,
                        "layers": route_layers,
                        "layerMembership": route_memberships,
                        "edges": incident_edges[:ABSTRACT_TOPOLOGY_ENTITY_EDGE_LIMIT],
                        "adjacentMapIds": sorted(adjacent_map_ids),
                        "edgeCounts": {
                            "incident": len(incident_edges),
                            "outgoing": len(outgoing_edges),
                            "incoming": len(incoming_edges),
                        },
                        "truncated": len(incident_edges) > ABSTRACT_TOPOLOGY_ENTITY_EDGE_LIMIT,
                        "abstractRouteable": bool(route_map_ids),
                        "note": "这是与实体端点关联的地图级抽象拓扑证据，不是连续步行路线；正式玩家路线资格仍由 routeNodeIds 独立决定。",
                    }
                )
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                # The player entity projection remains usable if the independent
                # abstract route evidence package is missing or malformed.
                pass
            self.send_json_payload(
                {
                    "schema": "elden-ring-reachability-map/player-entity-topology@1",
                    "found": True,
                    "entityId": entity_id,
                    "canonicalEntityId": entity.get("id"),
                    "entity": {
                        "id": entity.get("id"),
                        "name": entity.get("name"),
                        "topology": entity.get("topology", {}),
                    },
                    "bindings": bindings,
                    "acquisitionBridge": bridge_projection,
                    "abstractTopology": candidate_topology,
                    "abstractRouteEvidence": abstract_route_evidence,
                    "routeNodeIds": sorted(route_node_ids),
                    "routeReady": bool(route_node_ids),
                    "note": "仅 routeNodeIds 中的正式导航节点可进入路线规划；其他状态只展示数据，不自动制造导航边。",
                }
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.send_json_error(exc)

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
    parser = argparse.ArgumentParser(description="Run the Elden Ring Reachability Map WebUI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"Elden Ring Reachability Map running at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
