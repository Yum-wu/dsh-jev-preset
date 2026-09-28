# -*- coding: utf-8 -*-
"""小样本统计:Wilson 区间与 McNemar 精确检验(标准库实现,无第三方依赖)。"""
from math import comb, sqrt


def wilson(k: int, n: int, z: float = 1.959964) -> tuple:
    """二项比例 95% Wilson 置信区间。n=0 返回 (0, 1)。"""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, center - half), min(1.0, center + half))


def mcnemar_exact(b: int, c: int) -> float:
    """配对二元结果的 McNemar 精确检验(双侧)。
    b = A 对 B 错的题数,c = A 错 B 对的题数;不一致对数为 0 时 p=1。"""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)
