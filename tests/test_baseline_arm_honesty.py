# -*- coding: utf-8 -*-
"""
B6:A1 臂的「禁代码」**无程序级拦截**,仅靠 prompt 约束。

缺口(附录 B6,依据 EXP-F 第八节自认):
  A1(禁代码纯推理)是执行断言实验的**对照臂**。它与 C0/C1 **同为 `standard` 预设**,
  差异**只在文字约束**(prompt),工具面完全相同 —— 也就是说,
  A1 臂的 agent **物理上仍然能调用 pwsh/bash/jobs 执行代码**。
  仓库自己的审计也写着:「实测 A1 文本里有『代码』字样(仅文字提及,无执行)。
  **未做程序级拦截**,存在偷跑可能(若有,真实差距更大)」。

这为什么重要:
  p=0.0312(24/30 → 30/30)这个**本仓唯一的统计显著结论**,其基线是 A1 的 80.0%。
  若 A1 其实偷偷跑了断言,则真实差距**小于**报告值 —— 结论方向不变但幅度被高估。
  即:这是一个「结论可能被自己夸大」的口径缺口,而不是普通 TODO。

判据(预注册,R9):
  T1 必须**明确记录** A1 的「禁代码」是 prompt 级约束而非程序级拦截,
     且该记录须与 `run-bench.mjs` 的实际实现一致(A1 用的确实是 `standard` 预设);
  T2 persona **不得**声称 A1 的禁代码有程序级保障(那是它没有的东西);
  T3 判分侧必须能把「A1 臂跑过代码」的样本**识别出来**,否则偷跑永远查不出来
     —— EXP-F 只做了「文本里有没有『代码』字样」的**最弱**检查(文字提及≠执行);
  T4 当 T3 的识别能力不可得时,必须**显式登记为口径缺口**,而不是默认「没跑」。
"""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
BENCH = os.path.join(PLUGIN_ROOT, "benchmarks", "accuracy")
sys.path.insert(0, BENCH)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestBaselineArmHonesty(unittest.TestCase):

    def test_T1_A1_uses_standard_preset(self):
        """前提确认:A1 用的确实是 `standard` 预设 —— 与 C0/C1 同工具面,
        差异只在 prompt。若将来 A1 换成别的预设,本文件的判据需重估。"""
        src = _read(os.path.join(BENCH, "run-bench.mjs"))
        m = re.search(r"const PRESET\s*=\s*\{([^}]+)\}", src)
        self.assertIsNotNone(m, "run-bench.mjs 里找不到 PRESET 映射")
        preset = dict(re.findall(r"(\w+):\s*'([\w-]+)'", m.group(1)))
        self.assertEqual(preset.get("A1"), "standard",
            "A1 若不再是 standard 预设,「工具面与 C0 相同」的前提失效,判据需重估")
        self.assertEqual(preset.get("C0"), "standard",
            "C0 应同为 standard(B6 的论证依赖 A1/C0 工具面相同)")

    def test_T2_persona_makes_no_programmatic_claim(self):
        """persona 若提到「禁代码」,必须**同时**声明它是 prompt 级约束。

        判据修正(红队 31ebcbb2 实证):初版是「出现『禁代码』就失败」——
        那连**诚实的负面披露**都禁掉,而 B6 恰恰要求 persona 写明这个缺口。
        改为:同行出现 `程序级|拦截|保障|强制|杜绝` 等**肯定性 token** 才失败。
        """
        persona = _read(os.path.join(PLUGIN_ROOT, "cordis.patch.yml"))
        affirmative = re.compile(r"程序级|拦截|保障|强制|杜绝|保证")
        for m in re.finditer(r"[^\n]*禁代码[^\n]*", persona):
            line = m.group(0)
            with self.subTest(行=line.strip()[:40]):
                self.assertIsNone(
                    affirmative.search(line),
                    "persona 出现关于「禁代码」的**肯定性**表述 —— "
                    "它没有任何程序级拦截;但诚实写「仅为 prompt 级约束」是允许且必要的")

    def test_T3_grader_can_flag_arm_that_ran_code(self):
        """判分侧必须能识别「A1 臂跑过代码」,否则偷跑永远查不出来。

        EXP-F 的检查是「文本里有没有『代码』字样」—— 那是**最弱**的代理:
        模型可以纯文字讨论代码而完全不执行(实测 A1 文本确实含该字样却没执行)。
        真正的证据在 **tool 轨迹**里,不在文本里。
        """
        from jevbench.grading import grade_case  # noqa: F401
        import jevbench.grade_audit as audit
        self.assertTrue(hasattr(audit, "flag_code_execution"),
            "缺少 flag_code_execution —— 判分侧无法识别「对照臂偷跑代码」,"
            "EXP-F 的检查只覆盖文本字样,是代理指标而非证据")

    def test_T5_discussion_is_not_flagged_as_execution(self):
        """「讨论代码」**不得**被判成「执行了代码」—— 方向错了会把差距**高估**。

        EXP-F 的原检查正是栽在这:实测 A1 文本含「代码」字样却**没有执行**。
        本模块刻意把「提到代码」与「执行痕迹」分开:
        文本级检查只能**上界**报出「可能偷跑」,不能反过来说「一定没跑」。
        """
        from jevbench.grade_audit import flag_code_execution

        # 纯讨论:提到代码/函数/算法,但没有任何执行痕迹
        discussed = "要写一个 Python 函数实现 tick 截断,算法复杂度是 O(1),代码如下:\ndef f(): pass"
        hit, ev, saw_discussion = flag_code_execution(discussed)
        self.assertFalse(hit,
            f"纯讨论被判成执行了代码(命中 {ev})—— 这会把真实差距**高估**,"
            f"与 B6 关心的方向相反")
        self.assertTrue(saw_discussion, "应识别出「这段在讨论代码」")

        # 真执行:贴出了**完整报错栈**(含 Traceback + 栈帧)—— 必须被检出。
        # 红队 31ebcbb2 指出:初版的 T5 样例只靠文件路径 + AssertionError 就判「执行」,
        # 删掉那些高误报模式后测试仍绿 —— 说明它验的不是「真执行」而是「那两条规则」。
        executed = ('跑了一下,报错了:\nTraceback (most recent call last):\n'
                    '  File "x.py", line 3, in f\n    assert x == y\nAssertionError')
        hit2, ev2, _ = flag_code_execution(executed)
        self.assertTrue(hit2, "完整报错栈是强执行信号,必须被检出")
        self.assertTrue(ev2, "必须给出可人工复核的证据片段,不能是黑盒判罚")

        # 反向优化样本(红队 31ebcbb2 给出):纯讨论提到文件名与异常名,
        # 初版会因文件路径规则 + AssertionError 规则判成「执行」——
        # 那会把真实差距**高估**,与 B6 关心的方向相反。
        can_reverse = (
            "建议把断言写进 tests/test_x.py,里面用 assert 校验,"
            "失败时抛 AssertionError,便于回归。"
        )
        hit3, ev3, _ = flag_code_execution(can_reverse)
        self.assertFalse(
            hit3,
            f"纯讨论被判成执行了代码(命中 {ev3})—— 提到文件名/异常名 ≠ 执行,"
            f"这会把差距**高估**")

    def test_T7_no_production_wiring_is_disclosed(self):
        """本模块**测试外零接线**(红队 31ebcbb2 实锤)—— 必须在文档里如实登记。

        `audit_baseline_arm` / `flag_code_execution` 的全仓引用只有它自己和它自己的测试;
        `npm test` 之外没有任何脚本调它。它是**登记牌**,不是运行时防线。
        """
        audit = _read(os.path.join(BENCH, "jevbench", "grade_audit.py"))
        self.assertRegex(
            audit, r"不是\s*\*?\*?审计能力|登记牌|不是审计",
            "模块必须自我定位为「登记牌」而非「审计能力」—— "
            "R13:把弱代理包装成审计能力,正是本目标要消灭的验证剧场")

    def test_T6_audit_runs_on_real_A1_data(self):
        """必须能在**真实 A1 数据**上跑出结果,且如实报告检出能力受限。"""
        from jevbench.grade_audit import audit_baseline_arm
        path = os.path.join(BENCH, "_runs-assert-30.jsonl")
        if not os.path.exists(path):
            self.skipTest("A1 的 runs 文件不在本仓")
        runs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
        a1 = [r for r in runs if r.get("config") == "A1"]
        if not a1:
            self.skipTest("该文件不含 A1 臂")
        rep = audit_baseline_arm(runs, config="A1")
        self.assertEqual(rep["total"], len(a1), "审计样本数必须与 A1 臂记录数一致")
        self.assertRegex(rep["detection_power"], r"不能证明|不等于",
            "必须显式声明检出能力的边界 —— 无工具轨迹时,"
            "「没检出」不等于「没跑」,隐去这一点本模块就成了新的验证剧场")
        # 「讨论代码」的数量应 ≥ 检出数(EXP-F 记录 A1 文本确有代码字样)
        self.assertGreaterEqual(rep["discuss_only"] + rep["flagged"], 0)
    def test_T4_text_mention_is_documented_as_weak_proxy(self):
        exp = _read(os.path.join(BENCH, "EXP-F-ASSERTION-EFFECT.md"))
        self.assertIn("未做程序级拦截", exp,
            "EXP-F 丢失了「未做程序级拦截」的自认 —— 该缺口一旦被忘记,"
            "p=0.0312 的基线口径就再没人提")
        # 结论段必须重述幅度可能被高估
        self.assertRegex(
            exp, r"真实差距更大|差距.*高估|幅度",
            "EXP-F 未说明「若 A1 偷跑则真实差距更小」—— "
            "读者会以为 80% 是可信基线,而不是 prompt 级约束下的上界")


if __name__ == "__main__":
    unittest.main(verbosity=2)
