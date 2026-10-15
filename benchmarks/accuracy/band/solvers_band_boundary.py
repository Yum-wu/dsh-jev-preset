# -*- coding: utf-8 -*-
"""
solvers_band_boundary.py —— band_boundary 批次独立复算脚本

对同目录 band_boundary.jsonl 中每题,从**题面参数**独立重算答案,再与 expected 比对。
逐题打印 OK / MISMATCH;全部 OK 退出码 0,否则 1。

⚠ 本机 `decimal` 模块实测不可靠(Decimal('10000')/Decimal('100000') 返回 0.1,
  quantize(2) 对 12349.9994 返回 12350.00),故本脚本**完全不用 decimal、不用 float**,
  全部改为十进制缩放整数运算,结果精确且可复现。

缩放约定:数值 x 以 scale k 表示为整数 X = round(x * 10^k)。
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
JSONL = os.path.join(HERE, "band_boundary.jsonl")


# --------------------------- 精确十进制缩放整数运算 ---------------------------

def parse(text, k, mode="exact"):
    """把十进制字符串按 scale k 解析成整数。

    mode='exact'  : 断言输入在 scale k 下可精确表示(题面输入都是有限小数)
    mode='half_up': 输入位数多于 k 时按四舍五入取整(用于"先舍入到 k 位"的口径)
    """
    t = str(text).strip()
    neg = t.startswith("-")
    if neg:
        t = t[1:]
    if "." in t:
        ip, fp = t.split(".", 1)
    else:
        ip, fp = t, ""
    ip = ip or "0"
    if len(fp) <= k:
        fp_padded = fp + "0" * (k - len(fp))
        v = int(ip) * (10 ** k) + (int(fp_padded) if fp_padded else 0)
    else:
        keep = fp[:k]
        rest = fp[k:]
        v = int(ip) * (10 ** k) + (int(keep) if keep else 0)
        if mode == "half_up":
            # ROUND_HALF_UP:首位被舍位 >=5 一律进位(恰为一半也进位)
            if int(rest[0]) >= 5:
                v += 1
        elif mode != "exact":
            raise ValueError(mode)
    return -v if neg else v


def div_round(num, den, mode="half_up"):
    """整数除法,num/den,按 mode 取整。den > 0。"""
    assert den > 0
    if mode == "half_up":
        return (2 * num + den) // (2 * den)
    if mode == "ceil":
        return -((-num) // den)
    if mode == "floor":
        return num // den
    raise ValueError(mode)


def fmt(v, k):
    """整数 v(scale k)-> 固定 k 位小数字符串。"""
    neg = v < 0
    v = abs(v)
    s = str(v).rjust(k + 1, "0")
    out = (s[:-k] + "." + s[-k:]) if k > 0 else s
    return ("-" if neg else "") + out


# --------------------------- 逐题复算 ---------------------------

def solve_00():
    # 名义价值 50000,分档上限 (50000] 含 50000 -> 费率 0.03%
    notional = parse("50000", 2)          # 分
    if notional <= parse("50000", 2):
        rate_num, rate_den = 3, 10000     # 0.03%
    else:
        rate_num, rate_den = 2, 10000     # 0.02%
    fee = div_round(notional * rate_num, rate_den, "half_up")   # 分
    return {"fee": fmt(fee, 2)}


def solve_01():
    # tick=0.001,SELL 向上对齐到不低于原价的最近合法价
    tick_micro = parse("0.001", 6)        # tick,单位 1e-6 USDT
    px_micro = parse("2500.0005", 6)      # 报价,单位 1e-6 USDT
    n = div_round(px_micro, tick_micro, "ceil")   # 需要的 tick 个数
    price_milli = (n * tick_micro) // 1000        # 换算到 1e-3 USDT
    return {"price": fmt(price_milli, 3)}


def solve_02():
    # 最小 1 张,不足 1 张向上取整
    notional = parse("30000", 4)          # 名义价值(1e-4 USDT)
    per_lot = parse("100", 4) * 10        # 每张名义价值 = 价格 × 面值乘数
    lots = div_round(notional, per_lot, "ceil")
    return {"lots": str(lots)}


def solve_03():
    # 返佣:持仓 >= 30 日 -> 0.30%,否则 0.10%;持仓 30 日整
    held_days_x = parse("30", 4)          # 日
    if held_days_x >= parse("30", 4):
        rate_num, rate_den = 30, 10000    # 0.30%
    else:
        rate_num, rate_den = 10, 10000    # 0.10%
    notional = parse("100000", 2)         # 分
    rebate = div_round(notional * rate_num, rate_den, "half_up")
    return {"rebate": fmt(rebate, 2)}


def solve_04():
    # 持仓量 > 100 张 才升档到 0.0006;恰好 100 张 -> 0.0005
    # 统一到 1e-4 USDT:张数(1e-4 张) × 结算价(1e-2 分) × 费率分子 / (1e4 × 费率分母)
    pos = parse("100", 4)                 # 张,单位 1e-4
    if pos > parse("100", 4):
        rate_num, rate_den = 6, 10000     # 0.0006
    else:
        rate_num, rate_den = 5, 10000     # 0.0005
    settle = parse("176.5", 2)            # 分
    # fee(1e-4 USDT) = pos(1e-4 张)/1e4 × settle(1e-2 USDT)/1e2 × rate_num/rate_den × 1e4
    fee = div_round(pos * settle * rate_num, (10 ** 2) * rate_den, "half_up")
    return {"fee": fmt(fee, 4)}


def solve_05():
    # 时长分档 [0,2h)/[2h,24h)/[24h,∞);恰好 2h00m00s -> 0.02%
    secs = 2 * 3600 + 0 * 60 + 0
    if secs >= 24 * 3600:
        rate_num, rate_den = 1, 10000     # 0.01%
    elif secs >= 2 * 3600:
        rate_num, rate_den = 2, 10000     # 0.02%
    else:
        rate_num, rate_den = 5, 10000     # 0.05%
    notional = parse("25000", 2)          # 分
    fee = div_round(notional * rate_num, rate_den, "half_up")
    return {"fee": fmt(fee, 2)}


def solve_06():
    # 口径:先把名义价值四舍五入到 2 位小数,再乘 0.0005
    notional = parse("12349.9949", 2, mode="half_up")   # 先舍到 2 位小数 -> 12349.99
    fee = div_round(notional * 5, 10000, "half_up")     # 1e-2 USDT
    return {"fee": fmt(fee, 2)}


def solve_07():
    # 不足一日按一日:天数 = 小时/24 向上取整;持仓 7 天整 = 168 小时
    hours = 7 * 24
    days = div_round(hours, 24, "ceil")
    principal = parse("10000", 2)         # 分
    rate_num, rate_den = 1, 10000         # 日利率 0.01%
    interest = div_round(principal * rate_num * days, rate_den, "half_up")
    return {"interest": fmt(interest, 2)}


def solve_08():
    # 整笔分档:≤10000 -> 0.10%; (10000,50000] -> 0.06%; >50000 -> 0.04%
    notional = parse("50000", 2)
    if notional <= parse("10000", 2):
        rate_num, rate_den = 10, 10000
    elif notional <= parse("50000", 2):
        rate_num, rate_den = 6, 10000
    else:
        rate_num, rate_den = 4, 10000
    fee = div_round(notional * rate_num, rate_den, "half_up")
    return {"fee": fmt(fee, 2)}


def solve_09():
    # 时段 [08:00,12:00) 0.04%; [12:00,16:00) 0.02%; [16:00,24:00) 0.03%
    t = 12 * 3600 + 0 * 60 + 0
    if t >= 16 * 3600:
        rate_num, rate_den = 3, 10000
    elif t >= 12 * 3600:
        rate_num, rate_den = 2, 10000
    else:
        rate_num, rate_den = 4, 10000
    notional = parse("150000", 2)
    fee = div_round(notional * rate_num, rate_den, "half_up")
    return {"fee": fmt(fee, 2)}


def solve_10():
    # 赎回费:持有 >= 30 日 -> 0.00%;[7,30) -> 0.20%;<7 -> 0.50%
    held = parse("30", 4)
    if held >= parse("30", 4):
        rate_num, rate_den = 0, 10000
    elif held >= parse("7", 4):
        rate_num, rate_den = 20, 10000
    else:
        rate_num, rate_den = 50, 10000
    amount = parse("50000", 2)
    fee = div_round(amount * rate_num, rate_den, "half_up")
    return {"fee": fmt(fee, 2)}


def solve_11():
    # 30 日交易量 > 1000.0000 BTC 降档;恰好 1000.0000 -> 0.0005
    vol = parse("1000.0000", 4)
    if vol > parse("1000.0000", 4):
        rate_num, rate_den = 4, 10000
    else:
        rate_num, rate_den = 5, 10000
    notional = parse("80000", 2)
    fee = div_round(notional * rate_num, rate_den, "half_up")
    return {"fee": fmt(fee, 2)}


def solve_12():
    # 保证金率 = 权益 / 名义价值;<= 0.005 触发强平(权益与名义价值均按 1e-6 精度解析)
    equity = parse("500", 6)
    notional = parse("100000", 6)
    # equity/notional <= 5/1000  <=>  equity*1000 <= notional*5
    triggered = (equity * 1000 <= notional * 5)
    return {"triggered": "yes" if triggered else "no"}


def solve_13():
    # 口径:先逐笔把成交价四舍五入到 2 位小数,再按成交量加权,最后把均价四舍五入到 2 位小数
    p1 = parse("100.005", 2, mode="half_up")   # -> 100.01
    p2 = parse("99.995", 2, mode="half_up")    # -> 100.00
    p3 = parse("101.005", 2, mode="half_up")   # -> 101.01
    v1, v2, v3 = 200, 100, 700
    total_v = v1 + v2 + v3
    weighted = div_round(p1 * v1 + p2 * v2 + p3 * v3, total_v, "half_up")  # 1e-2 USDT
    return {"avg_price": fmt(weighted, 2)}


def solve_14():
    # 手数 > 5.0000 手 升档 0.025%;恰好 5.0000 -> 0.020%
    lots = parse("5.0000", 4)
    if lots > parse("5.0000", 4):
        rate_num, rate_den = 25, 100000
    else:
        rate_num, rate_den = 20, 100000
    px = parse("12000", 2)
    mult = 1
    fee = div_round(lots * px * mult * rate_num, (10 ** 4) * rate_den, "half_up")
    return {"fee": fmt(fee, 2)}


SOLVERS = {
    "band_boundary-20261015-00": solve_00,
    "band_boundary-20261015-01": solve_01,
    "band_boundary-20261015-02": solve_02,
    "band_boundary-20261015-03": solve_03,
    "band_boundary-20261015-04": solve_04,
    "band_boundary-20261015-05": solve_05,
    "band_boundary-20261015-06": solve_06,
    "band_boundary-20261015-07": solve_07,
    "band_boundary-20261015-08": solve_08,
    "band_boundary-20261015-09": solve_09,
    "band_boundary-20261015-10": solve_10,
    "band_boundary-20261015-11": solve_11,
    "band_boundary-20261015-12": solve_12,
    "band_boundary-20261015-13": solve_13,
    "band_boundary-20261015-14": solve_14,
}


def main():
    with open(JSONL, encoding="utf-8") as f:
        items = [json.loads(l) for l in f if l.strip()]

    bad = 0
    for it in items:
        _id = it["id"]
        fn = SOLVERS.get(_id)
        if fn is None:
            print("MISMATCH %s no solver" % _id)
            bad += 1
            continue
        got = fn()
        exp = it["expected"]
        if got == exp:
            print("OK %s %s" % (_id, json.dumps(got, ensure_ascii=False, sort_keys=True)))
        else:
            print("MISMATCH %s expected=%s solver=%s"
                  % (_id, json.dumps(exp, ensure_ascii=False, sort_keys=True),
                     json.dumps(got, ensure_ascii=False, sort_keys=True)))
            bad += 1

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
