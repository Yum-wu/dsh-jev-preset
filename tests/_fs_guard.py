# -*- coding: utf-8 -*-
r"""跨文件共享的**文件系统遍历原语** —— 只放「多处都要用、且写错会静默漏/多」的东西。

## 为什么存在这个文件(Round 66)

本仓的测试文件一贯**自包含**(常量、`REPO`、辅助函数都各写各的)。这条风格对
**取值常量**没问题(`SOURCE_DIRS` 在两处各写一份是有意的),但对**正确性原语**
会出事 —— 实测的现场:

* Round 63 在 `tests/test_no_encoding_damage.py` 的 `scan_syntax_warnings` 上
  发现 **junction 逃逸**(`os.walk` 跟随 junction → 仓外文件被拉进扫描),
  于是**只在那一个函数里**加了 `_inside` 检查;
* Round 65 红队复算时实测:**同一个文件里的 `iter_text_files` 连检查都没有**,
  而 `tests/test_no_duplicate_dict_keys.py` 的 `iter_py_files`(裸 `rglob`)
  **照样跟随 junction**,把仓外文件拉了进来。

这就是本仓已经记过两次的失败形态「**按目录 / 按函数而非按缺陷类别划修复范围**」
的第三次复发。**修复不是再抄一遍 `_inside`,而是让这个原语只有一个定义。**

## junction 不是 symlink(本仓踩过的坑)

`os.path.islink(junction)` 是 **`False`**;`os.walk(followlinks=False)` 与
`pathlib.Path.rglob` **都管不到它**。唯一可靠的判据是**真实路径**(`os.path.realpath`)
是否还在仓根之内 —— 见 `inside()`。

⚠ **「成环会无限递归挂死」是错的,已实测证伪**(Round 66 红队):本机
(Windows + CPython 3.12.7)用 `mklink /J` 造**仓内**环(`sub/jlink→sub2`,
`sub2/jlink2→sub`)后,`os.walk` 与裸 `rglob` **都不挂死** —— Windows 内核对单条路径的
reparse 解析有 **32 次**上限,超了报 `ERROR_CANT_RESOLVE_FILENAME`,而两者都**默认吞错**,
于是**有限终止**(yield 64~66 个重复路径)。本文件初版三处写了「挂死」,是**没验证过的
注释** —— 本仓记过多次的「注释 ≠ 事实」,当轮就被红队抓住。
**剪枝的理由因此只有一条(而且够):越界。** 顺带省掉重复路径,但不许再拿「挂死」当理由。

⚠ **`prune_escaped` 只剪「走出 `root`」的,不剪「仓内 junction」** —— 仓内 junction
(指向仓内另一个目录)仍会被跟随并**重复扫描**(实测 `tests\jlink→benchmarks` 时
`benchmarks\a.py` 与 `tests\jlink\a.py` 并存)。这是**契约外行为**(不越界),
当前无触发源(真仓只有 `tests/test_path_spelling.py` 在 `tempfile` 里建 junction)。

⚠ **`SHADOW.PY` 样本只服务 `iter_py_files` 的大小写判据**,不服务 `iter_text_files`
—— 后者用 `fn.endswith(EXTS)` 是**大小写敏感**的,`SHADOW.PY` 对它**零覆盖**。
(本文件初版注释把该样本的意义泛化到「全部扫描器」,与实现矛盾 —— 也是当轮被红队抓的。)
`iter_text_files` **有意不改**:E1/E2 的目的是抓 U+FFFD,扩大后缀匹配是**扩大扫描面**
而不是修缺陷,属 YAGNI 外。

⚠ **本模块不写 `test_` 前缀,不会被 `unittest` discover 当套件**,
也不在 `package.json` 的套件清单里。
"""

import os
import pathlib
import shutil
import subprocess
import tempfile

#: 建 junction 用的目录名(测试与守卫共用同一个名字,改一处即可)
JUNCTION_NAME = "jlink"


def inside(root_real, path_real):
    r"""`path_real` 是否在 `root_real` 之内(剔除 junction / symlink 越界用)。

    ⚠ 必须比 `root_real + os.sep`,不能只比前缀 —— `C:\a` 是 `C:\ab` 的
    **字符串前缀**,但 `C:\ab` **不在** `C:\a` 里面。本仓 Round 63 记过这条。

    两个入参都必须是 **`os.path.realpath` 之后的**真实路径。

    ⚠ **本函数不做任何规范化** —— 传进来的字符串长什么样就比什么。已知边界:
      * 根带**尾斜杠**时直接调用会误判(`inside("C:\\a\\", "C:\\a\\b")` 是 `False`)。
        实际调用路径安全:`os.path.realpath` **会去掉尾斜杠**。
      * **不存在的路径** `realpath` 不展开别名(8.3 短名 / 大小写),只做词法规范化。
        实际调用路径安全:`prune_escaped` 传的是 `os.walk` 给出的**真实存在**的目录名。
      * **UNC 路径**的前缀形式一致性本机未实测(`C$` 不可访问)—— **未验证**,
        不当成已验证。
    """
    return path_real == root_real or path_real.startswith(root_real + os.sep)


def prune_escaped(dirpath, dirnames, root_real):
    r"""`os.walk` 用:原地剔除会走出 `root_real` 的子目录(含 junction)。

    用法:

        for dirpath, dirnames, filenames in os.walk(root):
            prune_escaped(dirpath, dirnames, os.path.realpath(root))
            ...
    """
    dirnames[:] = [
        d for d in dirnames
        if inside(root_real, os.path.realpath(os.path.join(dirpath, d)))
    ]


def make_junction_lab(case, prefix="jev_junction_lab_"):
    r"""造一个「仓内 → 仓外」的 junction 实验场,返回 `(lab, outside)`。

    `lab/` 下有 `benchmarks/a.py`、`tests/b.py`,以及 `tests/<JUNCTION_NAME>`
    —— 一个指向 `outside/` 的 **junction**。`outside/` 里放两个源文件。
    调用方 `case` 负责清理(经 `addCleanup`)。

    ⚠ `mklink /J` **不需要管理员权限**、也不需要 `SeCreateSymbolicLinkPrivilege`
    (只有真 symlink 才需要)—— 所以这个实验场在本机**能真跑**,不是纸面推演。
    ⚠ 建不出来就**直接断言失败**,不 `skip`:静默跳过会让这条判据变成零覆盖
    (本仓记过的「空转判据」)。
    """
    lab = pathlib.Path(tempfile.mkdtemp(prefix=prefix))
    outside = pathlib.Path(tempfile.mkdtemp(prefix=prefix + "outside_"))
    case.addCleanup(shutil.rmtree, lab, True)
    case.addCleanup(shutil.rmtree, outside, True)

    (lab / "benchmarks").mkdir()
    (lab / "benchmarks" / "a.py").write_text("OK = 1\n", encoding="utf-8")
    (lab / "tests").mkdir()
    (lab / "tests" / "b.py").write_text("OK = 1\n", encoding="utf-8")
    #: ⚠ **大小写样本**必须放进实验场:Windows 上 `rglob("*.py")` 是**大小写不敏感**的,
    #: 把遍历改成 `fn.endswith(".py")` 会让 `SHADOW.PY` 从覆盖里**静默消失** ——
    #: 没有这个样本,那条加固就是**零覆盖**(本仓 Round 63 记过这条)。
    (lab / "tests" / "SHADOW.PY").write_text("OK = 1\n", encoding="utf-8")
    (outside / "c.py").write_text("OUTSIDE = 1\n", encoding="utf-8")

    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J",
         str(lab / "tests" / JUNCTION_NAME), str(outside)],
        capture_output=True)
    case.assertEqual(
        proc.returncode, 0,
        "建 junction 失败,本判据无法运行(不许静默跳过):"
        + proc.stdout.decode("gbk", "replace") + proc.stderr.decode("gbk", "replace"))
    # junction 的 islink 是 False —— 正是本原语存在的理由
    case.assertFalse(os.path.islink(lab / "tests" / JUNCTION_NAME),
                     "本机这个 junction 居然是 symlink —— 实验场前提变了,请重审本文件")
    return lab, outside
