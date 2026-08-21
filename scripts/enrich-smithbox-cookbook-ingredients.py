#!/usr/bin/env python3
"""Enrich cookbook unlock records with public recipe materials.

The Smithbox event-flag source is the authority for the unlock dependency.
The Eldenpedia cookbook table is a separate source for output and material
quantities.  A recipe is enriched only when both product and cookbook names
match exactly.  An unmatched recipe remains present with an explicit missing
status; no unlock relation is removed or inferred from a product-only match.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def last_link_label(value: str) -> str | None:
    """Return the label of the last Markdown link in a table cell."""

    close = value.rfind("](")
    if close < 0:
        return None
    depth = 1
    for index in range(close - 1, -1, -1):
        char = value[index]
        if char == "]":
            depth += 1
        elif char == "[":
            depth -= 1
            if depth == 0:
                label = value[index + 1 : close]
                if label.startswith("![") and label.endswith("]"):
                    label = label[2:-1]
                return re.sub(r"\s+", " ", label).strip()
    return None


def parse_quantity(value: str) -> int | None:
    match = re.fullmatch(r"x?(\d+)", value.strip(), flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def parse_public_recipe_table(source_path: Path) -> list[dict]:
    current_cookbook: str | None = None
    recipes: list[dict] = []
    lines = source_path.read_text(encoding="utf-8").splitlines()

    for line_number, line in enumerate(lines, 1):
        if " recipes " in line and "](" in line and not line.lstrip().startswith("|"):
            label = last_link_label(line)
            if label and ("Cookbook" in label or label == "Crafting Kit"):
                current_cookbook = label
                continue
        if (
            not current_cookbook
            or not line.startswith("|")
            or line.startswith("| ---")
            or "Item name" in line
        ):
            continue

        columns = [column.strip() for column in line.strip().strip("|").split("|")]
        if len(columns) == 4:
            product_name = last_link_label(columns[0])
            product_quantity = parse_quantity(columns[1])
            material_name = last_link_label(columns[2])
            material_quantity = parse_quantity(columns[3])
            if not product_name or product_quantity is None or not material_name:
                continue
            if material_quantity is None:
                raise ValueError(f"non-numeric material quantity at line {line_number}")
            recipes.append(
                {
                    "cookbookName": current_cookbook,
                    "productName": product_name,
                    "productQuantity": product_quantity,
                    "ingredients": [
                        {
                            "sourceName": material_name,
                            "quantity": material_quantity,
                            "quantityStatus": "stated_in_source",
                        }
                    ],
                    "sourceLine": line_number,
                }
            )
        elif len(columns) == 2 and recipes:
            material_name = last_link_label(columns[0])
            material_quantity = parse_quantity(columns[1])
            if material_name and material_quantity is not None:
                recipes[-1]["ingredients"].append(
                    {
                        "sourceName": material_name,
                        "quantity": material_quantity,
                        "quantityStatus": "stated_in_source",
                    }
                )

    if not recipes:
        raise ValueError("public cookbook source yielded no recipe rows")
    keys = [(recipe["productName"], recipe["cookbookName"]) for recipe in recipes]
    if len(keys) != len(set(keys)):
        raise ValueError("public cookbook source contains duplicate product/cookbook pairs")
    return recipes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipes", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--entity-registry", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--retrieval-url", required=True)
    parser.add_argument("--retrieved-at", required=True)
    args = parser.parse_args()

    payload = json.loads(args.recipes.read_text(encoding="utf-8"))
    entities = json.loads(args.entity_registry.read_text(encoding="utf-8"))["entities"]
    entity_by_name: dict[str, list[dict]] = {}
    for entity in entities:
        english_name = entity.get("name", {}).get("en")
        if english_name:
            entity_by_name.setdefault(english_name.casefold(), []).append(entity)

    public_recipes = parse_public_recipe_table(args.source)
    public_by_key = {
        (recipe["productName"].casefold(), recipe["cookbookName"].casefold()): recipe
        for recipe in public_recipes
    }

    exact_matches = 0
    pair_mismatches = 0
    ingredient_count = 0
    resolved_ingredient_count = 0
    unresolved_ingredient_count = 0
    output_recipes = []
    for recipe in payload.get("recipes", []):
        key = (
            str(recipe.get("productName") or "").casefold(),
            str(recipe.get("cookbookName") or "").casefold(),
        )
        public = public_by_key.get(key)
        enriched = dict(recipe)
        if public is None:
            pair_mismatches += 1
            enriched["ingredients"] = []
            enriched["ingredientsStatus"] = "source_pair_not_found"
            enriched["productQuantity"] = None
            enriched["productQuantityStatus"] = "source_pair_not_found"
            enriched["ingredientSourceLine"] = None
            output_recipes.append(enriched)
            continue

        exact_matches += 1
        ingredients = []
        for ingredient in public["ingredients"]:
            candidates = entity_by_name.get(ingredient["sourceName"].casefold(), [])
            if len(candidates) == 1:
                entity = candidates[0]
                resolved_ingredient_count += 1
                resolution = "exact_unique_official_name_match"
                item_id = entity["id"]
                canonical_name = entity["name"]
            else:
                unresolved_ingredient_count += 1
                resolution = "unresolved_unique_entity_name_required"
                item_id = None
                canonical_name = None
            ingredients.append(
                {
                    "itemId": item_id,
                    "sourceName": ingredient["sourceName"],
                    "canonicalName": canonical_name,
                    "quantity": ingredient["quantity"],
                    "quantityStatus": ingredient["quantityStatus"],
                    "resolution": resolution,
                }
            )
        ingredient_count += len(ingredients)
        enriched["ingredients"] = ingredients
        enriched["ingredientsStatus"] = (
            "present_exact_unique_entity_match"
            if all(ingredient["itemId"] for ingredient in ingredients)
            else "present_with_unresolved_source_names"
        )
        enriched["productQuantity"] = public["productQuantity"]
        enriched["productQuantityStatus"] = "stated_in_source"
        enriched["ingredientSourceLine"] = public["sourceLine"]
        output_recipes.append(enriched)

    raw = args.source.read_bytes()
    output = dict(payload)
    output["schema"] = "errn-smithbox-cookbook-recipes@2"
    output["ingredientSource"] = {
        "url": args.source_url,
        "retrievalUrl": args.retrieval_url,
        "retrievedAt": args.retrieved_at,
        "sourceFile": str(args.source),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "policy": (
            "Material names, per-craft quantities, and product output quantities "
            "are copied only from an exact public product/cookbook table match. "
            "Unmatched rows remain explicitly missing and never alter the unlock source."
        ),
    }
    stats = dict(output.get("stats") or {})
    stats.update(
        {
            "publicRecipeCount": len(public_recipes),
            "ingredientSourceExactMatchCount": exact_matches,
            "ingredientSourcePairMismatchCount": pair_mismatches,
            "ingredientCount": ingredient_count,
            "resolvedIngredientCount": resolved_ingredient_count,
            "unresolvedIngredientCount": unresolved_ingredient_count,
            "ingredientsPresentCount": sum(bool(recipe["ingredients"]) for recipe in output_recipes),
        }
    )
    output["stats"] = stats
    output["recipes"] = output_recipes
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(stats, ensure_ascii=False))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
