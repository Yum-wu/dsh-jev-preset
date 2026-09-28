# -*- coding: utf-8 -*-
"""准确率基准自身的守护测试:参考解正确 → 判分器正确 → 统计正确。

参考解用三类**独立于 solve.py 的证据**交叉验证:
1. 手算值(注释里写了算式)
2. 性质/暴力检验(约束满足 + 最优性)
3. 独立实现:标准库 zoneinfo、仓内 jev_assertions 断言库
"""
import json
import os
import random
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D, ROUND_HALF_UP

# Windows 控制台/CI 默认 stdout 为 cp1252,本文件与 jevbench 都会 print 中文,
# 不重配会在 print 处抛 UnicodeEncodeError(实测)。
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    _TZ_PROBE = "America/New_York"
    try:
        ZoneInfo(_TZ_PROBE)
        _HAS_TZ = True
        _TZ_WHY = ""
    except Exception as _e:                      # 缺 IANA 库(Windows 需 tzdata 包)
        _HAS_TZ = False
        _TZ_WHY = f"{type(_e).__name__}: {_e}"
except ImportError as _e:                       # Python < 3.9
    _HAS_TZ = False
    _TZ_WHY = f"zoneinfo 不可用: {_e}"

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "../benchmarks/accuracy")))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "../packages/assertions/python")))

from jevbench import solve  # noqa: E402
from jevbench.__main__ import cmd_selftest, main as cli_main  # noqa: E402
from jevbench.cases import DEFAULT_COUNTS, build_suite  # noqa: E402
from jevbench.extract import extract_answer, extract_route, is_three_path  # noqa: E402
from jevbench.grading import compare, difficulty_filter, grade_case, grade_runs, summarize  # noqa: E402
from jevbench.stats import mcnemar_exact, wilson  # noqa: E402
from jev_assertions import assert_ex_right_price, assert_orderbook_vwap, assert_tick_floor  # noqa: E402


class TestSolveHandComputed(unittest.TestCase):
    def test_tick(self):
        self.assertEqual(solve.tick_round("67432.178", "0.01", "BUY"), "67432.17")
        self.assertEqual(solve.tick_round("0.000034", "0.0001", "SELL"), "0.0001")   # 防零报价
        self.assertEqual(solve.tick_round("100.6", "0.25", "BUY"), "100.50")
        self.assertEqual(solve.tick_round("100.6", "0.25", "SELL"), "100.75")
        self.assertEqual(solve.tick_round("100.50", "0.25", "SELL"), "100.50")      # 已对齐不动

    def test_lot(self):
        # 1000/(100*1.001)=9.99000999 → 步长 0.01 向下 → 9.99;9.99*100.1=999.999 ≤ 1000
        self.assertEqual(solve.lot_budget("1000", "100", "0.01", "0.001", "10"), "9.99")
        # 8/(100.1)=0.0799 → 0.07,名义 7 < 10 → 0
        self.assertEqual(solve.lot_budget("8", "100", "0.01", "0.001", "10"), "0")

    def test_vwap(self):
        # 1×100 + 0.5×101 = 150.5;150.5/1.5 = 100.3333
        self.assertEqual(solve.orderbook_vwap("1.5", [["100", "1"], ["101", "1"]]),
                         {"total_cost": "150.50", "vwap": "100.3333"})
        self.assertEqual(solve.orderbook_vwap("3", [["100", "1"], ["101", "1"]]),
                         {"status": "insufficient_depth"})

    def test_tiered_mm(self):
        tiers = [[50000, "0.004"], [250000, "0.005"], [None, "0.01"]]
        # 50000*0.004 + 50000*0.005 = 450;D = 100000*0.005 - 450 = 50
        self.assertEqual(solve.tiered_mm("100000", tiers), {"mm": "450.00", "deduction": "50.00"})
        self.assertEqual(solve.tiered_mm("50000", tiers), {"mm": "200.00", "deduction": "0.00"})
        # 200 + 1000 + 50000*0.01 = 1700;D = 300000*0.01 - 1700 = 1300
        self.assertEqual(solve.tiered_mm("300000", tiers), {"mm": "1700.00", "deduction": "1300.00"})

    def test_ny_open(self):
        # 2026-03-08 为 3 月第 2 个周日(3/1 是周日)
        self.assertEqual(solve.ny_open("2026-03-06", "09:30"), {"utc": "2026-03-06 14:30", "beijing": "2026-03-06 22:30"})
        self.assertEqual(solve.ny_open("2026-03-09", "09:30"), {"utc": "2026-03-09 13:30", "beijing": "2026-03-09 21:30"})
        self.assertEqual(solve.ny_open("2026-03-09", "20:00"), {"utc": "2026-03-10 00:00", "beijing": "2026-03-10 08:00"})

    def test_ex_rights(self):
        self.assertEqual(solve.ex_rights("10", "1", "5", "0", "0"), "6.60")      # (10-0.1)/1.5
        self.assertEqual(solve.ex_rights("20", "0", "0", "3", "10"), "17.69")    # (20+3)/1.3

    def test_cagr(self):
        # 2021-01-01→2023-01-01 = 730 天;1.21^(1/2) = 1.1
        self.assertEqual(solve.cagr("100", "121", "2021-01-01", "2023-01-01"), "10.00")
        self.assertEqual(solve.cagr("100", "81", "2021-01-01", "2023-01-01"), "-10.00")

    def test_mdd(self):
        self.assertEqual(solve.max_drawdown(["100", "120", "90", "130", "65"]),
                         {"mdd_pct": "50.00", "peak_index": 3, "trough_index": 4})
        self.assertEqual(solve.max_drawdown(["100", "50", "100", "50"]),   # 并列取最早
                         {"mdd_pct": "50.00", "peak_index": 0, "trough_index": 1})
        self.assertEqual(solve.max_drawdown(["1", "2", "3"])["mdd_pct"], "0.00")


class TestSolveIndependentCrossCheck(unittest.TestCase):
    """用生成器同分布的随机参数,与独立实现/性质逐一比对。"""

    def setUp(self):
        self.rng = random.Random(20260928)

    def test_tick_properties(self):
        for _ in range(500):
            t = D(self.rng.choice(["0.05", "0.25", "0.5", "0.01", "0.001"]))
            p = D(f"{self.rng.uniform(50, 90000):.4f}")
            buy, sell = D(solve.tick_round(str(p), str(t), "BUY")), D(solve.tick_round(str(p), str(t), "SELL"))
            self.assertEqual(buy % t, 0); self.assertEqual(sell % t, 0)
            self.assertTrue(buy <= p < buy + t)
            self.assertTrue(sell - t < p <= sell)
        assert_tick_floor(67432.178, 0.01, solve.tick_round("67432.178", "0.01", "BUY"))

    def test_lot_optimality(self):
        for _ in range(500):
            s = D(self.rng.choice(["0.001", "0.01", "0.1", "1"]))
            f = D(self.rng.choice(["0.0005", "0.001", "0.002"]))
            p, b = D(f"{self.rng.uniform(5, 70000):.2f}"), D(f"{self.rng.uniform(50, 20000):.2f}")
            m = D(self.rng.choice(["5", "10", "100"]))
            q = D(solve.lot_budget(str(b), str(p), str(s), str(f), str(m)))
            if q == 0:
                n = (b / (p * (1 + f)) // s) * s          # 未过滤前的最大量
                self.assertTrue(n * p < m or n == 0)
                continue
            self.assertEqual(q % s, 0)
            self.assertLessEqual(q * p * (1 + f), b)      # 可行
            self.assertGreater((q + s) * p * (1 + f), b)  # 再加一步就超 → 最优
            self.assertGreaterEqual(q * p, m)

    def test_vwap_vs_assertion_lib(self):
        for _ in range(100):
            levels, px = [], self.rng.uniform(100, 60000)
            for _ in range(5):
                px *= 1 + self.rng.uniform(0.0002, 0.003)
                levels.append([f"{px:.2f}", f"{self.rng.uniform(0.1, 3):.3f}"])
            size = f"{sum(float(x) for _, x in levels) * 0.6:.3f}"
            r = solve.orderbook_vwap(size, levels)
            assert_orderbook_vwap(float(size), [{"price": float(a), "size": float(b)} for a, b in levels],
                                  float(r["vwap"]), float(r["total_cost"]))

    def test_tiered_identity_and_bruteforce(self):
        uppers = [50000, 250000, 1000000, 5000000, None]
        mmrs = ["0.004", "0.005", "0.01", "0.025", "0.05"]
        tiers = [[u, m] for u, m in zip(uppers, mmrs)]
        for _ in range(500):
            n = D(f"{self.rng.uniform(1, 8000000):.2f}")
            r = solve.tiered_mm(str(n), tiers)
            brute, lo = D(0), D(0)                          # 独立实现:逐段求和
            for u, m in tiers:
                hi = n if u is None else min(n, D(u))
                if hi > lo:
                    brute += (hi - lo) * D(m)
                if u is None or n <= D(u):
                    rate = D(m); break
                lo = D(u)
            self.assertEqual(D(r["mm"]), brute.quantize(D("0.01"), rounding=ROUND_HALF_UP))
            self.assertLessEqual(abs(n * rate - D(r["deduction"]) - brute), D("0.01"))  # MM = N×r − D

    @unittest.skipUnless(_HAS_TZ, f"缺 IANA 时区库(Windows 需 `pip install tzdata`): {_TZ_WHY}")
    def test_ny_open_vs_zoneinfo(self):
        """最强的一条独立证据:逐日扫 4 年,与标准库 zoneinfo 全量比对。

        ⚠️ Windows 的 Python 不自带 IANA 时区库,TZPATH 为空,必须装 `tzdata` 包
        (本机实测:无 tzdata 时抛 ZoneInfoNotFoundError)。CI 已显式安装该包,
        故此测试在 CI 中始终真实运行;本地缺失时跳过并在输出中告警,不静默通过。
        """
        tz = ZoneInfo("America/New_York")
        d0 = date(2025, 1, 1)
        for k in range(0, 365 * 4, 3):
            d = d0 + timedelta(days=k)
            for t in ("09:30", "16:00", "20:00"):
                h, m = map(int, t.split(":"))
                utc = datetime(d.year, d.month, d.day, h, m, tzinfo=tz).astimezone(timezone.utc)
                bj = utc + timedelta(hours=8)
                self.assertEqual(solve.ny_open(d.isoformat(), t),
                                 {"utc": utc.strftime("%Y-%m-%d %H:%M"), "beijing": bj.strftime("%Y-%m-%d %H:%M")},
                                 f"{d} {t}")

    def test_ex_rights_vs_assertion_lib(self):
        for _ in range(200):
            pre = f"{self.rng.uniform(5, 200):.2f}"
            cash, bonus = self.rng.choice(["0", "1.5", "3", "10"]), self.rng.choice(["0", "2", "5", "10"])
            got = solve.ex_rights(pre, cash, bonus, "0", "0")
            exact = (D(pre) - D(cash) / 10) / (1 + D(bonus) / 10)
            assert_ex_right_price(pre, bonus, 0, cash, exact)             # 断言库公式与本口径一致
            self.assertLessEqual(abs(D(got) - exact), D("0.005"))

    def test_cagr_vs_float(self):
        for _ in range(300):
            days = self.rng.randint(120, 1800)
            s = self.rng.uniform(10000, 1000000); e = s * self.rng.uniform(0.5, 3.5)
            s, e = f"{s:.2f}", f"{e:.2f}"
            f = ((float(e) / float(s)) ** (365 / days) - 1) * 100
            got = solve.cagr(s, e, "2020-01-01", (date(2020, 1, 1) + timedelta(days=days)).isoformat())
            self.assertLessEqual(abs(float(got) - f), 0.0051)

    def test_mdd_vs_bruteforce(self):
        for _ in range(300):
            seq = [f"{self.rng.uniform(500, 1500):.2f}" for _ in range(self.rng.randint(2, 16))]
            best = max((((D(seq[i]) - D(seq[j])) / D(seq[i]), i, j)
                        for i in range(len(seq)) for j in range(i, len(seq))), key=lambda x: x[0])
            r = solve.max_drawdown(seq)
            self.assertEqual(D(r["mdd_pct"]), (best[0] * 100).quantize(D("0.01"), rounding=ROUND_HALF_UP))
            if best[0] > 0:  # 回撤值必须与所报下标一致
                pk, tr = r["peak_index"], r["trough_index"]
                self.assertEqual((D(seq[pk]) - D(seq[tr])) / D(seq[pk]), best[0])


class TestSuite(unittest.TestCase):
    def test_deterministic_and_seed_sensitive(self):
        a, b, c = build_suite(1), build_suite(1), build_suite(2)
        self.assertEqual(json.dumps(a, ensure_ascii=False), json.dumps(b, ensure_ascii=False))
        self.assertNotEqual([x["question"] for x in a], [x["question"] for x in c])
        self.assertEqual(len(a), sum(DEFAULT_COUNTS.values()))
        self.assertEqual(len({x["id"] for x in a}), len(a))

    def test_category_isolation(self):
        """增减一个题型的数量,其他题型的题目不变。"""
        base = {x["id"]: x for x in build_suite(7)}
        more = {x["id"]: x for x in build_suite(7, {**DEFAULT_COUNTS, "tick": 9})}
        for cid, c in base.items():
            self.assertEqual(more[cid]["question"], c["question"])

    def test_every_expected_key_is_in_protocol(self):
        for c in build_suite(3):
            if c["kind"] == "gate":
                continue
            for k in c["expected"]:
                self.assertIn(f'"{k}"', c["question"], f"{c['id']} 题面未声明键 {k}")

    def test_adversarial_answers(self):
        for c in build_suite(5):
            if c["category"] == "adv_premise":
                self.assertIs(c["expected"]["premise_correct"], False)
            if c["category"] == "adv_depth":
                self.assertEqual(c["expected"], {"status": "insufficient_depth"})

    def test_selftest_passes_for_many_seeds(self):
        for seed in range(20):
            self.assertEqual(cmd_selftest(build_suite(seed)), 0)

    def test_gate_is_parameterized_across_seeds(self):
        """门控题必须随 seed 变化:若题面固定,多 seed 合并会反复出同一批题,
        既浪费 token 又无统计增益(历史实测 6 seed 合并出 72 条 gate 题但唯一题面仅 12 条)。"""
        a = [c["question"] for c in build_suite(1) if c["kind"] == "gate"]
        b = [c["question"] for c in build_suite(2) if c["kind"] == "gate"]
        self.assertEqual(len(a), len(b))
        overlap = set(a) & set(b)
        # 允许少量模板本身无参数的题(如 decimal 舍入模式),但不应全部相同
        self.assertLess(len(overlap), len(a), "门控题完全未参数化,多 seed 合并无意义")

    def test_gate_expected_split_is_balanced(self):
        """门控题必须两类都有,否则 gate_accuracy 无法反映误判方向。"""
        g = [c for c in build_suite(3) if c["kind"] == "gate"]
        three = sum(1 for c in g if c["expected"]["expect_three_path"])
        self.assertGreater(three, 0)
        self.assertGreater(len(g) - three, 0)

    def test_merge_multi_seed_unique_ids(self):
        """merge 子命令:多 seed 合并后 id 必须全局唯一,且总数 = seed 数 × 单套题数。"""
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "big.jsonl")
            self.assertEqual(cli_main(["merge", "--seeds", "1,2,3", "--out", out]), 0)
            with open(out, encoding="utf-8") as f:
                rows = [json.loads(x) for x in f if x.strip()]
            self.assertEqual(len(rows), 3 * sum(DEFAULT_COUNTS.values()))
            self.assertEqual(len({r["id"] for r in rows}), len(rows))
            # 合并后自检仍必须全绿
            self.assertEqual(cli_main(["selftest", "--suite", out]), 0)


class TestGrading(unittest.TestCase):
    def setUp(self):
        self.case = {"id": "x", "category": "vwap", "kind": "numeric",
                     "expected": {"total_cost": "150.50", "vwap": "100.3333"}}

    def test_numeric_equivalence_and_last_block(self):
        t = '[JEV: 3/3 Independent Consensus]\n草稿```json\n{"total_cost":"1","vwap":"2"}\n```\n最终\n```json\n{"total_cost":"150.5","vwap":"100.33330"}\n```'
        g = grade_case(self.case, t)
        self.assertTrue(g["correct"], g)
        self.assertEqual(g["route"], "3/3 Independent Consensus")

    def test_wrong_missing_malformed(self):
        self.assertFalse(grade_case(self.case, '```json\n{"total_cost":"150.50","vwap":"100.3334"}\n```')["correct"])
        self.assertFalse(grade_case(self.case, '```json\n{"total_cost":"150.50"}\n```')["correct"])
        self.assertFalse(grade_case(self.case, "答案是 150.50")["correct"])
        self.assertFalse(grade_case(self.case, '```json\n{"total_cost":"abc","vwap":"100.3333"}\n```')["correct"])

    def test_bool_int_string_fields(self):
        c = {"id": "y", "category": "c", "kind": "adversarial", "expected": {"premise_correct": False, "i": 3, "s": "insufficient_depth"}}
        self.assertTrue(grade_case(c, '```json\n{"premise_correct": false, "i": 3, "s": "insufficient_depth"}\n```')["correct"])
        self.assertTrue(grade_case(c, '```json\n{"premise_correct": "false", "i": "3", "s": "insufficient_depth"}\n```')["correct"])
        self.assertFalse(grade_case(c, '```json\n{"premise_correct": true, "i": 3, "s": "insufficient_depth"}\n```')["correct"])
        self.assertFalse(grade_case(c, '```json\n{"premise_correct": false, "i": 3.5, "s": "insufficient_depth"}\n```')["correct"])

    def test_extract_helpers(self):
        self.assertIsNone(extract_answer("```json\n[1,2]\n```"))
        self.assertEqual(extract_route("x\n[JEV: Fast-Pass]\n"), "Fast-Pass")
        self.assertFalse(is_three_path("Fast-Pass"))
        self.assertTrue(is_three_path("2/3 Majority Consensus"))
        self.assertFalse(is_three_path(None))

    def test_gate(self):
        c = {"id": "g", "category": "gate", "kind": "gate", "expected": {"expect_three_path": True}}
        self.assertTrue(grade_case(c, "[JEV: 3/3 Independent Consensus]")["correct"])
        self.assertFalse(grade_case(c, "[JEV: Fast-Pass]")["correct"])
        self.assertFalse(grade_case(c, "没有标识")["correct"])


class TestStats(unittest.TestCase):
    def test_mcnemar(self):
        self.assertEqual(mcnemar_exact(0, 0), 1.0)
        self.assertAlmostEqual(mcnemar_exact(0, 6), 2 / 64)          # 2×(1/2)^6
        self.assertAlmostEqual(mcnemar_exact(3, 3), 1.0)
        self.assertAlmostEqual(mcnemar_exact(1, 9), 2 * 11 / 1024)   # 2×(C(10,0)+C(10,1))/2^10

    def test_wilson(self):
        lo, hi = wilson(5, 10)
        self.assertAlmostEqual(lo, 0.2366, places=3); self.assertAlmostEqual(hi, 0.7634, places=3)
        self.assertEqual(wilson(0, 10)[0], 0.0)
        self.assertEqual(wilson(0, 0), (0.0, 1.0))


class TestPipeline(unittest.TestCase):
    """端到端:gen → 伪造两组运行结果 → grade/compare/filter,数值与手算一致。"""

    def test_end_to_end(self):
        suite = build_suite(11, {"tick": 4, "gate": 2})
        numeric = [c for c in suite if c["kind"] == "numeric"]
        ref = lambda c: "[JEV: Fast-Pass]\n```json\n" + json.dumps(c["expected"]) + "\n```"
        runs = []
        for i, c in enumerate(numeric):
            runs.append({"case_id": c["id"], "config": "C1", "rep": 0, "text": ref(c) if i < 1 else "无答案", "tokens": 100})
            runs.append({"case_id": c["id"], "config": "C3", "rep": 0, "text": ref(c), "tokens": 300})
        runs.append({"case_id": numeric[0]["id"], "config": "C0", "rep": 0, "error": "RATE_LIMIT"})
        graded = grade_runs(suite, runs)
        s = summarize(graded)
        self.assertEqual(s["C1"]["answer_accuracy"]["k"], 1)
        self.assertEqual(s["C3"]["answer_accuracy"]["k"], 4)
        self.assertEqual(s["C0"]["run_errors"], 1)
        self.assertEqual(s["C3"]["mean_tokens"], 300)
        cmp = compare(graded, "C1", "C3")
        self.assertEqual((cmp["pairs"], cmp["only_C1_correct"], cmp["only_C3_correct"]), (4, 0, 3))
        self.assertAlmostEqual(cmp["mcnemar_p"], 0.25)
        self.assertEqual(len(difficulty_filter(graded, "C1", 0.2, 0.8)), 0)   # 单次重复只有 0/1
        with self.assertRaises(KeyError):
            grade_runs(suite, [{"case_id": "不存在", "config": "C1", "text": ""}])

    def test_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            sp = os.path.join(d, "suite.jsonl")
            self.assertEqual(cli_main(["gen", "--seed", "4", "--out", sp]), 0)
            self.assertEqual(cli_main(["selftest", "--suite", sp]), 0)
            with open(sp, encoding="utf-8") as f:
                first = json.loads(f.readline())
            rp = os.path.join(d, "runs.jsonl")
            with open(rp, "w", encoding="utf-8") as f:
                f.write(json.dumps({"case_id": first["id"], "config": "C1", "rep": 0,
                                    "text": "```json\n" + json.dumps(first["expected"]) + "\n```"}) + "\n")
            out = os.path.join(d, "report.json")
            self.assertEqual(cli_main(["grade", "--suite", sp, "--runs", rp, "--out", out]), 0)
            with open(out, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["summary"]["C1"]["answer_accuracy"]["k"], 1)


if __name__ == "__main__":
    if not _HAS_TZ:
        print(f"⚠️ 跳过 zoneinfo 独立比对(缺 tzdata): {_TZ_WHY}", file=sys.stderr)
        print("⚠️ 该测试是本基准最强的独立证据之一,建议 `pip install tzdata` 后重跑。", file=sys.stderr)
    unittest.main(verbosity=1)
