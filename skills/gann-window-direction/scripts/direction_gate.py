#!/usr/bin/env python3
"""方向层的强制执行门禁（mandatory gate）。

为什么必须存在：
方向报告同时受点时数据、输出契约、关键位门禁和冻结哈希约束。本脚本验证这些约束，
而不评判观点本身。

本脚本按字段与结构检查一份路径报告、输入包、forecast 和阶段快照。检查包括：
报告头/决策卡、输入包完整性、外盘锚点及时点、领涨字段、逐层信息量、三段路径、
当前价格锚、无权重收盘轴、结构/路径分歧、缺口、复盘归因、规则版本和 manifest 哈希。预检决定报告头
`gate_status`；冻结后终检只写外部 `final_gate_status`，失败时整份快照作废，
不得修改冻结文件。检查不判断观点对错。

用法：
python3 scripts/direction_gate.py --report /abs/path/report.md \
    --audit /abs/path/audit.md --pack /abs/path/direction_input_pack.json \
    --forecast /abs/path/forecast_record.json \
    --manifest /abs/path/snapshot_manifest.json --output /abs/path/gate
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from common import (
    INFO_VALUES,
    LAYERS,
    REPORT_FIELD_LABELS_ZH,
    RULESET_VERSION,
    SCENARIO_REPORT_LABELS,
    SCENARIO_NAMES,
    atomic_write_json,
    normalize_report_value,
    parse_available_at,
    parse_cutoff,
    parse_date,
    validate_close_bins,
)
from path_contract import forbidden_keys, validate_next_day_path
from execution_overlay import (
    GAP_STATES,
    PARTICIPATION_STATES,
    PRESSURE_STATES,
    SETUP_EVIDENCE_STATES,
)

SHAPES = SCENARIO_NAMES
ATTRIBUTIONS = ("data_gap", "classification", "judgement", "rule_gap")
ATTRIBUTION_LABELS_ZH = {
    "data_gap": ("数据缺口",),
    "classification": ("分类口径", "分类"),
    "judgement": ("综合裁量", "判断错误"),
    "rule_gap": ("规则缺口",),
}
STRUCTURAL_VALUES = ("bullish", "bearish", "neutral")
WINDOW_VALUES = (
    "unresolved",
    "bullish_confirmation",
    "bearish_confirmation",
    "failed_bullish_window",
    "failed_bearish_window",
)
EXECUTION_VALUES = ("observe", "wait_for_confirmation", "confirmed", "reduce_only", "abstain")
ACTION_VALUES = ("observe", "add_only_after_confirmation", "hold", "reduce_only", "no_new_long", "stop")
RISK_STATES = ("normal", "watch", "preemptive_defensive", "defensive", "offensive", "unknown")
DECISION_FIELDS = (
    "structural_bias",
    "window_state",
    "next_day_baseline",
    "opening_zone",
    "intraday_zone",
    "close_zone",
    "close_character",
    "execution_state",
    "action_bias",
    "abstain",
)
PACK_REQUIRED = (
    "decision_stage",
    "prediction_type",
    "forecast_cutoff",
    "feature_cutoff",
    "target_date",
    "symbol",
    "ruleset_version",
    "source_used",
    "future_function_audit",
    "gann_result",
    "wave_result",
    "external_market",
    "external_gold",
    "external_snapshot",
    "information_content",
    "path_memory",
    "recent_5d_raw",
    "recent_5d_summary",
    "baseline_20d",
    "volume_price",
    "margin_financing",
    "breadth_and_sectors",
    "data_gap_register",
    "critical_evidence",
    "state_inputs",
    "structure_memory",
    "level_context",
    "llm_judgement",
    "leadership",
    "space_levels",
    "execution_overlay",
)
EXTERNAL_REQUIRED = ("IXIC", "SPX", "DJI", "SOX")
LEADERSHIP_FIELDS = (
    "leader_ret",
    "market_equal_weight_ret",
    "leadership_spread",
    "gap_up_fade_rate",
    "leader_above_rate",
    "rebound_quality",
)
INFORMATION_LAYER_LABELS_ZH = {
    "external": ("外围市场", "外部市场"),
    "volume": ("成交额", "量能"),
    "margin": ("两融", "融资融券"),
    "breadth": ("市场宽度", "宽度"),
    "leadership": ("领涨结构",),
    "path": ("前序路径", "路径"),
    "event": ("事件账本", "事件"),
}
INFORMATION_VALUE_LABELS_ZH = {
    "informative": ("有效信息", "信息有效"),
    "weak": ("偏弱信息", "信息偏弱"),
    "uninformative": ("无有效信息", "信息不足"),
}
LEADERSHIP_LABELS_ZH = {
    "leader_ret": ("领涨篮子收益",),
    "market_equal_weight_ret": ("市场等权收益",),
    "leadership_spread": ("领涨超额",),
    "gap_up_fade_rate": ("高开回落率",),
    "leader_above_rate": ("篮子成员站上均线比例",),
    "rebound_quality": ("反弹质量",),
}
CHINESE_NUMBER_CHARS = "零〇一二三四五六七八九十百千万亿两"
CHINESE_QUANTITY_PATTERNS = (
    re.compile(rf"百分之[{CHINESE_NUMBER_CHARS}]+(?:点[{CHINESE_NUMBER_CHARS}]+)?"),
    re.compile(rf"(?<!第)[{CHINESE_NUMBER_CHARS}]+点[{CHINESE_NUMBER_CHARS}]+"),
    re.compile(
        rf"(?:[{CHINESE_NUMBER_CHARS}]{{2,4}}年)?"
        rf"[{CHINESE_NUMBER_CHARS}]{{1,2}}月"
        rf"[{CHINESE_NUMBER_CHARS}]{{1,3}}日"
    ),
    re.compile(
        rf"(?<![第下同统唯前当])[{CHINESE_NUMBER_CHARS}]+"
        r"(?:个完整交易日|个交易日|交易日|周|日|倍|亿元|万元|点|次|只|根|家|项|档|时)"
    ),
    re.compile(rf"第[{CHINESE_NUMBER_CHARS}]+版"),
)
OBSERVATION_NODE_SCHEMAS = {
    "gann_result": {
        "date_fields": ("as_of", "asof"),
        "required": ("available_at", "source", "data_quality"),
    },
    "wave_result": {
        "date_fields": ("latest_data_asof", "as_of", "asof"),
        "required": ("available_at", "source", "data_quality"),
    },
    "path_memory": {
        "date_fields": ("data_asof",),
        "required": ("available_at", "source", "data_quality"),
    },
    "recent_5d_summary": {
        "date_fields": ("data_asof",),
        "required": ("available_at", "source", "data_quality"),
    },
    "baseline_20d": {
        "date_fields": ("data_asof",),
        "required": ("available_at", "source", "data_quality"),
    },
    "volume_price": {
        "date_fields": ("data_asof",),
        "required": ("available_at", "source", "data_quality"),
    },
    "margin_financing": {
        "date_fields": ("data_asof",),
        "required": ("available_at", "source", "data_quality"),
    },
    "breadth_and_sectors": {
        "date_fields": ("data_asof",),
        "required": ("available_at", "source", "data_quality"),
    },
    "leadership": {
        "date_fields": ("data_asof", "asof"),
        "required": ("available_at", "source", "data_quality"),
    },
    "state_inputs": {
        "date_fields": ("data_asof", "asof"),
        "required": ("available_at", "source", "data_quality"),
    },
    "structure_memory": {
        "date_fields": ("data_asof",),
        "required": ("available_at", "source", "data_quality"),
    },
    "level_context": {
        "date_fields": ("data_asof",),
        "required": ("available_at", "source", "data_quality"),
    },
    "llm_judgement": {
        "date_fields": ("decision_at",),
        "required": ("available_at", "source", "data_quality"),
    },
    "execution_overlay": {
        "date_fields": ("data_asof",),
        "required": ("available_at", "source", "data_quality"),
    },
}


def scenario_labels(shape: str) -> tuple[str, ...]:
    """Return accepted Chinese report labels while preserving the English schema id."""
    return SCENARIO_REPORT_LABELS.get(shape, ())


def shape_markers(shape: str) -> tuple[str, ...]:
    return (shape, *scenario_labels(shape))


def report_has_scenario(report: str, shape: str) -> bool:
    return any(marker in report for marker in shape_markers(shape))


def add(checks: list, name: str, status: str, detail: str, **extra) -> None:
    entry = {"check": name, "status": status, "detail": detail}
    entry.update(extra)
    checks.append(entry)


def report_field_raw(report: str, field: str) -> str | None:
    """Read a report field from English machine labels or Chinese display labels."""
    labels = (field, *REPORT_FIELD_LABELS_ZH.get(field, ()))
    label_pattern = "|".join(re.escape(label) for label in labels)
    head = report[:8000]
    patterns = (
        rf"(?im)^\s*\|\s*(?:{label_pattern})\s*\|\s*`?([^|\n]+?)\s*\|",
        rf"(?im)^\s*(?:{label_pattern})\s*[：:=]\s*`?([^\n]+?)\s*$",
    )
    for pattern in patterns:
        match = re.search(pattern, head)
        if match:
            return match.group(1).strip().strip("`").strip()
    return None


def report_value(report: str, field: str) -> str | None:
    return normalize_report_value(field, report_field_raw(report, field))


def report_labeled_value(report: str, labels: tuple[str, ...]) -> str | None:
    label_pattern = "|".join(re.escape(label) for label in labels)
    patterns = (
        rf"(?im)^\s*\|\s*(?:{label_pattern})\s*\|\s*`?([^|\n]+?)\s*\|",
        rf"(?im)^\s*(?:{label_pattern})\s*[：:=]\s*`?([^\n]+?)\s*$",
    )
    for pattern in patterns:
        match = re.search(pattern, report)
        if match:
            return match.group(1).strip().strip("`").strip()
    return None


def check_report_header(report: str, pack: dict | None, checks: list) -> None:
    required = (
        "prediction_type",
        "ruleset_version",
        "forecast_cutoff",
        "feature_cutoff",
        "target_date",
        "gate_status",
        *DECISION_FIELDS,
    )
    missing = [field for field in required if report_field_raw(report, field) is None]
    if missing:
        add(
            checks,
            "report_header_and_decision_card",
            "fail",
            "报告信息表或决策卡缺少字段；完整报告必须先给中文可读决策卡",
            missing_fields=missing,
        )
        return

    values = {field: report_value(report, field) for field in DECISION_FIELDS}
    invalid = []
    for field, allowed in (
        ("structural_bias", STRUCTURAL_VALUES),
        ("window_state", WINDOW_VALUES),
        ("execution_state", EXECUTION_VALUES),
        ("action_bias", ACTION_VALUES),
    ):
        if values[field] not in allowed:
            invalid.append({"field": field, "value": values[field], "allowed": list(allowed)})
    if invalid:
        add(checks, "report_header_and_decision_card", "fail", "决策卡存在非法枚举值", invalid=invalid)
        return

    if pack:
        mismatches = []
        for field in ("prediction_type", "target_date", "ruleset_version"):
            if report_value(report, field) and str(pack.get(field)) != report_value(report, field):
                mismatches.append({"field": field, "report": report_value(report, field), "pack": pack.get(field)})
        if mismatches:
            add(checks, "report_header_and_decision_card", "fail", "报告头与输入包元数据不一致", mismatches=mismatches)
            return
    forbidden_display = [
        label for label in ("事件日方向", "置信度", "权重领先幅度", "权重确信度")
        if label in report[:8000]
    ]
    if forbidden_display:
        add(
            checks,
            "report_header_and_decision_card",
            "fail",
            "新版决策卡不得包含事件日总方向、权重或置信度",
            forbidden_labels=forbidden_display,
        )
        return
    add(checks, "report_header_and_decision_card", "pass", "报告头、路径决策卡和枚举值齐备")


def check_numeric_display(report: str, checks: list) -> None:
    """Reject Chinese number words where a quantitative value belongs."""
    violations = []
    for line_number, line in enumerate(report.splitlines(), start=1):
        for pattern in CHINESE_QUANTITY_PATTERNS:
            for match in pattern.finditer(line):
                violations.append(
                    {
                        "line": line_number,
                        "text": match.group(0),
                        "context": line.strip()[:160],
                    }
                )
        if line.lstrip().startswith("|"):
            for cell in line.split("|")[1:-1]:
                value = cell.strip()
                if re.fullmatch(rf"[{CHINESE_NUMBER_CHARS}]+", value):
                    violations.append(
                        {
                            "line": line_number,
                            "text": value,
                            "context": line.strip()[:160],
                        }
                    )
    if violations:
        add(
            checks,
            "numeric_display",
            "fail",
            "价格、百分比、日期、周期、金额、倍数或版本号使用了中文数字",
            violations=violations[:20],
            violation_count=len(violations),
        )
        return
    add(checks, "numeric_display", "pass", "数量型数据均使用阿拉伯数字与常规单位")


def check_language_display(report: str, checks: list) -> None:
    """Reject English words in the human-facing display layer."""
    narrative = re.sub(r"!?\[[^\]]*\]\(<[^>]+>\)", "", report)
    narrative = re.sub(r"```.*?```", "", narrative, flags=re.S)
    narrative = re.sub(r"\b\d{6}\.(?:SH|SZ)\b", "", narrative)
    tokens = re.findall(r"[A-Za-z]{2,}", narrative)
    if tokens:
        add(
            checks,
            "language_display",
            "fail",
            "中文报告或审计附录仍包含英文叙述",
            tokens=sorted(set(tokens))[:20],
            token_count=len(tokens),
        )
        return
    add(checks, "language_display", "pass", "报告与审计附录均为中文叙述")


def check_pack_contract(report: str, pack: dict | None, checks: list) -> None:
    if pack is None:
        add(checks, "input_pack_contract", "fail", "缺少输入包（--pack）")
        return
    missing = [field for field in PACK_REQUIRED if field not in pack or pack.get(field) in (None, {}, [])]
    if missing:
        add(checks, "input_pack_contract", "fail", "输入包为生产级输出所需字段不完整", missing_fields=missing)
        return
    if pack.get("prediction_type") not in ("prospective", "backfill"):
        add(checks, "input_pack_contract", "fail", "输入包 prediction_type 非法")
        return
    if pack.get("ruleset_version") != RULESET_VERSION:
        add(
            checks,
            "input_pack_contract",
            "fail",
            "输入包 ruleset_version 与当前技能版本不一致",
            expected=RULESET_VERSION,
            actual=pack.get("ruleset_version"),
        )
        return
    if not isinstance(pack.get("source_used"), dict) or not pack["source_used"]:
        add(checks, "input_pack_contract", "fail", "source_used 必须给出字段级实际来源")
        return
    memory = pack.get("structure_memory")
    memory_required = (
        "target_date",
        "data_asof",
        "available_at",
        "source",
        "data_quality",
        "close",
        "recent_path_pressure",
        "pressure_attempt_memory",
    )
    memory_missing = [
        field for field in memory_required if not isinstance(memory, dict) or field not in memory
    ]
    if memory_missing:
        add(
            checks,
            "input_pack_contract",
            "fail",
            "structure_memory 字段不完整",
            missing_fields=memory_missing,
        )
        return
    path_state = (memory.get("recent_path_pressure") or {}).get("status")
    if path_state not in ("met", "not_met", "unknown"):
        add(
            checks,
            "input_pack_contract",
            "fail",
            "structure_memory.recent_path_pressure.status 非法",
            actual=path_state,
        )
        return
    pressure_memory = memory.get("pressure_attempt_memory")
    if not isinstance(pressure_memory, dict) or not isinstance(
        pressure_memory.get("bands"), list
    ):
        add(
            checks,
            "input_pack_contract",
            "fail",
            "structure_memory.pressure_attempt_memory 必须包含压力尝试序列",
        )
        return
    invalid_attempts = [
        row
        for row in pressure_memory.get("bands", [])
        if not isinstance(row, dict)
        or not {
            "band_id",
            "anchor_level",
            "defense_level",
            "test_count",
            "failed_close_count",
            "accepted_close_count",
            "consecutive_failed_tests",
            "status",
        }.issubset(row)
    ]
    if invalid_attempts:
        add(
            checks,
            "input_pack_contract",
            "fail",
            "pressure_attempt_memory 条目字段不完整",
            invalid_attempts=invalid_attempts[:5],
        )
        return
    try:
        if parse_date(memory["data_asof"]) >= parse_date(pack["target_date"]):
            add(
                checks,
                "input_pack_contract",
                "fail",
                "structure_memory 必须严格早于目标日期",
                data_asof=memory["data_asof"],
            )
            return
    except (KeyError, TypeError, ValueError):
        add(checks, "input_pack_contract", "fail", "structure_memory 时点无法解析")
        return
    add(checks, "input_pack_contract", "pass", f"{len(PACK_REQUIRED)} 个核心输入包字段齐备")


def check_level_context(pack: dict | None, checks: list) -> None:
    context = (pack or {}).get("level_context")
    if not isinstance(context, dict):
        add(checks, "level_context", "fail", "输入包缺少当前点位事实包")
        return
    errors = []
    if context.get("atr_method") != "wilder_14":
        errors.append("点位事实包必须使用统一 wilder_14")
    memory = (pack or {}).get("structure_memory") or {}
    summary = ((pack or {}).get("space_levels") or {}).get("level_registry_summary") or {}
    if memory.get("atr_method") != "wilder_14" or summary.get("atr_method") != "wilder_14":
        errors.append("结构记忆与关键位登记必须声明统一 ATR 口径")
    try:
        if abs(float(memory["atr14"]) - float(summary["atr14"])) > 0.011:
            errors.append("结构记忆与关键位登记的 ATR 数值不一致")
    except (KeyError, TypeError, ValueError):
        errors.append("结构记忆或关键位登记缺少 ATR")
    if not context.get("price_anchors"):
        errors.append("点位事实包缺少价格锚")
    errors.extend(validate_close_bins(context.get("close_bins") or []))
    if errors:
        add(checks, "level_context", "fail", "点位事实包不合格", errors=errors)
        return
    add(checks, "level_context", "pass", "当前点位、统一 ATR 与无权重收盘结算轴齐备")


def check_llm_judgement(
    report: str,
    pack: dict | None,
    forecast: dict | None,
    checks: list,
) -> None:
    judgement = (pack or {}).get("llm_judgement")
    if not isinstance(judgement, dict):
        add(checks, "llm_judgement", "fail", "输入包缺少大模型最终结构化研判")
        return
    errors: list[str] = []
    forbidden = forbidden_keys(judgement)
    if forbidden:
        errors.append(f"研判含新版禁用字段：{forbidden}")
    if judgement.get("source") != "llm":
        errors.append("最终研判来源必须明确为大模型")
    if str(judgement.get("target_date")) != str((pack or {}).get("target_date")):
        errors.append("大模型研判目标日与输入包不一致")
    if judgement.get("structural_bias") not in STRUCTURAL_VALUES:
        errors.append("大模型研判的结构偏向非法")
    if judgement.get("window_state") not in WINDOW_VALUES:
        errors.append("大模型研判的窗口状态非法")
    if judgement.get("execution_state") not in EXECUTION_VALUES:
        errors.append("大模型研判的执行状态非法")
    if judgement.get("execution_action") not in ACTION_VALUES:
        errors.append("大模型研判的执行动作非法")
    if judgement.get("risk_state") not in RISK_STATES:
        errors.append("大模型研判的风险状态非法")
    if not isinstance(judgement.get("abstain"), bool):
        errors.append("大模型研判的 abstain 必须为布尔值")
    errors.extend(
        validate_next_day_path(
            judgement.get("next_day_path"),
            str(judgement.get("structural_bias")),
            (pack or {}).get("level_context") or {},
        )
    )
    for field, minimum in (
        ("structure_reason", 2),
        ("structure_opposition", 1),
        ("structure_invalidation", 1),
        ("baseline_path_invalidation", 1),
        ("supporting_evidence", 2),
        ("opposing_evidence", 1),
        ("action_maintenance", 1),
        ("action_invalidation", 1),
        ("evidence_refs", 1),
    ):
        value = judgement.get(field)
        if not isinstance(value, list) or len(
            [item for item in value if str(item).strip()]
        ) < minimum:
            errors.append(f"{field} 至少需要 {minimum} 条")
    refs = judgement.get("evidence_refs")
    if isinstance(refs, list):
        missing_refs = []
        for reference in refs:
            text = str(reference or "").strip()
            ref_path = text[2:] if text.startswith("$.") else text
            current: object = pack
            for part in ref_path.split(".") if ref_path else []:
                if not isinstance(current, dict) or part not in current:
                    current = None
                    break
                current = current[part]
            if current in (None, "", [], {}):
                missing_refs.append(text)
        if missing_refs:
            errors.append(f"evidence_refs 包含不存在或为空的证据：{missing_refs}")
    for label in ("向上切换", "向下切换", "尾部风险"):
        if label not in report:
            errors.append(f"报告缺少{label}")

    if forecast is None:
        errors.append("缺少 forecast，无法核对大模型研判")
    else:
        if forecast.get("llm_judgement") != judgement:
            errors.append("forecast 未原样冻结大模型研判")
        if forecast.get("judgement_source") != "llm":
            errors.append("forecast.judgement_source 必须为 llm")
        for judgement_field, forecast_field in (
            ("structural_bias", "structural_bias"),
            ("window_state", "window_state"),
            ("next_day_path", "next_day_path"),
            ("structure_invalidation", "structure_invalidation"),
            ("baseline_path_invalidation", "baseline_path_invalidation"),
            ("execution_state", "execution_state"),
            ("execution_action", "action_bias"),
            ("abstain", "abstain"),
        ):
            if judgement.get(judgement_field) != forecast.get(forecast_field):
                errors.append(f"{forecast_field} 与大模型研判不一致")
    if errors:
        add(checks, "llm_judgement", "fail", "大模型结构与路径研判不完整或与 forecast 不一致", errors=errors)
        return
    add(checks, "llm_judgement", "pass", "大模型结构、三段路径、切换条件与理由契约齐备")


def check_critical_evidence(
    report: str,
    pack: dict | None,
    forecast: dict | None,
    checks: list,
) -> None:
    """Validate factual evidence only; llm_judgement is the sole decision copy."""
    del forecast  # Decisions are checked against llm_judgement, never duplicated here.
    if pack is None:
        add(checks, "critical_evidence", "fail", "缺少输入包，无法检查核心交易证据")
        return
    block = pack.get("critical_evidence")
    required = (
        "conditional_base_rates",
        "unmatched_rates_not_used",
        "critical_levels",
    )
    if not isinstance(block, dict):
        add(checks, "critical_evidence", "fail", "输入包缺少 critical_evidence 区块")
        return
    missing = [field for field in required if field not in block or block.get(field) in (None, "")]
    if missing:
        add(checks, "critical_evidence", "fail", "核心交易证据字段不完整", missing_fields=missing)
        return
    decision_copies = sorted(
        {"core_thesis", "next_day_baseline", "structure_path_audit", "direction_audit"}.intersection(block)
    )
    if decision_copies:
        add(
            checks,
            "critical_evidence",
            "fail",
            "核心证据层不得保存研判副本；唯一研判来源是 llm_judgement",
            decision_copies=decision_copies,
        )
        return
    if "核心交易判断" not in report[:12000]:
        add(checks, "critical_evidence", "fail", "报告正文前部缺少“核心交易判断”，关键信息仍可能被后文淹没")
        return

    rates = block.get("conditional_base_rates") or []
    if not isinstance(rates, list):
        add(checks, "critical_evidence", "fail", "conditional_base_rates 必须是列表")
        return
    for row in rates:
        absent = [
            field
            for field in ("state_key", "definition", "current_match", "n", "next_day_up_rate", "source")
            if field not in row
        ]
        if absent:
            add(
                checks,
                "critical_evidence",
                "fail",
                "条件基率记录不完整",
                state_key=row.get("state_key"),
                missing_fields=absent,
            )
            return
        if row.get("used_in_judgement") and row.get("current_match") is not True:
            add(
                checks,
                "critical_evidence",
                "fail",
                "不匹配当前状态的条件基率被用于综合裁量",
                state_key=row.get("state_key"),
            )
            return

    levels = block.get("critical_levels") or []
    if not isinstance(levels, list) or len(levels) < 2:
        add(checks, "critical_evidence", "fail", "critical_levels 至少需要向下和向上两个交易位")
        return
    if any("level" not in row or "role" not in row for row in levels):
        add(checks, "critical_evidence", "fail", "critical_levels 每项都必须包含 level 与 role")
        return

    add(checks, "critical_evidence", "pass", "条件基率与关键交易位事实齐备，未保存重复研判")


def check_external_integrity(report: str, pack: dict | None, checks: list) -> None:
    if pack is None:
        add(checks, "external_snapshot_integrity", "fail", "缺少输入包")
        return
    external = pack.get("external_market") or {}
    embedded_snapshot = pack.get("external_snapshot")
    if isinstance(embedded_snapshot, dict):
        if embedded_snapshot.get("ruleset_version") != RULESET_VERSION:
            add(
                checks,
                "external_snapshot_integrity",
                "fail",
                "内嵌外盘快照规则版本与当前技能不一致",
                expected=RULESET_VERSION,
                actual=embedded_snapshot.get("ruleset_version"),
            )
            return
        embedded_market = embedded_snapshot.get("external_market") or {}
        if embedded_market != external:
            add(
                checks,
                "external_snapshot_integrity",
                "fail",
                "输入包 external_market 与内嵌外盘快照不一致",
                pack_codes=sorted(external),
                snapshot_codes=sorted(embedded_market),
            )
            return
    else:
        add(checks, "external_snapshot_integrity", "fail", "输入包缺少 external_snapshot 内嵌快照")
        return
    source_snapshot_missing = False
    snapshot_path = pack.get("external_snapshot_path") or pack.get("asia_live_snapshot_path")
    if snapshot_path:
        path = Path(snapshot_path).expanduser().resolve()
        if not path.is_file():
            source_snapshot_missing = True
        else:
            try:
                snapshot = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                add(checks, "external_snapshot_integrity", "fail", f"外盘快照无法读取：{exc}")
                return
            snapshot_market = snapshot.get("external_market") or snapshot.get("us_anchors_last_close") or {}
            if snapshot_market != external:
                add(
                    checks,
                    "external_snapshot_integrity",
                    "fail",
                    "输入包 external_market 与冻结外盘快照不一致；必须先重新合并",
                    pack_codes=sorted(external),
                    snapshot_codes=sorted(snapshot_market),
                )
                return
    missing = [code for code in EXTERNAL_REQUIRED if code not in external]
    degraded = False
    if missing:
        rating = ((pack.get("information_content") or {}).get("external"))
        gap_fields = {str(item.get("field", "")) for item in (pack.get("data_gap_register") or [])}
        documented = all(any(code in field for field in gap_fields) for code in missing)
        if rating != "uninformative" or not documented:
            add(
                checks,
                "external_snapshot_integrity",
                "fail",
                "外盘锚点缺失时必须将 external 判为 uninformative 并逐项登记缺口",
                missing_anchors=missing,
                external_information_content=rating,
                documented=documented,
            )
            return
        degraded = True
    missing_metadata = []
    for code, row in external.items():
        if not isinstance(row, dict):
            missing_metadata.append({"code": code, "missing": ["record"]})
            continue
        absent = [field for field in ("trade_date", "source", "available_at", "data_quality") if not row.get(field)]
        if absent:
            missing_metadata.append({"code": code, "missing": absent})
    if missing_metadata:
        add(
            checks,
            "external_snapshot_integrity",
            "fail",
            "外盘记录必须逐项带 trade_date/source/available_at",
            incomplete=missing_metadata,
        )
        return
    gold = pack.get("external_gold") or pack.get("gold") or {}
    gold_metadata_missing = []
    for code, row in gold.items():
        if not isinstance(row, dict):
            gold_metadata_missing.append({"code": code, "missing": ["record"]})
            continue
        absent = [field for field in ("trade_date", "source", "available_at", "data_quality") if not row.get(field)]
        if absent:
            gold_metadata_missing.append({"code": code, "missing": absent})
    if gold_metadata_missing:
        add(
            checks,
            "external_snapshot_integrity",
            "fail",
            "黄金记录必须逐项带 trade_date/source/available_at",
            incomplete=gold_metadata_missing,
        )
        return

    try:
        cutoff = parse_cutoff(pack.get("forecast_cutoff"))
    except (TypeError, ValueError):
        add(checks, "external_snapshot_integrity", "fail", "forecast_cutoff 不是可解析的 ISO 时间")
        return
    future_records = []
    unknown_records = []
    for code, row in external.items():
        if not isinstance(row, dict):
            continue
        try:
            if parse_date(row.get("trade_date")).date() > cutoff.date():
                future_records.append(
                    {
                        "code": code,
                        "trade_date": str(row.get("trade_date")),
                        "reason": "trade_date later than cutoff date",
                    }
                )
        except (TypeError, ValueError):
            unknown_records.append(code)
            continue
        available_at = parse_available_at(row.get("available_at"))
        if available_at is None:
            unknown_records.append(code)
        elif available_at > cutoff:
            future_records.append({"code": code, "available_at": available_at.isoformat()})
    if future_records:
        add(
            checks,
            "external_snapshot_integrity",
            "fail",
            "外盘记录晚于 forecast_cutoff",
            future_records=future_records,
        )
        return
    if unknown_records:
        add(
            checks,
            "external_snapshot_integrity",
            "fail",
            "无法证明外盘记录在截点前可得",
            unknown_available_at=unknown_records,
        )
        return

    report_terms = {
        "日经": bool(re.search(r"日经|N225", report)),
        "KOSPI": bool(re.search(r"KOSPI|韩国", report)),
        "澳洲": bool(re.search(r"澳洲|AS51", report)),
        "台湾": bool(re.search(r"台湾|TWII", report)),
        "A50": bool(re.search(r"A50|XIN9|富时中国", report)),
        "恒生": bool(re.search(r"恒生|HSI", report)),
        "SOX": bool(re.search(r"SOX|费城半导体", report)),
    }
    required_terms = ["SOX"]
    if str(pack.get("target_date")) == cutoff.date().isoformat() and cutoff.hour >= 8:
        required_terms.extend(["日经", "KOSPI", "澳洲"])
        if (cutoff.hour, cutoff.minute) >= (9, 0):
            required_terms.extend(["A50", "台湾"])
        if (cutoff.hour, cutoff.minute) >= (9, 35):
            required_terms.append("恒生")
    missing_terms = [term for term in required_terms if not report_terms[term]]
    if missing_terms:
        add(
            checks,
            "external_snapshot_integrity",
            "fail",
            "报告未披露截止时点应覆盖的早开市场或行业锚点",
            missing_terms=missing_terms,
        )
        return

    gap_fields = " ".join(str(item.get("field", "")) for item in (pack.get("data_gap_register") or []))
    market_codes = {"日经": "N225", "KOSPI": "KS11", "澳洲": "AS51", "台湾": "TWII", "A50": "XIN9", "恒生": "HSI"}
    missing_without_gap = []
    for term in required_terms:
        code = market_codes.get(term)
        if not code:
            continue
        present = any(key == code or key.startswith(f"{code}_") for key in external)
        if not present and code not in gap_fields:
            missing_without_gap.append(code)
    if missing_without_gap:
        add(
            checks,
            "external_snapshot_integrity",
            "fail",
            "截止时点已开市市场的快照或缺口登记缺失",
            missing_markets=missing_without_gap,
        )
        return
    if degraded or source_snapshot_missing:
        add(
            checks,
            "external_snapshot_integrity",
            "warning",
            "外盘检查使用内嵌快照通过，但存在缺口或原始快照副本不在当前路径",
            missing_anchors=missing,
            source_snapshot_missing=source_snapshot_missing,
        )
    else:
        add(checks, "external_snapshot_integrity", "pass", "SOX、已开市亚洲市场和逐项时点元数据齐备")


def check_leadership(report: str, pack: dict | None, checks: list) -> None:
    missing = [
        field
        for field in LEADERSHIP_FIELDS
        if field not in report
        and report_labeled_value(report, (field, *LEADERSHIP_LABELS_ZH[field])) is None
    ]
    rebound_mentions = sum(
        report.count(label)
        for label in ("rebound_quality", *LEADERSHIP_LABELS_ZH["rebound_quality"])
    )
    if not missing and rebound_mentions < 2:
        missing.append("rebound_quality（需在情景与反方结论各出现一次）")
    if missing:
        add(checks, "leadership_contract", "fail", "领涨结构必填字段不完整", missing_fields=missing)
        return
    rating = ((pack or {}).get("information_content") or {}).get("leadership")
    leadership = (pack or {}).get("leadership") or {}
    if rating == "informative" and not leadership:
        add(checks, "leadership_contract", "fail", "leadership 被判 informative，但输入包没有龙头状态")
        return
    if leadership.get("state") == "leadership_confirming" and (
        leadership.get("gap_sample_count", 0) == 0 or leadership.get("gap_up_fade_rate") is None
    ):
        add(
            checks,
            "leadership_contract",
            "fail",
            "无高开样本时不能判定 leadership_confirming；应降为 leadership_neutral",
            gap_sample_count=leadership.get("gap_sample_count"),
            gap_up_fade_rate=leadership.get("gap_up_fade_rate"),
        )
        return
    if leadership.get("rebound_quality") == "leadership_repair" and leadership.get("state") != "leadership_confirming":
        add(checks, "leadership_contract", "fail", "leadership_repair 必须同时具备 leadership_confirming")
        return
    add(checks, "leadership_contract", "pass", "领涨六项与 rebound_quality 已披露")


def validate_path_forecasts(
    path: dict,
    structural_bias: str,
    level_context: dict,
) -> list[str]:
    return validate_next_day_path(path, structural_bias, level_context)


def check_forecast_contract(report: str, pack: dict | None, forecast: dict | None, checks: list) -> None:
    required = (
        "prediction_type",
        "decision_stage",
        "ruleset_version",
        "target_date",
        "forecast_cutoff",
        "feature_cutoff",
        "symbol",
        "structural_bias",
        "window_state",
        "next_day_baseline",
        "next_day_path",
        "structure_invalidation",
        "baseline_path_invalidation",
        "execution_state",
        "action_bias",
        "abstain",
        "close_axis",
        "interval_convention",
        "close_bins",
        "level_context",
        "execution_overlay",
        "llm_judgement",
        "judgement_source",
    )
    if forecast is None:
        add(checks, "forecast_contract", "fail", "缺少 forecast record")
        return
    missing = [field for field in required if field not in forecast]
    if missing:
        add(checks, "forecast_contract", "fail", "forecast record 缺少标准字段", missing_fields=missing)
        return
    errors = []
    legacy = sorted({"direction", "confidence", "scenarios", "targets"}.intersection(forecast))
    if legacy:
        errors.append(f"forecast 含旧版权重方向字段：{legacy}")
    if forecast.get("close_axis") != "close":
        errors.append("close_axis 必须为 close")
    if forecast.get("interval_convention") != "lower_inclusive_upper_exclusive":
        errors.append("interval_convention 必须为 lower_inclusive_upper_exclusive")
    if pack:
        for field in ("prediction_type", "target_date", "ruleset_version"):
            if forecast.get(field) != pack.get(field):
                errors.append(f"{field} 与输入包不一致")
        if forecast.get("level_context") != pack.get("level_context"):
            errors.append("forecast 与输入包的点位事实包不一致")
    for field in (
        "structural_bias",
        "window_state",
        "next_day_baseline",
        "execution_state",
        "action_bias",
        "abstain",
    ):
        report_value_text = report_value(report, field)
        forecast_value_text = str(forecast.get(field)).lower()
        if report_value_text is not None and report_value_text != forecast_value_text:
            errors.append(f"{field} 报告与 forecast 不一致：{report_value_text!r} != {forecast_value_text!r}")
    for field, allowed in (
        ("structural_bias", STRUCTURAL_VALUES),
        ("window_state", WINDOW_VALUES),
        ("execution_state", EXECUTION_VALUES),
        ("action_bias", ACTION_VALUES),
    ):
        if forecast.get(field) not in allowed:
            errors.append(f"{field} 枚举值非法：{forecast.get(field)!r}")
    for field, zone_name in (
        ("opening_zone", "opening"),
        ("intraday_zone", "intraday"),
        ("close_zone", "close"),
    ):
        zone = (forecast.get("next_day_path") or {}).get(zone_name) or {}
        try:
            expected = f"{float(zone['lower']):.2f}-{float(zone['upper']):.2f}"
            actual = (report_field_raw(report, field) or "").replace("`", "").replace(" ", "")
            if actual != expected:
                errors.append(f"{field} 报告与 forecast 不一致：{actual!r} != {expected!r}")
        except (KeyError, TypeError, ValueError):
            errors.append(f"{field} 无法核对数值区间")
    character_zh = {"strong": "偏强", "weak": "偏弱", "balanced": "平衡"}
    if report_field_raw(report, "close_character") != character_zh.get(forecast.get("close_character")):
        errors.append("收盘性质报告与 forecast 不一致")
    errors.extend(
        validate_path_forecasts(
            forecast.get("next_day_path") or {},
            str(forecast.get("structural_bias")),
            forecast.get("level_context") or {},
        )
    )
    close_bins = forecast.get("close_bins") or []
    errors.extend(validate_close_bins(close_bins, str(forecast.get("interval_convention"))))
    for row in close_bins:
        if not str(row.get("close_condition") or "").strip():
            errors.append(f"{row.get('name')} 缺少收盘结算条件")
    if errors:
        add(checks, "forecast_contract", "fail", "forecast record 不符合结构与路径契约", errors=errors)
        return
    add(checks, "forecast_contract", "pass", "forecast 元数据、三段路径与收盘结算轴齐备")


def check_execution_overlay(report: str, pack: dict | None, forecast: dict | None, checks: list) -> None:
    """Validate point-in-time execution facts; the LLM owns all action decisions."""
    if pack is None or forecast is None:
        add(checks, "execution_overlay", "fail", "缺少输入包或 forecast，无法校验执行事实层")
        return
    overlay = forecast.get("execution_overlay")
    if not isinstance(overlay, dict):
        add(checks, "execution_overlay", "fail", "forecast.execution_overlay 必须是对象")
        return
    required = (
        "ruleset_version", "stage", "target_date", "data_asof", "available_at",
        "source", "data_quality", "gap_state", "pressure_state",
        "participation_state", "metrics", "decision_mode", "setup_evidence",
        "thresholds", "invalidation", "valid_for", "next_review", "data_gaps",
    )
    errors = [f"缺少字段：{field}" for field in required if field not in overlay]
    if errors:
        add(checks, "execution_overlay", "fail", "执行事实层字段不完整", errors=errors)
        return
    forbidden = (
        "setup_state", "risk_state", "execution_bias", "action_rationale",
        "defensive_trigger", "offensive_trigger", "conditional_path",
    )
    errors.extend(f"执行事实层禁止生成裁决字段：{field}" for field in forbidden if field in overlay)
    metrics = overlay.get("metrics") if isinstance(overlay.get("metrics"), dict) else {}
    for field in ("setup_score", "setup_known_checks", "setup_unknown_checks"):
        if field in metrics:
            errors.append(f"执行事实层禁止生成评分字段：metrics.{field}")
    if overlay != pack.get("execution_overlay"):
        errors.append("pack 与 forecast 的 execution_overlay 必须完全一致")
    if overlay.get("ruleset_version") != RULESET_VERSION:
        errors.append("execution_overlay.ruleset_version 与当前技能不一致")
    for field in ("stage", "target_date"):
        if overlay.get(field) != pack.get("decision_stage" if field == "stage" else field):
            errors.append(f"execution_overlay.{field} 与输入包不一致")
    if forecast.get("decision_stage") != pack.get("decision_stage"):
        errors.append("forecast.decision_stage 与输入包不一致")
    for field in ("source", "data_quality", "valid_for", "next_review"):
        if not isinstance(overlay.get(field), str) or not overlay.get(field).strip():
            errors.append(f"{field} 必须是非空文本")
    for field, allowed in (
        ("gap_state", GAP_STATES),
        ("pressure_state", PRESSURE_STATES),
        ("participation_state", PARTICIPATION_STATES),
    ):
        if overlay.get(field) not in allowed:
            errors.append(f"{field} 枚举非法：{overlay.get(field)!r}")
    if overlay.get("decision_mode") not in ("premarket_facts", "combined"):
        errors.append("decision_mode 必须是 premarket_facts 或 combined")
    evidence_rows = overlay.get("setup_evidence")
    expected_evidence = {
        "active_key_window", "pressure_proximity", "external_extreme",
        "recent_path_pressure", "confirmation_deficit",
    }
    if not isinstance(evidence_rows, list):
        errors.append("setup_evidence 必须是盘前风险事实列表")
    else:
        names = [row.get("name") for row in evidence_rows if isinstance(row, dict)]
        if len(evidence_rows) != len(expected_evidence) or set(names) != expected_evidence:
            errors.append("setup_evidence 必须恰好包含五项客观风险事实，不得包含 structural_bearish")
        invalid_evidence = []
        for row in evidence_rows:
            if not isinstance(row, dict):
                invalid_evidence.append({"row": row, "reason": "不是对象"})
                continue
            status = row.get("status")
            value = row.get("value")
            if status not in SETUP_EVIDENCE_STATES:
                invalid_evidence.append({"name": row.get("name"), "reason": "状态非法", "status": status})
            elif status == "unknown" and value is not None:
                invalid_evidence.append({"name": row.get("name"), "reason": "未知状态的值必须为空"})
            elif status == "met" and value is not True:
                invalid_evidence.append({"name": row.get("name"), "reason": "成立状态的值必须为真"})
            elif status == "not_met" and value is not False:
                invalid_evidence.append({"name": row.get("name"), "reason": "不成立状态的值必须为假"})
            if not str(row.get("detail") or "").strip():
                invalid_evidence.append({"name": row.get("name"), "reason": "缺少证据说明"})
        if invalid_evidence:
            errors.append(f"setup_evidence 三值结构非法：{invalid_evidence}")
    for field in ("metrics", "thresholds"):
        if not isinstance(overlay.get(field), dict):
            errors.append(f"{field} 必须是对象")
    context = pack.get("level_context") or {}
    thresholds = overlay.get("thresholds") or {}
    if context and isinstance(thresholds, dict):
        band = context.get("decision_band") or {}
        anchors = set()
        for row in context.get("price_anchors") or []:
            try:
                anchors.add(round(float(row["price"]), 2))
            except (KeyError, TypeError, ValueError):
                continue
        try:
            pressure_low = float(thresholds["pressure_low"])
            pressure_high = float(thresholds["pressure_high"])
            support = float(thresholds["support"])
            expected_low = float(band["support_defense"])
            expected_high = float(band["pressure_defense"])
        except (KeyError, TypeError, ValueError):
            errors.append("执行事实层缺少有效压力/支撑阈值或当前决策带")
        else:
            for name, value in (
                ("pressure_low", pressure_low),
                ("pressure_high", pressure_high),
                ("support", support),
            ):
                if round(value, 2) not in anchors:
                    errors.append(f"execution_overlay.thresholds.{name}={value} 不在当前登记锚点中")
            if abs(support - expected_low) > 0.011:
                errors.append("execution_overlay 支撑必须等于 level_context.decision_band.support_defense")
            if abs(pressure_high - expected_high) > 0.011:
                errors.append("execution_overlay 压力防线必须等于 level_context.decision_band.pressure_defense")
            if not support < pressure_low <= pressure_high:
                errors.append("execution_overlay 阈值必须满足 support < pressure_low <= pressure_high")
    if not isinstance(overlay.get("invalidation"), list) or not overlay.get("invalidation"):
        errors.append("invalidation 必须是非空列表")
    if not isinstance(overlay.get("data_gaps"), list):
        errors.append("data_gaps 必须是列表")
    if not any(marker in report for marker in ("执行风险事实", "执行覆盖", "execution_overlay")):
        errors.append("报告缺少独立的执行风险事实小节")
    if "操作建议理由" not in report and "操作理由" not in report:
        errors.append("报告缺少大模型操作建议及其理由说明")
    required_report_markers = {
        "覆盖失效": ("覆盖失效", "执行覆盖失效"),
        "动作维持条件": ("动作维持条件",),
        "动作解除条件": ("动作解除条件", "动作失效条件"),
    }
    missing_report_markers = [
        label
        for label, aliases in required_report_markers.items()
        if not any(alias in report for alias in aliases)
    ]
    if missing_report_markers:
        errors.append(f"报告缺少执行条件字段：{missing_report_markers}")
    try:
        cutoff = parse_cutoff(pack["forecast_cutoff"])
        available = parse_available_at(overlay.get("available_at"))
        if available is None or available > cutoff:
            errors.append("execution_overlay.available_at 无法解析或晚于 forecast_cutoff")
        if parse_date(overlay.get("data_asof")).date() > parse_cutoff(pack["feature_cutoff"]).date():
            errors.append("execution_overlay.data_asof 晚于 feature_cutoff")
        if pack.get("decision_stage") == "preopen_0925":
            target_day = parse_date(pack["target_date"]).date()
            if cutoff.date() != target_day or (cutoff.hour, cutoff.minute, cutoff.second) != (9, 25, 0):
                errors.append("preopen_0925 的 forecast_cutoff 必须为目标日 09:25:00")
            state_inputs = pack.get("state_inputs") or {}
            state_asof = state_inputs.get("data_asof") or state_inputs.get("asof")
            if not state_asof or parse_date(state_asof).date() >= target_day:
                errors.append("09:25 的日线 state_inputs 必须严格截至 T-1；目标日快照只能进入覆盖层")
            if parse_date(overlay.get("data_asof")).date() != target_day:
                errors.append("09:25 execution_overlay.data_asof 必须为目标日快照")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"执行事实层时点无法审计：{exc}")
    if errors:
        add(checks, "execution_overlay", "fail", "执行事实层不符合客观事实或点时契约", errors=errors)
        return
    if overlay.get("data_gaps"):
        add(
            checks, "execution_overlay", "warning",
            "执行事实存在缺口；大模型须说明影响，不得把缺失解释为中性",
            data_gaps=overlay.get("data_gaps"),
        )
        return
    add(checks, "execution_overlay", "pass", "缺口、压力、参与度与盘前风险事实齐备，未生成代码操作裁决")


def check_manifest(
    manifest_path: str | None,
    pack: dict | None,
    report_path: str,
    pack_path: str | None,
    forecast_path: str | None,
    checks: list,
) -> None:
    if not manifest_path:
        add(checks, "snapshot_manifest", "fail", "终检未传 --manifest；该报告不能视为冻结归档")
        return
    path = Path(manifest_path).expanduser().resolve()
    if not path.is_file():
        add(checks, "snapshot_manifest", "fail", f"manifest 不存在：{path}")
        return
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        add(checks, "snapshot_manifest", "fail", f"manifest 无法读取：{exc}")
        return
    errors = []
    if pack:
        for field in ("prediction_type", "forecast_cutoff", "target_date", "ruleset_version"):
            if manifest.get(field) != pack.get(field):
                errors.append(f"{field} 不一致：manifest={manifest.get(field)!r}, pack={pack.get(field)!r}")
        stage_map = {
            "backfill": "backfill",
            "premarket": "premarket",
            "preopen_0925": "premarket",
            "intraday_open": "intraday",
            "intraday_update": "intraday",
            "post_close_review": "postclose",
        }
        expected_stage = (
            "backfill"
            if pack.get("prediction_type") == "backfill"
            else stage_map.get(pack.get("decision_stage"))
        )
        if expected_stage and manifest.get("stage") != expected_stage:
            errors.append(f"stage 不一致：manifest={manifest.get('stage')!r}, expected={expected_stage!r}")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        errors.append("manifest.files 为空")
    else:
        for item in files:
            relative = item.get("path")
            expected = item.get("sha256")
            if not relative or not expected:
                errors.append("manifest file 记录缺少 path/sha256")
                continue
            target = (path.parent / relative).resolve()
            if not target.is_file():
                errors.append(f"冻结文件丢失：{relative}")
                continue
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if digest != expected:
                errors.append(f"冻结文件哈希变化：{relative}")
    if isinstance(files, list):
        frozen_paths = {str(item.get("path")) for item in files if isinstance(item, dict)}
        for label, candidate in (
            ("report", report_path),
            ("pack", pack_path),
            ("forecast", forecast_path),
        ):
            if not candidate:
                continue
            candidate_path = Path(candidate).expanduser().resolve()
            try:
                relative = candidate_path.relative_to(path.parent).as_posix()
            except ValueError:
                errors.append(f"{label} 不在阶段目录内，无法由该 manifest 冻结")
                continue
            if relative not in frozen_paths:
                errors.append(f"{label} 未被 manifest 收录：{relative}")
    if errors:
        add(checks, "snapshot_manifest", "fail", "快照 manifest 校验失败", errors=errors)
        return
    add(checks, "snapshot_manifest", "pass", f"已校验 {len(files)} 个冻结文件")


def check_future_function(report: str, pack: dict | None, checks: list) -> None:
    if pack is None:
        add(checks, "future_function_audit", "fail", "缺少输入包（--pack）；无法审计时点与未来函数")
        return
    audit = pack.get("future_function_audit")
    missing = [k for k in ("forecast_cutoff", "feature_cutoff") if not pack.get(k)]
    if not audit:
        add(checks, "future_function_audit", "fail", "输入包缺少 future_function_audit 段", missing_fields=missing)
        return
    if missing:
        add(checks, "future_function_audit", "fail", "输入包缺少截点字段", missing_fields=missing)
        return
    if not audit.get("excluded"):
        add(checks, "future_function_audit", "fail", "future_function_audit 未列出被排除的数据")
        return
    try:
        forecast_cutoff = parse_cutoff(pack["forecast_cutoff"])
        feature_cutoff = parse_cutoff(pack["feature_cutoff"])
        target_day = parse_date(pack["target_date"])
    except (TypeError, ValueError):
        add(checks, "future_function_audit", "fail", "forecast_cutoff/feature_cutoff 无法解析为 ISO 时间")
        return
    if feature_cutoff > forecast_cutoff:
        add(checks, "future_function_audit", "fail", "feature_cutoff 晚于 forecast_cutoff")
        return
    if pack.get("available_data_end"):
        available_end = parse_available_at(pack["available_data_end"])
        if available_end is None:
            add(checks, "future_function_audit", "fail", "available_data_end 无法解析")
            return
        if available_end > forecast_cutoff:
            add(
                checks,
                "future_function_audit",
                "fail",
                "available_data_end 晚于 forecast_cutoff",
                available_data_end=available_end.isoformat(timespec="seconds"),
            )
            return

    future: list[dict] = []
    unverifiable: list[dict] = []

    def walk(value: object, path: str = "$") -> None:
        if isinstance(value, dict):
            available_raw = value.get("available_at")
            if available_raw:
                available = parse_available_at(available_raw)
                if available is None:
                    unverifiable.append({"path": f"{path}.available_at", "value": available_raw})
                elif available > forecast_cutoff:
                    future.append(
                        {
                            "path": f"{path}.available_at",
                            "value": available.isoformat(timespec="seconds"),
                        }
                    )
            data_asof_raw = value.get("data_asof")
            if data_asof_raw:
                try:
                    data_asof = parse_date(data_asof_raw)
                    if data_asof.date() > feature_cutoff.date():
                        future.append(
                            {
                                "path": f"{path}.data_asof",
                                "value": data_asof.strftime("%Y-%m-%d"),
                            }
                        )
                except (TypeError, ValueError):
                    unverifiable.append({"path": f"{path}.data_asof", "value": data_asof_raw})
            for key in ("as_of", "asof", "latest_data_asof"):
                raw_date = value.get(key)
                if not raw_date:
                    continue
                try:
                    observed = parse_date(raw_date)
                    if observed.date() > feature_cutoff.date():
                        future.append(
                            {
                                "path": f"{path}.{key}",
                                "value": observed.strftime("%Y-%m-%d"),
                            }
                        )
                except (TypeError, ValueError):
                    unverifiable.append({"path": f"{path}.{key}", "value": raw_date})
            if value.get("confirm_date"):
                try:
                    confirmed = parse_date(value["confirm_date"])
                    if confirmed >= target_day:
                        future.append(
                            {
                                "path": f"{path}.confirm_date",
                                "value": confirmed.strftime("%Y-%m-%d"),
                                "reason": "anchor confirmation must be strictly before target_date",
                            }
                        )
                except (TypeError, ValueError):
                    unverifiable.append({"path": f"{path}.confirm_date", "value": value.get("confirm_date")})
            for key, child in value.items():
                if key not in ("available_at", "data_asof", "as_of", "asof", "latest_data_asof", "confirm_date"):
                    walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(pack)
    for index, row in enumerate(pack.get("recent_5d_raw") or []):
        if not isinstance(row, dict):
            unverifiable.append({"path": f"$.recent_5d_raw[{index}]", "value": None})
            continue
        for field in ("data_asof", "available_at", "source", "data_quality"):
            if not row.get(field):
                unverifiable.append({"path": f"$.recent_5d_raw[{index}].{field}", "value": None})

    observation_nodes = [
        *OBSERVATION_NODE_SCHEMAS.items(),
        (
            "space_levels.level_registry_summary",
            {
                "date_fields": ("data_asof", "as_of", "asof"),
                "required": ("available_at", "source", "data_quality"),
            },
        ),
    ]
    for node, schema in observation_nodes:
        value = pack
        for part in node.split("."):
            value = (value or {}).get(part) if isinstance(value, dict) else None
        if not isinstance(value, dict):
            unverifiable.append({"path": f"$.{node}", "value": None})
            continue
        if not any(value.get(field) for field in schema["date_fields"]):
            unverifiable.append(
                {
                    "path": f"$.{node}",
                    "value": None,
                    "reason": f"missing one of {schema['date_fields']}",
                }
            )
        for field in schema["required"]:
            if not value.get(field):
                unverifiable.append({"path": f"$.{node}.{field}", "value": None})
    if future:
        add(
            checks,
            "future_function_audit",
            "fail",
            "存在晚于决策截点或特征截点的时间戳",
            future_records=future[:30],
        )
        return
    if unverifiable:
        add(
            checks,
            "future_function_audit",
            "fail",
            "存在无法证明可得时间的字段，不能进入正式预测",
            unverifiable=unverifiable[:30],
        )
        return
    if audit.get("status") != "passed":
        add(
            checks,
            "future_function_audit",
            "fail",
            "future_function_audit.status 必须为 passed",
            actual=audit.get("status"),
        )
        return
    add(checks, "future_function_audit", "pass", "所有带时间戳记录均不晚于决策截点")


def check_information_content(report: str, pack: dict | None, checks: list) -> None:
    raw_values = {
        layer: report_labeled_value(report, (layer, *INFORMATION_LAYER_LABELS_ZH[layer]))
        for layer in LAYERS
    }
    missing = [layer for layer, value in raw_values.items() if value is None]
    if missing:
        add(
            checks,
            "information_content",
            "fail",
            "报告未逐层给出 information_content",
            missing_layers=missing,
        )
        return
    report_values = {}
    unrated = []
    for layer in LAYERS:
        raw = raw_values[layer]
        if raw in INFO_VALUES:
            report_values[layer] = raw.lower()
            continue
        translated = next(
            (
                canonical
                for canonical, labels in INFORMATION_VALUE_LABELS_ZH.items()
                if raw in labels
            ),
            None,
        )
        if translated:
            report_values[layer] = translated
            continue
        unrated.append(layer)
    if unrated:
        add(
            checks,
            "information_content",
            "fail",
            "存在未判定信息量等级的输入层（informative/weak/uninformative）",
            unrated_layers=unrated,
        )
        return
    pack_values = (pack or {}).get("information_content")
    state_values = ((pack or {}).get("state_inputs") or {}).get("information_content")
    if not isinstance(pack_values, dict):
        add(checks, "information_content", "fail", "输入包缺少 information_content")
        return
    if state_values and pack_values != state_values:
        add(
            checks,
            "information_content",
            "fail",
            "输入包 information_content 与 state_inputs 不一致",
            pack=pack_values,
            state_inputs=state_values,
        )
        return
    invalid = {key: value for key, value in pack_values.items() if key not in LAYERS or value not in INFO_VALUES}
    if invalid:
        add(checks, "information_content", "fail", "输入包 information_content 枚举或层级非法", invalid=invalid)
        return
    mismatches = {
        layer: {"report": report_values.get(layer), "pack": pack_values.get(layer)}
        for layer in LAYERS
        if report_values.get(layer) != pack_values.get(layer)
    }
    if mismatches:
        add(
            checks,
            "information_content",
            "fail",
            "报告 information_content 与输入包不一致",
            mismatches=mismatches,
        )
        return
    add(checks, "information_content", "pass", f"{len(LAYERS)} 层均已判定信息量等级")


def check_close_bin_disclosure(report: str, checks: list) -> None:
    missing = [s for s in SHAPES if not report_has_scenario(report, s)]
    if missing:
        add(
            checks,
            "scenario_set_completeness",
            "fail",
            "收盘结算轴未采用标准四类中文名或机器英文名",
            missing_shapes=missing,
        )
        return
    forbidden = [
        label
        for label in ("置信度", "低确信", "正常确信", "权重领先幅度", "权重确信度", "最高权重")
        if label in report
    ]
    if re.search(r"(?im)^\s*\|[^\n]*\|\s*权重\s*\|", report):
        forbidden.append("权重表列")
    if re.search(r"(?<!无)权重\s*(?:为|=|:|：)\s*\d", report):
        forbidden.append("数值权重")
    if forbidden:
        add(
            checks,
            "weight_free_display",
            "fail",
            "新版报告不得展示权重或置信度",
            forbidden_labels=forbidden,
        )
        return
    add(checks, "close_bin_disclosure", "pass", "四类无权重收盘结算标签齐备")


def check_decidable(report: str, checks: list) -> None:
    """Accept either a compact scenario table or legacy per-scenario sections."""
    blocks = re.split(r"^#{2,4}\s*", report, flags=re.M)
    table_rows = [line for line in report.splitlines() if line.lstrip().startswith("|")]
    undecidable = []
    for shape in SHAPES:
        markers = shape_markers(shape)
        candidates = [
            block
            for block in blocks
            if any(marker in block[:80] for marker in markers)
        ]
        candidates.extend(
            line
            for line in table_rows
            if any(marker in line for marker in markers)
        )
        if not any(
            "收盘" in candidate and re.search(r"\d{3,5}(\.\d+)?", candidate)
            for candidate in candidates
        ):
            undecidable.append(shape)
    if undecidable:
        add(checks, "decidable_close_condition", "fail", "情景缺少可判定的收盘条件（价位或区间+口径）", scenarios=undecidable)
        return
    add(checks, "decidable_close_condition", "pass", "各情景均给出收盘口径的价位/区间条件")


def check_data_gap(report: str, pack: dict | None, checks: list) -> None:
    register = (pack or {}).get("data_gap_register")
    if register is None:
        if re.search(r"数据缺口|data_gap", report):
            add(checks, "data_gap_disclosure", "warning", "输入包没有 data_gap_register，报告仅以文字提及缺口")
            return
        add(
            checks,
            "data_gap_disclosure",
            "fail",
            "输入包缺少 data_gap_register 且报告未披露缺口：禁止把任何层标为 complete",
        )
        return
    undocumented = [row for row in register if not row.get("fallback_attempted") and row.get("status") != "ok"]
    if undocumented:
        add(
            checks,
            "data_gap_disclosure",
            "warning",
            "存在未尝试兜底源且未取到的字段（须在报告中显式标注缺口）",
            fields=[row.get("field") for row in undocumented],
        )
        return
    add(checks, "data_gap_disclosure", "pass", f"缺口登记表 {len(register)} 条，均已记录兜底尝试与状态")


def check_attribution(report: str, checks: list) -> None:
    missing = [
        category
        for category in ATTRIBUTIONS
        if category not in report
        and not any(label in report for label in ATTRIBUTION_LABELS_ZH[category])
    ]
    if missing:
        add(
            checks,
            "review_attribution",
            "fail",
            "复盘未按四类归因对账（数据缺口／分类口径／综合裁量／规则缺口）",
            missing_categories=missing,
        )
        return
    add(checks, "review_attribution", "pass", "复盘四类归因齐备")


def check_ledger_and_version(report: str, checks: list) -> None:
    if "rule-ledger" not in report and "rule_ledger" not in report and "无规则变更" not in report:
        add(checks, "rule_ledger", "fail", "报告未说明是否追加 rule-ledger（或明确“无规则变更”）")
    else:
        add(checks, "rule_ledger", "pass", "已声明规则账本处理方式")
    declared = report_value(report, "ruleset_version")
    if declared is None:
        add(checks, "ruleset_version", "fail", "报告未声明所使用的规则版本（ruleset_version）")
    elif declared != RULESET_VERSION:
        add(
            checks,
            "ruleset_version",
            "fail",
            "报告规则版本与当前脚本不一致",
            expected=RULESET_VERSION,
            actual=declared,
        )
    else:
        add(checks, "ruleset_version", "pass", "已声明规则版本")


def check_forecast_partition(forecast: dict | None, checks: list) -> None:
    """The settlement axis must be complete without scenario weights."""
    if forecast is None:
        add(checks, "scenario_partition", "fail", "缺少 forecast record；无法校验收盘结算轴")
        return
    close_bins = forecast.get("close_bins") or []
    errors = validate_close_bins(
        close_bins,
        str(forecast.get("interval_convention") or "lower_inclusive_upper_exclusive"),
    )
    if errors:
        add(checks, "scenario_partition", "fail", "收盘结算轴不合法", errors=errors)
        return
    add(checks, "scenario_partition", "pass", "四类收盘区间连续、无缺口、无重叠且无权重")


def check_level_registry(
    report: str,
    pack: dict | None,
    feature_cutoff: str | None,
    registry_arg: str | None,
    checks: list,
) -> None:
    registry_path = registry_arg or ((pack or {}).get("level_registry_path"))
    summary_inline = ((pack or {}).get("space_levels") or {}).get("level_registry_summary")
    summary = None
    if registry_path:
        path = Path(registry_path).expanduser().resolve()
        if not path.is_file():
            add(checks, "level_registry_gate", "fail", f"关键位登记文件不存在：{path}")
            return
        if path.suffix.lower() == ".json":
            try:
                summary = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                add(checks, "level_registry_gate", "fail", f"关键位摘要无法读取：{exc}")
                return
        else:
            summary_path = path.with_name("level_registry_summary.json")
            if summary_path.is_file():
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary is None and isinstance(summary_inline, dict):
        summary = summary_inline
    if not isinstance(summary, dict):
        add(checks, "level_registry_gate", "fail", "缺少关键位登记摘要；不能发布最近支撑/压力结论")
        return
    mandatory = summary.get("mandatory_gate") or {}
    if summary.get("ruleset_version") != RULESET_VERSION:
        add(
            checks,
            "level_registry_gate",
            "fail",
            "关键位登记规则版本与当前技能不一致",
            expected=RULESET_VERSION,
            actual=summary.get("ruleset_version"),
        )
        return
    if mandatory.get("passed") is not True:
        add(
            checks,
            "level_registry_gate",
            "fail",
            "关键位登记的强制检查未通过",
            checks=summary.get("checks"),
        )
        return
    if feature_cutoff:
        try:
            feature_day = parse_cutoff(feature_cutoff).date()
            registry_day = parse_date(summary.get("as_of") or summary.get("asof")).date()
            if registry_day > feature_day:
                add(
                    checks,
                    "level_registry_gate",
                    "fail",
                    "关键位登记使用了晚于 feature_cutoff 的数据",
                    registry_asof=registry_day.isoformat(),
                    feature_cutoff=feature_cutoff,
                )
                return
        except (TypeError, ValueError):
            add(checks, "level_registry_gate", "fail", "关键位摘要缺少可审计的 as_of")
            return
    orphan_checks = [
        item for item in (summary.get("checks") or []) if item.get("check") == "orphan_scan"
    ]
    orphan_levels = [
        float(row["level"])
        for check in orphan_checks
        for row in (check.get("levels") or [])
        if row.get("level") is not None
    ]
    undisclosed = []
    for level in orphan_levels:
        if not re.search(rf"{level:.2f}", report):
            undisclosed.append(level)
    if undisclosed:
        add(
            checks,
            "level_registry_gate",
            "fail",
            "关键位孤立项未在报告中逐项披露",
            undisclosed_levels=undisclosed,
        )
        return
    bands = summary.get("same_origin_bands") or []
    weak_bands = [
        row
        for row in bands
        if row.get("cluster_type") == "same_origin_cluster" and not row.get("formation_window")
    ]
    if weak_bands:
        add(checks, "level_registry_gate", "fail", "same_origin_cluster 缺少 formation_window", bands=weak_bands)
        return
    support_defenses = [
        float(row["defense_level"])
        for row in bands
        if row.get("kind") == "支撑" and row.get("defense_level") is not None
    ]
    pressure_defenses = [
        float(row["defense_level"])
        for row in bands
        if row.get("kind") == "压力" and row.get("defense_level") is not None
    ]
    critical_levels = ((pack or {}).get("critical_evidence") or {}).get("critical_levels") or []
    by_role = {str(row.get("role")): float(row.get("level")) for row in critical_levels if row.get("level") is not None}
    mismatch = []
    if support_defenses and by_role.get("downside_confirmation") is not None:
        expected = min(support_defenses)
        actual = by_role["downside_confirmation"]
        if abs(actual / expected - 1) > 0.0025:
            mismatch.append({"role": "downside_confirmation", "actual": actual, "registry": expected})
    if pressure_defenses and by_role.get("upside_confirmation") is not None:
        expected = max(pressure_defenses)
        actual = by_role["upside_confirmation"]
        if abs(actual / expected - 1) > 0.0025:
            mismatch.append({"role": "upside_confirmation", "actual": actual, "registry": expected})
    if mismatch:
        add(
            checks,
            "level_registry_gate",
            "fail",
            "关键交易位与关键位登记的带外侧防线不一致",
            mismatches=mismatch,
        )
        return
    add(
        checks,
        "level_registry_gate",
        "pass",
        "关键位登记、时点与孤立位披露均通过",
        bands=len(bands),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Direction-layer mandatory gate")
    parser.add_argument("--report", required=True, help="简洁方向报告 Markdown 绝对路径")
    parser.add_argument("--audit", help="审计附录 audit.md；领涨和复盘字段可与报告合并检查")
    parser.add_argument("--pack", help="direction_input_pack.json 绝对路径")
    parser.add_argument("--forecast", help="forecast record json（三段路径与无权重收盘区间）绝对路径")
    parser.add_argument("--level-registry", help="level_registry.csv 或 level_registry_summary.json")
    parser.add_argument("--manifest", help="阶段快照 snapshot_manifest.json 绝对路径")
    parser.add_argument("--preflight", action="store_true", help="预检模式：不检查 manifest，用于确定 gate_status 后再冻结")
    parser.add_argument("--output", required=True, help="输出目录（绝对路径）")
    args = parser.parse_args()

    report = Path(args.report).read_text(encoding="utf-8")
    audit = ""
    load_errors = []
    pack = None
    forecast = None
    if args.audit:
        try:
            audit = Path(args.audit).read_text(encoding="utf-8")
        except OSError as exc:
            load_errors.append(f"审计附录无法读取：{exc}")
    if args.pack:
        try:
            pack = json.loads(Path(args.pack).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            load_errors.append(f"输入包无法读取：{exc}")
    if args.forecast:
        try:
            forecast = json.loads(Path(args.forecast).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            load_errors.append(f"forecast 无法读取：{exc}")

    review_text = report if not audit else f"{report}\n\n{audit}"
    checks: list[dict] = []
    if load_errors:
        add(checks, "artifact_loading", "fail", "；".join(load_errors))
    else:
        add(checks, "artifact_loading", "pass", "报告、审计附录（如提供）、输入包与 forecast 均可读取")
    check_report_header(report, pack, checks)
    check_numeric_display(review_text, checks)
    check_language_display(review_text, checks)
    check_pack_contract(report, pack, checks)
    check_level_context(pack, checks)
    check_llm_judgement(report, pack, forecast, checks)
    check_critical_evidence(report, pack, forecast, checks)
    check_future_function(report, pack, checks)
    check_external_integrity(report, pack, checks)
    check_information_content(report, pack, checks)
    check_leadership(review_text, pack, checks)
    check_close_bin_disclosure(review_text, checks)
    check_decidable(review_text, checks)
    check_data_gap(report, pack, checks)
    check_attribution(review_text, checks)
    check_ledger_and_version(review_text, checks)
    check_forecast_contract(report, pack, forecast, checks)
    check_execution_overlay(report, pack, forecast, checks)
    check_forecast_partition(forecast, checks)
    check_level_registry(
        report,
        pack,
        (pack or {}).get("feature_cutoff"),
        args.level_registry,
        checks,
    )
    if not args.preflight:
        check_manifest(args.manifest, pack, args.report, args.pack, args.forecast, checks)

    def status_for(rows: list[dict]) -> str:
        if any(row["status"] == "fail" for row in rows):
            return "failed"
        if any(row["status"] == "warning" for row in rows):
            return "passed_with_warnings"
        return "passed"

    preflight_checks = [
        row for row in checks if row.get("check") not in ("snapshot_manifest", "gate_status_consistency")
    ]
    preflight_status = status_for(preflight_checks)
    declared = report_value(report, "gate_status")
    if args.preflight and declared == "pending":
        add(
            checks,
            "gate_status_consistency",
            "pass",
            f"预检完成；冻结前应将报告头 gate_status 更新为 {preflight_status!r}",
        )
    elif declared == preflight_status:
        add(checks, "gate_status_consistency", "pass", "报告头 gate_status 与预检状态一致")
    else:
        add(
            checks,
            "gate_status_consistency",
            "fail",
            f"报告头 gate_status={declared!r} 与预检状态 {preflight_status!r} 不一致；应在冻结前修正",
        )
    failed = [c for c in checks if c["status"] == "fail"]
    warnings = [c for c in checks if c["status"] == "warning"]
    final_gate_status = status_for(checks)
    gate_status = preflight_status if args.preflight else final_gate_status
    gate = {
        "report": str(Path(args.report).resolve()),
        "audit": str(Path(args.audit).resolve()) if args.audit else None,
        "pack": str(Path(args.pack).resolve()) if args.pack else None,
        "preflight": bool(args.preflight),
        "gate_status": gate_status,
        "preflight_status": preflight_status,
        "final_gate_status": None if args.preflight else final_gate_status,
        "failed_count": len(failed),
        "warning_count": len(warnings),
        "checks": checks,
        "rule": (
            "preflight 决定报告头 gate_status；冻结后只运行外部终检，"
            "不得修改已冻结报告。final_gate_status=failed 时整份快照作废，返回预检修复。"
        ),
    }
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output / "direction_gate.json", gate)

    print(f"gate_status = {gate['gate_status']}（fail {len(failed)} / warning {len(warnings)}）")
    for check in checks:
        detail = check["detail"]
        extra = {k: v for k, v in check.items() if k not in ("check", "status", "detail")}
        print(f"  [{check['status']:7s}] {check['check']}: {detail}" + (f" {extra}" if extra else ""))
    return 1 if final_gate_status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
