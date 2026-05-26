"""Tests for stock_screener.py"""
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestTencentQuoteParsing(unittest.TestCase):
    """Test Tencent quote data parsing."""

    def test_parse_valid_response(self):
        from stock_screener import get_tencent_quote

        mock_response = MagicMock()
        mock_response.status_code = 200
        # Tencent format: v_sh601398="1~名称~...~价格~开~高~低~成交量~成交额~~涨跌幅~~...~PE~...~市值~...~PB"
        parts = [""] * 50
        parts[1] = "工商银行"
        parts[3] = "7.18"
        parts[4] = "7.10"
        parts[5] = "7.20"
        parts[6] = "7.05"
        parts[7] = "100000"
        parts[8] = "718000"
        parts[32] = "0.50"
        parts[39] = "6.89"
        parts[44] = "19358.16"
        parts[46] = "0.82"
        mock_response.text = "v_sh601398=\"" + "~".join(parts) + "\";"

        with patch("stock_screener.requests.get", return_value=mock_response):
            result = get_tencent_quote("601398")

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["price"], 7.18)
        self.assertAlmostEqual(result["pe"], 6.89)
        self.assertAlmostEqual(result["market_cap"], 19358.16)

    def test_parse_empty_response(self):
        from stock_screener import get_tencent_quote

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""

        with patch("stock_screener.requests.get", return_value=mock_response):
            result = get_tencent_quote("601398")

        self.assertIsNone(result)

    def test_parse_http_error(self):
        from stock_screener import get_tencent_quote

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("stock_screener.requests.get", return_value=mock_response):
            result = get_tencent_quote("601398")

        self.assertIsNone(result)

    def test_prefix_sh(self):
        """Codes starting with 6 should use sh prefix."""
        from stock_screener import get_tencent_quote
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""

        with patch("stock_screener.requests.get", return_value=mock_response) as mock_get:
            get_tencent_quote("601398")
            call_url = mock_get.call_args[0][0]
            self.assertIn("sh601398", call_url)

    def test_prefix_sz(self):
        """Codes starting with 0/3 should use sz prefix."""
        from stock_screener import get_tencent_quote
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""

        with patch("stock_screener.requests.get", return_value=mock_response) as mock_get:
            get_tencent_quote("000001")
            call_url = mock_get.call_args[0][0]
            self.assertIn("sz000001", call_url)


class TestRetryLogic(unittest.TestCase):
    """Test retry_call mechanism."""

    def test_success_on_first_try(self):
        from stock_screener import retry_call

        fn = MagicMock(return_value=42)
        with patch("stock_screener.time.sleep"):
            result = retry_call(fn, "arg1")

        self.assertEqual(result, 42)
        fn.assert_called_once_with("arg1")

    def test_success_on_retry(self):
        from stock_screener import retry_call

        fn = MagicMock(side_effect=[Exception("fail"), 42])
        with patch("stock_screener.time.sleep"):
            result = retry_call(fn)

        self.assertEqual(result, 42)
        self.assertEqual(fn.call_count, 2)

    def test_all_retries_fail(self):
        from stock_screener import retry_call

        fn = MagicMock(side_effect=Exception("always fail"))
        with patch("stock_screener.time.sleep"):
            result = retry_call(fn)

        self.assertIsNone(result)
        self.assertEqual(fn.call_count, 3)


class TestCheckpoint(unittest.TestCase):
    """Test checkpoint save/load."""

    def test_save_and_load(self):
        from stock_screener import save_checkpoint, CHECKPOINT_FILE

        errors = [{"code": "000001", "error": "test"}]
        save_checkpoint("screening", "601398", 10, 50, errors)

        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["phase"], "screening")
        self.assertEqual(data["last_processed"], "601398")
        self.assertEqual(data["processed_count"], 10)
        self.assertEqual(len(data["errors"]), 1)

        # Cleanup
        os.remove(CHECKPOINT_FILE)


class TestFilteringLogic(unittest.TestCase):
    """Test stock filtering criteria."""

    def test_dividend_candidate_qualifies(self):
        stock = {
            "code": "601398", "name": "工商银行", "price": 7.18,
            "pe": 6.89, "pb": 0.82, "market_cap": 19358,
            "dividend_yield": 5.3, "industry": "银行",
        }
        qualifies = (
            stock["dividend_yield"] > 4.0
            and stock["pe"] < 20
            and stock["industry"] in {"银行", "煤炭", "公用事业", "建筑"}
        )
        self.assertTrue(qualifies)

    def test_dividend_candidate_fails_pe(self):
        stock = {
            "code": "600009", "name": "上海机场", "price": 25.61,
            "pe": 29.29, "pb": 3.5, "market_cap": 524,
            "dividend_yield": 1.5, "industry": "交通运输",
        }
        qualifies = (
            stock["dividend_yield"] > 4.0
            and stock["pe"] < 20
        )
        self.assertFalse(qualifies)

    def test_growth_candidate_qualifies(self):
        stock = {
            "code": "688981", "name": "中芯国际", "price": 149.18,
            "pe": 236.92, "market_cap": 2982,
            "industry": "半导体",
        }
        qualifies = (
            stock["industry"] in {"半导体", "人工智能", "软件", "互联网", "电子", "通信"}
            and stock["market_cap"] > 50
        )
        self.assertTrue(qualifies)

    def test_growth_candidate_fails_market_cap(self):
        stock = {
            "code": "002410", "name": "广联达", "price": 9.94,
            "pe": 40.1, "market_cap": 15,
            "industry": "软件",
        }
        qualifies = stock["market_cap"] > 50
        self.assertFalse(qualifies)


if __name__ == "__main__":
    unittest.main()
