"""Batch screen 124 stocks by criteria with checkpoint resume.

Output: filtered list for detailed reports based on dividend yield, PE, PB criteria.
Usage: python batch_screen.py [--resume]
"""
import json
import time
import requests
import re
import os
import sys

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'small_goal', 'data', 'screen_cache.json')


def get_prefix(code):
    """Derive market prefix from 6-digit stock code."""
    code = re.sub(r'[^0-9]', '', code)
    if code.startswith(('6', '9')):
        return 'sh' + code
    elif code.startswith('8'):
        return 'bj' + code
    else:
        return 'sz' + code


def fetch_tencent(code):
    """Fetch basic data from Tencent Finance API."""
    prefixed = get_prefix(code)
    try:
        url = f"https://qt.gtimg.cn/q={prefixed}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and prefixed in r.text:
            fields = r.text.split('~')
            if len(fields) > 50:
                return {
                    'code': fields[2],
                    'name': fields[1],
                    'price': float(fields[3]) if fields[3] else 0,
                    'prev_close': float(fields[4]) if fields[4] else 0,
                    'high': float(fields[33]) if fields[33] else 0,
                    'low': float(fields[34]) if fields[34] else 0,
                    'turnover_rate': float(fields[38]) if fields[38] else 0,
                    'pe_ttm': float(fields[39]) if fields[39] else 999,
                    'pb': float(fields[46]) if fields[46] else 0,
                    'total_market_cap': float(fields[45]) if fields[45] else 0,
                    'float_market_cap': float(fields[44]) if fields[44] else 0,
                    'amplitude': float(fields[43]) if fields[43] else 0,
                }
    except Exception:
        pass
    return None


def calc_dividend_yield(pe_ttm, payout_ratio=0.30):
    """Estimate dividend yield from PE: yield = payout_ratio / PE."""
    if pe_ttm and pe_ttm > 0:
        return payout_ratio / pe_ttm * 100
    return 0


def classify_stock(name, pe, pb, cap, dividend_yield):
    """Classify stock into strategy buckets."""
    tags = []

    # Red dividend candidate
    if dividend_yield >= 4.0:
        tags.append('红利候选')
    elif dividend_yield >= 3.0:
        tags.append('红利关注')

    # Value stock: PE < 15 and reasonable PB
    if pe and 0 < pe < 15 and pb and 0 < pb < 1.5:
        tags.append('价值股')

    # Tech-related
    tech_keywords = ['科技', '半导体', '芯片', '通信', '电子', '软件', 'AI', '人工', '智能',
                     '中微', '中芯', '海光', '寒武纪', '韦尔', '北方华创', '澜起', '金山',
                     '传音', '讯飞', '浪潮', '生益', '长电', '紫光', '锐捷', '长川', '拓荆',
                     '华润微', '龙芯', '瑞芯', '圣邦', '天孚', '光迅', '华工', '协创',
                     '润泽', '深科技', '烽火', '景旺', '胜宏', '香农']
    is_tech = any(kw in name for kw in tech_keywords)

    if is_tech:
        if pe and 0 < pe < 50:
            tags.append('科技成长')
        elif pe and pe >= 50:
            tags.append('科技高估值')
        else:
            tags.append('科技(PE缺失)')

    # Stable high-dividend: banks, highways, utilities
    stable_keywords = ['银行', '高速', '电力', '水泥', '煤炭', '钢铁', '交通']
    is_stable = any(kw in name for kw in stable_keywords)
    if is_stable and dividend_yield >= 4.0:
        tags.append('稳定高息')

    # PB discount
    if pb and 0 < pb < 0.7:
        tags.append('PB打折')

    # Ultra high valuation
    if pe and pe > 100:
        tags.append('超高估值')

    if not tags:
        tags.append('待观察')

    return tags


def load_cache():
    """Load previously cached results."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_cache(cache_data):
    """Save cache to disk."""
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)


def main():
    resume = '--resume' in sys.argv

    # Load stock list
    input_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reports', 'stock_list.json')
    with open(input_file, 'r', encoding='utf-8') as f:
        stocks = json.load(f)

    # Load cache for resume
    cache = load_cache()
    cached_count = len(cache)
    total = len(stocks)

    if resume and cached_count > 0:
        print(f"Resume mode: {cached_count}/{total} already cached. Continuing...\n")
    elif cached_count > 0 and not resume:
        print(f"Found {cached_count} cached results. Use --resume to continue, or starting fresh.\n")
        cache = {}

    results = []
    errors = []

    for i, stock in enumerate(stocks):
        code = stock['code']
        name = stock['name']

        # Check cache first
        if code in cache:
            data = cache[code]
        else:
            data = fetch_tencent(code)
            if data:
                cache[code] = data
                save_cache(cache)  # Save after each successful fetch
            time.sleep(0.3)

        if data:
            pe = data['pe_ttm']
            pb = data['pb']
            cap = data['total_market_cap']
            dividend_yield = calc_dividend_yield(pe)
            tags = classify_stock(name, pe, pb, cap, dividend_yield)

            result = {
                **data,
                'dividend_yield': round(dividend_yield, 2),
                'tags': tags,
                'market_cap_yi': round(cap / 10000, 1) if cap else 0,
            }
            results.append(result)
            print(f"  [{i+1:3d}/{total}] {name:8s} {code:6s} PE={pe:7.1f} PB={pb:.2f} 股息率={dividend_yield:.2f}% 市值={result['market_cap_yi']:8.1f}亿 | {', '.join(tags)}")
        else:
            errors.append({'code': code, 'name': name})
            print(f"  [{i+1:3d}/{total}] {name:8s} {code:6s} FAILED")

    # Save all results
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'small_goal', 'data')
    os.makedirs(output_dir, exist_ok=True)

    all_file = os.path.join(output_dir, 'all_124_stocks_screen.json')
    with open(all_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # ===== Filtering =====
    print("\n" + "=" * 120)
    print("FILTERED RESULTS")
    print("=" * 120)

    # Category 1: Red dividend candidates (股息率 >= 4%)
    red_stocks = [r for r in results if '红利候选' in r['tags']]
    red_stocks.sort(key=lambda x: x['dividend_yield'], reverse=True)

    print(f"\n【红利候选】(股息率>=4%): {len(red_stocks)} 只")
    for r in red_stocks[:40]:
        print(f"  {r['name']:10s} {r['code']:6s} PE={r['pe_ttm']:5.1f}x PB={r['pb']:.2f}x 股息率={r['dividend_yield']:.2f}% 市值={r['market_cap_yi']:.0f}亿 | {', '.join(r['tags'])}")

    # Category 2: Tech growth
    tech_stocks = [r for r in results if any(t in r['tags'] for t in ('科技成长', '科技高估值'))]
    tech_stocks.sort(key=lambda x: x['pe_ttm'])

    print(f"\n【科技/成长】: {len(tech_stocks)} 只")
    for r in tech_stocks[:40]:
        print(f"  {r['name']:10s} {r['code']:6s} PE={r['pe_ttm']:5.1f}x PB={r['pb']:.2f}x 股息率={r['dividend_yield']:.2f}% 市值={r['market_cap_yi']:.0f}亿 | {', '.join(r['tags'])}")

    # Category 3: Value stocks (PE<15, PB<1.5, not red dividend)
    value_stocks = [r for r in results if '价值股' in r['tags'] and '红利候选' not in r['tags']]
    value_stocks.sort(key=lambda x: x['pe_ttm'])

    print(f"\n【价值股】(PE<15, PB<1.5, 非红利): {len(value_stocks)} 只")
    for r in value_stocks[:30]:
        print(f"  {r['name']:10s} {r['code']:6s} PE={r['pe_ttm']:5.1f}x PB={r['pb']:.2f}x 股息率={r['dividend_yield']:.2f}% 市值={r['market_cap_yi']:.0f}亿 | {', '.join(r['tags'])}")

    # Category 4: PB discount
    pb_stocks = [r for r in results if 'PB打折' in r['tags']]
    pb_stocks.sort(key=lambda x: x['pb'])

    print(f"\n【PB打折】(PB<0.7): {len(pb_stocks)} 只")
    for r in pb_stocks[:20]:
        print(f"  {r['name']:10s} {r['code']:6s} PE={r['pe_ttm']:5.1f}x PB={r['pb']:.2f}x 股息率={r['dividend_yield']:.2f}% 市值={r['market_cap_yi']:.0f}亿 | {', '.join(r['tags'])}")

    # Generate filtered list for detailed reports
    filtered_codes = []
    # Top 15 red dividend candidates
    filtered_codes.extend([r['code'] for r in red_stocks[:15]])
    # Tech with reasonable PE (< 50)
    filtered_codes.extend([r['code'] for r in tech_stocks if r['pe_ttm'] < 50][:10])
    # Top 5 value stocks
    filtered_codes.extend([r['code'] for r in value_stocks[:5]])
    # Top 5 PB discount (not already in list)
    pb_extra = [r['code'] for r in pb_stocks if r['code'] not in filtered_codes][:5]
    filtered_codes.extend(pb_extra)

    # Deduplicate preserving order
    filtered_codes = list(dict.fromkeys(filtered_codes))

    filtered_list = []
    for code in filtered_codes:
        r = next((x for x in results if x['code'] == code), None)
        if r:
            filtered_list.append({'code': r['code'], 'name': r['name'], 'tags': r['tags']})

    filtered_file = os.path.join(output_dir, 'filtered_for_detailed_report.json')
    with open(filtered_file, 'w', encoding='utf-8') as f:
        json.dump(filtered_list, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 120}")
    print(f"筛选出 {len(filtered_list)} 只标的做详细报告：")
    for item in filtered_list:
        print(f"  {item['name']:10s} {item['code']:6s} | {', '.join(item['tags'])}")
    print(f"\n筛选结果保存至: {filtered_file}")
    print(f"全部数据保存至: {all_file}")
    print(f"缓存文件: {CACHE_FILE} (可用于 --resume 断点续传)")

    if errors:
        print(f"\nFailed: {len(errors)} stocks")
        for e in errors:
            print(f"  {e['name']} {e['code']}")


if __name__ == '__main__':
    main()
