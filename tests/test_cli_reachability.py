# -*- coding: utf-8 -*-
r"""
断言库的 **CLI 可达性**:`--list` 说有 18 项,不等于 18 项都能通过 CLI 调用。

## 缺口(2026-10-01 Round 19/20 实锤)

`packages/assertions/python/jev_assertions/calendar.py` 与 Python 标准库 `calendar` **同名**。
以脚本方式跑 `python cli.py` 时,`sys.path[0]` 就是脚本所在目录,于是标准库
`_strptime.py` 内部的 `import calendar` 会命中**本仓文件**:

```
  File "...\Lib\_strptime.py", line 83, in __calc_weekday
    a_weekday = [calendar.day_abbr[i].lower() for i in range(7)]
AttributeError: module 'calendar' has no attribute 'day_abbr'
```

后果:`ny_open_utc` 在 CLI 路径下**恒定 exit 2 / status:error**,而同一条断言
在包内导入路径下完全正常。

⚠ 为什么此前没被发现:`--list` 只查**数量**,现有全部 `ny_open_utc` 测试
(`test_assertions.py` / `test_assertions_reverse.py` / `test_guardrails.py`)
都走**包内导入**,**没有一条**走 CLI 路径 —— 即 persona §五 规定的、agent
实际会用的那条命令,从未被任何测试覆盖过。

判据(预注册,R9):
  T1 **逐项 pass**:每个断言经 CLI 调用必须 `status=pass` / exit 0。
     为什么要求 `pass` 而不是「不是 error」:后者把「期望值填错」也算成可达 ——
     红队 78c78922 实测 `inverse_liq` 的期望值抄了 `linear_liq` 的 48509.35
     (真实值 0.0005),在宽松判据下照样全绿。
  T2 **集合相等**:payload 集合必须与 `--list` 公布的集合完全相等。
     缺任何一项都说明新增断言时忘了补用例,而没有这条,T1 会因「没测的不参与」而全绿。
  T3 `ny_open_utc` 端到端可用:正确值 exit 0、错值 exit 1。
  T4 **边界**:`tiered_mm` 与参数名写错仍必须 exit 2 —— 证明修复没把「命令错」吃成「数据错」。
"""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
CLI = os.path.join(PLUGIN_ROOT, "packages", "assertions", "python",
                   "jev_assertions", "cli.py")

# 短名 -> 合法实参。实参取自 tests/test_assertions_reverse.py 已验证的用例,
# 避免「抄来的正确值本身是错的」(Round 17/18 的 amm 76.1% 教训)。
_PAYLOADS = {
    "tick_floor": {"raw_price": 67432.178, "tick_size": 0.01, "expected": "67432.17"},
    "tick_ceiling": {"raw_price": 67432.178, "tick_size": 0.01, "expected": "67432.18"},
    "fractional_tick": {"raw_price": 104.381, "fraction": 0.125, "expected": "104.375"},
    "lot_step_budget": {"budget": 1500.0, "price": 19.83, "lot_step": 0.01,
                        "min_notional": 50.0, "expected_qty": 75},
    "inverse_contracts": {"budget_coin": 2.5, "price_usd": 3420.50,
                          "contract_val_usd": 10.0, "expected_contracts": 855},
    "linear_liq": {"balance": 10000.0, "size": 5.0, "entry_price": 50000.0,
                   "mmr": 0.01, "fee_rate": 0.0005, "expected_liq": 48509.35},
    "inverse_liq": {"balance_coin": 0.01, "contracts": 5.0, "face_val": 1.0,
                    "entry_price": 50000.0, "mmr": 0.01, "expected_liq": 500.0},
    "collateral_haircut": {
        "assets": [
            {"coin": "USDT", "amount": 10000.0, "price": 1.0, "haircut": 1.0},
            {"coin": "ETH", "amount": 2.0, "price": 3500.0, "haircut": 0.90},
            {"coin": "SOL", "amount": 500.0, "price": 150.0, "haircut": 0.80},
        ],
        "expected_nominal": 92000.0, "expected_adjusted": 76300.0},
    "orderbook_vwap": {
        "order_size": 12.5,
        "depth_asks": [{"price": 60000.0, "size": 2.0}, {"price": 60010.0, "size": 3.5},
                       {"price": 60030.0, "size": 5.0}, {"price": 60100.0, "size": 10.0}],
        "expected_vwap": 60030.80, "expected_cost": 750385.0},
    "slippage_impact": {"order_val": 100000.0, "adv": 1000000.0, "daily_vol": 0.02,
                        "budget_bps": 50.0, "expect_penetrated": False},
    "amm_constant_product": {"pool_x": 1000000.0, "pool_y": 500.0, "dx": 50000.0,
                             "fee_rate": 0.003, "expected_dy": 23.741496,
                             "expected_price": 2106.018054},
    "leverage_fee_buffer": {"balance": 1000.0, "leverage": 2.0, "taker_fee": 0.0005,
                            "target_notional": 1000.0, "expect_rejected": False},
    "ny_open_utc": {"date_str": "2026-03-06", "ny_open_local": "09:30:00",
                    "expected_utc": "14:30:00"},
    "clock_monotonic": {"t1_ns": 1000, "t2_ns": 2000, "expect_monotonic": True},
    "ex_right_price": {"pre_close": 28.00, "bonus_per_10": 0, "transfer_per_10": 30,
                       "dividend_per_10": 3.00, "expected_ex": "6.925"},
    "forward_adj_log_return_safe": {"pre_close": 28.00, "ex_price": 1.0,
                                    "hist_price": 25.0},
    "reverse_split_volume_factor": {"split_ratio": 0.1, "expected_price_factor": 10.0,
                                    "expected_vol_factor": 0.1},
    "tiered_mm": {"notional": 30000.0,
                  "tiers": [{"tier": 1, "max_notional": 50000.0, "mmr": 0.005},
                            {"tier": 2, "max_notional": 250000.0, "mmr": 0.01}],
                  "expected_mm": 150.0, "expected_deduction": 0.0},
}


def run_cli_list():
    r = subprocess.run([sys.executable, "-B", CLI, "--list"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return json.loads(r.stdout)["assertions"]


def run_cli(func, payload):
    """以**脚本方式**调用 CLI —— 这正是 persona §五 规定的执行路径。"""
    r = subprocess.run([sys.executable, "-B", CLI, "--func", func,
                        "--args", json.dumps(payload)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        out = json.loads(r.stdout)
    except Exception:
        out = {"status": "unparsable", "raw": r.stdout, "stderr": r.stderr}
    return r.returncode, out


class TestCliReachability(unittest.TestCase):
    """`--list` 的数量 ≠ 18 项都能通过 CLI 调用。

    ⚠ 本文件在 Round 22 被红队 78c78922 推翻过一次,已收紧两处:
      ① 原 T1 判据是 `status != error`,把 `fail` 也算「可达」——
         于是**期望值填错**的用例(实测 `inverse_liq` 抄了 `linear_liq` 的 48509.35,
         而真实值是 0.0005)照样全绿。现改为要求 `status == pass`。
      ② 原文件**不与 `--list` 交叉校验**,红队实测删掉 4/17 条 payload 后测试仍 OK。
         现补 T2 强制集合相等。
      ③ 原 T3 是 `assertIn(status, 全部可能取值)` —— **恒真断言**,
         与我自己在 test_guardrails.py 里批过的 G6「同义反复」是同一个错误。已删除。
    """

    def test_T1_every_assertion_passes_through_cli(self):
        """可达的**充分**证据:每项都用一组经独立复算的**正确值**调用,必须 `pass`。

        `pass` 证明的不只是「函数被调到了」,而是「import 链完整、时区后端可用、
        参数形状正确、公式真的算出了预期结果」—— 比 `status != error` 强得多。
        """
        wrong = []
        for name in sorted(_PAYLOADS):
            with self.subTest(断言=name):
                rc, out = run_cli(name, _PAYLOADS[name])
                if out.get("status") != "pass" or rc != 0:
                    wrong.append(f"{name}: status={out.get('status')} exit={rc} "
                                 f"{out.get('error') or out.get('message') or ''}")
        self.assertEqual(
            wrong, [],
            "以下断言未能在 CLI 路径上给出 pass(要么不可用,要么这里的期望值本身是错的):\n  "
            + "\n  ".join(wrong))

    def test_T2_payload_set_matches_cli_list(self):
        """防漏检:payload 集合必须与 `--list` 公布的集合**完全相等**。

        少了任何一项,都说明新增断言时忘了补用例 —— 而没有这条,T1 会因为
        「没测的项不参与」而全绿(红队实测:删 4/17 条 payload,exit 仍为 0)。
        """
        listed = set(run_cli_list())
        covered = set(_PAYLOADS)
        self.assertEqual(
            sorted(listed - covered), [],
            f"--list 里有 {len(listed)} 项,但这些没有对应 payload(新增断言时忘了补用例):"
            f" {sorted(listed - covered)}")
        self.assertEqual(
            sorted(covered - listed), [],
            f"payload 里有这些名字,但 --list 里没有(可能已改名或被删):"
            f" {sorted(covered - listed)}")
        self.assertEqual(len(listed), 18, f"--list 应为 18 项,实际 {len(listed)}")

    def test_T3_ny_open_utc_end_to_end_through_cli(self):
        """D1 的直接复现:正确值必须 exit 0,错值必须 exit 1。"""
        ok_rc, ok_out = run_cli("ny_open_utc", _PAYLOADS["ny_open_utc"])
        self.assertEqual(ok_out.get("status"), "pass",
                         f"冬令时正确值未通过 CLI: exit={ok_rc} {ok_out}")
        self.assertEqual(ok_rc, 0)

        bad = dict(_PAYLOADS["ny_open_utc"], expected_utc="13:30:00")  # 夏令时答案
        bad_rc, bad_out = run_cli("ny_open_utc", bad)
        self.assertEqual(bad_out.get("status"), "fail",
                         f"错值未被 CLI 拒绝: exit={bad_rc} {bad_out}")
        self.assertEqual(bad_rc, 1)

    def test_T4_parameter_mismatch_stays_exit2(self):
        """★ 边界判据:命令写错仍必须 exit 2,不能被误判成数据错(exit 1)。"""
        rc, out = run_cli("tick_floor", {"raw_price": 67432.178, "tick_size": 0.01,
                                         "expected_typo": "67432.17"})
        self.assertEqual(out.get("status"), "error",
                         f"参数名写错被误报成数据错: exit={rc} {out}")
        self.assertEqual(rc, 2, "参数名写错必须 exit 2(该修命令,不是该重算)")

        rc, out = run_cli("no_such_assertion", {})
        self.assertEqual(rc, 2, "断言名不存在同样属于命令错")
        self.assertEqual(out.get("status"), "error")


if __name__ == "__main__":
    unittest.main(verbosity=2)
