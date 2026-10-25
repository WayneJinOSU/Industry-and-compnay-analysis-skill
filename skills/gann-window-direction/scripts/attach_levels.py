#!/usr/bin/env python3
"""Attach a level-registry summary to a direction input pack."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import RULESET_VERSION, atomic_write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Attach level registry output to a direction pack")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--levels", required=True, help="level_registry.csv or level_registry_summary.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    pack = json.loads(Path(args.pack).read_text(encoding="utf-8"))
    levels_path = Path(args.levels).expanduser().resolve()
    summary_path = (
        levels_path
        if levels_path.suffix.lower() == ".json"
        else levels_path.with_name("level_registry_summary.json")
    )
    if not summary_path.is_file():
        raise SystemExit(f"缺少关键位摘要：{summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    pack["ruleset_version"] = RULESET_VERSION
    pack["level_registry_path"] = str(levels_path)
    pack["space_levels"] = {
        "level_registry_summary": summary,
        "level_registry_path": str(levels_path),
        "level_ladder_path": str(levels_path.with_name("level_ladder.csv")),
    }
    pack.setdefault("source_used", {})["levels"] = str(levels_path)
    atomic_write_json(Path(args.output), pack)
    print(
        json.dumps(
            {
                "output": str(Path(args.output).expanduser().resolve()),
                "asof": summary.get("asof") or summary.get("as_of"),
                "target_date": summary.get("target_date"),
                "zones": summary.get("zones"),
                "gate_passed": (summary.get("mandatory_gate") or {}).get("passed"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
