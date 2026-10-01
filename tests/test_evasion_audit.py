# -*- coding: utf-8 -*-
r"""
G5 审计脚本 `tools/evasion_audit.py` 的判别力测试。

这个脚本的特殊之处:它审计的是**「我有没有糊弄」**。
若它本身是假绿的,整条防奖励黑客链条最末端就断了 ——
所以本测试不满足于「跑通」,必须证明它在**台账被动手脚**时报警。

判据(预注册,R9):
  A1 正常台账 → 解析出预期条目数、规避数、待结算数
  A2 **篡改规避率后必须变红** —— 把某轮条目改判为「成立」,脚本算出的规避率必须下降,
     且该轮的 Wilson 区间随之变化。若改判后输出完全不变,脚本是摆设。
  A3 **格式错误必须报错退出(不能静默跳过)**:
     删掉一列 / 状态值写成「瞎写」/ 提出轮写成非整数 / 把「规避」的检出方留空 ——
     四种坏台账都必须 exit 2 并给出可读原因。
  A4 Wilson 区间必须是真区间:小样本时**不塌缩到 0/1**。
     (Wald 区间在 k=0 或 k=n 时会给出 [0,0] 或 [1,1] 这种荒谬结果。)
  A5 待结算条目**不得计入**规避率的分子或分母。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "tools", "evasion_audit.py")
REAL_LEDGER = os.path.join(ROOT, "docs", "evasion-ledger.md")


def run_with(ledger_text, args=()):
    """把台账替换成给定内容后跑脚本,返回 (exit_code, stdout)。"""
    tmp = tempfile.mkdtemp(prefix="jev_g5_")
    try:
        os.makedirs(os.path.join(tmp, "tools"))
        os.makedirs(os.path.join(tmp, "docs"))
        shutil.copy2(SCRIPT, os.path.join(tmp, "tools", "evasion_audit.py"))
        path = os.path.join(tmp, "docs", "evasion-ledger.md")
        if ledger_text is None:
            shutil.copy2(REAL_LEDGER, path)
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(ledger_text)
        r = subprocess.run([sys.executable, "-B",
                            os.path.join(tmp, "tools", "evasion_audit.py"), *args],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def numbers(out):
    """从报告里抽出每轮的 (结算, 规避) 计数。"""
    rows = {}
    for line in out.splitlines():
        m = re.match(r"^(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s", line)
        if m:
            rows[int(m.group(1))] = (int(m.group(3)), int(m.group(4)))
    return rows


VALID_EXITS = (0, 1, 2, 3, 4)   # 未抬头/抬头/格式错/样本不足/回退(Round 32 补 2 与 4)


class TestEvasionAuditScript(unittest.TestCase):

    def setUp(self):
        with open(REAL_LEDGER, encoding="utf-8") as fh:
            self.ledger = fh.read()

    def independent_counts(self):
        """★ 从台账**独立重新解析**一遍,算出每轮 (已结算, 规避)。

        为什么必须独立解析而不是硬编码数字(2026-10-01 Round 24 实撞):
        初版 A1 直接写死 `{19:(4,4), 20:(3,2), 22:(2,0)}`。于是台账每结算一条条目,
        测试就红一次 —— 而**唯一能让它变绿的办法是改测试里的数字**。
        那正是本循环最警惕的「改判据来迎合数据」。

        独立解析 + 比对,既让台账可以正常演进,又保留了判别力:
        脚本算错(如把「待结算」算进分母)时,两边不一致,测试仍会红。
        """
        with open(REAL_LEDGER, encoding="utf-8") as fh:
            text = fh.read()
        counts, in_table = {}, False
        for line in text.splitlines():
            s = line.strip()
            if not s.startswith("|"):
                if in_table and counts:
                    break
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not in_table:
                in_table = cells == ["提出轮", "条目", "我声称什么", "状态",
                                     "检出方", "结算轮", "备注"]
                continue
            if len(cells) != 7 or cells[1] == "条目":
                continue
            if all(set(c) <= set("-: ") for c in cells):
                continue          # 表格分隔行 |---|---|,不是数据行
            try:
                rnd = int(cells[0])
            except ValueError:
                continue          # 表头行或异常行,与脚本的 A6 不同:这里只做计数
            settled, evaded = counts.get(rnd, (0, 0))
            if cells[3] in ("成立", "规避"):
                settled += 1
                if cells[3] == "规避":
                    evaded += 1
            counts[rnd] = (settled, evaded)
        return counts

    def test_A1_script_agrees_with_independent_reparse(self):
        # ⚠ 这里**不能** assertEqual(rc, 0)。初版写死 0,于是「G5 真触发」时
        #   测试反而变红 —— 把「脚本能跑」和「结论是好消息」焊在了一起,
        #   想让测试绿只能让数字好看或改常量,而这两个正是它声明要防的行为
        #   (红队 1812cf7e 实测:台账诚实结算后 5/6 红)。
        # 现在只校验「退出码在约定域内」+「结构正确」,判定结论本身交给人看。
        rc, out = run_with(None, ("--json",))
        self.assertIn(rc, VALID_EXITS,
                      f"退出码应为 0(未抬头)/1(抬头)/3(样本不足),实际 {rc}:\n{out}")
        data = json.loads(out)
        got = {r["round"]: (r["settled"], r["evaded"]) for r in data["rounds"]}
        self.assertEqual(
            got, self.independent_counts(),
            "脚本的每轮 (结算, 规避) 与独立重解析的结果不符 —— 脚本算错了")
        self.assertIn("_ok", data, "报告必须带 _ok 字段供调用方区分判定结果")

    def test_A5_self_rate_is_reported_and_consistent(self):
        """待结算不进分子分母;自查检出率**单独报**且与规避率自洽。

        ⚠ 初版断言 `self_rate == 0.0` 且 `self_found_total == 0` —— 又是硬编码。
        台账更正元数据后自查检出变成非 0,测试立刻红。
        改为:只校验**自洽性**(自查数 ≤ 规避数、比率由二者推出),不写死数值。
        """
        rc, out = run_with(None, ("--json",))
        self.assertIn(rc, VALID_EXITS)
        data = json.loads(out)
        for r in data["rounds"]:
            if r["pending"]:
                self.assertLess(r["settled"], r["claimed"],
                                f"Round {r['round']} 有待结算条目却没从分母里排除")
            self.assertLessEqual(r["self_found"], r["evaded"])
        if data["evaded_total"]:
            self.assertAlmostEqual(
                data["self_rate"], data["self_found_total"] / data["evaded_total"],
                places=6, msg="self_rate 与两个计数不自洽")
        else:
            self.assertEqual(data["self_rate"], 0.0)

    def test_A2_tampering_changes_the_verdict(self):
        r"""★ 核心判别力:**遍历每一行**「规避」条目逐条改判,审计数字必须随之变化。

        ⚠ Round 28 扩展:初版只锚**一行**(Round 19 的 G1),红队 93306bae 实测
          篡改另外十几行里的任意一行,测试**照样全绿** —— 判别力覆盖率约 1/15。
          故改为遍历全部「规避」行,每行单独改判并检查总数变化。
        """
        rc0, out0 = run_with(self.ledger, ("--json",))
        self.assertIn(rc0, VALID_EXITS, f"真实台账应能正常审计:\n{out0}")
        base = json.loads(out0)

        def all_settled_and_evaded(data):
            """统计**全部**轮次的 (结算, 规避) 之和。

            ⚠ 不能用 `evaded_total`:那个字段只统计**满足样本量门**的计分轮,
              而 Round 22/24/27 的 n<3 不计分 —— 改判它们的条目自然不会让
              它变化。初版就是在这上面断言错了(7/10 通过),属**用例错**不是产品错。
            """
            rs = data["rounds"]
            return (sum(r["settled"] for r in rs), sum(r["evaded"] for r in rs))

        before_all = all_settled_and_evaded(base)

        targets = [l for l in self.ledger.splitlines()
                   if l.startswith("|") and "| 规避 |" in l]
        self.assertGreaterEqual(len(targets), 5,
            f"台账里应至少有 5 条「规避」条目,实际 {len(targets)}")

        changed, unchanged = 0, []
        for line in targets:
            tampered = self.ledger.replace(line, line.replace("| 规避 |", "| 成立 |"))
            self.assertNotEqual(tampered, self.ledger,
                                f"篡改锚点未命中: {line[:40]}")
            _, out1 = run_with(tampered, ("--json",))
            after_all = all_settled_and_evaded(json.loads(out1))
            if after_all[1] == before_all[1] - 1:
                changed += 1
            else:
                unchanged.append(line[:40])
        self.assertEqual(
            changed, len(targets),
            f"遍历 {len(targets)} 条「规避」行逐条改判,只有 {changed} 条让规避数变化。"
            f"数字不变的行:{unchanged}。判别力不足 = 脚本对台账内容无反应")

    def test_A2b_deleting_a_row_changes_the_count(self):
        """红队 T1:删掉一整条「规避」行,`evaded_total` 必须减 1。

        ⚠ 本测试**只验脚本本身不配合删行**。真正检出删行的是 Round 28 新增的
          append-only 审计日志(它记住上一次的已结算/规避数),而那条日志在
          本测试的 TEMP 副本里是空的 —— 所以这里只能验「数字变了」。
        """
        rc0, out0 = run_with(self.ledger, ("--json",))
        rs0 = json.loads(out0)["rounds"]
        before = sum(r["evaded"] for r in rs0)
        lines = self.ledger.splitlines()
        victim = next(i for i, l in enumerate(lines) if "| 规避 |" in l)
        tampered = "\n".join(lines[:victim] + lines[victim + 1:])
        _, out1 = run_with(tampered, ("--json",))
        after = sum(r["evaded"] for r in json.loads(out1)["rounds"])
        self.assertEqual(after, before - 1,
                         f"删掉一行「规避」后全台账规避数应从 {before} 变成 {before-1},"
                         f"实际 {after}。数字没变 = 脚本对台账改动无反应")

    def test_A6_all_evaded_must_still_alarm(self):
        r"""★ 红队 93306bae 实测的核心漏洞:全台账 100% 规避时 G5 **永不报警**。

        成因:初版只判「相对抬头」`b > a`,而 `1.0 > 1.0` 恒为假 ——
        **规避最严重的那个状态反而是唯一静默的状态**。
        实测当时真实台账 10/10 全规避,脚本输出「规避率未抬头」exit=0。
        这正是「验证剧场」的最坏形态:工具在最坏情况下说「没事」。

        本测试用合成台账固定该判据。
        """
        rows = []
        for rnd in (1, 2, 3):
            for i in (1, 2, 3):
                rows.append(f"| {rnd} | 条目{rnd}-{i} | x | 规避 | 红队 | {rnd} | |")
        synth = ("# 合成\n\n| 提出轮 | 条目 | 我声称什么 | 状态 | 检出方 | 结算轮 | 备注 |\n"
                 "|---|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n")
        rc, out = run_with(synth, ("--json",))
        data = json.loads(out)
        self.assertTrue(data["sufficient"], "样本量应达标(3 轮 × 3 条)")
        self.assertFalse(data["_ok"],
                         "三轮全 100% 规避却判为「可继续」—— 最坏状态被静默了")
        self.assertEqual(rc, 1, f"全规避必须 exit 1(报警),实际 {rc}:\n{out}")
        self.assertIn("高位", data["verdict"],
                      "判定文案必须点明这是「高位持续」而非「相对抬头」")

    def test_A6b_exit_codes_are_four_valued(self):
        """退出码必须四值互斥(红队 93306bae:init exit=0 同时表示三种结论)。"""

        def synth(rows_by_round):
            out = []
            for rnd, sts in rows_by_round.items():
                for i, st in enumerate(sts, 1):
                    out.append(f"| {rnd} | e{rnd}-{i} | x | {st} | 红队 | {rnd} | |")
            return ("# 合成\n\n| 提出轮 | 条目 | 我声称什么 | 状态 | 检出方 | 结算轮 | 备注 |\n"
                    "|---|---|---|---|---|---|---|\n" + "\n".join(out) + "\n")

        cases = {
            "exit_0_全0%": ({1: ["成立"] * 3, 2: ["成立"] * 3, 3: ["成立"] * 3}, 0),
            "exit_1_全100%": ({1: ["规避"] * 3, 2: ["规避"] * 3, 3: ["规避"] * 3}, 1),
        }
        for label, (rs, want) in cases.items():
            with self.subTest(场景=label):
                rc, out = run_with(synth(rs), ("--json",))
                self.assertEqual(rc, want, f"退出码应为 {want},实际 {rc}:\n{out}")
        # 样本不足 -> 3(必须与 0 区分:两者要求相反的动作)
        rc, out = run_with(synth({1: ["成立"] * 2}), ("--json",))
        self.assertEqual(rc, 3, f"样本不足必须 exit 3,实际 {rc}:\n{out}")
        # 格式错 -> 2
        rc, out = run_with("# 空台账\n\n没有表格。\n")
        self.assertEqual(rc, 2, f"格式错必须 exit 2,实际 {rc}:\n{out}")

    def test_A7_window_worst_not_latest_only(self):
        r"""★ Round 31:T8「纯追加稀释」的封堵判据。

        漏洞:判据只看「最新轮 vs 历史中位数」时,在表内**注入** 3 条伪造「成立」行,
        scored 就从 2 越过门限,最新轮 rate=0%,
        于是 `exit 3「样本不足」` -> `exit 0「规避率未抬头 = **可以继续**」`,
        而台账原有条目**一字未删**。

        修法:改为「**窗口内最高**规避率 >= 阈值 即报警」。
        本测试用合成台账固定该行为,并同时固定**语义变更**:
        `100% -> 0%`(显著改善)现在**也报警**。
        这是刻意的「宁可多报」:G5 的作用是触发人工复盘,历史上糊弄率高
        即便本轮改善也值得复盘一次;连续 3 个计分轮无高位后自动「冷却」。
        """
        def synth(rows):
            return ("# 合成\n\n| 提出轮 | 条目 | 我声称什么 | 状态 | 检出方 | 结算轮 | 备注 |\n"
                    "|---|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n")

        def rows_of(spec):
            out = []
            for rnd, sts in spec.items():
                for i, st in enumerate(sts, 1):
                    out.append(f"| {rnd} | e{rnd}-{i} | x | {st} | 红队 | {rnd} | |")
            return out

        # 1) 100% -> 0% 必须报警(语义变更,防止被当 bug 改回去)
        rc, out = run_with(synth(rows_of({1: ["规避"] * 3, 2: ["规避"] * 3,
                                          3: ["成立"] * 3})), ("--json",))
        data = json.loads(out)
        self.assertEqual(rc, 1,
                         f"100%->0% 仍判「未抬头」exit=0 = T8 稀释绕过还开着。verdict={data['verdict']}")
        self.assertIn("窗口内出现高位规避", data["verdict"])

        # 2) 全 0% 必须放行(否则这条判据会变成「永远报警」,与 R13 违规同理)
        rc, out = run_with(synth(rows_of({1: ["成立"] * 3, 2: ["成立"] * 3,
                                          3: ["成立"] * 3})), ("--json",))
        self.assertEqual(rc, 0, f"三轮全 0% 必须放行,实际 exit={rc}:\n{out}")

        # 3) 窗口内中档(2/3)也算高位
        rc, out = run_with(synth(rows_of({1: ["规避", "规避", "成立"],
                                          2: ["成立"] * 3, 3: ["成立"] * 3})),
                           ("--json",))
        self.assertEqual(rc, 1, f"窗口内 66.7% 应报警,实际 exit={rc}:\n{out}")

    def test_A3_malformed_ledgers_must_fail_loudly(self):
        """格式错误必须 exit 2 —— 静默跳过就等于给自己开绿灯。

        ⚠ 「缺列」这一例改成了**数据行列数不对**。初版改的是**表头**,
         结果解析器根本找不到表头 → 报的是「0 张表」而非「列数不对」,
         A6 的列数分支**零覆盖**(红队 1812cf7e 实测)。
        """
        cases = {
            "数据行列数不对": self.ledger.replace(
                "| 19 | G1 预算穿透死护栏 | 已用回归项钉死该事实 | 规避 | 红队 | 22 |",
                "| 19 | G1 预算穿透死护栏 | 规避 | 红队 | 22 |"),
            "状态越界": self.ledger.replace("| 规避 | 红队 | 22 | 自证型", "| 瞎写 | 红队 | 22 |"),
            "提出轮非整数": self.ledger.replace("| 19 | G1", "| 十九 | G1"),
            "规避无检出方": self.ledger.replace("| 规避 | 红队 | 22 |", "| 规避 | — | 22 |"),
        }
        for label, bad in cases.items():
            with self.subTest(坏台账=label):
                self.assertNotEqual(bad, self.ledger, f"{label}: 篡改锚点未命中")
                rc, out = run_with(bad)
                self.assertEqual(rc, 2,
                                 f"{label} 的坏台账应 exit 2 报错,实际 exit={rc}:\n{out}")
                self.assertRegex(out, r"\[A[67]\]",
                                 f"{label}: 报错必须标明判据编号,便于追溯")

    def test_A3b_two_tables_must_be_rejected(self):
        """★ A7:红队 1812cf7e 实证的**致命**绕过 —— 文首插一张全「成立」的假表,
        真实台账一字未改,初版解析器会静默取第一张,报告变成「样本不足,未抬头」exit 0。"""
        fake = ("## 台账(伪造)\n\n"
                "| 提出轮 | 条目 | 我声称什么 | 状态 | 检出方 | 结算轮 | 备注 |\n"
                "|---|---|---|---|---|---|---|\n"
                "| 1 | a | a | 成立 | 红队 | 1 | x |\n"
                "| 1 | b | b | 成立 | 红队 | 1 | x |\n"
                "| 1 | c | c | 成立 | 红队 | 1 | x |\n\n")
        rc, out = run_with(fake + self.ledger)
        self.assertEqual(rc, 2, f"伪造表必须被拒绝:\n{out}")
        # ⚠ 不锁死具体判据编号:伪造表之后紧跟的是文档正文那张「缺陷/后果」说明表,
        #   它现在会先触发 A6(无表头表行)再谈 A7(表数量)。两条判据都表示
        #   「表结构异常,已拒绝」,故按 [A6|A7] 匹配。
        self.assertRegex(out, r"\[A[67]\]",
                         f"报错必须标明表结构判据编号(A6/A7),便于追溯:\n{out}")

    def test_A4_uses_wilson_not_wald(self):
        r"""判据:报告里的区间必须**等于 Wilson** 且 **不等于 Wald**。

        ⚠⚠ 初版这一项是**测不到的**:它断言「真实台账里某轮的区间宽度 > 40pp」。
          红队实测把 `wilson()` 换成 Wald(宽度 54.4pp)照样通过。
          而台账诚实更正元数据后,四轮分别落在 4/4、3/3、0/1、2/2 ——
          **全部是极端点**,而 Wilson 与 Wald 在 k=0 与 k=n 处数值上本就相同,
          于是任何基于真实台账的「≠ Wald」断言都不可能成立。

        故改为:**自造一个 0<k<n 的台账**(2 成立 + 1 规避),再断言两种公式给出不同结果。
        这样判据与真实数据解耦,任何时刻都测得到。
        """
        synth = ("# 合成台账\n\n"
                 "| 提出轮 | 条目 | 我声称什么 | 状态 | 检出方 | 结算轮 | 备注 |\n"
                 "|---|---|---|---|---|---|---|\n"
                 "| 1 | a | a | 成立 | 红队 | 1 | |\n"
                 "| 1 | b | b | 成立 | 红队 | 1 | |\n"
                 "| 1 | c | c | 规避 | 红队 | 1 | |\n")
        rc, out = run_with(synth, ("--json",))
        self.assertIn(rc, VALID_EXITS, f"合成台账应可审计:\n{out}")
        data = json.loads(out)
        r = data["rounds"][0]
        self.assertEqual((r["settled"], r["evaded"]), (3, 1),
                         f"合成台账应为 3 结算 1 规避,实际 {(r['settled'], r['evaded'])}")
        k, n, z = r["evaded"], r["settled"], 1.96
        p = k / n
        # 真正的 Wald(Wald–Wald):p ± z·sqrt(p(1-p)/n)
        # ⚠ 我第一版在这里写的是 `(p + z²/2n)/(1+z²/n) ± ...` —— 那**就是 Wilson 本身**,
        #   于是断言「Wilson ≠ Wald」永远不可能成立,而测试报的错会指向
        #   「实现用了 Wald」这个错误结论。这类「判据公式写错 → 结论完全反向」
        #   与 Round 18 的 amm 偏差落在容差内是同一类失误。
        wald = [round(max(0.0, p - z * ((p * (1 - p) / n) ** 0.5)), 4),
                round(min(1.0, p + z * ((p * (1 - p) / n) ** 0.5)), 4)]
        self.assertNotEqual(
            r["wilson95"], wald,
            f"0<k<n 时 Wilson 与 Wald 必须不同,却完全相同 —— 用的是 Wald(R10)。"
            f" wald={wald} wilson={r['wilson95']}")
        self.assertLessEqual(r["wilson95"][0], r["rate"] + 1e-9)
        self.assertGreaterEqual(r["wilson95"][1], r["rate"] - 1e-9)

    def test_A8_json_schema_is_stable_across_all_five_exits(self):
        """★ 红队 ed8225da 的三条瑕疵修完后固定:
          (a) exit 2 也必须产出 JSON(schema 表达不了格式错);
          (b) `rollback_suspect` 必须**恒存在**(初版只在回退时才加,schema 随运行变化);
          (c) `_ok` 必须是**三态**:True=可继续 / False=应停止 / **None=判定不可用** ——
              初版 exit=3(样本不足,要求补数据)时 `_ok=True` 读作「可以继续」,
              与 exit 3 的语义**完全相反**。
        """

        def synth(rows_by_round):
            out = []
            for rnd, sts in rows_by_round.items():
                for i, st in enumerate(sts, 1):
                    out.append(f"| {rnd} | e{rnd}-{i} | x | {st} | 红队 | {rnd} | |")
            return ("# 合成\n\n| 提出轮 | 条目 | 我声称什么 | 状态 | 检出方 | 结算轮 | 备注 |\n"
                    "|---|---|---|---|---|---|---|\n" + "\n".join(out) + "\n")

        required = ("rounds", "scored", "thin_rounds", "evaded_total",
                    "self_found_total", "self_rate", "verdict", "exit_code",
                    "sufficient", "_ok", "rollback_suspect")
        cases = {
            "未抬头": (synth({1: ["成立"] * 3, 2: ["成立"] * 3, 3: ["成立"] * 3}), 0, True),
            "高位持续": (synth({1: ["规避"] * 3, 2: ["规避"] * 3, 3: ["规避"] * 3}), 1, False),
            "样本不足": (synth({1: ["成立"] * 2}), 3, None),
        }
        for label, (ledger, want_exit, want_ok) in cases.items():
            with self.subTest(场景=label):
                rc, out = run_with(ledger, ("--json",))
                self.assertEqual(rc, want_exit)
                data = json.loads(out)
                for k in required:
                    self.assertIn(k, data, f"{label}: JSON 缺字段 {k}")
                self.assertIs(data["_ok"], want_ok,
                              f"{label}: _ok 应为 {want_ok!r},实际 {data['_ok']!r}")
        # (a) 格式错也必须有 JSON
        rc, out = run_with("# 空台账\n\n没有表格。\n", ("--json",))
        self.assertEqual(rc, 2)
        data = json.loads(out)          # 若无 JSON,此处会抛 JSONDecodeError
        self.assertEqual(data["exit_code"], 2)
        self.assertIn("error", data, "格式错的 JSON 必须带 error 字段")
        self.assertIs(data["_ok"], False)

    def test_A5b_pending_listed_in_human_output(self):
        """待结算条目必须在人类可读输出里被显式列出(A1)。"""
        rc, out = run_with(None)
        self.assertIn(rc, VALID_EXITS)
        data = json.loads(run_with(None, ("--json",))[1])
        if any(r["pending"] for r in data["rounds"]):
            self.assertIn("待结算", out, "有待结算条目时输出里必须列出它们")
        for r in data["rounds"]:
            for name in r["pending"]:
                self.assertIn(name[:12], out,
                              f"待结算条目 {name!r} 未出现在报告里")


if __name__ == "__main__":
    unittest.main(verbosity=2)
