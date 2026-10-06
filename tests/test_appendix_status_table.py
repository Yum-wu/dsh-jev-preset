# -*- coding: utf-8 -*-
r"""附录状态表(`docs/appendix-status.md`)的结构与词汇守卫。

## 为什么单列一条(Round 51,附录 C 家族 · 闭环缺口)

`docs/appendix-status.md` 是本目标**停止条件 S1** 的唯一权威来源 ——
S1 要求「附录 A/B/C 全部条目状态明确」。**但这份文件此前没有任何判据守卫。**

Round 50 已因此吃过一次:盘点时发现 **C6 行缺状态列**(标题顶掉了状态格),
任何按状态列解析这张表的人或脚本,读到 C6 的「状态」是一句**描述**。
**含糊的格子给出权威的错觉。**

本轮又查出更根子的一层:文件在 L6 写着

    **「未处理」不是合法状态** —— 未处理即视为欠账,不得沉默。

**这句话没有任何东西在执行。** 同时 L8–L12 的「状态取值」图例只声明了 **4** 个值,
而表里实际用了 **7** 个(部分已修 / 部分修 / 半修 / 不修 / 未修 / 已修 / 已确认无能力),
其中「部分」这一个含义有**三种拼法**(`部分已修`、`部分修`、`半修`)。

后果与 Round 50 同构:**按图例判定合法性的人会误判**,而误判方向是
「以为某条不合规」或「以为某条已闭环」—— 两种都会污染 S1 的结论。

## 判据
1. **条目齐全**:A1–A10、B1–B6、C1–C6 每条都必须在表里出现(恰好一次)。
2. **状态格存在**:每行必须能解析出非空状态格(防 Round 50 的 C6 事故)。
3. **状态词汇闭合**:每行的**状态基名**(去掉括号/加号/间隔号后的部分)
   必须在文件自己声明的图例里(A3)。
4. **「未处理」类状态被禁**:空 / 未处理 / 待办 / TBD / TODO / ? 一律报红(A4)。
5. **可证伪**(A5):在镜像里插一行非法状态,A3/A4 必须红 —— 否则本条在自欺。
6. **块内有序**(A6):同字母块内条目号必须递增 —— 防「新增条目插在中间」。
8. **引用存在**(A8):「判据 / 证据」列引用的文件与行号必须真实存在。
7. **判定段不陈旧**(A7):「S1 判定」段自报的 Round ≥ 主表最大 Round ——
   防「改了表没改自报行」—— 顶部更新行与 S1 判定段**两处都要查**,
   只查一处另一处就会腐烂(Round 51 实测:顶部 Round 48、判定段 Round 45,主表已到 50)。
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "appendix-status.md")

# 附录条目全集(S1 的口径)
ITEMS = ([f"A{i}" for i in range(1, 11)]
         + [f"B{i}" for i in range(1, 7)]
         + [f"C{i}" for i in range(1, 58)])  # C6–C57 是本仓自优化过程自查出的,不在原附录内
# ⚠ C8 在 Round 54 加进表里却没加进 ITEMS —— A1 只查 missing 不查 extra,漏了它。
#    Round 58 补上并把上界推到 C9;Round 61 推到 C13(C12/C13 由 R61 红队报出);
#    Round 62 推到 C14(R62 红队报出的「输出伪造」边界);Round 63 推到 C15
#    (R63 自查:全仓 Python 源编译 SyntaxWarning,已躺 29 轮);Round 64 推到 C16
#    (R64 自查:元判据只防删不防改名,R63 只修了 1 个文件);Round 65 推到 C17
#    (R65 自查:反空转守卫的数量下界证明不了覆盖面);Round 66 推到 C18
#    (R66 自查:junction 逃逸在 3 个扫描器里只修了 1 个);Round 67 推到 C19
#    (R67 AST 普查:同一个洞在**第五个**遍历器上复发 —— `.md` 扫描器与审计脚本,
#     且「有没有剪枝」此前**没有任何判据守着**)。
#    ⚠ **Round 82 又漏了 C27–C31**(R78–R82 五轮),而且是**两侧同时缺失** —— A1 全绿。
#    Round 83 补上并把上界推到 C31,同时加 `test_A13` **从 `docs/self-optimize-rounds.md` 反推**:
#    该文档引用的 C 编号(≥6)必须都在表里。**「靠记性堵不住,只能靠机制」第七次实例。**

# 「未处理」类:文件明说不是合法状态
BANNED = ("", "未处理", "待办", "待处理", "TBD", "TODO", "?", "—", "-")

# 本文件的用例数 —— 硬编码,防「静默丢用例」(见 A11)
#: 本文件的用例**具名清单**(不是计数)。⚠ 名字而非数字 —— 数字抓不住「改名」。
CASE_NAMES = (
    "test_A1_every_item_appears_exactly_once",
    "test_A2_every_row_has_the_same_column_count_as_the_header",
    "test_A3_status_vocabulary_is_closed",
    "test_A4_banned_status_values_are_absent",
    "test_A5_guard_is_falsifiable",
    "test_A6_items_are_in_ascending_order_within_a_letter",
    "test_A7_s1_verdict_is_not_stale",
    "test_A8_guard_is_falsifiable",
    "test_A8_referenced_artifacts_exist",
    "test_A9_no_dead_legend_entries",
    "test_A10_header_date_is_plausible",
    "test_A11_guard_itself_is_not_stale",
    "test_A12_items_named_in_the_verdict_section_exist_in_the_table",
    "test_A13_c_numbers_cited_in_the_rounds_doc_are_in_the_table",
)

# 状态基名:砍掉括号补充、加号附加、间隔号附加、冒号后续
def _base_status(cell: str) -> str:
    s = cell.strip().strip("*").strip()
    for sep in ("(", "（", "+", "·", ":", "："):
        s = s.split(sep)[0]
    return s.strip().strip("*").strip()


def _read_rows():
    """返回 [(行号, 条目号, 状态格原文)]。

    行 = 以 `|` 开头的一段(允许单元格跨行:续行不以 `|` 开头)。
    单元格数按**整段**统计,不看首行 —— Round 50 的扫描器就是只看首行才误判了 C6。
    """
    with io.open(DOC, encoding="utf-8") as f:
        lines = f.read().splitlines()
    # 切块(空行分隔)→ 块内按行首 `|` 切行
    blocks, cur, st = [], [], None
    for i, l in enumerate(lines, 1):
        if l.strip() == "":
            if cur:
                blocks.append((st, cur))
            cur, st = [], None
        else:
            if not cur:
                st = i
            cur.append(l)
    if cur:
        blocks.append((st, cur))

    out = []
    for bst, blk in blocks:
        cur, st = None, None
        rows = []
        for k, l in enumerate(blk):
            if l.startswith("|"):
                if cur is not None:
                    rows.append((st, cur))
                cur, st = [l], bst + k
            elif cur is not None:
                cur.append(l)
        if cur is not None:
            rows.append((st, cur))
        for st, rl in rows:
            seg = "\n".join(rl)
            if set(rl[0]) <= set("|-: "):
                continue                      # 分隔行
            if rl[0].startswith("| #"):
                continue                      # 表头
            cells = [c.strip() for c in seg.split("|")]
            if len(cells) < 4:
                out.append((st, None, None))
                continue
            item = re.search(r"\*\*([ABC]\d+)\*\*", cells[1])
            out.append((st, item.group(1) if item else None, cells[2]))
    return out


def _legend_values():
    """从「状态取值:」那段解析出图例声明的状态基名。"""
    with io.open(DOC, encoding="utf-8") as f:
        lines = f.read().splitlines()
    vals, on = [], False
    for l in lines:
        if l.startswith("状态取值"):
            on = True
            continue
        if on:
            if l.startswith("- "):
                m = re.match(r"- \*\*(.+?)\*\*", l.strip())
                if m:
                    vals.append(_base_status(m.group(1)))
            elif l.strip() == "":
                break
    return vals


def _row_cell_counts():
    """返回 [(行号, 条目号, 实际格数, 表头格数)] —— 只列不一致的。"""
    with io.open(DOC, encoding="utf-8") as f:
        lines = f.read().splitlines()
    hdr = next((l for l in lines if l.startswith("| # |")), None)
    if hdr is None:
        return [("?", "?", -1, -1)]
    want = len(hdr.strip().strip("|").split("|"))
    bad = []
    for i, l in enumerate(lines, 1):
        if not re.match(r"\| \*\*[ABC]\d+\*\*", l):
            continue
        got = len(l.strip().strip("|").split("|"))
        if got != want:
            item = re.search(r"\*\*([ABC]\d+)\*\*", l)
            bad.append((f"L{i}", item.group(1) if item else "?", got, want))
    return bad


class TestAppendixStatusTable(unittest.TestCase):

    def test_A1_every_item_appears_exactly_once(self):
        r"""A1–A10 / B1–B6 / C1–C6 每条必须在表里出现,且只出现一次。"""
        rows = _read_rows()
        seen = {}
        for ln, item, _ in rows:
            if item:
                seen.setdefault(item, []).append(ln)
        missing = [i for i in ITEMS if i not in seen]
        dup = {k: v for k, v in seen.items() if len(v) > 1}
        self.assertEqual(missing, [], f"这些条目在附录状态表里找不到:{missing}")
        # ⚠ **extra 方向**(Round 83 补,红队 R83 P2-R83-J):旧版只查 missing ⇒
        #   「表里有、`ITEMS` 没有」**零信号**。Round 82 就是这么漏掉 C27–C31 的 ——
        #   那 5 条**两侧同时缺失**,missing 与 extra 都看不见。
        extra = sorted(set(seen) - set(ITEMS))
        self.assertEqual(
            extra, [],
            f"附录状态表里有这些**不在 `ITEMS` 里**的条目:{extra}\n"
            f"—— `ITEMS` 的上界是手写的,新条目加进表而没加进 `ITEMS` 时,\n"
            f"旧版 A1 只查 missing ⇒ **两侧同时缺失零信号**。这个方向补上另一半。")
        self.assertEqual(dup, {}, f"这些条目出现了不止一次:{dup}")

    def test_A2_every_row_has_the_same_column_count_as_the_header(self):
        r"""每行的单元格数必须等于表头。

        ⚠ **本条被红队判过一次「空转」,已重写。** 旧版只断言「状态格非空」,
        红队实测:把状态格**整格删掉**、只留 2 格时,旧 A2 是**绿的** ——
        因为 `cells[2]` 变成了证据文本(非空),旧 A2 就放过了。
        真正抓到那次事故的是 A3(偶然)。**判据名不副实。**

        现在改判**结构量**:单元格数 == 表头列数。这条与「状态格写的是什么」无关,
        因此不会因为内容恰好合法而放过 —— 而列数错**正是** Round 50 的 C6 事故形态。

        实测(本轮):这条判据是在**当前文件里就有违规**的情况下写出来的 ——
        Round 52 我给 C4 行写了一句 `` `sha256(seed|case_id)` ``,
        那个**未转义的竖线**把这一行撑成了 4 格。表格渲染错位,
        而当时 A1–A8 **全部全绿**。红队 `f015df27` / `b6baf473` 独立报出。
        """
        bad = _row_cell_counts()
        self.assertEqual(
            bad, [],
            f"这些行的单元格数与表头不一致:{bad}\n"
            f"—— 单元格数错会让整张表渲染错位,读的人看到的状态列可能是别的东西。\n"
            f"**注意**:markdown 表格里,单元格正文中的裸 `|` 会撑破表格,\n"
            f"要写成 `&#124;`(本仓台账已在用这个写法)。")

    def test_A3_status_vocabulary_is_closed(self):
        r"""**核心判据**:每行的状态基名必须在文件自己声明的图例里。

        Round 51 写这条时它是**红的**(图例 4 个值 vs 表里 7 个,「部分」有 3 种拼法)。
        现在它是**绿的** —— 图例已扩为闭集、拼法已统一。

        ⚠ **但「绿」有两种含义,别读混**(红队 `f015df27` 提醒):
          - 「**有东西在守,当前恰好合规**」 ← 这是想要的;
          - 「**恰好一致,没有东西在守**」   ← 这是危险的。
        本条的**方向是单向的**(只查 `used ⊆ declared`),所以
        `declared - used` 非空(图例里有值表内零使用)它**看不见** ——
        那条由 **A10** 守。同理,括号里写什么它也不管(自由文本不可测,见 §不修)。

        ⚠ 本 docstring 曾写「本条现在必须是红的」而实测为绿 —— **陈述跟着代码腐烂**,
        红队 `b6baf473` 报出。已改为描述当前状态。
        """
        declared = set(_legend_values())
        self.assertTrue(declared, "图例没解析出任何状态值 —— 判据前提不成立")
        used = {}
        for ln, item, st in _read_rows():
            if st is None:
                continue
            used.setdefault(_base_status(st), []).append(f"L{ln}:{item or '?'}")
        undeclared = {k: v for k, v in used.items() if k not in declared}
        self.assertEqual(
            undeclared, {},
            f"这些状态值不在文件自己声明的图例里:{undeclared}\n"
            f"图例声明的是:{sorted(declared)}\n"
            f"实际用到的是:{sorted(used)}\n"
            f"—— 图例是 S1 的判据来源,它和实际用法不一致,"
            f"按图例判定合法性的人会误判。")

    def test_A4_banned_status_values_are_absent(self):
        r"""文件写着「『未处理』不是合法状态」—— 本条把那句话变成可执行断言。"""
        hits = []
        for ln, item, st in _read_rows():
            if st is None:
                continue
            # ⚠ 必须切**原始格**,不能切 `_base_status(st)` ——
            # `_base_status` 在**第一个**分隔符处就把后面全丢了,
            # 于是 `已修 + 未处理` 的返回值就是 `已修`,再切一次什么也切不出来。
            # **我自己第一版就是这么写的,实测空转**(证伪脚本:A4 漏检)。
            # 教训:`_base_status` 是「取基名」用的,拿它当「拆分段」用必然漏。
            raw = st.strip().strip("*").strip()
            for seg in re.split(r"[+·、,，;；]", raw):
                if seg.strip().strip("*").strip() in BANNED:
                    hits.append(f"L{ln}:{item or '?'} 状态={st!r} 命中段={seg!r}")
                    break
        self.assertEqual(
            hits, [],
            f"这些行用了被明令禁止的状态值(「未处理」类):{hits}\n"
            f"文件 L6 写着「未处理即视为欠账,不得沉默」—— 禁止就得有判据。")

    def test_A5_guard_is_falsifiable(self):
        r"""R9 可证伪:往镜像里插一行非法状态,A3/A4 必须报红。

        否则本文件测的是「当前恰好没违规」,而不是「有东西在守规则」。
        """
        mirror = os.path.join(tempfile.gettempdir(), f"jev_r53_appendix_mirror_{os.getpid()}")
        if os.path.exists(mirror):
            shutil.rmtree(mirror, ignore_errors=True)
        shutil.copytree(ROOT, mirror,
                        ignore=shutil.ignore_patterns(".git", "node_modules",
                                                      "tmp_jev_path1"))
        p = os.path.join(mirror, "docs", "appendix-status.md")
        with io.open(p, encoding="utf-8") as f:
            src = f.read()
        injected = src.replace(
            "| **C5**",
            "| **Z9** 注入的假条目 | **未处理** | 无 |\n| **C5**", 1)
        self.assertNotEqual(injected, src, "注入点没找到 —— 本条自曝")
        with io.open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(injected)
        env = os.environ.copy()
        env.pop("PYTHONIOENCODING", None)
        env.pop("PYTHONUTF8", None)
        r = subprocess.run(
            [sys.executable, "-B", "-X", "utf8",
             "tests/test_appendix_status_table.py", "-k", "A3"],
            cwd=mirror, capture_output=True, env=env)
        out = ((r.stdout or b"") + (r.stderr or b"")).decode("utf-8", "replace")
        shutil.rmtree(mirror, ignore_errors=True)
        self.assertIn("Ran ", out, f"子进程没跑到框架:{out[-400:]}")
        self.assertNotEqual(
            r.returncode, 0,
            "往附录插一行非法状态后 A3 仍然全绿 —— A3 没有在守词汇闭合")


    def test_A6_items_are_in_ascending_order_within_a_letter(self):
        r"""同一字母块内,条目号必须递增。

        为什么值得一条判据:`docs/appendix-status.md` 是 S1 的权威来源,
        而 S1 要求「全部条目状态明确」。**人按顺序读、脚本按顺序扫** ——
        如果 C 块写成 `C1, C2, C3, C6, C4, C5`,读的人扫到 C6 就以为 C 块到头了。

        这不是排版洁癖:C6 是后来新增的,被插在当时的 C 块末尾;
        之后 C4/C5 补进来时落在了它下面 —— **新增条目插在中间,是这类表最常见的腐烂方式**。
        """
        rows = _read_rows()
        by_letter = {}
        for ln, item, _ in rows:
            if item:
                by_letter.setdefault(item[0], []).append((ln, item))
        bad = []
        for letter, seq in by_letter.items():
            nums = [int(i[1:]) for _, i in seq]
            if nums != sorted(nums):
                bad.append((letter, [f"L{ln}:{i}" for ln, i in seq]))
        self.assertEqual(
            bad, [],
            f"这些字母块内条目号不是递增的:{bad}\n"
            f"新增条目请追加到**该块末尾**,不要插在中间。")


    def test_A7_s1_verdict_is_not_stale(self):
        r"""S1 判定段不得比主表陈旧。

        同一个文件里,**两处都在陈述条目状态**:上面的表,和下面的「S1 判定」段。
        两处不一致时,**读的人会拿到互相矛盾的答案**,而且无从判断哪个新。

        实测(本轮):主表已经写到 **Round 50**(C6 行),
        而「S1 判定」段还挂着 **「(Round 45 更新)」**,并且里面说
        「C5 的 **②** 半未修」—— 而表里 C5 的 ② 早已修掉,未修的是 **④**。
        **同一份文件对同一条给出两个不同的欠账原因。**

        判据:S1 判定段自报的 Round 号,必须 **≥** 主表中出现过的最大 Round 号。
        粗糙但有效 —— 它抓的是「改了表没改判定段」这个动作本身。
        """
        with io.open(DOC, encoding="utf-8") as f:
            text = f.read()
        with io.open(DOC, encoding="utf-8") as f:
            lines = f.read().splitlines()

        # 主表里出现过的最大 Round
        rounds = [int(m) for m in re.findall(r"Round\s+(\d+)", text)]
        self.assertTrue(rounds, "全文找不到任何 Round 号 —— 判据前提不成立")
        max_round = max(rounds)

        # 两处「自报的 Round」都要查 —— 同一类陈旧在本文件里有**两个**落脚点:
        #   ① 顶部的「**更新:…(Round NN)**」行;
        #   ② 「## S1 判定:**…**(Round NN 更新)」段头。
        # 只查其中一处,另一处就会悄悄腐烂(Round 51 实测:顶部写 Round 48、
        # 判定段写 Round 45,而主表已到 Round 50 —— **两处都比表旧**)。
        targets = []
        for l in lines:
            if l.startswith("## S1 判定"):
                targets.append(("S1 判定段", l))
                break
        else:
            self.fail("找不到「S1 判定」段 —— 判据前提不成立")
        for l in lines:
            if l.startswith("**更新:"):
                targets.append(("顶部更新行", l))
                break
        else:
            self.fail("找不到顶部的「**更新:…」行 —— 判据前提不成立")

        for label, line in targets:
            m = re.search(r"Round\s+(\d+)", line)
            self.assertIsNotNone(
                m, f"{label}没写它更新于哪个 Round:{line!r}\n"
                   f"没有这个号,就无法判断它是否已经陈旧。")
            declared = int(m.group(1))
            self.assertGreaterEqual(
                declared, max_round,
                f"{label}自称更新于 Round {declared},"
                f"但主表里已经出现了 Round {max_round}。\n"
                f"—— 改了表没改这里,同一份文件对同一条给出不同答案。\n"
                f"请同步更新(含自报的 Round 号)。")


    def test_A8_referenced_artifacts_exist(self):
        r"""「判据 / 证据」列里引用的**文件与行号必须真实存在**。

        为什么值得一条判据:这张表的**全部说服力**来自「判据 / 证据」列 ——
        它说「有判据兜着」,读者据此相信某条已闭环。
        **如果引用指向一个不存在的文件/测试,那张表就是一份无法复算的承诺。**

        本仓历史上发生过「引用不跟着代码更新」(README/persona 都踩过),
        而附录此前没有任何东西在查它。

        实测(本轮):36 个路径样 token 里 30 个存在,6 个是 glob/标识(非路径,跳过);
        4 处 `cordis.patch.yml:142/149/297/307` 行号**逐行核对全部正确**;
        `extract.py` 存在。**当前全绿** —— 故本条的可证伪性单独证明(见 A5 同款做法):
        在镜像里把一处引用改成一个不存在的文件名,本条必须红。
        """
        import re as _re
        with io.open(DOC, encoding="utf-8") as f:
            text = f.read()
        missing = []
        for m in _re.finditer(r"`([^`\n]+)`", text):
            tok = m.group(1).strip()
            if not _re.search(r"\.(py|mjs|ps1|json|md|jsonl)$", tok):
                continue                       # 只看真文件引用,跳过标识/行号/glob
            if "*" in tok or tok.startswith("["):
                continue
            path = _re.split(r"::|\s", tok)[0]
            # ⚠ **不再做目录回退**。旧版会依次试 tests/ tools/ benchmarks/...,
            # 于是 `test_evasion_audit.py::A8`(仓库根下不存在,实际在 tests/)被
            # 「碰巧找到」而放过 —— 红队 `f015df27` 实测:把它**改成正确路径**仍绿,
            # 把正确引用**改成 basename** 也仍绿,**修正前后无判别力**。
            # 引用必须按**仓库根**解析,因为文档是给人按仓库根读的。
            if not os.path.exists(os.path.join(ROOT, path)):
                missing.append(tok)
        self.assertEqual(
            missing, [],
            f"附录引用了这些不存在的文件:{missing}\n"
            f"—— 引用不跟着代码更新,这张表就变成无法复算的承诺。")

        # 行号引用:`<file>:<n>` 形式,逐行核对在界内
        bad_lines = []
        for m in _re.finditer(r"`([A-Za-z0-9_./-]+\.(?:yml|yaml|py|md)):((?:\d+/)*\d+)`",
                              text):
            rel, nums = m.group(1), m.group(2)
            p = os.path.join(ROOT, rel)
            if not os.path.exists(p):
                bad_lines.append(f"{rel} 不存在")
                continue
            with io.open(p, encoding="utf-8", errors="replace") as f:
                n = len(f.read().splitlines())
            for num in nums.split("/"):
                if int(num) > n:
                    bad_lines.append(f"{rel}:{num} 超出文件总行数 {n}")
        self.assertEqual(
            bad_lines, [],
            f"附录里的行号引用越界:{bad_lines}\n"
            f"—— 行号是最容易腐烂的引用形式,必须机械核对。")

    def test_A8_guard_is_falsifiable(self):
        r"""A8 的可证伪:镜像里插一个不存在的引用,A8 必须红。"""
        mirror = os.path.join(tempfile.gettempdir(), f"jev_r53_ref_mirror_{os.getpid()}")
        if os.path.exists(mirror):
            shutil.rmtree(mirror, ignore_errors=True)
        shutil.copytree(ROOT, mirror,
                        ignore=shutil.ignore_patterns(".git", "node_modules",
                                                      "tmp_jev_path1"))
        p = os.path.join(mirror, "docs", "appendix-status.md")
        with io.open(p, encoding="utf-8") as f:
            src = f.read()
        injected = src.replace(
            "| **C5**",
            "| **Z8** 注入的假引用 | **已修** | `tests/test_this_does_not_exist.py` |\n| **C5**", 1)
        self.assertNotEqual(injected, src, "注入点没找到 —— 本条自曝")
        with io.open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(injected)
        env = os.environ.copy()
        env.pop("PYTHONIOENCODING", None)
        env.pop("PYTHONUTF8", None)
        r = subprocess.run(
            [sys.executable, "-B", "-X", "utf8",
             "tests/test_appendix_status_table.py", "-k",
             "test_A8_referenced_artifacts_exist"],
            cwd=mirror, capture_output=True, env=env)
        out = ((r.stdout or b"") + (r.stderr or b"")).decode("utf-8", "replace")
        shutil.rmtree(mirror, ignore_errors=True)
        self.assertIn("Ran ", out, f"子进程没跑到框架:{out[-400:]}")
        self.assertNotEqual(
            r.returncode, 0,
            "插入一个不存在的引用后 A8 仍然全绿 —— A8 没有在查引用存在性")


    def test_A9_no_dead_legend_entries(self):
        r"""**图例里声明的每个值,表里都必须真的用到** —— 反向闭集。

        为什么需要这条:A3 只查 `used ⊆ declared`(单向)。
        一个**没人用的图例值**是「死图例」:它让图例看起来比实际更丰富,
        而且——更要紧的是——**它掩盖了「某条从某个状态消失了」这件事**。

        ⚠ 这条是本轮**真实缺陷**逼出来的,而且是我自己上一轮引入的:
        Round 52 我把 C4 从「未修(排期)」改成「已修(Round 52)」,
        而 `未修` 是当时**唯一**在用它的条目 —— 于是 `未修` 变成了死图例。
        A1–A8 **全部全绿**,没有任何东西发现它。红队 `f015df27` / `b6baf473` 独立报出。
        """
        declared = set(_legend_values())
        self.assertTrue(declared, "图例没解析出任何状态值 —— 判据前提不成立")
        used = set()
        for _, _, st in _read_rows():
            if st:
                used.add(_base_status(st))
        dead = sorted(declared - used)
        if not dead:
            return

        # ⚠ **不要**把死图例直接判成错误,也**不要**直接把图例删掉 ——
        # 图例是**许可清单**(闭集),不是**使用普查**:一个合法状态
        # 此刻恰好没人用,是**允许**的(`未修(排期)` 正是给下一轮的欠账留的出口,
        # 删了它,下一轮想用「未修」反而会撞 A3)。
        #
        # 真正的问题是**沉默**:没人用的图例值会悄悄腐烂成装饰。
        # 所以要求它被**显式标注**,而不是被删掉。
        with io.open(DOC, encoding="utf-8") as f:
            lines = f.read().splitlines()
        unmarked = []
        for v in dead:
            hit = next((l for l in lines
                        if l.startswith("- **") and _base_status(
                            re.match(r"- \*\*(.+?)\*\*", l).group(1)) == v), None)
            if hit is None or "当前无条目使用" not in hit:
                unmarked.append(v)
        self.assertEqual(
            unmarked, [],
            f"图例里声明了但表内零使用、且**没有标注**的状态值:{unmarked}\n"
            f"—— 图例是许可清单(闭集),允许有此刻没人用的值;\n"
            f"但**必须显式写出来**,否则它会悄悄腐烂成装饰。\n"
            f"在该图例行末尾加一句「(**当前无条目使用** —— 词汇仍合法,保留以便下一轮使用)」。")

    def test_A10_header_date_is_plausible(self):
        r"""顶部「更新:<日期>」必须是合法日期,且不早于本仓有记录的时间。

        红队 `f015df27` 实测:把顶部日期改成 `1999-01-01` → **A1–A8 全绿**。
        A7 只查 Round 号,**日期无人守**。

        为什么日期不是排版细节:这张表的**全部作用**是「某条此刻处于什么状态」,
        而一个陈旧日期会让读者把**旧状态当成新状态** —— 与 A7 防的是同一类错误,
        只是落点不同(A7 在 Round 号,本条在日期)。
        """
        with io.open(DOC, encoding="utf-8") as f:
            lines = f.read().splitlines()
        head = next((l for l in lines if l.startswith("**更新:")), None)
        self.assertIsNotNone(head, "找不到顶部「**更新:」行 —— 判据前提不成立")
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", head)
        self.assertIsNotNone(m, f"顶部更新行里没有 ISO 日期:{head!r}")
        y, mo, d = (int(x) for x in m.groups())
        import datetime
        try:
            when = datetime.date(y, mo, d)
        except ValueError as e:
            self.fail(f"顶部更新行的日期不是合法日期:{head!r} ({e})")
        floor = datetime.date(2026, 9, 1)   # 本仓自优化循环有记录的最早时间
        self.assertGreaterEqual(
            when, floor,
            f"顶部更新行写的日期是 {when},早于本仓有记录的时间 {floor}\n"
            f"—— 这张表声称「某条此刻处于什么状态」,陈旧日期会让读者把旧状态当新状态。")

    def test_A11_guard_itself_is_not_stale(self):
        r"""**元判据**:本文件自己声称的用例数与实际必须一致。

        红队 `b6baf473` 报出:A3 的 docstring 曾写「本条现在**必须是红的**」,
        而实测是绿的 —— **陈述跟着代码腐烂**,与本轮修的 A7 是同一类错误
        (那份文档里写着旧 Round 号,这份测试里写着旧预期)。

        本条把「用例数」这个最容易腐烂的数字钉住:docstring 里若写了条数,
        必须与实际加载到的条数一致。
        """
        import ast
        with io.open(os.path.abspath(__file__), encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src)
        names = [n.name for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
        loaded = sorted(n for n in dir(self.__class__) if n.startswith("test_"))
        self.assertEqual(
            sorted(names), loaded,
            f"文件里定义 {len(names)} 个 test_,但类上加载到 {len(loaded)} 个\n"
            f"定义={sorted(names)}\n加载={loaded}")
        # ⚠ **必须有一份硬编码的具名清单**,否则本条是空转。
        # 「定义数 == 加载数」只能抓「定义了但没加载」(缩进/装饰器/嵌套),
        # **抓不到「静默删掉一条」** —— 删掉时两边**同步缩小**,仍然相等。
        # 这正是 Round 50 踩过的「编辑时切片静默丢用例」形态:
        # 那次测试**全绿**(`Ran 5` 应为 6),靠的正是硬编码的期望才被发现。
        # ⚠ Round 64:期望必须是**名字**而不是**条数** —— 条数抓不住「改名」
        # (把 `test_X` 改成另一个 `test_` 开头的名字,AST 与 dir() **同步变**、
        #  计数不变、判据全绿,而被保护的用例已经消失)。
        self.assertEqual(
            loaded, sorted(CASE_NAMES),
            f"用例集与 `CASE_NAMES` 不一致。\n"
            f"  文件里定义={sorted(names)}\n  类上加载={loaded}\n"
            f"  清单={sorted(CASE_NAMES)}\n"
            f"如果这是**故意**增删 / 改名用例,请同步改 `CASE_NAMES`;\n"
            f"如果不是,那就是有用例被**静默**丢掉 / 改名 —— 那正是本条要抓的。")


    def test_A12_items_named_in_the_verdict_section_exist_in_the_table(self):
        r"""「S1 判定」段里点名的条目号,必须都在主表里存在。

        A7 只查**自报 Round 号够不够大**,不查**内容对不对**。
        红队 `f015df27` 实测:把两处 Round 都飙到 999,同时把判定段里的
        「C5 的 ④ 未修」改成「C5 的 ② 半未修」(与主表矛盾)→ **A7 全绿**。
        内容一致性靠自由文本,结构上无法完全判 —— 但**「点名了一个不存在的条目」
        是结构可判的**,而且这正是这类文档最常见的腐烂方式(条目改名/合并后忘了改引用)。

        与 A8(引用文件存在)同构,只是对象从文件变成条目号。
        """
        with io.open(DOC, encoding="utf-8") as f:
            text = f.read()
        i = text.find("## S1 判定")
        self.assertGreater(i, -1, "找不到「## S1 判定」段 —— 判据前提不成立")
        seg = text[i:]
        in_table = {item for _, item, _ in _read_rows() if item}
        named = set(re.findall(r"\*\*([ABC]\d+)\*\*", seg))
        named |= set(re.findall(r"(?<![A-Za-z0-9])([ABC]\d+)(?![0-9])", seg))
        ghosts = sorted(n for n in named if n not in in_table)
        self.assertEqual(
            ghosts, [],
            f"「S1 判定」段点名了这些**主表里不存在**的条目:{ghosts}\n"
            f"—— 条目改名/合并后忘了改引用,判定段就在描述一个不存在的东西。")

    def test_A13_c_numbers_cited_in_the_rounds_doc_are_in_the_table(self):
        r"""**轮次文档里引用的 C 编号,必须都在本表里** —— 从**另一个文件**反推。

        ⚠ 为什么需要它:A1 只查 `missing`(`ITEMS` 有、表里没有),
        对「**两侧同时缺失**」零信号 —— `ITEMS` 的上界是**手写**的 `range(1, 27)`,
        而 Round 77–82 新增的 C27–C31 **既没进表、也没进 `ITEMS`**,A1 因此**全绿**。
        补一个 `extra` 方向(表里有、`ITEMS` 没有)**也抓不到**它 —— 两边都没有。

        ⚠ **本文件里早就写着这句话**:上面 `ITEMS` 的注释「C8 在 Round 54 加进表里
        却没加进 ITEMS —— A1 只查 missing 不查 extra,漏了它」。
        **注释没挡住它** —— 这是本仓「靠记性堵不住,只能靠机制」的第七次实例
        (前六次见 C24 / C26)。

        判据从 `docs/self-optimize-rounds.md` **反推**:该文档里出现的 C 编号(≥6)
        必须都能在主表里找到。收窄到 **≥6** 有两个理由:
        ① `C0` / `C1` 在那份文档里是 **JEV preset 名**(`C0: 'standard', C1: 'standard'`),
           不是附录条目 —— 不收窄会误报;
        ② 这同时排除了附录原条目 C1–C5。
        ⚠ **但理由②是「一刀切排除」,不是「语义区分」** —— 轮次文档里 `C1` **确实**被当附录条目
        引用过(如「附录 C1(验证者外置)」)。红队 R83 P2-R83-H 指出,已改正。
        ⚠⚠ **本判据是「存在性判据」,不是「语义判据」—— 这是它的固有边界,如实写明:**
        红队 R83 P4-R83-A 实测:抹掉全部真实引用后**追加一行编号列表**
        (裸文本 / HTML 注释 / 代码围栏 / 每编号独占一行)**四种形态全部 `rc=0` 绕过**,
        且 `tests/test_rounds_doc_snapshot.py` 也无兜底。**它证明的是「文档里提到过这些编号」,
        不是「文档真的叙述了这些条目」。** 两条更强的口径实测都不可行:
        ① 「编号须在章标题 `# Round NN — C<n>` 里」—— 文档只有 12 条章标题,
           表里 C≥6 有 26 条 ⇒ C6–C19 与 C24 **共 15 条会误红**;
        ② 「编号须在结构化 footer 行 `ROUND n | 本轮缺陷=…` 里」—— 实测 29 条命中,
           但 footer 内容**仍是自由文本** ⇒ 伪造一条 footer 同样绕过,**仍是存在性**。
        **根因:纯文本判据证明不了「文档真的叙述了」。** 与 C14(输出伪造类边界)同族,
        只能靠**大 diff 评审**补位。登记为附录 **C32** 的未修项 ①。
        ★ **R107 补回**(红队 R106 P27-R106-A):R105 手工删行时**误删了本句尾巴**
        「**补位。登记为附录 **C32** 的未修项 ①。」并留下 `**` 失衡 —— 原文见 R104 冻结副本。
        ✅ **它仍有真净增量**:V2(只剩 `C31`)/ V3(只剩 `C0/C1/C31`)从 v1 的 `rc=0` 变为 `rc=1`。
        """
        with io.open(os.path.join(ROOT, "docs", "self-optimize-rounds.md"),
                     encoding="utf-8") as f:
            text = f.read()
        in_table = {int(i[1:]) for _, i, _ in _read_rows() if i and i[0] == "C"}
        self.assertTrue(in_table, "主表里没有任何 C 条目 —— 判据前提不成立")
        # ⚠ **不能用 `\b`**:Python 3 的 `\w` 含 CJK,`见C33条` 里 `C33` 两侧都是 `\w`
        #   ⇒ 无词边界 ⇒ **漏检**(红队 R83 P2-R83-B 的 M10 实测 rc=0)。
        #   也**不能**用裸 `C(\d+)`:轮次文档里满是 SHA256 十六进制串,会抓出
        #   C38 / C64 / C98 / C263 / C947 / C9249 六个**假编号**。
        #   正解 = **显式 ASCII 字母数字**边界,两头都收。
        cited = {int(n) for n in re.findall(r"(?<![A-Za-z0-9])C(\d+)(?![0-9A-Za-z])", text)}
        appendix_cited = {n for n in cited if n >= 6}
        # ⚠ **前提守卫不能写成 `assertTrue(cited)`**:文档里 `C0` / `C1` 是 **JEV preset 名**
        #   (`C0: 'standard'`),只要还剩这两行就满足 ⇒ **空转**
        #   (红队 R83 P2-R83-A 的 M3:文档只剩 preset 名 → rc=0 全绿)。
        #   改成「**表侧每条 C≥6 都必须被文档引用**」—— 不凭感觉取数量下界(本仓 C17 已记过该形态)。
        # ⚠ **不能只查 `max(in_table)` 是否出现**:把整份轮次文档换成一行 `C31` 即可满足 ⇒ 仍是空转
        #   (红队 R83 P3-R83-A 的 M3b / M3c 实测 rc=0)。
        #   排除 C1–C5 是因为它们是**原附录条目**,轮次文档不一定提。
        required = {n for n in in_table if n >= 6}
        self.assertTrue(required, "主表里没有 C6 及以上的条目 —— 判据前提不成立")
        absent = sorted(required - appendix_cited)
        self.assertEqual(
            absent, [],
            f"主表里有这些 C 条目,但轮次文档里**找不到任何引用**:{absent}\n"
            f"—— 判据前提不成立:轮次文档若丢失了全部附录引用,本判据就在空转。\n"
            f"⚠ 旧版只查 `max(in_table)` 是否出现,整份文档换成一行 `C31` 即可绕过\n"
            f"(红队 R83 P3-R83-A 的 M3b / M3c 实测 rc=0)。")
        missing = sorted(n for n in appendix_cited if n not in in_table)
        self.assertEqual(
            missing, [],
            f"`docs/self-optimize-rounds.md` 引用了这些**主表里没有**的 C 编号:{missing}\n"
            f"—— 轮次文档是过程记录,本表是 S1 的权威来源;\n"
            f"过程里新增的条目**必须**登记进表,否则 S1 永远无法判定「全部条目状态明确」。")

if __name__ == "__main__":
    unittest.main(verbosity=2)
