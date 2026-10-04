# -*- coding: utf-8 -*-
r"""
B4:成本–准确率帕累托前沿的**强制报告格式**的判别力测试。

## 缺口(2026-10-01 实测)

本仓每个实验各写各的表,导致:成本单位混用(`×2.0` / `×20` / 平均 token 三种)、
准确率单位混用(题数 `6→12` / 百分比 `80.0%` / 相对增益 `+89pp`)、
样本量与 Wilson 区间时有时无。`EXP-F:143-144` 里 `24/30` 与 `30/30` 都被写成
「80.0% / 100.0%」而**不带 n**,读者无法判断这个 100% 值不值得信。

## 判据(预注册,R9)

  Q1 **格式逐字锁定** —— 表头与列顺序由 `COLUMNS` 定,任何改动必须同步改测试,
     否则会静默改变下游文档的解析方式(这正是 B4 要消灭的现象本身)。
  Q2 **支配判定正确** —— 前沿上的方法不得被任何「不更贵 + 不更差 + 至少一项更优」
     的方法支配;两个**完全相同**的方法必须**都**在前沿上
     (若互相支配,前沿会被清空 —— 这是最容易写错的第二处)。
  Q3 **Wilson 必带** —— 每个方法输出 Wilson 95%,且必须**不是** Wald
     (n 小时 Wald 会给出越界或退化的区间)。
  Q4 **缺出处/缺样本量/单位越界一律拒绝出报告** —— 在**生成时**拦下,
     而不是等下游抄表时才发现。
  Q5 **对判据本身可证伪** —— 把 `on_frontier` 的严格性判据去掉,测试必须变红。
     (本仓反复栽在「看起来严谨但钉的是自己」的坑上,故每条判据都要问:
      它能被什么杀掉?)
"""
import os
import sys
import unittest
from decimal import Decimal as D
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "benchmarks", "accuracy"))

from pareto import COLUMNS, Method, on_frontier, render_markdown, verify_report, wilson  # noqa: E402


def sample():
    return [
        Method("A1 基线(不干预)", 80.0, 1.0, 30, "EXP-F-ASSERTION-EFFECT.md:143"),
        Method("A2 强制复算(执行断言)", 100.0, 2.0, 30, "EXP-F-ASSERTION-EFFECT.md:144"),
        Method("三路隔离采样", 100.0, 10.6, 30, "EXP-G-THREE-PATH-VS-ASSERTION.md"),
    ]


class TestParetoReport(unittest.TestCase):

    def test_Q1_format_is_locked(self):
        r"""⚠⚠ 本测试第一版是**恒真断言**,实测零检测力(Round 45,红队 a3d373a8 指出)。

        原写法:`assertEqual(header, "| " + " | ".join(COLUMNS) + " |")` ——
        表头**就是用 COLUMNS 拼出来的**,改 COLUMNS 时两边一起变,永远恒等。
        实测:把 COLUMNS 的 `n` 列删掉,本测试**照样通过**
        (见 `docs/self-optimize-rounds.md` Round 45 的复现脚本)。
        兜底的 `assertIn("n", header)` 也被 "Wilso**n**" 的子串骗过 —— 两次假安全。

        修法:**期望值写死在测试里**,不引用被测常量。改列必须改测试 → 有摩擦才有锁。
        """
        m = render_markdown(sample())
        header = m.splitlines()[0]
        # 期望列:写死。改 pareto.COLUMNS 而不改这里 -> 本测试红。
        EXPECT = ("方法", "准确率", "n", "Wilson 95%", "成本倍数", "帕累托前沿", "证据", "备注")
        self.assertEqual(EXPECT, COLUMNS,
                         "COLUMNS 被改动 —— 必须同步改本测试的 EXPECT,否则下游解析静默失效")
        # 逐列核对(不是子串巧合:把表头 split 成列再比,避免 "Wilson" 骗过 "n")
        cols = [c.strip() for c in header.strip().strip("|").split("|")]
        self.assertEqual(cols, list(EXPECT), f"表头列实际为 {cols}")
        # ⚠ Round 45 红队 73b9a722 实测:本测试对**分隔行**零判别力 ——
        #   把分隔行改成只有 3 个 `---`,Q1 仍然 GREEN(三条断言全部只看第 0 行 + 总行数)。
        #   而下游 Markdown 解析器依赖分隔行列数与表头**对齐**,错位是静默的。
        sep = [c.strip() for c in m.splitlines()[1].strip().strip("|").split("|")]
        self.assertEqual(len(sep), len(EXPECT),
                         f"分隔行 {len(sep)} 列 vs 表头 {len(EXPECT)} 列 —— 下游解析会错位")
        self.assertTrue(all(c and set(c) == {"-"} for c in sep),
                        f"分隔行每列必须非空且全为 `-`,实际 {sep}")
        self.assertEqual(len(m.splitlines()), 2 + len(sample()), "行数 = 表头 + 分隔 + 每方法一行")

    def test_Q2_domination(self):
        ms = sample()
        # ⚠ 我第一版把支配关系写反了(期望「A1 被 A2 支配」)——
        #   但 A2 更贵(×2 vs ×1),「不更贵」这一条**不成立**,它支配不了 A1。
        #   A1 是唯一 ×1 的方法,确实在前沿上。**用例错,不是产品错。**
        self.assertTrue(on_frontier(ms[0], ms),
                        "A1 是唯一 ×1 的方法,没有任何方法能以更低成本达到它,应在前沿")
        self.assertTrue(on_frontier(ms[1], ms), "A2 最便宜地达到最高准确率,应在前沿")
        self.assertFalse(on_frontier(ms[2], ms),
                         "三路与 A2 同准确率但贵 5.3 倍,被 A2 支配,不该在前沿")
        # 完全相同的方法必须**都**在前沿(否则互相支配 → 前沿清空)
        twin_a = Method("X", 50.0, 2.0, 20, "e1")
        twin_b = Method("Y", 50.0, 2.0, 20, "e2")
        pair = [twin_a, twin_b]
        self.assertTrue(on_frontier(twin_a, pair), "完全相同的方法不该互相支配")
        self.assertTrue(on_frontier(twin_b, pair), "完全相同的方法不该互相支配")
        # 支配方向 —— ⚠⚠ 我在这一个概念上**连错四次**,全部源于同一个误解:
        #   「更好」**不**支配「更差」。支配 N→M 的定义是三条**同时**成立:
        #       cost_N <= cost_M  且  accuracy_N >= accuracy_M  且 至少一项严格更优。
        #   也就是说:一个方法要么**全面不差**,要么根本不支配。
        #   - 更贵的不支配更便宜的(成本条不满足)
        #   - 更便宜的不支配更贵的(准确率条不满足)
        #   - 只有「同价且更准」或「同准且更便宜」这类**全面占优**的才算支配。
        #   这正是帕累托前沿存在的意义:二元集合里两个点**常常都在前沿上**。
        cheap_bad = Method("Z", 10.0, 1.0, 20, "e3")      # 最便宜、最差
        dear_good = Method("W", 50.0, 2.0, 20, "e4")      # 更贵、更好
        self.assertTrue(on_frontier(cheap_bad, [cheap_bad, dear_good]),
                        "Z 最便宜,没有方法能以更低成本达到它 -> 在前沿")
        self.assertTrue(on_frontier(dear_good, [cheap_bad, dear_good]),
                        "W 没有其他方法能用更低成本达到 50% -> **也在**前沿。"
                        "『更贵』不构成被支配的理由")
        # 真正能支配 Z 的:同价但更准
        same_cost_better = Method("V", 50.0, 1.0, 20, "e5")
        self.assertFalse(on_frontier(cheap_bad, [cheap_bad, same_cost_better]),
                         "V 与 Z 同价但更准,全面占优,支配 Z -> Z 不该在前沿")
        self.assertTrue(on_frontier(same_cost_better, [cheap_bad, same_cost_better]),
                        "V 同价且更准,应在前沿")

    def test_Q2b_report_refuses_empty_frontier(self):
        broken = [Method("A", 10.0, 5.0, 10, "e"), Method("B", 90.0, 1.0, 10, "e")]
        # 用一个「支配判定失效」的替身验证 verify_report 能拦住
        import pareto
        real = pareto.on_frontier
        # ⚠ Round 45 红队 73b9a722 实测:原版尾行 `self.assertIs(orig, real)` 是**恒真**的
        #   (`orig` 就是 `from pareto import on_frontier` 拿到的**同一个函数对象**),
        #   零判别力 —— 属「钉的是自己」。改为断言「打桩确实生效、还原确实恢复」。
        try:
            pareto.on_frontier = lambda m, others: False
            self.assertFalse(pareto.on_frontier(broken[0], broken), "打桩未生效")
            with self.assertRaises(ValueError):
                verify_report(broken)
        finally:
            pareto.on_frontier = real
        self.assertTrue(pareto.on_frontier(broken[1], broken),
                        "打桩未还原 —— 后续用例会跑在被污染的判定上")

    def test_Q6_generated_report_is_reproducible_and_baselined(self):
        r"""生成器必须可复现,且**基准换算**要被锁住。

        为什么这条重要:本仓对「三路到底贵多少」有**三个数字** ——
        `EXP-G:29` ×10.61(以 A2 为基准)、`EXP-F:59` ×20(以 A1 为基准)、
        `EXP-G:194` ×15.3(**另一个 30 题批实验**)。三个数本身都不算错,
        但都没写明基准,于是「贵 10 倍还是 20 倍」无法回答。

        本测试锁住:① 同一份输入生成两次,输出**逐字节相同**;
        ② 基准固定为 A1,换算后 C3 的倍数与 EXP-G 原文的 token 数一致。
        """
        import importlib
        import subprocess
        sys.path.insert(0, os.path.join(ROOT, "benchmarks", "accuracy"))
        mod = importlib.import_module("_make_pareto_report")

        out = os.path.join(ROOT, "docs", "pareto-frontier.md")
        gen = os.path.join(ROOT, "benchmarks", "accuracy", "_make_pareto_report.py")

        # ⚠ Round 45 修:原版在文件缺失时 `self.skipTest(...)` —— 那是**假绿**。
        #   新克隆里 `docs/pareto-frontier.md` 不存在(它是生成物),
        #   于是这条测试直接跳过,`Ran N tests / OK` 照常打印而**什么都没验**。
        #   「跳过」在测试报告上与「通过」不可区分,正是本仓反复栽的那类假绿灯
        #   (R4:先确认测到了)。改为**自己先跑生成器**(它本来就会创建该文件),
        #   再比较连续两次的输出 —— 不再依赖仓库里预先存在那个文件。
        def _generate_and_read():
            r = subprocess.run([sys.executable, "-B", gen], capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
            self.assertEqual(r.returncode, 0,
                             f"生成器退出码 {r.returncode}:\n{r.stderr[-500:]}")
            with open(out, encoding="utf-8") as fh:
                return fh.read()

        # ① 可复现(两次生成必须逐字节相同)
        first = _generate_and_read()
        self.assertTrue(os.path.exists(out), "生成器必须产出 docs/pareto-frontier.md")
        second = _generate_and_read()
        self.assertEqual(first, second, "生成器输出不确定 —— 同一输入两次生成结果不同")

        # ② 基准换算:A1=×1,C3 = 1266507/59753
        c3 = [m for m in mod.METHODS if m.name.startswith("C3")][0]
        self.assertAlmostEqual(c3.cost, 1266507 / 59753, places=3,
                               msg="C3 成本倍数未按 A1 基准换算")
        a1 = [m for m in mod.METHODS if m.name.startswith("A1")][0]
        self.assertAlmostEqual(a1.cost, 1.0, places=6, msg="基准行必须是 ×1")
        # 报告里必须写明基准,否则又变成「不知道按谁算的」
        self.assertIn("基准", first)
        self.assertIn("×1", first)

    def test_Q3_wilson_present_and_not_wald(self):
        r"""Wilson 区间必须出现在报告里,且**独立复算**一遍以证明实现没算错。

        ⚠ 我第一版硬编码了 `[88.7%, 100.0%]`(抄自 EXP-F 文档),实测实现给 88.6%。
        手算复核后确认**实现的 88.6% 才是对的**,文档里那个值与精确 Wilson 差 0.1pp。
        故改为独立复算:若实现有 bug,复算会不一致;若只是舍入差异,不会误报。
        """
        m = render_markdown(sample())
        self.assertIn("n |", m, "报告必须含样本量列 —— 100% 在 n=2 与 n=30 上不是一回事")

        z, n, p = 1.96, 30, 1.0
        den = 1 + z * z / n
        center = (p + z * z / (2 * n)) / den
        half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
        expect_lo = (center - half) * 100
        self.assertIn(f"[{expect_lo:.1f}%", m,
                      f"报告里的 Wilson 下界应等于独立复算值 {expect_lo:.1f}%")
        lo, hi = wilson(1.0, 30)
        self.assertAlmostEqual(lo * 100, expect_lo, places=6,
                               msg="wilson() 与独立复算不一致 —— 实现有 bug")
        # Wald 在 p=1 时给出退化的 [1,1];Wilson 必须给出 <1 的下界
        self.assertLess(lo, 1.0, "Wilson 下界不应等于 1(Wald 在 p=1 时会退化成 [1,1])")
        lo0, hi0 = wilson(0.0, 30)
        self.assertGreater(hi0, 0.0, "Wilson 上界不应等于 0(Wald 在 p=0 时会退化成 [0,0])")

    def test_Q4_bad_inputs_are_rejected_at_build_time(self):
        cases = {
            "缺 evidence": lambda: Method("A", 50.0, 1.0, 10, "   "),
            "n 为 0": lambda: Method("A", 50.0, 1.0, 0, "e"),
            "n 为负": lambda: Method("A", 50.0, 1.0, -5, "e"),
            "成本 < 1": lambda: Method("A", 50.0, 0.5, 10, "e"),
            "准确率越界": lambda: Method("A", 150.0, 1.0, 10, "e"),
            # ⚠⚠ 以下三条是 Round 45 红队 a3d373a8 实测的**真绕过**:
            #   `cost < 1.0` 对 NaN 恒为 False -> NaN 成本被静默接受;
            #   而 NaN 让 on_frontier 里所有比较为假 -> 支配判定被架空
            #   (实测:一个 NaN 成本/100% 准确率的方法与 80%/×1 的基线
            #    **双双**报「在前沿上」,不抛任何异常)。
            "NaN 成本": lambda: Method("A", 50.0, float("nan"), 10, "e"),
            "inf 成本": lambda: Method("A", 50.0, float("inf"), 10, "e"),
            "-inf 准确率": lambda: Method("A", float("-inf"), 1.0, 10, "e"),
            # n 非整数:会被接受并算出 [11.08%, 88.92%] 这种无意义区间
            "n 非整数": lambda: Method("A", 50.0, 1.0, 2.5, "e"),
            "n 为 bool": lambda: Method("A", 50.0, 1.0, True, "e"),
        }
        for label, fn in cases.items():
            with self.subTest(坏输入=label):
                with self.assertRaises(ValueError):
                    fn()

    def test_Q4c_mutation_after_construction_is_caught(self):
        r"""dataclass 可变 —— 构造后改 accuracy,_wilson 不得停留在旧值。

        Round 45 红队 a3d373a8 指出:`verify_report` 只看字段不看区间,
        于是「准确率 20% 却配着 100% 的 Wilson 区间」能堂而皇之出表。
        """
        m = Method("A", 100.0, 1.0, 30, "e")
        before = m.wilson
        m.accuracy = 20.0
        after = m.wilson
        self.assertNotEqual(before, after,
                            "改 accuracy 后 Wilson 仍是陈旧值 —— 会印出与准确率矛盾的区间")
        # 改成非法值也要被拒,而不是静默出表
        m.accuracy = 150.0
        with self.assertRaises(ValueError):
            _ = m.wilson

    def test_Q4d_render_is_also_gated(self):
        r"""`render_markdown` 是唯一的出表口 —— 不自检就等于门装在侧门上。

        绕过 `verify_report` 直接 `render_markdown` 曾能印出两行同名的 dup。
        """
        dup = [Method("dup", 50.0, 1.0, 10, "e1"), Method("dup", 60.0, 2.0, 10, "e2")]
        with self.assertRaises(ValueError):
            render_markdown(dup)

    def test_Q4e_hostile_types_are_rejected(self):
        r"""⚠⚠ Round 45 红队 73b9a722 实测的**高危残余**:NaN 检查靠 `value != value`,
        而**自定义类型可以把 `__ne__` 覆盖成恒 False**:

            class Ghost:
                def __eq__(self, other): return False
                def __ne__(self, other): return False

        实测 `Method("幽灵", 100.0, Ghost(), 30, "e")` **通过**纯比较式校验,
        随后 `on_frontier` 里所有比较也为假 → 支配判定**再次被架空**
        (幽灵与 80%/×1 的基线**双双**报「在前沿上」),且 `verify_report` 也拦不住
        —— 它只重跑同一套比较。当时唯一挡住它的是 `f"{cost:g}"` 抛 `TypeError`,
        属**侥幸**,不是设计。故改为**显式类型检查**。

        本用例把该类型连同 `bool` / `Decimal` / `Fraction` / `complex` 一起钉死。
        """
        class Ghost:
            def __eq__(self, other): return False
            def __ne__(self, other): return False
            def __lt__(self, other): return False
            def __le__(self, other): return False
            def __gt__(self, other): return False
            def __ge__(self, other): return False

        bad = {
            # ↓ 这一条是本次的高危残余本体
            "幽灵类型成本(可覆盖 __ne__)": lambda: Method("A", 100.0, Ghost(), 30, "e"),
            "幽灵类型准确率": lambda: Method("A", Ghost(), 1.0, 30, "e"),
            # bool 是 int 子类 —— `n` 一直拒 bool,cost/accuracy 却收,属同一份校验两种标准
            "bool 成本": lambda: Method("A", 50.0, True, 10, "e"),
            "bool 准确率": lambda: Method("A", True, 1.0, 10, "e"),
            "字符串成本": lambda: Method("A", 50.0, "1.0", 10, "e"),
            "字符串准确率": lambda: Method("A", "nan", 1.0, 10, "e"),
            "复数成本": lambda: Method("A", 50.0, complex(1, 2), 10, "e"),
            "任意对象成本": lambda: Method("A", 50.0, object(), 10, "e"),
            # Decimal('sNaN') 在旧实现下抛 InvalidOperation(**非 ValueError**)——
            # 退出码契约里「调用错」与「答案错」必须分得开,异常类型同理
            "Decimal NaN": lambda: Method("A", 50.0, D("NaN"), 10, "e"),
            "Decimal sNaN": lambda: Method("A", 50.0, D("sNaN"), 10, "e"),
            "Decimal 正常值(仍拒:类型不一致)": lambda: Method("A", 50.0, D("2.0"), 10, "e"),
            "Fraction": lambda: Method("A", 50.0, Fraction(6, 2), 10, "e"),
        }
        for label, fn in bad.items():
            with self.subTest(坏输入=label):
                with self.assertRaises(ValueError):
                    fn()
        # 合法 int 必须仍被接受(别把门关死)
        self.assertEqual(Method("A", 50, 1, 10, "e").cost, 1)
        self.assertEqual(Method("A", 50, 1, 10, "e").accuracy, 50)

    def test_Q4f_markdown_injection_is_rejected(self):
        r"""⚠⚠ Round 45 红队 73b9a722 实测的**唯一未封造假路径**。

        本模块的三列(`方法` / `证据` / `备注`)是**直接插进** Markdown 表格行的。
        字段含 `|` 或换行即**撕开列边界**,可以凭空造出一整行 ——
        实测用 `note` 注入后报告多出 3 行(期望 2 行),伪造行自带
        `×0.01 | **是**` → **可以伪造「在前沿上」的结论**,而 `verify_report` 当时不拦。

        这是本模块唯一能产出「看起来合规、实则造假」的通道,故在构造期就拒。
        选择「拒绝」而非「转义 `\|`」:拒绝是**响的**,转义是静默的。
        """
        evil = ("x | **是** | 伪造证据\n"
                "| 伪造方法 | 100.0% | 999 | [99.0%,100.0%] | ×0.01 | **是** | 伪造 | 伪造")
        bad = {
            "note 注入整行": lambda: Method("A", 50.0, 1.0, 10, "e", evil),
            "evidence 含竖线": lambda: Method("A", 50.0, 1.0, 10, "e | 伪造"),
            "name 含换行": lambda: Method("A\n| 伪造", 50.0, 1.0, 10, "e"),
            "name 含竖线": lambda: Method("A|B", 50.0, 1.0, 10, "e"),
        }
        for label, fn in bad.items():
            with self.subTest(坏输入=label):
                with self.assertRaises(ValueError):
                    fn()
        # 构造后改写也要被**出表口**拦住(render 会重跑 __post_init__)
        good = Method("好", 50.0, 1.0, 10, "e")
        good.note = evil
        with self.assertRaises(ValueError):
            render_markdown([good, Method("乙", 60.0, 2.0, 10, "e")])

    def test_Q4g_iterator_input_does_not_crash(self):
        r"""Round 45 红队 73b9a722 实测的**回归**:装上门之后传**迭代器**会炸。

        `verify_report` 先把迭代器消费光,`if not methods` 对迭代器又恒为假 ——
        旧版(没有 verify_report)能跑,新版 `TypeError: object of type 'generator'
        has no len()`。签名标注的是 `List`,但一个**只在类型外输入上才正确**的门,
        仍然是门装错了位置。
        """
        ms = sample()
        out = render_markdown(iter(ms))
        self.assertEqual(len(out.splitlines()), 2 + len(ms))
        self.assertEqual(out, render_markdown(ms), "迭代器输入与列表输入应给出相同输出")
        # verify_report 直接吃迭代器也不能炸
        verify_report(iter(ms))

    def test_Q4b_duplicate_names_rejected(self):
        ms = [Method("dup", 50.0, 1.0, 10, "e1"), Method("dup", 60.0, 2.0, 10, "e2")]
        with self.assertRaises(ValueError):
            verify_report(ms)

    def test_Q5_judgement_is_falsifiable(self):
        """把支配判定里的「至少一项严格更优」去掉,两个相同方法就会互相支配。"""
        a = Method("A", 50.0, 2.0, 10, "e1")
        b = Method("B", 50.0, 2.0, 10, "e2")
        # 无严格性要求时:互相「支配」→ 前沿被清空 → verify_report 应当拒绝出报告
        def naive_frontier(m, others):
            for o in others:
                if o is m:
                    continue
                if o.cost <= m.cost and o.accuracy >= m.accuracy:
                    return False
            return True
        self.assertFalse(naive_frontier(a, [a, b]))
        self.assertFalse(naive_frontier(b, [a, b]))
        # 本仓的实现必须给出相反结论
        self.assertTrue(on_frontier(a, [a, b]))
        self.assertTrue(on_frontier(b, [a, b]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
