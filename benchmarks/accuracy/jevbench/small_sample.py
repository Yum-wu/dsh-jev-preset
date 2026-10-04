# -*- coding: utf-8 -*-
r"""20 条小样本立即起步(附录 C4)。

## 为什么需要这个模块

依据 Anthropic《How we built our multi-agent research system》:先拿 **20 条**
立即起步,拿到信号再扩样。

本仓此前的习惯是「**攒一个大题集再跑**」。代价是**反馈延迟** ——
要等到 100+ 题跑完才知道判据/口径有没有问题,而那时配额已经花掉。
`docs/appendix-status.md` 的 C4 行记的就是这条缺口。

## 本模块只做「选择 + 预注册」,不跑实验

它要挡住三件事:

1. **选择不可复现** —— 「哪 20 条」必须能由 `(suite, n, seed)` 唯一决定。
   第三方拿同样的三个输入,必须得到**同样的 20 条**(逐字节)。
2. **事后挑样本** —— 预注册块(含 `case_ids` 与 `sha256`)必须在**跑之前**写下。
   否则「挑了 20 条好看的」无法被察觉(R9 预注册)。
3. **静默截断** —— 题量不足 20 时**响亮失败**,不悄悄给 15 条当 20 条用。

## ⚠ 为什么用 sha256 排序键,而不是 `hash()` 或 `random`

- `hash()` 对 `str` 受 `PYTHONHASHSEED` 影响 —— **跨进程不确定**。
  于是「同样的输入」在两次运行里给出**不同的 20 条**,
  而**在同一进程里跑三次看不出来**(这正是本仓反复吃亏的「测量环境 ≠ 默认环境」)。
- `random.sample` 的实现细节在 CPython 版本间变过。

sha256 与二者都无关:纯函数、跨进程、跨版本一致。

## 用法

    python -m jevbench.small_sample --suite suite150.jsonl --n 20 --seed jev-smoke

`--out` 写出预注册块(JSON)。**它应当出现在任何全量跑之前**。
"""
import argparse
import hashlib
import json
import os
import sys

from .grading import load_jsonl

DEFAULT_N = 20
DEFAULT_SEED = "jev-smoke"


def _sort_key(seed, case_id):
    r"""确定性排序键:`sha256(seed + "|" + case_id)`。

    用它而不是 `hash(case_id)` 的理由见模块头(跨进程不确定)。
    """
    h = hashlib.sha256(f"{seed}|{case_id}".encode("utf-8"))
    return h.hexdigest()


def select(cases, n=DEFAULT_N, seed=DEFAULT_SEED):
    r"""确定性选出 n 条。

    - 按 `sha256(seed|id)` 升序取前 n 条 —— 与输入顺序无关;
    - 题量不足 n 时**抛 ValueError**(不静默截断);
    - 同 `(cases, n, seed)` 必得同一结果。
    """
    if len(cases) < n:
        raise ValueError(
            f"题集只有 {len(cases)} 条,少于要求的 {n} 条 —— "
            f"不静默截断。要么补题,要么显式把 n 调小(那是一个需要写下来的决定)。")
    ids = sorted({c["id"] for c in cases})
    if len(ids) != len(cases):
        raise ValueError("题集里有重复 id —— 先查 seed 生成/合并链路")
    order = sorted(ids, key=lambda cid: (_sort_key(seed, cid), cid))
    chosen = set(order[:n])
    return [c for c in sorted(cases, key=lambda c: c["id"]) if c["id"] in chosen]


def prereg(cases, n=DEFAULT_N, seed=DEFAULT_SEED):
    r"""预注册块:**跑之前**写下来的东西。

    `sha256` 覆盖的正是 `case_ids` 的规范形式 —— 于是「跑完之后偷换样本」
    会在复算时被立刻发现。第三方只需 `(suite, n, seed)` 就能重建本块并逐字段比对。
    """
    picked = select(cases, n=n, seed=seed)
    ids = [c["id"] for c in picked]
    payload = json.dumps(ids, ensure_ascii=False, separators=(",", ":"))
    by_cat, by_kind = {}, {}
    for c in picked:
        by_cat[c.get("category", "?")] = by_cat.get(c.get("category", "?"), 0) + 1
        by_kind[c.get("kind", "?")] = by_kind.get(c.get("kind", "?"), 0) + 1
    return {
        "n": n,
        "seed": seed,
        "suite_total": len(cases),
        "suite_version": sorted({c.get("suite_version", "?") for c in cases}),
        "case_ids": ids,
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        # 覆盖度只**报告**,不强制 —— 20 条抽样抽到偏斜是正常风险,
        # 但读的人必须看得见它,否则「20 条全绿」会被当成「判据没问题」。
        "by_category": dict(sorted(by_cat.items())),
        "by_kind": dict(sorted(by_kind.items())),
        # 产出环境。**这不是装饰**:
        #   1. 复算要可复现,第三方得知道当时是什么环境;
        #   2. 它是「判据真的把 hashseed 送进了子进程」的**端到端证据** ——
        #      判据可以断言三次运行分别报告了 0/1/2,而不必去读测试辅助函数的返回值
        #      (那种写法是**自证型**:红队 Round 54 实测,把 env 送达路径改坏
        #       而辅助函数不动,自证型判据仍然全绿)。
        "pythonhashseed": os.environ.get("PYTHONHASHSEED", "<unset>"),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="20 条小样本立即起步 + 预注册块(附录 C4)")
    ap.add_argument("--suite", required=True, help="题集 jsonl")
    ap.add_argument("--n", type=int, default=DEFAULT_N,
                    help=f"抽样条数(默认 {DEFAULT_N} —— 纪律的数字写死在默认值里)")
    ap.add_argument("--seed", default=DEFAULT_SEED, help="抽样种子")
    ap.add_argument("--out", help="把预注册块写到该文件(JSON)")
    args = ap.parse_args(argv)

    block = prereg(load_jsonl(args.suite), n=args.n, seed=args.seed)
    text = json.dumps(block, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
    print(text)
    return 0


# 强制 UTF-8:Windows 默认 stdout/stderr 是 cp936(gbk),**重定向/管道**时中文变乱码,
# 而本仓文本产物一律 UTF-8 —— 第三方 `> out.txt` 后按 UTF-8 读只会得到乱码。
# 三条约束(都由实测逼出来):
#   ① **stdout 与 stderr 都要改** —— 异常路径的 traceback 同样会被重定向进文件;
#   ② 必须容忍 `sys.stdout is None`(pythonw / GUI 宿主)—— 否则兜底分支自己会二次崩溃;
#   ③ 兜底用 `getattr(_s, 'buffer', None)`,不直接取 `.buffer`。
# 守卫:tests/test_tool_stdout_encoding.py
# 包在 `__main__` 里:否则**被 import 时**会改写调用方的 stdout/stderr 编码
# (红队 `77ed8102` 实测:`import tools.evasion_audit` 会把调用方的 latin-1 强制改成 utf-8)。
if __name__ == "__main__":
    for _name in ("stdout", "stderr"):
        _s = getattr(sys, _name, None)
        if _s is None:
            continue
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:                   # pragma: no cover - 兜底老解释器
            import io
            _buf = getattr(_s, "buffer", None)
            if _buf is not None:
                setattr(sys, _name, io.TextIOWrapper(_buf, encoding="utf-8"))
    del _name, _s
    sys.exit(main())
