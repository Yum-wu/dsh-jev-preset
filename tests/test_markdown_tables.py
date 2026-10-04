# -*- coding: utf-8 -*-
r"""markdown 表格**列数一致性**守卫(全仓)。

## 为什么单列一条(Round 53)

Round 53 修的是「附录状态表 C4 行的裸竖线撑破表格」。
**同一个缺陷类别当天又复发了一次** —— 我给台账写 Round 53 那行时,
正文里引用了 `` `sha256(seed|case_id)` ``,那个**未转义的竖线**
把台账行撑成了 9 格,而 `tools/evasion_audit.py` 直接读到 **0 条**记录
(`test_evasion_audit.py` A1/A2/A2b 红、G5 exit=2)。

**修一处不够 —— 这是类别问题,不是文件问题。**
(Round 50 的教训原话:「按目录划修复范围,而不是按缺陷类别划」。)
所以本条**不扫某个文件**,扫全仓所有 markdown:

    | a | b | c |      ← 表头 3 格
    | x | y | z |      ← 3 格 ✓
    | x | y | z | w |  ← 4 格 ✗ 撑破

## 判据
对每个 markdown 文件,逐段找出连续 `|` 开头的行(表头 + 分隔行 + 数据行),
要求**同一张表内每一行的格数都等于表头格数**。

⚠ **豁免**:`` ``` `` 围栏代码块内的行(那是示例,不是表格)。
⚠ 正文里的裸 `|` 必须写成 `&#124;`(本仓台账已在用这个写法)。
"""
import io
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _fs_guard as fsg  # noqa: E402  —— 共享的「不走出仓根」原语(Round 67)

SKIP_DIRS = {".git", "node_modules", "tmp_jev_path1", "__pycache__"}


def _markdown_files(root=ROOT):
    r"""遍历 `root` 下所有 `.md`。

    ⚠ Round 67:`root` 参数是为了让 T4 能拿**带 junction 的临时仓**验证它
    (与 `test_no_encoding_damage.py` 的 `iter_text_files` 同款)。T1 仍走默认 `ROOT`。

    ⚠ **本条是全仓扫描器,必须做「不走出仓根」剪枝** —— Round 66 修了三个
    `.py` 扫描器却漏了这个 `.md` 扫描器(本仓记过三次的失败形态
    「按文件而非按缺陷类别划修复范围」的**第四次**复发)。`.md` 是**结论载体**,
    被拉进仓外文档会让本仓守卫替**别人的排版**报红。
    """
    out = []
    real_root = os.path.realpath(root)
    for dp, dn, fn in os.walk(root):
        fsg.prune_escaped(dp, dn, real_root)
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            if f.endswith(".md"):
                out.append(os.path.join(dp, f))
    return sorted(out)


def _strip_fences(lines):
    """返回 [(原行号, 行文本)] —— 去掉 ``` 围栏块内的行。"""
    out, fence = [], False
    for i, l in enumerate(lines, 1):
        if l.lstrip().startswith("```"):
            fence = not fence
            continue
        if not fence:
            out.append((i, l))
    return out


def _cell_count(line):
    r"""数一行的单元格数。

    ⚠ **必须先把 `\|`(转义竖线)换成占位符** —— 否则
    `` `(?:\*\*|__)?` `` 这种**正确写法**会被当成 4 格,
    扫出一堆**假违规**(Round 53 实测:8 条报告里 3 条是这么来的)。
    markdown 里 `\|` 表示「字面竖线,不是单元格边界」。
    """
    return len(line.replace("\\|", "\x00").strip().strip("|").split("|"))


def _tables(lines):
    """产出 (起始行号, [格数...], 表头格数)。空行断开一张表。"""
    cur, start = [], None
    for ln, l in _strip_fences(lines):
        if l.startswith("|"):
            if not cur:
                start = ln
            cur.append((ln, _cell_count(l)))
        else:
            if cur:
                yield start, cur
            cur = []
    if cur:
        yield start, cur


class TestMarkdownTableColumns(unittest.TestCase):

    def test_T1_every_table_row_matches_its_header(self):
        r"""同一张表内,每行的格数必须等于表头 —— 否则表格渲染错位。"""
        bad = []
        scanned = 0
        for path in _markdown_files():
            with io.open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
            for start, rows in _tables(lines):
                if len(rows) < 2:
                    continue          # 单行不是表
                scanned += 1
                want = rows[0][1]
                for ln, got in rows[1:]:
                    if got != want:
                        rel = os.path.relpath(path, ROOT).replace("\\", "/")
                        bad.append(f"{rel}:L{ln} 格数={got} 表头={want}(表起于 L{start})")
        # R4 守卫:先确认「测到了」
        self.assertGreater(scanned, 10,
                           f"只扫到 {scanned} 张表,扫描器可能失效 —— 判据前提不成立")
        self.assertEqual(
            bad, [],
            "这些表格行的格数与表头不一致(表格会渲染错位):\n  "
            + "\n  ".join(bad)
            + "\n—— 正文里的裸 `|` 要写成 `&#124;`;行尾别漏 `|`。")

    def test_T2_guard_is_falsifiable(self):
        r"""R9 可证伪:造一张格数不一致的表,扫描器必须报出来。"""
        lines = [
            "| a | b | c |",
            "|---|---|---|",
            "| x | y | z |",
            "| x | y | z | w |",       # ← 坏行
        ]
        bad = []
        for start, rows in _tables(lines):
            want = rows[0][1]
            for ln, got in rows[1:]:
                if got != want:
                    bad.append((ln, got, want))
        self.assertEqual(bad, [(4, 4, 3)],
                         f"扫描器没抓到造出来的坏行: {bad}")

    def test_T2b_escaped_pipe_is_not_a_cell_boundary(self):
        r"""`\|` 是字面竖线,**不是**单元格边界 —— 否则正确写法会被扫成违规。

        Round 53 实测:第一版扫描器把 `` `(?:\*\*|__)?` `` 数成 4 格,
        报了 8 条违规,其中 **3 条是假的**。**假阳性会让人去改本来正确的东西。**
        """
        self.assertEqual(_cell_count("| a | `x \\| y` | c |"), 3,
                         "转义竖线被当成了单元格边界")
        self.assertEqual(_cell_count("| a | x | y | z |"), 4,
                         "真竖线没被数到")

    def test_T3_fence_blocks_are_skipped(self):
        r"""围栏代码块里的示例表格不算表格(否则本文件的 docstring 会自曝)。"""
        lines = [
            "```",
            "| a | b | c |",
            "| x | y | z | w |",
            "```",
            "| p | q |",
            "|---|---|",
        ]
        seen = [(s, r) for s, r in _tables(lines)]
        self.assertEqual(len(seen), 1, f"围栏块没被跳过: {seen}")
        self.assertEqual(len(seen[0][1]), 2, f"把围栏内的行也扫进来了: {seen}")

    def test_T4_scan_does_not_escape_repo_via_junction(self):
        r"""T4:`.md` 扫描器**不得跟随 junction** 把仓外文档拉进来(Round 67)。

        ⚠ Round 66 在 `iter_text_files` / `scan_syntax_warnings` / `iter_py_files`
        三个 `.py` 扫描器上修了同一个洞,却**漏了这个 `.md` 扫描器** —— 本仓记过
        三次的失败形态「**按文件而非按缺陷类别划修复范围**」的**第四次**复发。
        Round 67 用 AST 普查全仓递归遍历器才发现它(单点读代码看不见)。

        为什么 `.md` 比 `.py` 更该守:`.md` 是**结论载体**。junction 指向仓外时,
        仓外文档的排版错误会让**本仓的守卫**报红 —— 信号被别人的文档污染。
        """
        lab, outside = fsg.make_junction_lab(self, prefix="jev_t4_")
        (lab / "doc.md").write_text("| a | b |\n|---|---|\n| x | y |\n", encoding="utf-8")
        (outside / "evil.md").write_text(
            "| a | b |\n|---|---|\n| x | y | z |\n", encoding="utf-8")
        rels = sorted(os.path.relpath(p, lab) for p in _markdown_files(lab))
        self.assertEqual(
            [r for r in rels if fsg.JUNCTION_NAME in r], [],
            f"`.md` 扫描器跟随 junction 把**仓外**文档拉进了扫描范围:{rels}")
        # 可证伪:扫描器必须**确实**扫到了仓内 markdown,否则上面那句在空集上恒真
        self.assertIn("doc.md", rels, "扫描器没扫到仓内 markdown")


if __name__ == "__main__":
    unittest.main(verbosity=2)
