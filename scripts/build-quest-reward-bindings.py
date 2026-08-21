#!/usr/bin/env python3
"""Join external quest-step descriptions to local event-award evidence.

Only a conservative intersection is published as a quest reward:

1. the local EMEVD award event references at least one event flag used by the
   external NPC quest step; and
2. the awarded item name occurs in that quest step description.

The external source is a checklist/reference dataset, not a replacement for
the local game data.  Name-only or flag-only matches are intentionally omitted
from the published bindings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVENTS = ROOT / "data" / "v1" / "entities" / "event-reward-bindings.json"
DEFAULT_REGISTRY = ROOT / "data" / "v1" / "entities" / "entity-registry.json"
SOURCE_URL = "https://github.com/oisis/EldenRing-SaveForge/blob/v1.6.8/backend/db/data/quests.go"

NPC_ALIASES = {
    "white mask varre": "enemy_white_mask_varr",
    "latenna": "npc_latenna_the_albinauric",
    "iron fist alexander": "npc_alexander_warrior_jar",
    "tanith": "npc_tanith_volcano_manor_proprietress",
}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).replace("’", "'")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def decode_go_string(value: str) -> str:
    return bytes(value, "utf-8").decode("unicode_escape")


def parse_quest_source(path: Path) -> list[dict[str, Any]]:
    npc_pattern = re.compile(r'^\s*"((?:\\.|[^"\\])*)": \{$')
    step_pattern = re.compile(
        r'^\s*\{"((?:\\.|[^"\\])*)",\s*"((?:\\.|[^"\\])*)",\s*\[\]QuestFlag\{(.*)\},\s*$'
    )
    flag_pattern = re.compile(r"\{(\d+),\s*(\d+)\}")
    steps: list[dict[str, Any]] = []
    npc_name: str | None = None
    step_index = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        npc_match = npc_pattern.match(line)
        if npc_match:
            npc_name = decode_go_string(npc_match.group(1))
            step_index = 0
            continue
        step_match = step_pattern.match(line)
        if not step_match or npc_name is None:
            continue
        flags = [
            {"id": int(flag_id), "value": int(value)}
            for flag_id, value in flag_pattern.findall(step_match.group(3))
        ]
        steps.append({
            "npcName": npc_name,
            "stepIndex": step_index,
            "description": decode_go_string(step_match.group(1)),
            "location": decode_go_string(step_match.group(2)),
            "questFlags": flags,
        })
        step_index += 1
    return steps


def resolve_npc(npc_name: str, entities: list[dict[str, Any]]) -> tuple[str | None, str]:
    by_name = {
        normalize(entity.get("name", {}).get("en", "")): entity["id"]
        for entity in entities
        if entity.get("name", {}).get("en")
    }
    key = normalize(npc_name)
    if key in by_name:
        return by_name[key], "exact_entity_name"
    alias = NPC_ALIASES.get(npc_name.casefold())
    if alias and any(entity.get("id") == alias for entity in entities):
        return alias, "external_npc_alias"
    return None, "unresolved_npc_entity"


def build(source_path: Path, event_path: Path, registry_path: Path) -> dict[str, Any]:
    steps = parse_quest_source(source_path)
    event_payload = json.loads(event_path.read_text(encoding="utf-8"))
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    entities = registry.get("entities", [])
    bindings: list[dict[str, Any]] = []
    name_only = 0
    flag_only = 0
    strong_event_ids: set[str] = set()

    for event in event_payload.get("bindings", []):
        event_flags = set(int(flag_id) for flag_id in event.get("eventFlagIds", []))
        event_items = event.get("items", [])
        for step in steps:
            quest_flags = {int(flag["id"]) for flag in step["questFlags"]}
            overlap = sorted(event_flags & quest_flags)
            if not overlap:
                continue
            for item in event_items:
                if normalize(item.get("name", {}).get("en", "")) not in normalize(step["description"]):
                    flag_only += 1
                    continue
                npc_id, npc_resolution = resolve_npc(step["npcName"], entities)
                binding_id = (
                    f"quest-reward-{event['id']}-{item['item']}-"
                    f"{normalize(step['npcName'])}-{step['stepIndex']}"
                )
                bindings.append({
                    "id": binding_id,
                    "method": "quest_reward",
                    "from": npc_id,
                    "npcName": step["npcName"],
                    "npcEntityId": npc_id,
                    "npcResolution": npc_resolution,
                    "questStep": {
                        "npcName": step["npcName"],
                        "stepIndex": step["stepIndex"],
                        "description": step["description"],
                        "location": step["location"],
                        "questFlags": step["questFlags"],
                    },
                    "eventRewardBindingId": event["id"],
                    "matchedEventFlagIds": overlap,
                    "items": [{"item": item["item"], "name": item["name"], "num": item.get("num")}],
                    "evidence": [
                        "local EMEVD item-award binding",
                        "external NPC quest step names the same awarded item",
                        "local event flag and external quest flag intersect",
                    ],
                    "verification": "local_award_external_quest_name_and_flag_overlap",
                })
                strong_event_ids.add(event["id"])
        # Count item-name matches without a flag intersection separately.
        for step in steps:
            description = normalize(step["description"])
            if any(normalize(item.get("name", {}).get("en", "")) in description for item in event_items):
                quest_flags = {int(flag["id"]) for flag in step["questFlags"]}
                if not event_flags & quest_flags:
                    name_only += 1

    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    return {
        "schema": "elden-ring-quest-reward-bindings@1",
        "builtFrom": {
            "externalSource": str(source_path),
            "externalSourceUrl": SOURCE_URL,
            "externalSourceSha256": source_hash,
            "eventRewardBindings": str(event_path),
            "entityRegistry": str(registry_path),
            "policy": "publish only item-name plus event-flag intersections; omit weaker candidates",
        },
        "stats": {
            "questSteps": len(steps),
            "questCharacters": len({step["npcName"] for step in steps}),
            "eventBindings": len(event_payload.get("bindings", [])),
            "strongBindings": len(bindings),
            "matchedEventBindings": len(strong_event_ids),
            "nameOnlyCandidates": name_only,
            "flagOnlyCandidates": flag_only,
            "unresolvedNpcEntities": sum(binding["from"] is None for binding in bindings),
        },
        "bindings": bindings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quest-source", type=Path, required=True)
    parser.add_argument("--event-rewards", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "v1" / "entities" / "quest-reward-bindings.json")
    args = parser.parse_args()
    payload = build(args.quest_source, args.event_rewards, args.registry)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2))
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
