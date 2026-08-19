#!/usr/bin/env python3
"""Elden Ring Reachability Map 发布脚本。

把"全量地图可达性查询"所需的运行时文件打包为一个 7z 发布包：

    Releases/Release-<时间戳>.7z

打包范围 = 整个仓库减去版本控制与构建产物（含 server、全部前端、以及
data/v1 下玩家主界面与研究控制台所需的全部数据：packages、zh-cn、正式图、
本地证据实体 local-*.json、在线快照 source-snapshots/ 等）。

依赖 7-Zip 命令行（7z）。脚本会先在 PATH 中查找，再回退到 Windows 常见
安装路径。

用法:
    python release.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASES_DIR = ROOT / "Releases"

# 相对于仓库根、递归排除的条目（传给 7z 的 -xr! 模式）。
EXCLUDE_PATTERNS = [
    ".git",
    "Releases",
    "__pycache__",
    ".runtime",
    ".playwright-mcp",
    "node_modules",
    "*.pyc",
    "*.7z",
]

SEVENZIP_CANDIDATES = [
    shutil.which("7z"),
    shutil.which("7za"),
    shutil.which("7zr"),
    r"C:\Program Files\7-Zip\7z.exe",
    r"C:\Program Files (x86)\7-Zip\7z.exe",
]


def find_7z() -> Path | None:
    """Locate a 7-Zip executable, first via PATH then common install dirs."""
    for candidate in SEVENZIP_CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file():
            return path
    return None


def main() -> int:
    seven_zip = find_7z()
    if seven_zip is None:
        print("错误：找不到 7-Zip。请安装 7-Zip，或将其加入 PATH。", file=sys.stderr)
        print("已尝试以下位置：", file=sys.stderr)
        for candidate in SEVENZIP_CANDIDATES:
            print(f"  {candidate}", file=sys.stderr)
        return 1

    RELEASES_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = RELEASES_DIR / f"Release-{timestamp}.7z"

    args = [str(seven_zip), "a", "-t7z", str(output), "."]
    for pattern in EXCLUDE_PATTERNS:
        args.append(f"-xr!{pattern}")

    print(f"7-Zip : {seven_zip}")
    print(f"输出  : {output}")
    print(f"排除  : {', '.join(EXCLUDE_PATTERNS)}")
    print("打包中……")

    result = subprocess.run(args, cwd=str(ROOT))
    if result.returncode != 0:
        print(f"打包失败：7z 退出码 {result.returncode}", file=sys.stderr)
        return result.returncode

    if not output.is_file():
        print(f"打包失败：未生成 {output}", file=sys.stderr)
        return 1

    size_mib = output.stat().st_size / (1024 * 1024)
    print(f"完成：{output}（{size_mib:.1f} MB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
