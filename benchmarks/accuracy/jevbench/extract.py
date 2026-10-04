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
    """首个 [JEV: ...] 标识的内容;无则 None。

    ⚠⚠ Round 47 修红队 `ca40e241` 实测的残余洞(Round 46 只堵了一条缝):

    捕获组是 `([^\\]】]+?)`(**一个或多个**非括号字符),于是 `[JEV: ]` 里的那个空格
    被捕获 → `.strip()` → **`''`**。而 `''` **不是 `None`** →
    `grading.py` 里 Round 46 刚加的 `if route is None:` 守卫**不触发** →
    `is_three_path('')` 走白名单兜底 → 返回 **True(多路)**。后果有两面:

      · 在**期望三路**的 2 条 gate 题上 `correct=True` —— **白拿分**;
      · 在**期望单路**的 14 条上判成 `correct=False` 且 `no_answer=False` ——
        被记成「**答错**」,而它其实是「**没给出**可判分的路由」(R5 又错了方向)。

    红队原话:**零 token 骗不过 ≠ 一个 token 骗不过。**

    **一个空的声明不是声明**:persona §一 要求第一行给出状态路由标识,
    `[JEV: ]` 没给出任何路由名,等于没给 —— 故返回 `None`,与「无标识」同义。

    R4 影响面(先量后改):历史 61 个 jsonl / 901 条含 `text` 的记录中,
    `extract_route` 返回 `''` 的 **0 条**,`is_three_path` 因此翻转的 **0 条**
    —— 对历史重判**零影响**。

    ⚠⚠ Round 48 补:**上一段修得**不完整**。** `.strip()` 只去 Unicode **空白**,
    去不掉**零宽 / 不可见非空白字符** —— `'\u200b'.isspace() is False`,
    故 `[JEV: \u200b]` 的 `.strip()` 结果是 `'\u200b'`(**非空**),
    `or None` **不触发** → 仍走白名单兜底判「多路」。红队 `93f0497b` 实测 9 个反例:

        \u200b  \u00ad  \u200d  \u200f  \u180e  \u2060  \x00  \ufeff
        [JEV: 【】] → '【'(单个括号,不是名字)

    判据改为 **`_wellformed`**:路由名里必须**至少有一个字母或数字**
    (`str.isalnum()`,中日韩汉字算 alnum)。这既堵住不可见字符,也堵住
    `'【'` 这类「只有标点」的伪名字,同时**不引入白名单**(新增路由名照旧自动判对)。

    R4 影响面(Round 48 再量):历史 26 种 route 取值**全部通过** `isalnum`,
    会被新规则拒绝的记录 **0 条** —— 仍是零影响。
    """
    m = _ROUTE.search(text or "")
    if not m:
        return None
    return _wellformed(m.group(1))


# 第一行行首的**声明**(Round 48)。允许前导空白与前导空行;**行首之后**必须是标识。
# 与 `_ROUTE` 的区别:`_ROUTE` 在**全文任意位置**找首个匹配(=「提及」也算),
# 本式只认**第一行行首**(=「声明」)。
#
# `(?:\*\*|__)?` 两侧的成对强调符:实测历史上有 4 条真实输出写成
# `**[JEV: 3/3 Independent Consensus]**` —— 那是**声明**(markdown 加粗),
# 不是提及。只放行**成对**的 `**` / `__`,**不放行单个 `*`** ——
# 因为 `* [JEV: x]` 是列表项,属「提及」那一侧。
#
# ⚠ Round 49 删掉了**尾部**的 `(?:\*\*|__)?`:它是**死代码**。
# 本式用 `.match()`(前缀锚定,无 `$`),标识之后的字符根本不被消费,
# 所以尾部组有没有都不改变结果 —— 红队 `0354a970` 用 720 组语料实测**差异 0 组**,
# 并把它列为「等价变异 / 测试盲区」。**看着有意义却零作用的正则比不写更坏**,
# 故删。前导的强调符**不能**删,它是真的在起作用(D12「行首-加粗包裹」)。
#
# ⚠ `^\s*`(Round 49 改):原写 `^[ \t]*`,与上面那句 `line.strip()` **不一致** ——
# `str.strip()` 认 Unicode 空白(全角空格 `\u3000`、不换行空格 `\u00a0`),
# 而 `[ \t]` 只认半角。红队 `0354a970` 实测后果是**假阴性**:
# `"\u3000[JEV: 断言通过]"` 因为 `line.strip()` 非空、正则又不匹配 →
# **整篇回复被判「无声明」**。`\s` 与 `str.strip()` 口径一致。
_ROUTE_DECL = re.compile(
    r"^\s*(?:\*\*|__)?[\[【]\s*jev\s*[:：]\s*([^\]】]+?)\s*[\]】]", re.I)

# 前导**不可见但非空白**字符:它们躲过 `str.strip()` 也躲过 `\s`。
# `\ufeff`(UTF-8 BOM)在 Windows 工具链里**很常见**,红队 `0354a970` 实测
# 它会把一个完全合法的首行声明打成「无声明」→ 又一个**假阴性**。
_INVISIBLE_PREFIX = "\ufeff\u200b\u200c\u200d\u200e\u200f\u2060\u180e\u00ad"


def _wellformed(raw: str):
    r"""捕获到的路由名 → 合法的名字,或 `None`。

    **一个空的声明不是声明**(Round 47),而「空」不只是空白(Round 48):
    `.strip()` 去不掉 `\u200b` `\u00ad` `\u200d` `\u200f` `\u180e` `\u2060`
    `\x00` `\ufeff` 这些**零宽/不可见非空白**字符,也去不掉 `【` 这种**只有标点**的伪名字。

    判据:**至少一个字母或数字**(`str.isalnum()`,中日韩汉字算 alnum)。
      · 不引入白名单 —— 新增路由名(如 `Triggered by Test Failure`)照旧自动生效;
      · 只排除「根本没给出名字」的输入。

    ⚠ 注意它**不**排除 `x` / `随便什么` / `0` 这类**垃圾但合法**的名字 ——
    那是 `is_three_path` 的**白名单设计**带来的另一个洞(垃圾名字兜底判「多路」),
    与「空声明」是两回事,归 Round 49。
    """
    name = (raw or "").strip()
    if not name:
        return None
    return name if any(ch.isalnum() for ch in name) else None


def extract_declared_route(text: str):
    r"""**第一行行首**的路由**声明**;没有则 `None`。

    ## 为什么需要它(附录 C5 之 ②,Round 48)

    persona `cordis.patch.yml:38` 承诺「**每条回复第一行必须是状态路由标识**」,
    但 `extract_route` 取的是**全文首个匹配,不辨位置**。于是**正文里任何一处提及**
    都覆盖真正第一行的声明。红队 `93f0497b` 实测,这是本族**最大的游戏面**:

        我不会用 [JEV: 断言通过] 这条路               → 14 条期望单路的 gate 全判对
        我不应该输出 [JEV: 3/3 Independent Consensus] → 2 条期望三路的 gate 判对

    即判分器只验「字符串出现过」,不验「它是**声明**」。这与
    arXiv:2507.08794《One Token to Fool LLM-as-a-Judge》是**同一件事**:
    上一轮(Round 47)修的是**零个** token,这一轮修的是**一个** token。

    ## 为什么**不**直接改 `extract_route`(R4 先量后改)

    `extract_route` 同时喂「成本 / 对照臂归类」。Round 48 实测历史 901 条记录:

        | 候选语义 | route 取值翻转 |
        |---|---|
        | 第一行-行首 | **28 条** |
        | 第一行-任意 | 23 条 |
        | 任意行行首 | 7 条 |

    真实分布:标识**行首** 86 条 / **不在第一行** 23 条 / 第一行但不在行首 5 条 ——
    **25% 的真实输出把标识写在第一行以外**。改它会重分类这些 run 的「是否三路」,
    从而动摇**已定论**的三路增益结论(目标明令不重跑那些实验)。
    故:**只收紧 gate 判分,`extract_route` 的「位置语义」不动**。
    `tests/test_gate_no_route_evidence.py` 的 **D13** 钉死这条边界。

    ⚠ **Round 49 更正(红队 `0354a970` 判我「声称不实」,判得对)**:
    我写过「共享抽取器**不动**」—— **这是假的**。Round 48 我给 `extract_route`
    加了 `_wellformed` 良构性检查。位置语义确实没动(那是 R4 量出来**不能**动的),
    但「不动」这个词**过度声称**了。准确说法是:
    **`extract_route` 的位置语义未改;良构性判据已改(实测影响 0 条)。**
    D13 原先只断言「提及仍能被抽出」,**测不出**这种内部过滤变动 —— 虚假安全感。
    Round 49 已把 D13 加强为逐值钉住 `extract_route` 的完整契约。
    """
    for line in (text or "").split("\n"):
        # 先剥前导不可见字符,再判空 —— 顺序不能反:
        # 一行只由 `\u200b` 组成时 `line.strip()` **非空**(它不是 Python 空白),
        # 会被误当成「第一行有内容但不是声明」而直接返回 None。
        line = line.lstrip(_INVISIBLE_PREFIX)
        if not line.strip():
            continue                      # 允许前导空行(含只由不可见字符组成的行)
        m = _ROUTE_DECL.match(line)
        if not m:
            return None                   # 第一行不是声明 → 后面出现的都只是「提及」
        return _wellformed(m.group(1))
    return None


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
