# Execution overlay and 09:25 stage

## Boundary

Keep four close bins and `path_forecast` unchanged. `execution_overlay` answers
whether risk should be reduced, held for confirmation or restored; it never
changes scenario weights and never rewrites a frozen prior decision.

The default stage is `premarket` at 09:00 and must not depend on call auction or
intraday data. In that mode the overlay uses the causal premarket setup described
in [premarket-foresight.md](premarket-foresight.md). A 09:25 snapshot is optional
and can only refine the premarket prior.

`preopen_0925` is an optional prospective stage stored in the existing
`premarket/` artifact directory. A 09:25 run uses the final call-auction
snapshot, not 09:30–10:00 data. Treat 09:15–09:20 indicative auction data as
cancellable and weaker than the final 09:25 snapshot.

Daily A-share features still end on T-1. Target-day auction, price, breadth,
leadership and amount-speed fields must come from a separate snapshot with
`data_asof`, `available_at`, `source` and `data_quality`.

## Snapshot

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
Missing fields remain missing; do not manufacture a complete participation
signal from one field.

## Independent states

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

These dimensions may coexist. Do not replace them with one overlapping label
such as `high_open_distribution`.

In `decision_mode=premarket_setup`, `pressure_state=untested` means the target
day has not begun; it does not make the premarket risk prior neutral. The
premarket setup state and evidence are reported separately.

The six setup checks use `external_extreme` instead of a one-sided positive
catalyst. A downside shock is confirmed only when US semiconductor/Nasdaq
weakness is paired with at least two of Japan, Korea, Taiwan and the China proxy
falling at the cutoff. US weakness with insufficient Asia confirmation remains
`unknown`. `recent_path_pressure` combines a fast three-day rebound with
break-and-reclaim memory, so an unreclaimed support break can contribute to the
premarket prior without fake-confirming a target-day close.

## Risk derivation

- `preemptive_defensive`: a premarket or combined setup identifies a mature
  time/price supply zone with a strong external catalyst and insufficient
  confirmation. This authorizes `reduce_only` before an intraday rejection.
- `defensive`: pressure rejected **and** participation divergent. A gap fade
  alone never triggers defense.
- `offensive`: pressure accepted **and** participation confirming.
- `watch`: a gap or pressure test exists but the evidence is incomplete.
- `unknown`: required observations are missing. Do not invent an action signal.
- `normal`: no active gap/pressure risk and no missing required observation.

When the premarket setup is `risk_zone_euphoria`, `normal`, `watch` and
`unknown` snapshot states cannot clear the premarket defense. The combined
state may move to `offensive` only after pressure acceptance plus confirming
participation, or to `defensive` after rejection plus divergence.

The execution bias is `reduce_only` for confirmed or preemptive defense,
`add_only_after_confirmation` for offense, `wait_for_confirmation` for
watch/unknown and `observe` for normal. This is a research risk overlay, not a
personalized portfolio instruction.

This mapping is a code reference. The final execution state and action belong to
the validated LLM judgement. A deviation must state which point-in-time evidence
overrode the reference and must still include maintenance, invalidation, horizon
and review conditions.

## Required output

Every overlay contains:

```text
stage, target_date, data_asof, available_at, source, data_quality
gap_state, pressure_state, participation_state, risk_state, execution_bias
decision_mode, setup_state, setup_evidence, metrics, thresholds,
action_rationale, defensive_trigger, offensive_trigger, invalidation
conditional_path, valid_for, next_review, data_gaps
```

Every action recommendation must include `action_rationale` with:

```text
recommendation, recommendation_zh
why_now[at least 2]
opposing_evidence[at least 1]
action_maintenance[at least 1]
action_invalidation[at least 1]
horizon, next_review
```

The user-facing report must contain a Chinese execution-overlay table and an
“操作建议理由” subsection. The table must explicitly include `防守触发`,
`恢复进攻触发` and `覆盖失效`; the rationale must explicitly include
`动作维持条件` and `动作解除条件`. Display `premarket_setup` as `盘前设定`,
`risk_zone_euphoria` as `风险区亢奋`, `preemptive_defensive` as `提前防守`,
and `reduce_only` as `只减不加`; do not expose the raw machine value block.
`action_maintenance` states why the current action remains valid.
`action_invalidation` contains only evidence that releases or overturns the
current action. The same condition must not be used for both.

Each premarket setup check uses `met`, `not_met` or `unknown`. Unknown checks
are excluded from the score; at least four known checks are required before a
setup state can be classified.

`conditional_path` covers the target day, T+1 defense persistence and the
T+1/T+3 condition for restoring offense. Score close-bin outcome, ordered path
nodes and execution outcome separately. Execution evaluation must include both
avoided drawdown and missed upside, false positives and a simple no-action
baseline; do not optimize only for earlier defensive signals.

## Command

```bash
# Default 09:00 premarket decision: no auction or intraday snapshot
python3 scripts/execution_overlay.py \
  --pack pack.final.json \
  --pressure-low 3690.95 --pressure-high 3700.82 --support 3606.94 \
  --pack-output pack.with_overlay.json --output execution_overlay.json

# Optional later refinement after a 09:25 or intraday snapshot
python3 scripts/execution_overlay.py \
  --pack pack.with_overlay.json --snapshot auction_0925.json \
  --pressure-low 3690.95 --pressure-high 3700.82 --support 3606.94 \
  --pack-output pack.with_snapshot_overlay.json \
  --output execution_overlay_with_snapshot.json
```

Copy the same overlay object into `forecast_record.json`. The gate checks enum
values, required triggers, risk/action consistency, stage and timestamps. At the
normal 09:00 `premarket` stage, omit `--snapshot`; the overlay must instead derive
`premarket_setup` from the pack. Missing optional data is recorded, but it does
not erase a valid causal premarket risk prior.
