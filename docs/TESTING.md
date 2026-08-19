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
