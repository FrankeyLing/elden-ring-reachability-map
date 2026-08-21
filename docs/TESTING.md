# Testing & Building

**Language**: English · [中文](TESTING.zh-CN.md)

```bash
# V1.0 completeness verification (local declarations → region reachability
# closure; exits with code 1 when it does not pass)
python scripts/build-v1-graph.py

# 8 E2E route regressions (real HTTP server + framework engine)
node scripts/e2e-route-regression.mjs

# Fault-isolation tests: zero data / single package / bad node / dangling
# edge / unknown condition / bad line / corrupt package / missing bridge /
# duplicate id / minimal blocked explanation
node scripts/test-fault-isolation.mjs

# Player entity query regressions: glovewort/smithing search, canonicalization,
# multiple acquisition relations and acquisition-to-topology bridge
python scripts/test-player-entity-query.py

# Release tracking policy: generated large JSON stays out of Git and is
# injected from the manifest during release.
python release.py --check
python release.py

# Isolated shop repair queue: one evidence record per unresolved purchase gap;
# no named seller or guessed endpoint may leak into the queue
python scripts/build-shop-gap-catalog.py
python scripts/audit-shop-gap-catalog.py

# Direct entity-to-map abstract topology query is covered by the same
# regression: exact target path, multi-target summary, and no-route isolation.

# Acquisition endpoint bridge: every acquisition relation and retained
# coverage-gap endpoint is isolated, map/layer/semantic-part anchors are
# audited, and no bridge record is promoted to a route
python scripts/build-acquisition-topology-bridge.py
python scripts/audit-acquisition-topology-bridge.py --input data/v1/entities/acquisition-topology-bridge.json --acquisitions data/v1/entities/acquisition-registry.json

# Independent abstract map/layer route evidence graph. This never enters the
# formal player route graph and does not perform collision or physics checks.
python scripts/build-abstract-topology-route-graph.py
python scripts/audit-abstract-topology-route-graph.py --input data/v1/entities/abstract-topology-route-graph.json

# Formal-origin to abstract-map identity evidence; candidate origins remain
# blockers and never become formal route origins.
python scripts/build-abstract-origin-bindings.py
python scripts/audit-abstract-origin-bindings.py

# Entity-layer fault isolation: one malformed record is quarantined while the
# remaining entity projection stays usable
python scripts/test-entity-layer-isolation.py

# Package integrity audit (split keeps every edge, no dangling/duplicates)
python scripts/audit-packages.py --graph data/v1/graph-v1.json

# Rebuild the packages from the V1.0 graph (mechanical split, reproducible)
python scripts/build-packages.py --graph data/v1/graph-v1.json --out data/v1/packages

# Official Chinese mapping audit (uncovered list + field completeness)
python scripts/audit-zh-mapping.py --graph data/v1/graph-v1.json

# Rebuild the official Chinese mapping (requires regenerating the bilingual
# FMG index first)
python scripts/build-official-fmg-index.py --msg-root <snapshot>/extracted/msg-all --oodle-dll <snapshot>/runtime/oo2core_6_win64.dll --output data/v1/entities/official-fmg-bilingual-index.json
python scripts/build-official-zh-mapping.py --graph data/v1/graph-v1.json

# Rebuild the local authoritative map-name table (map-file place-name
# identifiers → official text)
python scripts/build-local-map-names.py

# Datamine grace positions from the local MSBE copy (model AEG099_060)
python scripts/build-local-grace-positions.py

# Rebuild canonical equipment families and player query projection
python scripts/build-entity-registry.py --param-dir <snapshot>/extracted/param-json
python scripts/build-acquisition-registry.py --param-dir <snapshot>/extracted/param-json
python scripts/build-player-entity-index.py
python scripts/test-player-entity-query.py
