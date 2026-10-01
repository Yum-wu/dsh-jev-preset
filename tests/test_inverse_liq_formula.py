# -*- coding: utf-8 -*-
r"""
`assert_inverse_liq_price` 的公式是**错的** —— 本文件把「错」钉成可回归的事实。

## 缺口(2026-10-01 Round 27 实测)

`packages/assertions/python/jev_assertions/margin.py` 第 63 行:

```python
p_liq = (c * fv * (1 + mmr)) / (balance_coin + (contracts * face_val / entry_price))
```

其 docstring 自称「双曲线非线性方程」,但 `entry_price` 只出现在分母里一个
`contracts * face_val / entry_price` 的小项中 —— 当保证金远大于该小项时,这一项可忽略。

**实测(b=10000, c=5, fv=1, mmr=0.01)**:

```
基准 e=50000        -> P_liq = 0.00050500
  entry_price= 25000 -> 0.0005050000  (相对基准 -0.000%)
  entry_price= 50000 -> 0.0005050000  (相对基准 +0.000%)
  entry_price=100000 -> 0.0005050000  (相对基准 +0.000%)
  entry_price=500000 -> 0.0005050000  (相对基准 +0.000%)
```

**入场价放大 20 倍,强平价一位数字都没变。**

而按反向(币本位)合约做空的物理推导 —— 持仓币数 `n = c*fv/e`,
亏损(coin) `= n*(P-e)/e`,令亏损吃光保证金 `b`:`P = e + b*e^2/(c*fv)`:

```
b=10000 c=5 fv=1 e=50000: 推导 P_liq = 5000000050000.0000 | lib P_liq = 0.0005050000 | 比值 9.901e+15
b=10000 c=5 fv=1 e=100000: 推导 P_liq = 20000000100000.0000 | lib = 0.0005050000 | 比值 3.960e+16
b=1     c=5 fv=1 e=50000: 推导 P_liq = 500050000.0000 | lib = 5.0494950505 | 比值 9.903e+07
```

不仅量级差 10¹⁵ 倍,**方向也是反的**:做空亏损需要**价格上涨**才触发强平,
推导值远大于入场价,而 lib 给出的是远**小于**入场价(意为「几乎立刻强平」)。

## 为什么本文件只钉「参数敏感性」这一条

L1(入场价敏感性)是**无争议**的:入场价是强平价最重要的参数,
任何业务定义下它放大 20 倍,强平价都不可能纹丝不动。故把它做成会红的回归项。

而「正确的公式是什么」取决于三个尚未确认的业务约定 —— 方向(空头/多头)、
`mmr` 的位置、以及 `balance_coin` 是否为币本位保证金。**这是业务判断,不是机械修复。**
故 L2(量级)/ L3(方向)只作为分析记录在本文档里,**不写成断言** ——
否则就是「拿我的猜测当判据」。

## 判据(预注册,R9)

  L1 入场价放大 20 倍,强平价必须显著变化(相对变化 > 10%)。
     当前实现相对变化 = 0.000% → 本项为红。

## 修复归属

**本轮不改 `margin.py`。** 正确公式需业务拍板(A/B 方案见
`docs/self-optimize-rounds.md` Round 27 记账)。本测试将保持**红**,
直到正确公式落地 —— 这是有意的:一条红着的测试比一条假装绿的测试诚实。

⚠ 本文件**有意不挂进 `npm test`**(挂进去会让 G1 全红,阻断后续所有回归)。
按 `tests/test_means_markers.py::T4` 的规矩,不挂必须在文件里声明 EXPECTED_RED。
"""
EXPECTED_RED = "L1: margin.py:63 的 inverse_liq 公式已实测证伪(入场价变 20 倍结果不变);待业务拍板后修"

import os
import sys
import unittest
from decimal import Decimal as D

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "packages", "assertions", "python"))

from jev_assertions.margin import assert_inverse_liq_price  # noqa: E402


def lib_p_liq(balance_coin, contracts, face_val, entry_price, mmr):
    """复刻 margin.py 第 63 行的算式,用于「偷看」被测函数的真实输出。

    ⚠ 这不是被测函数本身,只是同一算式在测试侧的重现 ——
    L1 要比较的是「同一组输入下结果随入场价怎么变」,
    与断言内部的比较逻辑无关,因此可直接算,不必先猜一个 expected 再看它报不报错。
    """
    b, c, fv = D(str(balance_coin)), D(str(contracts)), D(str(face_val))
    e, m = D(str(entry_price)), D(str(mmr))
    return (c * fv * (D("1") + m)) / (b + (c * fv / e))


class TestInverseLiqFormula(unittest.TestCase):
    r"""入场价是最重要的参数,强平价必须对它敏感。"""

    B, C, FV, MMR = 10000, 5, 1, 0.01

    def test_L1_liq_price_must_respond_to_entry_price(self):
        """入场价放大 20 倍,强平价必须显著变化。当前实现变化 0.000% → 红。"""
        low = lib_p_liq(self.B, self.C, self.FV, 25000, self.MMR)
        high = lib_p_liq(self.B, self.C, self.FV, 500000, self.MMR)
        rel = abs(float(high / low) - 1.0)
        self.assertGreater(
            rel, 0.10,
            f"入场价从 25000 放大到 500000(20 倍),强平价相对变化仅 {rel*100:.3f}% —— "
            f"low={low} high={high}。入场价是强平价最重要的参数,任何业务定义下"
            f"都不可能对它无响应。margin.py 第 63 行把 entry_price 只放进分母的一个"
            f"可忽略小项里,公式实质上忽略了入场价。")

    def test_L1b_assertion_accepts_the_wrong_answer(self):
        """配套证据:断言会对一个**明显不合理**的强平价点头。

        入场价 50000 时,`expected_liq=0.0005` 会让断言通过 ——
        即「几乎立刻强平」这个结论被当成正确结果接受。
        本项当前为绿,用于说明 L1 不是测试自己出错。
        """
        self.assertTrue(assert_inverse_liq_price(self.B, self.C, self.FV, 50000,
                                                 self.MMR, 0.000505),
                        "断言对 0.000505 应当通过(它就是这么算的)")

    def test_L1c_sanity_check_the_harness_is_not_broken(self):
        """防「测试自己坏了」:断言对**明显错误**的强平价必须拒绝。"""
        with self.assertRaises(AssertionError):
            assert_inverse_liq_price(self.B, self.C, self.FV, 50000, self.MMR,
                                     1.0e9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
