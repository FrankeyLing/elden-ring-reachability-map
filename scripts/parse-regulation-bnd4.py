#!/usr/bin/env python3
"""Parse the Elden Ring regulation.bin BND4 container (after AES-CBC decrypt + DCX).

Layout follows SoulsFormats BND4.Read:
  header 0x40 bytes, file headers of `fileHeaderSize` (36 here) starting at 0x40,
  UTF-16LE names, optional hash table, then file data.
Output: JSON list of entries with name / sizes / offsets, plus optionally raw
extract of selected entries to a directory.

Usage:
    python scripts/parse-regulation-bnd4.py <reg-bnd4.bin> <out.json> [--extract <dir>]
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path


def reverse_bits(value: int) -> int:
    result = 0
    for _ in range(8):
        result = (result << 1) | (value & 1)
        value >>= 1
    return result


def parse_bnd4(raw: bytes) -> dict:
    if len(raw) < 0x40 or raw[:4] != b"BND4":
        raise ValueError("not a BND4 payload")
    file_count = struct.unpack_from("<I", raw, 0x0C)[0]
    header_size = struct.unpack_from("<Q", raw, 0x10)[0]
    version = raw[0x18:0x20].split(b"\x00")[0].decode("ascii", "replace")
    file_header_size = struct.unpack_from("<Q", raw, 0x20)[0]
    headers_end = struct.unpack_from("<Q", raw, 0x28)[0]
    unicode_names = bool(raw[0x30])
    format_raw = raw[0x31]
    bit_big_endian = not bool(raw[0x0A])
    format_value = reverse_bits(format_raw) if bit_big_endian else format_raw
    extended = raw[0x32]
    hash_table_offset = struct.unpack_from("<Q", raw, 0x38)[0]

    entries = []
    names_start = 0x40 + file_count * file_header_size
    for index in range(file_count):
        off = 0x40 + index * file_header_size
        flags_raw = raw[off]
        flags = reverse_bits(flags_raw) if bit_big_endian else flags_raw
        compressed_size = struct.unpack_from("<Q", raw, off + 8)[0]
        uncompressed_size = struct.unpack_from("<Q", raw, off + 16)[0]
        data_offset = struct.unpack_from("<I", raw, off + 24)[0]
        file_id = struct.unpack_from("<I", raw, off + 28)[0]
        name_offset = struct.unpack_from("<I", raw, off + 32)[0]
        entries.append({
            "index": index,
            "flags_raw": flags_raw,
            "flags": flags,
            "compressed": bool(flags & 0x01),
            "compressed_size": compressed_size,
            "uncompressed_size": uncompressed_size,
            "data_offset": data_offset,
            "id": file_id,
            "name_offset": name_offset,
        })

    names = {}
    if unicode_names:
        for e in entries:
            no = e["name_offset"]
            if no == 0xFFFFFFFF or no >= len(raw) - 1:
                continue
            i = no
            while i + 1 < len(raw) and raw[i : i + 2] != b"\x00\x00":
                i += 2
            try:
                names[e["index"]] = raw[no:i].decode("utf-16-le")
            except UnicodeDecodeError:
                names[e["index"]] = None

    return {
        "file_count": file_count,
        "header_size": header_size,
        "version": version,
        "file_header_size": file_header_size,
        "headers_end": headers_end,
        "unicode_names": unicode_names,
        "format": format_value,
        "extended": extended,
        "hash_table_offset": hash_table_offset,
        "entries": entries,
        "names": names,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse regulation BND4 container")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--extract", type=Path, default=None, help="extract raw entry payloads to a directory")
    args = parser.parse_args()

    raw = args.input.read_bytes()
    parsed = parse_bnd4(raw)
    out = {
        "schema": "errn-regulation-bnd4@1",
        "source_file": str(args.input.resolve()),
        "container": {k: v for k, v in parsed.items() if k not in ("entries", "names")},
        "entries": [],
    }
    for e in parsed["entries"]:
        record = dict(e)
        record["name"] = parsed["names"].get(e["index"])
        if args.extract is not None:
            start = e["data_offset"]
            payload = raw[start : start + e["compressed_size"]]
            if len(payload) != e["compressed_size"]:
                raise ValueError(f"entry {e['index']} payload out of range")
            safe = (record["name"] or f"entry-{e['index']}").replace("/", "_").replace("\\", "_")
            args.extract.mkdir(parents=True, exist_ok=True)
            (args.extract / f"{e['index']:03d}-{safe}").write_bytes(payload)
            record["extracted"] = str(args.extract / f"{e['index']:03d}-{safe}")
        out["entries"].append(record)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"entries={len(out['entries'])} version={parsed['version']} -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
