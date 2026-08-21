#!/usr/bin/env python3
"""Extract boss reward acquisitions from EMEVD AwardItemLot instructions.

Every EMEVD file (per map) is scanned for "Award Item Lot" (class 17, instr 4).
The lot id resolves into ItemLotParam_enemy rows; lots containing a Remembrance
(or Great Rune) identify the boss fight reward.  The official Remembrance name
maps to the boss entity via the name map below.

Usage:
    python scripts/build-boss-rewards.py \
        --parsed-emevd <snapshot>/extracted/parsed-emevd/files \
        --emedf <tools>/event-defs/er-common.emedf.json \
        --param-dir <snapshot>/extracted/param-json \
        --registry data/v1/entities/entity-registry.json \
        --out data/v1/entities/boss-rewards.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FMG_INDEX = ROOT / "data" / "v1" / "entities" / "official-fmg-bilingual-index.json"

# Official Remembrance goods name -> boss NpcName (FromSoftware official names)
REMEMBRANCE_TO_BOSS = {
    "Remembrance of the Grafted": "Godrick the Grafted",
    "Remembrance of the Starscourge": "Starscourge Radahn",
    "Remembrance of the Omen King": "Morgott, the Omen King",
    "Remembrance of the Blasphemous": "Rykard, Lord of Blasphemy",
    "Remembrance of the Rot Goddess": "Malenia, Blade of Miquella",
    "Remembrance of the Blood Lord": "Mohg, Lord of Blood",
    "Remembrance of the Full Moon Queen": "Rennala, Queen of the Full Moon",
    "Remembrance of the Naturalborn": "Astel, Naturalborn of the Void",
    "Remembrance of the Dragonlord": "Dragonlord Placidusax",
    "Remembrance of the Regal Ancestor": "Regal Ancestor Spirit",
    "Remembrance of the Fire Giant": "Fire Giant",
    "Remembrance of the Black Blade": "Maliketh, the Black Blade",
    "Remembrance of Hoarah Loux": "Hoarah Loux, Warrior",
    "Remembrance of the Elden Beast": "Elden Beast",
    "Remembrance of the Lord of Frenzied Flame": "Lord of Frenzied Flame",
    "Remembrance of the Wild Dancer": "Divine Beast Dancing Lion",
    "Remembrance of the Mother of Fingers": "Metyr, Mother of Fingers",
    "Remembrance of the Impaler": "Messmer the Impaler",
    "Remembrance of the Saint of the Bud": "Romina, Saint of the Bud",
    "Remembrance of the Dread": "Midra, Lord of Frenzied Flame",
    "Remembrance of the Falling Star Beast": "Fallingstar Beast",
    "Remembrance of the Twin Moon Knight": "Rellana, Twin Moon Knight",
    "Remembrance of the Shadow Sunflower": "Scadutree Avatar",
    "Remembrance of the Dancing Lion": "Divine Beast Dancing Lion",
    "Remembrance of the Bloodfiend's Arm": "Bloodfiend's Arm",
}

TYPE_INFO = {
    0: (1, "u8"), 1: (1, "s8"), 2: (2, "u16"), 3: (2, "s16"),
    4: (4, "u32"), 5: (4, "s32"), 6: (8, "f64"),
}

_suffix_re = re.compile(r"(_dlc0[12])?\.fmg$")


def load_name_tables() -> dict[str, dict[int, dict[str, str]]]:
    tables: dict[str, dict[int, dict[str, str]]] = {}
    with open(FMG_INDEX, encoding="utf-8") as fh:
        recs = json.load(fh)["records"]
    for rec in recs:
        lang = rec["language"]
        if lang not in ("engus", "zhocn"):
            continue
        fmg_name = _suffix_re.sub("", rec["fmg"].replace("\\", "/").split("/")[-1])
        entry = tables.setdefault(fmg_name, {}).setdefault(rec["id"], {})
        entry["en" if lang == "engus" else "zh"] = rec["text"]
    return tables


def clean_name(text: str | None) -> str | None:
    if not text or text in ("[ERROR]", ""):
        return None
    if text.startswith("[ERROR]"):
        text = text[len("[ERROR]"):].strip()
    return text or None


def decode_args(raw: bytes, definition: dict) -> list[dict]:
    decoded = []
    offset = 0
    for argument in definition.get("args", []):
        size, _ = TYPE_INFO[argument["type"]]
        offset = (offset + size - 1) & ~(size - 1)
        chunk = raw[offset:offset + size]
        if argument["type"] == 0:
            value = chunk[0]
        elif argument["type"] in (1, 2):
            value = int.from_bytes(chunk, "little", signed=False)
        elif argument["type"] in (3, 4, 5):
            value = int.from_bytes(chunk, "little", signed=True)
        else:
            value = None
        decoded.append({"name": argument["name"], "value": value})
        offset += size
    return decoded


def param_rows(param_dir: Path, name: str) -> list[dict[str, Any]]:
    path = param_dir / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"param dump missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))["rows"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parsed-emevd", type=Path, required=True)
    parser.add_argument("--emedf", type=Path, required=True)
    parser.add_argument("--param-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "boss-rewards.json")
    args = parser.parse_args()

    emedf = json.loads(args.emedf.read_text(encoding="utf-8"))
    definitions = {
        (int(group["index"]), int(instruction["index"])): instruction
        for group in emedf["main_classes"]
        for instruction in group.get("instrs", [])
    }
    def find_def(name):
        for group in emedf["main_classes"]:
            for ins in group.get("instrs", []):
                if ins.get("name") == name:
                    return int(group["index"]), ins
        return None, None

    award_class_index, award_def = find_def("Award Item Lot")
    award_items_index, award_items_def = find_def("Award Items (Including Clients)")
    if award_def is None:
        raise SystemExit("AwardItemLot not found in emedf")

    tables = load_name_tables()
    # Boss reward lots (remembrances / great runes) live in ItemLotParam_map
    lot_by_id = {}
    for lot_param in ("ItemLotParam_map", "ItemLotParam_enemy"):
        for r in param_rows(args.param_dir, lot_param):
            lot_by_id.setdefault(r["id"], (lot_param, r["cells"]))
    goods_names = tables["GoodsName"]

    awards: list[dict] = []
    for file_path in sorted(args.parsed_emevd.glob("*.json")):
        if file_path.name == "batch-manifest.json":
            continue
        file_data = json.loads(file_path.read_text(encoding="utf-8"))
        map_key = Path(file_data.get("source_file", file_path.name)).name.removesuffix(".emevd.dcx")
        for event in file_data.get("events", []):
            for instruction in event.get("instructions", []):
                op = (int(instruction["bank"]), int(instruction["id"]))
                definition = None
                if op == (award_class_index, award_def["index"]):
                    definition = award_def
                elif award_items_def is not None and op == (award_items_index, award_items_def["index"]):
                    definition = award_items_def
                if definition is None:
                    continue
                try:
                    decoded = decode_args(bytes.fromhex(instruction.get("args_hex", "")), definition)
                except (ValueError, IndexError):
                    continue
                lot_id = decoded[0]["value"] if decoded else None
                if not lot_id:
                    continue
                lot_hit = lot_by_id.get(lot_id)
                items = []
                if lot_hit:
                    lot_param_name, lot = lot_hit
                    for k in range(1, 9):
                        iid = lot.get(f"lotItemId{k:02d}")
                        if not iid or iid <= 0:
                            continue
                        entry = goods_names.get(iid)
                        en = clean_name((entry or {}).get("en"))
                        if not en:
                            continue
                        items.append({
                            "goodsId": iid,
                            "name": {"en": en, "zh": clean_name((entry or {}).get("zh")) or en},
                            "num": lot.get(f"lotItemNum{k:02d}"),
                        })
                awards.append({
                    "map": map_key,
                    "event": event["id"],
                    "lot": lot_id,
                    "lot_param": lot_hit[0] if lot_hit else None,
                    "items": items,
                })

    # group by lot
    by_lot: dict[int, dict] = {}
    for a in awards:
        entry = by_lot.setdefault(a["lot"], {
            "lot": a["lot"], "lot_param": a.get("lot_param"), "maps": [], "events": [], "items": a["items"] or [],
        })
        if a["map"] not in entry["maps"]:
            entry["maps"].append(a["map"])
        entry["events"].append(a["event"])

    rewards = []
    for lot_entry in sorted(by_lot.values(), key=lambda x: x["lot"]):
        remembrances = [i for i in lot_entry["items"] if "Remembrance" in i["name"]["en"]]
        great_runes = [i for i in lot_entry["items"] if "Great Rune" in i["name"]["en"]]
        boss = None
        if remembrances:
            rem_name = remembrances[0]["name"]["en"]
            boss_name = REMEMBRANCE_TO_BOSS.get(rem_name)
            if boss_name:
                boss = f"enemy_{re.sub(r'[^a-z0-9]+', '_', boss_name.lower()).strip('_')}"
        reward = {
            "id": f"boss-reward-lot{lot_entry['lot']}",
            "method": "boss_reward",
            "lot": {"param": lot_entry.get("lot_param") or "ItemLotParam_map", "rowId": lot_entry["lot"]},
            "remembrance": remembrances[0]["name"]["en"] if remembrances else None,
            "great_rune": great_runes[0]["name"]["en"] if great_runes else None,
            "boss": boss,
            "boss_name": REMEMBRANCE_TO_BOSS.get(remembrances[0]["name"]["en"]) if remembrances else None,
            "items": lot_entry["items"],
            "maps": lot_entry["maps"],
            "evidence": [f"EMEVD AwardItemLot lot {lot_entry['lot']} in {','.join(lot_entry['maps'])}"],
            "verification": "local_emevd_verified",
        }
        rewards.append(reward)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "errn-boss-rewards@1",
        "built_at": "2026-08-20",
        "stats": {"award_instructions": len(awards), "unique_lots": len(by_lot),
                  "boss_rewards": len([r for r in rewards if r["boss"]]),
                  "remembrance_rewards": len([r for r in rewards if r["remembrance"]])},
        "rewards": rewards,
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"award instructions: {len(awards)}, unique lots: {len(by_lot)}")
    print(f"boss rewards: {len([r for r in rewards if r['boss']])}, remembrance rewards: {len([r for r in rewards if r['remembrance']])}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
