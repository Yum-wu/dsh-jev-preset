# -*- coding: utf-8 -*-
"""
JEV 量化断言库 - 阶梯维持保证金与强平穿仓推导
"""
from decimal import Decimal

def assert_tiered_mm(notional, tiers, expected_mm, expected_deduction):
    """
    断言多档阶梯维持保证金(MM)与速算扣除数(Quick Deduction)
    tiers: [{'tier': 1, 'max_notional': 50000, 'mmr': 0.005}, ...]
    """
    tot = Decimal(str(notional))
    mm_acc = Decimal('0')
    last_max = Decimal('0')
    curr_mmr = Decimal('0')

    for t in tiers:
        t_max = Decimal(str(t['max_notional']))
        t_mmr = Decimal(str(t['mmr']))
        if tot > last_max:
            tier_chunk = min(tot, t_max) - last_max
            mm_acc += tier_chunk * t_mmr
            curr_mmr = t_mmr
        last_max = t_max

    # 速算扣除数 = 总名义价值 * 当前档位最高MMR - 真实阶梯累进MM
    deduction = tot * curr_mmr - mm_acc
    
    exp_mm = Decimal(str(expected_mm))
    exp_ded = Decimal(str(expected_deduction))

    assert abs(mm_acc - exp_mm) < Decimal('0.0001'), f"[阶梯MM错误] 期望={exp_mm}, 实际={mm_acc}"
    assert abs(deduction - exp_ded) < Decimal('0.0001'), f"[速算扣除数错误] 期望={exp_ded}, 实际={deduction}"
    return True

def assert_linear_liq_price(balance, size, entry_price, mmr, fee_rate, expected_liq):
    """
    断言正向(USDT本位)合约全仓多头强平价格
    P_liq = (entry * size - balance) / (size * (1 - mmr - fee))
    """
    b = Decimal(str(balance))
    s = Decimal(str(size))
    e = Decimal(str(entry_price))
    m = Decimal(str(mmr))
    f = Decimal(str(fee_rate))

    p_liq = (e * s - b) / (s * (Decimal('1') - m - f))
    exp_p = Decimal(str(expected_liq))
    assert abs(p_liq - exp_p) < Decimal('0.02'), f"[正向强平价失败] 期望={exp_p}, 实际={p_liq:.4f}"
    return True

def assert_inverse_liq_price(balance_coin, contracts, face_val, entry_price, mmr, expected_liq):
    """
    断言反向(币本位)合约空头强平价格 (双曲线非线性方程)
    P_liq = (contracts * face_val * (1 + mmr)) / (balance_coin + (contracts * face_val / entry_price))
    """
    b = Decimal(str(balance_coin))
    c = Decimal(str(contracts))
    fv = Decimal(str(face_val))
    e = Decimal(str(entry_price))
    m = Decimal(str(mmr))

    p_liq = (c * fv * (Decimal('1') + m)) / (b + (c * fv / e))
    exp_p = Decimal(str(expected_liq))
    assert abs(p_liq - exp_p) < Decimal('0.02'), f"[反向强平价失败] 期望={exp_p}, 实际={p_liq:.4f}"
    return True

def assert_collateral_haircut(assets, expected_nominal, expected_adjusted):
    """
    断言多资产抵押品折扣率(Haircut)后的有效美金净值
    assets: [{'amount': 10000, 'price': 1.0, 'haircut': 1.0}, ...]
    """
    nom = sum(Decimal(str(a['amount'])) * Decimal(str(a['price'])) for a in assets)
    adj = sum(Decimal(str(a['amount'])) * Decimal(str(a['price'])) * Decimal(str(a['haircut'])) for a in assets)

    assert abs(nom - Decimal(str(expected_nominal))) < Decimal('0.01'), f"[名义价值不匹配] 期望={expected_nominal}, 实际={nom}"
    assert abs(adj - Decimal(str(expected_adjusted))) < Decimal('0.01'), f"[折算权益不匹配] 期望={expected_adjusted}, 实际={adj}"
    return True
