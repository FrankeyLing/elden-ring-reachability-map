# Official Chinese Display

**Language**: English · [中文](CHINESE-LOCALIZATION.zh-CN.md)

The page displays FromSoftware official Simplified-Chinese fields by default (`data/v1/zh-cn/official-zh-mapping.json`):

- **Official text source**: assembled from the official multilingual texts in the local game data — 894,467 bilingual records in total (the build script `scripts/build-official-fmg-index.py` can regenerate the intermediate index; it is not committed).
- **Mapping rules** (`scripts/build-official-zh-mapping.py`): whole-field official match → official Chinese; official main name + official whitelisted suffix (升降机/棺木/传送门/赐福 etc.) → composite; official main name + no official suffix → partial Chinese with English remainder; no official text at all → English kept and listed in the audit's uncovered set (no invented translations).
- **Manually verified patches** (`scripts/zh-patch-manual.json`): 18 frequent condition names reference official NpcName/PlaceName/GoodsName entries verbatim; the build verifies each patch's official source and that template static words come verbatim from the original English field.
- **Coverage**: node region 100%, label 98.7% (736/746), condition label 94.4% (167/177); 10 custom topology nodes and 10 custom conditions have no official name and explicitly keep English.
- **Search**: official Chinese supported with bidirectional substring aliases (typing "玛利喀斯" finds "「黑剑」玛利喀斯"; typing "史东薇尔正门" finds "史东薇尔").
