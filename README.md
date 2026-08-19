# RUNE//PATH

**Language**: English · [中文](README.zh-CN.md)

An Elden Ring multi-plane topology route planner: a directed, conditional graph built from pinned online sources and verified against a local copy of the game data. Given the current world state it returns key node sequences, travel modes, one-way semantics, layer changes and condition notes.

## Quick start

```bash
python server.py --port 8105
# open http://127.0.0.1:8105/ in your browser
```

The first screen loads only the package manifest, the 13 data packages and route configuration; no local research indexes are loaded. The default example route is「黄金树大教堂 → 古兰桑克斯的雷电」(Erdtree Sanctuary → Bolt of Gransax).

## Usage

### 1. Plan a route

- **Origin / destination**: type a Chinese or English name in the search box on the left (official Chinese aliases work, e.g. "玛利喀斯", "史东薇尔正门", "黄金树大教堂"), then pick from the dropdown; the「⇅」button swaps them.
- **World state**: tick the conditions that match your progress (bosses defeated, keys, capital state, etc.). "Select all / clear all" toggles quickly.
- **Travel profile**: default is "Physical topology / no fast travel"; switch to "Normal flow / fast travel allowed" and tick "Map fast travel available" to travel between discovered graces.
- **Route preference**: balanced / fastest / low risk.
- Click「规划可达路线」(Plan route): the right panel shows a route card — each step lists the travel mode, direction (one-way drops are never reversed), layer change, required conditions, package version and evidence level.

### 2. Read the map

- **Default view is a region aggregate**: 122 region nodes (official Chinese names, node and grace counts) connected by dashed aggregate edges; **click a region to drill into its internal topology**, then use「← 返回全局」(back) to return.
- **Layer tabs**: surface / underground / legacy; route nodes stay visible on every layer.
- **Zoom and pan**: the wheel zooms around the mouse position; left-drag pans; the top-right buttons zoom/reset. On touch devices, pinch zooms and single-finger drag pans.
- **Zoom levels**: the far view shows only region names; zooming in reveals node labels and layer rows progressively.
- **Package status**: the right-hand "数据包状态与覆盖声明" panel lists the load state of all 13 packages, quarantined records and connected components; a local data failure only affects its own region.

### 3. Research console (development entry)

`http://127.0.0.1:8105/research.html` offers inspection views of the local research data and evidence chains; it is not part of the player route path.

## Documentation

| Document | Content |
|---|---|
| [Data & rights statement](docs/DISCLAIMER.md) | Fan project status, data sources and licenses, coordinate nature |
| [Package architecture & fault isolation](docs/ARCHITECTURE.md) | Framework/data decoupling, per-record validation, quarantine, acceptance |
| [Data scope & coverage](docs/DATA-COVERAGE.md) | V1.0 graph scale, coverage statement, 8 fixed E2E routes |
| [Official Chinese display](docs/CHINESE-LOCALIZATION.md) | FromSoftware Simplified-Chinese mapping rules and coverage |
| [Next steps](docs/ROADMAP.md) | Real-map path planning & navigation (interactive map + topology navigation) |
| [Testing & building](docs/TESTING.md) | Completeness verification, regressions, audits, rebuild commands |
| [Research layer](docs/RESEARCH-LAYER.md) | Local research evidence layer (technical details, not on the player path) |
