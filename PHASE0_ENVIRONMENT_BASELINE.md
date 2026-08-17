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
- 尚未从游戏归档提取地图、MSB、碰撞、Navmesh、FMG 或事件；因此 Phase 1B 尚未产生任何 `local_game_verified` POI、Floor 或 Transition。
- C 盘剩余空间查询因 `fsutil volume diskfree C:` 返回 Access Denied，尚未形成可靠容量结论。

## 安全边界

- 原始游戏安装只读，不修改 `Game` 目录。
- 不复制原始游戏归档到仓库。
- 不读取或写回存档，不连接在线/EAC 会话。
- 第三方在线坐标只能连同来源坐标系、revision、许可证和证据等级进入 `Online Verified V1`，不得冒充游戏原始 X/Y/Z 或 `local_game_verified`。
- 所有未验证关系保持候选或 unknown，不进入正式路线图。

## 当前结论

真实游戏安装已经找到，Phase 0 的安装定位与关键文件身份核验完成。由于 Regulation 版本和固定解析工具尚未确认，Phase 1B 本地真值提取仍停在前置门；但这不阻塞 Phase 1A：当前可按 `ONLINE_FIRST_V1_PLAN.md` 从许可明确、版本可追溯的在线文本/JSON Source Snapshot 建立真实可用 V1。游戏运行时只执行 `GAMING_SAFE + ONLINE_INGEST`，本地工具 spike、游戏归档读取和四类地图样片延后到合格空闲/快照窗口。
