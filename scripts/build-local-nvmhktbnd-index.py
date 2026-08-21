#!/usr/bin/env python3
"""Index native NVMHKT/BND4 Navmesh geometry entries from the snapshot.

The index does not deserialize Havok geometry yet.  It verifies the native
container, preserves each contained HKX name/size/offset, and binds NVA
ModelIDs to the corresponding ``<model_id>.hkx`` entry where possible.  This
keeps geometry provenance exact before any polygon or walkability promotion.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import struct
from pathlib import Path
from typing import Any


def load_nva_helpers() -> tuple[Any, Any]:
    script_path = Path(__file__).with_name("build-local-nva-navmesh-index.py")
    spec = importlib.util.spec_from_file_location("local_nva_helpers", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load NVA helper module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.OodleKrak, module.sha256


OodleKrak, sha256 = load_nva_helpers()
MODEL_FILE_RE = re.compile(r"(?P<model_id>\d{6})\.hkx$", flags=re.IGNORECASE)


def reverse_bits(value: int) -> int:
    return int(f"{value:08b}"[::-1], 2)


def decode_utf16_name(raw: bytes, offset: int) -> str | None:
    if offset <= 0 or offset >= len(raw):
        return None
    end = offset
    while end + 1 < len(raw):
        if raw[end : end + 2] == b"\0\0":
            break
        end += 2
    try:
        return raw[offset:end].decode("utf-16le")
    except UnicodeDecodeError:
        return None


def parse_bnd4(raw: bytes) -> dict[str, Any]:
    if len(raw) < 0x40 or raw[:4] != b"BND4":
        raise ValueError("decompressed NVMHKT payload is not BND4")
    file_count = struct.unpack_from("<I", raw, 0x0C)[0]
    file_header_size = struct.unpack_from("<Q", raw, 0x20)[0]
    headers_end = struct.unpack_from("<Q", raw, 0x28)[0]
    unicode_names = bool(raw[0x30])
    raw_format = raw[0x31]
    bit_big_endian = not bool(raw[0x0A])
    format_value = raw_format if bit_big_endian else reverse_bits(raw_format)
    if file_header_size <= 0 or 0x40 + file_count * file_header_size > len(raw):
        raise ValueError(
            f"invalid BND4 header file_count={file_count} file_header_size={file_header_size}"
        )
    files = []
    for index in range(file_count):
        offset = 0x40 + index * file_header_size
        flags_raw = raw[offset]
        flags = flags_raw if bit_big_endian else reverse_bits(flags_raw)
        compressed_size = struct.unpack_from("<Q", raw, offset + 8)[0]
        uncompressed_size = struct.unpack_from("<Q", raw, offset + 16)[0]
        data_offset = struct.unpack_from("<I", raw, offset + 24)[0]
        file_id = struct.unpack_from("<I", raw, offset + 28)[0]
        name_offset = struct.unpack_from("<I", raw, offset + 32)[0]
        name = decode_utf16_name(raw, name_offset) if unicode_names else None
        # These ER NVMHKT binders use the 32-bit data-offset layout.  Do not
        # silently read outside a declared file extent.
        if data_offset + compressed_size > len(raw):
            raise ValueError(f"BND4 entry {index} exceeds payload")
        entry = {
            "entry_index": index,
            "id": file_id,
            "name": name,
            "name_offset": name_offset,
            "flags_raw": flags_raw,
            "flags": flags,
            "compressed": bool(flags & 0x01),
            "compressed_size": compressed_size,
            "uncompressed_size": uncompressed_size,
            "data_offset": data_offset,
        }
        if not entry["compressed"]:
            inner = raw[data_offset : data_offset + compressed_size]
            entry["inner_magic"] = inner[:4].decode("ascii", errors="replace")
            entry["inner_tag"] = inner[4:8].decode("ascii", errors="replace")
            entry["inner_prefix_hex"] = inner[:16].hex().upper()
        files.append(entry)
    return {
        "file_count": file_count,
        "file_header_size": file_header_size,
        "headers_end": headers_end,
        "unicode_names": unicode_names,
        "format_value": format_value,
        "files": files,
    }


def model_id_from_name(name: str | None) -> int | None:
    if not name:
        return None
    match = MODEL_FILE_RE.search(name.replace("\\", "/").split("/")[-1])
    return int(match.group("model_id")) if match else None


def is_navmesh_hkx_name(name: str | None) -> bool:
    if not name:
        return False
    basename = name.replace("\\", "/").split("/")[-1].casefold()
    return basename.startswith("n") and basename.endswith(".hkx")


def build_record(record: dict[str, Any], input_root: Path, decoder: Any) -> dict[str, Any]:
    paired = record.get("paired_nvmhktbnd", {})
    source_file = paired.get("source_file")
    if not paired.get("present") or not source_file:
        raise ValueError("paired NVMHKT BND4 file is absent")
    path = input_root / source_file
    compressed = path.read_bytes()
    raw = decoder.decode(compressed)
    bnd = parse_bnd4(raw)
    files = bnd["files"]
    by_model_id: dict[int, list[dict[str, Any]]] = {}
    for entry in files:
        model_id = model_id_from_name(entry.get("name"))
        entry["model_id_from_name"] = model_id
        if model_id is not None:
            by_model_id.setdefault(model_id, []).append(entry)
    navmeshes = record["nva"]["sections"].get("0", {}).get("navmeshes", [])
    model_bindings = []
    for model_id in sorted({node["model_id"] for node in navmeshes if node["model_id"] >= 0}):
        matches = by_model_id.get(model_id, [])
        navmesh_matches = [entry for entry in matches if is_navmesh_hkx_name(entry.get("name"))]
        model_bindings.append(
            {
                "model_id": model_id,
                "nva_navmesh_count": sum(node["model_id"] == model_id for node in navmeshes),
                "matching_hkx_entry_indices": [entry["entry_index"] for entry in matches],
                "matching_hkx_names": [entry.get("name") for entry in matches],
                "matching_navmesh_hkx_entry_indices": [entry["entry_index"] for entry in navmesh_matches],
                "matching_navmesh_hkx_names": [entry.get("name") for entry in navmesh_matches],
                "binding_status": (
                    "exact_unique_hkx_filename_model_id"
                    if len(navmesh_matches) == 1
                    else "ambiguous_navmesh_hkx_filename_model_id"
                    if navmesh_matches
                    else "hkx_filename_model_id_missing"
                ),
                "routeable": False,
            }
        )
    return {
        "map_id": record["map_id"],
        "source_file": source_file,
        "source_sha256": sha256(path),
        "source_size": len(compressed),
        "bnd4": {key: value for key, value in bnd.items() if key != "files"},
        "files": files,
        "model_bindings": model_bindings,
        "status": {
            "hkx_entry_count": len(files),
            "hkx_tag0_count": sum(entry.get("inner_tag") == "TAG0" for entry in files),
            "nva_model_id_count": len(model_bindings),
            "nva_model_id_exact_unique_count": sum(
                row["binding_status"] == "exact_unique_hkx_filename_model_id" for row in model_bindings
            ),
            "nva_model_id_ambiguous_count": sum(
                row["binding_status"] == "ambiguous_navmesh_hkx_filename_model_id" for row in model_bindings
            ),
            "nva_model_id_missing_count": sum(
                row["binding_status"] == "hkx_filename_model_id_missing" for row in model_bindings
            ),
            "routeable_records": 0,
            "geometry_deserialized": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nva-index", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--oodle-dll", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    nva_path = args.nva_index.resolve()
    input_root = args.input_root.resolve()
    source = json.loads(nva_path.read_text(encoding="utf-8"))
    decoder = OodleKrak(args.oodle_dll)
    records = []
    errors = []
    for nva_record in source.get("records", []):
        try:
            records.append(build_record(nva_record, input_root, decoder))
        except Exception as exc:
            errors.append({"map_id": nva_record.get("map_id"), "error": str(exc)})
    output = {
        "schema": "elden-ring-local-nvmhktbnd-index@1",
        "source": {
            "nva_index": str(nva_path),
            "input_root": str(input_root),
            "oodle_dll": str(args.oodle_dll.resolve()),
            "snapshot_id": "elden-ring-local-snapshot-20260818",
            "read_only_snapshot": True,
        },
        "model": {
            "purpose": "native NVMHKT BND4/HKX geometry provenance for NVA ModelIDs",
            "geometry_deserialized": False,
            "player_walkability_validated": False,
            "routeable": False,
        },
        "status": {
            "nva_map_count": len(source.get("records", [])),
            "parsed_bnd4_record_count": len(records),
            "parse_error_count": len(errors),
            "hkx_entry_count": sum(row["status"]["hkx_entry_count"] for row in records),
            "hkx_tag0_count": sum(row["status"]["hkx_tag0_count"] for row in records),
            "nva_model_id_count": sum(row["status"]["nva_model_id_count"] for row in records),
            "nva_model_id_exact_unique_count": sum(
                row["status"]["nva_model_id_exact_unique_count"] for row in records
            ),
            "nva_model_id_ambiguous_count": sum(
                row["status"]["nva_model_id_ambiguous_count"] for row in records
            ),
            "nva_model_id_missing_count": sum(
                row["status"]["nva_model_id_missing_count"] for row in records
            ),
            "routeable_records": 0,
            "geometry_deserialized": False,
            "player_walkability_validated": False,
            "all_records_routeable_false": True,
        },
        "records": records,
        "errors": errors,
        "note": "BND4 and HKX entry provenance is exact. Polygon geometry is intentionally not deserialized or promoted to a walkable transition in this pass.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["status"], ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
