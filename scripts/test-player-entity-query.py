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


def abstract_entity_route_query(**params: object) -> dict:
    return get("/api/catalog/player-entity-abstract-route?" + urlencode(params, doseq=True))


def main() -> int:
    registry = json.loads(
        (ROOT / "data" / "v1" / "entities" / "entity-registry.json").read_text(encoding="utf-8")
    )
    reinforce_catalog = json.loads(
        (ROOT / "data" / "v1" / "entities" / "reinforce-catalog.json").read_text(encoding="utf-8")
    )
    assert registry["stats"]["ash_of_war"] == 116, registry["stats"]
    assert registry["stats"]["ash_of_war_source_rows"] == 141, registry["stats"]
    assert registry["stats"]["excluded_ash_of_war"] == 5, registry["stats"]
    assert registry["stats"]["excluded_armor_appearance_rows"] == 41, registry["stats"]
    assert registry["stats"]["excluded_internal_weapon_rows"] == 5, registry["stats"]
    assert registry["stats"]["excluded_internal_armor_rows"] == 23, registry["stats"]
    assert registry["stats"]["excluded_internal_accessory_rows"] == 1, registry["stats"]
    assert registry["stats"]["excluded_cut_gesture_rows"] == 3, registry["stats"]
    assert registry["stats"]["excluded_cut_goods_rows"] == 23, registry["stats"]
    exclusion_stat_total = sum(
        value
        for key, value in registry["stats"].items()
        if key.startswith("excluded_")
    )
    assert len(registry["exclusions"]) == exclusion_stat_total, (
        len(registry["exclusions"]), exclusion_stat_total
    )
    gesture_exclusion_rows = {
        exclusion["row"]
        for exclusion in registry["exclusions"]
        if exclusion.get("kind") == "gesture"
    }
    assert gesture_exclusion_rows == {55, 96, 110}, gesture_exclusion_rows
    cut_goods_rows = {
        exclusion["row"]
        for exclusion in registry["exclusions"]
        if exclusion.get("param") == "EquipParamGoods"
    }
    assert cut_goods_rows == {
        3020, 8147, 8192, 8195, 9304, 9195, 8156, 8181, 1570,
        8861, 8860, 8863, 3300, 8189, 8102, 8706, 8756, 480,
        1220, 1350, 8934, 9393, 2008023,
    }, cut_goods_rows
    cut_goods_ids = {
        "item_miranda_s_prayer",
        "item_asimi_silver_tear",
        "item_asimi_s_husk",
        "item_asimi_silver_chrysalid",
        "item_fugitive_warrior_s_recipe_5",
        "item_about_multiplayer", "item_burial_crow_s_letter",
        "item_drawstring_freezing_grease", "item_erdtree_codex",
        "item_erdtree_prayerbook", "item_golden_order_principles",
        "item_holy_water_grease", "item_iji_s_confession",
        "item_lucent_baldachin_s_blessing", "item_note_great_coffins",
        "item_roped_freezing_pot",
    }
    assert not cut_goods_ids.intersection(
        entity["id"] for entity in registry["entities"]
    ), "cut goods must remain evidence-layer exclusions, not player targets"
    assert not any(
        entity.get("kind") == "armor"
        and entity.get("properties", {}).get("protectorCategory") == 4
        for entity in registry["entities"]
    ), "appearance/body-type protector rows must not be published as armor"
    weapon_entities = [
        entity for entity in registry["entities"]
        if entity.get("kind") == "weapon"
    ]
    weapon_families = {
        entity.get("properties", {}).get("weaponFamily")
        for entity in weapon_entities
    }
    assert weapon_families == {
        "melee", "bow", "crossbow", "ballista", "staff", "sacred_seal",
        "shield", "torch", "hand_to_hand", "perfume",
    }, weapon_families
    assert sum(entity["properties"].get("weaponFamily") == "shield" for entity in weapon_entities) == 79
    assert sum(entity["properties"].get("weaponFamily") == "sacred_seal" for entity in weapon_entities) == 12
    spirit_ashes = [
        entity for entity in registry["entities"]
        if entity.get("category") == "spirit_ash"
    ]
    assert len(spirit_ashes) == 84, len(spirit_ashes)
    assert all(entity.get("variant_count") == 11 for entity in spirit_ashes), spirit_ashes
    assert not any(
        "+1" in entity.get("name", {}).get("en", "")
        for entity in spirit_ashes
    ), spirit_ashes
    flask_entities = [
        entity for entity in registry["entities"]
        if entity.get("id") in {
            "item_flask_of_crimson_tears",
            "item_flask_of_cerulean_tears",
        }
    ]
    assert len(flask_entities) == 2, flask_entities
    assert all(entity.get("category") == "consumable" for entity in flask_entities)
    assert all(entity.get("variant_count") == 26 for entity in flask_entities)
    assert all(
        entity.get("properties", {}).get("variantKind") == "reinforcement_state"
        for entity in flask_entities
    )
    assert not any(
        entity.get("id", "").startswith((
            "item_flask_of_crimson_tears_",
            "item_flask_of_cerulean_tears_",
        ))
        for entity in registry["entities"]
    ), "flask reinforcement states must not be separate canonical entities"
    glovewort_categories = {
        entity.get("category")
        for entity in registry["entities"]
        if entity.get("id", "").startswith((
            "item_grave_glovewort_",
            "item_ghost_glovewort_",
            "item_great_grave_glovewort",
            "item_great_ghost_glovewort",
        )) and "_picker_s_" not in entity.get("id", "")
    }
    assert glovewort_categories == {"grave_glovewort", "ghost_glovewort"}, glovewort_categories
    assert sum(entity.get("category") == "grave_glovewort" for entity in registry["entities"]) == 10
    assert sum(entity.get("category") == "ghost_glovewort" for entity in registry["entities"]) == 10
    spirit_reinforcements = [
        relation for relation in reinforce_catalog["reinforcements"]
        if relation.get("class") in {"grave_glovewort", "ghost_glovewort"}
    ]
    assert len(spirit_reinforcements) == 840, len(spirit_reinforcements)
    assert all(relation.get("maxLevel") == 10 for relation in spirit_reinforcements)
    assert not any(
        relation.get("from", "").startswith("armor_")
        for relation in reinforce_catalog["reinforcements"]
    )

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

        shield_query = query(q="盾牌", limit=100)
        assert shield_query["total_matches"] >= 79, shield_query
        assert sum(row.get("weaponFamily") == "shield" for row in shield_query["records"]) == 79
        shield_family = query(family="shield", limit=100)
        assert shield_family["total_matches"] == 79, shield_family
        bloody_longsword = query(q="Bloody Longsword")
        assert bloody_longsword["total_matches"] >= 1, bloody_longsword
        assert bloody_longsword["records"][0]["id"] == "weapon_longsword", bloody_longsword
        assert all(row.get("weaponFamily") == "shield" for row in shield_family["records"])
        seal_family = query(family="sacred_seal", limit=100)
        assert seal_family["total_matches"] == 12, seal_family

        spell = query(q="帚星", limit=100)
        comet = next((row for row in spell["records"] if row["id"] == "spell_comet"), None)
        assert comet is not None, spell
        comet = query(id="spell_comet")["entity"]
        online_relations = [
            relation for relation in comet["acquisitions"]
            if relation.get("method") == "online_map"
        ]
        assert online_relations, comet
        assert online_relations[0]["topologyBinding"]["status"] == "coordinate_endpoint", comet
        assert online_relations[0]["topologyBinding"]["mapBindingStatus"] == "external_map_scope", comet
        assert online_relations[0]["endpointInstances"][0]["kind"] == "online_map_marker", comet

        aether_item = query(id="weapon_black_key_bolt")
        assert aether_item["found"] is True, aether_item
        guide_relations = [
            relation for relation in aether_item["entity"]["acquisitions"]
            if relation.get("method") == "online_guide"
        ]
        assert guide_relations, aether_item
        guide_relation = guide_relations[0]
        assert guide_relation["verification"] == "online_guide_exact_unique_official_name_match", guide_relation
        assert guide_relation["items"][0]["externalSourceName"] == "Black-Key Bolt", guide_relation
        guide_endpoint = guide_relation["endpointInstances"][0]
        assert guide_endpoint["kind"] == "online_guide_marker", guide_endpoint
        assert guide_endpoint["coordinateSpace"] == "aether_map_lat_lng", guide_endpoint
        assert guide_endpoint["topologyBinding"]["status"] == "coordinate_endpoint", guide_endpoint
        assert guide_endpoint["topologyBinding"]["mapBindingStatus"] == "external_map_scope", guide_endpoint
        assert not guide_endpoint["topologyBinding"]["routeNodeIds"], guide_endpoint

        map_item = query(id="item_thin_beast_bones")
        assert map_item["found"] is True, map_item
        map_relations = [
            relation for relation in map_item["entity"]["acquisitions"]
            if relation.get("method") == "online_item_map"
        ]
        assert len(map_relations) >= 100, map_item
        map_endpoint = map_relations[0]["endpointInstances"][0]
        assert map_endpoint["kind"] == "online_item_map_endpoint", map_endpoint
        assert map_endpoint["coordinateSpace"] == "game_world_xyz", map_endpoint
        assert map_endpoint["placementType"] in {"enemy", "treasure", "emevd", "emevd_treasure", None}, map_endpoint
        assert map_endpoint["topologyBinding"]["status"] == "coordinate_endpoint", map_endpoint
        assert map_endpoint["topologyBinding"]["mapBindingStatus"] in {
            "exact_map_instance", "exact_map_instance_alias", "unresolved_map_instance"
        }, map_endpoint
        if map_endpoint["topologyBinding"]["mapBindingStatus"] in {
            "exact_map_instance", "exact_map_instance_alias"
        }:
            assert map_endpoint["topologyBinding"]["mapNodeIds"], map_endpoint

        param_id_item = query(id="item_lost_ashes_of_war")
        assert param_id_item["found"] is True, param_id_item
        param_id_relations = [
            relation for relation in param_id_item["entity"]["acquisitions"]
            if relation.get("method") == "online_item_map"
            and any(
                item.get("onlineItemMapMatchMethod") == "source_param_id"
                for item in relation.get("items", [])
            )
        ]
        assert param_id_relations == [], param_id_relations
        exact_name_relations = [
            relation for relation in param_id_item["entity"]["acquisitions"]
            if relation.get("method") == "online_item_map"
            and any(
                item.get("externalSourceName") == "Lost Ashes of War"
                and item.get("externalSourceId") == 10070
                and item.get("onlineItemMapMatchMethod") == "exact_name"
                for item in relation.get("items", [])
            )
        ]
        assert exact_name_relations, param_id_item
        assert exact_name_relations[0]["verification"] == (
            "online_item_map_exact_unique_official_name_match"
        ), exact_name_relations[0]

        arrow = query(id="weapon_arrow")
        assert arrow["found"] is True, arrow
        source_param_relations = [
            relation for relation in arrow["entity"]["acquisitions"]
            if relation.get("method") == "online_item_map"
            and any(
                item.get("onlineItemMapMatchMethod") == "source_param_id"
                for item in relation.get("items", [])
            )
        ]
        assert source_param_relations, arrow
        source_param_item = next(
            item for relation in source_param_relations
            for item in relation.get("items", [])
            if item.get("onlineItemMapMatchMethod") == "source_param_id"
        )
        assert source_param_item["externalSourceName"] == "Fire Arrow", source_param_item
        assert source_param_item["externalSourceId"] == 50010000, source_param_item

        source_only = query(q="Golden Vow", limit=50)
        assert source_only["total_matches"] > 0, source_only
        source_only_row = next(
            row for row in source_only["records"]
            if row.get("kind") == "external_item_reference"
            and row.get("sourceStatus") == "source_item_ambiguous"
            and row.get("id", "").startswith("source_only_online_item_map_")
        )
        assert source_only_row["sourceOnly"] is True, source_only_row
        assert source_only_row["sourceStatus"] == "source_item_ambiguous", source_only_row
        source_only_detail = query(id=source_only_row["id"])
        assert source_only_detail["found"] is True, source_only_detail
        assert source_only_detail["entity"]["properties"]["formalEntity"] is False, source_only_detail
        assert any(
            relation.get("verification") == "online_item_map_source_only_unresolved"
            and relation.get("sourceGapStatus") == "source_item_ambiguous"
            for relation in source_only_detail["entity"]["acquisitions"]
        ), source_only_detail

        guide_source_only = query(q="Burred Bolt", limit=20)
        guide_source_row = next(
            row for row in guide_source_only["records"]
            if row.get("kind") == "external_item_reference"
            and row.get("sourceStatus") == "source_item_no_map"
        )
        guide_source_detail = query(id=guide_source_row["id"])
        assert guide_source_detail["found"] is True, guide_source_detail
        assert any(
            relation.get("method") == "online_guide"
            and relation.get("sourceGapStatus") == "source_item_no_map"
            and relation.get("topologyBinding", {}).get("status") == "not_bound"
            for relation in guide_source_detail["entity"]["acquisitions"]
        ), guide_source_detail

        map_source_only = query(q="Moonlight Altar", limit=20)
        map_source_row = next(
            row for row in map_source_only["records"]
            if row.get("kind") == "external_map_reference"
        )
        map_source_detail = query(id=map_source_row["id"])
        assert map_source_detail["found"] is True, map_source_detail
        assert map_source_detail["entity"]["properties"]["sourceOnly"] is True, map_source_detail
        assert map_source_detail["entity"]["counts"]["occurrences"] == 1, map_source_detail
        assert map_source_detail["entity"]["occurrences"][0]["markerId"] == "r-M00-moonlight-altar", map_source_detail

        craft_item = query(id="weapon_bone_arrow")
        assert craft_item["found"] is True, craft_item
        craft_relations = [
            relation for relation in craft_item["entity"]["acquisitions"]
            if relation.get("method") == "craft"
        ]
        assert craft_relations, craft_item
        craft_relation = craft_relations[0]
        assert craft_relation["verification"] == "online_cookbook_product_exact_unique_official_name_match", craft_relation
        assert craft_relation["from"] == "item_nomadic_warrior_s_cookbook_1", craft_relation
        assert craft_relation["craftRecipe"]["sourceProductName"] == "Bone Arrow", craft_relation
        assert craft_relation["craftRecipe"]["ingredientsStatus"] == "present_exact_unique_entity_match", craft_relation
        ingredients = craft_relation["craftRecipe"]["ingredients"]
        assert {ingredient["itemId"]: ingredient["quantity"] for ingredient in ingredients} == {
            "item_thin_beast_bones": 3,
        }, craft_relation
        assert craft_relation["craftRecipe"]["productQuantity"] == 10, craft_relation

        dlc_craft_item = query(id="item_hefty_fire_pot")
        assert dlc_craft_item["found"] is True, dlc_craft_item
        dlc_craft_relations = [
            relation for relation in dlc_craft_item["entity"]["acquisitions"]
            if relation.get("method") == "craft"
        ]
        assert len(dlc_craft_relations) == 1, dlc_craft_item
        dlc_craft_relation = dlc_craft_relations[0]
        assert dlc_craft_relation["from"] == "item_greater_potentate_s_cookbook_1", dlc_craft_relation
        assert dlc_craft_relation["verification"] == (
            "online_dataset_dlc_pair_exact_unique_official_entity_match"
        ), dlc_craft_relation
        assert dlc_craft_relation["craftRecipe"]["ingredientsStatus"] == (
            "not_present_in_source"
        ), dlc_craft_relation
        assert dlc_craft_relation["craftRecipe"]["unlockSource"]["commit"] == (
            "73ae9c5c72873edab7629142a4ff5857360f8d81"
        ), dlc_craft_relation

        default_craft_item = query(id="item_fire_pot")
        assert default_craft_item["found"] is True, default_craft_item
        default_craft_relations = [
            relation for relation in default_craft_item["entity"]["acquisitions"]
            if relation.get("id") == "craft-default-30100"
        ]
        assert len(default_craft_relations) == 1, default_craft_item
        default_craft_relation = default_craft_relations[0]
        assert default_craft_relation["from"] == "item_crafting_kit", default_craft_relation
        assert default_craft_relation["craftRecipe"]["unlockType"] == "default", default_craft_relation
        assert default_craft_relation["localRecipe"]["materialSetId"] == 301000, default_craft_relation
        assert {
            (ingredient["itemId"], ingredient["quantity"])
            for ingredient in default_craft_relation["localRecipe"]["ingredients"]
        } == {
            ("item_mushroom", 1),
            ("item_smoldering_butterfly", 1),
        }, default_craft_relation

        memory_of_grace = query(id="item_memory_of_grace")
        assert memory_of_grace["found"] is True, memory_of_grace
        memory_relations = [
            relation for relation in memory_of_grace["entity"]["acquisitions"]
            if relation.get("id") == "initial-loadout-class-item_memory_of_grace"
        ]
        assert len(memory_relations) == 1, memory_of_grace
        assert memory_relations[0]["verification"] == "local_selectable_class_loadout_exact"
        assert len(memory_relations[0]["initialLoadoutBinding"]["sources"]) == 10

        lands_between_rune = query(id="item_lands_between_rune")
        assert lands_between_rune["found"] is True, lands_between_rune
        gift_relations = [
            relation for relation in lands_between_rune["entity"]["acquisitions"]
            if relation.get("id") == "initial-loadout-gift-100302-item_lands_between_rune"
        ]
        assert len(gift_relations) == 1, lands_between_rune
        gift_source = gift_relations[0]["initialLoadoutBinding"]["sources"][0]
        assert gift_source["sourceRowId"] == 2402, gift_source
        assert gift_source["selectionValue"] == 2, gift_source

        mapped_alias = query(id="item_glintstone_cometshard")
        assert mapped_alias["found"] is True, mapped_alias
        assert mapped_alias["entity"]["id"] == "spell_glintstone_cometshard", mapped_alias
        mapped_spell = mapped_alias["entity"]
        assert mapped_spell["acquisitions"], mapped_spell
        assert not any(
            relation.get("method") == "spell_acquisition"
            for relation in mapped_spell["acquisitions"]
        ), mapped_spell
        assert all(
            item.get("item") == "spell_glintstone_cometshard"
            for relation in mapped_spell["acquisitions"]
            for item in relation.get("items", [])
        ), mapped_spell

        golden_vow_item = query(id="item_golden_vow")["entity"]
        golden_vow_spell = query(id="spell_golden_vow")["entity"]
        assert golden_vow_item["id"] != golden_vow_spell["id"]
        assert any(
            item.get("sourceParam") == "EquipParamGoods"
            and item.get("sourceParamId") == 2003170
            for relation in golden_vow_item["acquisitions"]
            for item in relation.get("items", [])
        ), golden_vow_item
        assert not any(
            item.get("sourceParamId") == 2003170
            for relation in golden_vow_spell["acquisitions"]
            for item in relation.get("items", [])
        ), golden_vow_spell

        gestures = query(q="表情动作", limit=100)
        assert gestures["total_matches"] >= 50, gestures
        assert all(row["category"] == "gesture" for row in gestures["records"]), gestures
        gesture_count = gestures.get("stats", {}).get("categoryCounts", {}).get("gesture", 0)
        assert gesture_count >= 50, gestures

        messages = query(q="留言", limit=100)
        assert messages["total_matches"] == 50, messages
        assert all(row["kind"] == "message" for row in messages["records"]), messages
        assert all(row["category"] == "fixed_message" for row in messages["records"]), messages
        message_detail = query(id=messages["records"][0]["id"])
        assert message_detail["found"] is True, message_detail
        assert message_detail["entity"]["counts"]["occurrences"] == 1, message_detail
        message_endpoint = message_detail["entity"]["occurrences"][0]
        assert message_endpoint["kind"] == "fixed_message_endpoint", message_endpoint
        assert message_endpoint["coordinateSpace"] == "game_world_xyz", message_endpoint
        assert message_endpoint["topologyBinding"]["status"] == "coordinate_endpoint", message_endpoint
        assert all(axis in message_endpoint["position"] for axis in ("x", "y", "z")), message_endpoint

        summon_pools = query(q="\u53ec\u5524\u6c60", limit=1000)
        assert summon_pools["total_matches"] == 223, summon_pools
        assert all(row["kind"] == "summon_endpoint" for row in summon_pools["records"]), summon_pools
        assert all(row["category"] == "multiplayer_summon_pool" for row in summon_pools["records"]), summon_pools
        summon_detail = query(id=summon_pools["records"][0]["id"])
        assert summon_detail["found"] is True, summon_detail
        summon_endpoint = summon_detail["entity"]["occurrences"][0]
        assert summon_endpoint["kind"] == "multiplayer_summon_pool", summon_endpoint
        assert summon_endpoint["eventId"] is not None, summon_endpoint
        assert summon_endpoint["signPuddleParamId"] is not None, summon_endpoint
        assert summon_endpoint["coordinateSpace"] == "game_world_xyz", summon_endpoint
        assert summon_endpoint["topologyBinding"]["status"] == "coordinate_endpoint", summon_endpoint
        assert all(axis in summon_endpoint["position"] for axis in ("x", "y", "z")), summon_endpoint

        spirit_ash_points = query(q="\u9aa8\u7070\u53ec\u5524\u70b9", limit=1000)
        assert spirit_ash_points["total_matches"] == 102, spirit_ash_points
        assert all(row["category"] == "spirit_ash_summon_point" for row in spirit_ash_points["records"]), spirit_ash_points
        spirit_detail = query(id=spirit_ash_points["records"][0]["id"])
        assert spirit_detail["found"] is True, spirit_detail
        spirit_endpoint = spirit_detail["entity"]["occurrences"][0]
        assert spirit_endpoint["kind"] == "spirit_ash_summon_point", spirit_endpoint
        assert spirit_endpoint["regionId"] is not None, spirit_endpoint
        assert spirit_endpoint["coordinateSpace"] == "game_world_xyz", spirit_endpoint
        assert spirit_endpoint["topologyBinding"]["status"] == "coordinate_endpoint", spirit_endpoint
        assert all(axis in spirit_endpoint["position"] for axis in ("x", "y", "z")), spirit_endpoint
        assert summon_detail["entity"]["counts"]["occurrences"] == 1, summon_detail
        assert spirit_detail["entity"]["counts"]["occurrences"] == 1, spirit_detail

        map_fragments = query(q="\u5730\u56fe\u6b8b\u7247", limit=1000)
        assert map_fragments["total_matches"] == 24, map_fragments
        assert all(row["kind"] == "item" for row in map_fragments["records"]), map_fragments
        assert all(row["category"] == "map_fragment" for row in map_fragments["records"]), map_fragments
        assert query(id="spell_stonesword_key")["found"] is False

        # Contract search gate: every named Beta category remains independently
        # searchable through the player projection, including aliases that do
        # not appear literally in every canonical name.
        search_gate = {
            "铃兰": ({"grave_glovewort", "ghost_glovewort"}, 20),
            "锻造石": ("smithing_stone", 23),
            "石剑钥匙": ("stone_sword_key", 2),
            "地图残片": ("map_fragment", 24),
            "战灰": ("ash_of_war", 116),
            "护符": ("accessory", 66),
            "骨灰": ("spirit_ash", 53),
            "漫步灵庙": ("enemy", 1),
            "灵泉": ("spirit_spring", 70),
            "传送机关": ("teleporter", 1),
        }
        for search_text, (categories, minimum) in search_gate.items():
            result = query(q=search_text, limit=1000)
            if isinstance(categories, str):
                categories = {categories}
            category_count = sum(row["category"] in categories for row in result["records"])
            assert category_count >= minimum, (search_text, result)

        ordinary_ash = query(id="item_demi_human_ashes")["entity"]
        assert len(ordinary_ash["reinforcementOutgoing"]) == 10, ordinary_ash
        assert {row["class"] for row in ordinary_ash["reinforcementOutgoing"]} == {"grave_glovewort"}, ordinary_ash
        renowned_ash = query(id="item_mimic_tear_ashes")["entity"]
        assert len(renowned_ash["reinforcementOutgoing"]) == 10, renowned_ash
        assert {row["class"] for row in renowned_ash["reinforcementOutgoing"]} == {"ghost_glovewort"}, renowned_ash
        for unique_ash_id in (
            "item_black_knife_tiche",
            "item_lhutel_the_headless",
            "item_jarwight_puppet",
            "item_jol_n_and_anna",
        ):
            unique_ash = query(id=unique_ash_id)
            assert unique_ash["found"] is True, unique_ash
            assert unique_ash["entity"]["category"] == "spirit_ash", unique_ash
            assert len(unique_ash["entity"]["reinforcementOutgoing"]) == 10, unique_ash
            assert {row["class"] for row in unique_ash["entity"]["reinforcementOutgoing"]} == {"ghost_glovewort"}, unique_ash
            assert query(id=unique_ash_id + "_1")["found"] is False
        armor_detail = query(id="armor_banished_knight_armor")["entity"]
        assert not armor_detail["reinforcementOutgoing"], armor_detail
        assert not armor_detail["reinforcementIncoming"], armor_detail

        common_drop = query(id="item_smithing_stone_1")
        assert common_drop["found"] is True
        drop_relations = [
            relation for relation in common_drop["entity"]["acquisitions"]
            if relation.get("method") == "drop"
        ]
        assert drop_relations, common_drop
        assert any(relation.get("endpointInstances") for relation in drop_relations), common_drop
        pickup_relations = [
            relation for relation in common_drop["entity"]["acquisitions"]
            if relation.get("method") == "pickup"
        ]
        assert pickup_relations, common_drop
        assert any(
            endpoint.get("kind") == "pickup_endpoint"
            and endpoint.get("coordinateSpace") == "game_world_xyz"
            for relation in pickup_relations
            for endpoint in relation.get("endpointInstances", [])
        ), common_drop
        assert all(relation.get("pickupEndpointStatus") for relation in pickup_relations), common_drop
        assert all(
            relation.get("pickupEndpointStatus") == "coordinate_endpoint"
            for relation in pickup_relations
        ), common_drop
        for relation in drop_relations:
            for endpoint in relation.get("endpointInstances", []):
                assert endpoint.get("map"), endpoint
                assert endpoint.get("part"), endpoint
                assert isinstance(endpoint.get("position"), dict), endpoint
                assert all(axis in endpoint["position"] for axis in ("x", "y", "z")), endpoint
                assert endpoint.get("npcParamId") is not None, endpoint

        sequential_drop = query(id="armor_banished_knight_armor")
        assert sequential_drop["found"] is True, sequential_drop
        sequential_relations = [
            relation for relation in sequential_drop["entity"]["acquisitions"]
            if relation.get("method") == "drop"
        ]
        assert sequential_relations, sequential_drop
        assert any(
            301000203 in relation.get("sourceItemLotRows", [])
            and relation.get("endpointInstances")
            for relation in sequential_relations
        ), sequential_drop

        pickup_chain = query(id="armor_carian_knight_armor")
        assert pickup_chain["found"] is True, pickup_chain
        assert any(
            relation.get("method") == "pickup"
            and relation.get("lot", {}).get("rowId") == 14000850
            and 14000851 in relation.get("sourceItemLotRows", [])
            and relation.get("endpointInstances")
            for relation in pickup_chain["entity"]["acquisitions"]
        ), pickup_chain

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
        assert any(
            binding["binding"].get("mapBindingStatus") in {
                "exact_map_instance", "exact_map_instance_alias", "external_map_scope",
                "unresolved_map_instance",
            }
            for binding in glovewort_topology["bindings"]
        ), glovewort_topology

        thin_beast_bones = query(id="item_thin_beast_bones")
        assert thin_beast_bones["found"] is True, thin_beast_bones
        assert len(thin_beast_bones["entity"]["acquisitions"]) == thin_beast_bones["entity"]["counts"]["acquisitions"] == 4885, thin_beast_bones

        exact_part_anchor = topology_query("weapon_omen_cleaver")
        assert exact_part_anchor["found"] is True, exact_part_anchor
        assert any(
            row["localPartSemanticAnchor"]["status"] == "exact_local_part_semantic_anchor"
            and len(row["localPartSemanticAnchor"]["nodeIds"]) == 1
            for row in exact_part_anchor["acquisitionBridge"]["records"]
        ), exact_part_anchor

        routeable_entity_topology = topology_query("item_bolt_of_gransax")
        assert routeable_entity_topology["found"] is True
        assert routeable_entity_topology["canonicalEntityId"] == "weapon_bolt_of_gransax"
        assert routeable_entity_topology["routeReady"] is True
        assert "item_bolt_of_gransax" in routeable_entity_topology["routeNodeIds"]
        bolt_search = query(q="古兰桑克斯的雷电", limit=100)
        assert bolt_search["total_matches"] == 1, bolt_search
        assert bolt_search["records"][0]["id"] == "weapon_bolt_of_gransax", bolt_search
        bolt_alias_detail = query(id="item_bolt_of_gransax")
        assert bolt_alias_detail["found"] is True, bolt_alias_detail
        assert bolt_alias_detail["canonicalEntityId"] == "weapon_bolt_of_gransax", bolt_alias_detail

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

        mausoleum_shop = query(id="item_remembrance_of_the_grafted")
        assert mausoleum_shop["found"] is True, mausoleum_shop
        assert any(
            relation.get("method") == "purchase"
            and relation.get("merchantShopBinding", {}).get("merchantName") == "Wandering Mausoleum Corpse"
            and relation.get("merchantShopBinding", {}).get("sellerIdentitySource") == "local_map_semantic_alias"
            and relation.get("verification") == "local_param_and_local_map_semantic_shop_endpoint_verified"
            for relation in mausoleum_shop["entity"]["acquisitions"]
        ), mausoleum_shop

        kale = query(q="咖列", limit=20)
        assert any(row["id"] == "npc_merchant_kal" for row in kale["records"]), kale
        remembrance = query(id="item_remembrance_of_the_omen_king")
        assert remembrance["found"] is True
        reward_sources = [
            relation for relation in remembrance["entity"]["acquisitions"]
            if relation.get("method") == "drops"
        ]
        assert any(
            relation.get("topologyBinding", {}).get("status") == "routeable_anchor"
            and relation.get("endpointInstances")
            and relation["endpointInstances"][0].get("formalNodeId") == "morgott_arena_gate"
            for relation in reward_sources
        ), reward_sources
        boss_topology = topology_query("enemy_morgott_the_omen_king")
        assert boss_topology["found"] is True
        assert "morgott_arena_gate" in boss_topology["routeNodeIds"], boss_topology
        candidate_map = get(
            "/api/abstract-topology-candidates/map?"
            + urlencode({"map_id": "m10_00_00_00"})
        )
        assert candidate_map["schema"] == "elden-ring-abstract-topology-candidates-map@2"
        assert candidate_map["routeable"] is False
        assert candidate_map["layers"], candidate_map
        assert all(layer["routeable"] is False for layer in candidate_map["layers"]), candidate_map
        assert candidate_map["edges"], candidate_map
        assert all(edge["routeable"] is False for edge in candidate_map["edges"]), candidate_map
        abstract_path = get(
            "/api/abstract-topology-candidates/path?"
            + urlencode({"from_map_id": "m10_01_00_00", "to_map_id": "m10_00_00_00"})
        )
        assert abstract_path["found"] is True, abstract_path
        assert abstract_path["mode"] == "abstract_topology_evidence_trace", abstract_path
        assert abstract_path["routeable"] is False, abstract_path
        assert abstract_path["mapIds"][0] == "m10_01_00_00", abstract_path
        assert abstract_path["mapIds"][-1] == "m10_00_00_00", abstract_path
        assert all(edge["routeable"] is False for edge in abstract_path["edges"]), abstract_path
        abstract_route = get(
            "/api/abstract-topology-route?"
            + urlencode({
                "from_map_id": "m10_01_00_00",
                "to_map_id": "m10_00_00_00",
            })
        )
        assert abstract_route["schema"] == "elden-ring-abstract-topology-route@1"
        assert abstract_route["found"] is True, abstract_route
        assert abstract_route["mode"] == "abstract_topology_route_evidence"
        assert abstract_route["abstractRouteable"] is True, abstract_route
        assert abstract_route["playerRouteable"] is False, abstract_route
        assert abstract_route["routeable"] is False, abstract_route
        assert abstract_route["mapIds"][0] == "m10_01_00_00", abstract_route
        assert abstract_route["mapIds"][-1] == "m10_00_00_00", abstract_route
        assert all(edge["routeable"] is False for edge in abstract_route["edges"]), abstract_route
        entity_route = abstract_entity_route_query(
            id="item_smithing_stone_1",
            from_map_id="m10_01_00_00",
            target_map_id="m10_00_00_00",
            max_paths=5,
        )
        assert entity_route["schema"] == "elden-ring-reachability-map/player-entity-abstract-route@1", entity_route
        assert entity_route["found"] is True, entity_route
        assert entity_route["pathFound"] is True, entity_route
        assert entity_route["targetMapCount"] == 1, entity_route
        assert entity_route["reachableTargetMapCount"] == 1, entity_route
        assert entity_route["paths"][0]["targetMapId"] == "m10_00_00_00", entity_route
        assert entity_route["paths"][0]["mapIds"] == ["m10_01_00_00", "m10_00_00_00"], entity_route
        assert entity_route["abstractRouteable"] is True, entity_route
        assert entity_route["playerRouteable"] is False, entity_route
        assert entity_route["routeable"] is False, entity_route
        assert all(
            edge["playerRouteable"] is False and edge["routeable"] is False
            for edge in entity_route["paths"][0]["edges"]
        ), entity_route
        node_origin_route = abstract_entity_route_query(
            id="item_smithing_stone_1",
            from_node_id="grace_avenue_balcony",
            target_map_id="m11_10_00_00",
            max_paths=2,
        )
        assert node_origin_route["originResolution"]["status"] == "exact_formal_node_to_abstract_map", node_origin_route
        assert node_origin_route["originResolution"]["formalNodeId"] == "grace_avenue_balcony", node_origin_route
        assert node_origin_route["fromMapId"] == "m11_00_00_00", node_origin_route
        assert node_origin_route["pathFound"] is True, node_origin_route
        assert node_origin_route["paths"][0]["targetMapId"] == "m11_10_00_00", node_origin_route
        unique_name_node_origin = abstract_entity_route_query(
            id="item_smithing_stone_1",
            from_node_id="grace_limgrave_stormhill_castleward_tunnel",
            target_map_id="m10_00_00_00",
        )
        assert unique_name_node_origin["found"] is True, unique_name_node_origin
        assert unique_name_node_origin["pathFound"] is True, unique_name_node_origin
        assert unique_name_node_origin["originResolution"]["status"] == "exact_formal_node_to_abstract_map", unique_name_node_origin
        assert unique_name_node_origin["originResolution"]["formalNodeId"] == "grace_limgrave_stormhill_castleward_tunnel", unique_name_node_origin
        assert unique_name_node_origin["fromMapId"] == "m10_00_00_00", unique_name_node_origin
        assert unique_name_node_origin["paths"][0]["edges"] == [], unique_name_node_origin
        assert unique_name_node_origin["playerRouteable"] is False, unique_name_node_origin
        entity_route_summary = abstract_entity_route_query(
            id="item_thin_beast_bones",
            from_map_id="m10_00_00_00",
            max_paths=3,
        )
        assert entity_route_summary["found"] is True, entity_route_summary
        assert entity_route_summary["targetMapCount"] > 100, entity_route_summary
        assert entity_route_summary["endpointCount"] > 1000, entity_route_summary
        assert entity_route_summary["paths"], entity_route_summary
        assert all(
            row["playerRouteable"] is False and row["routeable"] is False
            for row in entity_route_summary["targetMapStatuses"]
        ), entity_route_summary
        unreachable_entity_route = abstract_entity_route_query(
            id="item_smithing_stone_1",
            from_map_id="m10_01_00_00",
            target_map_id="m99_99_99_99",
        )
        assert unreachable_entity_route["found"] is True, unreachable_entity_route
        assert unreachable_entity_route["pathFound"] is False, unreachable_entity_route
        assert unreachable_entity_route["targetMapCount"] == 1, unreachable_entity_route
        assert unreachable_entity_route["targetMapStatuses"][0]["endpointCount"] == 0, unreachable_entity_route
        assert unreachable_entity_route["targetMapStatuses"][0]["reachable"] is False, unreachable_entity_route
        native_map = get(
            "/api/abstract-native-topology/map?"
            + urlencode({"map_id": "m10_00_00_00"})
        )
        assert native_map["schema"] == "elden-ring-abstract-native-topology-map@1"
        assert native_map["found"] is True, native_map
        assert native_map["nodes"], native_map
        assert native_map["edges"], native_map
        assert all(row["routeable"] is False for row in native_map["nodes"] + native_map["edges"]), native_map
        item_topology = topology_query("item_thin_beast_bones")
        assert item_topology["abstractTopology"]["status"] == "candidate_evidence_only", item_topology
        assert item_topology["abstractTopology"]["routeable"] is False, item_topology
        abstract_route_evidence = item_topology["abstractRouteEvidence"]
        assert abstract_route_evidence["status"] == "abstract_topology_route_evidence", item_topology
        assert abstract_route_evidence["mapIds"], item_topology
        assert abstract_route_evidence["maps"], item_topology
        assert abstract_route_evidence["layers"], item_topology
        assert abstract_route_evidence["edgeCounts"]["incident"] >= len(abstract_route_evidence["edges"]), item_topology
        assert abstract_route_evidence["abstractRouteable"] is True, item_topology
        assert abstract_route_evidence["playerRouteable"] is False, item_topology
        assert abstract_route_evidence["routeable"] is False, item_topology
        assert all(
            edge["playerRouteable"] is False and edge["routeable"] is False
            for edge in abstract_route_evidence["edges"]
        ), item_topology
        assert item_topology["acquisitionBridge"]["status"] == "acquisition_endpoint_bridge_evidence_only", item_topology
        assert item_topology["acquisitionBridge"]["records"], item_topology
        drop_endpoint_rows = [
            row for row in item_topology["acquisitionBridge"]["records"]
            if row.get("method") in {"drop", "drops"}
            and row.get("endpointKind") in {"enemy_spawn", "dummy_enemy_spawn", "boss_reward_endpoint"}
        ]
        assert drop_endpoint_rows, item_topology
        assert all(
            row["localEndpointIdentity"]["status"] == "exact_local_endpoint_identity"
            and len(row["localEndpointIdentity"]["identityIds"]) == 1
            and row["localEndpointIdentity"]["routeable"] is False
            for row in drop_endpoint_rows
        ), item_topology
        assert all(
            row["routeable"] is False
            and row["abstractAnchor"]["routeable"] is False
            and row["semanticGraphAnchor"]["routeable"] is False
            and row["localPartSemanticAnchor"]["routeable"] is False
            and row["localEndpointIdentity"]["routeable"] is False
            and row["formalRouteAnchor"]["routeable"] is False
            for row in item_topology["acquisitionBridge"]["records"]
        ), item_topology
        bridge_map = get(
            "/api/acquisition-topology-bridge/map?"
            + urlencode({"map_id": "m10_00_00_00", "limit": 5})
        )
        assert bridge_map["schema"] == "elden-ring-acquisition-topology-bridge-map@1"
        assert bridge_map["found"] is True, bridge_map
        assert bridge_map["totalMatches"] >= len(bridge_map["records"]) > 0, bridge_map
        assert all(
            row["routeable"] is False
            and row["semanticGraphAnchor"]["routeable"] is False
            and row["localPartSemanticAnchor"]["routeable"] is False
            and row["localEndpointIdentity"]["routeable"] is False
            for row in bridge_map["records"]
        ), bridge_map
        bridge_relation = get(
            "/api/acquisition-topology-bridge/relation?"
            + urlencode({
                "relation_id": item_topology["acquisitionBridge"]["records"][0]["relationId"]
            })
        )
        assert bridge_relation["schema"] == "elden-ring-acquisition-topology-bridge-relation@1"
        assert bridge_relation["found"] is True, bridge_relation
        assert all(row["routeable"] is False for row in bridge_relation["records"]), bridge_relation

        palace_key = query(id="item_discarded_palace_key")
        assert palace_key["found"] is True
        quest_sources = [
            relation for relation in palace_key["entity"]["acquisitions"]
            if relation.get("method") == "quest_reward"
        ]
        assert any(
            relation.get("questRewardBinding", {}).get("npcName") == "Ranni the Witch"
            and relation.get("questRewardBinding", {}).get("eventRewardBindingId") == "event-reward-common-3050-7"
            and relation.get("endpointInstances")
            and relation["endpointInstances"][0].get("kind") == "quest_npc_endpoint"
            and relation["endpointInstances"][0].get("topologyBinding", {}).get("status") == "coordinate_endpoint"
            for relation in quest_sources
        ), quest_sources
        ranni = query(id="npc_ranni_the_witch")
        assert ranni["found"] is True
        assert any(target.get("method") == "quest_reward" for target in ranni["entity"].get("acquisitionTargets", [])), ranni

        external_quest_reward = query(id="item_golden_order_totality")
        assert external_quest_reward["found"] is True
        assert any(
            relation.get("method") == "quest_reward"
            and relation.get("verification") == "external_quest_named_reward_reference"
            and relation.get("questRewardBinding", {}).get("sourceStatus") == "external_reference_only"
            and relation.get("questRewardBinding", {}).get("npcName") == "Brother Corhyn"
            and any(item.get("quantityStatus") == "not_stated_in_external_step"
                    for item in relation.get("items", []))
            and relation.get("endpointInstances")
            and relation["endpointInstances"][0].get("kind") == "quest_npc_endpoint"
            for relation in external_quest_reward["entity"]["acquisitions"]
        ), external_quest_reward

        alexander = query(id="accessory_shard_of_alexander")
        assert alexander["found"] is True
        event_rewards = [
            relation for relation in alexander["entity"]["acquisitions"]
            if relation.get("method") == "event_reward"
        ]
        assert any(
            relation.get("eventRewardBinding", {}).get("eventId") == 13003711
            and relation.get("eventRewardBinding", {}).get("taskStatus") == "unclassified"
            for relation in event_rewards
        ), event_rewards

        eccentric_armor = query(id="armor_eccentric_s_armor")
        assert eccentric_armor["found"] is True
        eccentric_event_rewards = [
            relation for relation in eccentric_armor["entity"]["acquisitions"]
            if relation.get("method") == "event_reward"
        ]
        assert any(
            relation.get("eventRewardBinding", {}).get("eventId") == 14000712
            and relation.get("eventRewardBinding", {}).get("itemLot", {}).get("rowId") == 104010
            and 104011 in relation.get("eventRewardBinding", {}).get("sourceItemLotRows", [])
            and 104012 in relation.get("eventRewardBinding", {}).get("sourceItemLotRows", [])
            and 104013 in relation.get("eventRewardBinding", {}).get("sourceItemLotRows", [])
            and any(item.get("lot") == 104011 for item in relation.get("items", []))
            for relation in eccentric_event_rewards
        ), eccentric_event_rewards

        sword_lance = query(id="weapon_sword_lance")
        assert sword_lance["found"] is True
        sword_lance_exchanges = [
            relation for relation in sword_lance["entity"]["acquisitions"]
            if relation.get("method") == "purchase"
            and relation.get("lineupRow") == 101932
        ]
        assert len(sword_lance_exchanges) == 1, sword_lance_exchanges
        sword_lance_exchange = sword_lance_exchanges[0]
        assert sword_lance_exchange.get("from") == "npc_finger_reader_enia", sword_lance_exchange
        assert any(
            item.get("sourceCustomWeaponId") == 4400039
            and item.get("sourceParamId") == 3500000
            and item.get("reinforcementLevel") == 0
            for item in sword_lance_exchange.get("items", [])
        ), sword_lance_exchange

        rogier_rapier = query(id="weapon_rogier_s_rapier")
        assert rogier_rapier["found"] is True
        assert any(
            item.get("sourceCustomWeaponId") == 5010
            and item.get("sourceParamId") == 5030000
            and item.get("reinforcementLevel") == 8
            for relation in rogier_rapier["entity"]["acquisitions"]
            for item in relation.get("items", [])
        ), rogier_rapier

        dryleaf_arts = query(id="weapon_dryleaf_arts")
        assert dryleaf_arts["found"] is True
        assert any(
            relation.get("method") == "event_reward"
            and relation.get("eventRewardBinding", {}).get("itemLot", {}).get("rowId") == 107300
            and any(item.get("sourceCustomWeaponId") == 4401055
                    and item.get("sourceParamId") == 60500000
                    and item.get("reinforcementLevel") == 0
                    for item in relation.get("items", []))
            for relation in dryleaf_arts["entity"]["acquisitions"]
        ), dryleaf_arts

        inverted_statue = query(id="item_carian_inverted_statue")
        assert inverted_statue["found"] is True
        assert any(
            relation.get("eventRewardBinding", {}).get("id")
            == "event-reward-direct-m34_11_00_00-34112150-73"
            and relation.get("eventRewardBinding", {}).get("directGrant") == {
                "instruction": "Directly Give Player Item",
                "itemType": 3,
                "itemId": 8111,
                "baseEventFlagId": 34112155,
                "usedEventFlagBits": 1,
            }
            for relation in inverted_statue["entity"]["acquisitions"]
        ), inverted_statue

        direct_tutorial = query(id="item_about_sorceries_and_incantations")
        assert direct_tutorial["found"] is True
        assert any(
            relation.get("eventRewardBinding", {}).get("id")
            == "event-reward-direct-common-0-141-via-common-1720-14"
            and relation.get("eventRewardBinding", {}).get("awardSource", {}).get("resolution")
            == "initialize_event_parameter_substitution"
            for relation in direct_tutorial["entity"]["acquisitions"]
        ), direct_tutorial
        assert any(
            cost.get("item") == "item_remembrance_of_the_wild_boar_rider"
            and cost.get("quantity") == 1
            for cost in sword_lance_exchange.get("materialCost", [])
        ), sword_lance_exchange

        whistle = query(id="item_spectral_steed_whistle")
        assert whistle["found"] is True
        whistle_rewards = [
            relation for relation in whistle["entity"]["acquisitions"]
            if relation.get("method") == "talk_reward"
        ]
        assert any(
            relation.get("talkItemLotBinding", {}).get("talkFile") == "t000003000"
            and relation.get("talkItemLotBinding", {}).get("itemLot", {}).get("rowId") == 100000
            and len(relation.get("talkItemLotBinding", {}).get("callSites", [])) == 2
            and not relation.get("endpointInstances")
            for relation in whistle_rewards
        ), whistle_rewards

        beast_claw = query(id="spell_beast_claw")
        stone_of_gurranq = query(id="spell_stone_of_gurranq")
        assert beast_claw["found"] is True and stone_of_gurranq["found"] is True
        for result in (beast_claw, stone_of_gurranq):
            assert any(
                relation.get("method") == "talk_reward"
                and relation.get("talkItemLotBinding", {}).get("itemLot", {}).get("rowId") == 102310
                for relation in result["entity"]["acquisitions"]
            ), result

        kale_detail = query(id="npc_merchant_kal")
        assert kale_detail["found"] is True
        assert kale_detail["entity"]["counts"]["shopSales"] > 0, kale_detail
        husks_detail = query(id="enemy_twin_maiden_husks")
        assert husks_detail["found"] is True
        assert len(husks_detail["entity"]["shopSales"]) == husks_detail["entity"]["counts"]["shopSales"] == 541, husks_detail

        missing = query(id="definitely_missing_entity")
        assert missing["found"] is False
        missing_topology = topology_query("definitely_missing_entity")
        assert missing_topology["found"] is False

        index = get("/api/catalog/player-entities?limit=1")
        assert index["stats"]["entityCount"] >= 9000
        coverage = index["stats"]["acquisitionCoverage"]
        assert coverage["drop"]["dropRootCount"] == 1376, coverage
        assert coverage["drop"]["dropRelationCount"] == 1216, coverage
        assert coverage["drop"]["dropGapCount"] == 0, coverage
        assert coverage["pickup"]["pickupEndpointInstanceCount"] >= 3600, coverage
        assert coverage["pickup"]["pickup"] == 3346, coverage
        assert coverage["pickup"]["pickup_coverageGapCount"] == 0, coverage
        assert coverage["pickup"]["pickup_coverageGapNoExternalLocationBindingCount"] == 0, coverage
        assert coverage["pickup"]["pickup_coverageGapSourceRecordWithoutCoordinatesCount"] == 0, coverage
        assert coverage["pickup"]["pickupEventRewardExclusionCount"] == 827, coverage
        assert coverage["pickup"]["pickupOrphanTreasureExclusionCount"] == 11, coverage
        assert coverage["shop"]["shop_coverageGapCount"] == 0, coverage
        assert coverage["shop"]["shop_coverageGapSellerUnresolvedNoExternalBindingCount"] == 0, coverage
        assert coverage["shop"]["shop_coverageGapSellerUnresolvedCandidateBindingCount"] == 0, coverage
        assert coverage["shop"]["shop_sellerUnresolvedItemCoveredElsewhereCount"] == 237, coverage
        assert coverage["shop"]["shop_coverageGapSellerUnresolvedBindingCount"] == 0, coverage
        assert coverage["shop"]["shop_customWeaponPurchaseRows"] == 1, coverage
        assert coverage["shop"]["shop_unresolvedCustomWeaponPurchaseRows"] == 0, coverage
        # Research-only content equivalence (equivalent-map-instances identityPolicy)
        # must not promote a map-instance binding: those endpoints stay candidate.
        assert index["stats"]["topologyMapBinding"] == {
            "topologyMapEndpointCount": 81457,
            "topologyMapExactMapInstanceEndpointCount": 78378,
            "topologyMapExactLayerEndpointCount": 31968,
            "topologyMapCandidateEndpointCount": 35,
            "topologyMapExternalScopeEndpointCount": 3044,
            "topologyMapUnresolvedEndpointCount": 0,
            "topologyMapBindingStatusCounts": {
                "candidate_map_instance": 35,
                "exact_map_instance": 78282,
                "exact_map_instance_alias": 96,
                "external_map_scope": 3044,
            },
        }, index["stats"]
        assert len(index["coverageGaps"]) == 0, index
        assert len(index.get("onlineSourceGaps", [])) == 1288, index
        assert len(index.get("verifiedNoDropFacts", [])) >= 150, index
        assert len(index.get("verifiedUnusedMapLotFacts", [])) >= 500, index
        assert coverage["sourceExclusionCount"] == 1076, coverage
        assert coverage["pickup"]["pickupTalkRewardExclusionCount"] == 127, coverage
        assert index["stats"]["kindCounts"]["message"] == 50, index["stats"]
        assert index["stats"]["messageOccurrenceCount"] == 50, index["stats"]
        assert index["stats"]["kindCounts"]["summon_endpoint"] == 325, index["stats"]
        assert index["stats"]["summonEndpointOccurrenceCount"] == 325, index["stats"]
        assert index["stats"]["multiplayerSummonPoolCount"] == 223, index["stats"]
        assert index["stats"]["spiritAshSummonPointCount"] == 102, index["stats"]
        assert len(index["coverageGaps"]) == 0, index["coverageGaps"]
        assert len(index.get("sellerUnresolvedRecords", [])) == 237, index
        assert len(index.get("serviceMenuRecords", [])) == 450, index
        assert len(index.get("testShopRowRecords", [])) == 10, index
        assert {
            gap["status"] for gap in index["onlineSourceGaps"]
        } == {
            "source_item_unmatched",
            "source_item_ambiguous",
            "source_item_no_map",
            "source_map_invalid",
            "source_marker_unmatched",
        }, index["onlineSourceGaps"]
        assert sum(gap["method"] == "online_guide" for gap in index["onlineSourceGaps"]) == 1206
        assert sum(gap["method"] == "online_map" for gap in index["onlineSourceGaps"]) == 48
        assert sum(gap["method"] == "online_item_map" for gap in index["onlineSourceGaps"]) == 34

        # Local gesture facts are independent acquisitions.  Starting state,
        # map event, and Talk ESD evidence must all remain queryable without a
        # fabricated route endpoint.
        bow = query(id="item_bow")
        assert bow["found"] is True, bow
        assert any(
            acquisition.get("method") == "initial_loadout"
            for acquisition in bow["entity"].get("acquisitions", [])
        ), bow
        warm_welcome = query(id="item_warm_welcome")
        assert warm_welcome["found"] is True, warm_welcome
        assert any(
            acquisition.get("method") == "gesture_unlock"
            and acquisition.get("verification") == "local_emevd_gesture_award_verified"
            for acquisition in warm_welcome["entity"].get("acquisitions", [])
        ), warm_welcome
        for entity_id, method in {
            "item_phantom_bloody_finger": "session_grant",
            "item_phantom_recusant_finger": "session_grant",
            "item_phantom_great_rune": "session_grant",
            "item_grave_keeper_s_brainpan": "harvest",
            "item_nailstone": "harvest",
            "item_roundrock": "harvest",
        }.items():
            special = query(id=entity_id)
            assert special["found"] is True, special
            assert any(
                acquisition.get("method") == method
                for acquisition in special["entity"].get("acquisitions", [])
            ), special
        varre_bouquet = query(id="weapon_varr_s_bouquet")
        assert varre_bouquet["found"] is True, varre_bouquet
        assert any(
            acquisition.get("method") == "npc_map_drop"
            and acquisition.get("verification") == "local_npc_map_item_lot_verified"
            for acquisition in varre_bouquet["entity"].get("acquisitions", [])
        ), varre_bouquet
        rune_arc = query(id="item_rune_arc")
        assert rune_arc["found"] is True, rune_arc
        assert any(
            acquisition.get("method") == "multiplayer_role_reward"
            and acquisition.get("verification") == "local_role_param_item_lot_verified"
            and acquisition.get("topologyBinding", {}).get("status") == "not_bound"
            for acquisition in rune_arc["entity"].get("acquisitions", [])
        ), rune_arc
        outer_order = query(id="item_outer_order")
        assert outer_order["found"] is True, outer_order
        assert any(
            acquisition.get("method") == "gesture_unlock"
            and acquisition.get("verification") == "local_talk_esd_gesture_acquisition_verified"
            for acquisition in outer_order["entity"].get("acquisitions", [])
        ), outer_order
        tutorial_info = query(id="item_about_fast_travel_to_sites_of_grace")
        assert tutorial_info["found"] is True, tutorial_info
        assert any(
            acquisition.get("method") == "tutorial_unlock"
            and acquisition.get("verification") == "local_emevd_tutorial_unlock_verified"
            for acquisition in tutorial_info["entity"].get("acquisitions", [])
        ), tutorial_info
        print("PASS player entity query")
        print(f"  glovewort_matches={glovewort['total_matches']}")
        print(f"  smithing_matches={smithing['total_matches']}")
        print(f"  published_entities={index['stats']['entityCount']}")
        print(f"  enemy_drop_gaps={coverage['drop']['dropGapCount']}")
        print(f"  pickup_gaps={coverage['pickup']['pickup_coverageGapCount']}")
        print(f"  shop_gaps={coverage['shop']['shop_coverageGapCount']}")
        print(f"  fixed_messages={index['stats']['kindCounts']['message']}")
        print(f"  summon_pools={summon_pools['total_matches']}")
        print(f"  spirit_ash_summon_points={spirit_ash_points['total_matches']}")

        # ============================================================
        # 第十一章 强制回归样例
        # ============================================================

        # 1. 洞窟入口 — 玩家可以搜到、详情可查、获取终点可定位
        cave = query(id="abandoned_cave_surface_entrance")
        assert cave["found"] is True, cave
        assert cave["entity"]["kind"] == "entrance", cave

        # 2. 地下目的地 — 希芙拉河井底是地下区域代表
        underground = query(id="grace_caelid_main_deep_siofra_well")
        assert underground["found"] is True, underground
        assert underground["entity"]["kind"] == "grace", underground

        # 3. 屋顶终点 — 史东薇尔城屋顶 (Castle Sol Rooftop)
        rooftop = query(id="grace_castle_sol_rooftop")
        assert rooftop["found"] is True, rooftop
        assert rooftop["entity"]["kind"] == "grace", rooftop

        # 4. 未绑定终点 — 仍可搜索，但不能生成正式路线
        # 从本地 player-entity-index.json 直接读, 不依赖 API
        full_index = json.loads(
            (ROOT / "data" / "v1" / "entities" / "player-entity-index.json").read_text(encoding="utf-8")
        )
        unbound = next(
            (row for row in full_index["entities"]
             if row.get("topology", {}).get("status") == "not_bound"
             and row.get("name", {}).get("zh")),
            None,
        )
        assert unbound is not None, "no not_bound entity with zh name"
        unbound_search = query(q=unbound["name"]["zh"], limit=5)
        assert any(row["id"] == unbound["id"] for row in unbound_search["records"]), unbound_search
        # 尝试规划路线时应返回 found=True 但 pathFound=False
        unbound_route = abstract_entity_route_query(
            id=unbound["id"],
            from_map_id="m10_01_00_00",
            max_paths=1,
        )
        assert unbound_route["found"] is True, unbound_route
        # not_bound 实体的所有 binding 都未绑定, 因此 targetMapCount=0
        assert unbound_route.get("targetMapCount", 0) == 0 or all(
            not s.get("reachable") for s in unbound_route.get("targetMapStatuses", [])
        ), unbound_route

        # 5. 防具不存在强化关系 — 强化目录不含防具 (合同 4.3 + 10.4)
        armor_in_reinforce = any(
            (item.get("id", "").startswith("armor_") or
             item.get("category") == "armor" or
             "armor" in str(item.get("kind", "")).lower())
            for item in reinforce_catalog.get("items", [])
        )
        assert not armor_in_reinforce, "armor must not appear in reinforce-catalog items"
        # 加强断言：强化关系中每一条都不应该引用 armor 实体。
        for relation in reinforce_catalog.get("relations", []):
            assert not any(
                str(value).startswith("armor_")
                for key, value in relation.items()
                if key in {"from", "to", "item", "material"}
            ), f"armor reinforcement relation found: {relation}"

        # 6. 追忆 ↔ Boss ↔ 大卢恩 自指关系 (合同 4.6)
        # 拉卡德的追忆 → 拉卡德大卢恩 → 亵渎君王 (Boss 拉卡德)
        remb = query(id="item_remembrance_of_the_blasphemous")
        assert remb["found"] is True, remb
        assert remb["entity"]["category"] == "remembrance", remb
        # 大卢恩
        rune = query(id="item_rykard_s_great_rune")
        assert rune["found"] is True, rune
        assert rune["entity"]["category"] == "great_rune", rune
        # 追忆应能兑换为大卢恩或 Boss 战利品
        remb_topology = topology_query("item_remembrance_of_the_blasphemous")
        assert remb_topology["found"] is True, remb_topology
        remb_methods = {b["method"] for b in remb_topology.get("bindings", [])}
        assert "boss_reward" in remb_methods or "remembrance_exchange" in remb_methods or "purchase" in remb_methods, remb_topology

        # 7. 路线引擎正式可达 — 王城两态互斥 (e2e [7]) 已在 e2e-route-regression 中覆盖

        # 8. 正式路线锚点总量断言；证据层节点不得抬升此统计。
        assert index["stats"]["routeableAnchorCount"] == 938, index["stats"]

        # 9. 真实拾取实体必须经已有正式边绑定；普通锻造石仍保持未正式绑定。
        bolt_topology = topology_query("item_bolt_of_gransax")
        assert bolt_topology["routeReady"] is True, bolt_topology
        assert "item_bolt_of_gransax" in bolt_topology["routeNodeIds"], bolt_topology
        stone_topology = topology_query("item_smithing_stone_1")
        assert stone_topology["routeReady"] is False, stone_topology

        print("PASS player entity query (incl. 第十一章 regression samples)")
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
