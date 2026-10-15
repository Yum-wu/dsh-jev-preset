#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""solvers_band_conservation.py —— band_conservation.jsonl(B 线「朴素界错」20 题)独立复算脚本。

立场
----
只读 question 字段的文字,用正则把参数抠出来,自己重算每题真值;expected 只用于最后比对,
**绝不参与计算**。每题给出**两套互相独立的解法**:

    A = 解析 / 公式解
    B = 独立第二算法 —— (a) 守恒类:逐步数值迭代(按不变量反推,不做代数化简)
                        (b) 可达类:暴力枚举 / 穷举搜索(规模小到能枚举完)

A 与 B 必须逐位一致;不一致即打印 MISMATCH 并以退出码 1 结束。

另校验每题 naive(朴素直觉解)**严格不等于** expected —— 相等即陷阱失效,判废。

退出码
  0 = 全部 OK 且 20/20 NAIVE_DISTINCT ok=True
  1 = 存在 MISMATCH 或 NAIVE_DISTINCT ok=False

用法
  python -X utf8 -B solvers_band_conservation.py                 # 逐题复算 + 比对
  python -X utf8 -B solvers_band_conservation.py --emit out.json # 仅导出复算结果(expected 由本脚本产生)
"""

import json
import math
import os
import re
import sys
from decimal import Decimal as D
from decimal import ROUND_HALF_UP, getcontext
from itertools import combinations

getcontext().prec = 40
HERE = os.path.dirname(os.path.abspath(__file__))
JSONL = os.path.join(HERE, "band_conservation.jsonl")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ============================ 工具 ============================
def q4(x):
    """保留 4 位小数(四舍五入)。"""
    return str(D(x).quantize(D("0.0001"), rounding=ROUND_HALF_UP))


def istr(x):
    """整数答案写成不带小数点的字符串。"""
    return str(int(x))


def _rx(pat, q, gi=1):
    m = re.search(pat, q)
    if not m:
        raise RuntimeError("regex miss: %r" % pat)
    return D(m.group(gi))


def _ints(pat, q, gi=1):
    m = re.search(pat, q)
    if not m:
        raise RuntimeError("regex miss: %r" % pat)
    return [int(x) for x in m.group(gi).split("、")]


# ==================== (a) 守恒量建模 10 题 ====================
def s00(q):
    """盐水蒸发:盐(不变量)守恒反推新总重。"""
    m0 = _rx(r"(\d+(?:\.\d+)?) kg 盐水", q)
    p0 = _rx(r"盐占 (\d+(?:\.\d+)?)%", q)
    p1 = _rx(r"升到 (\d+(?:\.\d+)?)%", q)
    salt = m0 * p0 / 100                       # 不变量:盐的质量
    a = q4(m0 - salt / (p1 / 100))
    t, lost = m0, D(0)                         # 迭代:逐 1 kg 蒸发,直到浓度达标
    while salt / t < p1 / 100:
        t -= 1
        lost += 1
    return a, q4(lost), q4(m0 * (p1 - p0) / 100)


def s01(q):
    """铜锌合金加铜:锌(不变量)守恒反推新总重。"""
    m0 = _rx(r"(\d+(?:\.\d+)?) kg 铜锌合金", q)
    p0 = _rx(r"铜占 (\d+(?:\.\d+)?)%", q)
    p1 = _rx(r"升到 (\d+(?:\.\d+)?)%", q)
    cu0 = m0 * p0 / 100
    zn = m0 - cu0                              # 不变量:锌的质量
    a = q4(zn / (1 - p1 / 100) - m0)
    x = D(0)                                   # 迭代:逐 1 kg 加铜
    while (cu0 + x) / (m0 + x) < p1 / 100:
        x += 1
    return a, q4(x), q4(m0 * (p1 - p0) / 100)


def s02(q):
    """换汇往返:卖出价/买入价点差,钱不是不变量。"""
    usd = _rx(r"持有 ([\d.]+) 美元", q)
    r1 = _rx(r"按 ([\d.]+) 元/美元 的汇率把这", q)
    r2 = _rx(r"按 ([\d.]+) 元/美元 的汇率全部换回", q)
    a = q4(usd * r1 / r2)
    per = r1 / r2                              # 每 1 美元能换回多少美元
    tot = D(0)                                 # 迭代:逐美元累加
    for _ in range(int(usd)):
        tot += per
    return a, q4(tot), q4(usd)


def s03(q):
    """保证金率上调:权益(不变量)决定名义上限。"""
    eq = _rx(r"权益为 ([\d.]+) USDT", q)
    n0 = _rx(r"名义价值 ([\d.]+) USDT", q)
    m = re.search(r"从 (\d+)% 上调到 (\d+)%", q)
    old, new = D(m.group(1)), D(m.group(2))
    a = q4(eq / (new / 100))
    n = n0                                     # 迭代:逐 1 USDT 减仓
    while eq / n < new / 100:
        n -= 1
    return a, q4(n), q4(n0 * (1 - (new - old) / old))


def s04(q):
    """双边手续费后的净收益率:费率作用在各自成交额上,不能相减。"""
    buy = _rx(r"以 ([\d.]+) 元/股 买入", q)
    sell = _rx(r"以 ([\d.]+) 元/股 全部卖出", q)
    f = D(re.findall(r"成交金额的 (\d+)%", q)[0])
    cost = buy * (1 + f / 100)
    proceeds = sell * (1 - f / 100)
    a = q4((proceeds - cost) / cost * 100)
    r = D(0)                                   # 迭代:以 0.0001% 步长搜最小可行收益率
    while cost * (1 + r / 100) < proceeds:
        r += D("0.0001")
    return a, q4(r), q4((sell - buy) / buy * 100 - 2 * f)


def s05(q):
    """含税价换算:税基是不含税价,不能拿含税价乘 (1-税率)。"""
    gross = _rx(r"售价 ([\d.]+) 元已含", q)
    vat = _rx(r"元已含 (\d+)%", q)
    a = q4(gross / (1 + vat / 100))
    net = D(0)                                 # 迭代:以 0.01 元步长搜最小不含税价
    while net * (1 + vat / 100) < gross:
        net += D("0.01")
    return a, q4(net), q4(gross * (1 - vat / 100))


def s06(q):
    """容器注氧:氮气(不变量)守恒反推新总摩尔数。"""
    tot0 = _rx(r"有 (\d+(?:\.\d+)?) mol 混合气体", q)
    p0 = _rx(r"氧气占 (\d+(?:\.\d+)?)%", q)
    p1 = _rx(r"达到 (\d+(?:\.\d+)?)%", q)
    o2 = tot0 * p0 / 100
    n2 = tot0 - o2                             # 不变量:氮气摩尔数
    a = q4(n2 / (1 - p1 / 100) - tot0)
    x = D(0)                                   # 迭代:逐 0.1 mol 注氧
    while (o2 + x) / (tot0 + x) < p1 / 100:
        x += D("0.1")
    return a, q4(x), q4(tot0 * p1 / 100 - o2)


def s07(q):
    """两杯盐水混合:盐量守恒,浓度按质量加权(不是简单平均)。"""
    m = re.search(r"把 (\d+) g 质量分数 (\d+)% 的盐水与 (\d+) g 质量分数 (\d+)%", q)
    m1, p1, m2, p2 = D(m.group(1)), D(m.group(2)), D(m.group(3)), D(m.group(4))
    a = q4((m1 * p1 + m2 * p2) / (m1 + m2))
    salt, step, x = D(0), D("0.5"), D(0)       # 迭代:逐 0.5 g 累加盐量
    while x < m1:
        salt += step * p1 / 100
        x += step
    while x < m1 + m2:
        salt += step * p2 / 100
        x += step
    return a, q4(salt / (m1 + m2) * 100), q4((p1 + p2) / 2)


def s08(q):
    """往返平均速度:总路程/总时间(调和平均),不是速度的算术平均。"""
    dist = _rx(r"单程 (\d+(?:\.\d+)?) km", q)
    up = _rx(r"上坡平均速度 (\d+(?:\.\d+)?) km/h", q)
    dn = _rx(r"下坡平均速度 (\d+(?:\.\d+)?) km/h", q)
    a = q4(2 * dist / (dist / up + dist / dn))
    step, t, x = D("0.01"), D(0), D(0)         # 迭代:逐 0.01 km 累加用时
    while x < dist:
        t += step / up
        x += step
    x = D(0)
    while x < dist:
        t += step / dn
        x += step
    return a, q4(2 * dist / t), q4((up + dn) / 2)


def s09(q):
    """电池 SOH 逐年衰减:相对衰减是逐年相乘,不是线性累减。"""
    soh0 = _rx(r"SOH 为 (\d+)%", q)
    dec = _rx(r"上一年年末 SOH 的 (\d+)%", q)
    yrs = int(_rx(r"问 (\d+) 年后", q))
    a = q4(soh0 * (dec / 100) ** yrs)
    s = soh0                                   # 迭代:逐年相乘
    for _ in range(yrs):
        s = s * dec / 100
    return a, q4(s), q4(soh0 - yrs * (100 - dec))


# ============== (b) 极值可达性 10 题(必须验证可达) ==============
def s10(q):
    """硬币凑数:枚数上界 floor(总额/最小币值) 常常不可达,必须构造。"""
    c1 = _rx(r"(\d+) 元硬币和", q)
    c2 = _rx(r"元硬币和 (\d+) 元硬币", q)
    tgt = _rx(r"凑出 (\d+) 元", q)
    best = 0                                   # 暴力枚举所有 (a,b)
    for a in range(int(tgt // c1) + 1):
        rem = tgt - c1 * a
        if rem >= 0 and rem % c2 == 0:
            best = max(best, int(a + rem // c2))
    ana = 0                                    # 解析:4a+7b=53 → 枚数 n=(T-3b)/4,枚举合法 b
    for b in range(int(tgt // c2) + 1):
        if (tgt - c2 * b) % c1 == 0:
            ana = max(ana, int((tgt - c2 * b) // c1 + b))
    return istr(ana), istr(best), istr(int(tgt // c1))


def s11(q):
    """托盘装载:网格公式 floor(W/w)*floor(H/h) 不是最优,混排可多放。"""
    m = re.search(r"长 (\d+) cm、宽 (\d+) cm", q)
    W, H = int(m.group(1)), int(m.group(2))
    m2 = re.search(r"是 (\d+) cm × (\d+) cm", q)
    w, h = int(m2.group(1)), int(m2.group(2))
    ub = (W * H) // (w * h)                    # 面积上界
    shelf = 0                                  # 解析:两带混排(下带旋转箱,上带正放)
    for y in range(H + 1):
        shelf = max(shelf, (W // h) * (y // w) + (W // w) * ((H - y) // h))
    if shelf != ub:
        raise RuntimeError("构造值 %d != 面积上界 %d" % (shelf, ub))
    # 暴力:1 cm 网格精确回溯 —— 每步覆盖「行优先第一个空格」
    grid = bytearray(W * H)
    best = [0]

    def rec(cnt):
        if cnt > best[0]:
            best[0] = cnt
        free = W * H - sum(grid)
        if cnt + free // (w * h) <= best[0]:
            return
        p = None
        for i in range(W * H):
            if not grid[i]:
                p = divmod(i, W)
                break
        if p is None:
            return
        r, c = p
        for bw, bh in {(w, h), (h, w)}:
            if c + bw <= W and r + bh <= H:
                cells = [(r + dr) * W + (c + dc) for dr in range(bh) for dc in range(bw)]
                if all(not grid[i] for i in cells):
                    for i in cells:
                        grid[i] = 1
                    rec(cnt + 1)
                    for i in cells:
                        grid[i] = 0

    rec(0)
    return istr(shelf), istr(best[0]), istr((W // w) * (H // h))


def s12(q):
    """阶梯电价:按最低档单价除预算只是上界,必须分段累加验证。"""
    lows = re.findall(r"不超过 (\d+) 度的部分按 ([\d.]+) 元/度", q)
    hi = re.search(r"(?<!不)超过 (\d+) 度的部分按 ([\d.]+) 元/度", q)
    budget = _rx(r"预算为 (\d+) 元", q)
    tiers = [(D(a), D(b)) for a, b in lows] + [(None, D(hi.group(2)))]
    if int(hi.group(1)) != int(lows[-1][0]):
        raise RuntimeError("阶梯断点不一致")

    def cost(d):
        c, prev = D(0), D(0)
        for lim, price in tiers:
            if lim is None:
                if d > prev:
                    c += (d - prev) * price
                break
            if d <= lim:
                c += (d - prev) * price
                break
            c += (lim - prev) * price
            prev = lim
        return c

    a = None                                   # 解析:逐档填满
    rem, done = budget, D(0)
    for i, (lim, price) in enumerate(tiers):
        span = None if lim is None else lim - done
        if span is None or rem <= span * price:
            a = done + rem / price
            break
        rem -= span * price
        done = lim
    best = D(0)                                # 暴力:逐 0.5 度累加
    d = D(0)
    while d <= D(1000):
        if cost(d) <= budget:
            best = d
        d += D("0.5")
    return q4(a), q4(best), q4(budget / tiers[0][1])


def s13(q):
    """满减券拆单:一张券用在一整单只是下界,拆单可多买。"""
    price = _rx(r"单价 (\d+) 元", q)
    m = re.search(r"满 (\d+) 元减 (\d+) 元", q)
    thr, disc = D(m.group(1)), D(m.group(2))
    budget = _rx(r"预算为 (\d+) 元", q)
    need = int(math.ceil(thr / price))         # 每单至少几件才有券
    ana = max(k for k in range(0, 60) if price * k - disc * (k // need) <= budget)
    # 暴力:对每个 k 用 DP 求「任意拆单方案」下的最低总价
    def min_cost(k):
        f = [D(0)] * (k + 1)
        for n in range(1, k + 1):
            f[n] = min(f[n - j] + (price * j - (disc if price * j >= thr else D(0)))
                       for j in range(1, n + 1))
        return f[k]

    bru = max(k for k in range(0, 60) if min_cost(k) <= budget)
    naive = int(math.floor((budget + disc) / price))   # 只买一单、只用一张券
    return istr(ana), istr(bru), istr(naive)


def s14(q):
    """仓位取整:保证金够不等于开得起,手续费按名义另扣。"""
    face = _rx(r"面值 ([\d.]+) USDT", q)
    mm = _rx(r"保证金率 ([\d.]+)%", q)
    fee = _rx(r"名义价值的 ([\d.]+)%", q)
    avail = _rx(r"可用资金 ([\d.]+) USDT", q)
    per = face * mm / 100 + face * fee / 100
    a = istr(int(avail / per))
    n = 0                                      # 暴力:逐张加,直到开不起
    while (n + 1) * per <= avail:
        n += 1
    return a, istr(n), istr(int(avail / (face * mm / 100)))


def s15(q):
    """快递分段计费:首重单价线性外推只是下界,续重单价更便宜。"""
    base_kg = _rx(r"首重 ([\d.]+) kg", q)
    base_fee = _rx(r"以内收费 ([\d.]+) 元", q)
    m = re.search(r"每 ([\d.]+) kg 加收 ([\d.]+) 元", q)
    step_kg, step_fee = D(m.group(1)), D(m.group(2))
    budget = _rx(r"预算为 (\d+) 元", q)
    units = int((budget - base_fee) / step_fee)
    a = q4(base_kg + units * step_kg)
    best = D(0)                                # 暴力:逐 0.5 kg 试算
    w = D("0.5")
    while w <= D(100):
        extra = w - base_kg
        k = 0 if extra <= 0 else int(math.ceil(extra / step_kg))
        if base_fee + k * step_fee <= budget:
            best = w
        w += D("0.5")
    return a, q4(best), q4(budget / base_fee)


def s16(q):
    """会议室排程:最短会议时长除总时长只是上界,场次还受会议数限制。"""
    cap = _rx(r"共 (\d+) 分钟", q)
    durs = _ints(r"分别为 ([0-9]+(?:、[0-9]+)+) 分钟", q)
    tot, a = 0, 0                              # 解析:取最短的若干场
    for d in sorted(durs):
        if tot + d <= cap:
            tot += d
            a += 1
        else:
            break
    best = 0                                   # 暴力:2^n 子集枚举
    for r in range(1, len(durs) + 1):
        for comb in combinations(durs, r):
            if sum(comb) <= cap:
                best = max(best, r)
    return istr(a), istr(best), istr(int(cap // min(durs)))


def s17(q):
    """名义上限拆单:按总额除上限只是下界,每笔受「整单位」取整约束。"""
    units = _rx(r"持有 (\d+) 单位", q)
    cap = _rx(r"不得超过 (\d+) USDT", q)
    tick = _rx(r"必须是 ([\d.]+) 的整数倍", q)
    floor_px = _rx(r"不得低于 ([\d.]+)", q)
    if floor_px % tick != 0:
        raise RuntimeError("最低价不是 tick 整数倍")
    per_order = int(cap / floor_px)            # 每笔最多几个单位
    a = istr(int(math.ceil(units / per_order)))
    n = 1                                      # 暴力:逐笔加容量
    while n * per_order < units:
        n += 1
    return a, istr(n), istr(int(math.ceil(units * floor_px / cap)))


def s18(q):
    """电梯载重:额定载重除最轻体重只是上界,必须选人构造。"""
    cap = _rx(r"额定载重 (\d+) kg", q)
    ws = _ints(r"分别为 ([0-9]+(?:、[0-9]+)+) kg", q)
    tot, a = 0, 0                              # 解析:取最轻的若干位
    for w in sorted(ws):
        if tot + w <= cap:
            tot += w
            a += 1
        else:
            break
    best = 0                                   # 暴力:2^n 子集枚举
    for r in range(1, len(ws) + 1):
        for comb in combinations(ws, r):
            if sum(comb) <= cap:
                best = max(best, r)
    return istr(a), istr(best), istr(int(cap // min(ws)))


def s19(q):
    """鸽巢保证:必须构造最大的「不满足目标」的集合,再 +1。"""
    m = re.search(r"红球 (\d+) 个、蓝球 (\d+) 个、绿球 (\d+) 个", q)
    counts = [int(m.group(i)) for i in (1, 2, 3)]
    k = int(_rx(r"至少有 (\d+) 个同色", q))
    a = sum(min(c, k - 1) for c in counts) + 1
    best = 0                                   # 暴力:枚举所有「每色都 < k」的计数组合
    for r in range(counts[0] + 1):
        for b in range(counts[1] + 1):
            for g in range(counts[2] + 1):
                if r < k and b < k and g < k:
                    best = max(best, r + b + g)
    return istr(a), istr(best + 1), istr(len(counts) * k)


# ============================ 登记表 ============================
# (函数, 答案键名, 格式化器)
SPECS = [
    (s00, "water_lost_kg", q4), (s01, "copper_added_kg", q4),
    (s02, "usd_remaining", q4), (s03, "max_notional_usdt", q4),
    (s04, "net_return_pct", q4), (s05, "price_excl_tax", q4),
    (s06, "oxygen_added_mol", q4), (s07, "final_conc_pct", q4),
    (s08, "avg_speed_kmh", q4), (s09, "soh_pct", q4),
    (s10, "max_coins", istr), (s11, "max_boxes", istr),
    (s12, "max_kwh", q4), (s13, "max_items", istr),
    (s14, "max_contracts", istr), (s15, "max_weight_kg", q4),
    (s16, "max_meetings", istr), (s17, "min_orders", istr),
    (s18, "max_passengers", istr), (s19, "min_balls", istr),
]
KIND = ["(a)守恒"] * 10 + ["(b)可达"] * 10


def main():
    argv = sys.argv[1:]
    emit_path = None
    if "--emit" in argv:
        i = argv.index("--emit")
        emit_path = argv[i + 1] if i + 1 < len(argv) else "expected_emit.json"

    with open(JSONL, "r", encoding="utf-8") as fh:
        rows = [json.loads(ln) for ln in fh.read().splitlines() if ln.strip()]
    print("LINES %d" % len(rows))
    if len(rows) != 20:
        print("# FAIL: 行数不是 20")
        return 1

    bad, emit = 0, {}
    for row in rows:
        pid = row["id"]
        idx = int(pid.rsplit("-", 1)[1])
        func, key, fmt = SPECS[idx]
        a, b, nv = func(row["question"])
        a, b, nv = fmt(a), fmt(b), fmt(nv)
        if a != b:
            print("MISMATCH %s 两套解法不一致 analytic=%s brute=%s" % (pid, a, b))
            bad += 1
            continue
        emit[pid] = {"key": key, "value": a, "naive": nv}
        if emit_path:
            continue
        exp = row.get("expected", {}).get(key)
        if exp is None or str(exp) != a:
            print("MISMATCH %s expected=%s solver=%s" % (pid, exp, a))
            bad += 1
            continue
        print("OK %s %s   [%s analytic=%s brute=%s]" % (pid, a, KIND[idx], a, b))
        ok = str(row.get("naive", "")) != a
        print("NAIVE_DISTINCT %s ok=%s  naive=%s expected=%s" % (pid, ok, row.get("naive"), a))
        if not ok:
            bad += 1

    if emit_path:
        with open(emit_path, "w", encoding="utf-8") as fh:
            json.dump(emit, fh, ensure_ascii=False, indent=1)
        print("# emitted %d answers -> %s" % (len(emit), emit_path))
        return 0

    print("# summary: cases=%d bad=%d verdict=%s" % (len(rows), bad, "PASS" if bad == 0 else "FAIL"))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
