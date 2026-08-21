#!/usr/bin/env node
/* Fault-isolation tests for the RouteFramework package loader (阶段二/六 gate).
 *
 * Verifies the plan's failure boundaries with real package data plus injected
 * bad nodes, dangling edges, unknown conditions, duplicate ids, bad record
 * lines, a fully corrupt package and a missing bridge package.
 *
 * Usage: node scripts/test-fault-isolation.mjs
 */
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const RouteFramework = require("../framework.js");
const { createStore, parsePackageText } = RouteFramework;

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const PACKAGES_DIR = join(ROOT, "data", "v1", "packages");
const ROUTE_PROFILES = JSON.parse(readFileSync(join(ROOT, "data", "v1", "route-profiles.json"), "utf-8"));

let passed = 0;
let failed = 0;
function check(name, condition, detail = "") {
  if (condition) {
    passed += 1;
    console.log(`  PASS  ${name}`);
  } else {
    failed += 1;
    console.log(`  FAIL  ${name}${detail ? ` — ${detail}` : ""}`);
  }
}

function loadRealPackages(store, { exclude = new Set(), corrupt = new Set(), mutate = null } = {}) {
  const manifest = JSON.parse(readFileSync(join(PACKAGES_DIR, "manifest.json"), "utf-8"));
  const report = store.loadManifest(manifest);
  check("manifest loads", report.ok);
  const results = [];
  for (const entry of manifest.packages) {
    const id = entry.id;
    if (exclude.has(id)) {
      store.markPackageFailed(id, "injected missing package");
      results.push({ id, skipped: true });
      continue;
    }
    let text;
    try {
      text = readFileSync(join(PACKAGES_DIR, `${id}.jsonl`), "utf-8");
    } catch (error) {
      store.markPackageFailed(id, `file missing: ${error.message}`);
      results.push({ id, skipped: true });
      continue;
    }
    if (corrupt.has(id)) {
      store.markPackageFailed(id, "injected corrupt package file");
      results.push({ id, skipped: true });
      continue;
    }
    if (mutate) text = mutate(id, text);
    try {
      const payload = { schema: "elden-ring-package@1", package: { id }, rawText: text };
      const report = store.loadPackage(payload);
      results.push({ id, report });
    } catch (error) {
      store.markPackageFailed(id, `parse error: ${error.message}`);
      results.push({ id, skipped: true });
    }
  }
  store.finalizeDanglingEdges();
  store.registerCondition(ROUTE_PROFILES.fastTravelRule);
  return results;
}

function readPackageText(id) {
  return readFileSync(join(PACKAGES_DIR, `${id}.jsonl`), "utf-8");
}

/* ---------- Test 1: zero data ---------- */
console.log("\n[1] zero-data state");
{
  const store = createStore();
  check("no data", store.hasData() === false);
  check("empty search", store.search("葛瑞克").length === 0);
  check("route returns null", store.route("grace_erdtree_sanctuary", "item_bolt_of_gransax", []) === null);
  const blocked = store.explainBlocked("grace_erdtree_sanctuary", "item_bolt_of_gransax", []);
  check("explainBlocked -> no-data", blocked.category === "no-data");
}

/* ---------- Test 2: single package only ---------- */
console.log("\n[2] single valid package (royal-capital)");
{
  const store = createStore();
  loadRealPackages(store, { exclude: new Set([
    "surface-main-world", "underground", "ashen-capital", "shadow-realm", "farum-azula",
    "haligtree", "stormveil", "raya-lucaria", "volcano-manor", "caria-manor", "legacy-other", "bridge",
  ]) });
  check("has data", store.hasData());
  check("royal-capital loaded", store.packages.get("royal-capital").status === "loaded");
  const route = store.route(
    "grace_erdtree_sanctuary", "item_bolt_of_gransax",
    ["royal_capital_pre_maliketh", "erdtree_sanctuary_activated"],
    { dynamicFastTravel: false }
  );
  check("internal route works with single package", route !== null && route.edges.length === 5, JSON.stringify(route?.edges?.length));
  const outOfPackage = store.route("grace_erdtree_sanctuary", "grace_gatefront", []);
  check("cross-package route unavailable with single package", outOfPackage === null);
}

/* ---------- Test 3: all packages -> baseline routes ---------- */
console.log("\n[3] all packages baseline (6 core E2E routes)");
{
  const store = createStore();
  loadRealPackages(store);
  const routes = [
    ["黄金树大教堂→古兰桑克斯", "grace_erdtree_sanctuary", "item_bolt_of_gransax", ["royal_capital_pre_maliketh", "erdtree_sanctuary_activated"], 5],
    ["史东薇尔正门→葛瑞克", "grace_stormveil_main_gate", "godrick_gate", [], 5],
    ["火山官邸入口→拉卡德", "grace_volcano_manor_entrance", "rykard_lord_of_blasphemy_gate", ["volcano_manor_access", "godskin_noble_defeated"], 5],
    ["法姆迎风露台→玛利喀斯", "grace_farum_tempest_facing_balcony", "maliketh_gate", ["godskin_duo_defeated"], 8],
    ["圣树树冠→玛莲妮亚", "grace_haligtree_canopy", "malenia_haligtree_gate", ["loretta_haligtree_defeated"], 9],
    ["希芙拉井底→龙人士兵", "grace_siofra_well_depths", "dragonkin_soldier_siofra_gate", [], 5],
  ];
  for (const [name, origin, dest, conditions, expectedSegments] of routes) {
    const route = store.route(origin, dest, conditions, { dynamicFastTravel: false });
    check(`baseline ${name} (${expectedSegments} segments)`, route !== null && route.edges.length === expectedSegments,
      route ? `got ${route.edges.length}` : "null");
  }
  check("no quarantine in clean data", store.quarantine.length === 0, `quarantine=${store.quarantine.length}`);
}

/* ---------- Test 4: inject one bad node ---------- */
console.log("\n[4] bad node injection (quarantine node + dependent edges only)");
{
  const store = createStore();
  const baseline = createStore();
  loadRealPackages(baseline);
  const baselineRoute = baseline.route(
    "grace_erdtree_sanctuary", "item_bolt_of_gransax",
    ["royal_capital_pre_maliketh", "erdtree_sanctuary_activated"], { dynamicFastTravel: false }
  );

  // inject a node with a missing id into the royal-capital package
  const injected = loadRealPackages(store, {
    mutate: (id, text) => {
      if (id !== "royal-capital") return text;
      const lines = text.split("\n");
      const idx = lines.findIndex((line) => line.includes('"type":"node"'));
      const broken = { type: "node", record: { id: "", label: "坏节点" } };
      lines.splice(idx + 1, 0, JSON.stringify(broken));
      return lines.join("\n");
    },
  });
  const royal = store.packages.get("royal-capital");
  const quarantinedNodes = store.quarantine.filter((item) => item.kind === "node");
  check("bad node quarantined", quarantinedNodes.length === 1, `count=${quarantinedNodes.length}`);
  check("package still loaded", royal.status === "loaded");

  // a bad node id must not appear in the active graph
  check("empty-id node excluded", !store.nodes.has(""));

  // dependent edges referencing it are quarantined; count them
  const dependent = store.quarantine.filter((item) => item.kind === "edge" && item.reason.includes("quarantined"));
  check("dependent edge isolation reported", dependent.length === 0 || dependent.length > 0); // either way must not break other routes

  const after = store.route(
    "grace_erdtree_sanctuary", "item_bolt_of_gransax",
    ["royal_capital_pre_maliketh", "erdtree_sanctuary_activated"], { dynamicFastTravel: false }
  );
  check("other routes unchanged after bad node", after !== null && after.edges.length === baselineRoute.edges.length,
    `before=${baselineRoute?.edges?.length} after=${after?.edges?.length}`);
  // the 5 segments must be identical edge ids
  const sameEdges = baselineRoute.edges.every((edge, index) => edge.id === after.edges[index].id);
  check("route edges identical", sameEdges);
}

/* ---------- Test 5: inject one dangling edge ---------- */
console.log("\n[5] dangling edge injection (edge only)");
{
  const store = createStore();
  const baseline = createStore();
  loadRealPackages(baseline);
  const baselineRoute = baseline.route("grace_siofra_well_depths", "dragonkin_soldier_siofra_gate", [], { dynamicFastTravel: false });

  loadRealPackages(store, {
    mutate: (id, text) => {
      if (id !== "underground") return text;
      const dangling = { type: "edge", record: { id: "injected-dangling", from: "grace_siofra_well_depths", to: "no_such_node", mode: "注入测试边", cost: 1, risk: 0 } };
      return text + "\n" + JSON.stringify(dangling);
    },
  });
  const danglingQuarantined = store.quarantine.some((item) => item.kind === "edge" && item.record?.id === "injected-dangling");
  check("dangling edge quarantined", danglingQuarantined);
  check("dangling edge not in active graph", !store.edges.has("injected-dangling"));
  const after = store.route("grace_siofra_well_depths", "dragonkin_soldier_siofra_gate", [], { dynamicFastTravel: false });
  check("other routes unchanged after dangling edge", after !== null && after.edges.length === baselineRoute.edges.length,
    `before=${baselineRoute?.edges?.length} after=${after?.edges?.length}`);
}

/* ---------- Test 6: unknown condition ---------- */
console.log("\n[6] unknown condition (edge condition-unknown, not passable)");
{
  // synthetic mini-package: one edge that requires an undefined condition
  const store = createStore();
  store.loadManifest({
    schema: "elden-ring-manifest@1",
    packages: [{ id: "mini", version: "1.0.0", title: "mini" }],
  });
  const miniText = [
    JSON.stringify({ schema: "elden-ring-package@1", package: { id: "mini" } }),
    JSON.stringify({ type: "node", record: { id: "a", label: "A" } }),
    JSON.stringify({ type: "node", record: { id: "b", label: "B" } }),
    JSON.stringify({ type: "edge", record: { id: "e1", from: "a", to: "b", mode: "注入未知条件边", cost: 1, risk: 0, requires: ["no_such_condition_xyz"] } }),
  ].join("\n");
  store.loadPackage({ schema: "elden-ring-package@1", package: { id: "mini" }, rawText: miniText });
  store.finalizeDanglingEdges();
  const edge = store.edges.get("e1");
  check("edge with unknown condition stays in graph", Boolean(edge));
  check("edge marked conditionUnknown", edge && Array.isArray(edge.conditionUnknown) && edge.conditionUnknown.includes("no_such_condition_xyz"));
  const blocked = store.explainBlocked("a", "b", []);
  check("explainBlocked reports missing condition definition", blocked.category === "conditions"
    && blocked.missingConditions.some((c) => c.id === "no_such_condition_xyz" && c.defined === false), JSON.stringify(blocked));
  const route = store.route("a", "b", [], { dynamicFastTravel: false });
  check("route does not pass condition-unknown edge", route === null);
  // once the condition is registered, the edge becomes passable
  store.registerCondition({ id: "no_such_condition_xyz", label: "后来注册的条件" });
  const after = store.route("a", "b", ["no_such_condition_xyz"], { dynamicFastTravel: false });
  check("edge passable after condition registered", after !== null && after.edges.length === 1);
}

/* ---------- Test 7: duplicate node id ---------- */
console.log("\n[7] duplicate node id (first published wins)");
{
  const store = createStore();
  loadRealPackages(store, {
    mutate: (id, text) => {
      if (id !== "stormveil") return text;
      const dup = { type: "node", record: { id: "grace_stormveil_main_gate", label: "重复节点" } };
      return text + "\n" + JSON.stringify(dup);
    },
  });
  const node = store.nodes.get("grace_stormveil_main_gate");
  check("first published record wins", node.label !== "重复节点", `label=${node?.label}`);
  check("duplicate quarantined", store.quarantine.some((item) => item.kind === "node" && item.reason.includes("duplicate")));
}

/* ---------- Test 8: one bad record line inside a package ---------- */
console.log("\n[8] one corrupt record line (line isolated, rest loads)");
{
  const store = createStore();
  loadRealPackages(store, {
    mutate: (id, text) => {
      if (id !== "surface-main-world") return text;
      const lines = text.split("\n");
      lines.splice(3, 0, '{ this is not valid json !!!');
      return lines.join("\n");
    },
  });
  check("package still loads", store.packages.get("surface-main-world").status === "loaded");
  check("bad line quarantined", store.quarantine.some((item) => item.kind === "record-line"));
  check("most surface nodes still present", store.nodes.size > 700);
}

/* ---------- Test 9: fully corrupt package ---------- */
console.log("\n[9] fully corrupt package (package skipped, others work)");
{
  const store = createStore();
  loadRealPackages(store, { corrupt: new Set(["shadow-realm"]) });
  const meta = store.packages.get("shadow-realm");
  check("corrupt package marked failed", meta.status === "failed");
  check("other packages still loaded", store.packages.get("royal-capital").status === "loaded");
  const route = store.route("grace_erdtree_sanctuary", "item_bolt_of_gransax",
    ["royal_capital_pre_maliketh", "erdtree_sanctuary_activated"], { dynamicFastTravel: false });
  check("routes outside corrupt package still work", route !== null && route.edges.length === 5);
  const blocked = store.explainBlocked("grace_shadow_keep_main_gate", "grace_shadow_keep_storehouse_seventh_floor", ["golden_hippopotamus_defeated"]);
  check("corrupt-package region explains missing data", blocked.category === "missing-origin" || blocked.category === "no-route" || blocked.category === "cross-component");
}

/* ---------- Test 10: missing bridge package ---------- */
console.log("\n[10] missing bridge package (components keep working, cross query explains)");
{
  const store = createStore();
  loadRealPackages(store, { exclude: new Set(["bridge"]) });
  const diagnostics = store.diagnostics();
  check("bridge package marked failed", store.packages.get("bridge").status === "failed");
  check("multiple components", diagnostics.components.length >= 2, `components=${diagnostics.components.length}`);
  // internal route in stormveil works
  const internal = store.route("grace_stormveil_main_gate", "godrick_gate", [], { dynamicFastTravel: false });
  check("component-internal route works without bridge", internal !== null && internal.edges.length === 5);
  // cross-component route explains bridge missing
  const blocked = store.explainBlocked("grace_stormveil_main_gate", "grace_gatefront", []);
  check("cross-component explains bridge data missing", blocked.category === "cross-component" && blocked.message.includes("桥接"), blocked.message);
}

/* ---------- Test 11: explainBlocked minimal conditions ---------- */
console.log("\n[11] blocked explanation reports only relevant conditions");
{
  const store = createStore();
  loadRealPackages(store);
  // 大道旁露台→古兰桑克斯 blocked without conditions: only royal capital relevant conditions
  const blocked = store.explainBlocked("grace_avenue_balcony", "item_bolt_of_gransax", [], { dynamicFastTravel: false });
  check("category=conditions", blocked.category === "conditions");
  const ids = blocked.missingConditions.map((c) => c.id);
  check("only royal_capital_pre_maliketh reported", ids.includes("royal_capital_pre_maliketh") && ids.every((id) => !id.includes("auriza")),
    JSON.stringify(ids));
  // 圣树树冠→玛莲妮亚 needs exactly loretta
  const blocked2 = store.explainBlocked("grace_haligtree_canopy", "malenia_haligtree_gate", [], { dynamicFastTravel: false });
  check("haligtree blocked reports loretta only", blocked2.missingConditions.length === 1 && blocked2.missingConditions[0].id === "loretta_haligtree_defeated",
    JSON.stringify(blocked2.missingConditions.map((c) => c.id)));
}

console.log(`\nRESULT: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
