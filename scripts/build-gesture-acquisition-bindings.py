#!/usr/bin/env python3
"""Build independently verifiable gesture-acquisition facts from local data.

The output deliberately records facts, not inferred routes.  Each starting
loadout, EMEVD award instruction, and Talk ESD AcquireGesture call remains an
independent binding.  A missing or malformed source record therefore cannot
invalidate unrelated gesture acquisitions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT.parent.parent / "local-snapshots" / "elden-ring-20260818"
DEFAULT_PARAM_DIR = SNAPSHOT / "extracted" / "param-json"
DEFAULT_EMEVD_DIR = SNAPSHOT / "extracted" / "parsed-emevd" / "files"
DEFAULT_TALK_DIR = SNAPSHOT / "extracted" / "talkesd-py-by-map"
DEFAULT_REGISTRY = ROOT / "data" / "v1" / "entities" / "entity-registry.json"
DEFAULT_OUTPUT = ROOT / "data" / "v1" / "entities" / "gesture-acquisition-bindings.json"

AWARD_GESTURE_OPCODE = (2003, 71)
INITIALIZE_EVENT_OPCODES = {(2000, 0), (2000, 6)}
ACQUIRE_GESTURE_RE = re.compile(r"\bAcquireGesture\((\d+)\)")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_rows(param_dir: Path, table: str) -> dict[int, dict[str, Any]]:
    payload = json.loads((param_dir / f"{table}.json").read_text(encoding="utf-8"))
    return {int(row["id"]): row.get("cells", {}) for row in payload["rows"]}


def gesture_entities(registry_path: Path) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    by_row: dict[int, dict[str, Any]] = {}
    entities = []
    for entity in payload.get("entities", []):
        if entity.get("category") != "gesture":
            continue
        entities.append(entity)
        for signifier in entity.get("signifiers", []):
            if signifier.get("param") != "GestureParam":
                continue
            for row_id in signifier.get("rows", []):
                row_id = int(row_id)
                if row_id in by_row:
                    raise ValueError(f"GestureParam row {row_id} resolves to multiple entities")
                by_row[row_id] = entity
    return by_row, entities


def item_for(row_id: int, entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "item": entity["id"],
        "name": entity["name"],
        "sourceParam": "GestureParam",
        "sourceParamId": row_id,
    }


def initial_loadout_bindings(
    param_dir: Path,
    by_row: dict[int, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    menu_rows = load_rows(param_dir, "BaseChrSelectMenuParam")
    init_rows = load_rows(param_dir, "CharaInitParam")
    class_rows = []
    gesture_sources: dict[int, list[dict[str, int]]] = defaultdict(list)
    for menu_id, cells in sorted(menu_rows.items()):
        origin_id = cells.get("originChrInitParam")
        loadout_id = cells.get("chrInitParam")
        # Rows 2000-2009 are the ten selectable Elden Ring origins.  This is
        # verified structurally by their references to CharaInitParam 3000+
        # origin rows and parallel 3100+ concrete loadout rows.
        if not (
            isinstance(origin_id, int)
            and 3000 <= origin_id <= 3009
            and isinstance(loadout_id, int)
            and loadout_id in init_rows
            and origin_id in init_rows
        ):
            continue
        origin_gestures = [
            int(init_rows[origin_id].get(f"gestureId{index}", -1))
            for index in range(7)
        ]
        loadout_gestures = [
            int(init_rows[loadout_id].get(f"gestureId{index}", -1))
            for index in range(7)
        ]
        if origin_gestures != loadout_gestures:
            raise ValueError(
                f"starting class {menu_id} origin/loadout gesture mismatch: "
                f"{origin_gestures} != {loadout_gestures}"
            )
        class_row = {
            "baseChrSelectMenuRow": menu_id,
            "originCharaInitRow": origin_id,
            "loadoutCharaInitRow": loadout_id,
        }
        class_rows.append(class_row)
        for gesture_id in origin_gestures:
            if gesture_id >= 0:
                gesture_sources[gesture_id].append(class_row)

    bindings = []
    unresolved = []
    for gesture_id, sources in sorted(gesture_sources.items()):
        entity = by_row.get(gesture_id)
        if entity is None:
            unresolved.append({"source": "initial_loadout", "gestureParamRow": gesture_id})
            continue
        bindings.append({
            "id": f"gesture-initial-loadout-{gesture_id}",
            "method": "initial_loadout",
            "sourceType": "starting_class_loadout",
            "gestureParamRow": gesture_id,
            "items": [item_for(gesture_id, entity)],
            "startingClasses": sources,
            "evidence": [
                "local BaseChrSelectMenuParam selectable-origin references",
                "local CharaInitParam origin and concrete loadout gesture fields agree",
            ],
            "verification": "local_starting_class_param_verified",
        })
    return bindings, unresolved


def parse_event_files(emevd_dir: Path) -> dict[str, dict[str, Any]]:
    files = {}
    for path in sorted(emevd_dir.glob("*.json")):
        if path.name == "batch-manifest.json":
            continue
        files[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return files


def call_sites(
    files: dict[str, dict[str, Any]],
    template_file: str,
    event_id: int,
) -> list[dict[str, Any]]:
    # Initialize Common Event can call common_func from every map.  Ordinary
    # Initialize Event calls are file-local; accepting a same-number event in
    # another map would be a false identity join.
    scopes = files.items() if template_file == "common_func" else [(template_file, files[template_file])]
    expected_opcode = (2000, 6) if template_file == "common_func" else (2000, 0)
    calls = []
    for caller_file, payload in scopes:
        for caller_event in payload.get("events", []):
            for instruction in caller_event.get("instructions", []):
                if (instruction.get("bank"), instruction.get("id")) != expected_opcode:
                    continue
                try:
                    raw = bytes.fromhex(str(instruction.get("args_hex") or ""))
                except ValueError:
                    continue
                if len(raw) < 8 or struct.unpack_from("<I", raw, 4)[0] != event_id:
                    continue
                calls.append({
                    "callerFile": caller_file,
                    "callerEventId": int(caller_event["id"]),
                    "callerInstructionIndex": int(instruction["index"]),
                    "parameterBuffer": raw[8:],
                })
    return calls


def event_bindings(
    emevd_dir: Path,
    by_row: dict[int, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    files = parse_event_files(emevd_dir)
    bindings = []
    unresolved = []
    for source_file, payload in sorted(files.items()):
        for event in payload.get("events", []):
            event_id = int(event["id"])
            mappings_by_instruction: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for mapping in event.get("parameters", []):
                mappings_by_instruction[int(mapping.get("instruction_index", -1))].append(mapping)
            for instruction in event.get("instructions", []):
                if (instruction.get("bank"), instruction.get("id")) != AWARD_GESTURE_OPCODE:
                    continue
                instruction_index = int(instruction["index"])
                raw = bytes.fromhex(str(instruction.get("args_hex") or ""))
                if len(raw) < 4:
                    unresolved.append({
                        "source": "emevd",
                        "file": source_file,
                        "eventId": event_id,
                        "instructionIndex": instruction_index,
                        "reason": "truncated_award_gesture_argument",
                    })
                    continue
                mappings = [
                    mapping for mapping in mappings_by_instruction.get(instruction_index, [])
                    if int(mapping.get("target_start_byte", -1)) == 0
                    and int(mapping.get("byte_count", 0)) == 4
                ]
                resolved_sources = []
                if not mappings:
                    resolved_sources.append({
                        "gestureParamRow": struct.unpack_from("<i", raw, 0)[0],
                        "map": source_file,
                        "eventId": event_id,
                        "instructionIndex": instruction_index,
                        "resolution": "literal_instruction_argument",
                    })
                else:
                    calls = call_sites(files, source_file, event_id)
                    for mapping in mappings:
                        offset = int(mapping["source_start_byte"])
                        for call in calls:
                            buffer = call["parameterBuffer"]
                            if offset < 0 or offset + 4 > len(buffer):
                                continue
                            resolved_sources.append({
                                "gestureParamRow": struct.unpack_from("<i", buffer, offset)[0],
                                "map": call["callerFile"],
                                "eventId": call["callerEventId"],
                                "instructionIndex": call["callerInstructionIndex"],
                                "templateFile": source_file,
                                "templateEventId": event_id,
                                "templateInstructionIndex": instruction_index,
                                "parameterSourceByte": offset,
                                "resolution": "initialize_event_parameter_substitution",
                            })
                    if not resolved_sources:
                        unresolved.append({
                            "source": "emevd",
                            "file": source_file,
                            "eventId": event_id,
                            "instructionIndex": instruction_index,
                            "reason": "parameterized_template_has_no_verified_call_site",
                        })
                for source in resolved_sources:
                    gesture_id = int(source["gestureParamRow"])
                    entity = by_row.get(gesture_id)
                    if entity is None:
                        unresolved.append({**source, "source": "emevd", "reason": "unknown_gesture_param_row"})
                        continue
                    relation_id = (
                        f"gesture-emevd-{source['map']}-{source['eventId']}-"
                        f"{source['instructionIndex']}-{gesture_id}"
                    )
                    bindings.append({
                        "id": relation_id,
                        "method": "gesture_unlock",
                        "sourceType": "emevd_award_gesture",
                        "gestureParamRow": gesture_id,
                        "items": [item_for(gesture_id, entity)],
                        "source": source,
                        "evidence": [
                            "local parsed EMEVD Award Gesture instruction",
                            "literal argument or exact Initialize Event parameter substitution",
                            f"local GestureParam row {gesture_id}",
                        ],
                        "verification": "local_emevd_gesture_award_verified",
                    })
    deduped = {binding["id"]: binding for binding in bindings}
    return [deduped[key] for key in sorted(deduped)], unresolved


def talk_bindings(
    talk_dir: Path,
    by_row: dict[int, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    occurrences: dict[tuple[str, str, int], list[int]] = defaultdict(list)
    unresolved = []
    for path in sorted(talk_dir.glob("m*/*.py")):
        map_id = path.parent.name
        talk_script = path.stem
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in ACQUIRE_GESTURE_RE.finditer(line):
                gesture_id = int(match.group(1))
                if gesture_id not in by_row:
                    unresolved.append({
                        "source": "talk_esd",
                        "map": map_id,
                        "talkScript": talk_script,
                        "line": line_number,
                        "gestureParamRow": gesture_id,
                        "reason": "unknown_gesture_param_row",
                    })
                    continue
                occurrences[(map_id, talk_script, gesture_id)].append(line_number)
    bindings = []
    for (map_id, talk_script, gesture_id), lines in sorted(occurrences.items()):
        entity = by_row[gesture_id]
        bindings.append({
            "id": f"gesture-talk-{map_id}-{talk_script}-{gesture_id}",
            "method": "gesture_unlock",
            "sourceType": "talk_esd_acquire_gesture",
            "gestureParamRow": gesture_id,
            "items": [item_for(gesture_id, entity)],
            "source": {
                "map": map_id,
                "talkScript": talk_script,
                "lineNumbers": sorted(set(lines)),
            },
            "evidence": [
                "local Talk ESD AcquireGesture call",
                f"decompiled from copied game talk binder for {map_id}",
                f"local GestureParam row {gesture_id}",
            ],
            "verification": "local_talk_esd_gesture_acquisition_verified",
        })
    return bindings, unresolved


def build(param_dir: Path, emevd_dir: Path, talk_dir: Path, registry_path: Path) -> dict[str, Any]:
    by_row, entities = gesture_entities(registry_path)
    source_gesture_rows = load_rows(param_dir, "GestureParam")
    initial, initial_unresolved = initial_loadout_bindings(param_dir, by_row)
    events, event_unresolved = event_bindings(emevd_dir, by_row)
    talks, talk_unresolved = talk_bindings(talk_dir, by_row)
    bindings = initial + events + talks
    bound_rows = {int(binding["gestureParamRow"]) for binding in bindings}
    all_rows = set(by_row)
    return {
        "schema": "elden-ring-gesture-acquisition-bindings@1",
        "builtFrom": {
            "paramDir": str(param_dir.resolve()),
            "parsedEmevd": str(emevd_dir.resolve()),
            "decompiledTalkEsdByMap": str(talk_dir.resolve()),
            "entityRegistry": str(registry_path.resolve()),
            "entityRegistrySha256": sha256(registry_path),
            "policy": "independent local facts only; no route or NPC identity is inferred",
        },
        "stats": {
            "gestureEntityCount": len(entities),
            "gestureParamRowCount": len(source_gesture_rows),
            "eligibleGestureParamRowCount": len(all_rows),
            "initialLoadoutBindingCount": len(initial),
            "emevdBindingCount": len(events),
            "talkEsdBindingCount": len(talks),
            "bindingCount": len(bindings),
            "locallyBoundGestureRowCount": len(bound_rows),
            "locallyUnboundGestureRowCount": len(all_rows - bound_rows),
        },
        "bindings": bindings,
        "unresolvedSources": initial_unresolved + event_unresolved + talk_unresolved,
        "locallyUnboundGestureRows": [
            {
                "gestureParamRow": row_id,
                "item": by_row[row_id]["id"],
                "name": by_row[row_id]["name"],
                "status": "missing_local_acquisition_fact",
            }
            for row_id in sorted(all_rows - bound_rows)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--param-dir", type=Path, default=DEFAULT_PARAM_DIR)
    parser.add_argument("--parsed-emevd", type=Path, default=DEFAULT_EMEVD_DIR)
    parser.add_argument("--talk-esd", type=Path, default=DEFAULT_TALK_DIR)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build(args.param_dir, args.parsed_emevd, args.talk_esd, args.registry)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2))
    print(f"unresolved_sources={len(payload['unresolvedSources'])}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
