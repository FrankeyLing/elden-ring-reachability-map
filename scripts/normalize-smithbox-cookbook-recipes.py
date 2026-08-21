#!/usr/bin/env python3
"""Normalize Smithbox's public cookbook event-flag index.

The source lists the recipe product and the cookbook event flag that unlocks
it.  It does not include material quantities, so this normalizer preserves an
explicit unknown state instead of inventing ingredients or output counts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


RECIPE_RE = re.compile(
    r"^\s*(?P<recipe_id>\d+)\s+(?P<product>.+?)\s+-\s+(?P<cookbook>.+?Cookbook(?:\s+\[\d+\])?)\s*$"
)
COOKBOOK_RE = re.compile(r"^#\s+(?P<name>.+Cookbook(?:\s+\[\d+\])?)\s*$")


def normalize_cookbook_name(value: str) -> str:
    value = value.strip().replace("’", "'").replace("‘", "'")
    value = re.sub(r"^Nomadeic Warrior", "Nomadic Warrior", value)
    value = re.sub(r"^\s+", "", value)
    return re.sub(r"\s+", " ", value)


def normalize_product_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().replace("’", "'").replace("‘", "'"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--retrieved-at", required=True)
    args = parser.parse_args()

    raw = args.source.read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()
    recipes: list[dict] = []
    cookbook_names: set[str] = set()
    for line_number, raw_line in enumerate(raw.decode("utf-8").splitlines(), 1):
        line = raw_line.rstrip("\r")
        header = COOKBOOK_RE.match(line)
        if header and header.group("name") != "Cookbooks":
            cookbook_names.add(normalize_cookbook_name(header.group("name")))
        match = RECIPE_RE.match(line)
        if not match:
            continue
        recipe_id = int(match.group("recipe_id"))
        product = normalize_product_name(match.group("product"))
        cookbook = normalize_cookbook_name(match.group("cookbook"))
        recipes.append({
            "sourceRecipeId": recipe_id,
            "productName": product,
            "cookbookName": cookbook,
            "sourceLine": line_number,
            "productQuantity": None,
            "productQuantityStatus": "not_stated_in_source",
            "ingredients": [],
            "ingredientsStatus": "not_present_in_source",
        })

    if not recipes:
        raise SystemExit("Smithbox source yielded no cookbook recipes")
    ids = [recipe["sourceRecipeId"] for recipe in recipes]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate cookbook recipe event flag ids")
    for recipe in recipes:
        cookbook_series = re.sub(r"\s+\[\d+\]$", "", recipe["cookbookName"])
        if cookbook_series not in cookbook_names:
            # The source has a few section-name omissions/typos.  Keep the
            # recipe but report the mismatch in the artifact for audit.
            recipe["cookbookHeaderStatus"] = "not_seen_as_header"
        else:
            recipe["cookbookHeaderStatus"] = "header_seen"

    payload = {
        "schema": "errn-smithbox-cookbook-recipes@1",
        "built_at": args.retrieved_at,
        "source": {
            "url": args.source_url,
            "commit": args.source_commit,
            "retrieved_at": args.retrieved_at,
            "source_file": str(args.source),
            "sha256": sha256,
            "policy": (
                "Recipe product and cookbook unlock evidence are copied from "
                "the public event-flag index; material quantities and output "
                "counts remain explicitly unknown when absent from that source."
            ),
        },
        "stats": {
            "recipeCount": len(recipes),
            "cookbookCount": len(cookbook_names),
            "headerMatchedRecipeCount": sum(
                recipe["cookbookHeaderStatus"] == "header_seen" for recipe in recipes
            ),
            "ingredientsPresentCount": sum(bool(recipe["ingredients"]) for recipe in recipes),
        },
        "recipes": recipes,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(payload["stats"], ensure_ascii=False))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
