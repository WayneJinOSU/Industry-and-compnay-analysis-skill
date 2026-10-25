#!/usr/bin/env python3
"""极值状态的条件分布统计与状态专属反向分支下限。

第 7 节规定：极值状态（breadth_extreme / funding_spike）触发时，反向（均值回复）分支
权重不得低于 25%，且必须附同口径条件分布统计；样本不足 30 时只能写“样本不足”。
此前只有要求、没有估计器，于是那条下限只是一个未经检验的先验 —— 本脚本把它算出来。

输出：每个状态在 T+1 / T+3 / T+5 的前瞻分布、P(方向反转)、与无条件基线的二项检验，
以及一个 `recommended_reversal_floor`：只有在统计显著时才建议把下限提到 25% 以上。

用法：
python3 scripts/extreme_state_stats.py --index-daily <csv> [--margin <csv>] [--breadth <csv>] \
    --symbol 上证指数 --output <dir>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from common import RULESET_VERSION, atomic_write_json, filter_asof, parse_date, resolve_available_at

MIN_SAMPLE = 30
EXCESS_FOR_FLOOR = 0.05  # 相对基线的方向性超额门槛（5pp）


def binom_p(k: int, n: int, p0: float) -> float:
    """单侧二项检验 P(X >= k | n, p0)，避免外部依赖。"""
    if n == 0:
        return 1.0
    from math import comb

    return float(sum(comb(n, i) * p0**i * (1 - p0) ** (n - i) for i in range(k, n + 1)))


def build_features(index_daily: pd.DataFrame, margin: pd.DataFrame | None, breadth: pd.DataFrame | None) -> pd.DataFrame:
    frame = index_daily.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values("date").reset_index(drop=True)
    frame["pct_chg"] = frame["close"].pct_change()
    span = (frame["high"] - frame["low"]).replace(0, np.nan)
    frame["lower_shadow"] = (frame[["open", "close"]].min(axis=1) - frame["low"]) / span
    frame["close_position"] = (frame["close"] - frame["low"]) / span
    frame["ret_z"] = (frame["pct_chg"] - frame["pct_chg"].rolling(60).mean()) / frame["pct_chg"].rolling(60).std()
    frame["low20"] = frame["low"].rolling(20).min()
    frame["open_gap"] = frame["open"] / frame["close"].shift() - 1
    frame["sma50"] = frame["close"].rolling(50).mean()
    for horizon in (1, 3, 5):
        frame[f"fwd{horizon}"] = frame["close"].shift(-horizon) / frame["close"] - 1

    frame["state_crash"] = frame["ret_z"] <= -2.0
    frame["state_shadow_at_low"] = (frame["lower_shadow"] >= 0.5) & (frame["close"] <= frame["low20"] * 1.01)
    frame["state_gap_recovery"] = (frame["open_gap"] <= -0.008) & (frame["close"] > frame["open"])

    if margin is not None and not margin.empty:
        margin = margin.copy()
        column = "trade_date" if "trade_date" in margin.columns else "date"
        margin[column] = pd.to_datetime(margin[column].astype(str), format="%Y%m%d", errors="coerce").fillna(
            pd.to_datetime(margin[column], errors="coerce")
        )
        margin = margin.sort_values(column)
        margin["change"] = margin["rzye"].pct_change()
        margin["sigma20"] = margin["change"].rolling(20).std()
        margin["state_funding_spike"] = margin["change"] <= -1.0 * margin["sigma20"]
        frame = frame.merge(
            margin[[column, "state_funding_spike"]].rename(columns={column: "date"}), on="date", how="left"
        )
    else:
        frame["state_funding_spike"] = False

    if breadth is not None and not breadth.empty:
        breadth = breadth.copy()
        breadth["date"] = pd.to_datetime(breadth["date"])
        breadth["ratio_mean20"] = breadth["advance_ratio"].rolling(20).mean()
        breadth["ratio_std20"] = breadth["advance_ratio"].rolling(20).std()
        breadth["ratio_z20"] = (
            (breadth["advance_ratio"] - breadth["ratio_mean20"]) / breadth["ratio_std20"]
        )
        breadth["state_breadth_extreme_low"] = (
            (breadth["advance_ratio"] <= 0.15) | (breadth["ratio_z20"] <= -2.0)
        )
        frame = frame.merge(breadth[["date", "advance_ratio", "state_breadth_extreme_low"]], on="date", how="left")
    else:
        frame["state_breadth_extreme_low"] = False

    state_columns = [
        c
        for c in ("state_crash", "state_shadow_at_low", "state_gap_recovery", "state_funding_spike", "state_breadth_extreme_low")
        if c in frame.columns
    ]
    frame[state_columns] = frame[state_columns].fillna(False).astype(bool)
    frame["state_any_extreme"] = frame[state_columns].any(axis=1)
    frame["downtrend"] = frame["close"] < frame["sma50"]
    return frame, state_columns + ["state_any_extreme"]


def describe(subset: pd.DataFrame, baseline: dict) -> dict:
    row: dict = {"n": int(len(subset))}
    if len(subset) == 0:
        return row
    for horizon in (1, 3, 5):
        column = f"fwd{horizon}"
        values = subset[column].dropna()
        if values.empty:
            continue
        row[f"fwd{horizon}_mean"] = round(float(values.mean()) * 100, 3)
        row[f"fwd{horizon}_median"] = round(float(values.median()) * 100, 3)
        row[f"fwd{horizon}_P_up"] = round(float((values > 0).mean()), 4)
    up1 = subset["fwd1"].dropna()
    if not up1.empty and baseline.get("fwd1_P_up") is not None:
        k, n, p0 = int((up1 > 0).sum()), int(len(up1)), baseline["fwd1_P_up"]
        row["excess_fwd1_vs_baseline"] = round(row["fwd1_P_up"] - p0, 4)
        row["p_value_fwd1"] = round(binom_p(k, n, p0), 5)
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Conditional forward distribution of extreme states")
    parser.add_argument("--index-daily", required=True)
    parser.add_argument("--margin")
    parser.add_argument("--breadth")
    parser.add_argument("--symbol", default="上证指数")
    parser.add_argument("--asof", required=True, help="严格数据截点 YYYY-MM-DD")
    parser.add_argument("--stage", default="post_close_review", choices=("premarket", "preopen_0925", "intraday_update", "post_close_review"))
    parser.add_argument("--available-at", help="派生统计结果的明确可得时间；盘中回放应传快照时间")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    asof = parse_date(args.asof)
    index_daily = filter_asof(pd.read_csv(args.index_daily), asof)
    margin = filter_asof(pd.read_csv(args.margin), asof) if args.margin else None
    breadth = filter_asof(pd.read_csv(args.breadth), asof) if args.breadth else None
    frame, state_columns = build_features(index_daily, margin, breadth)
    sample = frame.dropna(subset=["fwd1"]).copy()

    baseline = {
        "fwd1_P_up": round(float((sample["fwd1"] > 0).mean()), 4),
        "fwd3_P_up": round(float((sample["fwd3"].dropna() > 0).mean()), 4),
        "fwd1_mean": round(float(sample["fwd1"].mean()) * 100, 3),
        "n": int(len(sample)),
        "start": str(sample["date"].min().date()),
        "end": str(sample["date"].max().date()),
    }

    rows: list[dict] = []
    for column in state_columns:
        for regime, subset in (("all", sample[sample[column]]), ("downtrend", sample[sample[column] & sample["downtrend"]])):
            stats = describe(subset, baseline)
            if not stats.get("n"):
                continue
            entry = {"state": column.replace("state_", ""), "regime_filter": regime, **stats}
            has_edge = (
                entry["n"] >= MIN_SAMPLE
                and entry.get("p_value_fwd1", 1) < 0.05
                and entry.get("excess_fwd1_vs_baseline", 0) >= EXCESS_FOR_FLOOR
            )
            entry["verdict"] = (
                "样本不足"
                if entry["n"] < MIN_SAMPLE
                else "有超额（该状态反向分支下限可升至 35%）"
                if has_edge
                else "无显著超额（反向分支下限维持 25%，不得据此提高）"
            )
            entry["recommended_reversal_floor"] = 0.25 if not has_edge else 0.35
            rows.append(entry)

    table = pd.DataFrame(rows).sort_values(["state", "regime_filter"])
    floors: dict[str, dict[str, float]] = {}
    for row in rows:
        floors.setdefault(row["state"], {})[row["regime_filter"]] = float(
            row.get("recommended_reversal_floor", 0.25)
        )
    recommended_floor = 0.25
    floor_note = (
        "默认反向分支下限为25%。只有当前匹配状态在对应市场状态下样本≥30、"
        "T+1超额≥5pp且p<0.05时，才允许该状态把下限提高到35%；不得跨状态借用。"
    )

    result = {
        "ruleset_version": RULESET_VERSION,
        "symbol": args.symbol,
        "asof": asof.strftime("%Y-%m-%d"),
        "data_asof": asof.strftime("%Y-%m-%d"),
        "stage": args.stage,
        "available_at": resolve_available_at(
            asof,
            stage=args.stage,
            explicit=args.available_at,
            forecast_cutoff=args.available_at,
        ),
        "source": "local historical daily/margin/breadth files filtered to asof",
        "data_quality": "complete" if breadth is not None and margin is not None else "partial",
        "baseline": baseline,
        "min_sample": MIN_SAMPLE,
        "states": rows,
        "recommended_reversal_floor_by_state": floors,
        "recommended_reversal_floor": recommended_floor,
        "floor_note": floor_note,
        "caveats": [
            "重叠窗口：T+3 / T+5 的前瞻窗口互相重叠，有效样本小于名义 n，显著性以 T+1 为主判据",
            "条件状态定义使用分布尺度（收益60日 z 分数、宽度20日 z 分数、两融20日 σ），当前与历史口径一致",
            "宽度极值状态需要逐日全市场家数序列；未提供时该状态不计入，也不得用指数代理冒充",
        ],
    }
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output / "extreme_state_stats.json", result)
    table.to_csv(output / "extreme_state_stats.csv", index=False)

    print(json.dumps({"baseline": baseline, "recommended_reversal_floor": recommended_floor, "floor_note": floor_note}, ensure_ascii=False, indent=2))
    print()
    columns = ["state", "regime_filter", "n", "fwd1_mean", "fwd1_P_up", "excess_fwd1_vs_baseline", "p_value_fwd1", "fwd3_mean", "verdict"]
    print(table[columns].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
