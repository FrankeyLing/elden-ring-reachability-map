#!/usr/bin/env python3
"""Build an independent event-reward evidence catalog.

This catalog records direct EMEVD item-award instructions and the local item
lot rows they reference.  It deliberately does not guess an NPC or quest
identity: an event can be a boss reward, a story reward, a system grant, or a
quest step.  Event flags are retained as evidence for a later classification
pass.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FMG_INDEX = ROOT / "data" / "v1" / "entities" / "official-fmg-bilingual-index.json"
DEFAULT_FLAGS = ROOT.parent.parent / "local-snapshots" / "elden-ring-20260818" / "supporting" / "smithbox-er-event-flags.json"
_suffix_re = re.compile(r"(_dlc0[12])?\.fmg$")

LOT_CATEGORY_TABLES = {
    1: "GoodsName",
    2: "WeaponName",
    3: "ProtectorName",
    4: "AccessoryName",
    5: "GemName",
}
LOT_CATEGORY_KIND = {
    1: "item",
    2: "weapon",
    3: "armor",
    4: "accessory",
    5: "ash_of_war",
}
LOT_CHAIN_REFERENCE = "https://soulsmodding.wikidot.com/param:itemlotparam"
TYPE_SIZE = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 8}


def load_name_tables() -> dict[str, dict[int, dict[str, str]]]:
    records = json.loads(FMG_INDEX.read_text(encoding="utf-8"))["records"]
    tables: dict[str, dict[int, dict[str, str]]] = {}
    for record in records:
        if record["language"] not in ("engus", "zhocn"):
            continue
        fmg = _suffix_re.sub("", record["fmg"].replace("\\", "/").split("/")[-1])
        entry = tables.setdefault(fmg, {}).setdefault(int(record["id"]), {})
        entry["en" if record["language"] == "engus" else "zh"] = record["text"]
    return tables


def clean_name(value: str | None) -> str | None:
    if not value or value in ("[ERROR]", ""):
        return None
    return value.removeprefix("[ERROR]").strip() or None


def decode_args(raw: bytes, definition: dict[str, Any]) -> list[int | None]:
    values: list[int | None] = []
    offset = 0
    for argument in definition.get("args", []):
        size = TYPE_SIZE[int(argument["type"])]
        offset = (offset + size - 1) & ~(size - 1)
        chunk = raw[offset:offset + size]
        if len(chunk) != size:
            raise ValueError("truncated instruction arguments")
        kind = int(argument["type"])
        if kind == 6:
            values.append(None)
        else:
            values.append(int.from_bytes(chunk, "little", signed=kind in (1, 3, 5)))
        offset += size
    return values


def load_rows(param_dir: Path, table: str) -> dict[int, dict[str, Any]]:
    rows = json.loads((param_dir / f"{table}.json").read_text(encoding="utf-8"))["rows"]
    return {int(row["id"]): row["cells"] for row in rows}


def load_flag_names(path: Path) -> dict[int, dict[str, Any]]:
    if not path.is_file():
        return {}
    return {int(row["ID"]): row for row in json.loads(path.read_text(encoding="utf-8"))}


def event_flags(reference_path: Path, event_id: int, flag_names: dict[int, dict[str, Any]]) -> dict[str, Any]:
    if not reference_path.is_file():
        return {"eventFlagIds": [], "eventFlags": [], "evidenceStatus": "no_semantic_reference"}
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    ids: set[int] = set()
    for reference in payload.get("references", []):
        if reference.get("event_id") != event_id:
            continue
        for value in reference.get("event_flag_ids", []):
            if isinstance(value, (int, float)):
                ids.add(int(value))
    return {
        "eventFlagIds": sorted(ids),
        "eventFlags": [
            {"id": flag_id, "name": flag_names[flag_id].get("Name"), "tags": flag_names[flag_id].get("Tags", [])}
            for flag_id in sorted(ids) if flag_id in flag_names
        ],
        "evidenceStatus": "semantic_event_flags_verified",
    }


def expand_lot_chain(
    root_lot_id: int,
    lot_by_id: dict[int, dict],
    referenced_lot_ids: set[int],
) -> list[int]:
    """Expand consecutive ItemLotParam rows for one event-award root."""
    chain: list[int] = []
    lot_id = root_lot_id
    while lot_id in lot_by_id:
        if lot_id != root_lot_id and lot_id in referenced_lot_ids:
            break
        chain.append(lot_id)
        lot_id += 1
    return chain


def build(parsed_dir: Path, semantic_dir: Path, emedf_path: Path, param_dir: Path, flags_path: Path) -> dict[str, Any]:
    emedf = json.loads(emedf_path.read_text(encoding="utf-8"))
    definitions: dict[tuple[int, int], dict[str, Any]] = {}
    for group in emedf["main_classes"]:
        for instruction in group.get("instrs", []):
            if instruction.get("name") in {"Award Item Lot", "Award Items (Including Clients)"}:
                definitions[(int(group["index"]), int(instruction["index"]))] = instruction
    if not definitions:
        raise SystemExit("award instruction definitions not found")

    tables = load_name_tables()
    flag_names = load_flag_names(flags_path)
    lots_by_table: dict[str, dict[int, dict]] = {}
    for table in ("ItemLotParam_map", "ItemLotParam_enemy"):
        lots_by_table[table] = load_rows(param_dir, table)

    records: list[dict[str, Any]] = []
    raw_awards = 0
    zero_lots = 0
    decoded_awards: list[dict[str, Any]] = []
    for file_path in sorted(parsed_dir.glob("*.json")):
        if file_path.name == "batch-manifest.json":
            continue
        file_data = json.loads(file_path.read_text(encoding="utf-8"))
        map_key = Path(file_data.get("source_file", file_path.name)).name.removesuffix(".emevd.dcx")
        ref_path = semantic_dir / file_path.name
        for event in file_data.get("events", []):
            for instruction in event.get("instructions", []):
                opcode = (int(instruction.get("bank", -1)), int(instruction.get("id", -1)))
                definition = definitions.get(opcode)
                if definition is None:
                    continue
                raw_awards += 1
                try:
                    decoded = decode_args(bytes.fromhex(instruction.get("args_hex", "")), definition)
                except (ValueError, IndexError):
                    continue
                lot_id = int(decoded[0]) if decoded and decoded[0] is not None else 0
                if lot_id <= 0:
                    zero_lots += 1
                    continue
                lot_table = next(
                    (
                        table for table in ("ItemLotParam_map", "ItemLotParam_enemy")
                        if lot_id in lots_by_table[table]
                    ),
                    None,
                )
                if lot_table is None:
                    continue
                decoded_awards.append({
                    "file_path": file_path,
                    "map_key": map_key,
                    "ref_path": ref_path,
                    "event": event,
                    "instruction": instruction,
                    "lot_id": lot_id,
                    "lot_table": lot_table,
                })

    roots_by_table: dict[str, set[int]] = {
        table: {
            award["lot_id"] for award in decoded_awards
            if award["lot_table"] == table
        }
        for table in lots_by_table
    }
    for award in decoded_awards:
        lot_id = award["lot_id"]
        lot_table = award["lot_table"]
        lot_by_id = lots_by_table[lot_table]
        chain_ids = expand_lot_chain(lot_id, lot_by_id, roots_by_table[lot_table])
        items = []
        for chain_lot_id in chain_ids:
            lot = lot_by_id[chain_lot_id]
            for slot in range(1, 9):
                item_id = lot.get(f"lotItemId{slot:02d}")
                category = lot.get(f"lotItemCategory{slot:02d}")
                if not item_id or item_id <= 0:
                    continue
                table = LOT_CATEGORY_TABLES.get(category)
                name_entry = tables.get(table, {}).get(item_id, {}) if table else {}
                english = clean_name(name_entry.get("en"))
                if not english:
                    continue
                items.append({
                    "item": f"{LOT_CATEGORY_KIND.get(category, 'item')}_{re.sub(r'[^a-z0-9]+', '_', english.lower()).strip('_')}",
                    "name": {"en": english, "zh": clean_name(name_entry.get("zh")) or english},
                    "category": category,
                    "lot": chain_lot_id,
                    "slot": slot,
                    "num": lot.get(f"lotItemNum{slot:02d}"),
                })
        if not items:
            continue
        flags = event_flags(award["ref_path"], int(award["event"]["id"]), flag_names)
        records.append({
            "id": f"event-reward-{award['map_key']}-{award['event']['id']}-{award['instruction']['index']}",
            "method": "event_reward",
            "map": award["map_key"],
            "eventId": int(award["event"]["id"]),
            "instructionIndex": int(award["instruction"]["index"]),
            "itemLot": {"param": lot_table, "rowId": lot_id},
            "items": items,
            "sourceItemLotRows": chain_ids,
            "eventFlags": flags["eventFlags"],
            "eventFlagIds": flags["eventFlagIds"],
            "taskStatus": "unclassified",
            "evidence": [
                f"local EMEVD {award['map_key']} event {award['event']['id']} award instruction {award['instruction']['index']}",
                f"local {lot_table} row {lot_id}",
                "sequential " + lot_table + " continuation rows "
                + ",".join(str(value) for value in chain_ids),
                flags["evidenceStatus"],
            ],
            "verification": (
                "local_emevd_and_param_verified_sequential_lot_chain"
                if len(chain_ids) > 1 else "local_emevd_and_param_verified"
            ),
        })

    return {
        "schema": "elden-ring-event-reward-bindings@1",
        "builtFrom": {
            "parsedEmevd": str(parsed_dir),
            "semanticReferences": str(semantic_dir),
            "emedf": str(emedf_path),
            "paramDir": str(param_dir),
            "eventFlags": str(flags_path),
            "itemLotChainReference": LOT_CHAIN_REFERENCE,
            "policy": "event award is factual; quest or NPC identity is never inferred from an event alone",
        },
        "stats": {
            "rawAwardInstructions": raw_awards,
            "zeroLotInstructions": zero_lots,
            "bindings": len(records),
            "withEventFlags": sum(bool(record["eventFlagIds"]) for record in records),
            "taskUnclassified": len(records),
        },
        "bindings": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parsed-emevd", type=Path, required=True)
    parser.add_argument("--semantic-references", type=Path, required=True)
    parser.add_argument("--emedf", type=Path, required=True)
    parser.add_argument("--param-dir", type=Path, required=True)
    parser.add_argument("--event-flags", type=Path, default=DEFAULT_FLAGS)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "v1" / "entities" / "event-reward-bindings.json")
    args = parser.parse_args()
    payload = build(args.parsed_emevd, args.semantic_references, args.emedf, args.param_dir, args.event_flags)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2))
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
