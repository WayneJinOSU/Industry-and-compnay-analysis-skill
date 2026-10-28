#!/usr/bin/env python3
"""Build current price anchors and weight-free close-settlement bins."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from common import RULESET_VERSION, atomic_write_json


def _band(summary: dict, token: str) -> dict:
    rows = summary.get("same_origin_bands") or []
    return next((row for row in rows if token in str(row.get("kind"))), {})


def main() -> int:
    parser = argparse.ArgumentParser(description="生成当前点位事实包与无权重收盘结算轴")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--levels", required=True, help="level_registry.csv")
    parser.add_argument("--output", required=True)
    parser.add_argument("--pack-output", required=True)
    args = parser.parse_args()

    pack = json.loads(Path(args.pack).read_text(encoding="utf-8"))
    summary = (pack.get("space_levels") or {}).get("level_registry_summary") or {}
    memory = pack.get("structure_memory") or {}
    state = pack.get("state_inputs") or {}
    close = float(summary.get("close") or memory.get("close") or 0)
    atr = float(summary.get("atr14") or memory.get("atr14") or 0)
    if close <= 0 or atr <= 0:
        raise SystemExit("点位事实包需要有效前收和统一 ATR")
    if summary.get("atr_method") != "wilder_14" or memory.get("atr_method") != "wilder_14":
        raise SystemExit("关键位登记与结构记忆必须统一使用 wilder_14")
    if abs(float(summary.get("atr14")) - float(memory.get("atr14"))) > 0.011:
        raise SystemExit("关键位登记与结构记忆的 ATR 不一致")

    support_band = _band(summary, "支撑")
    pressure_band = _band(summary, "压力")
    decision = memory.get("decision_band") or {}
    support = support_band.get("defense_level", decision.get("support_defense"))
    pressure = pressure_band.get("defense_level", decision.get("pressure_defense"))
    if support is None or pressure is None:
        raise SystemExit("当前关键位缺少支撑或压力防线")
    support = float(support)
    pressure = float(pressure)
    if not 0 < support < pressure:
        raise SystemExit("当前支撑和压力防线顺序非法")

    tail_upper = max(0.01, support - 2 * atr)
    upper_bound = max(pressure + 10 * atr, close * 3)
    close_bins = [
        {
            "name": "tail_extreme_down",
            "direction": "bearish",
            "lower": 0.0,
            "upper": round(tail_upper, 2),
            "close_condition": "收盘低于事前尾部阈值",
        },
        {
            "name": "downside_continuation",
            "direction": "bearish",
            "lower": round(tail_upper, 2),
            "upper": round(support, 2),
            "close_condition": "收盘低于支撑防线且不低于尾部阈值",
        },
        {
            "name": "range_oscillation",
            "direction": "neutral",
            "lower": round(support, 2),
            "upper": round(pressure, 2),
            "close_condition": "收盘位于当前支撑压力决策带",
        },
        {
            "name": "upside_breakout",
            "direction": "bullish",
            "lower": round(pressure, 2),
            "upper": round(upper_bound, 2),
            "close_condition": "收盘接受压力防线上方",
        },
    ]

    width_atr = (pressure - support) / atr
    range_quality = (
        "normal" if width_atr <= 1.5 else "wide" if width_atr <= 2.5 else "extreme_wide"
    )
    anchors: dict[float, dict] = {}

    def add_anchor(anchor_id: str, price: float, source: str, role: str) -> None:
        rounded = round(float(price), 2)
        if rounded > 0:
            anchors[rounded] = {
                "anchor_id": anchor_id,
                "price": rounded,
                "source": source,
                "role": role,
            }

    add_anchor("previous_close", close, "当前关键位登记", "前收")
    for multiple in (0.5, 1.0, 1.5, 2.0):
        suffix = str(multiple).replace(".", "_")
        add_anchor(f"close_minus_{suffix}_atr", close - multiple * atr, "前收与统一 ATR", "向下波动锚")
        add_anchor(f"close_plus_{suffix}_atr", close + multiple * atr, "前收与统一 ATR", "向上波动锚")
    add_anchor("support_defense", support, "当前关键位登记", "支撑防线")
    add_anchor("pressure_defense", pressure, "当前关键位登记", "压力防线")
    add_anchor("tail_threshold", tail_upper, "支撑防线与统一 ATR", "尾部阈值")
    add_anchor("upside_settlement_bound", upper_bound, "压力防线与统一 ATR", "结算轴上界")

    levels_path = Path(args.levels)
    with levels_path.open(encoding="utf-8", newline="") as handle:
        for index, row in enumerate(csv.DictReader(handle), start=1):
            try:
                price = float(row.get("level") or 0)
            except (TypeError, ValueError):
                continue
            add_anchor(
                f"registry_{index}",
                price,
                f"当前关键位登记:{row.get('band_id') or row.get('character') or 'level'}",
                str(row.get("role") or row.get("character") or "关键位"),
            )

    payload = {
        "ruleset_version": RULESET_VERSION,
        "target_date": pack.get("target_date"),
        "data_asof": summary.get("data_asof") or memory.get("data_asof"),
        "available_at": summary.get("available_at") or memory.get("available_at"),
        "source": "当前关键位登记、结构记忆与统一 ATR",
        "data_quality": "complete",
        "previous_close": round(close, 2),
        "atr14": round(atr, 4),
        "atr_method": "wilder_14",
        "decision_band": {
            "support_defense": round(support, 2),
            "pressure_defense": round(pressure, 2),
            "width_atr": round(width_atr, 4),
            "range_quality": range_quality,
        },
        "price_anchors": sorted(anchors.values(), key=lambda row: row["price"]),
        "close_bins": close_bins,
        "rule": "点位与收盘分箱是事实和结算锚，不是权重、概率或方向裁决",
    }
    atomic_write_json(Path(args.output), payload)
    pack["ruleset_version"] = RULESET_VERSION
    pack["level_context"] = payload
    pack.pop("scenario_weighting", None)
    atomic_write_json(Path(args.pack_output), pack)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
