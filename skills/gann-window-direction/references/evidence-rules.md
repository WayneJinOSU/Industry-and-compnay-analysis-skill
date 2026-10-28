# Evidence rules

## Independent states

Maintain three axes:

```text
structural_bias: bullish | bearish | neutral
window_state: unresolved | bullish_confirmation | bearish_confirmation |
              failed_bullish_window | failed_bearish_window
execution_state: observe | wait_for_confirmation | confirmed | reduce_only | abstain
```

`next_day_path` is independent of `structural_bias`. The LLM chooses a baseline
opening → intraday → close path from current anchors. A strong close inside a
bearish structure is a divergence to explain, not an automatic structural
reversal. There is no top-level event-day direction.

## Information content

Classify each layer:

```text
external
volume
margin
breadth
leadership
path
event
```

Use:

```text
informative
weak
uninformative
```

`uninformative` never means neutral and cannot anchor the baseline path. Missing
data is registered and excluded.

## External mapping

```text
tier_1: A50, China proxies, HSI when open
tier_2: N225, KOSPI, TWII, AS51
tier_3: US, Europe, SOX
```

- Use tier 1 for the opening-gap prior.
- If tier 1 conflicts with tiers 2–3, external is `weak`.
- If tier 1 is unavailable, external is `uninformative`.
- SOX is the semiconductor anchor. A broad index cannot replace it silently.
- Gold falling with a driving equity index below −1.5% is cross-asset
  liquidation, not risk-on.
- A live Asia value must carry an observation time no later than cutoff.

## Previous path

Describe, not embellish:

```text
open_near_high
open_near_low
close_near_high
close_near_low
upper_shadow_ratio
lower_shadow_ratio
close_position
same_path_repetition
reclaim_failure
```

Two consecutive low closes are a repeated seller path, not automatically a
bottom. A long lower shadow is a one-day rejection until the next close holds.

## Support and pressure

Use the multi-lens registry. Every displayed level needs:

```text
anchor
member zone
lens count
250-day touches
hold rate
formation window
cluster role
cluster defense level
next non-cluster level
```

Rules:

- `lens_count <= 1` or `touches == 0` is unverified.
- A same-side spatial band is only a defence band if its members share the same
  declared trend leg. Otherwise call it `spatial_proximity_band`.
- A band’s outer level is its defence; interior levels are not additional walls.
- A close outside the outer level changes the relevant scenario. An intraday
  touch does not.
- An isolated recent price-structure level must be disclosed by exact price.
- A gap in the volume profile is separate from a price gap and must be reported
  as a no-cost-support zone.

### Break and reclaim memory

Generate `structure_memory` from the previous report's support/pressure levels
before loading target-day data. A support break remains active until a later
close reclaims that exact level. A new support band cannot erase the old break.

Required states:

```text
support: not_broken | broken_unreclaimed | reclaimed
pressure: accepted | rejected_or_below
recent_path_pressure: met | not_met | unknown
```

`recent_path_pressure=met` includes either an unreclaimed support break or a
weak close near support. This is evidence for execution risk and LLM path
judgement, not a standalone short signal or an automatic path switch.

Also keep `pressure_attempt_memory` for each pressure band. A completed daily bar
tests the band when its high reaches the pressure anchor. The test is a failed
breakout when the close remains below the pressure defense, and an accepted
breakout only when the close reaches the defense. Record the 10-session test
count, failed and accepted close counts, consecutive failed tests, last test
date and status, sessions since the last test, whether failed highs are
descending, and test amount relative to the 10-day baseline. Decision-band width
must be disclosed; width alone cannot count as evidence of a stable range.

## Volume and margin

Use full-market Shanghai + Shenzhen totals where available.

```text
total_amount
amount vs 5-day median
amount vs 20-day median
volume z-score
Shanghai/Shenzhen synchronization
margin balance changes 1/5/20 days
margin net buy
short balance
```

Do not use index-only amount as total-market amount. Do not call a single-day
decline “continuous contraction.” Do not call a volume rise above yesterday a
rise above the 20-day mean.

## Leadership

Required:

```text
leader_ret
market_equal_weight_ret
leadership_spread
gap_up_fade_rate
gap_sample_count
leader_above_rate
leader_rs_4w
state
rebound_quality
```

`leadership_confirming` requires both:

```text
leadership_spread >= +0.3pp
gap_up_fade_rate <= 0.34
```

If no basket member has a qualifying gap, the gap sample is `not_applicable`;
this does not permit a confirming state.

Breadth state uses the same definition across scripts: the latest five-session
mean of advance ratio versus the preceding five-session mean, with a ±8pp
threshold. The latest single-day move is a separate extreme observation.

## Base rates

For a crash, low close or volume outlier, compute next-day rates. A usable state
must match the current definition exactly:

```text
drop
drop_low_close
drop_volume_expansion_1d
drop_volume_above_prior_20d_mean
```

Do not substitute “above yesterday” for “above the 20-day mean.”

## Extreme states

Extreme flags:

```text
breadth_extreme_low
breadth_extreme_high
funding_deleveraging_spike
```

Conditional extreme statistics are evidence, not automatic mean-reversion rules.
Report sample size, baseline, horizon and significance where available. Do not
aggregate one state's result into another state or into a general “market
bottom” rule. Legacy reversal-floor fields never enter the new path contract.

## Close-bin boundaries

All four bins are close-price bins for settlement only. They are not the full
intraday path and do not generate a top-level event-day direction:

```text
向下延续
区间震荡
向上突破
尾部极值（向下）
```

Recommended construction:

```text
tail upper threshold = outside support defense by ~2 ATR
trend lower = tail upper threshold
trend upper = support-band defense
key-test lower = support-band defense
key-test upper = pressure-band defense
breakout/breakdown lower = pressure-band defense
```

This is a default structural construction, not a permanent market threshold. The
final values come from the current level registry and must be auditable.

An intraday level can be an alert without becoming a close-bin boundary. State
this explicitly in the report.

## Discretionary path evidence

The LLM reviews weekly regime, funding, breadth, information content, matched
base rates, extreme states, pressure attempts, break/reclaim memory, current
anchors and window evidence together. Code does not convert these inputs into
scenario weights, calibrated probabilities or a direction ranking.

A nearby support's historical hold rate is not an independent reason to select a
range path. The baseline must state opening, ordered intraday observations and
close zones, then specify the evidence that switches it upward or downward. A
wide-range lower-edge close is weak, not a high-quality balanced-range result.

## Window confirmation

A bullish confirmation requires all:

- close above the structural pressure defense;
- follow-through rather than immediate reclaim failure;
- volume versus 5/20-day baselines;
- breadth and leadership confirmation.

A bearish confirmation requires:

- close below the structural support defense;
- failure to reclaim the level;
- weak or deteriorating close position and path;
- confirming breadth, funding or leadership evidence where available.

Do not use intraday acceptance in a premarket or close-bin decision.
