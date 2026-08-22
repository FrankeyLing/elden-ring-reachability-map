#!/usr/bin/env python3
"""Dump every regulation param to JSON via the C# paramdump tool.

Reads the regulation BND4 index, matches each param to its Paramdex XML
definition, and runs the net10 paramdump executable for every param.

Usage:
    python scripts/dump-all-params.py \
        --bnd4-index <regulation-bnd4-index.json> \
        --entries-dir <extracted/regulation-entries> \
        --paramdef-dir <supporting/paramdex-er-defs> \
        --out-dir <extracted/param-json> \
        --tool <paramdump.dll> [--dotnet-root <dir>]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bnd4-index", type=Path, required=True)
    parser.add_argument("--entries-dir", type=Path, required=True)
    parser.add_argument("--paramdef-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--tool", type=Path, required=True, help="paramdump.dll path")
    parser.add_argument("--dotnet-root", type=Path, default=None, help="user dotnet10 root for runtime")
    parser.add_argument("--only", default=None, help="comma-separated param names to dump (debug)")
    args = parser.parse_args()

    index = json.loads(args.bnd4_index.read_text(encoding="utf-8"))
    paramdefs = {p.name[:-4] for p in args.paramdef_dir.glob("*.xml")}
    args.out_dir.mkdir(parents=True, exist_ok=True)

    env = None
    if args.dotnet_root is not None:
        env = {"DOTNET_ROOT": str(args.dotnet_root), "DOTNET_MULTILEVEL_LOOKUP": "0"}
    dotnet = args.dotnet_root / "dotnet.exe" if args.dotnet_root else Path("dotnet")

    only = set(args.only.split(",")) if args.only else None
    ok, failed, skipped = 0, [], 0
    for entry in index["entries"]:
        name = (entry["name"] or "").split("\\")[-1]
        if not name.endswith(".param"):
            skipped += 1
            continue
        base = name[:-6]
        xml = args.paramdef_dir / f"{base}.xml"
        if not xml.exists():
            # merged variants share the base definition (e.g. ItemLotParam_map.param -> ItemLotParam.xml)
            stripped = (
                base.replace("_enemy", "")
                .replace("_map", "")
                .replace("_PC", "")
                .replace("_Recipe", "")
            )
            xml = args.paramdef_dir / f"{stripped}.xml"
        if not xml.exists():
            # param file name drops the Param suffix (Magic.param -> MagicParam.xml, Ceremony.param -> CeremonyParam.xml)
            xml = args.paramdef_dir / f"{base}Param.xml"
        if not xml.exists():
            skipped += 1
            continue
        if only is not None and base not in only:
            continue
        src = args.entries_dir / f"{entry['index']:03d}-entry-{entry['index']}"
        out = args.out_dir / f"{base}.json"
        if out.exists():
            ok += 1
            continue
        result = subprocess.run(
            [str(dotnet), str(args.tool), str(src), str(xml), str(out)],
            capture_output=True, text=True, env=env, timeout=120,
        )
        if result.returncode == 0 and out.exists():
            ok += 1
        else:
            failed.append((base, result.returncode, result.stderr.strip()[-200:]))
            if len(failed) > 10:
                break

    print(f"dumped={ok} skipped={skipped} failed={len(failed)}")
    for base, code, err in failed:
        print(f"  FAIL {base}: rc={code} {err}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
