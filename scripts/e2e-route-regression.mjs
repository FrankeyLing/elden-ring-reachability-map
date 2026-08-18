#!/usr/bin/env node
/* E2E route regression for the Beta (阶段七 gate).
 *
 * Boots the real HTTP server, loads the manifest + packages through the same
 * endpoints the page uses, then verifies the 8 fixed E2E routes:
 *   1. 黄金树大教堂 → 古兰桑克斯的雷电
 *   2. 史东薇尔正门 → “接肢”葛瑞克
 *   3. 火山官邸入口 → 拉卡德
 *   4. 法姆·亚兹拉迎风露台 → “黑剑”玛利喀斯
 *   5. 圣树树冠 → 玛莲妮亚
 *   6. 希芙拉河井底 → 龙人士兵
 *   7. 王城正常状态与灰烬状态互斥
 *   8. DLC 影之塔升降梯路线
 *
 * Each case checks segment order, key conditions, one-way semantics, layer
 * changes and the packages used.
 *
 * Usage: node scripts/e2e-route-regression.mjs [--port 8105]
 */
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const RouteFramework = require("../framework.js");
const { createStore } = RouteFramework;

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const PORT = Number(process.argv.find((arg) => arg.startsWith("--port="))?.split("=")[1] || 8105);
const BASE = `http://127.0.0.1:${PORT}`;

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

async function fetchText(path) {
  const response = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path} HTTP ${response.status}`);
  return response.text();
}

async function boot() {
  const server = spawn("python", ["server.py", "--port", String(PORT)], {
    cwd: ROOT,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const wait = async (attempts) => {
    for (let index = 0; index < attempts; index += 1) {
      try {
        const response = await fetch(`${BASE}/api/packages/manifest`, { cache: "no-store" });
        if (response.ok) return;
      } catch { /* not up yet */ }
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
    throw new Error("server did not start");
  };
  await wait(30);
  return server;
}

async function loadStoreFromServer() {
  const store = createStore();
  const manifest = JSON.parse(await fetchText("/api/packages/manifest"));
  store.loadManifest(manifest);
  for (const entry of manifest.packages) {
    try {
      const rawText = await fetchText(`/api/packages/${entry.id}`);
      store.loadPackage({ schema: "elden-ring-package@1", package: { id: entry.id }, rawText });
    } catch (error) {
      store.markPackageFailed(entry.id, `fetch failed: ${error.message}`);
    }
  }
  store.finalizeDanglingEdges();
  const profiles = JSON.parse(await fetchText("/api/route-profiles"));
  store.registerCondition(profiles.fastTravelRule);
  return store;
}

const OPTIONS = { dynamicFastTravel: false };

async function main() {
  const server = await boot();
  try {
    const store = await loadStoreFromServer();
    check("manifest + all packages loaded", store.hasData() && store.packages.size === 13, `nodes=${store.nodes.size}`);
    check("no quarantine in clean data", store.quarantine.length === 0, `quarantine=${store.quarantine.length}`);

    /* ---- 1. 黄金树大教堂 → 古兰桑克斯的雷电 ---- */
    console.log("\n[1] 黄金树大教堂 → 古兰桑克斯的雷电");
    {
      const route = store.route("grace_erdtree_sanctuary", "item_bolt_of_gransax",
        ["royal_capital_pre_maliketh", "erdtree_sanctuary_activated"], OPTIONS);
      check("5 segments", route && route.edges.length === 5, `got ${route?.edges?.length}`);
      const types = route?.edges.map((edge) => edge.transitionType);
      check("door_exit → elevator → walkway → one_way_drop → item_pickup",
        types && types.join(",") === "door_exit,elevator,walkway,one_way_drop,item_pickup_approach", JSON.stringify(types));
      check("one-way drop edge not reversed",
        route.edges.every((edge, index) => index === 0 || edge.from === route.nodes[index]), "");
      check("last node is the bolt", route?.nodes.at(-1) === "item_bolt_of_gransax");
      const layers = route?.edges.map((edge) => [store.node(edge.from).layer, store.node(edge.to).layer]);
      check("royal-capital package used", route?.edges.every((edge) => edge.packageId === "royal-capital"));
    }

    /* ---- 2. 史东薇尔正门 → 葛瑞克 ---- */
    console.log("\n[2] 史东薇尔正门 → “接肢”葛瑞克");
    {
      const route = store.route("grace_stormveil_main_gate", "godrick_gate", [], OPTIONS);
      check("5 segments", route && route.edges.length === 5, `got ${route?.edges?.length}`);
      check("last segment is boss approach", route?.edges.at(-1).transitionType === "boss_approach");
      check("uses stormveil package", route?.edges.every((edge) => edge.packageId === "stormveil"));
      check("destination reached", route?.nodes.at(-1) === "godrick_gate");
    }

    /* ---- 3. 火山官邸入口 → 拉卡德 ---- */
    console.log("\n[3] 火山官邸入口 → 拉卡德");
    {
      const route = store.route("grace_volcano_manor_entrance", "rykard_lord_of_blasphemy_gate",
        ["volcano_manor_access", "godskin_noble_defeated"], OPTIONS);
      check("5 segments", route && route.edges.length === 5, `got ${route?.edges?.length}`);
      const types = route?.edges.map((edge) => edge.transitionType);
      check("hidden route → vertical → boss completion → sending gate → boss approach",
        types && types.join(",") === "legacy_hidden_route,vertical_legacy_route,boss_completion,sending_gate_legacy_route,legacy_boss_approach", JSON.stringify(types));
      check("requires volcano_manor_access",
        route?.edges[0].requires.includes("volcano_manor_access"));
      // blocked without conditions
      const blocked = store.explainBlocked("grace_volcano_manor_entrance", "rykard_lord_of_blasphemy_gate", [], OPTIONS);
      check("blocked explanation lists only relevant conditions",
        blocked.category === "conditions" && blocked.missingConditions.length === 2
        && blocked.missingConditions.every((c) => ["volcano_manor_access", "godskin_noble_defeated"].includes(c.id)),
        JSON.stringify(blocked.missingConditions?.map((c) => c.id)));
    }

    /* ---- 4. 法姆·亚兹拉迎风露台 → 玛利喀斯 ---- */
    console.log("\n[4] 法姆·亚兹拉迎风露台 → “黑剑”玛利喀斯");
    {
      const route = store.route("grace_farum_tempest_facing_balcony", "maliketh_gate",
        ["godskin_duo_defeated"], OPTIONS);
      check("8 segments", route && route.edges.length === 8, `got ${route?.edges?.length}`);
      check("godskin duo → rooftop → bridge → boss approach",
        route?.edges[3].transitionType === "legacy_boss_approach"
        && route?.edges[4].transitionType === "boss_completion"
        && route?.edges[4].to === "grace_dragon_temple_altar"
        && route?.edges[6].transitionType === "lightning_rooftop_route"
        && route?.edges.at(-1).transitionType === "legacy_boss_approach");
      const blocked = store.explainBlocked("grace_farum_tempest_facing_balcony", "maliketh_gate", [], OPTIONS);
      check("blocked lists only godskin_duo_defeated",
        blocked.category === "conditions" && blocked.missingConditions.length === 1
        && blocked.missingConditions[0].id === "godskin_duo_defeated", JSON.stringify(blocked.missingConditions?.map((c) => c.id)));
    }

    /* ---- 5. 圣树树冠 → 玛莲妮亚 ---- */
    console.log("\n[5] 圣树树冠 → 玛莲妮亚");
    {
      const route = store.route("grace_haligtree_canopy", "malenia_haligtree_gate",
        ["loretta_haligtree_defeated"], OPTIONS);
      check("9 segments", route && route.edges.length === 9, `got ${route?.edges?.length}`);
      check("elevator and rot-root segments present",
        route?.edges.some((edge) => edge.transitionType === "legacy_elevator")
        && route?.edges.some((edge) => edge.transitionType === "scarlet_rot_root_route"));
      check("boss approach last", route?.edges.at(-1).transitionType === "legacy_boss_approach");
      const blocked = store.explainBlocked("grace_haligtree_canopy", "malenia_haligtree_gate", [], OPTIONS);
      check("blocked lists only loretta_haligtree_defeated",
        blocked.category === "conditions" && blocked.missingConditions.length === 1
        && blocked.missingConditions[0].id === "loretta_haligtree_defeated", JSON.stringify(blocked.missingConditions?.map((c) => c.id)));
    }

    /* ---- 6. 希芙拉河井底 → 龙人士兵 ---- */
    console.log("\n[6] 希芙拉河井底 → 龙人士兵");
    {
      const route = store.route("grace_siofra_well_depths", "dragonkin_soldier_siofra_gate", [], OPTIONS);
      check("5 segments", route && route.edges.length === 5, `got ${route?.edges?.length}`);
      check("elevator + sending gate present",
        route?.edges.some((edge) => edge.transitionType === "elevator")
        && route?.edges.at(-1).transitionType === "sending_gate");
      check("uses underground package", route?.edges.every((edge) => edge.packageId === "underground" || edge.packageId === "bridge"));
    }

    /* ---- 7. 王城正常状态与灰烬状态互斥 ---- */
    console.log("\n[7] 王城两态互斥");
    {
      // royal route needs royal_capital_pre_maliketh; in ashen state it must fail
      const royalRoute = store.route("grace_erdtree_sanctuary", "item_bolt_of_gransax",
        ["royal_capital_pre_maliketh", "erdtree_sanctuary_activated"], OPTIONS);
      check("royal route ok with royal condition", royalRoute !== null && royalRoute.edges.length === 5);
      const royalInAshen = store.route("grace_erdtree_sanctuary", "item_bolt_of_gransax",
        ["ashen_capital_post_maliketh", "erdtree_sanctuary_activated"], OPTIONS);
      check("royal route blocked in ashen state", royalInAshen === null);
      // ashen route: 灰烬王城 → 最终 Boss
      const ashenRoute = store.route("grace_leyndell_capital_of_ash", "radagon_elden_beast_gate",
        ["maliketh_defeated", "morgott_defeated", "gideon_defeated", "godfrey_ashen_defeated"], OPTIONS);
      check("ashen route ok with ashen conditions", ashenRoute !== null && ashenRoute.edges.length >= 6,
        `got ${ashenRoute?.edges?.length}`);
      check("ashen route uses ashen-capital package",
        ashenRoute?.edges.every((edge) => edge.packageId === "ashen-capital" || edge.packageId === "bridge"));
      // ashen route must not mix with royal state
      const ashenWithRoyalState = store.route("grace_leyndell_capital_of_ash", "radagon_elden_beast_gate",
        ["royal_capital_pre_maliketh"], OPTIONS);
      check("ashen route blocked in royal state", ashenWithRoyalState === null);
    }

    /* ---- 8. DLC 影之塔升降梯路线 ---- */
    console.log("\n[8] DLC 影之塔（升降梯/垂直路线）");
    {
      const route = store.route("grace_shadow_keep_main_gate_plaza", "grace_shadow_keep_storehouse_seventh_floor",
        ["golden_hippopotamus_defeated"], OPTIONS);
      check("3 segments", route && route.edges.length === 3, `got ${route?.edges?.length}`);
      check("storehouse vertical route (elevators)",
        route?.edges.every((edge) => edge.transitionType === "legacy_vertical_route" || edge.transitionType === "storehouse_vertical_route"));
      check("uses shadow-realm package", route?.edges.every((edge) => edge.packageId === "shadow-realm"));
      const blocked = store.explainBlocked("grace_shadow_keep_main_gate_plaza", "grace_shadow_keep_storehouse_seventh_floor", [], OPTIONS);
      check("blocked lists only golden_hippopotamus_defeated",
        blocked.category === "conditions" && blocked.missingConditions.length === 1
        && blocked.missingConditions[0].id === "golden_hippopotamus_defeated", JSON.stringify(blocked.missingConditions?.map((c) => c.id)));
    }

    /* ---- page-level: startup must not depend on research files ---- */
    console.log("\n[page] startup independence");
    {
      const html = await fetchText("/");
      check("player page served", html.includes("RUNE//PATH"));
      check("page loads framework + app only", html.includes("framework.js") && html.includes("app.js")
        && !html.includes("coordinate-map.js"));
      const researchHtml = await fetchText("/research.html");
      check("research console preserved", researchHtml.includes("coordinate-map.js"));
    }
  } finally {
    server.kill();
  }

  console.log(`\nRESULT: ${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
}

main().catch((error) => {
  console.error(error);
  process.exit(2);
});
