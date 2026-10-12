# 沪深两市成交量与两融确认规范

本文件定义 `gann-window-direction` 使用两市量能和两融数据时的字段、时点与判读规则。

## 1. 两市量能口径

优先使用沪市、深市全市场汇总的成交量/成交额。不要把沪指和深指指数 K 线自身的成交额直接相加后称为“沪深两市成交额”；只有在数据明确标注为全市场汇总时，才能生成 `total_amount`。

字段：

```text
sh_volume
sz_volume
sh_amount
sz_amount
total_volume = sh_volume + sz_volume
total_amount = sh_amount + sz_amount
sh_amount_change_1d
sz_amount_change_1d
total_amount_change_1d
total_amount_ratio_5d
total_amount_ratio_20d
sh_sz_amount_ratio
volume_state
volume_confirmation
volume_divergence
volume_data_asof
volume_data_available_at
volume_source
```

`total_amount` 为主要方向确认字段，`total_volume` 为辅助字段。只有 `total_volume` 时标记 `volume_only`；只有指数自身 amount 时标记 `index_proxy`，降低数据质量等级。

## 2. 两融口径

字段：

```text
margin_balance
margin_balance_change_1d
margin_balance_change_5d
margin_balance_change_20d
margin_buy_amount
margin_repay_amount
margin_net_buy = margin_buy_amount - margin_repay_amount
margin_net_buy_ratio
short_balance
short_balance_change_1d
margin_data_asof
margin_data_available_at
margin_source
margin_state
```

`margin_state`：

- `accumulating`：融资余额/净买入连续改善；
- `neutral`：变化小或方向不一致；
- `deleveraging`：融资余额下降、偿还占优或融券压力增加；
- `stale`：有数据但相对预测截点滞后；
- `unknown`：没有可审计数据。

缺少融券余额时，保留 `null`，不能用融资余额替代。

## 3. 时点审计

盘前情景判断只能使用：

```text
available_at <= forecast_cutoff
```

目标日盘前不得使用目标日的全天成交量/成交额；两融必须同时记录数据日期 `data_asof` 和实际可得时间 `available_at`。如果最新数据只到前一交易日或更早，报告必须说明滞后；不能把它写成目标日盘前实时数据。

## 4. KH 本地优先与外部 fallback

读取顺序固定为：

1. **本地 KH DuckDB/缓存**；
2. KH 覆盖不足时，通过 KH 数据层补数或从本地缓存重新读取；
3. KH 仍缺失时使用 **Tushare** 结构化接口补数；
4. 只有板块、宽度、异动等适合自然语言查询的字段，在 Tushare 仍缺失时才使用 **Wencai/`pywencai`**；保存原始查询语句、结果日期、获取时间和行数；
5. 每次 fallback 都记录 `source`、`fallback_reason`、`data_asof`、`available_at` 和质量等级；
6. 补数后优先回读并缓存到 KH 数据层；
7. 仍缺失则输出 `unknown`，并记录缺口及来源。

Wencai 不得替代 OHLCV、期货结算价、两融历史序列或明确的全市场成交额汇总；这些字段缺失时必须保持 `null`/`unknown`。

## 5. 方向映射

### 偏多确认

- 两市合计成交额高于 5 日或 20 日基准；
- 沪深同步放量；
- 放量伴随上涨家数、等权收益和宽基指数改善；
- 融资余额连续增加且净买入为正；
- 压力突破后得到跟随。

### 偏空确认

- 两市合计成交额放大但冲高回落；
- 沪深同步放量且下跌家数扩大；
- 价格跌破支撑且融资余额下降/偿还占优；
- 两融去杠杆与价格破位同向。

### 冲突或不足

- 一市放量、一市缩量；
- 量增但上涨家数不增；
- 两融增加但无法突破压力；
- 两融数据滞后，或量能/两融与价格、波浪冲突。

冲突时降级 `confidence`，必要时输出 `neutral`/`abstain`。
