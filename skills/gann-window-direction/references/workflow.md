# Operating workflow

## Data-source order

For A-share OHLCV, breadth, amount and margin:

1. KH local DuckDB or an audited local KH export.
2. Tushare structured data when KH coverage is incomplete.
3. Wencai only for market-internal fields suited to natural-language screening.

Record the actual adapter and failure. Never claim an unattempted primary-source
failure. Every observation carries `source`, `data_asof`, `available_at` and
`data_quality`.

## 1. Freeze the decision context

```text
target_date
decision_stage
prediction_type
forecast_cutoff
feature_cutoff
timezone
symbol
```

Premarket daily observations must be earlier than target date. Intraday runs use
the actual snapshot time. Historical replay is `backfill` even when it imitates a
premarket decision.

## 2. Audit upstream structure

Read Gann target/pivot/confirmation dates, time family, causal sources and space
levels. Read wave parent ledger, preferred/alternative counts, confirmation,
re-judgement and hard invalidation. Do not invent missing upstream anchors.

## 3. Build external and deterministic evidence

Run `external_snapshot.py`, `merge_external.py`, `leadership_state.py` and
`state_inputs.py` as shown in `SKILL.md`. Scripts filter every dated input before
calculation. External Asia records must be snapshots available at cutoff.

`state_inputs.py` produces factual states and information content only. It does
not emit weight priors, reversal floors or a direction.

Run `structure_memory.py` using previous exact levels. It preserves unreclaimed
breaks and pressure-test history and uses the shared Wilder 14-session ATR.

Conditional base rates and extreme-state statistics may be supplied as evidence
when relevant. They never impose scenario percentages or reversal floors.

## 4. Build current levels before judgement

```bash
python3 scripts/build_level_registry.py \
  --db /abs/kh_duckdb --stage premarket --asof 2026-10-22 \
  --target-date 2026-10-23 --gann-results /abs/gann \
  --wave-anchors /abs/wave_anchors.csv \
  --previous-levels /abs/previous_levels.csv \
  --require-handoff --symbol 000001.SH --output /abs/levels

python3 scripts/attach_levels.py \
  --pack /abs/pack.with_structure.json \
  --levels /abs/levels/level_registry.csv \
  --output /abs/pack.with_levels.json

python3 scripts/level_context.py \
  --pack /abs/pack.with_levels.json \
  --levels /abs/levels/level_registry.csv \
  --output /abs/level_context.json \
  --pack-output /abs/pack.with_context.json
```

The level registry and structure memory must both declare `wilder_14` and agree
on ATR. `level_context.py` rejects mismatches. Its current price anchors and
weight-free close bins are the only path-price and settlement inputs.

There is no `scenario_weights.py` step.

## 5. Build the execution fact layer

Run `execution_overlay.py` after current levels exist. At 09:00 omit the
snapshot; at 09:25 or intraday provide the actual snapshot. The overlay supplies
only gap, pressure, participation, premarket risk facts, timestamps and data gaps.
It must not generate a setup score, risk state, execution action, action rationale
or conditional action path. Those decisions belong exclusively to the LLM.

## 6. Submit LLM judgement

The LLM reads the full pack and writes `llm_judgement.json` according to
`llm-judgement.md` and `contract.md`.

Decision order:

1. Medium-term structure and its invalidation.
2. Window state and actual confirmation conditions.
3. Next-day opening → intraday → close baseline using registered price anchors.
4. Upside/downside switches and independent tail risk.
5. Structure/path divergence when applicable.
6. Execution state, action, opposing evidence and maintenance/release conditions.

No numerical confidence or scenario weight is requested. The baseline is chosen
by the LLM, not by sorting code-generated percentages.

Populate `critical_evidence` with factual conditional rates and critical levels
only. Do not copy `core_thesis`, `next_day_baseline`, `structure_path_audit` or
`direction_audit` into it: `llm_judgement` is the sole decision source.
Conditional rates use `used_in_judgement`, never `used_in_weights`.

Validate and build:

```bash
python3 scripts/validate_llm_judgement.py \
  --pack /abs/pack.with_overlay.json \
  --judgement /abs/llm_judgement.json \
  --pack-output /abs/direction_input_pack.json

python3 scripts/build_forecast_from_judgement.py \
  --pack /abs/direction_input_pack.json \
  --output /abs/forecast_record.json
```

## 7. Write the report

Write a concise Chinese `report.md` and complete `audit.md`.

The decision card leads with structure, window, next-day baseline, opening zone,
intraday zone, close zone/character and execution. The body presents one baseline
path plus switches and tail risk. Script-generated execution risk facts and the
LLM's execution discretion appear in separate sections. The audit carries the
weight-free close bins.

Do not display an event-day total direction, scenario weights, numerical
confidence or weight-confidence labels. Do not describe a wide-range lower-edge
close as balanced oscillation.

## 8. Gate and freeze

Run preflight, update the declared gate status before freezing, freeze once and
run final verification. A failed final gate invalidates the snapshot; never edit
frozen files to repair it.

New hard failures include old weight/confidence fields, missing path stages,
unregistered price anchors, inconsistent report/forecast zones and missing
structure/path divergence.

## 9. Review

Record actual open, high, low and close against the frozen baseline. Separately
settle opening zone, intraday range, close zone, close location and character.
Wide-range edge coverage is fragile and reported separately.

Daily OHLC does not reveal whether the high or low occurred first. Without real
intraday evidence, ordered-path settlement is `unavailable_from_daily_ohlc`.
Record trigger behavior and actual execution outcome separately, without
execution scoring.

Attribution categories:

```text
data_gap | classification | judgement | rule_gap
```

Legacy weighted forecasts remain in a separate scoring branch. Never mix their
accuracy with path metrics.

## 10. Maintenance checks

```bash
python3 scripts/selftest.py
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
python3 -m py_compile scripts/*.py
```

Regression covers point-in-time filtering, unified ATR, current price anchors,
weight-free judgement, three-stage paths, conditional switches, close-bin
geometry, report consistency, execution constraints, legacy scoring separation
and manifest integrity.
