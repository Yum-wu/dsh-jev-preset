# -*- coding: utf-8 -*-
"""
JEV 量化断言库 - 复权因子与除权除息数值守恒
"""
import math
from decimal import Decimal

def assert_ex_right_price(pre_close, bonus_per_10, transfer_per_10, dividend_per_10, expected_ex):
    """
    断言除权除息基准价
    P_ex = (pre_close - dividend_per_share) / (1 + (bonus + transfer)/10)
    """
    c = Decimal(str(pre_close))
    d = Decimal(str(dividend_per_10)) / Decimal('10')
    e = (Decimal(str(bonus_per_10)) + Decimal(str(transfer_per_10))) / Decimal('10')

    p_ex = (c - d) / (Decimal('1') + e)
    exp = Decimal(str(expected_ex))

    assert abs(p_ex - exp) < Decimal('0.001'), f"[除权价不匹配] 期望={exp}, 实际={p_ex:.4f}"
    return True

def assert_forward_adj_log_return_safe(pre_close, ex_price, hist_price):
    """
    断言乘法前复权因子不会产生负价格，确保对数收益率有效
    """
    c = Decimal(str(pre_close))
    ex = Decimal(str(ex_price))
    mult = ex / c

    adj_hist = Decimal(str(hist_price)) * mult
    assert adj_hist > Decimal('0'), f"[前复权价格非正] 历史价格复权后为 {adj_hist}，导致对数收益率 NaN"
    
    # 验证对数计算安全
    log_ret = math.log(float(adj_hist))
    assert not math.isnan(log_ret) and not math.isinf(log_ret), f"[收益率溢出] 对数收益率为 {log_ret}"
    return True

def assert_reverse_split_volume_factor(split_ratio, expected_price_factor, expected_vol_factor):
    """
    断言缩股(Reverse Split)下价格因子与成交量因子的反向守恒律
    """
    r = Decimal(str(split_ratio))
    price_f = Decimal('1') / r
    vol_f = r

    assert price_f == Decimal(str(expected_price_factor)), f"[价格调整因子错误] 期望={expected_price_factor}, 实际={price_f}"
    assert vol_f == Decimal(str(expected_vol_factor)), f"[成交量调整因子错误] 期望={expected_vol_factor}, 实际={vol_f}"
    return True
