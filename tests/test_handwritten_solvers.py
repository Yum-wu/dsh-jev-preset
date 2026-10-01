# -*- coding: utf-8 -*-
"""
B1:断言库 18 函数 vs jevbench 8 类 numeric,`cagr`/`mdd` **无对应断言**。

缺口(附录 B1):
  `solve.py` 里 `cagr()` 与 `max_drawdown()` 是**手写参考解** ——
  而它们定义的就是「正确答案」。若手写逻辑有 bug,
  **整批 cagr/mdd 题的判分基准就是错的**,而 selftest 只验「参考答案与作答一致」,
  参考答案自己错了也照样全绿(自洽 ≠ 正确)。

这个风险比附录原文描述的更重:原文说的是「必须手写,手写脚本自身有 bug 风险」,
实测确认:**手写解就在判分路径上**。

判据(预注册,R9):
  T1 手写解的**边界行为**必须有独立于自身的性质测试 ——
     对称性、恒等式、单调性、已知闭式解。属性自洽仍可能与外部标准不同,
     所以 T1 只要求「有属性测试」,性质本身的正确性另由 T2 用闭式解钉。
  T2 至少若干条用例必须与**独立的闭式/已知解**比对,而非与自身比对。
  T3 零/负数/空序列等退化输入必须有**显式行为**(抛错或返回约定值),不能静默出错值。
  T4 若这些性质被违反,判分必须**显式失败**,不得静默给出错误答案。
"""
import os
import sys
import unittest
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "benchmarks", "accuracy"))

from jevbench.solve import cagr, max_drawdown  # noqa: E402


class TestHandWrittenSolvers(unittest.TestCase):
    """手写参考解的性质测试。

    ⚠ 这些测试**不能**证明参考解与外部标准一致 ——
    它们只能锁住「已知的已知」(闭式解、恒等式、退化行为),
    从而让「手写解悄悄改错」变成可检出的事件。
    """

    def test_T1_cagr_identity_is_exact(self):
        """恒等式:期初 = 期末 ⇒ CAGR = 0。跨任意天数都应为 0.00。"""
        for days in (1, 30, 365, 1000):
            with self.subTest(days=days):
                d0 = date(2020, 1, 1)
                d1 = date.fromordinal(d0.toordinal() + days)
                self.assertEqual(cagr("100", "100", d0.isoformat(), d1.isoformat()), "0.00",
                    f"期初=期末时 CAGR 必须为 0.00({days} 天)")

    def test_T1_cagr_is_monotonic_in_return(self):
        """单调性:期末越大 ⇒ CAGR 越大。"""
        d0, d1 = date(2020, 1, 1), date(2021, 1, 1)   # 366 天(2020 闰年)
        vals = [float(cagr("100", e, d0.isoformat(), d1.isoformat()))
                for e in ("110", "120", "90", "60")]
        # 90 < 110 < 120
        self.assertLess(vals[3], vals[2], "期末 60 的 CAGR 应 < 期末 90")
        self.assertLess(vals[2], vals[0], "期末 90 的 CAGR 应 < 期末 110")
        self.assertLess(vals[0], vals[1], "期末 110 的 CAGR 应 < 期末 120")

    def test_T2_cagr_matches_closed_form(self):
        """T2:必须与**独立闭式解**比对,而不是与自身比对。

        闭式:((end/start)^(365/days) - 1) * 100,
        用 Python float 的 `pow` 独立实现,与 solve.py 的 `ln/exp` 路径互为交叉验证。

        ⚠ 短区间(days < 10)年化会溢出到 1e8 量级 —— 那是**数学事实**,
        不是 bug。故短区间只要求「显式、可读地失败」,不要求给出数值。
        """
        long_span = [
            ("100", "150", date(2020, 1, 1), date(2021, 1, 1)),
            ("10000", "8200", date(2019, 3, 15), date(2024, 11, 2)),
            ("5000", "5000", date(2018, 1, 1), date(2023, 6, 30)),
        ]
        for start, end, d0, d1 in long_span:
            with self.subTest(start=start, end=end):
                days = (d1 - d0).days
                closed = ((float(end) / float(start)) ** (365.0 / days) - 1) * 100
                got = float(cagr(start, end, d0.isoformat(), d1.isoformat()))
                # 判据修正(红队 6c40869b 4a 实证):初版用 `places=1`(容差 0.05),
                # 实测「整体偏移 0.1%」的错误实现**仍全绿** —— 比既有的
                # `test_cagr_vs_float`(绝对容差 0.0051)更松,精度维度上是净倒退。
                # 现改为**绝对容差 0.006**,与 solve.py 的四舍五入粒度(0.005)对齐,
                # 使 0.04% 级偏移必然报红(红队实测该偏移最大偏差 0.016 > 0.006)。
                self.assertAlmostEqual(
                    got, closed, delta=0.006,
                    msg=f"与独立闭式解不符:手写={got} 闭式={closed:.6f} "
                        f"偏差={abs(got - closed):.6f}")

        # 结果位数超过 Decimal 精度时必须抛**可读**的错。
        # ⚠ 判据不写死「短区间」:红队 6c40869b 实测 days=1 但 ratio=1.0001 时
        # **不抛错**(静默返回 3.72)—— 边界由结果位数决定,与 days 无关。
        for start, end, d0, d1 in [("1", "2", date(2020, 1, 1), date(2020, 1, 2)),
                                   ("100", "150", date(2020, 1, 1), date(2020, 1, 2))]:
            with self.subTest(场景=f"超精度 days={(d1 - d0).days}"):
                with self.assertRaises(ValueError) as cm:
                    cagr(start, end, d0.isoformat(), d1.isoformat())
                self.assertNotIn("InvalidOperation", str(cm.exception),
                    "异常信息不得是零信息量的 InvalidOperation")
                self.assertRegex(str(cm.exception), r"精度|位数|days",
                    "异常信息必须能定位原因(精度/位数/天数)")

    def test_T1_mdd_monotonic_curve_is_zero(self):
        """单调上涨的净值序列,最大回撤必为 0。"""
        r = max_drawdown(["100", "110", "120", "130"])
        self.assertEqual(r["mdd_pct"], "0.00", "单调上涨序列的最大回撤必须为 0")
        self.assertEqual(r["peak_index"], r["trough_index"],
            "回撤为 0 时 peak/trough 下标应相同(或按约定取最早)")

    def test_T1_mdd_known_value(self):
        """已知闭式:100 → 120 → 60 → 90。峰值 120,谷值 60,回撤 = (120-60)/120 = 50%。"""
        r = max_drawdown(["100", "120", "60", "90"])
        self.assertEqual(r["mdd_pct"], "50.00",
            f"手写回撤 = {r['mdd_pct']},闭式 = 50.00 —— 判分基准本身就错了")
        self.assertEqual(r["peak_index"], 1, "峰值下标应为 1")
        self.assertEqual(r["trough_index"], 2, "谷值下标应为 2")

    def test_T1_mdd_ties_take_earliest(self):
        """多个相同最大回撤须取**最早**出现者(须与题面约定一致)。"""
        # 100→50(回撤 50%), 100→50 再次:下标 0→1 与 2→3 回撤相同
        r = max_drawdown(["100", "50", "100", "50"])
        self.assertEqual(r["mdd_pct"], "50.00")
        self.assertEqual((r["peak_index"], r["trough_index"]), (0, 1),
            "相同最大回撤须取最早出现者")

    def test_T3_degenerate_inputs_are_explicit(self):
        """T3:退化输入必须有**显式**行为,不能静默给出错误值。

        判据修正(红队 6c40869b 变体 N1 实证:本条初版
        `except (IndexError, ValueError, ZeroDivisionError)` **全部接受** ——
        于是把「显式检查」删掉、只在循环外读 `equity[0]` 偶然抛 `IndexError`
        也能全绿通过。「抛了某个错」≠「显式检查了」。
        现要求:空序列必须抛 **ValueError** 且信息里点明「为空/序列」。

        `max_drawdown` 遇首元素为 0 会除零,亦须显式失败。
        """
        with self.subTest(场景="空序列"):
            with self.assertRaises(ValueError) as cm:
                max_drawdown([])
            self.assertRegex(
                str(cm.exception), r"空|序列",
                "空序列必须抛 ValueError 并点明原因;"
                "靠 IndexError 偶然崩溃不算显式检查(红队变体 N1)")

    def test_T9_guards_are_covered(self):
        """N9/N10:我新加的两个守卫(`期初=0`、`峰值=0`)此前**删掉后测试仍全绿** ——
        那是死代码级防御。现各配一条用例,删掉守卫即报红。"""
        with self.subTest(场景="cagr 期初为 0"):
            with self.assertRaises(ValueError) as cm:
                cagr("0", "150", "2020-01-01", "2021-01-01")
            self.assertRegex(str(cm.exception), r"期初|为 0|比值",
                "期初=0 必须显式失败(删掉该守卫会退化成 ZeroDivisionError 而漏过)")
        with self.subTest(场景="mdd 峰值为 0"):
            with self.assertRaises(ValueError) as cm:
                max_drawdown(["0", "50", "20"])
            self.assertRegex(str(cm.exception), r"峰|0",
                "峰值=0 时回撤无定义,必须显式失败")

    def test_T3_cagr_zero_span_raises(self):
        """T3:期初 = 期末日(days=0)必须**显式**失败,且错误信息要能定位原因。

        判据修正(自查 V2 变体实测:把 `if days <= 0` 改成 `if False` 仍全绿 ——
        因为 `DivisionByZero` 同样满足 `assertRaises((ZeroDivisionError, ValueError))`。
        即「抛了某个错」不等于「显式检查了」:删掉检查,靠偶然的除零也能过。
        这里改为**要求 ValueError 且信息含 days=0**,使「删掉显式检查」必然报红。
        """
        d0 = date(2020, 1, 1)
        with self.assertRaises(ValueError) as cm:
            cagr("100", "150", d0.isoformat(), d0.isoformat())
        self.assertRegex(
            str(cm.exception), r"days=0|区间非法",
            "days=0 必须是**显式**的 ValueError 且指明原因;"
            "靠 ZeroDivisionError 蒙混过关不算(删掉显式检查也会那样过)")
        # end < start 也一样,不得靠负 days 蒙混
        with self.assertRaises(ValueError):
            cagr("100", "150", "2020-01-02", "2020-01-01")


if __name__ == "__main__":
    unittest.main(verbosity=2)
