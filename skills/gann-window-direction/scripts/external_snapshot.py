#!/usr/bin/env python3
"""Build a point-in-time external-market snapshot.

The script records only observations that were available by ``--cutoff``.
Historical US/Europe/gold data use confirmed prior closes. Historical Asia
intraday data use the provider's minute series only when its session date
matches the cutoff date; otherwise the field is explicitly unavailable.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, time
from pathlib import Path

import akshare as ak
import pandas as pd
import requests

from common import RULESET_VERSION, TZ, atomic_write_json, parse_cutoff

US_ANCHORS = {
    "IXIC": ("纳斯达克综合", "整体风险偏好", ".IXIC"),
    "NDX": ("纳斯达克100", "成长风格", ".NDX"),
    "SPX": ("标普500", "整体风险偏好", ".INX"),
    "DJI": ("道琼斯", "价值与权重", ".DJI"),
    "SOX": ("费城半导体", "AI 算力/半导体链", ".SOX"),
}
EUROPE_ANCHORS = {
    "FTSE": ("英国富时100", "英国富时100指数", "FTSE"),
    "GDAXI": ("德国DAX", "德国DAX 30种股价指数", "GDAXI"),
    "FCHI": ("法国CAC40", "法CAC40指数", "FCHI"),
    "SX5E": ("欧洲斯托克50", "欧洲Stoxx50指数", "CSX5P"),
}
ASIA_MARKETS = {
    "N225": ("日经225", "NKY", time(8, 0)),
    "KS11": ("韩国KOSPI", "KOSPI", time(8, 0)),
    "AS51": ("澳大利亚标普200", "AS51", time(7, 0)),
    "TWII": ("台湾加权", "TWJQ", time(9, 0)),
    "HSI": ("恒生指数", "HSI", time(9, 30)),
}
SEMI_HEAVY_ASIA = ("N225", "KS11", "TWII")


def gap_register(gaps: list[dict], field: str, status: str, reason: str, attempted: bool) -> None:
    gaps.append(
        {
            "field": field,
            "status": status,
            "fallback_attempted": attempted,
            "reason": reason,
        }
    )


def fetch_tushare_globals(cutoff: datetime, gaps: list[dict]) -> pd.DataFrame | None:
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        gap_register(
            gaps,
            "external.tushare_primary",
            "missing",
            "TUSHARE_TOKEN 未设置；使用 AkShare fallback",
            False,
        )
        return None
    try:
        import tushare as ts

        pro = ts.pro_api(token)
        start = (cutoff.date() - pd.Timedelta(days=14)).strftime("%Y%m%d")
        end = cutoff.date().strftime("%Y%m%d")
        frame = pro.index_global(start_date=start, end_date=end)
        if frame is None or frame.empty:
            raise ValueError("Tushare index_global 返回空表")
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], format="%Y%m%d", errors="coerce")
        return frame
    except Exception as error:  # noqa: BLE001
        gap_register(
            gaps,
            "external.tushare_primary",
            "provider_error",
            f"{type(error).__name__}: {error}",
            True,
        )
        return None


def tushare_rows(global_frame: pd.DataFrame | None, code: str, available_day) -> pd.DataFrame:
    if global_frame is None:
        return pd.DataFrame()
    frame = global_frame[global_frame["ts_code"] == code].copy()
    return frame[frame["trade_date"] <= pd.Timestamp(available_day)].sort_values("trade_date")


def fetch_us_anchors(cutoff: datetime, gaps: list[dict], global_frame: pd.DataFrame | None) -> dict:
    """Fetch the last US session whose official close was available by cutoff."""
    available_day = cutoff.date()
    if cutoff.time() < time(5, 0):
        available_day -= pd.Timedelta(days=1)
    frame_date = pd.Timestamp(available_day)
    result: dict = {}
    for code, (name, chain, source_symbol) in US_ANCHORS.items():
        primary = tushare_rows(global_frame, code, frame_date)
        selected_primary = False
        while len(primary) >= 2:
            last, previous = primary.iloc[-1], primary.iloc[-2]
            available_at = (last["trade_date"] + pd.Timedelta(days=1)).replace(hour=5, minute=0).tz_localize(TZ)
            if available_at <= cutoff:
                result[code] = {
                    "name": name,
                    "chain": chain,
                    "trade_date": last["trade_date"].strftime("%Y-%m-%d"),
                    "close": float(last["close"]),
                    "pct_chg": round(float(last["pct_chg"]), 4),
                    "source": "tushare.index_global",
                    "available_at": available_at.isoformat(timespec="seconds"),
                    "availability_basis": "exchange_close_plus_conservative_buffer",
                    "data_quality": "primary_structured_close",
                }
                selected_primary = True
                break
            primary = primary.iloc[:-1]
        if selected_primary:
            continue
        try:
            raw = ak.index_us_stock_sina(symbol=source_symbol)
            raw["date"] = pd.to_datetime(raw["date"], errors="coerce").dt.normalize()
            raw = raw[raw["date"] <= frame_date].dropna(subset=["date"]).sort_values("date")
            if len(raw) < 2:
                raise ValueError("不足两根可用日线")
            last, previous = raw.iloc[-1], raw.iloc[-2]
            available_at = (last["date"] + pd.Timedelta(days=1)).replace(hour=5, minute=0).tz_localize(TZ)
            if available_at > cutoff:
                raw = raw.iloc[:-1]
                if len(raw) < 2:
                    raise ValueError("截点前没有完整两根日线")
                last, previous = raw.iloc[-1], raw.iloc[-2]
                available_at = (last["date"] + pd.Timedelta(days=1)).replace(hour=5, minute=0).tz_localize(TZ)
            result[code] = {
                "name": name,
                "chain": chain,
                "trade_date": last["date"].strftime("%Y-%m-%d"),
                "close": float(last["close"]),
                "pct_chg": round(float(last["close"] / previous["close"] - 1) * 100, 4),
                "source": "akshare.index_us_stock_sina",
                "available_at": available_at.isoformat(timespec="seconds"),
                "availability_basis": "exchange_close_plus_conservative_buffer",
                "used_fallback": True,
                "fallback_reason": "Tushare returned no eligible two-session history for this code",
                "data_quality": "official_session_close_proxy",
            }
            gap_register(
                gaps,
                f"external.{code}",
                "ok_with_fallback",
                "使用 AkShare 新浪日线适配器；未伪造未执行的 Tushare 主源查询",
                True,
            )
        except Exception as error:  # noqa: BLE001
            gap_register(gaps, f"external.{code}", "missing", f"{type(error).__name__}: {error}", True)
    return result


def fetch_europe(cutoff: datetime, gaps: list[dict], global_frame: pd.DataFrame | None) -> dict:
    result: dict = {}
    available_day = cutoff.date()
    if cutoff.time() < time(0, 30):
        available_day -= pd.Timedelta(days=1)
    for code, (name, ak_name, tushare_code) in EUROPE_ANCHORS.items():
        primary = tushare_rows(global_frame, tushare_code, available_day)
        selected_primary = False
        while len(primary) >= 2:
            last, previous = primary.iloc[-1], primary.iloc[-2]
            available_at = (last["trade_date"] + pd.Timedelta(days=1)).replace(hour=0, minute=30).tz_localize(TZ)
            if available_at <= cutoff:
                result[code] = {
                    "name": name,
                    "trade_date": last["trade_date"].strftime("%Y-%m-%d"),
                    "close": float(last["close"]),
                    "pct_chg": round(float(last["pct_chg"]), 4),
                    "source": "tushare.index_global",
                    "available_at": available_at.isoformat(timespec="seconds"),
                    "availability_basis": "exchange_close_plus_conservative_buffer",
                    "data_quality": "primary_structured_close",
                }
                selected_primary = True
                break
            primary = primary.iloc[:-1]
        if selected_primary:
            continue
        try:
            raw = ak.index_global_hist_sina(symbol=ak_name)
            raw["date"] = pd.to_datetime(raw["date"], errors="coerce").dt.normalize()
            raw = raw[raw["date"] <= pd.Timestamp(available_day)].dropna(subset=["date"]).sort_values("date")
            if len(raw) < 2:
                raise ValueError("不足两根可用日线")
            last, previous = raw.iloc[-1], raw.iloc[-2]
            available_at = (last["date"] + pd.Timedelta(days=1)).replace(hour=0, minute=30).tz_localize(TZ)
            if available_at > cutoff:
                last, previous = raw.iloc[-2], raw.iloc[-3]
                available_at = (last["date"] + pd.Timedelta(days=1)).replace(hour=0, minute=30).tz_localize(TZ)
            result[code] = {
                "name": name,
                "trade_date": last["date"].strftime("%Y-%m-%d"),
                "close": float(last["close"]),
                "pct_chg": round(float(last["close"] / previous["close"] - 1) * 100, 4),
                "source": "akshare.index_global_hist_sina",
                "available_at": available_at.isoformat(timespec="seconds"),
                "availability_basis": "exchange_close_plus_conservative_buffer",
                "data_quality": "prior_session_close",
            }
        except Exception as error:  # noqa: BLE001
            gap_register(gaps, f"external.{code}", "missing", f"{type(error).__name__}: {error}", True)
    return result


def fetch_asia_minute(code: str, name: str, symbol: str, open_time: time, cutoff: datetime, gaps: list[dict]) -> dict | None:
    if cutoff.time() < open_time:
        gap_register(gaps, f"external.{code}", "not_yet_open", f"{name}尚未开盘", False)
        return None
    try:
        response = requests.get(
            "https://gi.finance.sina.com.cn/hq/min",
            params={"symbol": symbol},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"},
            timeout=20,
        )
        response.raise_for_status()
        rows = response.json().get("result", {}).get("data") or []
        if not rows:
            raise ValueError("分钟序列为空")
        session_date = str(rows[0][4]) if len(rows[0]) > 4 else "unknown"
        if session_date != cutoff.date().isoformat():
            raise ValueError(f"最新分钟会话为 {session_date}，不能用于 {cutoff.date()}")
        cutoff_text = cutoff.strftime("%H:%M")
        eligible = [row for row in rows if str(row[0]) <= cutoff_text]
        if not eligible:
            raise ValueError("截点前没有分钟数据")
        selected = eligible[-1]
        previous_close = float(rows[0][5]) if len(rows[0]) > 5 else None
        price = float(selected[1])
        result = {
            "name": name,
            "trade_date": session_date,
            "snapshot_time": f"{cutoff.date()} {selected[0]}:00+08:00",
            "price_at_cutoff": price,
            "source": "gi.finance.sina.com.cn/hq/min",
            "available_at": f"{cutoff.date()} {selected[0]}:00+08:00",
            "availability_basis": "provider_minute_bar",
            "usage": "cutoff_snapshot_only",
            "data_quality": "minute_bar_at_cutoff",
        }
        if previous_close and previous_close > 0:
            result["prev_close"] = previous_close
            result["pct_chg"] = round((price / previous_close - 1) * 100, 4)
        return result
    except Exception as error:  # noqa: BLE001
        gap_register(gaps, f"external.{code}", "provider_error", f"{type(error).__name__}: {error}", True)
        return None


def fetch_gold(cutoff: datetime, gaps: list[dict]) -> dict:
    result: dict = {}
    asof_day = cutoff.date()
    for code, name, loader, source in (
        ("sge_au9999", "上海金 Au99.99", lambda: ak.spot_hist_sge(symbol="Au99.99"), "akshare.spot_hist_sge"),
        ("comex_gc", "COMEX 黄金", lambda: ak.futures_foreign_hist(symbol="GC"), "akshare.futures_foreign_hist"),
    ):
        try:
            raw = loader()
            date_column = next((column for column in ("date", "日期") if column in raw.columns), None)
            close_column = next((column for column in ("close", "收盘") if column in raw.columns), None)
            if date_column is None or close_column is None:
                raise ValueError("黄金数据缺少 date/close 列")
            raw["date"] = pd.to_datetime(raw[date_column], errors="coerce").dt.normalize()
            raw = raw[raw["date"] <= pd.Timestamp(asof_day)].dropna(subset=["date"]).sort_values("date")
            if len(raw) < 2:
                raise ValueError("黄金可用样本不足")
            last, previous = raw.iloc[-1], raw.iloc[-2]
            available_at = (last["date"] + pd.Timedelta(days=1)).replace(hour=6, minute=0).tz_localize(TZ)
            if available_at > cutoff:
                last, previous = raw.iloc[-2], raw.iloc[-3]
                available_at = (last["date"] + pd.Timedelta(days=1)).replace(hour=6, minute=0).tz_localize(TZ)
            result[code] = {
                "name": name,
                "trade_date": last["date"].strftime("%Y-%m-%d"),
                "close": float(last[close_column]),
                "pct_chg": round(float(last[close_column] / previous[close_column] - 1) * 100, 4),
                "source": source,
                "available_at": available_at.isoformat(timespec="seconds"),
                "availability_basis": "exchange_close_plus_conservative_buffer",
                "data_quality": "prior_session_close",
            }
        except Exception as error:  # noqa: BLE001
            gap_register(gaps, f"gold.{code}", "missing", f"{type(error).__name__}: {error}", True)
    return result


def fetch_a50_proxy(cutoff: datetime, gaps: list[dict], global_frame: pd.DataFrame | None) -> dict:
    """Use only a completed prior close or the already-observed session open."""
    primary = tushare_rows(global_frame, "XIN9", cutoff.date())
    if len(primary) >= 2:
        last, previous = primary.iloc[-1], primary.iloc[-2]
        if last["trade_date"].date() == cutoff.date() and cutoff.time() >= time(9, 0):
            price = float(last["open"])
            usage = "opening_price_only"
            available_at = f"{cutoff.date()} 09:00:00+08:00"
            quality = "primary_open_field"
        else:
            price = float(last["close"])
            usage = "prior_close_only"
            available_at = (last["trade_date"] + pd.Timedelta(days=1)).replace(hour=6).tz_localize(TZ).isoformat()
            quality = "primary_structured_close"
        return {
            "name": "富时中国A50",
            "trade_date": last["trade_date"].strftime("%Y-%m-%d"),
            "price": price,
            "pct_chg": round(float(price / previous["close"] - 1) * 100, 4),
            "source": "tushare.index_global",
            "available_at": available_at,
            "usage": usage,
            "data_quality": quality,
        }
    try:
        raw = ak.futures_foreign_hist(symbol="CHA50CFD")
        date_column = next((column for column in ("date", "日期") if column in raw.columns), None)
        if date_column is None:
            raise ValueError("A50 数据缺少 date 列")
        raw["date"] = pd.to_datetime(raw[date_column], errors="coerce").dt.normalize()
        raw = raw[raw["date"] <= pd.Timestamp(cutoff.date())].dropna(subset=["date"]).sort_values("date")
        if len(raw) < 2:
            raise ValueError("A50 可用样本不足")
        last, previous = raw.iloc[-1], raw.iloc[-2]
        if last["date"].date() == cutoff.date() and cutoff.time() >= time(9, 0):
            price = float(last["open"])
            usage = "opening_price_only"
            available_at = f"{cutoff.date()} 09:00:00+08:00"
            quality = "no_0900_live_price_proxy"
        else:
            price = float(last["close"])
            usage = "prior_close_only"
            available_at = (last["date"] + pd.Timedelta(days=1)).replace(hour=6, minute=0).tz_localize(TZ).isoformat()
            quality = "prior_session_close"
        return {
            "name": "富时中国A50期货",
            "trade_date": last["date"].strftime("%Y-%m-%d"),
            "price": price,
            "pct_chg": round(float(price / previous["close"] - 1) * 100, 4),
            "source": "akshare.futures_foreign_hist:CHA50CFD",
            "available_at": available_at,
            "usage": usage,
            "data_quality": quality,
        }
    except Exception as error:  # noqa: BLE001
        gap_register(gaps, "external.XIN9", "missing", f"{type(error).__name__}: {error}", True)
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Point-in-time external market snapshot")
    parser.add_argument("--cutoff", required=True, help='"YYYY-MM-DD HH:MM:SS+08:00"')
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    cutoff = parse_cutoff(args.cutoff)
    gaps: list[dict] = []
    global_frame = fetch_tushare_globals(cutoff, gaps)
    us = fetch_us_anchors(cutoff, gaps, global_frame)
    europe = fetch_europe(cutoff, gaps, global_frame)
    asia = {
        code: value
        for code, name, symbol, open_time in (
            (code, *definition) for code, definition in ASIA_MARKETS.items()
        )
        if (value := fetch_asia_minute(code, name, symbol, open_time, cutoff, gaps)) is not None
    }
    gold = fetch_gold(cutoff, gaps)
    a50 = fetch_a50_proxy(cutoff, gaps, global_frame)

    flags: dict = {}
    if "SOX" in us and "IXIC" in us:
        flags["us_semis_vs_broad_divergence"] = bool(us["SOX"]["pct_chg"] < 0 and us["IXIC"]["pct_chg"] >= 0)
        flags["sox_pct_chg"] = us["SOX"]["pct_chg"]
    live_semi = [
        row["pct_chg"]
        for code in SEMI_HEAVY_ASIA
        if (row := asia.get(code)) and "pct_chg" in row
    ]
    if live_semi:
        flags["asia_semis_live_mean_pct"] = round(sum(live_semi) / len(live_semi), 4)
    if flags.get("sox_pct_chg") is not None and live_semi:
        flags["semi_chain_state"] = (
            "same_direction_weak"
            if flags["sox_pct_chg"] < 0 and flags["asia_semis_live_mean_pct"] < 0
            else "mixed"
        )

    result = {
        "ruleset_version": RULESET_VERSION,
        "cutoff": cutoff.isoformat(timespec="seconds"),
        "external_market": {
            **us,
            **europe,
            **asia,
            **({"XIN9": a50} if a50 else {}),
        },
        "us_anchors_last_close": us,
        "europe_prior_close": europe,
        "asia_live_snapshot": asia,
        "gold": gold,
        "china_proxy": a50,
        "derived_flags": flags,
        "data_gap_register": gaps,
        "missing_us_anchors": [code for code in US_ANCHORS if code not in us],
        "source_policy": [
            "only observations available by cutoff",
            "US/Europe use completed prior sessions",
            "Asia uses minute data at or before cutoff",
            "non-live sessions use conservative exchange-close availability buffers",
        ],
    }
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output / "external_snapshot.json", result)
    print(
        json.dumps(
            {
                "cutoff": result["cutoff"],
                "us": {code: row["pct_chg"] for code, row in us.items()},
                "europe": {code: row["pct_chg"] for code, row in europe.items()},
                "asia": {
                    code: {
                        "pct_chg": row.get("pct_chg"),
                        "snapshot_time": row.get("snapshot_time"),
                    }
                    for code, row in asia.items()
                },
                "gold": {code: row["pct_chg"] for code, row in gold.items()},
                "china_proxy": a50,
                "gaps": len(gaps),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
