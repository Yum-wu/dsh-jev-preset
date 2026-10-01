# -*- coding: utf-8 -*-
"""
A10:gate 题的期望口径与 persona 的现行门控**冲突** —— 按新门控正确作答会被判错。

缺陷背景(附录 A10,严重度高):
  gate 题由 `jevbench/cases.py:GATE_TEMPLATES` 生成,每条带一个 `expect_three_path`,
  判分靠 `grading.py:48` 的 `is_three_path(route)`。
  但 persona 的门控已在 2026-09-30 改成「**断言优先**」:
  「命中量化推导/风控/资金类且答案可写成可执行断言 → **单路 + 真跑复算**,严禁派生三路」。
  而 GATE_TEMPLATES 里标 `True`(期望三路)的模板,恰恰**大量是可写成断言的**
  (应开多少张 / 网格每格价 / 跨市场价差扣费后有无利润 / Kelly 仓位比例 …)。

  后果:一个严格遵守 persona 的 agent,在这类题上输出 `[JEV: 断言通过]`(单路),
  会被 gate 判成 `correct=False`。**它没有做错任何事,只是被旧口径判为错。**
  即:当前 gate 准确率测的不是「门控是否正确」,而是「是否服从 2026-09-30 之前的旧门控」。

判据(预注册,R9):
  T1 gate 判分必须与 persona 现行门控**一致** —— 具体做法:
     期望值不能再是「是否三路」这个二值,而要区分「可断言 → 应单路」与
     「不可断言 → 才可三路」,且区分依据必须来自**题面**(可写成断言)而非硬编码布尔。
  T2 不允许用**硬编码布尔**表达 gate 期望:凡题面可写成可执行断言的,期望必须是单路。
  T3 门控判分口径的变更必须在 tests 里被锁住,且**判分函数本身**要能区分两类失败:
     「选错了路径」vs 「路径对但没执行/执行失败」。
  T4 gate 题必须能被独立复算:给定题面与作答,判分结论不依赖读代码的人的主观判断。
"""
import os
import random
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "benchmarks", "accuracy"))

from jevbench.cases import build_suite  # noqa: E402
from jevbench.grading import grade_case  # noqa: E402

# 注:本文件**不再**维护「可断言 / 高危」题面信号表 ——
# 那会变成 expected_gate_route 正则的**逐字副本**,两者一起漂移
# (红队 a0115d91 变体 V2c-clean 实证:副本对副本,A10 缺陷原形态可全绿通过)。
# 期望值的唯一独立判据是 T6 的**逐条快照** —— 具体值不会漂移。


def persona_prefix():
    lines = open(os.path.join(PLUGIN_ROOT, "cordis.patch.yml"), encoding="utf-8").read().split("\n")
    s = next((i for i, l in enumerate(lines) if re.match(r"^\s*prefix: \|-\s*$", l)), -1)
    assert s >= 0, "cordis.patch.yml 里找不到 `prefix: |-` 行"
    indent = re.search(r"\S", lines[s]).start()
    out = []
    for line in lines[s + 1:]:
        if line.strip() == "":
            out.append(line)
            continue
        if re.search(r"\S", line).start() < indent:
            break
        out.append(line)
    return "\n".join(out)


class TestGateExpectationMatchesGatekeeping(unittest.TestCase):

    def test_T1_persona_stillAssertsFirst(self):
        """前提确认:persona 的门控仍是「断言优先」,单路 + 真跑断言是首选路径。
        若哪天 persona 改回「高危一律三路」,本文件整套判据需重估。"""
        persona = persona_prefix()
        self.assertRegex(
            persona, r"断言优先|单路作答[^。\n]{0,20}真跑",
            "persona 不再是「断言优先」—— A10 的前提变了,本判据需重新评估")
        self.assertRegex(
            persona, r"严禁派生三路|不必三路",
            "persona 未禁止对可断言题派生三路 —— A10 描述的口径冲突已不存在")

    def test_T2_gate_expectation_not_derived_from_template_boolean(self):
        """gate 期望不得再从 `GATE_TEMPLATES` 的**硬编码布尔**取值。

        实现方式:直接检查 `gen_gate` 源码里没有取模板布尔的那一行 ——
        文本级断言,但对象是**唯一**的取值点,且不依赖随机参数。
        (初版想比对「模板题面 ↔ 题集题面」,实测 12/16 对不上 ——
         `build_suite` 与 `fn(Random(1))` 走的是不同随机序列,比对必然失配,
         而失配走 `continue` 就让整条判据静默失效。这就是 A10 的同款病:
         **跳过 ≠ 通过**。)
        """
        import inspect

        from jevbench.cases import gen_gate
        src = inspect.getsource(gen_gate)
        self.assertNotIn("GATE_TEMPLATES[i % len(GATE_TEMPLATES)][0]", src,
            "gen_gate 仍在取模板的硬编码布尔作为期望(A10 的原始病根)")
        self.assertRegex(src, r"expected_gate_route",
            "gen_gate 未调用 expected_gate_route —— 期望值仍不是从题面复算的")
        # 题集里每条 gate 都必须带口径来源
        gates = [c for c in build_suite(20260928) if c["kind"] == "gate"]
        missing = [c["id"] for c in gates if not c["expected"].get("expect_reason")]
        self.assertEqual(missing, [], f"这些 gate 题缺 expect_reason(期望不可审计): {missing}")

    def test_T3_grading_exposes_route_and_undecidable(self):
        """判分结果必须暴露 `route`(事后审计入口)与 `undecidable`(口径不明标记)。

        判据修正(红队 a0115d91 次要发现 4):本条原名「区分选错路径 vs 没执行」**名不副实** ——
        实现只查了 `route` 字段存在,且那段 if 体因首题恒为 False 从不执行。
        现改名并给出**真正有效**的两项:route 字段 + undecidable 字段。
        「路径对但没执行」需要 `executed` 字段才能表达,那是本目标未做的工作,登记在案。
        """
        from jevbench.grading import grade_case as gc
        suite = build_suite(20260928)
        gate = next(c for c in suite if c["kind"] == "gate")
        g = gc(gate, "[JEV: 断言通过]\n```json\n{}\n```")
        self.assertIsInstance(g, dict)
        self.assertIn("route", g, "判分结果缺 route 字段,无法事后审计选了什么路径")
        self.assertIn("undecidable", g,
            "判分结果缺 undecidable 字段 —— 「口径不明」与「判错」无法区分(R5)")
        # 口径不明时,必须三者同时成立:不判对、不判成答错、标记不可判定
        fake = dict(gate)
        fake["expected"] = {**gate["expected"], "expect_three_path": None}
        g2 = gc(fake, "[JEV: 断言通过]\n```json\n{}\n```")
        with self.subTest(场景="期望不可判定"):
            self.assertTrue(g2.get("undecidable"), "口径不明时未标 undecidable")
            self.assertTrue(g2.get("no_answer"), "口径不明时 no_answer 必须为真(R5)")
            self.assertFalse(g2.get("correct"), "口径不明时不得被判 correct")

    def test_T5_reference_answer_matches_gatekeeping(self):
        """selftest 用的**参考答案**必须符合现行门控。

        判据修正(自查 V3 变体实测:把单路参考答案改回 `Fast-Pass`,本文件全绿):
        `Fast-Pass` 是「低危任务单次直出」,与「已真跑断言」是**不同的事实** ——
        用它造参考答案,等于让 selftest 认可一条**没有执行断言**的作答,
        门控正确性就被自己架空了。
        """
        import inspect

        from jevbench.grading import reference_text
        src = inspect.getsource(reference_text)
        self.assertNotRegex(src, r'expect_three_path\]\s*\]\s*else\s*"Fast-Pass"',
            "reference_text 仍用 Fast-Pass 造单路参考答案 —— "
            "「未跑断言」与「跑了断言」被混同(A10)")
        self.assertIn("断言通过", src,
            "reference_text 未对「期望单路」使用 `断言通过` 标识(persona §二① 的首选路径)")

        # 端到端:期望单路的 gate 题,参考答案必须被判对
        gates = [c for c in build_suite(20260928) if c["kind"] == "gate"]
        single = [c for c in gates if c["expected"]["expect_three_path"] is False]
        self.assertGreater(len(single), 0, "题集里没有期望单路的 gate 题,判据无法生效")
        for c in single:
            with self.subTest(题=c["id"]):
                ref = reference_text(c)
                self.assertIn("[JEV: 断言通过]", ref,
                    f"{c['id']} 期望单路,参考答案却没用 `断言通过`")
                self.assertTrue(grade_case(c, ref)["correct"],
                    f"{c['id']} 的参考答案被判错 —— 参考答案与判分口径不一致")


    # ⚠ 快照:逐条钉死 16 条 gate 的期望,作为**唯一**的独立判据。
    # 判据修正(红队 a0115d91 变体 V2c-clean 实证):此前 T4 的「独立判读表」
    # 是 expected_gate_route 正则的**逐字副本** → 「知识题被误标三路」零保护。
    # 快照不是副本:它是一组人工逐条核对过的**具体值**,改任一条都会报红,
    # 且改的是**期望本身**而不是改判据去迁就代码。
    EXPECTED_GATE_VECTOR = (
        False, False, False, False, False, False, False, False,   # 纯知识/解释/列举
        False, False,                                                # 8 永续开仓 / 9 前复权
        True, True,                                                  # 10 并发防重 / 11 密钥安全
        False, False, False, False,                                 # 12 年化 / 13 网格 / 14 Kelly / 15 价差
        None,                                                        # 16 措辞中立探针(兜底分支必须可达)
    )

    def test_T8_fallback_branch_must_be_reachable(self):
        """题集必须**至少含 1 条**期望为 None 的题 —— 否则兜底分支是死代码。

        红队 a0115d91 变体 6 实测:兜底从 None 改成 True(退回 A10 的
        「不知道就默认三路」)时全绿,因为题集里 0 条 None,没人碰得到那条分支。
        这条把死分支变成活分支:改了兜底,快照会立刻报红。
        """
        gates = [c for c in build_suite(20260928) if c["kind"] == "gate"]
        nones = [c for c in gates if c["expected"]["expect_three_path"] is None]
        self.assertGreater(
            len(nones), 0,
            "题集里没有期望为 None 的 gate 题 —— `expected_gate_route` 的兜底分支是死代码,"
            "改成任何默认值都不会被测出来(红队变体 6)")

    def test_T6_gate_vector_snapshot(self):
        """逐条钉死 gate 期望向量 —— 唯一能防「知识题被误标三路」的判据。

        这条的存在理由:正则永远可能漏词,而**具体值**不会漂移。
        新增 gate 模板时必须同步更新本向量(这正是它该有的阻力)。
        """
        gates = [c for c in build_suite(20260928) if c["kind"] == "gate"]
        self.assertEqual(
            len(gates), len(self.EXPECTED_GATE_VECTOR),
            f"gate 题数从 {len(self.EXPECTED_GATE_VECTOR)} 变成 {len(gates)} —— "
            f"新增/删除了模板,必须同步更新 EXPECTED_GATE_VECTOR 快照")
        for i, (c, want) in enumerate(zip(gates, self.EXPECTED_GATE_VECTOR)):
            with self.subTest(题序号=i, 题面=c["question"][:24]):
                self.assertIs(
                    c["expected"]["expect_three_path"], want,
                    f"#{i} 期望与人工快照不符: 快照={want} 实际={c['expected']['expect_three_path']}\n"
                    f"  题面: {c['question']}")

    def test_T7_snapshot_reason_is_substantive(self):
        """`expect_reason` 不能只是非空 —— 改成 'x' 也不该放过。

        红队次要发现 2:该字段全仓只被写入,测试仅断非空,内容零校验。
        """
        gates = [c for c in build_suite(20260928) if c["kind"] == "gate"]
        for c in gates:
            with self.subTest(题=c["id"]):
                reason = c["expected"].get("expect_reason", "")
                self.assertRegex(
                    reason, r"§二[①②③]|不可判定|题面信号不足",
                    f"{c['id']} 的 expect_reason「{reason}」没说明依据到 persona 哪一条,"
                    f"也无法审计为「口径不明」")


if __name__ == "__main__":
    unittest.main(verbosity=2)
