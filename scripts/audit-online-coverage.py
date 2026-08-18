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


def audit() -> dict:
    graph = load("data/v1/graph.json")
    catalog = load("data/v1/entities/sites-of-grace.json")
    achievements = load("data/v1/entities/achievements.json")
    legs = load("data/v1/entities/er-guide-route-legs.json")
    route_profiles = load("data/v1/route-profiles.json")
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
    route_edges = {(edge["from"], edge["to"]) for edge in graph["edges"]}
    node_ids = set(node_by_id)
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

    def route_candidates(name: str, region: str = "") -> list[dict]:
        nonlocal endpoint_alias_matches
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
        from_candidates = route_candidates(leg["from"], leg["region_name"])
        to_candidates = route_candidates(leg["to"], leg["region_name"])
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
            "endpoint_ambiguous": endpoint_ambiguous,
            "direct_or_reverse_formal_edge_matches": direct_edge_match,
            "formal_topology_path_matches": topology_path_match,
            "normal_fast_travel_profile_matches": normal_profile_path_match,
            "normal_fast_travel_matches": normal_profile_matches,
            "exact_endpoint_without_topology_path": exact_endpoint_without_path,
            "endpoint_unmapped_or_broad_sweep": endpoint_unmapped,
        },
        "transition_contract": transition_contract,
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
