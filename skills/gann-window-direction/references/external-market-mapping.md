# 外部市场映射

## 目的

外盘信息用于建立A股开盘前的方向先验，不用于机械预测A股当日涨跌。必须考察：

```text
外盘方向
外盘强度
外盘内部一致性
A股前一日相关板块表现
内外强弱差
映射是否延续/修复/衰减/失效
```

## 映射状态

```text
same_direction_confirmation
external_strength_domestic_weakness
external_weakness_domestic_strength
internal_external_conflict
mapping_decay
mapping_failed
irrelevant
```

### 外盘强、A股前一日弱

是反向修复候选，不是自动看多。需要竞价、30分钟路径和主线板块确认。

### 外盘强、A股前一日也强

可能是趋势延续，也可能是高开兑现。需要检查价格是否已经透支、是否接近压力位、成交量是否支持。

### 外盘弱、A股前一日也弱

内外共振走弱，通常降低做多优先级；仍需结合A股是否已经过度释放风险。

### 外盘强弱与A股冲突

不能预先假设谁正确。将其标记为 `internal_external_conflict`，等待A股竞价和关键位行为解决冲突。

## 时间戳审计

每项外部数据保存：

```text
source
market_timezone
published_at
session_end
available_at_shanghai
forecast_cutoff
```

A股盘前预测只能使用在 `forecast_cutoff` 前已可获得的外部数据。不能把A股收盘后的数据用于盘前解释。
