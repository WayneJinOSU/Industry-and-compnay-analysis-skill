# Auction-independent premarket foresight

## Purpose

The normal premarket decision runs before the A-share call auction. It must
identify a high-risk setup from information available after the prior close and
before the target open. Call-auction data is optional and cannot be the only
route to a defensive posture.

The model separates:

```text
direction              event-day close-bin direction
structural_bias        medium-term price structure
execution posture      how much risk to carry before confirmation
```

A neutral close-direction forecast may therefore carry a defensive execution
posture. This is not a contradiction.

## Premarket setup checks

Evaluate six causal checks:

1. `structural_bearish`: parent/weekly structure remains bearish.
2. `active_key_window`: target date lies in a confirmed Gann time window.
3. `pressure_proximity`: prior close is within about 0.75 ATR below the first
   pressure anchor, or already inside the pressure band.
4. `external_extreme`: either a high-beta external chain accelerates sharply, or
   US semiconductors/Nasdaq fall sharply and at least two of Japan, Korea,
   Taiwan and the China proxy confirm downside at the cutoff. This is an
   execution-risk catalyst, not a direct event-day close direction signal.
5. `recent_path_pressure`: either the prior three sessions produced a fast
   rebound, or break/reclaim memory shows an unreclaimed support break or a weak
   close near support.
6. `confirmation_deficit`: volume and/or time-appropriate leadership are not
   informative or not confirming.

Report each check with one of three states: `met`, `not_met` or `unknown`.
Missing inputs remain `unknown`, lower confidence and never count toward the
setup score. At least four of the six checks must be known before classifying
the setup; otherwise `setup_state=unknown`.

For `external_extreme`, an unconfirmed US downside shock with fewer than two
Asia confirmations is `unknown`, not `not_met`. Missing Asia data must never be
silently interpreted as neutral.

## State derivation

Use the count of `met` checks only as an auditable premarket prior:

```text
score >= 4  -> setup_state=risk_zone_euphoria
            -> risk_state=preemptive_defensive
            -> execution_bias=reduce_only

score 2-3   -> setup_state=conditional_watch
            -> risk_state=watch
            -> execution_bias=wait_for_confirmation

score 0-1   -> setup_state=normal
            -> risk_state=normal
            -> execution_bias=observe
```

A confirmed downside combination also triggers `risk_zone_euphoria` with a score
of 3 when all three are true: bearish structure, confirmed external risk shock,
and recent path pressure from break/reclaim memory. These are separate risk
dimensions, so this combination does not require an unrelated fourth check.

These mappings are the code risk reference. The LLM's validated final judgement
selects the actual execution action and must explain any deviation from the
reference using point-in-time evidence.

`preemptive_defensive` means: do not add and reduce existing tactical exposure
until acceptance is demonstrated. It does not claim that support has already
broken or that a wave count is complete.

Once `setup_state=risk_zone_euphoria` is established, a combined snapshot cannot
downgrade it to `normal` or `watch`. It remains `preemptive_defensive` until
pressure is accepted with confirming participation, or strengthens to
`defensive` when pressure is rejected with divergent participation.

## Acceptance and recovery

Acceptance of the pressure zone requires:

- close above the pressure-band defense;
- volume at or above a scenario-specific threshold derived from comparable
  high-open/breakout sessions, not merely the 20-day median;
- breadth and time-appropriate leadership confirmation;
- the next observation remains above the accepted boundary.

If some acceptance fields are unavailable, retain the premarket prior and state
what is missing. Do not default to neutral.

## Optional 09:25 and intraday data

When a snapshot exists:

- confirmed pressure acceptance plus participation confirmation can upgrade
  `preemptive_defensive` to offense;
- an observed pressure rejection plus participation divergence can maintain or
  strengthen defense;
- a strong-looking auction alone cannot override a high-risk premarket setup;
- an early high open cannot clear `preemptive_defensive` before acceptance on
  close or a declared intraday acceptance rule.

## External chain anchors

Track stable, predeclared transmission anchors. Broad indices alone are
insufficient for AI or semiconductor-driven sessions. Include SOX plus relevant
high-beta listed proxies such as ARM and SOXL when available. Record source,
timestamp and availability. These are catalysts and crowding evidence, not
direct A-share direction signals.

## Evaluation

Score this layer separately from close bins:

- drawdown avoided versus a no-action baseline;
- upside missed during confirmed breakout;
- false defensive signals;
- lead time from the first defensive state to the largest drawdown;
- restoration latency after confirmed acceptance.

Do not optimize only for earlier warnings: a strategy that is always defensive
is not a forecast.
