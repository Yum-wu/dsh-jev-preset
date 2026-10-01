# -*- coding: utf-8 -*-
r"""
护栏变异验证 —— **在 TEMP 副本上变异,绝不写 REPO 的源文件**。

判据(预注册,R9):
  M1 每条护栏被阉割后,`tests/test_guardrails.py` 必须**变红**。
  M2 REPO 工作区在全程必须保持洁净 —— 变异只发生在副本里。
  M3 结束时 REPO 仍洁净;副本是唯一被改动的东西。

为什么改成副本模式(2026-10-01 Round 22,红队 39f52d8f/78c78922 指出的第 7 条):

  Round 19 我在 REPO 上原地变异,把 `slippage.py` 的深度护栏换成 `pass  # VULN depth`
  之后**没有还原**,此后所有测试都跑在被阉割的代码上,而测试反而全绿 ——
  一条永不报警的风控护栏被记成了「已覆盖」。

  原地变异有三个独立的失败面:
    ① 异常中断 → 不还原 → 污染(已发生过一次);
    ② 另一个人/另一路 agent 同时编辑同一文件 → 互相覆盖;
    ③ 还原校验本身出错 → 静默留下半个变异。
  副本模式把三者一次性消掉:REPO 的文件从头到尾没人写过。

变异清单最后一条是红队设计的**对照变异**(floor→ceil 算法替换):
  它不是删 assert,而是改算法。若测试仍全绿,说明用例抓错了行 ——
  红队实测 Round 19 的 G2/G7 在这条变异下**全绿而实际抛的是 [预算穿透]**。
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
REPO_PKG = os.path.join(PLUGIN_ROOT, "packages", "assertions", "python", "jev_assertions")

# (标识, 源文件, 原行, 变异行)
MUTANTS = [
    ("lot:min_notional", "tick.py",
     "assert notional >= min_not",
     "pass  # VULN min_notional"),
    ("vwap:depth_sufficient", "slippage.py",
     "assert rem == Decimal('0'), f\"[深度不足]",
     "pass  # VULN depth"),
    ("fwd_adj:adj_price>0", "split.py",
     "assert adj_hist > Decimal('0')",
     "pass  # VULN adjprice"),
    # ★ 对照变异(红队 39f52d8f 设计):不改 assert,只改 qty 算法。
    #   删 assert 的变异只能证明「用例会红」;这条能证明「用例红的原因是它该红的原因」。
    ("lot:algo floor->ceil(对照)", "tick.py",
     "qty = (b // p // step) * step",
     "qty = (b / p).to_integral_value(rounding=ROUND_CEILING) // step * step"),
]


def git_status_count():
    r = subprocess.run(["git", "status", "--porcelain"], cwd=PLUGIN_ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return len(r.stdout.strip().splitlines())


def build_copy():
    """把断言库与测试复制到一个临时目录,后续所有写操作只发生在这里。

    ⚠ 必须复制**全部** .py(2026-10-01 实测):只复制被变异的 3 个文件时,
      副本里缺 `__init__.py` / `calendar.py` / `margin.py`,
      `import jev_assertions` 直接失败 → 测试根本没跑 → 脚本误报「还原后仍红」。
      这正是「测量链路先要确认测到了」(R4)。
    """
    tmp = tempfile.mkdtemp(prefix="jev_mut_")
    pkg = os.path.join(tmp, "packages", "assertions", "python", "jev_assertions")
    os.makedirs(pkg)
    for fn in os.listdir(REPO_PKG):
        if fn.endswith(".py"):
            shutil.copy2(os.path.join(REPO_PKG, fn), os.path.join(pkg, fn))
    tests = os.path.join(tmp, "tests")
    os.makedirs(tests)
    shutil.copy2(os.path.join(HERE, "test_guardrails.py"),
                 os.path.join(tests, "test_guardrails.py"))
    return tmp


def run_suite(tmp):
    r = subprocess.run([sys.executable, "-B", os.path.join(tmp, "tests", "test_guardrails.py")],
                       cwd=tmp, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stderr or "") + (r.stdout or "")


def main():
    before = git_status_count()
    print(f"M2 REPO 起始洁净性:git status 条目 = {before}")
    if before != 0:
        print("  提示:工作区本就有未提交改动(Round 1-22 的累积产物),"
              "本脚本只保证**自己**不再新增改动。")

    tmp = build_copy()
    results = []
    # 每轮都从 pristine 写回。上一版把 import 注入到 original 上再 finally 写回,
    # 造成「还原后仍红」—— 还原本身成了第二个 bug(2026-10-01 实测)。
    pristine = {}
    for _fn in os.listdir(os.path.join(tmp, "packages", "assertions", "python", "jev_assertions")):
        if _fn.endswith(".py"):
            with open(os.path.join(tmp, "packages", "assertions", "python",
                                   "jev_assertions", _fn), "r", encoding="utf-8") as fh:
                pristine[_fn] = fh.read()
    try:
        for name, fname, old, new in MUTANTS:
            path = os.path.join(tmp, "packages", "assertions", "python",
                                "jev_assertions", fname)
            original = pristine[fname]
            if old not in original:
                print(f"  SKIP {name}: 原文锚点未命中 -> {old!r}")
                print("        (锚点写错会导致「变异未生效却报通过」的假绿)")
                results.append((name, "ANCHOR-MISS"))
                continue
            mutated = original
            if new.startswith("qty = (b / p)"):
                mutated = mutated.replace(
                    "from decimal import Decimal",
                    "from decimal import Decimal, ROUND_CEILING", 1)
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(mutated.replace(old, new, 1))
                rc, out = run_suite(tmp)
                tail = [l for l in out.splitlines() if l.startswith(("FAILED", "OK", "Ran "))]
                why = [l.strip() for l in out.splitlines()
                       if l.strip().startswith("AssertionError:")][:1]
                verdict = "有判别力(变红)" if rc != 0 else "★无判别力(仍全绿)"
                print(f"  {name}: exit={rc} {verdict} | {' / '.join(tail[-2:])}")
                if why:
                    print(f"      首个失败原因: {why[0][:110]}")
                results.append((name, verdict))
            finally:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(pristine[fname])
        rc, _ = run_suite(tmp)
        print(f"  副本还原后全量 exit={rc} {'(OK)' if rc == 0 else '(★仍红!)'}")
        judged = [r for r in results if r[1] != "ANCHOR-MISS"]
        strong = [r for r in judged if "有判别力" in r[1]]
        print(f"M1 结论: {len(strong)}/{len(judged)} 条变异被测试检出")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    after = git_status_count()
    print(f"M3 结束时 REPO git status 条目 = {after}(起始 {before})")
    clean = after == before
    print("  " + ("PASS 未对 REPO 产生任何改动" if clean else "★FAIL REPO 被改动了"))
    return 0 if clean and rc == 0 and len(strong) == len(judged) else 1


if __name__ == "__main__":
    sys.exit(main())
