# -*- coding: utf-8 -*-
"""
seed 结构自检(附录 C2)。

见 `tests/test_seed_structure.py` 的文件头 —— 那里写清了缺口来源与判据。
本模块只做三件事:确定性、片段齐全、答案协议一致。

⚠ 它**不是**内容正确性检查。「题面里的数算得对不对」由 `solve.py` 与断言库负责;
本模块只管**结构**:同样的输入是否产出同样的结构、该在的片段在不在、
题面要的键与答案给的键是否一致。
"""
import random
import re
import sys

from . import cases

# 题面里必须出现的「锚点」—— 取自各生成器共有的协议与约束措辞。
# 用**词**而不是完整句子:句子一改这里就全红,那是脆弱的锁;而这些词一旦消失,
# 题目就不再是可判分的题。
REQUIRED_FRAGMENTS = [
    "【作答格式",          # ANSWER_PROTOCOL 的段首
    "```json",             # 协议要求代码块
]

# 注:这里原有 `_KEY_RE = re.compile(r'"([a-z_]+)":\s*"<')`,是 Round 45 删除 `_skeleton()`
# 时漏下的**孤儿常量** —— 全仓零调用(`_proto_keys` 里把两种写法内联了)。
# 红队 73b9a722 查出。已删。


def _gen_names():
    return sorted(n for n in dir(cases) if n.startswith("gen_"))


def _proto_keys(text):
    r"""从题面里抠出 `_proto(...)` 声明的键 —— **同时认带引号与不带引号两种写法**。

    两种形态在本仓都存在:
        "mdd_pct": "<最大回撤%>"      ← 带引号(字符串)
        "peak_index": <整数>          ← 不带引号(整数)
    初版只认前者、后版只认后者,各造成一次**误报**。
    """
    idx = text.find("【作答格式")
    seg = text[idx:] if idx >= 0 else text
    keys = set(re.findall(r'"([a-z_]+)":\s*<', seg))
    keys |= set(re.findall(r'"([a-z_]+)":\s*"<', seg))
    return keys


def _type_declaration_mismatch(text, ans):
    """协议里 `<整数>`(无引号)声明该键为**字符串**,但实际给了 int → 不一致。

    这是本模块在本轮查出的**真缺陷**:`ANSWER_PROTOCOL` 明写
    「所有数值一律写成字符串(如 "123.45")」,而 `gen_mdd` 的协议段写了
    `"peak_index": <整数>`(无引号),实际 `ans` 也确实给的是 int。
    协议与实现同时偏离了「一律字符串」这条,判分器若严格按协议解析就会判错,
    而自优化循环不会察觉 —— 正是 C2 描述的「根因 0 次归因」。
    """
    idx = text.find("【作答格式")
    if idx < 0 or not isinstance(ans, dict):
        return []
    seg = text[idx:]
    bad = []
    for m in re.finditer(r'"([a-z_]+)":\s*<([^>]*)>', seg):
        key, declared = m.group(1), m.group(2)
        if key not in ans:
            continue
        # ⚠ 我第一版把这里写反了(`"整数" not in declared`),导致 `<整数>` 反而
        #   **不**要求字符串 —— 而协议恰恰明写「所有数值一律写成字符串」。
        #   所以 `<整数>` 是**与全局规则矛盾**的点,不是「合法声明整数」。
        wants_string = True          # 全局规则:一律字符串
        value = ans[key]
        if wants_string and not isinstance(value, str):
            bad.append({"key": key, "declared": declared,
                        "actual_type": type(value).__name__,
                        "note": "协议声明 <整数> 与全局「一律写成字符串」矛盾"})
    return bad


def audit_generators(n_per_gen=3, base_seed=20261001):
    """逐个生成器做结构审计,返回一条记录一个生成器。

    ⚠⚠ **刻意不做「结构漂移」检测**(我试过两次,都只能产出误报,故删除):

      设想一:比较**不同 seed** 的题面骨架 → 误报 5/10 个生成器。
              因为题面内容本就依赖 `rng`(如 `gen_tick` 的 BUY / SELL 两个分支),
              不同 seed 句式不同是**正常**的。
      设想二:比较**同 seed、不同题号 i** 的骨架 → 同样误报,
              因为同一个 rng 在不同 i 上也会走到不同分支。

      也就是说,「骨架应保持一致」这个前提**在本仓不成立**,
      而一个前提不成立的判据只会持续误报 —— 那比没有判据更糟
      (它会让人开始习惯红色)。真正的确定性检查是 `nondeterministic`:
      **同一个 seed 跑两次必须逐字节相同**,这个前提是成立的。
      故本模块只做:确定性 + 片段齐全 + 键一致 + 类型声明一致。
    """
    out = []
    for name in _gen_names():
        fn = getattr(cases, name)
        nondeterministic = False
        key_mismatch = None
        type_mismatch = []
        missing_fragment = None
        got_sample = False
        last_q = last_a = None
        for k in range(n_per_gen):
            seed = base_seed + k
            try:
                q1, a1 = fn(random.Random(seed), k)
                q2, a2 = fn(random.Random(seed), k)
            except Exception as e:                      # 生成器本身坏了
                nondeterministic = True
                missing_fragment = f"{type(e).__name__}: {e}"
                break
            if q1 != q2 or a1 != a2:
                nondeterministic = True
            if any(f not in q1 for f in REQUIRED_FRAGMENTS):
                missing_fragment = next(f for f in REQUIRED_FRAGMENTS if f not in q1)
            got_sample = True
            last_q, last_a = q1, a1
        if got_sample:
            declared = _proto_keys(last_q)
            actual = set(last_a.keys()) if isinstance(last_a, dict) else set()
            if declared and declared != actual:
                key_mismatch = {"declared": sorted(declared), "actual": sorted(actual)}
            type_mismatch = _type_declaration_mismatch(last_q, last_a)
        out.append({
            "generator": name,
            "nondeterministic": nondeterministic,
            "key_mismatch": key_mismatch,
            "type_mismatch": type_mismatch,
            "missing_fragment": missing_fragment,
        })
    return out


def audit_all():
    """跑完整审计,返回人类可读文本。"""
    report = audit_generators()
    lines = ["seed 结构自检(附录 C2)", "=" * 40]
    bad = 0
    for r in report:
        flags = []
        if r["nondeterministic"]:
            flags.append("非确定性")
        if r["key_mismatch"]:
            flags.append(f"键不一致 {r['key_mismatch']}")
        if r.get("type_mismatch"):
            flags.append(f"**类型声明不一致** {r['type_mismatch']}")
        if r["missing_fragment"]:
            flags.append(f"缺片段 {r['missing_fragment']!r}")
        if flags:
            bad += 1
            lines.append(f"  ✗ {r['generator']}: {', '.join(flags)}")
        else:
            lines.append(f"  ✓ {r['generator']}")
    lines.append("-" * 40)
    lines.append(f"{len(report)} 个生成器,{bad} 个有问题")
    return "\n".join(lines)


if __name__ == "__main__":
    # 强制 UTF-8:Windows 默认 stdout/stderr 是 cp936(gbk),**重定向/管道**时中文变乱码,
    # 而本仓文本产物一律 UTF-8 —— 第三方 `> out.txt` 后按 UTF-8 读只会得到乱码。
    # 守卫:tests/test_tool_stdout_encoding.py(T3 棘轮)
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
    print(audit_all())
