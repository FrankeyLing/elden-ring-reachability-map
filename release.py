#!/usr/bin/env python3
"""Build a release archive from tracked code plus explicit release data.

Generated JSON is deliberately not part of the source repository.  The
release manifest names the data files and directories that are copied into a
release staging tree.  This keeps private research snapshots and accidental
working-tree artifacts out of the archive.

Usage:
    python release.py --check
    python release.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASES_DIR = ROOT / "Releases"
RELEASE_DATA_MANIFEST_FILE = ROOT / "release-data-manifest.json"
GENERATED_RELEASE_MANIFEST = Path("data/v1/release-manifest.json")

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


def safe_relative_path(value: str) -> Path:
    """Validate a manifest path before it is joined to the staging root."""
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"release manifest path must stay inside the repository: {value!r}")
    return path


def load_release_manifest() -> dict:
    payload = json.loads(RELEASE_DATA_MANIFEST_FILE.read_text(encoding="utf-8"))
    if payload.get("schema") != "elden-ring-reachability-map/release-data-manifest@1":
        raise ValueError("unsupported release-data-manifest schema")
    if not isinstance(payload.get("largeJsonFiles"), list):
        raise ValueError("release-data-manifest.largeJsonFiles must be a list")
    if not isinstance(payload.get("releaseDirectories"), list):
        raise ValueError("release-data-manifest.releaseDirectories must be a list")
    for record in payload["largeJsonFiles"]:
        safe_relative_path(record["path"])
        if not str(record["path"]).lower().endswith(".json"):
            raise ValueError(f"release data file is not JSON: {record['path']!r}")
    for record in payload["releaseDirectories"]:
        safe_relative_path(record["path"])
    return payload


def git_tracked_paths() -> list[Path]:
    """Return tracked paths only; ignored local research files are excluded."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=str(ROOT),
        check=True,
        capture_output=True,
    )
    return [
        Path(raw.decode("utf-8"))
        for raw in result.stdout.split(b"\0")
        if raw
    ]


def tracked_large_json_files(manifest: dict) -> list[tuple[Path, int]]:
    threshold_mib = float(manifest.get("largeJsonThresholdMiB", 5))
    threshold_bytes = int(threshold_mib * 1024 * 1024)
    large_files = []
    for relative_path in git_tracked_paths():
        if relative_path.suffix.lower() != ".json":
            continue
        absolute_path = ROOT / relative_path
        if not absolute_path.is_file():
            continue
        size = absolute_path.stat().st_size
        if size > threshold_bytes:
            large_files.append((relative_path, size))
    return large_files


def required_release_inputs(manifest: dict) -> list[Path]:
    required = []
    for record in manifest["largeJsonFiles"]:
        if record.get("required", True):
            required.append(safe_relative_path(record["path"]))
    for record in manifest["releaseDirectories"]:
        if record.get("required", True):
            required.append(safe_relative_path(record["path"]))
    return required


def validate_inputs(manifest: dict) -> None:
    tracked_large = tracked_large_json_files(manifest)
    if tracked_large:
        details = ", ".join(
            f"{path.as_posix()} ({size / (1024 * 1024):.1f} MiB)"
            for path, size in tracked_large
        )
        raise RuntimeError(
            "source repository still tracks generated JSON above the release "
            f"threshold: {details}"
        )

    missing = []
    for relative_path in required_release_inputs(manifest):
        if not (ROOT / relative_path).exists():
            missing.append(relative_path.as_posix())
    if missing:
        raise FileNotFoundError(
            "required release data is missing from the local release input "
            f"directory: {', '.join(missing)}"
        )


def copy_tracked_code(stage_root: Path) -> None:
    for relative_path in git_tracked_paths():
        source = ROOT / relative_path
        if not source.is_file():
            continue
        destination = stage_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def copy_release_data(stage_root: Path, manifest: dict) -> list[Path]:
    copied_files = []
    for record in manifest["largeJsonFiles"]:
        relative_path = safe_relative_path(record["path"])
        source = ROOT / relative_path
        if not source.is_file():
            if record.get("required", True):
                raise FileNotFoundError(f"release data file not found: {relative_path}")
            continue
        destination = stage_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied_files.append(relative_path)

    for record in manifest["releaseDirectories"]:
        relative_path = safe_relative_path(record["path"])
        source = ROOT / relative_path
        if not source.is_dir():
            if record.get("required", True):
                raise FileNotFoundError(f"release data directory not found: {relative_path}")
            continue
        destination = stage_root / relative_path
        shutil.copytree(source, destination, dirs_exist_ok=True)
        copied_files.extend(
            path.relative_to(ROOT)
            for path in source.rglob("*")
            if path.is_file()
        )
    return sorted(set(copied_files))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_generated_release_manifest(stage_root: Path, copied_files: list[Path]) -> None:
    records = []
    for relative_path in copied_files:
        path = stage_root / relative_path
        records.append(
            {
                "path": relative_path.as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    output = stage_root / GENERATED_RELEASE_MANIFEST
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schema": "elden-ring-reachability-map/release-manifest@1",
                "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "sourceManifest": "release-data-manifest.json",
                "files": records,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def build_archive(seven_zip: Path, manifest: dict) -> Path:
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = RELEASES_DIR / f"Release-{timestamp}.7z"

    with tempfile.TemporaryDirectory(prefix="elden-ring-release-") as temporary_directory:
        stage_root = Path(temporary_directory)
        copy_tracked_code(stage_root)
        copied_files = copy_release_data(stage_root, manifest)
        write_generated_release_manifest(stage_root, copied_files)

        args = [str(seven_zip), "a", "-t7z", str(output), "."]
        print(f"7-Zip : {seven_zip}")
        print(f"输出  : {output}")
        print(f"代码  : {len(git_tracked_paths())} 个 Git 追踪文件")
        print(f"数据  : {len(copied_files)} 个发布数据文件")
        print("打包中……")
        result = subprocess.run(args, cwd=str(stage_root))
        if result.returncode != 0:
            raise RuntimeError(f"7-Zip exited with code {result.returncode}")

    if not output.is_file():
        raise RuntimeError(f"release archive was not created: {output}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a release archive without tracking generated JSON in Git.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate Git tracking policy and required release inputs without creating an archive",
    )
    args = parser.parse_args()

    try:
        manifest = load_release_manifest()
        validate_inputs(manifest)
        print("检查通过：Git 未追踪超过发布阈值的 JSON，发布数据输入齐全。")
        if args.check:
            return 0
        seven_zip = find_7z()
        if seven_zip is None:
            print("错误：找不到 7-Zip。请安装 7-Zip，或将其加入 PATH。", file=sys.stderr)
            return 1
        output = build_archive(seven_zip, manifest)
        size_mib = output.stat().st_size / (1024 * 1024)
        print(f"完成：{output}（{size_mib:.1f} MiB）")
        return 0
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"发布检查失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
