# -*- coding: utf-8 -*-
r"""
附录 B2:persona 把 PS 面与 Python 面**并列推荐**,但两者能力不对等。

## 缺口(2026-10-01 实测)

- Python 面:`packages/assertions/python/jev_assertions/` —— **18 个**断言,统一入口 `cli.py`
- PS 面:`packages/assertions/pwsh/JevAssertions.psm1` —— **只有 3 个**函数

原 persona 只说「或 PowerShell `Assert-Jev*`」,并列出 PS 的两值退出码问题,
**但没说覆盖面只有 3/18**。agent 读到这句会合理地推断「两套等价,挑顺手的用」——
而实际上 15 类判定在 PS 上**根本不存在**。

Round 29 已修好同名的 3 个函数的算法分歧(见 `docs/self-optimize-rounds.md` Round 29),
但**能力不对等本身没在 persona 里声明**。本测试把「声明与实际一致」变成可回归项。

## 判据(预注册,R9)

  D1 实际数量必须与 persona 里的声明**一致**:
     PS 导出函数数 = persona 写的数字;Python `--list` 项数 = persona 写的数字。
     任一改动未同步 persona → 本测试红。
  D2 persona 必须**明确**写出「不对等」且给出选择指引,
     而不是只列退出码差异 —— 只列差异会让人以为能力等同。
  D3 这类「persona 声明 vs 代码实际」的检查应覆盖不止 PS 一处
     (当前仓已另有多处同类检查,见 test_no_unsupported_claims.py)。
"""
import json
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PSM1 = os.path.join(ROOT, "packages", "assertions", "pwsh", "JevAssertions.psm1")
CLI = os.path.join(ROOT, "packages", "assertions", "python", "jev_assertions", "cli.py")
PATCH = os.path.join(ROOT, "cordis.patch.yml")

EXPECTED_PS = 3
EXPECTED_PY = 18


def ps_exports():
    src = open(PSM1, encoding="utf-8").read()
    m = re.search(r"Export-ModuleMember\s+-Function\s+(.+)", src)
    if not m:
        raise AssertionError("psm1 里找不到 Export-ModuleMember 语句")
    return [f.strip() for f in m.group(1).split(",") if f.strip()]


def py_list_count():
    r = subprocess.run([sys.executable, "-B", CLI, "--list"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return len(json.loads(r.stdout)["assertions"])


class TestPsPythonParityClaim(unittest.TestCase):

    def test_D1_counts_match_the_persona_claim(self):
        ps, py = len(ps_exports()), py_list_count()
        self.assertEqual(ps, EXPECTED_PS,
                         f"PS 导出函数数变成 {ps} 了,persona 里的 {EXPECTED_PS} 必须同步更新")
        self.assertEqual(py, EXPECTED_PY,
                         f"Python 断言数变成 {py} 了,persona 里的 {EXPECTED_PY} 必须同步更新")

    def test_D1b_persona_numbers_match_reality(self):
        """★ Round 33 自查发现:初版 D1 只比「实际数量 vs 测试常量」,
        **根本没校验 persona 里写的数字**。变异把 persona 的「18 个」改成「99 个」后
        测试**照样全绿** —— 即「声明与实际一致」这条判据本身是空的。

        本项改为:**从 persona 文本里把数字抠出来**,与实际数量比对。
        抠不到也算失败(说明 persona 的写法变了,需同步本测试)。
        """
        text = open(PATCH, encoding="utf-8").read()
        ps, py = len(ps_exports()), py_list_count()

        # persona 里的写法:「Python 面 **18 个**断言」「PS 面**只有 3 个**」
        m_py = re.search(r"Python\s*面\s*\*\*(\d+)\s*个\*\*", text)
        self.assertIsNotNone(m_py, f"persona 里抠不到 Python 面的断言数 —— 写法变了,需同步本测试")
        m_ps = re.search(r"PS\s*面\*\*只有\s*(\d+)\s*个\*\*", text)
        self.assertIsNotNone(m_ps, f"persona 里抠不到 PS 面的断言数 —— 写法变了,需同步本测试")

        self.assertEqual(int(m_py.group(1)), py,
                         f"persona 说 Python 面 {m_py.group(1)} 个,实际 {py} 个 —— 声明已失实")
        self.assertEqual(int(m_ps.group(1)), ps,
                         f"persona 说 PS 面 {m_ps.group(1)} 个,实际 {ps} 个 —— 声明已失实")

    def test_D1c_persona_names_the_real_functions(self):
        """★ 红队 2a1f0ee 实测(MUT12):把 persona 里的函数名换成
        `Assert-JevFoo / Assert-JevBar / Assert-JevBaz`(仓库 0 命中),
        **测试照样 exit=0 全绿** —— 因为 D1b 只比**数量**不比**身份**。

        这与我 Round 33 自查发现的 D1 缺陷**同源,但只升了一半**:
        初版只比「实际 vs 测试常量」完全不读 persona;改成 D1b 后读了**数字**,
        仍然不读**名字**。数量对了身份全错,同样是不一致。

        本项把 persona 里点名的函数名集合与 `Export-ModuleMember` 实际导出集合比对。
        """
        text = open(PATCH, encoding="utf-8").read()
        named = set(re.findall(r"Assert-Jev[A-Za-z]+", text))
        named.discard("Assert-Jev*")          # 通配写法不是函数名
        actual = set(ps_exports())
        self.assertTrue(named, "persona 里抠不到任何 PS 函数名 —— 写法变了,需同步本测试")
        self.assertEqual(
            named, actual,
            f"persona 点名的 PS 函数与实际导出不一致。\n"
            f"  persona 提到: {sorted(named)}\n"
            f"  实际导出   : {sorted(actual)}\n"
            f"  persona 提到了仓库里不存在的函数 —— 读 persona 的 agent 会去调用一个不存在的东西")

    def test_D2_persona_states_the_asymmetry_and_how_to_choose(self):
        text = open(PATCH, encoding="utf-8").read()
        # ⚠ Round 34 修红队 2a1f0ee 的三条:
        #  ① 删掉「不对等/不等同/覆盖面」全部三个词后测试仍绿 ——
        #     因为兜底词 `覆盖面` 会**独立命中**(persona 里别处也出现这三个字)。
        #     故改为:限定词必须与「PS」出现在**同一段**内,且不再用过宽的兜底词。
        #  ② `assertIn("Assert-Jev*")` 反而**钉死了**那句并列推荐 ——
        #     它要求保留「或 PowerShell Assert-Jev*」,而那句正是缺陷本身。
        #     改为:persona 里**任何提到 PS 断言入口的地方**,同段落必须有不对等限定。
        #  ③ 三处可执行指引被掏成「请自行核对」后仍绿(MUT11)——
        #     「优先走」必须在,且必须带明确对象(Python CLI)。
        m = re.search(r"Python\s*面\s*\*\*\d+\s*个\*\*", text)
        self.assertIsNotNone(m, "persona 里找不到 PS/Python 对比段 —— 结构变了,需同步本测试")
        start = m.start()
        seg = text[max(0, start - 800): start + 800]
        self.assertRegex(
            seg, r"(不对等|不等同|能力.{0,6}(不同|不等))",
            "PS/Python 对比段内必须**明确**写出不对等;"
            "只列退出码差异会让人误以为覆盖面等同(附录 B2 的原始缺口)。"
            "注:不能用「覆盖面」这类过宽兜底词 —— 它在别处也会出现,掩盖语义删除")
        self.assertRegex(
            seg, r"(优先走|一律优先|优先使用)[^。]{0,40}Python",
            "必须给出**带对象**的选择指引:能用 Python CLI 时优先用它。"
            "只写「优先」而无对象,或写成「请自行核对」,都不算数(红队 MUT11)")
        # ⚠ Round 34 第二轮迭代:上面那条**只检查了「有优先走 + 有 Python」**,
        #   于是把指引掏空成「优先走 Python CLI;具体取舍请自行核对」照样通过(红队 MUT11)。
        #   即「认词不认义」—— 出现了正确的词,但句子已不构成可执行指令。
        #   故补:该段不得含推卸话,且必须含明确的否定/条件约束。
        self.assertNotRegex(
            seg, r"(自行核对|自行判断|请酌情|自行把握)",
            "PS/Python 对比段里出现「自行核对」这类**推卸话** —— "
            "等于把该由 persona 说清的能力边界又推回给 agent 自己猜,"
            "正是附录 B2 要消灭的误导(红队 MUT11 实测:这样写四项测试仍全绿)")
        self.assertRegex(
            seg, r"(不存在|绝不可|仅在|只在)",
            "PS/Python 对比段必须含**明确的否定或条件约束**(如「15 类判定在 PS 上不存在」"
            "/「PS 面仅在…时用」),而不是只陈述差异让人自行取舍")

    def test_D4_readme_makes_the_same_claim(self):
        """★ 红队 2a1f0ee 实测:persona 改了但 **README.md / README_EN.md 完全没同步**,
        (历史:该事故发生在双语化重构前;2026-10-07 起英文文档为 README.md、
         中文为 README.zh-CN.md,README_EN.md 已不存在 —— 断言清单见下方 for 循环)
        人读 README 拿到的仍是「两套并列等价」的旧认知 —— 而那正是附录 B2 要消灭的误导。

        加本项是因为:Round 33 只改了 persona(persona 是给 agent 看的),
        **README 是给人看的**,两者都是对外承诺;只改前者等于只对机器说真话。
        """
        py, ps = py_list_count(), len(ps_exports())
        for name in ("README.md", "README.zh-CN.md"):
            with self.subTest(文档=name):
                path = os.path.join(ROOT, name)
                text = open(path, encoding="utf-8").read()
                # 必须同时出现两个数字,且明确写出「不对等」
                self.assertIn(str(py), text, f"{name} 里找不到 Python 侧的断言数 {py}")
                self.assertIn(str(ps), text, f"{name} 里找不到 PS 侧的函数数 {ps}")
                self.assertRegex(
                    text, r"(不对等|不等效|NOT equivalent|NOT the same)",
                    f"{name} 必须**明确**写出 PS 面与 Python 面能力不对等 —— "
                    f"只列两处路径而不点破差异,读者仍会以为覆盖面等同")

    def test_D5_readme_defenses_section_is_not_stale(self):
        """★ README 的「已落实的防线(和没有的)」两栏曾经落后 20 轮。

        Round 1–38 建了护栏补测 / 退出码契约 / CLI 可达性 / 输入域 / 跨实现一致 /
        变异基础设施 / G5 链 / 双 PS 版本入 CI 等 9 条,那一栏**一条都没写**。
        失真的原因不是忘了写,是**没有任何测试会去看它**。

        本项要求:两栏必须存在,且「没有的」一栏必须**明确列出几条当前已知的未修缺陷** ——
        否则「没有的」会退化成一句客套话,读者默认「该有的都有」。
        """
        import json as _json
        py, ps = py_list_count(), len(ps_exports())
        # ⚠ Round 40 连续三次自查才把这个判据修对,逐条记:
        #   ① 用 text.lower() 却拿大写「Absent」去比 —— 永远匹配不上;
        #   ② 用 name.endswith(".md") 区分中英文 —— `README_EN.md` 也以 .md 结尾,
        #      于是拿中文关键词去搜英文文档;
        #   ③ 用「没有的」定位栏目边界 —— 但「没有的」出现在**标题**「已落实的防线(和没有的)」里,
        #      find() 命中的是标题,导致 present_section 把全部条目都排除了。
        #      改用**只在 absent 栏正文出现**的标志:「别当成有」/「do not assume otherwise」。
        for name, absent_marker, keywords in (
            # ⚠ 2026-10-07 README 双语化重构:README.md 改为英文默认,中文移到 README.zh-CN.md,
            #   旧的 README_EN.md 被删除。这里的映射必须跟着走 —— 否则拿中文关键词去搜英文文档。
            ("README.zh-CN.md", "别当成有", ("护栏", "变异", "规避")),
            ("README.md", "do not assume otherwise", ("guardrail", "mutation", "evasion")),
        ):
            with self.subTest(文档=name):
                path = os.path.join(ROOT, name)
                text = open(path, encoding="utf-8").read()
                low = text.lower()
                m_absent = low.find(absent_marker)
                self.assertGreater(m_absent, 0,
                                   f"{name} 找不到「{absent_marker}」—— 「没有的」一栏可能被删了,"
                                   f"读者会默认该有的都有")
                present_section = low[:m_absent]
                for kw in keywords:
                    self.assertIn(kw.lower(), present_section,
                                  f"{name} 的「已落实」栏(而非全文)没有提到「{kw}」相关成果 —— "
                                  f"该栏可能已过期(它曾整整落后 20 轮)")
                n_present = present_section.count("- **")
                n_absent = low[m_absent:].count("- **")
                self.assertGreaterEqual(
                    n_present, 5,
                    f"{name}「已落实」栏只有 {n_present} 条条目 —— 若刚更新过,不该这么少")
                self.assertGreaterEqual(
                    n_absent, 4,
                    f"{name}「没有的」栏只有 {n_absent} 条 —— 它若退化成一句客套话,"
                    f"读者会默认「该有的都有」,而这正是它历史上发生过的退化")
                # 数量声明不能因为这次编辑而丢失(D4 覆盖的同一事实)
                self.assertIn(str(py), text)
                self.assertIn(str(ps), text)

    def test_D3_ps_module_is_actually_covered_by_a_test(self):
        """PS 模块必须有一份被 `npm test` 调用的测试 —— 否则 PS 侧改动无人验证。

        ⚠ Round 38 修红队 2a1f0ee 的一条:初版这里断言
          `assertIn("BOM", <ps1 内容>)` —— **只查「BOM」这个词出现过**。
          把 BOM 自检整段删掉、只留一句提到 BOM 的注释就能通过,判别力为 0。
          现改为:**真的把 ps1 跑起来并断言 exit 0** ——
          「PS 侧真的能跑通」只有真跑才能证明,词出现证明不了。
        """
        import json as _json
        pkg = _json.load(open(os.path.join(ROOT, "package.json"), encoding="utf-8"))
        self.assertIn("test_pwsh_assertions.ps1", pkg["scripts"]["test"],
                      "PS 测试未挂进 `npm test` —— PS 侧改动默认回归看不到"
                      "(Round 30 已挂,若被摘掉说明是有人认为它不需要跑)")

        ps1 = os.path.join(HERE, "test_pwsh_assertions.ps1")
        # ⚠ Round 41 补 PS5.1(红队 91faf08d):C0 那条 BOM 自检的**全部动机**是
        #   「PS5.1 按 ANSI 读中文会乱码,而 PS7 完全正常」,可我原先只跑 `pwsh` ——
        #   即**恰好在唯一能发现该事故的缺席**。红队实测:剥掉 BOM 后
        #   PS7 只红 1 项、PS5.1 红 6 项(乱码让 MustContain 字面量失效,
        #   把真功能 FAIL 伪装成「消息不匹配」)。故两版都必须真跑。
        interpreters = [("pwsh", ["-NoProfile", "-File", ps1])]
        if sys.platform == "win32":
            ps51 = os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                                 "System32", "WindowsPowerShell", "v1.0",
                                 "powershell.exe")
            if os.path.exists(ps51):
                interpreters.append(
                    ("powershell(5.1)",
                     ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1]))
            else:
                self.skipTest("本机找不到 PS5.1 —— C0 的主要防护对象缺席")
        for label, argv in interpreters:
            with self.subTest(解释器=label):
                r = subprocess.run([label.split("(")[0] if "(" in label else label]
                                   + argv[1:], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", cwd=ROOT)
                out = (r.stdout or "") + (r.stderr or "")
                self.assertEqual(r.returncode, 0,
                                 f"{label} 下 PS 测试实跑未通过(exit={r.returncode}):\n{out[-800:]}")
                self.assertIn("BOM", out,
                              f"{label} 输出里应出现 BOM 自检的结果行 —— "
                              f"删掉自检只留字面量也算过")


if __name__ == "__main__":
    unittest.main(verbosity=2)
