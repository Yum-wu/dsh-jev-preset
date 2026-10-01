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
        # 期望为 None = 题面信号不足,无法从题面复算(见 cases.expected_gate_route)。
        # ⚠ 绝不能把 None 当成「非三路」—— 那等于把「不知道」判成「单路」,
        #    与 R5「无答案与答错必须分开」同类:口径不明必须显式暴露,不能塌成 False。
        if want is None:
            return {"correct": False, "route": route, "no_answer": True,
                    "undecidable": True,
                    "reason": f"{NO_ANSWER}: gate 期望无法从题面复算(expect_three_path=None),"
                              f"不可判对错;路由={route!r}"}
        return {"correct": got == want, "route": route, "no_answer": False,
                "undecidable": False,
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
    """runs 每行 {case_id, config, rep, text, error?, tokens?, elapsed_ms?, seed?, session_id?}。
    运行出错(error 非空)计为错误,并单独统计,不静默丢弃。

    ⚠ 2026-10-01 起透传 `seed` 与 `session_id`(附录 B3 / R3,红队 5e900042 反证):
      原实现只透传 `(case_id, config, rep, tokens, elapsed_ms)`,把这两个字段**丢掉了**,
      导致:
        1. `passk` 的分组键 `(seed, case_id)` 在真实路径上**恒为 `(None, case_id)`** ——
           seed 维度完全惰性,而 `merge` 出来的多 seed 批(同 case_id 不同 seed)会被误配成
           「同一题的重复运行」;
        2. **无法核验 R3 独立性** —— pass^k 的前提是 k 次**独立**运行,
           而唯一能证明独立的是 `session_id` 各不相同;字段丢了,这个前提就只是假设。
      两者都是「看起来算得出、实则不可信」,故必须透传。
    """
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
        out.append({**{k: r.get(k) for k in
                       ("case_id", "config", "rep", "tokens", "elapsed_ms",
                        "seed", "session_id")},
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


def _scotts_pi(n11: int, n10: int, n01: int, n00: int):
    """Scott's π:校正随机一致(2×2,两个判定 × 二值结果)。**退化时返回 None**。

    为什么用它而不是裸 agreement:
      类别极不平衡时,「两边都判同一类」就能拿到很高的 agreement,
      但那不是「真一致」而是「同向的偏见」。π 把随机预期的一致扣掉。

    ⚠ 退化情形(2026-10-01 修正,红队 8c9dff71 反证):
      期望一致率 pe == 1(两方边际都退化到单一类别)时,π 的分母 (1-pe) 为 0,
      **数学上未定义**。原实现返回 0.0,于是「两配置全对」这种**最好**的结果
      被报成 `scotts_pi: 0.0` —— 读起来像「一致里 100% 来自不平衡」,语义完全反了。
      现返回 `None`,由 `compare()` 用 `pi_defined: false` 显式暴露,调用方必须自行处置。

    另注:本仓 `correct` 是二值 bool,2×2 无权重下 **π 与 Cohen's κ 数值恒等**;
    选 π 而非 κ 不影响结论,差别只在多分类/加权(本仓两者都没有)。
    """
    n = n11 + n10 + n01 + n00
    if n == 0:
        return None
    po = (n11 + n00) / n
    pa1 = (n11 + n10) / n   # 第一方判「对」的比例
    pa2 = (n11 + n01) / n   # 第二方判「对」的比例
    pe = pa1 * pa2 + (1 - pa1) * (1 - pa2)
    if abs(1 - pe) < 1e-12:
        return None          # π 在此未定义(pe == 1)
    return (po - pe) / (1 - pe)


def compare(graded: list, a: str, b: str) -> dict:
    """**配置** a vs b 的配对比较(不是两个判分器之间 —— 本仓只有 1 个判分器)。

    ⚠ 定位澄清(2026-10-01,红队 8c9dff71):
      附录 B5 的原始表述是「判分器用 percent agreement 而非 Scott's π」,
      其前提是**存在两个判分器要对齐**(典型:LLM judge vs 人工标注)。
      **本仓不满足该前提** —— `grade_case` 是唯一的判分器,`compare` 的 a/b 是**配置**。
      所以这里的 π 测的是「同一判分器跑两个配置时的**判定可复现度**」,
      而**不是** B5 意义上的效度度量。B5 应标「不可修 / 前置缺失」,
      前置是「建人工标注集 + 建第二判分器」,加指标替代不了前置。
      π 在此仍有真实价值:能抓「两配置共用一份 runs 却被当成两次独立实验」
      「某配置 run 大量 error」这类**链路事故**(此时 π 会异常低)。

    返回**互补**的量:
      1. `mcnemar_p` — 只看**不一致对**的方向性,对「两边一致但都错」完全无感
         (McNemar 的固有盲区,R8 同款问题);
      2. `agreement` — 朴素一致率,类别不平衡时虚高;
      3. `scotts_pi` + `pi_defined` — 校正随机一致后的值;**π 未定义时为 None**
         并由 `pi_defined: false` 暴露,不再谎报 0.0;
      4. `no_answer_pairs` / `n_gate` — 覆盖率与「无答案」对数(R5:无答案 ≠ 答错,
         两者混同会让 π 把「两边都没答」算成「一致」)。

    为什么不返回 `agreement_minus_pi`:它恒等于 `pe(1-po)/(1-pe)`,是 agreement 与 π 的
    严格函数,**零独立信息**(红队 5 万组随机表验证 |差| = 0.0),且在退化场景恒为 1.0,
    反而放大 π=0 那个错误的可读性。YAGNI,去掉。
    """
    def _idx(cfg):
        return {(g["case_id"], g.get("rep")): g for g in graded
                if g["kind"] != "gate" and g["config"] == cfg}

    raw_a, raw_b = _idx(a), _idx(b)
    common = sorted(set(raw_a) & set(raw_b))
    # R5:「没答」与「答错」必须分开 —— 无答案的对**不计入**一致率,单列统计。
    # 否则两边同一条都没答会被算成「一致」,π 完全看不见这个失败模式。
    answerable, no_answer_pairs = [], 0
    for k in common:
        ga, gb = raw_a[k], raw_b[k]
        if ga.get("no_answer") or gb.get("no_answer"):
            no_answer_pairs += 1
            continue
        answerable.append((ga["correct"], gb["correct"]))
    pairs = answerable
    only_a = sum(1 for x, y in pairs if x and not y)
    only_b = sum(1 for x, y in pairs if y and not x)
    n = len(pairs)
    n11 = sum(1 for x, y in pairs if x and y)
    n10 = sum(1 for x, y in pairs if x and not y)
    n01 = sum(1 for x, y in pairs if not x and y)
    n00 = sum(1 for x, y in pairs if not x and not y)
    agreement = (n11 + n00) / n if n else 0.0
    pi = _scotts_pi(n11, n10, n01, n00)
    n_gate = sum(1 for g in graded if g["kind"] == "gate" and g["config"] in (a, b))
    return {"pairs": n, f"only_{a}_correct": only_a, f"only_{b}_correct": only_b,
            "mcnemar_p": round(mcnemar_exact(only_a, only_b), 4),
            "n11": n11, "n10": n10, "n01": n01, "n00": n00,
            "agreement": round(agreement, 6),
            "scotts_pi": None if pi is None else round(pi, 6),
            "pi_defined": pi is not None,
            "no_answer_pairs": no_answer_pairs,
            "n_gate_excluded": n_gate,
            "n11": n11, "n10": n10, "n01": n01, "n00": n00,
            "agreement": round(agreement, 6),
            "n_gate_excluded": n_gate}


def difficulty_filter(graded: list, config: str, lo: float = 0.2, hi: float = 0.8) -> list:
    """用基线配置多次重复的结果筛题:保留正确率在 [lo, hi] 的题(全对/全错题无区分力)。"""
    acc = defaultdict(list)
    for g in graded:
        if g["config"] == config and g["kind"] != "gate":
            acc[g["case_id"]].append(g["correct"])
    return sorted(cid for cid, v in acc.items() if lo <= sum(v) / len(v) <= hi)


def reference_text(case: dict) -> str:
    """把标准答案包装成一条模型回复,用于判分器自检。

    2026-10-01 修正(附录 A10):gate 参考答案原先按旧布尔造路由
    (`expect_three_path` 真 → `3/3 Independent Consensus`,假 → `Fast-Pass`)。
    两处都与现行门控不符:
      1. 布尔现在是**三值**(True/False/**None**),None = 不可判定,不能再当「假」;
      2. 期望**单路**时正解是 `断言通过`(单路 + 真跑复算),不是 `Fast-Pass`
         —— Fast-Pass 是「低危任务单次直出」,与「已跑了断言」是不同的事实。
    用 Fast-Pass 造参考答案,等于让 selftest 认可一条**没有执行断言**的作答。
    """
    if case["kind"] == "gate":
        want = case["expected"].get("expect_three_path")
        if want is True:
            route = "3/3 Independent Consensus"
        elif want is False:
            # 期望单路 + 真跑复算 → persona 的首选路径标识
            route = "断言通过"
        else:
            # 不可判定:造不出合法参考答案,返回空串让 selftest 显式失败,
            # 而不是悄悄造一条会被判错的答案(那会掩盖口径缺口)。
            return ""
        return f"[JEV: {route}]\n参考回复"
    body = dict(case["expected"])
    return "[JEV: Fast-Pass]\n参考答案\n```json\n" + json.dumps(body, ensure_ascii=False) + "\n```"
