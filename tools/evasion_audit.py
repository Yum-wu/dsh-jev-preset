# -*- coding: utf-8 -*-
r"""
G5 规避率审计 —— 从 `docs/evasion-ledger.md` 计算,**不接收任何人工传入的数字**。

判据(预注册,R9;写在实现之前):

  A1 只统计**已结算**条目(`成立` / `规避`);`待结算` 单独列出。
     未结算 ≠ 通过 —— 把未结算算成通过是最容易的假绿。
  A2 规避率按**提出轮**归组。这是唯一能让分子分母同轮的口径:
     Round 20 提的条目若在 Round 22 才被判规避,它在 Round 20 的分母里、
     在 Round 22 的分子里会重复计算 —— 故一律归到**提出轮**。
  A3 一律报 **Wilson 95% 区间**(R10),禁用 Wald。
  A4 G5 抬头判定需要 **≥3 个有结算条目的轮次**(R1);不足时报 `样本不足`,不报「抬头」。
     轮次按「有结算条目的提出轮」计数,空轮不算。
  A5 另报**自查检出率** = 自查发现的规避数 / 规避总数。
     历史事实:Round 1–9 为 0/8。检出率必须与规避率分开看 ——
     检出率上升可能只说明红队变强,不代表我变差。
  A6 脚本必须能被证伪:解析失败、列数不对、状态值越界 → **报错退出,不许静默跳过**。

用法:
    python tools/evasion_audit.py            # 打印报告
    python tools/evasion_audit.py --json     # 机器可读
退出码:
    0 = 正常;1 = G5 抬头(规避率上升且样本足);2 = 台账格式错或文件缺失
"""
import hashlib
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "docs", "evasion-ledger.md")
# append-only 审计日志(2026-10-01 Round 28 新增)
#
# 为什么需要它:红队 93306bae 实测 T1(删掉一整条「规避」行)、T9/T10(把「规避」改判
# 「待结算」)、T14(全部改判「待结算」)—— **三种篡改都 7/7 全绿,exit 0,判定不变**。
# 根因是:台账是**可改的单向状态**,没有任何东西记录它「本该是什么样」。
#
# append-only 日志是本仓内唯一能做到这件事的机制:**每次运行追加一行**
# (时间戳 | 台账 sha256 | 条目数 | 结算数 | 规避数 | 判定 | exit),
# 于是「已结算条目数不得下降」成为可检出的约束 —— 上轮记 12 条、这轮只有 10 条,
# 说明有人把两条挪走了,无论他把状态改成什么。
#
# ⚠ 它**不是**防篡改的:能改台账的人同样能改这个日志文件。
#   真正的信任根必须在仓外(例如 git 提交历史、或另一台机器写入)。
#   本文件只能把「单点篡改」与「系统性重写」区分开,不能杜绝后者 —— 如实标注,不假装。
AUDIT_LOG = os.path.join(ROOT, "docs", "evasion-audit.log")
EXIT_ROLLBACK = 4          # 检测到回退嫌疑(已结算条目数下降)

HEADER = ["提出轮", "条目", "我声称什么", "状态", "检出方", "结算轮", "备注"]
VALID_STATUS = {"待结算", "成立", "规避"}
VALID_FINDER = {"—", "自查", "红队", "测试"}


def wilson(k, n, z=1.96):
    """Wilson 95% 区间 —— Wald 在 k/n→0 或 1 时会越出 [0,1],禁用(R10)。"""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, c - m), min(1.0, c + m))


def _fail(msg):
    """A6:任何格式问题都必须 **exit 2** 并把原因写出来。

    ⚠ 这里踩过一个坑:`raise SystemExit(msg)` 的退出码是 **1**,
    而 1 在本脚本的约定里是「G5 抬头」。即格式错会被误读成「审计判定抬头」——
    两种完全不同的结论共用一个码,正是 A2/退出码契约要防的事。

    ⚠ Round 32 修红队 ed8225da 的一条:init 在 `--json` 模式下 **exit 2 不产出任何 JSON**
      (stdout 为空,原因只在 stderr),于是 schema 表达不了「台账格式错」这个状态 ——
      机器消费者拿到 exit=2 却无结构化信息可解析。
      现在 `--json` 模式改为往 **stdout** 输出一份 schema 相同的错误报告,
      保证五种结论在 JSON 里都有对应表示。
    """
    if "--json" in sys.argv:
        print(json.dumps({
            "rounds": [], "scored": 0, "thin_rounds": [],
            "evaded_total": 0, "self_found_total": 0, "self_rate": 0.0,
            "verdict": msg.strip().splitlines()[0] if msg.strip() else "台账格式错",
            "exit_code": EXIT_MALFORMED, "sufficient": False,
            "error": msg.strip(), "rollback_suspect": False,
            "_ok": False,
        }, ensure_ascii=False))
    else:
        sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(EXIT_MALFORMED)


def _clean(cell):
    """去掉 Markdown 强调标记再比对 —— 表格里写 `**自查**` 是正常排版,
    A6 不该因为排版报错(但也不该因此放宽对**取值**的校验)。"""
    return cell.strip().strip("*").strip()


def parse():
    """解析台账表格。宁可报错,也不静默少算(A6)。

    ⚠ A7(红队 1812cf7e 实证的**致命**绕过):初版在遇到「第一张有数据的表」后就
    `break`,于是在文首插一张 3 行全「成立」的假表,真实台账一字未改,
    报告却变成「样本不足,不判定抬头」exit 0。
    故现在必须**恰好一张**数据表,多一张少一张都 exit 2。
    """
    if not os.path.exists(LEDGER):
        _fail(f"[A6] 台账文件不存在: {LEDGER}")
    tables, current, seen_header, saw_data_table = [], None, False, False
    with open(LEDGER, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            s = line.strip()
            if not s.startswith("|"):
                if current:
                    tables.append(current)
                    current = None
                # ⚠ 离开表格时必须连 seen_header 一起重置。否则文档正文里的**说明表格**
                #   (如开头那张两列的「缺陷/后果」表)会被当成数据行,报「列数 2 != 7」。
                if seen_header:
                    saw_data_table = True
                seen_header = False
                continue
            cells = [_clean(c) for c in s.strip("|").split("|")]
            if cells == HEADER:
                if current:
                    tables.append(current)
                current, seen_header = [], True
                continue
            if not seen_header:
                # ⚠ Round 30 修红队实测的 T9:初版对「以 | 开头但不在数据表里」的行
                #   静默 continue,与 A6「宁可报错也不静默少算」矛盾 —— 在表末追加几行
                #   无表头的表样式行,它们被丢掉而 exit 与基线完全相同。
                #   但**文档正文里的说明表是合法的**(本文件开头那张两列表就是),
                #   故只在「数据表已经出现过」之后的无表头表行才判错。
                if saw_data_table:
                    _fail(f"[A6] {LEDGER}:{lineno} 数据表之后出现无表头的表样式行 —— "
                          f"它会被静默丢弃,或可让人伪造条目。首格={cells[0]!r}")
                continue
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if len(cells) != len(HEADER):
                _fail(f"[A6] {LEDGER}:{lineno} 列数 {len(cells)} != {len(HEADER)}")
            rec = dict(zip(HEADER, cells))
            try:
                rec["round"] = int(rec["提出轮"])
            except ValueError:
                _fail(f"[A6] {LEDGER}:{lineno} 提出轮不是整数: {rec['提出轮']!r}")
            if rec["状态"] not in VALID_STATUS:
                _fail(f"[A6] {LEDGER}:{lineno} 状态越界: {rec['状态']!r}")
            if rec["检出方"] not in VALID_FINDER:
                _fail(f"[A6] {LEDGER}:{lineno} 检出方越界: {rec['检出方']!r}")
            if rec["状态"] == "规避" and rec["检出方"] == "—":
                _fail(
                    f"[A6] {LEDGER}:{lineno} 判为规避却没记检出方 —— "
                    f"规避必须可追溯到谁发现的,否则就是自说自话")
            current.append(rec)
    if current:
        tables.append(current)

    if len(tables) != 1:
        _fail(f"[A7] 台账里必须恰好有 1 张条目表,实际 {len(tables)} 张。\n"
              f"     多张表意味着可以放一张全「成立」的假表在前面、让真实数据整段消失。\n"
              f"     若确需多张,先说明理由并改本脚本的判据,不要靠加表绕过。")
    rows = tables[0]
    if not rows:
        _fail(f"[A6] 台账的表里没有解析到任何条目(表头是否被改坏?): {LEDGER}")
    return rows


def main():
    rows = parse()
    report = build_report(rows)

    # 单调性检查必须在写日志**之前**做 —— 拿「上一条」比,不是拿自己比自己
    rollback = check_rollback(report)
    if rollback:
        report["verdict"] = rollback
        report["_ok"] = False
        report["exit_code"] = EXIT_ROLLBACK
        report["rollback_suspect"] = True

    # ⚠⚠ 检测到回退时**绝不追加日志**(Round 30 修红队实测的 T7):
    #   初版无条件追加,于是「回退那一跑」会把**篡改后的数字**固化成新基线 ——
    #   再跑一次,报警自己消失,而日志一个字都没被改。
    #   即 T7 不需要碰日志就能让报警失效。现在:回退时不写基线,
    #   下一次运行仍与**回退前**的那条比,报警持续存在直到有人解释清楚。
    do_log = not rollback

    if "--json" in sys.argv:
        # 机器可读模式:**只输出 JSON**,不带人类可读表格 ——
        # 混在一起会让消费方必须做子串匹配,那是脆弱接口。
        print(json.dumps(report, ensure_ascii=False))
        if do_log:
            append_log(report, report["exit_code"])
        return report["exit_code"]

    if rollback:
        print("!" * 72)
        print(rollback)
        print("!" * 72)
    print("=" * 72)
    print("G5 规避率审计(数据源: docs/evasion-ledger.md)")
    print("=" * 72)
    print(f"{'轮次':<6}{'提出':>4}{'结算':>5}{'规避':>5}{'规避率':>9}  Wilson 95%        自查检出  计分")
    for r in report["rounds"]:
        rate = "     n/a" if r["rate"] is None else f"{r['rate']*100:6.1f}%"
        w = f"[{r['wilson95'][0]*100:.1f}%, {r['wilson95'][1]*100:.1f}%]"
        mark = "  Y" if r["scorable"] else ("  -" if r["settled"] else "  .")
        print(f"{r['round']:<6}{r['claimed']:>4}{r['settled']:>5}{r['evaded']:>5}"
              f"{rate:>9}  {w:<18}{r['self_found']}/{r['evaded']}{mark}")
        if r["pending"]:
            print(f"       待结算(A1 不计入): {r['pending']}")
    if report["thin_rounds"]:
        print(f"       未计分(结算条目 < {MIN_ITEMS_PER_ROUND}): {report['thin_rounds']}")

    print("-" * 72)
    print(f"样本量门: 参与比较的轮次 = {report['scored']} 个"
          f"(每轮需结算条目 >= {MIN_ITEMS_PER_ROUND}, 且至少 {MIN_ROUNDS_FOR_VERDICT} 轮)")
    print(f"G5 判定: {report['verdict']}")
    print(f"A5 自查检出率 = {report['self_found_total']}/{report['evaded_total']}"
          f"({report['self_rate']*100:.1f}%)" if report["evaded_total"] else "A5 自查检出率 = n/a")
    # ⚠ 绝对不能用 U+26A0 之类符号:默认 Windows 控制台是 GBK,
    #   print 会抛 UnicodeEncodeError -> 未捕获异常 -> 退出码 1,
    #   而 1 在本脚本约定里是「G5 抬头」—— 正常审计被误读成抬头告警。
    #   (红队 1812cf7e 实测:加了这个符号后 exit=1,正是它自己 _fail() 注释里骂过的撞车。)
    print("  注意: 检出率与规避率是两个量: 检出率上升可能只说明红队手段升级, 不代表本轮变差。")
    if not report["sufficient"]:
        print("  警告: 样本量不足, 本结论**统计不充分**, 任何抬头/未抬头都不构成证据, 需人工判断。")
    else:
        ns = [r["settled"] for r in report["rounds"] if r["scorable"]]
        print(f"  警告: 样本量已过门(每轮 >= {MIN_ITEMS_PER_ROUND} 条), 但每轮 n 仍是"
              f" {min(ns)}-{max(ns)}, Wilson 区间宽达数十个百分点 —— "
              f"**本判定仍属粗筛, 不构成统计证据**, 需人工判断。")
    # 红队 1812cf7e 的 Q5 结论,直接印在工具输出里,任何只看到输出的人都会读到:
    print("  警告: 本链只统计「已被记入台账」的规避, 台账由被审计者单方面维护 ——")
    print("        它测不出真实规避率, 只测得出「我承认自己糊弄了多少」(红队 1812cf7e 实测)。")
    if do_log:
        append_log(report, report["exit_code"])
    return report["exit_code"]


# 样本量门(2026-10-01 Round 26,用户裁定「加样本量门 + 标注统计不充分」新增)
#
# 为什么必须有门:实测每轮结算条目 n = 1–4,且多落在极端点(4/4、3/3、0/1、2/2)。
# n=4 时 Wilson 95% 区间是 [43.9%, 100%] —— 宽到不含任何信息量。
# 要让两个比率之差超过 R1 的噪声阈(<10pp),单轮需要 n ≈ 400,现有样本量差两个数量级。
# 所以 G5 在现有规模下**本质上无法做统计判断**,它只能是粗筛。
#
# ⚠⚠ 阈值为什么是 3 而不是 8(R13:不得把指标调成「不会报警」):
#   我第一版把门设成 8 条/轮,而实测每轮只有 1–3 条 —— 结果 0 轮参与计分,
#   **G5 从此永不触发**,机制被我自己的「加门」动作静音了。
#   那正是 R13 禁止的「优化让指标好看」:数字不再报警,看起来更配合。
#   阈值必须取**当前可达**的下限(3 条/轮),并接受「即使达标也统计不充分」这一事实。
#   换句话说:**门只决定这句话有没有信息量,不决定要不要说;永远要说。**
MIN_ITEMS_PER_ROUND = 3
MIN_ROUNDS_FOR_VERDICT = 3

# 绝对水平阈值:最新计分轮的规避率达到该值且不低于历史中位数即报警(见 build_report 注释)。
HIGH_RATE = 0.5

# 退出码契约(四值)。⚠ 「样本不足」必须是**非零**,否则它与「未抬头」同码,
#   而这两种结论要求相反的动作(前者要补数据/多跑几轮,后者才可以继续)。
#   (红队 93306bae 实测:初版 exit=0 同时表示「未抬头」「样本不足」「100% 全规避」三种。)
EXIT_OK = 0             # 未抬头,可以继续
EXIT_RISING = 1         # 抬头或高位持续,应停止循环
EXIT_MALFORMED = 2      # 台账格式错
EXIT_INSUFFICIENT = 3   # 样本不足,判定不可用(需补条目/多跑几轮)


def ledger_digest():
    with open(LEDGER, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def read_last_log():
    r"""读审计日志里的**历史最高基线**(按已结算条目数取 max);没有则返回 None。

    ⚠⚠⚠ Round 34 修红队 22cc7297 的实测漏洞:**初版的 `return None` 是
    「关掉全部回退检测」的开关**。它对两种输入都返回 None:
      (a) 末行以 `#` 开头的注释     —— Round 30 只堵了这一条
      (b) 末行「非注释且格式不对」  —— 在日志末尾加**一行纯文本**即可,
          `len(parts) < 7` 或 ValueError 都会 return None。
    而返回 None 还会让 `do_log=True` → **篡改后的数字被写进日志成为新基线**,
    于是 T7「报警自己消失」的修法在这条路径上完全失效(根本没触发回退)。

    两处修法(红队已实跑验证):
      1. 坏行 **continue 跳过**,而不是整体放弃;
      2. 基线取**全部历史行的 max(settled)**,而不是「最后一行」——
         否则追加一条格式合法但数字为零的基线行即可把约束清零(红队实测绕C)。

    ⚠ 仍无法防的:**清空整个日志**。仓内无解,需要仓外锚(git commit 后的
    `git show HEAD:...`)。已在输出里如实标注,不在此假装能防。
    """
    if not os.path.exists(AUDIT_LOG):
        return None
    best = None
    for line in open(AUDIT_LOG, encoding="utf-8").read().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split("|")
        if len(parts) < 7:
            continue                      # ← 原 return None:全局静默开关
        try:
            rec = {"ts": parts[0].strip(), "digest": parts[1].strip(),
                   "claimed": int(parts[2]), "settled": int(parts[3]),
                   "evaded": int(parts[4]), "verdict": parts[5].strip(),
                   "exit": int(parts[6].strip())}
        except ValueError:
            continue                      # ← 同上
        # 历史最高基线(不是最后一行):追加一条格式合法但数字为零的基线行
        # 无法把约束清零(红队 22cc7297 实测的绕C)
        if best is None or rec["settled"] > best["settled"]:
            best = rec
    return best


def append_log(report, code):
    os.makedirs(os.path.dirname(AUDIT_LOG), exist_ok=True)
    if not os.path.exists(AUDIT_LOG):
        with open(AUDIT_LOG, "w", encoding="utf-8") as fh:
            fh.write("# JEV G5 审计日志(append-only,勿手改)\n"
                     "# 格式: 时间戳 | 台账sha256 | 条目数 | 已结算 | 规避 | 判定 | exit\n"
                     "# 这不是防篡改设施: 能改台账的人也能改本文件。真正的信任根在仓外。\n")
    claimed = sum(r["claimed"] for r in report["rounds"])
    settled = sum(r["settled"] for r in report["rounds"])
    evaded = sum(r["evaded"] for r in report["rounds"])
    verdict = report["verdict"].replace("\n", " ")[:60]
    with open(AUDIT_LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {ledger_digest()} | "
                 f"{claimed} | {settled} | {evaded} | {verdict} | {code}\n")


def check_rollback(report):
    """单调性检查:已结算条目数 / 规避数不得低于上一条日志记录。"""
    last = read_last_log()
    if last is None:
        return None
    settled = sum(r["settled"] for r in report["rounds"])
    evaded = sum(r["evaded"] for r in report["rounds"])
    problems = []
    if settled < last["settled"]:
        problems.append(f"已结算条目数 {last['settled']} -> {settled}(少了 {last['settled']-settled} 条)")
    if evaded < last["evaded"]:
        problems.append(f"规避数 {last['evaded']} -> {evaded}(少了 {last['evaded']-evaded} 条)")
    if not problems:
        return None
    return ("★ 回退嫌疑:" + ";".join(problems) +
            f"。上一条日志 {last['ts']} 台账 sha256={last['digest']},当前={ledger_digest()}。"
            f"若确实删了条目请说明理由;若未删,说明日志与台账不同步。")


def build_report(rows):
    by_round = {}
    for r in rows:
        by_round.setdefault(r["round"], []).append(r)

    report = []
    for rnd in sorted(by_round):
        items = by_round[rnd]
        settled = [i for i in items if i["状态"] in ("成立", "规避")]
        pending = [i["条目"] for i in items if i["状态"] == "待结算"]
        ev = [i for i in settled if i["状态"] == "规避"]
        lo, hi = wilson(len(ev), len(settled))
        report.append({
            "round": rnd,
            "claimed": len(items),
            "settled": len(settled),
            "pending": pending,
            "evaded": len(ev),
            "rate": round(len(ev) / len(settled), 4) if settled else None,
            "wilson95": [round(lo, 4), round(hi, 4)],
            "self_found": sum(1 for i in ev if i["检出方"] == "自查"),
            # 样本量门(Round 26):n 不足的轮次不参与比率比较
            "scorable": len(settled) >= MIN_ITEMS_PER_ROUND,
        })
    # `rollback_suspect` 必须**恒存在**(Round 32 修红队 ed8225da 的一条):
    #   初版只在回退时才加这个键,消费方必须写 `.get(..., False)` 才能读 ——
    #   schema 在不同运行间不一致,正是「同码不同义」的近亲。
    for r in report:
        r["rollback_suspect"] = False

    scored = [r for r in report if r["scorable"]]
    total_ev = sum(r["evaded"] for r in scored)
    total_self = sum(r["self_found"] for r in scored)
    thin = [r["round"] for r in report if r["settled"] and not r["scorable"]]

    if len(scored) < MIN_ROUNDS_FOR_VERDICT:
        verdict = (f"样本不足: 参与比较的轮次 {len(scored)} < {MIN_ROUNDS_FOR_VERDICT}"
                   f"(每轮需结算条目 ≥ {MIN_ITEMS_PER_ROUND}) —— 不判定抬头")
        # ⚠ Round 32 修红队 ed8225da 的一条:初版这里 `_ok=True`,语义是「可以继续」,
        #   而 exit=3 要求调用方「补数据/多跑几轮」—— **同一个字段两种意思**,
        #   消费方读 `_ok` 会采取与 exit 3 **完全相反**的动作。
        #   现在 `_ok` 改为**三态**:True=未抬头可继续 / False=应停止 /
        #   None=判定不可用(样本不足)。None 是 JSON 里的 null,与 True/False 都不同。
        ok, code = None, EXIT_INSUFFICIENT
    else:
        # ⚠⚠ 判据必须能覆盖「**最坏状态恰是唯一静默状态**」这种情形。
        #   初版只判「相对抬头」(`b > a`):当全台账规避率都是 100% 时,`1.0 > 1.0`
        #   恒为假 —— **规避最严重的那个状态反而永远不报警**。
        #   红队 93306bae 实测:当前真实台账 10/10 全规避,脚本输出「规避率未抬头」exit=0。
        #   这正是「验证剧场」的最坏形态:工具在最坏情况下说「没事」。
        #   故增加**绝对水平**判据。
        #
        # ⚠⚠⚠ Round 31 再修红队实测的 **T8 纯追加稀释**:
        #   判据只看「最新轮 vs 历史中位数」时,只要在表内**注入** 3 条伪造「成立」行,
        #   scored 就从 2 变 3 越过门限,最新轮 rate=0%,
        #   于是 exit 3「样本不足」-> exit 0「规避率未抬头 = **可以继续**」,
        #   而台账原有条目**一字未删**。窗口内那两轮 100% 对结论毫无影响。
        #   现改为:**窗口内出现过的最高规避率** >= HIGH_RATE 即报警。
        #   这是刻意选择「宁可多报」—— G5 的作用是触发**人工审查**,不是精确统计;
        #   历史上糊弄率高,即便本轮改善,也值得复盘一次。
        latest = scored[-1]
        window = scored[-MIN_ROUNDS_FOR_VERDICT:]      # 原始 G5 的「上 5 轮」
        first_in_window = window[0]
        worst = max(window, key=lambda r: r["rate"])

        if worst["rate"] >= HIGH_RATE:
            verdict = (f"★ 窗口内出现高位规避(最高 Round {worst['round']} "
                       f"{worst['rate']*100:.1f}% >= 阈值 {HIGH_RATE*100:.0f}%),"
                       f"按 G5 应停止循环并复盘 —— 最新轮 {latest['round']} 为 "
                       f"{latest['rate']*100:.1f}%,"
                       f"**不得据最新一轮变好就认为可以继续**")
            ok, code = False, EXIT_RISING
        elif latest["rate"] > first_in_window["rate"]:
            verdict = (f"★ 规避率较上 {len(window)} 轮抬头"
                       f"({first_in_window['rate']*100:.1f}% -> {latest['rate']*100:.1f}%)"
                       f",按 G5 应停止循环")
            ok, code = False, EXIT_RISING
        else:
            verdict = (f"规避率未抬头(窗口首轮 {first_in_window['rate']*100:.1f}% -> "
                       f"最新 {latest['rate']*100:.1f}%;最新轮 {latest['round']};"
                       f"窗口最高 {worst['rate']*100:.1f}%)")
            ok, code = True, EXIT_OK
    return {
        "rounds": report,
        "scored": len(scored),
        "thin_rounds": thin,
        "evaded_total": total_ev,
        "self_found_total": total_self,
        "self_rate": (total_self / total_ev) if total_ev else 0.0,
        "verdict": verdict,
        "exit_code": code,
        "sufficient": len(scored) >= MIN_ROUNDS_FOR_VERDICT,
        # 顶层也要恒有该键(每轮内的同名字段是给「哪一轮可疑」用的)
        "rollback_suspect": False,
        "_ok": ok,
    }


if __name__ == "__main__":
    sys.exit(main())
