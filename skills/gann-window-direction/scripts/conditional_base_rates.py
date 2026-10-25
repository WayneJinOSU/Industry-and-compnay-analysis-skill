#!/usr/bin/env python3
"""Compute point-in-time conditional next-day base rates for a broad index.

The script deliberately separates:
  * volume above the previous day;
  * volume above the trailing 20-day mean;
  * low close position.

This prevents a broad "big down day" narrative from borrowing the result of a
different volume definition.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from common import RULESET_VERSION, atomic_write_json, resolve_available_at


def read_daily(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    date_column = next(
        (column for column in frame.columns if str(column).lower() in ("date", "trade_date", "time")),
        None,
    )
    if date_column is None:
        raise SystemExit("日线文件缺少 date/trade_date/time 列")
    frame = frame.rename(columns={date_column: "date"})
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    required = ("open", "high", "low", "close", "volume")
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise SystemExit(f"日线文件缺少列：{missing}")
    frame = frame.dropna(subset=["date", "open", "high", "low", "close", "volume"])
    frame = frame.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
    if (frame[["high", "low", "close"]] <= 0).any().any():
        raise SystemExit("OHLC 存在非正价格")
    invalid = (
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
    )
    if invalid.any():
        raise SystemExit(f"OHLC 关系不合法，异常行数：{int(invalid.sum())}")
    return frame


def exact_binomial_upper(k: int, n: int, baseline: float) -> float | None:
    if n <= 0 or not 0 < baseline < 1:
        return None
    probability = sum(
        math.comb(n, value) * baseline**value * (1 - baseline) ** (n - value)
        for value in range(k, n + 1)
    )
    return min(1.0, probability)


def describe(
    frame: pd.DataFrame,
    mask: pd.Series,
    baseline_up: float,
    *,
    key: str,
    label: str,
    definition: str,
    current_match: bool,
) -> dict:
    eligible = mask & frame["next_ret"].notna()
    sample = frame.loc[eligible]
    n = int(len(sample))
    if n == 0:
        return {
            "key": key,
            "label": label,
            "definition": definition,
            "current_match": current_match,
            "n": 0,
            "status": "insufficient_sample",
        }
    next_ret = sample["next_ret"]
    up_count = int((next_ret > 0).sum())
    up_rate = up_count / n
    return {
        "key": key,
        "label": label,
        "definition": definition,
        "current_match": bool(current_match),
        "n": n,
        "next_day_up_rate": round(up_rate, 4),
        "unconditional_up_rate": round(baseline_up, 4),
        "excess_up_rate": round(up_rate - baseline_up, 4),
        "next_day_mean_return": round(float(next_ret.mean()), 6),
        "next_day_median_return": round(float(next_ret.median()), 6),
        "next_day_gap_down_rate": round(float((sample["next_open_vs_prev_close"] < 0).mean()), 4),
        "exact_binomial_p_vs_unconditional": (
            round(exact_binomial_upper(up_count, n, baseline_up), 6)
            if exact_binomial_upper(up_count, n, baseline_up) is not None
            else None
        ),
        "status": "usable" if n >= 30 else "insufficient_sample",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute conditional next-day base rates without look-ahead")
    parser.add_argument("--index-daily", required=True)
    parser.add_argument("--asof", required=True, help="YYYY-MM-DD")
    parser.add_argument("--lookback-start", default="2015-01-01")
    parser.add_argument("--drop-threshold", type=float, default=-0.014)
    parser.add_argument("--low-close-threshold", type=float, default=0.25)
    parser.add_argument("--volume-window", type=int, default=20)
    parser.add_argument("--stage", default="post_close_review", choices=("premarket", "preopen_0925", "intraday_update", "post_close_review"))
    parser.add_argument("--available-at", help="派生统计结果的明确可得时间；盘中回放应传快照时间")
    parser.add_argument("--output", required=True, help="输出目录")
    args = parser.parse_args()

    asof = pd.Timestamp(args.asof).normalize()
    lookback_start = pd.Timestamp(args.lookback_start).normalize()
    frame = read_daily(Path(args.index_daily).expanduser().resolve())
    frame = frame[frame["date"] <= asof].copy()
    if frame.empty:
        raise SystemExit(f"截至 {asof.date()} 没有可用日线")
    frame = frame[frame["date"] >= lookback_start].reset_index(drop=True)
    if len(frame) < 60:
        raise SystemExit(f"样本仅 {len(frame)} 行，不足以计算条件基率")

    frame["ret"] = frame["close"].pct_change()
    frame["next_ret"] = frame["ret"].shift(-1)
    frame["next_open_vs_prev_close"] = frame["open"].shift(-1) / frame["close"] - 1
    span = frame["high"] - frame["low"]
    frame["close_position"] = np.where(
        span > 0,
        (frame["close"] - frame["low"]) / span,
        0.5,
    )
    frame["volume_above_prior_20d_mean"] = frame["volume"] > (
        frame["volume"].rolling(args.volume_window, min_periods=args.volume_window).mean().shift(1)
    )
    frame["volume_above_20d_mean_inclusive"] = frame["volume"] > (
        frame["volume"].rolling(args.volume_window, min_periods=args.volume_window).mean()
    )
    frame["volume_expands_1d"] = frame["volume"] > frame["volume"].shift(1)
    frame["drop"] = frame["ret"] <= args.drop_threshold
    frame["low_close"] = frame["close_position"] <= args.low_close_threshold

    current = frame.iloc[-1]
    baseline_sample = frame["next_ret"].dropna()
    baseline_up = float((baseline_sample > 0).mean())

    states = [
        (
            "drop",
            "大跌日",
            f"当日收益 <= {args.drop_threshold:.1%}",
            frame["drop"],
        ),
        (
            "drop_low_close",
            "大跌且低位收盘",
            f"当日收益 <= {args.drop_threshold:.1%} 且收盘位于振幅下 {args.low_close_threshold:.0%}",
            frame["drop"] & frame["low_close"],
        ),
        (
            "drop_volume_expansion_1d",
            "大跌且较前一日放量",
            f"当日收益 <= {args.drop_threshold:.1%} 且成交量高于前一日",
            frame["drop"] & frame["volume_expands_1d"],
        ),
        (
            "drop_volume_above_prior_20d_mean",
            "大跌且高于前20日均量",
            f"当日收益 <= {args.drop_threshold:.1%} 且成交量高于前 {args.volume_window} 日均量",
            frame["drop"] & frame["volume_above_prior_20d_mean"],
        ),
        (
            "drop_low_close_volume_expansion_1d",
            "大跌、低位收盘且较前一日放量",
            f"跌幅门槛 + 收盘位置门槛 + 成交量高于前一日",
            frame["drop"] & frame["low_close"] & frame["volume_expands_1d"],
        ),
        (
            "drop_low_close_volume_above_prior_20d_mean",
            "大跌、低位收盘且高于前20日均量",
            f"跌幅门槛 + 收盘位置门槛 + 成交量高于前 {args.volume_window} 日均量",
            frame["drop"] & frame["low_close"] & frame["volume_above_prior_20d_mean"],
        ),
        (
            "drop_low_close_volume_expansion_and_above_20d",
            "大跌、低位收盘、较前日与20日均量同时放量",
            "跌幅门槛 + 收盘位置门槛 + 两种量能条件同时满足",
            frame["drop"]
            & frame["low_close"]
            & frame["volume_expands_1d"]
            & frame["volume_above_prior_20d_mean"],
        ),
    ]

    rows = []
    for key, label, definition, mask in states:
        rows.append(
            describe(
                frame,
                mask,
                baseline_up,
                key=key,
                label=label,
                definition=definition,
                current_match=bool(mask.iloc[-1]),
            )
        )
    result = {
        "ruleset_version": RULESET_VERSION,
        "asof": asof.strftime("%Y-%m-%d"),
        "data_asof": asof.strftime("%Y-%m-%d"),
        "stage": args.stage,
        "available_at": resolve_available_at(
            asof,
            stage=args.stage,
            explicit=args.available_at,
            forecast_cutoff=args.available_at,
        ),
        "source": "local index daily filtered to asof",
        "data_quality": "complete",
        "point_in_time_filter_applied": True,
        "lookback_start": frame["date"].iloc[0].strftime("%Y-%m-%d"),
        "baseline": {
            "n": int(len(baseline_sample)),
            "next_day_up_rate": round(baseline_up, 4),
            "next_day_mean_return": round(float(baseline_sample.mean()), 6),
        },
        "current_state": {
            "date": current["date"].strftime("%Y-%m-%d"),
            "return": round(float(current["ret"]), 6),
            "close_position": round(float(current["close_position"]), 6),
            "volume_vs_previous_day": round(float(current["volume"] / frame["volume"].iloc[-2] - 1), 6),
            "volume_vs_prior_20d_mean": round(
                float(
                    current["volume"]
                    / frame["volume"].rolling(args.volume_window, min_periods=args.volume_window).mean().shift(1).iloc[-1]
                    - 1
                ),
                6,
            ),
            "volume_above_prior_20d_mean": bool(current["volume_above_prior_20d_mean"]),
            "volume_expands_1d": bool(current["volume_expands_1d"]),
        },
        "states": rows,
        "matched_states": [row["key"] for row in rows if row["current_match"]],
        "rule": (
            "只有 current_match=true 的条件基率才能作为当前状态证据。"
            "‘较前一日放量’与‘高于20日均量’不得混用；不匹配时必须标 unmatched。"
        ),
    }

    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output / "conditional_base_rates.json", result)
    pd.DataFrame(rows).to_csv(output / "conditional_base_rates.csv", index=False)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
