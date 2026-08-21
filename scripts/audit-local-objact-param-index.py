#!/usr/bin/env python3
"""Audit the version-matched local ObjActParam snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REQUIRED_FIELDS = {
    "actionEnableMsgId",
    "actionFailedMsgId",
    "spQualifiedPassEventFlag",
    "playerAnimId",
    "chrAnimId",
    "validDist",
    "spQualifiedId",
    "spQualifiedId2",
    "objDummyId",
    "isEventKickSync",
    "objAnimId",
    "validPlayerAngle",
    "spQualifiedType",
    "spQualifiedType2",
    "validObjAngle",
    "chrSorbType",
    "eventKickTiming",
    "actionButtonParamId",
    "enableTreasureDelaySec",
    "preActionSfxDmypolyId",
    "preActionSfxId",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    source = payload["source"]
    status = payload["status"]
    rows = payload.get("rows", [])
    assert payload["schema"] == "elden-ring-local-objact-param-index@1"
    assert source["regulation_version"] == "11611000"
    assert source["param_type"] == "OBJ_ACT_PARAM_ST"
    assert source["param_data_version"] == 3
    assert source["definition_data_version"] == 3
    assert source["row_size"] == 96
    assert status["row_count"] == len(rows) == 198
    assert status["all_records_routeable_false"] is True
    assert len({row["id"] for row in rows}) == len(rows)
    assert all(REQUIRED_FIELDS <= set(row.get("values", {})) for row in rows)
    if args.source_manifest:
        manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
        regulation_path = Path(source["regulation_file"])
        assert regulation_path.is_file()
        digest = hashlib.sha256(regulation_path.read_bytes()).hexdigest().upper()
        manifest_entry = next(
            row for row in manifest.get("files", []) if row.get("relative_path") == "regulation.bin"
        )
        assert digest == manifest_entry["sha256"]
        assert manifest["game"]["regulation_version"] == source["regulation_version"]
    print("LOCAL OBJACT PARAM INDEX AUDIT: PASS")
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
