# 官方中文显示

**语言**: [English](../README.md) · [中文](./CHINESE-LOCALIZATION.zh-CN.md)


- 官方文本来源：依据本地游戏数据中的官方多语言文本整理，共 894,467 条双语记录（构建脚本 `scripts/build-official-fmg-index.py` 可重建中间索引，不提交仓库）。
- 映射规则（`scripts/build-official-zh-mapping.py`）：整字段官方匹配 → 官方中文；官方主名 + 官方白名单后缀（升降机/棺木/传送门/赐福等）→ 组合；主名官方 + 无官方后缀 → 部分中文 + 英文残留；无任何官方文本 → 保留英文并列入审计 uncovered 清单。
- 人工核对补丁（`scripts/zh-patch-manual.json`）：18 个高频条件名逐字引用官方 NpcName/PlaceName/GoodsName 条目，构建时校验每个补丁的官方来源与模板静态词必须逐字来自原英文字段。
- 覆盖：节点 region 100%、label 98.7%（736/746）、条件 label 94.4%（167/177）；10 个自定义拓扑节点与 10 个自定义条件在官方文本中不存在名称，显式保留英文。
- 搜索支持官方中文（含双向子串：搜"玛利喀斯"命中"「黑剑」玛利喀斯"，搜"史东薇尔正门"命中"史东薇尔"）。

