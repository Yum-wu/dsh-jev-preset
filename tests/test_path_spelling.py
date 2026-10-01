# -*- coding: utf-8 -*-
r"""
D1 的彻底性:同一目录的**任意路径身份**都必须被正确识别。

## 缺口(三轮都没修对,红队逐轮实证)

| 轮次 | 写法 | 判定方式 | 结果 |
|---|---|---|---|
| 1 | `while _here in sys.path` | 精确字符串 | 小写拼写绕过 |
| 2 | `normcase(abspath(p)) == normcase(_here)` | 归一化字符串 | `\\?\`、`\\.\`、**junction** 绕过 |
| 3 | `os.path.samefile(p, _here)` | **文件系统身份** | — |

第 2 轮我写的注释宣称「三者合起来才覆盖得住 `\\?\` 前缀」,**是错的**:
`normcase` 只做 `replace('/','\').lower()`,不剥离长路径前缀、不解析 junction。
红队实测三种手法都让 `ny_open_utc` 回到 `error` / exit 2。

## 判据(预注册,R9)

  P1 同一目录的**字符串变体**(小写 / 大小写互换)必须 pass。
  P1b 同一目录的**另一种路径身份**(`\\?\` 前缀、`\\.\` 前缀、junction)必须 pass ——
     这一组才是真正能证伪 `samefile` 的;上一版的「尾反斜杠」是假绿
     (Python 启动时自己就把 PYTHONPATH 绝对化并去尾分隔符,与 cli.py 怎么写无关)。
  P2 摘除逻辑**不得摘掉非脚本目录**。做法是**真正执行** cli.py:
     复制一份到 TEMP,在其顶层插入一行把 `sys.path` 打到 stderr 的探针,再跑副本。
     ⚠ 上一版的 P2 是**恒绿的假绿**:它的探针把摘除逻辑**自己内联了一份旧实现**,
       从不 import / 执行 cli.py。实测把 cli.py 改成「删掉除 cwd 外的全部条目」,
       P2 依然 OK —— 它压根没在测被审对象。
  P3 干净环境不受损(回归对照)。
  P4 junction 用例若因权限无法创建 junction,**必须 skip 并说明**,不得静默通过。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PKG = os.path.join(ROOT, "packages", "assertions", "python", "jev_assertions")
CLI = os.path.join(PKG, "cli.py")

_PAYLOAD = {"date_str": "2026-03-06", "ny_open_local": "09:30:00",
            "expected_utc": "14:30:00"}


def run_cli(pythonpath=None, cli=CLI):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if pythonpath is not None:
        env["PYTHONPATH"] = pythonpath
    r = subprocess.run([sys.executable, "-B", cli, "--func", "ny_open_utc",
                        "--args", json.dumps(_PAYLOAD)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    try:
        return r.returncode, json.loads(r.stdout)
    except Exception:
        return r.returncode, {"status": "unparsable", "raw": r.stdout}


class TestPathSpellingInvariance(unittest.TestCase):
    r"""同一目录,任意写法与任意路径身份,结果必须一致。"""

    def test_P1_string_case_variants_pass(self):
        for label, pp in (("全小写", PKG.lower()), ("大小写互换", PKG.swapcase())):
            with self.subTest(拼写=label):
                rc, out = run_cli(pp)
                self.assertEqual(out.get("status"), "pass",
                                 f"{label} 未被摘除,calendar 遮蔽复发: exit={rc} {out}")
                self.assertEqual(rc, 0)

    def test_P1b_prefix_identities_pass(self):
        r"""`\\?\` / `\\.\` 前缀 —— 这一组才是能证伪 samefile 的判据。"""
        for label, pp in (("长路径前缀 \\?\\", "\\\\?\\" + PKG),
                          ("设备路径前缀 \\.\\", "\\\\.\\" + PKG)):
            with self.subTest(前缀=label):
                rc, out = run_cli(pp)
                self.assertEqual(out.get("status"), "pass",
                                 f"{label} 未被摘除: exit={rc} {out}")
                self.assertEqual(rc, 0)

    def test_P1c_junction_identity_passes_or_skips_loudly(self):
        """P4:junction(目录联接)是**文件系统身份**,字符串比较必漏。"""
        tmp = tempfile.mkdtemp(prefix="jev_junc_")
        link = os.path.join(tmp, "j")
        try:
            made = subprocess.run(["cmd", "/c", "mklink", "/J", link, PKG],
                                  capture_output=True, text=True)
            if made.returncode != 0 or not os.path.exists(link):
                self.skipTest(
                    f"本机无法创建 junction(mklink 返回 {made.returncode}: "
                    f"{made.stdout.strip()} {made.stderr.strip()})—— "
                    f"该路径身份在本机不可测,如实跳过,不得静默通过")
            rc, out = run_cli(link)
            self.assertEqual(out.get("status"), "pass",
                             f"junction 路径未被摘除: exit={rc} {out}")
            self.assertEqual(rc, 0)
        finally:
            if os.path.exists(link):
                subprocess.run(["cmd", "/c", "rmdir", link], capture_output=True)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_P2_unrelated_directories_survive(self):
        r"""★ 真正执行 cli.py,验证非脚本目录未被误伤。

        做法:把 cli.py 复制到 TEMP,在其顶层 import 之前插入一行
        `print('SYSPATH' + json.dumps(sys.path), file=sys.stderr)`,
        跑副本并解析 stderr。这样被测的摘除逻辑**就是 cli.py 里那份**,
        而不是测试自己内联的一份。
        """
        tmp = tempfile.mkdtemp(prefix="jev_p2_")
        try:
            probe = os.path.join(tmp, "cli_probe.py")
            with open(CLI, encoding="utf-8") as fh:
                src = fh.read()
            marker = "from jev_assertions import ("
            self.assertIn(marker, src, "cli.py 结构变了,探针插入点失效")
            injected = ("import json as _j, sys as _s\n"
                        "print('SYSPATH' + _j.dumps(_s.path), file=_s.stderr)\n")
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write(src.replace(marker, injected + marker, 1))
            # 副本放在 TEMP,它的“脚本目录”是 TEMP —— 所以把真 PKG 放进 PYTHONPATH,
            # 让被测逻辑必须认出「PYTHONPATH 里的 PKG」与「脚本所在 TEMP」两个目录,
            # 只该摘掉后者。
            victim = os.path.join(tmp, "keepme")
            os.makedirs(victim, exist_ok=True)
            env_path = os.pathsep.join([PKG, victim])
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            env["PYTHONPATH"] = env_path
            r = subprocess.run([sys.executable, "-B", probe, "--func", "ny_open_utc",
                                "--args", json.dumps(_PAYLOAD)],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", env=env, cwd=ROOT)
            line = [l for l in r.stderr.splitlines() if l.startswith("SYSPATH")]
            self.assertTrue(line, f"探针没输出,说明副本没跑起来:\n{r.stderr}")
            after = json.loads(line[0][len("SYSPATH"):])
            kept = [p for p in after if os.path.normcase(os.path.abspath(p))
                    == os.path.normcase(victim)]
            self.assertTrue(kept,
                            f"非脚本目录 {victim} 被误摘了 —— 摘除逻辑过宽。after={after}")
            # 副本放在 TEMP,故它自己的目录(TEMP)才是「脚本目录」,应当被摘掉。
            # (PKG 是 PYTHONPATH 里的**另一个**目录,必须保留 —— 初版我把这层
            #  关系写反了,断言 PKG 必被摘,是**用例错**不是产品错。)
            gone = [p for p in after if os.path.normcase(os.path.abspath(p))
                    == os.path.normcase(tmp)]
            self.assertFalse(
                gone, f"副本所在目录(脚本目录){tmp} 没被摘掉 —— 摘除逻辑根本没执行。"
                      f" after={after}")
            # 分工说明:「脚本目录被正确摘除」由 P1/P1b/P1c 覆盖(它们以真 cli.py
            # 验证 ny_open_utc 确实变 pass);本项只守「不误伤」这一半。
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_P3_clean_invocation_unaffected(self):
        rc, out = run_cli(None)
        self.assertEqual(out.get("status"), "pass",
                         f"干净环境下 ny_open_utc 应当通过: exit={rc} {out}")
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
