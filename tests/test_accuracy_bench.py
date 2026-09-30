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
import re
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
from jevbench.grading import compare, difficulty_filter, grade_case, grade_runs, reference_text, summarize  # noqa: E402
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


class TestCognitiveTraps(unittest.TestCase):
    """认知陷阱题(CRT 等):答案唯一,但直觉答案诱人且错误。

    这类题是"单路 vs 多路"的主要区分来源 —— 常规数值题已实测被单路做满
    (C0 97.5%),而陷阱题会诱导系统 1 给出自信的错误答案。
    """

    def setUp(self):
        self.rng = random.Random(20260928)

    def test_crt_reference_values(self):
        """CRT 原始三题的手算值(文献:5 分 / 5 分钟 / 47 天)。"""
        self.assertEqual(solve.crt_ball(110, 100), "5")       # 直觉错答 10
        self.assertEqual(solve.crt_widgets(5, 5, 5, 100, 100), "5")  # 直觉错答 100
        self.assertEqual(solve.crt_lily(48), "47")            # 直觉错答 24

    def test_crt_ball_identity(self):
        """性质检验:球价 + 球拍价 = 总价,且球拍价比球价正好贵 diff。"""
        for _ in range(200):
            diff = self.rng.choice([100, 90, 80, 60, 50, 40, 120])
            total = diff + self.rng.choice([10, 20, 30, 40, 60, 80])
            ball = D(solve.crt_ball(total, diff))
            bat = ball + D(diff)
            self.assertEqual(ball + bat, D(total))
            self.assertEqual(bat - ball, D(diff))

    def test_widgets_proportionality(self):
        """机器题:产量与机器数成正比、与时间成正比(用两种口径交叉验算)。"""
        for _ in range(200):
            m = self.rng.choice([5, 3, 4, 6, 10])
            w = self.rng.choice([m, m * 2, m * 3])
            tm = self.rng.choice([20, 50, 100, 200])
            tw = self.rng.choice([tm, tm * 2, tm * 5])
            got = D(solve.crt_widgets(m, 5, w, tm, tw))
            # 单位产能:每台每分钟产量
            rate = D(w) / (D(m) * 5)
            self.assertAlmostEqual(float(got), float(D(tw) / (rate * D(tm))), places=4)

    def test_lily_is_one_less(self):
        for d in (24, 30, 36, 48, 60, 72, 100):
            self.assertEqual(solve.crt_lily(d), str(d - 1))

    def test_decimal_compare_not_string_compare(self):
        """核心陷阱:模型常按"版本号/逐位"思维比较,得出 9.11 > 9.9(错)。

        注意:Python 的字符串比较**恰好**给出正确答案("9.11" < "9.9",
        因为 '1' < '9'),所以本陷阱不是字符串序造成的,而是
        "小数部分逐位比较"的直觉(0.11 vs 0.9 → 误以为 11 > 9)。
        """
        self.assertEqual(solve.decimal_max("9.11", "9.9"), "9.9")
        self.assertLess("9.11", "9.9")               # 字符串序恰好也是对的,故陷阱另有来源
        self.assertGreater(11, 9)                    # 直觉误用:小数位当整数比 → 错
        self.assertEqual(solve.decimal_max("1.10", "1.9"), "1.9")
        self.assertEqual(solve.decimal_max("10.11", "10.9"), "10.9")

    def test_letter_count_matches_manual(self):
        self.assertEqual(solve.count_letter("strawberry", "r"), "3")
        self.assertEqual(solve.count_letter("blueberry", "b"), "2")
        self.assertEqual(solve.count_letter("raspberry", "r"), "3")

    def test_mushroom_dry_matter_conserved(self):
        """性质检验:干物质在晾晒前后守恒(这是本题唯一正确的解法依据)。"""
        for _ in range(100):
            kg = D(self.rng.choice(["1000", "100", "500", "200"]))
            pi, pf = self.rng.choice([("0.99", "0.98"), ("0.98", "0.96"), ("0.95", "0.90")])
            lost = D(solve.mushroom_water_lost(str(kg), pi, pf))
            dry_before = kg * (1 - D(pi))
            dry_after = (kg - lost) * (1 - D(pf))
            self.assertLessEqual(abs(dry_before - dry_after), D("0.01"))
        self.assertEqual(solve.mushroom_water_lost("1000", "0.99", "0.98"), "500.00")

    def test_candy_bruteforce_crosscheck(self):
        """糖果题:与独立暴力实现交叉验证(枚举配比 + 枚举对手安排)。"""
        def brute(rc, sc, ia, ip):
            tc, ts = sum(rc), sum(sc)
            for n in range(0, tc + ts + 1):
                for x in range(max(0, n - ts), min(n, tc) + 1):
                    y = n - x
                    safe = True
                    for ac in range(0, min(x, rc[ia]) + 1):
                        for pc in range(0, min(x - ac, rc[ip]) + 1):
                            if x - ac - pc > rc[2]:
                                continue
                            for a_s in range(0, min(y, sc[ia]) + 1):
                                for ps in range(0, min(y - a_s, sc[ip]) + 1):
                                    if y - a_s - ps > sc[2]:
                                        continue
                                    if not ((ac >= 1 and ps >= 1) or (a_s >= 1 and pc >= 1)):
                                        safe = False
                                        break
                                if not safe:
                                    break
                            if not safe:
                                break
                        if not safe:
                            break
                    if safe:
                        return n
            return None

        for rc, sc in [([7, 9, 8], [7, 6, 4]), ([5, 4, 3], [4, 3, 2]), ([4, 4, 4], [4, 4, 4])]:
            self.assertEqual(solve.candy_min(rc, sc, 0, 1), brute(rc, sc, 0, 1), f"{rc} {sc}")
        # 文献原题答案 21
        self.assertEqual(solve.candy_min([7, 9, 8], [7, 6, 4], 0, 1), 21)

    def test_candy_trap_is_effective(self):
        """陷阱必须有效:忽略"形状可手感分辨"会得到**严格更大**的错答。

        若某组参数下两者相等,该题不构成审题陷阱,不应入题集。
        """
        for _ in range(50):
            rc = [self.rng.randint(3, 9) for _ in range(3)]
            sc = [self.rng.randint(2, 8) for _ in range(3)]
            self.assertGreater(solve.blind_candy_min(rc, sc, 0, 1), solve.candy_min(rc, sc, 0, 1),
                               f"陷阱无效: rc={rc} sc={sc}")
        self.assertEqual(solve.blind_candy_min([7, 9, 8], [7, 6, 4], 0, 1), 29)  # 文献常见错答

    def test_trap_cases_are_generated_and_gradable(self):
        """陷阱题必须真的进入题集,且参考答案能被判分器判对、扰动判错。"""
        suite = build_suite(20260928)
        traps = [c for c in suite if c["kind"] == "trap"]
        self.assertGreaterEqual(len(traps), 15, "陷阱题数量过少,不足以提供区分力")
        for c in traps:
            self.assertTrue(grade_case(c, reference_text(c))["correct"], c["id"])

    def test_trap_candy_uses_correct_params(self):
        """糖果题若参数导致陷阱失效,必须回退到文献原题参数(而非静默产出无效题)。"""
        for c in build_suite(7):
            if c["category"] != "trap_candy":
                continue
            exp = int(c["expected"]["min_candies"])
            m = re.search(r"圆形:(\d+) (\d+) (\d+)\n五角星形:(\d+) (\d+) (\d+)", c["question"])
            self.assertIsNotNone(m, c["id"])
            rc = [int(x) for x in m.group(1, 2, 3)]
            sc = [int(x) for x in m.group(4, 5, 6)]
            self.assertGreater(solve.blind_candy_min(rc, sc, 0, 1), exp, c["id"])

    def test_nonterminating_answer_needs_explicit_precision(self):
        """若参考解不是有限小数,题面**必须**规定精度。

        实测 bug(2026-09-28):`trap_widgets` 原题面只写"<分钟数>",未规定精度,
        参考解给 8.3333 而模型答 8.33(同样正确),被判错 —— 3 道题误判。
        判据:参考解小数位 > 4 时,题面必须出现"保留 N 位小数"。
        """
        for c in build_suite(20260928):
            for key, want in c["expected"].items():
                if not isinstance(want, str):
                    continue
                try:
                    d = D(want)
                except Exception:
                    continue
                frac = -d.as_tuple().exponent
                if frac > 4:                      # 非有限/长小数,必须声明精度
                    self.assertRegex(c["question"], r"保留\s*\d+\s*位小数",
                                     f"{c['id']} 的 {key}={want} 需在题面规定精度")

    def test_widgets_prompt_states_precision(self):
        """机器题专项守护:题面必须写明保留 4 位小数。"""
        for c in build_suite(3):
            if c["category"] != "trap_widgets":
                continue
            self.assertIn("保留 4 位小数", c["question"], c["id"])

    def test_ma_static_einstellung_cases(self):
        """定势效应题(MisguidedAttention 类)必须存在且参考答案判对。

        考察"抑制对经典原题的套用",与 candy 类(提取隐含约束)考察不同能力 ——
        实测 shangtang 在 candy 上 33.3% 但在这类题上 100%,故两类必须并存。
        """
        ma = [c for c in build_suite(20260928) if c["category"] == "ma_static"]
        self.assertEqual(len(ma), 12, "定势效应题应为 12 道")
        for c in ma:
            self.assertTrue(grade_case(c, reference_text(c))["correct"], c["id"])

    def test_ma_static_answers_independently_verified(self):
        """逐题核对:答案应与**经典原题**相反或更简单(全部独立验证,非引用来源)。"""
        ma = [c for c in build_suite(20260928) if c["category"] == "ma_static"]
        exp = {}
        for c in ma:
            for k, v in c["expected"].items():
                exp[k] = v
        # 水壶 4L 不可能(gcd 整除性,见下方专项测试)
        self.assertEqual(exp["status"], "impossible")
        # 反 Monty Hall:保持(暴力枚举 12/18=2/3,见下方专项测试)
        self.assertEqual(exp["action"], "keep")
        # 线性增长半满在第 20 天(经典翻倍题是第 39 天)
        self.assertEqual(exp["day"], "20")
        # 已死猫 P(活)=0(经典薛定谔猫是 0.5)
        self.assertEqual(exp["alive_prob"], "0")
        # 电车:五个已死者 → 不拉杆
        self.assertEqual(exp["pull"], "no")
        # 羽毛 vs 钢:1 磅 = 0.4536 kg < 1 kg
        self.assertEqual(exp["heavier"], "feathers")
        # 一次过河
        self.assertEqual(exp["trips"], "1")

    def test_monty_hall_inverse_bruteforce(self):
        """反 Monty Hall 暴力枚举验证:保持获胜 2/3(与原题"换门"相反)。"""
        from itertools import permutations
        win_keep = win_switch = total = 0
        for layout in permutations(["donkey", "car", "car"]):
            for pick in range(3):
                others = [i for i in range(3) if i != pick]
                car_others = [i for i in others if layout[i] == "car"]
                if not car_others:
                    continue                       # 主持人无法露出车 → 不计
                total += 1
                remaining = [i for i in others if i != car_others[0]][0]
                if layout[pick] == "car":
                    win_keep += 1
                if layout[remaining] == "car":
                    win_switch += 1
        self.assertEqual(total, 18)
        self.assertEqual(win_keep, 12)             # 2/3
        self.assertEqual(win_switch, 6)            # 1/3
        self.assertGreater(win_keep, win_switch)   # 与原 Monty Hall 相反

    def test_jugs_impossible_gcd_rule(self):
        """水壶题 gcd 整除性验证:4L 用 6L+12L 不可能;3L 用 1L+2L 可能。"""
        from math import gcd
        self.assertEqual(gcd(6, 12), 6)
        self.assertNotEqual(4 % gcd(6, 12), 0)
        self.assertEqual(3 % gcd(1, 2), 0)

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
        # 2026-09-30 门控改「断言优先」后新增的单路标识,不得被误判为三路
        self.assertFalse(is_three_path("断言通过"))
        self.assertFalse(is_three_path("断言不适用"))
        self.assertTrue(is_three_path("3/3 Independent Consensus"))
        self.assertTrue(is_three_path("Triggered by Test Failure"))

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
