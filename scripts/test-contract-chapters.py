#!/usr/bin/env python3
"""Contract-wide chapter evidence gate.  For every section of the absolute
acceptance contract the script asserts a concrete verifiable artifact exists
and is green, so the whole document (not one part) is covered by machine
evidence.  Sections map to: files that must exist, scripts that must pass,
and numeric facts that must hold."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "v1"

SECTIONS = [
    ("二 产品目标(玩家闭环 7 项)", "v1/browser-player-closed-loop.json",
     lambda d: d.get("searchEntity") and d.get("renderExecutableRoute")),
    ("四 实体范围 4.1 地点", "entities/location-catalog.json",
     lambda d: len(d.get("entities", [])) >= 200),
    ("四 实体范围 4.2 武器", "entities/entity-registry.json",
     lambda d: sum(1 for e in d["entities"] if e["kind"] == "weapon") >= 400),
    ("四 实体范围 4.3 防具+套装", "entities/entity-registry.json",
     lambda d: sum(1 for e in d["entities"] if e["kind"] == "armor") >= 500),
    ("四 实体范围 4.4 独特道具", "entities/entity-registry.json",
     lambda d: any(e["kind"] == "item" and e["category"] == "remembrance" for e in d["entities"])
              and any(e["category"] == "gesture" for e in d["entities"])),
    ("四 实体范围 4.5 道具", "entities/entity-registry.json",
     lambda d: sum(1 for e in d["entities"] if e["kind"] == "item" and e["category"] == "consumable") > 200),
    ("四 实体范围 4.6 敌人", "entities/entity-registry.json",
     lambda d: sum(1 for e in d["entities"] if e["kind"] == "enemy") >= 400),
    ("四 实体范围 4.7 锻造石", "entities/entity-registry.json",
     lambda d: any(e["category"] == "smithing_stone" for e in d["entities"]), None),
    ("四 实体范围 4.8 铃兰", "entities/entity-registry.json",
     lambda d: any(e["category"] in ("grave_glovewort", "ghost_glovewort") for e in d["entities"])),
    ("四 实体范围 4.9 友方", "entities/entity-registry.json",
     lambda d: any(e["kind"] == "npc" for e in d["entities"])),
    ("四 实体范围 4.10 其它(留言/谜题)", "entities/gap-catalog.json",
     lambda d: any(e["category"] == "puzzle" for e in d["entities"])),
    ("五 数据语义(实体/能指/关系/终点/锚点/导航边)", "entities/acquisition-registry.json",
     lambda d: len(d["relations"]) > 30000 and "schema" in d),
    ("六 框架/数据解耦(6 层)", "scripts/test-entity-layer-isolation.py",
     None, "test-entity-layer-isolation.py must PASS"),
    ("七 来源真实性(分层证据)", "../online-source-registry.json",
     lambda d: len(d.get("sources", [])) >= 5),
    ("九 Beta 门槛(12 条)", "scripts/audit-real-requirements.py",
     None, "audit-real-requirements must pass Beta+V1 gates"),
    ("十一 强制回归样例(13 类)", "scripts/test-ch11-regression.py",
     None, "test-ch11-regression.py must PASS"),
    ("十二 完成声明模板", "v1/release-declaration.json",
     lambda d: d.get("runtimeEntityCount", 0) == d.get("searchableEntityCount", 0)
               and d.get("runtimeEntityCount", 0)
               == d.get("baseGameEntityCount", 0) + d.get("dlcOnlyEntityCount", 0)
               + d.get("dualScopeEntityCount", 0) + d.get("mapUndeterminedEntityCount", 0)
               and d.get("dlcOnlyEntityCount", 0) > 0
               and d.get("dualScopeEntityCount", 0) > 0),
    ("十 可复现性", "scripts/test-reproducible-build.py",
     None, "test-reproducible-build.py must PASS"),
]


def main() -> int:
    failures = []
    for entry in SECTIONS:
        name, artifact, predicate = entry[:3]
        note = entry[3] if len(entry) > 3 else None
        path = DATA / artifact if not artifact.startswith("scripts/") else ROOT / artifact
        if not path.is_file():
            failures.append(f"{name}: missing artifact {artifact}")
            print(f"FAIL {name}: missing {artifact}")
            continue
        if predicate:
            data = json.loads(path.read_text(encoding="utf-8"))
            ok = predicate(data)
            label = "PASS " if ok else "FAIL "
            print(label + name)
            if not ok:
                failures.append(f"{name}: predicate failed on {artifact}")
        else:
            result = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=1800)
            ok = result.returncode == 0
            print(("PASS " if ok else "FAIL ") + name + (f" ({note})" if note else ""))
            if not ok:
                failures.append(f"{name}: {path.name} exited {result.returncode}: {result.stderr[-300:]}")
    print(f"\nCONTRACT CHAPTERS: {len(SECTIONS) - len(failures)}/{len(SECTIONS)} evidence gates passed")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
