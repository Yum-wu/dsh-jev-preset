# -*- coding: utf-8 -*-
"""band_quant 独立复算 solver(2026-10-15)。

读同目录 band_quant.jsonl,对每题从题面参数独立重算,比对 expected。
--emit 模式:用 solver 计算值生成 jsonl(expected 不手写)。
退出码:全部 OK = 0;有 MISMATCH = 1。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
JSONL = HERE / "band_quant.jsonl"
CATEGORY = "band_quant"
SEED = 20261015
SUITE = 1


def fmt_block(key: str, desc: str) -> str:
    return (
        "\n\n【作答格式(判分程序只读这一段)】\n"
        "回复最后必须给出一个 ```json 代码块,内容为单个 JSON 对象,键名严格如下:\n"
        '{"%s": "<%s>"}\n'
        '所有数值一律写成字符串(如 "123.45"),按题目要求的精度与舍入,不要带单位或千分位。'
        % (key, desc)
    )


# ---- 20 个独立复算函数(从题面参数重算,不读 expected) ----
def solve00() -> str:
    start = datetime(2026, 3, 1, 8, 0)
    end = datetime(2026, 3, 5, 16, 0)
    hours = (end - start).total_seconds() / 3600  # 104
    return str(int(hours // 8) + 1)  # 含两端 -> 14


def solve01() -> str:
    return f"{100000 * 0.0005 + 100000 * 0.0002:.2f}"  # taker开 + maker平


def solve02() -> str:
    return f"{50000 * (1 - 1 / 10 + 0.005):.2f}"


def solve03() -> str:
    aligned = (250050 // 100) * 100  # 先向下对齐 -> 250000
    return f"{aligned * 0.0003:.2f}"


def solve04() -> str:
    usable = 5000 * 0.98  # 预留 2% 手续费缓冲
    margin_per_lot = (0.01 * 60000) / 5  # 120
    return str(int(usable // margin_per_lot))


def solve05() -> str:
    trades = [(100, 10), (101, 20), (102, 30), (103, 40)][:-1]  # 剔除最后一笔
    num = sum(p * q for p, q in trades)
    den = sum(q for _, q in trades)
    return f"{num / den:.4f}"


def solve06() -> str:
    closes = [10, 12, 11, 13]
    opens = [10, 10, 12, 11]
    segs = [(o + c) / 2 for o, c in zip(opens, closes)]
    return f"{sum(segs) / len(segs):.4f}"


def solve07() -> str:
    eq = [1000, 1200, 1000, 1100, 800, 950]
    peak = eq[0]
    mdd = 0.0
    for e in eq:
        if e > peak:
            peak = e
        dd = (peak - e) / peak * 100
        if dd > mdd:
            mdd = dd
    return f"{mdd:.2f}"


def solve08() -> str:
    v = (1.12) ** (365 / 90) - 1
    return f"{v * 100:.2f}"


def solve09() -> str:
    return f"{50 * 0.01 * 60000:.2f}"  # 开仓价口径


def solve10() -> str:
    v = 100 * 0.0001 - 100 * 0.0002 + 100 * 0.00015  # 空头:正收负付
    return f"{v:.4f}"


def solve11() -> str:
    hours = [1.5, 2.0, 23.9, 24.0, 48.0]
    return str(sum(1 for h in hours if h >= 24))  # 24.0 归 long


def solve12() -> str:
    return f"{300000 * 0.01 - 500:.2f}"  # 减速算扣除数


def solve13() -> str:
    total = 100000 + 200000 + 600000
    return f"{200000 / total * 900:.2f}"  # 加权非等权


def solve14() -> str:
    return f"{(1500 - 1000) * 0.1:.2f}"  # 仅超出部分


def solve15() -> str:
    return f"{(200 - 20 - 5) / 100:.2f}"  # 净盈亏扣手续费+滑点


def solve16() -> str:
    E = min(1000, 1300)  # min(已实现,标记)
    dd = (1500 - E) / 1500
    factor = 0.25 if dd >= 0.20 else (0.5 if dd >= 0.10 else 1.0)
    return f"{2 * factor:.2f}"


def solve17() -> str:
    return f"{-0.0001 * 3 * 365 * 100:.4f}"  # 单利


def solve18() -> str:
    num = 400 * 10.0 + 350 * 10.2
    den = 400 + 350  # 仅已成交,不含 250 张挂单
    return f"{num / den:.4f}"


def solve19() -> str:
    remaining = 15 - 8  # 同簇同向剩余额度
    return f"{min(remaining, 15):.2f}"


# ---- 题面 + 规格 ----
SPECS = [
    ("00", "count", "结算次数,整数",
     "某 USDT 本位永续合约每 8 小时结算一次资金费,结算时刻为每日 UTC 00:00、08:00、16:00。"
     "统计区间为从 2026-03-01 08:00(UTC)起、至 2026-03-05 16:00(UTC)止,且含两端时刻。"
     "求该区间内共结算多少次资金费。", solve00),
    ("01", "fee_total", "合计手续费,保留2位小数",
     "某合约 taker 手续费率 0.05%,maker 手续费率 0.02%。用户以 taker 市价单开仓,名义价值 100,000 USDT;"
     "随后将该仓位全部以 maker 限价单平仓(按标准 maker 费率,不适用任何平今仓优惠)。"
     "求开仓与平仓两笔手续费的合计金额(USDT,保留 2 位小数)。", solve01),
    ("02", "liq_price", "强平价,保留2位小数",
     "逐仓做多某永续合约,开仓价 50,000 USDT,杠杆 10x,维持保证金率 0.5%。"
     "强平价按公式:强平价 = 开仓价 × (1 - 1/杠杆 + 维持保证金率)。求强平价(USDT,保留 2 位小数)。", solve02),
    ("03", "slippage", "滑点预算,保留2位小数",
     "计划下单名义 250,050 USDT。该合约每 1 张对应名义 100 USDT,张数必须为整数。"
     "风控要求先按每 100 USDT 名义向下取整对齐到整数张,再对对齐后的名义计算滑点预算;滑点预算率为 0.03%。"
     "求滑点预算金额(USDT,保留 2 位小数)。", solve03),
    ("04", "lots", "最多可开张数,整数",
     "账户可用保证金 5,000 USDT,BTC 价格 60,000 USDT,杠杆 5x,逐仓。该合约每 1 张 = 0.01 BTC,"
     "每张名义 = 0.01 × 60,000 = 600 USDT,每张所需保证金 = 名义 / 杠杆。"
     "风控规定可用保证金中需预留 2% 作为手续费缓冲,预留部分不可用于开仓。"
     "在满足整数张、向下取整的前提下,求最多可开多少张。", solve04),
    ("05", "vwap", "VWAP,保留4位小数",
     "某时段逐笔成交明细为(价格,数量):(100, 10)、(101, 20)、(102, 30)、(103, 40)。"
     "风控计算 VWAP 时规定剔除最后一笔成交(视为收盘集合竞价异常数据)。求剔除后的 VWAP(保留 4 位小数)。", solve05),
    ("06", "twap", "TWAP,保留4位小数",
     "某币在 4 个等长时段的收盘价分别为 10、12、11、13,且每个时段的开盘价等于上一时段的收盘价"
     "(第 1 时段开盘价 = 10)。风控规定 TWAP 使用各时段均价(开盘价与收盘价的算术平均),"
     "再对 4 个时段均价求简单平均。求规定口径下的 TWAP(保留 4 位小数)。", solve06),
    ("07", "mdd", "最大回撤百分比,保留2位小数",
     "某账户按日权益曲线为:1000、1200、1000、1100、800、950。"
     "最大回撤定义为(历史峰值 - 峰值之后的最低谷值)/ 历史峰值(注意分母是峰值,不是初始权益)。"
     "求最大回撤百分比(保留 2 位小数,不带百分号)。", solve07),
    ("08", "annual", "年化收益率百分比,保留2位小数",
     "某策略回测区间为 90 个自然日,累计收益率 12%。年化收益率按复利公式:"
     "(1 + 累计收益率)^(365 / 天数) - 1,其中天数与年化基数均取自然日 365 口径(非交易日 252 口径)。"
     "求年化收益率百分比(保留 2 位小数,不带百分号)。", solve08),
    ("09", "notional", "名义价值,保留2位小数",
     "某永续合约 1 张 = 0.01 BTC。用户持有 50 张多单,开仓价 60,000 USDT,当前标记价 61,000 USDT。"
     "风控计算名义价值敞口时规定使用开仓价(锁定建仓时风险敞口),不使用当前标记价。"
     "求名义价值(USDT,保留 2 位小数)。", solve09),
    ("10", "net_funding", "净资金费收入,保留4位小数",
     "某空头持仓名义价值 100 USDT,经历 3 次资金费结算,费率依次为 +0.01%、-0.02%、+0.015%。"
     "结算规则:空头在资金费率为正时收取资金费,为负时支付资金费。"
     "求这 3 次结算该空头的净资金费收入(USDT,保留 4 位小数;收入为正、支出为负)。", solve10),
    ("11", "long_count", "long 档笔数,整数",
     "风控按持仓时长分档:fast 档为持仓 < 2 小时,mid 档为 2 小时 ≤ 持仓 < 24 小时,"
     "long 档为持仓 ≥ 24 小时(区间左闭右开,恰好 24.0 小时归入 long 档)。"
     "现有 5 笔持仓,时长分别为 1.5、2.0、23.9、24.0、48.0 小时。求归入 long 档的笔数。", solve11),
    ("12", "mm", "维持保证金,保留2位小数",
     "某合约维持保证金分级如下:名义价值 ≤ 100,000 USDT 档,维持保证金率 0.5%,速算扣除数 0;"
     "名义价值 > 100,000 且 ≤ 500,000 USDT 档,维持保证金率 1.0%,速算扣除数 500。"
     "维持保证金 = 名义价值 × 该档维持保证金率 - 该档速算扣除数。用户持仓名义价值 300,000 USDT。"
     "求维持保证金(USDT,保留 2 位小数)。", solve12),
    ("13", "alloc", "分配滑点预算,保留2位小数",
     "组合含 3 笔订单,名义价值分别为 100,000、200,000、600,000 USDT。总滑点预算 900 USDT,"
     "规定按各笔名义价值占总名义的比例加权分配(不是等权平均分配)。"
     "求第 2 笔(名义 200,000)分得的滑点预算(USDT,保留 2 位小数)。", solve13),
    ("14", "rebate", "返佣金额,保留2位小数",
     "某返佣活动规则:月累计手续费达到 1,000 USDT 后,仅对超出 1,000 USDT 的部分按 10% 返佣"
     "(边际阶梯,非对全额返佣)。用户当月累计手续费 1,500 USDT。求返佣金额(USDT,保留 2 位小数)。", solve14),
    ("15", "r_multiple", "R倍数,保留2位小数",
     "某笔已平仓交易:毛利 +200 USDT,手续费支出 20 USDT,滑点损耗 5 USDT,"
     "初始风险(开仓时止损距离对应金额)100 USDT。"
     "R 倍数定义为净盈亏(毛利扣除手续费与滑点)除以初始风险。求 R 倍数(保留 2 位小数)。", solve15),
    ("16", "risk_pct", "单笔风险百分比,保留2位小数",
     "某引擎基础单笔风险为权益的 2%。回撤减速带规则:距峰值回撤 ≥ 10% 时单笔风险 × 0.5,"
     "≥ 20% 时 × 0.25(系数只减不增)。回撤判定所用权益规定取 min(已实现权益, 标记权益)"
     "(防止浮盈掩盖回撤)。当前:峰值权益 1,500,已实现权益 1,000,标记权益 1,300。"
     "求实际生效的单笔风险占权益百分比(保留 2 位小数,不带百分号)。", solve16),
    ("17", "annual_rate", "年化资金费率百分比,保留4位小数",
     "某永续合约当前 8 小时资金费率为 -0.01%(每 8 小时结算一次,每日 3 次)。"
     "求按单利口径年化的资金费率百分比(年化基数 365 天,公式:8h费率 × 每日结算次数 × 365 × 100)。"
     "(保留 4 位小数,带负号)", solve17),
    ("18", "avg_px", "已成交均价,保留4位小数",
     "某限价买单总量 1,000 张,成交情况:400 张 @ 10.0,350 张 @ 10.2;"
     "剩余 250 张仍以挂单价 10.5 挂在订单簿上未成交。求已成交部分的成交均价(保留 4 位小数)。", solve18),
    ("19", "max_risk", "最大单笔风险百分比,保留2位小数",
     "某组合风险闸门:同向(同簇同向)总风险上限为权益的 15%,同簇同向最多 2 腿,单笔风险上限 15%。"
     "当前组合已有 1 腿同簇同向持仓,占用同向风险 8%。新候选信号与已有持仓同簇且同向。"
     "在同时满足同向上限与腿数上限的前提下,求新候选允许的最大单笔风险占权益百分比"
     "(保留 2 位小数,不带百分号)。", solve19),
]


def build_question(body: str, key: str, desc: str) -> str:
    return body + fmt_block(key, desc)


def emit() -> int:
    lines = []
    for num, key, desc, body, fn in SPECS:
        qid = f"{CATEGORY}-20261015-{num}"
        value = fn()
        obj = {
            "id": qid,
            "category": CATEGORY,
            "kind": "numeric",
            "question": build_question(body, key, desc),
            "expected": {key: value},
            "suite_version": SUITE,
            "seed": SEED,
        }
        lines.append(json.dumps(obj, ensure_ascii=False))
    JSONL.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"EMIT {len(lines)} -> {JSONL}")
    return 0


def check() -> int:
    if not JSONL.exists():
        print(f"ERR jsonl not found: {JSONL}")
        return 1
    rows = {}
    for line in JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        rows[o["id"]] = o
    spec_by_id = {f"{CATEGORY}-20261015-{num}": (key, fn) for num, key, _, _, fn in SPECS}
    bad = 0
    for qid, (key, fn) in spec_by_id.items():
        if qid not in rows:
            print(f"MISMATCH {qid} expected=<missing> solver=<missing>")
            bad += 1
            continue
        exp = rows[qid]["expected"].get(key)
        got = fn()
        if exp == got:
            print(f"OK {qid} {got}")
        else:
            print(f"MISMATCH {qid} expected={exp} solver={got}")
            bad += 1
    return 0 if bad == 0 else 1


def main() -> int:
    if "--emit" in sys.argv:
        return emit()
    return check()


if __name__ == "__main__":
    sys.exit(main())
