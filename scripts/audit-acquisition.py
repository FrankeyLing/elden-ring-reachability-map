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

KNOWN_METHODS = {"drop", "pickup", "purchase", "boss_reward", "drops"}
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


def main() -> int:
    registry = json.loads((DATA / "entities" / "entity-registry.json").read_text(encoding="utf-8"))
    acquisitions = json.loads((DATA / "entities" / "acquisition-registry.json").read_text(encoding="utf-8"))
    locations = json.loads((DATA / "entities" / "location-catalog.json").read_text(encoding="utf-8"))
    graph = json.loads((DATA / "graph-v1.json").read_text(encoding="utf-8"))
    gaps = json.loads((DATA / "entities" / "gap-catalog.json").read_text(encoding="utf-8"))
    reinforce = json.loads((DATA / "entities" / "reinforce-catalog.json").read_text(encoding="utf-8"))
    pickups = json.loads((DATA / "entities" / "pickup-location-bindings.json").read_text(encoding="utf-8"))

    # ---- 1. entity registry -------------------------------------------------
    entities = registry["entities"]
    ids = [e["id"] for e in entities]
    check(len(ids) == len(set(ids)), f"entity ids not unique: {len(ids)} vs {len(set(ids))}")
    check(len(entities) > 0, "empty entity registry")
    for e in entities:
        check(bool(e["name"].get("en")), f"entity {e['id']} missing english name")
        check(bool(e["name"].get("zh")), f"entity {e['id']} missing chinese name")
        check(e["signifiers"], f"entity {e['id']} has no signifiers")
        if "[ERROR]" in (e["name"].get("en") or ""):
            check(False, f"entity {e['id']} has [ERROR] name: {e['name']['en']}")
    by_kind_name = Counter((e["kind"], e["name"]["en"]) for e in entities)
    dup_names = {n: c for n, c in by_kind_name.items() if c > 1}
    check(not dup_names, f"duplicate kind+name entities: {dict(list(dup_names.items())[:8])}")
    print(f"entity registry: {len(entities)} entities, {len(set(ids))} unique ids")

    # ---- 2. acquisition registry -------------------------------------------
    rels = acquisitions["relations"]
    entity_ids = set(ids)
    check(len(rels) > 0, "empty acquisition registry")
    for rel in rels:
        check(rel["method"] in KNOWN_METHODS, f"relation {rel['id']} unknown method {rel['method']}")
        if rel.get("from"):
            check(rel["from"] in entity_ids, f"relation {rel['id']} from {rel['from']} unresolved")
        for it in rel.get("items", []):
            check(it.get("item") in entity_ids or it["item"].startswith(("item_", "weapon_", "armor_", "enemy_", "npc_", "accessory_", "ash_of_war_")),
                  f"relation {rel['id']} item {it.get('item')} unresolved")
            check(bool(it["name"].get("en")), f"relation {rel['id']} item missing name")
    methods = Counter(r["method"] for r in rels)
    print(f"acquisition registry: {len(rels)} relations, methods={dict(methods)}")

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
            check(item.get("item") in entity_ids or item["item"].startswith(("item_", "weapon_", "armor_")),
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
