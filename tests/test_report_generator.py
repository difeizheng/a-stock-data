"""Tests for report_generator.py"""
import os
import sys
import json
import tempfile
import shutil
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSafeFloat(unittest.TestCase):
    """Test safe_float utility."""

    def test_valid_number(self):
        from report_generator import safe_float
        self.assertAlmostEqual(safe_float("3.14"), 3.14)

    def test_invalid_string(self):
        from report_generator import safe_float
        self.assertAlmostEqual(safe_float("abc"), 0.0)

    def test_none(self):
        from report_generator import safe_float
        self.assertAlmostEqual(safe_float(None), 0.0)

    def test_negative(self):
        from report_generator import safe_float
        self.assertAlmostEqual(safe_float("-2.5"), -2.5)

    def test_custom_default(self):
        from report_generator import safe_float
        self.assertAlmostEqual(safe_float("x", -1.0), -1.0)

    def test_nan_string(self):
        from report_generator import safe_float
        import math
        result = safe_float(float("nan"))
        self.assertAlmostEqual(result, 0.0)


class TestDividendYieldCalc(unittest.TestCase):
    """Test dividend yield calculation from history."""

    def test_valid_calculation(self):
        from report_generator import get_dividend_yield_from_history
        history = [{"amount": 0.35, "year": "2025"}]
        result = get_dividend_yield_from_history(history, 7.0)
        self.assertAlmostEqual(result, 5.0)

    def test_zero_price(self):
        from report_generator import get_dividend_yield_from_history
        history = [{"amount": 0.35, "year": "2025"}]
        result = get_dividend_yield_from_history(history, 0)
        self.assertAlmostEqual(result, 0.0)

    def test_empty_history(self):
        from report_generator import get_dividend_yield_from_history
        result = get_dividend_yield_from_history([], 7.0)
        self.assertAlmostEqual(result, 0.0)


class TestStrategyEvaluation(unittest.TestCase):
    """Test strategy evaluation logic."""

    def test_high_dividend_defense_score(self):
        from report_generator import evaluate_strategy
        quote = {"price": 7.0, "pe_ttm": 6.0, "pb": 0.8, "market_cap": 1000, "wave": 0.5}
        financial = {"净资产收益率": 12.0}
        result = evaluate_strategy("601398", quote, financial, 5.3, "dividend")

        self.assertEqual(result["defense_score"], 5)
        self.assertIn("强烈推荐", result["rating"])
        self.assertIn("买入", result["suggestion"])

    def test_low_dividend_defense_score(self):
        from report_generator import evaluate_strategy
        quote = {"price": 25.0, "pe_ttm": 30.0, "pb": 3.0, "market_cap": 500, "wave": -1.0}
        financial = {"净资产收益率": 5.0}
        result = evaluate_strategy("601360", quote, financial, 1.7, "dividend")

        self.assertLessEqual(result["defense_score"], 2)
        self.assertIn("不推荐", result["rating"])

    def test_growth_high_score(self):
        from report_generator import evaluate_strategy
        quote = {"price": 150.0, "pe_ttm": 25.0, "pb": 5.0, "market_cap": 3000, "wave": 2.0}
        financial = {"净资产收益率": 15.0}
        result = evaluate_strategy("688981", quote, financial, 0.0, "growth")

        self.assertGreaterEqual(result["offense_score"], 4)
        self.assertIn("推荐", result["rating"])

    def test_growth_overvalued(self):
        from report_generator import evaluate_strategy
        quote = {"price": 1400.0, "pe_ttm": 326.0, "pb": 72.0, "market_cap": 8000, "wave": 3.0}
        financial = {"净资产收益率": 2.0}
        result = evaluate_strategy("688256", quote, financial, 0.0, "growth")

        self.assertLessEqual(result["offense_score"], 3)

    def test_stop_loss_calculation(self):
        from report_generator import evaluate_strategy
        quote = {"price": 10.0, "pe_ttm": 5.0, "pb": 0.5, "market_cap": 1000, "wave": 0}
        financial = {}
        result = evaluate_strategy("601398", quote, financial, 5.0, "dividend")

        self.assertAlmostEqual(result["stop_loss_price"], 8.0)


class TestReportGeneration(unittest.TestCase):
    """Test report file generation."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.reports_dir = os.path.join(self.test_dir, "reports")
        os.makedirs(self.reports_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch("report_generator.retry_call")
    @patch("report_generator.get_tencent_quote")
    def test_skips_existing_report(self, mock_quote, mock_retry):
        from report_generator import generate_report

        today = "2026-05-27"
        filename = f"测试_600000_投资研究报告_{today}.md"
        filepath = os.path.join(self.reports_dir, filename)
        with open(filepath, "w") as f:
            f.write("existing")

        with patch("report_generator.REPORTS_DIR", self.reports_dir):
            result = generate_report("600000", "测试", "dividend")

        self.assertFalse(result)

    @patch("report_generator.get_tencent_quote")
    def test_skips_when_no_quote(self, mock_quote):
        from report_generator import generate_report

        mock_quote.return_value = None

        with patch("report_generator.REPORTS_DIR", self.reports_dir), \
             patch("report_generator.retry_call", return_value=None):
            result = generate_report("600000", "测试", "dividend")

        self.assertFalse(result)


class TestCheckpointIO(unittest.TestCase):
    """Test checkpoint save/load."""

    def test_save_load_roundtrip(self):
        from report_generator import load_checkpoint, save_checkpoint, CHECKPOINT_FILE

        test_cp = os.path.join(tempfile.gettempdir(), ".test_checkpoint.json")
        with patch("report_generator.CHECKPOINT_FILE", test_cp):
            save_checkpoint({"last_processed": "601398", "count": 5, "errors": []})
            loaded = load_checkpoint()
            self.assertEqual(loaded["last_processed"], "601398")
            self.assertEqual(loaded["count"], 5)

        os.remove(test_cp)

    def test_load_missing_returns_default(self):
        from report_generator import load_checkpoint

        test_cp = os.path.join(tempfile.gettempdir(), ".nonexistent_cp.json")
        with patch("report_generator.CHECKPOINT_FILE", test_cp):
            result = load_checkpoint()
            self.assertEqual(result["count"], 0)


if __name__ == "__main__":
    unittest.main()
