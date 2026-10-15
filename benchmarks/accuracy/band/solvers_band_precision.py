# -*- coding: utf-8 -*-
"""Independent recomputation for band_precision.jsonl.

Every expected value is re-derived FROM THE QUESTION TEXT (numbers are parsed out
of the question string with regex; `expected` is only read at the very end to
compare).  The trap in this batch is 精度与舍入链: the DEFAULT route (carry full
precision to the end, round once) must disagree with the route the question
specifies (round the intermediate quantity first).

Run:  python -X utf8 -B solvers_band_precision.py
Exit: 0 = all OK, 1 = any MISMATCH.
"""
import json
import os
import re
import sys
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN, ROUND_CEILING

HERE = os.path.dirname(os.path.abspath(__file__))
SUITE = os.path.join(HERE, "band_precision.jsonl")

H = ROUND_HALF_UP
Z = ROUND_DOWN          # toward zero
CE = ROUND_CEILING


def dec(s):
    return Decimal(str(s))


def rnd(x, q):
    """四舍五入到 q"""
    return dec(x).quantize(dec(q), rounding=H)


def trunc(x, q):
    """向零取整到 q"""
    return dec(x).quantize(dec(q), rounding=Z)


def num(text, pattern):
    m = re.search(pattern, text)
    if not m:
        raise ValueError("pattern not found: %s" % pattern)
    return dec(m.group(1))


def precs(text):
    """所有题面写明的精度(四舍五入到 / 取整到 …),按出现顺序"""
    out = [dec(m) for m in re.findall(
        r'(?:四舍五入到|取整到|取整\(截断\)到|截断到)\s*(\d+\.\d+)', text)]
    if not out:
        raise ValueError("no precision stated in question")
    return out


# ---------------------------------------------------------------- per-question
# Each solver returns the value the QUESTION asks for (题面口径), as a Decimal.

def s00(t):
    p = num(t, r'成交价格\s*(-?\d+(?:\.\d+)?)\s*USDT')
    n = num(t, r'成交数量\s*(-?\d+(?:\.\d+)?)\s*张')
    P = precs(t)
    return rnd(rnd(p, P[0]) * n, P[-1])


def s01(t):
    usd = num(t, r'金额为\s*(-?\d+(?:\.\d+)?)\s*美元')
    fx = num(t, r'汇率\s*(-?\d+(?:\.\d+)?)')
    P = precs(t)
    step = rnd(abs(usd), P[0]).copy_negate()      # 按绝对值舍入,再补回负号
    return rnd(step * fx, P[-1])


def s02(t):
    rate = num(t, r'年化收益率为\s*(-?\d+(?:\.\d+)?)%')
    cap = num(t, r'本金\s*(-?\d+(?:\.\d+)?)\s*元')
    P = precs(t)
    return rnd(rnd(rate, P[0]) / 100 * cap, P[-1])


def s03(t):
    usd = num(t, r'应收\s*(-?\d+(?:\.\d+)?)\s*美元')
    fx = num(t, r'汇率\s*(-?\d+(?:\.\d+)?)')
    P = precs(t)
    return rnd(rnd(usd, P[0]) * fx, P[-1])


def s04(t):
    tick = num(t, r'tick=(-?\d+(?:\.\d+)?)')
    px = num(t, r'买入限价\s*(-?\d+(?:\.\d+)?)')
    qty = num(t, r'数量\s*(\d+)\s*张')
    P = precs(t)
    aligned = (px / tick).to_integral_value(rounding=CE) * tick   # 向上对齐
    return rnd(aligned * qty, P[-1])


def s05(t):
    sh = num(t, r'持有份额\s*(-?\d+(?:\.\d+)?)\s*份')
    nav = num(t, r'单位净值\s*(-?\d+(?:\.\d+)?)\s*元')
    fr = num(t, r'赎回费率\s*(-?\d+(?:\.\d+)?)')
    P = precs(t)
    return trunc(sh * nav * (1 - fr), P[-1])       # 向零取整


def s06(t):
    m = re.search(r'分别为\s*(-?\d+(?:\.\d+)?)、(-?\d+(?:\.\d+)?)、(-?\d+(?:\.\d+)?)', t)
    if not m:
        raise ValueError("segments not found")
    segs = [dec(m.group(i)) for i in (1, 2, 3)]
    P = precs(t)
    return rnd(sum(rnd(x, P[0]) for x in segs), P[-1])


def s07(t):
    eq = num(t, r'总资金\s*(-?\d+(?:\.\d+)?)\s*元')
    pct = num(t, r'占比\s*(-?\d+(?:\.\d+)?)%')
    P = precs(t)
    return rnd(rnd(pct, P[0]) / 100 * eq, P[-1])


def s08(t):
    px = num(t, r'成交价\s*(-?\d+(?:\.\d+)?)\s*USDT')
    qty = num(t, r'成交数量\s*(\d+)\s*张')
    fee = num(t, r'手续费率\s*(-?\d+(?:\.\d+)?)')
    P = precs(t)
    return rnd(rnd(px, P[0]) * qty * fee, P[-1])


def s09(t):
    prin = num(t, r'本金\s*(-?\d+(?:\.\d+)?)\s*元')
    ar = num(t, r'年利率\s*(-?\d+(?:\.\d+)?)%')
    days = num(t, r'存期\s*(\d+)\s*天')
    P = precs(t)
    return rnd(prin * (rnd(ar, P[0]) / 100) * days / 365, P[-1])


def s10(t):
    price = num(t, r'原价\s*(-?\d+(?:\.\d+)?)\s*元')
    disc = num(t, r'折扣率\s*(-?\d+(?:\.\d+)?)%')
    P = precs(t)
    return rnd(rnd(disc, P[0]) / 100 * price, P[-1])


def s11(t):
    a = num(t, r'期初净值\s*(-?\d+(?:\.\d+)?)\s*元')
    b = num(t, r'期末净值\s*(-?\d+(?:\.\d+)?)\s*元')
    P = precs(t)
    a2, b2 = rnd(a, P[0]), rnd(b, P[0])
    return rnd((b2 - a2) / a2 * 100, P[-1])


def s12(t):
    mult = num(t, r'合约乘数为\s*(\d+)')
    prem = num(t, r'单张权利金报价\s*(-?\d+(?:\.\d+)?)\s*元')
    P = precs(t)
    return rnd(rnd(prem, P[0]) * mult, P[-1])


def s13(t):
    profit = num(t, r'已实现盈利\s*(-?\d+(?:\.\d+)?)\s*元')
    fee = num(t, r'手续费支出\s*(-?\d+(?:\.\d+)?)\s*元')
    P = precs(t)
    return trunc(profit - fee, P[-1])              # 向零取整


def s14(t):
    tot = num(t, r'费用合计\s*(-?\d+(?:\.\d+)?)\s*元')
    cnt = num(t, r'共成交\s*(\d+)\s*笔')
    P = precs(t)
    return rnd(rnd(tot / cnt, P[0]) * cnt, P[-1])


SOLVERS = {i: globals()["s%02d" % i] for i in range(15)}


def main():
    with open(SUITE, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]

    bad = 0
    for row in rows:
        iid = row["id"]
        idx = int(iid.rsplit("-", 1)[1])
        text = row["question"]
        # numbers are parsed from the question text only; the format block is
        # cut off so its example value "123.45" can never leak in.
        body = text.split("【作答格式")[0]
        try:
            got = SOLVERS[idx](body)
        except Exception as exc:                    # noqa: BLE001
            print("MISMATCH %s expected=%s solver=<error %s>" % (iid, row["expected"], exc))
            bad += 1
            continue
        key = list(row["expected"].keys())[0]
        exp = dec(row["expected"][key])
        if got == exp:
            print("OK %s %s" % (iid, got))
        else:
            print("MISMATCH %s expected=%s solver=%s" % (iid, exp, got))
            bad += 1

    print("TOTAL %d  MISMATCH %d" % (len(rows), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
