#!/usr/bin/env python3
"""Create a metadata-complete direction input pack skeleton."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import RULESET_VERSION, atomic_write_json, parse_cutoff, parse_date


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize a direction input pack")
    parser.add_argument("--output", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--forecast-cutoff", required=True)
    parser.add_argument("--feature-cutoff", required=True)
    parser.add_argument("--decision-stage", required=True, choices=("premarket", "preopen_0925", "intraday_open", "intraday_update", "post_close_review"))
    parser.add_argument("--prediction-type", required=True, choices=("prospective", "backfill"))
    args = parser.parse_args()

    cutoff = parse_cutoff(args.forecast_cutoff)
    feature_cutoff = parse_cutoff(args.feature_cutoff)
    if feature_cutoff > cutoff:
        raise SystemExit("feature_cutoff 不能晚于 forecast_cutoff")

    payload = {
        "ruleset_version": RULESET_VERSION,
        "decision_stage": args.decision_stage,
        "prediction_type": args.prediction_type,
        "forecast_cutoff": cutoff.isoformat(timespec="seconds"),
        "feature_cutoff": feature_cutoff.isoformat(timespec="seconds"),
        "available_data_end": feature_cutoff.isoformat(timespec="seconds"),
        "target_date": parse_date(args.target_date).strftime("%Y-%m-%d"),
        "timezone": "Asia/Shanghai",
        "symbol": args.symbol,
        "source_used": {},
        "future_function_audit": {
            "status": "pending",
            "excluded": [],
            "rule": "Reject any observation later than forecast_cutoff or any data_asof later than feature_cutoff.",
        },
        "gann_result": {},
        "wave_result": {},
        "external_market": {},
        "external_gold": {},
        "information_content": {},
        "path_memory": {},
        "recent_5d_raw": [],
        "recent_5d_summary": {},
        "baseline_20d": {},
        "volume_price": {},
        "margin_financing": {},
        "breadth_and_sectors": {},
        "leadership": {},
        "critical_evidence": {},
        "state_inputs": {},
        "space_levels": {},
        "execution_overlay": {},
        "data_gap_register": [],
    }
    atomic_write_json(Path(args.output), payload)
    print(Path(args.output).expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
