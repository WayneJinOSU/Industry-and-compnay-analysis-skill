#!/usr/bin/env python3
"""状态量输入：计算点时状态和逐层信息量。

为什么必须存在：
情景区间依赖 weekly_regime / funding_state / breadth_state，报告还需逐层判定
information_content。本脚本同时执行 as-of 截断，避免输入文件含未来行时污染状态。

本脚本只做确定性计算，不做方向判断；输出 JSON 供报告引用，并生成门禁要求的
`data_gap_register`（含每条字段的兜底尝试与状态，禁止静默丢弃）。

用法：
python3 scripts/state_inputs.py --index-daily <csv> --market-daily <csv> --margin <csv> \
    --external <json> [--leaders <csv>] --asof YYYY-MM-DD --output <dir>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from common import (
    RULESET_VERSION,
    atomic_write_json,
    breadth_state,
    filter_asof,
    normalize_date_column,
    parse_available_at,
    parse_cutoff,
    parse_date,
    resolve_available_at,
    weekly_regime,
)

# 外部锚点：链 → 标的。SOX 必须存在，缺失时本层只能判 uninformative 并登记缺口。
US_ANCHORS = {
    "IXIC": "整体风险偏好（纳指综合）",
    "SPX": "整体风险偏好（标普）",
    "DJI": "价值与权重",
    "SOX": "AI 算力/半导体链",
}
LAYERS = ("external", "volume", "margin", "breadth", "leadership", "path", "event")


def funding_state(margin: pd.DataFrame) -> tuple[str, dict, bool]:
    frame = margin.copy()
    column = "trade_date" if "trade_date" in frame.columns else "date"
    frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.normalize()
    frame = frame.sort_values(column).reset_index(drop=True)
    balance, net_buy = frame["rzye"], frame["margin_net_buy"]
    change_20d = float(balance.iloc[-1] / balance.iloc[-21] - 1) if len(frame) > 20 else float("nan")
    daily_change = balance.pct_change().dropna()
    latest_change = float(daily_change.iloc[-1])
    sigma = float(daily_change.tail(20).std())
    spike = bool(sigma > 0 and latest_change <= -1.0 * sigma)
    if change_20d <= -0.02 or (len(net_buy) and net_buy.iloc[-1] < 0 and change_20d < 0):
        state = "deleveraging"
    elif change_20d >= 0.01 and net_buy.iloc[-1] > 0:
        state = "accumulating"
    else:
        state = "neutral"
    detail = {
        "data_asof": str(frame[column].iloc[-1].date()),
        "balance": float(balance.iloc[-1]),
        "change_1d": round(latest_change, 5),
        "change_20d": None if np.isnan(change_20d) else round(change_20d, 5),
        "net_buy": float(net_buy.iloc[-1]),
        "latest_change_z": None if sigma == 0 else round(latest_change / sigma, 3),
    }
    return state, detail, spike


def path_state(index_daily: pd.DataFrame) -> tuple[str, dict]:
    frame = index_daily.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values("date").tail(3).reset_index(drop=True)
    labels = []
    for _, row in frame.iterrows():
        span = row["high"] - row["low"]
        if span <= 0:
            continue
        position = (row["close"] - row["low"]) / span
        labels.append("close_near_low" if position <= 0.30 else "close_near_high" if position >= 0.70 else "mid")
    repeat = len(labels) >= 2 and labels[-1] == labels[-2]
    return ("informative" if repeat else "weak"), {"recent_labels": labels}


def external_content(pack: dict, gap: list, forecast_cutoff: str | None = None) -> tuple[str, dict]:
    external = (pack or {}).get("external_market", {})
    existing_gaps = list((pack or {}).get("data_gap_register") or [])
    present = {code: value for code, value in external.items() if value.get("trade_date")}
    missing = [code for code in US_ANCHORS if code not in present]
    for code in missing:
        if not any(f"external.{code}" in str(row.get("field", "")) for row in existing_gaps):
            gap.append(
                {
                    "field": f"external.{code}",
                    "status": "missing",
                    "fallback_attempted": False,
                    "reason": "US anchor unavailable in pack",
                }
            )
    if missing:
        return "uninformative", {"missing_anchors": missing, "note": "锚点缺失时该层不得计入方向"}

    if forecast_cutoff:
        cutoff = parse_cutoff(forecast_cutoff)
        future = []
        unknown_time = []
        for code, value in present.items():
            observed = parse_available_at(value.get("available_at"))
            if observed is None:
                unknown_time.append(code)
            elif observed > cutoff:
                future.append({"code": code, "available_at": observed.isoformat()})
        if future:
            gap.append(
                {
                    "field": "external.future_records",
                    "status": "future",
                    "fallback_attempted": False,
                    "reason": f"输入包外盘记录晚于 forecast_cutoff：{future}",
                }
            )
            return "uninformative", {"future_records": future, "note": "存在未来外盘数据，外盘层不得参与方向"}
        if unknown_time:
            gap.append(
                {
                    "field": "external.available_at",
                    "status": "missing",
                    "fallback_attempted": False,
                    "reason": f"以下外盘记录无法证明可得时间：{unknown_time}",
                }
            )
            return "uninformative", {"unknown_available_at": unknown_time}
    dates = {value["trade_date"] for value in present.values()}
    driving = max(dates)
    session = {code: present[code] for code in US_ANCHORS}
    moves = {code: float(value["pct_chg"]) for code, value in session.items()}
    same_direction = len({np.sign(v) for v in moves.values()}) == 1
    mean_abs = float(np.mean([abs(v) for v in moves.values()]))
    if same_direction and mean_abs >= 0.5:
        content = "informative"
    elif mean_abs < 0.2:
        content = "weak"
    else:
        content = "weak"
    return content, {"driving_session": driving, "moves": moves, "same_direction": same_direction}


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute state variables and per-layer information content")
    parser.add_argument("--index-daily", required=True)
    parser.add_argument("--market-daily", required=True)
    parser.add_argument("--margin", required=True)
    parser.add_argument("--external", help="direction_input_pack.json 绝对路径（读取 external_market）")
    parser.add_argument("--leaders", help="龙头状态 csv（可选，缺失时该层登记缺口）")
    parser.add_argument("--leadership-json", help="leadership_state.py 输出的完整 JSON")
    parser.add_argument("--extreme-stats", help="extreme_state_stats.py 输出的完整 JSON")
    parser.add_argument("--nearest-resistance", type=float, help="最近压力位（判定量能压缩所在侧）")
    parser.add_argument("--nearest-support", type=float, help="最近支撑位（判定量能压缩所在侧）")
    parser.add_argument("--asof", required=True, help="数据截点 YYYY-MM-DD")
    parser.add_argument("--feature-cutoff", help="可选 ISO 时间；数据的 data_asof 同时不得晚于该时间")
    parser.add_argument("--forecast-cutoff", help="可选 ISO 时间；用于核对外盘 available_at")
    parser.add_argument("--stage", default="premarket", choices=("premarket", "preopen_0925", "intraday_open", "intraday_update", "post_close_review"))
    parser.add_argument("--available-at", help="派生状态可用的明确时间；盘中回放应传快照时间")
    parser.add_argument("--pack-output", help="可选：把 state_inputs/information_content 回填到输入包的新路径")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    requested_asof = parse_date(args.asof)
    effective_asof = requested_asof
    if args.feature_cutoff:
        feature_day = parse_cutoff(args.feature_cutoff).date()
        effective_asof = min(requested_asof, pd.Timestamp(feature_day))

    raw = {
        "index_daily": pd.read_csv(args.index_daily),
        "market_daily": pd.read_csv(args.market_daily),
        "margin": pd.read_csv(args.margin),
    }
    index_daily = filter_asof(raw["index_daily"], effective_asof)
    market = filter_asof(raw["market_daily"], effective_asof)
    margin = filter_asof(raw["margin"], effective_asof)
    coverage = {}
    for label, frame in raw.items():
        filtered = filter_asof(frame, effective_asof)
        normalized_raw = normalize_date_column(frame.copy())
        coverage[label] = {
            "requested_max": str(normalized_raw["date"].max().date()),
            "used_min": str(filtered["date"].min().date()),
            "used_max": str(filtered["date"].max().date()),
            "rows": int(len(filtered)),
        }
    pack = json.loads(Path(args.external).read_text(encoding="utf-8")) if args.external else None
    leadership_payload = (
        json.loads(Path(args.leadership_json).read_text(encoding="utf-8"))
        if args.leadership_json
        else None
    )
    extreme_payload = (
        json.loads(Path(args.extreme_stats).read_text(encoding="utf-8"))
        if args.extreme_stats
        else None
    )
    gap: list[dict] = []

    regime, regime_detail = weekly_regime(index_daily)
    funding, funding_detail, funding_spike = funding_state(margin)
    breadth, breadth_detail, extreme_low, extreme_high = breadth_state(market)
    path_content, path_detail = path_state(index_daily)
    external_content_value, external_detail = external_content(pack, gap, args.forecast_cutoff)

    volume = market.copy()
    volume["date"] = pd.to_datetime(volume["date"])
    total = volume["total_amount"]
    ratio_20d = float(total.iloc[-1] / total.tail(20).median() - 1)
    volume_content = "informative" if abs(ratio_20d) >= 0.15 else "weak"
    volume_z = float((total.iloc[-1] - total.tail(20).mean()) / total.tail(20).std())
    vol_series = volume["total_volume"] if "total_volume" in volume.columns else total
    volume_z_series = float((vol_series.iloc[-1] - vol_series.tail(20).mean()) / vol_series.tail(20).std())
    volume_compression = bool(ratio_20d <= -0.20 or volume_z_series <= -1.0 or volume_z <= -1.0)
    last_close = float(index_daily["close"].iloc[-1])
    if args.nearest_resistance is not None and last_close < args.nearest_resistance:
        compression_side = "below_resistance"
    elif args.nearest_support is not None and last_close > args.nearest_support:
        compression_side = "above_support"
    elif args.nearest_resistance is not None or args.nearest_support is not None:
        compression_side = "mid_range"
    else:
        compression_side = "unknown"

    margin_content = "informative" if (funding_detail.get("change_20d") or 0) <= -0.02 or funding_spike else "weak"
    breadth_content = "informative" if (extreme_low or extreme_high or abs(breadth_detail["advance_ratio_z"]) >= 1.5) else "weak"

    if args.leadership_json:
        share = leadership_payload.get("leader_above_rate")
        sample = leadership_payload.get("leader_above_sample")
        if share is None or sample is None:
            leadership_content, leadership_detail = "uninformative", {}
            gap.append(
                {
                    "field": "leadership.basket",
                    "status": "missing",
                    "fallback_attempted": False,
                    "reason": "leadership JSON 缺少 leader_above_rate 或样本数",
                }
            )
        else:
            share = float(share)
            leadership_content = "informative" if share <= 0.34 or share >= 0.67 else "weak"
            leadership_detail = {"above_both_share": round(share, 3), "n": int(sample)}
    elif args.leaders:
        leaders = pd.read_csv(args.leaders)
        leader_date_column = next(
            (column for column in ("date", "trade_date", "latest_week_end") if column in leaders.columns),
            None,
        )
        if leader_date_column:
            leaders[leader_date_column] = pd.to_datetime(leaders[leader_date_column], errors="coerce")
            leaders = leaders[leaders[leader_date_column] <= effective_asof]
        if leaders.empty:
            leadership_content, leadership_detail = "uninformative", {}
            gap.append(
                {
                    "field": "leadership.basket",
                    "status": "missing",
                    "fallback_attempted": False,
                    "reason": "龙头状态在数据截点前没有可用记录；该层不得计入方向",
                }
            )
        else:
            above = leaders["above_ema13"].astype(str).str.lower().eq("true") & leaders["above_ema34"].astype(str).str.lower().eq("true")
            share = float(above.mean())
            leadership_content = "informative" if share <= 0.34 or share >= 0.67 else "weak"
            leadership_detail = {"above_both_share": round(share, 3), "n": int(len(leaders))}
    else:
        leadership_content, leadership_detail = "uninformative", {}
        gap.append(
            {
                "field": "leadership.basket",
                "status": "missing",
                "fallback_attempted": False,
                "reason": "未提供龙头状态文件；该层不得计入方向",
            }
        )

    event_content = "uninformative"
    gap.append(
        {
            "field": "event.ledger",
            "status": "missing",
            "fallback_attempted": False,
            "reason": "事件账本未建立；该层不得计入方向",
        }
    )

    information_content = {
        "external": external_content_value,
        "volume": volume_content,
        "margin": margin_content,
        "breadth": breadth_content,
        "leadership": leadership_content,
        "path": path_content,
        "event": event_content,
    }
    informative_layers = [k for k, v in information_content.items() if v == "informative"]

    if regime == "down" and funding == "deleveraging" and breadth == "deteriorating":
        prior = {"downside_continuation": ">=35%", "range_oscillation": "20-35%", "upside_breakout": "15-30%", "tail_extreme_down": "<=10%"}
        cap_note = "weekly=down 且 funding=deleveraging 且 breadth=deteriorating：不得把回到中枢作为基准"
    elif regime == "down":
        prior = {"downside_continuation": "30-45%", "range_oscillation": ">=30%", "upside_breakout": "15-25%", "tail_extreme_down": "<=10%"}
        cap_note = "weekly=down 且资金/宽度不同向：downside_continuation 30-45%，range_oscillation 至少30%"
    elif regime == "up" and funding == "accumulating" and breadth == "improving":
        prior = {"downside_continuation": ">=35%（向上）", "range_oscillation": "20-35%", "upside_breakout": "15-30%", "tail_extreme_down": "<=10%"}
        cap_note = "镜像处理，突破方向优先"
    else:
        prior = {"downside_continuation": "<=40%", "range_oscillation": "<=40%", "upside_breakout": "—", "tail_extreme_down": "<=10%"}
        cap_note = "range 或跨层 mixed：权重由后续综合研判确定，只要求合计归一化"

    extreme_flags = {
        "breadth_extreme_low": extreme_low,
        "breadth_extreme_high": extreme_high,
        "funding_deleveraging_spike": funding_spike,
        "any_extreme": bool(extreme_low or extreme_high or funding_spike),
    }
    if extreme_flags["any_extreme"]:
        cap_note += "；存在极值状态时，按当前匹配状态的同口径条件分布确定反向分支下限"
    if volume_compression:
        cap_note += (
            "；量能压缩成立：upside_breakout 下限 25%，"
            "无宽度/等权修复确认时不得把“回到中枢”作为基准"
        )
        if prior.get("upside_breakout", "").startswith(("15-25", "15-30")):
            prior["upside_breakout"] = "25-30%"

    floors_by_state = {}
    reversal_floor = 0.25
    if extreme_payload:
        state_floor_map = extreme_payload.get("recommended_reversal_floor_by_state") or {}
        regime_key = "downtrend" if regime == "down" else "all"
        active_states = []
        if extreme_low:
            active_states.append("breadth_extreme_low")
        if funding_spike:
            active_states.append("funding_spike")
        for state_name in active_states:
            floor = ((state_floor_map.get(state_name) or {}).get(regime_key))
            if floor is not None:
                floors_by_state[state_name] = float(floor)
                reversal_floor = max(reversal_floor, float(floor))

    available_at = resolve_available_at(
        effective_asof,
        stage=args.stage,
        explicit=args.available_at,
        forecast_cutoff=args.forecast_cutoff,
    )
    result = {
        "ruleset_version": RULESET_VERSION,
        "asof": str(effective_asof.date()),
        "requested_asof": args.asof,
        "feature_cutoff": args.feature_cutoff,
        "forecast_cutoff": args.forecast_cutoff,
        "data_asof": str(effective_asof.date()),
        "stage": args.stage,
        "available_at": available_at,
        "source": "deterministic state calculation from point-in-time filtered local inputs",
        "data_quality": "partial" if gap else "complete",
        "point_in_time_filter_applied": True,
        "input_coverage": coverage,
        "weekly_regime": regime,
        "funding_state": funding,
        "breadth_state": breadth,
        "information_content": information_content,
        "informative_layers": informative_layers,
        "extreme_flags": extreme_flags,
        "reversal_floor": reversal_floor,
        "reversal_floor_by_state": floors_by_state,
        "volume_compression": volume_compression,
        "compression_side": compression_side,
        "volume_zscore_20d": round(volume_z_series, 3),
        "weight_prior": prior,
        "weight_cap_note": cap_note,
        "details": {
            "weekly_regime": regime_detail,
            "funding": funding_detail,
            "breadth": breadth_detail,
            "path": path_detail,
            "external": external_detail,
            "volume_ratio_20d": round(ratio_20d, 4),
            "volume_zscore_20d": round(volume_z_series, 3),
            "compression_side": compression_side,
            "leadership": leadership_detail,
        },
        "data_gap_register": gap,
        "note": "本文件只提供输入量，不产生方向结论；基准情景由信息量最高的内部层决定",
    }
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output / "state_inputs.json", result)
    if args.pack_output:
        if pack is None:
            raise SystemExit("--pack-output 需要 --external 指向基础输入包")
        enriched = dict(pack)
        enriched["ruleset_version"] = RULESET_VERSION
        enriched["state_inputs"] = result
        enriched["information_content"] = information_content
        if leadership_payload is not None:
            leadership_day = parse_date(leadership_payload.get("asof") or leadership_payload.get("target_date"))
            if leadership_day > effective_asof:
                raise SystemExit("leadership JSON 的 asof 晚于 state_inputs 截点")
            enriched["leadership"] = leadership_payload
        existing_gaps = list(enriched.get("data_gap_register") or [])
        known = {(row.get("field"), row.get("status")) for row in existing_gaps}
        for row in gap:
            key = (row.get("field"), row.get("status"))
            if key not in known:
                existing_gaps.append(row)
                known.add(key)
        enriched["data_gap_register"] = existing_gaps
        atomic_write_json(Path(args.pack_output), enriched)
    print(json.dumps({k: result[k] for k in ("asof", "weekly_regime", "funding_state", "breadth_state",
                                             "information_content", "extreme_flags", "volume_compression",
                                             "compression_side", "volume_zscore_20d", "weight_prior", "weight_cap_note")},
                     ensure_ascii=False, indent=2))
    print(f"\ndata_gap_register: {len(gap)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
