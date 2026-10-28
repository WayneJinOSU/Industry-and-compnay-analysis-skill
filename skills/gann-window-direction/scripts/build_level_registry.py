#!/usr/bin/env python3
"""关键位登记表：多镜头候选生成 + 交汇计数 + 行为评分 + 三项强制检查。

为什么必须存在这个脚本：
上游江恩输出的 `current_levels.csv` 只包含由分位/角度线/圆周位/历史记忆四类**几何**来源
生成的共振区间。未获 ZigZag 确认的近期日线极值不会进入该表，于是下游若直接把它当作
"完整档位表"，就会系统性漏掉最近一两周形成的、次日交易最相关的价位
（实例：2026-10-09 低点 3754.14 被漏，直到 2026-10-13 由使用者指出）。

本脚本把"重要位置"重新定义为两条独立标准的合并：
  1) 跨镜头交汇数——每类镜头独立产出候选，互不替代；
  2) 市场行为——触碰次数、守住率、触碰后反应、触碰日量能。
江恩只是 11 类镜头之一。

三项强制检查（任一不通过，报告不得直接输出最近支撑/压力结论）：
  A. 孤立位扫描：1.5 ATR 内是否存在只有 price_structure 单一镜头的近期极值；
  B. 上游交叉核对：current_levels.csv 的区间边界是否与 clusters.csv 的成员边界一致；
  C. 交接检查：上一份报告出现过的价位是否都进入了本次登记表（--previous-levels）。

数据源顺序遵循 SKILL.md：KH 本地 DuckDB 优先，其次 Tushare 导出的日线 CSV；
本脚本不做联网取数，缺数据必须显式报错或标注缺口。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from common import (
    RULESET_VERSION,
    atomic_write_json,
    filter_asof,
    parse_date,
    resolve_available_at,
    wilder_atr_14,
)

TOUCH_TOL = 0.003
CLUSTER_TOL = 0.0025
DEFAULT_HISTORY = 250

LENSES = (
    "pivot",
    "price_structure",
    "geometric",
    "fibonacci",
    "moving_average",
    "stat_band",
    "anchored_vwap",
    "volume_profile",
    "gap",
    "platform",
    "round_number",
)


# ---------------------------------------------------------------- data loading


def load_daily_from_duckdb(path: Path, start: str, end: str) -> pd.DataFrame:
    import duckdb

    connection = duckdb.connect(str(path), read_only=True)
    try:
        frame = connection.execute(
            """
            SELECT CAST(time AS DATE) AS date, open, high, low, close, volume, amount
            FROM kline_1d
            WHERE CAST(time AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
            ORDER BY time
            """,
            [start, end],
        ).df()
    finally:
        connection.close()
    return frame


def load_daily(args: argparse.Namespace) -> pd.DataFrame:
    if args.db:
        frame = load_daily_from_duckdb(Path(args.db), args.start or "1990-01-01", args.end or "2100-01-01")
        source = f"kh_local.duckdb:{args.db}"
    elif args.daily:
        frame = pd.read_csv(args.daily)
        source = f"csv:{args.daily}"
    else:
        raise SystemExit("必须提供 --db（KH 本地 DuckDB）或 --daily（日线 CSV）")

    frame.columns = [str(column).strip().lower() for column in frame.columns]
    rename = {"trade_date": "date", "time": "date", "vol": "volume"}
    frame = frame.rename(columns={k: v for k, v in rename.items() if k in frame.columns})
    required = {"date", "open", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise SystemExit(f"日线数据缺少字段：{sorted(missing)}")
    if "amount" not in frame.columns:
        frame["amount"] = np.nan
        amount_source = "missing"
    else:
        amount_source = "provided"
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    if len(frame) < 120:
        raise SystemExit(f"日线样本过少（{len(frame)} 行），关键位行为统计不可靠")
    frame.attrs["source"] = source
    frame.attrs["amount_source"] = amount_source
    return frame


# ------------------------------------------------------------------- analytics


def causal_zigzag(frame: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """因果 ZigZag：反向幅度达到阈值才确认转折，confirm_date 为首次达标日。"""
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    dates = frame["date"].to_numpy()
    pivots: list[dict] = []

    run_max_i, run_max = 0, highs[0]
    run_min_i, run_min = 0, lows[0]
    pivot: tuple[str, int, float] | None = None
    for i in range(1, len(frame)):
        if pivot is None:
            if highs[i] > run_max:
                run_max_i, run_max = i, highs[i]
            if lows[i] < run_min:
                run_min_i, run_min = i, lows[i]
            if run_max / run_min - 1 >= threshold:
                if run_min_i < run_max_i:
                    pivot = ("L", run_min_i, run_min)
                    pivots.append({"kind": "L", "index": run_min_i, "price": run_min, "confirm_index": i})
                else:
                    pivot = ("H", run_max_i, run_max)
                    pivots.append({"kind": "H", "index": run_max_i, "price": run_max, "confirm_index": i})
                mode = "high" if pivot[0] == "L" else "low"
                extreme_i, extreme = i, lows[i] if mode == "low" else highs[i]
            continue

        if mode == "high":
            if highs[i] > extreme:
                extreme_i, extreme = i, highs[i]
            elif lows[i] <= extreme * (1 - threshold):
                pivots.append({"kind": "H", "index": extreme_i, "price": extreme, "confirm_index": i})
                mode = "low"
                extreme_i, extreme = i, lows[i]
        else:
            if lows[i] < extreme:
                extreme_i, extreme = i, lows[i]
            elif highs[i] >= extreme * (1 + threshold):
                pivots.append({"kind": "L", "index": extreme_i, "price": extreme, "confirm_index": i})
                mode = "high"
                extreme_i, extreme = i, highs[i]

    rows = [
        {
            "pivot_date": pd.Timestamp(dates[item["index"]]),
            "confirm_date": pd.Timestamp(dates[item["confirm_index"]]),
            "type": item["kind"],
            "price": float(item["price"]),
        }
        for item in pivots
    ]
    return pd.DataFrame(rows)


def volume_profile(frame: pd.DataFrame, bucket: float = 10.0) -> dict:
    low = int(np.floor(frame["low"].min() / bucket) * bucket)
    high = int(np.ceil(frame["high"].max() / bucket) * bucket)
    grid = np.arange(low, high + bucket, bucket)
    volume = np.zeros(len(grid) - 1)
    for _, row in frame.iterrows():
        start = max(row["low"], grid[0])
        end = min(row["high"], grid[-1])
        if end <= start:
            index = int(np.searchsorted(grid, min(max(row["close"], grid[0]), grid[-1]))) - 1
            index = min(max(index, 0), len(volume) - 1)
            volume[index] += row["amount"]
            continue
        i0 = max(int(np.searchsorted(grid, start)) - 1, 0)
        i1 = min(int(np.searchsorted(grid, end)) - 1, len(volume) - 1)
        share = row["amount"] / max(i1 - i0 + 1, 1)
        for i in range(i0, i1 + 1):
            volume[i] += share
    series = pd.Series(volume, index=grid[:-1])
    total = series.sum()
    cumulative = series.cumsum()
    return {
        "series": series,
        "total": total,
        "val": float(series.index[int((cumulative >= total * 0.15).argmax())]),
        "vah": float(series.index[int((cumulative >= total * 0.85).argmax())]),
    }


def collect_candidates(
    daily: pd.DataFrame, close: float, gann_dir: Path | None, wave_anchors: Path | None = None
) -> tuple[list[dict], list[dict], dict]:
    candidates: list[dict] = []
    checks: list[dict] = []
    gaps: dict = {"geometric": "未提供 --gann-results，几何镜头缺失"}

    def add(
        level: float,
        lens: str,
        detail: str,
        status: str = "derived",
        source_date: object | None = None,
    ) -> None:
        if np.isfinite(level) and level > 0:
            candidates.append(
                {
                    "level": float(level),
                    "lens": lens,
                    "detail": detail,
                    "status": status,
                    "source_date": (
                        pd.Timestamp(source_date).strftime("%Y-%m-%d")
                        if source_date is not None and not pd.isna(source_date)
                        else None
                    ),
                }
            )

    # pivot：优先使用上游江恩输出的因果拐点；缺失时用内置因果 ZigZag 兜底
    pivot_files = []
    if gann_dir:
        pivot_files = [
            (gann_dir / "major_pivots_5pct.csv", "pivot_5pct"),
            (gann_dir / "local_pivots_2_5pct.csv", "pivot_2_5pct"),
        ]
    used_upstream = False
    for path, lens in pivot_files:
        if not path.is_file():
            continue
        frame = pd.read_csv(path, parse_dates=["pivot_date", "confirm_date"])
        hist_start = daily["date"].iloc[-1] - pd.Timedelta(days=420)
        frame = frame[(frame["pivot_date"] >= hist_start) & (frame["confirm_date"] <= daily["date"].iloc[-1])]
        for _, row in frame.iterrows():
            add(
                row["price"],
                "pivot",
                f"{lens}:{row['pivot_date']:%Y-%m-%d}",
                "confirmed",
                row["pivot_date"],
            )
        used_upstream = True
    if not used_upstream:
        for threshold, lens in ((0.05, "pivot_5pct"), (0.025, "pivot_2_5pct")):
            frame = causal_zigzag(daily, threshold)
            for _, row in frame.iterrows():
                add(
                    row["price"],
                    "pivot",
                    f"{lens}(internal):{row['pivot_date']:%Y-%m-%d}",
                    "confirmed",
                    row["pivot_date"],
                )
        gaps["pivot"] = "上游拐点缺失，已用内置因果 ZigZag 兜底；正式报告应改用江恩输出的因果拐点"

    # price_structure：未确认的近期日线极值（几何来源系统性排除的一类）
    for _, bar in daily.tail(60).iterrows():
        stamp = pd.Timestamp(bar["date"])
        add(bar["low"], "price_structure", f"low:{stamp:%Y-%m-%d}", "unconfirmed", stamp)
        add(bar["high"], "price_structure", f"high:{stamp:%Y-%m-%d}", "unconfirmed", stamp)

    # geometric + 上游交叉核对
    if gann_dir:
        current = gann_dir / "current_levels.csv"
        clusters = gann_dir / "clusters.csv"
        if current.is_file():
            gaps.pop("geometric", None)
            bands = pd.read_csv(current)
            if "as_of" in bands.columns:
                bands["as_of"] = pd.to_datetime(bands["as_of"], errors="coerce")
                if (bands["as_of"] > daily["date"].iloc[-1]).any():
                    raise SystemExit("江恩 current_levels.csv 含晚于 asof 的记录")
            for _, band in bands.iterrows():
                gann_date = band.get("as_of", daily["date"].iloc[-1])
                add(band["zone_lower"], "geometric", "gann_band_edge", source_date=gann_date)
                add(band["zone_upper"], "geometric", "gann_band_edge", source_date=gann_date)
                add(band["level"], "geometric", "gann_band_center", source_date=gann_date)
            if clusters.is_file():
                cluster_frame = pd.read_csv(clusters)
                cluster_frame["date"] = pd.to_datetime(cluster_frame["date"], errors="coerce")
                cluster_frame = cluster_frame[cluster_frame["date"] <= daily["date"].iloc[-1]]
                if cluster_frame.empty:
                    raise SystemExit("clusters.csv 在 asof 前没有记录")
                cluster_frame = cluster_frame[cluster_frame["date"] == cluster_frame["date"].max()]
                for _, band in bands.iterrows():
                    near = cluster_frame[
                        (cluster_frame["center"] >= band["zone_lower"] * 0.99)
                        & (cluster_frame["center"] <= band["zone_upper"] * 1.01)
                    ]
                    if len(near) == 0:
                        continue
                    member_low = float(near["min_level"].min())
                    member_high = float(near["max_level"].max())
                    if member_high - band["zone_upper"] > 0.0005 * close:
                        checks.append(
                            {
                                "check": "upstream_cross_check",
                                "status": "warning",
                                "detail": (
                                    f"current_levels 区间上沿 {band['zone_upper']:.2f} 低于 clusters 成员上界 "
                                    f"{member_high:.2f}；展示区间不等于共振覆盖范围，报告须以成员区间说明"
                                ),
                            }
                        )
                for _, cluster in cluster_frame.iterrows():
                    if abs(cluster["center"] / close - 1) <= 0.06:
                        add(cluster["min_level"], "geometric", "gann_cluster_edge", source_date=cluster["date"])
                        add(cluster["max_level"], "geometric", "gann_cluster_edge", source_date=cluster["date"])

    # fibonacci：只用审定账本声明的浪段锚点，禁止用比例反推浪型
    if wave_anchors and wave_anchors.is_file():
        anchors = pd.read_csv(wave_anchors, parse_dates=["end_date"])
        anchors = anchors[anchors["end_date"] <= daily["date"].iloc[-1]]
        for _, row in anchors.iterrows():
            high, low = float(row["start_price"]), float(row["end_price"])
            if high < low:
                high, low = low, high
            span = high - low
            tag = str(row.get("tag", "leg"))
            for ratio in (0.236, 0.382, 0.5, 0.618, 0.786):
                add(
                    high - span * ratio,
                    "fibonacci",
                    f"retrace_{tag}_{ratio:.3f}",
                    source_date=row.get("end_date"),
                )
            for ratio in (1.0, 1.272, 1.618, 2.618):
                add(
                    high - span * ratio,
                    "fibonacci",
                    f"ext_{tag}_{ratio}",
                    source_date=row.get("end_date"),
                )
    else:
        gaps["fibonacci"] = "未提供 --wave-anchors（审定浪段锚点），斐波那契镜头缺失"

    return candidates, checks, gaps


def add_derived_candidates(
    candidates: list[dict],
    daily: pd.DataFrame,
    close: float,
    atr: float,
    vwap_anchors: list[tuple[str, pd.Timestamp]] | None = None,
) -> None:
    def add(level: float, lens: str, detail: str, source_date: str | None = None) -> None:
        if np.isfinite(level) and level > 0:
            candidates.append(
                {
                    "level": float(level),
                    "lens": lens,
                    "detail": detail,
                    "status": "derived",
                    "source_date": source_date,
                }
            )

    for name, value in (
        ("ma20", float(daily["close"].tail(20).mean())),
        ("ma60", float(daily["close"].tail(60).mean())),
        ("ma120", float(daily["close"].tail(120).mean())),
    ):
        add(value, "moving_average", name)
    sd20 = float(daily["close"].tail(20).std())
    add(float(daily["close"].tail(20).mean()) - 2 * sd20, "stat_band", "bollinger_lower")
    add(close - atr, "stat_band", "close_minus_1atr")
    add(close - 2 * atr, "stat_band", "close_minus_2atr")
    for label, anchor in (vwap_anchors or []):
        try:
            anchor_date = pd.Timestamp(anchor)
            segment = daily[daily["date"] >= anchor_date]
        except Exception:
            continue
        if len(segment) < 3:
            continue
        typical = (segment["high"] + segment["low"] + segment["close"]) / 3
        weight = segment["amount"].fillna(0)
        if weight.sum() <= 0:
            continue
        vwap = float((typical * weight).sum() / weight.sum())
        sd = float(np.sqrt((weight * (typical - vwap) ** 2).sum() / weight.sum()))
        add(vwap, "anchored_vwap", f"vwap_{label}", anchor_date.strftime("%Y-%m-%d"))
        add(vwap - sd, "anchored_vwap", f"vwap-1sd_{label}", anchor_date.strftime("%Y-%m-%d"))
        add(vwap - 2 * sd, "anchored_vwap", f"vwap-2sd_{label}", anchor_date.strftime("%Y-%m-%d"))
    for label, frame in (("250d", daily.tail(250)), ("60d", daily.tail(60))):
        if frame["amount"].isna().all():
            continue
        result = volume_profile(frame)
        add(result["val"], "volume_profile", f"VA_low_{label}")
        add(result["vah"], "volume_profile", f"VA_high_{label}")
        series = result["series"]
        for level, _ in series.sort_values(ascending=False).head(6).items():
            if abs(level / close - 1) <= 0.06:
                add(level, "volume_profile", f"HVN_{label}")
    for i in range(max(len(daily) - 120, 1), len(daily)):
        previous, current = daily.iloc[i - 1], daily.iloc[i]
        if current["low"] > previous["high"]:
            after = daily.iloc[i:]
            if after["low"].min() > previous["high"]:
                add(previous["high"], "gap", f"up_gap_{current['date']:%Y-%m-%d}")
                add(current["low"], "gap", f"up_gap_{current['date']:%Y-%m-%d}")
        if current["high"] < previous["low"]:
            after = daily.iloc[i:]
            if after["high"].max() < previous["low"]:
                add(current["high"], "gap", f"down_gap_{current['date']:%Y-%m-%d}")
                add(previous["low"], "gap", f"down_gap_{current['date']:%Y-%m-%d}")
    span = daily["high"].rolling(20).max() - daily["low"].rolling(20).min()
    flat = span / daily["close"] < 0.035
    start = None
    previous = None
    for date, flag in zip(daily["date"], flat):
        if flag and start is None:
            start = date
        if (not flag) and start is not None:
            segment = daily[(daily["date"] >= start) & (daily["date"] <= previous)]
            add(float(segment["high"].max()), "platform", f"platform_{start:%Y-%m-%d}")
            add(float(segment["low"].min()), "platform", f"platform_{start:%Y-%m-%d}")
            start = None
        previous = date
    for level in np.arange(round(close / 50) * 50 - 200, round(close / 50) * 50 + 250, 50):
        add(float(level), "round_number", "50pt")


def merge_zones(candidates: pd.DataFrame, close: float, max_span_pct: float = 0.0025) -> list[dict]:
    """按成员间距聚类，但强制区域直径不超过 max_span_pct。

    没有直径上限时会出现链式漂移：3753.78 → 3754.14 → 3761.42 → 3761.75 → 3767.50
    → 3771.13 每步都在容差内，最终区域宽 0.46%（超过标称容差 1.8 倍），
    并把 3754.14 这样的关键位"淹没"在均值标签里。
    """
    candidates = candidates.copy()
    candidates["kind"] = np.where(candidates["level"] < close, "支撑", "压力")
    max_span = max_span_pct * close
    zones: list[dict] = []
    for kind in ("支撑", "压力"):
        side = candidates[candidates["kind"] == kind].sort_values("level")
        for _, row in side.iterrows():
            entry = {
                "level": float(row["level"]),
                "lens": row["lens"],
                "detail": row["detail"],
                "status": row.get("status", "derived"),
                "source_date": row.get("source_date"),
            }
            placed = False
            for zone in reversed(zones):
                if zone["kind"] != kind:
                    continue
                levels = [member["level"] for member in zone["members"]] + [entry["level"]]
                if abs(entry["level"] - float(np.mean(levels))) / close > CLUSTER_TOL:
                    continue
                if max(levels) - min(levels) > max_span:
                    continue
                zone["members"].append(entry)
                placed = True
                break
            if not placed:
                zones.append({"kind": kind, "members": [entry]})
    return zones


def level_behaviour(level: float, kind: str, history: pd.DataFrame, amount_median: float) -> dict:
    """单个价位的市场行为：触碰次数、守住率、触碰后反应、触碰日量能。"""
    support = kind == "支撑"
    touches: list[pd.Timestamp] = []
    reactions: list[float] = []
    failures = 0
    for _, bar in history.iterrows():
        hit = abs(bar["low"] / level - 1) <= TOUCH_TOL if support else abs(bar["high"] / level - 1) <= TOUCH_TOL
        if not hit:
            continue
        row_index = history.index.get_loc(bar.name)
        forward = history["close"].iloc[row_index:row_index + 6]
        if len(forward) < 2:
            continue
        touches.append(bar["date"])
        if support:
            reactions.append(float(forward.max() / level - 1))
            failures += int(float(forward.min() / level - 1) < -0.01)
        else:
            reactions.append(float(level / forward.min() - 1))
            failures += int(float(forward.max() / level - 1) > 0.01)
    hold = float(1 - failures / len(touches)) if touches else np.nan
    return {
        "touches": len(touches),
        "hold_rate": hold,
        "reaction_median": float(np.median(reactions)) if reactions else np.nan,
        "volume_ratio": float(history["amount"].reindex(touches).median() / amount_median) if touches and amount_median else np.nan,
        "days_since_touch": int((history["date"].iloc[-1] - max(touches)).days) if touches else None,
    }


def behaviour_metrics(zone: dict, history: pd.DataFrame, amount_median: float, close: float) -> dict:
    """区域指标以锚点计。锚点规则：成员自身互动次数最多者；并列时已确认拐点优先，
    再取距现价最近者。中心值仅作审计参考，不再作为标签。"""
    members = zone["members"]
    for member in members:
        member.update(level_behaviour(member["level"], zone["kind"], history, amount_median))
    ranked = sorted(
        members,
        key=lambda item: (
            -item["touches"],
            0 if item["status"] == "confirmed" else 1,
            abs(item["level"] - close),
        ),
    )
    anchor = ranked[0]
    level = float(anchor["level"])
    support = zone["kind"] == "支撑"
    levels = [member["level"] for member in members]
    lenses = {member["lens"] for member in members}
    source_dates = sorted(
        {
            pd.Timestamp(member["source_date"]).normalize() if member.get("source_date") else None
            for member in members
        }
        - {None}
    )
    formation_start = source_dates[0].strftime("%Y-%m-%d") if source_dates else None
    formation_end = source_dates[-1].strftime("%Y-%m-%d") if source_dates else None
    return {
        "level": round(level, 2),
        "anchor_status": anchor["status"],
        "anchor_lens": anchor["lens"],
        "anchor_detail": anchor["detail"],
        "zone_low": round(min(levels), 2),
        "zone_high": round(max(levels), 2),
        "zone_span_pct": round((max(levels) - min(levels)) / close, 5),
        "center": round(float(np.mean(levels)), 2),
        "member_count": len(members),
        "lens_count": len(lenses),
        "lenses": "|".join(sorted(lenses)),
        "touches": anchor["touches"],
        "hold_rate": anchor["hold_rate"],
        "reaction_median": anchor["reaction_median"],
        "volume_ratio": anchor["volume_ratio"],
        "days_since_touch": anchor["days_since_touch"],
        "formation_start": formation_start,
        "formation_end": formation_end,
        "formation_window": (
            f"{formation_start}/{formation_end}"
            if formation_start and formation_end
            else "unknown"
        ),
        "members": " ; ".join(
            f"{member['level']:.2f}({member['lens']},{member['status']},t{member['touches']})"
            for member in sorted(members, key=lambda item: item["level"])
        )[:600],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the multi-lens level registry with mandatory checks")
    parser.add_argument("--db", help="KH 本地 DuckDB 路径（优先）")
    parser.add_argument("--daily", help="日线 CSV（date/open/high/low/close/volume/amount）")
    parser.add_argument("--start", help="YYYY-MM-DD（--db 模式生效）")
    parser.add_argument("--end", help="YYYY-MM-DD（--db 模式生效）")
    parser.add_argument("--gann-results", help="江恩输出目录（含 current_levels.csv / clusters.csv / *_pivots_*.csv）")
    parser.add_argument("--previous-levels", help="上一份报告的价位 CSV，需含 level 列；用于交接检查")
    parser.add_argument(
        "--wave-anchors",
        help="审定浪段锚点 CSV（start_date,start_price,end_date,end_price,tag），用于斐波那契镜头；缺省则该镜头标记为缺口",
    )
    parser.add_argument("--symbol", default="上证指数")
    parser.add_argument("--target-date", help="目标交易日 YYYY-MM-DD；缺省为数据最后一日")
    parser.add_argument("--asof", help="实际允许使用的最后数据日；盘前应严格早于 target-date")
    parser.add_argument("--stage", choices=("premarket", "intraday", "post_close", "research"), default="premarket")
    parser.add_argument("--available-at", help="盘中或自定义阶段派生结果的明确可得时间")
    parser.add_argument(
        "--require-handoff",
        action="store_true",
        help="生产归档时必须提供严格早于 target-date 的 --previous-levels",
    )
    parser.add_argument("--orphan-atr", type=float, default=1.5, help="孤立位扫描的距离阈值（ATR 倍数）")
    parser.add_argument(
        "--max-zone-span-pct",
        type=float,
        default=0.0025,
        help="单个区域允许的最大直径（占收盘价比例）。防止链式合并把关键位淹没在均值标签里，默认 0.25%%",
    )
    parser.add_argument("--output", required=True, help="输出目录（绝对路径）")
    args = parser.parse_args()

    daily = load_daily(args)
    target = parse_date(args.target_date) if args.target_date else pd.Timestamp(daily["date"].iloc[-1]).normalize()
    if args.asof:
        asof = parse_date(args.asof)
    elif args.stage == "premarket":
        eligible = daily[daily["date"] < target]
        if eligible.empty:
            raise SystemExit("盘前模式下找不到严格早于 target-date 的日线")
        asof = pd.Timestamp(eligible["date"].max()).normalize()
    else:
        asof = min(pd.Timestamp(daily["date"].max()).normalize(), target)
    if asof > target:
        raise SystemExit(f"--asof={asof.date()} 晚于 target-date={target.date()}")
    if args.stage == "premarket" and asof >= target:
        raise SystemExit("盘前关键位必须使用严格早于 target-date 的数据")
    daily = daily[daily["date"] <= asof].reset_index(drop=True)
    if len(daily) < 120:
        raise SystemExit(f"截至 {asof.date()} 的日线样本不足（{len(daily)} 行）")
    close = float(daily["close"].iloc[-1])
    as_of = daily["date"].iloc[-1]
    history = daily.tail(DEFAULT_HISTORY).reset_index(drop=True)
    atr_value = wilder_atr_14(daily)
    if atr_value is None or atr_value <= 0:
        raise SystemExit("无法计算统一 Wilder 14 日平均真实波幅")
    atr = float(atr_value)

    candidates, checks, gaps = collect_candidates(
        daily,
        close,
        Path(args.gann_results) if args.gann_results else None,
        Path(args.wave_anchors) if args.wave_anchors else None,
    )
    vwap_anchors: list[tuple[str, pd.Timestamp]] = []
    declared_legs: list[tuple[pd.Timestamp, pd.Timestamp, str]] = []
    if args.wave_anchors and Path(args.wave_anchors).is_file():
        anchor_frame = pd.read_csv(args.wave_anchors, parse_dates=["start_date", "end_date"])
        anchor_frame = anchor_frame[anchor_frame["end_date"] <= asof]
        for row in anchor_frame.itertuples():
            declared_legs.append((row.start_date.normalize(), row.end_date.normalize(), str(row.tag)))
        for row in anchor_frame.sort_values("end_date").tail(4).itertuples():
            vwap_anchors.append((row.end_date.strftime("%Y-%m-%d"), row.end_date))
    add_derived_candidates(candidates, daily, close, atr, vwap_anchors)
    frame = pd.DataFrame(candidates)
    if "source_date" not in frame.columns:
        frame["source_date"] = None
    extracted_dates = frame["detail"].astype(str).str.extract(r"(20\d{2}-\d{2}-\d{2})")[0]
    frame["source_date"] = frame["source_date"].where(frame["source_date"].notna(), extracted_dates)
    frame["source_date"] = frame["source_date"].fillna(as_of.strftime("%Y-%m-%d"))
    zones = merge_zones(frame, close, max_span_pct=args.max_zone_span_pct)

    amount_median = float(history["amount"].median()) if history["amount"].notna().any() else 0.0
    rows = []
    for zone in zones:
        metrics = behaviour_metrics(zone, history, amount_median, close)
        metrics["kind"] = zone["kind"]
        metrics["distance_atr"] = (metrics["level"] - close) / atr
        metrics["distance_pct"] = metrics["level"] / close - 1
        rows.append(metrics)
    table = pd.DataFrame(rows)
    table["character"] = np.where(
        table["hold_rate"].isna(),
        "未触碰",
        np.where(table["hold_rate"] >= 0.8, "守得住", np.where(table["hold_rate"] <= 0.45, "反复被破", "混合")),
    )
    # Keep raw evidence only. The LLM weighs levels; this script does not score or rank them.
    table["unverified"] = (table["touches"] == 0) | (table["lens_count"] <= 1)
    table = table.sort_values(["kind", "level"]).reset_index(drop=True)

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    # 同源带（same-origin band）：同侧自最近档位起相邻间距 <= 0.5 ATR、累计跨度 <= 1.0 ATR。
    # 依据 references/evidence-rules.md：只有带内最外侧一档计入防线，
    # 其余档位标为 cluster_member，避免把一条带写成“多层支撑/压力”。
    table["cluster_role"] = ""
    table["cluster_defense_level"] = np.nan
    band_rows = []
    for kind in ("支撑", "压力"):
        side = table[table["kind"] == kind].copy()
        side["offset"] = side["level"] - close
        walk = (
            side[side["offset"] < 0].sort_values("level", ascending=False)
            if kind == "支撑"
            else side[side["offset"] > 0].sort_values("level")
        )
        walk = walk.reset_index().rename(columns={"index": "table_index"})
        if walk.empty:
            continue
        members = []
        span_atr = 0.0
        previous = None
        for row in walk.itertuples():
            if previous is None:
                members.append(row)
                previous = row
                continue
            gap = abs(row.level - previous.level)
            if gap <= 0.5 * atr and span_atr + gap / atr <= 1.0:
                members.append(row)
                span_atr += gap / atr
                previous = row
            else:
                break
        if len(members) < 2:
            continue
        defense = members[-1]
        next_row = walk.iloc[len(members)] if len(members) < len(walk) else None
        band_id = f"{kind}_band_1"
        formation_dates = []
        for member in members:
            for value in (member.formation_start, member.formation_end):
                if value and value != "unknown":
                    formation_dates.append(pd.Timestamp(value).normalize())
        leg_tags = {
            tag
            for stamp in formation_dates
            for start, end, tag in declared_legs
            if start <= stamp <= end
        }
        cluster_type = "same_origin_cluster" if len(leg_tags) == 1 else "spatial_proximity_band"
        for order, member in enumerate(members):
            role = "anchor" if order == 0 else ("defense" if member.table_index == defense.table_index else "cluster_member")
            table.loc[member.table_index, "cluster_role"] = f"{band_id}:{role}"
            table.loc[member.table_index, "cluster_defense_level"] = float(defense.level)
        band_rows.append(
            {
                "band_id": band_id,
                "kind": kind,
                "anchor_level": float(members[0].level),
                "defense_level": float(defense.level),
                "member_levels": "|".join(f"{m.level:.2f}" for m in members),
                "member_count": len(members),
                "span_atr": round(span_atr, 2),
                "cluster_type": cluster_type,
                "formation_window": (
                    f"{min(formation_dates).date()}/{max(formation_dates).date()}"
                    if formation_dates
                    else "unknown"
                ),
                "declared_wave_legs": sorted(leg_tags),
                "next_non_cluster_level": None if next_row is None else float(next_row.level),
                "unverified_members": int(sum(1 for m in members if m.unverified)),
            }
        )
    bands = pd.DataFrame(band_rows)
    if not bands.empty:
        bands.to_csv(output / "same_origin_bands.csv", index=False)
        for row in bands.itertuples():
            checks.append(
                {
                    "check": "same_origin_band",
                    "status": "info",
                    "detail": (
                        f"{row.kind}带 {row.band_id}（{row.cluster_type}）：锚点 {row.anchor_level:.2f} 至防线 {row.defense_level:.2f}"
                        f"（{row.member_count} 档，跨度 {row.span_atr:.2f} ATR）；中间档不作防线，"
                        f"下一道非同源档位 {row.next_non_cluster_level if row.next_non_cluster_level is not None else '未识别'}"
                    ),
                }
            )

    table.to_csv(output / "level_registry.csv", index=False)

    # 检查 A：孤立位扫描
    orphan = table[
        (table["distance_atr"].abs() <= args.orphan_atr)
        & (table["lens_count"] == 1)
        & (table["lenses"] == "price_structure")
    ]
    checks.append(
        {
            "check": "orphan_scan",
            "status": "warning" if len(orphan) else "pass",
            "detail": "1.5 ATR 内存在只有 price_structure 单一镜头的近期极值；报告必须逐项披露，未披露由方向总门禁拦截"
            if len(orphan)
            else "1.5 ATR 内无孤立极值",
            "levels": orphan[["kind", "level", "distance_atr"]].to_dict("records"),
        }
    )

    # 检查 C：交接检查
    if not args.previous_levels:
        checks.append(
            {
                "check": "handoff",
                "status": "fail" if args.require_handoff else "warning",
                "detail": "未提供严格早于 target-date 的 previous-levels；生产归档不得跳过关键位交接",
                "missing_levels": [],
                "tracked_targets": [],
            }
        )
    if args.previous_levels:
        previous = pd.read_csv(args.previous_levels)
        source_column = next(
            (
                item
                for item in previous.columns
                if str(item).lower() in ("source_report", "source_report_date", "report_date")
            ),
            None,
        )
        source_dates = []
        if source_column:
            for value in previous[source_column].dropna().astype(str):
                match = re.search(r"(20\d{2})(\d{2})(\d{2})", value)
                if match:
                    source_dates.append(pd.Timestamp("-".join(match.groups())))
        future_sources = sorted({stamp.strftime("%Y-%m-%d") for stamp in source_dates if stamp >= target})
        checks.append(
            {
                "check": "handoff_provenance",
                "status": (
                    "fail"
                    if future_sources or (args.require_handoff and not source_dates)
                    else ("pass" if source_dates else "warning")
                ),
                "detail": (
                    f"上一份价位表来自目标日或未来日：{future_sources}；必须改用严格早于目标日的最近一份报告"
                    if future_sources
                    else (
                        f"上一份价位表来源日：{', '.join(sorted({d.strftime('%Y-%m-%d') for d in source_dates}))}"
                        if source_dates
                        else "上一份价位表缺少 source_report 日期，无法审计时间先后"
                    )
                ),
                "source_dates": sorted({d.strftime("%Y-%m-%d") for d in source_dates}),
            }
        )
        column = next((item for item in previous.columns if str(item).lower() in ("level", "price", "价位")), None)
        if column is None:
            checks.append({"check": "handoff", "status": "skipped", "detail": "上一份价位文件缺少 level/price 列"})
        else:
            status_column = next((item for item in previous.columns if str(item).lower() in ("status", "状态")), None)
            role_column = next((item for item in previous.columns if str(item).lower() in ("role", "用途")), None)
            missing: list[dict] = []
            tracked: list[dict] = []
            for _, row in previous.iterrows():
                value = float(row[column])
                if not np.isfinite(value) or abs(value / close - 1) > 0.15:
                    continue
                status = str(row[status_column]).strip().lower() if status_column else "confirmed"
                role = str(row[role_column]) if role_column else ""
                entry = {"level": round(value, 2), "role": role, "status": status}
                covered = ((table["zone_low"] <= value * 1.0025) & (table["zone_high"] >= value * 0.9975)).any()
                # 预测/目标类价位本就不属于已观察价位，登记表不覆盖属正常，只作跟踪项
                if status in ("projection", "target", "band_edge", "pending") or not covered and status in ("projection", "target"):
                    tracked.append(entry)
                elif not covered:
                    missing.append(entry)
            checks.append(
                {
                    "check": "handoff",
                    "status": "fail" if missing else "pass",
                    "detail": "上一份报告中 status=confirmed 的价位未进入本次登记表，必须补齐或写明废弃理由；预测目标类只作跟踪，不要求覆盖",
                    "missing_levels": missing,
                    "tracked_targets": tracked,
                }
            )

    ladder = table[table["distance_atr"].abs() <= 2.2][
        [
            "character",
            "kind",
            "level",
            "anchor_status",
            "zone_low",
            "zone_high",
            "zone_span_pct",
            "member_count",
            "lens_count",
            "lenses",
            "touches",
            "hold_rate",
            "reaction_median",
            "distance_atr",
            "unverified",
            "formation_window",
            "cluster_role",
            "cluster_defense_level",
        ]
    ]
    available_at = resolve_available_at(
        asof,
        stage="intraday_update" if args.stage == "intraday" else args.stage,
        explicit=args.available_at,
        forecast_cutoff=args.available_at,
    )
    summary = {
        "ruleset_version": RULESET_VERSION,
        "symbol": args.symbol,
        "stage": args.stage,
        "requested_target_date": target.strftime("%Y-%m-%d"),
        "asof": asof.strftime("%Y-%m-%d"),
        "as_of": as_of.strftime("%Y-%m-%d"),
        "data_asof": as_of.strftime("%Y-%m-%d"),
        "available_at": available_at,
        "target_date": target.strftime("%Y-%m-%d"),
        "close": close,
        "atr14": round(atr, 2),
        "atr_method": "wilder_14",
        "data_source": daily.attrs.get("source"),
        "source": daily.attrs.get("source"),
        "data_quality": "complete" if not gaps else "partial",
        "amount_source": daily.attrs.get("amount_source"),
        "lens_count_total": len(LENSES),
        "zones": int(len(table)),
        "same_origin_bands": band_rows,
        "checks": checks,
        "gaps": gaps,
        "mandatory_gate": {
            "passed": not any(item["status"] == "fail" for item in checks),
            "rule": "任一检查为 fail 时，报告不得直接输出最近支撑/压力结论，必须先补齐或披露",
        },
    }
    atomic_write_json(output / "level_registry_summary.json", summary)
    ladder.to_csv(output / "level_ladder.csv", index=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    print(ladder.to_string(index=False))
    return 0 if summary["mandatory_gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
