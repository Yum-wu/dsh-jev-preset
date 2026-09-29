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


# ── trap:认知陷阱题(答案唯一可判分,但直觉答案诱人且错误)──────────────────
# 依据:认知反射测验 CRT(Frederick 2005)与业界"降智检测"题。
# 关键性质:**盲目/直觉路径会给出一个自信的错误答案**,而正确答案需要
# 抑制第一反应(system 1 → system 2)。这类题对"单路 vs 多路"的区分力
# 远高于常规数值题 —— 三路独立采样有机会在交叉比对时暴露分歧。
# 每道题在 prompt 中**不提示是陷阱题**,否则会人为激活审慎模式。
_TRAP_WORDS = ["strawberry", "raspberry", "blueberry", "cranberry", "gooseberry", "elderberry"]


def trap_crt_ball(rng, i):
    diff = rng.choice([100, 90, 80, 60, 50, 40, 120])
    total = diff + rng.choice([10, 20, 30, 40, 60, 80])
    ans = {"ball_cents": solve.crt_ball(total, diff)}
    q = (f"一副球拍和一个球一共 {total} 分钱,球拍比球贵 {diff} 分钱。球多少钱?(单位:分)"
         + _proto('{"ball_cents": "<球价,单位分,整数>"}'))
    return q, ans


def trap_crt_widgets(rng, i):
    m = rng.choice([5, 3, 4, 6, 10])
    w = rng.choice([m, m * 2, m * 3])
    tm = rng.choice([20, 50, 100, 200])
    tw = rng.choice([tm, tm * 2, tm * 5])
    ans = {"minutes": solve.crt_widgets(m, 5, w, tm, tw)}
    # ⚠️ 必须在题面明确规定精度:参考解按公式可给出 4 位小数(如 8.3333),
    # 而模型常保留 2 位(8.33)。若题面不定精度,会把**正确但精度不同**的答案
    # 判成错 —— 这是实测发现的误判(2026-09-28)。
    q = (f"{m} 台机器 {5} 分钟可以生产 {w} 个零件。那么 {tm} 台机器生产 {tw} 个零件需要多少分钟?"
         f"结果保留 4 位小数。"
         + _proto('{"minutes": "<分钟数,保留 4 位小数>"}'))
    return q, ans


def trap_crt_lily(rng, i):
    d = rng.choice([48, 30, 60, 24, 36, 72, 100])
    ans = {"days": solve.crt_lily(d)}
    q = (f"湖里有一片睡莲,面积每天翻一倍。如果 {d} 天可以铺满整个湖面,"
         f"那么铺满半个湖面需要多少天?"
         + _proto('{"days": "<天数,整数>"}'))
    return q, ans


def trap_decimal_compare(rng, i):
    a, b = rng.choice([("9.11", "9.9"), ("1.10", "1.9"), ("3.15", "3.9"),
                       ("2.05", "2.5"), ("10.11", "10.9")])
    ans = {"larger": solve.decimal_max(a, b)}
    q = (f"从数学上比较 {a} 和 {b} 哪个更大?给出较大的那个数。"
         + _proto('{"larger": "<较大的数,原样书写>"}'))
    return q, ans


def trap_count_letter(rng, i):
    w = rng.choice(_TRAP_WORDS)
    letter = rng.choice(["r", "b", "e"])
    ans = {"count": solve.count_letter(w, letter)}
    q = (f"单词 \"{w}\" 里字母 \"{letter}\" 出现了多少次?给出次数。"
         + _proto('{"count": "<次数,整数>"}'))
    return q, ans


def trap_mushroom(rng, i):
    kg = rng.choice(["1000", "100", "500", "200"])
    pi, pf = rng.choice([("0.99", "0.98"), ("0.98", "0.96"), ("0.95", "0.90")])
    ans = {"water_lost_kg": solve.mushroom_water_lost(kg, pi, pf)}
    q = (f"最初有 {kg} 千克蘑菇,其中 {float(pi)*100:.0f}% 是水。经过几天晾晒后,"
         f"水分含量降为 {float(pf)*100:.0f}%。问:蘑菇失去了多少千克水?"
         + _proto('{"water_lost_kg": "<失去的水重(千克),保留两位小数>"}'))
    return q, ans


def trap_candy(rng, i):
    """糖果题:关键提示"形状靠手感可以分辨"藏在括号里,易被忽略。
    忽略它会得到明显更大的错答(文献实测模型常答 29,正确 21)。"""
    rc = [rng.randint(3, 9) for _ in range(3)]
    sc = [rng.randint(2, 8) for _ in range(3)]
    ia, ip = 0, 1                                  # 苹果、桃子
    ans = {"min_candies": solve.candy_min(rc, sc, ia, ip)}
    blind = solve.blind_candy_min(rc, sc, ia, ip)
    if blind <= ans["min_candies"]:                # 陷阱无效则不采用这组参数
        rc, sc = [7, 9, 8], [7, 6, 4]
        ans = {"min_candies": solve.candy_min(rc, sc, ia, ip)}
    q = (f"在一个黑色的袋子里放有三种口味的糖果,每种糖果有两种不同的形状"
         f"(圆形和五角星形,不同的形状靠手感可以分辨)。现已知不同口味的糖和"
         f"不同形状的数量统计如下表。参赛者需要在活动前决定摸出的糖果数目,"
         f"那么,最少取出多少个糖果才能保证手中同时拥有不同形状的苹果味和桃子味的糖?"
         f"(同时手中有圆形苹果味匹配五角星桃子味糖果,或者有圆形桃子味匹配"
         f"五角星苹果味糖果都满足要求)\n"
         f"口味:苹果 桃子 西瓜\n圆形:{rc[0]} {rc[1]} {rc[2]}\n"
         f"五角星形:{sc[0]} {sc[1]} {sc[2]}"
         + _proto('{"min_candies": "<最少取出数,整数>"}'))
    return q, ans


# ══════════════════════════════════════════════════════════════════════════
# ma_*:定势效应题(Einstellung effect)
#
# 来源:[MisguidedAttention](https://github.com/cpldcpu/MisguidedAttention)(MIT),
# 原理:经典谜题的**轻微变体**。模型会因训练数据中的频繁出现而**认出原题**,
# 从而给出**原题的答案**,而非针对改动后的题面逐步推理。作者将其类比为人类的
# Einstellungseffekt(定势效应)。
#
# 与 candy 题(需从题干提取隐含约束)不同,这类题考察的是**抑制对原题的套用**。
# 实测(2026-09-28):shangtang 在 candy 题上仅 33.3%,但在本类题上 100% ——
# 证明两类题考察**不同能力**,需并存于题集。
#
# 这些题**不做参数化随机**:变体的微妙性是精心设计的关键,随机化会破坏陷阱。
# 答案均已由本仓独立推导或暴力枚举验证(见 COMMUNITY-DEGRADATION-BENCHMARKS.md)。
# ══════════════════════════════════════════════════════════════════════════

# (类别后缀, 题面, 期望, 判分键说明, 陷阱说明)
_MA_CASES = [
    ("jugs_impossible",
     "我有两个水壶,容量分别是 6 升和 12 升。我想准确量出 4 升水。"
     "请判断这件事是否可能做到;如果不可能,不要给出任何操作步骤。",
     {"status": "impossible", "steps": "-1"},
     '{"status": "<possible 或 impossible>", "steps": "<最少步数;不可能写 -1>"}',
     "gcd(6,12)=6,4 非其倍数 → 不可能;模型常给复杂步骤"),

    ("jugs_trivial_1",
     "我有两个水壶,每个容量都是 1 升。我想准确量出 1 升水。请判断能否做到,并给出最少步数。",
     {"status": "possible", "steps": "1"},
     '{"status": "<possible 或 impossible>", "steps": "<最少步数>"}',
     "装满任一壶即 1 升(1 步);模型常写多步清单"),

    ("jugs_sum_3",
     "我有两个水壶,容量分别是 1 升和 2 升。我想准确量出 3 升水。请判断能否做到,并给出最少步数。",
     {"status": "possible", "steps": "2"},
     '{"status": "<possible 或 impossible>", "steps": "<最少步数>"}',
     "两壶都装满 = 3 升(2 步);模型常写复杂倒水序列"),

    ("rope_60_easy",
     "我有两根绳子,每根完全烧完正好需要 60 分钟。绳子燃烧不均匀。"
     "除此之外没有任何计时工具。我想测量正好 60 分钟,最少需要几根绳子、几步操作?",
     {"ropes": "1", "steps": "1"},
     '{"ropes": "<最少用几根绳,整数>", "steps": "<最少操作步骤数,整数>"}',
     "点燃一根烧完即 60 分钟(1 根 1 步);模型常给两端点燃等复杂方案"),

    ("rope_20_impossible",
     "我有两根绳子,每根完全烧完正好需要 60 分钟。绳子燃烧不均匀,无法对折取得三等分。"
     "除此之外没有任何计时工具。我想测量正好 20 分钟。请判断是否可能。",
     {"status": "impossible", "steps": "-1"},
     '{"status": "<possible 或 impossible>", "steps": "<步数;不可能写 -1>"}',
     "20 分钟无解(需三等分);评测显示多数模型会强行给方案"),

    ("river_one_step",
     "一个人带着一只羊在河的一边,有一条船,船可以同时载下这个人和这只羊。"
     "人和羊要怎样到对岸?给出最少往返次数(单程过河算 1 次)。",
     {"trips": "1"},
     '{"trips": "<最少单程次数,整数>"}',
     "一次同船过河;模型常幻觉出多次往返、狼/菜等不存在的约束"),

    ("trolley_dead",
     "一辆失控的电车正冲向轨道上的五个人,这五个人**已经死亡**。你可以拉动拉杆,"
     "让电车转向另一条轨道,那里绑着一个**活着**的人。是否应该拉动拉杆?"
     "给出 yes 或 no,以及拉杆后相比不拉杆新增的死亡人数。",
     {"pull": "no", "extra_deaths": "1"},
     '{"pull": "<yes 或 no>", "extra_deaths": "<相比不拉杆新增的死亡人数,整数>"}',
     "五人已死,拉杆只会多死 1 个活人;模型常答 yes"),

    ("monty_hall_inverse",
     "你参加一个游戏:三扇门后分别是一头驴和两辆豪车。你先选了一扇门,"
     "主持人(知道门后是什么)打开了另外两扇中的一扇,露出**一辆豪车**,"
     "然后问你要保持原选择还是换到剩下那扇未开的门。为了赢得车,应该保持还是换?"
     "并给出保持获胜的概率(**保留 4 位小数**,写成 0 到 1 之间的小数)。",
     {"action": "keep", "win_prob": "0.6667"},
     '{"action": "<keep 或 switch>", "win_prob": "<保持获胜概率,保留 4 位小数>"}',
     "反 Monty Hall:应保持(2/3);模型常答 switch(沿用原题)"),

    ("linear_growth_half",
     "池塘里的莲花数量每天**增加 2 朵**(不是翻倍)。第 1 天有 2 朵,第 40 天池塘满了。"
     "问:池塘在第几天时是一半满?给出整数天数。",
     {"day": "20"},
     '{"day": "<天数,整数>"}',
     "线性增长半满在第 20 天;模型常答 39(沿用翻倍题)"),

    ("dead_cat_alive_prob",
     "一只**已经死亡**的猫被放进箱子,箱内还有放射性同位素、毒药瓶和辐射探测器;"
     "若探测到辐射则释放毒药。箱子一天后打开。问:此时猫活着概率是多少?"
     "写成 0 到 1 之间的小数(**保留 4 位小数**)。",
     {"alive_prob": "0"},
     '{"alive_prob": "<活着概率,保留 4 位小数>"}',
     "猫放入时已死,P(活)=0;模型常答 0.5(沿用薛定谔猫)"),

    ("birthday_easy_inverse",
     "一个房间里有 30 个人。问:其中**至少有两个人生日不同**的概率是多少?"
     "写成 0 到 1 之间的小数,**保留 4 位小数**,并四舍五入到该精度"
     "(若你的结果极接近 1,四舍五入后应为 1.0000)。",
     {"prob": "1.0000"},
     '{"prob": "<概率,保留 4 位小数,四舍五入>"}',
     "补事件是 30 人同一天(≈0),故 ≈1;模型常答生日悖论的 0.7"),

    ("units_feathers_steel",
     "请问 1 千克羽毛和 1 磅钢,哪个更重?更重的那个换算成千克是多少?"
     "(1 磅 = 0.45359237 千克),**保留 4 位小数**。",
     {"heavier": "feathers", "kg": "1.0000"},
     '{"heavier": "<feathers 或 steel>", "kg": "<更重者换算成千克,保留 4 位小数>"}',
     "1 磅 < 1 千克 → 羽毛重;模型常比较单位而非数值"),
]


def gen_ma_static(rng, i):
    """返回定势效应题(第 i 条)。rng 不参与:题目固定,参数化会破坏陷阱。"""
    suf, q, expected, keys, _trap = _MA_CASES[i % len(_MA_CASES)]
    return q + _proto(keys), expected


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
    "trap_ball": ("trap", trap_crt_ball),
    "trap_widgets": ("trap", trap_crt_widgets),
    "trap_lily": ("trap", trap_crt_lily),
    "trap_decimal": ("trap", trap_decimal_compare),
    "trap_letter": ("trap", trap_count_letter),
    "trap_mushroom": ("trap", trap_mushroom),
    "trap_candy": ("trap", trap_candy),
    "ma_static": ("trap", gen_ma_static),
    "gate": ("gate", gen_gate),
}

DEFAULT_COUNTS = {"tick": 4, "lot": 4, "vwap": 4, "tiered_mm": 4, "ny_open": 4, "ex_rights": 4,
                  "cagr": 3, "mdd": 3, "adv_premise": 4, "adv_depth": 3, "adv_missing": 3,
                  "trap_ball": 3, "trap_widgets": 3, "trap_lily": 3, "trap_decimal": 3,
                  "trap_letter": 3, "trap_mushroom": 3, "trap_candy": 3,
                  "ma_static": len(_MA_CASES),
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
