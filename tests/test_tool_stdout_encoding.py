# -*- coding: utf-8 -*-
r"""工具侧 stdout/stderr 编码:第三方**重定向/管道**取用必须仍是 UTF-8。

## 为什么单列一条(Round 50,附录 C6)

本机 `sys.stdout.encoding = gbk`(locale cp936)。Python 在**管道/重定向**下用 locale 编码,
而本仓所有文本产物都是 UTF-8 —— 于是:

    $ python tools/evasion_audit.py > audit.txt      # 默认环境,无 PYTHONIOENCODING
    $ python -c "print(open('audit.txt',encoding='utf-8').read()[:30])"
    G5 <乱码> —— 本行原先是**原样粘贴**的终端乱码;因 tests/test_no_encoding_damage.py 报红,已改为文字描述

**控制台里看着正常**(终端按 gbk 解码回中文),**重定向后全是乱码** —— 这正是
「**可被第三方复算**」这条目标的直接漏洞:别人按最自然的方式存盘再看,读到的不是我的结论。
而 `tools/evasion_audit.py` 就是 **G5 的验证工具**,`tools/_wilson_doc_scan.py` 是
**Wilson 区间独立复算工具** —— 两个都恰好是最需要被第三方读懂的。

## 判据(含 R4 守卫)

`benchmarks/accuracy/*.py` 那 22 个脚本各自写了 `TextIOWrapper(..., encoding='utf-8')`,
但 **`tools/` 下两个都没有**。本条要求:

1. **R4 守卫**:输出必须**真的含非 ASCII 字节**。否则 gbk 与 UTF-8 对纯 ASCII 完全一致,
   判据会**空转通过**却什么都没测到(「先确认测到了」)。
2. 输出必须能按 **UTF-8 无错解码**,且**不含 U+FFFD 替换字符**。
3. **stdout 与 stderr 都要**(只看 stdout 会漏掉 traceback 的乱码)。
"""

import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# tools/ 下的可执行入口(只读,无副作用)
TOOLS = ["tools/evasion_audit.py", "tools/_wilson_doc_scan.py"]


def _run_default_env(rel):
    r"""**默认环境**跑一个工具:清掉一切编码类环境变量。"""
    env = os.environ.copy()
    for k in ("PYTHONIOENCODING", "PYTHONUTF8", "PYTHONLEGACYWINDOWSSTDIO"):
        env.pop(k, None)
    return subprocess.run([sys.executable, "-B", rel], cwd=ROOT,
                          capture_output=True, env=env)


class TestToolStdoutEncoding(unittest.TestCase):

    def test_T1_tools_emit_utf8_when_redirected(self):
        r"""重定向到文件/管道时,输出必须仍是 UTF-8。"""
        bad = []
        for rel in TOOLS:
            with self.subTest(工具=rel):
                r = _run_default_env(rel)
                raw = (r.stdout or b"") + (r.stderr or b"")
                # ---- R4 守卫:先确认「测到了」 ----
                self.assertTrue(
                    any(b > 127 for b in raw),
                    f"{rel} 的输出全是 ASCII —— 本判据对纯 ASCII 是**空转**的"
                    f"(gbk 与 UTF-8 一致),先确认输出真含非 ASCII 再谈编码")
                # ---- 判据 ----
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError as e:
                    bad.append((rel, f"UTF-8 解码失败:{e}"))
                    continue
                if "\ufffd" in text:
                    bad.append((rel, "含 U+FFFD 替换字符(上游已损坏)"))
        self.assertEqual(bad, [], f"这些工具重定向后不是 UTF-8:{bad}")

    def test_T2_guard_is_falsifiable(self):
        r"""R9 可证伪:把编码改坏,本文件必须报红。

        ⚠ **本条在 Round 50 被红队 `77ed8102` 判为「伪证伪」并重写。**

        旧写法是「删掉含 `reconfigure` 的行」再重跑 T1。红队指出:
        那一删会把

            try:
                _s.reconfigure(encoding="utf-8")
            except Exception:

        变成 `try:` 紧跟 `except:` —— **语法错误**。
        子进程于是以 `SyntaxError` 退出码 1 结束,旧 T2 只看「退出码非 0」,
        就把**语法崩溃**当成了「编码缺陷被检出」。**它证明的是我删坏了文件,不是判据有效。**

        新写法:**改值不改结构** —— 把 `encoding="utf-8"` 换成 `encoding="gbk"`。
        语法完好、程序照跑,只有编码行为变了。**这才是对 T1 的真证伪。**
        并且断言子进程**确有 `Ran ` 行**(框架真跑了),堵住「崩溃冒充检出」。
        """
        import shutil
        import tempfile
        mirror = os.path.join(tempfile.gettempdir(), "jev_r50_enc_mirror")
        if os.path.exists(mirror):
            shutil.rmtree(mirror, ignore_errors=True)
        shutil.copytree(ROOT, mirror,
                        ignore=shutil.ignore_patterns(".git", "node_modules",
                                                      "tmp_jev_path1"))
        hit = 0
        for rel in TOOLS:
            p = os.path.join(mirror, rel)
            with open(p, encoding="utf-8") as f:
                src = f.read()
            mutated = src.replace('reconfigure(encoding="utf-8")',
                                  'reconfigure(encoding="gbk")')
            if mutated != src:
                hit += 1
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(mutated)
        self.assertGreater(hit, 0, "工具里根本没有 reconfigure —— 本条无可证伪对象")
        # 变异后语法必须仍然完好(否则又变成「崩溃冒充检出」)
        import ast
        for rel in TOOLS:
            with open(os.path.join(mirror, rel), encoding="utf-8") as f:
                ast.parse(f.read())          # 抛 SyntaxError 即本条自曝
        env = os.environ.copy()
        for k in ("PYTHONIOENCODING", "PYTHONUTF8"):
            env.pop(k, None)
        r = subprocess.run([sys.executable, "-B", "-X", "utf8",
                            "tests/test_tool_stdout_encoding.py", "-k", "T1"],
                           cwd=mirror, capture_output=True, env=env)
        # ⚠ `unittest` 的 "Ran N tests" 走 **stderr**,不是 stdout ——
        # 只读 stdout 会拿到空串,那条「框架真跑了没有」的断言就永远失败(或永远空转)。
        out = ((r.stdout or b"") + (r.stderr or b"")).decode("utf-8", "replace")
        shutil.rmtree(mirror, ignore_errors=True)
        self.assertIn("Ran ", out,
                      f"子进程根本没跑到测试框架(崩溃冒充检出):{out[-400:]}")
        self.assertNotEqual(
            r.returncode, 0,
            "把 encoding 改成 gbk 后 T1 仍然全绿 —— T1 没有在测编码")


    def test_T3_every_tool_entry_has_the_bootstrap(self):
        r"""结构守卫(准入规则):新增入口时,别漏挂编码 bootstrap。

        ⚠ **本条在 Round 50 被红队 `77ed8102` 用两个欺骗输入绕过,已重写。**

        旧写法是纯字符串匹配:`'__name__ == "__main__"' in src` 与
        `"reconfigure" in src`。两个绕过:
          ① 单引号 `if __name__ == '__main__':` → 匹配不上 → 被当「库模块」跳过;
          ② 正文里写一句注释 `# TODO: reconfigure` → 匹配得上 → 空脚本也放行。
        红队实测:构造这两个文件后 T3 **返回码 0 全绿**。

        新写法改用 **AST**:必须真的存在
          (a) 一个 `__name__ == "__main__"` 的比较(单双引号都认),且
          (b) 一次 `.reconfigure(encoding="utf-8")` 的**真实调用**。
        注释、字符串、单引号都骗不过语法树。
        """
        import ast
        missing = []
        # ⚠ 范围按**缺陷类别**划,不按目录划(Round 50 的教训):
        # 该缺陷是「向被重定向的 stdout/stderr 写中文的**入口**」,
        # 入口在 `tools/` 有,在 `benchmarks/accuracy/` 也有。
        # 初版只扫 `tools/`,于是 `benchmarks/accuracy/jevbench/__main__.py`
        # 与 `_make_pareto_report.py` 两个真实受害者都漏了(红队 `77ed8102` 实测)。
        SCAN_DIRS = ["tools", os.path.join("benchmarks", "accuracy"),
                     os.path.join("benchmarks", "accuracy", "jevbench")]
        files = []
        for d in SCAN_DIRS:
            full = os.path.join(ROOT, d)
            if not os.path.isdir(full):
                continue
            for fn in sorted(os.listdir(full)):
                if fn.endswith(".py") and not fn.startswith("__"):
                    files.append((os.path.join(d, fn), os.path.join(full, fn)))
        for rel, path in files:
            with open(path, encoding="utf-8") as f:
                src = f.read()
            tree = ast.parse(src)
            has_main = any(
                isinstance(n, ast.Compare)
                and isinstance(n.left, ast.Name) and n.left.id == "__name__"
                and any(isinstance(c, ast.Constant) and c.value == "__main__"
                        for c in n.comparators)
                for n in ast.walk(tree))
            if not has_main:
                continue                     # 不是入口(库模块)
            ok = False
            for n in ast.walk(tree):
                if not (isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Attribute)
                        and n.func.attr == "reconfigure"):
                    continue
                for kw in n.keywords:
                    if (kw.arg == "encoding"
                            and isinstance(kw.value, ast.Constant)
                            and kw.value.value == "utf-8"):
                        ok = True
            if not ok:
                missing.append(rel)
        # ---- 棘轮(Round 52)----
        # 扩范围后发现 `benchmarks/accuracy/` 下有一批**历史一次性分析脚本**
        # (`_` 前缀,23 个)同样缺 bootstrap。它们是 R50 §9 已如实登记的残余。
        #
        # 处理方式:**不强行改 23 个遗留脚本,但把它们冻结成清单** ——
        #   ① 出现清单外的**新**漏网文件 → 红(这才是准入规则的作用);
        #   ② 清单里的文件被修好 → **也红**,提示把该行从清单删掉(棘轮只往紧的方向转)。
        #
        # 为什么不做「一次性修复清单」:R50 的教训明写 ——
        # **一次性修复清单挡不住之后新建的文件**。冻结 + 禁止增长才挡得住。
        LEGACY = {
            "_analyze_10q.py", "_analyze_blind.py", "_analyze_blind2.py",
            "_analyze_blindrate.py", "_audit_9q.py", "_audit_measurement.py",
            "_check_arms.py", "_diag_c3_fail.py", "_diag_c3fail2.py",
            "_exp_assert_headroom.py", "_grade_assert.py",
            "_grade_c3f_partial.py", "_grade_expA30.py", "_grade_expD.py",
            "_grade_expD_sens.py", "_grade_gate30.py", "_grade_strong.py",
            "_mk_assert_suite.py", "_probe_archive.py", "_probe_compare.py",
            "_probe_grading.py", "_probe_timeout.py",
        }
        new_offenders = [m for m in missing if os.path.basename(m) not in LEGACY]
        self.assertEqual(
            new_offenders, [],
            f"这些入口是**新**漏网的(不在冻结清单里):{new_offenders}\n"
            f"—— 新增入口必须挂 bootstrap,照抄 tools/evasion_audit.py 顶部那段。")
        fixed = [b for b in LEGACY
                 if b not in {os.path.basename(m) for m in missing}]
        self.assertEqual(
            fixed, [],
            f"这些冻结清单里的文件**已经修好了**:{fixed}\n"
            f"—— 请把对应行从 LEGACY 删掉(棘轮只往紧的方向转)。")


    def test_T4_stderr_is_utf8_too(self):
        r"""**stderr 也要覆盖** —— 只改 stdout 会漏掉异常路径的乱码。

        本条是被**变异测试逼出来的**。Round 50 的变异 N-2(把 bootstrap 改成
        `for _name in ("stdout",):`,即**只改 stdout**)在加上本条之前**全量全绿**:

        原因:正常路径**根本不写 stderr**,于是 T1 里 `stdout + stderr` 的 stderr 是空的
        —— **T1 对 stderr 的判据是空转的**。

        这与 T1 里那条 R4 守卫(`any(b > 127 ...)`)**完全同构**:
        我在 stdout 上防住了「空转」,在 stderr 上没防 —— **同一个错犯两遍**。
        所以本条也带同样的守卫:stderr 必须**非空且含非 ASCII**,否则判据无效。

        触发方式:在**临时副本**里删掉 `docs/evasion-ledger.md`,
        工具走 `EXIT_MALFORMED` 分支,把判定文本写进 stderr。

        ⚠ 红队 `77ed8102` 独立报出了同一条(Q4.1),并给出**生产代码**上的同构实例:
        `benchmarks/accuracy/jevbench/__main__.py` 就是「只改了 stdout」的真实受害者
        (见 T5)。**判据的漏洞和生产的漏洞是同一个。**

        ⚠ 本条曾被我自己在重写 T2/T3 时**误删**(切片写错,把 T4 一起切掉了),
        靠 `Ran 5 tests` 与预期的 6 不符才发现 —— 所以 T7 钉住了套件里的用例数。
        """
        import shutil
        import tempfile
        mirror = os.path.join(tempfile.gettempdir(), "jev_r50_stderr_mirror")
        if os.path.exists(mirror):
            shutil.rmtree(mirror, ignore_errors=True)
        shutil.copytree(ROOT, mirror,
                        ignore=shutil.ignore_patterns(".git", "node_modules",
                                                      "tmp_jev_path1"))
        os.remove(os.path.join(mirror, "docs", "evasion-ledger.md"))
        env = os.environ.copy()
        for k in ("PYTHONIOENCODING", "PYTHONUTF8"):
            env.pop(k, None)
        r = subprocess.run([sys.executable, "-B", "tools/evasion_audit.py"],
                           cwd=mirror, capture_output=True, env=env)
        se = r.stderr or b""
        shutil.rmtree(mirror, ignore_errors=True)
        # ---- R4 守卫:先确认「测到了 stderr」 ----
        self.assertTrue(
            len(se) > 0,
            f"没有触发到写 stderr 的路径(exit={r.returncode})—— 本条判据空转,"
            f"先确认触发方式仍然有效")
        self.assertTrue(
            any(b > 127 for b in se),
            "stderr 全是 ASCII —— 本条判据对纯 ASCII 是空转的(gbk 与 UTF-8 一致)")
        # ---- 判据 ----
        try:
            se.decode("utf-8")
        except UnicodeDecodeError as e:
            self.fail(f"stderr 不是 UTF-8(只改了 stdout?):{e}")


    def test_T5_benchmark_entry_points_emit_utf8(self):
        r"""红队 `77ed8102` 查出的**另外两个生产入口**,一并钉住。

        作者(我)首轮只修了 `tools/` 下两个脚本,就声称「工具侧编码已修」。
        红队逐文件实测后指出:**核心评测入口也中招**,而且更严重:

          · `benchmarks/accuracy/jevbench/__main__.py` —— 只改了 stdout,**stderr 仍是 gbk**。
            实测 `python -m jevbench merge --seeds=,` 的 stderr 是
            `b'--seeds \\xb2\\xbb\\xc4\\xdc\\xce\\xaa\\xbf\\xd5'`(GBK 的「不能为空」)。
          · `benchmarks/accuracy/_make_pareto_report.py` —— **完全没有任何编码处理**,
            stdout 重定向后 1600+ 字节全是 GBK。

        **教训**:「修了一类缺陷」不等于「这一类修完了」。我按**目录**划范围(`tools/`),
        而不是按**缺陷类别**划范围,于是漏掉了同一缺陷在另一个目录的实例。

        两条都在**临时副本**里跑(第二个会写 `docs/pareto-frontier.md`,不能碰真仓库)。
        """
        import shutil
        import tempfile
        mirror = os.path.join(tempfile.gettempdir(), "jev_r50_bench_mirror")
        if os.path.exists(mirror):
            shutil.rmtree(mirror, ignore_errors=True)
        shutil.copytree(ROOT, mirror,
                        ignore=shutil.ignore_patterns(".git", "node_modules",
                                                      "tmp_jev_path1"))
        env = os.environ.copy()
        for k in ("PYTHONIOENCODING", "PYTHONUTF8"):
            env.pop(k, None)
        cases = [
            ("jevbench/__main__.py 的 stderr",
             [sys.executable, "-B", "-m", "jevbench", "merge", "--seeds=,",
              "--out", os.path.join(tempfile.gettempdir(), "jev_r50_dummy.jsonl")],
             os.path.join(mirror, "benchmarks", "accuracy")),
            ("_make_pareto_report.py 的 stdout",
             [sys.executable, "-B",
              os.path.join("benchmarks", "accuracy", "_make_pareto_report.py")],
             mirror),
        ]
        bad = []
        for label, args, cwd in cases:
            r = subprocess.run(args, cwd=cwd, capture_output=True, env=env)
            raw = (r.stdout or b"") + (r.stderr or b"")
            # ---- R4 守卫:先确认「测到了」 ----
            self.assertTrue(
                any(b > 127 for b in raw),
                f"{label}:输出全是 ASCII —— 本条判据空转(gbk 与 UTF-8 对纯 ASCII 一致)")
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError as e:
                bad.append((label, f"UTF-8 解码失败:{e}"))
        shutil.rmtree(mirror, ignore_errors=True)
        self.assertEqual(bad, [], f"这些评测入口重定向后不是 UTF-8:{bad}")

    def test_T6_bootstrap_does_not_pollute_importer(self):
        r"""红队 `77ed8102` 实测的**全局副作用**:import 会改写调用方的 stdout 编码。

        旧写法把 bootstrap 放在**模块顶层**。于是任何 `import tools.evasion_audit`
        的调用方,其自己的 `sys.stdout` 编码会被**无条件改成 utf-8**。
        红队实测:`import` 前是 `latin-1`,后变 `utf-8`。

        修法:把 bootstrap 包进 `if __name__ == "__main__":` ——
        以脚本身份跑才生效,被 import 时不动。

        本条在**子进程**里做,免得污染本进程。
        """
        import json
        code = (
            "import io, json, sys, importlib.util as iu\n"
            "p = sys.argv[1]\n"
            "real = sys.stdout\n"
            "custom = io.TextIOWrapper(io.BytesIO(), encoding='latin-1')\n"
            "sys.stdout = custom\n"
            "spec = iu.spec_from_file_location('jev_probe', p)\n"
            "m = iu.module_from_spec(spec)\n"
            "spec.loader.exec_module(m)\n"
            "sys.stdout = real\n"
            "print(json.dumps({'before': 'latin-1', 'after': custom.encoding}))\n"
        )
        for rel in ("tools/evasion_audit.py", "tools/_wilson_doc_scan.py"):
            r = subprocess.run(
                [sys.executable, "-X", "utf8", "-B", "-c", code,
                 os.path.join(ROOT, rel)],
                capture_output=True)
            self.assertEqual(r.returncode, 0,
                             (r.stderr or b"").decode("utf-8", "replace")[-400:])
            got = json.loads((r.stdout or b"").decode("utf-8"))
            self.assertEqual(
                got["after"], "latin-1",
                f"{rel} 被 import 时改写了调用方的 stdout 编码"
                f"({got['before']} → {got['after']})—— bootstrap 没包进 __main__")


    def test_T7_suite_has_not_silently_lost_cases(self):
        r"""元判据:钉住本文件里的用例数。

        为什么需要它:我在重写 T2/T3 时用切片拼接,**把 T4 整条静默切掉了** ——
        测试**全绿**,因为少一条用例不会让套件失败。
        是 `Ran 5 tests` 与预期的 6 不符才暴露的。

        **「少了一条判据」和「判据通过」在退出码上完全一样** —— 这是自欺的完美温床。
        所以这里把期望值钉死;将来**故意**增删用例,必须同步改这个数字。
        """
        import re
        import unittest as _ut
        with open(os.path.abspath(__file__), encoding="utf-8") as f:
            src = f.read()
        names = sorted(set(re.findall(r"^    def (test_\w+)", src, re.M)))
        self.assertEqual(
            len(names), 7,
            f"本文件的用例数从 7 变成了 {len(names)}:{names}\n"
            f"若是有意增删,请同步更新这个数字;若是编辑事故,请把丢掉的用例补回来")
        loader = _ut.TestLoader()
        loaded = loader.loadTestsFromTestCase(TestToolStdoutEncoding).countTestCases()
        self.assertEqual(
            loaded, 7,
            f"文件里有 {len(names)} 个 test_ 方法,但 unittest 只加载到 {loaded} 个 —— "
            f"有方法没被识别(缩进/装饰器/嵌套?):{names}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
