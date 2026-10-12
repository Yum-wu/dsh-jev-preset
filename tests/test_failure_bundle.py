# -*- coding: utf-8 -*-
r"""failure bundle 机制 —— 规范见 docs/failure-bundle-spec.md。

## 为什么单列一条

退出码契约(`0`/`1`/`2`/`3`)回答「**该做什么动作**」,失败包回答「**到底发生了什么**」。
A2 那轮修的是前者(见 `tests/test_cli_exit_codes.py`);后者此前不存在 ——
调用方拿到 `exit 1` 之后,除了 stdout 一行 JSON 之外无迹可查:`args` 只活在
调用方的命令行里,重跑通过后也无法证明「修的是同一个失败」。

## 判据取向:三条行为不变式,不是「字段齐不齐」

* **B1 opt-in** —— 不传 `--bundle-dir` 时行为与加本机制之前**完全一致**:
  不落盘,且 stdout 不多任何键。字段表填得再满,只要默认落盘,就是给
  不关心证据链的调用方制造垃圾文件。
* **B2 证据不篡改结论** —— 写包失败、`--resolves` 指向不存在的 id、
  目录不可写,退出码一律不变。**证据机制坏掉不该掩盖结论。**
* **B3 复现闭环** —— `repro_cmd` 必须**真的能跑**,且跑出与首次相同的 status。
  否则它只是装饰:一条从没被执行过的复现命令,和没有复现命令没有区别。

B3 是核心判据。前两条只守「不添乱」,B3 才把「可复现」从文档承诺变成可执行事实。

## 与 test_cli_exit_codes.py 的分工

那边守「退出码与 status 互推」;这边守「证据载体的行为边界」。
两边**不得互相依赖** —— 本条全程用 `--bundle-dir` 的调用,
那边全程不用,任一侧的改动不会静默削弱另一侧。
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
CLI = os.path.join(PLUGIN_ROOT, "packages", "assertions", "python", "jev_assertions", "cli.py")

PASS_ARGS = json.dumps({"raw_price": 100.12, "tick_size": 0.01, "expected": 100.12})
FAIL_ARGS = json.dumps({"raw_price": 100.12, "tick_size": 0.01, "expected": 100.13})
INSUFFICIENT_ARGS = json.dumps({
    "order_size": 10,
    "depth_asks": [{"price": 60000, "size": 2}],
    "expected_vwap": 60000,
    "expected_cost": 600000,
})
# 算术类输入错:adv(日均成交量)置 0 ⇒ float 除零 ⇒ 走 ArithmeticInputError 分支
# (status=fail / exit 1 / 带 hint)。参数取自 tests/test_arithmetic_input_domain.py
# 的既有探针,不另造一套 —— 同一触发点两处写法不一致时,先红的那处会误导人。
ARITH_ARGS = json.dumps({
    "order_val": 100000.0,
    "adv": 0.0,
    "daily_vol": 0.02,
    "budget_bps": 50.0,
    "expect_penetrated": False,
})


def run(*cli_args):
    """跑一次 CLI,返回 (exit_code, 解析后的 stdout dict)。"""
    res = subprocess.run([sys.executable, CLI, *cli_args], capture_output=True, text=True)
    try:
        payload = json.loads(res.stdout)
    except json.JSONDecodeError:
        payload = {"status": "<unparsable>", "_raw": res.stdout, "_err": res.stderr}
    return res.returncode, payload


class FailureBundleTestBase(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="_tmp_jev_bundle_")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def bundles(self):
        return sorted(f for f in os.listdir(self.dir) if f != "latest.json")

    def latest(self):
        with open(os.path.join(self.dir, "latest.json"), encoding="utf-8") as fh:
            return json.load(fh)


class TestOptIn(FailureBundleTestBase):

    def test_B1_no_bundle_dir_writes_nothing(self):
        """B1:不传 --bundle-dir 时,目录必须保持为空。"""
        code, _ = run("--func", "tick_floor", "--args", FAIL_ARGS)
        self.assertEqual(code, 1)
        self.assertEqual(os.listdir(self.dir), [],
                         "不传 --bundle-dir 却落了盘 —— opt-in 被破坏")

    def test_B1_pass_stdout_has_no_extra_keys(self):
        """B1:不传参时 pass 的 stdout 键集合必须与加本机制之前一致。

        这是「不传参 = 逐字节一致」的可执行版本。多一个恒为 null 的键
        同样是契约变更 —— 调用方可能按 keys 集合做严格校验。
        """
        code, out = run("--func", "tick_floor", "--args", PASS_ARGS)
        self.assertEqual(code, 0)
        self.assertEqual(sorted(out.keys()), ["assertion", "result", "status"],
                         f"pass 的 stdout 多了键: {sorted(out.keys())}")

    def test_B1_fail_stdout_has_no_extra_keys(self):
        code, out = run("--func", "tick_floor", "--args", FAIL_ARGS)
        self.assertEqual(code, 1)
        self.assertEqual(sorted(out.keys()), ["assertion", "error", "status"],
                         f"fail 的 stdout 多了键: {sorted(out.keys())}")


class TestBundleContent(FailureBundleTestBase):

    def test_T1_fail_bundle_fields(self):
        code, _ = run("--func", "tick_floor", "--args", FAIL_ARGS, "--bundle-dir", self.dir)
        self.assertEqual(code, 1)
        self.assertEqual(len(self.bundles()), 1, f"应恰好 1 个包, got {self.bundles()}")
        b = self.latest()
        self.assertEqual(b["schema_version"], "jev.failure/1")
        self.assertEqual(b["assertion"], "tick_floor")
        self.assertEqual(b["status"], "fail")
        self.assertEqual(b["exit_code"], 1)
        self.assertIsNone(b["resolved_by"])
        self.assertIsNone(b["hint"], "非算术类失败不该有 hint")
        # args 必须回显且与输入等价 —— 这是「可复现」的前提
        self.assertEqual(b["args"], json.loads(FAIL_ARGS))
        # 文件名必须等于 bundle_id,且 latest.json 是同一个包的副本
        self.assertIn(b["bundle_id"] + ".json", os.listdir(self.dir))
        with open(os.path.join(self.dir, b["bundle_id"] + ".json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), b, "latest.json 与具名包不是同一个包")

    def test_T2_insufficient_data_bundle(self):
        """exit 3 也要留证据 —— 「数据不足」是独立语义,不是没有结论。"""
        code, out = run("--func", "orderbook_vwap", "--args", INSUFFICIENT_ARGS,
                        "--bundle-dir", self.dir)
        self.assertEqual(code, 3)
        self.assertEqual(out["status"], "insufficient_data")
        b = self.latest()
        self.assertEqual(b["status"], "insufficient_data")
        self.assertEqual(b["exit_code"], 3, "包里的 exit_code 必须与真实退出码一致")

    def test_T3_arithmetic_input_error_carries_hint(self):
        """算术类输入错:status=fail / exit 1 / 带 hint,三者必须一起进包。

        hint 是「换数据」与「改命令」的分岔依据 —— 丢了它,消费方会按
        exit 1 去重算,而正确的动作是先换数据。
        """
        code, out = run("--func", "slippage_impact", "--args", ARITH_ARGS,
                        "--bundle-dir", self.dir)
        self.assertEqual(code, 1, f"算术类输入错应 exit 1, got {code}: {out}")
        self.assertEqual(out["status"], "fail")
        b = self.latest()
        self.assertIsNotNone(b["hint"], "算术类输入错的包必须带 hint")
        self.assertEqual(b["exit_code"], 1)

    def test_T4_frontend_error_writes_no_bundle(self):
        """前置校验失败(未知断言名)不写包 —— 断言名不可靠时包没有复现价值。"""
        before = self.bundles()
        code, out = run("--func", "no_such_assertion", "--args", "{}", "--bundle-dir", self.dir)
        self.assertEqual(code, 2)
        self.assertEqual(out["status"], "error")
        self.assertEqual(self.bundles(), before, "前置错误不该产生失败包")

    def test_T5_bundle_ids_are_not_silently_deduped(self):
        """同一断言同一输入失败两次 ⇒ 两个包。

        规范承诺「不被静默去重」,而 bundle_id 由 ts 参与哈希 ——
        若 ts 退回秒级精度,同一秒内连跑两次会撞成同一个文件名、后一次
        覆盖前一次,「同一失败复发了几次」这条信息就丢了。
        """
        run("--func", "tick_floor", "--args", FAIL_ARGS, "--bundle-dir", self.dir)
        run("--func", "tick_floor", "--args", FAIL_ARGS, "--bundle-dir", self.dir)
        self.assertEqual(len(self.bundles()), 2,
                         f"同输入两次失败被静默去重: {self.bundles()}")


class TestResolve(FailureBundleTestBase):

    def _make_fail(self):
        run("--func", "tick_floor", "--args", FAIL_ARGS, "--bundle-dir", self.dir)
        return self.latest()["bundle_id"]

    def test_T6_resolve_backfills(self):
        bid = self._make_fail()
        code, out = run("--func", "tick_floor", "--args", PASS_ARGS,
                        "--bundle-dir", self.dir, "--resolves", bid)
        self.assertEqual(code, 0)
        self.assertNotIn("resolve_warning", out, f"有效解析不该有告警: {out}")
        with open(os.path.join(self.dir, bid + ".json"), encoding="utf-8") as fh:
            b = json.load(fh)
        self.assertIsNotNone(b["resolved_by"], "resolved_by 未回填")
        self.assertEqual(b["resolved_by"]["assertion"], "tick_floor")
        self.assertTrue(b["resolved_by"]["bundle_id"], "解析记录缺 id")
        # 包本身必须还是原来那个失败包 —— 回填不许把证据改成成功
        self.assertEqual(b["status"], "fail")
        self.assertEqual(b["exit_code"], 1)

    def test_T7_resolve_missing_id_warns_without_changing_exit(self):
        code, out = run("--func", "tick_floor", "--args", PASS_ARGS,
                        "--bundle-dir", self.dir, "--resolves", "deadbeef0000")
        self.assertEqual(code, 0, "解析失败不得改变退出码")
        self.assertEqual(out["status"], "pass")
        self.assertIn("resolve_warning", out, f"缺 id 应告警: {out}")
        self.assertEqual(self.bundles(), [], "解析失败不该凭空造包")

    def test_T8_failed_call_ignores_resolves(self):
        """失败侧传 --resolves 一律忽略。

        否则「红包解析红包」会让 resolved_by 变成一句无意义的自指,
        把「这次绿修了那次红」的语义污染掉。
        """
        bid = self._make_fail()
        code, _ = run("--func", "tick_floor", "--args", FAIL_ARGS,
                      "--bundle-dir", self.dir, "--resolves", bid)
        self.assertEqual(code, 1)
        with open(os.path.join(self.dir, bid + ".json"), encoding="utf-8") as fh:
            b = json.load(fh)
        self.assertIsNone(b["resolved_by"], "失败调用不该回填 resolved_by")


class TestInvariants(FailureBundleTestBase):

    def test_B2_unwritable_dir_does_not_change_exit_code(self):
        """B2:目录不可写时,证据写不出来,结论必须照旧。

        bundle_dir 指向一个**已存在的普通文件** ⇒ makedirs 必失败。
        这是「证据机制坏掉不该掩盖结论」的可执行版本。
        """
        blocker = os.path.join(self.dir, "blocker")
        with open(blocker, "w", encoding="utf-8") as fh:
            fh.write("x")
        code, out = run("--func", "tick_floor", "--args", FAIL_ARGS, "--bundle-dir", blocker)
        self.assertEqual(code, 1, "写包失败改变了退出码")
        self.assertEqual(out["status"], "fail")

    def test_B2_exit_code_matrix_unchanged_by_bundle_dir(self):
        """B2:同一调用加不加 --bundle-dir,退出码与 status 必须逐格相同。"""
        cases = [
            (("--func", "tick_floor", "--args", PASS_ARGS), 0, "pass"),
            (("--func", "tick_floor", "--args", FAIL_ARGS), 1, "fail"),
            (("--func", "orderbook_vwap", "--args", INSUFFICIENT_ARGS), 3, "insufficient_data"),
            (("--func", "no_such_assertion", "--args", "{}"), 2, "error"),
            ((), 2, "error"),
        ]
        for argv, want_code, want_status in cases:
            with self.subTest(argv=argv[:3]):
                plain_code, plain_out = run(*argv)
                with_code, with_out = run(*argv, "--bundle-dir", self.dir)
                self.assertEqual(plain_code, want_code, f"基线退出码变了: {plain_out}")
                self.assertEqual(with_code, want_code,
                                 "--bundle-dir 改变了退出码")
                self.assertEqual(plain_out["status"], want_status)
                self.assertEqual(with_out["status"], want_status,
                                 "--bundle-dir 改变了 status")

    def test_B3_repro_cmd_is_actually_runnable(self):
        """B3(核心):把 repro_cmd 原样抄出来跑,必须复现同一个 status。

        这条是「可复现」的唯一客观判据。只断言 repro_cmd 非空、
        或只检查它包含某些子串,都测不出「命令其实跑不起来」——
        本仓记过的形态:判据检测**关键词存在性**,而缺陷恰恰是**写错**。
        """
        run("--func", "tick_floor", "--args", FAIL_ARGS, "--bundle-dir", self.dir)
        repro = self.latest()["repro_cmd"]
        argv = shlex.split(repro, posix=True)
        self.assertTrue(argv, f"repro_cmd 解析为空: {repro!r}")
        argv[0] = sys.executable          # 用当前解释器,避免 PATH 差异
        res = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(res.returncode, 1,
                         f"repro_cmd 跑出来的退出码不是 1: {repro!r}\n{res.stderr[:400]}")
        replay = json.loads(res.stdout)
        self.assertEqual(replay["status"], "fail",
                         f"repro_cmd 没能复现同一个 status: {replay}")
        self.assertEqual(replay["assertion"], "tick_floor")

    def test_B3_repro_cmd_round_trips_exotic_args(self):
        """B3 边界:args 含空格/引号/中文/Unicode 时,repro_cmd 仍须原样复现。

        规范化 JSON 用 `separators=(",", ":")` 且 `ensure_ascii=False` ——
        后者让中文原样落进命令行,前者去掉空格减少引号风险。
        这条测的正是「去掉空格」这个决定是否真的够。
        """
        tricky = {"order_size": 3, "depth_asks": [{"price": 60000, "size": 1}],
                  "expected_vwap": 60000, "expected_cost": 1}
        args_json = json.dumps(tricky, ensure_ascii=False)
        code, _ = run("--func", "orderbook_vwap", "--args", args_json,
                      "--bundle-dir", self.dir)
        b = self.latest()
        self.assertEqual(b["exit_code"], code, "包里的 exit_code 与真实退出码不一致")
        argv = shlex.split(b["repro_cmd"], posix=True)
        argv[0] = sys.executable
        res = subprocess.run(argv, capture_output=True, text=True)
        replay = json.loads(res.stdout)
        self.assertEqual(res.returncode, code,
                         f"含复杂 args 的 repro_cmd 复现失败: {b['repro_cmd']!r}")
        self.assertEqual(replay["status"], b["status"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
