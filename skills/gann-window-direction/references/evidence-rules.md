# Evidence rules

## Independent states

Maintain three axes:

```text
structural_bias: bullish | bearish | neutral
window_state: unresolved | bullish_confirmation | bearish_confirmation |
              failed_bullish_window | failed_bearish_window
execution_state: observe | wait_for_confirmation | confirmed | reduce_only | abstain
```

`direction` is a separate event-level output. It is the modal close-bin
direction. It is not copied from `structural_bias`.

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

`uninformative` never means neutral and cannot anchor the modal branch. Missing
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

The default mean-reversion floor is 25%. A state-specific floor of 35% is allowed
only if:

```text
sample >= 30
T+1 excess over baseline >= 5pp
p < 0.05
```

The floor belongs to the matching state. Never aggregate one state’s 35% into
another state or into a general “market bottom” rule.

## Scenario boundaries

All four bins are close-price bins for settlement. They are not the same as the
full intraday path.

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

## Weights

Weights rank scenarios. They are not calibrated probabilities.
No single scenario may exceed 50%.

Use state variables:

```text
weekly_regime
funding_state
breadth_state
information_content
matched base rates
extreme state
```

Do not increase a scenario weight because a nearby support has a high historical
hold rate. Levels do not count as independent evidence dimensions.

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
