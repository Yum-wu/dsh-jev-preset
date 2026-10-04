# -*- coding: utf-8 -*-
r"""元判据的键必须是**身份**(用例名),不能只是**计数**。

## 缺陷(附录 C16,Round 64)

Round 63 在 `tests/test_no_encoding_damage.py::E3c` 上发现:元判据「数 `test_` 前缀」
**只防删不防改名** —— 把 `test_E3b` 改名成另一个 `test_` 开头的名字,计数不变、
元判据全绿,而被保护的用例已经**消失**了(它正是「自证鉴别力」那条)。

Round 63 只修了那**一个文件**。Round 64 普查:**全仓 6 个文件带元判据,5 个仍是
「只数前缀」**。这正是本仓记过的失败形态 —— **按目录(单文件)而非按缺陷类别
划修复范围**(R48 教训):同一轮里已经知道病因,却只治了手边那一个病人。

## 判据(预注册,R9)

  M1 **改名必须被抓到**:对每个带元判据的文件,在**源码级**把一条非元判据用例
     改名(**不是删**),重新加载,真的调用它的元判据 —— 必须 `AssertionError`。
  M3 **扫描范围必须绑到文件名**(不是下界):实际扫到的文件集合必须**等于**
     `META_FILES` 具名清单 —— 少一个就报红。
  M4 变异体必须**语义完好**(崩溃不算检出)。
  M5 本文件自己的用例具名清单。

⚠ **为什么不设「新增用例」判据(Round 64 红队实测后删掉)**:初版有 `M2`(插入一条
新用例,期望报红)。红队独立复算发现它**对两种实现都判红** —— 具名清单版红、把判据
退回「只数前缀」的旧写法**也红**(`11 != 10`),因为新增用例**必然改变计数**,
计数判据天然防得住。**它区分不出「键是身份还是计数」,即零鉴别力** ——
本仓记过的「**空转判据**」。真正有鉴别力的方向只有**改名**(计数不变、身份变了),
那是 `M1` 的职责,已覆盖。故删除,不留一个看起来在守、实则测不出东西的用例。

⚠ **本文件会被自己扫到**(`CASE_NAMES` 名字本身含 `CASE`)—— 这是**有意的**:
`M5` 因此也受 `M1` 的改名变异保护,可自证。初版注释曾声称「拼接避免自扫」,
**与行为不符**(Round 64 红队报出),已改正。

⚠ 变异必须**源码级**,不能靠 monkeypatch `dir()`:`tests/test_appendix_status_table.py`
的元判据**同时**比较「AST 里的 `test_` 名」与「类上加载到的名」—— monkeypatch 只动
后者,会让两者**不等**而报红,**红的原因是另一条子判据**,不是我们要测的那条。
「变异没走到那条分支」是本仓记过的失败形态(拿冗余防护当检出)。
"""
import ast
import importlib.util
import os
import re
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(REPO, "tests")
#: 变异体是写到 `%TEMP%` 再加载的,被测文件原有的 `sys.path.insert` 会失效 ——
#: 这里把仓内两个可导入根预先挂上,否则变异体 `ModuleNotFoundError` 崩溃
#: (本仓铁律:**崩溃 ≠ 检出**)。
for _p in (os.path.join(REPO, "packages", "assertions", "python"),
           os.path.join(REPO, "benchmarks", "accuracy"),
           os.path.join(REPO, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
#: 元判据引用的模块级常量,名字里必须含 `CASE`(`EXPECTED_CASES` / `CASE_NAMES` 都算)。
_ANCHOR = "CASE"
#: ⚠ **具名清单,不是下界**(Round 64 红队实测):初版用 `MIN_META_FILES = 5` 而下界
#: 小于实际数(7),于是**允许 2 个元判据文件静默脱离扫描**仍全绿 —— 攻击链真实:
#: 把某文件的元判据改成 `builtins.dir(...)` + 只数前缀,`meta_methods()` 就扫不到它,
#: 它失效而没人管。**这正是本轮要修的那个缺陷(计数 vs 身份)在我自己的判据上复发。**
META_FILES = (
    "test_appendix_status_table.py",
    "test_fs_walkers_are_pruned.py",
    "test_g_check_actually_ran.py",
    "test_meta_criteria_bind_to_names.py",
    "test_no_duplicate_dict_keys.py",
    "test_no_encoding_damage.py",
    "test_no_silent_skips.py",
    "test_rounds_doc_snapshot.py",
)


def iter_test_files():
    for fn in sorted(os.listdir(TESTS)):
        if fn.startswith("test_") and fn.endswith(".py"):
            yield os.path.join(TESTS, fn)


def _case_consts(tree):
    """模块级的、名字含 `CASE` 的赋值目标(自锚定:不写死常量名)。"""
    out = set()
    for node in tree.body:
        targets = getattr(node, "targets", None) or []
        for t in targets:
            if isinstance(t, ast.Name) and _ANCHOR in t.id:
                out.add(t.id)
    return out


def meta_methods(src):
    """返回 `[(元判据方法名, 它引用的常量名)]`。

    元判据的**结构签名**:它同时
      * 引用一个模块级的、名字含 `CASE` 的常量(计数或具名清单),**且**
      * 调用 `dir(...)`(去枚举「类上真正加载到的用例」)。

    ⚠ 只认第一个条件会**误报**:`tests/test_assertions_reverse.py` 有一份
    用例数据表 `CASES`,14 个业务用例**每个**都引用它 —— 初版把它们全当成
    「元判据」,扫描结果 14 个假目标(实测)。**判据的锚点必须能区分
    「引用用例数据」与「枚举用例身份」。**
    """
    tree = ast.parse(src)
    consts = _case_consts(tree)
    if not consts:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            names = {x.id for x in ast.walk(node) if isinstance(x, ast.Name)}
            if not (names & consts):
                continue
            if "dir" not in names:
                continue
            out.append((node.name, sorted(names & consts)[0]))
    return sorted(out)


def all_case_methods(src):
    """源码里**全部** `test_` 方法名(按出现顺序)。"""
    return [n.name for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]


def load_from_source(source, name, cleanup=None):
    """把源码写进临时文件再加载 —— **源码级**变异,不走 monkeypatch。

    ⚠ 临时文件**不能**在加载后立刻删:`tests/test_appendix_status_table.py` 的元判据
    会 `open(os.path.abspath(__file__))` 读**自己那份源码**再与 `dir()` 比对 ——
    删早了它就 `FileNotFoundError`,而崩溃**不算检出**(实测踩到)。
    所以把删除交给调用方(`cleanup` 回调),活到元判据跑完为止。
    """
    fd, tmp = tempfile.mkstemp(suffix=".py", prefix="jev_meta_")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(source)
    if cleanup is not None:
        cleanup(tmp)
    spec = importlib.util.spec_from_file_location(name, tmp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def find_case_class(mod, method):
    """找到定义了 `method` 的 TestCase 子类。"""
    for attr in dir(mod):
        obj = getattr(mod, attr)
        if isinstance(obj, type) and issubclass(obj, unittest.TestCase) \
                and method in dir(obj):
            return obj
    return None


def run_meta(mod, cls, method):
    """调用元判据方法,返回 `(是否 AssertionError, 异常文本)`。"""
    case = cls(method)
    try:
        getattr(case, method)()
    except AssertionError as exc:
        return True, str(exc).splitlines()[0][:160]
    except Exception as exc:                       # noqa: BLE001 - 崩溃不算检出
        return False, f"非 AssertionError(崩溃,不算检出): {type(exc).__name__}: {exc}"
    return False, "判绿了"


def _rename(src, victim):
    old, new = f"def {victim}(", f"def {victim}_renamed("
    if src.count(old) != 1:
        return None
    return src.replace(old, new)


class TestMetaCriteriaBindToNames(unittest.TestCase):

    def setUp(self):
        self.targets = []            # [(文件名, 元判据方法名, 源码)]
        for path in iter_test_files():
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            for method, const in meta_methods(src):
                self.targets.append((os.path.basename(path), method, src))

    def _load(self, source, name):
        """加载变异体,临时文件活到本用例结束(元判据可能要读自己的源码)。"""
        return load_from_source(source, name, lambda p: self.addCleanup(os.unlink, p))

    # M3 扫描范围必须**绑到文件名**,不是下界
    def test_M3_scanner_actually_found_meta_criteria(self):
        found = sorted({f for f, _m, _s in self.targets})
        self.assertEqual(
            found, sorted(META_FILES),
            "扫到的「带元判据的文件」集合与 `META_FILES` 不一致。\n"
            "  **少一个** = 那个文件的元判据已脱离扫描(改了常量名 / 改用 `builtins.dir`\n"
            "  / 用 `vars()` 枚举),它失效而没人管 —— 这正是本判据要抓的;\n"
            "  **多一个** = 锚点误抓(如把「引用用例数据表」当成「枚举用例身份」)。\n"
            f"  实际={found}\n  清单={sorted(META_FILES)}\n"
            "  如果这是**故意**增删元判据文件,请同步改 `META_FILES`。")
        # 每个文件都必须定位到**恰好一条**元判据方法(否则 M1 的覆盖面被高估)
        per_file = {}
        for fname, method, _src in self.targets:
            per_file.setdefault(fname, []).append(method)
        bad = {f: ms for f, ms in per_file.items() if len(ms) != 1}
        self.assertEqual(bad, {}, f"这些文件定位到的元判据方法数不是 1: {bad}")

    # M1 改名必须被抓到(本轮缺陷本体)
    def test_M1_renaming_a_case_is_caught(self):
        bad = []
        for fname, method, src in self.targets:
            victims = [m for m in all_case_methods(src) if m != method]
            if not victims:
                bad.append(f"{fname}::{method}: 找不到可改名的受害者样本 —— 样本没构造出来")
                continue
            victim = victims[0]
            mutated = _rename(src, victim)
            if mutated is None:
                bad.append(f"{fname}::{method}: 变异锚点 `def {victim}(` 命中数不是 1")
                continue
            mod = self._load(mutated, "jev_meta_m1")
            cls = find_case_class(mod, method)
            if cls is None:
                bad.append(f"{fname}::{method}: 变异体里找不到定义它的 TestCase 子类")
                continue
            caught, why = run_meta(mod, cls, method)
            if not caught:
                bad.append(f"{fname}::{method} 对「{victim} 被**改名**」判绿 —— "
                           f"计数没变,用例却没了({why})")
        self.assertEqual(
            bad, [],
            "以下元判据**只防删、不防改名** —— 把用例改名成另一个 `test_` 开头的名字,\n"
            "计数不变、判据全绿,而被保护的用例已经消失。\n"
            "修法:把「数 `test_` 前缀」换成「与一份**具名清单**双向比对」。\n  "
            + "\n  ".join(bad))

    # M4 变异本身必须语义完好(崩溃 ≠ 检出)
    def test_M4_mutants_are_semantically_intact(self):
        bad = []
        for fname, method, src in self.targets:
            victims = [m for m in all_case_methods(src) if m != method]
            if not victims:
                bad.append(f"{fname}: 找不到可改名的受害者样本")
                continue
            mutated = _rename(src, victims[0])
            if mutated is None:
                bad.append(f"{fname}: 改名变异没构造出来")
                continue
            try:
                ast.parse(mutated)
            except SyntaxError as exc:
                bad.append(f"{fname}: 改名变异体语法崩了({exc})—— 崩溃不算检出")
                continue
            try:
                self._load(mutated, "jev_meta_m4")
            except Exception as exc:            # noqa: BLE001
                bad.append(f"{fname}: 改名变异体导入崩了"
                               f"({type(exc).__name__}: {exc})—— 崩溃不算检出")
        self.assertEqual(bad, [], "变异体必须语义完好,否则「红」可能只是崩溃:\n  "
                         + "\n  ".join(bad))

    # M5 元判据:本文件的用例数 + 具名用例(Round 63 的教训就地应用)
    def test_M5_case_names(self):
        loaded = sorted(n for n in dir(self) if n.startswith("test_"))
        self.assertEqual(loaded, sorted(CASE_NAMES),
                         "用例集变了 —— 删/改/增用例都必须同步改 CASE_NAMES 并说明原因")


#: 本文件的用例**具名清单**(不是计数)。⚠ 这是本文件自己主张的修法,必须自己先做到。
#: 初版有 `M2`(新增用例方向),Round 64 红队实测**对两种实现都判红** → 零鉴别力 →
#: 按本仓纪律**删掉**而不是留着充数(空转判据)。真鉴别力在 `M1`(改名)。
CASE_NAMES = (
    "test_M1_renaming_a_case_is_caught",
    "test_M3_scanner_actually_found_meta_criteria",
    "test_M4_mutants_are_semantically_intact",
    "test_M5_case_names",
)

if __name__ == "__main__":
    unittest.main(verbosity=2)
