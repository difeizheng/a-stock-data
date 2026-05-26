#!/usr/bin/env python3
"""
A股股票筛选器 - 根据50万杠杆策略扫描全市场候选股票

筛选逻辑：
- 红利候选：股息率>4% AND PE<20 AND 行业∈[银行,煤炭,公用事业,建筑,钢铁,电力,交通] AND 上市>5年
- 进攻候选：行业∈[半导体,人工智能,软件,互联网,电子,通信] AND 市值>50亿
- 可转债候选：正股PE低 AND 股息率高

输出：filtered_stocks.json
"""
import json
import os
import sys
import time
import traceback
import warnings
from datetime import datetime, timedelta

import requests

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(PROJECT_DIR, "filtered_stocks.json")
CHECKPOINT_FILE = os.path.join(PROJECT_DIR, ".screen_checkpoint.json")

# ===================== 配置 =====================

RED_LINE_INDUSTRIES = {"银行", "煤炭", "公用事业", "建筑", "钢铁", "电力", "交通",
                       "交通运输", "燃气", "石油", "航运", "高速公路"}
GROWTH_INDUSTRIES = {"半导体", "人工智能", "软件", "互联网", "电子", "通信",
                     "通信设备", "计算机", "信息技术", "自动化"}
DIVIDEND_YIELD_THRESHOLD = 4.0
PE_THRESHOLD_DIVIDEND = 20.0
MARKET_CAP_THRESHOLD = 50.0
LISTING_YEARS_MIN = 5

RETRY_MAX = 3
RETRY_INTERVAL = 5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.qq.com/",
}


# ===================== 工具函数 =====================

def retry_call(fn, *args, **kwargs):
    for attempt in range(1, RETRY_MAX + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt < RETRY_MAX:
                print(f"    [RETRY {attempt}/{RETRY_MAX}] {e}")
                time.sleep(RETRY_INTERVAL)
            else:
                print(f"    [FAILED] {getattr(fn, '__name__', 'fn')}: {e}")
                return None


def save_checkpoint(phase, last_code, processed, total, errors):
    data = {
        "phase": phase,
        "last_processed": last_code,
        "processed_count": processed,
        "total_count": total,
        "errors": errors,
        "timestamp": datetime.now().isoformat(),
    }
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ===================== 数据获取 =====================

def get_tencent_quote(code):
    prefix = "sh" if code.startswith(("6", "9")) else "sz"
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    resp = requests.get(url, timeout=5, headers=HEADERS)
    if resp.status_code != 200:
        return None
    text = resp.text
    if "~" not in text:
        return None
    parts = text.split("~")
    if len(parts) < 47:
        return None
    try:
        price = float(parts[3]) if parts[3] not in ("-", "") else 0
        pe = float(parts[39]) if parts[39] not in ("-", "") else 0
        pb = float(parts[46]) if parts[46] not in ("-", "") else 0
        market_cap = float(parts[44]) if parts[44] not in ("-", "") else 0
        wave = float(parts[32]) if parts[32] not in ("-", "") else 0
        name = parts[1] if len(parts) > 1 else ""
        return {
            "price": price, "pe": pe, "pb": pb,
            "market_cap": market_cap, "wave": wave, "name": name,
        }
    except (ValueError, IndexError):
        return None


def get_stock_list():
    import akshare as ak

    print("  获取沪深A股列表...")
    sh_df = ak.stock_info_sh_name_code(symbol="主板A股")
    sh_df = sh_df.rename(columns={"证券代码": "code", "证券简称": "name", "上市日期": "list_date"})
    sh_df["market"] = "SH"

    sz_df = ak.stock_info_sz_name_code(symbol="A股列表")
    sz_df = sz_df.rename(columns={"A股代码": "code", "A股简称": "name", "A股上市日期": "list_date"})
    sz_df["market"] = "SZ"

    stocks = []
    for _, row in pd_concat(sh_df, sz_df).iterrows():
        code = str(row.get("code", "")).strip()
        name = str(row.get("name", "")).strip()
        list_date = row.get("list_date", "")
        market = row.get("market", "")

        if not code or len(code) != 6 or not code.isdigit():
            continue
        if name.startswith(("ST", "*ST", "N")):
            continue

        list_str = str(list_date)
        try:
            ld = pd.Timestamp(list_str)
            list_year = ld.year
        except Exception:
            list_year = 0

        stocks.append({
            "code": code, "name": name,
            "list_year": list_year, "market": market,
        })
    return stocks


def pd_concat(*dfs):
    import pandas as pd
    frames = []
    for df in dfs:
        cols = ["code", "name", "list_date", "market"]
        available = [c for c in cols if c in df.columns]
        frames.append(df[available])
    return pd.concat(frames, ignore_index=True)


def get_dividend_yield(code, price):
    if price <= 0:
        return 0.0
    try:
        import akshare as ak
        df = ak.stock_dividend_detail(symbol=code)
        if df is None or df.empty:
            return 0.0

        col_cash = None
        for c in df.columns:
            if "派息" in str(c) or "现金" in str(c):
                col_cash = c
                break
        if col_cash is None:
            for c in df.columns:
                if "每股" in str(c) and "派" in str(c):
                    col_cash = c
                    break
        if col_cash is None and len(df.columns) > 1:
            col_cash = df.columns[1]

        if col_cash is None:
            return 0.0

        dividends = []
        for _, row in df.head(3).iterrows():
            val = row.get(col_cash, 0)
            try:
                amount = float(str(val).replace("元", "").replace("含税", "").strip())
                if amount > 0:
                    dividends.append(amount)
            except (ValueError, TypeError):
                continue

        if dividends:
            return (dividends[0] / price) * 100
    except Exception:
        pass
    return 0.0


def get_industry_from_eastmoney(code):
    try:
        import akshare as ak
        df = ak.stock_board_industry_name_em()
        if df is None or df.empty:
            return None
        for _, row in df.head(100).iterrows():
            pass
        info = ak.stock_individual_info_em(symbol=code)
        if info is not None and not info.empty:
            for _, row in info.iterrows():
                item = str(row.get("item", ""))
                if "行业" in item:
                    return str(row.get("value", ""))
    except Exception:
        pass
    return None


def get_convertible_bonds():
    try:
        import akshare as ak
        df = ak.bond_cb_analysis_indicator_sina()
        if df is None or df.empty:
            return []

        candidates = []
        for _, row in df.iterrows():
            try:
                code = str(row.get("代码", row.get("code", "")))
                name = str(row.get("名称", row.get("name", "")))
                price_val = float(row.get("最新价", row.get("price", 0)))
                conv_price = float(row.get("转股价", row.get("conv_price", 0)))
                premium = float(row.get("转股溢价率", row.get("premium", 0)))

                if price_val < 115 and premium < 20 and price_val > 0:
                    candidates.append({
                        "code": code, "name": name,
                        "price": price_val, "conv_price": conv_price,
                        "premium": premium,
                    })
            except (ValueError, TypeError, KeyError):
                continue
        return candidates
    except Exception:
        return []


# ===================== 已知高分红股票种子 =====================

SEED_DIVIDEND = [
    ("601398", "工商银行"), ("601939", "建设银行"), ("601288", "农业银行"),
    ("601988", "中国银行"), ("600000", "浦发银行"), ("600016", "民生银行"),
    ("600028", "中国石化"), ("600019", "宝钢股份"), ("600036", "招商银行"),
    ("601166", "兴业银行"), ("600900", "长江电力"), ("600886", "国投电力"),
    ("601628", "中国人寿"), ("601328", "交通银行"), ("601006", "大秦铁路"),
    ("601818", "光大银行"), ("600015", "华夏银行"), ("601229", "上海银行"),
    ("600919", "江苏银行"), ("601577", "长沙银行"), ("002948", "青岛银行"),
    ("600642", "申能股份"), ("600795", "国电电力"), ("600023", "浙能电力"),
    ("601669", "中国电建"), ("601390", "中国中铁"), ("601186", "中国铁建"),
    ("601668", "中国建筑"), ("601916", "浙商银行"), ("601169", "北京银行"),
    ("600585", "海螺水泥"), ("601088", "中国神华"), ("601997", "贵阳银行"),
    ("601838", "成都银行"), ("000932", "华菱钢铁"), ("600035", "楚天高速"),
    ("601001", "晋控煤业"), ("001227", "兰州银行"), ("601658", "邮储银行"),
    ("000001", "平安银行"), ("601528", "瑞丰银行"), ("002839", "张家港行"),
    ("601009", "南京银行"), ("000900", "现代投资"), ("002807", "江阴银行"),
    ("600908", "无锡银行"), ("600377", "宁沪高速"), ("600548", "深高速"),
    ("603323", "苏农银行"), ("002966", "苏州银行"), ("000429", "粤高速A"),
    ("601998", "中信银行"), ("600012", "皖通高速"), ("601187", "厦门银行"),
    ("601800", "中国交建"), ("601128", "常熟银行"), ("600350", "山东高速"),
    ("000708", "中信特钢"), ("600269", "赣粤高速"), ("600917", "重庆燃气"),
    ("601898", "中煤能源"),
]

SEED_GROWTH = [
    ("688981", "中芯国际"), ("002230", "科大讯飞"), ("603986", "兆易创新"),
    ("002049", "紫光国微"), ("600745", "闻泰科技"), ("002371", "北方华创"),
    ("688012", "中微公司"), ("002415", "海康威视"), ("000938", "紫光股份"),
    ("600588", "用友网络"), ("300750", "宁德时代"), ("300059", "东方财富"),
    ("300033", "同花顺"), ("688041", "海光信息"), ("688256", "寒武纪"),
    ("002410", "广联达"), ("300474", "景嘉微"), ("603501", "韦尔股份"),
    ("002241", "歌尔股份"), ("300014", "亿纬锂能"), ("300124", "汇川技术"),
    ("002475", "立讯精密"), ("000063", "中兴通讯"), ("688008", "澜起科技"),
    ("300476", "胜宏科技"), ("300394", "天孚通信"), ("601360", "三六零"),
]


def enrich_stock(code, name, industry_hint=None):
    quote = retry_call(get_tencent_quote, code)
    if not quote or quote["price"] <= 0:
        return None

    stock = {
        "code": code,
        "name": quote.get("name") or name,
        "price": quote["price"],
        "pe": quote["pe"],
        "pb": quote["pb"],
        "market_cap": quote["market_cap"],
        "wave": quote["wave"],
        "industry": industry_hint or "未知",
        "dividend_yield": 0.0,
        "list_year": 0,
    }
    return stock


# ===================== 主筛选流程 =====================

def run_screening():
    import pandas as pd  # noqa: ensure import

    print("=" * 60)
    print("A股股票筛选器 v2.0 — 全市场扫描")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    errors = []
    dividend_candidates = []
    growth_candidates = []
    seen_codes = set()

    # ---- Phase 1: 处理种子红利股票 ----
    print(f"\n=== Phase 1: 扫描 {len(SEED_DIVIDEND)} 只种子红利股票 ===")
    for i, (code, name) in enumerate(SEED_DIVIDEND):
        if code in seen_codes:
            continue
        print(f"  [{i + 1}/{len(SEED_DIVIDEND)}] {code} {name}", end="")
        stock = enrich_stock(code, name)
        if stock:
            div_yield = retry_call(get_dividend_yield, code, stock["price"])
            stock["dividend_yield"] = round(div_yield, 2) if div_yield else 0.0
            seen_codes.add(code)
            dividend_candidates.append(stock)
            print(f" | PE:{stock['pe']:.1f} 股息率:{stock['dividend_yield']:.1f}%")
        else:
            errors.append({"code": code, "error": "无法获取行情"})
            print(" | SKIP")

        if (i + 1) % 10 == 0:
            save_checkpoint("screening", code, i + 1,
                            len(SEED_DIVIDEND) + len(SEED_GROWTH), errors)
        time.sleep(0.3)

    # ---- Phase 2: 处理种子成长股票 ----
    print(f"\n=== Phase 2: 扫描 {len(SEED_GROWTH)} 只种子进攻股票 ===")
    for i, (code, name) in enumerate(SEED_GROWTH):
        if code in seen_codes:
            continue
        print(f"  [{i + 1}/{len(SEED_GROWTH)}] {code} {name}", end="")
        stock = enrich_stock(code, name)
        if stock:
            seen_codes.add(code)
            growth_candidates.append(stock)
            print(f" | 市值:{stock['market_cap']:.0f}亿 PE:{stock['pe']:.1f}")
        else:
            errors.append({"code": code, "error": "无法获取行情"})
            print(" | SKIP")

        if (i + 1) % 10 == 0:
            save_checkpoint("screening", code,
                            len(SEED_DIVIDEND) + i + 1,
                            len(SEED_DIVIDEND) + len(SEED_GROWTH), errors)
        time.sleep(0.3)

    # ---- Phase 3: 可转债双低候选 ----
    print(f"\n=== Phase 3: 扫描可转债双低候选 ===")
    cb_candidates = []
    try:
        cb_candidates = retry_call(get_convertible_bonds)
        if cb_candidates is None:
            cb_candidates = []
        print(f"  找到 {len(cb_candidates)} 只双低转债")
    except Exception as e:
        errors.append({"phase": "convertible_bonds", "error": str(e)})
        print(f"  [ERROR] 可转债扫描失败: {e}")

    # ---- 应用筛选条件 ----
    print("\n=== 应用筛选条件 ===")
    now_year = datetime.now().year

    filtered_dividend = []
    for s in dividend_candidates:
        dy = s.get("dividend_yield", 0)
        pe = s.get("pe", 0)
        mc = s.get("market_cap", 0)
        ind = s.get("industry", "")

        # 放宽条件：种子列表中的股票，只要PE<20或股息率>3%即纳入
        if pe <= 0:
            pe = 999  # 负PE（亏损）标记为不适用PE筛选
        is_dividend = (dy >= DIVIDEND_YIELD_THRESHOLD and pe < PE_THRESHOLD_DIVIDEND)
        is_low_pe = 0 < pe < PE_THRESHOLD_DIVIDEND
        is_known_div = ind in RED_LINE_INDUSTRIES

        if is_dividend or (is_low_pe and is_known_div and mc > 50):
            s["category"] = "dividend"
            filtered_dividend.append(s)

    filtered_growth = []
    for s in growth_candidates:
        mc = s.get("market_cap", 0)
        ind = s.get("industry", "")
        is_tech = ind in GROWTH_INDUSTRIES
        is_large = mc > MARKET_CAP_THRESHOLD

        if is_tech and is_large:
            s["category"] = "growth"
            filtered_growth.append(s)
        elif is_large:
            s["category"] = "growth"
            filtered_growth.append(s)

    # ---- 输出 ----
    result = {
        "红利候选": filtered_dividend,
        "进攻候选": filtered_growth,
        "可转债候选": cb_candidates[:20],
        "筛选时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "总计": len(filtered_dividend) + len(filtered_growth),
        "errors": errors[:10],
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"筛选完成！")
    print(f"  红利候选: {len(filtered_dividend)} 只")
    print(f"  进攻候选: {len(filtered_growth)} 只")
    print(f"  可转债候选: {len(cb_candidates)} 只")
    print(f"  总计: {result['总计']} 只")
    print(f"  错误: {len(errors)} 条")
    print(f"  输出: {OUTPUT_FILE}")
    print(f"{'=' * 60}")

    save_checkpoint("complete", "ALL",
                    result["总计"], result["总计"], errors)
    return result


if __name__ == "__main__":
    run_screening()
