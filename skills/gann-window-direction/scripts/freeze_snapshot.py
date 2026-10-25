#!/usr/bin/env python3
"""Create a reproducible manifest for one direction-analysis stage."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common import RULESET_VERSION

STAGES = ("premarket", "intraday", "postclose", "backfill")
PREDICTION_TYPES = ("prospective", "backfill")
INCLUDE_SUFFIXES = {".md", ".json", ".csv", ".png", ".html", ".svg", ".pdf"}
EXCLUDED_PREFIXES = ("gate/", "scorecard/")
EXCLUDED_NAMES = {"snapshot_manifest.json"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze a premarket/intraday/postclose/backfill artifact snapshot")
    parser.add_argument("--stage-dir", required=True, help="阶段输出目录的绝对路径")
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--prediction-type", required=True, choices=PREDICTION_TYPES)
    parser.add_argument("--forecast-cutoff", required=True)
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--ruleset-version", default=RULESET_VERSION)
    parser.add_argument("--output", help="manifest 路径；默认写入阶段目录/snapshot_manifest.json")
    parser.add_argument("--allow-nonstandard", action="store_true", help="允许阶段目录名与 --stage 不一致")
    args = parser.parse_args()

    stage_dir = Path(args.stage_dir).expanduser().resolve()
    if not stage_dir.is_dir():
        raise SystemExit(f"阶段目录不存在：{stage_dir}")
    if stage_dir.name != args.stage and not args.allow_nonstandard:
        raise SystemExit(
            f"阶段目录名 {stage_dir.name!r} 与 --stage {args.stage!r} 不一致；"
            "请使用 premarket/intraday/postclose/backfill 目录，或显式传 --allow-nonstandard"
        )

    files = []
    for path in sorted(stage_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(stage_dir).as_posix()
        if relative in EXCLUDED_NAMES or relative.startswith(EXCLUDED_PREFIXES):
            continue
        if path.suffix.lower() not in INCLUDE_SUFFIXES:
            continue
        files.append(
            {
                "path": relative,
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
        )

    if not files:
        raise SystemExit("阶段目录没有可冻结的 Markdown、JSON、CSV 或图表文件")

    manifest = {
        "schema_version": 1,
        "ruleset_version": args.ruleset_version,
        "stage": args.stage,
        "prediction_type": args.prediction_type,
        "forecast_cutoff": args.forecast_cutoff,
        "target_date": args.target_date,
        "frozen_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "excluded_prefixes": list(EXCLUDED_PREFIXES),
        "files": files,
    }

    output = Path(args.output).expanduser().resolve() if args.output else stage_dir / "snapshot_manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, output)
    print(
        json.dumps(
            {
                "manifest": str(output),
                "stage": args.stage,
                "prediction_type": args.prediction_type,
                "file_count": len(files),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
