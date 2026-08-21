#!/usr/bin/env python3
"""Integrate the acquisition entity layer into the formal graph.

Adds to graph-v1.json:
  - location nodes (WorldMapPointParam instances, kind=location)
  - boss -> arena gate relations (from achievements formal_target_ids)
  - unique item nodes (remembrances / great runes / stone sword keys / bell
    bearings / map fragments) with dropped_by / located_in relations
  - location -> graph node relations where names match

Usage:
    python scripts/build-graph-integration.py \
        --graph data/v1/graph-v1.json \
        --registry data/v1/entities/entity-registry.json \
        --acquisitions data/v1/entities/acquisition-registry.json \
        --locations data/v1/entities/location-catalog.json \
        --out data/v1/graph-v1.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

UNIQUE_ITEM_CATEGORIES = {"remembrance", "great_rune", "stone_sword_key",
                          "bell_bearing", "map_fragment"}


def slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, default=ROOT / "data" / "v1" / "graph-v1.json")
    parser.add_argument("--registry", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "entity-registry.json")
    parser.add_argument("--acquisitions", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "acquisition-registry.json")
    parser.add_argument("--locations", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "location-catalog.json")
    parser.add_argument("--achievements", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "achievements.json")
    parser.add_argument("--gaps", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "gap-catalog.json")
    parser.add_argument("--objacts", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "msb-objact-catalog.json")
    parser.add_argument("--pickups", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "pickup-location-bindings.json")
    parser.add_argument("--grace-positions", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "local-grace-positions.json")
    parser.add_argument("--reinforce", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "reinforce-catalog.json")
    args = parser.parse_args()

    graph = load_json(args.graph)
    registry = load_json(args.registry)
    acquisitions = load_json(args.acquisitions)
    locations = load_json(args.locations)
    achievements = load_json(args.achievements)
    gaps = load_json(args.gaps) if args.gaps.exists() else {"entities": []}
    objacts = load_json(args.objacts) if args.objacts.exists() else {"objacts": []}
    pickups = load_json(args.pickups) if args.pickups.exists() else {"bindings": []}
    grace_positions = load_json(args.grace_positions) if args.grace_positions.exists() else {"records": []}
    reinforce = load_json(args.reinforce) if args.reinforce.exists() else {"reinforcements": [], "armor_sets": []}

    entities = {e["id"]: e for e in registry["entities"]}
    valid_entity_ids = set(entities)

    def canonical_label(entity_id: str) -> tuple[str, bool]:
        """Return the official localized label and whether Chinese exists."""
        entity = entities.get(entity_id, {})
        name = entity.get("name") or {}
        label = name.get("zh") or name.get("en")
        return (label or entity_id, bool(name.get("zh")))
    # Remove acquisition-generated semantic nodes that belonged to a prior
    # canonicalization pass.  Route nodes are independent and are preserved;
    # only an item node with no current canonical entity is stale data.
    graph["nodes"] = [
        node for node in graph["nodes"]
        if not (node.get("kind") == "item" and node.get("id") not in valid_entity_ids)
    ]
    node_ids = {n["id"] for n in graph["nodes"]}
    # Remove a previously published false relation if an older build treated
    # armor as upgradeable. Keeping this cleanup in the compiler makes the
    # correction reproducible instead of relying on a one-off file edit.
    generated_relation_types = {
        "pickup_at", "pickup_lot", "sold_in", "dropped_by", "boss_located_at",
        "reinforced_with", "set_member",
    }
    relations = [
        relation for relation in graph.get("relations", [])
        if relation.get("type") not in generated_relation_types
    ]
    existing_relations = {(r["id"]) for r in relations}
    added_nodes = 0
    added_relations = 0

    # ---- 1. location nodes -------------------------------------------------
    for loc in locations["entities"]:
        if loc["id"] in node_ids:
            continue
        pos = loc["properties"].get("position") or {}
        graph["nodes"].append({
            "id": loc["id"],
            "label": loc["name"]["zh"] or loc["name"]["en"],
            "kind": "location",
            "layer": None,
            "region": None,
            "floor": None,
            "worldEpoch": None,
            "x": None,
            "y": None,
            "coordinateType": "none",
            "verificationState": "local_param_verified",
            "sourceEvidence": [f"WorldMapPointParam row {loc['signifiers'][0]['rows'][0]}"],
            "description": f"{loc['category']}: {loc['name']['en']}",
            "entityType": loc["category"],
            "position": pos,
        })
        node_ids.add(loc["id"])
        added_nodes += 1

    # ---- 1b. gap-catalog nodes (spirit springs / caravans / puzzles) -------
    for ent in gaps.get("entities", []):
        if ent["id"] in node_ids:
            continue
        graph["nodes"].append({
            "id": ent["id"],
            "label": ent["name"]["zh"] or ent["name"]["en"],
            "kind": "location",
            "layer": None,
            "region": None,
            "floor": None,
            "worldEpoch": None,
            "x": None,
            "y": None,
            "coordinateType": "none",
            "verificationState": ent.get("verification", "local_msb_verified"),
            "sourceEvidence": [json.dumps(ent.get("signifiers", [{}])[0], ensure_ascii=False)[:120]],
            "description": f"{ent['category']}: {ent['name']['en']}",
            "entityType": ent["category"],
            **({"position": ent["properties"].get("position")} if ent.get("properties", {}).get("position") else {}),
        })
        node_ids.add(ent["id"])
        added_nodes += 1

    # ---- 1c. hidden passages / teleporters from MSB ObjAct ----------------
    import re as _re
    for obj in objacts.get("objacts", []):
        n = obj.get("name", "")
        cat = None
        if _re.search(r"隠し|hidden|secret", n, re.I):
            cat = "hidden_passage"
        elif _re.search(r"ワープ|warp|転送|テレポート|転移", n, re.I):
            cat = "teleporter"
        if cat is None:
            continue
        lid = f"location_{cat}_{slugify(n)[:40]}"
        if lid in node_ids:
            continue
        graph["nodes"].append({
            "id": lid,
            "label": f"{'暗门' if cat == 'hidden_passage' else '传送机关'}: {n[:40]}",
            "kind": "location",
            "layer": None,
            "region": None,
            "floor": None,
            "worldEpoch": None,
            "x": None,
            "y": None,
            "coordinateType": "none",
            "verificationState": "local_msb_verified",
            "sourceEvidence": [f"MSB ObjAct {n} in {obj.get('map')}"],
            "description": f"{cat}: {n}",
            "entityType": cat,
        })
        node_ids.add(lid)
        added_nodes += 1

    # ---- 2. unique item nodes ---------------------------------------------
    for ent in registry["entities"]:
        if ent["kind"] not in ("item", "weapon", "armor", "accessory", "ash_of_war"):
            continue
        if ent["category"] not in UNIQUE_ITEM_CATEGORIES:
            continue
        if ent["id"] in node_ids:
            continue
        graph["nodes"].append({
            "id": ent["id"],
            "label": ent["name"]["zh"] or ent["name"]["en"],
            "kind": "item",
            "layer": None,
            "region": None,
            "floor": None,
            "worldEpoch": None,
            "x": None,
            "y": None,
            "coordinateType": "none",
            "verificationState": "local_param_verified",
            "sourceEvidence": [f"EquipParamGoods row {ent['signifiers'][0]['rows'][0]}"],
            "description": f"{ent['category']}: {ent['name']['en']}",
            "entityType": ent["category"],
        })
        node_ids.add(ent["id"])
        added_nodes += 1

    # ---- 2b. boss entity nodes (achievement bosses) -------------------------
    achievement_boss_names = {
        a["name"].lower() for a in achievements["records"] if a.get("category") == "boss"
    }
    reward_boss_names = set()
    for rel in acquisitions["relations"]:
        if rel["method"] == "boss_reward":
            for it in rel["items"]:
                reward_boss_names.add(it["name"]["en"].lower())
    boss_names = achievement_boss_names | reward_boss_names
    for ent in registry["entities"]:
        if ent["kind"] not in ("enemy", "npc"):
            continue
        low = ent["name"]["en"].lower()
        if low not in boss_names and not any(
            low in b or b in low for b in achievement_boss_names):
            continue
        if ent["id"] in node_ids:
            continue
        graph["nodes"].append({
            "id": ent["id"],
            "label": ent["name"]["zh"] or ent["name"]["en"],
            "kind": "boss",
            "layer": None,
            "region": None,
            "floor": None,
            "worldEpoch": None,
            "x": None,
            "y": None,
            "coordinateType": "none",
            "verificationState": "official_names",
            "sourceEvidence": ["achievement list"],
            "description": f"boss: {ent['name']['en']}",
            "entityType": "boss",
        })
        node_ids.add(ent["id"])
        added_nodes += 1

    # ---- 3. boss -> arena gate relations (achievements) --------------------
    boss_entities = {e["id"]: e for e in registry["entities"] if e["kind"] in ("enemy", "npc")}
    boss_by_name = {e["name"]["en"].lower(): e for e in boss_entities.values()}
    for ach in achievements["records"]:
        if ach.get("category") != "boss":
            continue
        name = ach["name"]
        boss = boss_by_name.get(name.lower())
        if not boss:
            # try a suffix-tolerant match (e.g. "Ancestor Spirit" vs entries)
            for key, e in boss_by_name.items():
                if name.lower() in key or key in name.lower():
                    boss = e
                    break
        if not boss:
            continue
        for target in ach.get("formal_target_ids", []):
            if target not in node_ids:
                continue
            rid = f"{slugify(boss['name']['en'])}-located-at-{target}"
            if rid in existing_relations:
                continue
            relations.append({
                "id": rid,
                "from": boss["id"],
                "to": target,
                "type": "boss_located_at",
                "routeable": False,
                "sourceEvidence": [f"achievement {ach['canonical_id']}"],
            })
            existing_relations.add(rid)
            added_relations += 1

    # ---- 4. remembrance / great rune -> boss (dropped_by) -------------------
    for rel in acquisitions["relations"]:
        if rel["method"] != "boss_reward":
            continue
        item_id = rel["from"]
        for it in rel["items"]:
            rid = f"{item_id}-dropped-by-{it['item']}"
            if rid in existing_relations:
                continue
            relations.append({
                "id": rid,
                "from": item_id,
                "to": it["item"],
                "type": "dropped_by",
                "routeable": False,
                "sourceEvidence": rel.get("evidence", []),
            })
            existing_relations.add(rid)
            added_relations += 1

    # ---- 4b. pickup lots -> pickup-point nodes (MSB coordinates) ----------
    pickup_relations = 0
    for binding in pickups.get("bindings", []):
        for pos_rec in binding.get("positions", []):
            if not pos_rec.get("position"):
                continue
            pos = pos_rec["position"]
            map_key = pos_rec.get("map", "unknown")
            pid = f"pickup_{binding['lot']}_{map_key}"
            if pid not in node_ids:
                graph["nodes"].append({
                    "id": pid,
                    "label": f"拾取点 lot {binding['lot']}",
                    "kind": "location",
                    "layer": None,
                    "region": None,
                    "floor": None,
                    "worldEpoch": None,
                    "x": None,
                    "y": None,
                    "coordinateType": "msb",
                    "verificationState": "local_msb_verified",
                    "sourceEvidence": [f"MSB Treasure {pos_rec.get('part')} in {map_key}"],
                    "description": f"pickup point: lot {binding['lot']} in {map_key}",
                    "entityType": "pickup_point",
                    "position": pos,
                    "map": map_key,
                })
                node_ids.add(pid)
                added_nodes += 1
            for item in binding.get("items", []):
                item_id = item["item"]
                if item_id not in node_ids:
                    item_label, item_has_zh = canonical_label(item_id)
                    graph["nodes"].append({
                        "id": item_id,
                        "label": item_label,
                        "kind": "item",
                        "layer": None,
                        "region": None,
                        "floor": None,
                        "worldEpoch": None,
                        "x": None,
                        "y": None,
                        "coordinateType": "none",
                        "verificationState": "local_param_verified",
                        "sourceEvidence": [f"pickup lot {binding['lot']}"],
                        "description": f"item: {item['name'].get('en')}",
                        "entityType": "pickup_item",
                        "officialZhAvailable": item_has_zh,
                        "sourceVariantName": item.get("name"),
                    })
                    node_ids.add(item_id)
                    added_nodes += 1
                rid = f"{item_id}-pickup-{binding['lot']}-{map_key}"
                if rid in existing_relations:
                    continue
                relations.append({
                    "id": rid,
                    "from": item_id,
                    "to": pid,
                    "type": "pickup_at",
                    "routeable": False,
                    "sourceEvidence": [f"MSB Treasure lot {binding['lot']} in {map_key} "
                                       f"({pos_rec.get('part')})"],
                    "lot": {"param": "ItemLotParam_map", "rowId": binding["lot"]},
                })
                existing_relations.add(rid)
                pickup_relations += 1
    print(f"pickup relations: {pickup_relations}")

    # ---- 4c. reinforcement relations and armor-set nodes -------------------
    reinforce_relations = 0
    for rel in reinforce.get("reinforcements", []):
        from_id, to_id = rel["from"], rel["to"]
        if from_id not in node_ids:
            from_label, from_has_zh = canonical_label(from_id)
            graph["nodes"].append({
                "id": from_id, "label": from_label, "kind": "item",
                "layer": None, "region": None, "floor": None, "worldEpoch": None,
                "x": None, "y": None, "coordinateType": "none",
                "verificationState": "local_param_verified",
                "sourceEvidence": ["reinforce-catalog"],
                "description": "reinforced item", "entityType": "reinforceable",
                "officialZhAvailable": from_has_zh,
            })
            node_ids.add(from_id)
            added_nodes += 1
        if to_id not in node_ids:
            to_label, to_has_zh = canonical_label(to_id)
            graph["nodes"].append({
                "id": to_id, "label": to_label, "kind": "item",
                "layer": None, "region": None, "floor": None, "worldEpoch": None,
                "x": None, "y": None, "coordinateType": "none",
                "verificationState": "local_param_verified",
                "sourceEvidence": ["reinforce-catalog"],
                "description": "reinforcement material", "entityType": "smithing_stone",
                "officialZhAvailable": to_has_zh,
            })
            node_ids.add(to_id)
            added_nodes += 1
        rid = rel["id"]
        if rid in existing_relations:
            continue
        relations.append({
            "id": rid, "from": from_id, "to": to_id, "type": "reinforced_with",
            "routeable": False, "level": rel["level"], "maxLevel": rel["maxLevel"],
            "sourceEvidence": rel.get("evidence", []),
        })
        existing_relations.add(rid)
        reinforce_relations += 1

    for s in reinforce.get("armor_sets", []):
        sid = s["id"]
        if sid not in node_ids:
            graph["nodes"].append({
                "id": sid,
                "label": s["name"]["zh"] or s["name"]["en"],
                "kind": "armor_set",
                "layer": None, "region": None, "floor": None, "worldEpoch": None,
                "x": None, "y": None, "coordinateType": "none",
                "verificationState": "name_grouping_heuristic",
                "sourceEvidence": ["armor-set grouping by owner prefix"],
                "description": f"armor set: {s['name']['en']}",
                "entityType": "armor_set",
            })
            node_ids.add(sid)
            added_nodes += 1
        for member in s.get("members", []):
            mid = member["item"]
            if mid not in node_ids:
                continue
            rid = f"{sid}-member-{mid}"
            if rid in existing_relations:
                continue
            relations.append({
                "id": rid, "from": sid, "to": mid, "type": "set_member",
                "routeable": False,
                "sourceEvidence": ["armor-set grouping"],
            })
            existing_relations.add(rid)
            reinforce_relations += 1
    print(f"reinforce relations: {reinforce_relations}")

    # ---- 5. unique items located in / at shops -----------------------------
    for rel in acquisitions["relations"]:
        if rel["method"] not in ("pickup", "purchase"):
            continue
        for it in rel["items"]:
            item_id = it["item"]
            if item_id not in node_ids:
                continue
            if rel["method"] == "pickup":
                rid = f"{item_id}-pickup-lot{rel['lot']['rowId']}"
                rtype = "pickup_lot"
            else:
                rid = f"{item_id}-sold-shop{rel['id']}"
                rtype = "sold_in"
            if rid in existing_relations:
                continue
            target = f"shop-{rel['id'].split('-')[-1]}" if rel["method"] == "purchase" else None
            if target is not None and target not in node_ids:
                continue
            relations.append({
                "id": rid,
                "from": item_id,
                "to": target,
                "type": rtype,
                "routeable": False,
                "sourceEvidence": rel.get("evidence", []),
                **({"lot": rel["lot"]} if "lot" in rel else {}),
            })
            existing_relations.add(rid)
            added_relations += 1

    node_ids_final = {n["id"] for n in graph["nodes"]}
    relations = [r for r in relations if r.get("to") in node_ids_final and r["from"] in node_ids_final]
    graph["relations"] = relations
    graph["coverage"] = {
        **graph.get("coverage", {}),
        "acquisitionEntities": len(registry["entities"]),
        "acquisitionRelations": len(relations),
        "locationInstances": len(locations["entities"]),
    }
    graph["meta"] = {
        **graph.get("meta", {}),
        "version": graph.get("meta", {}).get("version", "").removesuffix("-acquisition") + "-acquisition",
        "acquisitionLayer": "entity-registry + acquisition-registry (see data/v1/entities/)",
    }

    args.graph.write_text(json.dumps(graph, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"added nodes: {added_nodes}, relations: {added_relations}")
    print(f"graph now: {len(graph['nodes'])} nodes, {len(graph['relations'])} relations")
    print(f"wrote {args.graph}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
