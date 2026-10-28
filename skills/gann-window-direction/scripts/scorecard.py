#!/usr/bin/env python3
"""Settle legacy weighted forecasts and new weight-free path forecasts separately."""

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


def matched_close_bin(close: float, close_bins: list[dict]) -> str | None:
    ordered = sorted(close_bins, key=lambda row: float(row["lower"]))
    for index, row in enumerate(ordered):
        upper_ok = close <= float(row["upper"]) if index == len(ordered) - 1 else close < float(row["upper"])
        if close >= float(row["lower"]) and upper_ok:
            return str(row["name"])
    return None


def zone_distance(value: float, zone: dict) -> float:
    lower = float(zone["lower"])
    upper = float(zone["upper"])
    return round(max(lower - value, value - upper, 0.0), 4)


def inside(value: float, zone: dict) -> bool:
    return float(zone["lower"]) <= value <= float(zone["upper"])


def settle_path(record: dict, bars: pd.DataFrame) -> dict | None:
    target = pd.Timestamp(record["target_date"])
    if target not in bars.index:
        return None
    prior = bars[bars.index < target]
    if prior.empty:
        return None
    row = bars.loc[target]
    if any(column not in row or pd.isna(row[column]) for column in ("open", "high", "low", "close")):
        return None
    path = record.get("next_day_path") or {}
    opening = path.get("opening") or {}
    intraday = path.get("intraday") or {}
    close_zone = path.get("close") or {}
    if not opening or not intraday or not close_zone:
        return None
    open_price = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])
    close = float(row["close"])
    prior_close = float(prior["close"].iloc[-1])
    close_bins = record.get("close_bins") or []
    realized_branch = matched_close_bin(close, close_bins)
    band = (record.get("level_context") or {}).get("decision_band") or {}
    support = float(band["support_defense"])
    pressure = float(band["pressure_defense"])
    if close < support:
        realized_location = "below_support"
    elif close > pressure:
        realized_location = "above_pressure"
    else:
        position = (close - support) / (pressure - support)
        realized_location = "lower_edge" if position <= 0.25 else "upper_edge" if position >= 0.75 else "center"
    if realized_location in ("below_support", "lower_edge"):
        realized_character = "weak"
    elif realized_location in ("above_pressure", "upper_edge"):
        realized_character = "strong"
    else:
        realized_character = "balanced"
    range_quality = str(band.get("range_quality") or "unknown")
    fragile_range_coverage = bool(
        realized_branch == "range_oscillation"
        and range_quality in ("wide", "extreme_wide")
        and realized_location in ("lower_edge", "upper_edge")
    )
    return {
        "schema": "path_v1",
        "prediction_type": record.get("prediction_type", "prospective"),
        "ruleset_version": record.get("ruleset_version"),
        "target_date": record["target_date"],
        "prior_close": prior_close,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "pct_chg": round((close / prior_close - 1) * 100, 4),
        "open_zone_hit": inside(open_price, opening),
        "open_zone_distance": zone_distance(open_price, opening),
        "intraday_range_covered": low >= float(intraday["lower"]) and high <= float(intraday["upper"]),
        "intraday_overshoot": round(
            max(float(intraday["lower"]) - low, high - float(intraday["upper"]), 0.0),
            4,
        ),
        "close_zone_hit": inside(close, close_zone),
        "close_zone_distance": zone_distance(close, close_zone),
        "realized_branch": realized_branch or "in_gap",
        "expected_close_location": close_zone.get("location"),
        "realized_close_location": realized_location,
        "close_location_hit": realized_location == close_zone.get("location"),
        "expected_close_character": close_zone.get("character"),
        "realized_close_character": realized_character,
        "close_character_hit": realized_character == close_zone.get("character"),
        "range_quality": range_quality,
        "fragile_range_coverage": fragile_range_coverage,
        "path_order_status": "unavailable_from_daily_ohlc",
    }


def settle_legacy(record: dict, closes: pd.Series) -> dict | None:
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
    expected = by_direction.get(record.get("direction"))
    direction_hit = realized_direction == expected if expected in ("up", "down") else None
    scenarios = record.get("scenarios", [])
    matched = None
    ordered = sorted(scenarios, key=lambda row: float(row.get("lower", float("-inf"))))
    for index, scenario in enumerate(ordered):
        lower = scenario.get("lower")
        upper = scenario.get("upper")
        if lower is None or upper is None:
            continue
        upper_ok = close <= upper if index == len(ordered) - 1 else close < upper
        if close >= lower and upper_ok:
            matched = scenario["name"]
            break
    top_weight = max(scenarios, key=lambda row: row.get("weight", 0))["name"] if scenarios else None
    return {
        "schema": "legacy_weighted",
        "prediction_type": record.get("prediction_type", "prospective"),
        "ruleset_version": record.get("ruleset_version"),
        "target_date": record["target_date"],
        "prior_close": prior_close,
        "close": close,
        "pct_chg": round((close / prior_close - 1) * 100, 4),
        "realized_direction": realized_direction,
        "expected_direction": expected,
        "direction_hit": direction_hit,
        "realized_branch": matched if matched else "in_gap",
        "top_weight_branch": top_weight,
        "top_weight_hit": None if matched is None else matched == top_weight,
        "branch_weights": {row["name"]: float(row.get("weight", 0)) for row in scenarios},
        "targets_declared": [row.get("name") for row in record.get("targets", [])],
    }


def settle(record: dict, bars_or_closes: pd.DataFrame | pd.Series) -> dict | None:
    if "next_day_path" in record:
        if not isinstance(bars_or_closes, pd.DataFrame):
            return None
        return settle_path(record, bars_or_closes)
    closes = bars_or_closes["close"] if isinstance(bars_or_closes, pd.DataFrame) else bars_or_closes
    return settle_legacy(record, closes)


def ratio(rows: list[dict], field: str) -> float | None:
    return None if not rows else round(sum(bool(row.get(field)) for row in rows) / len(rows), 3)


def main() -> int:
    parser = argparse.ArgumentParser(description="分别结算旧版方向记录与新版路径记录")
    parser.add_argument("--log", required=True)
    parser.add_argument("--index-daily", required=True)
    parser.add_argument("--append")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    log_path = Path(args.log)
    if args.append:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(json.loads(Path(args.append).read_text(encoding="utf-8")), ensure_ascii=False) + "\n")
    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    bars = load_index_frame(args.index_daily)
    settled = []
    for record in records:
        row = settle(record, bars)
        if not row:
            continue
        settled.append(row)
    pending = [row["target_date"] for row in records if pd.Timestamp(row["target_date"]) not in bars.index]
    prospective = [row for row in settled if row.get("prediction_type", "prospective") == "prospective"]
    backfill = [row for row in records if row.get("prediction_type", "prospective") == "backfill"]
    path_rows = [row for row in prospective if row.get("schema") == "path_v1"]
    legacy_rows = [row for row in prospective if row.get("schema") == "legacy_weighted"]
    summary = {
        "settled_count": len(prospective),
        "backfill_count": len(backfill),
        "backfill_dates": [row["target_date"] for row in backfill],
        "excluded_from_scoring": "prediction_type=backfill",
        "pending_dates": pending,
        "path_count": len(path_rows),
        "legacy_count": len(legacy_rows),
    }
    if path_rows:
        summary["path"] = {
            "open_zone_hit_rate": ratio(path_rows, "open_zone_hit"),
            "intraday_range_coverage": ratio(path_rows, "intraday_range_covered"),
            "close_zone_hit_rate": ratio(path_rows, "close_zone_hit"),
            "close_location_hit_rate": ratio(path_rows, "close_location_hit"),
            "close_character_hit_rate": ratio(path_rows, "close_character_hit"),
            "fragile_range_coverage_count": sum(bool(row["fragile_range_coverage"]) for row in path_rows),
            "path_order_status": "daily OHLC 不推断盘中节点先后",
        }
    if legacy_rows:
        direction_rows = [row for row in legacy_rows if row["direction_hit"] is not None]
        branch_rows = [row for row in legacy_rows if row["top_weight_hit"] is not None]
        summary["legacy"] = {
            "direction_accuracy": ratio(direction_rows, "direction_hit"),
            "top_weight_branch_hit_rate": ratio(branch_rows, "top_weight_hit"),
            "note": "仅用于旧版冻结记录，不与新版路径指标混算",
        }
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "scorecard.json").write_text(
        json.dumps({"summary": summary, "settled": settled}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
