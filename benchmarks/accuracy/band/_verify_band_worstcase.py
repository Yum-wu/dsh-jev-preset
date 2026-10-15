# -*- coding: utf-8 -*-
"""独立复核 band_worstcase 的 expected —— 作者:大肥鱼(第三方实现,与造题路无关)

通用建模:「最少取 k 个才能保证性质 P」== (最大不满足 P 的子集大小) + 1。
每题用暴力枚举重算该最大值,再与 jsonl 的 expected 对比。
"""
import json, sys, itertools

P = r"C:\Users\Yum\Desktop\DeepSeekHarness\plugins\dsh-jev-preset\benchmarks\accuracy\band\band_worstcase.jsonl"


def max_bad(counts, ok, n_types=None):
    """在类型计数向量上暴力求「不满足 ok」的最大总元素数。counts = 每类型上限。"""
    best = 0
    ranges = [range(c + 1) for c in counts]
    for vec in itertools.product(*ranges):
        if not ok(vec):
            s = sum(vec)
            if s > best:
                best = s
    return best


def main():
    rows = [json.loads(l) for l in open(P, encoding="utf-8") if l.strip()]
    got = {}

    # 00 红7 蓝5 绿9 白4; P: 有红且有蓝
    got["-00"] = max_bad([7, 5, 9, 4], lambda v: v[0] >= 1 and v[1] >= 1) + 1
    # 01 黑12 灰7 蓝2 棕5 白11; P: 某色 >=4(坏向量各色 <=3,故 cap=3 等价)
    got["-01"] = max_bad([3, 3, 2, 3, 3], lambda v: max(v) >= 4) + 1
    # 02 圆:苹6桃9西5 星:苹4桃3西3; P: 某口味圆星都有
    got["-02"] = max_bad([6, 9, 5, 4, 3, 3],
                         lambda v: any(v[f] >= 1 and v[f + 3] >= 1 for f in range(3))) + 1
    # 03 39 件 9 件不合格; P: >=1 不合格
    got["-03"] = max_bad([30, 9], lambda v: v[1] >= 1) + 1
    # 04 20 用户 6 种组合; P: 某组合 >=3(坏向量每类 <=2,cap=2 等价)
    got["-04"] = max_bad([2] * 6, lambda v: max(v) >= 3) + 1
    # 05 20 节点恰 4 缺陷; P: 发现 >=3 缺陷
    got["-05"] = max_bad([16, 4], lambda v: v[1] >= 3) + 1
    # 06 库存 12 9 4 7 6; P: 5 款集齐
    got["-06"] = max_bad([12, 9, 4, 7, 6], lambda v: all(x >= 1 for x in v)) + 1
    # 07 9 仓位恰 4 浮亏; P: 平掉 >=2 浮亏
    got["-07"] = max_bad([5, 4], lambda v: v[1] >= 2) + 1
    # 08 3 关键包,链路最多丢 6; 逐副本数暴力 + 对抗分配暴力
    best08 = None
    for c in itertools.product(range(1, 9), repeat=3):
        ok = True
        for d in itertools.product(*[range(x + 1) for x in c]):
            if sum(d) <= 6 and any(d[i] == c[i] for i in range(3)):
                ok = False
                break
        if ok:
            s = sum(c)
            if best08 is None or s < best08:
                best08 = s
    got["-08"] = best08
    # 09 6 点数 × 4 张; P: 某点数 >=3(坏向量每类 <=2,cap=2 等价)
    got["-09"] = max_bad([2] * 6, lambda v: max(v) >= 3) + 1
    # 10 一排 10 座; P: 有相邻两人 —— 直接暴力座位子集
    best10 = 0
    for mask in range(1 << 10):
        seats = [i for i in range(10) if mask >> i & 1]
        if all(seats[i + 1] - seats[i] > 1 for i in range(len(seats) - 1)):
            best10 = max(best10, len(seats))
    got["-10"] = best10 + 1
    # 11 3 机房; P: 任一机房下线后剩余 >=6 —— 暴力总数
    best11 = None
    for tot in range(1, 40):
        found = False
        for a in range(tot + 1):
            for b in range(tot - a + 1):
                c = tot - a - b
                if min(b + c, a + c, a + b) >= 6:
                    found = True
        if found:
            best11 = tot
            break
    got["-11"] = best11
    # 12 A9 B7 O5 AB3; P: O>=2 且 AB>=1
    got["-12"] = max_bad([9, 7, 5, 3], lambda v: v[2] >= 2 and v[3] >= 1) + 1
    # 13 档位 1..4 库存 8 6 9 5; P: 存在两档相差 >=2
    got["-13"] = max_bad([8, 6, 9, 5],
                         lambda v: any(v[i] >= 1 and v[j] >= 1
                                       for i in range(4) for j in range(4) if abs(i - j) >= 2)) + 1
    # 14 5 知识点 12 9 7 15 4; P: 覆盖 >=4 个知识点
    got["-14"] = max_bad([12, 9, 7, 15, 4],
                         lambda v: sum(1 for x in v if x >= 1) >= 4) + 1
    # 15 手套 7 5 9 4 6; P: >=2 色各自 >=2
    got["-15"] = max_bad([7, 5, 9, 4, 6],
                         lambda v: sum(1 for x in v if x >= 2) >= 2) + 1
    # 16 批次 6 8 4 9 7; P: 某批次被抽空
    got["-16"] = max_bad([6, 8, 4, 9, 7],
                         lambda v: any(v[i] == [6, 8, 4, 9, 7][i] for i in range(5))) + 1
    # 17 9 类各 >=5; P: 某类 >=3(坏向量每类 <=2,cap=2 等价)
    got["-17"] = max_bad([2] * 9, lambda v: max(v) >= 3) + 1
    # 18 编号 4:6 5:5 7:4 9:3; P: 存在两球编号和 >=12
    labs = [4, 5, 7, 9]
    got["-18"] = max_bad([6, 5, 4, 3],
                         lambda v: any(v[i] >= (2 if i == j else 1) and
                                       labs[i] + labs[j] >= 12
                                       for i in range(4) for j in range(i, 4)
                                       if v[i] >= 1 and v[j] >= 1)) + 1
    # 19 4 编号 × 3 色; P: 同编号不同色
    cnt = [[3, 2, 4], [5, 1, 2], [2, 6, 3], [4, 3, 1]]
    best19 = 0
    for pick in itertools.product(*[range(3) for _ in range(4)]):
        s = sum(cnt[k][pick[k]] for k in range(4))
        best19 = max(best19, s)
    got["-19"] = best19 + 1

    bad = 0
    for r in rows:
        key = r["id"].split("-")[-1]
        e = r["expected"]
        k = list(e.keys())[0]
        exp = e[k]
        mine = str(got["-" + key])
        ok = (str(exp) == mine)
        if not ok:
            bad += 1
        print(("OK  " if ok else "BAD ") + r["id"] + "  expected=" + str(exp) + "  mine=" + mine)
    print("# summary: cases=%d bad=%d verdict=%s" % (len(rows), bad, "PASS" if bad == 0 else "FAIL"))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
