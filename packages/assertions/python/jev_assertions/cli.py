# -*- coding: utf-8 -*-
"""
JEV 标准断言库泛化命令行调度入口
支持全部 18 个量化与风控断言函数的标准 JSON-RPC 风格调用
"""
import sys
import os
import json
import argparse
import inspect
from decimal import DecimalException

# 「数据导致算术失败」的异常集合。实测 MRO(2026-10-01):
#   DivisionByZero  -> DecimalException -> ZeroDivisionError -> ArithmeticError
#   InvalidOperation-> DecimalException -> ArithmeticError
# 两者不共享单一基类,但 `ArithmeticError` 已覆盖 ZeroDivisionError/OverflowError,
# 故须显式并列 DecimalException。
ArithmeticInputError = (DecimalException, ArithmeticError)

# 以脚本方式运行(python cli.py)时,sys.path[0] 就是本目录。
# 这会让标准库 _strptime 内部的 `import calendar` 命中同目录的
# jev_assertions/calendar.py(与标准库 calendar 同名),导致
# AttributeError: module 'calendar' has no attribute 'day_abbr',
# 使 ny_open_utc 在 CLI 路径下恒定 exit 2(2026-10-01 D1 修复)。
#
# ⚠⚠ 必须用 os.path.samefile,不能用路径**字符串**比较(2026-10-01 D1 第三轮,
#   红队 26d39791 实测前两次加固都失败):
#     第 1 轮 `while _here in sys.path` —— 精确匹配,小写拼写漏;
#     第 2 轮 `normcase(abspath(p)) == normcase(_here)` —— 纯字符串判等,
#              对「同一目录的另一种**路径身份**」完全无效:
#                `\\?\C:\...`(长路径前缀)、`\\.\C:\...`(设备路径前缀)、
#                junction / subst(目录联接)—— 三种都实测让 ny_open_utc 回到 error exit=2。
#              （我第 2 轮写的注释宣称「三者合起来才覆盖得住 `\\?\` 前缀」是**错的**,
#                实测就是漏的那个。别再照抄那句话。）
#     samefile 比较的是**文件系统身份**(会跟随 junction),与拼写无关。
#     本仓尤其现实:DSH 的 profiles 就是 junction 农场。
#
# samefile 对不存在 / 无权限的路径抛 OSError,对非法类型抛 ValueError —— 两种都当 False。
# `__file__` 守卫:exec(open(cli).read()) 这类用法没有 __file__(红队实测 NameError exit=1)。


def _same_dir(p):
    try:
        return os.path.samefile(p, _here)
    except (OSError, ValueError):
        return False


_try_file = globals().get("__file__")
if _try_file:
    _here = os.path.dirname(os.path.abspath(_try_file))
    for _p in [p for p in sys.path if _same_dir(p)]:
        sys.path.remove(_p)

    _pkg_root = os.path.dirname(_here)
    if not any(_same_dir(p) or os.path.abspath(p) == _pkg_root for p in sys.path):
        sys.path.insert(0, _pkg_root)

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
    assert_reverse_split_volume_factor,
)

ASSERTIONS = {
    "tick_floor": assert_tick_floor,
    "assert_tick_floor": assert_tick_floor,
    "tick_ceiling": assert_tick_ceiling,
    "assert_tick_ceiling": assert_tick_ceiling,
    "fractional_tick": assert_fractional_tick,
    "assert_fractional_tick": assert_fractional_tick,
    "lot_step_budget": assert_lot_step_budget,
    "assert_lot_step_budget": assert_lot_step_budget,
    "inverse_contracts": assert_inverse_contracts,
    "assert_inverse_contracts": assert_inverse_contracts,
    "tiered_mm": assert_tiered_mm,
    "assert_tiered_mm": assert_tiered_mm,
    "linear_liq": assert_linear_liq_price,
    "assert_linear_liq_price": assert_linear_liq_price,
    "inverse_liq": assert_inverse_liq_price,
    "assert_inverse_liq_price": assert_inverse_liq_price,
    "collateral_haircut": assert_collateral_haircut,
    "assert_collateral_haircut": assert_collateral_haircut,
    "orderbook_vwap": assert_orderbook_vwap,
    "assert_orderbook_vwap": assert_orderbook_vwap,
    "slippage_impact": assert_almgren_chriss_impact,
    "assert_almgren_chriss_impact": assert_almgren_chriss_impact,
    "amm_constant_product": assert_amm_constant_product,
    "assert_amm_constant_product": assert_amm_constant_product,
    "leverage_fee_buffer": assert_leverage_fee_buffer,
    "assert_leverage_fee_buffer": assert_leverage_fee_buffer,
    "ny_open_utc": assert_ny_open_utc,
    "assert_ny_open_utc": assert_ny_open_utc,
    "clock_monotonic": assert_clock_monotonic,
    "assert_clock_monotonic": assert_clock_monotonic,
    "ex_right_price": assert_ex_right_price,
    "assert_ex_right_price": assert_ex_right_price,
    "forward_adj_log_return_safe": assert_forward_adj_log_return_safe,
    "assert_forward_adj_log_return_safe": assert_forward_adj_log_return_safe,
    "reverse_split_volume_factor": assert_reverse_split_volume_factor,
    "assert_reverse_split_volume_factor": assert_reverse_split_volume_factor,
}

def list_assertions():
    """列出全部可用断言及其参数签名"""
    result = {}
    for name, func in sorted(ASSERTIONS.items()):
        if name.startswith("assert_"):
            continue
        sig = inspect.signature(func)
        result[name] = [p.name for p in sig.parameters.values()]
    return result

def main():
    parser = argparse.ArgumentParser(description="JEV Quantitative Assertions Universal Runner")
    parser.add_argument("--test", "--func", dest="func_name", type=str, help="Assertion function name to run")
    parser.add_argument("--payload", "--args", dest="payload", type=str, help="JSON arguments payload")
    parser.add_argument("--list", action="store_true", help="List all available assertions and parameters")

    args = parser.parse_args()

    if args.list:
        print(json.dumps({"status": "ok", "assertions": list_assertions()}, indent=2))
        return

    if not args.func_name:
        print(json.dumps({"status": "error", "message": "Missing --func or --test argument"}))
        sys.exit(2)

    func = ASSERTIONS.get(args.func_name)
    if not func:
        print(json.dumps({
            "status": "error",
            "message": f"Unknown assertion: {args.func_name}",
            "available": list(list_assertions().keys())
        }))
        # exit 2 = 调用错(命令本身不成立),不是 exit 1。
        # exit 1 专供「断言跑了但答案错」—— 两者同码会让调用方无法区分
        # 「该重算」与「该修命令」,是验证剧场的入口(2026-10-01 A2 修复)。
        sys.exit(2)

    try:
        data = json.loads(args.payload or "{}")
    except Exception as e:
        print(json.dumps({"status": "error", "message": f"Malformed JSON payload: {e}"}))
        sys.exit(2)

    try:
        res = func(**data)
        print(json.dumps({
            "status": "pass",
            "assertion": args.func_name,
            "result": res
        }))
    except AssertionError as ae:
        # fail 分两类:「算错了」与「输入不足以判定」(如订单簿深度不够)。
        # 仓内评测模型早就把后者当独立语义(insufficient_depth),
        # 这里必须分开,否则调用方会对「数据不足」去重算 —— 重算没有意义。
        # 判据:错误文本含「不足 / insufficient」即视为数据不足。
        msg = str(ae) or "Assertion failed"
        insufficient = ("不足" in msg) or ("insufficient" in msg.lower())
        print(json.dumps({
            "status": "insufficient_data" if insufficient else "fail",
            "assertion": args.func_name,
            "error": msg,
        }))
        # exit 3 = 输入不足以判定(2026-10-01 加,红队 46cdb73f 发现 6d)。
        # 与 exit 1(算错了)分开:处置动作不同 —— 1 要重算,3 要补数据。
        sys.exit(3 if insufficient else 1)
    except ArithmeticInputError as ae:
        # 数据错而非命令错(2026-10-01 D3 修复,红队 39f52d8f/78c78922 实证)。
        #
        # 背景:断言库**普遍缺输入域校验**。审计全部 11 处除法运算,分母多数可由输入置 0,
        # 实测 10 个探针有 9 个抛未声明异常(DecimalException / ArithmeticError / ZeroDivisionError),
        # 全被 `except Exception` 归为 status:error + exit 2。
        # 但 exit 2 的语义是「命令本身不成立、该修命令」,而这些全是「你给的数据不对、该重算」——
        # 处置动作恰好相反,调用方会被引向错误的动作。
        #
        # 为什么不逐个加 `assert 分母 > 0`:9 处要逐处判断「0 是合法业务边界还是非法输入」
        # (如 order_size=0 是否算合法空订单),那是业务判断,猜错会把正确行为改坏。
        # 而根因在出口 —— 异常从函数体抛出时,已经能确定「参数绑定成功、函数确实跑起来了」。
        #
        # 参数绑定失败(TypeError)仍归 exit 2,语义不变:那才是「该修命令」。
        msg = f"{type(ae).__name__}: {ae}"
        print(json.dumps({
            "status": "fail",
            "assertion": args.func_name,
            "error": msg,
            "hint": "输入数据导致算术失败(如除数为 0),属数据错而非命令错;该修正数据重跑",
        }))
        sys.exit(1)
    except TypeError as te:
        print(json.dumps({
            "status": "error",
            "assertion": args.func_name,
            "message": f"Parameter mismatch: {te}",
            "expected_params": [p.name for p in inspect.signature(func).parameters.values()]
        }))
        sys.exit(2)
    except Exception as e:
        print(json.dumps({
            "status": "error",
            "assertion": args.func_name,
            "message": str(e)
        }))
        # 断言函数内部抛的非 TypeError 异常属「调用/环境错」,同 exit 2。
        sys.exit(2)

if __name__ == "__main__":
    main()
