# -*- coding: utf-8 -*-
"""参考解:全部 Decimal 精确运算,口径与题面文字逐条对应。

每个函数只接受字符串/整数入参(与题面展示值一致),避免 float 二次误差。
"""
from datetime import date, datetime, timedelta
from decimal import (Decimal as D, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP,
                    DecimalException, localcontext)


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
    """年化收益率(%) = ((期末/期初)^(365/自然日数) - 1) * 100,四舍五入到 0.01。

    ⚠ 2026-10-01 修正(附录 B1),**且原说明是错的,一并更正**(红队 6c40869b 实测):

      ❌ 原注释说「`Decimal.exp()` 越界」—— **机制描述错误**。
         `Decimal` 的默认 `Emax = 999999`,`exp()` 实际上**从不溢出**。
         实测:days=2 时 `exp()` 正常返回 40 位有效数字,days=1 才炸。
         真正抛 `InvalidOperation` 的是 **`quantize`** ——
         在 `ctx.prec = 40` 下,当结果需要**超过 40 位有效数字**时,`quantize` 抛错。

      ❌ 原注释说「区间过短(days<10)导致年化溢出」—— **边界划错了**。
         边界由**结果的数字位数**决定,与 `days` 无关。
         反例(红队实测):days=1 但 ratio=1.0001 时,**不抛错**,静默返回 `3.72`。

      ✅ 现在的说法:当结果位数超过 `prec` 时抛错,收口成可读的 `ValueError`。
         异常类型从 `InvalidOperation`(信息量为零)变为可读错误,
         这一点是真实改进。

    价值声明(必须诚实 —— 红队 R13 实测):
      出题器 `cases.py:118-119` 用 `randint(120, 1800)` 生成天数,
      **真跑 0/1200 题命中本函数的任何异常路径**。
      所以本函数是 cagr 题的判分基准这一点**不构成本次修改的理由** ——
      它是**防御性**改进,对已确立结论(24/30→30/30 等)零影响。
    """
    d0 = date.fromisoformat(start_day)
    d1 = date.fromisoformat(end_day)
    days = (d1 - d0).days
    if days <= 0:
        raise ValueError(
            f"cagr: 区间非法(end_day={end_day} 未晚于 start_day={start_day},days={days});"
            f"年化需要至少 1 天")
    if D(start_equity) == 0:
        raise ValueError(f"cagr: 期初权益为 0,比值无定义")
    with localcontext() as ctx:
        ctx.prec = 40
        # ⚠ 整段算术都在 try 内:Decimal 的 InvalidOperation 既可能来自 ln()/exp(),
        #    也可能在 `localcontext` 退出时做精度校验时抛出(初版只包住 exp(),
        #    异常从 ctx 边界直接穿透 —— **以为捕到了,其实没捕到**)。
        try:
            ratio = D(end_equity) / D(start_equity)
            if ratio <= 0:
                raise ValueError(f"cagr: 期末/期初 = {ratio} 非正,对数无定义")
            g = (ratio.ln() * D(365) / D(days)).exp() - 1
            return str((g * 100).quantize(D("0.01"), rounding=ROUND_HALF_UP))
        except (DecimalException, OverflowError, ArithmeticError) as e:
            # 真正触发点是 quantize:结果位数超过 ctx.prec(40)时抛 InvalidOperation。
            # (初版注释归因于 exp() 越界,机制错误,已更正 —— 见 docstring。)
            raise ValueError(
                f"cagr: 结果位数超过 Decimal 精度(prec=40);"
                f"days={days},期末/期初={ratio} 时年化会达到 1e20 量级,不适合该口径") from e


def max_drawdown(equity: list) -> dict:
    """最大回撤(%) = max((峰值 - 其后谷值)/峰值) * 100,四舍五入到 0.01;
    peak/trough 为 0 基下标;多个相同最大回撤取最早出现者。

    ⚠ 2026-10-01 修正(附录 B1):原实现对**空序列**静默返回
    `{"mdd_pct": "0.00", "peak_index": 0, "trough_index": 0}`。
    那是**凭空捏造的答案** ——「没有数据」被读成「没有回撤」,而且下标 0 指向不存在的元素。
    由于本函数是 mdd 题的**判分基准**,静默错值会让整批题判错却无人察觉
    (selftest 只验「参考答案与作答一致」,参考答案自己错了也照样全绿)。
    现改为显式抛错:调用方必须决定空序列怎么办,不能默认「回撤为 0」。
    """
    if not equity:
        raise ValueError("max_drawdown: equity 序列为空,无法定义回撤(需要至少 1 个点)")
    best, best_peak, best_trough = D(0), 0, 0
    peak_i = 0
    for i, v in enumerate(equity):
        v = D(v)
        if v > D(equity[peak_i]):
            peak_i = i
        if D(equity[peak_i]) == 0:
            # 峰值为 0 时回撤无定义(0/0)。显式失败,不让它变成一个看似正常的数字。
            raise ValueError(
                f"max_drawdown: 峰值下标 {peak_i} 的净值为 0,回撤无定义")
        dd = (D(equity[peak_i]) - v) / D(equity[peak_i])
        if dd > best:
            best, best_peak, best_trough = dd, peak_i, i
    return {"mdd_pct": str((best * 100).quantize(D("0.01"), rounding=ROUND_HALF_UP)),
            "peak_index": best_peak, "trough_index": best_trough}


# ══════════════════════════════════════════════════════════════════════════
# 认知陷阱题 (trap):答案唯一且可程序判分,但**直觉答案诱人且错误**。
# 设计依据:认知反射测验 (CRT, Frederick 2005) 与业界广泛复现的"降智检测"题。
# 这类题对"单路 vs 多路"的区分力远高于常规数值题 —— 因为系统 1 会给出
# 一个自信的错误答案,而三路独立采样有机会在交叉比对时发现分歧。
# ══════════════════════════════════════════════════════════════════════════

def crt_ball(total_cents: int, diff_cents: int) -> str:
    """CRT 球拍题:合计 total 分,球拍比球贵 diff 分,求球价(分)。
    正确 = (total - diff)/2;直觉错误 = diff(把"贵 diff"当成球价)。"""
    n = D(total_cents) - D(diff_cents)
    if n % 2 != 0:
        raise ValueError("无整数解")
    return str(int(n / 2))


def crt_widgets(machines: int, minutes: int, widgets: int, t_m: int, t_w: int) -> str:
    """CRT 机器题:m 台 m 分钟造 w 个;求 t_m 台造 t_w 个需几分钟。
    正确 = minutes × (t_w/w) × (m/t_m);直觉错误 = minutes × (t_w/w)(忽略机器数)。"""
    t = D(minutes) * (D(t_w) / D(widgets)) * (D(machines) / D(t_m))
    return str(t.quantize(D("0.0001")).normalize())


def crt_lily(total_days: int) -> str:
    """CRT 睡莲题:第 total_days 天铺满,问铺满一半是第几天。正确 = total_days - 1。"""
    return str(total_days - 1)


def decimal_max(a: str, b: str) -> str:
    """小数比较:返回较大者。专门捕捉"按字符串/版本号比较"的直觉错误
    (如 9.11 vs 9.9 → 直觉错答 9.11,正确 9.9)。"""
    return a if D(a) > D(b) else b


def count_letter(word: str, letter: str) -> str:
    """字母计数:捕捉 tokenizer 把词切成多 token 导致数错(如 strawberry 的 r)。"""
    return str(word.lower().count(letter.lower()))


def mushroom_water_lost(initial_kg: str, pct_initial: str, pct_final: str) -> str:
    """蘑菇含水率题:干物质守恒。正确 = 初始重 - 干物质/(1-最终含水率)。
    经典:1000kg 99%→98% 失水 500kg(直觉错答 10 或 20)。"""
    dry = D(initial_kg) * (1 - D(pct_initial))
    final_total = dry / (1 - D(pct_final))
    lost = D(initial_kg) - final_total
    return str(lost.quantize(D("0.01"), rounding=ROUND_HALF_UP))


def candy_min(round_counts: list, star_counts: list, i_a: int, i_p: int) -> int:
    """糖果题(最坏情况保证):三种口味、两种形状;形状靠手感可分辨 ⇒ 可自选圆/星配比。
    目标 = (圆A≥1 ∧ 星P≥1) ∨ (星A≥1 ∧ 圆P≥1)。
    返回最少取出数 n。**忽略"可分辨"提示会得到明显更大的错答**(见 blind_candy_min)。
    """
    tc, ts = sum(round_counts), sum(star_counts)
    Ac, Pc = round_counts[i_a], round_counts[i_p]
    As, Ps = star_counts[i_a], star_counts[i_p]

    def avoidable(x, y):
        """取 x 圆 + y 星时,对手能否构造出不含目标的组合。
        ¬目标 = (Ac=0∨Ps=0) ∧ (As=0∨Pc=0),展开为四种情形之一:"""
        return ((x <= tc - Ac and y <= ts - As)          # 无苹果
                or (x <= tc - Ac - Pc and y <= ts)       # 圆无苹果且圆无桃子(圆全西瓜)
                or (x <= tc and y <= ts - As - Ps)       # 星无苹果且星无桃子(星全西瓜)
                or (x <= tc - Pc and y <= ts - Ps))      # 无桃子

    for n in range(0, tc + ts + 1):
        for x in range(max(0, n - ts), min(n, tc) + 1):
            if not avoidable(x, n - x):
                return n
    return tc + ts


def blind_candy_min(round_counts: list, star_counts: list, i_a: int, i_p: int) -> int:
    """同一道题但**不利用"形状可分辨"**(盲目抓取,配比也由对手决定)的答案。
    用于测试:必须严格大于 candy_min,否则该题不构成"审题陷阱"。"""
    tc, ts = sum(round_counts), sum(star_counts)
    Ac, Pc = round_counts[i_a], round_counts[i_p]
    As, Ps = star_counts[i_a], star_counts[i_p]
    worst = max((tc - Ac) + (ts - As),
                (tc - Ac - Pc) + ts,
                tc + (ts - As - Ps),
                (tc - Pc) + (ts - Ps))
    return worst + 1
