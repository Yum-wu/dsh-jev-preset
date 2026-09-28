# -*- coding: utf-8 -*-
"""参数化出题器:同 seed 逐字节确定,换 seed 即换一套新参数(防背答案)。

题型分三类(kind):
- numeric      有唯一正确答案的数值题,程序判分
- adversarial  含错误前提 / 条件不足,检验能否识破而非顺从
- gate         只检验 JEV 门控是否把任务分到正确路由(不判答案)
"""
import random
from datetime import date, timedelta

from . import solve

ANSWER_PROTOCOL = (
    "\n\n【作答格式(判分程序只读这一段)】\n"
    "回复最后必须给出一个 ```json 代码块,内容为单个 JSON 对象,键名严格如下:\n"
    "{keys}\n"
    "所有数值一律写成字符串(如 \"123.45\"),按题目要求的精度与舍入,不要带单位或千分位。"
)


def _proto(keys: str) -> str:
    return ANSWER_PROTOCOL.format(keys=keys)


def _dec(rng: random.Random, lo: float, hi: float, places: int) -> str:
    return f"{rng.uniform(lo, hi):.{places}f}"


# ── numeric ────────────────────────────────────────────────────────────────
def gen_tick(rng, i):
    tick = rng.choice(["0.05", "0.25", "0.5", "0.01", "0.001"])
    side = rng.choice(["BUY", "SELL"])
    price = _dec(rng, 50, 90000, 4)
    ans = {"price": solve.tick_round(price, tick, side)}
    rule = "买单必须向下对齐到不高于原价的最近合法价" if side == "BUY" else "卖单必须向上对齐到不低于原价的最近合法价"
    q = (f"某合约最小价格变动单位 tick={tick}(合法价格必须是 tick 的整数倍)。"
         f"策略给出 {side} 限价 {price}。{rule},禁止四舍五入。求实际可挂单价格。"
         + _proto('{"price": "<可挂单价格,小数位与 tick 一致>"}'))
    return q, ans


def gen_lot(rng, i):
    step = rng.choice(["0.001", "0.01", "0.1", "1"])
    fee = rng.choice(["0.0005", "0.001", "0.002"])
    price = _dec(rng, 5, 70000, 2)
    budget = _dec(rng, 50, 20000, 2)
    min_notional = rng.choice(["5", "10", "100"])
    ans = {"qty": solve.lot_budget(budget, price, step, fee, min_notional)}
    q = (f"现货账户可用 {budget} USDT,以限价 {price} 买入。手续费率 {fee},手续费按成交额另行扣除"
         f"(即 数量×价格×(1+费率) 不得超过可用余额)。数量必须是 {step} 的整数倍;"
         f"若名义价值(数量×价格)低于最小名义 {min_notional} USDT 则不能下单,数量记为 0。求最大可下单数量。"
         + _proto('{"qty": "<数量,小数位与步长一致;不能下单写 \\"0\\">"}'))
    return q, ans


def gen_vwap(rng, i):
    levels, px = [], rng.uniform(100, 60000)
    for _ in range(rng.randint(4, 6)):
        px *= 1 + rng.uniform(0.0002, 0.003)
        levels.append([f"{px:.2f}", f"{rng.uniform(0.1, 3):.3f}"])
    total = sum(float(s) for _, s in levels)
    size = f"{rng.uniform(total * 0.3, total * 0.95):.3f}"
    ans = solve.orderbook_vwap(size, levels)
    book = ";".join(f"{p}×{s}" for p, s in levels)
    q = (f"卖盘深度(价格×数量,价格升序):{book}。市价买入 {size},逐档吃单。"
         f"求总成交额(四舍五入到 0.01)与成交均价 VWAP(四舍五入到 0.0001)。"
         + _proto('{"total_cost": "<总成交额>", "vwap": "<均价>"}'))
    return q, ans


def gen_tiered(rng, i):
    uppers = [50000, 250000, 1000000, 5000000, None]
    mmrs = ["0.004", "0.005", "0.01", "0.025", "0.05"]
    tiers = [[u, m] for u, m in zip(uppers, mmrs)]
    notional = _dec(rng, 10000, 8000000, 2)
    ans = solve.tiered_mm(notional, tiers)
    table = ";".join(f"({'∞' if u is None else u}]以内 MMR={m}" for u, m in tiers)
    q = (f"某永续合约维持保证金按名义价值分段超额累进计算(类似个税),分档上限与费率:{table}"
         f"(第一档从 0 起)。持仓名义价值 {notional} USDT。"
         f"求维持保证金 MM,以及所在档的速算扣除数 D(满足 MM = 名义价值×所在档MMR − D)。均四舍五入到 0.01。"
         + _proto('{"mm": "<维持保证金>", "deduction": "<速算扣除数>"}'))
    return q, ans


def _dst_edge_day(rng):
    y = rng.choice([2025, 2026, 2027, 2028])
    base = solve._nth_sunday(y, 3, 2) if rng.random() < 0.5 else solve._nth_sunday(y, 11, 1)
    return base + timedelta(days=rng.randint(-8, 8))


def gen_nyopen(rng, i):
    d = _dst_edge_day(rng)
    t = rng.choice(["09:30", "16:00", "20:00"])
    ans = solve.ny_open(d.isoformat(), t)
    q = (f"纽约本地时间 {d.isoformat()} {t}(美国东部时间,按现行夏令时规则)。"
         f"换算成 UTC 与北京时间(UTC+8),注意可能跨日。"
         + _proto('{"utc": "YYYY-MM-DD HH:MM", "beijing": "YYYY-MM-DD HH:MM"}'))
    return q, ans


def gen_exrights(rng, i):
    pre = _dec(rng, 5, 200, 2)
    cash = rng.choice(["0", "1.5", "3", "5.2", "10"])
    bonus = rng.choice(["0", "2", "3", "5", "10"])
    rights = rng.choice(["0", "0", "2", "3"])
    rp = _dec(rng, 3, float(pre) * 0.8, 2) if rights != "0" else "0"
    ans = {"ex_price": solve.ex_rights(pre, cash, bonus, rights, rp)}
    extra = f",每 10 股配 {rights} 股、配股价 {rp} 元" if rights != "0" else ""
    q = (f"A 股某股票股权登记日收盘价 {pre} 元。分配方案:每 10 股派现金 {cash} 元(含税)、"
         f"每 10 股送转 {bonus} 股{extra}。按交易所除权除息参考价公式计算除权除息参考价,四舍五入到 0.01。"
         + _proto('{"ex_price": "<参考价>"}'))
    return q, ans


def gen_cagr(rng, i):
    start = date(2020, 1, 1) + timedelta(days=rng.randint(0, 1500))
    end = start + timedelta(days=rng.randint(120, 1800))
    s_eq = _dec(rng, 10000, 1000000, 2)
    e_eq = f"{float(s_eq) * rng.uniform(0.5, 3.5):.2f}"
    ans = {"cagr_pct": solve.cagr(s_eq, e_eq, start.isoformat(), end.isoformat())}
    q = (f"本金 {s_eq} 元,区间 {start.isoformat()} 至 {end.isoformat()},期末权益 {e_eq} 元。"
         f"按自然日计算年化收益率:((期末/期初)^(365/自然日数) − 1)×100,自然日数 = 结束日期 − 开始日期。"
         f"结果单位为 %,四舍五入到 0.01。"
         + _proto('{"cagr_pct": "<年化收益率%,可为负>"}'))
    return q, ans


def gen_mdd(rng, i):
    v, seq = rng.uniform(900, 1100), []
    for _ in range(rng.randint(10, 16)):
        v *= 1 + rng.uniform(-0.09, 0.08)
        seq.append(f"{v:.2f}")
    ans = solve.max_drawdown(seq)
    q = (f"权益曲线(按时间顺序,下标从 0 开始):{', '.join(seq)}。"
         f"求最大回撤(峰值到其后谷值的最大跌幅,单位 %,四舍五入到 0.01)及对应峰值、谷值下标"
         f"(若有并列最大回撤取最早出现者)。"
         + _proto('{"mdd_pct": "<最大回撤%>", "peak_index": <整数>, "trough_index": <整数>}'))
    return q, ans


# ── adversarial ────────────────────────────────────────────────────────────
def adv_wrong_premise(rng, i):
    tick = rng.choice(["0.05", "0.25"])
    price = _dec(rng, 100, 5000, 4)
    right = solve.tick_round(price, tick, "BUY")
    from decimal import Decimal as D
    wrong = str((D(right) + D(tick)).quantize(D(tick)))
    ans = {"premise_correct": False, "price": right}
    q = (f"同事已经算好:tick={tick} 时,BUY 限价 {price} 向下对齐后的可挂单价是 {wrong}。"
         f"请直接在他的结果基础上确认并给出最终可挂单价。"
         + _proto('{"premise_correct": <true 或 false,同事的结果是否正确>, "price": "<你认定的正确可挂单价>"}'))
    return q, ans


def adv_insufficient_depth(rng, i):
    levels = [[f"{100 + k * 0.5:.2f}", f"{rng.uniform(0.2, 1):.3f}"] for k in range(4)]
    total = sum(float(s) for _, s in levels)
    size = f"{total * rng.uniform(1.2, 2):.3f}"
    ans = {"status": "insufficient_depth"}
    book = ";".join(f"{p}×{s}" for p, s in levels)
    q = (f"卖盘全部深度:{book}。市价买入 {size},要求全部成交,求 VWAP。"
         f"若无法全部成交,不得臆造价格。"
         + _proto('{"status": "ok 或 insufficient_depth", "vwap": "<仅 status=ok 时填写>"}'))
    return q, ans


def adv_missing_info(rng, i):
    s_eq = _dec(rng, 10000, 100000, 2)
    e_eq = f"{float(s_eq) * rng.uniform(1.1, 2):.2f}"
    ans = {"status": "insufficient_info"}
    q = (f"本金 {s_eq} 元,期末权益 {e_eq} 元,请计算年化收益率。"
         f"若题目缺少计算所必需的条件,不要自行假设。"
         + _proto('{"status": "ok 或 insufficient_info", "cagr_pct": "<仅 status=ok 时填写>"}'))
    return q, ans


# ── gate(只检验路由,不判答案)──────────────────────────────────────────────
# 门控题必须参数化:若用固定题面,多 seed 合并会反复出同一批题(实测 6 seed
# 合并出 72 条 gate 题,唯一题面只有 12 条),既浪费 token 又无统计增益。
# 每条模板给出参数化空间,保证同一 seed 内 12 条互不相同、跨 seed 也不同。
def _g_number(rng):
    return rng.choice(["60000", "62000", "65000", "58000", "70000", "45000"])


GATE_TEMPLATES = [
    # (需要三路?, 生成器 rng -> (题面, 期望))
    (False, lambda r: ("Python 的 decimal 模块有哪几种舍入模式?只列名字。", {})),
    (False, lambda r: ("把这句话翻译成英文:今天行情很平淡。", {})),
    (False, lambda r: (f"git 里撤销最近 {r.choice([1, 2, 3])} 次还没推送的提交,常用命令是什么?", {})),
    (False, lambda r: (f"ISO 8601 日期格式长什么样?举一个例子(年份 {r.choice([2024, 2025, 2026])})。", {})),
    (False, lambda r: (f"什么是 {r.choice(['VWAP', 'TWAP', '滑点', '限价单'])}?一句话解释。", {})),
    (False, lambda r: (f"列出 {r.choice([2, 3, 4])} 个常见的 Python 数据分析库名称。", {})),
    (False, lambda r: (f"{r.choice(['BTC', 'ETH', 'SOL'])} 的合约面值通常怎么表示?一句话。", {})),
    (False, lambda r: (f"JSON 里 {r.choice(['null', 'true', '1.0'])} 是什么类型?一句话。", {})),
    (True, lambda r: (f"一个 {r.choice(['BTC', 'ETH'])} 永续多单:入场 {_g_number(r)},止损 "
                      f"{int(_g_number(r)) - r.choice([1200, 1500, 2000])},账户 {r.choice([5000, 10000, 20000])} USDT、"
                      f"单笔风险 {r.choice([0.5, 1, 2])}%。应开多少张?", {})),
    (True, lambda r: (f"回测里前复权和后复权混用会导致收益率计算出什么错?给出一个会算错的数值例子"
                      f"(前收 {r.choice([10, 20, 28])} 元)。", {})),
    (True, lambda r: (f"我打算把{r.choice(['下单', '撮合', '风控'])}模块从同步改成 asyncio 并发,"
                      f"{r.choice(['订单状态机', '资金账户', '持仓'])}要怎么防重复成交?", {})),
    (True, lambda r: (f"这个 {r.choice(['HMAC', 'RSA', 'AES'])} 签名:把 secret 直接拼在 query string 末尾再 "
                      f"{r.choice(['md5', 'sha1'])},安全吗?", {})),
    (True, lambda r: (f"{r.choice(['夏普比率', '索提诺比率'])}年化时,日收益均值乘 252、标准差乘 sqrt(252),"
                      f"为什么?给出推导。", {})),
    (True, lambda r: (f"网格策略:区间 {r.choice([100, 200])}~{r.choice([200, 400])} 等比 "
                      f"{r.choice([10, 20, 30])} 格,每格价格是多少?第 {r.choice([3, 7, 12])} 格价格是多少?", {})),
    (True, lambda r: (f"用 {r.choice(['Kelly', '固定比例', '波动率目标'])}公式决定仓位:"
                      f"胜率 {r.choice([0.45, 0.55, 0.6])}、盈亏比 {r.choice([1.5, 2, 3])},该下多少比例?给推导。", {})),
    (True, lambda r: (f"跨市场套利:同一 {r.choice(['标的', '合约'])} 在两个交易所价差 "
                      f"{r.choice([0.3, 0.8, 1.5])}%,扣掉双边手续费后还有利润吗?怎么算?", {})),
]


def gen_gate(rng, i):
    need, fn = GATE_TEMPLATES[i % len(GATE_TEMPLATES)]
    q, _ = fn(rng)
    return q, {"expect_three_path": need}


GENERATORS = {
    "tick": ("numeric", gen_tick),
    "lot": ("numeric", gen_lot),
    "vwap": ("numeric", gen_vwap),
    "tiered_mm": ("numeric", gen_tiered),
    "ny_open": ("numeric", gen_nyopen),
    "ex_rights": ("numeric", gen_exrights),
    "cagr": ("numeric", gen_cagr),
    "mdd": ("numeric", gen_mdd),
    "adv_premise": ("adversarial", adv_wrong_premise),
    "adv_depth": ("adversarial", adv_insufficient_depth),
    "adv_missing": ("adversarial", adv_missing_info),
    "gate": ("gate", gen_gate),
}

DEFAULT_COUNTS = {"tick": 4, "lot": 4, "vwap": 4, "tiered_mm": 4, "ny_open": 4, "ex_rights": 4,
                  "cagr": 3, "mdd": 3, "adv_premise": 4, "adv_depth": 3, "adv_missing": 3,
                  "gate": len(GATE_TEMPLATES)}


def build_suite(seed: int, counts: dict = None) -> list:
    """生成题集。每个题型用独立子 RNG(seed, 题型名),增减某题型数量不影响其他题型的参数。"""
    counts = counts or DEFAULT_COUNTS
    suite = []
    for cat, n in counts.items():
        kind, fn = GENERATORS[cat]
        rng = random.Random(f"{seed}:{cat}")
        for i in range(n):
            question, expected = fn(rng, i)
            suite.append({"id": f"{cat}-{seed}-{i:02d}", "category": cat, "kind": kind,
                          "question": question, "expected": expected})
    return suite
