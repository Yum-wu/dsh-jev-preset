# -*- coding: utf-8 -*-
"""从模型最终回复中抽取答案 JSON 与 JEV 路由标识。"""
import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S | re.I)
# 容错(2026-10-01,红队 af983b62):模型可能写全角冒号/方括号或小写。
# 原正则只认半角 `[JEV: X]`,这些变体一律抽成 None,而 None 默认按**单路**算 ——
# 等于把「跑了三路」记成「单路」,虚报交叉验证,比漏报更危险。
# 故:括号与冒号全半角通吃,标签大小写不敏感。
_ROUTE = re.compile(r"[\[【]\s*jev\s*[:：]\s*([^\]】]+?)\s*[\]】]", re.I)


def extract_answer(text: str):
    """取最后一个可解析为 JSON 对象的 ```json 代码块;无则返回 None(判为格式错误)。"""
    for block in reversed(_FENCE.findall(text or "")):
        try:
            obj = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def extract_route(text: str):
    """首个 [JEV: ...] 标识的内容;无则 None。"""
    m = _ROUTE.search(text or "")
    return m.group(1).strip() if m else None


# 单路路径标识:这些表示**没有**启动多路隔离采样。
#
# 2026-10-01 重写(附录 A3/A4,红队 af983b62 复核):
# persona 已把析取标识 `[JEV: 断言不适用]` 拆成两条(转三路 / 换模型),
# 因为「转三路 = 真多路」与「换模型 = 单路重跑」物理行为相反,二值判分器无法表达析取。
# 本表因此必须与 persona 输出协议**逐条对齐**;`tests/test_route_classification.py`
# 会从 persona 原文抽表交叉核对,新增路由而忘了改这里会先报红。
#
# persona 原文对照:
#   Fast-Pass            低危任务单次直出                          → 单路
#   断言通过              单路算出后真跑代码复算                     → 单路
#   断言不适用-转三路      无法写成断言,已转 ② 三路隔离采样           → **多路**
#   断言不适用-换模型      无法写成断言,改用异构模型重跑(单路)        → **单路**
#   题干结构化后重算        审题类缺陷,列关键条件清单后单路重算        → **单路**(2026-10-01 加,附录 A5)
#   3/3 / 2/3 / 2/3+补派 / Rerank / Triggered by Test Failure      → 多路
#   串行降级-单路由        路由不足,三路被迫串行(并发退化,仍多路)    → 多路
#   串行降级-限流路由      该路由上多路改串行                         → 多路
#   单路未验证            仅 1 路可用,无独立交叉验证                → 单路
_SINGLE_PATH_PREFIXES = (
    "fast-pass",
    "断言通过",
    "断言不适用-换模型",
    "题干结构化后重算",
    "单路未验证",
)


def is_three_path(route) -> bool:
    """路由标识是否表示启动了多路验证。

    返回值含义:True = 走了三路(或多路);False = 单路路径。

    判定顺序(2026-10-01,附录 A3/A4,红队 af983b62 复核):
      1. 无标识 → 单路(没有可观测的多路行为)
      2. 命中显式单路白名单 → 单路
      3. 其余一律算多路 —— **白名单而非黑名单**。

    为什么是这个方向(红队纠正过我一次的相反说法):
      误判为**多路** = 保守(做了交叉验证却记成没做),只是虚高成本。
      误判为**单路** = **虚报交叉验证**,能让根本没做验证的答案骗过 gate 题。
    后者才是「验证剧场」,所以宁可漏报也不虚报 —— 白名单法正是这个方向。
    代价:persona 新增一条**多路**路由时判分器自动判对(无需改);
          新增一条**单路**路由时必须同步白名单,由 tests/test_route_classification.py 兜住。
    """
    if route is None:
        return False
    low = route.lower()
    return not any(low.startswith(p) for p in _SINGLE_PATH_PREFIXES)
