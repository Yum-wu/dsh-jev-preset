# -*- coding: utf-8 -*-
"""
A2:断言 CLI 的退出码契约 —— 退出码必须能区分「答案错」与「调用错」。

缺陷原状(2026-10-01 实测,见 docs/baseline-2026-10-01.md):
  status:"error" 却 exit 1,与 status:"fail" 同码。
  调用方(agent / 脚本)拿到 exit 1 无法区分:
    - 「断言跑了,答案错的」  → 该重算 / 改结论
    - 「根本没跑起来,调用错的」→ 该修命令,重算没有意义
  这是典型的验证剧场入口:退出码说「没过」,实际根本没执行。

预注册判据(R9,先写死再看数据):
  T1 退出码矩阵(唯一真相,全表断言,不允许只测其中几格):
       pass                    → 0
       fail(AssertionError)   → 1
       缺 --func               → 2
       坏 JSON                 → 2
       参数不匹配(TypeError)   → 2
       未知断言名              → 2   ← 修复前是 1,本轮改
  T2 **不变式**:`status == "error"` ⟺ `exit == 2`,且 `status != "error"` ⟹ `exit != 2`。
     这条比逐格枚举更强:任何新增/遗漏的 error 分支都会被它抓住。
  T3 判别力:存在一对 (调用, 退出码) 使「只按退出码判 fail」与
     「只按 status 判 fail」的结论**不同** —— 证明退出码确有信息量,
     而不是恒等于某个常量。
  T4 persona 与 README 都必须写明 exit 2 的存在与处置(契约要落在文档上,不只是代码)。
"""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(os.path.dirname(PLUGIN_ROOT))
CLI = os.path.join(PLUGIN_ROOT, "packages", "assertions", "python", "jev_assertions", "cli.py")

PASS_ARGS = json.dumps({"raw_price": 100.12, "tick_size": 0.01, "expected": 100.12})
FAIL_ARGS = json.dumps({"raw_price": 100.12, "tick_size": 0.01, "expected": 100.13})
MISMATCH_ARGS = json.dumps({"raw_price": 1})


def run(*cli_args):
    """跑一次 CLI,返回 (exit_code, 解析后的 stdout dict)。"""
    res = subprocess.run([sys.executable, CLI, *cli_args], capture_output=True, text=True)
    try:
        payload = json.loads(res.stdout)
    except json.JSONDecodeError:
        payload = {"status": "<unparsable>", "_raw": res.stdout, "_err": res.stderr}
    return res.returncode, payload


class TestCliExitCodeContract(unittest.TestCase):

    @staticmethod
    def _doc_targets():
        return [
            os.path.join(PLUGIN_ROOT, "cordis.patch.yml"),
            os.path.join(PLUGIN_ROOT, "README.md"),
            os.path.join(PLUGIN_ROOT, "README_EN.md"),
        ]

    def test_T1_exit_code_matrix(self):
        # argv 必须逐元素给,不能对整串 split —— JSON 里有空格,拆了就变成 argparse 报错,
        # 测的就不是产品行为而是测试自己(第一版就踩了这个坑,报出 9 个假红)。
        matrix = [
            (("--func", "tick_floor", "--args", PASS_ARGS), 0, "pass", "正常通过"),
            (("--func", "tick_floor", "--args", FAIL_ARGS), 1, "fail", "断言不通过"),
            ((), 2, "error", "缺 --func"),
            (("--func", "tick_floor", "--args", "not-json"), 2, "error", "坏 JSON"),
            (("--func", "tick_floor", "--args", MISMATCH_ARGS), 2, "error", "参数不匹配(缺参)"),
            (("--func", "tick_floor", "--args",
              '{"raw_price":100.12,"tick_size":0.01,"expected":100.12,"bogus":1}'),
             2, "error", "参数不匹配(多参)"),
            (("--func", "no_such_assertion", "--args", "{}"), 2, "error", "未知断言名"),
        ]
        for argv, want_code, want_status, label in matrix:
            with self.subTest(场景=label):
                code, out = run(*argv)
                self.assertEqual(out.get("status"), want_status, f"{label}: status 错, got {out}")
                self.assertEqual(code, want_code, f"{label}: 退出码应为 {want_code}, got {code}")

    def test_T2_error_iff_exit2(self):
        """不变式:退出码与 status 字段必须完全互推,不留「同码不同义」的缝。"""
        cases = [
            (("--func", "tick_floor", "--args", PASS_ARGS), "pass"),
            (("--func", "tick_floor", "--args", FAIL_ARGS), "fail"),
            (("--func", "no_such_assertion", "--args", "{}"), "未知断言名"),
            (("--func", "tick_floor", "--args", "not-json"), "坏 JSON"),
            (("--func", "tick_floor", "--args", MISMATCH_ARGS), "参数不匹配"),
            ((), "缺 --func"),
        ]
        for argv, label in cases:
            with self.subTest(场景=label):
                code, out = run(*argv)
                is_error = out.get("status") == "error"
                self.assertEqual(
                    is_error, code == 2,
                    f"status=error({is_error}) 与 exit=2({code == 2}) 不一致: {out}")

    def test_T3_exit_code_carries_information(self):
        """判别力:退出码必须能把「答案错」和「调用错」分开,否则契约等于没定义。"""
        fail_code, fail_out = run("--func", "tick_floor", "--args", FAIL_ARGS)
        unknown_code, unknown_out = run("--func", "no_such_assertion", "--args", "{}")
        # 两者 status 都是「没过」这一侧,但退出码必须不同,
        # 否则调用方无法决定「该重算」还是「该修命令」。
        self.assertEqual(fail_out.get("status"), "fail")
        self.assertEqual(unknown_out.get("status"), "error")
        self.assertNotEqual(
            fail_code, unknown_code,
            "「答案错」与「调用错」共用退出码,调用方无法区分 —— 正是 A2 缺陷本身")

    def test_T4_docs_declare_exit2(self):
        """契约必须落在 persona 与两份 README,且必须**语义正确**。

        判据修正(红队 46cdb73f 变异 M4/M4b 实证):初版只做 `assertIn("exit 2", text)`,
        删掉整张退出码表、甚至把 1↔2 语义**写反**都仍然全绿 —— 关键词存在性
        检测不了「写错/写反」。现改为逐条核对三值映射的方向。
        """
        # 每份文档都必须原样包含这三行(方向不可颠倒)。
        required = [
            ("`0`", "pass"),
            ("`1`", "fail"),
            ("`2`", "error"),
        ]
        for path in self._doc_targets():
            name = os.path.basename(path)
            with self.subTest(文件=name):
                self.assertTrue(os.path.exists(path), f"{path} 不存在")
                text = open(path, encoding="utf-8").read()
                for code_cell, status in required:
                    # 找形如 | `0` | pass | ... 或 exit 0 ... pass 的行
                    hit = any(
                        (line.count("|") >= 3 and code_cell in line and status in line)
                        or (f"exit {code_cell.strip('`')}" in line and status in line)
                        for line in text.splitlines()
                    )
                    self.assertTrue(
                        hit,
                        f"{name}: 找不到 `exit {code_cell.strip('`')}` 对应 status={status} 的行 —— "
                        f"退出码表可能被删除、写错或写反")

    def test_T5_internal_exception_is_exit2(self):
        """红队 46cdb73f 变异 M5 实证:通用 Exception 分支退回 exit 1 时,初版测试**全绿**。
        原因:T1/T2 的用例列表没有触发「断言函数内部抛普通异常」的场景。

        ⚠ 触发输入在 Round 22 换过一次(2026-10-01 D3):初版用「除零」触发
        (`slippage_impact` adv=0),但除零现在有了**专属**分支
        (`ArithmeticInputError` → status=fail / exit 1),不再落到通用分支。
        换输入不改目标 —— 本用例要守的仍是「**非算术类**内部异常必须 exit 2」。
        现用 KeyError:orderbook_vwap 的 depth_asks 元素缺 `price` 键。
        (除零那条路径由 tests/test_arithmetic_input_domain.py 专门覆盖。)
        """
        code, out = run("--func", "orderbook_vwap", "--args",
                        '{"order_size":1,"depth_asks":[{"px":60000,"size":2}],'
                        '"expected_vwap":60000,"expected_cost":60000}')
        self.assertEqual(out.get("status"), "error",
                         f"非算术类内部异常应落到通用 Exception 分支, got {out}")
        self.assertEqual(code, 2,
            "断言函数内部异常必须 exit 2(调用/环境错);退成 1 会与「答案错」同码")

    def test_T6_insufficient_data_is_not_answer_wrong(self):
        """红队 46cdb73f 发现 6d:「深度不足」被归为 fail/exit 1,处方是「重算」——
        但重算对数据不足毫无意义。R5 铁律:「无答案」与「答错」必须分开统计。"""
        code, out = run("--func", "orderbook_vwap", "--args",
                        '{"order_size":10,"depth_asks":[{"price":60000,"size":2}],'
                        '"expected_vwap":60000,"expected_cost":600000}')
        self.assertEqual(out.get("status"), "insufficient_data",
            f"深度不足属「输入不足以判定」,不该与「算错了」同列, got {out}")
        self.assertEqual(code, 3, "数据不足应走独立退出码 3,与 exit 1(算错了)分开")
        # 反向:真正的算错仍须留在 exit 1
        fcode, fout = run("--func", "tick_floor", "--args", FAIL_ARGS)
        self.assertEqual(fout.get("status"), "fail")
        self.assertEqual(fcode, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
