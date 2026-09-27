# -*- coding: utf-8 -*-
"""
JEV 断言库命令行调用入口
"""
import sys
import json
import argparse
from jev_assertions import (
    assert_tick_floor,
    assert_tick_ceiling,
    assert_tiered_mm,
    assert_linear_liq_price,
    assert_almgren_chriss_impact
)

def main():
    parser = argparse.ArgumentParser(description="JEV Quantitative Assertions Runner")
    parser.add_argument("--test", type=str, required=True, help="Assertion type to run")
    parser.add_argument("--payload", type=str, required=True, help="JSON payload")

    args = parser.parse_args()
    data = json.loads(args.payload)

    if args.test == "tick_floor":
        assert_tick_floor(data["raw_price"], data["tick_size"], data["expected"])
        print(json.dumps({"status": "pass", "assertion": "tick_floor"}))
    elif args.test == "tiered_mm":
        assert_tiered_mm(data["notional"], data["tiers"], data["expected_mm"], data["expected_deduction"])
        print(json.dumps({"status": "pass", "assertion": "tiered_mm"}))
    elif args.test == "linear_liq":
        assert_linear_liq_price(data["balance"], data["size"], data["entry_price"], data["mmr"], data["fee_rate"], data["expected_liq"])
        print(json.dumps({"status": "pass", "assertion": "linear_liq"}))
    elif args.test == "slippage_impact":
        assert_almgren_chriss_impact(data["order_val"], data["adv"], data["daily_vol"], data["budget_bps"], data["expect_penetrated"])
        print(json.dumps({"status": "pass", "assertion": "slippage_impact"}))
    else:
        print(json.dumps({"status": "error", "message": f"Unknown assertion: {args.test}"}))
        sys.exit(1)

if __name__ == "__main__":
    main()
