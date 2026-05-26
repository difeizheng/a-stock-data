#!/usr/bin/env python3
"""
A股投资报告生成器 - 批量生成投资研究报告

功能：
1. 读取 filtered_stocks.json 中的股票列表
2. 对每只股票获取行情/财务/分红/行业等数据
3. 对照50万杠杆策略进行评级
4. 生成格式化的 Markdown 报告

输出：reports/{股票简称}_{代码}_投资研究报告_{日期}.md
"""
import json
import os
import sys
import time
import traceback
import warnings
from datetime import datetime

import requests

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(PROJECT_DIR, "reports")
CHECKPOINT_FILE = os.path.join(PROJECT_DIR, ".generation_checkpoint.json")

os.makedirs(REPORTS_DIR, exist_ok=True)

RETRY_MAX = 3
RETRY_INTERVAL = 5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.qq.com/",
}

RED_LINE_INDUSTRIES = {"银行", "煤炭", "公用事业", "建筑", "钢铁", "电力", "交通",
                       "交通运输", "燃气", "石油", "航运", "高速公路"}
GROWTH_INDUSTRIES = {"半导体", "人工智能", "软件", "互联网", "电子", "通信",
                     "通信设备", "计算机", "信息技术", "自动化"}


# ===================== 工具函数 =====================

def retry_call(fn, *args, **kwargs):
    for attempt in range(1, RETRY_MAX + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt < RETRY_MAX:
                time.sleep(RETRY_INTERVAL)
            else:
                return None


def safe_float(val, default=0.0):
    try:
        v = float(val)
        return v if v == v else default  # NaN check
    except (ValueError, TypeError):
        return default


# ===================== 数据获取 =====================

def get_tencent_quote(code):
    prefix = "sh" if code.startswith(("6", "9")) else "sz"
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    resp = requests.get(url, timeout=5, headers=HEADERS)
    if resp.status_code != 200 or "~" not in resp.text:
        return None
    parts = resp.text.split("~")
    if len(parts) < 47:
        return None
    try:
        return {
            "name": parts[1] if len(parts) > 1 else "",
            "price": safe_float(parts[3]),
            "open": safe_float(parts[4]),
            "high": safe_float(parts[5]),
            "low": safe_float(parts[6]),
            "volume": safe_float(parts[7]),
            "amount": safe_float(parts[8]),
            "pe_ttm": safe_float(parts[39]),
            "pe_static": safe_float(parts[40]) if len(parts) > 40 else 0,
            "pb": safe_float(parts[46]),
            "market_cap": safe_float(parts[44]),
            "wave": safe_float(parts[32]),
            "amplitude": safe_float(parts[43]) if len(parts) > 43 else 0,
        }
    except (ValueError, IndexError):
        return None


def get_financial_summary(code):
    try:
        import akshare as ak
        df = ak.stock_financial_analysis_indicator(
            symbol=code, start_date="20240101", end_date="20261231"
        )
        if df is None or df.empty:
            return {}

        latest = df.iloc[-1]
        result = {}
        for col in df.columns:
            for key in ["每股收益", "每股净资产", "净资产收益率", "销售毛利率", "销售净利率"]:
                if key in str(col):
                    result[key] = safe_float(latest.get(col, 0))
        return result
    except Exception:
        return {}


def get_profit_data(code):
    try:
        import akshare as ak
        df = ak.stock_financial_abstract_ths(symbol=code, indicator="按年度")
        if df is None or df.empty:
            return []

        results = []
        for _, row in df.head(3).iterrows():
            entry = {}
            for col in df.columns:
                if "日期" in str(col) or "报告" in str(col):
                    entry["date"] = str(row.get(col, ""))
                elif "营业总收入" in str(col):
                    entry["revenue"] = str(row.get(col, "N/A"))
                elif "净利润" in str(col) and "扣" not in str(col):
                    entry["net_profit"] = str(row.get(col, "N/A"))
                elif "营业总成本" in str(col):
                    entry["total_cost"] = str(row.get(col, "N/A"))
            if entry:
                results.append(entry)
        return results
    except Exception:
        return []


def get_dividend_history(code):
    try:
        import akshare as ak
        df = ak.stock_dividend_detail(symbol=code)
        if df is None or df.empty:
            return []

        results = []
        for _, row in df.head(5).iterrows():
            entry = {"year": "", "amount": 0.0, "plan": ""}
            for col in df.columns:
                val = row.get(col, "")
                if "年度" in str(col) or "公告日" in str(col):
                    entry["year"] = str(val)[:4]
                elif "派息" in str(col) or "送转" in str(col):
                    entry["plan"] = str(val)
                    nums = [float(x) for x in str(val).replace("元", "").split()
                            if x.replace(".", "").replace("-", "").isdigit()]
                    if nums:
                        entry["amount"] = nums[0]
                elif "每股" in str(col) and "派" in str(col):
                    entry["amount"] = safe_float(val)
                    entry["plan"] = f"每10股派{safe_float(val) * 10:.2f}元"
            if entry["year"] or entry["amount"] > 0:
                results.append(entry)
        return results
    except Exception:
        return []


def get_company_info(code):
    try:
        import akshare as ak
        info = ak.stock_individual_info_em(symbol=code)
        if info is None or info.empty:
            return {}

        result = {}
        for _, row in info.iterrows():
            item = str(row.get("item", "")).strip()
            value = str(row.get("value", "")).strip()
            result[item] = value
        return result
    except Exception:
        return {}


def get_consensus_estimate(code):
    try:
        import akshare as ak
        df = ak.stock_em_forecast(symbol=code)
        if df is None or df.empty:
            return None

        result = {"years": [], "forward_pe": 0, "cagr": 0, "peg": 0}
        for _, row in df.head(3).iterrows():
            entry = {}
            for col in df.columns:
                if "年份" in str(col) or "年度" in str(col):
                    entry["year"] = str(row.get(col, ""))
                elif "机构" in str(col) or "预测" in str(col):
                    entry["count"] = safe_float(row.get(col, 0))
                elif "均值" in str(col) or "平均" in str(col):
                    entry["eps_mean"] = safe_float(row.get(col, 0))
                elif "最小" in str(col):
                    entry["eps_min"] = safe_float(row.get(col, 0))
                elif "最大" in str(col):
                    entry["eps_max"] = safe_float(row.get(col, 0))
            if entry:
                result["years"].append(entry)

        if result["years"] and len(result["years"]) >= 2:
            eps_start = result["years"][0].get("eps_mean", 0)
            eps_end = result["years"][-1].get("eps_mean", 0)
            n = len(result["years"])
            if eps_start > 0 and eps_end > 0:
                result["cagr"] = ((eps_end / eps_start) ** (1 / n) - 1) * 100

        return result
    except Exception:
        return None


def get_dividend_yield_from_history(dividend_history, price):
    if not dividend_history or price <= 0:
        return 0.0
    last = dividend_history[0]
    amount = last.get("amount", 0)
    return round((amount / price) * 100, 2) if amount > 0 else 0.0


# ===================== 策略评价 =====================

def evaluate_strategy(code, quote, financial, dividend_yield, category):
    price = quote.get("price", 0)
    pe = quote.get("pe_ttm", 0)
    pb = quote.get("pb", 0)
    mc = quote.get("market_cap", 0)
    roe = financial.get("净资产收益率", 0)

    # 防守评级
    d_score = 1
    if dividend_yield >= 5:
        d_score = 5
    elif dividend_yield >= 4:
        d_score = 4
    elif dividend_yield >= 3:
        d_score = 3
    elif dividend_yield >= 2:
        d_score = 2
    if 0 < pe < 10:
        d_score = min(5, d_score + 1)
    elif pe > 15:
        d_score = max(1, d_score - 1)
    d_stars = "⭐" * d_score + "☆" * (5 - d_score)
    d_desc = f"股息率{dividend_yield:.2f}%，PE{pe:.1f}x，PB{pb:.2f}x，ROE{roe:.1f}%"

    # 进攻评级
    o_score = 1
    if mc > 500:
        o_score = 5
    elif mc > 200:
        o_score = 4
    elif mc > 100:
        o_score = 3
    elif mc > 50:
        o_score = 2
    if pe > 50:
        o_score = max(1, o_score - 2)
    elif pe > 30:
        o_score = max(1, o_score - 1)
    o_stars = "⭐" * o_score + "☆" * (5 - o_score)
    o_desc = f"市值{mc:.0f}亿，PE{pe:.1f}x"

    # 操作建议
    if category == "dividend":
        if d_score >= 4 and pe > 0 and pe < 15:
            suggestion = f"✅ **买入建议**：股息率{dividend_yield:.2f}%覆盖3%资金成本，PE{pe:.1f}x估值合理，建议分批建仓，止损设{price * 0.7:.2f}元。"
            rating = "强烈推荐"
            weight = "5-8%"
        elif d_score >= 3:
            suggestion = f"🟡 **持有关注**：股息率{dividend_yield:.2f}%，PE{pe:.1f}x，建议观望等待更好买点。"
            rating = "谨慎推荐"
            weight = "3-5%"
        else:
            suggestion = f"❌ **观望**：股息率{dividend_yield:.2f}%不足以覆盖资金成本，建议寻找更优标的。"
            rating = "不推荐"
            weight = "0%"
    elif category == "growth":
        if o_score >= 4 and 0 < pe < 40:
            suggestion = f"✅ **买入建议**：市值{mc:.0f}亿弹性充足，PE{pe:.1f}x，建议分3-4批建仓，止损设{price * 0.8:.2f}元。"
            rating = "推荐"
            weight = "2-3%"
        elif o_score >= 3:
            suggestion = f"🟡 **持有关注**：有一定弹性，PE{pe:.1f}x，注意估值回调风险，轻仓试探。"
            rating = "谨慎推荐"
            weight = "1-2%"
        else:
            suggestion = f"❌ **观望**：不符合进攻条件，PE{pe:.1f}x偏高或市值偏小。"
            rating = "不推荐"
            weight = "0%"
    else:
        if d_score >= 3:
            suggestion = f"🟡 综合评分{d_score + o_score}/10，可作为底仓备选。"
            rating = "备选"
            weight = "2-3%"
        else:
            suggestion = f"❌ 综合评分{d_score + o_score}/10，不符合当前策略。"
            rating = "不推荐"
            weight = "0%"

    return {
        "defense_stars": d_stars, "defense_desc": d_desc,
        "offense_stars": o_stars, "offense_desc": o_desc,
        "suggestion": suggestion, "rating": rating, "weight": weight,
        "stop_loss_price": round(price * 0.8, 2),
        "defense_score": d_score, "offense_score": o_score,
    }


# ===================== 报告生成 =====================

def generate_report(code, name, category, info_cache=None):
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{name}_{code}_投资研究报告_{today}.md"
    filepath = os.path.join(REPORTS_DIR, filename)

    if os.path.exists(filepath):
        print(f"  [SKIP] {name}_{code} 已存在")
        return False

    # 获取行情
    quote = retry_call(get_tencent_quote, code)
    if not quote or quote["price"] <= 0:
        print(f"  [ERROR] {code} 无法获取行情")
        return False

    # 获取补充数据
    company = retry_call(get_company_info, code) or {}
    financial = retry_call(get_financial_summary, code) or {}
    dividends = retry_call(get_dividend_history, code) or []

    price = quote["price"]
    pe = quote["pe_ttm"]
    pb = quote["pb"]
    mc = quote["market_cap"]
    wave = quote["wave"]

    div_yield = get_dividend_yield_from_history(dividends, price)

    industry = company.get("行业", "未知")
    list_time = company.get("上市时间", "数据暂缺")
    total_shares = company.get("总股本", "数据暂缺")
    company_desc = company.get("公司概况", "")

    eps = financial.get("每股收益", 0)
    bvps = financial.get("每股净资产", 0)
    roe = financial.get("净资产收益率", 0)
    gross_margin = financial.get("销售毛利率", 0)
    net_margin = financial.get("销售净利率", 0)

    # 一致预期
    consensus = retry_call(get_consensus_estimate, code)

    # 策略评价
    strategy = evaluate_strategy(code, quote, financial, div_yield, category)

    category_label = "红利底仓（防守端）" if category == "dividend" else "AI/半导体进攻"

    # 构建报告
    report = f"""# {name}（{code}）投资研究报告

> 报告生成日期：{today}
> 筛选类别：{category_label}
> 数据来源：腾讯财经、akshare、东财、同花顺、百度股市通
> 本报告基于实时数据调用与公开资料整理，仅供参考，不构成投资建议。

---

## 一、公司概况

**{name}**（{code}）

| 项目 | 内容 |
|------|------|
| 股票代码 | {code} |
| 行业 | {industry} |
| 上市时间 | {list_time} |
| 总市值 | {mc:.2f} 亿元 |
| 总股本 | {total_shares} |

"""

    if company_desc and len(company_desc) > 20:
        report += f"""### 公司简介

{company_desc[:500]}

---

"""

    report += f"""## 二、实时行情

| 指标 | 值 |
|------|-----|
| 现价 | {price:.2f} 元 |
| 涨跌幅 | {wave:.2f}% |
| PE(TTM) | {pe:.2f}x |
| PB | {pb:.2f}x |
| 总市值 | {mc:.2f} 亿元 |

---

## 三、财务分析

| 指标 | 值 | 评价 |
|------|-----|------|
| 每股收益(EPS) | {eps:.4f} 元 | {'盈利' if eps > 0 else '亏损'} |
| 每股净资产 | {bvps:.2f} 元 | — |
| 净资产收益率(ROE) | {roe:.2f}% | {'优秀' if roe > 15 else '良好' if roe > 8 else '一般'} |
| 销售毛利率 | {gross_margin:.2f}% | {'高' if gross_margin > 30 else '中' if gross_margin > 15 else '低'} |
| 销售净利率 | {net_margin:.2f}% | {'高' if net_margin > 10 else '中' if net_margin > 5 else '低'} |

---

## 四、估值分析

| 指标 | 值 | 参考 |
|------|-----|------|
| 市盈率(PE) | {pe:.2f}x | 银行股合理区间 5-10x，科技股 20-50x |
| 市净率(PB) | {pb:.2f}x | 银行股合理区间 0.5-1x，成长股 3-6x |
| 股息率 | {div_yield:.2f}% | 高股息股通常 > 4% |

"""

    if consensus and consensus.get("years"):
        report += "### 机构一致预期\n\n"
        report += "| 年度 | 预测机构数 | EPS均值 | EPS最小 | EPS最大 |\n"
        report += "|------|-----------|---------|---------|--------|\n"
        for y in consensus["years"]:
            report += f"| {y.get('year', 'N/A')} | {int(y.get('count', 0))} | {y.get('eps_mean', 0):.4f} | {y.get('eps_min', 0):.4f} | {y.get('eps_max', 0):.4f} |\n"
        if consensus.get("cagr", 0) > 0:
            report += f"\n**EPS增速(CAGR)**: {consensus['cagr']:.1f}%\n"

    report += f"""
**估值判断：**
{"⚠️ 估值偏高，注意风险" if pe > 30 else "✅ 估值合理" if pe > 0 else "⚠️ 数据暂缺"}

---

## 五、分红历史

| 年度 | 每10股派息 | 分红方案 |
|------|-----------|---------|
"""
    if dividends:
        for d in dividends:
            yr = d.get("year", "N/A")
            amt = d.get("amount", 0)
            plan = d.get("plan", "—")
            if amt > 0:
                report += f"| {yr} | {amt * 10:.2f} 元 | {plan} |\n"
            elif plan:
                report += f"| {yr} | 数据暂缺 | {plan} |\n"
    else:
        report += "| 数据暂缺 | — | — |\n"

    report += f"""
---

## 六、策略评价（50万杠杆策略对照）

### 策略定位

- **仓位类型**: {"防守端（红利底仓）" if category == "dividend" else "进攻端（AI/半导体）"}
- **综合评级**: {strategy['rating']}
- **建议仓位权重**: {strategy['weight']}

### 防守评级：{strategy['defense_stars']}
{strategy['defense_desc']}

**是否符合红利底仓条件：**
- 股息率 {div_yield:.2f}% {'✅ > 4%' if div_yield > 4 else '❌ < 4%'}
- PE {pe:.2f}x {'✅ < 20' if pe < 20 else '❌ ≥ 20'}
- 行业：{industry} {'✅ 符合' if industry in RED_LINE_INDUSTRIES else '❌ 不符合'}

### 进攻评级：{strategy['offense_stars']}
{strategy['offense_desc']}

**是否符合AI/半导体进攻条件：**
- 行业：{industry} {'✅ 符合' if industry in GROWTH_INDUSTRIES else '❌ 不符合'}
- 市值：{mc:.0f}亿 {'✅ > 50亿' if mc > 50 else '❌ < 50亿'}

### 综合建议
{strategy['suggestion']}

---

## 七、风险提示

1. 本报告基于公开数据自动生成，不构成投资建议
2. 历史分红不代表未来分红承诺
3. 杠杆投资放大收益同时也放大亏损
4. 单只个股建议不超过总仓位20%
5. 总账户净值跌破42万必须减仓，跌破38万必须清仓还钱
6. 当前PE {pe:.1f}x，默认止损位：-20% → {strategy['stop_loss_price']:.2f} 元

---

*报告生成于 {today}*
*生成工具: A股投资报告批量生成系统*
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)
    return True


# ===================== 检查点 =====================

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_processed": None, "count": 0, "errors": []}


def save_checkpoint(data):
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ===================== 主程序 =====================

def main():
    print("=" * 60)
    print("A股投资报告生成器 v2.0")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"报告目录: {REPORTS_DIR}")
    print("=" * 60)

    filter_file = os.path.join(PROJECT_DIR, "filtered_stocks.json")
    if not os.path.exists(filter_file):
        print(f"[ERROR] 筛选结果不存在: {filter_file}")
        print("请先运行: python stock_screener.py")
        return

    with open(filter_file, "r", encoding="utf-8") as f:
        filtered = json.load(f)

    dividend_list = filtered.get("红利候选", [])
    growth_list = filtered.get("进攻候选", [])
    all_stocks = [(s, "dividend") for s in dividend_list] + [(s, "growth") for s in growth_list]

    print(f"加载筛选结果：红利 {len(dividend_list)} + 进攻 {len(growth_list)} = {len(all_stocks)} 只")

    checkpoint = load_checkpoint()
    start_idx = checkpoint.get("count", 0)
    print(f"从检查点恢复：已处理 {start_idx} 只")

    success = start_idx
    errors_list = checkpoint.get("errors", [])

    for i, (stock, cat) in enumerate(all_stocks):
        if i < start_idx:
            continue

        code = stock.get("code", "")
        name = stock.get("name", "")

        print(f"\n[{i + 1}/{len(all_stocks)}] {code} {name} ({cat})")

        try:
            result = generate_report(code, name, cat)
            if result:
                success += 1
                print(f"  [DONE] 成功")
            else:
                print(f"  [SKIP] 跳过")
        except Exception as e:
            print(f"  [ERROR] {e}")
            errors_list.append({"code": code, "name": name, "error": str(e)})

        if (i + 1) % 10 == 0:
            checkpoint["last_processed"] = code
            checkpoint["count"] = i + 1
            checkpoint["errors"] = errors_list
            save_checkpoint(checkpoint)
            print(f"  [CHECKPOINT] {success} 只成功")

        time.sleep(1)

    checkpoint["last_processed"] = "COMPLETE"
    checkpoint["count"] = len(all_stocks)
    checkpoint["errors"] = errors_list
    save_checkpoint(checkpoint)

    print(f"\n{'=' * 60}")
    print(f"生成完成！成功 {success} 只，错误 {len(errors_list)} 条")
    print(f"报告目录: {REPORTS_DIR}")
    if errors_list:
        print(f"错误列表:")
        for e in errors_list[:5]:
            print(f"  - {e.get('code', '?')} {e.get('name', '?')}: {e.get('error', '?')}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
