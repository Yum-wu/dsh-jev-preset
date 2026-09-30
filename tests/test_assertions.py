# -*- coding: utf-8 -*-
"""
JEV 标准断言库全量回归守护套件 (Regression Guard)
覆盖全部 5 大风险域的核心断言函数与异常拦截
"""
import unittest
import sys
import os

# 将 packages/assertions/python 加入搜索路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../packages/assertions/python")))

from jev_assertions import (
    assert_tick_floor,
    assert_tick_ceiling,
    assert_fractional_tick,
    assert_lot_step_budget,
    assert_inverse_contracts,
    assert_tiered_mm,
    assert_linear_liq_price,
    assert_inverse_liq_price,
    assert_collateral_haircut,
    assert_orderbook_vwap,
    assert_almgren_chriss_impact,
    assert_amm_constant_product,
    assert_leverage_fee_buffer,
    assert_ny_open_utc,
    assert_clock_monotonic,
    assert_ex_right_price,
    assert_forward_adj_log_return_safe,
    assert_reverse_split_volume_factor
)

class TestJevAssertions(unittest.TestCase):

    def test_tick_assertions(self):
        # 1. 严格向下截断
        self.assertTrue(assert_tick_floor(67432.178, 0.01, "67432.17"))
        with self.assertRaises(AssertionError):
            assert_tick_floor(67432.178, 0.01, "67432.18") # 禁止四舍五入

        # 2. 严格向上截断
        self.assertTrue(assert_tick_ceiling(0.000034, 0.0001, "0.0001"))
        
        # 3. 分数步长
        self.assertTrue(assert_fractional_tick(104.381, 0.125, "104.375"))

        # 4. Lot step 与最小名义价值
        self.assertTrue(assert_lot_step_budget(1500.0, 19.83, 1.0, 50.0, 75))
        
        # 5. 反向合约张数
        self.assertTrue(assert_inverse_contracts(2.5, 3420.50, 10.0, 855))

    def test_margin_assertions(self):
        tiers = [
            {"tier": 1, "max_notional": 50000.0, "mmr": 0.005},
            {"tier": 2, "max_notional": 250000.0, "mmr": 0.01},
            {"tier": 3, "max_notional": 1000000.0, "mmr": 0.02},
        ]
        self.assertTrue(assert_tiered_mm(400000.0, tiers, 5250.0, 2750.0))
        
        # 正向合约强平
        self.assertTrue(assert_linear_liq_price(10000.0, 5.0, 50000.0, 0.01, 0.0005, 48509.35))
        
        # 反向合约空头强平
        self.assertTrue(assert_inverse_liq_price(10.0, 10000, 10.0, 3000.0, 0.02, 2353.85))

        # 抵押品折扣
        assets = [
            {"coin": "USDT", "amount": 10000.0, "price": 1.0, "haircut": 1.0},
            {"coin": "ETH", "amount": 2.0, "price": 3500.0, "haircut": 0.90},
            {"coin": "SOL", "amount": 500.0, "price": 150.0, "haircut": 0.80},
        ]
        self.assertTrue(assert_collateral_haircut(assets, 92000.0, 76300.0))

    def test_slippage_assertions(self):
        asks = [
            {"price": 60000.0, "size": 2.0},
            {"price": 60010.0, "size": 3.5},
            {"price": 60030.0, "size": 5.0},
            {"price": 60100.0, "size": 10.0},
        ]
        self.assertTrue(assert_orderbook_vwap(12.5, asks, 60030.80, 750385.0))
        
        # 平方根冲击模型穿透
        self.assertTrue(assert_almgren_chriss_impact(500000.0, 10000000.0, 0.025, 15.0, True))
        
        # AMM 恒定乘积
        self.assertTrue(assert_amm_constant_product(1000000.0, 500.0, 50000.0, 0.003, "23.741496", "2105.98"))

        # 手续费垫资
        self.assertTrue(assert_leverage_fee_buffer(10000.0, 10.0, 0.0006, 100000.0, True))

    def test_calendar_assertions(self):
        # 纽约冬令时 vs 夏令时
        self.assertTrue(assert_ny_open_utc("2026-03-06", "09:30:00", "14:30:00"))
        self.assertTrue(assert_ny_open_utc("2026-03-09", "09:30:00", "13:30:00"))
        
        # 单调时钟
        self.assertTrue(assert_clock_monotonic(100, 105, True))
        self.assertTrue(assert_clock_monotonic(105, 100, False))

    def test_split_assertions(self):
        # 除权价计算
        self.assertTrue(assert_ex_right_price(28.00, 0, 30, 3.00, "6.925"))
        
        # 前复权对数收益率安全
        self.assertTrue(assert_forward_adj_log_return_safe(28.00, 6.925, 1.20))
        
        # 缩股价格与成交量反向守恒
        self.assertTrue(assert_reverse_split_volume_factor(0.1, 10.0, 0.1))

    def test_cli_runner(self):
        import subprocess
        import json
        cli_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../packages/assertions/python/jev_assertions/cli.py"))
        
        # 1. 测试 --list
        res = subprocess.run([sys.executable, cli_path, "--list"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data["status"], "ok")
        self.assertIn("tick_floor", data["assertions"])
        self.assertIn("ny_open_utc", data["assertions"])

        # 2. 测试正常断言通过
        payload = json.dumps({"raw_price": 67432.178, "tick_size": 0.01, "expected": "67432.17"})
        res = subprocess.run([sys.executable, cli_path, "--func", "tick_floor", "--args", payload], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data["status"], "pass")
        self.assertEqual(data["assertion"], "tick_floor")

        # 3. 测试断言失败 (非四舍五入)
        fail_payload = json.dumps({"raw_price": 67432.178, "tick_size": 0.01, "expected": "67432.18"})
        res = subprocess.run([sys.executable, cli_path, "--func", "tick_floor", "--args", fail_payload], capture_output=True, text=True)
        self.assertEqual(res.returncode, 1)
        data = json.loads(res.stdout)
        self.assertEqual(data["status"], "fail")

if __name__ == "__main__":
    unittest.main()
