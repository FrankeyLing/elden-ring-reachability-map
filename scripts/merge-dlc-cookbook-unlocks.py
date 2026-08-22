#!/usr/bin/env python3
"""Merge pinned DLC cookbook-to-product evidence into the recipe catalog.

The input CSV is an independently published, versioned online dataset.  It
states which products each cookbook unlocks but does not state ingredients.
Only DLC rows whose cookbook and product both resolve to one official local
entity are promoted.  Existing Smithbox relations are never overwritten.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
from pathlib import Path


def canonical_candidates(name: str, entities: list[dict], *, product: bool) -> list[dict]:
    normalized = name.strip().casefold()
    candidates = [
        entity
        for entity in entities
        if (entity.get("name", {}).get("en") or "").casefold() == normalized
        and (product or entity.get("kind") == "item")
    ]
    if not product and not candidates:
        alternate = re.sub(r"\s+\[(\d+)\]$", r" (\1)", name.strip()).casefold()
        candidates = [
            entity
            for entity in entities
            if entity.get("kind") == "item"
            and (entity.get("name", {}).get("en") or "").casefold() == alternate
        ]
    if product and len(candidates) > 1:
        # A craft result is an inventory Goods record.  This resolves names
        # such as Golden Vow that are shared by a Goods row and a Magic row.
        item_candidates = [entity for entity in candidates if entity.get("kind") == "item"]
        if len(item_candidates) == 1:
            return item_candidates
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipes", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--entity-registry", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--retrieved-at", required=True)
    args = parser.parse_args()

    output = json.loads(args.recipes.read_text(encoding="utf-8"))
    entities = json.loads(args.entity_registry.read_text(encoding="utf-8"))["entities"]
    # Make repeated runs deterministic by replacing only this source's prior
    # projection and retaining every independently sourced recipe unchanged.
    output["recipes"] = [
        recipe
        for recipe in output.get("recipes", [])
        if (recipe.get("unlockSource") or {}).get("id")
        != "ultimate-elden-ring-sote-dataset"
    ]
    existing_pairs = {
        (
            str(recipe.get("cookbookName") or "").casefold(),
            str(recipe.get("productName") or "").casefold(),
        )
        for recipe in output.get("recipes", [])
    }

    source_bytes = args.source.read_bytes()
    rows = list(csv.DictReader(source_bytes.decode("utf-8-sig").splitlines()))
    additions: list[dict] = []
    gaps: list[dict] = []
    seen_source_pairs: set[tuple[str, str]] = set()

    for source_line, row in enumerate(rows, 2):
        if str(row.get("dlc") or "").strip() != "1":
            continue
        cookbook_name = str(row.get("name") or "").strip()
        try:
            products = ast.literal_eval(str(row.get("required for") or "[]"))
        except (SyntaxError, ValueError) as error:
            gaps.append({
                "sourceLine": source_line,
                "sourceCookbookName": cookbook_name,
                "status": "invalid_product_list",
                "detail": str(error),
            })
            continue
        if not isinstance(products, list):
            gaps.append({
                "sourceLine": source_line,
                "sourceCookbookName": cookbook_name,
                "status": "product_list_not_array",
            })
            continue

        for product_index, raw_product_name in enumerate(products):
            product_name = str(raw_product_name).strip()
            pair = (cookbook_name.casefold(), product_name.casefold())
            if not product_name or pair in seen_source_pairs:
                continue
            seen_source_pairs.add(pair)
            if pair in existing_pairs:
                continue

            cookbooks = canonical_candidates(cookbook_name, entities, product=False)
            products_found = canonical_candidates(product_name, entities, product=True)
            if len(cookbooks) != 1 or len(products_found) != 1:
                gaps.append({
                    "sourceLine": source_line,
                    "sourceCookbookName": cookbook_name,
                    "sourceProductName": product_name,
                    "status": "canonical_unique_match_required",
                    "cookbookCandidateIds": [entity["id"] for entity in cookbooks],
                    "productCandidateIds": [entity["id"] for entity in products_found],
                })
                continue

            cookbook = cookbooks[0]
            product = products_found[0]
            additions.append({
                "sourceRecipeId": f"dataset-dlc-{row.get('id')}-{product_index}",
                "productName": product_name,
                "cookbookName": cookbook_name,
                "sourceLine": source_line,
                "productQuantity": None,
                "productQuantityStatus": "not_stated_in_source",
                "ingredients": [],
                "ingredientsStatus": "not_present_in_source",
                "cookbookHeaderStatus": "not_applicable_csv_row",
                "unlockSource": {
                    "id": "ultimate-elden-ring-sote-dataset",
                    "url": args.source_url,
                    "commit": args.source_commit,
                    "sourceFile": str(args.source),
                    "sourceLine": source_line,
                    "license": "CC0-1.0-as-stated-by-publisher",
                    "verification": "online_dataset_dlc_pair_exact_unique_official_entity_match",
                },
                "resolvedCookbookItemId": cookbook["id"],
                "resolvedProductItemId": product["id"],
            })
            existing_pairs.add(pair)

    if len(additions) < 50:
        raise SystemExit(f"DLC cookbook source yielded only {len(additions)} exact additions")

    output["recipes"].extend(additions)
    output["schema"] = "errn-cookbook-recipes@3"
    output["dlcUnlockSource"] = {
        "url": args.source_url,
        "commit": args.source_commit,
        "retrievedAt": args.retrieved_at,
        "sourceFile": str(args.source),
        "sha256": hashlib.sha256(source_bytes).hexdigest(),
        "license": "CC0-1.0-as-stated-by-publisher",
        "policy": (
            "Only DLC cookbook/product pairs with exact unique official local entity "
            "matches are added; no material quantities or locations are inferred."
        ),
    }
    output["dlcUnlockCoverageGaps"] = gaps
    stats = dict(output.get("stats") or {})
    stats.update({
        "recipeCount": len(output["recipes"]),
        "totalCookbookCount": len({
            str(recipe.get("cookbookName") or "").casefold()
            for recipe in output["recipes"]
            if recipe.get("cookbookName")
        }),
        "dlcSourceRowCount": sum(str(row.get("dlc") or "").strip() == "1" for row in rows),
        "dlcExactRecipeAdditionCount": len(additions),
        "dlcCoverageGapCount": len(gaps),
    })
    output["stats"] = stats
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "recipeCount": len(output["recipes"]),
        "dlcExactRecipeAdditionCount": len(additions),
        "dlcCoverageGapCount": len(gaps),
    }, ensure_ascii=False))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
