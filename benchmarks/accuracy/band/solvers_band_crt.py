# -*- coding: utf-8 -*-
"""
solvers_band_crt.py —— band_crt 批次独立复算脚本

对同目录 band_crt.jsonl 中每题,**只从题面文字**(正则抠出参数)独立重算答案,
再用 fractions.Fraction 做精确有理数运算,最后按题面要求的位数格式化。
计算过程完全不读取 expected 字段;expected 仅用于事后比对。

逐题打印: OK <id> expected=<真值> naive=<直觉错答> / MISMATCH <id> ...
并断言 naive != expected,相等则打印 NAIVE-COLLAPSE <id>。
退出码:全 OK 且无 NAIVE-COLLAPSE = 0,否则 1。

⚠ 不使用 float、不使用 decimal —— 全程 Fraction + 整数缩放,结果精确可复现。
"""

import json
import math
import os
import re
import sys
from datetime import date
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))
JSONL = os.path.join(HERE, "band_crt.jsonl")

NUM = r"\d+(?:\.\d+)?"


# ------------------------------- 工具 -------------------------------

def fmt(v, k):
    """Fraction -> 固定 k 位小数字符串,四舍五入(half-up),纯整数运算。"""
    assert isinstance(v, F), type(v)
    scale = 10 ** k
    num = v.numerator * scale
    den = v.denominator
    if num >= 0:
        q = (2 * num + den) // (2 * den)
    else:
        q = -((-2 * num + den) // (2 * den))
    if k == 0:
        return str(q)
    s = str(abs(q)).rjust(k + 1, "0")
    return ("-" if q < 0 else "") + s[:-k] + "." + s[-k:]


def nums(body):
    return [F(x) for x in re.findall(NUM, body)]


def C(n, r):
    """组合数,整数入参。"""
    if r < 0 or r > n:
        return 0
    out = 1
    for i in range(r):
        out = out * (n - i) // (i + 1)
    return out


def body_of(question):
    return question.split("【作答格式")[0].strip()


# ------------------------------- 逐题复算 -------------------------------
# 每个 solve_XX 只接收题面正文,自行抠参数;返回 (值字符串, 小数位数)。

def solve_00(b):
    # 一件商品先涨价 20%,再降价 20%。最终价格比原价低百分之几?
    a, d = [F(x) for x in re.findall(r"(\d+(?:\.\d+)?)%", b)][:2]
    v = a * d / 100                      # (1+a)(1-d) 相对原价的跌幅(%)
    return fmt(v, 1)


def solve_01(b):
    # 上山 a 千米/小时,原路下山 b 千米/小时 -> 全程平均速度
    a, c = [F(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*千米/小时", b)][:2]
    return fmt(2 * a * c / (a + c), 2)   # 等距调和平均


def solve_02(b):
    # 30 个苹果分给甲乙丙,甲比乙多 d,乙比丙多 d -> 丙
    n = nums(b)
    total, d = n[0], n[1]
    return fmt((total - 3 * d) / 3, 0)   # 丙 + (丙+d) + (丙+2d) = total


def solve_03(b):
    # 蜗牛白天爬 c 米、晚上滑 s 米,井深 D
    c, s, D = nums(b)[:3]
    if D <= c:
        return fmt(F(1), 0)
    return fmt(F(math.ceil((D - c) / (c - s)) + 1), 0)


def solve_04(b):
    # H 点 M 分,时针分针夹角
    hh, mm = nums(b)[:2]
    hour_ang = 30 * hh + mm / 2          # 时针 0.5°/分
    min_ang = 6 * mm                     # 分针 6°/分
    diff = abs(hour_ang - min_ang)
    diff = min(diff, 360 - diff)
    return fmt(diff, 1)


def solve_05(b):
    # 每 interval 分钟翻倍,从 start 个开始,hours 小时刚好装满 -> 半满时刻
    interval, start, hours = nums(b)[:3]
    assert start == 1
    total = hours * 60
    assert total % interval == 0
    return fmt(total - interval, 0)      # 少翻一倍即半满


def solve_06(b):
    # 含税价 price,税率 r% -> 不含税价
    price, r = nums(b)[:2]
    return fmt(price / (1 + r / 100), 2)


def solve_07(b):
    # 成本 c 元,售价 p 元 -> 利润率(利润/成本)
    c, p = [F(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*元", b)][:2]
    return fmt((p - c) / c * 100, 2)


def solve_08(b):
    # 打 d 折后售价 p -> 原价
    d, p = nums(b)[:2]
    return fmt(p / (d / 10), 2)


def solve_09(b):
    # 两个日期之间经过的天数
    ms = re.findall(r"(\d{4})\s*年\s*(\d+)\s*月\s*(\d+)\s*日", b)
    d1 = date(int(ms[0][0]), int(ms[0][1]), int(ms[0][2]))
    d2 = date(int(ms[1][0]), int(ms[1][1]), int(ms[1][2]))
    return fmt(F((d2 - d1).days), 0)


def solve_10(b):
    # 绳梯露出 exposed 级,涨潮上升 rise 级(船浮 -> 露出级数不变)
    total, exposed, rise = nums(b)[:3]
    assert rise < exposed and exposed < total
    return fmt(exposed, 0)


def solve_11(b):
    # 比例尺 1:scale,图上 d 厘米 -> 实际千米
    scale = F(re.search(r"1\s*:\s*(\d+)", b).group(1))
    d = F(re.search(r"(\d+(?:\.\d+)?)\s*厘米", b).group(1))
    return fmt(d * scale / 100000, 2)    # 厘米 -> 千米:除以 100000


def solve_12(b):
    # 本金 p,年利率 r%,复利 y 年
    p, r, y = nums(b)[:3]
    return fmt(p * (1 + r / 100) ** int(y), 2)


def solve_13(b):
    # 等长蜡烛可燃 a 小时 / b 小时,点燃 t 小时后剩余长度之比
    a, bb, t = nums(b)[:3]
    return fmt((1 - t / a) / (1 - t / bb), 2)


def solve_14(b):
    # n 枚均匀硬币至少一枚正面
    n = int(nums(b)[0])
    return fmt(1 - F(1, 2) ** n, 2)


def solve_15(b):
    # n 人两两握手一次
    n = int(nums(b)[0])
    return fmt(F(n * (n - 1), 2), 0)


def solve_16(b):
    # 进水管 a 小时注满,出水管 b 小时放空,同开
    a, bb = nums(b)[:2]
    return fmt(1 / (1 / a - 1 / bb), 2)


def solve_17(b):
    # 纸厚 t 毫米,对折 n 次
    t, n = nums(b)[:2]
    return fmt(t * 2 ** int(n), 1)


def solve_18(b):
    # 甲杯 V 毫升水,乙杯 M 毫升牛奶;取 v 毫升水入乙搅匀,再取 v 毫升混合液回甲
    V, M, v1, v2 = nums(b)[:4]
    assert v1 == v2
    return fmt(v2 * M / (M + v1), 2)     # 回倒液中的牛奶量 = v * M/(M+v)


def solve_19(b):
    # 正方形边长增加 p% -> 面积增加百分比
    p = nums(b)[0]
    return fmt(((1 + p / 100) ** 2 - 1) * 100, 1)


def solve_20(b):
    # N 人平均 avg 米,M 名男生平均 mavg 米 -> 女生平均
    N, avg, M, mavg = nums(b)[:4]
    return fmt((N * avg - M * mavg) / (N - M), 3)


def solve_21(b):
    # 华氏 f 度 -> 摄氏
    f = nums(b)[0]
    return fmt((f - 32) * 5 / 9, 2)


def solve_22(b):
    # 房间 L×W 米,边长 side 厘米正方形地砖
    L, W, side = nums(b)[:3]
    return fmt(L * W / (side / 100) ** 2, 0)


def solve_23(b):
    # r 个红球 + bl 个蓝球,不放回摸 draw 个,全红的概率
    r, bl, draw = [int(x) for x in nums(b)[:3]]
    return fmt(F(C(r, draw), C(r + bl, draw)), 2)


def solve_24(b):
    # 两根各烧 T 分钟的绳子计时:第一根两端 + 第二根一端,第一根烧完再点第二根另一端
    T = nums(b)[0]
    return fmt(T / 2 + (T / 2) / 2, 0)   # 30 分钟 + 剩余 30 分钟量两端烧 15 分钟


SOLVERS = {
    "band_crt-20261015-%02d" % i: globals()["solve_%02d" % i] for i in range(25)
}


def main():
    with open(JSONL, encoding="utf-8") as f:
        items = [json.loads(l) for l in f if l.strip()]

    bad = 0
    collapse = 0
    for it in items:
        _id = it["id"]
        fn = SOLVERS.get(_id)
        if fn is None:
            print("MISMATCH %s no solver" % _id)
            bad += 1
            continue
        got = fn(body_of(it["question"]))          # 从题面文字独立重算
        exp = it["expected"]
        nai = it.get("_naive")
        assert isinstance(exp, dict) and len(exp) == 1, exp
        key = next(iter(exp))
        exp_s, nai_s = exp[key], (nai or {}).get(key)

        if nai_s == exp_s:
            print("NAIVE-COLLAPSE %s expected=%s naive=%s" % (_id, exp_s, nai_s))
            collapse += 1
        if got == exp_s:
            print("OK %s expected=%s naive=%s" % (_id, got, nai_s))
        else:
            print("MISMATCH %s expected=%s solver=%s naive=%s"
                  % (_id, exp_s, got, nai_s))
            bad += 1

    print("---- total=%d ok=%d mismatch=%d collapse=%d"
          % (len(items), len(items) - bad, bad, collapse))
    return 1 if (bad or collapse) else 0


if __name__ == "__main__":
    sys.exit(main())
