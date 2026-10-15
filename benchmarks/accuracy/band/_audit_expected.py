#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_audit_expected.py —— band_* 四批数值题的 expected 字段独立复核器。

立场:本脚本**只读 question 字段的文字**,按自己的推导重算每题答案,再与 expected 比对。
不使用同目录 solvers_band_*.py 的任何代码,不参考 expected 反推。

实现口径:
- 全部用 decimal.Decimal(精度 60),四舍五入一律 ROUND_HALF_UP(半值远离零进位),
  截断(向零取整)一律 ROUND_DOWN,向上取整 ROUND_CEILING。
- 每题一个独立函数,函数上方注释引用题面关键句。

输出:
  AGREE <id> <值>
  DISAGREE <id> expected=<e> mine=<m>
  AMBIGUOUS <id> <原因>
  NOTE ...        (补充说明,不计入判定)
退出码:
  0 = 全部 AGREE
  1 = 存在 DISAGREE
  2 = 无 DISAGREE 但存在 AMBIGUOUS
"""

import json
import sys
import datetime as _dt
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN, ROUND_CEILING, getcontext
from pathlib import Path

getcontext().prec = 60
try:  # Windows 控制台默认 GBK,强制 UTF-8 输出避免中文注释行乱码
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
D = Decimal
HERE = Path(__file__).resolve().parent

FILES = [
    "band_boundary.jsonl",
    "band_clause.jsonl",
    "band_conditional.jsonl",
    "band_precision.jsonl",
]


# ---------- 数值工具 ----------
def r(x, n):
    """四舍五入(半值进位)到 n 位小数。"""
    return D(x).quantize(D(1).scaleb(-n), rounding=ROUND_HALF_UP)


def rz(x, n):
    """向零截断到 n 位小数(ROUND_DOWN 在 decimal 里就是 toward zero)。"""
    return D(x).quantize(D(1).scaleb(-n), rounding=ROUND_DOWN)


def s(x, n):
    """格式化为 n 位小数字符串。"""
    return f"{r(x, n):.{n}f}"


def i_ceil(x):
    return D(x).to_integral_value(rounding=ROUND_CEILING)


def i_floor(x):
    return D(x).to_integral_value(rounding=ROUND_DOWN)


# =========================================================================
# band_boundary —— 边界闭开/舍入口径
# =========================================================================
def b00():
    # 「分档上限 (50000] 以内(含 50000 USDT)的费率为 0.03%」;本笔名义价值 50000
    return {"fee": s(D(50000) * D("0.0003"), 2)}


def b01():
    # 「tick=0.001…卖单必须向上对齐到不低于原价的最近合法价」;限价 2500.0005
    ticks = i_ceil(D("2500.0005") / D("0.001"))
    return {"price": f"{ticks * D('0.001'):.3f}"}


def b02():
    # 「可下单张数 = 名义价值 ÷ (价格 × 面值乘数),不足 1 张的部分向上取整」
    lots = i_ceil(D(30000) / (D(100) * D(10)))
    return {"lots": f"{lots:.0f}"}


def b03():
    # 「持仓时长 ≥ 30 日的仓位,按名义价值的 0.30%」;持仓 30 日整
    return {"rebate": s(D(100000) * D("0.003"), 2)}


def b04():
    # 「持仓量 ≤ 100 张时费率为 0.0005。费用 = 持仓量 × 当日结算价 × 费率」;100 张,结算价 176.5
    return {"fee": s(D(100) * D("176.5") * D("0.0005"), 4)}


def b05():
    # 「[2 小时, 24 小时) 按 0.02% 计收」;持仓 2h00m00s,名义价值 25000
    return {"fee": s(D(25000) * D("0.0002"), 2)}


def b06():
    # 「先将成交名义价值四舍五入保留到 2 位小数,再用该结果乘以费率 0.0005」;12349.9949
    return {"fee": s(r(D("12349.9949"), 2) * D("0.0005"), 2)}


def b07():
    # 「计息天数 = 实际小时数 ÷ 24 后向上取整」;168 小时;日利率 0.01%,本金 10000
    days = i_ceil(D(168) / D(24))
    return {"interest": s(D(10000) * D("0.0001") * days, 2)}


def b08():
    # 「(10000, 50000] USDT 区间内费率为 0.06%」;名义价值 50000
    return {"fee": s(D(50000) * D("0.0006"), 2)}


def b09():
    # 「[12:00, 16:00) 费率 0.02%」;成交时间 12:00:00,名义价值 150000
    return {"fee": s(D(150000) * D("0.0002"), 2)}


def b10():
    # 「持有 ≥ 30 日免收赎回费(费率 0.00%)」;持有 30 日整,赎回金额 50000
    return {"fee": s(D(50000) * D("0"), 2)}


def b11():
    # 「交易量 ≤ 1000.0000 BTC 时为 0.0005」;账户 1000.0000 BTC,本笔名义价值 80000
    return {"fee": s(D(80000) * D("0.0005"), 2)}


def b12():
    # 「保证金率 ≤ 0.005 时触发强制平仓」;权益 500 / 名义 100000
    ratio = D(500) / D(100000)
    return {"triggered": "yes" if ratio <= D("0.005") else "no"}


def b13():
    # 「先将每笔成交价四舍五入保留到 2 位小数,再按成交量加权计算平均成交价」
    prices = [D("100.005"), D("99.995"), D("101.005")]
    qtys = [D(200), D(100), D(700)]
    num = sum(r(p, 2) * q for p, q in zip(prices, qtys))
    return {"avg_price": s(num / sum(qtys), 2)}


def b14():
    # 「手数 ≤ 5.0000 手时费率为 0.020%;手续费 = 手数 × 开仓价 × 合约乘数 × 费率」
    return {"fee": s(D(5) * D(12000) * D(1) * D("0.0002"), 2)}


# =========================================================================
# band_clause —— 条款口径
# =========================================================================
def c00():
    # 「名义价值 = 张数 × 面值 × 成交价」;30 张 × 0.001 × 60000 / 61000;maker 0.02%;
    # 「单笔四舍五入到 0.01 USDT」
    f_open = r(D(30) * D("0.001") * D(60000) * D("0.0002"), 2)
    f_close = r(D(30) * D("0.001") * D(61000) * D("0.0002"), 2)
    return {"fee_usdt": s(f_open + f_close, 2)}


def c01():
    # 「权重 = 该笔成交额 ÷ 当日总成交额」→ 成交均价 = Σ 价格_i × 权重_i
    prices = [D("30000.00"), D("30090.00"), D("30000.00")]
    qtys = [D(100), D(200), D(120)]
    notional = [p * q for p, q in zip(prices, qtys)]
    total = sum(notional)
    avg = sum(p * n for p, n in zip(prices, notional)) / total
    return {"avg_price": s(avg, 2)}


def c02():
    # 「合计成交 6000 USDT…只有 6 天有成交…只按有成交的天数折算」
    return {"avg_daily_amount": s(D(6000) / D(6), 2)}


def c03():
    # 「4 天有成交…只按有成交的天数折算」;+2.0/-1.5/+3.6/+2.2
    vals = [D("2.0"), D("-1.5"), D("3.6"), D("2.2")]
    return {"avg_daily_return_pct": s(sum(vals) / D(len(vals)), 2)}


def c04():
    # 「名义价值 = 张数 × 面值 × 成交价」;250 张 × 0.1 ETH × 2200
    return {"notional_usdt": s(D(250) * D("0.1") * D(2200), 2)}


def c05():
    # 「利息按单利计收(日利率按一年 365 天折算)」;50000 × 5.4% × 42/365
    return {"interest_usdt": s(D(50000) * D("0.054") * D(42) / D(365), 2)}


def c06():
    # 30 日累计名义 = 1850 × 0.01 × 60000 = 1,110,000 → 「第二档(500000 至 2000000,含两端)0.050%」
    # 本笔 400 张 × 0.01 × 60000 = 240,000 → 手续费,保留 3 位
    cum = D(1850) * D("0.01") * D(60000)
    rate = D("0.00050") if D(500000) <= cum <= D(2000000) else D("0")
    fee = D(400) * D("0.01") * D(60000) * rate
    return {"fee_usdt": f"{r(fee, 3):.3f}"}


def c07():
    # 「只纳入单笔成交名义价值不低于 5000000 USDT 的成交」
    rows = [(D("30000.00"), D(10)), (D("30010.00"), D(20)), (D("30020.00"), D(300)),
            (D("30030.00"), D(30)), (D("30040.00"), D(500)), (D("30050.00"), D(100)),
            (D("30060.00"), D(50))]
    keep = [(p, q) for p, q in rows if p * q >= D(5000000)]
    vwap = sum(p * q for p, q in keep) / sum(q for _, q in keep)
    return {"vwap": s(vwap, 2)}


def c08():
    # 「保证金占用 = 开仓名义价值 ÷ 10」;「保证金占用 + 这一轮开平仓的双边手续费 ≤ 1200」
    price, face, lev, rate, avail = D(60000), D("0.001"), D(10), D("0.0002"), D(1200)
    lots = 0
    while True:
        n = D(lots + 1)
        notional = n * face * price
        cost = notional / lev + notional * rate * 2
        if cost <= avail:
            lots += 1
        else:
            break
    return {"max_lots": f"{lots}"}


def c09():
    # 「年化收益率按单利折算(一年按 365 天计)」;620/50000 × 365/46 × 100
    return {"annualized_pct": s(D(620) / D(50000) * D(365) / D(46) * D(100), 2)}


def c10():
    # 「日界按交易所时区 UTC+8 切分」;取交易所时区 2026-10-01 的成交
    rows = [(_dt.datetime(2026, 10, 1, 15, 40), D(10000), D("0.00050")),
            (_dt.datetime(2026, 10, 1, 17, 20), D(12000), D("0.00020")),
            (_dt.datetime(2026, 10, 1, 18, 0), D(6000), D("0.00050")),
            (_dt.datetime(2026, 10, 2, 3, 30), D(8000), D("0.00020"))]
    total = D(0)
    for t, notional, rate in rows:
        local = t + _dt.timedelta(hours=8)
        if local.date() == _dt.date(2026, 10, 1):
            total += notional * rate
    return {"fee_usdt": f"{r(total, 3):.3f}"}


def c11():
    # 「一律以最高收盘净值为基准」;1.38 → 1.10
    return {"drawdown_pct": s((D("1.38") - D("1.10")) / D("1.38") * D(100), 2)}


def c12():
    # 「年化折算系数为一年 252 个交易日」;日 std 0.10% = 0.0010
    return {"annual_vol_pct": s(D("0.0010") * D(252).sqrt() * D(100), 4)}


def c13():
    # 「只统计已平仓交易」;21/35
    return {"win_rate_pct": s(D(21) / D(35) * D(100), 2)}


def c14():
    # 「按成交额占比分配」;B 1.2 亿 / (4.8 亿 + 1.2 亿)
    return {"weight_pct": s(D("1.2") / (D("4.8") + D("1.2")) * D(100), 2)}


# =========================================================================
# band_conditional —— 条件分支
# =========================================================================
def cd00():
    # 「跨越」= 成交前 ≤ 分档线 且 成交后 > 分档线;80 → 140,跨越 → 全部按高档 4.50 元/手
    before, lots = D(80), D(60)
    after = before + lots
    rate = D("4.50") if (before <= D(100) and after > D(100)) else (
        D("4.50") if before > D(100) else D("3.00"))
    return {"fee": s(lots * rate, 2)}


def cd01():
    # 「若当日 VWAP 不低于当日开盘价,则基准价取 VWAP;否则取开盘与收盘的算术平均」
    o, c, v = D("12.40"), D("12.80"), D("12.36")
    return {"base_price": s(v if v >= o else (o + c) / D(2), 2)}


def cd02():
    # 「若公布的结算价超出停板区间,则按超出方向最近的停板价计算」;6585 > 6520
    lo, hi, settle = D(5880), D(6520), D(6585)
    eff = settle if lo <= settle <= hi else (hi if settle > hi else lo)
    return {"margin": s(D(3) * D(10) * eff * D("0.09"), 2)}


def cd03():
    # 「平今仓…按开仓费率的 3 倍收取」;09:30 开 4 手,14:50 平 4 手
    return {"fee": s(D(4) * D("5.00") * D(3), 2)}


def cd04():
    # 「将财报公布日从样本中剔除」;剔除第 3 个交易日 +2.50%
    vals = [D("1.20"), D("-0.80"), D("0.30"), D("-0.90")]
    return {"avg_return": s(sum(vals) / D(len(vals)), 2)}


def cd05():
    # 「若单笔委托量超过当日该股成交量的 5%,则按当日 VWAP 成交」;78000/1200000 = 6.5%
    qty, vol, close, vwap = D(78000), D(1200000), D("18.55"), D("18.45")
    px = vwap if qty / vol > D("0.05") else close
    return {"commission": s(qty * px * D("0.0003"), 2)}


def cd06():
    # 「[起, 止) 不含止日」;2026-03-02(周一) 起,2026-03-09 止(不含),周末休市
    start, end = _dt.date(2026, 3, 2), _dt.date(2026, 3, 9)
    n, d = 0, start
    while d < end:
        if d.weekday() < 5:
            n += 1
        d += _dt.timedelta(days=1)
    return {"days": f"{n}"}


def cd07():
    # 「最大可开仓手数 = 账户权益 ÷ 单张合约保证金;不足一张向下取整」
    equity = D("50000.00") + D("-1180.00") - D("0.00")
    return {"lots": f"{i_floor(equity / D('3250.00')):.0f}"}


def cd08():
    # 「收益率 = (卖出价 + 每股现金分红 - 买入价)÷ 买入价」
    return {"return_pct": s((D("25.20") + D("0.60") - D("24.00")) / D("24.00") * D(100), 2)}


def cd09():
    # 保证金率 = 14000/200000 = 7% < 8% 触发;7% 不低于强平线 5% → 补足至 8%
    ratio = D("14000.00") / D("200000.00")
    target = D("0.10") if ratio < D("0.05") else D("0.08")
    return {"call_amount": s((target - ratio) * D("200000.00"), 2)}


def cd10():
    # 「若客户委托买入价高于当日 VWAP,则成交价取当日 VWAP」;47.80 > 47.62
    px = D("47.62") if D("47.80") > D("47.62") else D("47.80")
    return {"amount": s(D(6500) * px, 2)}


def cd11():
    # 「估值日为非港股通交易日,则沿用最近一个港股通交易日的汇率」;0.9215
    return {"cny_value": s(D("1200000.00") * D("0.9215"), 2)}


def cd12():
    # 「若区间内全局最高净值出现在全局最低净值之后,则该配对无效,
    #   改取谷值当日及之前出现过的最高净值作为峰值」→ 最高在最低之后(4 > 2)才走替代分支
    nav = [D("1.000"), D("1.120"), D("0.980"), D("1.050"), D("1.200")]
    lo_i = min(range(len(nav)), key=lambda k: nav[k])
    hi_i = max(range(len(nav)), key=lambda k: nav[k])
    if hi_i > lo_i:
        peak = max(nav[: lo_i + 1])
    else:
        peak = nav[hi_i]
    trough = nav[lo_i]
    return {"max_drawdown_pct": s((peak - trough) / peak * D(100), 2)}


def cd13():
    # 「若某成分股当日停牌,则将其从样本中剔除,分母相应减少」
    vals = [D("1260.00"), D("900.00")]
    return {"avg_volume": s(sum(vals) / D(len(vals)), 2)}


def cd14():
    # 「若交易对手为境外机构,则按结算金额全额结算(免征增值税)」;通道费 = 全额 × 0.3%
    return {"net_amount": s(D("106000.00") * (D(1) - D("0.003")), 2)}


# =========================================================================
# band_precision —— 精度/中间量舍入
# =========================================================================
def p00():
    # 「先把成交价格四舍五入到 0.01 再与数量相乘,所得成交额同样四舍五入到 0.01」
    return {"amount": s(r(D("4712.3467"), 2) * D("13.7"), 2)}


def p01():
    # 「美元金额先按绝对值四舍五入到 0.01、再补回负号,之后才与汇率相乘」
    usd = -r(abs(D("-1234.5678")), 2)
    return {"cny_amount": s(usd * D("7.1234"), 2)}


def p02():
    # 「年化收益率(以 % 为单位)先四舍五入到 0.0001,再换算成小数去乘本金」
    pct = r(D("8.37462"), 4)
    return {"profit": s(D("250000.00") * pct / D(100), 2)}


def p03():
    # 「美元金额先四舍五入到 0.01,再乘汇率折算,折算后的人民币金额四舍五入到 0.01」
    return {"cny_amount": s(r(D("12345.6789"), 2) * D("7.1234"), 2)}


def p04():
    # 「限价先向上对齐到不低于原价的最近合法价(禁止用四舍五入)」;tick = 0.05
    ticks = i_ceil(D("1234.567") / D("0.05"))
    return {"notional": s(ticks * D("0.05") * D(37), 2)}


def p05():
    # 「赎回金额 = 份额 × 净值 × (1 − 费率)」;「到账口径要求最终金额向零取整(截断)到 0.01」
    val = D("12345.6789") * D("1.2345") * (D(1) - D("0.0015"))
    return {"redemption": f"{rz(val, 2):.2f}"}


def p06():
    # 「先把每个中间量四舍五入到 0.001,再对舍入后的值求和,合计四舍五入到 0.01」
    total = sum(r(D(v), 3) for v in ("1.2346", "2.3456", "3.4547"))
    return {"total": s(total, 2)}


def p07():
    # 「先把占比(以 % 为单位)四舍五入到 0.1,再换算成小数去乘总资金」
    pct = r(D("33.348"), 1)
    return {"position_value": s(D("1234567.89") * pct / D(100), 2)}


def p08():
    # 「成交价先四舍五入到 0.0001,再乘数量得成交额,手续费 = 成交额 × 费率」
    amount = r(D("0.123456789"), 4) * D(1000000)
    return {"fee": s(amount * D("0.0004"), 2)}


def p09():
    # 「年利率(以 % 为单位)先四舍五入到 0.001…利息 = 本金 × 年利率小数 × 137 ÷ 365」
    rate = r(D("5.6235"), 3)
    return {"interest": s(D("888888.88") * rate / D(100) * D(137) / D(365), 2)}


def p10():
    # 「先把折扣率(以 % 为单位)四舍五入到 0.01,再换算成小数去乘原价」
    rate = r(D("87.654"), 2)
    return {"discounted_price": s(D("1288.88") * rate / D(100), 2)}


def p11():
    # 「先把期初与期末净值各四舍五入到 0.01,再计算涨跌幅」
    beg, end = r(D("9876.500"), 2), r(D("12346.116"), 2)
    return {"change_pct": s((end - beg) / beg * D(100), 2)}


def p12():
    # 「先把单张报价四舍五入到 0.01,再乘合约乘数」
    return {"premium_total": s(r(D("3.456789"), 2) * D(10000), 2)}


def p13():
    # 「最终结果向零取整到 0.01…不做四舍五入」;2158.4321 − 47.6543
    return {"net_pnl": f"{rz(D('2158.4321') - D('47.6543'), 2):.2f}"}


def p14():
    # 「先算出平均每笔费用并四舍五入到 0.0001,再用舍入后的均值乘笔数」
    mean = r(D("1234.56789") / D(137), 4)
    return {"allocated_fee": s(mean * D(137), 2)}


SOLVERS = {
    "band_boundary-20261015-00": b00,
    "band_boundary-20261015-01": b01,
    "band_boundary-20261015-02": b02,
    "band_boundary-20261015-03": b03,
    "band_boundary-20261015-04": b04,
    "band_boundary-20261015-05": b05,
    "band_boundary-20261015-06": b06,
    "band_boundary-20261015-07": b07,
    "band_boundary-20261015-08": b08,
    "band_boundary-20261015-09": b09,
    "band_boundary-20261015-10": b10,
    "band_boundary-20261015-11": b11,
    "band_boundary-20261015-12": b12,
    "band_boundary-20261015-13": b13,
    "band_boundary-20261015-14": b14,
    "band_clause-20261015-00": c00,
    "band_clause-20261015-01": c01,
    "band_clause-20261015-02": c02,
    "band_clause-20261015-03": c03,
    "band_clause-20261015-04": c04,
    "band_clause-20261015-05": c05,
    "band_clause-20261015-06": c06,
    "band_clause-20261015-07": c07,
    "band_clause-20261015-08": c08,
    "band_clause-20261015-09": c09,
    "band_clause-20261015-10": c10,
    "band_clause-20261015-11": c11,
    "band_clause-20261015-12": c12,
    "band_clause-20261015-13": c13,
    "band_clause-20261015-14": c14,
    "band_conditional-20261015-00": cd00,
    "band_conditional-20261015-01": cd01,
    "band_conditional-20261015-02": cd02,
    "band_conditional-20261015-03": cd03,
    "band_conditional-20261015-04": cd04,
    "band_conditional-20261015-05": cd05,
    "band_conditional-20261015-06": cd06,
    "band_conditional-20261015-07": cd07,
    "band_conditional-20261015-08": cd08,
    "band_conditional-20261015-09": cd09,
    "band_conditional-20261015-10": cd10,
    "band_conditional-20261015-11": cd11,
    "band_conditional-20261015-12": cd12,
    "band_conditional-20261015-13": cd13,
    "band_conditional-20261015-14": cd14,
    "band_precision-20261015-00": p00,
    "band_precision-20261015-01": p01,
    "band_precision-20261015-02": p02,
    "band_precision-20261015-03": p03,
    "band_precision-20261015-04": p04,
    "band_precision-20261015-05": p05,
    "band_precision-20261015-06": p06,
    "band_precision-20261015-07": p07,
    "band_precision-20261015-08": p08,
    "band_precision-20261015-09": p09,
    "band_precision-20261015-10": p10,
    "band_precision-20261015-11": p11,
    "band_precision-20261015-12": p12,
    "band_precision-20261015-13": p13,
    "band_precision-20261015-14": p14,
}


def main():
    agree = disagree = ambiguous = 0
    missing = []
    for fname in FILES:
        path = HERE / fname
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            rec = json.loads(raw)
            qid = rec["id"]
            expected = rec["expected"]
            fn = SOLVERS.get(qid)
            if fn is None:
                ambiguous += 1
                print(f"AMBIGUOUS {qid} no-independent-recomputation-available")
                missing.append(qid)
                continue
            mine = fn()
            keys = set(expected) | set(mine)
            bad = [(k, expected.get(k), mine.get(k)) for k in sorted(keys)
                   if expected.get(k) != mine.get(k)]
            if not bad:
                val = " ".join(f"{k}={mine[k]}" for k in sorted(mine))
                print(f"AGREE {qid} {val}")
                agree += 1
            else:
                e_txt = " ".join(f"{k}={e}" for k, e, _ in bad)
                m_txt = " ".join(f"{k2}={m}" for k2, _, m in bad)
                print(f"DISAGREE {qid} expected=<{e_txt}> mine=<{m_txt}>")
                disagree += 1
    print(f"# SUMMARY total={agree + disagree + ambiguous} "
          f"AGREE={agree} DISAGREE={disagree} AMBIGUOUS={ambiguous}")
    # 唯一一处口径分歧提示(不影响判定):
    # clause-01 若改按行业惯例 VWAP(总成交额 ÷ 总成交量 = 12618000 / 420 = 30042.8571)
    # 则得 30042.86(= expected);按题面明示的权重定义 Σ p_i×(成交额_i/总成交额) 得 30042.92。
    print("# NOTE band_clause-20261015-01 题面明示「权重 = 成交额 ÷ 总成交额」→ 30042.92;"
          "若按惯例 VWAP=总成交额/总成交量 → 12618000/420=30042.8571 → 30042.86(= expected)")
    if missing:
        print(f"# MISSING-SOLVER {missing}")
    if disagree:
        return 1
    if ambiguous:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
