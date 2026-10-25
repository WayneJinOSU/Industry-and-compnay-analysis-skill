#!/usr/bin/env python3
"""Derive bounded scenario ranking from state and break/reclaim memory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import RULESET_VERSION, atomic_write_json


def add_adjustment(
    weights: dict[str, float],
    adjustments: list[dict],
    *,
    name: str,
    reason: str,
    changes: dict[str, float],
) -> None:
    totals = {key: 0.0 for key in weights}
    for item in adjustments:
        for key, value in item["changes"].items():
            totals[key] += value
    limited = {}
    for key, value in changes.items():
        room = 0.12 - totals[key]
        if value > 0:
            limited[key] = min(value, max(0.0, room))
        elif value < 0:
            limited[key] = -min(abs(value), max(0.0, 0.12 + totals[key]))
        else:
            limited[key] = 0.0
        weights[key] += limited[key]
    adjustments.append({"name": name, "reason": reason, "changes": limited})


def normalize(weights: dict[str, float]) -> dict[str, float]:
    clipped = {
        key: max(0.0, value)
        for key, value in weights.items()
    }
    total = sum(clipped.values())
    normalized = {key: value / total for key, value in clipped.items()}
    rounded = {key: round(value, 4) for key, value in normalized.items()}
    difference = round(1.0 - sum(rounded.values()), 4)
    ordered_keys = sorted(rounded, key=rounded.get, reverse=True)
    for key in ordered_keys:
        if difference > 0:
            rounded[key] = round(rounded[key] + difference, 4)
            difference = 0.0
        elif difference < 0:
            amount = min(-difference, rounded[key])
            rounded[key] = round(rounded[key] - amount, 4)
            difference = round(difference + amount, 4)
        if abs(difference) < 1e-9:
            break
    return rounded


def main() -> int:
    parser = argparse.ArgumentParser(description="由状态与关键位记忆生成有界动态权重")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--pack-output", help="写回方案权重后的输入包路径")
    args = parser.parse_args()

    pack = json.loads(Path(args.pack).read_text(encoding="utf-8"))
    state = pack.get("state_inputs") or {}
    memory = pack.get("structure_memory") or {}
    regime = str(state.get("weekly_regime") or "range")
    funding = str(state.get("funding_state") or "neutral")
    breadth = str(state.get("breadth_state") or "neutral")

    if regime == "down" and funding == "deleveraging" and breadth == "deteriorating":
        weights = {
            "downside_continuation": 0.35,
            "range_oscillation": 0.30,
            "upside_breakout": 0.20,
            "tail_extreme_down": 0.15,
        }
        base_reason = "向下结构叠加去杠杆和宽度恶化"
    elif regime == "down":
        weights = {
            "downside_continuation": 0.30,
            "range_oscillation": 0.40,
            "upside_breakout": 0.20,
            "tail_extreme_down": 0.10,
        }
        base_reason = "向下结构，但资金与宽度尚未完全恶化"
    elif regime == "up":
        weights = {
            "downside_continuation": 0.35,
            "range_oscillation": 0.30,
            "upside_breakout": 0.25,
            "tail_extreme_down": 0.10,
        }
        base_reason = "向上结构，同时保留压力位测试"
    else:
        weights = {
            "downside_continuation": 0.20,
            "range_oscillation": 0.40,
            "upside_breakout": 0.30,
            "tail_extreme_down": 0.10,
        }
        base_reason = "周线震荡，区间测试为基础分支"
    baseline = dict(weights)
    adjustments: list[dict] = []

    path = memory.get("recent_path_pressure") or {}
    subtype = path.get("subtype")
    if path.get("status") == "met" and subtype == "break_unreclaimed":
        add_adjustment(
            weights,
            adjustments,
            name="broken_support_unreclaimed",
            reason=str(path.get("detail") or "支撑跌破后未收复"),
            changes={
                "downside_continuation": 0.10,
                "range_oscillation": -0.08,
                "upside_breakout": -0.02,
            },
        )
    elif path.get("status") == "met" and subtype == "weak_close_near_support":
        add_adjustment(
            weights,
            adjustments,
            name="weak_close_near_support",
            reason=str(path.get("detail") or "支撑附近弱收盘"),
            changes={
                "downside_continuation": 0.05,
                "range_oscillation": -0.05,
            },
        )
    if int(memory.get("reclaimed_count") or 0) > 0:
        add_adjustment(
            weights,
            adjustments,
            name="support_reclaimed",
            reason="此前跌穿的支撑已重新收复",
            changes={
                "downside_continuation": -0.05,
                "range_oscillation": 0.05,
            },
        )

    support_distance = memory.get("support_distance_atr")
    if support_distance is not None and 0 <= float(support_distance) <= 0.6:
        add_adjustment(
            weights,
            adjustments,
            name="near_support",
            reason=f"收盘距最近支撑仅{float(support_distance):.3f}倍平均真实波幅",
            changes={
                "downside_continuation": 0.03,
                "range_oscillation": -0.03,
            },
        )

    pressure_attempt = (memory.get("pressure_attempt_memory") or {}).get("nearest") or {}
    pressure_status = pressure_attempt.get("status")
    failed_count = int(pressure_attempt.get("failed_close_count") or 0)
    consecutive_failures = int(pressure_attempt.get("consecutive_failed_tests") or 0)
    last_pressure_failed = pressure_attempt.get("last_test_status") == "failed"
    if (
        pressure_status == "repeated_failure"
        or (last_pressure_failed and consecutive_failures >= 3)
    ) and failed_count >= 2:
        pressure_penalty = 0.04 if consecutive_failures >= 3 else 0.03
        add_adjustment(
            weights,
            adjustments,
            name="repeated_pressure_failure",
            reason=(
                f"最近{int(pressure_attempt.get('lookback_sessions') or 0)}个交易日中，"
                f"压力带测试{int(pressure_attempt.get('test_count') or 0)}次、"
                f"收盘失败{failed_count}次、连续失败{consecutive_failures}次"
            ),
            changes={
                "range_oscillation": pressure_penalty,
                "upside_breakout": -pressure_penalty,
            },
        )
    elif pressure_attempt.get("last_test_status") == "accepted":
        add_adjustment(
            weights,
            adjustments,
            name="pressure_recently_accepted",
            reason="最近一次压力测试获得收盘接受",
            changes={
                "range_oscillation": -0.02,
                "upside_breakout": 0.02,
            },
        )

    nearest_support = memory.get("nearest_support") or {}
    nearest_pressure = memory.get("nearest_pressure") or {}
    decision_band = memory.get("decision_band") or {}
    level_summary = (pack.get("space_levels") or {}).get("level_registry_summary") or {}
    current_bands = level_summary.get("same_origin_bands") or []
    current_support_band = next(
        (row for row in current_bands if "支撑" in str(row.get("kind"))),
        None,
    )
    current_pressure_band = next(
        (row for row in current_bands if "压力" in str(row.get("kind"))),
        None,
    )
    atr = float(memory.get("atr14") or 0)
    range_width_atr = None
    range_width_penalty = 0.0
    support_defense = (
        current_support_band.get("defense_level")
        if current_support_band and current_support_band.get("defense_level") is not None
        else decision_band.get("support_defense")
        if decision_band.get("support_defense") is not None
        else nearest_support.get("level")
    )
    pressure_defense = (
        current_pressure_band.get("defense_level")
        if current_pressure_band and current_pressure_band.get("defense_level") is not None
        else decision_band.get("pressure_defense")
        if decision_band.get("pressure_defense") is not None
        else nearest_pressure.get("level")
    )
    if (
        atr > 0
        and support_defense is not None
        and pressure_defense is not None
    ):
        range_width_atr = (
            float(pressure_defense) - float(support_defense)
        ) / atr
        if range_width_atr > 1.5:
            range_width_penalty = min(0.04, (range_width_atr - 1.5) * 0.02)
            add_adjustment(
                weights,
                adjustments,
                name="wide_range_penalty",
                reason=(
                    f"决策带宽度{range_width_atr:.2f}倍平均真实波幅，"
                    "宽区间不能自然获得高确信"
                ),
                changes={
                    "range_oscillation": -range_width_penalty,
                    "downside_continuation": range_width_penalty / 2,
                    "upside_breakout": range_width_penalty / 2,
                },
            )

    gann = pack.get("gann_result") or {}
    time_status = str((gann.get("target_time_window") or {}).get("status") or "").lower()
    if any(term in time_status for term in ("位于已确认", "inside", "important")):
        add_adjustment(
            weights,
            adjustments,
            name="active_key_window",
            reason="目标日处于已确认关键时间点",
            changes={"range_oscillation": 0.02},
        )

    weights = normalize(weights)
    ordered = sorted(weights.items(), key=lambda item: item[1], reverse=True)
    margin = round(ordered[0][1] - ordered[1][1], 4)
    direction_by_scenario = {
        "downside_continuation": "bearish",
        "range_oscillation": "neutral",
        "upside_breakout": "bullish",
        "tail_extreme_down": "bearish",
    }
    payload = {
        "ruleset_version": RULESET_VERSION,
        "role": "baseline_reference",
        "target_date": pack.get("target_date"),
        "data_asof": (pack.get("state_inputs") or {}).get("data_asof"),
        "available_at": (pack.get("state_inputs") or {}).get("available_at"),
        "source": "确定性状态、关键位记忆与有界调整规则",
        "data_quality": (
            "partial"
            if (pack.get("structure_memory") or {}).get("data_gaps")
            else "complete"
        ),
        "base_reason": base_reason,
        "range_width_atr": (
            round(range_width_atr, 4) if range_width_atr is not None else None
        ),
        "range_width_penalty": round(range_width_penalty, 4),
        "baseline_weights": baseline,
        "adjustments": adjustments,
        "weights": weights,
        "direction_by_scenario": direction_by_scenario,
        "top_scenario": ordered[0][0],
        "second_scenario": ordered[1][0],
        "confidence_margin": margin,
        "low_confidence": margin < 0.05,
        "decision_note": (
            "最高权重领先不足5个百分点，方向表达应降级并等待确认"
            if margin < 0.05
            else "最高权重与次高分支存在可区分的排序差"
        ),
        "rule": "权重是内部排序分，不是概率；调整幅度受限且不得使用目标日数据",
    }
    atomic_write_json(Path(args.output), payload)
    if args.pack_output:
        pack["ruleset_version"] = RULESET_VERSION
        pack["scenario_weighting"] = payload
        atomic_write_json(Path(args.pack_output), pack)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
