#!/usr/bin/env python3
"""Build the official-Chinese (zh-CN) field mapping for the formal graph (v2).

Only FromSoftware official Simplified-Chinese texts (extracted from the copied
game message binders, engus+zhocn) are used as translation sources. The tool
never invents translations.

Mapping levels:
  official   — the whole field text matches an official entry exactly
               (including word-order normalization and plural merging)
  official_bracket_main — official bracket-main name (+ official bracket content when known)
  official_slash_parts / official_comma_parts / official_to_parts
  composite  — official main name + official whitelisted suffix words
  partial    — partially official (some segments stay English because no
               official text exists for them)
  uncovered  — no official text covers the field; kept in English and reported

Output: data/v1/zh-cn/official-zh-mapping.json

Usage:
    python scripts/build-official-zh-mapping.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SUFFIX_WHITELIST = {
    "lift": "升降机",
    "elevator": "升降机",
    "coffin": "棺木",
    "sending gate": "传送门",
    "spiritspring": "灵魂气流",
    "waygate": "传送门",
    "grace": "赐福",
}
STOP_WORDS = {"of", "the", "and"}
PLURAL_MERGES = [
    ("men", "man"),
    ("virgins", "virgin"),
    ("champions", "champion"),
    ("beasts", "beast"),
]
QUALIFIER_WORDS = {
    "post-boss", "cleared", "return", "state", "upper", "lower", "sealed", "hidden",
    "arena", "descent", "exit", "entrance", "exterior", "interior", "approach",
    "passage", "bell", "throne", "gate", "north", "south", "east", "west", "main",
    "dark", "flooded", "ruined", "ancient", "great", "grand", "isolated", "divine",
    "forbidden", "consecrated", "moonlight", "eternal", "underground", "roadside",
    "sewer", "proscription", "frenzied", "flame", "rear", "side", "inner", "outer",
    "new", "old", "first", "second", "fourth", "seventh", "third", "eighth", "loft",
}


def is_zh(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def norm(text: str) -> str:
    # strip punctuation so "Ordina, Liturgical Town" == "Ordina Liturgical Town"
    cleaned = re.sub(r"[,.;:'\"]", "", text or "")
    return re.sub(r"\s+", " ", cleaned.strip().lower())


def wordset(text: str) -> tuple[str, ...]:
    return tuple(sorted(w for w in norm(text).split() if w not in STOP_WORDS))


def merge_plural(text: str) -> str:
    words = text.split()
    if not words:
        return text
    last = words[-1].lower()
    for plural, singular in PLURAL_MERGES:
        if last == plural:
            return " ".join(words[:-1] + [singular])
        if last.endswith(plural):
            return " ".join(words[:-1] + [last[: -len(plural)] + singular])
    return text


class OfficialDictionary:
    def __init__(self, fmg_index_path: Path):
        data = json.loads(fmg_index_path.read_text(encoding="utf-8"))
        pairs: dict[tuple[str, int], list[tuple[str, str]]] = defaultdict(list)
        for record in data.get("records", []):
            fmg_name = record["fmg"].replace("\\", "/").split("/")[-1]
            pairs[(fmg_name, record["id"])].append((record["language"], record["text"]))

        self.zho_by_eng: dict[str, set[str]] = defaultdict(set)
        self.sources: dict[str, list[dict]] = defaultdict(list)
        for (fmg_name, entry_id), lang_texts in pairs.items():
            eng = [t for lang, t in lang_texts if lang == "engus" and t and t.strip() and not is_zh(t)]
            zho = [t for lang, t in lang_texts if lang == "zhocn" and t and t.strip() and is_zh(t)]
            if not eng or not zho:
                continue
            for z in zho:
                self.zho_by_eng[eng[0].strip()].add(z.strip())
                self.sources[eng[0].strip()].append({"fmg": fmg_name, "id": entry_id, "zh": z.strip()})

        self.nzho_by_neng: dict[str, set[str]] = {}
        for e, zs in self.zho_by_eng.items():
            self.nzho_by_neng.setdefault(norm(e), set()).update(zs)
        self.wordset_index: dict[tuple, set[str]] = defaultdict(set)
        for e, zs in self.zho_by_eng.items():
            for z in zs:
                self.wordset_index[wordset(e)].add(z)

    def lookup(self, text: str) -> set[str]:
        if not text:
            return set()
        found = self.nzho_by_neng.get(norm(text), set())
        if found:
            return found
        found = self.wordset_index.get(wordset(text), set())
        if found:
            return found
        merged = merge_plural(text)
        if merged != text:
            found = self.nzho_by_neng.get(norm(merged), set())
            if found:
                return found
            found = self.wordset_index.get(wordset(merged), set())
        return found


def map_field(text: str, dictionary: OfficialDictionary) -> dict:
    if not text or is_zh(text):
        return {"zh": text, "level": "already_zh", "sources": []}
    level, zh = match_full(text, dictionary)
    if level:
        return {"zh": zh, "level": level, "sources": []}
    composite, composite_level = match_composite(text, dictionary)
    if composite:
        return {"zh": composite, "level": composite_level, "sources": []}
    return {"zh": text, "level": "uncovered", "sources": []}


def apply_patches(mapping: dict, patch_path: Path, dictionary: OfficialDictionary) -> int:
    """Apply the manually verified patch table (template form).

    Every {n} placeholder is replaced with the verbatim official Chinese text
    of sources[n]. Every other character in the template must appear verbatim
    in the original English field (status suffixes stay English); this
    guarantees no invented translation is ever introduced.
    """
    patch = json.loads(patch_path.read_text(encoding="utf-8"))
    applied = 0
    for kind in ("conditions", "nodes", "edges"):
        for key, fields in patch.get(kind, {}).items():
            target = mapping.get(kind, {}).get(key)
            if target is None:
                raise ValueError(f"patch {kind}.{key} has no mapping entry")
            for field, entry in fields.items():
                template = entry["zh_template"]
                sources = entry.get("sources", [])
                zh_parts = []
                for index, source in enumerate(sources):
                    found = dictionary.zho_by_eng.get(
                        official_eng_by_id(dictionary, source), set()
                    )
                    if not found:
                        raise ValueError(
                            f"patch {kind}.{key}.{field} source not verified: "
                            f"{source} has no official zh entry"
                        )
                    zh_parts.append(next(iter(found)))
                for index in range(len(sources)):
                    template = template.replace("{%d}" % index, zh_parts[index])
                # remaining placeholder count must be zero
                if re.search(r"\{\d+\}", template):
                    raise ValueError(f"patch {kind}.{key}.{field} has unresolved placeholders")
                # static template words must appear verbatim in the original English field
                original = target[field]["zh"]
                static_text = entry["zh_template"]
                for index in range(len(sources)):
                    static_text = re.sub(r"\{\d+\}", " ", static_text)
                static_words = {w for w in norm(static_text).split() if w}
                original_words = set(norm(original).split())
                if not static_words.issubset(original_words):
                    raise ValueError(
                        f"patch {kind}.{key}.{field} template words not in original field: "
                        f"{sorted(static_words - original_words)}"
                    )
                target[field] = {
                    "zh": template,
                    "level": "official_patch",
                    "sources": [
                        {"fmg": s["fmg"], "id": s["id"], "zh": zh_parts[i]}
                        for i, s in enumerate(sources)
                    ],
                }
                applied += 1
    return applied


def official_eng_by_id(dictionary: OfficialDictionary, source: dict) -> str:
    """Return the official English text for (fmg, id) by scanning sources."""
    for eng, entries in dictionary.sources.items():
        for entry in entries:
            if entry["fmg"] == source["fmg"] and entry["id"] == source["id"]:
                return eng
    return ""


def pick(found: set[str]) -> str:
    return " / ".join(sorted(found))


def match_full(text: str, dictionary: OfficialDictionary) -> tuple[str | None, str | None]:
    """Whole-field official matching. Returns (level, zh) or (None, None)."""
    found = dictionary.lookup(text)
    if found:
        return "official", pick(found)

    bracket = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", text.strip())
    if bracket:
        main = bracket.group(1).strip()
        inner = bracket.group(2).strip()
        main_found = dictionary.lookup(main)
        inner_found = dictionary.lookup(inner) if inner else set()
        if main_found:
            if inner_found:
                return "official", f"{pick(main_found)}（{pick(inner_found)}）"
            return "official_bracket_main", pick(main_found)
        if inner_found:
            return "partial", f"{main}（{pick(inner_found)}）"

    if "/" in text:
        parts = [p.strip() for p in text.split("/")]
        zhs = [dictionary.lookup(p) for p in parts]
        if all(zhs):
            return "official_slash_parts", " / ".join(pick(z) for z in zhs)
        zh_known = [pick(z) for z, p in zip(zhs, parts) if z]
        if zh_known:
            return "partial", " / ".join(
                pick(z) if z else p for z, p in zip(zhs, parts)
            )

    if "," in text:
        parts = [p.strip() for p in text.split(",")]
        zhs = [dictionary.lookup(p) for p in parts]
        if all(zhs):
            return "official_comma_parts", " / ".join(pick(z) for z in zhs)
        zh_known = [pick(z) for z in zhs if z]
        if zh_known:
            return "partial", " / ".join(pick(z) if z else p for z, p in zip(zhs, parts))

    if " to " in text:
        parts = [p.strip() for p in re.split(r"\s+to\s+", text)]
        if len(parts) == 2:
            zhs = [dictionary.lookup(p) for p in parts]
            if all(zhs):
                return "official_to_parts", f"{pick(zhs[0])} → {pick(zhs[1])}"
            zh_known = [pick(z) for z in zhs if z]
            if zh_known:
                return "partial", f"{pick(zhs[0]) if zhs[0] else parts[0]} → {pick(zhs[1]) if zhs[1] else parts[1]}"
    return None, None


def match_composite(text: str, dictionary: OfficialDictionary) -> tuple[str | None, str | None]:
    """Official main name + whitelisted/qualified trailing words; or English
    prefix + official trailing phrase (partial, e.g. 'Academy Abductor Virgin')."""
    words = text.split()
    for split_at in range(len(words) - 1, 0, -1):
        main = " ".join(words[:split_at])
        found = dictionary.lookup(main)
        if not found:
            continue
        main_zh = pick(found)
        trailing = words[split_at:]
        trailing_phrase = " ".join(trailing).lower()
        if trailing_phrase in SUFFIX_WHITELIST:
            return f"{main_zh} {SUFFIX_WHITELIST[trailing_phrase]}", "composite"
        suffix_zh = []
        rest_en = []
        for word in trailing:
            if word.lower() in SUFFIX_WHITELIST:
                suffix_zh.append(SUFFIX_WHITELIST[word.lower()])
            else:
                rest_en.append(word)
        if suffix_zh:
            display = f"{main_zh} {' '.join(suffix_zh)}"
            if rest_en:
                display += f" ({' '.join(rest_en)})"
            return display, "composite"
        return f"{main_zh} {trailing_phrase}", "partial"

    # official trailing phrase with English prefix: 'Academy Abductor Virgin'
    for split_at in range(1, min(len(words), 4)):
        trailing = " ".join(words[split_at:])
        found = dictionary.lookup(trailing)
        if not found:
            continue
        prefix = " ".join(words[:split_at])
        return f"{prefix} {pick(found)}", "partial"
    return None, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=Path("data/v1/graph.json"))
    parser.add_argument("--fmg-index", type=Path, default=Path("data/v1/entities/official-fmg-bilingual-index.json"))
    parser.add_argument("--patch", type=Path, default=Path(__file__).with_name("zh-patch-manual.json"))
    parser.add_argument("--output", type=Path, default=Path("data/v1/zh-cn/official-zh-mapping.json"))
    args = parser.parse_args()

    graph = json.loads(args.graph.resolve().read_text(encoding="utf-8"))
    dictionary = OfficialDictionary(args.fmg_index.resolve())

    nodes_map: dict[str, dict] = {}
    edges_map: dict[str, dict] = {}
    conditions_map: dict[str, dict] = {}
    layers_map: dict[str, dict] = {}
    epochs_map: dict[str, dict] = {}

    for node in graph["nodes"]:
        nodes_map[node["id"]] = {
            field: map_field(node.get(field, ""), dictionary)
            for field in ("label", "region", "floor", "description")
        }
    for edge in graph["edges"]:
        edges_map[edge["id"]] = {
            field: map_field(edge.get(field, ""), dictionary)
            for field in ("mode", "note")
        }
    for condition in graph["conditions"]:
        conditions_map[condition["id"]] = {
            field: map_field(condition.get(field, ""), dictionary)
            for field in ("label", "hint")
        }
    for layer in graph.get("layers", []):
        layers_map[layer["id"]] = {"label": map_field(layer.get("label", ""), dictionary)}
    for epoch in graph.get("worldEpochs", []):
        epochs_map[epoch["id"]] = {"label": map_field(epoch.get("label", ""), dictionary)}

    applied = apply_patches(
        {"nodes": nodes_map, "edges": edges_map, "conditions": conditions_map},
        args.patch.resolve(),
        dictionary,
    )
    print(f"manual patches applied: {applied}")

    def count_levels(mapping: dict, field: str) -> dict:
        counts = defaultdict(int)
        for entry in mapping.values():
            counts[entry[field]["level"]] += 1
        return dict(counts)

    coverage = {
        "nodes": {field: count_levels(nodes_map, field) for field in ("label", "region", "floor", "description")},
        "edges": {field: count_levels(edges_map, field) for field in ("mode", "note")},
        "conditions": {field: count_levels(conditions_map, field) for field in ("label", "hint")},
        "layers": count_levels(layers_map, "label"),
        "epochs": count_levels(epochs_map, "label"),
    }

    output = {
        "schema": "elden-ring-official-zh-mapping@2",
        "source": {
            "graph": str(args.graph.resolve()),
            "fmgIndex": str(args.fmg_index.resolve()),
            "policy": "Only FromSoftware official Simplified-Chinese texts are used; no invented translations.",
            "levels": {
                "official": "whole field matches an official entry",
                "official_bracket_main": "official bracket-main name (bracket content official when known)",
                "official_slash_parts": "each slash segment official",
                "official_comma_parts": "each comma segment official",
                "official_to_parts": "'X to Y' both official",
                "composite": "official main name + official whitelisted suffix",
                "partial": "partially official; remaining segments kept in English",
                "uncovered": "no official text covers the field",
            },
        },
        "coverage": coverage,
        "nodes": nodes_map,
        "edges": edges_map,
        "conditions": conditions_map,
        "layers": layers_map,
        "epochs": epochs_map,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(coverage, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
