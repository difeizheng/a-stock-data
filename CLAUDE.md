# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Structure

Three independent subsystems coexist in one repo:

1. **`SKILL.md`** — the public deliverable. A self-contained skill file (structured Markdown + embedded Python) packaging A-Share data tooling for AI coding assistants. 6-layer architecture, 21 endpoints, 8 data sources. No traditional source code.

2. **Root Python scripts** — a batch research-report generator that consumes the skill's data layer to produce investment reports aligned to a 50万 leverage strategy (`投资策略_50万杠杆资金.md`).

3. **`small_goal/`** — the personal investment workspace: strategy docs, research reports (`.md`), fetched data cache (`small_goal/data/*.json`), and a leverage monitoring subsystem (Excel + Python + DingTalk).

## Architecture

### Data Layer (SKILL.md)

```
行情层    mootdx (TCP 7709) + 腾讯财经 (HTTP)     K线/盘口/PE/PB/市值/换手率
研报层    东财 + akshare + iwencai                 研报列表/PDF/一致预期/NL搜索
信号层    同花顺 + 百度股市通 + akshare + 东财DC    强势股/题材/北向/概念/资金/龙虎榜/解禁/行业
新闻层    akshare × 3                              个股新闻/财联社快讯/全球资讯
基础数据  mootdx finance/F10                       37字段季报/9类公司资料
公告层    巨潮 cninfo + mootdx                     沪深北全量公告
```

Data source priority (by IP-ban risk, lowest first): mootdx → Tencent → akshare → iwencai → Eastmoney PDF → THS Hot → THS Northbound → Baidu.

### Batch Report Pipeline (root scripts)

```
stock_screener.py      → filtered_stocks.json         全市场筛选 (红利/进攻/可转债候选)
batch_screen.py        → small_goal/data/screen_cache.json  124股二次筛选 (checkpoint resume)
fetch_stock_data.py    → small_goal/data/{name}_{code}_data.json  单票全量数据
report_generator.py    → reports/{name}_{code}_投资研究报告_{date}.md  对照策略评级
report_to小白版.py     → 小白友好版 (通俗术语解读)
batch_runner.py        → orchestrator: scan → generate
batch_reports.py       → batch生成详细报告 (session checkpoint)
```

State/checkpoint files (do NOT delete mid-run): `progress_checkpoint.json`, `.generation_checkpoint.json`, `.screen_checkpoint.json`, `small_goal/data/{report_progress,screen_cache,filtered_for_detailed_report}.json`.

### Monitoring Subsystem (`small_goal/`)

```
create_excel_v4_enhanced.py  → 投资监控系统_v4.xlsx (11 sheets)
stock_monitor_v4.py          → mootdx股价(股/ETF/转债, TCP免代理) + PB/ROE + 动态股息率 + 净值曲线 + HTML周报
strategy_checks.py           → 策略级检查: 止损止盈/行业集中度/再平衡/本金警戒/逆回购择时/可转债强赎
dingtalk_notify.py           → 钉钉webhook推送 (HMAC-SHA256加签) + 每日心跳日报
daily_check.py               → 每日入口: 跑监控 → 推心跳日报(安全也发) + 红线预警
```

Config: `dingtalk_config.json` (webhook + secret — gitignored secrets). Red lines: 净值<42万减仓, <38万清仓, 进攻亏损>2万减半, 息差<3000加仓. 数据兜底: 取价失败>30%跳过红线; 现价偏离买入价5倍按成本计(mootdx代码映射错误防护, 如588000).

## Commands

```bash
# Dependencies
pip install -r requirements.txt          # akshare, requests, pandas
pip install mootdx stockstats            # for SKILL.md embedded code + monitoring

# Batch report pipeline (root)
python batch_runner.py                   # full: screen + generate
python batch_runner.py --scan-only       # 只筛选
python batch_runner.py --skip-scan       # 跳过筛选直接生成
python batch_reports.py --status         # 查看进度
python batch_reports.py --reset          # 清空进度重来

# Monitoring (small_goal)
cd small_goal && python create_excel_v4_enhanced.py   # 生成/重建Excel
cd small_goal && python stock_monitor_v4.py           # 手动跑监控
cd small_goal && python daily_check.py                # 每日检查+钉钉推送
cd small_goal && python dingtalk_notify.py            # 测试钉钉推送

# Tests
pytest                                   # all
pytest tests/test_screener.py            # single file
pytest tests/test_screener.py::test_name # single test

# Docker
docker-compose up stock-report           # 批量报告
docker-compose --profile scan up stock-scan
```

## Important Conventions

- **Stock code:** 6-digit numeric, normalized internally. `get_prefix()`: 6/9 → `sh`, 8 → `bj`, else → `sz`. Accepts `SH688017`, `688017.SH`, etc.
- **mootdx API:** class is `Quotes` (NOT `QuotesApi`), via `Quotes.factory(market='std')`. Returns DataFrames — guard with `df is not None and not df.empty`, never bare `if df`.
- **Tencent finance:** field 43 = amplitude%, field 46 = PB. Many online tutorials swap these.
- **Baidu PAE:** `ResultCode` returns int `0` or string `"0"` — compare with `str()`.
- **iwencai:** only source needing API key. X-Claw headers mandatory (SkillHub 2.0).
- **Console encoding:** Windows GBK console cannot print emoji — use `[OK]`/`[FAIL]`/`[WARN]` ASCII tags, or set `PYTHONIOENCODING=utf-8`.
- **Excel write lock:** `openpyxl.save()` fails with `PermissionError` if the `.xlsx` is open in Excel. Close it first; temp lock files are `~$*.xlsx`.
- **Overseas servers:** mootdx needs China IP for TCP stability. ETF/可转债 prices via akshare need network (fails behind proxy — stock_monitor_v4 falls back to manual).

## Known Issues / Workarounds

- akshare timeout → `time.sleep(1~3)` + retry (Eastmoney anti-scraping)
- iwencai 401 → verify API key + X-Claw headers
- THS hot `reason` empty → post-market data not updated, retry after 15:30
- Non-trading days → dragon tiger/northbound return empty
- Northbound history → Eastmoney cutoff 2024-08; V2.1 self-caches to `~/.tradingagents/cache/northbound_daily.csv`

## User Context

User is a finance/economics beginner (理科背景, 金融零基础). Explain professional terms in plain language. Preference: detailed, accurate, beginner-readable reports — NOT building systems unless explicitly asked.
