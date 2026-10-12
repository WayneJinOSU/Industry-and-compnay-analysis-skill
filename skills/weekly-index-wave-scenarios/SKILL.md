---
name: weekly-index-wave-scenarios
description: Produce auditable 4–12 week A-share index scenarios using multi-degree Elliott structure, price-first daily morphology, multi-clock timing, separate extreme/confirmation dates, rhythm/volume, optional Gann spatial resonance, breadth, cross-index confirmation, leadership, and verified events. Use for weekly index outlooks, evidence-driven launch/continuation/completion and degree transitions across all waves, C3/C4/C5 versus completed-C disputes, second-bottom paths, or distilling an expert's wave-counting method without losing independent audit.
---

# Weekly Index Wave Scenarios

Use this skill to make a decisive weekly market forecast. Lead with one predicted path, target point or target zone, and time window; then prove that judgement through wave structure, **time confirmation**, market internals, leaders, liquidity, policy, and events. A forecast is incomplete unless it states both where the turn is expected and what time evidence confirms, delays, or invalidates that turn.

## Scope and defaults

- Default market: A-share broad indices (`000300.SH`, `000001.SH`, `399006.SZ`, `000852.SH`). Resolve other indices before fetching data.
- Hierarchy: monthly chart establishes the regime; weekly chart establishes the scenario; daily data may confirm a weekly level but cannot overrule it alone.
- A-share adaptation: preserve Elliott hard rules while treating complex adjustment, overlap, sector rotation and second-bottom paths as explicit candidates rather than forcing a clean US-style impulse. Read [references/a-share-wave-counting.md](references/a-share-wave-counting.md) before counting an active wave 2/4, C wave, second bottom, or post-policy jump.
- For an index report, use at least two calendar years of weekly context. Always include a parent-wave ledger for waves `1`–`5`: give dates, prices, duration and status for every leg. Mark an unfinished or unproven leg as `进行中`/`待验证`/`未启动`; never invent its endpoint. State which numbered parent wave the current `A-B-C` is correcting; if that parent cannot be evidenced, explain why each unresolved wave remains unresolved.
- Horizon: 4–12 weeks. Use weekly closes for confirmation.
- Output language: Chinese unless the user asks otherwise.
- Decision order: parent hard structure first; then daily internal three/five-wave character and rhythm/volume; then Fibonacci/Gann spatial resonance; then breadth, leaders and events. Lower layers may reorder two valid counts but cannot repair a hard-rule violation.
- Before resolving an active daily subwave dispute or distilling an expert view, read [references/daily-structure-rhythm-and-expert.md](references/daily-structure-rhythm-and-expert.md).
- Before giving a current-wave endpoint, specific date/window, second-bottom date, or retrospective timing judgement, completely read [references/time-confirmation-ledger.md](references/time-confirmation-ledger.md).
- For every active wave judgement, read [references/wave-evidence-transition.md](references/wave-evidence-transition.md) and provide a concrete `新增证据 → 我会采用的结论` table for its key launch, continuation, completion or degree-transition branches. Separate mechanical pivots, price trends and wave identity; cover strengthening, soft downgrade and hard invalidation rather than only reporting a label/score. For a C-launch dispute, additionally read [references/c-wave-launch-prejudgement.md](references/c-wave-launch-prejudgement.md) as a specialization, not the general rule.


## 数据源与缓存规则（KH 优先）

- 指数和领导股的日线价格数据优先来自 KH 本地 DuckDB，而不是每次直接访问 Tushare。统一入口为工作区 `tools/kh_local_data.py`。
- 入口先检查本地 `1d` 覆盖范围；完整覆盖时只读本地库并因果聚合周线；缺失时先调用 KH 平台的 `kh data scan --fix`，必要时由 KH CLI 执行一次 `kh data download`，补数后再次从本地库读取。
- 相同 `code/period/start/end` 的补数请求写入 `~/.cache/khquant/skill_data_manifest.json`，24 小时内不重复调用远端接口；需要重试时显式使用 `--force-supplement`。
- 每次导出保留 `*_metadata.json`，记录 `source=kh_local.duckdb`、KH 数据库路径、补数前后覆盖和未来行过滤状态。历史回溯必须强制 `date/trade_date <= as_of`。
- breadth、板块、事件和外盘等非 KH 数据仍可作为确认层，但必须单独记录来源、时间戳和缓存；不能把它们混入波浪硬规则输入。

## Required inputs

1. Fetch index daily data with `scripts/fetch_market_data.py`; it first reads KH local DuckDB and causally aggregates to weekly OHLCV. Do not check or call `TUSHARE_TOKEN` directly; missing data is supplemented only through KH CLI.
2. Fetch a reviewed market-leadership basket with `scripts/fetch_leadership_data.py`; it also reads KH local DuckDB first and records any KH supplementation. The basket must include market anchors, style leaders, and current narrative leaders; it is not a permanently fixed ticker list.
3. Maintain a reviewed event ledger. Start from `assets/event-ledger-template.csv` and validate it with `scripts/build_event_ledger.py`.
4. Generate the scenario report with `scripts/generate_weekly_report.py`.
5. When the conclusion depends on daily C1–C5, create a price-only daily chart and a segment ledger before viewing or applying Gann overlays. Preserve both extreme pivots and any expert/structural working pivots.
6. For every active time window, collect daily whole-market breadth (`up/down/traded`, advance ratio and equal-weight return), amount versus its 20-day baseline, and at least three relevant broad indices in long form. Use an official exchange calendar for formal future trading-bar dates.

Do not treat a news headline, a rumoured IPO, or an intraday move as a wave confirmation. Preserve `published_at` for every event so reports and tests do not use future knowledge.

## Workflow

### 1. Prepare data

Run the fetcher for at least five years, unless the index listed later. It stores daily and weekly CSV outputs plus query metadata. KH local DuckDB is the primary source; the KH supplementation path is incremental and cache-aware.

```bash
python3 scripts/fetch_market_data.py --index-code 000300.SH --start 20190101 --output-dir data/000300
```

For a wider review, first reuse cached/local KH exports for industry performance, market breadth, amount and peer broad-index synchronization when present. Only series unavailable in KH (for example selected macro/news fields) may use Tushare or other external sources; record provider and as-of timestamp. Treat these as confirming evidence, not as wave-count inputs with hard rules, and record missing inputs as an evidence gap.

Build the leadership basket from `assets/market-leader-watchlist-template.csv`, then collect its weekly state. Read `references/market-leadership.md` before classifying a company as a total leader.

```bash
python3 scripts/fetch_leadership_data.py \
  --watchlist market-leaders.csv --start 20250101 --output data/leader_state.csv
```

Use the candidate collector to search Tushare major news before manual verification. It never writes a final event score or treats a candidate as fact.

```bash
python3 scripts/fetch_event_candidates.py --start 20260615 --end 20260716 \
  --keywords "智谱,长鑫,IPO" --output data/event_candidates.csv
```

When `major_news` is unavailable, conduct browser research using the official-source workflow in `references/web-research.md`. Search is for discovery only: open the original regulator, exchange, or company page and record its URL and publication time in the ledger. Do not score a search-result snippet or a media paraphrase.

### 2. Build and verify the event ledger

Event sources are ranked: official policy/central-bank/regulator/exchange/company disclosure; then reputable media; then unverified market discussion. Only confirmed sources may materially change a scenario score.

Use the following classes: `policy`, `liquidity`, `macro`, `ipo`, `external_risk`, `earnings`, `market_structure`.

For IPOs, record lifecycle states exactly: `rumour`, `filing`, `accepted`, `registered`, `priced`, `listed`, `post_listing`. A rumour is an observation only. `registered`, `priced`, and `listed` can affect the near-term event score when their issuance size, timetable, and affected sector are known.

```bash
python3 scripts/build_event_ledger.py --input events.csv --output data/events_clean.csv
```

Read `references/event-ledger.md` for required evidence and the four IPO transmission channels.

### 3. Generate price/time scenarios

```bash
python3 scripts/generate_weekly_report.py \
  --weekly data/000300/000300.SH_weekly.csv \
  --events data/events_clean.csv \
  --leaders data/leader_state.csv \
  --parent-context reports/parent-count.md \
  --index-name 沪深300 \
  --output reports/hs300-weekly.md
```

The script identifies only *candidate* pivots. Apply Elliott hard constraints before presenting an impulse count:

- Wave 2 must not exceed the start of wave 1.
- Wave 3 must not be the shortest of waves 1, 3, and 5.
- In a standard impulse, wave 4 must not overlap wave 1 price territory.

If the evidence cannot support a compliant count, describe the structure as a trend/correction candidate instead of inventing a label.

For an active C3/C4/C5 dispute, do not stop at candidate pivots. Compare the internal three-versus-five-wave character, trading-day duration, point-per-day speed, overlap, candle ranges,成交额, MA5/10/20 and momentum expansion/divergence. Explain why the preferred segment behaves like a motive or corrective wave. Use Fibonacci and Gann only after this morphology review; they may refine targets or rank two compliant counts, not select a count by visual coincidence.

Always show the full parent count leg by leg: `1`–`5` must all appear in a single table or ledger, including the current and not-yet-started leg. For completed waves give start/end date, price, point change and duration; for an incomplete wave give its start, current endpoint/target condition, status and confirmation trigger; for an unstarted wave give `未启动` plus the condition that would establish it. Then show the local `A-B-C` with dates, prices and retracement where applicable. State specifically why the preferred count is valid, the confirmation trigger for its unfinished leg, and why a plausible alternative count is rejected or retained. Do not call a pullback “wave 4” unless the preceding 1–2–3 structure has been demonstrated.

Read `references/correction-patterns.md` before naming a correction. Distinguish a sharp zigzag, flat, triangle, and combination; if the subtype cannot be identified, call it an `A-B-C candidate` and state the unresolved condition. For A-share adjustments, never collapse “parent A-B-C” and “C-leg internal 1-2-3-4-5” into one level. When a candidate low may be either C3 or completed C5, produce both local ledgers and apply the C-wave constraints in `references/a-share-wave-counting.md`.

Price zones should be clusters of 23.6%, 38.2%, and 50% retracements, prior weekly pivots, and weekly moving-average areas. Report a core zone, an extended zone, and an invalidation close. Time windows derive from the last comparable correction and 0.618×/1×/1.618× weekly-duration relationships; give a range, never a date certainty.

For an A-share rebound-to-main-rise transition, report the 10-week simple moving average alongside EMA13/EMA34, turnover versus the 13-week median, breadth and reviewed leaders. A weekly close above a moving average is confirmation evidence, not proof that C5 or parent wave 4 has ended. Specify whether every time interval uses natural days, trading days or weeks.

**时间确认是必填项。** Build four clocks side by side: 5% major-pivot natural days; 5% major-pivot trading bars; 2%–3% local-pivot trading bars; and declared-wave 0.618×/1×/1.618× durations in both natural and trading time. Keep `pivot_date`, causal `confirm_date`, calendar quality and tolerance. The first three clocks share the price-pivot causal family; multiple offsets, tolerances or anchors increase `window_count`, not independent evidence. A wave-duration clock is not independent if its segment or anchor was selected only because it fits the target date.

For every projected turning point (C3/C4/C5 endpoint, second bottom, parent-wave transition, or breakout), give: (a) source and time unit; (b) center date or bar count; (c) early/late tolerance; (d) price/structure condition; (e) breadth and cross-index condition; and (f) delay/failure rule. Separate `极值候选`, `价格反转`, `宽度反转`, `指数确认`, `扩散/跨指数确认`, and `周线确认`; never call all of them the same turning date. On each update use `时间未到/价格先到`, `已到窗待价确认`, `极值命中/确认待定`, `窗口命中`, `时间到而价格未确认`, `延迟`, or `失效`. Do not move the anchor, unit or center after the window ends.

### 4. Interpret events without narrative overreach

The event score can strengthen or weaken the main forecast, but must not create a target or overturn price invalidation. Explain the transmission channel separately:

- Policy/liquidity: funding conditions and risk appetite.
- Macro: growth/inflation/rate-expectation change.
- Major IPO: capital supply, valuation anchor, industry expectation, and risk appetite.

For a major IPO such as an AI or memory company, explicitly separate a funding-diversion hypothesis from a strategic-valuation-anchor hypothesis. State the status and evidence; do not assert a listing date unless it is officially disclosed.

## Market-leadership confirmation

The index count is a hypothesis; total leaders are confirmation evidence. Report: the basket definition and review date; the share above weekly EMA13/EMA34; 4-week relative performance; and named leaders making/breaking prior pivots. Do not let one stock invalidate an index count.

- Leaders broadly above both averages and breaking prior highs weaken a bearish C-wave hypothesis and support the alternative rebound count.
- Leaders broadly below both averages and breaking prior lows strengthen a bearish C-wave hypothesis.
- Divergence—index rising while leaders fail, or index falling while leaders hold—weakens the main forecast and requires a clearly stated alternative path.

Never use “market total leader” as a synonym for the biggest company by market value. Use the selection and rotation protocol in `references/market-leadership.md`.

## Multi-degree count

Create and pass a reviewed Markdown parent-count note for every index report. The note must include waves 1–5, even where wave 4 or 5 is only `进行中` or `未启动`: list each leg's start/end date and price where known, duration, status, wave-2 retracement, wave-3 length relative to wave 1, wave-4 non-overlap level, and the condition that can establish or invalidate every unfinished leg. Read `references/multi-degree-counting.md`.

When a parent wave-4 floor exists, pass `--parent-retrace-low` and `--parent-hard-invalidation`. Do not publish a mechanical local C-wave extension below the parent hard-invalid level as a normal target.

## Output contract

The report is a **current-time judgement**, not a fixed “C-wave endpoint” template. At each data cut-off, determine the market state first, then present the most likely next branch.

Use `assets/report-template.md` and populate only the sections supported by current evidence:

1. **Main forecast:** one sentence naming the expected path, target point or zone, and time window; immediately append the time-confirmation status and the trigger that will confirm or invalidate the timing call.
2. **Current state:** a `父级1–5浪总表` followed by the local-wave position that explains the forecast. The table must distinguish completed facts from active projections. If the active dispute is C3/C4/C5 versus completed C, add a `局部C段1–5账本`; use `待证` for subwaves that cannot be resolved at the available data granularity. Add a `时间确认账本` with source family, causal family, anchor/confirm dates, natural/trading unit, center/window, calendar status, extreme date, price-confirm date, breadth/cross-index confirm date and failure rule. Report `window_count` separately from `independent_family_count`.
3. **Daily structure audit:** price-only primary/alternative ledgers; internal a-b-c or 1–5 character; speed, overlap, volume and momentum comparison; explicit uncertainty when minute order is unavailable. Add a `浪段证据—结论与切换预判断` for the active main/alternative count, with concrete evidence→judgement rows and observed versus conditional status. Show which evidence only establishes a candidate, changes the trend scenario, promotes a wave count, soft-downgrades it, or hard-invalidates it. Apply to all wave types, not only C; preserve the original cutoff and first confirmation time, and do not invent future subwaves to justify a transition.
4. **Price map:** target, validation level, and re-judgement level. A C-wave target appears only when C is the active projected branch. Separate wave-derived, Gann-derived and joint zones.
5. **Evidence and contradictions:** price/internal evidence, Gann spatial evidence where used, daily breadth, amount, peer broad-index synchronization, leadership, liquidity/macro, and verified policy/events; state whether breadth led the index and name evidence that conflicts with the main forecast.
6. **Re-judgement paths:** no more than two alternatives, each with exact conditions that replace the main forecast.
7. **Next observation:** the few data points or events that will decide the next update. For a proposed second bottom, include the time band, center date/bar count, early/late tolerance, current timing status, core/extended price zones, weekly reclaim level and hard invalidation before the window begins.

Do not force every report to contain `A-B-C` or a wave-4 label. Even if structure is mixed, state the single most likely path and the target area implied by that path; then specify what would make the next report adopt another path.

## Integrated judgement hierarchy

Use a hierarchy rather than an opaque additive score. A lower layer may change confidence but cannot overrule a higher-layer price invalidation.

1. **Parent hard structure:** multi-year 1–2–3–4–5 or A-B-C count; hard rules and invalidation levels.
2. **Daily morphology and rhythm:** internal three/five-wave character, overlap, duration, speed, candles,成交额 and momentum.
3. **Spatial cross-check:** Fibonacci, historical pivots and, when requested, Gann resonance. It refines zones and ranks compliant counts but cannot override layers 1–2 hard evidence.
4. **Price and market internals:** weekly EMA structure, pivot breaks, advance/decline breadth, equal-weight return, turnover versus its recent range, and synchronization or divergence among major broad indices.
5. **Market leadership:** market anchors, style leaders and narrative leaders; identify confirmation, deterioration, or divergence.
6. **Liquidity, macro and events:** distinguish levels from momentum and verified surprises from existing policy stance.

The final conclusion must contain: `main forecast`, `current state`, `why now`, `re-judgement trigger`, and `what to observe next`. Read `references/integrated-judgement.md` before issuing a directional call.

Do not hide behind confidence bands or generic disclaimers. State the main forecast plainly; use re-judgement triggers only to define when the model must adopt a new forecast.

## Validation

Use only information whose `published_at` is no later than the decision timestamp. In rolling historical tests evaluate:

- Whether the next 4/8/12-week extrema reached the core or extended zone.
- Whether the time window contained the relevant turning point, whether the center date/bar count was early or late, and whether price confirmation arrived inside the stated tolerance window.
- Extreme-date hit rate, first price-confirmation hit rate, breadth/cross-index confirmation hit rate and weekly-confirmation hit rate must be reported separately, alongside calendar coverage. Adding clocks or widening tolerance cannot be presented as improved skill without an out-of-sample excess over that coverage.
- Directional accuracy versus a simple weekly EMA trend baseline.
- Invalidation latency and frequency of scenario changes.

Do not claim predictive skill before an out-of-sample, rolling evaluation across more than one market regime.
