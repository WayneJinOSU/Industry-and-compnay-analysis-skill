# Auction-independent premarket execution facts

## Purpose

The normal premarket run at 09:00 prepares facts available after the prior close
and before the target open. It does not create a defensive or offensive prior.
Call-auction data is optional additional evidence.

The model separates:

```text
next_day_path          LLM conditional opening → intraday → close baseline
structural_bias        LLM medium-term price-structure judgement
risk_state             LLM synthesis of current risk evidence
execution action       LLM discretionary action with reasons and invalidation
```

No script in this layer is allowed to collapse these axes into a score or action.

## Five premarket evidence rows

1. `active_key_window`: whether the target date lies in a confirmed Gann time window.
2. `pressure_proximity`: whether the prior close is within the declared ATR distance
   of the first pressure anchor, or already inside the pressure band.
3. `external_extreme`: whether the predefined high-beta external chain exceeds its
   declared movement thresholds. A downside shock requires US semiconductor/Nasdaq
   weakness paired with at least two confirmed Asian-market declines at the cutoff.
4. `recent_path_pressure`: whether the prior three sessions produced a fast rebound,
   or break/reclaim memory shows an unreclaimed support break or weak close near support.
5. `confirmation_deficit`: whether volume and/or time-appropriate leadership are
   weak, lagging or neutral rather than informatively confirming.

These rows describe evidence only. In particular, `confirmation_deficit` is not a
sell signal and `external_extreme` is not an event-day close-direction prediction.

## Three-state recording

Report each row with one of three states:

```text
met | not_met | unknown
```

Missing inputs remain `unknown`. Do not convert them to `not_met`, neutral or normal.
There is no minimum known-count threshold because the rows are no longer aggregated
into a setup classification. All available facts remain visible to the LLM together
with the data-gap register.

For `external_extreme`, an unconfirmed US downside shock with fewer than two Asian
confirmations is `unknown`. Missing Asian data must never be silently interpreted
as neutral.

## Removed decision rules

The following former rules must not be restored:

```text
count met rows → setup_score
setup_score → setup_state / risk_state
risk_state → execution_bias
premarket prior → forced intraday defense or release
```

The overlay also does not read `critical_evidence.direction_audit.structural_bias`.
That field was previously consumed before the formal LLM judgement and created a
second, prematurely inherited structure decision. Medium-term structure is judged
once by the LLM from the upstream wave evidence and current structure facts.

## LLM handoff

The LLM reads the five evidence rows, raw metrics, current level anchors, structure
memory and all other point-in-time evidence. It then independently writes:

- medium-term structure and its invalidation;
- window state and next-day path;
- risk state and execution action;
- at least two supporting reasons and the strongest opposing evidence;
- action maintenance and release conditions;
- horizon and next review point.

A strong-looking auction, one pressure label or one participation label cannot be
translated mechanically into an action. The final report must distinguish the
script's **执行风险事实** from the LLM's **执行裁量**.

## Record keeping

Keep the original LLM judgement, frozen forecast and realized market data. Do not
calculate execution scores, hypothetical action returns, defensive false positives,
avoided drawdown or missed-upside summaries. Do not add numerical confidence.
Opening, intraday and close-path settlement remains separate from execution
judgement; old weighted records remain frozen in their independent legacy branch.
