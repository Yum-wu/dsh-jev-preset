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

# 确保包根目录在 sys.path 中
_pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_root not in sys.path:
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
        sys.exit(1)

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
        print(json.dumps({
            "status": "fail",
            "assertion": args.func_name,
            "error": str(ae) or "Assertion failed"
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
        sys.exit(1)

if __name__ == "__main__":
    main()
