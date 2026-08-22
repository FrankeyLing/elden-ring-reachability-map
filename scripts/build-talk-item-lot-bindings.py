#!/usr/bin/env python3
"""Build exact Talk ESD item-lot award evidence from decompiled scripts.

Only integer values that can be propagated through local Python function calls
to ``AwardItemLot`` are published.  A talk file/map scope is evidence, but it
is not treated as an NPC identity, coordinate endpoint, or navigation anchor.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FMG_INDEX = ROOT / "data" / "v1" / "entities" / "official-fmg-bilingual-index.json"
DEFAULT_OUT = ROOT / "data" / "v1" / "entities" / "talk-item-lot-bindings.json"
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
FMG_TO_PARAM = {
    "GoodsName": "EquipParamGoods",
    "WeaponName": "EquipParamWeapon",
    "ProtectorName": "EquipParamProtector",
    "AccessoryName": "EquipParamAccessory",
    "GemName": "EquipParamGem",
}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def clean_name(value: str | None) -> str | None:
    if not value or value == "[ERROR]":
        return None
    return value.removeprefix("[ERROR]").strip() or None


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


def load_rows(param_dir: Path, table: str) -> dict[int, dict[str, Any]]:
    payload = json.loads((param_dir / f"{table}.json").read_text(encoding="utf-8"))
    return {int(row["id"]): row["cells"] for row in payload["rows"]}


def integer_value(node: ast.AST | None, environment: dict[str, int]) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return int(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = integer_value(node.operand, environment)
        return -value if value is not None else None
    if isinstance(node, ast.Name):
        return environment.get(node.id)
    return None


def called_name(call: ast.Call) -> str | None:
    return call.func.id if isinstance(call.func, ast.Name) else None


def function_parameters(function: ast.FunctionDef) -> list[str]:
    return [argument.arg for argument in function.args.args]


def bind_call(
    call: ast.Call,
    callee: ast.FunctionDef,
    environment: dict[str, int],
) -> dict[str, int]:
    names = function_parameters(callee)
    bound: dict[str, int] = {}
    for index, argument in enumerate(call.args):
        if index >= len(names):
            break
        value = integer_value(argument, environment)
        if value is not None:
            bound[names[index]] = value
    for keyword in call.keywords:
        if keyword.arg not in names:
            continue
        value = integer_value(keyword.value, environment)
        if value is not None:
            bound[keyword.arg] = value
    return bound


def resolve_awards(tree: ast.Module) -> tuple[list[dict[str, Any]], int, int]:
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    syntactic_awards = [
        (function.name, call)
        for function in functions.values()
        for call in ast.walk(function)
        if isinstance(call, ast.Call) and called_name(call) == "AwardItemLot"
    ]
    results: list[dict[str, Any]] = []

    def visit(
        function_name: str,
        environment: dict[str, int],
        path: list[dict[str, Any]],
        stack: set[tuple[str, tuple[tuple[str, int], ...]]],
    ) -> None:
        function = functions[function_name]
        state = (function_name, tuple(sorted(environment.items())))
        if state in stack:
            return
        next_stack = stack | {state}
        for call in (
            node for node in ast.walk(function) if isinstance(node, ast.Call)
        ):
            name = called_name(call)
            if name == "AwardItemLot":
                argument = call.args[0] if call.args else next(
                    (keyword.value for keyword in call.keywords if keyword.arg in {"lot", "lot1"}),
                    None,
                )
                lot_id = integer_value(argument, environment)
                if lot_id is not None and lot_id > 0:
                    results.append({
                        "lotId": lot_id,
                        "rootFunction": path[0]["caller"] if path else function_name,
                        "awardFunction": function_name,
                        "awardLine": int(call.lineno),
                        "callPath": path,
                    })
                continue
            if name not in functions:
                continue
            bound = bind_call(call, functions[name], environment)
            if not bound:
                continue
            visit(
                name,
                bound,
                path + [{
                    "caller": function_name,
                    "callee": name,
                    "line": int(call.lineno),
                    "boundArguments": dict(sorted(bound.items())),
                }],
                next_stack,
            )

    for function_name in sorted(functions):
        visit(function_name, {}, [], set())

    unique: dict[str, dict[str, Any]] = {}
    for result in results:
        key = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        unique[key] = result
    resolved_syntax = {
        (result["awardFunction"], result["awardLine"])
        for result in unique.values()
    }
    return (
        sorted(unique.values(), key=lambda row: (
            row["lotId"], row["rootFunction"], row["awardFunction"], row["awardLine"],
            json.dumps(row["callPath"], sort_keys=True),
        )),
        len(syntactic_awards),
        len(resolved_syntax),
    )


def expand_lot_chain(
    root_lot_id: int,
    lots: dict[int, dict[str, Any]],
    referenced_roots: set[int],
) -> list[int]:
    result = []
    lot_id = root_lot_id
    while lot_id in lots:
        if lot_id != root_lot_id and lot_id in referenced_roots:
            break
        result.append(lot_id)
        lot_id += 1
    return result


def build(talk_dir: Path, param_dir: Path) -> dict[str, Any]:
    names = load_name_tables()
    lots_by_table = {
        table: load_rows(param_dir, table)
        for table in ("ItemLotParam_map", "ItemLotParam_enemy")
    }
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    syntax_count = 0
    resolved_syntax_count = 0
    parsed_files = 0
    parse_failures: list[dict[str, str]] = []
    for path in sorted(talk_dir.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as error:
            parse_failures.append({"file": str(path), "error": str(error)})
            continue
        parsed_files += 1
        awards, file_syntax_count, file_resolved_count = resolve_awards(tree)
        syntax_count += file_syntax_count
        resolved_syntax_count += file_resolved_count
        map_id = path.parent.name
        for award in awards:
            grouped[(map_id, path.stem, award["lotId"])].append(award)

    referenced_roots = {lot_id for _, _, lot_id in grouped}
    bindings = []
    unresolved_lots = []
    for (map_id, talk_file, lot_id), call_sites in sorted(grouped.items()):
        lot_table = next(
            (table for table, rows in lots_by_table.items() if lot_id in rows),
            None,
        )
        if lot_table is None:
            unresolved_lots.append({
                "map": map_id,
                "talkFile": talk_file,
                "lotId": lot_id,
                "reason": "no_matching_local_item_lot_row",
            })
            continue
        chain_ids = expand_lot_chain(
            lot_id, lots_by_table[lot_table], referenced_roots
        )
        items = []
        for chain_lot_id in chain_ids:
            row = lots_by_table[lot_table][chain_lot_id]
            for slot in range(1, 9):
                item_id = row.get(f"lotItemId{slot:02d}")
                category = row.get(f"lotItemCategory{slot:02d}")
                table = LOT_CATEGORY_TABLES.get(category)
                if not isinstance(item_id, int) or item_id <= 0 or not table:
                    continue
                name = names.get(table, {}).get(item_id, {})
                english = clean_name(name.get("en"))
                if not english:
                    continue
                items.append({
                    "item": f"{LOT_CATEGORY_KIND[category]}_{slugify(english)}",
                    "name": {"en": english, "zh": clean_name(name.get("zh")) or english},
                    "sourceParam": FMG_TO_PARAM[table],
                    "sourceParamId": item_id,
                    "category": category,
                    "lot": chain_lot_id,
                    "slot": slot,
                    "num": row.get(f"lotItemNum{slot:02d}"),
                })
        if not items:
            continue
        bindings.append({
            "id": f"talk-item-lot-{map_id}-{talk_file}-{lot_id}",
            "method": "talk_reward",
            "map": map_id,
            "talkFile": talk_file,
            "itemLot": {"param": lot_table, "rowId": lot_id},
            "sourceItemLotRows": chain_ids,
            "items": items,
            "callSites": call_sites,
            "taskStatus": "npc_and_quest_unclassified",
            "evidence": [
                f"local Talk ESD {map_id}/{talk_file}.py exact AwardItemLot propagation",
                f"local {lot_table} row {lot_id}",
                "sequential item-lot continuation rows " + ",".join(map(str, chain_ids)),
            ],
            "verification": (
                "local_talk_esd_and_param_verified_sequential_lot_chain"
                if len(chain_ids) > 1
                else "local_talk_esd_and_param_verified"
            ),
        })

    return {
        "schema": "elden-ring-talk-item-lot-bindings@1",
        "builtFrom": {
            "talkEsdPython": str(talk_dir),
            "paramDir": str(param_dir),
            "policy": (
                "Only exact integer propagation to AwardItemLot is published; "
                "talk scope is not an NPC identity, endpoint, or topology anchor"
            ),
        },
        "stats": {
            "parsedFiles": parsed_files,
            "parseFailures": len(parse_failures),
            "syntacticAwardCalls": syntax_count,
            "resolvedAwardCallDefinitions": resolved_syntax_count,
            "resolvedCallSites": sum(len(value) for value in grouped.values()),
            "uniqueTalkLotReferences": len(grouped),
            "bindings": len(bindings),
            "unresolvedLots": len(unresolved_lots),
        },
        "bindings": bindings,
        "unresolvedLots": unresolved_lots,
        "parseFailures": parse_failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--talk-dir", type=Path, required=True)
    parser.add_argument("--param-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    payload = build(args.talk_dir, args.param_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2))
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
