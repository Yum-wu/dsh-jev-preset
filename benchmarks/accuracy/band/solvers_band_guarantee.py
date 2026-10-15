#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""solvers_band_guarantee.py —— band_guarantee.jsonl(组合保证型 20 题)独立求解器。

立场
----
本脚本**只读 question 字段的文字**,用正则把参数抠出来,再用**穷举 / 动态规划**
自己重算每题真值,然后与 expected 比对。**绝不读取 expected 参与计算**,
expected 只用于最后一步比对。

与生成器(band_guarantee.jsonl 的造题脚本)刻意使用**不同的算法**,
避免同一处编码错误在两处复现:

  族                      生成器                       本求解器
  A 摸球计数向量          全盒 itertools.product       按颜色逐步 DP(状态=已取计数的规范形)
  B/C/F 禁止对            位掩码增量 DP                按 k 从大到小穷举 itertools.combinations(真穷举)
  G 禁止三元组            位掩码增量 DP                按 k 从大到小穷举 combinations + 三元组增量判定
  D 子集和                DFS 剪枝                      DFS + 全掩码枚举 **两种方法互相校验**

退出码
  0 = 全部 OK 且无 NAIVE-COLLAPSE
  1 = 存在 MISMATCH 或 NAIVE-COLLAPSE
"""

import itertools
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
SUITE = HERE / "band_guarantee.jsonl"

CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}


# ============================ 题面解析 ============================
def parse_number_set(q):
    """解析「编号为 1, 2, 3, ..., 8 的球,共 8 个」→ (S, 声明个数)。"""
    m = re.search(r"编号为 ([^。]*?)的球,共 (\d+) 个", q)
    if not m:
        raise ValueError("无法解析编号集合")
    seg, cnt = m.group(1), int(m.group(2))
    nums = [int(x) for x in re.findall(r"\d+", seg)]
    if "..." in seg:
        start, second, last = nums[0], nums[1], nums[-1]
        step = second - start
        assert step > 0
        S = list(range(start, last + 1, step))
    else:
        S = nums
    assert len(S) == cnt, f"题面声明 {cnt} 个,解析出 {len(S)} 个"
    return S


def parse_coin_set(q):
    """解析「面值分别为 1, 2, 3, ..., 8,互不相同」→ (coins, T)。"""
    m = re.search(r"面值分别为 (.*?),互不相同", q)
    if not m:
        raise ValueError("无法解析面值集合")
    nums = [int(x) for x in re.findall(r"\d+", m.group(1))]
    if "..." in m.group(1):
        start, second, last = nums[0], nums[1], nums[-1]
        step = second - start
        coins = list(range(start, last + 1, step))
    else:
        coins = nums
    T = int(re.search(r"面值之和恰好等于 (\d+)", q).group(1))
    return coins, T


def parse_colors(q):
    """解析摸球计数向量题的 (p, cap, pred)。"""
    m = re.search(r"袋中有 (\d+) 种颜色的球,每种颜色各有 (\d+) 个", q)
    p, cap = int(m.group(1)), int(m.group(2))
    tmax = int(re.search(r"至少有一种颜色的球不少于 (\d+) 个", q).group(1))
    conds = [(CN_NUM[a], int(t)) for a, t
             in re.findall(r"至少有(一|两|三|四|五|六)种颜色的球各不少于 (\d+) 个", q)]
    all_present = bool(re.search(r"[三四五六]种颜色都至少出现 1 个", q))

    def pred(c):
        if max(c) >= tmax:
            return True
        for k, t in conds:
            if sum(1 for x in c if x >= t) >= k:
                return True
        if all_present and all(x >= 1 for x in c):
            return True
        return False

    return p, cap, pred


def classify(q):
    """按题面文字判族(不依赖 id)。"""
    if "种颜色的球" in q and "袋中有" in q:
        return "A"
    if "面值分别为" in q:
        return "D"
    if "个点排成一圈" in q:
        return "F"
    if "3 个编号互不相同的球" in q:
        return "G"
    if "编号之差恰好等于" in q:
        return "C"
    if "编号之和能被" in q and "其中两个球" in q:
        return "B"
    raise ValueError("无法判族")


# ============================ 独立求解器 ============================
def solve_A(p, cap, pred):
    """按颜色逐步 DP:状态 = 已取计数向量排序后的规范形,值 = 该状态最大总取数。

    谓词只依赖各颜色取数的**多重集**,故规范形归约与逐点穷举等价;
    每种颜色的取数在 0..cap 上**逐一枚举**(即遍历整个 (cap+1)^p 盒)。
    """
    states = {(): 0}
    for _ in range(p):
        nxt = {}
        for st, tot in states.items():
            for c in range(cap + 1):
                ns = tuple(sorted(st + (c,)))
                v = tot + c
                if nxt.get(ns, -1) < v:
                    nxt[ns] = v
        states = nxt
    best = max((v for st, v in states.items() if not pred(st)), default=-1)
    assert best >= 0, "盒内不存在坏配置?"
    return best + 1


def solve_forbidden_pairs(S, forb):
    """最大坏集 = 最大「两两不冲突」子集。k 从 n 递减穷举 combinations,首个命中即最大。"""
    n = len(S)
    cmask = [0] * n
    for i in range(n):
        for j in range(n):
            if i != j and forb(S[i], S[j]):
                cmask[i] |= 1 << j
    for k in range(n, 0, -1):
        for comb in itertools.combinations(range(n), k):
            used = 0
            ok = True
            for i in comb:
                if cmask[i] & used:
                    ok = False
                    break
                used |= 1 << i
            if ok:
                assert k < n, f"全体 {n} 个都不冲突,保证值不存在"
                return k + 1
    return 1


def solve_forbidden_triples(S, m):
    """最大坏集 = 不含「三数之和 ≡ 0 (mod m)」的子集。同样 k 递减穷举。"""
    n = len(S)
    res = [x % m for x in S]
    for k in range(n, 0, -1):
        for comb in itertools.combinations(range(n), k):
            used = 0
            pairs = 0          # 已选元素两两之和(mod m)的位集合
            ok = True
            for i in comb:
                r = res[i]
                if (pairs >> ((-r) % m)) & 1:      # 与已选两元素凑成 0
                    ok = False
                    break
                t = used
                while t:
                    l = t & -t
                    pairs |= 1 << ((r + res[l.bit_length() - 1]) % m)
                    t ^= l
                used |= 1 << i
            if ok:
                assert k < n, f"全体 {n} 个都无零和三元组,保证值不存在"
                return k + 1
    return 1


def _subset_sum_dfs(coins, T):
    n = len(coins)
    best = 0
    stack = [(0, 1, 0)]        # (下一个下标, 可达和位掩码, 已选个数)
    while stack:
        i, reach, sz = stack.pop()
        if (reach >> T) & 1:   # 已能凑出 T → 其所有超集都能,剪枝
            continue
        if sz > best:
            best = sz
        if i == n:
            continue
        c = coins[i]
        stack.append((i + 1, reach, sz))
        stack.append((i + 1, reach | (reach << c), sz + 1))
    return best + 1


def _subset_sum_fullmask(coins, T):
    """第二种方法:全掩码枚举 + 增量可达集,用于互相校验。"""
    n = len(coins)
    reach = [1] * (1 << n)
    best = 0
    for mask in range(1, 1 << n):
        low = mask & -mask
        i = low.bit_length() - 1
        rest = mask ^ low
        r = reach[rest] | (reach[rest] << coins[i])
        reach[mask] = r
        if not (r >> T) & 1:
            s = bin(mask).count("1")
            if s > best:
                best = s
    return best + 1


def solve_D(coins, T):
    a = _subset_sum_dfs(coins, T)
    if len(coins) <= 20:
        b = _subset_sum_fullmask(coins, T)
        assert a == b, f"D 族两种方法不一致 dfs={a} fullmask={b}"
    return a


# ============================ 主流程 ============================
def solve_from_text(q):
    fam = classify(q)
    if fam == "A":
        p, cap, pred = parse_colors(q)
        return fam, solve_A(p, cap, pred), (cap + 1) ** p
    if fam == "D":
        coins, T = parse_coin_set(q)
        return fam, solve_D(coins, T), 2 ** len(coins)
    if fam == "F":
        n = int(re.search(r"有 (\d+) 个点排成一圈", q).group(1))
        steps = {int(x) for x in re.findall(r"\d+", re.search(r"属于集合 \{([\d, ]+)\}", q).group(1))}

        def forb(a, b):
            dd = abs(a - b) % n
            return min(dd, n - dd) in steps

        S = list(range(1, n + 1))
        return fam, solve_forbidden_pairs(S, forb), 2 ** n
    if fam == "G":
        S = parse_number_set(q)
        m = int(re.search(r"编号之和能被 (\d+) 整除", q).group(1))
        return fam, solve_forbidden_triples(S, m), 2 ** len(S)
    if fam == "C":
        S = parse_number_set(q)
        d = int(re.search(r"编号之差恰好等于 (\d+)", q).group(1))
        return fam, solve_forbidden_pairs(S, lambda a, b: abs(a - b) == d), 2 ** len(S)
    if fam == "B":
        S = parse_number_set(q)
        m = int(re.search(r"编号之和能被 (\d+) 整除", q).group(1))
        return fam, solve_forbidden_pairs(S, lambda a, b: (a + b) % m == 0), 2 ** len(S)
    raise ValueError(fam)


def main() -> int:
    rows = [json.loads(l) for l in SUITE.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"# suite={SUITE.name} cases={len(rows)}")
    bad = 0
    collapse = 0
    for r in rows:
        pid = r["id"]
        q = r["question"]
        # 只从题面取参数;expected 不参与计算
        fam, mine, space = solve_from_text(q)
        exp_obj = r["expected"]
        nai_obj = r["_naive"]
        exp = exp_obj["answer"] if isinstance(exp_obj, dict) else exp_obj
        nai = nai_obj["answer"] if isinstance(nai_obj, dict) else nai_obj
        exp_i, nai_i = int(exp), int(nai)
        if mine == exp_i:
            print(f"OK {pid} expected={exp_i} naive={nai_i}   [fam={fam} space={space} scale={r.get('_scale')}]")
        else:
            print(f"MISMATCH {pid} expected={exp_i} mine={mine}   [fam={fam} space={space}]")
            bad += 1
        if nai_i == exp_i:
            print(f"NAIVE-COLLAPSE {pid} expected={exp_i} naive={nai_i}")
            collapse += 1
    print(f"# summary: cases={len(rows)} mismatch={bad} naive_collapse={collapse} "
          f"verdict={'PASS' if (bad == 0 and collapse == 0) else 'FAIL'}")
    return 0 if (bad == 0 and collapse == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
