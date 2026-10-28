#!/usr/bin/env python3
"""Validation helpers for discretionary, point-anchored next-day paths."""

from __future__ import annotations

import math


FORBIDDEN_JUDGEMENT_KEYS = {
    "weight",
    "weights",
    "scenario_weights",
    "confidence",
    "confidence_margin",
    "low_confidence",
    "top_scenario",
    "second_scenario",
    "direction",
}


def forbidden_keys(value: object, found: list[str] | None = None) -> list[str]:
    found = found if found is not None else []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_JUDGEMENT_KEYS:
                found.append(key)
            forbidden_keys(item, found)
    elif isinstance(value, list):
        for item in value:
            forbidden_keys(item, found)
    return sorted(set(found))


def anchor_prices(level_context: dict) -> set[float]:
    prices = set()
    for row in level_context.get("price_anchors") or []:
        try:
            price = float(row["price"])
            if math.isfinite(price) and price > 0:
                prices.add(round(price, 2))
        except (KeyError, TypeError, ValueError):
            continue
    return prices


def _price(value: object, field: str, anchors: set[float], errors: list[str]) -> None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        errors.append(f"{field} 必须为数值点位")
        return
    if not math.isfinite(price) or price <= 0:
        errors.append(f"{field} 必须为正数点位")
    elif round(price, 2) not in anchors:
        errors.append(f"{field}={price} 不在当前点位事实包的已登记锚点中")


def _zone(
    value: object,
    name: str,
    anchors: set[float],
    errors: list[str],
    *,
    reference: bool = False,
) -> None:
    if not isinstance(value, dict):
        errors.append(f"{name} 必须为对象")
        return
    _price(value.get("lower"), f"{name}.lower", anchors, errors)
    _price(value.get("upper"), f"{name}.upper", anchors, errors)
    try:
        if float(value["lower"]) >= float(value["upper"]):
            errors.append(f"{name} 下界必须小于上界")
    except (KeyError, TypeError, ValueError):
        pass
    if reference:
        _price(value.get("reference_level"), f"{name}.reference_level", anchors, errors)
        if not str(value.get("expectation") or "").strip():
            errors.append("opening.expectation 必须说明开盘位置和强弱性质")


def _switch(value: object, name: str, anchors: set[float], errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{name} 必须为对象")
        return
    if not str(value.get("trigger") or "").strip():
        errors.append(f"{name}.trigger 不能为空")
    _price(value.get("trigger_level"), f"{name}.trigger_level", anchors, errors)
    _price(value.get("close_lower"), f"{name}.close_lower", anchors, errors)
    _price(value.get("close_upper"), f"{name}.close_upper", anchors, errors)
    try:
        if float(value["close_lower"]) >= float(value["close_upper"]):
            errors.append(f"{name} 收盘下界必须小于上界")
    except (KeyError, TypeError, ValueError):
        pass
    if not str(value.get("invalidation") or "").strip():
        errors.append(f"{name}.invalidation 不能为空")


def validate_next_day_path(
    path: object,
    structural_bias: str,
    level_context: dict,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(path, dict):
        return ["next_day_path 必须为对象"]
    if not str(path.get("baseline_summary") or "").strip():
        errors.append("next_day_path.baseline_summary 不能为空")
    anchors = anchor_prices(level_context)
    if not anchors:
        return errors + ["level_context 没有可用价格锚"]
    _zone(path.get("opening"), "opening", anchors, errors, reference=True)
    _zone(path.get("intraday"), "intraday", anchors, errors)
    _zone(path.get("close"), "close", anchors, errors)

    intraday = path.get("intraday") or {}
    steps = intraday.get("ordered_steps")
    if not isinstance(steps, list) or len(steps) < 2:
        errors.append("intraday.ordered_steps 至少需要2个有序节点")
    else:
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                errors.append(f"盘中第{index}个节点必须为对象")
                continue
            if not str(step.get("action") or "").strip():
                errors.append(f"盘中第{index}个节点缺少 action")
            _price(step.get("level"), f"盘中第{index}个节点.level", anchors, errors)
            if not str(step.get("observation") or "").strip():
                errors.append(f"盘中第{index}个节点缺少 observation")
    if not str(intraday.get("acceptance_or_rejection") or "").strip():
        errors.append("intraday.acceptance_or_rejection 不能为空")

    close = path.get("close") or {}
    location = close.get("location")
    if location not in ("center", "upper_edge", "lower_edge", "below_support", "above_pressure"):
        errors.append("close.location 非法")
    else:
        band = level_context.get("decision_band") or {}
        try:
            close_lower = float(close["lower"])
            close_upper = float(close["upper"])
            support = float(band["support_defense"])
            pressure = float(band["pressure_defense"])
            if not all(math.isfinite(value) for value in (close_lower, close_upper, support, pressure)):
                raise ValueError("non-finite geometry")
            if support >= pressure:
                raise ValueError("invalid decision band")
        except (KeyError, TypeError, ValueError):
            errors.append("level_context 缺少有效支撑压力或收盘区，无法校验 close.location")
        else:
            geometry_matches = {
                "below_support": close_upper <= support,
                "above_pressure": close_lower >= pressure,
                "lower_edge": close_lower <= support < close_upper,
                "upper_edge": close_lower < pressure <= close_upper,
                "center": support < close_lower and close_upper < pressure,
            }
            if not geometry_matches[location]:
                errors.append(
                    f"close.location={location} 与收盘区 {close_lower}-{close_upper}、"
                    f"支撑 {support}、压力 {pressure} 的几何关系不一致"
                )
    if close.get("character") not in ("strong", "weak", "balanced"):
        errors.append("close.character 非法")
    for name in ("upside_switch", "downside_switch", "tail_risk"):
        _switch(path.get(name), name, anchors, errors)
    divergence = (
        (structural_bias == "bearish" and close.get("character") == "strong")
        or (structural_bias == "bullish" and close.get("character") == "weak")
    )
    if divergence and not str(path.get("structure_path_divergence") or "").strip():
        errors.append("中期结构与次日收盘性质冲突时必须填写 structure_path_divergence")
    return errors
