# -*- coding: utf-8 -*-
r"""★★★ Round 79:变异判定框架**进仓** —— 崩溃 / 等价 / 真检出 三分。

## 为什么它必须在仓内(红队 R78 §R13 ①)
R78 我把它写在 `%TEMP%\jev_mutlib.py`。红队判:「它**住在仓外**,不在 git、
无测试覆盖、第三方不可复现 —— **比仓内那些更不可追溯**。」**这条成立。**
故 Round 79 把它搬进仓,并加一个它自己的测试。

## 为什么需要它(红队 R77 P2-R77-1 反证 + 我复核)
R77 我声称「全角 `＝` / 全角 `:` / ASCII 对照 → 4/4 真检出」。**假的。**
锚点 `print(f"A10 ..."` 是**多行 f-string 的第一物理行** —— 把新语句插在它后面会
**切断语句拼接** → `SyntaxError`。而我的判定只看 `rc != 0 and "Ran " in out`,
于是**把崩溃记成了检出**。
红队 R78 进一步实测:**崩溃会产生 `Ran 25 tests` + 13 条真 `FAIL:` 行** ——
连「要求 ≥1 条 FAIL」的朴素分类器也会记成检出。
**这正是本仓老病「我跑了变异 ≠ 我跑到了该跑的那条」的第三次复发。**

## 三分判据(机制,不是记性)
| 判定 | 判据 |
|---|---|
| **崩溃** | ① 套件连 `Ran ` 汇总行都没有;或 ② **被变异的目标自身**起不来 |
| **等价变异** | 套件全绿,**且**测试数与期望一致(见下) |
| **真检出** | `rc != 0` **且**有 `Ran ` 行 **且**至少一条 `FAIL:` 行 |

## ★★ Round 79 的两处修正(红队 R78 P2-R78-2 / P2-R78-3)
**(甲)P2-R78-2 —— 预检只对「非测试文件」目标生效。**
红队实测:unittest 的 **FAIL 块本身就含 `Traceback (most recent call last):`**,
而 `target_crashes` 原来就是 grep 这一行 ⇒ 任何针对 `tests/` 的真检出都被改判成「崩溃」。
**修**:预检只跑 `tools/` 下的目标;测试文件目标跳过预检。
**(乙)P2-R78-3 —— `classify` 必须校验测试数。**
红队实测:把 `test_A11e` 体首插 `return` → `Ran 25 OK` 被判「等价变异」;
`Ran 24 tests OK` / `Ran 0 tests OK` 也全判「等价变异」。
**修**:`classify` 收 `expect_tests`,数不对 ⇒ 直接判**崩溃**(形状不对)。

⚠ **判据自检**:本模块 `_selftest()` 故意注入语法错误,确认它被判成**崩溃**;
  并固化「裸分类器会把它误判成真检出」这个前提。
"""
import ast
import atexit
import os
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_REL = "tools/evasion_audit.py"
TEST_REL = "tests/test_evasion_audit.py"
LEDGER_REL = "docs/evasion-ledger.md"
# ★★★ Round 82(红队 R81 ③):`repo_digest` 只覆盖 3 个文件 ⇒ 污染框架自己零告警。
HARNESS_REL = "tools/mutation_harness.py"
HARNESS_TEST_REL = "tests/test_mutation_harness.py"
SKIP_ALLOWED_REL = "tests/test_no_silent_skips.py"
GCHECK_REL = "tools/g_check.py"
# ★★★ Round 82 补修(自查):`tests/pre_registered.py` 是 R82 为修自指而**新建**的
#   参与文件,却**没进 `repo_digest`** —— 「3 文件 → 7 文件」是补数量,
#   不是**按「谁参与判定」定清单**。
PRE_REG_REL = "tests/pre_registered.py"

CRASH, EQUIV, DETECTED, STALE = "崩溃", "等价变异", "真检出", "锚点失效"

EXPECT_TESTS = 25
# ★★★ Round 81(红队 R80 P2-R80-3【高】):**预注册下界** —— `real_test_count()` 是
#   「常量 vs **当前**套件」的**自洽对拍**;红队三处自洽下调(删一个用例 +
#   改 `EXPECTED_TESTS` + 改 `EXPECT_TESTS` 为 24)⇒ **五个守卫全绿**。
#   故另加一个**只许增不许减**的下界。⚠ 它自己也是常量 —— 见 `tests/` 的棘轮。
MIN_SUITE_TESTS = 25
# ★★★ Round 82 补修(自查):这里原来有 `MIN_SUITE_FILES = 34` —— R82 记账写「已删」,
#   实测**仍在且全仓零引用**(R82 把 H5 的口径改成 `pkg["scripts"]["test"]` +
#   `PR.SUITE_FILES` 后,它就没人读了)。**记账与事实不符,已删。**
# ★★★ Round 82(红队 R81 P2-R81-A【高】):`_selftest()` 必须真跑到的判据条数。
#   红队删掉其中 5 条(只留⑤)→ `rc=0 Ran 7 tests OK` —— **无人看见**。
#   ⚠ **R104 更正**(红队 R103 P24-R103-G):原写「6 条中的 5 条」,实测判据总数 = **14**。
SELFTEST_CHECKS = 14


def _require(cond, msg):
    """★ Round 81(红队 R80 P2-R80-1【高】):**显式 raise,不用 `assert`**。

    红队实测:`python -O` 下裸 `assert` 全部消失,`_selftest()` 空转
    **还主动打印「[ok] … matches the real suite」这句假话**。
    `assert` 是**可被解释器开关剥掉**的判据 —— 判据不能用它。
    """
    if not cond:
        raise AssertionError(msg)


# ★★★ Round 82(红队 R81 P2-R81-A【高】):`_selftest()` 里**删掉 `SELFTEST_CHECKS` 条判据中的任意几条**
#   ⚠ **R104 更正**(红队 R103 P24-R103-G):原写「6 条」,实测 = **14**。
#   都**无人看见** —— 红队删掉 5 条(只留⑤)→ `rc=0 Ran 7 tests OK`。
#   根因:`test_H7` 是**单点探针**,只扰 ⑤ 那一处。
#   ⇒ 记**条数**:`_selftest()` 跑完必须真跑过 `SELFTEST_CHECKS` 条,少一条就 raise。
SELFTEST_CHECKS_RUN = []


def _check(cond, msg):
    """`_selftest()` 专用:登记**跑过第几条**判据,再走 `_require`。"""
    SELFTEST_CHECKS_RUN.append(len(SELFTEST_CHECKS_RUN) + 1)
    _require(cond, msg)
# ⚠ 上面这个数**必须与真实套件一致** —— 否则框架静默失效。
#   ★ Round 80(红队 R79 N3):红队把 `EXPECT_TESTS` 改成 24(真实 25),
#   `_selftest()` **照样打印「✓ 判据自检通过」**,而此后框架对**一切**变异报「崩溃」。
#   根因:自检里的 25 是**字面量**,不绑常量。修:`_selftest()` 必须**实跑真套件**取 `Ran N`
#   与 `EXPECT_TESTS` 对拍,再顺手覆盖「漂移」这个前提。


def real_test_count():
    """实跑**未变异**的套件,取它自己报的 `Ran N` —— 这是 `EXPECT_TESTS` 的唯一真值来源。"""
    r = subprocess.run([sys.executable, "-X", "utf8", "-B", TEST_REL],
                       cwd=str(REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    out = (r.stdout or "") + (r.stderr or "")
    # ★★★ Round 91(红队 P11-R90-B【高】):**「harness 绿」推不出「npm test 绿」。**
    #   原来这里只取 `Ran N`,**不看 failures** —— 红队 R90 实证:第 ⑫ 条打破 H8 后
    #   `npm test` 是**红的**,而 harness 仍 `rc=0` 且打印 `[ok] ... matches the real suite`。
    #   ⇒ 套件**没绿**时返回 `None`,第 ⑤ 条当场红。
    #   ⚠ 选这个改法是为了**最小**:零新增判据、零常量变动、零 H8 锚点变动
    #   (R90 正是死在「加判据 ⇒ SELFTEST_CHECKS 变 ⇒ H8 锚点没同步」)。
    #   ★ Round 91 第 2 轮(红队 P12-R91-F【低】):改用**现成的 `r.returncode`** ——
    #   红队实测 D3b/D3c:只靠输出文本,1 行(`return EXPECT_TESTS` 或 `return None`→`pass`)
    #   即可让 harness 在套件红时照样 `rc=0` 且打印 `[ok]`。
    #   `r.returncode` 是**进程事实**,不依赖套件自印什么;红队 1b(`print("OK")`)与
    #   5b(压掉 summary)两条绕过路线都被它一并封死。
    #   ⚠ 三重条件**都不是冗余**:`r.returncode` 挡「进程非零退出」;
    #   `^OK` 挡「没有 OK 行」(输出被清空 / summary 被压);`FAILED|ERROR` 挡「有失败行」。
    if (r.returncode != 0
            or re.search(r"^(FAILED|ERROR)\b", out, re.M)
            or not re.search(r"^OK\b", out, re.M)):
        return None
    m = re.search(r"^Ran (\d+) tests?", out, re.M)
    return int(m.group(1)) if m else None


#: 参与自守链的**全部**文件。
#:
#: ★★★ Round 87(红队 R82 / 附录 C31 ⑤ / C32 ⑦ —— **跨三轮未修**):
#: `repo_digest()` 覆盖 **8** 项,而 `run_case()` 的沙箱拷贝清单**硬编码 3 项** ——
#: 两处**不派生自同一源**。红队实测:对 `tests/pre_registered.py`(`PRE_REG_REL`)做变异时,
#: 副本里**没有**该文件 ⇒ `tgt.read_text()` 抛**未捕获** `FileNotFoundError`。
#: ⚠ 这是本仓记过的形态:**「同一份清单抄成两份,改一处 != 改一类」**。
PARTICIPATING_FILES = (SCRIPT_REL, TEST_REL, LEDGER_REL, HARNESS_REL,
                       HARNESS_TEST_REL, SKIP_ALLOWED_REL, GCHECK_REL, PRE_REG_REL)


def repo_digest():
    """★★ Round 80(红队 R79 N5):`import hashlib` 原来是**死引用**。

    ★★★ Round 82(红队 R81 ③【中】):原来只对 `SCRIPT/TEST/LEDGER` **三**个文件求和 ——
    红队实测「污染 `tools/mutation_harness.py` → **rc=0 零告警**」。
    现在覆盖**全部 8 个**参与文件(含框架自己、框架的测试、跳过白名单、g_check、预注册)。
    ★★★ Round 82 补修:补上第 **8** 个 —— R82 新建的 `tests/pre_registered.py`。
    ★ **R106 更正**(红队 R105 P26-R105-G):原首句写「全部 **7** 个」,
    而**下一句**就写「补上第 **8** 个」—— **同一 docstring 自相矛盾**,
    与 P25-R104-A(`_early_return_funcs` 的 `Return`/`Raise`)是**同一个形态**。
    ⇒ 真值 = `len(PARTICIPATING_FILES)` = **8**。
    ⚠ 本数字**会腐烂**(清单加项即过期),本仓**无判据守卫它**。
    """
    h = hashlib.sha256()
    for rel in PARTICIPATING_FILES:
        p = REPO / rel
        h.update(p.read_bytes() if p.exists() else b"<absent>")
    return h.hexdigest()


def classify(rc, out, expect_tests=EXPECT_TESTS):
    """★ 三分。只看 unittest **自己**的汇总,避开台账/文档正文里的 `Ran=` 字样。

    ★ Round 79(红队 R78 P2-R78-3):`Ran 24 tests OK` / `Ran 0 tests OK` /
      `Ran 25 OK (skipped=25)` 原来**全判「等价变异」** —— 框架对测试数完全免疫,
      于是「阉掉唯一守卫」也能算等价。现在数不对直接判**崩溃**(形状不对)。
    """
    m = re.search(r"^Ran (\d+) tests?", out, re.M)
    if not m:
        return CRASH, []                       # 连汇总行都没有 ⇒ 根本没跑起来
    n = int(m.group(1))
    if n != expect_tests:
        return CRASH, []                       # 形状不对:少跑/多跑都算没跑对
    fails = [l for l in out.splitlines() if l.startswith("FAIL: ")]
    if rc == 0:
        return EQUIV, fails
    if not fails:
        return CRASH, fails                    # rc≠0 却一条 FAIL 都没有 ⇒ 全是 ERROR
    return DETECTED, fails


def target_crashes(work, target_rel):
    """★ 被变异的目标**自身**是否起不来。

    ★★ Round 79(红队 R78 P2-R78-2):**只对 `tools/` 下的目标生效。**
      测试文件的 unittest FAIL 块本身就含 `Traceback (most recent call last):`,
      原来无条件 grep 这一行 ⇒ **把针对 tests/ 的真检出全改判成崩溃**。
    """
    if not str(target_rel).startswith("tools/"):
        return False
    r = subprocess.run([sys.executable, "-X", "utf8", "-B", str(target_rel)],
                       cwd=str(work), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    # ⚠ 红队 P2-R78-4:只看 stderr 会漏掉 traceback 走 stdout 的情况 ⇒ 两边都看
    blob = (r.stderr or "") + (r.stdout or "")
    return ("SyntaxError" in blob) or ("Traceback (most recent call last)" in blob)


def run_case(name, target_rel, old, new):
    """在**冻结副本**上做一次变异,返回 `(name, kind, fails, detail)`。

    ⚠ 在副本上做,不碰仓库。红队 R77 两次用自己的脚本 bug 破坏了仓库台账 ——
      本函数用路径护栏:所有写目标 `resolve()` 后必须落在临时目录内。
    """
    work = pathlib.Path(tempfile.mkdtemp(prefix="jev_mut_"))
    # ★★★ Round 81(红队 R80 P2-R80-7【中】):`repo_digest()` 原来是**死函数** ——
    #   零调用,于是「跑完校验仓库未变」这句话**从死 import 变成死函数**,N5 只修了一半。
    #   现在真调用:跑前记一次,跑后比一次,不一致直接 raise。
    digest_before = repo_digest()
    try:
        # ★ R87:与 `repo_digest()` **同源** —— 不再是另一份硬编码清单。
        for rel in PARTICIPATING_FILES:
            dst = work / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / rel, dst)
        tgt = (work / target_rel).resolve()
        # ★★ Round 80(红队 R79 N5):原来是 `assert` —— **`python -O` 下直接消失**,
        #   红队实测「真写到沙箱外,rc=0,文件存在」。改成**显式 raise**(不可被 -O 剥掉)。
        if work.resolve() not in tgt.parents:
            raise RuntimeError(f"路径逃出沙箱: {tgt}")
        src = tgt.read_text(encoding="utf-8")
        if old not in src:
            return name, STALE, [], f"锚点在 {target_rel} 里找不到"
        tgt.write_text(src.replace(old, new, 1), encoding="utf-8", newline="\n")
        if target_crashes(work, target_rel):           # ★★ 先判崩溃(只对 tools/)
            return name, CRASH, [], "目标自身起不来(SyntaxError/Traceback)"
        r = subprocess.run([sys.executable, "-X", "utf8", "-B", TEST_REL],
                           cwd=str(work), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300)
        out = (r.stdout or "") + (r.stderr or "")
        kind, fails = classify(r.returncode, out)
        return name, kind, fails, ""
    finally:
        shutil.rmtree(work, ignore_errors=True)
        # ★ R81(红队 R80 P2-R80-7):变异**不得**污染真仓库 —— 这句话现在有实现,不是注释。
        after = repo_digest()
        if after != digest_before:
            raise RuntimeError(
                f"变异污染了真仓库:{digest_before[:16]} -> {after[:16]}")


def report(cases):
    """跑一批 `(name, target_rel, old, new)` 并汇总。返回 (统计, 明细)。"""
    tally, rows = {}, []
    for name, target_rel, old, new in cases:
        n, kind, fails, detail = run_case(name, target_rel, old, new)
        tally[kind] = tally.get(kind, 0) + 1
        rows.append((n, kind, len(fails), detail))
        print(f"  {kind:6s} {n}" + (f"   ({detail})" if detail else ""))
    return tally, rows


def _is_literalish(node):
    """字面量,或**只由字面量构成**的 `len/str/int/...` 调用。

    ★ R84 红队 P5-R84-A:⑦ 原来只判 `type(a).__name__ == "Compare"`,
    于是 `True == True` / `len([]) == 0` 这类**恒真比较式**一律放行
    (实测 ②–⑥ 共 10 组,harness `rc=0` **且** `-k H8 rc=0`)。
    """
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_literalish(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(_is_literalish(e) for e in node.keys + node.values)
    if isinstance(node, ast.UnaryOp):
        return _is_literalish(node.operand)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in ("len", "str", "int", "float", "bool", "list",
                                 "dict", "set", "tuple", "range", "abs", "sum", "min", "max")):
        return all(_is_literalish(a) for a in node.args)
    return False


def _kind_of(node):
    """合规返回 `"Compare"`;否则返回违规形态名(供报错定位)。"""
    if not isinstance(node, ast.Compare):
        return type(node).__name__
    operands = [node.left] + list(node.comparators)
    if all(_is_literalish(o) for o in operands):
        return "Compare-all-literal"
    return "Compare"


def _early_exit_methods(src):
    """AST:方法体内含 `Return` / `Raise` 的 `test_*` 方法名。

    ★★★ Round 85(红队 R82 M8 / 附录 C31 ④【高】):**掏空方法体比删除更隐蔽。**
    在 H5 的 `JEV_SELFCOUNT_INNER` 护栏**之外**插一个无条件 `return`:
    内层照样 skip(被 `_COUNTER` 的 `for k in skipped: counts.pop(k)` **抹掉**),
    于是 H4/H6 的 `silent` 判据**看不见它** ⇒ **七条棘轮静默失效而两套件全绿**。
    R85 Step 2 实测(副本,真实 rc):基线 `H4=0 / H5=0 / H6=0`;**掏空后 `H4=0 / H5=0 / H6=0`**。

    ⚠ 本函数原来住在 `tests/test_mutation_harness.py` 里,**只有一个执行点**(H6 体内)。
    红队 P6-R85-A【高】实测:在它**之前**插 1 行 `return`,或把实现改成 `return []`,
    判据整体失效而**无人兜底**(`META_FILES` 不含该文件)。
    ⇒ R85 第 3 轮搬到这里,由 `_selftest()` 第 ⑧ 条调用 —— 绕它必须**跨文件**改动。

    ⚠ **边界(如实声明)**:`return` 换成 `raise` 也抓(`ast.Raise`),
    但 `os._exit(0)` / `sys.exit()` / 死循环 / `self.skipTest` 仍能绕过 ——
    本仓「**补一格 ≠ 堵住**」的**第十次**实例,靠大 diff 评审(⚠ **本仓当前无此控制** —— 5 个自守链文件未被 git 跟踪,`git diff` 无输出)补位。
    """
    out = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Return, ast.Raise)):
                    out.append(node.name)
                    break
    return out


def _participating_file_targets(src):
    """AST:`repo_digest()` 与 `run_case()` 里每个 `for rel in <X>:` 的 `<X>` 源码文本。

    ★★★ Round 88(红队 P8-R87-C【高】剩余部分):R87 把这条判据放在
    `tests/test_mutation_harness.py::test_H9` 体内,于是**删掉 H9 的行为段**就无人抓
    (红队 C5:H9/H4/H6 全绿)。⇒ 与 R85 第 3 轮同法,**搬到本文件**,由 `_selftest()` 调用 ——
    绕它必须**跨文件**改动。
    ⚠ 边界:把本函数实现改成 `return ["PARTICIPATING_FILES"] * 2` 仍能绕过
    —— 这是本仓「**补一格 != 堵住**」的**第十二次**,靠大 diff 评审(⚠ **本仓当前无此控制**)补位。
    """
    tree = ast.parse(src)
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in ("repo_digest", "run_case"):
            out[node.name] = [ast.unparse(n.iter) for n in ast.walk(node)
                              if isinstance(n, ast.For)]
    return out


def _pre_registered_files():
    """从 `tests/pre_registered.py` 的**文本**里取出具名清单(不 import,避免循环依赖)。

    ★★★ Round 88 第 2 轮(红队 P9-R88-B【高】):第 ⑨ 条只锚「消费点的 iter 文本」,
    清单**内容**改了它看不见(C9/C10 实测 `_selftest` 全绿)。
    本条把「两份清单是否一致」也搬到**跨文件**执行点上。
    ⚠ 边界:正则只认「顶层 `PARTICIPATING_FILES = (` 后到 `)` 的字符串字面量」——
    把它改成从别处计算出来的值就绕过了。**第十三次「补一格」。**
    """
    p = REPO / PRE_REG_REL
    if not p.is_file():
        raise RuntimeError(f"找不到 {p} —— 「没看」!=「没问题」")
    m = re.search(r"^PARTICIPATING_FILES = \((.*?)^\)",
                  p.read_text(encoding="utf-8"), re.S | re.M)
    if not m:
        raise RuntimeError("预注册文件里找不到 PARTICIPATING_FILES 字面量")
    return tuple(re.findall(r'"([^"]+)"', m.group(1)))


def _self_src():
    """**本文件**(`tools/mutation_harness.py`)的源码。

    ⚠ `_harness_src()` 读的是 **`tests/test_mutation_harness.py`**,**不是本文件** ——
    Round 96 第一版误用它去查**本文件里**的 helper,于是永远返回 `[]`
    (本仓记过的「**「没看」被当成「没问题」**」)。
    """
    return pathlib.Path(__file__).read_text(encoding="utf-8")


def _early_return_funcs(src, names):
    """AST:具名函数的 body 里**除最后一个语句外**含 `Return` 的函数名。

    ⚠ **R104 更正**(红队 R103 P24-R103-D):原写「含 `Return` / `Raise`」,
    但实现**只查 `ast.Return`**(见下方 `isinstance(x, ast.Return)`)。
    **不查 `Raise` 是故意的** —— 护栏 `raise` 会被误算成「提前 return」,
    造成假红(见 R96 事故),所以这里改的是**文案**,不是实现。

    ★★★ Round 96(红队 P16-R95-C【高】):`_pre_registered_ints()` /
    `_code_side_pre_registered()` **自身零守卫** —— 红队实测在这两个 helper 的**体首插 1 行**
    `return _pre_registered_ints()` / `return {}`,整条「5 个常量对拍」立刻退化成**恒真式**,
    harness `rc=0 [ok]`、H8 `OK`,**无人抓**。第 ⑦ 条只查 `_check` **第一参数的形状**,
    **不查被调函数的实现**。
    ⚠ 这是 **R94 已登记的 P15-R94-B 同族** —— R94 打穿 `_pre_registered_int()`,
    R95 删其调用点却**新建同性质 helper** ⇒ **「补一格」→「换个格子补一格」**。
    本条从**实现体控制流**这一面查。
    ⚠ **边界(如实声明)**:只查 `Return` 这一个原语 ——
    ★ **R105 更正**(红队 R104 P25-R104-A):原写「`Return` / `Raise`」,
    但实现**只查 `ast.Return`**。R104 改了同一 docstring 的**首句**却漏了**这一句**,
    造成同一 docstring **自相矛盾** —— 红队原话:「**逐处替换 ≠ 逐类替换**」。
    把整个函数体换成 `pass` + 模块级 monkey-patch、或 `os._exit(0)` / `sys.exit()` / 死循环
    仍能绕过。**第十六次「补一格」。**
    """
    out = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name in names:
            for stmt in node.body[:-1]:
                #   ⚠ 只查 `Return`,**不查 `Raise`** —— 这两个 helper 体内**有护栏 `raise`**
                #   (`RuntimeError("找不到 …")`),把它也算进来会**假红**(第一版实测命中
                #   `['_pre_registered_ints']`)。R85 那条先例查 `Return`+`Raise`,是因为
                #   `test_*` 方法体内没有护栏 raise。
                if any(isinstance(x, ast.Return) for x in ast.walk(stmt)):
                    out.append(node.name)
                    break
    return out


def _pre_registered_ints():
    """从 `tests/pre_registered.py` 的**文本**里取出**全部**顶层整数常量(不 import)。

    ★★★ Round 95(红队 P15-R94-D【中】):R94 只把 `SELFTEST_CHECKS` 一个常量接到跨文件对拍上,
    红队实测另外 **4 个**(`SUITE_TESTS` / `HARNESS_TESTS` / `SUITE_FILES` /
    `TOTAL_ASSERTIONS_FLOOR`)改掉后 harness **`rc=0 [ok]` 零反应** ——
    **「补一格」不是「堵一类」**。本条改成读**全部**顶层整数常量,由调用点逐个对拍。
    ⚠ 边界:正则只认「顶层 `NAME = <整数>`」;`12 + 1` / `0x0d` / `int("13")` / 缩进
    都**读不到** ⇒ 返回的字典里缺那个键 ⇒ **fail-closed**(判据红)。
    ⚠ 但**末位诱饵**(在文件**后面**插一行同名赋值)仍能骗过 —— 见 P15-R94-C,未修。
    ★ R103:此处原写「**首匹配**诱饵」(红队 R97 P18-R97-H(a) 报 doc≠实现)。
    实测实现是 **dict 推导 = 末位胜出**(`{m.group(1): ... for m in re.finditer(...)}`),
    所以能骗过它的是**末位**诱饵,**不是**首匹配 —— 原文说法与实现**相反**。
    **第十五次「补一格」。**
    """
    p = REPO / PRE_REG_REL
    if not p.is_file():
        raise RuntimeError(f"找不到 {p} —— 「没看」!=「没问题」")
    return {m.group(1): int(m.group(2))
            for m in re.finditer(r"^([A-Z_]+) = (\d+)\s*$",
                                 p.read_text(encoding="utf-8"), re.M)}


def _code_side_pre_registered():
    """代码侧那 5 个常量的**真值**(动态算出来,不抄字面量)。"""
    th = (REPO / HARNESS_TEST_REL).read_text(encoding="utf-8")
    m = re.search(r"^MIN_TOTAL_ASSERTIONS = (\d+)\s*$", th, re.M)
    return {
        "SUITE_TESTS": EXPECT_TESTS,
        "SELFTEST_CHECKS": SELFTEST_CHECKS,
        "HARNESS_TESTS": len(re.findall(r"^    def test_H", th, re.M)),
        # ⚠ R95 第 2 轮(红队 P16-R95-A【高】):口径必须是 **`scripts.test`** ——
        #   扫**整份** package.json 会把 `scripts["test:mutation"]` 的
        #   `tests/mutate_guardrails.py` 也算进来(它不匹配 `test_*.py`,是**另一个** 36)。
        #   四个口径(PR 注释 / TH 唯一消费者 / G1 两处)一致 = **36**
        #   ⚠ 2026-10-06 35 → 36:接线 `tests/test_boundary_check.py` 后 `scripts.test`
        #     的真实计数变了(算法口径未动)。同批须同步 H9 变异锚点(TH:434),
        #     否则 H9 走 STALE 提前返回、静默退化成空转(见 P16-R95-B)。
        "SUITE_FILES": len(set(re.findall(r"python\s+(tests/[A-Za-z0-9_]+\.py)",
                                          json.loads((REPO / "package.json").read_text(encoding="utf-8")
                                                     )["scripts"]["test"]))),
        "TOTAL_ASSERTIONS_FLOOR": int(m.group(1)) if m else None,
    }


def _pre_registered_int(name):
    """从 `tests/pre_registered.py` 的**文本**里取出一个顶层整数常量(不 import)。

    ★★★ Round 94(红队 P14-R93-D【低】):`_selftest()` 只对 `MH.SELFTEST_CHECKS` 判,
    **不读预注册文件里的对应常量** ⇒ 把 PR 侧单独改掉,harness **`rc=0 [ok]` 零反应**;
    唯一守卫是 H5 的 `assertEqual(MH, PR)`,而 H5 要 **81.7s** 才跑。
    本条把「两个常量必须相等」也搬到**跨文件**执行点上(仿照 `_pre_registered_files()`)。
    ⚠ 边界:正则只认「顶层 `NAME = <整数>`」;把它改成从别处算出来的值就绕过了。
    **第十四次「补一格」。**
    """
    p = REPO / PRE_REG_REL
    if not p.is_file():
        raise RuntimeError(f"找不到 {p} —— 「没看」!=「没问题」")
    m = re.search(rf"^{re.escape(name)} = (\d+)\s*$",
                  p.read_text(encoding="utf-8"), re.M)
    return int(m.group(1)) if m else None


def _harness_src():
    """`tests/test_mutation_harness.py` 的源码。

    ⚠ **路径护栏用 `raise` 不用 `assert`**(`python -O` 会剥掉 `assert`)。
    ⚠ 文件不存在时**必须抛** —— 返回空串会让判据「没看」而看起来「没问题」
    (本仓已记:「`silent == {}` 对空字典也成立」)。
    """
    p = pathlib.Path(__file__).resolve().parents[1] / "tests" / "test_mutation_harness.py"
    if not p.is_file():
        raise RuntimeError(f"找不到 {p} —— 判据无从谈起(「没看」!=「没问题」)")
    return p.read_text(encoding="utf-8")


def _methods_without_assertions(src):
    """AST:方法体内**没有任何 `self.assert*` 调用**的 `test_*` 方法名。

    ★★★ Round 85 第 2 轮(红队 P6-R85-B【高】):`_early_exit_methods` 只查
    **控制流原语**(`Return`/`Raise`),**完全不看断言是否存在** ——
    红队实测:把 H5 的方法体换成 `pass`(护栏保留、`SKIP_ALLOWED` 不腐烂)
    ⇒ H5 / H6 / `test_no_silent_skips` / `test_meta_criteria_bind_to_names` **全绿**,
    **七条棘轮静默失效,而成本是 0 个短路原语**。
    本条从**断言存在性**这一面查,与上一条互补。

    ⚠ **边界(如实声明)**:它数的是**源码里有没有** `self.assert*` 调用 ——
    把条件阉成 `True, True`(红队 C5)断言**仍在**,本条**看不见**;
    而 `_early_exit_methods` 那条也看不见 ⇒ 两条合起来仍挡不住「阉条件」。
    **第十一次「补一格」**,靠大 diff 评审(⚠ **本仓当前无此控制** —— 5 个自守链文件未被 git 跟踪,`git diff` 无输出)补位。
    """
    out = []
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.FunctionDef) and node.name.startswith("test_")):
            continue
        n = 0
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                f = sub.func
                if (isinstance(f, ast.Attribute) and f.attr.startswith("assert")
                        and isinstance(f.value, ast.Name) and f.value.id == "self"):
                    n += 1
        if n == 0:
            out.append(node.name)
    return out


def _selftest_check_kinds(src=None):
    """返回 `_selftest()` 里每个 `_check` 调用**第一个参数**的形态名。

    ★★★ Round 84(红队 R82 P2-R82-A【高】):**纯计数守卫防「删」不防「阉」。**
    把某条 `_check` 的条件改成 `True`,`SELFTEST_CHECKS_RUN` 仍是满条数,
    ⚠ **R104 更正**(红队 R103 P24-R103-G):原写「仍是 6 条」,实测 = **14**
    (= `SELFTEST_CHECKS`)。
    `len(...) == SELFTEST_CHECKS` 照样过 ⇒ **全绿**,而判据已恒真失效。
    R84 Step 2 实测:阉变异 `python tools/mutation_harness.py` → **`rc=0`**,
    且打印与基线**逐字相同**的 `[ok] selftest: ... matches the real suite` —— **假话**。

    ⚠ **文件内无法防住这件事**:`lambda: True` 与 `lambda: cond` 在外部不可区分。
    故判据放在**结构层**(AST):要求每条判据是**比较表达式**,且**操作数不得全是字面量**
    (`True == True` / `len([]) == 0` 这类恒真式当场红 —— 红队 P5-R84-A 实测的形态)。

    ⚠⚠ **这是本仓「补一格 ≠ 堵住」的第九次实例,边界如实声明:**
    它挡的是**结构可判**的恒真式。写成 `hash("x") == hash("x")`
    (`hash` 不在 `_is_literalish` 白名单里)仍能绕过 ——
    与 C14「输出伪造类边界」同族,**靠大 diff 评审(⚠ **本仓当前无此控制** —— 5 个自守链文件未被 git 跟踪,`git diff` 无输出)补位,判据补不了**。
    ★ **R107 补回**(红队 R106 P27-R106-A):R105 手工删行时**误删了「,判据补不了**」** —— 原文见 R104 冻结副本。
    ⚠ 而且第 ① 条之所以曾被拦,靠的是 `test_H8` 里**硬编码的变异锚**
    (红队 P5-R84-C 指出)—— 那是副作用,不是本判据的功劳;H8 的锚数**等于 `SELFTEST_CHECKS - 1`**(现为 **13** 条),每锚 **3** 档。
    ⚠ **R104 更正**(红队 R103 P24-R103-E):原写「6 条锚 × 3 档」是 R84 的旧数,
    与 TH 里被 R103 修掉的「18 处」**同源** —— R103 只修了 TH、**漏修此处**。

    `src` 供 `test_H8` 直接喂变异体文本(**不加载副本模块**,避免「同一份 payload 抄两份」)。
    """
    tree = ast.parse(src if src is not None
                     else pathlib.Path(__file__).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_selftest")
    out = []
    for c in ast.walk(fn):
        if not (isinstance(c, ast.Call) and getattr(c.func, "id", "") == "_check"):
            continue
        a = c.args[0]
        # 结构判据**自己**那条不算 —— 它的第一个参数形如
        # `_selftest_check_kinds() == [...]`,是 `Compare` 而**不是** `Call`,
        # 所以要按**左操作数**识别(否则它会被自己算进去,当场误红)。
        if (isinstance(a, ast.Compare)
                and isinstance(a.left, ast.Call)
                and getattr(a.left.func, "id", "").startswith("_selftest_check")):
            continue
        out.append(_kind_of(a))
    return out


def _selftest():
    """判据自检:语法错误必须被判成**崩溃**,绝不能算检出。

    ★★ Round 80(红队 R79 N3):**新增第 ⑤ 条 —— `EXPECT_TESTS` 必须与真套件对拍。**
      红队把 `EXPECT_TESTS` 改成 24(真实 25),自检**照样通过**,而此后框架
      对**一切**变异报「崩溃」= 静默失效。根因:自检里的 25 是**字面量**。
      修:自检**实跑未变异的真套件**取 `Ran N`,与常量对拍 —— 常量漂移当场红。
    """
    # ★ R82:计数表**每次调用清零** —— 否则跨调用累积,条数守卫第 2 次就误判。
    SELFTEST_CHECKS_RUN.clear()
    work = pathlib.Path(tempfile.mkdtemp(prefix="jev_selftest_"))
    try:
        (work / "tools").mkdir(parents=True)
        (work / "tests").mkdir(parents=True)
        (work / "tools" / "x.py").write_text("def f(:\n", encoding="utf-8")
        (work / "tests" / "t.py").write_text(
            "import unittest,subprocess,sys\n"
            "class T(unittest.TestCase):\n"
            "    def test_a(self):\n"
            "        r=subprocess.run([sys.executable,'tools/x.py'],capture_output=True,text=True)\n"
            "        self.assertEqual(r.returncode,0)\n"
            "unittest.main()\n", encoding="utf-8")
        r = subprocess.run([sys.executable, "-X", "utf8", "-B", "tests/t.py"],
                           cwd=str(work), capture_output=True, text=True, timeout=300)
        blob = (r.stdout or "") + (r.stderr or "")
        # ★★★ Round 81(红队 R80 P2-R80-1【高】):**这 5 条原来全是裸 `assert`** ——
        #   `python -O` 下**全部消失**,自检空转,还**主动打印「[ok] …」这句假话**。
        #   红队实测:`EXPECT_TESTS=24` + `-O` → **`exit=0`** 且输出
        #   `matches the real suite`;非 `-O` 同输入 → `exit=1`。
        #   R80 我只修了 `run_case` 的**路径护栏**,漏了**同一文件里这 5 条判据自检**。
        #   ⇒ 一律改 `_check()`(显式 raise,`-O` 剥不掉)。
        # ① 前提:裸分类器(不校验测试数)会把它误判成「真检出」
        naive, _ = classify(r.returncode, blob, expect_tests=1)
        _check(naive == DETECTED, f"自检前提变了:裸分类器判成 {naive}")
        # ② 测试数校验必须把它拦成崩溃
        guarded, _ = classify(r.returncode, blob, expect_tests=25)
        _check(guarded == CRASH, f"测试数校验没拦住:判成 {guarded}")
        # ③ 目标预检必须认出语法错误
        _check(target_crashes(work, "tools/x.py") is True, "预检没认出语法错误")
        # ④ ★ R79:预检**不得**对测试文件目标生效(红队 P2-R78-2)
        _check(target_crashes(work, "tests/t.py") is False,
                 "预检对测试文件生效了 —— 那会把真检出改判成崩溃")
        # ⑤ ★★ R80:EXPECT_TESTS 必须与**真套件**对拍(红队 R79 N3)
        real = real_test_count()
        _check(real == EXPECT_TESTS,
                 f"真套件对不上:常量 {EXPECT_TESTS},实测 {real} —— 若为 None 说明**套件没跑绿**"
                 f"框架会对一切变异误报「崩溃」")
        # ★★★ Round 93(红队 P13-R92-A【中】):`real_test_count()` 的契约是 `int | None`,
        #   下面第 ⑥ 条 `real >= MIN_SUITE_TESTS` 是**第二个**消费点,原来只靠第 ⑤ 条先 raise
        #   才不可达 —— 红队删掉 ⑤ 后实测 `rc=1` / **`TypeError`**(崩溃,不是判据红)。
        #   这里显式挡住:用 `is not None`(`Compare`,第 ⑦ 条合规)。
        _check(real is not None,
               f"取不到真套件的 Ran N(实测 {real})—— 套件没跑绿")
        # ⑥ ★★★ R81(红队 R80 P2-R80-3【高】):`real_test_count()` 是
        #   「常量 vs **当前**套件」的**自洽对拍**,不是「vs 预注册下界」——
        #   红队三处自洽下调(删一个用例 + 改 `EXPECTED_TESTS` + 改 `EXPECT_TESTS`)
        #   即可让**五个守卫全绿**。⇒ 再加一条**下界**判据:测试数只许增不许减。
        _check(real >= MIN_SUITE_TESTS,
                 f"套件测试数 {real} < 预注册下界 {MIN_SUITE_TESTS} —— "
                 f"用例被删或被阉(自洽对拍抓不住这个)")
        # ⑦ ★★★ R84(红队 R82 P2-R82-A【高】):**结构判据** —— 上面 `SELFTEST_CHECKS - 1` 条 `_check` 的
#   ⚠ **R104 更正**(红队 R103 P24-R103-G):原写「上面 6 条」;实测 `_selftest()` 内
#   `_check(` 调用点 = **14**(= `SELFTEST_CHECKS`),本条覆盖前 **13** 条。
        #   第一个参数必须是**比较表达式**。纯计数守卫(上一行)防「删」不防「阉」:
        #   把条件改成 `True` 后计数仍是 `SELFTEST_CHECKS`(现为 14),自检全绿
        #   **还打印「matches the real suite」这句假话**
        #   ★ **R105 更正**(红队 R104 P25-R104-A2):原写「仍是 6」,真值 **14**;
        #   同注释块 609-610 已在 R104 改过,本行**漏改**。
        #   (R84 Step 2 实测:阉变异 `rc=0`,输出与基线逐字相同)。
        #   ⚠ 边界:只挡结构可判的阉法;`len([]) == 0` 这类恒真式仍能绕过 —— 靠大 diff 评审(⚠ **本仓当前无此控制** —— 5 个自守链文件未被 git 跟踪,`git diff` 无输出)补位。
        #   ★★★ Round 93 第 2 轮(红队 P14-R93-B【低】,P11-R90-F 同族、**跨 3 轮未修**):
        #   message 原来只报「条件不是比较表达式」,而红队实测 **7 次命中里 6 次**真实原因是
        #   **`_check` 条数 != `SELFTEST_CHECKS - 1`**(删/加了一条判据)⇒ 复算者会按**错误方向**排查。
        #   改成把**两个数**都印出来,让复算者一眼看出是「条数不符」还是「形状不符」。
        _n_kinds = len(_selftest_check_kinds())
        _check(_selftest_check_kinds() == ["Compare"] * (SELFTEST_CHECKS - 1),
                 f"结构判据不符:数到 {_n_kinds} 条 _check 条件,期望 {SELFTEST_CHECKS - 1} 条 —— "
                 f"若两数不等,是**判据被删/被加**(不是形状问题);若两数相等,才是有条件的类型不是 `Compare`")
        _check(_methods_without_assertions(_harness_src())
                 + _early_exit_methods(_harness_src()) == [],
                 "有 test 方法体零断言或含 Return/Raise —— 可被静默掏空")
        # ★★★ Round 88(红队 P8-R87-C【高】剩余部分):把「两个消费点必须用
        #   `PARTICIPATING_FILES`」这条判据**搬出** `tests/test_mutation_harness.py`。
        #   原来它只在 H9 体内 ⇒ 删掉 H9 的行为段就无人抓(C5:H9/H4/H6 全绿)。
        #   ⚠ 与 R85 第 3 轮同法:**执行点跨文件**。
        #   ⚠ 读的是**本文件**(`repo_digest`/`run_case` 住在这里),不是 `_harness_src()`。
        #   ⚠ **单行**条件:多行表达式会被 H8 的变异注入改坏(`IndentationError`)——
        #   本仓记过的「变异锚点铁律:多行表达式的第一物理行不能追加新语句」。
        _targets = _participating_file_targets(pathlib.Path(__file__).read_text(encoding="utf-8"))
        _check(set(sum(_targets.values(), [])) == {"PARTICIPATING_FILES"},
               "repo_digest/run_case 的每个 for iter 都须是 PARTICIPATING_FILES")
        #   ⚠ 两条判据各自**单** `Compare` —— 合成 `and` 会变成 `BoolOp`,被第 ⑦ 条拦下。
        _check(tuple(sorted(_targets)) == ("repo_digest", "run_case"),
               "repo_digest/run_case 两个函数都必须被覆盖")
        # ★★★ Round 88 第 2 轮(红队 P9-R88-B【高】):上面那条只管**消费点**,
        #   **不锚清单内容** —— 红队 C9/C10 实测:两份清单任一份被改,`_selftest` 全绿,
        #   唯一守卫是 H9 ①,而 H9 正住在「要跨出去」的那个文件里。
        #   ⇒ 第 ⑩ 条:**跨文件**读预注册文件里的具名清单,与代码里的逐项对拍。
        _check(_pre_registered_files() == tuple(PARTICIPATING_FILES),
               "预注册文件里的 PARTICIPATING_FILES 与代码里的不一致")
        # ★★★ Round 94(红队 P14-R93-D【低】):**跨文件**对拍 `SELFTEST_CHECKS`。
        #   上面所有条数判据都只锚 `MH.SELFTEST_CHECKS` —— 把 `tests/pre_registered.py` 里
        #   那个同名常量单独改掉,harness **`rc=0 [ok]` 零反应**(红队实测 D4),
        #   唯一守卫是 H5 的 `assertEqual(MH, PR)`,而 H5 要 **81.7s** 才跑。
        #   ⚠ 这是本仓记过的形态:**「同一份常量抄成两份,改一处 != 改一类」**。
        # ★★★ Round 95(红队 P15-R94-D【中】):**从「补一格」改成「堵一类」** ——
        #   R94 只把 `SELFTEST_CHECKS` 一个常量接到跨文件对拍上,红队实测另外 **4 个**
        #   (`SUITE_TESTS` / `HARNESS_TESTS` / `SUITE_FILES` / `TOTAL_ASSERTIONS_FLOOR`)
        #   改掉后 harness **`rc=0 [ok]` 零反应**。本条把**全部 5 个**一起对拍。
        #   ⚠ 条件是**单行**(R94 教训:多行会被 H8 的变异注入改坏 ⇒ IndentationError)。
        _check(_pre_registered_ints() == _code_side_pre_registered(),
               f"预注册常量与代码侧真值不一致:预注册 {_pre_registered_ints()},代码侧 {_code_side_pre_registered()}")
        # ★★★ Round 96(红队 P16-R95-C【高】):上面那条判据的**两个 helper 自身零守卫** ——
        #   在任一体内**插 1 行 `return ...`**,整条对拍立刻退化成恒真式,harness `rc=0 [ok]` 无人抓。
        #   第 ⑦ 条只查 `_check` **第一参数的形状**,**不查被调函数的实现**。
        #   ⚠ 这是 **R94 的 P15-R94-B 同族** ⇒ **「补一格」→「换个格子补一格」**。
        #   ⚠ 条件是**单行**(R94 教训)。
        #   ⚠ `_harness_src()` 读的是 **`tests/test_mutation_harness.py`**,不是本文件 ——
        #   第一版用它查本文件的 helper ⇒ 永远返回 `[]`(「没看」被当成「没问题」)。
        _check(_early_return_funcs(_self_src(), ("_pre_registered_ints", "_code_side_pre_registered")) == [],
               f"这两个 helper 的体内有提前 return/raise,整条对拍会退化成恒真式:{_early_return_funcs(_self_src(), ('_pre_registered_ints', '_code_side_pre_registered'))}")
        # ★★ 注意:第 ⑧ 条的**执行点不在 `tests/test_mutation_harness.py` 里** ——
        #   它在**本文件**。这是有意为之(红队 P6-R85-A【高】):H6 体内那条 AST 判据
        #   只有 1 个执行点,在它**之前**插 1 行 `return` 或把实现改成 `return []`
        #   就整体失效、无人兜底。搬到本文件后,绕它必须**跨文件**改动。
        # ★★ Round 80:`_selftest()` 是**库函数** —— 被 `tests/` 调用时**入口 bootstrap 不生效**,
        #   而 stdout 被重定向时是 **gbk**。红队同族缺陷(R50)。故这里**只用 ASCII**:
        #   实测 `print("✓ ...")` 在 `npm test` 下抛 `UnicodeEncodeError: 'gbk' codec
        #   can't encode character '\u2713'` —— 而单独跑(控制台 UTF-8)看不出来。
        # ★★★ R82(红队 R81 P2-R81-A):**条数守卫** —— 删掉任意几条判据,这里会红。
        _require(len(SELFTEST_CHECKS_RUN) == SELFTEST_CHECKS,
                 f"自检只跑了 {len(SELFTEST_CHECKS_RUN)} 条判据,期望 {SELFTEST_CHECKS} 条 "
                 f"—— 有判据被删掉而无人看见")
        print("[ok] selftest: syntax error => CRASH; test-count mismatch => CRASH; "
              f"precheck does not misfire on tests/; EXPECT_TESTS={EXPECT_TESTS} "
              f"matches the real suite; >= {MIN_SUITE_TESTS} floor")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    # ⚠ 入口必须挂 UTF-8 bootstrap:本机 `sys.stdout.encoding` 是 **gbk**,
    # 直接打印中文,一旦 stdout 被重定向就是 GBK 字节(第三方复算会看到乱码)。
    # 本文件**建好当天就被 `tests/test_tool_stdout_encoding.py::T3` 抓到** ——
    # 那条棘轮判据按**缺陷类别**扫 `tools/`,不按「这个文件是不是我刚写的」。
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    # ★★★ Round 97(红队 P17-R96-D【中】/ P10-R89-F【低】):**`rc=0` 且零输出 = 假绿。**
    #   在 `_selftest()` 体内插 1 行 `raise SystemExit(0)`,或整个文件首行 `os._exit(0)`,
    #   harness 都会以 **`rc=0`、stdout/stderr 全空** 退出(红队 S9 实测 tail 为空)——
    #   **只看退出码的调用方会把「根本没跑」判成「通过」**。
    #   本仓记过的形态:「**「没看」!=「没问题」**」「**`silent == {}` 对空字典也成立**」。
    #   修法:挂 `atexit` 哨兵 —— 只有 `_selftest()` **正常返回**才置位;
    #   `raise SystemExit(0)` / `sys.exit(0)` 会**触发** `atexit` ⇒ 未置位 ⇒ `os._exit(1)`。
    #   ⚠ **边界(如实声明)**:`os._exit(0)` **不触发** `atexit` ⇒ 仍能绕过(见 P10-R89-B,
    #   本仓登记为**仓内无解**,需人工拍板)。死循环也不触发 ⇒ 挂死。
    #   ⚠ 这是「补一格」的**第十七次** —— 它只堵住「**`atexit` 会跑**」这一族短路原语。
    _ran = {"ok": False}

    def _no_silent_exit():
        if not _ran["ok"]:
            sys.stderr.write("[FAIL] selftest 未跑完就退出 —— 拒绝静默通过\n")
            sys.stderr.flush()
            os._exit(1)

    atexit.register(_no_silent_exit)
    _selftest()
    _ran["ok"] = True
    sys.exit(0)
