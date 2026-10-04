"""Round 59:重复字典键守卫。

Python 对 `{'a': 1, 'a': 2}` **不报错**:后者静默覆盖前者 ——
一次「看起来生效了」的修改实际无效,且**没有任何信号**。

现场:`benchmarks/accuracy/jevbench/grading.py` 的 `compare()` 返回值里,
`n11/n10/n01/n00/agreement/n_gate_excluded` 六个键被写了两次
(两次的值恰好相同,所以**当时没有行为差异** —— 但下一次有人只改第一处就会静默失效)。
删除后经 7 场景 × 双版本逐键对比,返回值**逐键相同**(红队 `jev_path2_r59` 独立复算确认)。

⚠ **覆盖范围(如实声明,不夸大)**

**覆盖** —— `ast.Dict` 字面量里**可静态求值**的键:
- 常量(`'a'` / `1` / `b'a'` / `None` …),按**运行时同一性**判重
  (`{1:…, 1.0:…}` 与 `{True:…, 1:…}` 是**同一个键**,`repr` 判不出来)
- 元组字面量、一元负号、常量表达式(`ast.literal_eval` 可求值的)
- 无占位符的 f-string(`f'x'` ≡ `'x'`)
- `**` 展开的**内层字面量** dict(递归;`{'a':1, **{'a':2}}` 是真重复)

**不覆盖**(由 `D6` 特征化钉住 —— 谁把它们修好了 D6 会红,提醒同步本文档):
- **变量键**:`k='a'; {k:1, 'a':2}` —— 需要数据流分析,静态不可判
- **`dict()` 调用族**:`dict(a=1, **{'a':2})` —— 且它在 CPython 里是 **TypeError**,
  不是静默覆盖,危害等级不同
- **数据层**:`json.loads('{"a":1,"a":2}')` —— 重复发生在字符串常量里,AST 层面看不见
"""

import ast
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _fs_guard as fsg  # noqa: E402  —— 共享的「不走出仓根」原语(Round 66)
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist",
             # ⚠ Round 65:D2 新加的「逐目录」检查**当场抓到** —— 本扫描器把仓内一个
             # **临时目录**(43 个 .py,占遍历数 34%)当成契约范围扫了进去,而兄弟守卫
             # `test_no_encoding_damage.py` 的 `EXCLUDE_DIRS` **早已排除它**。
             # 两个扫描器口径不一致 = **幽灵覆盖**:数字虚高,`>= 100` 这类下界更松。
             # 排除**不等于删除**(删除需人工拍板)。
             "tmp_jev_path1"}
#: ⚠ **排除清单 = 移动即消音**(Round 65 红队实测的固有权衡,明写在此):
#: ① 把文件**搬进**被排除目录 → 扫描不到它、`hits == []`、守卫判绿。
#:    守卫只防「整个目录消失」,防不了「文件搬进排除目录」。任何排除清单都有这个洞。
#: ② 匹配口径是**部件匹配**(`any(part in SKIP_DIRS for part in p.parts)`)——
#:    **有意**如此:任何深度的 `build/` / `dist/` / `__pycache__/` 都不是契约源。
#:    代价是仓内**深处**出现同名目录时会被静默排除,而 D2 只看**顶层**目录名、看不见它。
#: 两条都**不靠代码兜底**,靠人工纪律 + 大 diff 评审(⚠ **本仓当前无此控制** —— 5 个自守链文件未被 git 跟踪,`git diff` 无输出)补位。

#: 仓内**含 Python 源**的顶层目录 —— **具名清单**,不是数量下界(见 D2)。
#: ⚠ 写死的**身份**不会随仓增长过期;写死的**数字**会(Round 64 刚吃过一次)。
SOURCE_DIRS = ("benchmarks", "packages", "tests", "tools")


def assert_scan_covers_source_dirs(case, rels):
    """**反空转守卫**:扫描必须遍历到**该在的每一个目录**。

    ⚠ Round 65:口径从「数量下界 100(真实 126,余量 21%)+ 单个具名文件名」
    改成「**具名目录清单全覆盖**」。旧口径实测的洞:剔掉 `packages/`(7 个源)
    或 `tools/`(3 个源)后总数仍 ≥ 100 → **判绿** —— 那两个目录对守卫是
    **零覆盖**的。**数量下界只能证明「扫到了东西」,证明不了「扫到了该扫的东西」。**

    抽成函数是为了让它**可证伪**(D2 逐目录剔掉后调它,必须抛)。
    """
    dirs = {r.split(os.sep)[0] for r in rels}
    case.assertEqual(
        [d for d in SOURCE_DIRS if d not in dirs], [],
        f"扫描范围里缺这些目录 —— 该目录下的源不会被检查:"
        f"应有 {list(SOURCE_DIRS)},实到 {sorted(dirs)}")


def _joined_str_value(node):
    """无占位符的 f-string → 它的字面值;含占位符则返回 None(不可静态求值)。"""
    parts = []
    for v in node.values:
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            parts.append(v.value)
        else:
            return None
    return "".join(parts)


def _key_id(k):
    """把键节点映射成「运行时同一性」的标识;不可静态求值时返回 None。

    ⚠ **不能用 `repr` 判重**:`repr(1) == '1'` 而 `repr(1.0) == '1.0'`,
    但运行时 `{1: 'a', 1.0: 'b'}` 只有**一个**键 —— `1 == 1.0` 且 `hash` 相同。
    `{True: 'a', 1: 'b'}` 同理。所以直接用**值本身**:dict 的语义就是 `==` / `hash`。
    """
    if isinstance(k, ast.Constant):
        v = k.value
    elif isinstance(k, ast.JoinedStr):
        v = _joined_str_value(k)
        if v is None:
            return None
    elif isinstance(k, (ast.Tuple, ast.UnaryOp, ast.BinOp)):
        try:
            v = ast.literal_eval(k)
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
            return None
    else:
        return None
    try:
        hash(v)
    except TypeError:
        return None
    return v


def _collect(node, seen, out):
    """递归收集一个 Dict 字面量里的键;`**` 展开若是字面量则一并展开。"""
    for k, v in zip(node.keys, node.values):
        if k is None:                      # `**value`
            if isinstance(v, ast.Dict):
                _collect(v, seen, out)     # 内层字面量:合并时键会真正参与
            continue
        r = _key_id(k)
        if r is None:
            continue
        if r in seen:
            out.append((r, k.lineno, seen[r]))
        else:
            seen[r] = k.lineno


def scan_source(src, name="<src>"):
    """返回 [(键, 行号, 首次出现行号)],对给定源码做 AST 扫描。"""
    tree = ast.parse(src, filename=name)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            _collect(node, {}, out)
    return out


def iter_py_files(root):
    r"""遍历 `root` 下所有 `.py`(**不走出仓根** —— junction 是逃逸口,见 D8)。

    ⚠ Round 66 从 `root.rglob("*.py")` 改成 `os.walk` + `_fs_guard.prune_escaped`:
    `rglob` **跟随 junction**(`os.path.islink` 对 junction 是 `False`,
    `followlinks=False` 也管不到)→ 仓外文件被拉进扫描范围。
    改成 `os.walk` 是为了能在**进入前**剪枝,并与 `tests/test_no_encoding_damage.py` 的
    `scan_syntax_warnings` **同一形状**(单一原语,三个调用点)。

    ⚠ **不是**为了「防成环挂死」—— 那条动机**已被实测证伪**(Round 66 红队:
    Windows 内核对单条路径的 reparse 解析上限 32 次 → `ERROR_CANT_RESOLVE_FILENAME`,
    `walk`/`rglob` 都**默认吞错** → **有限终止**,不挂死)。理由只有**越界**一条。

    ⚠ 后缀比较用 `.lower()`,与 `rglob("*.py")` 在 Windows 上的**大小写不敏感**
    语义保持一致 —— 否则 `SHADOW.PY` 会从覆盖里静默消失(Round 63 记过这条)。
    """
    real_root = os.path.realpath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        fsg.prune_escaped(dirpath, dirnames, real_root)
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fn in sorted(filenames):
            if fn.lower().endswith(".py"):
                yield pathlib.Path(dirpath) / fn


class TestNoDuplicateDictKeys(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix=f"jev_r59_dup_{os.getpid()}_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    # D1 全仓真实扫描:不得有重复字典键
    def test_D1_no_duplicate_keys_in_repo(self):
        hits = []
        for p in iter_py_files(REPO):
            try:
                src = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            try:
                found = scan_source(src, str(p))
            except SyntaxError as e:
                hits.append(f"{p.relative_to(REPO)}: 解析失败 {e}")
                continue
            for key, ln, first in found:
                hits.append(f"{p.relative_to(REPO)}:{ln}  重复字典键 {key!r}(首次在 L{first})")
        self.assertEqual(hits, [], "以下文件有重复字典键(后者会静默覆盖前者):\n" + "\n".join(hits))

    # D2 空转守卫:扫描器必须真的扫到了**该扫的每一个目录** ——
    # 否则 D1 会因为「扫了 0 个文件」或「漏了一个目录」而恒真。
    # ⚠ Round 65 改口径(旧口径的洞见 `assert_scan_covers_source_dirs` 的 docstring)。
    def test_D2_scanner_actually_scanned_files(self):
        files = list(iter_py_files(REPO))
        rels = [str(p.relative_to(REPO)) for p in files]
        assert_scan_covers_source_dirs(self, rels)
        names = {p.name for p in files}
        self.assertIn("grading.py", names, "扫描范围里没有 grading.py —— 路径规则可能坏了")
        # 可证伪:逐个**真实出现**的目录剔掉后,守卫必须报红 ——
        # 「少一个目录」这条子判据如果对某个目录没有独立样本触发它,就是零覆盖。
        # ⚠ 遍历对象必须是**扫描结果里的真实目录**,不能是 `SOURCE_DIRS` 自己:
        # 否则 `SOURCE_DIRS` 缩水时循环跟着缩水,判据**自锚定到被守卫对象** ——
        # 表现为「漏检」(Round 65 变异 O-4 实测:把 `SOURCE_DIRS` 改成 `("tests",)`
        # 后 D2 仍全绿)。**判据的样本必须来自被测对象之外。**
        real_dirs = sorted({r.split(os.sep)[0] for r in rels})
        self.assertGreaterEqual(len(real_dirs), 2,
                                f"真实仓的顶层源目录只有 {real_dirs} —— 样本没构造出来")
        for victim in real_dirs:
            partial = [r for r in rels if r.split(os.sep)[0] != victim]
            self.assertLess(len(partial), len(rels), f"剔掉 {victim} 没生效")
            with self.assertRaises(
                    AssertionError,
                    msg=f"剔掉 {victim}/ 后守卫仍判绿 —— 该目录对守卫是零覆盖的"):
                assert_scan_covers_source_dirs(self, partial)

    # D3 可证伪:造含重复键的文件,扫描器必须报出来
    def test_D3_falsifiable(self):
        cases = [
            ("D = {'a': 1, 'b': 2, 'a': 3}\n", 1, "同字面量重复"),
            ("D = {1: 'a', 1.0: 'b'}\n", 1, "int 与 float 运行时同键"),
            ("D = {True: 'a', 1: 'b'}\n", 1, "bool 与 int 运行时同键"),
            ("D = {0: 'a', False: 'b'}\n", 1, "0 与 False 运行时同键"),
            ("D = {('a', 1): 'x', ('a', 1): 'y'}\n", 1, "元组字面量键重复"),
            ("D = {f'x': 1, 'x': 2}\n", 1, "无占位 f-string 与同值字符串"),
            ("D = {-1: 'a', -1: 'b'}\n", 1, "一元负号键重复"),
            ("D = {'a': 1, **{'a': 2}}\n", 1, "** 展开内层字面量与显式键冲突"),
            ("d1 = {'a': 1}\nd2 = {'a': 2}\nD = {**d1, **d2}\n", 0, "变量展开(静态不可判)不得误报"),
            ("D = {'a': 1, 'b': 2}\n", 0, "合法文件不得误报"),
            ("D = {1: 'a', 2.0: 'b'}\n", 0, "1 与 2.0 不同键,不得误报"),
        ]
        for src, want, why in cases:
            f = self.tmp / "case.py"
            f.write_text(src, encoding="utf-8")
            found = scan_source(src, str(f))
            self.assertEqual(len(found), want, f"{why}: {src!r} -> {found}")

    # D4 变量键 / 变量展开不应误报
    def test_D4_non_constant_keys_are_ignored(self):
        src = "def f(kw, k):\n    return {'a': 1, **kw, 'b': 2, k: 3}\n"
        self.assertEqual(scan_source(src), [], "变量键与变量展开不应参与判重")

    # D5 元判据:用例**具名清单**(不是计数),防「静默删掉一条」**与「改名」**
    # ⚠ 只数**类上**的方法 —— 用 `dir(self)` 会把 setUp 里 `self.test_xxx = 1`
    #    这类**实例属性**也算进去,导致计数虚高而误报(红队实测 loaded=6 vs 5)。
    # ⚠ 数字换成名字(Round 64):数字抓不住「改名」—— `test_X` 改成另一个
    #    `test_` 开头的名字,计数不变、判据全绿,而被保护的用例已经消失。
    def test_D5_case_count(self):
        loaded = sorted(n for n in dir(type(self)) if n.startswith("test_"))
        self.assertEqual(loaded, sorted(CASE_NAMES),
                         "用例集变了 —— 删 / 改名 / 新增用例都必须同步改 CASE_NAMES 并说明原因")

    # D6 特征化:已知盲区必须显式钉住,不许沉默
    def test_D6_known_blind_spots_are_documented(self):
        blind = [
            ("k = 'a'\nD = {k: 1, 'a': 2}\n", "变量键"),
            ("D = dict(a=1, **{'a': 2})\n", "dict() 调用族"),
            ("import json\nD = json.loads('{\"a\": 1, \"a\": 2}')\n", "数据层 JSON"),
        ]
        for src, why in blind:
            self.assertEqual(scan_source(src), [],
                             f"{why} 现在被覆盖了?请同步本文件 docstring 与 docs/ 记账")

    # D7 元判据:本文件自身必须能通过自己的扫描(否则「用违规代码守规矩」)
    def test_D7_self_scan_is_clean(self):
        me = pathlib.Path(__file__).read_text(encoding="utf-8")
        self.assertEqual(scan_source(me, __file__), [], "本测试文件自己就有重复字典键")

    # D8 扫描范围不得走出仓根 —— junction 是逃逸口(Round 66)
    def test_D8_scan_does_not_escape_repo_via_junction(self):
        r"""D8:`iter_py_files` 不得跟随 junction 把**仓外**文件拉进扫描范围。

        ⚠ Round 63 在兄弟文件 `tests/test_no_encoding_damage.py` 的
        `scan_syntax_warnings` 上发现过同一个洞并**只在那一个函数里**修掉;
        Round 65 红队复算时实测:**这里照样跟随**(本仓记过两次的失败形态
        「**按目录 / 按函数而非按缺陷类别划修复范围**」的第三次复发)。

        现场:`os.path.islink(junction)` 是 **`False`**,
        `pathlib.Path.rglob` 与 `os.walk(followlinks=False)` **都管不到它** ——
        唯一可靠判据是 `os.path.realpath` 是否还在仓根之内。
        """
        lab, _ = fsg.make_junction_lab(self, prefix="jev_d8_")
        rels = sorted(str(p.relative_to(lab)) for p in iter_py_files(lab))
        self.assertEqual(
            [r for r in rels if fsg.JUNCTION_NAME in r], [],
            f"`iter_py_files` 跟随 junction 把**仓外**文件拉进了扫描范围:{rels}")
        # 可证伪:扫描器必须**确实**扫到了仓内文件,否则上面那句在空集上恒真
        self.assertIn(os.path.join("tests", "b.py"), rels, "扫描器没扫到仓内文件")
        # 可证伪:**大小写不敏感**这条加固也要有样本 —— 仓内没有 `*.PY` 文件,
        # 实验场里有;把 `.lower()` 去掉会**静默**丢掉它(Round 63 的教训)。
        self.assertIn(os.path.join("tests", "SHADOW.PY"), rels,
                      "大写后缀的 `.PY` 源没被遍历到 —— 后缀比较丢了大小写不敏感")


#: 本文件的用例**具名清单**(不是计数)。⚠ 名字而非数字 —— 数字抓不住「改名」。
CASE_NAMES = (
    "test_D1_no_duplicate_keys_in_repo",
    "test_D2_scanner_actually_scanned_files",
    "test_D3_falsifiable",
    "test_D4_non_constant_keys_are_ignored",
    "test_D5_case_count",
    "test_D6_known_blind_spots_are_documented",
    "test_D7_self_scan_is_clean",
    "test_D8_scan_does_not_escape_repo_via_junction",
)

if __name__ == "__main__":
    unittest.main()
