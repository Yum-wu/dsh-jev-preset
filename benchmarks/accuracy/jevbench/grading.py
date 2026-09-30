# -*- coding: utf-8 -*-
"""程序化判分 + 配置间配对比较。不使用任何 LLM 评委。"""
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from .extract import extract_answer, extract_route, is_three_path
from .stats import mcnemar_exact, wilson


def _num_eq(got, want: str) -> bool:
    """数值按 Decimal 比较(\"1.50\" == \"1.5\");题面已规定舍入精度,故要求精确相等。"""
    try:
        return Decimal(str(got).strip().replace(",", "")) == Decimal(want)
    except (InvalidOperation, ValueError):
        return False


def _field_eq(got, want) -> bool:
    if isinstance(want, bool):
        return got is want or (isinstance(got, str) and got.strip().lower() == str(want).lower())
    if isinstance(want, int):
        try:
            return int(got) == want and str(got).strip().lstrip("-").isdigit()
        except (TypeError, ValueError):
            return False
    if isinstance(want, str):
        try:
            Decimal(want)
        except InvalidOperation:
            return isinstance(got, str) and got.strip() == want   # 非数值字符串:精确匹配(日期/状态)
        return _num_eq(got, want)
    return got == want


NO_ANSWER = "NO_ANSWER"


def grade_case(case: dict, text: str) -> dict:
    """返回 {correct, reason, route, no_answer}。gate 题只判路由;其余题只判答案 JSON 中 expected 的键。

    `no_answer` 区分「没给出可判分的答案」与「给了答案但算错」——
    2026-09-30 的测量事故中两者被混为一谈,导致 60% 未收敛样本被计成答错。
    """
    route = extract_route(text)
    if case["kind"] == "gate":
        want = case["expected"]["expect_three_path"]
        got = is_three_path(route)
        return {"correct": got == want, "route": route, "no_answer": False,
                "reason": "ok" if got == want else f"路由={route!r},期望三路={want}"}
    ans = extract_answer(text)
    if ans is None:
        return {"correct": False, "route": route, "no_answer": True,
                "reason": f"{NO_ANSWER}: 无可解析的 ```json 答案块"}
    for key, want in case["expected"].items():
        if key not in ans:
            return {"correct": False, "route": route, "no_answer": False,
                    "reason": f"缺少键 {key}"}
        if not _field_eq(ans[key], want):
            return {"correct": False, "route": route, "no_answer": False,
                    "reason": f"{key}: 得到 {ans[key]!r},期望 {want!r}"}
    return {"correct": True, "route": route, "no_answer": False, "reason": "ok"}


def load_jsonl(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def grade_runs(suite: list, runs: list) -> list:
    """runs 每行 {case_id, config, rep, text, error?, tokens?, elapsed_ms?}。
    运行出错(error 非空)计为错误,并单独统计,不静默丢弃。"""
    by_id = {c["id"]: c for c in suite}
    out = []
    for r in runs:
        case = by_id.get(r["case_id"])
        if case is None:
            raise KeyError(f"结果里的 case_id 不在题集中: {r['case_id']}(题集 seed 不一致?)")
        if r.get("error"):
            g = {"correct": False, "route": None, "no_answer": True,
                 "reason": f"运行失败: {r['error']}"}
        else:
            g = grade_case(case, r.get("text", ""))
        out.append({**{k: r.get(k) for k in ("case_id", "config", "rep", "tokens", "elapsed_ms")},
                    "category": case["category"], "kind": case["kind"],
                    "run_error": bool(r.get("error")), **g})
    return out


def summarize(graded: list) -> dict:
    """按配置汇总:准确率 + Wilson 区间、分题型、运行失败数、错误共识、分歧标注校准。"""
    cfgs = defaultdict(list)
    for g in graded:
        cfgs[g["config"]].append(g)
    report = {}
    for cfg, rows in sorted(cfgs.items()):
        answer_rows = [r for r in rows if r["kind"] != "gate"]
        gate_rows = [r for r in rows if r["kind"] == "gate"]
        k = sum(r["correct"] for r in answer_rows)
        n = len(answer_rows)
        lo, hi = wilson(k, n)
        # 「没答」与「答错」分离:no_answer 占比过高说明测量链路有问题,而非模型能力差。
        no_ans = sum(1 for r in answer_rows if r.get("no_answer"))
        by_cat = defaultdict(lambda: [0, 0])
        for r in rows:
            by_cat[r["category"]][0] += r["correct"]
            by_cat[r["category"]][1] += 1
        consensus = [r for r in answer_rows if r["route"] and "consensus" in r["route"].lower()]
        flagged = [r for r in answer_rows if r["route"] and any(s in r["route"] for s in ("Rerank", "未验证", "2/3", "降级"))]
        tokens = [r["tokens"] for r in rows if isinstance(r.get("tokens"), (int, float))]
        report[cfg] = {
            "answer_accuracy": {"k": k, "n": n, "rate": round(k / n, 4) if n else None,
                                "wilson95": [round(lo, 4), round(hi, 4)]},
            "gate_accuracy": {"k": sum(r["correct"] for r in gate_rows), "n": len(gate_rows)},
            "run_errors": sum(r["run_error"] for r in rows),
            # 2026-09-30 事故守卫:该值 > 20% 时,正确率不可信(多半是没等到收敛)。
            "no_answer": {"k": no_ans, "n": len(answer_rows),
                          "rate": round(no_ans / len(answer_rows), 4) if answer_rows else None,
                          "untrustworthy": bool(answer_rows) and no_ans / len(answer_rows) > 0.2},
            "by_category": {c: f"{a}/{b}" for c, (a, b) in sorted(by_cat.items())},
            "false_consensus": {"wrong": sum(not r["correct"] for r in consensus), "n": len(consensus)},
            "flagged_route_accuracy": {"k": sum(r["correct"] for r in flagged), "n": len(flagged)},
            "mean_tokens": round(sum(tokens) / len(tokens)) if tokens else None,
        }
    return report


def compare(graded: list, a: str, b: str) -> dict:
    """配置 a vs b 的配对比较(只用两边都有结果的答案题;多次重复取 rep 对齐)。"""
    idx = {(g["config"], g["case_id"], g.get("rep")): g["correct"] for g in graded if g["kind"] != "gate"}
    pairs = [(idx[(a, cid, rep)], idx[(b, cid, rep)])
             for (cfg, cid, rep) in idx if cfg == a and (b, cid, rep) in idx]
    only_a = sum(x and not y for x, y in pairs)
    only_b = sum(y and not x for x, y in pairs)
    return {"pairs": len(pairs), f"only_{a}_correct": only_a, f"only_{b}_correct": only_b,
            "mcnemar_p": round(mcnemar_exact(only_a, only_b), 4)}


def difficulty_filter(graded: list, config: str, lo: float = 0.2, hi: float = 0.8) -> list:
    """用基线配置多次重复的结果筛题:保留正确率在 [lo, hi] 的题(全对/全错题无区分力)。"""
    acc = defaultdict(list)
    for g in graded:
        if g["config"] == config and g["kind"] != "gate":
            acc[g["case_id"]].append(g["correct"])
    return sorted(cid for cid, v in acc.items() if lo <= sum(v) / len(v) <= hi)


def reference_text(case: dict) -> str:
    """把标准答案包装成一条模型回复,用于判分器自检。"""
    if case["kind"] == "gate":
        route = "3/3 Independent Consensus" if case["expected"]["expect_three_path"] else "Fast-Pass"
        return f"[JEV: {route}]\n参考回复"
    body = dict(case["expected"])
    return "[JEV: Fast-Pass]\n参考答案\n```json\n" + json.dumps(body, ensure_ascii=False) + "\n```"
