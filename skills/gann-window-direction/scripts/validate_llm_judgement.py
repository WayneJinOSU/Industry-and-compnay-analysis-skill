#!/usr/bin/env python3
"""Validate and attach the LLM's final structured judgement."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import (
    RULESET_VERSION,
    atomic_write_json,
    parse_cutoff,
    validate_scenarios,
)


DIRECTIONS = ("bullish", "bearish", "neutral", "range")
STRUCTURAL_STATES = ("bullish", "bearish", "neutral")
EXECUTION_STATES = ("observe", "wait_for_confirmation", "confirmed", "reduce_only", "abstain")
ACTIONS = ("observe", "add_only_after_confirmation", "hold", "reduce_only", "no_new_long", "stop")
RISK_STATES = ("normal", "watch", "preemptive_defensive", "defensive", "offensive", "unknown")
SCENARIOS = {
    "downside_continuation": "bearish",
    "range_oscillation": "neutral",
    "upside_breakout": "bullish",
    "tail_extreme_down": "bearish",
}


def canonical_direction(value: object) -> str:
    text = str(value or "").strip().lower()
    return "neutral" if text == "range" else text


def nonempty_list(value: object, minimum: int) -> bool:
    return isinstance(value, list) and len(
        [item for item in value if str(item).strip()]
    ) >= minimum


def reference_exists(pack: dict, reference: object) -> bool:
    text = str(reference or "").strip()
    if not text:
        return False
    path = text[2:] if text.startswith("$.") else text
    current: object = pack
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return current not in (None, "", [], {})


def main() -> int:
    parser = argparse.ArgumentParser(description="校验并附加大模型最终研判")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--judgement", required=True)
    parser.add_argument("--pack-output", required=True)
    args = parser.parse_args()

    pack = json.loads(Path(args.pack).read_text(encoding="utf-8"))
    judgement = json.loads(Path(args.judgement).read_text(encoding="utf-8"))
    errors: list[str] = []

    required = (
        "target_date",
        "decision_at",
        "core_thesis",
        "structural_bias",
        "window_state",
        "direction",
        "scenarios",
        "targets",
        "execution_state",
        "execution_action",
        "risk_state",
        "abstain",
        "confidence",
        "supporting_evidence",
        "opposing_evidence",
        "action_maintenance",
        "action_invalidation",
        "evidence_refs",
        "horizon",
        "next_review",
    )
    errors.extend(
        f"缺少字段：{field}"
        for field in required
        if field not in judgement or judgement.get(field) in (None, "", [], {})
    )
    if judgement.get("source") != "llm":
        errors.append("source 必须明确为 llm")
    if str(judgement.get("target_date")) != str(pack.get("target_date")):
        errors.append("target_date 与输入包不一致")
    try:
        decision_at = parse_cutoff(judgement["decision_at"])
        cutoff = parse_cutoff(pack["forecast_cutoff"])
        if decision_at > cutoff:
            errors.append("decision_at 晚于 forecast_cutoff")
    except (KeyError, TypeError, ValueError):
        errors.append("decision_at 无法解析")

    if judgement.get("structural_bias") not in STRUCTURAL_STATES:
        errors.append("structural_bias 非法")
    if judgement.get("window_state") not in (
        "unresolved",
        "bullish_confirmation",
        "bearish_confirmation",
        "failed_bullish_window",
        "failed_bearish_window",
    ):
        errors.append("window_state 非法")
    direction = canonical_direction(judgement.get("direction"))
    if direction not in ("bullish", "bearish", "neutral"):
        errors.append("direction 必须是看多、看空或震荡")
    if judgement.get("execution_state") not in EXECUTION_STATES:
        errors.append("execution_state 非法")
    if judgement.get("execution_action") not in ACTIONS:
        errors.append("execution_action 非法")
    if judgement.get("risk_state") not in RISK_STATES:
        errors.append("risk_state 非法")
    if not isinstance(judgement.get("abstain"), bool):
        errors.append("abstain 必须为布尔值")

    scenarios = judgement.get("scenarios")
    if not isinstance(scenarios, list):
        errors.append("scenarios 必须是列表")
        scenarios = []
    errors.extend(validate_scenarios(scenarios))
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        for field in ("name", "weight", "lower", "upper", "close_condition", "path_forecast"):
            if scenario.get(field) is None:
                errors.append(f"情景缺少字段：{scenario.get('name', '未命名')}.{field}")
        path = scenario.get("path_forecast") or {}
        for field in ("opening", "confirmation", "invalidation"):
            if not str(path.get(field) or "").strip():
                errors.append(f"情景路径缺少 {field}")
        if not nonempty_list(path.get("steps"), 2):
            errors.append("情景路径至少需要2个有序步骤")
        if not path.get("targets"):
            errors.append("情景路径必须包含目标")
    if not isinstance(judgement.get("targets"), list) or not judgement.get("targets"):
        errors.append("targets 必须是非空列表")

    if not nonempty_list(judgement.get("supporting_evidence"), 2):
        errors.append("supporting_evidence 至少需要2条")
    if not nonempty_list(judgement.get("opposing_evidence"), 1):
        errors.append("opposing_evidence 至少需要1条")
    if not nonempty_list(judgement.get("action_maintenance"), 1):
        errors.append("action_maintenance 至少需要1条")
    if not nonempty_list(judgement.get("action_invalidation"), 1):
        errors.append("action_invalidation 至少需要1条")
    if not nonempty_list(judgement.get("evidence_refs"), 1):
        errors.append("evidence_refs 至少需要1条")
    elif not all(reference_exists(pack, ref) for ref in judgement["evidence_refs"]):
        errors.append("evidence_refs 包含输入包中不存在的证据路径")

    top_scenario = None
    second_scenario = None
    margin = None
    if scenarios and not validate_scenarios(scenarios):
        ordered = sorted(scenarios, key=lambda item: float(item["weight"]), reverse=True)
        top_scenario = ordered[0]["name"]
        second_scenario = ordered[1]["name"]
        margin = round(float(ordered[0]["weight"]) - float(ordered[1]["weight"]), 4)
        if direction != SCENARIOS[top_scenario]:
            errors.append("direction 必须等于最高权重情景的固定方向")

    if errors:
        print(json.dumps({"status": "failed", "errors": errors}, ensure_ascii=False, indent=2))
        return 1

    payload = dict(judgement)
    payload.update(
        {
            "ruleset_version": RULESET_VERSION,
            "source": "llm",
            "available_at": judgement["decision_at"],
            "data_quality": "llm_structured_judgement",
            "direction": direction,
            "top_scenario": top_scenario,
            "second_scenario": second_scenario,
            "scenario_weights": {
                row["name"]: float(row["weight"]) for row in scenarios
            },
            "confidence_margin": margin,
            "low_confidence": bool(margin is not None and margin < 0.05),
        }
    )
    pack["ruleset_version"] = RULESET_VERSION
    pack["llm_judgement"] = payload
    atomic_write_json(Path(args.pack_output), pack)
    print(
        json.dumps(
            {
                "status": "passed",
                "direction": direction,
                "top_scenario": top_scenario,
                "confidence_margin": margin,
                "low_confidence": payload["low_confidence"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
