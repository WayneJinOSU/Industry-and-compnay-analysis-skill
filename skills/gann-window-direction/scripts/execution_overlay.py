#!/usr/bin/env python3
"""Build point-in-time execution facts without deriving risk or action decisions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import RULESET_VERSION, atomic_write_json, parse_available_at, parse_cutoff


GAP_STATES = ("expected", "confirmed", "faded", "not_applicable", "unknown")
PRESSURE_STATES = ("untested", "accepted", "rejected", "ambiguous", "not_applicable", "unknown")
PARTICIPATION_STATES = ("confirming", "divergent", "unknown")
SETUP_EVIDENCE_STATES = ("met", "not_met", "unknown")


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


def premarket_facts(
    pack: dict,
    *,
    pressure_low: float,
    pressure_high: float,
) -> tuple[dict, list[dict], list[str]]:
    """Compute point-in-time premarket facts without deriving an action."""
    summary = ((pack.get("space_levels") or {}).get("level_registry_summary") or {})
    recent = pack.get("recent_5d_raw") or []
    external = pack.get("external_market") or {}
    information = pack.get("information_content") or {}
    leadership = pack.get("leadership") or {}

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
    external_asia = {
        code: finite_number((pack.get("external_market") or {}).get(code, {}), "pct_chg")
        for code in ("N225", "KS11", "TWII", "XIN9")
    }
    asia_down_count = sum(
        value is not None and value <= -0.5 for value in external_asia.values()
    )
    asia_known_count = sum(value is not None for value in external_asia.values())
    us_risk_off = bool(
        (external_values["SOX"] is not None and external_values["SOX"] <= -2.0)
        or (
            external_values["IXIC"] is not None
            and external_values["IXIC"] <= -1.0
            and external_values["NDX"] is not None
            and external_values["NDX"] <= -1.0
        )
    )
    external_risk_shock = bool(us_risk_off and asia_down_count >= 2)
    external_extreme = bool(external_euphoria or external_risk_shock)
    external_known = any(value is not None for value in external_values.values())
    external_state = (
        "risk_on_euphoria"
        if external_euphoria
        else "risk_off_shock"
        if external_risk_shock
        else "risk_off_unconfirmed"
        if us_risk_off
        else "neutral"
        if external_known
        else "unknown"
    )
    volume_content = information.get("volume")
    leadership_state = leadership.get("state")
    if volume_content == "weak" or leadership_state in ("leadership_lagging", "leadership_neutral"):
        confirmation_deficit_status = "met"
    elif volume_content == "informative" and leadership_state == "leadership_confirming":
        confirmation_deficit_status = "not_met"
    else:
        confirmation_deficit_status = "unknown"
    time_window_known = bool(time_window.get("status") or time_window.get("active_window"))
    key_window_status = "met" if key_window else "not_met" if time_window_known else "unknown"
    pressure_status = (
        "met" if near_supply else "not_met" if distance_atr is not None else "unknown"
    )
    external_status = (
        "met"
        if external_extreme
        else "unknown"
        if external_state in ("risk_off_unconfirmed", "unknown")
        else "not_met"
    )
    structure_memory = pack.get("structure_memory") or {}
    memory_path = structure_memory.get("recent_path_pressure") or {}
    if three_day_impulse is not None and three_day_impulse >= 0.015:
        path_status = "met"
        path_subtype = "fast_impulse"
        path_detail = f"最近3日涨幅{three_day_impulse:.4%}，达到快速上涨门槛"
    elif memory_path.get("status") == "met":
        path_status = "met"
        path_subtype = str(memory_path.get("subtype") or "structure_pressure")
        path_detail = str(memory_path.get("detail") or "关键位记忆显示近期路径压力")
    elif three_day_impulse is not None and memory_path.get("status") in ("met", "not_met"):
        path_status = "not_met"
        path_subtype = "none"
        path_detail = "近期既无快速上涨脉冲，也无破位未收复或支撑附近弱收盘"
    else:
        path_status = "unknown"
        path_subtype = "unknown"
        path_detail = "近期路径压力状态缺失"

    def evidence_row(name: str, status: str, detail: str) -> dict:
        if status not in SETUP_EVIDENCE_STATES:
            raise ValueError(f"盘前证据状态非法：{status}")
        value = True if status == "met" else False if status == "not_met" else None
        return {"name": name, "status": status, "value": value, "detail": detail}

    evidence = [
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
            "external_extreme",
            external_status,
            (
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
                if external_state == "risk_on_euphoria"
                else (
                    f"美国科技与半导体走弱，亚洲开盘下跌确认{asia_down_count}个市场"
                    if external_state == "risk_off_shock"
                    else "美国科技与半导体走弱，但亚洲确认不足"
                    if external_state == "risk_off_unconfirmed"
                    else "外部极端状态未成立"
                )
            )
            if external_state != "unknown"
            else "高弹性外围市场锚点缺失",
        ),
        evidence_row(
            "recent_path_pressure",
            path_status,
            path_detail,
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
    for row in evidence:
        if row["status"] == "unknown":
            gaps.append(f"premarket.evidence.{row['name']}")

    metrics = {
        "close": close,
        "atr14": atr,
        "distance_to_pressure_low_atr": None if distance_atr is None else round(distance_atr, 4),
        "three_day_close_return": None if three_day_impulse is None else round(three_day_impulse, 6),
        "sox_pct_chg": external_values["SOX"],
        "nasdaq_pct_chg": external_values["IXIC"],
        "external_state": external_state,
        "asia_down_count": asia_down_count,
        "asia_known_count": asia_known_count,
        "external_risk_shock": external_risk_shock,
        "path_pressure_subtype": path_subtype,
    }
    return metrics, evidence, gaps


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
    return {
        "gap_state": gap_state,
        "pressure_state": pressure_state,
        "participation_state": participation,
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
    setup_metrics, setup_evidence, setup_gaps = premarket_facts(
        pack,
        pressure_low=pressure_low,
        pressure_high=pressure_high,
    )
    if snapshot is None:
        states = {
            "gap_state": "not_applicable",
            "pressure_state": "untested",
            "participation_state": "unknown",
        }
        metrics = setup_metrics
        gaps = setup_gaps
        decision_mode = "premarket_facts"
        data_asof = parse_cutoff(pack["feature_cutoff"]).date().isoformat()
        available_at = cutoff.isoformat(timespec="seconds")
        source = "deterministic premarket facts from point-in-time pack"
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
        gaps = setup_gaps + snapshot_gaps
        decision_mode = "combined"
    return {
        "ruleset_version": RULESET_VERSION,
        "stage": stage,
        "target_date": pack["target_date"],
        "data_asof": data_asof,
        "available_at": available_at,
        "source": source,
        "data_quality": data_quality,
        "decision_mode": decision_mode,
        "setup_evidence": setup_evidence,
        **states,
        "metrics": metrics,
        "thresholds": {
            "gap_up": gap_threshold,
            "gap_fade": fade_threshold,
            "pressure_low": pressure_low,
            "pressure_high": pressure_high,
            "support": support,
        },
        "invalidation": [
            "事实覆盖失效：快照晚于 forecast_cutoff、时点无法验证或关键字段缺失",
        ],
        "valid_for": "target_day",
        "next_review": "T+1 close",
        "data_gaps": sorted(set(gaps)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the point-in-time execution fact layer")
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
    band = (pack.get("level_context") or {}).get("decision_band") or {}
    pressure_high = args.pressure_high if args.pressure_high is not None else band.get("pressure_defense")
    pressure_low = args.pressure_low if args.pressure_low is not None else pressure_high
    support = args.support if args.support is not None else band.get("support_defense")
    if pressure_high is None or pressure_low is None or support is None:
        raise SystemExit("缺少压力带或支撑位；请传参或在 level_context.decision_band 中提供")
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
