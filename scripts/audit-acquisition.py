#!/usr/bin/env python3
"""Audit the acquisition entity layer for structural integrity.

Checks:
  1. entity-registry: unique ids, non-empty names, valid signifiers, no
     duplicate entities with identical names but different ids
  2. acquisition-registry: every referenced entity id resolves; lots resolve;
     methods are from the known set
  3. location-catalog: unique ids, known types, resolvable names
  4. graph-v1: relation endpoints exist; new node kinds are consistent

Usage:
    python scripts/audit-acquisition.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "v1"

KNOWN_METHODS = {"drop", "npc_map_drop", "multiplayer_role_reward", "pickup", "purchase", "boss_reward", "drops", "event_reward", "talk_reward", "quest_reward", "gesture_unlock", "initial_loadout", "tutorial_unlock", "online_map", "online_guide", "online_item_map", "spell_acquisition", "craft", "session_grant", "harvest"}
KNOWN_MAP_BINDING_STATUSES = {
    "exact_map_instance",
    "exact_map_instance_alias",
    "candidate_map_instance",
    "external_map_scope",
    "unresolved_map_instance",
    "unresolved_map_scope",
    "map_index_unavailable",
}
KNOWN_LOCATION_TYPES = {
    "church", "catacomb", "ruins", "shack", "lookout_tower", "evergaol",
    "gate", "bridge", "cave", "tunnel", "well", "hero_grave", "sorcerer_tower",
    "fort", "windmill", "cathedral", "grand_lift", "divine_tower", "colosseum",
    "castle", "minor_erdtree", "town", "village", "mausoleum", "eternal_city",
    "belfries", "landmark", "capital", "underground", "study_hall",
    "miquella_cross", "manse", "gaol", "ruined_forge", "unknown",
    "spirit_spring", "caravan", "puzzle", "hidden_passage", "teleporter",
}

problems: list[str] = []


def check(cond: bool, message: str) -> None:
    if not cond:
        problems.append(message)


def iter_acquisition_items(relations: list[dict]):
    for relation in relations:
        for item in relation.get("items", []):
            yield relation, item


def main() -> int:
    registry = json.loads((DATA / "entities" / "entity-registry.json").read_text(encoding="utf-8"))
    acquisitions = json.loads((DATA / "entities" / "acquisition-registry.json").read_text(encoding="utf-8"))
    locations = json.loads((DATA / "entities" / "location-catalog.json").read_text(encoding="utf-8"))
    graph = json.loads((DATA / "graph-v1.json").read_text(encoding="utf-8"))
    gaps = json.loads((DATA / "entities" / "gap-catalog.json").read_text(encoding="utf-8"))
    reinforce = json.loads((DATA / "entities" / "reinforce-catalog.json").read_text(encoding="utf-8"))
    pickups = json.loads((DATA / "entities" / "pickup-location-bindings.json").read_text(encoding="utf-8"))
    spawn_path = DATA / "entities" / "enemy-spawn-bindings.json"
    spawns = json.loads(spawn_path.read_text(encoding="utf-8")) if spawn_path.is_file() else {"bindings": []}
    merchant_path = DATA / "entities" / "merchant-shop-bindings.json"
    merchant_bindings = json.loads(merchant_path.read_text(encoding="utf-8")) if merchant_path.is_file() else {"bindings": []}
    semantic_alias_path = DATA / "entities" / "merchant-shop-semantic-aliases.json"
    semantic_aliases = json.loads(
        semantic_alias_path.read_text(encoding="utf-8")
    ) if semantic_alias_path.is_file() else {"aliases": []}
    boss_endpoint_path = DATA / "entities" / "boss-reward-endpoints.json"
    boss_endpoints = json.loads(boss_endpoint_path.read_text(encoding="utf-8")) if boss_endpoint_path.is_file() else {"endpoints": []}
    event_reward_path = DATA / "entities" / "event-reward-bindings.json"
    event_rewards = json.loads(event_reward_path.read_text(encoding="utf-8")) if event_reward_path.is_file() else {"bindings": []}
    talk_reward_path = DATA / "entities" / "talk-item-lot-bindings.json"
    talk_rewards = json.loads(talk_reward_path.read_text(encoding="utf-8")) if talk_reward_path.is_file() else {"bindings": []}
    quest_reward_path = DATA / "entities" / "quest-reward-bindings.json"
    quest_rewards = json.loads(quest_reward_path.read_text(encoding="utf-8")) if quest_reward_path.is_file() else {"bindings": []}
    gesture_path = DATA / "entities" / "gesture-acquisition-bindings.json"
    gesture_acquisitions = json.loads(gesture_path.read_text(encoding="utf-8")) if gesture_path.is_file() else {"bindings": []}
    tutorial_path = DATA / "entities" / "tutorial-unlock-bindings.json"
    tutorial_unlocks = json.loads(tutorial_path.read_text(encoding="utf-8")) if tutorial_path.is_file() else {"bindings": []}
    special_path = DATA / "entities" / "verified-special-acquisition-bindings.json"
    special_acquisitions = json.loads(special_path.read_text(encoding="utf-8"))

    # ---- 1. entity registry -------------------------------------------------
    entities = registry["entities"]
    ids = [e["id"] for e in entities]
    entity_by_id = {e["id"]: e for e in entities}
    check(len(ids) == len(set(ids)), f"entity ids not unique: {len(ids)} vs {len(set(ids))}")
    check(len(entities) > 0, "empty entity registry")
    for e in entities:
        check(bool(e["name"].get("en")), f"entity {e['id']} missing english name")
        check(bool(e["name"].get("zh")), f"entity {e['id']} missing chinese name")
        check(e["signifiers"], f"entity {e['id']} has no signifiers")
        if "[ERROR]" in (e["name"].get("en") or ""):
            check(False, f"entity {e['id']} has [ERROR] name: {e['name']['en']}")
    gesture_entities = [e for e in entities if e.get("category") == "gesture"]
    gesture_rows = []
    for entity in gesture_entities:
        gesture_signifiers = [
            signifier for signifier in entity.get("signifiers", [])
            if signifier.get("type") == "param"
            and signifier.get("param") == "GestureParam"
        ]
        check(gesture_signifiers, f"gesture {entity['id']} missing GestureParam signifier")
        check(
            any(
                signifier.get("type") == "category_alias"
                and signifier.get("zh") == "表情动作"
                for signifier in entity.get("signifiers", [])
            ),
            f"gesture {entity['id']} missing category alias",
        )
        gesture_rows.extend(
            row for signifier in gesture_signifiers for row in signifier.get("rows", [])
        )
    check(len(gesture_rows) == len(set(gesture_rows)), "GestureParam rows assigned to multiple entities")
    check(len(gesture_entities) >= 50, f"gesture entity coverage too low: {len(gesture_entities)}")
    print(f"gesture entities: {len(gesture_entities)}; GestureParam rows={len(gesture_rows)}")
    by_kind_name = Counter((e["kind"], e["name"]["en"]) for e in entities)
    dup_names = {n: c for n, c in by_kind_name.items() if c > 1}
    check(not dup_names, f"duplicate kind+name entities: {dict(list(dup_names.items())[:8])}")
    same_name_item_spell = {
        name
        for name in {e["name"]["en"] for e in entities}
        if {e["kind"] for e in entities if e["name"]["en"] == name}
        >= {"item", "spell"}
    }
    check(same_name_item_spell == {"Golden Vow"},
          f"unexpected same-name item/spell entities: {sorted(same_name_item_spell)}")
    print(f"entity registry: {len(entities)} entities, {len(set(ids))} unique ids")

    # ---- 2. acquisition registry -------------------------------------------
    rels = acquisitions["relations"]
    entity_ids = set(ids)
    check(len(rels) > 0, "empty acquisition registry")
    special_bindings = special_acquisitions["bindings"]
    special_ids = [binding["id"] for binding in special_bindings]
    check(len(special_ids) == len(set(special_ids)) == 6,
          f"special acquisition binding ids invalid: {special_ids}")
    special_relations = {rel["id"]: rel for rel in rels if rel["id"] in set(special_ids)}
    check(set(special_relations) == set(special_ids), "special acquisition relations missing")
    expected_special_items = {
        "item_phantom_bloody_finger", "item_phantom_recusant_finger",
        "item_phantom_great_rune", "item_grave_keeper_s_brainpan",
        "item_nailstone", "item_roundrock",
    }
    check({binding["item"] for binding in special_bindings} == expected_special_items,
          "special acquisition fixture item set changed")
    for binding in special_bindings:
        relation = special_relations.get(binding["id"], {})
        check(not relation.get("endpointInstances"),
              f"special acquisition {binding['id']} invented a positioned endpoint")
        if binding["method"] == "session_grant":
            check(binding.get("temporary") is True and binding.get("quantity") == 3,
                  f"session grant {binding['id']} must be temporary quantity 3")
            check(bool(binding.get("condition")), f"session grant {binding['id']} missing condition")
        elif binding["method"] == "harvest":
            check(len(binding.get("sourceItemLotRows", [])) == 1,
                  f"harvest {binding['id']} missing exact ItemLotParam_map row")
            check(bool(binding.get("region")), f"harvest {binding['id']} missing region evidence")
    npc_map_drops = [rel for rel in rels if rel.get("method") == "npc_map_drop"]
    check(len(npc_map_drops) == acquisitions.get("stats", {}).get("npc_map_drop") == 142,
          "NPC map-drop relation coverage changed")
    check(len({row for rel in npc_map_drops for row in rel.get("sourceItemLotRows", [])}) == 59,
          "NPC map-drop root coverage changed")
    for relation in npc_map_drops:
        check(relation.get("verification") == "local_npc_map_item_lot_verified",
              f"NPC map drop {relation['id']} has weak verification")
        check(len(relation.get("sourceNpcParamRows", [])) == 1,
              f"NPC map drop {relation['id']} must retain one exact NpcParam source row")
        check(len(relation.get("sourceItemLotRows", [])) == 1,
              f"NPC map drop {relation['id']} must retain one exact map-lot row")
        check(bool(relation.get("from")) and bool(relation.get("items")),
              f"NPC map drop {relation['id']} has unresolved source or items")
    role_rewards = [rel for rel in rels if rel.get("method") == "multiplayer_role_reward"]
    check(len(role_rewards) == acquisitions.get("stats", {}).get("multiplayer_role_reward") == 15,
          "multiplayer role reward relation coverage changed")
    check(len({row for rel in role_rewards for row in rel.get("sourceItemLotRows", [])}) == 7,
          "multiplayer role reward root coverage changed")
    for relation in role_rewards:
        check(relation.get("verification") == "local_role_param_item_lot_verified",
              f"multiplayer role reward {relation['id']} has weak verification")
        check(len(relation.get("sourceRoleParamRows", [])) == 1,
              f"multiplayer role reward {relation['id']} must retain one RoleParam row")
        check(len(relation.get("sourceItemLotRows", [])) == 1 and bool(relation.get("items")),
              f"multiplayer role reward {relation['id']} has unresolved lot or items")
        check(not relation.get("from") and not relation.get("endpointInstances"),
              f"multiplayer role reward {relation['id']} invented a world-space source")
        check(relation.get("triggerStatus") == "role_reward_trigger_not_encoded_by_this_param",
              f"multiplayer role reward {relation['id']} overstates its trigger")
    for rel in rels:
        check(rel["method"] in KNOWN_METHODS, f"relation {rel['id']} unknown method {rel['method']}")
        if rel.get("from"):
            check(rel["from"] in entity_ids, f"relation {rel['id']} from {rel['from']} unresolved")
        for it in rel.get("items", []):
            check(it.get("item") in entity_ids,
                  f"relation {rel['id']} item {it.get('item')} unresolved")
            check(bool(it["name"].get("en")), f"relation {rel['id']} item missing name")
            if it.get("sourceItemId"):
                check(bool(it.get("sourceName")),
                      f"relation {rel['id']} canonicalized item missing sourceName")
        for endpoint in rel.get("endpointInstances", []):
            binding = endpoint.get("topologyBinding") or {}
            map_status = binding.get("mapBindingStatus")
            check(map_status in KNOWN_MAP_BINDING_STATUSES,
                  f"relation {rel['id']} endpoint has invalid map binding status {map_status}")
            map_ids = binding.get("mapIds") or []
            map_node_ids = binding.get("mapNodeIds") or []
            candidate_ids = binding.get("mapCandidateIds") or []
            candidate_node_ids = binding.get("mapCandidateNodeIds") or []
            if map_status in {"exact_map_instance", "exact_map_instance_alias"}:
                if map_status == "exact_map_instance":
                    check(len(map_ids) == 1,
                          f"relation {rel['id']} endpoint exact map binding has invalid map count")
                else:
                    check(bool(map_ids),
                          f"relation {rel['id']} endpoint exact alias binding is empty")
                    if len(map_ids) > 1:
                        check(
                            any(
                                "content-equivalent" in evidence
                                and "normalized SHA-256" in evidence
                                for evidence in binding.get("mapBindingEvidence", [])
                            ),
                            f"relation {rel['id']} endpoint multi-map alias lacks content-equivalence evidence",
                        )
                check(map_node_ids == [f"local_map_{map_id}" for map_id in map_ids],
                      f"relation {rel['id']} endpoint exact map node mismatch")
                check(not candidate_ids and not candidate_node_ids,
                      f"relation {rel['id']} endpoint exact map retains candidates")
            if map_status == "candidate_map_instance":
                check(candidate_ids and candidate_node_ids,
                      f"relation {rel['id']} endpoint candidate map binding is empty")
                check(candidate_node_ids == [f"local_map_{map_id}" for map_id in candidate_ids],
                      f"relation {rel['id']} endpoint candidate map node mismatch")
            if map_status not in {"exact_map_instance", "exact_map_instance_alias"}:
                check(not map_ids and not map_node_ids,
                      f"relation {rel['id']} endpoint non-exact map binding contains exact map")
            layer_ids = binding.get("nativeLayerNodeIds") or []
            if layer_ids:
                check(map_status in {"exact_map_instance", "exact_map_instance_alias"},
                      f"relation {rel['id']} endpoint layer binding lacks exact map")
        if rel.get("method") == "online_map":
            check(rel.get("verification") == "online_map_exact_official_name_match",
                  f"online map relation {rel['id']} has weak verification")
            endpoints = rel.get("endpointInstances", [])
            check(len(endpoints) == 1, f"online map relation {rel['id']} must have one endpoint")
            for endpoint in endpoints:
                check(endpoint.get("kind") == "online_map_marker",
                      f"online map relation {rel['id']} has invalid endpoint kind")
                check(endpoint.get("markerId"), f"online map relation {rel['id']} missing marker id")
                check(endpoint.get("mapMaster") in {"M00", "M01", "M10"},
                      f"online map relation {rel['id']} has invalid map master")
                pixel = endpoint.get("pixelPosition") or {}
                check(all(isinstance(pixel.get(axis), (int, float)) for axis in ("x", "y")),
                      f"online map relation {rel['id']} missing pixel coordinates")
                binding = endpoint.get("topologyBinding") or {}
                check(binding.get("status") == "coordinate_endpoint",
                      f"online map relation {rel['id']} must remain coordinate-only")
                check(not binding.get("routeNodeIds") and not binding.get("semanticNodeIds"),
                      f"online map relation {rel['id']} invented a topology node")
        if rel.get("method") == "online_guide":
            check(rel.get("verification") == "online_guide_exact_unique_official_name_match",
                  f"online guide relation {rel['id']} has weak verification")
            endpoints = rel.get("endpointInstances", [])
            check(len(endpoints) == 1, f"online guide relation {rel['id']} must have one endpoint")
            guide_item = rel.get("onlineGuideItem") or {}
            check(guide_item.get("sourceId") == rel["id"].removeprefix("online-guide-"),
                  f"online guide relation {rel['id']} source item mismatch")
            for item in rel.get("items", []):
                check(item.get("externalSourceId") == guide_item.get("sourceId"),
                      f"online guide relation {rel['id']} missing external source id")
                check(item.get("externalSourceName") == guide_item.get("name"),
                      f"online guide relation {rel['id']} source name is not exact")
            for endpoint in endpoints:
                check(endpoint.get("kind") == "online_guide_marker",
                      f"online guide relation {rel['id']} has invalid endpoint kind")
                check(endpoint.get("sourceItemId") == guide_item.get("sourceId"),
                      f"online guide relation {rel['id']} endpoint source mismatch")
                check(endpoint.get("markerId") is not None,
                      f"online guide relation {rel['id']} missing marker id")
                check(isinstance(endpoint.get("mapCode"), str) and endpoint.get("mapCode"),
                      f"online guide relation {rel['id']} missing map code")
                position = endpoint.get("position") or {}
                check(all(isinstance(position.get(axis), (int, float)) for axis in ("lat", "lng")),
                      f"online guide relation {rel['id']} missing map coordinates")
                check(endpoint.get("coordinateSpace") == "aether_map_lat_lng",
                      f"online guide relation {rel['id']} has an unknown coordinate space")
                binding = endpoint.get("topologyBinding") or {}
                check(binding.get("status") == "coordinate_endpoint",
                      f"online guide relation {rel['id']} must remain coordinate-only")
                check(not binding.get("routeNodeIds") and not binding.get("semanticNodeIds"),
                      f"online guide relation {rel['id']} invented a topology node")
        if rel.get("method") == "online_item_map":
            check(rel.get("verification") in {
                "online_item_map_exact_unique_official_name_match",
                "online_item_map_source_param_id_unique_kind_match",
                "online_item_map_exact_name_or_source_param_id_unique_match",
            },
                  f"online item map relation {rel['id']} has weak verification")
            endpoints = rel.get("endpointInstances", [])
            check(len(endpoints) == 1, f"online item map relation {rel['id']} must have one endpoint")
            record = rel.get("onlineItemMapRecord") or {}
            check(record.get("sourceIndex") is not None,
                  f"online item map relation {rel['id']} missing source index")
            check(rel["id"] == f"online-item-map-{record.get('sourceIndex')}",
                  f"online item map relation {rel['id']} source index mismatch")
            for item in rel.get("items", []):
                match_method = item.get("onlineItemMapMatchMethod")
                check(match_method in {"exact_name", "source_param_id"},
                      f"online item map relation {rel['id']} has invalid match method")
                if match_method == "exact_name":
                    check(item.get("externalSourceName") == item.get("name", {}).get("en"),
                          f"online item map relation {rel['id']} source name is not exact")
                else:
                    check(item.get("externalSourceId") is not None,
                          f"online item map relation {rel['id']} param-id match is missing source id")
                check(item.get("quantityStatus") in {"stated", "not_stated"},
                      f"online item map relation {rel['id']} has invalid quantity status")
            for endpoint in endpoints:
                check(endpoint.get("kind") == "online_item_map_endpoint",
                      f"online item map relation {rel['id']} has invalid endpoint kind")
                check(endpoint.get("sourceIndex") == record.get("sourceIndex"),
                      f"online item map relation {rel['id']} endpoint source mismatch")
                check(endpoint.get("coordinateSpace") == "game_world_xyz",
                      f"online item map relation {rel['id']} has an unknown coordinate space")
                position = endpoint.get("position") or {}
                check(all(isinstance(position.get(axis), (int, float)) for axis in ("x", "y", "z")),
                      f"online item map relation {rel['id']} missing XYZ coordinates")
                check(endpoint.get("map"),
                      f"online item map relation {rel['id']} missing map identifier")
                binding = endpoint.get("topologyBinding") or {}
                check(binding.get("status") == "coordinate_endpoint",
                      f"online item map relation {rel['id']} must remain coordinate-only")
                check(not binding.get("routeNodeIds") and not binding.get("semanticNodeIds"),
                      f"online item map relation {rel['id']} invented a topology node")
        if rel.get("method") == "pickup":
            status = rel.get("pickupEndpointStatus")
            check(status in {
                "coordinate_endpoint",
                "source_record_without_coordinates",
                "no_external_location_binding",
            }, f"pickup relation {rel['id']} has invalid endpoint status")
            endpoints = rel.get("endpointInstances", [])
            if status == "coordinate_endpoint":
                check(endpoints, f"pickup relation {rel['id']} missing coordinate endpoint")
                for endpoint in endpoints:
                    check(endpoint.get("kind") == "pickup_endpoint",
                          f"pickup relation {rel['id']} has invalid endpoint kind")
                    check(endpoint.get("sourceLotRow") == (rel.get("lot") or {}).get("rowId"),
                          f"pickup relation {rel['id']} endpoint lot mismatch")
                    check(endpoint.get("coordinateSpace") == "game_world_xyz",
                          f"pickup relation {rel['id']} has unknown coordinate space")
                    position = endpoint.get("position") or {}
                    check(all(isinstance(position.get(axis), (int, float))
                              for axis in ("x", "y", "z")),
                          f"pickup relation {rel['id']} endpoint missing XYZ position")
                    binding = endpoint.get("topologyBinding") or {}
                    check(binding.get("status") == "coordinate_endpoint",
                          f"pickup relation {rel['id']} endpoint has invalid topology status")
                    check(not binding.get("routeNodeIds") and not binding.get("semanticNodeIds"),
                          f"pickup relation {rel['id']} invented a topology node")
            else:
                check(not endpoints,
                      f"pickup relation {rel['id']} has endpoints despite missing coordinates")
        if rel.get("method") == "craft":
            check(rel.get("verification") in {
                      "online_cookbook_product_exact_unique_official_name_match",
                      "online_dataset_dlc_pair_exact_unique_official_entity_match",
                      "local_recipe_and_pinned_default_unlock_exact",
                  },
                  f"craft relation {rel['id']} has weak verification")
            recipe = rel.get("craftRecipe") or {}
            check(isinstance(recipe.get("sourceRecipeId"), (int, str))
                  and bool(recipe.get("sourceRecipeId")),
                  f"craft relation {rel['id']} missing source recipe id")
            if recipe.get("unlockType") == "default":
                check(rel.get("from") == recipe.get("unlockItemId") == "item_crafting_kit",
                      f"default craft relation {rel['id']} has invalid unlock source")
                check(recipe.get("productItemId") == rel.get("items", [{}])[0].get("item"),
                      f"default craft relation {rel['id']} product mismatch")
                local_recipe = rel.get("localRecipe") or {}
                check(local_recipe.get("verification") == "local_param_exact",
                      f"default craft relation {rel['id']} lacks exact local recipe")
                check(local_recipe.get("productItemId") == recipe.get("productItemId"),
                      f"default craft relation {rel['id']} local product mismatch")
                check(isinstance(local_recipe.get("productQuantity"), int)
                      and local_recipe.get("productQuantity") > 0,
                      f"default craft relation {rel['id']} has invalid product quantity")
                local_ingredients = local_recipe.get("ingredients")
                check(isinstance(local_ingredients, list) and local_ingredients,
                      f"default craft relation {rel['id']} has no local ingredients")
                for ingredient in local_ingredients or []:
                    check(ingredient.get("itemId") in entity_ids,
                          f"default craft relation {rel['id']} ingredient is unresolved")
                    check(isinstance(ingredient.get("quantity"), int)
                          and ingredient.get("quantity") > 0,
                          f"default craft relation {rel['id']} ingredient quantity is invalid")
                    check(ingredient.get("quantityStatus") == "local_param_exact",
                          f"default craft relation {rel['id']} ingredient is not locally sourced")
                check(local_recipe.get("unresolvedIngredients") == [],
                      f"default craft relation {rel['id']} has unresolved ingredients")
                continue
            check(rel.get("from") == recipe.get("cookbookItemId"),
                  f"craft relation {rel['id']} cookbook source mismatch")
            check(recipe.get("sourceCookbookName"),
                  f"craft relation {rel['id']} missing source cookbook name")
            check(recipe.get("sourceProductName"),
                  f"craft relation {rel['id']} missing source product name")
            check(recipe.get("productItemId") == rel.get("items", [{}])[0].get("item"),
                  f"craft relation {rel['id']} product mismatch")
            check(all(item.get("craftProduct") is True for item in rel.get("items", [])),
                  f"craft relation {rel['id']} item is not marked as a craft product")
            ingredients_status = recipe.get("ingredientsStatus")
            check(ingredients_status in {
                "not_present_in_source",
                "source_pair_not_found",
                "present",
                "present_exact_unique_entity_match",
                "present_with_unresolved_source_names",
            },
                  f"craft relation {rel['id']} has invalid ingredient status")
            if ingredients_status in {"not_present_in_source", "source_pair_not_found"}:
                check(recipe.get("ingredients") == [],
                      f"craft relation {rel['id']} invents absent ingredients")
            else:
                ingredients = recipe.get("ingredients")
                check(isinstance(ingredients, list) and ingredients,
                      f"craft relation {rel['id']} has no present ingredients")
                for ingredient in ingredients:
                    check(isinstance(ingredient, dict),
                          f"craft relation {rel['id']} has malformed ingredient")
                    check(ingredient.get("sourceName"),
                          f"craft relation {rel['id']} ingredient is missing source name")
                    check(isinstance(ingredient.get("quantity"), int)
                          and ingredient.get("quantity") > 0,
                          f"craft relation {rel['id']} ingredient quantity is invalid")
                    check(ingredient.get("quantityStatus") == "stated_in_source",
                          f"craft relation {rel['id']} ingredient quantity is not sourced")
                    check(ingredient.get("resolution") in {
                        "exact_unique_official_name_match",
                        "unresolved_unique_entity_name_required",
                    }, f"craft relation {rel['id']} ingredient resolution is invalid")
                    if ingredient.get("resolution") == "exact_unique_official_name_match":
                        check(isinstance(ingredient.get("itemId"), str)
                              and ingredient.get("itemId"),
                              f"craft relation {rel['id']} resolved ingredient has no item id")
                        check(ingredient.get("itemId") in entity_ids,
                              f"craft relation {rel['id']} ingredient entity is unresolved")
                if ingredients_status == "present_exact_unique_entity_match":
                    check(all(ingredient.get("itemId") for ingredient in ingredients),
                          f"craft relation {rel['id']} claims exact ingredients with unresolved item")
        if rel.get("method") == "drop":
            root_lot = (rel.get("lot") or {}).get("rowId")
            lot_rows = rel.get("sourceItemLotRows") or []
            check(lot_rows and lot_rows[0] == root_lot,
                  f"drop {rel['id']} missing sequential lot-chain root")
            chain_set = set(lot_rows)
            for item in rel.get("items", []):
                check(item.get("lot") in chain_set,
                      f"drop {rel['id']} item points outside its lot chain")
            if len(lot_rows) > 1:
                check(rel.get("verification") == "local_param_verified_sequential_lot_chain",
                      f"drop {rel['id']} sequential chain has weak verification")
        if rel.get("method") == "pickup":
            root_lot = (rel.get("lot") or {}).get("rowId")
            lot_rows = rel.get("sourceItemLotRows") or []
            check(lot_rows and lot_rows[0] == root_lot,
                  f"pickup {rel['id']} missing sequential lot-chain root")
            chain_set = set(lot_rows)
            for item in rel.get("items", []):
                check(item.get("lot") in chain_set,
                      f"pickup {rel['id']} item points outside its lot chain")
            if len(lot_rows) > 1:
                check(rel.get("verification") == "local_param_verified_sequential_lot_chain",
                      f"pickup {rel['id']} sequential chain has weak verification")
    methods = Counter(r["method"] for r in rels)
    endpoint_map_status_counts = Counter(
        (endpoint.get("topologyBinding") or {}).get("mapBindingStatus")
        for relation in rels
        for endpoint in relation.get("endpointInstances", [])
    )
    endpoint_layer_count = sum(
        bool((endpoint.get("topologyBinding") or {}).get("nativeLayerNodeIds"))
        for relation in rels
        for endpoint in relation.get("endpointInstances", [])
    )
    topology_stats = acquisitions.get("stats", {})
    check(sum(endpoint_map_status_counts.values()) == topology_stats.get("topologyMapEndpointCount"),
          "topology map endpoint count does not match stats")
    check(
        sum(endpoint_map_status_counts.get(status, 0)
            for status in ("exact_map_instance", "exact_map_instance_alias"))
        == topology_stats.get("topologyMapExactMapInstanceEndpointCount"),
        "topology exact map endpoint count does not match stats",
    )
    check(endpoint_layer_count == topology_stats.get("topologyMapExactLayerEndpointCount"),
          "topology exact layer endpoint count does not match stats")
    check(endpoint_map_status_counts.get("candidate_map_instance", 0)
          == topology_stats.get("topologyMapCandidateEndpointCount"),
          "topology candidate endpoint count does not match stats")
    check(endpoint_map_status_counts.get("external_map_scope", 0)
          == topology_stats.get("topologyMapExternalScopeEndpointCount"),
          "topology external endpoint count does not match stats")
    check(sum(endpoint_map_status_counts.get(status, 0)
              for status in ("unresolved_map_instance", "unresolved_map_scope", "map_index_unavailable"))
          == topology_stats.get("topologyMapUnresolvedEndpointCount"),
          "topology unresolved endpoint count does not match stats")
    print(f"acquisition registry: {len(rels)} relations, methods={dict(methods)}")
    print(
        "endpoint map bindings: "
        f"total={sum(endpoint_map_status_counts.values())}; "
        f"exact-map={topology_stats.get('topologyMapExactMapInstanceEndpointCount', 0)}; "
        f"exact-layer={topology_stats.get('topologyMapExactLayerEndpointCount', 0)}; "
        f"candidate={topology_stats.get('topologyMapCandidateEndpointCount', 0)}; "
        f"external={topology_stats.get('topologyMapExternalScopeEndpointCount', 0)}; "
        f"unresolved={topology_stats.get('topologyMapUnresolvedEndpointCount', 0)}"
    )
    drop_relations = [rel for rel in rels if rel.get("method") == "drop"]
    acquisition_stats = acquisitions.get("stats", {})
    all_gaps = acquisitions.get("coverageGaps", [])
    all_gap_ids = [gap.get("id") for gap in all_gaps]
    check(len(all_gap_ids) == len(set(all_gap_ids)), "acquisition coverage gap ids are not unique")
    drop_stats = acquisition_stats
    drop_gaps = [gap for gap in all_gaps if gap.get("method") == "drop"]
    pickup_gaps = [gap for gap in all_gaps if gap.get("method") == "pickup"]
    unclassified_map_lot_gaps = [
        gap for gap in all_gaps
        if gap.get("method") == "unclassified_param"
    ]
    pickup_source_exclusions = acquisitions.get("sourceExclusions", [])
    event_reward_pickup_exclusions = [
        row for row in pickup_source_exclusions
        if row.get("status") == "classified_event_award_not_fixed_pickup"
    ]
    talk_reward_pickup_exclusions = [
        row for row in pickup_source_exclusions
        if row.get("status") == "classified_talk_award_not_fixed_pickup"
    ]
    orphan_treasure_exclusions = [
        row for row in pickup_source_exclusions
        if row.get("status") == "orphan_treasure_event_without_part"
    ]
    shop_gaps = [gap for gap in all_gaps if gap.get("method") == "purchase"]
    drop_gap_ids = [gap.get("id") for gap in drop_gaps]
    allowed_drop_gap_statuses = {
        "source_lot_missing",
        "source_lot_empty",
        "item_name_unresolved",
    }
    for gap in drop_gaps:
        check(gap.get("method") == "drop", f"enemy drop gap {gap.get('id')} has invalid method")
        check(gap.get("status") in allowed_drop_gap_statuses,
              f"enemy drop gap {gap.get('id')} has invalid status")
        check(isinstance(gap.get("sourceItemLotRoot"), int),
              f"enemy drop gap {gap.get('id')} has no source lot root")
        check(gap.get("sourceNpcParamRows"),
              f"enemy drop gap {gap.get('id')} has no source NpcParam rows")
        check(gap.get("verification") == "local_param_gap",
              f"enemy drop gap {gap.get('id')} has weak verification")
    drop_roots = {rel.get("lot", {}).get("rowId") for rel in drop_relations}
    check(len(drop_relations) == drop_stats.get("dropRelationCount"),
          "drop relation count does not match coverage stats")
    check(len(drop_roots) == drop_stats.get("dropRelationRootCount"),
          "drop relation root count does not match coverage stats")
    check(len(drop_gaps) == drop_stats.get("dropGapCount"),
          "drop gap count does not match coverage stats")
    check(drop_stats.get("dropRootCount", 0) == (
        drop_stats.get("dropRootWithResolvedItems", 0)
        + drop_stats.get("dropRootMissingLotRowCount", 0)
        + drop_stats.get("dropRootEmptyLotCount", 0)
        + drop_stats.get("dropRootWithUnresolvedNamesOnly", 0)
    ), "enemy drop root coverage does not reconcile")
    check(drop_stats.get("dropRootWithResolvedItems") == len(drop_roots),
          "resolved enemy drop roots do not match emitted relation roots")
    check(not (drop_roots & {
        gap.get("sourceItemLotRoot") for gap in drop_gaps
    }), "enemy drop root is both emitted and listed as a gap")
    print(
        f"enemy drop coverage: roots={drop_stats.get('dropRootCount', 0)}; "
        f"relations={len(drop_relations)}; gaps={len(drop_gaps)}; "
        f"raw-slots={drop_stats.get('dropRawItemSlotCount', 0)}; "
        f"resolved-slots={drop_stats.get('dropResolvedItemSlotCount', 0)}"
    )
    pickup_relations = [rel for rel in rels if rel.get("method") == "pickup"]
    pickup_by_id = {rel.get("id"): rel for rel in pickup_relations}
    allowed_pickup_gap_statuses = {
        "no_external_location_binding",
        "source_record_without_coordinates",
    }
    for gap in pickup_gaps:
        check(gap.get("status") in allowed_pickup_gap_statuses,
              f"pickup gap {gap.get('id')} has invalid status")
        check(gap.get("verification") == "local_param_gap",
              f"pickup gap {gap.get('id')} has weak verification")
        relation = pickup_by_id.get(gap.get("relationId"))
        check(relation is not None,
              f"pickup gap {gap.get('id')} references missing pickup relation")
        if relation is not None:
            check(relation.get("pickupEndpointStatus") == gap.get("status"),
                  f"pickup gap {gap.get('id')} status mismatch")
            check(not relation.get("endpointInstances"),
                  f"pickup gap {gap.get('id')} references a coordinate endpoint")
            check(gap.get("sourceItemLotRoot") == (relation.get("lot") or {}).get("rowId"),
                  f"pickup gap {gap.get('id')} lot root mismatch")
            check(gap.get("sourceItemLotRows") == relation.get("sourceItemLotRows"),
                  f"pickup gap {gap.get('id')} lot chain mismatch")
    check(len(pickup_gaps) == acquisition_stats.get("pickup_coverageGapCount"),
          "pickup coverage gap count does not match stats")
    check(
        sum(gap.get("status") == "no_external_location_binding" for gap in pickup_gaps)
        == acquisition_stats.get("pickup_coverageGapNoExternalLocationBindingCount"),
        "pickup no-binding gap count does not match stats",
    )
    check(
        sum(gap.get("status") == "source_record_without_coordinates" for gap in pickup_gaps)
        == acquisition_stats.get("pickup_coverageGapSourceRecordWithoutCoordinatesCount"),
        "pickup no-coordinate gap count does not match stats",
    )
    print(
        f"pickup coverage: relations={len(pickup_relations)}; "
        f"gaps={len(pickup_gaps)}; "
        f"no-binding={acquisition_stats.get('pickup_coverageGapNoExternalLocationBindingCount', 0)}; "
        f"no-coordinate={acquisition_stats.get('pickup_coverageGapSourceRecordWithoutCoordinatesCount', 0)}"
    )
    check(
        len(event_reward_pickup_exclusions)
        == acquisition_stats.get("pickupEventRewardExclusionCount"),
        "event-reward pickup exclusion count does not match stats",
    )
    check(
        len(talk_reward_pickup_exclusions)
        == acquisition_stats.get("pickupTalkRewardExclusionCount"),
        "talk-reward pickup exclusion count does not match stats",
    )
    check(
        len(orphan_treasure_exclusions)
        == acquisition_stats.get("pickupOrphanTreasureExclusionCount"),
        "orphan Treasure exclusion count does not match stats",
    )
    check(
        len(unclassified_map_lot_gaps)
        == acquisition_stats.get("unclassifiedItemLotParamMapCount"),
        "unclassified ItemLotParam_map count does not match stats",
    )
    published_pickup_rows = {
        row_id
        for relation in pickup_relations
        for row_id in relation.get("sourceItemLotRows", [])
    }
    excluded_rows = {
        exclusion.get("sourceItemLotRoot")
        for exclusion in pickup_source_exclusions
    }
    unclassified_rows = {
        gap.get("sourceItemLotRoot") for gap in unclassified_map_lot_gaps
    }
    check(not (published_pickup_rows & excluded_rows),
          "event reward lot is also published as a fixed pickup")
    check(not (published_pickup_rows & unclassified_rows),
          "unclassified map lot is also published as a fixed pickup")
    check(not (excluded_rows & unclassified_rows),
          "map lot is both event-classified and unclassified")
    for exclusion in event_reward_pickup_exclusions:
        check(exclusion.get("eventRewardBindingIds"),
              f"pickup exclusion {exclusion.get('id')} has no event binding")
        check(exclusion.get("verification") == "local_param_and_emevd_classified",
              f"pickup exclusion {exclusion.get('id')} has weak verification")
    for exclusion in talk_reward_pickup_exclusions:
        check(exclusion.get("talkItemLotBindingIds"),
              f"talk pickup exclusion {exclusion.get('id')} has no talk binding")
        check(exclusion.get("verification") == "local_param_and_talk_esd_classified",
              f"talk pickup exclusion {exclusion.get('id')} has weak verification")
    for exclusion in orphan_treasure_exclusions:
        check(exclusion.get("sourceTreasureEventIds"),
              f"orphan Treasure exclusion {exclusion.get('id')} has no event identity")
        check(exclusion.get("verification") == "local_msbe_uninstantiated_treasure",
              f"orphan Treasure exclusion {exclusion.get('id')} has weak verification")
    for gap in unclassified_map_lot_gaps:
        check(gap.get("status") == "unreferenced_item_lot_param_map",
              f"unclassified map lot {gap.get('id')} has invalid status")
        check(gap.get("verification") == "local_param_unclassified",
              f"unclassified map lot {gap.get('id')} has weak verification")
    print(
        "non-pickup map lot classification: "
        f"event-reward={len(event_reward_pickup_exclusions)}; "
        f"talk-reward={len(talk_reward_pickup_exclusions)}; "
        f"orphan-treasure={len(orphan_treasure_exclusions)}; "
        f"unclassified={len(unclassified_map_lot_gaps)}"
    )
    purchase_relations = [rel for rel in rels if rel.get("method") == "purchase"]
    purchase_by_id = {rel.get("id"): rel for rel in purchase_relations}
    allowed_shop_gap_statuses = {
        "seller_unresolved_no_external_binding",
        "seller_unresolved_binding",
        "seller_unresolved_candidate_binding",
    }
    for gap in shop_gaps:
        check(gap.get("status") in allowed_shop_gap_statuses,
              f"shop gap {gap.get('id')} has invalid status")
        check(gap.get("verification") == "local_param_gap",
              f"shop gap {gap.get('id')} has weak verification")
        relation = purchase_by_id.get(gap.get("relationId"))
        check(relation is not None, f"shop gap {gap.get('id')} references missing purchase relation")
        if relation is not None:
            check(relation.get("sellerStatus") != "named",
                  f"shop gap {gap.get('id')} references named purchase relation")
            check(gap.get("lineupRow") == relation.get("lineupRow"),
                  f"shop gap {gap.get('id')} lineup row mismatch")
            check(gap.get("shopContext") == relation.get("from"),
                  f"shop gap {gap.get('id')} shop context mismatch")
            check(bool(gap.get("hasCandidateBinding")) == bool(relation.get("merchantShopBinding")),
                  f"shop gap {gap.get('id')} candidate-binding flag mismatch")
    check(len(shop_gaps) == acquisition_stats.get("shop_coverageGapCount"),
          "shop coverage gap count does not match stats")
    check(
        sum(gap.get("status") == "seller_unresolved_no_external_binding" for gap in shop_gaps)
        == acquisition_stats.get("shop_coverageGapSellerUnresolvedNoExternalBindingCount"),
        "shop no-binding gap count does not match stats",
    )
    check(
        sum(gap.get("status") == "seller_unresolved_binding" for gap in shop_gaps)
        == acquisition_stats.get("shop_coverageGapSellerUnresolvedBindingCount"),
        "shop unresolved-binding gap count does not match stats",
    )
    check(
        sum(gap.get("status") == "seller_unresolved_candidate_binding" for gap in shop_gaps)
        == acquisition_stats.get("shop_coverageGapSellerUnresolvedCandidateBindingCount"),
        "shop candidate-binding gap count does not match stats",
    )
    print(
        f"shop coverage: relations={len(purchase_relations)}; "
        f"gaps={len(shop_gaps)}; "
        f"no-binding={acquisition_stats.get('shop_coverageGapSellerUnresolvedNoExternalBindingCount', 0)}; "
        f"candidate={acquisition_stats.get('shop_coverageGapSellerUnresolvedCandidateBindingCount', 0)}; "
        f"binding-only={acquisition_stats.get('shop_coverageGapSellerUnresolvedBindingCount', 0)}"
    )
    online_item_map_gaps = [gap for gap in all_gaps if gap.get("method") == "online_item_map"]
    for gap in online_item_map_gaps:
        check(gap.get("status") in {"source_item_unmatched", "source_item_ambiguous"},
              f"online item map gap {gap.get('id')} has invalid status")
        check(gap.get("verification") == "online_item_map_source_record_unresolved",
              f"online item map gap {gap.get('id')} has weak verification")
        check(gap.get("sourceIndex") is not None,
              f"online item map gap {gap.get('id')} is missing source index")
        check(gap.get("sourceItemIndex") is not None,
              f"online item map gap {gap.get('id')} is missing source item index")
        endpoints = gap.get("endpointInstances", [])
        check(len(endpoints) == 1,
              f"online item map gap {gap.get('id')} must retain one endpoint")
        if endpoints:
            endpoint = endpoints[0]
            check(endpoint.get("kind") == "online_item_map_endpoint",
                  f"online item map gap {gap.get('id')} has invalid endpoint kind")
            check(endpoint.get("sourceIndex") == gap.get("sourceIndex"),
                  f"online item map gap {gap.get('id')} source index mismatch")
            check(endpoint.get("coordinateSpace") == "game_world_xyz",
                  f"online item map gap {gap.get('id')} has invalid coordinate space")
            position = endpoint.get("position") or {}
            check(all(isinstance(position.get(axis), (int, float)) for axis in ("x", "y", "z")),
                  f"online item map gap {gap.get('id')} has invalid coordinates")
        if gap.get("status") == "source_item_ambiguous":
            check(gap.get("candidateEntityIds"),
                  f"online item map ambiguous gap {gap.get('id')} has no candidates")
    check(len(online_item_map_gaps) == acquisition_stats.get("onlineItemMapCoverageGapCount"),
          "online item map gap count does not match coverage stats")
    check(
        sum(gap.get("status") == "source_item_unmatched" for gap in online_item_map_gaps)
        == acquisition_stats.get("onlineItemMapUnmatchedItemOccurrenceCount"),
        "online item map unmatched gap count does not match coverage stats",
    )
    check(
        sum(gap.get("status") == "source_item_ambiguous" for gap in online_item_map_gaps)
        == acquisition_stats.get("onlineItemMapAmbiguousItemOccurrenceCount"),
        "online item map ambiguous gap count does not match coverage stats",
    )
    print(
        f"online item map gaps: {len(online_item_map_gaps)}; "
        f"unmatched={acquisition_stats.get('onlineItemMapUnmatchedItemOccurrenceCount', 0)}; "
        f"ambiguous={acquisition_stats.get('onlineItemMapAmbiguousItemOccurrenceCount', 0)}"
    )
    online_guide_gaps = [gap for gap in all_gaps if gap.get("method") == "online_guide"]
    for gap in online_guide_gaps:
        check(gap.get("status") in {
            "source_item_no_map",
            "source_map_invalid",
            "source_item_unmatched",
            "source_item_ambiguous",
        }, f"online guide gap {gap.get('id')} has invalid status")
        check(gap.get("verification") == "online_guide_source_record_unresolved",
              f"online guide gap {gap.get('id')} has weak verification")
        check(gap.get("externalSourceId"),
              f"online guide gap {gap.get('id')} is missing source id")
        endpoints = gap.get("endpointInstances", [])
        if gap.get("status") in {"source_item_unmatched", "source_item_ambiguous"}:
            check(len(endpoints) == 1,
                  f"online guide gap {gap.get('id')} must retain its map endpoint")
            if endpoints:
                endpoint = endpoints[0]
                check(endpoint.get("kind") == "online_guide_marker",
                      f"online guide gap {gap.get('id')} has invalid endpoint kind")
                position = endpoint.get("position") or {}
                check(all(isinstance(position.get(axis), (int, float)) for axis in ("lat", "lng")),
                      f"online guide gap {gap.get('id')} has invalid coordinates")
        else:
            check(not endpoints,
                  f"online guide gap {gap.get('id')} unexpectedly has a map endpoint")
        if gap.get("status") == "source_item_ambiguous":
            check(gap.get("candidateEntityIds"),
                  f"online guide ambiguous gap {gap.get('id')} has no candidates")
    check(len(online_guide_gaps) == acquisition_stats.get("onlineGuideCoverageGapCount"),
          "online guide gap count does not match coverage stats")
    check(
        sum(gap.get("status") == "source_item_no_map" for gap in online_guide_gaps)
        == acquisition_stats.get("onlineGuideNoMap"),
        "online guide no-map gap count does not match coverage stats",
    )
    check(
        sum(gap.get("status") == "source_map_invalid" for gap in online_guide_gaps)
        == acquisition_stats.get("onlineGuideInvalidMap"),
        "online guide invalid-map gap count does not match coverage stats",
    )
    check(
        sum(gap.get("status") == "source_item_unmatched" for gap in online_guide_gaps)
        == acquisition_stats.get("onlineGuideUnmatched"),
        "online guide unmatched gap count does not match coverage stats",
    )
    check(
        sum(gap.get("status") == "source_item_ambiguous" for gap in online_guide_gaps)
        == acquisition_stats.get("onlineGuideAmbiguous"),
        "online guide ambiguous gap count does not match coverage stats",
    )
    print(
        f"online guide gaps: {len(online_guide_gaps)}; "
        f"no-map={acquisition_stats.get('onlineGuideNoMap', 0)}; "
        f"unmatched={acquisition_stats.get('onlineGuideUnmatched', 0)}; "
        f"ambiguous={acquisition_stats.get('onlineGuideAmbiguous', 0)}"
    )
    online_map_gaps = [gap for gap in all_gaps if gap.get("method") == "online_map"]
    for gap in online_map_gaps:
        check(gap.get("status") in {"source_marker_unmatched", "source_marker_ambiguous"},
              f"online map gap {gap.get('id')} has invalid status")
        check(gap.get("verification") == "online_map_source_record_unresolved",
              f"online map gap {gap.get('id')} has weak verification")
        check(gap.get("externalSourceId"),
              f"online map gap {gap.get('id')} is missing marker id")
        endpoints = gap.get("endpointInstances", [])
        check(len(endpoints) == 1,
              f"online map gap {gap.get('id')} must retain one marker endpoint")
        if endpoints:
            endpoint = endpoints[0]
            check(endpoint.get("kind") == "online_map_marker",
                  f"online map gap {gap.get('id')} has invalid endpoint kind")
            check(endpoint.get("markerId") == gap.get("externalSourceId"),
                  f"online map gap {gap.get('id')} marker id mismatch")
            pixel = endpoint.get("pixelPosition") or {}
            check(all(isinstance(pixel.get(axis), (int, float)) for axis in ("x", "y")),
                  f"online map gap {gap.get('id')} has invalid pixel coordinates")
        if gap.get("status") == "source_marker_ambiguous":
            check(gap.get("candidateEntityIds"),
                  f"online map ambiguous gap {gap.get('id')} has no candidates")
    check(len(online_map_gaps) == acquisition_stats.get("onlineMapCoverageGapCount"),
          "online map gap count does not match coverage stats")
    check(
        sum(gap.get("status") == "source_marker_unmatched" for gap in online_map_gaps)
        == acquisition_stats.get("onlineMapUnmatched"),
        "online map unmatched gap count does not match coverage stats",
    )
    check(
        sum(gap.get("status") == "source_marker_ambiguous" for gap in online_map_gaps)
        == acquisition_stats.get("onlineMapAmbiguous"),
        "online map ambiguous gap count does not match coverage stats",
    )
    print(
        f"online map gaps: {len(online_map_gaps)}; "
        f"unmatched={acquisition_stats.get('onlineMapUnmatched', 0)}; "
        f"ambiguous={acquisition_stats.get('onlineMapAmbiguous', 0)}"
    )
    online_relations = [rel for rel in rels if rel.get("method") == "online_map"]
    online_stats = acquisitions.get("stats", {})
    check(len(online_relations) == online_stats.get("online_map"),
          "online map relation count does not match registry stats")
    check(online_stats.get("onlineMapAmbiguous") == 0,
          "online map contains ambiguous exact-name bindings")
    check(len(online_relations) >= 800,
          f"online map coverage unexpectedly low: {len(online_relations)}")
    print(
        f"online map endpoints: {len(online_relations)}; "
        f"source markers={online_stats.get('onlineMapMarkerCount', 0)}; "
        f"unmatched={online_stats.get('onlineMapUnmatched', 0)}"
    )
    online_guide_relations = [rel for rel in rels if rel.get("method") == "online_guide"]
    check(len(online_guide_relations) == online_stats.get("online_guide"),
          "online guide relation count does not match registry stats")
    check(online_stats.get("onlineGuideItemCount", 0) >= 2400,
          "online guide source item coverage unexpectedly low")
    check(online_stats.get("onlineGuideMapItemCount", 0) >= 1500,
          "online guide source map coverage unexpectedly low")
    check(len(online_guide_relations) >= 1000,
          f"online guide exact-name coverage unexpectedly low: {len(online_guide_relations)}")
    print(
        f"online guide endpoints: {len(online_guide_relations)}; "
        f"source items={online_stats.get('onlineGuideItemCount', 0)}; "
        f"with map={online_stats.get('onlineGuideMapItemCount', 0)}; "
        f"unmatched={online_stats.get('onlineGuideUnmatched', 0)}; "
        f"ambiguous={online_stats.get('onlineGuideAmbiguous', 0)}"
    )
    online_item_map_relations = [rel for rel in rels if rel.get("method") == "online_item_map"]
    check(len(online_item_map_relations) == online_stats.get("online_item_map"),
          "online item map relation count does not match registry stats")
    check(online_stats.get("onlineItemMapRecordCount", 0) == 31144,
          "online item map source record coverage unexpectedly changed")
    check(online_stats.get("onlineItemMapItemOccurrenceCount", 0) >= 40000,
          "online item map source item coverage unexpectedly low")
    check(online_stats.get("onlineItemMapMatchedItemOccurrenceCount", 0) >= 30000,
          "online item map exact-name coverage unexpectedly low")
    check(
        online_stats.get("onlineItemMapMatchedByExactNameItemOccurrenceCount", 0)
        + online_stats.get("onlineItemMapMatchedBySourceParamIdItemOccurrenceCount", 0)
        == online_stats.get("onlineItemMapMatchedItemOccurrenceCount", 0),
        "online item map match-method counts do not add up",
    )
    check(
        online_stats.get("onlineItemMapSourceParamIdAmbiguousItemOccurrenceCount", 0)
        <= online_stats.get("onlineItemMapAmbiguousItemOccurrenceCount", 0),
        "online item map source-param ambiguity exceeds total ambiguity",
    )
    check(len(online_item_map_relations) >= 24000,
          f"online item map endpoint coverage unexpectedly low: {len(online_item_map_relations)}")
    print(
        f"online item map endpoints: {len(online_item_map_relations)}; "
        f"source records={online_stats.get('onlineItemMapRecordCount', 0)}; "
        f"item occurrences={online_stats.get('onlineItemMapItemOccurrenceCount', 0)}; "
        f"matched items={online_stats.get('onlineItemMapMatchedItemOccurrenceCount', 0)}; "
        f"unmatched={online_stats.get('onlineItemMapUnmatchedItemOccurrenceCount', 0)}; "
        f"ambiguous={online_stats.get('onlineItemMapAmbiguousItemOccurrenceCount', 0)}"
    )
    craft_relations = [rel for rel in rels if rel.get("method") == "craft"]
    check(len(craft_relations) == online_stats.get("craft"),
          "craft relation count does not match registry stats")
    check(online_stats.get("craftRecipeCount", 0) >= 120,
          "craft recipe source coverage unexpectedly low")
    check(len(craft_relations) >= 120,
          f"craft relation coverage unexpectedly low: {len(craft_relations)}")
    online_craft_relations = [
        relation for relation in craft_relations
        if (relation.get("craftRecipe") or {}).get("unlockType") != "default"
    ]
    check(online_stats.get("craftMatchedProductCount") == len(online_craft_relations),
          "craft matched product count does not match relation count")
    check(online_stats.get("craftMatchedCookbookCount") == len(online_craft_relations),
          "craft matched cookbook count does not match relation count")
    check(online_stats.get("craftIngredientsPresentCount") == 124,
          "craft ingredient enrichment coverage unexpectedly changed")
    check(online_stats.get("craftIngredientSourceExactMatchCount") == 124,
          "craft ingredient source exact-match coverage unexpectedly changed")
    check(online_stats.get("craftIngredientSourcePairMismatchCount") == 3,
          "craft ingredient source mismatch count unexpectedly changed")
    check(online_stats.get("craftIngredientCount") == 340,
          "craft ingredient row count unexpectedly changed")
    check(online_stats.get("craftResolvedIngredientCount") == 340,
          "craft resolved ingredient count unexpectedly changed")
    check(online_stats.get("craftUnresolvedIngredientCount") == 0,
          "craft unresolved ingredient count unexpectedly changed")
    check(online_stats.get("localCraftUsableRecipeCount") == len(craft_relations),
          "local craft recipe coverage does not match relation count")
    check(online_stats.get("localCraftOnlineEnrichedCount") == len(online_craft_relations),
          "local craft enrichment count does not match online relations")
    check(online_stats.get("localCraftDefaultRelationCount") == 5,
          "default local craft relation count unexpectedly changed")
    check(online_stats.get("localCraftUnboundUnlockCount") == 0,
          "local craft unlocks remain unbound")
    check(online_stats.get("localCraftUnresolvedProductCount") == 0,
          "local craft products remain unresolved")
    check(online_stats.get("localCraftUnresolvedMaterialCount") == 0,
          "local craft materials remain unresolved")
    check(online_stats.get("pickupBindingCount", 0) >= 3500,
          "pickup binding coverage unexpectedly low")
    check(online_stats.get("pickupEndpointRelationCount", 0) >= 3300,
          "pickup endpoint relation coverage unexpectedly low")
    check(online_stats.get("pickupEndpointInstanceCount", 0) >= 3600,
          "pickup endpoint instance coverage unexpectedly low")
    print(
        f"craft recipe relations: {len(craft_relations)}; "
        f"source recipes={online_stats.get('craftRecipeCount', 0)}; "
        f"ingredients-present={online_stats.get('craftIngredientsPresentCount', 0)}; "
        f"ingredient-rows={online_stats.get('craftIngredientCount', 0)}"
    )
    spell_projections = [rel for rel in rels if rel.get("method") == "spell_acquisition"]
    check(len(spell_projections) == online_stats.get("spell_acquisition"),
          "spell acquisition projection count does not match registry stats")
    check(len(spell_projections) == 0,
          f"name-only spell acquisition projections remain: {len(spell_projections)}")
    aliases = registry.get("entityAliases", {})
    check(registry.get("stats", {}).get("spell_goods_signifiers_merged") == 213,
          "spell Goods signifier merge count drifted")
    check(len(aliases) == registry.get("stats", {}).get("entity_aliases") == 212,
          "spell Goods alias count drifted")
    for source_id, target_id in aliases.items():
        check(source_id not in entity_ids, f"merged alias source remains canonical: {source_id}")
        check(target_id in entity_ids, f"merged alias target is missing: {target_id}")
        check(entity_by_id[target_id].get("kind") == "spell",
              f"merged alias target is not a spell: {target_id}")
    golden_item = entity_by_id.get("item_golden_vow", {})
    golden_spell = entity_by_id.get("spell_golden_vow", {})
    check(golden_item and golden_spell, "Golden Vow item/spell split is missing")
    check(next(s for s in golden_item["signifiers"] if s.get("param") == "EquipParamGoods")["rows"] == [2003170],
          "Golden Vow consumable has incorrect Goods signifier")
    check(next(s for s in golden_spell["signifiers"] if s.get("param") == "EquipParamGoods")["rows"] == [6600],
          "Golden Vow spell has incorrect Goods signifier")
    print(f"spell acquisition projections: {len(spell_projections)}")
    for rel in purchase_relations:
        check(isinstance(rel.get("lineupRow"), int), f"purchase {rel['id']} missing ShopLineupParam row")
        seller_status = rel.get("sellerStatus")
        if seller_status == "named":
            binding = rel.get("merchantShopBinding") or {}
            check(bool(binding.get("merchantName")), f"named purchase {rel['id']} missing merchant name")
            check(bool(rel.get("endpointInstances")), f"named purchase {rel['id']} missing endpoint")
            for endpoint in rel.get("endpointInstances", []):
                check(endpoint.get("merchantName") == binding.get("merchantName"),
                      f"purchase {rel['id']} endpoint seller mismatch")
                check(endpoint.get("map"), f"named purchase {rel['id']} endpoint missing map")
                position = endpoint.get("position")
                check(isinstance(position, dict) and all(axis in position for axis in ("x", "y", "z")),
                      f"named purchase {rel['id']} endpoint missing XYZ")
        else:
            check(rel.get("from", "").startswith("shop_context_"),
                  f"unresolved purchase {rel['id']} must use an isolated shop context")
    custom_weapon_purchases = [
        (relation, item)
        for relation in purchase_relations
        for item in relation.get("items", [])
        if item.get("sourceEquipType") == 5
    ]
    check(len(custom_weapon_purchases) == acquisition_stats.get("shop_customWeaponPurchaseRows"),
          "custom-weapon purchase count does not match stats")
    check(acquisition_stats.get("shop_unresolvedCustomWeaponPurchaseRows") == 0,
          "unresolved custom-weapon shop rows remain")
    for relation, item in custom_weapon_purchases:
        check(str(item.get("item", "")).startswith("weapon_"),
              f"custom weapon purchase {relation['id']} masquerades as another item kind")
        check(item.get("sourceParam") == "EquipParamWeapon",
              f"custom weapon purchase {relation['id']} lacks base weapon identity")
        check(all(isinstance(item.get(key), int) for key in (
            "sourceParamId", "sourceCustomWeaponId", "reinforcementLevel", "attachedGemId"
        )), f"custom weapon purchase {relation['id']} lacks preset provenance")
    sword_lance = [
        relation for relation in purchase_relations
        if any(item.get("item") == "weapon_sword_lance" for item in relation.get("items", []))
    ]
    check(len(sword_lance) == 1, "Sword Lance custom-weapon exchange fixture is missing")
    if sword_lance:
        relation = sword_lance[0]
        item = next(item for item in relation["items"] if item.get("item") == "weapon_sword_lance")
        check(item.get("sourceCustomWeaponId") == 4400039
              and item.get("sourceParamId") == 3500000,
              "Sword Lance fixture resolved the wrong custom/base weapon rows")
        check(any(cost.get("item") == "item_remembrance_of_the_wild_boar_rider"
                  and cost.get("quantity") == 1
                  and cost.get("canonicalStatus") == "exact"
                  for cost in relation.get("materialCost", [])),
              "Sword Lance fixture lacks its exact remembrance cost")
    print(f"purchase endpoint layer: {len(purchase_relations)} relations; named={sum(r.get('sellerStatus') == 'named' for r in purchase_relations)}; unresolved={sum(r.get('sellerStatus') != 'named' for r in purchase_relations)}")
    event_binding_ids = [binding.get("id") for binding in event_rewards.get("bindings", [])]
    check(None not in event_binding_ids, "event reward binding missing id")
    check(len(event_binding_ids) == len(set(event_binding_ids)), "event reward binding ids not unique")
    for binding in event_rewards.get("bindings", []):
        check(binding.get("method") == "event_reward", f"event reward {binding.get('id')} bad method")
        check(isinstance(binding.get("eventId"), int), f"event reward {binding.get('id')} missing event id")
        check(binding.get("taskStatus") == "unclassified",
              f"event reward {binding.get('id')} must remain explicitly unclassified")
        check(binding.get("items"), f"event reward {binding.get('id')} has no items")
        award_source = binding.get("awardSource") or {}
        resolution = award_source.get("resolution")
        direct_grant = binding.get("directGrant") or {}
        if direct_grant:
            check(resolution in {
                "direct_literal_instruction_arguments",
                "direct_literal_item_parameterized_flag",
                "initialize_event_parameter_substitution",
            }, f"direct event reward {binding.get('id')} has invalid award-source resolution")
            check(direct_grant.get("instruction") == "Directly Give Player Item",
                  f"direct event reward {binding.get('id')} has wrong instruction identity")
            check(direct_grant.get("itemType") == 3,
                  f"direct event reward {binding.get('id')} is not a Goods grant")
            check(award_source.get("itemId") == direct_grant.get("itemId"),
                  f"direct event reward {binding.get('id')} source item mismatch")
            check(not binding.get("sourceItemLotRows"),
                  f"direct event reward {binding.get('id')} invents ItemLot rows")
            check(all(item.get("sourceParam") == "EquipParamGoods"
                      and item.get("sourceParamId") == direct_grant.get("itemId")
                      for item in binding.get("items", [])),
                  f"direct event reward {binding.get('id')} item provenance mismatch")
        else:
            check(resolution in {
                "literal_instruction_argument",
                "initialize_event_parameter_substitution",
            }, f"event reward {binding.get('id')} has invalid award-source resolution")
            check(award_source.get("lotId") == (binding.get("itemLot") or {}).get("rowId"),
                  f"event reward {binding.get('id')} award-source lot mismatch")
        if resolution == "initialize_event_parameter_substitution":
            common_keys = (
                "eventId", "instructionIndex", "templateEventId",
                "templateInstructionIndex",
            )
            check(all(isinstance(award_source.get(key), int) for key in common_keys),
                  f"event reward {binding.get('id')} has incomplete parameter-substitution provenance")
            if direct_grant:
                check(bool(award_source.get("parameterMappings")),
                      f"direct event reward {binding.get('id')} lacks argument mappings")
            else:
                check(isinstance(award_source.get("parameterSourceByte"), int),
                      f"event reward {binding.get('id')} lacks parameter source byte")
            check(award_source.get("templateMap"),
                  f"event reward {binding.get('id')} is missing its template map")
    parameterized_fixture = next(
        (
            binding for binding in event_rewards.get("bindings", [])
            if binding.get("id") == "event-reward-common-0-181-via-common-1100-4"
        ),
        None,
    )
    check(parameterized_fixture is not None,
          "known common-event parameter substitution fixture is missing")
    if parameterized_fixture:
        check((parameterized_fixture.get("itemLot") or {}).get("rowId") == 10000,
              "known common-event parameter substitution resolved the wrong lot")
        check(any(
            item.get("item") == "item_talisman_pouch"
            for item in parameterized_fixture.get("items", [])
        ), "known common-event parameter substitution resolved the wrong item")
    direct_stats = event_rewards.get("stats", {})
    check(direct_stats.get("rawDirectItemInstructions") == 127,
          "direct item instruction source count drifted")
    check(direct_stats.get("unresolvedDirectItemInstructions") == 1,
          "direct item unresolved count drifted")
    inverted_statue = next((
        binding for binding in event_rewards.get("bindings", [])
        if binding.get("id") == "event-reward-direct-m34_11_00_00-34112150-73"
    ), None)
    check(inverted_statue is not None, "Carian Inverted Statue direct-grant fixture is missing")
    if inverted_statue:
        check(inverted_statue.get("directGrant") == {
            "instruction": "Directly Give Player Item",
            "itemType": 3,
            "itemId": 8111,
            "baseEventFlagId": 34112155,
            "usedEventFlagBits": 1,
        }, "Carian Inverted Statue direct-grant arguments were decoded incorrectly")
        check(any(item.get("item") == "item_carian_inverted_statue"
                  for item in inverted_statue.get("items", [])),
              "Carian Inverted Statue direct-grant item identity is wrong")
    parameterized_direct = next((
        binding for binding in event_rewards.get("bindings", [])
        if binding.get("id") == "event-reward-direct-common-0-141-via-common-1720-14"
    ), None)
    check(parameterized_direct is not None,
          "parameterized direct-item fixture is missing")
    if parameterized_direct:
        check((parameterized_direct.get("directGrant") or {}).get("itemId") == 9101,
              "parameterized direct-item fixture resolved the wrong Goods row")
    event_relations = [rel for rel in rels if rel.get("method") == "event_reward"]
    for rel in event_relations:
        binding = rel.get("eventRewardBinding") or {}
        check(binding.get("id") == rel.get("id"), f"event reward relation {rel['id']} binding mismatch")
        check(binding.get("taskStatus") == "unclassified",
              f"event reward relation {rel['id']} must remain unclassified")
        if binding.get("directGrant"):
            check(not binding.get("itemLot"),
                  f"direct event reward {rel['id']} invents an ItemLot binding")
            check(not binding.get("sourceItemLotRows"),
                  f"direct event reward {rel['id']} invents a lot chain")
            check(binding.get("verification") == "local_emevd_direct_goods_verified",
                  f"direct event reward {rel['id']} has weak verification")
            continue
        root_lot = (binding.get("itemLot") or {}).get("rowId")
        lot_rows = binding.get("sourceItemLotRows") or []
        check(lot_rows and lot_rows[0] == root_lot,
              f"event reward {rel['id']} missing sequential lot-chain root")
        chain_set = set(lot_rows)
        for item in rel.get("items", []):
            check(item.get("lot") in chain_set or item.get("lot") is None,
                  f"event reward {rel['id']} item points outside its lot chain")
        if len(lot_rows) > 1:
            check(binding.get("verification") == "local_emevd_and_param_verified_sequential_lot_chain",
                  f"event reward {rel['id']} sequential chain has weak verification")
    rogier_event = [
        relation for relation in event_relations
        if any(item.get("item") == "weapon_rogier_s_rapier"
               for item in relation.get("items", []))
    ]
    check(any(
        any(item.get("category") == 6
            and item.get("sourceCustomWeaponId") == 5010
            and item.get("sourceParamId") == 5030000
            and item.get("reinforcementLevel") == 8
            for item in relation.get("items", []))
        for relation in rogier_event
    ), "Rogier's Rapier custom-weapon event fixture is missing")
    dryleaf_event = [
        relation for relation in event_relations
        if any(item.get("item") == "weapon_dryleaf_arts"
               for item in relation.get("items", []))
    ]
    check(any(
        any(item.get("category") == 6
            and item.get("sourceCustomWeaponId") == 4401055
            and item.get("sourceParamId") == 60500000
            and item.get("reinforcementLevel") == 0
            for item in relation.get("items", []))
        for relation in dryleaf_event
    ), "Dryleaf Arts custom-weapon event fixture is missing")
    print(f"event reward evidence: {len(event_binding_ids)} bindings; relations={len(event_relations)}; task identity intentionally unclassified")
    talk_binding_ids = [binding.get("id") for binding in talk_rewards.get("bindings", [])]
    check(None not in talk_binding_ids, "talk reward binding missing id")
    check(len(talk_binding_ids) == len(set(talk_binding_ids)),
          "talk reward binding ids not unique")
    talk_stats = talk_rewards.get("stats", {})
    check(talk_stats.get("bindings") == len(talk_binding_ids),
          "talk reward binding count mismatch")
    check(talk_stats.get("parseFailures") == 0,
          "Talk ESD parser has source failures")
    check(talk_stats.get("resolvedAwardCallDefinitions") == talk_stats.get("syntacticAwardCalls"),
          "Talk ESD contains an award definition with no exact resolved call site")
    for binding in talk_rewards.get("bindings", []):
        check(binding.get("method") == "talk_reward",
              f"talk reward {binding.get('id')} bad method")
        check(binding.get("taskStatus") == "npc_and_quest_unclassified",
              f"talk reward {binding.get('id')} overstates NPC or quest identity")
        check(binding.get("items"), f"talk reward {binding.get('id')} has no items")
        check(binding.get("callSites"), f"talk reward {binding.get('id')} has no exact call site")
        check(not binding.get("endpointInstances"),
              f"talk reward {binding.get('id')} invents an endpoint")
        lot_rows = binding.get("sourceItemLotRows") or []
        root_lot = (binding.get("itemLot") or {}).get("rowId")
        check(lot_rows and lot_rows[0] == root_lot,
              f"talk reward {binding.get('id')} missing lot-chain root")
        for item in binding.get("items", []):
            check(item.get("sourceParam") and isinstance(item.get("sourceParamId"), int),
                  f"talk reward {binding.get('id')} item lacks canonical signifier")
            check(item.get("lot") in set(lot_rows),
                  f"talk reward {binding.get('id')} item points outside lot chain")
    talk_relations = [rel for rel in rels if rel.get("method") == "talk_reward"]
    check(len(talk_relations) == len(talk_binding_ids),
          "talk reward relation count mismatch")
    for relation in talk_relations:
        binding = relation.get("talkItemLotBinding") or {}
        check(binding.get("id") == relation.get("id"),
              f"talk reward relation {relation.get('id')} binding mismatch")
        check(not relation.get("endpointInstances"),
              f"talk reward relation {relation.get('id')} invents an endpoint")
    for relation in rels:
        for item in relation.get("items", []):
            category = item.get("category", item.get("sourceItemCategory"))
            if category != 6:
                continue
            check(str(item.get("item", "")).startswith("weapon_"),
                  f"custom ItemLot item in {relation.get('id')} is not a weapon")
            check(item.get("sourceParam") == "EquipParamWeapon",
                  f"custom ItemLot item in {relation.get('id')} lacks base weapon param")
            check(all(isinstance(item.get(key), int) for key in (
                "sourceParamId", "sourceCustomWeaponId", "reinforcementLevel", "attachedGemId"
            )), f"custom ItemLot item in {relation.get('id')} lacks preset provenance")
    whistle = next((
        binding for binding in talk_rewards.get("bindings", [])
        if binding.get("id") == "talk-item-lot-m00_00_00_00-t000003000-100000"
    ), None)
    check(whistle is not None, "Spectral Steed Whistle Talk ESD fixture is missing")
    if whistle:
        check(any(item.get("sourceParam") == "EquipParamGoods"
                  and item.get("sourceParamId") == 130
                  for item in whistle.get("items", [])),
              "Spectral Steed Whistle fixture resolved the wrong item")
        check(len(whistle.get("callSites", [])) == 2,
              "Spectral Steed Whistle fixture lost a dialogue branch")
    gurranq = [
        relation for relation in talk_relations
        if (relation.get("talkItemLotBinding", {}).get("itemLot") or {}).get("rowId") == 102310
    ]
    check(any({item.get("item") for item in relation.get("items", [])}
              >= {"spell_beast_claw", "spell_stone_of_gurranq"}
              for relation in gurranq),
          "Gurranq Talk ESD fixture did not canonicalize both incantations")
    print(
        f"talk reward evidence: {len(talk_binding_ids)} bindings; "
        f"relations={len(talk_relations)}; unresolved-lots={talk_stats.get('unresolvedLots', 0)}; "
        "NPC identity and endpoints intentionally unclassified"
    )
    gesture_binding_ids = [binding.get("id") for binding in gesture_acquisitions.get("bindings", [])]
    check(None not in gesture_binding_ids, "gesture acquisition binding missing id")
    check(len(gesture_binding_ids) == len(set(gesture_binding_ids)),
          "gesture acquisition binding ids not unique")
    gesture_stats = gesture_acquisitions.get("stats", {})
    check(gesture_stats.get("bindingCount") == len(gesture_binding_ids),
          "gesture acquisition binding count mismatch")
    check(gesture_stats.get("gestureEntityCount") == len(gesture_entities),
          "gesture acquisition entity count mismatch")
    gesture_rows_from_bindings = set()
    for binding in gesture_acquisitions.get("bindings", []):
        check(binding.get("method") in {"gesture_unlock", "initial_loadout"},
              f"gesture acquisition {binding.get('id')} bad method")
        check(binding.get("verification") in {
            "local_starting_class_param_verified",
            "local_emevd_gesture_award_verified",
            "local_talk_esd_gesture_acquisition_verified",
        }, f"gesture acquisition {binding.get('id')} weak verification")
        check(binding.get("items"), f"gesture acquisition {binding.get('id')} has no item")
        for item in binding.get("items", []):
            check(item.get("item") in entity_ids,
                  f"gesture acquisition {binding.get('id')} item unresolved")
            check(item.get("sourceParam") == "GestureParam",
                  f"gesture acquisition {binding.get('id')} lacks GestureParam evidence")
            check(item.get("sourceParamId") == binding.get("gestureParamRow"),
                  f"gesture acquisition {binding.get('id')} row mismatch")
            gesture_rows_from_bindings.add(item.get("sourceParamId"))
    gesture_relations = [
        relation for relation in rels if relation.get("gestureAcquisitionBinding")
    ]
    check(len(gesture_relations) == len(gesture_binding_ids),
          "gesture acquisition relation projection count mismatch")
    for relation in gesture_relations:
        binding = relation.get("gestureAcquisitionBinding") or {}
        check(binding.get("id") == relation.get("id"),
              f"gesture acquisition relation {relation['id']} binding mismatch")
    check(gesture_stats.get("locallyBoundGestureRowCount") == len(gesture_rows_from_bindings),
          "gesture bound-row count mismatch")
    print(
        f"gesture acquisition evidence: {len(gesture_binding_ids)} bindings; "
        f"locally-bound rows={len(gesture_rows_from_bindings)}"
    )
    initial_loadout_relations = [
        relation for relation in rels if relation.get("initialLoadoutBinding")
    ]
    check(len(initial_loadout_relations) == online_stats.get("initialLoadoutRelationCount"),
          "initial loadout relation count mismatch")
    check(online_stats.get("initialLoadout_selectable_class_count") == 10,
          "selectable class count unexpectedly changed")
    check(online_stats.get("initialLoadout_class_relation_count") == 69,
          "class initial-loadout relation count unexpectedly changed")
    check(online_stats.get("initialLoadout_gift_option_count") == 10,
          "selectable gift option count unexpectedly changed")
    check(online_stats.get("initialLoadout_gift_relation_count") == 9,
          "selectable gift relation count unexpectedly changed")
    check(online_stats.get("initialLoadout_unresolved_slot_count") == 0,
          "initial loadout slots remain unresolved")
    for relation in initial_loadout_relations:
        binding = relation["initialLoadoutBinding"]
        check(relation.get("method") == "initial_loadout",
              f"initial loadout relation {relation['id']} has bad method")
        check(binding.get("sourceType") in {
            "selectable_starting_class", "selectable_starting_gift",
        }, f"initial loadout relation {relation['id']} has invalid source type")
        check(binding.get("sources"),
              f"initial loadout relation {relation['id']} has no source rows")
        check(relation.get("verification") in {
            "local_selectable_class_loadout_exact",
            "local_selectable_starting_gift_exact",
        }, f"initial loadout relation {relation['id']} has weak verification")
        check(all(item.get("item") in entity_ids for item in relation.get("items", [])),
              f"initial loadout relation {relation['id']} has unresolved item")
        check(not relation.get("endpointInstances"),
              f"initial loadout relation {relation['id']} invented a map endpoint")
    print(
        f"initial loadout evidence: {len(initial_loadout_relations)} relations; "
        f"classes={online_stats.get('initialLoadout_selectable_class_count')}; "
        f"gift-options={online_stats.get('initialLoadout_gift_option_count')}"
    )
    tutorial_binding_ids = [binding.get("id") for binding in tutorial_unlocks.get("bindings", [])]
    check(None not in tutorial_binding_ids, "tutorial unlock binding missing id")
    check(len(tutorial_binding_ids) == len(set(tutorial_binding_ids)),
          "tutorial unlock binding ids not unique")
    tutorial_stats = tutorial_unlocks.get("stats", {})
    check(tutorial_stats.get("bindingCount") == len(tutorial_binding_ids),
          "tutorial unlock binding count mismatch")
    check(tutorial_stats.get("tutorialEntityCount") == 47,
          "tutorial entity identity coverage changed")
    check(tutorial_stats.get("locallyBoundEntityCount") == 47,
          "tutorial local event coverage changed")
    for binding in tutorial_unlocks.get("bindings", []):
        check(binding.get("method") == "tutorial_unlock",
              f"tutorial unlock {binding.get('id')} bad method")
        check(binding.get("verification") == "local_emevd_tutorial_unlock_verified",
              f"tutorial unlock {binding.get('id')} weak verification")
        check(binding.get("items"), f"tutorial unlock {binding.get('id')} has no item")
        for item in binding.get("items", []):
            check(item.get("item") in entity_ids,
                  f"tutorial unlock {binding.get('id')} item unresolved")
            check(item.get("sourceParam") == "TutorialParam",
                  f"tutorial unlock {binding.get('id')} lacks TutorialParam evidence")
            check(item.get("sourceParamId") == binding.get("tutorialParamRow"),
                  f"tutorial unlock {binding.get('id')} row mismatch")
    tutorial_relations = [relation for relation in rels if relation.get("method") == "tutorial_unlock"]
    check(len(tutorial_relations) == len(tutorial_binding_ids),
          "tutorial unlock relation projection count mismatch")
    check(tutorial_unlocks.get("locallyUnboundEntities") == [],
          "tutorial unresolved entity set changed")
    print(
        f"tutorial unlock evidence: {len(tutorial_binding_ids)} bindings; "
        f"locally-bound entities={tutorial_stats.get('locallyBoundEntityCount')}"
    )
    quest_binding_ids = [binding.get("id") for binding in quest_rewards.get("bindings", [])]
    check(None not in quest_binding_ids, "quest reward binding missing id")
    check(len(quest_binding_ids) == len(set(quest_binding_ids)), "quest reward binding ids not unique")
    quest_stats = quest_rewards.get("stats", {})
    check(quest_stats.get("totalBindings") == len(quest_binding_ids),
          "quest reward total binding count does not match published bindings")
    check(quest_stats.get("strongBindings") == sum(
        binding.get("verification") == "local_award_external_quest_name_and_flag_overlap"
        for binding in quest_rewards.get("bindings", [])
    ), "quest reward strong binding count does not match evidence statuses")
    check(quest_stats.get("referenceBindings") == sum(
        binding.get("verification") == "external_quest_named_reward_reference"
        for binding in quest_rewards.get("bindings", [])
    ), "quest reward external reference count does not match evidence statuses")
    for binding in quest_rewards.get("bindings", []):
        check(binding.get("method") == "quest_reward", f"quest reward {binding.get('id')} bad method")
        if binding.get("from") is not None:
            check(binding.get("from") in entity_ids, f"quest reward {binding.get('id')} NPC unresolved")
        if binding.get("verification") == "local_award_external_quest_name_and_flag_overlap":
            check(binding.get("eventRewardBindingId"), f"quest reward {binding.get('id')} missing local event binding")
            check(binding.get("matchedEventFlagIds"), f"quest reward {binding.get('id')} missing flag intersection")
        else:
            check(binding.get("verification") == "external_quest_named_reward_reference",
                  f"quest reward {binding.get('id')} has unknown evidence status")
            check(binding.get("sourceStatus") == "external_reference_only",
                  f"quest reward {binding.get('id')} missing external-only status")
            check(binding.get("questStep", {}).get("description"),
                  f"quest reward {binding.get('id')} missing external quest description")
            check(all(item.get("quantityStatus") == "not_stated_in_external_step"
                      for item in binding.get("items", [])),
                  f"quest reward {binding.get('id')} missing quantity-unknown status")
        check(binding.get("items"), f"quest reward {binding.get('id')} has no items")
    quest_relations = [rel for rel in rels if rel.get("method") == "quest_reward"]
    for rel in quest_relations:
        binding = rel.get("questRewardBinding") or {}
        check(binding.get("id") == rel.get("id"), f"quest reward relation {rel['id']} binding mismatch")
        check(binding.get("from") == rel.get("from"), f"quest reward relation {rel['id']} NPC mismatch")
        check(binding.get("verification") in {
            "local_award_external_quest_name_and_flag_overlap",
            "external_quest_named_reward_reference",
        }, f"quest reward relation {rel['id']} weak verification")
        for endpoint in rel.get("endpointInstances", []):
            check(endpoint.get("kind") == "quest_npc_endpoint",
                  f"quest reward {rel['id']} has non-quest NPC endpoint")
            check(endpoint.get("map") and endpoint.get("part"),
                  f"quest reward {rel['id']} endpoint missing map or part")
            check(isinstance(endpoint.get("npcParamId"), int),
                  f"quest reward {rel['id']} endpoint missing NpcParam id")
            position = endpoint.get("position")
            check(
                isinstance(position, dict)
                and all(isinstance(position.get(axis), (int, float)) for axis in ("x", "y", "z")),
                f"quest reward {rel['id']} endpoint missing XYZ position",
            )
            topology_binding = endpoint.get("topologyBinding") or {}
            check(topology_binding.get("status") == "coordinate_endpoint",
                  f"quest reward {rel['id']} endpoint must remain coordinate-only")
            check(not topology_binding.get("routeNodeIds") and not topology_binding.get("semanticNodeIds"),
                  f"quest reward {rel['id']} endpoint invented a topology node")
    print(f"quest reward evidence: {len(quest_binding_ids)} bindings; relations={len(quest_relations)}")

    binding_ids = [binding.get("id") for binding in merchant_bindings.get("bindings", [])]
    check(None not in binding_ids, "merchant shop binding missing id")
    check(len(binding_ids) == len(set(binding_ids)), "merchant shop binding ids not unique")
    alias_ids = [alias.get("id") for alias in semantic_aliases.get("aliases", [])]
    check(None not in alias_ids, "semantic merchant alias missing id")
    check(len(alias_ids) == len(set(alias_ids)), "semantic merchant alias ids not unique")
    alias_by_id = {
        alias["id"]: alias for alias in semantic_aliases.get("aliases", [])
    }
    for alias in semantic_aliases.get("aliases", []):
        check(alias.get("merchantName") == "Wandering Mausoleum Corpse",
              f"semantic merchant alias {alias.get('id')} has unexpected name")
        check(alias.get("sellerIdentitySource") == "local_map_semantic_alias",
              f"semantic merchant alias {alias.get('id')} has invalid source")
        check(alias.get("verification") == "local_map_model_thinkparam_walkroute_and_shop_endpoint_exact",
              f"semantic merchant alias {alias.get('id')} has weak verification")
        check(alias.get("modelNames") == ["c4450"],
              f"semantic merchant alias {alias.get('id')} has unexpected model evidence")
        check(alias.get("thinkParamIds") == [44500000],
              f"semantic merchant alias {alias.get('id')} has unexpected ThinkParam evidence")
    for binding in merchant_bindings.get("bindings", []):
        check(isinstance(binding.get("rowId"), int), "merchant binding missing rowId")
        if binding.get("sellerStatus") == "named":
            check(bool(binding.get("merchantName")), f"named merchant binding {binding.get('id')} missing name")
            check(binding.get("position"), f"named merchant binding {binding.get('id')} missing position")
        if binding.get("sellerIdentitySource") == "local_map_semantic_alias":
            alias = alias_by_id.get(binding.get("semanticAliasId"))
            check(alias is not None,
                  f"semantic merchant binding {binding.get('id')} references missing alias")
            if alias is not None:
                check(binding.get("npcParamId") == alias.get("npcParamId"),
                      f"semantic merchant binding {binding.get('id')} NpcParam mismatch")
                check(binding.get("merchantName") == alias.get("merchantName"),
                      f"semantic merchant binding {binding.get('id')} name mismatch")
                check(binding.get("sourceEvidence"),
                      f"semantic merchant binding {binding.get('id')} has no evidence")
    check(
        sum(binding.get("sellerIdentitySource") == "local_map_semantic_alias"
            for binding in merchant_bindings.get("bindings", []))
        == merchant_bindings.get("stats", {}).get("semanticAliasBindings"),
        "semantic merchant alias binding count does not match stats",
    )
    print(f"merchant shop bindings: {len(binding_ids)} bindings; named={sum(b.get('sellerStatus') == 'named' for b in merchant_bindings.get('bindings', []))}; unresolved={sum(b.get('sellerStatus') != 'named' for b in merchant_bindings.get('bindings', []))}")
    boss_endpoint_ids = [endpoint.get("id") for endpoint in boss_endpoints.get("endpoints", [])]
    check(None not in boss_endpoint_ids, "Boss reward endpoint missing id")
    check(len(boss_endpoint_ids) == len(set(boss_endpoint_ids)), "Boss reward endpoint ids not unique")
    graph_node_ids = {node["id"] for node in graph["nodes"]}
    for endpoint in boss_endpoints.get("endpoints", []):
        check(bool(endpoint.get("bossName")), f"Boss reward endpoint {endpoint.get('id')} missing boss name")
        check(endpoint.get("endpointStatus") in {"routeable_anchor", "coordinate_endpoint", "unbound"},
              f"Boss reward endpoint {endpoint.get('id')} has invalid status")
        binding = endpoint.get("topologyBinding") or {}
        for node_id in binding.get("routeNodeIds", []) + binding.get("semanticNodeIds", []):
            check(node_id in graph_node_ids,
                  f"Boss reward endpoint {endpoint.get('id')} references missing graph node {node_id}")
    boss_relation_endpoint_count = 0
    for rel in rels:
        if rel.get("method") not in {"boss_reward", "drops"}:
            continue
        for endpoint in rel.get("endpointInstances", []):
            boss_relation_endpoint_count += 1
            check(endpoint.get("kind") == "boss_reward_endpoint",
                  f"Boss relation {rel['id']} has non-Boss endpoint")
            binding = endpoint.get("topologyBinding") or {}
            check(binding.get("routeNodeIds") or binding.get("semanticNodeIds"),
                  f"Boss relation {rel['id']} endpoint has no topology binding")
    print(f"Boss reward endpoints: {len(boss_endpoint_ids)} endpoints; relation attachments={boss_relation_endpoint_count}")
    spawn_keys = set()
    spawn_count = 0
    for binding in spawns.get("bindings", []):
        npc_id = binding.get("npcParamId")
        check(npc_id is not None, "enemy spawn binding missing npcParamId")
        for instance in binding.get("instances", []):
            key = (instance.get("map"), instance.get("part"), instance.get("npcParamId"))
            check(key not in spawn_keys, f"duplicate enemy spawn instance {key}")
            spawn_keys.add(key)
            spawn_count += 1
            check(bool(instance.get("map")), f"enemy spawn {key} missing map")
            check(bool(instance.get("part")), f"enemy spawn {key} missing part")
            position = instance.get("position")
            check(
                isinstance(position, dict)
                and all(isinstance(position.get(axis), (int, float)) for axis in ("x", "y", "z")),
                  f"enemy spawn {key} missing XYZ position")
            check(str(instance.get("npcParamId")) == str(npc_id),
                  f"enemy spawn {key} disagrees with binding npcParamId")
    drop_endpoint_count = 0
    for rel in rels:
        if rel.get("method") != "drop":
            continue
        for row_id in rel.get("sourceNpcParamRows", []):
            check(rel.get("from") in entity_ids,
                  f"drop {rel['id']} source row {row_id} has unresolved entity")
        for endpoint in rel.get("endpointInstances", []):
            key = (endpoint.get("map"), endpoint.get("part"), endpoint.get("npcParamId"))
            check(key in spawn_keys, f"drop {rel['id']} endpoint {key} missing from spawn catalog")
            drop_endpoint_count += 1
    print(f"enemy spawn bindings: {len(spawns.get('bindings', []))} npc params, {spawn_count} instances; drop endpoints={drop_endpoint_count}")
    quest_endpoint_count = 0
    for rel in quest_relations:
        for endpoint in rel.get("endpointInstances", []):
            key = (endpoint.get("map"), endpoint.get("part"), endpoint.get("npcParamId"))
            check(key in spawn_keys,
                  f"quest reward {rel['id']} endpoint {key} missing from spawn catalog")
            quest_endpoint_count += 1
    print(f"quest NPC coordinate endpoints={quest_endpoint_count}")

    # ---- 3. location catalog ------------------------------------------------
    locs = locations["entities"]
    loc_ids = [l["id"] for l in locs]
    check(len(loc_ids) == len(set(loc_ids)), "location ids not unique")
    for l in locs:
        check(l["category"] in KNOWN_LOCATION_TYPES, f"location {l['id']} unknown type {l['category']}")
    print(f"location catalog: {len(locs)} locations")

    # ---- 3b. gap catalog -----------------------------------------------------
    gap_ids = [g["id"] for g in gaps["entities"]]
    check(len(gap_ids) == len(set(gap_ids)), "gap catalog ids not unique")
    for g in gaps["entities"]:
        check(g["category"] in KNOWN_LOCATION_TYPES, f"gap entity {g['id']} unknown type {g['category']}")
        check(g.get("verification"), f"gap entity {g['id']} missing verification")
        if g["category"] == "spirit_spring":
            check(g.get("verification") == "icon_heuristic", f"spring {g['id']} must be labelled heuristic")
    print(f"gap catalog: {len(gaps['entities'])} entities")

    # ---- 3c. reinforce catalog -------------------------------------------------
    for rel in reinforce["reinforcements"]:
        check(rel["from"] in entity_ids, f"reinforce {rel['id']} from {rel['from']} unresolved")
        check(rel["to"] in entity_ids, f"reinforce {rel['id']} to {rel['to']} unresolved")
        check(rel["verification"] == "game_mechanics_official", f"reinforce {rel['id']} bad verification")
        source = entity_by_id.get(rel["from"], {})
        target = entity_by_id.get(rel["to"], {})
        check(source.get("kind") in {"weapon", "item"},
              f"reinforce {rel['id']} source is not a weapon or spirit ash")
        check(source.get("kind") != "armor",
              f"reinforce {rel['id']} incorrectly upgrades armor")
        if source.get("kind") == "weapon":
            check(target.get("category") == "smithing_stone",
                  f"weapon reinforce {rel['id']} target is not a smithing stone")
        if source.get("category") == "spirit_ash":
            check(target.get("category") in {"grave_glovewort", "ghost_glovewort"},
                  f"spirit ash reinforce {rel['id']} target is not glovewort")
    set_members = set()
    for s in reinforce["armor_sets"]:
        check(s["id"] not in set_members, f"armor set duplicate {s['id']}")
        set_members.add(s["id"])
        check(len(s["members"]) >= 1, f"armor set {s['id']} has no members")
        for member in s["members"]:
            check(member["item"] in entity_ids, f"armor set {s['id']} member {member['item']} unresolved")
    print(f"reinforce catalog: {len(reinforce['reinforcements'])} relations, {len(reinforce['armor_sets'])} sets")

    # ---- 3d. pickup bindings ---------------------------------------------------
    for b in pickups["bindings"]:
        for item in b.get("items", []):
            canonical_item_id = registry.get("entityAliases", {}).get(
                item.get("item"), item.get("item")
            )
            check(canonical_item_id in entity_ids,
                  f"pickup lot {b['lot']} item {item.get('item')} unresolved")
        check(b.get("positions"), f"pickup lot {b['lot']} has no positions")
    print(f"pickup bindings: {len(pickups['bindings'])} lots")

    # ---- 4. graph integration ------------------------------------------------
    node_ids = {n["id"] for n in graph["nodes"]}
    for r in graph.get("relations", []):
        check(r["from"] in node_ids, f"graph relation {r['id']} from {r['from']} missing")
        check(r.get("to") in node_ids, f"graph relation {r['id']} to {r.get('to')} missing")
    kinds = Counter(n["kind"] for n in graph["nodes"])
    print(f"graph: {len(graph['nodes'])} nodes (kinds={dict(kinds)}), {len(graph['relations'])} relations")

    if problems:
        print(f"\nAUDIT FAIL: {len(problems)} problems")
        for p in problems[:20]:
            print("  -", p)
        return 1
    print("\nAUDIT OK: acquisition entity layer is structurally sound")
    return 0


if __name__ == "__main__":
    sys.exit(main())
