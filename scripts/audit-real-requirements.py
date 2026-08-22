#!/usr/bin/env python3
"""Audit the 2026-08-21 real-requirements contract with hard failure gates.

This audit intentionally does not treat the 938-node formal route skeleton as
V1 completion.  It combines the player runtime projection, acquisitions,
endpoint bridge, native topology, origin identities, and game-mechanic data.
The generated report is suitable for the completion statement required by
chapter 12 of the local acceptance contract.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "v1"
ENTITIES = DATA / "entities"
DEFAULT_BROWSER_EVIDENCE = DATA / "v1" / "browser-player-closed-loop.json"
DEFAULT_CONTAINS = ENTITIES / "acquisition-contains-bindings.json"

REQUIRED_CATEGORIES = {
    "armor", "ash_of_war", "bell_bearing", "boss", "cookbook",
    "crystal_tear", "deathroot", "divine_tower", "dragon_heart",
    "enemy", "entrance", "evergaol", "fixed_message", "furnace_golem",
    "gesture", "ghost_glovewort", "golden_rune", "golden_seed",
    "grave_glovewort", "great_rune", "hero_rune", "incantation",
    "invader", "key_item", "map_fragment", "memory_stone", "merchant",
    "minor_erdtree", "multiplayer_item", "npc", "painting", "prayerbook",
    "puzzle", "remembrance", "rune_arc", "smithing_stone", "sorcery",
    "spirit_ash", "spirit_spring", "stone_sword_key", "teleport",
    "tool", "weapon",
}
ACQUIRABLE_KINDS = {"accessory", "armor", "ash_of_war", "item", "spell", "weapon"}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def gate(name: str, actual: Any, expected: Any, passed: bool, evidence: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "pass" if passed else "fail",
        "actual": actual,
        "expected": expected,
        "evidence": evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--milestone", choices=("beta", "v1"), default="v1")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--browser-evidence", type=Path, default=DEFAULT_BROWSER_EVIDENCE)
    parser.add_argument("--contains-bindings", type=Path, default=DEFAULT_CONTAINS)
    args = parser.parse_args()
    report_path = args.report or (
        DATA / "v1" / f"real-requirements-{args.milestone}-audit.json"
    )

    player = load(ENTITIES / "player-entity-index.json")
    acquisitions = load(ENTITIES / "acquisition-registry.json")
    bridge = load(ENTITIES / "acquisition-topology-bridge.json")
    contains = load(args.contains_bindings) if args.contains_bindings.is_file() else {}
    native = load(ENTITIES / "abstract-native-topology.json")
    origins = load(ENTITIES / "abstract-origin-bindings.json")
    reinforce = load(ENTITIES / "reinforce-catalog.json")
    graph = load(DATA / "graph-v1.json")
    incident_route_nodes = {
        endpoint
        for edge in graph.get("edges", [])
        for endpoint in (edge.get("from"), edge.get("to"))
        if endpoint
    }

    records = player.get("entities", [])
    ids = [record.get("id") for record in records]
    duplicate_ids = sorted(key for key, count in Counter(ids).items() if count > 1)
    category_counts = Counter(record.get("category") for record in records)
    missing_categories = sorted(REQUIRED_CATEGORIES - set(category_counts))

    acquirable = [record for record in records if record.get("kind") in ACQUIRABLE_KINDS]
    acquirable_without_relations = sorted(
        record["id"] for record in acquirable if not record.get("acquisitions")
    )
    formal_relation_count = sum(
        relation.get("topologyBinding", {}).get("status") == "routeable_anchor"
        for record in records
        for relation in record.get("acquisitions", [])
    )
    all_relation_count = sum(len(record.get("acquisitions", [])) for record in records)
    endpoint_count = sum(
        len(relation.get("endpointInstances", []))
        for record in records
        for relation in record.get("acquisitions", [])
    )
    searchable_name_missing = sorted(
        record["id"] for record in records
        if not any((record.get("name") or {}).get(language) for language in ("zh", "en"))
        and not record.get("aliases")
    )

    armor_reinforcement_relations = []
    for relation in reinforce.get("reinforcements", []):
        values = [str(relation.get(key, "")) for key in ("from", "to", "item", "material")]
        if any(value.startswith("armor_") for value in values):
            armor_reinforcement_relations.append(relation.get("id") or values)

    player_stats = player.get("stats", {})
    acquisition_stats = acquisitions.get("stats", {})
    bridge_stats = bridge.get("stats", {})
    native_stats = native.get("stats", {})
    origin_stats = origins.get("stats", {})
    contains_stats = contains.get("stats", {})

    # 5.5 containment layer: an endpoint with a proven exact map identity is
    # included inside the verified formal region; candidates, external scope,
    # and unresolved sources are never promoted by this layer.
    explicit_anchor_ids = {
        record.get("id")
        for record in bridge.get("records", [])
        if record.get("formalRouteAnchor", {}).get("routeNodeIds")
    }
    contained_anchor_ids = {
        binding.get("bridgeRecordId")
        for binding in contains.get("bindings", [])
        if binding.get("containsStatus") == "region_containment"
        and binding.get("routeNodeIds")
    }
    formal_anchor_ids = explicit_anchor_ids | contained_anchor_ids
    formal_anchor_endpoint_count = len(formal_anchor_ids)
    non_anchored_breakdown = Counter()
    for record in bridge.get("records", []):
        if (
            record.get("sourceClass") == "acquisition_relation"
            and record.get("id") not in formal_anchor_ids
        ):
            non_anchored_breakdown[str(record.get("abstractAnchor", {}).get("status"))] += 1
    browser_evidence = (
        load(args.browser_evidence) if args.browser_evidence.is_file() else {}
    )
    browser_entity = next(
        (
            record
            for record in records
            if record.get("id") == browser_evidence.get("entity", {}).get("canonicalId")
        ),
        None,
    )
    browser_dataset = browser_evidence.get("dataset", {})
    browser_entity_endpoint_count = sum(
        len(relation.get("endpointInstances", []))
        for relation in (browser_entity or {}).get("acquisitions", [])
    )
    package_manifest = load(DATA / "packages" / "manifest.json")
    browser_dataset_matches = (
        browser_dataset.get("playerEntityCount") == len(records)
        and browser_dataset.get("formalRouteNodeCount") == len(incident_route_nodes)
        and browser_dataset.get("formalRouteEdgeCount") == len(graph.get("edges", []))
        and browser_dataset.get("packageCount") == len(package_manifest.get("packages", []))
        and browser_entity is not None
        and browser_evidence.get("entity", {}).get("acquisitionRelationCount")
        == len(browser_entity.get("acquisitions", []))
        and browser_evidence.get("entity", {}).get("endpointInstanceCount")
        == browser_entity_endpoint_count
    )
    browser_closed_loop_passed = (
        browser_evidence.get("schema")
        == "elden-ring-reachability-map/browser-player-closed-loop@1"
        and browser_evidence.get("status") == "pass"
        and browser_evidence.get("searchEntity") is True
        and browser_evidence.get("selectAcquisition") is True
        and browser_evidence.get("selectOrigin") is True
        and browser_evidence.get("renderExecutableRoute") is True
        and browser_dataset_matches
    )

    beta_gates = [
        gate("runtime_entity_count_matches_projection", len(records), player_stats.get("entityCount"), len(records) == player_stats.get("entityCount"), "player-entity-index.json"),
        gate("duplicate_canonical_ids", len(duplicate_ids), 0, not duplicate_ids, "player-entity-index entities[].id"),
        gate("required_contract_categories_missing", missing_categories, [], not missing_categories, "chapter 4 category projection"),
        gate("published_entities_without_search_signifier", len(searchable_name_missing), 0, not searchable_name_missing, "name.zh/name.en/aliases"),
        gate("armor_reinforcement_relations", len(armor_reinforcement_relations), 0, not armor_reinforcement_relations, "reinforce-catalog.json"),
        gate("glovewort_reinforcement_relations", sum(1 for row in reinforce.get("reinforcements", []) if "glovewort" in json.dumps(row).lower()), "> 0", any("glovewort" in json.dumps(row).lower() for row in reinforce.get("reinforcements", [])), "reinforce-catalog.json"),
        gate("common_enemy_drop_relations", acquisition_stats.get("dropRelationCount", 0), "> 3", acquisition_stats.get("dropRelationCount", 0) > 3, "acquisition-registry stats"),
        gate("formal_acquisition_route_relations", formal_relation_count, "> 0", formal_relation_count > 0, "player projection relation topologyBinding"),
        gate("browser_player_closed_loop", browser_evidence.get("status", "missing"), "pass with matching current dataset", browser_closed_loop_passed, args.browser_evidence.relative_to(ROOT).as_posix() if args.browser_evidence.is_relative_to(ROOT) else str(args.browser_evidence)),
    ]

    coverage_gap_count = len(acquisitions.get("coverageGaps", []))
    topology_unbound_count = bridge_stats.get("unboundEndpointCount", 0)
    v1_gates = beta_gates + [
        gate("authoritative_source_coverage_gaps", coverage_gap_count, 0, coverage_gap_count == 0, "acquisition-registry coverageGaps"),
        gate("acquirable_entities_without_acquisition", len(acquirable_without_relations), 0, not acquirable_without_relations, "player entity acquisitions"),
        gate("unbound_or_unresolved_acquisition_endpoints", topology_unbound_count, 0, topology_unbound_count == 0, "acquisition-topology-bridge stats"),
        gate("candidate_map_endpoints", bridge_stats.get("abstractAnchorStatusCounts", {}).get("candidate_abstract_map_anchor", 0), 0, bridge_stats.get("abstractAnchorStatusCounts", {}).get("candidate_abstract_map_anchor", 0) == 0, "acquisition-topology-bridge stats"),
        gate("external_scope_endpoints", bridge_stats.get("abstractAnchorStatusCounts", {}).get("external_map_scope", 0), 0, bridge_stats.get("abstractAnchorStatusCounts", {}).get("external_map_scope", 0) == 0, "acquisition-topology-bridge stats"),
        gate("fixed_endpoints_without_formal_route_anchor", bridge_stats.get("acquisitionRelationEndpointCount", 0) - formal_anchor_endpoint_count, 0, bridge_stats.get("acquisitionRelationEndpointCount", 0) == formal_anchor_endpoint_count, "acquisition-topology-bridge formalRouteAnchorEndpointCount + acquisition-contains-bindings region_containment"),
        gate("maps_missing_native_topology", native_stats.get("missingNativeMapCount", 0), 0, native_stats.get("missingNativeMapCount", 0) == 0, "abstract-native-topology stats"),
        gate("legal_origins_without_exact_formal_identity", origin_stats.get("recordCount", 0) - origin_stats.get("exactAbstractOriginCount", 0), 0, origin_stats.get("recordCount", 0) == origin_stats.get("exactAbstractOriginCount", 0), "abstract-origin-bindings stats"),
    ]

    selected = beta_gates if args.milestone == "beta" else v1_gates
    failed = [item for item in selected if item["status"] == "fail"]
    report = {
        "schema": "elden-ring-reachability-map/real-requirements-audit@1",
        "contract": ".local-plans/2026-08-21-real-requirements-execution-and-acceptance.md",
        "milestone": args.milestone,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not failed else "fail",
        "summary": {
            "gateCount": len(selected),
            "passedGateCount": len(selected) - len(failed),
            "failedGateCount": len(failed),
            "runtimeEntityCount": len(records),
            "searchableEntityCount": len(records) - len(searchable_name_missing),
            "acquisitionRelationProjectionCount": all_relation_count,
            "endpointInstanceProjectionCount": endpoint_count,
            "formalAcquisitionRouteRelationCount": formal_relation_count,
            "formalRouteNodeCount": len(incident_route_nodes),
            "formalAnchorEndpointCount": formal_anchor_endpoint_count,
            "containmentRegionEndpointCount": len(contained_anchor_ids),
            "containmentUnresolvedEndpointCount": contains_stats.get(
                "containmentStatusCounts", {}
            ).get("region_unresolved", 0),
            "nonFormalAnchorBreakdown": dict(
                sorted(non_anchored_breakdown.items(), key=lambda item: (-item[1], item[0]))
            ),
            "coverageGapCount": coverage_gap_count,
            "unboundEndpointCount": topology_unbound_count,
            "acquirableEntityWithoutRelationCount": len(acquirable_without_relations),
        },
        "gates": selected,
        "samples": {
            "duplicateIds": duplicate_ids[:50],
            "missingCategories": missing_categories,
            "searchSignifierMissing": searchable_name_missing[:50],
            "acquirableWithoutRelations": acquirable_without_relations[:100],
            "armorReinforcementRelations": armor_reinforcement_relations[:50],
        },
        "limitations": [
            "Browser click acceptance is a separate dynamic gate.",
            "Reproducible two-build hash equality is a separate dynamic gate.",
            "Passing this audit never converts candidate evidence into a formal route.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"{args.milestone.upper()} acceptance: {report['status'].upper()} ({len(failed)} failed gates)")
    print(f"report: {report_path}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
