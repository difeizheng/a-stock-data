"""Batch generate detailed research reports for filtered stocks with session-persistent checkpoints.

State file: small_goal/data/report_progress.json
Each stock: {code, name, status: 'pending'|'fetching'|'done'|'failed', report_path}

Usage:
  python batch_reports.py           # start from first pending
  python batch_reports.py --resume  # same (auto-resume from state)
  python batch_reports.py --reset   # clear progress, start over
  python batch_reports.py --status  # show current progress only
"""
import json
import os
import sys
import time
import re
import requests

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'small_goal', 'data', 'report_progress.json')
FILTERED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'small_goal', 'data', 'filtered_for_detailed_report.json')
SCREEN_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'small_goal', 'data', 'screen_cache.json')
REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'small_goal')


def get_prefix(code):
    code = re.sub(r'[^0-9]', '', code)
    if code.startswith(('6', '9')):
        return 'sh' + code
    elif code.startswith('8'):
        return 'bj' + code
    else:
        return 'sz' + code


def fetch_tencent(code):
    prefixed = get_prefix(code)
    try:
        url = f"https://qt.gtimg.cn/q={prefixed}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and prefixed in r.text:
            fields = r.text.split('~')
            if len(fields) > 50:
                return {
                    'price': float(fields[3]) if fields[3] else 0,
                    'prev_close': float(fields[4]) if fields[4] else 0,
                    'high': float(fields[33]) if fields[33] else 0,
                    'low': float(fields[34]) if fields[34] else 0,
                    'turnover_rate': float(fields[38]) if fields[38] else 0,
                    'pe_ttm': float(fields[39]) if fields[39] else 999,
                    'pb': float(fields[46]) if fields[46] else 0,
                    'total_market_cap': float(fields[45]) if fields[45] else 0,
                    'limit_up': float(fields[47]) if fields[47] else 0,
                    'limit_down': float(fields[48]) if fields[48] else 0,
                }
    except Exception:
        pass
    return None


def fetch_kline(code):
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market='std', bestip=True, timeout=10)
        bars = client.bars(symbol=code, frequency=9, offset=80)
        if bars is not None and len(bars) > 0:
            last60 = bars.tail(60)
            return {
                'high_60d': float(last60['high'].max()),
                'low_60d': float(last60['low'].min()),
                'ma_5': float(bars.tail(5)['close'].mean()),
                'ma_10': float(bars.tail(10)['close'].mean()),
                'ma_20': float(bars.tail(20)['close'].mean()),
                'ma_60': float(last60['close'].mean()),
                'latest_5': bars.tail(5).to_dict('records'),
            }
    except Exception:
        pass
    return None


def fetch_financial(code):
    try:
        import akshare as ak
        fin = ak.stock_financial_abstract_ths(symbol=code)
        if fin is not None and len(fin) > 0:
            annual = fin[fin['报告日期'].str.contains('-12-31', na=False)]
            rows = []
            for _, row in annual.tail(5).iterrows():
                rows.append({
                    'date': row.get('报告日期', ''),
                    'revenue': row.get('营业总收入', ''),
                    'revenue_yoy': row.get('营业总收入同比增长率', ''),
                    'net_profit': row.get('净利润', ''),
                    'net_profit_yoy': row.get('净利润同比增长率', ''),
                    'eps': row.get('基本每股收益', ''),
                    'roe': row.get('净资产收益率', ''),
                    'nav_per_share': row.get('每股净资产', ''),
                    'debt_ratio': row.get('资产负债率', ''),
                })
            return rows
    except Exception:
        pass
    return None


def fetch_news(code):
    try:
        import akshare as ak
        news = ak.stock_news_em(symbol=code)
        if news is not None and len(news) > 0:
            items = []
            for _, row in news.head(5).iterrows():
                items.append({
                    'title': row.get('新闻标题', ''),
                    'time': row.get('发布时间', ''),
                    'source': row.get('文章来源', ''),
                    'content': row.get('新闻内容', '')[:200],
                })
            return items
    except Exception:
        pass
    return None


def fetch_reports(code):
    try:
        import akshare as ak
        reports = ak.stock_research_report_em(symbol=code)
        if reports is not None and len(reports) > 0:
            items = []
            for _, row in reports.head(5).iterrows():
                items.append({
                    'title': row.get('报告名称', ''),
                    'rating': row.get('东财评级', ''),
                    'org': row.get('机构', ''),
                    'date': row.get('日期', ''),
                    'eps_2026': row.get('2026-盈利预测-收益', ''),
                    'pe_2026': row.get('2026-盈利预测-市盈率', ''),
                })
            return items
    except Exception:
        pass
    return None


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_filtered_stocks():
    with open(FILTERED_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_cache():
    if os.path.exists(SCREEN_CACHE):
        with open(SCREEN_CACHE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def show_status(state):
    done = sum(1 for s in state if s['status'] == 'done')
    failed = sum(1 for s in state if s['status'] == 'failed')
    pending = sum(1 for s in state if s['status'] == 'pending')
    total = len(state)
    print(f"Progress: {done}/{total} done, {failed} failed, {pending} pending")
    print()
    for s in state:
        status_icon = {'done': '[OK]', 'failed': '[FAIL]', 'pending': '[..]', 'fetching': '[..]'}.get(s['status'], '[??]')
        print(f"  {status_icon} {s['name']:10s} {s['code']:6s} | {', '.join(s.get('tags', []))}")


def generate_report(stock, tencent, kline, financials, news, reports):
    """Generate a detailed research report markdown."""
    name = stock['name']
    code = stock['code']
    tags = stock.get('tags', [])
    date = time.strftime('%Y-%m-%d')

    # Extract key data
    price = tencent.get('price', 0) if tencent else 0
    pe = tencent.get('pe_ttm', 0) if tencent else 0
    pb = tencent.get('pb', 0) if tencent else 0
    cap = tencent.get('total_market_cap', 0) if tencent else 0
    cap_yi = cap / 10000 if cap else 0
    turnover = tencent.get('turnover_rate', 0) if tencent else 0
    dividend_yield = 30 / pe if pe and pe > 0 else 0

    high_60 = kline.get('high_60d', 0) if kline else 0
    low_60 = kline.get('low_60d', 0) if kline else 0
    ma5 = kline.get('ma_5', 0) if kline else 0
    ma10 = kline.get('ma_10', 0) if kline else 0
    ma20 = kline.get('ma_20', 0) if kline else 0
    ma60 = kline.get('ma_60', 0) if kline else 0

    pos_high = (1 - price / high_60) * 100 if high_60 and price else 0
    pos_low = (price / low_60 - 1) * 100 if low_60 and price else 0

    # Price assessment
    if pos_high < 5:
        price_verdict = "接近60日高点，短期偏贵"
    elif pos_high < 15:
        price_verdict = "60日区间中上部"
    elif pos_high < 30:
        price_verdict = "60日区间中部"
    else:
        price_verdict = "60日区间偏底部，相对便宜"

    # PE assessment
    if pe < 5:
        pe_verdict = "极低，可能价值陷阱或周期性低谷"
    elif pe < 10:
        pe_verdict = "便宜"
    elif pe < 15:
        pe_verdict = "合理"
    elif pe < 30:
        pe_verdict = "偏贵"
    else:
        pe_verdict = "很贵，高成长预期定价"

    # PB assessment
    if pb < 0.5:
        pb_verdict = "深度打折"
    elif pb < 0.7:
        pb_verdict = "打折"
    elif pb < 1.5:
        pb_verdict = "合理"
    elif pb < 3:
        pb_verdict = "偏贵"
    else:
        pb_verdict = "很贵"

    # Fair value estimation
    if pe > 0 and pe < 50:
        pe_low = round(pe * 0.8, 1)
        pe_high = round(pe * 1.2, 1)
        pe_range = f"PE法: {pe_low}-{pe_high}x → 合理价区间"
    else:
        pe_range = "PE法: PE过高或亏损，不适用"

    if pb > 0 and pb < 10:
        pb_range = f"PB法: 估值{'便宜' if pb < 1 else '合理' if pb < 2 else '偏贵'}"
    else:
        pb_range = "PB法: 不适用"

    # Strategy fit
    is_dividend = '红利候选' in tags or '稳定高息' in tags
    is_tech = '科技成长' in tags or '科技高估值' in tags
    is_value = '价值股' in tags

    if is_dividend:
        strategy = "红利底仓"
        strategy_comment = f"股息率{dividend_yield:.1f}%，覆盖3%借款利率，息差套利{dividend_yield - 3:.1f}%"
    elif is_tech and pe < 50:
        strategy = "科技成长/进攻"
        strategy_comment = "AI/科技赛道，高弹性高波动，需分批建仓+严格止损"
    elif is_value:
        strategy = "价值股"
        strategy_comment = "低PE+低PB，估值便宜，需确认基本面没有恶化"
    else:
        strategy = "待观察"
        strategy_comment = "不符合策略明确分类"

    # Financial summary
    fin_rows = ""
    if financials:
        for f in financials:
            date_str = str(f.get('date', ''))[:10]
            rev = f.get('revenue', '')
            rev_yoy = f.get('revenue_yoy', '')
            profit = f.get('net_profit', '')
            profit_yoy = f.get('net_profit_yoy', '')
            eps = f.get('eps', '')
            roe = f.get('roe', '')
            if rev and profit:
                fin_rows += f"| {date_str} | {rev} | {rev_yoy} | {profit} | {profit_yoy} | {eps} | {roe} |\n"

    # News summary
    news_items = ""
    if news:
        for n in news:
            news_items += f"- **{n.get('time', '')}** ({n.get('source', '')}): {n.get('title', '')}\n"

    # Report ratings
    report_items = ""
    if reports:
        for r in reports:
            rating = r.get('rating', '')
            org = r.get('org', '')
            eps_f = r.get('eps_2026', '')
            pe_f = r.get('pe_2026', '')
            if rating and org:
                report_items += f"- {org}: {rating} | 2026 EPS预测={eps_f} | 对应PE={pe_f}\n"

    # Build report
    report = f"""# {name}（{code}）投资调研报告

> 调研日期：{date}
> 现价：{price} 元
> 总市值：约 {cap_yi:.0f} 亿元
> 策略分类：{strategy}
> 标签：{', '.join(tags)}

---

## 一、目前的股价高不高？

### 现价位置

| 参照 | 价格 | 现价位置 |
|------|------|---------|
| 60日最高 | {high_60} 元 | 低 {pos_high:.1f}% |
| 60日最低 | {low_60} 元 | 高 {pos_low:.1f}% |
| 5日均线 | {ma5} 元 | {'高' if price > ma5 else '低'} {abs(price/ma5-1)*100:.1f}% |
| 10日均线 | {ma10} 元 | {'高' if price > ma10 else '低'} {abs(price/ma10-1)*100:.1f}% |
| 20日均线 | {ma20} 元 | {'高' if price > ma20 else '低'} {abs(price/ma20-1)*100:.1f}% |
| 60日均线 | {ma60} 元 | {'高' if price > ma60 else '低'} {abs(price/ma60-1)*100:.1f}% |

**{price_verdict}。**

### 估值

| 指标 | 值 | 评价 |
|------|----|------|
| PE(TTM) | {pe:.2f}x | {pe_verdict} |
| PB | {pb:.2f}x | {pb_verdict} |
| 换手率 | {turnover:.2f}% | {'活跃' if turnover > 3 else '正常' if turnover > 1 else '冷清'} |
| 预估股息率 | {dividend_yield:.1f}% | {'达标(>=4%)' if dividend_yield >= 4 else '偏低'} |

---

## 二、合理价格是多少？

| 方法 | 结论 |
|------|------|
| PE法 | {pe_range} |
| PB法 | {pb_range} |

**需要结合行业均值、机构预期进一步判断。**

---

## 三、历年财务数据

| 年度 | 营收 | 营收同比 | 净利润 | 净利润同比 | EPS | ROE |
|------|------|---------|--------|----------|-----|-----|
{fin_rows if fin_rows else "*暂无数据*"}

---

## 四、近期新闻

{news_items if news_items else "*暂无新闻*"}

---

## 五、机构研报

{report_items if report_items else "*暂无研报覆盖*"}

---

## 六、策略匹配度

**分类：{strategy}**
{strategy_comment}

| 维度 | 评价 |
|------|------|
| 股息收益 | {"★★★★★" if dividend_yield >= 5 else "★★★★☆" if dividend_yield >= 4 else "★★★☆☆" if dividend_yield >= 3 else "★★☆☆☆"} |
| 估值合理 | {"★★★★★" if pe < 10 and pb < 1 else "★★★★☆" if pe < 15 else "★★★☆☆" if pe < 30 else "★★☆☆☆"} |
| 安全性 | {"★★★★★" if '银行' in name or '高速' in name else "★★★★☆" if '稳定高息' in tags else "★★★☆☆"} |

---

*本报告由 a-stock-data SKILL 自动生成，数据来源：腾讯财经/mootdx/akshare/东财研报。*
*不构成投资建议，使用前请自行核实。*
"""
    return report


def main():
    mode = '--reset' in sys.argv
    status_only = '--status' in sys.argv

    filtered = load_filtered_stocks()

    if mode:
        state = [{'code': s['code'], 'name': s['name'], 'status': 'pending', 'tags': s.get('tags', []), 'report_path': ''} for s in filtered]
        save_state(state)
        print(f"State reset. {len(state)} stocks set to pending.")
        return

    state = load_state()
    if state is None:
        state = [{'code': s['code'], 'name': s['name'], 'status': 'pending', 'tags': s.get('tags', []), 'report_path': ''} for s in filtered]
        save_state(state)

    if status_only:
        show_status(state)
        return

    cache = load_cache()
    pending = [s for s in state if s['status'] == 'pending']

    if not pending:
        print("All stocks done. Use --reset to start over.")
        return

    print(f"Starting: {len(pending)} pending stocks. Progress saved after each one.\n")

    for stock in pending:
        code = stock['code']
        name = stock['name']
        print(f"\n=== [{state.index(stock)+1}/{len(state)}] {name} ({code}) ===")

        # Mark fetching
        stock['status'] = 'fetching'
        save_state(state)

        # 1. Tencent data (use cache first)
        tencent = cache.get(code)
        if not tencent:
            tencent = fetch_tencent(code)
            time.sleep(0.3)
        if not tencent:
            print(f"  [FAIL] Tencent data failed")
            stock['status'] = 'failed'
            save_state(state)
            continue

        # 2. K-line
        print(f"  Fetching K-line...")
        kline = fetch_kline(code)
        time.sleep(1)

        # 3. Financials
        print(f"  Fetching financials...")
        financials = fetch_financial(code)
        time.sleep(2)

        # 4. News
        print(f"  Fetching news...")
        news = fetch_news(code)
        time.sleep(2)

        # 5. Reports
        print(f"  Fetching research reports...")
        reports = fetch_reports(code)
        time.sleep(2)

        # Generate report
        print(f"  Generating report...")
        report_md = generate_report(stock, tencent, kline, financials, news, reports)

        # Save report
        report_path = os.path.join(REPORT_DIR, f"{name}_{code}_调研报告_{time.strftime('%Y-%m-%d')}.md")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_md)

        stock['status'] = 'done'
        stock['report_path'] = os.path.basename(report_path)
        save_state(state)

        pe = tencent.get('pe_ttm', 0)
        pb = tencent.get('pb', 0)
        print(f"  [OK] Report saved: {os.path.basename(report_path)} | PE={pe:.1f}x PB={pb:.2f}x")

    # Summary
    done = sum(1 for s in state if s['status'] == 'done')
    failed = sum(1 for s in state if s['status'] == 'failed')
    pending_count = sum(1 for s in state if s['status'] == 'pending')
    print(f"\n{'=' * 60}")
    print(f"Batch complete: {done} done, {failed} failed, {pending_count} remaining")
    print(f"Resume: python batch_reports.py --resume")
    print(f"Status: python batch_reports.py --status")


if __name__ == '__main__':
    main()
