# -*- coding: utf-8 -*-
"""
JEV 量化断言库 - Tick 大小截断与步长精度对齐
"""
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING, ROUND_HALF_UP

def assert_tick_floor(raw_price, tick_size, expected):
    """
    断言严格向下截断到 tick 步长 (买单防穿透风控)
    """
    p_raw = Decimal(str(raw_price))
    t_size = Decimal(str(tick_size))
    actual = p_raw.quantize(t_size, rounding=ROUND_FLOOR)
    exp = Decimal(str(expected))
    assert actual == exp, f"[assert_tick_floor 失败] raw={raw_price}, tick={tick_size}, 期望={exp}, 实际={actual}"
    return True

def assert_tick_ceiling(raw_price, tick_size, expected):
    """
    断言严格向上截断到 tick 步长 (卖单防穿透与防零报价)
    """
    p_raw = Decimal(str(raw_price))
    t_size = Decimal(str(tick_size))
    actual = p_raw.quantize(t_size, rounding=ROUND_CEILING)
    exp = Decimal(str(expected))
    assert actual == exp, f"[assert_tick_ceiling 失败] raw={raw_price}, tick={tick_size}, 期望={exp}, 实际={actual}"
    return True

def assert_fractional_tick(raw_price, fraction, expected):
    """
    断言分数步长 (如 1/8 = 0.125, 1/32) 离散对齐
    """
    p_raw = Decimal(str(raw_price))
    f_step = Decimal(str(fraction))
    ticks = round(p_raw / f_step)
    actual = ticks * f_step
    exp = Decimal(str(expected))
    assert actual == exp, f"[assert_fractional_tick 失败] raw={raw_price}, fraction={fraction}, 期望={exp}, 实际={actual}"
    return True

def assert_lot_step_budget(budget, price, lot_step, min_notional, expected_qty):
    """
    断言资金预算下 Lot Size 与最小名义价值过滤后的最大合法下单量
    """
    b = Decimal(str(budget))
    p = Decimal(str(price))
    step = Decimal(str(lot_step))
    min_not = Decimal(str(min_notional))
    
    qty = (b // p // step) * step
    notional = qty * p
    assert notional <= b, f"[预算穿透] 实际名义价值 {notional} 超过预算 {b}"
    if qty > 0:
        assert notional >= min_not, f"[低于最小名义价值] 名义价值 {notional} 小于 {min_not}"
    assert int(qty) == int(expected_qty), f"[LotSize 失败] 期望={expected_qty}, 实际={qty}"
    return True

def assert_inverse_contracts(budget_coin, price_usd, contract_val_usd, expected_contracts):
    """
    断言币本位反向合约张数向下取整
    """
    b = Decimal(str(budget_coin))
    p = Decimal(str(price_usd))
    c_val = Decimal(str(contract_val_usd))
    # 张数 = budget_coin / (contract_val_usd / price_usd) = budget_coin * price_usd / contract_val_usd
    actual = int(b * p // c_val)
    assert actual == int(expected_contracts), f"[反向合约张数失败] 期望={expected_contracts}, 实际={actual}"
    return True
