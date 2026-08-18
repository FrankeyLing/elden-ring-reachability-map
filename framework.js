/* RouteFramework — source-agnostic package loader, per-record isolation,
 * active graph store, connected components, search, conditional routing and
 * minimal blocked-condition explanation.
 *
 * Contract (see scripts/build-packages.py):
 *   - manifest:      elden-ring-manifest@1   (JSON)
 *   - package:       elden-ring-package@1    (JSONL, one record per line)
 *
 * Failure boundaries (the framework never throws on data problems):
 *   - zero data:                  store is empty, routes return null, UI shows zero-data state
 *   - one bad node:               that node and its directly dependent edges are quarantined
 *   - one dangling edge:          that edge is quarantined
 *   - unknown condition:          referencing edges become condition-unknown (not passable)
 *   - duplicate node/edge id:     the first published record wins, later ones are quarantined
 *   - one bad record line:        that line is quarantined, the rest of the package loads
 *   - one corrupt package file:   that package is skipped, others still load
 *   - missing bridge package:     each connected component keeps working internally
 *
 * The framework knows no concrete source (no MapForGoblins, no local MSBE/EMEVD,
 * no specific region). Every source must produce the same package contract.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.RouteFramework = api;
})(typeof self !== "undefined" ? self : globalThis, function () {
  "use strict";

  const MANIFEST_SCHEMA = "elden-ring-manifest@1";
  const PACKAGE_SCHEMA = "elden-ring-package@1";

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function conditionLabel(store, id) {
    const condition = store.conditions.get(id);
    return condition ? condition.label : id;
  }

  function validateNode(node, packageId) {
    if (!isPlainObject(node)) return { ok: false, reason: "record is not an object" };
    const id = node.id;
    if (typeof id !== "string" || !id.trim()) {
      return { ok: false, reason: "node id is missing or not a string" };
    }
    const issues = [];
    if (typeof node.label !== "string" || !node.label.trim()) {
      issues.push("missing display label; using id as fallback");
    }
    return { ok: true, issues };
  }

  function validateEdge(edge, packageId) {
    if (!isPlainObject(edge)) return { ok: false, reason: "record is not an object" };
    if (typeof edge.from !== "string" || !edge.from.trim()) {
      return { ok: false, reason: "edge from is missing or not a string" };
    }
    if (typeof edge.to !== "string" || !edge.to.trim()) {
      return { ok: false, reason: "edge to is missing or not a string" };
    }
    const issues = [];
    if (edge.id === undefined || edge.id === null) issues.push("edge id missing; generated");
    if (edge.cost === undefined || edge.cost === null || Number.isNaN(Number(edge.cost))) {
      issues.push("missing cost; defaulted to 1");
    }
    if (edge.risk === undefined || edge.risk === null || Number.isNaN(Number(edge.risk))) {
      issues.push("missing risk; defaulted to 0");
    }
    return { ok: true, issues };
  }

  function validateCondition(condition, packageId) {
    if (!isPlainObject(condition)) return { ok: false, reason: "record is not an object" };
    const id = condition.id;
    if (typeof id !== "string" || !id.trim()) {
      return { ok: false, reason: "condition id is missing or not a string" };
    }
    const issues = [];
    if (typeof condition.label !== "string" || !condition.label.trim()) {
      issues.push("missing condition label; using id as fallback");
    }
    return { ok: true, issues };
  }

  function parsePackageText(text) {
    /* JSONL: header line (schema + package meta) then one record per line.
     * A bad line is isolated, never fatal for the rest of the package. */
    const lines = text.split(/\r?\n/);
    let header = null;
    const records = [];
    const badLines = [];
    lines.forEach((line, index) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      let payload;
      try {
        payload = JSON.parse(trimmed);
      } catch (error) {
        badLines.push({ line: index + 1, error: String(error && error.message || error) });
        return;
      }
      if (isPlainObject(payload) && payload.schema === PACKAGE_SCHEMA) {
        header = payload;
        return;
      }
      if (isPlainObject(payload) && typeof payload.type === "string" && isPlainObject(payload.record)) {
        records.push(payload);
      } else {
        badLines.push({ line: index + 1, error: "record without {type, record} envelope" });
      }
    });
    return { header, records, badLines };
  }

  function createStore() {
    const store = {
      /* published state */
      manifest: null,
      manifestError: null,
      packages: new Map(),        // packageId -> {id, version, title, status, meta, quarantined: []}
      nodes: new Map(),           // nodeId -> node record (active graph)
      edges: new Map(),           // edgeId -> edge record (active graph)
      conditions: new Map(),      // conditionId -> condition record
      quarantine: [],             // [{kind, packageId, reason, record, line}]
      defaults: { origin: null, destination: null, conditions: [] },

      /* ---- manifest / package ingestion ---- */

      loadManifest(payload) {
        this.manifest = null;
        this.manifestError = null;
        this.packages.clear();
        if (!isPlainObject(payload)) {
          this.manifestError = "manifest is not an object";
          return { ok: false, error: this.manifestError };
        }
        if (payload.schema !== MANIFEST_SCHEMA) {
          this.manifestError = `unsupported manifest schema: ${payload.schema}`;
          return { ok: false, error: this.manifestError };
        }
        this.manifest = payload;
        if (isPlainObject(payload.defaults)) {
          this.defaults = {
            origin: payload.defaults.origin || null,
            destination: payload.defaults.destination || null,
            conditions: Array.isArray(payload.defaults.conditions) ? payload.defaults.conditions.slice() : [],
          };
        }
        for (const entry of payload.packages || []) {
          if (!isPlainObject(entry) || typeof entry.id !== "string" || !entry.id) continue;
          this.packages.set(entry.id, {
            id: entry.id,
            version: entry.version || "unknown",
            title: entry.title || entry.id,
            status: "pending",
            meta: entry,
            quarantined: [],
          });
        }
        return { ok: true, packageCount: this.packages.size };
      },

      /* Validate and merge one package. Returns a report; never throws. */
      loadPackage(payload) {
        const report = {
          packageId: null,
          ok: false,
          validNodes: 0,
          validEdges: 0,
          validConditions: 0,
          quarantined: [],
          skipped: false,
          error: null,
        };
        if (!isPlainObject(payload) || payload.schema !== PACKAGE_SCHEMA || !isPlainObject(payload.package)) {
          report.error = "package envelope invalid";
          return report;
        }
        const packageId = payload.package.id;
        report.packageId = packageId;
        const meta = this.packages.get(packageId);
        if (!meta) {
          report.error = `package ${packageId} not declared in manifest`;
          return report;
        }
        const { records, badLines, header } = parsePackageText(
          payload.rawText !== undefined ? payload.rawText : JSON.stringify(payload)
        );
        if (!header) {
          /* the package file itself is unreadable (no valid header line):
           * skip the whole package, never touch other packages */
          report.error = "package file has no valid header (file-level corruption)";
          for (const bad of badLines) {
            this.quarantine.push({ kind: "record-line", packageId, reason: `unparseable line: ${bad.error}`, line: bad.line });
          }
          return report;
        }
        for (const bad of badLines) {
          this.quarantine.push({ kind: "record-line", packageId, reason: `unparseable line: ${bad.error}`, line: bad.line });
          report.quarantined.push({ kind: "record-line", line: bad.line, reason: bad.error });
        }
        const quarantinedIds = new Set();
        for (const entry of records) {
          const record = entry.record;
          const kind = entry.type;
          if (kind === "node") {
            const verdict = validateNode(record, packageId);
            if (!verdict.ok) {
              quarantinedIds.add(record.id);
              this.quarantine.push({ kind: "node", packageId, reason: verdict.reason, record });
              report.quarantined.push({ kind: "node", id: record.id, reason: verdict.reason });
              continue;
            }
            if (this.nodes.has(record.id)) {
              this.quarantine.push({ kind: "node", packageId, reason: "duplicate node id; first published record wins", record });
              report.quarantined.push({ kind: "node", id: record.id, reason: "duplicate node id" });
              continue;
            }
            const node = Object.assign({}, record);
            if (!node.label) node.label = node.id;
            if (verdict.issues.length) node.degraded = (node.degraded || []).concat(verdict.issues);
            node.packageId = packageId;
            this.nodes.set(node.id, node);
            report.validNodes += 1;
          } else if (kind === "edge") {
            const verdict = validateEdge(record, packageId);
            if (!verdict.ok) {
              this.quarantine.push({ kind: "edge", packageId, reason: verdict.reason, record });
              report.quarantined.push({ kind: "edge", id: record.id, reason: verdict.reason });
              continue;
            }
            if (quarantinedIds.has(record.from) || quarantinedIds.has(record.to)) {
              this.quarantine.push({ kind: "edge", packageId, reason: "endpoint was quarantined in this package", record });
              report.quarantined.push({ kind: "edge", id: record.id, reason: "endpoint quarantined" });
              continue;
            }
            if (record.id !== undefined && this.edges.has(record.id)) {
              this.quarantine.push({ kind: "edge", packageId, reason: "duplicate edge id; first published record wins", record });
              report.quarantined.push({ kind: "edge", id: record.id, reason: "duplicate edge id" });
              continue;
            }
            const edge = Object.assign({}, record);
            if (edge.cost === undefined || edge.cost === null) edge.cost = 1;
            if (edge.risk === undefined || edge.risk === null) edge.risk = 0;
            if (edge.id === undefined || edge.id === null) edge.id = `${packageId}:${edge.from}:${edge.to}:${report.validEdges}`;
            if (verdict.issues.length) edge.degraded = (edge.degraded || []).concat(verdict.issues);
            edge.packageId = packageId;
            /* unknown-condition marking is deferred to reconcileConditions(),
             * because conditions of this or later packages may not be loaded
             * yet while this edge record is processed. */
            this.edges.set(edge.id, edge);
            report.validEdges += 1;
          } else if (kind === "condition") {
            const verdict = validateCondition(record, packageId);
            if (!verdict.ok) {
              this.quarantine.push({ kind: "condition", packageId, reason: verdict.reason, record });
              report.quarantined.push({ kind: "condition", id: record.id, reason: verdict.reason });
              continue;
            }
            if (this.conditions.has(record.id)) {
              /* duplicate condition definitions are merged as no-ops; the
               * first published label wins, no quarantine needed */
              continue;
            }
            const condition = Object.assign({}, record);
            if (!condition.label) condition.label = condition.id;
            condition.packageId = packageId;
            this.conditions.set(condition.id, condition);
            report.validConditions += 1;
          }
        }
        report.ok = true;
        meta.status = "loaded";
        meta.loadedAt = new Date().toISOString();
        meta.nodeCount = report.validNodes;
        meta.edgeCount = report.validEdges;
        return report;
      },

      /* Mark a package as failed at the transport/parse level (HTTP error,
       * unparseable whole file). Only that package is affected. */
      markPackageFailed(packageId, reason) {
        const meta = this.packages.get(packageId);
        if (!meta) return { ok: false, error: `package ${packageId} not declared in manifest` };
        meta.status = "failed";
        meta.failedReason = String(reason || "load failed");
        this.quarantine.push({ kind: "package", packageId, reason: meta.failedReason });
        return { ok: true };
      },

      /* Register a condition defined outside any package (e.g. the fast-travel
       * rule shipped with route profiles). Edges referencing it become
       * passable again once it is registered. */
      registerCondition(condition) {
        if (!isPlainObject(condition) || typeof condition.id !== "string" || !condition.id) return false;
        this.conditions.set(condition.id, Object.assign({ label: condition.id, packageId: "profiles" }, condition));
        /* edges previously marked condition-unknown for this id are unblocked */
        return this.reconcileConditions();
      },

      /* Reconcile condition-unknown flags after all packages (and any
       * externally registered conditions) are in. An edge referencing a
       * condition that is still undefined stays in the graph but is not
       * passable until the condition is defined. */
      reconcileConditions() {
        let marked = 0;
        for (const edge of this.edges.values()) {
          const unknownConditions = (edge.requires || []).filter((id) => !this.conditions.has(id));
          if (unknownConditions.length) {
            edge.conditionUnknown = unknownConditions;
            marked += 1;
          } else {
            delete edge.conditionUnknown;
          }
        }
        return marked;
      },

      /* Re-check edges whose endpoints must exist in the *active* graph.
       * Called after all packages were attempted. Only edges from loaded
       * packages are kept; dangling ones go to the quarantine. */
      finalizeDanglingEdges() {
        this.reconcileConditions();
        const dangling = [];
        for (const [edgeId, edge] of this.edges) {
          if (!this.nodes.has(edge.from) || !this.nodes.has(edge.to)) {
            this.edges.delete(edgeId);
            dangling.push({ kind: "edge", packageId: edge.packageId, reason: "dangling endpoint after all packages loaded", record: edge });
          }
        }
        for (const item of dangling) {
          this.quarantine.push(item);
          const meta = this.packages.get(item.packageId);
          if (meta) meta.quarantined.push(item);
        }
        return dangling.length;
      },

      /* ---- active graph queries ---- */

      hasData() {
        return this.nodes.size > 0 && this.edges.size > 0;
      },

      node(id) {
        return this.nodes.get(id) || null;
      },

      activeNodeList() {
        return [...this.nodes.values()];
      },

      activeEdgeList() {
        return [...this.edges.values()];
      },

      condition(id) {
        return this.conditions.get(id) || null;
      },

      connectedComponents() {
        const adjacency = new Map();
        for (const edge of this.edges.values()) {
          if (!adjacency.has(edge.from)) adjacency.set(edge.from, []);
          if (!adjacency.has(edge.to)) adjacency.set(edge.to, []);
          adjacency.get(edge.from).push(edge.to);
          adjacency.get(edge.to).push(edge.from);
        }
        const components = [];
        const visited = new Set();
        for (const nodeId of this.nodes.keys()) {
          if (visited.has(nodeId)) continue;
          const memberIds = [];
          const queue = [nodeId];
          visited.add(nodeId);
          while (queue.length) {
            const current = queue.pop();
            memberIds.push(current);
            for (const next of adjacency.get(current) || []) {
              if (!visited.has(next)) {
                visited.add(next);
                queue.push(next);
              }
            }
          }
          const members = memberIds.map((id) => this.nodes.get(id));
          const graces = members.filter((node) => node.kind === "grace" || node.isGraceAnchor === true).length;
          const entrances = members.filter((node) => node.kind === "entrance" || node.kind === "lift" || node.kind === "teleport").length;
          components.push({
            id: `component-${components.length + 1}`,
            nodeCount: members.length,
            graceCount: graces,
            entranceCount: entrances,
            regions: [...new Set(members.map((node) => node.region).filter(Boolean))].slice(0, 12),
            sampleNodeId: memberIds[0],
          });
        }
        return components.sort((a, b) => b.nodeCount - a.nodeCount);
      },

      /* Register search aliases (product data, not framework knowledge).
       * aliasMap: { "中文别名": ["english keyword", ...] } — a node matches
       * when every query token matches either the raw token or one of its
       * aliases against id/label/region/floor. */
      registerAliases(aliasMap) {
        this._aliases = new Map();
        for (const [key, values] of Object.entries(aliasMap || {})) {
          const normalizedKey = String(key).trim().toLowerCase();
          if (!normalizedKey) continue;
          this._aliases.set(normalizedKey, values.map((value) => String(value).toLowerCase()));
        }
        return this;
      },

      search(query, limit = 200) {
        const normalized = String(query || "").trim().toLowerCase();
        if (!this.hasData()) return [];
        if (!normalized) {
          /* empty query returns popular kinds first (graces) */
          const nodes = this.activeNodeList();
          const rank = { grace: 0, boss: 1, target: 2, entrance: 3, lift: 4, teleport: 5, junction: 6, state: 7, transition: 8 };
          return nodes
            .sort((a, b) => (rank[a.kind] ?? 9) - (rank[b.kind] ?? 9) || a.label.localeCompare(b.label, "zh-CN"))
            .slice(0, limit)
            .map((node) => this._searchResult(node));
        }
        const tokens = normalized.split(/\s+/).filter(Boolean);
        const tokenCandidates = tokens.map((token) => {
          const candidates = new Set([token]);
          if (this._aliases?.has(token)) {
            for (const value of this._aliases.get(token)) candidates.add(value);
          }
          /* substring alias support: 搜索"史东薇尔正门"也能命中别名"史东薇尔" */
          if (this._aliases) {
            for (const [key, values] of this._aliases) {
              if (key.length > 1 && token.includes(key)) {
                for (const value of values) candidates.add(value);
              }
            }
          }
          return [...candidates];
        });
        const scored = [];
        for (const node of this.nodes.values()) {
          const haystack = `${node.id} ${node.label} ${node.region || ""} ${node.floor || ""}`.toLowerCase();
          if (!tokenCandidates.every((candidates) => candidates.some((candidate) => haystack.includes(candidate)))) continue;
          let score = 0;
          if (node.label.toLowerCase().includes(normalized)) score += 4;
          if (node.id.includes(normalized)) score += 3;
          if ((node.region || "").toLowerCase().includes(normalized)) score += 1;
          scored.push({ node, score });
        }
        scored.sort((a, b) => b.score - a.score || a.node.label.localeCompare(b.node.label, "zh-CN"));
        return scored.slice(0, limit).map((entry) => this._searchResult(entry.node));
      },

      _searchResult(node) {
        return {
          id: node.id,
          label: node.label,
          kind: node.kind || "other",
          region: node.region || "",
          layer: node.layer || "",
          floor: node.floor || "",
          isGrace: node.kind === "grace" || node.isGraceAnchor === true,
          packageId: node.packageId || null,
        };
      },

      /* ---- routing ---- */

      edgeIsAvailable(edge, conditions) {
        if (edge.routeable === false) return false;
        if (edge.conditionUnknown && edge.conditionUnknown.length) return false;
        return (edge.requires || []).every((id) => conditions.has(id));
      },

      /* Returns {nodes, edges, score} or null. */
      route(originId, destinationId, conditionIds, options = {}) {
        if (!this.hasData()) return null;
        const conditions = new Set(conditionIds || []);
        const nodes = this.nodes;
        if (!nodes.has(originId) || !nodes.has(destinationId)) return null;
        if (originId === destinationId) {
          return { nodes: [originId], edges: [], score: 0, time: 0, risk: 0 };
        }

        const dynamicFastTravel = Boolean(options.dynamicFastTravel);
        const fastTravelRuleId = options.fastTravelRuleId;
        const fastTravelAllowed = dynamicFastTravel && fastTravelRuleId && conditions.has(fastTravelRuleId);

        const distances = new Map();
        const previous = new Map();
        const queue = new Set(nodes.keys());
        for (const id of nodes.keys()) distances.set(id, Number.POSITIVE_INFINITY);
        distances.set(originId, 0);

        const outgoing = new Map();
        for (const edge of this.edges.values()) {
          if (!outgoing.has(edge.from)) outgoing.set(edge.from, []);
          outgoing.get(edge.from).push(edge);
        }

        while (queue.size) {
          let current = null;
          let currentDistance = Number.POSITIVE_INFINITY;
          for (const id of queue) {
            const distance = distances.get(id);
            if (distance < currentDistance) {
              current = id;
              currentDistance = distance;
            }
          }
          if (!current || current === destinationId) break;
          queue.delete(current);

          const candidates = outgoing.get(current) || [];
          if (fastTravelAllowed && (nodes.get(current).kind === "grace" || nodes.get(current).isGraceAnchor)) {
            for (const [targetId, target] of nodes) {
              if (targetId === current) continue;
              if (!(target.kind === "grace" || target.isGraceAnchor)) continue;
              candidates.push({
                id: `dynamic-fast-travel:${current}:${targetId}`,
                from: current,
                to: targetId,
                mode: "地图快速旅行（目标赐福需已发现）",
                cost: 1,
                risk: 0,
                direction: "teleport",
                transitionType: "map_fast_travel",
                requires: [fastTravelRuleId],
                sourceEvidence: [],
                verificationState: "online_cross_checked",
                dynamic: true,
                packageId: "dynamic",
                note: "规划层动态边；不写入正式数据包，不代表玩家已经激活目标赐福。",
                tags: ["fast_travel", "profile_only", "conditional"],
              });
            }
          }
          for (const edge of candidates) {
            if (!this.edgeIsAvailable(edge, conditions)) continue;
            if (!queue.has(edge.to)) continue;
            const edgeScore = Number(edge.cost) + Number(edge.risk || 0) * (options.riskWeight || 2.0);
            const candidate = currentDistance + edgeScore;
            if (candidate < distances.get(edge.to)) {
              distances.set(edge.to, candidate);
              previous.set(edge.to, { nodeId: current, edge });
            }
          }
        }

        if (!previous.has(destinationId)) return null;

        const pathNodes = [];
        const pathEdges = [];
        let cursor = destinationId;
        while (cursor !== originId) {
          pathNodes.unshift(cursor);
          const step = previous.get(cursor);
          if (!step) return null;
          pathEdges.unshift(step.edge);
          cursor = step.nodeId;
        }
        pathNodes.unshift(originId);
        return {
          nodes: pathNodes,
          edges: pathEdges,
          score: distances.get(destinationId),
          time: pathEdges.reduce((sum, edge) => sum + Number(edge.cost || 0), 0),
          risk: pathEdges.reduce((sum, edge) => sum + Number(edge.risk || 0), 0),
        };
      },

      /* ---- blocked explanation (minimal relevant conditions) ---- */

      /* Finds the path from origin to destination that needs the fewest
       * additional conditions (ties broken by normal cost). Returns the edge
       * list of that path or null when no path exists even with every
       * condition granted. */
      _minBlockerPath(originId, destinationId, conditionIds, options = {}) {
        const conditions = new Set(conditionIds || []);
        const nodes = this.nodes;
        const outgoing = new Map();
        for (const edge of this.edges.values()) {
          if (!outgoing.has(edge.from)) outgoing.set(edge.from, []);
          outgoing.get(edge.from).push(edge);
        }
        const weights = new Map();
        const previous = new Map();
        const queue = new Set(nodes.keys());
        for (const id of nodes.keys()) weights.set(id, [Number.POSITIVE_INFINITY, Number.POSITIVE_INFINITY]);
        weights.set(originId, [0, 0]);

        while (queue.size) {
          let current = null;
          let best = [Number.POSITIVE_INFINITY, Number.POSITIVE_INFINITY];
          for (const id of queue) {
            const weight = weights.get(id);
            if (weight[0] < best[0] || (weight[0] === best[0] && weight[1] < best[1])) {
              best = weight;
              current = id;
            }
          }
          if (!current || current === destinationId) break;
          queue.delete(current);
          for (const edge of outgoing.get(current) || []) {
            if (!queue.has(edge.to)) continue;
            if (edge.routeable === false) continue;
            const missing = (edge.requires || []).filter((id) => !conditions.has(id)).length;
            const edgeCost = Number(edge.cost || 1) + Number(edge.risk || 0) * (options.riskWeight || 2.0);
            const candidate = [weights.get(current)[0] + missing, weights.get(current)[1] + edgeCost];
            if (candidate[0] < weights.get(edge.to)[0] || (candidate[0] === weights.get(edge.to)[0] && candidate[1] < weights.get(edge.to)[1])) {
              weights.set(edge.to, candidate);
              previous.set(edge.to, { nodeId: current, edge });
            }
          }
        }
        if (!previous.has(destinationId)) return null;
        const pathEdges = [];
        let cursor = destinationId;
        while (cursor !== originId) {
          const step = previous.get(cursor);
          if (!step) return null;
          pathEdges.unshift(step.edge);
          cursor = step.nodeId;
        }
        return pathEdges;
      },

      /* Returns a categorized explanation of why a route cannot be planned. */
      explainBlocked(originId, destinationId, conditionIds, options = {}) {
        if (!this.hasData()) {
          return { category: "no-data", message: "当前没有已加载地图数据", missingConditions: [] };
        }
        const origin = this.nodes.get(originId);
        const destination = this.nodes.get(destinationId);
        if (!origin) {
          return { category: "missing-origin", message: `起点「${originId}」不在已加载数据包中`, missingConditions: [] };
        }
        if (!destination) {
          return { category: "missing-destination", message: `终点「${destinationId}」不在已加载数据包中`, missingConditions: [] };
        }
        if (originId === destinationId) return { category: "same-node", message: "起点与终点相同", missingConditions: [] };

        const direct = this.route(originId, destinationId, conditionIds, options);
        if (direct) return { category: "ok", message: null, missingConditions: [] };

        /* find a feasible path with every condition granted */
        const relaxed = this._minBlockerPath(originId, destinationId, [...this.conditions.keys()], options);
        if (!relaxed) {
          const components = this.connectedComponents();
          const originComponent = components.find((component) => component.sampleNodeId === originId)
            || components.find((component) => this._componentContains(component, originId));
          const destinationComponent = components.find((component) => this._componentContains(component, destinationId));
          if (originComponent && destinationComponent && originComponent.id !== destinationComponent.id) {
            const bridge = this.packages.get(this.manifest?.bridgePackageId);
            const bridgeMissing = !bridge || bridge.status !== "loaded";
            return {
              category: "cross-component",
              message: bridgeMissing
                ? `「${origin.label}」与「${destination.label}」位于不同连通分量，且跨区桥接数据包尚未加载；请先加载桥接数据包。`
                : `「${origin.label}」与「${destination.label}」位于不同连通分量；当前已加载数据中未收录两者之间的连接。`,
              missingConditions: [],
              originComponent: originComponent.id,
              destinationComponent: destinationComponent.id,
            };
          }
          return {
            category: "no-route",
            message: `当前已加载数据中不存在从「${origin.label}」到「${destination.label}」的路线。`,
            missingConditions: [],
          };
        }

        /* minimal blocker path exists but requires conditions */
        const missingIds = new Set();
        for (const edge of relaxed) {
          for (const id of edge.requires || []) {
            if (!conditionIds.includes(id)) missingIds.add(id);
          }
          if (edge.conditionUnknown) {
            for (const id of edge.conditionUnknown) missingIds.add(id);
          }
        }
        const missingConditions = [...missingIds].map((id) => {
          const condition = this.conditions.get(id);
          return {
            id,
            label: condition ? condition.label : id,
            hint: condition ? condition.hint || "" : "条件定义缺失；该边处于条件未知状态。",
            defined: Boolean(condition),
          };
        });
        return {
          category: "conditions",
          message: `「${origin.label}」到「${destination.label}」在满足以下条件后可达：`,
          missingConditions,
        };
      },

      _componentContains(component, nodeId) {
        const sample = this.nodes.get(component.sampleNodeId);
        if (!sample) return false;
        const adjacency = new Map();
        for (const edge of this.edges.values()) {
          if (!adjacency.has(edge.from)) adjacency.set(edge.from, []);
          adjacency.get(edge.from).push(edge.to);
          if (!adjacency.has(edge.to)) adjacency.set(edge.to, []);
          adjacency.get(edge.to).push(edge.from);
        }
        const visited = new Set();
        const queue = [component.sampleNodeId];
        while (queue.length) {
          const current = queue.pop();
          if (current === nodeId) return true;
          if (visited.has(current)) continue;
          visited.add(current);
          for (const next of adjacency.get(current) || []) queue.push(next);
        }
        return false;
      },

      /* ---- diagnostics ---- */

      diagnostics() {
        const packageStatus = [];
        for (const meta of this.packages.values()) {
          packageStatus.push({
            id: meta.id,
            title: meta.title,
            version: meta.version,
            status: meta.status,
            nodeCount: meta.nodeCount || 0,
            edgeCount: meta.edgeCount || 0,
            quarantinedCount: meta.quarantined.length,
            crossPackageDependencies: meta.meta.crossPackageDependencies || [],
          });
        }
        const quarantineByPackage = new Map();
        for (const item of this.quarantine) {
          if (!quarantineByPackage.has(item.packageId)) quarantineByPackage.set(item.packageId, []);
          quarantineByPackage.get(item.packageId).push(item);
        }
        return {
          hasData: this.hasData(),
          manifestVersion: this.manifest ? this.manifest.version : null,
          manifestError: this.manifestError,
          packages: packageStatus,
          quarantineTotal: this.quarantine.length,
          quarantineByPackage: Object.fromEntries(quarantineByPackage),
          components: this.connectedComponents(),
          coverage: this.manifest ? this.manifest.coverage : null,
          defaults: this.defaults,
        };
      },
    };

    return store;
  }

  return { createStore, MANIFEST_SCHEMA, PACKAGE_SCHEMA, parsePackageText };
});
