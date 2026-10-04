# -*- coding: utf-8 -*-
r"""G1/G3 的判据必须验证「**真的跑到了东西**」—— 防**空转判据**(Round 62 / 附录 C12)。

## 缺陷的实质

`g1()` 的判据原为 `ok = rc == 0 and skipped == 0`,`g3()` 同理。
**两者都不看自己有没有测到东西。** Round 61 红队实测 5 种输出变换下 G1/G3
**全部判绿**:

| 变换 | 做法 | 旧判据 |
|---|---|---|
| `WRAP` | 每行加前缀 | 绿 |
| `FILTER` | 汇总行被吞 | 绿 |
| `EMPTY` | 空洞输出 | 绿(detail 还写着 `Ran 行 0 条`) |
| `RAN0` | 全部 `Ran 0 tests` | 绿 |
| `NOOP` | 整脚本空跑 | 绿 |

攻击链真实存在:改 `package.json` 的 `test` 脚本做包装 / 过滤 / 空跑 →
真跳过时 `_skip_total` 漏算 → **G1 绿**。`g1.ran`、`g3.m` 只进 detail,**不进 `ok`**。

**这是「空转判据」族在本仓的又一次复发**:判据看似在守,实则对被守对象零输入。

## 修法(以及为什么这样修)

`ok` 里加入**形状判据**,三个数字必须互相印证:

1. `suites`(**实跑**出的 `Ran N tests` 行数)
   == `_expected_suites()`(**文件系统**上应挂的套件数)
   == `_declared_suites()`(**`package.json`** 里声明的套件数);
2. `tests_total >= suites`(每个套件至少 1 个测试 → 挡 `Ran 0 tests`);
3. `verdicts >= 1`(汇总行 `^OK` / `^FAILED` 存在 → 挡「汇总行被吞」)。

⚠ **不写死数字**。写死就会过期,而过期的数字**没有判据守着** —— 本仓记过的
「含糊的 count 给出权威的错数」。三个锚点里两个来自产物(文件系统 / 配置),
改了配置判据跟着改,不需要人记得。

⚠ `_expected_suites()` 排除带「有意红」标记的文件 —— 那是本仓**既有**的约定,
与 `tests/test_means_markers.py::T4` 同源(标记写成拼接,免得本文件自己被当成
「有意红」而静默脱管)。

## 本判据的边界(如实声明)
- 只校验 **unittest 形状**。node `--test` 的 `ℹ tests N` **不参与计数**
  (它在 `package.json` 里是 1 条 `node --test`),本文件**不覆盖**该通道的形状。
- **不校验具体测试数**(那会随用例增删过期),只要求「每个套件 ≥ 1 个测试」。
  所以「把某个套件内部掏空到只剩 1 个用例」**不在覆盖范围内**。
- G3 只跑一个文件,故形状判据是 `suites >= 1`(而非 `== 期望`)。

## ⚠ 本文件自身的红线
**绝不在未打桩的情况下调用 `g1()` / `g3()`** —— 那会跑 `npm test`,而本文件
本身就在 `npm test` 里 → **无限递归**。所有行为判据必须 monkeypatch `_run`。

## Round 62 红队复算的结论(判【不成立】)与本轮加固

红队实测 6 种新绕过 + 2 类**真实误报**,逐条甄别后:

| 编号 | 现象 | 处置 |
|---|---|---|
| F1 | `print("Ran 5 tests in the morning")` 让套件数虚高 → **真绿判红** | **修**(正则锚整行,A8) |
| F2 | `OK: cache warm` 顶替被吞的汇总行 → **漏检** | **修**(正则锚整行,A8) |
| A1 | `echo "tests/test_a.py"` 只打印路径也被算成「声明」→ 三锚点齐满足、0 测试真跑 | **修**(只数真调用 + 文件存在,A9) |
| A3 | 31 套件吞掉 30 条汇总行,`verdicts >= 1` 仍成立 | **修**(改成 `== suites`,A9) |
| A4 | 测试全删 + 配置清空 → `0 == 0 == 0` 恒真 | **修**(加 `expected >= 1`,A9) |
| A2 | `OK (skipped=2)` 被**剥壳**成 `OK` → skip 漏算 | **登记为边界**(见下) |
| A5 | 直接改写 `tests/test_accuracy_bench.py` 去打印假形状 | **登记为边界**(见下) |
| — | 删 A2/A3/A5 并同步改 `CASE_NAMES` → 全绿 | **登记为边界**(元判据固有:改清单就是「有意为之」的动作,大 diff 可评审) |
| — | 把 `test_A2` **改名**成另一个 `test_` 开头的名字 | **已修**(Round 64:计数 → 具名清单双向比对) |

### 如实声明的边界(未修,不是漏检)

**当攻击者同时控制 `package.json` 与输出时,任何读输出的判据都能被伪造。**
他可以打印 31 组精确的假 `Ran`/`OK`,也可以把 `OK (skipped=2)` 剥壳成 `OK` ——
两者在输出层面与真实结果**不可区分**。同理,A5 只需改写一个入库文件。

本判据**不声称**能防这类伪造。它防的是**静默**:包装、过滤、空跑、漏挂、形状残缺
—— 这些会让 G1 从「绿」变成「红 + 写明原因」。真正的防线是 `package.json` 与
测试文件都是**入库受审**的产物,上述伪造必然留下一个大 diff。
(与 R13「指标须在 agent 控制之外」同源:这里的指标在**命令产出者**的控制之内,
只能靠**评审**补位。)
"""
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TESTS = os.path.join(REPO, "tests")

#: 本文件里的用例数(元判据;删用例会红)
#: 本文件的用例**具名清单**(不是计数)。⚠ 名字而非数字 —— 数字抓不住「改名」。
CASE_NAMES = (
    "test_A1_shape_check_is_falsifiable",
    "test_A2_g1_rejects_shape_transforms",
    "test_A3_g3_rejects_shape_transforms",
    "test_A4_anchor_counts_agree",
    "test_A5_real_shaped_output_still_passes",
    "test_A6_shape_check_has_discriminating_power",
    "test_A7_case_count",
    "test_A8_regex_boundaries",
    "test_A9_hardening_against_red_team_attacks",
    "test_A10_red_team_recheck_findings",
)

#: 「有意红」标记 —— 拼接写出,免得本文件自己被 T4 当成脱管文件
_KNOWN_RED = "EXPECTED" + "_RED"

#: 形状判据在 `g_check.py` 的 `ok` 表达式里的锚点(A6 变异用)
_SHAPE_TERM = " and shape_ok"

#: 双引号 —— 拼接写出,免得在锚点字符串里嵌套引号
Q = chr(34)


def _load_g_check(source=None):
    """加载 `tools/g_check.py`;`source` 非空时加载**变异体**(临时文件)。"""
    if source is None:
        sys.path.insert(0, os.path.join(REPO, "tools"))
        import g_check
        return g_check
    fd, path = tempfile.mkstemp(suffix=".py", prefix="jev_g_check_shape_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(source)
        spec = importlib.util.spec_from_file_location("g_check_shape_mutant", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)          # 变异体必须**导入即成功**(否则是伪证伪)
        # ⚠ 变异体从临时目录加载 → 它的 `ROOT = dirname(dirname(__file__))` 会算成
        # `%TEMP%`,于是 `_expected_suites()` 去找 `%TEMP%\tests` 并 `FileNotFoundError`。
        # **把 ROOT 指回真仓**,让变异体只在「被判据检查的那一处」不同。
        mod.ROOT = REPO
        return mod
    finally:
        os.unlink(path)


def _real_output(n_suites, per_suite=5):
    """按 unittest 的**真实形状**合成 npm test 输出。

    ⚠ `n_suites` **必须由调用方自锚定**(`mod._expected_suites()`),不能写死:
    Round 64 新增一个套件后,写死的 `31` 当场过期 → A1/A5/A10 三条一起误红。
    **写死的数字会过期,而过期的数字没有判据守着**(本仓已记)。
    """
    return "".join("....\nRan %d tests in 0.1s\n\nOK\n" % per_suite
                   for _ in range(n_suites))


def _transforms(base, per_suite=5):
    """Round 61 红队实测的 5 种输出变换(旧判据下**全部判绿**)。

    ⚠ `RAN0` 必须按 `per_suite` 定位 —— 写死 `"Ran 5 tests"` 时,若 base 用的是
    别的每套件数,`replace` 会**静默不生效**,那个变换就变成了「原样输入」,
    于是行为判据看起来「漏检」而实际是**样本没构造出来**。
    """
    return [
        ("WRAP",   "\n".join("WRAP " + l for l in base.splitlines()) + "\n"),
        ("FILTER", "\n".join(l for l in base.splitlines() if l.strip() != "OK") + "\n"),
        ("EMPTY",  ""),
        ("RAN0",   base.replace("Ran %d tests" % per_suite, "Ran 0 tests")),
        ("NOOP",   "ok\n"),
    ]


class TestGCheckActuallyRan(unittest.TestCase):
    def setUp(self):
        self.mod = _load_g_check()
        # ⚠ 自锚定:套件数从**产物**算,不写死(新增套件时不会过期)
        self.n = self.mod._expected_suites()
        self.base = _real_output(self.n)

    def _fake_run(self, out, rc=0, mod=None):
        """把 `_run` 换成喂合成输出,测完自动还原。"""
        mod = mod or self.mod
        orig = mod._run
        mod._run = lambda argv, cwd=None: (rc, out)
        self.addCleanup(setattr, mod, "_run", orig)

    # A1 形状判据本身可证伪
    def test_A1_shape_check_is_falsifiable(self):
        """`_unittest_shape` 必须能区分真实形状与 5 种变换。"""
        suites, tests_total, verdicts = self.mod._unittest_shape(self.base)
        self.assertEqual((suites, tests_total, verdicts),
                         (self.n, 5 * self.n, self.n),
                         "真实形状解析错了 —— 判据前提不成立")
        for name, out in _transforms(self.base):
            got = self.mod._unittest_shape(out)
            self.assertNotEqual(got, (self.n, 5 * self.n, self.n),
                                f"{name} 变换没有被形状判据区分出来")

    # A2 行为判据:g1 必须拒绝 5 种变换
    def test_A2_g1_rejects_shape_transforms(self):
        """⚠ 行为判据,不是 AST 检查(Round 61 红队发现 1 的教训)。"""
        for name, out in _transforms(self.base):
            self._fake_run(out)
            r = self.mod.g1()
            self.assertFalse(r["ok"], f"g1 对 {name} 输出判绿了:{r['detail']}")

    # A3 行为判据:g3 必须拒绝 5 种变换
    def test_A3_g3_rejects_shape_transforms(self):
        for name, out in _transforms(_real_output(1, 50), per_suite=50):
            self._fake_run(out)
            r = self.mod.g3()
            self.assertFalse(r["ok"], f"g3 对 {name} 输出判绿了:{r['detail']}")

    # A4 三个锚点里的两个(文件系统 / package.json)必须一致
    def test_A4_anchor_counts_agree(self):
        """⚠ 第三个锚点(**实跑**出的 `Ran` 行数)在本文件里**验不了** ——
        跑 `npm test` 会无限递归。它由外部 `tools/g_check.py` 的真实运行验证。
        """
        expected = self.mod._expected_suites()
        declared = self.mod._declared_suites()
        self.assertGreater(expected, 0, "文件系统锚点为 0 —— 判据前提不成立")
        self.assertEqual(
            expected, declared,
            "应挂的套件数 != package.json 声明的套件数 —— "
            "要么新增测试没挂进 npm test,要么声明了一个不存在的文件")

    # A5 鉴别力:真实形状必须仍然判绿(不能把真绿判红)
    def test_A5_real_shaped_output_still_passes(self):
        self._fake_run(self.base)
        r = self.mod.g1()
        self.assertTrue(r["ok"], f"真实形状被误判为红:{r['detail']}")

    # A6 自证鉴别力:去掉形状项的变异体必须**放行** WRAP
    def test_A6_shape_check_has_discriminating_power(self):
        """没有这条,A2 可能只是「恒红」—— 而恒红的判据什么也没守。"""
        src = open(os.path.join(REPO, "tools", "g_check.py"), encoding="utf-8").read()
        mutated = src.replace(_SHAPE_TERM, "")
        self.assertNotEqual(mutated, src,
                            f"变异没生效 —— `g_check.py` 里找不到锚点 {_SHAPE_TERM!r},"
                            "同步本文件")
        mod = _load_g_check(mutated)
        wrap = dict(_transforms(self.base))["WRAP"]
        self._fake_run(wrap, mod=mod)
        self.assertTrue(mod.g1()["ok"],
                        "去掉形状项的变异体竟然还是判红 —— A2 没有鉴别力")

    # A7 元判据:用例**具名清单**(不是计数)
    def test_A7_case_count(self):
        loaded = sorted(m for m in dir(type(self)) if m.startswith("test_"))
        self.assertEqual(loaded, sorted(CASE_NAMES),
                         "用例集变了 —— 删 / 改名 / 新增用例都必须同步改 CASE_NAMES 并说明原因")

    # ---- 以下两条来自 Round 62 红队的实测发现(判【不成立】后补的加固回归) ----

    def _fake_repo(self, script, names=("test_a.py", "test_b.py", "test_c.py")):
        """造一个只含 `tests/` + `package.json` 的临时仓,并把模块 `ROOT` 指过去。"""
        d = tempfile.mkdtemp(prefix="jev_r62_repo_")
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, "tests"))
        for name in names:
            open(os.path.join(d, "tests", name), "w").close()
        with open(os.path.join(d, "package.json"), "w", encoding="utf-8") as fh:
            json.dump({"scripts": {"test": script}}, fh)
        orig = self.mod.ROOT
        self.addCleanup(setattr, self.mod, "ROOT", orig)
        self.mod.ROOT = d
        return self.mod

    # A8 正则边界:日志行不得被当成计数行 / 结论行(红队 F1 误报、F2 漏检)
    def test_A8_regex_boundaries(self):
        """Round 62 红队 F1/F2,均为**实测**:

        - F1 **误报**:`print("Ran 5 tests in the morning")` 让套件数虚高 → 真绿判红;
        - F2 **漏检**:`OK: cache warm` 顶替被吞的汇总行 → 判绿。

        两条修法相同:必须**整行**匹配。
        """
        log = _real_output(2, 5) + "Ran 5 tests in the morning\n"
        self.assertEqual(self.mod._unittest_shape(log)[0], 2,
                         "`Ran N tests in the morning` 被算成了计数行 —— 会误报")
        self.assertEqual(self.mod._unittest_shape("Ran 1 test in 0.001s\n\nOK\n")[0], 1,
                         "单数 `test` 的真实计数行漏匹配")
        self.assertEqual(self.mod._unittest_shape("OK: cache warm\n")[2], 0,
                         "`OK: ...` 被算成了结论行 —— 汇总行被吞时会漏检")
        for v in ("OK", "OK (skipped=1)", "OK (skipped=0)",
                  "FAILED (failures=2)", "FAILED (failures=1, errors=1)"):
            self.assertEqual(self.mod._unittest_shape(v + "\n")[2], 1,
                             f"真实结论行 {v!r} 漏匹配")

    # A9 红队 A1/A3/A4 的加固回归(每条都是实测过的绕过)
    def test_A9_hardening_against_red_team_attacks(self):
        # A1:`echo "tests/test_a.py"` 只把路径**打印**出来 —— 不是调用,不得计数
        m = self._fake_repo('echo "tests/test_a.py" && echo "tests/test_b.py"')
        self.assertEqual(m._declared_suites(), 0,
                         "只被 `echo` 打印出来的路径被当成了「声明」—— 红队 A1 复活")
        # 真的调用才计数;指向**不存在**的文件也不计数;node 段不算 python 套件
        m2 = self._fake_repo("python tests/test_a.py && python tests/test_b.py "
                             "&& python tests/test_missing.py "
                             "&& node --test tests/test-*.mjs")
        self.assertEqual(m2._declared_suites(), 2,
                         "「真的调用 + 文件存在」这两条没生效")

        # ⚠ **必须显式还原 ROOT** —— 否则下面的形状判据跑在临时仓上,
        # `suites(31) == expected(3)` 直接为假,断言就**空洞通过**了。
        # 这个洞是 Round 62 的**变异测试**抓到的:回退 A3/A4 的修法时测试竟然还是绿的。
        self.mod.ROOT = REPO

        # A3:31 套件吞掉 30 条汇总行 → 只剩 1 条,必须判红
        kept, seen = [], 0
        for l in self.base.splitlines():
            if l == "OK":
                seen += 1
                if seen > 1:
                    continue
            kept.append(l)
        self._fake_run("\n".join(kept) + "\n")
        r3 = self.mod.g1()
        self.assertFalse(r3["ok"], "汇总行被吞掉 30 条仍判绿 —— 红队 A3 复活")
        self.assertEqual(self.mod._unittest_shape("\n".join(kept) + "\n")[2], 1,
                         "A3 的样本没构造出来(结论行不是 1 条)—— 断言无意义")

        # A4:测试全删光 + 配置清空 → 三个锚点同时归零,`0 == 0 == 0` 恒真。
        # ⚠ 样本必须是**空输出**:若喂 `OK\n`,`verdicts(1) == suites(0)` 也为假,
        # 于是红的原因是**另一条**子判据 —— 那样就测不到 `expected >= 1` 这一条。
        m3 = self._fake_repo("echo ok", names=())
        self._fake_run("", mod=m3)
        self.assertFalse(m3.g1()["ok"],
                         "锚点全归零仍判绿 —— 红队 A4 复活")

    # A10 红队**补派**的两条发现:N1 路径内嵌伪造 / ANSI 彩色输出误报
    def test_A10_red_team_recheck_findings(self):
        """Round 62 红队补派(判【部分完整】)实测的两条:

        - **N1(高)**:`python -c "print('tests/test_a.py')"` 把路径写在**字符串里**
          也被算成「声明」→ 31 条这种段 + 打印假形状 → 三锚点齐满足、**判绿**。
        - **ANSI**:彩色汇总行 `\\x1b[32mOK\\x1b[0m` 让整行正则全部失配 →
          **合法**输出被判红(误报)。
        """
        # N1:路径必须出现在**段尾**,不能只是字符串里提到的
        n1 = self._fake_repo(
            "python -c " + Q + "print('tests/test_a.py'); print('OK')" + Q
            + " && python -c " + Q + "print('tests/test_b.py')" + Q)
        self.assertEqual(n1._declared_suites(), 0,
                         "字符串里内嵌的路径被当成了「声明」—— 红队 N1 复活")
        # ⚠ 段尾锚点**单独**就能挡住上面那条;解释器前缀只对「段尾是测试路径
        # 但根本不是 python 调用」生效 —— 少了这个样本,前缀校验就是**零覆盖**的。
        # (Round 62 变异 M-11 实测:回退前缀校验时测试竟然还是绿的。)
        n2 = self._fake_repo("cat tests/test_a.py && node tests/test_b.py")
        self.assertEqual(n2._declared_suites(), 0,
                         "不是 python 调用的段被算成了「声明」")
        self.mod.ROOT = REPO

        # ANSI:剥掉转义后必须与无色输出同形
        esc = "\x1b[32mOK\x1b[0m"
        colored = "".join("....\n\x1b[36mRan 5 tests in 0.1s\x1b[0m\n\n%s\n" % esc
                          for _ in range(self.n))
        self.assertEqual(self.mod._unittest_shape(colored),
                         (self.n, 5 * self.n, self.n),
                         "彩色输出的转义没被剥掉 —— 会把合法输出判红")
        self._fake_run(colored)
        self.assertTrue(self.mod.g1()["ok"],
                        "合法的彩色输出被误判为红(误报)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
