#!/usr/bin/env python3
"""Build a weight-free forecast record from validated LLM judgement."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import atomic_write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="由大模型结构与路径研判生成预判记录")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    pack = json.loads(Path(args.pack).read_text(encoding="utf-8"))
    judgement = pack.get("llm_judgement")
    if not isinstance(judgement, dict):
        raise SystemExit("输入包缺少已校验的大模型研判")
    path = judgement.get("next_day_path")
    if not isinstance(path, dict):
        raise SystemExit("大模型研判缺少次日路径")
    level_context = pack.get("level_context") or {}
    close_bins = level_context.get("close_bins")
    if not isinstance(close_bins, list) or not close_bins:
        raise SystemExit("点位事实包缺少收盘结算轴")
    band = level_context.get("decision_band") or {}
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
        "next_day_baseline": path["baseline_summary"],
        "opening_zone": path["opening"],
        "intraday_zone": path["intraday"],
        "close_zone": path["close"],
        "close_character": path["close"]["character"],
        "next_day_path": path,
        "structure_invalidation": judgement["structure_invalidation"],
        "baseline_path_invalidation": judgement["baseline_path_invalidation"],
        "execution_state": judgement["execution_state"],
        "action_bias": judgement["execution_action"],
        "abstain": bool(judgement.get("abstain", False)),
        "close_axis": "close",
        "interval_convention": "lower_inclusive_upper_exclusive",
        "close_bins": close_bins,
        "level_context": level_context,
        "execution_overlay": pack.get("execution_overlay"),
        "llm_judgement": judgement,
        "judgement_source": "llm",
        "decision_level": f"{float(band['support_defense']):.2f}-{float(band['pressure_defense']):.2f}",
        "next_confirmation": {
            "down": path["downside_switch"]["trigger_level"],
            "up": path["upside_switch"]["trigger_level"],
        },
    }
    atomic_write_json(Path(args.output), forecast)
    print(json.dumps(forecast, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
