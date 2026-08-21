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
- The independent abstract-topology candidate layer contains 1,351 map nodes, 1,347 native map-layer nodes, 1,347 map-to-layer relations, 2,092 map-level candidate edges, and 18 interaction-transport evidence records: 1,588 map declarations, 149 exact map endpoint pairs, 15 exact scripted-transport edges, and 340 scripted-transport records (79 using edge-declared map identity and 261 completed from the local map identity of their endpoint nodes). Of these, 2,079 edges have local identity-backed abstract connectivity and 13 remain unresolved candidates; all 18 interaction transports have an abstract destination identity while runtime conditions remain separate evidence. Fifty source maps are explicitly recorded as lacking native-layer evidence, alongside four external declared-map placeholders. Every record remains `routeable=false`; abstract connectivity is not a formal player route and does not enter the formal route graph.
- Candidate-layer endpoints are `/api/abstract-topology-candidates`, `/api/abstract-topology-candidates/map?map_id=...`, and `/api/abstract-topology-candidates/path?from_map_id=...&to_map_id=...`. The path endpoint returns an abstract identity-connection evidence trace, not a player route. Player-entity topology details expose related evidence under `abstractTopology`; `routeNodeIds` still contains formal route anchors only.
- The independent native abstract-topology package records coverage for all 1,347 maps: 997 have native partition files and 350 are missing; it contains 9,480 partition nodes, 5,884 exact connector declarations, and 11,646 partition-to-map-part identity bindings. Endpoints are `/api/abstract-native-topology` and `/api/abstract-native-topology/map?map_id=...`; every record remains `routeable=false`.
- The independent acquisition bridge contains 71,563 endpoint records: 66,893 acquisition-relation endpoints plus 4,670 coverage-gap endpoints. It publishes 32,231 exact abstract-layer anchors, 32,507 exact abstract-map anchors, 37 candidate map anchors, 1,999 external map-scope records, and 4,789 unbound or unresolved records. The bridge endpoints are `/api/acquisition-topology-bridge`, `/api/acquisition-topology-bridge/map?map_id=...`, and `/api/acquisition-topology-bridge/relation?relation_id=...`. The bridge is a searchable evidence projection only; all bridge records remain `routeable=false` and do not enter the formal route graph.
- Of those records, 3,713 local pickup endpoints have an exact semantic pickup-node anchor using the `ItemLotParam_map` row and map identity. This anchor is independently exposed from formal route eligibility and does not create a navigation edge.
- A further 348 enemy, dummy-enemy, merchant, quest-NPC, or boss-reward endpoints have an exact local-part semantic anchor using all five identity fields: map id, part name, instance id, entity id, and map-studio layer. 31,883 local endpoint identities have no corresponding local abstract part node yet, and 195 lack one or more identity fields; these records remain searchable and isolated.
- Separately, 32,231 enemy, dummy-enemy, merchant, quest-NPC, and boss-reward endpoint records have an exact `localEndpointIdentity` join to the copied local spawn-instance snapshot using those same five fields. This proves the source instance identity only; it is not an abstract movement node, does not claim walkability, and never creates a route edge. The 348 abstract-part matches are a stricter subset of this identity layer.
- This layer does not depend on continuous collision, navigation meshes, or physics simulation. Native map declarations, direction, state conditions, and endpoint blockers are retained as evidence; unresolved records cannot become reachable routes implicitly.
- The independent abstract route evidence package contains 1,351 map nodes, 1,347 layer nodes, and 2,097 directed identity-backed abstract connection edges. `/api/abstract-topology-route?from_map_id=...&to_map_id=...` returns a map/layer topology trace with condition warnings; it remains separate from the formal player route graph and reports `routeable=false` for player routing.
- `/api/catalog/player-entity-topology?id=...` additionally exposes `abstractRouteEvidence`, a bounded incident-edge projection for the maps attached to that entity's acquisition endpoints. It includes matching maps/layers, map-layer memberships, adjacent map ids, missing requested map ids, and incident edge counts; edge details are capped at 2,000. The projection is independently optional and keeps `abstractRouteable` separate from `playerRouteable=false` and `routeable=false`, so a broken evidence package cannot invalidate entity search or acquisition data.
- `/api/catalog/player-entity-abstract-route?id=...&from_map_id=...` performs a single abstract-graph search from a supplied origin map and reports exact acquisition target-map reachability, endpoint references, path evidence, and separate candidate/external/unresolved/unbound counts. `target_map_id=...` narrows the query. This is an abstract map trace, not a continuous walk route or formal player route.
- `abstract-origin-bindings.json` contains 419 copied Compass grace identities joined by exact map id plus bonfire entity id to the local grace-position snapshot: 39 exact manual formal-origin bindings, 376 name/map candidates, 2 ambiguous candidates, and 2 unbound formal identities. `/api/catalog/player-entity-abstract-route` accepts `from_node_id=...` only for the 39 exact records; all other origin states return an explicit blocker and remain searchable evidence.
- Canonical weapon coverage preserves the local parameter equipment family on the existing 562 weapon entities: 399 melee, 19 bow, 9 crossbow, 3 ballista, 20 staff, 12 sacred seal, 85 shield, 8 torch, 2 hand-to-hand, and 5 perfume weapons. These are family properties and query aliases, not duplicate entities or fabricated acquisition records.
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
