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
import unicodedata
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
        # ⚠⚠ Round 47 红队 `93f0497b` 实测的**测量链路断裂**:
        # 父进程用 `encoding="utf-8"` 解码,**但子进程自身 stdout 是 gbk**(本机 cp936)——
        # 中文在管道里被按 gbk 编码、又按 utf-8 解码 → mojibake →
        # A5b/A6/A7/A9 四条判据在**默认环境**下全红,`npm test` 的 `&&` 链
        # 断在本文件 → **后面的套件(含 test_gate_no_route_evidence.py)从未被执行过**。
        # 此前之所以「全绿」,是因为调用方手工设了 `PYTHONIOENCODING=utf-8` ——
        # **测量环境与默认环境不一致,等于没测**(R4)。
        # 修法:给**子进程**加 `-X utf8`(只加在父进程上没用,子是全新进程)。
        r = subprocess.run([sys.executable, "-X", "utf8", "-B",
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

# ★★ Round 71 新增(**防我自己重复犯错**):我**连续两轮**用同一个 `edit` 锚点错误
# 删掉了一个 `def test_...` 行 —— R70 吃掉 `test_A12c`,R71 吃掉
# `test_A12_ledger_drift_during_run_is_fatal`。两次的后果一样:被吃掉的用例
# **变成前一个用例里的死代码**,`Ran N tests OK` 是**假绿**。
# 两次的唯一线索都是「**测试数没涨**」,而两次**我都没看**。
# 所以判据必须写进文件,不能靠我记性 —— 这就是本仓反复记的那条:
# 「靠记性堵不住,只能靠机制」。
EXPECTED_TESTS = frozenset({
    "test_A1_script_agrees_with_independent_reparse",
    "test_A2_tampering_changes_the_verdict",
    "test_A2b_deleting_a_row_changes_the_count",
    "test_A3_malformed_ledgers_must_fail_loudly",
    "test_A3b_two_tables_must_be_rejected",
    "test_A4_uses_wilson_not_wald",
    "test_A5_self_rate_is_reported_and_consistent",
    "test_A5b_pending_listed_in_human_output",
    "test_A6_all_evaded_must_still_alarm",
    "test_A6b_exit_codes_are_four_valued",
    "test_A7_window_worst_not_latest_only",
    "test_A8_json_schema_is_stable_across_all_five_exits",
    "test_A8c_error_paths_have_the_same_key_set",
    "test_A9_git_anchor_is_actually_covered",
    "test_A10_backfilled_rows_count_and_are_surfaced",
    "test_A11_backfill_is_cross_checked_against_objective_fact",
    "test_A11b_structural_signal_is_not_label_driven",
    "test_A11c_a11_numbers_are_independently_recomputed",
    "test_A11d_unparseable_settle_round_is_surfaced",
    "test_A11e_a_differently_shaped_ledger_pins_production",
    "test_A12_ledger_drift_during_run_is_fatal",
    "test_A12b_digest_is_reported_so_a_verdict_is_reproducible",
    "test_A12c_error_path_still_carries_the_digest",
    "test_A12d_drift_inside_parse_is_detected",
})


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

    def test_A9_git_anchor_is_actually_covered(self):
        r"""★ 红队 91faf08d 实测(Q4-F):把 `git_head_baseline()` 整个改成 `return None`
        (即退回 Round 37 之前「清空日志即绕过」的状态),
        **`tests/test_evasion_audit.py` 的 12 项照样全绿** ——
        整个 Round 37 的修复**零回归测试**,删掉也没人拦。

        本项在 TEMP 里建一个**带自己的 git 仓库**的副本(git init + commit),
        让 `git show HEAD:docs/evasion-audit.log` 可读,然后:
          1. 删一条「规避」行 + **清空整个日志** → 必须 exit 4;
          2. 把副本的 `git_head_baseline` 打桩成 `return None` → 本测试必须失败。
             (第 2 条是本测试的判别力自证:它证明自己真能检出锚被摘掉。)
        """
        import subprocess as _sp
        t = tempfile.mkdtemp(prefix="jev_gitanchor_")
        try:
            for sub in ("tools", "docs"):
                os.makedirs(os.path.join(t, sub), exist_ok=True)
            shutil.copy2(os.path.join(ROOT, "tools", "evasion_audit.py"),
                         os.path.join(t, "tools", "evasion_audit.py"))
            shutil.copy2(os.path.join(ROOT, "docs", "evasion-ledger.md"),
                         os.path.join(t, "docs", "evasion-ledger.md"))
            # 造一份有内容的日志,好让 commit 里有真实基线
            with open(os.path.join(t, "docs", "evasion-audit.log"), "w",
                      encoding="utf-8") as fh:
                fh.write("# 基线日志\n2026-01-01 00:00:00 | aaaaaaaaaaaaaaaa | 11 | 11 | 9 | seed | 3\n")
            env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                       GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
            for args in (["git", "init", "-q"], ["git", "add", "-A"],
                         ["git", "commit", "-qm", "seed"]):
                _sp.run(args, cwd=t, capture_output=True, env=env)
            probe = _sp.run(["git", "show", "HEAD:docs/evasion-audit.log"],
                            cwd=t, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(probe.returncode, 0,
                             f"副本 git 锚不可读,后续实验无意义:\n{probe.stderr}")

            def run():
                # `-X utf8` 必须给**子进程**(理由见本文件 `_audit` 处的长注释)。
                r = _sp.run([sys.executable, "-X", "utf8", "-B",
                             os.path.join(t, "tools", "evasion_audit.py")],
                            cwd=t, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
                return r.returncode, (r.stdout or "") + (r.stderr or "")

            # ① 清空日志 + 删台账一条规避行 -> 必须报回退
            led = os.path.join(t, "docs", "evasion-ledger.md")
            lines = [l for l in open(led, encoding="utf-8").read().splitlines()
                     if "| 规避 |" not in l]
            with open(led, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
            with open(os.path.join(t, "docs", "evasion-audit.log"), "w",
                      encoding="utf-8") as fh:
                fh.write("# 被清空,只剩表头\n")
            rc, out = run()
            self.assertEqual(rc, 4,
                             f"清空日志 + 删台账行必须 exit 4(回退),实际 {rc}:\n{out[-400:]}")
            self.assertIn("回退", out, f"应报回退嫌疑:\n{out[-400:]}")

            # ② 把锚打桩成 return None -> 回退检测必须失效(证明本测试真能检出锚被摘)
            src = os.path.join(t, "tools", "evasion_audit.py")
            text = open(src, encoding="utf-8").read()
            stubbed = text.replace(
                'r = subprocess.run(["git", "show", "HEAD:docs/evasion-audit.log"],',
                'return None  # STUB\n    r = subprocess.run(["git", "show", "HEAD:docs/evasion-audit.log"],',
                1)
            self.assertNotEqual(stubbed, text, "打桩锚点未命中 —— 本测试的判别力自证失效")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(stubbed)
            rc2, out2 = run()
            self.assertNotEqual(
                rc2, 4,
                "把 git 锚摘掉之后回退检测**仍然**报 exit 4 —— "
                "说明基线另有来源(工作区文件?),本测试没有真正测到 git 锚")
        finally:
            shutil.rmtree(t, ignore_errors=True)

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

        # (d) ★ Round 68 红队 F2:**键集必须与退出码无关**。
        #     此前 exit 2 的两条子路径(`_fail()` 与 `__main__` 最外层兜底)**各手写一份
        #     字面量**,于是 A10 新增的 `backfilled_total` / `backfilled_evaded` 双双缺席 ——
        #     schema 又随退出码变化了,与 Round 32 修 `rollback_suspect` 时是**同一形态**。
        #     ⚠ 上面那条「必需键存在」的断言**抓不住它**(缺的键不在 required 里),
        #     所以这里必须改成**集合相等** —— 只加两个键到 required 只是补一次窟窿,
        #     下一次新增字段还会漏。
        ref = None
        for label, ledger in [("exit0", synth({1: ["成立"] * 3, 2: ["成立"] * 3, 3: ["成立"] * 3})),
                              ("exit1", synth({1: ["规避"] * 3, 2: ["规避"] * 3, 3: ["规避"] * 3})),
                              ("exit2", "# 空台账\n\n没有表格。\n"),
                              ("exit3", synth({1: ["成立"] * 2})),
                              ("exit4", synth({1: ["成立"] * 3, 2: ["成立"] * 3, 3: ["成立"] * 3}))]:
            with self.subTest(键集=label):
                _rc, out = run_with(ledger, ("--json",))
                ks = frozenset(json.loads(out))
                if ref is None:
                    ref = ks
                self.assertEqual(
                    ks, ref,
                    f"{label}: JSON 键集与 exit 0 不同 —— 对称差 {sorted(ks ^ ref)}。"
                    f"schema 随退出码变化,消费方必须写 `.get(..., 默认)` 才能读,"
                    f"正是「同码不同义」的近亲")

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


    def test_A10_backfilled_rows_count_and_are_surfaced(self):
        r"""★ 铁律 1 声明「标 `回填` 的不计入规避率统计」,而脚本**从不读 `备注`**。

        台账 §「铁律 1 未实现」把它留成「二选一 · 未拍板」,已躺 22 轮。本轮**不擅自改语义**
        (那正是它要求人工拍板的原因),而是把**唯一 R13 合规的那个选项**钉死,
        并让「补写」这件事**可见**:

        ① **回填行必须仍被计入**。实现「回填不计入」= 我可以靠给一条规避行贴上 `回填`
           标签,把它从指标里摘掉 —— **指标落回我手里**,正是 R13 禁止的「优化让指标好看」。
           故当前行为(照实计入)是**更难看**的那一侧,必须钉住,
           防未来某轮以「让规则与实现一致」为名把它改成排除。
        ② **回填计数必须被报出**。否则「事后补写」完全不可见 ——
           铁律 1 想防的恰恰是「事后补写冒充预注册」,而它连数字都没露过。
        """
        def synth(remark):
            rows = []
            for rnd in (1, 2, 3):
                for i in (1, 2, 3):
                    rows.append(f"| {rnd} | 条目{rnd}-{i} | x | 规避 | 红队 | {rnd} | |")
            rows.append(f"| 3 | 补写的那条 | x | 规避 | 红队 | 3 | {remark} |")
            return ("# 合成\n\n| 提出轮 | 条目 | 我声称什么 | 状态 | 检出方 | 结算轮 | 备注 |\n"
                    "|---|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n")

        plain = run_with(synth("普通备注"), ("--json",))
        marked = run_with(synth("**回填**。事后补写。"), ("--json",))
        d_plain, d_marked = json.loads(plain[1]), json.loads(marked[1])

        # ① 「回填」二字不得改变任何计数 —— 照实计入
        self.assertEqual(
            d_plain["evaded_total"], d_marked["evaded_total"],
            "「回填」二字改变了规避总数 —— 说明有人实现了『回填不计入』。"
            "那等于把指标交回我手里(贴个标签就能摘掉一条规避),违反 R13")
        self.assertEqual(
            [r["evaded"] for r in d_plain["rounds"]],
            [r["evaded"] for r in d_marked["rounds"]],
            "分轮规避数也被备注影响了")

        # ② 回填数必须被报出(JSON + 人类可读两面)
        self.assertEqual(d_marked.get("backfilled_total"), 1,
                         "JSON 里没有 backfilled_total,或数不对 —— 补写这件事不可见")
        self.assertEqual(d_marked.get("backfilled_evaded"), 1,
                         "回填条目里有多少是『规避』也必须报出,否则无法判断补写规模")
        self.assertEqual(d_plain.get("backfilled_total"), 0,
                         "没有回填行时也必须报出 0,不能靠缺字段表示")
        # 人类可读面(`--json` 只吐 JSON,故这里必须用默认模式)
        rc_txt, out_txt = run_with(synth("**回填**。事后补写。"))
        self.assertIn("A10", out_txt, "回填计数没出现在人类可读输出里")
        self.assertRegex(out_txt, r"回填标注 = 1 条",
                         "人类可读面的回填计数不对")
        self.assertIn("照实计入", out_txt,
                      "输出必须写明本脚本**照实计入** —— 否则读的人会以为"
                      "铁律 1 的「不计入」已经生效")

    # ⚠ Round 68 红队 F5:**这里原本有一条 `test_A10b_backfill_exclusion_direction_is_guarded`,
    #   已删除。** 它自称「证明排除语义与照实计入可区分」,实测**对生产代码零鉴别力**:
    #   函数体内 `parse(` 出现 0 次、`backfilled` 出现 0 次 —— 它自己用列表推导造出
    #   「排除」输入,`rows_from()` 根本不写 `backfilled` 键(`.get()` 恒 None)。
    #   四个生产变异(标注→False / →True / 删 A10 行 / **真实现排除**)**它四次全绿**,
    #   而 `test_A10` 四次全红。它还会**误报**:把被标行改成「成立」,两种语义都算 9,
    #   `assertGreater` 直接失败。
    #   —— 按本仓原则「**零鉴别力判据 → 删掉**」。真正守住方向的是 `test_A10`(变异 P-20)。
    #   教训:判据自称什么不重要,**它能不能红**才重要;而「能不能红」必须用
    #   **对生产代码的变异**去测,不能靠读它的 docstring。

    def test_A11_backfill_is_cross_checked_against_objective_fact(self):
        r"""★ 红队 F6:A10 是**自报**,脚本无任何客观交叉校验 —— 「不贴标签」就能改善它。

        红队 F3 给出了客观信号:铁律 3 规定「本轮提出的条目,**最早在下一轮才能结算**」,
        故 `结算轮 == 提出轮` 是**可算的流程违规**,而且**完全不依赖我自己写的备注**。
        实测真台账:自报 81 条,客观同轮结算 **94** 条 —— **23 条未标**,而脚本对此**零输出**。

        本测试钉三件事:
          ① **客观数必须被报出**(脚本现在从不计算它);
          ② **「未标而客观违规」的差值必须被报出** —— 这是「靠不贴标签美化」的直接对策
             (R13:只允许让事实更清楚);
          ③ 自报数**不受影响**(与 A10 同:照实计入,不做任何排除)。
        """
        def synth(remark, settle_round):
            rows = []
            for rnd in (1, 2, 3):
                for i in (1, 2, 3):
                    # 基线 9 行的结算轮 = 提出轮 + 1 → **不**触发客观判据
                    rows.append(f"| {rnd} | 条目{rnd}-{i} | x | 规避 | 红队 | {rnd + 1} | |")
            rows.append(f"| 3 | 同轮结算的那条 | x | 规避 | 红队 | {settle_round} | {remark} |")
            return ("# 合成\n\n| 提出轮 | 条目 | 我声称什么 | 状态 | 检出方 | 结算轮 | 备注 |\n"
                    "|---|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n")

        # 场景 1:同轮结算 **且未标** → 客观判据命中,自报为 0 → 差值 1
        d1 = json.loads(run_with(synth("普通备注", 3), ("--json",))[1])
        self.assertEqual(d1.get("backfilled_struct_total"), 1,
                         "没有 backfilled_struct_total,或数不对 —— "
                         "「结算轮==提出轮」这个**客观**信号脚本根本没算")
        self.assertEqual(d1.get("backfill_unlabeled"), 1,
                         "未标而客观违规的条数没被报出 —— 那就等于"
                         "「不贴标签就能让 A10 好看」,正是红队 F6 说的自报型指标")
        self.assertEqual(d1.get("backfilled_total"), 0,
                         "自报数被客观判据影响了 —— 两者必须**分开**报,不能混成一个")

        # 场景 2:同轮结算 **且已标** → 客观 1、自报 1、差值 0
        d2 = json.loads(run_with(synth("**回填**。事后补写。", 3), ("--json",))[1])
        self.assertEqual((d2["backfilled_struct_total"], d2["backfilled_total"],
                          d2["backfill_unlabeled"]), (1, 1, 0),
                         "已标的情形下差值应为 0(差值只统计「该标没标」)")

        # 场景 3:不同轮结算 **且未标** → 客观 0、自报 0、差值 0(不得误报)
        d3 = json.loads(run_with(synth("普通备注", 4), ("--json",))[1])
        self.assertEqual((d3["backfilled_struct_total"], d3["backfill_unlabeled"]), (0, 0),
                         "结算轮 != 提出轮 的行被误算成客观回填 —— 假阳性会让人去改"
                         "本来合规的东西")

        # ④ 人类可读面必须把三者都写出来
        _rc, out = run_with(synth("普通备注", 3))
        self.assertIn("客观", out, "人类可读面没写客观数")
        self.assertIn("未标", out, "人类可读面没写「未标而客观违规」的差值 —— "
                                 "读的人就看不出我少贴了多少标签")

    def test_A11b_structural_signal_is_not_label_driven(self):
        r"""反向:把备注**全删**掉,客观数必须**一点不变** —— 否则它还是自报的。"""
        def synth(remark):
            rows = []
            for rnd in (1, 2, 3):
                for i in (1, 2, 3):
                    rows.append(f"| {rnd} | 条目{rnd}-{i} | x | 规避 | 红队 | {rnd + 1} | |")
            rows.append(f"| 3 | 同轮结算的那条 | x | 规避 | 红队 | 3 | {remark} |")
            return ("# 合成\n\n| 提出轮 | 条目 | 我声称什么 | 状态 | 检出方 | 结算轮 | 备注 |\n"
                    "|---|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n")

        a = json.loads(run_with(synth("**回填**。"), ("--json",))[1])
        b = json.loads(run_with(synth(""), ("--json",))[1])
        self.assertEqual(a["backfilled_struct_total"], b["backfilled_struct_total"],
                         "把备注从「回填」改成空,客观数就变了 —— 说明它其实是自报的")
        self.assertNotEqual(a["backfill_unlabeled"], b["backfill_unlabeled"],
                            "备注清空后差值必须上升(从 0 到 1)—— 若不上升,"
                            "说明「未标」这件事没被真正计算")

    def _independent_a11(self, text=None):
        """★ 从台账**独立重新解析**,算出 A11 的各数(自报 / 其中判为规避 / 客观 / 差值 / 不可解析)。

        红队 R70 的 F-B 说「A11 的数可被单方面改写,而**没有任何判据守着**」——
        `test_A1` 的独立重算只覆盖每轮 `(结算, 规避)`,**A11 一个数都没覆盖**。
        本 helper 就是那个缺的独立源。

        ★★★ Round 76(红队 R75 P2-R75-1):此前 `backfilled_evaded` **不在这里** ——
        它的「期望值」是 `test_A11e` 直接从**生产自己的 JSON** 里取的 ⇒ **自洽循环、恒等**。
        红队实测 N1b(`min(1, sum(...))` 按轮封顶):全套件 `exit=0 Ran 25` 全绿,
        而真台账人类面印「其中判为规避 **23** 条」、**真值 99**。**同源共变异直接骗过。**
        故它现在**在这里独立重算**,并进两张预注册常量。
        """
        if text is None:
            with open(REAL_LEDGER, encoding="utf-8") as fh:
                text = fh.read()
        label = evaded = struct = unlab = bad = 0
        in_table = False
        for line in text.splitlines():
            s = line.strip()
            if not s.startswith("|"):
                if in_table and label + struct + bad:
                    break
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not in_table:
                in_table = cells == ["提出轮", "条目", "我声称什么", "状态",
                                     "检出方", "结算轮", "备注"]
                continue
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if len(cells) != 7 or cells[3] not in ("成立", "规避"):
                continue                      # 只统计已结算
            try:
                n = int(cells[5])
                ok = n >= 1                      # F-1:`int()` 能过 ≠ 值合法
                same = ok and n == int(cells[0])
            except ValueError:
                same, ok = False, False
            if not ok:
                bad += 1
            if same:
                struct += 1
            if "回填" in cells[6]:
                label += 1
                if cells[3] == "规避":            # ★ P2-R75-1:独立重算,不再取自生产 JSON
                    evaded += 1
            if same and "回填" not in cells[6]:
                unlab += 1
        return {"backfilled_total": label, "backfilled_evaded": evaded,
                "backfilled_struct_total": struct,
                "backfill_unlabeled": unlab, "settle_unparseable_total": bad}

    # ★ Round 72(红队 R71 F-3):**恒 0 的量没有鉴别力**。
    #
    # 红队构造的生产变异 M-e(把 `settle_unparseable` 的口径收窄到只统计「规避」行)
    # 在**真台账**上:**四个数逐位相同、test_A11c 单独跑 OK、全套件全绿** ——
    # 而真值 1 被报成 0,**A11 的数确实错了**。
    # 根因:真台账 `settle_unparseable_total ≡ 0`,恒 0 的量无法为「缩小它」的变异
    # 提供任何鉴别力。
    #
    # 修法 = 让每个数都有一个**非 0** 的合成场景(红队建议)。本表刻意做成
    # 「四个数全非 0」,且**含一条「成立」行** —— 只统计「规避」的收窄会立刻露馅。
    SYNTHETIC_A11 = (
        "# 合成台账\n\n"
        "| 提出轮 | 条目 | 我声称什么 | 状态 | 检出方 | 结算轮 | 备注 |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 1 | a | x | 规避 | 红队 | 2 | |\n"          # 正常:非回填、非同轮
        "| 1 | b | x | 规避 | 红队 | 1 | 回填 |\n"       # 同轮 + 标了
        "| 2 | c | x | 规避 | 红队 | 2 | |\n"            # 同轮 + **未标**
        "| 2 | d | x | 成立 | 自查 | — | |\n"            # ★ **成立**行 + 不可解析
        "| 3 | e | x | 成立 | 自查 | 3 | 回填 |\n"       # ★ 成立行 + 同轮(但标了)
        "| 4 | f | x | 成立 | 自查 | 4 | |\n"            # ★★ 成立行 + 同轮 + **未标**
        # ★★ Round 77(红队 R76 P2-R76-2):此前矩阵里
        #   `backfilled_evaded × 收窄到可解析结算轮` **零鉴别力**(所有「回填」行恰好都可解析)。
        #   红队变异 X1(`be` 加 `and not i.get("settle_unparseable")`)→ **25/25 全绿**,
        #   而在**第四张台账**(含「回填 + 规避 + 结算轮 = —」的行)上 **be 报 0、真值 1**。
        #   ⇒ 补一行**回填 + 规避 + 非法结算轮**,那一格才第一次有鉴别力。
        "| 5 | g | x | 规避 | 红队 | — | 回填 |\n"
    )
    # ⚠ 最后一行 `f` 是**变异逼出来的**(M-e3):初版合成表里「同轮 + 未标」只有一条
    #   **规避**行,于是把 `backfill_unlabeled` 的口径收窄到「只统计规避」**结果不变**
    #   → 漏检。**每一类判定都必须在合成表里有它自己那一格**。
    #
    # ★★ Round 72 红队 P2-1(**严重**,R13 直接命中):补了这一格**仍然不够**。
    #   行 `f` 成了 `backfill_unlabeled` 在**整个套件里的唯一**鉴别力来源,
    #   于是「把行 `f` 的 `成立` 改成 `规避`」这一**行编辑**就能让
    #   「收窄到只统计规避」的变异**重新变成 no-op** → `exit=0 Ran 24 OK`,
    #   而生产代码**仍然是坏的**(拿它跑原表:unlab 报 1、真值 2)。
    #   **根因:「四个数全非 0」只防「某数归零」,不防「某数失去鉴别力」。**
    #   ⚠ 更糟:我的自检读的是 helper 算出的 `want` —— helper 与生产**同源**,
    #   同源共变异时**自检一起失效**,它不是独立的第二道锚。
    #
    #   故期望值改为**预注册常量**(R9:判据先写死再看数据),**不从 helper 现算**;
    #   并另加一条**鉴别力结构自检** —— 见 `_synthetic_discrimination()`。
    # ★ Round 77:补行 `g`(回填 + 规避 + 非法结算轮)后的五数。
    #   bt=3(b,e,g) · be=2(b,g) · bst=4(b,c,e,f) · bu=2(c,f) · su=2(d,g)
    SYNTHETIC_A11_EXPECTED = {"backfilled_total": 3, "backfilled_evaded": 2,
                              "backfilled_struct_total": 4,
                              "backfill_unlabeled": 2, "settle_unparseable_total": 2}

    # ★★★ Round 73(红队 R72 P2-3 的收口):R72 的鉴别力自检**也只测了一个变异类**
    #   (「收窄到只统计规避行」)。红队的话:**「只补一格 ≠ 堵住」** ——
    #   同一个病 R72 已经犯过一次(补行 `f` 造出新的单点依赖),不能再犯第二次。
    #
    #   故把「有鉴别力」推广成**预注册的变异类矩阵**:
    #   对**每个数 × 每个变异类**,要求「全量值 ≠ 该受限集合下的值」;
    #   然后把**实际成立的 (数, 类) 集合**与**预注册集合**比对 —— **完全相等**才算通过。
    #   ⚠ 为什么必须比集合,而不是只要求「至少一个类成立」:
    #     只要求「至少一个」的话,**删掉一行**只会让集合变小而仍然非空 → 照样绿。
    #     比集合才能让「少了一个可分辨的类」这件事**自己变成红的**。
    MUTANT_CLASSES = {
        "收窄到规避行": lambda r: r["status"] == "规避",
        "收窄到成立行": lambda r: r["status"] == "成立",
        "收窄到已标回填": lambda r: r["label"],
        "收窄到未标回填": lambda r: not r["label"],
        "收窄到同轮结算": lambda r: r["legal"] and r["n"] == r["proposed"],
        "收窄到可解析结算轮": lambda r: r["legal"],
    }
    # 预注册(R9):合成表当前**能**分辨哪些类。
    # 少一个 → 红(那一格没了,该变异类永远不会被发现 —— 正是 P2-1 的成因);
    # 多一个 → 也红(合成表变了而这份清单没同步 —— 同样是「改动没被看见」)。
    # ★ Round 77:补行 `g` 后重算。⚠ 红队 R76 的实测结论:**矩阵里出现「零鉴别力」的格
    #   本身不自动变红** —— 集合相等只保证「预注册的格一个不多一个不少」,
    #   不保证「每一格都有鉴别力」。补行的意义是**把那 30 格里的一个空格填上**;
    #   剩下的空格仍然只被**如实登记**。这是本表已知的边界,不粉饰。
    SYNTHETIC_A11_DISCRIMINATES = {
        "backfilled_total": {"收窄到规避行", "收窄到成立行", "收窄到未标回填",
                             "收窄到同轮结算", "收窄到可解析结算轮"},
        # ⚠ `backfilled_evaded` **天生**对「收窄到规避行」零鉴别力 —— 它的定义里
        #   已经含「状态 == 规避」,再收窄是恒等变换。
        #   ★ R77:补行 `g` 之后它终于对「收窄到可解析结算轮」有鉴别力(红队 X1 那条通道)。
        "backfilled_evaded": {"收窄到成立行", "收窄到未标回填",
                              "收窄到同轮结算", "收窄到可解析结算轮"},
        "backfilled_struct_total": {"收窄到规避行", "收窄到成立行",
                                    "收窄到已标回填", "收窄到未标回填"},
        "backfill_unlabeled": {"收窄到规避行", "收窄到成立行", "收窄到已标回填"},
        "settle_unparseable_total": {"收窄到规避行", "收窄到成立行", "收窄到已标回填",
                                     "收窄到未标回填", "收窄到同轮结算",
                                     "收窄到可解析结算轮"},
    }

    def _synthetic_discrimination(self):
        """★ 合成表的**鉴别力矩阵**自检(红队 P2-1 → R72 收口 → R73 推广)。

        一个数「有鉴别力」的确切含义:**把口径收窄到某个子集,它的值会变。**
        本 helper 用**自己的规则**解析 `SYNTHETIC_A11`(不调 `_independent_a11`,
        更不调生产代码),对**每个数 × 每个变异类**算出「全量值 / 受限值」,
        返回 `(全量表, 实际成立的 (数 → 类集合))`。
        """
        rows = []
        for line in self.SYNTHETIC_A11.splitlines():
            s = line.strip()
            if not s.startswith("|"):
                continue
            c = [x.strip() for x in s.strip("|").split("|")]
            if len(c) != 7 or c[3] not in ("成立", "规避"):
                continue
            try:
                n = int(c[5])
                ok = n >= 1
            except ValueError:
                n, ok = None, False
            rows.append({"proposed": int(c[0]), "status": c[3],
                         "n": n, "legal": ok, "label": "回填" in c[6]})

        def tally(rs):
            same = [r for r in rs if r["legal"] and r["n"] == r["proposed"]]
            return {
                "backfilled_total": sum(1 for r in rs if r["label"]),
                "backfilled_evaded": sum(1 for r in rs
                                         if r["label"] and r["status"] == "规避"),
                "backfilled_struct_total": len(same),
                "backfill_unlabeled": sum(1 for r in same if not r["label"]),
                "settle_unparseable_total": sum(1 for r in rs if not r["legal"]),
            }

        base = tally(rows)
        found = {}
        for k, v in base.items():
            for cname, filt in self.MUTANT_CLASSES.items():
                if tally([r for r in rows if filt(r)])[k] != v:
                    found.setdefault(k, set()).add(cname)
        return base, found

    def test_A11c_a11_numbers_are_independently_recomputed(self):
        r"""★ 红队 R70 F-B:`test_A1` 的独立重算**一个 A11 数都没覆盖**。
        ★★ 红队 R71 F-3:初版**对恒 0 的量零鉴别力**(真台账 `settle_unparseable ≡ 0`)
        —— M-e 变异(口径收窄到只统计「规避」)全套件绿而真值 1 被报成 0。
        ★★★ 红队 R72 P2-3:鉴别力自检**本身也只覆盖一个变异类** —— 同一个病。

        故本测试**三段**:
          ① 真台账:与**独立实现** `_independent_a11` 比对(可演进);
          ② 合成台账:与**预注册常量** `SYNTHETIC_A11_EXPECTED` 比对(R9,
             **不从 helper 现算** —— 否则同源共变异会把自检一起带走);
          ③ 合成表的**鉴别力矩阵**:实际能分辨的 (数, 类) 集合必须与
             **预注册集合完全相等**(少一个/多一个都红)。
        """
        # ① 真台账 —— 独立实现比对
        rc, out = run_with(None, ("--json",))
        self.assertIn(rc, VALID_EXITS, f"真台账: 退出码越界 {rc}:\n{out}")
        want = self._independent_a11()
        got = {k: json.loads(out).get(k) for k in want}
        self.assertEqual(got, want,
                         "真台账: A11 的四个数与独立重解析不符 —— 脚本算错了,或口径被改松了")

        # ② 合成台账 —— 预注册常量比对
        rc, out = run_with(self.SYNTHETIC_A11, ("--json",))
        self.assertIn(rc, VALID_EXITS, f"合成台账: 退出码越界 {rc}:\n{out}")
        got = {k: json.loads(out).get(k) for k in self.SYNTHETIC_A11_EXPECTED}
        self.assertEqual(got, self.SYNTHETIC_A11_EXPECTED,
                         "合成台账: 四个数与**预注册常量**不符。"
                         "⚠ 注意这条**不读 helper** —— 生产与 helper 同源共变异时,"
                         "只有常量能发现")

        # ③ 鉴别力矩阵(P2-1 + P2-3 的收口)
        base, found = self._synthetic_discrimination()
        for k in sorted(self.SYNTHETIC_A11_EXPECTED):
            with self.subTest(数=k):
                self.assertEqual(
                    base[k], self.SYNTHETIC_A11_EXPECTED[k],
                    f"`{k}` 的常量写错了:常量 {self.SYNTHETIC_A11_EXPECTED[k]},实算 {base[k]}")
                self.assertEqual(
                    found.get(k, set()), self.SYNTHETIC_A11_DISCRIMINATES[k],
                    f"`{k}` 的**鉴别力矩阵**与预注册不符。\n"
                    f"  实有   = {sorted(found.get(k, set()))}\n"
                    f"  预注册 = {sorted(self.SYNTHETIC_A11_DISCRIMINATES[k])}\n"
                    f"  **少一个** = 合成表里那一格没了 → 该变异类**永远不会被发现**"
                    f"(这正是红队 P2-1:一行编辑就能做到);\n"
                    f"  **多一个** = 合成表变了而这份清单没同步 —— 同样是「改动没被看见」。\n"
                    f"  ⚠ 别只要求「至少一个类成立」:删一行只会让集合变小而仍然非空 → 照样绿。")

    # ★★★ Round 74(红队 R73 P2-R73-1/-4/-5 的收口)。红队的共同根因原话:
    #   「**没有任何一道检查在「第三张台账」上对生产代码做端到端比对** ——
    #    凡在两台账上取值巧合一致的变异全部不可见。」
    #
    #   实测三条全绿的变异:
    #     · `sum(...)` → `len({i["结算轮"] for ...})`  **聚合去重**,值真的算错
    #     · `sum(...)` → `min(1, sum(...))`            **封顶**,值真的算错
    #     · `n < 1`   → `n < 1 or n > 9999`            **放宽**,把合法行报成非法
    #     · 人类面 `{report['backfill_unlabeled']}` → 字面量 `0`
    #   为什么前两个漏:① 真台账该数恒 0;② 合成表只有 **1** 条不可解析行,
    #   去重/封顶都不改值;③ **矩阵根本不运行生产代码**;④ `test_A11d` 每个子例也只有 1 条。
    #
    #   故本表**形状刻意不同**:两条不可解析行**取同一个值** `—`(去重会塌成 1)、
    #   一条 `结算轮 = 100000`(合法但极端,放宽会被抓)、并留出可断言的人类面数值。
    #   ⚠ 第一版我把两条不可解析行放在**不同轮**(提出轮 2 与 3)—— **聚合变异照样全绿**。
    #     根因:`build_report` 是**按轮**算完再求和的,每轮各 1 条,`len(set)` 每轮仍是 1,
    #     加总还是 2。**聚合变异只有在「同一轮内有重复值」时才露馅。**
    #     故本表刻意让**同一轮**里出现两条同值不可解析行 / 多条同轮行 / 两条同轮未标行。
    SYNTHETIC_A11_B = (
        "# 第三台账(形状不同)\n\n"
        "| 提出轮 | 条目 | 我声称什么 | 状态 | 检出方 | 结算轮 | 备注 |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 1 | a | x | 规避 | 红队 | 2 | |\n"          # 非同轮
        "| 2 | b | x | 规避 | 红队 | — | |\n"            # ★ 轮 2:不可解析 #1
        "| 2 | c | x | 成立 | 自查 | — | |\n"            # ★ 轮 2:**同轮**内不可解析 #2(同值)
        "| 4 | d | x | 规避 | 红队 | 4 | |\n"            # 同轮 + 未标
        "| 5 | e | x | 规避 | 红队 | 100000 | |\n"       # ★ 合法但极端
        "| 6 | f | x | 规避 | 红队 | 6 | 回填 |\n"       # 同轮 + 已标
        "| 7 | g | x | 规避 | 红队 | 7 | |\n"            # 同轮 + 未标
        "| 8 | h | x | 规避 | 红队 | 8 | |\n"            # ★ 轮 8:同轮 + 未标 #1
        "| 8 | i | x | 规避 | 红队 | 8 | 回填 |\n"       # ★ 轮 8:同轮 + 已标
        "| 8 | j | x | 规避 | 红队 | 8 | |\n"            # ★ 轮 8:同轮 + 未标 #2
    )
    # bt=2(f,i) · be=2(f,i,均规避) · bst=6(d,f,g,h,i,j) · bu=4(d,g,h,j) · su=2(b,c)
    SYNTHETIC_A11_B_EXPECTED = {"backfilled_total": 2, "backfilled_evaded": 2,
                                "backfilled_struct_total": 6,
                                "backfill_unlabeled": 4, "settle_unparseable_total": 2}

    # ★★★ Round 75(红队 R74 P2-R74-1 + P2-R74-5)。R74 我用的是
    #   `assertIn("未标而客观违规 4 条", human)` —— 红队实测这**形同虚设**:
    #     · M5:把人类面 `{report['backfilled_total']}` 改成字面量 `1` → **全绿**
    #           (我压根没钉 `backfilled_total` 与 `backfilled_evaded`)
    #     · M6:把人类面 `{report['backfill_unlabeled']}` 改成**与常量同值**的字面量 `4`
    #           → **全绿**(`assertIn` 只排除「字面量 ≠ 4」,不排除「4 不是算出来的」)
    #     · C2:只删掉 `"客观交叉校验 = "` 里一个空格 → **假红**(JSON 逐位不变)
    #   ⇒ 同一个 `assertIn` **既过严又过松**。
    #
    #   修法:改成**数值正则**(`\s*` 容忍空白),把人类面的数字**抽出来**,
    #   与**期望值**逐位比对 —— 而且**三张台账全钉**(真台账 + 两张合成表)。
    #   ⚠ 为什么必须三张都钉:M6 那种「字面量恰好等于某张表的常量」,
    #     只在**别的表**上才露馅(合成表 B 的 bu=4,而真台账 bu=23)。
    #   ★★★ Round 78(红队 R77 P2-R77-1,我复核确认):上面两条 `其中判为规避` 用的
    #     `\s*` **没有分隔符容忍位** —— `\s` 不匹配 `:`/`：`。于是
    #     `小结: 其中判为规避:99 条` 与 `…：99 条` 都**命中 1 处**(只有真那行),
    #     唯一性永远成立 ⇒ **两种写法全绿**。**我 R77 声称的 4/4 是假的**
    #     (其中两条其实是**崩溃**,见 `jev_mutlib.py` 的三分判据)。
    #     故所有 pattern 的分隔位一律写成 `[\s:=:]*`,并在归一化里剥掉零宽字符。
    _SEP = r"[\s:=\uFF1A\uFF1D]*"
    _HUMAN_PAT = {
        "backfilled_total": r"回填标注" + _SEP + r"(\d+)" + _SEP + r"条",
        "backfilled_evaded": r"其中判为规避" + _SEP + r"(\d+)" + _SEP + r"条",
        "backfilled_struct_total": r"客观交叉校验" + _SEP + r"(\d+)" + _SEP + r"条",
        "backfill_unlabeled": r"未标而客观违规" + _SEP + r"(\d+)" + _SEP + r"条",
        "settle_unparseable_total": r"不可解析或不合法" + _SEP + r"(\d+)" + _SEP + r"条",
    }

    @staticmethod
    def _normalize_human(text):
        """★★★ Round 77(红队 R76 P2-R76-1):**匹配之前**先把全角/不可见字符归一化。

        红队实测:生产加一行 `小结: 回填标注＝76 条`(**全角 U+FF1D**)或
        `小结: 其中判为规避:99 条`(全角冒号)→ **`exit=0 Ran=25` 全绿**,
        因为 ASCII 正则在那一行上**不匹配**,「恰好命中 1 处」于是永远成立 ——
        人类面同时印出 `＝76` 与 `= 105` 两个**互斥**的数而无人发现。
        **ASCII 版(N2)被抓住,全角版绕过。** ⇒ 归一化必须在匹配**之前**。
        ★★★ Round 78(红队 R77 P2-R77-2):**再剥零宽字符与不可见分隔**。

        ★★★ Round 79(红队 R78 P2-R78-1):红队实测「**24 种写法 13 种绕过**」,
        头号反例 **U+00AD SOFT HYPHEN** —— `小结: 其中判为规避\u00ad99 条`
        **`Ran 25 tests OK`**,而人类面同时印 `104` 与 `99`(肉眼无差)。
        ⇒ **枚举封不住**。改按 **Unicode 字符类别**剥:`Cf`(Format,含 U+00AD /
        U+200B–U+200D / U+2060 / U+FEFF / U+061C / U+180E / U+2066–U+2069 / U+FFF9–U+FFFB)
        与 `Mn`(组合附加符,如 U+0301)。**这是类别规则,不是清单。**
        ⚠ 仍封不住的(**如实登记**):繁体 `條`、汉字数字、罗马数字、词分隔 `共` ——
        它们是**语义不同的文本**,不是不可见字符;真正的修法是把 A10/A11 做成**机器行**。
        """
        text = "".join(c for c in text
                       if unicodedata.category(c) not in ("Cf", "Mn"))
        # ★★ Round 80(红队 R79 N8):`Cf`+`Mn` 仍漏 **6 种渲染为空白**的字符 ——
        #   U+20E3(Me 组合包围键帽)、U+115F/U+1160/U+3164/U+FFA0(Lo 韩文填充)、
        #   U+2800(So 盲文空白)。红队实测它们与 U+00AD **同等不可见**。
        #   ⚠ 空白类之所以被关住,靠的是 `_SEP` 里的 `\s`(Unicode 覆盖),**不是**类别剥离。
        #   这里按**码位**补剥这 6 个 —— 它们是**该剥而没剥**,
        #   与繁体 `條`/汉字数字/罗马数字/词分隔 `共`(**语义不同形,本就不该剥**)分开算。
        text = text.translate(dict.fromkeys(
            (0x20E3, 0x115F, 0x1160, 0x3164, 0xFFA0, 0x2800), None))
        return (text.replace("\uFF1D", "=").replace("\uFF1A", ":")
                    .replace("\uFE66", "=")
                    .replace("\u00a0", " ").replace("\u3000", " ")
                    .translate(str.maketrans("０１２３４５６７８９",
                                             "0123456789")))

    def _human_numbers(self, text):
        """把**人类面**打印的 A11 各数抽出来(红队 P2-R74-1 的收口)。

        ★★★ Round 76(红队 R75 P2-R75-2):此前用 `re.search` 取**首个**匹配 ——
        红队实测「加一行同措辞的输出」(如 `小结: 回填标注 = 76 条`)**全套件全绿**,
        因为首个匹配仍是正确那行。**措辞唯一性没人守。**
        故改用 `re.findall`,并要求**恰好命中 1 处** —— 多一处即红(语义有歧义),
        少一处也红(输出没了)。

        ★★★ Round 77(红队 R76 P2-R76-1):**先归一化再匹配** —— 否则全角 `＝` 绕过唯一性。

        抽不到 → `None`(缺失本身就是红的,不会被静默当成 0)。
        """
        text = self._normalize_human(text)
        out = {}
        for k, pat in self._HUMAN_PAT.items():
            hits = re.findall(pat, text)
            if len(hits) != 1:
                out[k] = f"<命中 {len(hits)} 处:{hits}>"
            else:
                out[k] = int(hits[0])
        return out

    def _assert_human_pins(self, label, ledger, expected):
        """人类面抽出的数必须与期望**逐位相等**(三张台账共用)。

        ⚠ 期望值**不得**来自生产 JSON(红队 R75 P2-R75-1:那是**自洽循环**)。
        """
        _rc, human = run_with(ledger)
        got = self._human_numbers(human)
        want = {k: expected[k] for k in self._HUMAN_PAT}
        self.assertEqual(
            got, want,
            f"{label}: **人类面**打印的数字与期望不符。\n"
            f"  人类面 = {got}\n  期望   = {want}\n"
            f"  ⚠ 这比 `assertIn('… 4 条')` 强:`assertIn` 会被**同值字面量**满足\n"
            f"     (红队 M6),也会被**删一个空格**弄假红(红队 C2)。\n"
            f"  ⚠ `<命中 N 处>` 表示同一措辞出现了多次 —— 语义有歧义,判据不敢选。")

    def test_A11e_a_differently_shaped_ledger_pins_production(self):
        r"""★★★ 红队 R73 的共同根因:**没有一道检查在「第三张台账」上对生产代码做端到端比对**。
        ★★★ 红队 R74 P2-R74-1/-5:R74 的人类面断言 `assertIn("… 4 条")` **既过严又过松**。

        三条全绿的变异(值都真的算错了):
          · `sum` → `len({结算轮})`   —— 两条 `—` 去重后塌成 1
          · `sum` → `min(1, sum)`     —— 封顶后永远是 1
          · `n < 1` → `n < 1 or n > 9999` —— 把 `100000` 报成非法

        本测试:① 第三台账对**生产代码**断言**绝对常量**(不读 helper);
        ② **人类面数值**用正则抽出,与期望**逐位比对**,且**三张台账全钉**。
        """
        rc, out = run_with(self.SYNTHETIC_A11_B, ("--json",))
        self.assertIn(rc, VALID_EXITS, f"第三台账: 退出码越界 {rc}:\n{out}")
        got = {k: json.loads(out).get(k) for k in self.SYNTHETIC_A11_B_EXPECTED}
        self.assertEqual(
            got, self.SYNTHETIC_A11_B_EXPECTED,
            "第三台账: 生产代码的四个数与**绝对常量**不符。\n"
            "  ⚠ 这张表是**形状不同**的:同轮两条同值不可解析行、一条 `100000`。\n"
            "  聚合类变异(`len(set)` / `min(1,·)`)与放宽类(`n > 9999`)**只有在这张表上**才露馅。")

        # ② 人类面数值 —— 三张台账全钉(红队 P2-R74-1 / P2-R74-5)
        for label, ledger, expected in (
            ("真台账", None, None),
            ("合成台账", self.SYNTHETIC_A11, self.SYNTHETIC_A11_EXPECTED),
            ("第三台账", self.SYNTHETIC_A11_B, self.SYNTHETIC_A11_B_EXPECTED),
        ):
            with self.subTest(台账=label):
                if expected is None:
                    # 真台账:五个数**全部**来自独立实现(红队 R75 P2-R75-1 前,
                    # `backfilled_evaded` 是从生产 JSON 取的 ⇒ 自洽循环)
                    exp = dict(self._independent_a11())
                    self._assert_human_pins(label, None, exp)
                else:
                    # 两张合成表:五个数**全部**来自预注册常量 —— 一个都不取自生产
                    self._assert_human_pins(label, ledger, dict(expected))


    def test_A11d_unparseable_settle_round_is_surfaced(self):
        r"""★ 红队 R69/R70 的 F-D:`结算轮` 不可解析的行**静默逃过**客观判据。

        红队实测:基线 9 行 + 第 10 行真·同轮结算 ——
          写 `3`         → 客观 1 / 未标 1
          写 `—`/空/`n/a` → 客观 **0** / 未标 **0**,exit 不变、**不报错**

        即:把 `结算轮` 填成任何非数字,客观信号就**归零**,而脚本对此零输出。
        真台账当前 0 例(潜伏),但这是**输入域缺守卫**,不是「不会发生」。
        修法:把不可解析的条数**单独报出来**,让它不能再静默。
        """
        def synth(settle):
            rows = [f"| {r} | e{r}-{i} | x | 规避 | 红队 | {r + 1} | |"
                    for r in (1, 2, 3) for i in (1, 2, 3)]
            rows.append(f"| 3 | 同轮结算的那条 | x | 规避 | 红队 | {settle} | |")
            return ("# 合成\n\n| 提出轮 | 条目 | 我声称什么 | 状态 | 检出方 | 结算轮 | 备注 |\n"
                    "|---|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n")

        d_ok = json.loads(run_with(synth("3"), ("--json",))[1])
        self.assertEqual(d_ok.get("settle_unparseable_total"), 0,
                         "正常的整数结算轮被误判成不可解析")

        for weird in ("—", "", "n/a", "?", "0", "-1"):
            with self.subTest(结算轮=weird):
                d = json.loads(run_with(synth(weird), ("--json",))[1])
                self.assertEqual(d.get("settle_unparseable_total"), 1,
                                 f"结算轮写 {weird!r} 时,该行**静默逃过**客观判据,"
                                 f"而脚本没把这件事报出来 —— 客观数归零却零告警")
                # 独立重算必须同意
                self.assertEqual(
                    self._independent_a11(synth(weird))["settle_unparseable_total"], 1,
                    "独立重解析与脚本对「不可解析/不合法」的认定不一致")

        # ⚠ 红队 R71 F-1:首版只堵「不可解析」,`int()` 能过就放行 —— 于是 `0` / `-1`
        #   成了**第二条完全静默的归零通道**(比 `—` 还好用,因为 `—` 现在会被报出来)。
        #   下面这条把它钉死。
        # ⚠ 断言必须锚在**那句话本身**上 —— 初版写 `assertIn("999999", ...)`,
        #   而变异把「为 0 **不等于**上方信号完整」整句删掉后,`999999` 仍出现在后半句,
        #   于是**漏检**(变异 P-44 实测)。这正是本仓记过的「子串口径双向失准」。
        self.assertIn("不等于", run_with(synth("999999"))[1],
                      "文案必须承认「为 0 ≠ 信号完整」—— "
                      "填一个能解析但错误的轮次号,本行**发现不了**")
        self.assertIn("自报字段", run_with(synth("999999"))[1],
                      "文案必须点明 `状态` 与 `结算轮` **都是自报字段** —— "
                      "否则读者会把「客观」当成真正独立于我的信号")

        # 人类可读面必须写出来
        _rc, human = run_with(synth("—"))
        self.assertIn("不可解析", human,
                      "人类面没写「结算轮不可解析」的条数 —— 读的人看不出客观数被归零了")

    def test_A12_ledger_drift_during_run_is_fatal(self):
        r"""★ 红队 F-A(**连续两轮**被判【严重】):审计**期间**台账被改动,脚本毫无察觉。

        R68 的 F1 是我跑变异改了工作区;R69 的 F-A 是**我的正常记账**改了台账 ——
        两次都让红队审到「**动靶**」,且**声称的数字事后不可复现**
        (它开工快照能逐字复现 `81/94/23`,收工同一命令却是 `84/97/23`)。

        根因**不是纪律,是机制**:脚本从不检查「我读的那个版本」和
        「我出判定时的那个版本」是不是同一份。纪律我已经违反两次了。

        本测试用 monkeypatch 驱动一次**确定的**漂移:`build_report` 被调用时改写台账。
        要求:必须 **exit 2**(格式错/不可判定),且原因里说清「审计期间被改动」——
        绝不能给出一个基于某个**中间状态**的判定。
        """
        v1 = ("# 合成\n\n| 提出轮 | 条目 | 我声称什么 | 状态 | 检出方 | 结算轮 | 备注 |\n"
              "|---|---|---|---|---|---|---|\n"
              + "\n".join(f"| {r} | e{r}-{i} | x | 成立 | 红队 | {r + 1} | |"
                          for r in (1, 2, 3) for i in (1, 2, 3)) + "\n")
        v2 = v1 + "\n<!-- 审计期间被追加的一行 -->\n"

        driver = (
            "import os, sys\n"
            "sys.path.insert(0, os.path.join(os.getcwd(), 'tools'))\n"
            "import evasion_audit as ea\n"
            f"V2 = {v2!r}\n"
            "LED = os.path.join(os.getcwd(), 'docs', 'evasion-ledger.md')\n"
            "_orig = ea.build_report\n"
            "def patched(rows):\n"
            "    with open(LED, 'w', encoding='utf-8') as fh:\n"
            "        fh.write(V2)\n"
            "    return _orig(rows)\n"
            "ea.build_report = patched\n"
            "sys.exit(ea.main())\n")

        tmp = tempfile.mkdtemp(prefix="jev_g5_drift_")
        try:
            os.makedirs(os.path.join(tmp, "tools"))
            os.makedirs(os.path.join(tmp, "docs"))
            shutil.copy2(SCRIPT, os.path.join(tmp, "tools", "evasion_audit.py"))
            with open(os.path.join(tmp, "docs", "evasion-ledger.md"),
                      "w", encoding="utf-8") as fh:
                fh.write(v1)
            with open(os.path.join(tmp, "drive.py"), "w", encoding="utf-8") as fh:
                fh.write(driver)
            r = subprocess.run([sys.executable, "-X", "utf8", "-B", "drive.py"],
                               cwd=tmp, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            out = (r.stdout or "") + (r.stderr or "")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertEqual(r.returncode, 2,
                         f"审计期间台账被改动却给了判定(exit={r.returncode}):\n{out}")
        self.assertIn("改动", out, "必须说清是「审计期间台账被改动」,不能只报个码")

    def test_A12b_digest_is_reported_so_a_verdict_is_reproducible(self):
        r"""★ 红队 F-A 的另一半:**判定必须能说清自己审的是哪个版本**。

        它开工快照与收工状态不同,于是「81/94/23」这个声称**事后无法复现** ——
        而输出里**没有任何东西**标识被审版本。
        """
        rc, out = run_with(None, ("--json",))
        data = json.loads(out)
        self.assertIn("ledger_sha256", data, "JSON 里没有被审台账的摘要 —— "
                                            "判定无法与某个具体版本对应")
        with open(REAL_LEDGER, "rb") as fh:
            import hashlib
            want = hashlib.sha256(fh.read()).hexdigest()
        self.assertEqual(data["ledger_sha256"], want,
                         "报出的摘要与实际台账不符 —— 那它就不能用来钉版本")

        # 红队 R70:摘要还必须印在**人类面** —— 此前 49 行输出里连 `sha` 三字母都没有,
        # 于是「审的是哪一版」只活在 JSON 里,读人类面的人看不到。
        _rc, human = run_with(None)
        self.assertIn("被审台账 sha256", human, "人类面没有印被审版本摘要")
        self.assertIn(want[:16], human, "人类面印的摘要与真实台账对不上")
        # ⚠ 措辞必须**收窄** —— 红队 R70 指出它挡不住跨运行改动。
        self.assertIn("不等于", human,
                      "人类面必须写明「窗口内未变 ≠ 判定可复现」,"
                      "否则读者会以为它钉住了版本")

    def test_A12d_drift_inside_parse_is_detected(self):
        r"""★ 红队 R70 反例 1 + 变异 M5(它实测**漏检**):漂移发生在 `parse()` **内部**。

        红队实测的形态:parse 期间把台账改成「全成立」、让它读到、返回前**立刻还原** ——
        `before` 与 `after` 两次**独立**读都读到原样,于是漂移不可见,
        而报告基于被改过的内容:`evaded_total = 0`(真值 104),
        **报出的 sha 却与磁盘 sha 一致** → 复算者按它重跑拿不到同一个数。
        **那正是 R69 判【严重】的同一形态。**

        修法:`parse()` 对**自己实际读到的那份字节**算摘要(`_PARSED`),
        `main()` 用它当 `before`,再与出判定前的磁盘摘要比。
        """
        v1 = ("# 合成\n\n| 提出轮 | 条目 | 我声称什么 | 状态 | 检出方 | 结算轮 | 备注 |\n"
              "|---|---|---|---|---|---|---|\n"
              + "\n".join(f"| {r} | e{r}-{i} | x | 规避 | 红队 | {r + 1} | |"
                          for r in (1, 2, 3) for i in (1, 2, 3)) + "\n")
        v2 = v1.replace("规避", "成立")

        driver = (
            "import os, sys\n"
            "sys.path.insert(0, os.path.join(os.getcwd(), 'tools'))\n"
            "import evasion_audit as ea\n"
            f"V2 = {v2!r}\n"
            "LED = os.path.join(os.getcwd(), 'docs', 'evasion-ledger.md')\n"
            "# 模拟「parse 期间读到被改过的内容,但磁盘随后被还原」:\n"
            "# 只让 parse 那次读拿到 V2,磁盘始终是 V1。\n"
            "_orig = ea._read_ledger_bytes\n"
            "calls = []\n"
            "def patched():\n"
            "    calls.append(1)\n"
            "    return V2.encode('utf-8') if len(calls) == 1 else _orig()\n"
            "ea._read_ledger_bytes = patched\n"
            "sys.exit(ea.main())\n")

        tmp = tempfile.mkdtemp(prefix="jev_g5_parse_")
        try:
            os.makedirs(os.path.join(tmp, "tools"))
            os.makedirs(os.path.join(tmp, "docs"))
            shutil.copy2(SCRIPT, os.path.join(tmp, "tools", "evasion_audit.py"))
            with open(os.path.join(tmp, "docs", "evasion-ledger.md"),
                      "w", encoding="utf-8") as fh:
                fh.write(v1)
            with open(os.path.join(tmp, "drive.py"), "w", encoding="utf-8") as fh:
                fh.write(driver)
            r = subprocess.run([sys.executable, "-X", "utf8", "-B", "drive.py"],
                               cwd=tmp, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            out = (r.stdout or "") + (r.stderr or "")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertEqual(r.returncode, 2,
                         f"parse() 内部漂移未被检出(exit={r.returncode})—— "
                         f"报告会基于被改过的内容,而报出的 sha 与磁盘一致:\n{out}")
        self.assertIn("改动", out, "必须说清是台账被改动")

    def test_A12c_error_path_still_carries_the_digest(self):
        r"""★ 红队 R70:`exit 2` 时 `ledger_sha256` 曾是 `null` —— 最该钉版本的时刻是空的。"""
        tmp = tempfile.mkdtemp(prefix="jev_g5_sha_")
        try:
            os.makedirs(os.path.join(tmp, "tools"))
            os.makedirs(os.path.join(tmp, "docs"))
            shutil.copy2(SCRIPT, os.path.join(tmp, "tools", "evasion_audit.py"))
            with open(os.path.join(tmp, "docs", "evasion-ledger.md"),
                      "w", encoding="utf-8") as fh:
                fh.write("没有表格\n")          # → A7 exit 2
            r = subprocess.run(
                [sys.executable, "-X", "utf8", "-B",
                 os.path.join(tmp, "tools", "evasion_audit.py"), "--json"],
                cwd=tmp, capture_output=True, text=True,
                encoding="utf-8", errors="replace")
            data = json.loads(r.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertEqual(r.returncode, 2, "台账无表格应 exit 2")
        self.assertIsNotNone(data.get("ledger_sha256"),
                             "exit 2 时摘要为 null —— 最该钉版本的时刻字段是空的")
        self.assertRegex(data["ledger_sha256"], r"^[0-9a-f]{64}$",
                         "错误路径的摘要必须是完整的 64 位十六进制")




    def test_A8c_error_paths_have_the_same_key_set(self):
        r"""★ 红队 R69 F2 反例:exit 2 的**第 4 条**子路径键集不同。

        我在 R68 声称「五种退出码 JSON 键集完全相同」,红队实测**不成立**:
        `check_rollback()` 自身出错时 `report["rollback_check_error"] = str(e)`
        → 该 JSON 是 **17 键**,而其余是 16。两个现实触发都实测复现:
        日志文件是目录(PermissionError)、日志含非法 UTF-8(UnicodeDecodeError)。

        本测试把这四条 exit 2 子路径全钉住 —— 上面 A8 只覆盖了其中一条。
        """
        def drive(mk):
            tmp = tempfile.mkdtemp(prefix="jev_g5_keys_")
            try:
                os.makedirs(os.path.join(tmp, "tools"))
                os.makedirs(os.path.join(tmp, "docs"))
                shutil.copy2(SCRIPT, os.path.join(tmp, "tools", "evasion_audit.py"))
                shutil.copy2(REAL_LEDGER,
                             os.path.join(tmp, "docs", "evasion-ledger.md"))
                mk(tmp)
                r = subprocess.run(
                    [sys.executable, "-X", "utf8", "-B",
                     os.path.join(tmp, "tools", "evasion_audit.py"), "--json"],
                    cwd=tmp, capture_output=True, text=True,
                    encoding="utf-8", errors="replace")
                return r.returncode, (r.stdout or "") + (r.stderr or "")
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        def _nothing(_t):
            pass

        def _log_is_dir(t):
            os.makedirs(os.path.join(t, "docs", "evasion-audit.log"))

        def _bad_utf8(t):
            with open(os.path.join(t, "docs", "evasion-audit.log"), "wb") as fh:
                fh.write(b"\xff\xfe not utf8 \x80\n")

        def _no_ledger(t):
            os.remove(os.path.join(t, "docs", "evasion-ledger.md"))

        ref = None
        for label, mk in [("正常", _nothing), ("日志是目录", _log_is_dir),
                          ("日志非法 UTF-8", _bad_utf8), ("台账缺失", _no_ledger)]:
            with self.subTest(路径=label):
                rc, out = drive(mk)
                self.assertIn(rc, VALID_EXITS, f"{label}: 退出码 {rc} 越界")
                ks = frozenset(json.loads(out))
                if ref is None:
                    ref = ks
                self.assertEqual(ks, ref,
                                 f"{label}: 键集与正常路径不同 —— 对称差 {sorted(ks ^ ref)}。"
                                 f"「恒存在」这句话在**每一条**子路径上都得成立,"
                                 f"不是抽查一条就算数")

    def test_ZZ_manifest_every_expected_case_still_exists(self):
        r"""★★ 防我**第三次**犯同一个错:`edit` 锚点选在 `def test_...` 行上,
        替换后忘了把 `def` 行加回来 → 那个用例**变成前一个用例里的死代码**,
        `Ran N tests OK` 是**假绿**。

        R70 吃掉 `test_A12c`(20 应为 21);R71 吃掉
        `test_A12_ledger_drift_during_run_is_fatal`(22 应为 23)。
        **两次的唯一线索都是「测试数没涨」,两次我都没看。**

        判据必须写进文件:`EXPECTED_TESTS` 是**手写准入清单**,
        实际收集到的用例名必须与它**完全相等**(少一个 = 被误删;多一个 = 忘了登记)。
        ⚠ 本判据的边界(如实登记):它只认**名字**。改名字会同时报「少一个 + 多一个」✓,
        但**把断言的函数体改坏**它看不出来 —— 那不是它的职责,是其余 23 个用例的。
        """
        loader = unittest.TestLoader()
        actual = {t.id().rsplit(".", 1)[-1]
                  for t in loader.loadTestsFromTestCase(type(self))}
        actual.discard("test_ZZ_manifest_every_expected_case_still_exists")
        missing = sorted(EXPECTED_TESTS - actual)
        extra = sorted(actual - EXPECTED_TESTS)
        self.assertEqual(
            (missing, extra), ([], []),
            f"用例清单对不上 —— 缺 {missing}(多半是 `def` 行被误删,"
            f"断言已变成别的用例里的**死代码**,而 `Ran N OK` 会是假绿);"
            f"多 {extra}(新增了用例但没登记进 `EXPECTED_TESTS`)")


if __name__ == "__main__":
    unittest.main(verbosity=2)