#!/usr/bin/env python3
"""记分账本：累积检验方向与收盘分箱。

为什么必须存在：
输出契约要求“统计实际结果落在最高权重分支的比例，并单独报告区间覆盖与弃权”，
但旧流程没有载体累积这些数字。结果是同一类权重
偏差连续多日重复出现而无人察觉 —— 方向判断可以连着对，情景权重却可以连着错。

记录格式（jsonl，每行一条预判）：
{"target_date","generated_at","prediction_type","ruleset_version","structural_bias",
 "window_state","direction","execution_state",
 "scenarios":[{"name","direction","weight","lower","upper"}],
 "targets":[{"name","level","direction"}]}

`prediction_type`：`prospective`（当时事前生成）或 `backfill`（事后补做）。
补做记录会一并结算，但**不计入**方向正确率与最高权重分支命中率——补做时结果已可见，
混入统计会系统性高估方法表现。

用法：
python3 scripts/scorecard.py --log forecasts.jsonl --index-daily <csv> \
    [--append <record.json>] --output <dir>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def load_index_frame(path: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    column = "date" if "date" in frame.columns else "trade_date"
    frame[column] = pd.to_datetime(frame[column], errors="coerce").fillna(
        pd.to_datetime(frame[column], format="%Y%m%d", errors="coerce")
    )
    return frame.sort_values(column).set_index(column)


def load_index(path: str) -> pd.Series:
    return load_index_frame(path)["close"]


def score_execution(record: dict, bars: pd.DataFrame) -> dict | None:
    """Score a defensive/additive execution bias from the target open onward."""
    overlay = record.get("execution_overlay")
    if not isinstance(overlay, dict):
        return None
    target = pd.Timestamp(record["target_date"])
    if target not in bars.index:
        return None
    row = bars.loc[target]
    required = ("open", "high", "low", "close")
    if any(column not in row or pd.isna(row[column]) for column in required):
        return None
    open_price = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])
    close = float(row["close"])
    if open_price <= 0:
        return None
    no_action_return = close / open_price - 1
    bias = overlay.get("execution_bias")
    if bias == "reduce_only":
        action_return = 0.0
        avoided_close_drawdown = max(0.0, -no_action_return)
        missed_upside = max(0.0, no_action_return)
        avoided_intraday_drawdown = max(0.0, -(low / open_price - 1))
    elif bias == "add_only_after_confirmation":
        action_return = no_action_return
        avoided_close_drawdown = 0.0
        missed_upside = 0.0
        avoided_intraday_drawdown = 0.0
    else:
        return None
    return {
        "risk_state": overlay.get("risk_state"),
        "execution_bias": bias,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "no_action_open_to_close_return": round(no_action_return, 6),
        "execution_open_to_close_return": round(action_return, 6),
        "avoided_close_drawdown": round(avoided_close_drawdown, 6),
        "avoided_intraday_drawdown_from_open": round(avoided_intraday_drawdown, 6),
        "missed_upside": round(missed_upside, 6),
        "defensive_false_positive": bool(
            bias == "reduce_only" and no_action_return >= 0 and low >= open_price
        ),
    }


def settle(record: dict, closes: pd.Series) -> dict | None:
    target = pd.Timestamp(record["target_date"])
    if target not in closes.index:
        return None
    prior = closes[closes.index < target]
    if prior.empty:
        return None
    prior_close = float(prior.iloc[-1])
    close = float(closes.loc[target])
    realized_direction = "up" if close > prior_close else "down" if close < prior_close else "flat"
    by_direction = {"bullish": "up", "bearish": "down", "neutral": "neutral"}
    expected = by_direction.get(record.get("direction"), None)
    direction_hit = realized_direction == expected if expected in ("up", "down") else None

    scenarios = record.get("scenarios", [])
    matched = None
    ordered_scenarios = sorted(
        scenarios,
        key=lambda row: float(row.get("lower", float("-inf"))),
    )
    for index, scenario in enumerate(ordered_scenarios):
        lower = scenario.get("lower")
        upper = scenario.get("upper")
        if lower is None or upper is None:
            continue
        lower_ok = close >= lower
        upper_ok = close <= upper if index == len(ordered_scenarios) - 1 else close < upper
        if lower_ok and upper_ok:
            matched = scenario["name"]
            break
    top_weight = max(scenarios, key=lambda s: s.get("weight", 0))["name"] if scenarios else None
    weights = {s["name"]: float(s.get("weight", 0)) for s in scenarios}

    return {
        "prediction_type": record.get("prediction_type", "prospective"),
        "ruleset_version": record.get("ruleset_version"),
        "target_date": record["target_date"],
        "prior_close": prior_close,
        "close": close,
        "pct_chg": round((close / prior_close - 1) * 100, 4),
        "realized_direction": realized_direction,
        "expected_direction": expected,
        "direction_hit": direction_hit,
        "realized_branch": matched if matched else "in_gap（落在分支之间）",
        "top_weight_branch": top_weight,
        "top_weight_hit": None if matched is None else matched == top_weight,
        "branch_weights": weights,
        "targets_declared": [t.get("name") for t in record.get("targets", [])],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Forecast scorecard with cumulative weight test")
    parser.add_argument("--log", required=True, help="forecasts.jsonl")
    parser.add_argument("--index-daily", required=True)
    parser.add_argument("--append", help="追加一条预判记录（json 文件）后再结算")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    log_path = Path(args.log)
    if args.append:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(json.loads(Path(args.append).read_text(encoding="utf-8")), ensure_ascii=False) + "\n")

    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    bars = load_index_frame(args.index_daily)
    closes = bars["close"]
    settled = []
    for record in records:
        row = settle(record, closes)
        if not row:
            continue
        execution = score_execution(record, bars)
        if execution is not None:
            row["execution_score"] = execution
        settled.append(row)
    pending = [r["target_date"] for r in records if pd.Timestamp(r["target_date"]) not in closes.index]

    prospective = [r for r in settled if r.get("prediction_type", "prospective") == "prospective"]
    backfill_all = [r for r in records if r.get("prediction_type", "prospective") == "backfill"]

    if prospective:
        direction_rows = [r for r in prospective if r["direction_hit"] is not None]
        branch_rows = [r for r in prospective if r["top_weight_hit"] is not None]
        neutral_rows = [r for r in prospective if r.get("expected_direction") == "neutral"]
        summary = {
            "settled_count": len(prospective),
            "backfill_count": len(backfill_all),
            "backfill_dates": [r["target_date"] for r in backfill_all],
            "excluded_from_scoring": "prediction_type=backfill",
            "pending_dates": pending,
            "direction_accuracy": None
            if not direction_rows
            else round(sum(bool(r["direction_hit"]) for r in direction_rows) / len(direction_rows), 3),
            "top_weight_branch_hit_rate": None
            if not branch_rows
            else round(sum(bool(r["top_weight_hit"]) for r in branch_rows) / len(branch_rows), 3),
            "in_gap_rate": round(sum(1 for r in prospective if r["realized_branch"].startswith("in_gap")) / len(prospective), 3),
            "neutral_count": len(neutral_rows),
            "abstention_rate": round(len(neutral_rows) / len(prospective), 3),
            "rule": "权重是内部排序分数，不是概率；neutral 不计入方向命中但单独报告弃权率；in_gap > 0 必须重估区间。",
        }
        execution_rows = [
            row["execution_score"]
            for row in prospective
            if isinstance(row.get("execution_score"), dict)
            and row["execution_score"].get("execution_bias") in ("reduce_only", "add_only_after_confirmation")
        ]
        if execution_rows:
            summary["execution"] = {
                "scored_count": len(execution_rows),
                "reduce_only_count": sum(
                    row["execution_bias"] == "reduce_only" for row in execution_rows
                ),
                "avg_avoided_close_drawdown": round(
                    sum(row["avoided_close_drawdown"] for row in execution_rows)
                    / len(execution_rows),
                    6,
                ),
                "avg_avoided_intraday_drawdown_from_open": round(
                    sum(row["avoided_intraday_drawdown_from_open"] for row in execution_rows)
                    / len(execution_rows),
                    6,
                ),
                "avg_missed_upside": round(
                    sum(row["missed_upside"] for row in execution_rows)
                    / len(execution_rows),
                    6,
                ),
                "defensive_false_positive_count": sum(
                    bool(row["defensive_false_positive"]) for row in execution_rows
                ),
                "no_action_baseline": "close/open-1 from the target open",
                "rule": "防守动作按目标日开盘执行；分别记录避开的跌幅、错过的涨幅和误报，不以单一方向命中代替执行评价。",
            }
    else:
        summary = {"settled_count": 0, "backfill_count": len(backfill_all),
                   "backfill_dates": [r["target_date"] for r in backfill_all],
                   "pending_dates": pending}

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "scorecard.json").write_text(
        json.dumps({"summary": summary, "settled": settled}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\n逐条：")
    for row in settled:
        print(
            f"  {row['target_date']} 收 {row['close']:.2f}（{row['pct_chg']:+.2f}%） 方向 "
            f"{'✅' if row['direction_hit'] else '❌' if row['direction_hit'] is not None else '—'} | "
            f"实际分支 {row['realized_branch']} | 最高权重分支 {row['top_weight_branch']} "
            f"{'✅' if row['top_weight_hit'] else '❌' if row['top_weight_hit'] is not None else '—'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
