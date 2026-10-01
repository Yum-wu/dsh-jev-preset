# -*- coding: utf-8 -*-
"""
A3 / A4:判分器 `is_three_path` 的路由归类与 persona 的**定义**相反。

缺陷实锤(2026-10-01 实测,附录 A3/A4):
  A3  persona 定义 `[JEV: 断言不适用]` = 「无法写成可执行断言,**已转 ② 三路或换模型**」
      → 语义上它**确实走了**多路(否则「已转」无从谈起);
      判分器却把它归为**单路**(`_SINGLE_PATH_PREFIXES` 含 '断言不适用')。
  A4  persona 定义 `[JEV: 单路未验证]` = 「仅 1 路可用(补派已达上限),**无独立交叉验证**」
      → 明确的单路降级;判分器却把它归为**三路**(不在单路白名单里)。

后果不是「分类不优雅」,而是 **gate 题直接判错**:
`grading.py:48` 用 `got = is_three_path(route)` 与 `expect_three_path` 比对,
归类反了 ⇒ 期望三路的题被判单路(错),期望单路的题被判三路(也错)。

本测试的判据直接从 **persona 原文**抽取,而不是手抄一张表 ——
手抄的表会和 persona 一起漂移,那就重演了同一个缺陷(附录 A 的病根:两处副本)。
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
BENCH = os.path.join(PLUGIN_ROOT, "benchmarks", "accuracy")
sys.path.insert(0, BENCH)

from jevbench.extract import is_three_path  # noqa: E402


def persona_route_table():
    """从 cordis.patch.yml 的 persona 输出协议段抽出 `[JEV: X] — 说明` 全表。

    标识与说明都在反引号里,故按「行内两个反引号组」切,不能用「排除反引号」的字符类。
    """
    text = open(os.path.join(PLUGIN_ROOT, "cordis.patch.yml"), encoding="utf-8").read()
    rows = {}
    for line in text.splitlines():
        m = re.match(r"\s*-\s*`\[JEV:\s*([^\]]+)\]`\s*—\s*(.*)", line)
        if m:
            rows[m.group(1).strip()] = m.group(2).strip().strip("`").strip()
    return rows


# persona 里描述「确实走了多路」的措辞。与语义无关的措辞一律不列,避免误判。
_MULTI_WITNESS = re.compile(r"\d/\d|补派|共识|三路|多路")


class TestRouteClassification(unittest.TestCase):

    def setUp(self):
        self.table = persona_route_table()
        self.assertGreater(len(self.table), 8, "从 persona 抽到的路由表过小,解析可能失效")

    def test_A3_disjunction_is_split_into_two_routes(self):
        """A3:persona 原文的 `已转 ② 三路或换模型` 是**析取**,二值判分器无法正确表达。

        红队 af983b62 的反证:两支的物理行为相反 ——
          转三路 = 3 路隔离采样(真多路)
          换模型 = 单路重跑(无隔离采样)
        所以正确修法是**拆 persona 标识**,不是在判分器里二选一。
        """
        # 拆过之后,旧标识必须已消失 —— 留着它判分器就只能猜。
        self.assertNotIn("断言不适用", self.table,
            "persona 里仍有未拆的析取标识 `断言不适用`,二值判分器无法表达它")
        for route, want in (("断言不适用-转三路", True), ("断言不适用-换模型", False)):
            with self.subTest(路由=route):
                self.assertIn(route, self.table, f"persona 里找不到拆分后的 `{route}`")
                self.assertEqual(is_three_path(route), want,
                    f"`{route}` 归类错误:persona: {self.table[route]}")

    def test_A4_single_path_unverified_is_single(self):
        """A4:`单路未验证` 明确是单路降级,应判为单路。"""
        desc = self.table.get("单路未验证")
        self.assertIsNotNone(desc, "persona 里找不到 `单路未验证` 标识")
        self.assertIn("无独立交叉验证", desc, f"persona 定义变了,判据需重估: {desc}")
        self.assertIn("1 路", desc, f"persona 定义变了,判据需重估: {desc}")
        self.assertFalse(is_three_path("单路未验证"),
            "A4:persona 说 `单路未验证` 是单路降级,判分器却归为三路")

    def test_serial_degrade_is_still_multi_path(self):
        """`串行降级-单路由` 的名字里有「单路由」,但 persona 明说「三路被迫串行」——
        退化的是**并发度**,不是路数。名字骗人,定义不骗人。"""
        desc = self.table.get("串行降级-单路由")
        self.assertIsNotNone(desc, "persona 里找不到 `串行降级-单路由` 标识")
        self.assertIn("三路", desc, f"persona 定义变了,判据需重估: {desc}")
        self.assertTrue(is_three_path("串行降级-单路由"),
            "`串行降级-单路由` 是三路并发退化,不是单路路径")

    def test_T7_route_marker_format_tolerance(self):
        """红队 af983b62 标「严重」:模型可能写全角冒号/方括号或小写,
        原正则只认半角 `[JEV: X]`,这些变体一律抽成 None,
        而 None 默认按**单路**算 = 虚报交叉验证 —— 比漏报更危险。"""
        from jevbench.extract import extract_route

        cases = [
            ("[JEV: 断言通过]", "断言通过"),
            ("[jev: 断言通过]", "断言通过"),
            ("[JEV：断言通过]", "断言通过"),
            ("【JEV: 断言通过】", "断言通过"),
            ("[jev：断言通过]", "断言通过"),
        ]
        for text, want in cases:
            with self.subTest(写法=text):
                self.assertEqual(extract_route(text), want,
                    f"{text!r} 未被识别 —— 会被记成「无标识」并默认按单路算,虚报交叉验证")

    def test_T8_no_disjunction_marker_left(self):
        """防守:析取型措辞(「或」连接两种不同物理行为)不得回到单条标识里。

        这条测的是**人会不会再犯**,不是代码状态 —— 判据从 persona 说明文字里找
        「或」字且同时含单路与多路线索的情况。
        """
        for route, desc in sorted(self.table.items()):
            with self.subTest(路由=route):
                has_or = ("或" in desc) or (" or " in desc.lower())
                mentions_multi = bool(_MULTI_WITNESS.search(desc))
                self.assertFalse(
                    has_or and mentions_multi and "换模型" in desc and "三路" in desc,
                    f"`{route}` 的说明同时承诺「三路」与「换模型」,又是析取: {desc}")

    def test_persona_and_judge_agree_on_every_route(self):
        """总闸:persona 声明的**每一条**路由,判分器的归类都必须与 persona 措辞一致。

        这条比逐条断言强 —— persona 以后新增标识而忘了改判分器时,它会先报红。

        跳过的标识:persona 一句话里**既没写「路」也没写任何可判语义**(如「分歧经裁决重排」)。
        判据从措辞推不出归类,强行推断只会让本测试变成随机红绿。
        这类标识单列一条测试(A5),提示 persona 补上语义说明。
        """
        ambiguous = []

        def expect_multi(desc):
            # 显式单路措辞优先。「三路被迫串行」含「三路」但仍是三路;
            # 「无独立交叉验证」含「验证」却不代表多路。
            if ("无独立交叉验证" in desc or "单路直出" in desc
                    or "单路作答" in desc or "单次直出" in desc
                    or "无隔离采样" in desc):
                return False
            if "单路" in desc and "三路" not in desc:
                return False
            if not _MULTI_WITNESS.search(desc):
                return None  # 措辞推不出归类
            return True

        for route, desc in sorted(self.table.items()):
            want = expect_multi(desc)
            if want is None:
                ambiguous.append((route, desc))
                continue
            with self.subTest(路由=route):
                self.assertEqual(
                    is_three_path(route), want,
                    f"路由 {route!r}: 判分器归类与 persona 定义不符\n  persona: {desc}")

        # 这几条确实推不出 —— 登记为 A5(persona 缺可度量的语义说明),不是本轮的修复对象。
        self.assertEqual(
            {r for r, _ in ambiguous},
            {"Rerank Pick #N - <角色> Verified", "Triggered by Test Failure"},
            f"措辞歧义的路由集合变了,需重新评估判据: {ambiguous}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
