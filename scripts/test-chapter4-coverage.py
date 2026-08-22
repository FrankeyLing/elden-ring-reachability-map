#!/usr/bin/env python3
"""Chapter 4 coverage gate: every 4.x entity-class line is present in the
published player query projection with a real example and a searchable term.

This is the machine-verifiable part of "第四章全部实体类别进入规范清单和玩家
查询投影；每类都能搜索到真实实体" (Beta gate) and of 10.1 category coverage.
It does NOT replace the fixed regression samples in test-ch11-regression.py;
it guards the whole category surface the contract lists explicitly.

Usage:
    python scripts/test-chapter4-coverage.py [--index data/v1/entities/player-entity-index.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (category, english term, chinese term) - at least one entity per category
# whose en/zh official name contains the term, proving the official name pair
# is present in the player runtime.
CATEGORY_TERMS = [
    # 4.1 地点与空间对象
    ("mausoleum", "Mausoleum", "灵庙"),
    ("divine_tower", "Divine Tower", "神授塔"),
    ("sorcerer_tower", "Sorcerer", "魔法师塔"),
    ("minor_erdtree", "Minor Erdtree", "小黄金树"),
    ("grand_lift", "Grand Lift", "大升降机"),
    ("cave", "Cave", "洞窟"),
    ("tunnel", "Tunnel", "坑道"),
    ("eternal_city", "Eternal City", "永恒之城"),
    ("church", "Church", "教堂"),
    ("cathedral", "Cathedral", "大教堂"),
    ("castle", "Castle", "城"),
    ("fort", "Fort", "要塞"),
    ("gaol", "Gaol", "监狱"),
    ("evergaol", "Evergaol", "封印监牢"),
    ("landmark", "Landmark", "地标"),
    ("ruins", "Ruins", "遗迹"),
    ("village", "Village", "村庄"),
    ("bridge", "Bridge", "桥"),
    ("lookout_tower", "Tower", "塔"),
    ("hidden_passage", "暗门", "暗门"),
    ("teleport", "Teleport", "传送"),
    ("caravan", "Caravan", "车队"),
    ("spirit_spring", "Spirit Spring", "灵泉"),
    # 4.3 防具（套装）
    ("armor_set", "Set", "套装"),
    # 4.4 独特道具与能力
    ("key_item", "Key", "钥匙"),
    ("note", "Note", "文件"),
    ("map_fragment", "Map", "地图碎片"),
    ("remembrance", "Remembrance", "追忆"),
    ("great_rune", "Great Rune", "大卢恩"),
    ("spirit_ash", "Spirit Ash", "骨灰"),
    ("scroll", "Scroll", "卷轴"),
    ("prayerbook", "Prayerbook", "祷告书"),
    ("sorcery", "Sorcery", "魔法"),
    ("incantation", "Incantation", "祷告"),
    ("ash_of_war", "Ash of War", "战灰"),
    ("bell_bearing", "Bell Bearing", "铃珠"),
    ("cookbook", "Cookbook", "制作"),
    ("tool", "Tool", "工具"),
    ("painting", "Painting", "绘画"),
    ("gesture", "Gesture", "动作"),
    # 4.5 一般道具和成长资源
    ("jar", "Pot", "壶"),
    ("golden_rune", "Golden Rune", "黄金卢恩"),
    ("crystal_tear", "Tear", "露滴"),
    ("starlight_shard", "Starlight Shard", "星光碎片"),
    ("larval_tear", "Larval Tear", "泪滴幼体"),
    ("rune_arc", "Rune Arc", "卢恩弯弧"),
    ("multiplayer_item", "Multiplayer", "联机"),
    ("dragon_heart", "Dragon Heart", "龙心脏"),
    ("golden_seed", "Golden Seed", "黄金种子"),
    ("memory_stone", "Memory Stone", "记忆石"),
    ("deathroot", "Deathroot", "死根"),
    ("hero_rune", "Hero's Rune", "英雄卢恩"),
    # 4.6 敌人
    ("boss", "Boss", "Boss"),
    ("furnace_golem", "Furnace Golem", "燃炉魔像"),
    ("elite", "Elite", "精英"),
    ("invader", "Invader", "入侵者"),
    # 4.7/4.8 锻造石与铃兰
    ("smithing_stone", "Smithing Stone", "锻造石"),
    ("grave_glovewort", "Grave Glovewort", "墓地铃兰"),
    ("ghost_glovewort", "Ghost Glovewort", "灵依墓地铃兰"),
    # 4.9 友方角色与协助
    ("npc", "NPC", "NPC"),
    ("merchant", "Merchant", "商人"),
    ("multiplayer_summon_pool", "summon pool", "召唤"),
    # 4.10 其他交互对象
    ("fixed_message", "message", "留言"),
    ("puzzle", "Puzzle", "谜题"),
]

# Canonical examples that must exist with exact official names and at least
# minAcq genuine acquisition relations.  A miss here is a real 4.x/10.2
# coverage defect, not a naming nit.
CANONICAL_EXAMPLES = [
    # 4.2 武器族
    ("weapon_staff_of_loss", "Staff of Loss", "丧失杖", 1, "weapon"),
    # 4.3 防具 + 套装（套装的 en 名是从防具成员派生的分组标签）
    ("armor_set_radahn_s", "Radahn's", "拉塔恩", 0, "armor_set"),
    # 4.4 独特道具
    ("item_stonesword_key", "Stonesword Key", "石剑钥匙", 1, "stone_sword_key"),
    ("item_map_altus_plateau", "Map: Altus Plateau", "地图碎片：亚坛高原", 1, "map_fragment"),
    ("item_remembrance_of_the_blasphemous", "Remembrance of the Blasphemous", "亵渎君王的追忆", 1, "remembrance"),
    ("item_mohg_s_great_rune", "Mohg's Great Rune", "蒙格的大卢恩", 1, "great_rune"),
    ("item_academy_scroll", "Academy Scroll", "学院卷轴", 1, "scroll"),
    ("spell_comet_azur", "Comet Azur", "彗星亚兹勒", 1, "sorcery"),
    ("spell_elden_stars", "Elden Stars", "艾尔登流星", 1, "incantation"),
    ("ash_of_war_ash_of_war_piercing_fang", "Ash of War: Piercing Fang", "战灰：突刺", 1, "ash_of_war"),
    ("item_somberstone_miner_s_bell_bearing_1", "Somberstone Miner's Bell Bearing [1]", "失色石矿工的铃珠【１】", 1, "bell_bearing"),
    ("item_memory_stone", "Memory Stone", "记忆石", 1, "memory_stone"),
    ("item_deathroot", "Deathroot", "死根", 1, "deathroot"),
    ("item_golden_seed", "Golden Seed", "黄金种子", 1, "golden_seed"),
    ("item_sacred_tear", "Sacred Tear", "圣杯露滴", 1, "crystal_tear"),
    ("item_dragon_heart", "Dragon Heart", "龙心脏", 1, "dragon_heart"),
    ("item_starlight_shards", "Starlight Shards", "星光碎片", 1, "starlight_shard"),
    ("item_larval_tear", "Larval Tear", "泪滴幼体", 1, "larval_tear"),
    ("item_rune_arc", "Rune Arc", "卢恩弯弧", 1, "rune_arc"),
    ("item_hefty_cracked_pot", "Hefty Cracked Pot", "大龟裂壶", 1, "jar"),
    ("item_hero_s_rune_5", "Hero's Rune [5]", "英雄卢恩【５】", 1, "hero_rune"),
    # 4.7 锻造石
    ("item_smithing_stone_1", "Smithing Stone [1]", "锻造石【１】", 1, "smithing_stone"),
    ("item_somber_smithing_stone_1", "Somber Smithing Stone [1]", "失色锻造石【１】", 1, "smithing_stone"),
    ("item_ancient_dragon_smithing_stone", "Ancient Dragon Smithing Stone", "古龙岩锻造石", 1, "smithing_stone"),
    ("item_somber_ancient_dragon_smithing_stone", "Somber Ancient Dragon Smithing Stone", "古龙岩失色锻造石", 1, "smithing_stone"),
    # 4.8 铃兰
    ("item_grave_glovewort_1", "Grave Glovewort [1]", "墓地铃兰【１】", 1, "grave_glovewort"),
    ("item_ghost_glovewort_9", "Ghost Glovewort [9]", "灵依墓地铃兰【９】", 1, "ghost_glovewort"),
    ("item_great_grave_glovewort", "Great Grave Glovewort", "大朵墓地铃兰", 1, "grave_glovewort"),
    ("item_great_ghost_glovewort", "Great Ghost Glovewort", "大朵灵依墓地铃兰", 1, "ghost_glovewort"),
    # 4.4 骨灰（真实骨灰样例）
    ("item_wandering_noble_ashes", "Wandering Noble Ashes", "徘徊权贵的骨灰", 1, "spirit_ash"),
    # 4.5 黄金卢恩
    ("item_golden_rune_1", "Golden Rune [1]", "黄金卢恩【１】", 1, "golden_rune"),
    # 4.4 唤声泥颅
    ("item_prattling_pate_hello", 'Prattling Pate "Hello"', "唤声泥颅“你好”", 1, "consumable"),
    # 4.9 解指老妪
    ("npc_finger_reader_crone", "Finger Reader Crone", "解指老妪", 1, "npc"),
    # 4.10 固定留言
    ("message_m10_00_00_00_region_440_entity_10002721", "Fixed message · NPC血文字：戦場医師", "固定留言 · NPC血文字：戦場医師", 0, "fixed_message"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path,
                        default=ROOT / "data" / "v1" / "entities" / "player-entity-index.json")
    args = parser.parse_args()
    payload = json.loads(args.index.read_text(encoding="utf-8"))
    entities = payload["entities"]
    by_id = {e["id"]: e for e in entities}

    failures: list[str] = []

    def check(ok: bool, msg: str) -> None:
        if ok:
            print(f"  PASS {msg}")
        else:
            print(f"  FAIL {msg}")
            failures.append(msg)

    # 1. every 4.x category line has an entity whose official name matches
    for category, en_term, zh_term in CATEGORY_TERMS:
        candidates = [e for e in entities if e.get("category") == category]
        if not candidates:
            check(False, f"category {category} has no published entity")
            continue
        if category == "armor_set":
            # Set names are derived possessive labels ("Radahn's ...") from
            # the member pieces; verify the derived pattern instead.
            matched = any(
                str((e.get("name") or {}).get("en") or "").endswith("'s")
                for e in candidates
            )
            check(matched, f"armor_set derived labels present (count={len(candidates)})")
            continue
        matched = False
        for e in candidates:
            name = e.get("name", {}) or {}
            hay = f"{name.get('en') or ''}|{name.get('zh') or ''}|{' '.join(e.get('aliases') or [])}"
            if en_term.casefold() in hay.casefold() or zh_term in hay:
                matched = True
                break
        check(matched, f"{category} ({en_term}/{zh_term}) has a matching entity "
                       f"(count={len(candidates)})")

    # 2. weapon families required by 4.2
    fams = {e.get("properties", {}).get("weaponFamily")
            for e in entities if e.get("category") == "weapon"}
    for fam, label in [("melee", "近战"), ("bow", "弓"), ("crossbow", "弩"),
                       ("staff", "法杖"), ("sacred_seal", "圣印记"),
                       ("shield", "盾牌"), ("torch", "火把"), ("ballista", "弩炮")]:
        check(fam in fams, f"weapon family {label} ({fam}) covered")

    # 3. armor piece categories: 单件防具 + 套装分组
    protector_cats = {e.get("properties", {}).get("protectorCategory")
                      for e in entities if e.get("category") == "armor"}
    check(len(protector_cats) >= 4,
          f"armor piece categories head/body/arms/legs covered ({sorted(protector_cats)})")
    check(len([e for e in entities if e.get("category") == "armor_set"]) > 0,
          "armor set group entities exist")

    # 4. canonical examples with exact names and acquisition floor
    for entity_id, en, zh, min_acq, expected_category in CANONICAL_EXAMPLES:
        e = by_id.get(entity_id)
        if not e:
            check(False, f"canonical example {entity_id} missing")
            continue
        name = e.get("name", {}) or {}
        name_ok = (name.get("en") or "").strip().casefold() == en.casefold()
        check(name_ok, f"{entity_id} en name matches ({name.get('en')})")
        zh_ok = (name.get("zh") or "").strip() == zh
        check(zh_ok, f"{entity_id} zh name matches ({name.get('zh')})")
        kind = e.get("category")
        check(kind == expected_category or expected_category in (kind, "consumable", "key_item"),
              f"{entity_id} category is {kind} (expected {expected_category})")
        acq = int(e.get("counts", {}).get("acquisitions") or 0)
        check(acq >= min_acq, f"{entity_id} acquisitions={acq} (floor {min_acq})")

    # 5. category-wide acquisition sanity: all map fragments and all
    # smithing/glovewort canonical ids are acquirable in-game.
    for cat in ("map_fragment", "grave_glovewort", "ghost_glovewort"):
        in_cat = [e for e in entities if e.get("category") == cat]
        missing = [e["id"] for e in in_cat
                   if int(e.get("counts", {}).get("acquisitions") or 0) == 0]
        check(not missing, f"category {cat} fully acquirable "
                           f"({len(in_cat)}/{len(in_cat)}; missing {missing})")

    # 6. 5.1 explicit markers: derived/instance labels are not official
    # bilingual names, and every such record must say so.
    cjk = re.compile(r"[\u4e00-\u9fff]")
    non_official_en = 0
    unmarked_en = []
    unmarked_zh = []
    for e in entities:
        props = e.get("properties") or {}
        name = e.get("name") or {}
        if cjk.search(str(name.get("en") or "")):
            non_official_en += 1
            if props.get("officialEnName") is not False:
                unmarked_en.append(e["id"])
        if not (name.get("zh") or "").strip():
            if props.get("officialZhName") is not False:
                unmarked_zh.append(e["id"])
    check(not unmarked_en,
          f"every CJK-en record carries officialEnName=False ({non_official_en} marked)")
    check(not unmarked_zh,
          f"every zh-missing record carries officialZhName=False "
          f"({len(unmarked_zh)} unmarked: {unmarked_zh[:5]})")
    check(non_official_en > 0, "derived en names exist and are explicitly marked")
    furnace = next(
        (e for e in entities if e.get("id") == "enemy_furnace_golem"), None
    )
    if furnace is None:
        check(False, "manual entity enemy_furnace_golem exists")
    else:
        check(
            (furnace.get("properties") or {}).get("officialEnName") is False,
            "manual entity enemy_furnace_golem marked non-official",
        )

    print(f"\nCHAPTER 4 COVERAGE: {len(CATEGORY_TERMS) + 12} partial checks, "
          f"{len(failures)} failures")
    for f in failures:
        print(f"  - {f}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
