#!/usr/bin/env python3
"""Build independent formal-origin to abstract-map identity evidence.

The Compass records provide a copied game-local map identity and coordinate
for each grace.  A manual name/region/map binding is treated as exact formal
identity.  A name-only formal candidate is retained as a candidate and never
becomes a route origin.  This file is an origin-binding evidence layer; it
does not add traversal edges or alter the formal player graph.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT_DIR = ROOT / "data" / "v1" / "source-snapshots"
DEFAULT_LOCAL_POSITIONS = ROOT / "data" / "v1" / "entities" / "local-grace-positions.json"
DEFAULT_MANUAL_BINDINGS = ROOT / "data" / "v1" / "entities" / "named-grace-identity-bindings.json"
DEFAULT_FORMAL_GRAPH = ROOT / "data" / "v1" / "graph-v1.json"
DEFAULT_ABSTRACT_GRAPH = ROOT / "data" / "v1" / "entities" / "abstract-topology-route-graph.json"
DEFAULT_OUTPUT = ROOT / "data" / "v1" / "entities" / "abstract-origin-bindings.json"
MAP_PATTERN = re.compile(r"m\d+_\d+_\d+_\d+", re.IGNORECASE)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_compass_records(snapshot_dir: Path) -> tuple[list[dict[str, Any]], list[Path]]:
    paths = sorted(snapshot_dir.glob("elden-ring-compass-graces-*.json"))
    if not paths:
        raise FileNotFoundError(f"no Compass grace snapshots under {snapshot_dir}")
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for path in paths:
        payload = load_json(path)
        for row in payload.get("records", []):
            key = (str(row["map"]), int(row["bonfire_entity_id"]))
            if key in seen:
                raise ValueError(f"duplicate Compass grace identity: {key}")
            seen.add(key)
            records.append({**row, "source_snapshot": path.name})
    return records, paths


def formal_nodes(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["id"]: row
        for row in graph.get("nodes", [])
        if row.get("id")
    }


def build(
    compass_records: list[dict[str, Any]],
    snapshot_paths: list[Path],
    local_positions: dict[str, Any],
    manual_bindings: dict[str, Any],
    formal_graph: dict[str, Any],
    abstract_graph: dict[str, Any],
    source_paths: dict[str, Path],
) -> dict[str, Any]:
    formal_by_id = formal_nodes(formal_graph)
    manual_by_key = {
        (str(row["name"]), str(row["map"])): row
        for row in manual_bindings.get("records", [])
    }
    local_by_key = {
        (str(row["map_id"]), int(row["entity_id"])): row
        for row in local_positions.get("records", [])
    }
    abstract_map_ids = {
        row.get("mapId")
        for row in abstract_graph.get("nodes", [])
        if row.get("nodeType") == "abstract_map" and row.get("mapId")
    }
    records: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    local_identity_counts: Counter[str] = Counter()

    for row in compass_records:
        name = str(row["name"])
        map_id = str(row["map"])
        entity_id = int(row["bonfire_entity_id"])
        local = local_by_key.get((map_id, entity_id))
        local_status = "exact_local_grace_identity" if local else "missing_local_grace_identity"
        local_identity_counts[local_status] += 1
        manual = manual_by_key.get((name, map_id))
        candidates = [str(value) for value in row.get("formal_candidates", []) if value]
        formal_node_id: str | None = None
        if manual:
            formal_node_id = str(manual["formal_id"])
            binding_status = "exact_manual_formal_identity"
            if formal_node_id not in formal_by_id:
                binding_status = "invalid_manual_formal_identity"
        elif len(candidates) == 1:
            formal_node_id = candidates[0]
            binding_status = "candidate_name_map_identity"
        elif candidates:
            binding_status = "ambiguous_name_map_identity"
        else:
            binding_status = "unbound_formal_identity"
        if map_id not in abstract_map_ids:
            binding_status = f"{binding_status}_map_not_in_abstract_graph"
        exact = (
            binding_status == "exact_manual_formal_identity"
            and local_status == "exact_local_grace_identity"
            and map_id in abstract_map_ids
        )
        status_counts[binding_status] += 1
        records.append(
            {
                "id": f"abstract-origin:{map_id}:{entity_id}",
                "sourceSnapshot": row["source_snapshot"],
                "name": name,
                "region": row.get("region"),
                "formalNodeId": formal_node_id,
                "formalNodeKind": formal_by_id.get(formal_node_id, {}).get("kind") if formal_node_id else None,
                "formalCandidateIds": candidates,
                "originMapId": map_id,
                "originMapNodeId": f"abstract-map:{map_id}" if map_id in abstract_map_ids else None,
                "bonfireEntityId": entity_id,
                "position": row.get("position"),
                "sourceIdentity": row.get("source_identity"),
                "binding": {
                    "status": binding_status,
                    "bindingBasis": (
                        "manual_name_region_map_binding"
                        if manual
                        else "unique_source_formal_candidate_by_name"
                        if len(candidates) == 1
                        else "multiple_source_formal_candidates_by_name"
                        if candidates
                        else "no_source_formal_candidate"
                    ),
                    "manualBindingId": manual.get("formal_id") if manual else None,
                    "localIdentityStatus": local_status,
                    "abstractMapIdentityStatus": (
                        "exact_abstract_map_identity"
                        if map_id in abstract_map_ids
                        else "map_not_in_abstract_route_graph"
                    ),
                },
                "localIdentity": {
                    "status": local_status,
                    "mapId": local.get("map_id") if local else map_id,
                    "entityId": local.get("entity_id") if local else entity_id,
                    "instanceId": local.get("instance_id") if local else None,
                    "mapStudioLayer": local.get("map_studio_layer") if local else None,
                    "position": local.get("position") if local else None,
                },
                "abstractOriginRouteable": exact,
                "playerRouteable": False,
                "routeable": False,
            }
        )

    return {
        "schema": "elden-ring-reachability-map/abstract-origin-bindings@1",
        "status": "abstract_origin_identity_evidence_only",
        "model": {
            "originMeaning": "a formal grace node or a retained source identity candidate",
            "mapMeaning": "the exact source map identity associated with the grace record",
            "exactMeaning": "manual formal identity plus exact copied local grace identity and abstract map identity",
            "candidateMeaning": "source name/map candidate retained for audit but not accepted as an exact origin",
            "edgeMeaning": "none; this package does not create traversal edges",
            "continuousPhysics": False,
            "playerRouteable": False,
            "routeable": False,
        },
        "source": {
            "compassSnapshots": [
                {"file": path.name, "sha256": sha256(path)} for path in snapshot_paths
            ],
            "localGracePositions": {
                "file": str(source_paths["local_positions"].relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(source_paths["local_positions"]),
            },
            "manualBindings": {
                "file": str(source_paths["manual_bindings"].relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(source_paths["manual_bindings"]),
            },
            "formalGraph": {
                "file": str(source_paths["formal_graph"].relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(source_paths["formal_graph"]),
            },
            "abstractRouteGraph": {
                "file": str(source_paths["abstract_graph"].relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(source_paths["abstract_graph"]),
            },
        },
        "records": records,
        "stats": {
            "recordCount": len(records),
            "bindingStatusCounts": dict(sorted(status_counts.items())),
            "localIdentityStatusCounts": dict(sorted(local_identity_counts.items())),
            "exactAbstractOriginCount": sum(row["abstractOriginRouteable"] for row in records),
            "allPlayerRouteableFalse": all(not row["playerRouteable"] for row in records),
            "allRouteableFalse": all(not row["routeable"] for row in records),
        },
        "notes": [
            "Only exact_manual_formal_identity records are abstract origin anchors.",
            "Name-only candidates and ambiguous names remain searchable evidence and cannot start a formal route.",
            "The local grace identity is joined by exact map id plus bonfire entity id; no coordinate proximity is used.",
            "No record in this package creates or reverses a traversal edge.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=DEFAULT_SNAPSHOT_DIR)
    parser.add_argument("--local-positions", type=Path, default=DEFAULT_LOCAL_POSITIONS)
    parser.add_argument("--manual-bindings", type=Path, default=DEFAULT_MANUAL_BINDINGS)
    parser.add_argument("--formal-graph", type=Path, default=DEFAULT_FORMAL_GRAPH)
    parser.add_argument("--abstract-graph", type=Path, default=DEFAULT_ABSTRACT_GRAPH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    compass_records, snapshot_paths = load_compass_records(args.snapshot_dir)
    payload = build(
        compass_records,
        snapshot_paths,
        load_json(args.local_positions),
        load_json(args.manual_bindings),
        load_json(args.formal_graph),
        load_json(args.abstract_graph),
        {
            "local_positions": args.local_positions,
            "manual_bindings": args.manual_bindings,
            "formal_graph": args.formal_graph,
            "abstract_graph": args.abstract_graph,
        },
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(payload["stats"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
