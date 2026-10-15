# -*- coding: utf-8 -*-
"""独立复核 band_conservation 的 expected —— 作者:大肥鱼(与造题路无关的第三方实现)
每题用与造题 solver 无关的写法重算,只读 jsonl 的 expected 做对比。
"""
import json, sys
from fractions import Fraction as F
from decimal import Decimal, ROUND_HALF_UP
from itertools import product

P = r"C:\Users\Yum\Desktop\DeepSeekHarness\plugins\dsh-jev-preset\benchmarks\accuracy\band\band_conservation.jsonl"


def r4(x):
    if isinstance(x, F):
        d = Decimal(x.numerator) / Decimal(x.denominator)
    else:
        d = Decimal(str(x))
    return str(d.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def main():
    rows = [json.loads(l) for l in open(P, encoding="utf-8") if l.strip()]
    got = {}

    # 00 盐水 800kg 盐 4% -> 5%,失水
    salt = F(800) * F(4, 100)
    got["band_conservation-20261015-00"] = r4(F(800) - salt / F(5, 100))
    # 01 600kg 铜 25% -> 40%,加铜 x: (150+x)/(600+x)=0.4
    x = (F(4, 10) * 600 - 150) / (1 - F(4, 10))
    got["band_conservation-20261015-01"] = r4(x)
    # 02 1200 USD *7.2 /7.5
    got["band_conservation-20261015-02"] = r4(F(1200) * F(72, 10) / F(75, 10))
    # 03 权益2400 / 12%
    got["band_conservation-20261015-03"] = r4(F(2400) / F(12, 100))
    # 04 (250*0.99 - 200*1.01)/(200*1.01)*100
    buy = F(200) * F(101, 100)
    sell = F(250) * F(99, 100)
    got["band_conservation-20261015-04"] = r4((sell - buy) / buy * 100)
    # 05 226/1.13
    got["band_conservation-20261015-05"] = r4(F(226) / F(113, 100))
    # 06 10mol 氧20%,注入 x: (2+x)/(10+x)=0.5
    x = (F(1, 2) * 10 - 2) / (1 - F(1, 2))
    got["band_conservation-20261015-06"] = r4(x)
    # 07 (300*.2+200*.45)/500*100
    got["band_conservation-20261015-07"] = r4((F(300) * F(2, 10) + F(200) * F(45, 100)) / 500 * 100)
    # 08 24 / (12/6 + 12/12)
    got["band_conservation-20261015-08"] = r4(F(24) / (F(12, 6) + F(12, 12)))
    # 09 0.9^3
    got["band_conservation-20261015-09"] = r4(F(9, 10) ** 3 * 100)
    # 10 4a+7b=53 最大化 a+b —— 暴力
    best = max(a + b for a in range(60) for b in range(60) if 4 * a + 7 * b == 53)
    got["band_conservation-20261015-10"] = str(best)
    # 11 托盘 120x80, 50x30 可旋转 —— 面积上界 + 构造
    area_max = (120 * 80) // (50 * 30)
    construct = 6  # 4 个 30x50 横排(占 120x50) + 2 个 50x30(占 100x30)
    assert construct <= area_max, (construct, area_max)
    got["band_conservation-20261015-11"] = str(construct)
    # 12 阶梯电价 预算200
    rem = F(200) - F(100) * F(5, 10)
    assert rem > 0
    mid = F(200) * F(6, 10)
    if rem >= mid:
        got["band_conservation-20261015-12"] = r4(F(300) + (rem - mid) / F(8, 10))
    else:
        got["band_conservation-20261015-12"] = r4(F(100) + rem / F(6, 10))
    # 13 单价30 满100减30 每单一张 预算400 —— 暴力枚举每单件数
    best = 0
    for n1 in range(0, 15):
        for n2 in range(0, 15):
            for n3 in range(0, 15):
                for n4 in range(0, 15):
                    for n5 in range(0, 15):
                        ns = [n1, n2, n3, n4, n5]
                        cost = sum(30 * n - (30 if 30 * n >= 100 else 0) for n in ns)
                        if cost <= 400:
                            best = max(best, sum(ns))
    got["band_conservation-20261015-13"] = str(best)
    # 14 每张 5 保证金 + 0.05 手续费, 950 可用 —— 暴力
    k = 0
    while (k + 1) * (F(5) + F(100) * F(5, 10000)) <= 950:
        k += 1
    got["band_conservation-20261015-14"] = str(k)
    # 15 首重12/1kg, 续重每0.5kg 3元, 预算60 —— 暴力
    best = F(0)
    w = F(0)
    while w <= 20:
        fee = 12 if w <= 1 else 12 + 3 * (int(((w - 1) / F(1, 2)).__ceil__()))
        if fee <= 60:
            best = max(best, w)
        w += F(1, 2)
    got["band_conservation-20261015-15"] = r4(best)
    # 16 480 分钟, 最多几场 —— 暴力子集
    durs = [150, 140, 130, 120, 60, 60, 60, 60]
    best = 0
    for mask in range(1 << len(durs)):
        s = sum(durs[i] for i in range(len(durs)) if mask >> i & 1)
        if s <= 480:
            best = max(best, bin(mask).count("1"))
    got["band_conservation-20261015-16"] = str(best)
    # 17 每笔 <=500 USDT, 价 60.00, 100 单位
    per = 500 // 60
    import math
    got["band_conservation-20261015-17"] = str(math.ceil(100 / per))
    # 18 电梯 500kg —— 暴力
    ws = [85, 78, 92, 66, 74, 88, 95, 60]
    best = 0
    for mask in range(1 << len(ws)):
        s = sum(ws[i] for i in range(len(ws)) if mask >> i & 1)
        if s <= 500:
            best = max(best, bin(mask).count("1"))
    got["band_conservation-20261015-18"] = str(best)
    # 19 鸽巢: 各色取 5 个的坏集合 + 1
    got["band_conservation-20261015-19"] = str(5 + 5 + 5 + 1)

    bad = 0
    for r in rows:
        e = r["expected"]
        key = list(e.keys())[0]
        exp = e[key]
        mine = got[r["id"]]
        ok = (str(exp) == str(mine))
        if not ok:
            bad += 1
        print(("OK  " if ok else "BAD ") + r["id"] + "  expected=" + str(exp) + "  mine=" + str(mine))
    print("# summary: cases=%d bad=%d verdict=%s" % (len(rows), bad, "PASS" if bad == 0 else "FAIL"))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
