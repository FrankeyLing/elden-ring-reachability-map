#!/usr/bin/env python3
"""Build a read-only native NVA/Navmesh evidence index from a game snapshot.

This is deliberately an evidence layer, not a walkability solver.  It records
the native navmesh instances and native connector declarations after decoding
the game's Oodle/KRAK DCX wrapper.  It never reads the live game directory and
never marks a record routeable.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import re
import struct
from collections import Counter
from pathlib import Path
from typing import Any


MAP_RE = re.compile(r"^(m\d+_\d+_\d+_\d+)$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def unpack_from(fmt: str, data: bytes, offset: int) -> tuple[Any, ...]:
    return struct.unpack_from(fmt, data, offset)


def finite_vector(values: tuple[float, ...]) -> list[float]:
    return [float(value) for value in values]


def parse_section_header(raw: bytes, offset: int) -> tuple[int, int, int, int]:
    if offset + 16 > len(raw):
        raise ValueError(f"truncated NVA section header at {offset}")
    index, version, length, count = unpack_from("<4i", raw, offset)
    payload_start = offset + 16
    if length < 0 or payload_start + length > len(raw):
        raise ValueError(
            f"invalid NVA section length index={index} offset={offset} length={length}"
        )
    return index, version, length, count


def parse_navmeshes(raw: bytes, payload: bytes, version: int, count: int) -> list[dict[str, Any]]:
    if version not in {2, 3, 4}:
        raise ValueError(f"unsupported navmesh section version {version}")
    records: list[dict[str, Any]] = []
    if count == 0:
        return records
    if len(payload) % count != 0:
        raise ValueError(f"navmesh section length is not divisible by count: {len(payload)} / {count}")
    stride = len(payload) // count
    if stride < 96:
        raise ValueError(f"unsupported navmesh entry stride {stride}")
    cursor = 0
    connected_count_sentinel = 1075419545
    for navmesh_index in range(count):
        if cursor + 96 > len(payload):
            raise ValueError(f"truncated navmesh entry {navmesh_index}")
        position = unpack_from("<4f", payload, cursor)
        rotation = unpack_from("<4f", payload, cursor + 16)
        scale = unpack_from("<4f", payload, cursor + 32)
        name_id, model_id, face_data_index, unk_3c, face_count, connected_count = unpack_from(
            "<6i", payload, cursor + 48
        )
        gate_node_index, gate_node_count = unpack_from("<2h", payload, cursor + 72)
        unk_4c = unpack_from("<i", payload, cursor + 76)[0]
        connected_offset, zero_54, zero_58, zero_5c = unpack_from("<4i", payload, cursor + 80)
        entry_end = cursor + 96
        inline = connected_offset == 0xFF01
        connected: list[int] = []
        inline_values: list[int] = []
        # Elden Ring v8 stores a fixed 0x90-byte entry.  The final 12 ints are
        # present even when the header uses the game's no-links sentinels
        # (0xFF00/0xFF01 and 1075419545).  The older SoulsFormats model treats
        # only 0xFF01 as inline; retaining the fixed stride is necessary for
        # the current m60/m61 NVA files and avoids shifting every later entry.
        if stride >= 144:
            if entry_end + 48 > cursor + stride:
                raise ValueError(f"truncated fixed navmesh links {navmesh_index}")
            inline_values = list(unpack_from("<12i", payload, entry_end))
            if inline:
                connected = inline_values
            entry_end = cursor + stride
        elif connected_count > 0 and connected_count != connected_count_sentinel:
            if connected_offset < 0 or connected_offset + connected_count * 4 > len(raw):
                raise ValueError(
                    f"invalid navmesh link offset index={navmesh_index} offset={connected_offset} count={connected_count}"
                )
            connected = list(unpack_from(f"<{connected_count}i", raw, connected_offset))
            entry_end = cursor + stride
        else:
            entry_end = cursor + stride
        records.append(
            {
                "navmesh_index": navmesh_index,
                "position": finite_vector(position),
                "rotation": finite_vector(rotation),
                "scale": finite_vector(scale),
                "name_id": name_id,
                "model_id": model_id,
                "face_data_index": face_data_index,
                "face_count": face_count,
                "connected_navmeshes": connected,
                "connected_navmeshes_count": (
                    None if connected_count == connected_count_sentinel else connected_count
                ),
                "connected_navmeshes_count_raw": connected_count,
                "connected_navmeshes_inline": inline,
                "connected_navmeshes_offset": connected_offset,
                "connected_navmeshes_inline_payload": inline_values,
                "gate_node_index": gate_node_index,
                "gate_node_count": gate_node_count,
                "unknown_values": {
                    "unk_3c": unk_3c,
                    "unk_4c": unk_4c,
                    "connected_header_zero_54": zero_54,
                    "connected_header_zero_58": zero_58,
                    "connected_header_zero_5c": zero_5c,
                },
            }
        )
        cursor = entry_end
    return records


def parse_connectors(payload: bytes, count: int) -> list[dict[str, Any]]:
    if len(payload) < count * 32:
        raise ValueError("truncated connector section")
    return [
        {
            "connector_index": index,
            "main_name_id": values[0],
            "target_name_id": values[1],
            "navmesh_connection_count": values[2],
            "graph_connection_count": values[3],
            "navmesh_connection_index": values[4],
            "unknown_14": values[5],
            "graph_connection_index": values[6],
            "unknown_1c": values[7],
        }
        for index in range(count)
        for values in [unpack_from("<8i", payload, index * 32)]
    ]


def parse_navmesh_connections(payload: bytes, count: int) -> list[dict[str, int]]:
    if len(payload) < count * 16:
        raise ValueError("truncated navmesh connection section")
    return [
        {
            "face_index": values[0],
            "edge_index": values[1],
            "opposite_face_index": values[2],
            "opposite_edge_index": values[3],
        }
        for index in range(count)
        for values in [unpack_from("<4i", payload, index * 16)]
    ]


def parse_graph_connections(payload: bytes, count: int) -> list[dict[str, int]]:
    if len(payload) < count * 8:
        raise ValueError("truncated graph connection section")
    return [
        {"node_index": values[0], "opposite_node_index": values[1]}
        for index in range(count)
        for values in [unpack_from("<2i", payload, index * 8)]
    ]


def parse_level_connectors(payload: bytes, count: int) -> list[dict[str, Any]]:
    if len(payload) < count * 32:
        raise ValueError("truncated level connector section")
    records = []
    for index in range(count):
        offset = index * 32
        position = unpack_from("<4f", payload, offset)
        navmesh_id, unk_14, unk_18, unk_1c = unpack_from("<4i", payload, offset + 16)
        records.append(
            {
                "level_connector_index": index,
                "position": finite_vector(position),
                "navmesh_id": navmesh_id,
                "unknown_values": {"unk_14": unk_14, "unk_18": unk_18, "unk_1c": unk_1c},
            }
        )
    return records


def parse_gate_nodes(raw: bytes, payload: bytes, version: int, count: int) -> list[dict[str, Any]]:
    records = []
    cursor = 0
    for index in range(count):
        if cursor + 16 > len(payload):
            raise ValueError(f"truncated gate node {index}")
        position = unpack_from("<3f", payload, cursor)
        connected_navmesh_index, node_sub_id = unpack_from("<2h", payload, cursor + 12)
        costs: list[int] = []
        unknown_14 = None
        if version < 2:
            if cursor + 48 > len(payload):
                raise ValueError(f"truncated inline gate node costs {index}")
            costs = list(unpack_from("<16h", payload, cursor + 16))
            cursor += 48
        else:
            if cursor + 32 > len(payload):
                raise ValueError(f"truncated gate node header {index}")
            costs_count, unknown_14, costs_offset, zero = unpack_from("<4i", payload, cursor + 16)
            if costs_count > 0:
                if costs_offset < 0 or costs_offset + costs_count * 2 > len(raw):
                    raise ValueError(f"invalid gate cost offset {index}")
                costs = list(unpack_from(f"<{costs_count}h", raw, costs_offset))
            cursor += 32
        records.append(
            {
                "gate_node_index": index,
                "position": finite_vector(position),
                "connected_navmesh_index": connected_navmesh_index,
                "node_sub_id": node_sub_id,
                "neighbour_gate_node_costs": costs,
                "unknown_14": unknown_14,
            }
        )
    return records


def parse_nva(raw: bytes) -> dict[str, Any]:
    if len(raw) < 16 or raw[:4] != b"NVMA":
        raise ValueError("decompressed payload is not NVMA")
    version, declared_size, section_count = unpack_from("<3I", raw, 4)
    if declared_size != len(raw):
        raise ValueError(f"NVA file size mismatch declared={declared_size} actual={len(raw)}")
    sections: dict[int, dict[str, Any]] = {}
    offset = 16
    for _ in range(section_count):
        index, section_version, length, count = parse_section_header(raw, offset)
        payload_start = offset + 16
        payload = raw[payload_start : payload_start + length]
        section: dict[str, Any] = {
            "version": section_version,
            "length": length,
            "count": count,
        }
        if index == 0:
            section["navmeshes"] = parse_navmeshes(raw, payload, section_version, count)
        elif index == 4:
            section["connectors"] = parse_connectors(payload, count)
        elif index == 5:
            section["navmesh_connections"] = parse_navmesh_connections(payload, count)
        elif index == 6:
            section["graph_connections"] = parse_graph_connections(payload, count)
        elif index == 7:
            section["level_connectors"] = parse_level_connectors(payload, count)
        elif index == 8:
            section["gate_nodes"] = parse_gate_nodes(raw, payload, section_version, count)
        sections[index] = section
        offset = payload_start + length

    navmeshes = sections.get(0, {}).get("navmeshes", [])
    navmesh_connections = sections.get(5, {}).get("navmesh_connections", [])
    graph_connections = sections.get(6, {}).get("graph_connections", [])
    connectors = sections.get(4, {}).get("connectors", [])
    for connector in connectors:
        n_start = connector["navmesh_connection_index"]
        n_end = n_start + max(0, connector["navmesh_connection_count"])
        g_start = connector["graph_connection_index"]
        g_end = g_start + max(0, connector["graph_connection_count"])
        connector["navmesh_connections"] = navmesh_connections[n_start:n_end]
        connector["graph_connections"] = graph_connections[g_start:g_end]

    return {
        "version": version,
        "declared_size": declared_size,
        "section_count": section_count,
        "section_counts": {str(index): section.get("count", 0) for index, section in sections.items()},
        "sections": sections,
        "summary": {
            "navmesh_count": len(navmeshes),
            "connector_count": len(connectors),
            "navmesh_connection_count": len(navmesh_connections),
            "graph_connection_count": len(graph_connections),
            "level_connector_count": len(sections.get(7, {}).get("level_connectors", [])),
            "gate_node_count": len(sections.get(8, {}).get("gate_nodes", [])),
        },
    }


class OodleKrak:
    def __init__(self, dll_path: Path) -> None:
        self.dll_path = dll_path.resolve()
        self.dll = ctypes.WinDLL(str(self.dll_path))
        self.decompress = self.dll.OodleLZ_Decompress
        self.decompress.argtypes = [
            ctypes.c_void_p,
            ctypes.c_longlong,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_longlong,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_longlong,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_longlong,
            ctypes.c_int,
        ]
        self.decompress.restype = ctypes.c_longlong

    def decode(self, data: bytes) -> bytes:
        if len(data) < 0x4C or data[:4] != b"DCX\0":
            raise ValueError("not an Elden Ring DCX file")
        if data[0x24:0x28] != b"DCP\0" or data[0x28:0x2C] != b"KRAK":
            raise ValueError("NVA DCX is not the expected KRAK wrapper")
        uncompressed_size, compressed_size = unpack_from(">2I", data, 0x1C)
        compressed = data[0x4C : 0x4C + compressed_size]
        if len(compressed) != compressed_size:
            raise ValueError("truncated Oodle compressed payload")
        source = ctypes.create_string_buffer(compressed)
        output = (ctypes.c_ubyte * uncompressed_size)()
        result = self.decompress(
            source,
            len(compressed),
            output,
            uncompressed_size,
            1,
            0,
            0,
            None,
            0,
            None,
            None,
            None,
            0,
            3,
        )
        if result != uncompressed_size:
            raise ValueError(f"Oodle decode failed result={result} expected={uncompressed_size}")
        return bytes(output)


def derive_map_id(path: Path) -> str | None:
    for part in reversed(path.parts):
        if MAP_RE.match(part):
            return part
    match = MAP_RE.match(path.stem.removesuffix(".nva"))
    return match.group(1) if match else None


def build_record(path: Path, input_root: Path, decoder: OodleKrak) -> dict[str, Any]:
    data = path.read_bytes()
    raw = decoder.decode(data)
    nva = parse_nva(raw)
    map_id = derive_map_id(path)
    paired_hk = path.with_name(path.name.removesuffix(".nva.dcx") + ".nvmhktbnd.dcx")
    return {
        "map_id": map_id,
        "source_file": path.relative_to(input_root).as_posix(),
        "source_sha256": sha256(path),
        "source_size": len(data),
        "paired_nvmhktbnd": {
            "present": paired_hk.is_file(),
            "source_file": paired_hk.relative_to(input_root).as_posix() if paired_hk.is_file() else None,
            "size": paired_hk.stat().st_size if paired_hk.is_file() else None,
        },
        "nva": nva,
        "continuous_player_walkability": False,
        "physical_geometry_validated": False,
        "routeable": False,
        "verification_state": "local_nva_oodle_decoded_exact",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--oodle-dll", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    input_root = args.input_root.resolve()
    files = sorted(input_root.rglob("*.nva.dcx"))
    decoder = OodleKrak(args.oodle_dll)
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in files:
        try:
            records.append(build_record(path, input_root, decoder))
        except Exception as exc:  # Keep the complete inventory auditable.
            errors.append({"source_file": path.relative_to(input_root).as_posix(), "error": str(exc)})

    summary_counts = Counter()
    for record in records:
        for key, value in record["nva"]["summary"].items():
            summary_counts[key] += int(value)
    map_records = {record["map_id"] for record in records if record.get("map_id")}
    paired_count = sum(record["paired_nvmhktbnd"]["present"] for record in records)
    status = {
        "nva_file_count": len(files),
        "parsed_record_count": len(records),
        "parse_error_count": len(errors),
        "map_count": len(map_records),
        "maps_with_navmesh": sum(record["nva"]["summary"]["navmesh_count"] > 0 for record in records),
        "paired_nvmhktbnd_count": paired_count,
        **{f"total_{key}": value for key, value in sorted(summary_counts.items())},
        "routeable_records": 0,
        "all_records_routeable_false": all(record["routeable"] is False for record in records),
        "continuous_player_walkability": False,
        "physical_geometry_validated": False,
    }
    output = {
        "schema": "elden-ring-local-nva-navmesh-index@1",
        "source": {
            "input_root": str(input_root),
            "oodle_dll": str(decoder.dll_path),
            "oodle_dll_sha256": sha256(decoder.dll_path),
            "compression": "DCX/KRAK/OodleLZ_Decompress",
            "read_only_snapshot": True,
        },
        "model": {
            "purpose": "exact native NVA/Navmesh evidence for physical topology compilation",
            "abstract_relations_are_not_walk_edges": True,
            "continuous_player_walkability_is_not_claimed": True,
            "routeable": False,
        },
        "status": status,
        "records": records,
        "errors": errors,
        "note": "NVA connectors and navmesh instances are native evidence only. They are not promoted to player routes without geometry, direction, state guards, and validation evidence.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    print(args.output)
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
