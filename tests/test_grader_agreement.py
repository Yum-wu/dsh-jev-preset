# -*- coding: utf-8 -*-
"""
B5:判分器口径 —— `compare` 只报 McNemar,**没有任何一致性指标**。

缺口(附录 B5,依据 arXiv:2406.12624):
  LLM-as-judge 论文指出:即便两判分器 **>90% 一致**,仍可能存在 **10+ 分**的系统性差异
  (percent agreement 高,是因为类别极不平衡时「都判错」也算一致)。
  本仓现状更严重:`compare()` 只返回 `{pairs, only_a, only_b, mcnemar_p}` ——
  **连 percent agreement 都没有**,更不用说校正随机一致的 Scott's π / Cohen's κ。

  后果:
  ① McNemar **只看不一致对**,对「两边一致但都错」完全无感 ——
     而「都错」恰恰是判分器系统性偏差的藏身处;
  ② 没有任何数字能回答「换判分器后,绝对分数会变多少」——
     而本仓所有结论(+89pp / p=0.0312)都建立在**某一个**判分器上;
  ③ 类别不平衡时 percent agreement 会被抬高,不加 κ/π 就是在自欺。

判据(预注册,R9):
  T1 `compare` 必须返回**一致性指标**,且至少含:
     - percent agreement(朴素一致率)
     - 校正随机一致的指标(Scott's π 或 Cohen's κ)
     - 二者的**差**,即「有多少一致来自类别不平衡」
  T2 指标必须能由**配对结果表**独立复算(不依赖 compare 的其他输出)
  T3 必须**同时**保留 McNemar —— 它测的是不一致对的方向,π 测的是整体一致,二者不可互替
  T4 极端构造下 π 必须体现「不平衡惩罚」:两判分器都恒判同一类时 π 应显著低于 agreement
"""
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "benchmarks", "accuracy"))

from jevbench.grading import compare  # noqa: E402


def _graded(pairs, no_answer=False, kind="numeric"):
    """构造最小 graded 列表:pairs = [(case_id, rep, a_correct, b_correct), ...]"""
    out = []
    for cfgname, i in (("A", 2), ("B", 3)):
        for p in pairs:
            row = {"config": cfgname, "case_id": p[0], "rep": p[1], "kind": kind,
                   "category": "tick", "correct": p[i], "no_answer": no_answer}
            if kind == "gate":
                row["expected"] = {"expect_three_path": False, "expect_reason": "test"}
            out.append(row)
    return out


def _scotts_pi(n11, n10, n01, n00):
    """独立实现,用来复算 compare 的输出(不复用被测代码)。

    ⚠ 已知局限(红队 8c9dff71 反证 M9):本实现与生产端**逐行同构**,
    两者可能共享同一个概念错误。这里刻意让退化分支返回 None 而**不是**复制生产端 ——
    生产端的退化 bug 正是红队挖出来的,复制就等于把 bug 一起写进测试。
    """
    n = n11 + n10 + n01 + n00
    if n == 0:
        return None
    po = (n11 + n00) / n
    pa1 = (n11 + n10) / n
    pa2 = (n11 + n01) / n
    pe = pa1 * pa2 + (1 - pa1) * (1 - pa2)
    if abs(1 - pe) < 1e-12:
        return None          # π 在此数学上未定义
    return (po - pe) / (1 - pe)

class TestGraderAgreementMetrics(unittest.TestCase):

    def test_T1_compare_reports_agreement_metrics(self):
        r = compare(_graded([
            ("c1", 0, True, True),
            ("c2", 0, True, True),
            ("c3", 0, False, True),
            ("c4", 0, False, False),
        ]), "A", "B")

        for key in ("agreement", "scotts_pi", "pi_defined",
                    "no_answer_pairs", "n_gate_excluded"):
            with self.subTest(指标=key):
                self.assertIn(key, r,
                    f"compare() 未返回 {key} —— 无一致性指标就无法量化"
                    f"「换配置后判定会变多少」")
        # McNemar 必须保留(它测不一致对方向,与 π 不可互替)
        self.assertIn("mcnemar_p", r, "compare() 丢了 McNemar —— π 不能替代它")
        # 不该有冗余派生量(红队 8c9dff71:恒等式证明它零独立信息)
        self.assertNotIn("agreement_minus_pi", r,
            "agreement_minus_pi 是 agreement 与 π 的严格函数,零独立信息,且在退化场景"
            "恒为 1.0 反而放大错误可读性 —— 不该作为独立字段出货")

    def test_T2_metrics_recomputable_from_contingency(self):
        """指标必须能由 2×2 配对表独立复算。"""
        pairs = [
            ("c1", 0, True, True),
            ("c2", 0, True, True),
            ("c3", 0, True, False),
            ("c4", 0, False, False),
            ("c5", 0, False, False),
        ]
        r = compare(_graded(pairs), "A", "B")
        n11 = sum(1 for p in pairs if p[2] and p[3])
        n10 = sum(1 for p in pairs if p[2] and not p[3])
        n01 = sum(1 for p in pairs if not p[2] and p[3])
        n00 = sum(1 for p in pairs if not p[2] and not p[3])
        n = len(pairs)

        # compare() 对输出做了 round(6)(报告用,避免浮点尾巴刷屏),
        # 故复算比较也放到同一精度 —— 用 9 位比较会因舍入而误报。
        self.assertAlmostEqual(r["agreement"], round((n11 + n00) / n, 6), places=9,
            msg="percent agreement 与独立复算不符")
        self.assertAlmostEqual(r["scotts_pi"], round(_scotts_pi(n11, n10, n01, n00), 6),
            places=9, msg="Scott's π 与独立复算不符")

    def test_T3_pi_corrects_random_agreement(self):
        """π 必须**校正随机一致**;同样的分歧比例下,边际越不平衡,agreement 越虚高。

        判据修正(我连错两次,记下来):
          第一次以为「完全一致时 π 应接近 0」—— 错,π 度量「比随机好多少」,满分是 1;
          第二次以为「完全一致 + 不平衡 → π < 1」—— 也错,**完全一致时 n10=n01=0,
          po=pe=1,π 恒等于 1,与边际分布无关**。随机一致校正只对**有分歧**的数据起作用。
        """
        # 有少量分歧 + 强不平衡
        imb = ([(f"t{i}", 0, True, True) for i in range(90)] +
               [(f"f{i}", 0, False, False) for i in range(8)] +
               [("d1", 0, True, False), ("d2", 0, False, True)])
        ri = compare(_graded(imb), "A", "B")
        self.assertGreater(ri["agreement"], 0.95, "构造应保持高一致率")
        self.assertLess(ri["scotts_pi"], ri["agreement"],
            "强不平衡下 π 必须明显低于 agreement —— 这正是 percent agreement 掩盖的部分")
        gap_imb = ri["agreement"] - ri["scotts_pi"]

        # 对照:同样的分歧比例,但类别平衡 → 差距明显更小
        bal = ([(f"t{i}", 0, True, True) for i in range(49)] +
               [(f"f{i}", 0, False, False) for i in range(49)] +
               [("d1", 0, True, False), ("d2", 0, False, True)])
        rb = compare(_graded(bal), "A", "B")
        gap_bal = rb["agreement"] - rb["scotts_pi"]
        self.assertGreater(
            gap_imb, gap_bal,
            "同样 2 题分歧,不平衡数据的 agreement-π 差距必须更大 —— "
            "否则 π 没在校正随机一致")

    def test_T4_perfect_agreement_gives_pi_one(self):
        """完全一致时 π = 1(与边际无关),这是 π 的定义,须锁定防回归。"""
        pairs = ([(f"t{i}", 0, True, True) for i in range(90)] +
                 [(f"f{i}", 0, False, False) for i in range(10)])
        r = compare(_graded(pairs), "A", "B")
        self.assertAlmostEqual(r["agreement"], 1.0, places=9)
        self.assertAlmostEqual(r["scotts_pi"], 1.0, places=6,
            msg="完全一致(n10=n01=0)时 po=pe=1,π 必然为 1")

    def test_T5_degenerate_pi_is_none_not_zero(self):
        """★ 红队 8c9dff71 的决定性反证:π **未定义**时必须报 None,不能报 0.0。

        实测原实现在真实题集上的表现:两配置**全对**(最好结果)时
        `pe == 1` → π 为 0/0 未定义 → 旧代码返回 0.0,
        报告里读起来像「完全一致里 100% 来自不平衡」,**语义完全反了**。
        """
        all_right = [(f"c{i}", 0, True, True) for i in range(73)]
        r = compare(_graded(all_right), "A", "B")
        self.assertFalse(r["pi_defined"],
            "pe==1 时 π 数学未定义,pi_defined 必须为 false")
        self.assertIsNone(r["scotts_pi"],
            "π 未定义时必须为 None —— 报 0.0 会让「最好结果」读起来像「最差结果」")

        # 「全错但一致」同样是 pe==1 的退化情形
        all_wrong = [(f"c{i}", 0, False, False) for i in range(73)]
        r2 = compare(_graded(all_wrong), "A", "B")
        self.assertFalse(r2["pi_defined"],
            "全错一致(pe==1)同样退化,pi_defined 必须为 false")
        self.assertIsNone(r2["scotts_pi"], "全错一致时 π 也未定义,必须是 None")

    def test_T6_no_answer_pairs_excluded_from_agreement(self):
        """R5:「没答」与「答错」必须分开 —— 无答案的对**不计入**一致率。

        红队 8c9dff71 实测:原实现不过滤 `no_answer`,
        两边同一条都没答会被算成「一致」,π 完全看不见这个失败模式。
        """
        # 两边同一条 no_answer,加上 1 条正常对
        rows = _graded([("c1", 0, True, True)])
        rows += [{"config": c, "case_id": "na1", "rep": 0, "kind": "numeric",
                  "category": "tick", "correct": False, "no_answer": True}
                 for c in ("A", "B")]
        r = compare(rows, "A", "B")
        self.assertEqual(r["no_answer_pairs"], 1, "no_answer 对必须被单列统计")
        self.assertEqual(r["pairs"], 1, "no_answer 对不得计入一致率的分母")
        self.assertAlmostEqual(r["agreement"], 1.0, places=9,
            msg="剔除 no_answer 后只剩 1 条正常对,agreement 应为 1.0")

    def test_T7_gate_exclusion_is_reported(self):
        """gate 题被剔除时必须在返回值里报数,否则 π 的覆盖率不可见。"""
        rows = _graded([("c1", 0, True, True)], kind="numeric")
        rows += _graded([("g1", 0, False, False)], kind="gate")
        r = compare(rows, "A", "B")
        self.assertEqual(r["n_gate_excluded"], 2,
            "gate 题被静默剔除,必须报数(红队:90 题丢 17 题而读者不知道)")

    def test_T8_asymmetric_key_sets_are_not_crashed(self):
        """两配置**键集不等**时必须只取交集,不得崩或把缺失当 False。

        红队 8c9dff71 变异 M6(交集改并集)存活 —— 因为原夹具**两边键集恒等**,
        非对称路径零覆盖。真实场景常是「某配置 run 少了几条」,那正是并集会 KeyError 的地方。
        """
        # A 有 c1,c2,c3;B 只有 c1,c2 —— B 少跑了一条
        a = [{"config": "A", "case_id": cid, "rep": 0, "kind": "numeric",
              "category": "tick", "correct": True, "no_answer": False}
             for cid in ("c1", "c2", "c3")]
        b = [{"config": "B", "case_id": cid, "rep": 0, "kind": "numeric",
              "category": "tick", "correct": True, "no_answer": False}
             for cid in ("c1", "c2")]
        r = compare(a + b, "A", "B")
        self.assertEqual(r["pairs"], 2,
            "键集不等时只应取交集 2 条;取并集会 KeyError 或把缺失当 False")

    def test_T8b_rep_alignment(self):
        """多次重复(rep)必须按 (case_id, rep) 配对,不能跨 rep 错配。"""
        rows = []
        for cid in ("c1", "c2"):
            for rep in (0, 1):
                rows += [{"config": "A", "case_id": cid, "rep": rep, "kind": "numeric",
                          "category": "tick", "correct": True, "no_answer": False},
                         {"config": "B", "case_id": cid, "rep": rep, "kind": "numeric",
                          "category": "tick", "correct": True, "no_answer": False}]
        r = compare(rows, "A", "B")
        self.assertEqual(r["pairs"], 4, "2 题 × 2 次重复 = 4 对,必须按 rep 分别配对")

    def test_T4_near_zero_agreement_detected(self):
        """近乎完全不一致时,agreement 与 π 都应低 —— 用于排查「判分器对不上」。"""
        pairs = ([(f"a{i}", 0, True, False) for i in range(5)] +
                 [(f"b{i}", 0, False, True) for i in range(5)])
        r = compare(_graded(pairs), "A", "B")
        self.assertLess(r["agreement"], 0.1, "近乎全不一致时 agreement 应接近 0")
        self.assertLess(r["scotts_pi"], 0.0, "全不一致时 π 应为负(比随机还差)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
