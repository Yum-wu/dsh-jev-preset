# -*- coding: utf-8 -*-
"""
断言库的**反向验证缺口**:18 条断言中 9 条从未被验证「会拒绝错答」。

缺口(红队 6c40869b 实测并在本轮复核):
  `tests/test_assertions.py` 里,21 次断言调用中只有 **1 次** `assertRaises`,
  且只针对 `assert_tick_floor`。其余 17 条**全部只有正向冒烟**。

为什么这比「少写几个测试」严重:
  断言库的**全部价值**在于「错的时候会说错」——
  判分侧(persona 唯一的客观真值源)用它决定放不放行。
  一条只会「永远返回 True」的断言,比没有断言**更危险**:
  它让人以为有客观真值源,实际是把「模型说什么就是什么」包装成了「已复算」。
  这条链路正是本仓立论根基(README:「执行断言是本仓唯一统计显著的正向结果」)。
  **若断言本身不会拒绝错答,那个 p=0.0312 就没有意义。**

形态必须分类处理(签名与正向值均**实测**取得,不猜):
  A. **等值型**(末位 expected):喂错的 expected → 必须抛 AssertionError
  B. **布尔型**(末位 expect_*):喂错的期望 → 必须抛 AssertionError
  C. **谓词型**(无 expected,返回 bool):前提被破坏 → 必须抛

⚠ 反向用例的正向值**直接复用** `test_assertions.py` 里已验证可用的实参,
  只改末位 expected/期望。这样失败原因唯一 —— 只能是「它认出了错」,
  不会与「实参形状构造错了」混在一起。
  (初版我猜了一堆实参形状,run 出来全是 TypeError/ValueError ——
   那正是「靠类型异常蒙混」的失败模式。)

判据(预注册,R9):
  T1 18 条断言**每条**都有反向用例,覆盖率可量化
  T2 反向用例只接受 AssertionError —— TypeError/KeyError/ValueError 蒙混不算
  T3 正向用例仍必须通过 —— 否则「拒绝一切」也能当反向用例
  T4 覆盖率数字如实报出,且重名会导致虚高
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "packages", "assertions", "python"))

import jev_assertions as J  # noqa: E402


def _names():
    return sorted(n for n in dir(J)
                  if n.startswith("assert_") and callable(getattr(J, n)))


# 实参直接取自 tests/test_assertions.py(那里已验证可用)
_TICK_ARGS = (67432.178, 0.01)
_TICK_OK = "67432.17"
_ASSETS = [
    {"coin": "USDT", "amount": 10000.0, "price": 1.0, "haircut": 1.0},
    {"coin": "ETH", "amount": 2.0, "price": 3500.0, "haircut": 0.90},
    {"coin": "SOL", "amount": 500.0, "price": 150.0, "haircut": 0.80},
]
_ASKS = [
    {"price": 60000.0, "size": 2.0},
    {"price": 60010.0, "size": 3.5},
    {"price": 60030.0, "size": 5.0},
    {"price": 60100.0, "size": 10.0},
]
_TIERS = [
    {"tier": 1, "max_notional": 50000.0, "mmr": 0.005},
    {"tier": 2, "max_notional": 250000.0, "mmr": 0.01},
    {"tier": 3, "max_notional": 1000000.0, "mmr": 0.02},
]

# ── A. 等值型:(函数, 前置实参, 正确 expected, 错误 expected) ─────────────
EQUALITY_CASES = [
    ("assert_tick_floor", _TICK_ARGS, _TICK_OK, "67432.18"),
    ("assert_tick_ceiling", (0.000034, 0.0001), "0.0001", "0.00003"),
    ("assert_fractional_tick", (104.381, 0.125), "104.375", "104.250"),
    # ⚠ `lot_step` **不能取 1.0** —— 那会让 (b//p//step)*step 与 (b//p)*step 完全相等,
    #   于是 `// step` 这段**核心逻辑**在正向与反向上**都**验不到
    #   (红队 d02d9ff0 变异 M9 实测:漏掉 `// step` 后测试仍全绿,exit=0)。
    #   取 0.01 使两级整除不再退化(75.0 vs 0.75),可分辨。
    ("assert_lot_step_budget", (1500.0, 19.83, 0.01, 50.0), 75, 74),
    ("assert_inverse_contracts", (2.5, 3420.50, 10.0), 855, 854),
    # ⚠ 错值 6.926 与正确值之差**恰好等于容差 0.001**(`abs(x) < 0.001` 靠严格小于才红)。
    #   容差哪天改成 `<=` 或 Decimal 精度一变,它立刻变成永不红的假用例
    #   (红队 d02d9ff0 次要发现 1)。故错值取 6.93,远离边界。
    ("assert_ex_right_price", (28.00, 0, 30, 3.00), "6.925", "6.930"),
    # ⚠ 两个分支都要测:2026-03-06 是 EST(-5),2026-03-09 起是夏令时 EDT(-4)。
    #   只测 EST 的话,一个「永远按 -5 算」的 mutant 能同时通过正反用例
    #   (红队 d02d9ff0 次要发现 2)—— 夏令时分支的判别力为 0。
    ("assert_ny_open_utc", ("2026-03-06", "09:30:00"), "14:30:00", "13:30:00"),
    ("assert_ny_open_utc", ("2026-03-09", "09:30:00"), "13:30:00", "14:30:00"),
    # ⚠ `expected_price=2105.98` 是**抄来的近似值**,真值 2106.018054,
    #   偏差 0.038 = 容差 0.05 的 **76.1%** —— 它靠容差蒙过(红队 d02d9ff0 实测)。
    #   抄 `test_assertions.py` 的代价就在这里:正向值错了,两边一起绿。
    #   故此处改用 lib 自身的精确值,并在下面用 T6 钉住「正向值与真值一致」。
    ("assert_amm_constant_product", (1000000.0, 500.0, 50000.0, 0.003),
     ("23.741496", "2106.018054"), ("23.750000", "2106.018054")),   # 只错 dy
    ("assert_amm_constant_product", (1000000.0, 500.0, 50000.0, 0.003),
     ("23.741496", "2106.018054"), ("23.741496", "2200.000")),     # 只错 eff_price
    ("assert_reverse_split_volume_factor", (0.1,), (10.0, 0.1), (9.0, 0.1)),
    ("assert_reverse_split_volume_factor", (0.1,), (10.0, 0.1), (10.0, 0.2)),
    ("assert_orderbook_vwap", (12.5, _ASKS), (60030.80, 750385.0),
     (60040.00, 750385.0)),                                       # 只错 vwap
    ("assert_orderbook_vwap", (12.5, _ASKS), (60030.80, 750385.0),
     (60030.80, 750500.0)),                                       # 只错 cost
    ("assert_collateral_haircut", (_ASSETS,), (92000.0, 76300.0),
     (93000.0, 76300.0)),                                         # 只错名义
    ("assert_collateral_haircut", (_ASSETS,), (92000.0, 76300.0),
     (92000.0, 80000.0)),                                         # 只错折算
    ("assert_linear_liq_price", (10000.0, 5.0, 50000.0, 0.01, 0.0005),
     48509.35, 48000.00),
    ("assert_inverse_liq_price", (10.0, 10000, 10.0, 3000.0, 0.02), 2353.85, 2000.00),
    ("assert_tiered_mm", (400000.0, _TIERS), (5250.0, 2750.0), (5000.0, 2750.0)),
    ("assert_tiered_mm", (400000.0, _TIERS), (5250.0, 2750.0), (5250.0, 2500.0)),
]

# ── B. 布尔型:(函数, 前置实参, 正确期望, 错误期望) ─────────────────────
BOOLEAN_CASES = [
    ("assert_almgren_chriss_impact", (500000.0, 10000000.0, 0.025, 15.0), True, False),
    ("assert_leverage_fee_buffer", (10000.0, 10.0, 0.0006, 100000.0), True, False),
    ("assert_clock_monotonic", (100, 105), True, False),
]

# ── C. 谓词型:(函数, 正常前提, 前提被破坏) ──────────────────────────────
# ⚠ `assert_forward_adj_log_return_safe` 的可破坏前提是 **ex_price ≤ 0**
#   (mult = ex/c;hist 非正时 adj_hist ≤ 0 → 断言抛)。
#   我初版用 ex=99(比前收大)当「破坏前提」,方向反了 —— ex 越大 mult 越大,
#   adj_hist 越正,断言正确地没有报警。**是我用例错,不是断言坏。**
PREDICATE_CASES = [
    ("assert_forward_adj_log_return_safe", (28.00, 6.925, 1.20), (28.00, 0.0, 1.20)),
]


def _call(fn, args, tail):
    """按末位参数是元组/标量的实际情况展开。"""
    if isinstance(tail, tuple):
        return fn(*args, *tail)
    return fn(*args, tail)


class TestAssertionsRejectWrongValues(unittest.TestCase):

    def test_T1_every_assertion_has_reverse_case(self):
        names = _names()
        self.assertEqual(len(names), 18, f"断言数从 18 变成 {len(names)},解析或口径需重估")
        covered = ({c[0] for c in EQUALITY_CASES} | {c[0] for c in BOOLEAN_CASES}
                   | {c[0] for c in PREDICATE_CASES})
        missing = sorted(set(names) - covered)
        self.assertEqual(
            missing, [],
            f"这些断言**没有反向验证**用例 —— 从未检查过「会不会拒绝错答」: {missing}")

    def test_T2_equality_cases_reject_wrong_expected(self):
        for name, args, good, bad in EQUALITY_CASES:
            with self.subTest(断言=name):
                fn = getattr(J, name)
                self.assertTrue(_call(fn, args, good),
                    f"{name} 对**正确**值 {good!r} 也失败 —— 断言已失效,反例无意义")
                with self.assertRaises(AssertionError,
                                       msg=f"{name} 喂错值 {bad!r} 却没抛 AssertionError "
                                           f"—— 它可能根本不会拒绝错答"):
                    _call(fn, args, bad)

    def test_T2b_boolean_cases_reject_wrong_expectation(self):
        for name, args, good, bad in BOOLEAN_CASES:
            with self.subTest(断言=name):
                fn = getattr(J, name)
                self.assertTrue(fn(*args, good), f"{name} 正向期望 {good!r} 都不通过")
                with self.assertRaises(AssertionError,
                                       msg=f"{name} 喂错期望 {bad!r} 却没抛"):
                    fn(*args, bad)

    def test_T2c_predicate_cases_reject_broken_premise(self):
        for name, good_args, bad_args in PREDICATE_CASES:
            with self.subTest(断言=name):
                fn = getattr(J, name)
                self.assertTrue(fn(*good_args), f"{name} 正常前提都不通过")
                with self.assertRaises(AssertionError,
                                       msg=f"{name} 前提被破坏(除权价 ≤ 0,复权后价格为负)却静默通过 "
                                           f"—— 它不会识破错误前提"):
                    fn(*bad_args)

    def test_T4_reverse_coverage_is_reported(self):
        """覆盖率必须可量化,且不得因**重复条目**而虚高。

        ⚠ 同一断言现在**合法地**有多条反向用例(多分量断言按分量各一条),
        所以不能简单查「断言名不得重复」—— 那会误报。
        真正要防的是**同一条用例被抄两遍**(会让唯一性检查失真)。
        """
        names = _names()
        covered = ({c[0] for c in EQUALITY_CASES} | {c[0] for c in BOOLEAN_CASES}
                   | {c[0] for c in PREDICATE_CASES})
        eq_ids = [(c[0], str(c[3])) for c in EQUALITY_CASES]
        dupes = sorted({i for i in eq_ids if eq_ids.count(i) > 1})
        self.assertEqual(dupes, [],
            f"反向用例有完全重复的条目(断言 + 同一错值),覆盖率会被虚高: {dupes}")
        self.assertEqual(
            len(covered), len(names),
            f"反向覆盖率 {len(covered)}/{len(names)} = {len(covered)/len(names):.0%} —— "
            f"缺口未补齐,不得声称 100%")

    def test_T5_every_expected_component_is_covered(self):
        """多分量断言(两个 expected)的**每个**分量都必须各有一条反向用例。

        自查发现:只改末位时断言仍会抛 —— 但抛的是**前一个** assert,
        于是「去掉前一个 assert 后还能不能抓住」测不出来,等于只覆盖了一半。
        这条把「每个分量都被独立检到」变成可机检的。
        """
        multi = [c for c in EQUALITY_CASES if isinstance(c[3], tuple)]
        by_fn = {}
        for name, _a, good, bad in multi:
            by_fn.setdefault(name, []).append((good, bad))
        for name, pairs in sorted(by_fn.items()):
            n_comp = len(pairs[0][0])
            for i in range(n_comp):
                hits = sum(
                    1 for good, bad in pairs
                    if bad[i] != good[i]
                    and sum(1 for j, v in enumerate(bad) if v != good[j]) == 1)
                with self.subTest(断言=name, 分量=i + 1):
                    self.assertEqual(
                        hits, 1,
                        f"{name} 的第 {i + 1} 个 expected 有 {hits} 条「只错它」的"
                        f"反向用例(应为 1)—— 该分量未被独立覆盖")


    def test_T6_positive_values_are_not_tolerance_dependent(self):
        """反向用例的「正确值」必须**贴近真值**,不能靠容差蒙过。

        红队 d02d9ff0 实测的活例:`assert_amm_constant_product` 的
        `expected_price = 2105.98`,真值 **2106.018054**,偏差 0.038
        = 容差 0.05 的 **76.1%** —— 它「通过」纯粹因为容差宽。
        抄 `test_assertions.py` 的代价正在于此:正向值本身错了,两边一起绿。

        判据:正向值与**独立重算的真值**之差,必须**明显小于**该断言的容差
        (此处取「不超过容差的 1/4」);超过即说明它靠容差蒙过。
        """
        # 由 lib 自身公式独立重算的参考值(不是从 lib 的断言里抄的)
        from decimal import Decimal as D
        x, y, dx, fe = D("1000000"), D("500"), D("50000"), D("0.003")
        g = D(1) - fe
        true_dy = (y * dx * g) / (x + dx * g)
        true_eff = dx / true_dy
        true_vals = {"dy": true_dy, "eff": true_eff}
        tolerances = {"dy": D("0.0001"), "eff": D("0.05")}

        eq = [c for c in EQUALITY_CASES if c[0] == "assert_amm_constant_product"]
        self.assertTrue(eq, "找不到 amm 的反向用例")
        for _name, _args, good, _bad in eq:
            with self.subTest(分量="dy"):
                self.assertLess(abs(D(str(good[0])) - true_vals["dy"]) / tolerances["dy"],
                                D("0.25"),
                                f"正向 dy={good[0]} 与真值 {true_vals['dy']} 的偏差"
                                f"已达容差的 1/4 以上 —— 靠容差蒙过")
            with self.subTest(分量="eff_price"):
                self.assertLess(abs(D(str(good[1])) - true_vals["eff"]) / tolerances["eff"],
                                D("0.25"),
                                f"正向 eff={good[1]} 与真值 {true_vals['eff']} 的偏差"
                                f"已达容差的 1/4 以上 —— 靠容差蒙过")


if __name__ == "__main__":
    unittest.main(verbosity=2)
