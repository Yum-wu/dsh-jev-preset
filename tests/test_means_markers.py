# -*- coding: utf-8 -*-
"""
A5:persona 手段优先级表里的主力手段,**没有对应的状态路由标识** —— 不可度量、不可审计。

背景(附录 A5,严重度中):
本仓 README「实测数据」表按效果排序,前 3 名手段是
  1. 题干结构化      +89pp(5/5 模型达 100%)
  2. 执行断言        +66pp(24/30 → 30/30,McNemar p=0.0312)
  3. 换异构模型      +89pp(部分模型)
而 persona 的输出协议只给了其中一条标识(执行断言 → `断言通过`),
`题干结构化` 与 `换异构模型` 作为**独立手段**没有任何标识。

后果不是「文档不全」,而是**这三种手段在数据上不可区分**:
benchmark 只能从 route 推断「走没走断言」,永远无法统计
「本轮到底是靠题干结构化过的,还是靠换模型过的」。
手段级的效果归因(README 那张表)因此**无法被 judge 复核**,只能靠人记。

判据(预注册,R9):
  T1 persona 的输出协议里,每个「可独立使用的主力手段」都有标识
  T2 每个标识的说明里含足以判定其归类的语义线索(不可只写「已使用 X」)
  T3 新增标识后,判分器与总闸不会把它静默归错类(沿用 tests/test_route_classification.py)
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "benchmarks", "accuracy"))

from jevbench.extract import is_three_path  # noqa: E402

# 主力手段 → 该手段在 persona 里应当存在的状态标识。
# 注意「执行断言」的标识叫 `断言通过`(不含「执行」二字),所以这里按语义指定,
# 不做字面包含匹配 —— 否则会重演 A3/A4 那种「措辞与标识对不上」的病。
REQUIRED_MEANS = {
    "题干结构化": ["题干结构化"],
    "换异构模型": ["异构模型", "换模型"],
    "执行断言": ["断言通过"],
}

# persona 优先级链的「类目词」→ 该类目**必须存在**的标识候选集。
# 登记在这里而不是内联豁免,是为了让「类目能不能落地」成为可判定的,
# 而不是一个恒真的白名单(红队 3c23c7ba 指出的漏洞)。
PRIORITY_ITEM_TO_MARKER = {
    "多路": ("断言不适用-转三路", "3/3 Independent Consensus",
             "2/3 Majority Consensus", "2/3 + 补派", "串行降级-单路由",
             "串行降级-限流路由", "Triggered by Test Failure"),
    "换模型": ("断言不适用-换模型",),
    "题干结构化": ("题干结构化后重算",),
    "断言通过": ("断言通过",),
    "Fast-Pass": ("Fast-Pass",),
}


def persona_route_table():
    text = open(os.path.join(PLUGIN_ROOT, "cordis.patch.yml"), encoding="utf-8").read()
    rows = {}
    for line in text.splitlines():
        m = re.match(r"\s*-\s*`\[JEV:\s*([^\]]+)\]`\s*—\s*(.*)", line)
        if m:
            rows[m.group(1).strip()] = m.group(2).strip().strip("`").strip()
    return rows


class TestMeansHaveRouteMarkers(unittest.TestCase):

    def setUp(self):
        self.table = persona_route_table()
        self.assertGreater(len(self.table), 8, "从 persona 抽到的路由表过小,解析可能失效")

    def test_T1_every_primary_means_has_a_marker(self):
        for means, candidates in REQUIRED_MEANS.items():
            with self.subTest(手段=means):
                found = [r for r in self.table if any(c in r for c in candidates)]
                self.assertTrue(
                    found,
                    f"手段「{means}」在 persona 输出协议里没有任何状态标识 —— "
                    f"它在 benchmark 数据上不可区分,README 的手段级效果归因无法被 judge 复核")

    def test_T2_markers_state_their_class(self):
        """标识的说明必须含**足以判定单路/多路归类**的语义线索。

        只写「已使用题干结构化」不行 —— 判分器读不出它是单路还是多路,
        这正是 A3 析取标识出问题的同一类病灶(语义不足以支撑机器判定)。

        判据修正(红队 3c23c7ba 变体 7 实证):初版是纯词面命中,
        写成「这不是单路也不是多路」照样绿 —— 而那句话实际把归类**说没了**。
        现在要求出现**肯定式**单路措辞,并显式排除否定窗口。
        """
        # 肯定式单路线索。刻意不用裸「单路」:它能出现在「不是单路」这类否定句里。
        positive_single = re.compile(
            r"单路(?:重算|作答|直出|算出|路径|降级|未验证)"
            r"|无隔离采样|无独立交叉验证|单次直出")
        # 多路线索同理要求肯定式。
        positive_multi = re.compile(
            r"多路|(?:^|[^不非])三路|隔离采样")
        # 否定窗口:「不是单路」「并非三路」「既不…也不…」
        negation = re.compile(r"(?:不是|并非|既不|也不是|非)[^。;、]{0,8}")

        def stripped(desc, pattern):
            """在否定窗口之外找肯定式命中。"""
            masked = negation.sub(lambda m: "\x00" * len(m.group(0)), desc)
            return pattern.search(masked)

        for means, candidates in REQUIRED_MEANS.items():
            for route in [r for r in self.table if any(c in r for c in candidates)]:
                with self.subTest(手段=means, 标识=route):
                    desc = self.table[route]
                    self.assertTrue(
                        stripped(desc, positive_single) or stripped(desc, positive_multi),
                        f"标识 `{route}` 的说明「{desc}」不含**肯定式**的单路/多路语义 —— "
                        f"判分器无法据此归类(或该句是否定式,恰好把归类说没了)")

    def test_T4_every_test_file_is_wired_into_npm_test(self):
        """Round 6 发现的假绿灯:`npm test` 漏接 test_route_classification /
        test_means_markers,导致 A3/A4/A5 的回归在默认测试命令下**根本没跑**,
        而 G1 仍然全绿 —— 绿灯是假的。

        判据修正(红队 3c23c7ba 变体 4a 实证):初版查的是**所有 script 的并集**,
        于是「只从 `test` 主脚本删掉、仍留在 `test:means`」能全绿通过 ——
        而那正是本测试要防的场景。现在只查 `scripts["test"]` 本身。
        """
        import json
        pkg = json.load(open(os.path.join(PLUGIN_ROOT, "package.json"), encoding="utf-8"))
        npm_test = pkg["scripts"]["test"]
        missing, known_red = [], {}
        for name in sorted(os.listdir(HERE)):
            if not name.startswith("test_") or not name.endswith(".py"):
                continue
            if name == os.path.basename(__file__):
                continue
            if f"tests/{name}" in npm_test:
                continue
            # 「有意不挂」的唯一合法形式:文件里显式声明 EXPECTED_RED 及原因。
            # ⚠ 这不是开后门 —— 它把「这条测试故意红、故意不跑」从疏漏变成**登记在案的事实**,
            #   且原因必须写出来。Round 27 的 test_inverse_liq_formula.py 属此类:
            #   公式已被实测证伪(入场价变 20 倍结果不变),但正确公式需业务拍板,
            #   修好之前它必须保持红。偷偷不挂 = 假绿灯;显式登记 = 可审查的欠账。
            src = open(os.path.join(HERE, name), encoding="utf-8").read()
            if "EXPECTED_RED" in src:
                reason = [l.strip() for l in src.splitlines()
                          if l.strip().startswith("EXPECTED_RED")]
                known_red[name] = reason[0] if reason else "(未写原因)"
                continue
            missing.append(name)
        # 本文件自身也必须在 `test` 主脚本里(上面的循环排除了自己,这里单独查)。
        self.assertIn("tests/test_means_markers.py", npm_test,
            "本文件未挂进 `npm test` 主脚本 —— 新增测试默认不跑,回归静默失效")
        self.assertEqual(missing, [],
            f"这些测试文件没挂进 `npm test` 主脚本,且未声明 EXPECTED_RED(假绿灯): {missing}")
        # 已登记的「有意红」不得超过 2 个 —— 欠账可以欠,但不能无限欠。
        self.assertLessEqual(len(known_red), 2,
            f"已登记的「有意红」测试有 {len(known_red)} 个,已超过上限 2:{known_red}")
        for name, reason in known_red.items():
            self.assertNotEqual(reason, "(未写原因)",
                f"{name} 声明了 EXPECTED_RED 但没写原因")

    def test_T5_priority_order_is_declared_and_machine_readable(self):
        """自查发现(2026-10-01):多手段可同时使用但标识只能输出一个,
        而原文只写「取值只能是下列之一」= 单选,没给优先级 ——
        agent 只能随意挑,而挑低的虚报强度、挑高的虚报验证。这是新的不可判定点。

        判据修正(红队 3c23c7ba 指出的漏洞):
          初版写成 `item in self.table or item in (豁免清单)`,
          而优先级链的 5 项恰好**全部命中豁免清单** → 后半段永真,任何伪造链都绿。
          现改为:每个类目词必须**至少映射到一个 persona 里的真实标识**,
          映射关系由 `PRIORITY_ITEM_TO_MARKER` 显式登记,查不到就红。
        """
        text = open(os.path.join(PLUGIN_ROOT, "cordis.patch.yml"), encoding="utf-8").read()
        m = re.search(r"多路\s*>\s*([^\n]+)", text)
        self.assertIsNotNone(m, "persona 未声明多手段并存时的标识优先级")
        chain = [p.strip().strip("`* ") for p in m.group(1).split(">")]
        self.assertGreaterEqual(len(chain), 4, f"优先级链过短,覆盖不了主力手段: {chain}")

        # 豁免清单从「判定条件」降级为「候选集合」,且要求其中**至少一个**
        # 真的出现在 persona 标识表里 —— 这才是有判别力的断言。
        for item in chain:
            with self.subTest(优先级项=item):
                candidates = PRIORITY_ITEM_TO_MARKER.get(item)
                self.assertIsNotNone(
                    candidates,
                    f"优先级链里的「{item}」没有登记对应标识,无法校验(测试自身缺口)")
                present = [c for c in candidates if c in self.table]
                self.assertTrue(
                    present,
                    f"优先级项「{item}」声称对应 {candidates},但 persona 输出协议里一个都没有")

        # 链上不得出现未登记项 —— 防止「往链里塞一个不存在的东西」蒙混过关。
        unknown = [i for i in chain if i not in PRIORITY_ITEM_TO_MARKER]
        self.assertEqual(unknown, [], f"优先级链含未登记项: {unknown}")

    def test_T3_new_markers_classify_safely(self):
        """新增的手段标识不得被静默归错类:每条标识要么在单路白名单,
        要么说明里写明是多路。白名单法下「未列出的单路措辞」会被判成多路。"""
        single_words = ("单路", "无隔离采样", "无独立交叉验证", "单次直出", "直出")
        for route, desc in sorted(self.table.items()):
            if route in ("断言不适用-转三路",):  # 已显式定为多路
                continue
            with self.subTest(标识=route):
                looks_single = any(w in desc for w in single_words)
                if looks_single:
                    self.assertFalse(
                        is_three_path(route),
                        f"标识 `{route}` 说明含单路措辞,却被判为多路(虚报交叉验证)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
