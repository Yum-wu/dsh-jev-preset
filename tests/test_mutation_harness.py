# -*- coding: utf-8 -*-
r"""★★ Round 80:变异判定框架**自己的**测试(红队 R79 N7)。

## 为什么需要它
R79 我在 `tools/mutation_harness.py` 的 docstring 里写「并加一个它自己的测试」——
**实际 `tests/` 下没有,全仓也没有任何入口运行 `_selftest()`**。红队判:**doc ≠ 实现**,
与刚修掉的 P2-R78-5(ledger 写错正则)同族。**这条成立,本文件就是补那个洞。**

## 它守什么
1. **`_selftest()` 必须通过** —— 且**有入口跑它**(R79 之前没人跑)。
2. **`EXPECT_TESTS` 必须与真套件对拍**(红队 R79 N3:常量漂移到 24 时框架静默失效)。
3. ★★ **断言计数判据(红队 R79 的设计,本文件实现)** —— 治「**用例被阉**」:
   把 `test_A11e` 体首插一个 `return`,套件照样 `Ran 25 tests OK`,
   `classify` 判「等价变异」⇒ **人类面 pin 的唯一守卫被无声拆掉**。
   修法:`unittest.TestCase.assert*` 打桩按 `test.id()` 计断言数,
   **每个用例至少 1 条断言,且总数不得低于预注册下界**。零断言的用例 ⇒ 红。
   ⚠ 这是**形状判据**,不是覆盖率 —— 但它精确命中「整条用例被短路」这一类。
"""
import ast
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import mutation_harness as MH  # noqa: E402
import pre_registered as PR  # noqa: E402

SUITE = "tests/test_evasion_audit.py"
# ⚠ `SUITE` 是**死变量**(红队 R80 低严重度指出)—— 保留它只为指向被测套件;
#   H4 的 `_COUNTER` 用的是 `unittest.discover` 的 pattern,不读这个常量。
# 预注册下界(只增不减;红队 **R81** 实测原始副本 25 用例 / **406** 条断言 ——
# R80 我写的 404 与两个独立计数器都不符,已按实测修正)。
# ⚠ R80 docstring 写「402」→ 404 → **实测 406**(红队 R81 P2-R81-G)。
# ⚠ **R82 再测为 407**(第 1 路 P2-R82-F 与第 2 路 P3-R82-B 各测一次,连跑 3 次 IDENTICAL)——
#   上面那个 406 是 **R81 旧记**,本行不复算它。**两个数不可复算一致**,详见 `tests/pre_registered.py`。
MIN_ASSERTIONS_PER_TEST = 1
MIN_TOTAL_ASSERTIONS = 400
# ★★★ Round 82 补修(自查):这里原来有个 `PRE_REGISTERED` dict。
#   R82 把常量搬到 `tests/pre_registered.py` 后**忘了删它**,而它**零读取点**
#   (`test_H5` 直接读 `PR.*` 模块属性)—— 红队 R81 报的「死键 `harness_tests`」
#   只是从「值写错」变成「值对但没人读」。
#   ⚠ 同一文件里 `SUITE`(见上)注明了是死变量,这个没有 ⇒ **「删一处 ≠ 删一类」**。已删。

_COUNTER = r'''
import json, sys, unittest
sys.path.insert(0, "tests")
counts = {}
skipped = set()
_orig = unittest.TestCase.run
_orig_skip = unittest.TestCase.skipTest
def _skip(self, reason=None):
    skipped.add(self.id())
    return _orig_skip(self, reason)
def _run(self, result=None):
    n = [0]
    def bump(*a, **k):
        n[0] += 1
    saved = {}
    for name in dir(unittest.TestCase):
        if name.startswith("assert"):
            m = getattr(unittest.TestCase, name)
            if callable(m):
                saved[name] = m
                setattr(unittest.TestCase, name, (lambda f: (lambda self, *a, **k: (bump(), f(self, *a, **k))))(m))
    try:
        return _orig(self, result)
    finally:
        for name, m in saved.items():
            setattr(unittest.TestCase, name, m)
        counts[self.id()] = n[0]
unittest.TestCase.run = _run
unittest.TestCase.skipTest = _skip
loader = unittest.TestLoader()
suite = loader.discover("tests", pattern="__PATTERN__")
res = unittest.TextTestRunner(verbosity=0).run(suite)
for k in skipped:
    counts.pop(k, None)          # ★ 被 skip 的用例不计(它本来就不该跑)
print("COUNTS_JSON=" + json.dumps(counts, ensure_ascii=False))
'''


class TestMutationHarness(unittest.TestCase):
    # ★★★ Round 100(红队 R99 P20-R99-A【高】):`_selftest()` 必须在**子进程**里跑。
    #   根因:本进程死循环时 `subprocess.run(timeout=)` **不在执行路径上** ⇒
    #   红队实测 `_selftest()` 体首 1 行 `while True: pass` 让 `-k H1_selftest` 挂死 >400s。
    #   搬到子进程后,同一构造变成 `TimeoutExpired` ⇒ `timeout=300` 生效。
    #   **顺手**堵掉 P19-R98-B(`_selftest` 体首 `os._exit(0)` ⇒ CI `rc=0`)。
    #   ⚠ 计数必须**跨进程回传**(哨兵行 `JEV_CHECKS=<json>`),不能读本进程的 `MH.SELFTEST_CHECKS_RUN`。
    _SUB_CODE = (
        "import json, sys;"
        "sys.path.insert(0, 'tools');"
        "import mutation_harness as m;"
        "m._selftest();"
        "print('JEV_CHECKS=' + json.dumps(len(m.SELFTEST_CHECKS_RUN)))"
    )

    @staticmethod
    def _ast_check_count():
        """★★★ Round 101(红队 R100 P21-R100-A【高】):**父进程自己算的真值。**

        哨兵行 `JEV_CHECKS=` 是**子进程自报**的 ⇒ 与 `rc` 不是两条独立事实 ⇒
        子进程 `print('JEV_CHECKS=14'); sys.exit(0)` 一行即可同时满足两条断言。
        ⇒ 本方法由**父进程** AST 解析 `tools/mutation_harness.py`,
        数 `_selftest()` 函数体内 `_check(` 的**调用点**数,作为独立真值。

        ⚠ **边界(如实声明)**:它读的是**同一个文件** ⇒ 攻击者改源码减判据时它跟着变。
          真正的第三方锚是 `pre_registered.SELFTEST_CHECKS`(**另一个文件**)。
        """
        src = (ROOT / "tools" / "mutation_harness.py").read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.FunctionDef) and node.name == "_selftest":
                return sum(1 for x in ast.walk(node)
                           if isinstance(x, ast.Call)
                           and (getattr(x.func, "id", None)
                                or getattr(x.func, "attr", None)) == "_check")
        return -1

    def _selftest_in_subprocess(self, timeout=300):
        """在**子进程**里跑 `_selftest()`;返回 `(rc, checks, blob)`。"""
        r = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", self._SUB_CODE],
                           cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        blob = (r.stdout or "") + (r.stderr or "")
        m = re.search(r"^JEV_CHECKS=(\d+)$", blob, re.M)
        return r.returncode, (int(m.group(1)) if m else None), blob

    def test_H1_selftest_passes_and_has_an_entrypoint(self):
        """`_selftest()` 必须通过 —— 且**有入口**跑它(本用例就是那个入口)。

        ★ Round 81:H6 抓出本用例**零 `self.assert*`**(只调了 `_selftest()`)。
        这本身是对的 —— 「没有断言」就是「这条用例什么都没守」。
        修:把返回值也断言掉,让它自己也有判据。
        """
        # ★★★ Round 100:搬到**子进程**(红队 R99 P20-R99-A)——
        #   本进程死循环时 `subprocess.run(timeout=)` 不在执行路径上 ⇒ 永久挂死。
        rc, checks, blob = self._selftest_in_subprocess()
        self.assertEqual(rc, 0, f"_selftest() 子进程非零退出(rc={rc}):\n{blob[-1500:]}")
        self.assertIsNotNone(
            checks, f"子进程没回传 `JEV_CHECKS=` 哨兵行 —— `_selftest()` 可能没跑完:\n{blob[-1500:]}")
        # ★★★ Round 89(红队 P9-R88-F【低】):`_selftest()` 末尾那条计数守卫
        #   (`_require(len(SELFTEST_CHECKS_RUN) == SELFTEST_CHECKS)`)住在**同一个函数体内** ——
        #   在它之前插 1 行 `return` 就能**同时**跳过 ⑨/⑩ 与守卫本身,而 `-k H1` 仍绿。
        #   ⇒ 与 R88 第 1 轮同法,把校验**搬到另一个文件**(本用例):
        #   红队实测的绕过是「`_selftest()` 内一行 `return`」,本用例在**跨文件**处对拍计数。
        self.assertEqual(
            checks, MH.SELFTEST_CHECKS,
            f"`_selftest()` 只登记了 {checks} 条判据,"
            f"期望 {MH.SELFTEST_CHECKS} 条 —— 有判据被 `return`/异常跳过了")
        # ★★★ Round 101(红队 R100 P21-R100-A【高】):**父进程自己算的真值**。
        #   前三条都建立在「子进程回传的 `checks`」上 —— 而那是**自报**:
        #   子进程 `print('JEV_CHECKS=14'); sys.exit(0)` 一行即可同时满足它们。
        #   ⇒ 本条由**父进程** AST 数 `_selftest()` 内 `_check(` 调用点数,与自报值对拍。
        self.assertEqual(
            checks, self._ast_check_count(),
            f"子进程自报 {checks} 条判据,但父进程 AST 只数出 {self._ast_check_count()} 处 "
            f"`_check(` 调用点 —— **自报值与源码不符**(哨兵被伪造)")
        # 跨**文件**第三方锚:真值住在 `tests/pre_registered.py`,不在被测文件里。
        self.assertEqual(
            MH.SELFTEST_CHECKS, PR.SELFTEST_CHECKS,
            f"`MH.SELFTEST_CHECKS={MH.SELFTEST_CHECKS}` 与 "
            f"`PR.SELFTEST_CHECKS={PR.SELFTEST_CHECKS}` 不一致 —— 跨文件锚被改")

    def test_H2_expected_tests_matches_the_real_suite(self):
        """红队 R79 N3:常量漂移会让框架对**一切**变异误报「崩溃」。"""
        real = MH.real_test_count()
        self.assertIsNotNone(real, "取不到真套件的 Ran N")
        self.assertEqual(MH.EXPECT_TESTS, real,
                         f"EXPECT_TESTS={MH.EXPECT_TESTS} 与真套件 {real} 不一致")

    def test_H3_path_guard_survives_python_dash_O(self):
        """红队 R79 N5:护栏原来是 `assert`,`python -O` 下会**消失**。"""
        src = (ROOT / "tools" / "mutation_harness.py").read_text(encoding="utf-8")
        self.assertIn("raise RuntimeError", src,
                      "路径护栏不是显式 raise —— python -O 下会被剥掉")
        i = src.index("def run_case")
        seg = src[i:src.index("def report")]
        self.assertNotIn("assert ", seg,
                         "run_case 里还有裸 assert 护栏(python -O 下失效)")

    def test_H4_every_case_makes_at_least_one_assertion(self):
        """★★ 断言计数判据(红队 R79 的设计):抓「用例被短路」。

        ⚠ **已知边界(红队 R80 P2-R80-2【高】)**:它是**纯计数** ——
        「把一条判据换成 `assertTrue(True)`,同时在别处补一条 `assertTrue(True)`」
        断言总数**反增**、逐用例仍 ≥1 ⇒ **H4 绿**,而那条判据已**恒真失效**。
        **登记未修**;真正的修法是按用例预注册断言数(比总数强)。
        """
        counts = self._count_assertions("test_evasion_audit.py")
        silent = {k: v for k, v in counts.items() if v < MIN_ASSERTIONS_PER_TEST}
        self.assertEqual(silent, {}, f"零断言(被短路)的用例:{silent}")
        total = sum(counts.values())
        self.assertGreaterEqual(
            total, MIN_TOTAL_ASSERTIONS,
            f"断言总数 {total} < 预注册下界 {MIN_TOTAL_ASSERTIONS} —— "
            f"有用例的断言被删空,却仍报 OK")

    def test_H6_harness_test_file_is_itself_covered(self):
        """★★ Round 81(红队 R80 P2-R80-9【中】):H4 **只覆盖被测套件,不覆盖自己**。

        ⚠ **递归护栏(我自己踩的坑)**:不加护栏时,本用例在子进程里跑**本文件**,
        本文件又跑 H6 …… **无限递归**(实测挂死 >10 分钟)。
        故子进程带 `JEV_SELFCOUNT_INNER=1`,内层直接跳过。

        ★★★ Round 82(红队 R81 P2-R81-C【高】):**原来没有「扫到了吗」守卫** ——
        红队三种方式让它静默通过:① 环境带 `JEV_SELFCOUNT_INNER=1`;
        ② 护栏改 `if True:`;③ `_count_assertions` 换一个**不存在的 pattern** ⇒
        `counts={}` ⇒ `silent={}` ⇒ **通过**(单跑 rc=0,0.248s)。
        根因:`silent == {}` 对**空字典**也成立 —— **「没问题」与「没看」同形**。
        ⇒ 加**非空 + 数量下界**守卫:扫到的用例数必须 ≥ 预注册值。
        """
        if os.environ.get("JEV_SELFCOUNT_INNER"):
            self.skipTest("内层:避免 H6 递归调用自己")
        counts = self._count_assertions("test_mutation_harness.py")
        self.assertGreaterEqual(
            # ⚠ 内层跑本文件时 H6 **自己被跳过** ⇒ 少 1。故下界是 N-1。
            #   「护栏改成 `if True:`」这种绕过**由 G1 的 skipped=0 抓** —— 外层被跳过时
            #   整套件会报 `OK (skipped=1)`,G1 判红。(红队 R81 P2-R81-C 的三种绕过,
            #   第②种靠 G1、第①③种靠这里的非空下界。)
            len(counts), PR.HARNESS_TESTS - 2,
            f"只扫到 {len(counts)} 个用例(期望 ≥{PR.HARNESS_TESTS - 2})—— "
            f"「silent 为空」也可能是**根本没扫到**")
        # ★★★ R85(红队 R82 M8 / 附录 C31 ④【高】):**AST 短路判据**。
        #   红队实测:在 H5 的 `JEV_SELFCOUNT_INNER` 护栏**之外**插一个无条件 `return`
        #   ⇒ 内层照样 skip(被 `_COUNTER` 的 `counts.pop` 抹掉)⇒ H4/H6 双双 `rc=0`,
        #   **七条棘轮静默失效而两套件全绿**。R85 Step 2 复现:基线 0/0/0,掏空后 0/0/0。
        #   ⚠ 边界:`os._exit(0)` 之类仍能绕过 —— **第十次「补一格」**,靠大 diff 评审(⚠ **本仓当前无此控制** —— 5 个自守链文件未被 git 跟踪,`git diff` 无输出)补位。
        # ⚠ R85 第 3 轮:实现搬到 `tools/mutation_harness.py`(**单一来源**),
        #   并同时由 `_selftest()` 第 ⑧ 条调用 —— 这里保留为**第二执行点**。
        early = MH._early_exit_methods(
            (ROOT / "tests" / "test_mutation_harness.py").read_text(encoding="utf-8"))
        self.assertEqual(
            early, [],
            f"这些 test 方法体里有 Return/Raise —— 可静默短路而计数判据看不见:{early}")
        silent = {k: v for k, v in counts.items() if v < MIN_ASSERTIONS_PER_TEST}
        self.assertEqual(silent, {}, f"本文件里零断言(被短路)的用例:{silent}")

    def test_H5_pre_registered_numbers_are_ratcheted(self):
        """★★★ Round 81(红队 R80 P2-R80-5【中】 / P2-R80-3【高】):
        `MIN_TOTAL_ASSERTIONS` 与 `EXPECT_TESTS` 都是**自指**的 —— 改小即恒绿。

        ★★★ Round 82(红队 R81 P2-R81-B【高】):R81 我把预注册数放在**本文件**里,
        与棘轮**同文件** ⇒ 红队「把 `PRE_REGISTERED` 一起调低」就绕过了
        (C2:删 2 用例 + 改到 23 + 棘轮同步 → `rc=0 Ran 7 tests OK`)。
        ⇒ 预注册常量**搬到 `tests/pre_registered.py`**,**不同文件**。
        ⚠ 这**不是外部锚**(仍在同仓同作者手里)—— **登记未修**。
        """
        # ★★★ R82:与 H6 同因 —— H5 现在也调 `_count_assertions`,
        #   不加护栏会在子进程里再跑本文件 → H5 → … **无限递归**(实测挂死 >17 分钟)。
        #   故与 H6 共用同一个环境变量护栏。
        if os.environ.get("JEV_SELFCOUNT_INNER"):
            self.skipTest("内层:避免 H5 递归调用自己")
        real = MH.real_test_count()
        # ★★★ Round 92(红队 P12-R91-D【中】):`real_test_count()` 的契约是 `int | None`
        #   (套件没跑绿时返回 `None`)—— 本文件**两个**消费点里,H2(L114)处理了,**H5 没有**:
        #   套件红时 `assertGreaterEqual(None, 25)` 抛 **TypeError**。
        #   按本仓三分判据,`TypeError` 是**崩溃**不是**判据红**,会污染判定
        #   (与 R91 红队登记的「把崩溃副作用记成判据功能」同族)。
        self.assertIsNotNone(real, "取不到真套件的 Ran N")  # ★ R92 第 2 轮(红队 P13-R92-D【低】):与 H2 同文案
        self.assertGreaterEqual(real, PR.SUITE_TESTS,
                                f"套件用例数 {real} < 预注册 {PR.SUITE_TESTS}")
        self.assertGreaterEqual(MH.EXPECT_TESTS, PR.SUITE_TESTS,
                                "EXPECT_TESTS 被下调 —— 自洽对拍抓不住这个")
        self.assertGreaterEqual(MIN_TOTAL_ASSERTIONS, PR.TOTAL_ASSERTIONS_FLOOR,
                                "MIN_TOTAL_ASSERTIONS 被下调 —— H4 会恒绿")
        self.assertGreaterEqual(MH.MIN_SUITE_TESTS, PR.SUITE_TESTS,
                                "MIN_SUITE_TESTS 被下调 —— 下界判据失效")
        # ★★★ R82(红队 R81 P2-R81-A):自检条数棘轮 —— 删判据必须红。
        # ★★★ Round 89 第 2 轮(红队 P10-R89-D【低】):原来这里是 `assertGreaterEqual`
        #   (单向棘轮),**只下调 `PR.SELFTEST_CHECKS` 零反应**(红队 8b 实测 rc=0)。
        #   而「删一条判据 + 两处常量各降 1」正是 P10-R89-A 那条绕过的**前置步骤**。
        #   ⇒ 改**等式**,两侧必须同步。
        self.assertEqual(MH.SELFTEST_CHECKS, PR.SELFTEST_CHECKS,
                                "SELFTEST_CHECKS 被下调 —— 条数守卫失效")
        # ⚠ 计数表是**模块级**的,`_selftest()` 每次调用先清零。
        #   这里只断言「清零后正好等于条数」这一不变量。
        MH._selftest()
        self.assertEqual(len(MH.SELFTEST_CHECKS_RUN), MH.SELFTEST_CHECKS,
                         "自检跑完的条数 != SELFTEST_CHECKS —— 有判据被删")
        # ★ R82(红队 R81 P2-R81-E):原来用**整份 package.json** 的 `count("python tests/")`
        #   = **60**(余量 26,棘轮形同虚设)。改成只数 `scripts.test` 那一条。
        pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        n = pkg["scripts"]["test"].count("python tests/")
        self.assertGreaterEqual(n, PR.SUITE_FILES,
                                f"npm test 里的套件数 {n} < 预注册 {PR.SUITE_FILES}")
        # ★ R82(红队 R81 P2-R81-D):`HARNESS_TESTS` 原来是**死键**且值错(5,实际 7)。
        #   现在真读:本文件用例数必须 ≥ 预注册值。
        counts = self._count_assertions("test_mutation_harness.py")
        self.assertGreaterEqual(len(counts), PR.HARNESS_TESTS - 2,
                                f"框架测试用例数 {len(counts)} < 预注册 {PR.HARNESS_TESTS - 2}")

    def test_H7_selftest_survives_python_dash_O(self):
        """★★★ Round 81(红队 R80 P2-R80-1【高】):`_selftest()` 原来 **5 条判据全是裸 `assert`**,
        `python -O` 下全消失,**还主动打印「[ok] … matches the real suite」这句假话**。
        这里用 `-O` **实跑**一次,确认它仍会红。
        """
        r = subprocess.run([sys.executable, "-O", "-X", "utf8", "-B", "-c",
                            "import sys; sys.path.insert(0,'tools');"
                            "import mutation_harness as m; m.EXPECT_TESTS=24; m._selftest()"],
                           cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300)
        self.assertNotEqual(r.returncode, 0,
                            "`python -O` 下 `_selftest()` 静默通过了 —— 判据被 -O 剥掉了")
        blob = (r.stdout or "") + (r.stderr or "")
        self.assertNotIn("[ok] selftest", blob,
                         "自检失败却仍打印了「[ok]」—— 那是主动说假话")


    def test_H8_gutted_selftest_checks_are_detected(self):
        """红队 R82 P2-R82-A【高】:纯计数守卫防「删」不防「阉」。

        R84 Step 2 实测:把 `_selftest()` 里第 ① 条 `_check` 的条件换成 `True`,
        `python tools/mutation_harness.py` **`rc=0`**,且打印与基线**逐字相同**的
        `[ok] selftest: ... matches the real suite` —— **假话**。

        ★★ R84 第 2 轮(红队 P5-R84-A/B/C 实测)把本用例从
        「**1 条锚 × 1 档**」扩到「**`SELFTEST_CHECKS - 1` 条锚 × 3 档**」(现为 13 锚):
        ⚠ **R104 更正**(红队 R103 P24-R103-E):原写「6 条锚」是 R84 旧数,实测 **13** 条。
        * 旧版只钉 `_check(naive == DETECTED,` 一条 ⇒ ②–⑥ 的阉变异
          **harness 与 H8 双双 `rc=0`**(10/10 组),而 ① 被拦纯属**锚点副作用**;
        * 旧版只测 `True` 一档 ⇒ 漏掉 `True == True` / `len([]) == 0` 两类恒真式;
        * 旧版是**单点**断言 ⇒ 红队把它换成 `pass` 即静默(P5-R84-B),
          现在要 `pass` 掉 `len(anchors) * 3` 处才可能绕过
          ★ R103:此处原写「18 处」(R84「6 锚 × 3 档」的旧数,红队 R99 P20-R99-D 报 doc≠实现);
          `anchors` 已扩到 **13** 条 ⇒ 实际 **39** 处。

        ⚠⚠ **R104 自我更正(红队 R103 P24-R103-C 三条实测)**:R103 在此写
        「**改为动态表述,结构上不会再腐烂**」—— **那句话本身是错的**。
        docstring 是 `Expr(Constant(str))`、**不是 f-string**(**不求值**);
        全仓 grep `__doc__` = **0 命中**;把这里的数字改成 99 后 `-k H8` 仍 **`rc=0` / `OK`**
        ⇒ **腐烂零反应**。
        ⇒ **如实声明**:本 docstring 里的数字**会腐烂**,本仓**无判据守卫它**。
        真正的真值源是 `MH.SELFTEST_CHECKS` 与 `len(anchors)`,**改代码后必须手工同步此处**。
        (该形态已登记进 `docs/structural-boundaries.md` §一。)
        ★ **R106 更正**(红队 R105 P26-R105-F):原写 **§三**;
        R105 已把该形态(B7)从 §三 **移到 §一**(判据类),此处未同步。

        ⚠ **边界(如实声明)**:结构可判的恒真式挡得住,`hash("x") == hash("x")`
        这类仍能绕过。原写「靠大 diff 评审补位」,但 **本仓当前无此控制**
        —— 5 个自守链文件未被 git 跟踪,`git diff` 无输出(与 C14 同族)。
        ★ **R106 补回**(红队 R105 P26-R105-A):R105 手工删行时**误删了本句尾巴**
        「(与 C14 同族)。」并留下**孤立 `)`** —— 这是执行者**把自己插入的文本
        当成了原文**所致(见 R105 章 §4.1)。
        ⚠ **第九次「补一格」**;R103 起本类形态已登记进 `docs/structural-boundaries.md` §一。
        """
        src = (ROOT / "tools" / "mutation_harness.py").read_text(encoding="utf-8")
        # ① 正例:当前判据全合规
        kinds = MH._selftest_check_kinds()
        self.assertEqual(len(kinds), MH.SELFTEST_CHECKS - 1,
                         f"结构判据扫到 {len(kinds)} 条,期望 {MH.SELFTEST_CHECKS - 1}")
        self.assertEqual(kinds, ["Compare"] * (MH.SELFTEST_CHECKS - 1),
                         f"有 _check 的条件不是合规比较式:{kinds}")
        # ② 变异注入:`SELFTEST_CHECKS - 1` 条锚 × 3 档,每条每档都必须被查出
        anchors = [
            "_check(naive == DETECTED,",
            "_check(guarded == CRASH,",
            '_check(target_crashes(work, "tools/x.py") is True,',
            '_check(target_crashes(work, "tests/t.py") is False,',
            "_check(real == EXPECT_TESTS,",
            "_check(real is not None,",
            "_check(real >= MIN_SUITE_TESTS,",
            "_check(_methods_without_assertions(_harness_src())",
            "_check(set(sum(_targets.values(), [])) ==",
            "_check(tuple(sorted(_targets)) ==",  # ★ R88 第 2 轮:单行条件(多行会被变异注入改坏)
            "_check(_pre_registered_files() == tuple(PARTICIPATING_FILES),",
            "_check(_pre_registered_ints() == _code_side_pre_registered(),",
            "_check(_early_return_funcs(_self_src(), (\"_pre_registered_ints\", \"_code_side_pre_registered\")) == [],",
        ]
        self.assertEqual(len(anchors), MH.SELFTEST_CHECKS - 1,
                         "变异锚条数 != 判据条数 —— 有新判据没被覆盖")
        blind = []
        for anchor in anchors:
            self.assertIn(anchor, src, f"变异锚失效(条件被重命名?):{anchor}")
            for tag, repl in (("True", "_check(True,"),
                              ("True == True", "_check(True == True,"),
                              ("len([]) == 0", "_check(len([]) == 0,")):
                mutant = src.replace(anchor, repl, 1)
                self.assertNotEqual(mutant, src, f"变异注入没命中:{anchor}")
                got = MH._selftest_check_kinds(mutant)
                if "Compare" == got[0] and got == ["Compare"] * (MH.SELFTEST_CHECKS - 1):
                    blind.append((anchor, tag))
        self.assertEqual(blind, [],
                         f"这些阉变异**没被结构判据查出**(harness 与 H8 双双静默):{blind}")


    def test_H9_run_case_copies_every_participating_file(self):
        """★★★ Round 87(红队 R82 / 附录 C31 ⑤ / C32 ⑦ —— **跨三轮未修**):

        `run_case()` 的沙箱拷贝清单**硬编码 3 项**(`SCRIPT_REL` / `TEST_REL` / `LEDGER_REL`),
        而 `repo_digest()` 覆盖 **8 项** —— 两处**不派生自同一源**。
        红队实测:对 `tests/pre_registered.py`(`PRE_REG_REL`)做变异时,
        副本里**没有**该文件 ⇒ `tgt.read_text()` 抛**未捕获** `FileNotFoundError`。

        ⚠ 这是本仓记过的形态:**「同一份清单抄成两份,改一处 != 改一类」**。
        修法:抽出模块级 `PARTICIPATING_FILES`,两处共用。
        """
        # ① **具名清单逐项对拍** —— 不是长度下界。
        #   红队 P8-R87-B【高】:第 1 轮的 `>= 8` 是数量判据,
        #   去掉 `tools/g_check.py` 换入 `package.json`(仍 8 项)即全绿,
        #   且污染 `tools/g_check.py` 零告警 —— 一条编辑重新打开 R82 修过的洞。
        self.assertEqual(
            tuple(MH.PARTICIPATING_FILES), tuple(PR.PARTICIPATING_FILES),
            "参与文件清单与预注册的具名清单不一致")
        # ③ **AST 判据**:`run_case` 的拷贝目标必须**就是** `PARTICIPATING_FILES`。
        #   红队 P8-R87-A/C【高】:① 只比两个常量,`run_case` 里写
        #   `PARTICIPATING_FILES[:3]` 或改回硬编码 3 项字面量,① 全绿。
        self.assertEqual(
            # ⚠ R88:实现搬到 `tools/mutation_harness.py`(**单一来源**),
            #   并同时由 `_selftest()` 第 ⑨ 条调用 —— 这里保留为**第二执行点**。
            MH._participating_file_targets(
                (ROOT / "tools" / "mutation_harness.py").read_text(encoding="utf-8")),
            {"repo_digest": ["PARTICIPATING_FILES"],
             "run_case": ["PARTICIPATING_FILES"]},
            "`repo_digest`/`run_case` 的遍历目标不都是 `PARTICIPATING_FILES`"
            "(切片/字面量都算分叉)")
        # ④ `HARNESS_TESTS` 必须**等于**实际用例数。
        #   红队 P8-R87-E【中】:它只被单边下界消费,下调无人抓。
        self.assertEqual(
            PR.HARNESS_TESTS,
            len(re.findall(r"^    def test_H", (ROOT / "tests" / "test_mutation_harness.py")
                           .read_text(encoding="utf-8"), re.M)),
            "`PR.HARNESS_TESTS` 与实际 `test_H*` 方法数不符")
        # ② 行为:对**最后一个**参与文件做变异,必须**不抛异常**
        try:
            got = MH.run_case("H9_probe", MH.PRE_REG_REL,
                              "SUITE_FILES = 36", "SUITE_FILES = 35")
        except Exception as e:                       # noqa: BLE001
            self.fail(f"run_case 对 {MH.PRE_REG_REL} 抛了 {type(e).__name__}: {e}")
        self.assertEqual(len(got), 4, f"run_case 返回形状不对:{got}")
        self.assertIn(got[1], (MH.DETECTED, MH.EQUIV, MH.CRASH, MH.STALE),
                      f"返回了非法 kind:{got[1]}")

    def _count_assertions(self, pattern):
        """在子进程里给 `unittest.TestCase.assert*` 打桩,按 `test.id()` 计断言数。

        ★ Round 81:`JEV_SELFCOUNT_INNER=1` 是**递归护栏** —— 见 `test_H6` 的 docstring。
        """
        code = _COUNTER.replace("__PATTERN__", pattern)
        env = dict(os.environ, JEV_SELFCOUNT_INNER="1")
        r = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", code],
                           cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env, timeout=300)
        blob = (r.stdout or "") + (r.stderr or "")
        m = re.search(r"^COUNTS_JSON=(.+)$", blob, re.M)
        self.assertIsNotNone(m, f"取不到断言计数:\n{blob[-1500:]}")
        return json.loads(m.group(1))

    def test_H10_harness_prints_ok_marker_on_success(self):
        """红队 P18-R97-C【高】:**CI 跑的是本文件,不是 `tools/mutation_harness.py`。**

        `package.json scripts.test` 38 段里**没有** `tools/mutation_harness.py`
        ⚠ **R104 更正**(红队 R103 P24-R103-F):原写「36 段」,实测 **38 段**(段 7 是 `tests/test_mutation_harness.py`)。
        所以 harness 自己的「**`rc=0` 且零输出 = 假绿**」在 **CI 路径上无人抓** ——
        红队实测:模块级 1 行 `raise SystemExit(0)` ⇒ `python tests/test_mutation_harness.py`
        **`rc=0` / 0 B / 0.1s**;`_selftest` 体首 `os._exit(0)` ⇒ `-k H1` **`rc=0` / 0 B**。

        本条把 harness 当**子进程**跑,断言两件事:
          ① `rc == 0`;
          ② **stdout 含 `[ok] selftest`** —— 这一条同时修 **P18-R97-D / P10-R89-F**
             (「`[ok] selftest` 行无人断言其存在」;全仓此前唯一命中是**反向**的 `assertNotIn`)。
        ⚠ 加 `timeout=180` ⇒ 顺带修 **P13-R92-E**(`subprocess.run` 无 `timeout=` ⇒ 挂死时永久阻塞)。
        ⚠ **边界(如实声明)**:`os._exit(0)` 在 harness **模块级**仍能绕过(它根本不启动);
        本条只覆盖「**harness 启动了、但提前静默退出**」这一族。
        """
        r = subprocess.run([sys.executable, "-X", "utf8", "-B", MH.HARNESS_REL],
                           cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180)
        blob = (r.stdout or "") + (r.stderr or "")
        self.assertEqual(r.returncode, 0,
                         f"harness 非零退出(rc={r.returncode}):\n{blob[-1500:]}")
        self.assertIn("[ok] selftest", blob,
                      f"harness rc=0 但**没印** `[ok] selftest` —— 可能根本没跑(假绿):\n{blob[-1500:]}")

if __name__ == "__main__":
    unittest.main()
