# Package Architecture & Fault Isolation

**Language**: English · [中文](ARCHITECTURE.zh-CN.md)

The framework and the data are fully decoupled: the formal graph (938 nodes / 1,601 edges / 177 conditions) is mechanically split into 12 region/state packages plus 1 bridge package, published under `data/v1/packages/`.

- Every package is JSONL with one record per line; a corrupt single record isolates only that line, a fully invalid package is skipped, and other packages are never affected.
- The bridge package holds only cross-package edges; when it is missing, every connected component keeps working internally.
- `framework.js` is the source-agnostic framework layer: per-record validation, quarantine, connected components, search, conditional routing, minimal blocked-condition explanation and diagnostics.
- A bad node isolates that node and its directly dependent edges; a dangling edge isolates only that edge; an unknown condition puts only the referencing edge into "condition unknown"; duplicate ids keep the first published record.

## Release acceptance (mapped to section 10 of the recovery plan)

All framework-behavior and player-flow checks pass: zero-data startup; single-package usability; bad nodes / dangling edges / corrupt packages / missing bridge all fail locally only; unknown conditions affect only referencing edges; the default example route succeeds on first screen; text search for origin/destination (with Chinese aliases); blocked explanations list only relevant missing conditions; one-way drops are never reversed; the two capital states stay mutually exclusive; route steps show entrance/layer/mode/package version/evidence level; no research data loads by default; the real browser shows no project errors; the page states its coverage and quarantine explicitly.
