# -*- coding: utf-8 -*-
"""参考解:全部 Decimal 精确运算,口径与题面文字逐条对应。

每个函数只接受字符串/整数入参(与题面展示值一致),避免 float 二次误差。
"""
from datetime import date, datetime, timedelta
from decimal import Decimal as D, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, localcontext


def tick_round(price: str, tick: str, side: str) -> str:
    """BUY 向下对齐到 tick 整数倍,SELL 向上对齐。tick 可为非 10 的幂(如 0.05/0.25)。"""
    p, t = D(price), D(tick)
    mode = ROUND_FLOOR if side == "BUY" else ROUND_CEILING
    n = (p / t).to_integral_value(rounding=mode)
    return str((n * t).quantize(t))


def lot_budget(budget: str, price: str, step: str, fee_rate: str, min_notional: str) -> str:
    """含手续费预算下的最大下单量:qty*price*(1+fee) <= budget,qty 为 step 整数倍;
    名义价值 qty*price < min_notional 时返回 0。"""
    b, p, s, f, m = D(budget), D(price), D(step), D(fee_rate), D(min_notional)
    n = (b / (p * (1 + f)) / s).to_integral_value(rounding=ROUND_FLOOR)
    qty = n * s
    if qty * p < m:
        return "0"
    return str(qty.quantize(s))


def orderbook_vwap(size: str, asks: list) -> dict:
    """市价买单逐档吃卖盘。asks=[[price,size],...] 价格升序。深度不足返回 insufficient_depth。"""
    rem, cost = D(size), D(0)
    for price, qty in asks:
        fill = min(rem, D(qty))
        cost += fill * D(price)
        rem -= fill
        if rem == 0:
            break
    if rem > 0:
        return {"status": "insufficient_depth"}
    vwap = (cost / D(size)).quantize(D("0.0001"), rounding=ROUND_HALF_UP)
    return {"total_cost": str(cost.quantize(D("0.01"), rounding=ROUND_HALF_UP)), "vwap": str(vwap)}


def tiered_mm(notional: str, tiers: list) -> dict:
    """阶梯维持保证金(超额累进)。tiers=[[上限, mmr],...];末档上限为 None 表示无穷。
    返回 MM 与所在档速算扣除数 (MM = notional*mmr_k - deduction_k)。"""
    n = D(notional)
    mm, lower, deduction, prev_mmr = D(0), D(0), D(0), D(0)
    cur_deduction = D(0)
    for upper, mmr in tiers:
        r = D(mmr)
        deduction += lower * (r - prev_mmr)
        hi = n if upper is None else min(n, D(upper))
        if n > lower:
            mm += (hi - lower) * r
            cur_deduction = deduction
        prev_mmr = r
        if upper is None or n <= D(upper):
            break
        lower = D(upper)
    q = D("0.01")
    return {"mm": str(mm.quantize(q, rounding=ROUND_HALF_UP)),
            "deduction": str(cur_deduction.quantize(q, rounding=ROUND_HALF_UP))}


def _nth_sunday(year: int, month: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))


def ny_utc_offset_hours(d: date) -> int:
    """美国东部 2007 年起规则:3 月第 2 个周日 ~ 11 月第 1 个周日为 EDT(-4),其余 EST(-5)。
    判定对象为当日 09:30 本地时刻,转换日凌晨 2 点已切换,故按日期比较即可。"""
    start, end = _nth_sunday(d.year, 3, 2), _nth_sunday(d.year, 11, 1)
    return -4 if start <= d < end else -5


def ny_open(day: str, local_time: str = "09:30") -> dict:
    """纽约本地时刻 → UTC 与北京时间(UTC+8,无夏令时),含跨日。"""
    d = date.fromisoformat(day)
    local = datetime.combine(d, datetime.strptime(local_time, "%H:%M").time())
    utc = local - timedelta(hours=ny_utc_offset_hours(d))
    bj = utc + timedelta(hours=8)
    return {"utc": utc.strftime("%Y-%m-%d %H:%M"), "beijing": bj.strftime("%Y-%m-%d %H:%M")}


def ex_rights(pre_close: str, cash_per10: str, bonus_per10: str, rights_per10: str, rights_price: str) -> str:
    """A 股除权除息参考价 = (前收 - 每股现金红利 + 配股价*每股配股比例) / (1 + 每股送转比例 + 每股配股比例),
    四舍五入到 0.01。"""
    c, cash = D(pre_close), D(cash_per10) / 10
    bonus, rights = D(bonus_per10) / 10, D(rights_per10) / 10
    p = (c - cash + D(rights_price) * rights) / (1 + bonus + rights)
    return str(p.quantize(D("0.01"), rounding=ROUND_HALF_UP))


def cagr(start_equity: str, end_equity: str, start_day: str, end_day: str) -> str:
    """年化收益率(%) = ((期末/期初)^(365/自然日数) - 1) * 100,四舍五入到 0.01。"""
    days = (date.fromisoformat(end_day) - date.fromisoformat(start_day)).days
    with localcontext() as ctx:
        ctx.prec = 40
        ratio = D(end_equity) / D(start_equity)
        g = (ratio.ln() * D(365) / D(days)).exp() - 1
        return str((g * 100).quantize(D("0.01"), rounding=ROUND_HALF_UP))


def max_drawdown(equity: list) -> dict:
    """最大回撤(%) = max((峰值 - 其后谷值)/峰值) * 100,四舍五入到 0.01;
    peak/trough 为 0 基下标;多个相同最大回撤取最早出现者。"""
    best, best_peak, best_trough = D(0), 0, 0
    peak_i = 0
    for i, v in enumerate(equity):
        v = D(v)
        if v > D(equity[peak_i]):
            peak_i = i
        dd = (D(equity[peak_i]) - v) / D(equity[peak_i])
        if dd > best:
            best, best_peak, best_trough = dd, peak_i, i
    return {"mdd_pct": str((best * 100).quantize(D("0.01"), rounding=ROUND_HALF_UP)),
            "peak_index": best_peak, "trough_index": best_trough}
