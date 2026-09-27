# -*- coding: utf-8 -*-
"""
JEV 量化断言库 - 滑点与执行预算穿透保护
"""
import math
from decimal import Decimal

def assert_orderbook_vwap(order_size, depth_asks, expected_vwap, expected_cost):
    """
    断言深度吃单 VWAP 与总成本
    depth_asks: [{'price': 60000.0, 'size': 2.0}, ...]
    """
    rem = Decimal(str(order_size))
    total_cost = Decimal('0')

    for ask in depth_asks:
        p = Decimal(str(ask['price']))
        s = Decimal(str(ask['size']))
        fill = min(rem, s)
        total_cost += fill * p
        rem -= fill
        if rem <= Decimal('0'):
            break

    assert rem == Decimal('0'), f"[深度不足] 订单未完全成交，剩余 {rem}"
    vwap = total_cost / Decimal(str(order_size))
    
    assert abs(total_cost - Decimal(str(expected_cost))) < Decimal('0.01'), f"[总成本不匹配] 期望={expected_cost}, 实际={total_cost}"
    assert abs(vwap - Decimal(str(expected_vwap))) < Decimal('0.02'), f"[VWAP不匹配] 期望={expected_vwap}, 实际={vwap:.4f}"
    return True

def assert_almgren_chriss_impact(order_val, adv, daily_vol, budget_bps, expect_penetrated):
    """
    断言 Almgren-Chriss 平方根市场冲击模型
    η = σ * sqrt(Volume / ADV) * 0.5
    """
    v = float(order_val)
    a = float(adv)
    sig = float(daily_vol)
    
    impact = sig * math.sqrt(v / a) * 0.5
    impact_bps = impact * 10000.0
    is_p = impact_bps > float(budget_bps)
    
    assert is_p == bool(expect_penetrated), f"[冲击预算断言失败] 期望穿透={expect_penetrated}, 实际冲击={impact_bps:.2f} bps, 预算={budget_bps} bps"
    return True

def assert_amm_constant_product(pool_x, pool_y, dx, fee_rate, expected_dy, expected_price):
    """
    断言 Uniswap V2 恒定乘积 (x * y = k) 交易滑点
    dy = (y * dx * (1 - fee)) / (x + dx * (1 - fee))
    """
    x = Decimal(str(pool_x))
    y = Decimal(str(pool_y))
    d_x = Decimal(str(dx))
    f = Decimal(str(fee_rate))
    
    gamma = Decimal('1') - f
    dy = (y * d_x * gamma) / (x + d_x * gamma)
    eff_p = d_x / dy

    exp_dy = Decimal(str(expected_dy))
    exp_p = Decimal(str(expected_price))

    assert abs(dy - exp_dy) < Decimal('0.0001'), f"[AMM dy不匹配] 期望={exp_dy}, 实际={dy:.6f}"
    assert abs(eff_p - exp_p) < Decimal('0.05'), f"[AMM 有效价格不匹配] 期望={exp_p}, 实际={eff_p:.2f}"
    return True

def assert_leverage_fee_buffer(balance, leverage, taker_fee, target_notional, expect_rejected):
    """
    断言开仓保证金双边手续费垫资不足拒绝
    Required = Notional * (1/Leverage + 2 * TakerFee)
    """
    b = Decimal(str(balance))
    lev = Decimal(str(leverage))
    fee = Decimal(str(taker_fee))
    notional = Decimal(str(target_notional))

    required = notional * (Decimal('1') / lev + Decimal('2') * fee)
    rejected = required > b
    assert rejected == bool(expect_rejected), f"[保证金垫资断言失败] 需求={required}, 可用={b}, 期望拒单={expect_rejected}"
    return True
