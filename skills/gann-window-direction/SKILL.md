---
name: gann-window-direction
description: Produce point-in-time A-share index structure and next-day path reports by combining verified Gann time/space, wave structure, current price anchors, external markets, breadth, funding and leadership. Use for premarket/intraday/backfill window decisions, conditional path construction, execution gating and post-close attribution. Do not use Gann dates as standalone buy/sell signals.
---

# Gann Window Direction

Turn upstream Gann and wave evidence into an auditable, point-in-time discretionary
judgement. Code computes facts, current price anchors, settlement geometry, execution
risk evidence and timestamps. The LLM solely owns structural bias, window state, the
next-day baseline path, conditional switches, risk state and the final execution judgement.

## Non-negotiable rules

1. Freeze `target_date`, `forecast_cutoff`, `feature_cutoff`, `decision_stage`
   and `prediction_type` before loading evidence.
2. Every input must satisfy `available_at <= forecast_cutoff` and
   `data_asof <= feature_cutoff`. Missing availability time means the input
   cannot support a formal decision.
3. A-share daily data for premarket must end before `target_date`. Asia markets
   use only historical snapshots available at or before cutoff.
4. Gann dates define observation moments, not direction. Price structure and
   accepted close behavior determine structural and window states.
5. Keep `structural_bias`, `window_state`, `next_day_path` and `execution_state`
   independent. An unresolved window does not imply neutral structure. A strong
   next-day repair does not by itself reverse bearish structure.
6. Do not generate scenario weights, numerical confidence, confidence margins,
   low-confidence labels, execution scores, or a top-level event-day direction.
   Never select a baseline by ranking hardcoded percentages.
7. The next-day baseline must contain numeric opening, intraday and close zones,
   at least two ordered intraday observations, upside/downside switches and an
   independent tail-risk path.
8. Every numeric path level must come from the current `level_context` anchor
   registry. The LLM must not invent prices. Use zones and observation anchors,
   not false precision or guaranteed arrival claims.
9. Four close bins remain mandatory for settlement only. They are contiguous,
   carry no weights and do not determine the report headline or structural bias.
10. Missing evidence is `uninformative`, not neutral. Register the gap and do not
    use that layer as decisive evidence.
11. Do not create a final report when a hard gate fails. After a snapshot is
    frozen, never edit it to repair a failed final check; discard and rerun.
12. Report `backfill` separately. It never enters prospective accuracy.
13. All user-facing narrative must be Chinese-only. Canonical English ids remain
    in JSON/CSV/YAML, gates, scorecards and file paths.
14. Every action recommendation needs at least two forward-looking reasons, the
    strongest opposing observation, maintenance conditions, invalidation
    conditions, horizon and next review point.
15. Quantitative values use Arabic numerals and normal units.
16. Keep break-and-reclaim memory from previous exact defenses. A newly generated
    band must not erase an older broken support until a close reclaims it.
17. Use one ATR definition everywhere: `wilder_14`, computed by `common.py` from
    the same completed daily history.
18. Build the current level registry and `level_context` before LLM judgement.
    No scenario-weight step exists in the pipeline. `execution_overlay` supplies
    facts only and must not generate scores, risk states, actions or action reasons.
19. The LLM submits its structured record before prose. Code validates timestamps,
    states, evidence references, current price anchors, path completeness and
    execution rationale; it does not secretly replace the discretionary view or
    rederive an expected execution action.
20. Separate `structure_invalidation`, `baseline_path_invalidation` and
    `action_invalidation`. Leaving a next-day range is not automatically a
    medium-term structural reversal.
21. `llm_judgement` is the only decision copy. `critical_evidence` contains factual
    rates and levels, never a duplicate thesis, baseline or structure/path audit.
22. Close-location labels must match close-zone/support/pressure geometry. Overlay
    thresholds must use the current decision band and registered anchors. Level
    registration exposes raw evidence without heuristic scores or tiers.

## Upstream inputs

Obtain both before writing the report:

- **Gann**: target date, pivot and confirmation dates, important time points,
  support/pressure member zones and causal-source counts.
- **Wave**: parent ledger, active wave, preferred/alternative counts,
  confirmation, re-judgement and hard invalidation levels.

If either is absent, run `gann-space-resonance` or
`weekly-index-wave-scenarios`. Do not invent upstream anchors in this layer.

## Decision stages

| Stage | A-share feature cutoff | Prediction type |
|---|---|---|
| `premarket` | last completed session before target | `prospective` only before target open |
| `preopen_0925` | daily features remain T-1; separate 09:25 auction snapshot | `prospective`; archive under `premarket/` |
| `intraday_open` / `intraday_update` | prior close plus explicitly marked partial data | `prospective` |
| `post_close_review` | target-day close | comparison with frozen forecast |
| historical replay | data available before original cutoff | `backfill` |

Premarket at 09:00 is the default. Auction data is an optional enhancement, not
the only route to a defensive action.

## Required pipeline

Run from the skill directory:

```bash
python3 scripts/init_pack.py \
  --output <base_pack.json> --symbol <index> \
  --target-date <target_date> --forecast-cutoff "<forecast_cutoff>" \
  --feature-cutoff "<feature_cutoff>" --decision-stage <stage> \
  --prediction-type <prospective|backfill>

python3 scripts/external_snapshot.py \
  --cutoff "<forecast_cutoff>" --output <external_dir>
python3 scripts/merge_external.py \
  --pack <base_pack.json> --external <external_dir>/external_snapshot.json \
  --output <pack.json>

python3 scripts/leadership_state.py \
  --basket <basket.csv> --leader-bars <leaders.csv> --index-bars <index.csv> \
  --breadth <market.csv> --target-date <target_date> --asof <feature_date> \
  --stage <premarket|intraday_partial|post_close> \
  [--available-at "<snapshot_time>"] --output <leadership.json>

python3 scripts/state_inputs.py \
  --index-daily <csv> --market-daily <csv> --margin <csv> \
  --external <pack.json> --asof <feature_date> \
  --feature-cutoff "<feature_cutoff>" --forecast-cutoff "<forecast_cutoff>" \
  --stage <stage> [--leadership-json <leadership.json>] \
  --pack-output <pack.enriched.json> --output <state_dir>

python3 scripts/structure_memory.py \
  --index-daily <csv> --previous-levels <previous_levels.csv> \
  --target-date <target_date> --asof <feature_date> \
  --available-at "<available_at>" --pack <pack.enriched.json> \
  --pack-output <pack.with_structure.json> --output <structure_memory.json>

# Conditional and extreme statistics are optional evidence, never weight rules.
python3 scripts/conditional_base_rates.py \
  --index-daily <long_history.csv> --asof <feature_date> \
  --lookback-start 2015-01-01 --stage <stage> --output <base_rate_dir>
python3 scripts/extreme_state_stats.py \
  --index-daily <long_history.csv> --asof <feature_date> \
  [--margin <csv>] [--breadth <csv>] --stage <stage> --output <extreme_dir>

# Current levels come before path judgement.
python3 scripts/build_level_registry.py \
  --db <kh_duckdb> --stage premarket --asof <feature_date> \
  --target-date <target_date> --gann-results <gann_dir> \
  --wave-anchors <wave_anchors.csv> --previous-levels <previous_levels.csv> \
  --require-handoff --symbol <index> --output <levels_dir>
python3 scripts/attach_levels.py \
  --pack <pack.with_structure.json> --levels <levels_dir>/level_registry.csv \
  --output <pack.with_levels.json>
python3 scripts/level_context.py \
  --pack <pack.with_levels.json> --levels <levels_dir>/level_registry.csv \
  --output <level_context.json> --pack-output <pack.with_context.json>

python3 scripts/execution_overlay.py \
  --pack <pack.with_context.json> [--snapshot <auction_or_intraday.json>] \
  --pressure-low <level> --pressure-high <level> --support <level> \
  --pack-output <pack.with_overlay.json> --output <execution_overlay.json>

# The LLM reads the complete pack and writes llm_judgement.json.
python3 scripts/validate_llm_judgement.py \
  --pack <pack.with_overlay.json> --judgement <llm_judgement.json> \
  --pack-output <pack.final.json>
python3 scripts/build_forecast_from_judgement.py \
  --pack <pack.final.json> --output <forecast_record.json>

# Write report.md and audit.md, then preflight, freeze and verify.
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
  --manifest <stage>/snapshot_manifest.json --output <stage>/gate

python3 scripts/scorecard.py \
  --log <forecasts.jsonl> --index-daily <history_with_target.csv> \
  [--append <forecast_record.json>] --output <score_dir>
```

## LLM decision contract

Read `references/llm-judgement.md` and `references/contract.md` before writing
`llm_judgement.json`.

Required decision content:

```text
structural_bias + structure_reason + structure_opposition + structure_invalidation
window_state
next_day_path:
  baseline_summary
  opening zone + reference level + expectation
  intraday lower/upper + at least two ordered observations + acceptance/rejection
  close lower/upper + location + character
  upside_switch + downside_switch + tail_risk
  structure_path_divergence when structure and close character conflict
baseline_path_invalidation
execution state/action + supporting/opposing evidence
action_maintenance + action_invalidation + horizon + next_review
```

`close.location` is `center`, `upper_edge`, `lower_edge`, `below_support` or
`above_pressure`. `close.character` is `strong`, `weak` or `balanced`. These are
path descriptors, not confidence scores.

## Report order

`report.md` is the concise decision brief; `audit.md` is the evidence appendix.

1. Chinese metadata and decision card: structure, window, next-day baseline,
   opening zone, intraday zone, close zone/character and execution state.
2. Core judgement: structure rationale, strongest opposing evidence and explicit
   structure/path divergence when applicable.
3. Compact decision-evidence table with material gaps.
4. Baseline opening → intraday → close path, upside/downside switches and tail
   risk. Every displayed level must be in the current anchor registry.
5. Script-generated execution risk facts, then the LLM's complete action rationale.

The four weight-free close bins belong in the audit settlement table. Do not
restore a weighted four-scenario table or an event-day headline such as
“方向：震荡”. A wide-range lower-edge close is weak, not a high-quality balanced
range hit.

## Gate and degradation

Hard failures include future/unverifiable timestamps, target-day daily data in a
premarket pack, inconsistent report/pack/forecast states, weights or confidence
in the new judgement, unregistered path prices, incomplete path stages, missing
structure/path invalidation, invalid close bins, missing level gates, manifest
hash mismatch and ruleset mismatch.

Missing external or optional evidence may degrade only when registered and not
used as decisive evidence. Never silently convert missing data to neutral.

## Scoring

New path records settle opening-zone hit/distance, intraday range coverage and
overshoot, close-zone hit/distance, close location, close character and fragile
wide-range coverage. Daily OHLC cannot establish the order of intraday nodes;
mark path order unavailable unless actual intraday evidence exists. Execution
results remain separate.

Legacy weighted forecasts remain readable under their old scoring branch. Never
mix legacy weighted accuracy with new path metrics and never rewrite frozen
records.

## Output

Persist by stage:

```text
outputs/window_direction_YYYYMMDD/
├── premarket/
├── intraday/
├── postclose/
└── backfill/
```

## References

- `references/workflow.md`: operating sequence and data cutoffs.
- `references/contract.md`: pack, judgement, path, forecast and report schemas.
- `references/llm-judgement.md`: discretionary judgement boundary.
- `references/evidence-rules.md`: independent states and evidence rules.
- `references/report-language-zh.md`: Chinese display contract.
- `references/execution-overlay.md`: point-in-time execution fact layer.
- `references/premarket-foresight.md`: auction-independent premarket risk facts.
- `references/rule-ledger.md`: rule changes and replay evidence.

Current ruleset: `2026-10-28.4`.
