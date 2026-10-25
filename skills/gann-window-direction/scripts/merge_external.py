#!/usr/bin/env python3
"""Merge an external snapshot into a direction input pack without manual aliases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import RULESET_VERSION, atomic_write_json, parse_cutoff


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge external_snapshot.json into direction_input_pack.json")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--external", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    pack = json.loads(Path(args.pack).read_text(encoding="utf-8"))
    snapshot = json.loads(Path(args.external).read_text(encoding="utf-8"))
    cutoff = parse_cutoff(snapshot["cutoff"])
    if parse_cutoff(pack["forecast_cutoff"]) != cutoff:
        raise SystemExit("输入包 forecast_cutoff 与外盘快照 cutoff 不一致")

    external_market = snapshot.get("external_market") or snapshot.get("us_anchors_last_close") or {}
    if not external_market:
        raise SystemExit("外盘快照没有 external_market")

    gaps = list(pack.get("data_gap_register") or [])
    known = {(row.get("field"), row.get("status")) for row in gaps}
    for row in snapshot.get("data_gap_register") or []:
        key = (row.get("field"), row.get("status"))
        if key not in known:
            gaps.append(row)
            known.add(key)

    pack["ruleset_version"] = RULESET_VERSION
    pack["external_market"] = external_market
    pack["external_gold"] = snapshot.get("gold") or {}
    pack["external_flags"] = snapshot.get("derived_flags") or {}
    pack["asia_live_snapshot"] = snapshot.get("asia_live_snapshot") or {}
    pack["external_snapshot"] = {
        "ruleset_version": snapshot.get("ruleset_version"),
        "cutoff": snapshot.get("cutoff"),
        "source_policy": snapshot.get("source_policy", []),
        "external_market": external_market,
        "gold": snapshot.get("gold") or {},
        "china_proxy": snapshot.get("china_proxy") or {},
        "asia_live_snapshot": snapshot.get("asia_live_snapshot") or {},
        "derived_flags": snapshot.get("derived_flags") or {},
        "data_gap_register": snapshot.get("data_gap_register") or [],
    }
    pack["external_snapshot_path"] = str(Path(args.external).expanduser().resolve())
    pack["data_gap_register"] = gaps
    pack.setdefault("source_used", {})["external_market"] = str(Path(args.external).expanduser().resolve())

    output = Path(args.output).expanduser().resolve()
    atomic_write_json(output, pack)
    print(
        json.dumps(
            {
                "output": str(output),
                "cutoff": cutoff.isoformat(timespec="seconds"),
                "external_codes": sorted(external_market),
                "gaps": len(gaps),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
