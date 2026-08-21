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
    "d hunter of the dead": "npc_d_hunter_of_the_dead",
    "diallos": "npc_knight_diallos",
    "ensha": "enemy_ensha_of_the_royal_remains",
    "fia": "npc_fia_deathbed_companion",
    "finger reader cone": "npc_finger_reader_crone",
    "gideon ofnir": "enemy_sir_gideon_ofnir_the_all_knowing",
    "gowry": "npc_sage_gowry",
    "gurranq": "npc_gurranq_beast_clergyman",
    "hyetta": "npc_finger_maiden_hyetta",
    "iji": "npc_war_counselor_iji",
    "irina": "npc_irina_of_morne",
    "jerren": "enemy_witch_hunter_jerren",
    "kale": "npc_merchant_kal",
    "kenneth haight": "npc_kenneth_haight_limgrave_heir",
    "miriel": "npc_miriel_pastor_of_vows",
    "nepheli loux": "npc_nepheli_loux_warrior",
    "pidia": "enemy_pidia_carian_servant",
    "rya": "enemy_rya_the_scout",
    "seluvis": "npc_preceptor_seluvis",
    "thops": "npc_sorcerer_thops",
}

REWARD_MARKERS = (
    "receiv",
    "reward",
    "obtain",
    "obtained",
    "gives you",
    "given",
)


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


def quest_named_reward_candidates(
    step: dict[str, Any], entities: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return exact quoted item names used in a reward-like quest step.

    The external checklist contains both prerequisites and rewards in prose.
    Requiring an exact quoted official name plus a reward marker avoids turning
    every item mentioned in a dialogue description into an acquisition fact.
    Goods are preferred over the parallel Magic projection; the acquisition
    builder will project the same fact to the corresponding spell entity.
    """
    description = step["description"]
    if not any(marker in description.casefold() for marker in REWARD_MARKERS):
        return []
    by_name: dict[str, list[dict[str, Any]]] = {}
    for entity in entities:
        if entity.get("kind") not in {"weapon", "armor", "accessory", "item", "spell"}:
            continue
        name = entity.get("name", {}).get("en")
        if name:
            by_name.setdefault(normalize(name), []).append(entity)

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for quoted in re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', description):
        matches = by_name.get(normalize(quoted), [])
        if not matches:
            continue
        non_spells = [entity for entity in matches if entity.get("kind") != "spell"]
        preferred = [entity for entity in non_spells if entity.get("kind") == "item"]
        if preferred:
            matches = preferred
        elif non_spells:
            matches = non_spells
        for entity in matches:
            if entity["id"] in seen:
                continue
            seen.add(entity["id"])
            candidates.append(entity)
    return candidates


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

    local_binding_count = len(bindings)

    # Publish independently useful external quest evidence when the checklist
    # explicitly names a reward but no local AwardItemLot/event-flag join was
    # proven.  This is intentionally weaker than a local award binding and is
    # kept as a separate status rather than silently upgrading the evidence.
    strong_keys = {
        (
            binding.get("npcName"),
            binding.get("questStep", {}).get("stepIndex"),
            item.get("item"),
        )
        for binding in bindings
        for item in binding.get("items", [])
    }
    reference_bindings = 0
    for step in steps:
        npc_id, npc_resolution = resolve_npc(step["npcName"], entities)
        for entity in quest_named_reward_candidates(step, entities):
            key = (step["npcName"], step["stepIndex"], entity["id"])
            if key in strong_keys:
                continue
            binding_id = (
                f"quest-reference-{normalize(step['npcName'])}-"
                f"{step['stepIndex']}-{entity['id']}"
            )
            bindings.append({
                "id": binding_id,
                "method": "quest_reward",
                "from": npc_id,
                "npcName": step["npcName"],
                "npcEntityId": npc_id,
                "npcResolution": npc_resolution,
                "sourceStatus": "external_reference_only",
                "questStep": {
                    "npcName": step["npcName"],
                    "stepIndex": step["stepIndex"],
                    "description": step["description"],
                    "location": step["location"],
                    "questFlags": step["questFlags"],
                },
                "items": [{
                    "item": entity["id"],
                    "name": entity["name"],
                    "num": 1,
                    "quantityStatus": "not_stated_in_external_step",
                }],
                "evidence": [
                    "external NPC quest step explicitly names the reward",
                    "external quest description contains a reward marker",
                    "no local EMEVD award and event-flag intersection was proven",
                ],
                "verification": "external_quest_named_reward_reference",
            })
            reference_bindings += 1

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
            "strongBindings": local_binding_count,
            "totalBindings": len(bindings),
            "matchedEventBindings": len(strong_event_ids),
            "nameOnlyCandidates": name_only,
            "flagOnlyCandidates": flag_only,
            "referenceBindings": reference_bindings,
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
