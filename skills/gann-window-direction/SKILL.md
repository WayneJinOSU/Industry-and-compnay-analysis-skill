---
name: gann-window-direction
description: Produce point-in-time A-share index direction reports by combining verified Gann time/space, wave structure, structural price levels, external markets, breadth, funding and leadership. Use for premarket/intraday/backfill window decisions, level interaction, scenario construction, gating and post-close attribution. Do not use Gann dates as standalone buy/sell signals.
---

# Gann Window Direction

Turn upstream Gann and wave evidence into an auditable, point-in-time direction
decision. Separate structural bias, event-day direction and execution state.

## Non-negotiable rules

1. Freeze `target_date`, `forecast_cutoff`, `feature_cutoff`, `decision_stage`
   and `prediction_type` before loading evidence.
2. Every input must satisfy `available_at <= forecast_cutoff` and
   `data_asof <= feature_cutoff`. Missing availability time means the input
   cannot support a formal decision.
3. A-share daily data for premarket must end before `target_date`. Asia markets
   use only the historical minute snapshot at or before cutoff. Never substitute
   target-day close data for a premarket snapshot.
4. Gann dates define observation moments, not direction. Price structure and
   accepted close behavior decide the direction.
5. `structural_bias`, `direction` and `execution_state` are independent.
   `direction` is the explicit direction of the highest-weight close bin.
6. Four close bins are mandatory and contiguous. Every bin declares its own
   `direction`; never infer direction from a bin name.
7. A missing evidence layer is `uninformative`, not neutral. Downgrade it only
   when the gap is registered and the layer is excluded from weighting.
8. Do not create a final directional report when a hard gate fails.
9. After a snapshot is frozen, never edit the report, pack or forecast to repair
   a failed final check. Discard that snapshot and return to preflight.
10. Report `backfill` separately. It never enters prospective accuracy.
11. Keep canonical English scenario ids in JSON/CSV and gates. In a Chinese
    user-facing report, lead with the standard Chinese labels below; add a short
    plain-language subtitle when it improves readability.
12. All user-facing narrative must be Chinese-only. This includes the final
    response, report titles, headings, prose, table labels, explanations,
    warnings, display tables and conclusions. Report headers, decision cards and
    execution-overlay displays must translate both field names and enum values
    into Chinese. Keep canonical English identifiers only in JSON/CSV/YAML,
    gate/scorecard artifacts, file paths and required securities identifiers.
    Never expose a raw machine field/value block as the primary report display;
    every report display must have a direct Chinese label and Chinese value.
13. Every action recommendation must include its rationale. State the action,
    at least two forward-looking reasons, at least one strongest opposing
    observation, the conditions that maintain the current action, the conditions
    that release or invalidate it, the applicable horizon and the next review
    point. Never use one ambiguous confirmation field for both maintenance and
    release. Action invalidation contains only evidence that overturns the
    current action.
14. Quantitative values must use Arabic numerals in every human-facing report.
    Prices, percentages, dates, times, durations, amounts, ratios, scores,
    counts and versions must be written as digits with their usual symbols or
    units. Never write `三千九百五十八点零三`, `百分之四点二九`,
    `九月二十二日`, `十三周` or `零点一八八倍`; write `3958.03`, `4.29%`,
    `9月22日`, `13周` and `0.188倍`. Chinese number words are allowed only in
    established qualitative labels such as `第四浪`; navigation and grammar
    phrases such as `下一交易日` are not quantities and must not be rewritten
    as `下1交易日`.

## Upstream inputs

Obtain both before writing the direction report:

- **Gann**: target date, pivot and confirmation dates, important time points,
  support/pressure member zones, and causal-source counts.
- **Wave**: parent 1-5 ledger, active wave, preferred/alternative counts,
  confirmation, re-judgement and hard invalidation levels.

If either is absent, run the owning upstream skill:

- `gann-space-resonance` for index time/space evidence.
- `weekly-index-wave-scenarios` for wave and market-confirmation structure.

Read [references/workflow.md](references/workflow.md) for the complete execution
sequence and data cutoffs.

## Decision stages

| Stage | A-share feature cutoff | Market context | Prediction type |
|---|---|---|---|
| `premarket` | last completed session before target | tier-1 proxy and any Asia minute data before cutoff | `prospective` only when generated before target open |
| `preopen_0925` | optional enhancement: daily features remain T-1; auction fields stay in a separate target-day snapshot | final 09:25 call-auction snapshot only | `prospective`; archive under `premarket/` |
| `intraday_open` | prior close plus explicitly marked partial target-day data | live context through update time | `prospective` |
| `intraday_update` | prior close plus partial target-day data | live context through update time | `prospective` |
| `post_close_review` | target-day close | full target-day context | comparison with frozen prerecorded forecast |
| historical replay | data available before the original cutoff | replay-safe snapshot | `backfill` |

If a historical replay is run after the event, `prediction_type=backfill` even
when the requested decision was premarket.

`premarket` at 09:00 is the default for this skill. Call-auction data is an
optional enhancement, never a required foundation. The premarket execution
prior must be derivable from completed daily structure, Gann windows, structural
levels, external-market catalysts and daily volume/breadth. If 09:25 data is
available, it may update that prior but cannot create the only path to a
defensive action.

## Required pipeline

Run from the skill directory:

```bash
# 1. Initialize metadata, then build and merge a timestamped external snapshot.
python3 scripts/init_pack.py \
  --output <base_pack.json> --symbol <index> \
  --target-date <target_date> --forecast-cutoff "<forecast_cutoff>" \
  --feature-cutoff "<feature_cutoff>" --decision-stage <stage> \
  --prediction-type <prospective|backfill>

python3 scripts/external_snapshot.py \
  --cutoff "<forecast_cutoff>" --output <external_dir>

# 2. Merge it into the input pack. Do not manually rename foreign-market codes.
python3 scripts/merge_external.py \
  --pack <base_pack.json> --external <external_dir>/external_snapshot.json \
  --output <pack.json>

# 3. Compute point-in-time leadership and state variables.
python3 scripts/leadership_state.py \
  --basket <basket.csv> --leader-bars <leaders.csv> --index-bars <index.csv> \
  --breadth <market.csv> --target-date <target_date> --asof <feature_date> \
  --stage <premarket|intraday_partial|post_close> \
  [--available-at "<snapshot_time>"] --output <leadership.json>

python3 scripts/state_inputs.py \
  --index-daily <csv> --market-daily <csv> --margin <csv> \
  --external <pack.json> --asof <feature_date> \
  --feature-cutoff "<feature_cutoff>" --forecast-cutoff "<forecast_cutoff>" \
  --stage <premarket|intraday_open|intraday_update|post_close_review> \
  [--leaders <csv>] [--leadership-json <json>] [--extreme-stats <json>] \
  --pack-output <pack.enriched.json> --output <state_dir>

# 4. Run conditional base rates when the prior session is a crash, low close
#    or volume outlier.
python3 scripts/conditional_base_rates.py \
  --index-daily <long_history.csv> --asof <feature_date> \
  --lookback-start 2015-01-01 --stage <stage> --output <base_rate_dir>

# 5. Run extreme-state distributions when an extreme flag is active.
python3 scripts/extreme_state_stats.py \
  --index-daily <long_history.csv> --asof <feature_date> \
  [--margin <csv>] [--breadth <csv>] --stage <stage> --output <extreme_dir>

# 6. Build the multi-lens level registry. Production calls require handoff.
python3 scripts/build_level_registry.py \
  --db <kh_duckdb> --stage premarket --asof <feature_date> \
  --target-date <target_date> --gann-results <gann_dir> \
  --wave-anchors <wave_anchors.csv> --previous-levels <previous_levels.csv> \
  --require-handoff --symbol <index> --output <levels_dir>

python3 scripts/attach_levels.py \
  --pack <pack.enriched.json> \
  --levels <levels_dir>/level_registry.csv \
  --output <pack.final.json>

# Build the independent execution layer. For the normal 09:00 premarket stage,
# omit --snapshot: the prior is derived causally from the pack. Add --snapshot
# only for an optional 09:25 or intraday update.
python3 scripts/execution_overlay.py \
  --pack <pack.final.json> [--snapshot <auction_0925_or_intraday.json>] \
  --pressure-low <level> --pressure-high <level> --support <level> \
  --pack-output <pack.with_overlay.json> --output <execution_overlay.json>

# 7. Write a concise report.md plus a complete audit.md, the enriched input pack
#    and forecast_record.json. Copy the identical execution_overlay object into
#    the forecast. Schemas are defined in references/contract.md.

# 8. Preflight, write the declared status, freeze once, then verify externally.
python3 scripts/direction_gate.py \
  --report <stage>/report.md --audit <stage>/audit.md \
  --pack <stage>/direction_input_pack.json \
  --forecast <stage>/forecast_record.json \
  --level-registry <stage>/level_registry.csv \
  --preflight --output <stage>/gate-preflight

python3 scripts/freeze_snapshot.py \
  --stage-dir <stage> --stage <premarket|backfill|intraday|postclose> \
  --prediction-type <prospective|backfill> \
  --forecast-cutoff "<forecast_cutoff>" --target-date <target_date>

python3 scripts/direction_gate.py \
  --report <stage>/report.md --audit <stage>/audit.md \
  --pack <stage>/direction_input_pack.json \
  --forecast <stage>/forecast_record.json \
  --level-registry <stage>/level_registry.csv \
  --manifest <stage>/snapshot_manifest.json \
  --output <stage>/gate

# 9. Score separately; never feed target-day results back into the report.
python3 scripts/scorecard.py \
  --log <forecasts.jsonl> --index-daily <history_with_target.csv> \
  [--append <forecast_record.json>] --output <score_dir>
```

The preflight writes `preflight_status`. Update the report header to that value
before freezing. The final gate writes `final_gate_status`; it does not rewrite
the frozen report. A failed final gate invalidates the snapshot.

## Decision model

Read [references/evidence-rules.md](references/evidence-rules.md) before choosing
weights or classifying a rebound. Read
[references/premarket-foresight.md](references/premarket-foresight.md) before
building a premarket execution posture without auction data.

Use four close bins:

| Canonical id | Chinese report label | Required meaning |
|---|---|---|
| `trend_continuation` | 趋势延续 | Close continues the active weekly/structural trend |
| `key_level_test` | 关键位区间测试 | Close remains inside the active support-pressure decision band |
| `breakdown_or_breakout` | 关键位突破/破位 | Close accepts a boundary; `direction` states which side |
| `tail_extreme` | 尾部极值 | Close is beyond a predeclared abnormal threshold |

The Chinese labels are part of the report contract, not replacements for the
canonical ids. A report may write “趋势延续（向下确认）”, “关键位区间测试
（基准：低开下探、日内修复）” or “关键位突破/破位（向上确认）”; the text before
the parenthesis must remain one of the standard Chinese labels above.

Rules:

- Close bins use `[lower, upper)`, except the final bin includes its upper bound.
- Every bin includes `direction`, `weight`, `lower`, `upper`, a numeric close
  condition and a complete `path_forecast`: opening assumption, at least two
  ordered path steps, confirmation, targets and invalidation. The close condition
  remains a pure close rule; the path describes how that close may be reached.
- `key_level_test.direction` is `neutral`.
- `trend_continuation.direction` agrees with `weekly_regime`: down→bearish,
  up→bullish. Weekly range requires an explicit branch thesis.
- `breakdown_or_breakout.direction` is never inferred from its name.
- Weight is an internal ranking score, not a probability. Do not call it a
  calibrated probability and do not compute Brier scores from it.
- No single close bin may exceed 50%.
- `event_direction` is copied from the highest-weight bin's explicit direction.

Before writing prose, populate `critical_evidence`:

```text
core_thesis
modal_scenario
conditional_base_rates
unmatched_rates_not_used
critical_levels
direction_audit
```

Only a base rate whose state definition exactly matches the current state may be
used. “Above prior day” and “above prior 20-day mean” are different states.

## Report order

Use the two-layer structure in [references/contract.md](references/contract.md).
`report.md` is the concise decision brief; `audit.md` is the complete evidence
appendix. Do not generate a second long narrative in the appendix.

The brief has five parts:

1. Chinese report-information table and one Chinese decision-card table.
2. Core judgment with the strongest supporting and opposing evidence.
3. One compact decision-evidence table, including material gaps.
4. Critical levels and one four-scenario table with complete ordered paths,
   close bins, targets and invalidation for every scenario. All prices,
   percentages, dates and durations in this table must use Arabic numerals.
5. One compact Chinese execution-overlay table (three states, risk state,
   action bias, defensive trigger, offensive trigger, overlay invalidation and
   an “操作建议理由” subsection containing separate maintenance and release
   conditions) and at most three confirmation or invalidation observations.

Never repeat the decision card, target list, cutoff disclaimer or level
rationale. Move completed wave history, the full level ladder, raw leadership
fields and review attribution to `audit.md`. Preserve orphan-level disclosure
in the brief when required by the gate. Link the appendix from the brief.

## Gate and degradation

Hard failures:

- observation later than cutoff;
- unavailable or unverifiable timestamps;
- target-day close or full-session data in a premarket pack;
- inconsistent report/pack/forecast states;
- invalid or overlapping close bins;
- missing level-registry gate or undisclosed orphan levels;
- manifest hash mismatch;
- rule/schema version mismatch;
- English words in the human-facing report or audit narrative (paths and
  required security identifiers excepted).

Allowed degraded passes:

- an external layer is missing but explicitly `uninformative`, documented in
  `data_gap_register`, and excluded from weights;
- a market is not yet open at cutoff and is registered as `not_yet_open`;
- path/event layers are weak or unavailable and do not anchor the modal branch.

Do not use `unknown` as a substitute for `missing`, `provider_error`,
`not_yet_open`, `closed`, or `stale`.

## Output

All human-readable output is Chinese-only. Before writing any report, read
[references/report-language-zh.md](references/report-language-zh.md). Translate
market names, indicators, directions, field labels and execution states into
Chinese. The report header, decision card and execution overlay must use the
Chinese display tables defined there. The gate canonicalizes those displays
internally; JSON/CSV and gate/scorecard records continue to use stable English
enum values.

Persist by stage:

```text
outputs/window_direction_YYYYMMDD/
├── premarket/
├── intraday/
├── postclose/
└── backfill/
```

Historical replay always goes under `backfill/`. Never overwrite a frozen stage.

## References

- [references/workflow.md](references/workflow.md): detailed operating flow,
  cutoff rules and failure recovery.
- [references/contract.md](references/contract.md): pack, scenario, report and
  artifact schemas.
- [references/execution-overlay.md](references/execution-overlay.md): optional
  09:25 snapshot schema, independent states, risk derivation and execution scoring.
- [references/premarket-foresight.md](references/premarket-foresight.md):
  auction-independent premarket risk prior, confluence score and asymmetric
  reduce/acceptance rules.
- [references/evidence-rules.md](references/evidence-rules.md): external
  mapping, levels, leadership, volume, state and scoring rules.
- [references/rule-ledger.md](references/rule-ledger.md): historical rule
  changes and replay evidence.
