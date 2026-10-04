# -*- coding: utf-8 -*-
r"""
全仓**编码损坏扫描**:任何文件里不得出现 U+FFFD(替换字符)。

## 缺口(2026-10-01 Round 34 由红队 22cc7297 发现,Round 35 修)

编辑工具在本机写入中文时偶发把一个汉字写成 U+FFFD 替换字符,
**不报语法错、不报运行错,只在人读文档时才发现**。实测抓到 3 处:

    docs/evasion-audit.log          第3行 「真??任根在仓外」   <- 日志表头
    docs/self-optimize-rounds.md    记账正文里描述该损坏的那句本身
    tests/test_evasion_audit.py     docstring 里的「遍历全??「规避」行」

第三处在**代码注释里** —— 它不影响执行,但会误导后续维护者,
而本仓大量结论就写在注释与 docs 里,注释被污染 = 结论的可读性被污染。

⚠ 本文件自身**绝不能含字面的替换字符**,否则它会检自己、永远红。
故用 `chr(0xFFFD)` 构造,docstring 里也只用文字描述它、**不展示该字符本身**。
(踩过两次:初版在 docstring 与常量里各写了一个字面量;第二次修 docstring 时
 又在「而不展示它」那句里打进了一个 —— 正在写的这段注释本身又被检测器抓住。)

## 判据(预注册,R9)

  E1 排除第三方与临时目录(`node_modules` / `.git` / `__pycache__` /
     红队遗留的 `tmp_jev_path1/`)后,**全仓不得出现 U+FFFD**。
  E2 覆盖所有承载文本的文件类型,不只是 `.py` ——
     损坏最常发生在 `.md` 与 `.log`,而它们恰恰是本仓结论的载体。
  E3 报错必须给出**文件 + 行号 + 该行内容**,便于直接定位。
     只说「有 N 处」等于让人自己找。
  E3 全仓 Python 源在编译时**不得产生 `SyntaxWarning`**(Round 63 新增)。
     与 E1 同族:**写错但静默**。非法转义序列(如普通字符串里的 `\d`)
     CPython 只发 `SyntaxWarning`,**不影响执行** —— 于是能在仓库里躺很多轮
     没人管(本仓实测躺了 29 轮)。它污染的又是 docstring 这类**结论载体**:
     读者无法从文本判断 `\d` 是「正则的 `\d`」还是「被吞掉的反斜杠」。
"""
import os
import shutil
import sys
import tempfile
import unittest
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import _fs_guard as fsg  # noqa: E402  —— 共享的「不走出仓根」原语(Round 66)

EXCLUDE_DIRS = {"node_modules", ".git", "__pycache__", "tmp_jev_path1", ".pytest_cache"}
EXTS = (".py", ".md", ".yml", ".yaml", ".mjs", ".js", ".json",
        ".ps1", ".psm1", ".log", ".txt")
# 用 chr() 构造,绝不写字面量 —— 否则本文件会检出自己,永远红
FFFD = chr(0xFFFD)

#: 本文件里的用例数(元判据;删用例会红)
#: 本文件的用例**具名清单**(不是计数)。⚠ 名字而非数字 —— 数字抓不住「改名」
#: (Round 63 红队补派实测;Round 64 把这条修法推广到全仓其余 5 个元判据)。
CASE_NAMES = (
    "test_E1_no_replacement_character_anywhere",
    "test_E2_covers_docs_and_logs",
    "test_E3_no_syntax_warnings_in_python_sources",
    "test_E3b_syntax_scan_has_discriminating_power",
    "test_E3c_case_count",
    "test_E5_text_scan_does_not_escape_repo_via_junction",
)


def iter_text_files(root=ROOT):
    r"""遍历 `root` 下承载文本的文件。

    ⚠ Round 66:`root` 参数是为了让 E5 能拿**带 junction 的临时仓**验证它
    (与 `scan_syntax_warnings` 同款)。E1/E2 仍走默认值 `ROOT`。
    """
    for dirpath, dirnames, filenames in os.walk(root):
        fsg.prune_escaped(dirpath, dirnames, os.path.realpath(root))
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if fn.endswith(EXTS):
                yield os.path.join(dirpath, fn)


#: 编译期扫描的源文件后缀。⚠ `.pyw` / `.pyi` 也要算 —— Round 63 红队实测:
# `python tool.pyw` 会**真的**打印 `SyntaxWarning`,而只认 `.py` 时完全看不见。
# 比较时**大小写不敏感**(Windows 上 `SHADOW.PY` 照样能被解释器执行)。
PY_SUFFIXES = (".py", ".pyw", ".pyi")
#: 编译期扫描的**遍历数下界**。⚠ 这是**反空转守卫**:`ROOT` 写错或
#: 仓内**含 Python 源**的顶层目录 —— **具名清单**,不是数量下界。
#: ⚠ 写死的**身份**不会随仓增长过期;写死的**数字**会(Round 64 刚在
#: `_real_output(31)` 上吃过一次)。
#: ⚠ Round 65 之前这里是 `MIN_PY_FILES = 50` + 只查 `tests` / `tools` 两个
#: 目录名 —— 实测真实遍历数 **83**,余量 **33(40%)**,而且 `benchmarks/`
#: (39 个源,占 47%)与 `packages/`(7 个源)是**零覆盖**的:它们整个消失后
#: 守卫要么判绿(7 个 / 3 个的目录),要么只是**侥幸**被下界挡住(39 个的目录
#: 让总数从 83 掉到 44)。**判据的覆盖不能靠数字余量,只能靠身份。**
SOURCE_DIRS = ("benchmarks", "packages", "tests", "tools")

#: ⚠ **排除清单 = 移动即消音**(Round 65 红队实测的固有权衡,明写在此):
#: 把文件**搬进** `EXCLUDE_DIRS` 里的目录 → 扫描不到它、`bad == []`、守卫判绿。
#: 守卫只防「整个目录消失」,防不了「文件搬进排除目录」。`tmp_jev_path1`
#: (43 个 `.py`)就是仓内现成的载体。**不靠代码兜底**,靠人工纪律 + 大 diff 评审(⚠ **本仓当前无此控制** —— 5 个自守链文件未被 git 跟踪,`git diff` 无输出)补位。


def scan_syntax_warnings(root=ROOT, exclude=EXCLUDE_DIRS):
    """遍历 Python 源,返回 `(被扫描的相对路径列表, 问题描述列表)`。

    抽成函数是为了让 E3b 能拿**已知有缺陷的临时仓**验证它的鉴别力 ——
    判据必须可证伪,否则「恒绿」也能冒充「守住了」。

    ⚠ Round 66:越界剔除改用 `_fs_guard.prune_escaped`(**单一原语**)。原先这里
    有一份**本地** `_inside`,而同一文件里的 `iter_text_files` 与
    `tests/test_no_duplicate_dict_keys.py` 的 `iter_py_files` 都没有 ——
    这正是本仓记过两次的「按函数而非按缺陷类别划修复范围」的第三次复发。
    """
    scanned, bad = [], []
    real_root = os.path.realpath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        fsg.prune_escaped(dirpath, dirnames, real_root)
        dirnames[:] = [d for d in dirnames if d not in exclude]
        for fn in filenames:
            if not fn.lower().endswith(PY_SUFFIXES):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root)
            scanned.append(rel)
            with open(path, "rb") as fh:
                src = fh.read()
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                try:
                    compile(src, rel, "exec")
                except SyntaxError as exc:
                    bad.append(f"{rel}:{exc.lineno}: 语法错误 {exc.msg}")
                    continue
                for w in caught:
                    if issubclass(w.category, SyntaxWarning):
                        bad.append(f"{rel}:{w.lineno}: {w.message}")
    return scanned, bad


def assert_scan_not_idle(case, scanned):
    """**反空转守卫**:断言这次扫描真的遍历到了**该在的每一个目录**。

    抽成函数是为了让它**可证伪** —— E3b 拿空仓调它,必须抛 `AssertionError`。
    留在 E3 里内联的话,删掉判据不会有任何用例报红(「判据看似在守」)。

    ⚠ Round 65:口径从「数量下界 + 两个目录名」改成「**具名目录清单全覆盖**」。
    旧口径两个洞(实测):① 剔掉 `packages/`(7 个源)或 `tools/`(3 个源)后
    总数仍 ≥ 50 → **判绿**;② `benchmarks/`(39 个源)整个消失只让总数从 83
    掉到 44,**恰好**被下界挡住 —— 纯属侥幸。
    **数量下界只能证明「扫到了东西」,证明不了「扫到了该扫的东西」。**
    """
    dirs = {os.path.dirname(rel).split(os.sep)[0] for rel in scanned}
    missing = [d for d in SOURCE_DIRS if d not in dirs]
    case.assertEqual(
        missing, [],
        f"扫描范围里缺这些目录:{missing}(应有 {list(SOURCE_DIRS)})—— "
        "该目录下的源不会被检查,`bad == []` 会在**部分输入**下恒真(空转判据)")


class TestNoEncodingDamage(unittest.TestCase):

    def test_E1_no_replacement_character_anywhere(self):
        bad = []
        for path in iter_text_files():
            rel = os.path.relpath(path, ROOT)
            try:
                with open(path, encoding="utf-8") as fh:
                    for lineno, line in enumerate(fh, 1):
                        if FFFD in line:
                            bad.append(f"{rel}:{lineno}: {line.strip()[:100]}")
            except UnicodeDecodeError:
                bad.append(f"{rel}: 文件不是合法 UTF-8(比 U+FFFD 更严重)")
        self.assertEqual(
            bad, [],
            "以下位置有编码损坏(U+FFFD 替换字符)。\n"
            "本机编辑工具写入中文时偶发把整个汉字写成 U+FFFD,"
            "不报语法错也不报运行错,只在人读时才发现。\n"
            "  " + "\n  ".join(bad))

    def test_E2_covers_docs_and_logs(self):
        """E2 反向自检:扫描范围必须真的包含 docs/ 与 *.log。

        若哪天把 EXTS 收窄成只剩 .py,这条会红 —— 防止「扫描范围悄悄变小」
        而损坏恰好落在范围之外(这正是当初 3 处漏网的原因之一)。
        """
        found_suffixes = set()
        for path in iter_text_files():
            found_suffixes.add(os.path.splitext(path)[1])
        for must in (".py", ".md", ".yml", ".mjs", ".json", ".log"):
            self.assertIn(must, found_suffixes,
                          f"扫描范围里没有 {must} —— 损坏最常发生在文档与日志里")

    def test_E3_no_syntax_warnings_in_python_sources(self):
        r"""E3:全仓 Python 源编译时不得产生 `SyntaxWarning`。

        ⚠ 与 E1 同族:**写错但静默**。非法转义序列在普通字符串里只是
        `SyntaxWarning`,**不影响执行** —— 本仓这两处躺了 29 轮没人管,
        因为它们不红、不报错、也不影响任何结论的数值。
        但 `SyntaxWarning` 在 3.12 起默认可见、未来会收紧为 `SyntaxError`,
        而且它落在 docstring 这类**结论载体**上 —— 读者无法从文本判断
        `\d` 是「正则的 `\d`」还是「被吞掉的反斜杠」。

        判据口径:只认**编译期**信号(`compile()` + 捕获 `SyntaxWarning`),
        不做文本扫描 —— 文本扫描分不清 raw string 与普通字符串。

        ⚠ **反空转守卫**(Round 63 红队实测的洞):初版只断言 `bad == []` ——
        `ROOT` 写错、或 `EXCLUDE_DIRS` 写宽,遍历数就归零,`[] == []` **恒真**。
        这正是本仓刚修过的「**空转判据**」同族。现在同时断言**遍历到了东西**
        (计数下界)与**遍历到了该在的目录**(结构自检,同 E2 的口径)。
        """
        scanned, bad = scan_syntax_warnings()
        assert_scan_not_idle(self, scanned)
        self.assertEqual(
            bad, [],
            "以下 Python 源在编译时产生 SyntaxWarning(写错但静默)。\n"
            "修法:把非法转义写成双反斜杠,或把 docstring 改成 raw string(前缀 r)。\n"
            "  " + "\n  ".join(bad))

    def test_E3b_syntax_scan_has_discriminating_power(self):
        """E3b 自证鉴别力:造一个**已知有缺陷**的临时仓,扫描必须报红。

        没有这条,E3 可能只是「恒绿」—— 而恒绿的判据什么也没守。
        同时证明**反空转守卫是有效的**:空仓必须被计数下界挡住。
        """
        tmp = tempfile.mkdtemp(prefix="jev_e3b_")
        self.addCleanup(shutil.rmtree, tmp, True)
        os.makedirs(os.path.join(tmp, "tests"))
        # ⚠ 每种后缀/大小写都要有样本,否则对应的加固是**零覆盖**的。
        # (Round 63 自审实测:只放 `.py` 时回退 `.pyw` 支持不会被检出;
        #  红队补派又实测:`.pyi` 同样缺样本 —— 加固声明支持它,却无人在守。)
        # 文件清单**从样本自身推导**,不写死数字 —— 加一个样本不必改两处。
        names = ("bad.py", "bad.pyw", "bad.pyi", "SHADOW.PY")
        for name in names:
            with open(os.path.join(tmp, "tests", name), "w", encoding="utf-8") as fh:
                fh.write("import re\n\nPAT = re.compile(\"\\d+\")\n")
        scanned, bad = scan_syntax_warnings(tmp, exclude=set())
        self.assertEqual(len(scanned), len(names),
                         f"临时仓的源没被全部遍历到(应为 {names})")
        self.assertEqual(len(bad), len(names),
                         "已知含非法转义的源没被全部报出 —— E3 没有鉴别力")
        self.assertIn("invalid escape sequence", bad[0])
        # junction / symlink 越界剔除必须**可证伪**(纯路径运算,不需要真建 junction)
        # ⚠ Round 66:原语搬到了 `_fs_guard.inside`(**单一定义**),判据跟着搬 ——
        #    否则「同一原语在别处漏用」时会因为这里还在测本地副本而看不出差别。
        self.assertTrue(fsg.inside(r"C:\a", r"C:\a\b"), "子目录被误判为越界")
        self.assertTrue(fsg.inside(r"C:\a", r"C:\a"), "根自身被误判为越界")
        self.assertFalse(fsg.inside(r"C:\a", r"C:\ab"),
                         "`C:\\a` 是 `C:\\ab` 的**字符串前缀**但不是其父目录 —— "
                         "只比前缀会让兄弟目录混进来")
        self.assertFalse(fsg.inside(r"C:\a", r"C:\other"), "越界目录没被剔除")
        # 反空转守卫必须**可证伪**:空仓调它必须抛错
        empty = tempfile.mkdtemp(prefix="jev_e3b_empty_")
        self.addCleanup(shutil.rmtree, empty, True)
        self.assertEqual(scan_syntax_warnings(empty, exclude=set())[0], [],
                         "空仓本应遍历到 0 个源")
        with self.assertRaises(AssertionError, msg="空仓竟然通过了反空转守卫"):
            assert_scan_not_idle(self, [])
        # 结构自检**也要可证伪**,而且必须**逐个目录**验(Round 65)。
        # ⚠ 旧口径只查 `tests` / `tools` 两个目录名 + 一条数量下界 ——
        # 实测:剔掉 `packages/`(7 个源)或 `tools/`(3 个源)后总数仍 ≥ 下界
        # → **判绿**;而 `benchmarks/`(39 个源,占 47%)整个消失只让总数从
        # 83 掉到 44,**恰好**被下界挡住 —— 纯属侥幸,下界松一点就漏了。
        # 「少一个目录」这条子判据,必须**每个目录**都有独立样本能触发它,
        # 否则它对被它守的那些目录是**零覆盖**的(本仓记过的失败形态)。
        scanned_all, _ = scan_syntax_warnings()
        real_dirs = sorted({rel.split(os.sep)[0] for rel in scanned_all})
        self.assertGreaterEqual(len(real_dirs), 2,
                                f"真实仓的顶层源目录只有 {real_dirs} —— 样本没构造出来")
        for victim in real_dirs:
            partial = [rel for rel in scanned_all if rel.split(os.sep)[0] != victim]
            self.assertLess(len(partial), len(scanned_all), f"剔掉 {victim} 没生效")
            with self.assertRaises(
                    AssertionError,
                    msg=f"剔掉 {victim}/ 后反空转守卫仍判绿 —— 该目录对守卫是零覆盖的"):
                assert_scan_not_idle(self, partial)

    def test_E3c_case_count(self):
        """元判据:用例数**且具名用例**都必须还在。

        ⚠ 只数 `test_` 前缀不够 —— Round 63 红队补派实测:把 `test_E3b`
        **改名**(而不是删掉)时计数不变、元判据全绿,而自证鉴别力用例已经失效。
        「防删」不等于「防消失」。
        """
        loaded = sorted(m for m in dir(self) if m.startswith("test_"))
        self.assertEqual(loaded, sorted(CASE_NAMES),
                         "用例集变了 —— 删 / 改名 / 新增用例都必须同步改 CASE_NAMES 并说明原因")

    def test_E5_text_scan_does_not_escape_repo_via_junction(self):
        r"""E5:**扫描范围不得走出仓根** —— junction 是逃逸口(Round 66)。

        ⚠ Round 63 只在 `scan_syntax_warnings` 里加了 `_inside` 检查,**同一个文件里
        的 `iter_text_files` 连检查都没有**,而 `tests/test_no_duplicate_dict_keys.py`
        的 `iter_py_files` 照样跟随 junction。这是本仓记过两次的失败形态
        「**按目录 / 按函数而非按缺陷类别划修复范围**」的第三次复发。

        现场:`os.path.islink(junction)` 是 **`False`**,`os.walk(followlinks=False)`
        与 `pathlib.Path.rglob` **都管不到它** —— 唯一可靠判据是 `os.path.realpath`
        是否还在仓根之内。

        两个扫描器都要验(一个判据一条,不合并 —— 合并后删掉一半不会红)。
        """
        lab, _ = fsg.make_junction_lab(self, prefix="jev_e5_")
        text = sorted(os.path.relpath(p, lab) for p in iter_text_files(lab))
        self.assertEqual(
            [t for t in text if fsg.JUNCTION_NAME in t], [],
            f"`iter_text_files` 跟随 junction 把**仓外**文件拉进了扫描范围:{text}")
        scanned, _bad = scan_syntax_warnings(lab, exclude=set())
        self.assertEqual(
            [s for s in scanned if fsg.JUNCTION_NAME in s], [],
            f"`scan_syntax_warnings` 跟随 junction 把**仓外**文件拉进了扫描范围:{scanned}")
        # 可证伪:实验场本身必须真的建出了 junction,且两个扫描器**确实**看见了仓内的源
        # (否则「没拉进仓外文件」可能只是因为「什么都没扫到」= 空转判据)
        self.assertIn(os.path.join("tests", "b.py"), text, "扫描器没扫到仓内文件")
        self.assertIn(os.path.join("benchmarks", "a.py"), scanned, "编译扫描没扫到仓内文件")


if __name__ == "__main__":
    unittest.main(verbosity=2)
