r"""
D3:断言库**普遍缺输入域校验**,导致「数据错」被 CLI 误报为「命令错」。

## 缺口(2026-10-01 Round 22 实测)

审计断言库全部 **11 处除法运算**,分母多数可由输入置 0。实跑 10 个探针:

```
pre_close=0          DivisionByZero     <- 未声明异常,CLI 会误归 exit 2
leverage=0           DivisionByZero     <- 未声明异常
contract_val=0       DivisionByZero     <- 未声明异常
price=0              DivisionByZero     <- 未声明异常
fraction=0           DivisionByZero     <- 未声明异常
split_ratio=0        DivisionByZero     <- 未声明异常
entry_price=0        AssertionError     <- 语义正确
order_size=0         InvalidOperation   <- 未声明异常(注意:与 DivisionByZero 不同类)
adv=0                ZeroDivisionError  <- 未声明异常(float 除零,第三类)
pool_y=0             DivisionByZero     <- 未声明异常
未声明异常数 = 9/10
```

后果是**退出码契约整体失效**:这些全是「数据不对」,却被 `except Exception`
归为 `status:error` / **exit 2**。而 exit 2 的语义是「命令本身不成立、该修命令」,
与 exit 1「断言跑了但答案错、该重算」的**处置动作恰好相反** —— 调用方会被引向错误的动作。

## 为什么不逐个加 `assert 分母 > 0`

9 处要修,就得逐处判断「0 是合法业务边界还是非法输入」(例如 `order_size=0`
是否算合法空订单、`ex_price=0` 在 Round 19 里被当作**合法**输入用来触发护栏)。
这是业务判断,不是机械修复,猜错会把正确行为改坏。

而根因在**出口**:异常从函数体抛出时,已经能确定「参数绑定成功了、函数确实跑起来了」。
故在 CLI 层按**异常类型**区分即可,无需猜任何业务语义:

- 参数绑定失败(`TypeError`)→ 命令错 → exit 2  ← **保持不变**
- 函数体内算不出来(算术异常)→ 数据错 → exit 1

判据(预注册,R9):
  T1 上表 9 个输入:CLI 必须 `status=fail` / **exit 1**,不得 `error` / 2。
  T2 语义已正确的输入(`entry_price=0`,已抛 AssertionError)行为**不得改变** —— 防过度修复。
  T3 **边界判据**:参数名/个数写错必须仍为 **exit 2**。
     这条是本次修复最关键的一条 —— 它证明修复没有把 exit 2 的语义吃掉。
     没有 T3,「把所有异常都改成 exit 1」也能让 T1 变绿,但那是错的。
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

_ASKS = [{"price": 60000.0, "size": 2.0}]

# 分母可由输入置 0 的实参组(9 处)
_ZERO_DIVISOR = {
    "forward_adj_log_return_safe": ({"pre_close": 0.0, "ex_price": 1.0,
                                     "hist_price": 5.0}, "pre_close=0"),
    "leverage_fee_buffer": ({"balance": 1000.0, "leverage": 0.0, "taker_fee": 0.0005,
                             "target_notional": 1000.0, "expect_rejected": False},
                            "leverage=0"),
    "inverse_contracts": ({"budget_coin": 2.5, "price_usd": 3420.50,
                           "contract_val_usd": 0.0, "expected_contracts": 855},
                          "contract_val=0"),
    "lot_step_budget": ({"budget": 1500.0, "price": 0.0, "lot_step": 0.01,
                         "min_notional": 50.0, "expected_qty": 75}, "price=0"),
    "fractional_tick": ({"raw_price": 104.381, "fraction": 0.0,
                         "expected": "104.375"}, "fraction=0"),
    "reverse_split_volume_factor": ({"split_ratio": 0.0, "expected_price_factor": 10.0,
                                     "expected_vol_factor": 0.1}, "split_ratio=0"),
    "orderbook_vwap": ({"order_size": 0.0, "depth_asks": _ASKS,
                        "expected_vwap": 0.0, "expected_cost": 0.0}, "order_size=0"),
    "slippage_impact": ({"order_val": 100000.0, "adv": 0.0, "daily_vol": 0.02,
                         "budget_bps": 50.0, "expect_penetrated": False}, "adv=0"),
    "amm_constant_product": ({"pool_x": 1000000.0, "pool_y": 0.0, "dx": 50000.0,
                              "fee_rate": 0.003, "expected_dy": 0.0,
                              "expected_price": 0.0}, "pool_y=0"),
}


def run_cli(func, payload):
    r = subprocess.run([sys.executable, "-B", CLI, "--func", func,
                        "--args", json.dumps(payload)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return r.returncode, json.loads(r.stdout)
    except Exception:
        return r.returncode, {"status": "unparsable", "raw": r.stdout, "stderr": r.stderr}


class TestArithmeticInputDomain(unittest.TestCase):
    """「数据错」必须报 exit 1,不能报 exit 2。"""

    def test_T1_zero_divisor_input_is_data_error_not_command_error(self):
        wrong = []
        for func in sorted(_ZERO_DIVISOR):
            payload, label = _ZERO_DIVISOR[func]
            with self.subTest(断言=func, 探针=label):
                rc, out = run_cli(func, payload)
                if out.get("status") != "fail" or rc != 1:
                    wrong.append(f"{func}({label}): status={out.get('status')} exit={rc}")
        self.assertEqual(wrong, [],
                         "以下探针是**数据错**却被报成命令错(exit 2),"
                         "调用方会被引向「修命令」而实际该「重算」:\n  "
                         + "\n  ".join(wrong))

    def test_T2_correct_semantics_unchanged(self):
        """防过度修复:本来就抛 AssertionError 的输入,行为不得改变。"""
        rc, out = run_cli("linear_liq", {"balance": 10000.0, "size": 5.0,
                                          "entry_price": 0.0, "mmr": 0.01,
                                          "fee_rate": 0.0005, "expected_liq": 48509.35})
        self.assertEqual(out.get("status"), "fail",
                         f"entry_price=0 本就报 fail,行为被改变: exit={rc} {out}")
        self.assertEqual(rc, 1)

    def test_T3_parameter_mismatch_stays_exit2(self):
        """★ 边界判据:命令写错仍必须 exit 2,不能被一起改成 exit 1。"""
        # 参数名不存在 -> TypeError -> 命令错
        rc, out = run_cli("tick_floor", {"raw_price": 67432.178, "tick_size": 0.01,
                                         "expected_typo": "67432.17"})
        self.assertEqual(out.get("status"), "error",
                         f"参数名写错被误报成数据错: exit={rc} {out}")
        self.assertEqual(rc, 2, "参数名写错必须 exit 2(该修命令,不是该重算)")

        # 参数个数不对 -> TypeError -> 命令错
        rc, out = run_cli("tick_floor", {"raw_price": 67432.178})
        self.assertEqual(rc, 2, "参数个数不对必须 exit 2")
        self.assertEqual(out.get("status"), "error")

    def test_T4_unknown_assertion_stays_exit2(self):
        """断言名不存在同样是命令错。"""
        rc, out = run_cli("no_such_assertion", {})
        self.assertEqual(rc, 2)
        self.assertEqual(out.get("status"), "error")


if __name__ == "__main__":
    unittest.main(verbosity=2)
