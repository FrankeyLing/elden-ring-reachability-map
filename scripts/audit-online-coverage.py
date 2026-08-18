"""Read-only audit for the online-first formal graph.

This script never contacts the game, reads process state, writes data, or
turns catalog/semantic records into traversal edges.  It only compares the
pinned online catalogs with the published V1 graph and reports explicit
aliases that need human review.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ONLINE_ITEM_FILES = tuple(
    ROOT / "data" / "v1" / "source-snapshots" / f"mapforgoblins-item-index-part{part}-20260818.json"
    for part in range(1, 31)
)
ONLINE_MAP_POINT_FILES = tuple(
    ROOT / "data" / "v1" / "source-snapshots" / f"mapforgoblins-map-points-part{part}-20260818.json"
    for part in range(1, 4)
)
ONLINE_BOSS_POSITION_FILE = ROOT / "data" / "v1" / "source-snapshots" / "mapforgoblins-boss-positions-20260818.json"
ONLINE_PROJECTED_GRACE_FILE = ROOT / "data" / "v1" / "source-snapshots" / "elden-ring-map-markers-20260818.json"
ONLINE_PROJECTED_GRACE_FILES = (
    ONLINE_PROJECTED_GRACE_FILE,
    *(ROOT / "data" / "v1" / "source-snapshots" / f"elden-ring-map-markers-supplement-{part:02d}-20260818.json" for part in range(1, 6)),
)
ONLINE_NAMED_GRACE_FILES = tuple(
    ROOT / "data" / "v1" / "source-snapshots" / f"elden-ring-compass-graces-{part:02d}-20260818.json"
    for part in range(1, 6)
)
ONLINE_INDEX_MANIFEST_FILE = ROOT / "data" / "v1" / "source-snapshots" / "mapforgoblins-online-index-20260818.json"
ONLINE_MAP_KEY_INDEX_FILE = ROOT / "data" / "v1" / "source-snapshots" / "mapforgoblins-map-key-index-20260818.json"
ROUTE_TARGET_GROUPS_FILE = ROOT / "data" / "v1" / "entities" / "er-guide-route-target-groups.json"
ROUTE_ASSESSMENTS_FILE = ROOT / "data" / "v1" / "entities" / "er-guide-route-assessments.json"
ER_GUIDE_ITEM_SNAPSHOT_FILES = {
    "er_guide_leg_caelid-04": ROOT / "data" / "v1" / "source-snapshots" / "er-guide-items-caelid-04-20260818.json",
    "er_guide_leg_caelid-06": ROOT / "data" / "v1" / "source-snapshots" / "er-guide-items-caelid-06-20260818.json",
    "er_guide_leg_dlc-scadu-altus-01": ROOT / "data" / "v1" / "source-snapshots" / "er-guide-items-dlc-scadu-altus-01-20260818.json",
    "er_guide_leg_dlc-scadu-altus-02": ROOT / "data" / "v1" / "source-snapshots" / "er-guide-items-dlc-scadu-altus-02-20260818.json",
    "er_guide_leg_dlc-scadu-altus-04": ROOT / "data" / "v1" / "source-snapshots" / "er-guide-items-dlc-scadu-altus-04-20260818.json",
    "er_guide_leg_dlc-scadu-altus-05": ROOT / "data" / "v1" / "source-snapshots" / "er-guide-items-dlc-scadu-altus-05-20260818.json",
    "er_guide_leg_dlc-scadu-altus-07": ROOT / "data" / "v1" / "source-snapshots" / "er-guide-items-dlc-scadu-altus-07-20260818.json",
    "er_guide_leg_dragonbarrow-02": ROOT / "data" / "v1" / "source-snapshots" / "er-guide-items-dragonbarrow-02-20260818.json",
}
EXPECTED_ITEM_COORDINATE_COUNTS = {
    "er_guide_leg_caelid-04": 48,
    "er_guide_leg_caelid-06": 8,
    "er_guide_leg_dlc-scadu-altus-01": 19,
    "er_guide_leg_dlc-scadu-altus-02": 14,
    "er_guide_leg_dlc-scadu-altus-04": 16,
    "er_guide_leg_dlc-scadu-altus-05": 12,
    "er_guide_leg_dlc-scadu-altus-07": 29,
    "er_guide_leg_dragonbarrow-02": 7,
}
UNRESOLVED_BOSS_LOCATION_NODES = {
    "elder_dragon_greyoll_gate",
    "mohg_omen_gate",
    "godrick_knight_fort_haight_gate",
    "soldier_of_godrick_cave_knowledge_gate",
}

# These are identity aliases only.  They do not create edges and are kept
# explicit because the formal graph deliberately uses shorter route IDs,
# translated labels, or post-boss state labels in some places.
EXPLICIT_ALIASES = {
    "grace_ainsel_river_ainsel_river_main_ainsel_river_main": "grace_ainsel_river_main",
    "grace_ainsel_river_ainsel_river_main_nokstella_eternal_city": "grace_nokstella_eternal_city",
    "grace_ainsel_river_ainsel_river_main_nokstella_waterfall_basin": "grace_nokstella_waterfall_basin",
    "grace_ainsel_river_main_astel_naturalborn_of_the_void": "grace_ainsel_river_main_astel_naturalborn_of_the_void",
    "grace_ainsel_river_main_dragonkin_soldier_of_nokstella": "grace_ainsel_river_main_dragonkin_soldier_of_nokstella",
    "grace_caelid_greyoll_s_dragonbarrow_isolated_merchant_s_shack_dragonbarrow": "grace_caelid_greyoll_s_dragonbarrow_isolated_merchant_shack",
    "grace_siofra_river_nokron_eternal_city_mimic_tear": "grace_nokron_mimic_tear",
    "grace_siofra_river_nokron_eternal_city_regal_ancestor_spirit": "grace_nokron_regal_ancestor_post_boss",
    "grace_altus_plateau_main_forest_spanning_greatbridge": "grace_altus_plateau_main_forest_spanning_greatbridge",
    "grace_crumbling_farum_azula_main_crumbling_beast_grave_depths": "grace_crumbling_beast_grave_depths",
    "grace_crumbling_farum_azula_main_dragon_temple_altar": "grace_dragon_temple_altar",
    "grace_crumbling_farum_azula_main_dragonlord_placidusax": "grace_farum_dragonlord_placidusax",
    "grace_crumbling_farum_azula_main_maliketh_the_black_blade": "grace_maliketh_black_blade",
    "grace_gravesite_plain_main_castle_front": "grace_castle_front",
    "grace_gravesite_plain_castle_ensis_castle_ensis_checkpoint": "grace_castle_ensis_checkpoint",
    "grace_gravesite_plain_castle_ensis_castle_lord_s_chamber": "grace_castle_lord_chamber",
    "grace_gravesite_plain_castle_ensis_ensis_moongazing_grounds": "grace_ensis_moongazing_grounds",
    "grace_leyndell_royal_capital_main_avenue_balcony": "grace_avenue_balcony",
    "grace_leyndell_royal_capital_main_east_capital_rampart": "grace_east_capital_rampart",
    "grace_leyndell_royal_capital_main_elden_throne": "grace_elden_throne",
    "grace_leyndell_royal_capital_main_erdtree_sanctuary": "grace_erdtree_sanctuary",
    "grace_leyndell_royal_capital_main_queen_s_bedchamber": "grace_queens_bedchamber",
    "grace_leyndell_royal_capital_leyndell_ashen_capital_elden_throne": "grace_ashen_elden_throne",
    "grace_leyndell_royal_capital_leyndell_ashen_capital_erdtree_sanctuary": "grace_ashen_erdtree_sanctuary",
    "grace_leyndell_royal_capital_leyndell_ashen_capital_queen_s_bedchamber": "grace_ashen_queens_bedchamber",
    "grace_limgrave_stormhill_limgrave_tower_bridge": "grace_limgrave_stormhill_limgrave_tower_bridge",
    "grace_limgrave_stormhill_margit_the_fell_omen": "grace_limgrave_stormhill_margit_the_fell_omen",
    "grace_limgrave_weeping_peninsula_isolated_merchant_s_shack": "grace_limgrave_weeping_peninsula_isolated_merchants_shack",
    "grace_liurnia_of_the_lakes_main_liurnia_tower_bridge": "grace_liurnia_of_the_lakes_main_liurnia_tower_bridge",
    "grace_liurnia_of_the_lakes_bellum_highway_east_raya_lucaria_gate": "grace_liurnia_of_the_lakes_bellum_highway_east_raya_lucaria_gate",
    "grace_liurnia_of_the_lakes_ruin_strewn_precipice_magma_wyrm_makar": "grace_liurnia_of_the_lakes_ruin_strewn_precipice_magma_wyrm_makar",
    "grace_miquella_s_haligtree_main_haligtree_canopy": "grace_haligtree_canopy",
    "grace_miquella_s_haligtree_main_haligtree_promenade": "grace_haligtree_promenade",
    "grace_miquella_s_haligtree_elphael_brace_of_the_haligtree_malenia_goddess_of_rot": "grace_malenia_post_boss",
    "grace_mountaintops_of_the_giants_consecrated_snowfield_ordina_liturgical_town": "grace_ordina_liturgical_town",
    "grace_mountaintops_of_the_giants_mountaintops_of_the_giants_spiritcaller_cave": "grace_mountaintops_main_spiritcallers_cave",
    "grace_scadu_altus_abyssal_woods_forsaken_graveyard": "grace_scadu_altus_abyssal_woods_forsaken_graveyard",
    "grace_siofra_river_nokron_eternal_city_nokron_eternal_city": "grace_nokron_eternal_city",
    "grace_siofra_river_siofra_river_siofra_river_bank": "grace_siofra_river_bank",
    "grace_siofra_river_siofra_river_siofra_river_well_depths": "grace_siofra_well_depths",
    "grace_volcano_manor_main_prison_town_church": "grace_prison_town_church",
    "grace_volcano_manor_main_rykard_lord_of_blasphemy": "grace_volcano_manor_main_rykard_lord_of_blasphemy",
    "grace_volcano_manor_main_temple_of_eiglay": "grace_temple_of_eiglay",
    "grace_volcano_manor_main_volcano_manor": "grace_volcano_manor_entrance",
}

# Normalized route-guide endpoint labels mapped to one formal node only when
# the guide label is an unambiguous identity match.  These aliases improve
# audit coverage; they do not promote guide legs to traversal edges.  Broad
# sweeps, multi-area labels, and endpoints that are not represented as a
# single formal node intentionally remain unmapped.
ROUTE_ENDPOINT_ALIASES = {
    "rennasrisesendinggate": "renna_rise_waygate",
    "rennasrise": "renna_rise_waygate",
    "ainselrivermain": "grace_ainsel_river_main",
    "nokstellaeternalcity": "grace_nokstella_eternal_city",
    "fracturedmarika": "grace_fractured_marika",
    "smolderingchurch": "grace_smoldering_church",
    "churchoftheplague": "grace_church_of_plague",
    "selliatownofsorcery": "grace_caelid_main_sellia_under_stair",
    "churchofirith": "landmark_church_of_irith",
    "rosechurchvarre": "landmark_rose_church",
    "bellumhighwayeastliurnia": "grace_liurnia_of_the_lakes_bellum_highway_east_raya_lucaria_gate",
    "bellumhighway": "grace_liurnia_of_the_lakes_bellum_highway_east_raya_lucaria_gate",
    "endings": "ending_selection_state",
    "innerconsecratedsnowfield": "grace_inner_consecrated_snowfield",
    "ordinaliturgicaltown": "grace_ordina_liturgical_town",
    "apostatederelict": "grace_mountaintops_of_the_giants_apostate_derelict",
    "spiralrise": "grace_enir_ilim_spiral_rise",
    "divinegate": "promised_consort_radahn_gate",
    "mohgwynpalace": "grace_palace_approach_ledge_road",
    "gravesiteplain": "grace_shadow_realm_gravesite_plain",
    "castlefront": "grace_castle_front",
    "ensismoongazinggrounds": "grace_ensis_moongazing_grounds",
    "cliffroadterminus": "grace_shadow_realm_cliffroad_terminus",
    "highroadcross": "grace_scadu_altus_highroad_cross",
    "castlewateringhole": "grace_scadu_altus_main_castle_watering_hole",
    "shadowkeepmaingateplaza": "grace_shadow_keep_main_gate_plaza",
    "shadowkeepbackgate": "grace_shadow_keep_back_gate",
    "dragonbarrowwest": "grace_caelid_greyoll_s_dragonbarrow_dragonbarrow_west",
    "fortfaroth": "grace_fort_faroth",
    "farumgreatbridge": "grace_caelid_greyoll_s_dragonbarrow_farum_greatbridge",
    "divinetowerofcaelid": "grace_caelid_greyoll_s_dragonbarrow_divine_tower_of_caelid_center",
    "forgeofthegiants": "grace_forge_of_giants",
    "crumblingbeastgravedepths": "grace_crumbling_beast_grave_depths",
    "dragontemplealtar": "grace_dragon_temple_altar",
    "haligtreecanopy": "grace_haligtree_canopy",
    "haligtreepromenade": "grace_haligtree_promenade",
    "haligtreeroots": "grace_elphael_haligtree_roots",
    "malenia": "malenia_haligtree_gate",
    "avenuebalcony": "grace_avenue_balcony",
    "erdtreesanctuary": "grace_erdtree_sanctuary",
    "lakefacingcliffs": "grace_lake_facing_cliffs",
    "mainacademygate": "grace_main_academy_gate",
    "rayalucariaacademy": "grace_church_of_cuckoo",
    "schoolhouseclassroom": "grace_schoolhouse_classroom",
    "rayalucariagrandlibrary": "grace_raya_lucaria_grand_library",
    "villageofthealbinaurics": "grace_liurnia_of_the_lakes_main_village_of_the_albinaurics",
    "cariamanor": "grace_liurnia_of_the_lakes_main_royal_moongazing_grounds",
    "rannisrise": "grace_liurnia_of_the_lakes_main_ranni_s_rise",
    "castlesolrooftop": "grace_castle_sol_rooftop",
    "spiritcallercave": "grace_mountaintops_main_spiritcallers_cave",
    "volcanomanor": "grace_volcano_manor_entrance",
    "prisontownchurch": "grace_prison_town_church",
    "templeofeiglay": "grace_temple_of_eiglay",
    "starfallcrater": "starfall_crater_entrance",
    "starfallcratermistwoodlimgrave": "starfall_crater_entrance",
    "nokroneternalcity": "grace_nokron_eternal_city",
    "aqueductfacingcliffs": "grace_aqueduct_facing_cliffs",
    "siofrariverwelldepths": "grace_siofra_well_depths",
    "siofrariverbank": "grace_siofra_river_bank",
    "hallowhorngrounds": "hallowhorn_grounds_siofra",
    "worshipperswoods": "grace_worshippers_woods",
    "siofraaqueduct": "siofra_hidden_waygate",
    "siofraaqueductdeeprootcoffin": "deeproot_coffin",
    "roundtablehold": "grace_roundtable_hold_main_table_of_lost_grace",
}

# Some guide legs intentionally name a location rather than the exact
# navigational endpoint.  Keep these decisions per leg and per direction:
# entering a boss arena resolves to the boss gate, while leaving a completed
# boss area resolves to the post-boss grace/state node.  These are audit
# bindings only; they do not create traversal edges or claim a physical path.
ROUTE_ENDPOINT_RESOLUTIONS = {
    "er_guide_leg_ainsel-04": {
        "to": "astel_naturalborn_gate",
    },
    "er_guide_leg_dlc-scadu-altus-02": {
        "from": "grace_scadu_altus_main_fort_of_reprimand",
    },
    "er_guide_leg_farum-03": {
        "to": "dragonlord_placidusax_gate",
    },
    "er_guide_leg_farum-04": {
        "to": "maliketh_gate",
    },
    "er_guide_leg_limgrave-12": {
        "from": "grace_limgrave_main_limgrave_tunnels",
        "to": "grace_limgrave_main_limgrave_tunnels",
    },
    "er_guide_leg_liurnia-11": {
        "from": "grace_liurnia_of_the_lakes_main_black_knife_catacombs",
        "to": "grace_liurnia_of_the_lakes_main_black_knife_catacombs",
    },
    "er_guide_leg_liurnia-12": {
        "from": "grace_liurnia_of_the_lakes_main_black_knife_catacombs",
    },
    "er_guide_leg_mtgelmir-03": {
        "from": "grace_altus_plateau_main_gelmir_hero_s_grave",
        "to": "grace_altus_plateau_main_wyndham_catacombs",
    },
    "er_guide_leg_nokron-02": {
        "to": "mimic_tear_gate",
    },
    "er_guide_leg_nokron-03": {
        "from": "grace_nokron_mimic_tear",
    },
    "er_guide_leg_weeping-03": {
        "from": "grace_limgrave_weeping_peninsula_earthbore_cave",
        "to": "grace_limgrave_weeping_peninsula_earthbore_cave",
    },
    "er_guide_leg_weeping-05": {
        "from": "grace_limgrave_weeping_peninsula_morne_tunnel",
        "to": "grace_limgrave_weeping_peninsula_morne_tunnel",
    },
}

EXPECTED_ROUTE_ENDPOINT_RESOLUTION_LEGS = {
    "er_guide_leg_ainsel-04",
    "er_guide_leg_dlc-scadu-altus-02",
    "er_guide_leg_farum-03",
    "er_guide_leg_farum-04",
    "er_guide_leg_limgrave-12",
    "er_guide_leg_liurnia-11",
    "er_guide_leg_liurnia-12",
    "er_guide_leg_mtgelmir-03",
    "er_guide_leg_nokron-02",
    "er_guide_leg_nokron-03",
    "er_guide_leg_weeping-03",
    "er_guide_leg_weeping-05",
}


def load(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or "")).lower()
    value = re.sub(r"\([^)]*\)", "", value)
    return re.sub(r"[^a-z0-9]+", "", value)


def candidates_for(label_index: dict[str, list[dict]], name: str, region: str = "", layer: str = "") -> list[dict]:
    candidates = label_index.get(norm(name), [])
    if not candidates:
        return []
    same_region = [node for node in candidates if norm(node.get("region")) == norm(region)]
    if same_region:
        candidates = same_region
    same_layer = [node for node in candidates if node.get("layer") == layer]
    if same_layer:
        candidates = same_layer
    return candidates


def decode_online_chunks(paths: tuple[Path, ...]) -> list:
    import base64
    import zlib

    chunks = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    chunks.sort(key=lambda payload: payload["part"])
    expected_parts = chunks[0]["parts"] if chunks else 0
    if not chunks or expected_parts != len(chunks) or [chunk["part"] for chunk in chunks] != list(range(1, expected_parts + 1)):
        raise ValueError("online item snapshot chunks are incomplete or out of order")
    encoded = "".join(chunk["chunk"] for chunk in chunks)
    return json.loads(zlib.decompress(base64.b64decode(encoded)).decode("utf-8"))


def load_online_map_point_records() -> dict[tuple[str, int, int], list]:
    records = {}
    for path in ONLINE_MAP_POINT_FILES:
        payload = json.loads(path.read_text(encoding="utf-8"))
        snapshot = path.stem
        for row in payload["records"]:
            records[(snapshot, int(row[0]), int(row[1]))] = row
    return records


def load_online_boss_position_records() -> dict[tuple[str, int, int], list]:
    records = {}
    payload = json.loads(ONLINE_BOSS_POSITION_FILE.read_text(encoding="utf-8"))
    snapshot = ONLINE_BOSS_POSITION_FILE.stem
    for row in payload["records"]:
        # Boss-position records have no separate map-point id; npcParamId is
        # the pinned source record identity used by onlineCoordinate.recordId.
        records[(snapshot, int(row[0]), int(row[10]))] = row
    return records


def audit() -> dict:
    graph = load("data/v1/graph.json")
    catalog = load("data/v1/entities/sites-of-grace.json")
    achievements = load("data/v1/entities/achievements.json")
    legs = load("data/v1/entities/er-guide-route-legs.json")
    route_target_groups = json.loads(ROUTE_TARGET_GROUPS_FILE.read_text(encoding="utf-8"))
    route_assessments = json.loads(ROUTE_ASSESSMENTS_FILE.read_text(encoding="utf-8"))
    item_snapshots = {
        leg_id: json.loads(path.read_text(encoding="utf-8"))
        for leg_id, path in ER_GUIDE_ITEM_SNAPSHOT_FILES.items()
    }
    route_profiles = load("data/v1/route-profiles.json")
    online_index_manifest = json.loads(ONLINE_INDEX_MANIFEST_FILE.read_text(encoding="utf-8"))
    online_map_key_index = json.loads(ONLINE_MAP_KEY_INDEX_FILE.read_text(encoding="utf-8"))
    projected_grace_payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in ONLINE_PROJECTED_GRACE_FILES
    ]
    projected_graces = projected_grace_payloads[0]
    named_grace_payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in ONLINE_NAMED_GRACE_FILES
    ]
    nodes = graph["nodes"]
    node_by_id = {node["id"]: node for node in nodes}
    related_source_ids = {source.get("source_id") for source in achievements.get("related_sources", [])}
    related_sources_by_id = {
        source.get("source_id"): source for source in achievements.get("related_sources", [])
    }
    graph_evidence_ids = {
        evidence.get("id") if isinstance(evidence, dict) else evidence
        for evidence in graph.get("sourceEvidence", [])
    }
    known_evidence_ids = related_source_ids | graph_evidence_ids | {achievements.get("source", {}).get("source_id")}
    formal_grace_labels = {node.get("label"): node.get("id") for node in nodes if node.get("kind") == "grace"}
    projected_records = [
        record
        for payload in projected_grace_payloads
        for record in payload.get("records", [])
    ]
    projected_formal_ids = [record.get("formal_id") for record in projected_records if record.get("formal_id")]
    projected_anchor_contract = {
        "schema": projected_graces.get("schema"),
        "snapshots": [payload.get("snapshot") for payload in projected_grace_payloads],
        "source_url": projected_graces.get("source", {}).get("url"),
        "coordinate_space": projected_graces.get("coordinate_space"),
        "record_count": len(projected_records),
        "part_record_counts": [len(payload.get("records", [])) for payload in projected_grace_payloads],
        "invalid_payloads": [
            payload.get("snapshot")
            for payload in projected_grace_payloads
            if payload.get("schema") != "elden-ring-reachability-map/projected-anchor-snapshot@1"
            or payload.get("source", {}).get("url") != "https://raw.githubusercontent.com/jw-ofs/elden-ring-map/main/markers.js"
            or payload.get("coordinate_space", {}).get("id") != "master_tile_pixel"
            or payload.get("coordinate_space", {}).get("width") != 10496
            or payload.get("coordinate_space", {}).get("height") != 10496
        ],
        "duplicate_source_ids": sorted(
            source_id
            for source_id in {record.get("source_id") for record in projected_records}
            if source_id and [item.get("source_id") for item in projected_records].count(source_id) > 1
        ),
        "invalid_records": [
            record.get("source_id")
            for record in projected_records
            if record.get("master") not in {"M00", "M01", "M10"}
            or not isinstance(record.get("position"), list)
            or len(record.get("position", [])) != 2
            or not all(isinstance(value, (int, float)) and 0 <= value <= 10496 for value in record.get("position", []))
            or (record.get("formal_id") and formal_grace_labels.get(record.get("name")) != record.get("formal_id"))
        ],
        "exact_formal_bindings": len(projected_formal_ids),
        "unbound_source_markers": sum(not record.get("formal_id") for record in projected_records),
    }
    if (
        projected_anchor_contract["schema"] != "elden-ring-reachability-map/projected-anchor-snapshot@1"
        or projected_anchor_contract["snapshots"] != [
            ONLINE_PROJECTED_GRACE_FILE.stem,
            *[path.stem for path in ONLINE_PROJECTED_GRACE_FILES[1:]],
        ]
        or projected_anchor_contract["source_url"] != "https://raw.githubusercontent.com/jw-ofs/elden-ring-map/main/markers.js"
        or projected_anchor_contract["coordinate_space"].get("id") != "master_tile_pixel"
        or projected_anchor_contract["coordinate_space"].get("width") != 10496
        or projected_anchor_contract["coordinate_space"].get("height") != 10496
        or projected_anchor_contract["record_count"] != 413
        or projected_anchor_contract["part_record_counts"] != [111, 75, 75, 75, 75, 2]
        or projected_anchor_contract["invalid_payloads"]
        or projected_anchor_contract["duplicate_source_ids"]
        or projected_anchor_contract["invalid_records"]
    ):
        raise ValueError(f"projected anchor contract failed: {projected_anchor_contract}")
    named_grace_records = [
        record
        for payload in named_grace_payloads
        for record in payload.get("records", [])
    ]
    formal_grace_ids = {node["id"] for node in nodes if node.get("kind") == "grace"}
    named_grace_contract = {
        "schema": named_grace_payloads[0].get("schema"),
        "snapshots": [payload.get("snapshot") for payload in named_grace_payloads],
        "source_url": named_grace_payloads[0].get("source", {}).get("url"),
        "coordinate_space": named_grace_payloads[0].get("coordinate_space"),
        "record_count": len(named_grace_records),
        "part_record_counts": [len(payload.get("records", [])) for payload in named_grace_payloads],
        "duplicate_flag_ids": sorted(
            flag_id
            for flag_id in {record.get("flag_id") for record in named_grace_records}
            if flag_id is not None and [item.get("flag_id") for item in named_grace_records].count(flag_id) > 1
        ),
        "duplicate_entity_ids": sorted(
            entity_id
            for entity_id in {record.get("bonfire_entity_id") for record in named_grace_records}
            if entity_id is not None and [item.get("bonfire_entity_id") for item in named_grace_records].count(entity_id) > 1
        ),
        "invalid_records": [
            record.get("flag_id")
            for record in named_grace_records
            if not re.fullmatch(r"m\d+_\d+_\d+_\d+", str(record.get("map", "")))
            or not isinstance(record.get("position"), list)
            or len(record.get("position", [])) != 3
            or not all(isinstance(value, (int, float)) for value in record.get("position", []))
            or not set(record.get("formal_candidates", [])) <= formal_grace_ids
        ],
        "formal_candidate_count": sum(bool(record.get("formal_candidates")) for record in named_grace_records),
    }
    if (
        named_grace_contract["schema"] != "elden-ring-reachability-map/named-grace-coordinate-snapshot@1"
        or named_grace_contract["snapshots"] != [path.stem for path in ONLINE_NAMED_GRACE_FILES]
        or named_grace_contract["source_url"] != "https://raw.githubusercontent.com/EthanShoeDev/elden-ring-compass/main/packages/data/src/generated/markers.ts"
        or named_grace_contract["coordinate_space"].get("id") != "source_map_local_xyz"
        or named_grace_contract["record_count"] != 419
        or named_grace_contract["part_record_counts"] != [84, 84, 84, 84, 83]
        or named_grace_contract["duplicate_flag_ids"]
        or named_grace_contract["duplicate_entity_ids"]
        or named_grace_contract["invalid_records"]
        or named_grace_contract["formal_candidate_count"] != 378
    ):
        raise ValueError(f"named grace coordinate contract failed: {named_grace_contract}")
    graph_condition_ids = {condition["id"] for condition in graph.get("conditions", [])}
    achievement_ids = [record.get("canonical_id") for record in achievements["records"]]
    required_items_by_achievement = {
        record["canonical_id"]: set(record.get("required_item_names", []))
        for record in achievements["records"]
    }
    text_location_catalog = achievements.get("online_text_location_evidence", {})
    text_location_entries = [
        (achievement_id, entry)
        for achievement_id, entries in text_location_catalog.items()
        for entry in entries
    ]
    text_location_contract = {
        "achievement_ids_without_records": sorted(
            achievement_id for achievement_id in text_location_catalog if achievement_id not in required_items_by_achievement
        ),
        "invalid_item_names": [
            {"achievement": achievement_id, "item": entry.get("item")}
            for achievement_id, entry in text_location_entries
            if entry.get("item") not in required_items_by_achievement.get(achievement_id, set())
        ],
        "invalid_target_ids": [
            {"achievement": achievement_id, "item": entry.get("item"), "target_id": entry.get("formal_target_id")}
            for achievement_id, entry in text_location_entries
            if entry.get("formal_target_id") not in node_by_id
        ],
        "invalid_source_evidence": [
            {"achievement": achievement_id, "item": entry.get("item"), "source_id": entry.get("source_evidence")}
            for achievement_id, entry in text_location_entries
            if entry.get("source_evidence") not in known_evidence_ids
        ],
        "missing_source_urls": [
            {"achievement": achievement_id, "item": entry.get("item"), "source_id": entry.get("source_evidence")}
            for achievement_id, entry in text_location_entries
            if not related_sources_by_id.get(entry.get("source_evidence"), {}).get("source_url")
        ],
        "coordinate_claims": [
            {"achievement": achievement_id, "item": entry.get("item")}
            for achievement_id, entry in text_location_entries
            if entry.get("coordinate_available") is not False
        ],
    }
    achievement_contract = {
        "records": len(achievements["records"]),
        "declared_records": achievements.get("record_count"),
        "duplicate_canonical_ids": sorted({item for item in achievement_ids if achievement_ids.count(item) > 1}),
        "missing_source_evidence": [
            record.get("canonical_id") for record in achievements["records"] if not record.get("source_evidence")
        ],
        "invalid_formal_target_ids": [
            {"achievement": record.get("canonical_id"), "target_id": target_id}
            for record in achievements["records"]
            for target_id in record.get("formal_target_ids", [])
            if target_id not in node_by_id
        ],
        "invalid_location_target_ids": [
            {"achievement": record.get("canonical_id"), "target_id": target_id}
            for record in achievements["records"]
            for target_id in record.get("location_target_ids", [])
            if target_id not in node_by_id
        ],
        "invalid_prerequisite_target_ids": [
            {"achievement": record.get("canonical_id"), "target_id": target_id}
            for record in achievements["records"]
            for target_id in record.get("prerequisite_target_ids", [])
            if target_id not in node_by_id
        ],
        "invalid_location_target_group_ids": [
            {"achievement": record.get("canonical_id"), "target_id": target_id}
            for record in achievements["records"]
            for group in record.get("location_target_groups", [])
            for target_id in group.get("target_ids", [])
            if target_id not in node_by_id
        ],
        "invalid_state_requirement_ids": [
            {"achievement": record.get("canonical_id"), "condition_id": condition_id}
            for record in achievements["records"]
            for condition_id in record.get("state_requirements", [])
            if condition_id not in graph_condition_ids
        ],
        "invalid_effect_condition_ids": [
            {"achievement": record.get("canonical_id"), "condition_id": condition_id}
            for record in achievements["records"]
            for condition_id in record.get("effect_conditions", [])
            if condition_id not in graph_condition_ids
        ],
        "missing_location_source_evidence": [
            record.get("canonical_id")
            for record in achievements["records"]
            if record.get("location_target_ids")
            and record.get("location_source_evidence") not in related_source_ids
        ],
        "missing_location_group_source_evidence": [
            {"achievement": record.get("canonical_id"), "requirement": group.get("requirement")}
            for record in achievements["records"]
            for group in record.get("location_target_groups", [])
            if group.get("source_evidence") not in related_source_ids
        ],
        "invalid_record_evidence_ids": [
            {"achievement": record.get("canonical_id"), "field": field, "source_id": record.get(field)}
            for record in achievements["records"]
            for field in ("state_source_evidence", "formal_target_source_evidence", "prerequisite_source_evidence")
            if record.get(field) and record.get(field) not in known_evidence_ids
        ],
        "online_text_location_contract": text_location_contract,
        "routeable_records": [
            record.get("canonical_id") for record in achievements["records"] if record.get("routeable") is not False
        ],
        "source_revision": achievements.get("source", {}).get("revision_id"),
    }
    if (
        achievement_contract["records"] != 42
        or achievement_contract["declared_records"] != 42
        or achievement_contract["duplicate_canonical_ids"]
        or achievement_contract["missing_source_evidence"]
        or achievement_contract["invalid_formal_target_ids"]
        or achievement_contract["invalid_location_target_ids"]
        or achievement_contract["invalid_prerequisite_target_ids"]
        or achievement_contract["invalid_location_target_group_ids"]
        or achievement_contract["invalid_state_requirement_ids"]
        or achievement_contract["invalid_effect_condition_ids"]
        or achievement_contract["missing_location_source_evidence"]
        or achievement_contract["missing_location_group_source_evidence"]
        or achievement_contract["invalid_record_evidence_ids"]
        or any(text_location_contract.values())
        or achievement_contract["routeable_records"]
        or not achievement_contract["source_revision"]
    ):
        raise ValueError(f"achievement catalog contract failed: {achievement_contract}")
    online_item_records = decode_online_chunks(ONLINE_ITEM_FILES)
    online_item_name_counts: Counter[str] = Counter(
        str(item.get("name"))
        for row in online_item_records
        for item in row[4]
        if item.get("name")
    )
    collection_item_coverage = {}
    for record in achievements["records"]:
        if record.get("category") != "collection":
            continue
        aliases = record.get("online_name_aliases", {})
        matched = {}
        unmatched = []
        for required_name in record.get("required_item_names", []):
            candidates = [required_name, *aliases.get(required_name, [])]
            source_matches = {name: online_item_name_counts[name] for name in candidates if online_item_name_counts[name]}
            if source_matches:
                matched[required_name] = source_matches
            else:
                unmatched.append(required_name)
        collection_item_coverage[record["canonical_id"]] = {
            "required_count": len(record.get("required_item_names", [])),
            "matched_count": len(matched),
            "unmatched": unmatched,
            "matched_source_names": matched,
        }
    label_index: dict[str, list[dict]] = {}
    for node in nodes:
        label_index.setdefault(norm(node.get("label")), []).append(node)

    bindings = []
    unmapped = []
    ambiguous = []
    for record in catalog["records"]:
        cid = record["canonical_id"]
        target_id = EXPLICIT_ALIASES.get(cid)
        method = "exact_label"
        if cid in node_by_id:
            candidates = [node_by_id[cid]]
            method = "exact_canonical_id"
        else:
            candidates = [node_by_id[target_id]] if target_id in node_by_id else []
            if candidates:
                method = "explicit_alias"
        if not candidates:
            candidates = candidates_for(label_index, record["name"], record["region"], record["layer"])
        preferred_graces = [
            node
            for node in candidates
            if node.get("kind") == "grace"
            and not any(marker in node["id"] for marker in ("post_boss", "postboss", "_post_", "_state"))
        ]
        if len(preferred_graces) == 1 and method == "exact_label":
            candidates = preferred_graces
            method = "preferred_grace_label"
        if candidates and all(node.get("kind") != "grace" for node in candidates) and method == "exact_label":
            unmapped.append(
                {
                    "catalog_id": cid,
                    "name": record["name"],
                    "region": record["region"],
                    "reason": "only_non_grace_formal_candidate",
                    "candidates": [node["id"] for node in candidates],
                }
            )
            continue
        if len(candidates) == 1:
            target = candidates[0]
            bindings.append(
                {
                    "catalog_id": cid,
                    "name": record["name"],
                    "formal_id": target["id"],
                    "formal_kind": target.get("kind"),
                    "method": method,
                }
            )
        elif len(candidates) > 1:
            ambiguous.append(
                {"catalog_id": cid, "name": record["name"], "candidates": [x["id"] for x in candidates]}
            )
        else:
            unmapped.append({"catalog_id": cid, "name": record["name"], "region": record["region"]})

    bound_ids = {item["formal_id"] for item in bindings}
    formal_graces = [node for node in nodes if node.get("kind") == "grace"]
    expected_catalog_unmapped = {
        "grace_mountaintops_of_the_giants_flame_peak_fire_giant",
        "grace_stormveil_castle_main_godrick_the_grafted",
    }
    expected_catalog_kind_mismatch = {
        "grace_altus_plateau_main_forest_spanning_greatbridge",
        "grace_leyndell_royal_capital_subterranean_shunning_grounds_frenzied_flame_proscription",
        "grace_limgrave_stormhill_limgrave_tower_bridge",
        "grace_liurnia_of_the_lakes_main_liurnia_tower_bridge",
        "grace_liurnia_of_the_lakes_bellum_highway_east_raya_lucaria_gate",
        "grace_scadu_altus_abyssal_woods_forsaken_graveyard",
    }
    expected_unlisted_formal_graces = {
        "grace_siofra_ancestor_spirit_post_boss",
        "grace_nokron_regal_ancestor_post_boss",
        "grace_siofra_great_waterfall_basin",
        "grace_lichdragon_fortissax_post_boss",
    }
    catalog_anomaly_contract = {
        "unmapped_catalog_ids": sorted(item["catalog_id"] for item in unmapped),
        "formal_kind_mismatch_ids": sorted(
            item["catalog_id"] for item in bindings if item["formal_kind"] != "grace"
        ),
        "formal_graces_without_catalog_binding": sorted(
            node["id"] for node in formal_graces if node["id"] not in bound_ids
        ),
        "expected_unmapped_catalog_ids": sorted(expected_catalog_unmapped),
        "expected_formal_kind_mismatch_ids": sorted(expected_catalog_kind_mismatch),
        "expected_formal_graces_without_catalog_binding": sorted(expected_unlisted_formal_graces),
    }
    if (
        catalog_anomaly_contract["unmapped_catalog_ids"] != catalog_anomaly_contract["expected_unmapped_catalog_ids"]
        or catalog_anomaly_contract["formal_kind_mismatch_ids"] != catalog_anomaly_contract["expected_formal_kind_mismatch_ids"]
        or catalog_anomaly_contract["formal_graces_without_catalog_binding"]
        != catalog_anomaly_contract["expected_formal_graces_without_catalog_binding"]
    ):
        raise ValueError(f"sites-of-grace catalog anomaly contract failed: {catalog_anomaly_contract}")
    route_edges = {(edge["from"], edge["to"]) for edge in graph["edges"]}
    edge_by_id = {edge["id"]: edge for edge in graph["edges"]}
    node_ids = set(node_by_id)
    registered_snapshot_ids = set(graph.get("meta", {}).get("sourceSnapshots", []))
    coordinate_snapshot_ids = {
        node["onlineCoordinate"].get("snapshot")
        for node in nodes
        if node.get("onlineCoordinate") and node["onlineCoordinate"].get("snapshot")
    }
    online_snapshot_contract = {
        "referenced": sorted(coordinate_snapshot_ids),
        "registered": sorted(coordinate_snapshot_ids & registered_snapshot_ids),
        "unregistered": sorted(coordinate_snapshot_ids - registered_snapshot_ids),
    }
    if online_snapshot_contract["unregistered"]:
        raise ValueError(f"online snapshot registration contract failed: {online_snapshot_contract}")
    expected_online_map_key_sources = {
        "tile-regions",
        "map-points",
        "grace-positions",
        "boss-positions",
        "map-conversions",
        "items",
        "entities",
        "gathering",
    }
    map_key_artifact_path = "data/v1/source-snapshots/mapforgoblins-map-key-index-20260818.json"
    online_map_key_contract = {
        "schema": online_map_key_index.get("schema"),
        "records": len(online_map_key_index.get("records", [])),
        "declared_records": online_map_key_index.get("record_count"),
        "duplicate_map_keys": sorted(
            {
                key
                for key in [record.get("mapKey") for record in online_map_key_index.get("records", [])]
                if key and [item.get("mapKey") for item in online_map_key_index.get("records", [])].count(key) > 1
            }
        ),
        "invalid_map_keys": [
            record.get("mapKey")
            for record in online_map_key_index.get("records", [])
            if not re.fullmatch(r"m\d+_\d+_\d+", str(record.get("mapKey", "")))
        ],
        "source_categories": sorted(online_map_key_index.get("source_categories", [])),
        "missing_source_categories": sorted(
            expected_online_map_key_sources - set(online_map_key_index.get("source_categories", []))
        ),
        "manifest_registered": any(
            artifact.get("path") == map_key_artifact_path
            for artifact in online_index_manifest.get("artifacts", [])
        ),
        "routeable": online_map_key_index.get("routeable"),
        "safety": online_map_key_index.get("safetyBoundary", {}),
    }
    if (
        online_map_key_contract["schema"] != "elden-ring-reachability-map/online-map-key-index@1"
        or online_map_key_contract["records"] != online_map_key_contract["declared_records"]
        or online_map_key_contract["records"] != 1037
        or online_map_key_contract["duplicate_map_keys"]
        or online_map_key_contract["invalid_map_keys"]
        or online_map_key_contract["missing_source_categories"]
        or not online_map_key_contract["manifest_registered"]
        or online_map_key_contract["routeable"] is not False
        or online_map_key_contract["safety"].get("gameProcessAccessed")
        or online_map_key_contract["safety"].get("gameFilesAccessed")
        or online_map_key_contract["safety"].get("runtimeInjection")
        or online_map_key_contract["safety"].get("overlay")
        or online_map_key_contract["safety"].get("saveAccess")
        or online_map_key_contract["safety"].get("gameDirectoryAccess")
    ):
        raise ValueError(f"online map-key index contract failed: {online_map_key_contract}")
    map_point_candidate_records = []
    for path in ONLINE_MAP_POINT_FILES:
        payload = json.loads(path.read_text(encoding="utf-8"))
        map_point_candidate_records.extend(
            (path.stem, row) for row in payload["records"] if len(row[10] or []) == 1
        )
    map_point_candidates_by_target: dict[str, list[dict]] = {}
    for snapshot, row in map_point_candidate_records:
        map_point_candidates_by_target.setdefault(row[10][0], []).append(
            {"snapshot": snapshot, "sourceIndex": row[0], "recordId": row[1], "names": row[9] or []}
        )
    map_point_candidate_contract = {
        "single_candidate_records": len(map_point_candidate_records),
        "unique_formal_targets": len(map_point_candidates_by_target),
        "bound_formal_targets": sum(
            target_id in {node["id"] for node in nodes if node.get("onlineCoordinate")}
            for target_id in map_point_candidates_by_target
        ),
        "unbound_formal_targets": {
            target_id: records
            for target_id, records in map_point_candidates_by_target.items()
            if target_id not in {node["id"] for node in nodes if node.get("onlineCoordinate")}
        },
    }
    if (
        map_point_candidate_contract["single_candidate_records"] != 157
        or map_point_candidate_contract["unique_formal_targets"] != 139
        or map_point_candidate_contract["bound_formal_targets"] != 139
        or map_point_candidate_contract["unbound_formal_targets"] != {}
    ):
        raise ValueError(f"online map-point candidate contract failed: {map_point_candidate_contract}")
    transition_contract = {
        "edge_count": len(graph["edges"]),
        "missing_source_evidence": [edge["id"] for edge in graph["edges"] if not edge.get("sourceEvidence")],
        "missing_verification_state": [edge["id"] for edge in graph["edges"] if not edge.get("verificationState")],
        "invalid_endpoints": [
            edge["id"]
            for edge in graph["edges"]
            if edge.get("from") not in node_ids or edge.get("to") not in node_ids
        ],
        "semantic_relation_edge_ids": [edge["id"] for edge in graph["edges"] if edge.get("routeable") is False],
    }
    if any(transition_contract[key] for key in ("missing_source_evidence", "missing_verification_state", "invalid_endpoints", "semantic_relation_edge_ids")):
        raise ValueError(f"formal transition contract failed: {transition_contract}")
    online_text_location_nodes = [node for node in nodes if node.get("onlineTextLocation")]
    invalid_online_text_locations = []
    for node in online_text_location_nodes:
        evidence = node["onlineTextLocation"]
        if (
            evidence.get("coordinateAvailable") is not False
            or evidence.get("anchorNodeId") not in node_ids
            or not evidence.get("locationClaim")
            or not evidence.get("reason")
        ):
            invalid_online_text_locations.append(node["id"])
    online_text_location_contract = {
        "node_count": len(online_text_location_nodes),
        "invalid_nodes": invalid_online_text_locations,
    }
    if online_text_location_contract["invalid_nodes"]:
        raise ValueError(f"online text location contract failed: {online_text_location_contract}")
    unresolved_boss_nodes = {
        node["id"]: node
        for node in nodes
        if node.get("kind") == "boss" and node.get("id") in UNRESOLVED_BOSS_LOCATION_NODES
    }
    unresolved_boss_location_contract = {
        "expected_nodes": sorted(UNRESOLVED_BOSS_LOCATION_NODES),
        "actual_nodes": sorted(unresolved_boss_nodes),
        "invalid_nodes": [
            node_id
            for node_id, node in unresolved_boss_nodes.items()
            if node.get("onlineCoordinate")
            or not node.get("onlineTextLocation")
            or node["onlineTextLocation"].get("coordinateAvailable") is not False
            or node["onlineTextLocation"].get("anchorNodeId") not in node_by_id
        ],
    }
    if (
        unresolved_boss_location_contract["actual_nodes"] != unresolved_boss_location_contract["expected_nodes"]
        or unresolved_boss_location_contract["invalid_nodes"]
    ):
        raise ValueError(f"unresolved boss location contract failed: {unresolved_boss_location_contract}")
    online_coordinate_nodes = [node for node in nodes if node.get("onlineCoordinate")]
    invalid_coordinate_nodes = [
        node["id"]
        for node in online_coordinate_nodes
        if not all(
            [
                node["onlineCoordinate"].get("source"),
                node["onlineCoordinate"].get("snapshot"),
                node["onlineCoordinate"].get("sourceIndex") is not None,
                node["onlineCoordinate"].get("recordId") is not None,
                node["onlineCoordinate"].get("name"),
                node["onlineCoordinate"].get("map"),
                node["onlineCoordinate"].get("coordinateSpace") == "game_world_xyz",
                isinstance(node["onlineCoordinate"].get("position"), list)
                and len(node["onlineCoordinate"].get("position")) == 3,
            ]
        )
    ]
    map_point_records = load_online_map_point_records()
    boss_position_records = load_online_boss_position_records()
    invalid_coordinate_bindings = []
    unresolved_formal_candidates = []
    manual_bindings = []
    shared_coordinate_groups = {}
    manual_binding_roles = {"landmark_anchor", "boss_arena_anchor", "shared_boss_encounter_anchor", "named_dungeon_location_anchor"}
    checked_source_records = 0
    for node in online_coordinate_nodes:
        if node["id"] in invalid_coordinate_nodes:
            continue
        coordinate = node["onlineCoordinate"]
        if coordinate.get("source") != "map_for_goblins":
            continue
        checked_source_records += 1
        key = (
            str(coordinate["snapshot"]),
            int(coordinate["sourceIndex"]),
            int(coordinate["recordId"]),
        )
        shared_group = coordinate.get("sharedCoordinateGroup")
        if shared_group:
            shared_coordinate_groups.setdefault(str(shared_group), []).append(
                {"node": node["id"], "key": list(key)}
            )
        source_snapshot = str(coordinate["snapshot"])
        if source_snapshot == ONLINE_BOSS_POSITION_FILE.stem:
            row = boss_position_records.get(key)
            source_kind = "boss_position"
            formal_candidates = (row[13] if row is not None else []) or []
            source_names = [row[1]] if row is not None else []
            expected_map = row[2] if row is not None else None
            expected_position = row[6:9] if row is not None else None
        else:
            row = map_point_records.get(key)
            source_kind = "map_point"
            formal_candidates = (row[10] if row is not None else []) or []
            source_names = (row[9] if row is not None else []) or []
            expected_map = f"area {row[3]} / grid {row[4]},{row[5]}" if row is not None else None
            expected_position = row[6:9] if row is not None else None
        if row is None:
            invalid_coordinate_bindings.append({"node": node["id"], "reason": "source_record_not_found", "key": key})
            continue
        if node["id"] not in formal_candidates:
            candidate_issue = {
                "node": node["id"],
                "reason": "formal_candidate_mismatch" if formal_candidates else "no_formal_candidate",
                "recordId": key[2],
                "sourceKind": source_kind,
                "formalCandidates": formal_candidates,
            }
            binding_basis = coordinate.get("bindingBasis")
            manual_name_match = coordinate.get("name") in source_names
            if binding_basis in {"manual_exact_name_region", "manual_source_alias_region", "manual_shared_encounter"} and manual_name_match:
                if coordinate.get("coordinateRole") not in manual_binding_roles:
                    invalid_coordinate_bindings.append(
                        {
                            **candidate_issue,
                            "reason": "invalid_manual_coordinate_role",
                            "coordinateRole": coordinate.get("coordinateRole"),
                        }
                    )
                    continue
                manual_bindings.append(
                    {
                        **candidate_issue,
                        "bindingBasis": binding_basis,
                        "coordinateRole": coordinate.get("coordinateRole"),
                        "sourceKind": source_kind,
                        "sourceNames": source_names,
                    }
                )
            elif node.get("kind") in {"grace", "boss", "entrance"} and formal_candidates:
                invalid_coordinate_bindings.append(candidate_issue)
                continue
            else:
                unresolved_formal_candidates.append(candidate_issue)
        if coordinate["position"] != expected_position:
            invalid_coordinate_bindings.append({"node": node["id"], "reason": "position_mismatch", "recordId": key[2], "sourceKind": source_kind})
        elif coordinate["name"] not in source_names:
            invalid_coordinate_bindings.append({"node": node["id"], "reason": "name_mismatch", "recordId": key[2], "sourceKind": source_kind})
        elif coordinate["map"] != expected_map:
            invalid_coordinate_bindings.append({"node": node["id"], "reason": "map_layer_mismatch", "recordId": key[2], "sourceKind": source_kind, "expected": expected_map})
    for group, entries in shared_coordinate_groups.items():
        source_keys = {tuple(entry["key"]) for entry in entries}
        if len(source_keys) > 1:
            invalid_coordinate_bindings.append(
                {
                    "reason": "shared_coordinate_group_mismatch",
                    "sharedCoordinateGroup": group,
                    "entries": entries,
                }
            )
    online_coordinate_contract = {
        "node_count": len(online_coordinate_nodes),
        "invalid_nodes": invalid_coordinate_nodes,
        "source_records_checked": checked_source_records,
        "invalid_bindings": invalid_coordinate_bindings,
        "manual_bindings": manual_bindings,
        "unresolved_formal_candidates": unresolved_formal_candidates,
        "shared_coordinate_groups": shared_coordinate_groups,
    }
    if online_coordinate_contract["invalid_nodes"] or online_coordinate_contract["invalid_bindings"]:
        raise ValueError(f"online coordinate contract failed: {online_coordinate_contract}")
    topology_adjacency: dict[str, set[str]] = {}
    for edge in graph["edges"]:
        topology_adjacency.setdefault(edge["from"], set()).add(edge["to"])

    all_condition_ids = graph_condition_ids
    condition_adjacency: dict[str, set[str]] = {}
    for edge in graph["edges"]:
        if edge.get("routeable") is False or not set(edge.get("requires", [])).issubset(all_condition_ids):
            continue
        condition_adjacency.setdefault(edge["from"], set()).add(edge["to"])

    def shortest_grace_path(target_id: str):
        best = None
        for grace in formal_graces:
            start = grace["id"]
            if start == target_id:
                continue
            seen = {start}
            queue = [(start, 0)]
            while queue:
                current, hops = queue.pop(0)
                if current == target_id:
                    candidate = {"origin": start, "target": target_id, "hops": hops}
                    if best is None or hops < best["hops"]:
                        best = candidate
                    break
                for neighbor in condition_adjacency.get(current, set()):
                    if neighbor not in seen:
                        seen.add(neighbor)
                        queue.append((neighbor, hops + 1))
        if best is None and target_id in {grace["id"] for grace in formal_graces}:
            return {"origin": target_id, "target": target_id, "hops": 0}
        return best

    achievement_route_coverage = []
    for record in achievements["records"]:
        target_ids = list(dict.fromkeys(record.get("formal_target_ids", []) + record.get("location_target_ids", [])))
        paths = [path for target_id in target_ids if (path := shortest_grace_path(target_id))]
        achievement_route_coverage.append(
            {
                "achievement": record["canonical_id"],
                "target_ids": target_ids,
                "best_grace_path": min(paths, key=lambda path: path["hops"]) if paths else None,
                "route_assessment": "formal_graph_path_exists_with_all_registered_conditions"
                if paths
                else "no_formal_grace_path_or_target_mapping",
            }
        )

    def topology_reachable(start: str, goal: str) -> bool:
        if start == goal:
            return True
        seen = {start}
        queue = [start]
        while queue:
            current = queue.pop()
            for neighbor in topology_adjacency.get(current, set()):
                if neighbor == goal:
                    return True
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        return False

    grace_ids = {node["id"] for node in formal_graces}
    normal_profile_adjacency = {node_id: set(neighbors) for node_id, neighbors in topology_adjacency.items()}
    for grace_id in grace_ids:
        normal_profile_adjacency.setdefault(grace_id, set()).update(grace_ids - {grace_id})

    def normal_profile_reachable(start: str, goal: str) -> bool:
        if start == goal:
            return True
        seen = {start}
        queue = [start]
        while queue:
            current = queue.pop()
            for neighbor in normal_profile_adjacency.get(current, set()):
                if neighbor == goal:
                    return True
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        return False

    endpoint_exact = 0
    endpoint_ambiguous = 0
    endpoint_unmapped = []
    exact_endpoint_without_path = []
    endpoint_alias_matches = 0
    direct_edge_match = 0
    topology_path_match = 0
    normal_profile_path_match = 0
    normal_profile_matches = []

    endpoint_resolution_matches = 0

    def route_candidates(name: str, region: str = "", leg: dict | None = None, direction: str = "") -> list[dict]:
        nonlocal endpoint_alias_matches, endpoint_resolution_matches
        if leg:
            resolved_id = ROUTE_ENDPOINT_RESOLUTIONS.get(leg["canonical_id"], {}).get(direction)
            if resolved_id in node_by_id:
                endpoint_resolution_matches += 1
                return [node_by_id[resolved_id]]
        name_key = norm(name)
        region_key = norm(region)
        # The guide reuses "Erdtree Sanctuary" for both capital epochs.  The
        # Ashen Capital record must resolve to its own floor node; otherwise a
        # valid post-Maliketh route is falsely compared against pre-Maliketh.
        if name_key == "erdtreesanctuary" and "ashen" in region_key:
            alias_id = "grace_ashen_erdtree_sanctuary"
        else:
            alias_id = ROUTE_ENDPOINT_ALIASES.get(name_key)
        if alias_id in node_by_id:
            endpoint_alias_matches += 1
            return [node_by_id[alias_id]]
        return candidates_for(label_index, name, region)

    for leg in legs["records"]:
        from_candidates = route_candidates(leg["from"], leg["region_name"], leg, "from")
        to_candidates = route_candidates(leg["to"], leg["region_name"], leg, "to")
        if len(from_candidates) == 1 and len(to_candidates) == 1:
            endpoint_exact += 1
            pair = (from_candidates[0]["id"], to_candidates[0]["id"])
            reverse = (pair[1], pair[0])
            if pair in route_edges or reverse in route_edges:
                direct_edge_match += 1
            if topology_reachable(*pair):
                topology_path_match += 1
            else:
                exact_endpoint_without_path.append(
                    {
                        "catalog_id": leg["canonical_id"],
                        "from": leg["from"],
                        "to": leg["to"],
                        "formal_from": pair[0],
                        "formal_to": pair[1],
                    }
                )
                if normal_profile_reachable(*pair):
                    normal_profile_path_match += 1
                    normal_profile_matches.append(
                        {
                            "catalog_id": leg["canonical_id"],
                            "from": leg["from"],
                            "to": leg["to"],
                            "formal_from": pair[0],
                            "formal_to": pair[1],
                            "profile": "normal_fast_travel",
                            "requires": [route_profiles["fastTravelRule"]["id"]],
                        }
                    )
        elif len(from_candidates) > 1 or len(to_candidates) > 1:
            endpoint_ambiguous += 1
        else:
            endpoint_unmapped.append(
                {
                    "catalog_id": leg["canonical_id"],
                    "from": leg["from"],
                    "to": leg["to"],
                }
            )

    expected_physical_route_discontinuities = {
        "er_guide_leg_dlc-scadu-altus-03",
        "er_guide_leg_dlc-south-03",
        "er_guide_leg_dlc-west-05",
        "er_guide_leg_mtgelmir-03",
    }
    physical_route_discontinuity_contract = {
        "actual": sorted(item["catalog_id"] for item in exact_endpoint_without_path),
        "expected": sorted(expected_physical_route_discontinuities),
        "normal_fast_travel_profiles": sorted(item["catalog_id"] for item in normal_profile_matches),
    }
    if physical_route_discontinuity_contract["actual"] != physical_route_discontinuity_contract["expected"]:
        raise ValueError(f"physical route discontinuity contract failed: {physical_route_discontinuity_contract}")
    route_assessment_records = route_assessments.get("records", [])
    route_assessment_contract = {
        "declared_records": route_assessments.get("record_count"),
        "records": len(route_assessment_records),
        "expected_route_leg_ids": sorted(expected_physical_route_discontinuities),
        "actual_route_leg_ids": sorted(record.get("route_leg_id") for record in route_assessment_records),
        "invalid_statuses": [
            record.get("route_leg_id") for record in route_assessment_records if record.get("status") != "normal_fast_travel_only"
        ],
        "invalid_profiles": [
            record.get("route_leg_id") for record in route_assessment_records if record.get("route_profile") != "normal_fast_travel"
        ],
        "routeable_records": [record.get("route_leg_id") for record in route_assessment_records if record.get("routeable")],
        "invalid_formal_endpoints": [
            record.get("route_leg_id")
            for record in route_assessment_records
            if record.get("formal_from") not in node_by_id or record.get("formal_to") not in node_by_id
        ],
    }
    if (
        route_assessment_contract["declared_records"] != 4
        or route_assessment_contract["records"] != 4
        or route_assessment_contract["actual_route_leg_ids"] != route_assessment_contract["expected_route_leg_ids"]
        or route_assessment_contract["invalid_statuses"]
        or route_assessment_contract["invalid_profiles"]
        or route_assessment_contract["routeable_records"]
        or route_assessment_contract["invalid_formal_endpoints"]
    ):
        raise ValueError(f"route assessment contract failed: {route_assessment_contract}")
    expected_broad_route_legs = {
        "er_guide_leg_caelid-04",
        "er_guide_leg_caelid-06",
        "er_guide_leg_dlc-scadu-altus-01",
        "er_guide_leg_dlc-scadu-altus-02",
        "er_guide_leg_dlc-scadu-altus-04",
        "er_guide_leg_dlc-scadu-altus-05",
        "er_guide_leg_dlc-scadu-altus-07",
        "er_guide_leg_dragonbarrow-02",
    }
    broad_route_endpoint_contract = {
        "actual": sorted(item["catalog_id"] for item in endpoint_unmapped),
        "expected": sorted(expected_broad_route_legs),
    }
    if broad_route_endpoint_contract["actual"] != broad_route_endpoint_contract["expected"]:
        raise ValueError(f"broad route endpoint contract failed: {broad_route_endpoint_contract}")
    target_group_records = route_target_groups.get("records", [])
    online_item_snapshot_contract = {}
    for leg_id, item_snapshot in item_snapshots.items():
        leg = next(record for record in legs["records"] if record["canonical_id"] == leg_id)
        target_group = next(record for record in target_group_records if record.get("route_leg_id") == leg_id)
        item_records = item_snapshot.get("records", [])
        expected_item_ids = set(leg.get("item_ids", []))
        actual_item_ids = [record.get("id") for record in item_records]
        expected_snapshot_id = f"er-guide-items-{leg_id.removeprefix('er_guide_leg_')}-20260818"
        contract = {
            "declared_records": item_snapshot.get("record_count"),
            "records": len(item_records),
            "expected_source_item_ids": len(expected_item_ids),
            "missing_source_item_ids": sorted(expected_item_ids - set(actual_item_ids)),
            "unexpected_item_ids": sorted(set(actual_item_ids) - expected_item_ids),
            "duplicate_item_ids": sorted(
                item for item in set(actual_item_ids) if actual_item_ids.count(item) > 1
            ),
            "coordinate_records": sum(record.get("map") is not None for record in item_records),
            "declared_coordinate_records": item_snapshot.get("coordinate_record_count"),
            "routeable": item_snapshot.get("routeable"),
            "source_commit": item_snapshot.get("source", {}).get("commit"),
            "source_path": item_snapshot.get("source", {}).get("path"),
            "target_group_reference_valid": (
                item_snapshot.get("route_target_group_id") == target_group.get("canonical_id")
                and target_group.get("online_item_snapshot") == expected_snapshot_id
                and target_group.get("online_item_snapshot_path") == f"data/v1/source-snapshots/{expected_snapshot_id}.json"
            ),
        }
        expected_count = len(expected_item_ids)
        expected_coordinate_count = EXPECTED_ITEM_COORDINATE_COUNTS[leg_id]
        if (
            contract["declared_records"] != expected_count
            or contract["records"] != expected_count
            or contract["expected_source_item_ids"] != expected_count
            or contract["missing_source_item_ids"]
            or contract["unexpected_item_ids"]
            or contract["duplicate_item_ids"]
            or contract["coordinate_records"] != expected_coordinate_count
            or contract["declared_coordinate_records"] != expected_coordinate_count
            or contract["routeable"] is not False
            or contract["source_commit"] != "7f24d64d3631ef4d549f56b42d4c3e3817a269fa"
            or contract["source_path"] != "data/items.json"
            or not contract["target_group_reference_valid"]
        ):
            raise ValueError(f"online item snapshot contract failed: {leg_id}: {contract}")
        online_item_snapshot_contract[leg_id] = contract
    invalid_target_group_subroutes = []
    for record in target_group_records:
        declared_targets = set(record.get("resolved_formal_target_ids", []))
        for subroute in record.get("subroutes", []):
            edge_ids = list(subroute.get("path_edge_ids", []))
            path_edges = [edge_by_id.get(edge_id) for edge_id in edge_ids]
            path_requires = set()
            if any(edge is None for edge in path_edges):
                invalid_target_group_subroutes.append(
                    {"group": record.get("canonical_id"), "target": subroute.get("target_node_id"), "reason": "missing_edge_id"}
                )
                continue
            for edge in path_edges:
                path_requires.update(edge.get("requires", []))
            if any(edge.get("routeable") is False for edge in path_edges):
                invalid_target_group_subroutes.append(
                    {"group": record.get("canonical_id"), "target": subroute.get("target_node_id"), "reason": "non_routeable_edge"}
                )
            if path_edges[0]["from"] != subroute.get("entry_node_id"):
                invalid_target_group_subroutes.append(
                    {"group": record.get("canonical_id"), "target": subroute.get("target_node_id"), "reason": "entry_mismatch"}
                )
            if path_edges[-1]["to"] != subroute.get("target_node_id"):
                invalid_target_group_subroutes.append(
                    {"group": record.get("canonical_id"), "target": subroute.get("target_node_id"), "reason": "target_mismatch"}
                )
            if any(left["to"] != right["from"] for left, right in zip(path_edges, path_edges[1:])):
                invalid_target_group_subroutes.append(
                    {"group": record.get("canonical_id"), "target": subroute.get("target_node_id"), "reason": "path_discontinuity"}
                )
            if set(subroute.get("requires", [])) != path_requires:
                invalid_target_group_subroutes.append(
                    {"group": record.get("canonical_id"), "target": subroute.get("target_node_id"), "reason": "condition_mismatch"}
                )
            if not set(subroute.get("requires", [])).issubset(graph_condition_ids):
                invalid_target_group_subroutes.append(
                    {"group": record.get("canonical_id"), "target": subroute.get("target_node_id"), "reason": "unknown_condition"}
                )
            if subroute.get("target_node_id") not in declared_targets:
                invalid_target_group_subroutes.append(
                    {"group": record.get("canonical_id"), "target": subroute.get("target_node_id"), "reason": "target_not_declared"}
                )
    target_group_contract = {
        "declared_records": route_target_groups.get("record_count"),
        "records": len(target_group_records),
        "duplicate_ids": sorted(
            item for item in {record.get("canonical_id") for record in target_group_records}
            if item and sum(1 for record in target_group_records if record.get("canonical_id") == item) > 1
        ),
        "expected_broad_route_leg_ids": sorted(expected_broad_route_legs),
        "actual_broad_route_leg_ids": sorted(record.get("route_leg_id") for record in target_group_records),
        "invalid_formal_target_ids": sorted(
            target_id
            for record in target_group_records
            for target_id in record.get("resolved_formal_target_ids", [])
            if target_id not in node_by_id
        ),
        "routeable_records": [record.get("canonical_id") for record in target_group_records if record.get("routeable")],
        "subroute_count": sum(len(record.get("subroutes", [])) for record in target_group_records),
        "invalid_subroutes": invalid_target_group_subroutes,
        "missing_source_evidence": [
            record.get("canonical_id")
            for record in target_group_records
            if not set(record.get("source_evidence", [])).issubset(known_evidence_ids)
        ],
        "item_snapshot_references_valid": all(
            record.get("online_item_snapshot")
            and record.get("online_item_snapshot_path")
            and record.get("online_item_record_count") == online_item_snapshot_contract[record["route_leg_id"]]["records"]
            and record.get("online_item_coordinate_count") == online_item_snapshot_contract[record["route_leg_id"]]["coordinate_records"]
            and record.get("item_target_status") in {
                "all_source_ids_resolved_coordinates_partial",
                "all_source_ids_resolved_coordinates_complete",
            }
            for record in target_group_records if record.get("route_leg_id") in ER_GUIDE_ITEM_SNAPSHOT_FILES
        ),
        "item_snapshots": online_item_snapshot_contract,
    }
    if (
        target_group_contract["declared_records"] != 8
        or target_group_contract["records"] != 8
        or target_group_contract["duplicate_ids"]
        or target_group_contract["actual_broad_route_leg_ids"] != target_group_contract["expected_broad_route_leg_ids"]
        or target_group_contract["invalid_formal_target_ids"]
        or target_group_contract["routeable_records"]
        or target_group_contract["missing_source_evidence"]
        or not target_group_contract["item_snapshot_references_valid"]
        or target_group_contract["invalid_subroutes"]
    ):
        raise ValueError(f"route target group contract failed: {target_group_contract}")
    route_endpoint_resolution_contract = {
        "expected_bindings": 17,
        "actual_bindings": endpoint_resolution_matches,
        "expected_leg_ids": sorted(EXPECTED_ROUTE_ENDPOINT_RESOLUTION_LEGS),
        "resolved_leg_ids": sorted(ROUTE_ENDPOINT_RESOLUTIONS),
    }
    if (
        route_endpoint_resolution_contract["actual_bindings"] != route_endpoint_resolution_contract["expected_bindings"]
        or route_endpoint_resolution_contract["resolved_leg_ids"] != route_endpoint_resolution_contract["expected_leg_ids"]
    ):
        raise ValueError(f"route endpoint resolution contract failed: {route_endpoint_resolution_contract}")

    return {
        "graph": {
            "version": graph["meta"]["version"],
            "nodes": len(nodes),
            "edges": len(graph["edges"]),
            "grace_nodes": len(formal_graces),
            "layers": dict(Counter(node.get("layer") for node in nodes)),
            "world_epochs": dict(Counter(node.get("worldEpoch") for node in nodes)),
        },
        "sites_of_grace_catalog": {
            "records": len(catalog["records"]),
            "bound_to_formal_node": len(bindings),
            "binding_methods": dict(Counter(item["method"] for item in bindings)),
            "formal_kind_mismatch": [item for item in bindings if item["formal_kind"] != "grace"],
            "ambiguous": ambiguous,
            "unmapped": unmapped,
            "formal_graces_without_catalog_binding": [
                node["id"] for node in formal_graces if node["id"] not in bound_ids
            ],
            "catalog_anomaly_contract": catalog_anomaly_contract,
        },
        "p0_achievement_catalog": {
            **achievement_contract,
            "formal_target_bound_records": sum(bool(record.get("formal_target_ids")) for record in achievements["records"]),
            "location_target_bound_records": sum(bool(record.get("location_target_ids")) for record in achievements["records"]),
            "prerequisite_target_bound_records": sum(bool(record.get("prerequisite_target_ids")) for record in achievements["records"]),
            "state_bound_records": sum(
                bool(record.get("state_requirements") or record.get("effect_conditions"))
                for record in achievements["records"]
            ),
            "location_target_group_count": sum(
                len(record.get("location_target_groups", [])) for record in achievements["records"]
            ),
            "unbound_records": [
                record["canonical_id"] for record in achievements["records"] if not record.get("formal_target_ids")
            ],
            "collection_requirement_counts": {
                record["canonical_id"]: len(record.get("required_item_names", []))
                for record in achievements["records"]
                if record.get("category") == "collection"
            },
            "online_item_placement_coverage": collection_item_coverage,
            "formal_graph_grace_path_coverage": {
                "condition_assumption": "all_registered_conditions_enabled; this is a coverage audit, not a current-player state",
                "records_with_target_mapping": sum(bool(item["target_ids"]) for item in achievement_route_coverage),
                "records_with_path": sum(bool(item["best_grace_path"]) for item in achievement_route_coverage),
                "records_without_path": [
                    item["achievement"]
                    for item in achievement_route_coverage
                    if item["target_ids"] and not item["best_grace_path"]
                ],
                "records_without_target_mapping": [
                    item["achievement"] for item in achievement_route_coverage if not item["target_ids"]
                ],
                "records": achievement_route_coverage,
            },
        },
        "route_leg_catalog": {
            "records": len(legs["records"]),
            "endpoint_exact_matches": endpoint_exact,
            "endpoint_alias_matches": endpoint_alias_matches,
            "endpoint_resolution_matches": endpoint_resolution_matches,
            "endpoint_ambiguous": endpoint_ambiguous,
            "direct_or_reverse_formal_edge_matches": direct_edge_match,
            "formal_topology_path_matches": topology_path_match,
            "normal_fast_travel_profile_matches": normal_profile_path_match,
            "normal_fast_travel_matches": normal_profile_matches,
            "exact_endpoint_without_topology_path": exact_endpoint_without_path,
            "endpoint_unmapped_or_broad_sweep": endpoint_unmapped,
            "physical_route_discontinuity_contract": physical_route_discontinuity_contract,
            "broad_route_endpoint_contract": broad_route_endpoint_contract,
            "endpoint_resolution_contract": route_endpoint_resolution_contract,
        },
        "route_target_group_contract": target_group_contract,
        "route_assessment_contract": route_assessment_contract,
        "online_item_snapshot_contract": online_item_snapshot_contract,
        "transition_contract": transition_contract,
        "online_snapshot_contract": online_snapshot_contract,
        "online_map_key_contract": online_map_key_contract,
        "projected_anchor_contract": projected_anchor_contract,
        "named_grace_coordinate_contract": named_grace_contract,
        "map_point_candidate_contract": map_point_candidate_contract,
        "online_text_location_contract": online_text_location_contract,
        "unresolved_boss_location_contract": unresolved_boss_location_contract,
        "online_coordinate_contract": online_coordinate_contract,
        "safety": {
            "game_process_accessed": False,
            "game_files_accessed": False,
            "writes_performed": False,
            "semantic_relations_promoted_to_edges": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit online catalog coverage without touching the game.")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    args = parser.parse_args()
    print(json.dumps(audit(), ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=args.pretty))


if __name__ == "__main__":
    main()
