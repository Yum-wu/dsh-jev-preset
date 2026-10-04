# -*- coding: utf-8 -*-
r"""G1–G5 全量回归,**不经任何 shell 管道**。

## 为什么需要这个脚本(Round 54)

我一直用 PowerShell 现敲 G1–G5。Round 54 实测到一个**证据污染**:

```powershell
python -X utf8 -B tools/evasion_audit.py 2>&1 | Select-String -Pattern 'A5 ' | Select-Object -First 1
"G5 exit=$LASTEXITCODE"        # ← 打印 0
```

而 `python tools/evasion_audit.py` 的**真值是 1**。

**机制**:`Select-Object -First N` 会**提前掐断管道**。上游 native 命令还在写输出时
被终止,它的退出码**根本不被记录**,`$LASTEXITCODE` **保留上一条命令的值**。
我那次的上一条是 `jev_r45_g4_smoke.py`(exit 0)→ 于是打印出**陈旧的 0**。

**危害**:`G5 exit=0` 读作「规避率正常,可以继续循环」,而真相是
「窗口内出现高位规避,按 G5 应停止」。**差点据一个陈旧数字下相反的结论。**
这与本仓记过的「PowerShell `>` 洗掉字节级证据」是**同一族**:
**shell 会吃掉退出码/字节,而吃掉之后留下的仍是一个看似合理的数字。**

## 本脚本的契约
- 一律用 Python `subprocess.run(capture_output=True)` 取**原始退出码与字节**;
- **不调用任何 shell**;不写临时文件到仓库外;
- 退出码 = 「G1–G4 是否全过」(G5 是**信息性**的:它 exit 1 是既有判定,
  不应当让整个回归变红 —— 但**必须原样打印它的判定文本**)。

用法:
    python -X utf8 -B tools/g_check.py
    python -X utf8 -B tools/g_check.py --json      # 机器可读
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JEV_CLI = os.path.join(ROOT, "packages", "assertions", "python",
                       "jev_assertions", "cli.py")

TIERS = [{"tier": 1, "max_notional": 50000, "mmr": 0.005},
         {"tier": 2, "max_notional": 250000, "mmr": 0.01}]

G4_CASES = [
    ("pass", "tick_floor", {"raw_price": 0.29, "tick_size": 0.01, "expected": 0.29}),
    ("pass", "fractional_tick", {"raw_price": 1.234, "fraction": 0.01, "expected": 1.23}),
    ("pass", "tiered_mm", {"notional": 60000, "tiers": TIERS,
                           "expected_mm": 350, "expected_deduction": 250}),
    ("fail", "tick_floor", {"raw_price": 0.29, "tick_size": 0.01, "expected": 0.28}),
    ("fail", "fractional_tick", {"raw_price": 1.234, "fraction": 0.01, "expected": 1.24}),
    ("fail", "tiered_mm", {"notional": 60000, "tiers": TIERS,
                           "expected_mm": 999, "expected_deduction": 250}),
]


def _run(argv, cwd=ROOT):
    """跑一条命令,返回 (exit, stdout+stderr 原始文本)。不经 shell。

    ⚠ Windows 上 `npm`/`node` 实际是 `npm.cmd`/`node.exe` ——
    直接传 "npm" 给 `CreateProcess` 会 `FileNotFoundError: [WinError 2]`。
    必须用 `shutil.which` 解析,**不要**改成 `shell=True`(那会把退出码
    再经一层 cmd,正是本脚本要消除的东西)。
    """
    argv = [shutil.which(argv[0]) or argv[0]] + list(argv[1:])
    r = subprocess.run(argv, cwd=cwd, capture_output=True,
                       env={k: v for k, v in os.environ.items()
                            if k not in ("PYTHONIOENCODING", "PYTHONUTF8")})
    out = ((r.stdout or b"") + (r.stderr or b"")).decode("utf-8", "replace")
    return r.returncode, out


#: unittest 的**汇总行**:`OK (skipped=N)` / `FAILED (failures=1, skipped=2)`
_RE_UNITTEST_SKIP = re.compile(r"^(?:OK|FAILED)\s*\([^)]*\bskipped=(\d+)[^)]*\)\s*$", re.M)
#: node --test 的汇总行:`ℹ skipped 1`
_RE_NODE_SKIP = re.compile(r"^\s*\u2139\s*skipped\s+(\d+)\s*$", re.M)


def _skip_total(out):
    """解析回归输出里的 skip 总数(unittest 汇总行 + node --test 汇总行)。

    ⚠ **为什么必须锚定到汇总行(Round 60 红队实测)**:初版是全文搜 `skipped=(\\d+)`,
    红队当场证伪 —— 任一测试打印的日志里出现 `skipped=99`(纯文本,不是任何计数),
    就会让 `_skip_total` 返回 99,于是判据把**全绿判红**(误报方向);
    同理路径里含 `skipped=1` 也会被骗。锚定 `^(OK|FAILED) (...)` 之后这类文本不再命中。

    ⚠ **为什么还要认 node 的行(Round 60 红队实测)**:`npm test` 第一步就是
    `node --test tests/test-*.mjs`,而 node 的 skip 输出是 `ℹ skipped 1` ——
    **没有 `skipped=` 字串**。只认 unittest 格式的话,node 侧的 skip 是**永久盲区**。

    ⚠ 已知盲区(未覆盖,如实声明):pytest 的 `1 skipped` 格式。本仓不用 pytest,故不覆盖。
    """
    return (sum(int(m) for m in _RE_UNITTEST_SKIP.findall(out))
            + sum(int(m) for m in _RE_NODE_SKIP.findall(out)))


#: ANSI 颜色 / 光标转义 —— **先剥掉再解析**。
# ⚠ Round 62 红队(补派)实测:彩色输出(`\x1b[32mOK\x1b[0m` / `\x1b[36mRan …`)会让
# 两个整行正则**全部失配** → 形状判据把**合法**输出判红。剥转义是零成本的修法。
_RE_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
#: unittest 的**计数行**:`Ran 31 tests in 12.345s` —— **整行**匹配。
# ⚠ Round 62 红队 F1(实测**误报**):初版 `^Ran (\d+) tests? in ` 会被**测试自己打印的
# 日志行**污染 —— `print("Ran 5 tests in the morning")` 会让套件数虚高 1,
# 于是形状比对失败、**把真绿判红**。unittest 这一行永远以秒数结尾,故锚到行尾。
_RE_RAN = re.compile(r"^Ran (\d+) tests? in \d+(?:\.\d+)?s\s*$", re.M)
#: unittest 的**结论行**:`OK` / `OK (skipped=1)` / `FAILED (failures=1)` —— **整行**。
# ⚠ 同上:初版 `^(?:OK|FAILED)\b` 会被 `OK: cache warm` 这类日志行命中,
# 于是「汇总行被吞」时由日志行顶替 → **漏检**(红队 F2,实测)。
_RE_VERDICT = re.compile(r"^(?:OK|FAILED)(?:\s*\([^)]*\))?\s*$", re.M)


def _unittest_shape(out):
    """解析输出的**形状**:(套件数, 测试总数, 结论行数)。

    ⚠ **为什么需要它(Round 62 / 附录 C12)**:G1/G3 的判据原本只看
    `rc == 0 and skipped == 0` —— **不看自己有没有测到东西**。
    Round 61 红队实测 5 种输出变换(`WRAP` / `FILTER` / `EMPTY` /
    `Ran 0 tests` / 整脚本空跑)下 G1/G3 **全部判绿**。
    这是「**空转判据**」族:判据看似在守,实则对被守对象**零输入**。

    ⚠ **它挡不住什么(如实声明;Round 62 红队实测)**:当攻击者**同时**控制
    `package.json` 与输出时,可以**精确仿造形状**(打印 31 组假 `Ran`/`OK`),
    或把 `OK (skipped=2)` **剥壳**成 `OK`。**任何读「自己所不控制的命令」输出的
    判据都挡不住这一点。** 真正的防线是 `package.json` 是**入库受审**的产物 ——
    这类伪造必然留下一个大 diff。本判据的职责是**抬高成本** + 让「静默」变「显式」。
    """
    runs = [int(x) for x in _RE_RAN.findall(_RE_ANSI.sub("", out))]
    return len(runs), sum(runs), len(_RE_VERDICT.findall(_RE_ANSI.sub("", out)))


def _declared_suites():
    """`package.json` 的 `test` 脚本里**真的调用**了几个 python 套件。

    ⚠ **不能只数字面出现**(Round 62 红队 A1,实测):初版用
    `re.findall(r"tests/test_*.py", script)` —— 于是
    `echo "tests/test_a.py tests/test_b.py …"` 这类**只把路径打印出来**的写法
    也会被数进去。红队实测:把 `test` 脚本换成「打印 31 组假形状 + `echo` 31 个路径」
    → 三个锚点**同时满足**、**0 个测试真跑,而 G1 判绿**。
    现在只数 `&&` 链里**以 python 解释器开头、且指向真实存在文件**的段。

    ⚠ 残余边界(如实声明):攻击者仍可写 31 条**真的** `python -c "打印假形状"` ——
    但那是一个 31 段的可见 diff。

    ⚠ **路径必须是段尾的实参**(Round 62 红队补派 N1,实测):初版用
    `re.search(r"tests/test_*.py", seg)` —— 于是
    `python -c "print('tests/test_a.py')"` 这种**把路径写在字符串里**的段也会被数进去,
    红队据此造出「31 条 `python -c` 打印假形状 + 假路径」→ 三锚点齐满足、**判绿**。
    现在要求 `tests/test_X.py` 出现在**段的末尾**(前面是解释器 + 可选开关)。
    """
    with open(os.path.join(ROOT, "package.json"), encoding="utf-8") as fh:
        script = json.load(fh)["scripts"]["test"]
    n = 0
    for seg in script.split("&&"):
        seg = seg.strip()
        if not re.match(r"^(?:[A-Za-z]:)?[^ ]*?(?:python[0-9.]*|py)(?:\.exe)?\s",
                        seg, re.I):
            continue
        m = re.search(r"tests[/\\](test_[A-Za-z0-9_]+\.py)\s*$", seg)
        if m and os.path.exists(os.path.join(ROOT, "tests", m.group(1))):
            n += 1
    return n


def _expected_suites():
    """`tests/` 下**应当**挂进 `npm test` 的 python 套件数。

    ⚠ 排除**声明**了「有意红」标记的文件 —— 那是本仓**既有**的约定
    (与 `tests/test_means_markers.py::T4` 同源):公式已被证伪、但正确写法
    需业务拍板的测试必须保持红,显式登记,而不是偷偷不挂。

    ⚠ 必须按 **T4 的原规则**判「声明」:**行首**以标记开头。
    Round 62 初版写成「源码里含该字面」→ 把 `test_means_markers.py` 自己
    (它源码里**提到**了这个标记)也排除了 → `_expected_suites()` 少 1,
    被本轮的 A4 当场抓到。**「提到」不等于「声明」。**

    ⚠ **不写死数字**:写死就会过期,而过期的数字**没有判据守着**
    (本仓记过:「含糊的 count 给出权威的错数」)。自锚定到产物 ——
    新增测试文件不挂进 `npm test` 就会红。
    """
    marker = "EXPECTED" + "_RED"
    n = 0
    d = os.path.join(ROOT, "tests")
    for name in sorted(os.listdir(d)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        with open(os.path.join(d, name), encoding="utf-8") as fh:
            if any(l.strip().startswith(marker) for l in fh.read().splitlines()):
                continue
        n += 1
    return n


def g1():
    rc, out = _run(["npm", "test"], cwd=ROOT)
    suites, tests_total, verdicts = _unittest_shape(out)
    expected, declared = _expected_suites(), _declared_suites()
    fails = [l for l in out.splitlines() if l.startswith(("FAIL:", "ERROR:"))]
    skipped = _skip_total(out)
    # ⚠ 形状判据:三个锚点必须互相印证(Round 62 / 附录 C12)
    # - `expected >= 1`:挡「测试全删光 + 配置清空」→ `0 == 0 == 0` 恒真(红队 A4,实测)
    # - `verdicts == suites`:挡「汇总行被吞剩 1 条」(红队 A3,实测)
    shape_ok = (expected >= 1 and suites == expected == declared
                and tests_total >= suites and verdicts == suites)
    detail = (f"Ran 行 {suites}/{expected} 条(声明 {declared}),测试 {tests_total} 个,"
              f"汇总行 {verdicts} 条,失败 {len(fails)} 条,skipped {skipped} 条")
    if skipped:
        detail += "  ← 有测试被跳过:「绿」不等于「验过了」"
    if not shape_ok:
        detail += "  ← 输出形状不对:「没报错」不等于「真跑了」"
    return {"name": "G1 npm test", "exit": rc,
            "ok": rc == 0 and skipped == 0 and shape_ok,
            "skipped": skipped, "detail": detail}


def g2():
    a, oa = _run(["node", "validate.mjs"])
    b, ob = _run(["node", "validate-official.mjs"])
    return {"name": "G2 双 validate", "exit": a if a else b,
            "ok": a == 0 and b == 0,
            "detail": f"validate.mjs exit={a} · validate-official.mjs exit={b}"}


def g3():
    rc, out = _run([sys.executable, "-B", "tests/test_accuracy_bench.py"])
    m = re.search(r"Ran (\d+) tests", out)
    suites, tests_total, verdicts = _unittest_shape(out)
    skipped = _skip_total(out)
    # ⚠ G3 只跑一个文件,故形状判据是 `suites >= 1`(不是 `== 期望`)。
    # 边界如实声明:它挡得住「整体空转」,挡不住「把套件内部掏空到只剩 1 个用例」;
    # 也挡不住「直接改写 `tests/test_accuracy_bench.py` 去打印假形状」(红队 A5)——
    # 那会留下一个可见 diff,与本仓对 `package.json` 的信任模型一致。
    shape_ok = suites >= 1 and tests_total >= suites and verdicts == suites
    detail = (f"Ran {m.group(1) if m else '?'} tests,skipped {skipped} 条"
              f" · 形状 {suites}/{tests_total}/{verdicts}")
    if skipped:
        detail += "  ← 有测试被跳过:「绿」不等于「验过了」"
    if not shape_ok:
        detail += "  ← 输出形状不对:「没报错」不等于「真跑了」"
    return {"name": "G3 accuracy selftest", "exit": rc,
            "ok": rc == 0 and skipped == 0 and shape_ok,
            "skipped": skipped, "detail": detail}


def g4():
    rc, out = _run([sys.executable, "-B", JEV_CLI, "--list"])
    # ⚠ `--list` 输出的是 **JSON**,不是行列表。
    # Round 54 初版按非空行数点,得到「115 项」—— 那其实是 JSON 的字段名行。
    # **含糊的 count 又一次给出权威的错数。**
    try:
        n = len(json.loads(out)["assertions"])
    except Exception:
        n = -1
    bad = 0
    for want, func, args in G4_CASES:
        c, _ = _run([sys.executable, "-B", JEV_CLI, "--func", func,
                     "--args", json.dumps(args, ensure_ascii=False)])
        if c != (0 if want == "pass" else 1):
            bad += 1
    return {"name": "G4 断言 CLI 冒烟", "exit": rc, "ok": (n == 18 and bad == 0),
            "detail": f"--list {n} 项(期望 18)· 冒烟 {len(G4_CASES) - bad}/{len(G4_CASES)} 符合退出码契约"}


def g5():
    rc, out = _run([sys.executable, "-X", "utf8", "-B", "tools/evasion_audit.py"])
    verdict = ""
    a5 = ""
    a10 = ""
    a11 = ""
    a11b = ""
    for l in out.splitlines():
        if l.startswith("G5 判定:"):
            verdict = l.strip()
        if l.startswith("A5 "):
            a5 = l.strip()
        # A10(Round 68):回填计数必须每轮露出来。铁律 1 想防「事后补写冒充预注册」,
        # 而它此前连数字都没出现过 —— 「81/108 条已结算规避是回填」这件事,
        # 是加上这行才看见的。(⚠ 别把这里与 `evaded_total` 相除:
        # 那个字段只统计**计分轮**,与全表回填数**不同分母**。)
        # A11(Round 69 红队 F3/F6):A10 是**自报**(标签由我自己写)→ 补上**客观**
        # 交叉校验(`结算轮==提出轮`,违反铁律 3)与**差值**(我少贴了多少标签)。
        # 只报自报数等于把指标交回我手里 —— 不贴标签就好看。
        if l.startswith("A10 "):
            a10 = l.split("——")[0].strip()
        if l.startswith("A11 "):
            a11 = l.split("——")[0].strip()
        # A11b(Round 71 红队 F-D):已结算但 `结算轮` **不可解析**的行会静默逃过上面两个数
        # —— 把结算轮填成 `—`/空,客观信号就归零而脚本不吭声。非 0 时上方信号**不完整**,
        # 所以它必须出现在抬头里,否则看 G5 一行的人以为客观数是全量。
        if l.startswith("A11b "):
            a11b = l.split("——")[0].strip()
    detail = (" · ".join(x for x in (a5, a10, a11, a11b) if x)
              or "(无 A5/A10/A11/A11b 行)")
    return {"name": "G5 规避率审计", "exit": rc, "ok": None,      # 信息性
            "detail": detail, "verdict": verdict}


def main(argv=None):
    ap = argparse.ArgumentParser(description="G1–G5 全量回归(不经 shell)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    rows = [g1(), g2(), g3(), g4(), g5()]
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for r in rows:
            tag = "OK " if r["ok"] else ("-- " if r["ok"] is None else "!! ")
            print(f"{tag}{r['name']:22s} exit={r['exit']}  {r['detail']}")
            if r.get("verdict"):
                print(f"      {r['verdict']}")
    hard = [r for r in rows if r["ok"] is False]
    print(f"\nG1–G4 {'全过' if not hard else '有失败'};"
          f"G5 为信息性判定(exit={rows[4]['exit']})")
    return 1 if hard else 0


if __name__ == "__main__":
    # ⚠ 入口必须挂 UTF-8 bootstrap:本机 `sys.stdout.encoding` 是 **gbk**,
    # 直接打印中文,一旦 stdout 被重定向就是 GBK 字节(第三方复算会看到乱码)。
    # 本文件**建好当天就被 `tests/test_tool_stdout_encoding.py::T3` 抓到**
    # —— 那条棘轮判据按**缺陷类别**(「向被重定向的 stdout 写中文的入口」)
    # 扫 `tools/`,不按「这个文件是不是我刚写的」。
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
