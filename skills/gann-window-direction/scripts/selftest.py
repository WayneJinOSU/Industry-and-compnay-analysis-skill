#!/usr/bin/env python3
"""Minimal regression tests for contracts that previously failed silently."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import common
import direction_gate
import execution_overlay
import scorecard

SCRIPT_DIR = Path(__file__).resolve().parent
VALID_EXECUTION_REPORT = """
执行风险事实
覆盖失效
操作建议理由
动作维持条件
动作解除条件
"""


def valid_close_bins() -> list[dict]:
    return [
        {"name": "tail_extreme_down", "direction": "bearish", "lower": 0.0, "upper": 3400.0, "close_condition": "收盘低于3400"},
        {"name": "downside_continuation", "direction": "bearish", "lower": 3400.0, "upper": 3600.0, "close_condition": "收盘低于3600"},
        {"name": "range_oscillation", "direction": "neutral", "lower": 3600.0, "upper": 3700.0, "close_condition": "收盘位于区间"},
        {"name": "upside_breakout", "direction": "bullish", "lower": 3700.0, "upper": 5000.0, "close_condition": "收盘高于3700"},
    ]


def valid_level_context() -> dict:
    anchors = [3300.0, 3400.0, 3500.0, 3550.0, 3600.0, 3650.0, 3700.0, 3750.0, 3800.0, 5000.0]
    return {
        "ruleset_version": common.RULESET_VERSION,
        "target_date": "2026-10-23",
        "data_asof": "2026-10-22",
        "available_at": "2026-10-22T18:00:00+08:00",
        "source": "测试关键位",
        "data_quality": "complete",
        "previous_close": 3650.0,
        "atr14": 50.0,
        "atr_method": "wilder_14",
        "decision_band": {
            "support_defense": 3600.0,
            "pressure_defense": 3700.0,
            "width_atr": 2.0,
            "range_quality": "wide",
        },
        "price_anchors": [
            {"anchor_id": f"test_{int(price)}", "price": price, "source": "测试", "role": "测试锚"}
            for price in anchors
        ],
        "close_bins": valid_close_bins(),
    }


def valid_next_day_path() -> dict:
    switch = lambda trigger, lower, upper: {
        "trigger": f"观察{trigger}的接受或失守",
        "trigger_level": trigger,
        "close_lower": lower,
        "close_upper": upper,
        "invalidation": "触发后重新回原区间",
    }
    return {
        "baseline_summary": "区间内偏弱，优先观察下沿测试",
        "opening": {"lower": 3650.0, "upper": 3700.0, "reference_level": 3650.0, "expectation": "平开至小幅高开但强度有限"},
        "intraday": {
            "lower": 3550.0,
            "upper": 3750.0,
            "ordered_steps": [
                {"action": "测试支撑", "level": 3600.0, "observation": "观察承接与反抽"},
                {"action": "观察压力", "level": 3700.0, "observation": "观察是否接受"},
            ],
            "acceptance_or_rejection": "以3600和3700的收盘接受情况确认",
        },
        "close": {"lower": 3600.0, "upper": 3700.0, "location": "lower_edge", "character": "weak"},
        "upside_switch": switch(3700.0, 3700.0, 3800.0),
        "downside_switch": switch(3600.0, 3400.0, 3600.0),
        "tail_risk": switch(3400.0, 3300.0, 3400.0),
    }


def valid_judgement() -> dict:
    return {
        "source": "llm",
        "target_date": "2026-10-23",
        "decision_at": "2026-10-23T08:55:00+08:00",
        "core_thesis": "周线结构偏空，次日仅作区间内弱势推演",
        "structural_bias": "bearish",
        "structure_reason": ["周线反弹未延续", "压力尚未接受"],
        "structure_opposition": ["外盘短线修复"],
        "structure_invalidation": ["周线收盘站稳3700"],
        "window_state": "unresolved",
        "next_day_path": valid_next_day_path(),
        "baseline_path_invalidation": ["开盘并持续接受3700上方"],
        "execution_state": "reduce_only",
        "execution_action": "reduce_only",
        "risk_state": "preemptive_defensive",
        "abstain": False,
        "supporting_evidence": ["支撑附近弱收盘", "外围风险冲击"],
        "opposing_evidence": ["短线出现反弹"],
        "action_maintenance": ["压力仍未接受"],
        "action_invalidation": ["收盘接受3700上方"],
        "evidence_refs": ["structure_memory.close", "external_market.SOX"],
        "horizon": "目标交易日",
        "next_review": "下一交易日收盘",
    }


def valid_forecast(pack: dict, judgement: dict) -> dict:
    path = judgement["next_day_path"]
    context = pack["level_context"]
    return {
        "target_date": pack["target_date"],
        "prediction_type": pack["prediction_type"],
        "decision_stage": pack["decision_stage"],
        "ruleset_version": pack["ruleset_version"],
        "forecast_cutoff": pack["forecast_cutoff"],
        "feature_cutoff": pack["feature_cutoff"],
        "symbol": pack["symbol"],
        "structural_bias": judgement["structural_bias"],
        "window_state": judgement["window_state"],
        "next_day_baseline": path["baseline_summary"],
        "opening_zone": path["opening"],
        "intraday_zone": path["intraday"],
        "close_zone": path["close"],
        "close_character": path["close"]["character"],
        "next_day_path": path,
        "structure_invalidation": judgement["structure_invalidation"],
        "baseline_path_invalidation": judgement["baseline_path_invalidation"],
        "execution_state": judgement["execution_state"],
        "action_bias": judgement["execution_action"],
        "abstain": judgement["abstain"],
        "close_axis": "close",
        "interval_convention": "lower_inclusive_upper_exclusive",
        "close_bins": context["close_bins"],
        "level_context": context,
        "execution_overlay": pack["execution_overlay"],
        "llm_judgement": judgement,
        "judgement_source": "llm",
    }


def valid_path_pack() -> dict:
    pack = overlay_pack("premarket")
    pack.update({
        "prediction_type": "prospective",
        "ruleset_version": common.RULESET_VERSION,
        "symbol": "000001.SH",
        "structure_memory": {"close": 3650.0, "atr14": 50.0, "atr_method": "wilder_14"},
        "space_levels": {"level_registry_summary": {"close": 3650.0, "atr14": 50.0, "atr_method": "wilder_14"}},
        "external_market": {"SOX": {"pct_chg": -4.3}},
        "level_context": valid_level_context(),
    })
    pack["execution_overlay"] = execution_overlay.build_overlay(
        pack, None, pressure_low=3650.0, pressure_high=3700.0, support=3600.0,
    )
    return pack


def valid_path_report() -> str:
    return f"""
| 项目 | 内容 |
|---|---|
| 预测类型 | 前瞻预测 |
| 规则版本 | {common.RULESET_VERSION} |
| 决策阶段 | 盘前 |
| 预判截点 | 2026-10-23 09:00:00+08:00 |
| 特征截点 | 2026-10-23 09:00:00+08:00 |
| 目标日期 | 2026-10-23 |
| 门禁状态 | 通过 |
| 结构偏向 | 看空 |
| 窗口状态 | 未决 |
| 次日基准 | 区间内偏弱，优先观察下沿测试 |
| 开盘点位 | 3650.00-3700.00 |
| 盘中波动点位 | 3550.00-3750.00 |
| 收盘点位 | 3600.00-3700.00 |
| 收盘性质 | 偏弱 |
| 执行状态 | 只减不加 |
| 操作偏向 | 只减不加 |
| 是否弃权 | 否 |
| 结构失效条件 | 周线收盘站稳3700 |
| 基准路径失效 | 开盘并持续接受3700上方 |

向上切换：接受3700。向下切换：失守3600。尾部风险：失守3400后波动放大。
"""


def overlay_pack(stage: str = "preopen_0925") -> dict:
    cutoff = "2026-10-23T09:25:00+08:00" if stage == "preopen_0925" else "2026-10-23T09:00:00+08:00"
    return {
        "decision_stage": stage,
        "target_date": "2026-10-23",
        "forecast_cutoff": cutoff,
        "feature_cutoff": cutoff,
        "state_inputs": {
            "data_asof": "2026-10-22",
            "available_at": "2026-10-22T18:00:00+08:00",
        },
    }


def premarket_foresight_pack() -> dict:
    pack = overlay_pack("premarket")
    pack.update(
        {
            "space_levels": {
                "level_registry_summary": {"close": 3949.91, "atr14": 43.1}
            },
            "recent_5d_raw": [
                {"close": 3864.28},
                {"close": 3891.60},
                {"close": 3875.60},
                {"close": 3911.87},
                {"close": 3949.91},
            ],
            "external_market": {
                "IXIC": {"pct_chg": 2.26},
                "NDX": {"pct_chg": 2.83},
                "SOX": {"pct_chg": 4.29},
                "KS11": {"pct_chg": 2.2},
                "TWII": {"pct_chg": 0.55},
            },
            "information_content": {"volume": "weak", "leadership": "uninformative"},
            "leadership": {"state": "uninformative"},
            "structure_memory": {
                "recent_path_pressure": {
                    "status": "not_met",
                    "subtype": "none",
                    "detail": "测试状态没有破位未收复或支撑附近弱收盘",
                }
            },
            "gann_result": {
                "target_time_window": {
                    "status": "inside_active_natural_window",
                    "active_window": "2026-10-19/2026-10-23",
                }
            },
            "target_date": "2026-10-23",
        }
    )
    return pack


def auction_snapshot(**updates: object) -> dict:
    snapshot = {
        "data_asof": "2026-10-23",
        "available_at": "2026-10-23T09:25:00+08:00",
        "source": "test auction",
        "data_quality": "final_call_auction",
        "prev_close": 3658.0,
        "open": 3695.0,
        "price": 3695.0,
        "session_high": 3702.0,
        "advance_ratio": 0.40,
        "leader_relative_strength": -0.01,
        "same_time_amount_ratio": 0.85,
    }
    snapshot.update(updates)
    return snapshot


class ContractTests(unittest.TestCase):
    def test_filter_asof_removes_future_rows(self) -> None:
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-10-21", "2026-10-22", "2026-10-23"]),
                "close": [1.0, 2.0, 3.0],
            }
        )
        filtered = common.filter_asof(frame, "2026-10-22")
        self.assertEqual(filtered["date"].max(), pd.Timestamp("2026-10-22"))
        self.assertEqual(len(filtered), 2)

    def test_available_at_is_machine_checked(self) -> None:
        cutoff = common.parse_cutoff("2026-10-23T09:00:00+08:00")
        before = common.parse_available_at("2026-10-23 08:00:00+08:00")
        after = common.parse_available_at("2026-10-23 10:00:00+08:00")
        self.assertIsNotNone(before)
        self.assertIsNotNone(after)
        self.assertLessEqual(before, cutoff)
        self.assertGreater(after, cutoff)

    def test_compact_numeric_dates_are_not_epoch_nanoseconds(self) -> None:
        frame = pd.DataFrame({"trade_date": [20261021, 20261022], "value": [1, 2]})
        filtered = common.filter_asof(frame, "2026-10-22")
        self.assertEqual(filtered["date"].tolist(), [pd.Timestamp("2026-10-21"), pd.Timestamp("2026-10-22")])

    def test_chinese_report_header_and_decision_card_are_gate_compatible(self) -> None:
        report = valid_path_report()
        pack = {
            "prediction_type": "prospective",
            "target_date": "2026-10-23",
            "ruleset_version": common.RULESET_VERSION,
        }
        checks: list[dict] = []
        direction_gate.check_report_header(report, pack, checks)
        self.assertEqual(checks[-1]["status"], "pass")
        self.assertEqual(direction_gate.report_value(report, "prediction_type"), "prospective")
        self.assertEqual(direction_gate.report_value(report, "structural_bias"), "bearish")
        self.assertEqual(direction_gate.report_value(report, "gate_status"), "passed")

    def test_chinese_execution_overlay_display_values_are_normalized(self) -> None:
        self.assertEqual(common.normalize_report_value("pressure_state", "尚未测试"), "untested")
        self.assertEqual(common.normalize_report_value("risk_state", "提前防守（盘前）"), "preemptive_defensive")
        self.assertEqual(common.normalize_report_value("risk_state", "观察"), "watch")
        self.assertEqual(common.normalize_report_value("execution_state", "观察"), "observe")
        self.assertEqual(common.normalize_report_value("action_bias", "停止操作"), "stop")
        self.assertEqual(common.normalize_report_value("structural_bias", "看空"), "bearish")

    def test_chinese_information_and_leadership_tables_are_gate_compatible(self) -> None:
        report = """
| 证据层 | 信息量 |
|---|---|
| 外围市场 | 有效信息 |
| 成交额 | 有效信息 |
| 两融 | 有效信息 |
| 市场宽度 | 有效信息 |
| 领涨结构 | 有效信息 |
| 前序路径 | 有效信息 |
| 事件账本 | 有效信息 |

| 领涨指标 | 当前读数 |
|---|---|
| 领涨篮子收益 | 1.2% |
| 市场等权收益 | 1.0% |
| 领涨超额 | 0.2% |
| 高开回落率 | 0.20 |
| 篮子成员站上均线比例 | 0.70 |
| 反弹质量 | 不明确 |

反弹质量仍需下一交易日复核。
"""
        pack = {
            "information_content": {layer: "informative" for layer in common.LAYERS},
            "leadership": {"state": "leadership_neutral", "rebound_quality": "unclear"},
        }
        checks: list[dict] = []
        direction_gate.check_information_content(report, pack, checks)
        direction_gate.check_leadership(report, pack, checks)
        self.assertEqual([row["status"] for row in checks], ["pass", "pass"])

    def test_quantity_values_require_arabic_numerals(self) -> None:
        bad_report = """
| 情景 | 完整路径预测 | 目标 |
|---|---|---|
| 区间震荡 | 9月22日测试三千九百五十八点零三→上涨百分之四点二九→五个完整交易日后回落 | 三千九百九十二点五五 |
"""
        checks: list[dict] = []
        direction_gate.check_numeric_display(bad_report, checks)
        self.assertEqual(checks[-1]["status"], "fail")
        self.assertGreaterEqual(checks[-1]["violation_count"], 3)

        good_report = """
| 情景 | 完整路径预测 | 目标 |
|---|---|---|
| 区间震荡 | 9月22日测试3958.03→上涨4.29%→5个完整交易日后回落 | 3992.55 |

下一交易日复查，同一时点继续观察；第四浪与丙二反弹作为结构名称保留。
"""
        checks = []
        direction_gate.check_numeric_display(good_report, checks)
        self.assertEqual(checks[-1]["status"], "pass")

    def test_human_report_language_gate_rejects_english_words(self) -> None:
        checks: list[dict] = []
        direction_gate.check_language_display("周线状态为down，反弹质量为unclear。", checks)
        self.assertEqual(checks[-1]["status"], "fail")
        checks = []
        direction_gate.check_language_display(
            "周线状态为向下，反弹质量为不明确。", checks
        )
        self.assertEqual(checks[-1]["status"], "pass")

    def test_intraday_available_at_uses_snapshot_cutoff(self) -> None:
        value = common.resolve_available_at(
            "2026-10-23",
            stage="intraday_update",
            forecast_cutoff="2026-10-23T10:00:00+08:00",
        )
        self.assertEqual(value, "2026-10-23T10:00:00+08:00")

    def test_preopen_available_at_uses_0925_cutoff(self) -> None:
        value = common.resolve_available_at(
            "2026-10-23",
            stage="preopen_0925",
            forecast_cutoff="2026-10-23T09:25:00+08:00",
        )
        self.assertEqual(value, "2026-10-23T09:25:00+08:00")

    def test_close_bins_require_explicit_direction(self) -> None:
        bins = valid_close_bins()
        self.assertEqual(common.validate_close_bins(bins), [])
        broken = [dict(row) for row in bins]
        broken[3].pop("direction")
        self.assertTrue(any("direction" in error for error in common.validate_close_bins(broken)))

    def test_close_bins_reject_weights(self) -> None:
        bins = valid_close_bins()
        bins[1]["weight"] = 0.55
        self.assertTrue(any("weight" in error for error in common.validate_close_bins(bins)))

    def test_overlapping_close_bins_are_rejected(self) -> None:
        bins = valid_close_bins()
        bins[1]["lower"] = 3399.0
        self.assertTrue(any("boundary" in error for error in common.validate_close_bins(bins)))

    def test_scorecard_neutral_is_abstention(self) -> None:
        scenarios = [
            {"name": "tail_extreme_down", "direction": "bearish", "weight": 0.05, "lower": 0, "upper": 3500},
            {"name": "downside_continuation", "direction": "bearish", "weight": 0.30, "lower": 3500, "upper": 3602.15},
            {"name": "range_oscillation", "direction": "neutral", "weight": 0.40, "lower": 3602.15, "upper": 3702.44},
            {"name": "upside_breakout", "direction": "bullish", "weight": 0.25, "lower": 3702.44, "upper": 10000},
        ]
        record = {
            "target_date": "2026-10-23",
            "prediction_type": "backfill",
            "direction": "neutral",
            "structural_bias": "bearish",
            "scenarios": scenarios,
            "targets": [],
        }
        closes = pd.Series(
            [3658.0, 3690.0],
            index=pd.to_datetime(["2026-10-22", "2026-10-23"]),
        )
        result = scorecard.settle(record, closes)
        self.assertEqual(result["expected_direction"], "neutral")
        self.assertIsNone(result["direction_hit"])
        self.assertEqual(result["realized_branch"], "range_oscillation")
        self.assertTrue(result["top_weight_hit"])
        self.assertEqual(result["schema"], "legacy_weighted")

    def test_path_scorecard_settles_zones_without_inferring_order(self) -> None:
        pack = valid_path_pack()
        record = valid_forecast(pack, valid_judgement())
        bars = pd.DataFrame(
            {
                "open": [3650.0, 3660.0],
                "high": [3670.0, 3690.0],
                "low": [3640.0, 3580.0],
                "close": [3650.0, 3610.0],
            },
            index=pd.to_datetime(["2026-10-22", "2026-10-23"]),
        )
        result = scorecard.settle(record, bars)
        self.assertEqual(result["schema"], "path_v1")
        self.assertTrue(result["open_zone_hit"])
        self.assertTrue(result["intraday_range_covered"])
        self.assertTrue(result["close_zone_hit"])
        self.assertTrue(result["close_location_hit"])
        self.assertTrue(result["close_character_hit"])
        self.assertTrue(result["fragile_range_coverage"])
        self.assertEqual(result["path_order_status"], "unavailable_from_daily_ohlc")

    def test_scorecard_does_not_infer_direction_from_structural_bias(self) -> None:
        closes = pd.Series(
            [3658.0, 3690.0],
            index=pd.to_datetime(["2026-10-22", "2026-10-23"]),
        )
        record = {
            "target_date": "2026-10-23",
            "prediction_type": "backfill",
            "structural_bias": "bearish",
            "scenarios": [],
            "targets": [],
        }
        result = scorecard.settle(record, closes)
        self.assertIsNone(result["expected_direction"])
        self.assertIsNone(result["direction_hit"])

    def test_future_external_timestamp_fails_gate(self) -> None:
        pack = {
            "target_date": "2026-10-23",
            "forecast_cutoff": "2026-10-23T09:00:00+08:00",
            "feature_cutoff": "2026-10-23T09:00:00+08:00",
            "future_function_audit": {"excluded": ["after cutoff"], "status": "passed"},
            "external_market": {
                "IXIC": {
                    "trade_date": "2026-10-23",
                    "available_at": "2026-10-23T10:00:00+08:00",
                }
            },
        }
        checks: list[dict] = []
        direction_gate.check_future_function("", pack, checks)
        self.assertEqual(checks[-1]["status"], "fail")

    def test_missing_upstream_timestamp_fails_gate(self) -> None:
        pack = {
            "target_date": "2026-10-23",
            "forecast_cutoff": "2026-10-23T09:00:00+08:00",
            "feature_cutoff": "2026-10-23T09:00:00+08:00",
            "future_function_audit": {"excluded": ["after cutoff"], "status": "passed"},
            "gann_result": {"as_of": "2026-10-22"},
            "wave_result": {"latest_data_asof": "2026-10-22"},
            "recent_5d_raw": [],
            "recent_5d_summary": {
                "data_asof": "2026-10-22",
                "available_at": "2026-10-22T18:00:00+08:00",
            },
            "volume_price": {
                "data_asof": "2026-10-22",
                "available_at": "2026-10-22T18:00:00+08:00",
            },
            "margin_financing": {
                "data_asof": "2026-10-22",
                "available_at": "2026-10-23T09:00:00+08:00",
            },
            "leadership": {
                "data_asof": "2026-10-22",
                "available_at": "2026-10-22T18:00:00+08:00",
            },
            "state_inputs": {
                "data_asof": "2026-10-22",
                "available_at": "2026-10-22T18:00:00+08:00",
            },
            "path_memory": {
                "data_asof": "2026-10-22",
                "available_at": "2026-10-22T18:00:00+08:00",
            },
            "breadth_and_sectors": {
                "data_asof": "2026-10-22",
                "available_at": "2026-10-22T18:00:00+08:00",
            },
        }
        checks: list[dict] = []
        direction_gate.check_future_function("", pack, checks)
        self.assertEqual(checks[-1]["status"], "fail")

    def test_forecast_contract_uses_three_stage_path(self) -> None:
        pack = valid_path_pack()
        forecast = valid_forecast(pack, valid_judgement())
        checks: list[dict] = []
        direction_gate.check_forecast_contract(valid_path_report(), pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "pass", checks[-1])

        forecast["direction"] = "bullish"
        checks = []
        direction_gate.check_forecast_contract(valid_path_report(), pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "fail")
        self.assertTrue(any("旧版" in error for error in checks[-1]["errors"]))

    def test_forecast_contract_rejects_report_zone_mismatch(self) -> None:
        pack = valid_path_pack()
        forecast = valid_forecast(pack, valid_judgement())
        report = valid_path_report().replace("3650.00-3700.00", "3600.00-3700.00", 1)
        checks: list[dict] = []
        direction_gate.check_forecast_contract(report, pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "fail")
        self.assertTrue(any("opening_zone" in error for error in checks[-1]["errors"]))

    def test_execution_overlay_records_rejection_without_action(self) -> None:
        pack = overlay_pack()
        overlay = execution_overlay.build_overlay(
            pack, auction_snapshot(price=3680.0),
            pressure_low=3690.0, pressure_high=3700.0, support=3600.0,
        )
        self.assertEqual(overlay["pressure_state"], "rejected")
        self.assertEqual(overlay["participation_state"], "divergent")
        self.assertNotIn("risk_state", overlay)
        self.assertNotIn("execution_bias", overlay)
        pack["execution_overlay"] = overlay
        forecast = {"decision_stage": "preopen_0925", "execution_overlay": overlay}
        checks: list[dict] = []
        direction_gate.check_execution_overlay(VALID_EXECUTION_REPORT, pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "warning")
        self.assertIn("不得把缺失解释为中性", checks[-1]["detail"])

    def test_gap_fade_records_facts_without_defense(self) -> None:
        overlay = execution_overlay.build_overlay(
            overlay_pack(),
            auction_snapshot(
                price=3670.0,
                advance_ratio=0.70,
                leader_relative_strength=0.01,
                same_time_amount_ratio=1.10,
            ),
            pressure_low=3690.0, pressure_high=3700.0, support=3600.0,
        )
        self.assertEqual(overlay["gap_state"], "faded")
        self.assertEqual(overlay["pressure_state"], "rejected")
        self.assertEqual(overlay["participation_state"], "confirming")
        self.assertNotIn("risk_state", overlay)
        self.assertNotIn("execution_bias", overlay)

    def test_execution_overlay_records_acceptance_without_offense(self) -> None:
        overlay = execution_overlay.build_overlay(
            overlay_pack(),
            auction_snapshot(
                price=3705.0,
                session_high=3705.0,
                advance_ratio=0.70,
                leader_relative_strength=0.01,
                same_time_amount_ratio=1.10,
            ),
            pressure_low=3690.0, pressure_high=3700.0, support=3600.0,
        )
        self.assertEqual(overlay["pressure_state"], "accepted")
        self.assertEqual(overlay["participation_state"], "confirming")
        self.assertNotIn("risk_state", overlay)
        self.assertNotIn("execution_bias", overlay)

    def test_missing_setup_inputs_remain_gaps_without_action(self) -> None:
        overlay = execution_overlay.build_overlay(
            overlay_pack(), None,
            pressure_low=3690.0, pressure_high=3700.0, support=3600.0,
        )
        self.assertNotIn("risk_state", overlay)
        self.assertNotIn("execution_bias", overlay)
        self.assertIn("premarket.close", overlay["data_gaps"])
        self.assertEqual(overlay["decision_mode"], "premarket_facts")

    def test_premarket_facts_do_not_generate_score_or_action(self) -> None:
        pack = premarket_foresight_pack()
        pack["critical_evidence"] = {"direction_audit": {"structural_bias": "bearish"}}
        overlay = execution_overlay.build_overlay(
            pack, None,
            pressure_low=3958.03, pressure_high=3992.55, support=3916.49,
        )
        self.assertEqual(overlay["decision_mode"], "premarket_facts")
        self.assertEqual(len(overlay["setup_evidence"]), 5)
        self.assertNotIn(
            "structural_bearish",
            {row["name"] for row in overlay["setup_evidence"]},
        )
        for field in ("setup_state", "risk_state", "execution_bias", "action_rationale"):
            self.assertNotIn(field, overlay)
        self.assertNotIn("setup_score", overlay["metrics"])

    def test_execution_overlay_gate_accepts_premarket_facts(self) -> None:
        pack = premarket_foresight_pack()
        overlay = execution_overlay.build_overlay(
            pack, None,
            pressure_low=3958.03, pressure_high=3992.55, support=3916.49,
        )
        pack["execution_overlay"] = overlay
        forecast = {
            "decision_stage": "premarket",
            "execution_overlay": overlay,
            "target_date": pack["target_date"],
        }
        checks: list[dict] = []
        direction_gate.check_execution_overlay(VALID_EXECUTION_REPORT, pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "pass")

    def test_combined_snapshot_updates_facts_without_action_carryover(self) -> None:
        pack = premarket_foresight_pack()
        quiet_snapshot = auction_snapshot(
            available_at="2026-10-23T09:00:00+08:00",
            prev_close=3658.0,
            open=3658.0,
            price=3660.0,
            session_high=3660.0,
            advance_ratio=0.70,
            leader_relative_strength=0.01,
            same_time_amount_ratio=1.10,
        )
        overlay = execution_overlay.build_overlay(
            pack,
            quiet_snapshot,
            pressure_low=3958.03,
            pressure_high=3992.55,
            support=3916.49,
        )
        self.assertEqual(overlay["pressure_state"], "untested")
        self.assertNotIn("risk_state", overlay)
        self.assertNotIn("execution_bias", overlay)

        accepted_snapshot = auction_snapshot(
            available_at="2026-10-23T09:00:00+08:00",
            prev_close=3950.0,
            open=3985.0,
            price=4000.0,
            session_high=4005.0,
            advance_ratio=0.70,
            leader_relative_strength=0.01,
            same_time_amount_ratio=1.10,
        )
        accepted = execution_overlay.build_overlay(
            pack,
            accepted_snapshot,
            pressure_low=3958.03,
            pressure_high=3992.55,
            support=3916.49,
        )
        self.assertEqual(accepted["pressure_state"], "accepted")
        self.assertEqual(accepted["participation_state"], "confirming")
        self.assertNotIn("risk_state", accepted)
        self.assertNotIn("execution_bias", accepted)

    def test_external_risk_shock_requires_asia_confirmation(self) -> None:
        pack = premarket_foresight_pack()
        pack["external_market"].update(
            {
                "SOX": {"pct_chg": -4.30},
                "IXIC": {"pct_chg": -1.88},
                "NDX": {"pct_chg": -2.02},
                "N225": {"pct_chg": -1.28},
                "KS11": {"pct_chg": -5.59},
                "TWII": {"pct_chg": -0.50},
                "XIN9": {"pct_chg": -0.20},
            }
        )
        pack["structure_memory"]["recent_path_pressure"] = {
            "status": "met",
            "subtype": "weak_close_near_support",
            "detail": "收盘位于日振幅低位并接近支撑防线",
        }
        overlay = execution_overlay.build_overlay(
            pack,
            None,
            pressure_low=3958.03,
            pressure_high=3992.55,
            support=3916.49,
        )
        evidence = next(
            row for row in overlay["setup_evidence"] if row["name"] == "external_extreme"
        )
        self.assertEqual(overlay["metrics"]["external_state"], "risk_off_shock")
        self.assertEqual(evidence["status"], "met")
        self.assertNotIn("risk_state", overlay)

        hard_combo = json.loads(json.dumps(pack))
        hard_combo["gann_result"]["target_time_window"] = {
            "status": "不在已确认关键时间点",
            "active_window": "",
        }
        hard_combo["information_content"] = {
            "volume": "uninformative",
            "leadership": "uninformative",
        }
        hard_combo["leadership"] = {"state": "uninformative"}
        overlay = execution_overlay.build_overlay(
            hard_combo,
            None,
            pressure_low=3400.0,
            pressure_high=3500.0,
            support=3800.0,
        )
        self.assertNotIn("setup_score", overlay["metrics"])
        self.assertNotIn("setup_state", overlay)
        self.assertNotIn("risk_state", overlay)

        unconfirmed = premarket_foresight_pack()
        unconfirmed["external_market"].update(
            {
                "SOX": {"pct_chg": -4.30},
                "IXIC": {"pct_chg": -1.88},
                "N225": {"pct_chg": -1.28},
            }
        )
        overlay = execution_overlay.build_overlay(
            unconfirmed,
            None,
            pressure_low=3958.03,
            pressure_high=3992.55,
            support=3916.49,
        )
        evidence = next(
            row for row in overlay["setup_evidence"] if row["name"] == "external_extreme"
        )
        self.assertEqual(overlay["metrics"]["external_state"], "risk_off_unconfirmed")
        self.assertEqual(evidence["status"], "unknown")

    def test_unknown_setup_evidence_remains_unknown_without_score(self) -> None:
        pack = premarket_foresight_pack()
        pack["information_content"] = {"volume": "uninformative", "leadership": "uninformative"}
        pack["leadership"] = {"state": "uninformative"}
        overlay = execution_overlay.build_overlay(
            pack,
            None,
            pressure_low=3958.03,
            pressure_high=3992.55,
            support=3916.49,
        )
        deficit = next(
            row for row in overlay["setup_evidence"] if row["name"] == "confirmation_deficit"
        )
        self.assertEqual(deficit["status"], "unknown")
        self.assertIsNone(deficit["value"])
        self.assertNotIn("setup_score", overlay["metrics"])
        self.assertNotIn("setup_unknown_checks", overlay["metrics"])
        self.assertIn("premarket.evidence.confirmation_deficit", overlay["data_gaps"])

    def test_structure_memory_tracks_unreclaimed_break(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            dates = pd.date_range("2026-09-01", periods=8, freq="B")
            closes = [101, 100.5, 100.2, 99.2, 98.8, 98.4, 98.1, 97.9]
            bars = pd.DataFrame(
                {
                    "date": dates,
                    "open": [value + 0.3 for value in closes],
                    "high": [value + 0.8 for value in closes],
                    "low": [value - 0.8 for value in closes],
                    "close": closes,
                    "volume": [1000] * len(dates),
                    "amount": [10000] * len(dates),
                }
            )
            bars.to_csv(root / "index.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "level": 100,
                        "role": "support_defense",
                        "source_report": "20260901_report",
                    },
                    {
                        "level": 103,
                        "role": "pressure_defense",
                        "source_report": "20260901_report",
                    },
                ]
            ).to_csv(root / "levels.csv", index=False)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "structure_memory.py"),
                    "--index-daily",
                    str(root / "index.csv"),
                    "--previous-levels",
                    str(root / "levels.csv"),
                    "--target-date",
                    "2026-09-11",
                    "--asof",
                    "2026-09-10",
                    "--available-at",
                    "2026-09-10T18:00:00+08:00",
                    "--output",
                    str(root / "memory.json"),
                ],
                cwd=SCRIPT_DIR,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            memory = json.loads((root / "memory.json").read_text(encoding="utf-8"))
            self.assertEqual(memory["broken_unreclaimed_count"], 1)
            self.assertEqual(memory["supports"][0]["status"], "broken_unreclaimed")
            self.assertEqual(memory["recent_path_pressure"]["status"], "met")
            self.assertEqual(
                memory["recent_path_pressure"]["subtype"], "break_unreclaimed"
            )

    def test_structure_memory_tracks_repeated_pressure_failures(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            dates = pd.date_range("2026-09-01", periods=10, freq="B")
            bars = pd.DataFrame(
                {
                    "date": dates,
                    "open": [100.0] * 7 + [101.0] * 3,
                    "high": [100.5] * 7 + [102.5] * 3,
                    "low": [99.0] * 10,
                    "close": [100.0] * 7 + [101.2] * 3,
                    "volume": [1000] * 10,
                    "amount": [10000] * 7 + [14000] * 3,
                }
            )
            bars.to_csv(root / "index.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "level": 101.5,
                        "role": "pressure_band_anchor",
                        "source_report": "20260901_report",
                        "band_id": "pressure_band_1",
                    },
                    {
                        "level": 103.0,
                        "role": "pressure_defense",
                        "source_report": "20260901_report",
                        "band_id": "pressure_band_1",
                    },
                ]
            ).to_csv(root / "levels.csv", index=False)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "structure_memory.py"),
                    "--index-daily",
                    str(root / "index.csv"),
                    "--previous-levels",
                    str(root / "levels.csv"),
                    "--target-date",
                    "2026-09-16",
                    "--asof",
                    "2026-09-14",
                    "--available-at",
                    "2026-09-14T18:00:00+08:00",
                    "--output",
                    str(root / "memory.json"),
                ],
                cwd=SCRIPT_DIR,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            memory = json.loads((root / "memory.json").read_text(encoding="utf-8"))
            nearest = memory["pressure_attempt_memory"]["nearest"]
            self.assertEqual(nearest["anchor_level"], 101.5)
            self.assertEqual(nearest["defense_level"], 103.0)
            self.assertEqual(nearest["test_count"], 3)
            self.assertEqual(nearest["failed_close_count"], 3)
            self.assertEqual(nearest["consecutive_failed_tests"], 3)
            self.assertEqual(nearest["status"], "repeated_failure")

    def test_level_context_builds_anchors_and_weight_free_bins(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            pack = valid_path_pack()
            pack["scenario_weighting"] = {"weights": {"legacy": 1.0}}
            summary = pack["space_levels"]["level_registry_summary"]
            summary.update({
                "data_asof": "2026-10-22",
                "available_at": "2026-10-22T18:00:00+08:00",
                "same_origin_bands": [
                    {"kind": "支撑带", "defense_level": 3600.0},
                    {"kind": "压力带", "defense_level": 3700.0},
                ],
            })
            (root / "pack.json").write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
            (root / "levels.csv").write_text("level,band_id,role\n3600,support,支撑防线\n3700,pressure,压力防线\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPT_DIR / "level_context.py"),
                    "--pack", str(root / "pack.json"),
                    "--levels", str(root / "levels.csv"),
                    "--output", str(root / "context.json"),
                    "--pack-output", str(root / "pack.final.json"),
                ],
                cwd=SCRIPT_DIR, text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            context = json.loads((root / "context.json").read_text(encoding="utf-8"))
            final_pack = json.loads((root / "pack.final.json").read_text(encoding="utf-8"))
            self.assertEqual(context["decision_band"]["range_quality"], "wide")
            self.assertEqual(common.validate_close_bins(context["close_bins"]), [])
            self.assertTrue(all("weight" not in row for row in context["close_bins"]))
            self.assertNotIn("scenario_weighting", final_pack)
            self.assertIn(3600.0, {row["price"] for row in context["price_anchors"]})

    def test_level_context_rejects_inconsistent_atr(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            pack = valid_path_pack()
            pack["space_levels"]["level_registry_summary"]["same_origin_bands"] = [
                {"kind": "支撑带", "defense_level": 3600.0},
                {"kind": "压力带", "defense_level": 3700.0},
            ]
            pack["space_levels"]["level_registry_summary"]["atr14"] = 55.0
            (root / "pack.json").write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
            (root / "levels.csv").write_text("level\n3600\n3700\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPT_DIR / "level_context.py"),
                    "--pack", str(root / "pack.json"),
                    "--levels", str(root / "levels.csv"),
                    "--output", str(root / "context.json"),
                    "--pack-output", str(root / "pack.final.json"),
                ],
                cwd=SCRIPT_DIR, text=True, capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ATR 不一致", result.stderr)

    def test_level_context_gate_requires_shared_atr(self) -> None:
        pack = valid_path_pack()
        checks: list[dict] = []
        direction_gate.check_level_context(pack, checks)
        self.assertEqual(checks[-1]["status"], "pass", checks[-1])
        pack["structure_memory"]["atr14"] = 55.0
        checks = []
        direction_gate.check_level_context(pack, checks)
        self.assertEqual(checks[-1]["status"], "fail")

    def test_gate_accepts_llm_final_judgement(self) -> None:
        pack = valid_path_pack()
        judgement = valid_judgement()
        pack["llm_judgement"] = judgement
        forecast = valid_forecast(pack, judgement)
        checks: list[dict] = []
        direction_gate.check_llm_judgement(valid_path_report(), pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "pass", checks[-1])

        forecast["next_day_path"] = {}
        checks = []
        direction_gate.check_llm_judgement(valid_path_report(), pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "fail")

    def test_critical_evidence_rejects_second_decision_copy(self) -> None:
        pack = {
            "critical_evidence": {
                "conditional_base_rates": [],
                "unmatched_rates_not_used": [],
                "critical_levels": [
                    {"level": 3600.0, "role": "downside_confirmation"},
                    {"level": 3700.0, "role": "upside_confirmation"},
                ],
            }
        }
        checks: list[dict] = []
        direction_gate.check_critical_evidence("核心交易判断", pack, None, checks)
        self.assertEqual(checks[-1]["status"], "pass", checks[-1])

        pack["critical_evidence"].update({
            "core_thesis": "与唯一研判相反的核心论点",
            "next_day_baseline": "另一份次日基准",
            "structure_path_audit": {"structural_bias": "bullish", "reason": "相反副本"},
        })
        checks = []
        direction_gate.check_critical_evidence("核心交易判断", pack, None, checks)
        self.assertEqual(checks[-1]["status"], "fail")
        self.assertIn("唯一研判来源", checks[-1]["detail"])

    def test_close_location_must_match_decision_band_geometry(self) -> None:
        path = valid_next_day_path()
        path["close"]["location"] = "above_pressure"
        errors = direction_gate.validate_path_forecasts(path, "bearish", valid_level_context())
        self.assertTrue(any("几何关系不一致" in error for error in errors))

        path["close"]["location"] = "lower_edge"
        self.assertEqual(direction_gate.validate_path_forecasts(path, "bearish", valid_level_context()), [])

    def test_execution_overlay_rejects_mismatched_registered_thresholds(self) -> None:
        pack = valid_path_pack()
        judgement = valid_judgement()
        forecast = valid_forecast(pack, judgement)
        overlay = json.loads(json.dumps(pack["execution_overlay"]))
        overlay["thresholds"].update({"pressure_low": 8000.0, "pressure_high": 8100.0, "support": 100.0})
        pack["execution_overlay"] = overlay
        forecast["execution_overlay"] = overlay
        checks: list[dict] = []
        direction_gate.check_execution_overlay(VALID_EXECUTION_REPORT, pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "fail")
        self.assertTrue(any("当前登记锚点" in error for error in checks[-1]["errors"]))
        self.assertTrue(any("support_defense" in error for error in checks[-1]["errors"]))
        self.assertTrue(any("pressure_defense" in error for error in checks[-1]["errors"]))

    def test_structure_path_divergence_is_mandatory(self) -> None:
        pack = valid_path_pack()
        judgement = valid_judgement()
        judgement["next_day_path"]["close"]["character"] = "strong"
        pack["llm_judgement"] = judgement
        forecast = valid_forecast(pack, judgement)
        checks: list[dict] = []
        direction_gate.check_llm_judgement(valid_path_report(), pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "fail")
        self.assertTrue(any("structure_path_divergence" in error for error in checks[-1]["errors"]))

    def test_llm_judgement_validator_builds_forecast(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            pack = valid_path_pack()
            judgement = valid_judgement()
            (root / "pack.json").write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
            (root / "judgement.json").write_text(json.dumps(judgement, ensure_ascii=False), encoding="utf-8")
            validated = subprocess.run(
                [
                    sys.executable, str(SCRIPT_DIR / "validate_llm_judgement.py"),
                    "--pack", str(root / "pack.json"),
                    "--judgement", str(root / "judgement.json"),
                    "--pack-output", str(root / "pack.final.json"),
                ],
                cwd=SCRIPT_DIR, text=True, capture_output=True,
            )
            self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)
            built = subprocess.run(
                [
                    sys.executable, str(SCRIPT_DIR / "build_forecast_from_judgement.py"),
                    "--pack", str(root / "pack.final.json"),
                    "--output", str(root / "forecast.json"),
                ],
                cwd=SCRIPT_DIR, text=True, capture_output=True,
            )
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            forecast = json.loads((root / "forecast.json").read_text(encoding="utf-8"))
            self.assertNotIn("direction", forecast)
            self.assertNotIn("confidence", forecast)
            self.assertEqual(forecast["next_day_path"], judgement["next_day_path"])
            self.assertEqual(forecast["close_bins"], valid_close_bins())
            self.assertEqual(forecast["action_bias"], "reduce_only")
            self.assertEqual(forecast["judgement_source"], "llm")

            judgement["confidence"] = 0.6
            (root / "judgement.json").write_text(json.dumps(judgement, ensure_ascii=False), encoding="utf-8")
            rejected = subprocess.run(
                [
                    sys.executable, str(SCRIPT_DIR / "validate_llm_judgement.py"),
                    "--pack", str(root / "pack.json"),
                    "--judgement", str(root / "judgement.json"),
                    "--pack-output", str(root / "pack.rejected.json"),
                ],
                cwd=SCRIPT_DIR, text=True, capture_output=True,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("confidence", rejected.stdout)

    def test_llm_action_maintenance_and_release_are_separate(self) -> None:
        judgement = valid_judgement()
        self.assertEqual(judgement["action_maintenance"], ["压力仍未接受"])
        self.assertEqual(judgement["action_invalidation"], ["收盘接受3700上方"])
        self.assertNotIn("action_confirmation", judgement)
        self.assertNotIn("action_rationale", judgement)

    def test_gate_requires_execution_condition_content_in_report(self) -> None:
        pack = premarket_foresight_pack()
        overlay = execution_overlay.build_overlay(
            pack,
            None,
            pressure_low=3958.03,
            pressure_high=3992.55,
            support=3916.49,
        )
        pack["execution_overlay"] = overlay
        forecast = {
            "decision_stage": "premarket",
            "execution_overlay": overlay,
            "target_date": pack["target_date"],
        }
        checks: list[dict] = []
        direction_gate.check_execution_overlay("执行风险事实\n操作建议理由", pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "fail")
        self.assertTrue(any("执行条件字段" in error for error in checks[-1]["errors"]))

    def test_snapshot_metadata_is_mandatory(self) -> None:
        snapshot = auction_snapshot()
        snapshot.pop("data_asof")
        with self.assertRaisesRegex(ValueError, "data_asof"):
            execution_overlay.build_overlay(
                overlay_pack(), snapshot,
                pressure_low=3690.0, pressure_high=3700.0, support=3600.0,
            )

    def test_execution_overlay_rejects_pack_forecast_mismatch(self) -> None:
        pack = overlay_pack()
        overlay = execution_overlay.build_overlay(
            pack, auction_snapshot(price=3680.0),
            pressure_low=3690.0, pressure_high=3700.0, support=3600.0,
        )
        pack["execution_overlay"] = overlay
        changed = json.loads(json.dumps(overlay))
        changed["pressure_state"] = "untested"
        forecast = {"decision_stage": "preopen_0925", "execution_overlay": changed}
        checks: list[dict] = []
        direction_gate.check_execution_overlay(VALID_EXECUTION_REPORT, pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "fail")
        self.assertTrue(any("完全一致" in error for error in checks[-1]["errors"]))

    def test_execution_overlay_rejects_missing_fields(self) -> None:
        pack = overlay_pack()
        overlay = execution_overlay.build_overlay(
            pack, auction_snapshot(price=3680.0),
            pressure_low=3690.0, pressure_high=3700.0, support=3600.0,
        )
        overlay.pop("pressure_state")
        pack["execution_overlay"] = overlay
        forecast = {"decision_stage": "preopen_0925", "execution_overlay": overlay}
        checks: list[dict] = []
        direction_gate.check_execution_overlay(VALID_EXECUTION_REPORT, pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "fail")
        self.assertTrue(any("pressure_state" in error for error in checks[-1]["errors"]))

    def test_execution_overlay_rejects_code_action_fields(self) -> None:
        pack = overlay_pack()
        overlay = execution_overlay.build_overlay(
            pack, auction_snapshot(price=3680.0),
            pressure_low=3690.0, pressure_high=3700.0, support=3600.0,
        )
        overlay["risk_state"] = "defensive"
        overlay["execution_bias"] = "reduce_only"
        pack["execution_overlay"] = overlay
        forecast = {"decision_stage": "preopen_0925", "execution_overlay": overlay}
        checks: list[dict] = []
        direction_gate.check_execution_overlay(VALID_EXECUTION_REPORT, pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "fail")
        self.assertTrue(any("裁决字段" in error for error in checks[-1]["errors"]))

    def test_preopen_rejects_target_day_daily_state(self) -> None:
        pack = overlay_pack()
        pack["state_inputs"]["data_asof"] = "2026-10-23"
        overlay = execution_overlay.build_overlay(
            pack, auction_snapshot(price=3680.0),
            pressure_low=3690.0, pressure_high=3700.0, support=3600.0,
        )
        pack["execution_overlay"] = overlay
        forecast = {"decision_stage": "preopen_0925", "execution_overlay": overlay}
        checks: list[dict] = []
        direction_gate.check_execution_overlay("执行覆盖\n操作建议理由", pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "fail")
        self.assertTrue(any("T-1" in error for error in checks[-1]["errors"]))

    def test_path_forecast_requires_complete_registered_chain(self) -> None:
        context = valid_level_context()
        self.assertEqual(direction_gate.validate_path_forecasts(valid_next_day_path(), "bearish", context), [])

        missing = valid_next_day_path()
        missing.pop("opening")
        errors = direction_gate.validate_path_forecasts(missing, "bearish", context)
        self.assertTrue(any("opening" in error for error in errors))

        short = valid_next_day_path()
        short["intraday"]["ordered_steps"] = short["intraday"]["ordered_steps"][:1]
        errors = direction_gate.validate_path_forecasts(short, "bearish", context)
        self.assertTrue(any("ordered_steps" in error for error in errors))

        unregistered = valid_next_day_path()
        unregistered["close"]["lower"] = 3612.34
        errors = direction_gate.validate_path_forecasts(unregistered, "bearish", context)
        self.assertTrue(any("已登记锚点" in error for error in errors))

    def test_chinese_close_bins_allow_weight_free_wording(self) -> None:
        report = """
以下四类仅为无权重收盘结算分箱。
| 类别 | 收盘条件 | 收盘区间 |
|---|---|---:|
| 区间震荡 | 收盘位于区间 | 3600-3700 |
| 向下延续 | 收盘低于支撑 | 3400-3600 |
| 向上突破 | 收盘接受压力 | 3700-5000 |
| 尾部极值（向下） | 收盘低于尾部阈值 | 0-3400 |
"""
        checks: list[dict] = []
        direction_gate.check_close_bin_disclosure(report, checks)
        self.assertEqual(checks[-1]["status"], "pass", checks[-1])

    def test_close_bin_display_rejects_weights_and_confidence(self) -> None:
        report = """
| 类别 | 权重 | 收盘条件 |
|---|---:|---|
| 区间震荡 | 40% | 收盘位于3600-3700 |
| 向下延续 | 30% | 收盘位于3400-3600 |
| 向上突破 | 20% | 收盘位于3700-5000 |
| 尾部极值（向下） | 10% | 收盘位于0-3400 |
置信度：0.6
"""
        checks: list[dict] = []
        direction_gate.check_close_bin_disclosure(report, checks)
        self.assertEqual(checks[-1]["status"], "fail")
        self.assertIn("权重表列", checks[-1]["forbidden_labels"])

    def test_chinese_scenario_headings_are_decidable(self) -> None:
        report = """
### 区间震荡
收盘在3640-3680。
### 向下延续
收盘低于3640，目标3584。
### 向上突破
收盘高于3680，目标3700。
### 尾部极值（向下）
收盘低于3600。
"""
        checks: list[dict] = []
        direction_gate.check_decidable(report, checks)
        self.assertEqual(checks[-1]["status"], "pass")

    def test_compact_scenario_table_is_decidable(self) -> None:
        report = """
| 类别 | 收盘判定 | 完整路径预测 |
|---|---|---|
| 区间震荡 | 收盘位于 `[3640, 3680)` | 低开→测试3640→收回并横盘 |
| 向下延续 | 收盘位于 `[3600, 3640)` | 低开→反抽3640失败→再度下破 |
| 向上突破 | 收盘位于 `[3680, 10000]` | 平开→获得承接→放量突破3680 |
| 尾部极值（向下） | 收盘位于 `[0, 3600)` | 显著低开→支撑无承接→流动性冲击 |
"""
        checks: list[dict] = []
        direction_gate.check_decidable(report, checks)
        self.assertEqual(checks[-1]["status"], "pass")

    def test_audit_appendix_can_hold_review_and_leadership_fields(self) -> None:
        report = f"ruleset_version : {common.RULESET_VERSION}\n"
        audit = """
leader_ret market_equal_weight_ret leadership_spread gap_up_fade_rate
leader_above_rate rebound_quality rebound_quality
data_gap classification judgement rule_gap
rule-ledger：无规则变更
"""
        review_text = report + audit
        pack = {
            "information_content": {"leadership": "informative"},
            "leadership": {"state": "leadership_lagging", "rebound_quality": "oversold_bounce"},
        }
        checks: list[dict] = []
        direction_gate.check_leadership(review_text, pack, checks)
        direction_gate.check_attribution(review_text, checks)
        direction_gate.check_ledger_and_version(review_text, checks)
        self.assertEqual([row["status"] for row in checks], ["pass", "pass", "pass", "pass"])

    def test_level_gate_requires_orphan_disclosure(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            level_file = root / "level_registry.csv"
            summary_file = root / "level_registry_summary.json"
            level_file.write_text("level\n1\n", encoding="utf-8")
            summary = {
                "as_of": "2026-10-22",
                "mandatory_gate": {"passed": True},
                "checks": [
                    {
                        "check": "orphan_scan",
                        "status": "warning",
                        "levels": [{"level": 3681.28}],
                    }
                ],
                "same_origin_bands": [],
            }
            summary_file.write_text(json.dumps(summary), encoding="utf-8")
            checks: list[dict] = []
            direction_gate.check_level_registry(
                "no orphan disclosed",
                {"critical_evidence": {"critical_levels": []}},
                "2026-10-23T09:00:00+08:00",
                str(level_file),
                checks,
            )
            self.assertEqual(checks[-1]["status"], "fail")

    def test_missing_sox_degrades_external_instead_of_failing_whole_report(self) -> None:
        available = "2026-10-23T08:00:00+08:00"
        external = {
            code: {
                "trade_date": "2026-10-23",
                "source": "test",
                "available_at": available,
                "pct_chg": -0.5,
                "data_quality": "test",
            }
            for code in ("IXIC", "SPX", "DJI", "N225")
        }
        external["XIN9"] = {
            "trade_date": "2026-10-23",
            "source": "test",
            "available_at": available,
            "pct_chg": 0.0,
            "data_quality": "test",
        }
        pack = {
            "target_date": "2026-10-23",
            "forecast_cutoff": "2026-10-23T09:00:00+08:00",
            "external_market": external,
            "external_gold": {
                "gold": {
                    "trade_date": "2026-10-22",
                    "source": "test",
                    "available_at": "2026-10-23T08:00:00+08:00",
                    "data_quality": "test",
                }
            },
            "external_snapshot": {
                "ruleset_version": common.RULESET_VERSION,
                "external_market": external,
            },
            "information_content": {"external": "uninformative"},
            "data_gap_register": [
                {"field": f"external.{code}", "status": "missing", "fallback_attempted": True}
                for code in ("SOX", "KS11", "AS51", "TWII")
            ],
        }
        report = "SOX 日经 KOSPI 澳洲 A50 台湾"
        checks: list[dict] = []
        direction_gate.check_external_integrity(report, pack, checks)
        self.assertEqual(checks[-1]["status"], "warning")

    def test_state_inputs_filters_future_rows(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            dates = pd.bdate_range("2025-01-01", periods=100)
            index = root / "index.csv"
            market = root / "market.csv"
            margin = root / "margin.csv"
            output = root / "state"
            pd.DataFrame(
                {
                    "date": dates,
                    "open": 100 + pd.Series(range(100)) * 0.1,
                    "high": 101 + pd.Series(range(100)) * 0.1,
                    "low": 99 + pd.Series(range(100)) * 0.1,
                    "close": 100.5 + pd.Series(range(100)) * 0.1,
                    "volume": 1_000_000 + pd.Series(range(100)) * 1000,
                    "amount": 1_000_000_000 + pd.Series(range(100)) * 100000,
                }
            ).to_csv(index, index=False)
            pd.DataFrame(
                {
                    "date": dates,
                    "advance_ratio": [0.5] * 99 + [0.95],
                    "equal_weight_ret": [0.0] * 99 + [0.03],
                    "total_amount": 1_000_000_000 + pd.Series(range(100)) * 100000,
                    "total_volume": 1_000_000 + pd.Series(range(100)) * 1000,
                }
            ).to_csv(market, index=False)
            pd.DataFrame(
                {
                    "trade_date": dates.strftime("%Y%m%d"),
                    "rzye": 1_000_000_000 - pd.Series(range(100)) * 100000,
                    "margin_net_buy": [-1_000_000] * 100,
                }
            ).to_csv(margin, index=False)
            asof = dates[-2].strftime("%Y-%m-%d")
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "state_inputs.py"),
                    "--index-daily",
                    str(index),
                    "--market-daily",
                    str(market),
                    "--margin",
                    str(margin),
                    "--asof",
                    asof,
                    "--output",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads((output / "state_inputs.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["asof"], asof)
            self.assertEqual(payload["input_coverage"]["index_daily"]["used_max"], asof)
            self.assertEqual(
                payload["input_coverage"]["margin"]["requested_max"],
                dates[-1].strftime("%Y-%m-%d"),
            )
            intraday_output = root / "state_intraday"
            intraday_stamp = f"{dates[-1].strftime('%Y-%m-%d')}T10:00:00+08:00"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "state_inputs.py"),
                    "--index-daily",
                    str(index),
                    "--market-daily",
                    str(market),
                    "--margin",
                    str(margin),
                    "--asof",
                    dates[-1].strftime("%Y-%m-%d"),
                    "--feature-cutoff",
                    intraday_stamp,
                    "--forecast-cutoff",
                    intraday_stamp,
                    "--stage",
                    "intraday_update",
                    "--available-at",
                    intraday_stamp,
                    "--output",
                    str(intraday_output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            intraday_payload = json.loads((intraday_output / "state_inputs.json").read_text(encoding="utf-8"))
            self.assertEqual(intraday_payload["available_at"], intraday_stamp)

    def test_level_registry_premarket_filters_target_day(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            dates = pd.bdate_range("2025-01-01", periods=150)
            daily = root / "daily.csv"
            output = root / "levels"
            close = pd.Series([3000 + i for i in range(150)], dtype=float)
            pd.DataFrame(
                {
                    "date": dates,
                    "open": close - 2,
                    "high": close + 8,
                    "low": close - 8,
                    "close": close,
                    "volume": 1_000_000,
                    "amount": 1_000_000_000,
                }
            ).to_csv(daily, index=False)
            target = dates[-1] + pd.Timedelta(days=1)
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "build_level_registry.py"),
                    "--daily",
                    str(daily),
                    "--stage",
                    "premarket",
                    "--target-date",
                    target.strftime("%Y-%m-%d"),
                    "--symbol",
                    "TEST",
                    "--output",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads((output / "level_registry_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["asof"], dates[-1].strftime("%Y-%m-%d"))
            self.assertLess(payload["asof"], payload["requested_target_date"])
            registry_columns = pd.read_csv(output / "level_registry.csv").columns
            ladder_columns = pd.read_csv(output / "level_ladder.csv").columns
            for columns in (registry_columns, ladder_columns):
                self.assertNotIn("score", columns)
                self.assertNotIn("tier", columns)
            self.assertIn("reaction_median", ladder_columns)

    def test_leadership_premarket_uses_prior_bar(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            dates = pd.bdate_range("2025-01-01", periods=300)
            target = dates[-1] + pd.Timedelta(days=1)
            basket = root / "basket.csv"
            bars = root / "bars.csv"
            index = root / "index.csv"
            output = root / "leader.json"
            pd.DataFrame(
                [{"ts_code": "000001.SZ", "name": "测试", "role": "market_anchor"}]
            ).to_csv(basket, index=False)
            pd.DataFrame(
                {
                    "ts_code": "000001.SZ",
                    "date": dates,
                    "open": [10 + index * 0.01 for index in range(len(dates))],
                    "high": [10.2 + index * 0.01 for index in range(len(dates))],
                    "low": [9.8 + index * 0.01 for index in range(len(dates))],
                    "close": [10.1 + index * 0.01 for index in range(len(dates))],
                }
            ).to_csv(bars, index=False)
            pd.DataFrame({"date": dates, "close": range(len(dates))}).to_csv(index, index=False)
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "leadership_state.py"),
                    "--basket",
                    str(basket),
                    "--leader-bars",
                    str(bars),
                    "--index-bars",
                    str(index),
                    "--target-date",
                    target.strftime("%Y-%m-%d"),
                    "--stage",
                    "premarket",
                    "--output",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["asof"], dates[-1].strftime("%Y-%m-%d"))
            self.assertEqual(payload["members_ok"], 1)
            self.assertNotEqual(payload["state"], "leadership_confirming")
            rejected = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "leadership_state.py"),
                    "--basket",
                    str(basket),
                    "--leader-bars",
                    str(bars),
                    "--index-bars",
                    str(index),
                    "--target-date",
                    target.strftime("%Y-%m-%d"),
                    "--asof",
                    target.strftime("%Y-%m-%d"),
                    "--stage",
                    "premarket",
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(rejected.returncode, 0)

    def test_scorecard_summaries_separate_path_and_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            pack = valid_path_pack()
            path_record = valid_forecast(pack, valid_judgement())
            legacy_record = {
                "target_date": "2026-10-23",
                "prediction_type": "prospective",
                "ruleset_version": "legacy",
                "direction": "neutral",
                "scenarios": valid_close_bins(),
                "targets": [],
            }
            for row, weight in zip(legacy_record["scenarios"], (0.1, 0.3, 0.4, 0.2)):
                row["weight"] = weight
            (root / "log.jsonl").write_text(
                json.dumps(path_record, ensure_ascii=False) + "\n" + json.dumps(legacy_record, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            pd.DataFrame({
                "date": ["2026-10-22", "2026-10-23"],
                "open": [3650.0, 3660.0],
                "high": [3670.0, 3690.0],
                "low": [3640.0, 3580.0],
                "close": [3650.0, 3610.0],
            }).to_csv(root / "bars.csv", index=False)
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPT_DIR / "scorecard.py"),
                    "--log", str(root / "log.jsonl"),
                    "--index-daily", str(root / "bars.csv"),
                    "--output", str(root / "score"),
                ],
                cwd=SCRIPT_DIR, text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads((root / "score" / "scorecard.json").read_text(encoding="utf-8"))["summary"]
            self.assertEqual(summary["path_count"], 1)
            self.assertEqual(summary["legacy_count"], 1)
            self.assertIn("path", summary)
            self.assertIn("legacy", summary)

    def test_extreme_statistics_are_evidence_without_weight_floors(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            dates = pd.bdate_range("2026-01-01", periods=100)
            close = pd.Series(100.0 + pd.RangeIndex(100) * 0.05)
            close.iloc[80] -= 8.0
            pd.DataFrame({
                "date": dates,
                "open": close.shift().fillna(100.0),
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
            }).to_csv(root / "index.csv", index=False)
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPT_DIR / "extreme_state_stats.py"),
                    "--index-daily", str(root / "index.csv"),
                    "--asof", "2026-05-20",
                    "--output", str(root / "stats"),
                ],
                cwd=SCRIPT_DIR, text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads((root / "stats" / "extreme_state_stats.json").read_text(encoding="utf-8"))
            self.assertNotIn("recommended_reversal_floor", payload)
            self.assertNotIn("recommended_reversal_floor_by_state", payload)
            self.assertIn("evidence_note", payload)
            self.assertTrue(all("recommended_reversal_floor" not in row for row in payload["states"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
