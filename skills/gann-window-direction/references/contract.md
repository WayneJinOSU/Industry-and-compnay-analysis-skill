# Artifact and report contract

## Direction input pack

Required top-level fields:

```text
decision_stage
prediction_type
forecast_cutoff
feature_cutoff
target_date
symbol
ruleset_version
source_used
future_function_audit
gann_result
wave_result
external_market
external_gold
external_snapshot
information_content
path_memory
recent_5d_raw
recent_5d_summary
baseline_20d
volume_price
margin_financing
breadth_and_sectors
leadership
critical_evidence
state_inputs
structure_memory
scenario_weighting
llm_judgement
space_levels
execution_overlay
data_gap_register
```

`source_used` records the actual adapter for each field. Do not claim a primary
source that was not queried.

`external_snapshot` is the normalized snapshot embedded by
`scripts/merge_external.py`. The gate compares it byte-for-data with
`external_market`; an external path is only a provenance pointer.

`future_function_audit` must include:

```json
{
  "status": "passed",
  "excluded": ["..."],
  "rule": "..."
}
```

The gate verifies every timestamp, not just the presence of this block.

### Observation-node timestamps

The gate requires an explicit timestamp schema for every decision input:

| Node | Required date field | Other required fields |
|---|---|---|
| `gann_result` | `as_of` | `available_at`, `source` |
| `wave_result` | `latest_data_asof` | `available_at`, `source` |
| `recent_5d_raw[]` / summary | `data_asof` | `available_at`, `source` |
| `volume_price` | `data_asof` | `available_at`, `source` |
| `margin_financing` | `data_asof` | `available_at`, `source` |
| `breadth_and_sectors` | `data_asof` | `available_at`, `source` |
| `path_memory` | `data_asof` | `available_at`, `source` |
| `leadership` | `data_asof` | `available_at`, `source` |
| `state_inputs` | `data_asof` | `available_at`, `source` |
| `structure_memory` | `data_asof` | `available_at`, `source`, `data_quality` |
| `scenario_weighting` | `data_asof` | `available_at`, `source`, `data_quality` |
| `llm_judgement` | `decision_at` | `available_at`, `source`, `data_quality` |
| `execution_overlay` | `data_asof` | `available_at`, `source`, `data_quality` |
| external records | `trade_date` | `available_at`, `source`, `data_quality` |
| gold records | `trade_date` | `available_at`, `source`, `data_quality` |

For intraday runs, `available_at` must come from the actual snapshot time through
`--available-at` or the intraday `forecast_cutoff`. It must not default to 18:00.

## Historical external records

External records use canonical codes and explicit times:

```json
{
  "IXIC": {
    "trade_date": "2026-10-22",
    "close": 26008.86,
    "pct_chg": -2.599,
    "source": "akshare.index_us_stock_sina",
    "available_at": "2026-10-23T05:00:00+08:00",
    "data_quality": "official_session_close_proxy"
  }
}
```

Asia at a cutoff must be a minute snapshot:

```json
{
  "N225": {
    "trade_date": "2026-10-23",
    "snapshot_time": "2026-10-23 09:00:00+08:00",
    "price_at_cutoff": 62242.45,
    "prev_close": 62907.84,
    "pct_chg": -1.0577,
    "source": "gi.finance.sina.com.cn/hq/min",
    "available_at": "2026-10-23 09:00:00+08:00",
    "usage": "cutoff_snapshot_only"
  }
}
```

Do not put a target-day daily close in an Asia premarket record.

## Gap statuses

Use these exact statuses:

```text
missing
provider_error
not_yet_open
closed
stale
future
```

`unknown` is only valid when the source itself cannot distinguish the state and
the limitation is separately documented.

## Leadership block

Required:

```text
target_date
asof
stage
basket_version
basket_size
members_ok
leader_ret
market_equal_weight_ret
leadership_spread
gap_up_fade_rate
gap_sample_count
gap_sample_status
leader_above_rate
leader_rs_4w
state
rebound_quality
members
```

`gap_up_fade_rate=null` with zero qualifying gaps is `not_applicable`, not an
austere pass. A missing sample cannot produce `leadership_confirming`.

## Critical evidence

```json
{
  "core_thesis": "...",
  "modal_scenario": "...",
  "why_this_is_modal": [],
  "conditional_base_rates": [],
  "unmatched_rates_not_used": [],
  "critical_levels": [],
  "direction_audit": {
    "modal_scenario": "...",
    "structural_bias": "bearish",
    "event_direction": "neutral",
    "reason": "..."
  }
}
```

## Structure memory and scenario weighting

```json
{
  "structure_memory": {
    "target_date": "YYYY-MM-DD",
    "data_asof": "YYYY-MM-DD",
    "available_at": "YYYY-MM-DDTHH:MM:SS+08:00",
    "source": "...",
    "data_quality": "complete|partial",
    "close": 0.0,
    "nearest_support": {},
    "nearest_pressure": {},
    "broken_unreclaimed_count": 0,
    "reclaimed_count": 0,
    "recent_path_pressure": {
      "status": "met|not_met|unknown",
      "subtype": "break_unreclaimed|weak_close_near_support|none|unknown",
      "detail": "..."
    },
    "pressure_attempt_memory": {
      "lookback_sessions": 10,
      "bands": [],
      "nearest": {}
    }
  },
  "scenario_weighting": {
    "role": "baseline_reference",
    "data_asof": "YYYY-MM-DD",
    "available_at": "YYYY-MM-DDTHH:MM:SS+08:00",
    "source": "...",
    "data_quality": "complete|partial",
    "baseline_weights": {},
    "adjustments": [],
    "weights": {},
    "top_scenario": "...",
    "second_scenario": "...",
    "confidence_margin": 0.0,
    "low_confidence": false
  },
  "llm_judgement": {
    "source": "llm",
    "target_date": "YYYY-MM-DD",
    "decision_at": "YYYY-MM-DDTHH:MM:SS+08:00",
    "structural_bias": "bearish",
    "window_state": "unresolved",
    "direction": "bearish",
    "scenarios": [],
    "targets": [],
    "execution_state": "reduce_only",
    "execution_action": "reduce_only",
    "risk_state": "preemptive_defensive",
    "confidence": 0.6,
    "supporting_evidence": [],
    "opposing_evidence": [],
    "action_maintenance": [],
    "action_invalidation": [],
    "evidence_refs": [],
    "horizon": "目标交易日",
    "next_review": "下一交易日收盘"
  }
}
```

`scenario_weighting` is a code baseline only. The final weights, direction,
execution state, action and rationale must come from `llm_judgement`; the
forecast must copy that record and use its four scenarios, weights, targets and
action. A final `confidence_margin` below 5 percentage points sets
`low_confidence=true`; prose must not claim a directional edge.

`structure_memory.pressure_attempt_memory` records 10-session pressure tests for
each registered band: test count, failed close count, accepted close count,
consecutive failed tests, last test date/status, sessions since last test,
failed-high descent and test amount ratio. `scenario_weighting` must expose
`range_width_atr` and `range_width_penalty` whenever the decision interval can
be calculated.

## Forecast record

```json
{
  "target_date": "YYYY-MM-DD",
  "prediction_type": "prospective|backfill",
  "decision_stage": "premarket",
  "ruleset_version": "YYYY-MM-DD.N",
  "forecast_cutoff": "YYYY-MM-DDTHH:MM:SS+08:00",
  "feature_cutoff": "YYYY-MM-DDTHH:MM:SS+08:00",
  "symbol": "000001.SH",
  "structural_bias": "bullish|bearish|neutral",
  "window_state": "unresolved|...",
  "direction": "bullish|bearish|neutral",
  "execution_state": "observe|wait_for_confirmation|confirmed|reduce_only|abstain",
  "action_bias": "observe|add_only_after_confirmation|hold|reduce_only|no_new_long|stop",
  "abstain": false,
  "confidence": 0.58,
  "close_axis": "close",
  "interval_convention": "lower_inclusive_upper_exclusive",
  "scenarios": [],
  "targets": [],
  "judgement_source": "llm",
  "llm_judgement": {},
  "execution_overlay": {
    "stage": "premarket",
    "decision_mode": "premarket_setup",
    "setup_state": "risk_zone_euphoria",
    "setup_evidence": [],
    "action_rationale": {
      "recommendation": "reduce_only",
      "recommendation_zh": "只减不加",
      "why_now": [],
      "opposing_evidence": [],
      "action_maintenance": [],
      "action_invalidation": [],
      "horizon": "目标交易日",
      "next_review": "下一交易日收盘"
    },
    "gap_state": "not_applicable",
    "pressure_state": "untested",
    "participation_state": "unknown",
    "risk_state": "preemptive_defensive",
    "execution_bias": "reduce_only"
  },
  "decision_level": "...",
  "invalidation": "...",
  "next_confirmation": {}
}
```

The overlay above is abbreviated. Its complete object, including timestamps,
metrics, thresholds, two-sided triggers, invalidation, conditional paths and
`data_gaps`, is defined in [execution-overlay.md](execution-overlay.md). Copy the
identical complete object into both the input pack and forecast. For
`preopen_0925`, the cutoff is exactly target-day 09:25:00 and daily
`state_inputs.data_asof` remains strictly before target day.

Every `setup_evidence` row declares `status=met|not_met|unknown` and a
consistent boolean-or-null `value`. `metrics.setup_score` counts only `met`;
`setup_known_checks` counts `met` plus `not_met`; `setup_unknown_checks` counts
`unknown`. At least four known checks are required before classifying setup
state.

The `scenarios` array must contain exactly the four required names. Every row has
an explicit direction:

```json
{
  "name": "downside_continuation",
  "direction": "bearish",
  "weight": 0.30,
  "lower": 3500.0,
  "upper": 3602.15,
  "close_condition": "close remains below the support defense",
  "path_forecast": {
    "opening": "flat or lower open",
    "steps": ["failed rebound at the decision-band floor", "renewed break of support"],
    "confirmation": "rebound fails and price accepts below support",
    "targets": [3480.0, 3450.0],
    "invalidation": "close reclaims 3602.15"
  }
}
```

`path_forecast` is mandatory for every scenario. `steps` must contain at least
two ordered observations; `targets` must be non-empty. Do not replace the full
chain with a vague phrase such as "test then rebound". Keep the path forecast
separate from `close_condition`: the path is scored as a path, while the close
bin is classified only by the final close.

Rules:

- weights sum to exactly 1;
- intervals are numeric, contiguous and non-overlapping;
- every interval has `lower < upper`;
- the first interval starts at a finite lower bound (normally 0);
- the final interval includes its upper bound;
- the highest-weight scenario's direction equals the top-level `direction`;
- `downside_continuation.direction` is always `bearish` and represents close below
  the downside defense;
- `range_oscillation.direction` is always `neutral`, displayed as `震荡`;
- `upside_breakout.direction` is always `bullish` and displayed as
  `向上突破`;
- `tail_extreme_down.direction` is always `bearish` in the standard lower-tail bin.

## Report header

The human report presents metadata as a Chinese two-column table:

```markdown
| 报告项目 | 内容 |
|---|---|
| 预测类型 | 历史回放 |
| 规则版本 | 2026-10-25.12 |
| 决策阶段 | 盘前 |
| 预判截点 | 2026-09-22 09:00:00+08:00 |
| 特征截点 | 2026-09-22 09:00:00+08:00 |
| 目标日期 | 2026-09-22 |
| 门禁状态 | 带警告通过 |
```

`门禁状态` is the preflight verdict displayed in Chinese. The gate canonicalizes
it internally. It is not rewritten after freezing.

## Decision card

```markdown
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
```

Dates, timestamps, versions, prices and ratios remain numeric. Field names and
enum values are displayed in Chinese. Canonical English values remain in
forecast and input-pack records.

All human-facing quantitative values use Arabic numerals and normal units. For
example, write `3958.03`, `4.29%`, `9月22日`, `13周` and `0.188倍`; do not write
the equivalent Chinese number words. This applies to prose, evidence tables and
the complete scenario-path table.

Then explain in Chinese:

```text
结构偏向为何成立
窗口状态为何如此
什么会推翻结构偏向
什么会确认执行状态
```

## Report body

`report.md` is the decision brief, not a dump of every intermediate artifact.
Keep it to five sections:

1. Header and one decision card.
2. Core trading judgment: one conclusion, at least two decision-relevant
   supporting observations and the strongest opposing evidence. State that the
   final comprehensive judgement is the validated LLM decision, while code
   supplies data, baseline weights and risk constraints.
3. Decision evidence: one compact table for external mapping, path, breadth,
   funding, leadership, broken-level memory and low-confidence weighting; state
   important gaps and unmatched base rates here.
4. Critical levels and one four-scenario table. Show only levels used by a
   trigger, target or invalidation. Every row contains the complete ordered
   path forecast, targets and invalidation, separate from the pure close rule.
5. Execution overlay: one compact Chinese table for gap state, pressure state,
   participation state, derived risk/action, defensive trigger, offensive
   trigger and overlay invalidation. The rationale must separately show
   `动作维持条件` and `动作解除条件`. Then give at most three confirmation
   observations. The overlay never changes close-bin weights or ordered path
   forecasts.

Do not repeat the decision card, target lists, cutoff disclaimer or the same
level rationale in later sections. Do not put completed wave ledgers, the full
level ladder, raw leadership fields or review attribution in the brief.

For Chinese user-facing reports, use the standard scenario labels in
[report-language-zh.md](report-language-zh.md): `向下延续`, `区间震荡`,
`向上突破`, `尾部极值（向下）`. Keep canonical English ids in
`forecast_record.json` and other machine-readable artifacts. Report headers,
decision cards and execution-overlay tables must use the Chinese field/value
display contract; raw machine enum blocks are not permitted as the primary
report display.

## Audit appendix

Write `audit.md` alongside the brief. It carries evidence needed for audit, not
a second narrative report:

1. Point-in-time table with actual data date and availability time for A-share,
   US, Europe, gold, Japan, Korea, Australia, Taiwan, Hong Kong and events.
2. Gann/wave ledger, including completed parent waves and long-horizon
   invalidation levels omitted from the brief.
3. Full external table, five-session statistics, leadership fields and basket
   provenance.
4. Full level ladder, formation windows, touch counts and cluster identities.
5. Conditional-rate definitions and unmatched rates.
6. Review attribution (`data_gap`, `classification`, `weighting`, `rule_gap`)
   and the rule-ledger disposition.

Link `audit.md` from the brief. An orphan level required by the level gate must
still be disclosed in `report.md`; moving every warning to the appendix is not
allowed. The gate may read leadership and review fields from the combined brief
and audit text, but machine artifacts remain authoritative.

## Stage directories

```text
outputs/window_direction_YYYYMMDD/
├── premarket/
├── intraday/
├── postclose/
└── backfill/
```

Required stage files:

```text
report.md
audit.md
direction_input_pack.json
forecast_record.json
level_registry.csv
level_ladder.csv
snapshot_manifest.json
gate-preflight/direction_gate.json
gate/direction_gate.json
```

`snapshot_manifest.json` hashes all stage payloads except gate directories,
scorecard directories and the manifest itself. The gate is stored separately and
must not mutate a frozen input.

## Gate outcomes

```text
preflight_status:
  passed
  passed_with_warnings
  failed

final_gate_status:
  passed
  passed_with_warnings
  failed
```

A warning may document a missing but correctly downgraded layer. A hash mismatch,
future timestamp, unverifiable timestamp or structural inconsistency is a hard
failure.

## Scoring

```bash
python3 scripts/scorecard.py \
  --log forecasts.jsonl \
  --index-daily index_history.csv \
  [--append forecast_record.json] \
  --output scorecard
```

The scorecard:

- ignores backfill records in prospective accuracy;
- scores event direction only when the forecast is bullish or bearish;
- reports neutral decisions as abstentions, not as flat outcomes;
- checks the realized close bin with upper-exclusive bounds;
- reports only directional hit rate, top-bin hit rate, in-gap rate and abstention;
  it does not manufacture a probability-calibration score from ranking weights;
- reports in-gap outcomes separately.

Score the execution overlay separately from close bins and ordered paths. Include
avoided drawdown, missed upside, false positives and a no-action baseline; do not
reward earlier defense without measuring its opportunity cost.

## Ruleset

The current schema/rule version is `2026-10-25.12`. All scripts read the version
from `scripts/common.py`; reports and packs must match it.
