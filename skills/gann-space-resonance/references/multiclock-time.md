# 江恩多时钟时间研究

## 何时使用

当用户要求具体时间点、变盘日、时间之窗、波浪等时、C3/C4/C5结束时间，或复盘某个日期为何有效时，除空间研究外运行多时钟时间账本。时间研究仍不能单独定方向。

## 对外只报重要关键时间点

- 正文、摘要、表格、图注和最终回复统一用“重要关键时间点”；每个条目只写一个完整日期，不输出日期区间、不写“上旬/下旬”，不在正文展开“±N日”容差。
- 关键日期必须来自已冻结、截至分析日已知的锚点所生成的原始 `center_date`，且该中心仍在有效主容差内（被因果/资格规则裁剪到中心之后的窗口不能提供该中心日）。不能取窗口中点、把覆盖密度最高但没有原始中心的日期冒充关键日，或按后来行情移动日期。
- 自然日中心落在休市日时保留原日期并标记“自然日节点/非交易日”，不擅自前移或后移；交易日中心须有交易所日历支持。`estimated_weekday`不进入正式关键日清单或共振计数，缺日历则明确缺口、不编造替代日期；自然日日期可保留，但未核实休市状态时标记“自然日节点/交易状态未核实”。
- 只给重要节点，不把每个覆盖日全部罗列。脚本的默认展示筛选：主自然日容差±2日（±3日仅敏感性，禁止混入排序）；去重后覆盖成员至少3个或保守因果来源至少2类才进入候选。按保守因果来源数、时钟种类数、主容差成员数、同日中心成员数降序，同分取较早日期；相邻2个交易间隔以内的候选保留排名最高者，非交易日之间或与交易日比较时用2自然日去重。最多8个，最后按日期展示。这是展示优先级，不是显著性/概率，也不是已验证的预测模型。
- 每个关键日保留来源时钟、原始中心成员、锚点/确认日、日历状态和重要性依据；缺少波浪段落时不能虚构波浪等时来源。阈值、数量或去重间隔若另行调整，须预先声明并记录，不能为保留某日事后调整。
- `time_key_points.csv`是正式摘要入口；`time_key_point_members.csv`和`multiclock_windows.csv`保留容差、起止、全部来源用于复核，不放到对外摘要中。
- 标题可写“关键时间点”，不得写“精准变盘预测”。日期是单点展示，预测仍有不确定性；方向与是否确认必须结合价格、宽度、跨指数及周线，不能凭关键日直接判涨跌。

## 机械时钟

1. `major_natural`：5%因果ZigZag拐点的预设自然日周期；主容差±2自然日，±3日只作敏感性。
2. `major_trading`：5%拐点后的21、34、55、89、144个交易间隔。
3. `local_trading`：2.5%因果ZigZag拐点后的5、8、13、21、34个交易间隔。
4. `wave_duration`：审定段落的0.618、1、1.618倍时长，同时计算自然日与交易日。

前三类由脚本机械生成；第四类必须通过人工段落CSV声明，脚本不得根据比例反推浪型。

## 运行

只需要KhQuant指数库时：

```bash
python scripts/build_multiclock_time_ledger.py \
  --db /absolute/path/to/index.duckdb \
  --start 2021-01-01 --end 2026-08-31 \
  --projection-end 2026-11-30 \
  --output /absolute/path/to/output
```

如有交易所日历、宽度与波浪段落：

```bash
python scripts/build_multiclock_time_ledger.py \
  --daily /absolute/path/to/index_daily.csv \
  --future-sessions /absolute/path/to/trade_calendar.csv \
  --breadth /absolute/path/to/daily_breadth.csv \
  --peer-indices /absolute/path/to/peer_indices_long.csv \
  --wave-segments /absolute/path/to/wave_segments.csv \
  --projection-end 2026-11-30 \
  --output /absolute/path/to/output
```

`wave_segments.csv`字段：

```csv
scenario,segment,start_date,end_date,projection_anchor_date,projection_anchor_confirm_date
preferred,C3,2026-07-01,2026-07-20,2026-08-18,2026-08-19
```

`projection_anchor_confirm_date`为必填项，应写该投影起点在当时可被确认的日期。窗口早沿会裁剪到确认日之后。

宽度文件需要`date`或`trade_date`，以及`advance_ratio`；也可提供`up`和`traded`由脚本计算。建议同时保留`equal_weight_ret`、`down`。

宽基文件采用长表`date,symbol,close`，至少包含两个、建议包含沪深300、中证500、中证1000和创业板。脚本以日涨跌和MA5/MA20同步比例生成跨指数确认；它是确认证据，不是独立定浪规则。

## 输出

- `major_pivots_5pct.csv`：父级因果拐点。
- `local_pivots_2_5pct.csv`：低级别因果拐点。
- `multiclock_windows.csv`：所有时间窗口与来源族。
- `wave_duration_windows.csv`：可选的波浪等时投影。
- `multiclock_density.csv`：完整覆盖账本，保留窗口数、锚点数和独立来源族数，只用于审计，不逐日复制为关键日。
- `time_key_points.csv`：筛选后的单一关键日期、优先级、来源和日历状态。
- `time_key_point_members.csv`：关键日期对应的成员/锚点/确认日/原始中心/容差/起止审计。
- `daily_confirmation_ledger.csv`：极值候选、价格反转、宽度反转、指数确认、扩散与跨指数确认。
- `multiclock_summary.md`：重要关键时间点和实际确认状态，不展示日期区间。

若未来日期未提供交易所日历，脚本用工作日估算并标记`estimated_weekday`。正式报告不得把该日期写成精确交易日，须在获取交易所日历后重跑。

## 解释纪律

- `window_count`表示成员数，`source_family_count`表示时钟种类；`independent_family_count`采用更保守的因果来源口径。
- 5%/2.5%、自然日/交易日时钟都来自价格拐点机制，统一归入`price_pivot_clock`；同一锚点的多个比例、同一族的多个周期、多个锚点或多个容差均不得重复加权。人工波浪等时归入`wave_duration`，但共享结构账本或事后选锚时仍须披露依赖关系。
- 低级别交易日窗口可以提示极值或首次确认，但不能越级确认父级浪。
- 区分`pivot_date`、`confirm_date`和窗口内实际出现的`extreme_date/confirmation_date`。
- 时间窗与价格支撑/压力、宽度和跨指数方向相冲突时，记录“时间到而方向未确认”。
- 对某个历史日期的解释必须先证明该窗口能够使用当时已经确认的锚点生成；事后新增锚点的漂亮解释一律剔除。

## 统计边界

自然日、交易日和波浪等时分别计算覆盖率、命中率和多重校正。增加时钟会提高日期覆盖率，因此不得用“更多窗口命中更多拐点”证明提升。正式提高模型权重前，至少滚动检验极值、首次确认和周线确认三类目标，并与简单的固定日期覆盖基线比较。
