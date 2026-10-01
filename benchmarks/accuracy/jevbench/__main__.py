# -*- coding: utf-8 -*-
"""命令行入口:python -m jevbench <子命令>

  gen     --seed N --out suite.jsonl           生成题集(同 seed 逐字节确定)
  merge   --seeds 1,2,3 --out big.jsonl        合并多 seed 成大题集(去重、校验 id 唯一)
  selftest --suite suite.jsonl                 判分器自检:参考答案必须全对、扰动答案必须全错
  grade   --suite suite.jsonl --runs a.jsonl [--runs b.jsonl ...] [--out report.json]
  compare --suite suite.jsonl --runs ... --a C1 --b C3
  filter  --suite suite.jsonl --runs ... --config C0 [--lo 0.2 --hi 0.8]
"""
import argparse
import json
import sys

from . import SUITE_VERSION
from .cases import build_suite
from .grading import compare, difficulty_filter, grade_case, grade_runs, load_jsonl, reference_text, summarize


def _perturb(case: dict) -> str:
    """把参考答案的第一个字段改错(数值 +1 / 布尔取反 / 字符串加后缀),用于反向自检。

    2026-10-01 修正(附录 A10):gate 分支原先与 `reference_text` 的分支**正好相反** ——
    `reference_text` 是「期望三路 → 3/3」,这里却是「期望三路 → Fast-Pass」。
    两处不一致时,扰动样本可能**恰好等于**参考答案,反向自检形同虚设。
    现在统一:扰动 = 参考答案的**相反**路由,且与 `reference_text` 同一套三值逻辑。
    """
    if case["kind"] == "gate":
        want = case["expected"].get("expect_three_path")
        if want is True:
            route = "断言通过"          # 期望三路 → 扰动成单路(错)
        elif want is False:
            route = "3/3 Independent Consensus"  # 期望单路 → 扰动成三路(错)
        else:
            return ""                    # 不可判定:造不出合法扰动(见 reference_text)
        return f"[JEV: {route}]\n扰动"
    body = dict(case["expected"])
    key = next(iter(body))
    v = body[key]
    if isinstance(v, bool):
        body[key] = not v
    elif isinstance(v, int):
        body[key] = v + 1
    else:
        try:
            from decimal import Decimal
            body[key] = str(Decimal(v) + 1)
        except Exception:
            body[key] = v + "_x"
    return "```json\n" + json.dumps(body, ensure_ascii=False) + "\n```"


def cmd_selftest(suite: list) -> int:
    bad = []
    undecidable = 0
    for c in suite:
        if c["kind"] == "gate" and c["expected"].get("expect_three_path") is None:
            # 口径不明的题**没有**合法参考答案(见 reference_text),不参与对错自检,
            # 但必须计数并显式报告 —— 否则「不可判定」就变成了「悄悄不算」。
            undecidable += 1
            continue
        if not grade_case(c, reference_text(c))["correct"]:
            bad.append(f"参考答案被判错: {c['id']}")
        if grade_case(c, _perturb(c))["correct"]:
            bad.append(f"扰动答案被判对: {c['id']}")
    if grade_case(suite[0], "没有答案块")["correct"]:
        bad.append("缺答案块被判对")
    for b in bad:
        print("FAIL", b)
    if undecidable:
        print(f"提示: {undecidable} 条 gate 题口径不可判定(expect_three_path=None),已跳过对错自检。")
    print(f"selftest: {len(suite)} 题,{'全部通过' if not bad else f'{len(bad)} 项失败'}")
    return 1 if bad else 0


def _runs(paths):
    rows = []
    for p in paths:
        rows.extend(load_jsonl(p))
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jevbench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen"); g.add_argument("--seed", type=int, required=True); g.add_argument("--out", required=True)
    m = sub.add_parser("merge"); m.add_argument("--seeds", required=True,
                                                help="逗号分隔的 seed 列表,如 1,2,3")
    m.add_argument("--out", required=True)
    for name in ("selftest", "grade", "compare", "filter"):
        p = sub.add_parser(name)
        p.add_argument("--suite", required=True)
        if name != "selftest":
            p.add_argument("--runs", action="append", required=True)
        if name == "grade":
            p.add_argument("--out")
        if name == "compare":
            p.add_argument("--a", required=True); p.add_argument("--b", required=True)
        if name == "filter":
            p.add_argument("--config", required=True)
            p.add_argument("--lo", type=float, default=0.2); p.add_argument("--hi", type=float, default=0.8)
    args = ap.parse_args(argv)

    if args.cmd == "gen":
        suite = build_suite(args.seed)
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            for c in suite:
                f.write(json.dumps({**c, "suite_version": SUITE_VERSION, "seed": args.seed}, ensure_ascii=False) + "\n")
        print(f"已生成 {len(suite)} 题 → {args.out}")
        return 0

    if args.cmd == "merge":
        seeds = [int(s) for s in str(args.seeds).split(",") if s.strip()]
        if not seeds:
            print("--seeds 不能为空", file=sys.stderr); return 2
        merged, seen_id, dup_q = [], set(), 0
        seen_q = set()
        for sd in seeds:
            for c in build_suite(sd):
                if c["id"] in seen_id:                       # id 已含 seed,理论上不会撞
                    print(f"id 冲突: {c['id']}", file=sys.stderr); return 1
                seen_id.add(c["id"])
                if c["question"] in seen_q:
                    dup_q += 1                                # 题面重复只告警,不丢弃(便于观察)
                seen_q.add(c["question"])
                merged.append({**c, "suite_version": SUITE_VERSION, "seed": sd})
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            for c in merged:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        print(f"已合并 {len(seeds)} 个 seed → {len(merged)} 题 → {args.out}")
        print(f"唯一 id {len(seen_id)},唯一题面 {len(seen_q)},题面重复 {dup_q}")
        if dup_q:
            print(f"提示: 仍有 {dup_q} 条重复题面(门控题模板有限时会出现),不影响判分但无统计增益。")
        return 0

    suite = load_jsonl(args.suite)
    if args.cmd == "selftest":
        return cmd_selftest(suite)
    graded = grade_runs(suite, _runs(args.runs))
    if args.cmd == "grade":
        report = {"summary": summarize(graded), "rows": graded}
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="\n") as f:
                f.write(text + "\n")
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        # 2026-09-30 事故守卫:某配置「没给答案」占比 >20% 时,其正确率是测量伪影,
        # 不能再被当成能力结论。此处硬失败(退出码 3),逼人先看测量链路。
        bad = [c for c, s in report["summary"].items() if s.get("no_answer", {}).get("untrustworthy")]
        if bad:
            for c in bad:
                na = report["summary"][c]["no_answer"]
                print(f"\n⚠️ 配置 {c}: {na['k']}/{na['n']} ({na['rate']:.1%}) 未给出可判分答案 —— "
                      f"正确率不可信。多半是没等到收敛(如 subagent 仍在后台就收工),"
                      f"请先修测量链路再解读。", file=sys.stderr)
            print("详见 benchmarks/accuracy/MEASUREMENT-BUG-2026-09-30.md", file=sys.stderr)
            return 3
    elif args.cmd == "compare":
        print(json.dumps(compare(graded, args.a, args.b), ensure_ascii=False, indent=2))
    elif args.cmd == "filter":
        keep = difficulty_filter(graded, args.config, args.lo, args.hi)
        print(json.dumps({"kept": len(keep), "case_ids": keep}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    # Windows 控制台/CI 默认 stdout 编码为 cp1252,中文 print 直接抛 UnicodeEncodeError。
    # 与 benchmarks/run_stress_matrix.py 同一处理:强制 UTF-8。
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.exit(main())
