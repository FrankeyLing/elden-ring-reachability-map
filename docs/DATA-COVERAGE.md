# Data Scope & Coverage Statement (V1.0)

**Language**: English · [中文](DATA-COVERAGE.zh-CN.md)

- **938 nodes**: 604 graces (the full official grace catalog of 418, with 192 newly added and wired into the region network), entrances, bosses, lifts, teleports and key landmarks.
- **1,601 directed edges**: online cross-checked edges + 18 local-declaration bridge edges (closing cross-region gaps) + 4 manually verified connections (Ashen Capital exits) + 384 official-grace intra-region bridge edges.
- **1 weakly connected component**: the whole node set is connected within the network.
- 177 state conditions; the Royal Capital / Ashen Capital states are mutually exclusive.
- Authoritative region-resolution chain: map-file place-name identifiers → official text place names (incl. DLC: Belurat Tower Settlement / Theatre of the Divine Beast / Scaduview), tile major-region index, and one-hop neighbor voting for unnamed grid maps.

## Coverage statement

- Formal graph coverage: 938 nodes (604 graces), 1,601 verified directed edges, 177 state conditions, 1 weakly connected component.
- Packages: `surface-main-world` / `underground` / `royal-capital` / `ashen-capital` / `shadow-realm` / `farum-azula` / `haligtree` / `stormveil` / `raya-lucaria` / `volcano-manor` / `caria-manor` / `legacy-other` / `bridge`.
- Coordinates are for the abstract layout only, not original game XYZ; cost/risk are relative units, not measured minutes.
- The local research graph (29,144 nodes / 7,976 candidate edges) is an evidence warehouse, not on the player path; development entry: `/research.html`.
- Bridge and intra-region bridge edges carry `local_declared` / `catalog_grace` tags with evidence notes; they are not claimed as verified walkable routes.

## Completeness verification (V1.0 acceptance gate)

All 7,976 local reachability declarations (1,588 MSBE cross-map declarations, 149 exact endpoint pairs, 355 EMEVD warps, 5,884 NVA connectors) map 100% to semantic regions; all 85 main-region declared pairs and 112 sub-region declared pairs have reachable paths (0 gaps); the remaining 6,198 are same-map declarations. Verification report: `data/v1/v1/coverage-audit.json`; rebuild commands in [Testing & building](TESTING.md).

## Fixed E2E routes (phase-7 regression)

| # | Route | Segments | Key semantics |
|---|---|---|---|
| 1 | Erdtree Sanctuary → Bolt of Gransax | 5 | exit → elevator → one-way drop → pickup |
| 2 | Stormveil Main Gate → Godrick the Grafted | 5 | legacy interior, vertical route, boss approach |
| 3 | Volcano Manor entrance → Rykard | 5 | hidden route, boss completion, sending gate |
| 4 | Tempest-Facing Balcony → Maliketh | 8 | floating rocks, rooftop, boss state |
| 5 | Haligtree Canopy → Malenia | 9 | vertical route, elevators, scarlet-rot roots |
| 6 | Siofra Well Depths → Dragonkin Soldier | 5 | underground path, elevator, sending gate |
| 7 | Royal Capital / Ashen Capital exclusivity | — | mutually exclusive world states |
| 8 | DLC Shadow Keep gate plaza → Storehouse 7F | 3 | elevator vertical route |
