#!/usr/bin/env python3
"""Contract chapter 12 completion declaration — every required quantity assembled
from the current generated data, printed as the declaration artifact."""
import json, re, subprocess, sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "v1"

idx = json.loads((DATA / "entities" / "player-entity-index.json").read_text(encoding="utf-8"))
reg = json.loads((DATA / "entities" / "acquisition-registry.json").read_text(encoding="utf-8"))
br = json.loads((DATA / "entities" / "acquisition-topology-bridge.json").read_text(encoding="utf-8"))
g = json.loads((DATA / "graph-v1.json").read_text(encoding="utf-8"))
cb = json.loads((DATA / "entities" / "acquisition-contains-bindings.json").read_text(encoding="utf-8"))

ents = idx["entities"]
acq_total = 0
endpoint_total = 0
routeable_anchor = 0
# 10.1 base-game / Shadow of the Erdtree split.  SotE map instances use the
# m60-m69 prefix; an entity is classed by the maps of its acquisition
# endpoints and occurrences, so the split is mechanical and auditable.
DLC_MAP_RE = re.compile(r"^m6[0-9]_", re.I)
base_entities = set()
dlc_entities = set()
undetermined_entities = set()
for e in ents:
    maps = set()
    for acq in e.get("acquisitions", []):
        for ep in acq.get("endpointInstances", []):
            if ep.get("map"):
                maps.add(str(ep["map"]))
    for occ in e.get("occurrences", []):
        if occ.get("map"):
            maps.add(str(occ["map"]))
    if maps:
        if any(DLC_MAP_RE.match(m) for m in maps):
            dlc_entities.add(e["id"])
        if any(not DLC_MAP_RE.match(m) for m in maps):
            base_entities.add(e["id"])
    else:
        undetermined_entities.add(e["id"])
    acqs = e.get("acquisitions", [])
    acq_total += len(acqs)
    endpoint_total += sum(len(a.get("endpointInstances", [])) for a in acqs)
    if e.get("topology", {}).get("status") == "routeable_anchor":
        routeable_anchor += 1

dlc_only = len(dlc_entities - base_entities)
base_only = len(base_entities - dlc_entities)
dual = len(base_entities & dlc_entities)

declaration = {
    "schema": "elden-ring-reachability-map/release-declaration@1",
    "contract": ".local-plans/2026-08-21-real-requirements-execution-and-acceptance.md chapter 12",
    "currentCommit": subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip(),
    "generatedAt": "2026-08-23",
    "runtimeEntityCount": len(ents),
    "searchableEntityCount": len(ents),
    "baseGameEntityCount": base_only,
    "dlcOnlyEntityCount": dlc_only,
    "dualScopeEntityCount": dual,
    "mapUndeterminedEntityCount": len(undetermined_entities),
    "entityWithAcquisitionCount": sum(1 for e in ents if e.get("acquisitions")),
    "acquisitionRelationCount": len(reg["relations"]),
    "projectedAcquisitionRelationCount": acq_total,
    "endpointInstanceCount": endpoint_total,
    "formalRouteNodeCount": len([n for n in g["nodes"] if n.get("kind") == "grace"]),
    "formalRouteEdgeCount": len(g["edges"]),
    "formalAnchorEndpointCount": br["stats"].get("formalRouteAnchorEndpointCount", 0),
    "containmentRegionEndpointCount": cb["stats"].get("region_containment", 0) if "region_containment" in cb.get("stats", {}) else sum(1 for b in cb.get("bindings", []) if b.get("containsStatus") == "region_containment"),
    "coverageGapCount": len(reg.get("coverageGaps", [])),
    "unboundEndpointCount": br["stats"].get("unboundEndpointCount", 0),
    "candidateEndpointCount": br["stats"].get("abstractAnchorStatusCounts", {}).get("candidate_abstract_map_anchor", 0),
    "externalScopeEndpointCount": br["stats"].get("abstractAnchorStatusCounts", {}).get("external_map_scope", 0),
    "onlineSourceGapCount": len(reg.get("onlineSourceGaps", [])),
    "sellerUnresolvedRecordCount": len(reg.get("sellerUnresolvedRecords", [])),
    "serviceMenuRecordCount": len(reg.get("serviceMenuRecords", [])),
    "testRowExclusionCount": len(reg.get("testShopRowRecords", [])),
    "verifiedNoDropFactCount": len(reg.get("verifiedNoDropFacts", [])),
    "verifiedUnusedMapLotFactCount": len(reg.get("verifiedUnusedMapLotFacts", [])),
}
out = DATA / "v1" / "release-declaration.json"
out.write_text(json.dumps(declaration, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(declaration, ensure_ascii=False, indent=1))
print("\nDECLARATION WRITTEN:", out)
