"""Fetch all data for a stock and save as JSON for report generation."""
import json
import time
import sys
import os
import re

def get_prefix(code):
    """Get market prefix from stock code."""
    code = re.sub(r'[^0-9]', '', code)
    if code.startswith(('6', '9')):
        return 'sh' + code
    elif code.startswith('8'):
        return 'bj' + code
    else:
        return 'sz' + code

def fetch_stock_data(code, name, is_etf=False):
    """Fetch comprehensive data for one stock."""
    result = {
        'code': code,
        'name': name,
        'is_etf': is_etf,
        'tencent': None,
        'mootdx_quotes': None,
        'mootdx_finance': None,
        'mootdx_f10': None,
        'mootdx_bars': None,
        'akshare_info': None,
        'akshare_news': None,
        'akshare_reports': None,
        'akshare_forecast': None,
        'akshare_holder': None,
        'akshare_lhb': None,
        'akshare_jiejin': None,
        'akshare_industry': None,
        'akshare_etf_holdings': None if is_etf else None,
    }

    prefixed_code = get_prefix(code)

    # === 1. Tencent Finance (PE/PB/Market Cap) ===
    try:
        import requests
        url = f"https://qt.gtimg.cn/q={prefixed_code}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and prefixed_code in r.text:
            text = r.text
            fields = text.split('~')
            if len(fields) > 50:
                result['tencent'] = {
                    'name': fields[1],
                    'code': fields[2],
                    'price': fields[3],
                    'prev_close': fields[4],
                    'open': fields[5],
                    'volume': fields[6],
                    'prev_volume': fields[7],
                    'high': fields[33],
                    'low': fields[34],
                    'turnover_rate': fields[38],
                    'pe_ttm': fields[39],
                    'amplitude': fields[43],
                    'pb': fields[46],
                    'total_market_cap': fields[45],
                    'float_market_cap': fields[44],
                    'limit_up': fields[47],
                    'limit_down': fields[48],
                }
        print(f"  [OK] Tencent: PE={result['tencent']['pe_ttm'] if result['tencent'] else 'N/A'}, PB={result['tencent']['pb'] if result['tencent'] else 'N/A'}")
    except Exception as e:
        print(f"  [FAIL] Tencent: {e}")
    time.sleep(0.5)

    # === 2. Mootdx Quotes ===
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market='std', bestip=True, timeout=10)
        quotes = client.bars(symbol=code, frequency=9, offset=80)  # daily K-line 80 bars
        if quotes is not None and len(quotes) > 0:
            result['mootdx_bars'] = {
                'count': len(quotes),
                'latest': quotes.tail(5).to_dict('records'),
                'high_60d': float(quotes.tail(60)['high'].max()) if len(quotes) >= 60 else None,
                'low_60d': float(quotes.tail(60)['low'].min()) if len(quotes) >= 60 else None,
                'ma_5': float(quotes.tail(5)['close'].mean()),
                'ma_10': float(quotes.tail(10)['close'].mean()),
                'ma_20': float(quotes.tail(20)['close'].mean()),
                'ma_60': float(quotes.tail(60)['close'].mean()) if len(quotes) >= 60 else None,
            }
        print(f"  [OK] Mootdx K-line: {result['mootdx_bars']['count']} bars, high60={result['mootdx_bars']['high_60d']}, low60={result['mootdx_bars']['low_60d']}")
    except Exception as e:
        print(f"  [FAIL] Mootdx K-line: {e}")
    time.sleep(1)

    # === 3. Mootdx Finance (quarterly financials) ===
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market='std', bestip=True, timeout=10)
        finance = client.finance(symbol=code)
        if finance is not None:
            result['mootdx_finance'] = str(finance)[:3000]
        print(f"  [OK] Mootdx finance: {'yes' if finance is not None else 'no'}")
    except Exception as e:
        print(f"  [FAIL] Mootdx finance: {e}")
    time.sleep(1)

    # === 4. Mootdx F10 (company info) ===
    try:
        from mootdx.affairs import Affairs
        from mootdx.reader import Reader
        reader = Reader.factory(market='std', bestip=True, timeout=10)
        f10_data = reader.finance(id=0, offset=0)
        # Try company info
        try:
            company = reader.get_company_info(code)
            if company:
                result['mootdx_f10'] = str(company)[:5000]
        except:
            pass
        print(f"  [OK] Mootdx F10: {'yes' if result['mootdx_f10'] else 'no'}")
    except Exception as e:
        print(f"  [FAIL] Mootdx F10: {e}")
    time.sleep(1)

    # === 5. Akshare individual info ===
    try:
        import akshare as ak
        info = ak.stock_individual_info_em(symbol=code)
        if info is not None:
            result['akshare_info'] = info.to_dict()
        print(f"  [OK] Akshare info: {list(info['item']) if info is not None else 'N/A'}")
    except Exception as e:
        print(f"  [FAIL] Akshare info: {e}")
    time.sleep(2)

    # === 6. Akshare news ===
    if not is_etf:
        try:
            import akshare as ak
            news = ak.stock_news_em(symbol=code)
            if news is not None and len(news) > 0:
                result['akshare_news'] = news.head(10).to_dict('records')
            print(f"  [OK] Akshare news: {len(news) if news is not None else 0} articles")
        except Exception as e:
            print(f"  [FAIL] Akshare news: {e}")
        time.sleep(2)

    # === 7. Akshare research reports ===
    if not is_etf:
        try:
            import akshare as ak
            reports = ak.stock_research_report_em(symbol=code)
            if reports is not None and len(reports) > 0:
                result['akshare_reports'] = reports.head(10).to_dict('records')
            print(f"  [OK] Akshare reports: {len(reports) if reports is not None else 0} reports")
        except Exception as e:
            print(f"  [FAIL] Akshare reports: {e}")
        time.sleep(2)

    # === 8. Akshare forecast/一致预期 ===
    if not is_etf:
        try:
            import akshare as ak
            forecast = ak.stock_forecast_consensus_em(symbol=code)
            if forecast is not None:
                result['akshare_forecast'] = forecast.head(5).to_dict('records')
            print(f"  [OK] Akshare forecast: {'yes' if forecast is not None else 'no'}")
        except Exception as e:
            print(f"  [FAIL] Akshare forecast: {e}")
        time.sleep(2)

    # === 9. Akshare shareholder count ===
    if not is_etf:
        try:
            import akshare as ak
            holder = ak.stock_gdfx_free_holding_detail_em(symbol=code)
            if holder is not None:
                result['akshare_holder'] = holder.head(10).to_dict('records')
            print(f"  [OK] Akshare holders: {'yes' if holder is not None else 'no'}")
        except Exception as e:
            print(f"  [FAIL] Akshare holders: {e}")
        time.sleep(2)

    # === 10. ETF holdings (for ETFs only) ===
    if is_etf:
        try:
            import akshare as ak
            # Try to get ETF holdings
            holdings = ak.fund_etf_portfolio_ths(symbol=code)
            if holdings is not None and len(holdings) > 0:
                result['akshare_etf_holdings'] = holdings.head(10).to_dict('records')
            print(f"  [OK] Akshare ETF holdings: {len(holdings) if holdings is not None else 0} holdings")
        except Exception as e:
            print(f"  [FAIL] Akshare ETF holdings: {e}")
        time.sleep(2)

        # Try fund info for ETF
        try:
            import akshare as ak
            fund_info = ak.fund_individual_basic_info_em(symbol=code)
            if fund_info is not None:
                result['akshare_info'] = str(fund_info)[:2000]
            print(f"  [OK] Akshare fund info: {'yes' if fund_info is not None else 'no'}")
        except Exception as e:
            print(f"  [FAIL] Akshare fund info: {e}")
        time.sleep(2)

    # === 11. Industry comparison ===
    try:
        import akshare as ak
        industry = ak.stock_board_industry_name_em()
        if industry is not None:
            result['akshare_industry'] = industry.head(30).to_dict('records')
        print(f"  [OK] Akshare industry boards: {len(industry) if industry is not None else 0}")
    except Exception as e:
        print(f"  [FAIL] Akshare industry: {e}")
    time.sleep(2)

    return result


def safe_json_serialize(obj):
    """Convert non-serializable objects to strings."""
    if isinstance(obj, dict):
        return {k: safe_json_serialize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [safe_json_serialize(v) for v in obj]
    elif hasattr(obj, 'tolist'):
        return obj.tolist()
    elif hasattr(obj, 'to_dict'):
        return obj.to_dict()
    elif hasattr(obj, 'isoformat'):
        return obj.isoformat()
    elif isinstance(obj, (bool, int, float, str)):
        return obj
    else:
        return str(obj)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python fetch_stock_data.py <code> <name> [--etf]")
        sys.exit(1)

    code = sys.argv[1]
    name = sys.argv[2]
    is_etf = '--etf' in sys.argv

    print(f"\n=== Fetching data for {name} ({code}) {'[ETF]' if is_etf else '[Stock]'} ===\n")

    data = fetch_stock_data(code, name, is_etf)

    # Save to JSON
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'small_goal', 'data')
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{name}_{code}_data.json")

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(safe_json_serialize(data), f, ensure_ascii=False, indent=2)

    print(f"\n=== Data saved to {output_file} ===")
    print(json.dumps(safe_json_serialize({k: v for k, v in data.items() if k not in ('mootdx_finance', 'mootdx_f10')}), ensure_ascii=False, indent=2)[:3000])
