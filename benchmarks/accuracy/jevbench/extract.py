# -*- coding: utf-8 -*-
"""从模型最终回复中抽取答案 JSON 与 JEV 路由标识。"""
import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S | re.I)
_ROUTE = re.compile(r"\[JEV:\s*([^\]]+)\]")


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


def is_three_path(route) -> bool:
    """路由标识是否表示启动了多路验证(非 Fast-Pass)。"""
    return route is not None and not route.lower().startswith("fast-pass")
