#!/usr/bin/env python3
"""从 KH 本地 DuckDB 读取指数日线，并因果聚合为周线。

只有本地覆盖不足时，才通过 KH CLI 补数；补数结果仍从本地库读取。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def _load_kh_loader():
    candidates = []
    if os.getenv("KHQUANT_ROOT"):
        candidates.append(Path(os.environ["KHQUANT_ROOT"]) / "tools")
    candidates.extend([
        Path.cwd() / "tools",
        Path("/Users/a/PycharmProjects/khquant/tools"),
    ])
    for directory in candidates:
        if (directory / "kh_local_data.py").is_file():
            sys.path.insert(0, str(directory))
            from kh_local_data import ensure_data, read_daily  # type: ignore
            return ensure_data, read_daily
    raise SystemExit("未找到 tools/kh_local_data.py；请在 khquant 工作区运行，或设置 KHQUANT_ROOT。")


def aggregate_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    daily = daily.copy()
    daily["trade_date"] = pd.to_datetime(daily["trade_date"])
    daily = daily.sort_values("trade_date").set_index("trade_date")
    aggregation = {"open": "first", "high": "max", "low": "min", "close": "last"}
    for field in ("vol", "amount"):
        if field in daily.columns:
            aggregation[field] = "sum"
    daily["week_bucket"] = daily.index.to_period("W-FRI")
    weekly = daily.groupby("week_bucket").agg(aggregation).dropna(subset=["open", "high", "low", "close"])
    weekly["week_end"] = daily.groupby("week_bucket").apply(lambda group: group.index.max(), include_groups=False)
    weekly = weekly.reset_index(drop=True)
    return weekly[["week_end", *[column for column in weekly.columns if column != "week_end"]]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-code", required=True, help="e.g. 000300.SH")
    parser.add_argument("--start", required=True, help="YYYYMMDD")
    parser.add_argument("--end", default=datetime.now().strftime("%Y%m%d"), help="YYYYMMDD")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--force-supplement", action="store_true", help="忽略24小时补数缓存，强制通过KH补数")
    args = parser.parse_args()
    if args.start > args.end:
        raise SystemExit("--start must not be later than --end")

    ensure_data, read_daily = _load_kh_loader()
    ensured = ensure_data(args.index_code, args.start, args.end, "1d", force_supplement=args.force_supplement)
    daily = read_daily(args.index_code, args.start, args.end)
    if daily.empty:
        raise SystemExit("KH 本地数据库在请求区间没有日线数据。")
    daily = daily.rename(columns={"volume": "vol"})
    weekly = aggregate_weekly(daily)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.index_code.replace("/", "_")
    daily_path = output_dir / f"{prefix}_daily.csv"
    weekly_path = output_dir / f"{prefix}_weekly.csv"
    daily.to_csv(daily_path, index=False)
    weekly.to_csv(weekly_path, index=False)
    metadata = {
        "source": "kh_local.duckdb",
        "index_code": ensured.code,
        "start": args.start,
        "end": args.end,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "daily_rows": len(daily),
        "weekly_rows": len(weekly),
        "daily_file": str(daily_path),
        "weekly_file": str(weekly_path),
        "kh_db_path": ensured.db_path,
        "coverage_before": ensured.coverage_before.to_dict(),
        "coverage_after": ensured.coverage_after.to_dict(),
        "supplemented": ensured.supplemented,
        "supplement_attempted": ensured.supplement_attempted,
        "supplement_skipped_by_cache": ensured.supplement_skipped_by_cache,
        "supplement_source": ensured.supplement_source,
        "future_rows_filtered": True,
        "cache_manifest": str(Path(os.environ.get("KH_SKILL_CACHE", str(Path.home() / ".cache" / "khquant" / "skill_data_manifest.json"))).expanduser()),
    }
    (output_dir / f"{prefix}_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
