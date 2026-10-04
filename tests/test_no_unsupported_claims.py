# -*- coding: utf-8 -*-
"""
A6:persona 硬编码实测数字 —— 把**后验结果**写成**手段的先验属性**,并隐去基线。

缺陷(附录 A6,严重度低,但性质是「契约说谎」而非「数字过时」):
  persona §二① 写「实测复算正确率 100%,成本仅 ×2.0」;
  §三 3.0b 写「题干结构化 +89pp(5/5 模型达 100%)」。

  两处问题:
  ① **「复算正确率 100%」是后验**:真实数据是 24/30 → 30/30(p=0.0312),
     即**基线 80%,复算后 100%**。写成「复算正确率 100%」抹掉了基线,
     读起来像「不做复算也只有 100%」或「复保证 100%」——
     这正是 R13 关心的形态:**指标被写成好看的样子**。
  ② 数字会随模型/题集漂移,而 persona 里的数字**没有任何出处标注**,
     第三方无法判断它是何时何地测的,也就无法在漂移时发现它已失效。

判据(预注册,R9):
  T1 persona 里的效果数字必须带**基线与样本量**(如 24/30→30/30),不得只报终值
  T2 persona 不得出现「正确率 100%」这种**缺基线**的表述
  T3 每个效果数字必须能对应到仓内**可查的出处文件**,并注明样本量与显著性
  T4 persona 必须写明这些数字是**本仓当前题集下的观测**,不是普适保证
     —— 否则换个题集它就成了新的「验证剧场」
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
DOCS = os.path.join(PLUGIN_ROOT, "docs")

# persona 中允许出现的效果数字 → 必须同段出现的出处标注关键词
EFFECT_CLAIMS = [
    ("+89pp", "题干结构化"),
    ("×2.0", "执行断言"),
    ("×1", "题干结构化"),
]


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


class TestNoUnsupportedEffectNumbers(unittest.TestCase):

    def setUp(self):
        self.persona = persona_prefix()
        self._assert_truncated()

    def _assert_truncated(self):
        """截断自证:persona 里不得含 YAML 注释 / 配置行(A9 教训)。"""
        self.assertNotRegex(self.persona, r"^\s*-\s+id:\s+delegation",
            "personaPrefix 截断越界,把 preset 配置行吞进来了")
        self.assertNotRegex(self.persona, r"^\#\s{2,}",
            "personaPrefix 截断越界,把 YAML 注释吞进来了")

    def test_T1_effect_numbers_carry_baseline(self):
        r"""效果数字必须带基线与样本量,不得只报终值。

        「正确率 100%」缺基线 = 抹掉 80% 的起点 = R13 形态(指标写成好看的样子)。

        判据修正(红队 1eef5957 变体 8 实证):初版把分母写死 `\d+\s*/\s*30`,
        于是「12/15→15/15」全绿;更糟的是**反向失效** ——
        将来真值扩样到 50 题,正确写法 `24/50→50/50` 会被这条**报红**,
        即**测试惩罚正确的更新**。现改为「任意分子/分母形态」而非固定分母。
        """
        for m in re.finditer(r"正确率\s*100\s*%", self.persona):
            ctx = self.persona[max(0, m.start() - 120):m.end() + 120]
            with self.subTest(片段=ctx[:40]):
                self.assertRegex(
                    ctx, r"\d+\s*/\s*\d+",
                    "persona 出现无基线的「正确率 100%」—— "
                    "真实数据是 24/30(80%)→ 30/30,抹掉基线正是 R13 关心的形态")
                # 还要说明是「复算后」而非「先验」
                self.assertRegex(ctx, r"复算后|→|提到|从",
                    "「正确率 100%」必须写成**复算后**的结果,不是先验属性")

    def test_T1b_no_abbreviated_denominator(self):
        """「正确答案」里的 `24/30` 不得被简写成只有终值(如「30/30 全对」)。

        这条把 T1 的分母检查从「必须含 30」放宽成「必须含**某个**分母」之后,
        仍保留一条底线:凡出现「正确率 X%」,同段必须有对应分数。
        """
        for m in re.finditer(r"正确率\s*(\d+(?:\.\d+)?)\s*%", self.persona):
            pct = float(m.group(1))
            ctx = self.persona[max(0, m.start() - 120):m.end() + 120]
            if pct < 100:
                continue  # 非 100% 的正确率本身已隐含未满分,不需基线
            with self.subTest(片段=ctx[:40]):
                self.assertRegex(ctx, r"\d+\s*/\s*\d+",
                    "「正确率 100%」附近没有任何分数形式的基线")

    # 效果数字形态。⚠ 刻意**不含**裸 `\d+/\d+` —— 那会命中路由标识
    # `[JEV: 3/3 Independent Consensus]` / `2/3 Majority`(它们是协议名,不是效果数字)。
    _NUM = r"\d+pp|×\d[\d.]*|正确率\s*\d+%"
    _SOURCE = r"(?:docs/[A-Za-z0-9._-]+\.md|benchmarks/[\w./-]+\.(?:jsonl|json|py))"

    def _windows(self, width=200):
        """按数字的**所在段落**取上下文,而不是固定 ±width 字。

        判据修正(红队 1eef5957:「±200 字窗口是任意值,实测隔 180 字漏、隔 360 字红」;
        自查时又实测到窗口恰好切在段落中间,导致本段有限定却判红):
        persona 的效果数字与它的出处/限定**同属一个段落**(YAML 块标量里以空行分节),
        所以按段落取是自然且有依据的边界,不是拍脑袋的字数。
        找不到段落边界时(如数字落在分节空行之间)退回 ±width 字。
        """
        spans, acc = [], 0
        for para in self.persona.split("\n\n"):
            spans.append((acc, acc + len(para)))
            acc += len(para) + 2
        for m in re.finditer(self._NUM, self.persona):
            pos = m.start()
            ctx = next((self.persona[a:b] for a, b in spans if a <= pos <= b), None)
            if ctx is None:
                ctx = self.persona[max(0, pos - width): pos + width]
            yield m.group(0), ctx

    def test_T2_no_guarantee_wording(self):
        """效果数字附近不得出现保证类措辞。

        判据修正(红队 1eef5957 变体 10 实证):初版只查
        `(复算|断言)…(保证|必然|一定)` —— 「保真」「确保」「稳定达到 100%」
        这类同义表达全绿。现扩到一组同义词。
        判据修正 2:只查**效果数字附近**(±150 字),技术性保证
        (如「Sort-Object 保证选取确定」)是正确用法,不该误伤。
        """
        guarantee = re.compile(
            r"保证|必然|必定|一定能|确保|保真|稳定达到|一定会|毫无疑问|铁定")
        # 已带完整限定词的段落不算违规 ——「**不是普适保证**」里的「保证」是限定,
        # 不是承诺;「非普适保证」同理。判据必须分清这两者,否则逼着人换词而非改事实。
        qualified = re.compile(r"非普适|不是普适|观测值?|非保证")
        for num, ctx in self._windows(150):
            if qualified.search(ctx):
                continue
            for m in guarantee.finditer(ctx):
                before = ctx[max(0, m.start() - 12):m.start()]
                if re.search(r"(不得|禁止|严禁|不会|不能|并非|不是|非普适)\s*$", before):
                    continue
                self.fail(f"效果数字「{num}」附近出现保证类措辞「{m.group(0)}」: "
                          f"…{ctx.strip()[:70]}…\n  —— 观测值不得写成保证")

    def test_T3_effect_numbers_have_traceable_source(self):
        """**每一处**效果数字都必须就近带出处,不是「全文出现过一次就算过」。

        判据修正(自查 V2 变体实测:删掉 §二① 的出处,3.0b 那个还在 → 全绿)。
        出处可以是 `docs/*.md` 或 `benchmarks/**` 下的数据文件。
        """
        windows = list(self._windows(200))
        self.assertGreater(len(windows), 0, "persona 里找不到效果数字")
        for num, ctx in windows:
            with self.subTest(数字=num):
                self.assertRegex(ctx, self._SOURCE,
                                 f"这处效果数字「{num}」附近没有出处标注 —— "
                                 f"第三方无法核验它何时何地测得")
                for rel in set(re.findall(self._SOURCE, ctx)):
                    with self.subTest(出处=rel):
                        self.assertTrue(
                            os.path.exists(os.path.join(PLUGIN_ROOT, rel)),
                            f"persona 引用了不存在的文件: {rel}")

    def test_T4_numbers_marked_as_observation_not_universal(self):
        """每处效果数字都必须带「观测值/非普适」限定。

        判据修正(自查 V3 变体实测:删掉 §二① 的限定,3.0b 那个还在 → 全绿)。
        """
        qualifier = re.compile(
            r"观测|非普适|不是普适|当前题集|当前[^。\n]{0,6}题集|非保证|取决于")
        for num, ctx in self._windows(200):
            with self.subTest(数字=num):
                self.assertRegex(ctx, qualifier,
                                 "这处数字附近没有「观测值/非普适保证」的限定 —— "
                                 "换个模型/题集它就成了新的「验证剧场」")
    def test_T5_stated_numbers_match_docs(self):
        """persona 写下的数字必须与 docs 里的**真值**一致,不能各说各话。

        真值锚点(取自 docs/FINAL-CONCLUSIONS.md,2026-09-28/30 实测):
          执行断言:24/30 → 30/30,p=0.0312,成本 ×2.0

        判据修正(红队 1eef5957 变体 13 实证:本条原为**空壳** ——
        它只对 docs 文件做 assertIn,**从头到尾没读过 persona**,
        所以把 persona 改成 28/30、p=0.0001、×3.0 这种与真值矛盾的内容也全绿)。
        现在改为**双向**:真值必须在 docs 里,**且 persona 里的同一项不得与之矛盾**。
        """
        final = os.path.join(DOCS, "FINAL-CONCLUSIONS.md")
        self.assertTrue(os.path.exists(final), f"缺少真值锚点文件: {final}")
        with open(final, encoding="utf-8") as f:
            text = f.read()
        for token in ("24/30", "30/30", "0.0312"):
            with self.subTest(真值=token):
                self.assertIn(token, text, f"FINAL-CONCLUSIONS.md 缺真值 {token},无法核对 persona")

        # ---- 关键新增:persona 侧必须与真值**一致**,而不是只查 docs ----
        # 真值源 = docs/ **全部** md(不只 FINAL-CONCLUSIONS —— persona 引的
        # capability-boundary.md 也是出处;初版只查 FINAL-CONCLUSIONS,误报)。
        docs_text = ""
        for name in sorted(os.listdir(DOCS)):
            if name.endswith(".md"):
                with open(os.path.join(DOCS, name), encoding="utf-8") as f:
                    docs_text += f.read() + "\n"
        # persona 里出现的每个「分子/分母」式数字,必须在 docs 真值里找得到
        persona_nums = set(re.findall(r"\b(\d+)\s*/\s*(\d+)\b", self.persona))
        docs_nums = set(re.findall(r"\b(\d+)\s*/\s*(\d+)\b", docs_text))
        for pair in persona_nums:
            with self.subTest(persona数字=f"{pair[0]}/{pair[1]}"):
                self.assertIn(
                    pair, docs_nums,
                    f"persona 里的「{pair[0]}/{pair[1]}」在整个 docs/ 里都找不到 —— "
                    f"persona 可能在自说自话(红队变体 13:改成 28/30 全绿)")
        # p 值同理
        persona_p = set(re.findall(r"p\s*=\s*([\d.]+)", self.persona))
        docs_p = set(re.findall(r"p\s*=\s*([\d.]+)", docs_text))
        for p in persona_p:
            with self.subTest(persona_p值=p):
                self.assertIn(p, docs_p, f"persona 里的 p={p} 在 docs 真值中不存在")


if __name__ == "__main__":
    unittest.main(verbosity=2)
