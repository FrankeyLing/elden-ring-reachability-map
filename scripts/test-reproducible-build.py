#!/usr/bin/env python3
"""Rebuild the published data plane twice and compare stable identities.

Timestamps and JSON formatting are deliberately excluded.  Chapter 10.7
requires canonical ids, relation identities, package membership, and coverage
statistics to remain identical across builds from the same pinned snapshots.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "v1"

def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def snapshot() -> dict[str, Any]:
    graph = load(DATA / "graph-v1.json")
    player = load(DATA / "entities" / "player-entity-index.json")
    acquisitions = load(DATA / "entities" / "acquisition-registry.json")
    bridge = load(DATA / "entities" / "acquisition-topology-bridge.json")
    contains = load(DATA / "entities" / "acquisition-contains-bindings.json")
    manifest = load(DATA / "packages" / "manifest.json")
    return {
        "graphNodeIds": sorted(node["id"] for node in graph.get("nodes", [])),
        "graphEdgeIds": sorted(edge["id"] for edge in graph.get("edges", [])),
        "graphRelationIds": sorted(relation["id"] for relation in graph.get("relations", [])),
        "graphCoverage": graph.get("coverage", {}),
        "playerEntityIds": sorted(record["id"] for record in player.get("entities", [])),
        "playerRelationIds": sorted(
            (record["id"], relation["id"])
            for record in player.get("entities", [])
            for relation in record.get("acquisitions", [])
        ),
        "playerStats": player.get("stats", {}),
        "acquisitionRelationIds": sorted(
            relation["id"] for relation in acquisitions.get("relations", [])
        ),
        "acquisitionCoverageGaps": acquisitions.get("coverageGaps", []),
        "acquisitionSourceExclusions": acquisitions.get("sourceExclusions", []),
        "acquisitionStats": acquisitions.get("stats", {}),
        "acquisitionBridgeStats": bridge.get("stats", {}),
        "containsBindingsStats": contains.get("stats", {}),
        "packageMembership": sorted(
            (entry["id"], entry.get("nodeCount"), entry.get("edgeCount"))
            for entry in manifest.get("packages", [])
        ),
    }


def build() -> None:
    current_acquisitions = load(DATA / "entities" / "acquisition-registry.json")
    current_pickups = load(DATA / "entities" / "pickup-location-bindings.json")
    current_event_rewards = load(DATA / "entities" / "event-reward-bindings.json")
    current_talk_rewards = load(DATA / "entities" / "talk-item-lot-bindings.json")
    current_quest_rewards = load(DATA / "entities" / "quest-reward-bindings.json")
    param_dir = current_acquisitions.get("built_from", {}).get("param_dir")
    msb_dir = current_pickups.get("built_from", {}).get("msb_dir")
    event_sources = current_event_rewards.get("builtFrom", {})
    talk_sources = current_talk_rewards.get("builtFrom", {})
    quest_sources = current_quest_rewards.get("builtFrom", {})
    if not param_dir or not Path(param_dir).is_dir():
        raise RuntimeError(f"pinned parameter snapshot unavailable: {param_dir}")
    if not msb_dir or not Path(msb_dir).is_dir():
        raise RuntimeError(f"pinned parsed MapStudio snapshot unavailable: {msb_dir}")
    required_event_sources = {
        "parsedEmevd": event_sources.get("parsedEmevd"),
        "semanticReferences": event_sources.get("semanticReferences"),
        "emedf": event_sources.get("emedf"),
        "eventFlags": event_sources.get("eventFlags"),
    }
    for source_name, source_path in required_event_sources.items():
        if not source_path or not Path(source_path).exists():
            raise RuntimeError(f"pinned event source unavailable ({source_name}): {source_path}")
    talk_dir = talk_sources.get("talkEsdPython")
    if not talk_dir or not Path(talk_dir).is_dir():
        raise RuntimeError(f"pinned Talk ESD source unavailable: {talk_dir}")
    quest_source = quest_sources.get("externalSource")
    if not quest_source or not Path(quest_source).is_file():
        raise RuntimeError(f"pinned quest source unavailable: {quest_source}")
    commands = [
        [sys.executable, "scripts/build-entity-registry.py", "--param-dir", param_dir],
        [sys.executable, "scripts/build-gesture-acquisition-bindings.py", "--param-dir", param_dir],
        [sys.executable, "scripts/build-tutorial-unlock-bindings.py", "--param-dir", param_dir],
        [
            sys.executable,
            "scripts/build-talk-item-lot-bindings.py",
            "--talk-dir",
            talk_dir,
            "--param-dir",
            param_dir,
        ],
        [
            sys.executable,
            "scripts/build-event-reward-bindings.py",
            "--parsed-emevd",
            required_event_sources["parsedEmevd"],
            "--semantic-references",
            required_event_sources["semanticReferences"],
            "--emedf",
            required_event_sources["emedf"],
            "--param-dir",
            param_dir,
            "--event-flags",
            required_event_sources["eventFlags"],
        ],
        [sys.executable, "scripts/build-equivalent-map-instances.py", "--maps-dir", msb_dir],
        [
            sys.executable,
            "scripts/build-pickup-bindings.py",
            "--msb-dir",
            msb_dir,
            "--param-dir",
            param_dir,
        ],
        # The first acquisition pass regenerates local NPC entities used by the
        # quest-name resolver.  Rebuild quest evidence from that registry, then
        # rebuild acquisitions so the new quest relations enter the product.
        [sys.executable, "scripts/build-acquisition-registry.py", "--param-dir", param_dir],
        [
            sys.executable,
            "scripts/build-quest-reward-bindings.py",
            "--quest-source",
            quest_source,
        ],
        [sys.executable, "scripts/build-acquisition-registry.py", "--param-dir", param_dir],
        [
            sys.executable,
            "scripts/build-reinforce-catalog.py",
            "--param-dir",
            param_dir,
        ],
        [sys.executable, "scripts/build-v1-graph.py"],
        [sys.executable, "scripts/build-graph-integration.py"],
        [
            sys.executable,
            "scripts/build-local-map-coverage-classification.py",
            "--coverage",
            "data/v1/entities/local-nva-coverage-audit.json",
            "--nva",
            "data/v1/entities/local-nva-navmesh-index.json",
            "--maps-dir",
            msb_dir,
            "--output",
            "data/v1/entities/local-map-coverage-classification.json",
        ],
        [sys.executable, "scripts/build-abstract-native-topology.py"],
        [sys.executable, "scripts/build-acquisition-topology-bridge.py"],
        [
            sys.executable,
            "scripts/audit-acquisition-topology-bridge.py",
            "--input",
            "data/v1/entities/acquisition-topology-bridge.json",
            "--acquisitions",
            "data/v1/entities/acquisition-registry.json",
        ],
        [sys.executable, "scripts/build-contains-bindings.py"],
        [sys.executable, "scripts/build-player-entity-index.py"],
        [sys.executable, "scripts/build-packages.py", "--graph", "data/v1/graph-v1.json", "--out", "data/v1/packages"],
        [sys.executable, "scripts/audit-packages.py", "--graph", "data/v1/graph-v1.json"],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f"build command failed ({result.returncode}): {' '.join(command)}")


def main() -> int:
    build()
    first = snapshot()
    first_digest = digest(first)
    build()
    second = snapshot()
    second_digest = digest(second)
    if first != second:
        for key in sorted(first):
            if first[key] != second[key]:
                print(
                    f"DIFF {key}: {digest(first[key])} != {digest(second[key])}",
                    file=sys.stderr,
                )
    assert first == second, f"non-deterministic stable projection: {first_digest} != {second_digest}"
    print("PASS reproducible two-build stable projection")
    print(f"  sha256={first_digest}")
    print(f"  nodes={len(first['graphNodeIds'])} edges={len(first['graphEdgeIds'])} relations={len(first['graphRelationIds'])}")
    print(f"  entities={len(first['playerEntityIds'])} projectedAcquisitions={len(first['playerRelationIds'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
