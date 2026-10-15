#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""solvers_band_worstcase.py —— band_worstcase.jsonl(「朴素界错」最坏情况构造 20 题)独立复算脚本。

立场
----
本脚本**不读 expected 参与计算**;expected 只在最后一步用于比对。
每题两套独立解法,必须一致:
  (a) formula —— 结构化闭式解(由「构造最大的不满足目标的集合,再 +1」推导)
  (b) brute   —— 暴力枚举(穷举所有取法向量 / 所有对抗性放置 / 所有机房分布),
                 规模刻意压到能枚举完(单题状态数 <= 1e5 量级)
两套不一致 ⇒ 打印 MISMATCH 并以退出码 1 结束(不迁就任何一侧)。

另校验:
  * 题面数字完整性 —— 结构化数据里的每个数字都必须出现在 question 文字里
  * NAIVE_DISTINCT —— 朴素直觉解必须严格不等于正确解(相等 = 陷阱无效 = 废题)

退出码: 0 = 全部 OK;1 = 存在 MISMATCH / 陷阱失效 / 题面数字缺失
"""

import itertools
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
SUITE = os.path.join(HERE, "band_worstcase.jsonl")


# ============================ 通用暴力引擎 ============================
def brute_draws(buckets, good):
    """穷举所有「取法向量」:每个桶取 0..count 个。

    返回 (min_draws, witness):
      min_draws = (不满足目标的取法中的最大总取数) + 1
      witness   = 那个最大坏集合本身(逐桶计数)
    good 必须**向上封闭**(多取不会让目标失效),因此一旦 good 成立即可整枝剪掉。
    """
    labels = list(buckets)
    n = len(labels)
    counts = {lab: 0 for lab in labels}
    best = -1
    best_witness = None

    def dfs(i, size):
        nonlocal best, best_witness
        if good(counts):
            return
        if i == n:
            if size > best:
                best = size
                best_witness = dict(counts)
            return
        lab = labels[i]
        for k in range(buckets[lab] + 1):
            counts[lab] = k
            dfs(i + 1, size + k)
        counts[lab] = 0

    dfs(0, 0)
    return best + 1, best_witness


def check_maximal(witness, buckets, good):
    """独立局部校验:最大坏集合必须「再加任何一个元素就变好」。

    这是与全局搜索不同的断言 —— 若某处还能加一个元素仍不满足目标,
    说明找出的根本不是最大坏集合(答案偏小)。同时校验 witness 本身确实不满足目标。
    """
    if good(witness):
        return False
    for lab, cap in buckets.items():
        if witness[lab] < cap:
            probe = dict(witness)
            probe[lab] += 1
            if not good(probe):
                return False
    return True


def brute_adversary(N, D, K):
    """对抗性放置暴力:共 N 个对象,其中恰好 D 个是「坏」的(位置未知,由对手决定),
    我们按固定顺序逐个检查 m 个,问最小的 m 使「无论对手把 D 个坏对象放在哪,
    检出的坏对象都 >= K 个」。

    真穷举:枚举全部 C(N, D) 种放置,取「检出坏对象数」的最小值。
    """
    placements = [frozenset(p) for p in itertools.combinations(range(N), D)]
    for m in range(0, N + 1):
        drawn = frozenset(range(m))
        if all(len(drawn & pl) >= K for pl in placements):
            return m
    return None


# ============================ 20 题的结构化数据 ============================
# 说明:下面的桶/计数/阈值全部是从 question 文字里抄录的输入数据(不是答案)。
# nums = 必须在 question 文字中出现的数字(题面完整性自检)。

PROBS = []


def add(pid, key, buckets, good, formula, naive, nums, brute=None):
    PROBS.append(dict(id=pid, key=key, buckets=buckets, good=good,
                      formula=formula, naive=naive, nums=nums, brute=brute))


# ---- 00 彩球箱:保证同时有红球与蓝球 -------------------------------------
B00 = {"红": 7, "蓝": 5, "绿": 9, "白": 4}
add("band_worstcase-20261015-00", "min_draws", B00,
    lambda c: c["红"] >= 1 and c["蓝"] >= 1,
    # 最大坏集合:整个缺红(18)或整个缺蓝(20)⇒ 取总数 - min(红,蓝)
    lambda b: sum(b.values()) - min(b["红"], b["蓝"]) + 1,
    # 朴素解:把两个目标颜色的球数直接相加
    lambda b: b["红"] + b["蓝"],
    [25, 7, 5, 9, 4])

# ---- 01 抽屉袜子:保证至少 4 只同色 --------------------------------------
B01 = {"黑": 12, "灰": 7, "蓝": 2, "棕": 5, "白": 11}
add("band_worstcase-20261015-01", "min_draws", B01,
    lambda c: any(v >= 4 for v in c.values()),
    # 最大坏集合:每种颜色至多 3 只,但蓝色只有 2 只
    lambda b: sum(min(v, 3) for v in b.values()) + 1,
    # 朴素解:5 种颜色 × 3 只 + 1,忘了蓝色只有 2 只
    lambda b: len(b) * 3 + 1,
    [5, 12, 7, 2, 5, 11, 4])

# ---- 02 糖果罐:保证同口味、不同形状 -------------------------------------
B02 = {"圆-苹果": 6, "圆-桃子": 9, "圆-西瓜": 5,
       "星-苹果": 4, "星-桃子": 3, "星-西瓜": 3}
FLAVORS02 = ["苹果", "桃子", "西瓜"]
add("band_worstcase-20261015-02", "min_draws", B02,
    lambda c: any(c["圆-" + f] >= 1 and c["星-" + f] >= 1 for f in FLAVORS02),
    # 最大坏集合:每种口味只取形状多的那一侧
    lambda b: sum(max(b["圆-" + f], b["星-" + f]) for f in FLAVORS02) + 1,
    # 朴素解:把全部圆形糖果加起来
    lambda b: sum(b["圆-" + f] for f in FLAVORS02),
    [3, 2, 6, 9, 5, 4, 3])

# ---- 03 零件质检:保证至少 1 件不合格品 ----------------------------------
B03 = {"甲": 12, "乙": 9, "丙": 7, "丁": 11}
GOOD03 = {"甲": 10, "乙": 6, "丙": 7, "丁": 7}   # 各家合格品数
add("band_worstcase-20261015-03", "min_draws", B03,
    # 对抗语义:只要某家取出的件数超过该家合格品数,该家就必然带出不合格品
    lambda c: any(c[s] > GOOD03[s] for s in c),
    # 最大坏集合:恰好取走所有合格品
    lambda b: sum(GOOD03.values()) + 1,
    # 朴素解:不合格品总数 9 + 1
    lambda b: sum(b.values()) - sum(GOOD03.values()) + 1,
    [39, 4, 12, 2, 9, 3, 7, 11, 1])

# ---- 04 权限位:保证 3 个用户权限组合完全相同 ----------------------------
B04 = {("组合" + "".join(str(x) for x in cb)): 8
       for cb in itertools.combinations(range(1, 5), 2)}
add("band_worstcase-20261015-04", "min_draws", B04,
    lambda c: any(v >= 3 for v in c.values()),
    # 6 个组合类,最大坏集合 = 每类 2 个
    lambda b: len(b) * 2 + 1,
    # 朴素解:6 类 × 3 个
    lambda b: len(b) * 3,
    [4, 2, 6, 20, 3])

# ---- 05 微服务故障注入:保证发现 3 个缺陷节点 ----------------------------
add("band_worstcase-20261015-05", "min_draws", {"缺陷": 4, "正常": 16},
    None,
    # 最大坏集合:先看完全部 16 个正常节点,再看到 2 个缺陷节点
    lambda b: (20 - 4) + (3 - 1) + 1,
    # 朴素解:缺陷数 4 + 目标 3
    lambda b: 4 + 3,
    [20, 4, 3],
    brute=lambda p: brute_adversary(20, 4, 3))

# ---- 06 盲盒集卡:保证集齐 5 款 ------------------------------------------
B06 = {"1号款": 12, "2号款": 9, "3号款": 4, "4号款": 7, "5号款": 6}
add("band_worstcase-20261015-06", "min_draws", B06,
    lambda c: all(v >= 1 for v in c.values()),
    # 最大坏集合:取完库存最多的 4 款(缺最少的那款)
    lambda b: sum(b.values()) - min(b.values()) + 1,
    # 朴素解:四个最大款之和
    lambda b: sum(b.values()) - min(b.values()),
    [5, 12, 9, 4, 7, 6, 38, 1])

# ---- 07 风控平仓:保证平掉 2 个浮亏仓位 ----------------------------------
add("band_worstcase-20261015-07", "min_draws", {"浮亏": 4, "浮盈": 5},
    None,
    # 最大坏集合:平完 5 个浮盈 + 1 个浮亏
    lambda b: (9 - 4) + (2 - 1) + 1,
    # 朴素解:浮亏数 4 + 目标 2
    lambda b: 4 + 2,
    [9, 4, 2],
    brute=lambda p: brute_adversary(9, 4, 2))

# ---- 08 网络包重传:保证 3 个关键包各至少收到 1 份 -----------------------
def _brute08(p):
    """穷举每包副本数 (c1,c2,c3),再穷举所有「丢包模式」检验保证性。"""
    for total in range(0, 40):
        for c1 in range(0, total + 1):
            for c2 in range(0, total - c1 + 1):
                c3 = total - c1 - c2
                cand = (c1, c2, c3)
                if any(x > 12 for x in cand):
                    continue
                ok = True
                for l1 in range(0, min(c1, 6) + 1):
                    for l2 in range(0, min(c2, 6 - l1) + 1):
                        for l3 in range(0, min(c3, 6 - l1 - l2) + 1):
                            if c1 - l1 < 1 or c2 - l2 < 1 or c3 - l3 < 1:
                                ok = False
                if ok:
                    return total
    return None


add("band_worstcase-20261015-08", "min_packets", {"包1": 7, "包2": 7, "包3": 7},
    None,
    # 每个包必须自身超过最大丢包数
    lambda b: 3 * (6 + 1),
    # 朴素解:3 个包 + 最多丢 6 个
    lambda b: 3 + 6,
    [3, 6, 1],
    brute=_brute08)

# ---- 09 扑克牌:保证 3 张同点数 ------------------------------------------
B09 = {p: 4 for p in ["A", "2", "3", "4", "5", "6"]}
add("band_worstcase-20261015-09", "min_draws", B09,
    lambda c: any(v >= 3 for v in c.values()),
    # 6 个点数,每点最大坏集合取 2 张
    lambda b: len(b) * 2 + 1,
    # 朴素解:6 个点数 × 3 张
    lambda b: len(b) * 3,
    [24, 6, 4, 3])

# ---- 10 影院连座:保证有两人相邻就座 -------------------------------------
B10 = {n: 1 for n in range(1, 11)}
add("band_worstcase-20261015-10", "min_draws", B10,
    lambda c: any(c[n] >= 1 and c[n + 1] >= 1 for n in range(1, 10)),
    # 最大坏集合:隔一个坐一个 = 5 人
    lambda b: len(b) // 2 + 1,
    # 朴素解:10 个座位 / 2
    lambda b: len(b) // 2,
    [10, 1, 2])

# ---- 11 机房冗余:保证任一机房故障后剩余 >= 6 台 -------------------------
def _brute11(p):
    """穷举采购台数 T 与所有三机房分配 (a,b,c),检验「任一机房整体下线后剩余 >= 6」。"""
    for T in range(0, 40):
        for a in range(0, T + 1):
            for bb in range(0, T - a + 1):
                c = T - a - bb
                if min(T - a, T - bb, T - c) >= 6:
                    return T
    return None


add("band_worstcase-20261015-11", "min_servers", {"机房1": 6, "机房2": 6, "机房3": 6},
    None,
    # 最优分布是均分:total - ceil(total/3) >= 6 的最小 total
    lambda b: next(T for T in itertools.count(1) if T - (-(-T // 3)) >= 6),
    # 朴素解:3 个机房 × 6 台
    lambda b: 3 * 6,
    [3, 6, 0],
    brute=_brute11)

# ---- 12 血库配型:保证 2 袋 O 型且 1 袋 AB 型 ----------------------------
B12 = {"A型": 9, "B型": 7, "O型": 5, "AB型": 3}
add("band_worstcase-20261015-12", "min_draws", B12,
    lambda c: c["O型"] >= 2 and c["AB型"] >= 1,
    # 最大坏集合:两种失效方式取较大者(取完非 O 再拿 1 个 O;或取完非 AB)
    lambda b: max(sum(b.values()) - b["O型"] + 1, sum(b.values()) - b["AB型"]) + 1,
    # 朴素解:O 型袋数 + AB 型袋数
    lambda b: b["O型"] + b["AB型"],
    [9, 7, 5, 3, 24, 2, 1])

# ---- 13 电芯分档:保证两个电芯档位差 >= 2 --------------------------------
B13 = {"1档": 8, "2档": 6, "3档": 9, "4档": 5}
add("band_worstcase-20261015-13", "min_draws", B13,
    lambda c: any(c["%d档" % i] >= 1 and c["%d档" % j] >= 1
                  for i in range(1, 5) for j in range(1, 5) if j - i >= 2),
    # 最大坏集合:只取相邻的两个档位,取和最大的那对
    lambda b: max(b["%d档" % i] + b["%d档" % (i + 1)] for i in range(1, 4)) + 1,
    # 朴素解:取库存最多的两个档位之和(忽略了这两个档位必须相邻)
    lambda b: sorted(b.values())[-1] + sorted(b.values())[-2],
    [4, 1, 8, 2, 6, 3, 9, 5, 2])

# ---- 14 题库组卷:保证覆盖至少 4 个知识点 --------------------------------
B14 = {"知识点一": 12, "知识点二": 9, "知识点三": 7, "知识点四": 15, "知识点五": 4}
add("band_worstcase-20261015-14", "min_draws", B14,
    lambda c: sum(1 for v in c.values() if v >= 1) >= 4,
    # 最大坏集合:取完题量最多的 3 个知识点
    lambda b: sum(sorted(b.values())[-3:]) + 1,
    # 朴素解:取题量最少的 3 个知识点 + 1(极值取反)
    lambda b: sum(sorted(b.values())[:3]) + 1,
    [5, 12, 9, 7, 15, 4, 4])

# ---- 15 手套配对:保证 2 种颜色各达到 2 只 -------------------------------
B15 = {"红": 7, "蓝": 5, "绿": 9, "黄": 4, "紫": 6}
add("band_worstcase-20261015-15", "min_draws", B15,
    lambda c: sum(1 for v in c.values() if v >= 2) >= 2,
    # 最大坏集合:最多只让一种颜色达到 2 只 —— 该色全取,其余颜色各取 1 只
    lambda b: max(b.values()) + (len(b) - 1) + 1,
    # 朴素解:5 种颜色 × 2 只
    lambda b: len(b) * 2,
    [5, 7, 5, 9, 4, 6, 2])

# ---- 16 留样复检:保证某批次被全部取出 -----------------------------------
B16 = {"1批": 6, "2批": 8, "3批": 4, "4批": 9, "5批": 7}
add("band_worstcase-20261015-16", "min_draws", B16,
    lambda c: any(c[k] == B16[k] for k in c),
    # 最大坏集合:每个批次各留 1 支没取
    lambda b: sum(v - 1 for v in b.values()) + 1,
    # 朴素解:总数 - 批次数(漏 +1)
    lambda b: sum(v - 1 for v in b.values()),
    [5, 1, 6, 2, 8, 3, 4, 9, 7])

# ---- 17 螺丝混料:保证 3 颗完全相同 --------------------------------------
B17 = {"%s-%s" % (col, spec): 5
       for col in ["银", "黑", "金"] for spec in ["M4", "M5", "M6"]}
add("band_worstcase-20261015-17", "min_draws", B17,
    lambda c: any(v >= 3 for v in c.values()),
    # 9 个类,最大坏集合 = 每类 2 颗
    lambda b: len(b) * 2 + 1,
    # 朴素解:9 类 × 3 颗
    lambda b: len(b) * 3,
    [3, 4, 5, 6, 9, 5, 3])

# ---- 18 抽奖编号球:保证两个球编号之和 >= 12 -----------------------------
B18 = {4: 6, 5: 5, 7: 4, 9: 3}
THR18 = 12


def _good18(c):
    vals = sorted([v for v, k in c.items() for _ in range(k)], reverse=True)
    return len(vals) >= 2 and vals[0] + vals[1] >= THR18


def _formula18(b):
    """结构引理:坏集合中最大的编号为 m,则其余编号 <= T-1-m;
    若 m <= T-1-m,可把编号 <= m 的全部取走;否则只能取编号 <= T-1-m 的全部 + 1 个 m。"""
    vals = sorted(b)
    best = 0
    for m in vals:
        lim = THR18 - 1 - m
        s = sum(b[v] for v in vals if v <= min(m, lim))
        if m > lim:
            s += 1
        best = max(best, s)
    return best + 1


add("band_worstcase-20261015-18", "min_draws", B18,
    _good18,
    _formula18,
    # 朴素解:取两个最小编号组的全部球
    lambda b: b[4] + b[5],
    [4, 6, 5, 7, 9, 3, 2, 12])

# ---- 19 积木(编号×颜色):保证同编号不同颜色 -----------------------------
B19 = {"1-红": 3, "1-蓝": 2, "1-绿": 4,
       "2-红": 5, "2-蓝": 1, "2-绿": 2,
       "3-红": 2, "3-蓝": 6, "3-绿": 3,
       "4-红": 4, "4-蓝": 3, "4-绿": 1}
NUMS19 = [1, 2, 3, 4]   # 编号只有 1..4 四种
COLS19 = ["红", "蓝", "绿"]


def _good19(c):
    return any(sum(1 for col in COLS19 if c["%d-%s" % (n, col)] >= 1) >= 2
               for n in NUMS19)


add("band_worstcase-20261015-19", "min_draws", B19,
    _good19,
    # 最大坏集合:每个编号只取颜色最多的那一色
    lambda b: sum(max(b["%d-%s" % (n, col)] for col in COLS19) for n in NUMS19) + 1,
    # 朴素解:同上但不 +1
    lambda b: sum(max(b["%d-%s" % (n, col)] for col in COLS19) for n in NUMS19),
    [1, 2, 3, 4, 5, 6])


# ============================ 主流程 ============================
def solve_one(p):
    """返回 (formula 值, brute 值, 局部最大性校验结果 or None)。"""
    f = p["formula"](p["buckets"])
    if p["brute"] is not None:
        b = p["brute"](p)
        witness_ok = None
    else:
        b, witness = brute_draws(p["buckets"], p["good"])
        witness_ok = check_maximal(witness, p["buckets"], p["good"])
    return f, b, witness_ok


def main():
    if not os.path.exists(SUITE):
        print("MISSING_SUITE %s" % SUITE)
        return 1
    with open(SUITE, encoding="utf-8") as fh:
        rows = [json.loads(ln) for ln in fh if ln.strip()]
    by_id = {r["id"]: r for r in rows}

    rc = 0
    n_wit = 0
    n_wit_ok = 0
    print("LINES %d" % len(rows))
    for p in PROBS:
        pid = p["id"]
        row = by_id.get(pid)
        if row is None:
            print("MISSING_ID %s" % pid)
            rc = 1
            continue
        # 题面数字完整性
        for n in p["nums"]:
            if str(n) not in row["question"]:
                print("TEXT_MISS %s num=%s" % (pid, n))
                rc = 1
        f, b, wit = solve_one(p)
        if wit is not None:
            n_wit += 1
            n_wit_ok += 1 if wit else 0
            if not wit:
                print("WITNESS_NOT_MAXIMAL %s" % pid)
                rc = 1
        if f != b:
            print("MISMATCH %s formula=%s brute=%s" % (pid, f, b))
            rc = 1
            continue
        exp = row["expected"][p["key"]]
        if str(f) != str(exp):
            print("MISMATCH %s expected=%s solver=%s" % (pid, exp, f))
            rc = 1
            continue
        print("OK %s %s" % (pid, f))
        nv = p["naive"](p["buckets"])
        jn = str(row.get("naive"))
        ok = (str(nv) != str(f)) and (jn == str(nv))
        print("NAIVE_DISTINCT %s ok=%s" % (pid, ok))
        if not ok:
            print("  naive_solver=%s naive_jsonl=%s expected=%s" % (nv, jn, f))
            rc = 1

    print("WITNESS_MAXIMAL ok=%d/%d" % (n_wit_ok, n_wit))
    print("EXIT %d" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
