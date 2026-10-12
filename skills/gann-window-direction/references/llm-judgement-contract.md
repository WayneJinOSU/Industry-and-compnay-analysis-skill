# 大模型判断协议

## 定位

大模型是结构化证据上的综合判断器，不是行情数据计算器。它不得自行补造：

- 江恩时间点；
- 江恩空间位；
- 波浪计数；
- 外盘涨跌；
- 成交量阈值；
- 目标价格。

## 输入事件包

```json
{
  "decision_stage": "premarket|intraday_open|intraday_update|post_close_review",
  "forecast_cutoff": "YYYY-MM-DD HH:MM:SS+08:00",
  "data_source_priority": ["kh", "tushare", "wencai"],
  "source_used": {},
  "fallback_reason": {},
  "wencai_queries": [],
  "symbol": "...",
  "target_date": "YYYY-MM-DD",
  "gann_result": {},
  "wave_result": {},
  "external_market": {},
  "path_memory": {},
  "space_levels": {},
  "level_interaction": {},
  "volume_price": {
    "sh_volume": null,
    "sz_volume": null,
    "sh_amount": null,
    "sz_amount": null,
    "total_volume": null,
    "total_amount": null,
    "total_amount_change_1d": null,
    "total_amount_ratio_5d": null,
    "total_amount_ratio_20d": null,
    "sh_sz_amount_ratio": null,
    "volume_state": "expanding|contracting|divergent|volume_only|index_proxy|unknown",
    "volume_confirmation": null,
    "volume_divergence": null,
    "data_asof": null,
    "available_at": null,
    "source": null
  },
  "recent_5d_raw": [
    {
      "date": null,
      "open": null,
      "high": null,
      "low": null,
      "close": null,
      "pct_chg": null,
      "volume": null,
      "amount": null,
      "advance_ratio": null,
      "decline_ratio": null,
      "data_asof": null,
      "available_at": null,
      "source": null
    }
  ],
  "recent_5d_summary": {
    "asof": null,
    "trading_dates": [],
    "close_change_5d": null,
    "amount_change_5d": null,
    "volume_change_5d": null,
    "amount_change_1d": null,
    "volume_change_1d": null,
    "amount_down_streak": null,
    "volume_down_streak": null,
    "amount_up_down_pattern": "unknown",
    "positive_days_count": null,
    "negative_days_count": null,
    "breadth_advance_ratio_5d": null,
    "breadth_change_5d": null,
    "recent_path_summary": null,
    "labels": [],
    "amount_basis": "total_market|index_proxy|unknown",
    "data_asof": null,
    "available_at": null,
    "source": null,
    "data_quality": "complete|partial|stale|insufficient"
  },
  "baseline_20d": {
    "amount_vs_5d_median": null,
    "amount_vs_20d_median": null,
    "volume_vs_5d_median": null,
    "volume_vs_20d_median": null,
    "volume_zscore_20d": null,
    "close_vs_20d_ma": null,
    "breadth_vs_20d_avg": null,
    "data_asof": null,
    "available_at": null,
    "source": null,
    "data_quality": "complete|partial|stale|insufficient"
  },
  "margin_financing": {
    "margin_balance": null,
    "margin_balance_change_1d": null,
    "margin_balance_change_5d": null,
    "margin_balance_change_20d": null,
    "margin_buy_amount": null,
    "margin_repay_amount": null,
    "margin_net_buy": null,
    "margin_net_buy_ratio": null,
    "short_balance": null,
    "short_balance_change_1d": null,
    "data_asof": null,
    "available_at": null,
    "state": "accumulating|neutral|deleveraging|stale|unknown",
    "source": null
  },
  "breadth_and_sectors": {}
}
```

## 全浪段证据—判断补充协议

读取[全浪段证据—判断转换](../../weekly-index-wave-scenarios/references/wave-evidence-transition.md)。保留 `wave_result` 原始内容，将其已有评估或基于可得增量证据的补充评估作为 `wave_transition_assessment`；适用于所有活跃浪的启动、延续、结束与浪级切换，不能在融合层补造父级或锚点。

输入/输出可附同名对象，字段定义见上述参考。若消费者不接受扩展字段，另存 `wave_transition_assessment.json` 并在报告引用，不改原协议枚举。至少保存原主计数/最强备选、截点、拐点与趋势状态、活跃浪级及转换阶段、具体证据→采用结论的表、软降级/硬失效和更新历史。未知留null。

盘前只列截点已有状态与未来条件；后来的跟随、回测或结构完成只能在新评估中记录。方向明确但浪段未决时分别裁决，是否弃权仍按原证据质量规则处理。价格/浪段状态不代替正式江恩窗口状态，置信分数不得自动变成概率。

C专项可沿用 `c_wave_assessment` 作补充，但不将其他浪填入C字段；通用对象与专项对象必须一致，不覆盖旧上游结果。

## 必须回答的问题

1. 时间窗口原本具有什么观察意义？
2. 外部市场给出的盘前先验是什么？
3. 前序价格路径是否重复、恶化或被修复？
4. 关键压力/支撑处于拒绝、蓄势、突破还是跌破状态？
5. 波浪结构支持延续、反转还是仍有冲突？
6. 窗口当前向上、向下还是尚未选择？
7. 两市成交量是否同步确认或出现量价背离？
8. 两融是增杠杆、去杠杆、中性还是滞后？数据能否在预测截点前获得？
9. 哪些条件出现后需要改变判断？
10. 当前活跃浪及关键切换分别需要哪些新增证据？每条证据会使原判断保持、增强、降级、失效还是切换备选？拐点、趋势与浪段身份分别如何裁决，哪些仍是未来条件？

## 输出协议

```json
{
  "structural_bias": "bullish|bearish|neutral",
  "window_state": "unresolved|bullish_confirmation|bearish_confirmation|failed_bullish_window|failed_bearish_window",
  "execution_state": "observe|wait_for_confirmation|confirmed|reduce_only|abstain",
  "direction": "bullish|bearish|neutral",
  "scenario_type": "reversal|continuation|false_breakout|false_breakdown|range|ambiguous",
  "confidence": 0,
  "evidence_for": [],
  "evidence_against": [],
  "volume_margin_evidence": [],
  "volume_margin_conflict": [],
  "volume_margin_data_quality": "complete|partial|stale|insufficient",
  "recent_5d_summary": {},
  "bullish_trigger": [],
  "bearish_trigger": [],
  "first_target": null,
  "second_target": null,
  "invalidation": null,
  "action_bias": "observe|add_only_after_confirmation|hold|reduce_only|no_new_long|stop",
  "abstain": false,
  "data_quality": "complete|partial|insufficient"
}
```

`structural_bias` 表示结构方向，`window_state` 表示本次窗口是否完成选择，`execution_state` 表示是否具备立即执行条件；三者不得互相替代。`window_state=unresolved` 不得自动填充 `structural_bias=neutral`。

规则：没有明确结构失效证据时，短线反弹或外盘改善只能降低确认度、改变 `execution_state`，不能抹除已有偏空/偏多结构；“浪段待证”也不能自动生成 `structural_bias=neutral`。

`confidence` 是内部排序分数，不应未经历史校准直接称为真实概率。关键位和目标位必须从输入的已知空间位中选择，不能自由编造。

`volume_margin_data_quality` 规则：

- `complete`：两市成交额（或明确的成交量替代）与两融关键字段均有可审计日期和可得时间；
- `partial`：只有部分两市字段或只有融资/融券的一侧；
- `stale`：数据存在，但最新 `available_at`/`data_asof` 对目标盘前明显滞后；
- `insufficient`：无法形成可审计的两市或两融证据。

若 `volume_margin_conflict` 与价格、关键位或波浪硬约束同等强，优先降低 `confidence`，并考虑 `neutral`/`abstain`。

## 反方检查

在输出前，强制列出至少一条反方证据。若反方证据与主结论同等强，优先输出 `neutral` 或 `abstain`，而不是增加叙事来掩盖冲突。
