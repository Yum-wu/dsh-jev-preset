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
"""
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

EXCLUDE_DIRS = {"node_modules", ".git", "__pycache__", "tmp_jev_path1", ".pytest_cache"}
EXTS = (".py", ".md", ".yml", ".yaml", ".mjs", ".js", ".json",
        ".ps1", ".psm1", ".log", ".txt")
# 用 chr() 构造,绝不写字面量 —— 否则本文件会检出自己,永远红
FFFD = chr(0xFFFD)


def iter_text_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if fn.endswith(EXTS):
                yield os.path.join(dirpath, fn)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
