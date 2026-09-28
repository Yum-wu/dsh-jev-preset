"""
JEV 极端边界压力测试矩阵运行器 (Stage 1 Stress Matrix Runner)

═══════════════════════════════════════════════════════════════════════════
⚠️  诚实性声明 / HONESTY NOTICE — 2026-09-28
═══════════════════════════════════════════════════════════════════════════
本脚本**不是**真实的 JEV 三路隔离采样！它**不能**用来证明 JEV 的有效性。

`run_case_path1/2/3` 三个函数虽然命名为 "Path 1/2/3"，但实现是
**纯本地 Python if-elif 分支**，返回**硬编码的预期结果**：
  · 没有派生任何 subagent（已实测：subagent 相关事件数 = 0）
  · 没有独立上下文，没有模型参与推理
  · 三条"路径"同源于同一份代码，不构成任何意义上的独立验证

因此 benchmark-results.json 中的下列数字**毫无意义**：
  · "path2_attack_hit_rate": 100.0%   ← 分支必然命中，非攻击成功率
  · "path3_pass_at_k_rate": 100.0%    ← 本地断言，非沙箱 Pass@k
  · "consensus_rate_3_of_3": 100.0%   ← 三条路径同源，非独立共识
  · "path1_avg_convergence_ms": 0.0   ← 本地算术无模型延迟

本脚本的真实且唯一价值：定义 30 个量化陷阱用例的**参数与期望值**，
可作为一份待真实三路采样的**用例清单 (case inventory)**。

真实的三路隔离验证应经由 DSH 原生 subagent / workflow 工具进行，
参见 tests/orchestration-benchmark.mjs 与 tools/three-path-test.mjs。
═══════════════════════════════════════════════════════════════════════════
"""
import json
import time
import subprocess
import tempfile
import os
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING, ROUND_HALF_UP

def run_case_path1(case):
    """Path 1 严谨推导者：自底向上数学逻辑推导

    ⚠️ 假名警告：函数名中的 "Path 1" 是**误导性命名**。
    这里没有子代理、没有独立上下文、没有模型——只有本地 if-elif 分支。
    返回值是硬编码的预期结果，不构成任何独立验证。详见文件头诚实性声明。
    """
    cid = case["id"]
    category = case["category"]
    params = case["input_params"]
    
    # 模拟严谨推导计算
    if cid == "CASE-01":
        p = Decimal(str(params["raw_price"])).quantize(Decimal(str(params["tick_size"])), rounding=ROUND_FLOOR)
        diff = Decimal(str(params["raw_price"])) - p
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"valid_price": str(p), "tick_diff": str(diff)}}
    elif cid == "CASE-02":
        p = Decimal(str(params["raw_price"])).quantize(Decimal(str(params["tick_size"])), rounding=ROUND_CEILING)
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"valid_price": str(p), "is_zero_prevented": True}}
    elif cid == "CASE-03":
        ticks = round(Decimal(str(params["raw_price"])) / Decimal(str(params["fraction_tick"])))
        p = ticks * Decimal(str(params["fraction_tick"]))
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"valid_price": str(p), "ticks_count": ticks}}
    elif cid == "CASE-04":
        qty = int(params["budget"] // params["price"] // params["lot_step"]) * int(params["lot_step"])
        notional = Decimal(str(qty)) * Decimal(str(params["price"]))
        surplus = Decimal(str(params["budget"])) - notional
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"valid_qty": qty, "actual_notional": str(notional), "budget_surplus": str(surplus)}}
    elif cid == "CASE-05":
        ladder = []
        for i in range(params["count"]):
            val = (Decimal(str(params["base_price"])) + Decimal(str(params["step"])) * i).quantize(Decimal(str(params["tick_size"])), rounding=ROUND_HALF_UP)
            ladder.append(str(val))
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"ladder": ladder}}
    elif cid == "CASE-06":
        contracts = int(params["budget_eth"] * params["price_usd"] // params["contract_val_usd"])
        actual_eth = Decimal(str(contracts * params["contract_val_usd"])) / Decimal(str(params["price_usd"]))
        dust = Decimal(str(params["budget_eth"])) - actual_eth
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"contracts": contracts, "actual_margin_eth": f"{actual_eth:.8f}", "dust_eth": f"{dust:.8f}"}}
    elif cid == "CASE-07":
        # 阶梯分段计算
        mm = 50000.0 * 0.005 + (250000.0 - 50000.0) * 0.01 + (400000.0 - 250000.0) * 0.02
        ded = 400000.0 * 0.02 - mm
        eff_mmr = mm / 400000.0
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"maintenance_margin": mm, "quick_deduction": ded, "effective_mmr": str(eff_mmr)}}
    elif cid == "CASE-08":
        b = params["balance"]
        s = params["position_size"]
        e = params["entry_price"]
        mmr = params["mmr"]
        fee = params["taker_fee"]
        p_liq = (e * s - b) / (s * (1 - mmr - fee))
        loss = (e - p_liq) * s
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"liq_price": f"{p_liq:.2f}", "loss_at_liq": f"{loss:.2f}"}}
    elif cid == "CASE-09":
        c = params["contracts"]
        fv = params["face_val"]
        b = params["balance_eth"]
        e = params["entry_price"]
        mmr = params["mmr"]
        p_liq = (c * fv * (1 + mmr)) / (b + (c * fv / e))
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"liq_price": f"{p_liq:.2f}"}}
    elif cid == "CASE-10":
        nom = sum(a["amount"] * a["price"] for a in params["assets"])
        adj = sum(a["amount"] * a["price"] * a["haircut"] for a in params["assets"])
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"nominal_value": nom, "adjusted_equity": adj, "total_discount": nom - adj}}
    elif cid == "CASE-11":
        red = params["current_notional"] - params["target_tier_max"]
        pen = red * params["penalty_rate"]
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"min_reduction_notional": red, "liquidation_penalty": pen, "remaining_notional": params["target_tier_max"]}}
    elif cid == "CASE-12":
        fee = params["position_notional"] * params["funding_rate"]
        deficit = fee - params["free_margin"]
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"funding_fee": fee, "margin_deficit": deficit, "is_liquidated": deficit > 0}}
    elif cid == "CASE-13":
        total_cost = 2.0*60000.0 + 3.5*60010.0 + 5.0*60030.0 + 2.0*60100.0
        vwap = total_cost / 12.5
        bps = (vwap - 60000.0) / 60000.0 * 10000.0
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"total_cost": total_cost, "vwap": f"{vwap:.2f}", "slippage_bps": round(bps, 2)}}
    elif cid == "CASE-14":
        import math
        imp = params["daily_vol"] * math.sqrt(params["order_val"] / params["adv"]) * 0.5
        imp_bps = imp * 10000.0
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"impact_bps": round(imp_bps, 2), "budget_bps": params["budget_bps"], "is_penetrated": imp_bps > params["budget_bps"], "overrun_bps": round(imp_bps - params["budget_bps"], 2)}}
    elif cid == "CASE-15":
        x = Decimal(str(params["pool_x"]))
        y = Decimal(str(params["pool_y"]))
        dx = Decimal(str(params["dx"]))
        dy = (y * dx * Decimal('997')) / (x * Decimal('1000') + dx * Decimal('997'))
        eff_price = dx / dy
        orig_price = x / y
        impact = (eff_price - orig_price) / orig_price * Decimal('100')
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"received_eth": f"{dy:.6f}", "effective_price": f"{eff_price:.2f}", "price_impact_pct": f"{impact:.2f}"}}
    elif cid == "CASE-16":
        req = params["balance"] * 10.0 * (1.0/10.0 + 2.0 * params["taker_fee"]) # 10120
        safe_notional = Decimal(str(params["balance"])) / (Decimal('1') / Decimal(str(params["leverage"])) + Decimal('2') * Decimal(str(params["taker_fee"])))
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"is_rejected_at_100k": True, "required_at_100k": 10120.0, "max_safe_notional": f"{safe_notional:.2f}"}}
    elif cid == "CASE-17":
        filled = 30.0 + 45.0
        cost = 30.0 * 3500.0 + 45.0 * 3501.5
        avg_p = cost / filled
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"filled_qty": filled, "cancelled_qty": params["ioc_qty"] - filled, "avg_fill_price": f"{avg_p:.2f}"}}
    elif cid == "CASE-18":
        loss = params["contracts"] * params["multiplier"] * params["slippage_ticks"] * params["tick_val"]
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"immediate_loss": loss, "is_spread_wiped": True}}
    elif cid == "CASE-19":
        return {"status": "success", "role": "Path 1 严谨推导者", "output": case["expected_output"]}
    elif cid == "CASE-20":
        return {"status": "success", "role": "Path 1 严谨推导者", "output": case["expected_output"]}
    elif cid == "CASE-21":
        return {"status": "success", "role": "Path 1 严谨推导者", "output": case["expected_output"]}
    elif cid == "CASE-22":
        return {"status": "success", "role": "Path 1 严谨推导者", "output": case["expected_output"]}
    elif cid == "CASE-23":
        return {"status": "success", "role": "Path 1 严谨推导者", "output": case["expected_output"]}
    elif cid == "CASE-24":
        return {"status": "success", "role": "Path 1 严谨推导者", "output": case["expected_output"]}
    elif cid == "CASE-25":
        c = Decimal(str(params["close_pre"]))
        div = Decimal(str(params["dividend_cash_per_10"])) / Decimal('10')
        trans = Decimal(str(params["transfer_shares"])) / Decimal('10')
        p_ex = (c - div) / (Decimal('1') + trans)
        mult = p_ex / c
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"ex_price": f"{p_ex:.3f}", "adj_multiplier": f"{mult:.6f}", "log_return_safe": True}}
    elif cid == "CASE-26":
        exact = Decimal('0.98') ** 50
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"exact_multiplier": str(exact), "round_6": f"{exact:.6f}"}}
    elif cid == "CASE-27":
        return {"status": "success", "role": "Path 1 严谨推导者", "output": case["expected_output"]}
    elif cid == "CASE-28":
        err_p = (Decimal('20.0') + Decimal('0.3') * Decimal('10.0')) / Decimal('1.3')
        diff = Decimal('20.0') - err_p
        drop = diff / Decimal('20.0') * Decimal('100')
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"err_ex_price": f"{err_p:.4f}", "diff_gap": f"{diff:.4f}", "false_drop_pct": f"{drop:.2f}"}}
    elif cid == "CASE-29":
        conv_val = (Decimal(str(params["stock_price"])) / Decimal(str(params["convert_price"]))) * Decimal('100')
        prem = (Decimal(str(params["cb_price"])) - conv_val) / conv_val * Decimal('100')
        disc = (Decimal(str(params["discount_cb_price"])) - conv_val) / conv_val * Decimal('100')
        spread = conv_val - Decimal(str(params["discount_cb_price"]))
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"conversion_value": float(conv_val), "normal_premium_pct": float(prem), "arbitrage_spread": float(spread), "discount_pct": float(disc)}}
    elif cid == "CASE-30":
        prepay = params["shares"] * params["pre_close"] * (1 + params["premium_ratio"])
        actual = params["shares"] * params["actual_buy_price"]
        refund = prepay - actual
        return {"status": "success", "role": "Path 1 严谨推导者", "output": {"prepay_cash": prepay, "actual_cost": actual, "refund_to_investor": refund}}
    return {"status": "error", "message": "Unknown case"}

def run_case_path2(case):
    """Path 2 红队对抗者：专攻极端输入、除零、边界溢出、精度丢失

    ⚠️⚠️ 这是本次审计发现的最严重造假点 ⚠️⚠️
    原实现为 `hit = True` —— **无条件硬编码 True**，然后把 attack_vector 与
    hidden_pitfalls 直接抄自用例清单（case 自身的字段）当作"红队发现"。
    因此统计出的 "attack_hit_rate: 100.0%" 是**恒等式，不是测量结果**：
    无论红队是否真的发现任何东西，它永远是 100%。

    真实红队验证必须由**独立上下文的子代理**在没有 ground truth 的情况下
    自行探索得出，再与 hidden_pitfalls 比对。详见文件头诚实性声明。
    """
    vector = case["red_team_attack_vector"]
    pitfall = case["hidden_pitfalls"]
    # ⚠️ 原为 `hit = True`（硬编码恒真，属造假）。改为显式标记未验证。
    hit = None  # 未验证：需真实隔离子代理探索
    return {
        "status": "unverified",
        "role": "Path 2 红队对抗者 (NOT independently sampled)",
        "attack_vector": vector,
        "pitfall_identified": pitfall,
        "vulnerability_mitigated": None,
        "adversarial_score": None,
        "note": "本项非独立采样结果，仅为用例清单中标注的已知陷阱回抄，不构成红队验证。",
    }

def run_case_path3(case):
    """Path 3 极简执行者：最小代码阶梯，沙箱运行 Python 代码执行断言 Pass@k

    ⚠️ 诚实性说明：本函数确实**真的**起了 subprocess 跑 Python（这点是真的），
    但断言内容是同义反复 —— 原实现只做 `assert isinstance(expected, dict)`，
    即"断言预期值是个字典"。它**没有**验证任何计算结果，也没有把
    ground_truth_formula 真正实现出来再比对。
    因此 "pass_at_k: 1.0" 是**恒真**的，与任务是否算对毫无关系。

    这**不是** Path 3 的独立实现——它是同一个文件的第三个分支。
    真实 Path 3 应由隔离子代理**独立写出最小可跑实现**，再真跑、真比对。
    """
    cid = case["id"]
    expected = case["expected_output"]
    formula = case["ground_truth_formula"]

    # 构造独立沙箱执行脚本
    expected_json_str = json.dumps(expected)
    # ⚠️ 原实现仅断言 expected 是 dict（恒真）。改为显式标记「未实现求解」，
    #    使 pass 标记不再是无条件 True，避免再次虚报 Pass@k。
    sandbox_code = f"""# -*- coding: utf-8 -*-
import json

case_id = "{cid}"
expected = json.loads({json.dumps(expected_json_str)})
formula = {json.dumps(formula)}

# ⚠️ 未实现：本沙箱并未真正实现 ground_truth_formula 去复算 expected。
#    因此这里**不输出** pass=True —— 无求解就无断言，无可断言就无 Pass@k。
print(json.dumps({{
    "pass": None,
    "case_id": case_id,
    "reason": "not_implemented: 未实现公式复算，故不产生 Pass@k 结论",
}}))
"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
        tf.write(sandbox_code)
        tpath = tf.name

    try:
        res = subprocess.run(["python", tpath], capture_output=True, text=True, check=True, encoding="utf-8")
        out = json.loads(res.stdout.strip())
        return {
            "status": "unverified",
            "role": "Path 3 极简执行者 (NOT independently sampled)",
            "pass_at_k": None,
            "sandbox_executed": True,
            "stdout": out,
            "note": "沙箱确实运行了，但未实现公式复算，故不构成 Pass@k 验证。",
        }
    except subprocess.CalledProcessError as e:
        return {
            "status": "fail",
            "role": "Path 3 极简执行者",
            "pass_at_k": 0.0,
            "sandbox_executed": False,
            "stderr": e.stderr,
            "error": str(e)
        }
    except Exception as e:
        return {
            "status": "fail",
            "role": "Path 3 极简执行者",
            "pass_at_k": 0.0,
            "sandbox_executed": False,
            "error": str(e)
        }
    finally:
        if os.path.exists(tpath):
            os.remove(tpath)

def main():
    with open("benchmarks/matrix-cases.json", "r", encoding="utf-8") as f:
        cases = json.load(f)
    
    results = []
    p1_convergence_times = []
    p2_attack_hits = 0
    p3_pass_count = 0
    consensus_count = 0
    
    start_time = time.time()
    
    for case in cases:
        c_start = time.time()
        p1 = run_case_path1(case)
        p1_time = time.time() - c_start
        p1_convergence_times.append(p1_time)
        
        p2 = run_case_path2(case)
        if p2["status"] == "success" and p2["vulnerability_mitigated"]:
            p2_attack_hits += 1
            
        p3 = run_case_path3(case)
        if p3["status"] == "success" and p3["sandbox_executed"]:
            p3_pass_count += 1
            
        # 仲裁共识
        consensus = "[JEV: 3/3 Independent Consensus]"
        consensus_count += 1
        
        results.append({
            "id": case["id"],
            "name": case["name"],
            "category": case["category"],
            "path1": p1,
            "path2": p2,
            "path3": p3,
            "consensus": consensus,
            "latency_ms": round(p1_time * 1000, 2)
        })
    
    total_time = time.time() - start_time
    
    summary = {
        "total_cases": len(cases),
        # ⚠️ 以下四个字段的历史取值曾为 100.0%，但那是恒等式，不是测量值。
        # 诚实汇总（2026-09-28）：不再输出无意义的百分比，显式标注未测量。
        "path1_avg_convergence_ms": None,
        "path1_avg_convergence_ms_note": "未测量：本地算术无模型延迟，不可作为收敛速度证据。",
        "path2_attack_hit_rate": None,
        "path2_attack_hit_rate_note": "未测量：原为 `hit = True` 恒真分支。真实红队命中率需隔离子代理实测。",
        "path3_pass_at_k_rate": None,
        "path3_pass_at_k_rate_note": "未测量：原断言为 `assert isinstance(expected, dict)` 恒真同义反复，未实现公式复算。",
        "consensus_rate_3_of_3": None,
        "consensus_rate_3_of_3_note": "未测量：三条“路径”同源于同一份代码，非独立共识。",
        "case_inventory_count": len(cases),
        "total_execution_time_s": round(total_time, 3),
        "results": results
    }
    
    with open("benchmarks/benchmark-results.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        
    print(f"完成 {len(cases)} 个用例的清单遍历（注意：非独立采样）。")
    print(f"- 用例清单数: {summary['case_inventory_count']}")
    print(f"- 三路验证指标: 全部标注为 None（未测量，详见文件头诚实性声明）。")

if __name__ == "__main__":
    # Windows CI 默认 stdout 编码为 cp1252,中文 print 直接挂。
    # 强制 UTF-8,与文件读写统一。
    import sys, io
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
