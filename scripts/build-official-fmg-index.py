#!/usr/bin/env python3
"""Extract ALL FMG texts from the copied game message binders (engus + zhocn).

Reuses the pinned Oodle/KRAK decoder and BND4 parser from the NVA pipeline.
Output is a bilingual dictionary keyed by (fmg, id), used to build the
official-Chinese mapping for the formal graph.

Usage:
    python scripts/build-official-fmg-index.py \
        --msg-root C:/Users/Frankey/ZCodeProject/local-snapshots/elden-ring-20260818/extracted/msg-all \
        --oodle-dll C:/Users/Frankey/ZCodeProject/local-snapshots/elden-ring-20260818/runtime/oo2core_6_win64.dll \
        --output data/v1/entities/official-fmg-bilingual-index.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path


def load_nva_helpers(script_dir: Path):
    nva_path = script_dir / "build-local-nva-navmesh-index.py"
    spec = importlib.util.spec_from_file_location("local_nva_helpers", nva_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load NVA helper module: {nva_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bnd_path = script_dir / "build-local-nvmhktbnd-index.py"
    spec2 = importlib.util.spec_from_file_location("local_bnd_helpers", bnd_path)
    if spec2 is None or spec2.loader is None:
        raise RuntimeError(f"cannot load BND4 helper module: {bnd_path}")
    module2 = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(module2)
    return module.OodleKrak, module2.parse_bnd4


def read_varint(raw: bytes, offset: int, wide: bool) -> tuple[int, int]:
    """Read a varint-sized integer; returns (value, next_offset)."""
    if wide:
        return struct.unpack_from("<Q", raw, offset)[0], offset + 8
    return struct.unpack_from("<I", raw, offset)[0], offset + 4


def parse_fmg(raw: bytes) -> dict[int, str]:
    """Elden Ring FMG (SoulsFormats DarkSouls3 layout, version byte 2).

    Layout: [optional MD5] 0x00 | bigEndian(bool) | version(byte) | 0x00 |
    fileSize(i32) | unicode(bool) | 0x00 0x00 0x00 | groupCount(i32) |
    stringCount(i32) | 0xFF(i32, wide) | stringOffsetsOffset(varint) | 0(varint)
    then groups of {offsetIndex(i32) firstID(i32) lastID(i32) [0(i32 wide)]}
    with per-entry varint string offsets into UTF-16 text.
    """
    cursor = 0
    if raw[0] != 0:
        cursor += 16  # MD5
    assert raw[cursor] == 0
    cursor += 1
    big_endian = bool(raw[cursor])
    cursor += 1
    version = raw[cursor]
    cursor += 1
    assert raw[cursor] == 0
    cursor += 1
    wide = version == 2  # DarkSouls3 / Elden Ring
    file_size = struct.unpack_from("<I" if not big_endian else ">I", raw, cursor)[0]
    cursor += 4
    unicode_text = bool(raw[cursor])
    cursor += 1
    cursor += 3  # 0x00 0x00 0x00
    group_count = struct.unpack_from("<i" if not big_endian else ">i", raw, cursor)[0]
    cursor += 4
    cursor += 4  # string count
    if wide:
        cursor += 4  # 0xFF marker
    string_offsets_offset, cursor = read_varint(raw, cursor, wide)
    _, cursor = read_varint(raw, cursor, wide)  # assert 0

    entries: dict[int, str] = {}
    for _ in range(group_count):
        offset_index, first_id, last_id = struct.unpack_from(
            "<3i" if not big_endian else ">3i", raw, cursor
        )
        cursor += 12
        if wide:
            cursor += 4  # 0 marker
        group_offsets = string_offsets_offset + offset_index * (8 if wide else 4)
        for j in range(last_id - first_id + 1):
            entry_offset = group_offsets + j * (8 if wide else 4)
            string_offset, _ = read_varint(raw, entry_offset, wide)
            entry_id = first_id + j
            if string_offset > 0 and string_offset < len(raw):
                if unicode_text:
                    end = string_offset
                    while end + 1 < len(raw) and raw[end : end + 2] != b"\0\0":
                        end += 2
                    entries[entry_id] = raw[string_offset:end].decode("utf-16le", errors="replace")
                else:
                    end = string_offset
                    while end < len(raw) and raw[end] != 0:
                        end += 1
                    entries[entry_id] = raw[string_offset:end].decode("shift_jis", errors="replace")
            else:
                entries[entry_id] = ""
    return entries


def extract_binder(binder_path: Path, decoder, parse_bnd4) -> list[dict]:
    data = binder_path.read_bytes()
    raw = decoder.decode(data)
    bnd4 = parse_bnd4(raw)
    files = []
    for entry in bnd4["files"]:
        name = entry["name"] or f"file_{entry['id']:08d}"
        payload_start = entry["data_offset"]
        payload = raw[payload_start : payload_start + entry["compressed_size"]]
        if entry["compressed"]:
            raise ValueError(f"unexpected compressed inner file: {name}")
        files.append({"name": name, "payload": payload})
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--msg-root", type=Path, required=True)
    parser.add_argument("--oodle-dll", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--list-only", action="store_true", help="print FMG names and stop")
    args = parser.parse_args()

    msg_root = args.msg_root.resolve()
    script_dir = Path(__file__).resolve().parent
    OodleKrak, parse_bnd4 = load_nva_helpers(script_dir)
    decoder = OodleKrak(args.oodle_dll.resolve())

    binders = sorted(msg_root.rglob("*.msgbnd.dcx"))
    print(f"binders: {len(binders)}")
    fmg_names = set()
    records = []
    failures = []
    for binder_path in binders:
        relative = binder_path.relative_to(msg_root).as_posix()
        segments = relative.split("/")
        locale = segments[1] if len(segments) > 1 else "unknown"
        if locale not in ("engus", "zhocn"):
            continue
        source_hash = hashlib.sha256(binder_path.read_bytes()).hexdigest().upper()
        try:
            files = extract_binder(binder_path, decoder, parse_bnd4)
        except Exception as exc:  # noqa: BLE001 - record and continue
            failures.append({"file": relative, "error": str(exc)})
            continue
        for file_entry in files:
            name = file_entry["name"]
            if not name.lower().endswith(".fmg"):
                continue
            fmg_names.add(name)
            if args.list_only:
                continue
            try:
                entries = parse_fmg(file_entry["payload"])
            except Exception as exc:  # noqa: BLE001 - record and continue
                failures.append({"file": f"{relative}/{name}", "error": str(exc)})
                continue
            for entry_id, text in entries.items():
                records.append(
                    {
                        "language": locale,
                        "fmg": name,
                        "id": entry_id,
                        "text": text,
                        "source_file": f"msg/{locale}/{binder_path.name}",
                        "source_sha256": source_hash,
                        "verification_state": "local_fmg_verified",
                    }
                )

    if args.list_only:
        for name in sorted(fmg_names):
            print(name)
        return 0

    output = {
        "schema": "elden-ring-official-fmg-bilingual-index@1",
        "source": {
            "snapshot_id": "elden-ring-local-snapshot-20260818",
            "input_root": str(msg_root),
            "locales": ["engus", "zhocn"],
            "note": "Extracted from the copied snapshot with the pinned Oodle decoder; official FromSoftware texts only.",
        },
        "records": records,
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
    print(f"records: {len(records)}  failures: {len(failures)}")
    print(f"output: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
