#!/usr/bin/env python3
"""Build a causal multi-clock time ledger for an A-share index."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gann.data import audit_ohlcv, load_ohlcv
from gann.multiclock import (
    LOCAL_TRADING_OFFSETS,
    MAJOR_TRADING_OFFSETS,
    WINDOW_COLUMNS,
    build_confirmation_ledger,
    extend_sessions,
    generate_trading_windows,
    generate_wave_duration_windows,
    multiclock_density,
)
from gann.time_points import select_time_key_points
from gann.windows import generate_time_windows
from gann.zigzag import confirmed_zigzag


def load_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    date_col = "date" if "date" in frame else "trade_date"
    rename = {date_col: "date", "vol": "volume"}
    frame = frame.rename(columns=rename)
    required = {"date", "open", "high", "low", "close", "amount"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"daily CSV missing columns: {sorted(missing)}")
    if "volume" not in frame:
        frame["volume"] = 0.0
    frame["date"] = pd.to_datetime(frame["date"].astype(str))
    for column in ("open", "high", "low", "close", "volume", "amount"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    return frame[["date", "open", "high", "low", "close", "volume", "amount"]].sort_values("date").reset_index(drop=True)


def standardize_natural(windows: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "source_family", "causal_family", "clock", "anchor_date", "anchor_type", "anchor_price",
        "confirm_date", "offset", "ratio", "center_date", "start_date", "end_date", "tolerance",
        "calendar_status", "window_id",
    ]
    if windows.empty:
        return pd.DataFrame(columns=columns)
    natural = windows.loc[windows["window_set"] == "big"].copy()
    natural["source_family"] = "major_natural"
    natural["causal_family"] = "price_pivot_clock"
    natural["clock"] = "natural_day"
    natural["anchor_price"] = pd.NA
    natural["offset"] = natural["offset_days"]
    natural["ratio"] = pd.NA
    natural["tolerance"] = natural["tolerance_days"]
    natural["calendar_status"] = "calendar_day"
    return natural[columns]


def write_summary(
    output: Path,
    as_of: pd.Timestamp,
    key_points: pd.DataFrame,
    windows: pd.DataFrame,
    confirmation: pd.DataFrame,
    calendar_note: str,
) -> None:
    def cell(value: str) -> str:
        return str(value).replace("|", "、") or "—"

    calendar_labels = {
        "observed": "已观测交易日",
        "exchange_calendar": "交易所交易日",
        "natural_nontrading_day": "自然日节点/非交易日",
        "natural_calendar_unverified": "自然日节点/交易状态未核实",
    }
    key_lines = [
        f"| {row.date.date()} | {row.priority_rank} | {row.window_count} | {row.source_family_count} | "
        f"{row.independent_family_count} | {row.center_member_count} | {cell(row.source_families)} | "
        f"{cell(row.causal_families)} | {calendar_labels.get(row.session_status, row.session_status)} | "
        f"{cell(row.center_window_ids)} | {cell(row.center_anchors)} | {cell(row.center_confirm_dates)} |"
        for row in key_points.itertuples(index=False)
    ] or ["| — | — | 0 | 0 | 0 | 0 | 暂无符合筛选条件的关键时间点 | — | — | — | — | — |"]
    wave_note = "已提供审定波浪段落。" if windows["source_family"].eq("wave_duration").any() else "波浪等时时钟缺失：未提供有效审定段落，不虚构来源。"
    recent = confirmation.loc[confirmation["date"] <= as_of].tail(10)
    recent_lines = []
    for row in recent.to_dict(orient="records"):
        tags = []
        for field, label in (
            ("trailing_low_candidate", "低点候选"),
            ("bullish_price_reversal", "价格反转"),
            ("breadth_reversal_up", "宽度反转"),
            ("index_confirmation_up", "指数确认"),
            ("diffusion_confirmation_up", "扩散确认"),
            ("cross_index_confirmation_up", "跨指数确认"),
        ):
            if bool(row[field]):
                tags.append(label)
        if tags:
            daily_return = row["return"]
            advance = f"{row['advance_ratio']:.1%}" if pd.notna(row["advance_ratio"]) else "—"
            recent_lines.append(
                f"| {pd.Timestamp(row['date']).date()} | {row['close']:.2f} | {daily_return:+.2%} | {advance}"
            )
            recent_lines[-1] += f" | {'、'.join(tags)} |"
    if not recent_lines:
        recent_lines = ["| — | — | — | — | 最近10日无反转/确认标签 |"]
    output.write_text(
        f"""# 多时钟时间确认账本

数据截至：{as_of.date()}  
未来交易日历：{calendar_note}

## 重要关键时间点

| 关键日期 | 展示优先级 | 主容差成员数 | 时钟种类 | 独立因果来源 | 同日中心成员数 | 来源族 | 因果族 | 日历状态 | 原始中心来源 | 中心起算锚点 | 锚点确认日 |
|---|---:|---:|---:|---:|---:|---|---|---|---|---|---|
{chr(10).join(key_lines)}

仅展示冻结锚点的原始中心日，按保守因果来源、时钟种类、成员数及同日中心数排序后去重；完整容差起止和覆盖账本仅供审计。展示优先级不是预测概率，关键日为观察节点，不保证当日变盘。

{wave_note}

确认条件：到达关键日后，仍须分别检查价格反转、宽度、跨指数及周线确认；未确认则记录“时间到而价格未确认”，不据日期单独判断涨跌。

窗口数不能直接相加为置信度。同一来源族内的多个周期、比例或锚点只算一个来源族；共享价格拐点机制的自然日/交易日与5%/2.5%时钟统一算一个独立因果来源。

## 极值与确认分离

| 日期 | 收盘 | 涨跌 | 上涨占比 | 标签 |
|---|---:|---:|---:|---|
{chr(10).join(recent_lines)}

- `低点候选/高点候选`只描述当日可见的尾随极值，不宣告波浪完成。
- `价格反转`、`宽度反转`、`指数确认`和`扩散确认`必须分开记录；极值日与确认日可以不同。
- 自然日大周期、交易日大周期、交易日低级别周期、波浪等时属于四类时间解释；它们共享锚点时不得伪装成完全独立证据。
- 时间窗到达而价格/宽度不确认时，状态应记为“时间到而价格未确认”，不得移动锚点或中心日。
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a causal multi-clock time ledger")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--db", type=Path)
    source.add_argument("--daily", type=Path)
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end")
    parser.add_argument("--projection-end")
    parser.add_argument("--future-sessions", type=Path, help="CSV with a date/trade_date column from an exchange calendar")
    parser.add_argument("--breadth", type=Path, help="Optional breadth CSV with advance_ratio or up/traded")
    parser.add_argument("--peer-indices", type=Path, help="Optional long CSV with date,symbol,close for broad-index confirmation")
    parser.add_argument("--wave-segments", type=Path, help="Optional declared segment CSV for 0.618/1/1.618 duration projections")
    parser.add_argument("--major-threshold", type=float, default=0.05)
    parser.add_argument("--local-threshold", type=float, default=0.025)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.db:
        end = args.end or pd.Timestamp.today().strftime("%Y-%m-%d")
        frame = load_ohlcv(args.db, args.start, end)
    else:
        frame = load_csv(args.daily)
        frame = frame.loc[frame["date"] >= pd.Timestamp(args.start)]
        if args.end:
            frame = frame.loc[frame["date"] <= pd.Timestamp(args.end)]
        frame = frame.reset_index(drop=True)
    audit = audit_ohlcv(frame)
    if not audit["passed"]:
        raise RuntimeError(f"data audit failed: {audit}")
    as_of = pd.Timestamp(frame.iloc[-1]["date"])
    projection_end = pd.Timestamp(args.projection_end) if args.projection_end else as_of + pd.Timedelta(days=90)

    future_sessions = None
    calendar_note = "未来工作日估算（遇法定休市须用交易所日历重跑）"
    if args.future_sessions:
        future_frame = pd.read_csv(args.future_sessions)
        date_col = "date" if "date" in future_frame else "trade_date"
        future_sessions = future_frame[date_col].astype(str).tolist()
        calendar_note = f"交易所日历 {args.future_sessions}"
    sessions = extend_sessions(frame["date"], projection_end, future_sessions)

    major = confirmed_zigzag(frame, threshold=args.major_threshold)
    local = confirmed_zigzag(frame, threshold=args.local_threshold)
    natural_raw = pd.concat(
        [
            generate_time_windows(major, frame["date"].min(), projection_end, tolerance_days=2),
            generate_time_windows(major, frame["date"].min(), projection_end, tolerance_days=3),
        ],
        ignore_index=True,
    )
    natural = standardize_natural(natural_raw)
    major_trading = generate_trading_windows(
        major, sessions, source_family="major_trading", offsets=MAJOR_TRADING_OFFSETS, tolerance_bars=1
    )
    local_trading = generate_trading_windows(
        local, sessions, source_family="local_trading", offsets=LOCAL_TRADING_OFFSETS, tolerance_bars=1
    )
    args.output.mkdir(parents=True, exist_ok=True)
    frames = [natural, major_trading, local_trading]
    if args.wave_segments:
        segments = pd.read_csv(args.wave_segments)
        wave = generate_wave_duration_windows(segments, sessions)
        frames.append(wave)
        wave.to_csv(args.output / "wave_duration_windows.csv", index=False)
    clean_frames = [candidate.dropna(axis=1, how="all") for candidate in frames if not candidate.empty]
    windows = (
        pd.concat(clean_frames, ignore_index=True).reindex(columns=WINDOW_COLUMNS)
        if clean_frames
        else pd.DataFrame(columns=WINDOW_COLUMNS)
    )
    for column in ("anchor_date", "confirm_date", "center_date", "start_date", "end_date"):
        windows[column] = pd.to_datetime(windows[column])
    density = multiclock_density(sessions, windows)
    key_points, key_members = select_time_key_points(windows, sessions, as_of, projection_end)

    breadth = pd.read_csv(args.breadth) if args.breadth else None
    peers = pd.read_csv(args.peer_indices) if args.peer_indices else None
    confirmation = build_confirmation_ledger(frame, breadth, peers)

    major.to_csv(args.output / "major_pivots_5pct.csv", index=False)
    local.to_csv(args.output / "local_pivots_2_5pct.csv", index=False)
    windows.to_csv(args.output / "multiclock_windows.csv", index=False)
    density.to_csv(args.output / "multiclock_density.csv", index=False)
    key_points.to_csv(args.output / "time_key_points.csv", index=False)
    key_members.to_csv(args.output / "time_key_point_members.csv", index=False)
    confirmation.to_csv(args.output / "daily_confirmation_ledger.csv", index=False)
    write_summary(args.output / "multiclock_summary.md", as_of, key_points, windows, confirmation, calendar_note)
    print(f"Wrote multi-clock ledger to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
