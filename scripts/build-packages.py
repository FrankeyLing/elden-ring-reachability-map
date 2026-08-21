#!/usr/bin/env python3
"""Build independent region/state/bridge data packages from the formal V1 graph.

The formal graph (data/v1/graph.json) is mechanically split into packages so a
bad node, edge or region package can never take down the whole product:

  - region/state packages hold their own nodes, intra-package edges and the
    conditions those edges reference;
  - the bridge package holds every edge whose endpoints live in different
    packages (teleports, lifts, entrances, one-way drops, world-state switches);
  - every package is written as JSONL with one record per line, so a single
    corrupt record can be isolated without losing the rest of the package;
  - the manifest is the only file whose corruption skips an entire package,
    and it must never take down other packages.

Output: data/v1/packages/manifest.json + data/v1/packages/<id>.jsonl

Usage:
    python scripts/build-packages.py [--graph data/v1/graph.json] [--out data/v1/packages]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_PACKAGE = "elden-ring-package@1"
SCHEMA_MANIFEST = "elden-ring-manifest@1"

# Package ids are stable publication units. A node goes to exactly one package;
# the mapping below is mechanical (epoch > region > layer) and must not be
# changed casually, because package ids appear in released manifests.
PACKAGE_TITLES = {
    "surface-main-world": "主世界地表（宁姆格福/利耶尼亚/盖利德/亚坛/巨人山顶/化圣雪原等）",
    "underground": "地下世界（希芙拉河/安瑟尔河/诺克隆/深根底层/腐败湖/蒙格温王朝）",
    "royal-capital": "王城罗德尔（玛利喀斯前正常状态）",
    "ashen-capital": "灰烬王城（玛利喀斯后状态）",
    "shadow-realm": "《黄金树幽影》区域（幽影之地/影之塔/恩希斯城/塔之镇/米德拉宅邸等）",
    "farum-azula": "法姆·亚兹拉（逐渐崩毁的法姆·亚兹拉）",
    "haligtree": "米凯拉的圣树与艾布雷菲尔",
    "stormveil": "史东薇尔城",
    "raya-lucaria": "雷亚卢卡利亚魔法学院",
    "volcano-manor": "火山官邸",
    "caria-manor": "卡利亚城寨",
    "legacy-other": "其他遗迹与地牢（洞窟/墓地/英雄墓地/塔/监牢等）",
    "bridge": "跨区域桥接（传送/升降梯/入口/单向跳落/世界状态切换等跨包边）",
}

ROYAL_CAPITAL_REGIONS = {"王城罗德尔", "Leyndell, Royal Capital", "Capital Outskirts", "Subterranean Shunning-Grounds"}
FARUM_REGIONS = {"Crumbling Farum Azula", "逐渐崩毁的法姆·亚兹拉"}
HALIGTREE_REGIONS = {"Miquella's Haligtree", "米凯拉的圣树", "Elphael, Brace of the Haligtree"}
STORMVEIL_REGIONS = {"Stormveil Castle", "城的前方"}
RAYA_LUCARIA_REGIONS = {"Academy of Raya Lucaria", "Raya Lucaria Academy"}
VOLCANO_MANOR_REGIONS = {"Volcano Manor"}
CARIA_MANOR_REGIONS = {"Caria Manor", "卡利亚城寨"}
UNDERGROUND_EPOCHS = {
    "siofra_underground",
    "ainsel_underground",
    "deeproot_underground",
    "nokron_underground",
    "nokstella_underground",
    "mohgwyn_underground",
    "lake_of_rot_underground",
}
SHADOW_EPOCHS = {"shadow_realm", "shadow_realm_enir_ilim"}


def package_for_node(node: dict) -> str:
    """Assign a node to exactly one package (mechanical, deterministic)."""
    epoch = node.get("worldEpoch") or ""
    region = node.get("region") or ""
    layer = node.get("layer") or ""

    if epoch == "ashen_capital_post_maliketh":
        return "ashen-capital"
    if region in ROYAL_CAPITAL_REGIONS or epoch == "royal_capital_pre_maliketh":
        return "royal-capital"
    if epoch in SHADOW_EPOCHS:
        return "shadow-realm"
    if region in FARUM_REGIONS or epoch == "crumbling_farum_azula":
        return "farum-azula"
    if region in HALIGTREE_REGIONS or epoch == "haligtree_legacy":
        return "haligtree"
    if region in STORMVEIL_REGIONS:
        return "stormveil"
    if region in RAYA_LUCARIA_REGIONS:
        return "raya-lucaria"
    if region in VOLCANO_MANOR_REGIONS:
        return "volcano-manor"
    if region in CARIA_MANOR_REGIONS:
        return "caria-manor"
    if layer == "underground" or epoch in UNDERGROUND_EPOCHS:
        return "underground"
    if layer == "legacy":
        return "legacy-other"
    return "surface-main-world"


def build_packages(graph_path: Path, out_dir: Path) -> dict:
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = graph["nodes"]
    edges = graph["edges"]
    conditions = graph["conditions"]

    # 1. assign nodes (entity-layer nodes without a region are not part of the
    #    reachability packages; they live in the entity/acquisition registries)
    node_package: dict[str, str] = {}
    for node in nodes:
        if node.get("region") is None:
            continue
        node_package[node["id"]] = package_for_node(node)

    # 2. assign edges (intra stays, cross goes to bridge)
    package_edges: dict[str, list[dict]] = defaultdict(list)
    bridge_edges: list[dict] = []
    for edge in edges:
        from_pkg = node_package.get(edge["from"])
        to_pkg = node_package.get(edge["to"])
        if from_pkg is not None and from_pkg == to_pkg:
            package_edges[from_pkg].append(edge)
        else:
            # cross-package or dangling-edge endpoints: recorded in the bridge
            # package so the loader can quarantine them with a reason instead of
            # silently dropping the edge from the data model.
            bridge_edges.append(edge)

    # 3. conditions referenced per package
    condition_by_id = {c["id"]: c for c in conditions}
    def referenced_conditions(edge_list):
        ids = set()
        for edge in edge_list:
            ids.update(edge.get("requires") or [])
        return [condition_by_id[cid] for cid in sorted(ids) if cid in condition_by_id]

    # 4. write packages
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    source = {"file": str(graph_path), "version": graph.get("meta", {}).get("version", "unknown")}

    package_meta = {}
    for pkg_id in [*PACKAGE_TITLES.keys()]:
        pkg_nodes = [n for n in nodes if n.get("region") is not None and node_package.get(n["id"]) == pkg_id] if pkg_id != "bridge" else []
        pkg_edges = package_edges.get(pkg_id, []) if pkg_id != "bridge" else bridge_edges
        pkg_conditions = referenced_conditions(pkg_edges) if pkg_id != "bridge" else referenced_conditions(pkg_edges)

        regions = sorted({n.get("region", "") for n in pkg_nodes})
        layers = sorted({n.get("layer", "") for n in pkg_nodes})
        epochs = sorted({n.get("worldEpoch", "") for n in pkg_nodes})

        # cross-package dependencies: other packages this package's edges touch
        deps = set()
        for edge in pkg_edges:
            if node_package.get(edge["from"]) == pkg_id and node_package.get(edge["to"]) not in (None, pkg_id):
                deps.add(node_package[edge["to"]])
            if node_package.get(edge["to"]) == pkg_id and node_package.get(edge["from"]) not in (None, pkg_id):
                deps.add(node_package[edge["from"]])
        deps.discard(pkg_id)

        package_meta[pkg_id] = {
            "id": pkg_id,
            "title": PACKAGE_TITLES[pkg_id],
            "version": "1.0.0",
            "generatedAt": generated_at,
            "source": source,
            "coverage": {
                "nodeCount": len(pkg_nodes),
                "edgeCount": len(pkg_edges),
                "conditionCount": len(pkg_conditions),
                "regions": regions,
                "layers": layers,
                "epochs": epochs,
            },
            "crossPackageDependencies": sorted(deps),
            "isolatedRecordCount": 0,
            "knownGaps": [],
        }
        header = {
            "schema": SCHEMA_PACKAGE,
            "package": package_meta[pkg_id],
        }
        lines = [json.dumps(header, ensure_ascii=False)]
        for node in pkg_nodes:
            lines.append(json.dumps({"type": "node", "record": node}, ensure_ascii=False))
        for edge in pkg_edges:
            lines.append(json.dumps({"type": "edge", "record": edge}, ensure_ascii=False))
        for condition in pkg_conditions:
            lines.append(json.dumps({"type": "condition", "record": condition}, ensure_ascii=False))
        (out_dir / f"{pkg_id}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 5. manifest
    manifest = {
        "schema": SCHEMA_MANIFEST,
        "version": "1.0.0",
        "title": graph.get("meta", {}).get("title", "Online Verified V1"),
        "generatedAt": generated_at,
        "source": source,
        "defaults": {
            "origin": "grace_erdtree_sanctuary",
            "destination": "item_bolt_of_gransax",
            "conditions": ["royal_capital_pre_maliketh", "erdtree_sanctuary_activated"],
        },
        "packages": [
            {"id": pkg_id, "path": f"data/v1/packages/{pkg_id}.jsonl", **{k: v for k, v in meta.items() if k != "source"}}
            for pkg_id, meta in package_meta.items()
        ],
        "bridgePackageId": "bridge",
        "coverage": {
            "formalNodeCount": len(nodes),
            "formalRouteEdgeCount": len(edges),
            "conditionCount": len(conditions),
            "packageCount": len(package_meta),
            "bridgeEdgeCount": len(bridge_edges),
            "originalGameCoordinates": False,
            "localGameVerified": False,
            "isolatedRecordCount": 0,
            "statement": "Beta 仅以已加载数据包的范围提供路线；未覆盖区域、未加载包与隔离记录不冒充一比一。",
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "manifest": manifest,
        "nodeCounts": Counter(node_package.values()),
        "edgeCounts": Counter({p: len(package_edges.get(p, [])) for p in PACKAGE_TITLES}),
        "bridgeEdgeCount": len(bridge_edges),
        "conditionsInBridge": len(referenced_conditions(bridge_edges)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=Path("data/v1/graph.json"))
    parser.add_argument("--out", type=Path, default=Path("data/v1/packages"))
    args = parser.parse_args()

    result = build_packages(args.graph.resolve(), args.out.resolve())

    print("== package node/edge counts ==")
    for pkg_id in PACKAGE_TITLES:
        print(f"  {pkg_id:<22} nodes={result['nodeCounts'].get(pkg_id, 0):>5}  edges={result['edgeCounts'].get(pkg_id, 0):>5}")
    print(f"  bridge edges: {result['bridgeEdgeCount']}")
    print(f"  conditions referenced by bridge edges: {result['conditionsInBridge']}")
    print(f"  manifest: {args.out / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
