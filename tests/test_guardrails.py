r"""
断言库的**护栏(guardrail)零覆盖**:风控护栏删掉后测试仍全绿。

缺口(红队 d02d9ff0 用变异矩阵实测):
  断言库共 **28 条 assert 语句**,逐条删掉后观察 `test_assertions_reverse.py` 是否变红:
    23 条有判别力,**5 条删掉后全绿**:
      lot:budget_penetration     `assert notional <= b`             <- 预算穿透
      lot:min_notional          `assert notional >= min_not`        <- 低于最小名义
      vwap:depth_sufficient     `assert rem == 0`                  <- 深度不足
      fwd_adj:adj_price>0       `assert adj_hist > 0`               <- 复权价非正
      ny_open:fallback 分支                                       <- 时区降级分支

## ⚠ 本文件在 Round 22 被红队推翻过一次,教训写在这里

Round 19 我把其中三条「钉成回归项」,实现方式是**自己重算一遍公式**:
  G1(预算穿透死代码):在测试里重算 `qty = (B//P//S)*S`,**从不调用** `assert_lot_step_budget`;
  G8(log finite 不可达):在测试里自己遍历输入算 `math.log`,**从不调用**被测函数;
  G6:只 `assertEqual(len(guards), 5)` —— 同义反复。

红队 39f52d8f 用变异实测证伪(2026-10-01):
  删光 `assert_lot_step_budget` 的全部 assert → G1 仍 **exit=0 全绿**;
  删光 split.py 第 32+36 行 → G8 仍 **exit=0 全绿**。

即:**这三个用例钉的是我自己的计算,不是被测代码**,对实现的任何改动零反应,
却以「钉成回归项」的名义制造了覆盖感的假象。这是本循环第 11 次「声明 > 实现」。

三条教训,已固化进本文件的设计规则:
  规则 A 用例必须**调用被测函数**。自证型断言没有判别力,再「严谨」也没有。
  规则 B `assertRaises(AssertionError)` **必须校验消息文本**。同一函数里有多条 assert 时,
          兄弟 assert 抢先触发会让用例假绿 —— 红队实测 floor→ceil 变异下,
          G2/G7 抛的是 `[预算穿透]`,而它们声称测的是另外两条。
  规则 C 「某条护栏不可达 / 恒真」是**变异测试的结论**,不是单元测试能表达的性质。
          单元测试无法证明「删掉它测试仍绿」—— 那恰恰说明测试没覆盖它。
          这类事实进 docs,并由 `tests/mutate_guardrails.py` 负责,不由本文件假装。

## 判据(预注册,R9)
  T1 每条护栏都必须有独立用例:喂一个**会触发该护栏**的输入,
     必须抛 AssertionError **且消息来自那一条 assert**。
  T2 护栏用例与期望值用例是**不同的失败模式**:
     护栏用例喂「越界」(消息=护栏名),期望值用例喂「结果错但没越界」(消息=数值不符)。
  T3 `ny_open` 的**正常分支与降级分支**都要覆盖 —— 只测一个分支,
     「永远按同一规则算」的 mutant 能过两个用例(夏令时判别力为 0)。
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "packages", "assertions", "python"))

import jev_assertions as J  # noqa: E402
from jev_assertions import calendar as _cal  # noqa: E402


class TestGuardrailAsserts(unittest.TestCase):
    r"""风控护栏:「越界时必须报错」,而不是「结果错时必须报错」。

    与 `test_assertions_reverse.py` 的区别:
       那份喂「**算出来的值**与期望不符」;本份喂「**输入本身就越界**」。
       两者是不同的失败模式,不能用彼此的用例顶替。

    每条用例都校验**错误消息文本**(规则 B),以证明报错的是被测的那一条 assert,
    而不是同函数里另一条抢先触发。
    """

    def test_G2_min_notional_violation_is_caught(self):
        """低于最小名义价值:必须由「低于最小名义价值」那条 assert 报错。

        预算 1500 / 价 19.83 / step 0.01 → qty=75、名义 1487.25,
        故 min_notional 取 2000 才越界。
        (min 取 50 时 1487 > 50 没越界,报的是 `[LotSize 失败]` 而非本条 —— 规则 B 就是防这个。)
        """
        with self.assertRaises(AssertionError) as cm:
            J.assert_lot_step_budget(1500.0, 19.83, 0.01, 2000.0, 75)
        self.assertIn("低于最小名义价值", str(cm.exception),
            "必须由「低于最小名义价值」报错;若报的是「预算穿透」或「LotSize 失败」,"
            "说明触发的不是本条护栏(规则 B)")

    def test_G3_insufficient_depth_is_caught(self):
        """订单簿深度不足:买不完却当作成交 → 必须报错。

        ⚠ 深度护栏(slippage.py)**先于** VWAP/成本两条数值校验执行。
        故 expected 必须配成**按已成交部分算出的真实值**:
        深度只有 2.0 + 3.5 = 5.5 手 < 12.5,已成交 cost = 2*60000 + 3.5*60010 = 330035.00,
        vwap = 330035 / 12.5 = 26402.80。这样除深度护栏外没有任何 assert 会抛。
        (红队 39f52d8f 独立 Decimal 复算确认这两个值正确,非编造。)
        """
        asks = [{"price": 60000.0, "size": 2.0}, {"price": 60010.0, "size": 3.5}]
        with self.assertRaises(AssertionError) as cm:
            J.assert_orderbook_vwap(12.5, asks, 26402.80, 330035.00)
        self.assertIn("深度不足", str(cm.exception),
            "必须由**深度护栏**报错;若报的是「总成本不匹配」/「VWAP不匹配」,"
            "说明 expected 没配对,测的不是这条护栏")

    def test_G4_nonpositive_adjusted_price_is_caught(self):
        """前复权价格非正 → 对数收益率失效:必须由 split.py 第 32 行报错。

        ⚠ 本条曾误测 split.py 第 36 行(`isnan/isinf(log_ret)`)。那条**不可达** ——
        第 32 行先拦下 `adj_hist <= 0`,永远走不到 log 计算。变异实测:阉割第 36 行测试全绿。
        而喂 ex_price=0 时报出来的是第 32 行的「前复权价格非正」,不是第 36 行。
        这就是规则 B 要防的「上游 assert 冒充下游护栏」。
        """
        for args, why in (((28.00, 0.0, 1.20), "除权价 0 → 复权价 0"),
                          ((28.00, 1.0, 0.0), "历史价 0 → 复权价 0"),
                          ((28.00, -2.0, 1.0), "除权价为负 → 复权价负")):
            with self.subTest(输入=args):
                with self.assertRaises(AssertionError) as cm:
                    J.assert_forward_adj_log_return_safe(*args)
                self.assertIn("前复权价格非正", str(cm.exception),
                              f"{why}: 必须由第 32 行报错。若抛的是 math domain error 之类"
                              f"未声明异常,说明第 32 行已被移除 —— 本用例的判别力来源错了")

    def test_G5_ny_open_covers_both_tz_branches(self):
        """T3:冬令时与夏令时**两个分支**都必须有护栏级用例。

        只测一个分支时,「永远按 -5 算」的 mutant 能同时通过正反用例。
        """
        for label, (d, t, want) in (("冬令时", ("2026-03-06", "09:30:00", "14:30:00")),
                                    ("夏令时", ("2026-03-09", "09:30:00", "13:30:00"))):
            with self.subTest(分支=label):
                self.assertTrue(J.assert_ny_open_utc(d, t, want), f"{label} 正向用例不通过")
                other = "13:30:00" if want == "14:30:00" else "14:30:00"
                with self.assertRaises(AssertionError, msg=f"{label} 用错时区答案({other})却通过了"):
                    J.assert_ny_open_utc(d, t, other)

    def test_G6_ny_open_fallback_branch_is_covered(self):
        r"""T3 续:**降级分支**(无 tz 后端时走手算偏移)此前零覆盖。

        红队 39f52d8f 用 `sys.settrace` 实测:本机 zoneinfo 可用,
        `calendar.py` 的降级分支(第 36–41 行)**一行都没执行**,
        而它仍被算进「5 条护栏」的清单里 —— 覆盖感是假的。

        降级分支**不是不可测**,只是要主动把 zoneinfo 置空才走得到:

            降级 冬令时正向: True
            降级 反向被抓: [夏令时开盘对齐失败/降级] 日期=2026-03-06, 期望UTC=13:30:00, 实际=14:30:00

        两条分支的错误消息文本也不同(降级带「/降级」后缀),故消息校验可证明
        报错/通过确实来自降级路径而非正常路径。
        """
        original = _cal.zoneinfo
        _cal.zoneinfo = None                      # 强制走手算降级
        try:
            with self.subTest(降级分支="正向"):
                self.assertTrue(J.assert_ny_open_utc("2026-03-06", "09:30:00", "14:30:00"),
                                "降级分支正向用例不通过")
            with self.subTest(降级分支="反向"):
                with self.assertRaises(AssertionError) as cm:
                    J.assert_ny_open_utc("2026-03-06", "09:30:00", "13:30:00")
                self.assertIn("/降级", str(cm.exception),
                              "错误消息必须来自**降级分支**;若含的是正常分支文案,"
                              "说明 zoneinfo 没被真正置空,本用例测的仍是正常路径")
        finally:
            _cal.zoneinfo = original

    def test_G7_the_three_lot_asserts_do_not_shadow_each_other(self):
        """规则 B 的直接检验:`assert_lot_step_budget` 里三条 assert 必须**各报各的**。

        该函数有三条 assert(预算穿透 / 低于最小名义价值 / LotSize 失败)。
        用例若只 `assertRaises(AssertionError)` 不看消息,兄弟 assert 抢先触发就会假绿
        —— 红队实测 floor→ceil 变异下,G2/G7 抛的都是 `[预算穿透]`。
        """
        # ① 只有「低于最小名义价值」该触发:1487.25 <= 1500(不穿透),1487.25 < 2000
        with self.assertRaises(AssertionError) as cm:
            J.assert_lot_step_budget(1500.0, 19.83, 0.01, 2000.0, 75)
        self.assertIn("低于最小名义价值", str(cm.exception))

        # ② 只有「LotSize 失败」该触发:notional=1487.25 正常,expected=74 与 qty=75 不符
        with self.assertRaises(AssertionError) as cm:
            J.assert_lot_step_budget(1500.0, 19.83, 0.01, 50.0, 74)
        self.assertIn("LotSize 失败", str(cm.exception),
                      "min_notional=50 不越界、预算也不穿透,只可能是期望值不符;"
                      "若报的是前两条,说明兄弟 assert 抢接了")

        # ③ 全部正常 → 必须通过(否则「拒绝一切」也能当护栏用例)
        self.assertTrue(J.assert_lot_step_budget(1500.0, 19.83, 0.01, 50.0, 75))


if __name__ == "__main__":
    unittest.main(verbosity=2)
