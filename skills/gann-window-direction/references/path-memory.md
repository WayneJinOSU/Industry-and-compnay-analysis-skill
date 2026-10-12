# 前序价格路径记忆

## 目的

路径记忆描述市场是否连续以同一种方式完成定价。它不是简单K线命名，而是对“前一日失败路径是否在今日重复”的状态描述。

## 推荐字段

```text
session_date
open_near_high
open_near_low
close_near_high
close_near_low
open_high_close_low
open_low_close_high
intraday_trend
body_ratio
upper_shadow_ratio
lower_shadow_ratio
close_position
support_reclaim
resistance_reclaim
same_path_streak
```

`near_high`、`near_low`、`close_position` 等阈值应按ATR、当日振幅或历史分位数标准化，不要永久固定为某个百分比。

## 重点路径

### 开盘即最高、单边阴跌

不是一根阴线，而是：

- 开盘价接近日内高点；
- 收盘价接近日内低点；
- 盘中高点很早出现；
- 后续反弹不能收复关键价位；
- 相同路径在相邻交易日重复。

连续重复时，尤其发生在强江恩时间窗口内，表示“向上确认失败”的证据增强，窗口可能向下选择。

### 开盘即最低、单边上行

对称地表示：

- 开盘价接近日内低点；
- 收盘价接近日内高点；
- 低点较早出现；
- 回落没有破坏关键位；
- 相同路径重复并获得板块/量能确认。

## 不要过度解释

- 单日开盘即最高不能直接等同于顶部；
- 连续阴线不一定意味着趋势反转；
- 需要结合关键位、量能、外部市场和波浪结构；
- 应将路径模式与非窗口日、相似波动率日进行匹配比较。
