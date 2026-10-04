# -*- coding: utf-8 -*-
r"""20 条小样本立即起步(附录 C4)的判据。

## 缺陷

`docs/appendix-status.md` 的 C4 行:

> **C4** 无「20 条小样本立即起步」纪律(本仓习惯是攒大题集)
> 依据:Anthropic《How we built our multi-agent research system》

**本仓此前的习惯是攒一个大题集再跑。** 代价是反馈延迟 ——
要等到 100+ 题跑完才知道判据/口径有没有问题,而那时配额已经花掉。

## ⚠ 为什么这条不能只写成 persona 文本

最省事的「修复」是在 persona 里加一句「请先用 20 条起步」,再加一个
`assert "20 条" in persona` 的测试。**那正是本目标要清的验证剧场**:
测试钉的是**字符串存在**,不是**行为**;而行为(先跑 20 条)发生在
一个测试看不见的地方。

所以本轮把它做成**可执行能力 + 可机械核对的预注册块**:

- `select(cases, n, seed)` —— 确定性抽样,`(suite, n, seed)` 唯一决定结果;
- `prereg(...)` —— 预注册块,含 `case_ids` 与 `sha256`,
  **必须在全量跑之前写下**,第三方可独立重建并逐字段比对。

## 判据

1. **S1 跨进程确定性** —— 三次**独立子进程**必须给出同样的 20 条与同样的 sha256。
   (关键:同进程内跑三次**测不出** `hash()` 的 `PYTHONHASHSEED` 随机化。)
2. **S2 真子集** —— 选中的必须是全集的真子集,且条数恰好 n。
3. **S3 不静默截断** —— 题量不足 n 时必须**响亮失败**。
4. **S4 种子真的起作用** —— 换 seed 必须换出不同的集合(否则 seed 是装饰)。
5. **S5 预注册块自洽** —— `sha256` 必须覆盖**恰好** `case_ids` 那批。
6. **S6 默认 n = 20** —— 纪律的数字写死在默认值里,不靠文档。
7. **S7 输入顺序无关** —— 打乱输入顺序,结果必须不变。
8. **S8 可证伪** —— 把选择换成 `hash()` 后,S1 必须红。
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACC = os.path.join(ROOT, "benchmarks", "accuracy")
SUITE = os.path.join(ACC, "suite150.jsonl")


def _env(hashseed=None):
    r"""子进程环境。

    ⚠ **必须显式处理 `PYTHONHASHSEED`,不能只 pop 编码相关的两个变量。**

    Round 54 红队 `0db255bd` 实测并被我复现:`hash(str)` 的结果由
    `PYTHONHASHSEED` 决定。宿主一旦设了它(哪怕只是为了可复现构建),
    **S1 就测不出跨进程不确定性** —— 实测 `PYTHONHASHSEED=0/1/7/12345`
    四种取值下,把 `_sort_key` 换成 `hash()` 的实现 **S1 全绿**。

    处置不是「pop 掉就完事」:
      - `hashseed=None` → pop(让子进程用 Python 默认的**随机** seed);
      - `hashseed="0"` → **显式设死**,用于「故意换 seed 看结果变不变」。
    后者才是让判据**与宿主环境无关**的做法 —— 不靠随机性,靠**受控变化**。
    """
    e = os.environ.copy()
    for k in ("PYTHONIOENCODING", "PYTHONUTF8", "PYTHONHASHSEED"):
        e.pop(k, None)
    if hashseed is not None:
        e["PYTHONHASHSEED"] = str(hashseed)
    return e


def _run_cli(args, cwd=ACC, hashseed=None):
    return subprocess.run([sys.executable, "-B", "-X", "utf8",
                           "-m", "jevbench.small_sample"] + args,
                          cwd=cwd, capture_output=True, env=_env(hashseed))


def _block(hashseed=None, **kw):
    a = ["--suite", SUITE]
    for k, v in kw.items():
        a += ["--" + k, str(v)]
    r = _run_cli(a, hashseed=hashseed)
    assert r.returncode == 0, (r.stderr or b"").decode("utf-8", "replace")[-600:]
    return json.loads((r.stdout or b"").decode("utf-8"))


class TestSmallSample(unittest.TestCase):

    def test_S1_deterministic_across_processes(self):
        r"""三次**独立子进程**必须给出同样的 20 条与同样的 sha256。

        ⚠ 必须在子进程里跑。`hash(str)` 受 `PYTHONHASHSEED` 影响 ——
        **同一进程内跑三次是完全确定的**,所以同进程测试会漏掉这个坑,
        而真实使用(每次一个新进程)会得到不同的 20 条。
        这正是本仓记过的「测量环境 ≠ 默认环境」。

        ⚠ **三次跑的是三个不同的 `PYTHONHASHSEED`(0/1/2),不是三次随机。**
        Round 54 前这里跑的是「三次默认环境」—— 那样只要宿主**没设**
        `PYTHONHASHSEED`,三次的子进程 seed 各自随机,确实能测出 `hash()`;
        但宿主**一旦设死**它,三次就完全一样,判据静默失效(红队实测:
        `PYTHONHASHSEED=0/1/7/12345` 下 `hash()` 实现 S1 全绿)。

        改成**受控变化**之后,这条判据**不再依赖宿主环境**:
        任何用 `hash()` 的实现,在这三个 seed 下必然给出不同的结果。
        """
        blocks = [_block(hashseed=str(i), n=20, seed="jev-smoke")
                  for i in range(3)]
        ids = [b["case_ids"] for b in blocks]
        self.assertEqual(ids[0], ids[1], "PYTHONHASHSEED=0 与 1 结果不同")
        self.assertEqual(ids[1], ids[2], "PYTHONHASHSEED=1 与 2 结果不同")
        sha = {b["sha256"] for b in blocks}
        self.assertEqual(len(sha), 1, f"三次的 sha256 不一致:{sha}")
        # ⚠ **端到端送达证据**:三次的子进程必须**自报**分别看到了 0/1/2。
        # 不能改成读 `_env()` 的返回值 —— 那是自证型(红队 Round 54 实测:
        # 把 env 送达路径改坏而 `_env()` 不动,自证型判据仍全绿)。
        # 这里断言的是**子进程真的报告出来的环境**,中间任何一环坏了都会红。
        self.assertEqual(
            [b["pythonhashseed"] for b in blocks], ["0", "1", "2"],
            "三次子进程自报的 PYTHONHASHSEED 不是 0/1/2 —— "
            "env 的送达路径有问题,或者 prereg 没有如实记录产出环境")
        # R4 守卫:先确认「测到了」—— 20 条不能是空的
        self.assertEqual(len(ids[0]), 20, "抽样条数不是 20,本条判据空转")

    def test_S2_selection_is_a_true_subset(self):
        with io.open(SUITE, encoding="utf-8") as f:
            all_ids = {json.loads(l)["id"] for l in f if l.strip()}
        b = _block(n=20, seed="jev-smoke")
        got = b["case_ids"]
        self.assertEqual(len(got), 20)
        self.assertEqual(len(set(got)), 20, "选出的 20 条里有重复")
        self.assertTrue(set(got) <= all_ids,
                        f"选出了全集里没有的 id:{set(got) - all_ids}")
        self.assertEqual(b["suite_total"], len(all_ids), "suite_total 与题集不符")

    def test_S3_does_not_silently_truncate(self):
        r"""题量不足时必须**响亮失败**,不悄悄给 15 条当 20 条用。

        静默截断是本仓记过的「含糊的 count 给出一个看似权威的错数」的同一形态:
        下游看到「n=20 的抽样」,实际只有 15 条,而**没有任何地方会说**。
        """
        small = os.path.join(tempfile.gettempdir(), f"jev_r54_small_{os.getpid()}.jsonl")
        with io.open(SUITE, encoding="utf-8") as f:
            lines = [l for l in f if l.strip()][:5]
        with io.open(small, "w", encoding="utf-8", newline="\n") as f:
            f.write("".join(lines))
        self.addCleanup(lambda: os.path.exists(small) and os.remove(small))
        r = _run_cli(["--suite", small, "--n", "20"])
        self.assertNotEqual(r.returncode, 0, "5 条题集配 n=20 竟然成功了 —— 静默截断")
        err = (r.stderr or b"").decode("utf-8", "replace")
        self.assertIn("少于", err, f"失败信息没说清原因:{err[-400:]}")

    def test_S4_seed_actually_matters(self):
        r"""换 seed 必须换出**不同**的集合 —— 否则 seed 是装饰。

        没有这一条,一个「永远返回前 20 条」的实现能骗过 S1/S2/S5 全部判据。
        """
        a = _block(n=20, seed="jev-smoke")["case_ids"]
        b = _block(n=20, seed="another-seed")["case_ids"]
        self.assertNotEqual(a, b, "换 seed 后选出的 20 条完全一样 —— seed 没起作用")
        # ⚠ **必须同时比集合**。只比列表会漏掉「seed 只影响排序、不影响集合」的实现:
        # 那种实现每次给出**同一批题**、只是顺序不同,`a != b` 成立 → 本条绿。
        # 红队 `0db255bd` 实测:该变异下**全量 26 个测试全绿**,
        # 而且 `prereg.sha256` 会**谎报样本变了**(sha 覆盖的是列表,顺序不同 sha 就不同)。
        # 「预注册块谎报样本变化」比「seed 没起作用」更坏 —— 它是**主动**误导。
        self.assertNotEqual(
            set(a), set(b),
            "换 seed 后**选出的题集**完全相同(只是顺序变了)—— "
            "seed 只影响了排序,没有影响选哪些题;而 prereg 的 sha256 会因此谎报样本变了")

    def test_S5_prereg_block_is_self_consistent(self):
        r"""`sha256` 必须覆盖**恰好** `case_ids` 那批。

        预注册块的全部作用就是「事后偷换样本能被发现」。
        若 sha256 覆盖的不是 case_ids,这条防线就是空的。
        """
        import hashlib
        b = _block(n=20, seed="jev-smoke")
        payload = json.dumps(b["case_ids"], ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
        self.assertEqual(hashlib.sha256(payload).hexdigest(), b["sha256"],
                         "预注册块的 sha256 与 case_ids 不自洽")
        # 覆盖度必须被报告出来(抽偏了要看得见,否则「20 条全绿」会被误读)
        self.assertEqual(sum(b["by_category"].values()), 20)
        self.assertEqual(sum(b["by_kind"].values()), 20)

    def test_S6_default_n_is_twenty(self):
        r"""纪律的数字必须写死在**默认值**里 —— 不靠文档、不靠调用方记得传。

        若默认是「全部」,那么忘了传 `--n` 的人就会把整个大题集跑掉,
        而这条纪律的意义正是「先跑小的」。
        """
        b = _block()                       # 故意不传 --n
        self.assertEqual(b["n"], 20, "默认 n 不是 20")
        self.assertEqual(len(b["case_ids"]), 20)

    def test_S7_input_order_does_not_matter(self):
        r"""打乱输入顺序,结果必须不变 —— 否则「确定性」只是「当前文件顺序下确定」。"""
        import random
        with io.open(SUITE, encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
        shuffled = lines[:]
        random.Random(12345).shuffle(shuffled)
        p = os.path.join(tempfile.gettempdir(), f"jev_r54_shuffled_{os.getpid()}.jsonl")
        with io.open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write("".join(shuffled))
        self.addCleanup(lambda: os.path.exists(p) and os.remove(p))
        a = _block(n=20, seed="jev-smoke")["case_ids"]
        r = _run_cli(["--suite", p, "--n", "20", "--seed", "jev-smoke"])
        self.assertEqual(r.returncode, 0)
        b = json.loads((r.stdout or b"").decode("utf-8"))["case_ids"]
        self.assertEqual(a, b, "打乱输入顺序后选出的 20 条变了")

    def test_S8_guard_is_falsifiable(self):
        r"""可证伪:把选择换成 `hash()`,S1 必须红。

        这是本文件最重要的一条 —— 它证明 S1 **真的在测跨进程确定性**,
        而不是在测「这台机器上恰好稳定」。

        做法:在镜像里把 `_sort_key` 换成 `hash(f"{seed}|{case_id}")`,
        **语法保持**(只改值不改结构 —— Round 50 的 T2 就是栽在删行造出
        `SyntaxError` 上,把语法崩溃当成了行为证伪)。
        """
        mirror = os.path.join(tempfile.gettempdir(), f"jev_r54_mirror_{os.getpid()}")
        if os.path.exists(mirror):
            shutil.rmtree(mirror, ignore_errors=True)
        shutil.copytree(ROOT, mirror,
                        ignore=shutil.ignore_patterns(".git", "node_modules",
                                                      "tmp_jev_path1"))
        p = os.path.join(mirror, "benchmarks", "accuracy", "jevbench",
                         "small_sample.py")
        with io.open(p, encoding="utf-8") as f:
            src = f.read()
        old = '    h = hashlib.sha256(f"{seed}|{case_id}".encode("utf-8"))\n    return h.hexdigest()'
        new = '    return str(hash(f"{seed}|{case_id}"))'
        self.assertIn(old, src, "变异锚点没找到 —— 本条自曝")
        with io.open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(src.replace(old, new, 1))
        # 语法必须仍然完好,否则又变成「崩溃冒充检出」
        import ast
        with io.open(p, encoding="utf-8") as f:
            ast.parse(f.read())
        # ⚠ **在固定 PYTHONHASHSEED 下证伪** —— 这正是 Round 54 的修复点。
        # 用默认环境证伪是**靠运气**:宿主没设 hashseed 时子进程 seed 随机,能测出来;
        # 宿主设死了就测不出来(红队实测 4 种取值全绿)。
        # 固定成 7 之后,证伪成立与否**只取决于 S1 自己的设计**,与宿主无关。
        r = subprocess.run(
            [sys.executable, "-B", "-X", "utf8",
             "tests/test_small_sample.py", "-k",
             "test_S1_deterministic_across_processes"],
            cwd=mirror, capture_output=True, env=_env(hashseed="7"))
        out = ((r.stdout or b"") + (r.stderr or b"")).decode("utf-8", "replace")
        shutil.rmtree(mirror, ignore_errors=True)
        self.assertIn("Ran ", out, f"子进程没跑到框架(崩溃冒充检出):{out[-400:]}")
        self.assertNotEqual(
            r.returncode, 0,
            "把选择换成 hash() 后 S1 仍然全绿 —— S1 没有在测跨进程确定性")


    def test_S9_env_does_not_leak_hashseed(self):
        r"""`_env()` 不得把宿主的 `PYTHONHASHSEED` 漏给子进程。

        Round 54 红队 `0db255bd` 实测:旧 `_env()` 只 pop
        `PYTHONIOENCODING`/`PYTHONUTF8`,**漏了 `PYTHONHASHSEED`** ——
        于是整族 S 判据的有效性**挂在宿主环境上**。
        **判据依赖宿主环境 = 判据在别的机器上可能是空转的。**

        本条直接断言 `_env()` 的契约(不依赖任何子进程),
        并顺带钉住「显式传入时必须真的设上」这个反向契约。
        """
        old = os.environ.get("PYTHONHASHSEED")
        try:
            os.environ["PYTHONHASHSEED"] = "424242"
            self.assertNotIn(
                "PYTHONHASHSEED", _env(),
                "宿主设了 PYTHONHASHSEED,_env() 把它漏给了子进程 —— "
                "S1 的跨进程确定性判据会因此静默失效")
            self.assertEqual(_env(hashseed="7")["PYTHONHASHSEED"], "7",
                             "显式传入 hashseed 时没有真的设上")
        finally:
            if old is None:
                os.environ.pop("PYTHONHASHSEED", None)
            else:
                os.environ["PYTHONHASHSEED"] = old

    def test_S6b_library_default_is_twenty(self):
        r"""纪律的 20 必须写在**库默认值**里,不只是 CLI 默认值里。

        红队 `0db255bd` 实测:S6 只走 CLI(`_block()` 不传 `--n`)。
        把函数签名的默认改成 `n=None`(等价于「全部」)后,
        `select(cases)` 直调返回 **231 条**,而 S6 **仍然是绿的** ——
        **CLI 的 argparse default 挡住了函数默认值,判据只守了一层。**
        """
        sys.path.insert(0, ACC)
        try:
            import importlib
            m = importlib.import_module("jevbench.small_sample")
            cases = m.load_cases(SUITE) if hasattr(m, "load_cases") else None
            if cases is None:
                with io.open(SUITE, encoding="utf-8") as f:
                    cases = [json.loads(l) for l in f if l.strip()]
            picked = m.select(cases)          # 故意不传 n / seed
            self.assertEqual(
                len(picked), 20,
                f"库默认抽样条数是 {len(picked)},不是 20 —— "
                f"纪律只写进了 CLI 的 argparse default,没写进函数默认值")
        finally:
            sys.path.remove(ACC)
            sys.modules.pop("jevbench.small_sample", None)


    def test_S10_n_argument_actually_changes_the_count(self):
        r"""`--n` 必须真的改变条数 —— 判据族此前**从不以 n≠20 调用**。

        红队 `0db255bd` 实测:把 `select` 改成「忽略 n、恒返 20 条」后,
        **10/10 全绿** —— 因为整族判据都只跑 n=20。
        「纪律的数字是 20」被遵守了,但**模块自声明的契约(`--n` 可变)没人验**。

        这是「判据只覆盖自己关心的那一个值」的典型:
        它证明了「默认是 20」,却没证明「20 是个**参数**而不是**常量**」。
        """
        for want in (5, 15, 33):
            b = _block(n=want, seed="jev-smoke")
            self.assertEqual(
                b["n"], want,
                f"--n {want} 报告的 n 是 {b['n']}")
            self.assertEqual(
                len(b["case_ids"]), want,
                f"--n {want} 实际给出 {len(b['case_ids'])} 条 —— "
                f"`--n` 没有生效(可能被实现忽略)")

    def test_S9b_hashseed_is_actually_delivered_to_the_child(self):
        r"""S9 的**行为版**:不读 `_env()` 的返回值,而是**观察子进程真的收到了什么**。

        为什么需要这一条:红队 `0db255bd` 实测 S9 是**自证型** ——
        把 `_run_cli` 改成 `env=_env("5")`(子进程全 pin 成 5、`_env()` 本身没动),
        **S9 仍然全绿**,而 `hash()` 实现就此逃过 S1。
        (`S8` 是这条链的兜底 —— 它确实红了,所以**整套**没有失守;
        但 **S9 单独**证明不了它声称的事。)

        修法:让**子进程自己**把看到的 `PYTHONHASHSEED` 打印出来。
        断言的对象从「辅助函数的返回值」变成「子进程的实际环境」——
        中间任何一环(参数透传、subprocess 调用)被改都会红。
        """
        probe = "import os;print(os.environ.get('PYTHONHASHSEED','<unset>'))"
        for want in ("0", "7", None):
            r = subprocess.run([sys.executable, "-B", "-c", probe],
                               capture_output=True, env=_env(hashseed=want))
            got = (r.stdout or b"").decode("utf-8", "replace").strip()
            exp = "<unset>" if want is None else want
            self.assertEqual(
                got, exp,
                f"子进程实际收到的 PYTHONHASHSEED 是 {got!r},期望 {exp!r} —— "
                f"env 的**送达路径**有问题,不只是 `_env()` 的返回值")


if __name__ == "__main__":
    unittest.main(verbosity=2)
