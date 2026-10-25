# Wayne's Skill

Personal Codex skills maintained as versioned assets.

## Skills

- `akshare`: Chinese financial data access using AkShare library. Fetch real-time and historical data for A-shares, Hong Kong stocks, US stocks, futures, funds, and macroeconomic indicators. Use when user requests Chinese market data, stock prices, market analysis, or financial information from Chinese exchanges. Supports stock quotes, historical data, futures market data, fund information, macroeconomic indicators, and real-time market updates.
- `chassis-growth-agentic-research`: 独立主控底盘型成长股正式研究；用私有 modules、多角色/subagent、中间产物、进攻型市场重定价主线、行业经济性与蛋糕分配、竞争/客户验证链、中期进攻 QA、终审事实 QA 和投资人写作，完整覆盖旧业务底盘、第二成长曲线、TAM/SAM/SOM、平台复用、承接动作、利润桥、跟踪体系、证据边界、三表/FCF 建模接力输入和估值接力输入。Use when 用户需要深度分析 A 股制造业、AI算力、数据中心、新能源、机器人、先进制造、半导体设备/材料等底盘型成长公司，判断旧业务托底、行业经济性拐点、新业务抬天花板、公司份额提升、平台能力复用、竞争客户验证、利润中枢上移、预期差和证伪路径，并产出正式深度报告而非摘要。
- `core-stock-sector-impact`: Analyze whether a caller-provided set of core stocks is leading, confirming, or exhausting risk in a sector/index/ETF by classifying each core stock into short-window up/sideways/down states, measuring breadth diffusion, and backtesting target forward returns, downside amplitude, and drawdowns. Use when the user asks to see whether core leaders affect or warn about a板块/指数/ETF, asks for 核心标的影响板块, 龙头扩散, 横盘/下跌数量, 板块风险温度计, or wants a reusable Tushare-based analysis where the core stock basket is supplied at call time.
- `dcf-model`: Real DCF (Discounted Cash Flow) model creation for equity valuation. Retrieves financial data from SEC filings and analyst reports, builds comprehensive cash flow projections with proper WACC calculations, performs sensitivity analysis, and outputs professional Excel models with executive summaries. Use when users need to value a company using DCF methodology, request intrinsic value analysis, or ask for detailed financial modeling with growth projections and terminal value calculations.
- `dcf-valuation-workflow`: DCF-only valuation workflow orchestrator for equity research. Use when the user asks for DCF估值, DCF闭环, intrinsic value, Formal DCF, Scenario DCF, Reverse DCF, or wants a one-pass workflow that first prepares financial-modeling DCF-ready inputs and then runs dcf-model outputs. This skill coordinates financial-modeling to dcf-model for DCF deliverables only.
- `doc`: Professional document creation, editing, and analysis for Office formats (docx, pdf, pptx, xlsx). Use when working with Word documents, PDFs, PowerPoint presentations, or Excel spreadsheets.
- `equity-catalyst-tracker`: 个股持续研究、领先变量识别与催化剂因果推演；在已有产业链、成长股、供应链平台或估值研究基础上，先建立标的专属 Driver Map 和利润传导链，再跟踪客户、订单、原材料、价格、技术路线、产能、同行、财报、预期修正和定价状态等增量证据，判断哪些领先变量会迫使市场未来修改利润锚、估值锚或证伪逻辑；按 Quick/Standard/Deep 分层使用 subagent，默认 Standard 只保留领先变量、财报传导和反方审查，Deep 才完整多角色取证。Use when 用户要求持续研究股票、跟踪爆点、审核新闻/公告/财报/产业变量是否强化逻辑、寻找未被市场充分定价的催化、判断原材料涨价是否收益传导、判断高位是否仍有新势能、识别高潮退潮或证伪，尤其适用于 A股/港股/美股成长股、AI算力、数据中心、新能源、机器人、半导体、先进制造供应链公司。
- `feishu-codex-research-bridge`: Build, migrate, inspect, and operate the local Feishu-to-Codex research bridge: Feishu bot messages create queued research tasks, a serialized worker runs Codex with research skills, final reports are converted to PDF or Drive links, and results are sent back to a Feishu group. Use when the user mentions 飞书/Codex 桥梁, 飞书投研队列, lark-cli event consume, /投研, queue worker, report delivery to Feishu, or migrating this bridge to another repository.
- `finance-research-xhs`: 将金融研报、股票研究、行业分析、财报解读、投资复盘和估值框架改写成小红书长文本笔记。适用于非种草、非带货、非标题党风格，强调信息密度、证据链、事实/推断/假设分层、风险和证伪点保留。Use when the user asks for 金融研报小红书、投研小红书长文、股票分析笔记、行业研究改写、财报解读小红书、非种草风格XHS长文本。
- `financial-modeling`: Build integrated financial models with 3-statement projections, DCF-ready UFCF bridges, working-capital schedules, and debt/interest linkages. Use for income statement, balance sheet, cash flow, and DCF input preparation. Scope is three-statement and DCF-ready modeling; PEG-ready packages are handled by growth-stock-valuation.
- `find-skills`: Helps users discover and install agent skills when they ask questions like "how do I do X", "find a skill for X", "is there a skill that can...", or express interest in extending capabilities. This skill should be used when the user is looking for functionality that might exist as an installable skill.
- `frontend-design`: Create distinctive, production-grade frontend interfaces with high design quality. Use this skill when the user asks to build web components, pages, artifacts, posters, or applications (examples include websites, landing pages, dashboards, React components, HTML/CSS layouts, or when styling/beautifying any web UI). Generates creative, polished code and UI design that avoids generic AI aesthetics.
- `gann-space-resonance`: 对A股指数执行无前视江恩空间与多时钟共振研究，以K线/日线结构优先，分离极值日和价格/宽度/跨指数确认日，并让江恩参与候选排序和目标校验，融合波浪父级1–5账本，输出圆周图、重要关键时间点（单一日期，不报时间区间）与未来4–12周情景。Use when 用户要求江恩理论、江恩空间/时间共振、变盘日、支撑压力、圆周图、Square-of-9、当前浪、C3/C4/C5或多技术线联合研判；不用于脱离价格结构把几何线直接当交易信号。
- `gann-window-direction`: Produce point-in-time A-share index direction reports by combining verified Gann time/space, wave structure, structural price levels, external markets, breadth, funding and leadership. Use for premarket/intraday/backfill window decisions, level interaction, scenario construction, gating and post-close attribution. Do not use Gann dates as standalone buy/sell signals.
- `growth-stock-valuation`: 成长股 PEG / Forward PE 交叉估值；用于动态 PEG、复合 PEG、Forward PE、估值增速裁量、PEG系数选档、正常/乐观目标市值、催化剂裁量估值、目标价、当前市值隐含预期和估值年份切换。必须纳入最近实际年度到预测期的完整增长路径，由模型区分客观增速与可用于估值的持续增速，并解释PEG为何取0.9、1.0、1.1等档位；防止高增速与高PEG双重计价。默认排除 bottom-up/算小账/分业务利润桥。
- `hithink-finance`: 当用户或 Agent 需要通过同花顺金融数据服务获取、查询、同步、分析或导出 A 股行情、财报、估值、指数、板块、公募基金、特色数据或本地 DuckDB 数据，或需要选择、安装、配置、诊断 REST API、MCP、hithink-finance CLI、Python SDK/marketdb 时使用。
- `index-stock-t-study`: 基于指数支撑压力事件与5分钟个股数据，研究江恩共振、斐波那契、黄金分割和均线压力对AI权重股日内回撤与收盘修复的解释力，并在无前视、同钟点对照和样本审计下评估做T路径；不直接生成未经验证的买卖信号。
- `industry-chain-agentic-research`: 强约束 Agentic 行业产业链深度研究；真实 subagent 优先，分角色证据收集、模块手册、子环节拆分、数据表沉淀、章节草稿、反查反证、反方审查、报告汇总、主笔重构和完整行业深度报告，用于 A 股/港股/美股行业、赛道、产业链或细分环节正式研究，防止摘要化、只说好话、终稿过薄、模块拼接和普通投资人读不懂。
- `khquant`: 当用户提到"回测"、"看海量化"、"kh命令"、"跑策略"、"下载股票数据"、"查看回测结果"、"双均线"、"MACD"、"RSI策略"、"KDJ"、"布林带"、"miniQMT"、"BaoStock"、"Tushare"、"沪深300"、"A股"、".kh配置文件"、"策略开发"、"K线"、"DuckDB"、"量化交易"、"khHandlebar"、"khGet"、"khPrice"、"khIndex"、"khHistory"、"khDuckDB"、"khMA"、"generate_signal"、"khAddExtraFields"、"MyTT"、"技术指标"、"交易信号"时使用。本 skill 是看海量化回测平台 CLI (kh) 的自然语言入口，支持首次配置、数据管理、策略开发、回测执行、结果分析和故障排查。
- `l2-etf-strategy`: Operate and reproduce the user's L2 ETF strategy package. Use when the user asks about L2 ETF, TRD_K20_ADV50M_NoKCB, quarterly ETF rebalancing, ETF picks/trades, live ETF holdings, NAV logs, or reproducing the ETF backtest/experiment evidence from the 2026-06-10 package.
- `local-bank-research`: 研究城商行、农商行等地方商业银行股的利润桥、资产质量、区域beta、债券投资、分红与预期差。
- `markdown-report-pdf`: Convert one or more Markdown reports into a polished HTML/CSS research-report PDF. Use when the user asks for Markdown -> HTML/CSS -> PDF, md to pdf, markdown report PDF, 投研报告 PDF, 研报排版导出, or wants a reusable report export workflow with Chinese typography, tables, print CSS, and PDF verification.
- `pipecat-deploy`: Deploy an agent to Pipecat Cloud
- `pipecat-init`: Scaffold a new Pipecat project with guided setup
- `pipecat-talk`: Start a voice conversation using the Pipecat MCP server
- `research-report-publication-editor`: 投研报告出版审校与对外口径清理；用于正式 PDF/Markdown/HTML 报告导出前后，扫描并清除导出痕迹、skill/subagent/任务名/工具名、终稿自述、提示词残留、内部审稿语言和过度教学化表达；可只列问题，也可在不改变事实和结论的前提下润色为正式研报正文。
- `simon-tail-risk-daily`: 每日检查 Simon 六因子尾部风险择时模型，增量更新 A 股、指数、行业、中证全指历史权重、纳斯达克和费城半导体数据，输出最新完整交易日的 0–6 分风险评分、风险链、六因子证据和次一交易日开盘目标仓位。用于用户说“看看今天风险”“每日风险评分”“今天几分”“明天仓位”“六因子是否触发”“外围冲击”“尾部风险日报”或要求只看每天情况时；固定组合为中际旭创、东山精密、生益科技、行云科技、亨通光电。
- `skill-github-sync`: Sync local Codex skills from ~/.codex/skills into a GitHub skills repository, update README, commit, and optionally push.
- `supply-chain-agentic-research`: 独立主控供应链平台型成长股正式研究；用私有 modules、多角色/subagent、中间产物、进攻型市场交易变量、技术路线到价值量、原材料价格链、竞争/客户认证链、产能升级、订单经营验证、利润天花板、跟踪体系、两轮 QA 和投资人写作，完整覆盖 AI 算力、数据中心、新能源、机器人、先进封装、半导体设备/材料等供应链公司研究。Use when 用户需要深度分析供应链公司，判断身份切换、订单放量、技术路线升级、利润中枢上移、天花板抬升、市场预期差和证伪路径，并产出正式深度报告而非摘要。
- `tushare`: 面向中文自然语言的 Tushare 数据研究技能。用于把“看看这只股票最近怎么样”“帮我查财报趋势”“最近哪个板块最强”“北向资金在买什么”“给我导出一份行情数据”这类请求，转成可执行的数据获取、清洗、对比、筛选、导出与简要分析流程。适用于 A 股、指数、ETF/基金、财务、估值、资金流、公告新闻、板块概念与宏观数据等研究场景。
- `weekly-index-wave-scenarios`: Produce auditable 4–12 week A-share index scenarios using multi-degree Elliott structure, price-first daily morphology, multi-clock timing, separate extreme/confirmation dates, rhythm/volume, optional Gann spatial resonance, breadth, cross-index confirmation, leadership, and verified events. Use for weekly index outlooks, evidence-driven launch/continuation/completion and degree transitions across all waves, C3/C4/C5 versus completed-C disputes, second-bottom paths, or distilling an expert's wave-counting method without losing independent audit.
- `wencai-query`: Query Tonghuashun Wencai with the `pywencai` Python package for Chinese-market screening, ranking, and tabular result retrieval. Use when Codex needs to execute or explain a natural-language Wencai request such as A-share stock screening, concept or industry ranking, valuation or financial-factor filtering, limit-up or turnover queries, export Wencai results, or summarize the returned table. Trigger when the user mentions "问财", "同花顺问财", or `pywencai`, or asks to turn a Chinese stock screener prompt into executable code or structured output.
## 估值链路

正式成长股估值拆成 PEG 与 DCF 两条独立闭环，避免一个 skill 同时承担研究、建模、定价和汇总：

```text
研究主控
  -> growth-stock-valuation
  -> dcf-valuation-workflow
       -> financial-modeling
       -> dcf-model
```

- `growth-stock-valuation`：只做 PEG / 动态 PE 成长股定价，输出目标市值区间、情景、年份切换和证伪点。
- `dcf-valuation-workflow`：DCF 主控闭环，先调用 `financial-modeling` 生成 DCF-ready / UFCF / assumption ledger，再调用 `dcf-model` 完成 Formal、Scenario 或 Reverse DCF。
- `financial-modeling`：把研究主控输出的 `dcf_financial_model_handoff` 转成三表、FCF、UFCF 和 DCF-ready 数据包，不输出目标价或最终估值结论。
- `dcf-model`：只基于 DCF-ready 现金流输入独立生成 DCF Excel、summary 和 validation。

PEG 与 DCF 如需对照，只在报告层并列引用两个独立产物。

## 如何调用技能

在 Codex 里可以直接写技能名，再说明研究对象、输出要求，以及是否启动 subagent。也可以不写技能名，只用自然语言描述任务目标；Codex 会根据意图匹配合适的技能。显式写技能名更精准，自然语言调用更顺手。

调用方式：

注意：仓库里的 `modules/`、`references/`、`agents/` 是某些主控 skill 的内部材料，不是独立 skill，也不需要单独点名调用。调用时只点名真实存在的 skill；如果不确定，就用自然语言描述目标，让 Codex 自动匹配。

1. 点名技能调用：

研究与跟踪：

- `equity-catalyst-tracker 调研东山精密，启动 subagent`
- `industry-chain-agentic-research 研究AI服务器产业链，启动 subagent，拆分上游材料、PCB、连接器、电源、液冷和整机环节`
- `chassis-growth-agentic-research 研究东山精密，重点看市场重定价、旧业务底盘、第二成长曲线、竞争客户验证和估值接力输入`
- `supply-chain-agentic-research 调研工业富联，启动 subagent，输出正式深度报告`
- `local-bank-research 研究江苏银行，重点拆利润桥、资产质量、区域beta、分红和估值预期差`

估值与建模：

- `growth-stock-valuation 基于东山精密前置深研和估值接力输入，做目标市值、PEG、一致预期差和赔率判断`
- `dcf-valuation-workflow 基于东山精密_dcf_financial_model_handoff.md 先生成 DCF-ready/UFCF，再完成 DCF 模型、估值摘要和 validation`
- `financial-modeling 基于东山精密_dcf_financial_model_handoff.md 生成 DCF-ready 和 UFCF 数据包`
- `dcf-model 基于东山精密_dcf_ready_package.md 生成 DCF 模型、估值摘要和 validation`

数据：

- `akshare 获取东山精密近一年行情、估值和财务数据，并做简要趋势分析`
- `tushare 导出东山精密近三年财务指标、估值和日行情，整理成表格`
- `wencai-query 查询最近10日涨停次数最多的A股，导出表格`

输出、发布和工具：

- `finance-research-xhs 把东山精密研究报告改写成小红书长文本笔记`
- `markdown-report-pdf 把东山精密研究报告转成正式 PDF`
- `research-report-publication-editor 审校东山精密终稿，清理内部痕迹和工具痕迹`
- `frontend-design 做一个AI算力供应链研究仪表盘，包含公司对比、催化事件和风险提示`
- `doc 把东山精密研究报告整理成docx，保留标题层级、表格和风险提示`
- `find-skills 找一个适合做A股公告跟踪和财报解析的skill`
- `skill-github-sync 重新同步本地skills到GitHub仓库，并更新README`
- `feishu-codex-research-bridge 查看飞书投研队列，确认当前运行任务和结果发送状态`

2. 不点名技能的自然语言调用：

研究与跟踪：

- `调研东山精密，重点看4月9日前后是否有订单、客户、财报或市场行为催化；启动 subagent，输出证据链和后续跟踪清单`
- `研究AI服务器产业链，启动 subagent，拆分上游材料、PCB、连接器、电源、液冷和整机环节，输出完整产业链深度报告`
- `研究东山精密，启动 subagent，重点看市场重定价、旧业务底盘、第二成长曲线、平台复用能力、竞争客户验证、利润桥和估值接力输入`
- `调研工业富联，启动 subagent，重点看AI服务器订单、客户结构、供应链地位、利润释放和估值接力输入`
- `研究江苏银行，重点拆利润桥、资产质量、区域beta、债券投资、分红和估值预期差`
- `持续跟踪东山精密的新订单、客户验证、财报和市场行为，判断逻辑是否强化或证伪`

估值与建模：

- `growth-stock-valuation 基于东山精密前置深研和估值接力输入，做目标市值、PEG、一致预期差和赔率判断`
- `基于东山精密正式研究输出，先做三表和现金流建模，再分别跑 PEG 和 DCF，最后聚合成统一估值摘要`
- `用官方 dcf-model 对东山精密 DCF-ready 数据包做现金流折现、敏感性分析和模型校验`
- `把 PEG 和 DCF 两个模型结果合并成一份估值 scorecard，列出关键假设、差异和证伪点`

数据：

- `获取东山精密近一年行情、估值和财务数据，并做简要趋势分析`
- `导出东山精密近三年财务指标、估值和日行情，整理成表格`
- `查询最近10日涨停次数最多的A股，导出表格`

输出、发布和工具：

- `把东山精密研究报告改写成小红书长文本笔记，保留证据链、风险和假设分层`
- `把东山精密研究报告转成带目录、页眉页脚和中文排版的 PDF`
- `审校这份投研终稿，删除工具痕迹、内部审稿语言和不适合对外发布的措辞`
- `做一个AI算力供应链研究仪表盘，包含公司对比、催化事件、估值和风险提示`
- `把东山精密研究报告整理成docx，保留标题层级、表格和风险提示`
- `帮我找一个适合做A股公告跟踪和财报解析的skill`
- `重新同步我的本地skills仓库，并更新GitHub仓库README`
- `看看飞书投研队列现在有多少任务，正在跑哪个任务`

## Local install

Install or update all skills from this repo into Codex:

```bash
mkdir -p ~/.codex/skills
cp -R skills/* ~/.codex/skills/
```

Restart Codex after installing or updating skills.
