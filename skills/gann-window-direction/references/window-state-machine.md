# 窗口与关键位状态机

## 结构偏向状态

窗口状态与结构偏向分开记录：

```text
structural_bias: bullish | bearish | neutral
window_state: unresolved | bullish_confirmation | bearish_confirmation | failed_bullish_window | failed_bearish_window
execution_state: observe | wait_for_confirmation | confirmed | reduce_only | abstain
```

`unresolved` 只表示窗口尚未选择方向，不得自动映射为 `structural_bias=neutral`。如果此前存在反弹失败、较低高点或关键支撑失守，只要没有明确的结构失效证据，就保留相应的偏空结构。

### 失败反弹后的二次破位

```text
反弹未过前高/指定压力
+ 再次收盘跌破同一结构支撑
= rebreak_after_failed_reclaim
= structural_bias 向下增强
```

这可以先改变趋势方向判断或提高C浪候选优先级，但不自动完成精确浪段命名。只有收复破位位、继续突破上一级压力，或触发上游明确的硬失效条件，才可将原有偏向降级为中性。

## 窗口状态

```text
unresolved
bullish_confirmation
bearish_confirmation
failed_bullish_window
failed_bearish_window
```

### unresolved → bullish_confirmation

至少同时满足：

- 关键压力位收盘突破；
- 突破幅度相对ATR足够；
- 成交量或成交额相对近期基线确认；
- 后续价格没有快速收回压力位下方；
- 市场内部或主线板块没有明显反向拖累。

### unresolved → bearish_confirmation

至少同时满足：

- 关键支撑位收盘跌破；
- 跌破后不能快速收复；
- 收盘位置偏弱或卖压持续；
- 前序弱势路径重复/恶化，或外部风险与内部走弱一致。

### 强窗口下的路径升级

如果时间窗口之前已经出现“开盘接近最高、收盘接近最低、全天单边走弱”，目标日再次重复，且没有重新站回关键位，可把窗口从 `unresolved` 或 `failed_bullish_window` 更新为 `bearish_confirmation` 候选。

如果前序“开盘接近最低、收盘接近最高、全天单边走强”重复，并伴随压力位突破和板块确认，可更新为 `bullish_confirmation` 候选。

## 关键位状态

```text
not_tested
approaching
testing
resistance_rejection
breakout_pending
breakout_accepted
support_rejection
breakdown_pending
breakdown_accepted
compression
ambiguous
```

盘中未收盘时，使用 `breakout_pending` 或 `breakdown_pending`，不得提前确认。

## 价格状态不等于波浪状态

突破/跌破被接受，或窗口向上/向下确认，不自动等于任何特定浪的启动、延续或完成。所有活跃浪都按[全浪段证据—判断转换](../../weekly-index-wave-scenarios/references/wave-evidence-transition.md)分别记录拐点、趋势、波浪和窗口状态，并给出具体“新增证据→采用结论”。没有正式时间中心的普通价格判断不能伪装成江恩窗口确认。

反向收复关键位或跟随失败是原方向情景的软降级；浪段是否硬失效，必须按该浪级和结构类型的既定硬规则另审。硬违规按已声明极值/精度口径检验，不能用盘中 `pending` 或未收盘豁免；禁止为保留计数静默移锚。

## 目标和失效

- 压力拒绝：第一目标通常是最近支撑，第二目标是更低的经验证空间位；重新站稳压力位则方向失效。
- 压力突破：第一目标通常是下一个阻力或空间位；重新跌回并不能收复时降级为假突破。
- 支撑拒绝：第一目标通常是最近压力；再次收盘跌破支撑时失效。
- 支撑跌破：第一目标通常是下一个支撑；重新收复破位支撑时降级为假跌破。若此前已有反弹失败，再次跌破同一支撑时标记为 `rebreak_after_failed_reclaim`，方向偏空增强；不得仅因窗口仍未完全确认而改写为结构中性。
