# -*- coding: utf-8 -*-
"""
成本–准确率**帕累托前沿**的强制报告格式(附录 B4,依据 arXiv:2407.01502《AI Agents That Matter》)。

## 为什么要有这个模块

B4 的原始缺口:「无「成本–准确率帕累托前沿」的**强制报告格式**」。
本仓的历史做法是**每个实验各写各的表**,于是:

- 成本单位不统一(`×2.0` / `×20` / 平均 token 三种混用);
- 准确率单位不统一(题数 `6→12` / 百分比 `80.0%` / 相对增益 `+89pp`);
- 样本量与 Wilson 区间时有时无 —— 而 R10 要求「通过率一律报 Wilson 95%」;
- **最贵的方法与最有效的方法被并列成一张表,读者无法一眼看出性价比拐点在哪**。

`benchmarks/accuracy/MEASUREMENT-BUG-2026-09-30.md` 记的就是这类事故的近亲:
数字一旦散落各处,就有人把 `hit = True` 的恒等式当成测量值。

## 本模块的职责(仅此三件,不做别的)

1. **统一单位** —— 准确率一律用百分比 + Wilson 95% 区间;成本一律用「相对基线的倍数」。
2. **判定帕累托前沿** —— 方法 M 在前沿上,当且仅当**不存在**另一个方法 N
   同时满足 `cost_N <= cost_M` 且 `accuracy_N >= accuracy_M`,且至少有一项严格更优。
3. **输出固定 Markdown 表** —— 由 `render_markdown()` 生成,列名与顺序**不可变**,
   由 `tests/test_pareto_report.py` 逐字锁定。

## 判据里最容易被糊弄的一条

**样本量必须显式**。准确率 100% 在 n=2 与 n=30 上完全不是一回事 ——
本仓 `EXP-F` 里 `12→12` 与 `30/30` 都被写成「100%」。故 `Method.n` 是**必填**,
且报告会同时打印 `n` 与 Wilson 区间,让读者能自己判断这个 100% 值不值得信。
"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Method:
    """一个可比较的干预手段。单位已由本模块强制,不接受混用。"""

    name: str
    accuracy: float          # 准确率,0–100(百分比)
    cost: float             # 成本倍数,相对基线;必须 >= 1.0
    n: int                  # 样本量,必填 —— 100% 在 n=2 与 n=30 上不是一回事
    evidence: str           # 证据出处,必填且不得为空
    note: str = ""          # 补充说明(如「增益不显著」)
    _wilson: Optional[tuple] = None

    def __post_init__(self):
        if not self.evidence.strip():
            raise ValueError(f"{self.name}: 缺 evidence —— 没有出处的数字不得进报告")
        # ⚠⚠ Round 45 修红队 73b9a722 实测的**唯一未封造假路径**:
        #   本模块的三列(`方法` / `证据` / `备注`)是直接插进 Markdown 表格行的。
        #   字段里含 `|` 或换行即**撕开列边界**,可以凭空造出一整行 ——
        #   实测用 `note` 注入后,报告多出 3 行(期望 2 行),
        #   伪造行自带 `×0.01 | **是**` → **可以伪造「在前沿上」的结论**,
        #   而 `verify_report` 当时**不拦**。
        #   这是本模块唯一能产出「看起来合规、实则造假」的通道,故在构造期就拒。
        #   选择「拒绝」而非「转义 `\|`」:拒绝是响的,转义是静默的;
        #   本模块的字段由内部硬编码(3 个方法),不接受含 `|` 的输入不构成负担。
        for field, value in (("name", self.name), ("evidence", self.evidence),
                             ("note", self.note)):
            if any(ch in value for ch in "|\n\r"):
                raise ValueError(
                    f"{field} 不得含 `|` 或换行 —— 它会撕开 Markdown 表格列边界,"
                    f"可凭空伪造出一行「帕累托前沿=是」。实际值:{value!r}")
        # ⚠⚠ Round 45 修红队 a3d373a8 实测的高危绕过:
        #   `cost < 1.0` 对 **NaN 恒为 False**,于是 NaN 成本被静默接受;
        #   而 NaN 让 `on_frontier` 里所有比较都为假 → **支配判定被架空**:
        #     一个 NaN 成本、100% 准确率的方法,本该支配所有便宜方法,
        #     实际 `on_frontier(A)` 仍返回 True(看起来在前沿上)。
        #   即:一个 NaN 就能让整张表的结论作废而不报任何错。
        #   accuracy 的 NaN 反而被正确拒(因为 `0<=nan<=100` 为 False)——
        #   同一个漏洞在两个字段上一进一出,更难被发现。
        # ⚠⚠⚠ Round 45 二次加固(红队 73b9a722 实测的高危残余):
        #   靠 `value != value` 判 NaN **依赖 `__ne__`**,而自定义类型可以把它覆盖掉:
        #       class Ghost:
        #           def __eq__(self, o): return False
        #           def __ne__(self, o): return False
        #   实测 `Method("幽灵", 100.0, Ghost(), 30, "e")` **通过**纯比较式校验,
        #   随后 `on_frontier` 里所有比较也为假 → 支配判定**再次被架空**
        #   (幽灵 ×NaN 与 80%/×1 基线双双报「在前沿上」),且 `verify_report` 也拦不住
        #   —— 它只重跑同一套比较。当时唯一挡住它的是 f"{cost:g}" 抛 TypeError,
        #   属**侥幸**,不是设计。故改为**显式类型检查**。
        #   顺带封掉:`cost=True`(bool 是 int 子类)、`Decimal('sNaN')`、`"nan"`、
        #   `complex`、`np.float64` 单元素数组 —— 它们此前要么被接受、要么抛非 ValueError。
        for field, value in (("cost", self.cost), ("accuracy", self.accuracy)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{self.name}: {field} 必须是实数,"
                                 f"实际类型 {type(value).__name__} —— "
                                 f"非实数的比较结果不可信,会让支配判定静默失效")
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError(f"{self.name}: {field} 不能是 NaN/inf —— "
                                 f"它会让支配判定静默失效(实测可让整表结论作废)")
        if not isinstance(self.n, int) or isinstance(self.n, bool):
            # n=2.5 会被接受并算出无意义区间;n=True 在 Python 里就是 1
            raise ValueError(f"{self.name}: n 必须是整数(当前 {self.n!r}),"
                             f"否则 Wilson 区间无意义")
        if self.n <= 0:
            raise ValueError(f"{self.name}: n 必须为正整数")
        if self.cost < 1.0:
            raise ValueError(f"{self.name}: 成本倍数必须 >= 1.0(相对基线),实际 {self.cost}")
        if not (0.0 <= self.accuracy <= 100.0):
            raise ValueError(f"{self.name}: 准确率必须在 0–100,实际 {self.accuracy}")
        object.__setattr__(self, "_wilson", wilson(self.accuracy / 100.0, self.n))

    @property
    def wilson(self):
        """Wilson 95% 区间(R10:禁用 Wald —— n 小时 Wald 会越出 [0,1])。

        ⚠⚠ 这里**不读缓存,每次重算**(Round 45 修红队 a3d373a8):
        本 dataclass 是**可变**的,构造后写 `m.accuracy = ...` 完全合法,
        而构造函数里算好的 `_wilson` 会就此**变成陈旧值** ——
        `verify_report()` 只看字段、不看区间,于是察觉不到,
        报告会堂而皇之地印出「准确率 20% 却配着 100% 的 Wilson 区间」。
        重算顺带把校验也重跑一遍:改成非法值会在这里被拒,而不是静默出表。
        """
        self.__post_init__()
        return self._wilson


def wilson(p, n, z=1.96):
    if n <= 0:
        return (0.0, 1.0)
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return (max(0.0, center - half), min(1.0, center + half))


def on_frontier(m: Method, others: List[Method]) -> bool:
    """M 在帕累托前沿上,当且仅当不存在 N 以「不更多成本 + 不更低准确率」支配它。

    要求至少一项严格更优 —— 否则两个完全相同的方法会互相「支配」,
    使前沿被清空(这是写这个函数时最容易写错的第二处)。
    """
    for o in others:
        if o is m:
            continue
        no_more_expensive = o.cost <= m.cost
        no_worse = o.accuracy >= m.accuracy
        strictly_better = (o.cost < m.cost) or (o.accuracy > m.accuracy)
        if no_more_expensive and no_worse and strictly_better:
            return False
    return True


COLUMNS = ("方法", "准确率", "n", "Wilson 95%", "成本倍数", "帕累托前沿", "证据", "备注")


def render_markdown(methods: List[Method]) -> str:
    """输出**固定格式**的 Markdown 表。列名与顺序由 COLUMNS 定,测试逐字锁定。"""
    # ⚠ Round 45 修红队 73b9a722 实测的回归:装上门之后传**迭代器**会炸 ——
    #   `verify_report` 先把迭代器消费光,`if not methods` 对迭代器又恒为假
    #   (旧版没有 verify_report,所以能跑)。实测:
    #     旧版传 generator -> 4 行 [正常]   新版传 generator -> TypeError: no len()
    #   签名标注的是 `List`,但一个只在类型外输入上才正确的门仍然是门装错了位置。
    methods = list(methods)
    if not methods:
        raise ValueError("至少要给一个方法")
    # ⚠ Round 45 修:render 是唯一的出表口,若它不自检,
    #   「绕过 verify_report 直接 render」就能印出重名/非法行 —— 门装在侧门上。
    verify_report(methods)
    lines = [
        "| " + " | ".join(COLUMNS) + " |",
        "|" + "|".join(["---"] * len(COLUMNS)) + "|",
    ]
    for m in sorted(methods, key=lambda x: (x.cost, -x.accuracy)):
        lo, hi = m.wilson
        front = "**是**" if on_frontier(m, methods) else "否"
        lines.append(
            f"| {m.name} | {m.accuracy:.1f}% | {m.n} | "
            f"[{lo*100:.1f}%, {hi*100:.1f}%] | ×{m.cost:g} | {front} | "
            f"{m.evidence} | {m.note} |"
        )
    return "\n".join(lines)


def verify_report(methods: List[Method]) -> None:
    """渲染前的自检:任何一条不满足即拒绝出报告。

    存在的意义是让「缺样本量 / 缺出处 / 单位混用」在**生成时**就被拦下,
    而不是等到某个下游文档抄表时才发现。
    """
    seen = set()
    methods = list(methods)      # 同 render_markdown:迭代器只能消费一次,而本函数要遍历两遍
    for m in methods:
        if m.name in seen:
            raise ValueError(f"方法名重复: {m.name} —— 报告会给出两行同名,无法比较")
        seen.add(m.name)
        m.__post_init__()          # 已由构造校验,这里再确认一次语义未被后续改坏
    if len(methods) == 1:
        return
    if not any(on_frontier(m, methods) for m in methods):
        raise ValueError("没有任何方法在帕累托前沿上 —— 通常意味着支配判定写错了")
