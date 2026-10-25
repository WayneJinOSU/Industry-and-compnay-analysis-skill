#!/usr/bin/env python3
"""Build a forecast record from the validated LLM judgement."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import atomic_write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="由大模型最终研判生成预判记录")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    pack = json.loads(Path(args.pack).read_text(encoding="utf-8"))
    judgement = pack.get("llm_judgement")
    if not isinstance(judgement, dict):
        raise SystemExit("输入包缺少已校验的大模型研判")
    scenarios = judgement.get("scenarios")
    if not isinstance(scenarios, list):
        raise SystemExit("大模型研判缺少四情景")
    key = next((row for row in scenarios if row.get("name") == "range_oscillation"), None)
    if not key:
        raise SystemExit("大模型研判缺少区间震荡情景")
    lower = float(key["lower"])
    upper = float(key["upper"])
    forecast = {
        "target_date": pack["target_date"],
        "prediction_type": pack["prediction_type"],
        "decision_stage": pack["decision_stage"],
        "ruleset_version": pack["ruleset_version"],
        "forecast_cutoff": pack["forecast_cutoff"],
        "feature_cutoff": pack["feature_cutoff"],
        "symbol": pack["symbol"],
        "structural_bias": judgement["structural_bias"],
        "window_state": judgement["window_state"],
        "direction": judgement["direction"],
        "execution_state": judgement["execution_state"],
        "action_bias": judgement["execution_action"],
        "abstain": bool(judgement.get("abstain", False)),
        "confidence": float(judgement["confidence"]),
        "close_axis": "close",
        "interval_convention": "lower_inclusive_upper_exclusive",
        "scenarios": scenarios,
        "targets": judgement["targets"],
        "execution_overlay": pack.get("execution_overlay"),
        "llm_judgement": judgement,
        "judgement_source": "llm",
        "decision_level": f"{lower:.2f}-{upper:.2f}",
        "invalidation": f"收盘低于{lower:.2f}或高于{upper:.2f}",
        "next_confirmation": {"down": lower, "up": upper},
    }
    atomic_write_json(Path(args.output), forecast)
    print(json.dumps(forecast, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
