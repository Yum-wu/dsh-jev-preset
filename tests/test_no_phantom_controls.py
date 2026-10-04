# -*- coding: utf-8 -*-
"""R86(红队 P6-R85-F【中】):**声称的补偿控制,必须在同一处声明它到底存不存在。**

## 缺陷
本仓多处在 docstring / 注释里写「残余边界靠**大 diff 评审**补位」,把它当作**兜底手段**。
而承载自守链的 **5 个**文件(`tools/mutation_harness.py` / `tests/test_mutation_harness.py` /
`tests/pre_registered.py` / `tests/test_no_silent_skips.py` / `tools/g_check.py`)
**全部未被 git 跟踪**
⇒ `git diff` **无输出** ⇒ **大 diff 评审在结构上做不到**(红队 `5458d852` 独立复核:
`git ls-files --error-unmatch` 对**五者**全报未跟踪,`git diff --stat` 全空)。
★ **R108 更正**(红队 R107 P28-R107-B):原文写「4 个文件」「对**四者**全报未跟踪」,
**漏了 `tools/g_check.py`** —— 而**本文件在「⚠ 边界」段里早就写「5 个」** ⇒ **同一文件内 4 vs 5 自相矛盾**。
⚠ **R109 更正**:本句原文写「本文件**第 26 行**早就写「5 个」」—— 插入 5 行后**实际不在第 26 行** ⇒ **写入当时即失效**(红队 R108 P29-R108-B)。⇒ **改为不带行号的指代**。
根因:R105 的「4→5」替换是**逐处**做的,而本处的措辞是「承载自守链的 4 个文件」,
与别处的「4 个自守链文件未被 git 跟踪」**不同形**,故被漏掉 ⇒ **逐处替换 ≠ 逐类替换(第 6 次)**。

**这是「声称的补偿控制缺席」** —— 与 C32 的「已修假象」同族:
权威表里写「已修」而实测未修 = 净增「已闭环」假象;这里写「有兜底」而实测无兜底 = 净增「有人看着」假象。

## 本判据做什么
对全仓 `tools/` 与 `tests/` 下的 `.py`,逐**注释段 / docstring 段**检查:
**若某段提到那个兜底手段,该段必须同时声明本仓当前没有它。**

## ⚠ 边界(红队 `5458d852` 实测,原样接受)
**这是「存在性判据」,不是语义判据。** 它只做 6 个汉字的**子串存在性**匹配,加一句声明就满足,
**证明不了**作者真的想过兜底手段不存在。红队实测的绕过面:
- **P7-R86-B【中】**:同义换词(**新增 1 行、零知识、零改动现有文件**,如写「靠**人工复核**补位」)·
  原字样**插 1 个空格** ×9 · 换载体(模块级字符串常量 / 属性-docstring)⇒ 全部 `rc=0`。
- **P7-R86-C【低】**:`SELF` 豁免留下自指盲区(本文件自己含 1 处它定义的违规段)。
⇒ 与 C14 / C32 ① 同族,**固有边界**。

⚠ 本判据的残余边界**靠大 diff 评审(⚠ **本仓当前无此控制** —— 5 个自守链文件未被 git 跟踪,`git diff` 无输出)补位。**
★ **R107 补回**(红队 R106 P27-R106-A):R105 手工删行时**误删了尾部 `**`** —— 原文见 R104 冻结副本。
"""
import ast
import io
import os
import shutil
import sys
import tempfile
import tokenize
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 被当作兜底手段引用的那个东西。
PHANTOM = "大 diff 评审"
#: 同一段里必须出现的免责声明。
DISCLAIMER = "本仓当前无"

SOURCE_DIRS = ("tools", "tests")
SELF = os.path.abspath(__file__)


def _segments(path):
    """返回该 `.py` 的 (docstring 段, 注释段) 两个列表。"""
    with io.open(path, encoding="utf-8") as f:
        src = f.read()
    docs = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            d = ast.get_docstring(node, clean=False)
            if d:
                docs.append(d)
    comments = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                comments.append(tok.string)
    except tokenize.TokenError:
        pass
    return docs, comments


def _py_files(root):
    """逐目录产出 `(相对路径, 绝对路径)`,并带**目录护栏**。

    ★ R86 第 2 轮(红队 P7-R86-F【低】):旧版 `_count_segments` 没有 `isdir` 护栏,
    源目录缺失时抛的是 `FileNotFoundError` 而不是设计的 `RuntimeError`。
    """
    for sub in SOURCE_DIRS:
        d = os.path.join(root, sub)
        if not os.path.isdir(d):
            raise RuntimeError(f"缺少源目录 {d} —— 「没扫到」!=「没问题」")
        for name in sorted(os.listdir(d)):
            if name.endswith(".py"):
                yield os.path.join(sub, name), os.path.join(d, name)


def _scan(root=None):
    """返回违规列表: `[(相对路径, 段前 60 字)]`。"""
    root = root or ROOT
    bad = []
    for rel, p in _py_files(root):
        if os.path.abspath(p) == SELF:
            continue                      # 本文件自己在 docstring 里引用了它
        docs, comments = _segments(p)
        for seg in docs + comments:
            if PHANTOM in seg and DISCLAIMER not in seg:
                bad.append((rel, " ".join(seg.split())[:60]))
    return bad


def _segments_per_dir(root=None):
    """逐源目录的段数(排除判据文件自身)。"""
    root = root or ROOT
    out = {}
    for rel, p in _py_files(root):
        if os.path.abspath(p) == SELF:
            continue
        docs, comments = _segments(p)
        sub = rel.split(os.sep)[0]
        out[sub] = out.get(sub, 0) + len(docs) + len(comments)
    return out


def _backed_segments(root=None):
    """**与那个兜底手段同段**、且含免责声明的段数。

    ★ R86 第 2 轮(红队 P7-R86-A【中】):旧版 P4 只数「含免责声明的段」,
    **与 `PHANTOM` 完全无关** —— 红队实测 C2d:**只删掉 9 处 6 个汉字、零新增**,
    `rc=0` 而旧 P4 仍是 9 ⇒ **旧 P4 拦不住它自称要拦的那件事**(「删掉字样充数」)。
    ⇒ 改成必须**同段**出现,与 P1 的口径**绑定**。
    """
    root = root or ROOT
    n = 0
    for rel, p in _py_files(root):
        if os.path.abspath(p) == SELF:
            continue
        docs, comments = _segments(p)
        n += sum(1 for s in docs + comments if PHANTOM in s and DISCLAIMER in s)
    return n


class TestNoPhantomControls(unittest.TestCase):
    def test_P1_no_phantom_control_without_disclaimer(self):
        """提到那个兜底手段的段,必须同时声明本仓没有它。"""
        bad = _scan()
        self.assertEqual(
            bad, [],
            "这些注释/docstring 把那个兜底手段当作兜底,却没声明本仓没有它:\n"
            + "\n".join(f"  {p}  …{t}" for p, t in bad)
            + "\n—— 声称的补偿控制缺席,等于净增「有人看着」假象。")

    def test_P2_guard_is_falsifiable(self):
        """R9 可证伪:造一个只提到、不声明的段,判据必须报红。"""
        d = tempfile.mkdtemp(prefix="jev_r86_")
        try:
            os.mkdir(os.path.join(d, "tools"))
            os.mkdir(os.path.join(d, "tests"))
            with io.open(os.path.join(d, "tools", "x.py"), "w", encoding="utf-8") as f:
                f.write("# 残余边界靠" + PHANTOM + "补位。\n")
            with io.open(os.path.join(d, "tests", "t.py"), "w", encoding="utf-8") as f:
                f.write("# 残余边界靠" + PHANTOM + "补位 —— " + DISCLAIMER + "此控制。\n")
            bad = _scan(d)
            self.assertEqual([p for p, _ in bad], [os.path.join("tools", "x.py")],
                             f"可证伪失败:{bad}")
            self.assertEqual(_backed_segments(d), 1, "同段声明计数应为 1")
        finally:
            # ★ R86 第 2 轮(红队 P7-R86-E【低】):旧版无清理,实测泄漏 34 个 `jev_r86_*` 目录。
            shutil.rmtree(d, ignore_errors=True)

    def test_P3_scan_is_not_empty(self):
        """反空转:扫到的段数必须有下界,**且每个源目录都要有贡献**。

        ★ R86 第 2 轮(红队 P7-R86-D【低】):旧版只有总数下界 100,而真实 1719(**17 倍余量**),
        对「丢一个源目录」**零信号**(把 `SOURCE_DIRS` 收成 `("tests",)` 时仍 1341)。
        ⇒ 本仓 C17 的正解:**覆盖不能靠数字余量,只能靠身份**。
        """
        per = _segments_per_dir()
        self.assertEqual(sorted(per), sorted(SOURCE_DIRS),
                         f"源目录没扫全:{sorted(per)} != {sorted(SOURCE_DIRS)}")
        for sub, n in per.items():
            self.assertGreaterEqual(n, 1, f"{sub}/ 一个段都没扫到 —— 该目录整块脱扫")
        self.assertGreaterEqual(sum(per.values()), 100,
                                f"只扫到 {sum(per.values())} 个段 —— 扫描面塌了")

    def test_P4_disclaimer_is_actually_used(self):
        """反空转(反向):**与那个兜底手段同段**的免责声明必须真的存在。

        ⚠ 没有这一条,把全仓所有原字样删掉就能让 P1 恒绿 —— 那是**删除证据**,不是**修正声明**。
        ⚠ 边界:红队 P7-R86-A 证明旧版(不绑同段)可被 5 行无关注释灌满;本版绑定了同段,
        但**同义换词**仍能绕过(那属于 P1 的固有边界,见模块 docstring)。
        """
        n = _backed_segments()
        self.assertGreaterEqual(
            n, 5,
            f"只有 {n} 处**同段**声明了「{DISCLAIMER}此控制」—— "
            f"要么漏改,要么有人把原字样删了充数(P1 会因此空转)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
