# Execution fact layer and 09:25 stage

## Boundary

`execution_overlay` is a point-in-time fact layer. It describes what can be observed
at the decision cutoff; it does not decide what the LLM should do. It never selects
`structural_bias`, `window_state`, `next_day_path`, `risk_state` or an execution action.

The overlay must not contain:

```text
setup_score / setup_state / risk_state / execution_bias
action_rationale / defensive_trigger / offensive_trigger / conditional_path
```

The LLM reads these facts together with the full evidence pack and independently
submits the risk state, execution state, action, supporting and opposing evidence,
maintenance conditions, invalidation, horizon and next review point.

## Decision stages

The default stage is `premarket` at 09:00 and does not depend on call-auction or
intraday data. A 09:25 snapshot is optional additional evidence, not a machine rule
for upgrading or downgrading an earlier action.

A `preopen_0925` run uses the final call-auction snapshot, not 09:30–10:00 data.
Treat 09:15–09:20 indicative auction data as cancellable and weaker than the final
09:25 snapshot. Daily A-share features still end on T-1.

Every target-day snapshot must include `data_asof`, `available_at`, `source` and
`data_quality`. Missing fields remain missing; do not manufacture a complete
participation observation from one field.

## Snapshot example

```json
{
  "data_asof": "2026-10-23",
  "available_at": "2026-10-23T09:25:00+08:00",
  "source": "audited auction snapshot",
  "data_quality": "final_call_auction",
  "prev_close": 3658.03,
  "open": 3690.0,
  "price": 3690.0,
  "session_high": 3690.0,
  "advance_ratio": 0.42,
  "leader_relative_strength": -0.006,
  "same_time_amount_ratio": 0.88
}
```

`same_time_amount_ratio` compares the same auction or intraday interval with
historical observations at that same time, never with a full-day median.

## Observable states

- `gap_state`: `expected | confirmed | faded | not_applicable | unknown`.
  A positive open gap must reach the declared threshold. `faded` requires the
  current price to retrace at least the declared fraction of that opening gap.
- `pressure_state`: `untested | accepted | rejected | ambiguous | not_applicable | unknown`.
  `rejected` requires an observed test above `pressure_low` followed by a return
  below it. `accepted` requires price above `pressure_high` plus confirming
  participation; otherwise an above-band snapshot remains ambiguous.
- `participation_state`: `confirming | divergent | unknown`. At least two of
  advance ratio, leader relative strength and same-time amount ratio must be
  present, and at least two must point in the same direction.

These are descriptive states. `rejected + divergent` does not automatically mean
`reduce_only`, and `accepted + confirming` does not automatically mean restore
offense. The LLM must explain its own execution decision and strongest opposing
observation.

In `decision_mode=premarket_facts`, `pressure_state=untested` means the target day
has not begun. It is not a neutral risk conclusion.

## Premarket facts

The overlay retains five three-state evidence rows:

```text
active_key_window
pressure_proximity
external_extreme
recent_path_pressure
confirmation_deficit
```

Each row is `met`, `not_met` or `unknown`, with a textual detail. There is no
`structural_bearish` row: the overlay runs before LLM judgement and must not read
or inherit a pre-existing `direction_audit.structural_bias` as a decision input.

The five rows are not added into a score and do not map to a risk or action state.
See [premarket-foresight.md](premarket-foresight.md) for their factual definitions.

## Required output

Every overlay contains:

```text
ruleset_version, stage, target_date, data_asof, available_at
source, data_quality, decision_mode
setup_evidence, gap_state, pressure_state, participation_state
metrics, thresholds, invalidation, valid_for, next_review, data_gaps
```

`invalidation` describes only when the fact coverage is unusable, such as a snapshot
later than `forecast_cutoff` or unverifiable timestamps. It is not an action
invalidation; the latter belongs to `llm_judgement`.

## Report and gate

The report separates:

1. **执行风险事实**：the script-generated states, metrics and data gaps.
2. **执行裁量**：the LLM's risk state, action, reasons, strongest opposing evidence,
   maintenance and release conditions, horizon and next review.

Default support and pressure defenses come from `level_context.decision_band`.
All thresholds must be registered anchors; support and the pressure defense must
match that band, with `support < pressure_low <= pressure_high`. Manual overrides
cannot introduce a second, inconsistent level set.

The gate rejects decision fields inside the overlay and does not rederive an
expected risk state or action. It continues to validate timestamps, evidence-row
structure, threshold geometry, pack/forecast equality and the LLM's complete
execution rationale.
