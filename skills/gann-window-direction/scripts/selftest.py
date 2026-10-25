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
执行覆盖
防守触发
恢复进攻触发
覆盖失效
操作建议理由
动作维持条件
动作解除条件
"""


def valid_path_forecast() -> dict:
    return {
        "opening": "flat or lower open",
        "steps": ["test support", "confirm acceptance or rejection"],
        "confirmation": "price accepts the declared boundary",
        "targets": [3584.0, 3560.0],
        "invalidation": "close leaves the scenario interval",
    }


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
            "critical_evidence": {
                "direction_audit": {
                    "structural_bias": "bearish",
                    "event_direction": "neutral",
                }
            },
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
        report = f"""
| 项目 | 内容 |
|---|---|
| 预测类型 | 历史回放 |
| 规则版本 | {common.RULESET_VERSION} |
| 决策阶段 | 盘前 |
| 预判截点 | 2026-09-22 09:00:00+08:00 |
| 特征截点 | 2026-09-22 09:00:00+08:00 |
| 目标日期 | 2026-09-22 |
| 门禁状态 | 带警告通过 |

| 决策项目 | 决策内容 |
|---|---|
| 结构偏向 | 看空 |
| 窗口状态 | 未决 |
| 事件日方向 | 震荡 |
| 执行状态 | 只减不加 |
| 操作偏向 | 只减不加 |
| 是否弃权 | 否 |
| 置信度 | 0.55 |
| 权重领先幅度 | 8.0个百分点 |
| 权重确信度 | 正常确信 |
| 决策区间 | 3958.03-3992.55 |
| 失效条件 | 收盘接受3992.55上方或跌破3916.49 |
| 下一确认 | 向下3916.49；向上3992.55 |
"""
        pack = {
            "prediction_type": "backfill",
            "target_date": "2026-09-22",
            "ruleset_version": common.RULESET_VERSION,
        }
        checks: list[dict] = []
        direction_gate.check_report_header(report, pack, checks)
        self.assertEqual(checks[-1]["status"], "pass")
        self.assertEqual(direction_gate.report_value(report, "prediction_type"), "backfill")
        self.assertEqual(direction_gate.report_value(report, "structural_bias"), "bearish")
        self.assertEqual(direction_gate.report_value(report, "gate_status"), "passed_with_warnings")

    def test_chinese_execution_overlay_display_values_are_normalized(self) -> None:
        self.assertEqual(common.normalize_report_value("setup_state", "风险区亢奋"), "risk_zone_euphoria")
        self.assertEqual(common.normalize_report_value("execution_bias", "只减不加"), "reduce_only")
        self.assertEqual(common.normalize_report_value("pressure_state", "尚未测试"), "untested")
        self.assertEqual(common.normalize_report_value("risk_state", "提前防守（盘前）"), "preemptive_defensive")
        self.assertEqual(common.normalize_report_value("risk_state", "观察"), "watch")
        self.assertEqual(common.normalize_report_value("execution_state", "观察"), "observe")
        self.assertEqual(common.normalize_report_value("action_bias", "停止操作"), "stop")
        self.assertEqual(common.normalize_report_value("direction", "震荡"), "neutral")
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

    def test_scenarios_require_explicit_direction(self) -> None:
        scenarios = [
            {"name": "tail_extreme_down", "direction": "bearish", "weight": 0.05, "lower": 0, "upper": 3500},
            {"name": "downside_continuation", "direction": "bearish", "weight": 0.30, "lower": 3500, "upper": 3602.15},
            {"name": "range_oscillation", "direction": "neutral", "weight": 0.40, "lower": 3602.15, "upper": 3702.44},
            {"name": "upside_breakout", "direction": "bullish", "weight": 0.25, "lower": 3702.44, "upper": 10000},
        ]
        self.assertEqual(common.validate_scenarios(scenarios), [])
        broken = [dict(row) for row in scenarios]
        broken[3].pop("direction")
        self.assertTrue(any("direction" in error for error in common.validate_scenarios(broken)))

    def test_single_scenario_above_half_is_allowed(self) -> None:
        scenarios = [
            {"name": "tail_extreme_down", "direction": "bearish", "weight": 0.05, "lower": 0, "upper": 3500},
            {"name": "downside_continuation", "direction": "bearish", "weight": 0.55, "lower": 3500, "upper": 3602.15},
            {"name": "range_oscillation", "direction": "neutral", "weight": 0.20, "lower": 3602.15, "upper": 3702.44},
            {"name": "upside_breakout", "direction": "bullish", "weight": 0.20, "lower": 3702.44, "upper": 10000},
        ]
        self.assertEqual(common.validate_scenarios(scenarios), [])

    def test_overlapping_scenarios_are_rejected(self) -> None:
        scenarios = [
            {"name": "tail_extreme_down", "direction": "bearish", "weight": 0.05, "lower": 0, "upper": 3500},
            {"name": "downside_continuation", "direction": "bearish", "weight": 0.30, "lower": 3499, "upper": 3602.15},
            {"name": "range_oscillation", "direction": "neutral", "weight": 0.40, "lower": 3602.15, "upper": 3702.44},
            {"name": "upside_breakout", "direction": "bullish", "weight": 0.25, "lower": 3702.44, "upper": 10000},
        ]
        self.assertTrue(any("boundary" in error for error in common.validate_scenarios(scenarios)))

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

    def test_scorecard_scores_preemptive_defense_from_open(self) -> None:
        bars = pd.DataFrame(
            {
                "open": [3949.9, 3963.8],
                "high": [3958.0, 3967.7],
                "low": [3940.0, 3945.4],
                "close": [3949.9, 3952.1],
            },
            index=pd.to_datetime(["2026-09-21", "2026-09-22"]),
        )
        record = {
            "target_date": "2026-09-22",
            "prediction_type": "prospective",
            "direction": "neutral",
            "structural_bias": "bearish",
            "scenarios": [],
            "targets": [],
            "execution_overlay": {
                "risk_state": "preemptive_defensive",
                "execution_bias": "reduce_only",
            },
        }
        result = scorecard.score_execution(record, bars)
        self.assertIsNotNone(result)
        self.assertLess(result["no_action_open_to_close_return"], 0)
        self.assertGreater(result["avoided_close_drawdown"], 0)
        self.assertEqual(result["execution_open_to_close_return"], 0.0)

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

    def test_scenario_directions_use_three_state_direction(self) -> None:
        scenarios = [
            {"name": "tail_extreme_down", "direction": "bearish", "weight": 0.05, "lower": 0, "upper": 3400, "close_condition": "close <3400"},
            {"name": "downside_continuation", "direction": "bearish", "weight": 0.20, "lower": 3400, "upper": 3600, "close_condition": "close <3600"},
            {"name": "range_oscillation", "direction": "neutral", "weight": 0.30, "lower": 3600, "upper": 3700, "close_condition": "close in band"},
            {"name": "upside_breakout", "direction": "bullish", "weight": 0.45, "lower": 3700, "upper": 5000, "close_condition": "close >3700"},
        ]
        for row in scenarios:
            row["path_forecast"] = valid_path_forecast()
        forecast = {
            "prediction_type": "prospective",
            "decision_stage": "premarket",
            "ruleset_version": common.RULESET_VERSION,
            "target_date": "2026-10-23",
            "forecast_cutoff": "2026-10-23T09:00:00+08:00",
            "feature_cutoff": "2026-10-23T09:00:00+08:00",
            "symbol": "000001.SH",
            "structural_bias": "bearish",
            "window_state": "unresolved",
            "direction": "bullish",
            "execution_state": "wait_for_confirmation",
            "action_bias": "reduce_only",
            "abstain": False,
            "confidence": 0.5,
            "close_axis": "close",
            "interval_convention": "lower_inclusive_upper_exclusive",
            "scenarios": scenarios,
            "targets": [{"name": "test", "level": 3600}],
            "llm_judgement": {},
            "judgement_source": "llm",
            "execution_overlay": execution_overlay.build_overlay(
                overlay_pack("premarket"), None,
                pressure_low=3690.0, pressure_high=3700.0, support=3600.0,
            ),
        }
        pack = {
            "prediction_type": "prospective",
            "ruleset_version": common.RULESET_VERSION,
            "target_date": "2026-10-23",
        }
        report = """
structural_bias : bearish
window_state : unresolved
direction : bullish
execution_state : wait_for_confirmation
action_bias : reduce_only
abstain : false
confidence : 0.5
"""
        checks: list[dict] = []
        direction_gate.check_forecast_contract(report, pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "pass")

        contradictory = [dict(row) for row in scenarios]
        contradictory[1]["direction"] = "neutral"
        self.assertTrue(
            any(
                "downside_continuation direction must be bearish" in error
                for error in common.validate_scenarios(contradictory)
            )
        )
        contradictory = [dict(row) for row in scenarios]
        contradictory[3]["direction"] = "bearish"
        self.assertTrue(
            any(
                "upside_breakout direction must be bullish" in error
                for error in common.validate_scenarios(contradictory)
            )
        )

    def test_execution_overlay_defensive_requires_pressure_and_participation(self) -> None:
        pack = overlay_pack()
        overlay = execution_overlay.build_overlay(
            pack, auction_snapshot(price=3680.0),
            pressure_low=3690.0, pressure_high=3700.0, support=3600.0,
        )
        self.assertEqual(overlay["pressure_state"], "rejected")
        self.assertEqual(overlay["participation_state"], "divergent")
        self.assertEqual(overlay["risk_state"], "defensive")
        self.assertEqual(overlay["execution_bias"], "reduce_only")
        pack["execution_overlay"] = overlay
        forecast = {"decision_stage": "preopen_0925", "execution_overlay": overlay}
        checks: list[dict] = []
        direction_gate.check_execution_overlay(VALID_EXECUTION_REPORT, pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "pass")

    def test_gap_fade_alone_does_not_trigger_defense(self) -> None:
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
        self.assertNotEqual(overlay["risk_state"], "defensive")
        self.assertNotEqual(overlay["execution_bias"], "reduce_only")

    def test_execution_overlay_offensive_requires_acceptance_and_confirmation(self) -> None:
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
        self.assertEqual(overlay["risk_state"], "offensive")
        self.assertEqual(overlay["execution_bias"], "add_only_after_confirmation")

    def test_missing_setup_inputs_degrade_without_action_signal(self) -> None:
        overlay = execution_overlay.build_overlay(
            overlay_pack(), None,
            pressure_low=3690.0, pressure_high=3700.0, support=3600.0,
        )
        self.assertEqual(overlay["risk_state"], "unknown")
        self.assertEqual(overlay["execution_bias"], "wait_for_confirmation")
        self.assertIn("premarket.close", overlay["data_gaps"])
        self.assertEqual(overlay["decision_mode"], "premarket_setup")

    def test_premarket_setup_triggers_preemptive_defense_without_snapshot(self) -> None:
        pack = premarket_foresight_pack()
        overlay = execution_overlay.build_overlay(
            pack, None,
            pressure_low=3958.03, pressure_high=3992.55, support=3916.49,
        )
        self.assertEqual(overlay["decision_mode"], "premarket_setup")
        self.assertEqual(overlay["setup_state"], "risk_zone_euphoria")
        self.assertEqual(overlay["risk_state"], "preemptive_defensive")
        self.assertEqual(overlay["execution_bias"], "reduce_only")
        self.assertGreaterEqual(overlay["metrics"]["setup_score"], 4)

    def test_execution_overlay_gate_accepts_premarket_preemptive_defense(self) -> None:
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

    def test_combined_snapshot_cannot_clear_premarket_risk_before_acceptance(self) -> None:
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
        self.assertEqual(overlay["risk_state"], "preemptive_defensive")
        self.assertEqual(overlay["execution_bias"], "reduce_only")

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
        self.assertEqual(accepted["risk_state"], "offensive")
        self.assertEqual(accepted["execution_bias"], "add_only_after_confirmation")

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
        self.assertEqual(overlay["risk_state"], "preemptive_defensive")

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
        self.assertEqual(overlay["metrics"]["setup_score"], 3)
        self.assertEqual(overlay["setup_state"], "risk_zone_euphoria")
        self.assertEqual(overlay["risk_state"], "preemptive_defensive")

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

    def test_unknown_setup_evidence_is_not_counted_as_met(self) -> None:
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
        self.assertEqual(overlay["metrics"]["setup_score"], 4)
        self.assertEqual(overlay["metrics"]["setup_unknown_checks"], 1)
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

    def test_scenario_weights_penalize_repeated_failure_and_wide_range(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            pack = {
                "target_date": "2026-10-15",
                "state_inputs": {
                    "weekly_regime": "down",
                    "funding_state": "neutral",
                    "breadth_state": "neutral",
                    "data_asof": "2026-10-14",
                    "available_at": "2026-10-14T18:00:00+08:00",
                },
                "structure_memory": {
                    "recent_path_pressure": {
                        "status": "not_met",
                        "subtype": "none",
                        "detail": "没有新增破位",
                    },
                    "nearest_support": {"level": 3700.0},
                    "nearest_pressure": {"level": 3800.0},
                    "atr14": 20.0,
                    "support_distance_atr": 1.0,
                    "reclaimed_count": 0,
                    "pressure_attempt_memory": {
                        "lookback_sessions": 10,
                        "nearest": {
                            "band_id": "pressure_band_1",
                            "test_count": 5,
                            "failed_close_count": 4,
                            "consecutive_failed_tests": 3,
                            "last_test_status": "failed",
                            "status": "repeated_failure",
                        },
                    },
                    "data_gaps": [],
                },
                "gann_result": {
                    "target_time_window": {"status": "不在已确认关键时间点"}
                },
            }
            (root / "pack.json").write_text(
                json.dumps(pack, ensure_ascii=False), encoding="utf-8"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "scenario_weights.py"),
                    "--pack",
                    str(root / "pack.json"),
                    "--output",
                    str(root / "weights.json"),
                ],
                cwd=SCRIPT_DIR,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            weighted = json.loads((root / "weights.json").read_text(encoding="utf-8"))
            names = {row["name"] for row in weighted["adjustments"]}
            self.assertIn("repeated_pressure_failure", names)
            self.assertIn("wide_range_penalty", names)
            self.assertEqual(weighted["range_width_atr"], 5.0)
            self.assertGreater(weighted["range_width_penalty"], 0)
            self.assertLess(
                weighted["weights"]["upside_breakout"],
                weighted["baseline_weights"]["upside_breakout"],
            )

    def test_bounded_scenario_weights_react_to_unreclaimed_break(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            pack = {
                "target_date": "2026-09-28",
                "state_inputs": {
                    "weekly_regime": "down",
                    "funding_state": "deleveraging",
                    "breadth_state": "deteriorating",
                    "data_asof": "2026-09-24",
                    "available_at": "2026-09-24T18:00:00+08:00",
                },
                "structure_memory": {
                    "recent_path_pressure": {
                        "status": "met",
                        "subtype": "break_unreclaimed",
                        "detail": "support 3896.62 broken and not reclaimed",
                    },
                    "support_distance_atr": 0.2,
                    "reclaimed_count": 0,
                    "data_gaps": [],
                },
                "gann_result": {
                    "target_time_window": {"status": "不在已确认关键时间点"}
                },
            }
            (root / "pack.json").write_text(
                json.dumps(pack, ensure_ascii=False), encoding="utf-8"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "scenario_weights.py"),
                    "--pack",
                    str(root / "pack.json"),
                    "--output",
                    str(root / "weights.json"),
                ],
                cwd=SCRIPT_DIR,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            weighted = json.loads((root / "weights.json").read_text(encoding="utf-8"))
            self.assertAlmostEqual(sum(weighted["weights"].values()), 1.0, places=6)
            self.assertEqual(weighted["top_scenario"], "downside_continuation")
            self.assertEqual(
                weighted["adjustments"][0]["name"], "broken_support_unreclaimed"
            )

    def test_code_weights_are_baseline_reference_only(self) -> None:
        weights = {
            "downside_continuation": 0.40,
            "range_oscillation": 0.30,
            "upside_breakout": 0.20,
            "tail_extreme_down": 0.10,
        }
        pack = {
            "scenario_weighting": {
                "role": "baseline_reference",
                "weights": weights,
                "confidence_margin": 0.10,
                "low_confidence": False,
            }
        }
        checks: list[dict] = []
        direction_gate.check_scenario_weighting(pack, checks)
        self.assertEqual(checks[-1]["status"], "pass")

    def test_gate_accepts_llm_final_judgement(self) -> None:
        scenarios = [
            {"name": "tail_extreme_down", "direction": "bearish", "weight": 0.10, "lower": 0, "upper": 3400},
            {"name": "downside_continuation", "direction": "bearish", "weight": 0.40, "lower": 3400, "upper": 3600},
            {"name": "range_oscillation", "direction": "neutral", "weight": 0.30, "lower": 3600, "upper": 3700},
            {"name": "upside_breakout", "direction": "bullish", "weight": 0.20, "lower": 3700, "upper": 5000},
        ]
        for row in scenarios:
            row["close_condition"] = "收盘位于声明区间"
            row["path_forecast"] = valid_path_forecast()
        judgement = {
            "source": "llm",
            "target_date": "2026-10-23",
            "structural_bias": "bearish",
            "window_state": "unresolved",
            "direction": "bearish",
            "execution_state": "reduce_only",
            "execution_action": "reduce_only",
            "risk_state": "preemptive_defensive",
            "abstain": False,
            "confidence": 0.6,
            "scenarios": scenarios,
            "targets": [{"name": "向下目标", "level": 3400}],
            "supporting_evidence": ["结构偏空", "支撑破位未收复"],
            "opposing_evidence": ["外盘短线反弹"],
            "action_maintenance": ["支撑仍未收复"],
            "action_invalidation": ["收盘重新站上支撑"],
            "evidence_refs": ["structure_memory", "external_market"],
            "top_scenario": "downside_continuation",
            "confidence_margin": 0.10,
            "low_confidence": False,
        }
        pack = {
            "target_date": "2026-10-23",
            "llm_judgement": judgement,
            "structure_memory": {"recent_path_pressure": {"status": "met"}},
            "external_market": {"SOX": {"pct_chg": -4.3}},
        }
        forecast = {
            "llm_judgement": judgement,
            "judgement_source": "llm",
            "structural_bias": "bearish",
            "window_state": "unresolved",
            "direction": "bearish",
            "execution_state": "reduce_only",
            "action_bias": "reduce_only",
            "abstain": False,
            "confidence": 0.6,
            "scenarios": scenarios,
            "targets": judgement["targets"],
        }
        checks = []
        direction_gate.check_llm_judgement(
            "| 权重确信度 | 正常确信 |", pack, forecast, checks
        )
        self.assertEqual(checks[-1]["status"], "pass")

        forecast["direction"] = "neutral"
        checks = []
        direction_gate.check_llm_judgement(
            "| 权重确信度 | 正常确信 |", pack, forecast, checks
        )
        self.assertEqual(checks[-1]["status"], "fail")

    def test_llm_judgement_validator_builds_forecast(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            scenarios = [
                {"name": "tail_extreme_down", "direction": "bearish", "weight": 0.10, "lower": 0, "upper": 3400, "close_condition": "收盘低于3400"},
                {"name": "downside_continuation", "direction": "bearish", "weight": 0.40, "lower": 3400, "upper": 3600, "close_condition": "收盘低于3600"},
                {"name": "range_oscillation", "direction": "neutral", "weight": 0.30, "lower": 3600, "upper": 3700, "close_condition": "收盘位于区间"},
                {"name": "upside_breakout", "direction": "bullish", "weight": 0.20, "lower": 3700, "upper": 5000, "close_condition": "收盘高于3700"},
            ]
            for row in scenarios:
                row["path_forecast"] = valid_path_forecast()
            pack = {
                "target_date": "2026-10-23",
                "prediction_type": "prospective",
                "decision_stage": "premarket",
                "ruleset_version": common.RULESET_VERSION,
                "forecast_cutoff": "2026-10-23T09:00:00+08:00",
                "feature_cutoff": "2026-10-23T09:00:00+08:00",
                "symbol": "000001.SH",
                "structure_memory": {"close": 3550},
                "external_market": {"SOX": {"pct_chg": -4.3}},
            }
            judgement = {
                "source": "llm",
                "target_date": "2026-10-23",
                "decision_at": "2026-10-23T08:55:00+08:00",
                "core_thesis": "支撑失守且外盘确认下行",
                "structural_bias": "bearish",
                "window_state": "unresolved",
                "direction": "bearish",
                "scenarios": scenarios,
                "targets": [{"name": "向下目标", "level": 3400}],
                "execution_state": "reduce_only",
                "execution_action": "reduce_only",
                "risk_state": "preemptive_defensive",
                "confidence": 0.6,
                "abstain": False,
                "supporting_evidence": ["支撑破位", "外围风险冲击"],
                "opposing_evidence": ["短线出现反弹"],
                "action_maintenance": ["支撑仍未收复"],
                "action_invalidation": ["收盘重新站上支撑"],
                "evidence_refs": ["structure_memory.close", "external_market.SOX"],
                "horizon": "目标交易日",
                "next_review": "下一交易日收盘",
            }
            (root / "pack.json").write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
            (root / "judgement.json").write_text(json.dumps(judgement, ensure_ascii=False), encoding="utf-8")
            validated = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "validate_llm_judgement.py"),
                    "--pack",
                    str(root / "pack.json"),
                    "--judgement",
                    str(root / "judgement.json"),
                    "--pack-output",
                    str(root / "pack.final.json"),
                ],
                cwd=SCRIPT_DIR,
                text=True,
                capture_output=True,
            )
            self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)
            built = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "build_forecast_from_judgement.py"),
                    "--pack",
                    str(root / "pack.final.json"),
                    "--output",
                    str(root / "forecast.json"),
                ],
                cwd=SCRIPT_DIR,
                text=True,
                capture_output=True,
            )
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            forecast = json.loads((root / "forecast.json").read_text(encoding="utf-8"))
            self.assertEqual(forecast["direction"], "bearish")
            self.assertEqual(forecast["action_bias"], "reduce_only")
            self.assertEqual(forecast["judgement_source"], "llm")

    def test_action_maintenance_and_release_are_separate(self) -> None:
        pack = premarket_foresight_pack()
        overlay = execution_overlay.build_overlay(
            pack,
            None,
            pressure_low=3958.03,
            pressure_high=3992.55,
            support=3916.49,
        )
        rationale = overlay["action_rationale"]
        self.assertIn("action_maintenance", rationale)
        self.assertIn("action_invalidation", rationale)
        self.assertNotIn("action_confirmation", rationale)
        self.assertTrue(any("仍未接受3992.55" in item for item in rationale["action_maintenance"]))
        self.assertTrue(any("放量收盘接受3992.55上方" in item for item in rationale["action_invalidation"]))
        self.assertTrue(all("覆盖失效" in item for item in overlay["invalidation"]))

    def test_gate_requires_execution_trigger_content_in_report(self) -> None:
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
        direction_gate.check_execution_overlay("执行覆盖\n操作建议理由", pack, forecast, checks)
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
        changed["risk_state"] = "watch"
        forecast = {"decision_stage": "preopen_0925", "execution_overlay": changed}
        checks: list[dict] = []
        direction_gate.check_execution_overlay("执行覆盖\n操作建议理由", pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "fail")
        self.assertTrue(any("完全一致" in error for error in checks[-1]["errors"]))

    def test_execution_overlay_rejects_missing_fields(self) -> None:
        pack = overlay_pack()
        overlay = execution_overlay.build_overlay(
            pack, auction_snapshot(price=3680.0),
            pressure_low=3690.0, pressure_high=3700.0, support=3600.0,
        )
        overlay.pop("offensive_trigger")
        pack["execution_overlay"] = overlay
        forecast = {"decision_stage": "preopen_0925", "execution_overlay": overlay}
        checks: list[dict] = []
        direction_gate.check_execution_overlay("执行覆盖\n操作建议理由", pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "fail")

    def test_execution_overlay_requires_action_rationale(self) -> None:
        pack = overlay_pack()
        overlay = execution_overlay.build_overlay(
            pack, auction_snapshot(price=3680.0),
            pressure_low=3690.0, pressure_high=3700.0, support=3600.0,
        )
        overlay["action_rationale"]["why_now"] = []
        pack["execution_overlay"] = overlay
        forecast = {"decision_stage": "preopen_0925", "execution_overlay": overlay}
        checks: list[dict] = []
        direction_gate.check_execution_overlay("执行覆盖\n操作建议理由", pack, forecast, checks)
        self.assertEqual(checks[-1]["status"], "fail")
        self.assertTrue(any("why_now" in error for error in checks[-1]["errors"]))

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

    def test_path_forecast_requires_complete_chain(self) -> None:
        scenario = {"name": "range_oscillation", "path_forecast": valid_path_forecast()}
        self.assertEqual(direction_gate.validate_path_forecasts([scenario]), [])

        missing = {"name": "range_oscillation"}
        self.assertIn(
            "range_oscillation 缺少 path_forecast",
            direction_gate.validate_path_forecasts([missing]),
        )

        short = valid_path_forecast()
        short["steps"] = ["test then rebound"]
        short["targets"] = []
        errors = direction_gate.validate_path_forecasts([
            {"name": "range_oscillation", "path_forecast": short}
        ])
        self.assertTrue(any("steps" in error for error in errors))
        self.assertTrue(any("targets" in error for error in errors))

    def test_chinese_scenario_labels_are_gate_compatible(self) -> None:
        report = """
| 情景 | 权重 | 方向 | 收盘区间 | 条件与目标 |
|---|---:|---|---:|---|
| 区间震荡 | 40% | 震荡 | 3640-3680 | 收盘位于区间，等待确认 |
| 向下延续 | 30% | 看空 | 3600-3640 | 收盘跌破防线，目标3584 |
| 向上突破 | 25% | 看多 | 3680以上 | 收盘站上防线，目标3700 |
| 尾部极值（向下） | 5% | 看空 | 3600以下 | 收盘低于尾部阈值 |
"""
        checks: list[dict] = []
        direction_gate.check_scenarios(report, checks)
        self.assertEqual(checks[-1]["status"], "pass")
        weights, total = direction_gate.parse_weights(report)
        self.assertAlmostEqual(total, 1.0)
        self.assertEqual(
            weights,
            {
                "downside_continuation": 0.30,
                "range_oscillation": 0.40,
                "upside_breakout": 0.25,
                "tail_extreme_down": 0.05,
            },
        )
    def test_chinese_scenario_table_rejects_weight_sum_over_hundred(self) -> None:
        report = """
| 情景 | 权重 | 方向 | 收盘区间 | 条件与目标 |
|---|---:|---|---:|---|
| 区间震荡 | 45% | 震荡 | 3640-3680 | 收盘位于区间，等待确认 |
| 向下延续 | 30% | 看空 | 3600-3640 | 收盘跌破防线，目标3584 |
| 向上突破 | 25% | 看多 | 3680以上 | 收盘站上防线，目标3700 |
| 尾部极值（向下） | 5% | 看空 | 3600以下 | 收盘低于尾部阈值 |
"""
        checks: list[dict] = []
        direction_gate.check_scenarios(report, checks)
        self.assertEqual(checks[-1]["status"], "fail")
        self.assertIn("105%", checks[-1]["detail"])

    def test_scenario_table_allows_weight_above_half(self) -> None:
        report = """
| 情景 | 权重 | 方向 | 收盘判定 | 完整路径预测 |
|---|---:|---|---|---|
| 区间震荡 | 20% | 震荡 | 收盘位于 `[3640, 3680)` | 测试边界后回到区间 |
| 向下延续 | 55% | 看空 | 收盘位于 `[3600, 3640)` | 反抽失败后跌破支撑 |
| 向上突破 | 20% | 看多 | 收盘位于 `[3680, 10000]` | 放量接受压力 |
| 尾部极值（向下） | 5% | 看空 | 收盘位于 `[0, 3600)` | 支撑失守后加速 |
"""
        checks: list[dict] = []
        direction_gate.check_scenarios(report, checks)
        self.assertEqual(checks[-1]["status"], "pass")

    def test_chinese_scenario_headings_are_decidable(self) -> None:
        report = """
### 区间震荡（40%）
收盘在3640-3680。
### 向下延续（30%）
收盘低于3640，目标3584。
### 向上突破（25%）
收盘高于3680，目标3700。
### 尾部极值（向下）（5%）
收盘低于3600。
"""
        checks: list[dict] = []
        direction_gate.check_decidable(report, checks)
        self.assertEqual(checks[-1]["status"], "pass")

    def test_compact_scenario_table_is_decidable(self) -> None:
        report = """
| 情景 | 权重 | 方向 | 收盘判定 | 完整路径预测 |
|---|---:|---|---|---|
| 区间震荡 | 40% | 震荡 | 收盘位于 `[3640, 3680)` | 低开→测试3640→收回并横盘 |
| 向下延续 | 30% | 看空 | 收盘位于 `[3600, 3640)` | 低开→反抽3640失败→再度下破 |
| 向上突破 | 25% | 看多 | 收盘位于 `[3680, 10000]` | 平开→获得承接→放量突破3680 |
| 尾部极值（向下） | 5% | 看空 | 收盘位于 `[0, 3600)` | 显著低开→支撑无承接→流动性冲击 |
"""
        checks: list[dict] = []
        direction_gate.check_decidable(report, checks)
        self.assertEqual(checks[-1]["status"], "pass")

    def test_audit_appendix_can_hold_review_and_leadership_fields(self) -> None:
        report = f"ruleset_version : {common.RULESET_VERSION}\n"
        audit = """
leader_ret market_equal_weight_ret leadership_spread gap_up_fade_rate
leader_above_rate rebound_quality rebound_quality
data_gap classification weighting rule_gap
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
