# -*- coding: utf-8 -*-
"""独立复算脚本 —— band_clause 题集(20-80% 难度带 · 从句限定漏读)。

每题都从 band_clause.jsonl 的 question 文本重新解析参数并复算,
不读取 expected 字段。逐题打印 `OK <id> <值>` / `MISMATCH <id> expected=<e> solver=<s>`。
退出码:全部 OK = 0;有 MISMATCH = 1。
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP, getcontext

getcontext().prec = 40

HERE = os.path.dirname(os.path.abspath(__file__))
JSONL = os.path.join(HERE, "band_clause.jsonl")


def D(x):
    return Decimal(str(x))


def rnd(x, n):
    """四舍五入(ROUND_HALF_UP)到 n 位小数,返回 Decimal。"""
    return Decimal(x).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP)


def fmt(x, n):
    """按 n 位小数格式化为字符串(保持尾随零)。"""
    return str(rnd(x, n))


def g(pat, t, flags=0):
    m = re.search(pat, t, flags)
    if not m:
        raise ValueError("解析失败: %r" % pat)
    return m.groups()


# ---------------------------------------------------------------- 各题复算

def s00(t):
    """开平仓双边手续费合计;限定在括号里 —— 两笔均为挂单,按 maker 费率。"""
    qty = int(g(r"开多\s*(\d+)\s*张", t)[0])
    face = D(g(r"合约面值\s*([\d.]+)\s*BTC/张", t)[0])
    p_open = D(g(r"开仓成交均价\s*([\d.]+)\s*USDT", t)[0])
    p_close = D(g(r"平仓成交均价\s*([\d.]+)\s*USDT", t)[0])
    rate = D(g(r"maker\)成交\s*([\d.]+)%", t)[0]) / D(100)   # 括号里的 maker 费率
    f_open = rnd(D(qty) * face * p_open * rate, 2)
    f_close = rnd(D(qty) * face * p_close * rate, 2)
    return {"fee_usdt": fmt(f_open + f_close, 2)}


def s01(t):
    """当日成交均价;限定在括号里 —— 权重按成交额(不是按成交量)。"""
    prices = [D(x) for x in g(r"成交价格分别为\s*([\d.]+)、([\d.]+)、([\d.]+)\s*USDT", t)]
    qtys = [D(x) for x in g(r"成交量分别为\s*(\d+)、(\d+)、(\d+)\s*张", t)]
    amounts = [p * q for p, q in zip(prices, qtys)]      # 各笔成交额
    total = sum(amounts)
    # 题面明示权重 = 该笔成交额 ÷ 当日总成交额 ⇒ Σp·(a/Σa) = Σp·a/Σa
    return {"avg_price": fmt(sum(p * a for p, a in zip(prices, amounts)) / total, 2)}


def s02(t):
    """区间日均成交额;限定在括号里 —— 只按有成交的天数折算。"""
    total = D(g(r"合计成交\s*(\d+)\s*USDT", t)[0])
    days = D(g(r"只有\s*(\d+)\s*天有成交", t)[0])
    return {"avg_daily_amount": fmt(total / days, 2)}


def s03(t):
    """区间日均涨跌幅;限定在括号里 —— 只按有成交的天数折算。"""
    rets = [D(x) for x in re.findall(r"([+-][\d.]+)%", t)]
    days = D(g(r"有\s*(\d+)\s*天有成交", t)[0])
    return {"avg_daily_return_pct": fmt(sum(rets) / days, 2)}


def s04(t):
    """平仓成交名义价值;限定在括号里 —— 名义价值 = 张数 × 面值 × 成交价。"""
    qty = D(g(r"开多\s*(\d+)\s*张", t)[0])
    face = D(g(r"每张面值\s*([\d.]+)\s*ETH", t)[0])
    px = D(g(r"以\s*([\d.]+)\s*USDT 全部平仓", t)[0])
    return {"notional_usdt": fmt(qty * face * px, 2)}


def s05(t):
    """单利利息;限定在括号里 —— 日利率按一年 365 天折算。"""
    p = D(g(r"借入\s*(\d+)\s*USDT", t)[0])
    rate = D(g(r"年化利率\s*([\d.]+)%", t)[0]) / D(100)
    days = D(g(r"借期\s*(\d+)\s*天", t)[0])
    basis = D(g(r"一年\s*(\d+)\s*天折算", t)[0])
    return {"interest_usdt": fmt(p * rate * days / basis, 2)}


def s06(t):
    """分档手续费;限定在括号里 —— 名义价值 = 张数 × 面值 × 成交价(不是 张数 × 成交价)。"""
    face = D(g(r"合约面值\s*([\d.]+)\s*BTC/张", t)[0])
    cum_lots = D(g(r"累计成交\s*(\d+)\s*张", t)[0])
    cum_px = D(g(r"期间成交均价\s*([\d.]+)\s*USDT", t)[0])
    sell_lots, sell_px = (D(x) for x in g(r"卖出\s*(\d+)\s*张,成交均价\s*([\d.]+)\s*USDT", t))

    # 分档表(按文本解析)
    b1, r1 = g(r"第一档\(0 至\s*(\d+)\s*USDT,不含上界\)费率\s*([\d.]+)%", t)
    b2lo, b2hi, r2 = g(r"第二档\((\d+)\s*USDT 至\s*(\d+)\s*USDT,含两端\)费率\s*([\d.]+)%", t)
    b3lo, r3 = g(r"第三档\(超过\s*(\d+)\s*USDT\)费率\s*([\d.]+)%", t)

    cum_notional = cum_lots * face * cum_px
    if cum_notional < D(b1):
        rate = D(r1) / D(100)
    elif D(b2lo) <= cum_notional <= D(b2hi):
        rate = D(r2) / D(100)
    else:
        rate = D(r3) / D(100)

    fee = sell_lots * face * sell_px * rate
    return {"fee_usdt": fmt(fee, 3)}


def s07(t):
    """当日 VWAP;限定在括号里 —— 只纳入单笔名义价值不低于门槛的成交。"""
    pairs = [(D(a), D(b)) for a, b in re.findall(r"\((\d+\.\d+), (\d+)\)", t)]
    thr = D(g(r"不低于\s*(\d+)\s*USDT 的成交", t)[0])
    kept = [(p, q) for p, q in pairs if p * q >= thr]
    vwap = sum(p * q for p, q in kept) / sum(q for _, q in kept)
    return {"vwap": fmt(vwap, 2)}


def s08(t):
    """最大可开张数;限定在括号里 —— 保证金占用之外还要扣双边手续费。"""
    margin = D(g(r"可用保证金\s*(\d+)\s*USDT", t)[0])
    face = D(g(r"合约面值\s*([\d.]+)\s*BTC/张", t)[0])
    px = D(g(r"以\s*([\d.]+)\s*USDT 的价格开多", t)[0])
    lev = D(g(r"使用\s*(\d+)\s*倍杠杆", t)[0])
    fee_rate = D(g(r"费率均为成交名义价值的\s*([\d.]+)%", t)[0]) / D(100)

    notional_per = face * px
    cost_per = notional_per / lev + 2 * fee_rate * notional_per   # 保证金 + 双边手续费
    n = int((margin / cost_per).to_integral_value(rounding="ROUND_FLOOR"))
    return {"max_lots": str(n)}


def s09(t):
    """年化收益率(单利);限定在括号里 —— 一年按 365 天计。"""
    p = D(g(r"本金\s*(\d+)\s*USDT", t)[0])
    days = D(g(r"实际占用\s*(\d+)\s*天", t)[0])
    pnl = D(g(r"净收益\s*([\d.]+)\s*USDT", t)[0])
    basis = D(g(r"一年按\s*(\d+)\s*天计", t)[0])
    return {"annualized_pct": fmt(pnl / p * basis / days * 100, 2)}


def s10(t):
    """交易所时区当日手续费合计;限定在括号里 —— 日界按 UTC+8 切分。"""
    tz = D(g(r"日界按交易所时区 UTC\+(\d+) 切分", t)[0])
    target = g(r"在交易所时区的\s*(\d{4}-\d{2}-\d{2})\s*当日", t)[0]
    recs = re.findall(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) UTC,成交名义价值 (\d+) USDT,(\S+?)费率 ([\d.]+)%", t)
    total = D(0)
    for ts, notional, _kind, rate in recs:
        local = datetime.strptime(ts, "%Y-%m-%d %H:%M") + timedelta(hours=int(tz))
        if local.strftime("%Y-%m-%d") == target:
            total += D(notional) * D(rate) / D(100)
    return {"fee_usdt": fmt(total, 3)}


def s11(t):
    """当前回撤;限定在括号里 —— 基准取最高收盘净值(不是最高盘中净值)。"""
    hi_close = D(g(r"历史最高收盘净值\s*([\d.]+)", t)[0])
    cur = D(g(r"当前净值\s*([\d.]+)", t)[0])
    return {"drawdown_pct": fmt((hi_close - cur) / hi_close * 100, 2)}


def s12(t):
    """年化波动率;限定在括号里 —— 年化折算系数为一年 252 个交易日。"""
    sd_pct = D(g(r"标准差为\s*([\d.]+)%", t)[0])
    n = D(g(r"一年\s*(\d+)\s*个交易日", t)[0])
    return {"annual_vol_pct": fmt(sd_pct * n.sqrt(), 4)}


def s13(t):
    """胜率;限定在括号里 —— 只统计已平仓交易。"""
    closed = D(g(r"其中\s*(\d+)\s*笔已平仓", t)[0])
    win = D(g(r"有\s*(\d+)\s*笔盈利", t)[0])
    return {"win_rate_pct": fmt(win / closed * 100, 2)}


def s14(t):
    """成分币权重;限定在括号里 —— 权重按成交额占比(不是成交量占比)。"""
    a_amt = D(g(r"A 成交量\s*[\d.]+\s*万枚、成交额\s*([\d.]+)\s*亿 USDT", t)[0])
    b_amt = D(g(r"B 成交量\s*[\d.]+\s*万枚、成交额\s*([\d.]+)\s*亿 USDT", t)[0])
    return {"weight_pct": fmt(b_amt / (a_amt + b_amt) * 100, 2)}


# 签名(题面中唯一子串) → (键名, 复算函数)
SPECS = [
    ("挂单(maker)成交", "fee_usdt", s00),
    ("成交价格分别为", "avg_price", s01),
    ("合计成交 6000 USDT", "avg_daily_amount", s02),
    ("这 4 天的日涨跌幅分别为", "avg_daily_return_pct", s03),
    ("ETH-USDT 永续合约", "notional_usdt", s04),
    ("借期 42 天", "interest_usdt", s05),
    ("最近 30 日累计成交名义价值", "fee_usdt", s06),
    ("只纳入单笔成交名义价值不低于", "vwap", s07),
    ("可用保证金 1200 USDT", "max_lots", s08),
    ("实际占用 46 天", "annualized_pct", s09),
    ("日界按交易所时区 UTC+8 切分", "fee_usdt", s10),
    ("历史最高盘中净值", "drawdown_pct", s11),
    ("年化折算系数为一年 252 个交易日", "annual_vol_pct", s12),
    ("笔仍在持仓", "win_rate_pct", s13),
    ("两只成分币构成", "weight_pct", s14),
]


def solve_one(question):
    for sig, key, fn in SPECS:
        if sig in question:
            return fn(question)
    raise ValueError("没有匹配到签名: %s" % question[:60])


def main():
    with open(JSONL, encoding="utf-8") as fh:
        items = [json.loads(line) for line in fh if line.strip()]

    bad = 0
    for it in items:
        exp = it["expected"]
        try:
            got = solve_one(it["question"])
        except Exception as exc:  # noqa: BLE001
            print("MISMATCH %s expected=%s solver=ERROR:%s" % (it["id"], exp, exc))
            bad += 1
            continue
        if got == exp:
            print("OK %s %s" % (it["id"], json.dumps(got, ensure_ascii=False, sort_keys=True)))
        else:
            print("MISMATCH %s expected=%s solver=%s"
                  % (it["id"], json.dumps(exp, ensure_ascii=False, sort_keys=True),
                     json.dumps(got, ensure_ascii=False, sort_keys=True)))
            bad += 1

    print("TOTAL %d  MISMATCH %d" % (len(items), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
