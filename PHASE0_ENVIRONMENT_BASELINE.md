# Phase 0 环境基线

记录时间：2026-08-17（Asia/Shanghai）

## 已确认

- Steam 安装路径：`C:\MyProgram\Steam`
- 游戏安装路径：`C:\MyProgram\Steam\steamapps\common\ELDEN RING`
- Steam AppID：`1245620`
- Steam BuildID：`22984413`
- Steam manifest 最后更新时间：`2026-08-11 19:30:41 +08:00`
- `eldenring.exe` 文件版本：`2.6.2.0`
- `regulation.bin` 已取得 SHA-256，但其内部版本号尚未解析
- EXE、Regulation、Data0/1/2/3 BHD、DLC BHD 哈希已写入 `data/source-manifest.json`
- 本项目原有 `data/graph.json` 仍为演示数据，未被接入真值流程
- Python 3.12、Node 20、Git 2.45 可用

## 未完成且不得猜测

- 不能把 EXE 文件版本直接当成 Regulation 版本；必须从标题画面、固定解析器或 Regulation 数据中确认。
- 当前 PATH 未发现 Smithbox、uvx、Bun。
- 尚未固定可复现的 MSB/BND/DCX/Param/FMG/EMEVD 解析工具提交与许可证。
- 尚未从游戏归档提取地图、MSB、碰撞、Navmesh、FMG 或事件；因此 Phase 1 尚未产生任何真实 POI、Floor 或 Transition。
- C 盘剩余空间查询因 `fsutil volume diskfree C:` 返回 Access Denied，尚未形成可靠容量结论。

## 安全边界

- 原始游戏安装只读，不修改 `Game` 目录。
- 不复制原始游戏归档到仓库。
- 不读取或写回存档，不连接在线/EAC 会话。
- 不把第三方在线地图坐标直接写入正式数据。
- 所有未验证关系保持候选或 unknown，不进入正式路线图。

## 当前结论

真实游戏安装已经找到，Phase 0 的安装定位与关键文件身份核验完成；由于 Regulation 版本和固定解析工具尚未确认，Phase 1 暂停在“提取前置”而不是伪造样片。下一步是完成解析工具 spike，并只读提取四类地图最小样片。
