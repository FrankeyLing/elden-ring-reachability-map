#!/usr/bin/env node
/**
 * Convert the public static-map marker JavaScript into a small, auditable
 * JSON snapshot. The source is kept outside the repository; only normalized
 * marker facts are published in data/v1.
 */

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

function argument(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

const sourcePath = argument("--source");
const outputPath = argument("--out");
const sourceUrl = argument("--source-url", "");
const retrievedAt = argument("--retrieved-at", new Date().toISOString().slice(0, 10));

if (!sourcePath || !outputPath) {
  console.error("usage: node scripts/normalize-online-map-markers.mjs --source <markers.js> --out <markers.json> [--source-url <url>] [--retrieved-at <date>]");
  process.exit(2);
}

const source = fs.readFileSync(sourcePath, "utf8")
  .replace("const CATEGORIES =", "globalThis.CATEGORIES =")
  .replace("const MARKERS =", "globalThis.MARKERS =");
const context = { globalThis: {} };
vm.runInNewContext(source, context, { filename: sourcePath });
const categories = context.globalThis.CATEGORIES;
const markers = context.globalThis.MARKERS;

if (!Array.isArray(categories) || !Array.isArray(markers)) {
  throw new Error("online map source did not publish CATEGORIES and MARKERS arrays");
}

const normalized = markers.map((marker) => {
  for (const field of ["id", "cat", "name", "master"]) {
    if (typeof marker[field] !== "string" || !marker[field]) {
      throw new Error(`marker missing required ${field}: ${JSON.stringify(marker)}`);
    }
  }
  if (!Number.isFinite(marker.px) || !Number.isFinite(marker.py)) {
    throw new Error(`marker has invalid pixel coordinates: ${JSON.stringify(marker)}`);
  }
  return {
    id: marker.id,
    category: marker.cat,
    name: marker.name,
    master: marker.master,
    pixel: { x: marker.px, y: marker.py },
    description: marker.desc || null,
  };
});

const ids = new Set();
for (const marker of normalized) {
  if (ids.has(marker.id)) throw new Error(`duplicate online marker id: ${marker.id}`);
  ids.add(marker.id);
}

const payload = {
  schema: "errn-online-map-markers@1",
  built_at: retrievedAt,
  source: {
    url: sourceUrl,
    retrieved_at: retrievedAt,
    source_file: sourcePath,
    policy: "Only exact English-name matches to the official entity registry are promoted to acquisition endpoints.",
  },
  categories,
  stats: { markerCount: normalized.length },
  markers: normalized,
};

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, `${JSON.stringify(payload)}\n`, "utf8");
console.log(JSON.stringify(payload.stats));
console.log(`wrote ${outputPath}`);
