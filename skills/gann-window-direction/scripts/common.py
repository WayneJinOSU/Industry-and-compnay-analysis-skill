#!/usr/bin/env python3
"""Shared contracts and point-in-time helpers for gann-window-direction."""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

RULESET_VERSION = "2026-10-25.12"
TZ = ZoneInfo("Asia/Shanghai")

LAYERS = ("external", "volume", "margin", "breadth", "leadership", "path", "event")
INFO_VALUES = ("informative", "weak", "uninformative")
SCENARIO_NAMES = (
    "downside_continuation",
    "range_oscillation",
    "upside_breakout",
    "tail_extreme_down",
)
# Canonical Chinese labels for human-facing reports. The English identifiers above
# remain the machine contract and must not be renamed in JSON/CSV artifacts.
SCENARIO_REPORT_LABELS = {
    "downside_continuation": ("向下延续", "向下破位"),
    "range_oscillation": ("区间震荡",),
    "upside_breakout": ("向上突破",),
    "tail_extreme_down": ("尾部极值（向下）", "尾部极值"),
}
# Human-facing report labels. Canonical English field names and enum values remain
# the machine contract in JSON/CSV, but reports present this Chinese display layer.
REPORT_FIELD_LABELS_ZH = {
    "prediction_type": ("预测类型",),
    "ruleset_version": ("规则版本",),
    "decision_stage": ("决策阶段",),
    "forecast_cutoff": ("预判截点", "判断截点"),
    "feature_cutoff": ("特征截点", "数据截点"),
    "target_date": ("目标日期",),
    "gate_status": ("门禁状态",),
    "structural_bias": ("结构偏向", "结构状态"),
    "window_state": ("窗口状态", "江恩窗口状态"),
    "direction": ("事件日方向", "收盘方向"),
    "execution_state": ("执行状态",),
    "action_bias": ("操作偏向", "操作建议"),
    "abstain": ("是否弃权", "弃权"),
    "confidence": ("置信度",),
    "decision_level": ("决策区间",),
    "invalidation": ("失效条件",),
    "next_confirmation": ("下一确认", "下次确认"),
    "decision_mode": ("决策模式",),
    "setup_state": ("盘前设定状态", "环境状态"),
    "setup_score": ("盘前检查得分", "检查得分"),
    "gap_state": ("缺口状态",),
    "pressure_state": ("压力状态",),
    "participation_state": ("参与度状态",),
    "risk_state": ("风险状态",),
    "execution_bias": ("执行偏向", "执行建议"),
}
REPORT_VALUE_LABELS_ZH = {
    "prediction_type": {
        "prospective": ("前瞻预测", "事前预测"),
        "backfill": ("历史回放", "事后补做"),
    },
    "decision_stage": {
        "premarket": ("盘前",),
        "preopen_0925": ("盘前九点二十五分", "九点二十五分竞价"),
        "intraday_open": ("盘中开盘",),
        "intraday_update": ("盘中更新",),
        "post_close_review": ("收盘复盘",),
    },
    "gate_status": {
        "pending": ("待定",),
        "passed": ("通过",),
        "passed_with_warnings": ("带警告通过", "有警告通过"),
        "failed": ("未通过", "失败"),
    },
    "structural_bias": {
        "bullish": ("偏多", "看多"),
        "bearish": ("偏空", "看空"),
        "neutral": ("震荡", "中性"),
    },
    "direction": {
        "bullish": ("偏多", "看多"),
        "bearish": ("偏空", "看空"),
        "neutral": ("震荡", "中性"),
    },
    "window_state": {
        "unresolved": ("未决",),
        "bullish_confirmation": ("向上确认", "偏多确认"),
        "bearish_confirmation": ("向下确认", "偏空确认"),
        "failed_bullish_window": ("向上窗口失败", "偏多窗口失败"),
        "failed_bearish_window": ("向下窗口失败", "偏空窗口失败"),
    },
    "execution_state": {
        "observe": ("观察",),
        "wait_for_confirmation": ("等待确认",),
        "confirmed": ("已确认",),
        "reduce_only": ("只减不加",),
        "abstain": ("弃权",),
    },
    "action_bias": {
        "observe": ("观察",),
        "add_only_after_confirmation": ("确认后恢复进攻", "确认后加仓"),
        "hold": ("持有",),
        "reduce_only": ("只减不加",),
        "no_new_long": ("不新开多仓",),
        "stop": ("停止操作", "停止"),
    },
    "abstain": {
        "true": ("是",),
        "false": ("否",),
    },
    "decision_mode": {
        "premarket_setup": ("盘前设定",),
        "combined": ("盘前设定与快照合并", "合并判断"),
    },
    "setup_state": {
        "risk_zone_euphoria": ("风险区亢奋",),
        "conditional_watch": ("条件观察",),
        "normal": ("正常",),
        "unknown": ("未知",),
    },
    "gap_state": {
        "expected": ("预期缺口",),
        "confirmed": ("缺口确认",),
        "faded": ("缺口回补",),
        "not_applicable": ("不适用",),
        "unknown": ("未知",),
    },
    "pressure_state": {
        "untested": ("尚未测试",),
        "accepted": ("已接受",),
        "rejected": ("已拒绝",),
        "ambiguous": ("待判定",),
        "not_applicable": ("不适用",),
        "unknown": ("未知",),
    },
    "participation_state": {
        "confirming": ("确认",),
        "divergent": ("背离",),
        "unknown": ("未知",),
    },
    "risk_state": {
        "normal": ("正常",),
        "watch": ("观察",),
        "preemptive_defensive": ("提前防守",),
        "defensive": ("防守",),
        "offensive": ("进攻",),
        "unknown": ("未知",),
    },
    "execution_bias": {
        "observe": ("观察",),
        "wait_for_confirmation": ("等待确认",),
        "reduce_only": ("只减不加",),
        "add_only_after_confirmation": ("确认后恢复进攻", "确认后加仓"),
    },
}
STAGE_PREDICTION = {
    "premarket": "prospective",
    "preopen_0925": "prospective",
    "intraday_open": "prospective",
    "intraday_update": "prospective",
    "post_close_review": "backfill",
}


def normalize_report_value(field: str, value: object) -> str | None:
    """Translate a Chinese display value to its stable machine enum.

    Existing English reports remain valid. Parenthetical explanations are
    ignored so a display cell such as “偏空（周线趋势）” still maps to bearish.
    """
    if value is None:
        return None
    text = str(value).strip().strip("`").strip()
    if not text:
        return None
    text = re.sub(r"\s*[（(][^（）()]*[）)]\s*$", "", text).strip()
    lowered = text.lower()
    field_labels = REPORT_VALUE_LABELS_ZH.get(field, {})
    if lowered in field_labels:
        return lowered
    for canonical, labels in field_labels.items():
        if text in labels:
            return canonical
    match = re.match(r"^([a-z][a-z0-9_]*)\b", lowered)
    return match.group(1) if match else text


def parse_cutoff(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace(" ", "T"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    return parsed.astimezone(TZ)


def parse_date(value: str | date | datetime | pd.Timestamp) -> pd.Timestamp:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is not None:
        parsed = parsed.tz_convert(TZ).tz_localize(None)
    return parsed.normalize()


def normalize_date_column(frame: pd.DataFrame, candidates: tuple[str, ...] = ("date", "trade_date", "time")) -> str:
    normalized = {str(column).strip().lower(): column for column in frame.columns}
    for candidate in candidates:
        source = normalized.get(candidate)
        if source is not None:
            if source != "date":
                frame = frame.rename(columns={source: "date"})
            break
    else:
        raise ValueError(f"找不到日期列，候选={candidates}")
    raw_dates = frame["date"]
    numeric_or_compact = raw_dates.astype(str).str.fullmatch(r"\d{8}").fillna(False)
    if pd.api.types.is_numeric_dtype(raw_dates):
        compact = raw_dates.round().astype("Int64").astype(str)
        frame["date"] = pd.to_datetime(compact, format="%Y%m%d", errors="coerce").dt.normalize()
    elif numeric_or_compact.all():
        frame["date"] = pd.to_datetime(raw_dates.astype(str), format="%Y%m%d", errors="coerce").dt.normalize()
    else:
        frame["date"] = pd.to_datetime(raw_dates, errors="coerce").dt.normalize()
    if frame["date"].isna().any():
        raise ValueError("日期列存在无法解析的值")
    return frame


def filter_asof(frame: pd.DataFrame, asof: str | date | datetime | pd.Timestamp) -> pd.DataFrame:
    result = normalize_date_column(frame.copy())
    end = parse_date(asof)
    result = result[result["date"] <= end]
    if result.empty:
        raise ValueError(f"数据在截点 {end.date()} 之前为空")
    return result.sort_values("date").reset_index(drop=True)


def parse_available_at(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if "（" in text:
        text = text.split("（", 1)[0].strip()
    if text.startswith("次日 "):
        return None
    try:
        parsed = datetime.fromisoformat(text.replace(" ", "T"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    return parsed.astimezone(TZ)


def max_date(frame: pd.DataFrame) -> pd.Timestamp:
    normalized = normalize_date_column(frame.copy())
    return pd.Timestamp(normalized["date"].max()).normalize()


def resolve_available_at(
    data_asof: str | date | datetime | pd.Timestamp,
    *,
    stage: str,
    explicit: str | None = None,
    forecast_cutoff: str | None = None,
) -> str:
    data_day = parse_date(data_asof)
    if explicit:
        available = parse_cutoff(explicit)
    elif stage in ("preopen_0925", "intraday_open", "intraday_update", "intraday_partial"):
        if not forecast_cutoff:
            raise ValueError("09:25/盘中派生数据必须提供 --available-at 或 forecast_cutoff")
        available = parse_cutoff(forecast_cutoff)
    else:
        available = datetime.combine(data_day.date(), datetime.min.time(), tzinfo=TZ).replace(
            hour=18
        )
    if available.date() < data_day.date():
        raise ValueError("available_at 不能早于 data_asof")
    return available.isoformat(timespec="seconds")


def weekly_regime(index_daily: pd.DataFrame) -> tuple[str, dict]:
    frame = normalize_date_column(index_daily.copy())
    weekly = (
        frame.set_index("date")
        .resample("W-FRI")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )
    if len(weekly) < 34:
        return "range", {"reason": "weekly sample shorter than 34 bars", "bars": len(weekly)}
    weekly["ema13"] = weekly["close"].ewm(span=13, adjust=False).mean()
    weekly["ema34"] = weekly["close"].ewm(span=34, adjust=False).mean()
    weekly["sma10"] = weekly["close"].rolling(10).mean()
    last = weekly.iloc[-1]
    below = [bool(last["close"] < last[c]) for c in ("ema13", "ema34", "sma10")]
    above = [bool(last["close"] > last[c]) for c in ("ema13", "ema34", "sma10")]
    if all(below) and last["ema13"] < last["ema34"]:
        regime = "down"
    elif all(above) and last["ema13"] > last["ema34"]:
        regime = "up"
    else:
        regime = "range"
    return regime, {
        "week_end": str(frame["date"].max().date()),
        "weekly_period_end": str(last.name.date()),
        "close": round(float(last["close"]), 2),
        "ema13": round(float(last["ema13"]), 2),
        "ema34": round(float(last["ema34"]), 2),
        "sma10": round(float(last["sma10"]), 2),
    }


def breadth_state(market: pd.DataFrame) -> tuple[str, dict, bool, bool]:
    frame = normalize_date_column(market.copy()).sort_values("date").reset_index(drop=True)
    ratio = pd.to_numeric(frame["advance_ratio"], errors="coerce")
    if ratio.tail(10).isna().any():
        raise ValueError("advance_ratio 最近 10 行不完整")
    latest = float(ratio.iloc[-1])
    mean20 = float(ratio.tail(20).mean())
    sigma20 = float(ratio.tail(20).std())
    z = (latest - mean20) / sigma20 if sigma20 > 0 else 0.0
    recent5 = float(ratio.tail(5).mean())
    prior5 = float(ratio.iloc[-10:-5].mean())
    if recent5 - prior5 >= 0.08:
        state = "improving"
    elif recent5 - prior5 <= -0.08:
        state = "deteriorating"
    else:
        state = "neutral"
    extreme_low = bool(latest <= 0.15 or z <= -2.0)
    extreme_high = bool(latest >= 0.85 or z >= 2.0)
    return state, {
        "data_asof": str(frame["date"].iloc[-1].date()),
        "advance_ratio": round(latest, 4),
        "advance_ratio_mean20": round(mean20, 4),
        "advance_ratio_z": round(z, 3),
        "recent5_mean": round(recent5, 4),
        "prior5_mean": round(prior5, 4),
    }, extreme_low, extreme_high


def validate_scenarios(scenarios: list[dict], interval_convention: str = "lower_inclusive_upper_exclusive") -> list[str]:
    errors: list[str] = []
    names = [row.get("name") for row in scenarios]
    if sorted(names) != sorted(SCENARIO_NAMES):
        errors.append(f"scenario names must be {list(SCENARIO_NAMES)}, got {names}")
    if any(not row.get("direction") for row in scenarios):
        errors.append("every scenario must declare direction explicitly")
    if any(float(row.get("weight", 0)) < 0 for row in scenarios):
        errors.append("scenario weights cannot be negative")
    expected_directions = {
        "downside_continuation": "bearish",
        "range_oscillation": "neutral",
        "upside_breakout": "bullish",
        "tail_extreme_down": "bearish",
    }
    for row in scenarios:
        expected = expected_directions.get(row.get("name"))
        if expected and row.get("direction") != expected:
            errors.append(f"{row.get('name')} direction must be {expected}")
    try:
        ordered = sorted(
            [(row.get("name"), float(row["lower"]), float(row["upper"])) for row in scenarios],
            key=lambda item: item[1],
        )
    except (KeyError, TypeError, ValueError):
        return errors + ["scenario lower/upper must be numeric"]
    if interval_convention != "lower_inclusive_upper_exclusive":
        errors.append("only lower_inclusive_upper_exclusive is supported")
    for left, right in zip(ordered, ordered[1:]):
        if not np.isclose(left[2], right[1]):
            errors.append(f"scenario boundary mismatch or overlap: {left[0]} upper={left[2]} vs {right[0]} lower={right[1]}")
    if ordered and ordered[0][1] > -1e300:
        # A finite lower bound is required for machine scoring; use 0 rather than -inf.
        if ordered[0][1] > 0:
            errors.append("first scenario must start at or below zero")
    if abs(sum(float(row.get("weight", 0)) for row in scenarios) - 1.0) > 1e-9:
        errors.append("scenario weights must sum to 1.0 exactly")
    return errors


def atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(temporary, path)

