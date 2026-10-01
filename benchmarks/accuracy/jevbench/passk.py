# -*- coding: utf-8 -*-
"""pass@k / pass^k / 稳定性画像(附录 B3)。

为什么需要这个模块(2026-10-01,依据 Anthropic《Demystifying evals》):
  **工具**用 pass@k(同一题跑 k 次,至少一次对);
  **agent** 用 **pass^k**(同一题跑 k 次,**每次都对**)。
  差别在单次通过率 p 上:pass^k ≈ p^k。文中给的直觉 ——
  单次 0.75 看着不错,(0.75)³ ≈ 0.42,也就是「三次全对」的只有 42%。
  **这个差距在单次实验里完全看不见**,而本仓所有实验此前都是单次(rep 全为 0)。

三条不可混淆的口径(本模块强制区分):
  `pass_at_1`  单次通过率 = 现有 summarize 的 answer_accuracy(不得另起口径)
  `pass_at_k`  至少一次对(工具口径;对 agent 基本无意义,保留只为对照)
  `pass_at_kk` **每次都对**(agent 口径,本模块的重点)
  `stability_profile` 逐题画像:稳定对 / 波动 / 稳定错 / 重复不足

R3(样本独立性):pass^k 的样本是**同一 case_id 的多次 rep**。
跨题把运行次数池在一起算「全对率」是错的 —— 那是聚合通过率,不是一致性。
本模块一律按 case_id 分组;重复不足的题**排除在分母外**而不是按缺次算错。
"""
from collections import defaultdict

__all__ = ["pass_at_1", "pass_at_k", "pass_at_kk", "stability_profile"]


def _group(graded, config=None):
    """按 **(config, seed, case_id)** 分组,返回 {key: [correct, ...]}(按 rep 排序,确定性)。

    ⚠ 2026-10-01 三个维度都必需(红队 5e900042 反证 + 自查):

    `config` —— 缺它会**跨配置池化**,产出语义错误的数:
      `_runs-assert-30.jsonl`(p=0.0312 那份数据)的「重复」其实是 **A1/A2 两臂**,
      不是重复运行。把它们当同一题的两次会报出 `pass^2 = 0.80` ——
      而 0.80 恰等于 **A1 的 pass@1**,即「A1 与 A2 都对」的题数比例,**不是一致性**。
      按 config 拆开后两臂都是 `None`(不可算)。这是本模块最可能造成实际危害的一处。

    `seed` —— 缺它会把 `merge` 出来的多 seed 批(同 case_id、不同 seed)误配成重复运行。

    `case_id` —— 题本身。

    `session_id` 不参与分组,但**由调用方**核验 R3 独立性(k 次必须是不同 session);
    `grade_runs` 现已透传它(此前被丢弃,导致「独立性」只是个假设)。
    """
    by_case = defaultdict(list)
    for g in graded:
        if g.get("kind") == "gate":
            continue          # gate 只判路由,不参与答案正确率
        if config is not None and g.get("config") != config:
            continue          # 显式只看某个配置时,不与其他配置池化
        key = (g.get("config"), g.get("seed"), g["case_id"])
        # ⚠ 只按 rep 排序,**不让 correct 参与排序**:Python 的 sort 是稳定的,
        # `sorted((rep, correct))` 在 rep 相同时会按 correct 排(False < True),
        # 于是「同 rep 的多条」永远把错的排到前面,`[:k]` 恒取到错的那批 ——
        # 系统性低估 pass^k,且完全看不出来(确定性掩盖了偏倚)。
        by_case[key].append((g.get("rep", 0), len(by_case[key]), bool(g["correct"])))
    return {key: [t[2] for t in sorted(rs)] for key, rs in by_case.items()}


def pass_at_1(graded) -> float:
    """单次通过率(每次运行都算一次样本)。

    与 `summarize().answer_accuracy.rate` 同口径 —— 本函数只是把同一口径
    单独暴露出来,便于在报告里与 pass^k 并列显示。
    """
    vals = [bool(g["correct"]) for g in graded if g.get("kind") != "gate"]
    return sum(vals) / len(vals) if vals else 0.0


def pass_at_k(graded, k: int, config=None) -> float:
    """pass@k:每题至少跑 k 次,**至少一次**对的比例(**工具**口径,对 agent 基本无意义)。"""
    prof = stability_profile(graded, k=k, config=config)
    eligible, by_case = prof["eligible"], prof["by_case"]
    if not eligible:
        return 0.0
    return sum(1 for cid in eligible
               if any(_window(by_case[cid], k))) / len(eligible)


def pass_at_kk(graded, k: int, config=None):
    """pass^k:每题至少跑 k 次,**每次都对**的比例(**agent**口径,本模块重点)。

    - `config`:显式指定只看某个配置;为 `None` 时按 `(config, seed, case_id)` 分组,
      **不会**把 A1/A2 两臂池化成「同一题的重复运行」(那是语义错误,见 `_group`)。
    - 重复不足的题**排除在分母外**;若没有任何题跑够 k 次,返回 `None` = 不可算,
      不得返回 `0.0`(会被读成「一道都没全对」)。
    """
    prof = stability_profile(graded, k=k, config=config)
    eligible, by_case = prof["eligible"], prof["by_case"]
    if not eligible:
        return None
    # 与 stability_profile 共用 `_window` —— 分子必须与画像里的分类同一批运行。
    return sum(1 for cid in eligible
               if all(_window(by_case[cid], k))) / len(eligible)


def _window(vals, k):
    """取该题的**前 k 次**运行,并保证判定与 `pass_at_kk` 用的是**同一批**运行。

    ⚠ 2026-10-01 修(红队 5e900042 反证 2:致命):
      原实现里 `stability_profile` 用 `head = vals[:k]` 分类,
      而 `pass_at_kk` 却对 `by_case[cid]` 的**全部** reps 求 `all()` ——
      两者分子不是同一个东西。实测真实 advprem(k=2):
        profile 说 10/12 = 0.833,`pass_at_kk` 返回 8/12 = 0.667。
      同一份数据、两个数、都不报错 —— 比报错更糟。
      现改为**两边共用 `_window`**,定义上不可能再分道扬镳。

      另:`_group` 里 `sorted((rep, correct))` 的 tie-break 在 rep 相同时按 `correct` 排
      (False < True),于是「同 rep 的多条」会**系统性把错的排到前面**,
      `vals[:k]` 恒取到错的那批 → 稳定低估 pass^k。
      现改为**只按 rep 排序、保持输入顺序**(Python sort 稳定),
      不让 correct 参与排序。
    """
    return vals[:k] if len(vals) > k else vals


def stability_profile(graded, k: int, config=None) -> dict:
    """逐题稳定性画像(附录 B3 的「一致性」维度)。

    返回:
      by_case         {(config, seed, case_id): [correct, ...]} 供调用方核对
      stable_pass     前 k 次全对的题
      volatile        前 k 次里有对有错的题
      always_wrong    前 k 次全错的题
      insufficient_reps 运行次数 < k 的题(**不计入上面三类,也不进 pass^k 分母**)
      eligible        次数 ≥ k 的题(即 pass^k 的分母)
      n_gate_excluded 被剔除的 gate 题数(覆盖率可见,别让分母看起来完整)

    为什么必须分出「波动」:全对或全错的题**没有区分力**
    (`difficulty_filter` 筛的就是它们 —— 两者集合在实测中完全相同)。
    """
    by_case = _group(graded, config=config)
    stable_pass, volatile, always_wrong, insufficient = [], [], [], []
    for cid, vals in sorted(by_case.items()):
        if len(vals) < k:
            insufficient.append(cid)
            continue
        head = _window(vals, k)
        if all(head):
            stable_pass.append(cid)
        elif any(head):
            volatile.append(cid)
        else:
            always_wrong.append(cid)
    n_gate = sum(1 for g in graded
                 if g.get("kind") == "gate"
                 and (config is None or g.get("config") == config))
    return {
        "by_case": by_case,
        "k": k,
        "stable_pass": stable_pass,
        "volatile": volatile,
        "always_wrong": always_wrong,
        "insufficient_reps": insufficient,
        "eligible": stable_pass + volatile + always_wrong,
        "n_gate_excluded": n_gate,
    }
