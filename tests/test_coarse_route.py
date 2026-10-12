# -*- coding: utf-8 -*-
"""
⑤ 粗档分层(2026-10-13):`coarse_route` 与 `is_three_path` 必须**两套独立表对拍一致**。

需求原文是「首行 3~4 个粗档」。本仓**只落地了判分侧的派生粗档**,没有改 persona 的
输出协议 —— 理由写在 `jevbench/extract.py` 的 `coarse_route` 上方(可测的三条:
前提无实测支撑 / 改协议打断 901 条历史语料的可比性 / 白名单法已把 12 条压成二值)。

本测试的**核心判据不是「粗档函数返回了我写的值」**(那是同义反复,本仓 H9 的① 踩过),
而是:**两张表 —— `_COARSE_BY_PREFIX` 与 `_SINGLE_PATH_PREFIXES` —— 独立写就,
对 persona 里每一个真实标识必须给出同一个「是不是多路」的答案。**

判据来源是 **persona 原文**,不是手抄表(复用 `test_route_classification.persona_route_table`,
单一来源,避免第二份副本)。
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
BENCH = os.path.join(PLUGIN_ROOT, "benchmarks", "accuracy")
sys.path.insert(0, BENCH)
sys.path.insert(0, HERE)

from jevbench.extract import (  # noqa: E402
    COARSE_DIRECT,
    COARSE_MULTI,
    COARSE_SINGLE,
    COARSE_UNKNOWN,
    _COARSE_BY_PREFIX,
    _SINGLE_PATH_PREFIXES,
    coarse_route,
    is_three_path,
)
from test_route_classification import persona_route_table  # noqa: E402

#: 三个**真实**粗档(不含 `未登记` 哨兵)。
REAL_BUCKETS = (COARSE_DIRECT, COARSE_SINGLE, COARSE_MULTI)


class TestCoarseRoute(unittest.TestCase):

    def setUp(self):
        self.table = persona_route_table()
        self.assertGreater(len(self.table), 8, "从 persona 抽到的路由表过小,解析可能失效")

    # ── T1 形状:恰好 3 个真实粗档(+1 哨兵),满足需求「3~4 个粗档」 ──────────
    def test_T1_three_real_buckets_plus_one_sentinel(self):
        self.assertEqual(len(set(REAL_BUCKETS)), 3, "三个真实粗档必须互不相同")
        self.assertNotIn(COARSE_UNKNOWN, REAL_BUCKETS, "哨兵不得与真实粗档重名")
        # 需求给的是 3~4 档;本仓取 3 + 哨兵。超出范围就必须回看这条判据。
        self.assertLessEqual(len(REAL_BUCKETS), 4)

    # ── T2 persona 全表必须都能映射,不得落进哨兵 ──────────────────────────
    def test_T2_every_persona_marker_maps_to_a_real_bucket(self):
        unmapped = sorted(m for m in self.table if coarse_route(m) == COARSE_UNKNOWN)
        self.assertEqual(
            unmapped, [],
            f"persona 里这些标识没在 _COARSE_BY_PREFIX 登记:{unmapped} "
            "—— 新增标识时必须同步登记,否则它会在聚合里静默消失",
        )

    # ── T3 对拍:两张独立表对每个真实标识给出同一个「是否多路」 ────────────
    def test_T3_two_independent_tables_agree_on_every_persona_marker(self):
        disagreements = []
        for marker in sorted(self.table):
            by_coarse = coarse_route(marker) == COARSE_MULTI
            by_whitelist = is_three_path(marker)
            if by_coarse != by_whitelist:
                disagreements.append(
                    f"{marker!r}: coarse={coarse_route(marker)} whitelist={by_whitelist}"
                )
        self.assertEqual(
            disagreements, [],
            "两套表对同一标识给出相反的「是否多路」判据(白名单法宁可漏报也不虚报,"
            "粗档若把单路标成多路就是**虚报交叉验证**):\n" + "\n".join(disagreements),
        )

    # ── T4 前缀顺序陷阱:两条共享前缀、物理行为相反的标识不得并档 ─────────
    def test_T4_shared_prefix_markers_are_not_merged(self):
        # 这两条在 persona 里**同时存在**,且共享前缀 `断言不适用`。
        # 表按前缀比对 ⇒ 更长的必须排在前面,否则「换模型」会被「转三路」吃掉。
        self.assertIn("断言不适用-转三路", self.table, "persona 表里应仍有这条")
        self.assertIn("断言不适用-换模型", self.table, "persona 表里应仍有这条")
        self.assertEqual(coarse_route("断言不适用-转三路"), COARSE_MULTI)
        self.assertEqual(coarse_route("断言不适用-换模型"), COARSE_SINGLE)

    # ── T5 单路白名单必须被粗档表覆盖,且「零验证动作」的那条单独成档 ──────
    def test_T5_coarse_table_covers_every_single_path_prefix(self):
        # 不变量:白名单判「单路」的每一条,粗档都不许是「多路」——否则就是虚报交叉验证。
        wrong = []
        for prefix in _SINGLE_PATH_PREFIXES:
            bucket = coarse_route(prefix)
            if bucket not in (COARSE_SINGLE, COARSE_DIRECT):
                wrong.append(f"{prefix!r} -> {bucket}")
        self.assertEqual(
            wrong, [],
            "_SINGLE_PATH_PREFIXES 里的单路前缀被粗档表判成了多路(虚报交叉验证):\n"
            + "\n".join(wrong),
        )

        # 且**恰好一条**白名单前缀属于「直出」档 —— 它必须就是 Fast-Pass。
        # 这条把「Fast-Pass 单独成档」从口味变成判据:多一条少一条都红。
        direct_prefixes = sorted(
            p for p in _SINGLE_PATH_PREFIXES if coarse_route(p) == COARSE_DIRECT
        )
        self.assertEqual(
            direct_prefixes, ["fast-pass"],
            "「零验证动作」档应当且只应当由 fast-pass 占据;实际:"
            f"{direct_prefixes}",
        )

        # 反向:粗档表里判「直出」的条目也必须都在白名单里(不许有表外特权)。
        coarse_direct = sorted(p for p, b in _COARSE_BY_PREFIX if b == COARSE_DIRECT)
        self.assertEqual(
            coarse_direct, ["fast-pass"],
            f"粗档表里判「直出」的条目:{coarse_direct}",
        )

    # ── T6 哨兵可证伪:没登记的标识必须显式可见,不静默并档 ────────────────
    def test_T6_unknown_marker_is_visible_not_silently_bucketed(self):
        self.assertEqual(coarse_route("随便什么"), COARSE_UNKNOWN)
        self.assertEqual(coarse_route("x"), COARSE_UNKNOWN)
        self.assertEqual(coarse_route(""), COARSE_UNKNOWN)
        self.assertEqual(coarse_route(None), COARSE_UNKNOWN)

    # ── T7 大小写不敏感(与 extract_route 的容错口径一致) ────────────────
    def test_T7_case_insensitive(self):
        for variant in ("fast-pass", "Fast-Pass", "FAST-PASS", "Fast-pass"):
            self.assertEqual(coarse_route(variant), COARSE_DIRECT, variant)
        self.assertEqual(coarse_route("Rerank Pick #2 - 红队 Verified"), COARSE_MULTI)
        self.assertEqual(coarse_route("rerank pick #2 - 红队 verified"), COARSE_MULTI)

    # ── T8 粗档是纯派生量:不得改变 is_three_path 的任何行为 ────────────────
    def test_T8_coarse_route_is_pure_and_does_not_shadow_the_binary(self):
        # 同一标识连问两次必须同答案(无隐藏状态),且 is_three_path 的答案不受影响。
        for marker in sorted(self.table):
            first = coarse_route(marker)
            self.assertEqual(coarse_route(marker), first, f"{marker} 不是纯函数")
            self.assertIsInstance(is_three_path(marker), bool)


if __name__ == "__main__":
    unittest.main(verbosity=2)
