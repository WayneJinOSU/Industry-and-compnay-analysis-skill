#!/usr/bin/env python3
"""Build point-in-time support/pressure break-and-reclaim memory."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from common import RULESET_VERSION, atomic_write_json, parse_date


SUPPORT_ROLES = ("support", "support_defense", "downside_confirmation", "支撑")
PRESSURE_ROLES = ("pressure", "pressure_defense", "upside_confirmation", "压力")
SUPPORT_ANCHOR_ROLES = ("support_band_anchor", "support_anchor", "support_high")
SUPPORT_DEFENSE_ROLES = ("support_defense", "downside_confirmation", "support", "支撑")
PRESSURE_ANCHOR_ROLES = ("pressure_band_anchor", "pressure_anchor", "pressure_low")
PRESSURE_DEFENSE_ROLES = ("pressure_defense", "upside_confirmation", "pressure", "压力")


def role_matches(role: str, family: tuple[str, ...]) -> bool:
    return any(token in role for token in family)


def atr14(frame: pd.DataFrame) -> float | None:
    previous_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    value = true_range.tail(14).mean()
    return None if pd.isna(value) else float(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="关键位记忆与破位收复状态")
    parser.add_argument("--index-daily", required=True)
    parser.add_argument("--previous-levels", required=True)
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--asof", required=True)
    parser.add_argument("--available-at", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--pack", help="可选输入包；提供后将关键位记忆写回副本")
    parser.add_argument("--pack-output", help="写回后的输入包路径")
    args = parser.parse_args()

    target_day = parse_date(args.target_date)
    asof_day = parse_date(args.asof)
    if asof_day >= target_day:
        raise SystemExit("关键位记忆的 asof 必须严格早于 target-date")

    frame = pd.read_csv(args.index_daily, parse_dates=["date"])
    frame = frame[frame["date"] <= asof_day].sort_values("date").reset_index(drop=True)
    if frame.empty:
        raise SystemExit("关键位记忆的指数日线为空")
    levels = pd.read_csv(args.previous_levels)
    required = {"level", "role"}
    missing = required.difference(levels.columns)
    if missing:
        raise SystemExit(f"上一份价位表缺少列：{sorted(missing)}")

    close = float(frame["close"].iloc[-1])
    session_range = float(frame["high"].iloc[-1] - frame["low"].iloc[-1])
    close_position = (
        (close - float(frame["low"].iloc[-1])) / session_range
        if session_range > 0
        else None
    )
    atr = atr14(frame)
    gaps: list[dict] = []
    support_rows = []
    pressure_rows = []
    support_bands: dict[str, dict] = {}
    pressure_bands: dict[str, dict] = {}

    for _, row in levels.iterrows():
        role = str(row.get("role", "")).strip().lower()
        try:
            level = float(row["level"])
        except (TypeError, ValueError):
            continue
        if level <= 0:
            continue
        source_value = next(
            (
                row.get(column)
                for column in ("source_report", "source_report_date", "report_date")
                if column in row and pd.notna(row.get(column))
            ),
            None,
        )
        source_day = None
        if source_value is not None:
            match = re.search(r"(20\d{2})-?(\d{2})-?(\d{2})", str(source_value))
            if match:
                source_day = parse_date("-".join(match.groups()))
        if source_day is None:
            gaps.append(
                {
                    "field": f"structure_memory.level.{level:.2f}",
                    "status": "missing",
                    "fallback_attempted": False,
                    "reason": "价位缺少可解析的来源报告日期",
                }
            )
            continue
        if source_day >= target_day:
            gaps.append(
                {
                    "field": f"structure_memory.level.{level:.2f}",
                    "status": "future",
                    "fallback_attempted": False,
                    "reason": "价位来源日不早于目标日",
                }
            )
            continue
        history = frame[frame["date"] >= source_day].copy()
        if history.empty:
            continue

        if role_matches(role, SUPPORT_ROLES):
            band_key = str(row.get("band_id") or f"support_{level:.2f}")
            band = support_bands.setdefault(
                band_key,
                {
                    "band_id": band_key,
                    "anchor_level": None,
                    "defense_level": None,
                    "source_date": source_day.strftime("%Y-%m-%d"),
                },
            )
            if role_matches(role, SUPPORT_ANCHOR_ROLES):
                band["anchor_level"] = level
            elif role_matches(role, SUPPORT_DEFENSE_ROLES):
                band["defense_level"] = level
            else:
                band["anchor_level"] = band["anchor_level"] or level
                band["defense_level"] = band["defense_level"] or level
            broken = history[history["close"] < level]
            broken_date = (
                broken["date"].iloc[0].strftime("%Y-%m-%d") if not broken.empty else None
            )
            status = (
                "broken_unreclaimed"
                if close < level
                else "reclaimed"
                if broken_date
                else "not_broken"
            )
            support_rows.append(
                {
                    "level": level,
                    "source_date": source_day.strftime("%Y-%m-%d"),
                    "broken_date": broken_date,
                    "status": status,
                    "sessions_since_break": (
                        int((history["date"] > pd.Timestamp(broken_date)).sum())
                        if broken_date
                        else None
                    ),
                    "band_id": band_key,
                }
            )
        elif role_matches(role, PRESSURE_ROLES):
            band_key = str(row.get("band_id") or f"pressure_{level:.2f}")
            band = pressure_bands.setdefault(
                band_key,
                {
                    "band_id": band_key,
                    "anchor_level": None,
                    "defense_level": None,
                    "source_date": source_day.strftime("%Y-%m-%d"),
                },
            )
            if role_matches(role, PRESSURE_ANCHOR_ROLES):
                band["anchor_level"] = level
            elif role_matches(role, PRESSURE_DEFENSE_ROLES):
                band["defense_level"] = level
            else:
                band["anchor_level"] = band["anchor_level"] or level
                band["defense_level"] = band["defense_level"] or level
            accepted = history[history["close"] > level]
            accepted_date = (
                accepted["date"].iloc[0].strftime("%Y-%m-%d")
                if not accepted.empty
                else None
            )
            pressure_rows.append(
                {
                    "level": level,
                    "source_date": source_day.strftime("%Y-%m-%d"),
                    "accepted_date": accepted_date,
                    "status": (
                        "accepted"
                        if close > level
                        else "rejected_or_below"
                    ),
                    "band_id": band_key,
                }
            )

    if not support_rows:
        gaps.append(
            {
                "field": "structure_memory.support",
                "status": "missing",
                "fallback_attempted": False,
                "reason": "上一份价位表没有可识别的支撑防线",
            }
        )
    if not pressure_rows:
        gaps.append(
            {
                "field": "structure_memory.pressure",
                "status": "missing",
                "fallback_attempted": False,
                "reason": "上一份价位表没有可识别的压力防线",
            }
        )

    below = [row for row in support_rows if row["level"] <= close]
    above = [row for row in pressure_rows if row["level"] >= close]
    nearest_support = max(below, key=lambda row: row["level"], default=None)
    nearest_pressure = min(above, key=lambda row: row["level"], default=None)
    support_defense_candidates = [
        band["defense_level"]
        for band in support_bands.values()
        if band.get("defense_level") is not None
    ]
    pressure_defense_candidates = [
        band["defense_level"]
        for band in pressure_bands.values()
        if band.get("defense_level") is not None
    ]
    support_defenses_below = [
        level for level in support_defense_candidates if float(level) <= close
    ]
    pressure_defenses_above = [
        level for level in pressure_defense_candidates if float(level) >= close
    ]
    decision_band = {
        "support_defense": (
            max(support_defenses_below)
            if support_defenses_below
            else min(support_defense_candidates, default=None)
        ),
        "pressure_defense": (
            min(pressure_defenses_above)
            if pressure_defenses_above
            else max(pressure_defense_candidates, default=None)
        ),
    }
    decision_band["width_atr"] = (
        round(
            (
                float(decision_band["pressure_defense"])
                - float(decision_band["support_defense"])
            )
            / atr,
            4,
        )
        if atr
        and decision_band["support_defense"] is not None
        and decision_band["pressure_defense"] is not None
        else None
    )
    support_distance_atr = (
        (close - nearest_support["level"]) / atr
        if nearest_support and atr
        else None
    )
    ma5 = float(frame["close"].tail(5).mean()) if len(frame) >= 5 else None
    broken_unreclaimed = [
        row for row in support_rows if row["status"] == "broken_unreclaimed"
    ]
    reclaimed = [row for row in support_rows if row["status"] == "reclaimed"]

    if broken_unreclaimed:
        path_status = "met"
        path_subtype = "break_unreclaimed"
        path_detail = (
            f"上一份支撑防线{broken_unreclaimed[-1]['level']:.2f}已跌破且尚未收复"
        )
    elif (
        close_position is not None
        and close_position <= 0.25
        and (
            (support_distance_atr is not None and support_distance_atr <= 0.6)
            or (ma5 is not None and close < ma5)
        )
    ):
        path_status = "met"
        path_subtype = "weak_close_near_support"
        path_detail = "收盘位于日振幅低位，且接近支撑防线或低于5日均线"
    else:
        path_status = "not_met"
        path_subtype = "none"
        path_detail = "没有形成破位未收复或支撑附近弱收盘状态"

    attempt_bands = []
    lookback = frame.tail(10).copy()
    amount_median = float(lookback["amount"].median()) if "amount" in lookback else None
    for band_id, band in pressure_bands.items():
        anchor = band.get("anchor_level")
        defense = band.get("defense_level")
        if anchor is None or defense is None:
            continue
        tested = lookback[lookback["high"] >= float(anchor)].copy()
        failed = tested[tested["close"] < float(defense)].copy()
        accepted = tested[tested["close"] >= float(defense)].copy()
        consecutive_failed = 0
        for _, row in tested.sort_values("date", ascending=False).iterrows():
            if float(row["close"]) < float(defense):
                consecutive_failed += 1
            else:
                break
        last_test = tested.sort_values("date").iloc[-1] if len(tested) else None
        last_test_status = None
        if last_test is not None:
            last_test_status = "failed" if float(last_test["close"]) < float(defense) else "accepted"
        attempt_bands.append(
            {
                "band_id": band_id,
                "anchor_level": round(float(anchor), 2),
                "defense_level": round(float(defense), 2),
                "lookback_sessions": int(len(lookback)),
                "test_count": int(len(tested)),
                "failed_close_count": int(len(failed)),
                "accepted_close_count": int(len(accepted)),
                "consecutive_failed_tests": int(consecutive_failed),
                "last_test_date": (
                    last_test["date"].strftime("%Y-%m-%d") if last_test is not None else None
                ),
                "last_test_status": last_test_status,
                "sessions_since_last_test": (
                    int((lookback["date"] > last_test["date"]).sum())
                    if last_test is not None
                    else None
                ),
                "failure_highs_descending": (
                    bool(len(failed) >= 2 and failed["high"].iloc[-2] > failed["high"].iloc[-1])
                    if len(failed) >= 2
                    else None
                ),
                "test_amount_ratio_10d": (
                    round(float(failed["amount"].median()) / amount_median, 4)
                    if amount_median and len(failed) and "amount" in failed
                    else None
                ),
                "status": (
                    "repeated_failure"
                    if len(failed) >= 2 and len(accepted) == 0
                    else "mixed"
                    if len(failed) and len(accepted)
                    else "single_failure"
                    if len(failed)
                    else "accepted"
                    if len(accepted)
                    else "no_test"
                ),
            }
        )
    nearest_attempt = (
        min(attempt_bands, key=lambda row: abs(float(row["anchor_level"]) - close))
        if attempt_bands
        else None
    )

    payload = {
        "ruleset_version": RULESET_VERSION,
        "target_date": args.target_date,
        "data_asof": args.asof,
        "available_at": args.available_at,
        "source": "上一份价位表与目标日前已完成日线",
        "data_quality": "complete" if not gaps else "partial",
        "close": close,
        "atr14": atr,
        "close_position": close_position,
        "ma5": ma5,
        "nearest_support": nearest_support,
        "nearest_pressure": nearest_pressure,
        "support_bands": sorted(
            support_bands.values(), key=lambda row: row["anchor_level"] or 0, reverse=True
        ),
        "decision_band": decision_band,
        "support_distance_atr": support_distance_atr,
        "supports": sorted(support_rows, key=lambda row: row["level"], reverse=True),
        "pressures": sorted(pressure_rows, key=lambda row: row["level"]),
        "pressure_attempt_memory": {
            "lookback_sessions": int(len(lookback)),
            "bands": sorted(attempt_bands, key=lambda row: row["anchor_level"]),
            "nearest": nearest_attempt,
        },
        "broken_unreclaimed_count": len(broken_unreclaimed),
        "reclaimed_count": len(reclaimed),
        "recent_path_pressure": {
            "status": path_status,
            "subtype": path_subtype,
            "detail": path_detail,
        },
        "data_gaps": gaps,
    }
    atomic_write_json(Path(args.output), payload)
    if bool(args.pack) != bool(args.pack_output):
        raise SystemExit("--pack 与 --pack-output 必须同时提供")
    if args.pack:
        pack_path = Path(args.pack)
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        if str(pack.get("target_date")) != args.target_date:
            raise SystemExit("输入包 target_date 与关键位记忆不一致")
        pack["ruleset_version"] = RULESET_VERSION
        pack["structure_memory"] = payload
        existing = list(pack.get("data_gap_register") or [])
        known = {(row.get("field"), row.get("status")) for row in existing}
        for gap in gaps:
            key = (gap.get("field"), gap.get("status"))
            if key not in known:
                existing.append(gap)
                known.add(key)
        pack["data_gap_register"] = existing
        atomic_write_json(Path(args.pack_output), pack)
    print(
        json.dumps(
            {
                "close": close,
                "path_pressure": payload["recent_path_pressure"],
                "broken_unreclaimed_count": len(broken_unreclaimed),
                "reclaimed_count": len(reclaimed),
                "data_gaps": len(gaps),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
