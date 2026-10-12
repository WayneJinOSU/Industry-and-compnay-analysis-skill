---
name: gann-space-resonance
description: 对A股指数执行无前视江恩空间与多时钟共振研究，以K线/日线结构优先，分离极值日和价格/宽度/跨指数确认日，并让江恩参与候选排序和目标校验，融合波浪父级1–5账本，输出圆周图、重要关键时间点（单一日期，不报时间区间）与未来4–12周情景。Use when 用户要求江恩理论、江恩空间/时间共振、变盘日、支撑压力、圆周图、Square-of-9、当前浪、C3/C4/C5或多技术线联合研判；不用于脱离价格结构把几何线直接当交易信号。
---

# 江恩空间共振

## 核心原则

1. 先计算随机价格覆盖率，再评价命中率；主结论只看超额与校正后显著性。
2. 只使用目标日前已确认的锚点。保留 `pivot_date` 与 `confirm_date`，锚点须满足 `confirm_date < target_date`。
3. 把八分法、历史记忆、角度线、圆周图视为四个独立来源。同一家族多条线靠近只增加成员数，不增加独立来源数。
4. 将分割位作为主线；角度线作为辅助；圆周图、历史顶底和整数关口用于定位。不得因线多、命中率高而宣称有效。
5. 默认降级时间周期。用户明确要求时运行因果多时钟账本并做覆盖率、多重校正和日历审计；不得把探索性的120日、720日或单次日期吻合写成已验证规律。
6. 融合层级固定为：波浪硬规则 → K线/日线内部三五浪结构 → 节奏量价 → 江恩空间共振 → 宽度/龙头/事件。江恩可在两个合规计数间调整排序和目标区，不能修复硬规则违规。
7. 最终必须同时给出江恩圆周图、父级1–5浪账本、日线结构与节奏量价证据、当前浪、未来4–12周主情景和文字描述。

8. **时间结果只交付重要关键日期，不交付日期区间。** 所有“后续重点投影窗口”“江恩时间窗口”“变盘时间”“波浪等时”等对外章节，统一写成“重要关键时间点”，每行一个明确日期；不得用“9月28—30日”“10月上旬”或“某日±2日”替代。容差和窗口起止只保留在审计文件，不删除底层误差口径；关键日是观察节点，不是必然变盘日。具体筛选见时间研究参考。

## 数据源与缓存规则（KH 优先）

- 江恩的指数/个股日线 OHLCV **必须先读取本地 KH DuckDB**，默认数据根目录由 KH 配置中的 `duckdb_data_path` 决定（本机通常为 `/Users/a/khquant/data`）。不得每次运行直接调用 Tushare/BaoStock。
- 统一入口为工作区的 `tools/kh_local_data.py`：先检查标的、周期和请求区间的本地覆盖；覆盖完整则只读本地库；覆盖不足才执行 `kh data scan --fix`，必要时由 KH CLI 执行一次 `kh data download`。补数完成后必须重新从本地库读取。
- 补数请求写入 `~/.cache/khquant/skill_data_manifest.json`。相同 `code/period/start/end` 在 24 小时内不重复触发补数；只有数据覆盖仍不足且明确使用 `--force-supplement` 时才重试。
- 输出 `kh_data_metadata.json`，记录本地数据库路径、补数前后覆盖范围、补数来源和是否过滤了 `date > as_of` 的未来行。历史截点分析必须在读取后再次过滤 `date <= as_of`。
- 若本地库与 KH 补数均不能覆盖请求区间，应报告数据缺口并停止统计结论；不得静默改用未经记录的外部接口。

开始前完整阅读 [references/methodology.md](references/methodology.md)。
涉及当前浪或未来判断时，同时完整阅读 [references/wave-integration.md](references/wave-integration.md)。
涉及具体时间点、时间窗口、变盘复盘、波浪等时或C3/C4/C5结束时间时，同时完整阅读 [references/multiclock-time.md](references/multiclock-time.md)。
涉及静态K线图、父级浪账本图、C3/C4/C5争议图、支撑压力带或交付视觉质量时，同时完整阅读 [references/charting.md](references/charting.md)。

## 工作流

### 1. 确定输入

- 指数默认使用最近5年不复权日线 OHLCV，5% high-low ZigZag。
- 个股使用前复权结构数据并另备不复权市场记忆价；默认12% ZigZag。个股不可直接套用指数回归数字。
- 审计缺失值、重复日期、OHLC关系和交易日排序。审计失败时停止统计结论。

### 2. 运行指数研究

优先使用与 KhQuant 数据环境一致的 Python。推荐直接传 KH 代码，由脚本完成本地检查和必要补数：

```bash
python3 scripts/run_gann_space_resonance.py \
  --kh-code 000001.SH \
  --start 2021-08-16 \
  --end 2026-09-22 \
  --symbol 上证指数 \
  --output /absolute/path/to/output
```

如需先单独检查/补数或批量准备多个指数：

```bash
python3 /absolute/path/to/khquant/tools/kh_local_data.py ensure \
  --code 000001.SH --start 2021-08-16 --end 2026-09-22 --json
```

只有在已经确认是 KH 本地 DuckDB 文件时，才使用兼容参数 `--db /absolute/path/to/security.db`；不要把 Tushare 导出的临时 CSV/数据库冒充 KH 数据源。

脚本生成拐点、空间位、共振簇、触碰事件、随机基线、统计表、Markdown结论和 `gann_circle.html`。始终传绝对路径，不写入技能目录。时间研究可同时传入交易所日历、日度宽度、宽基指数和人工审定波浪段落：

```bash
python3 scripts/run_gann_space_resonance.py \
  --kh-code 000001.SH \
  --start 2021-08-16 --end 2026-08-31 \
  --projection-end 2026-11-30 \
  --future-sessions /absolute/path/to/trade_calendar.csv \
  --breadth /absolute/path/to/daily_breadth.csv \
  --peer-indices /absolute/path/to/peer_indices_long.csv \
  --wave-segments /absolute/path/to/wave_segments.csv \
  --symbol 上证指数 --output /absolute/path/to/output
```

也可单独运行 `scripts/build_multiclock_time_ledger.py`。正式交易日日期必须来自交易所日历；`estimated_weekday`只能作为临时估算并在报告中警告。

### 3. 审核统计结果

重点读取：

- `statistical_results.csv`：比较 `hit_rate`、`baseline`、`excess`、`p_adjusted`。
- `support_resistance_summary.csv`：比较触碰后的成功率与匹配基线。
- `current_levels.csv`：读取成员区间、中心、距最新收盘、独立来源数。

使用以下裁决：

- `p_adjusted < 0.01`、超额至少 `+10pp`、样本至少60：有效。
- `p_adjusted < 0.05`、超额至少 `+5pp`：有苗头；样本不足60时必须写“待扩样”。
- 高命中但基线同样高：无增量，降级。
- 触碰后不优于匹配基线：不得称为可交易支撑/压力。

时间输出另行审核：

- `major_pivots_5pct.csv`、`local_pivots_2_5pct.csv`：父级与低级别因果拐点及确认日。
- `multiclock_windows.csv`、`wave_duration_windows.csv`：自然日、交易日和波浪等时窗口。
- `multiclock_density.csv`：`window_count`是窗口成员，`source_family_count`是时钟种类，`independent_family_count`是保守因果来源数；共享价格拐点的5%/2.5%、自然日/交易日时钟不得重复加权。
- `daily_confirmation_ledger.csv`：极值候选、价格反转、宽度反转、指数确认、扩散及跨指数确认必须分列。
- `time_key_points.csv`：重要关键日期、排序、来源、锚点和日历状态；正式摘要以此为准，不逐日抄录窗口覆盖表。
- `time_key_point_members.csv`：各关键日的原始成员、中心、容差和起止日期，仅供审计。
- `multiclock_summary.md`：仅列重要关键时间点，检查日历状态和“时间到而价格未确认”。

不得事后移动锚点、切换自然日/交易日、扩大容差或改波浪段落来保留目标日期。先冻结候选锚点和计数，再看窗口；外部时间观点必须记录原始发布时间、方向、容差和确认定义。

### 4. 图文交付

先按 [references/charting.md](references/charting.md) 的图表规范设计交付组合：父级结构周线图、调整浪日线审计图、当前局部结构图和独立江恩圆周图。先生成不含江恩线的价格优先图并检查K线、成交额、浪标、支撑/压力带和失效位，再生成圆周图；图表必须经过图像查看器视觉检查，不能只凭脚本成功结束判断完成。

先用不含江恩线的K线图形成初始波浪账本，并完成日线内部形态、速度、重叠、成交额和动能审计。优先调用 `weekly-index-wave-scenarios` 的父级计数、日线结构和龙头验证流程。随后把江恩区间纳入融合矩阵：它可以提高/降低两个合规计数的排序，定位波浪目标簇，或促使显式回查拐点；不得仅因江恩吻合而选择浪型。若融合后修改初始计数，报告必须列出原计数、触发修改的证据和新失效位。

当争议涉及C3/C4/C5、二次探底或调整是否结束时，报告必须展示一张不含江恩线的日线价格图或等价的日线段落账本，再展示江恩圆周图。日线账本至少比较首选/备选的三浪或五浪性格、交易日数、单位时间位移、重叠、成交与MA5/10/20；没有分钟数据时区分“极值锚点”“结构工作锚点”和“顺序待证”。

波浪报告必须包含完整父级1–5浪、当前浪的首选/备选计数、4–12周主路径、验证位、重判位和硬失效位。

将审定后的波浪Markdown合并进圆周图报告：

```bash
python scripts/render_circle_report.py \
  --results /absolute/path/to/output \
  --symbol 上证指数 \
  --wave-report /absolute/path/to/wave_scenario.md \
  --output /absolute/path/to/output
```

生成的主交付包括 `gann_wave_report.html`、`gann_circle.html` 与追加波浪正文的 `gann_summary.md`。

圆周图必须标出：

- Square-of-9锚点、锚点日期与最新收盘。
- 90°主角度点。
- 最近支撑、最近压力和来源最多的共振区。
- 支撑/压力成员区间，而非只画一个中心点。

文字必须紧邻图形并包含：

1. 最新收盘与所处区间。
2. 最近两级支撑和压力。
3. 每个关键区的独立来源：分割位、角度线、圆周图、历史记忆。
4. 哪一类工具有历史超额，哪一类只是几何定位。
5. 样本量、随机基线、显著性与“非交易建议”声明。
6. 当前最可能处于哪一浪、确认/重判/硬失效位以及未来4–12周路径。
7. 日线内部形态和节奏量价为何支持/反对该浪型，以及最强反证。
8. 江恩区间与波浪比例的联合观察区，并明确江恩增加的是空间信息而非浪型合法性。
9. 重要关键时间点逐日列出四时钟来源（未提供的注明缺失）、因果来源数、交易所日历状态、重要性依据和价格确认条件；极值/价格/宽度/跨指数/周线确认仍分别列实际日期。对外不列时间起止区间；容差、完整窗口和筛选过程留在审计文件。

若在支持内联可视化的 Codex 应用中工作，优先把圆周图直接呈现在对话中；同时保留 `gann_circle.html` 和 `gann_summary.md`。

## 禁止事项

- 禁止用样本内最终最低点在其出现前生成信号。
- 禁止把同一家族的3/8、1/2、5/8算作三个独立共振来源。
- 禁止只报裸命中率，不报覆盖率基线。
- 禁止事后挑选最佳角度、周期或容差而不标注探索性。
- 禁止把当前几何共振直接翻译成买卖建议。
- 禁止因某个江恩区间吻合就选择波浪计数；必须先独立审定父级结构。
- 禁止在未列出父级1–3浪证据时把调整命名为4浪。
- 禁止只列斐波那契或江恩比例而不检查日线内部三浪/五浪、速度、重叠与成交性格。
- 禁止在没有分钟数据时虚构同日高低点顺序；结构工作锚点必须与绝对极值锚点并列审计。
- 禁止把共享价格拐点生成的多种时钟、多个容差或多个比例写成独立证据。
- 禁止把极值日、首次反转日、宽度先行日、指数确认日和周线确认日合并成一个“精准变盘日”。
- 禁止在正式报告中用工作日估算替代交易所日历而不披露。

- 禁止把时间容差展开成一串同等重要日期、把连续日期合并成区间，或为凑出精确日期而取区间中点/事后峰值；空间支撑压力仍保留成员区间，不受此时间输出规则影响。
