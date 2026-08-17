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


def audit() -> dict:
    graph = load("data/v1/graph.json")
    catalog = load("data/v1/entities/sites-of-grace.json")
    legs = load("data/v1/entities/er-guide-route-legs.json")
    nodes = graph["nodes"]
    node_by_id = {node["id"]: node for node in nodes}
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
    topology_adjacency: dict[str, set[str]] = {}
    for edge in graph["edges"]:
        topology_adjacency.setdefault(edge["from"], set()).add(edge["to"])

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

    endpoint_exact = 0
    endpoint_ambiguous = 0
    endpoint_unmapped = []
    direct_edge_match = 0
    topology_path_match = 0
    for leg in legs["records"]:
        from_candidates = candidates_for(label_index, leg["from"], leg["region_name"])
        to_candidates = candidates_for(label_index, leg["to"], leg["region_name"])
        if len(from_candidates) == 1 and len(to_candidates) == 1:
            endpoint_exact += 1
            pair = (from_candidates[0]["id"], to_candidates[0]["id"])
            reverse = (pair[1], pair[0])
            if pair in route_edges or reverse in route_edges:
                direct_edge_match += 1
            if topology_reachable(*pair):
                topology_path_match += 1
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
        "route_leg_catalog": {
            "records": len(legs["records"]),
            "endpoint_exact_matches": endpoint_exact,
            "endpoint_ambiguous": endpoint_ambiguous,
            "direct_or_reverse_formal_edge_matches": direct_edge_match,
            "formal_topology_path_matches": topology_path_match,
            "endpoint_unmapped_or_broad_sweep": endpoint_unmapped,
        },
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
