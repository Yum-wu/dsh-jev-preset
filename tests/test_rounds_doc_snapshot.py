"""Round 58:docs/self-optimize-rounds.md 里贴的 g_check 输出快照不得含「会过期的数字」。

背景(全部来自外部红队实测,不是自评):
- Round 54 §9 贴了 `A5 自查检出率 = 9/35(25.7%)`;Round 55 收尾改成 `10/36(27.8%)`;
  Round 55 补记自己又加了一条台账行 → 实测变成 `11/37(29.7%)`,**改完当场又过期**。
- 红队 `0db255bd` 与 Round 58 红队两路都点名:就地改数字治标不治本 ——
  **只要台账再结算一条,这段贴死的输出必然再次过期**。

治本:该块**不含任何随台账/套件数增长的数字**。
本文件守卫的就是这条,并用「制造一次违规」证明判据不是空转。
"""

import os
import pathlib
import re
import shutil
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
DOC = REPO / "docs" / "self-optimize-rounds.md"

BEGIN = "<!-- BEGIN:g-check-snapshot -->"
END = "<!-- END:g-check-snapshot -->"

#: 会随台账增长 / 套件增删而失效的数字。快照块里一律不得出现。
#: 用 dict(而非 tuple)是为了让 T3 能**逐模式**实例化 ——
#: 只实例化一个模式时,删掉其余模式的正则不会有任何测试报红(实测)。
VOLATILE = {
    "A5 检出率": r"自查检出率[^\n]{0,10}?\d+\s*/\s*\d+",  # 分子分母随台账增长
    "最新轮百分比": r"最新轮\s*\d+\s*为\s*[\d.]+%",
    "裸百分比": r"\d+\.\d+\s*%",
    "Ran 行数": r"Ran\s*(?:行\s*)?\d+\s*(?:条|个测试|tests?)",
    "--list 项数": r"--list\s*\d+\s*项",
    "期望条数": r"期望\s*\d+",
    "冒烟比例": r"冒烟\s*\d+\s*/\s*\d+",
}

#: 每个模式一条**必定匹配**的样本,T3 用它在镜像里制造违规。
SAMPLES = {
    "A5 检出率": "A5 自查检出率 = 11/37(29.7%)",
    "最新轮百分比": "最新轮 55 为 27.8%",
    "裸百分比": "G5 判定: 25.7%",
    "Ran 行数": "Ran 行 28 条",
    "--list 项数": "--list 18 项",
    "期望条数": "· 冒烟 6/6 符合退出码契约(期望 18)",
    "冒烟比例": "· 冒烟 6/6 符合退出码契约",
}


def _scan(text):
    """返回快照块内命中 VOLATILE 的 (行号, 行内容, 模式);标记缺失时返回 None。"""
    if BEGIN not in text or END not in text:
        return None
    region = text.split(BEGIN, 1)[1].split(END, 1)[0]
    bad = []
    for i, line in enumerate(region.splitlines(), 1):
        for name, pat in VOLATILE.items():
            if re.search(pat, line):
                bad.append((i, line.strip(), name))
                break
    return bad


class T_RoundsDocSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix=f"jev_r58_mirror_{os.getpid()}_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.doc = DOC.read_text(encoding="utf-8")

    # T1 标记必须存在 —— 否则 T2/T3 会「全绿却什么都没测到」(空转判据)
    def test_T1_snapshot_markers_exist(self):
        self.assertIn(BEGIN, self.doc, "缺少快照起始标记")
        self.assertIn(END, self.doc, "缺少快照结束标记")
        self.assertLess(self.doc.index(BEGIN), self.doc.index(END), "标记顺序反了")
        self.assertEqual(self.doc.count(BEGIN), 1, "起始标记必须唯一")
        self.assertEqual(self.doc.count(END), 1, "结束标记必须唯一")

    # T1b 区域必须非空 —— 否则 T2 扫一个空串,恒绿(空转判据)
    def test_T1b_snapshot_region_is_not_empty(self):
        region = self.doc.split(BEGIN, 1)[1].split(END, 1)[0]
        lines = [l for l in region.splitlines() if l.strip()]
        self.assertGreater(len(lines), 5, f"快照块几乎是空的({len(lines)} 行非空),T2 会变成空转判据")
        self.assertIn("OK G1", region, "快照块丢了结构骨架(OK G1 那行)")

    # T2 真实文档:快照块内不得有会过期的数字
    def test_T2_no_volatile_numbers_in_snapshot(self):
        bad = _scan(self.doc)
        self.assertIsNotNone(bad, "标记缺失,判据未生效")
        self.assertEqual(
            bad, [],
            "快照块里出现了会随台账/套件数过期的数字:\n"
            + "\n".join(f"  L{n}: {t}  ← {p}" for n, t, p in bad),
        )

    # T3 可证伪:**逐个模式**实例化。只测一个模式时,删掉其余模式的正则不会红。
    def test_T3_falsifiable_per_pattern(self):
        self.assertEqual(set(SAMPLES), set(VOLATILE), "SAMPLES 与 VOLATILE 的键必须一一对应")
        missed = []
        for name, pat in VOLATILE.items():
            sample = SAMPLES[name]
            if not re.search(pat, sample):
                missed.append(f"{name}: 样本 {sample!r} 根本不匹配自己的模式 —— 样本写错了")
                continue
            mirror = self.doc.replace(BEGIN, BEGIN + "\n" + sample, 1)
            if mirror == self.doc:
                missed.append(f"{name}: 镜像未改动")
                continue
            if not _scan(mirror):
                missed.append(f"{name}: 注入 {sample!r} 后判据仍全绿")
        self.assertEqual(missed, [], "以下模式是空转的(删掉它也不会红):\n" + "\n".join(missed))

    # T4 元判据:用例**具名清单**(不是计数),防编辑时静默丢用例**与改名**
    def test_T4_case_count(self):
        loaded = sorted(n for n in dir(self) if n.startswith("test_"))
        self.assertEqual(loaded, sorted(CASE_NAMES),
                         "用例集变了 —— 删 / 改名 / 新增用例都必须同步改 CASE_NAMES 并说明原因")


#: 本文件的用例**具名清单**(不是计数)。⚠ 名字而非数字 —— 数字抓不住「改名」。
CASE_NAMES = (
    "test_T1_snapshot_markers_exist",
    "test_T1b_snapshot_region_is_not_empty",
    "test_T2_no_volatile_numbers_in_snapshot",
    "test_T3_falsifiable_per_pattern",
    "test_T4_case_count",
)

if __name__ == "__main__":
    unittest.main()
