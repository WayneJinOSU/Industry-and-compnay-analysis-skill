# Operating workflow

## Data-source order

For A-share OHLCV, breadth, amount and margin:

1. KH local DuckDB or an audited local KH export.
2. Tushare structured data when KH coverage is incomplete.
3. Wencai only for market-internal fields that need natural-language screening.

For external markets, use the adapter named in `source_used`. Record a real
adapter call or a real failure; never hardcode a primary-source failure that was
not attempted.

## 1. Freeze the decision context

Write these fields before collecting evidence:

```text
target_date
decision_stage
prediction_type
forecast_cutoff
feature_cutoff
timezone
symbol
```

`forecast_cutoff` is the wall-clock decision time.  `feature_cutoff` is the
latest time at which a feature may have been known.  For premarket A-share data,
the last daily observation must be earlier than `target_date`.

Every recorded observation must have:

```text
source
data_asof
available_at
data_quality
```

The gates reject future or unverifiable timestamps. A data provider's current
value cannot be relabeled as a historical observation.

## 2. Build the upstream structure

### Gann

Read or create:

```text
target_date
pivot_date
confirm_date
time_family
independent_causal_sources
space_levels
important_time_points
```

All anchors require `confirm_date < target_date`. Use one dated observation per
important time point; keep tolerances in the audit files.

When embedding the Gann result in the direction pack, add:

```text
as_of
available_at
source
```

### Wave

Read or create:

```text
parent_1_to_5_ledger
active_degree
preferred_count
strongest_alternative
confirmation_level
rejudgement_level
hard_invalidation
wave_confidence
```

If the upstream result is absent, run the owning skill. Do not invent an anchor
inside this direction layer.

The embedded wave result likewise needs:

```text
latest_data_asof
available_at
source
```

## 3. Build external snapshots

Choose the external anchor by transmission relevance:

```text
tier_1: A50, China proxies, HSI when open
tier_2: N225, KOSPI, TWII, AS51
tier_3: US indices, Europe, SOX
```

At a premarket cutoff, include:

- completed US/Europe sessions;
- the last China proxy observation available by cutoff;
- exact Asia minute snapshots at or before cutoff;
- completed gold observations available by cutoff.

An unopened market is `not_yet_open`; an absent historical minute series is
`missing` or `provider_error`. Neither is neutral.

```bash
python3 scripts/init_pack.py \
  --output /abs/output/base_pack.json --symbol 000001.SH \
  --target-date 2026-10-23 \
  --forecast-cutoff "2026-10-23T09:00:00+08:00" \
  --feature-cutoff "2026-10-23T09:00:00+08:00" \
  --decision-stage premarket --prediction-type backfill

python3 scripts/external_snapshot.py \
  --cutoff "2026-10-23T09:00:00+08:00" \
  --output /abs/output/external

python3 scripts/merge_external.py \
  --pack /abs/output/base_pack.json \
  --external /abs/output/external/external_snapshot.json \
  --output /abs/output/direction_input_pack.json
```

`merge_external.py` writes canonical codes (`IXIC`, `NDX`, `SPX`, `DJI`, `SOX`,
`N225`, `KS11`, `TWII`, `AS51`, `HSI`, `XIN9`). Do not maintain a second alias
mapping in prose.

## 4. Compute deterministic state

First compute the leadership state:

```bash
python3 scripts/leadership_state.py \
  --basket /abs/basket.csv \
  --leader-bars /abs/leader_bars.csv \
  --index-bars /abs/index.csv \
  --breadth /abs/market.csv \
  --target-date 2026-10-23 \
  --asof 2026-10-22 \
  --stage premarket \
  --output /abs/leadership.json
```

For `intraday_partial`, pass the actual `--available-at`. A premarket call with
`asof >= target_date` is rejected.

```bash
python3 scripts/state_inputs.py \
  --index-daily /abs/index.csv \
  --market-daily /abs/market.csv \
  --margin /abs/margin.csv \
  --leadership-json /abs/leadership.json \
  --external /abs/direction_input_pack.json \
  --asof 2026-10-22 \
  --feature-cutoff "2026-10-23T09:00:00+08:00" \
  --forecast-cutoff "2026-10-23T09:00:00+08:00" \
  --stage premarket \
  --extreme-stats /abs/extreme/extreme_state_stats.json \
  --pack-output /abs/direction_input_pack.enriched.json \
  --output /abs/state
```

The script filters every frame before computation and records actual coverage.
If an input has later rows, they are excluded and listed under
`input_coverage`.

For `preopen_0925`, `intraday_open` or `intraday_update`, pass the actual
snapshot time with `--available-at`. For premarket/post-close runs, omitted
`--available-at` defaults to 18:00 on `data_asof`. The same rule applies to
`leadership_state.py --available-at`. At 09:25, keep daily state computation on
T-1; target-day auction observations belong only in `execution_overlay`.

Run `conditional_base_rates.py` if the previous day is:

- a large drop;
- a low close;
- a day-over-day volume expansion;
- above the prior 20-day mean volume.

The last two are separate states. Do not substitute one for the other.

Run `extreme_state_stats.py --asof <feature_date> --stage <stage>` whenever the
current state has an extreme breadth or funding flag. For intraday data, pass
the exact snapshot time through `--available-at`.

## 5. Build structural levels

Use the multi-lens registry, not a raw Gann table:

```bash
python3 scripts/build_level_registry.py \
  --db /abs/kh_duckdb \
  --stage premarket \
  --asof 2026-10-22 \
  --target-date 2026-10-23 \
  --gann-results /abs/gann \
  --wave-anchors /abs/wave_anchors.csv \
  --previous-levels /abs/previous_levels.csv \
  --require-handoff \
  --symbol 000001.SH \
  --output /abs/levels

python3 scripts/attach_levels.py \
  --pack /abs/direction_input_pack.enriched.json \
  --levels /abs/levels/level_registry.csv \
  --output /abs/direction_input_pack.final.json
```

Production handoff requires a previous-levels file whose source report is
strictly earlier than `target_date`. The registry writes:

```text
level_registry.csv
level_ladder.csv
same_origin_bands.csv
level_registry_summary.json
```

Every zone records member levels, lens count, behaviour metrics,
`formation_window`, cluster role and cluster type. A spatial cluster is not called
`same_origin_cluster` unless its formation dates fall inside one declared wave
leg.

For `--stage intraday`, also pass `--available-at` with the partial snapshot
time. The registry rejects a premarket `asof` on or after the target date.

## 6. Construct the decision

Start with the event-level thesis:

1. Structural trend and active wave.
2. Previous price path and failed reclaims.
3. Support and pressure band interaction.
4. External mapping.
5. Volume, margin, breadth and leadership.
6. Gann time/space as an ordering layer.

Construct four mutually exclusive close bins. A price inside the support-pressure
decision band is a key-level test. A close beyond a structural boundary is
continuation or breakout/breakdown depending on the declared direction. The tail
threshold must be an abnormal, predeclared level.

Write every bin with a pure close condition and a complete path forecast:

```json
{
  "name": "breakdown_or_breakout",
  "direction": "bearish",
  "weight": 0.25,
  "lower": 3500.0,
  "upper": 3602.15,
  "close_condition": "close below the support-band defense",
  "path_forecast": {
    "opening": "flat or lower open",
    "steps": ["failed rebound at band support", "renewed sell-through and weak close"],
    "confirmation": "support rejects the rebound and price accepts below it",
    "targets": [3480.0, 3450.0],
    "invalidation": "close reclaims 3602.15"
  }
}
```

Set the event direction from the highest-weight bin's explicit `direction`.
In the human report, keep one table but show each scenario's full ordered path,
close bin, targets and invalidation. Score path and close-bin outcomes separately.

For Chinese reports, present the four close bins in Chinese first. Use the fixed
labels `趋势延续`, `关键位区间测试`, `关键位突破/破位`, `尾部极值`, with an
optional parenthetical path description. Keep English ids only in JSON, CSV,
gate and scorecard artifacts. See
[report-language-zh.md](report-language-zh.md).

Build `execution_overlay` after the close-bin forecast. It does not change any
scenario weight or path. At 09:25 use `decision_stage=preopen_0925`, cutoff
09:25:00 and a final call-auction snapshot; keep the existing `premarket/`
directory. Read [execution-overlay.md](execution-overlay.md) for the complete
schema and run:

```bash
python3 scripts/execution_overlay.py \
  --pack direction_input_pack.final.json --snapshot auction_0925.json \
  --pressure-low 3690.95 --pressure-high 3700.82 --support 3606.94 \
  --pack-output direction_input_pack.with_overlay.json \
  --output execution_overlay.json
```

Copy the identical overlay into `forecast_record.json`. Show one compact
“执行覆盖” block in the report: three independent states, derived risk state,
`防守触发`, `恢复进攻触发` and `覆盖失效`. The action rationale must separately
show `动作维持条件` and `动作解除条件`. A gap fade alone is not defensive.
Missing snapshots degrade to `unknown`; never invent a signal. Once a
`risk_zone_euphoria` premarket setup exists, only accepted pressure plus
confirming participation can restore offense.

## 7. Gate and freeze

First preflight without a manifest:

```bash
python3 scripts/direction_gate.py \
  --report report.md --audit audit.md --pack direction_input_pack.json \
  --forecast forecast_record.json --level-registry level_registry.csv \
  --preflight --output gate-preflight
```

The output contains `preflight_status`. Translate that status into the Chinese
value in the report-information table's `门禁状态` row and re-run preflight once.
For example, `passed_with_warnings` is displayed as `带警告通过`. Freeze only
after no hard failure remains:

```bash
python3 scripts/freeze_snapshot.py \
  --stage-dir /abs/stage --stage premarket \
  --prediction-type prospective \
  --forecast-cutoff "2026-10-23T09:00:00+08:00" \
  --target-date 2026-10-23
```

The final gate runs after the freeze:

```bash
python3 scripts/direction_gate.py \
  --report report.md --audit audit.md --pack direction_input_pack.json \
  --forecast forecast_record.json --level-registry level_registry.csv \
  --manifest snapshot_manifest.json --output gate
```

The final gate reports `final_gate_status`. It never edits frozen files. If final
verification fails, archive the failed snapshot and rerun from preflight.

## 8. Review

Post-close review records:

```text
prior forecast
actual path
final branch
target hit
invalidation behavior
external mapping outcome
leadership outcome
data gaps
attribution: data_gap | classification | weighting | rule_gap
```

A backfill result is displayed separately and never added to prospective accuracy.

## 9. Skill maintenance checks

Before distributing a modified copy:

```bash
python3 scripts/selftest.py
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
python3 -m py_compile scripts/*.py
```

The regression suite covers cutoff filtering, compact numeric dates, future
timestamps, premarket leadership data, explicit scenario directions, SOX
degradation, orphan disclosure, neutral scoring, interval overlap, 09:25 feature
separation, two-sided execution triggers, missing-data degradation and
pack/forecast overlay consistency.

