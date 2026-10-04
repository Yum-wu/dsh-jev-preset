# -*- coding: utf-8 -*-
r"""元判据:全仓**递归遍历器**必须都做「不走出仓根」剪枝(Round 67)。

## 为什么需要这条(Round 63 → 66 → 67 的三次复发)

* Round 63 在 `tests/test_no_encoding_damage.py` 的 `scan_syntax_warnings` 上发现
  **junction 逃逸**并**只在那一个函数里**修了;
* Round 66 抽了 `tests/_fs_guard.py` 做**单一定义**,改了三个 `.py` 扫描器 ——
  但仍**漏了 `.md` 扫描器**(`tests/test_markdown_tables.py`)与审计脚本
  (`tools/_wilson_doc_scan.py`);
* Round 67 用 **AST 普查**才发现这两个:单点读代码**看不见**它们。

**结论:靠「这一轮记得多查几个文件」永远会漏。** 唯一的堵法是让「有没有剪枝」
成为一个**机械可判**的性质 —— 本文件就是那个判据。

## 判据

  W1 **具名清单精确相等**:全仓 `os.walk` / `rglob` / `glob(..., recursive=True)`
     的调用点集合必须**恰好等于** `WALKERS`,且每一个都有**结构性**剪枝。
     ⚠ 用**身份**(file::function)而不是**数量下界** —— Round 65 的教训。
     ⚠ `WALKERS` 是**手写清单**,不从扫描结果派生 —— Round 65 的「锚点同源」教训。
  W2 可证伪:喂合成源码,「没剪枝」判没剪、「真剪枝」判剪。
  W3 元判据:用例具名清单。
  W4 **非递归** `glob.glob('*.jsonl')`(无 `**`)不得被误报。
  W5 **绕过面**:五种「看起来有剪枝、实际没剪」的写法必须**全判为没剪**。
  W6 别名 import(`import os as o` / `from os import walk`)的遍历器必须被认出来。

## ⚠ 「有剪枝」是**结构比对**,不是子串匹配(Round 67 红队实测)

初版写的是 `any("prune_escaped" in c for c in calls)` —— **子串匹配**。
红队用**一行代码**绕过:同一函数里定义并调用 `def prune_escaped_fake(...): pass`,
子串命中,判「有剪枝」。**这正是 Round 50 记过的「白名单按文本片段匹配 → 可换靶」。**
红队还给了**闭环演示**:W1 判 `('os.walk', True)`,同一逻辑的真实 junction 实验
把仓外 `docs\jlink\evil.md` 拉进了扫描 —— **判绿但实际越界**。

现在要求**同时**满足四条,缺一即红(W5 逐条钉住):

1. 被调函数的属性名**精确等于** `prune_escaped`(不是含子串);
2. 该调用在**该遍历器的 `for` 循环体内**(循环外调一次不算);
3. 第 2 个位置实参**就是该循环的 dirnames 变量**(传别的 → 改不到 `dirnames`);
4. 第 3 个位置实参是**该循环那个 root 的 `realpath`**(宽一级 → `inside` 恒真 → 空转)。

第 3 条是语义核心之一:`prune_escaped(dirpath, dirnames, root_real)` 之所以能剪,
靠的是**原地改写 `dirnames`**;实参传错时函数跑了但**一个子目录都没剪**。

⚠ 第 4 条是**红队绕过 5 逼出来的,而且当场暴露了我自己的一个真 bug**:我在
`tools/_wilson_doc_scan.py` 里 walk 根是 `base`,却传 `os.path.realpath(ROOT)` ——
`inside()` 对 `base` 下的一切恒真 → **剪枝完全空转**。红队的绕过形状
(`realpath(dirname(root))`)与我的 bug **同构**。**「空转判据」:判据看似在守,
实则对被守对象零输入 → 恒绿。**

## 已知边界(如实声明)

* **别名 import 已支持**:`import os as o` → `o.walk`、`from os import walk` → `walk(...)`
  都能解析(经 `ast.Import` / `ast.ImportFrom` 建名字映射)。初版**不认**这两类,
  红队实测:那样写出来的遍历器**完全游离在判据之外**(既不进 `found` 也不进 `unpruned`)。
* 仍**不认**的形式:`getattr(os, "walk")(...)`、把 `os.walk` 存进变量再调、
  自己写的包装函数。这些绕得过 —— 静态判据的固有限制。
* 剪枝调用必须是**模块属性**形式(`fsg.prune_escaped`);裸名 `prune_escaped(...)`
  不算(否则「同名本地函数」又成了绕过口)。
* 只认 `for a, b, c in <遍历调用>:` 这种**三元组解包**。写成
  `for t in os.walk(root): dp, dn, fn = t` 会被判成没剪枝(**宁误红不漏检**)。
* 同名作用域(`file::func` 键冲突)会**显式报错**,不静默覆盖。
* `tmp_jev_path1/` 被排除 —— **排除清单 = 移动即消音**,与 C17/C18 同一条边界。
"""
import ast
import os
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import _fs_guard as fsg  # noqa: E402

#: 全仓含 Python 源的顶层目录(与 C17 的 `SOURCE_DIRS` 同口径)。
SOURCE_DIRS = ("benchmarks", "packages", "tests", "tools")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", "tmp_jev_path1"}

#: ⚠ **具名清单,不是数量下界**(Round 65 的教训)。新增遍历器必须显式登记。
#: 格式 `相对路径::函数名`(模块级写 `<module>`)。
WALKERS = (
    "tests/test_fs_walkers_are_pruned.py::_py_files",   # 本判据自己的遍历器 —— 它也得守规矩
    "tests/test_markdown_tables.py::_markdown_files",
    "tests/test_no_duplicate_dict_keys.py::iter_py_files",
    "tests/test_no_encoding_damage.py::iter_text_files",
    "tests/test_no_encoding_damage.py::scan_syntax_warnings",
    "tools/_wilson_doc_scan.py::main",
)

#: 本文件的用例**具名清单**(不是计数)—— 防「改名绕过」(Round 63/64 的教训)。
CASE_NAMES = (
    "test_W1_every_recursive_walker_is_pruned",
    "test_W2_detector_is_falsifiable",
    "test_W3_case_count",
    "test_W4_non_recursive_glob_is_not_flagged",
    "test_W5_looks_like_pruning_but_is_not",
    "test_W6_alias_imports_are_recognised",
)

PRUNE_ATTR = "prune_escaped"


def _py_files(root=ROOT):
    r"""遍历 `root` 下所有 `.py`。⚠ 本函数**自己**也是一个递归遍历器,同样剪枝。"""
    out = []
    real_root = os.path.realpath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        fsg.prune_escaped(dirpath, dirnames, real_root)
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fn in sorted(filenames):
            if fn.lower().endswith(".py"):
                out.append(pathlib.Path(dirpath) / fn)
    return out


def _aliases(tree):
    r"""从 `ast.Import` / `ast.ImportFrom` 建名字映射。

    ⚠ Round 67 红队实测:初版不认 `import os as o` 与 `from os import walk`,
    这两类遍历器**完全不被识别** → 零覆盖(游离在判据之外)。
    """
    mods, funcs = {}, {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                mods[a.asname or a.name] = a.name
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                funcs[a.asname or a.name] = (n.module, a.name)
    return mods, funcs


def _resolve(func, mods, funcs):
    r"""把调用目标解析成 `(模块名, 属性名)`。解析不出来返回 `(None, None)`。"""
    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Name):
            base = mods.get(func.value.id, func.value.id)
        else:
            base = ast.unparse(func.value)
        return base, func.attr
    if isinstance(func, ast.Name):
        return funcs.get(func.id, (None, None))
    return None, None


def _calls(node):
    r"""收集 `node` 作用域内的调用 —— **不深入嵌套函数**(每个函数是独立作用域)。

    ⚠ Round 67 初版直接用 `ast.walk(tree)` 取模块级,于是函数体里的调用被
    **同时记进 `<module>` 和该函数** —— W4 当场报
    `['fake/rec.py::<module>', 'fake/rec.py::find'] != ['fake/rec.py::find']`。
    """
    out, stack = [], [node]
    while stack:
        n = stack.pop()
        if (n is not node
                and isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
            continue
        if isinstance(n, ast.Call):
            out.append(n)
        stack.extend(ast.iter_child_nodes(n))
    return out


def _walk_kind(call, mods, funcs):
    r"""该调用是不是**真递归**文件系统遍历?是则返回名字,否则 `None`。

    ⚠ `ast.walk` **不算** —— 它遍历语法树,不碰文件系统。Round 67 普查第一版
    把 `ast.walk` 也算了进去,9 条「无剪枝」里 7 条是假的。
    ⚠ `glob.glob(p)` **默认非递归**;只有 `recursive=True` 才算。
    ⚠ `call` 可能**不是** `ast.Call`(例如 `for a, b in (x, y):` 的 `iter` 是 Tuple)
    —— 直接取 `.func` 会 `AttributeError`。初版漏了这个判断,实跑当场崩。
    """
    if not isinstance(call, ast.Call):
        return None
    base, attr = _resolve(call.func, mods, funcs)
    if base == "os" and attr == "walk":
        return "os.walk"
    if attr == "rglob":
        return f"{base}.rglob"
    if attr == "glob" and (base or "").endswith("glob"):
        if any(k.arg == "recursive" and getattr(k.value, "value", False) is True
               for k in call.keywords):
            return "glob.glob(recursive=True)"
    return None


def _recursive_calls(calls, mods, funcs):
    return sorted({k for k in (_walk_kind(c, mods, funcs) for c in calls) if k})


def _is_realpath_of_walk_root(expr, walk_arg, scope, mods, funcs):
    r"""`expr` 是不是「**该遍历器自己那个 root** 的 `realpath`」?

    ⚠ Round 67 红队绕过 5 逼出这条,而且它**当场暴露了我自己的一个真 bug**:
    红队写 `prune_escaped(dp, dn, os.path.realpath(os.path.dirname(root)))` ——
    参照系比 walk 根**宽一级** → `inside()` 恒真 → **一个子目录都没剪,纯空转**。
    我在 `tools/_wilson_doc_scan.py` 里犯的是**同一个错**(walk 根是 `base`,
    我却传 `os.path.realpath(ROOT)`)—— 是红队的绕过形状让我发现的。
    **「空转判据」:判据看似在守,实则对被守对象零输入 → 恒绿。**

    认两种写法(真仓两种都在用):
      * 内联:`fsg.prune_escaped(dp, dn, os.path.realpath(root))`
      * 具名:`real_root = os.path.realpath(root)` … `fsg.prune_escaped(dp, dn, real_root)`
    """
    def _is_realpath_call(c):
        if not isinstance(c, ast.Call):
            return False
        _b, attr = _resolve(c.func, mods, funcs)
        if attr != "realpath" or not c.args:
            return False
        return ast.unparse(c.args[0]) == walk_arg

    if _is_realpath_call(expr):
        return True
    if isinstance(expr, ast.Name):
        for n in ast.walk(scope):
            if not isinstance(n, ast.Assign) or not _is_realpath_call(n.value):
                continue
            if any(isinstance(t, ast.Name) and t.id == expr.id for t in n.targets):
                return True
    return False


def _loop_prunes(node, scope, mods, funcs):
    r"""**单个** walk 循环体内,是否存在一个「真的会剪」的剪枝调用?

    四条同时满足才算(缺一即红,理由见模块 docstring;W5 逐条钉住):
      1. 属性名**精确等于** `prune_escaped`;
      2. 调用在**这个** `for a, b, c in <真递归遍历>:` 的循环体内;
      3. 第 2 个位置实参**就是**该循环的 `b`(dirnames 变量);
      4. 第 3 个位置实参是**该循环那个 root 的 `realpath`**(宽一级 = 剪错参照系)。
    """
    dn = node.target.elts[1]
    walk_arg = ast.unparse(node.iter.args[0])
    for c in _calls(node):
        _base, attr = _resolve(c.func, mods, funcs)
        if attr != PRUNE_ATTR:                       # ① 精确名,不是子串
            continue
        if not (len(c.args) >= 2 and isinstance(c.args[1], ast.Name)
                and c.args[1].id == dn.id):          # ③ 第 2 实参 = dirnames
            continue
        if len(c.args) >= 3 and \
                _is_realpath_of_walk_root(c.args[2], walk_arg, scope, mods, funcs):
            return True                              # ④ 第 3 实参 = realpath(walk root)
    return False


def _prunes_walk_loop(scope, mods, funcs):
    r"""该作用域里的**每一个**递归遍历循环都剪了吗?

    ⚠ **必须全称量化,不能存在量化。** Round 67 补派红队实测(绕过 B6):
    初版写成「找到**一个**合格循环就 `return True`」,于是同一函数里
    **第二个没剪的 walk 循环被整体掩盖** —— 判绿,而那个循环真把仓外文件拉进了扫描。
    **闭环演示**:W1 判「有剪枝」的同时,同构真实代码的循环 B 越界。
    本仓记过「数量下界证明不了覆盖面」,这里是同一族错误的另一面:
    **存在性证明不了全称性。**
    """
    loops = [n for n in ast.walk(scope)
             if isinstance(n, ast.For)
             and _walk_kind(n.iter, mods, funcs)
             and isinstance(n.target, ast.Tuple) and len(n.target.elts) == 3
             and isinstance(n.target.elts[1], ast.Name)
             and n.iter.args]
    if not loops:
        return False
    return all(_loop_prunes(n, scope, mods, funcs) for n in loops)


def walker_report(sources):
    r"""`sources` = [(相对路径, 源码)] → `{ 'file::func': (递归调用名, 真剪枝了吗) }`。

    ⚠ 键冲突(同名嵌套函数)会**显式报错**,不静默覆盖 —— Round 67 红队实测:
    初版 `report` 是 dict,一剪一不剪的同名嵌套函数互相覆盖,只看到剪枝者。
    """
    report, collisions = {}, []
    for rel, src in sources:
        try:
            tree = ast.parse(src, rel)
        except SyntaxError:
            continue
        mods, funcs = _aliases(tree)
        scopes = [("<module>", tree)] + [
            (n.name, n) for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for name, node in scopes:
            calls = _calls(node)
            rec = _recursive_calls(calls, mods, funcs)
            if not rec:
                continue
            key = f"{rel}::{name}"
            if key in report:
                collisions.append(key)
                continue
            report[key] = (rec, _prunes_walk_loop(node, mods, funcs))
    if collisions:
        raise AssertionError(
            f"同名作用域冲突,`walker_report` 的键 `file::func` 无法唯一标识:{collisions}\n"
            "  —— 一剪枝一不剪的同名嵌套函数会互相覆盖,判据会静默看到剪枝者。请改名。")
    return report


class TestFsWalkersArePruned(unittest.TestCase):

    def test_W1_every_recursive_walker_is_pruned(self):
        r"""W1:具名清单**精确相等**,且每一个都有**结构性**剪枝。

        ⚠ 两个方向都要红:少登记一个 → 有人删了遍历器;多出一个 → 新增的没登记
        (那正是「忘了剪枝」最常见的入口)。
        """
        rels = sorted(str(p.relative_to(ROOT)).replace(os.sep, "/") for p in _py_files())
        sources = [(r, (ROOT / r).read_text(encoding="utf-8")) for r in rels]
        report = walker_report(sources)
        found = sorted(report)

        # 可证伪:必须真的扫到了东西,否则下面两句在空集上恒真
        self.assertGreater(len(rels), 50, f"只扫到 {len(rels)} 个 .py —— 扫描器失效了")
        self.assertIn("tests/test_markdown_tables.py", rels, "扫描范围没覆盖 tests/")

        missing = [w for w in WALKERS if w not in report]
        extra = [w for w in found if w not in WALKERS]
        self.assertEqual(
            (missing, extra), ([], []),
            f"递归遍历器清单与 `WALKERS` 不一致 —— 缺登记={missing} 多出来={extra}\n"
            "  新增一个遍历器时,必须同时:① 在 `for …, dirnames, … in os.walk(...)` 的"
            "**循环体内**调 `fsg.prune_escaped(…, dirnames, …)`;"
            "② 把 `文件::函数` 加进本文件的 `WALKERS`。")

        unpruned = {w: rec for w, (rec, ok) in report.items() if not ok}
        self.assertEqual(
            unpruned, {},
            f"这些递归遍历器**没有**做「不走出仓根」剪枝:{unpruned}\n"
            "  —— junction 不是 symlink(`os.path.islink` 为 False),"
            "`os.walk(followlinks=False)` 与 `rglob` 都跟随它,"
            "仓外文件会被拉进扫描范围。用 `tests/_fs_guard.prune_escaped`。")

    def test_W2_detector_is_falsifiable(self):
        r"""W2:喂合成源码,「没剪枝」必须判没剪、「真剪枝」必须判剪。

        ⚠ 合成样本必须**按当前形状构造** —— 否则测的是过期的形状,不是被测对象
        (本仓记过「合成样本按旧形状构造」)。
        """
        bad = [("fake/scan_bad.py",
                "import os\n\n\ndef sweep(root):\n"
                "    out = []\n"
                "    for dp, dn, fn in os.walk(root):\n"
                "        out += fn\n"
                "    return out\n")]
        rep = walker_report(bad)
        self.assertEqual(sorted(rep), ["fake/scan_bad.py::sweep"],
                         f"检测器没认出没剪枝的遍历器:{rep}")
        self.assertFalse(rep["fake/scan_bad.py::sweep"][1], "没剪枝的遍历器被判成了「有剪枝」")

        good = [("fake/scan_good.py",
                 "import os\nimport _fs_guard as fsg\n\n\ndef sweep(root):\n"
                 "    out = []\n"
                 "    real = os.path.realpath(root)\n"
                 "    for dp, dn, fn in os.walk(root):\n"
                 "        fsg.prune_escaped(dp, dn, real)\n"
                 "        out += fn\n"
                 "    return out\n")]
        rep2 = walker_report(good)
        self.assertEqual(sorted(rep2), ["fake/scan_good.py::sweep"], f"剪枝版没被认出:{rep2}")
        self.assertTrue(rep2["fake/scan_good.py::sweep"][1], "剪枝版被判成了「没剪枝」")

    def test_W5_looks_like_pruning_but_is_not(self):
        r"""W5:**看起来有剪枝、实际没剪**的写法必须全判为「没剪」。

        ⚠ 这五条都是 Round 67 红队**实测出来的绕过**,不是假想的:

          A **子串匹配**:调 `fake_mod.prune_escaped_fake(dp, dn, os.path.realpath(root))` ——
            初版 `"prune_escaped" in c` 命中,**一行代码绕过**。这正是 Round 50 记过的
            「白名单按文本片段匹配 → 可换靶」。
            ⚠ 用**属性形式**而不是红队原样的裸名 `prune_escaped_fake(...)`:
            裸名走 `_resolve` 的「未知名字 → `(None, None)`」分支,① 在那形状上
            **本来就不是承重点** —— 拿它当样本会得到「判据① 失效也不红」的**假漏检**
            (本仓记过「子判据被冗余的另一条掩盖 → 表现为漏检」)。
            这里刻意把 ③④ 都写成正确的,让 ① 成为**唯一**判别点。
          B **循环外调用**:在 walk 循环**外面**调一次,循环里不调。
          C **传错实参**:`prune_escaped(dp, realpath(dirname(root)), real)` ——
            第 2 个实参不是 dirnames → `inside()` 恒真 → **一个子目录都没剪**。
          D **同名本地函数**:裸名 `prune_escaped(...)`(不是模块属性)。
          E **三元组写成整体**:`for t in os.walk(root): dp, dn, fn = t` ——
            宁误红不漏检(见 docstring 已知边界)。
          H **双循环一剪一不剪**:同函数两个 walk 循环,只有一个剪 ——
            判据必须是**全称量化**(每一个循环都剪),写成「存在一个合格循环就绿」
            会让第二个循环**被整体掩盖**。Round 67 补派红队实测的绕过 B6。

        红队对 A/C 还给了**闭环演示**:判据判绿的同时,真实 junction 实验把仓外
        `docs\jlink\evil.md` 拉进了扫描 —— **判绿但实际越界**。
        """
        cases = {
            "A 子串匹配": (
                "import os\n\n\ndef prune_escaped_fake(a, b, c):\n    pass\n\n\n"
                "def sweep(root):\n    for dp, dn, fn in os.walk(root):\n"
                "        fake_mod.prune_escaped_fake(dp, dn, os.path.realpath(root))\n"),
            "B 循环外调用": (
                "import os\nimport _fs_guard as fsg\n\n\ndef sweep(root):\n"
                "    fsg.prune_escaped(None, [], root)\n"
                "    for dp, dn, fn in os.walk(root):\n        pass\n"),
            "C 传错实参": (
                "import os\nimport _fs_guard as fsg\n\n\ndef sweep(root):\n"
                "    for dp, dn, fn in os.walk(root):\n"
                "        fsg.prune_escaped(dp, os.path.realpath(os.path.dirname(root)), root)\n"),
            "D 同名本地函数": (
                "import os\n\n\ndef prune_escaped(a, b, c):\n    pass\n\n\n"
                "def sweep(root):\n    for dp, dn, fn in os.walk(root):\n"
                "        prune_escaped(dp, dn, root)\n"),
            "E 三元组整体": (
                "import os\nimport _fs_guard as fsg\n\n\ndef sweep(root):\n"
                "    for t in os.walk(root):\n        dp, dn, fn = t\n"
                "        fsg.prune_escaped(dp, dn, root)\n"),
            "F 参照系宽一级(空转)": (
                "import os\nimport _fs_guard as fsg\n\n\ndef sweep(root):\n"
                "    for dp, dn, fn in os.walk(root):\n"
                "        fsg.prune_escaped(dp, dn, os.path.realpath(os.path.dirname(root)))\n"),
            "G 参照系不是本循环的 root": (
                "import os\nimport _fs_guard as fsg\n\n\ndef sweep(base, OTHER):\n"
                "    for dp, dn, fn in os.walk(base):\n"
                "        fsg.prune_escaped(dp, dn, os.path.realpath(OTHER))\n"),
            "H 双循环一剪一不剪(存在量化)": (
                "import os\nimport _fs_guard as fsg\n\n\ndef sweep(a, b):\n"
                "    for dp, dn, fn in os.walk(a):\n"
                "        fsg.prune_escaped(dp, dn, os.path.realpath(a))\n"
                "    for dp, dn, fn in os.walk(b):\n        pass\n"),
        }
        for label, src in cases.items():
            rep = walker_report([("fake/bypass.py", src)])
            self.assertEqual(sorted(rep), ["fake/bypass.py::sweep"],
                             f"[{label}] 遍历器没被认出来:{rep}")
            self.assertFalse(
                rep["fake/bypass.py::sweep"][1],
                f"[{label}] **判成了「有剪枝」** —— 这条写法实际没剪,判据被绕过了")

    def test_W6_alias_imports_are_recognised(self):
        r"""W6:别名 import 的遍历器**必须**被认出来(Round 67 红队实测的零覆盖)。

        初版只认字面 `os.walk`,于是 `import os as o` / `from os import walk`
        写出来的遍历器**完全不被识别** → 既不进 `found` 也不进 `unpruned` →
        一个真实遍历器可以**完全游离在判据之外**。
        """
        for label, src in {
            "import os as o": ("import os as o\n\n\ndef sweep(root):\n"
                               "    for dp, dn, fn in o.walk(root):\n        pass\n"),
            "from os import walk": ("from os import walk\n\n\ndef sweep(root):\n"
                                    "    for dp, dn, fn in walk(root):\n        pass\n"),
        }.items():
            rep = walker_report([("fake/alias.py", src)])
            self.assertEqual(sorted(rep), ["fake/alias.py::sweep"],
                             f"[{label}] 别名形式的遍历器**没被认出来** —— 它会游离在判据之外")
            self.assertFalse(rep["fake/alias.py::sweep"][1], f"[{label}] 没剪枝却判成剪了")

        # 别名 realpath 也认(判据④ 靠 `_resolve` 而不是字面 `os.path.realpath`)
        for label, src in {
            "import os.path as p": ("import os\nimport os.path as p\nimport _fs_guard as fsg\n"
                                    "\n\ndef sweep(root):\n"
                                    "    for dp, dn, fn in os.walk(root):\n"
                                    "        fsg.prune_escaped(dp, dn, p.realpath(root))\n"),
            "from os.path import realpath": (
                "import os\nfrom os.path import realpath\nimport _fs_guard as fsg\n"
                "\n\ndef sweep(root):\n"
                "    for dp, dn, fn in os.walk(root):\n"
                "        fsg.prune_escaped(dp, dn, realpath(root))\n"),
        }.items():
            rep = walker_report([("fake/alias_rp.py", src)])
            self.assertTrue(
                rep.get("fake/alias_rp.py::sweep", (None, False))[1],
                f"[{label}] 别名 `realpath` 没被认出来 → 真剪枝被误红(假阳性)")

    def test_W4_non_recursive_glob_is_not_flagged(self):
        r"""W4:`glob.glob('suite*.jsonl')`(无 `**`)**不是**递归遍历器,不得误报。

        ⚠ Round 67 普查脚本第一版就误报了它(`benchmarks/accuracy/_audit_measurement.py`)
        —— **假阳性会让人去改本来正确的东西**(Round 53 记过)。
        """
        src = [("fake/nonrec.py",
                "import glob\n\n\ndef find():\n"
                "    return [f for f in glob.glob('suite*.jsonl')]\n")]
        self.assertEqual(walker_report(src), {}, "非递归 glob 被误报成了递归遍历器")

        rec = [("fake/rec.py",
                "import glob\n\n\ndef find():\n"
                "    return list(glob.glob('**/*.jsonl', recursive=True))\n")]
        self.assertEqual(sorted(walker_report(rec)), ["fake/rec.py::find"],
                         "`recursive=True` 的 glob 没被认出来")

    def test_W3_case_count(self):
        r"""W3:元判据 —— 用例**具名清单**必须还在(防删 / 防改名)。"""
        loaded = sorted(m for m in dir(self) if m.startswith("test_"))
        self.assertEqual(loaded, sorted(CASE_NAMES),
                         "用例集变了 —— 删 / 改名 / 新增用例都必须同步改 CASE_NAMES 并说明原因")


if __name__ == "__main__":
    unittest.main(verbosity=2)
