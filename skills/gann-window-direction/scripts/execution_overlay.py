#!/usr/bin/env python3
"""Build a point-in-time execution overlay without changing close-bin weights."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import RULESET_VERSION, atomic_write_json, parse_available_at, parse_cutoff


GAP_STATES = ("expected", "confirmed", "faded", "not_applicable", "unknown")
PRESSURE_STATES = ("untested", "accepted", "rejected", "ambiguous", "not_applicable", "unknown")
PARTICIPATION_STATES = ("confirming", "divergent", "unknown")
RISK_STATES = ("normal", "watch", "preemptive_defensive", "defensive", "offensive", "unknown")
SETUP_EVIDENCE_STATES = ("met", "not_met", "unknown")


def critical_level(pack: dict, role: str) -> float | None:
    rows = (pack.get("critical_evidence") or {}).get("critical_levels") or []
    for row in rows:
        if row.get("role") == role and row.get("level") is not None:
            return float(row["level"])
    return None


def finite_number(snapshot: dict, field: str) -> float | None:
    value = snapshot.get(field)
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_participation(snapshot: dict) -> tuple[str, dict, list[str]]:
    metrics = {
        "advance_ratio": finite_number(snapshot, "advance_ratio"),
        "leader_relative_strength": finite_number(snapshot, "leader_relative_strength"),
        "same_time_amount_ratio": finite_number(snapshot, "same_time_amount_ratio"),
    }
    known = [name for name, value in metrics.items() if value is not None]
    missing = [name for name, value in metrics.items() if value is None]
    positive = sum(
        (
            metrics["advance_ratio"] is not None and metrics["advance_ratio"] >= 0.55,
            metrics["leader_relative_strength"] is not None and metrics["leader_relative_strength"] >= 0,
            metrics["same_time_amount_ratio"] is not None and metrics["same_time_amount_ratio"] >= 1.0,
        )
    )
    negative = sum(
        (
            metrics["advance_ratio"] is not None and metrics["advance_ratio"] <= 0.45,
            metrics["leader_relative_strength"] is not None and metrics["leader_relative_strength"] < 0,
            metrics["same_time_amount_ratio"] is not None and metrics["same_time_amount_ratio"] < 1.0,
        )
    )
    state = "unknown"
    if len(known) >= 2 and positive >= 2:
        state = "confirming"
    elif len(known) >= 2 and negative >= 2:
        state = "divergent"
    return state, metrics, [f"participation.{name}" for name in missing]


def premarket_setup(
    pack: dict,
    *,
    pressure_low: float,
    pressure_high: float,
) -> tuple[dict, dict, list[dict], list[str], str]:
    """Derive a causal premarket risk posture without auction or intraday data.

    This is deliberately an execution prior, not a price-direction claim. It
    addresses the asymmetry where a strong external catalyst pushes price into
    a mature time/price window: acceptance must be proven before adding or
    holding risk, rather than waiting for a completed rejection.
    """
    summary = ((pack.get("space_levels") or {}).get("level_registry_summary") or {})
    recent = pack.get("recent_5d_raw") or []
    external = pack.get("external_market") or {}
    information = pack.get("information_content") or {}
    leadership = pack.get("leadership") or {}
    direction_audit = ((pack.get("critical_evidence") or {}).get("direction_audit") or {})

    gaps: list[str] = []
    try:
        close = float(summary.get("close"))
        atr = float(summary.get("atr14"))
    except (TypeError, ValueError):
        close = None
        atr = None
        gaps.extend(["premarket.close", "premarket.atr"])
    try:
        closes = [float(row["close"]) for row in recent]
    except (KeyError, TypeError, ValueError):
        closes = []
    external_values = {
        code: finite_number(external.get(code, {}), "pct_chg")
        for code in ("IXIC", "NDX", "SOX", "ARM", "SOXL", "KS11", "TWII")
    }
    if all(value is None for value in external_values.values()):
        gaps.append("premarket.external_chain")

    time_window = ((pack.get("gann_result") or {}).get("target_time_window") or {})
    target = str(pack.get("target_date") or "")
    active_window = str(time_window.get("active_window") or "")
    key_window = bool(
        "inside" in str(time_window.get("status") or "").lower()
        or "important" in str(time_window.get("status") or "").lower()
        or (target and target in active_window)
    )
    distance_atr = None
    near_supply = False
    if close is not None and atr and atr > 0:
        distance_atr = (pressure_low - close) / atr
        near_supply = -0.25 <= distance_atr <= 0.75

    three_day_impulse = None
    if len(closes) >= 4 and closes[-4] > 0:
        three_day_impulse = closes[-1] / closes[-4] - 1
    external_euphoria = bool(
        (external_values["SOX"] is not None and external_values["SOX"] >= 3.0)
        or (external_values["ARM"] is not None and external_values["ARM"] >= 10.0)
        or (external_values["SOXL"] is not None and external_values["SOXL"] >= 8.0)
        or (
            external_values["IXIC"] is not None
            and external_values["IXIC"] >= 1.5
            and external_values["NDX"] is not None
            and external_values["NDX"] >= 2.0
        )
    )
    volume_content = information.get("volume")
    leadership_state = leadership.get("state")
    if volume_content == "weak" or leadership_state in ("leadership_lagging", "leadership_neutral"):
        confirmation_deficit_status = "met"
    elif volume_content == "informative" and leadership_state == "leadership_confirming":
        confirmation_deficit_status = "not_met"
    else:
        confirmation_deficit_status = "unknown"
    structural_value = direction_audit.get("structural_bias")
    structural_status = (
        "met"
        if structural_value == "bearish"
        else "not_met"
        if structural_value in ("bullish", "neutral")
        else "unknown"
    )
    time_window_known = bool(time_window.get("status") or time_window.get("active_window"))
    key_window_status = "met" if key_window else "not_met" if time_window_known else "unknown"
    pressure_status = (
        "met" if near_supply else "not_met" if distance_atr is not None else "unknown"
    )
    external_known = any(value is not None for value in external_values.values())
    external_status = "met" if external_euphoria else "not_met" if external_known else "unknown"
    impulse_status = (
        "met"
        if three_day_impulse is not None and three_day_impulse >= 0.015
        else "not_met"
        if three_day_impulse is not None
        else "unknown"
    )

    def evidence_row(name: str, status: str, detail: str) -> dict:
        if status not in SETUP_EVIDENCE_STATES:
            raise ValueError(f"盘前证据状态非法：{status}")
        value = True if status == "met" else False if status == "not_met" else None
        return {"name": name, "status": status, "value": value, "detail": detail}

    evidence = [
        evidence_row(
            "structural_bearish",
            structural_status,
            "周线结构仍偏空"
            if structural_status == "met"
            else "周线结构未确认偏空"
            if structural_status == "not_met"
            else "周线结构状态缺失",
        ),
        evidence_row(
            "active_key_window",
            key_window_status,
            "目标日处于已确认关键时间窗口"
            if key_window_status == "met"
            else "目标日不在有效关键时间窗口"
            if key_window_status == "not_met"
            else "关键时间窗口状态缺失",
        ),
        evidence_row(
            "pressure_proximity",
            pressure_status,
            (
                f"收盘价距压力带近端仅{distance_atr:.3f}倍平均真实波幅"
                if distance_atr is not None
                else "平均真实波幅不可得"
            ),
        ),
        evidence_row(
            "external_euphoria",
            external_status,
            "、".join(
                detail
                for detail in (
                    f"费城半导体指数上涨{external_values['SOX']:.2f}%" if external_values["SOX"] is not None else "",
                    f"纳斯达克综合指数上涨{external_values['IXIC']:.2f}%" if external_values["IXIC"] is not None else "",
                    f"纳斯达克100指数上涨{external_values['NDX']:.2f}%" if external_values["NDX"] is not None else "",
                    f"半导体高弹性股票型基金上涨{external_values['SOXL']:.2f}%" if external_values["SOXL"] is not None else "",
                    f"半导体设计公司股票上涨{external_values['ARM']:.2f}%" if external_values["ARM"] is not None else "",
                )
                if detail
            )
            if external_status != "unknown"
            else "高弹性外围市场锚点缺失",
        ),
        evidence_row(
            "recent_three_day_impulse",
            impulse_status,
            (
                f"最近3日涨幅{three_day_impulse:.4%}，达到或超过1.5%快速上涨门槛"
                if impulse_status == "met"
                else f"最近3日涨幅{three_day_impulse:.4%}，未达到1.5%快速上涨门槛"
                if three_day_impulse is not None
                else "近期价格序列不足"
            ),
        ),
        evidence_row(
            "confirmation_deficit",
            confirmation_deficit_status,
            "成交额或领涨结构尚不足以确认压力带已被接受"
            if confirmation_deficit_status == "met"
            else "成交额与领涨结构已同步确认"
            if confirmation_deficit_status == "not_met"
            else "成交额或领涨结构缺失，无法判断确认是否充分",
        ),
    ]
    score = sum(1 for row in evidence if row["status"] == "met")
    known_count = sum(1 for row in evidence if row["status"] != "unknown")
    unknown_count = len(evidence) - known_count
    for row in evidence:
        if row["status"] == "unknown":
            gaps.append(f"premarket.evidence.{row['name']}")
    if close is None or atr is None or all(value is None for value in external_values.values()):
        setup_state = "unknown"
        risk_state = "unknown"
    elif known_count < 4:
        setup_state = "unknown"
        risk_state = "unknown"
    elif score >= 4:
        setup_state = "risk_zone_euphoria"
        risk_state = "preemptive_defensive"
    elif score >= 2:
        setup_state = "conditional_watch"
        risk_state = "watch"
    else:
        setup_state = "normal"
        risk_state = "normal"

    metrics = {
        "close": close,
        "atr14": atr,
        "distance_to_pressure_low_atr": None if distance_atr is None else round(distance_atr, 4),
        "three_day_close_return": None if three_day_impulse is None else round(three_day_impulse, 6),
        "sox_pct_chg": external_values["SOX"],
        "nasdaq_pct_chg": external_values["IXIC"],
        "setup_score": score,
        "setup_known_checks": known_count,
        "setup_unknown_checks": unknown_count,
    }
    states = {
        "gap_state": "not_applicable",
        "pressure_state": "untested",
        "participation_state": "unknown",
        "risk_state": risk_state,
    }
    return states, metrics, evidence, gaps, setup_state


def classify_states(
    snapshot: dict,
    *,
    pressure_low: float,
    pressure_high: float,
    gap_threshold: float,
    fade_threshold: float,
) -> tuple[dict, dict, list[str]]:
    price = finite_number(snapshot, "price")
    previous_close = finite_number(snapshot, "prev_close")
    participation, participation_metrics, gaps = classify_participation(snapshot)
    metrics: dict = dict(participation_metrics)
    gap_state = "unknown"
    pressure_state = "unknown"
    if price is None or previous_close is None or previous_close <= 0:
        gaps.extend(field for field in ("price", "prev_close") if finite_number(snapshot, field) is None)
    else:
        open_price = finite_number(snapshot, "open") or price
        gap = open_price / previous_close - 1
        metrics["open_gap_pct"] = round(gap * 100, 4)
        metrics["price_vs_prev_close_pct"] = round((price / previous_close - 1) * 100, 4)
        if gap < gap_threshold:
            gap_state = "not_applicable"
        else:
            gap_state = "confirmed"
            denominator = open_price - previous_close
            if denominator > 0 and price < open_price:
                fade = (open_price - price) / denominator
                metrics["gap_fade_ratio"] = round(fade, 4)
                if fade >= fade_threshold:
                    gap_state = "faded"
        session_high = finite_number(snapshot, "session_high")
        tested = (session_high is not None and session_high >= pressure_low) or price >= pressure_low
        if price < pressure_low and session_high is not None and session_high >= pressure_low:
            pressure_state = "rejected"
        elif price > pressure_high and participation == "confirming":
            pressure_state = "accepted"
        elif tested:
            pressure_state = "ambiguous"
        else:
            pressure_state = "untested"
    if pressure_state == "rejected" and participation == "divergent":
        risk_state = "defensive"
    elif pressure_state == "accepted" and participation == "confirming":
        risk_state = "offensive"
    elif "unknown" in (gap_state, pressure_state, participation):
        risk_state = "unknown"
    elif pressure_state == "ambiguous" or gap_state in ("confirmed", "faded"):
        risk_state = "watch"
    else:
        risk_state = "normal"
    return {
        "gap_state": gap_state,
        "pressure_state": pressure_state,
        "participation_state": participation,
        "risk_state": risk_state,
    }, metrics, gaps


def build_overlay(
    pack: dict,
    snapshot: dict | None,
    *,
    pressure_low: float,
    pressure_high: float,
    support: float,
    gap_threshold: float = 0.005,
    fade_threshold: float = 0.5,
) -> dict:
    if pressure_low > pressure_high:
        raise ValueError("pressure_low 不能高于 pressure_high")
    stage = pack["decision_stage"]
    cutoff = parse_cutoff(pack["forecast_cutoff"])
    setup_states, setup_metrics, setup_evidence, setup_gaps, setup_state = premarket_setup(
        pack,
        pressure_low=pressure_low,
        pressure_high=pressure_high,
    )
    if snapshot is None:
        states = setup_states
        metrics = setup_metrics
        gaps = setup_gaps
        decision_mode = "premarket_setup"
        data_asof = parse_cutoff(pack["feature_cutoff"]).date().isoformat()
        available_at = cutoff.isoformat(timespec="seconds")
        source = "deterministic premarket setup from point-in-time pack"
        data_quality = "derived_from_point_in_time_pack"
    else:
        for field in ("data_asof", "available_at", "source", "data_quality"):
            if not snapshot.get(field):
                raise ValueError(f"快照缺少 {field}")
        available = parse_available_at(snapshot["available_at"])
        if available is None or available > cutoff:
            raise ValueError("快照 available_at 无法解析或晚于 forecast_cutoff")
        data_asof = str(snapshot["data_asof"])
        available_at = available.isoformat(timespec="seconds")
        source = str(snapshot["source"])
        data_quality = str(snapshot["data_quality"])
        states, snapshot_metrics, snapshot_gaps = classify_states(
            snapshot,
            pressure_low=pressure_low,
            pressure_high=pressure_high,
            gap_threshold=gap_threshold,
            fade_threshold=fade_threshold,
        )
        metrics = {**setup_metrics, **snapshot_metrics}
        gaps = snapshot_gaps
        decision_mode = "combined"
        if (
            setup_state == "risk_zone_euphoria"
            and states["risk_state"] not in ("offensive", "defensive")
        ):
            # A normal or untested snapshot cannot release a high-risk premarket
            # prior. Only accepted pressure plus confirming participation can
            # restore offense; rejection plus divergence may strengthen defense.
            states["risk_state"] = "preemptive_defensive"
    execution_bias = {
        "preemptive_defensive": "reduce_only",
        "defensive": "reduce_only",
        "offensive": "add_only_after_confirmation",
        "watch": "wait_for_confirmation",
        "unknown": "wait_for_confirmation",
        "normal": "observe",
    }[states["risk_state"]]
    recommendation_zh = {
        "reduce_only": "只减不加",
        "add_only_after_confirmation": "确认后恢复进攻",
        "wait_for_confirmation": "等待确认",
        "observe": "观察",
    }[execution_bias]
    active_reasons = [
        str(item.get("detail"))
        for item in setup_evidence
        if item.get("value") is True and item.get("detail")
    ]
    inaction_reasons = [
        str(item.get("detail"))
        for item in setup_evidence
        if item.get("value") is False and item.get("detail")
    ]
    if len(active_reasons) < 2:
        active_reasons.extend(
            [
                f"当前风险状态为{states['risk_state']}",
                f"压力带观察区间为{pressure_low:.2f}至{pressure_high:.2f}",
            ]
        )
    if not inaction_reasons:
        inaction_reasons = [
            "尚无证据证明压力带已被放量接受" if execution_bias == "reduce_only" else "当前没有足够的反向结构证据"
        ]
    if execution_bias == "reduce_only":
        action_maintenance = [
            f"收盘仍未接受{pressure_high:.2f}上方",
            "压力测试后未出现宽度与领涨结构的同步确认",
        ]
        action_invalidation = [
            f"放量收盘接受{pressure_high:.2f}上方，宽度与领涨结构同步确认，且下一观察点仍未失守"
        ]
    elif execution_bias == "add_only_after_confirmation":
        action_maintenance = [
            f"收盘维持在{pressure_high:.2f}上方",
            "参与度与领涨结构保持确认",
        ]
        action_invalidation = [
            f"收盘跌回{pressure_high:.2f}下方",
            "参与度转为背离且领涨结构同步转弱",
        ]
    elif execution_bias == "wait_for_confirmation":
        action_maintenance = [
            "压力状态仍未形成可验证的接受或拒绝",
            "参与度尚未形成确认或背离",
        ]
        action_invalidation = [
            "压力接受且参与度确认时改为恢复进攻",
            "压力拒绝且参与度背离时改为只减不加",
        ]
    else:
        action_maintenance = [
            "没有活跃缺口或压力测试",
            "参与度与领涨结构未出现背离",
        ]
        action_invalidation = [
            "压力拒绝且参与度背离时转为防守",
            "价格进入压力带且无法确认接受时改为等待确认",
        ]
    if execution_bias == "reduce_only":
        why_now = active_reasons
    elif execution_bias == "add_only_after_confirmation":
        why_now = [
            f"价格已接受{pressure_high:.2f}上方",
            "参与度与领涨结构同步确认",
        ]
    elif execution_bias == "wait_for_confirmation":
        why_now = active_reasons or ["关键位尚未形成可验证的接受或拒绝"]
    else:
        why_now = ["当前没有成立的时间、压力与外部催化组合"] + active_reasons
    return {
        "ruleset_version": RULESET_VERSION,
        "stage": stage,
        "target_date": pack["target_date"],
        "data_asof": data_asof,
        "available_at": available_at,
        "source": source,
        "data_quality": data_quality,
        "decision_mode": decision_mode,
        "setup_state": setup_state,
        "setup_evidence": setup_evidence,
        **states,
        "execution_bias": execution_bias,
        "action_rationale": {
            "recommendation": execution_bias,
            "recommendation_zh": recommendation_zh,
            "why_now": why_now,
            "opposing_evidence": inaction_reasons,
            "action_maintenance": action_maintenance,
            "action_invalidation": action_invalidation,
            "horizon": "目标交易日",
            "next_review": "下一交易日收盘",
        },
        "metrics": metrics,
        "thresholds": {
            "gap_up": gap_threshold,
            "gap_fade": fade_threshold,
            "pressure_low": pressure_low,
            "pressure_high": pressure_high,
            "support": support,
        },
        "defensive_trigger": (
            [
                "premarket_setup 至少满足4项：结构偏空、活跃关键时间、贴近压力带、外盘高弹性利好、近期快速上涨、量能/领涨确认不足",
                f"价格在 {pressure_low:.2f}-{pressure_high:.2f} 未获确认前保持 reduce_only；不得因单日高开直接恢复进攻",
            ]
            if states["risk_state"] == "preemptive_defensive"
            else [
                f"pressure_state=rejected：盘中测试 {pressure_low:.2f}-{pressure_high:.2f} 后重新跌回 {pressure_low:.2f} 下方",
                "participation_state=divergent：宽度、龙头相对强弱、同时段量速至少两项走弱；不得仅由 gap_up_fade 触发",
            ]
        ),
        "offensive_trigger": [
            f"价格站上并接受 {pressure_high:.2f}，pressure_state=accepted",
            "participation_state=confirming；回踩不失守后才恢复进攻",
        ],
        "invalidation": [
            "覆盖失效：快照晚于 forecast_cutoff、时点无法验证或关键字段缺失",
        ],
        "conditional_path": [
            {"horizon": "target_day", "if": "defensive_trigger 全部成立", "action": "reduce_only"},
            {"horizon": "T+1", "if": "压力拒绝仍未修复", "action": "continue_defense"},
            {"horizon": "T+1/T+3", "if": "压力接受且参与度确认", "action": "resume_offense"},
        ],
        "valid_for": "target_day",
        "next_review": "T+1 close",
        "data_gaps": sorted(set(gaps)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the independent execution overlay")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--snapshot", help="09:25 竞价或盘中同点时 JSON 快照")
    parser.add_argument("--pressure-low", type=float)
    parser.add_argument("--pressure-high", type=float)
    parser.add_argument("--support", type=float)
    parser.add_argument("--gap-threshold", type=float, default=0.005)
    parser.add_argument("--fade-threshold", type=float, default=0.5)
    parser.add_argument("--pack-output")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    pack = json.loads(Path(args.pack).read_text(encoding="utf-8"))
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8")) if args.snapshot else None
    pressure_high = args.pressure_high if args.pressure_high is not None else critical_level(pack, "upside_confirmation")
    pressure_low = args.pressure_low if args.pressure_low is not None else pressure_high
    support = args.support if args.support is not None else critical_level(pack, "downside_confirmation")
    if pressure_high is None or pressure_low is None or support is None:
        raise SystemExit("缺少压力带或支撑位；请传参或在 critical_evidence.critical_levels 中提供")
    overlay = build_overlay(
        pack,
        snapshot,
        pressure_low=pressure_low,
        pressure_high=pressure_high,
        support=support,
        gap_threshold=args.gap_threshold,
        fade_threshold=args.fade_threshold,
    )
    atomic_write_json(Path(args.output), overlay)
    if args.pack_output:
        enriched = dict(pack)
        enriched["execution_overlay"] = overlay
        enriched.setdefault("source_used", {})["execution_overlay"] = "scripts/execution_overlay.py"
        atomic_write_json(Path(args.pack_output), enriched)
    print(json.dumps(overlay, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
