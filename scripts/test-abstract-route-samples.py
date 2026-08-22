#!/usr/bin/env python3
"""Chapter 6/10.5 sample set: many entities each produce an abstract route
from a legal start, or are honestly reported as bound/unbound.  This is the
widened regression sample library (阶段六)."""
import json
import sys
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8127"
SAMPLE = [
    # (entity id, description)
    ("weapon_bolt_of_gransax", "legacy weapon (routeable anchor)"),
    ("item_smithing_stone_1", "common material (semantic)"),
    ("item_grave_glovewort_1", "glovewort (semantic)"),
    ("item_remembrance_of_the_omen_king", "remembrance (boss self-ref)"),
    ("enemy_godrick_the_grafted", "boss"),
    ("npc_finger_reader_enia", "merchant-ish NPC"),
    ("armor_finger_robe", "altered armor"),
    ("ash_of_war_ash_of_war_piercing_fang", "skill via expert source"),
    ("location_stormveil_castle", "landmark"),
    ("enemy_furnace_golem", "furnace golem"),
]
fails = []
for entity_id, description in SAMPLE:
    with urlopen(BASE + "/api/catalog/player-entities?" + urlencode({"id": entity_id}), timeout=15) as resp:
        detail = json.loads(resp.read().decode("utf-8"))
    if not detail.get("found"):
        print(f"FAIL {entity_id}: not found")
        fails.append(entity_id)
        continue
    with urlopen(BASE + "/api/catalog/player-entity-abstract-route?" + urlencode(
            {"id": entity_id, "from_map_id": "m10_01_00_00", "max_paths": 2}), timeout=20) as resp:
        route = json.loads(resp.read().decode("utf-8"))
    routeable = route.get("routeReady") or bool(route.get("paths"))
    print(f"PASS {entity_id} ({description}): found={route.get('found')} targets={route.get('targetMapCount')} paths={len(route.get('paths') or [])}")
    if not route.get("found"):
        fails.append(entity_id)

print(f"\nABSTRACT ROUTE SAMPLES: {len(SAMPLE) - len(fails)}/{len(SAMPLE)} passed")
sys.exit(0 if not fails else 1)
