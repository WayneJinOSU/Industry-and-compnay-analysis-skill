---
name: gann-window-direction
description: 在已有江恩时间/空间结果与波浪结构结果的基础上，结合外部市场先验、前序价格路径记忆、关键位突破/拒绝、沪深两市成交量、两融数据和市场内部确认，判断精确江恩时间窗口向上、向下或尚未选择方向，并输出盘前/盘中情景计划。适用于江恩变盘日、时间窗口方向选择、突破失败、支撑跌破、外盘映射和大模型综合研判；不替代江恩或波浪计算，也不把时间点单独当作涨跌信号。
---

# 江恩窗口方向选择

## 目的

本 Skill 是江恩空间共振与波浪结构之后的方向判别层。核心问题不是“江恩时间点天然看多还是看空”，而是：

> **在一个精确交易日上，外部市场给出的先验、前序价格路径和目标日的关键位行为，是否使时间窗口向上、向下，或仍然未决。**

时间点必须保持为单个交易日。不得把精确时间点随意扩展成 ±1 日或 ±2 日窗口；如需研究邻近交易日，只能作为单独的事件后反应分析。

## 调用前置条件：必须先取得上游结果

调用本 Skill 前，先调用或读取：

1. **江恩 Skill**：精确目标交易日、时间来源、`pivot_date`、`confirm_date`、时间共振强度、江恩空间位、支撑压力和目标区。
2. **波浪 Skill**：父级与当前级别的浪段、当前浪状态、备选计数、结构置信度和不确定性。

如果上游结果缺失、确认日晚于目标日、时间点不是正式交易日、波浪输入明显使用未来信息，应先停止方向判断并报告输入缺口；不得在本 Skill 内悄悄重算或补造江恩/波浪结论。

上游结果只是结构输入，不等于方向结论。本 Skill 负责融合：

```text
江恩时间/空间
+ 波浪结构
+ 外部市场先验
+ 前序价格路径记忆
+ 关键位交互
+ 沪深两市成交量与成交额
+ 两融（融资/融券）状态
+ 市场内部确认
→ 时间窗口方向与情景计划
```

## 核心原则

1. **时间点不直接给方向。** 江恩时间点只表示变盘或方向选择的观察时刻。
2. **窗口方向由实际路径选择。** 连续“开盘即最高、收盘接近最低、全天单边阴跌”等重复路径，可能使原本未决或偏强的窗口向下选择；向上突破并被接受，则使窗口向上确认。
3. **外部市场是盘前先验，不是机械映射。** 必须比较外盘方向、外盘内部一致性、A 股前一日表现和内外强弱差，并判断映射是延续、修复、衰减还是失效。
4. **关键位要判断交互状态。** “未突破压力”不自动等于看空；要区分压力拒绝、压力下方蓄势、有效突破、支撑假跌破和支撑有效击穿。
5. **波浪是结构约束。** 波浪可以提高某一情景的解释力，但不能被迫修改来迎合外盘、时间点或当天涨跌。
6. **先验、证据、结论分开。** 清楚区分盘前预期、盘中确认、盘后事实，不能用后续价格行为改写此前可得信息。
7. **大模型只做综合判别。** 价格、沪深两市成交量/成交额、两融数据、空间位、路径特征和时间合法性由确定性程序或上游结果提供；大模型不得自行编造价格、日期或数据。
8. **允许弃权，但不得用弃权抹平结构偏向。** 证据冲突、关键位未确认、波浪计数高度不确定或数据质量不足时，可以把短线窗口状态写成 `unresolved`，也可以把执行状态写成 `abstain`；但必须单独报告 `structural_bias`。只有结构证据本身平衡，或原有偏向已被明确失效，才可把 `structural_bias` 写成 `neutral`。
9. **方向、窗口状态与执行分层。** 分别输出：`structural_bias`（中高周期结构偏向）、`window_state`（本次窗口是否完成方向选择）和 `execution_state/action_bias`（是否立即执行）。“短线未确认”不得自动改写为“结构中性”。
10. **方向判断必须满足时间一致性。** 对相邻历史截点独立重跑时，若没有出现明确的结构失效证据，核心 `structural_bias` 应保持连续；可以改变置信度、触发状态和目标区，但不得仅因一两日反弹把偏空/偏多结构直接改成 `neutral`。
11. **所有结论必须可复盘。** 保存数据截止时间、上游结果版本、输入事件包、模型/提示词版本和最终实际路径。

## 结构偏向与窗口状态：必须分开裁决

方向融合至少维护两个独立轴：

```text
structural_bias: bullish | bearish | neutral
window_state: unresolved | bullish_confirmation | bearish_confirmation | failed_bullish_window | failed_bearish_window
execution_state: observe | wait_for_confirmation | confirmed | reduce_only | abstain
```

裁决顺序固定为：

1. 先判断父级结构、反弹是否形成更高高点/更低高点、关键支撑或压力是否发生有效突破/跌破；
2. 再判断本次精确窗口是否已经完成方向选择；
3. 最后决定是否有足够的收盘、跟随、量价和市场内部证据进入执行状态。

以下规则必须执行：

- `window_state=unresolved` 只表示本次窗口尚未完成确认，不表示 `structural_bias=neutral`。
- 波浪身份仍为候选时，方向仍可明确偏多或偏空；“C浪待证”不等于“方向中性”。
- 短线反弹只有在突破并接受上一级关键压力、或触发上游明确的结构失效条件后，才可把原有偏空结构降为中性；短线反弹本身不得清除未失效的空头风险。
- “反弹未过前高/压力 + 再次跌破同一结构位”属于失败反弹后的二次破位，应提升 `structural_bias=bearish` 和下行延续/C浪候选的优先级。
- “收盘跌破”与“立即追空”分开记录：前者是方向证据，后者还需要反抽失败、跟随或量价确认。
- 若上游没有提供明确失效位，不得自行把某个短线收复当成结构失效；应保留原偏向并把执行状态写成 `wait_for_confirmation`。

每次报告都要说明：

```text
why_structural_bias
why_window_state
what_invalidates_structural_bias
what_confirms_execution
```

## 数据依赖与取数优先级（强制）

本 Skill 的所有行情、宽度、板块、资金、期指和两融数据，统一按以下顺序取数，并在事件包中记录实际来源：

1. **KH 平台数据库/本地 KH DuckDB 与缓存**：优先使用 `tools/kh_local_data.py` 的覆盖检查、补数和读取逻辑；已有本地覆盖时不得重复调用外部接口。
2. **Tushare**：KH 数据库缺失、日期覆盖不足、字段不完整或接口无法提供该类数据时，使用 Tushare 结构化接口补数。优先使用 `index_daily`、`fut_daily`/`fut_mapping`、`margin`、`moneyflow_hsgt`、`index_global` 等历史接口；记录接口名、查询日期和权限/空结果。
3. **同花顺问财（Wencai/`pywencai`）**：KH 与 Tushare 仍缺失时，用于板块/概念排行、市场宽度、涨跌停、异动和资金偏好等可由自然语言查询获得的字段。必须保存**原始查询语句、`query_type`、结果日期、返回行数和获取时间**；不得把未明确日期或盘后回填的数据当作盘前信息。

取数规则：

- 每个字段都要记录 `source`、`data_asof`、`available_at`、`fallback_reason` 和 `data_quality`。
- Wencai 只能作为适合其返回口径的板块/市场内部数据来源，不能替代缺失的 OHLCV、期货结算价或两融历史序列；这些字段在 KH/Tushare 都缺失时必须标记 `unknown`。
- KH、Tushare、Wencai 口径不一致时，优先保留原始值和口径说明，不得静默混合；方向判断应降低置信度。
- 默认不使用网页搜索抓取行情数据；只有用户明确要求，或 KH/Tushare/Wencai 均不可得时才可使用，并标记为低优先级外部资料。
- 任何 fallback 都不能突破 `available_at <= forecast_cutoff`；不能用目标日盘中、收盘或事后发布数据回填盘前判断。

建议在事件包增加：

```text
data_source_priority = ["kh", "tushare", "wencai"]
source_used = {field: "kh|tushare|wencai|unknown"}
fallback_reason = {field: "..."}
wencai_queries = [{query, query_type, result_asof, retrieved_at, rows}]
```

## 工作流

### 0. 固定决策阶段和数据截止时间

先声明当前阶段：

- `premarket`：A 股开盘前；
- `intraday_open`：开盘至前 30 分钟；
- `intraday_update`：盘中更新；
- `post_close_review`：收盘复盘。

记录：

```text
forecast_cutoff
feature_cutoff
available_data_end
symbol
trade_date
timezone
```

盘前判断不得使用目标日的收盘、全天成交量或盘后才可得信息。外盘数据必须确认在 A 股决策截止时间前已经可得。

### 1. 读取并审计上游结果

最低需要：

```text
target_date
pivot_date
confirm_date
time_family
resonance_strength
space_levels
current_wave
wave_confidence
alternative_counts
```

检查：

- `confirm_date < target_date`；
- `target_date` 为正式交易日；
- 江恩空间位有来源、价格单位一致；
- 波浪计数标注当前已确认部分与工作假设；
- 上游输出没有使用目标日之后的数据。

### 2. 建立外部市场先验

整理与标的相关的外部资产、海外行业和期指信息，提取：

```text
external_return
external_strength
external_dispersion
external_sector_consistency
domestic_prior_return
external_domestic_gap
mapping_consistency
mapping_decay
external_risk_level
```

分类为：

```text
supportive
contradictory
reversal_candidate
same_direction_confirmation
weak_or_irrelevant
```

外盘强弱只能改变盘前先验和置信度，不能跳过 A 股自身的竞价、价格和量能确认。

### 3. 提取前序价格路径记忆

至少检查最近 1、2、3、5 个交易日：

```text
open_near_high
open_near_low
close_near_high
close_near_low
open_high_close_low
open_low_close_high
consecutive_bearish_path_count
consecutive_bullish_path_count
same_path_repetition
support_reclaim_failure
resistance_reclaim_failure
intraday_trend
```

重点识别：

- 连续开盘即最高、收盘接近最低；
- 连续开盘即最低、收盘接近最高；
- 连续冲高回落或下探回收；
- 前一天失败的路径在目标日重复；
- 价格在强时间窗口内没有完成预期确认。

### 4. 判断关键位交互

把空间位转成状态，而不是只记录“距离压力/支撑还有多少”：

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
rebreak_after_failed_reclaim
compression
ambiguous
```

判断时同时使用：

```text
penetration_atr
close_above_or_below_level
close_position
upper_shadow_ratio
lower_shadow_ratio
volume_confirmation
follow_through
reclaim_failure
```

未收盘前的突破或跌破只能标记为 `pending`，不得提前写成有效突破或有效击穿。

`rebreak_after_failed_reclaim` 仅在以下组合出现时使用：此前已发生结构位跌破；随后反弹未突破指定前高/压力或未形成结构修复；之后再次收盘跌破同一结构位。该状态是方向增强证据，不要求精确浪段已经完成命名。

#### 4.1 所有浪段的证据—判断转换与预判断

读取上游波浪账本及[全浪段证据—判断转换](../weekly-index-wave-scenarios/references/wave-evidence-transition.md)，对当前活跃主计数、最强备选和关键切换输出“新增证据 → 我会采用的结论”表，不仅针对C浪：

- 覆盖相关浪段的启动、延续、结束或浪级切换；区分机械拐点确认、趋势情景改变和浪段身份提升，关键位突破/跌破不能自动定浪。
- 使用上游已知锚点、反转参数和结构位；列具体证据组合、已发生/待验证状态、原计数→新判断、最强备选，以及软降级和该类型硬失效。
- 可以先转向上行/下行延续而精确浪段仍待证；将某一切换提升主计数须有上一级关系、前段完成依据和当前合规内部结构。不同浪与调整类型不能共用同一硬规则。方向偏向与浪段身份分开裁决，不能因浪段待证而自动输出中性。
- 不回写上游计数或原盘前结果；新增依据作为带截点/来源的 `wave_transition_assessment`，需重数时返回波浪层审计。缺上游浪级/端点时不得在本层补造。
- 没有正式江恩时间中心时，仅给普通价格趋势/浪段的条件判断，不能伪造正式窗口信号；波浪硬违规按既定极值口径检验，与盘中关键位 `pending` 分开。

C启动争议另读[C专项](../weekly-index-wave-scenarios/references/c-wave-launch-prejudgement.md)，它只是通用机制的一个实例。

### 5. 加入沪深两市成交量、两融、市场内部和板块确认

#### 5.1 数据源与时点约束

成交量与两融数据必须遵守以下优先级：

1. 优先读取本地 KH DuckDB/缓存；在本仓库执行时优先复用 `tools/kh_local_data.py` 的读取与补数逻辑；
2. 本地字段或日期覆盖不足时，先用 Tushare 补数；
3. 仅对板块/宽度/异动等适合自然语言查询的字段，在 Tushare 仍缺失时使用 Wencai，并保存原始查询语句与结果日期；
4. 同一 `symbol/field/start/end` 请求应复用本地缓存，避免每次运行重复调用外部接口；
5. 补数后重新从本地库读取，并在报告中记录 `source`、覆盖范围和数据质量；
6. 若仍不可得，填 `null`/`unknown`，不得猜测，也不得把代理字段伪装成真实两市合计。

盘前判断只允许使用 `available_at <= forecast_cutoff` 的数据：

- 目标日盘前不得使用目标日全天成交量或成交额；
- 两融通常有滞后，必须同时记录 `data_asof` 与 `available_at`；
- 目标日之后发布的两融数据不得回填目标日盘前判断；
- `stale` 数据可以作为低权重背景，但不能当作目标日实时确认。

#### 5.2 两市成交量/成交额最低字段

优先使用沪市、深市全市场汇总，而不是单个指数自身的成交额。最低字段为：

```text
sh_volume
sz_volume
sh_amount
sz_amount
total_volume
total_amount
total_amount_change_1d
total_amount_ratio_5d
total_amount_ratio_20d
sh_sz_amount_ratio
sh_amount_change_1d
sz_amount_change_1d
volume_confirmation
volume_divergence
volume_state
volume_data_asof
volume_data_available_at
volume_source
```

其中：

```text
total_volume = sh_volume + sz_volume
total_amount = sh_amount + sz_amount
```

`total_amount` 是方向判断的主量能字段；若只有成交量而没有成交额，应明确标记为 `volume_only`。沪指/深指指数 K 线自身的 `amount` 只能作为 `index_proxy`，不能直接称为两市合计。

至少比较：

- 两市合计成交额相对 5 日、20 日中位数或均值；
- 沪市与深市是否同步放量/缩量；
- 量能扩张是否伴随上涨家数、等权收益和宽基指数同步改善；
- 上涨放量、下跌放量、缩量突破、放量滞涨、放量冲高回落等状态。

#### 5.3 两融最低字段

```text
margin_balance
margin_balance_change_1d
margin_balance_change_5d
margin_balance_change_20d
margin_buy_amount
margin_repay_amount
margin_net_buy
margin_net_buy_ratio
short_balance
short_balance_change_1d
margin_data_asof
margin_data_available_at
margin_source
margin_state
```

其中 `margin_net_buy = margin_buy_amount - margin_repay_amount`。至少区分融资余额、融资买入额、融资偿还额、融资净买入和融券余额；缺失的融券字段保持 `unknown`，不能用融资余额替代。

`margin_state` 只能取：

```text
accumulating       # 融资余额/净买入持续改善
neutral            # 变化小或方向不一致
deleveraging       # 融资余额下降、偿还占优或融券压力上升
stale              # 数据可得但相对目标日明显滞后
unknown             # 没有可审计数据
```

#### 5.4 现有量价与内部字段

```text
volume_ratio_5d
volume_ratio_20d
volume_zscore
turnover_pace
breadth_state
leader_state
sector_confirmation
sector_failure
```

板块信息要区分：

- 外盘强、A 股前一日弱的错位修复候选；
- 内外同向强势的趋势确认；
- 内外同向走弱的回避信号；
- 外盘强但 A 股竞价/早盘不承接的映射失效。

#### 5.5 最近5日基础变化摘要（必填）

每次盘前、盘中更新或收盘复盘，都必须基于**截至当前决策截点已经完成的最近5个交易日**生成一个简短的基础变化摘要。盘前目标日不得把目标日的未完成数据混入这5日序列；盘中如要使用当日部分成交量，必须另列为 `intraday_partial`，不能覆盖最近5个完整交易日。

至少生成以下字段：

```text
recent_5d_summary:
  asof
  trading_dates[5]
  close_change_5d
  amount_change_5d
  volume_change_5d
  amount_change_1d
  volume_change_1d
  amount_down_streak
  volume_down_streak
  amount_up_down_pattern
  positive_days_count
  negative_days_count
  breadth_advance_ratio_5d
  breadth_change_5d
  recent_path_summary
  labels[]
  source
  data_asof
  available_at
  data_quality
```

计算口径固定为：

- `close_change_5d = close_t / close_{t-4} - 1`；
- `amount_change_5d = amount_t / amount_{t-4} - 1`；
- `volume_change_5d = volume_t / volume_{t-4} - 1`；
- `amount_change_1d`、`volume_change_1d` 为最新完整日相对前一完整日的变化；
- `amount_down_streak`、`volume_down_streak` 从最新完整日向前计数，单日下降只能记为 `1`，不得称为“连续缩量”；
- `breadth_advance_ratio_5d` 是5日上涨家数占比序列或其摘要，`breadth_change_5d` 是最新值相对5日前值的变化；
- 若使用沪深全市场汇总，成交额优先；只有指数自身成交额时必须标记 `amount_basis=index_proxy`，不得伪称为沪深两市合计。

`labels[]` 只能从可解释的描述性标签中选择，例如：

```text
连续放量
连续缩量
先放量后缩量
高位缩量回落
放量上涨后缩量滞涨
量价背离
宽度同步改善
宽度先于价格恶化
价格上涨但量能收缩
价格下跌且量能放大
```

判读规则：

1. 最近5日摘要是描述性统计，不得单独决定窗口方向；必须与关键位、前序路径、宽度、波浪和外盘共同判断。
2. “连续缩量”至少需要最近2个已完成交易日成交额或成交量连续下降；只有最新1日下降时只能写“单日缩量”或“高位缩量回落”。
3. “连续放量”同样至少需要连续2个已完成交易日上升；涨跌与量能方向不一致时，优先使用“量价背离”或“放量滞涨”等中性描述。
4. 若5日中成交额、成交量或宽度口径不完整，保留 `null/unknown`，降低 `data_quality`，不得用主观印象补齐。
5. 两融也要尽量提供 `change_1d/change_5d/change_20d`；若最新两融只到更早日期，必须单独标注 `data_asof`、`available_at` 和 `stale`，不得臆造5日趋势。

报告中至少用一句自然语言直接呈现，例如：

> 最近5日价格先升后弱，最新一日缩量回落；尚未形成连续缩量，但宽度已先于价格转弱。

#### 5.6 交给大模型的量价输入格式

量价数据不得只以一句自然语言结论输入，也不得只把5日原始表格直接交给大模型。标准输入采用“三层结构”：

```text
最近5个完整交易日原始序列
+ 程序确定性计算的5日摘要
+ 5日/20日基准与异常程度
```

**第一层：最近5日原始序列。** 至少提供以下字段，并保持日期升序：

```text
date
open
high
low
close
pct_chg
volume
amount
advance_ratio
```

如有可靠数据，可增加 `decline_ratio`、`limit_up_count`、`limit_down_count`、`sh_amount`、`sz_amount`；缺失字段填 `null`，不得用估算值补齐。最近5日必须是截至决策截点已经完成的5个交易日；目标日盘中部分数据另列为 `intraday_partial`，不得覆盖完整5日序列。

**第二层：确定性摘要。** 由程序计算并传入，不要求大模型重新做算术：

```text
close_change_5d
amount_change_5d
volume_change_5d
amount_change_1d
volume_change_1d
amount_down_streak
volume_down_streak
positive_days_count
negative_days_count
breadth_change_5d
amount_up_down_pattern
recent_path_summary
labels[]
```

大模型可以检查摘要与原始序列是否一致；若不一致，应以可审计的原始序列为准，并将数据质量降级，而不是自行选择有利数字。

**第三层：5日/20日基准。** 至少提供：

```text
amount_vs_5d_median
amount_vs_20d_median
volume_vs_5d_median
volume_vs_20d_median
volume_zscore_20d
close_vs_20d_ma
breadth_vs_20d_avg
```

5日序列用于识别“先放量后缩量、连续缩量、放量滞涨、量价背离”等路径；20日基准用于判断当前量能是正常波动还是显著异常。没有20日覆盖时填 `null/unknown`，不得把5日变化直接称为长期异常。

输入优先级固定为：

```text
原始5日序列用于审计
→ 确定性摘要用于快速识别
→ 5日/20日基准用于异常校准
→ 大模型结合关键位、波浪、宽度、两融和外盘做方向判断
```

标签只是辅助提示，不能替代原始序列。特别是：

- 只有最新1日成交额下降，只能标记“单日缩量”或“高位缩量回落”；
- 最近2个或以上完整交易日连续下降，才可标记“连续缩量”；
- “连续缩量下跌”必须同时满足价格连续走弱，不能由量能单独推出；
- 最近5日价格上涨、量能收缩时，优先考虑“上涨但跟随不足”或“量价背离”，不要直接写成趋势反转；
- 两融只有最新可得日数据时，传入 `data_asof`、`available_at` 和 `stale/unknown`，不得臆造5日趋势。

### 6. 融合波浪结构

优先判断：

```text
波浪硬约束是否允许当前情景
当前是趋势延续、调整中继还是潜在终点
突破/跌破是否支持某一备选计数
波浪不确定性是否足以要求弃权
```

决策层级固定为：

```text
数据时点/未来函数审计
→ 波浪硬约束与父级结构
→ 前序路径、反弹高低点和关键位交互
→ 外部市场与市场内部确认
→ 沪深两市成交量/成交额与两融
→ 江恩时间/空间对合法情景排序
```

外盘、量价和两融可以改变置信度与执行状态，但不能在没有结构失效证据时抹除已经形成的 `structural_bias`。

江恩可以帮助排序和定位，不能修复波浪硬规则违规。

### 7. 两市成交量与两融的方向确认规则

两市成交量、两融只作为确认/反确认，不得单独产生方向结论。按以下规则记录证据：

#### 偏多确认

满足越多，越支持窗口向上，但仍需关键位和价格路径确认：

- 两市合计成交额高于 5 日或 20 日基准；
- 沪深成交额同步扩张，而非仅一市独立放量；
- 成交额扩张伴随上涨家数、等权收益和宽基指数同步改善；
- 融资余额连续增加；
- 融资净买入为正，且不是单日异常脉冲；
- 放量突破压力后能够跟随并接受在压力上方。

#### 偏空确认

- 两市合计成交额放大但指数冲高回落；
- 下跌家数扩大，成交额主要集中在下跌方向；
- 沪深成交额同步放大且价格跌破支撑；
- 融资余额下降；
- 融资偿还额明显高于融资买入额；
- 两融去杠杆与支撑跌破同时出现。

#### 中性/冲突

- 总成交额放大但上涨家数不增；
- 沪市放量、深市缩量，或相反；
- 两融余额增加但指数无法突破；
- 两融数据只有前一日或更早日期，不能与目标日盘前状态严格同步；
- 量能、两融与价格/波浪方向冲突时，优先降级为 `unresolved`、`neutral` 或 `abstain`，不得用叙事强行单边化。

建议在融合前生成：

```text
volume_margin_evidence
volume_margin_conflict
volume_margin_data_quality
```

其中 `volume_margin_data_quality` 取 `complete|partial|stale|insufficient`。

### 8. 确定窗口状态

同时输出三个状态，不得把它们合并成一个 `direction`：

```text
structural_bias: bullish | bearish | neutral
window_state: unresolved | bullish_confirmation | bearish_confirmation | failed_bullish_window | failed_bearish_window
execution_state: observe | wait_for_confirmation | confirmed | reduce_only | abstain
```

判读要求：

- `window_state=unresolved` 可以与 `structural_bias=bearish` 或 `structural_bias=bullish` 同时存在；
- `structural_bias=neutral` 必须列出结构平衡证据，或明确写出原有偏向的失效条件已经发生；
- 关键位收盘跌破且反抽失败时，先提升结构偏向；是否立即执行另由 `execution_state` 决定；
- 反弹未过前高后再次跌破同一支撑，优先标记为 `rebreak_after_failed_reclaim`，不得仅因外盘或短线反弹输出 `neutral`。

主状态必须有：

```text
支持证据
反方证据
触发条件
失效条件
未决因素
```

### 9. 由大模型生成情景计划

不得只输出“涨/跌”。至少输出：

- 基准情景；
- 向上确认情景；
- 向下确认情景；
- 极端风险情景；
- 第一目标和第二目标；
- 失效位；
- 观察条件；
- 行动偏向；
- 是否弃权。

详细输入输出协议见 [references/llm-judgement-contract.md](references/llm-judgement-contract.md)；两市成交量与两融字段和时点规范见 [references/volume-margin-confirmation.md](references/volume-margin-confirmation.md)。

### 10. 盘中更新和收盘复盘

盘中只更新新增可得信息，不回写盘前判断。重点记录：

```text
auction_state
opening_gap
first_30m_path
volume_pace
sector_confirmation
key_level_acceptance
window_state_transition
```

收盘后复盘：

```text
盘前先验是否正确
路径记忆是否有增量
外盘映射是否成立
窗口是否完成方向选择
关键位是否被接受/拒绝
大模型是否只是事后解释
```

## 最低输出格式

中文输出，使用以下结构：

```text
一、数据截止时间与输入完整性
二、上游江恩结果摘要
三、上游波浪结果摘要
四、外部市场先验
五、前序价格路径记忆
六、关键空间位交互
七、成交量、板块和市场内部确认
八、结构偏向、窗口状态与执行状态
九、基准/向上/向下/极端风险情景
十、目标位、失效位和观察条件
十一、置信度、反方证据与是否弃权
```

## 明确禁止

- 未先取得江恩和波浪结果就独立输出最终方向；
- 把江恩时间点直接解释为必涨或必跌；
- 把“未突破压力”直接等同于看空；
- 把盘中触碰支撑直接等同于支撑失效；
- 用目标日收盘数据进行目标日盘前预测；
- 用绝对成交额阈值替代波动率、市场规模和时段标准化；
- 让大模型编造外盘数据、价格位、时间点或波浪计数；
- 将置信度当成未经校准的真实概率；
- 在没有样本外验证时宣称某个路径模式具有稳定预测力。

## 参考资料

按当前任务只读取相关文件：

- [references/methodology.md](references/methodology.md)：总体方法和决策层级；
- [references/window-state-machine.md](references/window-state-machine.md)：窗口状态和关键位状态转换；
- [全浪段证据—判断转换](../weekly-index-wave-scenarios/references/wave-evidence-transition.md)：所有浪的启动/延续/结束/浪级切换，具体新增证据→采用结论与软/硬失效；
- [C专项](../weekly-index-wave-scenarios/references/c-wave-launch-prejudgement.md)：通用机制在C启动争议中的应用；
- [references/path-memory.md](references/path-memory.md)：连续K线路径和失败路径定义；
- [references/external-market-mapping.md](references/external-market-mapping.md)：外盘先验、内外映射和时间戳审计；
- [references/llm-judgement-contract.md](references/llm-judgement-contract.md)：大模型输入、输出和弃权协议；
- [references/backtesting.md](references/backtesting.md)：标签、消融、样本外和未来函数审计；
- [references/report-template.md](references/report-template.md)：盘前、盘中和盘后报告模板。
