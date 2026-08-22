#!/usr/bin/env python3
"""Build independent tutorial/info unlock facts from copied game data.

Player-facing ``About ...`` records are EquipParamGoods rows of goodsType 12.
They correspond to TutorialParam rows through the official TutorialTitle text.
Only literal Show Tutorial Popup calls or exactly substituted Initialize Event
parameters are emitted.  No coordinate, route, or trigger-object identity is
inferred from the event's map scope.
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
DEFAULT_REGISTRY = ROOT / "data" / "v1" / "entities" / "entity-registry.json"
DEFAULT_FMG = ROOT / "data" / "v1" / "entities" / "official-fmg-bilingual-index.json"
DEFAULT_OUTPUT = ROOT / "data" / "v1" / "entities" / "tutorial-unlock-bindings.json"

SHOW_TUTORIAL_POPUP_OPCODE = (2007, 15)

# Three official GoodsName/TutorialTitle pairs use harmless wording or article
# differences.  Keeping these explicit avoids fuzzy identity joins.
TITLE_ALIASES = {
    "requesting help from hunters": "requesting aid from a hunter",
    "the scadutree blessing": "scadutree blessing",
    "the revered spirit ash blessing": "revered spirit ash blessing",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def load_rows(param_dir: Path, table: str) -> list[dict[str, Any]]:
    payload = json.loads((param_dir / f"{table}.json").read_text(encoding="utf-8"))
    return payload["rows"]


def tutorial_titles(fmg_path: Path) -> dict[int, dict[str, str]]:
    payload = json.loads(fmg_path.read_text(encoding="utf-8"))
    titles: dict[int, dict[str, str]] = defaultdict(dict)
    for record in payload.get("records", []):
        if not Path(record.get("fmg", "")).name.startswith("TutorialTitle"):
            continue
        text = str(record.get("text") or "").strip()
        if text:
            titles[int(record["id"])][record["language"]] = text
    return dict(titles)


def tutorial_entities(
    registry_path: Path,
    param_dir: Path,
    fmg_path: Path,
) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    goods = {int(row["id"]): row["cells"] for row in load_rows(param_dir, "EquipParamGoods")}
    titles = tutorial_titles(fmg_path)
    title_id_by_name: dict[str, int] = {}
    for title_id, names in titles.items():
        english = names.get("engus")
        if english:
            key = normalize(english)
            if key in title_id_by_name and title_id_by_name[key] != title_id:
                raise ValueError(f"duplicate official tutorial title: {english}")
            title_id_by_name[key] = title_id

    entities_by_title_id: dict[int, dict[str, Any]] = {}
    entities = []
    unresolved = []
    for entity in registry.get("entities", []):
        english = str((entity.get("name") or {}).get("en") or "")
        goods_rows = [
            int(row_id)
            for signifier in entity.get("signifiers", [])
            if signifier.get("param") == "EquipParamGoods"
            for row_id in signifier.get("rows", [])
        ]
        if not english.startswith("About ") or not goods_rows:
            continue
        if not all(goods.get(row_id, {}).get("goodsType") == 12 for row_id in goods_rows):
            continue
        key = normalize(english.removeprefix("About "))
        key = TITLE_ALIASES.get(key, key)
        title_id = title_id_by_name.get(key)
        if title_id is None:
            unresolved.append({
                "entity": entity["id"],
                "name": entity["name"],
                "reason": "no_exact_official_tutorial_title",
            })
            continue
        if title_id in entities_by_title_id:
            raise ValueError(f"TutorialTitle {title_id} resolves to multiple entities")
        entities_by_title_id[title_id] = entity
        entities.append(entity)

    by_tutorial_row: dict[int, dict[str, Any]] = {}
    for row in load_rows(param_dir, "TutorialParam"):
        title_id = int(row["cells"].get("textId", -1))
        entity = entities_by_title_id.get(title_id)
        if entity is not None:
            by_tutorial_row[int(row["id"])] = {
                "entity": entity,
                "tutorialTitleId": title_id,
                "unlockEventFlagId": int(row["cells"].get("unlockEventFlagId", 0)),
                "officialTitle": titles[title_id],
            }
    return by_tutorial_row, entities, unresolved


def parse_event_files(emevd_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(emevd_dir.glob("*.json"))
        if path.name != "batch-manifest.json"
    }


def call_sites(
    files: dict[str, dict[str, Any]], template_file: str, event_id: int
) -> list[dict[str, Any]]:
    scopes = files.items() if template_file == "common_func" else [(template_file, files[template_file])]
    expected_opcode = (2000, 6) if template_file == "common_func" else (2000, 0)
    calls = []
    for caller_file, payload in scopes:
        for caller_event in payload.get("events", []):
            for instruction in caller_event.get("instructions", []):
                if (instruction.get("bank"), instruction.get("id")) != expected_opcode:
                    continue
                raw = bytes.fromhex(str(instruction.get("args_hex") or ""))
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
    emevd_dir: Path, by_tutorial_row: dict[int, dict[str, Any]]
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
                if (instruction.get("bank"), instruction.get("id")) != SHOW_TUTORIAL_POPUP_OPCODE:
                    continue
                instruction_index = int(instruction["index"])
                raw = bytes.fromhex(str(instruction.get("args_hex") or ""))
                if len(raw) < 4:
                    unresolved.append({
                        "source": "emevd", "file": source_file, "eventId": event_id,
                        "instructionIndex": instruction_index,
                        "reason": "truncated_tutorial_argument",
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
                        "tutorialParamRow": struct.unpack_from("<i", raw, 0)[0],
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
                                "tutorialParamRow": struct.unpack_from("<i", buffer, offset)[0],
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
                            "source": "emevd", "file": source_file, "eventId": event_id,
                            "instructionIndex": instruction_index,
                            "reason": "parameterized_template_has_no_verified_call_site",
                        })
                for source in resolved_sources:
                    row_id = int(source["tutorialParamRow"])
                    target = by_tutorial_row.get(row_id)
                    if target is None:
                        continue  # A menu-only tutorial, not an About-info entity.
                    entity = target["entity"]
                    binding_id = (
                        f"tutorial-emevd-{source['map']}-{source['eventId']}-"
                        f"{source['instructionIndex']}-{row_id}"
                    )
                    bindings.append({
                        "id": binding_id,
                        "method": "tutorial_unlock",
                        "sourceType": "emevd_show_tutorial_popup",
                        "tutorialParamRow": row_id,
                        "tutorialTitleId": target["tutorialTitleId"],
                        "unlockEventFlagId": target["unlockEventFlagId"],
                        "items": [{
                            "item": entity["id"],
                            "name": entity["name"],
                            "sourceParam": "TutorialParam",
                            "sourceParamId": row_id,
                        }],
                        "source": source,
                        "evidence": [
                            "local parsed EMEVD Show Tutorial Popup instruction",
                            "literal argument or exact Initialize Event parameter substitution",
                            f"local TutorialParam row {row_id}",
                            f"official TutorialTitle id {target['tutorialTitleId']}",
                        ],
                        "verification": "local_emevd_tutorial_unlock_verified",
                    })
    deduped = {binding["id"]: binding for binding in bindings}
    return [deduped[key] for key in sorted(deduped)], unresolved


def build(param_dir: Path, emevd_dir: Path, registry_path: Path, fmg_path: Path) -> dict[str, Any]:
    by_row, entities, identity_unresolved = tutorial_entities(
        registry_path, param_dir, fmg_path
    )
    bindings, event_unresolved = event_bindings(emevd_dir, by_row)
    bound_entities = {
        item["item"] for binding in bindings for item in binding.get("items", [])
    }
    all_entity_ids = {entity["id"] for entity in entities}
    return {
        "schema": "elden-ring-tutorial-unlock-bindings@1",
        "builtFrom": {
            "paramDir": str(param_dir.resolve()),
            "parsedEmevd": str(emevd_dir.resolve()),
            "entityRegistry": str(registry_path.resolve()),
            "entityRegistrySha256": sha256(registry_path),
            "officialFmg": str(fmg_path.resolve()),
            "officialFmgSha256": sha256(fmg_path),
            "policy": "exact local event and official-title facts only; no route or trigger object inferred",
        },
        "stats": {
            "tutorialEntityCount": len(entities),
            "matchedTutorialParamRowCount": len(by_row),
            "bindingCount": len(bindings),
            "locallyBoundEntityCount": len(bound_entities),
            "locallyUnboundEntityCount": len(all_entity_ids - bound_entities),
        },
        "bindings": bindings,
        "unresolvedSources": identity_unresolved + event_unresolved,
        "locallyUnboundEntities": sorted(all_entity_ids - bound_entities),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--param-dir", type=Path, default=DEFAULT_PARAM_DIR)
    parser.add_argument("--parsed-emevd", type=Path, default=DEFAULT_EMEVD_DIR)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--official-fmg", type=Path, default=DEFAULT_FMG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build(args.param_dir, args.parsed_emevd, args.registry, args.official_fmg)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2))
    print(f"unresolved_sources={len(payload['unresolvedSources'])}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
