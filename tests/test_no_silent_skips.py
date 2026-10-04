"""Round 60/61:`OK` 不等于「验过了」—— skip 通道必须有守卫。

## 缺陷

`unittest` 在测试被**跳过**时也返回 **exit 0**,打印 `OK (skipped=N)`。
而 `tools/g_check.py` 的 G1/G3 判据原本是:

    ok = (rc == 0)

于是「有 3 条测试被跳过」与「全都验过了」在**回归输出里完全不可区分**。
更糟的是 detail 写的是 `Ran 行 30 条,失败 0 条` —— 那是**套件数**,不是测试数,
读起来却像「30 个套件全验过了」。这与本仓记过的「含糊的 count 给出权威的错数」同族。

## 本文件做三件事

1. **静态白名单**(S1/S2/S3/S4/S9):`tests/` 下每一处**静态字面** skip 通道
   都必须登记在案并写明理由;白名单项也必须仍然存在(S2),否则会腐烂成
   「曾经可以跳过」的清单。
2. **判据本身可测**(S5/S6/S6b):`g_check` 的 skipped 解析是纯函数,单独测;
   并且**用行为判据**(喂合成输出、看 `g1()` 真的怎么判)而不是 AST 检查 ——
   R60 初版是 AST 检查,红队实测可被 `_skip_total("")` 绕过(S6b 把这个鉴别力
   差距**自证**出来)。
3. **边界如实声明**(S8):S1 只覆盖静态字面通道;别名/变量/getattr/`raise` 等
   **动态**写法检不出来。兜底不在 S1 而在**运行时** —— 只要真跳过了,
   `skipped != 0` 就让 G1/G3 变红(S6 测的就是这条)。
   **S1 负责「让人看得见」,S6 负责「拦得住」。**

⚠ 白名单键 = (文件, 方法名, skip 点源码段)。**不能**只用「文件 + 文本片段」:
删掉已登记的 skip、在别处新增未登记的 skip、把旧片段塞进新 skip 的窗口 ——
文件对、片段对,S1/S2 双双全绿(Round 60 红队实测的换靶绕过)。
加上方法名仍不够(同一方法里可以放两个 skip);只有绑到该 skip 点**自己的源码段**,
换靶才不成立。

⚠ 但绑到源码段之后,同方法里**复制粘贴**两处一样的 skip 会让两条键**完全相同** ——
所以 S1 比的是**多重集**(逐键计数),不是集合。比集合时「2 个真实通道、只登记 1 条」
照样全绿(Round 61 红队实测)。
"""

import ast
import importlib.util
import os
import pathlib
import re
import sys
import tempfile
import unittest
from collections import Counter

REPO = pathlib.Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"

#: ⚠ **这不是「允许跳过」的许可** —— 它是「**已知 skip 通道清单**」:
#: 每一处 skip 都必须在这里**被人工看过并写明理由**,它的存在是为了让
#: 「有 skip 通道」这件事**可见**,而不是让它悄悄发生。
#: 注意:登记 ≠ 可以跳。真跳过时 `skipped != 0` 仍然让 G1/G3 变红(S6)。
#: 键 = (相对路径, 所在测试方法名, skip 点源码段规范化)。
SKIP_ALLOWED = [
    ("tests/test_accuracy_bench.py", "test_ny_open_vs_zoneinfo",
     'unittest.skipUnless(_HAS_TZ, f"缺 IANA 时区库(Windows 需 `pip install tzdata`): {_TZ_WHY}")',
     "本机能力缺失:无 tzdata 时 zoneinfo 不可用(CI 已显式安装)"),
    ("tests/test_baseline_arm_honesty.py", "test_T6_audit_runs_on_real_A1_data",
     'self.skipTest("A1 的 runs 文件不在本仓")',
     "数据缺失:该实验产物不在仓内(README 已声明)"),
    ("tests/test_baseline_arm_honesty.py", "test_T6_audit_runs_on_real_A1_data",
     'self.skipTest("该文件不含 A1 臂")',
     "数据缺失:runs 文件存在但不含目标臂"),
    ("tests/test_path_spelling.py", "test_P1c_junction_identity_passes_or_skips_loudly",
     'self.skipTest( f"本机无法创建 junction(mklink 返回 {made.returncode}: " '
     'f"{made.stdout.strip()} {made.stderr.strip()})—— " '
     'f"该路径身份在本机不可测,如实跳过,不得静默通过")',
     "本机能力缺失:无 mklink 权限时,junction 路径身份不可测"),
    ("tests/test_ps_python_parity.py", "test_D3_ps_module_is_actually_covered_by_a_test",
     'self.skipTest("本机找不到 PS5.1 —— C0 的主要防护对象缺席")',
     "本机能力缺失:没有 PS5.1 时,跨实现一致性无从测起"),
    # ★ Round 81:本用例把「断言计数判据」**指向自己** —— 子进程跑本文件时,
    #   本用例会再次进入 ⇒ **无限递归**(实测挂死 >10 分钟)。故内层显式跳过。
    #   ⚠ 这是「判据指向自己」这一类设计的固有风险,不是数据缺失。
    ("tests/test_mutation_harness.py", "test_H6_harness_test_file_is_itself_covered",
     'self.skipTest("内层:避免 H6 递归调用自己")',
     "自指递归护栏:子进程内层再跑一次会无限递归,显式跳过并在此登记"),
    # ★ R82:H5 现在也调 `_count_assertions` ⇒ 同样会无限递归,共用同一护栏。
    ("tests/test_mutation_harness.py", "test_H5_pre_registered_numbers_are_ratcheted",
     'self.skipTest("内层:避免 H5 递归调用自己")',
     "自指递归护栏:子进程内层再跑一次会无限递归,显式跳过并在此登记"),
]

#: 检测用的名字(写成拼接,避免本文件自己被当成 skip 点)
_SKIP_CALLS = ("skip" + "Test",)
_SKIP_DECOS = ("skip", "skipIf", "skipUnless")
_UNITTEST = "unittest"


def _norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def find_skips(src):
    """返回 [(行号, 方法名, 规范化源码段)],覆盖**静态字面**的 skip 通道。

    只认两条通道:
      * `self.skipTest(...)`
      * `@unittest.skip` / `@unittest.skipIf` / `@unittest.skipUnless`

    ⚠ 必须限定 `self.` 与 `unittest.`,否则**误报**(Round 60 红队实测 4/6):
    `@skipIf`(别名)、`@mylib.skipIf`、`other.skipTest`、形参/方法名叫
    `skipTest` 的,都不是 unittest 的 skip 通道,却会被裸名字匹配抓成通道,
    逼着白名单去登记不存在的点。

    ⚠ 动态写法(getattr 拼接、变量、`raise unittest.SkipTest`、别名装饰器、
    `pytest.skip`)检不出来 —— 这是**已声明的边界**(S8 特征化钉住),不是漏检。
    """
    tree = ast.parse(src)
    parents = {}
    for n in ast.walk(tree):
        for c in ast.iter_child_nodes(n):
            parents[c] = n

    def method_of(node):
        cur = node
        while cur in parents:
            cur = parents[cur]
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return cur.name
        return "(模块级)"

    out = []

    def add(node):
        out.append((node.lineno, method_of(node),
                    _norm(ast.get_source_segment(src, node))))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if (isinstance(f, ast.Attribute) and f.attr in _SKIP_CALLS
                    and isinstance(f.value, ast.Name) and f.value.id == "self"):
                add(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.decorator_list:
                base = d.func if isinstance(d, ast.Call) else d
                if (isinstance(base, ast.Attribute) and base.attr in _SKIP_DECOS
                        and isinstance(base.value, ast.Name)
                        and base.value.id == _UNITTEST):
                    add(d)
    return sorted(set(out))


def iter_test_files():
    for p in sorted(TESTS.glob("test_*.py")):
        yield p


def _shaped_output(g, tail="OK", per_suite=5):
    """按**当前**形状判据合成 `npm test` 输出(Round 62 起 `g1` 会校验形状)。

    ⚠ 套件数取自 `g._expected_suites()`(文件系统锚点),**不写死** ——
    写死的合成输出会在套件数变化后**静默变成「形状不合法」的输入**,
    于是 S6 看起来「漏检」,实际是**样本没构造出来**。
    """
    n = max(1, g._expected_suites())
    body = "....\nRan %d tests in 0.1s\n\nOK\n" % per_suite
    return body * (n - 1) + "....\nRan %d tests in 0.1s\n\n%s\n" % (per_suite, tail)


def _load_g_check(source=None):
    """加载 `tools/g_check.py`;`source` 非空时加载**变异体**(临时文件)。"""
    if source is None:
        sys.path.insert(0, str(REPO / "tools"))
        import g_check
        return g_check
    fd, path = tempfile.mkstemp(suffix=".py", prefix="jev_g_check_mut_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(source)
        spec = importlib.util.spec_from_file_location("g_check_mutant", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # ⚠ 变异体从临时目录加载 → `ROOT = dirname(dirname(__file__))` 会算成 `%TEMP%`,
        # 于是 `_expected_suites()` 去找 `%TEMP%\tests` 并 `FileNotFoundError`。
        # 把 ROOT 指回真仓,让变异体**只在被检查的那一处**不同。
        mod.ROOT = str(REPO)
        return mod
    finally:
        os.unlink(path)


class TestNoSilentSkips(unittest.TestCase):
    def setUp(self):
        self.found = []          # [(rel, lineno, method, seg)]
        for p in iter_test_files():
            rel = str(p.relative_to(REPO)).replace("\\", "/")
            for ln, meth, seg in find_skips(p.read_text(encoding="utf-8")):
                self.found.append((rel, ln, meth, seg))

    def _fake_run(self, mod, out, rc=0):
        """把 `mod._run` 换成喂合成输出,测完自动还原。"""
        orig = mod._run
        mod._run = lambda argv, cwd=None: (rc, out)
        self.addCleanup(setattr, mod, "_run", orig)

    # S1 每一处 skip 通道都必须在白名单里
    def test_S1_every_skip_is_declared(self):
        """⚠ 比的是**多重集**,不是集合(Round 61 红队发现 3)。

        同一个方法里**复制粘贴**两处一模一样的 skip,两处的
        `(文件, 方法名, 源码段)` 完全相同 —— 比集合时两条都命中同一条登记,
        于是「2 个真实通道、只登记 1 条」照样全绿。**比计数才拦得住。**
        """
        declared = Counter((r, m, s) for r, m, s, _w in SKIP_ALLOWED)
        found = Counter((rel, meth, seg) for rel, _ln, meth, seg in self.found)
        lines_of = {}
        for rel, ln, meth, seg in self.found:
            lines_of.setdefault((rel, meth, seg), []).append(ln)
        undeclared = []
        for key, n in found.items():
            if declared.get(key, 0) < n:
                undeclared.append(f"{key[0]}:{lines_of[key]}  [{key[1]}]  {key[2][:80]}"
                                  f"  ×{n}(只登记 {declared.get(key, 0)} 次)")
        self.assertEqual(undeclared, [],
                         "以下 skip 通道没有登记(它会静默把「没验」变成「绿」):\n  "
                         + "\n  ".join(undeclared)
                         + "\n\n登记方式:加进本文件的 SKIP_ALLOWED,并写明为什么可以 skip。")

    # S2 白名单不许腐烂:每一项都必须仍然命中一个真实 skip 点,且不许有重复键
    def test_S2_allowlist_has_no_rot(self):
        found = {(r, m, s) for r, _l, m, s in self.found}
        rotten = [f"{rel} [{meth}] ← {seg[:70]!r} 已不再命中任何 skip 点"
                  for rel, meth, seg, _why in SKIP_ALLOWED if (rel, meth, seg) not in found]
        keys = [(r, m, s) for r, m, s, _w in SKIP_ALLOWED]
        dup = [f"{k[0]} [{k[1]}] {k[2][:60]!r} ×{keys.count(k)}"
               for k in set(keys) if keys.count(k) > 1]
        self.assertEqual(rotten, [],
                         "白名单项已失效(代码改好了却没删掉登记,清单会腐烂):\n  "
                         + "\n  ".join(rotten))
        self.assertEqual(dup, [],
                         "白名单有重复键 —— 其中一条是死条目,S2 的腐烂判据看不见它:\n  "
                         + "\n  ".join(dup))

    # S3 可证伪:合成一个带 skip 的文件,检测器必须报出来,且方法名要归属正确
    def test_S3_falsifiable(self):
        src = ("import unittest\n"
               "class T(unittest.TestCase):\n"
               "    def test_a(self):\n"
               "        self.skipTest('假装验过了')\n"
               "    @unittest.skipUnless(True, '也是 skip')\n"
               "    def test_b(self):\n"
               "        pass\n")
        got = find_skips(src)
        self.assertEqual(len(got), 2, f"检测器没抓到合成的 skip 点: {got}")
        self.assertEqual([m for _l, m, _s in got], ["test_a", "test_b"],
                         f"方法名归属错了(S1/S2 的键就靠它): {got}")

    # S4 空转守卫:扫描器必须**精确覆盖** `tests/` 下的全部测试文件
    def test_S4_scanner_actually_scanned(self):
        """⚠ Round 65 改口径:旧版是 `len(files) >= 25`(真实 33,余量 24%)
        且**零具名样本** —— 路径规则收窄到只剩 25 个文件仍判绿。
        改成与**独立机制**(`os.listdir`,与被测的 `pathlib.glob` 不同)算出的
        集合**精确相等**:少一个、多一个都红。

        ⚠ Round 65 红队实测指出:初版注释自称「与被测的 `os.listdir` 不同」,
        而当时两半写的是**同一个** `TESTS.glob("test_*.py")` 表达式 —— **名不副实**,
        被测函数没坏时两半恒等,那个「独立」是假的。**撒谎的注释比没有注释更危险**
        —— 下一个人会据此以为这里有交叉校验。现已改成真的独立机制。

        `skip` 点数的守卫同理 —— 旧版 `>= 5` 而真实恰好 5(余量 0),
        它证明不了「检测器找到了**该找的**那些」。改成与 `SKIP_ALLOWED`
        (本身就是一份人工看过的**具名清单**)**精确相等**:
        `found` 比白名单少 → 检测器漏了;多 → S1 会报未登记,这里也先红。
        """
        files = sorted(p.name for p in iter_test_files())
        # 口径与 `glob("test_*.py")` 一致:都同时匹配文件与同名目录,不做 `isfile` 过滤。
        on_disk = sorted(n for n in os.listdir(TESTS)
                         if n.startswith("test_") and n.endswith(".py"))
        self.assertEqual(
            files, on_disk,
            f"`iter_test_files()` 与独立 `os.listdir` 的结果不一致 —— 路径规则收窄或放宽了。\n"
            f"  检测器={files}\n  独立 os.listdir={on_disk}")
        self.assertEqual(
            len(self.found), len(SKIP_ALLOWED),
            f"检测到的 skip 点({len(self.found)})与白名单({len(SKIP_ALLOWED)})不等 —— "
            "检测器漏了(则 S1 恒真),或白名单腐烂了(则 S2 该红)")

    # S5 g_check 的 skipped 解析必须正确(纯函数,可单独测)
    def test_S5_skip_total_parses_regression_output(self):
        g = _load_g_check()
        cases = [
            ("Ran 30 tests in 5s\n\nOK\n", 0, "全绿无 skip"),
            ("Ran 30 tests in 5s\n\nOK (skipped=1)\n", 1, "整套件被跳过"),
            ("Ran 30 tests in 5s\n\nOK (skipped=3)\n", 3, "多条被跳过"),
            ("Ran 30 tests in 5s\n\nFAILED (failures=1, skipped=2)\n", 2, "失败与跳过并存"),
            ("Ran 30 tests in 5s\n\nOK (skipped=1)\nRan 5 tests in 1s\n\nOK (skipped=2)\n", 3,
             "多个套件各跳一些"),
            # ↓ R60 红队发现 4:非 unittest 文本不得被当成计数(误报方向)
            ("[log] cache skipped=99 entries\nRan 30 tests in 5s\n\nOK\n", 0, "日志文本 skipped=99"),
            ("path C:/a/skipped=1/b.py\nRan 30 tests in 5s\n\nOK\n", 0, "路径里含 skipped=1"),
            # ↓ R60 红队发现 5:node --test 通道(输出里**没有** `skipped=` 字串)
            ("\u2139 tests 5\n\u2139 pass 4\n\u2139 skipped 1\n\u2139 fail 0\n", 1, "node 单条跳过"),
            ("\u2139 skipped 2\n", 2, "node 多条跳过"),
        ]
        for out, want, why in cases:
            self.assertEqual(g._skip_total(out), want, f"{why}: {out!r}")

    # S6 行为判据:g1/g3 必须**真的**对 skipped 反应(不是「代码里有个调用」)
    def test_S6_g1_g3_actually_react_to_skipped(self):
        g = _load_g_check()
        # ⚠ g1 自 Round 62 起还校验**输出形状**(附录 C12),故合成输入必须
        # 满足形状判据,否则 skip 反应会被形状判据掩盖 —— 那是**样本问题**,不是漏检。
        cases = [
            ("g1", _shaped_output(g), 0, 0, True, "全绿无 skip"),
            ("g1", _shaped_output(g, tail="OK (skipped=2)"), 0, 2, False, "两条被跳过"),
            ("g1", _shaped_output(g, tail="FAILED (failures=1)"), 1, 0, False, "有失败"),
            ("g3", "Ran 50 tests in 1s\n\nOK\n", 0, 0, True, "全绿无 skip"),
            ("g3", "Ran 50 tests in 1s\n\nOK (skipped=1)\n", 0, 1, False, "一条被跳过"),
            ("g3", "Ran 50 tests in 1s\n\nFAILED (failures=1)\n", 1, 0, False, "有失败"),
        ]
        for fn, out, rc, want_sk, want_ok, why in cases:
            self._fake_run(g, out, rc)
            r = getattr(g, fn)()
            self.assertEqual((r["skipped"], r["ok"]), (want_sk, want_ok),
                             f"{fn}() 对「{why}」反应错误 —— 跳过会被当成通过: {r}")

    # S6b 自证鉴别力:行为判据能抓住「吞掉 skip」的变异,而 AST 检查抓不住
    def test_S6b_behaviour_check_has_discriminating_power(self):
        src = (REPO / "tools" / "g_check.py").read_text(encoding="utf-8")
        old, new = "skipped = _skip_total(out)", 'skipped = _skip_total("")'
        self.assertEqual(src.count(old), 2, "变异锚点命中数不是 2 —— 变异体不可靠")
        mutated = src.replace(old, new)

        # 对照 1:老判据(AST 看有没有调用 _skip_total)对变异体**照样绿** → 零鉴别力
        tree = ast.parse(mutated)
        for fname in ("g1", "g3"):
            fn = next(x for x in tree.body
                      if isinstance(x, ast.FunctionDef) and x.name == fname)
            used = any(isinstance(x, ast.Call) and getattr(x.func, "id", "") == "_skip_total"
                       for x in ast.walk(fn))
            self.assertTrue(used, f"变异体 {fname} 已不调用 _skip_total —— 对照失效")

        # 对照 2:行为判据对同一个变异体报**绿**(skip 被吞) → 它确实在看行为
        mut = _load_g_check(mutated)
        g = _load_g_check()
        self._fake_run(mut, _shaped_output(g, tail="OK (skipped=2)"), 0)
        r = mut.g1()
        self.assertEqual((r["skipped"], r["ok"]), (0, True),
                         f"变异体没生效,本判据的鉴别力无法自证: {r}")

    # S8 特征化(不是修复):S1 只覆盖静态字面通道,动态写法是**已声明的边界**
    def test_S8_dynamic_channels_are_a_declared_blind_spot(self):
        """⚠ 本清单**不穷尽**(Round 61 红队指出:边界外的写法还有更多)。

        它的作用是钉住**边界的位置** —— 一旦某条已列写法被检出了,
        说明检测器变强了(应删掉该条),而不是「盲区消失了」。
        Round 61 红队实测:下列前 3 条新加的写法**真的会产生 `OK (skipped=1)`**。
        """
        dynamic = [
            ("getattr(self, 'skip' + 'Test')('x')", "getattr 拼接"),
            ("getattr(self, 'skipTest')('x')", "getattr 字面"),
            ("raise unittest.SkipTest('x')", "直接 raise SkipTest"),
            ("@alias_skip\ndef test_a(self):\n    pass\n", "别名装饰器"),
            ("import pytest\npytest.skip('x')", "pytest.skip"),
            # ↓ Round 61 红队发现 5:以下 5 种初版清单漏列,且实测全盲
            ("st = self.skipTest\nst('x')", "绑定变量再调用"),
            ("@ut.skipIf(True)\ndef test_a(self):\n    pass\n", "模块别名装饰器 @ut.skipIf"),
            ("@skip\ndef test_a(self):\n    pass\n", "from unittest import skip 后的裸装饰器"),
            ("unittest.skipIf(True)(f)", "手动应用装饰器(不走 decorator_list)"),
            ("super().skipTest('x')", "super().skipTest"),
        ]
        missed = []
        for body, why in dynamic:
            src = ("import unittest\nclass T(unittest.TestCase):\n"
                   "    def test_a(self):\n        "
                   + body.replace("\n", "\n        ") + "\n")
            if not find_skips(src):
                missed.append(why)
        self.assertEqual(sorted(missed), sorted(w for _b, w in dynamic),
                         "已列出的动态写法不再全盲 —— 要么检测器变强了(应删掉对应条目),"
                         f"要么坏了。当前**检出**的: {sorted(set(w for _b, w in dynamic) - set(missed))}")

    # S9 严格性:名字像 skip 的**非通道**不许被算成通道(否则白名单会逼人登记假点)
    def test_S9_detector_ignores_lookalikes(self):
        lookalikes = [
            ("@skipIf(os.name == 'nt')\ndef test_a():\n    pass\n", "别名装饰器 @skipIf"),
            ("@skip\ndef test_a():\n    pass\n", "裸 @skip"),
            ("@mylib.skipIf(True)\ndef test_a():\n    pass\n", "@mylib.skipIf(第三方)"),
            ("class A:\n    def helper(self):\n        other.skipTest('x')\n", "other.skipTest(非 self)"),
            ("def f(skipTest=None):\n    return skipTest\n", "形参名 skipTest"),
            ("class A:\n    def skipTest(self):\n        pass\n", "普通方法定义 skipTest"),
        ]
        bad = [f"{why}  ←  {src.splitlines()[0][:44]}"
               for src, why in lookalikes if find_skips(src)]
        self.assertEqual(bad, [],
                         "以下写法名字像 skip 但**不是** skip 通道,却被算成通道了"
                         "(白名单会被迫登记不存在的点):\n  " + "\n  ".join(bad))

    # S7 元判据:用例**具名清单**(不是计数)
    def test_S7_case_count(self):
        loaded = sorted(n for n in dir(type(self)) if n.startswith("test_"))
        self.assertEqual(loaded, sorted(CASE_NAMES),
                         "用例集变了 —— 删 / 改名 / 新增用例都必须同步改 CASE_NAMES 并说明原因")


#: 本文件的用例**具名清单**(不是计数)。
#: ⚠ 用**名字**而不是数字:数字只抓得住「删」,抓不住「**改名**」——
#: 把 `test_X` 改成另一个 `test_` 开头的名字,计数不变、判据全绿,
#: 而被保护的用例已经消失。Round 64 普查:全仓 6 个元判据里 5 个是这个形态
#: (Round 63 只在 `test_no_encoding_damage.py` 一个文件里修过 —— 按目录而非
#: 按缺陷类别划修复范围,本仓记过的失败形态)。
#: 改这份清单必须是**有意为之**的动作 —— 这就是它存在的意义。
CASE_NAMES = (
    "test_S1_every_skip_is_declared",
    "test_S2_allowlist_has_no_rot",
    "test_S3_falsifiable",
    "test_S4_scanner_actually_scanned",
    "test_S5_skip_total_parses_regression_output",
    "test_S6_g1_g3_actually_react_to_skipped",
    "test_S6b_behaviour_check_has_discriminating_power",
    "test_S7_case_count",
    "test_S8_dynamic_channels_are_a_declared_blind_spot",
    "test_S9_detector_ignores_lookalikes",
)

if __name__ == "__main__":
    unittest.main()
