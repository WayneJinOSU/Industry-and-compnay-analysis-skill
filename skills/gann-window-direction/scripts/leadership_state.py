#!/usr/bin/env python3
"""领涨结构状态量：由确定性计算给出 leadership 维度与反弹性质判定。

本脚本不做联网取数。输入为已落地的 CSV，输出 leadership_state.json。
口径与阈值定义见 references/evidence-rules.md，人工不得替代数值。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from common import RULESET_VERSION, atomic_write_json, breadth_state, parse_date, resolve_available_at

GAP_THRESHOLD = 0.015


def load_basket(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"ts_code", "name", "role"}
    missing = required.difference(frame.columns)
    if missing:
        raise SystemExit(f"篮子文件缺少列: {sorted(missing)}")
    if frame["ts_code"].duplicated().any():
        raise SystemExit("篮子存在重复代码；同一标的只能出现一次")
    return frame


def load_bars(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"ts_code", "date", "open", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise SystemExit(f"行情文件缺少列: {sorted(missing)}")
    frame["date"] = pd.to_datetime(frame["date"])
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values(["ts_code", "date"]).reset_index(drop=True)


def weekly_above_rate(bars: pd.DataFrame, asof: pd.Timestamp) -> tuple[float | None, int]:
    above = 0
    total = 0
    for _, group in bars.groupby("ts_code"):
        group = group[group["date"] <= asof]
        if len(group) < 260:
            continue
        weekly = (
            group.set_index("date")["close"].resample("W-FRI").last().dropna()
        )
        if len(weekly) < 40:
            continue
        ema13 = weekly.ewm(span=13, adjust=False).mean().iloc[-1]
        ema34 = weekly.ewm(span=34, adjust=False).mean().iloc[-1]
        last = weekly.iloc[-1]
        above += int(last > ema13 and last > ema34)
        total += 1
    if total == 0:
        return None, 0
    return above / total, total


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute the leadership dimension from local CSVs")
    parser.add_argument("--basket", required=True, help="篮子 CSV：ts_code,name,role(,theme)")
    parser.add_argument("--leader-bars", required=True, help="成员日线长表：ts_code,date,open,high,low,close")
    parser.add_argument("--index-bars", required=True, help="指数日线：date,close（用于 RS 口径，可与其他指数共用）")
    parser.add_argument("--breadth", help="可选：全市场宽度 CSV，含 date,advance_ratio,equal_weight_ret")
    parser.add_argument("--target-date", required=True, help="目标交易日 YYYY-MM-DD")
    parser.add_argument(
        "--asof",
        help="实际使用的最后一根行情日期。盘前应传 T-1；缺省时若目标日缺 bar，则自动取目标日前最近交易日",
    )
    parser.add_argument("--available-at", help="派生领涨状态的明确可得时间；盘中回放必须提供")
    parser.add_argument("--basket-version", default=None)
    parser.add_argument("--stage", default="post_close", choices=["premarket", "intraday_partial", "post_close"])
    parser.add_argument(
        "--key-level-reclaimed",
        default="unknown",
        choices=["true", "false", "unknown"],
        help="关键压力位是否已收盘收复（用于反弹性质判定）",
    )
    parser.add_argument(
        "--volume-ratio-20d",
        type=float,
        default=None,
        help="当日量能相对 20 日中位数的比值（用于反弹性质判定）",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    target = parse_date(args.target_date)
    basket = load_basket(Path(args.basket))
    bars = load_bars(Path(args.leader_bars))
    bars = bars[bars["date"] < target] if args.stage == "premarket" and not args.asof else bars[bars["date"] <= target]
    index_bars = pd.read_csv(args.index_bars, parse_dates=["date"])
    if args.asof:
        asof = parse_date(args.asof)
        bars = bars[bars["date"] <= asof]
        index_bars = index_bars[index_bars["date"] <= asof]
    elif args.stage == "premarket" and not (bars["date"] == target).any():
        asof = pd.Timestamp(bars["date"].max())
    else:
        asof = target
    if args.stage == "premarket" and asof >= target:
        raise SystemExit("盘前 leadership_state 必须使用严格早于 target-date 的 asof")
    bars = bars[bars["date"] <= asof].copy()
    index_bars = index_bars[index_bars["date"] <= asof].copy()
    index_bars = index_bars.sort_values("date")

    rows = []
    for _, member in basket.iterrows():
        group = bars[bars["ts_code"] == member["ts_code"]]
        if len(group) < 2 or group["date"].iloc[-1] != asof:
            rows.append({"ts_code": member["ts_code"], "name": member["name"], "role": member["role"],
                         "status": "missing_asof_bar"})
            continue
        latest, previous = group.iloc[-1], group.iloc[-2]
        change = latest["close"] / previous["close"] - 1
        gap = latest["open"] / previous["close"] - 1
        rows.append({
            "ts_code": member["ts_code"],
            "name": member["name"],
            "role": member["role"],
            "status": "ok",
            "prev_close": float(previous["close"]),
            "open": float(latest["open"]),
            "close": float(latest["close"]),
            "ret": float(change),
            "gap": float(gap),
            "gap_filled": bool(gap >= GAP_THRESHOLD and latest["close"] < previous["close"]),
        })
    detail = pd.DataFrame(rows)
    valid = detail[detail["status"] == "ok"]

    leader_ret = float(valid["ret"].mean()) if len(valid) else None
    gapped = valid[valid["gap"] >= GAP_THRESHOLD]
    gap_up_fade_rate = float(gapped["gap_filled"].mean()) if len(gapped) else None
    gap_sample_count = int(len(gapped))
    gap_sample_status = "available" if gap_sample_count else "not_applicable"
    above_rate, above_sample = weekly_above_rate(bars, asof)

    market_equal_weight_ret = None
    breadth_note = "未提供宽度文件"
    if args.breadth:
        breadth = pd.read_csv(args.breadth, parse_dates=["date"])
        breadth = breadth[breadth["date"] == asof]
        if len(breadth) and "equal_weight_ret" in breadth.columns:
            market_equal_weight_ret = float(breadth["equal_weight_ret"].iloc[0])
            breadth_note = "来自宽度文件"
        else:
            breadth_note = "宽度文件缺少目标日或 equal_weight_ret 列"

    leadership_spread = (
        leader_ret - market_equal_weight_ret
        if leader_ret is not None and market_equal_weight_ret is not None
        else None
    )

    if leader_ret is None or market_equal_weight_ret is None:
        state = "uninformative"
    elif (
        leadership_spread is not None
        and leadership_spread >= 0.003
        and gap_up_fade_rate is not None
        and gap_up_fade_rate <= 0.34
    ):
        state = "leadership_confirming"
    elif (leadership_spread is not None and leadership_spread <= -0.005) or (
        gap_up_fade_rate is not None and gap_up_fade_rate >= 0.50
    ):
        state = "leadership_lagging"
    else:
        state = "leadership_neutral"

    index_ret_4w = None
    if len(index_bars) > 20:
        index_ret_4w = float(index_bars["close"].iloc[-1] / index_bars["close"].iloc[-21] - 1)
    leader_rs_4w = None
    if len(valid) and len(bars) > 20:
        leader_returns = []
        for code in valid["ts_code"]:
            group = bars[bars["ts_code"] == code]
            if len(group) > 20:
                leader_returns.append(group["close"].iloc[-1] / group["close"].iloc[-21] - 1)
        if leader_returns and index_ret_4w is not None:
            leader_rs_4w = float(sum(leader_returns) / len(leader_returns) - index_ret_4w)

    breadth_improving = None
    breadth_state_value = None
    if args.breadth:
        breadth_all = pd.read_csv(args.breadth, parse_dates=["date"])
        breadth_all = breadth_all[breadth_all["date"] <= asof]
        if len(breadth_all) >= 10 and "advance_ratio" in breadth_all.columns:
            breadth_state_value, _, _, _ = breadth_state(breadth_all)
            breadth_improving = breadth_state_value == "improving"

    volume_ok = None if args.volume_ratio_20d is None else args.volume_ratio_20d >= 1.0
    reclaimed = {"true": True, "false": False, "unknown": None}[args.key_level_reclaimed]

    if state == "leadership_confirming" and breadth_improving and reclaimed and volume_ok:
        rebound_quality = "leadership_repair"
    elif state == "leadership_lagging" and breadth_improving:
        rebound_quality = "oversold_bounce"
    else:
        rebound_quality = "unclear"

    available_at = resolve_available_at(asof, stage=args.stage, explicit=args.available_at)
    payload = {
        "ruleset_version": RULESET_VERSION,
        "target_date": args.target_date,
        "asof": asof.strftime("%Y-%m-%d"),
        "data_asof": asof.strftime("%Y-%m-%d"),
        "available_at": available_at,
        "source": "local leader_bars + market breadth; deterministic calculation",
        "data_quality": "complete" if len(valid) == len(basket) else "partial",
        "stage": args.stage,
        "basket_version": args.basket_version,
        "basket_size": int(len(basket)),
        "members_ok": int(len(valid)),
        "leader_ret": leader_ret,
        "market_equal_weight_ret": market_equal_weight_ret,
        "leadership_spread": leadership_spread,
        "gap_up_fade_rate": gap_up_fade_rate,
        "gap_sample_count": gap_sample_count,
        "gap_sample_status": gap_sample_status,
        "leader_above_rate": above_rate,
        "leader_above_sample": above_sample,
        "leader_rs_4w": leader_rs_4w,
        "state": state,
        "rebound_quality": rebound_quality,
        "inputs_used": {
            "breadth": breadth_note,
            "breadth_state": breadth_state_value,
            "breadth_improving": breadth_improving,
            "key_level_reclaimed": reclaimed,
            "volume_ratio_20d": args.volume_ratio_20d,
        },
        "members": detail.to_dict("records"),
    }
    atomic_write_json(Path(args.output), payload)
    print(json.dumps({k: payload[k] for k in (
        "target_date", "leader_ret", "market_equal_weight_ret", "leadership_spread",
        "gap_up_fade_rate", "leader_above_rate", "state", "rebound_quality")},
        ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
