# -*- coding: utf-8 -*-
"""
JEV 工业级量化数学与风控标准断言函数库 (JEV Quantitative & Risk Assertions)
"""
from .tick import (
    assert_tick_floor,
    assert_tick_ceiling,
    assert_fractional_tick,
    assert_lot_step_budget,
    assert_inverse_contracts
)
from .margin import (
    assert_tiered_mm,
    assert_linear_liq_price,
    assert_inverse_liq_price,
    assert_collateral_haircut
)
from .slippage import (
    assert_orderbook_vwap,
    assert_almgren_chriss_impact,
    assert_amm_constant_product,
    assert_leverage_fee_buffer
)
from .calendar import (
    assert_ny_open_utc,
    assert_clock_monotonic
)
from .split import (
    assert_ex_right_price,
    assert_forward_adj_log_return_safe,
    assert_reverse_split_volume_factor
)

__all__ = [
    "assert_tick_floor",
    "assert_tick_ceiling",
    "assert_fractional_tick",
    "assert_lot_step_budget",
    "assert_inverse_contracts",
    "assert_tiered_mm",
    "assert_linear_liq_price",
    "assert_inverse_liq_price",
    "assert_collateral_haircut",
    "assert_orderbook_vwap",
    "assert_almgren_chriss_impact",
    "assert_amm_constant_product",
    "assert_leverage_fee_buffer",
    "assert_ny_open_utc",
    "assert_clock_monotonic",
    "assert_ex_right_price",
    "assert_forward_adj_log_return_safe",
    "assert_reverse_split_volume_factor",
]
