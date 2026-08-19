# Next Steps: Real-Map Path Planning & Navigation

**Language**: English · [中文](ROADMAP.zh-CN.md)

## Goal

Build a "real-map path planning and navigation" feature on top of the existing abstract topology node framework — a capability that is largely absent from the current community ecosystem: present the world of Elden Ring as an interactive map, and combine it with this project's unique conditional directed topology and fault-isolation abilities, so players can see **genuinely reachable routes** on the world map — including travel modes, one-way drops, elevators, sending gates and condition gates.

## Relationship to the existing framework

The abstract topology layer already provides:

- 938 semantic nodes (graces/entrances/bosses/lifts/teleports/key landmarks) with 1,601 conditional directed edges;
- per-record validation, quarantine and connected-component services (a local data failure never affects other regions);
- official Chinese display and Chinese search;
- region aggregate view with drill-down.

Real-map navigation is a leap in the **presentation layer**: bind abstract nodes to real map positions, draw directed edges as real routes on the map, and visualize conditions and one-way semantics.

## Phases

1. **Map base presentation**: present the game world as an interactive map (illustrative references to game maps and assets, see the presentation policy in [Data & Rights Statement](DISCLAIMER.md)).
2. **Node ↔ map position binding**: align abstract topology nodes with map coordinates (graces, entrances, lift endpoints, boss rooms, etc.).
3. **Real path drawing & navigation**: draw routes along genuinely reachable paths on the base map, overlaying travel modes, direction, layer changes and conditions; recompute live as the world state changes.
4. **Integration with existing capabilities**: reuse search, condition toggles, blocked explanations, fault isolation and official Chinese; support mobile and touch interactions.

## Milestones

- M1: base map presentation + node coordinate binding (all nodes and regions visible on the map).
- M2: single-route real-path drawing on the map (with one-way / elevator / teleport semantics).
- M3: live route recomputation and navigation under world-state switches.
- M4: multi-route comparison, deviation hints and coverage-gap visualization.

## Community presentation references

- Gamersky Elden Ring interactive map: https://www.gamersky.com/tools/map/eldenring/
- Elpwc Elden Ring map: https://www.elpwc.com/eldenringmap/
- Fextralife Elden Ring interactive map: https://eldenring.wiki.fextralife.com/Interactive_Map
