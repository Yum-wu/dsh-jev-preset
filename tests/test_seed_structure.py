# -*- coding: utf-8 -*-
"""
seed 结构自检(附录 C2)。

## 缺口(arXiv:2603.18388《Reflection in the Dark》)

> GEPA 用官方提供的 defective seed 在 GSM8K 上把准确率从 **23.81% 打到 13.50%**,
> 而**真实根因(字段顺序)在所有轮次获得 0 次归因** ——
> 即优化循环**系统性地看不见数据本身的结构缺陷**,于是一轮轮地在错误的方向上优化。

本仓的对应面:题面由 `cases.py` 的各 `gen_*` 用 f-string **拼接**而成,
**关键约束(方向词 / 禁止四舍五入 / 答案协议)出现的顺序内嵌在拼接顺序里**。
若某次改动让顺序漂移、或某个必需片段丢失,自优化循环会**照常跑完并报告一个「正常」的准确率**,
而根因仍然 0 次归因 —— 这正是 C2 描述的失败模式。

## 本模块做什么(只做三件)

1. **确定性**:同一 seed 跑两次,题面字符串必须**逐字节相同**。
   结构漂移(即题面随无关改动而变)会在这里暴露。
2. **片段齐全**:每类题面必须包含它自己的数值、方向/条件词、以及 `ANSWER_PROTOCOL` 声明的键。
3. **答案协议一致**:`ans` 的键必须与题面里 `_proto(...)` 声明的键**完全一致** ——
   题面要一个键、答案给另一个键,判分器会静默判错,而自优化循环看不出来。

## 判据的可证伪性

T4 专门检验「本模块能否检出结构漂移」:人为把某生成器的拼接顺序改掉,
`audit_generators()` 必须报出该生成器。**若改顺序而它仍然全绿,本模块就是装饰品。**
"""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "benchmarks", "accuracy"))

from jevbench import cases  # noqa: E402
from jevbench.seed_audit import audit_all, audit_generators  # noqa: E402

_GENERATORS = [n for n in dir(cases) if n.startswith("gen_")]


class TestSeedStructureAudit(unittest.TestCase):

    def test_T1_every_generator_is_audited(self):
        self.assertGreaterEqual(len(_GENERATORS), 8,
                                f"只发现 {len(_GENERATORS)} 个生成器,题库结构可能变了")
        report = audit_generators()
        audited = {r["generator"] for r in report}
        missing = sorted(set(_GENERATORS) - audited)
        self.assertEqual(missing, [],
                         f"这些生成器没被审计到: {missing} —— 新增 gen_* 会被静默跳过")

    def test_T2_same_seed_gives_identical_text(self):
        """确定性:同一 seed 两次生成必须逐字节相同(结构漂移会在这里暴露)。"""
        drifts = [r for r in audit_generators() if r.get("nondeterministic")]
        self.assertEqual([d["generator"] for d in drifts], [],
                         "这些生成器在同 seed 下产出不同题面 —— 结构不稳定,"
                         "优化循环会把它当成随机波动,而不是结构缺陷")

    def test_T3_answer_keys_match_protocol(self):
        """题面声明的键必须与 `ans` 的键完全一致。"""
        bad = [r for r in audit_generators() if r.get("key_mismatch")]
        self.assertEqual([b["generator"] for b in bad], [],
                         "题面 `_proto()` 声明的键与 `ans` 的键不一致 —— "
                         "判分器会静默判错,而自优化循环看不出来")

    def test_T4_audit_detects_injected_nondeterminism(self):
        r"""★ 可证伪性:人为让生成器**不幂等**,审计**必须**报出来。

        ⚠⚠ 本测试第一版(T4,已废)验的是 `drifted`(拼接顺序漂移),而 `drifted`
        判据**两次实现都误报** —— 根因:题面内容本就依赖 `rng`,「改拼接顺序」
        与「换一个 rng 抽取」在题面字符串上无法区分,「骨架应一致」的前提不成立。
        红队 a3d373a8 也指出它。**已删除该判据,本测试随之改验真正可判的一条:
        同 seed 两次调用产出不同题面(= 不幂等)。** 这是唯一不依赖「骨架」假设的判据。

        若注入不幂等后本测试仍绿,`audit_generators()` 就是装饰品。
        """
        import importlib

        mod = importlib.import_module("jevbench.cases")
        real = mod.gen_tick
        calls = {"n": 0}

        def nonidempotent(rng, i):
            # 同 seed 下第二次调用给出不同题面 —— 模拟「题面依赖了外部时钟/调用次数」
            calls["n"] += 1
            q, ans = real(rng, i)
            return (q + f"(第{calls['n']}次)" if calls["n"] > 1 else q), ans

        mod.gen_tick = nonidempotent
        try:
            report = audit_generators()
            hit = [r for r in report if r["generator"] == "gen_tick"]
            self.assertTrue(hit and hit[0].get("nondeterministic"),
                            "注入不幂等后审计未报出 —— 确定性自检是摆设,"
                            "T2 就只是『跑了一遍生成器』的假检查")
        finally:
            mod.gen_tick = real

    def test_T4b_hook_is_live_not_decoration(self):
        r"""★ 补丁真的生效了吗?—— 打桩后必须**真的被调用**,否则上面的 try 块是空转。

        这是本仓反复栽的「钉的是自己」的镜像:打桩写对了但注入目标与审计读的
        不是同一个对象 -> 测试变绿而实际上什么都没检验。故显式验注入生效。
        """
        import importlib

        mod = importlib.import_module("jevbench.cases")
        real = mod.gen_tick
        seen = []

        def spy(rng, i):
            seen.append(1)
            return real(rng, i)

        mod.gen_tick = spy
        try:
            audit_generators()
        finally:
            mod.gen_tick = real
        self.assertGreater(len(seen), 0,
                           "注入的替身一次都没被调用 —— 审计读的是别的引用,"
                           "T4 的 try 块是空转,结论不可信")

    def test_T3b_answer_value_types_match_protocol(self):
        r"""★ 本模块查出的**真缺陷**:协议声明与实际值的**类型**不一致。

        `ANSWER_PROTOCOL` 明写「所有数值一律写成字符串(如 "123.45")」,
        而 `gen_mdd` 的协议段写的是:
            {"mdd_pct": "<最大回撤%>", "peak_index": <整数>, "trough_index": <整数>}
        —— `peak_index` / `trough_index` 用的是**无引号的 `<整数>`**,
        实际 `ans` 也确实给的是 int。

        协议与实现在这里**同时**偏离了「一律字符串」这条规则:
        判分器若严格按协议解析就会判错,而自优化循环跑完只会报告一个「正常」的准确率,
        根因 0 次归因 —— 正是附录 C2 描述的失败模式。

        本测试断言:该问题**现在仍存在且被如实检出**(不是断言它已修),
        修好之后本测试应随之改写 —— 那一改本身就是「归因发生了一次」的证据。
        """
        report = audit_generators()
        hits = [r for r in report if r.get("type_mismatch")]
        self.assertTrue(hits, "gen_mdd 的类型声明不一致应被检出 —— 若消失了,"
                               "请把本测试改成断言「已修复」,并记下修复轮次")
        keys = {m["key"] for h in hits for m in h["type_mismatch"]}
        self.assertIn("peak_index", keys,
                      "预期检出 gen_mdd 的 peak_index(协议说字符串、实际给整数)")

    def test_T5_suite_builds_and_is_auditable(self):
        """端到端:真实题库能被构建并通过审计(否则前面的检查都跑在空集上)。"""
        suite = cases.build_suite(20261001)
        self.assertGreater(len(suite), 20, f"题库只有 {len(suite)} 题,规模异常")
        ids = [c["id"] for c in suite]
        self.assertEqual(len(ids), len(set(ids)), "题库出现重复 id —— 判分会串题")


if __name__ == "__main__":
    unittest.main(verbosity=2)
