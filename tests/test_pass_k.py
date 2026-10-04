# -*- coding: utf-8 -*-
r"""
B3:无 pass^k / 稳定性指标 —— 所有实验都是单次运行,只报 pass@1。

缺口(附录 B3,依据 Anthropic《Demystifying evals》):
  「工具用 pass@k、agent 用 **pass^k**」—— 后者衡量**一致性**:同一题跑 k 次是否**每次都**对。
  文中给的直觉数字:单次通过率 0.75 时,(0.75)³ ≈ 42% —— 也就是
  「看起来 75% 稳的模型,跑三次全对的只有 42%」。这个差距在单次实验里**完全看不见**。

本仓现状(2026-10-01 实测):
  - 全部 10 个 `_runs-*.jsonl` 里,9 个 `rep` 全为 0(单次);
    唯一的例外 `_runs-c3fail-retry.jsonl` 是 {0:2, 1:2, 2:2}(失败的补跑,不是独立重复)。
  - `jevbench/` 全目录 grep `pass\^|pass_k|passk|stability` **零命中**。

后果:本仓所有结论(+89pp / p=0.0312 / 增益 0)都建立在 **pass@1** 上,
既没有 pass^k,也没有「一致性」这个维度。三路的「3/3 独立收敛」在实验层面
其实正是 pass^3 的概念,但没有任何代码计算它 —— 概念存在,度量不存在。

判据(预注册,R9):
  T1 必须能计算 pass^k(同一配置、同一题,k 次重复**全对**的比例),
     而不是 pass@k(至少一次对)—— 后者对 agent 无意义。
  T2 必须能计算逐题的稳定性画像(全对 / 波动 / 全错),因为它决定
     「这批题能不能区分模型」—— 全对全错的题没有区分力。
  T3 k=1 时 pass^k 必须**等于** pass@1(定义自洽,不能另起一套口径)。
  T4 数据不足(k<2)时必须显式报告「不可算」,**不得**用 k=1 的数据冒充 pass^k。
  T5 采样独立性(R3)必须被显式记录:同一 case_id 的多次 rep 才是 pass^k 的样本,
     跨 case 聚合的「平均通过率」不是一致性。
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "benchmarks", "accuracy"))

from jevbench.passk import pass_at_1, pass_at_k, pass_at_kk, stability_profile  # noqa: E402


def _runs(rows):
    """rows = [(case_id, rep, correct), ...] → grade_runs 风格的最小结构。

    `route` 必须带上:`summarize` 会读它统计错误共识(缺键会 KeyError)。
    """
    return [{"config": "C1", "case_id": cid, "rep": rep, "kind": "numeric",
             "category": "tick", "correct": c, "no_answer": False,
             "route": "断言通过", "run_error": False}
            for cid, rep, c in rows]


class TestPassK(unittest.TestCase):

    def test_T1_pass_k_is_all_correct_not_any(self):
        """pass^k = k 次**全对**;pass@k = 至少一次对。两者不可混用。"""
        # 一题跑了 3 次:对、错、错 → pass@3 = True(至少一次对),pass^3 = False(非全对)
        rows = _runs([("c1", 0, True), ("c1", 1, False), ("c1", 2, False)])
        self.assertTrue(pass_at_k(rows, k=3), "pass@3 应为 True(至少一次对)")
        self.assertFalse(pass_at_kk(rows, k=3), "pass^3 应为 False(3 次没有全对)")

    def test_T2_stability_profile_distinguishes_volatile(self):
        """稳定性画像必须区分「稳定对 / 波动 / 稳定错」—— 这决定题有没有区分力。"""
        rows = _runs([
            ("stable", 0, True), ("stable", 1, True), ("stable", 2, True),
            ("volatile", 0, True), ("volatile", 1, False), ("volatile", 2, True),
            ("broken", 0, False), ("broken", 1, False), ("broken", 2, False),
        ])
        prof = stability_profile(rows, k=3)
        # 2026-10-01:分组键改为 (seed, case_id)(R3 独立性),断言同步
        self.assertEqual([c for _k, _s, c in prof["stable_pass"]], ["stable"],
            "恒对题必须被识别为「稳定对」")
        self.assertEqual([c for _k, _s, c in prof["volatile"]], ["volatile"],
            "有对有错的题必须被识别为「波动」")
        self.assertEqual([c for _k, _s, c in prof["always_wrong"]], ["broken"],
            "恒错题必须被识别为「稳定错」")
        self.assertEqual(prof["insufficient_reps"], [],
            "三题都跑满 3 次,不应有「重复不足」的题")

    def test_T3_k1_degenerates_to_pass_at_1(self):
        """k=1 时 pass^k 必须等于 pass@1 —— 定义自洽,不能另起口径。"""
        rows = _runs([("a", 0, True), ("b", 0, False), ("c", 0, True)])
        self.assertAlmostEqual(pass_at_1(rows), 2 / 3, places=9)
        self.assertAlmostEqual(pass_at_kk(rows, k=1), 2 / 3, places=9,
            msg="k=1 时 pass^k 与 pass@1 必须相等")

    def test_T4_insufficient_reps_is_reported_not_faked(self):
        """重复不足的题必须被标出,**不得**用 k=1 的数据冒充 pass^k。"""
        rows = _runs([
            ("a", 0, True), ("a", 1, True), ("a", 2, True),   # 满 3 次
            ("b", 0, True),                                      # 只跑 1 次
        ])
        prof = stability_profile(rows, k=3)
        self.assertEqual([c for _k, _s, c in prof["insufficient_reps"]], ["b"],
            "只跑 1 次的题必须被标为重复不足,不能混入 pass^3 的分母")
        # pass^3 只在满 3 次的题上计算
        self.assertAlmostEqual(pass_at_kk(rows, k=3), 1.0, places=9,
            msg="只有题 a 满 3 次且全对,pass^3 = 1.0(题 b 因重复不足被排除)")

    def test_T5_independence_is_per_case_not_pooled(self):
        """R3:pass^k 的样本是**同一 case_id 的多次 rep**,不是跨题聚合。

        反例:两题各跑 1 次(共 2 次运行,全对)——
        聚合看「2/2 全对」像很稳,但按 case 口径是一题重复不足、不可计入 pass^k。
        """
        rows = _runs([("a", 0, True), ("b", 0, True)])
        prof = stability_profile(rows, k=2)
        self.assertEqual([c for _k, _s, c in prof["insufficient_reps"]], ["a", "b"],
            "两题各只跑 1 次,k=2 时**全部**重复不足 —— 不得把 2 次运行当成同一题的 2 次重复")
        self.assertIsNone(pass_at_kk(rows, k=2),
            "无任何题满足 k=2 时,pass^2 应为 None(不可算),不得返回 0.0 或 1.0")

    def test_T7_different_seeds_are_not_treated_as_repeats(self):
        """R3:不同 seed 的同 ID 题**不是**同一题的重复样本。

        自查发现(2026-10-01):`_runs-assert-strong.jsonl` 里 30 题**每题两条 `rep=0`**、
        `session_id` 不同 —— 那是**两个 seed 合并批**的产物,不是独立重复 2 次。
        若只按 case_id 分组,它们会被误配成同一题的 2 次重复,pass^k 就算出一份
        「看起来有数字、实则无意义」的一致性。
        """
        rows = [
            {"config": "C1", "case_id": "tick-1", "rep": 0, "kind": "numeric",
             "category": "tick", "correct": True, "no_answer": False,
             "route": "断言通过", "run_error": False, "seed": 20260928},
            {"config": "C1", "case_id": "tick-1", "rep": 0, "kind": "numeric",
             "category": "tick", "correct": False, "no_answer": False,
             "route": "断言通过", "run_error": False, "seed": 20260929},
        ]
        prof = stability_profile(rows, k=2)
        self.assertEqual(len(prof["eligible"]), 0,
            "两个不同 seed 的同 ID 题各自只跑 1 次,k=2 时**都不该**进分母")
        self.assertEqual(len(prof["insufficient_reps"]), 2,
            "两条分别属于不同 seed,必须是两个独立的「重复不足」条目")
        self.assertIsNone(pass_at_kk(rows, k=2),
            "不得把跨 seed 的两条误配成一次重复而算出 pass^2")

        # 同一 seed 内真重复 2 次 → 应当计入
        same_seed = [
            dict(r, seed=20260928, rep=0) for r in rows[:1]
        ] + [dict(rows[1], seed=20260928, rep=1)]
        prof2 = stability_profile(same_seed, k=2)
        self.assertEqual(len(prof2["eligible"]), 1,
            "同一 seed、同一题、rep 0/1 才是真正的独立重复")

    def test_T8_profile_and_pass_kk_use_same_window(self):
        """★ 红队 5e900042 反证 2(致命):两者分子必须**逐题相同**,不只是集合相等。

        红队实测:真实 advprem(k=2)下 `stability_profile` 说 10/12 = 0.833,
        而 `pass_at_kk` 返回 8/12 = 0.667 —— 同一份数据、两个数、都不报错。
        比报错更糟:它看起来是正常的。

        触发条件是**运行次数 > k**:本套件此前的 7 个测试恰好都是 len(vals) == k,
        令 `head = vals[:k]` 成为**死代码**,所以缺陷一直藏着。
        """
        # 一题跑 3 次(对、对、错),k=2 → 两种算法必须给出同一个数
        rows = _runs([("c1", 0, True), ("c1", 1, True), ("c1", 2, False)])
        prof = stability_profile(rows, k=2)
        pkk = pass_at_kk(rows, k=2)
        stable_frac = len(prof["stable_pass"]) / len(prof["eligible"])
        self.assertAlmostEqual(pkk, stable_frac, places=9,
            msg="pass^k 与 stability_profile 的 stable_pass 占比不一致 —— "
                "说明两者对「跑超过 k 次时取哪几次」的处理不同(红队反证 2)")
        # 且窗口必须是「前 k 次」而非「全部」—— 否则 all([T,T,F]) = False,
        # 与 stable_pass 的 all(head=[T,T]) = True 矛盾
        self.assertAlmostEqual(pkk, 1.0, places=9,
            msg="k=2 时应按前 2 次判定(全对 → 1.0);若按全部 3 次会得 0.0")

    def test_T9_no_pooling_across_configs(self):
        """★ 红队 5e900042 反证 1(致命):**不得跨 config 池化**。

        `_runs-assert-30.jsonl`(p=0.0312 那份数据)的「重复」其实是 **A1/A2 两臂**,
        不是重复运行。按 case 分组会把它们当成同一题的两次,
        报出 `pass^2 = 0.80` —— 而 0.80 恰等于 **A1 的 pass@1**,
        即「A1 与 A2 都对」的题数比例,**不是一致性**。按 config 拆开后两臂都不可算。
        """
        rows = [
            {"config": "A1", "case_id": f"c{i}", "rep": 0, "kind": "numeric",
             "category": "tick", "correct": i < 3, "no_answer": False,
             "route": "断言通过", "run_error": False, "seed": 20260928}
            for i in range(5)
        ] + [
            {"config": "A2", "case_id": f"c{i}", "rep": 0, "kind": "numeric",
             "category": "tick", "correct": True, "no_answer": False,
             "route": "断言通过", "run_error": False, "seed": 20260928}
            for i in range(5)
        ]
        # 不指定 config → 按 (config, seed, case_id) 分组,A1/A2 各是一批单次运行
        self.assertIsNone(pass_at_kk(rows, k=2),
            "A1/A2 是两个配置各跑 1 次,不是同一题的重复 —— 不得池化算出 pass^2")
        self.assertEqual(pass_at_kk(rows, k=2, config="A1"), None,
            "显式指定 config 后,单个配置内每题仍只跑 1 次 → 不可算")
        self.assertAlmostEqual(pass_at_1(rows), 8 / 10, places=9,
            msg="pass@1 应按每次运行等权(A1 对 3/5,A2 对 5/5)")

    def test_T10_gate_rows_are_excluded_and_counted(self):
        """gate 题只判路由、不判答案,**必须排除**,且剔除数要报出来。

        红队 5e900042 变异 M6(`_group` 不过滤 gate)曾**全绿** ——
        因为套件里没有任何含 gate 的样本,那条 `continue` 形同虚设。
        把 gate 混进答案正确率会把「路由判对」算成「答案判对」,直接虚高 pass@1。
        """
        rows = _runs([("c1", 0, True), ("c1", 1, True)])
        rows += [{"config": "C1", "case_id": "g1", "rep": 0, "kind": "gate",
                  "category": "gate", "correct": True, "no_answer": False,
                  "route": "3/3 Independent Consensus", "run_error": False,
                  "expected": {"expect_three_path": True, "expect_reason": "test"}}
                 for _ in range(2)]
        prof = stability_profile(rows, k=2)
        self.assertEqual(prof["n_gate_excluded"], 2, "被剔除的 gate 题数必须报出来")
        self.assertEqual(len(prof["eligible"]), 1, "gate 题不得进 pass^k 的分母")
        self.assertAlmostEqual(pass_at_1(rows), 1.0, places=9,
            msg="pass@1 只看答案题(2 次全对);gate 若混入,分母会从 2 变成 4")
    def test_T6_pass_at_1_matches_existing_accuracy(self):
        """pass@1 必须等于现有 summarize 的 answer_accuracy —— 不能另起一套口径。"""
        from jevbench.grading import summarize
        rows = _runs([("a", 0, True), ("b", 0, True), ("c", 0, False)])
        graded = [dict(r, run_error=False) for r in rows]
        s = summarize(graded)
        # summarize 的 rate 是 round(4) 的报告值,pass@1 返回全精度;
        # 比较前把两边统一到 4 位,否则会因舍入误报「两套口径打架」。
        self.assertAlmostEqual(
            round(pass_at_1(rows), 4),
            s["C1"]["answer_accuracy"]["rate"], places=4,
            msg="pass@1 与 summarize 的 answer_accuracy 不一致 —— 两套口径会互相打架")


if __name__ == "__main__":
    unittest.main(verbosity=2)
