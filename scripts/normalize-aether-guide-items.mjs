#!/usr/bin/env node
/**
 * Normalize the public Aether item guide snapshot into an auditable source
 * layer. The source snapshot stays outside this repository. This file keeps
 * the source item identity, acquisition text and map coordinate intact; it
 * does not infer a game route node or convert the source projection.
 */

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

function argument(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

const sourcePath = argument("--source");
const outputPath = argument("--out");
const sourceUrl = argument("--source-url", "");
const retrievedAt = argument("--retrieved-at", new Date().toISOString().slice(0, 10));

if (!sourcePath || !outputPath) {
  console.error("usage: node scripts/normalize-aether-guide-items.mjs --source <items.json> --out <items.json> [--source-url <url>] [--retrieved-at <date>]");
  process.exit(2);
}

const raw = fs.readFileSync(sourcePath);
const sourceHash = crypto.createHash("sha256").update(raw).digest("hex");
const sourceItems = JSON.parse(raw.toString("utf8"));
if (!Array.isArray(sourceItems)) {
  throw new Error("Aether source is not an item array");
}

const items = sourceItems.map((item, index) => {
  for (const field of ["id", "name", "category"]) {
    if (typeof item[field] !== "string" || !item[field]) {
      throw new Error(`source item ${index} missing required ${field}`);
    }
  }
  const map = item.map ?? null;
  if (map !== null) {
    if (typeof map !== "object" || map.markerId === undefined ||
        !Number.isFinite(map.lat) || !Number.isFinite(map.lng) ||
        typeof map.code !== "string" || !map.code) {
      throw new Error(`source item ${item.id} has an invalid map record`);
    }
  }
  return {
    sourceId: item.id,
    name: item.name,
    category: item.category,
    dlc: item.dlc === true,
    acquisition: item.acquisition || null,
    missable: item.missable ?? null,
    quest: item.quest ?? null,
    map: map ? {
      code: map.code,
      markerId: map.markerId,
      lat: map.lat,
      lng: map.lng,
    } : null,
    wikiUrl: item.wikiUrl || null,
    details: item.details ?? null,
  };
});

const mapItems = items.filter((item) => item.map !== null);
const categoryCounts = {};
for (const item of items) {
  categoryCounts[item.category] = (categoryCounts[item.category] || 0) + 1;
}

const payload = {
  schema: "errn-aether-guide-items@1",
  built_at: retrievedAt,
  source: {
    url: sourceUrl,
    retrieved_at: retrievedAt,
    source_file: sourcePath,
    sha256: sourceHash,
    policy: "Only exact unique English-name matches to the official entity registry are promoted to acquisition relations; source coordinates remain coordinate-only endpoints.",
  },
  stats: {
    itemCount: items.length,
    mapItemCount: mapItems.length,
    noMapItemCount: items.length - mapItems.length,
    categoryCounts,
  },
  items,
};

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, `${JSON.stringify(payload)}\n`, "utf8");
console.log(JSON.stringify(payload.stats));
console.log(`wrote ${outputPath}`);

