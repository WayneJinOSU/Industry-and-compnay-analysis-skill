#!/usr/bin/env python3
"""Validate and attach discretionary LLM structure and next-day path judgement."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import RULESET_VERSION, atomic_write_json, parse_cutoff
from path_contract import forbidden_keys, validate_next_day_path


STRUCTURAL_STATES = ("bullish", "bearish", "neutral")
EXECUTION_STATES = ("observe", "wait_for_confirmation", "confirmed", "reduce_only", "abstain")
ACTIONS = ("observe", "add_only_after_confirmation", "hold", "reduce_only", "no_new_long", "stop")
RISK_STATES = ("normal", "watch", "preemptive_defensive", "defensive", "offensive", "unknown")


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
    parser = argparse.ArgumentParser(description="校验并附加大模型结构与路径研判")
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
        "structure_reason",
        "structure_opposition",
        "structure_invalidation",
        "window_state",
        "next_day_path",
        "baseline_path_invalidation",
        "execution_state",
        "execution_action",
        "risk_state",
        "abstain",
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
    forbidden = forbidden_keys(judgement)
    if forbidden:
        errors.append(f"新版研判禁止权重、置信度和顶层方向字段：{forbidden}")
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
    if judgement.get("execution_state") not in EXECUTION_STATES:
        errors.append("execution_state 非法")
    if judgement.get("execution_action") not in ACTIONS:
        errors.append("execution_action 非法")
    if judgement.get("risk_state") not in RISK_STATES:
        errors.append("risk_state 非法")
    if not isinstance(judgement.get("abstain"), bool):
        errors.append("abstain 必须为布尔值")

    level_context = pack.get("level_context") or {}
    errors.extend(
        validate_next_day_path(
            judgement.get("next_day_path"),
            str(judgement.get("structural_bias")),
            level_context,
        )
    )
    for field, minimum in (
        ("structure_reason", 2),
        ("structure_opposition", 1),
        ("structure_invalidation", 1),
        ("baseline_path_invalidation", 1),
        ("supporting_evidence", 2),
        ("opposing_evidence", 1),
        ("action_maintenance", 1),
        ("action_invalidation", 1),
        ("evidence_refs", 1),
    ):
        if not nonempty_list(judgement.get(field), minimum):
            errors.append(f"{field} 至少需要{minimum}条")
    if nonempty_list(judgement.get("evidence_refs"), 1) and not all(
        reference_exists(pack, ref) for ref in judgement["evidence_refs"]
    ):
        errors.append("evidence_refs 包含输入包中不存在的证据路径")

    if errors:
        print(json.dumps({"status": "failed", "errors": errors}, ensure_ascii=False, indent=2))
        return 1

    payload = dict(judgement)
    payload.update(
        {
            "ruleset_version": RULESET_VERSION,
            "source": "llm",
            "available_at": judgement["decision_at"],
            "data_quality": "llm_structured_path_judgement",
        }
    )
    pack["ruleset_version"] = RULESET_VERSION
    pack["llm_judgement"] = payload
    atomic_write_json(Path(args.pack_output), pack)
    print(
        json.dumps(
            {
                "status": "passed",
                "structural_bias": payload["structural_bias"],
                "next_day_baseline": payload["next_day_path"]["baseline_summary"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
