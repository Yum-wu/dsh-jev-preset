# -*- coding: utf-8 -*-
"""
solvers_band_conditional.py —— band_conditional 批次独立复算脚本

对 band/band_conditional.jsonl 中每题,从**题面参数**独立重算答案,再与 expected 比对。
逐题打印 OK / MISMATCH;全部 OK 退出码 0,否则 1。

本批陷阱形态 = **单条件分支**:每题题面给出 1 个明写且可判定的条件,两分支公式/口径不同。
每条 solve_* 里把该条件写成显式布尔量(注释标出题面出处),分支取错必然得不同数值。

所有金额/比率计算一律用 Decimal + ROUND_HALF_UP,避免二进制浮点误差。
"""
import datetime
import json
import os
import sys
from decimal import Decimal, ROUND_HALF_UP

HERE = os.path.dirname(os.path.abspath(__file__))
JSONL = os.path.join(HERE, "band_conditional.jsonl")


def D(x):
    return Decimal(str(x))


def q(x, n):
    """四舍五入(ROUND_HALF_UP)保留 n 位小数。"""
    return D(x).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP)


def s(x, n):
    """格式化:固定 n 位小数字符串。"""
    return str(q(x, n))


# --------------------------------------------------------------------------
# 逐题复算
# --------------------------------------------------------------------------

def solve_00():
    # 条件:本笔成交是否使持仓跨越 100 手分档线(成交前 <=100 且成交后 >100)
    before, add, line = D("80"), D("60"), D("100")
    crossed = (before <= line) and (before + add > line)
    rate = D("4.50") if crossed else D("3.00")   # 跨越 -> 全部手数按高档
    return {"fee": s(add * rate, 2)}


def solve_01():
    # 条件:VWAP 是否不低于开盘价
    op, cl, vwap = D("12.40"), D("12.80"), D("12.36")
    base = vwap if vwap >= op else (op + cl) / D("2")
    return {"base_price": s(base, 2)}


def solve_02():
    # 条件:公布结算价是否落在停板区间内(含端点)
    lower, upper, settle = D("5880"), D("6520"), D("6585")
    if lower <= settle <= upper:
        px = settle
    else:
        px = upper if settle > upper else lower
    return {"margin": s(px * D("10") * D("3") * D("0.09"), 2)}


def solve_03():
    # 条件:该笔平仓是否为平今仓(开仓与平仓在同一交易日)
    lots, open_fee = D("4"), D("5.00")
    is_today_close = True            # 题面:当日 09:30 开仓、当日 14:50 平仓
    rate = open_fee * D("3") if is_today_close else open_fee
    return {"fee": s(lots * rate, 2)}


def solve_04():
    # 条件:区间内是否包含财报公布日(第 3 个交易日)
    rets = [D("1.20"), D("-0.80"), D("2.50"), D("0.30"), D("-0.90")]
    report_idx = 2
    kept = [r for i, r in enumerate(rets) if i != report_idx]
    return {"avg_return": s(sum(kept) / D(len(kept)), 2)}


def solve_05():
    # 条件:单笔委托量是否超过当日成交量的 5%
    day_vol, qty = D("1200000"), D("78000")
    close, vwap = D("18.55"), D("18.45")
    px = vwap if (qty / day_vol) > D("0.05") else close
    return {"commission": s(qty * px * D("0.0003"), 2)}


def solve_06():
    # 条件:区间写法是左闭右开还是闭区间
    start = datetime.date(2026, 3, 2)
    end = datetime.date(2026, 3, 9)
    assert start.weekday() == 0, "题面声明 2026-03-02 为周一,此处自校"
    right_closed = False             # 题面写作 [2026-03-02, 2026-03-09)
    last = end if right_closed else end - datetime.timedelta(days=1)
    n = 0
    d = start
    while d <= last:
        if d.weekday() < 5:          # 周六周日休市
            n += 1
        d += datetime.timedelta(days=1)
    return {"days": str(n)}


def solve_07():
    # 条件:权益 ÷ 单张保证金 不是整数时,向下取整(不足一张不计)
    equity = D("50000.00") + D("-1180.00") - D("0.00")
    per_lot = D("3250.00")
    raw = equity / per_lot
    lots = raw.to_integral_value(rounding="ROUND_FLOOR")
    return {"lots": str(lots)}


def solve_08():
    # 条件:持有期内是否实施过现金分红
    buy, sell, div = D("24.00"), D("25.20"), D("0.60")
    has_dividend = True              # 题面:每股派发现金红利 0.60 元(已实施)
    gain = (sell + div - buy) if has_dividend else (sell - buy)
    return {"return_pct": s(gain / buy * D("100"), 2)}


def solve_09():
    # 条件:当前保证金率是否低于强平线 5%
    mv, equity = D("200000.00"), D("14000.00")
    ratio = equity / mv
    maint, liq = D("0.08"), D("0.05")
    if ratio >= maint:
        amt = D("0")
    else:
        target = D("0.10") if ratio < liq else maint
        amt = (target - ratio) * mv
    return {"call_amount": s(amt, 2)}


def solve_10():
    # 条件:委托买入价是否高于当日 VWAP
    order_px, vwap, qty = D("47.80"), D("47.62"), D("6500")
    px = vwap if order_px > vwap else order_px
    return {"amount": s(px * qty, 2)}


def solve_11():
    # 条件:估值日是否为港股通交易日
    hkd = D("1200000.00")
    fx_prev, fx_today = D("0.9215"), D("0.9188")
    is_hk_connect_day = False        # 题面:估值日为非港股通交易日
    fx = fx_today if is_hk_connect_day else fx_prev
    return {"cny_value": s(hkd * fx, 2)}


def solve_12():
    # 条件:全局最高净值是否出现在全局最低净值之前(否则该配对无效)
    nav = [D("1.000"), D("1.120"), D("0.980"), D("1.050"), D("1.200")]
    hi, lo = max(nav), min(nav)
    hi_i, lo_i = nav.index(hi), nav.index(lo)
    if hi_i < lo_i:
        peak, trough = hi, lo
    else:
        peak = max(nav[:lo_i + 1])   # 取谷值当日及之前的最高净值
        trough = lo
    return {"max_drawdown_pct": s((peak - trough) / peak * D("100"), 2)}


def solve_13():
    # 条件:某成分股当日是否停牌(停牌 -> 从样本剔除)
    vols = [D("1260.00"), None, D("900.00")]   # B 股停牌
    kept = [v for v in vols if v is not None]
    return {"avg_volume": s(sum(kept) / D(len(kept)), 2)}


def solve_14():
    # 条件:交易对手是否为境外机构(境外 -> 全额结算,不做价税分离)
    gross = D("106000.00")
    is_offshore = True               # 题面:交易对手为境外机构
    base = gross if is_offshore else gross / D("1.06")
    return {"net_amount": s(base * (D("1") - D("0.003")), 2)}


SOLVERS = {
    "band_conditional-20261015-00": solve_00,
    "band_conditional-20261015-01": solve_01,
    "band_conditional-20261015-02": solve_02,
    "band_conditional-20261015-03": solve_03,
    "band_conditional-20261015-04": solve_04,
    "band_conditional-20261015-05": solve_05,
    "band_conditional-20261015-06": solve_06,
    "band_conditional-20261015-07": solve_07,
    "band_conditional-20261015-08": solve_08,
    "band_conditional-20261015-09": solve_09,
    "band_conditional-20261015-10": solve_10,
    "band_conditional-20261015-11": solve_11,
    "band_conditional-20261015-12": solve_12,
    "band_conditional-20261015-13": solve_13,
    "band_conditional-20261015-14": solve_14,
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
