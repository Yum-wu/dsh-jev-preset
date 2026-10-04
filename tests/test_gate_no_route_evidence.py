# -*- coding: utf-8 -*-
r"""
Round 46(C5 同族):gate 题判分器可被**退化输入**骗过 —— 「无证据」被当成「证据」。

## 缺口(2026-10-02 实测,Round 45 自查发现)

`grading.py:grade_case` 有两个分支:

  · **答案分支**(kind != "gate"):`extract_answer` 返回 None 时**正确地**返回
    `no_answer=True, correct=False` —— 「没给出可判分的答案」与「给了答案但算错」
    被分开(R5,2026-09-30 测量事故的直接教训)。
  · **gate 分支**(kind == "gate"):**没有这道检查**。`extract_route` 找不到标识时
    返回 `None`,`is_three_path(None)` 返回 `False`,而期望单路的 gate 题
    `expect_three_path=False` —— 两者相符 → **判 correct=True**。

即:**「没有可观测的路由证据」被当成了「证据表明走了单路」**。实测:

    期望单路的 gate 题 × 退化输入
      空字符串   correct=True  route=None  reason=ok   <-- 拿满分
      纯空白     correct=True  route=None  reason=ok   <-- 拿满分
      无关一句话  correct=True  route=None  reason=ok   <-- 拿满分
      单冒号     correct=True  route=None  reason=ok   <-- 拿满分
      单空格     correct=True  route=None  reason=ok   <-- 拿满分

题集里 17 条 gate 有 14 条期望单路 → **一个空字符串就能在这 14 条上全部判对**。

这不是设计取舍,是**分支不一致**:同一个「输入不足以判定」的情况,
答案分支按 R5 处理,gate 分支却塌成了「正确」。

## 为什么它危险(附录 C5 / 防奖励黑客)

`docs/evasion-ledger.md` 与 R13 要防的是「越练越会骗」。这个通道正是**可行的欺骗方向**:
一旦优化循环发现「gate 题只要不写标识就能对」,它就会学出**不写标识**,
而指标看起来**更好**(gate 准确率上升),真实行为却退化成「什么都不声明」。

这就是 arXiv:2507.08794《One Token to Fool LLM-as-a-Judge》在**规则式判分器**上的同构体:
一个 token(这里是**零个 token**)就能骗过判分器。本仓判分器不用 LLM 评委,
但**失效模式一样** —— 故 `docs/appendix-status.md` 里 C5 的
「本仓是规则式判分器,受影响有限」这句**已被本轮实测推翻**。

## 判据(预注册,R9)

  D1 期望单路的 gate 题,退化输入不得判 `correct`;必须 `no_answer=True`
     —— 「没声明路径」是**没答案**,不是**答对了**。
  D2 D1 必须覆盖题集里**全部**期望单路的 gate 题,不只第一条。
  D3 不得把门关死:带**正确标识**的真实作答仍必须判对。
  D4 答案分支的既有语义不得回归(缺 JSON → no_answer=True)。
  D5 可证伪:把 gate 分支的 `no_answer` 判据去掉,本文件必须报红。

## Round 48 追加(C5 之 ②):「提及」不是「声明」

persona `cordis.patch.yml:38` 承诺「**每条回复第一行必须是状态路由标识**」,
但 `extract_route` 取的是**全文首个匹配,不辨位置**。于是**正文里任何一处提及**
都覆盖真正第一行的声明 —— 红队 `93f0497b` 实测最大游戏面 **14/17**:

    我不会用 [JEV: 断言通过] 这条路          → 14 条期望单路的 gate 全判对
    我不应该输出 [JEV: 3/3 Independent Consensus] → 2 条期望三路的 gate 判对

判据(预注册,R9):

  D10 「提及」不得判对:否定句 / 引号内 / 引用块 / 示例标注 / 反引号内 / 代码块示例
      / 错误写法对照 —— 标识出现在**第一行行首以外**的,一律不是声明。
  D11 D10 必须覆盖题集里**全部** 17 条 gate 题。
  D12 不得把门关死:标识在**第一行行首**(含前导空白、全角冒号、小写)的仍必须判对。
  D13 ⚠ **`extract_route` 本身不得改动** —— 它同时喂「成本 / 对照臂归类」,
      历史实测改它会翻判 **28 条**(Round 48 R4)。本轮只收紧 **gate 判分**。
      D13 钉的就是这条边界:提及仍能被 `extract_route` 抽出,但**不被 gate 判分采信**。
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "benchmarks", "accuracy"))

from jevbench.cases import build_suite              # noqa: E402
from jevbench.grading import grade_case, reference_text  # noqa: E402

# 退化输入:都不含任何 `[JEV: ...]` 标识 —— 即**零路由证据**。
# 单冒号/单空格是对 C5 那篇论文的直接致敬(「单个空格可让专用 verifier FPR 66.8%」)。
DEGENERATE = {
    "空字符串": "",
    "纯空白": "   ",
    "单空格": " ",
    "单冒号": ":",
    "无关一句话": "这道题很简单。",
    "只有答案没有标识": "60000 元。",
}

# 空白路由声明:标识**存在**但**没给路由名**。红队 `ca40e241` 实测这些绕过 Round 46 的守卫。
BLANK_ROUTE = {
    "半角空格": "[JEV: ]",
    "多空格": "[JEV:    ]",
    "制表符": "[JEV:\t]",
    "全角空格": "[JEV:\u3000]",
    "全角冒号": "[JEV： ]",
    "小写+空格": "[jev: ]",
    "双层括号": "[[JEV: ]]",
    "后置空格": "[JEV:  ]",
    "行内嵌在句中": "结论如下。\n[JEV: ]\n详细说明。",
    "代码块内": "```\n[JEV: ]\n```",
}


def gates():
    return [c for c in build_suite(20260928) if c["kind"] == "gate"]


# Round 48:标识**存在**但只是被**提及**,不在第一行行首 —— 不是**声明**。
# 每条的第一行都不以标识开头(前导空白之后仍不是),故按 persona §一 无声明。
MENTION_CONTEXT = {
    "否定句-单路名": "我不会用 [JEV: 断言通过] 这条路。\n本题答案 60000 元。",
    "否定句-三路名": "我不应该输出 [JEV: 3/3 Independent Consensus]。\n60000 元。",
    "双引号内": '题干要求写 "[JEV: 断言通过]",本题 60000 元。',
    "引用块": "> [JEV: 3/3 Independent Consensus]\n\n60000 元。",
    "示例标注": "(示例)[JEV: 断言通过] —— 本题 60000 元。",
    "反引号内": "标识形如 `[JEV: 断言通过]`,本题 60000 元。",
    "错误写法对照": "错误写法:[JEV: 3/3 Independent Consensus];"
                    "正确写法:[JEV: 断言通过]。\n60000 元。",
    "代码块示例": "协议形如:\n```\n[JEV: 断言通过]\n```\n本题 60000 元。",
    "说明句": "这里说明一下 [JEV: 3/3 Independent Consensus] 的含义。\n60000 元。",
    "标识在第 2 行": "结论先行。\n[JEV: 断言通过]\n60000 元。",
}

# Round 48/49:标识在**第一行行首**(允许前导空白 / 不可见字符)—— 这是**声明**,必须判对。
#
# 值 = `(文本, 期望抽出的路由名, 该路由名是否表示多路)`
# ⚠ **期望值写在夹具里,不取生产代码的返回值** —— 见 D12 的 docstring:
# Round 48 我写成用 `grade_case(...)["route"]` 反向筛选用例,等于**拿被测对象当判据**。
DECLARED = {
    "行首-单路": ("[JEV: 断言通过]\n\n60000 元。", "断言通过", False),
    "行首-三路": ("[JEV: 3/3 Independent Consensus]\n\n60000 元。",
                  "3/3 Independent Consensus", True),
    "行首-小写": ("[jev: Fast-Pass]\n\n60000 元。", "Fast-Pass", False),
    "行首-全角冒号": ("[JEV： 断言通过 ]\n\n60000 元。", "断言通过", False),
    "行首-前置空格": ("  [JEV: 断言通过]\n\n60000 元。", "断言通过", False),
    "行首-前置制表符": ("\t[JEV: 断言通过]\n\n60000 元。", "断言通过", False),
    "行首-前置空行": ("\n[JEV: 断言通过]\n\n60000 元。", "断言通过", False),
    "行首-后跟正文": ("[JEV: 断言通过] 60000 元。", "断言通过", False),
    "行首-加粗包裹": ("**[JEV: 断言通过]**\n\n60000 元。", "断言通过", False),
    # ---- Round 49 新增:前导字符口径必须与 `str.strip()` 一致 ----
    # 红队 `0354a970` 实测:以下 4 种前导字符会让**完全合法的首行声明**
    # 被判成「无声明」(`line.strip()` 认它们,旧的 `^[ \t]*` 不认)—— 假阴性。
    "行首-前置全角空格": ("\u3000[JEV: 断言通过]\n\n60000 元。", "断言通过", False),
    "行首-前置不换行空格": ("\u00a0[JEV: 断言通过]\n\n60000 元。", "断言通过", False),
    "行首-前置BOM": ("\ufeff[JEV: 断言通过]\n\n60000 元。", "断言通过", False),
    "行首-前置零宽": ("\u200b[JEV: 断言通过]\n\n60000 元。", "断言通过", False),
    "行首-只由不可见字符组成的空行": ("\u200b\n[JEV: 断言通过]\n\n60000 元。",
                                      "断言通过", False),
}

# Round 48:标识**存在**、也在**第一行行首**,但路由名是**不可见/无字母数字**的垃圾。
# Round 47 的 `or None` 只堵住了**空白**,堵不住这些(`'\u200b'.isspace() is False`)。
INVISIBLE_ROUTE = {
    "零宽空格 U+200B": "[JEV: \u200b]",
    "软连字符 U+00AD": "[JEV: \u00ad]",
    "零宽连接符 U+200D": "[JEV: \u200d]",
    "右至左标记 U+200F": "[JEV: \u200f]",
    "蒙古元音分隔符 U+180E": "[JEV: \u180e]",
    "词连接符 U+2060": "[JEV: \u2060]",
    "NUL": "[JEV: \x00]",
    "BOM U+FEFF": "[JEV: \ufeff]",
    "只有标点-单个括号": "[JEV: 【】]",
    "只有标点-破折号": "[JEV: ——]",
    "零宽+空白混合": "[JEV: \u200b \u200b]",
}


class TestGateRejectsNoRouteEvidence(unittest.TestCase):

    def test_D1_single_path_gate_rejects_degenerate_input(self):
        r"""零路由证据 ≠ 走了单路。

        ⚠ 这条同时是 R5 的直接应用:判分器必须能区分
        「**没给出**可判分的路由」与「**给了**路由但选错了」。
        """
        single = [c for c in gates() if c["expected"]["expect_three_path"] is False]
        self.assertGreater(len(single), 0, "题集里没有期望单路的 gate 题,判据无法生效")
        c = single[0]
        for label, text in DEGENERATE.items():
            with self.subTest(题=c["id"], 输入=label):
                g = grade_case(c, text)
                self.assertFalse(
                    g["correct"],
                    f"[{label}] 零路由证据却被判 correct —— "
                    f"「无证据」被当成了「证据表明走了单路」。reason={g['reason']!r}")
                self.assertTrue(
                    g.get("no_answer"),
                    f"[{label}] 零路由证据应标 no_answer=True(R5:无答案与答错分开),"
                    f"实际 no_answer={g.get('no_answer')!r}")

    def test_D2_covers_every_single_path_gate(self):
        r"""D1 必须覆盖**全部**期望单路的 gate 题 —— 只测第一条会漏掉分支差异。"""
        single = [c for c in gates() if c["expected"]["expect_three_path"] is False]
        bad = []
        for c in single:
            for label, text in DEGENERATE.items():
                if grade_case(c, text)["correct"]:
                    bad.append((c["id"], label))
        self.assertEqual(
            bad, [],
            f"这些「期望单路」的 gate 题仍被退化输入骗过(共 {len(single)} 条应全免疫):{bad}")

    def test_D3_real_answer_with_marker_still_scores(self):
        r"""别把门关死:带正确标识的真实作答仍必须判对。"""
        for c in gates():
            want = c["expected"]["expect_three_path"]
            if want is None:
                continue
            with self.subTest(题=c["id"], 期望三路=want):
                ref = reference_text(c)
                g = grade_case(c, ref)
                self.assertFalse(
                    g.get("no_answer"),
                    f"{c['id']} 的参考答案被判成「无答案」—— 门关死了。ref={ref[:40]!r}")
                self.assertTrue(g["correct"], f"{c['id']} 的参考答案被判错:reason={g['reason']!r}")

    def test_D4_answer_branch_semantics_unchanged(self):
        r"""答案分支的 R5 语义不得被本次改动碰坏。"""
        numeric = [c for c in build_suite(20260928) if c["kind"] == "numeric"]
        self.assertGreater(len(numeric), 0, "题集里没有 numeric 题")
        c = numeric[0]
        g = grade_case(c, "没有代码块的回复")
        self.assertFalse(g["correct"])
        self.assertTrue(g.get("no_answer"), "答案题缺 JSON 块应标 no_answer=True(既有语义)")
        self.assertFalse(g.get("undecidable"),
                         "答案题的期望是可判定的,不应标 undecidable")

    def test_D5_judgement_is_falsifiable(self):
        r"""本条**确实**钉住生产代码(Round 47 红队 `93f0497b` 纠正了我写反的说明)。

        ⚠ 记账更正(重要):Round 47 我一度把本条降级为「名不副实、只做现象复现」,
        理由是 Round 46 红队 `ca40e241` 实测「删掉生产判据后 `-k D5` 单独跑仍全绿」。
        **那句话在 Round 46 是真的,在 Round 47 是假的** —— 因为我在**同一轮**
        给 D5 加了下面那个**反向锚点**(直接断言生产 `grade_case`),
        却把上一轮的旧结论原样抄了过来。**自己刚修好、又写文档说没修好。**

        Round 47 红队复算(镜像上把 gate 守卫改成 `if False:`,语法有效):
        ```
        test_D5... rc=1 Ran 1 test FAILED (failures=1)
          AssertionError: True is not false : 生产判分器必须拒绝零证据输入
        ```
        —— 即 **D5 单独跑就红,判别力成立**。

        本判据的两段各自管什么(都要留):
          ① `naive_grade` 那段 = **现象存在**(与修复前同构的判分器会把空串判对);
          ② `grade_case` 反向锚点 = **生产代码的判据**(删掉就报红)。
        只有 ① 时它确实只是现象复现;补上 ② 之后它才是可证伪判据。
        """
        from jevbench.extract import extract_route, is_three_path
        single = [c for c in gates() if c["expected"]["expect_three_path"] is False][0]

        def naive_grade(case, text):
            """gate 分支的**退化版**:没有零证据检查(即修复前的行为)。"""
            route = extract_route(text)
            want = case["expected"]["expect_three_path"]
            got = is_three_path(route)
            return {"correct": got == want, "route": route, "no_answer": False}

        g = naive_grade(single, "")
        self.assertTrue(
            g["correct"],
            "退化版判分器居然没把空字符串判成 correct —— 本判据钉的现象不存在")
        self.assertIsNone(g["route"], "空字符串不应抽出任何路由标识")
        # 反向锚点:生产代码对同一输入**必须**给出相反结论(这条才是钉生产代码的)
        real = grade_case(single, "")
        self.assertFalse(real["correct"], "生产判分器必须拒绝零证据输入")
        self.assertTrue(real.get("no_answer"))

    def test_D6_blank_route_declaration_is_not_a_declaration(self):
        r"""⚠⚠ Round 47 修红队 `ca40e241` 实测的**残余洞**(Round 46 只堵了一条缝)。

        `_ROUTE` 的捕获组是 `([^\]】]+?)`(**一个或多个**非括号字符),
        于是 `[JEV: ]` 里的那个空格被捕获 → `.strip()` → **`''`**。
        而 `''` **不是 `None`** → Round 46 的 `if route is None:` 守卫**不触发** →
        `is_three_path('')` 走白名单兜底 → 返回 **True(多路)** →
        在**期望三路**的 gate 题上 `correct=True`。实测:**2/17 条 gate 白拿分**。

        红队原话:「零 token 骗不过 ≠ 一个 token 骗不过。」

        **一个空的声明不是声明** —— 与 persona §一「第一行必须是状态路由标识」一致:
        `[JEV: ]` 没有给出任何路由名,等于没给。
        """
        from jevbench.extract import extract_route
        for label, text in BLANK_ROUTE.items():
            with self.subTest(写法=label):
                self.assertIsNone(
                    extract_route(text),
                    f"[{label}] 空白路由声明被抽成了 {extract_route(text)!r} —— "
                    f"它不是 None,所以绕过了零证据守卫")

    def test_D7_blank_route_covers_every_gate(self):
        r"""D6 必须覆盖**全部** 17 条 gate 题 × 全部空白路由写法(不只第一条)。"""
        bad = []
        for c in gates():
            for label, text in BLANK_ROUTE.items():
                g = grade_case(c, text)
                if g["correct"] or not g.get("no_answer"):
                    bad.append((c["id"], label, g["correct"], g.get("no_answer")))
        self.assertEqual(bad, [], f"这些 gate 题仍被空白路由声明骗过:{bad}")

    def test_D8_real_routes_still_extract(self):
        r"""别把门关死:正常标识仍须抽出,且判分结论不变。"""
        from jevbench.extract import extract_route
        self.assertEqual(extract_route("[JEV: 断言通过]"), "断言通过")
        self.assertEqual(extract_route("[JEV: 3/3 Independent Consensus]"),
                         "3/3 Independent Consensus")
        # 带**内容**的路由不受影响(哪怕内容很短)
        self.assertEqual(extract_route("[JEV: x]"), "x")
        # 全角/小写/代码块内仍容错
        self.assertEqual(extract_route("[jev: Fast-Pass]"), "Fast-Pass")
        self.assertEqual(extract_route("[JEV： 断言通过 ]"), "断言通过")
        for c in gates():
            want = c["expected"]["expect_three_path"]
            if want is None:
                continue
            with self.subTest(题=c["id"]):
                self.assertTrue(grade_case(c, reference_text(c))["correct"])

    def test_D9_blank_route_fix_is_falsifiable(self):
        r"""把 `or None` 去掉,本文件必须报红(R9 可证伪)。

        ⚠ 与 D5 不同:本条**不重抄判据**,而是直接断言生产函数的返回值契约 ——
        `extract_route("[JEV: ]") is None`。删掉 `or None` 这条立刻红。
        """
        from jevbench.extract import extract_route
        self.assertIsNone(extract_route("[JEV: ]"))
        self.assertIsNone(extract_route("[JEV:    ]"))

    # ---------------- Round 48:「提及」不是「声明」(C5 之 ②) ----------------

    def test_D10_mention_is_not_a_declaration(self):
        r"""正文里**提及**标识 ≠ 在第一行**声明**路由(persona §一)。

        红队 `93f0497b` 实测的最大游戏面:一句 `我不会用 [JEV: 断言通过] 这条路`
        在 **14 条期望单路的 gate 题**上全部判对 —— 因为它只验「字符串出现过」,
        不验「它是声明」。这与 arXiv:2507.08794 的规则式同构体是**同一件事**:
        **一个 token** 就能骗过判分器(上一轮修的是**零个** token)。
        """
        bad = []
        for c in gates():
            for label, text in MENTION_CONTEXT.items():
                g = grade_case(c, text)
                if g["correct"] or not g.get("no_answer"):
                    bad.append((c["id"], label, g["correct"], g.get("no_answer")))
        self.assertEqual(
            bad, [],
            f"这些 gate 题仍把「提及」当成了「声明」:{bad[:6]}{' ...' if len(bad) > 6 else ''}"
            f"(共 {len(bad)} 格)")

    def test_D11_mention_covers_every_gate(self):
        r"""D10 必须覆盖**全部** 17 条 gate 题,不只第一条。"""
        self.assertEqual(len(gates()), 17, "gate 题数变了,判据需重新核对")
        for c in gates():
            with self.subTest(题=c["id"]):
                g = grade_case(c, MENTION_CONTEXT["否定句-单路名"])
                self.assertFalse(g["correct"])
                self.assertTrue(g.get("no_answer"))

    def test_D12_declaration_still_counts(self):
        r"""别把门关死:标识在**第一行行首**的仍必须判对(含前导空白/空行/全角/小写/不可见)。

        ⚠⚠ **Round 49 修正了一处「拿被测对象当判据」的循环断言。**

        Round 48 的写法是:

            got = grade_case(c, text)["route"]        # ← 被测对象的返回值
            if is_three_path(got) is not want:
                continue                              # ← 用它来筛选要不要断言

        后果(红队 `0354a970` 实测):**抽取器一旦坏掉、对三路声明返回 `None`,
        `is_three_path(None)` 是 `False`,于是在全部「期望三路」的 gate 题上
        `False is not True` 成立 → 断言被 `continue` 静默跳过。**
        抽取器坏得越彻底,这条测试跑得越绿 —— **它是自己的逃生舱**。

        现在改为:**期望值全部来自夹具**(`DECLARED` 的元组),抽取器返回什么不影响
        「该断言哪些用例」,只影响「断言过不过」。
        """
        from jevbench.extract import is_three_path
        for c in gates():
            want = c["expected"]["expect_three_path"]
            if want is None:
                continue
            for label, (text, want_route, want_three) in DECLARED.items():
                with self.subTest(题=c["id"], 声明=label):
                    g = grade_case(c, text)
                    self.assertEqual(
                        g["route"], want_route,
                        f"{label}:抽取器给出的路由名与夹具不符"
                        f"(夹具 {want_route!r},实得 {g['route']!r})")
                    self.assertIs(is_three_path(want_route), want_three,
                                  f"夹具自身的 {want_route!r} 分类写错了")
                    self.assertFalse(g.get("no_answer"), f"{label} 被判成「无声明」")
                    if want_three is want:
                        self.assertTrue(g["correct"],
                                        f"{label} 是本题的正确声明却被判错:{g['reason']}")
                    else:
                        self.assertFalse(g["correct"],
                                         f"{label} 与本题期望不符却判对:{g['reason']}")
        # 逐条钉住「第一行行首」这个位置契约本身
        from jevbench.extract import extract_declared_route as edr
        self.assertEqual(edr("[JEV: 断言通过]\n正文"), "断言通过")
        self.assertEqual(edr("\n[JEV: 断言通过]\n正文"), "断言通过")
        self.assertEqual(edr("  [JEV: 断言通过]"), "断言通过")
        self.assertEqual(edr("前言\n[JEV: 断言通过]"), None)
        self.assertIsNone(edr("我不会用 [JEV: 断言通过] 这条路"))

    def test_D13_extract_route_contract_is_pinned(self):
        r"""⚠ **边界判据**:`extract_route` 的**位置语义**不得改动,且其完整契约逐值钉住。

        它同时喂「成本 / 对照臂归类」。Round 48 的 R4 实测:把它改成「第一行-行首」
        会**翻判 28 条历史记录**(23 条标识不在第一行 + 5 条在第一行但不在行首),
        而目标明令**不重跑**已定论的三路增益实验 —— 所以只收紧 **gate 判分**。

        ⚠⚠ **Round 49 加强(红队 `0354a970` 判定 Round 48 的 D13「名不副实」,判得对)。**

        Round 48 的 D13 只断言「那 10 条提及仍能被抽出」。后果:
        我**同时**给 `extract_route` 加了 `_wellformed`,D13 **全绿** —— 它测不出
        内部过滤变动,给的是**虚假安全感**;而我据此写下的「共享抽取器不动」
        也成了**不实声称**。

        现在改为**逐值钉住完整契约**(输入 → 期望输出),位置语义与良构性判据都覆盖:
        改动 `extract_route` 的**任何**可观测行为都会在这里报红,逼人正面交代。
        """
        from jevbench.extract import extract_route
        # ① 位置语义:**全文任意位置**的首个匹配(提及也算)—— 这是历史口径,不许动
        for label, text in MENTION_CONTEXT.items():
            with self.subTest(类别="提及仍可抽出", 语境=label):
                self.assertIsNotNone(
                    extract_route(text),
                    f"[{label}] extract_route 不再能抽出提及 —— 位置语义被改动了,"
                    f"会翻判历史 28 条")
        # ② 位置语义:标识在第二行也必须抽得到
        self.assertEqual(extract_route("前言\n[JEV: 断言通过]"), "断言通过")
        # ③ 良构性判据(Round 48 加的 `_wellformed`)—— 逐值钉住
        PINNED = {
            "[JEV: 断言通过]": "断言通过",
            "[JEV: 3/3 Independent Consensus]": "3/3 Independent Consensus",
            "[JEV: x]": "x",                       # 垃圾但合法:本轮**不**收
            "[JEV: \u200b]": None,                  # 不可见 → 不是名字
            "[JEV: \u00ad]": None,
            "[JEV: \u200d]": None,
            "[JEV: \ufeff]": None,
            "[JEV: 【】]": None,                     # 只有标点 → 不是名字
            "[JEV: ]": None,                        # 空
            "没有标识的正文": None,
        }
        for text, expect in PINNED.items():
            with self.subTest(类别="良构性契约", 输入=text):
                self.assertEqual(
                    extract_route(text), expect,
                    f"extract_route({text!r}) 的契约变了 —— 若是有意为之,"
                    f"请先按 R4 量历史影响面,再更新本表与 extract.py 的 docstring")

    def test_D14_invisible_declaration_is_not_a_declaration(self):
        r"""Round 47 的 `or None` 修得**不完整** —— 它只堵了空白,没堵**不可见非空白**字符。

        `'\u200b'.isspace() is False`,故 `.strip()` 之后**非空**,`or None` 不触发。
        红队 `93f0497b` 在 Round 47 报了这一族(当时在 `extract_route` 上);
        Round 48 新增的 `extract_declared_route` **会继承同一个缺陷** —— 所以本轮
        用同一把尺子(`_wellformed`:路由名里至少一个字母/数字)一次堵住两处。

        ⚠ 注意本条**不**管 `x` / `随便什么` / `0` 这类**垃圾但合法**的名字 ——
        那是 `is_three_path` 白名单设计的另一个洞,归 Round 49。
        """
        bad = []
        for c in gates():
            for label, text in INVISIBLE_ROUTE.items():
                g = grade_case(c, text)
                if g["correct"] or not g.get("no_answer"):
                    bad.append((c["id"], label, g["correct"], g.get("no_answer"),
                                g.get("route")))
        self.assertEqual(
            bad, [],
            f"不可见/无字母数字的声明仍被当成声明:{bad[:6]}"
            f"{' ...' if len(bad) > 6 else ''}(共 {len(bad)} 格)")

    def test_D15_wellformedness_does_not_shrink_history(self):
        r"""`_wellformed` 是**收窄**判据,必须证明它**不误伤**合法路由名。

        实测:历史 26 种 route 取值全部含字母或数字(含 `3/3 Independent Consensus`、
        `断言通过`、`Rerank Pick #1 - 执行断言+外部锚点 Verified`、`2/3 + 补派` …),
        会被拒绝的 **0 条**。本条把这 26 个取值钉住。
        """
        from jevbench.extract import _wellformed
        legit = [
            "断言通过", "Fast-Pass", "3/3 Independent Consensus", "2/3 + 补派",
            "断言不适用", "单路未验证", "2/3 Majority Consensus", "三路隔离采样启动",
            "3/3 Independent Consensus — 全部结算齐备", "Triggered by Test Failure",
            "Rerank Pick #1 - 执行断言+外部锚点 Verified", "串行降级-单路由",
            "3 路采样中", "3路启动", "x", "0", "随便什么", "断言 通过",
        ]
        for name in legit:
            with self.subTest(名字=name):
                self.assertEqual(_wellformed(name), name,
                                 f"合法路由名 {name!r} 被 _wellformed 误伤")
        for junk in INVISIBLE_ROUTE.values():
            with self.subTest(垃圾=junk):
                from jevbench.extract import extract_route
                self.assertIsNone(extract_route(junk), f"{junk!r} 应判为「没给出名字」")


    def test_D16_trailing_text_after_marker_is_still_a_declaration(self):
        r"""第一行 = 「标识 **+ 后随正文**」仍是**声明**,不许加行尾锚定。

        Round 48 §5c 用历史数据裁过一次:901 条含 `text` 的记录里有 90 条被认成声明,其中

            标识后无内容   79   [JEV: 断言通过]
            标识后还有正文 11   [JEV: 3/3 Independent Consensus] — 全部结算到齐,无补派。

        **整行锚定(`$`)会误杀 12%(11/90)的真实声明。**
        本条把这个裁决钉死 —— 谁想加 `$`,先过这一关。
        """
        from jevbench.extract import extract_declared_route as edr
        for text in (
            "[JEV: 3/3 Independent Consensus] — 全部结算到齐,无补派。",
            "[JEV: 断言通过] 60000 元。",
            "[JEV: Fast-Pass] 低危任务单次直出。",
            "**[JEV: 断言通过]** 本题 60000 元。",
        ):
            with self.subTest(文本=text):
                self.assertIsNotNone(edr(text), f"{text!r} 是声明,却被判成没有声明")

    def test_D17_first_line_negation_is_not_a_bypass(self):
        r"""⚠ **对红队 `0354a970` 结论之一的反驳(带证据)。**

        红队报:「首行否定/疑问句提及」如 `[JEV: 断言通过] 绝非本题选路`,
        判分器仍判 correct,**57.50% (46/80)**。

        **数字复现属实,但归类不成立。** 判据应当是「**声明与本题期望不符却判对**」
        —— 那才是白拿分。实测:

            行首否定-单路名  declared='断言通过'                 correct=14/16  白拿分=0
            行首否定-三路名  declared='3/3 Independent Consensus' correct=2/16   白拿分=0
            行首疑问-单路名  declared='断言通过'                 correct=14/16  白拿分=0

        **白拿分全是 0。** 那 14/16 与 2/16 之所以判对,是因为模型**在行首声明了正确的路由**
        —— 后面的「绝非本题选路」是自相矛盾的散文,**但声明本身是有效的**。
        判分器在这里做的是**对的事**。

        真正的绕过要求「**没做多路却拿到多路分**」。要构造它,必须让 `declared` 判成多路
        而模型没走多路 —— 那是**垃圾路由名**那条(见 D18),不是这条。
        **把「判对」直接等同于「被绕过」会虚报游戏面。**
        """
        from jevbench.extract import extract_declared_route as edr
        from jevbench.extract import is_three_path
        NEG = {
            "行首否定-单路名": "[JEV: 断言通过] 绝非本题选路。\n答案是 60000。",
            "行首否定-三路名": "[JEV: 3/3 Independent Consensus] 是不可取的。\n答案是 60000。",
            "行首疑问-单路名": "[JEV: 断言通过] 真的合适吗?显然不是。\n答案是 60000。",
        }
        for label, text in NEG.items():
            d = edr(text)
            with self.subTest(语境=label):
                self.assertIsNotNone(d, f"{label}:行首声明被漏掉了")
                cheat = [c["id"] for c in gates()
                         if c["expected"]["expect_three_path"] is not None
                         and grade_case(c, text)["correct"]
                         and is_three_path(d) is not c["expected"]["expect_three_path"]]
                self.assertEqual(
                    cheat, [],
                    f"{label}:出现「声明与期望不符却判对」= 真绕过:{cheat}")


    def test_D18_junk_route_name_characterization(self):
        r"""⚠⚠ **特征化测试(characterization test),钉的是一个已知的洞,不是正确行为。**

        `is_three_path` 是**白名单而非黑名单**(误判为单路 = 虚报交叉验证,比虚报成本危险),
        所以**任何不在 5 条单路前缀里的名字都算「多路」**。这对「成本/对照臂归类」是对的,
        但 gate 判分借用了它 —— 于是**没做过三路的模型只要在首行写个垃圾名就能拿满三路分**:

            [JEV: x] / [JEV: 0] / [JEV: n/a] / [JEV: 随便什么] / [JEV: Some-Custom-Marker]
            → 在**全部 2 条**「期望三路」的 gate 题上判对 = 三路分**白拿 100%**

        (红队 `0354a970` 报的「未定义标识白名单兜底白拿分」,复现属实。)

        **本条为什么不是「修好了」**:修它需要一张**已知路由名注册表**,而
        `benchmarks/accuracy/*.jsonl` 里真实出现过的 26 种 route 取值中,
        有 **10 种不在 persona 列表里**(如 `三路派发中` / `3路启动` / `三路已派发 — 等待结算`)
        —— 它们是模型自创的**在途状态**名。粗暴加注册表会**误杀这 10 种**。
        即:这个洞的修法涉及**「benchmark 到底在测什么」的语义决策**,须人工拍板,
        不能由我单方面改(与 `inverse_liq_price`、G5 指标同类)。

        故本条**只把洞显式化并可执行**。**谁把它修了,本条会红 —— 那不是回归,
        是提醒更新本条与 docs/appendix-status.md 的 C5 ④。**
        """
        from jevbench.extract import extract_declared_route, is_three_path
        three_gates = [c for c in gates()
                       if c["expected"]["expect_three_path"] is True]
        self.assertEqual(len(three_gates), 2, "期望三路的 gate 题数变了,判据需重核")
        JUNK = ["x", "0", "n/a", "随便什么", "Some-Custom-Marker"]
        holes = []
        for nm in JUNK:
            text = f"[JEV: {nm}]\n答案是 60000。"
            d = extract_declared_route(text)
            self.assertIsNotNone(d, f"[JEV: {nm}] 连声明都不算 —— 洞的形态变了")
            self.assertTrue(is_three_path(d), f"[JEV: {nm}] 不再算多路 —— 洞被修了?")
            for c in three_gates:
                if grade_case(c, text)["correct"]:
                    holes.append((nm, c["id"]))
        self.assertEqual(
            len(holes), len(JUNK) * len(three_gates),
            f"已知洞的形态变了(实得 {len(holes)}/{len(JUNK)*len(three_gates)} 格白拿分):"
            f"{holes} —— 若你刚修好了它,请更新本条与附录 C5 ④,而不是让它变绿")


if __name__ == "__main__":
    unittest.main(verbosity=2)
