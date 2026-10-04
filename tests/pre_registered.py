# -*- coding: utf-8 -*-
r"""★★★ Round 82:**预注册常量搬出被测主体**(红队 R80 §⑯ / R81 P2-R81-B)。

## 为什么必须分文件
R80 我把 `EXPECT_TESTS` 放在 `tools/mutation_harness.py` 里,与它守的逻辑**同文件**;
R81 又把 `PRE_REGISTERED` 放在 `tests/test_mutation_harness.py` 里,与它守的棘轮**同文件**。
红队两轮各打穿一次:
* R80 P2-R80-3:三处**自洽下调**(删用例 + 改 `EXPECTED_TESTS` + 改 `EXPECT_TESTS`)⇒ 五个守卫全绿。
* R81 C2:再**把 `PRE_REGISTERED` 一起调低** ⇒ `rc=0 Ran 7 tests OK`,套件已静默少 2 个用例。

**根因是同一个**:判据的**期望值**与被判据的**对象**住在同一个可写文件里 ——
**同源共变异**直接骗过。这与 C23 的 F-4(生产与 helper 规则同源)是**同一族**,
只是上移了一层:**棘轮与它守的常量同源**。

## 本文件是「不同主体」
它**不含任何被测逻辑**,只放**只增不减**的数。修改它会被:
1. `tests/test_mutation_harness.py::test_H5` 的棘轮读。
⚠ **R82 这里曾声称还有第二个守卫 `tests/test_pre_registered_is_append_only.py`(「只增」判据)。红队 R82 P2-R82-D【中】实测该文件不存在**(`Test-Path` False;全仓 grep 只命中本 docstring 与 `test_mutation_harness.py` 的一处注释)—— **文档 ≠ 实现**,假声称已删。
⚠ 故本文件**只有 `test_H5` 一条棘轮**;**`test_H6` 也消费 `PR.HARNESS_TESTS`(作下界,L152)** —— 下调它同样削弱 H6(红队 R82 P3-R82-C 指出,本行已改口)。而 H5 本身可被**掏空**(红队 R82 M8:体首插 `return` + 保留 skip 通道 ⇒ 七条棘轮静默失效而两套件全绿)或被**跨 3 文件共变异**(M5)。**登记 R83 补真守卫。**
⚠ 这**不是**外部锚 —— 它仍在同一个仓、同一个作者手里。
   真正的「外部锚」需要仓外存证(CI / 第三方签名),**登记未修**。
   但把期望值从**被测文件**里搬出来,至少让「**顺手改一处**」不再同时改到判据和常量。
"""

#: 被测套件 `tests/test_evasion_audit.py` 的用例数下界
SUITE_TESTS = 25
#: 框架测试 `tests/test_mutation_harness.py` 的用例数下界
#: 参与自守链的**具名文件清单**。
#:
#: ★★★ Round 87 第 2 轮(红队 P8-R87-A/B【高】):
#: 第 1 轮我在 `tools/mutation_harness.py` 里加 `repo_digest_files()` 作为「单一来源」,
#: 但它的实现就是 `return PARTICIPATING_FILES` —— H9 的 ① 比较它与 `PARTICIPATING_FILES`,
#: **是同义反复,鉴别力为 0**(红队 C3:`repo_digest` 改回硬编码 8 项字面量 ⇒ H9 `rc=0`)。
#: 而 ① 里的 `len(...) >= 8` 是**数量判据不是身份判据** —— 红队 C4b:
#: 去掉 `tools/g_check.py` 换入 `package.json`(**仍 8 项**)⇒ H9 `rc=0`,
#: 随后**污染 `tools/g_check.py` 零告警** —— **R82 修 R81③ 的那个洞被一条编辑重新打开**。
#: ⇒ 清单搬到**另一个文件**(预注册),按**名字**逐项对拍。本仓 C16/C17 的正解:
#: **覆盖不能靠数字余量,只能靠身份。**
PARTICIPATING_FILES = (
    "tools/evasion_audit.py",
    "tests/test_evasion_audit.py",
    "docs/evasion-ledger.md",
    "tools/mutation_harness.py",
    "tests/test_mutation_harness.py",
    "tests/test_no_silent_skips.py",
    "tools/g_check.py",
    "tests/pre_registered.py",
)

HARNESS_TESTS = 10
#: `package.json` 的 `scripts.test` 里声明的 python 套件数下界
SUITE_FILES = 35
#: 被测套件断言总数下界。⚠ **这个「总数」本身不可复算、且单位失真**(红队 R82 P2-R82-F):
#:   R81 记 **406**、R82 用文件自带的 `_COUNTER` 连跑两次逐用例计数 **IDENTICAL** 得 **407** ——
#:   两数对不上;更要紧的是**单位**:1 条 `assertEqual('abc','abc')` 被记 **4** 次
#:   (`assertEqual`→`assertMultiLineEqual`→2×`assertIsInstance` 全被打桩)
#:   ⇒ `MIN_TOTAL_ASSERTIONS` 守的是**被调度放大的调用数**,不是断言条数。**登记 R83。**
TOTAL_ASSERTIONS_FLOOR = 400
#: `_selftest()` 必须真跑到的判据条数(红队 R81 P2-R81-A:删掉 5 条无人看见)
SELFTEST_CHECKS = 14
